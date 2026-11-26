"""End-to-end answer accuracy on all 150 FinanceBench questions, graded by an LLM judge.

Each question goes through the running API with the same options the web UI sends
(decomposition on, HyDE off, top_k 8). A judge model from a different family labels
each answer against the FinanceBench reference, using the paper's three labels:

  correct    same figure or conclusion as the reference (rounding and units allowed)
  incorrect  a different figure or conclusion
  refused    no final answer ("Insufficient context", or a non-answer)

The run is resumable. Answers and grades are appended to JSONL files keyed by
financebench_id, so rerunning the same command skips finished questions. When the
provider's per-minute limit is hit it waits; when the daily limit is hit it stops and
says so, and the next run picks up where this one stopped.

  python scripts/answer_accuracy.py --run evaluation/runs/<name>            # answer + grade
  python scripts/answer_accuracy.py --run evaluation/runs/<name> --summary  # print results

Every judge label is a proxy: review the incorrect and refused cases by hand (see
`--review`) before quoting a number. Needs GROQ_API_KEY for the judge.
"""

import argparse
import json
import math
import os
import re
import subprocess
import sys
import time
import urllib.error
import urllib.request
from collections import Counter, defaultdict
from datetime import datetime, timezone
from pathlib import Path

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from answer_eval import close, figures  # noqa: E402  (same folder)

UI_OPTIONS = {"use_hyde": False, "use_decomposition": True, "top_k": 8}
# A Retry-After longer than this means a daily limit: stop the run. Providers with
# hourly request limits (Cerebras: 150/hour) need RUN_MAX_WAIT_S=3700.
LONG_WAIT_S = float(os.getenv("RUN_MAX_WAIT_S", 300))

JUDGE_SYSTEM = """You grade answers to questions about company financial filings.
Compare the CANDIDATE answer with the REFERENCE answer and give one label:

- "correct": the candidate's final answer agrees with the reference. Allow rounding
  (about 1%), different units or scale ($1,577 million = $1.58 billion, 0.25 = 25%),
  extra explanation, and a missing minor detail. For yes/no and qualitative questions
  the main conclusion must match the reference.
- "incorrect": a different figure, a wrong conclusion, a contradiction of the
  reference, or several conflicting answers.
- "refused": the candidate gives no final answer, for example "Insufficient context".

Judge only agreement with the reference; do not use your own knowledge of the company.
Reply with JSON only: {"label": "correct" | "incorrect" | "refused", "reason": "<one sentence>"}"""


# ── Data ────────────────────────────────────────────────────────────────────────


def _norm(text: str) -> str:
    return " ".join(text.split())


def evidence_retrieved(chunk_texts: list[str], evidence: str) -> bool:
    """Same rule as scripts/retrieval_benchmark.py: a chunk was cut from the evidence."""
    ev = _norm(evidence)
    for t in chunk_texts:
        c = _norm(t)
        if c and (c in ev or ev[:120] in c or c[:120] in ev):
            return True
    return False


def load_questions() -> list[dict]:
    from datasets import load_dataset

    rows = []
    for row in load_dataset("PatronusAI/financebench", split="train"):
        rows.append(
            {
                "id": row["financebench_id"],
                "question": row["question"],
                "reference": row["answer"],
                "justification": row.get("justification") or "",
                "question_type": row.get("question_type") or "unknown",
                "company": row.get("company"),
                "doc_name": row.get("doc_name"),
                "evidence": " ".join(
                    e.get("evidence_text", "")
                    for e in (row.get("evidence") or [])
                    if e.get("evidence_text")
                ),
            }
        )
    return rows


def read_jsonl(path: Path) -> dict[str, dict]:
    if not path.exists():
        return {}
    out = {}
    for line in path.read_text().splitlines():
        if line.strip():
            rec = json.loads(line)
            out[rec["id"]] = rec
    return out


def append_jsonl(path: Path, rec: dict) -> None:
    with path.open("a") as f:
        f.write(json.dumps(rec) + "\n")


# ── Rate limits ─────────────────────────────────────────────────────────────────


class DailyLimit(Exception):
    """The provider asked us to wait longer than LONG_WAIT_S: stop and resume later."""


