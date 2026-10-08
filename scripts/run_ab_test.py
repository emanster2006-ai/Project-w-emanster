"""
A/B test runner — compare multiple pipeline configurations.
Reports metrics with bootstrapped confidence intervals.
Run: python scripts/run_ab_test.py
"""

import json
import os
import sys

import numpy as np

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from dotenv import load_dotenv

load_dotenv()

import logging

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


def bootstrap_ci(
    scores: list[float], n_bootstrap: int = 1000, ci: float = 0.95
) -> tuple:
    """Compute bootstrap confidence interval for a list of scores."""
    arr = np.array(scores)
    bootstrap_means = [
        np.mean(np.random.choice(arr, size=len(arr), replace=True))
        for _ in range(n_bootstrap)
    ]
    lower = np.percentile(bootstrap_means, (1 - ci) / 2 * 100)
    upper = np.percentile(bootstrap_means, (1 + ci) / 2 * 100)
    return float(np.mean(arr)), float(lower), float(upper)


CONFIGURATIONS = [
    {"name": "baseline_dense_only", "hyde": False, "rerank": False, "hybrid": False},
    {"name": "dense_plus_rerank", "hyde": False, "rerank": True, "hybrid": False},
    {"name": "hybrid_only", "hyde": False, "rerank": False, "hybrid": True},
    {"name": "hybrid_plus_rerank", "hyde": False, "rerank": True, "hybrid": True},
    {"name": "hyde_plus_hybrid_rerank", "hyde": True, "rerank": True, "hybrid": True},
]


def run_ab_test():
    from deepeval.metrics import (
        AnswerRelevancyMetric,
        ContextualPrecisionMetric,
        FaithfulnessMetric,
    )
    from deepeval.test_case import LLMTestCase

    with open("evaluation/golden_dataset.json") as f:
        golden = json.load(f)

    sample = golden[:20]  # Use 20 questions for A/B test (cost control)
    results_summary = []

    for config in CONFIGURATIONS:
        logger.info(f"\nRunning config: {config['name']}")

        # Set environment flags for this config
        os.environ["ENABLE_HYDE"] = str(config["hyde"]).lower()
        os.environ["ENABLE_HYBRID_RETRIEVAL"] = str(config["hybrid"]).lower()

        faithfulness_scores = []
        precision_scores = []
        relevancy_scores = []

        for item in sample:
            # Inline sync query for A/B test (not streaming)
            import asyncio

            from generation.llm import generate_answer
            from retrieval.hybrid import hybrid_search
            from retrieval.hyde import generate_hypothetical_doc
            from retrieval.reranker import rerank

            question = item["question"]
            query = question

            if config["hyde"]:
                query = asyncio.run(generate_hypothetical_doc(question))

            if config["hybrid"]:
                chunks = asyncio.run(hybrid_search(query, top_k=20))
            else:
                from ingestion.embedder import embed_texts
                from retrieval.vectorstore import dense_search

                vec = embed_texts([query], normalize=True)[0]
                chunks = dense_search(vec, top_k=20)

            if config["rerank"]:
                chunks = rerank(question, chunks, top_k=5)
            else:
                chunks = chunks[:5]

            answer = asyncio.run(generate_answer(question, chunks))
            context_texts = [c["text"] for c in chunks]

            # Score with DeepEval
            test_case = LLMTestCase(
                input=question,
                actual_output=answer,
                expected_output=item.get("answer", ""),
                retrieval_context=context_texts,
            )

            f_metric = FaithfulnessMetric(threshold=0.5, model="gpt-4o-mini")
            p_metric = ContextualPrecisionMetric(threshold=0.5, model="gpt-4o-mini")
            r_metric = AnswerRelevancyMetric(threshold=0.5, model="gpt-4o-mini")

            f_metric.measure(test_case)
            p_metric.measure(test_case)
            r_metric.measure(test_case)

            faithfulness_scores.append(f_metric.score)
            precision_scores.append(p_metric.score)
            relevancy_scores.append(r_metric.score)

        f_mean, f_lo, f_hi = bootstrap_ci(faithfulness_scores)
        p_mean, p_lo, p_hi = bootstrap_ci(precision_scores)
        r_mean, r_lo, r_hi = bootstrap_ci(relevancy_scores)

        config_result = {
            "config": config["name"],
            "faithfulness": {"mean": f_mean, "ci_95": [f_lo, f_hi]},
            "contextual_precision": {"mean": p_mean, "ci_95": [p_lo, p_hi]},
            "answer_relevancy": {"mean": r_mean, "ci_95": [r_lo, r_hi]},
        }
        results_summary.append(config_result)
        logger.info(json.dumps(config_result, indent=2))

    # Save results
    with open("evaluation/ab_test_results.json", "w") as f:
        json.dump(results_summary, f, indent=2)

    print("\n" + "=" * 60)
    print("A/B TEST RESULTS SUMMARY")
    print("=" * 60)
    for r in results_summary:
        print(f"\n{r['config']}:")
        print(
            f"  Faithfulness:    {r['faithfulness']['mean']:.3f} "
            f"[{r['faithfulness']['ci_95'][0]:.3f}, {r['faithfulness']['ci_95'][1]:.3f}]"
        )
        print(
            f"  Precision:       {r['contextual_precision']['mean']:.3f} "
            f"[{r['contextual_precision']['ci_95'][0]:.3f}, {r['contextual_precision']['ci_95'][1]:.3f}]"
        )
        print(
            f"  Relevancy:       {r['answer_relevancy']['mean']:.3f} "
            f"[{r['answer_relevancy']['ci_95'][0]:.3f}, {r['answer_relevancy']['ci_95'][1]:.3f}]"
        )


if __name__ == "__main__":
    run_ab_test()
