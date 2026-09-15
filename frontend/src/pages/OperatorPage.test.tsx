import { render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { MemoryRouter, Route, Routes } from "react-router-dom";
import { afterEach, describe, expect, it, vi } from "vitest";
import * as client from "../api/client";
import { ApiError } from "../api/errors";
import type { ReplayAllResult } from "../api/types";
import { OperatorPage } from "./OperatorPage";

// Product Demo Hardening Phase 2C (P1-4): Replay-All remains fully
// available for engineering/operator workflows, relocated to a narrowly
// scoped, non-primary route (/operator) rather than deleted.

function renderPage() {
  return render(
    <MemoryRouter initialEntries={["/operator"]}>
      <Routes>
        <Route path="/operator" element={<OperatorPage />} />
      </Routes>
    </MemoryRouter>
  );
}

function sampleResult(overrides: Partial<ReplayAllResult> = {}): ReplayAllResult {
  return {
    status: "completed",
    total_runs_found: 1,
    completed_count: 1,
    blocked_count: 0,
    failed_count: 0,
    results: [
      {
        source_run_id: "source-1",
        ticker: "SNDK",
        replay_run_id: "replay-1",
        status: "completed",
        output_dir: "outputs/replays/replay-1",
        error_code: null,
      },
    ],
    provider_calls: 0,
    tradingagents_calls: 0,
    ...overrides,
  };
}

describe("OperatorPage", () => {
  afterEach(() => {
    vi.restoreAllMocks();
  });

  it("has an explicit operator-role heading and explanatory copy", () => {
    renderPage();
    expect(screen.getByRole("heading", { name: "Operator Tools" })).toBeInTheDocument();
    expect(
      screen.getByText("Maintenance and replay utilities for persisted research runs.")
    ).toBeInTheDocument();
  });

  it("hosts the ReplayAllPanel functionality unchanged", () => {
    renderPage();
    expect(
      screen.getByRole("button", { name: "Re-run all saved outputs with current architecture" })
    ).toBeInTheDocument();
  });

  it("preserves the existing confirmation dialog before sending a request", async () => {
    const user = userEvent.setup();
    const spy = vi.spyOn(client, "replayAllSavedOutputs");
    renderPage();
    await user.click(screen.getByRole("button", { name: "Re-run all saved outputs with current architecture" }));
    expect(screen.getByRole("dialog")).toBeInTheDocument();
    await user.click(screen.getByRole("button", { name: "Cancel" }));
    expect(screen.queryByRole("dialog")).not.toBeInTheDocument();
    expect(spy).not.toHaveBeenCalled();
  });

  it("still sends the request to POST /api/replay-all via the unchanged client function on confirm", async () => {
    const user = userEvent.setup();
    const spy = vi.spyOn(client, "replayAllSavedOutputs").mockResolvedValue(sampleResult());
    renderPage();
    await user.click(screen.getByRole("button", { name: "Re-run all saved outputs with current architecture" }));
    await user.click(screen.getByRole("button", { name: "Start replay" }));
    await waitFor(() => expect(spy).toHaveBeenCalledTimes(1));
  });

  it("still shows a results summary after a successful replay", async () => {
    const user = userEvent.setup();
    vi.spyOn(client, "replayAllSavedOutputs").mockResolvedValue(sampleResult());
    renderPage();
    await user.click(screen.getByRole("button", { name: "Re-run all saved outputs with current architecture" }));
    await user.click(screen.getByRole("button", { name: "Start replay" }));
    await waitFor(() => expect(screen.getByText(/1 runs processed/)).toBeInTheDocument());
    expect(screen.getByText(/1 runs processed/).textContent).toContain("1 completed");
  });

  it("still shows a safe error message, never a raw exception, on replay failure", async () => {
    const user = userEvent.setup();
    vi.spyOn(client, "replayAllSavedOutputs").mockRejectedValue(ApiError.network());
    renderPage();
    await user.click(screen.getByRole("button", { name: "Re-run all saved outputs with current architecture" }));
    await user.click(screen.getByRole("button", { name: "Start replay" }));
    await waitFor(() => expect(screen.getByRole("alert")).toBeInTheDocument());
  });

  it("never implies replay is equivalent to running new research or calling a Provider", async () => {
    const user = userEvent.setup();
    renderPage();
    expect((document.body.textContent ?? "").toLowerCase()).not.toContain("start research");
    await user.click(screen.getByRole("button", { name: "Re-run all saved outputs with current architecture" }));
    expect(document.body.textContent ?? "").toContain(
      "It will not rerun TradingAgents or call an LLM provider."
    );
  });
});
