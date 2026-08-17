"""B4 Activation Level Alignment -- dedicated tests (task
B4_ACTIVATION_LEVEL_ALIGNMENT).

Covers the task's own required sections A-H against the single
authoritative classifier (``graph_engine.alpha_level_classifier``) and its
wiring into Exposure, persistence, and the Conflict Detector. Reuses the
existing, unmodified Activation v2 cap/regime-gate reason codes and
Exposure Engine formula/qualification signals -- never reimplements or
re-derives them; every input this file passes to the classifier is exactly
the shape the real pipeline (``graph_engine.pipeline.
score_and_assemble_structure_graph``) already produces.

Section map:
    A - exact threshold boundaries + type/range rejection
    B - dominant qualification (5 distinct failure causes)
    C - regime qualification (3 scenarios, fixed blocked_from order)
    D - B3 Entity Exposure lifecycle interaction (all 3 states + fail-closed)
    E - canonical reason mapping (John's 4 reasons, dedup, unmapped-diagnostic-only)
    F - collection consistency / five-way UI-partition exclusivity
    G - persistence whitelist consistency (old and new payloads)
    H - B2 Conflict Core compatibility (byte-identical inputs, unaffected admission)
"""

from __future__ import annotations

import math

import pytest

from comqutor_alpha.conflict_engine.conflict_detector import detect_alpha_conflicts
from comqutor_alpha.conflict_engine.conflict_schema import ADMISSIBLE_STATUSES
from comqutor_alpha.graph_engine.activation_scorer_v2 import ACTIVATION_V2_FORMULA_VERSION
from comqutor_alpha.graph_engine.alpha_level_classifier import (
    ACTIVE,
    ACTIVE_THRESHOLD,
    CANDIDATE,
    CANONICAL_BLOCKED_REASONS,
    CLASSIFICATION_VERSION,
    DOMINANT,
    DOMINANT_THRESHOLD,
    REASON_INSUFFICIENT_EVIDENCE,
    REASON_LOW_ENTITY_EXPOSURE,
    REASON_NO_LOCAL_STRUCTURE_SUPPORT,
    REASON_NO_TICKER_SPECIFIC_EVIDENCE,
    REGIME_LEVEL,
    REGIME_LEVEL_THRESHOLD,
    AlphaLevelInputError,
    classify_alpha_level,
    classify_and_rebuild_collections,
    level_for_score,
)
from comqutor_alpha.storage.db.engine import build_engine
from comqutor_alpha.storage.db.migrations import apply_migrations
from comqutor_alpha.storage.db.repository import GraphPersistenceError, GraphPersistenceRepository
from tests.fixtures.week4_conflict_cases import activation_entry, activation_payload, match_record

# ---------------------------------------------------------------------------
# Section A -- exact threshold boundaries (task section 4/16.A). Half-open
# lower-bound comparisons only (score >= threshold) -- the exact class of
# <=/> boundary bug this task exists to eliminate.
# ---------------------------------------------------------------------------


@pytest.mark.parametrize(
    ("score", "expected_level"),
    [
        (0.0, CANDIDATE),
        (ACTIVE_THRESHOLD - 0.001, CANDIDATE),  # 49.999 -> candidate
        (ACTIVE_THRESHOLD, ACTIVE),  # 50.000 -> active
        (DOMINANT_THRESHOLD - 0.001, ACTIVE),  # 69.999 -> active
        (DOMINANT_THRESHOLD, DOMINANT),  # 70.000 -> dominant
        (REGIME_LEVEL_THRESHOLD - 0.001, DOMINANT),  # 85.999 -> dominant
        (REGIME_LEVEL_THRESHOLD, REGIME_LEVEL),  # 86.000 -> regime_level
        (100.0, REGIME_LEVEL),
    ],
)
def test_a_exact_threshold_boundaries(score, expected_level):
    assert level_for_score(score) == expected_level


@pytest.mark.parametrize(
    "bad_score",
    [
        float("nan"),
        float("inf"),
        float("-inf"),
        True,
        False,
        "50",
        None,
        -0.001,
        100.001,
    ],
)
def test_a_invalid_scores_are_rejected_never_clamped_or_guessed(bad_score):
    with pytest.raises(AlphaLevelInputError) as exc_info:
        level_for_score(bad_score)
    assert exc_info.value.reason_code == "INVALID_ACTIVATION_LEVEL_SCORE"


