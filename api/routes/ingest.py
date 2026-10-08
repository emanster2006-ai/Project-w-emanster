import logging

from fastapi import APIRouter, BackgroundTasks
from pydantic import BaseModel

logger = logging.getLogger(__name__)
router = APIRouter()


class IngestRequest(BaseModel):
    source: str = "financebench"
    limit: int | None = None  # None = ingest all


class IngestResponse(BaseModel):
    status: str
    documents_queued: int
    message: str


@router.post("/ingest", response_model=IngestResponse)
async def ingest(body: IngestRequest, background_tasks: BackgroundTasks):
    """
    Trigger the ingestion pipeline in the background.
    Downloads FinanceBench, chunks, embeds, and upserts into Qdrant.
    """
    from scripts.ingest import run_ingestion

    background_tasks.add_task(run_ingestion, source=body.source, limit=body.limit)
    return IngestResponse(
        status="queued",
        documents_queued=body.limit or -1,
        message="Ingestion running in background. Check /health for status.",
    )
