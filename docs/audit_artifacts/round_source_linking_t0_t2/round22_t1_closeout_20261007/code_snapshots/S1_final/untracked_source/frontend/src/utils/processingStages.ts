import type { ResearchRunRecord } from "../api/types";

export type StageState = "done" | "current" | "failed" | "pending";
export type StageGroupKey = "prep" | "analysts" | "debate" | "structure";

export interface StageEntry {
  stage: string;
  label: string;
  group: StageGroupKey;
}

/** The frozen stage vocabulary in execution order (analyst stages are
 * filtered to the run's actual selection). Labels are text -- stage state
 * is additionally marked with a symbol and words, never color alone. */
const ANALYST_STAGE_BY_KEY: Record<string, { stage: string; label: string }> = {
  market: { stage: "market_analysis", label: "Market analysis" },
  sentiment: { stage: "sentiment_analysis", label: "Sentiment analysis" },
  news: { stage: "news_analysis", label: "News analysis" },
  fundamentals: { stage: "fundamentals_analysis", label: "Fundamentals analysis" },
};

const PRE_ANALYST_STAGES: ReadonlyArray<StageEntry> = [
  { stage: "queued", label: "Queued", group: "prep" },
  { stage: "initializing", label: "Initializing", group: "prep" },
];

const POST_ANALYST_STAGES: ReadonlyArray<StageEntry> = [
  { stage: "research_debate", label: "Research debate", group: "debate" },
  { stage: "trading_plan", label: "Trading plan", group: "debate" },
  { stage: "risk_review", label: "Risk review", group: "debate" },
  { stage: "raw_outputs_saved", label: "Saving agent outputs", group: "structure" },
  { stage: "structured_claims", label: "Structured claims", group: "structure" },
  { stage: "alpha_mapping", label: "Alpha mapping", group: "structure" },
  { stage: "structure_graph", label: "Structure graph", group: "structure" },
  { stage: "activation_scoring", label: "Activation scoring", group: "structure" },
  { stage: "conflict_analysis", label: "Conflict analysis", group: "structure" },
  { stage: "result_persistence", label: "Persisting results", group: "structure" },
  { stage: "result_assembly", label: "Assembling results", group: "structure" },
];

export const ANALYST_ORDER = ["market", "sentiment", "news", "fundamentals"] as const;

export const STAGE_GROUPS: ReadonlyArray<{ key: StageGroupKey; name: string }> = [
  { key: "prep", name: "Preparing" },
  { key: "analysts", name: "Analyst research" },
  { key: "debate", name: "Debate and decision" },
  { key: "structure", name: "Structure analysis" },
];

export function buildStagePlan(selectedAnalysts: string[]): StageEntry[] {
  const selected = new Set(selectedAnalysts);
  const analystStages = ANALYST_ORDER.filter((key) => selected.has(key)).flatMap((key) => {
    const entry = ANALYST_STAGE_BY_KEY[key];
    return entry ? [{ ...entry, group: "analysts" as const }] : [];
  });
  return [...PRE_ANALYST_STAGES, ...analystStages, ...POST_ANALYST_STAGES];
}

/** The parts of a run record stage progress is derived from. */
export type StageProgressInput = Pick<
  ResearchRunRecord,
  "selected_analysts" | "status" | "current_stage" | "completed_units" | "progress_percent" | "started_at"
>;

export interface StageProgress {
  plan: StageEntry[];
  states: StageState[];
  /** Index of the stage being worked on (or that failed). `plan.length`
   * once everything is done, -1 when nothing is known yet. */
  activeIndex: number;
}

/**
 * Per-stage state for the Stages panel and the pipeline scene. Everything
 * comes from the status endpoint's persisted telemetry (`current_stage`,
 * `completed_units`); a failed or partial run is placed from the same
 * fields, never guessed from elapsed time.
 */
export function computeStageProgress(record: StageProgressInput): StageProgress {
  const plan = buildStagePlan(record.selected_analysts);
  const currentIndex = plan.findIndex((entry) => entry.stage === record.current_stage);
  const completedUnits = Math.max(0, Math.floor(record.completed_units ?? 0));
  const completedPlanCount = Math.min(plan.length, PRE_ANALYST_STAGES.length + completedUnits);

  let inferredFailureIndex = -1;
  if (record.status === "failed") {
    if (currentIndex >= 0) {
      inferredFailureIndex = currentIndex;
    } else if (record.started_at === null) {
      inferredFailureIndex = 0;
    } else if (completedUnits === 0 && (record.progress_percent ?? 0) < 10) {
      inferredFailureIndex = 1;
    } else {
      inferredFailureIndex = Math.min(completedPlanCount, plan.length - 1);
    }
  }

  const states = plan.map((_, index): StageState => {
    if (record.status === "completed") return "done";
    if (record.status === "partial") return index < completedPlanCount ? "done" : "pending";
    if (record.status === "failed") {
      return index < inferredFailureIndex ? "done" : index === inferredFailureIndex ? "failed" : "pending";
    }
    if (currentIndex >= 0) {
      return index < currentIndex ? "done" : index === currentIndex ? "current" : "pending";
    }
    if (record.completed_units !== null) {
      return index < completedPlanCount ? "done" : index === completedPlanCount ? "current" : "pending";
    }
    return "pending";
  });

  let activeIndex: number;
  if (record.status === "completed") activeIndex = plan.length;
  else if (record.status === "failed") activeIndex = inferredFailureIndex;
  else if (record.status === "partial") activeIndex = completedPlanCount;
  else if (currentIndex >= 0) activeIndex = currentIndex;
  else if (record.completed_units !== null) activeIndex = completedPlanCount;
  else activeIndex = -1;

  return { plan, states, activeIndex };
}

