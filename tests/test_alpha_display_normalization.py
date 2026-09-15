"""Alpha-Level Display Normalization (Step 7).

Presentation/audit normalization only -- ``alpha_level_classifier`` (B4)
remains the sole activation authority. Every test here either builds a
minimal already-classified entry directly (never recomputing activation) or
reads real, already-persisted Step-6-qualified six-ticker data. Zero
Provider calls, zero TradingAgents calls.
"""

from __future__ import annotations

import ast
import json
from pathlib import Path

import pytest

from comqutor_alpha.alpha_library.alpha_loader import load_alpha_taxonomy
from comqutor_alpha.conflict_engine.conflict_admissibility import (
    ALPHA_SCORE_THRESHOLD,
    MIN_SUPPORTING_EVIDENCE_PER_SIDE,
    MIN_TICKER_SPECIFIC_SUPPORT_PER_SIDE,
)
from comqutor_alpha.graph_engine.activation_scorer_v2 import score_alpha_activations_v2
from comqutor_alpha.graph_engine.alpha_display_normalizer import (
    ALPHA_DISPLAY_NORMALIZATION_VERSION,
    DISPLAY_LEVELS,
    UNKNOWN_DISPLAY_STATE,
    normalize_alpha_display_state,
    normalize_alpha_display_states,
)
from comqutor_alpha.graph_engine.alpha_level_classifier import (
    ACTIVE,
    ACTIVE_THRESHOLD,
    CANDIDATE,
    CAPPED_ACTIVE,
    DOMINANT,
    DOMINANT_THRESHOLD,
    REGIME_LEVEL,
    REGIME_LEVEL_THRESHOLD,
    classify_alpha_level,
    classify_and_rebuild_collections,
)

REPO_ROOT = Path(__file__).resolve().parents[1]
TICKERS = ("NVDA", "QQQ", "MSFT", "SNDK", "TSM", "AMD")
TAXONOMY = load_alpha_taxonomy()


def _classified_entry(**kwargs) -> dict:
    """A minimal Activation v2 entry, already run through classify_alpha_level
    -- exactly the shape normalize_alpha_display_state consumes."""
    activation_score = kwargs.pop("activation_score")
    classification = classify_alpha_level(activation_score=activation_score, **kwargs)
    entry = {"alpha_id": "A101", "activation_score": activation_score}
    entry.update(classification.to_dict())
    return entry


# ---------------------------------------------------------------------------
# Case 1-8, 15-17: direct entry-level cases
# ---------------------------------------------------------------------------


def test_case1_active_alpha_normalizes_to_active():
    entry = _classified_entry(activation_score=60.0, uncapped_score=60.0)
    result = normalize_alpha_display_state(entry)
    assert result["display_level"] == ACTIVE
    assert result["authoritative_level"] == ACTIVE
    assert result["blocked"] is False


def test_case2_dominant_alpha_normalizes_to_dominant():
    entry = _classified_entry(activation_score=75.0, uncapped_score=75.0)
    result = normalize_alpha_display_state(entry)
    assert result["display_level"] == DOMINANT
    assert result["authoritative_level"] == DOMINANT
    assert result["blocked"] is False


def test_case3_regime_alpha_normalizes_to_regime_level():
    entry = _classified_entry(
        activation_score=90.0, uncapped_score=90.0, regime_gate_passed=True
    )
    result = normalize_alpha_display_state(entry)
    assert result["display_level"] == REGIME_LEVEL
    assert result["authoritative_level"] == REGIME_LEVEL
    assert result["blocked"] is False


def test_case4_cap_constrained_active_normalizes_to_capped_active_score_unchanged():
    entry = _classified_entry(
        activation_score=65.0,
        uncapped_score=88.0,
        dominant_cap_reason_codes=["NO_TICKER_SPECIFIC_EVIDENCE"],
    )
    result = normalize_alpha_display_state(entry)
    assert result["display_level"] == CAPPED_ACTIVE
    # B4's authoritative qualified_level is still exactly "active" -- capped_active
    # is a display-only refinement, never a fifth authoritative level.
    assert result["authoritative_level"] == ACTIVE
    # Underlying activation_score is untouched by normalization.
    assert result["activation_score"] == 65.0 == entry["activation_score"]


