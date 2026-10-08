"""Unit tests for hierarchical chunker."""

from llama_index.core import Document

from ingestion.chunker import chunk_documents


def test_chunker_produces_nodes():
    docs = [
        Document(text="Apple Inc. reported revenue of $394 billion in FY2022. " * 50)
    ]
    nodes = chunk_documents(docs)
    assert len(nodes) > 0


def test_metadata_injected_into_all_nodes():
    metadata = {"company": "Apple", "ticker": "AAPL", "year": "2022"}
    doc = Document(text="Some financial text. " * 100, metadata=metadata)
    nodes = chunk_documents([doc])
    for node in nodes:
        assert node.metadata.get("company") == "Apple"
        assert node.metadata.get("ticker") == "AAPL"


def test_no_empty_chunks():
    docs = [Document(text="Short document with minimal content.")]
    nodes = chunk_documents(docs)
    for node in nodes:
        assert len(node.get_content().strip()) > 0
