"""Gold answers must never become retrievable document metadata."""

import importlib.util
import sys
from pathlib import Path
from types import ModuleType, SimpleNamespace


def test_loader_keeps_expected_answer_out_of_documents(monkeypatch):
    row = {
        "company": "Example",
        "doc_period": 2022,
        "doc_name": "example.pdf",
        "question": "What was revenue?",
        "answer": "PRIVATE GOLD ANSWER",
        "evidence": [{"evidence_text": "Revenue evidence passage"}],
    }
    datasets = ModuleType("datasets")
    datasets.load_dataset = lambda *a, **kw: [row]
    core = ModuleType("llama_index.core")
    core.Document = lambda **kw: SimpleNamespace(**kw)
    monkeypatch.setitem(sys.modules, "datasets", datasets)
    monkeypatch.setitem(sys.modules, "llama_index.core", core)
    spec = importlib.util.spec_from_file_location(
        "isolated_loader", Path("ingestion/loader.py")
    )
    loader = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(loader)
    docs, pairs = loader.load_financebench()
    assert docs[0].text == "Revenue evidence passage"
    assert "question" not in docs[0].metadata
    assert "answer" not in docs[0].metadata
    assert pairs[0]["answer"] == "PRIVATE GOLD ANSWER"
