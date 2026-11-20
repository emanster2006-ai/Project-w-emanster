"""Retrieval-only benchmark: does the right evidence passage reach the top results?

Needs no LLM calls and no API keys, so it is free and deterministic. For every
FinanceBench question that has evidence, it runs the real hybrid search and reranker
and checks whether a returned chunk comes from that question's evidence text.

    export QDRANT_COLLECTION_NAME=financebench_eval   # a collection built by scripts/ingest.py
    python scripts/retrieval_benchmark.py              # all questions
    python scripts/retrieval_benchmark.py --stride 4   # every 4th question (faster)

Reports recall@20 (candidate pool, before reranking) and recall@5 (final context).
The corpus IS the evidence snippets, so a perfect system scores 100%; use the numbers
to compare retrieval changes against each other, not as a claim about full filings.
"""

import argparse
import asyncio
import logging
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from dotenv import load_dotenv

load_dotenv()
logging.basicConfig(level=logging.WARNING)


def _norm(text: str) -> str:
    return " ".join(text.split())


def belongs(chunk_text: str, evidence: str) -> bool:
    """True when the chunk was cut from this evidence text (ignoring whitespace)."""
    chunk, ev = _norm(chunk_text), _norm(evidence)
    return chunk in ev or ev[:120] in chunk or chunk[:120] in ev


def load_rows(stride: int) -> list[dict]:
    from datasets import load_dataset

    rows = []
    for row in load_dataset("PatronusAI/financebench", split="train"):
        evidence = " ".join(
            e.get("evidence_text", "")
            for e in (row.get("evidence") or [])
            if e.get("evidence_text")
        ).strip()
        if evidence:
            rows.append({"question": row["question"], "evidence": evidence})
    return rows[::stride]


async def run(stride: int, pool: int, top_k: int) -> None:
    from retrieval.hybrid import hybrid_search
    from retrieval.reranker import rerank

    rows = load_rows(stride)
    pool_hits = top_hits = 0
    misses = []
    for index, row in enumerate(rows):
        candidates = await hybrid_search(row["question"], top_k=pool)
        final = rerank(row["question"], candidates, top_k=top_k)
        in_pool = any(belongs(c["text"], row["evidence"]) for c in candidates)
        in_top = any(belongs(c["text"], row["evidence"]) for c in final)
        pool_hits += in_pool
        top_hits += in_top
        if not in_top:
            misses.append(index * stride)

    n = len(rows)
    print(
        f"collection: {os.getenv('QDRANT_COLLECTION_NAME', 'financebench')}  questions: {n}"
    )
    print(f"recall@{pool} (candidate pool): {pool_hits}/{n} = {pool_hits / n:.1%}")
    print(f"recall@{top_k} (after rerank):  {top_hits}/{n} = {top_hits / n:.1%}")
    print(f"missed question indexes: {misses}")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    parser.add_argument("--stride", type=int, default=1, help="use every Nth question")
    parser.add_argument(
        "--pool", type=int, default=20, help="candidates from hybrid search"
    )
    parser.add_argument(
        "--top-k", type=int, default=5, help="chunks kept after reranking"
    )
    args = parser.parse_args()
    asyncio.run(run(args.stride, args.pool, args.top_k))
