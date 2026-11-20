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

## PII handling check (offline, 2026-10-18)

`python scripts/pii_benchmark.py` runs `security/pii_handler.py` with Presidio and `en_core_web_lg`; no services or keys. Small hand-written sets, a regression signal only.

| Check | Result |
| --- | --- |
| Planted PII removed and restored by rehydration (11 cases: email, card, phone, names, IBAN, IP, passport, account, SSN) | 10/11 |
| Benign financial questions left unchanged (8) | 8/8 |

The one miss is `123-45-6789`, a sequential value Presidio rejects as an invalid SSN; a realistic SSN (`078-05-1120`) is detected. Real tests with invalid-looking test SSNs will not be masked.

Before this change, Presidio's default entities masked fiscal years, quarters and regions: only 3 of 8 benign questions were left unchanged (e.g. "from 2020 to 2022" became `<DATE_TIME_0>`), which would also degrade retrieval. The handler now masks only person/account identifiers (`PII_ENTITIES`). Detection quality on real user text and non-English input is unmeasured.

## Retrieval benchmark (offline, 2026-11-20)

`python scripts/retrieval_benchmark.py` (or `make retrieval-bench`) needs no API keys or LLM calls. For each of the 150 FinanceBench questions it runs the real hybrid search and reranker and checks whether a returned chunk was cut from that question's evidence text. The corpus is the evidence snippets only (962 chunks), so a perfect system scores 100%; the numbers compare retrieval changes against each other and say nothing about complete filings.

| Change (all on the same 150 questions) | recall@20 (candidate pool) | recall@5 (after rerank) |
| --- | --- | --- |
| Before: chunk text only | 121/150 (80.7%) | 105/150 (70.0%) |
| **Company / period header added to each chunk** | **144/150 (96.0%)** | **135/150 (90.0%)** |
| Header + larger candidate pool (40) | 147/150 | 128/150 |
| Header + `ms-marco-MiniLM-L-12-v2` reranker | 144/150 | 133/150 |
| Header + `BAAI/bge-reranker-base` reranker | 144/150 | 130/150 |
| Header + a regex tokenizer for BM25 | 144/150 | 135/150 (no change, not adopted) |

Questions name the company and fiscal year, but evidence chunks rarely do, so retrieval could not match them. `retrieval/context.py` now prepends "company year filing" to each chunk for embedding, keyword search and reranking (stored text is unchanged). The larger pool and both alternative rerankers scored worse, so `ms-marco-MiniLM-L-6-v2` and a pool of 20 stay.

On a 38-question subset with the header in place, question-only retrieval, HyDE-only and question+HyDE (old and new HyDE prompts) all scored 35/38 at recall@5. HyDE showed no measurable retrieval benefit and costs a model call per query, so `use_hyde` now defaults to false.

**Re-ingest after upgrading.** Vectors in collections built before this change were embedded without the header. Build a fresh collection (see below) to get the full benefit; do not mix old and new points in one collection.

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
