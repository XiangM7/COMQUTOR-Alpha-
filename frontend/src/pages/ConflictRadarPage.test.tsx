import { render, screen, waitFor } from "@testing-library/react";
import { MemoryRouter, Route, Routes } from "react-router-dom";
import { afterEach, describe, expect, it, vi } from "vitest";
import * as client from "../api/client";
import type { AlphaConflict } from "../api/types";
import { ConflictRadarPage } from "./ConflictRadarPage";

function renderPage(runId = "run-1") {
  return render(
    <MemoryRouter initialEntries={[`/runs/${runId}/conflicts`]}>
      <Routes>
        <Route path="/runs/:runId/conflicts" element={<ConflictRadarPage />} />
      </Routes>
    </MemoryRouter>
  );
}

function makeConflict(overrides: Partial<AlphaConflict> = {}): AlphaConflict {
  return {
    conflict_id: "A101__A304",
    alpha_a: "A101",
    alpha_b: "A304",
    bull_alpha_id: "A101",
    bear_alpha_id: "A304",
    bull_structure: {
      alpha_id: "A101",
      alpha_name: "Demand Growth",
      activation_score: 80,
      status: "dominant",
      direction: "positive",
      claim_ids: ["c1"],
      source_agent_output_ids: ["o1"],
      agents: ["news_agent"],
      evidence: ["Strong demand evidence."],
      match_scores: [0.9],
    },
    bear_structure: {
      alpha_id: "A304",
      alpha_name: "Valuation Risk",
      activation_score: 70,
      status: "active",
      direction: "negative",
      claim_ids: ["c2"],
      source_agent_output_ids: ["o2"],
      agents: ["risk_agent"],
      evidence: ["Valuation concern evidence."],
      match_scores: [0.8],
    },
    components: {
      activation_a: 80,
      activation_b: 70,
      minimum_activation: 70,
      contradiction_weight: 1,
      alpha_a_evidence_strength: 0.9,
      alpha_b_evidence_strength: 0.8,
      evidence_strength: 0.85,
    },
    alpha_a_strength: 0.9,
    alpha_b_strength: 0.8,
    evidence_strength: 0.85,
    conflict_score: 72.5,
    conflict_level: "medium_high",
    reason_codes: [],
    explanation: "Demand Growth and Valuation Risk present a bull-vs-bear structural tension.",
    ...overrides,
  };
}

