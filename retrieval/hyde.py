"""
HyDE — Hypothetical Document Embeddings.
Instead of embedding the short user question, we ask the LLM to generate
a hypothetical ideal answer, then embed THAT for retrieval.
Works because: ideal answers are long and semantically rich, closer to
what's actually stored in the document corpus than a short question.
"""

from jinja2 import Environment, FileSystemLoader
import os
import logging

logger = logging.getLogger(__name__)

_jinja_env = Environment(
    loader=FileSystemLoader(os.path.join(os.path.dirname(__file__), "..", "generation", "prompts"))
)


async def generate_hypothetical_doc(question: str) -> str:
    """
    Generate a hypothetical answer document for HyDE retrieval.
    Returns the hypothetical answer string (used for embedding, not shown to user).
    """
    from generation.llm import get_llm_client

    template = _jinja_env.get_template("hyde.j2")
    prompt = template.render(question=question)

    client = get_llm_client()
    response = client.chat.completions.create(
        model=os.getenv("LLM_MODEL", "llama-3.1-70b-versatile"),
        messages=[{"role": "user", "content": prompt}],
        max_tokens=300,
        temperature=0.7,
    )

    hypothetical = response.choices[0].message.content.strip()
    logger.info(f"HyDE generated {len(hypothetical)} char hypothetical doc")
    return hypothetical
