import { render, screen, waitFor } from "@testing-library/react";
import { MemoryRouter, Route, Routes } from "react-router-dom";
import { afterEach, describe, expect, it, vi } from "vitest";
import * as client from "../api/client";
import { makeRunRecord } from "../tests/factories";
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

describe("ProcessingPage", () => {
  afterEach(() => {
    vi.restoreAllMocks();
  });

  it("renders real backend progress: bar value, steps, elapsed, profile name", async () => {
    vi.spyOn(client, "getResearchRunStatus").mockResolvedValue(RUNNING_RECORD);
    renderPage();

    await waitFor(() => expect(screen.getByText("Analyzing NVDA")).toBeInTheDocument());
    const bar = screen.getByRole("progressbar");
    expect(bar).toHaveAttribute("aria-valuemin", "0");
    expect(bar).toHaveAttribute("aria-valuemax", "100");
    expect(bar).toHaveAttribute("aria-valuenow", "43");
    expect(screen.getByText(/43% complete/)).toBeInTheDocument();
    expect(screen.getByText(/4 of 15 steps/)).toBeInTheDocument();
    expect(screen.getByText(/elapsed time: 1m 38s/i)).toBeInTheDocument();
    expect(screen.getByText(/research profile: comqutor anthropic medium v1/i)).toBeInTheDocument();
    expect(screen.getByText(/current step: running the news analyst/i)).toBeInTheDocument();
  });

  it("marks completed, in-progress, and remaining stages distinctly (not by color alone)", async () => {
    vi.spyOn(client, "getResearchRunStatus").mockResolvedValue(RUNNING_RECORD);
    renderPage();

    await waitFor(() => expect(screen.getByRole("list", { name: /research stages/i })).toBeInTheDocument());
    const items = screen.getAllByRole("listitem");
    const text = (label: string) =>
      items.find((item) => item.textContent?.includes(label))?.textContent ?? "";
    expect(text("Market analysis")).toContain("completed");
    expect(text("News analysis")).toContain("in progress");
    expect(text("Conflict analysis")).toContain("pending");
  });

  it("never grows the percentage client-side between polls", async () => {
    vi.useFakeTimers();
    try {
      vi.spyOn(client, "getResearchRunStatus").mockResolvedValue(RUNNING_RECORD);
      renderPage();
      await vi.waitFor(() => expect(screen.getByRole("progressbar")).toBeInTheDocument());
      expect(screen.getByRole("progressbar")).toHaveAttribute("aria-valuenow", "43");
      // Advance well past any imaginary ticker -- the value must not move
      // without a new backend value.
      await vi.advanceTimersByTimeAsync(400);
      expect(screen.getByRole("progressbar")).toHaveAttribute("aria-valuenow", "43");
    } finally {
      vi.useRealTimers();
    }
  });

  it("shows the estimating message when no ETA history exists", async () => {
    vi.spyOn(client, "getResearchRunStatus").mockResolvedValue(RUNNING_RECORD);
    renderPage();
    await waitFor(() =>
      expect(screen.getByText("Estimating completion time…")).toBeInTheDocument()
    );
    expect(screen.queryByText(/approximately/)).toBeNull();
  });

  it("shows an approximate range when ETA history is available", async () => {
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
    await waitFor(() =>
      expect(
        screen.getByText("Estimated remaining time: approximately 2–4 minutes")
      ).toBeInTheDocument()
    );
  });

  it("auto-navigates to the results page once the run completes", async () => {
    vi.spyOn(client, "getResearchRunStatus").mockResolvedValue(
      makeRunRecord({ status: "completed", stage: "completed", progress_percent: 100 })
    );
    renderPage();
    await waitFor(() =>
      expect(screen.getByText(/research complete\. opening results…/i)).toBeInTheDocument()
    );
    await waitFor(
      () => expect(screen.getByText("results page for run-1")).toBeInTheDocument(),
      { timeout: 3000 }
    );
  });

  it("marks every checklist stage completed for a completed run", async () => {
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
    // Never bounced away from the processing page.
    expect(screen.queryByText(/results page for/)).toBeNull();
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
    await waitFor(() =>
      expect(screen.getByText(/progress reporting is not available/i)).toBeInTheDocument()
    );
    expect(screen.getByRole("progressbar")).not.toHaveAttribute("aria-valuenow");
  });
});
