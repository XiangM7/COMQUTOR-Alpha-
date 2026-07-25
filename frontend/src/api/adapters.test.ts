import { describe, expect, it } from "vitest";
import { adaptCanonicalResearchResponse } from "./adapters";

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
