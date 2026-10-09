"""2026-10-06 (round 15): the two zero-call preparations for the real AMD
classification recovery.

1. Classification vs direction-task isolation. The fake transport returns
   VALID Alpha *selections* (not NONE), so the follow-up direction step would
   have real work; the recovery path must still send only alpha_classifier
   requests. A control shows the production payload path DOES append
   evidence_stance_classifier requests for the same input, and that the guard
   refuses them -- so the assertions can actually detect the failure.
2. Derived run save/view path. A recovery execution is built from the frozen
   c904d4cc inputs plus an assembled (fake-HTTP) classification, and read back
   through the real API routes and the real Export ZIP. The original run is
   hash-verified unchanged.

Everything uses only the bottom-most httpx transport faked; zero real Provider
calls. All scratch artifacts live under pytest tmp_path -- never outputs/runs/.
"""

from __future__ import annotations

import importlib.util
import io
import itertools
import json
import math
import os
import shutil
import threading
import zipfile
from pathlib import Path

import httpx
import pytest

import comqutor_alpha.structure_engine.week2_llm as week2_llm
from comqutor_alpha.classification_recovery import (
    RECOVERY_EXECUTION_TYPE,
    RECOVERY_LINEAGE_FILENAME,
    STANCE_FOLLOWUP_MANIFEST_FILENAME,
    RecoveryTaskNotAllowedError,
    TaskAllowlistGateway,
    build_stance_followup_manifest,
    finalize_classification_recovery_execution,
    new_recovery_execution_id,
    snapshot_directory_hashes,
)
from comqutor_alpha.llm_runtime.cache import InMemoryLLMResponseCache
from comqutor_alpha.llm_runtime.session import SemanticRuntimeSession
from comqutor_alpha.structure_engine import alpha_mapper
from comqutor_alpha.structure_engine import evidence_stance_llm as esl
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

RUN_ID = "recovery-isolation-test"
ALPHAS = ("A304", "A102")


@pytest.fixture(scope="module")
def recover():
    spec = importlib.util.spec_from_file_location("recover_alpha_classification_r15", SCRIPT_PATH)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


@pytest.fixture(scope="module")
def full_plan(recover):
    return recover.build_recovery_plan()


@pytest.fixture(scope="module")
def records_by_id():
    structured = json.loads((FROZEN_DIR / "structured_agent_outputs.json").read_text())
    return {r["claim_id"]: r for r in structured["records"]}


def _small_plan(full_plan, extra=30):
    """19 analytical-SUPPORTS claims (4 + 15) plus `extra` of the rest, same stage shape."""
    return [full_plan[0], full_plan[1], {**full_plan[2], "claim_ids": full_plan[2]["claim_ids"][:extra]}]


def _answer(decision, alpha=None):
    return httpx.Response(200, json={
        "id": "x", "object": "chat.completion", "created": 0, "model": "deepseek-v4-flash",
        "choices": [{"index": 0, "message": {"role": "assistant", "content": json.dumps(
            {"decision": decision, "selected_alpha_id": alpha})}, "finish_reason": "stop"}],
        "usage": {"prompt_tokens": 1, "completion_tokens": 1, "total_tokens": 2}})


def _selecting_handler(sends):
    """Every request gets a VALID Alpha selection (alternating A304/A102)."""
    counter = itertools.count()
    lock = threading.Lock()

    def handler(request):
        with lock:
            sends.append(json.loads(request.content)["messages"][0]["content"][:60])
            alpha = ALPHAS[next(counter) % len(ALPHAS)]
        return _answer("select", alpha)

    return handler


def _gateway(root, monkeypatch, handler, *, run_id=RUN_ID, max_calls=973):
    monkeypatch.setenv("COMQUTOR_WEEK2_LLM_ENABLED", "1")
    monkeypatch.setenv("COMQUTOR_WEEK2_LLM_PROVIDER", "deepseek")
    monkeypatch.setenv("COMQUTOR_WEEK2_LLM_MODEL", "deepseek-v4-flash")
    monkeypatch.setenv("COMQUTOR_WEEK2_LLM_MAX_RETRIES", "0")
    monkeypatch.setenv("COMQUTOR_WEEK2_LLM_MAX_CALLS", str(max_calls))
    monkeypatch.setenv("COMQUTOR_WEEK2_LLM_TIMEOUT_SECONDS", "45")
    monkeypatch.setenv("DEEPSEEK_API_KEY", "fixed-test-key-not-real")
    root.mkdir(parents=True, exist_ok=True)
    gateway = build_server_week2_llm_gateway(
        run_id, root, enable_request_response_audit=True,
        _base_transport_for_testing=httpx.MockTransport(handler),
    )
    assert gateway is not None
    (root / run_id).mkdir(exist_ok=True)
    gateway.attach_semantic_runtime(SemanticRuntimeSession(
        run_id=run_id, output_directory=str(root / run_id), execution_mode="live",
        provider=gateway.provider, model=gateway.model_name, cache=InMemoryLLMResponseCache()))
    return gateway