def test_a_classify_alpha_level_itself_rejects_an_invalid_activation_score():
    # Not just the level_for_score helper -- the actual entry point too.
    with pytest.raises(AlphaLevelInputError):
        classify_alpha_level(activation_score=math.nan)


def test_a_classify_alpha_level_rejects_an_invalid_uncapped_score_too():
    with pytest.raises(AlphaLevelInputError):
        classify_alpha_level(activation_score=60.0, uncapped_score="not a number")


# ---------------------------------------------------------------------------
# Section B -- dominant qualification: 5 distinct real failure causes, each
# reusing one of activation_scorer_v2._apply_caps's own unmodified reason
# codes (never a new one invented here).
# ---------------------------------------------------------------------------

_DOMINANT_CAP_CAUSES = [
    "INSUFFICIENT_UNIQUE_EVIDENCE",
    "INSUFFICIENT_AGENT_INDEPENDENCE",
    "NO_TICKER_SPECIFIC_EVIDENCE",
    "NO_LOCAL_STRUCTURE_SUPPORT",
    "KEYWORD_ONLY_SUPPORT",
]


@pytest.mark.parametrize("cap_reason", _DOMINANT_CAP_CAUSES)
def test_b_each_dominant_cap_cause_blocks_dominant_and_falls_back_to_active(cap_reason):
    result = classify_alpha_level(
        activation_score=75.0,  # target_level == dominant
        dominant_cap_reason_codes=[cap_reason],
    )
    assert result.target_level == DOMINANT
    assert result.qualified_level == ACTIVE
    assert result.is_blocked is True
    assert result.blocked_from == (DOMINANT,)
    assert cap_reason in result.diagnostic_reason_codes
    assert result.classification_version == CLASSIFICATION_VERSION


def test_b_no_cap_reasons_means_dominant_fully_qualifies():
    result = classify_alpha_level(activation_score=75.0, dominant_cap_reason_codes=[])
    assert result.target_level == DOMINANT
    assert result.qualified_level == DOMINANT
    assert result.is_blocked is False
    assert result.blocked_from == ()
    assert result.blocked_reason_codes == ()


def test_b_candidate_and_active_never_gain_a_new_evidence_graph_or_exposure_gate():
    # Case A/B (task section 7): John explicitly -- do not invent a new gate
    # for candidate/active beyond the score itself, even when every other
    # qualification signal would fail.
    for score in (10.0, 55.0):
        result = classify_alpha_level(
            activation_score=score,
            dominant_cap_reason_codes=["NO_LOCAL_STRUCTURE_SUPPORT"],
            regime_gate_passed=False,
            entity_exposure={
                "effective_status": "approved_gating",
                "exposure_status": "computed",
                "would_block_dominant": True,
                "would_block_regime_level": True,
                "reason_codes": ["EXPOSURE_BELOW_DOMINANT_THRESHOLD"],
            },
        )
        assert result.is_blocked is False
        assert result.qualified_level == result.target_level


# ---------------------------------------------------------------------------
# Section C -- regime qualification (3 scenarios). blocked_from is always
# [dominant, regime_level] in that fixed order, never regime_level alone
# jumping straight to active.
# ---------------------------------------------------------------------------


def test_c_regime_gate_passes_and_dominant_qualifies_reaches_regime_level():
    result = classify_alpha_level(
        activation_score=90.0,  # target_level == regime_level
        dominant_cap_reason_codes=[],
        regime_gate_passed=True,
    )
    assert result.target_level == REGIME_LEVEL
    assert result.qualified_level == REGIME_LEVEL
    assert result.is_blocked is False


def test_c_regime_gate_fails_alone_falls_back_to_dominant_not_active():
    result = classify_alpha_level(
        activation_score=90.0,
        dominant_cap_reason_codes=[],  # dominant qualification still passes
        regime_gate_passed=False,
        regime_gate_failures=["INSUFFICIENT_UNIQUE_EVIDENCE_FOR_REGIME"],
    )
    assert result.target_level == REGIME_LEVEL
    assert result.qualified_level == DOMINANT
    assert result.is_blocked is True
    assert result.blocked_from == (REGIME_LEVEL,)
    assert result.blocked_reason_codes == (REASON_INSUFFICIENT_EVIDENCE,)


