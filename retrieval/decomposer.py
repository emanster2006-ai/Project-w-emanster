"""
Multi-hop query decomposition.
Complex financial questions (e.g., "Compare Apple and Microsoft R&D spend 2021 vs 2022")
require multiple retrievals. This breaks them into atomic sub-questions.
"""

import logging
import os

import instructor
from pydantic import BaseModel, Field

from generation.llm import get_llm_client

logger = logging.getLogger(__name__)


class DecomposedQuery(BaseModel):
    """Structured output enforced by instructor."""

    needs_decomposition: bool
    sub_questions: list[str] = Field(default_factory=list, max_length=4)
    reasoning: str = Field(default="")


async def decompose_query(question: str) -> list[str] | None:
    """
    Use LLM to break complex questions into atomic sub-questions.
    Returns list of sub-questions, or None if question is already atomic.
    """
    raw_client = get_llm_client()
    provider = os.getenv("LLM_PROVIDER", "groq")
    if provider == "groq":
        client = instructor.from_groq(raw_client, mode=instructor.Mode.JSON)
    else:
        client = instructor.from_openai(raw_client, mode=instructor.Mode.JSON)

    result = client.chat.completions.create(
        model=os.getenv("LLM_MODEL", "llama-3.1-70b-versatile"),
        response_model=DecomposedQuery,
        messages=[
            {
                "role": "system",
                "content": (
                    "You are a financial document analysis assistant. "
                    "Determine if a question requires multiple document lookups "
                    "to answer completely. If yes, break it into 2-4 atomic sub-questions."
                ),
            },
            {
                "role": "user",
                "content": f"Question: {question}\n\nDoes this require multiple lookups?",
            },
        ],
        max_tokens=400,
    )

    if result.needs_decomposition and result.sub_questions:
        logger.info(f"Decomposed into {len(result.sub_questions)} sub-questions")
        return result.sub_questions

    return [question]  # Return as single-item list if no decomposition needed
