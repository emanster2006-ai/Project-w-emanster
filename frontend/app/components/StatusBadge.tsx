// Server component — fetched at request time, no client JS
interface HealthData {
  status: string;
}

async function fetchHealth(): Promise<HealthData | null> {
  try {
    const res = await fetch(
      process.env.API_URL
        ? `${process.env.API_URL}/health`
        : "http://localhost:8000/health",
      { next: { revalidate: 30 }, signal: AbortSignal.timeout(3000) }
    );
    if (!res.ok) return null;
    return res.json();
  } catch {
    return null;
  }
}

export default async function StatusBadge() {
  const health = await fetchHealth();

  if (!health) {
    return (
      <span
        className="flex items-center gap-1.5 text-xs px-2 py-1 rounded-full border"
        style={{ borderColor: "var(--border)", color: "var(--text-muted)" }}
      >
        <span className="w-1.5 h-1.5 rounded-full bg-zinc-500" />
        API unavailable
      </span>
    );
  }

  const isOk = health.status === "ok";

  return (
    <div className="flex items-center gap-2">
      <span
        className="flex items-center gap-1.5 text-xs px-2 py-1 rounded-full border"
        style={{ borderColor: "var(--border)", color: isOk ? "#22c55e" : "#eab308" }}
      >
        <span
          className="w-1.5 h-1.5 rounded-full"
          style={{ background: isOk ? "#22c55e" : "#eab308" }}
        />
        {isOk ? "API available" : "Degraded"}
      </span>


    </div>
  );
}

