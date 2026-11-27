"""Export recorded counterfactual runs for the static replay page (no model calls).

  python scripts/counterfactual_export.py \\
      --runs evaluation/counterfactual/runs/dev-baseline evaluation/counterfactual/runs/reserved \\
      --ids financebench_id_03531 author_07661_1 financebench_id_04980 \\
      --out frontend/lib/replay-cases.json

For each case it picks the captured chunk that holds the asked-for figure, computes a
word-level diff of that chunk for every arm, and attaches each system's recorded answer
and its grade. Every edited excerpt is a synthetic benchmark fixture and is labelled so
on the page.
"""

import argparse
import difflib
import json
import re
import sys
from datetime import datetime, timezone
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
    summarize,
)
from evaluation.counterfactual.edits import ARMS, number_pattern  # noqa: E402

BEFORE, AFTER = 250, 900  # characters of context kept around the asked-for figure
ARM_LABELS = {
    "A": "Original filing",
    "B": "Target figure changed",
    "C": "Another year changed",
    "D": "Evidence removed",
}
SCALE_WORDS = {"millions": "million", "billions": "billion", "units": ""}


def provider_name(meta: dict) -> str:
    url = (meta.get("llm_base_url") or "").lower()
    for host, name in (
        ("cerebras", "Cerebras"),
        ("groq", "Groq"),
        ("openai.com", "OpenAI"),
    ):
        if host in url:
            return name
    return "Groq" if meta.get("llm_provider", "groq") == "groq" else url or "unknown"


def money(value: float, unit: str) -> str:
    text = f"{value:,.3f}".rstrip("0").rstrip(".")
    word = SCALE_WORDS.get(unit, unit)
    return f"${text} {word}".strip()


def segments(before: str, after: str) -> list[dict]:
    """Word-level diff as [{kind: same|added|removed, text}] keeping whitespace."""
    a, b = re.split(r"(\s+)", before), re.split(r"(\s+)", after)
    out: list[dict] = []

    def push(kind: str, text: str) -> None:
        if not text:
            return
        if out and out[-1]["kind"] == kind:
            out[-1]["text"] += text
        else:
            out.append({"kind": kind, "text": text})

    for op, i1, i2, j1, j2 in difflib.SequenceMatcher(
        None, a, b, autojunk=False
    ).get_opcodes():
        if op == "equal":
            push("same", "".join(a[i1:i2]))
        else:
            push("removed", "".join(a[i1:i2]))
            push("added", "".join(b[j1:j2]))
    return out


def trim(segs: list[dict], anchor: int) -> list[dict]:
    """Keep BEFORE/AFTER characters around offset `anchor`, without blank lines."""
    lo, hi, pos, out = anchor - BEFORE, anchor + AFTER, 0, []
    for s in segs:
        start, end = pos, pos + len(s["text"])
        if s["kind"] == "added":
            end = start  # added text takes no room in the original
        if end >= lo and start <= hi or (s["kind"] == "added" and lo <= start <= hi):
            text = s["text"]
            if s["kind"] == "same":
                text = text[max(0, lo - start) : max(0, hi - start)]
            if text:
                out.append({"kind": s["kind"], "text": text})
        if s["kind"] != "added":
            pos = end
    for seg in out:  # PDF extraction leaves runs of whitespace-only lines
        seg["text"] = re.sub(r"\n[ \t]*(?=\n)", "", seg["text"])
    if out and out[0]["kind"] == "same":
        out[0]["text"] = "…" + out[0]["text"].lstrip()
    if out and out[-1]["kind"] == "same":
        out[-1]["text"] = out[-1]["text"].rstrip() + "…"
    return out


def export_case(case: dict, ctx: dict, outputs: dict, outcomes: dict) -> dict:
    target = case["arms"]["B"]["gone"][0]
    pattern = number_pattern(target)
    rank = next(i for i, c in enumerate(ctx["chunks"]) if pattern.search(c["text"]))
    original = ctx["chunks"][rank]["text"]
    anchor = pattern.search(original).start()
    unit = case["unit"]
    figures = {
        "original": money(case["expected"]["A"], unit),
        "edited": money(case["expected"]["B"], unit),
        "other_year": money(case["trap"]["C"], unit),
    }
    arms = {}
    for arm in ARMS:
        edited = arm_chunks(case, ctx, arm)[rank]["text"]
        expected = (
            "Say the evidence is insufficient"
            if arm == "D"
            else money(case["expected"][arm], unit)
        )
        options = [figures["original"], figures["edited"], "Say it can't answer"]
        if arm == "C":
            options = [
                figures["original"],
                figures["other_year"],
                "Say it can't answer",
            ]
        arms[arm] = {
            "label": ARM_LABELS[arm],
            "expected": expected,
            "correct_option": (
                2 if arm == "D" else options.index(money(case["expected"][arm], unit))
            ),
            "options": options,
            "segments": trim(segments(original, edited), anchor),
            "answers": {
                system: {
                    "text": outputs[(case["id"], arm, system)]["answer"],
                    "grade": outcomes[system][case["id"]][arm],
                }
                for system in outcomes
                if (case["id"], arm, system) in outputs
            },
        }
    return {
        "id": case["id"],
        "source": case.get("source", "financebench"),
        "split": case["split"],
        "doc_name": case["doc_name"],
        "chunk_source": ctx["chunks"][rank]["metadata"].get("source"),
        "question": ctx["question"],
        "metric": case["metric"],
        "audit": case["audit"],
        "arms": arms,
    }


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    parser.add_argument("--runs", nargs="+", required=True)
    parser.add_argument("--ids", nargs="+", required=True)
    parser.add_argument("--out", default=str(ROOT / "frontend/lib/replay-cases.json"))
    args = parser.parse_args()

    manifest = load_manifest()
    cases = {c["id"]: c for c in manifest["cases"]}
    exported, summaries, meta = [], [], None
    for run in map(Path, args.runs):
        meta = meta or json.loads((run / "run.json").read_text())
        outputs = read_keyed(run / "outputs.jsonl")
        split = json.loads((run / "run.json").read_text())["split"]
        summaries.append(summarize(manifest, run, split))
        outcomes = outcomes_for(manifest, run, split)
        for cid in args.ids:
            if cid in cases and cases[cid]["split"] == split:
                exported.append(
                    export_case(cases[cid], load_context(cid), outputs, outcomes)
                )
    order = {cid: i for i, cid in enumerate(args.ids)}
    exported.sort(key=lambda c: order[c["id"]])
    data = {
        "generated_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "model": meta["llm_model"],
        "provider": provider_name(meta),
        "reasoning_effort": meta.get("llm_reasoning_effort"),
        "run_started": meta["started"],
        "summaries": summaries,
        "cases": exported,
    }
    Path(args.out).write_text(json.dumps(data, indent=1, ensure_ascii=False) + "\n")
    print(f"wrote {len(exported)} cases to {args.out}")


if __name__ == "__main__":
    main()
