"""T4 round 28 (2026-10-08): the run-scoped stop after a provider HTTP 401 / 403 / 429.

Zero provider calls. Real LangChain/OpenAI-compatible clients, the real Week2LLMGateway (built by the production
builder, with its AuditingTransport), the real research pipeline and task scheduling (run_research_request), a real
LangGraph research stage with the real budget guard and the real TradingAgents structured-output fallback helper --
only the bottom HTTP transport is replaced by an httpx.MockTransport. Fixed responses prove engineering behavior, not
model quality.
"""

from __future__ import annotations

import hashlib
import json
import os
import threading
import time
import uuid
from collections import Counter
from pathlib import Path

import httpx
import pytest

from comqutor_alpha.run_provider_stop import (
    ARTIFACT_FILENAME,
    STOP_ERROR_CODE,
    redact_reason,
    release_run_provider_stop,
    run_provider_stop,
)

REPO = Path(__file__).resolve().parents[1]
SOURCE_RUN = REPO / "outputs" / "runs" / "034a0a60-430e-41f8-8321-03a11389707a"
COPIED = ("raw_agent_outputs.json", "source_registry.json", "market_data_snapshot.json", "derived_inputs.json", "provider_response_audit.json")
SECRET_IN_BODY = "sk-testsecret0123456789abcdef"
needs_source = pytest.mark.skipif(not (SOURCE_RUN / "raw_agent_outputs.json").is_file(), reason="saved NVDA run 034a0a60 not present")

WEEK2_TASKS = ("claim_batch_enrichment", "alpha_classifier", "content_support_verification", "evidence_stance_classifier", "structure_extractor")


def _completion(content: object) -> httpx.Response:
    return httpx.Response(200, json={"id": f"mock-{uuid.uuid4()}", "object": "chat.completion", "created": 0, "model": "deepseek-flash",
                                     "choices": [{"index": 0, "message": {"role": "assistant", "content": json.dumps(content)}, "finish_reason": "stop"}],
                                     "usage": {"prompt_tokens": 100, "completion_tokens": 10, "total_tokens": 110,
                                               "prompt_cache_hit_tokens": 60, "prompt_cache_miss_tokens": 40}})


def _refusal(status_code: int) -> httpx.Response:
    message = {401: f"Authentication Fails, Your api key: {SECRET_IN_BODY} is invalid",
               403: f"Permission denied for key {SECRET_IN_BODY}",
               429: "Rate limit reached for requests"}[status_code]
    return httpx.Response(status_code, json={"error": {"message": message, "type": "refusal", "code": status_code}})


def _default_week2_response(task: str, payload: dict) -> httpx.Response:
    if task == "alpha_classifier":
        claim = str(payload.get("claim") or "")
        select = int(hashlib.sha256(claim.encode()).hexdigest(), 16) % 2 == 0
        return _completion({"decision": "select", "selected_alpha_id": "A304"} if select else {"decision": "none", "selected_alpha_id": None})
    if task == "claim_batch_enrichment":
        return _completion({"claims": [{"segment_id": s["segment_id"], "claim": s["claim"], "evidence": s["evidence"], "source_section": s["source_section"],
                                        "entities": [], "factors": [], "direction": "unknown", "confidence": 0.0} for s in payload.get("segments", [])]})
    if task == "content_support_verification":
        items = []
        for item in payload.get("items", []):
            candidate = item["allowed_candidates"][0]
            items.append({"claim_id": item["claim_id"], "core_proposition": "mock", "status": "SUPPORTS", "support_basis": "DIRECT_FACT",
                          "used_source_id": candidate["source_id"], "used_location": "excerpt",
                          "supporting_quote_or_data": (candidate.get("excerpt") or "")[:30], "inference_facts": [], "inference_assumptions": [],
                          "rationale": "mock", "supported_proposition": item["proposition"], "unsupported_remainder": "",
                          "unsupported_remainder_materiality": "NONE"})
        return _completion({"items": items})
    if task == "evidence_stance_classifier":
        return _completion({"items": [{"claim_id": i["claim_id"], "target_alpha_id": i["target_alpha_id"], "stance": "supports_alpha", "counter_alpha_id": None}
                                      for i in payload.get("items", [])]})
    if task == "structure_extractor":
        return _completion({"edges": []})
    return httpx.Response(400, json={"error": {"message": "mock: unrecognized task"}})


