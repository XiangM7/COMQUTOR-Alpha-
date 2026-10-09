"""T2 round 24: the Alpha-layer rules of John's frozen Gold v0.2 contract, executed by the unified formal-acceptance entry
(comqutor_alpha.regression.gold_contract_rules, called from acceptance_engine.run_formal_acceptance).

John's T2 table: "有明确支持证据，却漏掉必须识别的 Alpha -> 验收能够发现漏检". The contract defines must_detect_if_evidence_present at the Alpha level
(NVDA-A101 and NVDA-A304 blocking, MSFT-A102 non-blocking); the two composite rules (NVDA, AMD) are conditional_only with "any ONE allowed pair".

Three kinds of evidence, never mixed:

  * MECHANISM tests -- SYNTHETIC run artifacts (a hand-made ``activation_summary`` and ``alpha_matches``) judged against the REAL frozen contract and
    trigger matrix. They prove how the executor decides; they are not market data and are never counted as real validation.
  * CONTROLLED variants -- a copy of the contract / freeze manifest / matrix in tmp_path, edited on purpose, to prove a tampered, re-versioned or
    incomplete rule file is refused. They are not John's files.
  * HISTORICAL-INPUT tests -- the repository's saved runs under outputs/runs, read-only (the same practice as tests/test_v0_1_3_offline_replay_proof.py).
    They show what the executor says about real saved results and that it reproduces John's own Step-4 table rows for the runs the matrix is bound to.

Zero Provider calls; every file written lives under tmp_path.
"""

from __future__ import annotations

import hashlib
import json
import re
import shutil
from pathlib import Path

import pytest

from comqutor_alpha.regression import (
    acceptance_engine as engine,
    formal_acceptance_report as report,
    gold_contract_rules as gold,
)
from comqutor_alpha.regression.acceptance_engine import (
    AcceptanceConfigError,
    effective_rules,
    run_formal_acceptance,
)
from comqutor_alpha.regression.labels import load_j2_labels, ticker_label
from comqutor_alpha.regression.labels_v2 import load_j2_labels_v2, ticker_label_v2

REPO = Path(__file__).resolve().parents[1]
RUNS_ROOT = REPO / "outputs" / "runs"
AUDIT = REPO / "docs" / "audit_artifacts"
CONTRACT = AUDIT / "v0_2_gold_operational_contract.json"
MANIFEST = AUDIT / "v0_2_gold_freeze_manifest.json"
MATRIX = AUDIT / "v0_2_evidence_trigger_matrix.json"
STEP4_TABLE = AUDIT / "v0_2_final_acceptance_table.md"

NVDA_BOUND = "57d7b4c4-dbb9-4134-b962-ee2a873941cc"
MSFT_BOUND = "43472ace-454f-4c69-892c-adca91c25be7"
AMD_BOUND = "949f685a-3945-4fd0-b7b9-362b37c90721"
NVDA_PINNED = "ded99ecd-a186-4a90-859e-0f1a0efa43db"
MSFT_PINNED = "64568bfb-fe0c-453c-9872-831a8dc339a0"
AMD_PINNED = "d5b60b8a-66b8-44c1-9f55-ee345e58c48d"
SNDK_BOUND_AND_PINNED = "e8e0f398-7b26-4462-8135-a1410ea5b335"

DETECTED = ("active", "dominant", "regime_level")
NOT_DETECTED = ("candidate", "capped_active", "blocked", "unavailable")


# ---------------------------------------------------------------------------------------------------------------------------------------
# helpers
# ---------------------------------------------------------------------------------------------------------------------------------------