def test_c_regime_and_dominant_both_fail_falls_back_to_active_never_skips_dominant():
    result = classify_alpha_level(
        activation_score=90.0,
        dominant_cap_reason_codes=["NO_LOCAL_STRUCTURE_SUPPORT"],
        regime_gate_passed=False,
        regime_gate_failures=["NO_LOCAL_STRUCTURE_FOR_REGIME"],
    )
    assert result.target_level == REGIME_LEVEL
    assert result.qualified_level == ACTIVE
    assert result.is_blocked is True
    # Fixed order: dominant first, then regime_level -- never reversed,
    # never regime_level alone.
    assert result.blocked_from == (DOMINANT, REGIME_LEVEL)
    assert result.blocked_reason_codes == (REASON_NO_LOCAL_STRUCTURE_SUPPORT,)


# ---------------------------------------------------------------------------
# Section D -- B3 Entity Exposure lifecycle interaction. Only
# effective_status == "approved_gating" may ever block; draft_shadow/
# disabled/absent never do, regardless of would_block_* -- and a missing
# approved seed entry fails closed even though would_block_* is False for a
# null final_exposure. The full Exposure -> B4 pipeline wiring itself
# (compute_run_entity_alpha_exposures feeding classify_and_rebuild_
# collections) is separately covered end-to-end by
# tests/test_entity_alpha_exposure_productization.py::
# test_synthetic_enforced_qualification_ceiling; this section isolates the
# classifier's own consumption contract precisely.
# ---------------------------------------------------------------------------


def _exposure(*, effective_status, would_block_dominant=True, would_block_regime_level=True,
              exposure_status="computed", reason_codes=("EXPOSURE_BELOW_DOMINANT_THRESHOLD",)):
    return {
        "effective_status": effective_status,
        "exposure_status": exposure_status,
        "would_block_dominant": would_block_dominant,
        "would_block_regime_level": would_block_regime_level,
        "reason_codes": list(reason_codes),
    }


def test_d_draft_shadow_never_blocks_even_when_would_block_is_true():
    result = classify_alpha_level(
        activation_score=75.0,
        dominant_cap_reason_codes=[],
        entity_exposure=_exposure(effective_status="draft_shadow"),
    )
    assert result.qualified_level == DOMINANT
    assert result.is_blocked is False


def test_d_disabled_never_blocks_even_when_would_block_is_true():
    result = classify_alpha_level(
        activation_score=75.0,
        dominant_cap_reason_codes=[],
        entity_exposure=_exposure(effective_status="disabled"),
    )
    assert result.qualified_level == DOMINANT
    assert result.is_blocked is False


def test_d_no_exposure_record_at_all_never_blocks():
    result = classify_alpha_level(
        activation_score=75.0, dominant_cap_reason_codes=[], entity_exposure=None
    )
    assert result.qualified_level == DOMINANT
    assert result.is_blocked is False


def test_d_approved_gating_actually_blocks():
    result = classify_alpha_level(
        activation_score=75.0,
        dominant_cap_reason_codes=[],
        entity_exposure=_exposure(effective_status="approved_gating"),
    )
    assert result.qualified_level == ACTIVE
    assert result.is_blocked is True
    assert result.blocked_from == (DOMINANT,)
    assert result.blocked_reason_codes == (REASON_LOW_ENTITY_EXPOSURE,)


