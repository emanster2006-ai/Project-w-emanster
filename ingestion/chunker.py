"""
Hierarchical chunking for SEC 10-K filings.
Standard character-overlap chunking shreds financial tables — this doesn't.
"""

from llama_index.core.node_parser import (
    HierarchicalNodeParser,
    SentenceSplitter,
)
from llama_index.core import Document
from llama_index.core.schema import BaseNode
from typing import Any
import re
import logging

logger = logging.getLogger(__name__)

# Chunk sizes: parent → child → grandchild
CHUNK_SIZES = [2048, 512, 256]


def build_hierarchical_parser() -> HierarchicalNodeParser:
    """
    Three-level hierarchy preserves document context at multiple granularities.
    Parent chunks: for broad context
    Child chunks: for precise retrieval
    """
    return HierarchicalNodeParser.from_defaults(
        chunk_sizes=CHUNK_SIZES,
        chunk_overlap=64,
    )


def inject_metadata(doc: Document, metadata: dict[str, Any]) -> Document:
    """Inject document-level metadata into every chunk's payload."""
    doc.metadata.update(metadata)
    return doc


def extract_section_header(text: str) -> str | None:
    """Detect SEC filing section headers (e.g., 'ITEM 1A. RISK FACTORS')."""
    pattern = r"^(ITEM\s+\d+[A-Z]?\.\s+[A-Z\s]+)$"
    for line in text.split("\n")[:5]:
        match = re.match(pattern, line.strip())
        if match:
            return match.group(1).strip()
    return None


def chunk_documents(documents: list[Document]) -> list[BaseNode]:
    """
    Parse documents into hierarchical nodes.
    Each node inherits: company, ticker, year, filing_type, section.
    """
    parser = build_hierarchical_parser()
    all_nodes = []

    for doc in documents:
        nodes = parser.get_nodes_from_documents([doc])
        for node in nodes:
            # Propagate metadata to all child nodes
            node.metadata.update(doc.metadata)
            # Try to extract section header from chunk text
            section = extract_section_header(node.get_content())
            if section:
                node.metadata["section"] = section
        all_nodes.extend(nodes)

    logger.info(f"Produced {len(all_nodes)} nodes from {len(documents)} documents")
    return all_nodes
