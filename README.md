# SecureRAG

**Evaluation-first RAG platform with OWASP LLM security guardrails.**  
Answers complex multi-hop financial questions from SEC 10-K filings with measurably better accuracy than naive RAG.

[![CI](https://github.com/ErikEllis-git/Project-w-emanster/actions/workflows/ci.yml/badge.svg)](https://github.com/ErikEllis-git/Project-w-emanster/actions/workflows/ci.yml)
[![Python 3.11](https://img.shields.io/badge/python-3.11-blue.svg)](https://www.python.org/downloads/release/python-3110/)
[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](LICENSE)

---

## What It Does

SecureRAG ingests SEC 10-K filings from [FinanceBench](https://huggingface.co/datasets/PatronusAI/financebench) and answers financial questions like:

> *"Compare Apple and Microsoft R&D spending from 2020 to 2022 and identify the trend."*

The system decomposes multi-hop questions, retrieves relevant passages using hybrid dense + sparse search, reranks candidates, and generates cited answers — all while blocking prompt injection, stripping PII, and validating output schema.

---

## Architecture

```
User Query
    │
    ▼
┌─────────────────────────────────────────────────────┐
│  FastAPI  (SecurityMiddleware → rate limit → route)  │
│  ├── Prompt injection block (regex + blocklist)      │
│  └── PII anonymization (Presidio)                    │
└──────────────┬──────────────────────────────────────┘
               │
    ┌──────────▼──────────┐
    │  Semantic Cache      │  Redis — cosine sim ≥ 0.92 skips LLM
    └──────────┬──────────┘
               │ miss
    ┌──────────▼──────────┐
    │  Query Decomposer    │  instructor → DecomposedQuery (Pydantic)
    └──────────┬──────────┘
               │ sub-questions
    ┌──────────▼──────────┐
    │  HyDE Expansion      │  LLM generates hypothetical answer for retrieval
    └──────────┬──────────┘
               │
    ┌──────────▼────────────────────────────────────┐
    │  Hybrid Retrieval                              │
    │  ├── Dense search   (SentenceTransformers)     │
    │  ├── BM25 sparse    (rank-bm25)                │
    │  └── RRF fusion     (k=60)          top-20     │
    └──────────┬────────────────────────────────────┘
               │
    ┌──────────▼──────────┐
    │  CrossEncoder Rerank │  ms-marco-MiniLM-L-6-v2 → top-5
    └──────────┬──────────┘
               │
    ┌──────────▼──────────┐
    │  LLM Generation      │  Groq llama-3.1-70b + instructor validation
    └──────────┬──────────┘
               │
    ┌──────────▼──────────┐
    │  PII Rehydration     │  Presidio tokens → original values
    └──────────┬──────────┘
               │
    ┌──────────▼──────────┐
    │  Langfuse Trace      │  Every query traced end-to-end
    └─────────────────────┘
```

---

## Quick Start

```bash
# 1. Clone and configure
git clone https://github.com/ErikEllis-git/Project-w-emanster.git
cd Project-w-emanster
make setup                   # install deps + spaCy model
cp .env.example .env         # add your API keys (Groq is free)

# 2. Start the stack
make dev                     # docker-compose up: Qdrant + Redis + API

# 3. Ingest FinanceBench
make ingest                  # downloads from HuggingFace, chunks, upserts to Qdrant

# 4. Query the API
curl -X POST http://localhost:8000/api/v1/query \
  -H "Content-Type: application/json" \
  -d '{"question": "What was Apple'\''s total revenue in FY2022?"}'
```

**Services after `make dev`:**

| Service       | URL                              |
|---------------|----------------------------------|
| API + docs    | http://localhost:8000/docs       |
| Qdrant UI     | http://localhost:6333/dashboard  |
| Redis         | localhost:6379                   |

---

## RAG Pipeline

### Hybrid Retrieval + RRF
Dense semantic search (SentenceTransformers `all-MiniLM-L6-v2`) fused with BM25 lexical search using Reciprocal Rank Fusion (`score = Σ 1/(60 + rank)`). Outperforms either method alone, especially on ticker symbols and financial figures that dense retrieval misses.

### HyDE (Hypothetical Document Embeddings)
Instead of embedding the short user question, the LLM generates a hypothetical ideal answer and *that* gets embedded. The hypothetical answer is semantically similar to what's actually in the corpus — significantly improving recall on complex questions.

### CrossEncoder Reranking
After retrieving 20 candidates, a `cross-encoder/ms-marco-MiniLM-L-6-v2` model scores each `(query, chunk)` pair jointly. Unlike bi-encoder similarity, the cross-encoder sees both at once, giving much more accurate relevance scores. Top 5 go to the LLM.

### Multi-hop Query Decomposition
Complex questions (e.g., *"Compare Apple and Microsoft R&D 2020–2022"*) are broken into atomic sub-questions via structured LLM calls using `instructor`. Each sub-question is retrieved independently, then all chunks are merged before reranking.

### Hierarchical Chunking
SEC filings contain financial tables that naive sentence-splitter chunking destroys. LlamaIndex's `HierarchicalNodeParser` produces 2048/512/128-token overlapping parent-child chunks, preserving table structure and cross-reference context.

### Semantic Cache
Redis stores query embeddings. On each request, the incoming query is compared to all cached embeddings using cosine similarity. Hits above 0.92 threshold return the cached response without touching the LLM.

---

## Security (OWASP LLM Top 10)

| Threat | Mitigation | Where |
|--------|-----------|-------|
| LLM01 Prompt Injection | Regex + blocklist on 15+ injection patterns | `security/input_guard.py` → `SecurityMiddleware` |
| LLM02 Insecure Output | `instructor` + Pydantic schema validation, auto-retry | `security/output_guard.py` → `FinancialRAGResponse` |
| LLM06 Sensitive Info Disclosure | Presidio PII anonymization before LLM, rehydration after | `security/pii_handler.py` |

Adversarial test coverage: 10 injection attempts + 3 PII cases + rate limit test — all enforced in CI.

---

## Evaluation

CI enforces quality thresholds on every PR to `main`. Build fails if scores drop below:

| Metric | Threshold | Judge Model |
|--------|-----------|-------------|
| Faithfulness | ≥ 0.75 | gpt-4o-mini |
| Contextual Precision | ≥ 0.70 | gpt-4o-mini |
| Answer Relevancy | ≥ 0.75 | gpt-4o-mini |

### A/B Pipeline Comparison

5 configurations tested on 20 golden questions with bootstrapped 95% CI:

| Configuration | Faithfulness | Ctx Precision | Relevancy |
|---------------|-------------|---------------|-----------|
| Baseline (dense only) | — | — | — |
| Dense + rerank | — | — | — |
| Hybrid only | — | — | — |
| Hybrid + rerank | — | — | — |
| **HyDE + hybrid + rerank** | — | — | — |

*Results populated after running `make ab-test`. See `evaluation/ab_test_results.json`.*

### Golden Dataset
100 Q&A pairs: real FinanceBench ground truth + Ragas-synthesized multi-hop questions.

```bash
make golden     # generate synthetic Q&A pairs via Ragas
make eval       # run DeepEval quality gate
make eval-adv   # run adversarial red-team tests
make ab-test    # run A/B pipeline comparison
```

---

## Tech Stack

| Layer | Technology |
|-------|-----------|
| API | FastAPI + Uvicorn + slowapi (rate limiting) |
| Vector DB | Qdrant (dense + sparse collections) |
| Embeddings | SentenceTransformers `all-MiniLM-L6-v2` |
| Reranker | CrossEncoder `ms-marco-MiniLM-L-6-v2` |
| LLM | Groq `llama-3.1-70b-versatile` (free tier) + OpenAI fallback |
| Structured output | `instructor` (NOT Guardrails RAIL — deprecated) |
| Cache | Redis (semantic cosine similarity) |
| PII | Microsoft Presidio |
| Eval | DeepEval + Ragas + SciPy (bootstrap CI) |
| Tracing | Langfuse |
| Ingestion | unstructured[pdf] + HuggingFace datasets |
| Frontend | Next.js 15 + Tailwind CSS |
| Deploy | Vercel (frontend) + Fly.io (API) |
| CI | GitHub Actions |

---

## Project Structure

```
.
├── api/                    # FastAPI app, routes, middleware
│   ├── main.py             # app factory, lifespan, middleware registration
│   ├── routes/             # /query, /ingest, /health
│   └── middleware/         # security (injection block), cache, logging
├── retrieval/              # retrieval pipeline modules
│   ├── hybrid.py           # dense + BM25 + RRF fusion
│   ├── hyde.py             # hypothetical document embedding
│   ├── reranker.py         # CrossEncoder reranking
│   ├── decomposer.py       # multi-hop query decomposition
│   └── vectorstore.py      # Qdrant client + upsert/search
├── generation/             # LLM generation
│   ├── llm.py              # Groq/OpenAI client + generate_answer
│   └── prompts/            # Jinja2 templates (system, user, HyDE, decompose)
├── ingestion/              # data pipeline
│   ├── loader.py           # FinanceBench HuggingFace loader
│   ├── chunker.py          # hierarchical chunking (preserves tables)
│   └── embedder.py         # SentenceTransformers + L2 normalization
├── security/               # OWASP LLM guardrails
│   ├── input_guard.py      # prompt injection detection
│   ├── output_guard.py     # Pydantic output schema
│   └── pii_handler.py      # Presidio anonymize/rehydrate
├── evaluation/             # eval framework
│   ├── harness.py          # DeepEval test runner
│   ├── ab_test.py          # A/B pipeline config manager
│   ├── metrics.py          # metric collection + persistence
│   ├── golden_dataset.py   # golden dataset management
│   └── adversarial.py      # injection + PII test cases
├── scripts/                # one-shot CLI scripts
│   ├── ingest.py           # ingest FinanceBench into Qdrant
│   ├── generate_golden_dataset.py
│   ├── run_ab_test.py
│   └── fine_tune_embeddings.py
├── tests/
│   ├── unit/               # chunker, input_guard, pii_handler
│   ├── integration/        # ingest + query endpoints
│   └── eval/               # DeepEval quality gate + adversarial
├── docs/
│   ├── ARCHITECTURE.md     # detailed system design
│   └── SECURITY.md         # threat model + mitigations
├── docker-compose.yml      # Qdrant + Redis + API (one command)
├── Dockerfile
├── Makefile                # make dev / test / eval / ab-test
└── .env.example            # all required env vars documented
```

---

## Team

- **Erik** — DS/ML: retrieval pipeline, evaluation framework, A/B testing, embedding fine-tuning
- **Emmanuel** — SWE: Next.js frontend, Fly.io deployment, CI/CD, API integration

---

## API Reference

Full interactive docs at `http://localhost:8000/docs` after `make dev`.

**POST `/api/v1/query`**
```json
{
  "question": "What was Apple's revenue in FY2022?",
  "top_k": 5,
  "use_hyde": true,
  "use_decomposition": true
}
```

**Response**
```json
{
  "answer": "Apple reported net sales of $394.3 billion in fiscal year 2022...",
  "sources": [
    {
      "text": "...",
      "source": "AAPL_2022_10K.pdf",
      "company": "Apple",
      "year": "2022",
      "section": "ITEM 6. SELECTED FINANCIAL DATA",
      "score": 0.94
    }
  ],
  "latency_ms": 1240.5,
  "cached": false,
  "sub_questions": null
}
```
