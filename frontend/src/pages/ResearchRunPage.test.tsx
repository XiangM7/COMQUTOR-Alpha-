import { render, screen, waitFor, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { MemoryRouter, Route, Routes } from "react-router-dom";
import { afterEach, describe, expect, it, vi } from "vitest";
import * as client from "../api/client";
import type {
  AgentOutputsResponse,
  CanonicalResearchResponse,
  StructuredAgentOutputRecord,
  UnclassifiedFinding,
} from "../api/types";
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
        | "data_sanity_status"
        | "data_sanity_warning_count"
        | "data_sanity_critical_count"
        | "data_sanity_warnings"
        | "data_sanity_numeric_semantics"
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

  it("splits findings into independent Positive and Negative panels", async () => {
    mockAgentOutputs([
      findingRecord({ claim_id: "c1", agent: "market_agent", direction: "positive", claim: "Positive claim about SNDK." }),
      findingRecord({ claim_id: "c2", agent: "market_agent", direction: "negative", claim: "Negative claim about SNDK." }),
    ]);

    renderPage();

    await waitFor(() => expect(screen.getByText("Positive findings")).toBeInTheDocument());
    expect(screen.getByText("Negative findings")).toBeInTheDocument();
    expect(screen.getByText(/positive claim about sndk/i)).toBeInTheDocument();
    expect(screen.getByText(/negative claim about sndk/i)).toBeInTheDocument();
  });

  it("never renders a per-card Direction field -- direction is expressed once by the panel heading", async () => {
    mockAgentOutputs([
      findingRecord({ claim_id: "c1", agent: "market_agent", direction: "negative" }),
    ]);

    const { container } = renderPage();

    await waitFor(() => expect(screen.getByText("market_agent")).toBeInTheDocument());
    expect(screen.getByText("Agent")).toBeInTheDocument();
    expect(screen.queryByText("Direction")).not.toBeInTheDocument();
    expect(container.textContent).not.toContain("Direction");
    // Evidence identical to the claim is not rendered a second time.
    expect(screen.getAllByText(/From a May 1st open/)).toHaveLength(1);
  });

  it("shows Agent, claim, and confidence on a finding card", async () => {
    mockAgentOutputs([
      findingRecord({ claim_id: "c1", agent: "market_agent", direction: "positive", confidence: 0.85 }),
    ]);
    renderPage();
    await waitFor(() => expect(screen.getByText("market_agent")).toBeInTheDocument());
    expect(screen.getByText(/From a May 1st open/)).toBeInTheDocument();
    expect(screen.getByText(/Confidence 85%/)).toBeInTheDocument();
  });

  it("hides an unknown-direction finding from both directional panels", async () => {
    mockAgentOutputs([
      findingRecord({ claim_id: "c1", direction: "positive", claim: "Visible positive claim about SNDK." }),
      findingRecord({ claim_id: "c2", direction: "unknown", claim: "Hidden unknown claim about SNDK." }),
    ]);
    renderPage();
    await waitFor(() => expect(screen.getByText(/visible positive claim/i)).toBeInTheDocument());
    expect(screen.queryByText(/hidden unknown claim/i)).not.toBeInTheDocument();
    // Sprint 3, Track A3: which findings are "unclassified" (and why) is now
    // computed backend-side (comqutor_alpha/api/unclassified_findings.py),
    // never re-derived here from the claim's own `direction`. This mocked
    // getResearchRun response predates that field entirely, so the panel
    // must show the honest historical-unavailable state, never a fabricated
    // "0 unclassified findings" or a frontend-guessed direction-based count.
    expect(
      screen.getByText(/unclassified finding audit is not available for this historical run/i)
    ).toBeInTheDocument();
  });

  it("hides a mixed-direction finding from both directional panels", async () => {
    mockAgentOutputs([
      findingRecord({ claim_id: "c1", direction: "positive", claim: "Visible positive claim about SNDK." }),
      findingRecord({ claim_id: "c2", direction: "mixed", claim: "Hidden mixed claim about SNDK." }),
    ]);
    renderPage();
    await waitFor(() => expect(screen.getByText(/visible positive claim/i)).toBeInTheDocument());
    expect(screen.queryByText(/hidden mixed claim/i)).not.toBeInTheDocument();
    expect(
      screen.getByText(/unclassified finding audit is not available for this historical run/i)
    ).toBeInTheDocument();
  });

  it("does not show the neutral/unclassified findings entry when every finding is directional", async () => {
    mockAgentOutputs([findingRecord({ claim_id: "c1", direction: "positive" })]);
    renderPage();
    await waitFor(() => expect(screen.getByText("Positive findings")).toBeInTheDocument());
    expect(screen.queryByText(/Neutral and unclassified findings/)).not.toBeInTheDocument();
  });

  it("shows an independent empty state for each directional panel when only unknown/mixed findings exist", async () => {
    mockAgentOutputs([
      findingRecord({ claim_id: "c1", direction: "unknown" }),
      findingRecord({ claim_id: "c2", direction: "mixed" }),
    ]);
    renderPage();
    await waitFor(() =>
      expect(screen.getByText(/no eligible positive findings were identified/i)).toBeInTheDocument()
    );
    expect(screen.getByText(/no eligible negative findings were identified/i)).toBeInTheDocument();
    expect(
      screen.getByText(/unclassified finding audit is not available for this historical run/i)
    ).toBeInTheDocument();
  });

  it("does not mutate the original agent-outputs API response object while filtering by direction", async () => {
    const response = mockAgentOutputs([
      findingRecord({ claim_id: "c1", direction: "positive" }),
      findingRecord({ claim_id: "c2", direction: "unknown" }),
    ]);
    const originalRecords = [...response.structured_agent_outputs];
    renderPage();
    await waitFor(() => expect(screen.getByText("Positive findings")).toBeInTheDocument());
    expect(response.structured_agent_outputs).toEqual(originalRecords);
    expect(response.structured_agent_outputs).toHaveLength(2);
  });

  describe("More/Less expand and collapse", () => {
    it("shows only the top-ranked (highest confidence) finding by default", async () => {
      mockAgentOutputs([
        findingRecord({ claim_id: "c1", direction: "positive", claim: "Lower confidence claim.", confidence: 0.4 }),
        findingRecord({ claim_id: "c2", direction: "positive", claim: "Highest confidence claim.", confidence: 0.9 }),
      ]);
      renderPage();
      await waitFor(() => expect(screen.getByText(/highest confidence claim/i)).toBeInTheDocument());
      expect(screen.queryByText(/lower confidence claim/i)).not.toBeInTheDocument();
      expect(screen.getByText("More (1)")).toBeInTheDocument();
    });

    it("expands to show every eligible finding (up to 20) when More is clicked", async () => {
      const user = userEvent.setup();
      mockAgentOutputs([
        findingRecord({ claim_id: "c1", direction: "positive", claim: "Highest confidence claim.", confidence: 0.9 }),
        findingRecord({ claim_id: "c2", direction: "positive", claim: "Lower confidence claim.", confidence: 0.4 }),
      ]);
      renderPage();
      await waitFor(() => expect(screen.getByText("More (1)")).toBeInTheDocument());
      await user.click(screen.getByText("More (1)"));
      expect(screen.getByText(/lower confidence claim/i)).toBeInTheDocument();
      expect(screen.getByText("Less")).toBeInTheDocument();
    });

    it("caps a direction at 20 displayed findings even when more are eligible", async () => {
      const user = userEvent.setup();
      const records = Array.from({ length: 25 }, (_, i) =>
        findingRecord({
          claim_id: `c${i}`,
          direction: "positive",
          claim: `Positive claim number ${i}.`,
          confidence: 0.5,
          claim_index: i,
        })
      );
      mockAgentOutputs(records);
      renderPage();
      await waitFor(() => expect(screen.getByText("More (19)")).toBeInTheDocument());
      await user.click(screen.getByText("More (19)"));
      expect(screen.getAllByText(/positive claim number/i)).toHaveLength(20);
    });

    it("collapses back to the first finding when Less is clicked", async () => {
      const user = userEvent.setup();
      mockAgentOutputs([
        findingRecord({ claim_id: "c1", direction: "positive", claim: "Highest confidence claim.", confidence: 0.9 }),
        findingRecord({ claim_id: "c2", direction: "positive", claim: "Lower confidence claim.", confidence: 0.4 }),
      ]);
      renderPage();
      await waitFor(() => expect(screen.getByText("More (1)")).toBeInTheDocument());
      await user.click(screen.getByText("More (1)"));
      await waitFor(() => expect(screen.getByText("Less")).toBeInTheDocument());
      await user.click(screen.getByText("Less"));
      expect(screen.queryByText(/lower confidence claim/i)).not.toBeInTheDocument();
      expect(screen.getByText("More (1)")).toBeInTheDocument();
    });

    it("never shows More when only one eligible finding exists", async () => {
      mockAgentOutputs([findingRecord({ claim_id: "c1", direction: "positive" })]);
      renderPage();
      await waitFor(() => expect(screen.getByText("Positive findings")).toBeInTheDocument());
      expect(screen.queryByText(/^More/)).not.toBeInTheDocument();
    });

    it("expands and collapses Positive and Negative panels independently", async () => {
      const user = userEvent.setup();
      mockAgentOutputs([
        findingRecord({ claim_id: "p1", direction: "positive", claim: "Top positive claim.", confidence: 0.9 }),
        findingRecord({ claim_id: "p2", direction: "positive", claim: "Second positive claim.", confidence: 0.4 }),
        findingRecord({ claim_id: "n1", direction: "negative", claim: "Top negative claim.", confidence: 0.9 }),
        findingRecord({ claim_id: "n2", direction: "negative", claim: "Second negative claim.", confidence: 0.4 }),
      ]);
      renderPage();
      await waitFor(() => expect(screen.getAllByText("More (1)")).toHaveLength(2));
      const positivePanel = screen.getByText("Positive findings").closest("section") as HTMLElement;
      const moreButtonInPositive = within(positivePanel).getByText("More (1)");
      await user.click(moreButtonInPositive);
      expect(screen.getByText(/second positive claim/i)).toBeInTheDocument();
      expect(screen.queryByText(/second negative claim/i)).not.toBeInTheDocument();
      const negativePanel = screen.getByText("Negative findings").closest("section") as HTMLElement;
      expect(within(negativePanel).getByText("More (1)")).toBeInTheDocument();
    });
  });

  it("keeps sorting stable and deterministic when confidence ties (evidence, then claim_index, then claim_id)", async () => {
    mockAgentOutputs([
      findingRecord({
        claim_id: "z-claim",
        direction: "positive",
        claim: "Tied confidence claim with no separate evidence.",
        evidence: "Tied confidence claim with no separate evidence.",
        confidence: 0.5,
        claim_index: 5,
      }),
      findingRecord({
        claim_id: "a-claim",
        direction: "positive",
        claim: "Tied confidence claim with distinct evidence.",
        evidence: "This is separate supporting evidence text.",
        confidence: 0.5,
        claim_index: 3,
      }),
    ]);
    renderPage();
    // The tied-confidence record with non-empty distinct evidence outranks
    // the one whose evidence is identical to its own claim text.
    await waitFor(() => expect(screen.getByText(/tied confidence claim with distinct evidence/i)).toBeInTheDocument());
    expect(screen.queryByText(/tied confidence claim with no separate evidence/i)).not.toBeInTheDocument();
  });

  // Product Demo Hardening Phase 3B (F1): a long, colon-delimited claim_id
  // (the real shape: "<run_id>:<agent>:<source>:claim:<n>") must render
  // completely -- never truncated or ellipsized -- and must live inside the
  // .analyst-output-card container that carries the overflow-wrap fix
  // (see styles.layout.test.ts for the actual CSS rule assertion; jsdom
  // does not apply styles.css, so real overflow cannot be verified here).
  it("renders a long claim_id completely, never truncated, inside the wrap-protected finding card", async () => {
    const longClaimId =
      "57d7b4c4-dbb9-4134-b962-ee2a873941cc:fundamental_agent:fundamentals_report:claim:122";
    mockAgentOutputs([
      findingRecord({ claim_id: longClaimId, direction: "positive", claim: "Some claim text." }),
    ]);
    renderPage();
    const codeEl = await waitFor(() => screen.getByText(longClaimId));
    expect(codeEl.textContent).toBe(longClaimId);
    expect(codeEl.textContent).not.toContain("…");
    expect(codeEl.textContent).not.toContain("...");
    expect(codeEl.closest(".analyst-output-card")).not.toBeNull();
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

    it("shows a low-risk numeric-semantics summary for skipped technical-indicator candidates, never as a warning", async () => {
      mockAgentOutputs([findingRecord({ direction: "positive" })], {
        data_sanity_status: "ok",
        data_sanity_numeric_semantics: {
          evaluated_count: 3,
          daily_range_eligible_count: 2,
          skipped_by_role_count: 1,
          semantic_role_counts: { MOVING_AVERAGE: 1, OBSERVED_MARKET_PRICE: 2 },
        },
      });
      renderPage();
      await waitFor(() =>
        expect(
          screen.getByText(/1 numeric candidate\(s\) skipped as non-market-price/)
        ).toBeInTheDocument()
      );
      // Never rendered inside/as a warning-severity item.
      expect(document.querySelector(".data-quality-severity-warning")).not.toBeInTheDocument();
      expect(document.querySelector(".data-quality-severity-critical")).not.toBeInTheDocument();
    });

    it("omits the numeric-semantics summary when nothing was skipped", async () => {
      mockAgentOutputs([findingRecord({ direction: "positive" })], {
        data_sanity_status: "ok",
        data_sanity_numeric_semantics: {
          evaluated_count: 2,
          daily_range_eligible_count: 2,
          skipped_by_role_count: 0,
          semantic_role_counts: { OBSERVED_MARKET_PRICE: 2 },
        },
      });
      renderPage();
      await waitFor(() =>
        expect(
          screen.getByText(/external market-data cross-check completed with no warnings/i)
        ).toBeInTheDocument()
      );
      expect(screen.queryByText(/skipped as non-market-price/)).not.toBeInTheDocument();
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

  // Sprint 3 (Unclassified Findings Control), Track A3.
  describe("Unclassified findings panel", () => {
    function unclassifiedFinding(overrides: Partial<UnclassifiedFinding>): UnclassifiedFinding {
      return {
        run_id: "run-1",
        ticker: "SNDK",
        claim_id: "u1",
        claim: "Analysis Date: 2026-08-11 | Exchange: NMS | Sector: Technology.",
        evidence: "Analysis Date: 2026-08-11 | Exchange: NMS | Sector: Technology.",
        agent: "market_agent",
        confidence: 0.4,
        matched_alpha: null,
        secondary_alphas: [],
        direction: "unknown",
        reason: "no_alpha_match",
        reason_codes: ["no_alpha_match"],
        diagnostic_reason_codes: [],
        ticker_specific: false,
        duplicate_group_id: null,
        evidence_fact_group_id: null,
        representative_claim_id: null,
        source_refs: [],
        source_agent_output_id: "o1",
        claim_index: 0,
        display_rank: 1,
        ...overrides,
      };
    }

    function mockResearch(overrides: Partial<CanonicalResearchResponse>) {
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
        agent_output_count: 0,
        structured_output_count: 0,
        structure_graph_status: "ready",
        dominant_alphas: [],
        main_conflict: null,
        conflict_status: "ready",
        summary: "Summary.",
        data_sanity_status: "not_available",
        data_sanity_warning_count: 0,
        data_sanity_critical_count: 0,
        data_sanity_warnings: [],
        ...overrides,
      });
      vi.spyOn(client, "getAgentOutputs").mockResolvedValue({
        run_id: "run-1",
        ticker: "SNDK",
        status: "ok",
        schema_version: "week1a.structured_agent_outputs.v2",
        count: 0,
        structured_agent_outputs: [],
      });
    }

    it("shows friendly reason labels and an accurate Showing X of Y count", async () => {
      mockResearch({
        unclassified_findings_status: "ready",
        unclassified_findings_total_count: 2,
        unclassified_findings_reason_counts: { no_alpha_match: 1, no_ticker_specific_evidence: 1 },
        unclassified_findings_download_available: true,
        unclassified_findings_top20: [
          unclassifiedFinding({ claim_id: "u1", reason: "no_alpha_match", display_rank: 1 }),
          unclassifiedFinding({
            claim_id: "u2",
            reason: "no_ticker_specific_evidence",
            reason_codes: ["no_ticker_specific_evidence"],
            matched_alpha: "A601",
            ticker_specific: false,
            claim: "Momentum is broadly positive across the sector.",
            display_rank: 2,
          }),
        ],
      });
      renderPage();
      await waitFor(() => expect(screen.getByText("Unclassified findings (2)")).toBeInTheDocument());
      expect(screen.getByText("Showing 2 of 2")).toBeInTheDocument();
      // Friendly text, never the raw snake_case reason code, in the card body.
      // (u1 has no matched_alpha, so both its Reason and Alpha match rows
      // legitimately read "No canonical Alpha match" -- two distinct cells.)
      expect(screen.getAllByText("No canonical Alpha match").length).toBeGreaterThan(0);
      expect(screen.getByText("No ticker-specific Evidence")).toBeInTheDocument();
      expect(screen.queryByText("no_alpha_match")).not.toBeInTheDocument();
      expect(screen.queryByText("no_ticker_specific_evidence")).not.toBeInTheDocument();
      // A mention/no-match finding is never worded as supporting its Alpha.
      expect(screen.getByText("A601")).toBeInTheDocument();
    });

    it("shows a Download full audit link pointing at the existing artifact route", async () => {
      mockResearch({
        unclassified_findings_status: "ready",
        unclassified_findings_total_count: 1,
        unclassified_findings_reason_counts: { no_alpha_match: 1 },
        unclassified_findings_download_available: true,
        unclassified_findings_top20: [unclassifiedFinding({ claim_id: "u1" })],
      });
      renderPage();
      await waitFor(() => expect(screen.getByText(/download full audit/i)).toBeInTheDocument());
      const link = screen.getByText(/download full audit \(1\)/i).closest("a");
      expect(link).not.toBeNull();
      expect(link?.getAttribute("href")).toContain("/api/research/run-1/artifacts/unclassified_findings.json");
      expect(link?.getAttribute("download")).toBe("run-1_unclassified_findings_audit.json");
    });

    it("omits the Download full audit link when the backend reports it unavailable", async () => {
      mockResearch({
        unclassified_findings_status: "ready",
        unclassified_findings_total_count: 1,
        unclassified_findings_reason_counts: { no_alpha_match: 1 },
        unclassified_findings_download_available: false,
        unclassified_findings_top20: [unclassifiedFinding({ claim_id: "u1" })],
      });
      renderPage();
      await waitFor(() => expect(screen.getByText("Unclassified findings (1)")).toBeInTheDocument());
      expect(screen.queryByText(/download full audit/i)).not.toBeInTheDocument();
    });

    it("shows a Representative finding note for a non-representative duplicate", async () => {
      mockResearch({
        unclassified_findings_status: "ready",
        unclassified_findings_total_count: 1,
        unclassified_findings_reason_counts: { duplicate_supporting_text: 1 },
        unclassified_findings_download_available: true,
        unclassified_findings_top20: [
          unclassifiedFinding({
            claim_id: "u2",
            matched_alpha: "A304",
            reason: "duplicate_supporting_text",
            reason_codes: ["duplicate_supporting_text"],
            evidence_fact_group_id: "group-1",
            representative_claim_id: "u1",
          }),
        ],
      });
      renderPage();
      await waitFor(() => expect(screen.getByText("Duplicate supporting text")).toBeInTheDocument());
      expect(screen.getByText("Representative finding:")).toBeInTheDocument();
      expect(screen.getByText("u1")).toBeInTheDocument();
    });

    it("shows an honest empty state, never a fake Showing 0 of 0, when the run genuinely has zero unclassified findings", async () => {
      mockResearch({
        unclassified_findings_status: "ready",
        unclassified_findings_total_count: 0,
        unclassified_findings_reason_counts: {},
        unclassified_findings_download_available: false,
        unclassified_findings_top20: [],
      });
      renderPage();
      await waitFor(() => expect(screen.getByText("No unclassified findings for this run.")).toBeInTheDocument());
      expect(screen.queryByText(/Showing 0 of 0/)).not.toBeInTheDocument();
    });

    it("shows the historical-unavailable message, never a fabricated zero, when the backend explicitly reports unavailable", async () => {
      mockResearch({ unclassified_findings_status: "unavailable" });
      renderPage();
      await waitFor(() =>
        expect(
          screen.getByText(/unclassified finding audit is not available for this historical run/i)
        ).toBeInTheDocument()
      );
      expect(screen.queryByText(/Showing \d+ of \d+/)).not.toBeInTheDocument();
    });
  });

  describe("Alpha Memory panel (Implementation Step 4B)", () => {
    function mockResearchWithMemory(alphaMemory: CanonicalResearchResponse["alpha_memory"]) {
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
        ticker: "NVDA",
        status: "completed",
        artifacts: BASE_ARTIFACTS,
        agent_output_count: 0,
        structured_output_count: 0,
        structure_graph_status: "ready",
        dominant_alphas: [],
        main_conflict: null,
        conflict_status: "ready",
        summary: "Summary.",
        data_sanity_status: "not_available",
        data_sanity_warning_count: 0,
        data_sanity_critical_count: 0,
        data_sanity_warnings: [],
        alpha_memory: alphaMemory,
      });
      vi.spyOn(client, "getAgentOutputs").mockResolvedValue({
        run_id: "run-1",
        ticker: "NVDA",
        status: "ok",
        schema_version: "week1a.structured_agent_outputs.v2",
        count: 0,
        structured_agent_outputs: [],
      });
    }

    const RECURRING_STRUCTURE = {
      phi_id: "abc123def456",
      ticker: "NVDA",
      alpha_id: "A101",
      source: "ai_capex",
      edge_type: "causal",
      target: "gpu_demand",
      is_recurring: true,
      has_prior_observation: true,
      prior_observation_count: 5,
      prior_run_ids: ["run-a", "run-b", "run-c", "run-d", "run-e"],
      first_seen: "2026-08-01T00:00:00Z",
      last_seen_prior: "2026-08-20T00:00:00Z",
      current_seen_at: "2026-09-05T00:00:00Z",
    };

    const FIRST_SEEN_STRUCTURE = {
      phi_id: "fedcba987654",
      ticker: "NVDA",
      alpha_id: "A101",
      source: "rate_cut_cycle",
      edge_type: "conflicting",
      target: "valuation_risk",
      is_recurring: false,
      has_prior_observation: false,
      prior_observation_count: 0,
      prior_run_ids: [],
      first_seen: "2026-09-05T00:00:00Z",
      last_seen_prior: null,
      current_seen_at: "2026-09-05T00:00:00Z",
    };

    it("renders the Alpha Memory panel with Shadow badge and modulation Off when data exists", async () => {
      mockResearchWithMemory({
        mode: "shadow",
        activation_modulation_applied: false,
        identity_model: "atomic_edge_phi",
        identity_version: "alpha_memory.phi_edge.v1",
        phi_structures: [RECURRING_STRUCTURE, FIRST_SEEN_STRUCTURE],
        alpha_memory_summary: [
          {
            alpha_id: "A101",
            current_phi_count: 5,
            first_seen_phi_count: 3,
            recurring_phi_count: 2,
            recurrence_ratio: 0.4,
            prior_observation_total: 7,
          },
        ],
        aggregate_fingerprints: [],
        instability_signals: { alpha_attribution_variance: [], edge_type_variance: [] },
      });
      renderPage();

      await waitFor(() => expect(screen.getByText("Alpha Memory")).toBeInTheDocument());
      // Product Demo Hardening Phase 2D: SHADOW/mode/activation_modulation_applied
      // are no longer prominent by default -- the default copy states plainly
      // that memory does not alter the current activation result, and the
      // raw values are preserved verbatim under Technical details.
      expect(screen.queryByText("SHADOW")).not.toBeInTheDocument();
      expect(screen.getByText("Mode").closest("div")?.textContent).toContain("shadow");
      expect(
        screen.getByText("Historical memory is shown for context and does not alter the current activation result.")
      ).toBeInTheDocument();
    });

    it("renders the recurring and first-seen counts correctly", async () => {
      mockResearchWithMemory({
        mode: "shadow",
        activation_modulation_applied: false,
        identity_model: "atomic_edge_phi",
        identity_version: "alpha_memory.phi_edge.v1",
        phi_structures: [RECURRING_STRUCTURE, FIRST_SEEN_STRUCTURE],
        alpha_memory_summary: [
          {
            alpha_id: "A101",
            current_phi_count: 5,
            first_seen_phi_count: 3,
            recurring_phi_count: 2,
            recurrence_ratio: 0.4,
            prior_observation_total: 7,
          },
        ],
        aggregate_fingerprints: [],
      });
      renderPage();

      await waitFor(() => expect(screen.getByText("Alpha Memory")).toBeInTheDocument());
      const summaryText = screen.getByText(/current structure/).textContent ?? "";
      expect(summaryText).toContain("A101");
      expect(summaryText).toContain("5 current structures");
      expect(summaryText).toContain("2 recurring");
      expect(summaryText).toContain("3 first seen");
      expect(summaryText).toContain("40% recurrence");
    });

    it("never uses bullish/bearish/confidence language anywhere in the panel", async () => {
      mockResearchWithMemory({
        mode: "shadow",
        activation_modulation_applied: false,
        identity_model: "atomic_edge_phi",
        identity_version: "alpha_memory.phi_edge.v1",
        phi_structures: [RECURRING_STRUCTURE],
        alpha_memory_summary: [
          {
            alpha_id: "A101",
            current_phi_count: 1,
            first_seen_phi_count: 0,
            recurring_phi_count: 1,
            recurrence_ratio: 1,
            prior_observation_total: 5,
          },
        ],
        aggregate_fingerprints: [],
      });
      renderPage();
      await waitFor(() => expect(screen.getByText("Alpha Memory")).toBeInTheDocument());

      const panelText = screen.getByText("Alpha Memory").closest("section")?.textContent ?? "";
      for (const forbidden of [
        "bullish",
        "bearish",
        "confirmed thesis",
        "stronger signal",
        "higher confidence",
        "validated alpha",
        "memory boost",
        "memory penalty",
        "invalidated",
        "expired",
        "failed",
      ]) {
        expect(panelText.toLowerCase()).not.toContain(forbidden);
      }
    });

    it("shows the actual source-to-target relation and real prior-observation details when expanded", async () => {
      mockResearchWithMemory({
        mode: "shadow",
        activation_modulation_applied: false,
        identity_model: "atomic_edge_phi",
        identity_version: "alpha_memory.phi_edge.v1",
        phi_structures: [RECURRING_STRUCTURE],
        alpha_memory_summary: [
          {
            alpha_id: "A101",
            current_phi_count: 1,
            first_seen_phi_count: 0,
            recurring_phi_count: 1,
            recurrence_ratio: 1,
            prior_observation_total: 5,
          },
        ],
        aggregate_fingerprints: [],
      });
      renderPage();
      await waitFor(() => expect(screen.getByText(/Recurring structures/)).toBeInTheDocument());

      const user = userEvent.setup();
      await user.click(screen.getByText(/Recurring structures/));

      expect(screen.getByText("ai_capex")).toBeInTheDocument();
      expect(screen.getByText("gpu_demand")).toBeInTheDocument();
      expect(screen.getByText(/5 prior runs/)).toBeInTheDocument();
      expect(screen.getByText("2026-08-01T00:00:00Z")).toBeInTheDocument();
      expect(screen.getByText("2026-08-20T00:00:00Z")).toBeInTheDocument();
      // The raw phi_id is available only inside the (closed-by-default)
      // technical detail, never as the primary visible human-facing label.
      expect(screen.getByText("abc123def456")).not.toBeVisible();
      await user.click(screen.getByText("Technical detail"));
      expect(screen.getByText("abc123def456")).toBeVisible();
    });

    it("renders a first-seen-only Alpha (no recurrence) honestly, without a fake recurring section", async () => {
      mockResearchWithMemory({
        mode: "shadow",
        activation_modulation_applied: false,
        identity_model: "atomic_edge_phi",
        identity_version: "alpha_memory.phi_edge.v1",
        phi_structures: [FIRST_SEEN_STRUCTURE],
        alpha_memory_summary: [
          {
            alpha_id: "A101",
            current_phi_count: 1,
            first_seen_phi_count: 1,
            recurring_phi_count: 0,
            recurrence_ratio: 0,
            prior_observation_total: 0,
          },
        ],
        aggregate_fingerprints: [],
      });
      renderPage();
      await waitFor(() => expect(screen.getByText("Alpha Memory")).toBeInTheDocument());
      expect(screen.getByText("No exact historical recurrence found for this Alpha.")).toBeInTheDocument();
      expect(screen.queryByText(/Recurring structures/)).not.toBeInTheDocument();
    });

    it("renders an honest empty state when there is no current Alpha structure to compare, never fabricated memory", async () => {
      mockResearchWithMemory({
        mode: "shadow",
        activation_modulation_applied: false,
        identity_model: "atomic_edge_phi",
        identity_version: "alpha_memory.phi_edge.v1",
        phi_structures: [],
        alpha_memory_summary: [],
        aggregate_fingerprints: [],
      });
      renderPage();
      await waitFor(() => expect(screen.getByText("Alpha Memory")).toBeInTheDocument());
      expect(
        screen.getByText("No current Alpha structures to compare against history for this run.")
      ).toBeInTheDocument();
    });

    it("renders an MSFT-style zero-recurrence result honestly, never as a failure", async () => {
      mockResearchWithMemory({
        mode: "shadow",
        activation_modulation_applied: false,
        identity_model: "atomic_edge_phi",
        identity_version: "alpha_memory.phi_edge.v1",
        phi_structures: Array.from({ length: 12 }, (_, i) => ({
          ...FIRST_SEEN_STRUCTURE,
          phi_id: `msft-phi-${i}`,
          alpha_id: i < 6 ? "A102" : "A103",
        })),
        alpha_memory_summary: [
          {
            alpha_id: "A102",
            current_phi_count: 6,
            first_seen_phi_count: 6,
            recurring_phi_count: 0,
            recurrence_ratio: 0,
            prior_observation_total: 0,
          },
          {
            alpha_id: "A103",
            current_phi_count: 6,
            first_seen_phi_count: 6,
            recurring_phi_count: 0,
            recurrence_ratio: 0,
            prior_observation_total: 0,
          },
        ],
        aggregate_fingerprints: [],
      });
      renderPage();
      await waitFor(() => expect(screen.getByText("Alpha Memory")).toBeInTheDocument());
      const panelText = screen.getByText("Alpha Memory").closest("section")?.textContent ?? "";
      expect(panelText.toLowerCase()).not.toContain("memory failed");
      expect(panelText.toLowerCase()).not.toContain("failed");
      expect(screen.getAllByText("No exact historical recurrence found for this Alpha.")).toHaveLength(2);
    });

    it("never fabricates a timestamp when first_seen/last_seen_prior are unavailable", async () => {
      mockResearchWithMemory({
        mode: "shadow",
        activation_modulation_applied: false,
        identity_model: "atomic_edge_phi",
        identity_version: "alpha_memory.phi_edge.v1",
        phi_structures: [
          { ...RECURRING_STRUCTURE, first_seen: null, last_seen_prior: null },
        ],
        alpha_memory_summary: [
          {
            alpha_id: "A101",
            current_phi_count: 1,
            first_seen_phi_count: 0,
            recurring_phi_count: 1,
            recurrence_ratio: 1,
            prior_observation_total: 5,
          },
        ],
        aggregate_fingerprints: [],
      });
      renderPage();
      await waitFor(() => expect(screen.getByText(/Recurring structures/)).toBeInTheDocument());
      const user = userEvent.setup();
      await user.click(screen.getByText(/Recurring structures/));
      expect(screen.getAllByText("Unavailable")).toHaveLength(2);
    });

    it("treats aggregate fingerprint information as secondary only, inside technical detail", async () => {
      mockResearchWithMemory({
        mode: "shadow",
        activation_modulation_applied: false,
        identity_model: "atomic_edge_phi",
        identity_version: "alpha_memory.phi_edge.v1",
        phi_structures: [RECURRING_STRUCTURE],
        alpha_memory_summary: [
          {
            alpha_id: "A101",
            current_phi_count: 1,
            first_seen_phi_count: 0,
            recurring_phi_count: 1,
            recurrence_ratio: 1,
            prior_observation_total: 5,
          },
        ],
        aggregate_fingerprints: [{ aggregate_fingerprint_id: "agg123", alpha_id: "A101" }],
      });
      renderPage();
      await waitFor(() => expect(screen.getByText("Alpha Memory")).toBeInTheDocument());
      const diagnosticText = screen.getByText(/is a secondary diagnostic only/i);
      // Not visible until the secondary-diagnostics detail is expanded.
      expect(diagnosticText).not.toBeVisible();
      const user = userEvent.setup();
      await user.click(screen.getByText("Secondary diagnostics (technical)"));
      expect(diagnosticText).toBeVisible();
    });

    it("does not render the Alpha Memory panel at all for a historical run predating Step 1 (no fabricated section)", async () => {
      mockResearchWithMemory(null);
      renderPage();
      await waitFor(() => expect(screen.getByText("Summary.")).toBeInTheDocument());
      expect(screen.queryByText("Alpha Memory")).not.toBeInTheDocument();
    });

    it("leaves the existing research summary and Unclassified findings panel unchanged when Alpha Memory is present", async () => {
      mockResearchWithMemory({
        mode: "shadow",
        activation_modulation_applied: false,
        identity_model: "atomic_edge_phi",
        identity_version: "alpha_memory.phi_edge.v1",
        phi_structures: [RECURRING_STRUCTURE],
        alpha_memory_summary: [
          {
            alpha_id: "A101",
            current_phi_count: 1,
            first_seen_phi_count: 0,
            recurring_phi_count: 1,
            recurrence_ratio: 1,
            prior_observation_total: 5,
          },
        ],
        aggregate_fingerprints: [],
      });
      renderPage();
      await waitFor(() => expect(screen.getByText("Summary.")).toBeInTheDocument());
      expect(
        screen.getByText(/unclassified finding audit is not available for this historical run/i)
      ).toBeInTheDocument();
      expect(screen.getByText("Alpha Memory")).toBeInTheDocument();
    });

    // Product Demo Hardening Phase 2D, Sections 13/21/30.
    describe("Phase 2D: default-view jargon cleanup", () => {
      function memoryFixture(overrides: Partial<NonNullable<CanonicalResearchResponse["alpha_memory"]>> = {}) {
        return {
          mode: "shadow" as const,
          activation_modulation_applied: false as const,
          identity_model: "atomic_edge_phi",
          identity_version: "alpha_memory.phi_edge.v1",
          phi_structures: [],
          alpha_memory_summary: [],
          aggregate_fingerprints: [],
          ...overrides,
        };
      }

      it("does not show SHADOW as default stakeholder copy", async () => {
        mockResearchWithMemory(memoryFixture());
        renderPage();
        await waitFor(() => expect(screen.getByText("Alpha Memory")).toBeInTheDocument());
        expect(screen.queryByText("SHADOW")).not.toBeInTheDocument();
      });

      it("does not show phi_id in default stakeholder copy", async () => {
        mockResearchWithMemory(
          memoryFixture({
            phi_structures: [RECURRING_STRUCTURE],
            alpha_memory_summary: [
              { alpha_id: "A101", current_phi_count: 1, first_seen_phi_count: 0, recurring_phi_count: 1, recurrence_ratio: 1, prior_observation_total: 5 },
            ],
          })
        );
        renderPage();
        await waitFor(() => expect(screen.getByText(/Recurring structures/)).toBeInTheDocument());
        expect(screen.getByText(RECURRING_STRUCTURE.phi_id)).not.toBeVisible();
      });

      it("does not show activation_modulation_applied raw by default, and states plainly that memory does not alter the current activation result", async () => {
        mockResearchWithMemory(memoryFixture({ activation_modulation_applied: false }));
        renderPage();
        await waitFor(() => expect(screen.getByText("Alpha Memory")).toBeInTheDocument());
        expect(screen.queryByText(/activation_modulation_applied/)).not.toBeInTheDocument();
        expect(
          screen.getByText("Historical memory is shown for context and does not alter the current activation result.")
        ).toBeInTheDocument();
      });

      it("exposes the exact technical mode/modulation values once Technical details is opened", async () => {
        const user = userEvent.setup();
        mockResearchWithMemory(memoryFixture());
        renderPage();
        await waitFor(() => expect(screen.getByText("Alpha Memory")).toBeInTheDocument());
        const [firstSummary] = screen.getAllByText("Technical details");
        await user.click(firstSummary!);
        expect(screen.getByText("Mode").closest("div")?.textContent).toContain("shadow");
        expect(screen.getByText("Activation modulation applied").closest("div")?.textContent).toContain("No");
      });

      it("never implies memory modifies current activation, even in the (currently type-constrained) modulation-applied branch", async () => {
        mockResearchWithMemory(
          memoryFixture({ activation_modulation_applied: true as unknown as false })
        );
        renderPage();
        await waitFor(() => expect(screen.getByText("Alpha Memory")).toBeInTheDocument());
        const panelText = screen.getByText("Alpha Memory").closest("section")?.textContent ?? "";
        expect(panelText).toContain("Historical memory modulation is currently applied to this run's activation.");
        expect(panelText).not.toContain("does not alter the current activation result");
      });
    });
  });
});
