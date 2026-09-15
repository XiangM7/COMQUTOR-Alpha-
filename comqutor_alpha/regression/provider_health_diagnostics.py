"""v0.1.3 Provider Health + Benchmark Eligibility Diagnostics.

Purely observational, read-only diagnostics computed from ALREADY-persisted
run artifacts. This module never calls a Provider, never reruns anything,
never mutates a historical run artifact in place, and never influences
Alpha mapping, evidence qualification, structure extraction, activation
scoring, conflicts, or Gold results -- see
docs/audit_artifacts/v0_1_3_provider_health_implementation.md for the full
non-effect proof.

Canonical data sources (see docs/audit_artifacts/v0_1_3_provider_health_diagnostics.md
Section "Canonical Data Sources" for the full mapping):

- ``error_logs/week2_llm_errors.jsonl`` -- raw, per-retry-attempt Provider
  failure EVENTS, one line per attempt (task, error_code, attempt,
  created_at). A batch that fails on attempt 1 and succeeds on attempt 2
  still logs one failure line despite the task ultimately succeeding --
  this is deliberately NOT the same thing as a "final orphan".
- ``alpha_matches.json`` (``matches[].match_status`` /
  ``.alpha_match_fallback_reason`` / ``.deterministic_top_alpha`` /
  ``.deterministic_match_status``) -- the canonical, definitive, per-claim
  FINAL outcome of the alpha_classifier task (Pure-LLM Semantic Authority
  has no intermediate fallback: a claim either gets a real LLM verdict, or
  ends up ``match_status='unavailable'`` after all retries are exhausted).
- ``llm_semantic_calls.jsonl`` (``task`` / ``fallback_used`` /
  ``error_code``) -- the canonical, definitive, per-call FINAL outcome for
  tasks that DO have a deterministic fallback path (evidence_stance_classifier,
  structure_extractor): ``fallback_used=True`` means the deterministic
  baseline was used for that call because the LLM path did not complete.
- ``llm_semantic_manifest.json`` (``tasks`` / ``provider_call_count`` /
  ``accepted_count`` / ``fallback_count``) -- per-task call-attempt
  denominators, where available.

This module builds on, and never duplicates, the existing
``comqutor_alpha.regression.semantic_execution_health`` module (which
already computes the alpha_classifier-specific coverage/health contract
from ``alpha_matches.json``) -- ``compute_semantic_execution_health`` is
reused directly rather than re-implemented.
"""

from __future__ import annotations

import json
from collections import Counter
from pathlib import Path
from typing import Any

from comqutor_alpha.regression.semantic_execution_health import (
    compute_semantic_execution_health,
)

PROVIDER_HEALTHY = "PROVIDER_HEALTHY"
PROVIDER_DEGRADED = "PROVIDER_DEGRADED"
VALID_PROVIDER_HEALTH_STATUSES = frozenset({PROVIDER_HEALTHY, PROVIDER_DEGRADED})

# Section 5: semantic-critical components -- prior audit authority
# (docs/audit_artifacts/v0_1_3_provider_failure_blast_radius.json), not
# re-derived from current Alpha misses. claim_batch_enrichment and
# structured_adapter are presentation/extraction-QC tasks, not semantic
# critical, per that same prior audit's classification.
SEMANTIC_CRITICAL_TASKS = frozenset(
    {"alpha_classifier", "evidence_stance_classifier", "structure_extractor"}
)
PRESENTATION_ONLY_TASKS = frozenset({"claim_batch_enrichment", "structured_adapter"})

# Impact classes (Section 8) -- reused vocabulary from the prior blast-radius
# audit, not invented fresh from current Alpha misses.
IMPACT_NO_SEMANTIC_IMPACT = "NO_SEMANTIC_IMPACT"
IMPACT_PRESENTATION_ONLY = "PRESENTATION_ONLY"
IMPACT_EVIDENCE_ATTRITION = "EVIDENCE_ATTRITION"
IMPACT_ALPHA_MAPPING_ATTRITION = "ALPHA_MAPPING_ATTRITION"
IMPACT_STANCE_ATTRITION = "STANCE_ATTRITION"
IMPACT_STRUCTURE_ATTRITION = "STRUCTURE_ATTRITION"
IMPACT_CONFLICT_ATTRITION = "CONFLICT_ATTRITION"
IMPACT_ACTIVATION_ATTRITION = "ACTIVATION_ATTRITION"
IMPACT_TRACEABILITY_UNKNOWN = "TRACEABILITY_UNKNOWN"

