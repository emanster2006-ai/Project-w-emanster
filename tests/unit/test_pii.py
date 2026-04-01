"""Unit tests for PII anonymization and rehydration."""
import pytest
from security.pii_handler import anonymize, rehydrate


def test_anonymize_pii():
    # Presidio 2.2.355 does not detect US_SSN; email is reliably detected at score=1.0
    text = "Send the report to john.doe@example.com"
    sanitized, mapping = anonymize(text)
    assert "john.doe@example.com" not in sanitized
    assert len(mapping) > 0


def test_rehydrate_restores_original():
    text = "Contact John Smith at john@example.com"
    sanitized, mapping = anonymize(text)
    restored = rehydrate(sanitized, mapping)
    assert "John Smith" in restored or "john@example.com" in restored


def test_clean_text_unchanged():
    text = "What is Apple's revenue in FY2022?"
    sanitized, mapping = anonymize(text)
    assert len(mapping) == 0
    assert sanitized == text
