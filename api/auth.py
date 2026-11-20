"""Authentication for operator-only endpoints."""

import hmac
import os

from fastapi import Header, HTTPException


def require_ingest_key(authorization: str | None = Header(default=None)) -> None:
    """Allow a request only when it carries ``Authorization: Bearer $INGEST_API_KEY``.

    Ingestion is expensive and every run adds a full copy of the corpus to the
    index, so it must never be open to the public. With no key configured the
    endpoint is disabled instead of silently open.
    """
    expected = os.getenv("INGEST_API_KEY", "")
    if not expected:
        raise HTTPException(
            status_code=503,
            detail="Ingestion is disabled: INGEST_API_KEY is not configured.",
        )
    scheme, _, supplied = (authorization or "").partition(" ")
    if scheme.lower() != "bearer" or not hmac.compare_digest(
        supplied.encode(), expected.encode()
    ):
        raise HTTPException(
            status_code=401,
            detail="Invalid or missing ingestion credentials.",
            headers={"WWW-Authenticate": "Bearer"},
        )