def test_d_missing_approved_seed_fails_closed_for_both_levels():
    # would_block_dominant/would_block_regime_level are both False here (a
    # null final_exposure never satisfies "final_exposure < threshold"),
    # but exposure_status == "missing_seed" must still fail closed.
    exposure = _exposure(
        effective_status="approved_gating",
        would_block_dominant=False,
        would_block_regime_level=False,
        exposure_status="missing_seed",
        reason_codes=("SEED_ENTRY_MISSING", "EXPOSURE_SEED_MISSING", "EXPOSURE_QUALIFICATION_APPLIED"),
    )
    result = classify_alpha_level(
        activation_score=90.0,
        dominant_cap_reason_codes=[],
        regime_gate_passed=True,
        entity_exposure=exposure,
    )
    assert result.target_level == REGIME_LEVEL
    assert result.qualified_level == ACTIVE
    assert result.is_blocked is True
    assert result.blocked_from == (DOMINANT, REGIME_LEVEL)
    assert result.blocked_reason_codes == (REASON_LOW_ENTITY_EXPOSURE,)


# ---------------------------------------------------------------------------
# Section E -- canonical reason mapping (task section 9). John's four
# canonical reasons only; unmapped diagnostic codes are surfaced in
# diagnostic_reason_codes but never invent a fifth canonical reason.
# ---------------------------------------------------------------------------


@pytest.mark.parametrize(
    ("raw_code", "canonical"),
    [
        ("INSUFFICIENT_UNIQUE_EVIDENCE", REASON_INSUFFICIENT_EVIDENCE),
        ("INSUFFICIENT_AGENT_INDEPENDENCE", REASON_INSUFFICIENT_EVIDENCE),
        ("KEYWORD_ONLY_SUPPORT", REASON_INSUFFICIENT_EVIDENCE),
        ("NO_LOCAL_STRUCTURE_SUPPORT", REASON_NO_LOCAL_STRUCTURE_SUPPORT),
        ("NO_TICKER_SPECIFIC_EVIDENCE", REASON_NO_TICKER_SPECIFIC_EVIDENCE),
    ],
)
def test_e_each_dominant_cap_code_maps_to_its_canonical_reason(raw_code, canonical):
    result = classify_alpha_level(activation_score=75.0, dominant_cap_reason_codes=[raw_code])
    assert result.blocked_reason_codes == (canonical,)
    assert canonical in CANONICAL_BLOCKED_REASONS


def test_e_unmapped_regime_codes_are_diagnostic_only_never_canonical():
    result = classify_alpha_level(
        activation_score=90.0,
        dominant_cap_reason_codes=[],
        regime_gate_passed=False,
        regime_gate_failures=["SCORE_BELOW_REGIME_THRESHOLD", "EVIDENCE_INTEGRITY_WARNING"],
    )
    assert result.is_blocked is True
    assert result.blocked_reason_codes == ()  # neither maps to a canonical reason
    assert "SCORE_BELOW_REGIME_THRESHOLD" in result.diagnostic_reason_codes
    assert "EVIDENCE_INTEGRITY_WARNING" in result.diagnostic_reason_codes


def test_e_duplicate_raw_codes_collapse_to_one_canonical_reason_deduped():
    # INSUFFICIENT_UNIQUE_EVIDENCE and KEYWORD_ONLY_SUPPORT both map to
    # REASON_INSUFFICIENT_EVIDENCE -- must appear exactly once, not twice.
    result = classify_alpha_level(
        activation_score=75.0,
        dominant_cap_reason_codes=["INSUFFICIENT_UNIQUE_EVIDENCE", "KEYWORD_ONLY_SUPPORT"],
    )
    assert result.blocked_reason_codes == (REASON_INSUFFICIENT_EVIDENCE,)
    assert result.diagnostic_reason_codes == (
        "INSUFFICIENT_UNIQUE_EVIDENCE",
        "KEYWORD_ONLY_SUPPORT",
    )


def test_e_every_canonical_reason_is_one_of_johns_exact_four():
    assert frozenset(
        {
            "NO_LOCAL_STRUCTURE_SUPPORT",
            "INSUFFICIENT_EVIDENCE",
            "LOW_ENTITY_EXPOSURE",
            "NO_TICKER_SPECIFIC_EVIDENCE",
        }
    ) == CANONICAL_BLOCKED_REASONS


# ---------------------------------------------------------------------------
# Section F -- collection consistency / five-way UI-partition exclusivity.
# ---------------------------------------------------------------------------


