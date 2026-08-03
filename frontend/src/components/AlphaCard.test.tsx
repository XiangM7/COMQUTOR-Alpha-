import { render, screen } from "@testing-library/react";
import { describe, expect, it } from "vitest";
import type { AlphaActivation, AlphaEvidenceDetail, EntityExposure } from "../api/types";
import { AlphaCard } from "./AlphaCard";

function makeActivation(overrides: Partial<AlphaActivation> = {}): AlphaActivation {
  return {
    alpha_id: "A101",
    alpha_name: "AI Expansion",
    activation_score: 58.3,
    status: "active",
    direction: "positive",
    components: {},
    evidence_count: 5,
    distinct_supporting_agents: 3,
    claim_ids: [],
    evidence: [],
    reason_codes: [],
    evidence_detail: [],
    formula_version: "activation.v2.evidence_local_structure.v1",
    uncapped_score: 58.3,
    eligible_cap: null,
    cap_was_binding: false,
    cap_reason_codes: [],
    binding_cap_reason_codes: [],
    unique_evidence_count: 5,
    ticker_specific_evidence_count: 1,
    local_edge_count: 2,
    regime_gate_passed: false,
    regime_gate_failures: [],
    ...overrides,
  };
}

const EVIDENCE: AlphaEvidenceDetail[] = [
  {
    claim_id: "run1:news_agent:news_report:claim:1",
    claim: "Datacenter storage demand supports revenue growth.",
    agent: "news_agent",
    source_agent_output_id: "run1:news_agent:news_report",
    match_score: 0.61,
    relation: "activation",
    matched_keywords: ["storage demand"],
    matched_factors: ["Semiconductor Cycle"],
    assertion_status: "asserted",
    direction: "positive",
  },
];

function renderCard(overrides: Partial<Parameters<typeof AlphaCard>[0]> = {}) {
  return render(
    <AlphaCard
      alphaId="A101"
      alphaName="AI Expansion"
      activationScore={90.7}
      status="regime_level"
      direction="positive"
      evidenceCount={5}
      distinctSupportingAgents={3}
      {...overrides}
    />
  );
}

function makeExposure(overrides: Partial<EntityExposure> = {}): EntityExposure {
  return {
    historical_mapping: 0.95,
    current_evidence: 0.5,
    agent_confidence: 0.8,
    final_exposure: 0.785,
    seed_version: "v0.1",
    seed_effective_date: "2026-07-31",
    seed_approval_status: "draft",
    mode: "shadow",
    exposure_status: "computed",
    would_block_dominant: false,
    would_block_regime_level: false,
    override_candidate: false,
    qualification_effect_applied: false,
    unique_evidence_fact_count: 4,
    ticker_specific_fact_count: 2,
    distinct_supporting_agent_count: 3,
    reason_codes: [],
    ...overrides,
  };
}

