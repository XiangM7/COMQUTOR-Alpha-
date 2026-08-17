"""J3-1: NVDA Structure Graph sanity check against investment logic.

Runs the real Week 1-3 pipeline end to end (offline, deterministic) over a
hand-authored -- not copied from either protected golden-label file --
multi-agent NVDA fixture, then asserts on the *shape and differentiation* of
the result rather than brittle exact scores. This is a robustness/coherence
sanity check, not a market-prediction accuracy claim.
"""

import json
import re

from comqutor_alpha.api.routes_research import (
    get_persisted_structure_graph,
    run_research_request,
)
from comqutor_alpha.storage.db.engine import build_engine
from comqutor_alpha.storage.db.migrations import apply_migrations
from comqutor_alpha.storage.db.repository import GraphPersistenceRepository
from scripts.w5_demo_fixtures import approved_demo_outputs

RELEVANT_NVDA_ALPHA_IDS = {"A101", "A103", "A201", "A301", "A304", "A601"}


def _nvda_offline_outputs():
    return approved_demo_outputs("NVDA")


def _run_nvda_fixture(tmp_path):
    engine = build_engine("sqlite:///:memory:")
    apply_migrations(engine)
    repo = GraphPersistenceRepository(engine)
    payload = {
        "ticker": "NVDA",
        "analysis_date": "2026-06-30",
        "selected_analysts": ["market", "news", "fundamentals", "sentiment"],
        "offline_raw_agent_outputs": _nvda_offline_outputs(),
    }
    response = run_research_request(payload, output_root=tmp_path, graph_repository=repo)
    assert response["status"] == "completed"
    graph = get_persisted_structure_graph(response["run_id"], output_root=tmp_path, graph_repository=repo)
    assert graph["status"] == "ok"
    return response["run_id"], graph, repo


def test_nvda_produces_a_valid_structure_graph_json(tmp_path):
    _, graph, _ = _run_nvda_fixture(tmp_path)

    assert graph["ticker"] == "NVDA"
    assert graph["nodes"]
    assert graph["edges"]
    json.dumps(graph)  # must be plain-JSON serializable


def test_relevant_nvda_alpha_ids_are_represented_when_evidence_exists(tmp_path):
    _, graph, _ = _run_nvda_fixture(tmp_path)

    alphas_by_id = {a["alpha_id"] for a in graph["activation"]["alphas"]}
    assert alphas_by_id == {
        "A001", "A003", "A101", "A102", "A103", "A201", "A301", "A304", "A501", "A601",
    }  # exactly the MVP-10, always emitted regardless of evidence

    evidenced_relevant = {
        a["alpha_id"]
        for a in graph["activation"]["alphas"]
        if a["alpha_id"] in RELEVANT_NVDA_ALPHA_IDS and a["evidence_count"] > 0
    }
    assert evidenced_relevant == RELEVANT_NVDA_ALPHA_IDS


def test_relevant_nvda_alpha_scores_are_differentiated_not_uniform(tmp_path):
    _, graph, _ = _run_nvda_fixture(tmp_path)

    relevant_scores = [
        a["activation_score"] for a in graph["activation"]["alphas"] if a["alpha_id"] in RELEVANT_NVDA_ALPHA_IDS
    ]
    distinct_scores = set(relevant_scores)

    assert len(distinct_scores) >= 4  # several genuinely distinct values, not a flat line
    assert max(relevant_scores) - min(relevant_scores) > 20  # meaningfully spread out


def test_scores_are_explainable_from_component_breakdowns(tmp_path):
    _, graph, _ = _run_nvda_fixture(tmp_path)

    for alpha in graph["activation"]["alphas"]:
        total = sum(c["contribution"] for c in alpha["components"].values())
        assert abs(total - alpha["activation_score"]) < 1e-6


def test_dominant_alphas_are_well_formed_when_present(tmp_path):
    """AI Alpha Mapper Discrimination Sprint: this fixture's A101 score
    dropped from regime_level (evidence_count=3) to active
    (evidence_count=2) once the Mapper's new A101 hard gate correctly
    stopped counting "NVIDIA should benefit as artificial intelligence
    demand keeps accelerator supply tight." as A101 evidence -- a bare
    "artificial intelligence demand"/"accelerator supply" mention with no
    genuine training/accelerator/investment anchor and no co-located change
    predicate, exactly the over-triggering this Sprint closes (see
    tests/test_ai_alpha_mapper_discrimination.py). dominant_alphas can
    legitimately be empty for this fixture now -- Activation/the Structure
    Graph are otherwise unchanged, so this test now only asserts the shape
    invariants that must hold whenever an entry is present, matching this
    file's own "shape and differentiation, not brittle exact scores"
    philosophy.
    """
    _, graph, _ = _run_nvda_fixture(tmp_path)

    for entry in graph["dominant_alphas"]:
        assert entry["status"] in ("dominant", "regime_level")
    scores = [entry["activation_score"] for entry in graph["dominant_alphas"]]
    assert scores == sorted(scores, reverse=True)


def test_evidence_and_claim_provenance_are_preserved(tmp_path):
    run_id, graph, repo = _run_nvda_fixture(tmp_path)

    a101 = next(a for a in graph["activation"]["alphas"] if a["alpha_id"] == "A101")
    assert a101["claim_ids"]
    assert a101["evidence"]

    persisted_matches = repo.get_alpha_matches(run_id)
    persisted_claim_ids = {row["claim_id"] for row in persisted_matches}
    assert set(a101["claim_ids"]).issubset(persisted_claim_ids)

    for node in graph["nodes"]:
        assert node["claim_ids"], f"node {node['id']} lost claim provenance"


def test_a304_negative_evidence_is_not_discarded_despite_coexisting_positive_ai_evidence(tmp_path):
    _, graph, _ = _run_nvda_fixture(tmp_path)

    a304 = next(a for a in graph["activation"]["alphas"] if a["alpha_id"] == "A304")
    a101 = next(a for a in graph["activation"]["alphas"] if a["alpha_id"] == "A101")

    assert a101["evidence_count"] > 0  # positive AI evidence exists in this fixture
    assert a304["evidence_count"] > 0  # A304's own risk evidence still got through
    assert a304["direction"] == "negative"
    assert a304["status"] != "inactive"
    assert a304["activation_score"] > 0


def test_graph_is_not_converted_into_a_buy_sell_hold_conclusion(tmp_path):
    _, graph, _ = _run_nvda_fixture(tmp_path)

    serialized = json.dumps(graph).lower()
    # Word-boundary match, not a bare substring check (same pattern as
    # test_week4_golden_closure.py's _BARE_TRADING_TERMS): a naive `in`
    # check false-positives on legitimate non-trading-advice content that
    # happens to contain one of these terms as a substring -- e.g. John's
    # B3 gated seed lifecycle's own EXPOSURE_BELOW_REGIME_THRESHOLD reason
    # code contains "hold" (thresHOLD), with zero relation to trading
    # advice. This graph legitimately reaching that reason code (NVDA is
    # now one of John's approved_gating tickers) is exactly the case a
    # substring check gets wrong and a word-boundary check gets right.
    for banned_term in ("buy", "sell", "hold", "recommendation", "conclusion"):
        assert re.search(rf"\b{banned_term}\b", serialized) is None


def test_no_week4_conflict_fields_are_present(tmp_path):
    _, graph, _ = _run_nvda_fixture(tmp_path)

    assert "main_conflict" not in graph
    assert "conflict_score" not in json.dumps(graph)
    assert "bull_structure" not in graph
    assert "bear_structure" not in graph
