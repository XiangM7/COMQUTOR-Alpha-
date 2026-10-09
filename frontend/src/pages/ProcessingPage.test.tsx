import { act, fireEvent, render, screen, waitFor, within } from "@testing-library/react";
import { MemoryRouter, Route, Routes } from "react-router-dom";
import { afterEach, describe, expect, it, vi } from "vitest";
import * as client from "../api/client";
import { makeRunRecord } from "../tests/factories";
import { peekRunHandoff, setRunHandoff } from "../utils/transitionHandoff";
import { ProcessingPage } from "./ProcessingPage";

function renderPage(runId = "run-1") {
  return render(
    <MemoryRouter initialEntries={[`/runs/${runId}/processing`]}>
      <Routes>
        <Route path="/runs/:runId/processing" element={<ProcessingPage />} />
        <Route path="/runs/:runId/research" element={<p>results page for {runId}</p>} />
        <Route path="/research" element={<p>research form page</p>} />
      </Routes>
    </MemoryRouter>
  );
}

const RUNNING_RECORD = makeRunRecord({
  status: "running",
  stage: "research_pipeline",
  analysis_date: "2026-10-07",
  selected_analysts: ["market", "sentiment", "news", "fundamentals"],
  profile_id: "comqutor_anthropic_medium_sonnet46_v1",
  profile_display_name: "COMQUTOR Anthropic Medium v1",
  progress_percent: 43,
  current_stage: "news_analysis",
  completed_units: 4,
  total_units: 15,
  progress_message: "Running the News Analyst.",
  elapsed_seconds: 98,
  eta_status: "estimating",
  eta_sample_count: 0,
});

const WITH_ETA = makeRunRecord({
  ...RUNNING_RECORD,
  eta_status: "available",
  estimated_remaining_seconds_min: 600,
  estimated_remaining_seconds_max: 960,
  eta_sample_count: 14,
});

/** First poll answers, every later poll never does: the page lives purely on
 * its own clock afterwards, so nothing re-calibrates it. */
function answerOnce(record: ReturnType<typeof makeRunRecord>) {
  return vi
    .spyOn(client, "getResearchRunStatus")
    .mockResolvedValueOnce(record)
    .mockReturnValue(new Promise(() => undefined));
}

