import { render, screen, waitFor } from "@testing-library/react";
import { MemoryRouter, Route, Routes } from "react-router-dom";
import { afterEach, describe, expect, it, vi } from "vitest";
import * as client from "../api/client";
import type { AgentOutputsResponse, CanonicalResearchResponse, StructuredAgentOutputRecord } from "../api/types";
import { makeRunRecord } from "../tests/factories";
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
    vi.spyOn(client, "getResearchRunStatus").mockResolvedValue(
      makeRunRecord({
        analysis_date: "2026-06-30",
        selected_analysts: ["market"],
        status: "completed",
        stage: "completed",
        message: "Research run completed.",
      })
    );
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
      data_sanity_status: "not_available",
      data_sanity_warning_count: 0,
      data_sanity_critical_count: 0,
      data_sanity_warnings: [],
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

  function mockAgentOutputs(
    records: StructuredAgentOutputRecord[],
    dataSanity: Partial<
      Pick<
        CanonicalResearchResponse,
        "data_sanity_status" | "data_sanity_warning_count" | "data_sanity_critical_count" | "data_sanity_warnings"
      >
    > = {}
  ): AgentOutputsResponse {
    vi.spyOn(client, "getResearchRunStatus").mockResolvedValue(
      makeRunRecord({
        selected_analysts: ["market"],
        status: "completed",
        stage: "completed",
        message: "Research run completed.",
      })
    );
    vi.spyOn(client, "getResearchRun").mockResolvedValue({
      run_id: "run-1",
      ticker: "SNDK",
      status: "completed",
      artifacts: BASE_ARTIFACTS,
      agent_output_count: records.length,
      structured_output_count: records.length,
      structure_graph_status: "ready",
      dominant_alphas: [],
      main_conflict: null,
      conflict_status: "ready",
      summary: "Summary.",
      data_sanity_status: "not_available",
      data_sanity_warning_count: 0,
      data_sanity_critical_count: 0,
      data_sanity_warnings: [],
      ...dataSanity,
    });
    const response: AgentOutputsResponse = {
      run_id: "run-1",
      ticker: "SNDK",
      status: "ok",
      schema_version: "week1a.structured_agent_outputs.v2",
      count: records.length,
      structured_agent_outputs: records,
    };
    vi.spyOn(client, "getAgentOutputs").mockResolvedValue(response);
    return response;
  }

  function findingRecord(overrides: Partial<StructuredAgentOutputRecord>): StructuredAgentOutputRecord {
    return {
      claim_id: "c1",
      source_agent_output_id: "o1",
      run_id: "run-1",
      ticker: "SNDK",
      agent: "market_agent",
      claim: "From a May 1st open, the stock surged 25%.",
      // Deterministic splitter sets evidence identical to claim.
      evidence: "From a May 1st open, the stock surged 25%.",
      entities: ["SNDK"],
      factors: [],
      direction: "unknown",
      confidence: 0.5,
      ...overrides,
    };
  }

  it("renders agent and direction as two separate DOM elements, never concatenated", async () => {
    mockAgentOutputs([
      findingRecord({ claim_id: "c1", agent: "market_agent", direction: "negative" }),
    ]);

    const { container } = renderPage();

    await waitFor(() => expect(screen.getByText("market_agent")).toBeInTheDocument());
    // Agent and Direction are two independently labeled dt/dd pairs...
    expect(screen.getByText("Agent")).toBeInTheDocument();
    expect(screen.getByText("Direction")).toBeInTheDocument();
    const agentValue = screen.getByText("market_agent");
    const directionValue = screen.getByText("negative");
    expect(agentValue).not.toBe(directionValue);
    expect(agentValue.parentElement).not.toBe(directionValue.parentElement);
    // ...never rendered as one concatenated string/text node, in either order.
    expect(container.textContent).not.toContain("market_agentnegative");
    expect(container.textContent).not.toContain("Agent: market_agentDirection:");
    // Evidence identical to the claim is not rendered a second time.
    expect(screen.getAllByText(/From a May 1st open/)).toHaveLength(1);
  });

  it("displays a positive-direction finding in the main list", async () => {
    mockAgentOutputs([findingRecord({ claim_id: "c1", direction: "positive" })]);
    renderPage();
    await waitFor(() => expect(screen.getByText("positive")).toBeInTheDocument());
    expect(screen.getByText(/From a May 1st open/)).toBeInTheDocument();
  });

  it("displays a negative-direction finding in the main list", async () => {
    mockAgentOutputs([findingRecord({ claim_id: "c1", direction: "negative" })]);
    renderPage();
    await waitFor(() => expect(screen.getByText("negative")).toBeInTheDocument());
    expect(screen.getByText(/From a May 1st open/)).toBeInTheDocument();
  });

  it("hides an unknown-direction finding from the main list but reports it as hidden", async () => {
    mockAgentOutputs([
      findingRecord({ claim_id: "c1", direction: "positive", claim: "Visible positive claim about SNDK." }),
      findingRecord({ claim_id: "c2", direction: "unknown", claim: "Hidden unknown claim about SNDK." }),
    ]);
    renderPage();
    await waitFor(() => expect(screen.getByText(/visible positive claim/i)).toBeInTheDocument());
    expect(screen.queryByText(/hidden unknown claim/i)).not.toBeInTheDocument();
    expect(screen.getByText(/1 neutral or unclassified findings are hidden from this view/)).toBeInTheDocument();
  });

  it("hides a mixed-direction finding from the main list", async () => {
    mockAgentOutputs([
      findingRecord({ claim_id: "c1", direction: "positive", claim: "Visible positive claim about SNDK." }),
      findingRecord({ claim_id: "c2", direction: "mixed", claim: "Hidden mixed claim about SNDK." }),
    ]);
    renderPage();
    await waitFor(() => expect(screen.getByText(/visible positive claim/i)).toBeInTheDocument());
    expect(screen.queryByText(/hidden mixed claim/i)).not.toBeInTheDocument();
    expect(screen.getByText(/1 neutral or unclassified findings are hidden from this view/)).toBeInTheDocument();
  });

  it("does not show the hidden-findings note when every finding is directional", async () => {
    mockAgentOutputs([findingRecord({ claim_id: "c1", direction: "positive" })]);
    renderPage();
    await waitFor(() => expect(screen.getByText("positive")).toBeInTheDocument());
    expect(screen.queryByText(/hidden from this view/)).not.toBeInTheDocument();
  });

  it("shows a directional-empty state plus hidden count when only unknown/mixed findings exist", async () => {
    mockAgentOutputs([
      findingRecord({ claim_id: "c1", direction: "unknown" }),
      findingRecord({ claim_id: "c2", direction: "mixed" }),
    ]);
    renderPage();
    await waitFor(() =>
      expect(screen.getByText(/no directional analyst findings are available for this run/i)).toBeInTheDocument()
    );
    expect(screen.getByText(/2 neutral or unclassified findings are hidden from this view/)).toBeInTheDocument();
  });

  it("does not mutate the original agent-outputs API response object while filtering by direction", async () => {
    const response = mockAgentOutputs([
      findingRecord({ claim_id: "c1", direction: "positive" }),
      findingRecord({ claim_id: "c2", direction: "unknown" }),
    ]);
    const originalRecords = [...response.structured_agent_outputs];
    renderPage();
    await waitFor(() => expect(screen.getByText("positive")).toBeInTheDocument());
    expect(response.structured_agent_outputs).toEqual(originalRecords);
    expect(response.structured_agent_outputs).toHaveLength(2);
  });

  it("renders a partial run without failing", async () => {
    vi.spyOn(client, "getResearchRunStatus").mockResolvedValue(
      makeRunRecord({
        selected_analysts: [],
        status: "partial",
        stage: "partial",
        message: "Research run completed partially.",
      })
    );
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
      data_sanity_status: "not_available",
      data_sanity_warning_count: 0,
      data_sanity_critical_count: 0,
      data_sanity_warnings: [],
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
    vi.spyOn(client, "getResearchRunStatus").mockResolvedValue(
      makeRunRecord({ selected_analysts: [], status: "completed", stage: "completed" })
    );
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
      data_sanity_status: "not_available",
      data_sanity_warning_count: 0,
      data_sanity_critical_count: 0,
      data_sanity_warnings: [],
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

  describe("Data Quality panel", () => {
    it("shows the low-emphasis ok message with no warnings", async () => {
      mockAgentOutputs([findingRecord({ direction: "positive" })], { data_sanity_status: "ok" });
      renderPage();
      await waitFor(() =>
        expect(
          screen.getByText(/external market-data cross-check completed with no warnings/i)
        ).toBeInTheDocument()
      );
    });

    it("shows a warning panel with the warning's code/severity/message", async () => {
      mockAgentOutputs([findingRecord({ direction: "positive" })], {
        data_sanity_status: "warning",
        data_sanity_warning_count: 1,
        data_sanity_warnings: [
          {
            code: "REPORTED_PRICE_MISMATCH",
            severity: "warning",
            message: "A price mentioned in a structured analyst claim does not match the external market reference.",
            details: {
              claim_id: "c1",
              reported_date: "2026-07-20",
              reported_price: 108.0,
              external_reference: 100.0,
            },
          },
        ],
      });
      renderPage();
      await waitFor(() => expect(screen.getByText("REPORTED_PRICE_MISMATCH")).toBeInTheDocument());
      expect(screen.getByText(/does not match the external market reference/i)).toBeInTheDocument();
      expect(screen.getByText("warning")).toBeInTheDocument();
    });

    it("shows a critical panel", async () => {
      mockAgentOutputs([findingRecord({ direction: "positive" })], {
        data_sanity_status: "critical",
        data_sanity_critical_count: 1,
        data_sanity_warnings: [
          {
            code: "NO_MARKET_DATA_AVAILABLE",
            severity: "critical",
            message: "Yahoo Finance returned no market data for this ticker and query window.",
            details: {},
          },
        ],
      });
      renderPage();
      await waitFor(() => expect(screen.getByText("NO_MARKET_DATA_AVAILABLE")).toBeInTheDocument());
      expect(screen.getByText("critical")).toBeInTheDocument();
    });

    it("shows the unavailable message", async () => {
      mockAgentOutputs([findingRecord({ direction: "positive" })], { data_sanity_status: "unavailable" });
      renderPage();
      await waitFor(() =>
        expect(screen.getByText(/external market-data cross-check is unavailable for this run/i)).toBeInTheDocument()
      );
    });

    it("shows the disabled message", async () => {
      mockAgentOutputs([findingRecord({ direction: "positive" })], { data_sanity_status: "disabled" });
      renderPage();
      await waitFor(() =>
        expect(screen.getByText(/external market-data cross-check was disabled for this run/i)).toBeInTheDocument()
      );
    });

    it("shows the historical not_available message without treating it as an error", async () => {
      mockAgentOutputs([findingRecord({ direction: "positive" })], { data_sanity_status: "not_available" });
      renderPage();
      await waitFor(() =>
        expect(screen.getByText(/no data-quality artifact is available for this historical run/i)).toBeInTheDocument()
      );
    });

    it("renders an info-severity corporate-action signal without a critical style, even inside a warning-status run", async () => {
      mockAgentOutputs([findingRecord({ direction: "positive" })], {
        data_sanity_status: "warning",
        data_sanity_warning_count: 1,
        data_sanity_warnings: [
          {
            code: "STOCK_SPLIT_IN_ANALYSIS_WINDOW",
            severity: "info",
            message: "Yahoo Finance reports a stock split in the analysis window.",
            details: { date: "2026-06-01", stock_split: 4.0 },
          },
          {
            code: "REPORTED_PRICE_MISMATCH",
            severity: "warning",
            message: "A price mismatch was found.",
            details: { reported_price: 108.0, external_reference: 100.0 },
          },
        ],
      });
      const { container } = renderPage();
      await waitFor(() => expect(screen.getByText("STOCK_SPLIT_IN_ANALYSIS_WINDOW")).toBeInTheDocument());
      const splitItem = screen.getByText("STOCK_SPLIT_IN_ANALYSIS_WINDOW").closest("li");
      expect(splitItem).not.toBeNull();
      expect(splitItem?.className).toContain("data-quality-severity-info");
      expect(splitItem?.className).not.toContain("data-quality-severity-critical");
      // Never claims independent confirmation.
      expect(container.textContent).not.toContain("COMQUTOR independently confirmed");
    });

    it("displays reported/external price and split ratio only for the warnings that carry them", async () => {
      mockAgentOutputs([findingRecord({ direction: "positive" })], {
        data_sanity_status: "warning",
        data_sanity_warning_count: 1,
        data_sanity_warnings: [
          {
            code: "POSSIBLE_PRICE_ADJUSTMENT_CONVENTION_MISMATCH",
            severity: "warning",
            message: "A stock split occurred near this reported price's date.",
            details: { claim_id: "c1", reported_date: "2026-07-20", split_date: "2026-07-20", split_ratio: 4.0 },
          },
        ],
      });
      renderPage();
      await waitFor(() =>
        expect(screen.getByText("POSSIBLE_PRICE_ADJUSTMENT_CONVENTION_MISMATCH")).toBeInTheDocument()
      );
      expect(screen.getByText("Split ratio")).toBeInTheDocument();
      expect(screen.getByText("4")).toBeInTheDocument();
    });

    it("never affects the Analyst findings list rendered alongside it", async () => {
      mockAgentOutputs(
        [findingRecord({ claim_id: "c1", direction: "positive", claim: "Visible positive claim about SNDK." })],
        {
          data_sanity_status: "critical",
          data_sanity_critical_count: 1,
          data_sanity_warnings: [
            { code: "NO_MARKET_DATA_AVAILABLE", severity: "critical", message: "No data.", details: {} },
          ],
        }
      );
      renderPage();
      await waitFor(() => expect(screen.getByText(/visible positive claim/i)).toBeInTheDocument());
      expect(screen.getByText("NO_MARKET_DATA_AVAILABLE")).toBeInTheDocument();
    });
  });
});
