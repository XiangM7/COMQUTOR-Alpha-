"""MVP Audit, Evaluation, Golden Fixtures, and Delivery Readiness Sprint,
Track B/C: Cross-run Evaluation Harness and Golden Case format tests.

Uses the same approved, deterministic, offline NVDA fixture the W5 demo
uses (``scripts.w5_demo_fixtures.approved_demo_outputs``) to produce one
real run directory via the already-tested ``run_research_request`` offline
path, then wraps that run as both a ``historical_replay_case`` and a
``frozen_golden_case`` bundle -- no network, no Provider, no LLM call
anywhere in this file.
"""

from __future__ import annotations

import json
import shutil
from pathlib import Path

import pytest
import yaml

from comqutor_alpha.api.routes_research import run_research_request
from comqutor_alpha.evaluation.cross_run import main as cross_run_main
from comqutor_alpha.evaluation.expectations import evaluate_expected, evaluate_leaf
from comqutor_alpha.evaluation.golden_case import (
    GoldenCaseError,
    load_golden_case,
    verify_artifact_hashes,
)
from comqutor_alpha.evaluation.runner import (
    STATUS_COMPLETED,
    STATUS_PENDING_FIXTURE,
    run_case,
)
from scripts.w5_demo_fixtures import (
    DEMO_ANALYSIS_DATE,
    DEMO_SELECTED_ANALYSTS,
    approved_demo_outputs,
)

# ---------------------------------------------------------------------------
# Shared real-run fixture
# ---------------------------------------------------------------------------


def _make_real_run(tmp_path: Path) -> tuple[str, Path]:
    payload = {
        "ticker": "NVDA",
        "analysis_date": DEMO_ANALYSIS_DATE,
        "selected_analysts": list(DEMO_SELECTED_ANALYSTS),
        "offline_raw_agent_outputs": approved_demo_outputs("NVDA"),
    }
    response = run_research_request(payload, output_root=tmp_path)
    assert response["status"] == "completed"
    run_id = response["run_id"]
    return run_id, tmp_path / run_id


def _write_case_bundle(case_dir: Path, *, case_yaml: dict, expected_yaml: dict) -> None:
    case_dir.mkdir(parents=True, exist_ok=True)
    (case_dir / "case.yaml").write_text(yaml.safe_dump(case_yaml), encoding="utf-8")
    (case_dir / "expected.yaml").write_text(yaml.safe_dump(expected_yaml), encoding="utf-8")


# ---------------------------------------------------------------------------
# 1. Expectation types
# ---------------------------------------------------------------------------


def test_exact_expectation():
    assert evaluate_leaf("x", {"exact": 5}, 5).passed
    assert not evaluate_leaf("x", {"exact": 5}, 6).passed


def test_range_expectation():
    assert evaluate_leaf("x", {"range": [1, 10]}, 5).passed
    assert not evaluate_leaf("x", {"range": [1, 10]}, 11).passed


def test_minimum_maximum_expectation():
    assert evaluate_leaf("x", {"minimum": 5}, 5).passed
    assert not evaluate_leaf("x", {"minimum": 5}, 4).passed
    assert evaluate_leaf("x", {"maximum": 5}, 5).passed
    assert not evaluate_leaf("x", {"maximum": 5}, 6).passed


def test_set_equals_and_set_contains_expectation():
    assert evaluate_leaf("x", {"set_equals": ["A", "B"]}, ["B", "A"]).passed
    assert not evaluate_leaf("x", {"set_equals": ["A", "B"]}, ["A"]).passed
    assert evaluate_leaf("x", {"set_contains": ["A"]}, ["A", "B"]).passed
    assert not evaluate_leaf("x", {"set_contains": ["A", "C"]}, ["A", "B"]).passed


def test_one_of_expectation():
    assert evaluate_leaf("x", {"one_of": ["A101__A304", "A301__A304"]}, "A301__A304").passed
    assert not evaluate_leaf("x", {"one_of": ["A101__A304"]}, "A301__A304").passed


def test_must_exist_and_must_not_exist_expectation():
    assert evaluate_leaf("x", {"must_exist": True}, "value").passed
    assert not evaluate_leaf("x", {"must_exist": True}, None).passed
    assert evaluate_leaf("x", {"must_not_exist": True}, None).passed
    assert not evaluate_leaf("x", {"must_not_exist": True}, "value").passed


def test_manual_review_expectation_is_never_auto_verified():
    result = evaluate_leaf("x", {"manual_review": True}, "anything")
    assert result.manual is True
    assert result.passed is True  # never blocks the run, always surfaced


