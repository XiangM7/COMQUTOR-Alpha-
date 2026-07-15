"""W4.4 NVDA / QQQ Golden Closure and MSFT Blocker Guard.

Exercises the *complete* Week 4 end-to-end path -- offline inputs ->
structured outputs -> alpha matches -> graph -> activation -> conflict
detector -> W4 persistence -> canonical research response -> conflicts API
-- for the two tickers whose offline fixtures already produce real,
taxonomy-declared, admitted conflicts (see docs/week4_conflict_core_report.md
sections 20/21). Reuses the existing, already-clearly-labeled
synthetic/offline NVDA and QQQ fixtures via direct import -- never copies
fixture text, never invents ticker data.

Also locks a *blocker guard* for MSFT A102-A304 (docs/week4_spec_freeze_audit.md
section 16: BLOCKED_BY_SPEC_CONFLICT, taxonomy does not declare this pair).
The guard's purpose is not to make the MSFT Golden Case pass -- it never
will until a product/spec decision resolves the taxonomy conflict -- but to
catch any future attempt to quietly work around the block (editing the
taxonomy, hardcoding a ticker-specific exception in the detector,
substituting a different pair for the MSFT expectation).
"""

from __future__ import annotations

import re

from comqutor_alpha.alpha_library.alpha_loader import load_alpha_taxonomy
from comqutor_alpha.api.routes_research import (
    get_persisted_conflicts,
    get_research_run,
    run_research_request,
)
from comqutor_alpha.conflict_engine.conflict_detector import (
    detect_alpha_conflicts,
    evaluate_conflict_pair,
)
from comqutor_alpha.graph_engine.graph_schema import ACTIVATION_FORMULA_VERSION
from comqutor_alpha.storage.db.engine import build_engine
from comqutor_alpha.storage.db.migrations import apply_migrations
from comqutor_alpha.storage.db.repository import GraphPersistenceRepository
from tests.test_week3_nvda_sanity import _nvda_offline_outputs
from tests.test_week3_qqq_sanity import _SYNTHETIC_QQQ_OFFLINE_OUTPUTS

_BARE_TRADING_TERMS = re.compile(r"\b(buy|sell|hold)\b", re.IGNORECASE)
_FORBIDDEN_SUMMARY_PHRASES = (
    "price target",
    "guaranteed return",
    "guarantee",
    "% return",
    "position size",
    "expected return",
)


def _assert_no_bare_trading_language(text):
    assert text
    assert not _BARE_TRADING_TERMS.search(text)
    lowered = text.lower()
    for forbidden in _FORBIDDEN_SUMMARY_PHRASES:
        assert forbidden not in lowered


def _repo():
    engine = build_engine("sqlite:///:memory:")
    apply_migrations(engine)
    return GraphPersistenceRepository(engine)


def _nvda_payload():
    return {
        "ticker": "NVDA",
        "analysis_date": "2026-06-30",
        "selected_analysts": ["market", "news", "fundamentals", "sentiment"],
        "offline_raw_agent_outputs": _nvda_offline_outputs(),
    }


def _qqq_payload():
    return {
        "ticker": "QQQ",
        "analysis_date": "2026-06-30",
        "selected_analysts": ["market", "news", "fundamentals", "sentiment"],
        "offline_raw_agent_outputs": _SYNTHETIC_QQQ_OFFLINE_OUTPUTS,
    }


# ---------------------------------------------------------------------------
# NVDA Golden Closure
# ---------------------------------------------------------------------------


