"""The counterfactual benchmark's edits, leak check, grader and runner, offline."""

import asyncio
import json
import os
import sys
from types import SimpleNamespace

import pytest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "..", "scripts"))

import counterfactual_run as cr  # noqa: E402
from evaluation.counterfactual.edits import (  # noqa: E402
    FixtureError,
    apply_ops,
    build_arm,
    leaks,
)
from evaluation.counterfactual.grade import (  # noqa: E402
    case_passes,
    figures,
    grade_arm,
)

# Overlapping chunks, as the hierarchical chunker produces: the capex row is in both.
CHUNKS = [
    "Consolidated Statement of Cash Flows\nPurchases of property, plant and "
    "equipment (PP&E)\n(1,577)\n(1,373)\n(1,420)\nProceeds from sale of PP&E\n262",
    "Purchases of property, plant and equipment (PP&E)\n(1,577)\n(1,373)",
    "Total revenue 32,765 and 11,577 other",
]
CASE = {
    "id": "case1",
    "split": "dev",
    "unit": "millions",
    "expected": {"A": 1577, "B": 1777, "C": 1577},
    "trap": {"B": 1577, "C": 1473, "D": 1577},
    "arms": {
        "B": {
            "ops": [{"re": r"\(1,577\)", "sub": "(1,777)"}],
            "gone": ["1,577"],
            "present": ["1,777"],
        },
        "C": {
            "ops": [{"re": r"\(1,373\)", "sub": "(1,473)"}],
            "gone": ["1,373"],
            "present": ["1,577"],
        },
        "D": {
            "ops": [
                {
                    "re": r"Purchases of property, plant and equipment \(PP&E\)\n"
                    r"\(1,577\)\n\(1,373\)(\n\(1,420\))?\n?",
                    "sub": "",
                }
            ],
            "gone": ["1,577"],
        },
    },
}


# ── Edits and leak check ────────────────────────────────────────────────────────


def test_edits_apply_to_every_overlapping_chunk():
    b = build_arm(CASE, CHUNKS, "B")
    assert leaks(b, ["1,577"]) == []  # "11,577" in chunk 3 is a different number
    assert sum("1,777" in c for c in b) == 2


def test_an_edit_that_matches_nothing_is_a_fixture_error():
    with pytest.raises(FixtureError, match="matched nothing"):
        apply_ops(CHUNKS, [{"re": "no such row", "sub": ""}])


def test_leak_check_catches_a_value_left_in_another_chunk():
    partial = {
        **CASE,
        "arms": {
            "B": {
                **CASE["arms"]["B"],
                "ops": [
                    {
                        "re": r"equipment \(PP&E\)\n\(1,577\)\n\(1,373\)\n\(1,420\)",
                        "sub": "x",
                    }
                ],
            }
        },
    }
    with pytest.raises(FixtureError, match="still present"):
        build_arm(partial, CHUNKS, "B")


def test_leak_check_does_not_match_inside_longer_numbers():
    assert leaks(["11,577 and 1,5770"], ["1,577"]) == []
    assert leaks(["($1,577.0)"], ["1,577"]) == ["1,577"]


def test_removing_evidence_leaves_unrelated_rows():
    d = build_arm(CASE, CHUNKS, "D")
    assert "Proceeds from sale of PP&E\n262" in d[0]
    assert d[2] == CHUNKS[2]


def test_arm_a_is_the_capture_unchanged():
    assert build_arm(CASE, CHUNKS, "A") == CHUNKS


# ── Grader ──────────────────────────────────────────────────────────────────────


@pytest.mark.parametrize(
    "answer,unit,expected",
    [
        ("Capex was $1,577 million in FY2018.", "millions", [1577.0]),
        ("about $1.58 billion", "millions", [1580.0]),
        ("$8,738 million", "billions", [8.738]),
        ("$8.7 bn", "billions", [8.7]),
        ("In FY2018 (2018) it was (1,577)", "millions", [1577.0]),
    ],
)
def test_figures_convert_scale_and_skip_years(answer, unit, expected):
    assert figures(answer, unit) == pytest.approx(expected)


@pytest.mark.parametrize(
    "arm,answer,outcome",
    [
        ("A", "FY2018 capex was $1,577 million.", "correct"),
        ("A", "Capex was $1.58 billion.", "correct"),  # within 1% after conversion
        ("A", "Insufficient context to answer this question accurately.", "refused"),
        ("A", "Capex was $1,420 million.", "wrong"),
        ("B", "Capex was $1,777 million.", "correct"),
        ("B", "Capex was $1,577 million.", "trap"),  # ignored the edit
        ("B", "Either $1,777 million or $1,577 million.", "ambiguous"),
        ("C", "Capex was $1,577 million.", "correct"),
        ("C", "Capex was $1,473 million.", "trap"),  # took the other year
        ("C", "Capex was high.", "ambiguous"),
        ("D", "Insufficient context to answer this question accurately.", "correct"),
        ("D", "Insufficient context; FY2017 was $1,373 million.", "correct"),
        ("D", "Capex was $1,577 million.", "leaked"),
        ("D", "Capex was $1,400 million.", "wrong"),
        ("D", "Capex was high.", "ambiguous"),
    ],
)
def test_grade_arm(arm, answer, outcome):
    got = grade_arm(
        arm, answer, "millions", CASE["expected"].get(arm), CASE["trap"].get(arm)
    )
    assert got == outcome