def test_case5_blocked_alpha_exposes_blocked_true_and_preserves_reason_codes():
    entry = _classified_entry(
        activation_score=60.0,
        uncapped_score=95.0,
        dominant_cap_reason_codes=["INSUFFICIENT_UNIQUE_EVIDENCE"],
        regime_gate_passed=False,
        regime_gate_failures=["SCORE_BELOW_REGIME_THRESHOLD"],
    )
    # cap_reason_codes is activation_scorer_v2's own raw field (separate from
    # classify_alpha_level's own dict) -- present alongside it on the real
    # pipeline's entry after classify_and_rebuild_collections runs.
    entry["cap_reason_codes"] = ["INSUFFICIENT_UNIQUE_EVIDENCE"]
    result = normalize_alpha_display_state(entry)
    assert result["blocked"] is True
    assert "INSUFFICIENT_EVIDENCE" in result["blocked_reason_codes"]
    assert result["cap_reason_codes"] == ["INSUFFICIENT_UNIQUE_EVIDENCE"]


def test_case6_candidate_alpha_never_shows_candidate_active():
    """No authoritative existing definition for a state distinct from plain
    "candidate" was found anywhere in this codebase (see module docstring
    and tests/test_b4_activation_level_alignment.py::
    test_i_candidate_shows_plain_candidate_no_authoritative_candidate_active_definition).
    display_level must therefore never be "candidate_active" -- only plain
    "candidate"."""
    entry = _classified_entry(activation_score=25.0, uncapped_score=25.0)
    result = normalize_alpha_display_state(entry)
    assert result["display_level"] == CANDIDATE
    assert result["display_level"] != "candidate_active"
    assert "candidate_active" not in DISPLAY_LEVELS


def test_case6b_a301_style_active_gated_alpha_displays_as_candidate_not_active():
    """v0.1.3 QA Closure, Item 4 (A301 trace): end-to-end through the REAL
    classify_alpha_level (Section C's fix) into normalize_alpha_display_state,
    proving the display-normalization layer has no independent bug of its
    own -- it is a pure relabel of whatever the classifier already decided.
    A score of 55 clears ACTIVE_THRESHOLD (50) on its own, but with BOTH
    NO_TICKER_SPECIFIC_EVIDENCE and NO_LOCAL_STRUCTURE_SUPPORT present (John's
    exact A301 counter-example), the classifier now demotes to
    qualified_level=candidate/is_blocked=True/blocked_from=(active,) -- and
    display_level must follow it down to plain "candidate", never "active"
    and never "capped_active" (capped_active is reserved for an active
    Alpha blocked down from dominant, not this case)."""
    entry = _classified_entry(
        activation_score=55.0,
        uncapped_score=55.0,
        dominant_cap_reason_codes=["NO_TICKER_SPECIFIC_EVIDENCE", "NO_LOCAL_STRUCTURE_SUPPORT"],
    )
    assert entry["qualified_level"] == CANDIDATE
    assert entry["is_blocked"] is True
    assert ACTIVE in entry["blocked_from"]
    result = normalize_alpha_display_state(entry)
    assert result["display_level"] == CANDIDATE
    assert result["display_level"] != ACTIVE
    assert result["display_level"] != CAPPED_ACTIVE
    assert result["blocked"] is True
    assert result["authoritative_level"] == CANDIDATE


def test_case7_zero_qualifying_evidence_cannot_become_active_or_higher():
    entry = _classified_entry(activation_score=0.0, uncapped_score=0.0)
    result = normalize_alpha_display_state(entry)
    assert result["display_level"] == CANDIDATE
    assert result["display_level"] not in (ACTIVE, CAPPED_ACTIVE, DOMINANT, REGIME_LEVEL)


def test_case8_multiple_cap_reasons_all_preserved():
    entry = _classified_entry(
        activation_score=60.0,
        uncapped_score=95.0,
        dominant_cap_reason_codes=["NO_TICKER_SPECIFIC_EVIDENCE"],
        regime_gate_passed=False,
        regime_gate_failures=["SCORE_BELOW_REGIME_THRESHOLD"],
    )
    result = normalize_alpha_display_state(entry)
    assert result["display_level"] == CAPPED_ACTIVE
    assert set(result["blocked_reason_codes"]) == {"NO_TICKER_SPECIFIC_EVIDENCE"}
    assert entry["blocked_from"] == [DOMINANT, REGIME_LEVEL]


def test_case15_activation_score_unchanged_before_vs_after_normalization():
    for score in (0.0, 25.0, 50.0, 65.0, 70.0, 86.0, 99.0):
        entry = _classified_entry(activation_score=score, uncapped_score=score)
        result = normalize_alpha_display_state(entry)
        assert result["activation_score"] == score == entry["activation_score"]


def test_case16_legacy_artifact_fields_remain_readable_and_untouched():
    entry = _classified_entry(activation_score=75.0, uncapped_score=75.0)
    before = dict(entry)
    normalize_alpha_display_state(entry)
    assert entry == before  # normalization never mutates its input
    assert "qualified_level" in entry
    assert "activation_level" in entry
    assert "is_blocked" in entry