def test_nvda_golden_closure_full_week1_through_4_path(tmp_path):
    repo = _repo()

    post_response = run_research_request(_nvda_payload(), output_root=tmp_path, graph_repository=repo)
    run_id = post_response["run_id"]

    assert post_response["status"] == "completed"
    assert post_response["structure_graph_status"] == "ready"
    assert post_response["conflict_status"] == "ready"

    main_conflict = post_response["main_conflict"]
    assert main_conflict is not None
    assert main_conflict["conflict_id"] == "A101__A304"
    assert main_conflict["bull_alpha_id"] == "A101"
    assert main_conflict["bear_alpha_id"] == "A304"
    assert main_conflict["bull_structure"]["claim_ids"]
    assert main_conflict["bull_structure"]["evidence"]
    assert main_conflict["bear_structure"]["claim_ids"]
    assert main_conflict["bear_structure"]["evidence"]

    # Only bounds/composition/direction/ranking are asserted -- never a
    # brittle exact conflict_score.
    assert 0.0 <= main_conflict["conflict_score"] <= 100.0
    assert main_conflict["conflict_level"] in {"low", "medium", "medium_high", "high"}
    components = main_conflict["components"]
    assert components["contradiction_weight"] == 0.90  # taxonomy-declared A101<->A304 weight
    assert components["minimum_activation"] == min(components["activation_a"], components["activation_b"])

    # POST vs repository reconstruction vs /conflicts vs GET all agree.
    db_result = repo.get_week4_conflict_result(run_id)
    assert db_result is not None
    assert post_response["main_conflict"] == db_result["main_conflict"]

    conflicts_response = get_persisted_conflicts(run_id, output_root=tmp_path, graph_repository=repo)
    assert conflicts_response["status"] == "ok"
    assert {k: v for k, v in conflicts_response.items() if k != "status"} == db_result

    get_response = get_research_run(run_id, output_root=tmp_path, graph_repository=repo)
    assert get_response["main_conflict"] == post_response["main_conflict"]
    assert get_response["conflict_status"] == post_response["conflict_status"]
    assert get_response["summary"] == post_response["summary"]

    assert post_response["summary"] == main_conflict["explanation"]
    _assert_no_bare_trading_language(post_response["summary"])


# ---------------------------------------------------------------------------
# QQQ Golden Closure
# ---------------------------------------------------------------------------


def test_qqq_golden_closure_full_week1_through_4_path(tmp_path):
    repo = _repo()

    post_response = run_research_request(_qqq_payload(), output_root=tmp_path, graph_repository=repo)
    run_id = post_response["run_id"]

    assert post_response["status"] == "completed"
    assert post_response["structure_graph_status"] == "ready"
    assert post_response["conflict_status"] == "ready"

    db_result = repo.get_week4_conflict_result(run_id)
    assert db_result is not None
    conflicts = db_result["conflicts"]
    conflict_ids = {c["conflict_id"] for c in conflicts}

    assert "A001__A501" in conflict_ids
    assert "A003__A501" in conflict_ids

    for conflict in conflicts:
        if conflict["conflict_id"] not in {"A001__A501", "A003__A501"}:
            continue
        # A501 is the bear side of both admitted QQQ conflicts.
        assert conflict["bear_alpha_id"] == "A501"
        assert conflict["bull_alpha_id"] in {"A001", "A003"}
        assert conflict["bull_structure"]["claim_ids"]
        assert conflict["bull_structure"]["evidence"]
        assert conflict["bear_structure"]["claim_ids"]
        assert conflict["bear_structure"]["evidence"]
        assert 0.0 <= conflict["conflict_score"] <= 100.0

    # main_conflict must come from real arbitration ordering -- this test
    # never hardcodes which of the two admitted pairs wins.
    main_conflict = db_result["main_conflict"]
    assert main_conflict is not None
    assert main_conflict["conflict_id"] in {"A001__A501", "A003__A501"}
    assert main_conflict == conflicts[0]
    for later in conflicts[1:]:
        assert conflicts[0]["conflict_score"] >= later["conflict_score"]

    # POST / repository / conflicts API agreement.
    assert post_response["main_conflict"] == main_conflict
    conflicts_response = get_persisted_conflicts(run_id, output_root=tmp_path, graph_repository=repo)
    assert conflicts_response["status"] == "ok"
    assert {k: v for k, v in conflicts_response.items() if k != "status"} == db_result

    get_response = get_research_run(run_id, output_root=tmp_path, graph_repository=repo)
    assert get_response["main_conflict"] == post_response["main_conflict"]
    assert get_response["summary"] == post_response["summary"]

    _assert_no_bare_trading_language(post_response["summary"])


# ---------------------------------------------------------------------------
# MSFT Blocker Guard (docs/week4_spec_freeze_audit.md section 16)
# ---------------------------------------------------------------------------


