"""2026-10-06 (round 15): the real recovery path is written but GATED.

`--execute` must do nothing at all -- no gateway, no directory, no request --
unless the operator's own shell exports an acknowledgement bound to the exact
frozen plan, and then only if the environment matches the frozen configuration.
The path itself (`execute_recovery`: send -> assemble 975 -> direction manifest
-> finalize the derived run) is exercised end to end against a fake transport in
a scratch directory, including stop -> resume, where the stage-A gate must stay
failed rather than be waved through.

Zero real Provider calls anywhere in this file.
"""

from __future__ import annotations

import importlib.util
import json
import os
import shutil
import subprocess
import sys
from pathlib import Path

import httpx
import pytest

import comqutor_alpha.structure_engine.week2_llm as week2_llm
from comqutor_alpha.llm_runtime.cache import InMemoryLLMResponseCache
from comqutor_alpha.llm_runtime.session import SemanticRuntimeSession
from comqutor_alpha.structure_engine.week2_llm import build_server_week2_llm_gateway

REPO_ROOT = Path(__file__).resolve().parents[1]
SCRIPT_PATH = (
    REPO_ROOT / "docs" / "audit_artifacts" / "round_source_linking_t0_t2"
    / "round12_alpha_classifier_audit_fix_20261006" / "recover_alpha_classification.py"
)
ORIGINAL_ID = "c904d4cc-dc09-495c-aec5-b056979948e1"
FROZEN_DIR = REPO_ROOT / "outputs" / "runs" / ORIGINAL_ID

pytestmark = pytest.mark.skipif(
    not (SCRIPT_PATH.exists() and (FROZEN_DIR / "structured_agent_outputs.json").exists()),
    reason="recovery script or frozen c904d4cc inputs not present",
)


@pytest.fixture(scope="module")
def recover():
    spec = importlib.util.spec_from_file_location("recover_alpha_classification_gating", SCRIPT_PATH)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


@pytest.fixture(scope="module")
def plan(recover):
    return recover.build_recovery_plan()


def _complete_env(**overrides):
    env = {**{k: v for k, v in {
        "COMQUTOR_WEEK2_LLM_ENABLED": "1", "COMQUTOR_WEEK2_LLM_PROVIDER": "deepseek",
        "COMQUTOR_WEEK2_LLM_MODEL": "deepseek-v4-flash", "COMQUTOR_WEEK2_LLM_MAX_RETRIES": "0",
        "COMQUTOR_WEEK2_LLM_TIMEOUT_SECONDS": "45", "COMQUTOR_WEEK2_LLM_CONCURRENCY": "4",
        "COMQUTOR_WEEK2_LLM_MAX_CALLS": "973", "DEEPSEEK_API_KEY": "not-a-real-key",
        "COMQUTOR_DATABASE_URL": "postgresql+psycopg://user:pw@localhost:5433/comqutor_alpha_test",
        "COMQUTOR_REQUIRE_DATABASE_NAME": "comqutor_alpha_test",
    }.items()}, **overrides}
    return {k: v for k, v in env.items() if v is not None}


# ---------------------------------------------------------------------------
# The gate
# ---------------------------------------------------------------------------


def test_acknowledgement_is_bound_to_the_exact_frozen_plan(recover, plan):
    ack = recover.expected_real_execution_ack(plan)
    assert ack.startswith("recover-973-alpha-classifier-requests-plan-")
    assert recover.real_execution_authorization_problem(plan, {}) is not None
    assert recover.real_execution_authorization_problem(plan, {recover.REAL_EXECUTION_ACK_ENV: "yes"}) is not None
    assert recover.real_execution_authorization_problem(plan, {recover.REAL_EXECUTION_ACK_ENV: ack}) is None

    import copy

    for mutate in (
        lambda p: p[2]["claim_ids"].pop(),                          # a claim removed
        lambda p: p[0]["claim_ids"].reverse(),                      # the order changed
        lambda p: p[0].__setitem__("batch_size", 5),                # the batching changed
    ):
        changed = copy.deepcopy(plan)
        mutate(changed)
        assert recover.expected_real_execution_ack(changed) != ack, "a changed plan must need a new authorization"


