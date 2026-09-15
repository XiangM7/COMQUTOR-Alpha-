import { render, screen, waitFor } from "@testing-library/react";
import { MemoryRouter } from "react-router-dom";
import { afterEach, describe, expect, it, vi } from "vitest";
import * as client from "../api/client";
import { ResearchPage } from "./ResearchPage";

// Product Demo Hardening Phase 2C (P1-4): the normal /research landing page
// must no longer expose the operator-only Replay-All control. Replay
// functionality itself is not deleted -- see OperatorPage.test.tsx.

function renderPage() {
  return render(
    <MemoryRouter>
      <ResearchPage />
    </MemoryRouter>
  );
}

function mockReadinessAndHistory() {
  vi.spyOn(client, "getReadiness").mockResolvedValue({
    status: 200,
    result: {
      status: "ready",
      database: "ready",
      job_manager: "ready",
      real_execution: "disabled",
      live_semantic_pipeline: "not_applicable",
    },
  });
  vi.spyOn(client, "getResearchHistory").mockResolvedValue({ status: "ok", items: [], next_cursor: null });
}

describe("ResearchPage", () => {
  afterEach(() => {
    vi.restoreAllMocks();
  });

  it("does not render ReplayAllPanel or its 'Reprocess saved outputs' heading", async () => {
    mockReadinessAndHistory();
    renderPage();
    await waitFor(() => expect(screen.getByText(/research a ticker/i)).toBeInTheDocument());
    expect(screen.queryByText("Reprocess saved outputs")).not.toBeInTheDocument();
    expect(
      screen.queryByRole("button", { name: /re-run all saved outputs with current architecture/i })
    ).not.toBeInTheDocument();
  });

  it("never calls the replay-all endpoint from the normal Research landing page", async () => {
    mockReadinessAndHistory();
    const replaySpy = vi.spyOn(client, "replayAllSavedOutputs");
    renderPage();
    await waitFor(() => expect(screen.getByText(/research a ticker/i)).toBeInTheDocument());
    expect(replaySpy).not.toHaveBeenCalled();
  });

  it("still shows the normal research workflow: ticker input and Recent research runs", async () => {
    mockReadinessAndHistory();
    renderPage();
    await waitFor(() => expect(screen.getByText(/research a ticker/i)).toBeInTheDocument());
    expect(screen.getByLabelText("Ticker")).toBeInTheDocument();
    expect(screen.getByText("Recent research runs")).toBeInTheDocument();
    expect(screen.getByText("No research runs yet")).toBeInTheDocument();
  });

  it("still shows the existing product explainer panel", async () => {
    mockReadinessAndHistory();
    renderPage();
    await waitFor(() => expect(screen.getByText("What makes COMQUTOR different")).toBeInTheDocument());
  });
});
