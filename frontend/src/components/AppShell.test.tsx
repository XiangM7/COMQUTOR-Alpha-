import { render, screen } from "@testing-library/react";
import type { ReactNode } from "react";
import { MemoryRouter } from "react-router-dom";
import { describe, expect, it } from "vitest";
import { AppShell } from "./AppShell";

// Product Demo Hardening Phase 2C (P1-3): a single, stable, global
// research-only positioning statement, visible without opening a tooltip or
// documentation page, on every page AppShell wraps (the Research landing
// page and the full result flow alike).

const BANNED_RECOMMENDATION_WORDS = ["guaranteed", "risk-free", "should invest", " buy ", " sell "];

function renderShell(children: ReactNode = <p>page content</p>) {
  return render(
    <MemoryRouter>
      <AppShell>{children}</AppShell>
    </MemoryRouter>
  );
}

describe("AppShell", () => {
  it("shows a research-only, not-financial-advice positioning statement", () => {
    renderShell();
    expect(screen.getByText("Research analysis only — not financial advice.")).toBeInTheDocument();
  });

  it("communicates explicit not-financial-advice meaning, not just a vague tagline", () => {
    renderShell();
    const disclaimer = screen.getByText(/not financial advice/i);
    expect(disclaimer.textContent?.toLowerCase()).toContain("not financial advice");
  });

  it("renders the disclaimer as plain readable text, not color-only, on any wrapped page", () => {
    renderShell(<p>Some arbitrary page content</p>);
    const disclaimer = screen.getByText("Research analysis only — not financial advice.");
    // A real DOM text node -- readable independent of any color/background styling.
    expect(disclaimer.tagName).toBe("P");
    expect(disclaimer.textContent).not.toHaveLength(0);
  });

  it("contains no forbidden recommendation-style product-language wording", () => {
    renderShell();
    const disclaimer = screen.getByText(/not financial advice/i);
    const text = ` ${disclaimer.textContent?.toLowerCase() ?? ""} `;
    for (const forbidden of BANNED_RECOMMENDATION_WORDS) {
      expect(text).not.toContain(forbidden);
    }
  });

  it("still renders the existing header brand and tagline alongside the new footer disclaimer", () => {
    renderShell();
    expect(screen.getByText("COMQUTOR Alpha")).toBeInTheDocument();
    expect(screen.getByText("Structured research, not a stock tip.")).toBeInTheDocument();
  });

  it("renders page content passed as children unchanged", () => {
    renderShell(<p>Unique marker content</p>);
    expect(screen.getByText("Unique marker content")).toBeInTheDocument();
  });
});
