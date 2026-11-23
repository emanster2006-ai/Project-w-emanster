"use client";

import { useState, useRef, useEffect } from "react";
import {
  ApiError,
  figuresIn,
  isAbstention,
  submitQuery,
  type QueryResponse,
} from "@/lib/queryApi";

// Questions taken from the FinanceBench sample the demo index is built from,
// so each one has its evidence in the corpus.
const EXAMPLE_QUESTIONS = [
  "What was the largest liability in American Express's Balance Sheet in 2022?",
  "By how much did Pepsico increase its unsecured five year revolving credit agreement on May 26, 2023?",
  "What is the FY2017 - FY2019 3 year average of capex as a % of revenue for Activision Blizzard?",
];

function Highlighted({ text, terms }: { text: string; terms: string[] }) {
  if (terms.length === 0) return <>{text}</>;
  const escaped = terms.map((t) => t.replace(/[.*+?^${}()|[\]\\]/g, "\\$&"));
  const parts = text.split(new RegExp(`(${escaped.join("|")})`, "g"));
  return (
    <>
      {parts.map((part, i) =>
        terms.includes(part) ? (
          <mark key={i} className="rounded px-0.5" style={{ background: "rgba(99,102,241,0.35)", color: "var(--text)" }}>
            {part}
          </mark>
        ) : (
          <span key={i}>{part}</span>
        ),
      )}
    </>
  );
}

export default function QueryInterface() {
  const [question, setQuestion] = useState("");
  const [result, setResult] = useState<QueryResponse | null>(null);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [retryIn, setRetryIn] = useState(0);
  const [copied, setCopied] = useState(false);
  const [expandedSources, setExpandedSources] = useState<Set<number>>(new Set());
  const textareaRef = useRef<HTMLTextAreaElement>(null);
  const abortRef = useRef<AbortController | null>(null);

  useEffect(() => () => abortRef.current?.abort(), []);

  // Count down after a rate-limit response so the user knows when to retry.
  useEffect(() => {
    if (retryIn <= 0) return;
    const t = setTimeout(() => setRetryIn((n) => n - 1), 1000);
    return () => clearTimeout(t);
  }, [retryIn]);

  async function copyAnswer(text: string) {
    try {
      await navigator.clipboard.writeText(text);
      setCopied(true);
      setTimeout(() => setCopied(false), 1500);
    } catch {
      /* clipboard unavailable (insecure context); nothing to do */
    }
  }

  useEffect(() => {
    if (textareaRef.current) {
      textareaRef.current.style.height = "auto";
      textareaRef.current.style.height = `${textareaRef.current.scrollHeight}px`;
    }
  }, [question]);

  async function handleSubmit(q?: string) {
    const query = q ?? question;
    if (!query.trim() || loading || retryIn > 0) return;

    // Cancel any in-flight request so a slow older answer cannot overwrite a newer one.
    abortRef.current?.abort();
    const controller = new AbortController();
    abortRef.current = controller;

    setLoading(true);
    setError(null);
    setRetryIn(0);
    setCopied(false);
    setResult(null);
    setExpandedSources(new Set());

    try {
      const data = await submitQuery(query, controller.signal);
      if (!controller.signal.aborted) setResult(data);
    } catch (err) {
      if (controller.signal.aborted) return;
      setError(err instanceof Error ? err.message : "Unknown error");
      if (err instanceof ApiError && err.status === 429) setRetryIn(err.retryAfter ?? 30);
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
            disabled={loading || retryIn > 0 || !question.trim()}
            className="px-4 py-2 rounded-lg text-sm font-medium text-white transition-colors disabled:opacity-40 disabled:cursor-not-allowed"
            style={{ background: loading ? "var(--accent-hover)" : "var(--accent)" }}
          >
            {loading ? "Searching…" : retryIn > 0 ? `Retry in ${retryIn}s` : "Ask"}
          </button>
        </div>
      </div>

      {/* Example questions */}
      {!result && !loading && (
        <div className="flex flex-col gap-2">
          <p className="text-xs font-medium uppercase tracking-widest" style={{ color: "var(--text-muted)" }}>
            Try a question from the demo index
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
          <span className="text-sm">Searching filings, reranking passages and writing an answer…</span>
        </div>
      )}
      {loading && (
        <div aria-hidden className="flex flex-col gap-3 animate-pulse">
          <div className="h-24 rounded-2xl" style={{ background: "var(--surface)" }} />
          <div className="h-10 rounded-xl" style={{ background: "var(--surface)" }} />
          <div className="h-10 rounded-xl" style={{ background: "var(--surface)" }} />
        </div>
      )}

      {/* Error */}
      {error && (
        <div role="alert" className="rounded-xl border border-red-500/30 bg-red-500/10 px-4 py-3 text-sm text-red-400">
          {error}
          {retryIn > 0 && <span> You can ask again in {retryIn}s.</span>}
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
            {isAbstention(result.answer) && (
              <p
                className="mb-3 rounded-lg px-3 py-2 text-xs"
                style={{ background: "var(--surface-2)", color: "var(--text-muted)" }}
              >
                The model could not find this in the retrieved passages. The demo index only holds
                excerpts from 150 FinanceBench questions, so try one of the example questions or
                check the sources below.
              </p>
            )}
            <p className="text-base leading-7" style={{ color: "var(--text)", whiteSpace: "pre-wrap" }}>
              {result.answer}
            </p>
            <button
              onClick={() => copyAnswer(result.answer)}
              className="mt-4 text-xs underline-offset-2 hover:underline"
              style={{ color: "var(--text-muted)" }}
            >
              {copied ? "Copied" : "Copy answer"}
            </button>
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
                      <p className="pt-3 font-mono text-xs whitespace-pre-wrap">
                        <Highlighted text={src.text} terms={figuresIn(result.answer)} />
                      </p>
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

