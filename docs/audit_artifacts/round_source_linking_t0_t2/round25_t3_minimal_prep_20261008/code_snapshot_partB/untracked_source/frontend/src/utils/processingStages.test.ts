import { describe, expect, it } from "vitest";
import { makeRunRecord } from "../tests/factories";
import {
  buildStagePlan,
  computeStageProgress,
  describeCaption,
  describeEta,
  formatDuration,
  sceneForProgress,
  structureEdgesShown,
} from "./processingStages";

const ALL = ["market", "sentiment", "news", "fundamentals"];

function progressFor(overrides: Parameters<typeof makeRunRecord>[0]) {
  return computeStageProgress(makeRunRecord({ selected_analysts: ALL, ...overrides }));
}

describe("buildStagePlan", () => {
  it("has all 17 stages in execution order for the full analyst team", () => {
    const plan = buildStagePlan(ALL);
    expect(plan).toHaveLength(17);
    expect(plan.map((entry) => entry.stage).slice(0, 8)).toEqual([
      "queued",
      "initializing",
      "market_analysis",
      "sentiment_analysis",
      "news_analysis",
      "fundamentals_analysis",
      "research_debate",
      "trading_plan",
    ]);
    expect(plan[16]?.stage).toBe("result_assembly");
  });

  it("keeps only the analyst stages that were selected, in product order", () => {
    const plan = buildStagePlan(["news", "market"]);
    expect(plan.filter((entry) => entry.group === "analysts").map((entry) => entry.stage)).toEqual([
      "market_analysis",
      "news_analysis",
    ]);
    expect(plan).toHaveLength(15);
  });

  it("assigns every stage to one of the four groups", () => {
    const groups = new Set(buildStagePlan(ALL).map((entry) => entry.group));
    expect([...groups].sort()).toEqual(["analysts", "debate", "prep", "structure"]);
  });
});

describe("computeStageProgress", () => {
  it("places a running run on its current stage", () => {
    const progress = progressFor({ status: "running", current_stage: "news_analysis", completed_units: 4 });
    const state = (stage: string) => progress.states[progress.plan.findIndex((entry) => entry.stage === stage)];
    expect(state("market_analysis")).toBe("done");
    expect(state("news_analysis")).toBe("current");
    expect(state("conflict_analysis")).toBe("pending");
    expect(progress.plan[progress.activeIndex]?.stage).toBe("news_analysis");
  });

  it("falls back to completed_units when the current stage is not a known one", () => {
    const progress = progressFor({ status: "running", current_stage: "research_pipeline", completed_units: 3 });
    expect(progress.states.filter((state) => state === "done")).toHaveLength(5);
    expect(progress.states[5]).toBe("current");
  });

  it("knows nothing for a legacy run without telemetry, and invents nothing", () => {
    const progress = progressFor({ status: "running", current_stage: null, completed_units: null });
    expect(progress.states.every((state) => state === "pending")).toBe(true);
    expect(progress.activeIndex).toBe(-1);
  });

  it("marks every stage done for a completed run", () => {
    const progress = progressFor({ status: "completed" });
    expect(progress.states.every((state) => state === "done")).toBe(true);
    expect(progress.activeIndex).toBe(progress.plan.length);
  });

  it("keeps only the really-completed stages done for a partial run", () => {
    const progress = progressFor({ status: "partial", completed_units: 4, current_stage: "completed_partial" });
    expect(progress.states.filter((state) => state === "done")).toHaveLength(6);
    expect(progress.states.at(-1)).toBe("pending");
  });

  it("places a failure on the stage that failed when it is known", () => {
    const progress = progressFor({ status: "failed", current_stage: "research_debate", started_at: "2026-10-07T10:00:00Z" });
    expect(progress.states[progress.activeIndex]).toBe("failed");
    expect(progress.plan[progress.activeIndex]?.stage).toBe("research_debate");
  });

  it("places a failure before the run started on the first stage", () => {
    const progress = progressFor({ status: "failed", current_stage: "failed", started_at: null });
    expect(progress.activeIndex).toBe(0);
    expect(progress.states[0]).toBe("failed");
  });

  it("places an early failure on Initializing", () => {
    const progress = progressFor({
      status: "failed",
      current_stage: "failed",
      started_at: "2026-10-07T10:00:00Z",
      completed_units: 0,
      progress_percent: 3,
    });
    expect(progress.plan[progress.activeIndex]?.stage).toBe("initializing");
  });

  it("places a later failure just after the completed units", () => {
    const progress = progressFor({
      status: "failed",
      current_stage: "failed",
      started_at: "2026-10-07T10:00:00Z",
      completed_units: 6,
      progress_percent: 64,
    });
    expect(progress.activeIndex).toBe(8);
    expect(progress.states.filter((state) => state === "failed")).toHaveLength(1);
  });
});