def _retry_after(text: str, header: str | None) -> float:
    if header:
        try:
            return float(header)
        except ValueError:
            pass
    # Groq's message: "Please try again in 1m23.5s" / "in 7.2s" / "in 2h1m"
    m = re.search(r"try again in ((?:\d+h)?(?:\d+m)?(?:[\d.]+s)?)", text)
    if not m or not m.group(1):
        return 60.0
    total = 0.0
    for value, unit in re.findall(r"([\d.]+)([hms])", m.group(1)):
        total += float(value) * {"h": 3600, "m": 60, "s": 1}[unit]
    return total or 60.0


def _wait_or_stop(seconds: float, what: str) -> None:
    if seconds > LONG_WAIT_S:
        raise DailyLimit(f"{what}: provider asks to wait {seconds / 60:.0f} min")
    print(f"  rate limited ({what}), waiting {seconds:.0f}s", flush=True)
    time.sleep(seconds + 1)


# ── Answering ───────────────────────────────────────────────────────────────────


def ask(url: str, question: str) -> dict:
    body = json.dumps({"question": question, **UI_OPTIONS}).encode()
    for _ in range(20):
        req = urllib.request.Request(url, body, {"Content-Type": "application/json"})
        try:
            with urllib.request.urlopen(req, timeout=300) as resp:
                return json.load(resp)
        except urllib.error.HTTPError as exc:
            text = exc.read().decode(errors="replace")
            if exc.code == 429:
                _wait_or_stop(_retry_after(text, exc.headers.get("Retry-After")), "api")
                continue
            return {"error": f"HTTP {exc.code}: {text[:300]}"}
        except Exception as exc:  # keep failures as data, not crashes
            return {"error": str(exc)[:300]}
    return {"error": "gave up after repeated rate limits"}


def answer_record(q: dict, resp: dict) -> dict:
    sources = resp.get("sources") or []
    texts = [s.get("text", "") for s in sources]
    answer = resp.get("answer", "")
    return {
        "id": q["id"],
        "question": q["question"],
        "answer": answer,
        "error": resp.get("error"),
        "cached": resp.get("cached", False),
        "latency_ms": resp.get("latency_ms"),
        "sub_questions": resp.get("sub_questions"),
        "sources": [
            {"source": s.get("source"), "year": s.get("year"), "score": s.get("score")}
            for s in sources
        ],
        "evidence_retrieved": (
            evidence_retrieved(texts, q["evidence"]) if q["evidence"] else None
        ),
        # The figure is in the retrieved text: separates retrieval misses from
        # generation misses for numeric questions.
        "figure_in_sources": (
            close(figures(q["reference"]), figures(" ".join(texts)), 0.0)
            if figures(q["reference"])
            else None
        ),
    }


# ── Grading ─────────────────────────────────────────────────────────────────────


def judge(client, model: str, q: dict, answer: str) -> dict:
    user = (
        f"QUESTION:\n{q['question']}\n\nREFERENCE answer:\n{q['reference']}\n\n"
        f"Reference reasoning (for context):\n{q['justification'] or '(none)'}\n\n"
        f"CANDIDATE answer:\n{answer or '(empty)'}"
    )
    for _ in range(20):
        try:
            r = client.chat.completions.create(
                model=model,
                messages=[
                    {"role": "system", "content": JUDGE_SYSTEM},
                    {"role": "user", "content": user},
                ],
                temperature=0,
                max_tokens=300,
                response_format={"type": "json_object"},
                extra_body={"reasoning_effort": "none"},
            )
        except Exception as exc:
            text = str(exc)
            if "429" in text or "rate_limit" in text:
                headers = getattr(getattr(exc, "response", None), "headers", {}) or {}
                _wait_or_stop(_retry_after(text, headers.get("retry-after")), "judge")
                continue
            return {"label": None, "reason": f"judge error: {text[:200]}"}
        try:
            out = json.loads(r.choices[0].message.content)
        except (json.JSONDecodeError, TypeError):
            return {"label": None, "reason": "judge returned invalid JSON"}
        label = str(out.get("label", "")).strip().lower()
        if label not in {"correct", "incorrect", "refused"}:
            return {"label": None, "reason": f"judge returned label {label!r}"}
        return {"label": label, "reason": str(out.get("reason", ""))[:400]}
    return {"label": None, "reason": "judge gave up after repeated rate limits"}


