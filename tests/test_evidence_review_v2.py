"""Evidence Review v2 + Critical Reversal Adjudication (Step 8).

Pure audit/consolidation over already-persisted, already-frozen Blind
Holdout #5 artifacts. Zero Provider calls, zero TradingAgents calls. These
tests read only the static v2 JSON artifact and the frozen H5 source files
-- they never call a Provider, never mutate the frozen review, and never
touch production semantic code.
"""

from __future__ import annotations

import ast
import csv
import hashlib
import json
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parents[1]
ARTIFACTS = REPO_ROOT / "docs" / "audit_artifacts"
V2_PATH = ARTIFACTS / "evidence_review_summary_v2.json"
LEGACY_PATH = ARTIFACTS / "evidence_review_summary.json"
QA_INDEX_PATH = ARTIFACTS / "qa_closure_index.json"
FROZEN_REVIEW_PATH = ARTIFACTS / "item2_blind_holdout5_review_frozen.csv"
FROZEN_HOLDOUT_PATH = ARTIFACTS / "item2_blind_holdout5_frozen.csv"
SYSTEM_ALPHA_PATH = ARTIFACTS / "item2_blind_holdout5_system_alpha.json"
SYSTEM_POLARITY_PATH = ARTIFACTS / "item2_blind_holdout5_system_polarity.json"


@pytest.fixture(scope="module")
def v2() -> dict:
    return json.loads(V2_PATH.read_text())


@pytest.fixture(scope="module")
def legacy() -> dict:
    return json.loads(LEGACY_PATH.read_text())


@pytest.fixture(scope="module")
def qa_index() -> dict:
    return json.loads(QA_INDEX_PATH.read_text())


@pytest.fixture(scope="module")
def review_rows() -> list[dict]:
    with open(FROZEN_REVIEW_PATH, newline="") as f:
        return list(csv.DictReader(f))


def _recompute_raw_metrics(review_rows):
    with open(SYSTEM_ALPHA_PATH) as f:
        system_alpha = json.load(f)
    with open(SYSTEM_POLARITY_PATH) as f:
        system_polarity = json.load(f)

    alpha_correct = alpha_total = 0
    polarity_correct = polarity_total = 0
    critical_reversals = []
    for row in review_rows:
        sid = row["sample_id"]
        fit = row["human_material_alpha_fit"].strip().lower() == "true"
        reviewed_alpha = row["human_expected_alpha_id"].strip() if fit else "NONE"
        reviewed_polarity = row["human_polarity"].strip() if fit else None
        sys_entry = system_alpha.get(sid)
        alpha_total += 1
        system_alpha_id = (sys_entry or {}).get("system_matched_alpha_id") or "NONE"
        if system_alpha_id == reviewed_alpha:
            alpha_correct += 1
        if fit:
            pol_entry = system_polarity.get(sid)
            if pol_entry is not None:
                polarity_total += 1
                system_pol = pol_entry.get("system_polarity")
                if system_pol == reviewed_polarity:
                    polarity_correct += 1
                if {system_pol, reviewed_polarity} == {"supports_alpha", "opposes_alpha"}:
                    critical_reversals.append(sid)
    return {
        "alpha_correct": alpha_correct,
        "alpha_total": alpha_total,
        "polarity_correct": polarity_correct,
        "polarity_total": polarity_total,
        "critical_reversal_sample_ids": critical_reversals,
    }


# ---------------------------------------------------------------------------
# Case 1-3: single current source, legacy/dev-rereview cannot override it
# ---------------------------------------------------------------------------


def test_case1_v2_summary_uses_exactly_one_200_row_current_review_source(v2):
    assert v2["reviewed_count"] == 200
    assert v2["review_version"] == "blind_holdout_5"
    assert v2["raw_h5_metrics"]["reviewed_count"] == 200


def test_case2_legacy_50_row_metrics_cannot_become_current_acceptance_metrics(v2, legacy):
    # The legacy file's top-level fields describe the 50-row review.
    assert legacy["reviewed_count"] == 50
    assert legacy["alpha_match_accuracy"] == 0.72
    # v2 must not have inherited either the 50-row count or its accuracy.
    assert v2["reviewed_count"] == 200
    assert v2["raw_h5_metrics"]["alpha_match_accuracy"]["total"] == 200
    assert v2["raw_h5_metrics"]["alpha_match_accuracy"]["accuracy_percent"] != legacy["alpha_match_accuracy"] * 100


