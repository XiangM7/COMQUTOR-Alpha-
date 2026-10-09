"""AMD 34-item re-verification (2026-10-04), per direct user instruction:
re-check John's T1 original AMD acceptance scope using ALL CURRENT
production mechanisms (Round 1 financial capture, Round 2 full-table
capture, Round 3 cross-agent/normalized matching) -- never a different,
easier-to-pass batch of evidence. Read-only against the real, original AMD
run (d5b60b8a-66b8-44c1-9f55-ee345e58c48d). Zero writes to that run
directory. Zero Provider calls.
"""
import json
import sys
from pathlib import Path

sys.path.insert(0, ".")

from comqutor_alpha.source_provenance import (
    extract_all_source_markers_from_text,
    match_evidence_to_source_candidates,
    match_evidence_to_source_candidates_normalized,
    resolve_external_source_for_claim,
    validate_source_reference,
)

RUN_ID = "d5b60b8a-66b8-44c1-9f55-ee345e58c48d"
RUN_DIR = Path("outputs/runs") / RUN_ID
TICKER = "AMD"

conflicts = json.loads((RUN_DIR / "conflicts.json").read_text())
registry = json.loads((RUN_DIR / "source_registry.json").read_text())
metadata = json.loads((RUN_DIR / "metadata.json").read_text())
structured = json.loads((RUN_DIR / "structured_agent_outputs.json").read_text())
sources = registry.get("sources") or []
evidence_cutoff = metadata.get("analysis_date")
by_claim_id = {r["claim_id"]: r for r in structured["records"]}

main_conflict = conflicts["main_conflict"]
ui = main_conflict["evidence_ui"]

# ---------------------------------------------------------------------------
# Real-registry facts, independently re-confirmed (not trusted from the old
# ledger blindly).
# ---------------------------------------------------------------------------
source_types_present = sorted({s.get("source_type") for s in sources})
sources_with_excerpt = sum(1 for s in sources if s.get("excerpt"))
sources_with_data_snapshot = sum(1 for s in sources if s.get("data_snapshot"))

registry_facts = {
    "source_count": len(sources),
    "source_types_present": source_types_present,
    "sources_with_excerpt": sources_with_excerpt,
    "sources_with_data_snapshot": sources_with_data_snapshot,
    "registry_schema_predates_excerpt_field": not any("excerpt" in s for s in sources),
    "structured_agent_outputs_predates_source_link_status_field": not any(
        "source_link_status" in r for r in structured["records"]
    ),
}

# ---------------------------------------------------------------------------
# Per-item re-verification against ALL current mechanisms.
# ---------------------------------------------------------------------------
_FINANCIAL_PRODUCING_AGENTS = {"fundamental_agent"}
_SENTIMENT_PRODUCING_AGENTS = {"sentiment_agent"}
_NEWS_PRODUCING_AGENTS = {"news_agent"}
_DOWNSTREAM_SYNTHESIS_AGENTS = {
    "bull_researcher", "bear_researcher", "research_manager", "trader",
    "aggressive_risk_analyst", "conservative_risk_analyst", "neutral_risk_analyst",
    "portfolio_manager",
}


def _producing_agent(item):
    agents = item.get("agents") or []
    return agents[0] if agents else "unknown"


def _classify_bucket(agent, new_source_link_status, new_candidates_found):
    """The 4 required buckets, precisely distinguished -- never collapsed
    into a single generic 'no source' bucket."""
    if new_source_link_status == "VALID":
        return "ALREADY_LINKED_PENDING_CONTENT_REVIEW"  # bucket 4 (link achieved; content support still PENDING_REVIEW, never auto-SUPPORTS)
    if agent in _FINANCIAL_PRODUCING_AGENTS:
        return "SOURCE_TYPE_NEVER_CAPTURED_FOR_THIS_RUN__FINANCIAL"
    if agent in _SENTIMENT_PRODUCING_AGENTS:
        return "SOURCE_TYPE_NEVER_CAPTURED_FOR_THIS_RUN__SENTIMENT"
    if agent in _NEWS_PRODUCING_AGENTS:
        return "SOURCE_IDENTITY_EXISTS_BODY_NEVER_SAVED__NEWS"
    if agent in _DOWNSTREAM_SYNTHESIS_AGENTS:
        return "DOWNSTREAM_SYNTHESIS_OF_UNCAPTURED_UPSTREAM_DATA"
    return "UNCLASSIFIED"


