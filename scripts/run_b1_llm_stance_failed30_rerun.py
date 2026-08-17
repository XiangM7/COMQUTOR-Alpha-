#!/usr/bin/env python3
"""B1 LLM Evidence Stance Upgrade -- bounded rerun of the 30 rows that
previously fell back with ``malformed_response`` in the original 50-row
validation, now that the shared Week2LLMGateway JSON parser strips a
whole-response markdown fence before parsing (see
``docs/audit_artifacts/b1_shared_json_parser_fix_report.md``).

Reruns ONLY those exact 30 rows -- identified from the original
``docs/audit_artifacts/b1_llm_stance_50_validation.csv`` (never resampled,
never selected by current semantics) -- through the SAME production B1
prompt/parser/validator/batching (``evidence_stance_llm.apply_llm_stance_upgrade``,
unmodified). Never touches the 20 rows that already had a valid LLM result
in the original run, and never modifies the original validation artifact.

Never invoked automatically; never calls a Provider unless every one of
these is true:

- ``--execute-rerun`` is passed,
- the environment variable ``COMQUTOR_B1_LLM_STANCE_FAILED30_RERUN_APPROVED``
  is exactly the string ``"true"``,
- the original 50-row validation CSV is present and contains exactly the
  expected 30 malformed_response rows.

The gateway is constructed with ``max_retries=0`` and ``max_calls=3`` -- a
hard, enforced budget (3 batches of 10 == 3 logical calls == at most 3 real
attempts), not just a soft script-level check.
"""

from __future__ import annotations

import argparse
import csv
import json
import os
import sys
from pathlib import Path
from typing import Any

REPO_ROOT = Path(__file__).resolve().parents[1]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from comqutor_alpha.alpha_library.alpha_loader import load_alpha_taxonomy  # noqa: E402
from comqutor_alpha.research_profiles import (  # noqa: E402
    ANTHROPIC_PROFILE_ID,
    ResearchProfileError,
    get_research_profile,
)
from comqutor_alpha.structure_engine import (  # noqa: E402
    evidence_stance as es,
    evidence_stance_llm as esl,
)
from comqutor_alpha.structure_engine.week2_llm import Week2LLMGateway  # noqa: E402

APPROVAL_ENV_VAR = "COMQUTOR_B1_LLM_STANCE_FAILED30_RERUN_APPROVED"
MAX_LOGICAL_CALLS = 3
MAX_REAL_PROVIDER_ATTEMPTS = 3
VALIDATION_TIMEOUT_SECONDS = 60.0
EXPECTED_FAILED_ROW_COUNT = 30

SAMPLE_PATH = REPO_ROOT / "docs" / "evidence_review_sample_records.json"
ORIGINAL_VALIDATION_CSV = REPO_ROOT / "docs" / "audit_artifacts" / "b1_llm_stance_50_validation.csv"
RERUN_CSV_PATH = REPO_ROOT / "docs" / "audit_artifacts" / "b1_llm_stance_failed30_rerun.csv"
RERUN_JSON_PATH = REPO_ROOT / "docs" / "audit_artifacts" / "b1_llm_stance_failed30_rerun_result.json"
COMBINED_CSV_PATH = REPO_ROOT / "docs" / "audit_artifacts" / "b1_llm_stance_50_validation_after_parser_fix.csv"

BLOCKED_NOT_AUTHORIZED = "BLOCKED_RERUN_NOT_AUTHORIZED"
BLOCKED_ORIGINAL_VALIDATION_UNAVAILABLE = "BLOCKED_ORIGINAL_VALIDATION_UNAVAILABLE"
BLOCKED_FAILED_ROW_COUNT_UNEXPECTED = "BLOCKED_FAILED_ROW_COUNT_UNEXPECTED"
BLOCKED_SAMPLE_UNAVAILABLE = "BLOCKED_SAMPLE_UNAVAILABLE"
BLOCKED_CALL_BUDGET_WOULD_BE_EXCEEDED = "BLOCKED_CALL_BUDGET_WOULD_BE_EXCEEDED"
BLOCKED_PROVIDER_CREDENTIALS_MISSING = "BLOCKED_PROVIDER_CREDENTIALS_MISSING"
BLOCKED_PROVIDER_CLIENT_INITIALIZATION_FAILED = "BLOCKED_PROVIDER_CLIENT_INITIALIZATION_FAILED"

