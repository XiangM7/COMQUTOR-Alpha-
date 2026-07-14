"""Assembles the canonical Week 3 ``structure_graph.json`` contract.

Combines :func:`graph_builder.build_structure_graph` and
:func:`activation_scorer.score_alpha_activations` into the single payload
that is written as the ``structure_graph.json`` file artifact and persisted
verbatim into ``structure_graphs.graph_json``. Kept as a thin composition
layer so the two engines stay independently unit-testable.
"""

from __future__ import annotations

from collections.abc import Mapping
from typing import Any

from comqutor_alpha.alpha_library.alpha_schema import AlphaDefinition
from comqutor_alpha.graph_engine.activation_scorer import score_alpha_activations
from comqutor_alpha.graph_engine.graph_builder import build_structure_graph
from comqutor_alpha.graph_engine.graph_schema import (
    ACTIVATION_SCORER_VERSION,
    GRAPH_BUILDER_VERSION,
    GRAPH_SCHEMA_VERSION,
)


def _provenance(
    alpha_matches_payload: Mapping[str, Any],
    extracted_structures_payload: Mapping[str, Any],
) -> dict[str, Any]:
    records = alpha_matches_payload.get("matches") if isinstance(alpha_matches_payload, Mapping) else None
    records = records if isinstance(records, list) else []
    counts = {"matched": 0, "ambiguous": 0, "no_match": 0}
    for record in records:
        if not isinstance(record, Mapping):
            continue
        status = record.get("match_status")
        if status in counts:
            counts[status] += 1
    return {
        "source_artifacts": {
            "alpha_matches_schema_version": alpha_matches_payload.get("schema_version")
            if isinstance(alpha_matches_payload, Mapping)
            else None,
            "extracted_structures_schema_version": extracted_structures_payload.get("schema_version")
            if isinstance(extracted_structures_payload, Mapping)
            else None,
        },
        "committed_match_count": counts["matched"],
        "ambiguous_match_count": counts["ambiguous"],
        "no_match_count": counts["no_match"],
        "total_claim_count": len(records),
    }


def build_structure_graph_stage(
    alpha_matches_payload: Mapping[str, Any],
    extracted_structures_payload: Mapping[str, Any],
) -> dict[str, Any]:
    """Stage 1: build the Structure Graph only (no activation scoring).

    Split out from :func:`build_and_score_structure_graph` so callers that
    need to distinguish "graph construction failed" from "activation
    scoring failed" (e.g. for a stage-specific error code) can catch each
    stage independently.
    """
    return build_structure_graph(alpha_matches_payload, extracted_structures_payload)


def score_and_assemble_structure_graph(
    graph: Mapping[str, Any],
    alpha_matches_payload: Mapping[str, Any],
    extracted_structures_payload: Mapping[str, Any],
    *,
    taxonomy: Mapping[str, AlphaDefinition] | None = None,
    run_timestamp: Any = None,
    as_of: Any = None,
) -> dict[str, Any]:
    """Stage 2: score all MVP-10 Alphas against an already-built graph and
    assemble the final ``structure_graph.json`` contract."""
    activation = score_alpha_activations(
        alpha_matches_payload,
        graph["graph_coherence"]["score"],
        taxonomy=taxonomy,
        run_timestamp=run_timestamp,
        as_of=as_of,
    )

    return {
        "schema_version": GRAPH_SCHEMA_VERSION,
        "graph_builder_version": GRAPH_BUILDER_VERSION,
        "activation_scorer_version": ACTIVATION_SCORER_VERSION,
        "run_id": graph["run_id"],
        "ticker": graph["ticker"],
        "nodes": graph["nodes"],
        "edges": graph["edges"],
        "graph_metrics": graph["graph_metrics"],
        "graph_coherence": graph["graph_coherence"],
        "activation": {
            "formula_version": activation["formula_version"],
            "weights": activation["weights"],
            "run_timestamp": activation["run_timestamp"],
            "as_of": activation["as_of"],
            "alphas": activation["alphas"],
        },
        "dominant_alphas": activation["dominant_alphas"],
        "provenance": _provenance(alpha_matches_payload, extracted_structures_payload),
    }


def build_and_score_structure_graph(
    alpha_matches_payload: Mapping[str, Any],
    extracted_structures_payload: Mapping[str, Any],
    *,
    taxonomy: Mapping[str, AlphaDefinition] | None = None,
    run_timestamp: Any = None,
    as_of: Any = None,
) -> dict[str, Any]:
    """Build the Structure Graph and score all MVP-10 Alphas against it.

    Pure function of its inputs (plus the optional deterministic
    ``run_timestamp``/``as_of`` pair) -- no I/O, no wall-clock reads. Both
    stages combined; callers that need per-stage error isolation should use
    :func:`build_structure_graph_stage` and
    :func:`score_and_assemble_structure_graph` directly instead.
    """
    graph = build_structure_graph_stage(alpha_matches_payload, extracted_structures_payload)
    return score_and_assemble_structure_graph(
        graph,
        alpha_matches_payload,
        extracted_structures_payload,
        taxonomy=taxonomy,
        run_timestamp=run_timestamp,
        as_of=as_of,
    )
