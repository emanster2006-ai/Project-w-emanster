export interface SourceChunk {
  text: string;
  source: string;
  company: string | null;
  year: string | null;
  section: string | null;
  score: number;
}

export interface QueryResponse {
  answer: string;
  sources: SourceChunk[];
  latency_ms: number;
  cached: boolean;
  sub_questions: string[] | null;
}

/**
 * Turn a FastAPI error body into a readable message.
 * `detail` is a string for most errors but a list of `{msg}` objects for
 * request-validation (422) errors, which used to render as "[object Object]".
 */
export function errorMessage(body: unknown, status: number): string {
  const detail = (body as { detail?: unknown } | null)?.detail;

  if (typeof detail === "string" && detail.trim()) return detail;

  if (Array.isArray(detail)) {
    const messages = detail
      .map((item) =>
        typeof item === "string" ? item : (item as { msg?: unknown })?.msg,
      )
      .filter((msg): msg is string => typeof msg === "string" && msg.length > 0);
    if (messages.length > 0) return messages.join("; ");
  }

  if (status === 429) return "Too many requests. Please wait a moment and try again.";
  return `Server error ${status}`;
}

export async function submitQuery(
  question: string,
  signal?: AbortSignal,
): Promise<QueryResponse> {
  const res = await fetch("/api/v1/query", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    signal,
    body: JSON.stringify({
      question,
      use_hyde: false,
      use_decomposition: true,
      top_k: 5,
    }),
  });

  if (!res.ok) {
    const body = await res.json().catch(() => null);
    throw new Error(errorMessage(body, res.status));
  }

  return (await res.json()) as QueryResponse;
}
