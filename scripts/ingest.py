"""
One-shot ingestion script.
Run: python scripts/ingest.py
     python scripts/ingest.py --sample-only   (for CI — uses 50 docs)
     python scripts/ingest.py --limit 500     (partial ingest)
"""

import argparse
import logging
import sys
import os

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from dotenv import load_dotenv
load_dotenv()

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
logger = logging.getLogger(__name__)


def run_ingestion(source: str = "financebench", limit: int | None = None):
    from ingestion.loader import load_financebench
    from ingestion.chunker import chunk_documents
    from retrieval.vectorstore import upsert_nodes
    import json

    logger.info(f"Starting ingestion: source={source}, limit={limit}")

    # 1. Load documents
    documents, qa_pairs = load_financebench(limit=limit)
    logger.info(f"Loaded {len(documents)} documents")

    # 2. Hierarchical chunking
    nodes = chunk_documents(documents)
    logger.info(f"Chunked into {len(nodes)} nodes")

    # 3. Upsert into Qdrant (with L2-normalized dense vectors)
    upsert_nodes(nodes)
    logger.info("Upsert complete")

    # 4. Save raw QA pairs for golden dataset generation
    if qa_pairs:
        os.makedirs("data", exist_ok=True)
        with open("data/raw_qa_pairs.json", "w") as f:
            json.dump(qa_pairs, f, indent=2)
        logger.info(f"Saved {len(qa_pairs)} QA pairs to data/raw_qa_pairs.json")

    logger.info("Ingestion complete")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Ingest FinanceBench into Qdrant")
    parser.add_argument("--limit", type=int, default=None, help="Max documents to ingest")
    parser.add_argument("--sample-only", action="store_true", help="Ingest 50 docs (for CI)")
    args = parser.parse_args()

    limit = 50 if args.sample_only else args.limit
    run_ingestion(limit=limit)
