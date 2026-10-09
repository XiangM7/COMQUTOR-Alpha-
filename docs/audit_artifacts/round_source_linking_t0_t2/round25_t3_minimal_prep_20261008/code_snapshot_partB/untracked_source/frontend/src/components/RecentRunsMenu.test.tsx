import { fireEvent, render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { MemoryRouter, Route, Routes } from "react-router-dom";
import { afterEach, describe, expect, it, vi } from "vitest";
import * as client from "../api/client";
import { makeRunRecord } from "../tests/factories";
import { RecentRunsMenu } from "./RecentRunsMenu";

function renderMenu() {
  return render(
    <MemoryRouter initialEntries={["/research"]}>
      <Routes>
        <Route path="/research" element={<RecentRunsMenu />} />
        <Route path="/runs/:runId/research" element={<p>OPENED_RESEARCH_RUN</p>} />
        <Route path="/runs/:runId/processing" element={<p>OPENED_PROCESSING_RUN</p>} />
      </Routes>
    </MemoryRouter>
  );
}

function openMenu() {
  fireEvent.click(screen.getByRole("button", { name: /recent runs/i }));
}

describe("RecentRunsMenu -- disclosure", () => {
  afterEach(() => {
    vi.restoreAllMocks();
  });

  it("is collapsed by default and does not request history until opened", () => {
    const historySpy = vi.spyOn(client, "getResearchHistory");
    renderMenu();

    const button = screen.getByRole("button", { name: /recent runs/i });
    expect(button).toHaveAttribute("aria-expanded", "false");
    expect(button).toHaveAttribute("aria-controls");
    expect(screen.queryByRole("region", { name: /recent runs/i })).not.toBeInTheDocument();
    expect(historySpy).not.toHaveBeenCalled();
  });

  it("opens on click, loads the first page of 10, and points aria-controls at the menu", async () => {
    const historySpy = vi
      .spyOn(client, "getResearchHistory")
      .mockResolvedValue({ status: "ok", items: [makeRunRecord({ run_id: "run-1", ticker: "NVDA" })], next_cursor: null });
    renderMenu();
    openMenu();

    const button = screen.getByRole("button", { name: /recent runs/i });
    expect(button).toHaveAttribute("aria-expanded", "true");
    const menu = screen.getByRole("region", { name: /recent runs/i });
    expect(button.getAttribute("aria-controls")).toBe(menu.id);
    await waitFor(() => expect(screen.getByText("NVDA")).toBeInTheDocument());
    expect(historySpy).toHaveBeenCalledTimes(1);
    expect(historySpy).toHaveBeenCalledWith({ limit: 10, ticker: undefined }, expect.anything());
  });

  it("collapses again on a second click", async () => {
    vi.spyOn(client, "getResearchHistory").mockResolvedValue({ status: "ok", items: [], next_cursor: null });
    renderMenu();
    openMenu();
    expect(screen.getByRole("region", { name: /recent runs/i })).toBeInTheDocument();

    openMenu();
    expect(screen.queryByRole("region", { name: /recent runs/i })).not.toBeInTheDocument();
    expect(screen.getByRole("button", { name: /recent runs/i })).toHaveAttribute("aria-expanded", "false");
  });

  it("closes on Escape and returns focus to the button", async () => {
    const user = userEvent.setup();
    vi.spyOn(client, "getResearchHistory").mockResolvedValue({ status: "ok", items: [], next_cursor: null });
    renderMenu();
    await user.click(screen.getByRole("button", { name: /recent runs/i }));
    await user.click(await screen.findByLabelText(/filter by ticker/i));

    await user.keyboard("{Escape}");

    expect(screen.queryByRole("region", { name: /recent runs/i })).not.toBeInTheDocument();
    expect(screen.getByRole("button", { name: /recent runs/i })).toHaveFocus();
  });

  it("closes when the user clicks outside the menu, but not when clicking inside it", async () => {
    const user = userEvent.setup();
    vi.spyOn(client, "getResearchHistory").mockResolvedValue({ status: "ok", items: [], next_cursor: null });
    renderMenu();
    await user.click(screen.getByRole("button", { name: /recent runs/i }));

    await user.click(await screen.findByText("No research runs yet"));
    expect(screen.getByRole("region", { name: /recent runs/i })).toBeInTheDocument();

    await user.click(document.body);
    expect(screen.queryByRole("region", { name: /recent runs/i })).not.toBeInTheDocument();
  });

  it("requests fresh history every time it is reopened", async () => {
    const historySpy = vi.spyOn(client, "getResearchHistory").mockResolvedValue({ status: "ok", items: [], next_cursor: null });
    renderMenu();
    openMenu();
    await waitFor(() => expect(historySpy).toHaveBeenCalledTimes(1));
    openMenu();
    openMenu();
    await waitFor(() => expect(historySpy).toHaveBeenCalledTimes(2));
  });
});

describe("RecentRunsMenu -- rows and states", () => {
  afterEach(() => {
    vi.restoreAllMocks();
  });

  it("shows ticker, status as text, analysis date and creation time for each run", async () => {
    vi.spyOn(client, "getResearchHistory").mockResolvedValue({
      status: "ok",
      items: [
        makeRunRecord({
          run_id: "run-1",
          ticker: "NVDA",
          status: "completed",
          analysis_date: "2026-10-06",
          created_at: "2026-10-06T14:05:00Z",
        }),
        makeRunRecord({ run_id: "run-2", ticker: "AMD", status: "partial", analysis_date: null }),
      ],
      next_cursor: null,
    });
    renderMenu();
    openMenu();

    const nvda = await screen.findByRole("link", { name: /NVDA/ });
    expect(nvda).toHaveTextContent("Completed");
    expect(nvda).toHaveTextContent("Analysis date Oct 6, 2026");
    const amd = screen.getByRole("link", { name: /AMD/ });
    expect(amd).toHaveTextContent("Partial");
    expect(amd).toHaveTextContent("Analysis date Not available");
  });

  it("shows a loading message while the first page is in flight", async () => {
    vi.spyOn(client, "getResearchHistory").mockReturnValue(new Promise(() => undefined));
    renderMenu();
    openMenu();
    expect(await screen.findByText("Loading recent research runs…")).toBeInTheDocument();
  });

  it("shows an empty state when there are no runs", async () => {
    vi.spyOn(client, "getResearchHistory").mockResolvedValue({ status: "ok", items: [], next_cursor: null });
    renderMenu();
    openMenu();
    expect(await screen.findByText("No research runs yet")).toBeInTheDocument();
  });

  it("shows an honest error when history cannot be loaded", async () => {
    vi.spyOn(client, "getResearchHistory").mockRejectedValue(new Error("network down"));
    renderMenu();
    openMenu();
    expect(await screen.findByRole("alert")).toHaveTextContent(/could not reach the comqutor api/i);
  });

  it("shows the server's message when history comes back as a failure envelope", async () => {
    vi.spyOn(client, "getResearchHistory").mockResolvedValue({
      run_id: null,
      ticker: null,
      status: "failed",
      message: "History is temporarily unavailable.",
    });
    renderMenu();
    openMenu();
    expect(await screen.findByRole("alert")).toHaveTextContent("History is temporarily unavailable.");
  });
});

// John MVP Gap Closure, Gap A (Run History Discovery): cursor-based "Load
// more" and a ticker filter, now inside the menu.
describe("RecentRunsMenu -- pagination and filtering", () => {
  afterEach(() => {
    vi.restoreAllMocks();
  });

  it("offers no Load more when no more runs exist", async () => {
    vi.spyOn(client, "getResearchHistory").mockResolvedValue({
      status: "ok",
      items: [makeRunRecord({ run_id: "run-1", ticker: "NVDA" })],
      next_cursor: null,
    });
    renderMenu();
    openMenu();
    await waitFor(() => expect(screen.getByText("NVDA")).toBeInTheDocument());
    expect(screen.queryByRole("button", { name: /load more/i })).not.toBeInTheDocument();
  });

  it("Load more retrieves the next cursor and appends without duplicating rows", async () => {
    const historySpy = vi
      .spyOn(client, "getResearchHistory")
      .mockResolvedValueOnce({
        status: "ok",
        items: [makeRunRecord({ run_id: "run-1", ticker: "NVDA" })],
        next_cursor: "cursor-abc",
      })
      .mockResolvedValueOnce({
        status: "ok",
        // Deliberately includes run-1 again, as a real backend page overlap
        // could -- the component must de-duplicate by run_id.
        items: [makeRunRecord({ run_id: "run-1", ticker: "NVDA" }), makeRunRecord({ run_id: "run-2", ticker: "QQQ" })],
        next_cursor: null,
      });
    renderMenu();
    openMenu();
    await waitFor(() => expect(screen.getByText("NVDA")).toBeInTheDocument());
    fireEvent.click(screen.getByRole("button", { name: /load more/i }));
    await waitFor(() => expect(screen.getByText("QQQ")).toBeInTheDocument());

    expect(screen.getAllByText("NVDA")).toHaveLength(1);
    expect(historySpy).toHaveBeenLastCalledWith(expect.objectContaining({ cursor: "cursor-abc" }));
    expect(screen.queryByRole("button", { name: /load more/i })).not.toBeInTheDocument();
  });

  it("shows an honest error and keeps existing rows when Load more fails", async () => {
    vi.spyOn(client, "getResearchHistory")
      .mockResolvedValueOnce({
        status: "ok",
        items: [makeRunRecord({ run_id: "run-1", ticker: "NVDA" })],
        next_cursor: "cursor-abc",
      })
      .mockRejectedValueOnce(new Error("network down"));
    renderMenu();
    openMenu();
    await waitFor(() => expect(screen.getByText("NVDA")).toBeInTheDocument());
    fireEvent.click(screen.getByRole("button", { name: /load more/i }));
    await waitFor(() => expect(screen.getByText(/could not reach the comqutor api/i)).toBeInTheDocument());
    // The row already on screen must not be silently cleared by the failure.
    expect(screen.getByText("NVDA")).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "Retry" })).toBeInTheDocument();
  });

  it("filtering by ticker requests a fresh first page scoped to that ticker", async () => {
    const historySpy = vi
      .spyOn(client, "getResearchHistory")
      .mockResolvedValueOnce({
        status: "ok",
        items: [makeRunRecord({ run_id: "run-1", ticker: "NVDA" }), makeRunRecord({ run_id: "run-2", ticker: "QQQ" })],
        next_cursor: null,
      })
      .mockResolvedValueOnce({
        status: "ok",
        items: [makeRunRecord({ run_id: "run-2", ticker: "QQQ" })],
        next_cursor: null,
      });
    renderMenu();
    openMenu();
    await waitFor(() => expect(screen.getByText("NVDA")).toBeInTheDocument());

    fireEvent.change(screen.getByLabelText(/filter by ticker/i), { target: { value: "qqq" } });
    fireEvent.click(screen.getByRole("button", { name: /^filter$/i }));

    await waitFor(() => expect(historySpy).toHaveBeenCalledTimes(2));
    expect(historySpy).toHaveBeenLastCalledWith(expect.objectContaining({ ticker: "QQQ" }), expect.anything());
    expect(historySpy.mock.calls.at(-1)?.[0]?.cursor).toBeUndefined();
    await waitFor(() => expect(screen.queryByText("NVDA")).not.toBeInTheDocument());
    expect(screen.getByText("QQQ")).toBeInTheDocument();
  });

  it("filters on Enter and can clear the filter back to all runs", async () => {
    const user = userEvent.setup();
    const historySpy = vi.spyOn(client, "getResearchHistory").mockResolvedValue({ status: "ok", items: [], next_cursor: null });
    renderMenu();
    await user.click(screen.getByRole("button", { name: /recent runs/i }));
    await user.type(await screen.findByLabelText(/filter by ticker/i), "amd{Enter}");

    await waitFor(() => expect(historySpy).toHaveBeenLastCalledWith(expect.objectContaining({ ticker: "AMD" }), expect.anything()));
    expect(await screen.findByText("No research runs found for AMD")).toBeInTheDocument();

    await user.click(screen.getByRole("button", { name: /clear \(amd\)/i }));
    await waitFor(() => expect(historySpy).toHaveBeenLastCalledWith(expect.objectContaining({ ticker: undefined }), expect.anything()));
    expect(await screen.findByText("No research runs yet")).toBeInTheDocument();
  });
});

