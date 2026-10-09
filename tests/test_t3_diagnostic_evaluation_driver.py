"""Tests for the T3 diagnostic-evaluation driver
(docs/audit_artifacts/round_source_linking_t0_t2/t3_diagnostic_evaluation_driver.py).

Loaded via importlib since the driver lives under docs/audit_artifacts/, a
non-package directory, matching the rest of that directory's convention of
standalone scripts rather than an importable module.

Fixed Provider responses only -- zero network, zero paid calls. Every
human-label fixture here is local to this test file (`_FAKE_REVIEW_ITEMS`)
and is never written into the real t3_human_review_form_2026-09-30.json.
"""

from __future__ import annotations

import csv
import importlib.util
import json
import sys
from pathlib import Path

import pytest

_DRIVER_PATH = (
    Path(__file__).resolve().parents[1]
    / "docs/audit_artifacts/round_source_linking_t0_t2/t3_diagnostic_evaluation_driver.py"
)
_spec = importlib.util.spec_from_file_location("t3_diagnostic_evaluation_driver", _DRIVER_PATH)
driver = importlib.util.module_from_spec(_spec)
sys.modules[_spec.name] = driver
_spec.loader.exec_module(driver)


# ---------------------------------------------------------------------------
# classify_outcome: pure mapping function
# ---------------------------------------------------------------------------


@pytest.mark.parametrize(
    ("classifier_status", "match_status", "expected"),
    [
        ("disabled", "unavailable", "UNAVAILABLE"),
        ("unavailable", "unavailable", "UNAVAILABLE"),
        ("provider_timeout", "unavailable", "CALL_FAILED"),
        ("provider_error", "unavailable", "CALL_FAILED"),
        ("call_budget_exhausted", "unavailable", "CALL_FAILED"),
        ("provider_rate_limited", "unavailable", "CALL_FAILED"),
        ("invalid_output", "unavailable", "PARSE_FAILED"),
        ("invalid_alpha_id", "unavailable", "PARSE_FAILED"),
        ("input_too_large", "unavailable", "PARSE_FAILED"),
        ("llm_none", "no_match", "NONE"),
        ("llm_selected", "matched", "MATCHED"),
        ("llm_selected", "ambiguous", "ABSTAINED_AMBIGUOUS"),
        # 2026-10-01 (AI-review comparison round) bug fix: the classifier
        # validly selected an in-taxonomy Alpha ID, but alpha_mapper.py's own
        # post-hoc veto/positive-requirement gate overrode the match back to
        # no_match. Previously silently fell through to "MATCHED" despite no
        # usable predicted_alpha -- confirmed against 5 real records in
        # execution t3live_20261001T014648Z_1fb9c9d5. Must be its own status,
        # never folded into MATCHED or NONE.
        ("llm_selected", "no_match", "SELECTED_BUT_NOT_MATCHED"),
    ],
)
def test_classify_outcome_covers_every_real_classifier_status(classifier_status, match_status, expected):
    assert driver.classify_outcome(classifier_status, match_status) == expected


def test_classify_outcome_flags_unexpected_status_rather_than_silently_defaulting():
    result = driver.classify_outcome("some_new_status_nobody_registered", "matched")
    assert result.startswith("UNEXPECTED_CLASSIFIER_STATUS:")


def test_classify_outcome_flags_unexpected_match_status_for_llm_selected():
    """A future, not-yet-registered match_status value under llm_selected
    must fail loudly, not silently collapse into MATCHED (the exact failure
    mode this round's bug fix corrects for the known "no_match" value)."""
    result = driver.classify_outcome("llm_selected", "some_new_match_status")
    assert result.startswith("UNEXPECTED_CLASSIFIER_STATUS:llm_selected+match_status=")


# ---------------------------------------------------------------------------
# Fixtures: a tiny, real-shaped sample set + review form
# ---------------------------------------------------------------------------


def _make_samples_doc(n=3):
    samples = []
    for i in range(n):
        samples.append(
            {
                "sample_id": f"test-{i}",
                "claim_id": f"run{i}:agent:report:claim:{i}",
                "claim_text": f"claim text {i}",
                "evidence_text": f"evidence text {i}",
                "ticker": "NVDA",
                "run_id": f"run{i}",
                "quota_category": "A001",
            }
        )
    return {"status": "COMPLETE", "samples": samples}


class _FixedResponse:
    def __init__(self, content):
        self.content = content


class _FixedSequenceModel:
    def __init__(self, responses):
        self.responses = list(responses)
        self.calls = 0

    def invoke(self, _prompt):
        item = self.responses[self.calls]
        self.calls += 1
        if isinstance(item, Exception):
            raise item
        return _FixedResponse(item)


