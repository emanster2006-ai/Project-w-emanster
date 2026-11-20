"""Guards for the semantic cache.

Embedding similarity alone treats "3M capex in 2018" and "3M capex in 2019" as the
same question. A cached answer may only be reused when the details that change the
answer (years, quarters, figures, company and other proper nouns) are identical.
"""

import re

_WORD = re.compile(r"[A-Za-z0-9&][A-Za-z0-9&.'\-]*")
_STOP = {
    "what", "which", "who", "how", "when", "where", "why", "is", "are", "was", "were",
    "does", "do", "did", "the", "a", "an", "in", "of", "for", "and", "if", "assume",
    "answer", "give", "compare", "i", "us", "u.s.",
}


def signature(query: str) -> frozenset[str]:
    """Tokens that must match exactly for two questions to share a cached answer."""
    sig = set()
    for i, raw in enumerate(_WORD.findall(query)):
        token = raw.strip(".'-").replace("'s", "")
        if not token:
            continue
        low = token.lower()
        if any(ch.isdigit() for ch in token):
            sig.add(low)
        elif i > 0 and token[0].isupper() and low not in _STOP:
            sig.add(low)
    return frozenset(sig)


def options_key(use_hyde: bool, use_decomposition: bool, top_k: int) -> str:
    """Request settings that change the answer must also match."""
    return f"h{int(use_hyde)}d{int(use_decomposition)}k{top_k}"


def is_reusable(query: str, cached_signature: list[str], cached_options: str, options: str) -> bool:
    return cached_options == options and signature(query) == frozenset(cached_signature)
