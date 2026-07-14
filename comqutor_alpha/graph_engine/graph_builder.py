"""Week 3 Structure Graph builder.

Consumes validated Week 2 outputs only (``alpha_matches.json`` and
``extracted_structures.json``) and assembles a run-level, deterministic
``networkx.DiGraph``. Never reparses raw TradingAgents reports and never
imports from ``structure_engine`` beyond the frozen output contracts those
two artifacts already represent.

Week 2 (``structure_extractor``) already merges duplicate factor nodes and
keeps one edge per *claim*, so a run's ``extracted_structures.json`` is
already a claim-level structure. This module performs a second,
run-level merge: it consolidates edges that repeat across multiple claims
into one graph edge with unioned provenance, and it is independently
defensive about malformed input (self-loops, dangling references, invalid
edge types, non-finite/out-of-range weights) because it is a public, directly
testable entry point in its own right, not merely an internal helper.
"""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from typing import Any

import networkx as nx

from comqutor_alpha.graph_engine.graph_schema import (
    GRAPH_BUILDER_VERSION,
    GRAPH_COHERENCE_FORMULA_VERSION,
    GRAPH_SCHEMA_VERSION,
    MVP_ALPHA_IDS,
    VALID_ASSERTION_STATUSES,
    VALID_GRAPH_EDGE_TYPES,
    clamp_percent,
    is_finite_number,
)

# Merged-edge assertion status priority when instances disagree (set-based,
# so the result never depends on which claim was processed first).
_ASSERTION_MERGE_ORDER = ("asserted", "conditional", "mixed", "negated", "unknown")


def _dedupe_sorted(values) -> list[str]:
    return sorted({str(v) for v in values if str(v or "").strip()})


def _claim_provenance_index(alpha_matches_payload: Mapping[str, Any]) -> dict[str, dict[str, Any]]:
    """Build claim_id -> match info for every structured claim in this run.

    Every structured claim produces exactly one ``alpha_matches`` record
    (matched, ambiguous, or no_match), so this index also doubles as the
    claim_id -> agent lookup used to enrich graph nodes/edges without ever
    re-reading ``structured_agent_outputs.json``.
    """
    index: dict[str, dict[str, Any]] = {}
    matches = alpha_matches_payload.get("matches") if isinstance(alpha_matches_payload, Mapping) else None
    if not isinstance(matches, list):
        return index
    for record in matches:
        if not isinstance(record, Mapping):
            continue
        claim_id = record.get("claim_id")
        if not claim_id:
            continue
        index[str(claim_id)] = dict(record)
    return index


def _committed_alpha_ids_for_claim(claim_info: Mapping[str, Any] | None) -> list[str]:
    if not claim_info or claim_info.get("match_status") != "matched":
        return []
    alpha_id = claim_info.get("matched_alpha")
    return [str(alpha_id)] if alpha_id else []


def _ambiguous_alpha_ids_for_claim(claim_info: Mapping[str, Any] | None) -> list[str]:
    if not claim_info or claim_info.get("match_status") != "ambiguous":
        return []
    plausible = claim_info.get("plausible_alphas") or []
    return [str(a) for a in plausible if a]


def _normalize_input_nodes(raw_nodes: Sequence[Any]) -> dict[str, dict[str, Any]]:
    """Canonically merge input nodes by id, order-independently.

    Union rule: never last-write-wins. Every provenance list is the union
    (deduped, sorted) of every merged instance; score is the max observed.
    """
    merged: dict[str, dict[str, Any]] = {}
    for raw in raw_nodes:
        if not isinstance(raw, Mapping):
            continue
        node_id = str(raw.get("id") or "").strip()
        if not node_id:
            continue
        label = str(raw.get("label") or node_id)
        canonical_factor = str(raw.get("canonical_factor") or label)
        node_type = str(raw.get("node_type") or "factor")
        claim_ids = [str(v) for v in (raw.get("source_records") or []) if str(v or "").strip()]
        source_output_ids = [
            str(v) for v in (raw.get("source_agent_output_ids") or []) if str(v or "").strip()
        ]
        evidence = [str(v) for v in (raw.get("evidence") or []) if str(v or "").strip()]
        score = raw.get("score", 0.0)

        if node_id not in merged:
            merged[node_id] = {
                "id": node_id,
                "node_type": node_type if node_type in {"factor"} else "factor",
                "label": label,
                "canonical_factor": canonical_factor,
                "original_labels": {label},
                "claim_ids": set(claim_ids),
                "source_agent_output_ids": set(source_output_ids),
                "evidence": set(evidence),
                "score": clamp_percent(score, 0.0, 1.0),
            }
        else:
            existing = merged[node_id]
            existing["original_labels"].add(label)
            existing["claim_ids"].update(claim_ids)
            existing["source_agent_output_ids"].update(source_output_ids)
            existing["evidence"].update(evidence)
            existing["score"] = max(existing["score"], clamp_percent(score, 0.0, 1.0))
    return merged


