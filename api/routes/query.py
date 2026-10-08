"""
/api/v1/query — Main RAG query endpoint
Handles multi-hop decomposition, HyDE, hybrid retrieval, reranking, and streaming.
"""

import logging
import os
import time

from fastapi import APIRouter, HTTPException, Request
from pydantic import BaseModel, Field
from slowapi import Limiter
from slowapi.util import get_remote_address

logger = logging.getLogger(__name__)
router = APIRouter()
limiter = Limiter(key_func=get_remote_address)


class QueryRequest(BaseModel):
    question: str = Field(..., min_length=3, max_length=2000)
    top_k: int = Field(default=5, ge=1, le=20)
    use_hyde: bool = Field(default=True)
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
@limiter.limit(f"{os.getenv('RATE_LIMIT_PER_MINUTE', "20")}/minute")
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
    from generation.llm import generate_answer
    from retrieval.decomposer import decompose_query
    from retrieval.hybrid import hybrid_search
    from retrieval.hyde import generate_hypothetical_doc
    from retrieval.reranker import rerank
    from retrieval.vectorstore import get_vectorstore
    from security.pii_handler import rehydrate

    start = time.time()
    langfuse = request.app.state.langfuse
    trace = langfuse.trace(name="rag_query", input={"question": body.question})

    try:
        # ── 1. Semantic cache ──────────────────────────────────────────────
        cached = await check_cache(body.question)
        if cached:
            logger.info("Cache hit for query")
            cached["cached"] = True
            return QueryResponse(**cached)

        # ── 2. Query decomposition ─────────────────────────────────────────
        sub_questions = None
        queries_to_run = [body.question]
        if body.use_decomposition:
            span = trace.span(name="decomposition")
            sub_questions = await decompose_query(body.question)
            if sub_questions and len(sub_questions) > 1:
                queries_to_run = sub_questions
            span.end(output={"sub_questions": sub_questions})

        # ── 3. HyDE expansion ──────────────────────────────────────────────
        retrieval_queries = []
        if body.use_hyde:
            span = trace.span(name="hyde")
            for q in queries_to_run:
                hypo_doc = await generate_hypothetical_doc(q)
                retrieval_queries.append(hypo_doc)
            span.end(output={"hyde_docs_generated": len(retrieval_queries)})
        else:
            retrieval_queries = queries_to_run

        # ── 4. Hybrid retrieval + RRF fusion ───────────────────────────────
        span = trace.span(name="retrieval")
        get_vectorstore()
        all_chunks = []
        for rq in retrieval_queries:
            chunks = await hybrid_search(
                rq, top_k=int(os.getenv("TOP_K_RETRIEVE", "20"))
            )
            all_chunks.extend(chunks)
        span.end(output={"chunks_retrieved": len(all_chunks)})

        # ── 5. CrossEncoder reranking ──────────────────────────────────────
        span = trace.span(name="reranking")
        top_k = body.top_k or int(os.getenv("TOP_K_RERANK", "5"))
        reranked_chunks = rerank(body.question, all_chunks, top_k=top_k)
        span.end(output={"chunks_after_rerank": len(reranked_chunks)})

        # ── 6. LLM generation ──────────────────────────────────────────────
        span = trace.span(name="generation")
        answer = await generate_answer(body.question, reranked_chunks)
        span.end(output={"answer_length": len(answer)})

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
        trace.update(output={"answer": answer, "latency_ms": latency_ms})

        result = QueryResponse(
            answer=answer,
            sources=sources,
            latency_ms=latency_ms,
            cached=False,
            sub_questions=sub_questions,
        )

        # ── 8. Cache the result ───────────────────────────────────────────
        await set_cache(body.question, result.model_dump())

        return result

    except Exception as e:
        logger.exception("Query failed")
        trace.update(level="ERROR", status_message=str(e))
        raise HTTPException(status_code=500, detail="Query processing failed")
