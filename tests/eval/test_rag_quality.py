"""
DeepEval RAG quality gate — runs in CI on every PR to main.
Build FAILS if scores drop below thresholds in .env.
"""

import pytest
import json
import os
import asyncio
from deepeval import assert_test
from deepeval.metrics import (
    FaithfulnessMetric,
    ContextualPrecisionMetric,
    ContextualRecallMetric,
    AnswerRelevancyMetric,
)
from deepeval.test_case import LLMTestCase
from deepeval.dataset import EvaluationDataset


FAITHFULNESS_THRESHOLD = float(os.getenv("FAITHFULNESS_THRESHOLD", 0.75))
PRECISION_THRESHOLD = float(os.getenv("CONTEXTUAL_PRECISION_THRESHOLD", 0.70))
RELEVANCY_THRESHOLD = float(os.getenv("ANSWER_RELEVANCY_THRESHOLD", 0.75))


def load_test_cases(n: int = 10) -> list[LLMTestCase]:
    """Load golden dataset and run live queries for eval."""
    with open("evaluation/golden_dataset.json") as f:
        golden = json.load(f)

    sample = golden[:n]
    test_cases = []

    for item in sample:
        from retrieval.hybrid import hybrid_search
        from retrieval.reranker import rerank
        from retrieval.hyde import generate_hypothetical_doc
        from generation.llm import generate_answer

        question = item["question"]

        # Run live RAG pipeline
        hypo_doc = asyncio.run(generate_hypothetical_doc(question))
        chunks = asyncio.run(hybrid_search(hypo_doc, top_k=20))
        reranked = rerank(question, chunks, top_k=5)
        answer = asyncio.run(generate_answer(question, reranked))

        test_cases.append(LLMTestCase(
            input=question,
            actual_output=answer,
            expected_output=item.get("answer", ""),
            retrieval_context=[c["text"] for c in reranked],
        ))

    return test_cases


@pytest.mark.parametrize("test_case", load_test_cases(n=10))
def test_rag_faithfulness(test_case):
    """FAILS if answer contains claims not supported by retrieved context."""
    metric = FaithfulnessMetric(
        threshold=FAITHFULNESS_THRESHOLD,
        model="gpt-4o-mini",
        include_reason=True,
    )
    assert_test(test_case, [metric])


@pytest.mark.parametrize("test_case", load_test_cases(n=10))
def test_rag_contextual_precision(test_case):
    """FAILS if retrieval returns noisy, irrelevant chunks."""
    metric = ContextualPrecisionMetric(
        threshold=PRECISION_THRESHOLD,
        model="gpt-4o-mini",
        include_reason=True,
    )
    assert_test(test_case, [metric])


@pytest.mark.parametrize("test_case", load_test_cases(n=10))
def test_rag_answer_relevancy(test_case):
    """FAILS if answer doesn't directly address the question."""
    metric = AnswerRelevancyMetric(
        threshold=RELEVANCY_THRESHOLD,
        model="gpt-4o-mini",
        include_reason=True,
    )
    assert_test(test_case, [metric])