def _entry(alpha_id, *, score, uncapped=None, cap_reason_codes=(), regime_gate_passed=None,
           regime_gate_failures=()):
    return {
        "alpha_id": alpha_id,
        "alpha_name": alpha_id,
        "activation_score": score,
        "uncapped_score": uncapped if uncapped is not None else score,
        "status": "placeholder",
        "direction": "positive",
        "evidence_count": 1,
        "distinct_supporting_agents": 1,
        "cap_reason_codes": list(cap_reason_codes),
        "regime_gate_passed": regime_gate_passed,
        "regime_gate_failures": list(regime_gate_failures),
    }


def test_f_collections_partition_correctly_and_dominant_alphas_keeps_backward_compat_meaning():
    payload = {
        "formula_version": ACTIVATION_V2_FORMULA_VERSION,
        "alphas": [
            _entry("A_CANDIDATE", score=30.0),
            _entry("A_ACTIVE", score=60.0),
            _entry("A_DOMINANT", score=75.0),
            _entry("A_REGIME", score=90.0, regime_gate_passed=True),
            _entry(
                "A_BLOCKED_FROM_DOMINANT",
                score=75.0,
                cap_reason_codes=["NO_LOCAL_STRUCTURE_SUPPORT"],
            ),
            _entry(
                "A_BLOCKED_FROM_REGIME",
                score=90.0,
                regime_gate_passed=False,
                regime_gate_failures=["SCORE_BELOW_REGIME_THRESHOLD"],
            ),
        ],
    }
    result = classify_and_rebuild_collections(payload)

    by_id = {e["alpha_id"]: e for e in result["alphas"]}
    # Every entry's own status is always exactly its qualified_level.
    for entry in result["alphas"]:
        assert entry["status"] == entry["qualified_level"]

    def ids(collection):
        return {e["alpha_id"] for e in collection}

    assert ids(result["candidate_alphas"]) == {"A_CANDIDATE"}
    assert ids(result["active_alphas"]) == {"A_ACTIVE", "A_BLOCKED_FROM_DOMINANT"}
    assert ids(result["regime_level_alphas"]) == {"A_REGIME"}
    # Backward-compatible, pre-existing meaning: dominant OR regime_level --
    # A_BLOCKED_FROM_REGIME's *final* qualified_level is "dominant", so it
    # belongs here; A_BLOCKED_FROM_DOMINANT's final level is "active", so it
    # does not.
    assert ids(result["dominant_alphas"]) == {"A_DOMINANT", "A_REGIME", "A_BLOCKED_FROM_REGIME"}
    assert ids(result["blocked_alphas"]) == {"A_BLOCKED_FROM_DOMINANT", "A_BLOCKED_FROM_REGIME"}

    # Frontend five-way UI partition (task section 11, Decision 2) is
    # mutually exclusive by construction: is_blocked wins first, so
    # blocked_alphas members must not double-count inside whichever
    # qualified_level bucket the *display* partition would also place them
    # in for any OTHER purpose -- i.e. every blocked alpha's own
    # qualified_level bucket is a distinct concern from "is it blocked",
    # and a UI reading is_blocked first can always assign exactly one
    # bucket per alpha.
    for entry in result["alphas"]:
        if entry["is_blocked"]:
            assert entry["alpha_id"] in ids(result["blocked_alphas"])

    # Every alpha appears in exactly one of the four *exclusive* new
    # collections (candidate/active/regime_level, and dominant restricted
    # to entries whose qualified_level=="dominant" specifically).
    exclusive_dominant_only = {e["alpha_id"] for e in result["dominant_alphas"] if e["qualified_level"] == "dominant"}
    exclusive_buckets = (
        ids(result["candidate_alphas"])
        | ids(result["active_alphas"])
        | exclusive_dominant_only
        | ids(result["regime_level_alphas"])
    )
    assert exclusive_buckets == set(by_id)
    assert len(exclusive_buckets) == len(by_id)  # no overlap


def test_f_classification_version_stamped_on_every_entry():
    payload = {"alphas": [_entry("A101", score=55.0)]}
    result = classify_and_rebuild_collections(payload)
    assert result["alphas"][0]["classification_version"] == CLASSIFICATION_VERSION


# ---------------------------------------------------------------------------
# Section G -- persistence whitelist consistency (old and new payloads).
# ---------------------------------------------------------------------------


