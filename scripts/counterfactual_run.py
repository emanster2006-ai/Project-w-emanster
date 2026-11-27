"""Run the counterfactual grounding benchmark on frozen contexts.

For every case in the manifest it builds four arms from the captured context
(evaluation/counterfactual/edits.py), sends each through the real generator with
retrieval held fixed, and grades the answers deterministically
(evaluation/counterfactual/grade.py). A case passes only if all four arms pass.

  python scripts/counterfactual_run.py --check-fixtures            # no model calls
  python scripts/counterfactual_run.py --run <dir> --split dev --systems baseline
  python scripts/counterfactual_run.py --run <dir> --split dev --summary

Outputs are appended to <dir>/outputs.jsonl keyed by (case, arm, system) and never
rewritten; rerunning skips finished arms, so an interrupted run resumes. Hand-review
labels go in <dir>/reviews.jsonl as {"id", "arm", "system", "label", "note"} and
override the automatic grade. Waits out per-minute rate limits; stops at daily ones.
"""

import argparse
import asyncio
import json
import os
import sys
import time
from collections import Counter
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "scripts"))

from answer_accuracy import (  # noqa: E402
    DailyLimit,
    _retry_after,
    _wait_or_stop,
    wilson,
)
from evaluation.counterfactual.edits import (  # noqa: E402
    ARMS,
    FixtureError,
    build_arm,
    context_sha,
)
from evaluation.counterfactual.grade import case_passes, grade_arm  # noqa: E402

MANIFEST = ROOT / "evaluation/counterfactual/manifest.json"
CONTEXTS = ROOT / "evaluation/counterfactual/contexts"


# ── Systems under test ──────────────────────────────────────────────────────────


async def baseline(question: str, chunks: list[dict]):
    from generation.llm import generate_response

    return await generate_response(question, chunks)


async def candidate(question: str, chunks: list[dict]):
    """Baseline plus one rule against substituting or deriving a missing line item,
    chosen from the dev failures (generation/prompts/rag_system_candidate.j2)."""
    from generation.llm import generate_response

    return await generate_response(
        question, chunks, system_template="rag_system_candidate.j2"
    )


SYSTEMS = {"baseline": baseline, "candidate": candidate}


# ── Data ────────────────────────────────────────────────────────────────────────


def load_manifest(path: Path = MANIFEST) -> dict:
    return json.loads(path.read_text())


def load_context(case_id: str, contexts: Path | None = None) -> dict:
    return json.loads(((contexts or CONTEXTS) / f"{case_id}.json").read_text())


def arm_chunks(case: dict, ctx: dict, arm: str) -> list[dict]:
    """Chunks for one arm: captured metadata, edited text, same order."""
    texts = build_arm(case, [c["text"] for c in ctx["chunks"]], arm)
    return [
        {"text": t, "metadata": c["metadata"]} for t, c in zip(texts, ctx["chunks"])
    ]


def read_keyed(path: Path) -> dict[tuple, dict]:
    if not path.exists():
        return {}
    out = {}
    for line in path.read_text().splitlines():
        if line.strip():
            r = json.loads(line)
            out[(r["id"], r["arm"], r["system"])] = r
    return out


# ── Rate limits ─────────────────────────────────────────────────────────────────


def _provider_error(exc: BaseException) -> BaseException:
    """Unwrap instructor/tenacity wrappers to the provider's own exception."""
    seen = set()
    while id(exc) not in seen:
        seen.add(id(exc))
        last = getattr(exc, "last_attempt", None)
        if last is not None and last.failed:
            exc = last.exception()
            continue
        nxt = exc.__cause__ or exc.__context__
        if nxt is None:
            break
        exc = nxt
    return exc


def _is_rate_limit(exc: BaseException) -> bool:
    return getattr(exc, "status_code", None) == 429 or "rate_limit" in str(exc)


# ── Running ─────────────────────────────────────────────────────────────────────


class _LimitReached(Exception):
    pass