# ── Summary ─────────────────────────────────────────────────────────────────────


def wilson(k: int, n: int, z: float = 1.96) -> tuple[float, float]:
    """95% Wilson score interval for a proportion."""
    if n == 0:
        return (0.0, 0.0)
    p = k / n
    d = 1 + z * z / n
    centre = (p + z * z / (2 * n)) / d
    half = z * math.sqrt(p * (1 - p) / n + z * z / (4 * n * n)) / d
    return (centre - half, centre + half)


def final_label(grade: dict) -> str | None:
    """A hand-reviewed label overrides the judge's."""
    return grade.get("review_label") or grade.get("label")


def summarize(run: Path, questions: list[dict]) -> dict:
    answers = read_jsonl(run / "answers.jsonl")
    grades = read_jsonl(run / "grades.jsonl")
    by_id = {q["id"]: q for q in questions}
    rows = []
    for qid, g in grades.items():
        label = final_label(g)
        if label and qid in answers and not answers[qid]["error"]:
            rows.append((by_id[qid], answers[qid], g, label))
    n = len(rows)
    counts = Counter(label for *_, label in rows)
    lo, hi = wilson(counts["correct"], n)

    by_type: dict[str, Counter] = defaultdict(Counter)
    retrieval: dict[str, Counter] = defaultdict(Counter)
    agree = disagree = 0
    for q, a, g, label in rows:
        by_type[q["question_type"]][label] += 1
        key = {
            True: "evidence retrieved",
            False: "evidence missed",
            None: "no evidence",
        }
        retrieval[key[a["evidence_retrieved"]]][label] += 1
        ref = figures(q["reference"])
        if ref and len(q["reference"]) <= 150:  # short numeric answers only
            matched = close(ref, figures(a["answer"]))
            if matched == (label == "correct"):
                agree += 1
            else:
                disagree += 1

    reviewed = sum(1 for _, _, g, _ in rows if g.get("review_label"))
    return {
        "graded": n,
        "of": len(questions),
        "answer_errors": sum(1 for a in answers.values() if a["error"]),
        "correct": counts["correct"],
        "incorrect": counts["incorrect"],
        "refused": counts["refused"],
        "accuracy": counts["correct"] / n if n else 0.0,
        "accuracy_ci95": [lo, hi],
        "hand_reviewed": reviewed,
        "label_changed_on_review": sum(
            1
            for _, _, g, _ in rows
            if g.get("review_label") and g["review_label"] != g.get("label")
        ),
        "by_question_type": {k: dict(v) for k, v in sorted(by_type.items())},
        "by_retrieval": {k: dict(v) for k, v in sorted(retrieval.items())},
        "figure_check_agrees_with_label": [agree, agree + disagree],
    }


def print_summary(s: dict) -> None:
    lo, hi = s["accuracy_ci95"]
    print(f"graded {s['graded']}/{s['of']} (answer errors: {s['answer_errors']})")
    print(
        f"correct {s['correct']}  incorrect {s['incorrect']}  refused {s['refused']}"
        f"  →  accuracy {s['accuracy']:.1%} (95% CI {lo:.1%}–{hi:.1%})"
    )
    print(
        f"hand-reviewed {s['hand_reviewed']} labels, changed {s['label_changed_on_review']}"
    )
    for title, key in (
        ("by question type", "by_question_type"),
        ("by retrieval", "by_retrieval"),
    ):
        print(f"\n{title}:")
        for k, v in s[key].items():
            tot = sum(v.values())
            print(f"  {k:24s} {v.get('correct', 0):3d}/{tot:<3d} correct  {v}")
    a, t = s["figure_check_agrees_with_label"]
    print(f"\nfigure check agrees with label on {a}/{t} short numeric questions")


# ── Main ────────────────────────────────────────────────────────────────────────


