"""
PII anonymization and rehydration using Microsoft Presidio.
OWASP LLM06 mitigation — zero data leakage to external LLM APIs.
"""

import logging
import re

from presidio_analyzer import AnalyzerEngine
from presidio_anonymizer import AnonymizerEngine
from presidio_anonymizer.entities import OperatorConfig

logger = logging.getLogger(__name__)

_analyzer = None
_anonymizer = None
_PRESIDIO_DISABLED = False

_FALLBACK_PATTERNS = [
    ("US_SSN", re.compile(r"\b\d{3}-\d{2}-\d{4}\b")),
    ("EMAIL_ADDRESS", re.compile(r"\b[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Za-z]{2,}\b")),
    ("CREDIT_CARD", re.compile(r"\b(?:\d{4}[- ]?){3}\d{4}\b")),
]


def _get_engines():
    global _PRESIDIO_DISABLED, _analyzer, _anonymizer
    if _PRESIDIO_DISABLED:
        return None, None
    if _analyzer is None:
        try:
            _analyzer = AnalyzerEngine()
            _anonymizer = AnonymizerEngine()
        except Exception as exc:
            logger.warning(
                "Presidio initialization failed; using regex-only PII fallback: %s",
                exc,
            )
            _PRESIDIO_DISABLED = True
            return None, None
    return _analyzer, _anonymizer


def _fallback_anonymize(text: str) -> tuple[str, dict]:
    """Conservative offline fallback when Presidio or its models are unavailable."""
    matches = []
    for entity_type, pattern in _FALLBACK_PATTERNS:
        for match in pattern.finditer(text):
            matches.append((match.start(), match.end(), entity_type, match.group(0)))

    if not matches:
        return text, {}

    matches.sort(key=lambda item: (item[0], -(item[1] - item[0])))
    filtered_matches = []
    last_end = -1
    for start, end, entity_type, value in matches:
        if start < last_end:
            continue
        filtered_matches.append((start, end, entity_type, value))
        last_end = end

    counters: dict[str, int] = {}
    pii_mapping = {}
    parts = []
    cursor = 0

    for start, end, entity_type, value in filtered_matches:
        counter = counters.get(entity_type, 0)
        token = f"<{entity_type}_{counter}>"
        counters[entity_type] = counter + 1
        pii_mapping[token] = value
        parts.append(text[cursor:start])
        parts.append(token)
        cursor = end

    parts.append(text[cursor:])
    logger.info("PII anonymized with fallback recognizers: %s entities masked", len(pii_mapping))
    return "".join(parts), pii_mapping


def anonymize(text: str) -> tuple[str, dict]:
    """
    Detect and replace PII entities with deterministic tokens.
    Returns: (sanitized_text, pii_mapping for rehydration)

    Example:
        "John Doe's account is 123-45-6789"
        -> "<PERSON_0>'s account is <US_SSN_0>", {"<PERSON_0>": "John Doe", ...}
    """
    analyzer, anonymizer = _get_engines()
    if analyzer is None or anonymizer is None:
        return _fallback_anonymize(text)

    try:
        results = analyzer.analyze(text=text, language="en")
    except Exception as exc:
        logger.warning("Presidio analysis failed; using regex-only PII fallback: %s", exc)
        return _fallback_anonymize(text)

    if not results:
        return text, {}

    pii_mapping = {}
    counters = {}
    operator_config = {}

    for result in results:
        entity_type = result.entity_type
        counter = counters.get(entity_type, 0)
        token = f"<{entity_type}_{counter}>"
        original_value = text[result.start:result.end]
        pii_mapping[token] = original_value
        counters[entity_type] = counter + 1
        operator_config[entity_type] = OperatorConfig("replace", {"new_value": token})

    anonymized = anonymizer.anonymize(
        text=text,
        analyzer_results=results,
        operators=operator_config,
    )

    logger.info(f"PII anonymized: {len(pii_mapping)} entities masked")
    return anonymized.text, pii_mapping


def rehydrate(text: str, pii_mapping: dict) -> str:
    """Replace deterministic tokens back with original PII values."""
    for token, original in pii_mapping.items():
        text = text.replace(token, original)
    return text
