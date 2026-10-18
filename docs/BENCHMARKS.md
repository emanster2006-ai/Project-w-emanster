# Benchmark status and protocol

No comparative results have been published. Do not use accuracy-improvement percentages in a resume until the run artifacts support them.

Before measuring: validate ingestion and golden-dataset generation against the pinned dependencies; freeze a held-out FinanceBench question set and preserve source document IDs. Ingest only the corresponding evidence, never the expected answers as retrieval documents. Keep synthetic training or tuning questions separate from the held-out set.

Compare dense-only, dense plus reranking, hybrid-only, hybrid plus reranking, and HyDE plus hybrid plus reranking using identical questions, corpus, model versions, generation settings, and retrieval limits. Disable the cache for each configuration. Record per-question answers, citations, errors, latency, token usage, provider cost, and judge explanations. Publish the dataset provenance, configuration, date, sample size, and bootstrapped confidence intervals alongside aggregates. Report failed queries, not just successful ones.

Inspect a sample manually for citation correctness and unsupported claims. LLM-judge faithfulness and relevance are proxies, not proof of numerical financial correctness. A small evidence-snippet corpus does not establish performance over complete filings.

The existing evaluation and synthetic-generation scripts need end-to-end verification. Deterministic HTTP contract tests do not replace this benchmark.

Existing Qdrant collections built by older versions may contain gold question/answer metadata. Build a fresh collection with the corrected loader before evaluating, switch QDRANT_COLLECTION_NAME to it, and restart the API to refresh the in-memory BM25 index. Reusing an old collection preserves the leakage this change removes. Do not delete a shared or production collection without reviewing its use.

## Input guard check (offline, 2026-10-18)

`python scripts/guard_benchmark.py` runs `security/input_guard.py` alone, with no services or keys. It is a regression signal on small hand-written sets, not a security guarantee, and it does not cover PII handling, retrieval or answer quality.

| Set | Result |
| --- | --- |
| Repo adversarial cases (`evaluation/adversarial.py`) | 10/10 blocked |
| Paraphrase/French/base64/extraction attacks (6) | 6/6 blocked, but the guard's second layer was tuned on this set, so it is no longer held out |
| Unseen attacks written afterwards, not tuned against (8) | 1/8 blocked |
| Benign financial questions (15) | 15/15 passed, no false positives |

Before this change 3 of the 10 repo adversarial cases were not blocked. The unseen-set result is the honest generalization estimate: the regex and keyword layers (plus base64 decoding and fr/es/de patterns) catch known phrasings only. Closing the gap needs an embedding-similarity classifier or an LLM-based check; neither could be built or tested in the offline environment used here (model downloads were blocked).
