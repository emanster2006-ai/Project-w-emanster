"""
DeepEval evaluation harness — runs the full RAG pipeline against the golden dataset
and collects per-question metric scores.

Usage:
    from evaluation.harness import EvalHarness
    harness = EvalHarness()
    results = harness.run(n=20)
"""

import asyncio
import json
import logging
import os
import time
from dataclasses import asdict, dataclass, field
from pathlib import Path

from deepeval.metrics import (
    AnswerRelevancyMetric,
    ContextualPrecisionMetric,
    FaithfulnessMetric,
)
from deepeval.test_case import LLMTestCase

logger = logging.getLogger(__name__)

GOLDEN_DATASET_PATH = Path("evaluation/golden_dataset.json")
RESULTS_PATH = Path("evaluation/eval_results.json")

JUDGE_MODEL = os.getenv("EVAL_JUDGE_MODEL", "gpt-4o-mini")
FAITHFULNESS_THRESHOLD = float(os.getenv("FAITHFULNESS_THRESHOLD", "0.75"))
PRECISION_THRESHOLD = float(os.getenv("CONTEXTUAL_PRECISION_THRESHOLD", "0.70"))
RELEVANCY_THRESHOLD = float(os.getenv("ANSWER_RELEVANCY_THRESHOLD", "0.75"))


@dataclass
class QuestionResult:
    question: str
    answer: str
    expected_answer: str
    retrieval_context: list[str]
    faithfulness: float = 0.0
    contextual_precision: float = 0.0
    answer_relevancy: float = 0.0
    latency_ms: float = 0.0
    passed: bool = False


@dataclass
class HarnessResult:
    n_questions: int = 0
    mean_faithfulness: float = 0.0
    mean_contextual_precision: float = 0.0
    mean_answer_relevancy: float = 0.0
    pass_rate: float = 0.0
    questions: list[QuestionResult] = field(default_factory=list)


class EvalHarness:
    def __init__(self):
        self.metrics = [
            FaithfulnessMetric(
                threshold=FAITHFULNESS_THRESHOLD, model=JUDGE_MODEL, include_reason=True
            ),
            ContextualPrecisionMetric(
                threshold=PRECISION_THRESHOLD, model=JUDGE_MODEL, include_reason=True
            ),
            AnswerRelevancyMetric(
                threshold=RELEVANCY_THRESHOLD, model=JUDGE_MODEL, include_reason=True
            ),
        ]

    def _load_golden(self, n: int) -> list[dict]:
        if not GOLDEN_DATASET_PATH.exists():
            raise FileNotFoundError(
                f"{GOLDEN_DATASET_PATH} not found. Run: python scripts/generate_golden_dataset.py"
            )
        with open(GOLDEN_DATASET_PATH) as f:
            data = json.load(f)
        return data[:n]

    def _run_pipeline(self, question: str) -> tuple[str, list[dict], float]:
        """Run the full RAG pipeline synchronously for eval."""
        from generation.llm import generate_answer
        from retrieval.hybrid import hybrid_search
        from retrieval.hyde import generate_hypothetical_doc
        from retrieval.reranker import rerank

        start = time.time()

        hypo_doc = asyncio.run(generate_hypothetical_doc(question))
        chunks = asyncio.run(hybrid_search(hypo_doc, top_k=20))
        reranked = rerank(question, chunks, top_k=5)
        answer = asyncio.run(generate_answer(question, reranked))

        latency_ms = (time.time() - start) * 1000
        return answer, reranked, latency_ms

    def run(self, n: int = 20, save_results: bool = True) -> HarnessResult:
        """Run evaluation on n questions from the golden dataset."""
        golden = self._load_golden(n)
        logger.info(f"Running eval on {len(golden)} questions with judge={JUDGE_MODEL}")

        question_results = []

        for i, item in enumerate(golden):
            question = item["question"]
            expected = item.get("answer", item.get("ground_truth", ""))

            logger.info(f"[{i+1}/{len(golden)}] {question[:80]}...")

            try:
                answer, chunks, latency_ms = self._run_pipeline(question)
                context_texts = [c["text"] for c in chunks]

                test_case = LLMTestCase(
                    input=question,
                    actual_output=answer,
                    expected_output=expected,
                    retrieval_context=context_texts,
                )

                f_metric, p_metric, r_metric = self.metrics
                f_metric.measure(test_case)
                p_metric.measure(test_case)
                r_metric.measure(test_case)

                passed = (
                    f_metric.score >= FAITHFULNESS_THRESHOLD
                    and p_metric.score >= PRECISION_THRESHOLD
                    and r_metric.score >= RELEVANCY_THRESHOLD
                )

                question_results.append(
                    QuestionResult(
                        question=question,
                        answer=answer,
                        expected_answer=expected,
                        retrieval_context=context_texts,
                        faithfulness=f_metric.score,
                        contextual_precision=p_metric.score,
                        answer_relevancy=r_metric.score,
                        latency_ms=latency_ms,
                        passed=passed,
                    )
                )

            except Exception as e:  # noqa: BLE001
                logger.error(f"Failed on question {i+1}: {e}")
                question_results.append(
                    QuestionResult(
                        question=question,
                        answer="ERROR",
                        expected_answer=expected,
                        retrieval_context=[],
                        passed=False,
                    )
                )

        result = HarnessResult(
            n_questions=len(question_results),
            mean_faithfulness=sum(q.faithfulness for q in question_results)
            / len(question_results),
            mean_contextual_precision=sum(
                q.contextual_precision for q in question_results
            )
            / len(question_results),
            mean_answer_relevancy=sum(q.answer_relevancy for q in question_results)
            / len(question_results),
            pass_rate=sum(q.passed for q in question_results) / len(question_results),
            questions=question_results,
        )

        if save_results:
            with open(RESULTS_PATH, "w") as f:
                json.dump(asdict(result), f, indent=2, default=str)
            logger.info(f"Results saved to {RESULTS_PATH}")

        logger.info(
            f"Eval complete | Faithfulness={result.mean_faithfulness:.3f} "
            f"Precision={result.mean_contextual_precision:.3f} "
            f"Relevancy={result.mean_answer_relevancy:.3f} "
            f"Pass={result.pass_rate:.1%}"
        )

        return result
