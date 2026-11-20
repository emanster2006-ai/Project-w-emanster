"""
PII anonymization and rehydration using Microsoft Presidio.
OWASP LLM06 mitigation — zero data leakage to external LLM APIs.
"""

from presidio_analyzer import AnalyzerEngine
import logging

logger = logging.getLogger(__name__)

_analyzer = None

# Presidio's default set also masks DATE_TIME, LOCATION and NRP, which wipes
# out fiscal years, quarters and regions from financial questions and hurts
# retrieval. Only mask entities that identify a person or account.
PII_ENTITIES = [
    "PERSON",
    "EMAIL_ADDRESS",
    "PHONE_NUMBER",
    "CREDIT_CARD",
    "US_SSN",
    "US_ITIN",
    "US_PASSPORT",
    "US_DRIVER_LICENSE",
    "US_BANK_NUMBER",
    "IBAN_CODE",
    "IP_ADDRESS",
    "CRYPTO",
    "MEDICAL_LICENSE",
]


def _get_analyzer() -> AnalyzerEngine:
    global _analyzer
    if _analyzer is None:
        _analyzer = AnalyzerEngine()
    return _analyzer


def anonymize(text: str) -> tuple[str, dict]:
    """
    Detect and replace PII entities with deterministic tokens.
    Returns: (sanitized_text, pii_mapping for rehydration)

    Example:
        "John Doe's account is 123-45-6789"
        -> "<PERSON_0>'s account is <US_SSN_0>", {"<PERSON_0>": "John Doe", ...}
    """
    analyzer = _get_analyzer()

    results = analyzer.analyze(
        text=text, language="en", entities=PII_ENTITIES, score_threshold=0.4
    )
    if not results:
        return text, {}

    # Keep the highest-scoring span wherever detections overlap
    spans = []
    for result in sorted(results, key=lambda r: (-r.score, r.start)):
        if all(result.end <= kept.start or result.start >= kept.end for kept in spans):
            spans.append(result)
    spans.sort(key=lambda r: r.start)

    # One token per distinct value, numbered in order of appearance
    pii_mapping = {}
    token_for = {}
    counters = {}
    tokens = []
    for span in spans:
        value = text[span.start : span.end]
        key = (span.entity_type, value)
        if key not in token_for:
            index = counters.get(span.entity_type, 0)
            counters[span.entity_type] = index + 1
            token_for[key] = f"<{span.entity_type}_{index}>"
            pii_mapping[token_for[key]] = value
        tokens.append(token_for[key])

    # Replace right-to-left so earlier offsets stay valid
    anonymized = text
    for span, token in reversed(list(zip(spans, tokens))):
        anonymized = anonymized[: span.start] + token + anonymized[span.end :]

    logger.info(f"PII anonymized: {len(pii_mapping)} entities masked")
    return anonymized, pii_mapping


def rehydrate(text: str, pii_mapping: dict) -> str:
    """Replace deterministic tokens back with original PII values."""
    for token, original in pii_mapping.items():
        text = text.replace(token, original)
    return text
