"""Protect benchmark evidence against silent sample loss and invalid scores."""

import json
import pytest

from evaluation.benchmark import METRICS, bootstrap_ci, run_suite, select_questions


def test_selection_is_reproducible_and_rejects_duplicates():
    rows = [{"question": f"q{i}", "answer": "a"} for i in range(20)]
    assert select_questions(rows, 5, 42) == select_questions(rows, 5, 42)
    assert select_questions(rows, 5, 42) != select_questions(rows, 5, 43)
    with pytest.raises(ValueError, match="Duplicate"):
        select_questions([rows[0], rows[0]], 2, 42)
    with pytest.raises(ValueError):
        select_questions([{"question": "q", "answer": ""}], 1, 42)


def test_failure_is_preserved_without_becoming_a_quality_score(tmp_path):
    questions = [{"question": "q1", "answer": "a"}, {"question": "q2", "answer": "a"}]
    configs = [{"name": "baseline"}, {"name": "candidate"}]

    def evaluate(config, row):
        if config["name"] == "candidate":
            raise RuntimeError("private provider exception with credential")
        return {
            "answer": "a",
            "retrieved_sources": [],
            "scores": dict.fromkeys(METRICS, 0.75),
            "judge_reasons": dict.fromkeys(METRICS, "fixture reason"),
        }

    output = tmp_path / "run"
    summary = run_suite(questions, configs, evaluate, output, {"fixture": True})
    records = [
        json.loads(line)
        for line in (output / "attempts.jsonl").read_text().splitlines()
    ]
    assert len(records) == 4
    assert summary[0]["succeeded"] == 2
    assert summary[1]["failed"] == 2
    assert summary[1]["metrics"]["faithfulness"] == {
        "mean": None,
        "ci_95": None,
        "n": 0,
    }
    assert "private provider exception" not in (output / "attempts.jsonl").read_text()
    assert len(json.loads((output / "manifest.json").read_text())["question_ids"]) == 2
    with pytest.raises(FileExistsError):
        run_suite(questions, configs, evaluate, output, {})


@pytest.mark.parametrize("score", [float("nan"), float("inf"), -1, 1.5, None])
def test_invalid_judge_score_cannot_be_published_as_success(tmp_path, score):
    def evaluate(config, row):
        return {
            "answer": "a",
            "retrieved_sources": [],
            "scores": dict.fromkeys(METRICS, score),
            "judge_reasons": {},
        }

    summary = run_suite(
        [{"question": "q", "answer": "a"}],
        [{"name": "baseline"}],
        evaluate,
        tmp_path / "run",
        {},
    )
    assert summary[0]["failed"] == 1
    assert summary[0]["metrics"]["faithfulness"]["mean"] is None


def test_confidence_interval_seed_and_empty_sample():
    assert bootstrap_ci([0, 0.2, 0.8, 1], 42) == bootstrap_ci([0, 0.2, 0.8, 1], 42)
    assert bootstrap_ci([], 42) == {"mean": None, "ci_95": None, "n": 0}
