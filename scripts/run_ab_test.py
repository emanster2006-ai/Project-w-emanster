"""Compare pipeline variants and preserve reproducible per-question evidence."""

import argparse
import asyncio
import importlib.metadata
import json
import os
from pathlib import Path
import subprocess
import sys
from datetime import datetime, timezone

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from evaluation.ab_test import PIPELINE_CONFIGS
from evaluation.benchmark import digest, run_suite, select_questions


def evaluate(config, row):
    from deepeval.metrics import (
        FaithfulnessMetric,
        ContextualPrecisionMetric,
        AnswerRelevancyMetric,
    )
    from deepeval.test_case import LLMTestCase
    from retrieval.hybrid import hybrid_search
    from retrieval.reranker import rerank
    from retrieval.hyde import generate_hypothetical_doc
    from generation.llm import generate_answer
    from ingestion.embedder import embed_texts
    from retrieval.vectorstore import dense_search

    question = row["question"]
    query = (
        asyncio.run(generate_hypothetical_doc(question)) if config["hyde"] else question
    )
    chunks = (
        asyncio.run(hybrid_search(query, top_k=20))
        if config["hybrid"]
        else dense_search(embed_texts([query], normalize=True)[0], top_k=20)
    )
    chunks = rerank(question, chunks, top_k=5) if config["rerank"] else chunks[:5]
    if not chunks:
        raise ValueError("No retrieved evidence")
    answer = asyncio.run(generate_answer(question, chunks))
    case = LLMTestCase(
        input=question,
        actual_output=answer,
        expected_output=row["answer"],
        retrieval_context=[chunk["text"] for chunk in chunks],
    )
    scores, reasons = {}, {}
    for name, cls in [
        ("faithfulness", FaithfulnessMetric),
        ("contextual_precision", ContextualPrecisionMetric),
        ("answer_relevancy", AnswerRelevancyMetric),
    ]:
        metric = cls(threshold=0.5, model=os.getenv("JUDGE_MODEL", "gpt-4o-mini"))
        metric.measure(case)
        scores[name], reasons[name] = metric.score, metric.reason
    return {
        "answer": answer,
        "retrieved_sources": chunks,
        "scores": scores,
        "judge_reasons": reasons,
    }


def check_collection():
    """Fingerprint the actual corpus and reject known gold-metadata leakage."""
    from retrieval.vectorstore import get_vectorstore, COLLECTION

    client = get_vectorstore()
    offset, payloads = None, []
    while True:
        points, offset = client.scroll(
            collection_name=COLLECTION,
            offset=offset,
            limit=256,
            with_payload=True,
            with_vectors=False,
        )
        for point in points:
            payload = point.payload or {}
            if any(
                key in payload
                for key in ("question", "answer", "gold_answer", "expected_answer")
            ):
                raise ValueError(
                    "Gold metadata in collection; rebuild a fresh evidence-only collection"
                )
            payloads.append(json.dumps(payload, sort_keys=True))
        if offset is None:
            break
    if not payloads:
        raise ValueError("Collection contains no evidence")
    return {
        "collection": COLLECTION,
        "point_count": len(payloads),
        "payload_sha256": digest("\n".join(sorted(payloads)).encode()),
    }


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--dataset", type=Path, default=Path("evaluation/golden_dataset.json")
    )
    parser.add_argument("--limit", type=int, default=20)
    parser.add_argument("--seed", type=int, default=42)
    parser.add_argument("--output", type=Path)
    parser.add_argument(
        "--preflight",
        action="store_true",
        help="Validate dataset and credentials; make no network calls",
    )
    args = parser.parse_args()
    try:
        from dotenv import load_dotenv

        load_dotenv()
    except ImportError:
        pass
    raw = args.dataset.read_bytes()
    questions = select_questions(json.loads(raw), args.limit, args.seed)
    provider = os.getenv("LLM_PROVIDER", "groq")
    if provider not in ("groq", "openai"):
        parser.error("LLM_PROVIDER must be groq or openai")
    required = (
        ["OPENAI_API_KEY", "GROQ_API_KEY"] if provider == "groq" else ["OPENAI_API_KEY"]
    )
    missing = [
        key
        for key in required
        if not os.getenv(key) or os.getenv(key).startswith("your_")
    ]
    if missing:
        parser.error("Missing configured credentials: " + ", ".join(missing))
    if not os.getenv("LLM_MODEL"):
        parser.error("Set LLM_MODEL to a currently available provider model")
    if args.preflight:
        print(
            f"Dataset valid: {len(questions)} selected questions; required credentials are set. No provider/service calls made."
        )
        return
    corpus = check_collection()
    revision = subprocess.check_output(["git", "rev-parse", "HEAD"], text=True).strip()
    dirty = bool(
        subprocess.check_output(["git", "status", "--porcelain"], text=True).strip()
    )
    packages = {}
    for name in (
        "deepeval",
        "groq",
        "openai",
        "sentence-transformers",
        "qdrant-client",
    ):
        packages[name] = importlib.metadata.version(name)
    metadata = {
        "dataset_sha256": digest(raw),
        "git_revision": revision,
        "working_tree_dirty": dirty,
        "provider": provider,
        "generation_model": os.environ["LLM_MODEL"],
        "judge_model": os.getenv("JUDGE_MODEL", "gpt-4o-mini"),
        "packages": packages,
        "embedding_model": os.getenv(
            "EMBEDDING_MODEL", "sentence-transformers/all-MiniLM-L6-v2"
        ),
        "reranker_model": "cross-encoder/ms-marco-MiniLM-L-6-v2",
        "corpus": corpus,
        "retrieval_top_k": 20,
        "context_top_k": 5,
        "decomposition": False,
        "generation_max_tokens": 1000,
        "generation_temperature": "provider default; not fixed",
        "model_revisions": "model names only; immutable revisions not captured",
    }
    configs = [vars(config) for config in PIPELINE_CONFIGS]
    output = args.output or Path("evaluation/runs") / datetime.now(
        timezone.utc
    ).strftime("%Y%m%dT%H%M%S%fZ")
    summary = run_suite(questions, configs, evaluate, output, metadata, args.seed)
    print(json.dumps(summary, indent=2))
    print(f"Artifacts: {output}")
    if any(item["failed"] for item in summary):
        raise SystemExit(1)


if __name__ == "__main__":
    main()