def _audit(root, which, run_id=RUN_ID):
    name = {"req": week2_llm.PROVIDER_REQUEST_AUDIT_ARTIFACT_PATH, "resp": week2_llm.PROVIDER_RESPONSE_AUDIT_ARTIFACT_PATH}[which]
    path = root / run_id / name
    return [json.loads(line) for line in path.read_text().splitlines() if line.strip()] if path.exists() else []


def _run(recover, plan, records_by_id, gateway, root, *, run_id=RUN_ID, **overrides):
    return recover.run_staged_recovery(
        plan, records_by_id, gateway=gateway, run_output_root=root, run_id=run_id,
        checkpoint_path=root / "checkpoint.json", map_fn=alpha_mapper.map_structured_records,
        **{"checkpoint_origin": "fake_http_test", **overrides},
    )


# ---------------------------------------------------------------------------
# TaskAllowlistGateway
# ---------------------------------------------------------------------------


class _StubGateway:
    model_name = "stub-model"
    call_count = 7

    def __init__(self):
        self.calls = []

    def invoke_json_with_trace(self, task, payload, validator, *, claim_ids=None):
        self.calls.append(("trace", task, claim_ids))
        return "invocation"

    def invoke_json(self, task, payload, validator):
        self.calls.append(("json", task))
        return "json"

    def invoke_prebuilt_json_prompt(self, *, task, prompt, **kwargs):
        self.calls.append(("prebuilt", task))
        return "prebuilt"

    def finalize_semantic_invocation(self, invocation, **kwargs):
        self.calls.append(("finalize",))


def test_allowlist_proxy_forwards_allowed_task_with_claim_ids_and_passes_attributes_through():
    stub = _StubGateway()
    proxy = TaskAllowlistGateway(stub)
    assert alpha_mapper._gateway_accepts_claim_ids(proxy) is True, "claim_ids must still reach the audit log through the proxy"
    assert proxy.invoke_json_with_trace("alpha_classifier", {}, None, claim_ids=("c1",)) == "invocation"
    assert stub.calls == [("trace", "alpha_classifier", ("c1",))]
    assert (proxy.model_name, proxy.call_count) == ("stub-model", 7)
    proxy.finalize_semantic_invocation("invocation", accepted=True)
    assert stub.calls[-1] == ("finalize",)
    assert proxy.refused_tasks == []


def test_allowlist_proxy_refuses_every_other_task_on_all_three_provider_entry_points_before_forwarding():
    stub = _StubGateway()
    proxy = TaskAllowlistGateway(stub)
    with pytest.raises(RecoveryTaskNotAllowedError):
        proxy.invoke_json_with_trace("evidence_stance_classifier", {}, None)
    with pytest.raises(RecoveryTaskNotAllowedError):
        proxy.invoke_json("evidence_stance_classifier", {}, None)
    with pytest.raises(RecoveryTaskNotAllowedError):
        proxy.invoke_prebuilt_json_prompt(task="content_support_verification", prompt="p")
    assert stub.calls == [], "a refused task must never reach the wrapped gateway"
    assert proxy.refused_tasks == ["evidence_stance_classifier", "evidence_stance_classifier", "content_support_verification"]


# ---------------------------------------------------------------------------
# Section 2.2: classification vs direction-task isolation
# ---------------------------------------------------------------------------


def test_recovery_with_valid_alpha_matches_sends_only_classification_requests(
    recover, full_plan, records_by_id, tmp_path, monkeypatch
):
    """The fake returns a valid Alpha SELECTION for every claim, so every claim ends up matched and the
    direction step would have real work. The actual recovery path must still send only alpha_classifier."""
    plan = _small_plan(full_plan)
    total = sum(len(s["claim_ids"]) for s in plan)  # 19 + 30
    sends = []
    gateway = _gateway(tmp_path, monkeypatch, _selecting_handler(sends), max_calls=total)
    outcome = _run(recover, plan, records_by_id, gateway, tmp_path, hard_cap=total)

    assert outcome["stop_reason"] is None
    requests = _audit(tmp_path, "req")
    assert {r["task"] for r in requests} == {"alpha_classifier"}
    assert len(requests) == len(sends) == total, "every audited request is a classification request, and nothing else reached the wire"
    assert outcome["task_isolation"] == {
        "allowed_tasks": ["alpha_classifier"], "refused_tasks": [],
        "request_tasks_observed": {"alpha_classifier": total},
    }
    records = recover.load_match_records(Path(outcome["records_path"]))
    assert len(records) == total and all(r["matched_alpha"] in ALPHAS for r in records.values()), \
        "this must not be a NONE-only scenario: every claim carries a valid selected Alpha"

    budget = recover.stance_followup_budget(list(records.values()))
    assert budget["matched_claims"] == total
    assert budget["stance_items"] >= total and budget["max_requests_with_zero_retries"] >= math.ceil(total / esl.BATCH_SIZE)
    assert len(sends) == total, "sizing the follow-up work must not send anything"


