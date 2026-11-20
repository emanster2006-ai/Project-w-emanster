import pytest

from generation.reasoning import reasoning_options


def test_reasoning_models_get_the_requested_effort(monkeypatch):
    monkeypatch.setenv("LLM_MODEL", "openai/gpt-oss-120b")
    assert reasoning_options("low") == {"extra_body": {"reasoning_effort": "low"}}
    assert reasoning_options("high") == {"extra_body": {"reasoning_effort": "high"}}


def test_default_model_is_a_reasoning_model(monkeypatch):
    monkeypatch.delenv("LLM_MODEL", raising=False)
    assert reasoning_options("low")["extra_body"]["reasoning_effort"] == "low"


@pytest.mark.parametrize(
    "model", ["llama-3.3-70b-versatile", "gpt-4o-mini", "qwen/qwen3-32b"]
)
def test_other_models_get_no_extra_arguments(monkeypatch, model):
    monkeypatch.setenv("LLM_MODEL", model)
    assert reasoning_options("low") == {}
