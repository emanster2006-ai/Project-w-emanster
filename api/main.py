"""
SecureRAG — FastAPI Application Entry Point
"""

from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from slowapi import Limiter, _rate_limit_exceeded_handler
from slowapi.errors import RateLimitExceeded
from slowapi.util import get_remote_address

from api.middleware.logging import LoggingMiddleware
from api.middleware.security import SecurityMiddleware
from api.routes import health, ingest, query
from langfuse import Langfuse
import logging
import os

logger = logging.getLogger(__name__)

limiter = Limiter(key_func=get_remote_address)


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Initialize resources on startup, clean up on shutdown."""
    logger.info("SecureRAG API starting up...")

    from ingestion.embedder import get_embedder
    get_embedder()
    logger.info("Embedding model loaded")

    from retrieval.vectorstore import get_vectorstore
    get_vectorstore()
    logger.info(f"Qdrant connected — collection: {os.getenv('QDRANT_COLLECTION_NAME')}")

    app.state.langfuse = Langfuse(
        public_key=os.getenv("LANGFUSE_PUBLIC_KEY"),
        secret_key=os.getenv("LANGFUSE_SECRET_KEY"),
        host=os.getenv("LANGFUSE_HOST", "https://cloud.langfuse.com"),
    )
    logger.info("Langfuse tracing initialized")

    yield

    logger.info("SecureRAG API shutting down...")
    app.state.langfuse.flush()


def create_app() -> FastAPI:
    app = FastAPI(
        title="SecureRAG",
        description=(
            "Evaluation-first RAG platform with security guardrails. "
            "Answers complex financial questions from SEC 10-K filings."
        ),
        version="1.0.0",
        lifespan=lifespan,
        docs_url="/docs",
        redoc_url="/redoc",
    )

    app.add_middleware(
        CORSMiddleware,
        allow_origins=["http://localhost:3000"],
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )
    app.add_middleware(LoggingMiddleware)
    app.add_middleware(SecurityMiddleware)

    app.state.limiter = limiter
    app.add_exception_handler(RateLimitExceeded, _rate_limit_exceeded_handler)

    app.include_router(health.router, tags=["Health"])
    app.include_router(query.router, prefix="/api/v1", tags=["Query"])
    app.include_router(ingest.router, prefix="/api/v1", tags=["Ingest"])

    return app


app = create_app()
