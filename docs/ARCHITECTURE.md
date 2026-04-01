# Architecture

## System Overview

SecureRAG is a production-grade RAG (Retrieval-Augmented Generation) API designed specifically for SEC 10-K financial filings. It answers complex multi-hop financial questions with citations, while enforcing OWASP LLM Top 10 security controls at every stage.

```
                        ┌─────────────────┐
                        │   Next.js 15    │  localhost:3000
                        │   Frontend      │
                        └────────┬────────┘
                                 │ POST /api/v1/query
                        ┌────────▼────────┐
                        │   FastAPI API   │  localhost:8000
                        │                 │
                        │ SecurityMiddleware
                        │  ├─ injection   │  regex + blocklist
                        │  └─ PII strip   │  Presidio
                        │                 │
                        │  Rate Limiter   │  slowapi (20 req/min)
                        └────────┬────────┘
                                 │
              ┌──────────────────▼──────────────────┐
              │           Query Pipeline             │
              │                                      │
              │  1. Semantic cache (Redis)            │
              │     cosine sim >= 0.92 => return      │
              │                                      │
              │  2. Query decomposition               │
              │     instructor -> DecomposedQuery    │
              │     (sub-questions for multi-hop)    │
              │                                      │
              │  3. HyDE expansion                   │
              │     LLM -> hypothetical answer text  │
              │     embed that instead of question   │
              │                                      │
              │  4. Hybrid retrieval                 │
              │     dense: SentenceTransformers      │
              │     BM25:  rank-bm25                 │
              │     Fuse:  RRF (k=60)       top-20  │
              │                                      │
              │  5. CrossEncoder reranking            │
              │     ms-marco-MiniLM-L-6-v2   top-5  │
              │                                      │
              │  6. LLM generation                   │
              │     Groq llama-3.1-70b               │
              │     instructor + Pydantic schema     │
              │     auto-retry on schema failure     │
              │                                      │
              │  7. PII rehydration                  │
              │     restore Presidio tokens          │
              │                                      │
              │  8. Langfuse trace                   │
              └─────────────────────────────────────┘
                                 │
              ┌──────────────────┴────────────────────┐
              │                                        │
    ┌─────────▼──────────┐              ┌─────────────▼──────────┐
    │   Qdrant           │              │   Redis                 │
    │   Vector DB        │              │   Semantic cache        │
    │   Dense + Sparse   │              │   TTL: 1 hour           │
    └────────────────────┘              └────────────────────────┘
```

---

## Component Design

### SecurityMiddleware

Runs before every route. Two responsibilities:

1. **Injection detection** — `security/input_guard.py` checks 15+ regex patterns covering: ignore-previous-instructions, persona hijacking (DAN, jailbreak), system prompt extraction, Llama format injection, XSS in query. Returns 400 if matched.

2. **PII anonymization** — `security/pii_handler.py` uses Presidio to detect and replace PII entities (SSN, credit cards, names, emails) with deterministic tokens (`<PERSON_0>`, `<US_SSN_0>`). The mapping is stored in `request.state.pii_mapping` for rehydration after generation. No raw PII reaches the LLM or Qdrant.

### Ingestion Pipeline

```
HuggingFace (PatronusAI/financebench)
    |
    v
loader.py          load_financebench()
    |              Downloads dataset, extracts evidence_text + metadata
    |              (company, ticker, fiscal_year, doc_type)
    v
chunker.py         chunk_documents()
    |              HierarchicalNodeParser: 2048 / 512 / 128 token levels
    |              Detects SEC section headers (ITEM 1A. RISK FACTORS, etc.)
    |              Injects company/year/section into every node's metadata
    v
embedder.py        embed_texts()
    |              SentenceTransformers all-MiniLM-L6-v2
    |              L2-normalized -> dot product = cosine similarity
    v
vectorstore.py     upsert_nodes()
                   Qdrant collection with dense + sparse vector support
                   Batched upsert (100 per request)
```