async def run_one(system: str, case: dict, ctx: dict, arm: str) -> dict:
    chunks = arm_chunks(case, ctx, arm)
    record = {
        "id": case["id"],
        "arm": arm,
        "system": system,
        "context_sha256": context_sha([c["text"] for c in chunks]),
        "started": datetime.now(timezone.utc).isoformat(timespec="seconds"),
    }
    for _ in range(20):
        t0 = time.time()
        try:
            response, usage = await SYSTEMS[system](ctx["question_sent"], chunks)
        except Exception as exc:
            root = _provider_error(exc)
            if _is_rate_limit(root):
                headers = getattr(getattr(root, "response", None), "headers", {}) or {}
                _wait_or_stop(
                    _retry_after(str(root), headers.get("retry-after")), "llm"
                )
                continue
            return {
                **record,
                "answer": None,
                "error": f"{type(root).__name__}: {root}"[:300],
            }
        return {
            **record,
            "answer": response.answer,
            "confidence": response.confidence,
            "error": None,
            "latency_s": round(time.time() - t0, 2),
            "attempts": usage.attempts,
            "prompt_tokens": usage.prompt_tokens,
            "completion_tokens": usage.completion_tokens,
        }
    return {**record, "answer": None, "error": "gave up after repeated rate limits"}


async def run(args, manifest: dict) -> None:
    out = Path(args.run)
    out.mkdir(parents=True, exist_ok=True)
    meta = out / "run.json"
    if not meta.exists():
        meta.write_text(
            json.dumps(
                {
                    "started": datetime.now(timezone.utc).isoformat(timespec="seconds"),
                    "manifest_version": manifest.get("version"),
                    "split": args.split,
                    "systems": args.systems,
                    "llm_model": os.getenv("LLM_MODEL", "openai/gpt-oss-120b"),
                    "llm_provider": os.getenv("LLM_PROVIDER", "groq"),
                    "llm_base_url": os.getenv("OPENAI_BASE_URL") or None,
                    "llm_reasoning_effort": os.getenv("LLM_REASONING_EFFORT", "medium"),
                    "git_rev": os.getenv("GIT_REV"),
                },
                indent=1,
            )
            + "\n"
        )
    path = out / "outputs.jsonl"
    done = {k for k, r in read_keyed(path).items() if not r["error"]}
    spent = sum(
        (r.get("prompt_tokens") or 0) + (r.get("completion_tokens") or 0)
        for r in read_keyed(path).values()
    )
    cases = [c for c in manifest["cases"] if c["split"] == args.split]
    calls = 0
    try:
        for i, case in enumerate(cases):
            ctx = load_context(case["id"])
            for arm in ARMS:
                # Rotate system order per case so neither always runs first.
                rotated = (
                    args.systems[i % len(args.systems) :]
                    + args.systems[: i % len(args.systems)]
                )
                for system in rotated:
                    if (case["id"], arm, system) in done:
                        continue
                    if args.limit is not None and calls >= args.limit:
                        raise _LimitReached
                    if args.token_budget and spent >= args.token_budget:
                        print(f"\nStopped: token budget {args.token_budget:,} reached.")
                        return
                    rec = await run_one(system, case, ctx, arm)
                    calls += 1
                    spent += (rec.get("prompt_tokens") or 0) + (
                        rec.get("completion_tokens") or 0
                    )
                    with path.open("a") as f:
                        f.write(json.dumps(rec) + "\n")
                    print(
                        f"{case['id']} {arm} {system}: "
                        f"{rec['error'] or (rec['answer'] or '')[:90]!r}",
                        flush=True,
                    )
                    time.sleep(args.pause)
    except DailyLimit as exc:
        print(f"\nStopped: {exc}. Rerun the same command later to continue.")
    except _LimitReached:
        print(f"\nStopped after --limit {args.limit} calls.")


# ── Summary ─────────────────────────────────────────────────────────────────────


