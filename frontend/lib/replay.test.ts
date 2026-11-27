import { describe, expect, it } from "vitest";
import { casePasses, gradeText, sourceLabel, systemsIn, type ReplayCase } from "./replay";
import data from "./replay-cases.json";

function makeCase(grades: Record<string, Record<string, string>>): ReplayCase {
  const arm = (k: string) => ({
    label: k,
    expected: "",
    options: [],
    correct_option: 0,
    segments: [],
    answers: Object.fromEntries(
      Object.entries(grades)
        .filter(([, g]) => g[k])
        .map(([s, g]) => [s, { text: "x", grade: g[k] }]),
    ),
  });
  return {
    id: "c",
    source: "author",
    split: "dev",
    doc_name: "D",
    chunk_source: "D",
    question: "q",
    metric: "m",
    audit: "a",
    arms: { A: arm("A"), B: arm("B"), C: arm("C"), D: arm("D") },
  } as ReplayCase;
}

describe("replay helpers", () => {
  it("passes a case only when all four arms are correct", () => {
    const all = { A: "correct", B: "correct", C: "correct", D: "correct" };
    expect(casePasses(makeCase({ baseline: all }), "baseline")).toBe(true);
    expect(casePasses(makeCase({ baseline: { ...all, D: "wrong" } }), "baseline")).toBe(false);
    expect(casePasses(makeCase({ baseline: { A: "correct" } }), "baseline")).toBe(false);
  });

  it("lists systems in a fixed order and labels sources and grades", () => {
    const c = makeCase({ candidate: { A: "correct" }, baseline: { A: "trap" } });
    expect(systemsIn(c)).toEqual(["baseline", "candidate"]);
    expect(sourceLabel(c)).toBe("Author-written question");
    expect(gradeText("trap")).toBe("Used the wrong figure");
  });
});

describe("exported replay data", () => {
  it("has four arms per case, each with a valid expected option", () => {
    expect(data.cases.length).toBeGreaterThan(0);
    for (const c of data.cases) {
      for (const k of ["A", "B", "C", "D"] as const) {
        const arm = c.arms[k];
        expect(arm.options.length).toBe(3);
        expect(arm.correct_option).toBeGreaterThanOrEqual(0);
        expect(arm.correct_option).toBeLessThan(arm.options.length);
        expect(arm.segments.length).toBeGreaterThan(0);
      }
      // Only arms B-D are edited; the original excerpt has no changes.
      expect(c.arms.A.segments.every((s) => s.kind === "same")).toBe(true);
      expect(c.arms.B.segments.some((s) => s.kind !== "same")).toBe(true);
    }
  });
});