def test_control_the_production_payload_path_does_append_direction_requests_and_the_guard_refuses_them(
    records_by_id, tmp_path, monkeypatch
):
    """Same input, same selecting fake. Through build_alpha_matches_payload (what a normal run uses) the
    evidence_stance_classifier requests ARE sent -- proving the audit-task assertion above can see them --
    and through the allowlist guard they are refused instead."""
    records = list(records_by_id.values())[:12]
    structured = {"run_id": ORIGINAL_ID, "ticker": "AMD", "records": records}

    open_sends = []
    open_gateway = _gateway(tmp_path / "open", monkeypatch, _selecting_handler(open_sends))
    alpha_mapper.build_alpha_matches_payload(structured, classifier_enabled=True, llm_gateway=open_gateway, concurrency=1)
    open_tasks = {r["task"] for r in _audit(tmp_path / "open", "req")}
    assert open_tasks == {"alpha_classifier", "evidence_stance_classifier"}

    guarded_sends = []
    guarded = TaskAllowlistGateway(_gateway(tmp_path / "guarded", monkeypatch, _selecting_handler(guarded_sends)))
    alpha_mapper.build_alpha_matches_payload(structured, classifier_enabled=True, llm_gateway=guarded, concurrency=1)
    assert {r["task"] for r in _audit(tmp_path / "guarded", "req")} == {"alpha_classifier"}
    assert guarded.refused_tasks and set(guarded.refused_tasks) == {"evidence_stance_classifier"}
    assert len(guarded_sends) == 12 < len(open_sends), "the guard removed exactly the direction requests"


def test_executor_stops_and_sends_nothing_when_a_batch_attempts_a_second_task(
    recover, full_plan, records_by_id, tmp_path, monkeypatch
):
    sends = []
    gateway = _gateway(tmp_path, monkeypatch, _selecting_handler(sends), max_calls=49)

    def map_fn_that_also_tries_a_direction_call(batch, *, classifier_enabled, llm_gateway, concurrency):
        results = alpha_mapper.map_structured_records(
            batch, classifier_enabled=classifier_enabled, llm_gateway=llm_gateway, concurrency=concurrency)
        try:  # the mapping layer swallows exceptions into per-claim fallbacks; so does this stand-in
            llm_gateway.invoke_json_with_trace("evidence_stance_classifier", {"items": []}, lambda payload: payload)
        except Exception:
            pass
        return results

    outcome = recover.run_staged_recovery(
        _small_plan(full_plan), records_by_id, gateway=gateway, run_output_root=tmp_path, run_id=RUN_ID,
        checkpoint_path=tmp_path / "checkpoint.json", map_fn=map_fn_that_also_tries_a_direction_call,
        checkpoint_origin="fake_http_test", hard_cap=49)

    assert outcome["stop_reason"] == "task_isolation_violation"
    assert outcome["stop_detail"]["refused_tasks"] == ["evidence_stance_classifier"]
    assert outcome["batches_run"] == 1 and len(sends) == 4, "only the first 4-claim batch's classification requests were sent"
    assert {r["task"] for r in _audit(tmp_path, "req")} == {"alpha_classifier"}


def test_a_resumed_process_counts_requests_already_audited_against_the_same_cap(
    recover, full_plan, records_by_id, tmp_path, monkeypatch
):
    plan = _small_plan(full_plan)
    first_sends = []
    first = _gateway(tmp_path, monkeypatch, _selecting_handler(first_sends), max_calls=30)
    outcome = _run(recover, plan, records_by_id, first, tmp_path, hard_cap=30)
    assert outcome["stop_reason"] == "call_cap_would_be_exceeded" and len(first_sends) == 19

    second_sends = []  # a brand-new process: its own Gateway counter starts at 0
    second = _gateway(tmp_path, monkeypatch, _selecting_handler(second_sends), max_calls=11)
    resumed = _run(recover, plan, records_by_id, second, tmp_path, hard_cap=30)
    assert resumed["stop_reason"] == "call_cap_would_be_exceeded"
    assert resumed["stop_detail"]["prior_sent_by_earlier_processes"] == 19
    assert second_sends == [] and len(_audit(tmp_path, "req")) == 19, "the resume must not get a fresh allowance"


