"""
CrossEncoder reranking — significantly improves retrieval precision.
Takes top_k=20 candidates from hybrid search, scores each against query,
returns top_k=5 final chunks for LLM context.
"""

from sentence_transformers import CrossEncoder
from retrieval.context import contextualize
from retrieval.year_boost import apply_year_bonus
import logging
import os

logger = logging.getLogger(__name__)

MODEL_NAME = os.getenv("RERANKER_MODEL", "cross-encoder/ms-marco-MiniLM-L-6-v2")
_reranker = None


def get_reranker() -> CrossEncoder:
    global _reranker
    if _reranker is None:
        _reranker = CrossEncoder(MODEL_NAME)
        logger.info(f"Loaded reranker: {MODEL_NAME}")
    return _reranker


def rerank(query: str, chunks: list[dict], top_k: int = 5) -> list[dict]:
    """
    Score each (query, chunk) pair with cross-encoder.
    Cross-encoder sees the full query + chunk together — much more accurate
    than bi-encoder similarity used in retrieval step.
    """
    if not chunks:
        return []

    reranker = get_reranker()
    pairs = [
        (query, contextualize(chunk["text"], chunk.get("metadata"))) for chunk in chunks
    ]
    scores = apply_year_bonus(query, chunks, list(reranker.predict(pairs)))

    scored = sorted(
        zip(scores, chunks),
        key=lambda x: x[0],
        reverse=True,
    )

    result = []
    for score, chunk in scored[:top_k]:
        result.append({**chunk, "score": float(score)})

    logger.info(f"Reranked {len(chunks)} → top {len(result)} chunks")
    return result
