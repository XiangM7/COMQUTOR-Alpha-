import { act, fireEvent, render, screen, waitFor, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { MemoryRouter, Route, Routes } from "react-router-dom";
import { afterEach, describe, expect, it, vi } from "vitest";
import * as client from "../api/client";
import type { ReadinessResponse } from "../api/types";
import { ReadinessProvider } from "../components/ReadinessProvider";
import { clearRunHandoff, peekRunHandoff } from "../utils/transitionHandoff";
import { ResearchPage } from "./ResearchPage";

// Product Demo Hardening Phase 2C (P1-4): the normal /research landing page
// must no longer expose the operator-only Replay-All control. Replay
// functionality itself is not deleted -- see OperatorPage.test.tsx.

const OFFLINE_READINESS: ReadinessResponse = {
  status: "ready",
  database: "ready",
  job_manager: "ready",
  real_execution: "disabled",
  live_semantic_pipeline: "not_applicable",
};

// Renders, then lets the mocked /ready answer land inside act().
async function renderPage() {
  await act(async () => {
    render(
      <MemoryRouter initialEntries={["/research"]}>
        <ReadinessProvider>
          <Routes>
            <Route path="/research" element={<ResearchPage />} />
            <Route path="/runs/:runId/research" element={<p>OPENED_RESEARCH_RUN</p>} />
            <Route path="/runs/:runId/processing" element={<p>OPENED_PROCESSING_RUN</p>} />
          </Routes>
        </ReadinessProvider>
      </MemoryRouter>
    );
  });
}

function mockReadinessAndHistory(readiness: ReadinessResponse = OFFLINE_READINESS) {
  vi.spyOn(client, "getReadiness").mockResolvedValue({ status: 200, result: readiness });
  return vi.spyOn(client, "getResearchHistory").mockResolvedValue({ status: "ok", items: [], next_cursor: null });
}

describe("ResearchPage", () => {
  afterEach(() => {
    vi.restoreAllMocks();
  });

  it("does not render ReplayAllPanel or its 'Reprocess saved outputs' heading", async () => {
    mockReadinessAndHistory();
    await renderPage();
    await waitFor(() => expect(screen.getByText(/research a ticker/i)).toBeInTheDocument());
    expect(screen.queryByText("Reprocess saved outputs")).not.toBeInTheDocument();
    expect(
      screen.queryByRole("button", { name: /re-run all saved outputs with current architecture/i })
    ).not.toBeInTheDocument();
  });

  it("never calls the replay-all endpoint from the normal Research landing page", async () => {
    mockReadinessAndHistory();
    const replaySpy = vi.spyOn(client, "replayAllSavedOutputs");
    await renderPage();
    await waitFor(() => expect(screen.getByText(/research a ticker/i)).toBeInTheDocument());
    expect(replaySpy).not.toHaveBeenCalled();
  });

  it("shows the hero: heading, subtitle, ticker input and Start research", async () => {
    mockReadinessAndHistory();
    await renderPage();
    expect(screen.getByRole("heading", { level: 1, name: "Research a ticker." })).toBeInTheDocument();
    expect(screen.getByText("Every conclusion arrives with the claims and evidence behind it.")).toBeInTheDocument();
    expect(screen.getByLabelText("Ticker")).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "Start research" })).toBeDisabled();
  });

  it("no longer asks for an analysis date or an analyst team", async () => {
    mockReadinessAndHistory();
    await renderPage();
    expect(screen.queryByLabelText(/analysis date/i)).not.toBeInTheDocument();
    expect(screen.queryByRole("checkbox")).not.toBeInTheDocument();
    expect(screen.queryByText(/analysts team/i)).not.toBeInTheDocument();
  });

  it("keeps Recent runs collapsed and does not load history until it is opened", async () => {
    const historySpy = mockReadinessAndHistory();
    await renderPage();
    const button = screen.getByRole("button", { name: /recent runs/i });
    expect(button).toHaveAttribute("aria-expanded", "false");
    // The old always-visible runs table and its heading are gone.
    expect(screen.queryByText("Recent research runs")).not.toBeInTheDocument();
    expect(screen.queryByRole("table")).not.toBeInTheDocument();
    expect(historySpy).not.toHaveBeenCalled();

    fireEvent.click(button);
    expect(button).toHaveAttribute("aria-expanded", "true");
    expect(await screen.findByText("No research runs yet")).toBeInTheDocument();
    expect(historySpy).toHaveBeenCalledTimes(1);
  });

  it("shows the evidence trace at the bottom, labelled as an illustrative example", async () => {
    mockReadinessAndHistory();
    await renderPage();
    const trace = screen.getByRole("region", { name: "How one conclusion is traced." });
    for (const kind of ["Evidence fact", "Alpha", "Conflict"]) {
      expect(within(trace).getByText(kind)).toBeInTheDocument();
    }
    expect(within(trace).getByText(/Claim, from the News analyst/)).toBeInTheDocument();
    expect(within(trace).getByText(/illustrative example/i)).toBeInTheDocument();
  });
});

