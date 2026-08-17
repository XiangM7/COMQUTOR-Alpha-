import { render, screen, waitFor, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { Link, MemoryRouter, Route, Routes } from "react-router-dom";
import { afterEach, describe, expect, it, vi } from "vitest";
import * as client from "../api/client";
import type { AlphaActivation, ConflictsResponse, StructureGraphResponse } from "../api/types";
import { StructureGraphPage } from "./StructureGraphPage";

// Sprint 1 (Run Identity Integrity and Complete Artifact Export),
// Track A1/frontend: regression tests for the SNDK/TSM stale-graph
// investigation. Confirms StructureGraphPage never continues to render a
// previous run's Structure Graph (including its own ticker-labeled node
// names, e.g. "TSM Revenue Growth") while a newly-selected run is still
// loading, and never renders a payload whose own embedded run_id disagrees
// with the currently-selected run.

function renderPage(runId: string) {
  return render(
    <MemoryRouter initialEntries={[`/runs/${runId}/graph`]}>
      <Routes>
        <Route path="/runs/:runId/graph" element={<StructureGraphPage />} />
      </Routes>
    </MemoryRouter>
  );
}

// A real client-side <Link> navigation (exactly what switching runs does
// in the actual app) between two runs, all inside one MemoryRouter
// instance -- unlike swapping <MemoryRouter initialEntries> across a
// rerender (which react-router does not treat as a navigation at all,
// since initialEntries is only consulted on first mount).
function renderWithRunSwitcher(firstRunId: string, secondRunId: string) {
  return render(
    <MemoryRouter initialEntries={[`/runs/${firstRunId}/graph`]}>
      <Routes>
        <Route
          path="/runs/:runId/graph"
          element={
            <>
              <Link to={`/runs/${secondRunId}/graph`}>switch-run</Link>
              <StructureGraphPage />
            </>
          }
        />
      </Routes>
    </MemoryRouter>
  );
}

function makeGraph(runId: string, ticker: string, nodeLabel: string): StructureGraphResponse {
  return {
    run_id: runId,
    ticker,
    status: "ok",
    schema_version: "week3.structure_graph.v2",
    graph_builder_version: "test.v1",
    activation_scorer_version: "test.v1",
    nodes: [
      {
        id: "revenue_growth",
        node_type: "factor",
        label: nodeLabel,
        canonical_factor: "Revenue Growth",
        original_labels: [nodeLabel],
        alpha_ids: [],
        ambiguous_alpha_ids: [],
        score: 1,
        claim_ids: [],
        source_agent_output_ids: [],
        agents: [],
        evidence: [],
      },
    ],
    edges: [],
    graph_metrics: {},
    graph_coherence: {},
    activation: {
      formula_version: "test.v1",
      weights: {},
      run_timestamp: null,
      as_of: null,
      alphas: [],
    },
    activation_versions: {},
    primary_activation_version: null,
    dominant_alphas: [],
    provenance: {},
  };
}

function makeConflicts(runId: string, ticker: string): ConflictsResponse {
  return {
    status: "ok",
    schema_version: "week4.alpha_conflicts.v1",
    formula_version: "test.v1",
    activation_formula_version: null,
    run_id: runId,
    ticker,
    conflicts: [],
    main_conflict: null,
    arbitration: {
      declared_pair_count: 0,
      admitted_count: 0,
      suppressed_count: 0,
      rejected_count: 0,
      candidate_evaluations: [],
    },
  };
}

function makeAlpha(overrides: Partial<AlphaActivation> = {}): AlphaActivation {
  return {
    alpha_id: "A101",
    alpha_name: "AI Expansion",
    activation_score: 60,
    status: "active",
    direction: "positive",
    components: {},
    evidence_count: 1,
    distinct_supporting_agents: 1,
    claim_ids: [],
    evidence: [],
    reason_codes: [],
    evidence_detail: [],
    formula_version: "activation.v2.evidence_local_structure.v1",
    uncapped_score: 60,
    eligible_cap: null,
    cap_was_binding: false,
    cap_reason_codes: [],
    binding_cap_reason_codes: [],
    unique_evidence_count: 1,
    ticker_specific_evidence_count: 1,
    local_edge_count: 0,
    regime_gate_passed: false,
    regime_gate_failures: [],
    ...overrides,
  };
}

afterEach(() => {
  vi.restoreAllMocks();
});

// The graph SVG truncates long node labels for display (a pre-existing,
// unrelated UI behavior), but always keeps the full label in the node's
// own `aria-label` attribute -- query that instead of visible text.
function hasNodeLabel(container: HTMLElement, label: string): boolean {
  return container.querySelector(`[aria-label*="${label}"]`) !== null;
}

describe("StructureGraphPage run switching", () => {
  it("never continues to display a previous run's graph while the newly-selected run is still loading", async () => {
    const user = userEvent.setup();
    let resolveTsm: (() => void) | undefined;
    let resolveSndk: ((value: StructureGraphResponse) => void) | undefined;

    const graphSpy = vi.spyOn(client, "getResearchGraph");
    graphSpy.mockImplementationOnce(
      () =>
        new Promise((resolve) => {
          resolveTsm = () => resolve(makeGraph("tsm-run", "TSM", "TSM Revenue Growth"));
        })
    );
    vi.spyOn(client, "getResearchConflicts").mockResolvedValue(makeConflicts("tsm-run", "TSM"));

    const { container } = renderWithRunSwitcher("tsm-run", "sndk-run");

    resolveTsm?.();
    await waitFor(() => expect(hasNodeLabel(container, "TSM Revenue Growth")).toBe(true));

    // Now switch to the SNDK run via a real client-side navigation. Its
    // own fetch is deliberately left pending (never resolved in this
    // test) to prove the TSM graph does not linger on screen during the
    // loading window.
    graphSpy.mockImplementationOnce(
      () =>
        new Promise((resolve) => {
          resolveSndk = resolve;
        })
    );
    vi.spyOn(client, "getResearchConflicts").mockResolvedValue(makeConflicts("sndk-run", "SNDK"));

    await user.click(screen.getByText("switch-run"));

    await waitFor(() => expect(hasNodeLabel(container, "TSM Revenue Growth")).toBe(false));
    void resolveSndk; // never resolved -- the point of this test
  });

  it("an out-of-order (late-resolving) previous request cannot overwrite the current run's graph", async () => {
    const user = userEvent.setup();
    const graphSpy = vi.spyOn(client, "getResearchGraph");
    let resolveFirst: ((value: StructureGraphResponse) => void) | undefined;
    graphSpy.mockImplementationOnce(
      () =>
        new Promise((resolve) => {
          resolveFirst = resolve;
        })
    );
    vi.spyOn(client, "getResearchConflicts").mockResolvedValue(makeConflicts("tsm-run", "TSM"));

    const { container } = renderWithRunSwitcher("tsm-run", "sndk-run");

    graphSpy.mockResolvedValueOnce(makeGraph("sndk-run", "SNDK", "SNDK Revenue Growth"));
    vi.spyOn(client, "getResearchConflicts").mockResolvedValue(makeConflicts("sndk-run", "SNDK"));
    await user.click(screen.getByText("switch-run"));

    await waitFor(() => expect(hasNodeLabel(container, "SNDK Revenue Growth")).toBe(true));

    // The first (TSM) request now finally resolves, after the SNDK run's
    // own data has already rendered -- it must never overwrite it.
    resolveFirst?.(makeGraph("tsm-run", "TSM", "TSM Revenue Growth"));
    await new Promise((r) => setTimeout(r, 0));
    expect(hasNodeLabel(container, "SNDK Revenue Growth")).toBe(true);
    expect(hasNodeLabel(container, "TSM Revenue Growth")).toBe(false);
  });

  it("shows a Data Integrity Warning and refuses to render when the payload's run_id disagrees with the current route", async () => {
    vi.spyOn(client, "getResearchGraph").mockResolvedValue(
      // Requested for sndk-run, but the payload itself claims tsm-run.
      makeGraph("tsm-run", "TSM", "TSM Revenue Growth")
    );
    vi.spyOn(client, "getResearchConflicts").mockResolvedValue(makeConflicts("sndk-run", "SNDK"));

    const { container } = renderPage("sndk-run");

    await waitFor(() => expect(screen.getByText(/Data Integrity Warning/i)).toBeInTheDocument());
    expect(hasNodeLabel(container, "TSM Revenue Growth")).toBe(false);
  });

  it("renders normally when the payload's run_id matches the current route", async () => {
    vi.spyOn(client, "getResearchGraph").mockResolvedValue(
      makeGraph("sndk-run", "SNDK", "SNDK Revenue Growth")
    );
    vi.spyOn(client, "getResearchConflicts").mockResolvedValue(makeConflicts("sndk-run", "SNDK"));

    const { container } = renderPage("sndk-run");

    await waitFor(() => expect(hasNodeLabel(container, "SNDK Revenue Growth")).toBe(true));
    expect(screen.queryByText(/Data Integrity Warning/i)).not.toBeInTheDocument();
  });
});

// B4 Activation Level Alignment (task B4_ACTIVATION_LEVEL_ALIGNMENT,
// Decision 2): the five-way mutually-exclusive Alpha partition.
describe("StructureGraphPage five-way alpha partition", () => {
  it("places each alpha in exactly one of Active/Dominant/Regime-level/Candidate/Blocked using is_blocked and qualified_level directly", async () => {
    const graph = makeGraph("b4-run", "NVDA", "Revenue Growth");
    graph.activation.alphas = [
      makeAlpha({ alpha_id: "A_ACTIVE", alpha_name: "Active One", status: "active", qualified_level: "active", target_level: "active", is_blocked: false }),
      makeAlpha({ alpha_id: "A_DOMINANT", alpha_name: "Dominant One", status: "dominant", qualified_level: "dominant", target_level: "dominant", is_blocked: false }),
      makeAlpha({ alpha_id: "A_REGIME", alpha_name: "Regime One", status: "regime_level", qualified_level: "regime_level", target_level: "regime_level", is_blocked: false }),
      makeAlpha({ alpha_id: "A_CANDIDATE", alpha_name: "Candidate One", status: "candidate", qualified_level: "candidate", target_level: "candidate", is_blocked: false }),
      // Blocked from dominant -- its own qualified_level is "active", but
      // is_blocked must win first and place it in Blocked, not Active.
      makeAlpha({
        alpha_id: "A_BLOCKED",
        alpha_name: "Blocked One",
        status: "active",
        qualified_level: "active",
        target_level: "dominant",
        is_blocked: true,
        blocked_from: ["dominant"],
        blocked_reason_codes: ["NO_LOCAL_STRUCTURE_SUPPORT"],
      }),
    ];
    vi.spyOn(client, "getResearchGraph").mockResolvedValue(graph);
    vi.spyOn(client, "getResearchConflicts").mockResolvedValue(makeConflicts("b4-run", "NVDA"));

    renderPage("b4-run");

    await waitFor(() => expect(screen.getByText("Active One")).toBeInTheDocument());

    const sectionFor = (heading: string) => {
      const section = screen.getByRole("heading", { name: heading }).closest("section");
      expect(section).not.toBeNull();
      return within(section as HTMLElement);
    };

    expect(sectionFor("Active alphas").getByText("Active One")).toBeInTheDocument();
    expect(sectionFor("Active alphas").queryByText("Blocked One")).not.toBeInTheDocument();

    expect(sectionFor("Dominant alphas").getByText("Dominant One")).toBeInTheDocument();

    expect(sectionFor("Regime-level alphas").getByText("Regime One")).toBeInTheDocument();

    expect(sectionFor("Candidate alphas").getByText("Candidate One")).toBeInTheDocument();

    // Blocked wins over its own qualified_level ("active") -- appears here
    // and nowhere else.
    expect(sectionFor("Blocked alphas").getByText("Blocked One")).toBeInTheDocument();
    expect(sectionFor("Active alphas").queryByText("Blocked One")).not.toBeInTheDocument();
  });

  it("labels the whole partition as legacy classification for a historical payload with no qualified_level anywhere", async () => {
    const graph = makeGraph("legacy-run", "NVDA", "Revenue Growth");
    graph.activation.alphas = [
      makeAlpha({ alpha_id: "A101", status: "active", qualified_level: undefined, target_level: undefined, is_blocked: undefined }),
    ];
    vi.spyOn(client, "getResearchGraph").mockResolvedValue(graph);
    vi.spyOn(client, "getResearchConflicts").mockResolvedValue(makeConflicts("legacy-run", "NVDA"));

    renderPage("legacy-run");

    // Both the page-level overview note and the individual AlphaCard's own
    // fallback row legitimately render "Legacy classification" text.
    await waitFor(() => expect(screen.getAllByText(/Legacy classification/).length).toBeGreaterThan(0));
    // Falls back to the legacy `status` field ("active") for placement --
    // never crashes, never silently drops the alpha from every section.
    const activeSection = screen.getByRole("heading", { name: "Active alphas" }).closest("section");
    expect(within(activeSection as HTMLElement).getByText("A101")).toBeInTheDocument();
  });
});
