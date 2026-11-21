"""Thin tracing layer over the Langfuse SDK.

The query route records one trace per request with a span per pipeline stage.
Keeping the SDK calls here means an SDK upgrade touches one file, and a tracing
failure (bad keys, network, API change) is logged and ignored instead of failing
the user's request.
"""

import logging
from typing import Any

logger = logging.getLogger(__name__)


def _safe(fn, *args, **kwargs):
    try:
        return fn(*args, **kwargs)
    except Exception as exc:  # tracing must never break a request
        logger.warning("Tracing call failed: %s", exc)
        return None


class Span:
    def __init__(self, observation: Any):
        self._obs = observation

    def end(self, output: Any = None) -> None:
        if self._obs is None:
            return
        if output is not None:
            _safe(self._obs.update, output=output)
        _safe(self._obs.end)


class Trace:
    """Root observation for one request."""

    def __init__(self, observation: Any):
        self._obs = observation

    def span(self, name: str, input: Any = None) -> Span:
        if self._obs is None:
            return Span(None)
        return Span(_safe(self._obs.start_observation, name=name, input=input))

    def update(self, **fields: Any) -> None:
        if self._obs is not None:
            _safe(self._obs.update, **fields)

    def end(self) -> None:
        if self._obs is not None:
            _safe(self._obs.end)


def start_trace(client: Any, name: str, input: Any = None) -> Trace:
    """Start a root trace; returns a no-op trace if the client is missing or fails."""
    if client is None:
        return Trace(None)
    return Trace(_safe(client.start_observation, name=name, input=input))