def _sha(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _bundle(**kwargs) -> gold.GoldContractBundle:
    return gold.load_gold_contract_bundle(**kwargs)


def _summary(**levels) -> dict:
    """SYNTHETIC run_audit.json -> activation_summary: ``_summary(A101=("candidate", 48.5))``."""
    return {
        "per_alpha": {
            alpha: {
                "score": score,
                "level": level,
                "qualification_codes": [],
                "unique_evidence_fact_count": 3,
                "distinct_supporting_agents": 2,
                "ticker_specific_evidence_count": 2,
            }
            for alpha, (level, score) in levels.items()
        }
    }


def _matches(*, matched=(), no_match=0, unavailable=0) -> dict:
    """SYNTHETIC alpha_matches: ``matched`` is a list of Alpha ids, one claim each."""
    records = [{"claim_id": f"m{i}", "match_status": "matched", "matched_alpha": alpha} for i, alpha in enumerate(matched)]
    records += [{"claim_id": f"n{i}", "match_status": "no_match", "matched_alpha": None} for i in range(no_match)]
    records += [{"claim_id": f"u{i}", "match_status": "unavailable", "matched_alpha": None} for i in range(unavailable)]
    return {"matches": records}


def _alpha_rule(rule_id, ticker, run_id, *, summary, matches, bundle=None):
    bundle = bundle or _bundle()
    return gold.evaluate_alpha_rule(
        bundle, bundle.rules_by_id[rule_id], ticker=ticker, run_id=run_id, activation_summary=summary, alpha_matches_payload=matches
    )


def _composite(rule_id, ticker, run_id, *, admitted, main=None, family=(), bundle=None):
    bundle = bundle or _bundle()
    return gold.evaluate_composite_rule(
        bundle, bundle.rules_by_id[rule_id], ticker=ticker, run_id=run_id, admitted_conflicts=admitted, main_conflict=main, allowed_family=family
    )


def _evaluate_ticker_result(ticker, run_id, *, admitted=(), main=None):
    return {
        "ticker": ticker,
        "run_id": run_id,
        "run_selection_status": "selected",
        "offline_reprocess_status": "completed",
        "artifact_completeness": "pass",
        "artifact_missing_files": [],
        "admitted_conflicts": list(admitted),
        "candidate_conflicts": [],
        "main_conflict": main,
        "stance_source": "llm_semantic",
    }


def _verdict(ticker, run_id, *, summary, matches, admitted=(), main=None, **paths):
    """The REAL labels for the ticker and the real engine, fed SYNTHETIC run artifacts."""
    conflict_payload = {
        "conflicts": [{"conflict_id": c} for c in admitted],
        "arbitration": {
            "candidate_evaluations": [
                {
                    "alpha_a": c.split("__")[0],
                    "alpha_b": c.split("__")[1],
                    "outcome": "admitted",
                    "admissibility": {"status": "admitted", "reason_codes": [], "bull_supporting_evidence_count": 2, "bear_supporting_evidence_count": 2},
                }
                for c in admitted
            ]
        },
    }
    return run_formal_acceptance(
        ticker=ticker,
        ticker_v2_label=ticker_label_v2(load_j2_labels_v2(), ticker),
        label_block_v1=ticker_label(load_j2_labels(), ticker),
        evaluate_ticker_result=_evaluate_ticker_result(ticker, run_id, admitted=admitted, main=main),
        conflict_payload=conflict_payload,
        graph_payload={},
        alpha_matches_payload=matches,
        activation_summary=summary,
        **paths,
    )


def _variant(tmp_path: Path, *, contract_edit=None, matrix_edit=None, refreeze=True, manifest_edit=None) -> dict:
    """A tampered / re-versioned copy of the three frozen inputs. ``refreeze=True`` re-records the edited contract's sha256 in the copied manifest and
    matrix (as a legitimate re-freeze would), so the edit is judged on its content and not only on its hash."""
    contract_path = tmp_path / "contract.json"
    if contract_edit is None:
        shutil.copyfile(CONTRACT, contract_path)  # byte-identical: its sha256 is still the frozen one
    else:
        contract = json.loads(CONTRACT.read_text(encoding="utf-8"))
        contract_edit(contract)
        contract_path.write_text(json.dumps(contract, indent=1), encoding="utf-8")
    manifest = json.loads(MANIFEST.read_text(encoding="utf-8"))
    matrix = json.loads(MATRIX.read_text(encoding="utf-8"))
    if refreeze:
        manifest["frozen_contract_json_sha256"] = _sha(contract_path)
        matrix["gold_authority"]["contract_sha256"] = _sha(contract_path)
    if manifest_edit:
        manifest_edit(manifest)
    if matrix_edit:
        matrix_edit(matrix)
    manifest_path, matrix_path = tmp_path / "manifest.json", tmp_path / "matrix.json"
    manifest_path.write_text(json.dumps(manifest, indent=1), encoding="utf-8")
    matrix_path.write_text(json.dumps(matrix, indent=1), encoding="utf-8")
    return {"contract_path": contract_path, "freeze_manifest_path": manifest_path, "trigger_matrix_path": matrix_path}


def _reason(**kwargs) -> str:
    with pytest.raises(gold.GoldContractError) as info:
        gold.load_gold_contract_bundle(**kwargs)
    return info.value.reason_code


# ---------------------------------------------------------------------------------------------------------------------------------------
# 1. the contract is the frozen file, and what is in effect is stated with the John decision it implements
# ---------------------------------------------------------------------------------------------------------------------------------------


def test_the_repository_contract_is_the_frozen_file_and_the_matrix_is_bound_to_it():
    bundle = _bundle()
    assert bundle.contract_sha256 == bundle.manifest["frozen_contract_json_sha256"] == _sha(CONTRACT)
    assert bundle.matrix_sha256 == gold.FROZEN_TRIGGER_MATRIX_SHA256
    assert bundle.matrix["gold_authority"]["contract_sha256"] == bundle.contract_sha256
    assert bundle.matrix_runs == {
        "NVDA": NVDA_BOUND,
        "QQQ": "f88c8956-cb62-48aa-9951-89f8e8a95f83",
        "MSFT": MSFT_BOUND,
        "SNDK": SNDK_BOUND_AND_PINNED,
        "TSM": "dfc7ceb3-3584-4514-bd84-6c371aab3e95",
        "AMD": AMD_BOUND,
    }
    assert len(bundle.rules_by_id) == 19


def test_each_executed_rule_is_the_contract_record_John_froze_and_cites_his_decision():
    bundle = _bundle()
    expected = {
        "NVDA-A101-AI-GROWTH": ("must_detect_if_evidence_present", True, ["A101"]),
        "NVDA-A304-VALUATION-RISK": ("must_detect_if_evidence_present", True, ["A304"]),
        "MSFT-A102-DIRECT-INFERENCE-TRIGGER": ("must_detect_if_evidence_present", False, ["A102"]),
    }
    for rule_id, (rule_type, blocking, alphas) in expected.items():
        rule = bundle.rules_by_id[rule_id]
        assert (rule["rule_type"], rule["blocking"], rule["acceptable_alphas"]) == (rule_type, blocking, alphas)
        basis = " ".join(gold.RULE_AUTHORITY_BASIS[rule_id])
        assert "Step 2" in basis and "2026-09-10T21:02:57Z" in basis
    assert "section 1.G" in " ".join(gold.RULE_AUTHORITY_BASIS["MSFT-A102-DIRECT-INFERENCE-TRIGGER"])
    assert "section 4" in " ".join(gold.RULE_AUTHORITY_BASIS["NVDA-A101-AI-GROWTH"])
    assert set(gold.RULE_AUTHORITY_BASIS) == set(gold.EXECUTED_RULE_IDS)


def test_the_approval_flag_inside_the_contract_file_is_not_cited_as_evidence():
    description = gold.describe_bundle(_bundle())
    assert description["authority_field_in_file"]["approval_status"] == "APPROVED"
    assert "template" in description["authority_note"] and "not cited as evidence" in description["authority_note"]


def test_the_markdown_companion_drift_is_reported_not_hidden_and_the_executor_does_not_read_it():
    companion = gold.describe_bundle(_bundle())["markdown_companion"]
    assert companion["read_by_executor"] is False
    assert companion["sha256_frozen"] == "8e184d7ed41cbe253b5aa7e97e150e9c7f4dbfd6852d411e9874dbe299bf9f04"
    assert companion["matches_frozen"] == (companion["sha256_now"] == companion["sha256_frozen"])
    assert "2026-09-15" in companion["note"]


def test_the_frozen_files_are_found_under_the_working_directory_when_the_package_is_installed_elsewhere(tmp_path, monkeypatch):
    """The container image installs comqutor_alpha into a virtualenv and keeps the repository copy in WORKDIR, so the files under docs/audit_artifacts/
    are NOT next to the package there. They are found under the working directory instead -- the same bytes, verified against the same freeze manifest
    -- and when they are nowhere the error names the expected place (no silent skip)."""
    workdir = tmp_path / "app"
    (workdir / "docs" / "audit_artifacts").mkdir(parents=True)
    for source in (CONTRACT, MANIFEST, MATRIX):
        shutil.copyfile(source, workdir / "docs" / "audit_artifacts" / source.name)
    elsewhere = tmp_path / "site-packages" / "docs" / "audit_artifacts"
    monkeypatch.setattr(gold, "DEFAULT_CONTRACT_PATH", elsewhere / CONTRACT.name)
    monkeypatch.setattr(gold, "DEFAULT_FREEZE_MANIFEST_PATH", elsewhere / MANIFEST.name)
    monkeypatch.setattr(gold, "DEFAULT_TRIGGER_MATRIX_PATH", elsewhere / MATRIX.name)
    monkeypatch.chdir(workdir)
    bundle = gold.load_gold_contract_bundle()
    assert bundle.contract_sha256 == _sha(CONTRACT) and bundle.contract_path == workdir / "docs" / "audit_artifacts" / CONTRACT.name
    assert gold.describe_bundle(bundle)["path"] == "docs/audit_artifacts/v0_2_gold_operational_contract.json"  # no engineer's absolute path
    empty = tmp_path / "empty"
    empty.mkdir()
    monkeypatch.chdir(empty)
    with pytest.raises(gold.GoldContractError) as info:
        gold.load_gold_contract_bundle()
    assert info.value.reason_code == "ACCEPTANCE_GOLD_CONTRACT_FILE_NOT_FOUND" and "site-packages" in info.value.detail


def test_the_rules_this_entry_does_not_execute_are_listed_with_a_reason_and_none_is_silently_skipped():
    description = gold.describe_bundle(_bundle())
    in_effect = {r["rule_id"] for r in description["rules_in_effect"]}
    not_in_effect = {r["rule_id"] for r in description["rules_not_in_effect"]}
    assert in_effect | not_in_effect == set(_bundle().rules_by_id) and not in_effect & not_in_effect
    assert len(not_in_effect) == 14
    assert all(r["reason_code"] == "NOT_EXECUTED_THIS_ROUND" for r in description["rules_not_in_effect"])


# ---------------------------------------------------------------------------------------------------------------------------------------
# 2. a missing, edited, re-versioned or incomplete rule file is a configuration error -- never a pass
# ---------------------------------------------------------------------------------------------------------------------------------------


def test_a_missing_contract_freeze_manifest_or_matrix_is_a_configuration_error(tmp_path):
    assert _reason(contract_path=tmp_path / "nope.json") == "ACCEPTANCE_GOLD_CONTRACT_FILE_NOT_FOUND"
    assert _reason(freeze_manifest_path=tmp_path / "nope.json") == "ACCEPTANCE_GOLD_FREEZE_MANIFEST_NOT_FOUND"
    assert _reason(trigger_matrix_path=tmp_path / "nope.json") == "ACCEPTANCE_TRIGGER_MATRIX_NOT_FOUND"
    broken = tmp_path / "broken.json"
    broken.write_text("{not json", encoding="utf-8")
    assert _reason(contract_path=broken) == "ACCEPTANCE_GOLD_CONTRACT_MALFORMED"


def test_an_edited_contract_is_not_the_contract_John_froze_even_if_it_still_parses(tmp_path):
    def flip_blocking(contract):
        contract["tickers"]["MSFT"]["rules"][1]["blocking"] = True

    paths = _variant(tmp_path, contract_edit=flip_blocking, refreeze=False)  # the manifest still records the frozen sha256
    assert _reason(**paths) == "ACCEPTANCE_GOLD_CONTRACT_INTEGRITY_MISMATCH"


def test_a_contract_of_another_gold_version_is_refused(tmp_path):
    paths = _variant(tmp_path, contract_edit=lambda c: c.update(gold_version="v0.3"))
    assert _reason(**paths) == "ACCEPTANCE_GOLD_CONTRACT_VERSION_MISMATCH"
    draft = tmp_path / "draft"
    draft.mkdir()
    paths = _variant(draft, contract_edit=lambda c: c.update(freeze_status="DRAFT"))
    assert _reason(**paths) == "ACCEPTANCE_GOLD_CONTRACT_VERSION_MISMATCH"


def test_a_contract_whose_detected_levels_disagree_with_the_authority_it_cites_is_refused(tmp_path):
    paths = _variant(tmp_path, contract_edit=lambda c: c["detected_level_authority"].update(detected_levels=["active", "dominant", "regime_level", "candidate"]))
    assert _reason(**paths, expected_matrix_sha256=None) == "ACCEPTANCE_GOLD_CONTRACT_DETECTION_AUTHORITY_MISMATCH"
    assert set(_bundle().contract["detected_level_authority"]["detected_levels"]) == set(DETECTED)


def test_a_matrix_that_is_not_the_frozen_file_or_was_written_against_another_contract_is_refused(tmp_path):
    def flip_a_trigger(matrix):
        matrix["tickers"]["NVDA"]["rules"][0]["trigger_state"] = "ABSENT"

    paths = _variant(tmp_path, matrix_edit=flip_a_trigger)
    assert _reason(contract_path=paths["contract_path"], freeze_manifest_path=paths["freeze_manifest_path"], trigger_matrix_path=paths["trigger_matrix_path"]) == (
        "ACCEPTANCE_TRIGGER_MATRIX_INTEGRITY_MISMATCH"
    )
    other = tmp_path / "other"
    other.mkdir()
    paths = _variant(other, matrix_edit=lambda m: m["gold_authority"].update(contract_sha256="0" * 64))
    assert _reason(**paths, expected_matrix_sha256=None) == "ACCEPTANCE_TRIGGER_MATRIX_CONTRACT_MISMATCH"


def test_a_rule_the_executor_runs_but_the_contract_lacks_or_retypes_is_refused(tmp_path):
    def drop_rule(contract):
        contract["tickers"]["NVDA"]["rules"] = [r for r in contract["tickers"]["NVDA"]["rules"] if r["rule_id"] != "NVDA-A304-VALUATION-RISK"]

    paths = _variant(tmp_path, contract_edit=drop_rule)
    assert _reason(**paths, expected_matrix_sha256=None) == "ACCEPTANCE_GOLD_CONTRACT_RULE_MISSING"
    other = tmp_path / "retyped"
    other.mkdir()

    def retype(contract):
        contract["tickers"]["NVDA"]["rules"][0]["rule_type"] = "should_detect_if_supported"

    paths = _variant(other, contract_edit=retype)
    assert _reason(**paths, expected_matrix_sha256=None) == "ACCEPTANCE_RULE_TYPE_NOT_IMPLEMENTED"


def test_through_the_unified_entry_a_bad_contract_file_is_a_config_error_for_every_ticker_never_a_pass(tmp_path):
    paths = _variant(tmp_path, contract_edit=lambda c: c.update(gold_version="v0.3"))
    kwargs = {
        "gold_contract_path": paths["contract_path"],
        "gold_freeze_manifest_path": paths["freeze_manifest_path"],
        "trigger_matrix_path": paths["trigger_matrix_path"],
    }
    with pytest.raises(AcceptanceConfigError) as info:
        effective_rules(**kwargs)
    assert info.value.reason_code == "ACCEPTANCE_GOLD_CONTRACT_VERSION_MISMATCH"
    for ticker in ("NVDA", "QQQ"):
        verdict = _verdict(ticker, "any-run", summary=_summary(), matches=_matches(matched=["A101"]), **kwargs)
        assert verdict["formal_status"] == "config_error"
        assert verdict["config_error_reason_code"] == "ACCEPTANCE_GOLD_CONTRACT_VERSION_MISMATCH"
        assert verdict["rule_family_results"] == {}


# ---------------------------------------------------------------------------------------------------------------------------------------
# 3. the evidence trigger belongs to the run the matrix is bound to -- and to no other
# ---------------------------------------------------------------------------------------------------------------------------------------


def test_the_frozen_trigger_is_used_for_the_run_the_matrix_is_bound_to():
    trigger = gold.trigger_for(_bundle(), ticker="NVDA", rule_id="NVDA-A101-AI-GROWTH", run_id=NVDA_BOUND)
    assert (trigger["state"], trigger["strength"], trigger["source"]) == ("PRESENT", "STRONG", "frozen_evidence_trigger_matrix")
    assert trigger["matrix_run_id"] == trigger["evaluated_run_id"] == NVDA_BOUND


@pytest.mark.parametrize("run_id", [NVDA_PINNED, f"dependency-20261007T000000Z-{NVDA_BOUND[:8]}", f"requal-{NVDA_BOUND}", "", None])
def test_the_same_ticker_on_any_other_run_is_not_evaluable_and_the_historical_state_is_not_carried_over(run_id):
    trigger = gold.trigger_for(_bundle(), ticker="NVDA", rule_id="NVDA-A101-AI-GROWTH", run_id=run_id)
    assert trigger["state"] == "NOT_EVALUABLE" and trigger["reason_code"] == gold.REASON_RUN_NOT_BOUND
    assert trigger["strength"] is None and trigger["source"] is None  # no PRESENT/STRONG leaks across
    assert "not carried over" in trigger["reading"] and NVDA_BOUND in trigger["reading"]


def test_a_ticker_or_rule_the_matrix_does_not_carry_is_not_evaluable_with_its_own_reason(tmp_path):
    assert gold.trigger_for(_bundle(), ticker="ZZZZ", rule_id="X", run_id="r")["reason_code"] == gold.REASON_TICKER_NOT_IN_MATRIX

    def drop_rule(matrix):
        matrix["tickers"]["NVDA"]["rules"] = [r for r in matrix["tickers"]["NVDA"]["rules"] if r["rule_id"] != "NVDA-A101-AI-GROWTH"]

    paths = _variant(tmp_path, matrix_edit=drop_rule, refreeze=False)
    bundle = _bundle(**paths, expected_matrix_sha256=None)
    assert gold.trigger_for(bundle, ticker="NVDA", rule_id="NVDA-A101-AI-GROWTH", run_id=NVDA_BOUND)["reason_code"] == gold.REASON_RULE_NOT_IN_MATRIX


# ---------------------------------------------------------------------------------------------------------------------------------------
# 4. four facts, kept apart: identified? / activation level / contract requirement / evidence trigger
# ---------------------------------------------------------------------------------------------------------------------------------------


def test_trigger_present_and_the_alpha_identified_but_below_the_required_level_is_a_fail_that_is_not_written_as_not_identified():
    rule = _alpha_rule("NVDA-A101-AI-GROWTH", "NVDA", NVDA_BOUND, summary=_summary(A101=("candidate", 48.55)), matches=_matches(matched=["A101"] * 4, no_match=6))
    (alpha,) = rule["alpha_recognition"]
    assert alpha["identification_state"] == gold.IDENTIFIED and alpha["claims_matched_to_this_alpha"] == 4
    assert alpha["activation_level"] == "candidate" and alpha["activation_score"] == 48.55 and alpha["level_is_official_detected_level"] is False
    assert rule["requirement"]["satisfied"] is False
    assert rule["evidence_trigger"]["state"] == "PRESENT"
    assert rule["verdict"] == "fail" and rule["john_result"] == "FAIL"
    assert "identified (4 claims classified to it) but its level is candidate, below the required level" in rule["requirement"]["reading"]
    assert "not identified" not in rule["requirement"]["reading"]


def test_trigger_present_and_the_alpha_never_classified_with_a_complete_classification_is_a_fail_recorded_as_not_identified():
    rule = _alpha_rule("NVDA-A101-AI-GROWTH", "NVDA", NVDA_BOUND, summary=_summary(A101=("candidate", 0.0)), matches=_matches(matched=["A301"] * 3, no_match=7))
    (alpha,) = rule["alpha_recognition"]
    assert alpha["identification_state"] == gold.NOT_IDENTIFIED and alpha["claims_classification_unavailable"] == 0
    assert rule["verdict"] == "fail"
    assert "not identified (no claim classified to it; classification complete)" in rule["requirement"]["reading"]


def test_a_technically_unfinished_classification_is_never_written_as_a_valid_none_and_the_miss_is_not_asserted():
    rule = _alpha_rule(
        "NVDA-A101-AI-GROWTH", "NVDA", NVDA_BOUND, summary=_summary(A101=("candidate", 0.0)), matches=_matches(matched=["A301"] * 3, no_match=5, unavailable=2)
    )
    (alpha,) = rule["alpha_recognition"]
    assert alpha["identification_state"] == gold.UNKNOWN_CLASSIFICATION_INCOMPLETE and alpha["claims_classification_unavailable"] == 2
    assert alpha["identification_state"] != gold.NOT_IDENTIFIED
    assert rule["verdict"] == "not_evaluable" and rule["reason_code"] == gold.REASON_CLASSIFICATION_INCOMPLETE
    assert "cannot be written as a valid NONE" in rule["detail"] and "technically unclassified" in rule["requirement"]["reading"]


def test_some_unavailable_claims_do_not_hide_a_real_miss_when_claims_were_classified_to_the_alpha():
    rule = _alpha_rule(
        "NVDA-A101-AI-GROWTH", "NVDA", NVDA_BOUND, summary=_summary(A101=("candidate", 40.0)), matches=_matches(matched=["A101"] * 2, no_match=5, unavailable=1)
    )
    assert rule["alpha_recognition"][0]["identification_state"] == gold.IDENTIFIED
    assert rule["verdict"] == "fail"  # the Alpha WAS identified; its level is what falls short


@pytest.mark.parametrize("level", DETECTED)
def test_every_official_detected_level_satisfies_the_requirement(level):
    rule = _alpha_rule("NVDA-A304-VALUATION-RISK", "NVDA", NVDA_BOUND, summary=_summary(A304=(level, 67.6)), matches=_matches(matched=["A304"] * 3))
    assert rule["requirement"]["satisfied"] is True and rule["requirement"]["satisfied_by"] == "A304"
    assert rule["verdict"] == "pass" and rule["blocks_release"] is False


@pytest.mark.parametrize("level", NOT_DETECTED)
def test_no_level_below_the_official_detected_levels_satisfies_the_requirement(level):
    rule = _alpha_rule("NVDA-A304-VALUATION-RISK", "NVDA", NVDA_BOUND, summary=_summary(A304=(level, 43.0)), matches=_matches(matched=["A304"] * 3))
    assert rule["requirement"]["satisfied"] is False and rule["verdict"] == "fail"


def test_when_the_detection_authority_cannot_be_read_a_present_trigger_is_not_evaluable_never_guessed():
    for summary in (None, {}, {"per_alpha": {}}, {"per_alpha": {"A101": {"score": 70.0}}}, "not-a-mapping"):
        rule = _alpha_rule("NVDA-A101-AI-GROWTH", "NVDA", NVDA_BOUND, summary=summary, matches=_matches(matched=["A101"] * 3))
        assert rule["verdict"] == "not_evaluable" and rule["reason_code"] == gold.REASON_DETECTION_AUTHORITY_UNAVAILABLE
        assert rule["requirement"]["satisfied"] is None


def test_on_an_unbound_run_the_alpha_facts_are_still_recorded_but_no_verdict_is_reached():
    rule = _alpha_rule("NVDA-A101-AI-GROWTH", "NVDA", NVDA_PINNED, summary=_summary(A101=("candidate", 48.55)), matches=_matches(matched=["A101"] * 21))
    assert rule["verdict"] == "not_evaluable" and rule["reason_code"] == gold.REASON_RUN_NOT_BOUND
    assert rule["alpha_recognition"][0]["activation_level"] == "candidate"
    assert rule["requirement"]["satisfied"] is False  # a fact about the level, recorded; it is not a verdict on a rule whose trigger is unknown
    assert rule["blocks_release"] is False and rule["unresolved_blocking"] is True


def test_trigger_absent_means_not_triggered_and_nothing_is_forced_and_uncertain_means_review(tmp_path):
    for state, verdict in (("ABSENT", "not_triggered"), ("UNCERTAIN", "needs_review")):
        directory = tmp_path / state
        directory.mkdir()
        paths = _variant(directory, matrix_edit=lambda m, s=state: m["tickers"]["NVDA"]["rules"][0].update(trigger_state=s), refreeze=False)
        bundle = _bundle(**paths, expected_matrix_sha256=None)
        assert bundle.matrix_rules[("NVDA", "NVDA-A101-AI-GROWTH")]["trigger_state"] == state
        rule = _alpha_rule("NVDA-A101-AI-GROWTH", "NVDA", NVDA_BOUND, summary=_summary(A101=("candidate", 5.0)), matches=_matches(no_match=9), bundle=bundle)
        assert rule["verdict"] == verdict and rule["blocks_release"] is False


# ---------------------------------------------------------------------------------------------------------------------------------------
# 5. severity is the contract's: blocking / non-blocking, and a non-blocking rule never becomes a global block
# ---------------------------------------------------------------------------------------------------------------------------------------


def test_a_failed_blocking_rule_blocks_release_and_a_failed_non_blocking_rule_does_not():
    nvda = _alpha_rule("NVDA-A101-AI-GROWTH", "NVDA", NVDA_BOUND, summary=_summary(A101=("candidate", 48.0)), matches=_matches(matched=["A101"] * 3))
    msft = _alpha_rule(
        "MSFT-A102-DIRECT-INFERENCE-TRIGGER", "MSFT", MSFT_BOUND, summary=_summary(A102=("candidate", 34.9)), matches=_matches(matched=["A102"] * 3)
    )
    assert (nvda["verdict"], nvda["blocking"], nvda["blocks_release"]) == ("fail", True, True)
    assert (msft["verdict"], msft["blocking"], msft["blocks_release"]) == ("fail", False, False)
    assert gold.release_impact([nvda])["blocks_release"] is True
    impact = gold.release_impact([msft])
    assert impact["blocks_release"] is False and impact["release_status"] == gold.RELEASE_NO_BLOCKER_AMONG_EXECUTED
    assert impact["non_blocking_findings"] == [{"rule_id": "MSFT-A102-DIRECT-INFERENCE-TRIGGER", "verdict": "fail", "reason_code": None}]


def test_an_unevaluated_blocking_rule_blocks_certification_but_is_not_a_failure():
    rule = _alpha_rule("NVDA-A304-VALUATION-RISK", "NVDA", NVDA_PINNED, summary=_summary(A304=("dominant", 71.7)), matches=_matches(matched=["A304"] * 3))
    impact = gold.release_impact([rule])
    assert impact["blocks_release"] is False and impact["blocking_unresolved"] == ["NVDA-A304-VALUATION-RISK"]
    assert impact["release_status"] == gold.RELEASE_UNRESOLVED
    non_blocking = _alpha_rule(
        "MSFT-A102-DIRECT-INFERENCE-TRIGGER", "MSFT", MSFT_PINNED, summary=_summary(A102=("candidate", 41.9)), matches=_matches(matched=["A102"])
    )
    assert gold.release_impact([non_blocking])["release_status"] == gold.RELEASE_NO_BLOCKER_AMONG_EXECUTED  # a non-blocking rule never blocks


def test_the_ticker_verdict_consumes_the_severity_the_contract_fixed():
    bad_nvda = _verdict("NVDA", NVDA_BOUND, summary=_summary(A101=("candidate", 48.0), A304=("active", 67.0)), matches=_matches(matched=["A101", "A304"]))
    assert bad_nvda["formal_status"] == "fail" and bad_nvda["release"]["blocks_release"] is True
    (reason,) = [r for r in bad_nvda["failure_reasons"] if r.get("rule_id")]
    assert (reason["rule_id"], reason["blocking"], reason["blocks_release"]) == ("NVDA-A101-AI-GROWTH", True, True)
    bad_msft = _verdict("MSFT", MSFT_BOUND, summary=_summary(A102=("candidate", 34.9)), matches=_matches(matched=["A102"]))
    assert bad_msft["formal_status"] == "fail" and bad_msft["release"]["blocks_release"] is False
    (reason,) = [r for r in bad_msft["failure_reasons"] if r.get("rule_id")]
    assert (reason["blocking"], reason["blocks_release"]) == (False, False)


# ---------------------------------------------------------------------------------------------------------------------------------------
# 6. composite rules: ANY ONE allowed pair satisfies; no allowed pair is individually required
# ---------------------------------------------------------------------------------------------------------------------------------------


def test_one_admitted_allowed_pair_satisfies_the_composite_the_other_need_not_appear():
    for admitted in (["A101__A304"], ["A301__A304"], ["A101__A304", "A301__A304"]):
        rule = _composite("NVDA-GROWTH-VS-VALUATION-CONFLICT", "NVDA", NVDA_BOUND, admitted=admitted)
        assert rule["verdict"] == "pass", admitted
        assert rule["requirement"]["logic"].startswith("any ONE allowed pair")


def test_a_present_composite_with_nothing_admitted_is_a_review_that_needs_adjudication_not_a_failure():
    rule = _composite("NVDA-GROWTH-VS-VALUATION-CONFLICT", "NVDA", NVDA_BOUND, admitted=[])
    assert rule["verdict"] == "needs_review" and rule["reason_code"] == gold.REASON_NO_ALLOWED_PAIR_ADMITTED and rule["requires_adjudication"] is True
    assert rule["blocks_release"] is False and rule["unresolved_blocking"] is True  # NVDA's composite is blocking, so the review is unresolved-blocking


def test_an_admitted_conflict_outside_the_allowed_family_keeps_the_research_output_and_routes_to_review():
    rule = _composite("NVDA-GROWTH-VS-VALUATION-CONFLICT", "NVDA", NVDA_BOUND, admitted=["A304__A601"])
    assert rule["verdict"] == "needs_review" and rule["reason_code"] == gold.REASON_ADMITTED_OUTSIDE_FAMILY
    assert rule["admitted_outside_allowed_family"] == ["A304__A601"]


def test_the_composite_trigger_is_the_matrixs_not_the_runs_levels_and_an_unbound_run_is_not_evaluable():
    rule = _composite("NVDA-GROWTH-VS-VALUATION-CONFLICT", "NVDA", NVDA_PINNED, admitted=["A301__A304"])
    assert rule["verdict"] == "not_evaluable" and rule["reason_code"] == gold.REASON_RUN_NOT_BOUND
    assert rule["admitted_in_allowed_family"] == ["A301__A304"]  # recorded as a fact; with the trigger unknown it satisfies nothing


def test_amds_allowed_family_is_the_one_Johns_later_baseline_fixes_and_it_adds_a201_a304():
    contract_only = _composite("AMD-AI-GROWTH-VS-VALUATION", "AMD", AMD_BOUND, admitted=["A201__A304"])
    assert contract_only["verdict"] == "needs_review"  # the contract's own two pairs do not include it
    with_baseline = _composite("AMD-AI-GROWTH-VS-VALUATION", "AMD", AMD_BOUND, admitted=["A201__A304"], family=["A101__A304", "A201__A304", "A301__A304"])
    assert with_baseline["verdict"] == "pass" and with_baseline["allowed_family"] == ["A101__A304", "A201__A304", "A301__A304"]


def test_a_composite_whose_frozen_trigger_is_absent_forces_no_conflict(tmp_path):
    paths = _variant(tmp_path, matrix_edit=lambda m: m["tickers"]["NVDA"]["rules"][3].update(trigger_state="ABSENT"), refreeze=False)
    bundle = _bundle(**paths, expected_matrix_sha256=None)
    rule = _composite("NVDA-GROWTH-VS-VALUATION-CONFLICT", "NVDA", NVDA_BOUND, admitted=[], bundle=bundle)
    assert rule["verdict"] == "not_triggered" and rule["blocks_release"] is False


def _pair_record(state, *, b2_status=None, b2=(), entry=()):
    return {"state": state, "b2_status": b2_status, "b2_reason_codes": list(b2), "entry_reason_codes": list(entry)}


def _composite_with_records(rule_id, ticker, run_id, records, *, admitted=(), bundle=None):
    bundle = bundle or _bundle()
    return gold.evaluate_composite_rule(
        bundle,
        bundle.rules_by_id[rule_id],
        ticker=ticker,
        run_id=run_id,
        admitted_conflicts=admitted,
        main_conflict=None,
        allowed_family=(),
        pair_records=records,
    )


def test_the_pair_states_the_composite_reads_are_the_engines_own():
    assert gold.PAIR_STATE_B2_NO_REASON == engine.PAIR_STATE_B2_NO_REASON
    assert gold.PAIR_STATE_NO_RECORD == engine.PAIR_STATE_NO_RECORD


def test_a_present_composite_whose_allowed_pairs_were_all_rejected_by_b2_is_a_review_that_says_why_and_not_a_failure():
    records = {
        "A101__A304": _pair_record("b2_rejected", b2_status="candidate", b2=["BULL_SCORE_BELOW_THRESHOLD"]),
        "A301__A304": _pair_record("b2_rejected", b2_status="candidate", b2=["NO_BULL_TICKER_SPECIFIC_SUPPORT"]),
    }
    rule = _composite_with_records("NVDA-GROWTH-VS-VALUATION-CONFLICT", "NVDA", NVDA_BOUND, records)
    assert (rule["verdict"], rule["reason_code"], rule["requires_adjudication"]) == ("needs_review", gold.REASON_NO_ALLOWED_PAIR_ADMITTED, True)
    assert "BULL_SCORE_BELOW_THRESHOLD" in rule["detail"] and "NO_BULL_TICKER_SPECIFIC_SUPPORT" in rule["detail"]
    assert rule["family_pair_records"]["A301__A304"]["b2_reason_codes"] == ["NO_BULL_TICKER_SPECIFIC_SUPPORT"]
    assert rule["blocks_release"] is False and rule["unresolved_blocking"] is True


def test_a_composite_family_pair_with_no_arbitration_record_is_listed_as_having_none():
    rule = _composite_with_records("NVDA-GROWTH-VS-VALUATION-CONFLICT", "NVDA", NVDA_BOUND, {})
    assert {p: r["state"] for p, r in rule["family_pair_records"].items()} == {"A101__A304": "no_arbitration_record", "A301__A304": "no_arbitration_record"}
    assert rule["verdict"] == "needs_review" and "no_arbitration_record" in rule["detail"]


def test_controlled_modification_an_allowed_pair_that_meets_every_b2_condition_yet_is_not_admitted_is_a_deterministic_violation():
    """NOT a production B2 result (B2 writes a rejection reason for every pair it does not admit): the artifact "already proves a deterministic
    violation" of the contract, which John's Step-4 text keeps apart from the gap that merely needs adjudication."""
    records = {
        "A101__A304": _pair_record("b2_rejected", b2_status="candidate", b2=["BULL_SCORE_BELOW_THRESHOLD"]),
        "A301__A304": _pair_record("b2_not_admitted_without_reason", b2_status="candidate"),
    }
    nvda = _composite_with_records("NVDA-GROWTH-VS-VALUATION-CONFLICT", "NVDA", NVDA_BOUND, records)
    assert (nvda["verdict"], nvda["reason_code"]) == ("fail", gold.REASON_ALLOWED_PAIR_COMPLETE_NOT_ADMITTED)
    assert nvda["blocking"] is True and nvda["blocks_release"] is True and "A301__A304" in nvda["detail"]
    amd = _composite_with_records("AMD-AI-GROWTH-VS-VALUATION", "AMD", AMD_BOUND, {"A101__A304": records["A301__A304"]})
    assert amd["verdict"] == "fail" and amd["blocking"] is False and amd["blocks_release"] is False  # the contract's severity, not an upgrade
    # an allowed pair that IS admitted satisfies the composite: the violation does not outvote "any one"
    admitted = _composite_with_records("NVDA-GROWTH-VS-VALUATION-CONFLICT", "NVDA", NVDA_BOUND, records, admitted=["A101__A304"])
    assert admitted["verdict"] == "pass"


def test_through_the_unified_entry_a_composite_violation_is_a_blocking_failure_of_the_ticker():
    conflict_payload = {
        "conflicts": [],
        "arbitration": {
            "candidate_evaluations": [
                {
                    "alpha_a": "A301",
                    "alpha_b": "A304",
                    "outcome": "suppressed",  # CONTROLLED MODIFICATION: a candidate with no rejection reason
                    "reason_codes": [],
                    "admissibility": {"status": "candidate", "reason_codes": [], "bull_supporting_evidence_count": 3, "bear_supporting_evidence_count": 3},
                }
            ]
        },
    }
    verdict = run_formal_acceptance(
        ticker="NVDA",
        ticker_v2_label=ticker_label_v2(load_j2_labels_v2(), "NVDA"),
        label_block_v1=ticker_label(load_j2_labels(), "NVDA"),
        evaluate_ticker_result=_evaluate_ticker_result("NVDA", NVDA_BOUND),
        conflict_payload=conflict_payload,
        graph_payload={},
        alpha_matches_payload=_matches(matched=["A101", "A304"]),
        activation_summary=_summary(A101=("active", 70.0), A304=("active", 67.0)),
    )
    assert verdict["formal_status"] == "fail" and verdict["release"]["release_status"] == "blocked"
    (reason,) = [r for r in verdict["failure_reasons"] if r.get("rule_id")]
    assert (reason["rule_id"], reason["blocking"], reason["blocks_release"]) == ("NVDA-GROWTH-VS-VALUATION-CONFLICT", True, True)


def _rejected_candidate_payload(pairs):
    """SYNTHETIC: every pair evaluated by B2 and rejected for a recorded reason, with a supporting fact on each side."""
    return {
        "conflicts": [],
        "arbitration": {
            "candidate_evaluations": [
                {
                    "alpha_a": pair.split("__")[0],
                    "alpha_b": pair.split("__")[1],
                    "outcome": "suppressed",
                    "reason_codes": ["BULL_SCORE_BELOW_THRESHOLD"],
                    "admissibility": {
                        "status": "candidate",
                        "reason_codes": ["BULL_SCORE_BELOW_THRESHOLD"],
                        "bull_supporting_evidence_count": 3,
                        "bear_supporting_evidence_count": 3,
                        "bull_score": 40.0,
                        "bear_score": 70.0,
                    },
                }
                for pair in pairs
            ]
        },
    }


def test_the_sixteen_allowed_relations_create_no_expectation_the_conditional_ones_only_leave_a_diagnostic():
    """The 16 allowed relations are permissions, never mandatory outputs. With NONE of them admitted -- every one evaluated by B2 and rejected, with
    supporting evidence on both sides and a reliable stance -- no label-based rule fails or asks for review on their account; the pair-level
    should_detect reading leaves a diagnostic and the formal status is exactly what it is without those records."""
    labels = load_j2_labels_v2()
    carried_by_ticker = {t: sorted(set(b["required_conflicts"]) | set(b["conditional_conflicts"]) | set(b["allowed_conflicts"])) for t, b in labels["tickers"].items()}
    assert sum(len(v) for v in carried_by_ticker.values()) == 16
    diagnostics = 0
    for ticker, carried in carried_by_ticker.items():
        label_v2, label_v1 = ticker_label_v2(labels, ticker), ticker_label(load_j2_labels(), ticker)

        def judge(payload, ticker=ticker, label_v2=label_v2, label_v1=label_v1):
            return run_formal_acceptance(
                ticker=ticker,
                ticker_v2_label=label_v2,
                label_block_v1=label_v1,
                evaluate_ticker_result=_evaluate_ticker_result(ticker, "not-a-bound-run"),
                conflict_payload=payload,
                graph_payload={},
                alpha_matches_payload=_matches(matched=["A601"]),
                activation_summary=_summary(),
            )

        with_records = judge(_rejected_candidate_payload(carried))
        without_records = judge({"conflicts": [], "arbitration": {"candidate_evaluations": []}})
        assert with_records["failure_reasons"] == []
        assert not [r for r in with_records["review_reasons"] if r.get("pair") in carried], ticker
        assert with_records["formal_status"] == without_records["formal_status"], ticker
        findings = with_records["diagnostic_findings"]
        assert {f["pair"] for f in findings} == set(label_v2["conditional_conflicts"]), ticker
        assert all(f["decides_formal_status"] is False and "B2 rejected it for BULL_SCORE_BELOW_THRESHOLD" in f["detail"] for f in findings)
        diagnostics += len(findings)
    assert diagnostics == 10  # exactly the ten pairs the label files under conditional_conflicts; the six allowed_conflicts pairs leave nothing at all


# ---------------------------------------------------------------------------------------------------------------------------------------
# 7. HISTORICAL INPUTS: the repository's saved runs, read-only
# ---------------------------------------------------------------------------------------------------------------------------------------


def _step4_rows() -> dict[str, str]:
    """John's own Step-4 table: rule id -> result column."""
    rows = {}
    for line in STEP4_TABLE.read_text(encoding="utf-8").splitlines():
        cells = [c.strip() for c in line.strip().strip("|").split("|")]
        if len(cells) >= 5 and re.fullmatch(r"[A-Z]+-[A-Z0-9-]+", cells[0]):
            rows[cells[0]] = cells[4].replace("*", "")
    return rows


@pytest.fixture(scope="module")
def bound_entries():
    return {
        ticker: report.evaluate_saved_run(ticker=ticker, run_id=run_id, runs_root=RUNS_ROOT)
        for ticker, run_id in (("NVDA", NVDA_BOUND), ("MSFT", MSFT_BOUND), ("AMD", AMD_BOUND))
    }


@pytest.fixture(scope="module")
def pinned_entries():
    return {ticker: report.evaluate_saved_run(ticker=ticker, run_id=run_id, runs_root=RUNS_ROOT) for ticker, run_id in report.DEFAULT_SIX_TICKER_RUNS.items()}


def _rules(entry) -> dict:
    return {r["rule_id"]: r for r in entry["verdict"]["contract_rule_results"]}


def test_on_the_runs_the_matrix_is_bound_to_the_executor_reproduces_Johns_step_4_rows(bound_entries):
    step4 = _step4_rows()
    nvda, msft, amd = (_rules(bound_entries[t]) for t in ("NVDA", "MSFT", "AMD"))
    expected = {
        "NVDA-A101-AI-GROWTH": nvda,
        "NVDA-A304-VALUATION-RISK": nvda,
        "NVDA-GROWTH-VS-VALUATION-CONFLICT": nvda,
        "MSFT-A102-DIRECT-INFERENCE-TRIGGER": msft,
        "AMD-AI-GROWTH-VS-VALUATION": amd,
    }
    for rule_id, rules in expected.items():
        assert step4[rule_id] in ("PASS", "FAIL"), (rule_id, step4.get(rule_id))
        assert rules[rule_id]["john_result"] == step4[rule_id], (rule_id, rules[rule_id]["john_result"], step4[rule_id])
    assert (nvda["NVDA-A101-AI-GROWTH"]["alpha_recognition"][0]["activation_level"], nvda["NVDA-A101-AI-GROWTH"]["alpha_recognition"][0]["activation_score"]) == ("active", 70.0)
    miss = msft["MSFT-A102-DIRECT-INFERENCE-TRIGGER"]
    assert (miss["blocking"], miss["blocks_release"]) == (False, False)
    assert miss["alpha_recognition"][0]["activation_level"] == "candidate" and miss["alpha_recognition"][0]["identification_state"] == gold.IDENTIFIED
    assert bound_entries["MSFT"]["verdict"]["release"]["blocks_release"] is False


def test_on_the_six_pinned_runs_only_sndk_is_the_run_the_matrix_is_bound_to_so_the_other_contract_rules_are_not_evaluable(pinned_entries):
    bound = gold.load_gold_contract_bundle().matrix_runs
    assert {t: bound[t] == run_id for t, run_id in report.DEFAULT_SIX_TICKER_RUNS.items()} == {
        "NVDA": False,
        "QQQ": False,
        "SNDK": True,
        "MSFT": False,
        "TSM": False,
        "AMD": False,
    }
    for ticker in ("NVDA", "MSFT", "AMD"):
        for rule in pinned_entries[ticker]["verdict"]["contract_rule_results"]:
            assert rule["verdict"] == "not_evaluable" and rule["reason_code"] == gold.REASON_RUN_NOT_BOUND, rule["rule_id"]
            assert rule["evidence_trigger"]["strength"] is None
    for ticker in ("QQQ", "SNDK", "TSM"):
        assert pinned_entries[ticker]["verdict"]["contract_rule_results"] == []  # no executed contract rule belongs to them


def test_on_the_pinned_runs_the_four_facts_are_recorded_separately(pinned_entries):
    nvda = _rules(pinned_entries["NVDA"])
    a101 = nvda["NVDA-A101-AI-GROWTH"]["alpha_recognition"][0]
    assert (a101["identification_state"], a101["activation_level"], a101["activation_score"]) == (gold.IDENTIFIED, "candidate", 48.5501)
    assert a101["claims_matched_to_this_alpha"] > 0 and a101["level_is_official_detected_level"] is False
    assert nvda["NVDA-A101-AI-GROWTH"]["requirement"]["satisfied"] is False  # a fact about the level...
    assert nvda["NVDA-A101-AI-GROWTH"]["evidence_trigger"]["state"] == "NOT_EVALUABLE"  # ...kept apart from the trigger, which is unknown for this run
    a304 = nvda["NVDA-A304-VALUATION-RISK"]["alpha_recognition"][0]
    assert (a304["activation_level"], a304["level_is_official_detected_level"]) == ("dominant", True)
    msft = _rules(pinned_entries["MSFT"])["MSFT-A102-DIRECT-INFERENCE-TRIGGER"]["alpha_recognition"][0]
    assert (msft["identification_state"], msft["activation_level"]) == (gold.IDENTIFIED, "candidate")


def test_the_pinned_verdicts_do_not_change_because_of_a_historical_trigger_that_was_never_theirs(pinned_entries):
    # an unevaluated rule is a review item, never a pass and never a fail: the tickers keep the status their other findings give them
    assert {t: e["verdict"]["formal_status"] for t, e in pinned_entries.items()} == {
        "NVDA": "needs_review",
        "QQQ": "needs_review",
        "SNDK": "pass",
        "MSFT": "needs_review",
        "TSM": "needs_review",
        "AMD": "needs_review",
    }
    assert pinned_entries["NVDA"]["verdict"]["release"]["release_status"] == gold.RELEASE_UNRESOLVED
    assert all(not e["verdict"]["release"]["blocks_release"] for e in pinned_entries.values())


def test_the_nvda_reference_runs_observed_main_conflict_matches_its_saved_one_and_it_is_not_a_rule(pinned_entries):
    """label v0.2 NVDA.run_bound_expectations: reference run e3eb3909, observed main conflict A301__A304. The label itself says no formal approval exists
    for it, and J2 v0.2 allows a run-bound expectation to be strict only when fully bound AND approved: it is reported as the unapproved historical
    observation it is, and decides nothing -- on the pinned run (not the reference run) and on the reference run alike."""
    reference = "e3eb3909-3744-4a02-9b32-b225cf6ef665"
    observation = pinned_entries["NVDA"]["verdict"]["run_bound_observation"]
    assert observation["classification"] == "unapproved_historical_observation" and observation["executable"] is False
    assert observation["reference_run_id"] == reference and observation["evaluated_run_is_the_reference_run"] is False
    assert observation["effect_on_formal_status"] == "none"
    on_reference = report.evaluate_saved_run(ticker="NVDA", run_id=reference, runs_root=RUNS_ROOT)
    assert on_reference["verdict"]["run_bound_observation"]["evaluated_run_is_the_reference_run"] is True
    assert on_reference["main_conflict"] == observation["observed_historical_main_conflict"] == "A301__A304"  # what the label observed is what the run saved
    assert "run_bound_observation" not in pinned_entries["QQQ"]["verdict"]  # only a ticker that declares one has one


def test_the_executor_never_touches_the_saved_run(tmp_path):
    source = RUNS_ROOT / NVDA_BOUND
    copy_root = tmp_path / "runs"
    shutil.copytree(source, copy_root / NVDA_BOUND)

    def tree(root):
        return {str(p.relative_to(root)): hashlib.sha256(p.read_bytes()).hexdigest() for p in sorted(root.rglob("*")) if p.is_file()}

    before = tree(copy_root)
    entry = report.evaluate_saved_run(ticker="NVDA", run_id=NVDA_BOUND, runs_root=copy_root)
    assert entry["verdict"]["contract_rule_results"][0]["verdict"] == "pass"
    assert tree(copy_root) == before


def test_a_replay_under_another_run_id_changes_no_research_fact_and_only_the_run_bound_trigger_becomes_not_evaluable(tmp_path):
    """John's scenario 7 ("同一输入做纯 replay，只更换执行编号 -> 不因 run_id 变化产生无依据的研究结论变化") against the new run-bound trigger. The frozen matrix
    is bound to a run id BY DESIGN, so the same saved run under another id loses its trigger -- it is not evaluable, never a pass, never a fail. What
    the replay carries is unchanged: the Alpha facts (identification, level, score) and the admitted conflicts are byte-for-byte the same."""
    replay_root = tmp_path / "runs"
    shutil.copytree(RUNS_ROOT / NVDA_BOUND, replay_root / "replay-of-the-bound-run")
    original = report.evaluate_saved_run(ticker="NVDA", run_id=NVDA_BOUND, runs_root=RUNS_ROOT)
    replay = report.evaluate_saved_run(ticker="NVDA", run_id="replay-of-the-bound-run", runs_root=replay_root)
    original_rules, replay_rules = _rules(original), _rules(replay)
    assert original["admitted_conflicts"] == replay["admitted_conflicts"] and original["main_conflict"] == replay["main_conflict"]
    for rule_id in ("NVDA-A101-AI-GROWTH", "NVDA-A304-VALUATION-RISK"):
        assert original_rules[rule_id]["alpha_recognition"] == replay_rules[rule_id]["alpha_recognition"]
        assert original_rules[rule_id]["verdict"] == "pass"
        assert replay_rules[rule_id]["verdict"] == "not_evaluable" and replay_rules[rule_id]["reason_code"] == gold.REASON_RUN_NOT_BOUND
    assert replay["verdict"]["undeclared_admitted_conflicts"] == original["verdict"]["undeclared_admitted_conflicts"]


def test_the_contract_modules_are_not_imported_by_anything_that_runs_before_the_research_is_complete():
    importers = [
        p.relative_to(REPO).as_posix()
        for p in sorted((REPO / "comqutor_alpha").rglob("*.py"))
        if "gold_contract_rules" in p.read_text(encoding="utf-8") and p.name != "gold_contract_rules.py"
    ]
    assert importers == ["comqutor_alpha/regression/acceptance_engine.py"]
    assert engine.TICKER_RULE_KEY_ROLES["run_bound_expectations"].startswith("unapproved run-bound historical observation")
