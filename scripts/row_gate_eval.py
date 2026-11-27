"""Would the row-aware check work as a gate on ordinary questions?

The counterfactual benchmark shows the row check flags 9/11 invented figures and 0/162
correct answers on its edited filings. A gate that refuses flagged answers is only safe
if it also leaves correct answers to ordinary questions alone. This script measures that
on a recorded accuracy run, with no model calls:

1. Rebuild each answer's context. HyDE is off in the UI defaults, so retrieval is the
   question plus its recorded sub-questions, hybrid search, dedup and rerank; all local
   and deterministic. A rebuild counts only if its sources match the recorded ones.
2. Run the row check on the recorded answer and that context.
3. Cross the flags with the final (hand-reviewed) labels.

  python scripts/row_gate_eval.py --run evaluation/runs/cerebras-2026-11-26
"""

import argparse
import asyncio
import sys
from collections import Counter
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "scripts"))

from answer_accuracy import (  # noqa: E402
    final_label,
    load_questions,
    read_grades,
    read_jsonl,
)
from security.row_grounding import check_answer  # noqa: E402

REFUSAL = "insufficient context"


def same_sources(chunks: list[dict], recorded: list[dict]) -> bool:
    got = [(c["metadata"].get("source"), round(c.get("score", 0), 3)) for c in chunks]
    want = [(s.get("source"), round(s.get("score", 0), 3)) for s in recorded]
    return got == want


async def rebuild(record: dict) -> list[dict]:
    import retrieval.decomposer as decomposer
    from retrieval.pipeline import retrieve_context

    async def recorded_sub_questions(_question):
        return record["sub_questions"]

    decomposer.decompose_query = recorded_sub_questions
    context = await retrieve_context(
        record["question"], use_decomposition=True, use_hyde=False, top_k=8
    )
    return context.chunks


async def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--run", type=Path, required=True)
    args = parser.parse_args()

    answers = read_jsonl(args.run / "answers.jsonl")
    grades = read_grades(args.run)
    types = {q["id"]: q["question_type"] for q in load_questions()}
    tally: Counter = Counter()
    by_type: Counter = Counter()
    flagged_correct, mismatched = [], []
    for qid, grade in grades.items():
        record = answers.get(qid)
        label = final_label(grade)
        if not record or record["error"] or not label:
            continue
        chunks = await rebuild(record)
        if not same_sources(chunks, record["sources"]):
            mismatched.append(qid)
            continue
        if REFUSAL in record["answer"].lower():
            tally[(label, "refusal")] += 1
            continue
        result = check_answer(record["question"], record["answer"], chunks)
        verdict = "flagged" if result.flagged else "passed"
        tally[(label, verdict)] += 1
        by_type[(types.get(qid, "unknown"), label, verdict)] += 1
        if result.flagged and label == "correct":
            flagged_correct.append(
                f"  {qid} ({result.reason}): {record['answer'][:110]!r}"
            )

    print(f"run: {args.run}")
    print(
        f"rebuilt contexts: {sum(tally.values())}; source mismatch skipped: {len(mismatched)}"
    )
    for label in ("correct", "incorrect"):
        f, p = tally[(label, "flagged")], tally[(label, "passed")]
        print(f"{label:9s} answers: flagged {f}/{f + p}")
    refusals = sum(n for (_, kind), n in tally.items() if kind == "refusal")
    print(f"refusals (nothing to check): {refusals}")
    print("correct answers flagged, by question type:")
    for qtype in sorted({t for t, _, _ in by_type}):
        f = by_type[(qtype, "correct", "flagged")]
        n = f + by_type[(qtype, "correct", "passed")]
        print(f"  {qtype:20s} {f}/{n}")
    print("correct answers the gate would refuse:")
    print("\n".join(flagged_correct) or "  none")
    if mismatched:
        print("mismatched:", " ".join(mismatched))


if __name__ == "__main__":
    asyncio.run(main())
