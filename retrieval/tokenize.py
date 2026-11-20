"""Tokenizer for the BM25 (keyword) branch of hybrid retrieval."""

import re

_TOKEN = re.compile(r"[a-z0-9]+(?:[.,][0-9]+)*")


def tokenize(text: str) -> list[str]:
    """Lowercase alphanumeric tokens; keeps numbers like 1,577 or 24.26 whole.

    str.split() left punctuation attached ("2018,", "revenue.") so exact
    year/figure matches silently failed in the BM25 branch.
    """
    return _TOKEN.findall(text.lower())
