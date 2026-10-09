"""Round 8 (2026-10-06): independent re-evaluation of the already-completed
AMD Fresh Run (run_id 1bad76a7-72ac-4c8b-8189-2e5c0f1a6105) under the new
automated-eligibility mechanism (comqutor_alpha.source_provenance.
verify_data_fact_or_derived_calculation / apply_automated_content_support_
verification) and the corrected evidence_cutoff_at (resolve_evidence_cutoff_at).

Per the controlling task's explicit constraints:
- Creates a NEW, independent execution_id. NEVER overwrites, re-fetches, or
  reclassifies anything from the original run -- alpha_matches.json and
  extracted_structures.json (the frozen Alpha-classification result) are
  copied through byte-for-byte (only run_id/claim run_id rebased, the SAME
  rebase routes_research.trigger_content_support_reevaluation already uses).
- structured_agent_outputs.json's records are re-annotated, never
  re-extracted: for a record whose source_link_status was TIME_INVALID, its
  ALREADY-FOUND linked_source_id candidate is re-validated against the
  corrected evidence_cutoff_at (never a new candidate search); for any
  record that is (or becomes) source_link_status VALID, content_support_*
  is re-derived via the new automated verifier. No other field on any
  record is touched.
- Zero Provider calls, zero network calls -- every input is already-saved
  JSON on disk.
- DB writes (Week3/Week4 persistence, via the real, unmodified
  _run_week3_graph_pipeline) go ONLY to the isolated COMQUTOR_TEST_DATABASE_URL
  instance -- this script refuses to run unless COMQUTOR_DATABASE_URL has
  already been forced to a database whose name ends in "_test" (see the
  accompanying 00_run_isolated_db.sh wrapper, modeled on
  run_nvda_fresh_run_isolated_db.sh's own proven guard).
"""

from __future__ import annotations

import copy
import json
import os
import sys
from datetime import UTC, datetime
from pathlib import Path
from uuid import uuid4

REPO_ROOT = Path(__file__).resolve().parents[4]
sys.path.insert(0, str(REPO_ROOT))

# --- Hard DB-safety gate (defense in depth alongside the bash wrapper) ----
db_url = os.environ.get("COMQUTOR_DATABASE_URL", "")
db_name = db_url.rsplit("/", 1)[-1].split("?", 1)[0]
if not db_name.endswith("_test"):
    raise SystemExit(
        f"REFUSING TO RUN: COMQUTOR_DATABASE_URL resolves to database {db_name!r}, "
        "which does not end in '_test'. This script writes real DB rows via the "
        "production Week3/Week4 pipeline and must only ever target the isolated "
        "test database. Run via 00_run_isolated_db.sh, never directly."
    )

from comqutor_alpha.api.routes_research import (  # noqa: E402
    _rebase_run_id_for_reevaluation_execution,
    _run_week3_graph_pipeline,
)
from comqutor_alpha.source_provenance import (  # noqa: E402
    REVIEW_METHOD_AGENT_CITED_UNVERIFIED_SUPPORT,
    REVIEW_METHOD_ORIGINAL_AGENT_CITED_UNVERIFIED_SUPPORT,
    REVIEW_METHOD_UNVERIFIED_OFFLINE_CONTENT_MATCH,
    SOURCE_LINK_VALID,
    SUPPORT_PENDING_REVIEW,
    apply_automated_content_support_verification,
    build_content_support_review,
    resolve_evidence_cutoff_at,
    validate_source_reference,
)
from comqutor_alpha.structure_engine.structured_output_adapter import (  # noqa: E402
    SOURCE_LINK_METHOD_AGENT_CITED,
    SOURCE_LINK_METHOD_ORIGINAL_AGENT_MARKER,
)
from comqutor_alpha.storage.file_store import load_json_record, run_dir_for, save_json_record

ORIGINAL_RUN_ID = "1bad76a7-72ac-4c8b-8189-2e5c0f1a6105"
OUTPUT_ROOT = "outputs/runs"


def _re_annotate_records(records: list[dict], sources: list[dict], evidence_cutoff: str | None) -> dict:
    """Returns (new_records, change_log) -- never mutates ``records``."""
    change_log: list[dict] = []
    new_records = []
    for record in records:
        record = dict(record)
        original_status = record.get("source_link_status")

        if original_status == "TIME_INVALID":
            revalidated = validate_source_reference(
                record.get("linked_source_id"), sources=sources, evidence_cutoff=evidence_cutoff
            )
            if revalidated["source_link_status"] != original_status:
                record["source_link_status"] = revalidated["source_link_status"]
                record["linked_source_id"] = revalidated["linked_source_id"]
                change_log.append(
                    {
                        "claim_id": record.get("claim_id"),
                        "change": "source_link_status",
                        "before": original_status,
                        "after": revalidated["source_link_status"],
                    }
                )
                if revalidated["source_link_status"] == SOURCE_LINK_VALID:
                    method = record.get("source_link_method")
                    if method == SOURCE_LINK_METHOD_AGENT_CITED:
                        review_method = REVIEW_METHOD_AGENT_CITED_UNVERIFIED_SUPPORT
                    elif method == SOURCE_LINK_METHOD_ORIGINAL_AGENT_MARKER:
                        review_method = REVIEW_METHOD_ORIGINAL_AGENT_CITED_UNVERIFIED_SUPPORT
                    else:
                        review_method = REVIEW_METHOD_UNVERIFIED_OFFLINE_CONTENT_MATCH
                    record["content_support_status"] = SUPPORT_PENDING_REVIEW
                    record["content_support_method"] = review_method
                    record["content_support_review"] = build_content_support_review(
                        SUPPORT_PENDING_REVIEW,
                        method=review_method,
                        claim_id=record.get("claim_id"),
                        linked_source_id=revalidated.get("linked_source_id"),
                    )

        if record.get("source_link_status") == SOURCE_LINK_VALID:
            automated = apply_automated_content_support_verification(record, sources=sources)
            if automated is not None:
                change_log.append(
                    {
                        "claim_id": record.get("claim_id"),
                        "change": "content_support_status",
                        "before": record.get("content_support_status"),
                        "after": automated["content_support_status"],
                        "method": automated["content_support_method"],
                    }
                )
                record = automated

        new_records.append(record)
    return {"records": new_records, "change_log": change_log}


