"""Prepare FinanceBench ground truth after ingestion, without synthetic LLM calls."""

import json
import random
from pathlib import Path


def prepare(
    source=Path("data/raw_qa_pairs.json"), target=Path("evaluation/golden_dataset.json")
):
    rows = json.loads(source.read_text())
    valid = [row for row in rows if row.get("question") and row.get("answer")]
    if not valid:
        raise ValueError("No question/answer pairs found; run ingestion first")
    random.Random(42).shuffle(valid)
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(json.dumps(valid, indent=2))
    return len(valid)


if __name__ == "__main__":
    print(f"Prepared {prepare()} FinanceBench evaluation pairs")
