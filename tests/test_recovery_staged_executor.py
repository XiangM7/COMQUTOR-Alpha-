"""2026-10-06 (round 14, sections 5 and 7): the staged recovery executor and
its stop rules, driven against the REAL frozen c904d4cc inputs with only the
bottom-most httpx transport faked (real build_server_week2_llm_gateway, real
create_llm_client, real map_structured_records, real audit logging).

This proves the plan/stop-rule LOGIC a future, separately-authorized real
recovery would run. It makes zero real Provider calls and proves nothing
about real classification quality. All artifacts go to pytest tmp_path --
never outputs/runs/, never a future real recovery directory.
"""

from __future__ import annotations

import importlib.util
import json
import threading
from collections import Counter
from pathlib import Path

import httpx
import pytest

import comqutor_alpha.structure_engine.week2_llm as week2_llm
from comqutor_alpha.llm_runtime.cache import InMemoryLLMResponseCache
from comqutor_alpha.llm_runtime.session import SemanticRuntimeSession
from comqutor_alpha.structure_engine import alpha_mapper
from comqutor_alpha.structure_engine.week2_llm import build_server_week2_llm_gateway

REPO_ROOT = Path(__file__).resolve().parents[1]
SCRIPT_PATH = (
    REPO_ROOT / "docs" / "audit_artifacts" / "round_source_linking_t0_t2"
    / "round12_alpha_classifier_audit_fix_20261006" / "recover_alpha_classification.py"
)
FROZEN_DIR = REPO_ROOT / "outputs" / "runs" / "c904d4cc-dc09-495c-aec5-b056979948e1"

pytestmark = pytest.mark.skipif(
    not (SCRIPT_PATH.exists() and (FROZEN_DIR / "structured_agent_outputs.json").exists()),
    reason="recovery script or frozen c904d4cc inputs not present",
)

RUN_ID = "recovery-staged-test"


def _load_script():
    spec = importlib.util.spec_from_file_location("recover_alpha_classification_under_test", SCRIPT_PATH)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


@pytest.fixture(scope="module")
def recover():
    return _load_script()


@pytest.fixture(scope="module")
def plan(recover):
    return recover.build_recovery_plan()


@pytest.fixture(scope="module")
def records_by_id():
    structured = json.loads((FROZEN_DIR / "structured_agent_outputs.json").read_text())
    return {r["claim_id"]: r for r in structured["records"]}


def _needle(text: str) -> str:
    return '"claim": "' + json.dumps(text, ensure_ascii=False)[1:-1] + '"'


def _ok(decision="none", alpha=None) -> httpx.Response:
    return httpx.Response(200, json={
        "id": "x", "object": "chat.completion", "created": 0, "model": "deepseek-v4-flash",
        "choices": [{"index": 0, "message": {"role": "assistant", "content": json.dumps(
            {"decision": decision, "selected_alpha_id": alpha})}, "finish_reason": "stop"}],
        "usage": {"prompt_tokens": 1, "completion_tokens": 1, "total_tokens": 2}})


def _gateway(tmp_path, monkeypatch, handler, *, max_calls=973):
    monkeypatch.setenv("COMQUTOR_WEEK2_LLM_ENABLED", "1")
    monkeypatch.setenv("COMQUTOR_WEEK2_LLM_PROVIDER", "deepseek")
    monkeypatch.setenv("COMQUTOR_WEEK2_LLM_MODEL", "deepseek-v4-flash")
    monkeypatch.setenv("COMQUTOR_WEEK2_LLM_MAX_RETRIES", "0")
    monkeypatch.setenv("COMQUTOR_WEEK2_LLM_MAX_CALLS", str(max_calls))
    monkeypatch.setenv("COMQUTOR_WEEK2_LLM_TIMEOUT_SECONDS", "45")  # explicit freeze, like the real launcher
    monkeypatch.setenv("DEEPSEEK_API_KEY", "fixed-test-key-not-real")
    gateway = build_server_week2_llm_gateway(
        RUN_ID, tmp_path, enable_request_response_audit=True,
        _base_transport_for_testing=httpx.MockTransport(handler),
    )
    assert gateway is not None
    (tmp_path / RUN_ID).mkdir(exist_ok=True)
    gateway.attach_semantic_runtime(SemanticRuntimeSession(
        run_id=RUN_ID, output_directory=str(tmp_path / RUN_ID), execution_mode="live",
        provider=gateway.provider, model=gateway.model_name, cache=InMemoryLLMResponseCache()))
    return gateway


