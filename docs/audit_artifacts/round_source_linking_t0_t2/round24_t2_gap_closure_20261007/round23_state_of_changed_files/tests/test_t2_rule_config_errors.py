"""T2 (2026-10-07), John's task sheet section 4, "第三，统一正式验收入口":

    正式验收显式读取指定规则文件和 taxonomy，不允许静默回退到旧版本。程序输出解析后的 effective_rules ...
    规则缺失、类型未实现或 taxonomy 不兼容，应输出配置／执行错误，不能改成 NOT_APPLICABLE 后继续 PASS。

Each test below pins one of the silent-pass paths a 2026-10-07 audit reproduced, plus the two scenario tests ("有明确支持证据，却漏掉必须识别的
Alpha" / "没有支持证据") at the level of the FINAL formal_status -- before, they only exercised one sub-function.

SYNTHETIC FIXTURES: the label / taxonomy variants and the conflict payloads below are built by hand to exercise error paths and rule logic. They
are NOT real market data and must never be counted as real validation (the real six-ticker verdicts come from scripts/run_formal_acceptance.py).
Zero Provider calls; every file written lives under tmp_path.
"""

from __future__ import annotations

import copy
import json
from pathlib import Path

import pytest
import yaml

from comqutor_alpha.api import formal_acceptance_artifact as wiring
from comqutor_alpha.regression import acceptance_engine as engine
from comqutor_alpha.regression.acceptance_engine import (
    FORMAL_STATUS_CONFIG_ERROR,
    FORMAL_STATUS_EXECUTION_ERROR,
    AcceptanceConfigError,
    effective_rules,
    run_formal_acceptance,
)

REPO = Path(__file__).resolve().parents[1]
TAXONOMY = REPO / "comqutor_alpha" / "alpha_library" / "alpha_taxonomy_v1.yaml"
LABELS_V2 = REPO / "comqutor_alpha" / "config" / "j2_provisional_regression_labels_v0.2.yaml"
LABELS_V1 = REPO / "comqutor_alpha" / "config" / "j2_provisional_regression_labels_v0.1.yaml"


def _load(path: Path) -> dict:
    return yaml.safe_load(path.read_text(encoding="utf-8"))


def _dump(tmp_path: Path, name: str, data: dict) -> Path:
    path = tmp_path / name
    path.write_text(yaml.safe_dump(data, allow_unicode=True, sort_keys=False), encoding="utf-8")
    return path


def _reason_of(**kwargs) -> str:
    with pytest.raises(AcceptanceConfigError) as info:
        effective_rules(**kwargs)
    return info.value.reason_code


# ---------------------------------------------------------------------------------------------------------------------------------------
# effective_rules(): what it reports about the files it resolved
# ---------------------------------------------------------------------------------------------------------------------------------------


def test_effective_rules_names_every_rule_file_by_repository_relative_path_and_hash():
    rules = effective_rules()
    for key in ("taxonomy", "label_v2", "label_v1"):
        assert not rules[key]["path"].startswith("/"), f"{key} path must not carry an engineer's absolute path"
        assert len(rules[key]["sha256"]) == 64
    assert rules["taxonomy"]["schema_version"] == rules["label_v2"]["taxonomy_version"]
    assert rules["taxonomy"]["content_version"] == rules["label_v2"]["taxonomy_content_version"]
    # the authority of the rule file is part of its identity: a provisional/shadow file must never read as an approved one
    assert rules["label_v2"]["evaluation_mode"] == "shadow"
    assert rules["label_v2"]["formal_product_owner_approval"] == "pending"
    # six families, each with the five facts the task sheet asks for
    assert set(rules["rule_families"]) == set(engine.ALL_RULE_FAMILIES)
    for family in rules["rule_families"].values():
        assert {"config_source", "applicable_target", "execution_function", "trigger_condition", "verdict_result"} <= set(family)
    # what is declared but evaluated by no family is said out loud
    assert "run_bound_expectations" in rules["declared_but_not_evaluated"]


