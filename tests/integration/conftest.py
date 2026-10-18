"""Exercise real HTTP routes with deterministic substitutes for ML services."""

import sys
from types import ModuleType, SimpleNamespace
from unittest.mock import AsyncMock, Mock

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient
from slowapi import _rate_limit_exceeded_handler
from slowapi.errors import RateLimitExceeded


@pytest.fixture
def endpoint(monkeypatch):
    services = SimpleNamespace(
        anonymize=Mock(side_effect=lambda text: (text, {})),
        rehydrate=Mock(side_effect=lambda text, mapping: text),
        cache=AsyncMock(return_value=None),
        save=AsyncMock(),
        search=AsyncMock(
            return_value=[
                {
                    "text": "Revenue was 42",
                    "metadata": {"source": "filing.pdf"},
                    "score": 0.9,
                }
            ]
        ),
        generate=AsyncMock(return_value="Revenue was 42"),
        ingest=Mock(),
    )
    modules = {
        "security.pii_handler": {
            "anonymize": services.anonymize,
            "rehydrate": services.rehydrate,
        },
        "api.middleware.cache": {
            "check_cache": services.cache,
            "set_cache": services.save,
        },
        "retrieval.vectorstore": {"get_vectorstore": Mock()},
        "retrieval.reranker": {"rerank": lambda q, chunks, top_k: chunks[:top_k]},
        "retrieval.hybrid": {"hybrid_search": services.search},
        "retrieval.hyde": {
            "generate_hypothetical_doc": AsyncMock(side_effect=lambda q: q)
        },
        "retrieval.decomposer": {"decompose_query": AsyncMock(return_value=[])},
        "generation.llm": {"generate_answer": services.generate},
        "scripts.ingest": {"run_ingestion": services.ingest},
    }
    for name, attrs in modules.items():
        module = ModuleType(name)
        module.__dict__.update(attrs)
        monkeypatch.setitem(sys.modules, name, module)
    # Import after replacing external-service adapters; patch the bound PII function too.
    from api.middleware import security
    from api.routes import ingest, query

    monkeypatch.setattr(security, "anonymize", services.anonymize)
    query.limiter.reset()
    app = FastAPI()
    app.state.limiter = query.limiter
    app.add_exception_handler(RateLimitExceeded, _rate_limit_exceeded_handler)
    app.add_middleware(security.SecurityMiddleware)
    app.include_router(query.router, prefix="/api/v1")
    app.include_router(ingest.router, prefix="/api/v1")
    app.state.langfuse = Mock()
    with TestClient(app) as client:
        yield client, services
    query.limiter.reset()
