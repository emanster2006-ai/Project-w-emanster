# Benchmark status and protocol

No comparative results have been published. Do not use accuracy-improvement percentages in a resume until the run artifacts support them.

Before measuring: validate ingestion and golden-dataset generation against the pinned dependencies; freeze a held-out FinanceBench question set and preserve source document IDs. Ingest only the corresponding evidence, never the expected answers as retrieval documents. Keep synthetic training or tuning questions separate from the held-out set.

Compare dense-only, dense plus reranking, hybrid-only, hybrid plus reranking, and HyDE plus hybrid plus reranking using identical questions, corpus, model versions, generation settings, and retrieval limits. Disable the cache for each configuration. Record per-question answers, citations, errors, latency, token usage, provider cost, and judge explanations. Publish the dataset provenance, configuration, date, sample size, and bootstrapped confidence intervals alongside aggregates. Report failed queries, not just successful ones.

Inspect a sample manually for citation correctness and unsupported claims. LLM-judge faithfulness and relevance are proxies, not proof of numerical financial correctness. A small evidence-snippet corpus does not establish performance over complete filings.

The existing evaluation and synthetic-generation scripts need end-to-end verification. Deterministic HTTP contract tests do not replace this benchmark.

Existing Qdrant collections built by older versions may contain gold question/answer metadata. Build a fresh collection with the corrected loader before evaluating, switch QDRANT_COLLECTION_NAME to it, and restart the API to refresh the in-memory BM25 index. Reusing an old collection preserves the leakage this change removes. Do not delete a shared or production collection without reviewing its use.

## Run and preserve the comparison

From the repo root, after installing `requirements.txt`, configure provider keys privately and set `LLM_MODEL` to a model currently available from that provider. The historical example model may have been retired. Groq generation requires both `GROQ_API_KEY` and `OPENAI_API_KEY` (the latter for the judge); OpenAI generation uses `OPENAI_API_KEY`. `JUDGE_MODEL` defaults to `gpt-4o-mini`.

```sh
# Ingest into a NEW, dedicated evidence-only collection, then freeze questions.
export QDRANT_COLLECTION_NAME=financebench_eval_20261018
python scripts/ingest.py
python scripts/prepare_eval_dataset.py
# Checks dataset and key presence only; does not validate provider authorization.
python scripts/run_ab_test.py --preflight --limit 20 --seed 42
# Makes billable/provider calls. Start with a small run after confirming model availability.
python scripts/run_ab_test.py --limit 20 --seed 42 --output /tmp/secure-rag-benchmark
```

The output path must not exist. Each question runs through all five configurations in a seeded shuffled order. Cache and decomposition are bypassed. Each attempt is flushed to `attempts.jsonl`, so errors and interrupted runs remain inspectable. A completed run produces `summary.json`; a failed attempt causes exit code 1. Keep partial runs as partial runs, not completed comparisons.

Artifacts:

- `manifest.json`: dataset hash, selected question IDs, seed, configs, corpus payload hash/count, Git revision/dirty state, model names, and installed package versions.
- `questions.json`: exact selected question/expected-answer pairs; never ingest this file.
- `attempts.jsonl`: answers, retrieved context, scores, judge explanations, error types, and total attempt time.
- `summary.json`: attempted/successful/failed counts and seeded bootstrap intervals for successful judge scores.

Intervals are per configuration, not paired improvement intervals or proof of statistical significance. Total attempt time includes judging and initialization on the first attempt; it must not be presented as user-facing latency. Token usage and cost are explicitly null because the current generation wrappers do not expose them. Retrieved context is not proof of correct citations. Review generated text and judge reasons for sensitive content before publishing artifacts; never include credentials or private prompts. Preserve the original FinanceBench revision/license/provenance separately. Hashes identify the actual selected dataset and payloads but do not substitute for those records or immutable model revisions.

## Current evidence

The artifact runner is tested locally with controlled evaluators, including failure preservation, invalid scores, duplicate questions, seeded sampling, and overwrite refusal. These tests are not a FinanceBench result. No live provider comparison was run in the portfolio enhancement session: provider keys were not configured in that environment. Accuracy, end-user latency, cost, and relative improvement remain unmeasured.
