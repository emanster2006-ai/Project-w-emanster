"""
FinanceBench document loader.
Downloads from HuggingFace hub, parses PDF SEC filings, injects metadata.
"""

from datasets import load_dataset
from llama_index.core import Document
from unstructured.partition.pdf import partition_pdf
import os
import tempfile
import logging
from pathlib import Path

logger = logging.getLogger(__name__)

FINANCEBENCH_DATASET = "PatronusAI/financebench"


def load_financebench(limit: int | None = None) -> tuple[list[Document], list[dict]]:
    """
    Load FinanceBench documents from HuggingFace.
    Returns: (llama_index Documents, raw QA pairs for golden dataset generation)
    """
    logger.info("Downloading FinanceBench from HuggingFace...")
    dataset = load_dataset(FINANCEBENCH_DATASET, split="train")

    if limit:
        dataset = dataset.select(range(min(limit, len(dataset))))

    documents = []
    qa_pairs = []

    for row in dataset:
        # Build metadata payload — injected into every chunk
        metadata = {
            "company": row.get("company"),
            "ticker": row.get("ticker"),
            "year": str(row.get("fiscal_year", "")),
            "filing_type": row.get("doc_type", "10-K"),
            "question": row.get("question"),        # for golden dataset
            "answer": row.get("answer"),
            "source": row.get("doc_name", ""),
        }

        doc_text = row.get("evidence_text") or row.get("page_text") or ""
        if not doc_text.strip():
            continue

        doc = Document(text=doc_text, metadata=metadata)
        documents.append(doc)

        # Collect Q&A pairs for golden dataset
        if row.get("question") and row.get("answer"):
            qa_pairs.append({
                "question": row["question"],
                "answer": row["answer"],
                "company": metadata["company"],
                "year": metadata["year"],
                "source": metadata["source"],
            })

    logger.info(f"Loaded {len(documents)} documents, {len(qa_pairs)} QA pairs")
    return documents, qa_pairs
