"""2026-10-07 (round 17): direction (evidence_stance_classifier) evaluation of the recovered AMD classification.

Real saved inputs (the recovery run's 162 matched claims, read-only) with ONLY the bottom-most httpx transport faked.
Proves the executor's behavior -- plan, per-pair results, the first-batch protocol check, failure handling, cap and
resume accounting, unknown batches, task isolation -- and the derived evaluation run saved through the verified
derived-run path. Zero real Provider calls; scratch directories only.
"""

from __future__ import annotations

import importlib.util
import itertools
import json
import shutil
import threading
from pathlib import Path

import httpx
import pytest

from comqutor_alpha.alpha_library.alpha_loader import load_alpha_taxonomy
from comqutor_alpha.classification_recovery import (
    DIRECTION_LINEAGE_FILENAME,
    DIRECTION_RESULTS_FILENAME,
    STANCE_TASK,
    TaskAllowlistGateway,
    snapshot_directory_hashes,
)
from comqutor_alpha.direction_evaluation import (
    audit_paths,
    build_direction_plan,
    collect_direction_results,
    load_checkpoint,
    preflight_direction_gateway,
    read_jsonl,
    request_wire_problem,
    run_direction_batches,
)
from comqutor_alpha.llm_runtime.cache import InMemoryLLMResponseCache
from comqutor_alpha.llm_runtime.session import SemanticRuntimeSession
from comqutor_alpha.structure_engine import evidence_stance_llm as esl
from comqutor_alpha.structure_engine.week2_llm import build_server_week2_llm_gateway

REPO_ROOT = Path(__file__).resolve().parents[1]
ROOT_ID = "c904d4cc-dc09-495c-aec5-b056979948e1"
PARENT_ID = "recovery-20261007T053635Z-26d6cd1a"
PARENT_DIR = REPO_ROOT / "outputs" / "runs" / PARENT_ID
ROOT_DIR = REPO_ROOT / "outputs" / "runs" / ROOT_ID
DRIVER = (REPO_ROOT / "docs" / "audit_artifacts" / "round_source_linking_t0_t2" / "round17_direction_evaluation_20261007"
          / "run_direction_evaluation.py")

pytestmark = pytest.mark.skipif(
    not ((PARENT_DIR / "alpha_matches.json").exists() and (ROOT_DIR / "structured_agent_outputs.json").exists() and DRIVER.exists()),
    reason="the saved recovery run / original run / driver are not present",
)

STANCES = ("supports_alpha", "opposes_alpha", "mentions_alpha", "neutral_background")
MODEL = "deepseek-v4-flash"


@pytest.fixture(scope="module")
def taxonomy():
    return load_alpha_taxonomy()


@pytest.fixture(scope="module")
def parent_payload():
    return json.loads((PARENT_DIR / "alpha_matches.json").read_text())


@pytest.fixture
def plan(parent_payload, taxonomy):
    return build_direction_plan(parent_payload, taxonomy)


@pytest.fixture(scope="module")
def driver():
    spec = importlib.util.spec_from_file_location("direction_driver_under_test", DRIVER)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def _chat(items):
    return httpx.Response(200, json={
        "id": "x", "object": "chat.completion", "created": 0, "model": MODEL,
        "choices": [{"index": 0, "message": {"role": "assistant", "content": json.dumps({"items": items})}, "finish_reason": "stop"}],
        "usage": {"prompt_tokens": 7, "completion_tokens": 3, "total_tokens": 10}})


def _request_items(request):
    prompt = json.loads(request.content)["messages"][0]["content"]
    return json.JSONDecoder().raw_decode(prompt[prompt.rfind('{"items"'):])[0]["items"]


def _valid_handler(sends, *, fail_when=None, mutate=None):
    """Valid answers for every requested item (stance cycles through four values); `fail_when(items)` -> an HTTP
    500 for that batch; `mutate(answer_items)` may corrupt the answer."""
    counter = itertools.count()
    lock = threading.Lock()

    def handler(request):
        items = _request_items(request)
        with lock:
            sends.append([i["claim_id"] for i in items])
            offset = next(counter)
        if fail_when and fail_when(items):
            return httpx.Response(500, json={"error": {"message": "boom"}})
        answer = [{"claim_id": i["claim_id"], "target_alpha_id": i["target_alpha_id"], "stance": STANCES[(offset + n) % 4]} for n, i in enumerate(items)]
        if mutate:
            mutate(answer)
        return _chat(answer)

    return handler


