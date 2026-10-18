"""
Numeric grounding check for generated answers.
OWASP LLM09 (misinformation) mitigation — flags figures in an answer that do
not appear in the retrieved context. Heuristic: it compares digits only, so a
unit conversion (383,285 million vs $383.3 billion) is reported as ungrounded.
Treat the result as a warning signal, not a verdict.
"""

import re

_NUMBER = re.compile(r"\d[\d,]*(?:\.\d+)?")
# Years and tiny integers (list numbering, "Q3") are too common to be informative
_IGNORE_BELOW = 10


def _numbers(text: str) -> set[str]:
    found = set()
    for raw in _NUMBER.findall(text):
        value = raw.replace(",", "").rstrip(".")
        if "." in value:
            value = value.rstrip("0").rstrip(".")
        if value and not (value.isdigit() and int(value) < _IGNORE_BELOW):
            found.add(value)
    return found


def ungrounded_numbers(answer: str, context_chunks: list[dict]) -> list[str]:
    """Return numbers in the answer that appear in none of the context chunks."""
    context = set()
    for chunk in context_chunks:
        context |= _numbers(chunk["text"])
    return sorted(_numbers(answer) - context)
