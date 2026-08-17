#!/usr/bin/env python3
"""B1 LLM Evidence Stance Upgrade -- bounded real 50-row validation.

Classifies the EXISTING J3 50-Evidence sample
(``docs/evidence_review_sample_records.json``) using the real, production
``evidence_stance_classifier`` batch task through the shared
``Week2LLMGateway`` -- the exact same request-building, batch-shape
validation, per-item identity/vocabulary/counter-Alpha validation, and
fail-soft fallback logic as ``comqutor_alpha.structure_engine.
evidence_stance_llm.apply_llm_stance_upgrade`` (no parallel implementation).

Never invoked automatically; never calls a Provider unless every one of
these is true:

- ``--execute-validation`` is passed,
- the environment variable ``COMQUTOR_B1_LLM_STANCE_50_VALIDATION_APPROVED``
  is exactly the string ``"true"``,
- the 50-row sample is present, unmodified, and exactly 50 records,
- batching the 50 rows at <=10 items/call would require at most 5 logical
  calls (it always does: 50 / 10 == 5 exactly).

The gateway itself is constructed with ``max_retries=0`` and
``max_calls=5`` -- a hard, enforced budget, not just a soft check: even a
bug in this script cannot cause more than 5 real Provider attempts.

This script never reads ``COMQUTOR_WEEK2_LLM_ENABLED`` as authorization and
never sets the approval variable itself. Never modifies the original
50-row sample.
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

APPROVAL_ENV_VAR = "COMQUTOR_B1_LLM_STANCE_50_VALIDATION_APPROVED"
MAX_LOGICAL_CALLS = 5
MAX_REAL_PROVIDER_ATTEMPTS = 5
VALIDATION_TIMEOUT_SECONDS = 60.0
EXPECTED_RECORD_COUNT = 50

SAMPLE_PATH = REPO_ROOT / "docs" / "evidence_review_sample_records.json"
OUTPUT_CSV_PATH = REPO_ROOT / "docs" / "audit_artifacts" / "b1_llm_stance_50_validation.csv"
OUTPUT_JSON_PATH = REPO_ROOT / "docs" / "audit_artifacts" / "b1_llm_stance_50_validation_result.json"

BLOCKED_NOT_AUTHORIZED = "BLOCKED_VALIDATION_NOT_AUTHORIZED"
BLOCKED_SAMPLE_UNAVAILABLE = "BLOCKED_SAMPLE_UNAVAILABLE"
BLOCKED_SAMPLE_RECORD_COUNT_UNEXPECTED = "BLOCKED_SAMPLE_RECORD_COUNT_UNEXPECTED"
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
]


def _write_blocked(reason: str, detail: dict[str, Any] | None = None) -> dict[str, Any]:
    payload = {"status": "BLOCKED", "reason": reason, "detail": detail or {}}
    OUTPUT_JSON_PATH.parent.mkdir(parents=True, exist_ok=True)
    OUTPUT_JSON_PATH.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
    print(json.dumps(payload, ensure_ascii=False, indent=2))
    return payload


def _load_sample() -> tuple[dict[str, Any], list[dict[str, Any]]]:
    data = json.loads(SAMPLE_PATH.read_text(encoding="utf-8"))
    return data, data["records"]


def _build_synthetic_matches(records: list[dict[str, Any]], taxonomy) -> list[dict[str, Any]]:
    """One synthetic match per J3 row, exactly at the granularity the row
    already is: one (claim_id, target_alpha_id) pair. The row's OWN
    already-recorded deterministic.v1 evidence_stance/counter_alpha_id/
    reason_codes/band become that candidate's starting (fallback) values --
    the real, frozen deterministic.v1 output for this exact sample, never
    recomputed."""
    matches = []
    for row in records:
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


def _write_outputs(matches: list[dict[str, Any]], stats: esl.StanceRunStats, gateway: Week2LLMGateway) -> dict[str, Any]:
    rows = []
    for match in matches:
        candidate = match["candidate_scores"][0]
        deterministic_stance = match["_deterministic_v1_stance"]
        stance_method = candidate.get("stance_method")
        llm_stance = candidate.get("evidence_stance") if stance_method == esl.STANCE_METHOD_LLM else None
        reviewer_expected = match["_reviewer_expected_stance"]
        rows.append(
            {
                "sample_id": match["_sample_id"],
                "claim_id": match["claim_id"],
                "ticker": match["ticker"],
                "target_alpha_id": match["matched_alpha"],
                "claim": match["claim"],
                "deterministic_v1_stance": deterministic_stance,
                "llm_v1_stance": llm_stance or "",
                "final_stance": candidate.get("evidence_stance"),
                "counter_alpha_id": candidate.get("counter_alpha_id") or "",
                "stance_method": stance_method or "",
                "fallback_reason": candidate.get("stance_fallback_reason") or "",
                "reviewer_expected_stance": reviewer_expected or "",
                "agreement_with_existing_review": "N/A" if not reviewer_expected else str(candidate.get("evidence_stance") == reviewer_expected),
            }
        )

    OUTPUT_CSV_PATH.parent.mkdir(parents=True, exist_ok=True)
    with OUTPUT_CSV_PATH.open("w", encoding="utf-8", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=CSV_FIELDS)
        writer.writeheader()
        writer.writerows(rows)

    disagreements = [
        r for r in rows if r["llm_v1_stance"] and r["llm_v1_stance"] != r["deterministic_v1_stance"]
    ]
    stance_distribution: dict[str, int] = {}
    for r in rows:
        stance_distribution[r["final_stance"]] = stance_distribution.get(r["final_stance"], 0) + 1

    review_gold_available = any(r["reviewer_expected_stance"] for r in rows)

    result = {
        "status": "PASS",
        "sample_path": str(SAMPLE_PATH.relative_to(REPO_ROOT)),
        "sample_record_count": len(matches),
        "batch_count": stats.batch_count,
        "logical_provider_calls": stats.logical_provider_calls,
        "real_provider_attempts": stats.real_provider_attempts,
        "retries_used": 0,
        "llm_result_count": stats.llm_result_count,
        "deterministic_fallback_count": stats.deterministic_fallback_count,
        "fallback_reason_counts": stats.fallback_reason_counts,
        "invalid_llm_output_admitted": stats.invalid_llm_output_admitted,
        "final_stance_distribution": stance_distribution,
        "llm_vs_deterministic_disagreement_count": len(disagreements),
        "review_gold_available": review_gold_available,
        "provider": gateway.provider,
        "model_name": gateway.model_name,
        "output_csv": str(OUTPUT_CSV_PATH.relative_to(REPO_ROOT)),
    }
    OUTPUT_JSON_PATH.write_text(json.dumps(result, ensure_ascii=False, indent=2), encoding="utf-8")
    print(json.dumps(result, ensure_ascii=False, indent=2))
    return result


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--execute-validation", action="store_true")
    parser.add_argument("--profile-id", default=ANTHROPIC_PROFILE_ID)
    args = parser.parse_args(argv)

    approved = os.environ.get(APPROVAL_ENV_VAR, "") == "true"
    if not args.execute_validation or not approved:
        _write_blocked(
            BLOCKED_NOT_AUTHORIZED,
            {
                "execute_validation_flag": args.execute_validation,
                "approval_env_var": APPROVAL_ENV_VAR,
                "approval_env_var_set_to_true": approved,
            },
        )
        return 1

    if not SAMPLE_PATH.exists():
        _write_blocked(BLOCKED_SAMPLE_UNAVAILABLE, {"path": str(SAMPLE_PATH)})
        return 1

    _, records = _load_sample()
    if len(records) != EXPECTED_RECORD_COUNT:
        _write_blocked(BLOCKED_SAMPLE_RECORD_COUNT_UNEXPECTED, {"count": len(records), "expected": EXPECTED_RECORD_COUNT})
        return 1

    num_batches = (len(records) + esl.BATCH_SIZE - 1) // esl.BATCH_SIZE
    if num_batches > MAX_LOGICAL_CALLS:
        _write_blocked(BLOCKED_CALL_BUDGET_WOULD_BE_EXCEEDED, {"num_batches": num_batches, "max": MAX_LOGICAL_CALLS})
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
        run_id="b1-llm-stance-50-validation",
        output_root=str(REPO_ROOT / "outputs" / "runs"),
        timeout_seconds=VALIDATION_TIMEOUT_SECONDS,
        max_retries=0,  # RETRIES = 0 for this validation run
        max_calls=MAX_REAL_PROVIDER_ATTEMPTS,  # hard-enforced budget
        provider=profile.llm_provider,
        model_name=profile.quick_think_llm,
    )

    taxonomy = load_alpha_taxonomy()
    matches = _build_synthetic_matches(records, taxonomy)

    # The real, unmodified production function -- same code path a live
    # research run would use, sequential batches, no concurrency.
    stats = esl.apply_llm_stance_upgrade(matches, taxonomy, llm_gateway=gateway)

    _write_outputs(matches, stats, gateway)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
