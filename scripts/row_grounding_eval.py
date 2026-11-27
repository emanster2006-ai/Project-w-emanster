"""Compare the row-aware grounding check with the digit-level one on recorded answers.

Uses the counterfactual benchmark's recorded outputs and frozen contexts, so it makes
no model calls. For every graded answer it asks both checks whether to flag it:

- caught: failing evidence-removed answers (arm D, not correct) that a check flags
- false flags: correct answers on arms A-C that a check flags

  python scripts/row_grounding_eval.py
"""

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "scripts"))

from counterfactual_run import (  # noqa: E402
    arm_chunks,
    load_context,
    load_manifest,
    outcomes_for,
    read_keyed,
)
from security.grounding import ungrounded_numbers  # noqa: E402
from security.row_grounding import check_answer  # noqa: E402

RUNS = {
    "dev": ROOT / "evaluation/counterfactual/runs/dev-baseline",
    "reserved": ROOT / "evaluation/counterfactual/runs/reserved",
}


def main() -> None:
    manifest = load_manifest()
    cases = {c["id"]: c for c in manifest["cases"]}
    tally = {
        "digit": {"caught": 0, "false": 0},
        "row": {"caught": 0, "false": 0},
    }
    failing = correct = 0
    misses = []
    for split, run in RUNS.items():
        outputs = read_keyed(run / "outputs.jsonl")
        for system, per_case in outcomes_for(manifest, run, split).items():
            for cid, arms in per_case.items():
                ctx = load_context(cid)
                for arm, outcome in arms.items():
                    answer = outputs[(cid, arm, system)]["answer"] or ""
                    chunks = arm_chunks(cases[cid], ctx, arm)
                    digit = bool(ungrounded_numbers(answer, chunks))
                    row = check_answer(ctx["question_sent"], answer, chunks)
                    if arm == "D" and outcome != "correct":
                        failing += 1
                        tally["digit"]["caught"] += digit
                        tally["row"]["caught"] += row.flagged
                        if not row.flagged:
                            misses.append(f"missed  {cid} {system}: {answer[:90]!r}")
                    elif arm != "D" and outcome == "correct":
                        correct += 1
                        tally["digit"]["false"] += digit
                        tally["row"]["false"] += row.flagged
                        if row.flagged:
                            misses.append(
                                f"flagged {cid} {arm} {system} ({row.reason}): "
                                f"{answer[:90]!r}"
                            )
    for name, label in (("digit", "digit-level (grounding.py)"), ("row", "row-aware")):
        t = tally[name]
        print(
            f"{label:28s} caught {t['caught']}/{failing} failing arm-D answers; "
            f"flagged {t['false']}/{correct} correct arm A-C answers"
        )
    print("\n".join(misses))


if __name__ == "__main__":
    main()