def test_execute_without_the_acknowledgement_constructs_nothing_and_exits_1(recover, tmp_path, monkeypatch):
    monkeypatch.delenv(recover.REAL_EXECUTION_ACK_ENV, raising=False)
    monkeypatch.setattr(recover, "OUTPUT_ROOT", tmp_path / "runs")
    built = []
    monkeypatch.setattr(week2_llm, "build_server_week2_llm_gateway", lambda *a, **k: built.append(1))
    assert recover.run_real_recovery(None) == 1
    assert built == [] and not (tmp_path / "runs").exists()


def test_execute_with_a_stale_acknowledgement_is_blocked(recover, tmp_path, monkeypatch):
    monkeypatch.setenv(recover.REAL_EXECUTION_ACK_ENV, "recover-973-alpha-classifier-requests-plan-0000000000000000")
    monkeypatch.setattr(recover, "OUTPUT_ROOT", tmp_path / "runs")
    built = []
    monkeypatch.setattr(week2_llm, "build_server_week2_llm_gateway", lambda *a, **k: built.append(1))
    assert recover.run_real_recovery(None) == 1 and built == []


def test_a_correct_acknowledgement_still_does_nothing_when_the_environment_is_not_the_frozen_one(
    recover, plan, tmp_path, monkeypatch
):
    """The repo .env sets MAX_RETRIES=1 / TIMEOUT=45; an operator who forgot to export MAX_RETRIES=0 must be stopped
    before any gateway exists -- even with a valid acknowledgement."""
    monkeypatch.setenv(recover.REAL_EXECUTION_ACK_ENV, recover.expected_real_execution_ack(plan))
    monkeypatch.setattr(recover, "OUTPUT_ROOT", tmp_path / "runs")
    for key, value in _complete_env(COMQUTOR_WEEK2_LLM_MAX_RETRIES="1").items():
        monkeypatch.setenv(key, value)
    built = []
    monkeypatch.setattr(week2_llm, "build_server_week2_llm_gateway", lambda *a, **k: built.append(1))
    assert recover.run_real_recovery(None) == 1
    assert built == [] and not (tmp_path / "runs").exists()


def test_environment_checks_name_each_deviation(recover):
    assert recover.real_environment_problems(0, _complete_env()) == []
    assert any("MAX_RETRIES" in p for p in recover.real_environment_problems(0, _complete_env(COMQUTOR_WEEK2_LLM_MAX_RETRIES="1")))
    assert any("TIMEOUT" in p for p in recover.real_environment_problems(0, _complete_env(COMQUTOR_WEEK2_LLM_TIMEOUT_SECONDS="20")))
    assert any("TIMEOUT" in p for p in recover.real_environment_problems(0, _complete_env(COMQUTOR_WEEK2_LLM_TIMEOUT_SECONDS=None)))
    assert any("MODEL" in p for p in recover.real_environment_problems(0, _complete_env(COMQUTOR_WEEK2_LLM_MODEL="other")))
    assert any("CONCURRENCY" in p for p in recover.real_environment_problems(0, _complete_env(COMQUTOR_WEEK2_LLM_CONCURRENCY="8")))
    assert any("MAX_CALLS" in p for p in recover.real_environment_problems(0, _complete_env(COMQUTOR_WEEK2_LLM_MAX_CALLS="974")))
    assert any("MAX_CALLS" in p for p in recover.real_environment_problems(0, _complete_env(COMQUTOR_WEEK2_LLM_MAX_CALLS=None)))
    assert any("DEEPSEEK_API_KEY" in p for p in recover.real_environment_problems(0, _complete_env(DEEPSEEK_API_KEY=None)))
    assert any("MAX_TOKENS" in p for p in recover.real_environment_problems(0, _complete_env(COMQUTOR_WEEK2_ALPHA_CLASSIFIER_MAX_TOKENS="64")))
    assert any("BASE_URL" in p for p in recover.real_environment_problems(0, _complete_env(COMQUTOR_WEEK2_LLM_BASE_URL="https://example.invalid")))
    assert any("COMQUTOR_DATABASE_URL" in p for p in recover.real_environment_problems(0, _complete_env(COMQUTOR_DATABASE_URL=None)))
    main_db = "postgresql+psycopg://user:pw@localhost:5433/comqutor_alpha"
    assert any("_test" in p for p in recover.real_environment_problems(
        0, _complete_env(COMQUTOR_DATABASE_URL=main_db, COMQUTOR_REQUIRE_DATABASE_NAME="comqutor_alpha")))
    assert any("REQUIRE_DATABASE_NAME" in p for p in recover.real_environment_problems(
        0, _complete_env(COMQUTOR_REQUIRE_DATABASE_NAME=None)))
    # a resume only gets what is left of the cap
    assert recover.real_environment_problems(19, _complete_env(COMQUTOR_WEEK2_LLM_MAX_CALLS="954")) == []
    assert any("MAX_CALLS" in p for p in recover.real_environment_problems(19, _complete_env(COMQUTOR_WEEK2_LLM_MAX_CALLS="955")))


