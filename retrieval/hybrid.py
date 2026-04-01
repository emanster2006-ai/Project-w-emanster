"""
Hybrid retrieval: dense vectors + BM25 sparse search, fused via RRF.
This is what production RAG systems actually use.
Reciprocal Rank Fusion (RRF) formula: score = sum(1 / (k + rank_i)) where k=60
"""

from retrieval.vectorstore import dense_search, get_vectorstore
from ingestion.embedder import embed_texts
from rank_bm25 import BM25Okapi
import numpy as np
import os
import logging

logger = logging.getLogger(__name__)

RRF_K = 60  # standard constant — higher = less emphasis on top ranks


def reciprocal_rank_fusion(
    ranked_lists: list[list[dict]], k: int = RRF_K
) -> list[dict]:
    """
    Merge multiple ranked lists into a single ranking via RRF.
    Score = sum(1 / (k + rank)) across all lists.
    """
    scores: dict[str, float] = {}
    items: dict[str, dict] = {}

    for ranked_list in ranked_lists:
        for rank, item in enumerate(ranked_list):
            key = item["text"][:100]  # dedup key
            scores[key] = scores.get(key, 0.0) + (1.0 / (k + rank + 1))
            items[key] = item

    sorted_keys = sorted(scores, key=lambda k: scores[k], reverse=True)
    return [
        {**items[key], "score": scores[key]}
        for key in sorted_keys
    ]


# Module-level BM25 index (rebuilt on first call, then cached)
_bm25_index = None
_bm25_corpus = None


def _get_bm25_index():
    """
    Build BM25 index from Qdrant collection.
    In production, this would be rebuilt incrementally.
    """
    global _bm25_index, _bm25_corpus
    if _bm25_index is None:
        client = get_vectorstore()
        # Scroll all texts from Qdrant
        records, _ = client.scroll(
            collection_name=os.getenv("QDRANT_COLLECTION_NAME", "financebench"),
            limit=10000,
            with_payload=True,
            with_vectors=False,
        )
        _bm25_corpus = [
            {"text": r.payload.get("text", ""), "metadata": r.payload}
            for r in records
        ]
        tokenized = [doc["text"].lower().split() for doc in _bm25_corpus]
        _bm25_index = BM25Okapi(tokenized) if tokenized else None
        logger.info(f"BM25 index built with {len(_bm25_corpus)} documents")
    return _bm25_index, _bm25_corpus


async def hybrid_search(query: str, top_k: int = 20) -> list[dict]:
    """
    1. Dense retrieval (semantic similarity)
    2. BM25 retrieval (keyword/lexical)
    3. RRF fusion of both ranked lists
    """
    # Dense retrieval
    query_vec = embed_texts([query], normalize=True)[0]
    dense_results = dense_search(query_vec, top_k=top_k)

    # BM25 retrieval
    bm25, corpus = _get_bm25_index()
    if bm25 is not None and corpus:
        tokenized_query = query.lower().split()
        bm25_scores = bm25.get_scores(tokenized_query)
        top_bm25_indices = np.argsort(bm25_scores)[::-1][:top_k]
        bm25_results = [
            {**corpus[i], "score": float(bm25_scores[i])}
            for i in top_bm25_indices
        ]
    else:
        bm25_results = []

    # RRF fusion
    fused = reciprocal_rank_fusion([dense_results, bm25_results])
    logger.info(
        f"Hybrid search: {len(dense_results)} dense + {len(bm25_results)} BM25 → {len(fused)} fused"
    )
    return fused[:top_k]
