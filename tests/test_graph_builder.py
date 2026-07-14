import math

from comqutor_alpha.graph_engine.graph_builder import (
    build_structure_graph,
    compute_graph_coherence_score,
)


def _match(claim_id, agent, matched_alpha, *, status="matched", plausible=None, score=0.8):
    return {
        "claim_id": claim_id,
        "agent": agent,
        "match_status": status,
        "matched_alpha": matched_alpha if status == "matched" else None,
        "plausible_alphas": plausible or ([matched_alpha] if matched_alpha else []),
        "score": score,
    }


def _alpha_matches(matches):
    return {"run_id": "r1", "ticker": "NVDA", "matches": matches}


def _node(node_id, label, claim_ids, *, score=0.8, evidence=None, source_output_ids=None, canonical_factor=None):
    return {
        "id": node_id,
        "label": label,
        "canonical_factor": canonical_factor or label,
        "node_type": "factor",
        "source_records": list(claim_ids),
        "source_agent_output_ids": list(source_output_ids or []),
        "evidence": evidence or [f"{label} evidence"],
        "score": score,
    }


def _edge(source, target, edge_type, claim_id, *, confidence=0.8, assertion_status="asserted", evidence="evidence text"):
    return {
        "source": source,
        "target": target,
        "edge_type": edge_type,
        "confidence": confidence,
        "assertion_status": assertion_status,
        "source_record_id": claim_id,
        "source_agent_output_id": f"o_{claim_id}",
        "evidence": evidence,
        "extraction_method": "deterministic_rules",
        "rule_name": "active_causal_between_factors",
    }


def _extracted(nodes, edges):
    return {"run_id": "r1", "ticker": "NVDA", "nodes": nodes, "edges": edges}


def test_builds_valid_digraph_with_nodes_and_edges():
    alpha_matches = _alpha_matches([_match("c1", "news_agent", "A101")])
    extracted = _extracted(
        [_node("ai_demand", "AI Demand", ["c1"]), _node("gpu_demand", "GPU Demand", ["c1"])],
        [_edge("ai_demand", "gpu_demand", "causal", "c1")],
    )

    graph = build_structure_graph(alpha_matches, extracted)

    assert graph["run_id"] == "r1"
    assert graph["ticker"] == "NVDA"
    assert {n["id"] for n in graph["nodes"]} == {"ai_demand", "gpu_demand"}
    assert len(graph["edges"]) == 1
    assert graph["edges"][0]["source"] == "ai_demand"
    assert graph["edges"][0]["target"] == "gpu_demand"


def test_serialization_is_deterministic_across_repeated_calls():
    alpha_matches = _alpha_matches([_match("c1", "news_agent", "A101"), _match("c2", "fundamental_agent", "A301")])
    extracted = _extracted(
        [_node("ai_demand", "AI Demand", ["c1"]), _node("nvda_revenue_growth", "NVDA Revenue Growth", ["c2"])],
        [_edge("ai_demand", "nvda_revenue_growth", "causal", "c1")],
    )

    first = build_structure_graph(alpha_matches, extracted)
    second = build_structure_graph(alpha_matches, extracted)

    assert first == second


def test_input_record_order_does_not_affect_serialized_graph():
    alpha_matches = _alpha_matches([_match("c1", "news_agent", "A101"), _match("c2", "fundamental_agent", "A301")])
    nodes = [_node("ai_demand", "AI Demand", ["c1"]), _node("nvda_revenue_growth", "NVDA Revenue Growth", ["c2"])]
    edges = [_edge("ai_demand", "nvda_revenue_growth", "causal", "c1")]

    forward = build_structure_graph(alpha_matches, _extracted(nodes, edges))
    reversed_graph = build_structure_graph(
        {**alpha_matches, "matches": list(reversed(alpha_matches["matches"]))},
        _extracted(list(reversed(nodes)), list(reversed(edges))),
    )

    assert forward == reversed_graph


def test_canonical_duplicate_node_merge_unions_provenance_without_last_write_wins():
    alpha_matches = _alpha_matches([_match("c1", "news_agent", "A101"), _match("c2", "fundamental_agent", "A101")])
    extracted = _extracted(
        [
            _node("ai_demand", "AI Demand", ["c1"], score=0.6, evidence=["first evidence"], source_output_ids=["o1"]),
            _node("ai_demand", "AI Demand", ["c2"], score=0.9, evidence=["second evidence"], source_output_ids=["o2"]),
        ],
        [],
    )

    graph = build_structure_graph(alpha_matches, extracted)

    assert len(graph["nodes"]) == 1
    node = graph["nodes"][0]
    assert node["score"] == 0.9  # max, not last-write
    assert node["claim_ids"] == ["c1", "c2"]
    assert node["source_agent_output_ids"] == ["o1", "o2"]
    assert node["evidence"] == ["first evidence", "second evidence"]
    assert node["agents"] == ["fundamental_agent", "news_agent"]
    assert node["alpha_ids"] == ["A101"]
    assert graph["graph_metrics"]["duplicate_nodes_merged"] == 1


