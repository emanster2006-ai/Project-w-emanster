"use client";

import { useState, useRef, useEffect } from "react";
import { submitQuery, type QueryResponse } from "@/lib/queryApi";

const EXAMPLE_QUESTIONS = [
  "What was Apple's R&D expense in fiscal year 2022?",
  "Compare Microsoft and Google's operating margins for 2021.",
  "How did Amazon's AWS revenue grow from 2020 to 2022?",
  "What risk factors did Tesla cite in their 2022 10-K?",
];

export default function QueryInterface() {
  const [question, setQuestion] = useState("");
  const [result, setResult] = useState<QueryResponse | null>(null);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [expandedSources, setExpandedSources] = useState<Set<number>>(new Set());
  const textareaRef = useRef<HTMLTextAreaElement>(null);
  const abortRef = useRef<AbortController | null>(null);

  useEffect(() => () => abortRef.current?.abort(), []);

  useEffect(() => {
    if (textareaRef.current) {
      textareaRef.current.style.height = "auto";
      textareaRef.current.style.height = `${textareaRef.current.scrollHeight}px`;
    }
  }, [question]);

  async function handleSubmit(q?: string) {
    const query = q ?? question;
    if (!query.trim() || loading) return;

    // Cancel any in-flight request so a slow older answer cannot overwrite a newer one.
    abortRef.current?.abort();
    const controller = new AbortController();
    abortRef.current = controller;

    setLoading(true);
    setError(null);
    setResult(null);
    setExpandedSources(new Set());

    try {
      const data = await submitQuery(query, controller.signal);
      if (!controller.signal.aborted) setResult(data);
    } catch (err) {
      if (controller.signal.aborted) return;
      setError(err instanceof Error ? err.message : "Unknown error");
    } finally {
      if (abortRef.current === controller) {
        abortRef.current = null;
        setLoading(false);
      }
    }
  }

  function toggleSource(i: number) {
    setExpandedSources((prev) => {
      const next = new Set(prev);
      if (next.has(i)) {
        next.delete(i);
      } else {
        next.add(i);
      }
      return next;
    });
  }

  return (
    <div className="w-full max-w-3xl mx-auto flex flex-col gap-8">
      {/* Input */}
      <div
        className="rounded-2xl border p-4 flex flex-col gap-3"
        style={{ background: "var(--surface)", borderColor: "var(--border)" }}
      >
        <textarea
          ref={textareaRef}
          rows={2}
          aria-label="Question about SEC 10-K filings"
          placeholder="Ask a question about SEC 10-K filings…"
          value={question}
          onChange={(e) => setQuestion(e.target.value)}
          onKeyDown={(e) => {
            if (e.key === "Enter" && !e.shiftKey) {
              e.preventDefault();
              handleSubmit();
            }
          }}
          className="w-full resize-none bg-transparent text-base outline-none placeholder-[var(--text-muted)]"
          style={{ color: "var(--text)", minHeight: "3rem", maxHeight: "12rem" }}
        />
        <div className="flex items-center justify-between">
          <span className="text-xs" style={{ color: "var(--text-muted)" }}>
            Shift+Enter for newline
          </span>
          <button
            onClick={() => handleSubmit()}
            disabled={loading || !question.trim()}
            className="px-4 py-2 rounded-lg text-sm font-medium text-white transition-colors disabled:opacity-40 disabled:cursor-not-allowed"
            style={{ background: loading ? "var(--accent-hover)" : "var(--accent)" }}
          >
            {loading ? "Searching…" : "Ask"}
          </button>
        </div>
      </div>

      {/* Example questions */}
      {!result && !loading && (
        <div className="flex flex-col gap-2">
          <p className="text-xs font-medium uppercase tracking-widest" style={{ color: "var(--text-muted)" }}>
            Example questions
          </p>
          <div className="grid grid-cols-1 sm:grid-cols-2 gap-2">
            {EXAMPLE_QUESTIONS.map((q) => (
              <button
                key={q}
                onClick={() => {
                  setQuestion(q);
                  handleSubmit(q);
                }}
                className="text-left text-sm px-4 py-3 rounded-xl border transition-colors hover:border-[var(--accent)]"
                style={{
                  background: "var(--surface)",
                  borderColor: "var(--border)",
                  color: "var(--text-muted)",
                }}
              >
                {q}
              </button>
            ))}
          </div>
        </div>
      )}

      {/* Loading */}
      {loading && (
        <div role="status" aria-live="polite" className="flex items-center gap-3" style={{ color: "var(--text-muted)" }}>
          <div className="h-4 w-4 rounded-full border-2 border-t-transparent animate-spin" style={{ borderColor: "var(--accent)", borderTopColor: "transparent" }} />
          <span className="text-sm">Running pipeline — hybrid retrieval + reranking…</span>
        </div>
      )}

      {/* Error */}
      {error && (
        <div role="alert" className="rounded-xl border border-red-500/30 bg-red-500/10 px-4 py-3 text-sm text-red-400">
          {error}
        </div>
      )}

      {/* Result */}
      {result && (
        <div className="flex flex-col gap-6" aria-live="polite">
          {/* Meta bar */}
          <div className="flex items-center gap-4 text-xs" style={{ color: "var(--text-muted)" }}>
            <span>{result.latency_ms.toFixed(0)} ms</span>
            {result.cached && (
              <span className="px-2 py-0.5 rounded-full text-xs" style={{ background: "var(--surface-2)", color: "var(--accent)" }}>
                cached
              </span>
            )}
            {result.sub_questions && result.sub_questions.length > 1 && (
              <span>{result.sub_questions.length} sub-questions decomposed</span>
            )}
          </div>

          {/* Sub-questions */}
          {result.sub_questions && result.sub_questions.length > 1 && (
            <div
              className="rounded-xl border p-4 flex flex-col gap-2"
              style={{ background: "var(--surface)", borderColor: "var(--border)" }}
            >
              <p className="text-xs font-medium uppercase tracking-widest" style={{ color: "var(--text-muted)" }}>
                Decomposed into
              </p>
              <ol className="flex flex-col gap-1 pl-4 list-decimal">
                {result.sub_questions.map((q, i) => (
                  <li key={i} className="text-sm" style={{ color: "var(--text-muted)" }}>
                    {q}
                  </li>
                ))}
              </ol>
            </div>
          )}

          {/* Answer */}
          <div
            className="rounded-2xl border p-6"
            style={{ background: "var(--surface)", borderColor: "var(--border)" }}
          >
            <p className="text-base leading-7" style={{ color: "var(--text)", whiteSpace: "pre-wrap" }}>
              {result.answer}
            </p>
          </div>

          {/* Sources */}
          {result.sources.length > 0 && (
            <div className="flex flex-col gap-2">
              <p className="text-xs font-medium uppercase tracking-widest" style={{ color: "var(--text-muted)" }}>
                {result.sources.length} source{result.sources.length !== 1 ? "s" : ""}
              </p>
              {result.sources.map((src, i) => (
                <div
                  key={i}
                  className="rounded-xl border overflow-hidden"
                  style={{ background: "var(--surface)", borderColor: "var(--border)" }}
                >
                  <button
                    className="w-full flex items-center justify-between px-4 py-3 text-sm hover:bg-white/5 transition-colors"
                    onClick={() => toggleSource(i)}
                    aria-expanded={expandedSources.has(i)}
                  >
                    <div className="flex items-center gap-3 min-w-0">
                      <span
                        title="Reranker relevance score (higher is more relevant; not a percentage)"
                        className="shrink-0 text-xs font-mono px-2 py-0.5 rounded"
                        style={{ background: "var(--surface-2)", color: "var(--accent)" }}
                      >
                        {src.score.toFixed(2)}
                      </span>
                      <span className="truncate font-medium" style={{ color: "var(--text)" }}>
                        {src.company ?? src.source}
                      </span>
                      {src.year && (
                        <span style={{ color: "var(--text-muted)" }}>{src.year}</span>
                      )}
                      {src.section && (
                        <span className="truncate hidden sm:block" style={{ color: "var(--text-muted)" }}>
                          · {src.section}
                        </span>
                      )}
                    </div>
                    <span className="shrink-0 ml-2 text-lg leading-none" style={{ color: "var(--text-muted)" }}>
                      {expandedSources.has(i) ? "−" : "+"}
                    </span>
                  </button>

                  {expandedSources.has(i) && (
                    <div
                      className="px-4 pb-4 text-sm leading-6 border-t"
                      style={{ color: "var(--text-muted)", borderColor: "var(--border)" }}
                    >
                      <p className="pt-3 font-mono text-xs whitespace-pre-wrap">{src.text}</p>
                    </div>
                  )}
                </div>
              ))}
            </div>
          )}
        </div>
      )}
    </div>
  );
}