def test_provider_failure_is_an_error_not_a_refusal():
    assert grade_arm("D", None, "millions", None, 1577, error="HTTP 500") == "error"


def test_a_case_passes_only_when_all_four_arms_pass():
    assert case_passes(dict.fromkeys("ABCD", "correct"))
    assert not case_passes({**dict.fromkeys("ABC", "correct"), "D": "leaked"})
    assert not case_passes(dict.fromkeys("ABC", "correct"))


# ── Runner ──────────────────────────────────────────────────────────────────────


@pytest.fixture
def bench(tmp_path, monkeypatch):
    contexts = tmp_path / "contexts"
    contexts.mkdir()
    ctx = {
        "id": "case1",
        "question_sent": "What is the FY2018 capex for 3M?",
        "chunks": [
            {"text": t, "metadata": {"company": "3M", "year": "2018"}} for t in CHUNKS
        ],
    }
    (contexts / "case1.json").write_text(json.dumps(ctx))
    monkeypatch.setattr(cr, "CONTEXTS", contexts)
    seen = []

    async def fake(question, chunks):
        seen.append((question, chunks))
        text = " ".join(c["text"] for c in chunks)
        if "(1,777)" in text:
            answer = "Capex was $1,777 million."
        elif "(1,577)" in text:
            answer = "Capex was $1,577 million."
        else:
            answer = "Insufficient context to answer this question accurately."
        resp = SimpleNamespace(answer=answer, confidence="high")
        return resp, SimpleNamespace(
            attempts=1, prompt_tokens=100, completion_tokens=10
        )

    monkeypatch.setitem(cr.SYSTEMS, "fake", fake)
    monkeypatch.setattr(cr.time, "sleep", lambda s: None)
    args = SimpleNamespace(
        run=str(tmp_path / "run"), split="dev", systems=["fake"], limit=None, pause=0
    )
    return SimpleNamespace(
        args=args, manifest={"version": 1, "cases": [CASE]}, seen=seen
    )


def test_runner_grades_all_arms_and_resumes_without_new_calls(bench):
    asyncio.run(cr.run(bench.args, bench.manifest))
    assert len(bench.seen) == 4
    s = cr.summarize(bench.manifest, cr.Path(bench.args.run), "dev")["systems"]["fake"]
    assert s["complete_passes"] == 1
    assert s["provider_attempts"] == 4 and s["prompt_tokens"] == 400

    asyncio.run(cr.run(bench.args, bench.manifest))
    assert len(bench.seen) == 4  # everything was already done


def test_model_input_carries_no_arm_names_or_grading_data(bench):
    asyncio.run(cr.run(bench.args, bench.manifest))
    for question, chunks in bench.seen:
        assert question == "What is the FY2018 capex for 3M?"
        payload = json.dumps(chunks)
        assert all(set(c) == {"text", "metadata"} for c in chunks)
        for hint in ('"arm"', "expected", "trap", "case1", "split"):
            assert hint not in payload


def test_hand_review_overrides_the_automatic_grade(bench):
    asyncio.run(cr.run(bench.args, bench.manifest))
    run = cr.Path(bench.args.run)
    (run / "reviews.jsonl").write_text(
        json.dumps({"id": "case1", "arm": "C", "system": "fake", "label": "wrong"})
        + "\n"
    )
    s = cr.summarize(bench.manifest, run, "dev")["systems"]["fake"]
    assert s["complete_passes"] == 0 and s["per_arm"]["C"] == {"wrong": 1}


def test_rate_limit_waits_then_retries(bench, monkeypatch):
    calls = {"n": 0}
    waits = []

    async def flaky(question, chunks):
        calls["n"] += 1
        if calls["n"] == 1:
            err = Exception("rate_limit_exceeded: Please try again in 3.5s")
            err.status_code = 429
            raise RuntimeError("wrapped") from err
        return SimpleNamespace(
            answer="Capex was $1,577 million.", confidence="high"
        ), SimpleNamespace(attempts=1, prompt_tokens=1, completion_tokens=1)

    monkeypatch.setitem(cr.SYSTEMS, "flaky", flaky)
    monkeypatch.setattr(cr, "_wait_or_stop", lambda s, what: waits.append(s))
    rec = asyncio.run(cr.run_one("flaky", CASE, cr.load_context("case1"), "A"))
    assert waits == [3.5] and rec["error"] is None and calls["n"] == 2


def test_a_daily_limit_stops_the_run_and_keeps_finished_arms(bench, monkeypatch):
    n = {"calls": 0}

    async def limited(question, chunks):
        n["calls"] += 1
        if n["calls"] > 2:
            err = Exception("rate_limit_exceeded: Please try again in 2h1m")
            err.status_code = 429
            raise err
        return SimpleNamespace(
            answer="Capex was $1,577 million.", confidence="high"
        ), SimpleNamespace(attempts=1, prompt_tokens=1, completion_tokens=1)

    monkeypatch.setitem(cr.SYSTEMS, "limited", limited)
    bench.args.systems = ["limited"]
    asyncio.run(cr.run(bench.args, bench.manifest))
    done = cr.read_keyed(cr.Path(bench.args.run) / "outputs.jsonl")
    assert len(done) == 2
