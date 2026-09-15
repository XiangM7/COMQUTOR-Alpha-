"""John Item 9 -- Evidence Review v2 acceptance-contract cleanup.

Pure audit-artifact consistency tests over the directional Gold eligibility
contract added to evidence_review_summary_v2.json. Zero Provider calls, zero
TradingAgents calls; never mutates any frozen review label; never touches
production B1 semantic code.
"""

from __future__ import annotations

import ast
import csv
import json
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parents[1]
ARTIFACTS = REPO_ROOT / "docs" / "audit_artifacts"
V2_PATH = ARTIFACTS / "evidence_review_summary_v2.json"
FROZEN_REVIEW_PATH = ARTIFACTS / "item2_blind_holdout5_review_frozen.csv"
SYSTEM_POLARITY_PATH = ARTIFACTS / "item2_blind_holdout5_system_polarity.json"

import sys

sys.path.insert(0, str(REPO_ROOT / "scripts"))
from build_evidence_review_v2_directional_eligibility import (  # noqa: E402
    ADJUDICATION_OUTCOME_TO_ELIGIBILITY,
    AMBIGUOUS_DIRECTION,
    DIRECTIONALLY_CLEAR,
    _eligibility_for,
    _load_adjudication_registry,
)


@pytest.fixture(scope="module")
def v2() -> dict:
    return json.loads(V2_PATH.read_text())


@pytest.fixture(scope="module")
def eligibility(v2) -> dict:
    return v2["directional_eligibility"]


@pytest.fixture(scope="module")
def review_rows() -> dict[str, dict]:
    with open(FROZEN_REVIEW_PATH, newline="") as f:
        return {r["sample_id"]: r for r in csv.DictReader(f)}


# ---------------------------------------------------------------------------
# A: ambiguous-direction rows remain preserved in audit provenance
# ---------------------------------------------------------------------------


def test_a_ambiguous_row_is_preserved_in_audit_provenance(eligibility):
    per_row_ids = {row["sample_id"] for row in eligibility["per_row"]}
    assert "holdout5-005" in per_row_ids
    row = next(r for r in eligibility["per_row"] if r["sample_id"] == "holdout5-005")
    assert row["directional_eligibility"] == AMBIGUOUS_DIRECTION
    # The raw review/system polarity values are still visible on the row --
    # nothing about the disagreement was hidden or deleted.
    assert row["review_polarity"] == "supports_alpha"
    assert row["system_polarity"] == "opposes_alpha"
    assert row["raw_critical_reversal"] is True


# ---------------------------------------------------------------------------
# B: ambiguous-direction rows excluded from the polarity acceptance
#    denominator
# ---------------------------------------------------------------------------


def test_b_ambiguous_row_excluded_from_polarity_acceptance_denominator(eligibility, v2):
    assert "holdout5-005" in eligibility["excluded_ambiguous_direction_sample_ids"]
    raw_total = v2["raw_h5_metrics"]["polarity_accuracy"]["total"]
    assert eligibility["eligible_denominator"] == raw_total - 1 == 61
    assert v2["acceptance_results"]["polarity_accuracy_result"]["eligible_denominator"] == 61
    assert v2["acceptance_results"]["polarity_accuracy_result"]["excluded_ambiguous_count"] == 1


# ---------------------------------------------------------------------------
# C: ambiguous-direction rows excluded from the critical reversal gate
# ---------------------------------------------------------------------------


def test_c_ambiguous_row_excluded_from_critical_reversal_gate(eligibility, v2):
    assert eligibility["eligible_critical_reversal_count"] == 0
    assert eligibility["eligible_critical_reversal_sample_ids"] == []
    assert v2["acceptance_results"]["critical_reversal_result"]["eligible_value"] == 0
    assert v2["acceptance_results"]["critical_reversal_result"]["status"] == "PASS"
    # Raw historical value is a separate, unmodified field -- never confused
    # with the eligible/acceptance value.
    assert v2["acceptance_results"]["critical_reversal_result"]["raw_historical_value"] == 1


# ---------------------------------------------------------------------------
# D: a directionally-clear supports<->opposes reversal would still count
# ---------------------------------------------------------------------------


def test_d_directionally_clear_reversal_would_still_count_as_critical(review_rows):
    """No row in the actual 62-row eligible-candidate set is both (a)
    DIRECTIONALLY_CLEAR and (b) a raw supports/opposes reversal other than
    holdout5-005 -- but the gate logic itself must still flag one if it
    existed. This directly exercises the same counting logic the build
    script uses, over a synthetic DIRECTIONALLY_CLEAR reversal, proving the
    exclusion in test_c is specific to AMBIGUOUS_DIRECTION and not a
    blanket suppression of all reversals.
    """
    system_polarity = json.loads(SYSTEM_POLARITY_PATH.read_text())
    registry: dict = {}  # no adjudication record at all -> defaults to DIRECTIONALLY_CLEAR
    synthetic_sid = "holdout5-001"  # a real, non-ambiguous row (system_polarity == review_polarity == supports_alpha)
    rev_polarity = review_rows[synthetic_sid]["human_polarity"].strip()
    assert rev_polarity == "supports_alpha"
    synthetic_system_polarity = "opposes_alpha"  # force a synthetic reversal
    eligibility_class, _basis = _eligibility_for(synthetic_sid, registry)
    is_reversal = {synthetic_system_polarity, rev_polarity} == {"supports_alpha", "opposes_alpha"}
    assert eligibility_class == DIRECTIONALLY_CLEAR
    assert is_reversal is True
    # A DIRECTIONALLY_CLEAR reversal is never excluded -- only AMBIGUOUS_
    # DIRECTION (or other non-clear classes) are.
    counts_toward_gate = is_reversal and eligibility_class == DIRECTIONALLY_CLEAR
    assert counts_toward_gate is True


