from fastapi import FastAPI
from fastapi.testclient import TestClient

from api.middleware.headers import SecurityHeadersMiddleware


def test_responses_carry_defensive_headers():
    app = FastAPI()
    app.add_middleware(SecurityHeadersMiddleware)

    @app.get("/ping")
    def ping():
        return {"ok": True}

    response = TestClient(app).get("/ping")
    assert response.headers["x-content-type-options"] == "nosniff"
    assert response.headers["x-frame-options"] == "DENY"
    assert response.headers["referrer-policy"] == "no-referrer"
    assert response.headers["cache-control"] == "no-store"


class RateLimitError(Exception):
    pass


def test_upstream_rate_limit_becomes_429_with_retry_after(endpoint):
    client, services = endpoint
    services.generate.side_effect = RateLimitError("tokens per day exceeded")
    response = client.post("/api/v1/query", json={"question": "What was revenue?"})
    assert response.status_code == 429
    assert response.headers["retry-after"] == "60"
    assert "rate limited" in response.json()["detail"].lower()


def test_other_upstream_failures_stay_generic_500(endpoint):
    client, services = endpoint
    services.generate.side_effect = RuntimeError("secret internal detail")
    response = client.post("/api/v1/query", json={"question": "What was revenue?"})
    assert response.status_code == 500
    assert "secret" not in response.text
