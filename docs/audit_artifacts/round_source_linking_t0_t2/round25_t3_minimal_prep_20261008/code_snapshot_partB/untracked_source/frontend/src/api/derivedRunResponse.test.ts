import { existsSync, readFileSync } from "node:fs";
import { resolve } from "node:path";
import { describe, expect, it } from "vitest";
import { adaptCanonicalResearchResponse } from "./adapters";

// Round 15: the canonical responses of a DERIVED alpha-classification recovery run and of the original run it
// is based on, captured from the real API route by tests/test_classification_recovery_derived_run.py (set
// COMQUTOR_CAPTURE_API_RESPONSES_DIR to regenerate). The derived run is built from the frozen c904d4cc inputs
// with a FAKE HTTP transport: its classification decisions are test doubles, so only the SHAPE and the
// disclosure fields are asserted here -- never anything about real AMD classification quality.
const FIXTURE_DIR = resolve(
  import.meta.dirname,
  "../../../docs/audit_artifacts/round_source_linking_t0_t2/round15_recovery_prep_20261006/ui_fixture",
);
const DERIVED = resolve(FIXTURE_DIR, "derived_run_api_response_fake_http.json");
const ORIGINAL = resolve(FIXTURE_DIR, "original_run_api_response_as_frozen.json");

function load(path: string): unknown {
  return (JSON.parse(readFileSync(path, "utf-8")) as { response: unknown }).response;
}

describe.skipIf(!existsSync(DERIVED) || !existsSync(ORIGINAL))("derived recovery run, as the UI adapter reads it", () => {
  it("adapts the derived run's canonical response, ignoring the additive lineage block", () => {
    const result = adaptCanonicalResearchResponse(load(DERIVED));
    expect(result.ok).toBe(true);
    if (!result.ok) return;
    expect(result.value.status).toBe("completed");
    expect(result.value.run_id.startsWith("recovery-")).toBe(true);
    expect(result.value.structure_graph_status).toBe("ready");
    expect(result.value.conflict_status).toBe("ready");
    expect(result.value.alpha_classification_completion).toMatchObject({
      total_claims: 975,
      call_failure_count: 0,
      not_executed_count: 0,
      complete: true,
    });
    expect(result.value.alpha_classification_status).toMatch(/^complete_/);
  });

  it("shows the original run as incomplete and the derived run as complete from the same 975 claims", () => {
    const original = adaptCanonicalResearchResponse(load(ORIGINAL));
    const derived = adaptCanonicalResearchResponse(load(DERIVED));
    expect(original.ok && derived.ok).toBe(true);
    if (!original.ok || !derived.ok) return;
    expect(original.value.alpha_classification_status).toBe("incomplete");
    expect(original.value.alpha_classification_completion).toMatchObject({
      total_claims: 975,
      call_failure_count: 973,
      complete: false,
    });
    expect(derived.value.alpha_classification_completion?.total_claims).toBe(
      original.value.alpha_classification_completion?.total_claims,
    );
    expect(derived.value.alpha_classification_completion?.complete).toBe(true);
  });
});
