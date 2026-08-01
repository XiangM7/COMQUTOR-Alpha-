"""Cross-run metric aggregation over a batch of ``CaseResult``s.

Every rate here is computed only from cases that actually reached
``completed`` -- a ``pending_fixture``/``blocked`` case is reported
separately (never silently folded into a denominator as if it were a
failure, and never dropped as if it never existed).
"""

from __future__ import annotations

from typing import Any

from comqutor_alpha.evaluation.runner import (
    STATUS_BLOCKED,
    STATUS_COMPLETED,
    STATUS_ERROR,
    STATUS_PENDING_FIXTURE,
    CaseResult,
)


def _rate(numerator: int, denominator: int) -> float | None:
    if denominator <= 0:
        return None
    return numerator / denominator


def aggregate_cross_run_metrics(results: list[CaseResult]) -> dict[str, Any]:
    total = len(results)
    by_status = {
        STATUS_COMPLETED: [r for r in results if r.status == STATUS_COMPLETED],
        STATUS_PENDING_FIXTURE: [r for r in results if r.status == STATUS_PENDING_FIXTURE],
        STATUS_BLOCKED: [r for r in results if r.status == STATUS_BLOCKED],
        STATUS_ERROR: [r for r in results if r.status == STATUS_ERROR],
    }
    completed = by_status[STATUS_COMPLETED]
    provider_calls = sum(r.provider_calls for r in results)

    operational = {
        "total_cases": total,
        "completed_cases": len(completed),
        "pending_fixture_cases": len(by_status[STATUS_PENDING_FIXTURE]),
        "blocked_cases": len(by_status[STATUS_BLOCKED]),
        "failed_cases": len(by_status[STATUS_ERROR]),
        "provider_calls": provider_calls,
        "missing_artifact_rate": _rate(len(by_status[STATUS_PENDING_FIXTURE]) + len(by_status[STATUS_BLOCKED]), total),
        "schema_failure_rate": _rate(len(by_status[STATUS_ERROR]), total),
        "canonical_block_parse_failure_rate": None,  # not separately distinguished by this harness's inputs today
    }

    claims_counts = [r.actual.get("claims", {}) for r in completed if r.actual.get("claims")]
    candidate_segments = sum(c.get("retained_claim_count") or 0 for c in claims_counts)
    analytical = sum(c.get("analytical_claim_count") or 0 for c in claims_counts)
    context_only = sum(c.get("context_only_claim_count") or 0 for c in claims_counts)
    claims = {
        "retained_claims_total": candidate_segments,
        "analytical_claim_total": analytical,
        "context_only_claim_total": context_only,
        "analytical_to_context_only_ratio": _rate(analytical, context_only) if context_only else None,
    }

    graph_node_counts = [r.actual.get("graph", {}).get("node_count") for r in completed if r.actual.get("graph")]
    graph_edge_counts = [r.actual.get("graph", {}).get("edge_count") for r in completed if r.actual.get("graph")]
    zero_edge_cases = sum(1 for n in graph_edge_counts if n == 0)
    relations_graph = {
        "graph_node_count_distribution": sorted(n for n in graph_node_counts if n is not None),
        "graph_edge_count_distribution": sorted(n for n in graph_edge_counts if n is not None),
        "zero_edge_case_count": zero_edge_cases,
    }

    active_alpha_counts = [len(r.actual.get("activation", {}).get("active_alpha_ids") or []) for r in completed if r.actual.get("activation")]
    no_local_structure_rate = _rate(
        sum(1 for n in active_alpha_counts if n == 0), len(active_alpha_counts)
    )
    activation = {
        "scored_case_count": len(active_alpha_counts),
        "active_alpha_count_distribution": sorted(active_alpha_counts),
        "no_active_alpha_rate": no_local_structure_rate,
    }

    conflict_blocks = [r.actual.get("conflicts", {}) for r in completed if r.actual.get("conflicts")]
    declared = [c.get("declared_pair_count") for c in conflict_blocks if c.get("declared_pair_count") is not None]
    evaluated = [c.get("evaluated_pair_count") for c in conflict_blocks if c.get("evaluated_pair_count") is not None]
    admitted_counts = [len(c.get("admitted") or []) for c in conflict_blocks]
    missing_bull = sum(
        1 for c in conflict_blocks for a in (c.get("admitted") or []) if not (a.get("bull_raw_claim_count") or 0) > 0
    )
    missing_bear = sum(
        1 for c in conflict_blocks for a in (c.get("admitted") or []) if not (a.get("bear_raw_claim_count") or 0) > 0
    )
    main_conflict_available = sum(1 for c in conflict_blocks if c.get("main_conflict_id"))
    conflict = {
        "declared_pair_count_total": sum(declared),
        "evaluated_pair_count_total": sum(evaluated),
        "admitted_pair_count_total": sum(admitted_counts),
        "conflicts_missing_bull_evidence": missing_bull,
        "conflicts_missing_bear_evidence": missing_bear,
        "main_conflict_available_case_count": main_conflict_available,
    }

    # Data Sanity: no per-case data-sanity recomputation is performed by
    # this harness (see runner.py) -- explicitly reported as unavailable
    # rather than fabricated as all-zero.
    data_sanity = {
        "available": False,
        "reason": "cross_run.py does not recompute data-sanity checks; a case's source run's own data_sanity.json is not read by this harness today",
    }

    return {
        "operational": operational,
        "claims": claims,
        "relations_graph": relations_graph,
        "activation": activation,
        "conflict": conflict,
        "data_sanity": data_sanity,
    }


__all__ = ["aggregate_cross_run_metrics"]