def test_every_ticker_block_key_in_the_real_label_file_is_an_implemented_rule_key():
    label = _load(LABELS_V2)
    used = {key for block in label["tickers"].values() for key in block}
    assert used <= engine.IMPLEMENTED_TICKER_RULE_KEYS


# ---------------------------------------------------------------------------------------------------------------------------------------
# E1 / E2: taxonomy incompatibility and version mismatch are configuration errors (never silently accepted)
# ---------------------------------------------------------------------------------------------------------------------------------------


def test_a_taxonomy_that_lacks_the_pairs_the_label_declares_is_a_config_error_not_a_silent_acceptance(tmp_path):
    taxonomy = _load(TAXONOMY)
    for alpha in taxonomy["alphas"]:
        if alpha["alpha_id"] in ("A102", "A201"):
            alpha["conflict_alphas"] = []
        if alpha["alpha_id"] == "A304":
            alpha["conflict_alphas"] = [c for c in alpha["conflict_alphas"] if c["alpha_id"] not in ("A102", "A201")]
    old_style_taxonomy = _dump(tmp_path, "taxonomy_without_the_t2_pairs.yaml", taxonomy)

    # The label file (default) lists A102__A304 / A201__A304 as conditional pairs. Before 2026-10-07 the label was validated against the DEFAULT
    # taxonomy even when another one was named, so this passed silently.
    assert _reason_of(taxonomy_path=old_style_taxonomy) == engine.REASON_TAXONOMY_INCOMPATIBLE_WITH_LABELS


def test_a_taxonomy_without_a_content_version_is_a_config_error(tmp_path):
    taxonomy = _load(TAXONOMY)
    del taxonomy["content_version"]
    path = _dump(tmp_path, "taxonomy_no_content_version.yaml", taxonomy)
    assert _reason_of(taxonomy_path=path) == engine.REASON_TAXONOMY_CONTENT_VERSION_MISSING


def test_a_taxonomy_with_another_content_version_than_the_label_expects_is_a_config_error(tmp_path):
    taxonomy = _load(TAXONOMY)
    taxonomy["content_version"] = "9.9.9"
    path = _dump(tmp_path, "taxonomy_other_content_version.yaml", taxonomy)
    assert _reason_of(taxonomy_path=path) == engine.REASON_TAXONOMY_CONTENT_VERSION_MISMATCH


def test_a_taxonomy_with_another_schema_version_than_the_label_expects_is_a_config_error(tmp_path):
    taxonomy = _load(TAXONOMY)
    taxonomy["schema_version"] = "alpha_taxonomy_v999"
    path = _dump(tmp_path, "taxonomy_other_schema_version.yaml", taxonomy)
    assert _reason_of(taxonomy_path=path) == engine.REASON_TAXONOMY_VERSION_MISMATCH


def test_a_label_file_that_claims_another_taxonomy_version_is_a_config_error(tmp_path):
    label = _load(LABELS_V2)
    label["taxonomy_version"] = "alpha_taxonomy_v999"
    assert _reason_of(label_v2_path=_dump(tmp_path, "label_other_taxonomy_version.yaml", label)) == engine.REASON_TAXONOMY_VERSION_MISMATCH


def test_a_label_file_without_a_taxonomy_content_version_is_a_config_error(tmp_path):
    label = _load(LABELS_V2)
    del label["taxonomy_content_version"]
    assert (
        _reason_of(label_v2_path=_dump(tmp_path, "label_no_content_version.yaml", label))
        == engine.REASON_LABEL_TAXONOMY_CONTENT_VERSION_MISSING
    )


def test_a_label_file_written_against_another_taxonomy_content_version_is_a_config_error(tmp_path):
    label = _load(LABELS_V2)
    label["taxonomy_content_version"] = "1.0.0"
    assert (
        _reason_of(label_v2_path=_dump(tmp_path, "label_old_content_version.yaml", label))
        == engine.REASON_TAXONOMY_CONTENT_VERSION_MISMATCH
    )


