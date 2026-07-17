import { fireEvent, render, screen, waitFor } from "@testing-library/react";
import { MemoryRouter, Route, Routes } from "react-router-dom";
import { afterEach, describe, expect, it, vi } from "vitest";
import * as client from "../api/client";
import { makeRunRecord } from "../tests/factories";
import { ProcessingPage } from "./ProcessingPage";

const FAILED_RUN = makeRunRecord({
  run_id: "failed-run",
  ticker: "NVDA",
  analysis_date: "2026-07-16",
  selected_analysts: ["market", "sentiment", "news", "fundamentals"],
  status: "failed",
  stage: "failed",
  error_code: "RESEARCH_TIMEOUT",
  message: "The research run exceeded the configured timeout.",
  started_at: "2026-07-16T12:00:00Z",
  progress_percent: 64,
  current_stage: "failed",
  completed_units: 6,
  total_units: 15,
});

function renderFailedPage() {
  vi.spyOn(client, "getResearchRunStatus").mockResolvedValue(FAILED_RUN);
  return render(
    <MemoryRouter initialEntries={["/runs/failed-run/processing"]}>
      <Routes>
        <Route path="/runs/:runId/processing" element={<ProcessingPage />} />
        <Route path="/runs/new-run/processing" element={<p>new processing run</p>} />
        <Route path="/runs/cached-run/research" element={<p>cached research run</p>} />
      </Routes>
    </MemoryRouter>
  );
}

describe("ProcessingPage failed-run retry", () => {
  afterEach(() => {
    vi.restoreAllMocks();
  });

  it("POSTs only ticker/date/analysts and navigates a 202 to the new processing run", async () => {
    const submit = vi.spyOn(client, "submitResearch").mockResolvedValue({
      status: 202,
      result: { run_id: "new-run", ticker: "NVDA", status: "queued", cache_disposition: "created" },
    });
    renderFailedPage();

    fireEvent.click(await screen.findByRole("button", { name: "Retry research" }));
    await waitFor(() => expect(submit).toHaveBeenCalledTimes(1));
    expect(submit.mock.calls[0]?.[0]).toEqual({
      ticker: "NVDA",
      analysis_date: "2026-07-16",
      selected_analysts: ["market", "sentiment", "news", "fundamentals"],
    });
    expect(submit.mock.calls[0]?.[0]).not.toHaveProperty("run_id");
    expect(submit.mock.calls[0]?.[0]).not.toHaveProperty("force_refresh");
    expect(submit.mock.calls[0]?.[1]?.signal).toBeInstanceOf(AbortSignal);
    expect(await screen.findByText("new processing run")).toBeInTheDocument();
  });

  it("navigates an HTTP 200 completed reuse directly to results", async () => {
    vi.spyOn(client, "submitResearch").mockResolvedValue({
      status: 200,
      result: {
        run_id: "cached-run",
        ticker: "NVDA",
        status: "completed",
        cache_disposition: "reused_completed",
      },
    });
    renderFailedPage();
    fireEvent.click(await screen.findByRole("button", { name: "Retry research" }));
    expect(await screen.findByText("cached research run")).toBeInTheDocument();
  });

  it("stays on the failed page and shows safe copy when POST is rejected", async () => {
    vi.spyOn(client, "submitResearch").mockResolvedValue({
      status: 503,
      result: {
        run_id: null,
        ticker: "NVDA",
        status: "failed",
        error_code: "RESEARCH_QUEUE_FULL",
        message: "The research job queue is full.",
      },
    });
    renderFailedPage();
    fireEvent.click(await screen.findByRole("button", { name: "Retry research" }));
    expect(await screen.findByText(/queue is full right now/i)).toBeInTheDocument();
    expect(screen.getByText(/research run failed/i)).toBeInTheDocument();
  });

  it("blocks duplicate Retry clicks while the POST is pending", async () => {
    let resolveRequest!: (value: Awaited<ReturnType<typeof client.submitResearch>>) => void;
    const pendingRequest = new Promise<Awaited<ReturnType<typeof client.submitResearch>>>((resolve) => {
      resolveRequest = resolve;
    });
    const submit = vi.spyOn(client, "submitResearch").mockReturnValue(pendingRequest);
    renderFailedPage();
    const button = await screen.findByRole("button", { name: "Retry research" });
    fireEvent.click(button);
    fireEvent.click(button);
    expect(submit).toHaveBeenCalledTimes(1);
    expect(screen.getByRole("button", { name: "Retrying…" })).toBeDisabled();
    resolveRequest({
      status: 202,
      result: { run_id: "new-run", ticker: "NVDA", status: "queued", cache_disposition: "created" },
    });
    expect(await screen.findByText("new processing run")).toBeInTheDocument();
  });

  it("keeps Refresh status as GET-only", async () => {
    const submit = vi.spyOn(client, "submitResearch");
    renderFailedPage();
    const refresh = await screen.findByRole("button", { name: "Refresh status" });
    fireEvent.click(refresh);
    await waitFor(() => expect(client.getResearchRunStatus).toHaveBeenCalledTimes(2));
    expect(submit).not.toHaveBeenCalled();
  });
});
