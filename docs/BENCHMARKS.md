# Benchmark status and protocol

Measured results: retrieval (2026-11-20, below), end-to-end answer accuracy on all 150 FinanceBench questions (2026-11-27, below), and a counterfactual grounding benchmark ([COUNTERFACTUAL.md](COUNTERFACTUAL.md)). Each states its sample, setup and limits. The comparative A/B protocol further down has not been run with live providers.

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

### How many passages the model sees (`top_k`)

Same 150 questions, same index; only the number of reranked passages passed to the model changes:

| top_k | evidence in final context |
|---|---|
| 5 | 135/150 (90.0%) |
| **8 (new default)** | **142/150 (94.7%)** |
| 10 | 143/150 (95.3%) |

The candidate pool ceiling is 144/150. Going from 5 to 8 recovers cases like 3M FY2018 capex, where the right passage ranked 7th and the model correctly said "Insufficient context" because it never saw it. Going past 8 adds little for roughly 25% more prompt tokens, so the default is 8. Override with `TOP_K_RERANK` or the request's `top_k`.

### Fiscal-year bonus in the reranker

The cross-encoder rarely weighs the fiscal year in a question ("FY2018") against a chunk labelled 2022, so chunks from a year the question names get a score bonus (`RERANK_YEAR_BONUS`, default 3, `0` disables). Same 150 questions:

| bonus | top-5 | top-8 |
|---|---|---|
| 0 | 135/150 (90.0%) | 142/150 (94.7%) |
| 1 | 139/150 (92.7%) | 142/150 (94.7%) |
| 2 | 140/150 (93.3%) | 142/150 (94.7%) |
| **3 (default)** | **141/150 (94.0%)** | **143/150 (95.3%)** |
| 5 | 141/150 (94.0%) | 143/150 (95.3%) |

The bonus was chosen on these same 150 questions, so the gain may be slightly optimistic on unseen ones.

Two-digit years ("FY20 and FY21") are also recognised, which recovered one more question: top-8 143/150 to **144/150 (96.0%)**, top-5 unchanged at 141/150.

Tested and not adopted: an extra dense and BM25 search restricted to the named year's chunks. It raised the candidate pool from 144/150 to 148/150 (98.7%), but the reranker then dropped other evidence, so final top-5 (141/150) and top-8 (144/150) were unchanged while each question cost extra searches.

On a 38-question subset with the header in place, question-only retrieval, HyDE-only and question+HyDE (old and new HyDE prompts) all scored 35/38 at recall@5. HyDE showed no measurable retrieval benefit and costs a model call per query, so `use_hyde` now defaults to false.

**Re-ingest after upgrading.** Vectors in collections built before this change were embedded without the header. Build a fresh collection (see below) to get the full benefit; do not mix old and new points in one collection.

## End-to-end answer accuracy (2026-11-27)

`scripts/answer_accuracy.py` asks every FinanceBench question through the running API with the web UI's options (decomposition on, HyDE off, top 8), with the semantic cache disabled, and has a judge from a different model family label each answer against the FinanceBench reference as correct, incorrect or refused (the paper's three labels).

| | Result |
| --- | --- |
| **Correct, after hand review** | **120/150 = 80.0%** (95% Wilson interval 72.9-85.6%) |
| Incorrect / refused | 13 / 17 |
| Judge labels before hand review | 115/150 = 76.7% |
| When a chunk of the evidence passage was retrieved | 118/143 (82.5%) |
| When it was not | 2/7 |
| By question type | metrics-generated 45/50, domain-relevant 38/50, novel-generated 37/50 |

**Setup.** `gpt-oss-120b` (medium reasoning) served by Cerebras; judge `qwen/qwen3.8-27b` on Groq with reasoning off and temperature 0; collection `financebench_eval150_ctx`; code at commit `b23eba6`. No answer came from the cache and no request errored (one 500 was retried). Artifacts: [evaluation/results/answer-accuracy-2026-11-26](../evaluation/results/answer-accuracy-2026-11-26) (answers, judge grades with reasons, hand reviews, run metadata, summary).

**Hand review.** Every answer the judge labelled incorrect or refused (35) was checked against the reference by hand; 5 were changed to correct, all format or definition differences rather than different facts (for example -1.53% for a reference of -0.02 when rounding to two decimals, and $389 million for a reference of $0.40 billion). Two of those five are yes/no working-capital questions answered correctly with a broader working-capital definition than the reference's. 33 judge labels of correct were also spot-checked, with no false positives. Each review keeps the judge's original label next to the hand label (`reviews.jsonl`).

**What this does and does not show.** The corpus is FinanceBench's evidence excerpts, so this is accuracy when the relevant filing pages are in the index, not over complete filings. The judge is a proxy; the hand review covers every non-correct label but only a sample of correct ones. Most misses are refusals (17), several where the needed figure was retrieved but not used; the counterfactual benchmark shows the opposite failure, answering when the evidence is missing. Latency in the artifacts includes provider rate-limit waits and is not user-facing latency. An earlier partial run on Groq stopped at the free tier's daily limit and is not reported; all 150 answers here come from one provider.

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

The artifact runner is tested locally with controlled evaluators, including failure preservation, invalid scores, duplicate questions, seeded sampling, and overwrite refusal. These tests are not a FinanceBench result. The five-configuration A/B comparison has not been run with live providers; end-to-end accuracy for the shipped configuration is reported above, and end-user latency remains unmeasured.