def test_duplicate_node_merge_is_order_independent():
    alpha_matches = _alpha_matches([_match("c1", "news_agent", "A101"), _match("c2", "fundamental_agent", "A101")])
    nodes_a = [
        _node("ai_demand", "AI Demand", ["c1"], score=0.6, evidence=["e1"]),
        _node("ai_demand", "AI Demand", ["c2"], score=0.9, evidence=["e2"]),
    ]
    nodes_b = list(reversed(nodes_a))

    graph_a = build_structure_graph(alpha_matches, _extracted(nodes_a, []))
    graph_b = build_structure_graph(alpha_matches, _extracted(nodes_b, []))

    assert graph_a == graph_b


def test_distinct_concepts_with_similar_but_different_ids_are_not_merged():
    alpha_matches = _alpha_matches([_match("c1", "news_agent", "A101"), _match("c2", "fundamental_agent", "A301")])
    extracted = _extracted(
        [
            _node("ai_demand", "AI Demand", ["c1"]),
            _node("nvda_revenue_growth", "NVDA Revenue Growth", ["c2"]),
        ],
        [],
    )

    graph = build_structure_graph(alpha_matches, extracted)

    assert {n["id"] for n in graph["nodes"]} == {"ai_demand", "nvda_revenue_growth"}


def test_duplicate_edge_merge_unions_provenance():
    alpha_matches = _alpha_matches([_match("c1", "news_agent", "A101"), _match("c3", "sentiment_agent", "A101")])
    extracted = _extracted(
        [_node("ai_demand", "AI Demand", ["c1", "c3"]), _node("gpu_demand", "GPU Demand", ["c1", "c3"])],
        [
            _edge("ai_demand", "gpu_demand", "causal", "c1", confidence=0.7, evidence="first claim evidence"),
            _edge("ai_demand", "gpu_demand", "causal", "c3", confidence=0.9, evidence="second claim evidence"),
        ],
    )

    graph = build_structure_graph(alpha_matches, extracted)

    assert len(graph["edges"]) == 1
    edge = graph["edges"][0]
    assert edge["weight"] == 0.9  # max of merged confidences
    assert edge["claim_ids"] == ["c1", "c3"]
    assert edge["source_agent_output_ids"] == ["o_c1", "o_c3"]
    assert set(edge["evidence"]) == {"first claim evidence", "second claim evidence"}
    assert edge["agents"] == ["news_agent", "sentiment_agent"]
    assert graph["graph_metrics"]["duplicate_edges_merged"] == 1


def test_merged_edge_assertion_status_becomes_mixed_on_genuine_contradiction():
    alpha_matches = _alpha_matches([_match("c1", "news_agent", "A101"), _match("c2", "news_agent", "A101")])
    extracted = _extracted(
        [_node("ai_demand", "AI Demand", ["c1", "c2"]), _node("gpu_demand", "GPU Demand", ["c1", "c2"])],
        [
            _edge("ai_demand", "gpu_demand", "causal", "c1", assertion_status="asserted"),
            _edge("ai_demand", "gpu_demand", "causal", "c2", assertion_status="negated"),
        ],
    )

    graph = build_structure_graph(alpha_matches, extracted)

    assert graph["edges"][0]["assertion_status"] == "mixed"


def test_conditional_edge_is_retained_and_counted_as_valid():
    alpha_matches = _alpha_matches([_match("c1", "news_agent", "A101")])
    extracted = _extracted(
        [_node("ai_demand", "AI Demand", ["c1"]), _node("gpu_demand", "GPU Demand", ["c1"])],
        [_edge("ai_demand", "gpu_demand", "causal", "c1", assertion_status="conditional", confidence=0.58)],
    )

    graph = build_structure_graph(alpha_matches, extracted)

    assert graph["edges"][0]["assertion_status"] == "conditional"
    assert graph["graph_metrics"]["valid_edges"] == 1


