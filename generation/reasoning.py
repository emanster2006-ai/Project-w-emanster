"""Reasoning-effort options for reasoning models (e.g. Groq's gpt-oss family).

Reasoning models spend hidden tokens "thinking" before they answer. For cheap helper
steps (HyDE, question decomposition) that is wasted budget: it drains rate-limited
free-tier quotas and can exhaust ``max_tokens`` before any visible answer appears.
"""

import os

# Groq names the model "openai/gpt-oss-120b"; Cerebras and others use "gpt-oss-120b".
_REASONING_MODEL_PREFIXES = ("openai/gpt-oss", "gpt-oss")


def reasoning_options(effort: str) -> dict:
    """Extra request arguments selecting ``effort`` ("low" | "medium" | "high").

    Returns {} for models that do not take the parameter, so it is safe to splat into
    any chat-completion call. Sent via ``extra_body`` because the pinned groq SDK
    rejects ``reasoning_effort`` as a keyword.
    """
    model = os.getenv("LLM_MODEL", "openai/gpt-oss-120b")
    if model.startswith(_REASONING_MODEL_PREFIXES):
        return {"extra_body": {"reasoning_effort": effort}}
    return {}