def _fake_gateway_factory(responses):
    """Builds a real Week2LLMGateway + real SemanticRuntimeSession, wired to
    a fixed-response fake model -- the real call wrapper, fake Provider."""

    def factory(execution_id, output_root):
        from comqutor_alpha.llm_runtime.session import SemanticRuntimeSession
        from comqutor_alpha.structure_engine.week2_llm import Week2LLMGateway

        run_dir = Path(output_root) / execution_id
        run_dir.mkdir(parents=True, exist_ok=True)
        session = SemanticRuntimeSession(
            run_id=execution_id,
            output_directory=run_dir,
            execution_mode="test",
            provider="fake-provider",
            model="fake-model",
        )
        gateway = Week2LLMGateway(
            _FixedSequenceModel(responses),
            run_id=execution_id,
            output_root=output_root,
            timeout_seconds=0.2,
            max_retries=1,
            max_calls=50,
            provider="fake-provider",
            model_name="fake-model",
            semantic_runtime=session,
        )
        return gateway, session

    return factory


# ---------------------------------------------------------------------------
# run_live_evaluation: real driver path, fixed responses
# ---------------------------------------------------------------------------


def test_live_evaluation_classifies_matched_none_and_call_failed(tmp_path):
    samples = _make_samples_doc(3)["samples"]
    responses = [
        json.dumps({"decision": "select", "selected_alpha_id": "A501"}),  # sample 0: MATCHED
        json.dumps({"decision": "none", "selected_alpha_id": None}),  # sample 1: NONE
        RuntimeError("provider unreachable"),  # sample 2: CALL_FAILED (after retries)
    ]
    result = driver.run_live_evaluation(
        samples,
        execution_id="test-exec-1",
        output_dir=tmp_path,
        max_actual_requests=60,
        max_retries_per_call=0,
        gateway_factory=_fake_gateway_factory(responses),
    )

    by_id = {r["sample_id"]: r for r in result.records}
    assert by_id["test-0"]["outcome_code"] == "MATCHED"
    assert by_id["test-0"]["predicted_alpha"] == "A501"
    assert by_id["test-1"]["outcome_code"] == "NONE"
    assert by_id["test-2"]["outcome_code"] == "CALL_FAILED"
    assert not result.stopped_early

    # Real artifacts were actually written to disk.
    run_root = tmp_path / "test-exec-1"
    assert (run_root / "t3_eval_records.jsonl").exists()
    assert (run_root / "t3_eval_semantic_call_records.jsonl").exists()
    call_records = [
        json.loads(line)
        for line in (run_root / "t3_eval_semantic_call_records.jsonl").read_text().splitlines()
        if line
    ]
    assert len(call_records) == 3  # one real SemanticCallRecord per sample


def test_live_evaluation_records_selected_but_not_matched_when_negative_veto_fires(tmp_path):
    """End-to-end regression (2026-10-01, AI-review comparison round) for the
    confirmed bug: the real classifier selects a valid, in-taxonomy Alpha ID
    (A001), but alpha_mapper.py's own Step 7A alpha-specific-invalidation
    veto (a pre-existing, deliberate product check -- not touched by this
    fix) overrides it back to no_match because the claim text explicitly
    asserts A001's own thesis is false. This is the exact real claim text
    from execution t3live_20261001T014648Z_1fb9c9d5's prod-run-010 sample,
    which hit this case for real. Before this round's fix, this recorded
    outcome_code="MATCHED" with predicted_alpha=None -- an internally
    inconsistent record. It must now record SELECTED_BUT_NOT_MATCHED and
    preserve the classifier's own original selection."""
    samples = _make_samples_doc(1)["samples"]
    samples[0]["claim_text"] = (
        "Prediction markets price a 93% probability of NO Fed rate cuts in 2026 (up +4.8pp on the week)."
    )
    samples[0]["evidence_text"] = samples[0]["claim_text"]
    responses = [json.dumps({"decision": "select", "selected_alpha_id": "A001"})]
    result = driver.run_live_evaluation(
        samples,
        execution_id="test-exec-veto",
        output_dir=tmp_path,
        max_actual_requests=60,
        max_retries_per_call=0,
        gateway_factory=_fake_gateway_factory(responses),
    )
    record = result.records[0]
    assert record["outcome_code"] == "SELECTED_BUT_NOT_MATCHED"
    assert record["predicted_alpha"] is None
    assert record["classifier_status_raw"] == "llm_selected"
    assert record["match_status_raw"] == "no_match"
    assert record["llm_selected_alpha_id"] == "A001"
    assert record["alpha_specific_invalidation_override"] is True


def test_live_evaluation_records_selected_but_not_matched_when_positive_requirement_gate_fails(tmp_path):
    """Sibling regression for the OTHER post-hoc gate (Step 7A.2): the claim
    is generic rate/duration context that never affirmatively asserts A001's
    easing thesis, so the positive-requirement gate (not the negative veto)
    is what overrides the selection back to no_match. Real claim text from
    execution t3live_20261001T014648Z_1fb9c9d5's gold-final-030 sample."""
    samples = _make_samples_doc(1)["samples"]
    samples[0]["claim_text"] = (
        "QQQ, as the highest-duration large-cap growth vehicle in the market, "
        "is the most exposed index product to this repricing."
    )
    samples[0]["evidence_text"] = samples[0]["claim_text"]
    responses = [json.dumps({"decision": "select", "selected_alpha_id": "A001"})]
    result = driver.run_live_evaluation(
        samples,
        execution_id="test-exec-positive-gate",
        output_dir=tmp_path,
        max_actual_requests=60,
        max_retries_per_call=0,
        gateway_factory=_fake_gateway_factory(responses),
    )
    record = result.records[0]
    assert record["outcome_code"] == "SELECTED_BUT_NOT_MATCHED"
    assert record["predicted_alpha"] is None
    assert record["llm_selected_alpha_id"] == "A001"
    assert record["alpha_specific_invalidation_override"] is False
    assert record["alpha_positive_requirement_override"] is True