def test_negated_edge_is_retained_but_still_just_auditable_structure():
    alpha_matches = _alpha_matches([_match("c1", "news_agent", "A101")])
    extracted = _extracted(
        [_node("ai_demand", "AI Demand", ["c1"]), _node("gpu_demand", "GPU Demand", ["c1"])],
        [_edge("ai_demand", "gpu_demand", "causal", "c1", assertion_status="negated", confidence=0.35)],
    )

    graph = build_structure_graph(alpha_matches, extracted)

    assert graph["edges"][0]["assertion_status"] == "negated"
    # Still a structurally valid, admissible edge (auditable), per spec.
    assert graph["graph_metrics"]["valid_edges"] == 1


def test_self_loop_is_rejected():
    alpha_matches = _alpha_matches([_match("c1", "news_agent", "A101")])
    extracted = _extracted(
        [_node("ai_demand", "AI Demand", ["c1"])],
        [_edge("ai_demand", "ai_demand", "causal", "c1")],
    )

    graph = build_structure_graph(alpha_matches, extracted)

    assert graph["edges"] == []
    assert graph["graph_metrics"]["rejected_edges"]["self_loop"] == 1


def test_dangling_edge_is_rejected():
    alpha_matches = _alpha_matches([_match("c1", "news_agent", "A101")])
    extracted = _extracted(
        [_node("ai_demand", "AI Demand", ["c1"])],
        [_edge("ai_demand", "unknown_node", "causal", "c1")],
    )

    graph = build_structure_graph(alpha_matches, extracted)

    assert graph["edges"] == []
    assert graph["graph_metrics"]["rejected_edges"]["dangling_reference"] == 1


def test_invalid_edge_type_is_rejected():
    alpha_matches = _alpha_matches([_match("c1", "news_agent", "A101")])
    extracted = _extracted(
        [_node("ai_demand", "AI Demand", ["c1"]), _node("gpu_demand", "GPU Demand", ["c1"])],
        [_edge("ai_demand", "gpu_demand", "not_a_real_type", "c1")],
    )

    graph = build_structure_graph(alpha_matches, extracted)

    assert graph["edges"] == []
    assert graph["graph_metrics"]["rejected_edges"]["invalid_edge_type"] == 1


def test_non_finite_weight_is_rejected():
    alpha_matches = _alpha_matches([_match("c1", "news_agent", "A101")])
    for bad_weight in (float("nan"), float("inf"), float("-inf")):
        extracted = _extracted(
            [_node("ai_demand", "AI Demand", ["c1"]), _node("gpu_demand", "GPU Demand", ["c1"])],
            [_edge("ai_demand", "gpu_demand", "causal", "c1", confidence=bad_weight)],
        )
        graph = build_structure_graph(alpha_matches, extracted)
        assert graph["edges"] == []
        assert graph["graph_metrics"]["rejected_edges"]["invalid_weight"] == 1


def test_out_of_range_weight_is_rejected():
    alpha_matches = _alpha_matches([_match("c1", "news_agent", "A101")])
    for bad_weight in (1.5, -0.2):
        extracted = _extracted(
            [_node("ai_demand", "AI Demand", ["c1"]), _node("gpu_demand", "GPU Demand", ["c1"])],
            [_edge("ai_demand", "gpu_demand", "causal", "c1", confidence=bad_weight)],
        )
        graph = build_structure_graph(alpha_matches, extracted)
        assert graph["edges"] == []
        assert graph["graph_metrics"]["rejected_edges"]["invalid_weight"] == 1


def test_committed_alpha_label_is_assigned_from_matched_claim():
    alpha_matches = _alpha_matches([_match("c1", "news_agent", "A101")])
    extracted = _extracted([_node("ai_demand", "AI Demand", ["c1"])], [])

    graph = build_structure_graph(alpha_matches, extracted)

    assert graph["nodes"][0]["alpha_ids"] == ["A101"]


def test_no_match_evidence_does_not_label_the_node():
    alpha_matches = _alpha_matches([_match("c1", "news_agent", None, status="no_match")])
    extracted = _extracted([_node("ai_demand", "AI Demand", ["c1"])], [])

    graph = build_structure_graph(alpha_matches, extracted)

    assert graph["nodes"][0]["alpha_ids"] == []
    assert graph["nodes"][0]["ambiguous_alpha_ids"] == []


def test_ambiguous_evidence_is_tracked_separately_not_as_committed_coverage():
    alpha_matches = _alpha_matches(
        [_match("c1", "news_agent", None, status="ambiguous", plausible=["A101", "A301"])]
    )
    extracted = _extracted([_node("ai_demand", "AI Demand", ["c1"])], [])

    graph = build_structure_graph(alpha_matches, extracted)

    assert graph["nodes"][0]["alpha_ids"] == []
    assert graph["nodes"][0]["ambiguous_alpha_ids"] == ["A101", "A301"]
    assert graph["graph_coherence"]["alpha_covered_count"] == 0