def test_preflight_refuses_a_timeout_that_is_not_exactly_45_seconds(recover, tmp_path, monkeypatch):
    gateway = _gateway(tmp_path, monkeypatch, lambda request: _answer("none"))
    assert recover.preflight_gateway_config(gateway, hard_cap=973, concurrency=4)["timeout_seconds"] == 45.0
    gateway.timeout_seconds = 20.0
    with pytest.raises(RuntimeError, match=r"timeout_seconds=20\.0"):
        recover.preflight_gateway_config(gateway, hard_cap=973, concurrency=4)


def test_audited_request_config_check_reads_the_wire_not_the_gateway_object(recover):
    good = {"url": "https://api.deepseek.com/chat/completions",
            "body": json.dumps({"messages": [], "model": "deepseek-v4-flash", "stream": False}),
            "headers": {"X-Stainless-Read-Timeout": "45.0", "x-stainless-retry-count": "0"}}
    assert recover._request_config_problem(good) is None
    assert "url" in recover._request_config_problem({**good, "url": "https://example.invalid/v1"})
    assert "body keys" in recover._request_config_problem(
        {**good, "body": json.dumps({"messages": [], "model": "deepseek-v4-flash", "stream": False, "max_tokens": 64})})
    assert "read-timeout" in recover._request_config_problem({**good, "headers": {"x-stainless-read-timeout": "20.0", "x-stainless-retry-count": "0"}})
    assert "retry-count" in recover._request_config_problem({**good, "headers": {"x-stainless-read-timeout": "45.0", "x-stainless-retry-count": "2"}})
    assert "model" in recover._request_config_problem(
        {**good, "body": json.dumps({"messages": [], "model": "other", "stream": False})})


# ---------------------------------------------------------------------------
# Direction-task follow-up manifest
# ---------------------------------------------------------------------------


@pytest.fixture(scope="module")
def selected_match_records(recover, full_plan, records_by_id, tmp_path_factory):
    root = tmp_path_factory.mktemp("manifest_src")
    mp = pytest.MonkeyPatch()
    try:
        plan = _small_plan(full_plan)
        total = sum(len(s["claim_ids"]) for s in plan)
        gateway = _gateway(root, mp, _selecting_handler([]), max_calls=total)
        outcome = _run(recover, plan, records_by_id, gateway, root, hard_cap=total)
    finally:
        mp.undo()
    return list(recover.load_match_records(Path(outcome["records_path"])).values())


def test_stance_manifest_lists_the_needed_direction_requests_with_an_independent_budget(selected_match_records):
    manifest = build_stance_followup_manifest(selected_match_records, base_run_id=ORIGINAL_ID, execution_id="recovery-x")
    from comqutor_alpha.alpha_library.alpha_loader import load_alpha_taxonomy

    expected_items = esl.build_stance_request_items(selected_match_records, load_alpha_taxonomy())
    assert manifest["pairs_total"] == manifest["pairs_needing_request"] == len(expected_items) > 0
    assert [(i["claim_id"], i["target_alpha_id"]) for i in manifest["items"]] == [(i.claim_id, i.target_alpha_id) for i in expected_items]
    assert manifest["independent_request_budget"] == math.ceil(len(expected_items) / esl.BATCH_SIZE)
    assert manifest["task"] == "evidence_stance_classifier"
    assert manifest["sent_by_this_manifest"] == 0
    assert manifest["requires_separate_authorization"] is True
    assert manifest["counted_against_classification_cap"] is False
    assert all(len(i["request_payload_sha256"]) == 64 for i in manifest["items"])


def test_stance_manifest_reuses_only_an_existing_llm_direction_result_for_the_same_claim_and_alpha(selected_match_records):
    import copy

    base = copy.deepcopy(selected_match_records[:3])
    claim = base[0]
    alpha = claim["matched_alpha"]
    candidate = next(c for c in claim["candidate_scores"] if c["alpha_id"] == alpha)

    candidate["stance_method"] = "deterministic_fallback"
    deterministic_only = build_stance_followup_manifest(selected_match_records, base_match_records=base)
    plain = build_stance_followup_manifest(selected_match_records)
    assert deterministic_only["pairs_reusable_from_base_run"] == 0, "a deterministic stance is never a reusable direction result"
    assert deterministic_only["pairs_needing_request"] == plain["pairs_needing_request"]

    candidate["stance_method"] = "llm"
    reused = build_stance_followup_manifest(selected_match_records, base_match_records=base)
    assert reused["pairs_reusable_from_base_run"] == 1
    assert reused["pairs_needing_request"] == plain["pairs_needing_request"] - 1
    assert [(i["claim_id"], i["target_alpha_id"]) for i in reused["reusable_items"]] == [(claim["claim_id"], alpha)]


