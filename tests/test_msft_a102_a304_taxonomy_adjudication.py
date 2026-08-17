"""MSFT A102__A304 Canonical Conflict Taxonomy Adjudication -- dedicated
tests (task `MSFT_A102_A304_TAXONOMY_ADJUDICATION`).

DECISION = REJECT_PAIR (PD-017, docs/specs/product_decisions_and_unknowns.md):
A102__A304 is not added to the canonical conflict taxonomy. Source-authority
reasoning lives in PD-017 and the final report, not here -- this file only
locks in the resulting, observable system behavior.

Section map (matches the task's own checklist):
    A - Checks required for every outcome (1-10)
    B - REJECT_PAIR-specific checks (11-15)
"""

from __future__ import annotations

import re
import subprocess
from pathlib import Path

import pytest

from comqutor_alpha.alpha_library.alpha_loader import load_alpha_taxonomy
from comqutor_alpha.regression.evaluation_contract import apply_v2_contract
from comqutor_alpha.regression.evaluator import evaluate_ticker
from comqutor_alpha.regression.labels import _canonical_conflict_pairs, load_j2_labels, ticker_label
from comqutor_alpha.regression.labels_v2 import (
    LabelV2ValidationError,
    load_j2_labels_v2,
    ticker_label_v2,
)
from comqutor_alpha.regression.run_selection import select_run_for_ticker

REPO_ROOT = Path(__file__).resolve().parents[1]
PD_REGISTER_PATH = REPO_ROOT / "docs" / "specs" / "product_decisions_and_unknowns.md"
TAXONOMY_PATH = REPO_ROOT / "comqutor_alpha" / "alpha_library" / "alpha_taxonomy_v1.yaml"
DEVELOPMENT_PLAN_DOCX_PATH = REPO_ROOT / "docs" / "specs" / "COMQUTOR_Alpha_Development_Plan_v1.0.docx"
J3_BENCHMARK_PATH = REPO_ROOT / "comqutor_alpha" / "config" / "j3_provisional_semantic_benchmark_v0.1.json"

# Frozen SHA-256 baselines captured immediately before this adjudication's
# own edits (git-status-confirmed clean beforehand); these modules must
# never be touched by a taxonomy content decision.
FROZEN_HASHES = {
    TAXONOMY_PATH: "c031168c726cd424252cd9ee0491e55f335b5966694a326e0bcdfeeab1e7939c",
    REPO_ROOT / "comqutor_alpha/structure_engine/week2_llm.py": "a190fb9be805ae458d80d03c5aca3c5897e684683cd885594808ccd6973b6acd",
    REPO_ROOT / "comqutor_alpha/structure_engine/alpha_mapper.py": "138af8eb20531a31b71e31bcda3fa4194ba4eae5b974da8251c3cd8afa53ec1a",
    REPO_ROOT / "comqutor_alpha/conflict_engine/conflict_schema.py": "58466213a20810a062d98551866d4e4895f97771792ccaf6d08991655f28969e",
    REPO_ROOT / "comqutor_alpha/conflict_engine/conflict_admissibility.py": "0b795d4b2ee36fe11496b6766a83196b81d8afaec6c83f15cae2dbd0699b1f41",
    REPO_ROOT / "comqutor_alpha/conflict_engine/conflict_detector.py": "eea8055e07c23c90f53c500c5c4952d2a7d78541429d9acf0a13a941a1c88a55",
    # Development Plan v1.0 is PD-001 SOURCE_FROZEN; its own recorded hash.
    DEVELOPMENT_PLAN_DOCX_PATH: "cabf3381aaa633b7b88035ab6df2d7dac0def3d5ddd337f6384f23f4c439a8d9",
    J3_BENCHMARK_PATH: "0a021feff423ae075dd55d27c77f8e063826caf0046a1756fb92768ab6698ca6",
}


def _sha256(path: Path) -> str:
    import hashlib

    return hashlib.sha256(path.read_bytes()).hexdigest()


def _pd017_text() -> str:
    text = PD_REGISTER_PATH.read_text(encoding="utf-8")
    match = re.search(r"## PD-017.*?(?=\n## PD-|\Z)", text, re.DOTALL)
    assert match, "PD-017 section not found in product_decisions_and_unknowns.md"
    return match.group(0)


