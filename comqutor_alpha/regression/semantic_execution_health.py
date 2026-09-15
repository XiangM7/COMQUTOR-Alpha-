"""Step 5A (v0.1.2.1) Sections 10-12: runtime semantic-execution health
contract.

This measures whether the Pure-LLM Alpha classifier actually got to render a
real verdict on the real workload -- it is completely independent of, and
never influenced by, any expected-Alpha regression label
(comqutor_alpha.regression.authority_contract lives on a different axis
entirely). A run can have PASS semantic health and a low Alpha hit-rate
(genuine semantic disagreement, a Step-5B-style question) or FAIL semantic
health while coincidentally matching some expected Alphas (meaningless: most
claims never received a real classifier verdict in the first place). QA
baseline promotion requires PASS -- see ``is_valid_for_qa_baseline_promotion``.

Critical invariant (Section 11): Provider execution failure is never
converted into semantic NONE, and deterministic Alpha scoring is never used
as a semantic fallback -- UNAVAILABLE and NONE remain permanently distinct
here, exactly as comqutor_alpha.structure_engine.alpha_mapper already keeps
them distinct in match_status.
"""

from __future__ import annotations

import json
from collections import Counter
from pathlib import Path
from typing import Any

HEALTH_PASS = "PASS"
HEALTH_DEGRADED = "DEGRADED"
HEALTH_FAIL = "FAIL"
VALID_HEALTH_STATUSES = frozenset({HEALTH_PASS, HEALTH_DEGRADED, HEALTH_FAIL})

# Section 15: this is a runtime COVERAGE target, judged before seeing
# repaired semantic output, never tuned after the fact. classified_coverage
# = (MATCHED + NONE) / eligible_claims.
CLASSIFIED_COVERAGE_TARGET = 0.95
# Below this, health is FAIL outright rather than merely DEGRADED -- a run
# where fewer than half of all eligible claims ever got a real classifier
# verdict cannot be called merely "degraded".
DEGRADED_COVERAGE_FLOOR = 0.50

DISABLED_FALLBACK_REASON = "disabled"


class SemanticExecutionHealthError(Exception):
    """Raised only for a structurally unreadable run -- never for a low
    coverage number, which is a legitimate FAIL/DEGRADED health result, not
    an exception."""


def _read_json(path: Path) -> dict[str, Any]:
    return json.loads(path.read_text())


def _read_jsonl(path: Path) -> list[dict[str, Any]]:
    if not path.exists():
        return []
    records = []
    for line in path.read_text().splitlines():
        line = line.strip()
        if line:
            records.append(json.loads(line))
    return records


