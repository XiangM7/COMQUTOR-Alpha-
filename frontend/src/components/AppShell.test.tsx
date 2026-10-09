import { render, screen, within } from "@testing-library/react";
import type { ReactNode } from "react";
import { MemoryRouter } from "react-router-dom";
import { describe, expect, it } from "vitest";
import { ReadinessContext, type ReadinessState } from "../hooks/useReadiness";
import { AppShell } from "./AppShell";

// Product Demo Hardening Phase 2C (P1-3): a single, stable, global
// research-only positioning statement, visible without opening a tooltip or
// documentation page, on every page AppShell wraps (the Research landing
// page and the full result flow alike).

const BANNED_RECOMMENDATION_WORDS = ["guaranteed", "risk-free", "should invest", " buy ", " sell "];

function renderShell(
  children: ReactNode = <p>page content</p>,
  { path = "/research", readiness }: { path?: string; readiness?: ReadinessState } = {}
) {
  const shell = (
    <MemoryRouter initialEntries={[path]}>
      <AppShell>{children}</AppShell>
    </MemoryRouter>
  );
  return render(readiness ? <ReadinessContext.Provider value={readiness}>{shell}</ReadinessContext.Provider> : shell);
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

  it("renders the brand in the primary navigation alongside the footer disclaimer", () => {
    renderShell();
    const nav = screen.getByRole("navigation", { name: "Primary" });
    expect(within(nav).getByRole("link", { name: "COMQUTOR Alpha" })).toHaveAttribute("href", "/research");
  });

  it("renders page content passed as children unchanged", () => {
    renderShell(<p>Unique marker content</p>);
    expect(screen.getByText("Unique marker content")).toBeInTheDocument();
  });
});

describe("AppShell primary navigation", () => {
  it("links to Research and Operator", () => {
    renderShell();
    const nav = screen.getByRole("navigation", { name: "Primary" });
    expect(within(nav).getByRole("link", { name: "Research" })).toHaveAttribute("href", "/research");
    expect(within(nav).getByRole("link", { name: "Operator" })).toHaveAttribute("href", "/operator");
  });

  it("marks Research as the current page on /research", () => {
    renderShell(undefined, { path: "/research" });
    const nav = screen.getByRole("navigation", { name: "Primary" });
    expect(within(nav).getByRole("link", { name: "Research" })).toHaveAttribute("aria-current", "page");
    expect(within(nav).getByRole("link", { name: "Operator" })).not.toHaveAttribute("aria-current");
  });

  it("marks Operator as the current page on /operator", () => {
    renderShell(undefined, { path: "/operator" });
    const nav = screen.getByRole("navigation", { name: "Primary" });
    expect(within(nav).getByRole("link", { name: "Operator" })).toHaveAttribute("aria-current", "page");
    expect(within(nav).getByRole("link", { name: "Research" })).not.toHaveAttribute("aria-current");
  });

  it("keeps Research highlighted (without claiming the exact page) inside a run", () => {
    renderShell(undefined, { path: "/runs/run-abc/structure" });
    const nav = screen.getByRole("navigation", { name: "Primary" });
    const research = within(nav).getByRole("link", { name: "Research" });
    expect(research).toHaveClass("app-nav-link-active");
    expect(research).not.toHaveAttribute("aria-current");
  });
});

describe("AppShell server status", () => {
  it("says it is checking until readiness is known", () => {
    renderShell();
    expect(screen.getByRole("status")).toHaveTextContent("Checking server status…");
  });

  it("shows the server summary from the shared readiness state", () => {
    renderShell(undefined, {
      readiness: {
        readiness: {
          status: "ready",
          database: "ready",
          job_manager: "ready",
          real_execution: "configured",
          live_semantic_pipeline: "ready",
        },
        errorMessage: null,
      },
    });
    expect(screen.getByRole("status")).toHaveTextContent("Server ready, live research configured");
  });

  it("shows a short label in the bar and keeps the full error message as its tooltip", () => {
    renderShell(undefined, {
      readiness: { readiness: null, errorMessage: "Could not reach the COMQUTOR API. Check that it is running." },
    });
    const status = screen.getByRole("status");
    expect(status).toHaveTextContent("Server status unavailable");
    expect(status).toHaveAttribute("title", "Could not reach the COMQUTOR API. Check that it is running.");
  });

  it("warns when the live semantic pipeline is not ready", () => {
    renderShell(undefined, {
      readiness: {
        readiness: {
          status: "ready",
          database: "ready",
          job_manager: "ready",
          real_execution: "configured",
          live_semantic_pipeline: "not_ready",
        },
        errorMessage: null,
      },
    });
    expect(screen.getByRole("status")).toHaveTextContent(/live semantic pipeline not ready/i);
  });
});
