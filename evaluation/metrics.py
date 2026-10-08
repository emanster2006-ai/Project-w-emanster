"""
Metric collection, persistence, and comparison utilities.
Tracks eval runs over time so we can show improvement trajectory.
"""

import json
import logging
from dataclasses import asdict, dataclass
from datetime import datetime, timezone
from pathlib import Path

logger = logging.getLogger(__name__)

METRICS_HISTORY_PATH = Path("evaluation/metrics_history.json")


@dataclass
class EvalRun:
    run_id: str
    timestamp: str
    config_name: str
    n_questions: int
    faithfulness: float
    contextual_precision: float
    answer_relevancy: float
    pass_rate: float
    notes: str = ""

    @property
    def composite_score(self) -> float:
        """Equal-weight composite for ranking configs."""
        return (
            self.faithfulness + self.contextual_precision + self.answer_relevancy
        ) / 3.0


def load_history() -> list[EvalRun]:
    if not METRICS_HISTORY_PATH.exists():
        return []
    with open(METRICS_HISTORY_PATH) as f:
        raw = json.load(f)
    return [EvalRun(**r) for r in raw]


def save_run(run: EvalRun) -> None:
    history = load_history()
    history.append(run)
    with open(METRICS_HISTORY_PATH, "w") as f:
        json.dump([asdict(r) for r in history], f, indent=2)
    logger.info(f"Saved eval run: {run.run_id} (composite={run.composite_score:.3f})")


def record_harness_result(
    result, config_name: str = "default", notes: str = ""
) -> EvalRun:
    """Convert a HarnessResult into an EvalRun and persist it."""
    import uuid

    run = EvalRun(
        run_id=str(uuid.uuid4())[:8],
        timestamp=datetime.now(timezone.utc).replace(tzinfo=None).isoformat(),
        config_name=config_name,
        n_questions=result.n_questions,
        faithfulness=round(result.mean_faithfulness, 4),
        contextual_precision=round(result.mean_contextual_precision, 4),
        answer_relevancy=round(result.mean_answer_relevancy, 4),
        pass_rate=round(result.pass_rate, 4),
        notes=notes,
    )
    save_run(run)
    return run


def compare_runs(run_a: EvalRun, run_b: EvalRun) -> dict:
    """Return metric deltas between two runs (b - a)."""
    return {
        "faithfulness_delta": round(run_b.faithfulness - run_a.faithfulness, 4),
        "precision_delta": round(
            run_b.contextual_precision - run_a.contextual_precision, 4
        ),
        "relevancy_delta": round(run_b.answer_relevancy - run_a.answer_relevancy, 4),
        "composite_delta": round(run_b.composite_score - run_a.composite_score, 4),
    }


def print_history_table() -> None:
    """Print a summary table of all eval runs."""
    history = load_history()
    if not history:
        print("No eval runs recorded yet. Run: make eval")
        return

    print(
        f"\n{'Run ID':<10} {'Config':<30} {'Faith':>7} {'Prec':>6} {'Relev':>6} {'Pass':>6} {'Date'}"
    )
    print("-" * 85)
    for r in sorted(history, key=lambda x: x.timestamp):
        print(
            f"{r.run_id:<10} {r.config_name:<30} "
            f"{r.faithfulness:>7.3f} {r.contextual_precision:>6.3f} "
            f"{r.answer_relevancy:>6.3f} {r.pass_rate:>5.1%}  {r.timestamp[:10]}"
        )