describe("ResearchPage -- starting research", () => {
  afterEach(() => {
    vi.restoreAllMocks();
  });

  it("submits the ticker with today's date and the full analyst team, then opens the completed result", async () => {
    const user = userEvent.setup();
    mockReadinessAndHistory();
    const submitSpy = vi.spyOn(client, "submitResearch").mockResolvedValue({
      status: 200,
      result: { run_id: "run-1", ticker: "NVDA", status: "completed", cache_disposition: "reused_completed" },
    });
    await renderPage();

    await user.type(screen.getByLabelText("Ticker"), "nvda");
    await user.click(screen.getByRole("button", { name: "Start research" }));

    await waitFor(() => expect(submitSpy).toHaveBeenCalledTimes(1));
    expect(submitSpy.mock.calls[0]?.[0]).toEqual({
      ticker: "NVDA",
      analysis_date: expect.stringMatching(/^\d{4}-\d{2}-\d{2}$/),
      selected_analysts: ["market", "sentiment", "news", "fundamentals"],
    });
    expect(await screen.findByText("OPENED_RESEARCH_RUN")).toBeInTheDocument();
  });

  it("opens Processing for a run that is still in progress", async () => {
    const user = userEvent.setup();
    mockReadinessAndHistory();
    vi.spyOn(client, "submitResearch").mockResolvedValue({
      status: 202,
      result: { run_id: "run-2", ticker: "AMD", status: "queued", cache_disposition: "created" },
    });
    await renderPage();

    await user.type(screen.getByLabelText("Ticker"), "AMD");
    await user.click(screen.getByRole("button", { name: "Start research" }));

    expect(await screen.findByText("OPENED_PROCESSING_RUN")).toBeInTheDocument();
  });

  it("shows a safe message and stays on the page when the server rejects the submission", async () => {
    const user = userEvent.setup();
    mockReadinessAndHistory();
    vi.spyOn(client, "submitResearch").mockResolvedValue({
      status: 200,
      result: { run_id: null, ticker: "ZZZZ", status: "failed", error_code: "invalid_ticker", message: "Unknown ticker." },
    });
    await renderPage();

    await user.type(screen.getByLabelText("Ticker"), "ZZZZ");
    await user.click(screen.getByRole("button", { name: "Start research" }));

    expect(await screen.findByRole("alert")).toBeInTheDocument();
    expect(screen.queryByText("OPENED_RESEARCH_RUN")).not.toBeInTheDocument();
    expect(screen.queryByText("OPENED_PROCESSING_RUN")).not.toBeInTheDocument();
  });
});

describe("ResearchPage -- live-research readiness guard", () => {
  afterEach(() => {
    vi.restoreAllMocks();
  });

  it("disables Start research and explains why when the live semantic pipeline is not ready", async () => {
    const user = userEvent.setup();
    mockReadinessAndHistory({
      status: "ready",
      database: "ready",
      job_manager: "ready",
      real_execution: "configured",
      live_semantic_pipeline: "not_ready",
    });
    const submitSpy = vi.spyOn(client, "submitResearch");
    await renderPage();

    expect(await screen.findByText(/live semantic pipeline not ready/i)).toBeInTheDocument();
    await user.type(screen.getByLabelText("Ticker"), "NVDA");
    expect(screen.getByRole("button", { name: "Start research" })).toBeDisabled();
    await user.type(screen.getByLabelText("Ticker"), "{Enter}");
    expect(submitSpy).not.toHaveBeenCalled();
  });

  it("does not block while readiness is still loading", async () => {
    const user = userEvent.setup();
    vi.spyOn(client, "getReadiness").mockReturnValue(new Promise(() => undefined));
    vi.spyOn(client, "getResearchHistory").mockResolvedValue({ status: "ok", items: [], next_cursor: null });
    await renderPage();

    await user.type(screen.getByLabelText("Ticker"), "NVDA");
    expect(screen.getByRole("button", { name: "Start research" })).toBeEnabled();
  });

  it("keeps the form usable and shows the full error when /ready cannot be reached", async () => {
    const user = userEvent.setup();
    vi.spyOn(client, "getReadiness").mockRejectedValue(new Error("network down"));
    vi.spyOn(client, "getResearchHistory").mockResolvedValue({ status: "ok", items: [], next_cursor: null });
    await renderPage();

    expect(await screen.findByRole("alert")).toHaveTextContent(/could not reach the comqutor api/i);
    await user.type(screen.getByLabelText("Ticker"), "NVDA");
    expect(screen.getByRole("button", { name: "Start research" })).toBeEnabled();
  });
});

