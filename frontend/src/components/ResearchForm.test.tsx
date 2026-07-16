import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { describe, expect, it, vi } from "vitest";
import { ResearchForm } from "./ResearchForm";

describe("ResearchForm", () => {
  it("defaults to all four real-mode analysts selected", () => {
    render(<ResearchForm isSubmitting={false} onSubmit={vi.fn()} />);
    for (const label of ["Market", "News", "Fundamentals", "Sentiment"]) {
      expect(screen.getByLabelText(label)).toBeChecked();
    }
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

    for (const label of ["Market", "News", "Fundamentals", "Sentiment"]) {
      await user.click(screen.getByLabelText(label));
    }
    await user.type(screen.getByLabelText(/ticker/i), "NVDA");
    await user.click(screen.getByRole("button", { name: /start research/i }));

    expect(onSubmit).not.toHaveBeenCalled();
    expect(screen.getByRole("alert")).toHaveTextContent(/select at least one analyst/i);
  });

  it("never sends a provider/model/config/API key field", async () => {
    const user = userEvent.setup();
    const onSubmit = vi.fn();
    render(<ResearchForm isSubmitting={false} onSubmit={onSubmit} />);

    await user.type(screen.getByLabelText(/ticker/i), "NVDA");
    await user.click(screen.getByRole("button", { name: /start research/i }));

    const request = onSubmit.mock.calls[0]?.[0] as Record<string, unknown>;
    for (const forbidden of [
      "provider",
      "model",
      "config",
      "api_key",
      "allow_real_tradingagents_run",
      "offline_raw_agent_outputs",
    ]) {
      expect(request).not.toHaveProperty(forbidden);
    }
  });

  it("disables the submit button while a submission is in flight", () => {
    render(<ResearchForm isSubmitting onSubmit={vi.fn()} />);
    expect(screen.getByRole("button", { name: /submitting/i })).toBeDisabled();
  });

  it("puts force_refresh only in the advanced-options details element", () => {
    render(<ResearchForm isSubmitting={false} onSubmit={vi.fn()} />);
    const forceRefreshCheckbox = screen.getByLabelText(/force refresh/i);
    expect(forceRefreshCheckbox.closest("details")).not.toBeNull();
  });
});
