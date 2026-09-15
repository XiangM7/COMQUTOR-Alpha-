import { describe, expect, it } from "vitest";
import { adaptAlphaLibraryResponse, adaptCanonicalResearchResponse } from "./adapters";

const VALID_ARTIFACTS = {
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

function validPayload(overrides: Record<string, unknown> = {}) {
  return {
    run_id: "run-1",
    ticker: "MU",
    status: "completed",
    artifacts: VALID_ARTIFACTS,
    agent_output_count: 1,
    structured_output_count: 1,
    structure_graph_status: "ready",
    dominant_alphas: [],
    main_conflict: null,
    conflict_status: "ready",
    summary: "Summary.",
    data_sanity_status: "ok",
    data_sanity_warning_count: 0,
    data_sanity_critical_count: 0,
    data_sanity_warnings: [],
    ...overrides,
  };
}

describe("adaptCanonicalResearchResponse -- Data Sanity Cross-Check v1 contract", () => {
  it("accepts a valid ok payload with the additive fields", () => {
    const result = adaptCanonicalResearchResponse(validPayload());
    expect(result.ok).toBe(true);
    if (result.ok) {
      expect(result.value.data_sanity_status).toBe("ok");
      expect(result.value.data_sanity_warnings).toEqual([]);
    }
  });

  it("accepts every documented status value", () => {
    for (const status of ["ok", "warning", "critical", "unavailable", "disabled", "not_available"]) {
      const result = adaptCanonicalResearchResponse(validPayload({ data_sanity_status: status }));
      expect(result.ok, `status ${status} should be accepted`).toBe(true);
    }
  });

  it("rejects an unrecognized data_sanity_status as a contract mismatch, not a silent coercion", () => {
    const result = adaptCanonicalResearchResponse(validPayload({ data_sanity_status: "totally_made_up" }));
    expect(result.ok).toBe(false);
  });

  it("rejects a missing data_sanity_status", () => {
    const payload = validPayload();
    delete (payload as Record<string, unknown>).data_sanity_status;
    const result = adaptCanonicalResearchResponse(payload);
    expect(result.ok).toBe(false);
  });

  it("rejects an unrecognized warning severity", () => {
    const result = adaptCanonicalResearchResponse(
      validPayload({
        data_sanity_status: "warning",
        data_sanity_warnings: [{ code: "X", severity: "super_bad", message: "msg", details: {} }],
      })
    );
    expect(result.ok).toBe(false);
  });

  it("rejects a warning whose details is not an object", () => {
    const result = adaptCanonicalResearchResponse(
      validPayload({
        data_sanity_status: "warning",
        data_sanity_warnings: [{ code: "X", severity: "warning", message: "msg", details: "not an object" }],
      })
    );
    expect(result.ok).toBe(false);
  });

  it("rejects a non-array data_sanity_warnings", () => {
    const result = adaptCanonicalResearchResponse(validPayload({ data_sanity_warnings: "not an array" }));
    expect(result.ok).toBe(false);
  });

  it("parses a full warning entry's safe fields", () => {
    const result = adaptCanonicalResearchResponse(
      validPayload({
        data_sanity_status: "warning",
        data_sanity_warning_count: 1,
        data_sanity_warnings: [
          {
            code: "REPORTED_PRICE_MISMATCH",
            severity: "warning",
            message: "A price mentioned in a structured analyst claim does not match the external market reference.",
            details: { claim_id: "c1", reported_price: 108.0, external_reference: 100.0 },
          },
        ],
      })
    );
    expect(result.ok).toBe(true);
    if (result.ok) {
      const [warning] = result.value.data_sanity_warnings;
      expect(warning?.code).toBe("REPORTED_PRICE_MISMATCH");
      expect(warning?.details.reported_price).toBe(108.0);
    }
  });
});

describe("adaptCanonicalResearchResponse -- Alpha Memory (Implementation Step 4B)", () => {
  const VALID_ALPHA_MEMORY = {
    mode: "shadow",
    activation_modulation_applied: false,
    identity_model: "atomic_edge_phi",
    identity_version: "alpha_memory.phi_edge.v1",
    phi_structures: [
      {
        phi_id: "abc123",
        ticker: "NVDA",
        alpha_id: "A101",
        source: "ai_capex",
        edge_type: "causal",
        target: "gpu_demand",
        is_recurring: true,
        has_prior_observation: true,
        prior_observation_count: 3,
        prior_run_ids: ["r1", "r2", "r3"],
        first_seen: "2026-08-01T00:00:00Z",
        last_seen_prior: "2026-08-10T00:00:00Z",
      },
    ],
    alpha_memory_summary: [
      {
        alpha_id: "A101",
        current_phi_count: 1,
        first_seen_phi_count: 0,
        recurring_phi_count: 1,
        recurrence_ratio: 1,
        prior_observation_total: 3,
      },
    ],
    aggregate_fingerprints: [{ aggregate_fingerprint_id: "agg1", alpha_id: "A101" }],
    instability_signals: { alpha_attribution_variance: [], edge_type_variance: [] },
  };

  it("adapts a well-formed alpha_memory section verbatim", () => {
    const result = adaptCanonicalResearchResponse(validPayload({ alpha_memory: VALID_ALPHA_MEMORY }));
    expect(result.ok).toBe(true);
    if (result.ok) {
      expect(result.value.alpha_memory?.mode).toBe("shadow");
      expect(result.value.alpha_memory?.activation_modulation_applied).toBe(false);
      expect(result.value.alpha_memory?.phi_structures).toHaveLength(1);
      expect(result.value.alpha_memory?.phi_structures[0]?.phi_id).toBe("abc123");
      expect(result.value.alpha_memory?.alpha_memory_summary[0]?.recurrence_ratio).toBe(1);
    }
  });

  it("returns null (never fabricated) when alpha_memory is explicitly null", () => {
    const result = adaptCanonicalResearchResponse(validPayload({ alpha_memory: null }));
    expect(result.ok).toBe(true);
    if (result.ok) {
      expect(result.value.alpha_memory).toBeNull();
    }
  });

  it("returns undefined (never fabricated) when alpha_memory is absent from the payload", () => {
    const result = adaptCanonicalResearchResponse(validPayload());
    expect(result.ok).toBe(true);
    if (result.ok) {
      expect(result.value.alpha_memory).toBeUndefined();
    }
  });

  it("rejects (returns undefined) a payload where activation_modulation_applied is not false, never silently coerced", () => {
    const result = adaptCanonicalResearchResponse(
      validPayload({ alpha_memory: { ...VALID_ALPHA_MEMORY, activation_modulation_applied: true } })
    );
    expect(result.ok).toBe(true);
    if (result.ok) {
      expect(result.value.alpha_memory).toBeUndefined();
    }
  });

  it("never fails the whole research response when alpha_memory is malformed", () => {
    const result = adaptCanonicalResearchResponse(validPayload({ alpha_memory: { garbage: true } }));
    expect(result.ok).toBe(true);
    if (result.ok) {
      expect(result.value.alpha_memory).toBeUndefined();
      expect(result.value.run_id).toBe("run-1");
    }
  });

  it("drops individual malformed phi_structures/summary entries without failing the section", () => {
    const result = adaptCanonicalResearchResponse(
      validPayload({
        alpha_memory: {
          ...VALID_ALPHA_MEMORY,
          phi_structures: [VALID_ALPHA_MEMORY.phi_structures[0], { missing: "fields" }],
        },
      })
    );
    expect(result.ok).toBe(true);
    if (result.ok) {
      expect(result.value.alpha_memory?.phi_structures).toHaveLength(1);
    }
  });
});

function validAlphaLibraryEntry(overrides: Record<string, unknown> = {}) {
  return {
    alpha_id: "A101",
    name_en: "AI Expansion",
    name_cn: "AI 扩张",
    layer: "Theme",
    status: "active",
    core_thesis: "AI infrastructure demand drives growth.",
    keywords: ["AI"],
    trigger_signals: ["capex growth"],
    confirmation_signals: ["earnings beat"],
    beneficiary_assets: ["NVDA"],
    risk_assets: [],
    conflict_alphas: [{ alpha_id: "A304", contradiction_weight: 0.9 }],
    invalidation_conditions: ["AI capex cuts", "model demand slows", "GPU oversupply"],
    agent_sources: ["news_agent"],
    ...overrides,
  };
}

describe("adaptAlphaLibraryResponse -- GET /api/alpha-library (John Follow-Up Requirement A)", () => {
  it("accepts a valid payload and preserves each Alpha's invalidation_conditions verbatim", () => {
    const result = adaptAlphaLibraryResponse({
      schema_version: "week1.alpha_library.v1",
      alpha_count: 1,
      alphas: [validAlphaLibraryEntry()],
    });
    expect(result.ok).toBe(true);
    if (result.ok) {
      expect(result.value.alphas).toHaveLength(1);
      expect(result.value.alphas[0]?.invalidation_conditions).toEqual([
        "AI capex cuts",
        "model demand slows",
        "GPU oversupply",
      ]);
    }
  });

  it("accepts an Alpha with a genuinely empty invalidation_conditions list -- never rejected as malformed", () => {
    const result = adaptAlphaLibraryResponse({
      schema_version: "week1.alpha_library.v1",
      alpha_count: 1,
      alphas: [validAlphaLibraryEntry({ invalidation_conditions: [] })],
    });
    expect(result.ok).toBe(true);
    if (result.ok) {
      expect(result.value.alphas[0]?.invalidation_conditions).toEqual([]);
    }
  });

  it("rejects a payload missing alphas", () => {
    const result = adaptAlphaLibraryResponse({ schema_version: "week1.alpha_library.v1", alpha_count: 0 });
    expect(result.ok).toBe(false);
  });

  it("rejects an entry with a non-string invalidation_conditions item", () => {
    const result = adaptAlphaLibraryResponse({
      schema_version: "week1.alpha_library.v1",
      alpha_count: 1,
      alphas: [validAlphaLibraryEntry({ invalidation_conditions: [42] })],
    });
    expect(result.ok).toBe(false);
  });
});
