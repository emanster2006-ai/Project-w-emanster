"""Regenerate the cases in evaluation/counterfactual/manifest.json from row-level specs.

  python evaluation/counterfactual/build_manifest.py .
  python scripts/counterfactual_run.py --check-fixtures

Eligibility, the split rule and exclusions are kept from the existing manifest. Each
spec names rows by their label as it appears in the captured text; `cell` edits one
column, `num` edits a figure everywhere, `drop` removes a row.
"""

import hashlib
import json
import re
import sys
from pathlib import Path

REPO = Path(sys.argv[1])
SEP = r"[\s$]*"
VAL = r"\(?[\d,.]+\)?"


def esc(s):
    return re.escape(s)


def cell(label, k, old, new):
    """Replace the k-th value (0-based) of the row starting with `label`."""
    return {
        "re": "(" + esc(label) + SEP + (VAL + SEP) * k + r"\(?)" + esc(old) + r"(?!\d)",
        "sub": r"\g<1>" + new,
    }


def num(old, new):
    """Replace a figure everywhere it appears as a whole number."""
    return {"re": r"(?<![\d.,])" + esc(old) + r"(?!\d)", "sub": new}


def drop(label, first, n=3):
    """Remove the row starting with `label` whose first value is `first`."""
    return {
        "re": esc(label)
        + SEP
        + r"\(?"
        + esc(first)
        + r"\)?"
        + SEP
        + "(?:"
        + VAL
        + SEP
        + "){0,%d}" % (n - 1),
        "sub": "",
    }