def _gateway(root, monkeypatch, handler, run_id, *, max_calls=17):
    monkeypatch.setenv("COMQUTOR_WEEK2_LLM_ENABLED", "1")
    monkeypatch.setenv("COMQUTOR_WEEK2_LLM_PROVIDER", "deepseek")
    monkeypatch.setenv("COMQUTOR_WEEK2_LLM_MODEL", MODEL)
    monkeypatch.setenv("COMQUTOR_WEEK2_LLM_MAX_RETRIES", "0")
    monkeypatch.setenv("COMQUTOR_WEEK2_LLM_MAX_CALLS", str(max_calls))
    monkeypatch.setenv("COMQUTOR_WEEK2_LLM_TIMEOUT_SECONDS", "45")
    monkeypatch.setenv("COMQUTOR_WEEK2_STANCE_CONCURRENCY", "4")
    monkeypatch.setenv("DEEPSEEK_API_KEY", "fixed-test-key-not-real")
    root.mkdir(parents=True, exist_ok=True)
    gateway = build_server_week2_llm_gateway(run_id, root, enable_request_response_audit=True, _base_transport_for_testing=httpx.MockTransport(handler))
    (root / run_id).mkdir(exist_ok=True)
    gateway.attach_semantic_runtime(SemanticRuntimeSession(
        run_id=run_id, output_directory=str(root / run_id), execution_mode="live",
        provider=gateway.provider, model=gateway.model_name, cache=InMemoryLLMResponseCache()))
    return gateway


def _run(plan, taxonomy, gateway, root, run_id, *, hard_cap=17):
    return run_direction_batches(
        plan, taxonomy, gateway=gateway, run_output_root=root, execution_id=run_id,
        checkpoint_path=root / run_id / "checkpoint_direction.json", hard_cap=hard_cap, concurrency=4,
        expected_model=MODEL, expected_timeout=45.0)


def test_plan_reproduces_the_saved_manifest_with_the_production_batching(plan):
    manifest = json.loads((PARENT_DIR / "evidence_stance_followup_manifest.json").read_text())
    assert len(plan.items) == manifest["pairs_needing_request"] == 162
    assert [len(b) for b in plan.batches] == [10] * 16 + [2]
    assert len(plan.batches) == manifest["independent_request_budget"] == 17
    assert [(i.claim_id, i.target_alpha_id) for i in plan.items] == [(i["claim_id"], i["target_alpha_id"]) for i in manifest["items"]]


def test_all_batches_valid_every_request_is_a_direction_request_and_every_pair_is_saved(plan, taxonomy, tmp_path, monkeypatch):
    sends = []
    gateway = _gateway(tmp_path, monkeypatch, _valid_handler(sends), "direction-t1")
    effective = preflight_direction_gateway(gateway, hard_cap=17, prior_sent=0, concurrency=4, expected_model=MODEL, expected_timeout=45.0)
    outcome = _run(plan, taxonomy, gateway, tmp_path, "direction-t1")
    gateway.semantic_runtime.finalize_manifest(complete=True)

    assert outcome["stop_reason"] is None and outcome["requests_audited_total"] == len(sends) == 17
    assert outcome["request_tasks_observed"] == {STANCE_TASK: 17} and outcome["batch_states"] == {"valid_response": 17}
    req_path, _ = audit_paths(tmp_path, "direction-t1")
    assert all(request_wire_problem(r, expected_model=MODEL, expected_timeout=45.0) is None for r in read_jsonl(req_path))
    results = collect_direction_results(plan, run_output_root=tmp_path, execution_id="direction-t1", base_run_id=PARENT_ID, root_run_id=ROOT_ID,
                                        checkpoint=load_checkpoint(tmp_path / "direction-t1" / "checkpoint_direction.json"), effective_config=effective)
    completion = results["completion"]
    assert completion["pairs_total"] == completion["llm_results"] == 162 and completion["complete"] is True
    assert sum(completion["llm_stance_distribution"].values()) == 162 and set(completion["llm_stance_distribution"]) <= set(STANCES)
    for pair in results["pairs"]:
        assert pair["is_llm_result"] and pair["method"] == "llm" and pair["semantic_call_id"] and pair["attempt_id"]
        assert pair["model_answer"]["claim_id"] == pair["claim_id"] and pair["model_answer"]["target_alpha_id"] == pair["target_alpha_id"]
        assert pair["confidence"] is None and "does not ask the model for a confidence" in pair["confidence_note"]
    for batch in results["batches"]:
        assert batch["http_status"] == 200 and batch["finish_reason"] == "stop" and batch["usage"]["total_tokens"] == 10
        assert batch["prompt_version"] == "evidence_stance.llm_classifier.v3" and batch["request_control"]["max_tokens_value"] is None
    candidates = [i.candidate for i in plan.items]
    assert all(c["stance_method"] == "llm" and c["stance_confidence_band"] is None and c["stance_fallback_reason"] is None for c in candidates)