def _validate_edge_type(edge_type: Any) -> str | None:
    value = str(edge_type or "").strip().lower()
    return value if value in VALID_GRAPH_EDGE_TYPES else None


def _validate_weight(weight: Any) -> float | None:
    if not is_finite_number(weight):
        return None
    value = float(weight)
    if not 0.0 <= value <= 1.0:
        return None
    return value


def _merge_assertion_status(statuses: set[str]) -> str:
    normalized = {s for s in statuses if s in VALID_ASSERTION_STATUSES} or {"unknown"}
    if len(normalized) == 1:
        return next(iter(normalized))
    if {"asserted", "negated"}.issubset(normalized):
        return "mixed"
    for candidate in _ASSERTION_MERGE_ORDER:
        if candidate in normalized:
            return candidate
    return "unknown"


def _normalize_and_merge_edges(
    raw_edges: Sequence[Any],
    known_node_ids: set[str],
) -> tuple[dict[tuple[str, str, str], dict[str, Any]], dict[str, int]]:
    """Validate, reject/omit malformed edges, and merge duplicates.

    Merge key is (source, target, edge_type) -- deliberately coarser than
    Week 2's per-claim edge key, so repeated claims stating the same relation
    collapse into one run-level graph edge with unioned provenance instead of
    staying duplicated. Returns (merged_edges, rejection_counts) so callers
    can audit why an edge was dropped without silently losing the signal.
    """
    merged: dict[tuple[str, str, str], dict[str, Any]] = {}
    rejections = {
        "self_loop": 0,
        "dangling_reference": 0,
        "invalid_edge_type": 0,
        "invalid_weight": 0,
        "malformed": 0,
    }

    for raw in raw_edges:
        if not isinstance(raw, Mapping):
            rejections["malformed"] += 1
            continue
        source = str(raw.get("source") or "").strip()
        target = str(raw.get("target") or "").strip()
        if not source or not target:
            rejections["malformed"] += 1
            continue
        if source == target:
            rejections["self_loop"] += 1
            continue
        if source not in known_node_ids or target not in known_node_ids:
            rejections["dangling_reference"] += 1
            continue
        edge_type = _validate_edge_type(raw.get("edge_type"))
        if edge_type is None:
            rejections["invalid_edge_type"] += 1
            continue
        weight = _validate_weight(raw.get("confidence", raw.get("weight")))
        if weight is None:
            rejections["invalid_weight"] += 1
            continue

        assertion_status = str(raw.get("assertion_status") or "unknown").strip().lower()
        if assertion_status not in VALID_ASSERTION_STATUSES:
            assertion_status = "unknown"
        claim_id = raw.get("source_record_id")
        source_output_id = raw.get("source_agent_output_id")
        evidence = str(raw.get("evidence") or "").strip()
        extraction_method = str(raw.get("extraction_method") or "unknown")
        rule_name = str(raw.get("rule_name") or "")

        key = (source, target, edge_type)
        if key not in merged:
            merged[key] = {
                "source": source,
                "target": target,
                "edge_type": edge_type,
                "weights": [weight],
                "assertion_statuses": {assertion_status},
                "claim_ids": {str(claim_id)} if claim_id else set(),
                "source_agent_output_ids": {str(source_output_id)} if source_output_id else set(),
                "evidence": {evidence} if evidence else set(),
                "extraction_methods": {extraction_method},
                "rule_names": {rule_name} if rule_name else set(),
            }
        else:
            existing = merged[key]
            existing["weights"].append(weight)
            existing["assertion_statuses"].add(assertion_status)
            if claim_id:
                existing["claim_ids"].add(str(claim_id))
            if source_output_id:
                existing["source_agent_output_ids"].add(str(source_output_id))
            if evidence:
                existing["evidence"].add(evidence)
            existing["extraction_methods"].add(extraction_method)
            if rule_name:
                existing["rule_names"].add(rule_name)

    return merged, rejections