def main() -> None:
    metadata = load_json_record(ORIGINAL_RUN_ID, "metadata.json", output_root=OUTPUT_ROOT)
    structured_payload = load_json_record(ORIGINAL_RUN_ID, "structured_agent_outputs.json", output_root=OUTPUT_ROOT)
    alpha_matches_payload = load_json_record(ORIGINAL_RUN_ID, "alpha_matches.json", output_root=OUTPUT_ROOT)
    extracted_structures_payload = load_json_record(
        ORIGINAL_RUN_ID, "extracted_structures.json", output_root=OUTPUT_ROOT
    )
    registry = load_json_record(ORIGINAL_RUN_ID, "source_registry.json", output_root=OUTPUT_ROOT)
    sources = registry["sources"]

    analysis_date = metadata.get("analysis_date")
    evidence_cutoff, evidence_cutoff_basis = resolve_evidence_cutoff_at(analysis_date, sources)

    annotation_result = _re_annotate_records(structured_payload["records"], sources, evidence_cutoff)
    reannotated_structured_payload = dict(structured_payload)
    reannotated_structured_payload["records"] = annotation_result["records"]

    execution_id = f"automated-eligibility-reeval-{datetime.now(UTC).strftime('%Y%m%dT%H%M%SZ')}-{uuid4().hex[:8]}"
    rebased_structured, rebased_alpha_matches, rebased_extracted_structures = (
        _rebase_run_id_for_reevaluation_execution(
            structured_payload=reannotated_structured_payload,
            alpha_matches_payload=alpha_matches_payload,
            extracted_structures_payload=extracted_structures_payload,
            execution_id=execution_id,
        )
    )
    rebased_registry = copy.deepcopy(registry)
    rebased_registry["run_id"] = execution_id

    execution_metadata = {
        **metadata,
        "run_id": execution_id,
        "based_on_run_id": ORIGINAL_RUN_ID,
        "execution_type": "automated_eligibility_reevaluation",
        "evidence_cutoff_at": evidence_cutoff,
        "evidence_cutoff_basis": evidence_cutoff_basis,
        "analysis_date": analysis_date,
        "reannotation_change_count": len(annotation_result["change_log"]),
        "triggered_at": datetime.now(UTC).isoformat(),
    }

    save_json_record(execution_id, "metadata.json", execution_metadata, output_root=OUTPUT_ROOT)
    save_json_record(execution_id, "alpha_matches.json", rebased_alpha_matches, output_root=OUTPUT_ROOT)
    save_json_record(execution_id, "extracted_structures.json", rebased_extracted_structures, output_root=OUTPUT_ROOT)
    save_json_record(execution_id, "structured_agent_outputs.json", rebased_structured, output_root=OUTPUT_ROOT)
    save_json_record(execution_id, "source_registry.json", rebased_registry, output_root=OUTPUT_ROOT)

    change_log_path = Path(
        "docs/audit_artifacts/round_source_linking_t0_t2/round8_automated_eligibility_20261006"
        "/02_reannotation_change_log.json"
    )
    change_log_path.write_text(
        json.dumps(
            {
                "based_on_run_id": ORIGINAL_RUN_ID,
                "execution_id": execution_id,
                "evidence_cutoff_at": evidence_cutoff,
                "evidence_cutoff_basis": evidence_cutoff_basis,
                "change_count": len(annotation_result["change_log"]),
                "changes": annotation_result["change_log"],
            },
            indent=2,
            default=str,
        )
    )

    execution_run_dir = run_dir_for(execution_id, OUTPUT_ROOT)
    _run_week3_graph_pipeline(execution_run_dir, require_verified_evidence_gate=True)

    print(f"ORIGINAL_RUN_ID={ORIGINAL_RUN_ID}")
    print(f"NEW_EXECUTION_ID={execution_id}")
    print(f"EVIDENCE_CUTOFF_AT={evidence_cutoff} ({evidence_cutoff_basis})")
    print(f"REANNOTATION_CHANGE_COUNT={len(annotation_result['change_log'])}")


if __name__ == "__main__":
    main()