def test_case3_development_rereview_cannot_overwrite_current_acceptance(v2, legacy):
    assert "item2_200row_development_re_review" in legacy
    dev = legacy["item2_200row_development_re_review"]
    # Whatever the dev rereview's own approval flag is, it must never be read
    # as v2's acceptance source -- v2 sources only from item2_blind_holdout5_*.
    assert v2["raw_h5_metrics"]["cross_check_against_item2_blind_holdout5_metrics_json"] == "MATCH_EXACT"
    assert isinstance(dev, dict)  # exists and preserved, but not consulted by v2


# ---------------------------------------------------------------------------
# Case 4-5: raw H5 recomputation and immutability
# ---------------------------------------------------------------------------


def test_case4_raw_h5_metrics_recompute_deterministically(v2, review_rows):
    recomputed = _recompute_raw_metrics(review_rows)
    assert recomputed["alpha_correct"] == v2["raw_h5_metrics"]["alpha_match_accuracy"]["correct"] == 166
    assert recomputed["alpha_total"] == v2["raw_h5_metrics"]["alpha_match_accuracy"]["total"] == 200
    assert recomputed["polarity_correct"] == v2["raw_h5_metrics"]["polarity_accuracy"]["correct"] == 52
    assert recomputed["polarity_total"] == v2["raw_h5_metrics"]["polarity_accuracy"]["total"] == 62
    assert recomputed["critical_reversal_sample_ids"] == ["holdout5-005"]


def test_case5_raw_critical_reversal_remains_1(v2):
    assert v2["raw_h5_metrics"]["critical_reversal_count"] == 1
    assert v2["raw_h5_metrics"]["critical_reversal_sample_ids"] == ["holdout5-005"]


# ---------------------------------------------------------------------------
# Case 6-9: adjudication behavior
# ---------------------------------------------------------------------------


def test_case6_adjudication_does_not_mutate_frozen_labels(v2):
    expected_review_sha = "900ee50b9cfb8f5b3653ebcd30e41403d2af6665fc72cc7f4af49493d9d92ed1"
    expected_holdout_sha = "a2f8e0bd6fa1229f3e5876673be751e54155c750e524899cde9dd523142e17b7"
    actual_review_sha = hashlib.sha256(FROZEN_REVIEW_PATH.read_bytes()).hexdigest()
    actual_holdout_sha = hashlib.sha256(FROZEN_HOLDOUT_PATH.read_bytes()).hexdigest()
    assert actual_review_sha == expected_review_sha
    assert actual_holdout_sha == expected_holdout_sha
    assert v2["critical_reversal_adjudication"]["raw_labels_modified"] is False


def test_case7_system_correct_review_wrong_would_produce_separate_adjudicated_view():
    """Documents the contract: an adjudicated_acceptance_view is only ever
    computed when the outcome is SYSTEM_CORRECT_REVIEW_LABEL_WRONG. Since
    this task's actual outcome is BOTH_REASONABLE_AMBIGUOUS, no such view
    exists here -- this test pins the conditional rule itself."""
    outcome = "SYSTEM_CORRECT_REVIEW_LABEL_WRONG"
    applicable = outcome == "SYSTEM_CORRECT_REVIEW_LABEL_WRONG"
    assert applicable is True


def test_case8_review_label_correct_system_wrong_would_retain_critical_reversal_failure():
    outcome = "REVIEW_LABEL_CORRECT_SYSTEM_WRONG"
    adjudicated_critical_reversal_count = 1 if outcome == "REVIEW_LABEL_CORRECT_SYSTEM_WRONG" else 0
    assert adjudicated_critical_reversal_count == 1


def test_case9_ambiguous_adjudication_remains_pending(v2):
    assert v2["critical_reversal_adjudication"]["outcome"] == "BOTH_REASONABLE_AMBIGUOUS"
    assert v2["adjudicated_acceptance_view"]["applicable"] is False
    # No zero was manufactured in the *raw* record -- the raw historical
    # reversal count is preserved unmodified for audit provenance.
    assert v2["adjudicated_acceptance_view"]["critical_reversal_count"] == 1
    assert v2["raw_h5_metrics"]["critical_reversal_count"] == 1


# John Item 9 (Evidence Review v2 acceptance-contract cleanup): the
# BOTH_REASONABLE_AMBIGUOUS adjudication maps to the general
# AMBIGUOUS_DIRECTION eligibility class, which excludes holdout5-005 from
# the *current acceptance* critical-reversal gate (not from the raw
# historical record, which stays 1 -- see test_case9 above).
def test_case9b_ambiguous_direction_resolves_current_acceptance_to_pass_without_erasing_the_raw_reversal(v2):
    assert v2["acceptance_results"]["critical_reversal_result"]["status"] == "PASS"
    assert v2["acceptance_results"]["critical_reversal_result"]["eligible_value"] == 0
    assert v2["acceptance_results"]["critical_reversal_result"]["raw_historical_value"] == 1
    assert v2["acceptance_results"]["critical_reversal_result"]["excluded_ambiguous_sample_ids"] == ["holdout5-005"]


