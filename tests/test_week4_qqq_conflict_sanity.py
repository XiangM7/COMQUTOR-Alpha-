"""J4-2/J4-3: QQQ Conflict Core sanity check (W4.1).

Reuses the exact same SYNTHETIC macro fixture as
``test_week3_qqq_sanity._SYNTHETIC_QQQ_OFFLINE_OUTPUTS`` (not modified, not
copied) -- still clearly labeled synthetic, still not a real market report.
Runs the real Week 1-3 offline pipeline, then feeds the resulting structured
``alpha_matches``/``activation`` output into the Week 4 Conflict Detector.
"""

from __future__ import annotations

import json

from comqutor_alpha.api.routes_research import (
    get_persisted_structure_graph,
    run_research_request,
)
from comqutor_alpha.conflict_engine.conflict_detector import detect_alpha_conflicts
from comqutor_alpha.conflict_engine.conflict_schema import conflict_level
from comqutor_alpha.storage.db.engine import build_engine
from comqutor_alpha.storage.db.migrations import apply_migrations
from comqutor_alpha.storage.db.repository import GraphPersistenceRepository
from tests.test_week3_qqq_sanity import _SYNTHETIC_QQQ_OFFLINE_OUTPUTS


def _run_qqq_conflict_fixture(tmp_path):
    engine = build_engine("sqlite:///:memory:")
    apply_migrations(engine)
    repo = GraphPersistenceRepository(engine)
    payload = {
        "ticker": "QQQ",
        "analysis_date": "2026-06-30",
        "selected_analysts": ["market", "news", "fundamentals", "sentiment"],
        "offline_raw_agent_outputs": _SYNTHETIC_QQQ_OFFLINE_OUTPUTS,
    }
    response = run_research_request(payload, output_root=tmp_path, graph_repository=repo)
    assert response["status"] == "completed"
    run_id = response["run_id"]

    graph = get_persisted_structure_graph(run_id, output_root=tmp_path, graph_repository=repo)
    assert graph["status"] == "ok"

    matches_payload = json.loads((tmp_path / run_id / "alpha_matches.json").read_text(encoding="utf-8"))

    # These oracles lock W4.1 detector semantics (arbitration, bull/bear
    # roles, traceability) against the Activation *v1* payload the fixture
    # was calibrated for -- which also exercises the historical-run
    # compatibility path: a v1 activation payload must remain accepted by
    # the detector unchanged. The run's primary (v2) payload legitimately
    # admits zero QQQ conflicts and is covered by the QQQ golden closure.
    activation_v1 = graph["activation_versions"]["v1"]
    result = detect_alpha_conflicts(
        run_id=run_id,
        ticker="QQQ",
        activation_payload=activation_v1,
        alpha_matches=matches_payload["matches"],
    )
    return run_id, result


def _conflicts_by_id(result):
    return {c["conflict_id"]: c for c in result["conflicts"]}


def test_a001_a501_produces_admitted_conflict(tmp_path):
    _, result = _run_qqq_conflict_fixture(tmp_path)
    assert "A001__A501" in _conflicts_by_id(result)


def test_a003_a501_produces_admitted_conflict(tmp_path):
    _, result = _run_qqq_conflict_fixture(tmp_path)
    assert "A003__A501" in _conflicts_by_id(result)


def test_both_groups_are_retained_in_conflicts(tmp_path):
    _, result = _run_qqq_conflict_fixture(tmp_path)
    conflicts = _conflicts_by_id(result)
    assert {"A001__A501", "A003__A501"}.issubset(conflicts)


def test_main_conflict_is_decided_by_formal_sort_rule_not_hardcoded(tmp_path):
    _, result = _run_qqq_conflict_fixture(tmp_path)
    conflicts = result["conflicts"]
    assert len(conflicts) >= 2
    # main_conflict must be exactly the first element of the already-sorted
    # conflicts list -- i.e. arbitration order, never a ticker-specific pick.
    assert result["main_conflict"]["conflict_id"] == conflicts[0]["conflict_id"]
    scores = [c["conflict_score"] for c in conflicts]
    assert scores == sorted(scores, reverse=True)


def test_a501_is_bear_side_in_both_groups(tmp_path):
    _, result = _run_qqq_conflict_fixture(tmp_path)
    conflicts = _conflicts_by_id(result)
    assert conflicts["A001__A501"]["bear_alpha_id"] == "A501"
    assert conflicts["A003__A501"]["bear_alpha_id"] == "A501"
    assert conflicts["A001__A501"]["bear_structure"]["direction"] == "negative"
    assert conflicts["A003__A501"]["bear_structure"]["direction"] == "negative"


def test_a001_a003_are_bull_side_per_formal_direction(tmp_path):
    _, result = _run_qqq_conflict_fixture(tmp_path)
    conflicts = _conflicts_by_id(result)
    assert conflicts["A001__A501"]["bull_alpha_id"] == "A001"
    assert conflicts["A003__A501"]["bull_alpha_id"] == "A003"
    assert conflicts["A001__A501"]["bull_structure"]["direction"] == "positive"
    assert conflicts["A003__A501"]["bull_structure"]["direction"] == "positive"


def test_component_breakdown_and_evidence_are_traceable(tmp_path):
    _, result = _run_qqq_conflict_fixture(tmp_path)
    for conflict_id in ("A001__A501", "A003__A501"):
        conflict = _conflicts_by_id(result)[conflict_id]
        assert conflict["components"]["contradiction_weight"] == 0.85
        assert conflict["bull_structure"]["claim_ids"]
        assert conflict["bull_structure"]["evidence"]
        assert conflict["bear_structure"]["claim_ids"]
        assert conflict["bear_structure"]["evidence"]
        assert conflict["conflict_level"] == conflict_level(conflict["conflict_score"])


def test_explanation_has_no_bare_trading_advice(tmp_path):
    _, result = _run_qqq_conflict_fixture(tmp_path)
    for conflict in result["conflicts"]:
        explanation = conflict["explanation"]
        for phrase in ("Buy", "Sell", "Hold", "Strong Buy", "Strong Sell", "Guaranteed"):
            assert phrase not in explanation


def test_no_pairwise_conflict_hardcoded_as_main_by_ticker(tmp_path):
    import inspect

    from comqutor_alpha.conflict_engine import conflict_detector

    source = inspect.getsource(conflict_detector)
    assert '"QQQ"' not in source
    assert "'QQQ'" not in source
