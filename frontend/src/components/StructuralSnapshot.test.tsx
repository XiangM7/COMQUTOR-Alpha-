import { render, screen, waitFor } from "@testing-library/react";
import { MemoryRouter } from "react-router-dom";
import { afterEach, describe, expect, it, vi } from "vitest";
import * as client from "../api/client";
import { ApiError } from "../api/errors";
import type { AlphaActivation, AlphaConflict, CanonicalResearchResponse, StructureGraphResponse } from "../api/types";
import { StructuralSnapshot } from "./StructuralSnapshot";

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

function makeGraph(runId: string, ticker: string, alphas: AlphaActivation[]): StructureGraphResponse {
  return {
    run_id: runId,
    ticker,
    status: "ok",
    schema_version: "week3.structure_graph.v2",
    graph_builder_version: "test.v1",
    activation_scorer_version: "test.v1",
    nodes: [],
    edges: [],
    graph_metrics: {},
    graph_coherence: {},
    activation: {
      formula_version: "test.v1",
      weights: {},
      run_timestamp: null,
      as_of: null,
      alphas,
    },
    activation_versions: {},
    primary_activation_version: null,
    dominant_alphas: [],
    provenance: {},
  };
}

function makeConflict(overrides: Partial<AlphaConflict> = {}): AlphaConflict {
  return {
    conflict_id: "A301__A304",
    alpha_a: "A301",
    alpha_b: "A304",
    bull_alpha_id: "A301",
    bear_alpha_id: "A304",
    bull_structure: {
      alpha_id: "A301",
      alpha_name: "Revenue Expansion",
      activation_score: 66.5,
      status: "active",
      direction: "positive",
      claim_ids: ["c1"],
      source_agent_output_ids: ["o1"],
      agents: ["news_agent"],
      evidence: ["Revenue guidance was raised."],
      match_scores: [0.9],
    },
    bear_structure: {
      alpha_id: "A304",
      alpha_name: "Multiple Compression",
      activation_score: 55.2,
      status: "active",
      direction: "negative",
      claim_ids: ["b1"],
      source_agent_output_ids: ["o2"],
      agents: ["bear_researcher"],
      evidence: ["Valuation multiples remain stretched."],
      match_scores: [0.8],
    },
    components: {
      activation_a: 66.5,
      activation_b: 55.2,
      minimum_activation: 55.2,
      contradiction_weight: 0.85,
      alpha_a_evidence_strength: 0.9,
      alpha_b_evidence_strength: 0.78,
      evidence_strength: 0.84,
    },
    alpha_a_strength: 0.9,
    alpha_b_strength: 0.78,
    evidence_strength: 0.84,
    conflict_score: 36.8,
    conflict_level: "medium_high",
    reason_codes: [],
    explanation: "Revenue Expansion and Multiple Compression present a structural tension.",
    bull_evidence: [],
    bear_evidence: [],
    ...overrides,
  };
}

const BASE_ARTIFACTS = {
  metadata: true,
  raw_agent_outputs: true,
  structured_agent_outputs: true,
  final_report: false,
  alpha_matches: true,
  extracted_structures: true,
  structured_output_error_logs: false,
  week2_llm_error_logs: false,
  week2_pipeline_error_logs: false,
};

function makeResearch(overrides: Partial<CanonicalResearchResponse> = {}): CanonicalResearchResponse {
  return {
    run_id: "run-1",
    ticker: "NVDA",
    status: "completed",
    artifacts: BASE_ARTIFACTS,
    agent_output_count: 1,
    structured_output_count: 1,
    structure_graph_status: "ready",
    dominant_alphas: [],
    main_conflict: null,
    conflict_status: "ready",
    summary: "Summary.",
    data_sanity_status: "not_available",
    data_sanity_warning_count: 0,
    data_sanity_critical_count: 0,
    data_sanity_warnings: [],
    ...overrides,
  };
}

function renderSnapshot(research: CanonicalResearchResponse, runId = "run-1") {
  return render(
    <MemoryRouter>
      <StructuralSnapshot runId={runId} research={research} />
    </MemoryRouter>
  );
}