def test_the_cli_refuses_execute_without_an_acknowledgement_and_leaves_the_real_runs_directory_alone():
    runs = REPO_ROOT / "outputs" / "runs"
    before = sorted(p.name for p in runs.iterdir())
    env = {k: v for k, v in os.environ.items() if k != "COMQUTOR_RECOVERY_REAL_EXECUTION_ACK"}
    result = subprocess.run([sys.executable, str(SCRIPT_PATH), "--execute"], capture_output=True, text=True, env=env, cwd=REPO_ROOT)
    assert result.returncode == 1
    assert "BLOCKED" in result.stderr and "sent nothing" in result.stderr
    assert sorted(p.name for p in runs.iterdir()) == before


# ---------------------------------------------------------------------------
# execute_recovery end to end, fake transport, scratch directory
# ---------------------------------------------------------------------------


def _ok(decision="none", alpha=None):
    return httpx.Response(200, json={
        "id": "x", "object": "chat.completion", "created": 0, "model": "deepseek-v4-flash",
        "choices": [{"index": 0, "message": {"role": "assistant", "content": json.dumps(
            {"decision": decision, "selected_alpha_id": alpha})}, "finish_reason": "stop"}],
        "usage": {"prompt_tokens": 1, "completion_tokens": 1, "total_tokens": 2}})


def _gateway(out_root, monkeypatch, handler, run_id, *, max_calls):
    monkeypatch.setenv("COMQUTOR_WEEK2_LLM_ENABLED", "1")
    monkeypatch.setenv("COMQUTOR_WEEK2_LLM_PROVIDER", "deepseek")
    monkeypatch.setenv("COMQUTOR_WEEK2_LLM_MODEL", "deepseek-v4-flash")
    monkeypatch.setenv("COMQUTOR_WEEK2_LLM_MAX_RETRIES", "0")
    monkeypatch.setenv("COMQUTOR_WEEK2_LLM_MAX_CALLS", str(max_calls))
    monkeypatch.setenv("COMQUTOR_WEEK2_LLM_TIMEOUT_SECONDS", "45")
    monkeypatch.setenv("DEEPSEEK_API_KEY", "fixed-test-key-not-real")
    gateway = build_server_week2_llm_gateway(
        run_id, out_root, enable_request_response_audit=True, _base_transport_for_testing=httpx.MockTransport(handler))
    (out_root / run_id).mkdir(parents=True, exist_ok=True)
    gateway.attach_semantic_runtime(SemanticRuntimeSession(
        run_id=run_id, output_directory=str(out_root / run_id), execution_mode="live",
        provider=gateway.provider, model=gateway.model_name, cache=InMemoryLLMResponseCache()))
    return gateway


@pytest.fixture
def scratch(recover, tmp_path, monkeypatch):
    from comqutor_alpha.storage.db.repository import build_write_repository_from_env

    out_root = tmp_path / "outputs"
    out_root.mkdir()
    shutil.copytree(FROZEN_DIR, out_root / ORIGINAL_ID)
    monkeypatch.setenv("COMQUTOR_DATABASE_URL", f"sqlite:///{tmp_path / 'scratch.db'}")
    repository = build_write_repository_from_env(str(out_root))
    structured = json.loads((FROZEN_DIR / "structured_agent_outputs.json").read_text())
    return {
        "out_root": out_root, "repository": repository, "tmp": tmp_path,
        "records_by_id": {r["claim_id"]: r for r in structured["records"]},
        "scope": recover.compute_recovery_scope(),
    }


def _small_plan(plan, extra=30):
    return [plan[0], plan[1], {**plan[2], "claim_ids": plan[2]["claim_ids"][:extra]}]


