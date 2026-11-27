"use client";

import { useEffect, useRef, useState } from "react";
import {
  ARM_KEYS,
  SYSTEM_LABELS,
  casePasses,
  gradeText,
  isPass,
  sourceLabel,
  systemsIn,
  type ReplayCase,
  type ReplayData,
  type Segment,
} from "@/lib/replay";

type ArmKey = (typeof ARM_KEYS)[number];

function Excerpt({ segments }: { segments: Segment[] }) {
  const box = useRef<HTMLPreElement>(null);

  // Bring the first edit into view: figures sit one per line, so it can be far down.
  useEffect(() => {
    const el = box.current;
    const first = el?.querySelector<HTMLElement>("mark, del");
    if (el) el.scrollTop = first ? Math.max(0, first.offsetTop - el.offsetTop - 48) : 0;
  }, [segments]);

  return (
    <pre
      ref={box}
      aria-label="Filing excerpt"
      className="text-xs leading-relaxed whitespace-pre-wrap rounded-lg border p-3 max-h-72 overflow-auto"
      style={{ borderColor: "var(--border)", background: "var(--surface-2)", color: "var(--text-muted)" }}
    >
      {segments.map((s, i) =>
        s.kind === "same" ? (
          <span key={i}>{s.text}</span>
        ) : s.kind === "added" ? (
          <mark key={i} className="rounded px-0.5" style={{ background: "rgba(34,197,94,0.3)", color: "var(--text)" }}>
            {s.text}
          </mark>
        ) : (
          <del key={i} className="rounded px-0.5" style={{ background: "rgba(239,68,68,0.25)", color: "var(--text)" }}>
            {s.text}
          </del>
        ),
      )}
    </pre>
  );
}

function CaseView({ c }: { c: ReplayCase }) {
  const [arm, setArm] = useState<ArmKey>("A");
  const [guess, setGuess] = useState<number | null>(null);
  const current = c.arms[arm];
  const systems = systemsIn(c);

  function pick(next: ArmKey) {
    setArm(next);
    setGuess(null);
  }

  return (
    <section className="flex flex-col gap-4">
      <div className="flex flex-wrap gap-2 text-xs">
        <span className="px-2 py-0.5 rounded-full border" style={{ borderColor: "var(--border)", color: "var(--text-muted)" }}>
          {sourceLabel(c)}
        </span>
        <span className="px-2 py-0.5 rounded-full border" style={{ borderColor: "var(--border)", color: "var(--text-muted)" }}>
          {c.chunk_source}
        </span>
        <span className="px-2 py-0.5 rounded-full border" style={{ borderColor: "var(--border)", color: "var(--text-muted)" }}>
          {c.split === "dev" ? "Practice case" : "Held-out case"}
        </span>
      </div>
      <h2 className="text-lg font-semibold" style={{ color: "var(--text)" }}>
        {c.question}
      </h2>

      <div role="tablist" aria-label="Version of the evidence" className="flex flex-wrap gap-2">
        {ARM_KEYS.map((k) => (
          <button
            key={k}
            role="tab"
            aria-selected={arm === k}
            onClick={() => pick(k)}
            className="text-xs px-3 py-1.5 rounded-lg border"
            style={{
              borderColor: arm === k ? "var(--accent)" : "var(--border)",
              color: arm === k ? "var(--text)" : "var(--text-muted)",
              background: arm === k ? "var(--surface-2)" : "transparent",
            }}
          >
            {k}. {c.arms[k].label}
          </button>
        ))}
      </div>

      {arm !== "A" && (
        <p className="text-xs" style={{ color: "var(--text-muted)" }}>
          Synthetic edit for testing, not a real company figure. Added text is green; removed text is struck through.
        </p>
      )}
      <Excerpt segments={current.segments} />

      <div className="flex flex-col gap-2">
        <p className="text-sm" style={{ color: "var(--text)" }}>
          Given this evidence, what should a grounded answer say?
        </p>
        <div className="flex flex-wrap gap-2">
          {current.options.map((option, i) => (
            <button
              key={option}
              onClick={() => setGuess(i)}
              disabled={guess !== null}
              className="text-sm px-3 py-1.5 rounded-lg border disabled:cursor-default"
              style={{
                borderColor:
                  guess === null
                    ? "var(--border)"
                    : i === current.correct_option
                      ? "rgb(34,197,94)"
                      : i === guess
                        ? "rgb(239,68,68)"
                        : "var(--border)",
                color: "var(--text)",
              }}
            >
              {option}
            </button>
          ))}
        </div>
      </div>

      {guess !== null && (
        <div className="flex flex-col gap-3" aria-live="polite">
          <p className="text-sm" style={{ color: "var(--text-muted)" }}>
            {guess === current.correct_option ? "You got it." : "Not quite."} Expected: {current.expected}.
          </p>
          {systems.map((s) => {
            const a = current.answers[s];
            if (!a) return null;
            return (
              <div
                key={s}
                className="rounded-lg border p-3 flex flex-col gap-1"
                style={{ borderColor: isPass(a.grade) ? "rgba(34,197,94,0.5)" : "rgba(239,68,68,0.5)" }}
              >
                <div className="flex justify-between text-xs" style={{ color: "var(--text-muted)" }}>
                  <span>{SYSTEM_LABELS[s] ?? s}</span>
                  <span>{gradeText(a.grade)}</span>
                </div>
                <p className="text-sm" style={{ color: "var(--text)" }}>
                  {a.text ?? "(no answer)"}
                </p>
              </div>
            );
          })}
        </div>
      )}

      <details className="text-xs" style={{ color: "var(--text-muted)" }}>
        <summary className="cursor-pointer">How this case was built</summary>
        <p className="mt-2">{c.audit}</p>
      </details>
    </section>
  );
}

function caseTag(c: ReplayCase): string {
  if (casePasses(c, "baseline")) return "";
  if (systemsIn(c).includes("candidate") && casePasses(c, "candidate")) return " · fixed by the new rule";
  return " · still fails";
}

export default function ReplayViewer({ data }: { data: ReplayData }) {
  const [index, setIndex] = useState(0);
  const c = data.cases[index];

  return (
    <div className="flex flex-col gap-6">
      <nav aria-label="Cases" className="flex flex-wrap gap-2">
        {data.cases.map((item, i) => (
          <button
            key={item.id}
            onClick={() => setIndex(i)}
            aria-current={i === index}
            className="text-xs px-3 py-1.5 rounded-lg border"
            style={{
              borderColor: i === index ? "var(--accent)" : "var(--border)",
              color: i === index ? "var(--text)" : "var(--text-muted)",
            }}
          >
            {item.metric}
            {caseTag(item)}
          </button>
        ))}
      </nav>
      {c && <CaseView key={c.id} c={c} />}
      <p className="text-xs" style={{ color: "var(--text-muted)" }}>
        Recorded answers from {data.model} ({data.reasoning_effort} reasoning) via {data.provider}, run{" "}
        {data.run_started.slice(0, 10)}. This page replays saved results and makes no model calls.
      </p>
    </div>
  );
}