def _audit(tmp_path, which):
    name = {"req": week2_llm.PROVIDER_REQUEST_AUDIT_ARTIFACT_PATH, "resp": week2_llm.PROVIDER_RESPONSE_AUDIT_ARTIFACT_PATH}[which]
    path = tmp_path / RUN_ID / name
    return [json.loads(line) for line in path.read_text().splitlines() if line.strip()] if path.exists() else []


def _run(recover, plan, records_by_id, gateway, tmp_path, **overrides):
    return recover.run_staged_recovery(
        plan, records_by_id, gateway=gateway, run_output_root=tmp_path, run_id=RUN_ID,
        checkpoint_path=tmp_path / "checkpoint.json",
        map_fn=alpha_mapper.map_structured_records,
        **{"checkpoint_origin": "fake_http_test", **overrides},
    )


def test_plan_shape_is_frozen(plan, recover):
    assert [(s["name"], len(s["claim_ids"])) for s in plan] == [
        ("stage_a_parallel_config_check", 4),
        ("stage_b_remaining_analytical_supports", 15),
        ("stage_c_remaining_claims", 954),
    ]
    nineteen = recover.load_nineteen_claim_ids()
    assert plan[0]["claim_ids"] == nineteen[:4]
    assert plan[1]["claim_ids"] == nineteen[4:]
    assert sum(len(s["claim_ids"]) for s in plan) == 973 == recover.HARD_REQUEST_CAP


def test_normal_run_follows_frozen_order_completes_and_every_request_is_identity_bound(
    recover, plan, records_by_id, tmp_path, monkeypatch
):
    sends = []
    lock = threading.Lock()

    def handler(request):
        with lock:
            sends.append(1)
        return _ok()

    gateway = _gateway(tmp_path, monkeypatch, handler)
    outcome = _run(recover, plan, records_by_id, gateway, tmp_path)

    assert outcome["stop_reason"] is None
    assert outcome["checkpoint_completed"] == 973
    assert outcome["gateway_call_count"] == len(sends) <= 973
    assert 955 <= len(sends) <= 973

    requests = _audit(tmp_path, "req")
    nineteen = recover.load_nineteen_claim_ids()
    # Frozen order: the first 4 audited requests are exactly the stage-A claims,
    # the first 19 are exactly the fixed analytical-SUPPORTS set.
    assert {tuple(r["claim_ids"]) for r in requests[:4]} == {(c,) for c in nineteen[:4]}
    assert {tuple(r["claim_ids"]) for r in requests[:19]} == {(c,) for c in nineteen}

    # 100% of real requests carry exactly one correct claim identity and a
    # semantic_call_id that resolves to a real semantic-call record agreeing on claim_ids.
    semantic = {r["call_id"]: r for r in
                (json.loads(l) for l in (tmp_path / RUN_ID / "llm_semantic_calls.jsonl").read_text().splitlines() if l.strip())}
    for request in requests:
        assert len(request["claim_ids"]) == 1
        assert semantic[request["semantic_call_id"]]["claim_ids"] == request["claim_ids"]
    # Cache-served claims explicitly cite a real source call.
    hits = [r for r in semantic.values() if r["cache"]["hit"]]
    assert len(hits) == 973 - len(sends)
    for hit in hits:
        assert hit["cache"]["source_call_id"] in semantic
        assert semantic[hit["cache"]["source_call_id"]]["cache"]["hit"] is False


def test_auth_failure_in_stage_a_stops_all_further_scheduling(recover, plan, records_by_id, tmp_path, monkeypatch):
    handler = lambda request: httpx.Response(401, json={"error": {"message": "bad key"}})  # noqa: E731
    gateway = _gateway(tmp_path, monkeypatch, handler)
    outcome = _run(recover, plan, records_by_id, gateway, tmp_path)

    assert outcome["stop_reason"] == "auth_failure"
    assert outcome["stop_detail"]["status_codes"] == [401]
    assert len(_audit(tmp_path, "req")) == 4
    assert outcome["gateway_call_count"] == 4
    assert outcome["audit_buckets_over_plan"]["failed"] == 4
    assert outcome["audit_buckets_over_plan"]["not_sent_or_cache_served"] == 969


