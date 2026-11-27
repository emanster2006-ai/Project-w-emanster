"""Deterministic grading for counterfactual arms. No LLM judge.

Rules (fixed before any run; see docs/COUNTERFACTUAL.md):

- Signs are ignored (cash-flow outflows appear in parentheses). Bare integers from
  1990 to 2035 without a comma are read as years and ignored.
- Every figure in the answer is read with its scale word (thousand, million,
  billion, trillion; also "m", "mn", "bn") and converted to the case's unit.
  A bare figure is taken to already be in the case's unit.
- A figure matches a target when it is within 1% of it (relative).
- Arms A, B, C have an expected figure and may have a trap figure (B: the original
  value; C: the edited irrelevant value). Outcome:
    correct    expected figure present, trap absent
    trap       trap present, expected absent (the model used the wrong figure)
    ambiguous  both present, or no figures and no refusal → hand review
    refused    a refusal phrase and no expected figure
    wrong      figures present but none match
- Arm D expects abstention. Outcome:
    correct    refusal phrase and the removed figure absent
    leaked     the removed figure appears (recovered from elsewhere or from memory)
    wrong      figures given without a refusal (an unsupported answer)
    ambiguous  neither figures nor a refusal phrase → hand review
- Provider failures are "error", never a refusal.
"""

import re

REL_TOL = 0.01
SCALES = {
    "thousand": 1e3,
    "k": 1e3,
    "million": 1e6,
    "millions": 1e6,
    "mn": 1e6,
    "m": 1e6,
    "mm": 1e6,
    "billion": 1e9,
    "billions": 1e9,
    "bn": 1e9,
    "b": 1e9,
    "trillion": 1e12,
}
UNITS = {"thousands": 1e3, "millions": 1e6, "billions": 1e9, "units": 1.0}
REFUSAL_PHRASES = (
    "insufficient context",
    "not enough information",
    "does not provide",
    "does not contain",
    "not provided in the",
    "not included in the",
    "cannot be determined",
    "unable to determine",
)

_FIGURE = re.compile(
    r"(?P<num>\d[\d,]*(?:\.\d+)?)\s*(?P<scale>thousand|millions?|mn|mm|m|billions?|bn|b|trillion|k)?\b",
    re.IGNORECASE,
)


def figures(answer: str, unit: str) -> list[float]:
    """All figures in the answer, converted to `unit` (a key of UNITS)."""
    divisor = UNITS[unit]
    out = []
    for m in _FIGURE.finditer(answer):
        raw = m.group("num").rstrip(",")
        try:
            value = float(raw.replace(",", ""))
        except ValueError:
            continue
        scale = (m.group("scale") or "").lower()
        if not scale and "," not in raw and "." not in raw and 1990 <= value <= 2035:
            continue  # a year, not a figure
        out.append(value * SCALES[scale] / divisor if scale else value)
    return out


def matches(found: list[float], target: float | None) -> bool:
    if target is None:
        return False
    return any(
        abs(f - target) <= REL_TOL * abs(target) if target else f == 0 for f in found
    )


def is_refusal(answer: str) -> bool:
    text = answer.lower()
    return any(p in text for p in REFUSAL_PHRASES)


def grade_arm(
    arm: str,
    answer: str | None,
    unit: str,
    expected: float | None,
    trap: float | None = None,
    error: str | None = None,
) -> str:
    if error or answer is None:
        return "error"
    found = figures(answer, unit)
    refused = is_refusal(answer)
    if arm == "D":
        if matches(found, trap):
            return "leaked"
        if refused:
            return "correct"
        return "wrong" if found else "ambiguous"
    has_expected, has_trap = matches(found, expected), matches(found, trap)
    if has_expected and not has_trap:
        return "correct"
    if has_expected and has_trap:
        return "ambiguous"
    if has_trap:
        return "trap"
    if refused:
        return "refused"
    return "wrong" if found else "ambiguous"


def case_passes(outcomes: dict[str, str]) -> bool:
    """A question passes only if all four arms are correct."""
    return all(outcomes.get(arm) == "correct" for arm in ("A", "B", "C", "D"))
