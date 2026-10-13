"""P4 phase 2 (2026-10-12): the controlled execution entry of a small-sample relevance plan, and the evaluation tool.

Nothing here reaches a model or the network. The execution guards run against a small REAL sample (two saved GOOGL runs, re-read from
disk) with scripted or simulated answers; the LIVE path runs the real client construction with only the lowest HTTP layer replaced by
``httpx.MockTransport`` (and every socket connect forbidden). The evaluation tests use explicitly labelled TEST DATA samples: scripted
answers and scripted review sheets, chosen to exercise mismatch, duplicate, missing, failed, unresolved, not-sent and pending cases.
A passing test proves only that the guards and the statistics work -- never anything about the quality of a real model.
"""

from __future__ import annotations

import csv
import dataclasses
import io
import json
import socket
from collections.abc import Callable
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any

import httpx
import pytest

from comqutor_alpha import (
    alpha_relevance_eval_prep as ep,
    alpha_relevance_evaluation as ev,
    alpha_relevance_experiment as ex,
)
from comqutor_alpha.alpha_library.alpha_relevance_elements import (
    load_relevance_definitions,
    sha256_canonical_json,
)
from comqutor_alpha.graph_engine.alpha_relevance_judgment import (
    LEDGER_DIRNAME,
    RESULTS_FILENAME,
)
from comqutor_alpha.structure_engine import alpha_relevance_llm as rl

REPO_ROOT = Path(__file__).resolve().parents[1]
DEFS = load_relevance_definitions()
NOW = datetime(2026, 10, 12, 12, 0, tzinfo=timezone.utc)
# TEST DATA basis for plans built in tests (the real plan measures saved ledgers instead)
TEST_REFERENCE = {
    "sources": [], "reference_task": "TEST DATA", "reference_provider_models": [],
    "stance": {"calls": 0, "chars_per_input_token": {"median": 4.0, "min": 3.5, "max": 4.5}, "output_tokens_per_item": {"median": 800.0, "max": 1300.0},
               "latency_seconds_per_item": {"median": 10.0, "max": 20.0}},
    "max_tokens_enforcement": {"calls": 0, "calls_over_cap": 0, "by_cap": {}},
}


@pytest.fixture(autouse=True, scope="module")
def _pinned_to_prompt_v2():
    """2026-10-12, session 6: prompt v3 / output v3 became current. The tests of this module cover the version-independent chain and the
    v2 contract, so they run with v2 as the module's current version; the current v3 path is covered by tests/test_p4_exp3_v3.py."""
    with pytest.MonkeyPatch.context() as patch:
        for name, value in rl.version_constants(rl.PROMPT_VERSION_V2).items():
            patch.setattr(rl, name, value)
        yield


# ----------------------------------------------------------------------------------------------------------- helpers
class _Message:
    def __init__(self, content: str) -> None:
        self.content = content


class ScriptedProvider:
    """TEST DATA: answers each call with ``responder(batch payload, call number)`` -- a dict (sent as JSON), a raw string, or an
    exception (raised)."""

    def __init__(self, responder: Callable[[dict[str, Any], int], Any]) -> None:
        self.responder = responder
        self.calls = 0

    def invoke(self, prompt: str) -> _Message:
        self.calls += 1
        payload = json.loads(prompt.split(rl.PROMPT_IDENTITY_SEPARATOR, 1)[1])
        out = self.responder(payload, self.calls)
        if isinstance(out, BaseException):
            raise out
        return _Message(out if isinstance(out, str) else json.dumps(out))


class Refusal(Exception):
    status_code = 429  # what the provider-stop machinery reads from a client error


def simulated(payload: dict[str, Any], _call: int) -> dict[str, Any]:
    return json.loads(ex.SimulatedRelevanceProvider().invoke("x" + rl.PROMPT_IDENTITY_SEPARATOR + json.dumps(payload)).content)


def answer(sample: dict[str, Any], outcome: str = "DETERMINED", tier: str | None = "weak", anchors: list[str] | None = None,
           unresolved: str | None = None) -> dict[str, Any]:
    anchors = anchors or []
    return {"claim_id": sample["claim_id"], "alpha_id": sample["target_alpha_id"], "outcome": outcome, "tier": tier,
            "anchor_element_ids": anchors, "basis": "TEST DATA scripted basis", "unresolved_reason": unresolved,
            # output contract v2: every anchor carries a quote of the claim's own words
            "anchor_evidence": [{"element_id": a, "quote": sample["claim_text"][:rl.MAX_QUOTE_CHARS]} for a in anchors]}


def core_of(alpha_id: str) -> str:
    return next(e for e, o in DEFS[alpha_id].ownership.items() if o == "core")


def strong_of(alpha_id: str) -> str:
    return next(e for e, o in DEFS[alpha_id].ownership.items() if o == "strong")


def write_inputs(tmp: Path, manifest: dict[str, Any], *, mode: str = ex.EVAL_MODE_REHEARSAL, plan_edit: Callable[[dict[str, Any]], None] | None = None,
                 auth_edit: Callable[[dict[str, Any]], None] | None = None) -> dict[str, Path]:
    """Manifest + plan + authorization on disk, the way an operator hands them to the entry."""
    tmp.mkdir(parents=True, exist_ok=True)
    manifest_path = tmp / "sample_manifest.json"
    manifest_sha = ep.write_json(manifest_path, manifest)
    plan = ep.build_plan(manifest, DEFS, manifest_file_sha256=manifest_sha, reference=TEST_REFERENCE, provider=ep.LIVE_PROVIDER, model=ep.LIVE_MODEL,
                         batch_size=ep.LIVE_BATCH_SIZE, repeat_every=ep.LIVE_REPEAT_EVERY, timeout_seconds=ep.LIVE_TIMEOUT_SECONDS,
                         max_output_tokens=ep.LIVE_MAX_OUTPUT_TOKENS, repo_root=REPO_ROOT)
    if plan_edit is not None:
        plan_edit(plan)
        plan["plan_sha256"] = ep.plan_content_sha256(plan)  # a consistently re-hashed but different plan
    plan_path = tmp / "execution_plan.json"
    ep.write_json(plan_path, plan)
    if mode == ex.EVAL_MODE_LIVE:
        auth = ep.authorization_template(plan)
        auth.update({"live_authorized": True, "max_cost_usd": 1.0, "authorized_by": "TEST DATA owner", "authorized_at": (NOW - timedelta(hours=1)).isoformat(),
                     "valid_until": (NOW + timedelta(hours=1)).isoformat()})
    else:
        auth = ep.rehearsal_authorization(plan, authorized_by="TEST DATA rehearsal", authorized_at=(NOW - timedelta(hours=1)).isoformat(),
                                          valid_until=(NOW + timedelta(hours=1)).isoformat())
    if auth_edit is not None:
        auth_edit(auth)
    auth_path = tmp / f"authorization_{mode}.json"
    ep.write_json(auth_path, auth)
    return {"manifest": manifest_path, "plan": plan_path, "authorization": auth_path, "eval_root": tmp / "evaluations"}