def test_stage_a_gate_stops_on_a_single_non_auth_failure(recover, plan, records_by_id, tmp_path, monkeypatch):
    bad_claim = plan[0]["claim_ids"][2]
    bad_needle = _needle(records_by_id[bad_claim]["claim"])

    def handler(request):
        prompt = json.loads(request.content)["messages"][0]["content"]
        return httpx.Response(500, json={"error": "boom"}) if bad_needle in prompt else _ok()

    gateway = _gateway(tmp_path, monkeypatch, handler)
    outcome = _run(recover, plan, records_by_id, gateway, tmp_path)

    assert outcome["stop_reason"] == "stage_a_gate_failed"
    assert outcome["stop_detail"]["not_protocol_complete"] == {bad_claim: "failed"}
    assert len(_audit(tmp_path, "req")) == 4  # nothing beyond the gate was scheduled


def test_later_stage_single_failure_is_saved_never_retried_and_run_continues(
    recover, plan, records_by_id, tmp_path, monkeypatch
):
    text_counts = Counter(str(r.get("claim") or "") for r in records_by_id.values())
    bad_claim = next(c for c in plan[2]["claim_ids"][100:] if text_counts[str(records_by_id[c]["claim"])] == 1)
    bad_needle = _needle(records_by_id[bad_claim]["claim"])
    bad_sends = []

    def handler(request):
        prompt = json.loads(request.content)["messages"][0]["content"]
        if bad_needle in prompt:
            bad_sends.append(1)
            return httpx.Response(500, json={"error": "boom"})
        return _ok()

    gateway = _gateway(tmp_path, monkeypatch, handler)
    outcome = _run(recover, plan, records_by_id, gateway, tmp_path)

    assert outcome["stop_reason"] is None, "a single later-stage failure must not stop the run"
    assert len(bad_sends) == 1, "a failed claim must never be automatically retried"
    entry = json.loads((tmp_path / "checkpoint.json").read_text())["completed_claim_ids"][bad_claim]
    assert entry["alpha_match_method"] == "llm_unavailable" and entry["fallback_reason"] == "provider_error"
    assert outcome["audit_buckets_over_plan"]["failed"] == 1

    merged = {"matches": [
        {"claim_id": cid, "alpha_match_method": v["alpha_match_method"],
         "alpha_match_fallback_reason": v["fallback_reason"], "matched_alpha": v["matched_alpha"]}
        for cid, v in json.loads((tmp_path / "checkpoint.json").read_text())["completed_claim_ids"].items()
    ]}
    completion = alpha_mapper.compute_alpha_classification_completion(merged)
    assert completion["call_failure_count"] == 1 and completion["complete"] is False
    assert completion["valid_none_count"] == 972


def test_local_audit_failure_stops_new_batches_and_refused_claims_are_not_success(
    recover, plan, records_by_id, tmp_path, monkeypatch
):
    real_append = week2_llm.append_jsonl_record
    response_writes = {"n": 0}

    def flaky_append(run_id, artifact_path, record, *, output_root=None):
        if artifact_path == week2_llm.PROVIDER_RESPONSE_AUDIT_ARTIFACT_PATH:
            response_writes["n"] += 1
            if response_writes["n"] == 30:
                raise OSError("simulated disk failure on the 30th response-audit write")
        return real_append(run_id, artifact_path, record, output_root=output_root)

    monkeypatch.setattr(week2_llm, "append_jsonl_record", flaky_append)
    gateway = _gateway(tmp_path, monkeypatch, lambda request: _ok())
    outcome = _run(recover, plan, records_by_id, gateway, tmp_path)

    assert outcome["stop_reason"] == "local_audit_failure"
    assert gateway.audit_write_failed is True
    # stage A (4) + stage B (15) + exactly ONE stage-C batch (<=25) were ever scheduled.
    assert len(outcome["submitted_claim_ids"]) <= 4 + 15 + 25
    assert len(_audit(tmp_path, "req")) <= 4 + 15 + 25
    assert outcome["batches_run"] <= 3

    checkpoint = json.loads((tmp_path / "checkpoint.json").read_text())["completed_claim_ids"]
    refused = [v for v in checkpoint.values() if v["fallback_reason"] == "audit_unavailable"]
    assert refused, "claims refused after the audit failure must be recorded as audit_unavailable"
    assert all(v["alpha_match_method"] == "llm_unavailable" for v in refused)
    completion = alpha_mapper.compute_alpha_classification_completion({"matches": [
        {"claim_id": cid, "alpha_match_method": v["alpha_match_method"],
         "alpha_match_fallback_reason": v["fallback_reason"], "matched_alpha": v["matched_alpha"]}
        for cid, v in checkpoint.items()]})
    assert completion["not_executed_count"] == len(refused)
    assert completion["complete"] is False


