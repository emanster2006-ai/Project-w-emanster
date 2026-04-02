"""Integration tests for the query endpoint with mocked pipeline dependencies."""

from contextlib import asynccontextmanager
import sys
from types import ModuleType

from fastapi.testclient import TestClient

from api.main import create_app


class _DummySpan:
    def end(self, **kwargs):
        return None


class _DummyTrace:
    def span(self, **kwargs):
        return _DummySpan()

    def update(self, **kwargs):
        return None


class _DummyLangfuse:
    def trace(self, **kwargs):
        return _DummyTrace()

    def flush(self):
        return None


@asynccontextmanager
async def _test_lifespan(app):
    app.state.langfuse = _DummyLangfuse()
    yield


def _build_test_client():
    app = create_app()
    app.router.lifespan_context = _test_lifespan
    return TestClient(app)


def test_query_endpoint_returns_expected_payload(monkeypatch):
    async def fake_check_cache(_query):
        return None

    async def fake_set_cache(_query, _response):
        return None

    async def fake_decompose_query(_question):
        return ["What was Apple's revenue in FY2022?"]

    async def fake_generate_hypothetical_doc(question):
        return f"Hypothetical answer for {question}"

    async def fake_hybrid_search(_query, top_k=20):
        return [
            {
                "text": "Apple reported net sales of $394.3 billion in fiscal year 2022.",
                "metadata": {
                    "source": "AAPL_2022_10K.pdf",
                    "company": "Apple",
                    "year": "2022",
                    "section": "ITEM 8. FINANCIAL STATEMENTS",
                },
                "score": 0.87,
            }
        ]

    def fake_rerank(_question, chunks, top_k=5):
        return chunks[:top_k]

    async def fake_generate_answer(_question, _chunks):
        return "Apple reported $394.3 billion in FY2022 revenue."

    monkeypatch.setattr("api.middleware.cache.check_cache", fake_check_cache)
    monkeypatch.setattr("api.middleware.cache.set_cache", fake_set_cache)

    fake_decomposer_module = ModuleType("retrieval.decomposer")
    fake_decomposer_module.decompose_query = fake_decompose_query
    monkeypatch.setitem(sys.modules, "retrieval.decomposer", fake_decomposer_module)

    fake_hyde_module = ModuleType("retrieval.hyde")
    fake_hyde_module.generate_hypothetical_doc = fake_generate_hypothetical_doc
    monkeypatch.setitem(sys.modules, "retrieval.hyde", fake_hyde_module)

    fake_hybrid_module = ModuleType("retrieval.hybrid")
    fake_hybrid_module.hybrid_search = fake_hybrid_search
    monkeypatch.setitem(sys.modules, "retrieval.hybrid", fake_hybrid_module)

    fake_reranker_module = ModuleType("retrieval.reranker")
    fake_reranker_module.rerank = fake_rerank
    monkeypatch.setitem(sys.modules, "retrieval.reranker", fake_reranker_module)

    fake_vectorstore_module = ModuleType("retrieval.vectorstore")
    fake_vectorstore_module.get_vectorstore = lambda: object()
    monkeypatch.setitem(sys.modules, "retrieval.vectorstore", fake_vectorstore_module)

    fake_generation_module = ModuleType("generation.llm")
    fake_generation_module.generate_answer = fake_generate_answer
    monkeypatch.setitem(sys.modules, "generation.llm", fake_generation_module)

    with _build_test_client() as client:
        response = client.post(
            "/api/v1/query",
            json={
                "question": "What was Apple's revenue in FY2022?",
                "top_k": 5,
                "use_hyde": True,
                "use_decomposition": True,
                "stream": False,
            },
        )

    assert response.status_code == 200
    payload = response.json()
    assert payload["answer"] == "Apple reported $394.3 billion in FY2022 revenue."
    assert payload["cached"] is False
    assert payload["sub_questions"] == ["What was Apple's revenue in FY2022?"]
    assert len(payload["sources"]) == 1
    assert payload["sources"][0]["company"] == "Apple"
    assert payload["sources"][0]["source"] == "AAPL_2022_10K.pdf"


def test_query_endpoint_returns_cached_response(monkeypatch):
    async def fake_check_cache(_query):
        return {
            "answer": "Cached answer",
            "sources": [],
            "latency_ms": 12.5,
            "cached": False,
            "sub_questions": None,
        }

    monkeypatch.setattr("api.middleware.cache.check_cache", fake_check_cache)

    fake_decomposer_module = ModuleType("retrieval.decomposer")
    fake_decomposer_module.decompose_query = lambda _question: [_question]
    monkeypatch.setitem(sys.modules, "retrieval.decomposer", fake_decomposer_module)

    fake_hyde_module = ModuleType("retrieval.hyde")
    fake_hyde_module.generate_hypothetical_doc = lambda question: question
    monkeypatch.setitem(sys.modules, "retrieval.hyde", fake_hyde_module)

    fake_hybrid_module = ModuleType("retrieval.hybrid")
    fake_hybrid_module.hybrid_search = lambda _query, top_k=20: []
    monkeypatch.setitem(sys.modules, "retrieval.hybrid", fake_hybrid_module)

    fake_reranker_module = ModuleType("retrieval.reranker")
    fake_reranker_module.rerank = lambda _question, chunks, top_k=5: chunks[:top_k]
    monkeypatch.setitem(sys.modules, "retrieval.reranker", fake_reranker_module)

    fake_vectorstore_module = ModuleType("retrieval.vectorstore")
    fake_vectorstore_module.get_vectorstore = lambda: object()
    monkeypatch.setitem(sys.modules, "retrieval.vectorstore", fake_vectorstore_module)

    fake_generation_module = ModuleType("generation.llm")
    fake_generation_module.generate_answer = lambda _question, _chunks: "unused"
    monkeypatch.setitem(sys.modules, "generation.llm", fake_generation_module)

    with _build_test_client() as client:
        response = client.post(
            "/api/v1/query",
            json={"question": "What was Apple's revenue in FY2022?", "stream": False},
        )

    assert response.status_code == 200
    payload = response.json()
    assert payload["answer"] == "Cached answer"
    assert payload["cached"] is True