def test_a_failed_first_batch_stops_everything_after_one_request(plan, taxonomy, tmp_path, monkeypatch):
    sends = []
    gateway = _gateway(tmp_path, monkeypatch, _valid_handler(sends, fail_when=lambda items: True), "direction-t2")
    outcome = _run(plan, taxonomy, gateway, tmp_path, "direction-t2")

    assert outcome["stop_reason"] == "first_batch_gate_failed" and len(sends) == 1 and outcome["requests_audited_total"] == 1
    assert outcome["batch_states"] == {"failed": 1} and outcome["batches_never_scheduled"] == 16
    assert {i.candidate["stance_fallback_reason"] for i in plan.batches[0]} == {"provider_error"}
    assert all(i.candidate.get("stance_method") != "llm" for i in plan.items)
    results = collect_direction_results(plan, run_output_root=tmp_path, execution_id="direction-t2", base_run_id=PARENT_ID, root_run_id=ROOT_ID,
                                        checkpoint=load_checkpoint(tmp_path / "direction-t2" / "checkpoint_direction.json"), effective_config={})
    assert results["completion"]["llm_results"] == 0 and results["completion"]["complete"] is False
    assert results["completion"]["never_scheduled_or_unknown"] == 152 and results["completion"]["fallback_by_reason"] == {"provider_error": 10}


def test_a_malformed_first_response_also_fails_the_gate(plan, taxonomy, tmp_path, monkeypatch):
    def handler(request):
        return httpx.Response(200, json={"id": "x", "object": "chat.completion", "created": 0, "model": MODEL,
            "choices": [{"index": 0, "message": {"role": "assistant", "content": "not json at all"}, "finish_reason": "stop"}],
            "usage": {"prompt_tokens": 1, "completion_tokens": 1, "total_tokens": 2}})

    gateway = _gateway(tmp_path, monkeypatch, handler, "direction-t3")
    outcome = _run(plan, taxonomy, gateway, tmp_path, "direction-t3")
    assert outcome["stop_reason"] == "first_batch_gate_failed" and outcome["requests_audited_total"] == 1
    assert outcome["stop_detail"]["failure_reason"] in ("malformed_response", "provider_error")


def test_a_later_failed_batch_is_saved_as_a_fallback_never_as_neutral_and_the_run_continues(plan, taxonomy, tmp_path, monkeypatch):
    victim = plan.batch_claim_ids(5)
    sends = []
    gateway = _gateway(tmp_path, monkeypatch, _valid_handler(sends, fail_when=lambda items: [i["claim_id"] for i in items] == victim), "direction-t4")
    outcome = _run(plan, taxonomy, gateway, tmp_path, "direction-t4")

    assert outcome["stop_reason"] is None and outcome["requests_audited_total"] == 17
    assert outcome["batch_states"] == {"valid_response": 16, "failed": 1}
    failed = plan.batches[5]
    assert {i.candidate["stance_method"] for i in failed} == {"deterministic_fallback"}
    assert {i.candidate["stance_fallback_reason"] for i in failed} == {"provider_error"}
    llm = [i for i in plan.items if i.candidate["stance_method"] == "llm"]
    assert len(llm) == 152
    assert all(i.candidate["evidence_stance_version"] == esl.DETERMINISTIC_CLASSIFIER_VERSION for i in failed), \
        "a failed pair keeps the deterministic classifier's own identity -- it is not called an LLM result"