describe("sceneForProgress", () => {
  it("shows the scene of the stage group being worked on", () => {
    expect(sceneForProgress(progressFor({ status: "running", current_stage: "queued", completed_units: 0 }))).toBe("prep");
    expect(sceneForProgress(progressFor({ status: "running", current_stage: "news_analysis" }))).toBe("analysts");
    expect(sceneForProgress(progressFor({ status: "running", current_stage: "trading_plan" }))).toBe("debate");
    expect(sceneForProgress(progressFor({ status: "running", current_stage: "alpha_mapping" }))).toBe("structure");
  });

  it("starts at preparation when nothing is known and ends on structure when done", () => {
    expect(sceneForProgress(progressFor({ status: "running", current_stage: null, completed_units: null }))).toBe("prep");
    expect(sceneForProgress(progressFor({ status: "completed" }))).toBe("structure");
  });
});

describe("structureEdgesShown", () => {
  it("adds one connection per structure stage reached", () => {
    expect(structureEdgesShown(progressFor({ status: "running", current_stage: "research_debate" }))).toBe(0);
    expect(structureEdgesShown(progressFor({ status: "running", current_stage: "raw_outputs_saved" }))).toBe(1);
    expect(structureEdgesShown(progressFor({ status: "running", current_stage: "structure_graph" }))).toBe(4);
    expect(structureEdgesShown(progressFor({ status: "running", current_stage: "result_assembly" }))).toBe(8);
  });

  it("shows every connection once the run is complete", () => {
    expect(structureEdgesShown(progressFor({ status: "completed" }))).toBe(8);
  });
});

describe("describeCaption", () => {
  const running = progressFor({ status: "running", current_stage: "news_analysis" });

  it("prefers the backend's own message while the run is going", () => {
    const record = makeRunRecord({ status: "running", progress_message: "Running the News Analyst." });
    expect(describeCaption(record, running)).toBe("Running the News Analyst.");
  });

  it("falls back to a derived phrase when the backend sent none", () => {
    const record = makeRunRecord({ status: "running", progress_message: null });
    expect(describeCaption(record, running)).toBe("Analysts researching, news analysis");
    expect(describeCaption(record, progressFor({ status: "running", current_stage: "research_debate" }))).toBe(
      "Bull and bear cases debating"
    );
    expect(describeCaption(record, progressFor({ status: "running", current_stage: "trading_plan" }))).toBe(
      "Drafting the trading plan"
    );
    expect(describeCaption(record, progressFor({ status: "running", current_stage: "risk_review" }))).toBe("Reviewing risk");
    expect(describeCaption(record, progressFor({ status: "running", current_stage: "alpha_mapping" }))).toBe(
      "Building the structure, alpha mapping"
    );
  });

  it("describes a run that has not been placed yet", () => {
    const record = makeRunRecord({ status: "queued", progress_message: null });
    const progress = progressFor({ status: "queued", current_stage: null, completed_units: null });
    expect(describeCaption(record, progress)).toBe("Preparing the run");
    expect(describeCaption(null, progress)).toBe("Preparing the run");
  });

  it("uses its own wording for finished runs, whatever the backend message says", () => {
    expect(describeCaption(makeRunRecord({ status: "completed", progress_message: "Research run completed." }), progressFor({ status: "completed" }))).toBe(
      "Structure built, results are ready"
    );
    expect(describeCaption(makeRunRecord({ status: "partial" }), progressFor({ status: "partial", completed_units: 4 }))).toBe(
      "Finished with partial results"
    );
    const failed = progressFor({ status: "failed", current_stage: "research_debate", started_at: "2026-10-07T10:00:00Z" });
    expect(describeCaption(makeRunRecord({ status: "failed" }), failed)).toBe("Stopped during research debate");
  });
});

