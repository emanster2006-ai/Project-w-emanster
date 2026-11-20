from concurrent.futures import Future

from api.errors import is_rate_limited


class RateLimitError(Exception):
    """Stands in for groq/openai RateLimitError (matched by name)."""


class StatusError(Exception):
    def __init__(self, status_code):
        self.status_code = status_code


class FakeRetryError(Exception):
    def __init__(self, inner):
        future = Future()
        future.set_exception(inner)
        self.last_attempt = future


def test_direct_rate_limit_error():
    assert is_rate_limited(RateLimitError("slow down"))


def test_status_code_429():
    assert is_rate_limited(StatusError(429))
    assert not is_rate_limited(StatusError(500))


def test_rate_limit_hidden_inside_a_retry_wrapper():
    assert is_rate_limited(FakeRetryError(RateLimitError("slow down")))


def test_rate_limit_in_exception_chain():
    try:
        try:
            raise RateLimitError("slow down")
        except RateLimitError as inner:
            raise RuntimeError("wrapped") from inner
    except RuntimeError as outer:
        assert is_rate_limited(outer)


def test_unrelated_errors_are_not_rate_limits():
    assert not is_rate_limited(ValueError("boom"))
    assert not is_rate_limited(FakeRetryError(ValueError("boom")))
    assert not is_rate_limited(None)
