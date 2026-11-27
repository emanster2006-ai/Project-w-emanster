"""The retrieval half of a query: decomposition, HyDE, hybrid search, dedup, rerank.

Shared by the /query route and by evaluation scripts that need the exact ordered
context the generator would see (scripts/counterfactual_capture.py), so the two can
never drift apart. Imports are inside the function so tests can substitute modules.
"""

import os
from dataclasses import dataclass


class _NoSpan:
    def end(self, **_):
        pass


class _NoTrace:
    def span(self, **_):
        return _NoSpan()


@dataclass
class RetrievedContext:
    chunks: list[dict]  # reranked, in the order the generator receives them
    sub_questions: list[str] | None


async def retrieve_context(
    question: str,
    *,
    use_decomposition: bool,
    use_hyde: bool,
    top_k: int | None,
    trace=None,
) -> RetrievedContext:
    from retrieval.decomposer import decompose_query
    from retrieval.hybrid import hybrid_search
    from retrieval.hyde import generate_hypothetical_doc
    from retrieval.reranker import rerank

    trace = trace or _NoTrace()

    # ── Query decomposition ────────────────────────────────────────────────
    sub_questions = None
    queries_to_run = [question]
    if use_decomposition:
        span = trace.span(name="decomposition")
        sub_questions = await decompose_query(question)
        if sub_questions and len(sub_questions) > 1:
            # Keep the original question too: sub-questions alone can drop the
            # company, year or metric that the full question carries.
            queries_to_run = [question, *sub_questions]
        span.end(output={"sub_questions": sub_questions})

    # ── HyDE expansion ─────────────────────────────────────────────────────
    # Always retrieve with the real question(s); HyDE passages are an addition, not a
    # replacement, so entity and year terms in the question cannot be diluted away.
    retrieval_queries = list(queries_to_run)
    if use_hyde:
        span = trace.span(name="hyde")
        for q in queries_to_run:
            hypo_doc = await generate_hypothetical_doc(q)
            if hypo_doc:
                retrieval_queries.append(hypo_doc)
        span.end(
            output={"hyde_docs_generated": len(retrieval_queries) - len(queries_to_run)}
        )

    # ── Hybrid retrieval + RRF fusion ──────────────────────────────────────
    span = trace.span(name="retrieval")
    all_chunks = []
    for rq in retrieval_queries:
        chunks = await hybrid_search(rq, top_k=int(os.getenv("TOP_K_RETRIEVE", 20)))
        all_chunks.extend(chunks)
    span.end(output={"chunks_retrieved": len(all_chunks)})

    # The same chunk is usually returned by several queries; keep one copy so
    # duplicates cannot crowd distinct evidence out of the top-k.
    seen: set[str] = set()
    unique_chunks = []
    for c in all_chunks:
        if c["text"] not in seen:
            seen.add(c["text"])
            unique_chunks.append(c)

    # ── CrossEncoder reranking ─────────────────────────────────────────────
    span = trace.span(name="reranking")
    k = top_k or int(os.getenv("TOP_K_RERANK", 8))
    reranked = rerank(question, unique_chunks, top_k=k)
    span.end(output={"chunks_after_rerank": len(reranked)})

    return RetrievedContext(chunks=reranked, sub_questions=sub_questions)
