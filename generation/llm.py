"""
LLM client wrapper — supports Groq (primary) and OpenAI (fallback).
All prompts are loaded from Jinja2 templates in generation/prompts/.
"""

from groq import Groq
from openai import OpenAI
from jinja2 import Environment, FileSystemLoader
import os
import logging
from dataclasses import dataclass

from generation.reasoning import reasoning_options
from security.grounding import ungrounded_numbers

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


@dataclass
class Usage:
    """Provider calls made for one answer, counting instructor's validation retries."""

    attempts: int = 0
    prompt_tokens: int = 0
    completion_tokens: int = 0


def render_messages(question: str, context_chunks: list[dict]) -> list[dict]:
    """The exact chat messages the generator sends for this question and context."""
    context_text = "\n\n---\n\n".join(
        f"[Source: {c['metadata'].get('company', 'Unknown')} {c['metadata'].get('year', '')}]\n{c['text']}"
        for c in context_chunks
    )
    system_prompt = _jinja_env.get_template("rag_system.j2").render()
    user_prompt = _jinja_env.get_template("rag_user.j2").render(
        question=question,
        context=context_text,
    )
    return [
        {"role": "system", "content": system_prompt},
        {"role": "user", "content": user_prompt},
    ]


async def generate_response(question: str, context_chunks: list[dict]):
    """
    Generate a validated FinancialRAGResponse from retrieved chunks.
    Returns (response, Usage); Usage meters every provider call, retries included.
    """
    import instructor
    from security.output_guard import FinancialRAGResponse

    raw_client = get_llm_client()
    usage = Usage()

    def metered_create(*args, **kwargs):
        usage.attempts += 1
        completion = raw_client.chat.completions.create(*args, **kwargs)
        reported = getattr(completion, "usage", None)
        if reported is not None:
            usage.prompt_tokens += reported.prompt_tokens or 0
            usage.completion_tokens += reported.completion_tokens or 0
        return completion

    # Use instructor for structured output validation. Built directly (rather than
    # instructor.from_groq) so the patched create is the metered one.
    provider = os.getenv("LLM_PROVIDER", "groq")
    client = instructor.Instructor(
        client=raw_client,
        create=instructor.patch(create=metered_create, mode=instructor.Mode.JSON),
        provider=(
            instructor.Provider.GROQ
            if provider == "groq"
            else instructor.Provider.OPENAI
        ),
        mode=instructor.Mode.JSON,
    )

    response = client.chat.completions.create(
        model=os.getenv("LLM_MODEL", "openai/gpt-oss-120b"),
        response_model=FinancialRAGResponse,
        messages=render_messages(question, context_chunks),
        max_tokens=1000,
        max_retries=2,  # instructor auto-retries if schema validation fails
        **reasoning_options(os.getenv("LLM_REASONING_EFFORT", "medium")),
    )

    missing = ungrounded_numbers(response.answer, context_chunks)
    if missing:
        logger.warning(f"Answer figures not found in retrieved context: {missing}")

    return response, usage


async def generate_answer(question: str, context_chunks: list[dict]) -> str:
    """
    Generate an answer using retrieved chunks as context.
    Uses instructor-validated output schema (FinancialRAGResponse).
    """
    response, _ = await generate_response(question, context_chunks)
    return response.answer
