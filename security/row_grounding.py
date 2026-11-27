"""Row-aware grounding check for numeric answers.

`security/grounding.py` only asks whether an answer's digits appear somewhere in the
retrieved text. That misses the substitutions the counterfactual benchmark found: a
component reported as the total (product revenue given as total revenue) uses a figure
that is in the context, just in the wrong row. It also flags correct answers that
convert units ($4.925 billion from 4,925).

This check reads the retrieved text as statement rows (a label followed by its values),
finds the rows whose label best matches the question, and accepts an answer only if one
of its figures comes from such a row, allowing for scale (thousands, millions, billions)
and rounding. It is a heuristic for flagging answers to review, not a verdict.
"""

import re
from dataclasses import dataclass

REL_TOL = 0.01
SCALES = {"thousand": 1e3, "million": 1e6, "billion": 1e9, "trillion": 1e12}
SCALE_ALIASES = {"k": "thousand", "m": "million", "mm": "million", "mn": "million",
                 "b": "billion", "bn": "billion"}  # fmt: skip

# Finance terms questions use that filings often word differently.
SYNONYMS = {
    "capex": ["capital", "spending", "expenditure", "purchases", "property"],
    "capital expenditure": ["capital", "spending", "purchases", "property"],
    "cogs": ["cost", "revenue", "sales", "goods"],
    "cost of goods sold": ["cost", "revenue", "sales"],
    "ppne": ["property", "plant", "equipment"],
    "pp&e": ["property", "plant", "equipment"],
    "ppe": ["property", "plant", "equipment"],
    "net ar": ["receivable", "receivables"],
    "accounts receivable": ["receivable", "receivables"],
    "d&a": ["depreciation", "amortization"],
}

STOPWORDS = set(
    """a an and the of for in on at to by from as is was were be been are what which
    how much many does did do has have had its it this that with into within over per
    fy year years end ending ended fiscal usd dollar dollars million millions billion
    billions thousand thousands answer answers respond response question round decimal
    place places unit units percent using use based base primarily mainly only details
    detail information info provided clearly outlined stated shown according judgments
    judgment perspective analyst investment banker public equities assume assuming
    statement statements sheet
    consolidated report reported reports company companies drawing conclusions
    give provide address adopting lost internet connection access metric metrics
    calculate calculated compute extract best abilities yourself following
    amount total quantity value""".split()
)

_NUM = re.compile(r"\(?-?\$?\s*\d[\d,]*(?:\.\d+)?\)?")
_ANSWER_FIGURE = re.compile(
    r"(?P<num>\d[\d,]*(?:\.\d+)?)\s*(?P<pct>%)?\s*(?P<scale>thousand|millions?|mn|mm|"
    r"m|billions?|bn|b|trillion|k)?\b",
    re.IGNORECASE,
)


@dataclass
class Row:
    label: str
    values: list[float]


def _to_float(raw: str) -> float | None:
    raw = raw.strip().strip("()$ ").replace(",", "").replace("$", "").strip()
    try:
        return abs(float(raw))
    except ValueError:
        return None


def parse_rows(text: str) -> list[Row]:
    """Statement rows: each text line is a label; numbers on it or on the purely
    numeric lines that follow belong to it."""
    rows: list[Row] = []
    current: Row | None = None
    for line in text.splitlines():
        stripped = line.strip()
        if not stripped:
            continue
        if re.search(r"[A-Za-z]", stripped):
            label = _NUM.sub(" ", stripped)
            current = Row(label=" ".join(label.split()), values=[])
            rows.append(current)
            nums = [_to_float(m.group(0)) for m in _NUM.finditer(stripped)]
        else:
            nums = [_to_float(m.group(0)) for m in _NUM.finditer(stripped)]
        if current is not None:
            current.values.extend(v for v in nums if v is not None)
    return [r for r in rows if r.values]