def test_an_invalid_item_in_a_valid_response_falls_back_for_that_pair_only(plan, taxonomy, tmp_path, monkeypatch):
    def corrupt(answer):
        answer[2]["stance"] = "bullish"  # not in the five-value vocabulary

    sends = []
    gateway = _gateway(tmp_path, monkeypatch, _valid_handler(sends, mutate=lambda a: corrupt(a) if len(a) == 10 else None), "direction-t5")
    outcome = _run(plan, taxonomy, gateway, tmp_path, "direction-t5")
    assert outcome["stop_reason"] is None and outcome["batch_states"] == {"valid_response": 17}
    assert sum(1 for i in plan.items if i.candidate["stance_fallback_reason"] == "invalid_stance") == 16
    assert sum(1 for i in plan.items if i.candidate["stance_method"] == "llm") == 162 - 16


def test_the_cap_stops_scheduling_and_a_resume_never_resends_or_regains_allowance(plan, taxonomy, tmp_path, monkeypatch):
    sends1 = []
    first = _gateway(tmp_path, monkeypatch, _valid_handler(sends1), "direction-t6", max_calls=5)
    stopped = _run(plan, taxonomy, first, tmp_path, "direction-t6", hard_cap=5)
    assert stopped["stop_reason"] == "call_cap_would_be_exceeded" and len(sends1) == 5 and stopped["batch_states"] == {"valid_response": 5}

    sends2 = []
    capped = _gateway(tmp_path, monkeypatch, _valid_handler(sends2), "direction-t6", max_calls=12)
    again = _run(plan, taxonomy, capped, tmp_path, "direction-t6", hard_cap=5)
    assert again["stop_reason"] == "call_cap_would_be_exceeded" and sends2 == []
    assert again["stop_detail"]["prior_sent_by_earlier_processes"] == 5

    sends3 = []
    resumed = _gateway(tmp_path, monkeypatch, _valid_handler(sends3), "direction-t6", max_calls=12)
    done = _run(plan, taxonomy, resumed, tmp_path, "direction-t6", hard_cap=17)
    assert done["stop_reason"] is None and len(sends3) == 12 and done["requests_audited_total"] == 17
    all_requests = sends1 + sends3
    assert len(all_requests) == len({tuple(c) for c in all_requests}) == 17, "every batch was requested exactly once across processes"
    assert sum(1 for i in plan.items if i.candidate["stance_method"] == "llm") == 162, "the resumed process re-applied the saved first five batches"


def test_a_batch_audited_but_never_saved_is_unknown_and_is_never_resent(plan, taxonomy, tmp_path, monkeypatch):
    sends = []
    gateway = _gateway(tmp_path, monkeypatch, _valid_handler(sends), "direction-t7")
    req_path, _ = audit_paths(tmp_path, "direction-t7")
    req_path.parent.mkdir(parents=True, exist_ok=True)
    with open(req_path, "a") as handle:  # a request that reached the transport in an earlier process; its answer was never saved
        handle.write(json.dumps({"attempt_id": "crash:1", "task": STANCE_TASK, "claim_ids": plan.batch_claim_ids(3),
                                 "url": "https://api.deepseek.com/chat/completions", "body": "{}", "headers": {}}) + "\n")
    outcome = _run(plan, taxonomy, gateway, tmp_path, "direction-t7", hard_cap=17)
    assert plan.batch_claim_ids(3) not in sends and len(sends) == 16, "17 batches minus the unknown one; the audited request still counts toward the cap (1 + 16 = 17)"
    assert outcome["requests_audited_total"] == 17
    checkpoint = load_checkpoint(tmp_path / "direction-t7" / "checkpoint_direction.json")
    assert checkpoint["batches"]["3"]["state"] == "unknown_inflight"
    assert outcome["batch_states"]["unknown_inflight"] == 1
    results = collect_direction_results(plan, run_output_root=tmp_path, execution_id="direction-t7", base_run_id=PARENT_ID, root_run_id=ROOT_ID,
                                        checkpoint=checkpoint, effective_config={})
    assert results["completion"]["complete"] is False and results["completion"]["never_scheduled_or_unknown"] == 10


