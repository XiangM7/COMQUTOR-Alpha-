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
    bull_evidence: [
      {
        claim_id: "c1",
        claim_text: "Strong demand evidence.",
        agent: "news_agent",
        match_score: 0.9,
        relation: "activation",
      },
    ],
    bear_evidence: [
      {
        claim_id: "c2",
        claim_text: "Valuation concern evidence.",
        agent: "risk_agent",
        match_score: 0.8,
        relation: "activation",
      },
    ],
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
      activation_formula_version: "activation.v2.evidence_local_structure.v1",
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
      data_sanity_status: "not_available",
      data_sanity_warning_count: 0,
      data_sanity_critical_count: 0,
      data_sanity_warnings: [],
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
      activation_formula_version: "activation.v2.evidence_local_structure.v1",
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
      activation_formula_version: "activation.v2.evidence_local_structure.v1",
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
      activation_formula_version: "activation.v2.evidence_local_structure.v1",
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
      data_sanity_status: "not_available",
      data_sanity_warning_count: 0,
      data_sanity_critical_count: 0,
      data_sanity_warnings: [],
    });

    renderPage();
    await waitFor(() => expect(screen.getByText(/only partially complete/i)).toBeInTheDocument());
  });

  // Regression test for docs/audit_artifacts/live_run_5ffe121a_pipeline_failure_report.md
  // (B5): "Persisted conflict result is missing required fields" must only
  // ever be shown for a genuinely corrupted/incomplete persisted result --
  // never for a run whose conflicts payload is actually complete, and
  // never conflated with the separate "not ready yet" state above.
  it("shows 'missing required fields' only for a genuinely corrupted persisted result", async () => {
    vi.spyOn(client, "getResearchConflicts").mockResolvedValue({
      run_id: "run-1",
      ticker: null,
      status: "failed",
      error_code: "CONFLICTS_CORRUPTED",
      message: "Persisted conflict result is missing required fields.",
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
      agent_output_count: 1,
      structured_output_count: 1,
      structure_graph_status: "ready",
      dominant_alphas: [],
      main_conflict: null,
      conflict_status: "not_ready",
      summary: "Conflict analysis is not ready for this research run.",
      data_sanity_status: "not_available",
      data_sanity_warning_count: 0,
      data_sanity_critical_count: 0,
      data_sanity_warnings: [],
    });

    renderPage();
    await waitFor(() =>
      expect(screen.getByText(/persisted conflict result is missing required fields/i)).toBeInTheDocument()
    );
    // Distinct from the "not ready yet" wording above -- never the same message.
    expect(screen.queryByText(/has not been generated for this research run yet/i)).not.toBeInTheDocument();
    expect(screen.queryByText(/only partially complete/i)).not.toBeInTheDocument();
  });

  it("never shows 'missing required fields' when the conflicts payload is actually complete", async () => {
    const mainConflict = makeConflict();
    vi.spyOn(client, "getResearchConflicts").mockResolvedValue({
      status: "ok",
      schema_version: "week4.alpha_conflicts.v1",
      formula_version: "week4.conflict_score.mvp_v1",
      activation_formula_version: "activation.v2.evidence_local_structure.v1",
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
      data_sanity_status: "not_available",
      data_sanity_warning_count: 0,
      data_sanity_critical_count: 0,
      data_sanity_warnings: [],
    });

    renderPage();
    await waitFor(() => expect(screen.getAllByText(mainConflict.explanation).length).toBeGreaterThan(0));
    expect(screen.queryByText(/missing required fields/i)).not.toBeInTheDocument();
    expect(screen.queryByText(/conflict analysis unavailable/i)).not.toBeInTheDocument();
  });

  // QA Closure v0.1.2 Item 3 (Candidate Conflict vs Main Conflict Strict
  // Separation). Shapes mirror the real saved run 5ffe121a-68fd-473b-82b5-
  // c9465332d8a2 (A301__A304 admitted + main, A304__A601 admitted
  // non-main, A101__A304 a real B2-denied candidate) -- used here only as
  // a QA fixture, never hardcoded into product logic.
  it("keeps admitted and candidate conflicts strictly separated across every section", async () => {
    const mainConflict = makeConflict({ conflict_id: "A301__A304", alpha_a: "A301", alpha_b: "A304" });
    const secondAdmitted = makeConflict({ conflict_id: "A304__A601", alpha_a: "A304", alpha_b: "A601" });
    const evidenceAudit = (alphaId: string) => ({ alpha_id: alphaId, qualifying_claim_ids: [], qualifying_count: 0, excluded: [] });

    vi.spyOn(client, "getResearchConflicts").mockResolvedValue({
      status: "ok",
      schema_version: "week4.alpha_conflicts.v1",
      formula_version: "week4.conflict_score.mvp_v1",
      activation_formula_version: "activation.v2.evidence_local_structure.v1",
      run_id: "run-1",
      ticker: "NVDA",
      conflicts: [mainConflict, secondAdmitted],
      main_conflict: mainConflict,
      arbitration: {
        declared_pair_count: 3,
        admitted_count: 2,
        suppressed_count: 1,
        rejected_count: 0,
        candidate_evaluations: [
          {
            alpha_a: "A301",
            alpha_b: "A304",
            outcome: "admitted",
            reason_codes: [],
            evidence_audit: { alpha_a: evidenceAudit("A301"), alpha_b: evidenceAudit("A304") },
          },
          {
            alpha_a: "A304",
            alpha_b: "A601",
            outcome: "admitted",
            reason_codes: [],
            evidence_audit: { alpha_a: evidenceAudit("A304"), alpha_b: evidenceAudit("A601") },
          },
          {
            alpha_a: "A101",
            alpha_b: "A304",
            outcome: "suppressed",
            reason_codes: [],
            evidence_audit: { alpha_a: evidenceAudit("A101"), alpha_b: evidenceAudit("A304") },
            bull_alpha_id: "A101",
            bear_alpha_id: "A304",
            admissibility: {
              admissibility_version: "conflict_evidence_admissibility.v1",
              status: "candidate",
              reason_codes: ["BULL_SCORE_BELOW_THRESHOLD"],
              bull_score: 40,
              bear_score: 70,
              bull_supporting_evidence_count: 0,
              bear_supporting_evidence_count: 2,
              bull_ticker_specific_support_count: 0,
              bear_ticker_specific_support_count: 2,
              bull_supporting_fact_group_ids: [],
              bear_supporting_fact_group_ids: ["g1", "g2"],
            },
          },
        ],
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
    await waitFor(() => expect(screen.getByText("Candidate and rejected pairs")).toBeInTheDocument());

    // "Main conflict" badges appear twice -- once in the top summary
    // panel, once inside "All admitted conflicts" (which lists every
    // admitted pair, main included) -- and every single instance must
    // belong to A301 vs A304's own card, never A304 vs A601's (also
    // admitted, but not main) and never A101 vs A304's (candidate).
    const mainBadges = screen.getAllByText("Main conflict");
    expect(mainBadges).toHaveLength(2);
    for (const badge of mainBadges) {
      const heading = badge.closest("article")?.querySelector("h3");
      expect(heading?.textContent).toBe("A301 vs A304");
    }

    const adminSection = screen.getByText("All admitted conflicts").closest("section");
    expect(adminSection).not.toBeNull();
    const adminHeadings = adminSection!.querySelectorAll("h3");
    expect(Array.from(adminHeadings).map((h) => h.textContent)).toEqual(["A301 vs A304", "A304 vs A601"]);
    // A304__A601's own card explicitly says Admitted, not Main.
    const secondAdmittedHeading = Array.from(adminHeadings).find((h) => h.textContent === "A304 vs A601");
    const secondAdmittedBadge = secondAdmittedHeading?.closest("article")?.querySelector(".conflict-card-badge");
    expect(secondAdmittedBadge?.textContent).toBe("Admitted conflict");

    const candidateSection = screen.getByText("Candidate and rejected pairs").closest("section");
    expect(candidateSection).not.toBeNull();
    expect(candidateSection!.textContent).toContain("A101 vs A304");
    expect(candidateSection!.textContent).toContain("Candidate conflict");
    // The strict invariant: no candidate section content ever claims Main
    // Conflict status, however it is capitalized/worded.
    expect(candidateSection!.textContent).not.toMatch(/main conflict/i);
    // Only the genuinely-denied pair appears here -- the two admitted
    // pairs (also present in candidate_evaluations as the full audit
    // trail) are filtered out, never duplicated into this section.
    expect(candidateSection!.textContent).not.toContain("A301 vs A304");
    expect(candidateSection!.textContent).not.toContain("A304 vs A601");
  });

  // Task section 5, Case D / section 4.1's required edge case: candidates
  // exist, zero admitted conflicts -- Research Summary/Conflict Radar must
  // report no main conflict, never promote the highest-scoring candidate,
  // and must not lose candidate visibility in the process.
  it("reports no main conflict when candidates exist but nothing is admitted, and keeps the candidate visible", async () => {
    vi.spyOn(client, "getResearchConflicts").mockResolvedValue({
      status: "ok",
      schema_version: "week4.alpha_conflicts.v1",
      formula_version: "week4.conflict_score.mvp_v1",
      activation_formula_version: "activation.v2.evidence_local_structure.v1",
      run_id: "run-1",
      ticker: "NVDA",
      conflicts: [],
      main_conflict: null,
      arbitration: {
        declared_pair_count: 1,
        admitted_count: 0,
        suppressed_count: 1,
        rejected_count: 0,
        candidate_evaluations: [
          {
            alpha_a: "A101",
            alpha_b: "A304",
            outcome: "suppressed",
            reason_codes: [],
            evidence_audit: {
              alpha_a: { alpha_id: "A101", qualifying_claim_ids: [], qualifying_count: 0, excluded: [] },
              alpha_b: { alpha_id: "A304", qualifying_claim_ids: [], qualifying_count: 0, excluded: [] },
            },
            bull_alpha_id: "A101",
            bear_alpha_id: "A304",
            admissibility: {
              admissibility_version: "conflict_evidence_admissibility.v1",
              status: "candidate",
              reason_codes: ["BULL_SCORE_BELOW_THRESHOLD"],
              bull_score: 40,
              bear_score: 70,
              bull_supporting_evidence_count: 0,
              bear_supporting_evidence_count: 2,
              bull_ticker_specific_support_count: 0,
              bear_ticker_specific_support_count: 2,
              bull_supporting_fact_group_ids: [],
              bear_supporting_fact_group_ids: ["g1", "g2"],
            },
          },
        ],
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
    await waitFor(() => expect(screen.getByText(/no conflicts detected/i)).toBeInTheDocument());
    // Never a fabricated main conflict -- no admitted-conflicts list, no
    // main-conflict badge anywhere.
    expect(screen.queryByText("All admitted conflicts")).not.toBeInTheDocument();
    expect(screen.queryByText(/main conflict/i)).not.toBeInTheDocument();
    // The candidate remains fully visible in its own section, never
    // removed just because there is no admitted conflict to show.
    expect(screen.getByText("Candidate and rejected pairs")).toBeInTheDocument();
    expect(screen.getByText("A101 vs A304")).toBeInTheDocument();
    expect(screen.getByText("Candidate conflict")).toBeInTheDocument();
  });
});