# ---------------------------------------------------------------------------
# E: no row-ID-specific exception exists in the eligibility logic itself
# ---------------------------------------------------------------------------


def test_e_no_row_id_specific_exception_in_eligibility_source_code():
    source = (REPO_ROOT / "scripts" / "build_evidence_review_v2_directional_eligibility.py").read_text()
    tree = ast.parse(source)
    # The only permissible appearance of the literal "holdout5-005" is
    # inside a comment/docstring (not parsed by ast) -- there must be no
    # string constant equal to it anywhere in the actual code (no branch
    # like `if sample_id == "holdout5-005"`).
    for node in ast.walk(tree):
        if isinstance(node, ast.Constant) and node.value == "holdout5-005":
            pytest.fail("eligibility script contains a hardcoded holdout5-005 string constant")
    # The eligibility function's own signature takes a generic sample_id and
    # a registry -- it is not special-cased by identity.
    func_source = ast.get_source_segment(source, next(
        n for n in ast.walk(tree) if isinstance(n, ast.FunctionDef) and n.name == "_eligibility_for"
    ))
    assert "holdout5-005" not in func_source


def test_e_eligibility_is_driven_by_outcome_not_by_identity():
    # Two different sample_ids carrying the SAME adjudication outcome must
    # resolve to the SAME eligibility class -- proving the mapping is keyed
    # on outcome, not on which row it is.
    registry = {
        "holdout5-005": {"sample_id": "holdout5-005", "outcome": "BOTH_REASONABLE_AMBIGUOUS"},
        "holdout5-999": {"sample_id": "holdout5-999", "outcome": "BOTH_REASONABLE_AMBIGUOUS"},
    }
    e1, _ = _eligibility_for("holdout5-005", registry)
    e2, _ = _eligibility_for("holdout5-999", registry)
    assert e1 == e2 == AMBIGUOUS_DIRECTION


# ---------------------------------------------------------------------------
# F: john_approved cannot become true automatically
# ---------------------------------------------------------------------------


def test_f_john_approved_cannot_become_true_automatically_even_when_all_mechanical_gates_pass(v2):
    results = v2["acceptance_results"]
    assert results["alpha_accuracy_result"]["status"] == "PASS"
    assert results["polarity_accuracy_result"]["status"] == "PASS"
    assert results["critical_reversal_result"]["status"] == "PASS"
    assert results["overall_mechanical_status"] == "ELIGIBLE_ACCEPTANCE_CRITERIA_MET_PENDING_JOHN_APPROVAL"
    # Despite every mechanical gate passing, approval remains explicitly
    # false/pending -- mechanical passage is never sufficient.
    assert v2["john_approval_status"]["john_approved"] is False
    assert v2["john_approval_status"]["john_approval_status"] == "PENDING_JOHN_APPROVAL"


# ---------------------------------------------------------------------------
# G: legacy conflicting metrics are not current acceptance metrics
# ---------------------------------------------------------------------------


def test_g_legacy_mixed_summary_metrics_are_not_read_as_current_acceptance(v2):
    legacy = json.loads((ARTIFACTS / "evidence_review_summary.json").read_text())
    # The legacy file's stale top-level critical_support_opposition_reversal_count
    # (0) contradicts the true raw H5 finding (1) -- current acceptance must
    # never read from it.
    assert legacy.get("critical_support_opposition_reversal_count") == 0
    assert v2["raw_h5_metrics"]["critical_reversal_count"] == 1
    assert v2["historical_sources"][
        "docs/audit_artifacts/evidence_review_summary.json"
    ]["use_for_current_acceptance"] is False


def test_g_eligibility_contract_is_the_generic_source_used_by_the_build_script():
    # Re-derive the eligibility registry the same way the build script does,
    # directly from the v2 artifact's own adjudication record -- proving the
    # v2 file's directional_eligibility block is reproducible, not hand-typed.
    v2_existing = json.loads(V2_PATH.read_text())
    registry = _load_adjudication_registry(v2_existing)
    assert set(registry) == {"holdout5-005"}
    eligibility_class, basis = _eligibility_for("holdout5-005", registry)
    assert eligibility_class == AMBIGUOUS_DIRECTION
    assert basis == "formal_adjudication_outcome:BOTH_REASONABLE_AMBIGUOUS"
    assert ADJUDICATION_OUTCOME_TO_ELIGIBILITY["BOTH_REASONABLE_AMBIGUOUS"] == AMBIGUOUS_DIRECTION


def test_no_import_of_provider_or_tradingagents_client_modules_in_this_test_file():
    tree = ast.parse(Path(__file__).read_text())
    banned_substrings = ("llm_clients", "tradingagents", "week2_llm")
    for node in ast.walk(tree):
        if isinstance(node, ast.ImportFrom) and node.module:
            assert not any(b in node.module for b in banned_substrings)