def test_live_evaluation_parse_failed_on_invalid_json(tmp_path):
    samples = _make_samples_doc(1)["samples"]
    result = driver.run_live_evaluation(
        samples,
        execution_id="test-exec-parse",
        output_dir=tmp_path,
        max_actual_requests=60,
        max_retries_per_call=0,
        gateway_factory=_fake_gateway_factory(["not valid json at all"]),
    )
    assert result.records[0]["outcome_code"] == "PARSE_FAILED"


def test_live_evaluation_stops_at_budget_and_records_skipped_samples(tmp_path):
    samples = _make_samples_doc(3)["samples"]
    responses = [json.dumps({"decision": "select", "selected_alpha_id": "A501"}) for _ in range(3)]
    result = driver.run_live_evaluation(
        samples,
        execution_id="test-exec-budget",
        output_dir=tmp_path,
        max_actual_requests=1,  # only the first sample's single call is allowed
        max_retries_per_call=0,
        gateway_factory=_fake_gateway_factory(responses),
    )
    by_id = {r["sample_id"]: r for r in result.records}
    assert result.stopped_early is True
    assert by_id["test-0"]["outcome_code"] == "MATCHED"
    assert by_id["test-1"]["outcome_code"] == "SKIPPED_BUDGET_STOP"
    assert by_id["test-2"]["outcome_code"] == "SKIPPED_BUDGET_STOP"
    # every sample still appears exactly once -- never silently dropped.
    assert len(result.records) == 3


def test_max_retries_per_call_is_actually_applied_to_the_gateway(tmp_path):
    samples = _make_samples_doc(1)["samples"]
    captured = {}

    def factory(execution_id, output_root):
        gateway, session = _fake_gateway_factory([json.dumps({"decision": "none", "selected_alpha_id": None})])(
            execution_id, output_root
        )
        captured["gateway"] = gateway
        return gateway, session

    driver.run_live_evaluation(
        samples,
        execution_id="test-exec-retries",
        output_dir=tmp_path,
        max_actual_requests=60,
        max_retries_per_call=3,
        gateway_factory=factory,
    )
    assert captured["gateway"].max_retries == 3


# ---------------------------------------------------------------------------
# score_against_human_labels
# ---------------------------------------------------------------------------

_FAKE_REVIEW_ITEMS = [
    {"sample_id": "test-0", "your_judgment": "A001"},
    {"sample_id": "test-1", "your_judgment": "NONE"},
    {"sample_id": "test-2", "your_judgment": "A003"},
]


def test_scoring_is_blocked_with_no_human_labels():
    records = [{"sample_id": "test-0", "outcome_code": "MATCHED", "predicted_alpha": "A001", "quota_category": "A001"}]
    review_items = [{"sample_id": "test-0", "your_judgment": None}]
    result = driver.score_against_human_labels(records, review_items)
    assert result["scoring_status"] == "BLOCKED_NO_HUMAN_LABELS"
    assert "overall_accuracy" not in result


def test_scoring_computes_accuracy_precision_recall_and_never_drops_failures():
    records = [
        {"sample_id": "test-0", "outcome_code": "MATCHED", "predicted_alpha": "A001", "quota_category": "A001"},
        {"sample_id": "test-1", "outcome_code": "NONE", "predicted_alpha": None, "quota_category": "A001"},
        {"sample_id": "test-2", "outcome_code": "CALL_FAILED", "predicted_alpha": None, "quota_category": "A001"},
    ]
    result = driver.score_against_human_labels(records, _FAKE_REVIEW_ITEMS)
    assert result["scoring_status"] == "SCORED"
    # scored_sample_count must include the CALL_FAILED sample -- never dropped.
    assert result["scored_sample_count"] == 3
    assert result["outcome_code_counts"]["CALL_FAILED"] == 1
    # test-0: correct (A001==A001). test-1: correct (NONE==NONE, both non-matches).
    # test-2: human said A003, system reported CALL_FAILED -> wrong.
    assert result["overall_accuracy"] == pytest.approx(2 / 3)
    assert "A003" in result["confusion_matrix"]
    assert result["confusion_matrix"]["A003"]["CALL_FAILED"] == 1
    assert result["steps_covered"]["source_support_verification"].startswith("NOT_IMPLEMENTED")