# ---------------------------------------------------------------------------------------------------------------------------------------
# E3: a rule type this engine does not implement is refused, not ignored
# ---------------------------------------------------------------------------------------------------------------------------------------


def test_a_rule_key_the_engine_does_not_implement_is_a_config_error_that_names_it(tmp_path):
    label = _load(LABELS_V2)
    label["tickers"]["NVDA"]["must_detect_alphas_if_evidence_present"] = ["A301"]
    path = _dump(tmp_path, "label_unknown_rule_key.yaml", label)
    with pytest.raises(AcceptanceConfigError) as info:
        effective_rules(label_v2_path=path)
    assert info.value.reason_code == engine.REASON_RULE_TYPE_NOT_IMPLEMENTED
    assert "must_detect_alphas_if_evidence_present" in info.value.detail
    assert "NVDA" in info.value.detail


# ---------------------------------------------------------------------------------------------------------------------------------------
# Two copies of one rule (the dominance guard lives in v0.1 AND v0.2) must not diverge silently
# ---------------------------------------------------------------------------------------------------------------------------------------


def test_the_two_copies_of_the_dominance_guard_are_equal_in_the_real_files():
    assert effective_rules()  # raises ACCEPTANCE_RULE_SOURCES_DISAGREE otherwise


def test_diverging_copies_of_the_dominance_guard_are_refused(tmp_path):
    label_v1 = _load(LABELS_V1)
    label_v1["tickers"]["NVDA"]["should_not_be_dominant_without_strong_evidence"]["A102"] = "a condition nobody agreed to"
    assert _reason_of(label_v1_path=_dump(tmp_path, "label_v1_diverged.yaml", label_v1)) == engine.REASON_RULE_SOURCES_DISAGREE


# ---------------------------------------------------------------------------------------------------------------------------------------
# E5: a ticker the rule file says nothing about is never a PASS
# ---------------------------------------------------------------------------------------------------------------------------------------

HEALTHY_MATCHES = {"matches": [{"claim_id": "c1", "match_status": "matched", "matched_alpha": "A101"}]}
EMPTY_LABEL = {
    "required_conflicts": [],
    "conditional_conflicts": [],
    "allowed_conflicts": [],
    "product_decision_pending": [],
    "remove_while_undeclared": [],
    "structural_expectations": {},
}


def _evaluate_ticker_result(*, admitted=(), candidate=(), stance_source="llm_semantic") -> dict:
    return {
        "ticker": "TEST",
        "run_selection_status": "selected",
        "offline_reprocess_status": "completed",
        "artifact_completeness": "pass",
        "artifact_missing_files": [],
        "admitted_conflicts": list(admitted),
        "candidate_conflicts": list(candidate),
        "stance_source": stance_source,
    }


def _entry(alpha_a, alpha_b, *, outcome, status, bull, bear) -> dict:
    return {
        "alpha_a": alpha_a,
        "alpha_b": alpha_b,
        "outcome": outcome,
        "admissibility": {
            "status": status,
            "reason_codes": [],
            "bull_supporting_evidence_count": bull,
            "bear_supporting_evidence_count": bear,
            "bull_score": 80.0,
            "bear_score": 80.0,
        },
    }


def _verdict(label, *, entries=(), admitted=(), candidate=(), label_block_v1=None, **kwargs) -> dict:
    return run_formal_acceptance(
        ticker="TEST",
        ticker_v2_label=label,
        label_block_v1=label_block_v1 if label_block_v1 is not None else {},
        evaluate_ticker_result=_evaluate_ticker_result(admitted=admitted, candidate=candidate),
        conflict_payload={"arbitration": {"candidate_evaluations": list(entries)}},
        graph_payload={},
        alpha_matches_payload=HEALTHY_MATCHES,
        **kwargs,
    )