def run(paths: dict[str, Path], mode: str | None = ex.EVAL_MODE_REHEARSAL, **kwargs: Any) -> dict[str, Any]:
    kwargs.setdefault("now", NOW)
    return ex.run_relevance_evaluation_plan(plan_path=paths["plan"], manifest_path=paths["manifest"], authorization_path=paths["authorization"],
                                            eval_root=paths["eval_root"], mode=mode, **kwargs)


def nothing_written(paths: dict[str, Path]) -> bool:
    return not paths["eval_root"].exists() and not Path(str(paths["authorization"]) + ex.AUTHORIZATION_CONSUMED_SUFFIX).exists()


# ----------------------------------------------------------------------------------------------------------- a small REAL sample
def _googl_runs() -> list[Path]:
    runs = []
    for root in ep.SAVED_RUN_ROOTS:
        for path in sorted(root.iterdir()) if root.is_dir() else []:
            meta = path / "metadata.json"
            if ep.is_original_run_dir(path) and meta.is_file() and json.loads(meta.read_text(encoding="utf-8")).get("ticker") == "GOOGL":
                runs.append(path)
    return runs


GOOGL_RUNS = _googl_runs()
needs_saved_runs = pytest.mark.skipif(len(GOOGL_RUNS) < 2, reason="the saved GOOGL runs are not present (local run data)")


@pytest.fixture(scope="module")
def real_manifest() -> dict[str, Any]:
    if len(GOOGL_RUNS) < 2:
        pytest.skip("the saved GOOGL runs are not present (local run data)")
    selection = ep.select_sample(ep.scan_candidates(GOOGL_RUNS, DEFS), quotas={ep.STRATUM_ORDINARY: 9})
    return ep.build_manifest(selection, DEFS, pool_runs=[r.name for r in GOOGL_RUNS])


# ----------------------------------------------------------------------------------------------------------- execution entry
@needs_saved_runs
def test_a_rehearsal_sends_exactly_the_planned_requests_once_into_new_task_own_ledgers(tmp_path, real_manifest):
    paths = write_inputs(tmp_path, real_manifest)
    plan = json.loads(paths["plan"].read_text(encoding="utf-8"))
    provider = ScriptedProvider(simulated)
    result = run(paths, provider=provider)
    assert result["status"] == "ok" and result["test_data"] is True and result["stop"] is None
    assert provider.calls == result["requests_sent"] == plan["request_cap"] == sum(len(r["batches"]) for r in plan["rounds"])
    eval_dir = Path(result["evaluation_dir"])
    assert eval_dir.parent == paths["eval_root"] and eval_dir.name.startswith("relevance-eval-")
    record = json.loads((eval_dir / ex.EVAL_RECORD_FILENAME).read_text(encoding="utf-8"))
    assert record["status"] == "COMPLETED" and record["test_data"] is True and record["plan_sha256"] == plan["plan_sha256"]
    for round_info in result["rounds"]:
        round_dir = eval_dir / round_info["round_run_id"]
        calls = [json.loads(line) for line in (round_dir / LEDGER_DIRNAME / "llm_semantic_calls.jsonl").read_text(encoding="utf-8").splitlines()]
        assert round_info["ledger_integrity"] == "MATCHES_MANIFEST" and {c["task"] for c in calls} == {rl.LLM_TASK_NAME}
        assert all(c["execution_mode"] == "test" and c["provider"] == "simulated" and not c["cache"]["hit"] and c["retry_count"] == 0 for c in calls)
        assert json.loads((round_dir / RESULTS_FILENAME).read_text(encoding="utf-8"))["evaluation"]["round"] == round_info["round"]
    # the repeat round re-sent identical payloads (same input hashes as their round-1 batches)
    r1, r2 = (eval_dir / f"{result['evaluation_id']}-r{n}" / LEDGER_DIRNAME / "llm_semantic_calls.jsonl" for n in (1, 2))
    first = {json.loads(line)["input_sha256"] for line in r1.read_text(encoding="utf-8").splitlines()}
    second = [json.loads(line)["input_sha256"] for line in r2.read_text(encoding="utf-8").splitlines()]
    assert second and set(second) <= first
    # the authorization is used once: a second execution is refused and sends nothing
    assert Path(str(paths["authorization"]) + ex.AUTHORIZATION_CONSUMED_SUFFIX).is_file()
    again = ScriptedProvider(simulated)
    assert run(paths, provider=again)["error_code"] == "AUTHORIZATION_ALREADY_USED" and again.calls == 0
    assert [p.name for p in paths["eval_root"].iterdir()] == [eval_dir.name]


REFUSALS = [
    ("mode_missing", {}, {}, None, "EVALUATION_MODE_NOT_SELECTED"),
    ("mode_unknown", {}, {}, "REAL", "EVALUATION_MODE_NOT_SELECTED"),
    ("live_auth_for_rehearsal", {}, {"mode": "LIVE"}, ex.EVAL_MODE_REHEARSAL, "AUTHORIZATION_MODE_MISMATCH"),
    ("rehearsal_auth_for_live", {}, {}, ex.EVAL_MODE_LIVE, "AUTHORIZATION_MODE_MISMATCH"),
    ("rehearsal_not_authorized", {}, {"rehearsal_authorized": False}, ex.EVAL_MODE_REHEARSAL, "REHEARSAL_NOT_AUTHORIZED"),
    ("rehearsal_claims_live", {}, {"live_authorized": True}, ex.EVAL_MODE_REHEARSAL, "REHEARSAL_NOT_AUTHORIZED"),
    ("other_plan", {}, {"plan_sha256": "0" * 64}, ex.EVAL_MODE_REHEARSAL, "AUTHORIZATION_PLAN_MISMATCH"),
    ("other_manifest", {}, {"sample_manifest_content_sha256": "0" * 64}, ex.EVAL_MODE_REHEARSAL, "AUTHORIZATION_MANIFEST_MISMATCH"),
    ("cap_not_the_plan", {}, {"max_requests": 999}, ex.EVAL_MODE_REHEARSAL, "AUTHORIZATION_CAP_MISMATCH"),
    ("expired", {}, {"valid_until": (NOW - timedelta(seconds=1)).isoformat()}, ex.EVAL_MODE_REHEARSAL, "AUTHORIZATION_EXPIRED"),
    ("no_time_zone", {}, {"valid_until": "2026-10-12T13:00:00"}, ex.EVAL_MODE_REHEARSAL, "AUTHORIZATION_EXPIRY_INVALID"),
    ("signed_in_future", {}, {"authorized_at": (NOW + timedelta(hours=1)).isoformat()}, ex.EVAL_MODE_REHEARSAL, "AUTHORIZATION_TIME_INVALID"),
    ("unsigned", {}, {"authorized_by": " "}, ex.EVAL_MODE_REHEARSAL, "AUTHORIZATION_SIGNER_MISSING"),
    ("thresholds_other", {}, {"quality_thresholds_confirmed": True, "quality_thresholds_sha256": "0" * 64}, ex.EVAL_MODE_REHEARSAL, "AUTHORIZATION_THRESHOLDS_MISMATCH"),
    ("code_changed", {"code": True}, {}, ex.EVAL_MODE_REHEARSAL, "CODE_IDENTITY_MISMATCH"),
    ("requests_drift", {"drift": True}, {}, ex.EVAL_MODE_REHEARSAL, "PLAN_REQUESTS_DRIFT"),
    ("repeat_not_identical", {"repeat_drift": True}, {}, ex.EVAL_MODE_REHEARSAL, "PLAN_REQUESTS_DRIFT"),
    ("cap_over_ceiling", {"cap": True}, {}, ex.EVAL_MODE_REHEARSAL, "PLAN_CAP_INVALID"),
    ("retries_in_plan", {"retries": True}, {}, ex.EVAL_MODE_REHEARSAL, "PLAN_CONFIG_MISMATCH"),
]


