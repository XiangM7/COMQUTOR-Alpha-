import type { ReadinessResponse } from "../api/types";

export type ServerStatusTone = "ok" | "warn" | "neutral";

export interface ServerStatusView {
  tone: ServerStatusTone;
  /** Short text for the navigation bar. */
  label: string;
}

const LIVE_RESEARCH_LABELS: Record<string, string> = {
  disabled: "live research disabled",
  configured: "live research configured",
  misconfigured: "live research misconfigured",
};

/** One-line server summary for the navigation bar. Every state carries its
 * own text, so the status dot is never the only signal. */
export function describeServerStatus(
  readiness: ReadinessResponse | null,
  errorMessage: string | null
): ServerStatusView {
  if (errorMessage) return { tone: "warn", label: "Server status unavailable" };
  if (!readiness) return { tone: "neutral", label: "Checking server status…" };
  if (readiness.status !== "ready") return { tone: "warn", label: "Server not ready" };
  if (readiness.live_semantic_pipeline === "not_ready") {
    return { tone: "warn", label: "Server ready, live semantic pipeline not ready" };
  }
  const live = LIVE_RESEARCH_LABELS[readiness.real_execution] ?? readiness.real_execution;
  return {
    tone: readiness.real_execution === "misconfigured" ? "warn" : "ok",
    label: `Server ready, ${live}`,
  };
}