def build_structure_graph(
    alpha_matches_payload: Mapping[str, Any],
    extracted_structures_payload: Mapping[str, Any],
) -> dict[str, Any]:
    """Build a deterministic, run-level Structure Graph.

    Pure function of its two Week 2 input payloads: the same semantic input
    (regardless of dict iteration order or input record order) always
    produces the same serialized graph, because every collection is merged
    into a set/dict keyed by canonical identity and then sorted before
    serialization.
    """
    run_id = None
    ticker = None
    if isinstance(extracted_structures_payload, Mapping):
        run_id = extracted_structures_payload.get("run_id")
        ticker = extracted_structures_payload.get("ticker")
    if not run_id and isinstance(alpha_matches_payload, Mapping):
        run_id = alpha_matches_payload.get("run_id")
    if not ticker and isinstance(alpha_matches_payload, Mapping):
        ticker = alpha_matches_payload.get("ticker")

    claim_index = _claim_provenance_index(alpha_matches_payload)

    raw_nodes = (
        extracted_structures_payload.get("nodes", [])
        if isinstance(extracted_structures_payload, Mapping)
        else []
    )
    raw_edges = (
        extracted_structures_payload.get("edges", [])
        if isinstance(extracted_structures_payload, Mapping)
        else []
    )
    if not isinstance(raw_nodes, list):
        raw_nodes = []
    if not isinstance(raw_edges, list):
        raw_edges = []

    nodes = _normalize_input_nodes(raw_nodes)
    known_node_ids = set(nodes)
    merged_edges, rejections = _normalize_and_merge_edges(raw_edges, known_node_ids)

    # Attach alpha_ids / agents / ambiguous_alpha_ids to nodes strictly via
    # each node's own claim_ids, so one claim's alpha can never leak onto a
    # node built from a different, unrelated claim.
    for node in nodes.values():
        committed: set[str] = set()
        ambiguous: set[str] = set()
        agents: set[str] = set()
        for claim_id in node["claim_ids"]:
            claim_info = claim_index.get(claim_id)
            committed.update(_committed_alpha_ids_for_claim(claim_info))
            ambiguous.update(_ambiguous_alpha_ids_for_claim(claim_info))
            if claim_info and claim_info.get("agent"):
                agents.add(str(claim_info["agent"]))
        node["alpha_ids"] = sorted(committed)
        node["ambiguous_alpha_ids"] = sorted(ambiguous - committed)
        node["agents"] = sorted(agents)

    graph = nx.DiGraph()
    for node_id, node in nodes.items():
        graph.add_node(node_id, **node)
    for (source, target, edge_type), edge in merged_edges.items():
        committed: set[str] = set()
        agents: set[str] = set()
        for claim_id in edge["claim_ids"]:
            claim_info = claim_index.get(claim_id)
            committed.update(_committed_alpha_ids_for_claim(claim_info))
            if claim_info and claim_info.get("agent"):
                agents.add(str(claim_info["agent"]))
        edge["alpha_ids"] = sorted(committed)
        edge["agents"] = sorted(agents)
        edge["weight"] = clamp_percent(max(edge["weights"]), 0.0, 1.0)
        graph.add_edge(source, target, edge_type=edge_type, weight=edge["weight"])

    serialized_nodes = [_serialize_node(node) for node in nodes.values()]
    serialized_nodes.sort(key=lambda item: item["id"])

    serialized_edges = [_serialize_edge(edge) for edge in merged_edges.values()]
    serialized_edges.sort(key=lambda item: (item["edge_type"], item["source"], item["target"]))

    graph_metrics = _compute_graph_metrics(graph, merged_edges, rejections, raw_nodes, raw_edges)
    alpha_covered_count, covered_alpha_ids = _graph_alpha_coverage(nodes.values())
    coherence = compute_graph_coherence_score(
        valid_edges=graph_metrics["valid_edges"],
        alpha_covered_count=alpha_covered_count,
    )

    return {
        "schema_version": GRAPH_SCHEMA_VERSION,
        "graph_builder_version": GRAPH_BUILDER_VERSION,
        "run_id": run_id,
        "ticker": ticker,
        "nodes": serialized_nodes,
        "edges": serialized_edges,
        "graph_metrics": graph_metrics,
        "graph_coherence": coherence,
        "covered_alpha_ids": sorted(covered_alpha_ids),
    }


