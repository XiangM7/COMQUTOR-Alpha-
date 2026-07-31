import { render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { MemoryRouter } from "react-router-dom";
import { afterEach, describe, expect, it, vi } from "vitest";
import * as client from "../api/client";
import { ApiError } from "../api/errors";
import type { ReplayAllResult } from "../api/types";
import { ReplayAllPanel } from "./ReplayAllPanel";

function renderPanel() {
  return render(
    <MemoryRouter>
      <ReplayAllPanel />
    </MemoryRouter>
  );
}

function sampleResult(overrides: Partial<ReplayAllResult> = {}): ReplayAllResult {
  return {
    status: "completed",
    total_runs_found: 2,
    completed_count: 1,
    blocked_count: 0,
    failed_count: 1,
    results: [
      {
        source_run_id: "source-1",
        ticker: "SNDK",
        replay_run_id: "replay-1",
        status: "completed",
        output_dir: "outputs/replays/replay-1",
        error_code: null,
      },
      {
        source_run_id: "source-2",
        ticker: "MSFT",
        replay_run_id: null,
        status: "failed",
        output_dir: null,
        error_code: "REPLAY_SERVICE_ERROR",
      },
    ],
    provider_calls: 0,
    tradingagents_calls: 0,
    ...overrides,
  };
}

describe("ReplayAllPanel", () => {
  afterEach(() => {
    vi.restoreAllMocks();
  });

  it("shows the reprocess button on the Research page", () => {
    renderPanel();
    expect(
      screen.getByRole("button", { name: "Re-run all saved outputs with current architecture" })
    ).toBeInTheDocument();
  });

  it("clicking the button opens a confirmation dialog with the required copy", async () => {
    const user = userEvent.setup();
    renderPanel();
    await user.click(screen.getByRole("button", { name: "Re-run all saved outputs with current architecture" }));

    expect(screen.getByRole("dialog")).toBeInTheDocument();
    expect(
      screen.getByText(
        "This will reprocess every saved TradingAgents output using the current COMQUTOR architecture."
      )
    ).toBeInTheDocument();
    expect(
      screen.getByText(
        "It will not rerun TradingAgents or call an LLM provider. Existing source runs will not be overwritten."
      )
    ).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "Cancel" })).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "Start replay" })).toBeInTheDocument();
  });

  it("Cancel closes the dialog without sending a request", async () => {
    const user = userEvent.setup();
    const spy = vi.spyOn(client, "replayAllSavedOutputs");
    renderPanel();
    await user.click(screen.getByRole("button", { name: "Re-run all saved outputs with current architecture" }));
    await user.click(screen.getByRole("button", { name: "Cancel" }));

    expect(screen.queryByRole("dialog")).not.toBeInTheDocument();
    expect(spy).not.toHaveBeenCalled();
  });

  it("Start replay sends exactly one request and disables the button while pending", async () => {
    const user = userEvent.setup();
    let resolveRequest!: (value: ReplayAllResult) => void;
    const spy = vi.spyOn(client, "replayAllSavedOutputs").mockReturnValue(
      new Promise((resolve) => {
        resolveRequest = resolve;
      })
    );
    renderPanel();
    await user.click(screen.getByRole("button", { name: "Re-run all saved outputs with current architecture" }));
    await user.click(screen.getByRole("button", { name: "Start replay" }));

    expect(spy).toHaveBeenCalledTimes(1);
    const button = screen.getByRole("button", { name: "Reprocessing…" });
    expect(button).toBeDisabled();
    expect(screen.queryByRole("dialog")).not.toBeInTheDocument();

    resolveRequest(sampleResult());
    await waitFor(() => expect(screen.getByRole("button", { name: /Re-run all saved outputs/ })).not.toBeDisabled());
    expect(spy).toHaveBeenCalledTimes(1);
  });

  it("shows a results summary with per-run ticker, source run, and status after completion", async () => {
    const user = userEvent.setup();
    vi.spyOn(client, "replayAllSavedOutputs").mockResolvedValue(sampleResult());
    renderPanel();
    await user.click(screen.getByRole("button", { name: "Re-run all saved outputs with current architecture" }));
    await user.click(screen.getByRole("button", { name: "Start replay" }));

    expect(await screen.findByText(/2 runs processed/)).toBeInTheDocument();
    expect(screen.getByText(/1 completed/)).toBeInTheDocument();
    expect(screen.getByText(/1 failed/)).toBeInTheDocument();
    expect(screen.getByText("source-1")).toBeInTheDocument();
    expect(screen.getByText("source-2")).toBeInTheDocument();
    expect(screen.getByText("SNDK")).toBeInTheDocument();
    expect(screen.getByText("MSFT")).toBeInTheDocument();
  });

  it("completed rows link to the replay run's output page", async () => {
    const user = userEvent.setup();
    vi.spyOn(client, "replayAllSavedOutputs").mockResolvedValue(sampleResult());
    renderPanel();
    await user.click(screen.getByRole("button", { name: "Re-run all saved outputs with current architecture" }));
    await user.click(screen.getByRole("button", { name: "Start replay" }));

    const link = await screen.findByRole("link", { name: "replay-1" });
    expect(link).toHaveAttribute("href", "/runs/replay-1/research");
  });

  it("failed rows never render as a clickable link", async () => {
    const user = userEvent.setup();
    vi.spyOn(client, "replayAllSavedOutputs").mockResolvedValue(sampleResult());
    renderPanel();
    await user.click(screen.getByRole("button", { name: "Re-run all saved outputs with current architecture" }));
    await user.click(screen.getByRole("button", { name: "Start replay" }));

    await screen.findByText("source-2");
    expect(screen.queryByRole("link", { name: /REPLAY_SERVICE_ERROR/ })).not.toBeInTheDocument();
  });

  it("shows an error and restores the button when the request fails", async () => {
    const user = userEvent.setup();
    vi.spyOn(client, "replayAllSavedOutputs").mockRejectedValue(
      ApiError.http(500, "REPLAY_ALL_INTERNAL_ERROR", "Something went wrong on the server.")
    );
    renderPanel();
    await user.click(screen.getByRole("button", { name: "Re-run all saved outputs with current architecture" }));
    await user.click(screen.getByRole("button", { name: "Start replay" }));

    expect(await screen.findByText("Something went wrong on the server.")).toBeInTheDocument();
    expect(screen.getByRole("button", { name: /Re-run all saved outputs/ })).not.toBeDisabled();
  });

  it("handles zero saved outputs without crashing", async () => {
    const user = userEvent.setup();
    vi.spyOn(client, "replayAllSavedOutputs").mockResolvedValue(
      sampleResult({ total_runs_found: 0, completed_count: 0, failed_count: 0, results: [] })
    );
    renderPanel();
    await user.click(screen.getByRole("button", { name: "Re-run all saved outputs with current architecture" }));
    await user.click(screen.getByRole("button", { name: "Start replay" }));

    expect(await screen.findByText(/No saved TradingAgents outputs were found/)).toBeInTheDocument();
  });
});
