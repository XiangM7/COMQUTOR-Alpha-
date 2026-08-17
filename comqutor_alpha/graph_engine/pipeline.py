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
from comqutor_alpha.exposure.seed_loader import load_exposure_seed, resolve_exposure_mode
from comqutor_alpha.exposure_engine import compute_run_entity_alpha_exposures
from comqutor_alpha.graph_engine.activation_scorer import score_alpha_activations
from comqutor_alpha.graph_engine.activation_scorer_v2 import (
    ACTIVATION_V2_FORMULA_VERSION,
    score_alpha_activations_v2,
)
from comqutor_alpha.graph_engine.alpha_level_classifier import classify_and_rebuild_collections
from comqutor_alpha.graph_engine.graph_builder import build_structure_graph
from comqutor_alpha.graph_engine.graph_schema import (
    ACTIVATION_SCORER_VERSION,
    GRAPH_BUILDER_VERSION,
    GRAPH_SCHEMA_VERSION_V2,
)


def _match_relation_details(record: Mapping[str, Any], alpha_id: str) -> dict[str, Any]:
    """Read back the Week 2 candidate entry for this claim's matched alpha.

    Never recomputes semantics -- only surfaces what the mapper already
    attached (relation / matched_keywords / matched_factors)."""
    for pool_key in ("eligible_candidates", "top_candidates", "candidate_scores"):
        pool = record.get(pool_key)
        if not isinstance(pool, list):
            continue
        for candidate in pool:
            if isinstance(candidate, Mapping) and str(candidate.get("alpha_id")) == alpha_id:
                return {
                    "relation": str(candidate.get("relation") or "unknown"),
                    "matched_keywords": [
                        str(k) for k in (candidate.get("matched_keywords") or []) if str(k).strip()
                    ],
                    "matched_factors": [
                        str(f) for f in (candidate.get("matched_factors") or []) if str(f).strip()
                    ],
                }
    return {"relation": "unknown", "matched_keywords": [], "matched_factors": []}


def _attach_evidence_detail(
    activation_alphas: list[dict[str, Any]],
    alpha_matches_payload: Mapping[str, Any],
) -> None:
    """Additively attach full per-claim evidence provenance to each scored
    alpha (claim text, agent, source_agent_output_id, match score, relation,
    matched keywords/factors, assertion status, direction). Purely a
    read-back join against ``alpha_matches`` records -- the frozen activation
    formula, weights, and every existing field stay byte-identical."""
    matches = (
        alpha_matches_payload.get("matches") if isinstance(alpha_matches_payload, Mapping) else None
    )
    by_claim_id: dict[str, Mapping[str, Any]] = {}
    if isinstance(matches, list):
        for record in matches:
            if isinstance(record, Mapping) and record.get("claim_id"):
                by_claim_id[str(record["claim_id"])] = record

    for entry in activation_alphas:
        alpha_id = str(entry.get("alpha_id") or "")
        details = []
        for claim_id in entry.get("claim_ids") or []:
            record = by_claim_id.get(str(claim_id))
            if record is None:
                continue
            relation_details = _match_relation_details(record, alpha_id)
            details.append(
                {
                    "claim_id": str(claim_id),
                    "claim": str(record.get("claim") or ""),
                    "agent": str(record.get("agent") or ""),
                    "source_agent_output_id": str(record.get("source_agent_output_id") or ""),
                    "match_score": record.get("score", 0.0),
                    "assertion_status": str(record.get("assertion_status") or "unknown"),
                    "direction": str(record.get("direction") or "unknown"),
                    **relation_details,
                }
            )
        details.sort(key=lambda item: item["claim_id"])
        entry["evidence_detail"] = details


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


def _activation_block(activation: Mapping[str, Any]) -> dict[str, Any]:
    return {
        "formula_version": activation["formula_version"],
        "weights": activation["weights"],
        "run_timestamp": activation["run_timestamp"],
        "as_of": activation["as_of"],
        "alphas": activation["alphas"],
    }


