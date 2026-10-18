"""
Prompt injection detection — pattern-based + keyword blocklist.
OWASP LLM01 mitigation.
"""

import base64
import binascii
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
    r"what\s+(is|are)\s+your\s+(system\s+)?(prompt|instructions)",
    r"disregard\s+(your\s+|the\s+|all\s+)?(previous|prior|above)\s+(context|instructions|rules)",
    r"\b(launder(ing)?\s+money|insider\s+trading\s+(tips|advice)|evade\s+taxes)\b",  # harmful finance
    r"<\|?(im_start|im_end|system)\|?>",  # chat-template control tokens
]

# Same attack in other common languages (fr/es/de)
INJECTION_PATTERNS += [
    r"ignor(ez|e|a|ar)\s+(toutes\s+)?(les\s+|todas\s+las\s+|las\s+)?(instructions|instrucciones)\s+(pr[ée]c[ée]dentes|anteriores)",
    r"ignorier(e|en)\s+(alle\s+)?(vorherigen|bisherigen)\s+(anweisungen|instruktionen)",
]

_compiled = [re.compile(p, re.IGNORECASE) for p in INJECTION_PATTERNS]

# Second layer: an attack usually pairs a directive verb with a reference to
# the assistant's own rules/prompt. Either alone is common in benign queries.
_DIRECTIVE = re.compile(
    r"\b(pretend|translate|repeat|start your (reply|answer|response)|from now on"
    r"|answer freely|without any (restrictions|rules|limits))\b",
    re.IGNORECASE,
)
_SELF_REF = re.compile(
    r"\b(earlier|previous|prior|hidden|secret|initial|original|given before)\b.{0,40}"
    r"\b(rules?|setup|prompt|instructions?|text|message|conversation)\b"
    r"|\byou (answer|respond|reply|are)\b.{0,30}\b(without|no)\b.{0,15}\b(restrictions?|rules?|limits?)\b"
    r"|\bthe text you were given\b",
    re.IGNORECASE,
)
_B64_TOKEN = re.compile(r"[A-Za-z0-9+/]{16,}={0,2}")


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
    return _matches(query) or any(_matches(d) for d in _decoded_base64(query))


def _matches(text: str) -> bool:
    if any(p.search(text) for p in _compiled):
        return True
    return bool(_DIRECTIVE.search(text) and _SELF_REF.search(text))


def _decoded_base64(text: str) -> list[str]:
    """Decode base64-looking tokens so encoded payloads get the same checks."""
    decoded = []
    for token in _B64_TOKEN.findall(text):
        try:
            decoded.append(
                base64.b64decode(token + "=" * (-len(token) % 4), validate=True).decode(
                    "utf-8"
                )
            )
        except (binascii.Error, UnicodeDecodeError, ValueError):
            continue
    return decoded