def test_call_cap_stops_before_it_would_be_exceeded(recover, plan, records_by_id, tmp_path, monkeypatch):
    gateway = _gateway(tmp_path, monkeypatch, lambda request: _ok(), max_calls=30)
    outcome = _run(recover, plan, records_by_id, gateway, tmp_path, hard_cap=30)

    assert outcome["stop_reason"] == "call_cap_would_be_exceeded"
    assert outcome["stop_detail"] == {"call_count": 19, "prior_sent_by_earlier_processes": 0, "next_batch": 25, "hard_cap": 30}
    assert len(_audit(tmp_path, "req")) == 19
    assert gateway.call_count == 19 <= 30


def test_unknown_inflight_and_prior_failed_claims_are_never_resent(recover, plan, records_by_id, tmp_path, monkeypatch):
    stage_a = plan[0]["claim_ids"]
    unknown_claim, failed_claim = stage_a[0], stage_a[1]
    audit_dir = tmp_path / RUN_ID / "error_logs"
    audit_dir.mkdir(parents=True)
    (audit_dir / "week2_llm_provider_request_audit.jsonl").write_text(
        json.dumps({"attempt_id": "prior:1", "claim_ids": [unknown_claim]}) + "\n"
        + json.dumps({"attempt_id": "prior:2", "claim_ids": [failed_claim]}) + "\n")
    (audit_dir / "week2_llm_provider_response_audit.jsonl").write_text(
        json.dumps({"attempt_id": "prior:2", "status_code": 500, "body": "{}"}) + "\n")

    sent_needles = []

    def handler(request):
        prompt = json.loads(request.content)["messages"][0]["content"]
        for cid in (unknown_claim, failed_claim):
            if _needle(records_by_id[cid]["claim"]) in prompt:
                sent_needles.append(cid)
        return _ok()

    gateway = _gateway(tmp_path, monkeypatch, handler)
    outcome = _run(recover, plan, records_by_id, gateway, tmp_path)

    assert sent_needles == [], "unknown_inflight / previously failed claims must never be automatically re-sent"
    assert outcome["stop_reason"] == "stage_a_gate_failed"
    assert outcome["stop_detail"]["not_protocol_complete"] == {
        unknown_claim: "unknown_inflight", failed_claim: "failed",
    }
    assert outcome["gateway_call_count"] == 2  # only the other two stage-A claims were sent


# ---------------------------------------------------------------------------
# Fake-HTTP artifacts can never become real results (round 14, section 5)
# ---------------------------------------------------------------------------


def test_fake_run_marks_its_directory_and_stamps_the_checkpoint(recover, plan, records_by_id, tmp_path, monkeypatch):
    gateway = _gateway(tmp_path, monkeypatch, lambda request: _ok(), max_calls=30)
    _run(recover, plan, records_by_id, gateway, tmp_path, hard_cap=30)
    assert (tmp_path / recover.FAKE_HTTP_MARKER_FILENAME).exists()
    assert json.loads((tmp_path / "checkpoint.json").read_text())["origin"] == "fake_http_test"


def test_a_fake_origin_checkpoint_cannot_be_resumed_as_real(recover, plan, records_by_id, tmp_path, monkeypatch):
    gateway = _gateway(tmp_path, monkeypatch, lambda request: _ok(), max_calls=30)
    _run(recover, plan, records_by_id, gateway, tmp_path, hard_cap=30)
    sends_before = len(_audit(tmp_path, "req"))
    with pytest.raises(RuntimeError, match="fake"):
        _run(recover, plan, records_by_id, gateway, tmp_path, checkpoint_origin="real")
    assert len(_audit(tmp_path, "req")) == sends_before, "a refused resume must send nothing"