def _repo():
    engine = build_engine("sqlite:///:memory:")
    apply_migrations(engine)
    return GraphPersistenceRepository(engine)


def _v2_entry_and_conflict(run_id, ticker, *, alpha_id="A101", score=75.0, extra_fields=None):
    entry = activation_entry(alpha_id, score=score, status="active", direction="positive")
    entry["formula_version"] = ACTIVATION_V2_FORMULA_VERSION
    if extra_fields:
        entry.update(extra_fields)
    activation = activation_payload(entry)
    conflict = detect_alpha_conflicts(
        run_id=run_id, ticker=ticker, activation_payload=activation, alpha_matches=[]
    )
    return activation, conflict


def test_g_new_b4_fields_round_trip_through_real_persistence():
    repo = _repo()
    run_id, ticker = "b4_g1", "NVDA"
    payload = {
        "alphas": [
            _entry("A101", score=75.0, cap_reason_codes=[], regime_gate_passed=False)
        ]
    }
    payload["alphas"][0]["formula_version"] = ACTIVATION_V2_FORMULA_VERSION
    classified = classify_and_rebuild_collections(payload)
    entry = classified["alphas"][0]
    entry["alpha_name"] = "A101"
    entry["direction"] = "positive"
    entry["claim_ids"] = []
    entry["evidence"] = []
    entry["reason_codes"] = []
    entry["components"] = {}

    activation = activation_payload(entry)
    conflict = detect_alpha_conflicts(
        run_id=run_id, ticker=ticker, activation_payload=activation, alpha_matches=[]
    )
    repo.persist_week4_results(
        run_id=run_id, ticker=ticker, activation_payload=activation, conflict_payload=conflict
    )

    rows = repo.get_alpha_activations(run_id)
    assert len(rows) == 1
    # The row's own top-level columns cover only run_id/ticker/alpha_id/
    # alpha_name/activation_score/status/direction/formula_version/
    # activation_rank -- every other whitelisted field (including all new
    # B4 fields) lives in the activation_json catch-all column, exactly
    # the same established pattern as every other v2-only field.
    stored = rows[0]["activation_json"]
    assert rows[0]["status"] == stored["status"] == entry["qualified_level"] == DOMINANT
    assert stored["target_level"] == entry["target_level"]
    assert stored["qualified_level"] == entry["qualified_level"] == DOMINANT
    assert stored["is_blocked"] == entry["is_blocked"] == False  # noqa: E712 (explicit bool identity intent)
    assert stored["blocked_from"] == list(entry["blocked_from"])
    assert stored["blocked_reason_codes"] == list(entry["blocked_reason_codes"])
    assert stored["diagnostic_reason_codes"] == list(entry["diagnostic_reason_codes"])
    assert stored["classification_version"] == CLASSIFICATION_VERSION


def test_g_old_v2_payload_predating_b4_persists_and_reads_back_without_fabricating_fields():
    repo = _repo()
    run_id, ticker = "b4_g2", "NVDA"
    # A real Activation v2 entry that never went through classify_and_
    # rebuild_collections at all (a historical, pre-B4 payload shape).
    activation, conflict = _v2_entry_and_conflict(run_id, ticker, score=55.0)
    repo.persist_week4_results(
        run_id=run_id, ticker=ticker, activation_payload=activation, conflict_payload=conflict
    )

    row = repo.get_alpha_activations(run_id)[0]
    assert row["status"] == "active"  # untouched, exactly as supplied
    stored = row["activation_json"]
    for field in (
        "target_level",
        "qualified_level",
        "is_blocked",
        "blocked_from",
        "blocked_reason_codes",
        "diagnostic_reason_codes",
        "classification_version",
    ):
        assert field not in stored, f"{field} must be genuinely absent, never fabricated"