def test_the_direction_gateway_refuses_every_other_task_and_preflight_rejects_the_env_dotenv_default(plan, taxonomy, tmp_path, monkeypatch):
    gateway = _gateway(tmp_path, monkeypatch, _valid_handler([]), "direction-t8")
    guarded = TaskAllowlistGateway(gateway, allowed_tasks=(STANCE_TASK,))
    from comqutor_alpha.classification_recovery import RecoveryTaskNotAllowedError

    with pytest.raises(RecoveryTaskNotAllowedError):
        guarded.invoke_json_with_trace("alpha_classifier", {"claim": "x"}, lambda p: p)
    assert read_jsonl(audit_paths(tmp_path, "direction-t8")[0]) == []

    for attribute, value, needle in (("max_retries", 1, "max_retries"), ("timeout_seconds", 20.0, "timeout_seconds")):
        broken = _gateway(tmp_path / attribute, monkeypatch, _valid_handler([]), "direction-t8b")
        setattr(broken, attribute, value)
        with pytest.raises(RuntimeError, match=needle):
            preflight_direction_gateway(broken, hard_cap=17, prior_sent=0, concurrency=4, expected_model=MODEL, expected_timeout=45.0)
    over = _gateway(tmp_path / "over", monkeypatch, _valid_handler([]), "direction-t8c", max_calls=17)
    with pytest.raises(RuntimeError, match="remaining cap"):
        preflight_direction_gateway(over, hard_cap=17, prior_sent=5, concurrency=4, expected_model=MODEL, expected_timeout=45.0)


def test_the_driver_environment_check_names_each_deviation(driver):
    complete = {**driver.REQUIRED_ENV, "COMQUTOR_WEEK2_LLM_MAX_CALLS": "17", "DEEPSEEK_API_KEY": "k",
                "COMQUTOR_DATABASE_URL": "postgresql+psycopg://u:p@localhost:5433/comqutor_alpha_test", "COMQUTOR_REQUIRE_DATABASE_NAME": "comqutor_alpha_test"}
    assert driver.environment_problems(0, complete) == []
    assert any("MAX_RETRIES" in p for p in driver.environment_problems(0, {**complete, "COMQUTOR_WEEK2_LLM_MAX_RETRIES": "1"}))
    assert any("TIMEOUT" in p for p in driver.environment_problems(0, {**complete, "COMQUTOR_WEEK2_LLM_TIMEOUT_SECONDS": "20"}))
    assert any("MAX_CALLS" in p for p in driver.environment_problems(0, {**complete, "COMQUTOR_WEEK2_LLM_MAX_CALLS": "18"}))
    assert any("MAX_CALLS" in p for p in driver.environment_problems(5, {**complete, "COMQUTOR_WEEK2_LLM_MAX_CALLS": "13"}))
    assert any("CONTENT_SUPPORT_MAX_TOKENS" in p for p in driver.environment_problems(0, {**complete, "COMQUTOR_WEEK2_CONTENT_SUPPORT_MAX_TOKENS": "8192"}))
    assert any("MAX_TOKENS" in p for p in driver.environment_problems(0, {**complete, "COMQUTOR_WEEK2_ALPHA_CLASSIFIER_MAX_TOKENS": "64"}))
    assert any("_test" in p for p in driver.environment_problems(0, {**complete, "COMQUTOR_DATABASE_URL": "postgresql+psycopg://u:p@localhost:5433/comqutor_alpha"}))


def test_execute_without_the_acknowledgement_builds_and_sends_nothing(driver, monkeypatch, tmp_path):
    monkeypatch.delenv(driver.ACK_ENV, raising=False)
    built = []
    import comqutor_alpha.structure_engine.week2_llm as week2_llm

    monkeypatch.setattr(week2_llm, "build_server_week2_llm_gateway", lambda *a, **k: built.append(1))
    monkeypatch.setattr(driver, "OUTPUT_ROOT", tmp_path / "runs")
    assert driver.run_real_direction(None, environ={}) == 1
    assert driver.run_real_direction(None, environ={driver.ACK_ENV: "direction-162-pairs-17-requests-plan-0000000000000000"}) == 1
    assert built == [] and not (tmp_path / "runs").exists()


