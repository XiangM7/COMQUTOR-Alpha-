#!/usr/bin/env python3
"""Read-only aggregation script for the c904d4cc AMD Fresh Run minimal audit.
Zero Provider calls, zero writes to the run's own directory -- reads only,
writes exclusively into this round's own audit deliverable directory."""
import json
from pathlib import Path
from collections import defaultdict, Counter

RUN = Path("outputs/runs/c904d4cc-dc09-495c-aec5-b056979948e1")
OUT = Path("docs/audit_artifacts/round_source_linking_t0_t2/round11_amd_fresh_run_20261006/c904d4cc_minimal_audit")

def load(name):
    return json.loads((RUN / name).read_text())

def load_jsonl(path):
    out = []
    if path.exists():
        with open(path) as f:
            for line in f:
                line = line.strip()
                if line:
                    out.append(json.loads(line))
    return out

structured = load("structured_agent_outputs.json")
alpha_matches = load("alpha_matches.json")
source_registry = load("source_registry.json")
evidence_stance = load("evidence_stance_audit.json")
week2_errors = load_jsonl(RUN / "error_logs" / "week2_llm_errors.jsonl")
semantic_calls = load_jsonl(RUN / "llm_semantic_calls.jsonl")
req_audit = load_jsonl(RUN / "error_logs" / "week2_llm_provider_request_audit.jsonl")
resp_audit = load_jsonl(RUN / "error_logs" / "week2_llm_provider_response_audit.jsonl")

records_by_id = {r["claim_id"]: r for r in structured["records"]}
matches_by_id = {m["claim_id"]: m for m in alpha_matches["matches"]}
sources_by_id = {s["source_id"]: s for s in source_registry.get("sources", [])}

# semantic calls / audit indexed by claim where identifiable
semantic_by_task = defaultdict(list)
for c in semantic_calls:
    semantic_by_task[c.get("task")].append(c)

req_audit_claim_ids = defaultdict(list)
for r in req_audit:
    for cid in (r.get("claim_ids") or []):
        req_audit_claim_ids[cid].append(r)

resp_audit_by_attempt = {r["attempt_id"]: r for r in resp_audit}

# -------- build claim_trace_index.json --------
claim_index = []
for claim_id, rec in records_by_id.items():
    match = matches_by_id.get(claim_id)
    content_support_llm_detail = rec.get("content_support_llm_detail")

    req_entries = req_audit_claim_ids.get(claim_id, [])
    req_detail = []
    for r in req_entries:
        resp = resp_audit_by_attempt.get(r["attempt_id"])
        req_detail.append({
            "attempt_id": r["attempt_id"],
            "task": r.get("task"),
            "requested_at": r.get("created_at"),
            "response_received": resp is not None,
            "response_at": resp.get("created_at") if resp else None,
        })

    entry = {
        "claim_id": claim_id,
        "agent": rec.get("agent"),
        "claim": rec.get("claim"),
        "evidence": rec.get("evidence"),
        "source_section": rec.get("source_section"),
        "claim_index_in_agent": rec.get("claim_index"),
        "claim_quality": rec.get("claim_quality"),
        "claim_quality_reason_codes": rec.get("claim_quality_reason_codes"),
        "analysis_eligible": rec.get("analysis_eligible"),
        "assertion_status": rec.get("assertion_status"),
        "duplicate_group_id": rec.get("duplicate_group_id"),
        "duplicate_count": rec.get("duplicate_count"),
        "source_link_status": rec.get("source_link_status"),
        "linked_source_id": rec.get("linked_source_id"),
        "source_link_method": rec.get("source_link_method"),
        "submitted_to_content_support": rec.get("source_link_status") == "VALID",
        "content_support_status": rec.get("content_support_status"),
        "content_support_method": rec.get("content_support_method"),
        "content_support_llm_detail": content_support_llm_detail,
        "content_support_real_requests": req_detail if req_detail else "NONE_RECORDED",
        "alpha_classification": {
            "attempted_real_llm_call_recorded": any(
                e["task"] == "alpha_classifier" for e in req_detail
            ),
            "alpha_match_method": match.get("alpha_match_method") if match else None,
            "alpha_match_fallback_reason": match.get("alpha_match_fallback_reason") if match else None,
            "matched_alpha": match.get("matched_alpha") if match else None,
            "reason": match.get("reason") if match else None,
            "matched_evidence_stance": match.get("matched_evidence_stance") if match else None,
            "matched_stance_reason_codes": match.get("matched_stance_reason_codes") if match else None,
            "matched_stance_requires_manual_review": match.get("matched_stance_requires_manual_review") if match else None,
        } if match else "NOT_IN_ALPHA_MATCHES_FILE",
    }
    claim_index.append(entry)

claim_index.sort(key=lambda e: e["claim_id"])

OUT.mkdir(parents=True, exist_ok=True)
(OUT / "claim_trace_index.json").write_text(json.dumps({
    "schema_version": "c904d4cc_audit.claim_trace_index.v1",
    "run_id": "c904d4cc-dc09-495c-aec5-b056979948e1",
    "total_claims": len(claim_index),
    "note": "Read-only aggregation of this run's own real, already-persisted artifacts. "
            "Fields with no real saved record are null/NOT_IN_ALPHA_MATCHES_FILE/NONE_RECORDED, "
            "never inferred.",
    "claims": claim_index,
}, indent=2, default=str))

# -------- summary counters for the report --------
summary = {
    "total_claims": len(records_by_id),
    "source_link_status": dict(Counter(r.get("source_link_status") for r in records_by_id.values())),
    "content_support_status": dict(Counter(r.get("content_support_status") for r in records_by_id.values())),
    "content_support_method": dict(Counter(r.get("content_support_method") for r in records_by_id.values())),
    "claim_quality": dict(Counter(r.get("claim_quality") for r in records_by_id.values())),
    "alpha_match_method": dict(Counter(m.get("alpha_match_method") for m in alpha_matches["matches"])),
    "alpha_match_fallback_reason": dict(Counter(m.get("alpha_match_fallback_reason") for m in alpha_matches["matches"] if m.get("alpha_match_fallback_reason"))),
    "matched_alpha_nonnull_count": sum(1 for m in alpha_matches["matches"] if m.get("matched_alpha")),
    "content_support_real_llm_verified_count": sum(1 for r in records_by_id.values() if r.get("content_support_method") == "LLM_CONTENT_SUPPORT_VERIFIED"),
    "content_support_supports_count": sum(1 for r in records_by_id.values() if r.get("content_support_status") == "SUPPORTS"),
    "content_support_conditional_count": sum(1 for r in records_by_id.values() if r.get("content_support_status") == "CONDITIONAL"),
    "valid_source_link_and_content_support_resolved_but_zero_alpha_match": sum(
        1 for r in records_by_id.values()
        if r.get("source_link_status") == "VALID"
        and r.get("content_support_status") in ("SUPPORTS", "CONDITIONAL")
        and not (matches_by_id.get(r["claim_id"]) or {}).get("matched_alpha")
    ),
}
(OUT / "00_summary_counts.json").write_text(json.dumps(summary, indent=2, default=str))
print(json.dumps(summary, indent=2, default=str))
