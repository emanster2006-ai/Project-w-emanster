import pytest

KEY = "test-ingest-key"
AUTH = {"Authorization": f"Bearer {KEY}"}


@pytest.fixture(autouse=True)
def ingest_key(monkeypatch):
    monkeypatch.setenv("INGEST_API_KEY", KEY)


def test_ingest_runs_background_pipeline_with_valid_parameters(endpoint):
    client, services = endpoint
    response = client.post("/api/v1/ingest", json={"limit": 2}, headers=AUTH)
    assert response.status_code == 200
    assert response.json()["documents_queued"] == 2
    services.ingest.assert_called_once_with(source="financebench", limit=2)


@pytest.mark.parametrize("body", [{"limit": 0}, {"limit": -1}, {"source": "unknown"}])
def test_invalid_ingest_request_never_starts_work(endpoint, body):
    client, services = endpoint
    assert client.post("/api/v1/ingest", json=body, headers=AUTH).status_code == 422
    services.ingest.assert_not_called()


@pytest.mark.parametrize(
    "headers",
    [
        {},
        {"Authorization": "Bearer wrong"},
        {"Authorization": "Basic " + KEY},
        {"Authorization": KEY},
        {"Authorization": "Bearer "},
    ],
)
def test_ingest_rejects_missing_or_wrong_credentials(endpoint, headers):
    client, services = endpoint
    response = client.post("/api/v1/ingest", json={"limit": 2}, headers=headers)
    assert response.status_code == 401
    assert response.headers["www-authenticate"] == "Bearer"
    services.ingest.assert_not_called()


def test_ingest_is_disabled_when_no_key_is_configured(endpoint, monkeypatch):
    client, services = endpoint
    monkeypatch.delenv("INGEST_API_KEY", raising=False)
    response = client.post("/api/v1/ingest", json={"limit": 2}, headers=AUTH)
    assert response.status_code == 503
    services.ingest.assert_not_called()


def test_second_ingest_is_refused_while_one_is_running(endpoint):
    from api.routes import ingest

    client, services = endpoint
    ingest._running = True
    response = client.post("/api/v1/ingest", json={"limit": 2}, headers=AUTH)
    assert response.status_code == 409
    services.ingest.assert_not_called()
