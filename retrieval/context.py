"""Contextual chunk headers.

SEC evidence chunks rarely repeat the company name or fiscal period, yet questions
almost always name them ("3M's capital expenditure in fiscal year 2018"). Retrieval
only sees the chunk text, so the company and period are prepended for embedding,
keyword indexing and reranking. The stored payload text is left unchanged, so the
answer-generation context and displayed sources are unaffected.
"""


def contextualize(text: str, metadata: dict | None) -> str:
    """Return ``text`` prefixed with a one-line company / period / filing header."""
    metadata = metadata or {}
    parts = [
        str(metadata.get(key)).strip()
        for key in ("company", "year", "filing_type")
        if metadata.get(key)
    ]
    if not parts:
        return text
    return f"{' '.join(parts)}\n{text}"