def test_path_exists_via_required_paths():
    expected = {
        "graph": {
            "required_paths": [{"source": "a", "target": "c", "max_hops": 3}],
        }
    }
    actual_ok = {"graph": {"edges": [{"source": "a", "target": "b"}, {"source": "b", "target": "c"}]}}
    results = evaluate_expected(expected, actual_ok)
    assert results[0].passed

    actual_missing = {"graph": {"edges": [{"source": "a", "target": "b"}]}}
    results = evaluate_expected(expected, actual_missing)
    assert not results[0].passed


def test_forbidden_pattern_expectation():
    expected = {"claims": {"forbidden_patterns": ["let me synthesize"]}}
    actual_clean = {"claims": {"texts": ["Revenue grew 20% year over year."]}}
    results = evaluate_expected(expected, actual_clean)
    assert all(r.passed for r in results)

    actual_dirty = {"claims": {"texts": ["Let me synthesize the findings now."]}}
    results = evaluate_expected(expected, actual_dirty)
    assert any(not r.passed for r in results)


def test_zero_edges_allowed_case_does_not_fail():
    expected = {"graph": {"edge_count": {"minimum": 0}, "zero_edges_allowed": True}}
    actual = {"graph": {"node_count": 5, "edge_count": 0, "edges": []}}
    results = evaluate_expected(expected, actual)
    assert all(r.passed for r in results)


def test_per_case_minimum_edge_expectation_can_fail():
    expected = {"graph": {"edge_count": {"minimum": 3}}}
    actual = {"graph": {"node_count": 5, "edge_count": 0, "edges": []}}
    results = evaluate_expected(expected, actual)
    assert any(not r.passed for r in results)


def test_optional_entity_exposure_expectations_are_evaluated_only_when_declared():
    results = evaluate_expected(
        {"entity_exposure": {"A101": {"range": [0.8, 1.0]}, "A102": {"maximum": 0.3}}},
        {"entity_exposure": {"by_alpha": {"A101": 0.9, "A102": 0.25}}},
    )
    assert [result.name for result in results] == [
        "entity_exposure.A101",
        "entity_exposure.A102",
    ]
    assert all(result.passed for result in results)


# ---------------------------------------------------------------------------
# 2. Golden Case bundle loading
# ---------------------------------------------------------------------------


def test_valid_case_bundle_loads(tmp_path):
    case_dir = tmp_path / "example_case"
    _write_case_bundle(
        case_dir,
        case_yaml={
            "case_id": "example_case",
            "ticker": "NVDA",
            "case_type": "historical_replay_case",
            "approval_status": "draft",
            "source_run_id": "somerun",
        },
        expected_yaml={"graph": {"node_count": {"minimum": 0}}},
    )
    case = load_golden_case(case_dir)
    assert case.case_id == "example_case"
    assert case.case_type == "historical_replay_case"
    assert case.approval_status == "draft"


def test_missing_required_artifact_fails_clearly(tmp_path):
    case_dir = tmp_path / "broken_case"
    case_dir.mkdir()
    (case_dir / "case.yaml").write_text(
        yaml.safe_dump({"case_id": "broken_case", "ticker": "NVDA", "case_type": "historical_replay_case", "approval_status": "draft"}),
        encoding="utf-8",
    )
    # expected.yaml deliberately absent.
    with pytest.raises(GoldenCaseError, match="MISSING_REQUIRED_ARTIFACT"):
        load_golden_case(case_dir)


def test_missing_required_fields_in_case_yaml_fails_clearly(tmp_path):
    case_dir = tmp_path / "incomplete_case"
    _write_case_bundle(
        case_dir,
        case_yaml={"case_id": "incomplete_case"},  # missing ticker/case_type/approval_status
        expected_yaml={},
    )
    with pytest.raises(GoldenCaseError, match="MISSING_FIELDS"):
        load_golden_case(case_dir)


def test_invalid_approval_status_and_case_type_are_rejected(tmp_path):
    case_dir = tmp_path / "invalid_status_case"
    _write_case_bundle(
        case_dir,
        case_yaml={"case_id": "x", "ticker": "NVDA", "case_type": "historical_replay_case", "approval_status": "definitely_approved_trust_me"},
        expected_yaml={},
    )
    with pytest.raises(GoldenCaseError, match="INVALID_APPROVAL_STATUS"):
        load_golden_case(case_dir)

    case_dir2 = tmp_path / "invalid_type_case"
    _write_case_bundle(
        case_dir2,
        case_yaml={"case_id": "x", "ticker": "NVDA", "case_type": "fully_verified_case", "approval_status": "draft"},
        expected_yaml={},
    )
    with pytest.raises(GoldenCaseError, match="INVALID_CASE_TYPE"):
        load_golden_case(case_dir2)


