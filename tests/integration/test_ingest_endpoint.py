import pytest


def test_ingest_runs_background_pipeline_with_valid_parameters(endpoint):
    client, services = endpoint
    response = client.post("/api/v1/ingest", json={"limit": 2})
    assert response.status_code == 200
    assert response.json()["documents_queued"] == 2
    services.ingest.assert_called_once_with(source="financebench", limit=2)


@pytest.mark.parametrize("body", [{"limit": 0}, {"limit": -1}, {"source": "unknown"}])
def test_invalid_ingest_request_never_starts_work(endpoint, body):
    client, services = endpoint
    assert client.post("/api/v1/ingest", json=body).status_code == 422
    services.ingest.assert_not_called()
