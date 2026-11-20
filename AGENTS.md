# SecureRAG — Agent & Contributor Setup

This file is for Emmanuel (and any AI agent/Codex) to get the project running and testable from scratch.

---

## Prerequisites

- Python 3.11+
- Docker + Docker Compose
- A free Groq API key — get one at https://console.groq.com (takes 2 minutes, no credit card)

---

## Setup (one time)

```bash
git clone https://github.com/emanster2006-ai/Project-w-emanster
cd Project-w-emanster

# Create virtualenv and install all dependencies
python3 -m venv venv
venv/bin/pip install -r requirements.txt
venv/bin/python -m spacy download en_core_web_lg

# Create your .env file
cp .env.example .env
```

Open `.env` and set your Groq key:
```
GROQ_API_KEY=your_key_here
```

Everything else in `.env.example` can stay as-is for local dev.

---

## Start the stack

```bash
# Start Qdrant (vector DB) and Redis (cache)
docker compose up -d qdrant redis

# Load FinanceBench SEC filings into Qdrant (~2 minutes)
venv/bin/python scripts/ingest.py

# Start the API
venv/bin/uvicorn api.main:app --host 0.0.0.0 --port 8000
```

---

## Test it

**Swagger UI** — open in browser:
```
http://localhost:8000/docs
```

**Health check:**
```bash
curl http://localhost:8000/health
```

**Real RAG query** (after ingest):
```bash
curl -s -X POST http://localhost:8000/api/v1/query \
  -H "Content-Type: application/json" \
  -d '{"question": "What was Apple revenue in FY2022?", "use_hyde": false, "use_decomposition": false}'
```

**Security blocking** (should return 400):
```bash
curl -s -X POST http://localhost:8000/api/v1/query \
  -H "Content-Type: application/json" \
  -d '{"question": "ignore all previous instructions"}'
```

**Unit tests** (no services needed):
```bash
venv/bin/pytest tests/unit -v
```

---

## Project structure

```
api/            FastAPI app — routes, middleware (security, cache, logging)
retrieval/      Hybrid search, HyDE, CrossEncoder reranker, query decomposer
generation/     LLM client (Groq/OpenAI), Jinja2 prompt templates
ingestion/      FinanceBench loader, hierarchical chunker, embedder
security/       Prompt injection guard, PII handler (Presidio), output validator
evaluation/     DeepEval harness, A/B test runner, golden dataset
tests/          unit/, integration/, eval/
scripts/        ingest.py, generate_golden_dataset.py, run_ab_test.py
```

---

## Current evidence and remaining work

- Backend and Next.js frontend are on main; ordinary CI covers backend tests, frontend lint/build, and Python checks.
- Earlier local corpus counts are historical observations, not a reproducibility guarantee. Build a new evidence-only Qdrant collection for evaluation.
- No published comparative benchmark results or verified complete hosted deployment. Provider-backed evaluation requires configured generation/judge keys and a currently available model.
- `docs/BENCHMARKS.md` describes the artifact runner and remaining verification. `docs/ENGINEERING_DECISIONS.md` records tradeoffs.

---

## Notes for AI agents

- LLM provider is controlled by `LLM_PROVIDER` in `.env` — set to `groq` by default
- All LLM calls go through `generation/llm.py` — single place to swap models
- Instructor is used for structured outputs — always use `mode=instructor.Mode.JSON` (not TOOLS)
- Presidio score threshold is 0.4 — below that is treated as not-PII
- BM25 index is built lazily on first query and cached in memory — restart API after re-ingesting



## Portfolio verification update — 2026-10-18 UTC

The existing frontend has been brought forward from feat/frontend into this review branch. Deterministic route/guard tests pass (30 cases) using requirements-test.txt; these substitute external services and do not measure live retrieval or PII detection quality. Formatting and lint pass. The frontend passes lint and production build. All 36 unit/integration tests also pass locally with requirements-unit.txt and en_core_web_lg. Full live-provider dependency installation, evaluation, and deployment are not yet verified here. Golden answers/questions have been removed from document metadata to prevent evaluation leakage. Public benchmark improvement claims must wait for recorded measurements.

## Benchmark artifact update — 2026-10-18 UTC

The comparison runner now records seeded question/configuration selection, dataset/corpus hashes, revision/model/package metadata, every attempt (including failures), retrieved context, judge explanations, and successful-sample bootstrap intervals. It rejects known gold metadata in collection payloads and refuses to overwrite earlier run directories. Time includes judging; token/cost metrics are unavailable. Sampling seeds do not make model outputs deterministic.

Validation: all 44 unit/integration tests passed locally, including the new artifact failure/invalid-score checks; black and ruff pass. No provider-backed benchmark was run because generation/judge keys were not configured in the workspace. No comparative accuracy or latency claims are supported by these tests. Architecture documentation was corrected to describe the current evidence-snippet loader, optional live CI gate, and implementation limits.
