"""J3-2/J3-3: QQQ macro Structure Graph sanity check.

No genuine QQQ TradingAgents report artifact exists in this repository, so
this uses a clearly-labeled SYNTHETIC macro fixture built from formal macro
claims (Rate Cut Cycle / Liquidity Expansion / Recession Risk language drawn
from the taxonomy's own trigger/confirmation signals). This is not, and must
not be represented as, a real market report.

Scope: macro Structure Graph and activation only. A001/A003 vs A501 conflict
arbitration is explicit Week 4 scope and is neither computed nor asserted
here.
"""

import json

from comqutor_alpha.api.routes_research import (
    get_persisted_structure_graph,
    run_research_request,
)
from comqutor_alpha.storage.db.engine import build_engine
from comqutor_alpha.storage.db.migrations import apply_migrations
from comqutor_alpha.storage.db.repository import GraphPersistenceRepository
from scripts.w5_demo_fixtures import approved_demo_outputs
from scripts.deterministic_echo_llm import build_deterministic_echo_gateway

# SYNTHETIC macro claims -- not a real market report for any ticker.
_SYNTHETIC_QQQ_OFFLINE_OUTPUTS = approved_demo_outputs("QQQ")


def _run_qqq_fixture(tmp_path):
    engine = build_engine("sqlite:///:memory:")
    apply_migrations(engine)
    repo = GraphPersistenceRepository(engine)
    payload = {
        "ticker": "QQQ",
        "analysis_date": "2026-06-30",
        "selected_analysts": ["market", "news", "fundamentals", "sentiment"],
        "offline_raw_agent_outputs": _SYNTHETIC_QQQ_OFFLINE_OUTPUTS,
    }
    gateway = build_deterministic_echo_gateway("week3-qqq-sanity", tmp_path)
    response = run_research_request(
        payload, output_root=tmp_path, graph_repository=repo, week2_llm_gateway=gateway
    )
    assert response["status"] == "completed"
    graph = get_persisted_structure_graph(response["run_id"], output_root=tmp_path, graph_repository=repo)
    assert graph["status"] == "ok"
    return response["run_id"], graph, repo


def _alpha(graph, alpha_id):
    return next(a for a in graph["activation"]["alphas"] if a["alpha_id"] == alpha_id)


def test_qqq_graph_is_valid_and_ticker_correct(tmp_path):
    _, graph, _ = _run_qqq_fixture(tmp_path)

    assert graph["ticker"] == "QQQ"
    assert graph["nodes"]
    json.dumps(graph)


def test_a001_a003_a501_all_receive_nonzero_evidence_based_activation(tmp_path):
    _, graph, _ = _run_qqq_fixture(tmp_path)

    for alpha_id in ("A001", "A003", "A501"):
        alpha = _alpha(graph, alpha_id)
        assert alpha["evidence_count"] > 0, f"{alpha_id} should have committed evidence in this fixture"
        assert alpha["activation_score"] > 0


def test_scores_are_differentiated_by_evidence_and_agent_agreement(tmp_path):
    _, graph, _ = _run_qqq_fixture(tmp_path)

    a001 = _alpha(graph, "A001")
    a003 = _alpha(graph, "A003")
    a501 = _alpha(graph, "A501")

    # A001/A003 each get 3-agent corroboration in this fixture; A501 gets 1.
    assert a001["distinct_supporting_agents"] > a501["distinct_supporting_agents"]
    assert a003["distinct_supporting_agents"] > a501["distinct_supporting_agents"]
    assert len({a001["activation_score"], a003["activation_score"], a501["activation_score"]}) >= 2


def test_direction_is_preserved_per_alpha_type(tmp_path):
    _, graph, _ = _run_qqq_fixture(tmp_path)

    # A001/A003 are opportunity alphas being activated -> bullish/positive.
    assert _alpha(graph, "A001")["direction"] == "positive"
    assert _alpha(graph, "A003")["direction"] == "positive"
    # A501 is a risk alpha being activated -> legitimately bearish/negative.
    assert _alpha(graph, "A501")["direction"] == "negative"


def test_graph_provenance_is_complete(tmp_path):
    run_id, graph, repo = _run_qqq_fixture(tmp_path)

    for alpha_id in ("A001", "A003", "A501"):
        alpha = _alpha(graph, alpha_id)
        assert alpha["claim_ids"]
        assert alpha["evidence"]

    persisted_claim_ids = {row["claim_id"] for row in repo.get_alpha_matches(run_id)}
    for alpha_id in ("A001", "A003", "A501"):
        assert set(_alpha(graph, alpha_id)["claim_ids"]).issubset(persisted_claim_ids)


def test_no_pairwise_conflict_score_or_main_conflict_is_emitted(tmp_path):
    _, graph, _ = _run_qqq_fixture(tmp_path)

    serialized = json.dumps(graph)
    assert "main_conflict" not in graph
    assert "conflict_score" not in serialized
    assert "conflict_level" not in serialized
    assert "/conflicts" not in serialized