class TestMSFTBlockerGuard:
    """Not a MSFT Golden Case -- MSFT stays BLOCKED_BY_SPEC_CONFLICT. These
    tests only prevent the block from being quietly worked around."""

    def test_a102_conflict_alphas_does_not_declare_a304(self):
        taxonomy = load_alpha_taxonomy()
        a102_targets = {c.alpha_id for c in taxonomy["A102"].conflict_alphas}
        assert "A304" not in a102_targets

    def test_a304_conflict_alphas_does_not_declare_a102(self):
        taxonomy = load_alpha_taxonomy()
        a304_targets = {c.alpha_id for c in taxonomy["A304"].conflict_alphas}
        assert "A102" not in a304_targets

    def test_no_a102_a304_contradiction_weight_is_declared_anywhere(self):
        taxonomy = load_alpha_taxonomy()
        for conflict in taxonomy["A102"].conflict_alphas:
            assert conflict.alpha_id != "A304"
        for conflict in taxonomy["A304"].conflict_alphas:
            assert conflict.alpha_id != "A102"

    def test_declared_pair_count_is_six_and_excludes_msft(self):
        taxonomy = load_alpha_taxonomy()
        activation_payload = {
            "formula_version": ACTIVATION_FORMULA_VERSION,
            "alphas": [
                {
                    "alpha_id": alpha_id,
                    "alpha_name": alpha_id,
                    "activation_score": 10.0,
                    "status": "inactive",
                    "direction": "unknown",
                }
                for alpha_id in taxonomy
            ],
        }
        result = detect_alpha_conflicts(
            run_id="msft_guard_run",
            ticker="MSFT",
            activation_payload=activation_payload,
            alpha_matches=[],
        )
        assert result["arbitration"]["declared_pair_count"] == 6
        pairs = {
            (candidate["alpha_a"], candidate["alpha_b"])
            for candidate in result["arbitration"]["candidate_evaluations"]
        }
        assert ("A102", "A304") not in pairs
        assert not any({"A102", "A304"} == set(pair) for pair in pairs)

    def test_evaluate_conflict_pair_returns_pair_not_declared_for_msft(self):
        minimal_activation_payload = {"formula_version": ACTIVATION_FORMULA_VERSION, "alphas": []}
        result = evaluate_conflict_pair(
            "A102",
            "A304",
            activation_payload=minimal_activation_payload,
            alpha_matches=[],
        )
        assert result["outcome"] == "rejected"
        assert "PAIR_NOT_DECLARED" in result["reason_codes"]
        assert "conflict" not in result

    def test_msft_pair_stays_undeclared_even_with_strong_synthetic_evidence(self):
        """Defense in depth: admissibility comes from taxonomy declaration
        alone, never from how strong constructed evidence looks -- even a
        maximally favorable synthetic activation/evidence pair for A102 and
        A304 must still be rejected as undeclared."""
        activation_payload = {
            "formula_version": ACTIVATION_FORMULA_VERSION,
            "alphas": [
                {
                    "alpha_id": "A102",
                    "alpha_name": "synthetic A102",
                    "activation_score": 95.0,
                    "status": "dominant",
                    "direction": "positive",
                },
                {
                    "alpha_id": "A304",
                    "alpha_name": "synthetic A304",
                    "activation_score": 95.0,
                    "status": "dominant",
                    "direction": "negative",
                },
            ],
        }
        alpha_matches = [
            {
                "claim_id": "synthetic_a102_claim",
                "match_status": "matched",
                "matched_alpha": "A102",
                "score": 0.95,
                "claim": "synthetic strong evidence for A102",
                "evidence": "synthetic strong evidence for A102",
                "candidate_scores": [{"alpha_id": "A102", "score": 0.95, "relation": "activation"}],
            },
            {
                "claim_id": "synthetic_a304_claim",
                "match_status": "matched",
                "matched_alpha": "A304",
                "score": 0.95,
                "claim": "synthetic strong evidence for A304",
                "evidence": "synthetic strong evidence for A304",
                "candidate_scores": [{"alpha_id": "A304", "score": 0.95, "relation": "activation"}],
            },
        ]
        result = evaluate_conflict_pair(
            "A102",
            "A304",
            activation_payload=activation_payload,
            alpha_matches=alpha_matches,
        )
        assert result["outcome"] == "rejected"
        assert "PAIR_NOT_DECLARED" in result["reason_codes"]
        assert "conflict" not in result