def test_stance_manifest_for_a_none_only_recovery_needs_zero_requests(recover, records_by_id):
    none_only = [recover.rematerialize_match_record(r, {"decision": "none", "selected_alpha_id": None})
                 for r in list(records_by_id.values())[:20]]
    manifest = build_stance_followup_manifest(none_only)
    assert (manifest["matched_claims"], manifest["pairs_needing_request"], manifest["independent_request_budget"]) == (0, 0, 0)


# ---------------------------------------------------------------------------
# Section 2.1: derived run save / view path
# ---------------------------------------------------------------------------


def _database_url(root):
    """SQLite scratch file by default. Round 16: COMQUTOR_R16_PRECHECK_DATABASE_URL points the SAME tests at a
    scratch PostgreSQL database (created and dropped by the pre-check driver) to exercise the Postgres path."""
    return os.environ.get("COMQUTOR_R16_PRECHECK_DATABASE_URL") or f"sqlite:///{root / 'derived.db'}"


@pytest.fixture(scope="module")
def derived(recover, full_plan, records_by_id, tmp_path_factory):
    """A full 973-claim fake-HTTP recovery -> assembled -> derived run, in a scratch outputs root with
    its own SQLite database. The real frozen run directory is hash-checked before and after."""
    from comqutor_alpha.storage.db.repository import build_write_repository_from_env

    real_before = snapshot_directory_hashes(FROZEN_DIR)
    root = tmp_path_factory.mktemp("derived_run")
    out_root = root / "outputs"
    out_root.mkdir()
    recover.mark_fake_http_directory(root)
    shutil.copytree(FROZEN_DIR, out_root / ORIGINAL_ID)

    mp = pytest.MonkeyPatch()
    mp.setenv("COMQUTOR_DATABASE_URL", _database_url(root))
    mp.setenv("COMQUTOR_OUTPUT_DIR", str(out_root))
    execution_id = new_recovery_execution_id()
    try:
        selected = [full_plan[2]["claim_ids"][i] for i in (10, 200, 500)]
        selectors = {'"claim": "' + json.dumps(records_by_id[c]["claim"], ensure_ascii=False)[1:-1] + '"' for c in selected}

        def handler(request):
            prompt = json.loads(request.content)["messages"][0]["content"]
            return _answer("select", "A304") if any(n in prompt for n in selectors) else _answer("none")

        gateway = _gateway(out_root, mp, handler, run_id=execution_id)
        outcome = _run(recover, full_plan, records_by_id, gateway, out_root, run_id=execution_id)
        assert outcome["stop_reason"] is None
        gateway.semantic_runtime.finalize_manifest(complete=True)

        original_payload = json.loads((out_root / ORIGINAL_ID / "alpha_matches.json").read_text())
        audit_states = recover.reconcile_claim_states_from_audit_log(out_root, execution_id)
        audit_states.pop("__multi_attempt_warnings__", None)
        payload, report = recover.assemble_recovered_alpha_matches(
            original_payload, recover.compute_recovery_scope(), records_by_id=records_by_id,
            full_match_records=recover.load_match_records(Path(outcome["records_path"])), audit_states=audit_states)

        from comqutor_alpha.storage.file_store import save_json_record
        manifest = build_stance_followup_manifest(
            payload["matches"], base_run_id=ORIGINAL_ID, execution_id=execution_id,
            base_match_records=original_payload["matches"])
        save_json_record(execution_id, STANCE_FOLLOWUP_MANIFEST_FILENAME, manifest, output_root=out_root)

        from comqutor_alpha.api import routes_research

        repository = build_write_repository_from_env(str(out_root))
        # The original run's own agent-output rows, in the SCRATCH database only, so the API can be asked
        # about both runs and the two answers compared.
        repository.persist_agent_outputs(
            run_id=ORIGINAL_ID, ticker="AMD",
            structured_payload=json.loads((out_root / ORIGINAL_ID / "structured_agent_outputs.json").read_text()))
        base_response_before = routes_research.build_research_response(
            ORIGINAL_ID, output_root=str(out_root), graph_repository=repository)
        result = finalize_classification_recovery_execution(
            ORIGINAL_ID, execution_id, assembled_alpha_matches=payload,
            recovery_provenance={"checkpoint_origin": "fake_http_test", "claim_sources": report["claim_sources"],
                                 "assembly_report": {k: v for k, v in report.items() if k != "claim_sources"}},
            output_root=str(out_root), graph_repository=repository)
        yield {
            "root": root, "out_root": out_root, "execution_id": execution_id, "result": result, "report": report,
            "repository": repository, "manifest": manifest, "selected": selected, "payload": payload,
            "base_response_before": base_response_before, "real_before": real_before, "original_payload": original_payload,
        }
    finally:
        mp.undo()


