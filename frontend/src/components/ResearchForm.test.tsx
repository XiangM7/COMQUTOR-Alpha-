import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { describe, expect, it, vi } from "vitest";
import { ResearchForm } from "./ResearchForm";

function localTodayIso(): string {
  const now = new Date();
  const month = String(now.getMonth() + 1).padStart(2, "0");
  const day = String(now.getDate()).padStart(2, "0");
  return `${now.getFullYear()}-${month}-${day}`;
}

describe("ResearchForm", () => {
  it("defaults to all four analysts selected, in the product display order", () => {
    render(<ResearchForm isSubmitting={false} onSubmit={vi.fn()} />);
    const checkboxes = screen.getAllByRole("checkbox");
    expect(checkboxes).toHaveLength(4);
    for (const label of ["Market", "Sentiment", "News", "Fundamentals"]) {
      expect(screen.getByLabelText(label)).toBeChecked();
    }
    const labels = checkboxes.map((box) => box.closest("label")?.textContent?.trim());
    expect(labels).toEqual(["Market", "Sentiment", "News", "Fundamentals"]);
  });

  it("exposes exactly three user input categories: ticker, date, analysts", () => {
    const { container } = render(<ResearchForm isSubmitting={false} onSubmit={vi.fn()} />);
    expect(screen.getByLabelText(/ticker/i)).toBeInTheDocument();
    expect(screen.getByLabelText(/analysis date/i)).toBeInTheDocument();
    expect(screen.getAllByRole("checkbox")).toHaveLength(4);
    // No Advanced options, no force refresh, no provider/model/key inputs.
    expect(container.querySelector("details")).toBeNull();
    expect(screen.queryByText(/advanced options/i)).toBeNull();
    expect(screen.queryByLabelText(/force refresh/i)).toBeNull();
    const inputs = Array.from(container.querySelectorAll("input"));
    expect(inputs).toHaveLength(6); // ticker + date + 4 analyst checkboxes
  });

  it("defaults the analysis date to today", () => {
    render(<ResearchForm isSubmitting={false} onSubmit={vi.fn()} />);
    expect(screen.getByLabelText(/analysis date/i)).toHaveValue(localTodayIso());
  });

  it("rejects an analysis date later than today", async () => {
    const user = userEvent.setup();
    const onSubmit = vi.fn();
    render(<ResearchForm isSubmitting={false} onSubmit={onSubmit} />);

    const dateInput = screen.getByLabelText(/analysis date/i);
    // fireEvent-style direct value set: the max attribute blocks typing a
    // future date through the picker, but a manual value must still be
    // validated client-side.
    await user.clear(dateInput);
    await user.type(dateInput, "2099-01-01");
    await user.type(screen.getByLabelText(/ticker/i), "NVDA");
    await user.click(screen.getByRole("button", { name: /start research/i }));

    expect(onSubmit).not.toHaveBeenCalled();
    expect(screen.getByRole("alert")).toHaveTextContent(/cannot be later than today/i);
  });

  it("normalizes the ticker (trim + uppercase) before submitting", async () => {
    const user = userEvent.setup();
    const onSubmit = vi.fn();
    render(<ResearchForm isSubmitting={false} onSubmit={onSubmit} />);

    await user.type(screen.getByLabelText(/ticker/i), "  nvda  ");
    await user.click(screen.getByRole("button", { name: /start research/i }));

    expect(onSubmit).toHaveBeenCalledWith(
      expect.objectContaining({ ticker: "NVDA" })
    );
  });

  it("requires at least one analyst to be selected", async () => {
    const user = userEvent.setup();
    const onSubmit = vi.fn();
    render(<ResearchForm isSubmitting={false} onSubmit={onSubmit} />);

    for (const label of ["Market", "Sentiment", "News", "Fundamentals"]) {
      await user.click(screen.getByLabelText(label));
    }
    await user.type(screen.getByLabelText(/ticker/i), "NVDA");
    await user.click(screen.getByRole("button", { name: /start research/i }));

    expect(onSubmit).not.toHaveBeenCalled();
    expect(screen.getByRole("alert")).toHaveTextContent(/select at least one analyst/i);
  });

  it("submits exactly ticker/analysis_date/selected_analysts and nothing else", async () => {
    const user = userEvent.setup();
    const onSubmit = vi.fn();
    render(<ResearchForm isSubmitting={false} onSubmit={onSubmit} />);

    await user.type(screen.getByLabelText(/ticker/i), "NVDA");
    await user.click(screen.getByRole("button", { name: /start research/i }));

    const request = onSubmit.mock.calls[0]?.[0] as Record<string, unknown>;
    expect(Object.keys(request).sort()).toEqual([
      "analysis_date",
      "selected_analysts",
      "ticker",
    ]);
    expect(request.selected_analysts).toEqual([
      "market",
      "sentiment",
      "news",
      "fundamentals",
    ]);
    for (const forbidden of [
      "provider",
      "model",
      "config",
      "api_key",
      "force_refresh",
      "allow_real_tradingagents_run",
      "offline_raw_agent_outputs",
      "llm_provider",
      "quick_think_llm",
      "deep_think_llm",
      "backend_url",
      "output_language",
      "research_depth",
      "max_debate_rounds",
      "max_risk_discuss_rounds",
      "reasoning_effort",
    ]) {
      expect(request).not.toHaveProperty(forbidden);
    }
  });

  it("deduplicates and canonically orders the analyst selection", async () => {
    const user = userEvent.setup();
    const onSubmit = vi.fn();
    render(<ResearchForm isSubmitting={false} onSubmit={onSubmit} />);

    // Toggle a couple off and back on in a scrambled order -- the payload
    // must still come out canonical.
    await user.click(screen.getByLabelText("Market"));
    await user.click(screen.getByLabelText("News"));
    await user.click(screen.getByLabelText("News"));
    await user.click(screen.getByLabelText("Market"));
    await user.type(screen.getByLabelText(/ticker/i), "NVDA");
    await user.click(screen.getByRole("button", { name: /start research/i }));

    const request = onSubmit.mock.calls[0]?.[0] as { selected_analysts: string[] };
    expect(request.selected_analysts).toEqual(["market", "sentiment", "news", "fundamentals"]);
  });

  it("disables the submit button while a submission is in flight", () => {
    render(<ResearchForm isSubmitting onSubmit={vi.fn()} />);
    expect(screen.getByRole("button", { name: /submitting/i })).toBeDisabled();
  });

  // Live-research readiness guard (operational safety fix): the two fresh
  // live runs (NVDA/SNDK) that recorded zero Alpha activation happened
  // because a live submission was allowed through while Week2's semantic
  // pipeline was not ready. The form must never let that happen again.
  it("disables Start research and shows the reason when disabledReason is set", () => {
    render(
      <ResearchForm
        isSubmitting={false}
        onSubmit={vi.fn()}
        disabledReason="Live semantic pipeline not ready. Live research was not started."
      />
    );
    expect(screen.getByRole("button", { name: /start research/i })).toBeDisabled();
    expect(screen.getByText(/live semantic pipeline not ready/i)).toBeInTheDocument();
  });

  it("does not call onSubmit when disabledReason is set and the form is submitted", async () => {
    const user = userEvent.setup();
    const onSubmit = vi.fn();
    render(
      <ResearchForm
        isSubmitting={false}
        onSubmit={onSubmit}
        disabledReason="Live semantic pipeline not ready."
      />
    );
    await user.type(screen.getByLabelText(/ticker/i), "NVDA");
    // The button itself is disabled (already covered above); this proves
    // the handler's own early-return guard also blocks a submit that
    // somehow still reaches it (e.g. pressing Enter in a text field).
    const form = screen.getByRole("button", { name: /start research/i }).closest("form")!;
    form.requestSubmit ? form.requestSubmit() : form.dispatchEvent(new Event("submit", { cancelable: true, bubbles: true }));
    expect(onSubmit).not.toHaveBeenCalled();
  });

  it("re-enables the submit button once disabledReason clears", () => {
    const { rerender } = render(
      <ResearchForm isSubmitting={false} onSubmit={vi.fn()} disabledReason="Live semantic pipeline not ready." />
    );
    expect(screen.getByRole("button", { name: /start research/i })).toBeDisabled();
    rerender(<ResearchForm isSubmitting={false} onSubmit={vi.fn()} disabledReason={null} />);
    expect(screen.getByRole("button", { name: /start research/i })).not.toBeDisabled();
  });
});