# Section 22: deterministic error-type bucket names, derived from the exact
# WEEK2_LLM_* error codes already used throughout this codebase (see
# comqutor_alpha/structure_engine/alpha_mapper.py's
# _GATEWAY_ERROR_CODE_TO_FALLBACK_REASON) -- not invented fresh.
_ERROR_CODE_TO_BUCKET = {
    "WEEK2_LLM_TIMEOUT": "TIMEOUT",
    "WEEK2_LLM_TRANSPORT_ERROR": "TRANSPORT_ERROR",
    "WEEK2_LLM_PROVIDER_ERROR": "TRANSPORT_ERROR",
    "WEEK2_LLM_RATE_LIMIT": "HTTP_ERROR",
    "WEEK2_LLM_VALIDATION_FAILED": "SCHEMA_ERROR",
    "WEEK2_LLM_INVALID_JSON": "PARSE_ERROR",
    "WEEK2_LLM_INPUT_TOO_LARGE": "OTHER",
    "WEEK2_LLM_CALL_BUDGET_EXHAUSTED": "RETRY_EXHAUSTED",
}


def _error_bucket(error_code: str | None) -> str:
    return _ERROR_CODE_TO_BUCKET.get(str(error_code or ""), "OTHER")


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


def compute_provider_failure_events(run_dir: str | Path) -> dict[str, Any]:
    """Section 6: raw, per-retry-attempt Provider failure EVENT counts from
    ``error_logs/week2_llm_errors.jsonl`` -- never final-outcome counts.
    Never call these "failed claims"; see the module docstring."""
    run_dir = Path(run_dir)
    records = _read_jsonl(run_dir / "error_logs" / "week2_llm_errors.jsonl")

    by_task: Counter[str] = Counter()
    by_task_and_bucket: Counter[tuple[str, str]] = Counter()
    error_type_counts: Counter[str] = Counter()
    for record in records:
        task = str(record.get("task") or "unknown")
        bucket = _error_bucket(record.get("error_code"))
        by_task[task] += 1
        by_task_and_bucket[(task, bucket)] += 1
        error_type_counts[bucket] += 1

    provider_failure_events = len(records)
    semantic_critical_failure_events = sum(
        count for task, count in by_task.items() if task in SEMANTIC_CRITICAL_TASKS
    )
    alpha_classifier_failure_events = by_task.get("alpha_classifier", 0)

    return {
        "provider_failure_events": provider_failure_events,
        "semantic_critical_failure_events": semantic_critical_failure_events,
        "alpha_classifier_failure_events": alpha_classifier_failure_events,
        "provider_failure_events_by_task": dict(by_task),
        "error_type_counts": dict(error_type_counts),
        "error_type_counts_by_task": {
            f"{task}:{bucket}": count for (task, bucket), count in by_task_and_bucket.items()
        },
    }


def compute_final_orphans(run_dir: str | Path) -> dict[str, Any]:
    """Section 3/6: FINAL, post-retry-exhaustion orphan counts -- the
    semantic unit remained unresolved after every retry/fallback attempt.

    - alpha_classifier: canonical source is ``alpha_matches.json``'s
      per-claim ``match_status == 'unavailable'`` (Pure-LLM Semantic
      Authority has no intermediate fallback for this task).
    - evidence_stance_classifier / structure_extractor: canonical source is
      ``llm_semantic_calls.jsonl``'s per-call ``fallback_used == True`` for
      that task (both tasks DO have a deterministic fallback baseline, so a
      call ending in fallback is that call's final, non-LLM outcome).
    """
    run_dir = Path(run_dir)

    alpha_matches_path = run_dir / "alpha_matches.json"
    matches: list[dict[str, Any]] = []
    if alpha_matches_path.is_file():
        payload = _read_json(alpha_matches_path)
        raw_matches = payload.get("matches")
        if isinstance(raw_matches, list):
            matches = raw_matches
    alpha_classifier_final_orphans = sum(
        1 for m in matches if m.get("match_status") == "unavailable"
    )

    calls = _read_jsonl(run_dir / "llm_semantic_calls.jsonl")
    evidence_stance_final_orphans = sum(
        1
        for c in calls
        if c.get("task") == "evidence_stance_classifier" and c.get("fallback_used")
    )
    structure_extractor_final_orphans = sum(
        1 for c in calls if c.get("task") == "structure_extractor" and c.get("fallback_used")
    )

    provider_final_orphans_total = (
        alpha_classifier_final_orphans
        + evidence_stance_final_orphans
        + structure_extractor_final_orphans
    )

    return {
        "alpha_classifier_final_orphans": alpha_classifier_final_orphans,
        "evidence_stance_final_orphans": evidence_stance_final_orphans,
        "structure_extractor_final_orphans": structure_extractor_final_orphans,
        "provider_final_orphans_total": provider_final_orphans_total,
        "claims_orphaned_by_provider_failure": alpha_classifier_final_orphans,
    }