def _git_rev() -> str | None:
    try:
        return subprocess.check_output(
            ["git", "rev-parse", "--short", "HEAD"],
            text=True,
            stderr=subprocess.DEVNULL,
        ).strip()
    except Exception:
        return os.getenv("GIT_REV")


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    parser.add_argument("--run", required=True, help="output folder for this run")
    parser.add_argument("--url", default="http://localhost:8000/api/v1/query")
    parser.add_argument("--judge-model", default="qwen/qwen3.8-27b")
    parser.add_argument("--limit", type=int, help="stop after this many new questions")
    parser.add_argument(
        "--pause", type=float, default=0.0, help="seconds between questions"
    )
    parser.add_argument("--summary", action="store_true", help="print results and exit")
    parser.add_argument(
        "--review", action="store_true", help="print non-correct cases for hand review"
    )
    args = parser.parse_args()

    run = Path(args.run)
    run.mkdir(parents=True, exist_ok=True)
    questions = load_questions()

    if args.summary or args.review:
        if args.review:
            answers, grades = read_jsonl(run / "answers.jsonl"), read_jsonl(
                run / "grades.jsonl"
            )
            for q in questions:
                g = grades.get(q["id"])
                if g and final_label(g) != "correct":
                    print(f"\n── {q['id']} [{final_label(g)}] {q['question']}")
                    print(f"  reference: {q['reference']}")
                    print(f"  answer:    {answers[q['id']]['answer'][:600]}")
                    print(f"  judge:     {g.get('reason')}")
                    print(
                        f"  evidence retrieved: {answers[q['id']]['evidence_retrieved']}"
                    )
        summary = summarize(run, questions)
        (run / "summary.json").write_text(json.dumps(summary, indent=1) + "\n")
        print_summary(summary)
        return

    meta_path = run / "run.json"
    if not meta_path.exists():
        meta_path.write_text(
            json.dumps(
                {
                    "started": datetime.now(timezone.utc).isoformat(timespec="seconds"),
                    "git_rev": _git_rev(),
                    "dataset": "PatronusAI/financebench (train, 150 questions)",
                    "api_options": UI_OPTIONS,
                    "llm_model": os.getenv("LLM_MODEL"),
                    "llm_reasoning_effort": os.getenv("LLM_REASONING_EFFORT", "medium"),
                    "collection": os.getenv("QDRANT_COLLECTION_NAME"),
                    "top_k_retrieve": os.getenv("TOP_K_RETRIEVE", "20"),
                    "judge_model": args.judge_model,
                    "judge_prompt": JUDGE_SYSTEM,
                },
                indent=1,
            )
            + "\n"
        )

    from groq import Groq

    client = Groq(api_key=os.environ["GROQ_API_KEY"])
    answers_path, grades_path = run / "answers.jsonl", run / "grades.jsonl"
    answers, grades = read_jsonl(answers_path), read_jsonl(grades_path)
    done_new = 0
    try:
        for i, q in enumerate(questions, 1):
            if q["id"] in grades:
                continue
            if args.limit is not None and done_new >= args.limit:
                break
            a = answers.get(q["id"])
            if a is None or a["error"]:
                a = answer_record(q, ask(args.url, q["question"]))
                if a["error"]:
                    print(
                        f"[{i}/{len(questions)}] error: {a['error'][:120]}", flush=True
                    )
                    continue  # not saved, so the next run retries it
                append_jsonl(answers_path, a)
                answers[q["id"]] = a
            g = {"id": q["id"], **judge(client, args.judge_model, q, a["answer"])}
            if g["label"] is None:
                print(f"[{i}/{len(questions)}] {g['reason']}", flush=True)
                continue
            append_jsonl(grades_path, g)
            grades[q["id"]] = g
            done_new += 1
            print(
                f"[{i}/{len(questions)}] {g['label']:9s} retrieved={a['evidence_retrieved']} "
                f"{q['question'][:60]}",
                flush=True,
            )
            time.sleep(args.pause)
    except DailyLimit as exc:
        print(f"\nStopped: {exc}. Rerun the same command later to continue.")

    print()
    print_summary(summarize(run, questions))


if __name__ == "__main__":
    main()