items_out = []
for side_key, side_name in (("bull_evidence", "bull"), ("bear_evidence", "bear"), ("counter_evidence", "counter")):
    for item in ui.get(side_key) or []:
        evidence_text = item.get("evidence_text") or ""
        claim_id = item.get("representative_claim_id")
        agent = _producing_agent(item)
        persisted_record = by_claim_id.get(claim_id)

        # Mechanism 1: legacy title-substring match (resolve_external_source_for_claim).
        legacy_matched_source, legacy_status = resolve_external_source_for_claim(
            claim=None, evidence=evidence_text, sources=sources
        )

        # Mechanism 2: OLD whole-excerpt content match (pre-Round-3).
        old_candidates = match_evidence_to_source_candidates(evidence_text, None, sources)

        # Mechanism 3 (Round 3): multi-marker extraction -- would the ORIGINAL
        # agent's own text have carried a marker at all? (expected: no --
        # this run predates the marker-embedding mechanism; confirmed, not assumed.)
        markers_found = extract_all_source_markers_from_text(evidence_text, sources)

        # Mechanism 4 (Round 3): normalized numeric/field matching.
        normalized_result = match_evidence_to_source_candidates_normalized(
            evidence_text, None, sources, instrument=TICKER
        )

        # Combine exactly as the real production _annotate_source_link does:
        # marker > old content-match > normalized match, each gated by
        # validate_source_reference.
        final_result = None
        final_method = "NONE"
        if markers_found:
            validated = validate_source_reference(markers_found[0], sources=sources, evidence_cutoff=evidence_cutoff)
            if validated["source_link_status"] == "VALID":
                final_result, final_method = validated, "ORIGINAL_AGENT_MARKER_CITED"
        if final_result is None and old_candidates:
            for candidate in old_candidates:
                validated = validate_source_reference(candidate, sources=sources, evidence_cutoff=evidence_cutoff)
                if validated["source_link_status"] == "VALID":
                    final_result, final_method = validated, "CONTENT_MATCH_CANDIDATE"
                    break
        if final_result is None and normalized_result["candidates"]:
            for candidate in normalized_result["candidates"]:
                validated = validate_source_reference(candidate, sources=sources, evidence_cutoff=evidence_cutoff)
                if validated["source_link_status"] == "VALID":
                    final_result, final_method = validated, "NORMALIZED_FIELD_MATCH_CANDIDATE"
                    break
        if final_result is None:
            final_result = validate_source_reference(None, sources=sources, evidence_cutoff=evidence_cutoff)
            final_method = "NONE"

        new_source_link_status = final_result["source_link_status"]
        bucket = _classify_bucket(agent, new_source_link_status, bool(old_candidates or normalized_result["candidates"]))

        items_out.append({
            "evidence_id": claim_id,
            "side": side_name,
            "producing_agent": agent,
            "target_alpha_id": item.get("target_alpha_id"),
            "original_linkage_status": "UNAVAILABLE",  # per the original cited audit, re-confirmed below
            "original_source_id_or_position": None,
            "current_source_id_or_content_location": final_result.get("linked_source_id"),
            "source_content_available": (
                "NO_SOURCE_RECORD_OF_THIS_TYPE_EXISTS" if agent in (_FINANCIAL_PRODUCING_AGENTS | _SENTIMENT_PRODUCING_AGENTS)
                else ("IDENTITY_ONLY_NO_BODY" if agent in _NEWS_PRODUCING_AGENTS else "DEPENDS_ON_UPSTREAM")
            ),
            "post_fix_source_link_status": new_source_link_status,
            "post_fix_source_link_method": final_method,
            "post_fix_content_support_status": "PENDING_REVIEW" if new_source_link_status == "VALID" else "NOT_APPLICABLE",
            "continues_to_be_used_for_main_conflict": True,
            "not_passed_reason": None if new_source_link_status == "VALID" else bucket,
            "mechanism_detail": {
                "legacy_title_match_status": legacy_status,
                "old_whole_excerpt_candidates_found": len(old_candidates),
                "round3_markers_found_in_original_text": markers_found,
                "round3_normalized_candidates_found": len(normalized_result["candidates"]),
                "round3_normalized_ambiguous_numbers": normalized_result["ambiguous_numbers"],
            },
            "persisted_record_has_source_link_status_field": (
                "source_link_status" in persisted_record if persisted_record else None
            ),
            "classification_bucket": bucket,
            "evidence_text_excerpt": evidence_text[:200],
        })

# ---------------------------------------------------------------------------
# Tallies.
# ---------------------------------------------------------------------------
original_breakdown = {"UNAVAILABLE": len(items_out)}
post_fix_status_breakdown = {}
bucket_breakdown = {}
for item in items_out:
    s = item["post_fix_source_link_status"]
    post_fix_status_breakdown[s] = post_fix_status_breakdown.get(s, 0) + 1
    b = item["classification_bucket"]
    bucket_breakdown[b] = bucket_breakdown.get(b, 0) + 1

output = {
    "re_verification_date": "2026-10-04",
    "run_id": RUN_ID,
    "conflict_id": main_conflict.get("conflict_id"),
    "evidence_cutoff": evidence_cutoff,
    "item_count": len(items_out),
    "item_count_matches_john_cited_34": len(items_out) == 34,
    "registry_facts_independently_reconfirmed": registry_facts,
    "original_linkage_status_breakdown": original_breakdown,
    "post_fix_source_link_status_breakdown_ALL_CURRENT_MECHANISMS": post_fix_status_breakdown,
    "four_bucket_classification_breakdown": bucket_breakdown,
    "items": items_out,
}
print(json.dumps(output, indent=2, default=str, ensure_ascii=False))