class MockWeek2Provider:
    """Answers the Week 2 tasks at the bottom transport; ``plan(provider, task, index, payload)`` may return a response
    (else the default). Records every arrival, and whether the run was already stopped when it arrived."""

    def __init__(self, plan=None) -> None:
        from comqutor_alpha.structure_engine.week2_llm import Week2LLMGateway

        self.prefixes = {t: Week2LLMGateway._provider_prompt_prefix(t) for t in WEEK2_TASKS}
        self.plan = plan or (lambda *_: None)
        self.lock = threading.Lock()
        self.seen: list[dict] = []
        self.count: Counter = Counter()
        self.run_id: str | None = None

    def stop_state(self):
        return run_provider_stop(self.run_id).triggered if self.run_id else None

    def handler(self, request: httpx.Request) -> httpx.Response:
        body = json.loads(request.content)
        content = body["messages"][0]["content"]
        task = next((t for t, p in self.prefixes.items() if content.startswith(p)), "UNKNOWN_TASK")
        payload = json.loads(content[len(self.prefixes[task]):]) if task != "UNKNOWN_TASK" else {}
        stopped = self.stop_state() is not None
        with self.lock:
            self.count[task] += 1
            index = self.count[task]
            self.seen.append({"task": task, "index": index, "arrived_while_stopped": stopped,
                              "retry_header": request.headers.get("x-stainless-retry-count"), "claim": payload.get("claim")})
        return self.plan(self, task, index, payload) or _default_week2_response(task, payload)


@pytest.fixture
def week2_env(monkeypatch, tmp_path):
    for name in list(os.environ):
        if name.startswith(("COMQUTOR_WEEK2_", "COMQUTOR_RESEARCH_AGENT_")):
            monkeypatch.delenv(name, raising=False)
    monkeypatch.setenv("COMQUTOR_WEEK2_LLM_ENABLED", "true")
    monkeypatch.setenv("COMQUTOR_WEEK2_LLM_PROVIDER", "deepseek")
    monkeypatch.setenv("COMQUTOR_WEEK2_LLM_MODEL", "deepseek-v4-flash")
    monkeypatch.setenv("COMQUTOR_WEEK2_LLM_TIMEOUT_SECONDS", "45")
    monkeypatch.setenv("COMQUTOR_WEEK2_LLM_MAX_RETRIES", "0")
    monkeypatch.setenv("COMQUTOR_WEEK2_LLM_PROFILE", "t3_verified_20261008")
    monkeypatch.setenv("COMQUTOR_WEEK2_LLM_MAX_CALLS", "200")
    monkeypatch.setenv("DEEPSEEK_API_KEY", "mock-not-a-key")
    from comqutor_alpha.storage.db.engine import build_engine
    from comqutor_alpha.storage.db.repository import GraphPersistenceRepository

    repository = GraphPersistenceRepository(build_engine(f"sqlite:///{tmp_path / 'r28.sqlite'}"))
    repository.ensure_schema()
    return {"repository": repository, "output_root": tmp_path / "runs"}


def _install(monkeypatch, provider: MockWeek2Provider) -> None:
    monkeypatch.setattr(httpx, "HTTPTransport", lambda *a, **k: httpx.MockTransport(provider.handler))


def _runner(provider: MockWeek2Provider, label: str, agents=("trader",)):
    from comqutor_alpha.classification_recovery import rebase_run_id

    def runner(payload, output_root):
        run_id = f"r28-{label}-{uuid.uuid4().hex[:8]}"
        provider.run_id = run_id
        run_dir = Path(output_root) / run_id
        run_dir.mkdir(parents=True)
        for name in COPIED:
            if (SOURCE_RUN / name).is_file():
                data = rebase_run_id(json.loads((SOURCE_RUN / name).read_text(encoding="utf-8")), base_run_id=SOURCE_RUN.name, execution_id=run_id)
                if name == "raw_agent_outputs.json":
                    data["agent_outputs"] = [o for o in data["agent_outputs"] if o.get("agent") in agents]
                (run_dir / name).write_text(json.dumps(data, ensure_ascii=False), encoding="utf-8")
        source_meta = json.loads((SOURCE_RUN / "metadata.json").read_text(encoding="utf-8"))
        metadata = {**{k: source_meta[k] for k in ("ticker", "analysis_date", "llm_provider", "quick_model", "deep_model") if k in source_meta},
                    "run_id": run_id, "selected_analysts": list(agents), "output_version": "week1a.v1", "source": "round 28 test (saved trader output)"}
        (run_dir / "metadata.json").write_text(json.dumps(metadata), encoding="utf-8")
        return str(run_dir)

    return runner