def test_a_ticker_with_no_declared_rules_is_a_config_error_never_a_pass():
    result = _verdict(None)
    assert result["formal_status"] == FORMAL_STATUS_CONFIG_ERROR
    assert result["config_error_reason_code"] == engine.REASON_TICKER_RULES_NOT_DECLARED
    assert "TEST" in result["config_error_detail"]
    assert result["rule_family_results"] == {}
    assert "effective_rules" in result  # the rule files themselves resolved fine; only this ticker has nothing


def test_an_empty_but_declared_rule_block_is_not_the_same_as_no_rules_at_all():
    result = _verdict(copy.deepcopy(EMPTY_LABEL))
    assert result["formal_status"] == "pass"
    assert result["coverage"]["pass_is_vacuous"] is True  # ...but a PASS that exercised nothing says so


def test_conflicting_dominance_guards_handed_to_one_verdict_are_refused():
    label = {**EMPTY_LABEL, "should_not_be_dominant_without_strong_evidence": {"A001": "rate evidence"}}
    result = _verdict(label, label_block_v1={"should_not_be_dominant_without_strong_evidence": {"A001": "something else"}})
    assert result["formal_status"] == FORMAL_STATUS_CONFIG_ERROR
    assert result["config_error_reason_code"] == engine.REASON_RULE_SOURCES_DISAGREE


# ---------------------------------------------------------------------------------------------------------------------------------------
# John's scenarios (a) and (b) at the level of the FINAL formal_status
# ---------------------------------------------------------------------------------------------------------------------------------------


def test_scenario_a_a_required_pair_with_evidence_on_both_sides_that_was_not_admitted_is_a_formal_fail():
    label = {**EMPTY_LABEL, "required_conflicts": ["A101__A304"]}
    entries = [_entry("A101", "A304", outcome="suppressed", status="candidate", bull=3, bear=3)]
    result = _verdict(label, entries=entries, candidate=["A101__A304"])
    assert result["formal_status"] == "fail"
    assert [(r["family"], r["pair"]) for r in result["failure_reasons"]] == [("must_detect_if_evidence_present", "A101__A304")]
    assert result["coverage"]["pass_is_vacuous"] is False


def test_scenario_b_a_required_pair_without_supporting_evidence_is_never_forced_into_a_fail():
    label = {**EMPTY_LABEL, "required_conflicts": ["A101__A304"]}
    result = _verdict(label, entries=[])  # the pair never even reached arbitration: nothing to require detection of
    assert result["rule_family_results"]["must_detect_if_evidence_present"][0]["verdict"] == "not_applicable"
    assert result["formal_status"] != "fail"
    assert result["failure_reasons"] == []
    # The legacy v0.2 contract view still reads "required and not admitted -> fail" unconditionally. It is report-only and says so: the verdict
    # follows the rule families. (Before 2026-10-07 this view leaked into formal_status and forced a fail here.)
    assert result["v2_contract_result"]["ticker_status"] == "fail"
    assert "report only" in result["v2_contract_note"]


def test_scenario_b_one_sided_evidence_is_not_enough_to_force_a_fail():
    label = {**EMPTY_LABEL, "required_conflicts": ["A101__A304"]}
    entries = [_entry("A101", "A304", outcome="suppressed", status="candidate", bull=2, bear=0)]
    result = _verdict(label, entries=entries, candidate=["A101__A304"])
    assert result["formal_status"] != "fail"


def test_a_required_pair_that_was_admitted_is_a_pass_that_really_exercised_a_rule():
    label = {**EMPTY_LABEL, "required_conflicts": ["A101__A304"]}
    entries = [_entry("A101", "A304", outcome="admitted", status="admitted", bull=2, bear=2)]
    result = _verdict(label, entries=entries, admitted=["A101__A304"])
    assert result["formal_status"] == "pass"
    assert result["coverage"]["declared_pairs_with_evidence"] == 1
    assert result["coverage"]["pass_is_vacuous"] is False
    assert result["coverage"]["reading"] is None