CASES = [
    dict(
        id="financebench_id_04980",
        doc_name="PEPSICO_2021_10K",
        pilot=True,
        metric="FY2021 capital spending (cash flow statement)",
        unit="billions",
        expected={"A": 4.625, "B": 4.925, "C": 4.625},
        trap={"B": 4.625, "C": 4.04, "D": 4.625},
        arms={
            "B": dict(
                ops=[
                    num("(4,625)", "(4,925)"),
                    cell("Net Cash Used for Investing Activities", 0, "3,269", "3,569"),
                ],
                gone=["4,625", "3,269"],
                present=["4,925"],
            ),
            "C": dict(
                ops=[
                    num("(4,240)", "(4,040)"),
                    cell(
                        "Net Cash Used for Investing Activities", 1, "11,619", "11,419"
                    ),
                ],
                gone=["4,240", "11,619"],
                present=["4,625", "4,040"],
            ),
            "D": dict(
                ops=[
                    drop("Capital spending", "4,625"),
                    drop("Capital spending", "5,207"),
                    drop("Net Cash Used for Investing Activities", "3,269"),
                ],
                gone=["4,625", "3,269"],
            ),
        },
        audit="Capex appears in three overlapping 2021-10-K chunks (FY2021 first column) and in a 2022-10-K chunk (FY2021 second column); all are edited. The FY2021 investing total sums exactly to -3,269 including capex, so B and C move it and D removes it. No prose mention of $4.6 billion in the captured chunks.",
    ),
    dict(
        id="financebench_id_04417",
        doc_name="BESTBUY_2019_10K",
        pilot=True,
        metric="Merchandise inventories at fiscal year end 2019 (Feb 2, 2019)",
        unit="millions",
        expected={"A": 5409, "B": 5709, "C": 5409},
        trap={"B": 5409, "C": 5009, "D": 5409},
        arms={
            "B": dict(
                ops=[
                    cell("Merchandiseinventories", 0, "5,409", "5,709"),
                    cell("Totalcurrentassets", 0, "8,870", "9,170"),
                ],
                gone=["5,409", "8,870"],
                present=["5,709"],
            ),
            "C": dict(
                ops=[
                    cell("Merchandiseinventories", 1, "5,209", "5,009"),
                    cell("Totalcurrentassets", 1, "9,829", "9,629"),
                ],
                gone=["5,209", "9,829"],
                present=["5,409", "5,009"],
            ),
            "D": dict(
                ops=[
                    drop("Merchandiseinventories", "5,409", 2),
                    drop("Totalcurrentassets", "8,870", 2),
                ],
                gone=["5,409", "8,870"],
            ),
        },
        audit="Inventories and total current assets appear once, in the FY2019 balance sheet chunk; total assets is not in the captured context. Raising inventories raises total current assets by the same amount.",
    ),
    dict(
        id="financebench_id_03531",
        doc_name="NIKE_2019_10K",
        pilot=True,
        metric="Total current assets at May 31, 2019",
        unit="millions",
        expected={"A": 16525, "B": 17525, "C": 16525},
        trap={"B": 16525, "C": 14534, "D": 16525},
        arms={
            "B": dict(
                ops=[
                    cell(
                        "Prepaid expenses and other current assets", 0, "1,968", "2,968"
                    ),
                    cell("Total current assets", 0, "16,525", "17,525"),
                    cell("Deferred income taxes and other assets", 0, "2,011", "1,011"),
                ],
                gone=["16,525", "1,968", "2,011"],
                present=["17,525"],
            ),
            "C": dict(
                ops=[
                    cell(
                        "Prepaid expenses and other current assets", 1, "1,130", "530"
                    ),
                    cell("Total current assets", 1, "15,134", "14,534"),
                    num("2,509", "3,109"),
                ],  # chunk 2 starts mid-row
                gone=["15,134", "1,130", "2,509"],
                present=["16,525", "14,534"],
            ),
            "D": dict(
                ops=[
                    drop("Total current assets", "16,525", 2),
                    drop("Prepaid expenses and other current assets", "1,968", 2),
                    drop("TOTAL ASSETS", "23,717", 2),
                    drop("TOTAL LIABILITIES AND SHAREHOLDERS' EQUITY", "23,717", 2),
                ],
                gone=["16,525", "1,968", "23,717"],
            ),
        },
        audit="The FY2019 balance sheet appears in three overlapping chunks. B and C move prepaid expenses and total current assets and offset the change in deferred income taxes and other assets, so total assets and the balance-sheet identity are unchanged. D removes the subtotal, one component and both balance-sheet totals; recovering the figure would take several subtractions from rows that remain (total liabilities and equity are removed).",
    ),
    dict(
        id="financebench_id_03282",
        doc_name="NETFLIX_2017_10K",
        metric="Total current liabilities at Dec 31, 2017 (filing in thousands)",
        unit="millions",
        expected={"A": 5466.312, "B": 5816.312, "C": 5466.312},
        trap={"B": 5466.312, "C": 4386.657, "D": 5466.312},
        arms={
            "B": dict(
                ops=[
                    cell("Deferred revenue", 0, "618,622", "968,622"),
                    cell("Total current liabilities", 0, "5,466,312", "5,816,312"),
                    cell(
                        "Non-current content liabilities", 0, "3,329,796", "2,979,796"
                    ),
                ],
                gone=["5,466,312", "618,622", "3,329,796"],
                present=["5,816,312"],
            ),
            "C": dict(
                ops=[
                    cell("Deferred revenue", 1, "443,472", "243,472"),
                    cell("Total current liabilities", 1, "4,586,657", "4,386,657"),
                    cell(
                        "Non-current content liabilities", 1, "2,894,654", "3,094,654"
                    ),
                ],
                gone=["4,586,657", "443,472", "2,894,654"],
                present=["5,466,312", "4,386,657"],
            ),
            "D": dict(
                ops=[
                    drop("Total current liabilities", "5,466,312", 2),
                    drop("Deferred revenue", "618,622", 2),
                    drop("Total liabilities", "15,430,786", 2),
                ],
                gone=["5,466,312", "618,622", "15,430,786"],
            ),
        },
        audit="B and C move deferred revenue and total current liabilities and offset non-current content liabilities, so total liabilities and the balance-sheet identity are unchanged. D removes the subtotal, one component and total liabilities; total liabilities and equity minus equity minus non-current rows would still recover it in several steps.",
    ),
    dict(
        id="financebench_id_04209",
        doc_name="COSTCO_2021_10K",
        metric="Total assets at fiscal year end 2021",
        unit="millions",
        expected={"A": 59268, "B": 62268, "C": 59268},
        trap={"B": 59268, "C": 54056, "D": 59268},
        arms={
            "B": dict(
                ops=[
                    cell("Other long-term assets", 0, "3,381", "6,381"),
                    num("59,268", "62,268"),
                    cell("Other long-term liabilities", 0, "2,415", "5,415"),
                    cell("TOTAL LIABILITIES", 0, "41,190", "44,190"),
                ],
                gone=["59,268", "3,381", "2,415", "41,190"],
                present=["62,268"],
            ),
            "C": dict(
                ops=[
                    cell("Other long-term assets", 1, "2,841", "1,341"),
                    num("55,556", "54,056"),
                    cell("Other long-term liabilities", 1, "1,935", "435"),
                    cell("TOTAL LIABILITIES", 1, "36,851", "35,351"),
                ],
                gone=["55,556", "2,841", "1,935", "36,851"],
                present=["59,268", "54,056"],
            ),
            "D": dict(
                ops=[
                    drop("TOTAL ASSETS", "59,268", 2),
                    drop("TOTAL LIABILITIES AND EQUITY", "59,268", 2),
                    drop("TOTAL LIABILITIES", "41,190", 2),
                    drop("Other long-term assets", "3,381", 2),
                ],
                gone=["59,268", "41,190", "3,381"],
            ),
        },
        audit="B and C move one asset row and one liability row by the same amount, with total assets, total liabilities and total liabilities and equity, so both sides balance. D removes both totals, total liabilities and one asset component; recovering it would take summing several liability and equity rows.",
    ),
    dict(
        id="financebench_id_04700",
        doc_name="MICROSOFT_2016_10K",
        metric="FY2016 total cost of revenue",
        unit="millions",
        expected={"A": 32780, "B": 34780, "C": 32780},
        trap={"B": 32780, "C": 31538, "D": 32780},
        arms={
            "B": dict(
                ops=[
                    cell("Service and other", 0, "14,900", "16,900"),
                    cell("Total cost of revenue", 0, "32,780", "34,780"),
                    cell("Service and other", 0, "23,818", "25,818"),
                    cell("Total revenue", 0, "85,320", "87,320"),
                ],
                gone=["32,780", "14,900", "85,320"],
                present=["34,780"],
            ),
            "C": dict(
                ops=[
                    cell("Service and other", 1, "11,628", "10,128"),
                    num("33,038", "31,538"),
                    cell("Service and other", 1, "17,624", "16,124"),
                    cell("Total revenue", 1, "93,580", "92,080"),
                ],
                gone=["33,038", "11,628", "93,580"],
                present=["32,780", "31,538"],
            ),
            "D": dict(
                ops=[
                    drop("Total cost of revenue", "32,780"),
                    drop("Service and other", "14,900"),
                    drop("Gross margin", "52,540"),
                ],
                gone=["32,780", "14,900", "52,540"],
            ),
        },
        audit="B and C move service cost and service revenue by the same amount with both totals, so gross margin and everything below it are unchanged. D removes total cost of revenue, the service cost row and gross margin (cost = revenue - gross margin); operating expenses and operating income remain, so a multi-step recovery is still possible.",
    ),
    dict(
        id="financebench_id_07661",
        doc_name="BLOCK_2020_10K",
        metric="FY2020 net cash provided by operating activities (filing in thousands)",
        unit="millions",
        expected={"A": 381.603, "B": 406.603, "C": 381.603},
        trap={"B": 381.603, "C": 435.699, "D": 381.603},
        arms={
            "B": dict(
                ops=[
                    cell("Customerspayable", 0, "1,733,138", "1,758,138"),
                    cell(
                        "Netcashprovidedbyoperatingactivities", 0, "381,603", "406,603"
                    ),
                    num("2,103,157", "2,128,157"),
                    num("3,201,863", "3,226,863"),
                ],
                gone=["381,603", "1,733,138", "2,103,157"],
                present=["406,603"],
            ),
            "C": dict(
                ops=[
                    cell("Customerspayable", 1, "523,795", "493,795"),
                    cell(
                        "Netcashprovidedbyoperatingactivities", 1, "465,699", "435,699"
                    ),
                    num("465,859", "435,859"),
                    num("1,098,706", "1,068,706"),
                ],
                gone=["465,699", "523,795", "465,859"],
                present=["381,603", "435,699"],
            ),
            "D": dict(
                ops=[
                    drop("Netcashprovidedbyoperatingactivities", "381,603"),
                    drop("Customerspayable", "1,733,138"),
                    drop(
                        "Netincrease(decrease)incash,cashequivalentsandrestrictedcash",
                        "2,103,157",
                    ),
                    drop("cashequivalentsandrestrictedcash", "2,103,157"),
                ],  # chunk 4 splits the label
                gone=["381,603", "1,733,138", "2,103,157"],
            ),
        },
        audit="B and C move one operating item, operating cash flow, the net change in cash and the affected year-end cash balance by the same amount. D removes operating cash flow, one component and the net change in cash; beginning and ending cash with the investing and financing totals would still recover it in several steps.",
    ),
    dict(
        id="financebench_id_08286",
        doc_name="AMAZON_2019_10K",
        metric="FY2019 net income (third column: 2017, 2018, 2019)",
        unit="millions",
        expected={"A": 11588, "B": 12288, "C": 11588},
        trap={"B": 11588, "C": 9573, "D": 11588},
        arms={
            "B": dict(
                ops=[
                    cell("Net income", 2, "11,588", "12,288"),
                    cell("Provision for income taxes", 2, "2,374", "1,674"),
                    cell("Basic earnings per share", 2, "23.46", "24.87"),
                    cell("Diluted earnings per share", 2, "23.01", "24.38"),
                ],
                gone=["11,588", "2,374", "23.46"],
                present=["12,288"],
            ),
            "C": dict(
                ops=[
                    cell("Net income", 1, "10,073", "9,573"),
                    cell("Provision for income taxes", 1, "1,197", "1,697"),
                    cell("Basic earnings per share", 1, "20.68", "19.66"),
                    cell("Diluted earnings per share", 1, "20.14", "19.15"),
                ],
                gone=["10,073", "1,197", "20.68"],
                present=["11,588", "9,573"],
            ),
            "D": dict(
                ops=[
                    drop("Net income", "3,033"),
                    drop("Provision for income taxes", "769"),
                    drop("Basic earnings per share", "6.32"),
                    drop("Diluted earnings per share", "6.15"),
                ],
                gone=["11,588", "2,374", "23.46"],
            ),
        },
        audit="B and C change net income through the tax provision, so income before taxes and every line above it are unchanged; earnings per share are recomputed from the weighted shares shown. D removes net income, the tax provision and both EPS rows (EPS x shares would recover it).",
    ),
    dict(
        id="financebench_id_10285",
        doc_name="BOEING_2018_10K",
        metric="Property, plant and equipment, net, at Dec 31, 2018",
        unit="millions",
        expected={"A": 12645, "B": 13445, "C": 12645},
        trap={"B": 12645, "C": 12172, "D": 12645},
        arms={
            "B": dict(
                ops=[
                    cell("Property, plant and equipment, net", 0, "12,645", "13,445"),
                    cell("Investments", 0, "1,087", "287"),
                ],
                gone=["12,645", "1,087"],
                present=["13,445"],
            ),
            "C": dict(
                ops=[
                    cell("Property, plant and equipment, net", 1, "12,672", "12,172"),
                    cell("Investments", 1, "1,260", "1,760"),
                ],
                gone=["12,672", "1,260"],
                present=["12,645", "12,172"],
            ),
            "D": dict(
                ops=[
                    drop("Property, plant and equipment, net", "12,645", 2),
                    drop("Total assets", "117,359", 2),
                    drop("Total liabilities and equity", "117,359", 2),
                ],
                gone=["12,645", "117,359"],
            ),
        },
        audit="B and C offset the PP&E change in investments, so total assets and the balance-sheet identity are unchanged. D removes PP&E and both balance-sheet totals; total liabilities plus total equity minus the other asset rows would still recover it in several steps.",
    ),
]