describe("AlphaCard", () => {
  it("shows draft shadow Entity Exposure components and would-block fields", () => {
    renderCard({ activation: makeActivation({ entity_exposure: makeExposure() }) });
    expect(screen.getByText("Entity Exposure").closest("div")?.textContent).toContain("0.785");
    expect(screen.getByText("Draft seed — pending product-owner approval")).toBeInTheDocument();
    expect(screen.getByText("Shadow only — Not applied to Activation")).toBeInTheDocument();
    expect(screen.getByText("Historical mapping").closest("div")?.textContent).toContain("0.950");
    expect(screen.getByText("Current evidence").closest("div")?.textContent).toContain("0.500");
    expect(screen.getByText("Agent confidence").closest("div")?.textContent).toContain("0.800");
    expect(screen.getByText("Would block dominant").closest("div")?.textContent).toContain("No");
    expect(screen.getByText("Would block regime level").closest("div")?.textContent).toContain("No");
  });

  it("shows an explicit missing-seed fallback", () => {
    renderCard({
      activation: makeActivation({
        entity_exposure: makeExposure({
          historical_mapping: null,
          final_exposure: null,
          exposure_status: "missing_seed",
        }),
      }),
    });
    expect(screen.getByText("Entity Exposure").closest("div")?.textContent).toContain(
      "Not available",
    );
    expect(screen.getByText("No approved/configured seed entry")).toBeInTheDocument();
  });

  it("handles an old Activation payload with no Entity Exposure", () => {
    renderCard({ activation: makeActivation() });
    expect(screen.getByText("Entity Exposure").closest("div")?.textContent).toContain(
      "Not available",
    );
  });

  it("shows related conflicts when this run has conflicts involving the alpha", () => {
    renderCard({ relatedConflicts: ["A101 vs A304"] });
    expect(screen.getByText("A101 vs A304")).toBeInTheDocument();
    expect(screen.queryByText("Not available")).not.toBeInTheDocument();
  });

  it("distinguishes 'no conflicts this run' (None) from 'no conflict data' (Not available)", () => {
    const { unmount } = renderCard({ relatedConflicts: [] });
    expect(screen.getByText("None")).toBeInTheDocument();
    unmount();
    renderCard({ relatedConflicts: null });
    expect(screen.getByText("Not available")).toBeInTheDocument();
  });

  it("shows the Activation v2 formula transparency block", () => {
    renderCard({
      status: "dominant",
      activation: makeActivation({
        eligible_cap: 70,
        cap_was_binding: true,
        cap_reason_codes: ["NO_LOCAL_STRUCTURE_SUPPORT"],
        binding_cap_reason_codes: ["NO_LOCAL_STRUCTURE_SUPPORT"],
        uncapped_score: 75.2,
        activation_score: 70,
        regime_gate_passed: false,
        regime_gate_failures: ["NO_LOCAL_STRUCTURE_FOR_REGIME"],
      }),
    });
    expect(screen.getByText("Activation v2")).toBeInTheDocument();
    expect(screen.getByText("75.2")).toBeInTheDocument();
    expect(screen.getByText(/70 \(NO_LOCAL_STRUCTURE_SUPPORT\)/)).toBeInTheDocument();
    expect(screen.getByText(/Yes — final score: 70.0 \(NO_LOCAL_STRUCTURE_SUPPORT\)/)).toBeInTheDocument();
    expect(screen.getByText("Ticker-specific evidence")).toBeInTheDocument();
    expect(screen.getByText("Local structural edges")).toBeInTheDocument();
    expect(
      screen.getByText(/Not qualified \(NO_LOCAL_STRUCTURE_FOR_REGIME\)/)
    ).toBeInTheDocument();
  });

  it("cap contract test #16: distinguishes an eligible-but-non-binding cap from a binding one", () => {
    const { unmount } = renderCard({
      status: "active",
      activation: makeActivation({
        eligible_cap: 70,
        cap_was_binding: false,
        cap_reason_codes: ["INSUFFICIENT_AGENT_INDEPENDENCE"],
        binding_cap_reason_codes: [],
        uncapped_score: 65.9,
        activation_score: 65.9,
      }),
    });
    expect(screen.getByText(/70 \(INSUFFICIENT_AGENT_INDEPENDENCE\)/)).toBeInTheDocument();
    expect(screen.getByText("No")).toBeInTheDocument();
    unmount();

    renderCard({
      status: "dominant",
      activation: makeActivation({
        eligible_cap: 60,
        cap_was_binding: true,
        cap_reason_codes: ["INSUFFICIENT_UNIQUE_EVIDENCE", "NO_LOCAL_STRUCTURE_SUPPORT"],
        binding_cap_reason_codes: ["INSUFFICIENT_UNIQUE_EVIDENCE"],
        uncapped_score: 88,
        activation_score: 60,
      }),
    });
    // The "Score was capped" row shows only the binding (60-value) reason
    // -- the non-binding 70-value cap's reason must never appear there,
    // even though it legitimately still appears in the "Qualification
    // ceiling" row's full cap_reason_codes list.
    const cappedRow = screen.getByText(/Yes — final score: 60.0/);
    expect(cappedRow.textContent).toContain("INSUFFICIENT_UNIQUE_EVIDENCE");
    expect(cappedRow.textContent).not.toContain("NO_LOCAL_STRUCTURE_SUPPORT");
  });

  it("regime gate test #27: reads regime_gate_passed directly, never re-derives it from status", () => {
    // status alone says "regime_level", but the backend's own verdict says
    // the gate did not pass -- the card must trust regime_gate_passed, not
    // infer success from the status string.
    renderCard({
      status: "regime_level",
      activation: makeActivation({
        regime_gate_passed: false,
        regime_gate_failures: ["EVIDENCE_INTEGRITY_WARNING"],
      }),
    });
    expect(screen.getByText(/Not qualified \(EVIDENCE_INTEGRITY_WARNING\)/)).toBeInTheDocument();
    expect(screen.queryByText("Qualified")).not.toBeInTheDocument();
  });

  it("labels a v1-legacy activation as v1 and never as v2", () => {
    renderCard({
      activation: makeActivation({ formula_version: null }),
    });
    expect(screen.getByText("Activation v1 (legacy)")).toBeInTheDocument();
    expect(screen.queryByText("Activation v2")).not.toBeInTheDocument();
    expect(screen.queryByText("Uncapped score")).not.toBeInTheDocument();
  });

  it("shows raw/independent/overlap evidence fact fields when the API provides them (A304 profile)", () => {
    renderCard({
      status: "active",
      activation: makeActivation({
        raw_supporting_claim_count: 11,
        unique_evidence_fact_count: 5,
        distinct_supporting_agent_count: 5,
        evidence_overlap_ratio: 0.5455,
        high_overlap_warning: true,
      }),
    });
    expect(screen.getByText("Raw supporting claims").closest("div")?.textContent).toContain("11");
    expect(
      screen.getByText("Independent evidence facts").closest("div")?.textContent
    ).toContain("5");
    expect(screen.getByText("Evidence overlap").closest("div")?.textContent).toContain("54.5%");
    expect(
      screen.getByText(/Several supporting claims appear to restate the same underlying facts/)
    ).toBeInTheDocument();
    // The raw count (11) must never be presented as "11 independent facts".
    expect(screen.queryByText(/11 independent/i)).not.toBeInTheDocument();
  });

  it("omits the evidence-fact breakdown and overlap warning when the API predates these fields", () => {
    renderCard({ status: "active", activation: makeActivation() });
    expect(screen.queryByText("Raw supporting claims")).not.toBeInTheDocument();
    expect(screen.queryByText("Independent evidence facts")).not.toBeInTheDocument();
    expect(screen.queryByText(/Evidence overlap warning/)).not.toBeInTheDocument();
  });

  it("distinguishes incident graph edges from qualifying activation-support edges, with exclusion reasons", () => {
    renderCard({
      status: "active",
      activation: makeActivation({
        components: {
          local_structure_support: {
            incident_graph_edge_count: 4,
            qualifying_local_edge_count: 0,
            nonqualifying_local_edge_count: 4,
            local_edge_exclusion_reasons: ["NO_COMMITTED_ALPHA_MATCH"],
          },
        },
      }),
    });
    expect(screen.getByText("Incident graph edges").closest("div")?.textContent).toContain("4");
    expect(
      screen.getByText("Qualifying activation-support edges").closest("div")?.textContent
    ).toContain("0");
    expect(screen.getByText("Why edges did not qualify")).toBeInTheDocument();
    expect(screen.getByText("NO_COMMITTED_ALPHA_MATCH")).toBeInTheDocument();
  });

  it("never claims 4 incident edges all qualify when qualifying count is 0", () => {
    renderCard({
      status: "active",
      activation: makeActivation({
        components: {
          local_structure_support: {
            incident_graph_edge_count: 4,
            qualifying_local_edge_count: 0,
            nonqualifying_local_edge_count: 4,
            local_edge_exclusion_reasons: [],
          },
        },
      }),
    });
    const incidentRow = screen.getByText("Incident graph edges").closest("div");
    const qualifyingRow = screen.getByText("Qualifying activation-support edges").closest("div");
    expect(incidentRow?.textContent).toContain("4");
    expect(qualifyingRow?.textContent).toContain("0");
  });

  it("renders expandable evidence with claim, agent, match provenance, keywords and factors", () => {
    renderCard({ relatedConflicts: ["A101 vs A304"], evidenceDetail: EVIDENCE });
    expect(screen.getByText(/Evidence \(1\)/)).toBeInTheDocument();
    expect(
      screen.getByText("Datacenter storage demand supports revenue growth.")
    ).toBeInTheDocument();
    expect(screen.getByText(/Agent: news_agent/)).toBeInTheDocument();
    expect(screen.getByText(/Match 0.61/)).toBeInTheDocument();
    expect(screen.getByText(/Relation: activation/)).toBeInTheDocument();
    expect(screen.getByText(/Matched keywords: storage demand/)).toBeInTheDocument();
    expect(screen.getByText(/Matched factors: Semiconductor Cycle/)).toBeInTheDocument();
    expect(screen.getByText("run1:news_agent:news_report:claim:1")).toBeInTheDocument();
    // Supporting agents surfaced from evidence provenance.
    expect(screen.getByText("news_agent")).toBeInTheDocument();
  });
});
