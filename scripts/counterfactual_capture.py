"""Capture the exact ordered context the generator sees for FinanceBench questions.

The counterfactual replay (docs/COUNTERFACTUAL.md) edits these saved contexts, so
retrieval is frozen: every arm of a question sees the same chunks in the same order,
and decomposition's run-to-run variation cannot leak into the comparison.

  python scripts/counterfactual_capture.py --ids financebench_id_03029 ... \\
      --out evaluation/counterfactual/contexts
  python scripts/counterfactual_capture.py --check --ids financebench_id_03029 \\
      --api http://localhost:8000/api/v1/query

Capture uses the same retrieve_context() and PII masking as the /query route, with
the web UI's options (decomposition on, HyDE off, top_k 8). Existing captures are
never overwritten. --check compares a capture made with decomposition off (which
is deterministic) against the live API's returned sources, chunk by chunk.
"""

import argparse
import asyncio
import hashlib
import json
import os
import subprocess
import sys
import urllib.request
from datetime import datetime, timezone
from pathlib import Path

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

UI_OPTIONS = {"use_decomposition": True, "use_hyde": False, "top_k": 8}
GENERATION_MAX_TOKENS = 1000  # mirrors generation/llm.py; recorded for provenance
METADATA_KEYS = ("company", "year", "source", "section", "doc_name", "filing_type")


def sha256(text: str) -> str:
    return hashlib.sha256(text.encode()).hexdigest()


AUTHOR_QUESTIONS = Path(__file__).resolve().parent.parent / (
    "evaluation/counterfactual/author_questions.json"
)


def load_question(qid: str) -> dict:
    """A FinanceBench row, or an author-written question (ids starting 'author_')."""
    if qid.startswith("author_"):
        for row in json.loads(AUTHOR_QUESTIONS.read_text())["questions"]:
            if row["id"] == qid:
                return {**row, "source": "author"}
        raise KeyError(qid)
    from datasets import load_dataset

    for row in load_dataset("PatronusAI/financebench", split="train"):
        if row["financebench_id"] == qid:
            return row
    raise KeyError(qid)


def _git_rev() -> str | None:
    try:
        return subprocess.check_output(
            ["git", "rev-parse", "--short", "HEAD"],
            text=True,
            stderr=subprocess.DEVNULL,
        ).strip()
    except Exception:
        return os.getenv("GIT_REV")


async def _retrieve_waiting(question: str, options: dict):
    """retrieve_context, waiting out provider rate limits (decomposition calls the LLM)."""
    from counterfactual_run import _is_rate_limit, _provider_error
    from answer_accuracy import _retry_after, _wait_or_stop
    from retrieval.pipeline import retrieve_context

    while True:
        try:
            return await retrieve_context(question, **options)
        except Exception as exc:
            root = _provider_error(exc)
            if not _is_rate_limit(root):
                raise
            headers = getattr(getattr(root, "response", None), "headers", {}) or {}
            _wait_or_stop(
                _retry_after(str(root), headers.get("retry-after")), "capture"
            )


async def capture(question: str, options: dict) -> dict:
    """Mask PII like the API middleware, then run the shared retrieval pipeline."""
    from generation.llm import render_messages
    from security.pii_handler import anonymize

    sanitized, mapping = anonymize(question)
    ctx = await _retrieve_waiting(sanitized, options)
    messages = render_messages(sanitized, ctx.chunks)
    return {
        "question_sent": sanitized,
        "pii_masked": bool(mapping),
        "sub_questions": ctx.sub_questions,
        "chunks": [
            {
                "rank": i,
                "text": c["text"],
                "sha256": sha256(c["text"]),
                "score": c.get("score"),
                "metadata": {
                    k: c["metadata"].get(k) for k in METADATA_KEYS if k in c["metadata"]
                },
            }
            for i, c in enumerate(ctx.chunks)
        ],
        "messages_sha256": sha256(json.dumps(messages, sort_keys=True)),
    }


def api_sources(url: str, question: str) -> list[str]:
    body = json.dumps(
        {
            "question": question,
            "use_decomposition": False,
            "use_hyde": False,
            "top_k": 8,
        }
    ).encode()
    req = urllib.request.Request(url, body, {"Content-Type": "application/json"})
    with urllib.request.urlopen(req, timeout=300) as resp:
        return [s["text"] for s in json.load(resp)["sources"]]


async def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    parser.add_argument("--ids", nargs="+", required=True)
    parser.add_argument("--out", default="evaluation/counterfactual/contexts")
    parser.add_argument("--check", action="store_true")
    parser.add_argument("--api", default="http://localhost:8000/api/v1/query")
    args = parser.parse_args()

    if args.check:
        failures = 0
        for qid in args.ids:
            q = load_question(qid)["question"]
            options = {**UI_OPTIONS, "use_decomposition": False}
            mine = [c["text"] for c in (await capture(q, options))["chunks"]]
            theirs = api_sources(args.api, q)
            same = mine == theirs
            failures += not same
            print(f"{qid}: {'identical' if same else 'DIFFERENT'} ({len(mine)} chunks)")
            if not same:
                for i, (a, b) in enumerate(zip(mine, theirs)):
                    if a != b:
                        print(f"  first difference at rank {i}")
                        break
        sys.exit(1 if failures else 0)

    out = Path(args.out)
    out.mkdir(parents=True, exist_ok=True)
    for qid in args.ids:
        path = out / f"{qid}.json"
        if path.exists():
            print(f"{qid}: already captured, kept")
            continue
        row = load_question(qid)
        record = {
            "id": qid,
            "doc_name": row.get("doc_name"),
            "source": row.get("source", "financebench"),
            "question": row["question"],
            "captured_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
            "git_rev": _git_rev(),
            "options": UI_OPTIONS,
            "llm_model": os.getenv("LLM_MODEL", "openai/gpt-oss-120b"),
            "llm_reasoning_effort": os.getenv("LLM_REASONING_EFFORT", "medium"),
            "max_tokens": GENERATION_MAX_TOKENS,
            "collection": os.getenv("QDRANT_COLLECTION_NAME"),
            **await capture(row["question"], UI_OPTIONS),
        }
        path.write_text(json.dumps(record, indent=1) + "\n")
        print(f"{qid}: {len(record['chunks'])} chunks → {path}")


if __name__ == "__main__":
    asyncio.run(main())
