import { fireEvent, render, screen, waitFor, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { MemoryRouter, Route, Routes } from "react-router-dom";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { App } from "./App";
import * as client from "./api/client";
import { makeRunRecord } from "./tests/factories";
import { ResearchPage } from "./pages/ResearchPage";

function renderAt(path: string) {
  return render(
    <MemoryRouter initialEntries={[path]}>
      <App />
    </MemoryRouter>
  );
}

describe("App routing", () => {
  beforeEach(() => {
    // Every page sits under the navigation bar, which shows server status.
    vi.spyOn(client, "getReadiness").mockResolvedValue({
      status: 200,
      result: { status: "ready", database: "ready", job_manager: "ready", real_execution: "disabled", live_semantic_pipeline: "not_applicable" },
    });
  });

  afterEach(() => {
    vi.restoreAllMocks();
  });

  it("redirects the root path to /research", async () => {
    vi.spyOn(client, "getReadiness").mockResolvedValue({
      status: 200,
      result: { status: "ready", database: "ready", job_manager: "ready", real_execution: "disabled", live_semantic_pipeline: "not_applicable" },
    });
    vi.spyOn(client, "getResearchHistory").mockResolvedValue({ status: "ok", items: [], next_cursor: null });

    renderAt("/");
    await waitFor(() => expect(screen.getByText(/research a ticker/i)).toBeInTheDocument());
  });

  it("renders each of the three run pages while preserving run_id in the URL", async () => {
    vi.spyOn(client, "getResearchRunStatus").mockResolvedValue(
      makeRunRecord({
        run_id: "run-abc",
        selected_analysts: [],
        status: "completed",
        stage: "completed",
      })
    );
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
      data_sanity_status: "not_available",
      data_sanity_warning_count: 0,
      data_sanity_critical_count: 0,
      data_sanity_warnings: [],
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
    // The run-sections navigation, not the app's primary navigation (whose
    // "Research" link points at the landing page).
    const runNav = screen.getByRole("navigation", { name: "Research run sections" });
    for (const link of within(runNav).getAllByRole("link")) {
      if (link.textContent === "Research") expect(link).toHaveAttribute("href", "/runs/run-abc/research");
      if (link.textContent === "Structure Graph") expect(link).toHaveAttribute("href", "/runs/run-abc/structure");
      if (link.textContent === "Conflict Radar") expect(link).toHaveAttribute("href", "/runs/run-abc/conflicts");
    }
  });

  it("renders the Processing page for /runs/:runId/processing (refresh restores from the URL)", async () => {
    vi.spyOn(client, "getResearchRunStatus").mockResolvedValue(
      makeRunRecord({
        run_id: "run-abc",
        status: "running",
        stage: "research_pipeline",
        progress_percent: 43,
        current_stage: "news_analysis",
        completed_units: 4,
        total_units: 15,
        progress_message: "Running the News Analyst.",
        elapsed_seconds: 98,
        eta_status: "estimating",
        eta_sample_count: 0,
      })
    );

    renderAt("/runs/run-abc/processing");
    await waitFor(() => expect(screen.getByRole("heading", { name: /analyzing nvda/i })).toBeInTheDocument());
    expect(screen.getByRole("progressbar")).toHaveAttribute("aria-valuenow", "43");
  });

  it("shows the server status in the navigation bar, on the Research page and elsewhere", async () => {
    vi.spyOn(client, "getResearchHistory").mockResolvedValue({ status: "ok", items: [], next_cursor: null });

    renderAt("/research");
    await waitFor(() => expect(screen.getByRole("status")).toHaveTextContent("Server ready, live research disabled"));
    // One /ready request serves both the status and the submit guard.
    expect(client.getReadiness).toHaveBeenCalledTimes(1);
  });

  it("renders NotFoundPage for an unknown path", async () => {
    renderAt("/this/does/not/exist");
    await waitFor(() => expect(screen.getByText(/page not found/i)).toBeInTheDocument());
  });
});

describe("Recent runs routing", () => {
  afterEach(() => {
    vi.restoreAllMocks();
  });

  const cases = [
    ["queued", "processing"],
    ["running", "processing"],
    ["failed", "processing"],
    ["completed", "research"],
    ["partial", "research"],
  ] as const;

  function renderRecentRun(status: (typeof cases)[number][0]) {
    vi.spyOn(client, "getReadiness").mockResolvedValue({
      status: 200,
      result: { status: "ready", database: "ready", job_manager: "ready", real_execution: "disabled", live_semantic_pipeline: "not_applicable" },
    });
    vi.spyOn(client, "getResearchHistory").mockResolvedValue({
      status: "ok",
      items: [makeRunRecord({ run_id: `run-${status}`, ticker: status.toUpperCase(), status })],
      next_cursor: null,
    });
    return render(
      <MemoryRouter initialEntries={["/research"]}>
        <Routes>
          <Route path="/research" element={<ResearchPage />} />
          <Route path="/runs/:runId/processing" element={<p>processing destination</p>} />
          <Route path="/runs/:runId/research" element={<p>research destination</p>} />
        </Routes>
      </MemoryRouter>
    );
  }

  async function openRecentRun(status: (typeof cases)[number][0]) {
    fireEvent.click(screen.getByRole("button", { name: /recent runs/i }));
    return screen.findByRole("link", { name: new RegExp(status.toUpperCase()) });
  }

  it.each(cases)("routes a %s run by mouse to %s", async (status, destination) => {
    renderRecentRun(status);
    fireEvent.click(await openRecentRun(status));
    expect(await screen.findByText(`${destination} destination`)).toBeInTheDocument();
  });

  it.each(cases)("routes a %s run by Enter to %s", async (status, destination) => {
    const user = userEvent.setup();
    renderRecentRun(status);
    (await openRecentRun(status)).focus();
    await user.keyboard("{Enter}");
    expect(await screen.findByText(`${destination} destination`)).toBeInTheDocument();
  });
});
