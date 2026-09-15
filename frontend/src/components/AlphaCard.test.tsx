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
  it("shows draft shadow Entity Exposure components and would-block fields (legacy payload, no effective_status)", () => {
    // makeExposure()'s default (mode: "shadow", no configured_status/
    // effective_status) is deliberately shaped like a historical payload
    // predating John's B3 lifecycle fields -- the card must fall back to
    // the legacy `mode` field and label it correctly, never crash (task
    // section 9/24).
    renderCard({ activation: makeActivation({ entity_exposure: makeExposure() }) });
    expect(screen.getByText("Entity Exposure").closest("div")?.textContent).toContain("0.785");
    expect(
      screen.getByText("Draft shadow — Displayed only — not applied to Activation")
    ).toBeInTheDocument();
    expect(screen.getByText("Shadow only — Not applied to Activation")).toBeInTheDocument();
    expect(screen.getByText("Historical mapping").closest("div")?.textContent).toContain("0.950");
    expect(screen.getByText("Current evidence").closest("div")?.textContent).toContain("0.500");
    expect(screen.getByText("Agent confidence").closest("div")?.textContent).toContain("0.800");
    expect(screen.getByText("Would block dominant").closest("div")?.textContent).toContain("No");
    expect(screen.getByText("Would block regime level").closest("div")?.textContent).toContain("No");
  });

  it("shows Approved gating status and approver identity for a gated seed", () => {
    renderCard({
      activation: makeActivation({
        entity_exposure: makeExposure({
          configured_status: "approved_gating",
          effective_status: "approved_gating",
          seed_approval_status: "approved_gating",
          mode: "enforced",
          owner: "John",
          approved_by: "John",
          approved_at: "2026-08-11",
        }),
      }),
    });
    expect(
      screen.getByText("Approved gating — Participates in qualification")
    ).toBeInTheDocument();
    expect(screen.getByText("Approved by").closest("div")?.textContent).toContain("John");
    expect(screen.getByText("Approved by").closest("div")?.textContent).toContain("2026-08-11");
    // approved_gating must never show the shadow-only warning.
    expect(screen.queryByText("Shadow only — Not applied to Activation")).not.toBeInTheDocument();
  });

  it("shows Disabled status for a disabled seed", () => {
    renderCard({
      activation: makeActivation({
        entity_exposure: makeExposure({
          configured_status: "disabled",
          effective_status: "disabled",
          mode: "off",
        }),
      }),
    });
    expect(screen.getByText("Disabled — Seed not participating")).toBeInTheDocument();
  });

  it("shows the fail-closed gating-downgraded warning with the backend's own reason codes, never re-derived", () => {
    renderCard({
      activation: makeActivation({
        entity_exposure: makeExposure({
          configured_status: "approved_gating",
          effective_status: "draft_shadow",
          mode: "shadow",
          reason_codes: ["APPROVAL_METADATA_INCOMPLETE", "GATING_NOT_ALLOWED"],
        }),
      }),
    });
    expect(
      screen.getByText("Draft shadow — Displayed only — not applied to Activation")
    ).toBeInTheDocument();
    const downgradeRow = screen.getByText("Gating downgraded").closest("div");
    expect(downgradeRow?.textContent).toContain("Approved gating");
    expect(downgradeRow?.textContent).toContain("APPROVAL_METADATA_INCOMPLETE");
    expect(downgradeRow?.textContent).toContain("GATING_NOT_ALLOWED");
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
    // Product Demo Hardening Phase 2D: the default view shows the ceiling
    // value and the capped/qualified state without the raw reason code --
    // the exact raw code is preserved, relocated to Technical details.
    expect(screen.getByText("Qualification ceiling").closest("div")?.textContent).toBe(
      "Qualification ceiling70"
    );
    expect(screen.getByText(/^Yes — final score: 70\.0$/)).toBeInTheDocument();
    expect(screen.getByText("Ticker-specific evidence")).toBeInTheDocument();
    expect(screen.getByText("Local structural edges")).toBeInTheDocument();
    expect(screen.getByText("Not qualified")).toBeInTheDocument();
    // Raw codes remain fully auditable under Technical details, just not
    // visible by default.
    expect(screen.getByText("Technical details")).toBeInTheDocument();
    for (const el of screen.getAllByText("NO_LOCAL_STRUCTURE_SUPPORT")) {
      expect(el).not.toBeVisible();
    }
    expect(screen.getByText("NO_LOCAL_STRUCTURE_FOR_REGIME")).not.toBeVisible();
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
    expect(screen.getByText("Qualification ceiling").closest("div")?.textContent).toBe(
      "Qualification ceiling70"
    );
    expect(screen.getByText("No")).toBeInTheDocument();
    // Raw code preserved under Technical details for this non-binding cap.
    expect(screen.getByText("Qualification ceiling reason codes").closest("div")?.textContent).toContain(
      "INSUFFICIENT_AGENT_INDEPENDENCE"
    );
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
    // The default "Score was capped" row no longer shows any raw reason
    // code at all (Phase 2D). The binding-vs-eligible distinction is
    // preserved verbatim under Technical details: "Score-capped reason
    // codes" carries only the binding (60-value) reason, while
    // "Qualification ceiling reason codes" carries the full eligible-cap
    // list -- the non-binding 70-value-style reason must never appear in
    // the binding-only technical field.
    expect(screen.getByText(/^Yes — final score: 60\.0$/)).toBeInTheDocument();
    const scoreCappedCodes = screen.getByText("Score-capped reason codes").closest("div");
    expect(scoreCappedCodes?.textContent).toContain("INSUFFICIENT_UNIQUE_EVIDENCE");
    expect(scoreCappedCodes?.textContent).not.toContain("NO_LOCAL_STRUCTURE_SUPPORT");
    const ceilingCodes = screen.getByText("Qualification ceiling reason codes").closest("div");
    expect(ceilingCodes?.textContent).toContain("INSUFFICIENT_UNIQUE_EVIDENCE");
    expect(ceilingCodes?.textContent).toContain("NO_LOCAL_STRUCTURE_SUPPORT");
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
    expect(screen.getByText("Not qualified")).toBeInTheDocument();
    expect(screen.queryByText("Qualified")).not.toBeInTheDocument();
    // The raw failure code is preserved verbatim under Technical details.
    expect(screen.getByText("Regime gate failure codes").closest("div")?.textContent).toContain(
      "EVIDENCE_INTEGRITY_WARNING"
    );
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

  // B4 Activation Level Alignment (task B4_ACTIVATION_LEVEL_ALIGNMENT).
  it("shows target level, blocked-from, and canonical blocked reason for a blocked alpha", () => {
    renderCard({
      status: "active",
      activation: makeActivation({
        status: "active",
        target_level: "dominant",
        qualified_level: "active",
        is_blocked: true,
        blocked_from: ["dominant"],
        blocked_reason_codes: ["NO_LOCAL_STRUCTURE_SUPPORT"],
        diagnostic_reason_codes: ["NO_LOCAL_STRUCTURE_SUPPORT"],
        classification_version: "b4.alpha_level.v1",
      }),
    });
    // Product Demo Hardening Phase 2D: raw level tokens embedded in this
    // prose are translated to product language ("Dominant"/"Active"),
    // never the raw "dominant"/"active" strings.
    expect(screen.getByText("Target level").closest("div")?.textContent).toContain("Dominant");
    const blockedRow = screen.getByText("Blocked").closest("div");
    expect(blockedRow?.textContent).toContain("Active");
    expect(blockedRow?.textContent).toContain("Dominant");
    // Canonical reason rendered with friendly text, not the raw code alone.
    expect(blockedRow?.textContent).toContain("No supporting Structure Graph edges");
    // Raw diagnostic detail is present but collapsed behind a <details>.
    expect(screen.getByText("Full diagnostic detail")).toBeInTheDocument();
    // The raw level tokens remain available verbatim under Technical details.
    expect(screen.getByText("Target level (raw)").closest("div")?.textContent).toContain("dominant");
    expect(screen.getByText("Qualified level (raw)").closest("div")?.textContent).toContain("active");
  });

  // QA Closure v0.1.2 Item 4 (Alpha Level Display Alignment).
  it("shows capped_active (not plain active) and a Cap reason row for a qualification-capped Alpha", () => {
    // Real A301 shape, run 5ffe121a-68fd-473b-82b5-c9465332d8a2.
    renderCard({
      status: "active",
      activationScore: 70.0,
      activation: makeActivation({
        status: "active",
        activation_score: 70.0,
        uncapped_score: 71.8756,
        target_level: "dominant",
        qualified_level: "active",
        is_blocked: true,
        blocked_from: ["dominant"],
        blocked_reason_codes: ["NO_LOCAL_STRUCTURE_SUPPORT"],
        diagnostic_reason_codes: ["NO_LOCAL_STRUCTURE_SUPPORT"],
        classification_version: "b4.alpha_level.v1",
        activation_level: "capped_active",
      }),
    });
    // Product Demo Hardening Phase 2D: the default label is the translated
    // "Active" (capped_active and plain active are both "Active" from a
    // stakeholder's perspective) -- never the raw "capped_active" token.
    const levelRow = screen.getByText("Activation level").closest("div");
    expect(levelRow?.querySelector("dd")?.textContent).toBe("Active");
    const capReasonRow = screen.getByText("Cap reason").closest("div");
    expect(capReasonRow?.textContent).not.toContain("NO_LOCAL_STRUCTURE_SUPPORT");
    expect(capReasonRow?.textContent).toContain("No supporting Structure Graph edges");
    // The raw "capped_active" token remains available verbatim under
    // Technical details -- the distinction is relocated, never destroyed.
    expect(screen.getByText("Raw activation level").closest("div")?.textContent).toContain("capped_active");
    expect(screen.getByText("Cap reason codes (raw)").closest("div")?.textContent).toContain(
      "NO_LOCAL_STRUCTURE_SUPPORT"
    );
    // The underlying score is never hidden.
    expect(screen.getByText("Activation score").closest("div")?.textContent).toContain("70.0");
    // The existing, richer "Blocked" row is preserved alongside the new
    // Cap reason row -- never removed.
    expect(screen.getByText("Blocked")).toBeInTheDocument();
  });

  it("shows plain active (no Cap reason row) for a genuinely uncapped Active Alpha", () => {
    renderCard({
      status: "active",
      activationScore: 63.1,
      activation: makeActivation({
        status: "active",
        activation_score: 63.1,
        uncapped_score: 63.1,
        target_level: "active",
        qualified_level: "active",
        is_blocked: false,
        blocked_from: [],
        blocked_reason_codes: [],
        diagnostic_reason_codes: [],
        classification_version: "b4.alpha_level.v1",
        activation_level: "active",
      }),
    });
    expect(screen.getByText("Activation level").closest("div")?.querySelector("dd")?.textContent).toBe("Active");
    expect(screen.queryByText("Cap reason")).not.toBeInTheDocument();
    expect(screen.queryByText("Blocked")).not.toBeInTheDocument();
  });

  it("shows plain dominant, never capped_active, for a genuinely qualified Dominant Alpha", () => {
    renderCard({
      status: "dominant",
      activationScore: 84.5,
      activation: makeActivation({
        status: "dominant",
        activation_score: 84.5,
        uncapped_score: 84.5,
        target_level: "dominant",
        qualified_level: "dominant",
        is_blocked: false,
        blocked_from: [],
        blocked_reason_codes: [],
        diagnostic_reason_codes: [],
        classification_version: "b4.alpha_level.v1",
        activation_level: "dominant",
      }),
    });
    expect(screen.getByText("Activation level").closest("div")?.querySelector("dd")?.textContent).toBe("Dominant");
    expect(screen.queryByText("Cap reason")).not.toBeInTheDocument();
  });

  it("shows Dominant (translated), never raw regime_level or capped_active, for a genuinely qualified Regime-level Alpha -- raw value preserved under Technical details", () => {
    renderCard({
      status: "regime_level",
      activationScore: 86.9,
      activation: makeActivation({
        status: "regime_level",
        activation_score: 86.9,
        uncapped_score: 86.9,
        target_level: "regime_level",
        qualified_level: "regime_level",
        is_blocked: false,
        blocked_from: [],
        blocked_reason_codes: [],
        diagnostic_reason_codes: [],
        classification_version: "b4.alpha_level.v1",
        activation_level: "regime_level",
        regime_gate_passed: true,
      }),
    });
    // Product Demo Hardening Phase 2D: regime_level is a sustained/
    // confirmed form of Dominant from a stakeholder's perspective, and is
    // translated to the same "Dominant" product word -- never the raw
    // "regime_level" token.
    expect(screen.getByText("Activation level").closest("div")?.querySelector("dd")?.textContent).toBe("Dominant");
    expect(screen.queryByText("Cap reason")).not.toBeInTheDocument();
    // The raw distinction is not destroyed -- it remains available verbatim
    // under Technical details.
    expect(screen.getByText("Raw activation level").closest("div")?.textContent).toContain("regime_level");
  });

  it("falls back to the legacy status for Activation level on a payload predating activation_level, but still shows the existing Blocked row", () => {
    // Same fixture as the pre-existing "shows target level, blocked-from..."
    // test above, which never sets activation_level -- confirms the
    // fallback (activation?.activation_level ?? status) degrades exactly
    // to prior behavior, never crashes, never fabricates "capped_active".
    renderCard({
      status: "active",
      activation: makeActivation({
        status: "active",
        target_level: "dominant",
        qualified_level: "active",
        is_blocked: true,
        blocked_from: ["dominant"],
        blocked_reason_codes: ["NO_LOCAL_STRUCTURE_SUPPORT"],
        diagnostic_reason_codes: ["NO_LOCAL_STRUCTURE_SUPPORT"],
        classification_version: "b4.alpha_level.v1",
      }),
    });
    expect(screen.getByText("Activation level").closest("div")?.querySelector("dd")?.textContent).toBe("Active");
    expect(screen.queryByText("Cap reason")).not.toBeInTheDocument();
    expect(screen.getByText("Blocked")).toBeInTheDocument();
  });

  it("never shows a Blocked row for a qualified (non-blocked) alpha", () => {
    renderCard({
      status: "dominant",
      activation: makeActivation({
        status: "dominant",
        target_level: "dominant",
        qualified_level: "dominant",
        is_blocked: false,
        blocked_from: [],
        blocked_reason_codes: [],
        diagnostic_reason_codes: [],
        classification_version: "b4.alpha_level.v1",
      }),
    });
    expect(screen.queryByText("Blocked")).not.toBeInTheDocument();
    // target_level == qualified_level here, so the Target level row (only
    // shown when the two diverge) must not render either.
    expect(screen.queryByText("Target level")).not.toBeInTheDocument();
  });

  it("falls back to a legacy-classification note for a historical payload predating B4", () => {
    // makeActivation()'s own defaults never set target_level/
    // qualified_level -- exactly a payload saved before task
    // B4_ACTIVATION_LEVEL_ALIGNMENT shipped. Must not crash, must not
    // fabricate a level, must label it explicitly.
    renderCard({ status: "active", activation: makeActivation() });
    expect(
      screen.getByText("Legacy classification — this run predates the B4 alpha-level classifier")
    ).toBeInTheDocument();
    expect(screen.queryByText("Blocked")).not.toBeInTheDocument();
  });

  it("renders nothing B4-specific when no activation entry is supplied at all", () => {
    renderCard({ status: "active", activation: null });
    expect(screen.queryByText("Legacy classification — this run predates the B4 alpha-level classifier")).not.toBeInTheDocument();
    expect(screen.queryByText("Blocked")).not.toBeInTheDocument();
    expect(screen.queryByText("Target level")).not.toBeInTheDocument();
  });

  // Product Demo Hardening Phase 2D, Section 24: an unrecognized future
  // activation-level value must never crash the card, and must never be
  // silently misrepresented as a known state (Active/Dominant/Emerging).
  it("does not crash on an unrecognized future activation level and does not misrepresent it as a known state", () => {
    renderCard({ status: "some_future_level" as never });
    const levelRow = screen.getByText("Activation level").closest("div");
    const shown = levelRow?.querySelector("dd")?.textContent ?? "";
    expect(shown.length).toBeGreaterThan(0);
    expect(["Active", "Dominant", "Emerging", "Watchlist", "Inactive"]).not.toContain(shown);
  });
});