describe("ConflictRadarPage", () => {
  afterEach(() => {
    vi.restoreAllMocks();
  });

  it("renders main_conflict using only backend-provided fields", async () => {
    const mainConflict = makeConflict();
    vi.spyOn(client, "getResearchConflicts").mockResolvedValue({
      status: "ok",
      schema_version: "week4.alpha_conflicts.v1",
      formula_version: "week4.conflict_score.mvp_v1",
      run_id: "run-1",
      ticker: "NVDA",
      conflicts: [mainConflict],
      main_conflict: mainConflict,
      arbitration: {
        declared_pair_count: 1,
        admitted_count: 1,
        suppressed_count: 0,
        rejected_count: 0,
        candidate_evaluations: [],
      },
    });
    vi.spyOn(client, "getResearchRun").mockResolvedValue({
      run_id: "run-1",
      ticker: "NVDA",
      status: "completed",
      artifacts: {
        metadata: true,
        raw_agent_outputs: true,
        structured_agent_outputs: true,
        final_report: false,
        alpha_matches: true,
        extracted_structures: true,
        structured_output_error_logs: false,
        week2_llm_error_logs: false,
        week2_pipeline_error_logs: false,
      },
      agent_output_count: 2,
      structured_output_count: 2,
      structure_graph_status: "ready",
      dominant_alphas: [],
      main_conflict: mainConflict,
      conflict_status: "ready",
      summary: mainConflict.explanation,
    });

    renderPage();

    await waitFor(() => expect(screen.getAllByText(mainConflict.explanation).length).toBeGreaterThan(0));
    expect(screen.getAllByText(/main conflict/i).length).toBeGreaterThan(0);
    expect(screen.getAllByText(/A101 vs A304/).length).toBeGreaterThan(0);
  });

  it("orders the conflict list using the backend-provided order (never re-sorted client-side)", async () => {
    const first = makeConflict({ conflict_id: "A101__A304", alpha_a: "A101", alpha_b: "A304", conflict_score: 40 });
    const second = makeConflict({ conflict_id: "A201__A501", alpha_a: "A201", alpha_b: "A501", conflict_score: 90 });
    vi.spyOn(client, "getResearchConflicts").mockResolvedValue({
      status: "ok",
      schema_version: "week4.alpha_conflicts.v1",
      formula_version: "week4.conflict_score.mvp_v1",
      run_id: "run-1",
      ticker: "NVDA",
      conflicts: [first, second], // backend order: lower score first -- must not be re-sorted by score
      main_conflict: first,
      arbitration: {
        declared_pair_count: 2,
        admitted_count: 2,
        suppressed_count: 0,
        rejected_count: 0,
        candidate_evaluations: [],
      },
    });
    vi.spyOn(client, "getResearchRun").mockResolvedValue({
      run_id: "run-1",
      ticker: null,
      status: "failed",
      error_code: "RUN_STATUS_NOT_FOUND",
      message: "not used",
    });

    renderPage();
    await waitFor(() => expect(screen.getByText(/all admitted conflicts/i)).toBeInTheDocument());
    const headings = screen.getAllByRole("heading", { level: 3 }).map((el) => el.textContent);
    const firstIndex = headings.findIndex((text) => text?.includes("A101"));
    const secondIndex = headings.findIndex((text) => text?.includes("A201"));
    expect(firstIndex).toBeLessThan(secondIndex);
  });

  it("shows evidence traceability references (claim_id, agent, match score) without raw output", async () => {
    const mainConflict = makeConflict();
    vi.spyOn(client, "getResearchConflicts").mockResolvedValue({
      status: "ok",
      schema_version: "week4.alpha_conflicts.v1",
      formula_version: "week4.conflict_score.mvp_v1",
      run_id: "run-1",
      ticker: "NVDA",
      conflicts: [mainConflict],
      main_conflict: mainConflict,
      arbitration: { declared_pair_count: 1, admitted_count: 1, suppressed_count: 0, rejected_count: 0, candidate_evaluations: [] },
    });
    vi.spyOn(client, "getResearchRun").mockResolvedValue({
      run_id: "run-1",
      ticker: null,
      status: "failed",
      error_code: "RUN_STATUS_NOT_FOUND",
      message: "not used",
    });

    renderPage();
    await waitFor(() => expect(screen.getByText(/evidence traceability/i)).toBeInTheDocument());
    expect(screen.getByText("c1")).toBeInTheDocument();
    expect(screen.getByText("c2")).toBeInTheDocument();
    expect(screen.getByText(/match 0\.90/)).toBeInTheDocument();
  });

  it("shows a 'no conflicts detected' empty state that never implies zero risk", async () => {
    vi.spyOn(client, "getResearchConflicts").mockResolvedValue({
      status: "ok",
      schema_version: "week4.alpha_conflicts.v1",
      formula_version: "week4.conflict_score.mvp_v1",
      run_id: "run-1",
      ticker: "NVDA",
      conflicts: [],
      main_conflict: null,
      arbitration: { declared_pair_count: 0, admitted_count: 0, suppressed_count: 0, rejected_count: 0, candidate_evaluations: [] },
    });
    vi.spyOn(client, "getResearchRun").mockResolvedValue({
      run_id: "run-1",
      ticker: null,
      status: "failed",
      error_code: "RUN_STATUS_NOT_FOUND",
      message: "not used",
    });

    renderPage();
    await waitFor(() => expect(screen.getByText(/no conflicts detected/i)).toBeInTheDocument());
    const text = (screen.getByText(/no conflicts detected/i).closest("section")?.textContent ?? "").toLowerCase();
    // Must not claim the position is risk-free -- and must, in fact,
    // explicitly say the opposite (no conflicts found is not a safety
    // guarantee).
    expect(text).not.toContain("risk-free");
    expect(text).not.toContain("guaranteed");
    expect(text).toContain("does not mean the position carries no risk");
  });

  it("distinguishes 'conflicts not ready' from 'no conflicts detected'", async () => {
    vi.spyOn(client, "getResearchConflicts").mockResolvedValue({
      run_id: "run-1",
      ticker: null,
      status: "failed",
      error_code: "CONFLICTS_NOT_READY",
      message: "Conflict analysis has not been generated for this research run yet.",
    });
    vi.spyOn(client, "getResearchRun").mockResolvedValue({
      run_id: "run-1",
      ticker: "NVDA",
      status: "partial",
      artifacts: {
        metadata: true,
        raw_agent_outputs: true,
        structured_agent_outputs: true,
        final_report: false,
        alpha_matches: true,
        extracted_structures: false,
        structured_output_error_logs: false,
        week2_llm_error_logs: false,
        week2_pipeline_error_logs: false,
      },
      agent_output_count: 1,
      structured_output_count: 1,
      structure_graph_status: "not_ready",
      dominant_alphas: [],
      main_conflict: null,
      conflict_status: "not_ready",
      summary: "Conflict analysis is not ready for this research run.",
    });

    renderPage();
    await waitFor(() => expect(screen.getByText(/only partially complete/i)).toBeInTheDocument());
  });
});