def _serialize_node(node: dict[str, Any]) -> dict[str, Any]:
    return {
        "id": node["id"],
        "node_type": node["node_type"],
        "label": node["label"],
        "canonical_factor": node["canonical_factor"],
        "original_labels": sorted(node["original_labels"]),
        "alpha_ids": node["alpha_ids"],
        "ambiguous_alpha_ids": node["ambiguous_alpha_ids"],
        "score": clamp_percent(node["score"], 0.0, 1.0),
        "claim_ids": sorted(node["claim_ids"]),
        "source_agent_output_ids": sorted(node["source_agent_output_ids"]),
        "agents": node["agents"],
        "evidence": sorted(node["evidence"]),
    }


def _serialize_edge(edge: dict[str, Any]) -> dict[str, Any]:
    return {
        "source": edge["source"],
        "target": edge["target"],
        "edge_type": edge["edge_type"],
        "weight": edge["weight"],
        "assertion_status": _merge_assertion_status(edge["assertion_statuses"]),
        "alpha_ids": edge["alpha_ids"],
        "claim_ids": sorted(edge["claim_ids"]),
        "source_agent_output_ids": sorted(edge["source_agent_output_ids"]),
        "agents": edge["agents"],
        "evidence": sorted(edge["evidence"]),
        "extraction_methods": sorted(edge["extraction_methods"]),
        "rule_names": sorted(edge["rule_names"]),
    }


def _graph_alpha_coverage(nodes) -> tuple[int, set[str]]:
    covered: set[str] = set()
    for node in nodes:
        covered.update(a for a in node["alpha_ids"] if a in MVP_ALPHA_IDS)
    return len(covered), covered


def _compute_graph_metrics(
    graph: nx.DiGraph,
    merged_edges: Mapping[tuple[str, str, str], Any],
    rejections: Mapping[str, int],
    raw_nodes: Sequence[Any],
    raw_edges: Sequence[Any],
) -> dict[str, Any]:
    causal_subgraph = nx.DiGraph(
        (u, v) for u, v, data in graph.edges(data=True) if data.get("edge_type") == "causal"
    )
    causal_subgraph.add_nodes_from(graph.nodes)
    try:
        longest_causal_chain = nx.dag_longest_path_length(causal_subgraph)
    except nx.NetworkXUnfeasible:
        # A cycle should not occur (causal edges only run in increasing rank
        # order upstream) but this stays a safe diagnostic, not a crash.
        longest_causal_chain = 0

    duplicate_nodes_merged = max(0, len(raw_nodes) - graph.number_of_nodes())
    duplicate_edges_merged = max(0, len(raw_edges) - len(merged_edges))

    return {
        "node_count": graph.number_of_nodes(),
        "edge_count": graph.number_of_edges(),
        "valid_edges": graph.number_of_edges(),
        "connected_components": nx.number_weakly_connected_components(graph),
        "longest_causal_chain": longest_causal_chain,
        "duplicate_nodes_merged": duplicate_nodes_merged,
        "duplicate_edges_merged": duplicate_edges_merged,
        "rejected_edges": dict(rejections),
    }


def compute_graph_coherence_score(*, valid_edges: int, alpha_covered_count: int) -> dict[str, Any]:
    """Official Week 3 MVP graph coherence formula.

    ``graph_coherence_score = min(100, valid_edges * 15 + alpha_covered_count * 10)``

    - ``valid_edges``: validated, non-duplicate, admissible graph edges after
      graph construction (self-loops/dangling/invalid-type/invalid-weight
      edges already excluded; duplicates already merged). Includes negated
      and conditional edges -- they are still structurally valid, auditable
      graph information, they simply must not (and, by construction, do not)
      feed activation as asserted support.
    - ``alpha_covered_count``: count of unique MVP-10 alpha_ids attached to at
      least one graph node via committed (``match_status == "matched"``)
      evidence. Ambiguous/no_match evidence does not count as coverage.

    This is the only coherence formula used; no undocumented custom formula
    is substituted, per the Week 3 MVP contract.
    """
    valid_edges = max(0, int(valid_edges))
    alpha_covered_count = max(0, int(alpha_covered_count))
    edge_contribution = valid_edges * 15
    coverage_contribution = alpha_covered_count * 10
    unclamped_score = edge_contribution + coverage_contribution
    final_score = clamp_percent(unclamped_score)
    return {
        "formula_version": GRAPH_COHERENCE_FORMULA_VERSION,
        "valid_edges": valid_edges,
        "alpha_covered_count": alpha_covered_count,
        "edge_contribution": edge_contribution,
        "coverage_contribution": coverage_contribution,
        "unclamped_score": unclamped_score,
        "score": final_score,
    }