/** Scene shown in the pipeline card. */
export function sceneForProgress(progress: StageProgress): StageGroupKey {
  if (progress.activeIndex < 0) return "prep";
  if (progress.activeIndex >= progress.plan.length) return "structure";
  return progress.plan[progress.activeIndex]?.group ?? "prep";
}

const STRUCTURE_STAGE_ORDER = [
  "raw_outputs_saved",
  "structured_claims",
  "alpha_mapping",
  "structure_graph",
  "activation_scoring",
  "conflict_analysis",
  "result_persistence",
  "result_assembly",
] as const;

export const STRUCTURE_EDGE_COUNT = STRUCTURE_STAGE_ORDER.length;

/** How many connections of the structure graph are drawn: one per
 * structure-analysis stage reached, all of them once the run is done. */
export function structureEdgesShown(progress: StageProgress): number {
  if (progress.activeIndex >= progress.plan.length) return STRUCTURE_EDGE_COUNT;
  const stage = progress.plan[progress.activeIndex]?.stage;
  const position = STRUCTURE_STAGE_ORDER.findIndex((key) => key === stage);
  return position < 0 ? 0 : position + 1;
}

/** Short sentence under the pipeline scene. While the run is going, the
 * backend's own progress message wins (it is what is actually happening);
 * the derived phrase is only a fallback and the wording of finished runs. */
export function describeCaption(
  record: Pick<ResearchRunRecord, "status" | "progress_message"> | null,
  progress: StageProgress
): string {
  const status = record?.status ?? "queued";
  if (status === "completed") return "Structure built, results are ready";
  if (status === "partial") return "Finished with partial results";
  const entry = progress.plan[progress.activeIndex];
  if (status === "failed") {
    return entry ? `Stopped during ${entry.label.toLowerCase()}` : "Stopped before finishing";
  }
  if (record?.progress_message) return record.progress_message;
  if (!entry) return "Preparing the run";
  switch (entry.group) {
    case "prep":
      return `Preparing the run, ${entry.label.toLowerCase()}`;
    case "analysts":
      return `Analysts researching, ${entry.label.toLowerCase()}`;
    case "debate":
      if (entry.stage === "research_debate") return "Bull and bear cases debating";
      if (entry.stage === "trading_plan") return "Drafting the trading plan";
      return "Reviewing risk";
    case "structure":
      return `Building the structure, ${entry.label.toLowerCase()}`;
  }
}

/** "45s", "3m 40s", "1h 2m 5s". */
export function formatDuration(totalSeconds: number): string {
  const total = Math.max(0, Math.round(totalSeconds));
  if (total < 60) return `${total}s`;
  const minutes = Math.floor(total / 60);
  const seconds = total % 60;
  if (minutes >= 60) return `${Math.floor(minutes / 60)}h ${minutes % 60}m ${seconds}s`;
  return `${minutes}m ${seconds}s`;
}

export interface EtaView {
  headline: string;
  basis: string;
}

/**
 * Estimate text. `secondsSincePoll` is the real time since the status that
 * carried the estimate arrived: the estimate counts down locally between
 * polls (time only -- it never moves the progress percentage) and every new
 * poll re-calibrates it. Ranges are whole minutes; there is never a
 * seconds-level countdown, a negative value, or a stuck zero.
 */
export function describeEta(
  record: Pick<
    ResearchRunRecord,
    "status" | "eta_status" | "estimated_remaining_seconds_min" | "estimated_remaining_seconds_max" | "eta_sample_count" | "elapsed_seconds"
  >,
  secondsSincePoll: number
): EtaView {
  if (record.status === "completed") {
    return {
      headline: "Research complete",
      basis: record.elapsed_seconds !== null ? `Finished in ${formatDuration(record.elapsed_seconds)}` : "",
    };
  }
  if (record.status === "partial") {
    return { headline: "Finished with partial results", basis: "Some stages did not produce results" };
  }
  if (record.eta_status === "available") {
    const min = record.estimated_remaining_seconds_min;
    const max = record.estimated_remaining_seconds_max;
    if (min !== null && max !== null) {
      const low = min - secondsSincePoll;
      const high = max - secondsSincePoll;
      const samples = record.eta_sample_count ?? 0;
      const basis = `Based on ${samples} similar ${samples === 1 ? "run" : "runs"}`;
      if (high <= 0) {
        return { headline: "Taking longer than usual", basis: "Still working, the estimate was exceeded" };
      }
      if (high < 60) return { headline: "Less than a minute left", basis };
      const lowMinutes = Math.max(1, Math.floor(Math.max(low, 0) / 60));
      const highMinutes = Math.ceil(high / 60);
      return {
        headline:
          lowMinutes >= highMinutes
            ? `About ${highMinutes} min left`
            : `About ${lowMinutes}–${highMinutes} min left`,
        basis,
      };
    }
  }
  if (record.eta_status === "estimating" || record.eta_status === null) {
    return { headline: "Estimating time…", basis: "Not enough past runs to estimate yet" };
  }
  return { headline: "In progress", basis: "" };
}