# ---------------------------------------------------------------------------
# Section A -- required for every outcome
# ---------------------------------------------------------------------------


class TestSectionAAllOutcomes:
    def test_a1_decision_record_exists_and_is_readable(self):
        assert PD_REGISTER_PATH.exists()
        text = PD_REGISTER_PATH.read_text(encoding="utf-8")
        assert "## PD-017" in text
        assert "MSFT A102__A304" in text

    def test_a2_decision_source_is_accurate(self):
        pd017 = _pd017_text()
        assert "User-authorized independent LLM product adjudication" in pd017

    def test_a3_never_claims_john_or_human_approval(self):
        for source_text in (
            _pd017_text(),
            Path(REPO_ROOT / "docs/audit_artifacts/msft_a102_a304_taxonomy_adjudication_report.md").read_text(encoding="utf-8")
            if (REPO_ROOT / "docs/audit_artifacts/msft_a102_a304_taxonomy_adjudication_report.md").exists()
            else "",
        ):
            if not source_text:
                continue
            lowered = source_text.lower()
            assert "john personally approved" not in lowered
            assert "john approved" not in lowered
            assert re.search(r"human review (was |has been )?performed\b(?!.{0,40}not)", lowered) is None or "not performed" in lowered

    def test_a4_j2_is_consistent_with_the_final_decision(self):
        v2 = load_j2_labels_v2()
        msft = ticker_label_v2(v2, "MSFT")
        assert msft["product_decision_pending"] == []
        assert "A102__A304" in msft["remove_while_undeclared"]
        for category in ("required_conflicts", "conditional_conflicts", "allowed_conflicts"):
            assert "A102__A304" not in msft[category]

    def test_a5_a4_no_longer_reports_the_old_unexplained_pending_entry(self):
        v2 = load_j2_labels_v2()
        label = ticker_label_v2(v2, "MSFT")
        not_evaluable_result = {
            "run_selection_status": "selected",
            "offline_reprocess_status": "completed",
            "artifact_completeness": "fail",
            "ticker_consistency": "pass",
            "admitted_conflicts": [],
            "candidate_conflicts": [],
            "detected_alphas": [],
        }
        result = apply_v2_contract(ticker="MSFT", ticker_v2_label=label, evaluate_ticker_result=not_evaluable_result)
        assert result["product_decision_pending_results"] == []
        assert result["removed_while_undeclared_pairs"] == ["A102__A304"]

    def test_a6_b1_b2_b3_b4_invariant_modules_are_byte_identical(self):
        for path, expected_hash in FROZEN_HASHES.items():
            assert _sha256(path) == expected_hash, f"{path} hash changed"

    def test_a7_and_a8_provider_and_tradingagents_calls_zero(self, real_evaluated_msft):
        assert real_evaluated_msft.get("provider_calls") == 0
        assert real_evaluated_msft.get("tradingagents_calls") == 0

    def test_a9_source_run_byte_identical_before_and_after(self, real_evaluated_msft):
        hashes = real_evaluated_msft.get("artifact_hashes", {})
        assert hashes.get("source_raw_artifact_unchanged") is True

    def test_a10_j3_benchmark_byte_identical(self):
        assert _sha256(J3_BENCHMARK_PATH) == FROZEN_HASHES[J3_BENCHMARK_PATH]


# ---------------------------------------------------------------------------
# Section B -- REJECT_PAIR-specific
# ---------------------------------------------------------------------------


