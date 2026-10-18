"""
SecurityMiddleware — input validation, PII sanitization, injection detection.
Runs BEFORE the request hits any route handler.
"""

from starlette.middleware.base import BaseHTTPMiddleware
from starlette.requests import Request
from starlette.responses import JSONResponse
from security.input_guard import is_injection_attempt
from security.pii_handler import anonymize
import json
import os
import logging

logger = logging.getLogger(__name__)
MAX_QUERY_LENGTH = int(os.getenv("MAX_QUERY_LENGTH", 2000))


class SecurityMiddleware(BaseHTTPMiddleware):
    async def dispatch(self, request: Request, call_next):
        if request.url.path == "/api/v1/query" and request.method == "POST":
            try:
                body_bytes = await request.body()
                body = json.loads(body_bytes)
                if not isinstance(body, dict) or not isinstance(
                    body.get("question"), str
                ):
                    return await call_next(request)
                question = body["question"]

                # ── Length cap ─────────────────────────────────────────────
                if len(question) > MAX_QUERY_LENGTH:
                    return JSONResponse(
                        status_code=400,
                        content={
                            "detail": f"Query exceeds max length of {MAX_QUERY_LENGTH} chars."
                        },
                    )

                # ── Prompt injection detection ─────────────────────────────
                if is_injection_attempt(question):
                    logger.warning("Prompt injection attempt blocked")
                    return JSONResponse(
                        status_code=400,
                        content={"detail": "Query contains disallowed patterns."},
                    )

                # ── PII anonymization ──────────────────────────────────────
                sanitized, pii_mapping = anonymize(question)
                request.state.sanitized_question = sanitized
                request.state.pii_mapping = pii_mapping
                request.state.original_question = question

            except (json.JSONDecodeError, KeyError):
                pass  # let FastAPI handle malformed JSON

        response = await call_next(request)
        return response