describe("ResearchPage -- leaving for the Processing page", () => {
  const originalAnimate = Element.prototype.animate;

  afterEach(() => {
    Element.prototype.animate = originalAnimate;
    vi.restoreAllMocks();
    vi.useRealTimers();
    clearRunHandoff();
  });

  it("fades the hero out and shows Starting… from the click until the page is left", async () => {
    const user = userEvent.setup();
    mockReadinessAndHistory();
    let answer!: (value: Awaited<ReturnType<typeof client.submitResearch>>) => void;
    vi.spyOn(client, "submitResearch").mockReturnValue(
      new Promise((resolve) => {
        answer = resolve;
      })
    );
    await renderPage();

    await user.type(screen.getByLabelText("Ticker"), "amd");
    await user.click(screen.getByRole("button", { name: "Start research" }));

    expect(await screen.findByRole("button", { name: "Starting…" })).toBeDisabled();
    expect(document.querySelector(".research-page")).toHaveClass("research-page-leaving");
    expect(screen.getByRole("button", { name: /recent runs/i })).toBeDisabled();
    expect(document.querySelector('[data-transition="ticker"]')).toHaveTextContent("AMD");

    answer({ status: 202, result: { run_id: "run-2", ticker: "AMD", status: "queued", cache_disposition: "created" } });
    expect(await screen.findByText("OPENED_PROCESSING_RUN")).toBeInTheDocument();
  });

  it("hands the Processing page what was just submitted", async () => {
    const user = userEvent.setup();
    mockReadinessAndHistory();
    vi.spyOn(client, "submitResearch").mockResolvedValue({
      status: 202,
      result: { run_id: "run-2", ticker: "AMD", status: "queued", cache_disposition: "created" },
    });
    await renderPage();

    await user.type(screen.getByLabelText("Ticker"), "amd");
    await user.click(screen.getByRole("button", { name: "Start research" }));
    await screen.findByText("OPENED_PROCESSING_RUN");

    expect(peekRunHandoff("run-2")).toMatchObject({
      runId: "run-2",
      ticker: "AMD",
      analysisDate: expect.stringMatching(/^\d{4}-\d{2}-\d{2}$/),
      selectedAnalysts: ["market", "sentiment", "news", "fundamentals"],
      // Nothing can be animated here (no Web Animations API), so no start
      // positions are handed over.
      geometry: null,
    });
  });

  it("hands over nothing for a finished run that opens straight on its results", async () => {
    const user = userEvent.setup();
    mockReadinessAndHistory();
    vi.spyOn(client, "submitResearch").mockResolvedValue({
      status: 200,
      result: { run_id: "run-1", ticker: "NVDA", status: "completed", cache_disposition: "reused_completed" },
    });
    await renderPage();

    await user.type(screen.getByLabelText("Ticker"), "nvda");
    await user.click(screen.getByRole("button", { name: "Start research" }));

    expect(await screen.findByText("OPENED_RESEARCH_RUN")).toBeInTheDocument();
    expect(peekRunHandoff("run-1")).toBeNull();
  });

  it("brings the form back, with what was typed, when starting fails", async () => {
    const user = userEvent.setup();
    mockReadinessAndHistory();
    vi.spyOn(client, "submitResearch").mockResolvedValue({
      status: 200,
      result: { run_id: null, ticker: "ZZZZ", status: "failed", error_code: "invalid_ticker", message: "Unknown ticker." },
    });
    await renderPage();

    await user.type(screen.getByLabelText("Ticker"), "zzzz");
    await user.click(screen.getByRole("button", { name: "Start research" }));

    expect(await screen.findByRole("alert")).toBeInTheDocument();
    expect(document.querySelector(".research-page")).not.toHaveClass("research-page-leaving");
    expect(screen.getByLabelText("Ticker")).toHaveValue("zzzz");
    expect(screen.getByRole("button", { name: "Start research" })).toBeEnabled();
    expect(screen.getByRole("button", { name: /recent runs/i })).toBeEnabled();
  });

  it("brings the form back when the request itself fails", async () => {
    const user = userEvent.setup();
    mockReadinessAndHistory();
    vi.spyOn(client, "submitResearch").mockRejectedValue(new Error("network down"));
    await renderPage();

    await user.type(screen.getByLabelText("Ticker"), "nvda");
    await user.click(screen.getByRole("button", { name: "Start research" }));

    expect(await screen.findByText(/could not reach the comqutor api/i)).toBeInTheDocument();
    expect(screen.getByLabelText("Ticker")).toHaveValue("nvda");
    expect(document.querySelector(".research-page")).not.toHaveClass("research-page-leaving");
  });

  it("lets the fade finish before leaving, however fast the server answers", async () => {
    Element.prototype.animate = vi.fn(() => ({}) as Animation) as unknown as typeof Element.prototype.animate;
    vi.useFakeTimers({ shouldAdvanceTime: true });
    const user = userEvent.setup({ advanceTimers: vi.advanceTimersByTime });
    mockReadinessAndHistory();
    vi.spyOn(client, "submitResearch").mockResolvedValue({
      status: 202,
      result: { run_id: "run-2", ticker: "AMD", status: "queued", cache_disposition: "created" },
    });
    await renderPage();

    await user.type(screen.getByLabelText("Ticker"), "amd");
    await user.click(screen.getByRole("button", { name: "Start research" }));
    await act(async () => {
      await vi.advanceTimersByTimeAsync(100);
    });
    expect(screen.queryByText("OPENED_PROCESSING_RUN")).toBeNull();
    expect(screen.getByRole("button", { name: "Starting…" })).toBeInTheDocument();

    await act(async () => {
      await vi.advanceTimersByTimeAsync(400);
    });
    expect(screen.getByText("OPENED_PROCESSING_RUN")).toBeInTheDocument();
  });
});