describe("RecentRunsMenu -- opening a run", () => {
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

  function mockRunWithStatus(status: (typeof cases)[number][0]) {
    vi.spyOn(client, "getResearchHistory").mockResolvedValue({
      status: "ok",
      items: [makeRunRecord({ run_id: `run-${status}`, ticker: status.toUpperCase(), status })],
      next_cursor: null,
    });
  }

  it.each(cases)("opens a %s run on %s by mouse", async (status, destination) => {
    mockRunWithStatus(status);
    renderMenu();
    openMenu();
    const link = await screen.findByRole("link", { name: new RegExp(status.toUpperCase()) });
    expect(link).toHaveAttribute("href", `/runs/run-${status}/${destination}`);
    fireEvent.click(link);
    expect(await screen.findByText(`OPENED_${destination.toUpperCase()}_RUN`)).toBeInTheDocument();
  });

  it.each(cases)("opens a %s run on %s by keyboard", async (status, destination) => {
    const user = userEvent.setup();
    mockRunWithStatus(status);
    renderMenu();
    await user.click(screen.getByRole("button", { name: /recent runs/i }));
    const link = await screen.findByRole("link", { name: new RegExp(status.toUpperCase()) });
    link.focus();
    await user.keyboard("{Enter}");
    expect(await screen.findByText(`OPENED_${destination.toUpperCase()}_RUN`)).toBeInTheDocument();
  });
});