def test_scoring_excludes_unable_to_judge_from_accuracy_but_still_counts_it():
    records = [
        {"sample_id": "test-0", "outcome_code": "MATCHED", "predicted_alpha": "A001", "quota_category": "A001"},
        {"sample_id": "test-3", "outcome_code": "MATCHED", "predicted_alpha": "A501", "quota_category": "A501"},
    ]
    review_items = [
        {"sample_id": "test-0", "your_judgment": "A001"},  # a real, correct judgment
        {"sample_id": "test-3", "your_judgment": driver.UNABLE_TO_JUDGE},  # explicit refusal to guess
    ]
    result = driver.score_against_human_labels(records, review_items)
    assert result["scoring_status"] == "SCORED"
    # never silently dropped: both counted somewhere.
    assert result["total_judged_count"] == 2
    assert result["unable_to_judge_count"] == 1
    # but excluded from the actual accuracy computation -- never coerced
    # into a right/wrong comparison.
    assert result["scored_sample_count"] == 1
    assert result["overall_accuracy"] == 1.0
    assert "A501" not in result["confusion_matrix"]


# ---------------------------------------------------------------------------
# run_preflight: zero external requests, correct blocking reasons
# ---------------------------------------------------------------------------


def test_preflight_blocks_when_week2_llm_disabled(tmp_path, monkeypatch):
    monkeypatch.delenv("COMQUTOR_WEEK2_LLM_ENABLED", raising=False)
    samples_path = tmp_path / "samples.json"
    samples_path.write_text(json.dumps(_make_samples_doc(1)))
    review_path = tmp_path / "review.json"
    review_path.write_text(json.dumps({"review_items": [{"sample_id": "test-0", "your_judgment": None}]}))

    report = driver.run_preflight(samples_path, review_path, tmp_path / "out", 60, 1)
    assert "WEEK2_LLM_CONFIG_INCOMPLETE_OR_DISABLED" in report.blocking_reasons
    assert report.ready_for_live is False


def test_preflight_reports_incomplete_sample_count_without_failing_the_process(tmp_path, monkeypatch):
    monkeypatch.setenv("COMQUTOR_WEEK2_LLM_ENABLED", "1")
    monkeypatch.setenv("COMQUTOR_WEEK2_LLM_PROVIDER", "deepseek")
    monkeypatch.setenv("COMQUTOR_WEEK2_LLM_MODEL", "deepseek-v4-flash")
    samples_path = tmp_path / "samples.json"
    samples_path.write_text(json.dumps({"status": "INCOMPLETE", "samples": []}))
    review_path = tmp_path / "review.json"
    review_path.write_text(json.dumps({"review_items": []}))

    report = driver.run_preflight(samples_path, review_path, tmp_path / "out", 60, 1)
    assert "SAMPLES_NOT_COMPLETE" in report.blocking_reasons
    assert report.ready_for_live is False


def test_preflight_never_imports_a_network_or_provider_library():
    import ast

    tree = ast.parse(_DRIVER_PATH.read_text())
    imported = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            imported.update(alias.name for alias in node.names)
        elif isinstance(node, ast.ImportFrom) and node.module:
            imported.add(node.module)
    forbidden = {"anthropic", "openai", "httpx", "requests", "socket", "boto3"}
    assert not (imported & forbidden)


# ---------------------------------------------------------------------------
# build_freeze_identity: real, local, no network
# ---------------------------------------------------------------------------


def test_freeze_identity_produces_real_hashes(tmp_path):
    samples_path = tmp_path / "samples.json"
    samples_path.write_text(json.dumps(_make_samples_doc(1)))
    review_path = tmp_path / "review.json"
    review_path.write_text(json.dumps({"review_items": []}))

    identity = driver.build_freeze_identity(samples_path, review_path)
    assert len(identity["samples_file_sha256"]) == 64
    assert len(identity["git_head"]) == 40
    assert "alpha_classifier_prompt_identity_sha256" in identity


# ---------------------------------------------------------------------------
# main(): `live` is ALWAYS predict-only and NEVER reads review_items, even
# if the review form is malformed (scoring is a fully separate `score` mode).
# ---------------------------------------------------------------------------


def test_live_mode_never_reads_review_items_even_if_review_form_is_malformed(tmp_path, monkeypatch):
    monkeypatch.setenv("COMQUTOR_WEEK2_LLM_ENABLED", "1")
    samples_path = tmp_path / "samples.json"
    samples_path.write_text(json.dumps(_make_samples_doc(1)))
    review_path = tmp_path / "review.json"
    review_path.write_text("not valid json at all")  # would raise if ever json.loads'd
    output_dir = tmp_path / "out"

    monkeypatch.setattr(
        driver,
        "_default_gateway_factory",
        lambda execution_id, output_root, **kwargs: _fake_gateway_factory(
            [json.dumps({"decision": "none", "selected_alpha_id": None})]
        )(execution_id, output_root),
    )

    exit_code = driver.main(
        [
            "live",
            "--i-acknowledge-this-makes-real-provider-calls",
            "--samples-file", str(samples_path),
            "--review-form-file", str(review_path),
            "--output-dir", str(output_dir),
        ]
    )
    assert exit_code == 0
    summary_files = list(output_dir.rglob("t3_eval_summary.json"))
    assert len(summary_files) == 1
    summary = json.loads(summary_files[0].read_text())
    assert summary["scoring"]["scoring_status"].startswith("NOT_APPLICABLE")
    assert "score --prediction-execution-dir" in summary["scoring"]["scoring_status"]