def _run(week2_env, provider, label):
    from comqutor_alpha.api.routes_research import run_research_request

    response = run_research_request({"ticker": "NVDA"}, runner=_runner(provider, label), output_root=str(week2_env["output_root"]),
                                    graph_repository=week2_env["repository"])
    return response, week2_env["output_root"] / response["run_id"]


def _jsonl(path: Path) -> list[dict]:
    return [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines() if line.strip()] if path.is_file() else []


def _wait(predicate, timeout=10.0) -> bool:
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        if predicate():
            return True
        time.sleep(0.01)
    return predicate()


# ---------------------------------------------------------------------------
# Week 2 layer: a refusal with requests in flight and requests queued
# ---------------------------------------------------------------------------


def _alpha_refusal_plan(status_code: int):
    def plan(provider, task, index, payload):
        if task != "alpha_classifier":
            return None
        if index == 1:
            # wait until the other concurrent workers' requests are on the wire, then refuse
            _wait(lambda: provider.count["alpha_classifier"] >= 4, timeout=2.0)
            return _refusal(status_code)
        if index <= 4:
            # in flight when the refusal arrives: answered only after the run is stopped
            assert _wait(lambda: provider.stop_state() is not None), "the stop was never triggered"
            return None
        return None

    return plan


@needs_source
@pytest.mark.parametrize("status_code", [401, 403, 429])
def test_week2_refusal_stops_the_run_keeps_in_flight_answers_and_refuses_queued_requests(week2_env, monkeypatch, status_code):
    provider = MockWeek2Provider(_alpha_refusal_plan(status_code))
    _install(monkeypatch, provider)
    response, run_dir = _run(week2_env, provider, f"w2-{status_code}")

    stop = json.loads((run_dir / ARTIFACT_FILENAME).read_text(encoding="utf-8"))
    trigger = stop["trigger"]
    assert stop["stopped"] is True and trigger["status_code"] == status_code
    assert trigger["layer"] == "week2_semantic" and trigger["task"] == "alpha_classifier" and trigger["attempt_id"] and trigger["call_id"]
    assert SECRET_IN_BODY not in json.dumps(stop) and "[REDACTED]" in (trigger["reason_redacted"] or "") or status_code == 429

    # no request reached the transport once the run was stopped; nothing was retried
    assert [s for s in provider.seen if s["arrived_while_stopped"]] == []
    assert {s["retry_header"] for s in provider.seen} == {"0"}
    alpha_sent = provider.count["alpha_classifier"]
    assert 1 <= alpha_sent <= 4

    matches = json.loads((run_dir / "alpha_matches.json").read_text(encoding="utf-8"))["matches"]
    reasons = Counter(m.get("alpha_match_fallback_reason") for m in matches)
    expected_failure = "provider_rate_limited" if status_code == 429 else "provider_error"
    assert reasons[expected_failure] == 1
    in_flight_answered = len(stop["answered_after_stop_in_flight"])
    assert in_flight_answered == alpha_sent - 1
    valid = [m for m in matches if m.get("alpha_match_method") == "llm" and m.get("alpha_match_fallback_reason") is None]
    assert len(valid) == in_flight_answered
    refused = [m for m in matches if m.get("alpha_match_fallback_reason") == "provider_stopped"]
    assert len(refused) == len(matches) - alpha_sent
    # failed and refused claims are never a valid NONE
    assert all(m.get("alpha_match_method") != "llm" and not m.get("matched_alpha") for m in refused)

    # identity: each in-flight answer belongs to its own claim (audit request claim_ids == the valid alpha record)
    audit_requests = {r["attempt_id"]: r for r in _jsonl(run_dir / "error_logs" / "week2_llm_provider_request_audit.jsonl")}
    answered_claims = {tuple(audit_requests[a["attempt_id"]]["claim_ids"]) for a in stop["answered_after_stop_in_flight"]}
    assert answered_claims == {(m["claim_id"],) for m in valid}
    assert tuple(audit_requests[trigger["attempt_id"]]["claim_ids"]) in {(m["claim_id"],) for m in matches if m.get("alpha_match_fallback_reason") == expected_failure}

    # ledger: refused calls are not_called with the stop code and no attempt; no later stage sent anything
    ledger = _jsonl(run_dir / "llm_semantic_calls.jsonl")
    refused_ledger = [r for r in ledger if r.get("error_code") == STOP_ERROR_CODE]
    assert refused_ledger and all(r["provider_status"] == "not_called" and not r.get("request_attempts") for r in refused_ledger)
    assert provider.count["evidence_stance_classifier"] == 0 and provider.count["structure_extractor"] == 0
    assert stop["refused_before_send_total"] >= len(refused)

    from comqutor_alpha.structure_engine.alpha_mapper import compute_alpha_classification_completion

    completion = compute_alpha_classification_completion({"matches": matches})
    assert completion["call_failure_count"] == 1 and completion["not_executed_fault_count"] == len(refused) and completion["complete"] is False
    assert response["status"] == "partial" and response["provider_stop"]["stopped"] is True
    assert response["provider_stop"]["trigger"]["status_code"] == status_code
    # the response reads the final record (written before the manifest), and the Export manifest hash matches the file
    assert response["provider_stop"]["refused_before_send_total"] == stop["refused_before_send_total"] >= len(refused)
    manifest = json.loads((run_dir / "artifact_manifest.json").read_text(encoding="utf-8"))
    listed = json.dumps(manifest)
    assert ARTIFACT_FILENAME in listed
    import hashlib as _h

    assert _h.sha256((run_dir / ARTIFACT_FILENAME).read_bytes()).hexdigest() in listed

    usage = json.loads((run_dir / "llm_usage_report.json").read_text(encoding="utf-8"))
    assert usage["totals"]["week2_semantic"]["not_sent_reasons"].get(STOP_ERROR_CODE, 0) == len(refused_ledger)