# ---------------------------------------------------------------------------------------------------------------------------------------
# One list of reasons feeds the status and every table: they cannot disagree
# ---------------------------------------------------------------------------------------------------------------------------------------


def test_review_reasons_explain_a_needs_review_and_name_their_family():
    label = {**EMPTY_LABEL, "conditional_conflicts": ["A101__A304"]}
    entries = [_entry("A101", "A304", outcome="suppressed", status="candidate", bull=2, bear=2)]
    result = _verdict(label, entries=entries, candidate=["A101__A304"])
    assert result["formal_status"] == "needs_review"
    assert result["failure_reasons"] == []
    assert [(r["family"], r["pair"]) for r in result["review_reasons"]] == [("should_detect_if_supported", "A101__A304")]


def test_an_undeclared_admitted_conflict_is_a_review_reason():
    entries = [_entry("A304", "A601", outcome="admitted", status="admitted", bull=2, bear=2)]
    result = _verdict(copy.deepcopy(EMPTY_LABEL), entries=entries, admitted=["A304__A601"])
    assert result["formal_status"] == "needs_review"
    assert result["undeclared_admitted_conflicts"] == ["A304__A601"]
    assert {"family": "undeclared_admitted_conflict", "pair": "A304__A601", "verdict": "review_required"} in result["review_reasons"]


def test_status_is_a_pure_function_of_the_two_reason_lists():
    cases = [
        (copy.deepcopy(EMPTY_LABEL), [], [], []),
        ({**EMPTY_LABEL, "required_conflicts": ["A101__A304"]}, [_entry("A101", "A304", outcome="suppressed", status="candidate", bull=3, bear=3)], [], ["A101__A304"]),
        (
            {**EMPTY_LABEL, "conditional_conflicts": ["A101__A304"]},
            [_entry("A101", "A304", outcome="suppressed", status="candidate", bull=2, bear=2)],
            [],
            ["A101__A304"],
        ),
    ]
    for label, entries, admitted, candidate in cases:
        result = _verdict(label, entries=entries, admitted=admitted, candidate=candidate)
        expected = "fail" if result["failure_reasons"] else "needs_review" if result["review_reasons"] else "pass"
        assert result["formal_status"] == expected


def test_the_resolved_ticker_rules_are_part_of_effective_rules():
    label = {**EMPTY_LABEL, "conditional_conflicts": ["A301__A304", "A101__A304"], "allowed_conflicts": ["A003__A501"]}
    result = _verdict(label, label_block_v1={"should_not_be_dominant_without_strong_evidence": {"A001": "rate evidence"}})
    ticker_rules = result["effective_rules"]["ticker_rules"]
    assert ticker_rules["conditional_only"]["pairs"] == ["A101__A304", "A301__A304"]
    assert ticker_rules["allowed_main_conflicts"]["pairs"] == ["A003__A501"]
    assert ticker_rules["forbidden_dominant_without_strong_evidence"]["guarded_alphas"] == {"A001": "rate evidence"}
    assert ticker_rules["must_detect_if_evidence_present"]["pairs"] == []


# ---------------------------------------------------------------------------------------------------------------------------------------
# E4: production wiring - a rule or execution problem is VISIBLE, never silent, and never breaks the run
# ---------------------------------------------------------------------------------------------------------------------------------------

HEALTHY_PAYLOADS = {
    "graph_payload": {"ticker": "AMD", "activation_versions": {"v2": {"alphas": []}}, "activation": {"alphas": []}, "dominant_alphas": []},
    "conflict_payload": {"conflicts": [], "arbitration": {"candidate_evaluations": []}, "main_conflict": None},
    "alpha_matches_payload": {"matches": [{"claim_id": "c1", "match_status": "matched", "matched_alpha": None}]},
}


