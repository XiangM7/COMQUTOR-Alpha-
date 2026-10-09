"""T1: AMD's original 34 conflict-evidence item ledger.

Locates the exact origin of "34": docs/audit_artifacts/
v0_2_mvp_functional_completeness_audit_final.json, row 8 ("Conflict-evidence
external source display"): "Live-verified for AMD's real conflict: 0/34
bull/bear/counter evidence items matched a captured source this run".
Re-inspecting AMD's run d5b60b8a-66b8-44c1-9f55-ee345e58c48d's CURRENTLY
persisted conflicts.json confirms this is main_conflict A301__A304's own
evidence_ui: 15 bull + 17 bear + 2 counter = 34, exactly matching -- no
discrepancy to report for the count itself (recorded honestly either way).

For each of the 34 items this script re-applies TWO mechanisms against
AMD's real, already-persisted 46-source registry:

  1. legacy: source_provenance.resolve_external_source_for_claim (title-
     substring match) -- the same function API/export code already calls.
  2. NEW (this round's T1 chain): source_provenance.
     match_evidence_to_source_candidates (content/excerpt-based) followed
     by validate_source_reference (the real ID-based backend gate) --
     the mechanism comqutor_alpha.structure_engine.structured_output_
     adapter._annotate_source_link now runs for every FRESH extraction.

AMD's registry was captured BEFORE this round's fetch-stage excerpt
capture (tradingagents/dataflows/yfinance_news.py's _capture_news_source
did not yet record `excerpt`) -- every one of its 46 sources has
excerpt=None. match_evidence_to_source_candidates therefore cannot
propose a single candidate for any of the 34 items, regardless of wording:
this is reported honestly below as NOT_PROVIDED for all 34, not silently
upgraded and not hidden. tests/test_t1_source_linking_pipeline.py's own
Scenario A proves the SAME new mechanism DOES produce a VALID link end to
end when the registry actually carries a captured excerpt (i.e. for any
run captured after this round's fetch-stage change) -- AMD's own historical
registry is simply too old to have one, which is exactly the follow-up
Fresh Run gap this ledger flags below.

Separately records the already-existing B1 stance classification as each
item's support method -- never treating source-linkage success as proof of
support, and never treating stance alone as proof of source traceability.
No re-adjudication: the conflict's own admission/score is untouched; this
is a traceability audit layered on top of already-persisted data (Type A,
zero Provider calls)."""
from __future__ import annotations

import json
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(REPO_ROOT))

from comqutor_alpha.source_provenance import (
    match_evidence_to_source_candidates,
    public_source_fields,
    resolve_external_source_for_claim,
    validate_source_reference,
)

RUN_ID = "d5b60b8a-66b8-44c1-9f55-ee345e58c48d"
RUN_DIR = REPO_ROOT / "outputs" / "runs" / RUN_ID

ORIGINAL_AUDIT_CITATION = {
    "file": "docs/audit_artifacts/v0_2_mvp_functional_completeness_audit_final.json",
    "row": 8,
    "quote": (
        "Live-verified for AMD's real conflict: 0/34 bull/bear/counter evidence items "
        "matched a captured source this run -- an honest, statistically unsurprising "
        "outcome given the same ~0.3% overall match rate, not a defect in the mechanism."
    ),
}


