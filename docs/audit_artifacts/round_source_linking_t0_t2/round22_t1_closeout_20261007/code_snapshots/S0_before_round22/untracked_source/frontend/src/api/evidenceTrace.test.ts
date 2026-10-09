import { describe, expect, it } from "vitest";
import { adaptEvidenceTraceItemResponse, adaptKeyConclusionsResponse } from "./evidenceTrace";
import claim31 from "./__fixtures__/evidence_trace_claim_31.json";
import claim33 from "./__fixtures__/evidence_trace_claim_33.json";
import claim10 from "./__fixtures__/evidence_trace_claim_10_a304.json";
import keyConclusions from "./__fixtures__/evidence_key_conclusions.json";

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