def _plan_edit(spec: dict[str, Any]) -> Callable[[dict[str, Any]], None] | None:
    if not spec:
        return None

    def edit(plan: dict[str, Any]) -> None:
        if spec.get("code"):
            plan["code_identity"]["files"]["comqutor_alpha/alpha_relevance_experiment.py"] = "0" * 64
        if spec.get("drift"):  # a round-1 batch that is NOT repeated: only the round-1 comparison can notice
            assert len(plan["rounds"][0]["batches"]) >= 2
            plan["rounds"][0]["batches"][1]["payload_sha256"] = "0" * 64
        if spec.get("repeat_drift"):
            plan["rounds"][1]["batches"][0]["sample_ids"] = list(reversed(plan["rounds"][1]["batches"][0]["sample_ids"])) + ["S999"]
        if spec.get("cap"):
            extra = [dict(plan["rounds"][0]["batches"][0], batch_id=f"RB01x{i}") for i in range(ex.P4_RELEVANCE_LIVE_SMALL_SAMPLE_20261012.max_calls)]
            plan["rounds"].append({"round": 3, "purpose": "TEST DATA: more than the ceiling", "batches": extra})
            plan["request_cap"] = sum(len(r["batches"]) for r in plan["rounds"])
        if spec.get("retries"):
            plan["call_settings"]["max_retries"] = 1
    return edit


@needs_saved_runs
@pytest.mark.parametrize(("name", "plan_spec", "auth_change", "mode", "code"), REFUSALS, ids=[r[0] for r in REFUSALS])
def test_every_refusal_happens_before_anything_is_written_or_sent(tmp_path, real_manifest, name, plan_spec, auth_change, mode, code):
    paths = write_inputs(tmp_path, real_manifest, plan_edit=_plan_edit(plan_spec), auth_edit=(lambda a: a.update(auth_change)) if auth_change else None)
    provider = ScriptedProvider(simulated)
    result = run(paths, mode=mode, provider=provider if mode != ex.EVAL_MODE_LIVE else None)
    assert result["status"] == "failed" and result["error_code"] == code, result
    assert provider.calls == 0 and nothing_written(paths)


@needs_saved_runs
def test_tampered_plan_or_manifest_files_and_wrong_roots_are_refused(tmp_path, real_manifest):
    provider = ScriptedProvider(simulated)
    paths = write_inputs(tmp_path / "a", real_manifest)
    plan = json.loads(paths["plan"].read_text(encoding="utf-8"))
    plan["request_cap"] += 1  # edited without re-hashing
    paths["plan"].write_text(json.dumps(plan), encoding="utf-8")
    assert run(paths, provider=provider)["error_code"] == "PLAN_HASH_MISMATCH"
    paths = write_inputs(tmp_path / "b", real_manifest)
    paths["manifest"].write_text(paths["manifest"].read_text(encoding="utf-8") + " ", encoding="utf-8")  # one byte more
    assert run(paths, provider=provider)["error_code"] == "MANIFEST_FILE_MISMATCH"
    paths = write_inputs(tmp_path / "c", real_manifest)
    assert ex.run_relevance_evaluation_plan(plan_path=paths["plan"], manifest_path=paths["manifest"], authorization_path=paths["authorization"],
                                            eval_root=REPO_ROOT / "outputs" / "relevance_evaluations", mode=ex.EVAL_MODE_REHEARSAL, provider=provider,
                                            now=NOW)["error_code"] == "REFUSED_REAL_OUTPUTS"
    assert run(paths, provider=provider, config=ex.P4_RELEVANCE_SIMULATED_20261012)["error_code"] == "UNKNOWN_EVALUATION_CONFIG"
    assert provider.calls == 0 and nothing_written(paths)
    # the run-level entry never accepts the evaluation configuration
    assert ex.judge_run_relevance("any", output_root=tmp_path / "c", config=ex.P4_RELEVANCE_LIVE_SMALL_SAMPLE_20261012)["status"] == "disabled"


@needs_saved_runs
def test_changed_definitions_or_changed_saved_sources_are_refused(tmp_path, real_manifest, monkeypatch):
    provider = ScriptedProvider(simulated)
    paths = write_inputs(tmp_path / "a", real_manifest)
    monkeypatch.setattr(ep, "verify_manifest_sources", lambda manifest: [{"sample_id": "S001", "problem": "SOURCE_TEXT_CHANGED"}])
    assert run(paths, provider=provider)["error_code"] == "SOURCE_CHANGED"
    monkeypatch.undo()
    # the definitions change after the plan was built: the planned requests no longer match what would be sent
    paths = write_inputs(tmp_path / "b", real_manifest)
    alpha = real_manifest["samples"][0]["target_alpha_id"]
    changed = {**DEFS, alpha: dataclasses.replace(DEFS[alpha], sha256="0" * 64)}
    monkeypatch.setattr(ex, "load_relevance_definitions", lambda: changed)
    assert run(paths, provider=provider)["error_code"] == "DEFINITION_CHANGED_SINCE_SAMPLE"
    assert provider.calls == 0 and nothing_written(paths)


@needs_saved_runs
def test_a_provider_refusal_stops_the_whole_execution_and_nothing_is_retried(tmp_path, real_manifest):
    paths = write_inputs(tmp_path, real_manifest)
    provider = ScriptedProvider(lambda payload, call: Refusal("TEST DATA: HTTP 429") if call == 2 else simulated(payload, call))
    result = run(paths, provider=provider)
    assert result["status"] == "stopped" and result["stop"] == "PROVIDER_REFUSAL" and provider.calls == result["requests_sent"] == 2
    record = json.loads((Path(result["evaluation_dir"]) / ex.EVAL_RECORD_FILENAME).read_text(encoding="utf-8"))
    sent = [b for b in record["batches"] if b["status"] == "SENT"]
    assert [b["provider_attempts"] for b in sent] == [1, 1] and all(b["status"] == "NOT_SENT" for b in record["batches"][2:])
    assert record["rounds"][-1]["status"] == "NOT_STARTED"


@needs_saved_runs
def test_a_transient_error_is_never_retried(tmp_path, real_manifest):
    paths = write_inputs(tmp_path, real_manifest)
    provider = ScriptedProvider(lambda payload, call: ConnectionError("TEST DATA: transient") if call == 1 else simulated(payload, call))
    result = run(paths, provider=provider)
    assert result["status"] == "ok" and provider.calls == result["requests_sent"]  # the failed batch was not sent again
    record = json.loads((Path(result["evaluation_dir"]) / ex.EVAL_RECORD_FILENAME).read_text(encoding="utf-8"))
    assert record["batches"][0]["states"] == {rl.STATE_FAILED: len(json.loads(paths["plan"].read_text(encoding="utf-8"))["rounds"][0]["batches"][0]["sample_ids"])}
    assert record["batches"][0]["failure_reasons"] == {rl.FAILURE_PROVIDER_ERROR: record["batches"][0]["states"][rl.STATE_FAILED]}


