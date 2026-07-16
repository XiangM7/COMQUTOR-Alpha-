import { render, screen, waitFor } from "@testing-library/react";
import { MemoryRouter } from "react-router-dom";
import { afterEach, describe, expect, it, vi } from "vitest";
import { App } from "./App";
import * as client from "./api/client";

function renderAt(path: string) {
  return render(
    <MemoryRouter initialEntries={[path]}>
      <App />
    </MemoryRouter>
  );
}

describe("App routing", () => {
  afterEach(() => {
    vi.restoreAllMocks();
  });

  it("redirects the root path to /research", async () => {
    vi.spyOn(client, "getReadiness").mockResolvedValue({
      status: 200,
      result: { status: "ready", database: "ready", job_manager: "ready", real_execution: "disabled" },
    });
    vi.spyOn(client, "getResearchHistory").mockResolvedValue({ status: "ok", items: [], next_cursor: null });

    renderAt("/");
    await waitFor(() => expect(screen.getByText(/research a ticker/i)).toBeInTheDocument());
  });

  it("renders each of the three run pages while preserving run_id in the URL", async () => {
    vi.spyOn(client, "getResearchRunStatus").mockResolvedValue({
      run_id: "run-abc",
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
      run_id: "run-abc",
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
      agent_output_count: 0,
      structured_output_count: 0,
      structure_graph_status: "ready",
      dominant_alphas: [],
      main_conflict: null,
      conflict_status: "ready",
      summary: "No dominant Alpha structure or admitted conflict was identified for this research run.",
    });
    vi.spyOn(client, "getAgentOutputs").mockResolvedValue({
      run_id: "run-abc",
      ticker: "NVDA",
      status: "ok",
      schema_version: "week1a.structured_agent_outputs.v2",
      count: 0,
      structured_agent_outputs: [],
    });

    renderAt("/runs/run-abc/research");
    await waitFor(() => expect(screen.getByText(/run-abc/i)).toBeInTheDocument());
    for (const link of screen.getAllByRole("link")) {
      if (link.textContent === "Research") expect(link).toHaveAttribute("href", "/runs/run-abc/research");
      if (link.textContent === "Structure Graph") expect(link).toHaveAttribute("href", "/runs/run-abc/structure");
      if (link.textContent === "Conflict Radar") expect(link).toHaveAttribute("href", "/runs/run-abc/conflicts");
    }
  });

  it("renders NotFoundPage for an unknown path", async () => {
    renderAt("/this/does/not/exist");
    await waitFor(() => expect(screen.getByText(/page not found/i)).toBeInTheDocument());
  });
});
