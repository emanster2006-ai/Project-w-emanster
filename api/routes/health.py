from fastapi import APIRouter
from pydantic import BaseModel
import time
import os
import logging

logger = logging.getLogger(__name__)
router = APIRouter()


class DependencyStatus(BaseModel):
    qdrant: str
    redis: str
    embedder: str


class HealthResponse(BaseModel):
    status: str
    version: str
    timestamp: float
    dependencies: DependencyStatus


@router.get("/health", response_model=HealthResponse)
async def health():
    deps = await _check_dependencies()
    overall = "ok" if all(v == "ok" for v in deps.model_dump().values()) else "degraded"
    return HealthResponse(
        status=overall,
        version="1.0.0",
        timestamp=time.time(),
        dependencies=deps,
    )


async def _check_dependencies() -> DependencyStatus:
    qdrant_status = "ok"
    redis_status = "ok"
    embedder_status = "ok"

    try:
        from retrieval.vectorstore import get_vectorstore
        client = get_vectorstore()
        client.get_collections()
    except Exception as e:
        logger.warning(f"Qdrant health check failed: {e}")
        qdrant_status = "unavailable"

    try:
        import redis.asyncio as aioredis
        r = aioredis.from_url(os.getenv("REDIS_URL", "redis://localhost:6379"))
        await r.ping()
        await r.aclose()
    except Exception as e:
        logger.warning(f"Redis health check failed: {e}")
        redis_status = "unavailable"

    try:
        from ingestion.embedder import get_embedder
        get_embedder()
    except Exception as e:
        logger.warning(f"Embedder health check failed: {e}")
        embedder_status = "unavailable"

    return DependencyStatus(qdrant=qdrant_status, redis=redis_status, embedder=embedder_status)
