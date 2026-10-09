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
  it("exposes exactly one user input: the ticker", () => {
    const { container } = render(<ResearchForm isSubmitting={false} onSubmit={vi.fn()} />);
    expect(screen.getByLabelText(/ticker/i)).toBeInTheDocument();
    // No date picker, no analyst selection.
    expect(screen.queryByLabelText(/analysis date/i)).toBeNull();
    expect(screen.queryByRole("checkbox")).toBeNull();
    expect(screen.queryByText(/analysts team/i)).toBeNull();
    // No Advanced options, no force refresh, no provider/model/key inputs.
    expect(container.querySelector("details")).toBeNull();
    expect(screen.queryByText(/advanced options/i)).toBeNull();
    expect(screen.queryByLabelText(/force refresh/i)).toBeNull();
    expect(container.querySelectorAll("input")).toHaveLength(1);
  });

  it("disables Start research until a ticker is entered", async () => {
    const user = userEvent.setup();
    render(<ResearchForm isSubmitting={false} onSubmit={vi.fn()} />);
    const start = screen.getByRole("button", { name: /start research/i });
    expect(start).toBeDisabled();

    await user.type(screen.getByLabelText(/ticker/i), "   ");
    expect(start).toBeDisabled();

    await user.type(screen.getByLabelText(/ticker/i), "nvda");
    expect(start).toBeEnabled();
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

  it("submits with Enter from the ticker field", async () => {
    const user = userEvent.setup();
    const onSubmit = vi.fn();
    render(<ResearchForm isSubmitting={false} onSubmit={onSubmit} />);

    await user.type(screen.getByLabelText(/ticker/i), "amd{Enter}");

    expect(onSubmit).toHaveBeenCalledTimes(1);
    expect(onSubmit).toHaveBeenCalledWith(expect.objectContaining({ ticker: "AMD" }));
  });

  it("does not submit on Enter while the ticker is empty", async () => {
    const user = userEvent.setup();
    const onSubmit = vi.fn();
    render(<ResearchForm isSubmitting={false} onSubmit={onSubmit} />);

    await user.type(screen.getByLabelText(/ticker/i), "{Enter}");

    expect(onSubmit).not.toHaveBeenCalled();
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

  it("always sends the full analyst team in the frozen product order", async () => {
    const user = userEvent.setup();
    const onSubmit = vi.fn();
    render(<ResearchForm isSubmitting={false} onSubmit={onSubmit} />);

    await user.type(screen.getByLabelText(/ticker/i), "NVDA");
    await user.click(screen.getByRole("button", { name: /start research/i }));

    const request = onSubmit.mock.calls[0]?.[0] as { selected_analysts: string[] };
    expect(request.selected_analysts).toEqual(["market", "sentiment", "news", "fundamentals"]);
  });

  it("always sends today's local date explicitly, never leaving it to a server default", async () => {
    const user = userEvent.setup();
    const onSubmit = vi.fn();
    render(<ResearchForm isSubmitting={false} onSubmit={onSubmit} />);

    await user.type(screen.getByLabelText(/ticker/i), "NVDA");
    await user.click(screen.getByRole("button", { name: /start research/i }));

    const request = onSubmit.mock.calls[0]?.[0] as { analysis_date: string };
    expect(request.analysis_date).toBe(localTodayIso());
  });

  it("shows Starting… on a busy, disabled button while a submission is in flight", () => {
    render(<ResearchForm isSubmitting onSubmit={vi.fn()} />);
    const button = screen.getByRole("button", { name: "Starting…" });
    expect(button).toBeDisabled();
    expect(button).toHaveAttribute("aria-busy", "true");
    expect(button).toHaveClass("cta-button-busy");
    expect(button).toHaveAttribute("data-transition", "cta");
  });

  it("swaps the input for the ticker as plain text while submitting, so it can fly into the next page", async () => {
    const user = userEvent.setup();
    const { rerender } = render(<ResearchForm isSubmitting={false} onSubmit={vi.fn()} />);
    await user.type(screen.getByLabelText(/ticker/i), "  nvda ");

    rerender(<ResearchForm isSubmitting onSubmit={vi.fn()} />);

    expect(screen.queryByRole("textbox")).toBeNull();
    const text = document.querySelector('[data-transition="ticker"]');
    expect(text).toHaveTextContent("NVDA");

    // A failed start brings the input back with what was typed.
    rerender(<ResearchForm isSubmitting={false} onSubmit={vi.fn()} />);
    expect(screen.getByRole("textbox")).toHaveValue("  nvda ");
  });

  it("ignores a second submit while one is in flight", () => {
    const onSubmit = vi.fn();
    render(<ResearchForm isSubmitting onSubmit={onSubmit} />);
    const form = document.querySelector("form")!;
    if (form.requestSubmit) {
      form.requestSubmit();
    } else {
      form.dispatchEvent(new Event("submit", { cancelable: true, bubbles: true }));
    }
    expect(onSubmit).not.toHaveBeenCalled();
  });

  it("renders the leading action before Start research, outside the ticker form", () => {
    render(
      <ResearchForm isSubmitting={false} onSubmit={vi.fn()} leadingAction={<button type="button">Recent runs</button>} />
    );
    const recent = screen.getByRole("button", { name: "Recent runs" });
    const start = screen.getByRole("button", { name: /start research/i });
    expect(recent.compareDocumentPosition(start) & Node.DOCUMENT_POSITION_FOLLOWING).toBeTruthy();
    expect(recent.closest("form")).toBeNull();
  });

  // Live-research readiness guard (operational safety fix): the two fresh
  // live runs (NVDA/SNDK) that recorded zero Alpha activation happened
  // because a live submission was allowed through while Week2's semantic
  // pipeline was not ready. The form must never let that happen again.
  it("disables Start research and shows the reason when disabledReason is set", async () => {
    const user = userEvent.setup();
    render(
      <ResearchForm
        isSubmitting={false}
        onSubmit={vi.fn()}
        disabledReason="Live semantic pipeline not ready. Live research was not started."
      />
    );
    await user.type(screen.getByLabelText(/ticker/i), "NVDA");
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
    const form = screen.getByLabelText(/ticker/i).closest("form")!;
    if (form.requestSubmit) {
      form.requestSubmit();
    } else {
      form.dispatchEvent(new Event("submit", { cancelable: true, bubbles: true }));
    }
    expect(onSubmit).not.toHaveBeenCalled();
  });

  it("re-enables the submit button once disabledReason clears", async () => {
    const user = userEvent.setup();
    const { rerender } = render(
      <ResearchForm isSubmitting={false} onSubmit={vi.fn()} disabledReason="Live semantic pipeline not ready." />
    );
    await user.type(screen.getByLabelText(/ticker/i), "NVDA");
    expect(screen.getByRole("button", { name: /start research/i })).toBeDisabled();
    rerender(<ResearchForm isSubmitting={false} onSubmit={vi.fn()} disabledReason={null} />);
    expect(screen.getByRole("button", { name: /start research/i })).not.toBeDisabled();
  });
});
