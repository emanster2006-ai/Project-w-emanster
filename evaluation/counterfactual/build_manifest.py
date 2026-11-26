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

pilots = [c["id"] for c in CASES if c.get("pilot")]
rest = sorted(
    (c["id"] for c in CASES if not c.get("pilot")),
    key=lambda i: hashlib.sha256(i.encode()).hexdigest(),
)
dev = set(pilots) | {rest[0]}
for c in CASES:
    c["split"] = "dev" if c["id"] in dev else "reserved"
    c.setdefault("pilot", False)

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
