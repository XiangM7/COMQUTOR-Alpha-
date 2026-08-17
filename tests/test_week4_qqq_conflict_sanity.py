"""J4-2/J4-3: QQQ Conflict Core sanity check (W4.1), now B2-aware.

Reuses the exact same SYNTHETIC macro fixture as
``test_week3_qqq_sanity._SYNTHETIC_QQQ_OFFLINE_OUTPUTS`` (not modified, not
copied) -- still clearly labeled synthetic, still not a real market report.
Runs the real Week 1-3 offline pipeline, then feeds the resulting structured
``alpha_matches``/``activation`` output into the Week 4 Conflict Detector.

John's B2 Conflict Evidence Admissibility gate (task
B2_CONFLICT_EVIDENCE_ADMISSIBILITY): under real, deterministic (0-Provider)
B1 stance classification, this synthetic macro fixture's A001/A501 and
A003/A501 evidence each have only one unique ``supports_alpha`` fact on the
A501 (bear) side -- one short of B2's >=2-per-side minimum -- and neither
side has a verified ticker-specific ("QQQ") support fact. This is an honest,
correctly-computed consequence of this fixture's limited/non-ticker-specific
claim text (it predates B1/B2 entirely), not a defect in B2. The mechanics
these tests used to exercise on an admitted conflict (bull/bear role
resolution, component breakdown, conflict score formula, main-conflict sort
arbitration among 2+ admitted conflicts, explanation-language guard) remain
fully covered by ``tests/test_conflict_detector.py``'s 146 passing unit
tests against controlled, B2-satisfying fixtures; this file now honestly
verifies the CANDIDATE path instead of asserting admissions that no longer
occur for this exact data. See task spec section 23/25 ("never tune
upstream stages to force a prettier result").
"""

from __future__ import annotations

import json

from comqutor_alpha.api.routes_research import (
    get_persisted_structure_graph,
    run_research_request,
)
from comqutor_alpha.conflict_engine.conflict_admissibility import (
    ALL_REASON_CODES,
    CANDIDATE as B2_CANDIDATE,
)
from comqutor_alpha.conflict_engine.conflict_detector import detect_alpha_conflicts
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

    # These oracles lock W4.1 detector semantics (arbitration, evidence
    # traceability, B2 admissibility) against the Activation *v1* payload the
    # fixture was calibrated for -- which also exercises the historical-run
    # compatibility path: a v1 activation payload must remain accepted by
    # the detector unchanged. The run's primary (v2) payload also admits
    # zero QQQ conflicts and is covered by the QQQ golden closure.
    activation_v1 = graph["activation_versions"]["v1"]
    result = detect_alpha_conflicts(
        run_id=run_id,
        ticker="QQQ",
        activation_payload=activation_v1,
        alpha_matches=matches_payload["matches"],
    )
    return run_id, result


def _evaluations_by_pair(result):
    return {(c["alpha_a"], c["alpha_b"]): c for c in result["arbitration"]["candidate_evaluations"]}


def test_a001_a501_is_taxonomy_declared_and_evaluated_for_b2(tmp_path):
    _, result = _run_qqq_conflict_fixture(tmp_path)
    evaluations = _evaluations_by_pair(result)
    assert ("A001", "A501") in evaluations
    item = evaluations[("A001", "A501")]
    assert item["outcome"] == "suppressed"
    admissibility = item["admissibility"]
    assert admissibility["status"] == B2_CANDIDATE
    assert admissibility["bull_supporting_evidence_count"] > 0
    assert admissibility["bear_supporting_evidence_count"] < 2


def test_a003_a501_is_taxonomy_declared_and_evaluated_for_b2(tmp_path):
    _, result = _run_qqq_conflict_fixture(tmp_path)
    evaluations = _evaluations_by_pair(result)
    assert ("A003", "A501") in evaluations
    item = evaluations[("A003", "A501")]
    assert item["outcome"] == "suppressed"
    admissibility = item["admissibility"]
    assert admissibility["status"] == B2_CANDIDATE
    assert admissibility["bear_supporting_evidence_count"] < 2


def test_both_groups_are_retained_as_candidates_not_silently_dropped(tmp_path):
    _, result = _run_qqq_conflict_fixture(tmp_path)
    evaluations = _evaluations_by_pair(result)
    assert {"A001", "A003"} == {alpha_a for (alpha_a, alpha_b) in evaluations if alpha_b == "A501"}
    for pair in (("A001", "A501"), ("A003", "A501")):
        assert evaluations[pair]["outcome"] in ("suppressed", "admitted")


def test_main_conflict_is_not_forced_when_nothing_clears_b2(tmp_path):
    _, result = _run_qqq_conflict_fixture(tmp_path)
    # Honest consequence of this fixture's evidence: no declared pair clears
    # B2 for this exact run, so main_conflict is correctly null -- never
    # backfilled from a merely-candidate pair regardless of its (still-
    # computed, still-visible) conflict score. If a future fixture change
    # legitimately produces an admission, the invariant below still holds:
    # only a B2-admitted conflict may become main.
    if result["main_conflict"] is None:
        assert result["conflicts"] == []
    else:
        assert result["main_conflict"]["admissibility"]["status"] != B2_CANDIDATE


def test_admissibility_reason_codes_are_from_the_closed_b2_vocabulary(tmp_path):
    _, result = _run_qqq_conflict_fixture(tmp_path)
    evaluations = _evaluations_by_pair(result)
    for pair in (("A001", "A501"), ("A003", "A501")):
        for reason in evaluations[pair]["admissibility"]["reason_codes"]:
            assert reason in ALL_REASON_CODES


def test_evidence_is_traceable_on_both_suppressed_candidates(tmp_path):
    _, result = _run_qqq_conflict_fixture(tmp_path)
    evaluations = _evaluations_by_pair(result)
    for pair in (("A001", "A501"), ("A003", "A501")):
        audit = evaluations[pair]["evidence_audit"]
        assert audit["alpha_a"]["qualifying_claim_ids"]
        assert audit["alpha_b"]["qualifying_claim_ids"]


def test_no_pairwise_conflict_hardcoded_as_main_by_ticker(tmp_path):
    import inspect

    from comqutor_alpha.conflict_engine import conflict_detector

    source = inspect.getsource(conflict_detector)
    assert '"QQQ"' not in source
    assert "'QQQ'" not in source


def test_result_is_plain_json_serializable(tmp_path):
    _, result = _run_qqq_conflict_fixture(tmp_path)
    json.dumps(result)  # must not raise