@needs_saved_runs
def test_three_failed_batches_in_a_row_stop_the_execution(tmp_path, real_manifest):
    paths = write_inputs(tmp_path, real_manifest)
    provider = ScriptedProvider(lambda payload, call: "TEST DATA: not JSON")
    result = run(paths, provider=provider)
    assert result["stop"] == "CONSECUTIVE_FAILED_BATCHES" and provider.calls == result["requests_sent"] == 3


@needs_saved_runs
def test_the_wall_clock_limit_stops_before_the_next_request(tmp_path, real_manifest):
    paths = write_inputs(tmp_path, real_manifest)
    ticks = iter([0.0, 0.0, 1.0, 1.0] + [10.0 ** 9] * 100)
    provider = ScriptedProvider(simulated)
    result = run(paths, provider=provider, clock=lambda: next(ticks))
    assert result["stop"] == "WALL_CLOCK_LIMIT" and provider.calls == 1


# ----------------------------------------------------------------------------------------------------------- LIVE path (mock HTTP)
SERVED_NAME = "TEST-DATA-served-name"  # what the mock provider reports as the serving model: deliberately not the requested name


def _chat_completion(content: str, *, completion_tokens: int) -> dict[str, Any]:
    return {"id": "TEST-DATA", "object": "chat.completion", "created": 0, "model": SERVED_NAME,
            "choices": [{"index": 0, "message": {"role": "assistant", "content": content}, "finish_reason": "stop"}],
            "usage": {"prompt_tokens": 1500, "completion_tokens": completion_tokens, "total_tokens": 1500 + completion_tokens,
                      "completion_tokens_details": {"reasoning_tokens": completion_tokens - 100}, "prompt_cache_hit_tokens": 0,
                      "prompt_cache_miss_tokens": 1500}}


@pytest.fixture
def live_env(monkeypatch):
    for name in ("COMQUTOR_WEEK2_LLM_BASE_URL", "TRADINGAGENTS_LLM_BACKEND_URL", "COMQUTOR_WEEK2_LLM_PROFILE"):
        monkeypatch.delenv(name, raising=False)
    monkeypatch.setenv("COMQUTOR_WEEK2_LLM_PROVIDER", ep.LIVE_PROVIDER)
    monkeypatch.setenv("COMQUTOR_WEEK2_LLM_MODEL", ep.LIVE_MODEL)
    monkeypatch.setenv("DEEPSEEK_API_KEY", "test-key-not-a-secret")

    def no_socket(*_args, **_kwargs):
        raise AssertionError("TEST: no socket may be opened")

    monkeypatch.setattr(socket.socket, "connect", no_socket)


def _mock_client(bodies: list[dict[str, Any]], completion_tokens: int = 900, fail_first_with: int | None = None) -> httpx.Client:
    def handler(request: httpx.Request) -> httpx.Response:
        body = json.loads(request.content)
        bodies.append(body)
        if fail_first_with is not None and len(bodies) == 1:
            return httpx.Response(fail_first_with, json={"error": {"message": "TEST DATA: server error"}})
        payload = json.loads(body["messages"][-1]["content"].split(rl.PROMPT_IDENTITY_SEPARATOR, 1)[1])
        return httpx.Response(200, json=_chat_completion(json.dumps(simulated(payload, len(bodies))), completion_tokens=completion_tokens))
    return httpx.Client(transport=httpx.MockTransport(handler))


@needs_saved_runs
def test_live_builds_the_real_client_with_the_plans_cap_and_no_retry_and_records_usage(tmp_path, real_manifest, live_env):
    paths = write_inputs(tmp_path, real_manifest, mode=ex.EVAL_MODE_LIVE)
    plan = json.loads(paths["plan"].read_text(encoding="utf-8"))
    bodies: list[dict[str, Any]] = []
    result = run(paths, mode=ex.EVAL_MODE_LIVE, _http_client_for_testing=_mock_client(bodies))
    assert result["status"] == "ok" and result["test_data"] is False and len(bodies) == result["requests_sent"] == plan["request_cap"]
    assert {b["model"] for b in bodies} == {ep.LIVE_MODEL} and {b.get("max_tokens") for b in bodies} == {ep.LIVE_MAX_OUTPUT_TOKENS}
    assert not any("max_completion_tokens" in b for b in bodies)
    eval_dir = Path(result["evaluation_dir"])
    calls = [json.loads(line) for r in result["rounds"] for line in
             (eval_dir / r["round_run_id"] / LEDGER_DIRNAME / "llm_semantic_calls.jsonl").read_text(encoding="utf-8").splitlines()]
    assert {(c["provider"], c["model"], c["execution_mode"]) for c in calls} == {(ep.LIVE_PROVIDER, ep.LIVE_MODEL, "live")}
    assert all(c["retry_count"] == 0 and c["token_usage"]["output_tokens"] == 900 for c in calls)
    record = json.loads((eval_dir / ex.EVAL_RECORD_FILENAME).read_text(encoding="utf-8"))
    assert record["recorded_usage"] == {"input_tokens": 1500 * len(calls), "output_tokens": 900 * len(calls), "calls_with_usage": len(calls)}
    assert record["cost_usd_recorded_usage"]["peak"] == ep.usd([0.30, 1.20], 1500 * len(calls), 900 * len(calls))
    # the requested name and the name the provider returned are both kept, with the call dates: the request name pins nothing
    identity = record["model_identity"]
    assert identity["request_model"] == ep.LIVE_MODEL and identity["requested"] == {ep.LIVE_MODEL: len(calls)}
    assert identity["returned_by_provider"] == {SERVED_NAME: len(calls)} and identity["first_call_at"] <= identity["last_call_at"]
    # the prebuilt-prompt seam keeps what the provider reported, like the production path: cap sent, finish reason, raw usage
    for call in calls:
        assert call["request_control"]["request_model"] == ep.LIVE_MODEL and call["request_control"]["max_tokens_value"] == ep.LIVE_MAX_OUTPUT_TOKENS
        assert call["provider_response"]["finish_reason"] == "stop" and call["provider_response"]["response_model"] == SERVED_NAME
        assert call["provider_response"]["raw_usage"]["completion_tokens_details"]["reasoning_tokens"] == 800
    # ... and the evaluation report surfaces it (the review sheet is still blank: nothing is scored)
    sheet = tmp_path / "blank_A.csv"
    manifest = json.loads(paths["manifest"].read_text(encoding="utf-8"))
    sheet.write_text(ep.render_csv(ep.blind_review_rows(manifest, DEFS), ep.REVIEW_COLUMNS), encoding="utf-8")
    usage = ev.evaluate(manifest=manifest, plan=plan, eval_dir=eval_dir, review_a=sheet, definitions=DEFS, repo_root=REPO_ROOT)["usage"]
    assert usage["finish_reasons"] == {"stop": len(calls)} and usage["max_tokens_values"] == [ep.LIVE_MAX_OUTPUT_TOKENS]
    assert usage["tokens"]["reasoning"] == 800 * len(calls) and usage["tokens"]["cache_miss_input"] == 1500 * len(calls)
    assert usage["cost_usd"]["with_provider_cache_split"] is not None and usage["model_names"]["returned_by_provider"] == {SERVED_NAME: len(calls)}
    # the prebuilt-prompt path records provider metadata per CALL; it writes no per-attempt entries (only the production path does)
    assert usage["calls_with_provider_metadata"] == len(calls) and usage["ledger_attempt_entries"] == 0


