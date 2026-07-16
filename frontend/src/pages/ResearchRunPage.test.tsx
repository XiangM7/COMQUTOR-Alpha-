import { render, screen, waitFor } from "@testing-library/react";
import { MemoryRouter, Route, Routes } from "react-router-dom";
import { afterEach, describe, expect, it, vi } from "vitest";
import * as client from "../api/client";
import { ResearchRunPage } from "./ResearchRunPage";

function renderPage(runId = "run-1") {
  return render(
    <MemoryRouter initialEntries={[`/runs/${runId}/research`]}>
      <Routes>
        <Route path="/runs/:runId/research" element={<ResearchRunPage />} />
      </Routes>
    </MemoryRouter>
  );
}

const BASE_ARTIFACTS = {
  metadata: true,
  raw_agent_outputs: true,
  structured_agent_outputs: true,
  final_report: false,
  alpha_matches: true,
  extracted_structures: true,
  structured_output_error_logs: false,
  week2_llm_error_logs: false,
  week2_pipeline_error_logs: false,
};

describe("ResearchRunPage", () => {
  afterEach(() => {
    vi.restoreAllMocks();
  });

  it("renders a completed run's summary and structured analyst outputs", async () => {
    vi.spyOn(client, "getResearchRunStatus").mockResolvedValue({
      run_id: "run-1",
      ticker: "NVDA",
      analysis_date: "2026-06-30",
      selected_analysts: ["market"],
      status: "completed",
      stage: "completed",
      error_code: null,
      message: "Research run completed.",
      created_at: null,
      started_at: null,
      completed_at: null,
      updated_at: null,
    });
    vi.spyOn(client, "getResearchRun").mockResolvedValue({
      run_id: "run-1",
      ticker: "NVDA",
      status: "completed",
      artifacts: BASE_ARTIFACTS,
      agent_output_count: 1,
      structured_output_count: 1,
      structure_graph_status: "ready",
      dominant_alphas: [],
      main_conflict: null,
      conflict_status: "ready",
      summary: "No dominant Alpha structure or admitted conflict was identified for this research run.",
    });
    vi.spyOn(client, "getAgentOutputs").mockResolvedValue({
      run_id: "run-1",
      ticker: "NVDA",
      status: "ok",
      schema_version: "week1a.structured_agent_outputs.v2",
      count: 1,
      structured_agent_outputs: [
        {
          claim_id: "c1",
          source_agent_output_id: "o1",
          run_id: "run-1",
          ticker: "NVDA",
          agent: "news_agent",
          claim: "AI capex is rising.",
          evidence: "Multiple hyperscalers raised guidance.",
          entities: ["NVDA"],
          factors: ["demand"],
          direction: "positive",
          confidence: 0.8,
        },
      ],
    });

    renderPage();

    await waitFor(() => expect(screen.getByText(/no dominant alpha structure/i)).toBeInTheDocument());
    expect(screen.getByText(/ai capex is rising/i)).toBeInTheDocument();
    expect(screen.getByText("news_agent")).toBeInTheDocument();
    expect(screen.getByText("c1")).toBeInTheDocument();
  });

  it("renders a partial run without failing", async () => {
    vi.spyOn(client, "getResearchRunStatus").mockResolvedValue({
      run_id: "run-1",
      ticker: "NVDA",
      analysis_date: null,
      selected_analysts: [],
      status: "partial",
      stage: "partial",
      error_code: null,
      message: "Research run completed partially.",
      created_at: null,
      started_at: null,
      completed_at: null,
      updated_at: null,
    });
    vi.spyOn(client, "getResearchRun").mockResolvedValue({
      run_id: "run-1",
      ticker: "NVDA",
      status: "partial",
      artifacts: BASE_ARTIFACTS,
      agent_output_count: 1,
      structured_output_count: 0,
      structure_graph_status: "not_ready",
      dominant_alphas: [],
      main_conflict: null,
      conflict_status: "not_ready",
      summary: "Conflict analysis is not ready for this research run.",
    });
    vi.spyOn(client, "getAgentOutputs").mockResolvedValue({
      run_id: "run-1",
      ticker: "NVDA",
      status: "ok",
      schema_version: "week1a.structured_agent_outputs.v2",
      count: 0,
      structured_agent_outputs: [],
    });

    renderPage();

    await waitFor(() => expect(screen.getByText("Partially completed")).toBeInTheDocument());
  });

  it("renders a failed run with a safe error code/message and a way back to Research", async () => {
    vi.spyOn(client, "getResearchRunStatus").mockResolvedValue({
      run_id: "run-1",
      status: "failed",
      error_code: "INTERNAL_ERROR",
      message: "Research request failed.",
    });
    const researchSpy = vi.spyOn(client, "getResearchRun");
    const agentOutputsSpy = vi.spyOn(client, "getAgentOutputs");

    renderPage();

    await waitFor(() => expect(screen.getByText("INTERNAL_ERROR")).toBeInTheDocument());
    expect(screen.getByText("Research request failed.")).toBeInTheDocument();
    expect(screen.getByRole("link", { name: /back to research/i })).toBeInTheDocument();
    // A failed run never triggers the canonical-result fetch.
    expect(researchSpy).not.toHaveBeenCalled();
    expect(agentOutputsSpy).not.toHaveBeenCalled();
  });

  it("never renders raw/private fields (raw_output, prompt, provider config, local paths)", async () => {
    vi.spyOn(client, "getResearchRunStatus").mockResolvedValue({
      run_id: "run-1",
      ticker: "NVDA",
      analysis_date: null,
      selected_analysts: [],
      status: "completed",
      stage: "completed",
      error_code: null,
      message: "",
      created_at: null,
      started_at: null,
      completed_at: null,
      updated_at: null,
    });
    vi.spyOn(client, "getResearchRun").mockResolvedValue({
      run_id: "run-1",
      ticker: "NVDA",
      status: "completed",
      artifacts: BASE_ARTIFACTS,
      agent_output_count: 0,
      structured_output_count: 0,
      structure_graph_status: "ready",
      dominant_alphas: [],
      main_conflict: null,
      conflict_status: "ready",
      summary: "No dominant Alpha structure or admitted conflict was identified for this research run.",
    });
    vi.spyOn(client, "getAgentOutputs").mockResolvedValue({
      run_id: "run-1",
      ticker: "NVDA",
      status: "ok",
      schema_version: "week1a.structured_agent_outputs.v2",
      count: 0,
      structured_agent_outputs: [],
    });

    const { container } = renderPage();
    await waitFor(() => expect(screen.getByText(/no dominant alpha structure/i)).toBeInTheDocument());

    const text = container.textContent ?? "";
    for (const forbidden of ["raw_output", "prompt", "/Users/", "postgresql://", "final_state"]) {
      expect(text).not.toContain(forbidden);
    }
  });
});
