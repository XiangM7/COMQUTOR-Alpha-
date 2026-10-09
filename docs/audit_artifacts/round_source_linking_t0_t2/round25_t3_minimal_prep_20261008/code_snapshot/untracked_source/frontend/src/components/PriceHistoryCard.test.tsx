import { fireEvent, render, screen, waitFor, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { afterEach, describe, expect, it, vi } from "vitest";
import { makeSamplePriceHistory } from "../utils/priceHistory";
import { PriceHistoryCard } from "./PriceHistoryCard";

const HISTORY = makeSamplePriceHistory("NVDA", "2026-10-07");

function renderCard() {
  return render(
    <div>
      <button type="button">before</button>
      <PriceHistoryCard history={HISTORY} />
    </div>
  );
}

async function openSheet() {
  const user = userEvent.setup();
  renderCard();
  const card = screen.getByRole("button", { name: "Open NVDA price history" });
  await user.click(card);
  return { user, card, dialog: await screen.findByRole("dialog", { name: "NVDA price history" }) };
}

describe("PriceHistoryCard", () => {
  it("shows the 3-month summary and says the prices are sample data", () => {
    renderCard();
    const card = screen.getByRole("button", { name: "Open NVDA price history" });
    expect(card).toHaveAttribute("aria-haspopup", "dialog");
    expect(card).toHaveTextContent("Price history, 3 months · Sample data");
    const last = HISTORY.candles.at(-1)!;
    expect(card).toHaveTextContent(last.close.toFixed(2));
    expect(card).toHaveTextContent(/over 3 months/);
  });

  it("draws the mini chart as hidden decoration with one candle per day", () => {
    renderCard();
    const card = screen.getByRole("button", { name: "Open NVDA price history" });
    const svg = card.querySelector("svg.candle-svg");
    expect(svg).toHaveAttribute("aria-hidden", "true");
    expect(svg?.querySelectorAll(".candle-body")).toHaveLength(63);
  });

  it("marks up days and down days with different shapes, not only colors", () => {
    renderCard();
    const bodies = Array.from(screen.getByRole("button", { name: /price history/i }).querySelectorAll(".candle-body"));
    expect(bodies.some((body) => body.classList.contains("candle-body-up"))).toBe(true);
    expect(bodies.some((body) => body.classList.contains("candle-body-down"))).toBe(true);
  });
});

describe("PriceHistorySheet", () => {
  afterEach(() => {
    vi.unstubAllGlobals();
  });

  it("opens as a modal dialog with focus inside it", async () => {
    const { dialog } = await openSheet();
    expect(dialog).toHaveAttribute("aria-modal", "true");
    expect(dialog.contains(document.activeElement)).toBe(true);
    expect(within(dialog).getByRole("button", { name: "Close price history" })).toHaveFocus();
  });

  it("reads out the latest close by default, and says it is the close", async () => {
    const { dialog } = await openSheet();
    const last = HISTORY.candles.at(-1)!;
    expect(within(dialog).getByText(last.close.toFixed(2))).toBeInTheDocument();
    expect(within(dialog).getByText(/^Close, /)).toBeInTheDocument();
    expect(within(dialog).getByText(`Open ${last.open.toFixed(2)}`)).toBeInTheDocument();
    expect(within(dialog).getByText(`High ${last.high.toFixed(2)}`)).toBeInTheDocument();
  });

  it("states that nothing after the analysis date is drawn, and that the data is a sample", async () => {
    const { dialog } = await openSheet();
    expect(within(dialog).getByText(/nothing after it can influence the read/i)).toBeInTheDocument();
    expect(within(dialog).getByText(/sample data, not real prices/i)).toBeInTheDocument();
    expect(within(dialog).getByText("Analysis date")).toBeInTheDocument();
  });

  it("switches between 1M, 3M and 6M", async () => {
    const { user, dialog } = await openSheet();
    const candles = () => dialog.querySelectorAll(".candle-body").length;
    expect(within(dialog).getByRole("button", { name: "3M" })).toHaveAttribute("aria-pressed", "true");
    expect(candles()).toBe(63);

    await user.click(within(dialog).getByRole("button", { name: "1M" }));
    expect(within(dialog).getByRole("button", { name: "1M" })).toHaveAttribute("aria-pressed", "true");
    expect(within(dialog).getByRole("button", { name: "3M" })).toHaveAttribute("aria-pressed", "false");
    expect(candles()).toBe(22);

    await user.click(within(dialog).getByRole("button", { name: "6M" }));
    expect(candles()).toBe(126);
  });

  it("reads out the day under the pointer and goes back to the latest close when it leaves", async () => {
    // jsdom has no PointerEvent, so events would carry no coordinates.
    vi.stubGlobal("PointerEvent", class extends MouseEvent {});
    const { dialog } = await openSheet();
    const chart = dialog.querySelector<HTMLElement>(".price-chart")!;
    chart.getBoundingClientRect = () => new DOMRect(0, 0, 630, 400);
    const candles = HISTORY.candles.slice(-63);

    // Pointer at 50% of the width: the middle candle of 63.
    fireEvent.pointerMove(chart, { clientX: 315, clientY: 100 });
    const hovered = candles[31]!;
    expect(within(dialog).getByText(hovered.close.toFixed(2))).toBeInTheDocument();
    expect(within(dialog).queryByText(/^Close, /)).toBeNull();
    expect(dialog.querySelector(".price-chart-cross")).not.toBeNull();

    fireEvent.pointerLeave(chart);
    expect(within(dialog).getByText(/^Close, /)).toBeInTheDocument();
    expect(dialog.querySelector(".price-chart-cross")).toBeNull();
  });

  it("closes on Escape and gives focus back to the card", async () => {
    const { user, card } = await openSheet();
    await user.keyboard("{Escape}");
    await waitFor(() => expect(screen.queryByRole("dialog")).toBeNull());
    expect(card).toHaveFocus();
  });

  it("closes with the close button", async () => {
    const { user, dialog, card } = await openSheet();
    await user.click(within(dialog).getByRole("button", { name: "Close price history" }));
    await waitFor(() => expect(screen.queryByRole("dialog")).toBeNull());
    expect(card).toHaveFocus();
  });

  it("closes when the dimmed page behind it is clicked", async () => {
    const { user } = await openSheet();
    await user.click(document.querySelector(".price-sheet-backdrop")!);
    await waitFor(() => expect(screen.queryByRole("dialog")).toBeNull());
  });

  it("keeps Tab inside the dialog", async () => {
    const { user, dialog } = await openSheet();
    for (let step = 0; step < 12; step += 1) {
      await user.tab();
      expect(dialog.contains(document.activeElement)).toBe(true);
    }
    for (let step = 0; step < 12; step += 1) {
      await user.tab({ shift: true });
      expect(dialog.contains(document.activeElement)).toBe(true);
    }
  });

  it("locks page scrolling while open and releases it after", async () => {
    const { user } = await openSheet();
    expect(document.body.style.overflow).toBe("hidden");
    await user.keyboard("{Escape}");
    await waitFor(() => expect(screen.queryByRole("dialog")).toBeNull());
    expect(document.body.style.overflow).not.toBe("hidden");
  });
});
