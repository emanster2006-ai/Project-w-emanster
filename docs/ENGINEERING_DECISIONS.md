# SecureRAG: decisions and evidence limits

This is a team project. Emmanuel's focus is frontend, API integration, deployment, and CI/CD; Erik's focus is retrieval, evaluation, and ML. These notes describe repository behavior, not sole authorship of every component.

## Treat retrieval improvements as hypotheses

Dense retrieval, BM25 fusion, reranking, and HyDE offer different tradeoffs. HyDE adds a generation call; reranking adds candidate-scoring work. Better retrieval is a hypothesis until the same held-out questions and corpus are measured across configurations. The A/B runner compares five variants using top-20 candidates and top-5 generation contexts, bypassing the HTTP semantic cache.

Questions and configuration order use a fixed seed. The runner saves question snapshots and IDs, dataset/corpus hashes, model names, package versions, source revision, raw attempts, judge reasons, and successful-sample confidence intervals. Failures stay visible in the denominator and cause a nonzero exit. Retrieval, generation, and judge time are combined; this is not an API latency benchmark. Token usage and cost remain unavailable from the current wrappers.

## Keep expected answers outside the retrieval corpus

The FinanceBench loader places company, year, filing type, and source metadata on evidence snippets. Gold questions and answers are saved separately for evaluation. Older collections can retain leaked metadata even after code is fixed, so use a fresh evidence-only collection and restart the API's cached BM25 index. The benchmark scans and fingerprints payloads before running, rejecting known gold-answer fields.

A clean metadata scan does not establish that a corpus is a faithful copy of full filings. This loader uses evidence snippets; conclusions must say so. Keep tuning/synthetic questions separate from held-out evaluation and preserve the dataset revision and original source provenance.

## Make privacy boundaries explicit

The API passes sanitized questions into retrieval/generation, avoids sharing PII-bearing responses through the semantic cache, and traces sanitized answers. Deterministic route tests substitute external components to check wiring; they do not prove detection quality or resistance to arbitrary prompt injection. Regex controls and Presidio have limits. Never equate a green contract test with a security certification.

## Separate local checks, live evaluation, and deployment

Ordinary CI runs deterministic API tests, real chunker/Presidio unit tests, formatting/lint, and the frontend build. Live judge evaluation is explicitly dispatched with provider keys. A built frontend and a liveness response do not establish that the full hosted retrieval/generation flow works. Published benchmark claims must link to measured artifacts and manually inspected failures.
