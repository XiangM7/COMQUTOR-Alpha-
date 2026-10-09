import { render, screen } from "@testing-library/react";
import { describe, expect, it } from "vitest";
import type { ExternalSource } from "../api/types";
import { ExternalSourceDisplay } from "./ExternalSourceDisplay";

// John MVP Final Gap Closure -- Structured External Source Traceability.

function makeSource(overrides: Partial<ExternalSource> = {}): ExternalSource {
  return {
    source_id: "src_abc123",
    source_type: "news",
    name: "Barron's",
    title: "Why Stocks Are Loving the Fed's Rate Hike",
    url: "https://barrons.com/articles/x",
    published_at: "2026-09-17T10:00:00",
    retrieved_at: "2026-09-17T22:00:00Z",
    external_record_id: null,
    locator: null,
    provider: "yfinance",
    metadata_status: "TRACEABLE",
    ...overrides,
  };
}

describe("ExternalSourceDisplay", () => {
  it("renders the genuine publisher, title, and date for a TRACEABLE source", () => {
    render(<ExternalSourceDisplay source={makeSource()} status="TRACEABLE" />);
    expect(screen.getByText("Barron's")).toBeInTheDocument();
    expect(screen.getByText("Why Stocks Are Loving the Fed's Rate Hike")).toBeInTheDocument();
    expect(screen.getByText("2026-09-17T10:00:00")).toBeInTheDocument();
  });

  it("renders a clickable external link when a genuine URL exists", () => {
    render(<ExternalSourceDisplay source={makeSource()} status="TRACEABLE" />);
    const link = screen.getByRole("link", { name: /open source/i });
    expect(link).toHaveAttribute("href", "https://barrons.com/articles/x");
    expect(link).toHaveAttribute("target", "_blank");
    expect(link).toHaveAttribute("rel", expect.stringContaining("noopener"));
  });

  it("never renders a link when the source has no URL", () => {
    render(<ExternalSourceDisplay source={makeSource({ url: null })} status="PARTIAL" />);
    expect(screen.queryByRole("link")).not.toBeInTheDocument();
  });

  it("shows a partial-metadata note for PARTIAL status", () => {
    render(<ExternalSourceDisplay source={makeSource({ url: null })} status="PARTIAL" />);
    expect(screen.getByText(/some source details are not available/i)).toBeInTheDocument();
  });

  it("shows an honest unavailable state, never a fabricated source, when status is UNAVAILABLE", () => {
    render(<ExternalSourceDisplay source={null} status="UNAVAILABLE" />);
    expect(screen.getByText(/external source metadata is not available/i)).toBeInTheDocument();
    expect(screen.queryByRole("link")).not.toBeInTheDocument();
  });

  it("shows the unavailable state when status is undefined (older response shape)", () => {
    render(<ExternalSourceDisplay source={undefined} status={undefined} />);
    expect(screen.getByText(/external source metadata is not available/i)).toBeInTheDocument();
  });

  it("shows the unavailable state if status says UNAVAILABLE even when a source object is somehow present", () => {
    // Defensive: status is the authority, never the mere presence of a
    // source object -- this can never happen from the real API, but the
    // component must not silently render a "source" whose own status says
    // it isn't one.
    render(<ExternalSourceDisplay source={makeSource()} status="UNAVAILABLE" />);
    expect(screen.getByText(/external source metadata is not available/i)).toBeInTheDocument();
  });

  it("only renders fields the source actually supplied -- never a fabricated placeholder for a missing field", () => {
    render(
      <ExternalSourceDisplay
        source={makeSource({ name: null, external_record_id: null, locator: null })}
        status="PARTIAL"
      />
    );
    expect(screen.queryByText("Publisher")).not.toBeInTheDocument();
    expect(screen.queryByText("Record")).not.toBeInTheDocument();
    expect(screen.queryByText("Locator")).not.toBeInTheDocument();
  });

  it("renders external_record_id and locator when present (e.g. a filing/dataset record)", () => {
    render(
      <ExternalSourceDisplay
        source={makeSource({ url: null, external_record_id: "CPIAUCSL", locator: "Table 2" })}
        status="PARTIAL"
      />
    );
    expect(screen.getByText("CPIAUCSL")).toBeInTheDocument();
    expect(screen.getByText("Table 2")).toBeInTheDocument();
  });

  // T1 source-linking chain (COMQUTOR Alpha next-round task, 2026-09-26):
  // linkedSource/sourceLinkStatus/contentSupportStatus are deliberately
  // separate from source/status above (the legacy title-match join).
  describe("linked source (ID-validated, T1 source-linking chain)", () => {
    it("renders nothing extra when no source reference was ever provided", () => {
      render(
        <ExternalSourceDisplay
          source={null}
          status="UNAVAILABLE"
          sourceLinkStatus="NOT_PROVIDED"
        />
      );
      expect(screen.queryByText(/linked source/i)).not.toBeInTheDocument();
    });

    it("renders the real excerpt and a pending-review support status for a VALID link", () => {
      render(
        <ExternalSourceDisplay
          source={null}
          status="UNAVAILABLE"
          sourceLinkStatus="VALID"
          contentSupportStatus="PENDING_REVIEW"
          linkedSource={makeSource({
            title: "NVDA Data Center Revenue Beats Estimates",
            excerpt: "NVDA reported record data center revenue this quarter.",
          })}
        />
      );
      expect(screen.getByText("NVDA Data Center Revenue Beats Estimates")).toBeInTheDocument();
      expect(
        screen.getByText("“NVDA reported record data center revenue this quarter.”")
      ).toBeInTheDocument();
      expect(screen.getByText(/support pending review/i)).toBeInTheDocument();
    });

    it("never renders an excerpt for a rejected/unresolved link status, only the reason", () => {
      render(
        <ExternalSourceDisplay
          source={null}
          status="UNAVAILABLE"
          sourceLinkStatus="UNKNOWN_ID"
          linkedSource={null}
        />
      );
      expect(screen.getByText(/source reference not recognized/i)).toBeInTheDocument();
      expect(screen.queryByText(/support pending review/i)).not.toBeInTheDocument();
    });

    it("reports a time-invalid link honestly instead of hiding it", () => {
      render(
        <ExternalSourceDisplay
          source={null}
          status="UNAVAILABLE"
          sourceLinkStatus="TIME_INVALID"
          linkedSource={null}
        />
      );
      expect(screen.getByText(/published after the evidence cutoff/i)).toBeInTheDocument();
    });

    it("a VALID link never implies support -- SUPPORTS is only shown when explicitly given", () => {
      render(
        <ExternalSourceDisplay
          source={null}
          status="UNAVAILABLE"
          sourceLinkStatus="VALID"
          contentSupportStatus="OPPOSES"
          linkedSource={makeSource({ excerpt: "Guidance was cut for the coming quarter." })}
        />
      );
      expect(screen.getByText(/opposes this claim/i)).toBeInTheDocument();
      expect(screen.queryByText(/supports this claim/i)).not.toBeInTheDocument();
    });
  });
});