def _item_ledger_entry(side: str, item: dict, sources: list[dict], evidence_cutoff: str | None) -> dict:
    evidence_text = item.get("evidence_text") or ""
    claim_text = item.get("claim_text") or None
    target_alpha = item.get("target_alpha_id") or item.get("counter_target_alpha_id")

    # Legacy mechanism (title-substring match).
    matched_source, external_status = resolve_external_source_for_claim(
        claim=None, evidence=evidence_text, sources=sources
    )
    original_linkage_status = "UNAVAILABLE"  # per the cited prior audit: 0/34 matched at that time
    post_fix_legacy_linkage_status = external_status

    # NEW T1 mechanism (content/excerpt-based candidate + real ID validation
    # gate) -- the same two-step _annotate_source_link now runs for every
    # freshly-extracted claim.
    new_candidates = match_evidence_to_source_candidates(evidence_text, claim_text, sources)
    if new_candidates:
        new_result = validate_source_reference(new_candidates[0], sources=sources, evidence_cutoff=evidence_cutoff)
    else:
        new_result = validate_source_reference(None, sources=sources, evidence_cutoff=evidence_cutoff)
    new_source_link_status = new_result["source_link_status"]
    new_content_support_status = "PENDING_REVIEW" if new_source_link_status == "VALID" else "NOT_APPLICABLE"

    # T1 follow-up (2026-09-28): a specific, per-item reason for
    # NOT_PROVIDED -- never a bare, unexplained status. Distinguishes "no
    # candidate could even be proposed" (the AMD-wide case: the registry
    # this run persisted has zero sources with a captured excerpt, so
    # match_evidence_to_source_candidates structurally has nothing to match
    # against) from a genuinely different per-item reason (kept general so
    # a future run with a partially-excerpted registry reports honestly
    # per item, not with a single blanket note).
    sources_with_excerpt_count = sum(1 for s in sources if s.get("excerpt"))
    if new_source_link_status != "VALID":
        if not new_candidates:
            if sources_with_excerpt_count == 0:
                blocker_detail = (
                    f"NO_CANDIDATE_PROPOSED: this run's source_registry.json has "
                    f"{sources_with_excerpt_count}/{len(sources)} sources with a captured excerpt -- "
                    "match_evidence_to_source_candidates structurally cannot propose any candidate "
                    "for ANY item in this run, regardless of this item's own wording."
                )
            else:
                blocker_detail = (
                    "NO_CANDIDATE_PROPOSED: none of this run's "
                    f"{sources_with_excerpt_count} excerpt-bearing sources' text overlaps this "
                    "item's own evidence/claim text."
                )
        else:
            blocker_detail = f"CANDIDATE_PROPOSED_BUT_REJECTED: {new_source_link_status}"
    else:
        blocker_detail = None

    return {
        "evidence_id": item.get("representative_claim_id"),
        "side": side,
        "evidence_fact_group_id": item.get("evidence_fact_group_id"),
        "member_claim_ids": item.get("member_claim_ids") or [],
        "member_claim_count": len(item.get("member_claim_ids") or []),
        "target_alpha_id": target_alpha,
        "original_linkage_status": original_linkage_status,
        "source_id_or_position": None,
        "post_fix_legacy_linkage_status": post_fix_legacy_linkage_status,
        "post_fix_legacy_matched_source": public_source_fields(matched_source) if matched_source else None,
        "post_fix_new_source_link_status": new_source_link_status,
        "post_fix_new_linked_source_id": new_result.get("linked_source_id"),
        "post_fix_new_content_support_status": new_content_support_status,
        "post_fix_new_blocker_detail": blocker_detail,
        "support_check": {
            "result": item.get("evidence_stance"),
            "method": f"B1 evidence-stance classification ({item.get('stance_method') or 'unrecorded'})",
            "target": target_alpha,
            "rationale": (
                f"already stance-filtered at evidence-qualification time (evidence_stance="
                f"{item.get('evidence_stance')!r}) -- this determines WHICH SIDE this item argues "
                f"for, independent of whether its source content is locatable"
            ),
        },
        "linkage_vs_support_note": (
            "SOURCE_LINKED (legacy TRACEABLE/PARTIAL, or new VALID) does not by itself mean "
            "verified truth, and UNAVAILABLE/NOT_PROVIDED linkage does not retract the stance-based "
            "support determination above -- these are two independent axes, never conflated."
        ),
        "continues_to_be_used_for_main_conflict": True,
        "downgrade_or_exclusion_reason": None,
        "evidence_text_excerpt": evidence_text[:280],
    }


