"""End-to-end answer check against a running API (uses the LLM, so it costs tokens).

For each FinanceBench question it asks the API and checks whether the answer
contains a distinctive figure from the reference answer. This is a coarse,
conservative check (it does not judge wording), meant to track change over time
rather than to certify accuracy. Questions whose reference has no figure are skipped.

Reports: figure match rate, abstention rate, and how often a source passage
contained the figure (separates retrieval misses from generation misses).

Usage: python scripts/answer_eval.py --limit 30 --top-k 8 --out results.json
Free-tier note: pass --pause to stay under a tokens-per-minute limit.
"""

import argparse
import json
import re
import time
import urllib.request


def _canon(num: str) -> str:
    """Canonical form so '1,577', '1577.00' and '$1577' compare equal."""
    value = float(num.replace(",", ""))
    return str(int(value)) if value == int(value) else f"{value:g}"


def figures(text: str) -> set[str]:
    """Distinctive numbers (3+ digits/characters after canonicalising) found in text."""
    found = re.findall(r"\d[\d,]*\.?\d*", text)
    out = set()
    for f in found:
        f = f.rstrip(".,")
        if f and len(f.replace(",", "").replace(".", "")) >= 2:
            out.add(_canon(f))
    # Drop plain years (FY2018 etc.): they appear in questions and answers regardless of correctness.
    return {
        f
        for f in out
        if (len(f) >= 3 or "." in f) and not (f.isdigit() and 1990 <= int(f) <= 2035)
    }


def close(want: set[str], got: set[str], rel: float = 0.01) -> bool:
    """True if any wanted figure appears in got, allowing 1% rounding (24.26 vs 24.3)."""
    for w in want:
        for g in got:
            fw, fg = float(w), float(g)
            if fw == fg or (fw and abs(fw - fg) / abs(fw) <= rel):
                return True
    return False


def load_rows() -> list[dict]:
    from datasets import load_dataset

    rows = []
    for row in load_dataset("PatronusAI/financebench", split="train"):
        answer = row.get("answer") or ""
        ref = figures(answer)
        # Short numeric answers only: long qualitative ones cannot be scored by figure matching.
        if ref and len(answer) <= 150 and row.get("evidence"):
            rows.append({"question": row["question"], "figures": sorted(ref)})
    return rows


def ask(url: str, question: str, top_k: int, decompose: bool) -> dict:
    body = json.dumps(
        {
            "question": question,
            "use_hyde": False,
            "use_decomposition": decompose,
            "top_k": top_k,
        }
    ).encode()
    req = urllib.request.Request(url, body, {"Content-Type": "application/json"})
    try:
        return json.load(urllib.request.urlopen(req, timeout=180))
    except Exception as exc:  # keep failures as data, not crashes
        return {"error": str(exc)[:200], "answer": "", "sources": []}


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    parser.add_argument("--url", default="http://localhost:8000/api/v1/query")
    parser.add_argument("--limit", type=int, default=30)
    parser.add_argument("--stride", type=int, default=1)
    parser.add_argument("--top-k", type=int, default=8)
    parser.add_argument("--decompose", action="store_true")
    parser.add_argument(
        "--pause", type=float, default=0.0, help="seconds between questions"
    )
    parser.add_argument("--out", default="answer_eval.json")
    args = parser.parse_args()

    rows = load_rows()[:: args.stride][: args.limit]
    results = []
    streak = 0
    for i, row in enumerate(rows, 1):
        resp = ask(args.url, row["question"], args.top_k, args.decompose)
        streak = streak + 1 if "429" in str(resp.get("error", "")) else 0
        if streak >= 3:
            print(
                "Stopping: 3 rate-limit errors in a row (provider quota). Rerun later."
            )
            break
        answer = resp.get("answer", "")
        answer_figs = figures(answer)
        source_text = " ".join(s.get("text", "") for s in resp.get("sources", []))
        source_figs = figures(source_text)
        want = set(row["figures"])
        results.append(
            {
                "question": row["question"],
                "error": resp.get("error"),
                "want": sorted(want),
                "matched": close(want, answer_figs),
                "abstained": "insufficient context" in answer.lower(),
                "figure_in_sources": close(want, source_figs, rel=0.0),
                "answer": answer[:300],
            }
        )
        print(
            f"[{i}/{len(rows)}] matched={results[-1]['matched']} {row['question'][:70]}"
        )
        json.dump(results, open(args.out, "w"), indent=1)
        time.sleep(args.pause)

    n = len(results)
    errors = sum(1 for r in results if r["error"])
    scored = [r for r in results if not r["error"]]
    m = len(scored) or 1
    print(f"\nquestions: {n} (errors, excluded: {errors})")
    print(f"figure matched in answer: {sum(r['matched'] for r in scored)}/{m}")
    print(f"abstained:                {sum(r['abstained'] for r in scored)}/{m}")
    print(
        f"figure in retrieved text: {sum(r['figure_in_sources'] for r in scored)}/{m}"
    )


if __name__ == "__main__":
    main()
