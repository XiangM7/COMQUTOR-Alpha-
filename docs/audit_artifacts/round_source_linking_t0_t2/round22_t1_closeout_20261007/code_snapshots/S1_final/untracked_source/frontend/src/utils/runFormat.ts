import type { ResearchRunStatus } from "../api/types";

/** Visual tone of a run status. Always paired with a text label -- a status
 * is never communicated by color alone. */
export type RunTone = "ok" | "active" | "warn" | "bad" | "neutral";

const STATUS_PRESENTATION: Record<ResearchRunStatus, { label: string; tone: RunTone }> = {
  completed: { label: "Completed", tone: "ok" },
  running: { label: "Running", tone: "active" },
  queued: { label: "Queued", tone: "neutral" },
  partial: { label: "Partial", tone: "warn" },
  failed: { label: "Failed", tone: "bad" },
};

export function describeRunStatus(status: string): { label: string; tone: RunTone } {
  const known = STATUS_PRESENTATION[status as ResearchRunStatus];
  if (known) return known;
  const label = status ? status.charAt(0).toUpperCase() + status.slice(1) : "Unknown";
  return { label, tone: "neutral" };
}

const DATE_ONLY = /^(\d{4})-(\d{2})-(\d{2})$/;

/** "2026-10-06" -> "Oct 6, 2026". Date-only values are formatted from their
 * parts so the viewer's timezone can never shift the calendar day. */
export function formatAnalysisDate(value: string | null): string {
  if (!value) return "Not available";
  const match = DATE_ONLY.exec(value);
  if (!match) return value;
  const date = new Date(Number(match[1]), Number(match[2]) - 1, Number(match[3]));
  return date.toLocaleDateString("en-US", { month: "short", day: "numeric", year: "numeric" });
}

/** ISO timestamp -> "Oct 6, 2:05 PM" in the viewer's timezone. */
export function formatCreatedAt(value: string | null): string {
  if (!value) return "Not available";
  const date = new Date(value);
  if (Number.isNaN(date.getTime())) return value;
  return date.toLocaleString("en-US", {
    month: "short",
    day: "numeric",
    hour: "numeric",
    minute: "2-digit",
  });
}

/** Where a historical run opens: finished runs show their research, runs
 * still in progress (or failed) show their processing state. */
export function pathForRun(run: { run_id: string; status: string }): string {
  const destination = run.status === "completed" || run.status === "partial" ? "research" : "processing";
  return `/runs/${encodeURIComponent(run.run_id)}/${destination}`;
}
