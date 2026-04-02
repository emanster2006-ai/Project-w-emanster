"""Integration tests for the ingest endpoint."""

from contextlib import asynccontextmanager

from fastapi.testclient import TestClient

from api.main import create_app


class _DummyLangfuse:
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


def test_ingest_endpoint_queues_background_task(monkeypatch):
    called = {}

    def fake_run_ingestion(source, limit):
        called["source"] = source
        called["limit"] = limit

    monkeypatch.setattr("scripts.ingest.run_ingestion", fake_run_ingestion)

    with _build_test_client() as client:
        response = client.post("/api/v1/ingest", json={"source": "financebench", "limit": 3})

    assert response.status_code == 200
    assert response.json() == {
        "status": "queued",
        "documents_queued": 3,
        "message": "Ingestion running in background. Check /health for status.",
    }
    assert called == {"source": "financebench", "limit": 3}


def test_health_endpoint_reports_mocked_dependencies(monkeypatch):
    async def fake_check_dependencies():
        from api.routes.health import DependencyStatus

        return DependencyStatus(qdrant="ok", redis="ok", embedder="ok")

    monkeypatch.setattr("api.routes.health._check_dependencies", fake_check_dependencies)

    with _build_test_client() as client:
        response = client.get("/health")

    assert response.status_code == 200
    payload = response.json()
    assert payload["status"] == "ok"
    assert payload["dependencies"] == {
        "qdrant": "ok",
        "redis": "ok",
        "embedder": "ok",
    }
