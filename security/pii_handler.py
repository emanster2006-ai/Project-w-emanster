"""
PII anonymization and rehydration using Microsoft Presidio.
OWASP LLM06 mitigation — zero data leakage to external LLM APIs.
"""

from presidio_analyzer import AnalyzerEngine
from presidio_anonymizer import AnonymizerEngine
from presidio_anonymizer.entities import OperatorConfig
import logging

logger = logging.getLogger(__name__)

_analyzer = None
_anonymizer = None


def _get_engines():
    global _analyzer, _anonymizer
    if _analyzer is None:
        _analyzer = AnalyzerEngine()
        _anonymizer = AnonymizerEngine()
    return _analyzer, _anonymizer


def anonymize(text: str) -> tuple[str, dict]:
    """
    Detect and replace PII entities with deterministic tokens.
    Returns: (sanitized_text, pii_mapping for rehydration)

    Example:
        "John Doe's account is 123-45-6789"
        -> "<PERSON_0>'s account is <US_SSN_0>", {"<PERSON_0>": "John Doe", ...}
    """
    analyzer, anonymizer = _get_engines()

    results = analyzer.analyze(text=text, language="en", score_threshold=0.4)
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