@pytest.fixture
def api(derived, monkeypatch):
    """GET against the real FastAPI app, pointed at the scratch outputs root and SQLite database. The env is
    set per test because tests/conftest.py strips COMQUTOR_DATABASE_URL before every test body."""
    from fastapi.testclient import TestClient

    import comqutor_alpha.api.main as main_module

    monkeypatch.setenv("COMQUTOR_DATABASE_URL", _database_url(derived["root"]))
    monkeypatch.setenv("COMQUTOR_OUTPUT_DIR", str(derived["out_root"]))
    client = TestClient(main_module.app)
    return client.get


def test_derived_run_completes_and_names_its_base(derived):
    result = derived["result"]
    assert result["status"] == "ok" and result["run_status"] == "completed", result
    assert result["based_on_run_id"] == ORIGINAL_ID and result["execution_id"] == derived["execution_id"] != ORIGINAL_ID
    assert derived["execution_id"].startswith("recovery-")
    assert result["classification_source_counts"] == {"reused_original_valid_result": 2, "recovered_real_classification": 973}
    metadata = json.loads((derived["out_root"] / derived["execution_id"] / "metadata.json").read_text())
    assert (metadata["based_on_run_id"], metadata["execution_type"], metadata["run_id"]) == (
        ORIGINAL_ID, RECOVERY_EXECUTION_TYPE, derived["execution_id"])


def test_original_run_is_untouched_in_the_scratch_copy_and_in_the_real_frozen_directory(derived):
    assert derived["result"]["base_run_unchanged"] is True
    scratch_after = snapshot_directory_hashes(derived["out_root"] / ORIGINAL_ID)
    lineage = json.loads((derived["out_root"] / derived["execution_id"] / RECOVERY_LINEAGE_FILENAME).read_text())
    assert scratch_after == lineage["original_run_file_hashes_at_derivation"]
    assert snapshot_directory_hashes(FROZEN_DIR) == derived["real_before"], "the real outputs/runs/c904d4cc... directory must be byte-identical"
    assert not (derived["out_root"] / ORIGINAL_ID / "reevaluation_executions.jsonl").exists(), \
        "unlike the review re-evaluation precedent, nothing is appended into the original run"


def test_lineage_maps_every_original_claim_identity_to_its_derived_identity(derived):
    lineage = json.loads((derived["out_root"] / derived["execution_id"] / RECOVERY_LINEAGE_FILENAME).read_text())
    original_ids = [m["claim_id"] for m in derived["original_payload"]["matches"]]
    mapping = lineage["claim_identity_map"]
    assert [e["claim_id"] for e in mapping] == original_ids and len(mapping) == 975
    assert all(e["original_run_id"] == ORIGINAL_ID and e["derived_run_id"] == derived["execution_id"] for e in mapping)
    assert all(e["agent_output_id"] and e["source_agent_output_id"] for e in mapping)
    counts = {}
    for entry in mapping:
        counts[entry["classification_source"]] = counts.get(entry["classification_source"], 0) + 1
    assert counts == {"reused_original_valid_result": 2, "recovered_real_classification": 973}
    changed = [e for e in mapping if e["original_alpha_match_method"] != e["derived_alpha_match_method"]]
    assert len(changed) == 973 and all(e["original_fallback_reason"] == "provider_error" and e["derived_fallback_reason"] is None for e in changed)
    assert {e["derived_matched_alpha"] for e in mapping if e["derived_matched_alpha"]} == {"A304"}
    for name, record in lineage["artifacts"].items():
        assert record["content_equal_modulo_run_id"] is not False, name
    assert all(count == 0 for count in lineage["residual_original_run_id_fields"].values())


def test_claim_text_sources_and_verification_bindings_are_preserved_verbatim(derived):
    base_dir, new_dir = derived["out_root"] / ORIGINAL_ID, derived["out_root"] / derived["execution_id"]
    for name in ("structured_agent_outputs.json", "source_registry.json", "raw_agent_outputs.json", "extracted_structures.json"):
        original = json.loads((base_dir / name).read_text())
        copied = json.loads((new_dir / name).read_text())
        assert copied.pop("run_id") == derived["execution_id"] and original.pop("run_id") == ORIGINAL_ID
        for key in ("records", "agent_outputs", "canonical_relations"):
            for item in (original.get(key) or []) + (copied.get(key) or []):
                item.pop("run_id", None)
        assert copied == original, f"{name} differs beyond run_id fields"
    new_records = json.loads((new_dir / "structured_agent_outputs.json").read_text())["records"]
    assert [r["claim_id"] for r in new_records][:2] == [m["claim_id"] for m in derived["original_payload"]["matches"]][:2]
    assert all(r["run_id"] == derived["execution_id"] for r in new_records)
    assert {r["content_support_status"] for r in new_records}, "verification bindings are carried on the records"