// John Follow-Up Requirement A (Invalidation-Condition Coverage
// Completion): AlphaCard renders whatever invalidationConditions prop it is
// given -- it never special-cases A101, and never fetches anything itself
// (the Alpha Library fetch happens once, upstream, in useAlphaLibrary).
describe("AlphaCard invalidation conditions", () => {
  it("renders A101's taxonomy invalidation conditions", () => {
    renderCard({
      alphaId: "A101",
      alphaName: "AI Expansion",
      invalidationConditions: ["AI capex cuts", "model demand slows", "GPU oversupply"],
    });
    expect(screen.getByText("Invalidation conditions")).toBeInTheDocument();
    expect(screen.getByText("AI capex cuts")).toBeInTheDocument();
    expect(screen.getByText("model demand slows")).toBeInTheDocument();
    expect(screen.getByText("GPU oversupply")).toBeInTheDocument();
  });

  it("renders a second, non-A101 Alpha's conditions from the exact same prop/source -- proving no hardcoded A101-only path remains", () => {
    renderCard({
      alphaId: "A201",
      alphaName: "Semiconductor Supercycle",
      invalidationConditions: ["inventory glut returns", "order cuts resume"],
    });
    expect(screen.getByText("Invalidation conditions")).toBeInTheDocument();
    expect(screen.getByText("inventory glut returns")).toBeInTheDocument();
    expect(screen.getByText("order cuts resume")).toBeInTheDocument();
  });

  it("renders conditions as plain, human-readable list text -- never raw YAML/JSON syntax", () => {
    renderCard({ invalidationConditions: ["revenue misses, guide-down, demand weakens"] });
    const item = screen.getByText("revenue misses, guide-down, demand weakens");
    expect(item.tagName).toBe("LI");
    expect(item.textContent).not.toMatch(/[{}[\]"]|:\s/);
  });

  it("shows an honest fallback, not a hidden section or invented content, when the taxonomy defines zero conditions", () => {
    renderCard({ invalidationConditions: [] });
    expect(screen.getByText("Invalidation conditions")).toBeInTheDocument();
    expect(
      screen.getByText("No validated invalidation condition is currently defined for this Alpha.")
    ).toBeInTheDocument();
    expect(screen.queryByRole("listitem")).not.toBeInTheDocument();
  });

  it("renders no invalidation section at all while the Alpha Library hasn't loaded (undefined), never a false null/undefined display", () => {
    renderCard({ invalidationConditions: undefined });
    expect(screen.queryByText("Invalidation conditions")).not.toBeInTheDocument();
    expect(screen.queryByText("null")).not.toBeInTheDocument();
    expect(screen.queryByText("undefined")).not.toBeInTheDocument();
  });

  it("never labels taxonomy conditions as approved or John-approved -- that provenance claim is not supported for this source", () => {
    renderCard({ invalidationConditions: ["AI capex cuts"] });
    expect(screen.queryByText(/John-approved/i)).not.toBeInTheDocument();
    expect(screen.queryByText(/^Approved/)).not.toBeInTheDocument();
  });

  it("makes clear these conditions come from the Alpha's own definition, not the current run's analysis", () => {
    renderCard({ invalidationConditions: ["AI capex cuts"] });
    expect(screen.getByText("From this Alpha's definition, not this run's analysis.")).toBeInTheDocument();
  });
});