CSV_FIELDS = [
    "sample_id",
    "claim_id",
    "ticker",
    "target_alpha_id",
    "claim",
    "deterministic_v1_stance",
    "llm_v1_stance",
    "final_stance",
    "counter_alpha_id",
    "stance_method",
    "fallback_reason",
    "reviewer_expected_stance",
    "agreement_with_existing_review",
    "provenance",
]


def _write_blocked(reason: str, detail: dict[str, Any] | None = None) -> dict[str, Any]:
    payload = {"status": "BLOCKED", "reason": reason, "detail": detail or {}}
    RERUN_JSON_PATH.parent.mkdir(parents=True, exist_ok=True)
    RERUN_JSON_PATH.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
    print(json.dumps(payload, ensure_ascii=False, indent=2))
    return payload


def _identify_failed_30() -> tuple[list[dict[str, str]], list[dict[str, str]]]:
    """Reads the ORIGINAL validation CSV (never resampled, never modified)
    and returns (failed_rows, valid_rows) exactly as that run produced them."""
    with ORIGINAL_VALIDATION_CSV.open(encoding="utf-8", newline="") as f:
        rows = list(csv.DictReader(f))
    failed = [r for r in rows if r["stance_method"] == "deterministic_fallback" and r["fallback_reason"] == "malformed_response"]
    valid = [r for r in rows if r["stance_method"] == "llm"]
    return failed, valid


def _build_synthetic_matches(sample_rows: list[dict[str, Any]]) -> list[dict[str, Any]]:
    matches = []
    for row in sample_rows:
        alpha_id = row["target_alpha_id"]
        candidate = {
            "alpha_id": alpha_id,
            "alpha_name": row.get("target_alpha_name"),
            "evidence_stance": row.get("evidence_stance"),
            "counter_alpha_id": row.get("counter_alpha_id"),
            "stance_reason_codes": list(row.get("stance_reason_codes") or []),
            "stance_confidence_band": row.get("stance_confidence_band"),
            "requires_manual_review": bool(row.get("requires_manual_review")),
            "evidence_stance_version": es.CLASSIFIER_VERSION,
            "stance_method": None,
            "stance_fallback_reason": None,
        }
        matches.append(
            {
                "run_id": row.get("run_id"),
                "ticker": row.get("ticker"),
                "claim_id": row.get("claim_id"),
                "source_agent_output_id": row.get("source_agent_output_id"),
                "claim": row.get("claim"),
                "evidence": row.get("evidence"),
                "factors": [],
                "matched_alpha": alpha_id,
                "matched_alpha_name": row.get("target_alpha_name"),
                "secondary_alphas": [],
                "match_status": "matched",
                "candidate_scores": [candidate],
                "_sample_id": row.get("sample_id"),
                "_review_status": row.get("review_status"),
                "_reviewer_expected_stance": row.get("reviewer_expected_stance") or None,
                "_deterministic_v1_stance": row.get("evidence_stance"),
            }
        )
    return matches