def test_a_real_origin_run_refuses_any_directory_holding_fake_artifacts(recover, plan, records_by_id, tmp_path, monkeypatch):
    (tmp_path / recover.FAKE_HTTP_MARKER_FILENAME).write_text("fake")
    gateway = _gateway(tmp_path, monkeypatch, lambda request: _ok())
    with pytest.raises(RuntimeError, match="fake-HTTP"):
        _run(recover, plan, records_by_id, gateway, tmp_path, checkpoint_origin="real")
    assert _audit(tmp_path, "req") == []


def test_a_real_origin_run_refuses_a_fake_checkpoint_in_its_checkpoint_directory(recover, plan, records_by_id, tmp_path, monkeypatch):
    run_root = tmp_path / "runs"
    run_root.mkdir()
    ckpt_dir = tmp_path / "ckpt"
    ckpt_dir.mkdir()
    (ckpt_dir / "checkpoint.json").write_text(json.dumps({"origin": "fake_http_test", "completed_claim_ids": {}}))
    gateway = _gateway(run_root, monkeypatch, lambda request: _ok())
    with pytest.raises(RuntimeError, match="fake-HTTP checkpoint"):
        recover.run_staged_recovery(
            plan, records_by_id, gateway=gateway, run_output_root=run_root, run_id=RUN_ID,
            checkpoint_path=ckpt_dir / "checkpoint.json", map_fn=alpha_mapper.map_structured_records,
            checkpoint_origin="real",
        )


def test_a_fake_run_refuses_to_write_under_the_real_runs_directory(recover):
    real_runs = recover.OUTPUT_ROOT
    with pytest.raises(RuntimeError, match="real runs directory"):
        recover.mark_fake_http_directory(real_runs / "some-recovery-run")
    assert not (real_runs / "some-recovery-run").exists()


def test_checkpoint_origin_is_required_and_validated(recover, plan, records_by_id, tmp_path, monkeypatch):
    gateway = _gateway(tmp_path, monkeypatch, lambda request: _ok())
    with pytest.raises(TypeError):
        recover.run_staged_recovery(
            plan, records_by_id, gateway=gateway, run_output_root=tmp_path, run_id=RUN_ID,
            checkpoint_path=tmp_path / "checkpoint.json", map_fn=alpha_mapper.map_structured_records,
        )
    with pytest.raises(ValueError, match="unknown checkpoint_origin"):
        _run(recover, plan, records_by_id, gateway, tmp_path, checkpoint_origin="whatever")


# ---------------------------------------------------------------------------
# Preflight: refuse to start on a mis-configured Gateway (round 14, section 7)
# ---------------------------------------------------------------------------


def test_preflight_refuses_nonzero_application_retries_the_repo_dotenv_default(
    recover, plan, records_by_id, tmp_path, monkeypatch
):
    sends = []
    gateway = _gateway(tmp_path, monkeypatch, lambda request: sends.append(1) or _ok())
    gateway.max_retries = 1  # what a launcher that forgot to export 0 would get from the repo's .env
    with pytest.raises(RuntimeError, match=r"max_retries=1 \(must be 0\)"):
        _run(recover, plan, records_by_id, gateway, tmp_path)
    assert sends == []


def test_preflight_refuses_a_gateway_cap_above_the_independent_cap_or_audit_off_or_wrong_concurrency(
    recover, plan, records_by_id, tmp_path, monkeypatch
):
    gateway = _gateway(tmp_path, monkeypatch, lambda request: _ok(), max_calls=1500)
    with pytest.raises(RuntimeError, match="exceeds the independent cap 973"):
        _run(recover, plan, records_by_id, gateway, tmp_path)

    gateway = _gateway(tmp_path, monkeypatch, lambda request: _ok())
    gateway._audit_enabled = False
    with pytest.raises(RuntimeError, match="audit is not enabled"):
        _run(recover, plan, records_by_id, gateway, tmp_path)

    gateway = _gateway(tmp_path, monkeypatch, lambda request: _ok())
    with pytest.raises(RuntimeError, match=r"concurrency=8 \(frozen value is 4\)"):
        _run(recover, plan, records_by_id, gateway, tmp_path, concurrency=8)
    assert _audit(tmp_path, "req") == []