# ---------------------------------------------------------------------------
# Research-agent layer through the real streaming path
# ---------------------------------------------------------------------------


class _ResearchAgentProvider:
    def __init__(self, refuse_on: int, status_code: int) -> None:
        self.refuse_on, self.status_code = refuse_on, status_code
        self.requests = 0
        self.lock = threading.Lock()

    def handler(self, request: httpx.Request) -> httpx.Response:
        with self.lock:
            self.requests += 1
            n = self.requests
        if n == self.refuse_on:
            return _refusal(self.status_code)
        return httpx.Response(200, json={"id": f"ra-{n}", "object": "chat.completion", "created": 0, "model": "deepseek-flash",
                                         "choices": [{"index": 0, "message": {"role": "assistant", "content": f"report {n}"}, "finish_reason": "stop"}],
                                         "usage": {"prompt_tokens": 50, "completion_tokens": 5, "total_tokens": 55}})


def _mini_graph_factory(provider: _ResearchAgentProvider):
    """A real LangGraph over real OpenAI-compatible clients (tradingagents create_llm_client, the same factory the real
    graph uses): Market Analyst (plain call) -> Research Manager (the real TradingAgents structured-output helper,
    which falls back to a second plain call when the structured call fails) -> Portfolio Manager."""
    from typing import TypedDict

    from langgraph.graph import END, START, StateGraph
    from pydantic import BaseModel

    from tradingagents.agents.utils.structured import bind_structured, invoke_structured_or_freetext
    from tradingagents.llm_clients import create_llm_client

    class Plan(BaseModel):
        recommendation: str

    class State(TypedDict, total=False):
        market_report: str
        investment_plan: str
        final_trade_decision: str

    def factory(internal_analysts, config):
        def client():
            return create_llm_client(provider="deepseek", model="deepseek-v4-flash", base_url=None, timeout=45, max_retries=config.get("max_retries", 0),
                                     http_client=httpx.Client(transport=httpx.MockTransport(provider.handler))).get_llm()

        class Graph:
            pass

        graph = Graph()
        graph.quick_thinking_llm = client()
        graph.deep_thinking_llm = client()
        structured = bind_structured(graph.deep_thinking_llm, Plan, "Research Manager")

        def market(state):
            return {"market_report": graph.quick_thinking_llm.invoke("market").content}

        def manager(state):
            return {"investment_plan": invoke_structured_or_freetext(structured, graph.deep_thinking_llm, "plan", lambda r: r.recommendation, "Research Manager")}

        def portfolio(state):
            return {"final_trade_decision": graph.deep_thinking_llm.invoke("decide").content}

        workflow = StateGraph(State)
        workflow.add_node("Market Analyst", market)
        workflow.add_node("Research Manager", manager)
        workflow.add_node("Portfolio Manager", portfolio)
        workflow.add_edge(START, "Market Analyst")
        workflow.add_edge("Market Analyst", "Research Manager")
        workflow.add_edge("Research Manager", "Portfolio Manager")
        workflow.add_edge("Portfolio Manager", END)
        graph.graph = workflow.compile()

        class Propagator:
            @staticmethod
            def create_initial_state(ticker, date, **_):
                return {}

            @staticmethod
            def get_graph_args():
                return {"stream_mode": "values", "config": {}}

        graph.propagator = Propagator()
        return graph

    return factory


