"""Unit tests for PII anonymization and rehydration."""
import pytest
from security.pii_handler import anonymize, rehydrate


def test_anonymize_ssn():
    text = "My SSN is 123-45-6789"
    sanitized, mapping = anonymize(text)
    assert "123-45-6789" not in sanitized
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