# Author-written questions (evaluation/counterfactual/author_questions.json). Each moves the
# target and offsets a sibling row under the same subtotal, so no subtotal changes.
AUTHOR_CASES = [
    dict(
        id="author_04980_1",
        parent="financebench_id_04980",
        metric="FY2021 net cash provided by operating activities",
        unit="millions",
        expected={"A": 11616, "B": 12316, "C": 11616},
        trap={"B": 11616, "C": 10113, "D": 11616},
        arms={
            "B": dict(
                ops=[
                    num("11,616", "12,316"),
                    cell(
                        "Accounts payable and other current liabilities",
                        0,
                        "1,762",
                        "2,462",
                    ),
                    cell(
                        "Accounts payable and other current liabilities",
                        1,
                        "1,762",
                        "2,462",
                    ),
                ],
                gone=["11,616", "1,762"],
                present=["12,316"],
            ),
            "C": dict(
                ops=[
                    num("10,613", "10,113"),
                    cell(
                        "Accounts payable and other current liabilities",
                        1,
                        "766",
                        "266",
                    ),
                    cell(
                        "Accounts payable and other current liabilities",
                        2,
                        "766",
                        "266",
                    ),
                ],
                gone=["10,613"],
                present=["11,616", "10,113"],
            ),
            "D": dict(
                ops=[
                    drop("Net Cash Provided by Operating Activities", "11,616"),
                    drop("Net Cash Provided by Operating Activities", "10,811"),
                    drop("Accounts payable and other current liabilities", "1,762"),
                    drop("Accounts payable and other current liabilities", "1,842"),
                ],
                gone=["11,616", "1,762"],
            ),
        },
        audit="Operating cash flow appears in the 2021 10-K (first column) and the 2022 10-K (second column); B and C move it with one operating component in both filings. The net change in cash is not in the captured context. D removes operating cash flow and that component in both filings.",
    ),
    dict(
        id="author_04980_2",
        parent="financebench_id_04980",
        metric="FY2021 sales of property, plant and equipment (cash flow)",
        unit="millions",
        expected={"A": 166, "B": 226, "C": 166},
        trap={"B": 166, "C": 35, "D": 166},
        arms={
            "B": dict(
                ops=[
                    num("166", "226"),
                    cell(
                        "Divestitures and sales of investments in noncontrolled affiliates",
                        0,
                        "169",
                        "109",
                    ),
                ],
                gone=["166", "169"],
                present=["226"],
            ),
            "C": dict(
                ops=[
                    cell("Sales of property, plant and equipment", 1, "55", "35"),
                    cell("Sales of property, plant and equipment", 2, "55", "35"),
                    cell(
                        "plant and equipment", 1, "55", "35"
                    ),  # chunk 3 starts mid-label
                    cell(
                        "Divestitures and sales of investments in noncontrolled affiliates",
                        1,
                        "6",
                        "26",
                    ),
                ],
                gone=[],
                present=["166", "35"],
            ),  # "55" also appears in an unrelated row
            "D": dict(
                ops=[
                    drop("Sales of property, plant and equipment", "166"),
                    drop("Sales of property, plant and equipment", "251"),
                    drop("plant and equipment", "166"),  # chunk 3 starts mid-label
                    drop("Net Cash Used for Investing Activities", "3,269"),
                ],
                gone=["166", "3,269"],
            ),
        },
        audit="Chunk 3 starts mid-label ('plant and equipment'), so it gets its own edit. B and C offset the change in divestitures within the 2021 10-K's investing section, so the investing total holds there; the 2022 10-K's FY2021 investing column is not rebalanced (its total is not in the captured chunk). D removes the row in both filings and the 2021 investing total.",
    ),
    dict(
        id="author_04417_1",
        parent="financebench_id_04417",
        metric="Cash and cash equivalents at Feb 2, 2019",
        unit="millions",
        expected={"A": 1980, "B": 2100, "C": 1980},
        trap={"B": 1980, "C": 1001, "D": 1980},
        arms={
            "B": dict(
                ops=[
                    cell("Cashandcashequivalents", 0, "1,980", "2,100"),
                    cell("Othercurrentassets", 0, "466", "346"),
                ],
                gone=["1,980"],
                present=["2,100"],
            ),
            "C": dict(
                ops=[
                    cell("Cashandcashequivalents", 1, "1,101", "1,001"),
                    cell("Short-terminvestments", 0, "2,032", "2,132"),
                ],
                gone=["1,101", "2,032"],
                present=["1,980", "1,001"],
            ),
            "D": dict(
                ops=[
                    drop("Cashandcashequivalents", "1,980", 2),
                    drop("Totalcurrentassets", "8,870", 2),
                ],
                gone=["1,980", "8,870"],
            ),
        },
        audit="B offsets other current assets, C offsets the prior-year short-term investments, so total current assets is unchanged. D removes cash and total current assets.",
    ),
    dict(
        id="author_04417_2",
        parent="financebench_id_04417",
        metric="Receivables, net at Feb 2, 2019",
        unit="millions",
        expected={"A": 1015, "B": 1115, "C": 1015},
        trap={"B": 1015, "C": 949, "D": 1015},
        arms={
            "B": dict(
                ops=[
                    cell("Receivables,net", 0, "1,015", "1,115"),
                    cell("Othercurrentassets", 0, "466", "366"),
                ],
                gone=["1,015"],
                present=["1,115"],
            ),
            "C": dict(
                ops=[
                    cell("Receivables,net", 1, "1,049", "949"),
                    cell("Othercurrentassets", 1, "438", "538"),
                ],
                gone=["1,049"],
                present=["1,015", "949"],
            ),
            "D": dict(
                ops=[
                    drop("Receivables,net", "1,015", 2),
                    drop("Totalcurrentassets", "8,870", 2),
                ],
                gone=["1,015", "8,870"],
            ),
        },
        audit="B and C offset other current assets, so total current assets is unchanged. D removes receivables and total current assets.",
    ),
    dict(
        id="author_03531_1",
        parent="financebench_id_03531",
        metric="Cash and equivalents at May 31, 2019",
        unit="millions",
        expected={"A": 4466, "B": 4766, "C": 4466},
        trap={"B": 4466, "C": 3949, "D": 4466},
        arms={
            "B": dict(
                ops=[
                    cell("Cash and equivalents", 0, "4,466", "4,766"),
                    cell("Inventories", 0, "5,622", "5,322"),
                ],
                gone=["4,466", "5,622"],
                present=["4,766"],
            ),
            "C": dict(
                ops=[
                    cell("Cash and equivalents", 1, "4,249", "3,949"),
                    cell("Inventories", 1, "5,261", "5,561"),
                ],
                gone=["4,249", "5,261"],
                present=["4,466", "3,949"],
            ),
            "D": dict(
                ops=[
                    drop("Cash and equivalents", "4,466", 2),
                    drop("Total current assets", "16,525", 2),
                ],
                gone=["4,466", "16,525"],
            ),
        },
        audit="B and C offset inventories, so total current assets is unchanged. D removes cash and total current assets.",
    ),
    dict(
        id="author_03531_2",
        parent="financebench_id_03531",
        metric="Inventories at May 31, 2019",
        unit="millions",
        expected={"A": 5622, "B": 5972, "C": 5622},
        trap={"B": 5622, "C": 4961, "D": 5622},
        arms={
            "B": dict(
                ops=[
                    cell("Inventories", 0, "5,622", "5,972"),
                    cell("Cash and equivalents", 0, "4,466", "4,116"),
                ],
                gone=["5,622", "4,466"],
                present=["5,972"],
            ),
            "C": dict(
                ops=[
                    cell("Inventories", 1, "5,261", "4,961"),
                    cell("Cash and equivalents", 1, "4,249", "4,549"),
                ],
                gone=["5,261", "4,249"],
                present=["5,622", "4,961"],
            ),
            "D": dict(
                ops=[
                    drop("Inventories", "5,622", 2),
                    drop("Total current assets", "16,525", 2),
                ],
                gone=["5,622", "16,525"],
            ),
        },
        audit="B and C offset cash, so total current assets is unchanged. The 2021 10-K's inventories row (other years) is left as a distractor. D removes inventories and total current assets.",
    ),
    dict(
        id="author_03282_1",
        parent="financebench_id_03282",
        metric="Accounts payable (balance sheet) at Dec 31, 2017, filing in thousands",
        unit="millions",
        expected={"A": 359.555, "B": 384.555, "C": 359.555},
        trap={"B": 359.555, "C": 292.842, "D": 359.555},
        arms={
            "B": dict(
                ops=[
                    cell("Accounts payable", 0, "359,555", "384,555"),
                    cell("Accrued expenses", 0, "315,094", "290,094"),
                ],
                gone=["359,555", "315,094"],
                present=["384,555"],
            ),
            "C": dict(
                ops=[
                    cell("Accounts payable", 1, "312,842", "292,842"),
                    cell("Accrued expenses", 1, "197,632", "217,632"),
                ],
                gone=["312,842", "197,632"],
                present=["359,555", "292,842"],
            ),
            "D": dict(
                ops=[
                    drop("Accounts payable", "359,555", 2),
                    drop("Total current liabilities", "5,466,312", 2),
                    drop("Total liabilities", "15,430,786", 2),
                ],
                gone=["359,555", "5,466,312", "15,430,786"],
            ),
        },
        audit="B and C offset accrued expenses, so total current liabilities is unchanged. The cash flow statement's 'Accounts payable' row (the change in payables) is left as a distractor. D removes accounts payable, total current liabilities and total liabilities.",
    ),
    dict(
        id="author_03282_2",
        parent="financebench_id_03282",
        metric="Long-term debt at Dec 31, 2017, filing in thousands",
        unit="millions",
        expected={"A": 6499.432, "B": 6899.432, "C": 6499.432},
        trap={"B": 6499.432, "C": 3164.311, "D": 6499.432},
        arms={
            "B": dict(
                ops=[
                    cell("Long-term debt", 0, "6,499,432", "6,899,432"),
                    cell(
                        "Non-current content liabilities", 0, "3,329,796", "2,929,796"
                    ),
                ],
                gone=["6,499,432", "3,329,796"],
                present=["6,899,432"],
            ),
            "C": dict(
                ops=[
                    cell("Long-term debt", 1, "3,364,311", "3,164,311"),
                    cell(
                        "Non-current content liabilities", 1, "2,894,654", "3,094,654"
                    ),
                ],
                gone=["3,364,311", "2,894,654"],
                present=["6,499,432", "3,164,311"],
            ),
            "D": dict(
                ops=[
                    drop("Long-term debt", "6,499,432", 2),
                    drop("Total liabilities", "15,430,786", 2),
                ],
                gone=["6,499,432", "15,430,786"],
            ),
        },
        audit="B and C offset non-current content liabilities, so total liabilities is unchanged. D removes long-term debt and total liabilities.",
    ),
    dict(
        id="author_04209_1",
        parent="financebench_id_04209",
        metric="Accounts payable at fiscal year end 2021",
        unit="millions",
        expected={"A": 16278, "B": 17278, "C": 16278},
        trap={"B": 16278, "C": 13172, "D": 16278},
        arms={
            "B": dict(
                ops=[
                    cell("Accounts payable", 0, "16,278", "17,278"),
                    cell("Other current liabilities", 0, "4,561", "3,561"),
                ],
                gone=["16,278", "4,561"],
                present=["17,278"],
            ),
            "C": dict(
                ops=[
                    cell("Accounts payable", 1, "14,172", "13,172"),
                    cell("Other current liabilities", 1, "3,728", "4,728"),
                ],
                gone=["14,172", "3,728"],
                present=["16,278", "13,172"],
            ),
            "D": dict(
                ops=[
                    drop("Accounts payable", "16,278", 2),
                    drop("Total current liabilities", "29,441", 2),
                    drop("TOTAL LIABILITIES", "41,190", 2),
                ],
                gone=["16,278", "29,441", "41,190"],
            ),
        },
        audit="B and C offset other current liabilities, so total current liabilities is unchanged. D removes accounts payable, total current liabilities and total liabilities.",
    ),
    dict(
        id="author_04209_2",
        parent="financebench_id_04209",
        metric="Merchandise inventories at fiscal year end 2021",
        unit="millions",
        expected={"A": 14215, "B": 15115, "C": 14215},
        trap={"B": 14215, "C": 11542, "D": 14215},
        arms={
            "B": dict(
                ops=[
                    cell("Merchandise inventories", 0, "14,215", "15,115"),
                    cell("Cash and cash equivalents", 0, "11,258", "10,358"),
                ],
                gone=["14,215", "11,258"],
                present=["15,115"],
            ),
            "C": dict(
                ops=[
                    cell("Merchandise inventories", 1, "12,242", "11,542"),
                    cell("Cash and cash equivalents", 1, "12,277", "12,977"),
                ],
                gone=["12,242", "12,277"],
                present=["14,215", "11,542"],
            ),
            "D": dict(
                ops=[
                    drop("Merchandise inventories", "14,215", 2),
                    drop("Total current assets", "29,505", 2),
                ],
                gone=["14,215", "29,505"],
            ),
        },
        audit="B and C offset cash, so total current assets is unchanged. D removes inventories and total current assets.",
    ),
]