@pytest.mark.parametrize("status_code", [401, 403, 429])
def test_research_agent_refusal_stops_the_fallback_request_and_the_week2_layer(week2_env, monkeypatch, status_code):
    from comqutor_alpha.api.routes_research import run_research_request
    from comqutor_alpha.runners import tradingagents_runner

    ra = _ResearchAgentProvider(refuse_on=2, status_code=status_code)  # 2nd request = Research Manager's structured call
    week2 = MockWeek2Provider()
    _install(monkeypatch, week2)
    monkeypatch.setattr(tradingagents_runner, "_default_streaming_graph_factory", _mini_graph_factory(ra))
    run_id = f"r28-ra-{status_code}-{uuid.uuid4().hex[:6]}"
    week2.run_id = run_id
    payload = {"ticker": "NVDA", "analysis_date": "2026-10-08", "asset_type": "stock", "selected_analysts": ["market"], "run_id": run_id,
               "allow_real_tradingagents_run": True, "config": {"checkpoint_enabled": False}, "research_agent_max_actual_requests": 10,
               "research_agent_max_retries": 0}
    response = run_research_request(payload, output_root=str(week2_env["output_root"]), graph_repository=week2_env["repository"])

    assert response["status"] == "failed" and response["error_code"] == "PROVIDER_REFUSED_RUN_STOPPED"
    assert ra.requests == 2, "the structured call was refused; its free-text fallback must not be sent"
    assert sum(week2.count.values()) == 0, "the Week 2 layer sent nothing"
    stop = json.loads((week2_env["output_root"] / run_id / ARTIFACT_FILENAME).read_text(encoding="utf-8"))
    assert stop["trigger"]["status_code"] == status_code and stop["trigger"]["layer"] == "research_agent"
    assert stop["trigger"]["task"] == "Research Manager"
    assert stop["refused_before_send"] == {"research_agent:Research Manager": 1}
    assert SECRET_IN_BODY not in json.dumps(stop)
    assert (week2_env["output_root"] / run_id / "tradingagents_llm_calls.jsonl").is_file()


# ---------------------------------------------------------------------------
# One shared stop per run; other runs unaffected; no lock across the network wait
# ---------------------------------------------------------------------------


def _alpha_validator(value):
    return value