@pytest.mark.parametrize(
    "malformed_entry",
    [
        {},
        {"alpha_id": "A1", "activation_score": 90.0},  # missing classification fields entirely
        {"alpha_id": "A1", "activation_score": 90.0, "qualified_level": "regime_level", "activation_level": "regime_level", "is_blocked": "not_a_bool"},
        {"alpha_id": "A1", "activation_score": "not_a_number", "qualified_level": "active", "activation_level": "active", "is_blocked": False},
        {"alpha_id": "A1", "activation_score": 90.0, "qualified_level": "made_up_level", "activation_level": "made_up_level", "is_blocked": False},
    ],
)
def test_case17_malformed_authoritative_state_fails_conservatively(malformed_entry):
    result = normalize_alpha_display_state(malformed_entry)
    assert result["display_level"] == UNKNOWN_DISPLAY_STATE
    assert result["display_level"] not in (ACTIVE, CAPPED_ACTIVE, DOMINANT, REGIME_LEVEL)
    assert result["ambiguous"] is True


# ---------------------------------------------------------------------------
# Case 9: normalizer never reconsiders evidence (Step-6-aware upstream only)
# ---------------------------------------------------------------------------


def test_case9_normalizer_signature_never_touches_evidence_or_claims():
    """The normalizer's only input is an already-classified entry -- it has
    no parameter for claims/evidence/alpha_matches/structured_records, and
    an entry with zero evidence-shaped fields at all still normalizes
    correctly from activation_score/qualified_level/activation_level alone."""
    import inspect

    sig = inspect.signature(normalize_alpha_display_state)
    assert list(sig.parameters) == ["entry"]
    entry = _classified_entry(activation_score=55.0, uncapped_score=55.0)
    # Strip anything evidence-shaped that classify_alpha_level's own dict
    # never even includes in the first place -- proving no such field is
    # read even if present.
    entry["evidence"] = ["should never be read"]
    entry["claim_ids"] = ["should never be read"]
    result = normalize_alpha_display_state(entry)
    assert result["display_level"] == ACTIVE


# ---------------------------------------------------------------------------
# Case 10-12: B4 thresholds unchanged
# ---------------------------------------------------------------------------


def test_case10_active_threshold_exactly_50():
    assert ACTIVE_THRESHOLD == 50.0


def test_case11_dominant_threshold_exactly_70():
    assert DOMINANT_THRESHOLD == 70.0


def test_case12_regime_threshold_exactly_86():
    assert REGIME_LEVEL_THRESHOLD == 86.0


# ---------------------------------------------------------------------------
# Case 13-14: B1/B2 untouched by this module
# ---------------------------------------------------------------------------


def test_case13_display_normalizer_never_imports_evidence_stance_b1():
    tree = ast.parse((REPO_ROOT / "comqutor_alpha/graph_engine/alpha_display_normalizer.py").read_text())
    for node in ast.walk(tree):
        if isinstance(node, ast.ImportFrom) and node.module:
            assert "evidence_stance" not in node.module
        if isinstance(node, ast.Import):
            for alias in node.names:
                assert "evidence_stance" not in alias.name


def test_case14_b2_threshold_constants_unchanged_and_untouched_by_this_module():
    assert ALPHA_SCORE_THRESHOLD == 50.0
    assert MIN_SUPPORTING_EVIDENCE_PER_SIDE == 2
    assert MIN_TICKER_SPECIFIC_SUPPORT_PER_SIDE == 1
    tree = ast.parse((REPO_ROOT / "comqutor_alpha/conflict_engine/conflict_detector.py").read_text())
    for node in ast.walk(tree):
        if isinstance(node, ast.ImportFrom) and node.module:
            assert "alpha_display_normalizer" not in node.module


# ---------------------------------------------------------------------------
# Case 18: all 60 six-ticker Alpha records normalize or are explicitly
# reported ambiguous -- real, persisted, Step-6-qualified data.
# ---------------------------------------------------------------------------


@pytest.mark.parametrize("ticker", TICKERS)
def test_case18_six_ticker_real_data_normalizes_without_exception(ticker):
    run_dir = REPO_ROOT / "outputs" / "runs" / f"_step5a_coverage_{ticker.lower()}"
    alpha_matches_payload = json.loads((run_dir / "alpha_matches.json").read_text())
    activation_payload = score_alpha_activations_v2(
        alpha_matches_payload, ticker=ticker, taxonomy=TAXONOMY
    )
    classify_and_rebuild_collections(activation_payload)
    results = normalize_alpha_display_states(activation_payload["alphas"])
    assert len(results) == 10
    for result in results:
        assert result["display_level"] in (*DISPLAY_LEVELS, UNKNOWN_DISPLAY_STATE)
        assert result["normalization_contract_version"] == ALPHA_DISPLAY_NORMALIZATION_VERSION