def test_live_mode_max_output_tokens_reaches_the_gateway_factory(tmp_path, monkeypatch):
    monkeypatch.setenv("COMQUTOR_WEEK2_LLM_ENABLED", "1")
    samples_path = tmp_path / "samples.json"
    samples_path.write_text(json.dumps(_make_samples_doc(1)))
    review_path = tmp_path / "review.json"
    review_path.write_text(json.dumps({"review_items": []}))
    output_dir = tmp_path / "out"
    captured = {}

    def fake_factory(execution_id, output_root, **kwargs):
        captured.update(kwargs)
        return _fake_gateway_factory([json.dumps({"decision": "none", "selected_alpha_id": None})])(
            execution_id, output_root
        )

    monkeypatch.setattr(driver, "_default_gateway_factory", fake_factory)

    exit_code = driver.main(
        [
            "live",
            "--i-acknowledge-this-makes-real-provider-calls",
            "--samples-file", str(samples_path),
            "--review-form-file", str(review_path),
            "--output-dir", str(output_dir),
            "--max-output-tokens", "321",
        ]
    )
    assert exit_code == 0
    assert captured["max_tokens"] == 321


# ---------------------------------------------------------------------------
# score mode: fully offline, zero Provider calls, records provenance,
# never overwrites the original prediction.
# ---------------------------------------------------------------------------


def _write_prediction_execution(tmp_dir: Path, records: list[dict]) -> Path:
    execution_dir = tmp_dir / "t3live_fake_execution"
    execution_dir.mkdir(parents=True, exist_ok=True)
    (execution_dir / "t3_eval_records.jsonl").write_text(
        "\n".join(json.dumps(r, ensure_ascii=False) for r in records) + "\n"
    )
    (execution_dir / "freeze_identity.json").write_text(json.dumps({"samples_file_sha256": "abc123"}))
    return execution_dir


def test_score_offline_never_imports_provider_or_gateway_construction():
    """AST-level proof: score_offline's own source never references any
    Provider/gateway-construction symbol -- not just "didn't happen to call
    it in this test", but structurally cannot."""
    import ast
    import inspect

    source = inspect.getsource(driver.score_offline)
    tree = ast.parse(source)
    names_referenced = {node.id for node in ast.walk(tree) if isinstance(node, ast.Name)}
    names_referenced |= {node.attr for node in ast.walk(tree) if isinstance(node, ast.Attribute)}
    forbidden = {
        "map_claim_to_alpha", "build_server_week2_llm_gateway", "create_llm_client",
        "Week2LLMGateway", "SemanticRuntimeSession", "run_live_evaluation",
    }
    assert not (names_referenced & forbidden)


def test_score_offline_makes_zero_gateway_calls_even_if_monkeypatch_would_raise(tmp_path, monkeypatch):
    """Behavioral proof to accompany the structural one above: even if
    gateway construction WERE somehow reached, it would raise -- and it
    never does."""
    import comqutor_alpha.structure_engine.week2_llm as week2_llm

    def _must_not_be_called(*args, **kwargs):
        raise AssertionError("score_offline must never construct a gateway or call a Provider")

    monkeypatch.setattr(week2_llm, "build_server_week2_llm_gateway", _must_not_be_called)

    execution_dir = _write_prediction_execution(
        tmp_path,
        [
            {
                "sample_id": "test-0", "outcome_code": "MATCHED", "predicted_alpha": "A501",
                "quota_category": "A501", "input": {"claim": "claim text 0"},
            }
        ],
    )
    review_path = tmp_path / "review.json"
    review_path.write_text(
        json.dumps({"review_items": [{"sample_id": "test-0", "claim_text": "claim text 0", "your_judgment": "A501"}]})
    )

    result = driver.score_offline(prediction_execution_dir=execution_dir, review_form_file=review_path)
    assert result["scoring"]["scoring_status"] == "SCORED"
    assert result["scoring"]["overall_accuracy"] == 1.0


def test_score_offline_records_provenance_and_writes_a_new_file_never_overwriting_the_original(tmp_path):
    execution_dir = _write_prediction_execution(
        tmp_path,
        [
            {
                "sample_id": "test-0", "outcome_code": "MATCHED", "predicted_alpha": "A501",
                "quota_category": "A501", "input": {"claim": "claim text 0"},
            }
        ],
    )
    original_records_bytes = (execution_dir / "t3_eval_records.jsonl").read_bytes()
    review_path = tmp_path / "review.json"
    review_path.write_text(
        json.dumps({"review_items": [{"sample_id": "test-0", "claim_text": "claim text 0", "your_judgment": "A501"}]})
    )

    result = driver.score_offline(prediction_execution_dir=execution_dir, review_form_file=review_path)

    assert result["source_prediction_execution_id"] == "t3live_fake_execution"
    assert len(result["source_predictions_file_sha256"]) == 64
    assert len(result["review_form_file_sha256"]) == 64
    # the original prediction file is byte-for-byte untouched.
    assert (execution_dir / "t3_eval_records.jsonl").read_bytes() == original_records_bytes