def _gateway(run_id, output_root, handler):
    """The production builder plus the research pipeline's own attach step (routes_research.attach_run_provider_stop)."""
    from comqutor_alpha.api.routes_research import attach_run_provider_stop
    from comqutor_alpha.structure_engine.week2_llm import build_server_week2_llm_gateway

    gateway = build_server_week2_llm_gateway(run_id, output_root, _base_transport_for_testing=httpx.MockTransport(handler))
    assert gateway is not None and gateway.provider_stop is None  # the builder alone attaches nothing (recovery / evaluation drivers)
    attach_run_provider_stop(gateway, run_id, Path(output_root) / run_id)
    assert gateway.provider_stop is run_provider_stop(run_id)
    return gateway


def test_a_stop_set_by_the_research_layer_is_honored_by_the_week2_gateway_of_the_same_run_only(week2_env, tmp_path):
    from comqutor_alpha.runners.request_budget import RequestBudgetGuard

    sent: Counter = Counter()
    lock = threading.Lock()
    barrier = threading.Barrier(4, timeout=10)

    def handler(request):
        payload = json.loads(request.content)["messages"][0]["content"]
        with lock:
            sent["B" if "run-B" in payload else "A"] += 1
        if "run-B" in payload:
            barrier.wait()  # all four of run B's requests are on the wire at once: no lock is held across the network wait
        return _completion({"decision": "none", "selected_alpha_id": None})

    run_a, run_b = f"r28-shared-A-{uuid.uuid4().hex[:6]}", f"r28-shared-B-{uuid.uuid4().hex[:6]}"
    try:
        guard = RequestBudgetGuard(10, provider_stop=run_provider_stop(run_a))
        gateway_a, gateway_b = _gateway(run_a, tmp_path, handler), _gateway(run_b, tmp_path, handler)
        assert guard.provider_stop is gateway_a.provider_stop and gateway_a.provider_stop is not gateway_b.provider_stop
        run_provider_stop(run_a).trigger(status_code=429, layer="research_agent", task="News Analyst", reason="rate limited")

        invocation = gateway_a.invoke_json_with_trace("alpha_classifier", {"claim": "run-A claim"}, _alpha_validator, claim_ids=("a1",))
        assert invocation.provider_status == "not_called" and invocation.error_code == STOP_ERROR_CODE and not invocation.provider_called
        from comqutor_alpha.run_provider_stop import RunProviderStopped

        with pytest.raises(RunProviderStopped):
            guard.reserve(task="Bull Researcher")

        results = []
        threads = [threading.Thread(target=lambda i=i: results.append(gateway_b.invoke_json_with_trace(
            "alpha_classifier", {"claim": f"run-B claim {i}"}, _alpha_validator, claim_ids=(f"b{i}",)))) for i in range(4)]
        for t in threads:
            t.start()
        for t in threads:
            t.join(timeout=20)
        assert sent == {"B": 4} and all(r.provider_status == "success" for r in results)
        assert guard.actual_requests_made == 0
        snapshot = run_provider_stop(run_a).snapshot()
        assert snapshot["refused_before_send"] == {"research_agent:Bull Researcher": 1, "week2_semantic:alpha_classifier": 1}
        assert (tmp_path / run_a / ARTIFACT_FILENAME).is_file() and not (tmp_path / run_b / ARTIFACT_FILENAME).exists()
    finally:
        release_run_provider_stop(run_a)
        release_run_provider_stop(run_b)


def test_the_transport_hook_refuses_a_request_that_passed_the_gateway_check_before_the_stop(week2_env, tmp_path):
    """The race the last check exists for: the gateway loop's check passed, then another request stopped the run
    before this one was forwarded -- AuditingTransport's request hook refuses it, it is recorded as not sent."""
    from comqutor_alpha.structure_engine import week2_llm

    sent = []
    run_id = f"r28-hook-{uuid.uuid4().hex[:6]}"
    try:
        gateway = _gateway(run_id, tmp_path, lambda request: sent.append(1) or _completion({"decision": "none", "selected_alpha_id": None}))
        original = week2_llm.Week2LLMGateway._provider_stop_refusal
        calls = {"n": 0}

        def check_then_stop(self, task):
            calls["n"] += 1
            result = original(self, task)
            if calls["n"] == 1:  # the loop check passes ... and only then the run is stopped
                run_provider_stop(run_id).trigger(status_code=401, layer="week2_semantic", task="content_support_verification", attempt_id="x")
            return result

        week2_llm.Week2LLMGateway._provider_stop_refusal = check_then_stop
        try:
            invocation = gateway.invoke_json_with_trace("alpha_classifier", {"claim": "c"}, _alpha_validator, claim_ids=("c1",))
        finally:
            week2_llm.Week2LLMGateway._provider_stop_refusal = original
        assert sent == [] and calls["n"] == 2
        assert invocation.provider_status == "not_called" and invocation.error_code == STOP_ERROR_CODE and not invocation.provider_called
        assert gateway.audit_write_failed is False  # a stop refusal is not an audit failure
    finally:
        release_run_provider_stop(run_id)


