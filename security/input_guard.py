"""
Prompt injection detection — pattern-based + keyword blocklist.
OWASP LLM01 mitigation.
"""

import re

# Classic injection patterns
INJECTION_PATTERNS = [
    r"ignore\s+(all\s+)?(previous|prior|above)\s+instructions",
    r"disregard\s+(your\s+)?(system\s+)?prompt",
    r"you\s+are\s+now\s+(?!a\s+financial)",   # persona hijacking
    r"act\s+as\s+(if\s+you\s+are\s+)?(?!a\s+financial)",
    r"jailbreak",
    r"dan\s+mode",
    r"developer\s+mode",
    r"override\s+(your\s+)?(safety|instructions|rules)",
    r"forget\s+(everything|all)\s+(you|above)",
    r"<\s*script",            # XSS in query
    r"system\s*:\s*you\s+are",  # system prompt injection format
    r"\[INST\]",              # Llama instruction injection
    r"###\s*instruction",
    r"reveal\s+(your\s+)?(system\s+)?prompt",
    r"print\s+(your\s+)?(system\s+)?prompt",
    r"what\s+(are|is)\s+your\s+(system\s+)?instructions",
]

_compiled = [re.compile(p, re.IGNORECASE) for p in INJECTION_PATTERNS]


def is_injection_attempt(query: str) -> bool:
    """Return True if the query matches known injection patterns."""
    for pattern in _compiled:
        if pattern.search(query):
            return True
    return False