AUTHOR_CASES += [
    dict(
        id="author_04700_1",
        parent="financebench_id_04700",
        metric="FY2016 research and development expense",
        unit="millions",
        expected={"A": 11988, "B": 12688, "C": 11988},
        trap={"B": 11988, "C": 11546, "D": 11988},
        arms={
            "B": dict(
                ops=[
                    cell("Research and development", 0, "11,988", "12,688"),
                    cell("Sales and marketing", 0, "14,697", "13,997"),
                ],
                gone=["11,988", "14,697"],
                present=["12,688"],
            ),
            "C": dict(
                ops=[cell("Research and development", 1, "12,046", "11,546")],
                gone=["12,046"],
                present=["11,988", "11,546"],
            ),
            "D": dict(
                ops=[
                    drop("Research and development", "11,988"),
                    drop("Operating income", "20,182"),
                ],
                gone=["11,988", "20,182"],
            ),
        },
        audit="B offsets sales and marketing so operating income is unchanged. C has no visible offset: the FY2015 sales and marketing value is cut off at the chunk boundary, so FY2015 operating expenses no longer add up to an operating income that is itself not in the captured text. D removes R&D and operating income.",
    ),
    dict(
        id="author_04700_2",
        parent="financebench_id_04700",
        metric="FY2016 total revenue",
        unit="millions",
        expected={"A": 85320, "B": 87320, "C": 85320},
        trap={"B": 85320, "C": 91580, "D": 85320},
        arms={
            "B": dict(
                ops=[
                    cell("Product", 0, "61,502", "63,502"),
                    cell("Total revenue", 0, "85,320", "87,320"),
                    cell("Product", 0, "17,880", "19,880"),
                    cell("Total cost of revenue", 0, "32,780", "34,780"),
                ],
                gone=["85,320", "61,502", "17,880", "32,780"],
                present=["87,320"],
            ),
            "C": dict(
                ops=[
                    cell("Product", 1, "75,956", "73,956"),
                    num("93,580", "91,580"),
                    cell("Product", 1, "21,410", "19,410"),
                    num("33,038", "31,038"),
                ],
                gone=["93,580", "75,956", "21,410", "33,038"],
                present=["85,320", "91,580"],
            ),
            "D": dict(
                ops=[
                    drop("Total revenue", "85,320"),
                    drop("Service and other", "23,818"),
                    drop("Gross margin", "52,540"),
                ],
                gone=["85,320", "23,818", "52,540"],
            ),
        },
        audit="B and C move product revenue and product cost by the same amount, with both totals, so gross margin and everything below it are unchanged. D removes total revenue, the service revenue row and gross margin (revenue = cost + gross margin).",
    ),
    dict(
        id="author_07661_1",
        parent="financebench_id_07661",
        metric="FY2020 transaction and loan losses (cash flow), filing in thousands",
        unit="millions",
        expected={"A": 177.670, "B": 189.670, "C": 177.670},
        trap={"B": 177.670, "C": 116.959, "D": 177.670},
        arms={
            "B": dict(
                ops=[
                    cell("Transactionandloanlosses", 0, "177,670", "189,670"),
                    cell("Non-cashinterestandother", 0, "76,129", "64,129"),
                ],
                gone=["177,670", "76,129"],
                present=["189,670"],
            ),
            "C": dict(
                ops=[
                    cell("Transactionandloanlosses", 1, "126,959", "116,959"),
                    cell("Non-cashinterestandother", 1, "33,478", "43,478"),
                ],
                gone=["126,959", "33,478"],
                present=["177,670", "116,959"],
            ),
            "D": dict(
                ops=[
                    drop("Transactionandloanlosses", "177,670"),
                    drop("Netcashprovidedbyoperatingactivities", "381,603"),
                ],
                gone=["177,670", "381,603"],
            ),
        },
        audit="B and C offset non-cash interest and other, so operating cash flow is unchanged. D removes the row and operating cash flow.",
    ),
    dict(
        id="author_07661_2",
        parent="financebench_id_07661",
        metric="FY2020 depreciation and amortization (cash flow), filing in thousands",
        unit="millions",
        expected={"A": 84.212, "B": 89.212, "C": 84.212},
        trap={"B": 84.212, "C": 70.598, "D": 84.212},
        arms={
            "B": dict(
                ops=[
                    cell("Depreciationandamortization", 0, "84,212", "89,212"),
                    cell("Non-cashinterestandother", 0, "76,129", "71,129"),
                ],
                gone=["84,212", "76,129"],
                present=["89,212"],
            ),
            "C": dict(
                ops=[
                    cell("Depreciationandamortization", 1, "75,598", "70,598"),
                    cell("Non-cashinterestandother", 1, "33,478", "38,478"),
                ],
                gone=["75,598", "33,478"],
                present=["84,212", "70,598"],
            ),
            "D": dict(
                ops=[
                    drop("Depreciationandamortization", "84,212"),
                    drop("Netcashprovidedbyoperatingactivities", "381,603"),
                ],
                gone=["84,212", "381,603"],
            ),
        },
        audit="B and C offset non-cash interest and other, so operating cash flow is unchanged. D removes the row and operating cash flow.",
    ),
    dict(
        id="author_08286_1",
        parent="financebench_id_08286",
        metric="FY2019 income before income taxes (third column)",
        unit="millions",
        expected={"A": 13976, "B": 14776, "C": 13976},
        trap={"B": 13976, "C": 10761, "D": 13976},
        arms={
            "B": dict(
                ops=[
                    cell("Other income (expense), net", 2, "203", "1,003"),
                    cell("Total non-operating income (expense)", 2, "(565)", "235"),
                    cell("Income before income taxes", 2, "13,976", "14,776"),
                    cell("Provision for income taxes", 2, "(2,374)", "(3,174)"),
                ],
                gone=["13,976", "2,374"],
                present=["14,776"],
            ),
            "C": dict(
                ops=[
                    cell("Other income (expense), net", 1, "(183)", "(683)"),
                    cell(
                        "Total non-operating income (expense)", 1, "(1,160)", "(1,660)"
                    ),
                    cell("Income before income taxes", 1, "11,261", "10,761"),
                    cell("Provision for income taxes", 1, "(1,197)", "(697)"),
                ],
                gone=["11,261", "1,197", "1,160"],
                present=["13,976", "10,761"],
            ),
            "D": dict(
                ops=[
                    drop("Income before income taxes", "3,806 \n11,261"),
                    drop("Total non-operating income (expense)", "(300)"),
                    drop("Provision for income taxes", "(769)"),
                ],
                gone=["13,976"],
            ),
        },
        audit="B and C move other income, the non-operating total, income before taxes and the tax provision together, so operating income and net income are unchanged. D removes income before taxes, the non-operating total and the tax provision (net income plus tax would recover it). The 2017 10-K's income statement in the context (FY2015-FY2017) is left as a distractor.",
    ),
    dict(
        id="author_08286_2",
        parent="financebench_id_08286",
        metric="FY2019 interest expense (third column)",
        unit="millions",
        expected={"A": 1600, "B": 1700, "C": 1600},
        trap={"B": 1600, "C": 1317, "D": 1600},
        arms={
            "B": dict(
                ops=[
                    cell("Interest expense", 2, "(1,600)", "(1,700)"),
                    cell("Other income (expense), net", 2, "203", "303"),
                ],
                gone=["1,600"],
                present=["1,700"],
            ),
            "C": dict(
                ops=[
                    cell("Interest expense", 1, "(1,417)", "(1,317)"),
                    cell("Other income (expense), net", 1, "(183)", "(283)"),
                ],
                gone=["1,417"],
                present=["1,600", "1,317"],
            ),
            "D": dict(
                ops=[
                    drop("Interest expense", "(848) \n(1,417)"),
                    drop("Total non-operating income (expense)", "(300)"),
                ],
                gone=["1,600"],
            ),
        },
        audit="B and C offset other income, so the non-operating total is unchanged. D removes interest expense and the non-operating total. The 2017 10-K's interest expense row (FY2015-FY2017) is left as a distractor.",
    ),
    dict(
        id="author_10285_1",
        parent="financebench_id_10285",
        metric="Inventories at Dec 31, 2018",
        unit="millions",
        expected={"A": 62567, "B": 66567, "C": 62567},
        trap={"B": 62567, "C": 58388, "D": 62567},
        arms={
            "B": dict(
                ops=[
                    cell("Inventories", 0, "62,567", "66,567"),
                    cell("Unbilled receivables, net", 0, "10,025", "6,025"),
                ],
                gone=["62,567", "10,025"],
                present=["66,567"],
            ),
            "C": dict(
                ops=[
                    cell("Inventories", 1, "61,388", "58,388"),
                    cell("Unbilled receivables, net", 1, "8,194", "11,194"),
                ],
                gone=["61,388", "8,194"],
                present=["62,567", "58,388"],
            ),
            "D": dict(
                ops=[
                    drop("Inventories", "62,567", 2),
                    drop("Total current assets", "87,830", 2),
                ],
                gone=["62,567", "87,830"],
            ),
        },
        audit="B and C offset unbilled receivables, so total current assets is unchanged. D removes inventories and total current assets.",
    ),
    dict(
        id="author_10285_2",
        parent="financebench_id_10285",
        metric="Accounts payable at Dec 31, 2018",
        unit="millions",
        expected={"A": 12916, "B": 13716, "C": 12916},
        trap={"B": 12916, "C": 11702, "D": 12916},
        arms={
            "B": dict(
                ops=[
                    cell("Accounts payable", 0, "12,916", "13,716"),
                    cell("Accrued liabilities", 0, "14,808", "14,008"),
                ],
                gone=["12,916", "14,808"],
                present=["13,716"],
            ),
            "C": dict(
                ops=[
                    cell("Accounts payable", 1, "12,202", "11,702"),
                    cell("Accrued liabilities", 1, "13,069", "13,569"),
                ],
                gone=["12,202", "13,069"],
                present=["12,916", "11,702"],
            ),
            "D": dict(
                ops=[
                    drop("Accounts payable", "12,916", 2),
                    drop("Total current liabilities", "81,590", 2),
                ],
                gone=["12,916", "81,590"],
            ),
        },
        audit="B and C offset accrued liabilities, so total current liabilities is unchanged. D removes accounts payable and total current liabilities.",
    ),
]
for c in AUTHOR_CASES:
    c["source"] = "author"