def outcomes_for(manifest: dict, run: Path, split: str) -> dict:
    """{system: {case_id: {arm: outcome}}}, hand-review labels taking precedence."""
    outputs = read_keyed(run / "outputs.jsonl")
    reviews = read_keyed(run / "reviews.jsonl")
    cases = {c["id"]: c for c in manifest["cases"] if c["split"] == split}
    table: dict = {}
    for (cid, arm, system), rec in outputs.items():
        if cid not in cases:
            continue
        case = cases[cid]
        label = grade_arm(
            arm,
            rec["answer"],
            case["unit"],
            case["expected"].get(arm),
            case.get("trap", {}).get(arm),
            rec["error"],
        )
        review = reviews.get((cid, arm, system))
        table.setdefault(system, {}).setdefault(cid, {})[arm] = (
            review["label"] if review else label
        )
    return table


def summarize(manifest: dict, run: Path, split: str) -> dict:
    n_cases = sum(1 for c in manifest["cases"] if c["split"] == split)
    table = outcomes_for(manifest, run, split)
    outputs = read_keyed(run / "outputs.jsonl")
    result = {"split": split, "cases": n_cases, "systems": {}}
    for system, per_case in table.items():
        passes = sum(case_passes(o) for o in per_case.values())
        lo, hi = wilson(passes, n_cases)
        recs = [r for (_, _, s), r in outputs.items() if s == system]
        result["systems"][system] = {
            "complete_passes": passes,
            "pass_rate_ci95": [lo, hi],
            "incomplete_cases": sum(
                1 for o in per_case.values() if len(o) < 4 or "error" in o.values()
            )
            + (n_cases - len(per_case)),
            "per_arm": {
                arm: dict(Counter(o.get(arm, "missing") for o in per_case.values()))
                for arm in ARMS
            },
            "provider_attempts": sum(r.get("attempts") or 0 for r in recs),
            "prompt_tokens": sum(r.get("prompt_tokens") or 0 for r in recs),
            "completion_tokens": sum(r.get("completion_tokens") or 0 for r in recs),
        }
    systems = list(table)
    if len(systems) == 2:
        a, b = systems
        wins = losses = same = 0
        for cid in set(table[a]) | set(table[b]):
            pa = case_passes(table[a].get(cid, {}))
            pb = case_passes(table[b].get(cid, {}))
            wins += pb and not pa
            losses += pa and not pb
            same += pa == pb
        result["paired"] = {
            "compare": f"{b} vs {a}",
            "wins": wins,
            "losses": losses,
            "unchanged": same,
        }
    return result


def check_fixtures(manifest: dict) -> int:
    """Build every arm of every case offline; report fixtures that are not clean."""
    bad = 0
    for case in manifest["cases"]:
        try:
            ctx = load_context(case["id"])
            for arm in ARMS:
                arm_chunks(case, ctx, arm)
            print(f"ok    {case['id']} ({case['split']})")
        except (FixtureError, FileNotFoundError, KeyError) as exc:
            bad += 1
            print(f"FAIL  {case['id']}: {exc}")
    return bad


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    parser.add_argument("--run")
    parser.add_argument("--split", choices=["dev", "reserved"], default="dev")
    parser.add_argument("--systems", nargs="+", default=["baseline"])
    parser.add_argument("--manifest", default=str(MANIFEST))
    parser.add_argument("--limit", type=int, help="stop after this many model calls")
    parser.add_argument("--pause", type=float, default=0.0)
    parser.add_argument(
        "--token-budget",
        type=int,
        default=0,
        help="stop once this run's metered tokens reach this total (0: no cap)",
    )
    parser.add_argument("--summary", action="store_true")
    parser.add_argument("--check-fixtures", action="store_true")
    args = parser.parse_args()

    manifest = load_manifest(Path(args.manifest))
    if args.check_fixtures:
        sys.exit(1 if check_fixtures(manifest) else 0)
    if not args.run:
        parser.error("--run is required")
    unknown = set(args.systems) - set(SYSTEMS)
    if unknown:
        parser.error(f"unknown systems: {sorted(unknown)}")
    if args.summary:
        print(json.dumps(summarize(manifest, Path(args.run), args.split), indent=1))
        return
    if check_fixtures(manifest):
        sys.exit("Fix the manifest before running: some arms are not clean.")
    asyncio.run(run(args, manifest))
    print(json.dumps(summarize(manifest, Path(args.run), args.split), indent=1))


if __name__ == "__main__":
    main()
