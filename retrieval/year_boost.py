"""Fiscal-year awareness for reranking.

The cross-encoder rarely weighs "FY2018" in a question against a chunk labelled 2022,
so chunks from a year the question names get a score bonus. Measured on 150 FinanceBench
questions (docs/BENCHMARKS.md): top-5 recall 90.0% -> 94.0% with a bonus of 3, no gain
beyond that. Set RERANK_YEAR_BONUS=0 to disable.
"""

import os
import re

DEFAULT_BONUS = 3.0
_YEAR = re.compile(r"(?<!\d)((?:19|20)\d{2})(?!\d)")
_SHORT_FY = re.compile(r"\bFY\s?'?(\d{2})(?!\d)", re.IGNORECASE)


def query_years(query: str) -> set[str]:
    """Fiscal years named in the question: 'FY2018', 'in 2018', 'FY20' or "FY '21"."""
    years = set(_YEAR.findall(query))
    years.update(f"20{yy}" for yy in _SHORT_FY.findall(query))
    return years


def year_bonus() -> float:
    try:
        return float(os.getenv("RERANK_YEAR_BONUS", DEFAULT_BONUS))
    except ValueError:
        return DEFAULT_BONUS


def apply_year_bonus(
    query: str, chunks: list[dict], scores: list[float]
) -> list[float]:
    """Return scores with the bonus added to chunks from a year the query names."""
    years, bonus = query_years(query), year_bonus()
    if not years or not bonus:
        return list(scores)
    return [
        (
            score + bonus
            if str((chunk.get("metadata") or {}).get("year")) in years
            else score
        )
        for score, chunk in zip(scores, chunks)
    ]