describe("ProcessingPage", () => {
  afterEach(() => {
    vi.restoreAllMocks();
    vi.unstubAllEnvs();
    vi.unstubAllGlobals();
    vi.useRealTimers();
  });

  it("renders real backend progress: heading, bar value, percent, caption, elapsed", async () => {
    vi.spyOn(client, "getResearchRunStatus").mockResolvedValue(RUNNING_RECORD);
    renderPage();

    expect(await screen.findByRole("heading", { name: "Analyzing NVDA" })).toBeInTheDocument();
    const bar = screen.getByRole("progressbar", { name: "Research progress" });
    expect(bar).toHaveAttribute("aria-valuemin", "0");
    expect(bar).toHaveAttribute("aria-valuemax", "100");
    expect(bar).toHaveAttribute("aria-valuenow", "43");
    expect(screen.getByText("43%")).toBeInTheDocument();
    expect(screen.getByText(/^Elapsed 1m 3\ds$|^Elapsed 1m 38s$/)).toBeInTheDocument();
    expect(screen.getByText("Running the News Analyst.")).toBeInTheDocument();
  });

  it("states the analysis date and that all four analysts ran", async () => {
    vi.spyOn(client, "getResearchRunStatus").mockResolvedValue(RUNNING_RECORD);
    renderPage();
    expect(await screen.findByText("Analysis date Oct 7, 2026, all four analysts")).toBeInTheDocument();
  });

  it("names a partial analyst selection instead of claiming all four", async () => {
    vi.spyOn(client, "getResearchRunStatus").mockResolvedValue(
      makeRunRecord({ ...RUNNING_RECORD, selected_analysts: ["market", "news"] })
    );
    renderPage();
    expect(await screen.findByText("Analysis date Oct 7, 2026, Market, News analysts")).toBeInTheDocument();
  });

  it("does not show the research profile name", async () => {
    vi.spyOn(client, "getResearchRunStatus").mockResolvedValue(RUNNING_RECORD);
    renderPage();
    await screen.findByRole("heading", { name: "Analyzing NVDA" });
    expect(screen.queryByText(/COMQUTOR Anthropic/)).toBeNull();
    expect(screen.queryByText(/research profile/i)).toBeNull();
  });

  it("marks completed, in-progress, and remaining stages distinctly (not by color alone)", async () => {
    vi.spyOn(client, "getResearchRunStatus").mockResolvedValue(RUNNING_RECORD);
    renderPage();

    const analysts = await screen.findByRole("list", { name: "Analyst research" });
    const text = (label: string) => within(analysts).getByText(label).closest("li")?.textContent ?? "";
    expect(text("Market analysis")).toContain("completed");
    expect(text("News analysis")).toContain("in progress");
    expect(text("Fundamentals analysis")).toContain("pending");
    const structure = screen.getByRole("list", { name: "Structure analysis" });
    expect(within(structure).getByText("Conflict analysis").closest("li")?.textContent).toContain("pending");
  });

  it("draws the newest structure connection in the accent color only while the run is going", async () => {
    const structure = { current_stage: "alpha_mapping", completed_units: 11 };
    const spy = vi.spyOn(client, "getResearchRunStatus");

    spy.mockResolvedValue(makeRunRecord({ ...RUNNING_RECORD, ...structure }));
    const running = renderPage();
    await screen.findByRole("heading", { name: "Analyzing NVDA" });
    expect(document.querySelectorAll(".scene-edge-latest")).toHaveLength(1);
    running.unmount();

    spy.mockResolvedValue(
      makeRunRecord({ ...RUNNING_RECORD, ...structure, status: "failed", stage: "failed", error_code: "RESEARCH_TIMEOUT", started_at: "2026-10-07T10:00:00Z" })
    );
    renderPage();
    await screen.findByText(/research run failed/i);
    expect(document.querySelectorAll(".scene-edge")).not.toHaveLength(0);
    expect(document.querySelectorAll(".scene-edge-latest")).toHaveLength(0);
  });

  it("lists all 17 stages in four groups", async () => {
    vi.spyOn(client, "getResearchRunStatus").mockResolvedValue(RUNNING_RECORD);
    renderPage();
    const items = await screen.findAllByRole("listitem");
    expect(items).toHaveLength(17);
    for (const group of ["Preparing", "Analyst research", "Debate and decision", "Structure analysis"]) {
      expect(screen.getByRole("list", { name: group })).toBeInTheDocument();
    }
  });

  it("never grows the percentage client-side between polls", async () => {
    vi.useFakeTimers();
    answerOnce(WITH_ETA);
    renderPage();
    await vi.waitFor(() => expect(screen.getByRole("progressbar")).toBeInTheDocument());
    expect(screen.getByRole("progressbar")).toHaveAttribute("aria-valuenow", "43");
    // Minutes pass with no new answer: time-based text moves, the
    // percentage must not.
    await act(async () => {
      await vi.advanceTimersByTimeAsync(5 * 60 * 1000);
    });
    expect(screen.getByRole("progressbar")).toHaveAttribute("aria-valuenow", "43");
    expect(screen.getByText("43%")).toBeInTheDocument();
  });

  it("shows the estimating message when no ETA history exists", async () => {
    vi.spyOn(client, "getResearchRunStatus").mockResolvedValue(RUNNING_RECORD);
    renderPage();
    expect(await screen.findByText("Estimating time…")).toBeInTheDocument();
    expect(screen.getByText("Not enough past runs to estimate yet")).toBeInTheDocument();
    expect(screen.queryByText(/min left/)).toBeNull();
  });

  it("shows a whole-minute range and its basis when ETA history is available", async () => {
    vi.spyOn(client, "getResearchRunStatus").mockResolvedValue(
      makeRunRecord({
        ...RUNNING_RECORD,
        eta_status: "available",
        estimated_remaining_seconds_min: 120,
        estimated_remaining_seconds_max: 240,
        eta_sample_count: 5,
      })
    );
    renderPage();
    expect(await screen.findByText("About 2–4 min left")).toBeInTheDocument();
    expect(screen.getByText("Based on 5 similar runs")).toBeInTheDocument();
  });

  it("counts the estimate and the elapsed time down in real time between polls", async () => {
    vi.useFakeTimers();
    answerOnce(WITH_ETA);
    renderPage();
    await vi.waitFor(() => expect(screen.getByText("About 10–16 min left")).toBeInTheDocument());
    expect(screen.getByText("Elapsed 1m 38s")).toBeInTheDocument();

    await act(async () => {
      await vi.advanceTimersByTimeAsync(300_000);
    });

    expect(screen.getByText("About 5–11 min left")).toBeInTheDocument();
    expect(screen.getByText("Elapsed 6m 38s")).toBeInTheDocument();
  });

  it("says it is taking longer once the estimate has run out, not a negative or stuck zero", async () => {
    vi.useFakeTimers();
    answerOnce(makeRunRecord({ ...WITH_ETA, estimated_remaining_seconds_min: 60, estimated_remaining_seconds_max: 120 }));
    renderPage();
    await vi.waitFor(() => expect(screen.getByText("About 1–2 min left")).toBeInTheDocument());

    await act(async () => {
      await vi.advanceTimersByTimeAsync(130_000);
    });

    expect(screen.getByText("Taking longer than usual")).toBeInTheDocument();
  });

  it("shows the finished state with a View results button and never navigates on its own", async () => {
    vi.useFakeTimers();
    vi.spyOn(client, "getResearchRunStatus").mockResolvedValue(
      makeRunRecord({ status: "completed", stage: "completed", progress_percent: 100, elapsed_seconds: 620 })
    );
    renderPage();
    await vi.waitFor(() => expect(screen.getByText("Research complete")).toBeInTheDocument());
    expect(screen.getByText("Finished in 10m 20s")).toBeInTheDocument();
    expect(screen.getByRole("link", { name: "View results" })).toHaveAttribute("href", "/runs/run-1/research");

    await act(async () => {
      await vi.advanceTimersByTimeAsync(10_000);
    });

    expect(screen.queryByText("results page for run-1")).toBeNull();
    expect(screen.getByText("Research complete")).toBeInTheDocument();
  });

  it("opens the results when View results is chosen", async () => {
    vi.spyOn(client, "getResearchRunStatus").mockResolvedValue(
      makeRunRecord({ status: "completed", stage: "completed", progress_percent: 100 })
    );
    renderPage();
    fireEvent.click(await screen.findByRole("link", { name: "View results" }));
    expect(await screen.findByText("results page for run-1")).toBeInTheDocument();
  });

  it("marks every stage completed for a completed run and drops the leave-the-page note", async () => {
    vi.spyOn(client, "getResearchRunStatus").mockResolvedValue(
      makeRunRecord({
        status: "completed",
        stage: "completed",
        progress_percent: 100,
        current_stage: "completed",
        completed_units: 15,
        total_units: 15,
      })
    );
    renderPage();
    const items = await screen.findAllByRole("listitem");
    expect(items).toHaveLength(17);
    expect(items.every((item) => item.textContent?.includes("completed"))).toBe(true);
    expect(screen.queryByText(/you can leave this page/i)).toBeNull();
  });

  it("shows a partial notice with a link to the partial results (no auto-navigation)", async () => {
    vi.spyOn(client, "getResearchRunStatus").mockResolvedValue(
      makeRunRecord({
        status: "partial",
        stage: "partial",
        progress_percent: 100,
        current_stage: "completed_partial",
        completed_units: 6,
        total_units: 15,
      })
    );
    renderPage();
    await waitFor(() => expect(screen.getByText(/finished only partially/i)).toBeInTheDocument());
    expect(screen.getByRole("link", { name: /open partial results/i })).toBeInTheDocument();
    const items = screen.getAllByRole("listitem");
    expect(items.some((item) => item.textContent?.includes("completed"))).toBe(true);
    expect(items.some((item) => item.textContent?.includes("pending"))).toBe(true);
    expect(items.every((item) => item.textContent?.includes("completed"))).toBe(false);
  });

  it("stays on the page for a failed run with retry, refresh, and return actions", async () => {
    vi.spyOn(client, "getResearchRunStatus").mockResolvedValue(
      makeRunRecord({
        status: "failed",
        stage: "failed",
        error_code: "RESEARCH_TIMEOUT",
        message: "The research run exceeded the configured execution time.",
        started_at: "2026-07-16T12:00:00Z",
        progress_percent: 64,
        completed_units: 6,
        total_units: 15,
      })
    );
    renderPage();
    await waitFor(() => expect(screen.getByText(/research run failed/i)).toBeInTheDocument());
    expect(
      screen.getByText("The research run exceeded the configured execution time.")
    ).toBeInTheDocument();
    expect(screen.getByText("RESEARCH_TIMEOUT")).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "Retry research" })).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "Refresh status" })).toBeInTheDocument();
    expect(screen.getByRole("link", { name: /return to research/i })).toBeInTheDocument();
    const items = screen.getAllByRole("listitem");
    expect(items.some((item) => item.textContent?.includes("completed"))).toBe(true);
    expect(items.some((item) => item.textContent?.includes("failed"))).toBe(true);
    expect(items.some((item) => item.textContent?.includes("pending"))).toBe(true);
    // Never bounced away from the processing page, and no progress claim.
    expect(screen.queryByText(/results page for/)).toBeNull();
    expect(screen.queryByRole("progressbar")).toBeNull();
  });

  it("shows a connection issue with status refresh without marking the run failed", async () => {
    const { ApiError } = await import("../api/errors");
    vi.spyOn(client, "getResearchRunStatus").mockRejectedValue(ApiError.network());
    renderPage();
    await waitFor(() => expect(screen.getByText(/connection issue/i)).toBeInTheDocument());
    expect(screen.getByRole("button", { name: /refresh status/i })).toBeInTheDocument();
    expect(screen.queryByText(/research run failed/i)).toBeNull();
  });

  it("restores the run purely from the URL run_id", async () => {
    const spy = vi.spyOn(client, "getResearchRunStatus").mockResolvedValue(RUNNING_RECORD);
    renderPage("run-from-url");
    await waitFor(() => expect(spy).toHaveBeenCalledWith("run-from-url", expect.anything()));
  });

  it("handles a missing-progress legacy run without fabricating a percentage", async () => {
    vi.spyOn(client, "getResearchRunStatus").mockResolvedValue(
      makeRunRecord({ status: "running", stage: "research_pipeline" })
    );
    renderPage();
    expect(await screen.findByText(/progress reporting is not available/i)).toBeInTheDocument();
    expect(screen.getByRole("progressbar")).not.toHaveAttribute("aria-valuenow");
    expect(screen.queryByText(/%$/)).toBeNull();
  });

  it("shows a loading message when a run is opened directly and nothing has answered yet", () => {
    vi.spyOn(client, "getResearchRunStatus").mockReturnValue(new Promise(() => undefined));
    renderPage();
    expect(screen.getByText("Loading run status…")).toBeInTheDocument();
    expect(screen.queryByRole("progressbar")).toBeNull();
  });
});