def _write(tmp_path: Path, ticker: str = "AMD", run_id: str = "wiring-run"):
    artifact = wiring.write_formal_acceptance_artifact(
        run_id=run_id, ticker=ticker, output_root=tmp_path, artifact_completeness="pass", **HEALTHY_PAYLOADS
    )
    path = tmp_path / run_id / wiring.FORMAL_ACCEPTANCE_ARTIFACT_FILENAME
    return artifact, path


def test_an_unusable_rule_file_leaves_a_visible_config_error_artifact(tmp_path, monkeypatch):
    monkeypatch.setattr(engine, "DEFAULT_LABEL_V2_PATH", wiring._REPO_ROOT / "does_not_exist_labels_v0.2.yaml")
    artifact, path = _write(tmp_path)
    assert artifact is not None and path.exists()
    assert artifact["formal_status"] == FORMAL_STATUS_CONFIG_ERROR
    assert artifact["config_error_reason_code"] == "ACCEPTANCE_LABEL_V2_INVALID"
    assert json.loads(path.read_text(encoding="utf-8")) == artifact
    assert str(wiring._REPO_ROOT) not in artifact["config_error_detail"], "no absolute path of an engineer's machine"


def test_an_unexpected_failure_leaves_a_visible_execution_error_artifact(tmp_path, monkeypatch):
    def boom(**_kwargs):
        raise RuntimeError("boom")

    monkeypatch.setattr(wiring, "run_formal_acceptance", boom)
    artifact, path = _write(tmp_path)
    assert artifact["formal_status"] == FORMAL_STATUS_EXECUTION_ERROR
    assert artifact["execution_error_reason_code"] == wiring.REASON_EXECUTION_ERROR
    assert "RuntimeError: boom" in artifact["execution_error_detail"]
    assert path.exists()


def test_failing_to_write_the_artifact_is_logged_and_returns_none_without_raising(tmp_path, monkeypatch):
    def cannot_write(*_args, **_kwargs):
        raise OSError("disk full")

    monkeypatch.setattr(wiring, "save_json_record", cannot_write)
    artifact, path = _write(tmp_path)
    assert artifact is None
    assert not path.exists()


def test_a_ticker_with_no_declared_rules_gets_a_visible_config_error_artifact_in_production(tmp_path):
    artifact, path = _write(tmp_path, ticker="ZZZZ_NO_RULES")
    assert artifact["formal_status"] == FORMAL_STATUS_CONFIG_ERROR
    assert artifact["config_error_reason_code"] == engine.REASON_TICKER_RULES_NOT_DECLARED
    assert path.exists()


def test_a_healthy_labeled_ticker_still_gets_a_normal_verdict_with_the_new_fields(tmp_path):
    artifact, _path = _write(tmp_path, ticker="AMD")
    assert artifact["formal_status"] in ("pass", "needs_review")
    assert artifact["schema_version"] == wiring.FORMAL_ACCEPTANCE_SCHEMA_VERSION
    assert artifact["effective_rules"]["ticker_rules"]["ticker"] == "AMD"
    assert {"declared_conflict_pairs", "pass_is_vacuous"} <= set(artifact["coverage"])


def test_a_pair_that_reached_arbitration_without_supporting_evidence_does_not_make_a_pass_non_vacuous():
    """Appearing in the arbitration list is not evidence: with no supporting fact on either side the evidence-conditional rules are not applicable, so
    the PASS exercised nothing and must say so."""
    label = {**EMPTY_LABEL, "conditional_conflicts": ["A101__A304"], "allowed_conflicts": ["A301__A304"]}
    entries = [
        _entry("A101", "A304", outcome="suppressed", status="candidate", bull=0, bear=0),
        _entry("A301", "A304", outcome="suppressed", status="candidate", bull=1, bear=0),
    ]
    result = _verdict(label, entries=entries, candidate=["A101__A304", "A301__A304"])
    assert result["formal_status"] == "pass"
    assert result["coverage"]["declared_conflict_pairs"] == 2
    assert result["coverage"]["declared_pairs_with_evidence"] == 0
    assert result["coverage"]["pass_is_vacuous"] is True