def test_prebuilt_and_legacy_gateway_paths_also_check_the_stop():
    from comqutor_alpha.structure_engine.week2_llm import Week2LLMGateway

    class _Model:
        calls = 0

        def invoke(self, prompt):
            _Model.calls += 1
            raise AssertionError("must not be sent")

    run_id = f"r28-paths-{uuid.uuid4().hex[:6]}"
    try:
        gateway = Week2LLMGateway(_Model(), run_id=run_id, output_root="/nonexistent-never-written", max_calls=5)
        gateway.provider_stop = run_provider_stop(run_id)
        gateway.provider_stop.trigger(status_code=403, layer="week2_semantic", task="alpha_classifier")
        gateway._log = lambda *a, **k: None
        assert gateway._invoke_json_legacy("alpha_classifier", {"claim": "x"}, _alpha_validator) is None
        prebuilt = gateway.invoke_prebuilt_json_prompt(
            task="alpha_classifier", prompt="p", prompt_version="v", prompt_sha256="0" * 64, input_schema_version="i",
            output_schema_version="o", payload_for_identity={"claim": "x"}, validator=_alpha_validator)
        assert prebuilt.provider_status == "not_called" and prebuilt.error_code == STOP_ERROR_CODE and not prebuilt.provider_called
        assert _Model.calls == 0 and gateway.call_count == 0
    finally:
        release_run_provider_stop(run_id)


# ---------------------------------------------------------------------------
# Unchanged behavior: success path, budget guard, audit, zero retries
# ---------------------------------------------------------------------------


@needs_source
def test_success_path_has_no_stop_record_and_keeps_audit_budget_and_zero_retries(week2_env, monkeypatch):
    provider = MockWeek2Provider()
    _install(monkeypatch, provider)
    response, run_dir = _run(week2_env, provider, "ok")
    assert not (run_dir / ARTIFACT_FILENAME).exists() and response["provider_stop"] is None
    assert response["status"] in {"completed", "partial"}
    ledger = _jsonl(run_dir / "llm_semantic_calls.jsonl")
    assert not [r for r in ledger if r.get("error_code") == STOP_ERROR_CODE]
    audit = _jsonl(run_dir / "error_logs" / "week2_llm_provider_request_audit.jsonl")
    assert len(audit) == len(provider.seen) and len({r["attempt_id"] for r in audit}) == len(audit)
    assert {s["retry_header"] for s in provider.seen} == {"0"}
    from comqutor_alpha.structure_engine.alpha_mapper import compute_alpha_classification_completion

    matches = json.loads((run_dir / "alpha_matches.json").read_text(encoding="utf-8"))["matches"]
    assert compute_alpha_classification_completion({"matches": matches})["complete"] is True
    # the 200 cap counts gateway reservations; reported next to the HTTP requests the wire audit saw
    budget = json.loads((run_dir / "week2_gateway_budget.json").read_text(encoding="utf-8"))
    assert budget["max_calls"] == 200 and budget["budget_reservations"] == len(provider.seen)
    accounting = json.loads((run_dir / "llm_usage_report.json").read_text(encoding="utf-8"))["week2_cap_accounting"]
    assert accounting["cap"] == 200 and accounting["gateway_budget_reservations"] == len(provider.seen)
    assert accounting["http_requests_forwarded_per_wire_audit"] == len(audit) == len(provider.seen)