def test_score_offline_detects_claim_text_drift_between_prediction_and_review(tmp_path):
    execution_dir = _write_prediction_execution(
        tmp_path,
        [
            {
                "sample_id": "test-0", "outcome_code": "MATCHED", "predicted_alpha": "A501",
                "quota_category": "A501", "input": {"claim": "the ORIGINAL claim text sent to the Provider"},
            }
        ],
    )
    review_path = tmp_path / "review.json"
    review_path.write_text(
        json.dumps(
            {"review_items": [{"sample_id": "test-0", "claim_text": "a DIFFERENT, drifted claim text", "your_judgment": "A501"}]}
        )
    )

    result = driver.score_offline(prediction_execution_dir=execution_dir, review_form_file=review_path)
    assert result["sample_version_consistent"] is False
    assert result["sample_version_mismatches"][0]["reason"] == "CLAIM_TEXT_MISMATCH_BETWEEN_PREDICTION_AND_REVIEW"


def test_score_offline_flags_a_judged_sample_id_missing_from_predictions(tmp_path):
    execution_dir = _write_prediction_execution(tmp_path, [])
    review_path = tmp_path / "review.json"
    review_path.write_text(
        json.dumps({"review_items": [{"sample_id": "never-predicted", "claim_text": "x", "your_judgment": "A501"}]})
    )
    result = driver.score_offline(prediction_execution_dir=execution_dir, review_form_file=review_path)
    assert result["sample_version_consistent"] is False
    assert result["sample_version_mismatches"][0]["reason"] == "JUDGED_SAMPLE_ID_NOT_IN_PREDICTION_RECORDS"


def test_cli_score_mode_writes_a_new_result_file_and_prints_it(tmp_path):
    execution_dir = _write_prediction_execution(
        tmp_path,
        [
            {
                "sample_id": "test-0", "outcome_code": "MATCHED", "predicted_alpha": "A501",
                "quota_category": "A501", "input": {"claim": "claim text 0"},
            }
        ],
    )
    review_path = tmp_path / "review.json"
    review_path.write_text(
        json.dumps({"review_items": [{"sample_id": "test-0", "claim_text": "claim text 0", "your_judgment": "A501"}]})
    )

    exit_code = driver.main(
        [
            "score",
            "--review-form-file", str(review_path),
            "--prediction-execution-dir", str(execution_dir),
        ]
    )
    assert exit_code == 0
    result_files = list(execution_dir.glob("*_score_result.json"))
    assert len(result_files) == 1
    result = json.loads(result_files[0].read_text())
    assert result["scoring"]["scoring_status"] == "SCORED"


def test_cli_score_mode_requires_prediction_execution_dir(tmp_path):
    review_path = tmp_path / "review.json"
    review_path.write_text(json.dumps({"review_items": []}))
    exit_code = driver.main(["score", "--review-form-file", str(review_path)])
    assert exit_code == 2


# ---------------------------------------------------------------------------
# Human-review worksheet: export (readable), import (merge back), and the
# CLI wiring for both, kept strictly separate from prediction commands.
# ---------------------------------------------------------------------------


def _make_review_doc(n=3):
    return {
        "review_items": [
            {
                "sample_id": f"test-{i}",
                "quota_category": "A001",
                "ticker": "NVDA",
                "claim_text": f"claim text {i}",
                "alpha_judgment_feasibility": "JUDGABLE_FROM_TEXT_ALONE",
                "source_material_completeness_status": "RAW_AGENT_REPORT_TEXT_ONLY",
                "your_judgment": None,
                "your_rationale": None,
                "reviewer_id": None,
                "reviewed_at": None,
            }
            for i in range(n)
        ],
        "hidden_system_answers": {f"test-{i}": {"current_production_matched_alpha": "A001"} for i in range(n)},
        "human_review_performed": False,
        "review_status": "NOT_STARTED",
    }


def test_export_review_worksheet_never_includes_hidden_answers(tmp_path):
    review_path = tmp_path / "review.json"
    review_path.write_text(json.dumps(_make_review_doc(2)))
    worksheet_path = tmp_path / "worksheet.csv"

    row_count = driver.export_review_worksheet(review_path, worksheet_path)
    assert row_count == 2

    content = worksheet_path.read_text()
    assert "current_production_matched_alpha" not in content
    assert "A001" in content  # quota_category/alpha_judgment_feasibility are shown, just not the hidden answer
    rows = list(csv.DictReader(worksheet_path.open()))
    assert rows[0]["your_judgment"] == ""
    assert set(driver.WORKSHEET_FIELDS) == set(rows[0].keys())