**Why hierarchical chunking?** SEC 10-K filings contain tables (income statements, balance sheets) that naive sentence splitting destroys mid-row. The three-level hierarchy lets retrieval find the exact row (128 tokens) while keeping the full table as context (2048 tokens parent node).

### Retrieval: Hybrid + RRF

Dense and sparse retrieval are complementary:
- **Dense (semantic)** — good at paraphrases, synonyms, conceptual queries
- **BM25 (lexical)** — good at exact terms: ticker symbols, financial figures, section names

RRF formula: `score = sum(1 / (k + rank_i))` across all ranked lists. `k=60` is the standard constant that reduces the gap between rank 1 and rank 2, preventing any single list from dominating.

### HyDE

Short questions are often semantically far from the long passages stored in the corpus. HyDE bridges this by asking the LLM to write a hypothetical answer, then embedding that. The hypothetical answer uses the same vocabulary and style as the 10-K passage it describes.

The hypothetical doc is only used for embedding/retrieval — it is never shown to the user.

### CrossEncoder Reranking

Bi-encoder similarity (used in dense retrieval) computes embeddings for query and document independently — fast but less accurate. The CrossEncoder sees the full `(query, chunk)` pair together, giving access to interaction signals. This significantly improves precision at the cost of latency on the top-20 candidates only (not all corpus documents).

Model: `cross-encoder/ms-marco-MiniLM-L-6-v2` — lightweight but highly accurate for passage ranking.

### Query Decomposition

Complex questions requiring multiple lookups (e.g., *"Compare Apple and Microsoft R&D 2020-2022"*) are detected and decomposed via a structured LLM call. The `instructor` library enforces the `DecomposedQuery` Pydantic schema — if the LLM returns malformed output, instructor auto-retries.

Each sub-question is retrieved independently. All chunks are merged into a single pool before reranking, and the original question is used for reranking (not the sub-questions).

### Semantic Cache

Redis stores: `cache:emb:{md5(query)}` -> embedding bytes, `cache:resp:{md5(query)}` -> JSON response.

On each request, the incoming query embedding is compared against all cached embeddings using dot product (valid for L2-normalized vectors). Threshold 0.92 was chosen empirically — below this, paraphrases with different intent start matching.

### Output Validation

`instructor` wraps the Groq client and enforces `FinancialRAGResponse`:
- `answer: str` — the actual answer
- `confidence: "high" | "medium" | "low"`
- `requires_professional_advice: bool`

A `field_validator` catches common hallucination signals ("as an AI", "I don't have access to") and raises a `ValueError`, causing instructor to retry with the LLM.

---

## Infrastructure

### Docker Compose (local)

| Service | Image | Port |
|---------|-------|------|
| Qdrant | qdrant/qdrant:v1.11.3 | 6333 (REST), 6334 (gRPC) |
| Redis | redis:7.4-alpine | 6379 |
| API | local Dockerfile | 8000 |

All services have healthchecks. The API container waits for both Qdrant and Redis to be healthy before starting.

### Production (planned)

| Component | Provider |
|-----------|---------|
| API | Fly.io (Docker container) |
| Frontend | Vercel |
| Qdrant | Qdrant Cloud or Fly.io volume |
| Redis | Upstash Redis |
| Tracing | Langfuse Cloud |

---

## Evaluation Architecture

```
Golden Dataset (100 Q&A pairs)
  60%  FinanceBench ground truth (real SEC data)
  40%  Ragas-synthesized multi-hop questions

EvalHarness (evaluation/harness.py)
  -> runs full pipeline per question
  -> scores with DeepEval metrics (judge: gpt-4o-mini)
  -> persists results to evaluation/metrics_history.json

A/B Test Runner (scripts/run_ab_test.py)
  -> 5 PipelineConfig variants
  -> 20 questions per config
  -> bootstrapped 95% CI on each metric
  -> saves to evaluation/ab_test_results.json

CI Quality Gate (.github/workflows/ci.yml)
  -> runs on every PR to main
  -> deepeval test run tests/eval/test_rag_quality.py
  -> build FAILS if any threshold violated
```
