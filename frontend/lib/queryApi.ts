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

/** Error carrying the server's Retry-After hint (seconds) when rate limited. */
export class ApiError extends Error {
  constructor(
    message: string,
    public status: number,
    public retryAfter: number | null = null,
  ) {
    super(message);
    this.name = "ApiError";
  }
}

export function parseRetryAfter(value: string | null): number | null {
  if (!value) return null;
  const seconds = Number(value);
  return Number.isFinite(seconds) && seconds > 0 ? Math.ceil(seconds) : null;
}

/** True when the model declined to answer from the retrieved context. */
export function isAbstention(answer: string): boolean {
  return /insufficient context/i.test(answer);
}

/** Numbers like 1,577 or 24.26 that appear in the answer, for highlighting in sources. */
export function figuresIn(answer: string): string[] {
  const found = answer.match(/\d[\d,]*\.?\d*/g) ?? [];
  return [...new Set(found.map((f) => f.replace(/[.,]$/, "")).filter((f) => f.length >= 3))];
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
      top_k: 8,
    }),
  });

  if (!res.ok) {
    const body = await res.json().catch(() => null);
    throw new ApiError(
      errorMessage(body, res.status),
      res.status,
      parseRetryAfter(res.headers?.get?.("Retry-After") ?? null),
    );
  }

  return (await res.json()) as QueryResponse;
}