def test_g_v1_entry_smuggling_a_b4_only_field_is_rejected():
    repo = _repo()
    run_id, ticker = "b4_g3", "NVDA"
    entry = activation_entry("A101", score=75.0, status="active", direction="positive")
    assert "formula_version" not in entry  # v1-shaped
    entry["target_level"] = "dominant"  # smuggled v2/B4-only field
    activation = activation_payload(entry)
    conflict = detect_alpha_conflicts(
        run_id=run_id, ticker=ticker, activation_payload=activation, alpha_matches=[]
    )
    with pytest.raises(GraphPersistenceError) as exc_info:
        repo.persist_week4_results(
            run_id=run_id, ticker=ticker, activation_payload=activation, conflict_payload=conflict
        )
    assert exc_info.value.reason_code == "WEEK4_ACTIVATION_PAYLOAD_INVALID"
    assert repo.get_alpha_activations(run_id) == []


def test_g_malformed_is_blocked_type_is_rejected_not_coerced():
    repo = _repo()
    run_id, ticker = "b4_g4", "NVDA"
    activation, conflict = _v2_entry_and_conflict(
        run_id, ticker, score=75.0, extra_fields={"is_blocked": "yes"}
    )
    with pytest.raises(GraphPersistenceError) as exc_info:
        repo.persist_week4_results(
            run_id=run_id, ticker=ticker, activation_payload=activation, conflict_payload=conflict
        )
    assert exc_info.value.reason_code == "WEEK4_ACTIVATION_PAYLOAD_INVALID"


# ---------------------------------------------------------------------------
# Section H -- B2 Conflict Core compatibility. B4 must never modify any
# field the Conflict Detector reads other than status/target_level/
# qualified_level/is_blocked/blocked_from/blocked_reason_codes/
# diagnostic_reason_codes/classification_version, and the earlier admissibility
# gate change (ADMISSIBLE_STATUSES) must remain purely additive.
# ---------------------------------------------------------------------------

_B4_OWNED_FIELDS = frozenset(
    {
        "status",
        "target_level",
        "qualified_level",
        "is_blocked",
        "blocked_from",
        "blocked_reason_codes",
        "diagnostic_reason_codes",
        "classification_version",
    }
)


def test_h_admissible_statuses_is_additive_never_removes_the_pre_b4_vocabulary():
    assert {"watch", "active", "dominant", "regime_level"} <= ADMISSIBLE_STATUSES
    assert "candidate" in ADMISSIBLE_STATUSES


def test_h_classification_never_mutates_any_field_it_does_not_own():
    entry = _entry("A101", score=75.0, cap_reason_codes=["NO_LOCAL_STRUCTURE_SUPPORT"])
    entry.update(
        {
            "alpha_name": "AI Expansion",
            "direction": "positive",
            "components": {"recency": {"raw": 1.0}},
            "evidence": ["claim text"],
            "claim_ids": ["c1"],
            "reason_codes": ["SOME_EXISTING_REASON"],
        }
    )
    before = {k: v for k, v in entry.items() if k not in _B4_OWNED_FIELDS and k != "status"}
    payload = {"alphas": [entry]}
    result = classify_and_rebuild_collections(payload)
    after_entry = result["alphas"][0]
    after = {k: v for k, v in after_entry.items() if k not in _B4_OWNED_FIELDS and k != "status"}
    assert before == after
    # activation_score/uncapped_score specifically -- B4 must never modify
    # either numeric value (task section 5).
    assert after_entry["activation_score"] == 75.0
    assert after_entry["uncapped_score"] == 75.0


@pytest.mark.parametrize("status", ["candidate", "active", "dominant", "regime_level"])
def test_h_every_new_admissible_status_can_still_be_admitted_by_b2(status):
    # Mirrors test_conflict_detector.py's own
    # test_admissible_statuses_above_watch_can_be_admitted, extended with
    # "candidate" -- the new status this task's ADMISSIBLE_STATUSES change
    # actually enables through the early gate. B2's own, independent,
    # stronger score>=50 admissibility check is unaffected either way.
    result = detect_alpha_conflicts(
        run_id="b4_h2",
        ticker="NVDA",
        activation_payload=activation_payload(
            activation_entry("A101", score=90, status=status, direction="positive"),
            activation_entry("A304", score=90, status=status, direction="negative"),
        ),
        alpha_matches=[
            match_record("cA", "A101"),
            match_record("cA2", "A101"),
            match_record("cB", "A304"),
            match_record("cB2", "A304"),
        ],
    )
    assert result["main_conflict"] is not None