@needs_saved_runs
def test_live_stops_before_a_request_that_could_exceed_the_authorized_cost(tmp_path, real_manifest, live_env):
    probe = write_inputs(tmp_path / "probe", real_manifest, mode=ex.EVAL_MODE_LIVE)
    plan = json.loads(probe["plan"].read_text(encoding="utf-8"))
    first = plan["rounds"][0]["batches"][0]
    bound = ep.usd([0.30, 1.20], first["prompt_chars"] / TEST_REFERENCE["stance"]["chars_per_input_token"]["min"], ep.LIVE_MAX_OUTPUT_TOKENS)
    paths = write_inputs(tmp_path / "run", real_manifest, mode=ex.EVAL_MODE_LIVE, auth_edit=lambda a: a.update({"max_cost_usd": round(bound * 1.5, 6)}))
    bodies: list[dict[str, Any]] = []
    result = run(paths, mode=ex.EVAL_MODE_LIVE, _http_client_for_testing=_mock_client(bodies, completion_tokens=16000))
    assert result["stop"] == "COST_LIMIT" and len(bodies) == result["requests_sent"] == 1


@needs_saved_runs
def test_live_counts_a_sent_request_without_recorded_usage_at_its_hard_bound(tmp_path, real_manifest, live_env):
    probe = write_inputs(tmp_path / "probe", real_manifest, mode=ex.EVAL_MODE_LIVE)
    plan = json.loads(probe["plan"].read_text(encoding="utf-8"))
    bounds = [ep.usd([0.30, 1.20], b["prompt_chars"] / TEST_REFERENCE["stance"]["chars_per_input_token"]["min"], ep.LIVE_MAX_OUTPUT_TOKENS)
              for b in plan["rounds"][0]["batches"][:2]]
    limit = round(bounds[0] + bounds[1] * 0.9, 6)  # room for the second request only if the failed first one cost nothing
    paths = write_inputs(tmp_path / "run", real_manifest, mode=ex.EVAL_MODE_LIVE, auth_edit=lambda a: a.update({"max_cost_usd": limit}))
    bodies: list[dict[str, Any]] = []
    result = run(paths, mode=ex.EVAL_MODE_LIVE, _http_client_for_testing=_mock_client(bodies, fail_first_with=500))
    assert result["stop"] == "COST_LIMIT" and len(bodies) == result["requests_sent"] == 1  # an HTTP 500 is not retried either
    record = json.loads((Path(result["evaluation_dir"]) / ex.EVAL_RECORD_FILENAME).read_text(encoding="utf-8"))
    assert record["cost_usd_recorded_usage"]["unrecorded_requests_counted_at_hard_bound_usd"] == round(bounds[0], 4)


@needs_saved_runs
def test_live_refuses_another_configured_model_an_injected_provider_and_a_missing_cost_limit(tmp_path, real_manifest, live_env, monkeypatch):
    bodies: list[dict[str, Any]] = []
    paths = write_inputs(tmp_path / "a", real_manifest, mode=ex.EVAL_MODE_LIVE)
    monkeypatch.setenv("COMQUTOR_WEEK2_LLM_MODEL", "deepseek-v4-pro")
    assert run(paths, mode=ex.EVAL_MODE_LIVE, _http_client_for_testing=_mock_client(bodies))["error_code"] == "PROVIDER_MODEL_MISMATCH"
    monkeypatch.setenv("COMQUTOR_WEEK2_LLM_MODEL", ep.LIVE_MODEL)
    assert run(paths, mode=ex.EVAL_MODE_LIVE, provider=ScriptedProvider(simulated))["error_code"] == "LIVE_PROVIDER_INJECTION_REFUSED"
    assert nothing_written(paths)
    for change, code in (({"max_cost_usd": None}, "AUTHORIZATION_COST_LIMIT_MISSING"), ({"live_authorized": False}, "LIVE_NOT_AUTHORIZED"),
                         ({"model": "deepseek-v4-pro"}, "AUTHORIZATION_PROVIDER_MISMATCH")):
        paths = write_inputs(tmp_path / code, real_manifest, mode=ex.EVAL_MODE_LIVE, auth_edit=lambda a, c=change: a.update(c))
        assert run(paths, mode=ex.EVAL_MODE_LIVE, _http_client_for_testing=_mock_client(bodies))["error_code"] == code
        assert nothing_written(paths)
    assert bodies == []


def test_the_evaluation_hands_out_a_gateway_that_serves_only_the_relevance_task():
    calls: list[str] = []

    class Gateway:
        def invoke_prebuilt_json_prompt(self, *, task: str, **_kwargs: Any) -> str:
            calls.append(task)
            return "sent"

        def invoke_json(self, *_args: Any, **_kwargs: Any) -> None:  # pragma: no cover - must not be reachable
            calls.append("invoke_json")

    narrow = ex._RelevanceOnlyGateway(Gateway())  # noqa: SLF001
    assert narrow.invoke_prebuilt_json_prompt(task=rl.LLM_TASK_NAME, prompt="TEST DATA") == "sent"
    with pytest.raises(ex.EvaluationRefused, match="TASK_NOT_ALLOWED"):
        narrow.invoke_prebuilt_json_prompt(task="evidence_stance_classifier", prompt="TEST DATA")
    assert not hasattr(narrow, "invoke_json") and calls == [rl.LLM_TASK_NAME]


def test_the_operator_network_guard_allows_only_the_named_provider_host(monkeypatch):
    import importlib.util  # noqa: PLC0415

    spec = importlib.util.spec_from_file_location("relevance_cli", REPO_ROOT / "scripts" / "alpha_relevance_judgment.py")
    assert spec is not None and spec.loader is not None
    cli = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(cli)
    with cli.NetworkGuard(("api.provider.test",)) as guard:
        with pytest.raises(AssertionError, match="DNS lookup"):
            socket.getaddrinfo("example.org", 443)
        with socket.socket() as sock, pytest.raises(AssertionError, match="connect"):
            sock.connect(("192.0.2.1", 443))
    assert guard.attempts == ["getaddrinfo:example.org", "connect:192.0.2.1"]
    with cli.NetworkGuard() as closed, pytest.raises(AssertionError):
        httpx.Client().get("https://api.provider.test")
    assert closed.attempts and closed.attempts[0].startswith("httpx")