def test_api_status_history_and_response_read_the_derived_run_consistently(derived, api):
    execution_id = derived["execution_id"]
    response = api(f"/api/research/{execution_id}").json()
    assert response["status"] == "completed" and response["run_id"] == execution_id
    assert response["lineage"] == {"based_on_run_id": ORIGINAL_ID, "execution_type": RECOVERY_EXECUTION_TYPE,
                                   "recovery_lineage_artifact": RECOVERY_LINEAGE_FILENAME}
    completion = response["alpha_classification_completion"]
    assert (completion["total_claims"], completion["complete"], completion["call_failure_count"]) == (975, True, 0)
    assert completion["valid_select_count"] == 3 and completion["valid_none_count"] == 972
    assert response["alpha_classification_status"] in {"complete_no_active", "complete_active_no_dominant", "complete_has_dominant"}
    assert response["structure_graph_status"] == "ready"

    status = api(f"/api/research/{execution_id}/status").json()
    assert status["status"] == "completed"
    history = api("/api/research?ticker=AMD&limit=50").json()
    rows = {row["run_id"]: row for row in history["items"]}
    assert execution_id in rows and rows[execution_id]["status"] == "completed"
    assert rows[execution_id]["ticker"] == "AMD"
    assert api(f"/api/research/{execution_id}/graph").json()["status"] == "ok"
    assert api(f"/api/research/{execution_id}/conflicts").json()["status"] == "ok"

    # Optional: freeze the two canonical responses for the frontend adapter test (a FAKE-HTTP derived run built
    # from the real frozen AMD inputs; never a real classification result).
    capture_dir = os.environ.get("COMQUTOR_CAPTURE_API_RESPONSES_DIR")
    if capture_dir:
        target = Path(capture_dir)
        target.mkdir(parents=True, exist_ok=True)
        notice = ("FAKE-HTTP derived run built from the frozen c904d4cc inputs by tests/test_classification_recovery_derived_run.py; "
                  "the classification decisions are test doubles, not a real recovery.")
        (target / "derived_run_api_response_fake_http.json").write_text(json.dumps(
            {"_notice": notice, "response": response}, indent=1, default=str))
        (target / "original_run_api_response_as_frozen.json").write_text(json.dumps(
            {"_notice": ("The ORIGINAL c904d4cc run read through the same route against a SCRATCH database that holds only its "
                         "agent-output rows (no graph/conflict rows), so its status and conflict_status are not the live run's. "
                         "Only the alpha_classification_* fields are meaningful here."),
             "response": api(f"/api/research/{ORIGINAL_ID}").json()}, indent=1, default=str))


def test_original_run_response_is_unchanged_and_still_discloses_its_own_failure(derived):
    from comqutor_alpha.api import routes_research

    after = routes_research.build_research_response(
        ORIGINAL_ID, output_root=str(derived["out_root"]), graph_repository=derived["repository"])
    assert after == derived["base_response_before"]
    assert "lineage" not in after
    assert after["alpha_classification_status"] == "incomplete"
    assert after["alpha_classification_completion"]["call_failure_count"] == 973


def test_agent_outputs_for_the_derived_run_equal_the_originals_apart_from_the_run_id(derived, api):
    execution_id = derived["execution_id"]
    original = api(f"/api/research/{ORIGINAL_ID}/agent-outputs").json()
    derived_body = api(f"/api/research/{execution_id}/agent-outputs").json()
    assert original["status"] == derived_body["status"] == "ok"
    assert original["count"] == derived_body["count"] > 0

    def without_run_id(rows):
        return [{k: v for k, v in row.items() if k != "run_id"} for row in rows]

    assert without_run_id(derived_body["structured_agent_outputs"]) == without_run_id(original["structured_agent_outputs"])
    assert {r["run_id"] for r in derived_body["structured_agent_outputs"]} == {execution_id}
    assert {r["run_id"] for r in original["structured_agent_outputs"]} == {ORIGINAL_ID}