def score_and_assemble_structure_graph(
    graph: Mapping[str, Any],
    alpha_matches_payload: Mapping[str, Any],
    extracted_structures_payload: Mapping[str, Any],
    *,
    taxonomy: Mapping[str, AlphaDefinition] | None = None,
    run_timestamp: Any = None,
    as_of: Any = None,
    structured_records: Any = None,
    exposure_run_id: str | None = None,
    exposure_seed_bundle: Any = None,
    exposure_mode_decision: Any = None,
) -> dict[str, Any]:
    """Stage 2: score all MVP-10 Alphas against an already-built graph and
    assemble the final ``structure_graph.json`` contract.

    Versioned activation contract (Activation v2 sprint, additive):
    ``activation`` holds the *primary* payload (Activation v2 for every new
    run), ``activation_versions`` holds both full payloads keyed "v1"/"v2",
    and ``primary_activation_version`` names the primary formula. The v1
    payload is computed by the unchanged v1 scorer -- it stays available as
    the audit baseline. ``schema_version`` is unchanged: historical graphs
    (v1-only, no ``activation_versions``) remain fully readable.
    """
    activation_v1 = score_alpha_activations(
        alpha_matches_payload,
        graph["graph_coherence"]["score"],
        taxonomy=taxonomy,
        run_timestamp=run_timestamp,
        as_of=as_of,
    )
    _attach_evidence_detail(activation_v1["alphas"], alpha_matches_payload)

    activation_v2 = score_alpha_activations_v2(
        alpha_matches_payload,
        graph_edges=graph.get("edges") or (),
        ticker=graph.get("ticker"),
        structured_records=structured_records,
        taxonomy=taxonomy,
        run_timestamp=run_timestamp,
        as_of=as_of,
    )
    _attach_evidence_detail(activation_v2["alphas"], alpha_matches_payload)
    seed_bundle = exposure_seed_bundle or load_exposure_seed()
    mode_decision = exposure_mode_decision or resolve_exposure_mode(seed_bundle, str(graph["ticker"]))
    activation_v2, exposure_artifact = compute_run_entity_alpha_exposures(
        run_id=exposure_run_id or str(graph["run_id"]),
        ticker=str(graph["ticker"]),
        activation_payload=activation_v2,
        seed_bundle=seed_bundle,
        mode_decision=mode_decision,
    )
    # B4 alpha-level classification (task B4_ACTIVATION_LEVEL_ALIGNMENT):
    # the single authoritative pass, run only now that every qualification
    # input -- Activation v2's own score/caps/regime gate, and B3 Entity
    # Exposure's per-alpha record -- is available. Writes the final
    # status/target_level/qualified_level/is_blocked/blocked_from/
    # blocked_reason_codes/diagnostic_reason_codes onto each v2 alpha entry
    # and rebuilds dominant_alphas/active_alphas/regime_level_alphas/
    # candidate_alphas/blocked_alphas exactly once -- never re-derived
    # independently by the API or the frontend afterward.
    activation_v2 = classify_and_rebuild_collections(activation_v2)

    # Built exactly once and reused for both "activation" (the primary
    # payload callers read) and activation_versions["v2"] -- so the two can
    # never independently drift apart; validate_structure_graph_contract
    # checks this invariant holds, but constructing it once makes a
    # violation structurally impossible rather than merely usually-true.
    v1_block = _activation_block(activation_v1)
    v2_block = _activation_block(activation_v2)

    return {
        "schema_version": GRAPH_SCHEMA_VERSION_V2,
        "graph_builder_version": GRAPH_BUILDER_VERSION,
        "activation_scorer_version": ACTIVATION_SCORER_VERSION,
        "run_id": graph["run_id"],
        "ticker": graph["ticker"],
        "nodes": graph["nodes"],
        "edges": graph["edges"],
        "graph_metrics": graph["graph_metrics"],
        "graph_coherence": graph["graph_coherence"],
        "activation": v2_block,
        "activation_versions": {
            "v1": v1_block,
            "v2": v2_block,
        },
        "primary_activation_version": ACTIVATION_V2_FORMULA_VERSION,
        "dominant_alphas": activation_v2["dominant_alphas"],
        # B4 additive authoritative collections (task
        # B4_ACTIVATION_LEVEL_ALIGNMENT, section 11) -- dominant_alphas
        # above keeps its exact pre-existing meaning (dominant OR
        # regime_level) for backward compatibility; these four are new,
        # split by the single true qualified_level/is_blocked B4 just
        # computed. Sibling top-level fields, same pattern as
        # dominant_alphas -- never nested inside the narrower
        # activation/activation_versions blocks.
        "active_alphas": activation_v2["active_alphas"],
        "regime_level_alphas": activation_v2["regime_level_alphas"],
        "candidate_alphas": activation_v2["candidate_alphas"],
        "blocked_alphas": activation_v2["blocked_alphas"],
        "entity_alpha_exposures": exposure_artifact,
        "provenance": _provenance(alpha_matches_payload, extracted_structures_payload),
    }


def build_and_score_structure_graph(
    alpha_matches_payload: Mapping[str, Any],
    extracted_structures_payload: Mapping[str, Any],
    *,
    taxonomy: Mapping[str, AlphaDefinition] | None = None,
    run_timestamp: Any = None,
    as_of: Any = None,
    structured_records: Any = None,
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
        structured_records=structured_records,
    )
