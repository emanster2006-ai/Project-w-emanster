"""
Offline benchmark of PII detection (security/pii_handler.py + Presidio).

Needs presidio-analyzer and the spaCy en_core_web_lg model, but no services or
API keys. Small hand-written sets: a regression signal, not a general estimate.

Reports (1) recall: is each planted PII value removed from the sanitized text,
and (2) over-masking: how often benign financial questions get altered.

Usage: python scripts/pii_benchmark.py
"""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from security.pii_handler import anonymize, rehydrate  # noqa: E402

# (text, planted PII value, type)
PII_CASES = [
    ("Send the report to john.doe@example.com", "john.doe@example.com", "EMAIL"),
    ("My SSN is 123-45-6789, what is Apple's revenue?", "123-45-6789", "SSN"),
    ("SSN 078-05-1120 on file, summarize Boeing's risks", "078-05-1120", "SSN"),
    ("My credit card 4111-1111-1111-1111 needs advice", "4111-1111-1111-1111", "CARD"),
    ("Call me on 212-555-0198 about Tesla", "212-555-0198", "PHONE"),
    ("John Smith from Enron asks about the P/E ratio", "John Smith", "PERSON"),
    ("I'm Maria Garcia, summarize Amazon's risks", "Maria Garcia", "PERSON"),
    ("Wire to IBAN GB82WEST12345698765432 please", "GB82WEST12345698765432", "IBAN"),
    ("Server at 192.168.1.15 queries Netflix data", "192.168.1.15", "IP"),
    ("My passport number is C01234567, compare MSFT and GOOG", "C01234567", "ID"),
    ("Account 000123456789 belongs to me; Apple revenue?", "000123456789", "ACCOUNT"),
]

BENIGN = [
    "What was Apple's revenue in FY2022?",
    "Compare Microsoft and Google R&D expenses",
    "What are the risk factors in Tesla's 10-K?",
    "How did Netflix's operating income change from 2020 to 2022?",
    "Summarize Amazon's operations in Europe and Asia",
    "What did the CEO say about margins in the fourth quarter?",
    "How much did Boeing spend on capital expenditures in 2021?",
    "What is Walmart's effective tax rate for fiscal 2023?",
]


def main() -> None:
    caught = 0
    for text, value, kind in PII_CASES:
        sanitized, mapping = anonymize(text)
        ok = value not in sanitized and rehydrate(sanitized, mapping) == text
        caught += ok
        print(f"{'ok  ' if ok else 'MISS'} {kind:8} {text}")
    print(f"\nPII removed and restored: {caught}/{len(PII_CASES)}")

    altered = []
    for text in BENIGN:
        sanitized, _ = anonymize(text)
        if sanitized != text:
            altered.append((text, sanitized))
    print(f"Benign queries left unchanged: {len(BENIGN) - len(altered)}/{len(BENIGN)}")
    for text, sanitized in altered:
        print(f"  altered: {sanitized}")


if __name__ == "__main__":
    main()