# ---------------------------------------------------------------------------
# The derived evaluation run, end to end on scratch copies
# ---------------------------------------------------------------------------


@pytest.fixture(scope="module")
def evaluation(driver, tmp_path_factory):
    from comqutor_alpha.storage.db.repository import build_write_repository_from_env

    root = tmp_path_factory.mktemp("direction_eval")
    out_root = root / "outputs"
    out_root.mkdir()
    marker = root / "FAKE_HTTP_TEST_ARTIFACTS.marker"
    marker.write_text("fake transport; nothing here is a real direction result\n")
    shutil.copytree(ROOT_DIR, out_root / ROOT_ID)
    shutil.copytree(PARENT_DIR, out_root / PARENT_ID)
    real_hashes = {"root": snapshot_directory_hashes(ROOT_DIR), "parent": snapshot_directory_hashes(PARENT_DIR)}

    mp = pytest.MonkeyPatch()
    mp.setenv("COMQUTOR_DATABASE_URL", f"sqlite:///{root / 'eval.db'}")
    mp.setenv("COMQUTOR_OUTPUT_DIR", str(out_root))
    try:
        parent = json.loads((out_root / PARENT_ID / "alpha_matches.json").read_text())
        tax = load_alpha_taxonomy()
        plan = build_direction_plan(parent, tax)
        victim = plan.batch_claim_ids(9)
        sends = []
        gateway = _gateway(out_root, mp, _valid_handler(sends, fail_when=lambda items: [i["claim_id"] for i in items] == victim), "direction-20261007T000000Z-aaaaaaaa")
        repository = build_write_repository_from_env(str(out_root))
        repository.persist_agent_outputs(run_id=ROOT_ID, ticker="AMD", structured_payload=json.loads((out_root / ROOT_ID / "structured_agent_outputs.json").read_text()))
        result = driver.execute_direction(
            plan=plan, taxonomy=tax, parent=parent, gateway=gateway, output_root=out_root, parent_id=PARENT_ID, root_id=ROOT_ID,
            execution_id="direction-20261007T000000Z-aaaaaaaa", checkpoint_origin="fake_http_test", hard_cap=17, repository=repository, plan_hash="test")
        yield {"root": root, "out_root": out_root, "result": result, "sends": sends, "victim": victim, "real_before": real_hashes,
               "execution_id": "direction-20261007T000000Z-aaaaaaaa", "repository": repository}
    finally:
        mp.undo()


@pytest.fixture
def api(evaluation, monkeypatch):
    from fastapi.testclient import TestClient

    import comqutor_alpha.api.main as main_module

    monkeypatch.setenv("COMQUTOR_DATABASE_URL", f"sqlite:///{evaluation['root'] / 'eval.db'}")
    monkeypatch.setenv("COMQUTOR_OUTPUT_DIR", str(evaluation["out_root"]))
    return TestClient(main_module.app).get


def test_the_evaluation_run_is_saved_with_parent_and_root_lineage_and_separate_completeness(evaluation):
    result = evaluation["result"]
    # T4 (2026-10-08): the one disclosed classification timeout makes the run partial, never completed
    assert result["outcome"]["stop_reason"] is None and result["finalized"]["status"] == "ok" and result["finalized"]["run_status"] == "partial"
    assert result["finalized"]["base_run_unchanged"] is True and result["finalized"]["root_run_unchanged"] is True
    run_dir = evaluation["out_root"] / evaluation["execution_id"]
    lineage = json.loads((run_dir / DIRECTION_LINEAGE_FILENAME).read_text())
    assert [(e["run_id"], e["role"]) for e in lineage["lineage_chain"]] == [
        (evaluation["execution_id"], "this_execution"), (PARENT_ID, "direct_parent"), (ROOT_ID, "original_research_run")]
    assert lineage["execution_type"] == "alpha_direction_evaluation" and len(lineage["claim_identity_map"]) == 975
    completeness = lineage["completeness"]
    assert completeness["direction"]["llm_results"] == 152 and completeness["direction"]["deterministic_fallback"] == 10 and completeness["direction"]["complete"] is False
    assert "classification" in completeness and "downstream_evaluation" in completeness
    labels = {e["classification_source"] for e in lineage["claim_identity_map"]}
    assert {"direction_llm_result", "direction_not_obtained_deterministic_fallback"} <= labels
    metadata = json.loads((run_dir / "metadata.json").read_text())
    assert (metadata["based_on_run_id"], metadata["root_research_run_id"]) == (PARENT_ID, ROOT_ID)
    assert not (run_dir / "recovery_lineage.json").exists()