@needs_source
def test_budget_guard_still_refuses_unsent_and_is_not_reported_as_a_provider_stop(week2_env, monkeypatch):
    monkeypatch.setenv("COMQUTOR_WEEK2_LLM_MAX_CALLS", "3")
    provider = MockWeek2Provider()
    _install(monkeypatch, provider)
    response, run_dir = _run(week2_env, provider, "budget")
    assert sum(provider.count.values()) == 3
    ledger = _jsonl(run_dir / "llm_semantic_calls.jsonl")
    assert [r for r in ledger if r.get("provider_status") == "budget_exhausted"]
    assert not [r for r in ledger if r.get("error_code") == STOP_ERROR_CODE]
    assert not (run_dir / ARTIFACT_FILENAME).exists() and response["status"] == "partial"


def test_redaction_removes_keys_and_bearer_tokens():
    text = "Authentication Fails, Your api key: sk-abcdef1234567890 is invalid; Authorization: Bearer abc.def-123; api_key=XYZ987"
    redacted = redact_reason(text)
    assert "sk-abcdef1234567890" not in redacted and "abc.def-123" not in redacted and "XYZ987" not in redacted
    assert redacted.count("[REDACTED]") >= 3


# ---------------------------------------------------------------------------
# Timeout preservation: every finished call is on disk before the next stage starts
# ---------------------------------------------------------------------------


@needs_source
def test_each_finished_call_is_persisted_before_the_next_stage_sends_anything(week2_env, monkeypatch):
    """What a worker termination at any later moment would still find: when the first Alpha request reaches the
    transport, every content-support result is already a ledger line; when the first stance request arrives, every
    Alpha result is. A ledger line carries the task, call id, claim ids, input hash and the validated output with its
    own hash (comqutor_alpha.llm_runtime.session.finalize_call, appended per call)."""
    snapshots: dict[str, list[dict]] = {}

    def plan(provider, task, index, payload):
        if index == 1 and task in ("alpha_classifier", "evidence_stance_classifier"):
            snapshots[task] = _jsonl(week2_env["output_root"] / provider.run_id / "llm_semantic_calls.jsonl")
        return None

    provider = MockWeek2Provider(plan)
    _install(monkeypatch, provider)
    response, run_dir = _run(week2_env, provider, "persist")
    from comqutor_alpha.llm_runtime.canonical_json import sha256_canonical_json

    at_alpha = snapshots["alpha_classifier"]
    cs_on_disk = [r for r in at_alpha if r["task"] == "content_support_verification"]
    assert len(cs_on_disk) == provider.count["content_support_verification"] >= 1
    assert all(r["validated_output"] is not None and sha256_canonical_json(r["validated_output"]) == r["validated_output_sha256"]
               and r.get("claim_ids") and r.get("input_sha256") for r in cs_on_disk)
    if "evidence_stance_classifier" in snapshots:
        alpha_on_disk = [r for r in snapshots["evidence_stance_classifier"] if r["task"] == "alpha_classifier"]
        assert len(alpha_on_disk) == provider.count["alpha_classifier"]
        assert all(r.get("claim_ids") and r["validated_output"] is not None for r in alpha_on_disk)


def test_a_gateway_without_the_run_stop_keeps_its_earlier_retry_behavior():
    """Only the research pipeline attaches the stop; any other gateway (recovery / evaluation drivers, which have their
    own stop rules) still retries a 429 exactly as before when its own retry count allows it."""
    from comqutor_alpha.structure_engine.week2_llm import Week2LLMGateway

    class _RateLimited(Exception):
        status_code = 429

    class _Model:
        calls = 0

        def invoke(self, prompt):
            _Model.calls += 1
            if _Model.calls == 1:
                raise _RateLimited()

            class _R:
                content = json.dumps({"decision": "none", "selected_alpha_id": None})

            return _R()

    gateway = Week2LLMGateway(_Model(), run_id=f"r28-noattach-{uuid.uuid4().hex[:6]}", output_root="/nonexistent-never-written", max_retries=1)
    gateway._log = lambda *a, **k: None
    invocation = gateway.invoke_json_with_trace("alpha_classifier", {"claim": "x"}, _alpha_validator)
    assert gateway.provider_stop is None and _Model.calls == 2 and invocation.provider_status == "success"