describe("ProcessingPage -- opened by Start research", () => {
  afterEach(() => {
    vi.restoreAllMocks();
  });

  it("draws the page at once from what was just submitted, before the first poll", () => {
    vi.spyOn(client, "getResearchRunStatus").mockReturnValue(new Promise(() => undefined));
    setRunHandoff({
      runId: "run-1",
      ticker: "AMD",
      analysisDate: "2026-10-07",
      selectedAnalysts: ["market", "sentiment", "news", "fundamentals"],
      geometry: null,
      createdAt: Date.now(),
    });
    renderPage();

    expect(screen.getByRole("heading", { name: "Analyzing AMD" })).toBeInTheDocument();
    expect(screen.getByText("Analysis date Oct 7, 2026, all four analysts")).toBeInTheDocument();
    expect(screen.getByText("Estimating time…")).toBeInTheDocument();
    expect(screen.getByRole("progressbar")).toHaveAttribute("aria-valuenow", "0");
    expect(screen.getAllByRole("listitem")).toHaveLength(17);
    expect(screen.queryByText("Loading run status…")).toBeNull();
  });

  it("uses the hand-off once: a later visit to the same run starts plain", () => {
    vi.spyOn(client, "getResearchRunStatus").mockReturnValue(new Promise(() => undefined));
    setRunHandoff({
      runId: "run-1",
      ticker: "AMD",
      analysisDate: null,
      selectedAnalysts: [],
      geometry: null,
      createdAt: Date.now(),
    });
    const first = renderPage();
    expect(peekRunHandoff("run-1")).toBeNull();
    first.unmount();

    renderPage();
    expect(screen.getByText("Loading run status…")).toBeInTheDocument();
    expect(screen.queryByRole("heading", { name: "Analyzing AMD" })).toBeNull();
  });

  it("ignores a hand-off meant for a different run", () => {
    vi.spyOn(client, "getResearchRunStatus").mockReturnValue(new Promise(() => undefined));
    setRunHandoff({
      runId: "some-other-run",
      ticker: "AMD",
      analysisDate: null,
      selectedAnalysts: [],
      geometry: null,
      createdAt: Date.now(),
    });
    renderPage();
    expect(screen.getByText("Loading run status…")).toBeInTheDocument();
  });
});