def main() -> None:
    conflicts = json.loads((RUN_DIR / "conflicts.json").read_text(encoding="utf-8"))
    registry = json.loads((RUN_DIR / "source_registry.json").read_text(encoding="utf-8"))
    metadata = json.loads((RUN_DIR / "metadata.json").read_text(encoding="utf-8"))
    sources = registry.get("sources") or []
    evidence_cutoff = metadata.get("analysis_date")

    main_conflict = conflicts.get("main_conflict")
    assert main_conflict is not None, "AMD run has no main_conflict -- cannot build the ledger"
    conflict_id = main_conflict.get("conflict_id")
    ui = main_conflict.get("evidence_ui", {})

    items = []
    for side_key, side_name in (("bull_evidence", "bull"), ("bear_evidence", "bear"), ("counter_evidence", "counter")):
        for item in ui.get(side_key) or []:
            items.append(_item_ledger_entry(side_name, item, sources, evidence_cutoff))

    legacy_linkage_breakdown: dict[str, int] = {}
    new_linkage_breakdown: dict[str, int] = {}
    for entry in items:
        legacy_status = entry["post_fix_legacy_linkage_status"]
        legacy_linkage_breakdown[legacy_status] = legacy_linkage_breakdown.get(legacy_status, 0) + 1
        new_status = entry["post_fix_new_source_link_status"]
        new_linkage_breakdown[new_status] = new_linkage_breakdown.get(new_status, 0) + 1

    sources_with_excerpt = sum(1 for s in sources if s.get("excerpt"))

    out = {
        "schema_version": "amd_34_item_ledger.v2",
        "run_id": RUN_ID,
        "conflict_id": conflict_id,
        "evidence_cutoff": evidence_cutoff,
        "original_audit_citation": ORIGINAL_AUDIT_CITATION,
        "item_count_found": len(items),
        "item_count_matches_cited_34": len(items) == 34,
        "counts_by_side": {
            "bull": len(ui.get("bull_evidence") or []),
            "bear": len(ui.get("bear_evidence") or []),
            "counter": len(ui.get("counter_evidence") or []),
        },
        "original_linkage_status_breakdown": {"UNAVAILABLE": len(items)},
        "post_fix_legacy_linkage_status_breakdown": legacy_linkage_breakdown,
        "post_fix_new_source_link_status_breakdown": new_linkage_breakdown,
        "source_registry_summary": {
            "source_count": registry.get("source_count"),
            "traceable_count": sum(1 for s in sources if s.get("metadata_status") == "TRACEABLE"),
            "partial_count": sum(1 for s in sources if s.get("metadata_status") == "PARTIAL"),
            "sources_with_captured_excerpt": sources_with_excerpt,
        },
        "items": items,
        "honest_result_new_mechanism": (
            f"{new_linkage_breakdown.get('VALID', 0)}/{len(items)} items achieved a VALID link under "
            "the NEW T1 content/ID-based mechanism (match_evidence_to_source_candidates + "
            "validate_source_reference). AMD's own source_registry.json was captured BEFORE this "
            "round's fetch-stage excerpt capture (tradingagents/dataflows/yfinance_news.py's "
            f"_capture_news_source) -- {sources_with_excerpt}/{len(sources)} of its 46 sources carry an "
            "excerpt at all, so the new mechanism structurally cannot produce a candidate for any of "
            "these 34 items, regardless of wording. This is reported honestly, not padded: it is a "
            "real, expected consequence of reprocessing an old artifact with a new mechanism that "
            "needs freshly-captured content to have anything to match against -- never never a claim "
            "that the mechanism itself is non-functional (see the positive proof below)."
        ),
        "positive_end_to_end_proof": (
            "tests/test_t1_source_linking_pipeline.py::TestScenarioA_ValidLinkPropagatesEndToEnd -- "
            "the SAME match_evidence_to_source_candidates + validate_source_reference mechanism, run "
            "through the SAME real save_structured_agent_outputs production entrypoint, against a "
            "freshly-captured (excerpt-bearing) source, DOES produce SOURCE_LINK_VALID end to end "
            "(verified via a real captured news source, real deterministic claim extraction, and a "
            "real API round-trip) -- proving the new chain itself works on the input shape it needs; "
            "AMD's specific historical registry is simply too old to have that shape."
        ),
        "follow_up_fresh_run_testing_needed": (
            "AMD's real match rate under the new ID/content-based mechanism can only be honestly "
            "measured with a Fresh Run (new data fetch through the now-excerpt-capturing yfinance_news "
            "path, followed by fresh structured extraction) -- not by reprocessing this old, "
            "excerpt-less registry. This ledger does not claim that follow-up as done."
        ),
    }

    out_path = REPO_ROOT / "docs/audit_artifacts/round_source_linking_t0_t2/amd_34_item_ledger.json"
    out_path.write_text(json.dumps(out, indent=2, ensure_ascii=False, sort_keys=False), encoding="utf-8")
    print(f"item_count_found={len(items)} matches_cited_34={len(items) == 34}")
    print("post_fix_legacy_linkage_status_breakdown:", legacy_linkage_breakdown)
    print("post_fix_new_source_link_status_breakdown:", new_linkage_breakdown)
    print(f"wrote {out_path}")


if __name__ == "__main__":
    main()
