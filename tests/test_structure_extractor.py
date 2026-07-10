import json

from comqutor_alpha.structure_engine.structure_extractor import (
    extract_structures_from_records,
    normalize_factor_label,
    save_extracted_structures,
)


def _record(claim, factors=None, confidence=0.8):
    return {
        "run_id": "run1",
        "ticker": "NVDA",
        "agent": "news_agent",
        "claim": claim,
        "evidence": claim,
        "entities": ["NVDA"],
        "factors": factors or [],
        "direction": "positive",
        "confidence": confidence,
        "source_agent_output_id": f"source:{abs(hash(claim))}",
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


def test_vague_coexistence_does_not_hallucinate_causal_edge():
    payload = extract_structures_from_records(
        [_record("Both AI capex and GPU demand were mentioned in the same earnings call.")]
    )

    assert payload["nodes"]
    assert payload["edges"] == []


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

    assert payload["schema_version"] == "week2.extracted_structures.v1"
    assert _has_edge(payload, "GPU Demand", "NVDA Revenue Growth", "causal")
    assert (run_dir / "extracted_structures.json").exists()