def test_unrelated_claims_alpha_does_not_leak_onto_a_different_nodes_claim():
    alpha_matches = _alpha_matches([_match("c1", "news_agent", "A101"), _match("c2", "fundamental_agent", "A301")])
    extracted = _extracted(
        [_node("ai_demand", "AI Demand", ["c1"]), _node("nvda_revenue_growth", "NVDA Revenue Growth", ["c2"])],
        [],
    )

    graph = build_structure_graph(alpha_matches, extracted)

    by_id = {n["id"]: n for n in graph["nodes"]}
    assert by_id["ai_demand"]["alpha_ids"] == ["A101"]
    assert by_id["nvda_revenue_growth"]["alpha_ids"] == ["A301"]


def test_malformed_edge_input_is_safely_omitted_not_raised():
    alpha_matches = _alpha_matches([_match("c1", "news_agent", "A101")])
    extracted = _extracted(
        [_node("ai_demand", "AI Demand", ["c1"])],
        ["not-a-dict", {"source": "ai_demand"}, None, 42],
    )

    graph = build_structure_graph(alpha_matches, extracted)

    assert graph["edges"] == []
    assert graph["graph_metrics"]["rejected_edges"]["malformed"] >= 1


def test_no_local_object_references_leak_into_serialized_json():
    import json

    alpha_matches = _alpha_matches([_match("c1", "news_agent", "A101")])
    extracted = _extracted(
        [_node("ai_demand", "AI Demand", ["c1"]), _node("gpu_demand", "GPU Demand", ["c1"])],
        [_edge("ai_demand", "gpu_demand", "causal", "c1")],
    )

    graph = build_structure_graph(alpha_matches, extracted)

    # Must be plain-JSON-serializable with no custom objects (sets, etc.).
    json.dumps(graph)


class TestGraphCoherenceScore:
    def test_zero_edge_graph_scores_only_from_coverage(self):
        result = compute_graph_coherence_score(valid_edges=0, alpha_covered_count=0)
        assert result["score"] == 0.0
        assert result["formula_version"]

    def test_formula_breakdown_matches_official_mvp_formula(self):
        result = compute_graph_coherence_score(valid_edges=3, alpha_covered_count=2)
        assert result["edge_contribution"] == 45
        assert result["coverage_contribution"] == 20
        assert result["unclamped_score"] == 65
        assert result["score"] == 65.0

    def test_score_clamps_at_100(self):
        result = compute_graph_coherence_score(valid_edges=20, alpha_covered_count=10)
        assert result["unclamped_score"] > 100
        assert result["score"] == 100.0

    def test_result_is_deterministic(self):
        first = compute_graph_coherence_score(valid_edges=4, alpha_covered_count=3)
        second = compute_graph_coherence_score(valid_edges=4, alpha_covered_count=3)
        assert first == second

    def test_duplicate_edges_are_counted_once_via_graph_builder(self):
        alpha_matches = _alpha_matches([_match("c1", "news_agent", "A101"), _match("c2", "news_agent", "A101")])
        extracted = _extracted(
            [_node("ai_demand", "AI Demand", ["c1", "c2"]), _node("gpu_demand", "GPU Demand", ["c1", "c2"])],
            [
                _edge("ai_demand", "gpu_demand", "causal", "c1"),
                _edge("ai_demand", "gpu_demand", "causal", "c2"),
            ],
        )

        graph = build_structure_graph(alpha_matches, extracted)

        assert graph["graph_coherence"]["valid_edges"] == 1

    def test_alpha_covered_count_reflects_committed_evidence_only(self):
        alpha_matches = _alpha_matches(
            [
                _match("c1", "news_agent", "A101"),
                _match("c2", "news_agent", None, status="ambiguous", plausible=["A301"]),
                _match("c3", "news_agent", None, status="no_match"),
            ]
        )
        extracted = _extracted(
            [
                _node("ai_demand", "AI Demand", ["c1"]),
                _node("nvda_revenue_growth", "NVDA Revenue Growth", ["c2"]),
                _node("valuation_risk", "Valuation Risk", ["c3"]),
            ],
            [],
        )

        graph = build_structure_graph(alpha_matches, extracted)

        assert graph["graph_coherence"]["alpha_covered_count"] == 1
        assert not math.isnan(graph["graph_coherence"]["score"])