# Names of statements say where to look, not which line item: drop them as phrases so
# "cash", "income" and "balance" still count in "cash and equivalents" or "net income".
STATEMENT_NAMES = re.compile(
    r"(consolidated )?(statements? of (cash flows?|income|operations|earnings|"
    r"financial position)|cash ?flows? statements?|income statements?|"
    r"balance sheets?|p&l)"
)

MONTHS = set(
    "january february march april may june july august september october november "
    "december".split()
)


def question_terms(question: str) -> set[str]:
    """Content words of the question, expanded with finance synonyms. Company names
    (capitalized words that are not acronyms) and months are dropped: they say which
    filing, not which line item, and they match headers and prose."""
    names = {
        w.lower()
        for w in re.findall(r"\b[A-Z][a-z][A-Za-z&]*", question)
        if w.lower() not in STOPWORDS
    }
    q = STATEMENT_NAMES.sub(" ", question.lower())
    terms = {
        w
        for w in re.findall(r"[a-z&]+", q)
        if len(w) >= 3
        and w not in STOPWORDS
        and w not in MONTHS
        and w not in names
        and not re.fullmatch(r"fy\d*", w)
    }
    for key, extra in SYNONYMS.items():
        if key in q:
            terms.update(extra)
    return terms


def label_score(label: str, terms: set[str]) -> int:
    squashed = re.sub(r"[^a-z]", "", label.lower())
    return sum(
        1 for t in terms if re.sub(r"[^a-z]", "", t) and t.replace("&", "") in squashed
    )


def answer_figures(answer: str) -> list[float]:
    """Figures in absolute units where a scale word is given; bare figures as written.
    Years, percentages and small bare integers (days in dates) are skipped."""
    out = []
    for m in _ANSWER_FIGURE.finditer(answer):
        if m.group("pct"):
            continue
        num = m.group("num").rstrip(",.")
        value = _to_float(num)
        if value is None:
            continue
        scale = (m.group("scale") or "").lower().rstrip("s") if m.group("scale") else ""
        scale = SCALE_ALIASES.get(scale, scale)
        bare = not scale and "," not in num and "." not in num
        has_dollar = "$" in answer[max(0, m.start() - 2) : m.start()]
        if bare and 1990 <= value <= 2035:
            continue  # a year
        if bare and not has_dollar and value < 100:
            continue  # a day of the month, a count, a footnote: not a reported figure
        out.append(value * SCALES[scale] if scale in SCALES else value)
    return out


def _same(answer_value: float, row_value: float) -> bool:
    """Does an answer figure equal a row figure at some reporting scale?"""
    if answer_value == 0 or row_value == 0:
        return answer_value == row_value
    for scale in (1.0, 1e3, 1e6, 1e9, 1e-3):
        candidate = row_value * scale
        if abs(candidate - answer_value) <= REL_TOL * answer_value:
            return True
    return False


@dataclass
class RowCheck:
    flagged: bool
    reason: str  # "supported", "wrong_row", "unsupported" or "no_figures"


def check_answer(question: str, answer: str, chunks: list[dict]) -> RowCheck:
    """Flag a numeric answer whose stated figure does not come from a row matching the
    question. The answer's first figure is taken as its answer; later figures are often
    the components it was (wrongly) built from, so they must not rescue it."""
    figures = answer_figures(answer)
    if not figures:
        return RowCheck(False, "no_figures")
    primary = figures[0]
    rows = [r for c in chunks for r in parse_rows(c["text"])]
    terms = question_terms(question)
    scores = [label_score(r.label, terms) for r in rows]
    best = max(scores, default=0)
    # Rows close to the best match count, so a table row is not out-scored by a prose
    # sentence that repeats one more word of the question.
    good_enough = max(1, -(-2 * best // 3))  # ceil(2/3 of best)
    holders = [
        s for r, s in zip(rows, scores) if any(_same(primary, v) for v in r.values)
    ]
    if not holders:
        return RowCheck(True, "unsupported")
    if best > 0 and max(holders) >= good_enough:
        return RowCheck(False, "supported")
    return RowCheck(True, "wrong_row")
