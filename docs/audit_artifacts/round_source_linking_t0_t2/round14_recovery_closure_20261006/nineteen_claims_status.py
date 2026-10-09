#!/usr/bin/env python3
"""Per-claim status for the fixed 19 analytical SUPPORTS claims (round 14,
section 8). Read-only; derives every field verbatim from a run directory's
own persisted artifacts and never recomputes a score, stance, or level.

Usage: nineteen_claims_status.py [--run-dir DIR] [--out FILE]
Default run dir is the ORIGINAL c904d4cc run (read-only). After a real,
separately-authorized recovery, point it at the recovered run's directory to
answer, claim by claim: valid match / valid NONE / failure; whether a match
reached the official (verified) evidence pool and with what activation
level; and the first gate that kept it from contributing.
"""
import argparse, json, sys
from pathlib import Path

REPO = Path(__file__).resolve().parents[4]
sys.path.insert(0, str(REPO))
from comqutor_alpha.structure_engine.alpha_mapper import _NEVER_SENT_FALLBACK_REASONS  # noqa: E402

NINETEEN = REPO / "docs/audit_artifacts/round_source_linking_t0_t2/round12_alpha_classifier_audit_fix_20261006/19_analytical_supports_claim_list.json"
DEFAULT_RUN = REPO / "outputs/runs/c904d4cc-dc09-495c-aec5-b056979948e1"


def classification_bucket(match):
    if match is None:
        return "missing_from_alpha_matches", None
    method, reason = match.get("alpha_match_method"), match.get("alpha_match_fallback_reason")
    if method == "llm" and reason is None:
        return ("valid_select" if match.get("matched_alpha") else "valid_none"), None
    return ("not_executed" if reason in _NEVER_SENT_FALLBACK_REASONS else "call_failure"), reason


def view_alphas(activation_payload, view):
    if view == "v2":
        return (activation_payload.get("activation") or {}).get("alphas") or []
    versions = activation_payload.get("activation_versions") or {}
    return (versions.get(view) or {}).get("alphas") or []


def contributions(activation_payload, claim_id, view):
    out = []
    for alpha in view_alphas(activation_payload, view):
        if claim_id in (alpha.get("claim_ids") or []):
            out.append({k: alpha.get(k) for k in ("alpha_id", "status", "activation_level", "qualified_level",
                                                   "activation_score", "is_blocked", "blocked_reason_codes")})
    return out


def first_blocking_gate(bucket, reason, record, in_raw, in_verified):
    if bucket in ("call_failure", "not_executed", "missing_from_alpha_matches"):
        return f"alpha_classification_unavailable:{reason or bucket}"
    if bucket == "valid_none":
        return "classified_none: the model decided no Alpha applies (a completed classification)"
    if not record.get("analysis_eligible", False):
        return f"claim_not_analysis_eligible:{record.get('claim_quality')}"
    if in_verified:
        return None  # contributes to the official (verified) pool
    if in_raw:
        return f"in_raw_pool_but_not_official: content_support_status={record.get('content_support_status')}"
    return "matched_but_absent_from_every_activation_view (see evidence_integrity_warnings / blocked_reason_codes in the run's alpha_activations.json)"


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--run-dir", default=str(DEFAULT_RUN))
    ap.add_argument("--out", default=None)
    args = ap.parse_args()
    run = Path(args.run_dir)
    ids = [c["claim_id"] for c in json.loads(NINETEEN.read_text())["claims"]]
    structured = {r["claim_id"]: r for r in json.loads((run / "structured_agent_outputs.json").read_text())["records"]}
    matches = {m["claim_id"]: m for m in json.loads((run / "alpha_matches.json").read_text())["matches"]}
    activation = json.loads((run / "alpha_activations.json").read_text()) if (run / "alpha_activations.json").exists() else {}
    rows = []
    for cid in ids:
        # claim ids of a RECOVERY run keep the original run's id prefix by design (frozen identity)
        rec = structured.get(cid, {})
        bucket, reason = classification_bucket(matches.get(cid))
        raw, verified = contributions(activation, cid, "v2"), contributions(activation, cid, "v2_verified")
        rows.append({
            "claim_id": cid,
            "claim_quality": rec.get("claim_quality"), "analysis_eligible": rec.get("analysis_eligible"),
            "source_link_status": rec.get("source_link_status"), "linked_source_id": rec.get("linked_source_id"),
            "content_support_status": rec.get("content_support_status"), "content_support_method": rec.get("content_support_method"),
            "classification": bucket, "classification_fallback_reason": reason,
            "matched_alpha": (matches.get(cid) or {}).get("matched_alpha"),
            "matched_evidence_stance": (matches.get(cid) or {}).get("matched_evidence_stance"),
            "in_raw_pool_alphas": raw, "in_official_verified_pool_alphas": verified,
            "first_blocking_gate": first_blocking_gate(bucket, reason, rec, bool(raw), bool(verified)),
        })
    from collections import Counter
    summary = {"run_dir": str(run), "claims": len(rows),
               "classification_counts": dict(Counter(r["classification"] for r in rows)),
               "reached_official_pool": sum(1 for r in rows if r["in_official_verified_pool_alphas"]),
               "content_support_counts": dict(Counter(r["content_support_status"] for r in rows))}
    doc = {"summary": summary, "claims": rows}
    if args.out:
        Path(args.out).write_text(json.dumps(doc, indent=2))
    print(json.dumps(summary, indent=2))
    for r in rows:
        print(f"{r['claim_id'].split(':',1)[1][:46]:46} {r['classification']:14} {str(r['classification_fallback_reason'] or ''):15} "
              f"{str(r['content_support_status']):12} -> {r['first_blocking_gate']}")


if __name__ == "__main__":
    main()
