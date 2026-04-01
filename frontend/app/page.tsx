import QueryInterface from "./components/QueryInterface";

export default function Home() {
  return (
    <div className="min-h-screen flex flex-col" style={{ background: "var(--background)" }}>
      {/* Header */}
      <header
        className="border-b px-6 py-4 flex items-center justify-between"
        style={{ borderColor: "var(--border)", background: "var(--surface)" }}
      >
        <div className="flex items-center gap-3">
          <div
            className="w-7 h-7 rounded-lg flex items-center justify-center text-white text-xs font-bold"
            style={{ background: "var(--accent)" }}
          >
            S
          </div>
          <span className="font-semibold tracking-tight" style={{ color: "var(--text)" }}>
            SecureRAG
          </span>
          <span
            className="text-xs px-2 py-0.5 rounded-full border"
            style={{ color: "var(--text-muted)", borderColor: "var(--border)" }}
          >
            SEC 10-K Intelligence
          </span>
        </div>
        <div className="flex items-center gap-4 text-xs" style={{ color: "var(--text-muted)" }}>
          <span>HyDE + RRF + CrossEncoder</span>
          <a
            href="https://github.com/ErikEllis-git/Project-w-emanster"
            target="_blank"
            rel="noopener noreferrer"
            className="hover:underline"
          >
            GitHub
          </a>
        </div>
      </header>

      {/* Main */}
      <main className="flex-1 px-4 py-12">
        <div className="max-w-3xl mx-auto flex flex-col gap-10">
          {/* Hero */}
          <div className="text-center flex flex-col gap-3">
            <h1 className="text-3xl font-bold tracking-tight" style={{ color: "var(--text)" }}>
              Financial Document Intelligence
            </h1>
            <p className="text-base" style={{ color: "var(--text-muted)" }}>
              Multi-hop RAG over SEC 10-K filings — hybrid retrieval, HyDE, reranking, and OWASP LLM security guardrails.
            </p>
          </div>

          <QueryInterface />
        </div>
      </main>

      {/* Footer */}
      <footer
        className="border-t px-6 py-4 text-center text-xs"
        style={{ borderColor: "var(--border)", color: "var(--text-muted)" }}
      >
        Built with FastAPI · Qdrant · SentenceTransformers · DeepEval
      </footer>
    </div>
  );
}
