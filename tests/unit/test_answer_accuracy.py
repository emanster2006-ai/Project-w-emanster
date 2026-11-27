"""Keep the answer-accuracy runner's arithmetic, resume logic and labels honest."""

import json
import os
import sys

import pytest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "..", "scripts"))

import answer_accuracy as aa  # noqa: E402


def test_wilson_interval_matches_known_values():
    lo, hi = aa.wilson(120, 150)
    assert lo == pytest.approx(0.7289, abs=1e-3)
    assert hi == pytest.approx(0.8560, abs=1e-3)
    assert aa.wilson(0, 0) == (0.0, 0.0)
    lo, hi = aa.wilson(0, 3)
    assert lo == pytest.approx(0.0, abs=1e-9) and 0.5 < hi < 0.6


@pytest.mark.parametrize(
    "text,header,expected",
    [
        ("", "12", 12.0),
        ("Please try again in 7.25s. Visit ...", None, 7.25),
        ("Please try again in 1m30s", None, 90.0),
        ("Please try again in 2h1m", None, 7260.0),
        ("no hint at all", None, 60.0),
    ],
)
def test_retry_after_reads_header_or_groq_message(text, header, expected):
    assert aa._retry_after(text, header) == pytest.approx(expected)


def test_long_wait_stops_the_run_instead_of_sleeping():
    with pytest.raises(aa.DailyLimit):
        aa._wait_or_stop(aa.LONG_WAIT_S + 1, "api")


def test_evidence_retrieved_uses_the_retrieval_benchmark_rule():
    evidence = "Purchases of property, plant and equipment (PP&E) (1,577) (1,373) " * 3
    assert aa.evidence_retrieved(
        ["x", "Purchases of property,  plant and\nequipment"], evidence
    )
    assert not aa.evidence_retrieved(["Total revenue 32,765"], evidence)
    assert not aa.evidence_retrieved([""], evidence)


def _write(path, recs):
    path.write_text("".join(json.dumps(r) + "\n" for r in recs))


def test_summary_counts_labels_prefers_hand_review_and_skips_errors(tmp_path):
    questions = [
        {"id": f"q{i}", "question": f"Q{i}?", "reference": ref, "question_type": t}
        for i, (ref, t) in enumerate(
            [
                ("$1577.00", "metrics"),
                ("Yes", "domain"),
                ("$8.70", "metrics"),
                ("No", "domain"),
            ]
        )
    ]
    _write(
        tmp_path / "answers.jsonl",
        [
            {
                "id": "q0",
                "answer": "Capex was $1,577 million.",
                "error": None,
                "evidence_retrieved": True,
            },
            {
                "id": "q1",
                "answer": "Yes, it is.",
                "error": None,
                "evidence_retrieved": False,
            },
            {
                "id": "q2",
                "answer": "Insufficient context",
                "error": None,
                "evidence_retrieved": True,
            },
            {"id": "q3", "answer": "", "error": "HTTP 500", "evidence_retrieved": None},
        ],
    )
    _write(
        tmp_path / "grades.jsonl",
        [
            {"id": "q0", "label": "correct", "reason": ""},
            {"id": "q1", "label": "incorrect", "reason": "", "review_label": "correct"},
            {"id": "q2", "label": "refused", "reason": ""},
            {
                "id": "q3",
                "label": "correct",
                "reason": "",
            },  # answer errored: not counted
        ],
    )
    s = aa.summarize(tmp_path, questions)
    assert (s["graded"], s["correct"], s["incorrect"], s["refused"]) == (3, 2, 0, 1)
    assert s["answer_errors"] == 1
    assert s["hand_reviewed"] == 1 and s["label_changed_on_review"] == 1
    assert s["by_retrieval"]["evidence missed"] == {"correct": 1}
    # q0: figure matched, correct. q2: no figure in answer, refused. Both agree.
    assert s["figure_check_agrees_with_label"] == [2, 2]


def test_read_jsonl_keeps_the_last_record_per_id(tmp_path):
    _write(
        tmp_path / "g.jsonl",
        [{"id": "a", "label": "refused"}, {"id": "a", "label": "correct"}],
    )
    assert aa.read_jsonl(tmp_path / "g.jsonl")["a"]["label"] == "correct"
    assert aa.read_jsonl(tmp_path / "missing.jsonl") == {}


def test_hand_reviews_file_overrides_the_judge_but_keeps_its_label(tmp_path):
    questions = [
        {"id": "q0", "question": "Q?", "reference": "-0.02", "question_type": "m"}
    ]
    _write(
        tmp_path / "answers.jsonl",
        [{"id": "q0", "answer": "-1.53%", "error": None, "evidence_retrieved": True}],
    )
    _write(
        tmp_path / "grades.jsonl", [{"id": "q0", "label": "incorrect", "reason": ""}]
    )
    _write(
        tmp_path / "reviews.jsonl",
        [{"id": "q0", "review_label": "correct", "review_note": "same figure"}],
    )
    merged = aa.read_grades(tmp_path)["q0"]
    assert merged["label"] == "incorrect" and merged["review_label"] == "correct"
    s = aa.summarize(tmp_path, questions)
    assert s["correct"] == 1 and s["label_changed_on_review"] == 1
