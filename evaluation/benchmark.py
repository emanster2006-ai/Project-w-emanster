"""Reproducible benchmark artifacts; no model or service dependencies."""

import hashlib
import json
import math
import random
import statistics
import time
from datetime import datetime, timezone
from pathlib import Path

METRICS = ("faithfulness", "contextual_precision", "answer_relevancy")


def digest(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def select_questions(rows: list[dict], limit: int, seed: int) -> list[dict]:
    if limit < 1 or not rows:
        raise ValueError("Provide a nonempty dataset and a positive sample size")
    seen = set()
    for row in rows:
        if not all(
            isinstance(row.get(key), str) and row[key].strip()
            for key in ("question", "answer")
        ):
            raise ValueError("Each row needs nonempty question and answer strings")
        key = digest(row["question"].strip().encode())
        if key in seen:
            raise ValueError("Duplicate questions would inflate the sample size")
        seen.add(key)
    indices = list(range(len(rows)))
    random.Random(seed).shuffle(indices)
    return [rows[index] for index in indices[:limit]]


def bootstrap_ci(scores: list[float], seed: int, n_bootstrap: int = 1000) -> dict:
    if not scores:
        return {"mean": None, "ci_95": None, "n": 0}
    rng = random.Random(seed)
    means = sorted(
        statistics.mean(rng.choices(scores, k=len(scores))) for _ in range(n_bootstrap)
    )
    return {
        "mean": statistics.mean(scores),
        "ci_95": [
            means[int(0.025 * (n_bootstrap - 1))],
            means[int(0.975 * (n_bootstrap - 1))],
        ],
        "n": len(scores),
    }


def run_suite(
    questions, configurations, evaluate, output: Path, metadata: dict, seed=42
):
    """Persist every attempt, including errors. Refuse to overwrite a previous run.

    evaluate(config, row) returns answer, retrieved_sources, scores and judge_reasons.
    Latency includes retrieval, generation AND judge calls; it is not API latency.
    """
    output.mkdir(parents=True, exist_ok=False)
    manifest = {
        "schema_version": 1,
        "started_at": datetime.now(timezone.utc).isoformat(),
        "seed": seed,
        "sample_size": len(questions),
        "configurations": configurations,
        "cache": "bypassed: direct retrieval/generation calls",
        "latency_scope": "retrieval + generation + judging; excludes initial imports",
        "question_ids": [digest(row["question"].strip().encode()) for row in questions],
        "metadata": metadata,
        "limitations": [
            "Seed controls sample/order/bootstrap only; provider outputs can vary.",
            "Judge scores are proxies, not financial accuracy.",
            "Token usage and provider cost are unavailable from current wrappers.",
            "Bootstrap intervals describe successful samples only; consult failure counts.",
            "Retrieved sources are evidence candidates, not verified answer citations.",
        ],
    }
    (output / "manifest.json").write_text(json.dumps(manifest, indent=2) + "\n")
    (output / "questions.json").write_text(json.dumps(questions, indent=2) + "\n")
    records = []
    rng = random.Random(seed)
    with (output / "attempts.jsonl").open("w") as stream:
        for row in questions:
            order = list(configurations)
            rng.shuffle(order)
            for config in order:
                record = {
                    "config": config["name"],
                    "question_id": digest(row["question"].strip().encode()),
                    "question": row["question"],
                    "expected_answer": row["answer"],
                    "answer": None,
                    "retrieved_sources": [],
                    "scores": {},
                    "judge_reasons": {},
                    "token_usage": None,
                    "provider_cost_usd": None,
                }
                start = time.perf_counter()
                try:
                    result = evaluate(config, row)
                    record.update(
                        {
                            key: result[key]
                            for key in (
                                "answer",
                                "retrieved_sources",
                                "scores",
                                "judge_reasons",
                            )
                        }
                    )
                    if (
                        not isinstance(record["answer"], str)
                        or not record["answer"].strip()
                    ):
                        raise ValueError("Generation returned an empty answer")
                    for metric in METRICS:
                        value = record["scores"][metric]
                        if (
                            not isinstance(value, (int, float))
                            or not math.isfinite(value)
                            or not 0 <= value <= 1
                        ):
                            raise ValueError(f"Invalid {metric} score")
                    record["status"] = "success"
                except Exception as error:
                    record["scores"] = {}
                    record["status"] = "error"
                    record["error_type"] = type(error).__name__
                    record["error"] = (
                        "Attempt failed; inspect the provider locally without publishing credentials."
                    )
                record["elapsed_ms"] = round((time.perf_counter() - start) * 1000, 3)
                stream.write(json.dumps(record, allow_nan=False) + "\n")
                stream.flush()
                records.append(record)
    summary = []
    for config in configurations:
        attempts = [row for row in records if row["config"] == config["name"]]
        successes = [row for row in attempts if row["status"] == "success"]
        summary.append(
            {
                "config": config["name"],
                "attempted": len(attempts),
                "succeeded": len(successes),
                "failed": len(attempts) - len(successes),
                "metrics": {
                    metric: bootstrap_ci(
                        [row["scores"][metric] for row in successes], seed
                    )
                    for metric in METRICS
                },
                "mean_attempt_elapsed_ms": statistics.mean(
                    row["elapsed_ms"] for row in attempts
                ),
            }
        )
    (output / "summary.json").write_text(
        json.dumps(summary, indent=2, allow_nan=False) + "\n"
    )
    return summary
