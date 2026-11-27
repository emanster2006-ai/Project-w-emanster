"""Which system prompt template the generator uses. Kept free of third-party imports so
the choice can be tested without the provider SDKs installed."""

import os
import re

PROMPTS_DIR = os.path.join(os.path.dirname(__file__), "prompts")


def default_system_template() -> str:
    """System prompt template: rag_system.j2 unless LLM_SYSTEM_TEMPLATE names another
    template in generation/prompts/ (used to evaluate prompt changes end to end)."""
    name = os.getenv("LLM_SYSTEM_TEMPLATE", "rag_system.j2")
    if not re.fullmatch(r"[\w.-]+\.j2", name) or not os.path.exists(
        os.path.join(PROMPTS_DIR, name)
    ):
        raise ValueError(
            f"LLM_SYSTEM_TEMPLATE must name a template in prompts/: {name!r}"
        )
    return name