def _execute(recover, scratch, plan, gateway, execution_id, **kw):
    return recover.execute_recovery(
        plan=plan, records_by_id=scratch["records_by_id"], scope=scratch["scope"], gateway=gateway,
        output_root=scratch["out_root"], base_run_id=ORIGINAL_ID, execution_id=execution_id,
        checkpoint_origin="fake_http_test", repository=scratch["repository"], **kw)


def test_execute_recovery_end_to_end_finalizes_a_derived_run_and_keeps_unrecovered_claims_visible(
    recover, plan, scratch, monkeypatch
):
    from comqutor_alpha.api import routes_research

    small = _small_plan(plan)
    total = sum(len(s["claim_ids"]) for s in small)  # 49
    sends = []

    def handler(request):
        sends.append(1)
        return _ok("select", "A304")

    execution_id = "recovery-20261006T000000Z-aaaaaaaa"
    gateway = _gateway(scratch["out_root"], monkeypatch, handler, execution_id, max_calls=total)
    result = _execute(recover, scratch, small, gateway, execution_id, hard_cap=total)

    assert result["outcome"]["stop_reason"] is None and len(sends) == total
    assert result["outcome"]["task_isolation"]["request_tasks_observed"] == {"alpha_classifier": total}
    assert result["assembly"]["sources"] == {"reused": 2, "recovered": total, "rematerialized": 0, "kept_original": 973 - total}
    assert result["finalized"]["status"] == "ok" and result["finalized"]["base_run_unchanged"] is True

    response = routes_research.build_research_response(
        execution_id, output_root=str(scratch["out_root"]), graph_repository=scratch["repository"])
    assert response["status"] == "completed" and response["lineage"]["based_on_run_id"] == ORIGINAL_ID
    completion = response["alpha_classification_completion"]
    assert completion["complete"] is False and completion["call_failure_count"] == 973 - total, \
        "claims the run did not reach stay disclosed as failures in the derived run -- never turned into NONE"
    assert response["alpha_classification_status"] == "incomplete"

    manifest = json.loads((scratch["out_root"] / execution_id / "llm_semantic_manifest.json").read_text())
    assert manifest["complete"] is True and manifest["provider_call_count"] == total
    assert result["stance_followup"]["matched_claims"] == total + 0 and result["stance_followup"]["independent_request_budget"] >= 1
    assert (scratch["out_root"] / execution_id / "checkpoint_recovery.json").exists()


def test_a_stopped_run_creates_no_derived_run_and_a_resume_cannot_wave_the_failed_gate_through(
    recover, plan, scratch, monkeypatch
):
    small = _small_plan(plan)
    execution_id = "recovery-20261006T000001-bbbbbbbb"
    sends = []

    def unauthorized(request):
        sends.append(1)
        return httpx.Response(401, json={"error": {"message": "invalid key"}})

    first = _gateway(scratch["out_root"], monkeypatch, unauthorized, execution_id, max_calls=49)
    stopped = _execute(recover, scratch, small, first, execution_id, hard_cap=49)
    assert stopped["outcome"]["stop_reason"] == "auth_failure" and stopped["finalized"] is None
    assert len(sends) == 4, "stage A is one 4-claim batch; nothing after it was scheduled"
    assert not (scratch["out_root"] / execution_id / "recovery_lineage.json").exists()
    manifest = json.loads((scratch["out_root"] / execution_id / "llm_semantic_manifest.json").read_text())
    assert manifest["complete"] is False
    assert scratch["repository"].get_research_run_record(execution_id) is None, "a stopped run is not registered as a run"

    healthy = []

    def ok(request):
        healthy.append(1)
        return _ok("none")

    second = _gateway(scratch["out_root"], monkeypatch, ok, execution_id, max_calls=45)
    resumed = _execute(recover, scratch, small, second, execution_id, hard_cap=49)
    assert resumed["outcome"]["stop_reason"] == "stage_a_gate_failed"
    assert sorted(resumed["outcome"]["stop_detail"]["not_protocol_complete"].values()) == ["failed"] * 4
    assert healthy == [], "the four failed claims are never auto-resent, and no later stage ran"
    assert resumed["finalized"] is None


# ---------------------------------------------------------------------------
# Round 16: lineage labels must be TRUE (found on the real run: a timed-out attempt and 18 cache-served claims were
# first labelled `recovered_real_classification`)
# ---------------------------------------------------------------------------