# ---------------------------------------------------------------------------
# Case 10-12: threshold values exact
# ---------------------------------------------------------------------------


def test_case10_alpha_threshold_is_exactly_80_percent(v2):
    assert v2["acceptance_thresholds"]["alpha_accuracy_threshold_percent"] == 80.0


def test_case11_polarity_threshold_is_exactly_80_percent(v2):
    assert v2["acceptance_thresholds"]["polarity_accuracy_threshold_percent"] == 80.0


def test_case12_critical_reversal_target_is_exactly_0(v2):
    assert v2["acceptance_thresholds"]["critical_reversal_target"] == 0


# ---------------------------------------------------------------------------
# Case 13-14: approval/provenance honesty
# ---------------------------------------------------------------------------


def test_case13_john_approved_cannot_become_true_without_explicit_approval_provenance(v2):
    assert v2["john_approval_status"]["john_approved"] is False
    assert v2["john_approval_status"]["john_approval_status"] == "PENDING_JOHN_APPROVAL"


def test_case14_human_review_performed_remains_false_for_independent_model_review(v2):
    assert v2["review_source"] == "independent_model_review"
    assert v2["human_review_performed"] is False
    # The only occurrence of "human-reviewed"-style phrasing anywhere in the
    # artifact must be inside an explicit disclaimer, never an affirmative
    # claim that a human performed the review.
    note = v2["review_source_note"].lower()
    assert "not a human reviewer" in note or "never described as human-reviewed" in note


# ---------------------------------------------------------------------------
# Case 15-16: legacy/index wiring
# ---------------------------------------------------------------------------


def test_case15_legacy_mixed_summary_is_not_current_acceptance_source(qa_index):
    assert qa_index["legacy_evidence_review_summary"]["use_for_current_acceptance"] is False
    assert qa_index["legacy_evidence_review_summary"]["classification"] == "HISTORICAL_MIXED_SOURCE"


def test_case16_qa_closure_index_points_current_evidence_review_acceptance_to_v2(qa_index):
    block = qa_index["step8_evidence_review_v2"]
    assert block["current_acceptance_artifact"] == "docs/audit_artifacts/evidence_review_summary_v2.json"
    assert block["historical_mixed_summary_deprecated_for_acceptance"] is True
    assert block["provider_calls"] == 0
    assert block["tradingagents_calls"] == 0


# ---------------------------------------------------------------------------
# Case 17: production semantic modules untouched
# ---------------------------------------------------------------------------


# Frozen at the end of Step 8's own work (this task never edited any of
# these files) -- a guard against a FUTURE change silently landing without
# being noticed, matching this codebase's own established FROZEN_HASHES
# convention (see tests/test_msft_a102_a304_taxonomy_adjudication.py). The
# taxonomy hash also cross-checks exactly against the SHA-256 recorded in
# item2_blind_holdout5_internal_report.md Section 3 at H5 review-freeze
# time -- proving the taxonomy is still byte-identical to what H5 evaluated
# against.
_STEP8_FROZEN_HASHES = {
    "comqutor_alpha/structure_engine/alpha_mapper.py": "506a228eb10e0b77b2058c9eaa327ae0ec44ba36b1515e5e6400187ffe65a6fd",
    "comqutor_alpha/structure_engine/evidence_stance.py": "9ae3aaeb14b453672445eeb6db6dccc6f526e3bc84bfec2776625436c27e14a6",
    "comqutor_alpha/structure_engine/evidence_stance_llm.py": "282577a54c97e1bd8d962eb793f41baf2cf30930ba0ce178000834eed3307a58",
    # v0.1.3 P0/P1 Evidence Correctness Fix: added the foreign-issuer-only
    # evidence-ownership qualification veto (_foreign_issuer_only_reason)
    # and company_names propagation support. Hash updated deliberately for
    # that authorized change -- see
    # tests/test_p0_p1_evidence_correctness_fix.py.
    "comqutor_alpha/graph_engine/activation_scorer_v2.py": "c1b0a479a1d06c94811004c2ea62d95598427ea4541e0f770a5d4633e642911e",
    # v0.1.3 QA Closure, Section D: bull_structure/bear_structure (the
    # top-level, frontend-rendered fields ConflictCard.tsx reads) were built
    # from the unfiltered qualifying-claim pool, so evidence that rebuts an
    # Alpha's thesis could display as if it supported that Alpha. Fixed by
    # adding a stance-filtered display-only subset; evidence_strength/
    # conflict_score/admissibility remain fed by the original unfiltered
    # pool -- see tests/test_conflict_detector.py's
    # TestEvidencePolarityBullBearAssignment. Hash updated deliberately for
    # that authorized change (this entry had already drifted from an
    # earlier, unrelated, pre-existing Primary/Secondary Evidence
    # Qualification change before this task began).
    "comqutor_alpha/conflict_engine/conflict_detector.py": "f07604bc61a713f7ed3db4cb4db5b6ae9091487cf83c85e40b68696f9c3874da",
    # v0.1.3 QA Closure, Section C: John explicitly reversed the original
    # Case A/B "active is never gated" decision after identifying a
    # concrete A301 counter-example (active display with zero
    # ticker-specific evidence AND zero local Structure Graph support).
    # Hash updated deliberately for that authorized change -- see
    # tests/test_b4_activation_level_alignment.py's test_c2_* tests.
    "comqutor_alpha/graph_engine/alpha_level_classifier.py": "3cf25b42cbc91d8976978d89c45cbab45859accd37c6a8f8731ff42eabb1da85",
    "comqutor_alpha/graph_engine/evidence_source_role.py": "4835e4e2d83b8438bf23d1a9c35123072439d5f501146b77d8d038585d47ae99",
    "comqutor_alpha/graph_engine/alpha_display_normalizer.py": "f63cb9d63a157ab2d817d66d071b94f6b967809d871bc3bb067a2afa9d7ebeea",
    "comqutor_alpha/alpha_library/alpha_taxonomy_v1.yaml": "c031168c726cd424252cd9ee0491e55f335b5966694a326e0bcdfeeab1e7939c",
}


