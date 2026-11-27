// Types and helpers for the counterfactual replay page. The data is exported from
// recorded benchmark runs by scripts/counterfactual_export.py; nothing here calls a model.

export type Segment = { kind: "same" | "added" | "removed"; text: string };

export type Grade =
  | "correct"
  | "wrong"
  | "trap"
  | "refused"
  | "leaked"
  | "ambiguous"
  | "error";

export type RecordedAnswer = { text: string | null; grade: Grade };

export type Arm = {
  label: string;
  expected: string;
  options: string[];
  correct_option: number;
  segments: Segment[];
  answers: Record<string, RecordedAnswer>;
};

export type ReplayCase = {
  id: string;
  source: "financebench" | "author";
  split: "dev" | "reserved";
  doc_name: string;
  chunk_source: string;
  question: string;
  metric: string;
  audit: string;
  arms: Record<"A" | "B" | "C" | "D", Arm>;
};

export type ReplayData = {
  generated_at: string;
  model: string;
  provider: string;
  reasoning_effort: string;
  run_started: string;
  cases: ReplayCase[];
};

export const ARM_KEYS = ["A", "B", "C", "D"] as const;

export const SYSTEM_LABELS: Record<string, string> = {
  baseline: "Current prompt",
  candidate: "With the new rule",
};

const GRADE_TEXT: Record<Grade, string> = {
  correct: "Correct",
  wrong: "Wrong figure",
  trap: "Used the wrong figure",
  refused: "Refused",
  leaked: "Gave the removed figure",
  ambiguous: "Unclear",
  error: "Provider error",
};

export function gradeText(grade: Grade): string {
  return GRADE_TEXT[grade] ?? grade;
}

export function isPass(grade: Grade): boolean {
  return grade === "correct";
}

/** Did the case pass all four arms for this system? Missing arms count as not passing. */
export function casePasses(c: ReplayCase, system: string): boolean {
  return ARM_KEYS.every((arm) => c.arms[arm].answers[system]?.grade === "correct");
}

export function systemsIn(c: ReplayCase): string[] {
  const seen = new Set<string>();
  for (const arm of ARM_KEYS) Object.keys(c.arms[arm].answers).forEach((s) => seen.add(s));
  return ["baseline", "candidate"].filter((s) => seen.has(s));
}

export function sourceLabel(c: ReplayCase): string {
  return c.source === "author" ? "Author-written question" : "FinanceBench question";
}