def _input_hash(record):
    from comqutor_alpha.llm_runtime.canonical_json import sha256_canonical_json
    from comqutor_alpha.structure_engine import alpha_mapper

    return sha256_canonical_json({
        "claim": str(record.get("claim") or ""), "evidence": str(record.get("evidence") or ""),
        "ticker": str(record.get("ticker") or ""), "factors": alpha_mapper._record_factors(record),
        "direction": alpha_mapper.normalize_direction(record.get("direction")),
        "alpha_taxonomy": alpha_mapper._alpha_taxonomy_request_block(alpha_mapper.load_alpha_taxonomy()),
    })


def test_assembly_labels_a_failed_attempt_as_an_attempt_not_a_recovery(recover):
    original = {"matches": [{"claim_id": c, "alpha_match_method": "llm_unavailable", "alpha_match_fallback_reason": "provider_error"} for c in ("a", "b", "c")]}
    full = {
        "a": {"claim_id": "a", "alpha_match_method": "llm", "alpha_match_fallback_reason": None, "matched_alpha": "A304"},
        "b": {"claim_id": "b", "alpha_match_method": "llm_unavailable", "alpha_match_fallback_reason": "provider_timeout", "matched_alpha": None},
        "c": {"claim_id": "c", "alpha_match_method": "llm", "alpha_match_fallback_reason": None, "matched_alpha": None},
    }
    _, report = recover.assemble_recovered_alpha_matches(
        original, {"valid_llm_results_claim_ids": []}, records_by_id={}, full_match_records=full, audit_states={})
    assert report["claim_sources"] == {"a": "recovered_real_classification", "b": "attempted_failed_no_valid_result", "c": "recovered_real_classification"}


def test_lineage_separates_own_request_cache_served_and_failed_claims(recover, plan, scratch, monkeypatch):
    """Through the real execute_recovery: a twin pair (identical request input) placed in different batches so the
    second is served by the run-local cache, plus one claim whose request fails with HTTP 500."""
    records = scratch["records_by_id"]
    nineteen = set(recover.load_nineteen_claim_ids())
    pool = [c for c in plan[2]["claim_ids"] if c not in nineteen]
    groups = {}
    for claim_id in pool:
        groups.setdefault(_input_hash(records[claim_id]), []).append(claim_id)
    twin_a, twin_b = next(ids[:2] for ids in groups.values() if len(ids) >= 2)
    singles = [ids[0] for ids in groups.values() if len(ids) == 1][:24]
    failing = singles[3]
    stage_c = [twin_a, *singles, twin_b]  # twin_b lands in the second batch of 25, after twin_a is cached
    small = [plan[0], plan[1], {**plan[2], "claim_ids": stage_c}]
    total = 19 + len(stage_c)

    def needle(claim_id):
        return '"claim": "' + json.dumps(records[claim_id]["claim"], ensure_ascii=False)[1:-1] + '"'

    sends = []

    def handler(request):
        sends.append(1)
        prompt = json.loads(request.content)["messages"][0]["content"]
        if needle(failing) in prompt:
            return httpx.Response(500, json={"error": {"message": "boom"}})
        return _ok("select", "A304")

    execution_id = "recovery-20261006T000002-cccccccc"
    gateway = _gateway(scratch["out_root"], monkeypatch, handler, execution_id, max_calls=total)
    result = _execute(recover, scratch, small, gateway, execution_id, hard_cap=total)

    assert result["outcome"]["stop_reason"] is None and result["finalized"]["status"] == "ok"
    assert len(sends) == total - 1, "the cache-served twin sent nothing"
    lineage = json.loads((scratch["out_root"] / execution_id / "recovery_lineage.json").read_text())
    entry = {e["claim_id"]: e for e in lineage["claim_identity_map"]}
    assert entry[twin_a]["classification_source"] == "recovered_real_classification" and entry[twin_a]["cache_source_call_id"] is None
    assert entry[twin_b]["classification_source"] == "recovered_via_identical_input_cache" and entry[twin_b]["cache_source_call_id"]
    assert entry[failing]["classification_source"] == "attempted_failed_no_valid_result"
    assert entry[failing]["derived_alpha_match_method"] == "llm_unavailable"
    counts = lineage["classification_source_counts"]
    assert counts["recovered_via_identical_input_cache"] == 1 and counts["attempted_failed_no_valid_result"] == 1
    assert counts["recovered_real_classification"] == total - 2
