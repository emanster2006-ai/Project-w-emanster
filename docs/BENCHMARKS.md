# Benchmark status and protocol

No comparative results have been published. Do not use accuracy-improvement percentages in a resume until the run artifacts support them.

Before measuring: validate ingestion and golden-dataset generation against the pinned dependencies; freeze a held-out FinanceBench question set and preserve source document IDs. Ingest only the corresponding evidence, never the expected answers as retrieval documents. Keep synthetic training or tuning questions separate from the held-out set.

Compare dense-only, dense plus reranking, hybrid-only, hybrid plus reranking, and HyDE plus hybrid plus reranking using identical questions, corpus, model versions, generation settings, and retrieval limits. Disable the cache for each configuration. Record per-question answers, citations, errors, latency, token usage, provider cost, and judge explanations. Publish the dataset provenance, configuration, date, sample size, and bootstrapped confidence intervals alongside aggregates. Report failed queries, not just successful ones.

Inspect a sample manually for citation correctness and unsupported claims. LLM-judge faithfulness and relevance are proxies, not proof of numerical financial correctness. A small evidence-snippet corpus does not establish performance over complete filings.

The existing evaluation and synthetic-generation scripts need end-to-end verification. Deterministic HTTP contract tests do not replace this benchmark.