describe("formatDuration", () => {
  it("formats seconds, minutes and hours", () => {
    expect(formatDuration(0)).toBe("0s");
    expect(formatDuration(45)).toBe("45s");
    expect(formatDuration(98)).toBe("1m 38s");
    expect(formatDuration(3725)).toBe("1h 2m 5s");
  });

  it("rounds and never goes negative", () => {
    expect(formatDuration(59.6)).toBe("1m 0s");
    expect(formatDuration(-5)).toBe("0s");
  });
});

describe("describeEta", () => {
  function eta(overrides: Parameters<typeof makeRunRecord>[0], since = 0) {
    return describeEta(makeRunRecord({ status: "running", ...overrides }), since);
  }
  const available = { eta_status: "available" as const, eta_sample_count: 14 };

  it("shows a whole-minute range with its basis", () => {
    expect(eta({ ...available, estimated_remaining_seconds_min: 120, estimated_remaining_seconds_max: 240 })).toEqual({
      headline: "About 2–4 min left",
      basis: "Based on 14 similar runs",
    });
  });

  it("collapses a range that rounds to one number", () => {
    expect(eta({ ...available, estimated_remaining_seconds_min: 300, estimated_remaining_seconds_max: 300 }).headline).toBe(
      "About 5 min left"
    );
  });

  it("says less than a minute under a minute, never a seconds countdown", () => {
    expect(eta({ ...available, estimated_remaining_seconds_min: 10, estimated_remaining_seconds_max: 45 }).headline).toBe(
      "Less than a minute left"
    );
  });

  it("counts down in real time between polls", () => {
    const base = { ...available, estimated_remaining_seconds_min: 600, estimated_remaining_seconds_max: 960 };
    expect(eta(base, 0).headline).toBe("About 10–16 min left");
    expect(eta(base, 300).headline).toBe("About 5–11 min left");
    expect(eta(base, 840).headline).toBe("About 1–2 min left");
    expect(eta(base, 910).headline).toBe("Less than a minute left");
  });

  it("says it is taking longer once the estimate is exceeded, never negative or stuck at zero", () => {
    const base = { ...available, estimated_remaining_seconds_min: 60, estimated_remaining_seconds_max: 120 };
    expect(eta(base, 125)).toEqual({
      headline: "Taking longer than usual",
      basis: "Still working, the estimate was exceeded",
    });
    expect(eta(base, 9999).headline).toBe("Taking longer than usual");
  });

  it("uses the singular for a single similar run", () => {
    expect(
      eta({ eta_status: "available", eta_sample_count: 1, estimated_remaining_seconds_min: 300, estimated_remaining_seconds_max: 600 }).basis
    ).toBe("Based on 1 similar run");
  });

  it("says it is estimating when there is no history yet, or no status at all", () => {
    expect(eta({ eta_status: "estimating" })).toEqual({ headline: "Estimating time…", basis: "Not enough past runs to estimate yet" });
    expect(eta({ eta_status: null }).headline).toBe("Estimating time…");
  });

  it("claims nothing when an available estimate is missing its numbers", () => {
    expect(eta({ eta_status: "available", estimated_remaining_seconds_min: null, estimated_remaining_seconds_max: null }).headline).toBe(
      "In progress"
    );
  });

  it("shows a neutral line when no estimate can be given", () => {
    expect(eta({ eta_status: "unavailable" })).toEqual({ headline: "In progress", basis: "" });
  });

  it("announces the final states instead of an estimate", () => {
    expect(describeEta(makeRunRecord({ status: "completed", elapsed_seconds: 620 }), 0)).toEqual({
      headline: "Research complete",
      basis: "Finished in 10m 20s",
    });
    expect(describeEta(makeRunRecord({ status: "completed", elapsed_seconds: null }), 0).basis).toBe("");
    expect(describeEta(makeRunRecord({ status: "partial" }), 0).headline).toBe("Finished with partial results");
  });
});
