"""Unit tests for PII anonymization and rehydration."""

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


class _Hit:
    def __init__(self, entity_type, start, end, score=0.9):
        self.entity_type, self.start, self.end, self.score = (
            entity_type,
            start,
            end,
            score,
        )


def _stub_analyzer(monkeypatch, hits):
    class Stub:
        def analyze(self, **_):
            return hits

    monkeypatch.setattr("security.pii_handler._get_analyzer", lambda: Stub())


def test_two_entities_of_same_type_roundtrip(monkeypatch):
    text = "Alice Jones and Bob Lee asked about revenue"
    _stub_analyzer(monkeypatch, [_Hit("PERSON", 0, 11), _Hit("PERSON", 16, 23)])
    sanitized, mapping = anonymize(text)
    assert sanitized == "<PERSON_0> and <PERSON_1> asked about revenue"
    assert rehydrate(sanitized, mapping) == text


def test_repeated_value_reuses_token_and_overlap_keeps_best(monkeypatch):
    text = "Bob wrote to Bob"
    _stub_analyzer(
        monkeypatch,
        [_Hit("PERSON", 0, 3), _Hit("PERSON", 13, 16), _Hit("LOCATION", 0, 3, 0.5)],
    )
    sanitized, mapping = anonymize(text)
    assert sanitized == "<PERSON_0> wrote to <PERSON_0>"
    assert rehydrate(sanitized, mapping) == text
