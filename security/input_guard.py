"""
Prompt injection detection — pattern-based + keyword blocklist.
OWASP LLM01 mitigation.
"""

import re
import unicodedata

# Classic injection patterns
INJECTION_PATTERNS = [
    r"ignore\s+(all\s+)?(previous|prior|above)\s+instructions",
    r"disregard\s+(your\s+)?(system\s+)?prompt",
    r"you\s+are\s+now\s+(?!a\s+financial)",  # persona hijacking
    r"act\s+as\s+(if\s+you\s+are\s+)?(?!a\s+financial)",
    r"jailbreak",
    r"dan\s+mode",
    r"developer\s+mode",
    r"override\s+(your\s+)?(safety|instructions|rules)",
    r"forget\s+(everything|all)\s+(you|above)",
    r"<\s*script",  # XSS in query
    r"system\s*:\s*you\s+are",  # system prompt injection format
    r"\[INST\]",  # Llama instruction injection
    r"###\s*instruction",
    r"reveal\s+(your\s+)?(system\s+)?prompt",
    r"print\s+(your\s+)?(system\s+)?prompt",
    r"what\s+(are|is)\s+your\s+(system\s+)?instructions",
    r"(show|repeat|output|display)\s+(me\s+)?(your\s+|the\s+)?(system\s+|initial\s+|hidden\s+)(prompt|instructions|message)",
    r"(do\s+not|don'?t)\s+follow\s+(your\s+|the\s+)?(previous|prior|above|system)",
    r"(bypass|disable)\s+(your\s+|the\s+)?(safety|guardrails?|filters?|restrictions?)",
    r"<\|?(im_start|im_end|system)\|?>",  # chat-template control tokens
]

_compiled = [re.compile(p, re.IGNORECASE) for p in INJECTION_PATTERNS]


# Zero-width / invisible characters used to split keywords past regexes
_INVISIBLE = dict.fromkeys(map(ord, "\u200b\u200c\u200d\u2060\ufeff\u00ad"))


def _normalize(query: str) -> str:
    """Fold look-alike Unicode, strip invisible chars, collapse whitespace."""
    text = unicodedata.normalize("NFKC", query).translate(_INVISIBLE)
    return re.sub(r"\s+", " ", text)


def is_injection_attempt(query: str) -> bool:
    """Return True if the query matches known injection patterns.

    Pattern matching only catches known phrasings; paraphrases, encodings and
    other languages can still get through (see SECURITY.md).
    """
    query = _normalize(query)
    for pattern in _compiled:
        if pattern.search(query):
            return True
    return False