def test_import_review_worksheet_merges_real_judgments_and_leaves_blanks_untouched(tmp_path):
    review_path = tmp_path / "review.json"
    review_path.write_text(json.dumps(_make_review_doc(3)))
    worksheet_path = tmp_path / "worksheet.csv"
    driver.export_review_worksheet(review_path, worksheet_path)

    rows = list(csv.DictReader(worksheet_path.open()))
    rows[0]["your_judgment"] = "A001"
    rows[0]["your_rationale"] = "clear rate-cut framing"
    rows[0]["reviewer_id"] = "john"
    rows[1]["your_judgment"] = driver.UNABLE_TO_JUDGE
    # rows[2] left entirely blank -- not yet reviewed.
    with worksheet_path.open("w", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=driver.WORKSHEET_FIELDS)
        writer.writeheader()
        writer.writerows(rows)

    result = driver.import_review_worksheet(worksheet_path, review_path)
    assert result["updated_count"] == 2
    assert result["rejected"] == []

    items_by_id = {item["sample_id"]: item for item in result["document"]["review_items"]}
    assert items_by_id["test-0"]["your_judgment"] == "A001"
    assert items_by_id["test-0"]["reviewer_id"] == "john"
    assert items_by_id["test-0"]["reviewed_at"] is not None
    assert items_by_id["test-1"]["your_judgment"] == driver.UNABLE_TO_JUDGE
    # never invented a judgment for a row left blank.
    assert items_by_id["test-2"]["your_judgment"] is None
    assert result["document"]["review_status"] == "IN_PROGRESS -- 2/3 judged"


def test_import_review_worksheet_rejects_invalid_judgment_values_without_crashing(tmp_path):
    review_path = tmp_path / "review.json"
    review_path.write_text(json.dumps(_make_review_doc(1)))
    worksheet_path = tmp_path / "worksheet.csv"
    with worksheet_path.open("w", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=driver.WORKSHEET_FIELDS)
        writer.writeheader()
        writer.writerow(
            {
                "sample_id": "test-0", "quota_category": "A001", "ticker": "NVDA", "claim_text": "x",
                "alpha_judgment_feasibility": "", "source_material_completeness_status": "",
                "your_judgment": "A9999-not-a-real-alpha", "your_rationale": "", "reviewer_id": "",
            }
        )
    result = driver.import_review_worksheet(worksheet_path, review_path)
    assert result["updated_count"] == 0
    assert len(result["rejected"]) == 1
    assert "INVALID_JUDGMENT_VALUE" in result["rejected"][0]["reason"]
    # the original review form is untouched for this sample.
    assert result["document"]["review_items"][0]["your_judgment"] is None


def test_import_review_worksheet_accepts_every_real_taxonomy_alpha_id_not_only_sampling_quota_keys(tmp_path):
    """2026-10-05 fix: _ALLOWED_JUDGMENT_VALUES previously hardcoded only the
    7 Alpha IDs that appear in requested_quota's own sampling-stratification
    keys (t3_targeted_diagnostic_sample_2026-09-30.json's quota buckets
    control which CLAIMS get selected, never which ANSWERS are legal). The
    real, frozen candidate set is the full taxonomy the live classifier
    itself validates against (alpha_mapper.py's own `allowed_ids =
    set(taxonomy)`) -- confirmed to be all 10 top-level alpha_id entries in
    comqutor_alpha/alpha_library/alpha_taxonomy_v1.yaml, including A201,
    A301, and A601, none of which were in the old hardcoded 7-item set. A
    reviewer's genuine judgment that a claim's real mechanism is A301 must
    import successfully, exactly like A001/A304/etc. already did."""
    review_path = tmp_path / "review.json"
    review_path.write_text(json.dumps(_make_review_doc(3)))
    worksheet_path = tmp_path / "worksheet.csv"
    driver.export_review_worksheet(review_path, worksheet_path)

    rows = list(csv.DictReader(worksheet_path.open()))
    rows[0]["your_judgment"] = "A301"
    rows[1]["your_judgment"] = "A201"
    rows[2]["your_judgment"] = "A601"
    with worksheet_path.open("w", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=driver.WORKSHEET_FIELDS)
        writer.writeheader()
        writer.writerows(rows)

    result = driver.import_review_worksheet(worksheet_path, review_path)
    assert result["rejected"] == []
    assert result["updated_count"] == 3
    items_by_id = {item["sample_id"]: item for item in result["document"]["review_items"]}
    assert items_by_id["test-0"]["your_judgment"] == "A301"
    assert items_by_id["test-1"]["your_judgment"] == "A201"
    assert items_by_id["test-2"]["your_judgment"] == "A601"


def test_import_review_worksheet_still_rejects_an_id_outside_the_real_taxonomy(tmp_path):
    """The fix widens the allowed set to the real taxonomy's 10 Alpha IDs --
    it must not become unconstrained. An ID the real taxonomy genuinely does
    not declare is still rejected, exactly like before the fix."""
    review_path = tmp_path / "review.json"
    review_path.write_text(json.dumps(_make_review_doc(1)))
    worksheet_path = tmp_path / "worksheet.csv"
    with worksheet_path.open("w", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=driver.WORKSHEET_FIELDS)
        writer.writeheader()
        writer.writerow(
            {
                "sample_id": "test-0", "quota_category": "A001", "ticker": "NVDA", "claim_text": "x",
                "alpha_judgment_feasibility": "", "source_material_completeness_status": "",
                "your_judgment": "A999", "your_rationale": "", "reviewer_id": "",
            }
        )
    result = driver.import_review_worksheet(worksheet_path, review_path)
    assert result["updated_count"] == 0
    assert len(result["rejected"]) == 1
    assert "INVALID_JUDGMENT_VALUE" in result["rejected"][0]["reason"]


