"""The row-aware grounding check: rows, answer figures, question terms and verdicts."""

import pytest

from security.row_grounding import (
    answer_figures,
    check_answer,
    parse_rows,
    question_terms,
)

INCOME = (
    "(In millions)\nYear Ended June 30,\n2016 \n2015 \nRevenue:\nProduct\n$ 61,502 \n"
    "$ 75,956 \nService and other\n23,818 \n17,624 \nTotal revenue\n85,320 \n93,580 \n"
    "Cost of revenue:\nProduct\n17,880 \n21,410 \nTotal cost of revenue\n32,780 \n33,038"
)
CHUNKS = [{"text": INCOME}]


def test_rows_collect_values_from_the_following_numeric_lines():
    rows = {r.label: r.values for r in parse_rows(INCOME)}
    assert rows["Total revenue"] == [85320.0, 93580.0]
    assert rows["Total cost of revenue"] == [32780.0, 33038.0]
    assert "Revenue:" not in rows  # a section header with no values is not a row


@pytest.mark.parametrize(
    "answer,expected",
    [
        ("Total revenue was $85,320 million.", [85_320e6]),
        ("about $4.925 billion (capital spending)", [4.925e9]),
        ("at the end of FY2019 (May 31, 2019) was $4,466 million", [4_466e6]),
        ("a margin of 34.6% in FY2022", []),
        ("$0.55 per share", [0.55]),
    ],
)
def test_answer_figures_skip_dates_years_and_percents(answer, expected):
    assert answer_figures(answer) == pytest.approx(expected)


def test_question_terms_drop_statement_names_company_names_and_months():
    terms = question_terms(
        "What was Nike's cash and equivalents at the end of FY2019 (May 31, 2019), "
        "in USD millions? Answer using the balance sheet."
    )
    assert {"cash", "equivalents"} <= terms
    assert not terms & {"nike", "may", "balance", "sheet", "fy2019"}
    assert {"cost", "revenue"} <= question_terms(
        "What is the FY2016 COGS for Microsoft?"
    )


@pytest.mark.parametrize(
    "question,answer,flagged,reason",
    [
        (
            "What was FY2016 total revenue?",
            "Total revenue was $85,320 million.",
            False,
            "supported",
        ),
        (
            "What was FY2016 total revenue?",
            "Total revenue was $85.3 billion.",
            False,
            "supported",
        ),
        # A component reported as the total: the figure is in the context, wrong row.
        (
            "What was FY2016 total revenue?",
            "Total revenue was $61,502 million.",
            True,
            "wrong_row",
        ),
        ("What is the FY2016 COGS?", "COGS was $17,880 million.", True, "wrong_row"),
        ("What is the FY2016 COGS?", "COGS was $32,780 million.", False, "supported"),
        # A partial sum: the first figure is in no row; components must not rescue it.
        (
            "What was FY2016 total cost of revenue?",
            "It was $35,000 million (product $17,880 million plus services).",
            True,
            "unsupported",
        ),
        (
            "What was FY2016 total revenue?",
            "Insufficient context.",
            False,
            "no_figures",
        ),
    ],
)
def test_check_answer(question, answer, flagged, reason):
    result = check_answer(question, answer, CHUNKS)
    assert (result.flagged, result.reason) == (flagged, reason)


def test_figures_in_thousands_match_answers_in_millions():
    chunks = [{"text": "Accounts payable\n359,555 \n312,842"}]
    result = check_answer(
        "What was accounts payable at December 31, 2017?",
        "Accounts payable was $359.6 million.",
        chunks,
    )
    assert not result.flagged