class TestSectionBRejectPairSpecific:
    def test_b11_canonical_taxonomy_hash_unchanged(self):
        assert _sha256(TAXONOMY_PATH) == FROZEN_HASHES[TAXONOMY_PATH]

    def test_b12_j2_no_longer_treats_the_pair_as_an_executable_expectation(self):
        v2 = load_j2_labels_v2()
        msft = ticker_label_v2(v2, "MSFT")
        assert "A102__A304" not in msft["required_conflicts"]
        assert "A102__A304" not in msft["conditional_conflicts"]
        assert "A102__A304" not in msft["allowed_conflicts"]

    def test_b13_a4_never_reports_the_missing_pair_as_a_ticker_failure(self):
        v2 = load_j2_labels_v2()
        label = ticker_label_v2(v2, "MSFT")
        evaluable_result = {
            "run_selection_status": "selected",
            "offline_reprocess_status": "completed",
            "artifact_completeness": "pass",
            "ticker_consistency": "pass",
            "admitted_conflicts": [],
            "candidate_conflicts": [],
            "detected_alphas": [],
        }
        result = apply_v2_contract(ticker="MSFT", ticker_v2_label=label, evaluate_ticker_result=evaluable_result)
        assert result["ticker_status"] == "pass"
        assert result["required_conflict_results"] == []

    def test_b14_validator_still_rejects_a102_a304_as_an_executable_pair(self, tmp_path):
        import yaml

        payload = {
            "schema_version": "regression_labels.v2",
            "label_version": "test.v2",
            "taxonomy_version": "alpha_taxonomy_v1",
            "evaluation_mode": "shadow",
            "evaluation_authority": "provisional",
            "approved_by": None,
            "approved_at": None,
            "formal_product_owner_approval": "pending",
            "tickers": {
                "MSFT": {
                    "structural_expectations": {"positive_alphas": [], "negative_alphas": [], "conditional_alphas": []},
                    "run_bound_expectations": None,
                    "required_conflicts": [],
                    # Attempting to silently re-promote the rejected pair
                    # into an executable category must still fail closed.
                    "conditional_conflicts": ["A102__A304"],
                    "product_decision_pending": [],
                    "remove_while_undeclared": [],
                    "allowed_conflicts": [],
                }
            },
        }
        path = tmp_path / "attempted_reintroduction.yaml"
        path.write_text(yaml.safe_dump(payload), encoding="utf-8")
        with pytest.raises(LabelV2ValidationError) as exc_info:
            load_j2_labels_v2(path)
        assert exc_info.value.reason_code == "LABEL_V2_UNDECLARED_EXECUTABLE_CONFLICT_PAIR"

    def test_b14b_a102_still_has_zero_canonical_conflicts(self):
        taxonomy = load_alpha_taxonomy()
        assert taxonomy["A102"].conflict_alphas == []
        pairs = _canonical_conflict_pairs(taxonomy)
        assert "A102__A304" not in pairs
        assert "A304__A102" not in pairs

    def test_b15_development_plan_preserved_with_a_formal_superseding_decision(self):
        assert _sha256(DEVELOPMENT_PLAN_DOCX_PATH) == FROZEN_HASHES[DEVELOPMENT_PLAN_DOCX_PATH]
        pd017 = _pd017_text()
        assert "Development Plan" in pd017
        assert "§4" in pd017 or "section 4" in pd017.lower()


# ---------------------------------------------------------------------------
# Shared real-replay fixture (MSFT's only saved run; deterministic-baseline,
# artifact_completeness=fail, zero Provider/TradingAgents calls by
# Architecture Replay's own structural guarantee).
# ---------------------------------------------------------------------------


@pytest.fixture(scope="module")
def real_saved_msft_run_id() -> str | None:
    runs_dir = REPO_ROOT / "outputs" / "runs"
    if not runs_dir.exists():
        return None
    import json

    for path in sorted(runs_dir.glob("*/metadata.json")):
        try:
            metadata = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, ValueError):
            continue
        if metadata.get("ticker") == "MSFT" and (path.parent / "raw_agent_outputs.json").exists():
            return path.parent.name
    return None


@pytest.fixture(scope="module")
def real_evaluated_msft(real_saved_msft_run_id, tmp_path_factory):
    if real_saved_msft_run_id is None:
        pytest.skip("LIVE_SAVED_RUN_NOT_AVAILABLE: no real MSFT saved run found")
    v1_labels = load_j2_labels()
    label_block = ticker_label(v1_labels, "MSFT")
    selection = select_run_for_ticker("MSFT", REPO_ROOT / "outputs" / "runs")
    replay_root = tmp_path_factory.mktemp("msft_a102_a304_replay")
    return evaluate_ticker("MSFT", selection, label_block, replay_output_root=str(replay_root))


def test_head_unchanged_from_session_frozen_starting_commit():
    proc = subprocess.run(["git", "rev-parse", "HEAD"], cwd=str(REPO_ROOT), capture_output=True, text=True, check=True)
    assert proc.stdout.strip() == "b5837e80a4550fc35165d0013a8ef0f27ccb4c8f"
