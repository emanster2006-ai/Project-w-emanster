from fastapi import APIRouter, BackgroundTasks, Depends, HTTPException
from api.auth import require_ingest_key
from pydantic import BaseModel, Field
from typing import Literal
import logging

logger = logging.getLogger(__name__)
router = APIRouter()
_running = False  # one ingestion at a time: each run adds a full copy of the corpus


class IngestRequest(BaseModel):
    source: Literal["financebench"] = "financebench"
    limit: int | None = Field(default=None, ge=1)  # None = ingest all


class IngestResponse(BaseModel):
    status: str
    documents_queued: int
    message: str


def _run_once(source: str, limit: int | None) -> None:
    global _running
    from scripts.ingest import run_ingestion

    try:
        run_ingestion(source=source, limit=limit)
    finally:
        _running = False


@router.post(
    "/ingest",
    response_model=IngestResponse,
    dependencies=[Depends(require_ingest_key)],
)
async def ingest(body: IngestRequest, background_tasks: BackgroundTasks):
    """
    Trigger the ingestion pipeline in the background (requires INGEST_API_KEY).
    Downloads FinanceBench, chunks, embeds, and upserts into Qdrant.
    """
    global _running
    if _running:
        raise HTTPException(status_code=409, detail="An ingestion is already running.")
    _running = True
    background_tasks.add_task(_run_once, body.source, body.limit)
    return IngestResponse(
        status="queued",
        documents_queued=body.limit or -1,
        message="Ingestion running in background. Check /health for status.",
    )