def test_cli_export_then_import_worksheet_roundtrip(tmp_path):
    review_path = tmp_path / "review.json"
    review_path.write_text(json.dumps(_make_review_doc(1)))
    worksheet_path = tmp_path / "worksheet.csv"

    exit_code = driver.main(
        ["export-worksheet", "--review-form-file", str(review_path), "--worksheet-file", str(worksheet_path)]
    )
    assert exit_code == 0
    assert worksheet_path.exists()

    rows = list(csv.DictReader(worksheet_path.open()))
    rows[0]["your_judgment"] = "NONE"
    with worksheet_path.open("w", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=driver.WORKSHEET_FIELDS)
        writer.writeheader()
        writer.writerows(rows)

    exit_code = driver.main(
        ["import-worksheet", "--review-form-file", str(review_path), "--worksheet-file", str(worksheet_path)]
    )
    assert exit_code == 0
    updated = json.loads(review_path.read_text())
    assert updated["review_items"][0]["your_judgment"] == "NONE"
    assert updated["human_review_performed"] is True


def test_worksheet_modes_require_no_samples_file_or_output_dir(tmp_path):
    review_path = tmp_path / "review.json"
    review_path.write_text(json.dumps(_make_review_doc(1)))
    worksheet_path = tmp_path / "worksheet.csv"

    # No --samples-file, no --output-dir passed at all -- export/import must
    # not require them (strict separation from the prediction commands).
    exit_code = driver.main(
        ["export-worksheet", "--review-form-file", str(review_path), "--worksheet-file", str(worksheet_path)]
    )
    assert exit_code == 0


def test_predict_only_and_worksheet_export_are_independent_commands(tmp_path):
    """Exact separate commands exist for predict-only vs review-worksheet
    handling -- neither reads or writes the other's file."""
    samples_path = tmp_path / "samples.json"
    samples_path.write_text(json.dumps(_make_samples_doc(1)))
    review_path = tmp_path / "review.json"
    review_path.write_text(json.dumps(_make_review_doc(1)))
    worksheet_path = tmp_path / "worksheet.csv"

    assert (
        driver.main(["export-worksheet", "--review-form-file", str(review_path), "--worksheet-file", str(worksheet_path)])
        == 0
    )
    # The samples file was never touched by the worksheet export.
    assert json.loads(samples_path.read_text()) == _make_samples_doc(1)


# ---------------------------------------------------------------------------
# _default_gateway_factory: the REAL, only-reachable-in-live-mode
# construction path. Every other test in this file injects a fake
# gateway_factory, which is why a real bug here (an invalid execution_mode
# string, caught only during this round's first live authorized attempt --
# zero cost, the crash happened before any Provider call) was never covered.
# ---------------------------------------------------------------------------


def test_default_gateway_factory_uses_a_valid_execution_mode(tmp_path, monkeypatch):
    """Regression test for a real bug caught during this round's first
    authorized live attempt (zero cost -- the crash happened before any
    Provider call): SemanticRuntimeSession only accepts execution_mode in
    {"live", "shadow", "replay_fixture", "test"}
    (comqutor_alpha.llm_runtime.contracts.EXECUTION_MODES); any other
    string crashes SemanticCallRecorder.__init__ with RECORDER_MODE_INVALID.
    Exercises the REAL _default_gateway_factory end to end (the one factory
    every other test in this file bypasses with a fake), with only the
    underlying model's own real network call avoided by monkeypatching
    create_llm_client at its own real module -- the same seam
    build_server_week2_llm_gateway itself already uses.
    """
    monkeypatch.setenv("COMQUTOR_WEEK2_LLM_ENABLED", "1")
    monkeypatch.setenv("COMQUTOR_WEEK2_LLM_PROVIDER", "deepseek")
    monkeypatch.setenv("COMQUTOR_WEEK2_LLM_MODEL", "deepseek-v4-flash")
    (tmp_path / "exec1").mkdir()

    import tradingagents.llm_clients as llm_clients

    class _FakeClient:
        provider = "deepseek"
        model_name = "deepseek-v4-flash"

        def get_llm(self):
            return _fake_gateway_factory(["{}"])("exec1", tmp_path)[0]._model

    monkeypatch.setattr(llm_clients, "create_llm_client", lambda **kwargs: _FakeClient())

    gateway, session = driver._default_gateway_factory("exec1", tmp_path, max_tokens=200)
    assert session.recorder is not None  # construction succeeded -- no RECORDER_MODE_INVALID
    assert session.execution_mode == "live"
