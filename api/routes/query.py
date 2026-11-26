"""
/api/v1/query — Main RAG query endpoint
Handles multi-hop decomposition, HyDE, hybrid retrieval, reranking, and streaming.
"""

from fastapi import APIRouter, Request, HTTPException
from pydantic import BaseModel, Field
from slowapi import Limiter
from slowapi.util import get_remote_address
import time
import os
import logging

logger = logging.getLogger(__name__)
router = APIRouter()
limiter = Limiter(key_func=get_remote_address)


class QueryRequest(BaseModel):
    question: str = Field(..., min_length=3, max_length=2000)
    top_k: int = Field(default=8, ge=1, le=20)
    use_hyde: bool = Field(
        default=False
    )  # no measured retrieval gain; costs a model call
    use_decomposition: bool = Field(default=True)
    stream: bool = Field(default=True)


class SourceChunk(BaseModel):
    text: str
    source: str
    company: str | None = None
    year: str | None = None
    section: str | None = None
    score: float


class QueryResponse(BaseModel):
    answer: str
    sources: list[SourceChunk]
    latency_ms: float
    cached: bool = False
    sub_questions: list[str] | None = None


@router.post("/query")
@limiter.limit(f"{os.getenv('RATE_LIMIT_PER_MINUTE', 20)}/minute")
async def query(request: Request, body: QueryRequest):
    """
    Full RAG pipeline:
    1. PII sanitization (via SecurityMiddleware)
    2. Semantic cache lookup
    3. Optional query decomposition (multi-hop)
    4. Optional HyDE expansion
    5. Hybrid retrieval (dense + sparse BM25 + RRF fusion)
    6. CrossEncoder reranking
    7. LLM generation with Jinja2 prompts
    8. Output validation via instructor
    9. PII rehydration
    10. Langfuse trace logging
    """
    from api.middleware.cache import check_cache, set_cache
    from retrieval.pipeline import retrieve_context
    from generation.llm import generate_answer
    from security.pii_handler import rehydrate
    from api.tracing import start_trace

    question = getattr(request.state, "sanitized_question", body.question)
    pii_mapping = getattr(request.state, "pii_mapping", {})
    start = time.time()
    trace = start_trace(
        getattr(request.app.state, "langfuse", None),
        name="rag_query",
        input={"question": question},
    )

    try:
        # ── 1. Semantic cache ──────────────────────────────────────────────
        cached = (
            None
            if pii_mapping
            else await check_cache(
                question, body.use_hyde, body.use_decomposition, body.top_k or 8
            )
        )
        if cached:
            logger.info("Cache hit for query")
            cached["cached"] = True
            return QueryResponse(**cached)

        # ── 2–5. Decomposition, HyDE, hybrid retrieval, dedup, reranking ───
        context = await retrieve_context(
            question,
            use_decomposition=body.use_decomposition,
            use_hyde=body.use_hyde,
            top_k=body.top_k,
            trace=trace,
        )
        reranked_chunks, sub_questions = context.chunks, context.sub_questions

        # ── 6. LLM generation ──────────────────────────────────────────────
        span = trace.span(name="generation")
        answer = await generate_answer(question, reranked_chunks)
        span.end(output={"answer_length": len(answer)})

        sanitized_answer = answer

        # ── 7. Rehydrate PII tokens ───────────────────────────────────────
        if hasattr(request.state, "pii_mapping") and request.state.pii_mapping:
            answer = rehydrate(answer, request.state.pii_mapping)

        sources = [
            SourceChunk(
                text=c["text"],
                source=c["metadata"].get("source", ""),
                company=c["metadata"].get("company"),
                year=c["metadata"].get("year"),
                section=c["metadata"].get("section"),
                score=c["score"],
            )
            for c in reranked_chunks
        ]

        latency_ms = (time.time() - start) * 1000
        trace.update(output={"answer": sanitized_answer, "latency_ms": latency_ms})

        result = QueryResponse(
            answer=answer,
            sources=sources,
            latency_ms=latency_ms,
            cached=False,
            sub_questions=sub_questions,
        )

        # ── 8. Cache the result ───────────────────────────────────────────
        if not pii_mapping:
            await set_cache(
                question,
                result.model_dump(),
                body.use_hyde,
                body.use_decomposition,
                body.top_k or 8,
            )

        return result

    except Exception as e:
        logger.error(f"Query failed: {e}", exc_info=True)
        trace.update(level="ERROR", status_message=str(e))
        from api.errors import is_rate_limited

        if is_rate_limited(e):
            raise HTTPException(
                status_code=429,
                detail="The language model is rate limited. Please retry shortly.",
                headers={"Retry-After": "60"},
            )
        raise HTTPException(status_code=500, detail="Query processing failed")
    finally:
        trace.end()