def test_hash_mismatch_is_detected(tmp_path):
    case_dir = tmp_path / "hash_case"
    _write_case_bundle(
        case_dir,
        case_yaml={
            "case_id": "hash_case",
            "ticker": "NVDA",
            "case_type": "frozen_golden_case",
            "approval_status": "draft",
            "artifact_hashes": {"raw_agent_outputs.json": "0" * 64},
        },
        expected_yaml={},
    )
    (case_dir / "raw_agent_outputs.json").write_text(json.dumps({"agent_outputs": []}), encoding="utf-8")
    case = load_golden_case(case_dir)
    mismatches = verify_artifact_hashes(case)
    assert mismatches
    assert "hash mismatch" in mismatches[0]


def test_manual_claim_labels_template_loads():
    from comqutor_alpha.evaluation.golden_case import load_manual_claim_labels

    template_path = Path("evaluation/golden_cases/_template/manual_claim_labels.csv")
    rows = load_manual_claim_labels(template_path)
    # The template's example row is illustrative, never treated as real data
    # by any harness logic -- this test only verifies the CSV parses.
    assert isinstance(rows, list)


# ---------------------------------------------------------------------------
# 3. Runner: frozen_golden_case / historical_replay_case / pending_fixture /
#    live_smoke_result -- real pipeline, 0 Provider calls.
# ---------------------------------------------------------------------------


def test_historical_replay_case_runs_with_zero_provider_calls(tmp_path):
    run_id, run_dir = _make_real_run(tmp_path)
    case_dir = tmp_path / "golden_cases" / "nvda_case"
    _write_case_bundle(
        case_dir,
        case_yaml={
            "case_id": "nvda_case",
            "ticker": "NVDA",
            "case_type": "historical_replay_case",
            "approval_status": "draft",
            "source_run_id": run_id,
            "source_output_root": str(tmp_path),
        },
        expected_yaml={"graph": {"node_count": {"minimum": 0}}, "claims": {"forbidden_patterns": ["let me synthesize"]}},
    )
    case = load_golden_case(case_dir)
    result = run_case(case, evaluation_output_root=str(tmp_path / "eval_out"))

    assert result.status == STATUS_COMPLETED
    assert result.provider_calls == 0
    assert result.actual["graph"]["node_count"] >= 0
    assert result.required_expectations_passed


def test_frozen_golden_case_runs_from_a_self_contained_bundle(tmp_path):
    run_id, run_dir = _make_real_run(tmp_path)
    case_dir = tmp_path / "golden_cases" / "nvda_frozen_case"
    case_dir.mkdir(parents=True)
    shutil.copy(run_dir / "raw_agent_outputs.json", case_dir / "raw_agent_outputs.json")
    shutil.copy(run_dir / "metadata.json", case_dir / "metadata.json")
    _write_case_bundle(
        case_dir,
        case_yaml={
            "case_id": "nvda_frozen_case",
            "ticker": "NVDA",
            "case_type": "frozen_golden_case",
            "approval_status": "draft",
            "input_artifacts": ["raw_agent_outputs.json"],
        },
        expected_yaml={"graph": {"node_count": {"minimum": 0}}},
    )
    case = load_golden_case(case_dir)
    result = run_case(case, evaluation_output_root=str(tmp_path / "eval_out2"))

    assert result.status == STATUS_COMPLETED
    assert result.provider_calls == 0


def test_pending_fixture_is_honestly_reported_never_a_fabricated_pass(tmp_path):
    case_dir = tmp_path / "golden_cases" / "missing_case"
    _write_case_bundle(
        case_dir,
        case_yaml={
            "case_id": "missing_case",
            "ticker": "TSM",
            "case_type": "historical_replay_case",
            "approval_status": "draft",
            "source_run_id": "does_not_exist_anywhere",
            "source_output_root": str(tmp_path / "no_such_root"),
        },
        expected_yaml={"graph": {"node_count": {"minimum": 5}}},
    )
    case = load_golden_case(case_dir)
    result = run_case(case, evaluation_output_root=str(tmp_path / "eval_out3"))

    assert result.status == STATUS_PENDING_FIXTURE
    assert result.expectation_results == []
    # Never silently counted as passing.
    assert result.required_expectations_passed is True  # vacuously true (no checks ran)
    assert result.skipped_reason is not None


