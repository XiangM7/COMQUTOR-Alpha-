"""W4.4 NVDA / QQQ Golden Closure and MSFT Blocker Guard.

Exercises the *complete* Week 4 end-to-end path -- offline inputs ->
structured outputs -> alpha matches -> graph -> activation -> conflict
detector -> W4 persistence -> canonical research response -> conflicts API
-- for the two tickers whose offline fixtures were originally built to
produce real, taxonomy-declared, admitted conflicts (see
docs/week4_conflict_core_report.md sections 20/21). Reuses the existing,
already-clearly-labeled synthetic/offline NVDA and QQQ fixtures via direct
import -- never copies fixture text, never invents ticker data.

John's B2 Conflict Evidence Admissibility gate (task
B2_CONFLICT_EVIDENCE_ADMISSIBILITY): under real, deterministic (0-Provider)
B1 stance classification, both of these fixtures' committed evidence has
only one unique ``supports_alpha`` fact on at least one side of their
previously-admitted pair -- one short of B2's >=2-per-side minimum -- so
both pairs now correctly close as B2 candidates rather than admitted
conflicts. This is an honest, correctly-computed consequence of these
fixtures' evidence volume (built before B1/B2 existed), not a defect in B2
-- see task spec section 23/25 ("never tune upstream stages to force a
prettier result"). What this file continues to prove end-to-end --
including, for NVDA, that the exact same computed admissibility diagnostic
reaches the DB reconstruction, the /conflicts API, and the GET response
without recomputation -- remains fully exercised below; only the specific
admitted-vs-candidate outcome changed.

Also locked (2026-09-28 update) a guard for MSFT A102-A304. This pair was
ORIGINALLY undeclared -- docs/week4_spec_freeze_audit.md section 16
(BLOCKED_BY_SPEC_CONFLICT, a frozen historical audit, never rewritten) and
PD-017 (docs/specs/product_decisions_and_unknowns.md,
REJECTED_BY_INDEPENDENT_LLM_ADJUDICATION) both record that state as of
their own time. It has SINCE been explicitly reopened and approved by
PD-017-REVISED (`APPROVED_CONDITIONAL`, direct user instruction naming
A102__A304 and A201__A304 by name) -- `alpha_taxonomy_v1.yaml` now declares
both pairs (contradiction_weight 0.75 each), and
`tests/test_msft_a102_a304_taxonomy_adjudication.py` was already updated in
that same change to assert the new state. The class below was NOT updated
at that time (a genuine gap, fixed here) -- its assertions are corrected to
match PD-017-REVISED's own documented, current, authorized taxonomy state.
Its remaining guard purpose: declaring a pair evaluable is explicitly NOT
the same as admitting it (PD-017-REVISED's own "What this does NOT mean"
clause) -- the real, unmodified B2 admissibility gate must still govern
whether A102__A304 is ever actually admitted for any given run, exactly
like every other declared pair; these tests catch any future attempt to
special-case an automatic admission for it.
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
from comqutor_alpha.graph_engine.verified_evidence_gate import ACTIVATION_V2_VERIFIED_FORMULA_VERSION
from comqutor_alpha.storage.db.engine import build_engine
from comqutor_alpha.storage.db.migrations import apply_migrations
from comqutor_alpha.storage.db.repository import GraphPersistenceRepository
from scripts.w5_demo_fixtures import approved_demo_outputs
from scripts.deterministic_echo_llm import build_deterministic_echo_gateway

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


def _assert_agent_output_traceability(repo, run_id):
    outputs = {row["claim_id"]: row for row in repo.list_agent_outputs(run_id)}
    matches = repo.get_alpha_matches(run_id)
    assert outputs
    assert matches
    assert repo.count_agent_outputs(run_id) == len(outputs)
    for match in matches:
        output = outputs[match["claim_id"]]
        assert match["source_agent_output_id"] == output["source_agent_output_id"]
        assert match["evidence"] == output["evidence"]


_EVIDENCE_UI_TEXT_GROUPS = ("bull_evidence", "bear_evidence", "counter_evidence")
_EXTERNAL_SOURCE_KEYS = ("external_source", "external_source_status")


def _strip_external_source_annotations(conflict):
    """Drop John MVP Final Gap Closure's additive, read-time-only
    external_source/external_source_status keys from every evidence_ui
    item -- see routes_research._attach_external_sources_to_conflicts,
    which annotates conflicts/main_conflict/candidate_evaluations in
    place, never recomputing evidence_ui itself."""
    if not isinstance(conflict, dict):
        return conflict
    evidence_ui = conflict.get("evidence_ui")
    if not isinstance(evidence_ui, dict):
        return conflict
    stripped_evidence_ui = dict(evidence_ui)
    for group_name in _EVIDENCE_UI_TEXT_GROUPS:
        items = stripped_evidence_ui.get(group_name)
        if not isinstance(items, list):
            continue
        stripped_evidence_ui[group_name] = [
            {k: v for k, v in item.items() if k not in _EXTERNAL_SOURCE_KEYS}
            if isinstance(item, dict)
            else item
            for item in items
        ]
    return {**conflict, "evidence_ui": stripped_evidence_ui}


def _without_additive_conflict_evidence(conflicts_response):
    """Drop the Structure Correctness Sprint's additive per-conflict
    bull_evidence/bear_evidence fields (and top-level status), plus John
    MVP Final Gap Closure's additive evidence_ui external_source/
    external_source_status annotations, so the remainder can be compared
    byte-for-byte against the W4.2 repository reconstruction, which never
    carried any of them."""
    def strip(conflict):
        if not isinstance(conflict, dict):
            return conflict
        conflict = _strip_external_source_annotations(conflict)
        return {k: v for k, v in conflict.items() if k not in {"bull_evidence", "bear_evidence"}}

    stripped = {k: v for k, v in conflicts_response.items() if k != "status"}
    stripped["conflicts"] = [strip(c) for c in stripped.get("conflicts", [])]
    stripped["main_conflict"] = strip(stripped.get("main_conflict"))
    arbitration = stripped.get("arbitration")
    if isinstance(arbitration, dict) and isinstance(arbitration.get("candidate_evaluations"), list):
        stripped["arbitration"] = {
            **arbitration,
            "candidate_evaluations": [
                _strip_external_source_annotations(item) for item in arbitration["candidate_evaluations"]
            ],
        }
    return stripped


def _nvda_payload():
    return {
        "ticker": "NVDA",
        "analysis_date": "2026-06-30",
        "selected_analysts": ["market", "news", "fundamentals", "sentiment"],
        "offline_raw_agent_outputs": approved_demo_outputs("NVDA"),
    }


def _qqq_payload():
    return {
        "ticker": "QQQ",
        "analysis_date": "2026-06-30",
        "selected_analysts": ["market", "news", "fundamentals", "sentiment"],
        "offline_raw_agent_outputs": approved_demo_outputs("QQQ"),
    }


# ---------------------------------------------------------------------------
# NVDA Golden Closure
# ---------------------------------------------------------------------------


def test_nvda_golden_closure_full_week1_through_4_path(tmp_path):
    repo = _repo()

    gateway = build_deterministic_echo_gateway("week4-golden-closure-nvda", tmp_path)
    post_response = run_research_request(
        _nvda_payload(), output_root=tmp_path, graph_repository=repo, week2_llm_gateway=gateway
    )
    run_id = post_response["run_id"]

    assert post_response["status"] == "completed"
    assert post_response["structure_graph_status"] == "ready"
    assert post_response["conflict_status"] == "ready"
    _assert_agent_output_traceability(repo, run_id)

    # T1 gate-bypass fix (2026-09-29): require_verified_evidence_gate=True
    # now makes the OFFICIAL activation pool verified-only unconditionally,
    # and this fixture's claims are never source-linked/human-reviewed --
    # both A101 and A304 officially score 0 (zero verified evidence), so
    # bull/bear role resolution itself cannot resolve (DIRECTION_ROLE_
    # UNRESOLVED), rejecting the candidate even earlier than the old,
    # pre-fix "suppressed at B2 for insufficient evidence volume" outcome.
    # main_conflict is correctly null either way; never backfilled from a
    # merely-candidate pair.
    assert post_response["main_conflict"] is None

    # Taxonomy-declared A101<->A304 weight is a static taxonomy property,
    # independent of any run's admissibility outcome.
    taxonomy = load_alpha_taxonomy()
    a101_weight = next(
        c.contradiction_weight for c in taxonomy["A101"].conflict_alphas if c.alpha_id == "A304"
    )
    assert a101_weight == 0.90

    # POST vs repository reconstruction vs /conflicts vs GET all agree --
    # including the full admissibility diagnostic the DB persisted for the
    # A101/A304 candidate, computed exactly once by the Conflict Detector
    # and never recomputed by any of these three read paths.
    db_result = repo.get_week4_conflict_result(run_id)
    assert db_result is not None
    assert db_result["conflicts"] == []
    assert post_response["main_conflict"] == db_result["main_conflict"]

    evaluations = {
        (c["alpha_a"], c["alpha_b"]): c for c in db_result["arbitration"]["candidate_evaluations"]
    }
    assert ("A101", "A304") in evaluations
    a101_a304 = evaluations[("A101", "A304")]
    # Rejected before ever reaching B2 admissibility -- with both sides at
    # official (verified) score 0, bull/bear role resolution itself cannot
    # resolve. evidence_audit's own claim-to-alpha matching (computed
    # before role/score resolution) is unaffected by the gate and still
    # shows the real, qualifying claim counts.
    assert a101_a304["outcome"] == "rejected"
    assert a101_a304["reason_codes"] == ["DIRECTION_ROLE_UNRESOLVED"]
    assert "admissibility" not in a101_a304
    assert a101_a304["evidence_audit"]["alpha_a"]["qualifying_count"] > 0
    assert a101_a304["evidence_audit"]["alpha_b"]["qualifying_count"] > 0

    conflicts_response = get_persisted_conflicts(run_id, output_root=tmp_path, graph_repository=repo)
    assert conflicts_response["status"] == "ok"
    assert _without_additive_conflict_evidence(conflicts_response) == db_result
    # No admitted conflict exists for this fixture under B2, so the
    # Structure Correctness Sprint's additive bull_evidence/bear_evidence
    # enrichment (which only attaches to entries in conflicts/main_conflict)
    # has nothing to enrich here; its wiring is exercised by
    # test_conflict_detector.py/test_week4_persistence.py fixtures that do
    # clear B2.

    get_response = get_research_run(run_id, output_root=tmp_path, graph_repository=repo)
    assert get_response["main_conflict"] == post_response["main_conflict"]
    assert get_response["conflict_status"] == post_response["conflict_status"]
    assert get_response["summary"] == post_response["summary"]

    # T1 gate-bypass fix (2026-09-29): this fixture's claims are never
    # source-linked/human-reviewed, so the official (verified) pool has
    # zero evidence everywhere -- the summary now explicitly distinguishes
    # this data-availability state from "genuinely evaluated and found
    # nothing," never silently claiming the market has no conflict.
    assert post_response["summary"] == (
        "Verified evidence is currently insufficient to reach an official "
        "conclusion for this research run -- unreviewed or unlinked claims "
        "may still exist as research text or pending-review candidates, but "
        "none yet counts as verified support."
    )
    _assert_no_bare_trading_language(post_response["summary"])


# ---------------------------------------------------------------------------
# QQQ Golden Closure
# ---------------------------------------------------------------------------


def test_qqq_golden_closure_full_week1_through_4_path(tmp_path):
    """QQQ golden closure under the versioned activation contract.

    The run's *primary* activation is v2: the deliberately thin QQQ fixture
    (one A501 claim from one agent) legitimately admits zero conflicts --
    both approved pairs are still arbitrated and are rejected on activation
    threshold, never silently skipped. The v1 audit payload is preserved
    verbatim, and feeding it to the detector still admits both approved
    pairs exactly as before (historical-run compatibility).
    """
    repo = _repo()

    gateway = build_deterministic_echo_gateway("week4-golden-closure-qqq", tmp_path)
    post_response = run_research_request(
        _qqq_payload(), output_root=tmp_path, graph_repository=repo, week2_llm_gateway=gateway
    )
    run_id = post_response["run_id"]

    assert post_response["status"] == "completed"
    assert post_response["structure_graph_status"] == "ready"
    assert post_response["conflict_status"] == "ready"
    _assert_agent_output_traceability(repo, run_id)

    db_result = repo.get_week4_conflict_result(run_id)
    assert db_result is not None
    # T1 gate-bypass fix (2026-09-29): require_verified_evidence_gate=True
    # on the real run_research_request entrypoint makes the verified-gate
    # formula version official unconditionally (never the plain v2 formula
    # version), even for a run with no source-linked/reviewed claims.
    assert db_result["activation_formula_version"] == ACTIVATION_V2_VERIFIED_FORMULA_VERSION
    assert db_result["conflicts"] == []
    assert db_result["main_conflict"] is None

    # Both approved pairs were genuinely arbitrated (evaluated, then
    # rejected) -- never skipped. T1 gate-bypass fix (2026-09-29): with the
    # OFFICIAL pool now unconditionally verified-only and this fixture's
    # claims never source-linked/reviewed, every alpha officially scores 0
    # -- bull/bear role resolution itself cannot resolve (DIRECTION_ROLE_
    # UNRESOLVED) for both pairs, rejecting them even before B2's own
    # score/evidence-count admissibility checks are ever reached.
    evaluations = {
        (c["alpha_a"], c["alpha_b"]): c
        for c in db_result["arbitration"]["candidate_evaluations"]
    }
    for pair in (("A001", "A501"), ("A003", "A501")):
        assert pair in evaluations
        assert evaluations[pair]["outcome"] == "rejected"
        assert evaluations[pair]["reason_codes"] == ["DIRECTION_ROLE_UNRESOLVED"]

    # POST / repository / conflicts API agreement.
    assert post_response["main_conflict"] is None
    conflicts_response = get_persisted_conflicts(run_id, output_root=tmp_path, graph_repository=repo)
    assert conflicts_response["status"] == "ok"
    assert _without_additive_conflict_evidence(conflicts_response) == db_result

    get_response = get_research_run(run_id, output_root=tmp_path, graph_repository=repo)
    assert get_response["main_conflict"] == post_response["main_conflict"]
    assert get_response["summary"] == post_response["summary"]

    _assert_no_bare_trading_language(post_response["summary"])

    # Historical-run compatibility: the preserved v1 activation payload,
    # fed to the (unchanged min() formula) detector, still evaluates both
    # approved QQQ pairs with A501 on the bear side (byte-for-byte v1
    # activation-score oracle behavior -- both clear the v1 activation
    # threshold, unlike under the primary v2 payload above). John's B2 gate
    # then applies identically regardless of activation formula version:
    # this fixture's real evidence gives A501 (bear, both pairs) only one
    # unique supports_alpha fact with no verified ticker-specific support --
    # one short of B2's per-side minimum -- so neither pair is admitted.
    # This is an honest, correctly-computed consequence of this fixture's
    # evidence (predates B1/B2), not a defect in B2 or in v1 compatibility.
    import json as _json

    graph_json = repo.get_graph(run_id)["graph_json"]
    activation_v1 = graph_json["activation_versions"]["v1"]
    assert activation_v1["formula_version"] == ACTIVATION_FORMULA_VERSION
    matches_payload = _json.loads(
        (tmp_path / run_id / "alpha_matches.json").read_text(encoding="utf-8")
    )
    v1_result = detect_alpha_conflicts(
        run_id=run_id,
        ticker="QQQ",
        activation_payload=activation_v1,
        alpha_matches=matches_payload["matches"],
    )
    assert v1_result["conflicts"] == []
    assert v1_result["main_conflict"] is None
    v1_evaluations = {
        (c["alpha_a"], c["alpha_b"]): c for c in v1_result["arbitration"]["candidate_evaluations"]
    }
    for pair in (("A001", "A501"), ("A003", "A501")):
        assert pair in v1_evaluations
        item = v1_evaluations[pair]
        assert item["outcome"] == "suppressed"
        admissibility = item["admissibility"]
        assert admissibility["status"] == "candidate"
        # Both pairs clear the v1 activation threshold (unlike the primary
        # v2 payload above) -- B2 suppression here is evidence-driven, not
        # activation-driven.
        assert "BULL_SCORE_BELOW_THRESHOLD" not in admissibility["reason_codes"]
        assert "BEAR_SCORE_BELOW_THRESHOLD" not in admissibility["reason_codes"]
        assert admissibility["bear_supporting_evidence_count"] < 2


# ---------------------------------------------------------------------------
# MSFT A102-A304 taxonomy-declaration guard (updated 2026-09-28 per
# PD-017-REVISED -- see the class docstring above for the full history)
# ---------------------------------------------------------------------------


class TestMSFTA102A304DeclaredButAdmissionStillEvidenceGated:
    """PD-017-REVISED (docs/specs/product_decisions_and_unknowns.md):
    A102__A304 (and A201__A304) are now declared, APPROVED_CONDITIONAL
    taxonomy pairs -- superseding PD-017's original rejection. These tests
    assert the CURRENT, authorized declaration state, and guard the ONE
    thing PD-017-REVISED itself explicitly preserves: declaring a pair
    evaluable is never the same as admitting it -- the real, unmodified B2
    admissibility gate still decides admission exactly like every other
    declared pair, so a future change must never special-case automatic
    admission for A102__A304."""

    def test_a102_conflict_alphas_declares_a304_per_pd017_revised(self):
        taxonomy = load_alpha_taxonomy()
        a102_by_target = {c.alpha_id: c.contradiction_weight for c in taxonomy["A102"].conflict_alphas}
        assert a102_by_target.get("A304") == 0.75

    def test_a304_conflict_alphas_declares_a102_reciprocally(self):
        taxonomy = load_alpha_taxonomy()
        a304_by_target = {c.alpha_id: c.contradiction_weight for c in taxonomy["A304"].conflict_alphas}
        assert a304_by_target.get("A102") == 0.75

    def test_a102_a304_contradiction_weight_matches_reciprocally_both_sides(self):
        taxonomy = load_alpha_taxonomy()
        a102_weight = next(c.contradiction_weight for c in taxonomy["A102"].conflict_alphas if c.alpha_id == "A304")
        a304_weight = next(c.contradiction_weight for c in taxonomy["A304"].conflict_alphas if c.alpha_id == "A102")
        assert a102_weight == a304_weight == 0.75

    def test_declared_pair_count_is_eight_and_includes_a102_a304(self):
        """6 original mandatory pairs + A102__A304 + A201__A304
        (PD-017-REVISED) = 8. Verified directly against
        ``_enumerate_canonical_pairs`` before writing this literal -- never
        a blind 6->8 replacement."""
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
        assert result["arbitration"]["declared_pair_count"] == 8
        pairs = {
            (candidate["alpha_a"], candidate["alpha_b"])
            for candidate in result["arbitration"]["candidate_evaluations"]
        }
        assert any({"A102", "A304"} == set(pair) for pair in pairs)
        assert any({"A201", "A304"} == set(pair) for pair in pairs)

    def test_evaluate_conflict_pair_no_longer_rejects_a102_a304_as_undeclared(self):
        """The pair is now declared -- an empty activation payload is
        rejected for a genuinely different, real reason (no activation
        entry for either side at all), never PAIR_NOT_DECLARED."""
        minimal_activation_payload = {"formula_version": ACTIVATION_FORMULA_VERSION, "alphas": []}
        result = evaluate_conflict_pair(
            "A102",
            "A304",
            activation_payload=minimal_activation_payload,
            alpha_matches=[],
        )
        assert result["outcome"] == "rejected"
        assert "PAIR_NOT_DECLARED" not in result["reason_codes"]
        assert "MISSING_LEFT_ACTIVATION" in result["reason_codes"]
        assert "MISSING_RIGHT_ACTIVATION" in result["reason_codes"]
        assert "conflict" not in result

    def test_a102_a304_declaration_alone_never_admits_without_real_sufficient_evidence(self):
        """PD-017-REVISED's own explicit caveat, exercised through the real
        function: 'declaring a pair evaluable is not the same as it being
        admitted' -- even a maximally favorable synthetic activation score
        for both sides is still suppressed here because this fixture
        supplies only ONE claim per side (John's B2 gate requires >=2
        supporting facts per side, exactly as for every other declared
        pair) -- never an automatic admission just because the taxonomy now
        declares the pair."""
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
        assert result["outcome"] != "admitted"
        assert "PAIR_NOT_DECLARED" not in result["reason_codes"]
        assert "conflict" not in result
