from comqutor_alpha.structure_engine.structure_schema import (
    AlphaCandidateScore,
    AlphaMatchRecord,
    StructureEdge,
    StructureNode,
    StructuredAgentOutput,
)


def test_alpha_candidate_score_to_dict_clamps_out_of_range_scores():
    candidate = AlphaCandidateScore(
        alpha_id="A101",
        alpha_name="AI Expansion",
        score=1.5,
        keyword_score=-0.2,
        factor_score=0.42,
        direction_score=2.0,
    )

    data = candidate.to_dict()

    assert data["score"] == 1.0
    assert data["keyword_score"] == 0.0
    assert data["factor_score"] == 0.42
    assert data["direction_score"] == 1.0


def test_alpha_match_record_to_dict_forces_no_matched_alpha_unless_matched():
    record = AlphaMatchRecord(
        run_id="run1",
        ticker="NVDA",
        agent="news_agent",
        source_agent_output_id="src1",
        claim="AI demand is strong.",
        direction="bullish",
        matched_alpha="A101",
        matched_alpha_name="AI Expansion",
        score=0.9,
        keyword_score=0.9,
        factor_score=0.5,
        direction_score=1.0,
        candidate_scores=[],
        match_status="ambiguous",
        reason="top alpha candidates are too close to force a single match",
    )

    data = record.to_dict()

    assert data["match_status"] == "ambiguous"
    assert data["matched_alpha"] is None
    assert data["matched_alpha_name"] is None
    assert data["direction"] == "positive"


def test_alpha_match_record_to_dict_normalizes_direction():
    record = AlphaMatchRecord(
        run_id="run1",
        ticker="NVDA",
        agent="news_agent",
        source_agent_output_id="src1",
        claim="AI demand is strong.",
        direction="bullish",
        matched_alpha="A101",
        matched_alpha_name="AI Expansion",
        score=0.9,
        keyword_score=0.9,
        factor_score=0.5,
        direction_score=1.0,
        candidate_scores=[],
        match_status="matched",
        reason="top alpha score passed threshold and separation checks",
    )

    assert record.to_dict()["direction"] == "positive"


def test_alpha_match_record_to_dict_clears_matched_alpha_when_no_match():
    record = AlphaMatchRecord(
        run_id="run1",
        ticker="NVDA",
        agent="news_agent",
        source_agent_output_id="src1",
        claim="The company signed an ordinary office lease.",
        direction="unknown",
        matched_alpha="A101",
        matched_alpha_name="AI Expansion",
        score=0.1,
        keyword_score=0.1,
        factor_score=0.0,
        direction_score=0.0,
        candidate_scores=[],
        match_status="no_match",
        reason="top score below minimum match threshold",
    )

    data = record.to_dict()

    assert data["match_status"] == "no_match"
    assert data["matched_alpha"] is None
    assert data["matched_alpha_name"] is None


def test_alpha_match_record_to_dict_clears_matched_alpha_when_ambiguous():
    record = AlphaMatchRecord(
        run_id="run1",
        ticker="NVDA",
        agent="news_agent",
        source_agent_output_id="src1",
        claim="AI demand is strong, but rich valuation creates downside risk.",
        direction="neutral",
        matched_alpha="A101",
        matched_alpha_name="AI Expansion",
        score=0.5,
        keyword_score=0.5,
        factor_score=0.5,
        direction_score=0.35,
        candidate_scores=[],
        match_status="ambiguous",
        reason="top alpha candidates are too close to force a single match",
    )

    data = record.to_dict()

    assert data["match_status"] == "ambiguous"
    assert data["matched_alpha"] is None
    assert data["matched_alpha_name"] is None


def test_alpha_match_record_to_dict_normalizes_candidate_scores_and_limits_to_five():
    candidates = [
        {
            "alpha_id": f"A{i}",
            "alpha_name": f"Alpha {i}",
            "score": 1.5,
            "keyword_score": 0.5,
            "factor_score": 0.5,
            "direction_score": 0.5,
        }
        for i in range(7)
    ]
    record = AlphaMatchRecord(
        run_id="run1",
        ticker="NVDA",
        agent="news_agent",
        source_agent_output_id="src1",
        claim="AI demand is strong.",
        direction="positive",
        matched_alpha="A0",
        matched_alpha_name="Alpha 0",
        score=1.5,
        keyword_score=0.9,
        factor_score=0.5,
        direction_score=1.0,
        candidate_scores=candidates,
        match_status="matched",
        reason="top alpha score passed threshold and separation checks",
    )

    data = record.to_dict()

    assert data["score"] == 1.0
    assert len(data["candidate_scores"]) == 5
    assert all(item["score"] == 1.0 for item in data["candidate_scores"])


def test_alpha_match_record_to_dict_rejects_invalid_match_status():
    record = AlphaMatchRecord(
        run_id="run1",
        ticker="NVDA",
        agent="news_agent",
        source_agent_output_id="src1",
        claim="claim",
        direction="unknown",
        matched_alpha="A101",
        matched_alpha_name="AI Expansion",
        score=0.5,
        keyword_score=0.5,
        factor_score=0.0,
        direction_score=0.0,
        match_status="not_a_real_status",
        reason="",
    )

    data = record.to_dict()

    assert data["match_status"] == "no_match"
    assert data["matched_alpha"] is None


def test_structure_node_to_dict_clamps_score_and_dedupes():
    node = StructureNode(
        id="ai_demand",
        label="AI Demand",
        canonical_factor="AI Demand",
        source_records=["src1", "src1", "src2"],
        evidence=["claim a", "claim a"],
        score=1.7,
    )

    data = node.to_dict()

    assert data["score"] == 1.0
    assert data["source_records"] == ["src1", "src2"]
    assert data["evidence"] == ["claim a"]


def test_structure_edge_to_dict_clamps_confidence():
    edge = StructureEdge(
        source="ai_demand",
        target="gpu_demand",
        source_label="AI Demand",
        target_label="GPU Demand",
        edge_type="causal",
        confidence=3.0,
    )

    data = edge.to_dict()

    assert data["confidence"] == 1.0
    assert data["edge_type"] == "causal"


def test_structured_agent_output_to_dict_normalizes_direction_and_confidence():
    output = StructuredAgentOutput(
        run_id="run1",
        ticker="NVDA",
        agent="news_agent",
        timestamp="2026-07-01T00:00:00Z",
        claim="AI demand is strong.",
        evidence="AI demand is strong.",
        direction="bullish",
        confidence=5.0,
    )

    data = output.to_dict()

    assert data["direction"] == "positive"
    assert data["confidence"] == 1.0