describe("RecentRunsMenu -- locked while a run is being started", () => {
  afterEach(() => {
    vi.restoreAllMocks();
  });

  function renderLockable(locked: boolean) {
    const tree = (isLocked: boolean) => (
      <MemoryRouter>
        <RecentRunsMenu locked={isLocked} />
      </MemoryRouter>
    );
    const view = render(tree(locked));
    return { rerenderLocked: (isLocked: boolean) => view.rerender(tree(isLocked)) };
  }

  it("cannot be opened", () => {
    const historySpy = vi.spyOn(client, "getResearchHistory");
    renderLockable(true);
    const button = screen.getByRole("button", { name: /recent runs/i });
    expect(button).toBeDisabled();
    fireEvent.click(button);
    expect(screen.queryByRole("region", { name: /recent runs/i })).not.toBeInTheDocument();
    expect(historySpy).not.toHaveBeenCalled();
  });

  it("closes an open menu when it becomes locked, and stays closed once unlocked again", async () => {
    vi.spyOn(client, "getResearchHistory").mockResolvedValue({ status: "ok", items: [], next_cursor: null });
    const { rerenderLocked } = renderLockable(false);
    openMenu();
    expect(await screen.findByRole("region", { name: /recent runs/i })).toBeInTheDocument();

    rerenderLocked(true);
    expect(screen.queryByRole("region", { name: /recent runs/i })).not.toBeInTheDocument();

    // A failed start unlocks it: it must not pop back open by itself.
    rerenderLocked(false);
    expect(screen.queryByRole("region", { name: /recent runs/i })).not.toBeInTheDocument();
    expect(screen.getByRole("button", { name: /recent runs/i })).toHaveAttribute("aria-expanded", "false");
  });
});