def test_artifact_listing_download_and_export_zip_all_include_the_lineage_and_the_assembled_results(derived, api):
    execution_id = derived["execution_id"]
    listing = api(f"/api/research/{execution_id}/artifacts").json()
    assert listing["status"] == "ok" and listing["artifact_completeness"] == "pass" and listing["ticker_consistency"] == "pass"
    entries = {e["artifact_name"]: e for e in listing["artifacts"]}
    for name in (RECOVERY_LINEAGE_FILENAME, STANCE_FOLLOWUP_MANIFEST_FILENAME):
        assert entries[name]["exists"] and entries[name]["status"] == "valid", name

    download = api(f"/api/research/{execution_id}/artifacts/{RECOVERY_LINEAGE_FILENAME}")
    assert download.status_code == 200 and len(download.json()["claim_identity_map"]) == 975

    export = api(f"/api/research/{execution_id}/export")
    assert export.status_code == 200 and export.headers["content-type"] == "application/zip"
    archive = zipfile.ZipFile(io.BytesIO(export.content))
    names = set(archive.namelist())
    assert {RECOVERY_LINEAGE_FILENAME, STANCE_FOLLOWUP_MANIFEST_FILENAME, "alpha_matches.json", "conflicts.json",
            "alpha_activations.json", "evidence_facts.json", "summary.json", "artifact_manifest.json"} <= names
    matches = json.loads(archive.read("alpha_matches.json"))["matches"]
    assert len(matches) == 975 and {m["run_id"] for m in matches} == {execution_id}
    assert {m["alpha_match_method"] for m in matches} == {"llm"}, "no failed classification survives into the exported results"
    summary = json.loads(archive.read("summary.json"))
    assert summary["run_id"] == execution_id


def test_ordinary_runs_manifest_gains_no_recovery_entries(derived):
    """The present-only mechanism: the ORIGINAL run's manifest (an ordinary run) lists neither recovery artifact."""
    manifest = json.loads((derived["out_root"] / ORIGINAL_ID / "artifact_manifest.json").read_text())
    names = {e["artifact_name"] for e in manifest["artifacts"]}
    assert RECOVERY_LINEAGE_FILENAME not in names and STANCE_FOLLOWUP_MANIFEST_FILENAME not in names


def test_stance_manifest_of_the_derived_run_matches_the_recovered_matches_and_is_not_part_of_the_973(derived):
    manifest = derived["manifest"]
    on_disk = json.loads((derived["out_root"] / derived["execution_id"] / STANCE_FOLLOWUP_MANIFEST_FILENAME).read_text())
    assert on_disk == manifest
    assert manifest["matched_claims"] == 3 and manifest["pairs_needing_request"] >= 3
    assert manifest["pairs_reusable_from_base_run"] == 0, "the original run has no LLM direction results to reuse"
    assert manifest["counted_against_classification_cap"] is False and manifest["sent_by_this_manifest"] == 0


def test_finalize_refuses_bad_inputs_without_writing_anything(derived, recover):
    payload = json.loads(json.dumps(derived["payload"]))
    out_root = str(derived["out_root"])

    swapped = json.loads(json.dumps(payload))
    swapped["matches"][0], swapped["matches"][1] = swapped["matches"][1], swapped["matches"][0]
    assert finalize_classification_recovery_execution(
        ORIGINAL_ID, "recovery-refused-1", assembled_alpha_matches=swapped, output_root=out_root,
        graph_repository=derived["repository"])["error_code"] == "RECOVERY_IDENTITY_NOT_PRESERVED"

    edited = json.loads(json.dumps(payload))
    edited["matches"][5]["evidence"] = edited["matches"][5]["evidence"] + " (edited)"
    assert finalize_classification_recovery_execution(
        ORIGINAL_ID, "recovery-refused-2", assembled_alpha_matches=edited, output_root=out_root,
        graph_repository=derived["repository"])["error_code"] == "RECOVERY_IDENTITY_NOT_PRESERVED"

    assert finalize_classification_recovery_execution(
        ORIGINAL_ID, ORIGINAL_ID, assembled_alpha_matches=payload, output_root=out_root)["error_code"] == "RECOVERY_EXECUTION_ID_EQUALS_BASE"
    assert finalize_classification_recovery_execution(
        ORIGINAL_ID, derived["execution_id"], assembled_alpha_matches=payload, output_root=out_root,
        graph_repository=derived["repository"])["error_code"] == "RECOVERY_EXECUTION_ALREADY_FINALIZED"
    assert finalize_classification_recovery_execution(
        "no-such-run", "recovery-refused-3", assembled_alpha_matches=payload, output_root=out_root)["error_code"] == "BASE_RUN_NOT_FOUND"
    for name in ("recovery-refused-1", "recovery-refused-2", "recovery-refused-3"):
        assert not (derived["out_root"] / name).exists(), f"{name}: a refused finalize must not create a directory"


def test_a_fake_http_origin_is_refused_under_the_real_runs_directory(recover):
    real_runs = REPO_ROOT / "outputs" / "runs"
    with pytest.raises(RuntimeError, match="fake-HTTP"):
        from comqutor_alpha.classification_recovery import _refuse_fake_under_real_runs
        _refuse_fake_under_real_runs("fake_http_test", real_runs)
    from comqutor_alpha.classification_recovery import _refuse_fake_under_real_runs
    _refuse_fake_under_real_runs("real", real_runs)  # a real origin is allowed there

