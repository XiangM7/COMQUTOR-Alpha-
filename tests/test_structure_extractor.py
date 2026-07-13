import json

from comqutor_alpha.structure_engine.structure_extractor import (
    extract_structures_from_records,
    normalize_factor_label,
    save_extracted_structures,
)


def _record(claim, factors=None, confidence=0.8, *, claim_id=None, raw_id=None, evidence=None):
    raw_id = raw_id or f"source:{abs(hash(claim))}"
    return {
        "run_id": "run1",
        "ticker": "NVDA",
        "agent": "news_agent",
        "claim": claim,
        "evidence": evidence or claim,
        "entities": ["NVDA"],
        "factors": factors or [],
        "direction": "positive",
        "confidence": confidence,
        "claim_id": claim_id or f"{raw_id}:claim:1",
        "agent_output_id": claim_id or f"{raw_id}:claim:1",
        "source_agent_output_id": raw_id,
    }


def _has_edge(payload, source_label, target_label, edge_type):
    return any(
        edge["source_label"] == source_label
        and edge["target_label"] == target_label
        and edge["edge_type"] == edge_type
        for edge in payload["edges"]
    )


def test_extracts_ai_demand_to_gpu_demand_edge():
    payload = extract_structures_from_records(
        [_record("AI demand drives GPU demand as model training expands.")]
    )

    assert _has_edge(payload, "AI Demand", "GPU Demand", "causal")


def test_extracts_ai_capex_to_gpu_demand_edge():
    payload = extract_structures_from_records(
        [_record("Hyperscaler AI capex raises GPU demand for accelerator clusters.")]
    )

    assert _has_edge(payload, "AI CapEx", "GPU Demand", "causal")


def test_extracts_gpu_demand_to_nvda_revenue_growth_edge():
    payload = extract_structures_from_records(
        [_record("GPU demand drives revenue growth at NVDA as customer orders rise.")]
    )

    assert _has_edge(payload, "GPU Demand", "NVDA Revenue Growth", "causal")


def test_extracts_supportive_edge():
    payload = extract_structures_from_records(
        [_record("Liquidity expansion supports narrative momentum in AI stocks.")]
    )

    assert _has_edge(payload, "Liquidity Expansion", "Narrative Momentum", "supportive")


def test_extracts_conflicting_edge():
    payload = extract_structures_from_records(
        [_record("AI demand is strong, but rich valuation creates downside risk.")]
    )

    assert _has_edge(payload, "Valuation Risk", "AI Demand", "conflicting")


def test_duplicate_factor_normalization_merges_nodes():
    payload = extract_structures_from_records(
        [
            _record("AI demand is improving.", factors=["AI demand"]),
            _record(
                "Artificial intelligence demand is improving.",
                factors=["artificial intelligence demand"],
            ),
        ]
    )
    labels = [node["label"] for node in payload["nodes"]]

    assert normalize_factor_label("artificial intelligence demand") == "AI Demand"
    assert labels.count("AI Demand") == 1


def test_ambiguous_text_does_not_hallucinate_causal_edge():
    payload = extract_structures_from_records(
        [_record("AI demand and GPU demand are both mentioned without a clear relationship.")]
    )

    assert payload["nodes"]
    assert payload["edges"] == []


def test_reversed_causal_phrasing_does_not_emit_wrong_direction_edge():
    """"GPU demand drives AI demand" mentions both factors plus causal
    language ("drives"), but in the reversed order from the canonical
    AI Demand -> GPU Demand rule. The extractor must not emit that edge
    (in either direction) rather than hallucinate the canonical direction.
    """
    payload = extract_structures_from_records(
        [_record("GPU demand drives AI demand as model usage rises.")]
    )

    assert not _has_edge(payload, "AI Demand", "GPU Demand", "causal")
    assert not _has_edge(payload, "GPU Demand", "AI Demand", "causal")
    labels = {node["label"] for node in payload["nodes"]}
    assert labels == {"AI Demand", "GPU Demand"}


def test_extracts_passive_causal_relation_in_canonical_direction():
    payload = extract_structures_from_records(
        [_record("GPU demand is driven by AI capex.")]
    )

    edge = next(edge for edge in payload["edges"] if edge["edge_type"] == "causal")
    assert edge["source_label"] == "AI CapEx"
    assert edge["target_label"] == "GPU Demand"
    assert edge["assertion_status"] == "asserted"


def test_conditional_causal_relation_is_not_asserted():
    payload = extract_structures_from_records(
        [_record("If AI capex rises, GPU demand could increase.")]
    )

    edge = next(edge for edge in payload["edges"] if edge["edge_type"] == "causal")
    assert edge["assertion_status"] == "conditional"
    assert edge["confidence"] < 0.84


def test_negated_causal_relation_is_marked_negated():
    payload = extract_structures_from_records(
        [_record("AI capex does not drive GPU demand.")]
    )

    edge = next(edge for edge in payload["edges"] if edge["edge_type"] == "causal")
    assert edge["assertion_status"] == "negated"
    assert edge["confidence"] < 0.5


def test_no_evidence_causal_phrase_is_not_asserted():
    payload = extract_structures_from_records(
        [_record("There is no evidence that AI demand drives GPU demand.")]
    )

    assert all(edge["assertion_status"] != "asserted" for edge in payload["edges"])


def test_vague_coexistence_does_not_hallucinate_causal_edge():
    payload = extract_structures_from_records(
        [_record("Both AI capex and GPU demand were mentioned in the same earnings call.")]
    )

    assert payload["nodes"]
    assert payload["edges"] == []


def test_same_raw_output_keeps_edges_from_distinct_claims():
    raw_id = "run1:news_agent:news_report"
    payload = extract_structures_from_records(
        [
            _record(
                "AI demand drives GPU demand in training workloads.",
                claim_id=f"{raw_id}:claim:1",
                raw_id=raw_id,
            ),
            _record(
                "AI demand drives GPU demand across cloud workloads.",
                claim_id=f"{raw_id}:claim:2",
                raw_id=raw_id,
            ),
        ]
    )

    edges = [edge for edge in payload["edges"] if edge["edge_type"] == "causal"]
    assert len(edges) == 2
    assert {edge["source_record_id"] for edge in edges} == {
        f"{raw_id}:claim:1",
        f"{raw_id}:claim:2",
    }
    assert all(edge["source_agent_output_id"] == raw_id for edge in edges)
    assert all(edge["evidence"] for edge in edges)


def test_legacy_v1_identity_remains_traceable():
    record = _record("AI demand drives GPU demand.")
    record.pop("claim_id")
    record.pop("source_agent_output_id")
    record["agent_output_id"] = "legacy_raw_output_id"

    payload = extract_structures_from_records([record])

    assert payload["edges"][0]["source_record_id"] == "legacy_raw_output_id"
    assert payload["edges"][0]["source_agent_output_id"] == "legacy_raw_output_id"


def test_save_extracted_structures_writes_week2_artifact(tmp_path):
    run_dir = tmp_path / "run1"
    run_dir.mkdir()
    (run_dir / "structured_agent_outputs.json").write_text(
        json.dumps(
            {
                "schema_version": "week1a.structured_agent_outputs.v1",
                "run_id": "run1",
                "ticker": "NVDA",
                "records": [_record("GPU demand drives revenue growth at NVDA.")],
            }
        ),
        encoding="utf-8",
    )

    payload = save_extracted_structures("run1", output_root=tmp_path)

    assert payload["schema_version"] == "week2.extracted_structures.v2"
    assert _has_edge(payload, "GPU Demand", "NVDA Revenue Growth", "causal")
    assert (run_dir / "extracted_structures.json").exists()
