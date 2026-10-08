"""
LLM client wrapper — supports Groq (primary) and OpenAI (fallback).
All prompts are loaded from Jinja2 templates in generation/prompts/.
"""

import logging
import os

from groq import Groq
from jinja2 import Environment, FileSystemLoader
from openai import OpenAI

logger = logging.getLogger(__name__)

_client = None
_jinja_env = Environment(
    loader=FileSystemLoader(os.path.join(os.path.dirname(__file__), "prompts"))
)


def get_llm_client():
    global _client
    if _client is None:
        provider = os.getenv("LLM_PROVIDER", "groq")
        if provider == "groq":
            _client = Groq(api_key=os.getenv("GROQ_API_KEY"))
        else:
            _client = OpenAI(
                api_key=os.getenv("OPENAI_API_KEY"),
                base_url=os.getenv("OPENAI_BASE_URL") or None,
            )
        logger.info(f"LLM client initialized: {provider}")
    return _client


async def generate_answer(question: str, context_chunks: list[dict]) -> str:
    """
    Generate an answer using retrieved chunks as context.
    Uses instructor-validated output schema (FinancialRAGResponse).
    """
    import instructor

    from security.output_guard import FinancialRAGResponse

    context_text = "\n\n---\n\n".join(
        f"[Source: {c['metadata'].get('company', 'Unknown')} {c['metadata'].get('year', '')}]\n{c['text']}"
        for c in context_chunks
    )

    system_prompt = _jinja_env.get_template("rag_system.j2").render()
    user_prompt = _jinja_env.get_template("rag_user.j2").render(
        question=question,
        context=context_text,
    )

    raw_client = get_llm_client()

    # Use instructor for structured output validation
    provider = os.getenv("LLM_PROVIDER", "groq")
    if provider == "groq":
        client = instructor.from_groq(raw_client, mode=instructor.Mode.JSON)
    else:
        client = instructor.from_openai(raw_client, mode=instructor.Mode.JSON)

    response = client.chat.completions.create(
        model=os.getenv("LLM_MODEL", "llama-3.1-70b-versatile"),
        response_model=FinancialRAGResponse,
        messages=[
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": user_prompt},
        ],
        max_tokens=1000,
        max_retries=2,  # instructor auto-retries if schema validation fails
    )

    return response.answer
