import type { Metadata } from "next";
import Link from "next/link";
import ReplayViewer from "../components/ReplayViewer";
import data from "@/lib/replay-cases.json";
import type { ReplayData } from "@/lib/replay";

export const metadata: Metadata = {
  title: "SecureRAG · Does the answer follow the filing?",
  description:
    "Replay of a grounding benchmark: the same question asked against four versions of a filing excerpt.",
};

export default function ReplayPage() {
  return (
    <div className="min-h-screen flex flex-col" style={{ background: "var(--background)" }}>
      <header
        className="border-b px-6 py-4 flex items-center justify-between"
        style={{ borderColor: "var(--border)", background: "var(--surface)" }}
      >
        <Link href="/" className="font-semibold tracking-tight" style={{ color: "var(--text)" }}>
          SecureRAG
        </Link>
        <a
          href="https://github.com/emanster2006-ai/Project-w-emanster/blob/main/docs/COUNTERFACTUAL.md"
          className="text-xs hover:underline"
          style={{ color: "var(--text-muted)" }}
        >
          Method and results
        </a>
      </header>
      <main className="flex-1 px-4 py-10">
        <div className="max-w-3xl mx-auto flex flex-col gap-6">
          <div className="flex flex-col gap-2">
            <h1 className="text-2xl font-bold tracking-tight" style={{ color: "var(--text)" }}>
              Does the answer follow the filing?
            </h1>
            <p className="text-sm" style={{ color: "var(--text-muted)" }}>
              Each case asks one question against four versions of the same retrieved evidence: the
              original, the asked-for figure changed, another year&apos;s figure changed, and the
              evidence removed. A grounded system should change its answer only when the asked-for
              figure changes, and say so when the evidence is gone. Pick what the answer should be,
              then see what the model said.
            </p>
          </div>
          <ReplayViewer data={data as ReplayData} />
        </div>
      </main>
    </div>
  );
}
