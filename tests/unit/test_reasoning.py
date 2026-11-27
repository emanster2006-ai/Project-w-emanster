import pytest

from generation.reasoning import reasoning_options


def test_reasoning_models_get_the_requested_effort(monkeypatch):
    monkeypatch.setenv("LLM_MODEL", "openai/gpt-oss-120b")
    assert reasoning_options("low") == {"extra_body": {"reasoning_effort": "low"}}
    assert reasoning_options("high") == {"extra_body": {"reasoning_effort": "high"}}


@pytest.mark.parametrize("model", ["openai/gpt-oss-120b", "gpt-oss-120b"])
def test_gpt_oss_gets_effort_under_any_provider_name(monkeypatch, model):
    monkeypatch.setenv("LLM_MODEL", model)
    assert reasoning_options("medium") == {"extra_body": {"reasoning_effort": "medium"}}


def test_default_model_is_a_reasoning_model(monkeypatch):
    monkeypatch.delenv("LLM_MODEL", raising=False)
    assert reasoning_options("low")["extra_body"]["reasoning_effort"] == "low"


@pytest.mark.parametrize(
    "model", ["llama-3.3-70b-versatile", "gpt-4o-mini", "qwen/qwen3-32b"]
)
def test_other_models_get_no_extra_arguments(monkeypatch, model):
    monkeypatch.setenv("LLM_MODEL", model)
    assert reasoning_options("low") == {}


def test_system_template_comes_from_env_and_must_exist(monkeypatch):
    import generation.templates as templates

    monkeypatch.delenv("LLM_SYSTEM_TEMPLATE", raising=False)
    assert templates.default_system_template() == "rag_system.j2"
    monkeypatch.setenv("LLM_SYSTEM_TEMPLATE", "rag_system_candidate.j2")
    assert templates.default_system_template() == "rag_system_candidate.j2"
    for bad in ("../../etc/passwd", "missing.j2"):
        monkeypatch.setenv("LLM_SYSTEM_TEMPLATE", bad)
        with pytest.raises(ValueError):
            templates.default_system_template()