# ----------------------------------------------------------------------------------------------------------- evaluation (TEST DATA)
EVAL_TEXTS = [  # TEST DATA claims: written for the tests, never presented as saved claims
    ("TEST DATA: bookings accelerated sharply this quarter.", "A301"),
    ("TEST DATA: revenue grew 30% year over year.", "A301"),
    ("TEST DATA: margins held steady.", "A301"),
    ("TEST DATA: guidance was raised.", "A301"),
    ("TEST DATA: retail chatter about the stock is loud.", "A601"),
    ("TEST DATA: the theme broadened to small caps.", "A601"),
    ("TEST DATA: a new product was announced.", "A601"),
    ("TEST DATA: the Fed held rates.", "A001"),
]


def test_manifest() -> dict[str, Any]:
    samples = []
    for index, (text, alpha) in enumerate(EVAL_TEXTS, start=1):
        claim_id = f"TEST-DATA-run:test_agent:report:claim:{index}"
        samples.append({"sample_id": f"S{index:03d}", "source_run_id": "TEST-DATA-run", "source_alpha_matches_sha256": "0" * 64, "claim_id": claim_id,
                        "ticker": "NVDA" if index % 2 else "QQQ", "agent": "test_agent", "target_alpha_id": alpha, "claim_text": text,
                        "claim_text_sha256": rl.claim_text_sha256({"claim": text}), "alpha_definition_sha256": DEFS[alpha].sha256,
                        "selection": {"primary_stratum": ep.STRATUM_ORDINARY, "all_strata": [ep.STRATUM_ORDINARY], "features": {},
                                      "a9_fixture_id": None, "a9_disputed_id": None}})
    body = {"schema": ep.SAMPLE_SCHEMA, "test_data": True, "sample_count": len(samples), "samples": samples}
    return {**body, "content_sha256": sha256_canonical_json(body)}


test_manifest.__test__ = False  # a helper, not a test


def sheet(manifest: dict[str, Any], rows: dict[str, dict[str, str]], *, reviewer: str = "TEST-A", drop: tuple[str, ...] = (),
          extra: list[dict[str, str]] | None = None) -> str:
    base = {r["sample_id"]: r for r in ep.blind_review_rows(manifest, DEFS)}
    out = []
    for sid, row in base.items():
        if sid in drop:
            continue
        filled = dict(row)
        if sid in rows:
            filled.update({"review_status": ep.REVIEW_STATUS_CONFIRMED, "reviewer": reviewer, "reviewed_at": "2026-10-12", **rows[sid]})
        out.append(filled)
    return ep.render_csv(out + (extra or []), ep.REVIEW_COLUMNS)


@pytest.fixture
def scripted_execution(tmp_path, monkeypatch):
    """A rehearsal of a TEST DATA manifest with scripted answers (the source re-read is stubbed: these samples have no saved run)."""
    monkeypatch.setattr(ep, "verify_manifest_sources", lambda manifest: [])
    manifest = test_manifest()
    by_id = {s["sample_id"]: s for s in manifest["samples"]}
    seen: dict[str, int] = {}

    def responder(payload: dict[str, Any], _call: int) -> dict[str, Any]:
        items = []
        for request in payload["items"]:
            sid = next(k for k, s in by_id.items() if s["claim_id"] == request["claim_id"])
            seen[sid] = seen.get(sid, 0) + 1
            s = by_id[sid]
            items.extend({
                "S001": [answer(s, tier="core", anchors=[core_of("A301")])],
                "S002": [answer(s, tier="strong", anchors=[strong_of("A301")])],  # reference core -> core/strong confusion
                "S003": [answer(s, tier="none")],  # reference core -> wrong none
                "S004": [answer(s, outcome="UNRESOLVED", tier=None, unresolved="TEST DATA: cannot tell")],  # reference weak
                # S005: reference weak, flips between the two calls when it is repeated
                "S005": [answer(s, tier="weak" if seen[sid] == 1 else "none")],
                "S006": [answer(s, tier="moderate")],  # illegal label -> FAILED (contract)
                "S007": [answer(s, tier="weak")],  # reference UNRESOLVED
                "S008": [answer(s, tier="core", anchors=[core_of("A001")])],  # pending row: never a reference
            }[sid])
        return {"items": items}

    paths = write_inputs(tmp_path, manifest)
    result = run(paths, provider=ScriptedProvider(responder))
    assert result["status"] == "ok"
    plan = json.loads(paths["plan"].read_text(encoding="utf-8"))
    return manifest, plan, Path(result["evaluation_dir"]), tmp_path


REFERENCE_A = {
    "S001": {"outcome": "DETERMINED", "tier": "core", "anchor_element_ids": core_of("A301")},
    "S002": {"outcome": "DETERMINED", "tier": "core", "anchor_element_ids": core_of("A301")},
    "S003": {"outcome": "DETERMINED", "tier": "core", "anchor_element_ids": core_of("A301")},
    "S004": {"outcome": "DETERMINED", "tier": "weak"},
    "S005": {"outcome": "DETERMINED", "tier": "weak"},
    "S006": {"outcome": "DETERMINED", "tier": "none"},
    "S007": {"outcome": "UNRESOLVED", "ambiguity_note": "TEST DATA: two readings"},
}


def test_every_planned_pair_stays_in_the_totals_and_the_rates_are_reported_side_by_side(scripted_execution):
    manifest, plan, eval_dir, tmp = scripted_execution
    (tmp / "a.csv").write_text(sheet(manifest, REFERENCE_A), encoding="utf-8")
    report = ev.evaluate(manifest=manifest, plan=plan, eval_dir=eval_dir, review_a=tmp / "a.csv", definitions=DEFS, repo_root=REPO_ROOT)
    assert report["test_data"] is True and "TEST DATA" in report["banner"]
    t1 = report["totals"]["round_1"]
    assert t1["planned_pairs"] == 8 and sum(t1["outcomes"].values()) == 8
    assert t1["outcomes"] == {"core": 2, "strong": 1, "weak": 2, "none": 1, "UNRESOLVED": 1, "FAILED": 1, "NOT_SENT": 0}
    assert (t1["valid_return_rate"], t1["result_coverage"], t1["failure_rate"]) == (0.875, 0.75, 0.125)
    assert t1["failure_reasons"] == {rl.FAILURE_INVALID_LABEL: 1} and t1["contract_failures"] == 1
    r = report["reference"]
    assert r["reference_rows"]["CONFIRMED"] == 7 and r["reference_rows"]["PENDING"] == 1 and r["confirmed_determined"] == 6
    # S001 core=core, S005 weak=weak agree; S002 strong, S003 none, S004 UNRESOLVED, S006 FAILED do not
    assert (r["unconditional_agreement"]["count"], r["unconditional_agreement"]["n"]) == (2, 6)
    assert (r["coverage"]["count"], r["conditional_agreement"]["count"], r["conditional_agreement"]["n"]) == (4, 2, 4)
    assert r["unresolved_share_on_determined"]["count"] == 1 and r["failed_on_determined"] == 1
    assert r["confusion_matrix"]["cells"]["core"] == {"core": 1, "strong": 1, "weak": 0, "none": 1, "UNRESOLVED": 0, "FAILED": 0, "NOT_SENT": 0}
    assert r["confusion_matrix"]["cells"]["none"]["FAILED"] == 1
    assert [c["sample_id"] for c in r["core_strong_confusions"]] == ["S002"] and [c["sample_id"] for c in r["wrong_none"]] == ["S003"]
    assert r["none_on_core"] == {"count": 1, "n": 3} and [c["sample_id"] for c in r["on_confirmed_unresolved"]] == ["S007"]
    assert r["per_tier"]["core"] == {"reference_support": 3, "model_judged_as": 1, "agree": 1, "recall": 0.3333, "precision": 1.0}
    assert r["model_vs_reference_agreement"]["n"] == 6 and r["model_vs_reference_agreement"]["excluded_model_invalid"] == 1
    assert report["inter_annotator_agreement"]["status"] == "NOT_COMPUTED" and report["thresholds"]["status"] == "NOT_APPLIED"
    planned = sum(len(r["batches"]) for r in plan["rounds"])
    usage = report["usage"]
    assert usage["model_names"]["requested"] == {ex.SIMULATED_MODEL: planned} and usage["model_names"]["returned_by_provider"] == {"(no model field)": planned}
    assert usage["calls_with_provider_metadata"] == 0  # the simulated provider returns no response metadata
    assert "written only by the production Week 2 path" in ev.render_markdown(report)
    assert usage["requests_sent"] == usage["provider_attempts"] == usage["recorded_calls"] == planned and usage["retries"] == 0
    rows = {row["sample_id"]: row for row in report["samples"]}
    assert set(rows) == {s["sample_id"] for s in manifest["samples"]}
    assert rows["S008"]["reference_status"] == "PENDING" and rows["S008"]["reference_label"] == "" and rows["S008"]["agrees_with_reference"] == ""
    assert "TEST DATA" in ev.render_markdown(report)