def compute_impacted_alphas(run_dir: str | Path) -> dict[str, Any]:
    """Section 7: the most important field. An Alpha is impacted ONLY when
    there is deterministic trace evidence that a Provider failure removed
    an otherwise-usable lineage for it:

        valid deterministic candidate (deterministic_match_status=='matched',
        a real deterministic_top_alpha)
        -> Provider failure (match_status=='unavailable')
        -> final orphan state (matched_alpha=None)

    Never counts an Alpha merely because a Provider call mentioned it, a
    failure happened somewhere in the run, or the Alpha is currently a
    Gold miss. Claims with match_status=='unavailable' but NO clean
    deterministic candidate are counted separately as
    ``traceability_unknown_count`` -- never guessed into an Alpha ID.
    """
    run_dir = Path(run_dir)
    alpha_matches_path = run_dir / "alpha_matches.json"
    matches: list[dict[str, Any]] = []
    if alpha_matches_path.is_file():
        payload = _read_json(alpha_matches_path)
        raw_matches = payload.get("matches")
        if isinstance(raw_matches, list):
            matches = raw_matches

    impacted_alpha_ids: set[str] = set()
    impacted_claims: list[dict[str, Any]] = []
    traceability_unknown_count = 0

    for m in matches:
        if m.get("match_status") != "unavailable":
            continue
        det_status = m.get("deterministic_match_status")
        det_alpha = m.get("deterministic_top_alpha")
        if det_status == "matched" and det_alpha:
            impacted_alpha_ids.add(str(det_alpha))
            impacted_claims.append(
                {
                    "claim_id": m.get("claim_id"),
                    "agent": m.get("agent"),
                    "deterministic_top_alpha": det_alpha,
                    "alpha_match_fallback_reason": m.get("alpha_match_fallback_reason"),
                }
            )
        else:
            traceability_unknown_count += 1

    return {
        "alphas_impacted_by_provider_failure": len(impacted_alpha_ids),
        "impacted_alpha_ids": sorted(impacted_alpha_ids),
        "impacted_claims": impacted_claims,
        "traceability_unknown_count": traceability_unknown_count,
    }


def classify_final_orphan_impact(
    *, task: str, has_deterministic_lineage: bool, is_semantic_critical: bool
) -> str:
    """Section 8: derive one primary impact class for a single final orphan,
    reusing the prior audit's classification logic (never invented fresh
    from current Alpha misses)."""
    if not is_semantic_critical:
        return IMPACT_PRESENTATION_ONLY
    if not has_deterministic_lineage:
        return IMPACT_TRACEABILITY_UNKNOWN
    if task == "alpha_classifier":
        return IMPACT_ALPHA_MAPPING_ATTRITION
    if task == "evidence_stance_classifier":
        return IMPACT_STANCE_ATTRITION
    if task == "structure_extractor":
        return IMPACT_STRUCTURE_ATTRITION
    return IMPACT_NO_SEMANTIC_IMPACT