pilots = [c["id"] for c in CASES if c.get("pilot")]
rest = sorted(
    (c["id"] for c in CASES if not c.get("pilot")),
    key=lambda i: hashlib.sha256(i.encode()).hexdigest(),
)
dev = set(pilots) | {rest[0]}
for c in CASES:
    c["split"] = "dev" if c["id"] in dev else "reserved"
    c.setdefault("pilot", False)
    c.setdefault("source", "financebench")
split_of = {c["id"]: c["split"] for c in CASES}
for c in AUTHOR_CASES:
    c["split"] = split_of[c["parent"]]  # same filing, same split
    c["pilot"] = False
    c["doc_name"] = next(p["doc_name"] for p in CASES if p["id"] == c["parent"])
CASES += AUTHOR_CASES

old = json.loads((REPO / "evaluation/counterfactual/manifest.json").read_text())
manifest = {
    "version": 1,
    "frozen": False,
    "notes": "Synthetic edits of FinanceBench evidence excerpts (CC BY-NC 4.0). Arms B-D are benchmark fixtures, not company figures. B raises the target by about 5-6% and C lowers the previous year's value; each edit is offset within the same statement so totals and the balance-sheet identity still hold (exceptions are noted per case). Edits are large enough that the 1% grading tolerance cannot confuse the original and edited figures. D removes the target and any row it could be recovered from in one step; multi-step recoveries that remain are disclosed per case.",
    "eligibility": old["eligibility"],
    "split_rule": old["split_rule"],
    "cases": CASES,
    "excluded": old["excluded"],
}
(REPO / "evaluation/counterfactual/manifest.json").write_text(
    json.dumps(manifest, indent=1) + "\n"
)
print("dev:", sorted(dev))