def compute_semantic_execution_health(*, run_dir: str | Path) -> dict[str, Any]:
    """Compute the semantic execution health summary for one already-
    persisted run. Reads only existing artifacts -- never calls a Provider,
    never reruns anything, never reads a regression/expectation label."""

    run_dir = Path(run_dir)
    alpha_matches_path = run_dir / "alpha_matches.json"
    if not alpha_matches_path.is_file():
        raise SemanticExecutionHealthError(f"alpha_matches.json not found under {run_dir}")
    alpha_matches = _read_json(alpha_matches_path)
    matches = alpha_matches.get("matches")
    if not isinstance(matches, list):
        raise SemanticExecutionHealthError("alpha_matches.json has no matches array")

    eligible_claim_count = len(matches)
    status_counts = Counter(m.get("match_status") for m in matches)
    matched_count = status_counts.get("matched", 0)
    none_count = status_counts.get("no_match", 0)
    unavailable_count = status_counts.get("unavailable", 0)
    classified_claim_count = matched_count + none_count

    unavailable_reason_counts: dict[str, int] = {}
    for m in matches:
        if m.get("match_status") == "unavailable":
            reason = m.get("alpha_match_fallback_reason") or "unknown"
            unavailable_reason_counts[reason] = unavailable_reason_counts.get(reason, 0) + 1

    manifest_path = run_dir / "llm_semantic_manifest.json"
    manifest = _read_json(manifest_path) if manifest_path.is_file() else {}
    error_log_records = _read_jsonl(run_dir / "error_logs" / "week2_llm_errors.jsonl")
    error_code_counts = Counter(e.get("error_code") for e in error_log_records)

    provider_attempts = manifest.get("provider_call_count")
    provider_successes = manifest.get("accepted_count")
    timeouts = error_code_counts.get("WEEK2_LLM_TIMEOUT", 0)
    validation_failures = error_code_counts.get("WEEK2_LLM_VALIDATION_FAILED", 0) + error_code_counts.get(
        "WEEK2_LLM_INVALID_JSON", 0
    )
    budget_exhaustions = error_code_counts.get("WEEK2_LLM_CALL_BUDGET_EXHAUSTED", 0)
    rate_limits = error_code_counts.get("WEEK2_LLM_RATE_LIMIT", 0)
    transport_errors = error_code_counts.get("WEEK2_LLM_TRANSPORT_ERROR", 0) + error_code_counts.get(
        "WEEK2_LLM_PROVIDER_ERROR", 0
    )
    # Retries are individually-budgeted attempts (Week2LLMGateway._reserve_
    # call is called once per attempt, including retries -- see
    # docs/audit_artifacts/week2_runtime_capacity_root_cause_v0.1.2.1.json
    # question 10), so an exact retry count is not separately recoverable
    # from the error log alone without double-counting first attempts.
    # Report explicitly as unavailable rather than guessing.
    retries = "EXACT_COUNT_UNAVAILABLE_FROM_PERSISTED_ARTIFACTS"

    classified_coverage = (classified_claim_count / eligible_claim_count) if eligible_claim_count else None
    disabled_caused_unavailable = unavailable_reason_counts.get(DISABLED_FALLBACK_REASON, 0)

    status: str
    status_reason: str
    if disabled_caused_unavailable > 0:
        status = HEALTH_FAIL
        status_reason = "CLASSIFIER_DISABLED_DURING_A_REAL_RUN"
    elif eligible_claim_count == 0:
        # No eligible claims is not itself a failure of the classifier --
        # there was nothing to classify -- but it is not evaluable as a
        # coverage number either.
        status = HEALTH_PASS
        status_reason = "NO_ELIGIBLE_CLAIMS"
    elif classified_coverage is not None and classified_coverage >= CLASSIFIED_COVERAGE_TARGET:
        status = HEALTH_PASS
        status_reason = "COVERAGE_AT_OR_ABOVE_TARGET"
    elif classified_coverage is not None and classified_coverage >= DEGRADED_COVERAGE_FLOOR:
        status = HEALTH_DEGRADED
        status_reason = "COVERAGE_BELOW_TARGET_ABOVE_FLOOR"
    else:
        status = HEALTH_FAIL
        status_reason = "EXCESSIVE_ALPHA_MAPPER_UNAVAILABLE"

    return {
        "run_dir": str(run_dir),
        "eligible_claim_count": eligible_claim_count,
        "classified_claim_count": classified_claim_count,
        "matched_count": matched_count,
        "none_count": none_count,
        "unavailable_count": unavailable_count,
        "unavailable_rate": (unavailable_count / eligible_claim_count) if eligible_claim_count else None,
        "unavailable_reason_counts": unavailable_reason_counts,
        "classified_coverage": classified_coverage,
        "classified_coverage_target": CLASSIFIED_COVERAGE_TARGET,
        "provider_attempts": provider_attempts,
        "provider_successes": provider_successes,
        "timeouts": timeouts,
        "rate_limits": rate_limits,
        "transport_or_provider_errors": transport_errors,
        "validation_failures": validation_failures,
        "budget_exhaustions": budget_exhaustions,
        "retries": retries,
        "disabled_caused_unavailable": disabled_caused_unavailable,
        "semantic_execution_health_status": status,
        "semantic_execution_health_status_reason": status_reason,
    }


def is_valid_for_qa_baseline_promotion(health: dict[str, Any]) -> bool:
    """Section 12 fail-closed QA rule: a run may technically complete and
    export all required artifacts while its semantic classification is
    unusable. Such a run may still be RETAINED (technical_complete=true,
    semantic_valid=false) -- this function only gates QA baseline
    ELIGIBILITY, never artifact persistence."""

    status = health.get("semantic_execution_health_status")
    if status not in VALID_HEALTH_STATUSES:
        raise SemanticExecutionHealthError(f"unrecognized semantic_execution_health_status: {status!r}")
    return status == HEALTH_PASS


def technical_vs_semantic_status(
    *, artifact_completeness_status: str, health: dict[str, Any]
) -> dict[str, Any]:
    """Section 3's required explicit distinction: technical_completeness is
    never sufficient evidence of semantic_execution_health, and the two
    must always be reported side by side, never collapsed into one boolean."""

    return {
        "technical_completeness": "PASS" if artifact_completeness_status == "9/9" else "FAIL",
        "semantic_execution_health": health.get("semantic_execution_health_status"),
        "semantic_execution_health_reason": health.get("semantic_execution_health_status_reason"),
        "qa_baseline_eligible": is_valid_for_qa_baseline_promotion(health)
        and artifact_completeness_status == "9/9",
    }
