"""Structured JSON request logging middleware."""
from starlette.middleware.base import BaseHTTPMiddleware
from starlette.requests import Request
import logging
import time
import json

logger = logging.getLogger(__name__)
logging.basicConfig(level=logging.INFO, format="%(message)s")


class LoggingMiddleware(BaseHTTPMiddleware):
    async def dispatch(self, request: Request, call_next):
        start = time.time()
        response = await call_next(request)
        latency_ms = (time.time() - start) * 1000

        log = {
            "method": request.method,
            "path": request.url.path,
            "status_code": response.status_code,
            "latency_ms": round(latency_ms, 2),
            "client_ip": request.client.host if request.client else "unknown",
        }
        logger.info(json.dumps(log))
        return response