def test_effective_config_is_reported_in_the_run_outcome(recover, plan, records_by_id, tmp_path, monkeypatch):
    gateway = _gateway(tmp_path, monkeypatch, lambda request: _ok(), max_calls=30)
    outcome = _run(recover, plan, records_by_id, gateway, tmp_path, hard_cap=30)
    cfg = outcome["effective_config"]
    assert (cfg["application_max_retries"], cfg["gateway_max_calls"], cfg["hard_request_cap"], cfg["concurrency"]) == (0, 30, 30, 4)
    assert cfg["audit_enabled"] is True and cfg["model"] == "deepseek-v4-flash"


def test_stance_followup_budget_is_computed_without_any_model_call(recover, records_by_id, tmp_path, monkeypatch):
    """Classify a handful of real frozen claims with a fake transport that
    selects an Alpha, then size the follow-up stance task from those results
    with the production request builder. Zero extra sends."""
    sends = []

    def handler(request):
        sends.append(1)
        return _ok("select", "A304")

    gateway = _gateway(tmp_path, monkeypatch, handler)
    some = list(records_by_id.values())[:12]
    results = alpha_mapper.map_structured_records(some, classifier_enabled=True, llm_gateway=gateway, concurrency=4)
    sends_after_classification = len(sends)

    budget = recover.stance_followup_budget(results)
    assert len(sends) == sends_after_classification, "sizing the stance task must not send anything"
    assert budget["matched_claims"] == sum(1 for r in results if r.get("matched_alpha"))
    assert budget["stance_items"] >= budget["matched_claims"]  # >= 1 target Alpha per matched claim
    assert budget["max_requests_with_zero_retries"] == -(-budget["stance_items"] // budget["items_per_call"])

    none_results = [{**r, "matched_alpha": None} for r in results]
    assert recover.stance_followup_budget(none_results)["max_requests_with_zero_retries"] == 0


# ---------------------------------------------------------------------------
# Assembly of the full 975-claim alpha-matches payload (round 14, section 5)
# ---------------------------------------------------------------------------

import socket  # noqa: E402
import shutil  # noqa: E402


@pytest.fixture(scope="module")
def original_alpha_payload():
    return json.loads((FROZEN_DIR / "alpha_matches.json").read_text())


@pytest.fixture(scope="module")
def scope(recover):
    return recover.compute_recovery_scope()


def _decision_handler_by_claim_text(records_by_id, plan_ids, select_for=()):
    """Fake transport: 'select A304' for the claims whose text is in `select_for`,
    valid NONE for everything else. Keyed on claim text (the only thing in the prompt)."""
    selectors = {_needle(records_by_id[c]["claim"]) for c in select_for}

    def handler(request):
        prompt = json.loads(request.content)["messages"][0]["content"]
        return _ok("select", "A304") if any(n in prompt for n in selectors) else _ok()

    return handler


def test_rematerialized_record_is_field_for_field_what_the_gateway_path_produces(recover, records_by_id, tmp_path, monkeypatch):
    """Offline re-materialization (zero model calls) must reproduce exactly the
    record the real gateway path builds for the same audited decision."""
    some = list(records_by_id.values())[:10]
    selected = {some[i]["claim_id"] for i in (1, 4, 7)}
    selectors = {_needle(r["claim"]) for r in some if r["claim_id"] in selected}

    def handler(request):
        prompt = json.loads(request.content)["messages"][0]["content"]
        return _ok("select", "A304") if any(n in prompt for n in selectors) else _ok()

    gateway = _gateway(tmp_path, monkeypatch, handler)
    via_gateway = {r["claim_id"]: r for r in alpha_mapper.map_structured_records(some, classifier_enabled=True, llm_gateway=gateway, concurrency=1)}
    for record in some:
        decision = {"decision": "select", "selected_alpha_id": "A304"} if record["claim_id"] in selected else {"decision": "none", "selected_alpha_id": None}
        rebuilt = recover.rematerialize_match_record(record, decision)
        assert rebuilt == via_gateway[record["claim_id"]], f"re-materialized record differs for {record['claim_id']}"
    assert any(r["matched_alpha"] for r in via_gateway.values()), "the test must include at least one real selection"


@pytest.fixture(scope="module")
def full_fake_recovery(recover, plan, records_by_id, tmp_path_factory):
    """One full 973-claim fake-transport staged recovery, shared by the assembly tests."""
    tmp = tmp_path_factory.mktemp("full_staged")
    mp = pytest.MonkeyPatch()
    try:
        sample_selected = [plan[2]["claim_ids"][i] for i in (10, 200, 500)]
        gateway = _gateway(tmp, mp, _decision_handler_by_claim_text(records_by_id, None, select_for=sample_selected))
        outcome = _run(recover, plan, records_by_id, gateway, tmp)
    finally:
        mp.undo()
    return {"tmp": tmp, "outcome": outcome, "selected": sample_selected}


def test_assembly_of_a_full_recovery_preserves_all_975_identities_and_reuses_the_two_valid_results(
    recover, scope, records_by_id, original_alpha_payload, full_fake_recovery
):
    tmp = full_fake_recovery["tmp"]
    assert full_fake_recovery["outcome"]["stop_reason"] is None
    audit_states = recover.reconcile_claim_states_from_audit_log(tmp, RUN_ID)
    audit_states.pop("__multi_attempt_warnings__", None)
    payload, report = recover.assemble_recovered_alpha_matches(
        original_alpha_payload, scope, records_by_id=records_by_id,
        full_match_records=recover.load_match_records(Path(full_fake_recovery["outcome"]["records_path"])),
        audit_states=audit_states,
    )
    original_ids = [m["claim_id"] for m in original_alpha_payload["matches"]]
    assert [m["claim_id"] for m in payload["matches"]] == original_ids and len(original_ids) == 975
    assert report["sources"] == {"reused": 2, "recovered": 973, "rematerialized": 0, "kept_original": 0}
    originals = {m["claim_id"]: m for m in original_alpha_payload["matches"]}
    for cid in scope["valid_llm_results_claim_ids"]:
        assert next(m for m in payload["matches"] if m["claim_id"] == cid) == originals[cid], "reused results must be verbatim"
    completion = alpha_mapper.compute_alpha_classification_completion(payload)
    assert completion["complete"] is True and completion["call_failure_count"] == 0 and completion["not_executed_count"] == 0
    assert completion["valid_select_count"] >= 3 and completion["total_claims"] == 975


def test_assembly_after_an_early_stop_keeps_failures_visible_and_never_invents_a_result(
    recover, plan, scope, records_by_id, original_alpha_payload, tmp_path, monkeypatch
):
    gateway = _gateway(tmp_path, monkeypatch, lambda request: _ok(), max_calls=30)
    outcome = _run(recover, plan, records_by_id, gateway, tmp_path, hard_cap=30)  # stops after 19 sends
    assert outcome["stop_reason"] == "call_cap_would_be_exceeded"
    audit_states = recover.reconcile_claim_states_from_audit_log(tmp_path, RUN_ID)
    audit_states.pop("__multi_attempt_warnings__", None)
    payload, report = recover.assemble_recovered_alpha_matches(
        original_alpha_payload, scope, records_by_id=records_by_id,
        full_match_records=recover.load_match_records(Path(outcome["records_path"])), audit_states=audit_states,
    )
    assert report["total"] == 975 and report["identity_preserved"]
    assert report["sources"]["recovered"] == 19 and report["sources"]["kept_original"] == 973 - 19
    completion = alpha_mapper.compute_alpha_classification_completion(payload)
    assert completion["complete"] is False
    assert completion["valid_none_count"] == 2 + 19, "only the 2 reused + the 19 actually answered may count as completed"
    assert completion["call_failure_count"] == 973 - 19, "every unanswered claim must still read as a failure, never as NONE"


def test_a_response_audited_but_never_checkpointed_is_rebuilt_from_the_audited_decision_and_an_unknown_stays_unknown(
    recover, plan, scope, records_by_id, original_alpha_payload, tmp_path, monkeypatch
):
    """The mid-batch crash: all 4 stage-A responses are audited, but the batch's records/
    checkpoint never reached disk. One more claim is left 'sent, no response saved'."""
    gateway = _gateway(tmp_path, monkeypatch, lambda request: _ok("select", "A304"), max_calls=4)
    outcome = _run(recover, plan, records_by_id, gateway, tmp_path, hard_cap=4)
    live_records = recover.load_match_records(Path(outcome["records_path"]))
    assert len(live_records) == 4
    # Simulate the crash: the persisted records/checkpoint are gone, only the audit log survives.
    Path(outcome["records_path"]).unlink(missing_ok=True)
    unknown_claim = plan[1]["claim_ids"][0]
    req_path = tmp_path / RUN_ID / week2_llm.PROVIDER_REQUEST_AUDIT_ARTIFACT_PATH
    with open(req_path, "a") as fh:
        fh.write(json.dumps({"attempt_id": "crash:1", "claim_ids": [unknown_claim]}) + "\n")
    audit_states = recover.reconcile_claim_states_from_audit_log(tmp_path, RUN_ID)
    audit_states.pop("__multi_attempt_warnings__", None)
    payload, report = recover.assemble_recovered_alpha_matches(
        original_alpha_payload, scope, records_by_id=records_by_id, full_match_records={}, audit_states=audit_states)
    assert report["sources"]["rematerialized"] == 4 and report["sources"]["recovered"] == 0
    by_id = {m["claim_id"]: m for m in payload["matches"]}
    for cid, live in live_records.items():
        assert by_id[cid] == live, "a claim rebuilt from the audit log must equal the record that was lost"
    assert by_id[unknown_claim]["alpha_match_fallback_reason"] == "provider_error", "an unknown must stay a failure, not become NONE"
    assert report["kept_original_by_audit_state"].get("unknown_inflight") == 1


def test_downstream_recompute_on_the_assembled_payload_makes_zero_model_calls(
    recover, scope, records_by_id, original_alpha_payload, full_fake_recovery, tmp_path, monkeypatch
):
    """Evidence Fact / Activation / Exposure / Conflict are rebuilt by the existing production
    pipeline from the assembled payload with every model/network seam trapped."""
    import httpx
    from comqutor_alpha.api import routes_research
    from comqutor_alpha.storage.db.engine import build_engine
    from comqutor_alpha.storage.db.migrations import apply_migrations
    from comqutor_alpha.storage.db.repository import GraphPersistenceRepository
    from comqutor_alpha.structure_engine.week2_llm import Week2LLMGateway

    audit_states = recover.reconcile_claim_states_from_audit_log(full_fake_recovery["tmp"], RUN_ID)
    audit_states.pop("__multi_attempt_warnings__", None)
    payload, _ = recover.assemble_recovered_alpha_matches(
        original_alpha_payload, scope, records_by_id=records_by_id,
        full_match_records=recover.load_match_records(Path(full_fake_recovery["outcome"]["records_path"])),
        audit_states=audit_states)

    run_dir = tmp_path / "c904d4cc-dc09-495c-aec5-b056979948e1"
    run_dir.mkdir()
    for name in ("extracted_structures.json", "structured_agent_outputs.json", "source_registry.json", "metadata.json"):
        shutil.copy2(FROZEN_DIR / name, run_dir / name)
    (run_dir / "alpha_matches.json").write_text(json.dumps(payload))

    hits = []
    def trap(name):
        def _raise(*a, **k):
            hits.append(name); raise AssertionError(name)
        return _raise
    monkeypatch.setattr(httpx.HTTPTransport, "handle_request", trap("httpx"))
    monkeypatch.setattr(socket.socket, "connect", trap("socket"))
    for method in ("invoke_json", "invoke_json_with_trace", "invoke_prebuilt_json_prompt"):
        monkeypatch.setattr(Week2LLMGateway, method, trap(method))

    engine = build_engine("sqlite:///:memory:"); apply_migrations(engine)
    repo = GraphPersistenceRepository(engine)
    routes_research._run_week3_graph_pipeline(run_dir, graph_repository=repo)
    assert hits == []
    assert json.loads((run_dir / "week3_pipeline_status.json").read_text()).get("outcome") == "success"
    response = routes_research.build_research_response(run_dir.name, output_root=str(tmp_path), graph_repository=repo)
    assert response["alpha_classification_status"] in {"complete_no_active", "complete_active_no_dominant", "complete_has_dominant"}
    assert response["alpha_classification_completion"]["total_claims"] == 975