describe("StructuralSnapshot", () => {
  afterEach(() => {
    vi.restoreAllMocks();
  });

  it("renders the active Alpha list with human-readable names paired to each ID", async () => {
    vi.spyOn(client, "getResearchGraph").mockResolvedValue(
      makeGraph("run-1", "NVDA", [
        makeAlpha({ alpha_id: "A301", alpha_name: "Revenue Expansion", status: "dominant" }),
        makeAlpha({ alpha_id: "A101", alpha_name: "AI Expansion", status: "active" }),
        makeAlpha({ alpha_id: "A001", alpha_name: "Rate Cut Cycle", status: "candidate" }),
      ])
    );
    renderSnapshot(makeResearch());

    await waitFor(() => expect(screen.getByText("Revenue Expansion")).toBeInTheDocument());
    expect(screen.getByText("A301")).toBeInTheDocument();
    expect(screen.getByText("AI Expansion")).toBeInTheDocument();
    expect(screen.getByText("A101")).toBeInTheDocument();
    // Candidate-level Alphas are not shown indiscriminately in the active list.
    expect(screen.queryByText("Rate Cut Cycle")).not.toBeInTheDocument();
    expect(screen.queryByText("A001")).not.toBeInTheDocument();
  });

  it("shows a legitimate empty state, never a fabricated Alpha, when nothing meets the active threshold", async () => {
    vi.spyOn(client, "getResearchGraph").mockResolvedValue(
      makeGraph("run-1", "NVDA", [makeAlpha({ alpha_id: "A001", status: "candidate" })])
    );
    renderSnapshot(makeResearch());
    await waitFor(() =>
      expect(screen.getByText("No Alpha structure currently meets the active threshold.")).toBeInTheDocument()
    );
  });

  it("shows the Dominant Structure present state with ID and human-readable name", async () => {
    vi.spyOn(client, "getResearchGraph").mockResolvedValue(makeGraph("run-1", "NVDA", []));
    renderSnapshot(
      makeResearch({
        dominant_alphas: [
          {
            alpha_id: "A301",
            alpha_name: "Revenue Expansion",
            activation_score: 78.5,
            status: "dominant",
            direction: "positive",
            evidence_summary: { evidence_count: 10, distinct_supporting_agents: 4 },
          },
        ],
      })
    );
    await waitFor(() => expect(screen.getByText("Dominant structure")).toBeInTheDocument());
    expect(screen.getByText("A301")).toBeInTheDocument();
    expect(screen.getByText("Revenue Expansion")).toBeInTheDocument();
  });

  it("shows the explicit no-dominant legitimate-result copy, not blank/None/a dash", async () => {
    vi.spyOn(client, "getResearchGraph").mockResolvedValue(makeGraph("run-1", "QQQ", []));
    renderSnapshot(makeResearch({ dominant_alphas: [] }));
    await waitFor(() =>
      expect(screen.getByText("No single structure currently dominates.")).toBeInTheDocument()
    );
    expect(
      screen.getByText("Several active forces are present, but none has reached dominant status.")
    ).toBeInTheDocument();
  });

  it("distinguishes the no-dominant legitimate result from a not-ready structure_graph_status", async () => {
    vi.spyOn(client, "getResearchGraph").mockResolvedValue(makeGraph("run-1", "NVDA", []));
    renderSnapshot(makeResearch({ structure_graph_status: "not_ready", dominant_alphas: [] }));
    await waitFor(() =>
      expect(screen.getByText("Structural detail is not ready yet for this run.")).toBeInTheDocument()
    );
    expect(screen.queryByText("No single structure currently dominates.")).not.toBeInTheDocument();
  });

  it("shows the Main Structural Conflict present state with both sides' ID and human-readable name", async () => {
    vi.spyOn(client, "getResearchGraph").mockResolvedValue(makeGraph("run-1", "NVDA", []));
    renderSnapshot(makeResearch({ main_conflict: makeConflict({ alpha_a: "A301", alpha_b: "A304" }) }));
    await waitFor(() => expect(screen.getByText("Main structural conflict")).toBeInTheDocument());
    expect(screen.getByText(/A301 — Revenue Expansion/)).toBeInTheDocument();
    expect(screen.getByText(/A304 — Multiple Compression/)).toBeInTheDocument();
    expect(screen.getByRole("link", { name: /view conflict details/i })).toBeInTheDocument();
  });

  it("shows the explicit no-conflict legitimate-result copy, adapted from ConflictRadarPage's own language", async () => {
    vi.spyOn(client, "getResearchGraph").mockResolvedValue(makeGraph("run-1", "SNDK", []));
    renderSnapshot(makeResearch({ main_conflict: null }));
    await waitFor(() =>
      expect(
        screen.getByText(/no high-confidence structural conflict is currently admitted/i)
      ).toBeInTheDocument()
    );
    expect(screen.getByText(/does not mean the position carries no risk/i)).toBeInTheDocument();
  });

  it("distinguishes the no-conflict legitimate result from a not-ready conflict_status", async () => {
    vi.spyOn(client, "getResearchGraph").mockResolvedValue(makeGraph("run-1", "NVDA", []));
    renderSnapshot(makeResearch({ conflict_status: "not_ready", main_conflict: null }));
    await waitFor(() =>
      expect(screen.getByText("Conflict analysis is not ready yet for this run.")).toBeInTheDocument()
    );
    expect(screen.queryByText(/no high-confidence structural conflict/i)).not.toBeInTheDocument();
  });

  it("shows a loading state for the active-structures section while the graph fetch is in flight", async () => {
    let resolveGraph: (value: StructureGraphResponse) => void = () => {};
    vi.spyOn(client, "getResearchGraph").mockReturnValue(
      new Promise((resolve) => {
        resolveGraph = resolve;
      })
    );
    renderSnapshot(makeResearch());
    expect(screen.getByText("Loading structural detail…")).toBeInTheDocument();
    resolveGraph(makeGraph("run-1", "NVDA", []));
    await waitFor(() =>
      expect(screen.getByText("No Alpha structure currently meets the active threshold.")).toBeInTheDocument()
    );
  });

  it("shows a safe unavailable message, never a raw error, when the graph fetch fails", async () => {
    vi.spyOn(client, "getResearchGraph").mockRejectedValue(ApiError.network());
    renderSnapshot(makeResearch());
    await waitFor(() => expect(screen.getByRole("button", { name: /retry/i })).toBeInTheDocument());
    expect(screen.queryByText("Loading structural detail…")).not.toBeInTheDocument();
  });

  it("never renders raw internal level vocabulary (regime_level, candidate) anywhere in the summary", async () => {
    vi.spyOn(client, "getResearchGraph").mockResolvedValue(
      makeGraph("run-1", "NVDA", [
        makeAlpha({ alpha_id: "A301", alpha_name: "Revenue Expansion", status: "dominant" }),
        makeAlpha({ alpha_id: "A601", alpha_name: "Narrative Momentum", status: "regime_level" }),
        makeAlpha({ alpha_id: "A001", alpha_name: "Rate Cut Cycle", status: "candidate" }),
      ])
    );
    const { container } = renderSnapshot(
      makeResearch({
        dominant_alphas: [
          {
            alpha_id: "A301",
            alpha_name: "Revenue Expansion",
            activation_score: 78.5,
            status: "dominant",
            direction: "positive",
            evidence_summary: { evidence_count: 10, distinct_supporting_agents: 4 },
          },
        ],
      })
    );
    await waitFor(() => expect(screen.getByText("Revenue Expansion")).toBeInTheDocument());
    const text = container.textContent ?? "";
    expect(text).not.toContain("regime_level");
    expect(text).not.toContain("candidate");
  });

  describe("Demo-state reference fixtures", () => {
    it("NVDA-like: multiple active structures, dominant A301, main conflict A101 vs A304", async () => {
      vi.spyOn(client, "getResearchGraph").mockResolvedValue(
        makeGraph("run-nvda", "NVDA", [
          makeAlpha({ alpha_id: "A301", alpha_name: "Revenue Expansion", status: "dominant" }),
          makeAlpha({ alpha_id: "A101", alpha_name: "AI Expansion", status: "active", activation_level: "capped_active" }),
          makeAlpha({ alpha_id: "A601", alpha_name: "Narrative Momentum", status: "active" }),
          makeAlpha({ alpha_id: "A304", alpha_name: "Multiple Compression", status: "active" }),
          makeAlpha({ alpha_id: "A001", alpha_name: "Rate Cut Cycle", status: "candidate" }),
        ])
      );
      renderSnapshot(
        makeResearch({
          run_id: "run-nvda",
          ticker: "NVDA",
          dominant_alphas: [
            {
              alpha_id: "A301",
              alpha_name: "Revenue Expansion",
              activation_score: 78.5,
              status: "dominant",
              direction: "positive",
              evidence_summary: { evidence_count: 10, distinct_supporting_agents: 4 },
            },
          ],
          main_conflict: makeConflict({
            alpha_a: "A101",
            alpha_b: "A304",
            bull_structure: {
              alpha_id: "A101",
              alpha_name: "AI Expansion",
              activation_score: 70,
              status: "active",
              direction: "positive",
              claim_ids: [],
              source_agent_output_ids: [],
              agents: [],
              evidence: [],
              match_scores: [],
            },
            bear_structure: {
              alpha_id: "A304",
              alpha_name: "Multiple Compression",
              activation_score: 67.6,
              status: "active",
              direction: "negative",
              claim_ids: [],
              source_agent_output_ids: [],
              agents: [],
              evidence: [],
              match_scores: [],
            },
          }),
        }),
        "run-nvda"
      );

      await waitFor(() => expect(screen.getByText("Dominant structure")).toBeInTheDocument());
      expect(screen.getAllByText("Revenue Expansion").length).toBeGreaterThan(0);
      expect(screen.getByText("AI Expansion")).toBeInTheDocument();
      expect(screen.getByText("Narrative Momentum")).toBeInTheDocument();
      expect(screen.getByText(/A101 — AI Expansion/)).toBeInTheDocument();
      expect(screen.getByText(/A304 — Multiple Compression/)).toBeInTheDocument();
      expect(screen.queryByText("Rate Cut Cycle")).not.toBeInTheDocument();
    });

    it("QQQ-like: active structures present, NO dominant Alpha, main conflict A301 vs A304, no A001 remediation story leaked", async () => {
      vi.spyOn(client, "getResearchGraph").mockResolvedValue(
        makeGraph("run-qqq", "QQQ", [
          makeAlpha({ alpha_id: "A103", alpha_name: "AI Infrastructure", status: "active", activation_level: "capped_active" }),
          makeAlpha({ alpha_id: "A304", alpha_name: "Multiple Compression", status: "active" }),
          makeAlpha({ alpha_id: "A601", alpha_name: "Narrative Momentum", status: "active" }),
          makeAlpha({ alpha_id: "A301", alpha_name: "Revenue Expansion", status: "active" }),
          makeAlpha({ alpha_id: "A001", alpha_name: "Rate Cut Cycle", status: "candidate" }),
        ])
      );
      renderSnapshot(
        makeResearch({
          run_id: "run-qqq",
          ticker: "QQQ",
          dominant_alphas: [],
          main_conflict: makeConflict({ alpha_a: "A301", alpha_b: "A304" }),
        }),
        "run-qqq"
      );

      await waitFor(() => expect(screen.getByText("No single structure currently dominates.")).toBeInTheDocument());
      expect(screen.getByText(/A301 — Revenue Expansion/)).toBeInTheDocument();
      expect(screen.getByText(/A304 — Multiple Compression/)).toBeInTheDocument();
      expect(screen.getByText("AI Infrastructure")).toBeInTheDocument();
      // A001 remains a non-shown candidate; the historical remediation story
      // is never surfaced in normal product UI.
      expect(screen.queryByText("Rate Cut Cycle")).not.toBeInTheDocument();
      expect(screen.queryByText(/remediat/i)).not.toBeInTheDocument();
    });

    it("SNDK-like: active structures present, dominant A201, NO admitted main conflict", async () => {
      vi.spyOn(client, "getResearchGraph").mockResolvedValue(
        makeGraph("run-sndk", "SNDK", [
          makeAlpha({ alpha_id: "A201", alpha_name: "Semiconductor Supercycle", status: "dominant" }),
          makeAlpha({ alpha_id: "A601", alpha_name: "Narrative Momentum", status: "active" }),
          makeAlpha({ alpha_id: "A304", alpha_name: "Multiple Compression", status: "active" }),
        ])
      );
      renderSnapshot(
        makeResearch({
          run_id: "run-sndk",
          ticker: "SNDK",
          dominant_alphas: [
            {
              alpha_id: "A201",
              alpha_name: "Semiconductor Supercycle",
              activation_score: 84.2,
              status: "dominant",
              direction: "positive",
              evidence_summary: { evidence_count: 8, distinct_supporting_agents: 3 },
            },
          ],
          main_conflict: null,
        }),
        "run-sndk"
      );

      await waitFor(() => expect(screen.getAllByText("Semiconductor Supercycle").length).toBeGreaterThan(0));
      expect(
        screen.getByText(/no high-confidence structural conflict is currently admitted/i)
      ).toBeInTheDocument();
    });
  });
});