describe("ProcessingPage -- tab title", () => {
  afterEach(() => {
    vi.restoreAllMocks();
  });

  it("shows progress in the tab title and restores the old title on leaving", async () => {
    document.title = "Before";
    vi.spyOn(client, "getResearchRunStatus").mockResolvedValue(RUNNING_RECORD);
    const { unmount } = renderPage();
    await waitFor(() => expect(document.title).toBe("43% · NVDA"));
    unmount();
    expect(document.title).toBe("Before");
  });

  it("says Done, Partial or Failed for a finished run", async () => {
    vi.spyOn(client, "getResearchRunStatus").mockResolvedValue(
      makeRunRecord({ status: "completed", stage: "completed", progress_percent: 100 })
    );
    renderPage();
    await waitFor(() => expect(document.title).toBe("Done · NVDA"));
  });
});

describe("ProcessingPage -- price history and notifications", () => {
  afterEach(() => {
    vi.restoreAllMocks();
    vi.unstubAllEnvs();
    vi.unstubAllGlobals();
  });

  it("shows no price history card by default: there is no real data source yet", async () => {
    vi.spyOn(client, "getResearchRunStatus").mockResolvedValue(RUNNING_RECORD);
    renderPage();
    await screen.findByRole("heading", { name: "Analyzing NVDA" });
    expect(screen.queryByRole("button", { name: /price history/i })).toBeNull();
  });

  it("shows a clearly labelled sample card only when the development switch is on", async () => {
    vi.stubEnv("VITE_SAMPLE_PRICE_HISTORY", "1");
    vi.spyOn(client, "getResearchRunStatus").mockResolvedValue(RUNNING_RECORD);
    renderPage();
    const card = await screen.findByRole("button", { name: "Open NVDA price history" });
    expect(card).toHaveTextContent("Sample data");
  });

  it("offers notifications while the run is going and asks permission only on click", async () => {
    const requestPermission = vi.fn().mockResolvedValue("granted");
    vi.stubGlobal(
      "Notification",
      Object.assign(vi.fn(), { permission: "default", requestPermission })
    );
    vi.spyOn(client, "getResearchRunStatus").mockResolvedValue(RUNNING_RECORD);
    renderPage();

    const button = await screen.findByRole("button", { name: "Notify me when done" });
    expect(requestPermission).not.toHaveBeenCalled();
    fireEvent.click(button);
    await waitFor(() => expect(requestPermission).toHaveBeenCalledTimes(1));
    expect(await screen.findByText(/you will get a notification/i)).toBeInTheDocument();
  });

  it("offers no notification control for a run that has already finished", async () => {
    vi.stubGlobal("Notification", Object.assign(vi.fn(), { permission: "default", requestPermission: vi.fn() }));
    vi.spyOn(client, "getResearchRunStatus").mockResolvedValue(
      makeRunRecord({ status: "completed", stage: "completed", progress_percent: 100 })
    );
    renderPage();
    await screen.findByText("Research complete");
    expect(screen.queryByRole("button", { name: "Notify me when done" })).toBeNull();
  });
});
