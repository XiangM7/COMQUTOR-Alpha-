import { describe, expect, it } from "vitest";
import { adaptEvidenceTraceItemResponse, adaptKeyConclusionsResponse } from "./evidenceTrace";
import claim31 from "./__fixtures__/evidence_trace_claim_31.json";
import claim33 from "./__fixtures__/evidence_trace_claim_33.json";
import claim10 from "./__fixtures__/evidence_trace_claim_10_a304.json";
import keyConclusions from "./__fixtures__/evidence_key_conclusions.json";
import legacyConflictClaim from "./__fixtures__/evidence_trace_conflict_legacy_claim_90.json";

// The fixtures are REAL responses of GET /api/research/{run}/evidence-trace produced by the backend from a trimmed copy
// of the saved AMD records (tests/fixtures/t1_closure_amd_excerpt.json) -- not hand-written payloads. The adapter must
// carry every field the UI shows: a field the adapter drops never reaches the browser, whatever the type says.

describe("adaptEvidenceTraceItemResponse", () => {
  it("carries claim 31's source material, location, verification and scoring through the adapter", () => {
    const adapted = adaptEvidenceTraceItemResponse(claim31);
    expect(adapted.ok).toBe(true);
    if (!adapted.ok) return;
    const item = adapted.value.item;
    expect(item.source_support.status_code).toBe("VERIFIED_SUPPORT");
    expect(item.source_support.content_support.used_location).toBe("excerpt and data_snapshot.periods for Total Revenue");
    expect(item.source_support.content_support.supporting_quote_or_data).toContain("2026-06-30=11536000000.0");
    expect(item.source_support.content_support.support_basis).toBe("DIRECT_FACT");
    expect(item.source_support.eligible).toBe(true);
    expect(item.source_support.eligibility_time_basis?.basis).toBe("REGISTRY_WRITE_TIME_UPPER_BOUND");
    const source = item.sources[0];
    expect(source?.role).toBe("verified_basis");
    expect(source?.fragment_id).toBe("src_582ac24bf4319648:frag:0");
    expect(source?.content_hash).toMatch(/^[0-9a-f]{64}$/);
    expect(source?.material_rows[0]?.label).toBe("Total Revenue");
    expect(source?.material_rows[0]?.cells.map((cell) => cell.used)).toEqual([true, true, true, true, true]);
    expect(source?.material_rows[0]?.cells[0]?.token).toBe("$11,536M");
    expect(item.alpha_match.matched_alpha).toBe("A301");
    expect(item.stance.method).toBe("deterministic");
    expect(item.scoring.in_official_pool).toBe(true);
    expect(item.scoring.weight_contribution).toBeCloseTo(0.1873);
    expect(item.scoring.alpha_result?.claims_in_pool).toBe(3);
    expect(item.scoring.alpha_result?.independent_facts).toBe(2);
    expect(item.scoring.fact_group?.member_claim_ids).toHaveLength(2);
    expect(item.scoring.fact_group?.source_role).toBe("PRIMARY_RESEARCH");
    expect(item.dependency.depended_by).toHaveLength(1);
    expect(item.claim.paragraph).toContain("Revenue acceleration is dramatic");
  });

  it("carries the dependency of claim 33 on claim 31 and keeps its own citation", () => {
    const adapted = adaptEvidenceTraceItemResponse(claim33);
    expect(adapted.ok).toBe(true);
    if (!adapted.ok) return;
    const item = adapted.value.item;
    expect(item.dependency.depends_on?.endsWith(":claim:31")).toBe(true);
    expect(item.dependency.same_evidence_fact_members).toHaveLength(2);
    expect(item.sources[0]?.source_id).toBe("src_582ac24bf4319648");
  });

  it("carries an unresolved relation as unresolved, with its reason", () => {
    const adapted = adaptEvidenceTraceItemResponse(claim10);
    expect(adapted.ok).toBe(true);
    if (!adapted.ok) return;
    const item = adapted.value.item;
    expect(item.source_support.status_code).toBe("VERIFIED_SUPPORT");
    expect(item.stance.status_code).toBe("RELATION_UNRESOLVED");
    expect(item.stance.reason).toContain("No model stance judgment was obtained");
    expect(item.scoring.not_scored_code).toBe("RELATION_NOT_SUPPORTING");
  });

  it("carries the numbers a claim states that no saved cell holds, and none when every number was found", () => {
    const flagged = adaptEvidenceTraceItemResponse(claim10);
    const clean = adaptEvidenceTraceItemResponse(claim31);
    expect(flagged.ok && flagged.value.item.numbers_not_found_in_saved_data).toEqual(["$1.38"]);
    expect(clean.ok && clean.value.item.numbers_not_found_in_saved_data).toEqual([]);
  });

  it("carries the saved historical use of a claim in a conflict and the legacy-run basis (REAL historical data)", () => {
    const adapted = adaptEvidenceTraceItemResponse(legacyConflictClaim);
    expect(adapted.ok).toBe(true);
    if (!adapted.ok) return;
    const item = adapted.value.item;
    const main = item.conflict_adoption.entries.filter((e) => e.conflict_id === "A301__A304");
    expect(main.map((e) => e.side).sort()).toEqual(["bear", "counter"]); // every saved placement is carried, none chosen
    expect(main.every((e) => e.conflict_status === "admitted" && e.conflict_level === "low" && e.conflict_score === 14.2594 && e.is_main_conflict)).toBe(true);
    expect(item.conflict_adoption.note).toContain("unchanged by anything shown in the current basis");
    expect(item.run_basis.link_fields_saved).toBe(false);
    expect(item.run_basis.note).toContain("saved before source linking existed");
    expect(item.source_support.reason_code).toBe("RUN_PREDATES_SOURCE_LINKING");
    expect(item.source_support.status_code).toBe("NOT_LINKED");
  });

  it("treats an older saved trace without the new fields as a run with link fields and no conflict use", () => {
    const old = JSON.parse(JSON.stringify(claim31)) as { item: Record<string, unknown> };
    delete old.item.conflict_adoption;
    delete old.item.run_basis;
    const adapted = adaptEvidenceTraceItemResponse(old);
    expect(adapted.ok).toBe(true);
    if (!adapted.ok) return;
    expect(adapted.value.item.conflict_adoption).toEqual({ entries: [], note: null });
    expect(adapted.value.item.run_basis).toEqual({ link_fields_saved: true, note: null });
    expect(adapted.value.item.sources[0]?.derived_inputs ?? null).toBeNull();
  });

  it("carries the derived-input status of a source: saved and recomputed, or not saved", () => {
    const payload = JSON.parse(JSON.stringify(claim31)) as { item: { sources: Array<Record<string, unknown>> } };
    const firstSource = payload.item.sources[0];
    if (!firstSource) throw new Error("fixture has no source");
    firstSource.derived_inputs = {
      status: "SAVED", method: "stockstats", version: "stockstats==0.6.8", row_count: 1255, first_date: "2021-10-06", last_date: "2026-10-06",
      series_hash_ok: true, registry_pointer_matches: true, recomputation: { status: "REPRODUCED", indicators_checked: 11, mismatched: [], version_match: true }, note: "n",
    };
    const saved = adaptEvidenceTraceItemResponse(payload);
    expect(saved.ok && saved.value.item.sources[0]?.derived_inputs).toMatchObject({
      status: "SAVED", row_count: 1255, recomputation_status: "REPRODUCED", recomputation_indicators_checked: 11, series_hash_ok: true,
    });
    firstSource.derived_inputs = { status: "NOT_SAVED", method: "stockstats", version: "stockstats==0.6.8", window_parameters: { row_count: 1255, window_start: "2021-10-06", window_end: "2026-10-06" }, note: "n" };
    const notSaved = adaptEvidenceTraceItemResponse(payload);
    expect(notSaved.ok && notSaved.value.item.sources[0]?.derived_inputs).toMatchObject({ status: "NOT_SAVED", row_count: 1255, first_date: "2021-10-06", last_date: "2026-10-06" });
  });

  it("rejects a payload that lacks one of the four statuses", () => {
    const broken = JSON.parse(JSON.stringify(claim31)) as { item: Record<string, unknown> };
    delete broken.item.stance;
    expect(adaptEvidenceTraceItemResponse(broken).ok).toBe(false);
    expect(adaptEvidenceTraceItemResponse({ run_id: "r" }).ok).toBe(false);
  });
});

describe("adaptKeyConclusionsResponse", () => {
  it("keeps every row's four statuses and the Agent-wording flag", () => {
    const adapted = adaptKeyConclusionsResponse(keyConclusions);
    expect(adapted.ok).toBe(true);
    if (!adapted.ok) return;
    const view = adapted.value.key_conclusions;
    const rows = view.groups.flatMap((group) => group.rows);
    expect(rows.length).toBe(view.claim_count);
    expect(rows.every((row) => row.source_support.status_code && row.alpha_match.status_code && row.stance.status_code && row.scoring.status_code)).toBe(true);
    const verifiedWording = rows.filter((row) => row.agent_wording.self_labeled_verified);
    expect(verifiedWording.length).toBe(view.agent_wording_verified_count);
    expect(verifiedWording[0]?.source_support.status_code).toBe("NOT_LINKED");
    expect(view.rule).toContain("final-decision agents");
  });
});
