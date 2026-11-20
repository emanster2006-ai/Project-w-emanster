"""Translate upstream failures into accurate HTTP errors."""


def is_rate_limited(exc: BaseException | None) -> bool:
    """True when ``exc`` or anything it wraps is an upstream 429 (retry wrappers hide it)."""
    seen = set()
    while exc is not None and id(exc) not in seen:
        seen.add(id(exc))
        if getattr(exc, "status_code", None) == 429 or type(exc).__name__ == "RateLimitError":
            return True
        # tenacity.RetryError keeps the real failure on its last attempt
        last = getattr(exc, "last_attempt", None)
        if last is not None and not last.cancelled():
            if is_rate_limited(last.exception()):
                return True
        exc = exc.__cause__ or exc.__context__
    return False