def compute_provider_health_diagnostics(
    *, run_dir: str | Path, ticker: str | None = None, run_id: str | None = None
) -> dict[str, Any]:
    """Section 6/30 main entry point: the full per-run Provider Health
    diagnostic record. Pure function of already-persisted artifacts --
    zero Provider calls, zero mutation of any historical artifact."""
    run_dir = Path(run_dir)

    failure_events = compute_provider_failure_events(run_dir)
    final_orphans = compute_final_orphans(run_dir)
    impacted = compute_impacted_alphas(run_dir)
    semantic_health = None
    semantic_status = None
    try:
        semantic_health = compute_semantic_execution_health(run_dir=run_dir)
        semantic_status = semantic_health.get("semantic_execution_health_status")
    except Exception:
        # Section 21: never guess -- if the existing semantic-health
        # contract cannot be computed, report null, not a fabricated status.
        semantic_health = None
        semantic_status = None

    manifest_path = run_dir / "llm_semantic_manifest.json"
    manifest = _read_json(manifest_path) if manifest_path.is_file() else {}
    task_call_counts = manifest.get("tasks") if isinstance(manifest.get("tasks"), dict) else {}
    alpha_classifier_call_attempts = task_call_counts.get("alpha_classifier")
    semantic_critical_call_attempts = (
        sum(
            count
            for task, count in task_call_counts.items()
            if task in SEMANTIC_CRITICAL_TASKS
        )
        if task_call_counts
        else None
    )
    provider_call_attempts_total = manifest.get("provider_call_count")

    def _rate(numerator: int, denominator: Any) -> float | None:
        if not isinstance(denominator, (int, float)) or denominator <= 0:
            return None
        return round(numerator / denominator, 6)

    provider_failure_rate = _rate(
        failure_events["provider_failure_events"], provider_call_attempts_total
    )
    semantic_critical_failure_rate = _rate(
        failure_events["semantic_critical_failure_events"], semantic_critical_call_attempts
    )
    alpha_classifier_failure_rate = _rate(
        failure_events["alpha_classifier_failure_events"], alpha_classifier_call_attempts
    )

    # Section 9: conservative, non-arbitrary rule -- degraded iff at least
    # one final orphan exists anywhere in a semantic-critical stage. No
    # numeric failure-rate threshold is introduced.
    provider_health = (
        PROVIDER_DEGRADED if final_orphans["provider_final_orphans_total"] > 0 else PROVIDER_HEALTHY
    )

    # Section 10: manual-review trigger, never an automatic rejection.
    benchmark_review_required = impacted["alphas_impacted_by_provider_failure"] >= 1
    benchmark_review_reasons = [
        f"PROVIDER_FAILURE_IMPACTED_ALPHA:{alpha_id}" for alpha_id in impacted["impacted_alpha_ids"]
    ]

    return {
        "ticker": ticker,
        "run_id": run_id,
        "run_dir": str(run_dir),
        "semantic_status": semantic_status,
        "semantic_execution_health": semantic_health,
        "provider_health": provider_health,
        "provider_call_attempts_total": provider_call_attempts_total,
        "provider_failure_events": failure_events["provider_failure_events"],
        "provider_failure_rate": provider_failure_rate,
        "semantic_critical_call_attempts": semantic_critical_call_attempts,
        "semantic_critical_failure_events": failure_events["semantic_critical_failure_events"],
        "semantic_critical_failure_rate": semantic_critical_failure_rate,
        "alpha_classifier_call_attempts": alpha_classifier_call_attempts,
        "alpha_classifier_failure_events": failure_events["alpha_classifier_failure_events"],
        "alpha_classifier_failure_rate": alpha_classifier_failure_rate,
        "alpha_classifier_final_orphans": final_orphans["alpha_classifier_final_orphans"],
        "evidence_stance_final_orphans": final_orphans["evidence_stance_final_orphans"],
        "structure_extractor_final_orphans": final_orphans["structure_extractor_final_orphans"],
        "provider_final_orphans_total": final_orphans["provider_final_orphans_total"],
        "claims_orphaned_by_provider_failure": final_orphans["claims_orphaned_by_provider_failure"],
        "alphas_impacted_by_provider_failure": impacted["alphas_impacted_by_provider_failure"],
        "impacted_alpha_ids": impacted["impacted_alpha_ids"],
        "impacted_claims": impacted["impacted_claims"],
        "traceability_unknown_count": impacted["traceability_unknown_count"],
        "benchmark_review_required": benchmark_review_required,
        "benchmark_review_reasons": benchmark_review_reasons,
        "benchmark_auto_rejected": False,
        "provider_failure_components": sorted(failure_events["provider_failure_events_by_task"]),
        "provider_failure_error_types": failure_events["error_type_counts"],
        "provider_failure_events_by_task": failure_events["provider_failure_events_by_task"],
        "error_type_counts_by_task": failure_events["error_type_counts_by_task"],
    }


__all__ = [
    "PROVIDER_HEALTHY",
    "PROVIDER_DEGRADED",
    "VALID_PROVIDER_HEALTH_STATUSES",
    "SEMANTIC_CRITICAL_TASKS",
    "PRESENTATION_ONLY_TASKS",
    "IMPACT_NO_SEMANTIC_IMPACT",
    "IMPACT_PRESENTATION_ONLY",
    "IMPACT_EVIDENCE_ATTRITION",
    "IMPACT_ALPHA_MAPPING_ATTRITION",
    "IMPACT_STANCE_ATTRITION",
    "IMPACT_STRUCTURE_ATTRITION",
    "IMPACT_CONFLICT_ATTRITION",
    "IMPACT_ACTIVATION_ATTRITION",
    "IMPACT_TRACEABILITY_UNKNOWN",
    "compute_provider_failure_events",
    "compute_final_orphans",
    "compute_impacted_alphas",
    "classify_final_orphan_impact",
    "compute_provider_health_diagnostics",
]
