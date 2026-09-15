import { render, screen, waitFor, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { Link, MemoryRouter, Route, Routes } from "react-router-dom";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import * as client from "../api/client";
import type { AlphaActivation, AlphaLibraryResponse, ConflictsResponse, StructureGraphResponse } from "../api/types";
import { resetAlphaLibraryCacheForTests } from "../hooks/useAlphaLibrary";
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

function emptyAlphaLibrary(): AlphaLibraryResponse {
  return { schema_version: "week1.alpha_library.v1", alpha_count: 0, alphas: [] };
}

// John Follow-Up Requirement A (Invalidation-Condition Coverage
// Completion): every test in this file renders StructureGraphPage, which
// now also calls useAlphaLibrary. Default to an empty, deterministic
// library so pre-existing tests (none of which assert on invalidation
// conditions) never depend on a real network fetch; tests below that do
// care about invalidation conditions override this mock explicitly.
beforeEach(() => {
  resetAlphaLibraryCacheForTests();
  vi.spyOn(client, "getAlphaLibrary").mockResolvedValue(emptyAlphaLibrary());
});

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

// John Item 8 (Alpha-Level Display Normalization): the display-level
// partition, plus the orthogonal Blocked view.
describe("StructureGraphPage alpha-level partition", () => {
  it("places each alpha in exactly one of Active/Dominant/Regime-level/Candidate using activation_level/qualified_level directly, never is_blocked", async () => {
    const graph = makeGraph("b4-run", "NVDA", "Revenue Growth");
    graph.activation.alphas = [
      makeAlpha({ alpha_id: "A_ACTIVE", alpha_name: "Active One", status: "active", qualified_level: "active", target_level: "active", activation_level: "active", is_blocked: false }),
      makeAlpha({ alpha_id: "A_DOMINANT", alpha_name: "Dominant One", status: "dominant", qualified_level: "dominant", target_level: "dominant", activation_level: "dominant", is_blocked: false }),
      makeAlpha({ alpha_id: "A_REGIME", alpha_name: "Regime One", status: "regime_level", qualified_level: "regime_level", target_level: "regime_level", activation_level: "regime_level", is_blocked: false }),
      makeAlpha({ alpha_id: "A_CANDIDATE", alpha_name: "Candidate One", status: "candidate", qualified_level: "candidate", target_level: "candidate", activation_level: "candidate", is_blocked: false }),
      // (B) Blocked from dominant, but its own qualified_level/
      // activation_level is "active" -- is_blocked must NOT override its
      // display-level placement; it stays in Active alphas, not a
      // "Blocked" level bucket (blocked is now surfaced only via the
      // orthogonal Blocked section below).
      makeAlpha({
        alpha_id: "A_BLOCKED",
        alpha_name: "Blocked One",
        status: "active",
        qualified_level: "active",
        target_level: "dominant",
        activation_level: "active",
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

    // (G) existing candidate/active/dominant/regime_level grouping is
    // unchanged.
    expect(sectionFor("Active alphas").getByText("Active One")).toBeInTheDocument();
    expect(sectionFor("Dominant alphas").getByText("Dominant One")).toBeInTheDocument();
    expect(sectionFor("Regime-level alphas").getByText("Regime One")).toBeInTheDocument();
    expect(sectionFor("Candidate alphas").getByText("Candidate One")).toBeInTheDocument();

    // (B) is_blocked does not move A_BLOCKED out of its own display level.
    expect(sectionFor("Active alphas").getByText("Blocked One")).toBeInTheDocument();

    // (F) A_BLOCKED is ALSO, independently, represented in the orthogonal
    // Blocked view -- without changing its authoritative display level
    // (it does not appear in Dominant, Regime-level, or Candidate).
    expect(sectionFor("Blocked alphas").getByText(/Blocked One/)).toBeInTheDocument();
    expect(sectionFor("Dominant alphas").queryByText("Blocked One")).not.toBeInTheDocument();
    expect(sectionFor("Regime-level alphas").queryByText("Blocked One")).not.toBeInTheDocument();
    expect(sectionFor("Candidate alphas").queryByText("Blocked One")).not.toBeInTheDocument();
  });

  it("routes a capped_active alpha to its own dedicated section, not Active and not a generic Blocked level (A, B, C, F, H)", async () => {
    const graph = makeGraph("capped-run", "QQQ", "Revenue Growth");
    graph.activation.alphas = [
      makeAlpha({ alpha_id: "A101", alpha_name: "Plain Active", status: "active", qualified_level: "active", target_level: "active", activation_level: "active", is_blocked: false }),
      // The real QQQ A601 shape (Step 10/11 production run): qualified
      // "active", capped for display because it was blocked from
      // "dominant" -- activation_level is the backend's own
      // presentation-only field carrying that refinement.
      makeAlpha({
        alpha_id: "A601",
        alpha_name: "Narrative Momentum",
        status: "active",
        qualified_level: "active",
        target_level: "dominant",
        activation_level: "capped_active",
        is_blocked: true,
        blocked_from: ["dominant"],
        blocked_reason_codes: ["NO_LOCAL_STRUCTURE_SUPPORT"],
      }),
    ];
    vi.spyOn(client, "getResearchGraph").mockResolvedValue(graph);
    vi.spyOn(client, "getResearchConflicts").mockResolvedValue(makeConflicts("capped-run", "QQQ"));

    renderPage("capped-run");

    await waitFor(() => expect(screen.getByText("Narrative Momentum")).toBeInTheDocument());

    const sectionFor = (heading: string) => {
      const section = screen.getByRole("heading", { name: heading }).closest("section");
      expect(section).not.toBeNull();
      return within(section as HTMLElement);
    };

    // (A) dedicated "Capped active alphas" section exists and contains it.
    expect(sectionFor("Capped active alphas").getByText("Narrative Momentum")).toBeInTheDocument();

    // (C) NOT counted in / rendered under plain "Active alphas".
    expect(sectionFor("Active alphas").getByText("Plain Active")).toBeInTheDocument();
    expect(sectionFor("Active alphas").queryByText("Narrative Momentum")).not.toBeInTheDocument();

    // (D) summary shows "Capped active alphas: 1".
    const summaryRow = screen.getByText("Capped active alphas", { selector: "dt" }).closest("div");
    expect(within(summaryRow as HTMLElement).getByText("1")).toBeInTheDocument();

    // (F) still independently represented as blocked via the orthogonal
    // Blocked view, without becoming a generic "Blocked" level.
    expect(sectionFor("Blocked alphas").getByText(/Narrative Momentum/)).toBeInTheDocument();
    // Product Demo Hardening Phase 2D: the default view now shows the
    // translated reason, not the raw code -- the raw code is preserved
    // verbatim under Technical details.
    expect(sectionFor("Blocked alphas").getByText(/No supporting Structure Graph edges/)).toBeInTheDocument();
    expect(sectionFor("Blocked alphas").getByText(/NO_LOCAL_STRUCTURE_SUPPORT/)).not.toBeVisible();

    // (H) no candidate_active section/label was invented anywhere.
    expect(screen.queryByText(/candidate_active/i)).not.toBeInTheDocument();
  });

  it("keeps the Blocked-alphas summary count independently correct from is_blocked, distinct from the Capped-active count (D, E)", async () => {
    const graph = makeGraph("counts-run", "QQQ", "Revenue Growth");
    graph.activation.alphas = [
      makeAlpha({ alpha_id: "A601", alpha_name: "Capped And Blocked", status: "active", qualified_level: "active", target_level: "dominant", activation_level: "capped_active", is_blocked: true, blocked_from: ["dominant"], blocked_reason_codes: ["NO_LOCAL_STRUCTURE_SUPPORT"] }),
      // Blocked from regime_level while its own display level is
      // "dominant" -- contributes to the Blocked count but NOT to the
      // Capped-active count (capped_active is only ever a refinement of
      // qualified "active", never of "dominant").
      makeAlpha({ alpha_id: "A101", alpha_name: "Dominant But Blocked", status: "dominant", qualified_level: "dominant", target_level: "regime_level", activation_level: "dominant", is_blocked: true, blocked_from: ["regime_level"], blocked_reason_codes: ["NO_LOCAL_STRUCTURE_SUPPORT"] }),
      makeAlpha({ alpha_id: "A201", alpha_name: "Plain Candidate", status: "candidate", qualified_level: "candidate", target_level: "candidate", activation_level: "candidate", is_blocked: false }),
    ];
    vi.spyOn(client, "getResearchGraph").mockResolvedValue(graph);
    vi.spyOn(client, "getResearchConflicts").mockResolvedValue(makeConflicts("counts-run", "QQQ"));

    renderPage("counts-run");

    await waitFor(() => expect(screen.getByText("Capped And Blocked")).toBeInTheDocument());

    const countFor = (label: string) => {
      const row = screen.getByText(label, { selector: "dt" }).closest("div");
      return within(row as HTMLElement).getByRole("definition").textContent;
    };

    expect(countFor("Capped active alphas")).toBe("1");
    // (E) Blocked count (2) is independent of, and larger than, the
    // Capped-active count (1) -- both alphas are blocked, only one is
    // capped_active.
    expect(countFor("Blocked alphas")).toBe("2");
    expect(countFor("Candidate alphas")).toBe("1");
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

// John Follow-Up Requirement A (Invalidation-Condition Coverage
// Completion): the Alpha Library (GET /api/alpha-library) is fetched once
// and mapped by alpha_id onto every AlphaCard the page renders -- these
// tests prove the wiring end-to-end, that a second (non-A101) Alpha renders
// from the exact same source, and that many simultaneously-rendered
// AlphaCards never trigger more than one Alpha Library request.
describe("StructureGraphPage invalidation conditions", () => {
  it("renders each Alpha's taxonomy invalidation conditions from one shared Alpha Library fetch, for A101 and a second non-A101 Alpha alike", async () => {
    const graph = makeGraph("inv-run", "NVDA", "Revenue Growth");
    graph.activation.alphas = [
      makeAlpha({ alpha_id: "A101", alpha_name: "AI Expansion", status: "active", qualified_level: "active", target_level: "active", activation_level: "active", is_blocked: false }),
      makeAlpha({ alpha_id: "A201", alpha_name: "Semiconductor Supercycle", status: "dominant", qualified_level: "dominant", target_level: "dominant", activation_level: "dominant", is_blocked: false }),
    ];
    vi.spyOn(client, "getResearchGraph").mockResolvedValue(graph);
    vi.spyOn(client, "getResearchConflicts").mockResolvedValue(makeConflicts("inv-run", "NVDA"));
    const librarySpy = vi.spyOn(client, "getAlphaLibrary").mockResolvedValue({
      schema_version: "week1.alpha_library.v1",
      alpha_count: 2,
      alphas: [
        {
          alpha_id: "A101",
          name_en: "AI Expansion",
          name_cn: "AI 扩张",
          layer: "Theme",
          status: "active",
          core_thesis: "AI infrastructure demand drives growth.",
          keywords: [],
          trigger_signals: [],
          confirmation_signals: [],
          beneficiary_assets: [],
          risk_assets: [],
          conflict_alphas: [],
          invalidation_conditions: ["AI capex cuts", "model demand slows", "GPU oversupply"],
          agent_sources: [],
        },
        {
          alpha_id: "A201",
          name_en: "Semiconductor Supercycle",
          name_cn: "半导体超级周期",
          layer: "Industry",
          status: "active",
          core_thesis: "Storage/semiconductor cycle drives demand.",
          keywords: [],
          trigger_signals: [],
          confirmation_signals: [],
          beneficiary_assets: [],
          risk_assets: [],
          conflict_alphas: [],
          invalidation_conditions: ["inventory glut returns", "order cuts resume"],
          agent_sources: [],
        },
      ],
    });

    renderPage("inv-run");

    await waitFor(() => expect(screen.getByText("AI Expansion")).toBeInTheDocument());
    await waitFor(() => expect(screen.getAllByText("Invalidation conditions").length).toBeGreaterThan(0));

    expect(screen.getByText("AI capex cuts")).toBeInTheDocument();
    expect(screen.getByText("inventory glut returns")).toBeInTheDocument();

    // No per-Alpha N+1 fetch: two AlphaCards rendered, one Alpha Library call.
    expect(librarySpy).toHaveBeenCalledTimes(1);
  });

  it("shows the honest fallback for an Alpha with no authoritative invalidation content, never a raw null/undefined", async () => {
    const graph = makeGraph("inv-empty-run", "MSFT", "Revenue Growth");
    graph.activation.alphas = [
      makeAlpha({ alpha_id: "A102", alpha_name: "Inference Explosion", status: "active", qualified_level: "active", target_level: "active", activation_level: "active", is_blocked: false }),
    ];
    vi.spyOn(client, "getResearchGraph").mockResolvedValue(graph);
    vi.spyOn(client, "getResearchConflicts").mockResolvedValue(makeConflicts("inv-empty-run", "MSFT"));
    vi.spyOn(client, "getAlphaLibrary").mockResolvedValue({
      schema_version: "week1.alpha_library.v1",
      alpha_count: 1,
      alphas: [
        {
          alpha_id: "A102",
          name_en: "Inference Explosion",
          name_cn: "推理爆发",
          layer: "Theme",
          status: "active",
          core_thesis: "Enterprise AI inference demand.",
          keywords: [],
          trigger_signals: [],
          confirmation_signals: [],
          beneficiary_assets: [],
          risk_assets: [],
          conflict_alphas: [],
          invalidation_conditions: [],
          agent_sources: [],
        },
      ],
    });

    renderPage("inv-empty-run");

    await waitFor(() => expect(screen.getByText("Inference Explosion")).toBeInTheDocument());
    await waitFor(() =>
      expect(
        screen.getByText("No validated invalidation condition is currently defined for this Alpha.")
      ).toBeInTheDocument()
    );
    expect(screen.queryByText("null")).not.toBeInTheDocument();
    expect(screen.queryByText("undefined")).not.toBeInTheDocument();
  });
});