def test_parent_and_root_runs_are_byte_identical_after_the_evaluation(evaluation):
    assert snapshot_directory_hashes(evaluation["out_root"] / ROOT_ID) == evaluation["real_before"]["root"]
    assert snapshot_directory_hashes(evaluation["out_root"] / PARENT_ID) == evaluation["real_before"]["parent"]
    assert snapshot_directory_hashes(ROOT_DIR) == evaluation["real_before"]["root"], "and the real directories were never touched"
    assert snapshot_directory_hashes(PARENT_DIR) == evaluation["real_before"]["parent"]


def test_only_direction_requests_were_sent_and_stances_come_from_the_saved_results(evaluation):
    assert len(evaluation["sends"]) == 17
    run_dir = evaluation["out_root"] / evaluation["execution_id"]
    requests = read_jsonl(run_dir / "error_logs" / "week2_llm_provider_request_audit.jsonl")
    assert {r["task"] for r in requests} == {STANCE_TASK}
    results = json.loads((run_dir / DIRECTION_RESULTS_FILENAME).read_text())
    by_pair = {(p["claim_id"], p["target_alpha_id"]): p for p in results["pairs"]}
    matches = json.loads((run_dir / "alpha_matches.json").read_text())["matches"]
    seen = 0
    for match in matches:
        for candidate in match.get("candidate_scores") or []:
            pair = by_pair.get((match["claim_id"], candidate["alpha_id"]))
            if pair is None:
                continue
            seen += 1
            assert candidate["evidence_stance"] == pair["final_stance"] and candidate["stance_method"] == pair["method"]
            assert candidate["stance_fallback_reason"] == pair["fallback_reason"]
    assert seen == 162


def test_api_reads_the_evaluation_run_with_its_three_separate_axes(evaluation, api):
    response = api(f"/api/research/{evaluation['execution_id']}").json()
    # T4 (2026-10-08): partial because of the one disclosed classification timeout; graph and conflicts are still ready
    assert response["status"] == "partial" and response["structure_graph_status"] == "ready" and response["conflict_status"] == "ready"
    lineage = response["lineage"]
    assert (lineage["based_on_run_id"], lineage["root_research_run_id"], lineage["execution_type"]) == (PARENT_ID, ROOT_ID, "alpha_direction_evaluation")
    assert lineage["lineage_artifact"] == DIRECTION_LINEAGE_FILENAME
    assert lineage["direction_completion"]["llm_results"] == 152 and lineage["direction_completion"]["complete"] is False
    assert response["alpha_classification_completion"]["total_claims"] == 975
    assert response["alpha_classification_completion"]["call_failure_count"] == 1, "the classification timeout stays disclosed"
    assert response["alpha_classification_status"] == "incomplete"
    history = {row["run_id"]: row for row in api("/api/research?ticker=AMD&limit=50").json()["items"]}
    assert history[evaluation["execution_id"]]["status"] == "partial"


def test_export_zip_matches_the_files_and_carries_the_direction_artifacts(evaluation, api):
    import io
    import zipfile

    run_dir = evaluation["out_root"] / evaluation["execution_id"]
    export = api(f"/api/research/{evaluation['execution_id']}/export")
    assert export.status_code == 200
    archive = zipfile.ZipFile(io.BytesIO(export.content))
    assert {DIRECTION_LINEAGE_FILENAME, DIRECTION_RESULTS_FILENAME, "alpha_matches.json", "conflicts.json", "alpha_activations.json",
            "evidence_facts.json", "summary.json", "artifact_manifest.json"} <= set(archive.namelist())
    assert [n for n in archive.namelist() if archive.read(n) != (run_dir / n).read_bytes()] == []
    download = api(f"/api/research/{evaluation['execution_id']}/artifacts/{DIRECTION_RESULTS_FILENAME}")
    assert download.status_code == 200 and download.json()["completion"]["llm_results"] == 152
