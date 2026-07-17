import type { ResearchRunRecord } from "../api/types";

/** Fully-populated ResearchRunRecord for tests -- progress/ETA telemetry
 * defaults to the "no telemetry yet" nulls the backend reports for legacy
 * runs; override per test. */
export function makeRunRecord(overrides: Partial<ResearchRunRecord> = {}): ResearchRunRecord {
  return {
    run_id: "run-1",
    ticker: "NVDA",
    analysis_date: null,
    selected_analysts: ["market", "sentiment", "news", "fundamentals"],
    status: "queued",
    stage: null,
    error_code: null,
    message: "",
    created_at: null,
    started_at: null,
    completed_at: null,
    updated_at: null,
    profile_id: null,
    profile_display_name: null,
    progress_percent: null,
    current_stage: null,
    completed_units: null,
    total_units: null,
    progress_message: null,
    elapsed_seconds: null,
    eta_status: null,
    estimated_remaining_seconds_min: null,
    estimated_remaining_seconds_max: null,
    eta_sample_count: null,
    ...overrides,
  };
}