def test_repeat_consistency_counts_a_flip_on_identical_input(scripted_execution):
    manifest, plan, eval_dir, tmp = scripted_execution
    (tmp / "a.csv").write_text(sheet(manifest, {}), encoding="utf-8")
    report = ev.evaluate(manifest=manifest, plan=plan, eval_dir=eval_dir, review_a=tmp / "a.csv", definitions=DEFS, repo_root=REPO_ROOT)
    subset = plan["requests"]["repeat_subset_samples"]
    rc = report["repeat_consistency"]
    assert rc["repeat_subset"] == len(subset) and rc["comparable"] == len(subset)
    flips = [f["sample_id"] for f in rc["flips"]]
    assert flips == (["S005"] if "S005" in subset else [])
    assert rc["identical_share_comparable"]["count"] == len(subset) - len(flips)


def test_review_sheets_never_fill_answers_and_flag_duplicates_missing_and_inconsistent_rows(scripted_execution):
    manifest, plan, eval_dir, tmp = scripted_execution
    rows = dict(REFERENCE_A)
    rows["S001"] = {"outcome": "DETERMINED", "tier": "core", "anchor_element_ids": ""}  # core without a core-owned anchor
    rows["S002"] = {"outcome": "DETERMINED", "tier": "strong", "anchor_element_ids": core_of("A301")}  # strong with a core-owned anchor
    rows["S004"] = {"outcome": "DETERMINED", "tier": "moderate"}
    rows["S007"] = {"outcome": "UNRESOLVED", "tier": "weak"}
    # filled in but not confirmed: never a reference, whatever it says
    rows["S008"] = {"outcome": "DETERMINED", "tier": "core", "anchor_element_ids": core_of("A001"), "review_status": "NEEDS_DISCUSSION"}
    duplicate = dict(ep.blind_review_rows(manifest, DEFS)[4], review_status="CONFIRMED", outcome="DETERMINED", tier="none")
    stranger = dict(ep.blind_review_rows(manifest, DEFS)[0], sample_id="S999")
    text = sheet(manifest, rows, extra=[duplicate, stranger])
    text = text.replace(EVAL_TEXTS[2][0], "TEST DATA: a different claim")  # the S003 row no longer shows its claim
    (tmp / "a.csv").write_text(text, encoding="utf-8")
    loaded = ev.load_review_sheet(tmp / "a.csv", manifest, DEFS)
    status = {sid: (row.status, row.problems) for sid, row in loaded.rows.items()}
    assert status["S001"] == ("INVALID", ["CORE_WITHOUT_CORE_OWNED_ANCHOR"]) and status["S002"] == ("INVALID", ["STRONG_ANCHORS_INCONSISTENT"])
    assert status["S003"] == ("INVALID", ["ROW_CONTENT_CHANGED"]) and status["S004"] == ("INVALID", ["TIER_INVALID"])
    assert status["S005"][0] == "INVALID" and status["S005"][1][0].startswith("DUPLICATE_ROW")
    assert status["S007"] == ("INVALID", ["TIER_ON_UNRESOLVED"]) and status["S008"] == ("NEEDS_DISCUSSION", [])
    assert {p["problem"] for p in loaded.problems} == {"DUPLICATE_ROW", "UNKNOWN_SAMPLE"}
    assert [sid for sid, row in loaded.rows.items() if row.label is not None] == ["S006"]  # the only usable confirmation left
    (tmp / "short.csv").write_text(sheet(manifest, REFERENCE_A, drop=("S008",)), encoding="utf-8")
    assert ev.load_review_sheet(tmp / "short.csv", manifest, DEFS).rows["S008"].status == "MISSING"
    # the engineering draft file is not a review sheet: nothing in it becomes a reference
    draft = ep.render_csv(ep.draft_label_rows(manifest, None), ["sample_id", "engineering_draft_tier", "draft_basis", "draft_source", "status"])
    (tmp / "draft.csv").write_text(draft, encoding="utf-8")
    as_sheet = ev.load_review_sheet(tmp / "draft.csv", manifest, DEFS)
    assert as_sheet.problems[0]["problem"] == "SHEET_COLUMNS_MISSING" and all(r.status == "MISSING" for r in as_sheet.rows.values())


def test_reviewer_agreement_needs_two_independent_sheets(scripted_execution):
    manifest, plan, eval_dir, tmp = scripted_execution
    (tmp / "a.csv").write_text(sheet(manifest, REFERENCE_A), encoding="utf-8")
    b_rows = {**REFERENCE_A, "S001": {"outcome": "DETERMINED", "tier": "weak"}}
    (tmp / "b.csv").write_text(sheet(manifest, b_rows, reviewer="TEST-B"), encoding="utf-8")
    (tmp / "b_same.csv").write_text(sheet(manifest, b_rows, reviewer="test-a"), encoding="utf-8")
    report = ev.evaluate(manifest=manifest, plan=plan, eval_dir=eval_dir, review_a=tmp / "a.csv", review_b=tmp / "b.csv", definitions=DEFS, repo_root=REPO_ROOT)
    iaa = report["inter_annotator_agreement"]
    assert iaa["status"] == "COMPUTED" and iaa["n_both_confirmed"] == 7 and iaa["disagreements"] == [{"sample_id": "S001", "reviewer_a": "core", "reviewer_b": "weak"}]
    assert iaa["agreement"] == round(6 / 7, 4)
    # reviewer B never changes the reference: the model metrics are identical with or without sheet B
    alone = ev.evaluate(manifest=manifest, plan=plan, eval_dir=eval_dir, review_a=tmp / "a.csv", definitions=DEFS, repo_root=REPO_ROOT)
    assert alone["reference"] == report["reference"]
    same = ev.evaluate(manifest=manifest, plan=plan, eval_dir=eval_dir, review_a=tmp / "a.csv", review_b=tmp / "b_same.csv", definitions=DEFS, repo_root=REPO_ROOT)
    assert same["inter_annotator_agreement"]["status"] == "NOT_INDEPENDENT"