def test_live_smoke_result_never_uses_exact_stochastic_text_as_oracle(tmp_path):
    run_id, run_dir = _make_real_run(tmp_path)
    case_dir = tmp_path / "golden_cases" / "nvda_smoke_case"
    _write_case_bundle(
        case_dir,
        case_yaml={
            "case_id": "nvda_smoke_case",
            "ticker": "NVDA",
            "case_type": "live_smoke_result",
            "approval_status": "draft",
            "source_run_id": run_id,
            "source_output_root": str(tmp_path),
        },
        # Even if an author mistakenly declares assertions here, a
        # live_smoke_result case must never auto-verify them as an exact
        # text oracle.
        expected_yaml={"claims": {"forbidden_patterns": ["this text will never appear verbatim in any real report"]}},
    )
    case = load_golden_case(case_dir)
    result = run_case(case, evaluation_output_root=str(tmp_path / "eval_out4"))

    assert result.status == STATUS_COMPLETED
    assert result.expectation_results == []  # never evaluated for this case type


# ---------------------------------------------------------------------------
# 4. cross_run.py: report generation and exit codes
# ---------------------------------------------------------------------------


def _write_manifest(manifest_path: Path, entries: list[dict]) -> None:
    manifest_path.parent.mkdir(parents=True, exist_ok=True)
    manifest_path.write_text(yaml.safe_dump({"cases": entries}), encoding="utf-8")


def test_report_files_are_generated_and_source_artifacts_are_untouched(tmp_path):
    run_id, run_dir = _make_real_run(tmp_path)
    raw_before = (run_dir / "raw_agent_outputs.json").read_bytes()

    case_dir = tmp_path / "golden_cases" / "nvda_case"
    _write_case_bundle(
        case_dir,
        case_yaml={
            "case_id": "nvda_case",
            "ticker": "NVDA",
            "case_type": "historical_replay_case",
            "approval_status": "draft",
            "source_run_id": run_id,
            "source_output_root": str(tmp_path),
        },
        expected_yaml={"graph": {"node_count": {"minimum": 0}}},
    )
    manifest_path = tmp_path / "manifests" / "cases.yaml"
    _write_manifest(manifest_path, [{"case_id": "nvda_case", "ticker": "NVDA", "case_dir": str(case_dir)}])

    output_dir = tmp_path / "eval_output"
    exit_code = cross_run_main(["--manifest", str(manifest_path), "--output-dir", str(output_dir)])

    assert exit_code == 0
    for filename in ("evaluation_summary.json", "case_results.json", "case_results.csv", "evaluation_report.md", "failures.json"):
        assert (output_dir / filename).exists(), filename

    summary = json.loads((output_dir / "evaluation_summary.json").read_text(encoding="utf-8"))
    assert summary["provider_calls"] == 0
    assert summary["source_artifacts_changed"] is False
    assert (run_dir / "raw_agent_outputs.json").read_bytes() == raw_before


def test_nonzero_exit_code_on_failed_required_expectation(tmp_path):
    run_id, run_dir = _make_real_run(tmp_path)
    case_dir = tmp_path / "golden_cases" / "impossible_case"
    _write_case_bundle(
        case_dir,
        case_yaml={
            "case_id": "impossible_case",
            "ticker": "NVDA",
            "case_type": "historical_replay_case",
            "approval_status": "draft",
            "source_run_id": run_id,
            "source_output_root": str(tmp_path),
        },
        # An impossible minimum -- guaranteed to fail structurally.
        expected_yaml={"graph": {"node_count": {"minimum": 999999}}},
    )
    manifest_path = tmp_path / "manifests" / "cases.yaml"
    _write_manifest(manifest_path, [{"case_id": "impossible_case", "ticker": "NVDA", "case_dir": str(case_dir)}])

    output_dir = tmp_path / "eval_output_fail"
    exit_code = cross_run_main(["--manifest", str(manifest_path), "--output-dir", str(output_dir)])

    assert exit_code == 1
    failures = json.loads((output_dir / "failures.json").read_text(encoding="utf-8"))
    assert failures
    assert failures[0]["case_id"] == "impossible_case"


def test_pending_fixture_case_is_skipped_honestly_in_full_run(tmp_path):
    manifest_path = tmp_path / "manifests" / "cases.yaml"
    _write_manifest(
        manifest_path,
        [{"case_id": "nonexistent_case", "ticker": "AVGO", "case_dir": str(tmp_path / "golden_cases" / "does_not_exist")}],
    )
    output_dir = tmp_path / "eval_output_pending"
    exit_code = cross_run_main(["--manifest", str(manifest_path), "--output-dir", str(output_dir)])

    # A purely-pending manifest (no bundle present) must never be reported
    # as a failure -- it is exit code 0 with an honest pending_fixture count.
    assert exit_code == 0
    summary = json.loads((output_dir / "evaluation_summary.json").read_text(encoding="utf-8"))
    assert summary["cases_pending_fixture"] == 1
    assert summary["cases_completed"] == 0
