"""
Semantic cache using Redis.
If an incoming query has cosine similarity > threshold with a cached query,
return the cached response without hitting the LLM.
"""

import redis.asyncio as aioredis
import numpy as np
import json
import os
import hashlib
import logging

from api.middleware.cache_key import is_reusable, options_key, signature

logger = logging.getLogger(__name__)

REDIS_URL = os.getenv("REDIS_URL", "redis://localhost:6379")
THRESHOLD = float(os.getenv("SEMANTIC_CACHE_THRESHOLD", 0.92))
TTL = int(os.getenv("CACHE_TTL_SECONDS", 3600))

_redis_client = None


async def get_redis():
    global _redis_client
    if _redis_client is None:
        _redis_client = aioredis.from_url(REDIS_URL, decode_responses=False)
    return _redis_client


def _embed_query(query: str) -> np.ndarray:
    from ingestion.embedder import get_embedder

    embedder = get_embedder()
    vec = embedder.encode([query], normalize_embeddings=True)[0]
    return vec


# v2: payloads carry a signature and the request options so a similar-sounding question
# about a different year/company, or asked with other settings, never reuses an answer.
EMB_PREFIX = "cache:v2:emb:"
RESP_PREFIX = "cache:v2:resp:"


async def check_cache(
    query: str, use_hyde: bool = True, use_decomposition: bool = True, top_k: int = 5
) -> dict | None:
    """Return a cached response for a semantically similar, compatible query."""
    try:
        r = await get_redis()
        query_vec = _embed_query(query)
        options = options_key(use_hyde, use_decomposition, top_k)

        candidates = []
        for key in await r.keys(EMB_PREFIX + "*"):
            cached_emb_bytes = await r.get(key)
            if cached_emb_bytes is None:
                continue
            cached_vec = np.frombuffer(cached_emb_bytes, dtype=np.float32)
            sim = float(np.dot(query_vec, cached_vec))  # normalized, so cosine
            if sim >= THRESHOLD:
                candidates.append((sim, key))

        for sim, key in sorted(candidates, reverse=True):
            payload = await r.get(key.decode().replace(EMB_PREFIX, RESP_PREFIX))
            if not payload:
                continue
            entry = json.loads(payload)
            if is_reusable(query, entry["sig"], entry["options"], options):
                logger.info(f"Semantic cache hit (similarity={sim:.4f})")
                return entry["response"]
            logger.info(
                f"Cache candidate rejected (similarity={sim:.4f}): details differ"
            )

    except Exception as e:
        logger.warning(f"Cache check failed: {e}")

    return None


async def set_cache(
    query: str,
    response: dict,
    use_hyde: bool = True,
    use_decomposition: bool = True,
    top_k: int = 5,
) -> None:
    """Store query embedding + response in Redis."""
    try:
        r = await get_redis()
        options = options_key(use_hyde, use_decomposition, top_k)
        query_hash = hashlib.md5(f"{options}|{query}".encode()).hexdigest()

        query_vec = _embed_query(query)
        entry = {
            "sig": sorted(signature(query)),
            "options": options,
            "response": response,
        }

        await r.setex(
            EMB_PREFIX + query_hash, TTL, query_vec.astype(np.float32).tobytes()
        )
        await r.setex(RESP_PREFIX + query_hash, TTL, json.dumps(entry))

    except Exception as e:
        logger.warning(f"Cache set failed: {e}")