def _rerun_row(match: dict[str, Any]) -> dict[str, Any]:
    candidate = match["candidate_scores"][0]
    stance_method = candidate.get("stance_method")
    llm_stance = candidate.get("evidence_stance") if stance_method == esl.STANCE_METHOD_LLM else None
    reviewer_expected = match["_reviewer_expected_stance"]
    return {
        "sample_id": match["_sample_id"],
        "claim_id": match["claim_id"],
        "ticker": match["ticker"],
        "target_alpha_id": match["matched_alpha"],
        "claim": match["claim"],
        "deterministic_v1_stance": match["_deterministic_v1_stance"],
        "llm_v1_stance": llm_stance or "",
        "final_stance": candidate.get("evidence_stance"),
        "counter_alpha_id": candidate.get("counter_alpha_id") or "",
        "stance_method": stance_method or "",
        "fallback_reason": candidate.get("stance_fallback_reason") or "",
        "reviewer_expected_stance": reviewer_expected or "",
        "agreement_with_existing_review": "N/A" if not reviewer_expected else str(candidate.get("evidence_stance") == reviewer_expected),
    }


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--execute-rerun", action="store_true")
    parser.add_argument("--profile-id", default=ANTHROPIC_PROFILE_ID)
    args = parser.parse_args(argv)

    approved = os.environ.get(APPROVAL_ENV_VAR, "") == "true"
    if not args.execute_rerun or not approved:
        _write_blocked(
            BLOCKED_NOT_AUTHORIZED,
            {
                "execute_rerun_flag": args.execute_rerun,
                "approval_env_var": APPROVAL_ENV_VAR,
                "approval_env_var_set_to_true": approved,
            },
        )
        return 1

    if not ORIGINAL_VALIDATION_CSV.exists():
        _write_blocked(BLOCKED_ORIGINAL_VALIDATION_UNAVAILABLE, {"path": str(ORIGINAL_VALIDATION_CSV)})
        return 1
    if not SAMPLE_PATH.exists():
        _write_blocked(BLOCKED_SAMPLE_UNAVAILABLE, {"path": str(SAMPLE_PATH)})
        return 1

    failed_rows, valid_rows = _identify_failed_30()
    if len(failed_rows) != EXPECTED_FAILED_ROW_COUNT:
        _write_blocked(
            BLOCKED_FAILED_ROW_COUNT_UNEXPECTED,
            {"count": len(failed_rows), "expected": EXPECTED_FAILED_ROW_COUNT, "sample_ids": [r["sample_id"] for r in failed_rows]},
        )
        return 1

    failed_sample_ids = {r["sample_id"] for r in failed_rows}
    print(f"IDENTIFIED_FAILED_30 = {sorted(failed_sample_ids)}")

    num_batches = (len(failed_rows) + esl.BATCH_SIZE - 1) // esl.BATCH_SIZE
    if num_batches > MAX_LOGICAL_CALLS:
        _write_blocked(BLOCKED_CALL_BUDGET_WOULD_BE_EXCEEDED, {"num_batches": num_batches, "max": MAX_LOGICAL_CALLS})
        return 1

    sample_data = json.loads(SAMPLE_PATH.read_text(encoding="utf-8"))
    records_by_id = {r["sample_id"]: r for r in sample_data["records"]}
    # Rebuild full row context (claim text, stance_reason_codes, etc.) from
    # the untouched original 50-row sample, restricted to exactly the 30
    # failed sample_ids -- not resampled, not selected by current semantics.
    failed_full_rows = [records_by_id[sid] for sid in sorted(failed_sample_ids)]
    if len(failed_full_rows) != EXPECTED_FAILED_ROW_COUNT:
        _write_blocked("BLOCKED_SAMPLE_ROW_LOOKUP_MISMATCH", {"found": len(failed_full_rows)})
        return 1

    try:
        from dotenv import load_dotenv

        load_dotenv()
    except ImportError:
        pass

    try:
        profile = get_research_profile(args.profile_id)
    except ResearchProfileError as exc:
        _write_blocked(BLOCKED_PROVIDER_CREDENTIALS_MISSING, {"reason_code": exc.reason_code})
        return 1

    try:
        from tradingagents.llm_clients import create_llm_client

        client = create_llm_client(
            provider=profile.llm_provider,
            model=profile.quick_think_llm,
            base_url=profile.backend_url,
            timeout=VALIDATION_TIMEOUT_SECONDS,
            max_retries=0,
        )
        model = client.get_llm()
    except Exception as exc:
        _write_blocked(BLOCKED_PROVIDER_CLIENT_INITIALIZATION_FAILED, {"error_type": type(exc).__name__})
        return 1

    gateway = Week2LLMGateway(
        model,
        run_id="b1-llm-stance-failed30-rerun",
        output_root=str(REPO_ROOT / "outputs" / "runs"),
        timeout_seconds=VALIDATION_TIMEOUT_SECONDS,
        max_retries=0,  # RETRIES = 0
        max_calls=MAX_REAL_PROVIDER_ATTEMPTS,  # hard-enforced budget of 3
        provider=profile.llm_provider,
        model_name=profile.quick_think_llm,
    )

    taxonomy = load_alpha_taxonomy()
    matches = _build_synthetic_matches(failed_full_rows)

    # The real, unmodified production function -- identical code path the
    # original 50-row validation and live research runs use.
    stats = esl.apply_llm_stance_upgrade(matches, taxonomy, llm_gateway=gateway)

    rerun_rows = [_rerun_row(m) for m in matches]
    for row in rerun_rows:
        row["provenance"] = "parser_fix_rerun"

    RERUN_CSV_PATH.parent.mkdir(parents=True, exist_ok=True)
    with RERUN_CSV_PATH.open("w", encoding="utf-8", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=CSV_FIELDS)
        writer.writeheader()
        writer.writerows(rerun_rows)

    # Combined view: prior 20 valid (provenance=original_50_row_validation)
    # + new rerun results for the 30 (provenance=parser_fix_rerun). The
    # original validation CSV is never overwritten.
    combined_rows = []
    for r in valid_rows:
        row = {field: r.get(field, "") for field in CSV_FIELDS if field != "provenance"}
        row["provenance"] = "original_50_row_validation"
        combined_rows.append(row)
    combined_rows.extend(rerun_rows)
    combined_rows.sort(key=lambda r: r["sample_id"])
    with COMBINED_CSV_PATH.open("w", encoding="utf-8", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=CSV_FIELDS)
        writer.writeheader()
        writer.writerows(combined_rows)

    rerun_fallback_reason_counts = dict(stats.fallback_reason_counts)
    result = {
        "status": "PASS",
        "failed_30_sample_ids": sorted(failed_sample_ids),
        "rerun_batch_count": stats.batch_count,
        "rerun_logical_provider_calls": stats.logical_provider_calls,
        "rerun_real_provider_attempts": stats.real_provider_attempts,
        "rerun_retries_used": 0,
        "rerun_llm_valid_count": stats.llm_result_count,
        "rerun_deterministic_fallback_count": stats.deterministic_fallback_count,
        "rerun_fallback_reason_counts": rerun_fallback_reason_counts,
        "rerun_invalid_json_count": rerun_fallback_reason_counts.get(esl.FALLBACK_MALFORMED_RESPONSE, 0),
        "prior_valid_llm_rows_preserved": len(valid_rows),
        "final_50_llm_valid_count": len(valid_rows) + stats.llm_result_count,
        "final_50_deterministic_fallback_count": stats.deterministic_fallback_count,
        "invalid_llm_output_admitted": stats.invalid_llm_output_admitted,
        "provider": gateway.provider,
        "model_name": gateway.model_name,
        "rerun_csv": str(RERUN_CSV_PATH.relative_to(REPO_ROOT)),
        "combined_csv": str(COMBINED_CSV_PATH.relative_to(REPO_ROOT)),
        "original_validation_csv_untouched": str(ORIGINAL_VALIDATION_CSV.relative_to(REPO_ROOT)),
    }
    RERUN_JSON_PATH.write_text(json.dumps(result, ensure_ascii=False, indent=2), encoding="utf-8")
    print(json.dumps(result, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