def test_results_that_the_ledger_does_not_reproduce_are_failed_never_counted(scripted_execution):
    manifest, plan, eval_dir, tmp = scripted_execution
    round_dir = next(p for p in eval_dir.iterdir() if p.name.endswith("-r1"))
    path = round_dir / RESULTS_FILENAME
    payload = json.loads(path.read_text(encoding="utf-8"))
    by_claim = {r["claim_id"]: r for r in payload["records"]}
    s003 = by_claim["TEST-DATA-run:test_agent:report:claim:3"]
    s003.update({"state": rl.STATE_JUDGED, "tier": "core"})  # edited after the fact: the ledger says none
    payload["records"].append(dict(by_claim["TEST-DATA-run:test_agent:report:claim:1"]))  # a duplicate record for S001
    path.write_text(json.dumps(payload), encoding="utf-8")
    (tmp / "a.csv").write_text(sheet(manifest, REFERENCE_A), encoding="utf-8")
    report = ev.evaluate(manifest=manifest, plan=plan, eval_dir=eval_dir, review_a=tmp / "a.csv", definitions=DEFS, repo_root=REPO_ROOT)
    reasons = {c["sample_id"]: c["reason"] for c in report["totals"]["round_1"]["failed_cases"]}
    assert reasons["S003"] == "ledger_label_mismatch" and reasons["S001"] == "ledger_conflict"
    assert report["totals"]["round_1"]["failure_categories"]["read_time_verification"] == 2
    assert report["reference"]["unconditional_agreement"]["count"] == 1  # S001 no longer counts as agreeing


def test_not_sent_pairs_stay_in_every_denominator(tmp_path, monkeypatch):
    monkeypatch.setattr(ep, "verify_manifest_sources", lambda manifest: [])
    manifest = test_manifest()
    paths = write_inputs(tmp_path, manifest)
    result = run(paths, provider=ScriptedProvider(lambda payload, call: Refusal("TEST DATA: HTTP 429")))
    assert result["stop"] == "PROVIDER_REFUSAL" and result["requests_sent"] == 1
    plan = json.loads(paths["plan"].read_text(encoding="utf-8"))
    (tmp_path / "a.csv").write_text(sheet(manifest, REFERENCE_A), encoding="utf-8")
    report = ev.evaluate(manifest=manifest, plan=plan, eval_dir=result["evaluation_dir"], review_a=tmp_path / "a.csv", definitions=DEFS, repo_root=REPO_ROOT)
    t1 = report["totals"]["round_1"]
    first_batch = plan["rounds"][0]["batches"][0]["items"]
    assert t1["planned_pairs"] == 8 and t1["outcomes"]["FAILED"] == first_batch and t1["outcomes"]["NOT_SENT"] == 8 - first_batch
    assert t1["valid_return_rate"] == 0.0 and report["reference"]["unconditional_agreement"]["n"] == 6
    assert report["totals"]["round_2"]["outcomes"]["NOT_SENT"] == report["totals"]["round_2"]["planned_pairs"]
    assert report["repeat_consistency"]["comparable"] == 0


def test_thresholds_apply_only_when_confirmed_before_execution_and_never_on_test_data():
    plan = {"quality_thresholds": ep.PENDING_THRESHOLDS, "quality_thresholds_sha256": sha256_canonical_json(ep.PENDING_THRESHOLDS)}
    flat = {"round_1.valid_return_rate": (0.97, 60), "round_1.contract_failures": (3, 60), "reference.unresolved_share_on_determined": (0.1, 12),
            "reference.unconditional_agreement": (0.75, 40), "reference.none_on_core": (0, 15), "repeat.identical_share_valid_in_both": (0.95, 38)}
    confirmed = {"test_data": False, "authorization": {"quality_thresholds_confirmed": True, "quality_thresholds_sha256": plan["quality_thresholds_sha256"]}}
    verdicts = {t["id"]: t["verdict"] for t in ev.apply_thresholds(plan, confirmed, flat)["results"]}
    assert verdicts == {"Q1": "PASS", "Q2": "FAIL", "Q3": "NOT_EVALUABLE", "Q4": "PASS", "Q5": "PASS", "Q6": "PASS", "Q7": "REPORTED"}
    assert ev.apply_thresholds(plan, {**confirmed, "test_data": True}, flat)["status"] == "NOT_APPLIED"
    # the same thresholds hash, only the confirmation flag differs: without it nothing is applied
    unconfirmed = {"test_data": False, "authorization": {"quality_thresholds_confirmed": False, "quality_thresholds_sha256": plan["quality_thresholds_sha256"]}}
    assert ev.apply_thresholds(plan, unconfirmed, flat)["status"] == "NOT_APPLIED"
    other_hash = {"test_data": False, "authorization": {"quality_thresholds_confirmed": True, "quality_thresholds_sha256": "0" * 64}}
    assert ev.apply_thresholds(plan, other_hash, flat)["status"] == "NOT_APPLIED"
    edited = {**plan, "quality_thresholds": {**ep.PENDING_THRESHOLDS, "rule": "changed after the results"}}
    assert ev.apply_thresholds(edited, confirmed, flat)["status"] == "NOT_APPLIED"


def test_statistics_helpers():
    full, interval = ev.wilson_interval(10, 10), ev.wilson_interval(7, 10)
    assert ev.wilson_interval(0, 0) is None and full is not None and full[1] == 1.0
    assert interval is not None and (round(interval[0], 3), round(interval[1], 3)) == (0.397, 0.892)
    assert ev.cohen_kappa([("a", "a"), ("b", "b")]) == 1.0 and ev.cohen_kappa([("a", "a")]) is None and ev.cohen_kappa([]) is None
    assert ev.cohen_kappa([("a", "a"), ("a", "b"), ("b", "a"), ("b", "b")]) == 0.0


def test_the_per_sample_csv_round_trips_every_sample(scripted_execution):
    manifest, plan, eval_dir, tmp = scripted_execution
    (tmp / "a.csv").write_text(sheet(manifest, REFERENCE_A), encoding="utf-8")
    report = ev.evaluate(manifest=manifest, plan=plan, eval_dir=eval_dir, review_a=tmp / "a.csv", definitions=DEFS, repo_root=REPO_ROOT)
    text = ep.render_csv(report["samples"], ev.SAMPLE_TABLE_COLUMNS)
    rows = list(csv.DictReader(io.StringIO(text.lstrip("﻿"))))
    assert [r["sample_id"] for r in rows] == [s["sample_id"] for s in manifest["samples"]]