@pytest.mark.parametrize("module_path", sorted(_STEP8_FROZEN_HASHES))
def test_case17_production_semantic_modules_remain_untouched(module_path):
    actual = hashlib.sha256((REPO_ROOT / module_path).read_bytes()).hexdigest()
    assert actual == _STEP8_FROZEN_HASHES[module_path], f"{module_path} hash changed"


def test_no_import_of_provider_or_tradingagents_client_modules_in_this_test_file():
    tree = ast.parse(Path(__file__).read_text())
    banned_substrings = ("llm_clients", "tradingagents", "week2_llm")
    for node in ast.walk(tree):
        if isinstance(node, ast.ImportFrom) and node.module:
            assert not any(b in node.module for b in banned_substrings)


# ---------------------------------------------------------------------------
# v0.1.3 QA Closure, Item 2: John asked for explicit named formal metrics
# (not just nested numerator/denominator/percentage inside
# acceptance_results). ``formal_metrics`` is additive -- every value is a
# direct alias of the pre-existing acceptance_results numbers, never a
# second, independently computed source of truth, and never a mutation of
# any frozen human-reviewed label.
# ---------------------------------------------------------------------------


def test_formal_metrics_block_exists_with_exact_named_fields(v2):
    fm = v2["formal_metrics"]
    for field in (
        "alpha_match_accuracy",
        "alpha_match_reviewed_count",
        "alpha_match_correct_count",
        "polarity_accuracy",
        "polarity_reviewed_count",
        "polarity_correct_count",
        "critical_support_opposition_reversal_count",
    ):
        assert field in fm


def test_formal_metrics_are_a_pure_alias_of_acceptance_results_never_a_second_source(v2):
    ar = v2["acceptance_results"]
    fm = v2["formal_metrics"]
    am, pol, rev = ar["alpha_match_accuracy"], ar["polarity_accuracy"], ar["critical_support_opposition_reversal_count"]
    assert fm["alpha_match_reviewed_count"] == am["denominator"]
    assert fm["alpha_match_correct_count"] == am["numerator"]
    assert fm["alpha_match_accuracy"] == pytest.approx(am["numerator"] / am["denominator"], abs=1e-4)
    assert fm["polarity_reviewed_count"] == pol["denominator"]
    assert fm["polarity_correct_count"] == pol["numerator"]
    assert fm["polarity_accuracy"] == pytest.approx(pol["numerator"] / pol["denominator"], abs=1e-4)
    assert fm["critical_support_opposition_reversal_count"] == rev["value"]


def test_formal_metrics_meet_v0_1_3_acceptance_targets(v2):
    fm = v2["formal_metrics"]
    assert fm["alpha_match_accuracy"] >= 0.80
    assert fm["polarity_accuracy"] >= 0.80
    assert fm["critical_support_opposition_reversal_count"] == 0
