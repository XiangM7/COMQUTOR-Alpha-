"""J4-1: NVDA Conflict Core sanity check (W4.1).

Runs the real Week 1-3 offline pipeline (reusing the exact same fixture
``test_week3_nvda_sanity._nvda_offline_outputs`` -- not modified, not
copied) to get real ``alpha_matches``/``activation`` structured output, then
feeds those directly into the Week 4 Conflict Detector. Never constructs a
conflict result from raw text, never hardcodes NVDA in production code --
only in this test's own assertions, which is the point of a ticker-specific
golden test.
"""

from __future__ import annotations

import json

from comqutor_alpha.api.routes_research import (
    get_persisted_structure_graph,
    run_research_request,
)
from comqutor_alpha.conflict_engine.conflict_detector import detect_alpha_conflicts
from comqutor_alpha.storage.db.engine import build_engine
from comqutor_alpha.storage.db.migrations import apply_migrations
from comqutor_alpha.storage.db.repository import GraphPersistenceRepository
from tests.test_week3_nvda_sanity import _nvda_offline_outputs


def _run_nvda_conflict_fixture(tmp_path):
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
    run_id = response["run_id"]

    graph = get_persisted_structure_graph(run_id, output_root=tmp_path, graph_repository=repo)
    assert graph["status"] == "ok"

    matches_payload = json.loads((tmp_path / run_id / "alpha_matches.json").read_text(encoding="utf-8"))

    result = detect_alpha_conflicts(
        run_id=run_id,
        ticker="NVDA",
        activation_payload=graph["activation"],
        alpha_matches=matches_payload["matches"],
    )
    return run_id, result


def test_a101_and_a304_both_have_qualifying_committed_evidence(tmp_path):
    _, result = _run_nvda_conflict_fixture(tmp_path)
    conflict = next(c for c in result["conflicts"] if c["conflict_id"] == "A101__A304")
    assert conflict["bull_structure"]["claim_ids"]
    assert conflict["bear_structure"]["claim_ids"]


def test_a101_a304_is_taxonomy_declared_and_admitted(tmp_path):
    _, result = _run_nvda_conflict_fixture(tmp_path)
    evaluations = {(c["alpha_a"], c["alpha_b"]): c for c in result["arbitration"]["candidate_evaluations"]}
    assert ("A101", "A304") in evaluations
    assert evaluations[("A101", "A304")]["outcome"] == "admitted"


def test_both_sides_status_at_least_watch(tmp_path):
    _, result = _run_nvda_conflict_fixture(tmp_path)
    conflict = next(c for c in result["conflicts"] if c["conflict_id"] == "A101__A304")
    admissible = {"watch", "active", "dominant", "regime_level"}
    assert conflict["bull_structure"]["status"] in admissible
    assert conflict["bear_structure"]["status"] in admissible


def test_bull_bear_roles_are_correct(tmp_path):
    _, result = _run_nvda_conflict_fixture(tmp_path)
    conflict = next(c for c in result["conflicts"] if c["conflict_id"] == "A101__A304")
    assert conflict["bull_alpha_id"] == "A101"
    assert conflict["bear_alpha_id"] == "A304"
    assert conflict["bull_structure"]["direction"] == "positive"
    assert conflict["bear_structure"]["direction"] == "negative"


def test_component_breakdown_is_complete(tmp_path):
    _, result = _run_nvda_conflict_fixture(tmp_path)
    conflict = next(c for c in result["conflicts"] if c["conflict_id"] == "A101__A304")
    components = conflict["components"]
    for key in (
        "activation_a",
        "activation_b",
        "minimum_activation",
        "contradiction_weight",
        "alpha_a_evidence_strength",
        "alpha_b_evidence_strength",
        "evidence_strength",
    ):
        assert key in components
    assert components["contradiction_weight"] == 0.90


def test_conflict_score_in_range_and_level_matches_formula(tmp_path):
    from comqutor_alpha.conflict_engine.conflict_schema import conflict_level

    _, result = _run_nvda_conflict_fixture(tmp_path)
    conflict = next(c for c in result["conflicts"] if c["conflict_id"] == "A101__A304")
    assert 0.0 <= conflict["conflict_score"] <= 100.0
    assert conflict["conflict_level"] == conflict_level(conflict["conflict_score"])


def test_main_conflict_is_a101_a304(tmp_path):
    _, result = _run_nvda_conflict_fixture(tmp_path)
    assert result["main_conflict"] is not None
    assert result["main_conflict"]["conflict_id"] == "A101__A304"


def test_explanation_has_no_bare_trading_advice(tmp_path):
    _, result = _run_nvda_conflict_fixture(tmp_path)
    conflict = next(c for c in result["conflicts"] if c["conflict_id"] == "A101__A304")
    explanation = conflict["explanation"]
    for phrase in ("Buy", "Sell", "Hold", "Strong Buy", "Strong Sell", "Guaranteed"):
        assert phrase not in explanation


def test_no_ticker_specific_production_branch(tmp_path):
    import inspect

    from comqutor_alpha.conflict_engine import conflict_detector

    source = inspect.getsource(conflict_detector)
    assert '"NVDA"' not in source
    assert "'NVDA'" not in source


def test_result_is_plain_json_serializable(tmp_path):
    _, result = _run_nvda_conflict_fixture(tmp_path)
    json.dumps(result)  # must not raise
