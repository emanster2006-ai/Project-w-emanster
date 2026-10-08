"""
Semantic cache using Redis.
If an incoming query has cosine similarity > threshold with a cached query,
return the cached response without hitting the LLM.
"""

import hashlib
import json
import logging
import os

import numpy as np
import redis.asyncio as aioredis

logger = logging.getLogger(__name__)

REDIS_URL = os.getenv("REDIS_URL", "redis://localhost:6379")
THRESHOLD = float(os.getenv("SEMANTIC_CACHE_THRESHOLD", "0.92"))
TTL = int(os.getenv("CACHE_TTL_SECONDS", "3600"))

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


async def check_cache(query: str) -> dict | None:
    """Return cached response if a semantically similar query exists."""
    try:
        r = await get_redis()
        query_vec = _embed_query(query)

        # Scan all cached embedding keys
        keys = await r.keys("cache:emb:*")
        best_sim = 0.0
        best_key = None

        for key in keys:
            cached_emb_bytes = await r.get(key)
            if cached_emb_bytes is None:
                continue
            cached_vec = np.frombuffer(cached_emb_bytes, dtype=np.float32)
            sim = float(
                np.dot(query_vec, cached_vec)
            )  # dot product = cosine (normalized)
            if sim > best_sim:
                best_sim = sim
                best_key = key

        if best_sim >= THRESHOLD and best_key is not None:
            # Get corresponding response
            response_key = best_key.decode().replace("cache:emb:", "cache:resp:")
            cached_response = await r.get(response_key)
            if cached_response:
                logger.info(f"Semantic cache hit (similarity={best_sim:.4f})")
                return json.loads(cached_response)

    except Exception as e:  # noqa: BLE001
        logger.warning(f"Cache check failed: {e}")

    return None


async def set_cache(query: str, response: dict) -> None:
    """Store query embedding + response in Redis."""
    try:
        r = await get_redis()
        query_hash = hashlib.md5(query.encode()).hexdigest()

        query_vec = _embed_query(query)
        emb_key = f"cache:emb:{query_hash}"
        resp_key = f"cache:resp:{query_hash}"

        await r.setex(emb_key, TTL, query_vec.astype(np.float32).tobytes())
        await r.setex(resp_key, TTL, json.dumps(response))

    except Exception as e:  # noqa: BLE001
        logger.warning(f"Cache set failed: {e}")
