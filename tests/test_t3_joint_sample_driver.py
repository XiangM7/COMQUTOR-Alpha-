"""Round 25 (T3), part B: zero-call tests for the five-link joint driver
(docs/audit_artifacts/round_source_linking_t0_t2/t3_joint_sample_driver.py) on the frozen v4 sample.

The REAL sending stack is exercised -- tradingagents' create_llm_client, the production Week2LLMGateway (retry loop, call budget, validation,
semantic ledger), the production AuditingTransport and the driver's send guard and checkpoint -- with only the network itself replaced by an
httpx.MockTransport. These tests prove client construction, configuration passing, audit, budget, failure recording, checkpoint and stop
rules; fixed responses prove nothing about answer quality. The saved runs are read, never written.
"""

from __future__ import annotations

import functools
import hashlib
import importlib.util
import json
import sys
from collections import Counter
from pathlib import Path
from typing import Any

import httpx
import pytest

from comqutor_alpha.structure_engine.week2_llm import Week2LLMGateway

REPO = Path(__file__).resolve().parents[1]
AUDIT = REPO / "docs/audit_artifacts/round_source_linking_t0_t2"
PACKAGE = AUDIT / "round25_t3_minimal_prep_20261008"
B1 = PACKAGE / "B1_samples_v4"
MANIFEST = B1 / "joint_sample_v4_manifest.json"
FORM = B1 / "review_form_v4.json"
RUNS = ("1bad76a7-72ac-4c8b-8189-2e5c0f1a6105", "c904d4cc-dc09-495c-aec5-b056979948e1", "034a0a60-430e-41f8-8321-03a11389707a")

_spec = importlib.util.spec_from_file_location("t3_joint_sample_driver", AUDIT / "t3_joint_sample_driver.py")
driver = importlib.util.module_from_spec(_spec)
sys.modules[_spec.name] = driver
_spec.loader.exec_module(driver)

needs_saved_runs = pytest.mark.skipif(
    not MANIFEST.is_file() or not all((REPO / "outputs/runs" / r / "structured_agent_outputs.json").is_file() for r in RUNS),
    reason="the frozen round-25 sample or its saved runs are not present in this checkout",
)
FORBIDDEN_BODY_KEYS = {"max_tokens", "max_completion_tokens", "temperature", "top_p", "thinking", "reasoning_effort", "response_format", "extra_body", "stop"}


@functools.lru_cache(maxsize=1)
def _frozen() -> str:
    return json.dumps(driver.build_frozen_requests(driver.load_samples(MANIFEST), driver.FrozenConfig()))


def frozen() -> dict:
    return json.loads(_frozen())


class Network:
    """Stands in for the network under the real transport stack; counts what reaches it, per task."""

    def __init__(self, override=None) -> None:
        self.prefixes = driver.prompt_prefixes()
        self.override = override or {}
        self.received: Counter = Counter()
        self.requests: list[httpx.Request] = []

    def task_of(self, request: httpx.Request) -> str:
        content = json.loads(request.content)["messages"][0]["content"]
        return next(t for t, p in self.prefixes.items() if content.startswith(p))

    def handler(self, request: httpx.Request) -> httpx.Response:
        task = self.task_of(request)
        self.received[task] += 1
        self.requests.append(request)
        behave = self.override.get(task)
        if behave is not None:
            return behave(request, self.received[task])
        return driver.rehearsal_response(request, self.prefixes)

    def factory(self):
        return lambda: httpx.MockTransport(self.handler)


def run(tmp_path: Path, network: Network, *, config=None, gateway_config=None, mutate=None) -> dict[str, Any]:
    config = config or driver.FrozenConfig()
    checkpoint = driver.Checkpoint(tmp_path / "checkpoint.jsonl")
    guard = driver.SendGuard(frozen(), checkpoint)
    gateways = driver.build_task_gateways(gateway_config or config, tmp_path, "exec-test", guard, base_transport_factory=network.factory(), api_key="test-not-a-key")
    samples = driver.load_samples(MANIFEST)
    if mutate:
        mutate(samples, gateways)
    audit: dict = {}
    predictions = driver.predict(samples, gateways=gateways, config=config, audit=audit, guard=guard, progress_dir=tmp_path)
    return {"predictions": {p["sample_id"]: p for p in predictions}, "guard": guard, "gateways": gateways, "audit": audit,
            "checkpoint": driver.summarize_checkpoint(checkpoint.path), "events": [json.loads(x) for x in checkpoint.path.read_text().splitlines()]}


def _audit_records(tmp_path: Path, task: str, kind: str) -> list[dict]:
    path = tmp_path / task / "exec-test" / "error_logs" / f"week2_llm_provider_{kind}_audit.jsonl"
    return [json.loads(x) for x in path.read_text().splitlines()] if path.exists() else []


def _saved_run_hashes():
    return {r: hashlib.sha256((REPO / "outputs/runs" / r / "structured_agent_outputs.json").read_bytes()).hexdigest() for r in RUNS}


# ---------------------------------------------------------------------------------------------------------------------------------
# real client construction, configuration passing, audit identity
# ---------------------------------------------------------------------------------------------------------------------------------


@needs_saved_runs
def test_the_real_clients_send_exactly_the_frozen_request_shape(tmp_path):
    before = _saved_run_hashes()
    network = Network()
    result = run(tmp_path, network)
    config = driver.FrozenConfig()
    assert result["guard"].tripped is None
    assert network.received["content_support_verification"] == 17 and network.received["alpha_classifier"] == 40
    assert 1 <= network.received["evidence_stance_classifier"] <= config.max_requests["evidence_stance_classifier"]
    for request in network.requests:
        body = json.loads(request.content)
        assert str(request.url) == "https://api.deepseek.com/chat/completions" and request.method == "POST"
        assert sorted(body) == ["messages", "model", "stream"] and body["model"] == "deepseek-v4-flash" and body["stream"] is False
        assert not (FORBIDDEN_BODY_KEYS & set(body))  # no output cap, no thinking / reasoning / sampling parameter is sent
        assert request.headers["x-stainless-retry-count"] == "0"  # SDK retries 0
    for task, gateway in result["gateways"].items():
        model = gateway._model
        assert type(model).__name__ == "DeepSeekChatOpenAI"  # tradingagents' DeepSeek client class, as production builds it
        assert model.request_timeout == config.timeout_seconds[task] and model.max_retries == 0 and model.max_tokens is None
        assert gateway.timeout_seconds == config.timeout_seconds[task] and gateway.max_retries == 0 and gateway.max_calls == config.max_requests[task]
        assert gateway._call_count == network.received[task]  # with both retry layers at 0, reservations == requests sent
    assert _saved_run_hashes() == before  # read-only


@needs_saved_runs
def test_every_sent_request_leaves_task_claim_attempt_request_response_model_prompt_and_usage(tmp_path):
    network = Network()
    result = run(tmp_path, network)
    sending = [e for e in result["events"] if e["event"] == "sending"]
    assert len(sending) == sum(network.received.values())
    for task in driver.TASKS:
        req, resp = _audit_records(tmp_path, task, "request"), _audit_records(tmp_path, task, "response")
        assert len(req) == len(resp) == network.received[task]
        assert {r["attempt_id"] for r in req} == {r["attempt_id"] for r in resp} == {e["attempt_id"] for e in sending if e["task"] == task}
        for r in req:
            assert r["task"] == task and r["claim_ids"] and json.loads(r["body"])["model"] == "deepseek-v4-flash"
            assert r["headers"]["authorization"] == "REDACTED"  # the credential never reaches a file
        for r in resp:
            body = json.loads(r["body"])
            assert r["status_code"] == 200 and body["usage"] and body["model"] == "deepseek-v4-flash"
    for e in sending:  # the checkpoint names the verified prompt version and the frozen input hash of every request
        assert e["prompt_version"] == frozen()["prompt_version"][e["task"]] and e["input_sha256"] and e["claim_ids"]
    for task in ("alpha_classifier", "evidence_stance_classifier"):  # these two also land in the semantic ledger
        ledger = [json.loads(x) for x in (tmp_path / task / "exec-test" / "llm_semantic_calls.jsonl").read_text().splitlines()]
        assert len(ledger) == network.received[task]
        assert {r["prompt_version"] for r in ledger} == {frozen()["prompt_version"][task]} and {r["model"] for r in ledger} == {"deepseek-v4-flash"}
        assert all(r["token_usage"] and r["input_sha256"] for r in ledger)
        if task == "alpha_classifier":  # alpha carries its claim out of band; a stance batch carries its claims inside the payload items
            assert all(r["claim_ids"] for r in ledger)


@needs_saved_runs
def test_all_forty_alpha_predictions_are_new_requests_and_history_is_only_a_comparison(tmp_path):
    network = Network()
    result = run(tmp_path, network)
    assert network.received["alpha_classifier"] == 40
    assert {p["L2"]["answer_source"] for p in result["predictions"].values()} == {"NEW_REQUEST_THIS_EXECUTION"}
    history = driver.historical_alpha_answers(driver.load_samples(MANIFEST), driver.FrozenConfig())
    assert sum(1 for h in history.values() if h["status"] == "HISTORICAL_ANSWER") >= 1
    assert set(history) == set(result["predictions"])


# ---------------------------------------------------------------------------------------------------------------------------------
# stop rules and failure recording
# ---------------------------------------------------------------------------------------------------------------------------------


@needs_saved_runs
def test_a_request_field_that_differs_from_the_frozen_shape_is_never_sent_and_stops_everything(tmp_path):
    network = Network()
    drifted = driver.FrozenConfig(max_tokens={"content_support_verification": None, "alpha_classifier": 4096, "evidence_stance_classifier": None})
    result = run(tmp_path, network, gateway_config=drifted)
    assert result["guard"].tripped == "REQUEST_FIELDS_MISMATCH"
    assert network.received["alpha_classifier"] == 0 and network.received["evidence_stance_classifier"] == 0  # nothing left the guard
    assert network.received["content_support_verification"] == 17  # L1 had already completed under the frozen shape
    refused = [e for e in result["events"] if e["event"] == "not_sent"]
    assert any(e["reason"] == "REQUEST_FIELDS_MISMATCH" for e in refused)  # concurrent attempts then see GUARD_ALREADY_TRIPPED
    assert [e["reason"] for e in result["events"] if e["event"] == "guard_tripped"] == ["REQUEST_FIELDS_MISMATCH"]
    outcomes = {p["L2"]["outcome_code"] for p in result["predictions"].values()}
    assert "NONE" not in outcomes and "MATCHED" not in outcomes  # a refusal never becomes a valid NONE


@needs_saved_runs
def test_an_input_that_was_not_frozen_is_never_sent(tmp_path):
    network = Network()

    def change_one_claim(samples, _gateways):
        samples[0]["record"]["claim"] += " (edited after freezing)"

    result = run(tmp_path, network, mutate=change_one_claim)
    assert result["guard"].tripped == "INPUT_NOT_FROZEN"
    assert result["checkpoint"]["by_state"].get("not_sent", 0) >= 1


@needs_saved_runs
def test_an_authentication_failure_stops_all_later_sending(tmp_path):
    network = Network({"content_support_verification": lambda req, n: httpx.Response(401, json={"error": {"message": "invalid api key"}})})
    result = run(tmp_path, network)
    assert result["guard"].tripped == "HTTP_401"
    assert sum(network.received.values()) == 1  # the first request failed; nothing after it reached the network
    assert {p["L2"]["outcome_code"] for p in result["predictions"].values()} == {driver.NOT_REACHED_GUARD_TRIPPED}
    assert result["checkpoint"]["by_state"]["returned_error"] == 1


@needs_saved_runs
def test_a_request_audit_save_failure_means_not_sent_and_stops(tmp_path):
    network = Network()

    def break_request_audit(_samples, gateways):
        def fail(_request):
            raise OSError("disk full")
        gateways["content_support_verification"]._persist_request_audit = fail

    result = run(tmp_path, network, mutate=break_request_audit)
    assert sum(network.received.values()) == 0  # the request was refused before the network
    assert result["guard"].tripped == "AUDIT_REQUEST_SAVE_FAILED"
    assert any(e["event"] == "not_sent" and e["reason"] == "AUDIT_REQUEST_SAVE_FAILED" for e in result["events"])


@needs_saved_runs
def test_a_response_audit_save_failure_stops_later_sending(tmp_path):
    network = Network()

    def break_response_audit(_samples, gateways):
        def fail(_request, _response):
            raise OSError("disk full")
        gateways["content_support_verification"]._persist_response_audit = fail

    result = run(tmp_path, network, mutate=break_response_audit)
    assert result["guard"].tripped == "AUDIT_RESPONSE_SAVE_FAILED"
    assert sum(network.received.values()) == 1  # the provider had already answered the first; nothing else was sent


@needs_saved_runs
def test_a_timeout_is_recorded_as_a_failure_never_as_none(tmp_path):
    def timeout(request, n):
        raise httpx.ReadTimeout("simulated", request=request)

    network = Network({"alpha_classifier": timeout})
    result = run(tmp_path, network)
    outcomes = Counter(p["L2"]["outcome_code"] for p in result["predictions"].values())
    assert "NONE" not in outcomes and "MATCHED" not in outcomes
    assert result["checkpoint"]["by_task"]["alpha_classifier"] == {"sent_transport_error": 40}
    assert result["guard"].tripped is None  # a timeout is a recorded failure, not a stop rule; nothing is retried
    assert network.received["alpha_classifier"] == 40


@needs_saved_runs
def test_a_failed_direction_is_a_task_failure_never_the_deterministic_baseline(tmp_path):
    def broken(request, n):
        return httpx.Response(200, json={"id": "x", "object": "chat.completion", "created": 0, "model": "deepseek-v4-flash",
                                         "choices": [{"index": 0, "message": {"role": "assistant", "content": "{not json"}, "finish_reason": "stop"}],
                                         "usage": {"prompt_tokens": 1, "completion_tokens": 1, "total_tokens": 2}})

    result = run(tmp_path, Network({"evidence_stance_classifier": broken}))
    matched = [p for p in result["predictions"].values() if p["L2"]["outcome_code"] == "MATCHED"]
    assert matched
    for p in matched:
        assert p["L3"]["status"] == driver.TASK_FAILED and "stance" not in p["L3"] and "deterministic_baseline_not_a_result" in p["L3"]
        assert p["L4"]["conflict_side_eligible"] is None


@needs_saved_runs
def test_request_caps_are_exact(tmp_path):
    network = Network()
    capped = driver.FrozenConfig(max_requests={"content_support_verification": 17, "alpha_classifier": 40, "evidence_stance_classifier": 1}, stance_concurrency=1)
    result = run(tmp_path, network, config=capped, gateway_config=capped)
    assert network.received["evidence_stance_classifier"] == 1
    assert any(p["L3"]["status"] == driver.TASK_FAILED for p in result["predictions"].values())


def test_an_unknown_outcome_is_reported_and_never_resent(tmp_path):
    checkpoint = driver.Checkpoint(tmp_path / "checkpoint.jsonl")
    checkpoint.write("sending", task="alpha_classifier", attempt_id="x:1", claim_ids=["c1"])
    checkpoint.write("response", task="alpha_classifier", attempt_id="x:1", status_code=200)
    checkpoint.write("sending", task="alpha_classifier", attempt_id="x:2", claim_ids=["c2"])  # process died here
    checkpoint.write("sending", task="content_support_verification", attempt_id="x:1", claim_ids=["c3"])
    checkpoint.write("response", task="content_support_verification", attempt_id="x:1", status_code=200)
    summary = driver.summarize_checkpoint(checkpoint.path)
    assert summary["by_state"] == {"returned_ok": 2, "unknown": 1}
    assert summary["unknown_never_resent"] == [{"attempt_id": "alpha_classifier|x:2", "task": "alpha_classifier", "claim_ids": ["c2"]}]


# ---------------------------------------------------------------------------------------------------------------------------------
# the authorized-plan entry point: refusals, rehearsal, and one full mock execution
# ---------------------------------------------------------------------------------------------------------------------------------


def _plan(tmp_path: Path, **overrides) -> tuple[str, str]:
    freeze_dir = tmp_path / "freeze"
    if not (freeze_dir / "authorized_plan_TEMPLATE.json").exists():
        assert driver.main(["freeze", "--manifest", str(MANIFEST), "--review-form", str(FORM), "--out-dir", str(freeze_dir)]) == 0
    plan = json.loads((freeze_dir / "authorized_plan_TEMPLATE.json").read_text())
    plan.update({"authorized": True, "authorized_by": "test owner", "execution_id": "t3joint-test", "out_dir": str(tmp_path / "executions")})
    plan.update(overrides)
    path = tmp_path / f"plan_{len(list(tmp_path.glob('plan_*.json')))}.json"
    path.write_text(json.dumps(plan))
    return str(path), hashlib.sha256(path.read_bytes()).hexdigest()


@needs_saved_runs
def test_predict_refuses_before_any_gateway_unless_the_plan_matches(tmp_path):
    network = Network()
    path, _digest = _plan(tmp_path)
    template = str(tmp_path / "freeze" / "authorized_plan_TEMPLATE.json")
    template_digest = hashlib.sha256(Path(template).read_bytes()).hexdigest()
    assert driver.main(["predict", "--authorized-plan", template, "--plan-sha256", template_digest], base_transport_factory=network.factory()) == 3  # unsigned
    assert driver.main(["predict", "--authorized-plan", path, "--plan-sha256", "0" * 64], base_transport_factory=network.factory()) == 3
    plan = json.loads(Path(path).read_text())
    for overrides in ({"authorized_by": " "}, {"manifest_sha256": "0" * 64}, {"frozen_requests_sha256": "0" * 64},
                      {"prompt_identity_sha256": {**plan["prompt_identity_sha256"], "alpha_classifier": "0" * 64}},
                      {"code_identity": {**plan["code_identity"], "tracked_diff_sha256": "0" * 64}}):
        p, d = _plan(tmp_path, **overrides)
        assert driver.main(["predict", "--authorized-plan", p, "--plan-sha256", d], base_transport_factory=network.factory()) == 3
    assert sum(network.received.values()) == 0 and not (tmp_path / "executions").exists()


@needs_saved_runs
def test_a_full_authorized_execution_rehearses_first_then_writes_everything_and_is_never_resumed(tmp_path):
    network = Network()
    path, digest = _plan(tmp_path)
    assert driver.main(["predict", "--authorized-plan", path, "--plan-sha256", digest], base_transport_factory=network.factory()) == 0
    execution = tmp_path / "executions" / "t3joint-test"
    rehearsal = json.loads((execution / "rehearsal_report.json").read_text())
    assert rehearsal["passed"] and rehearsal["requests_sent"]["alpha_classifier"] == 40
    summary = json.loads((execution / "run_summary.json").read_text())
    assert summary["guard_tripped"] is None and set(summary["checkpoint"]["by_state"]) == {"returned_ok"}
    assert summary["checkpoint"]["by_task"]["alpha_classifier"] == {"returned_ok": 40}
    assert len((execution / "joint_predictions.jsonl").read_text().splitlines()) == 40
    for name in ("authorized_plan.json", "checkpoint.jsonl", "task_audit.json", "progress_L1.json", "progress_L2_L3.json"):
        assert (execution / name).is_file()
    sent_before = sum(network.received.values())
    assert driver.main(["predict", "--authorized-plan", path, "--plan-sha256", digest], base_transport_factory=network.factory()) == 2
    assert sum(network.received.values()) == sent_before  # an existing execution is never resumed or re-sent


# ---------------------------------------------------------------------------------------------------------------------------------
# bounded material collection (prediction-market history for the four A501 samples)
# ---------------------------------------------------------------------------------------------------------------------------------


def _market(mid, question, token):
    return {"id": mid, "question": question, "outcomes": '["Yes", "No"]', "clobTokenIds": json.dumps([token, token + "-no"])}


class MarketNetwork:
    def __init__(self, *, search_status=200, drop=()):
        self.search_status, self.drop, self.requests = search_status, set(drop), []

    def handler(self, request: httpx.Request) -> httpx.Response:
        self.requests.append(request)
        if request.url.host == "gamma-api.polymarket.com":
            markets = [_market("m1", "US recession by end of 2026?", "tok-us"), _market("m2", "UK recession in 2026?", "tok-uk"),
                       _market("m3", "Japan recession in 2026?", "tok-jp"), _market("m4", "Germany recession in 2026?", "tok-de")]
            return httpx.Response(self.search_status, json={"events": [{"markets": [m for m in markets if m["question"] not in self.drop]}]})
        assert request.url.host == "clob.polymarket.com" and request.url.params["fidelity"] == "1440"
        return httpx.Response(200, json={"history": [{"t": 1759276800, "p": 0.08}, {"t": 1759622400, "p": 0.075}]})


def test_collection_sends_one_search_and_one_history_per_market_and_saves_everything(tmp_path):
    network = MarketNetwork()
    record = driver.collect_materials(tmp_path / "m", transport=httpx.MockTransport(network.handler))
    assert record["stopped"] is None and record["requests_sent"] == len(network.requests) == 4
    assert {q: m["status"] for q, m in record["markets"].items()} == dict.fromkeys(driver.COLLECTION_TARGETS, "COLLECTED")
    for entry in record["requests"]:
        saved = (tmp_path / "m" / entry["file"]).read_bytes()
        assert hashlib.sha256(saved).hexdigest() == entry["sha256"] and entry["status_code"] == 200 and entry["retrieved_at"]
    addendum = json.loads((tmp_path / "m" / "review_form_v4_addendum.json").read_text())["items"]
    assert set(addendum) == {"t3v3-037", "t3v3-038", "t3v3-039", "t3v3-040"}
    assert all(m["note"].startswith("collected for this verification") for items in addendum.values() for m in items)


def test_collection_stops_at_the_first_error_and_never_searches_again(tmp_path):
    failing = MarketNetwork(search_status=500)
    record = driver.collect_materials(tmp_path / "a", transport=httpx.MockTransport(failing.handler))
    assert record["stopped"] == "HTTP_500" and len(failing.requests) == 1
    missing = MarketNetwork(drop={"Japan recession in 2026?"})
    record = driver.collect_materials(tmp_path / "b", transport=httpx.MockTransport(missing.handler))
    assert record["markets"]["Japan recession in 2026"]["status"] == "NOT_FOUND" and len(missing.requests) == 3


@needs_saved_runs
def test_collection_runs_only_under_an_authorized_collection_section(tmp_path):
    network = MarketNetwork()
    factory = lambda: httpx.MockTransport(network.handler)  # noqa: E731
    path, digest = _plan(tmp_path)
    assert driver.main(["collect", "--authorized-plan", path, "--plan-sha256", digest], base_transport_factory=factory) == 3
    plan = json.loads(Path(path).read_text())
    path, digest = _plan(tmp_path, collection={**plan["collection"], "authorized": True})
    assert len(network.requests) == 0
    assert driver.main(["collect", "--authorized-plan", path, "--plan-sha256", digest], base_transport_factory=factory) == 0
    assert (tmp_path / "executions" / "t3joint-test-materials" / "collection_record.json").is_file() and len(network.requests) == 4
    assert driver.main(["collect", "--authorized-plan", path, "--plan-sha256", digest], base_transport_factory=factory) == 2  # never repeated


# ---------------------------------------------------------------------------------------------------------------------------------
# sample materials, sizing, form and scoring
# ---------------------------------------------------------------------------------------------------------------------------------


@needs_saved_runs
def test_the_v4_sample_and_its_materials_rebuild_byte_for_byte(tmp_path):
    spec = importlib.util.spec_from_file_location("build_samples_v4", PACKAGE / "tools" / "build_samples_v4.py")
    builder = importlib.util.module_from_spec(spec)
    sys.path.insert(0, str(PACKAGE / "tools"))
    spec.loader.exec_module(builder)
    assert builder.main(["--out-dir", str(tmp_path / "v4")]) == 0
    for name in ("joint_sample_v4_manifest.json", "review_form_v4.json", "review_worksheet_v4.csv", "material_coverage.json", "replacement_log.json", "collection_list.json"):
        assert (tmp_path / "v4" / name).read_bytes() == (B1 / name).read_bytes(), name


@needs_saved_runs
def test_sizing_counts_forty_new_alpha_requests_and_the_stance_worst_case():
    sizing = driver.sizing(driver.load_samples(MANIFEST), driver.FrozenConfig())
    assert sizing["content_support_verification"]["requests"] == 17 and sizing["content_support_verification"]["reusable_saved_results"] == 0
    assert sizing["content_support_verification"]["production_default_batch_size"]["batches_over_input_cap_refused_before_sending"] == 3
    assert sizing["alpha_classifier"]["requests"] == 40
    assert sizing["evidence_stance_classifier"]["requests_upper_bound"] == 13 == driver.FrozenConfig().max_requests["evidence_stance_classifier"]


@needs_saved_runs
def test_the_review_form_carries_no_system_answer():
    form = json.loads(FORM.read_text())
    text = json.dumps(form)
    for marker in ("matched_alpha", "source_link_status", "evidence_stance", "content_support", "claim_id", "run_id", "conflict_raw_pool",
                   "key_conclusion", "material_status", "NOT_SAVED", "linked_source"):
        assert marker not in text
    assert set(form["judgment_vocabulary"]) == set(driver.JUDGMENT_KEYS)
    assert all(all(v is None for v in i["judgments"].values()) for i in form["items"])
    assert len(form["items"]) == 40


def _prediction(sid, cell="A304_boundary", alpha="A304", l1="SUPPORTS", stance="supports_alpha", qualifies=True, claim_text="c", l1_status=None, material="COMPLETE"):
    l1_block = {"status": driver.LLM_RESULT, "content_support_status": l1} if l1_status is None else {"status": l1_status, "reason": "x"}
    return {"sample_id": sid, "cell": cell, "material_status": material, "claim_text": claim_text, "L1": l1_block,
            "L2": {"outcome_code": "MATCHED" if alpha else "NONE", "predicted_alpha": alpha, "raw_selected_alpha": alpha},
            "L3": {"status": driver.LLM_RESULT, "target_alpha": alpha, "stance": stance} if alpha else {"status": driver.NOT_APPLICABLE},
            "L4": {"status": "DETERMINED", "alpha": alpha, "activation_pool_eligible": qualifies, "failing_condition_kind": None, "selector": {}, "verified_support": {}}
            if alpha else {"status": driver.NOT_APPLICABLE}}


def _form(items):
    return {"judgment_vocabulary": json.loads(FORM.read_text())["judgment_vocabulary"] if FORM.is_file() else {},
            "items": [{"sample_id": sid, "claim_text": "c", "judgments": j} for sid, j in items]}


def _judgment(**values):
    base: dict[str, Any] = dict.fromkeys(driver.JUDGMENT_KEYS)
    base.update({"reviewer_id": "reviewer-1", "reviewer_role": "designated", "attests_no_prior_view_of_system_outputs": True})
    base.update(values)
    return base


def test_scoring_is_blocked_without_named_reviewers():
    result = driver.score([_prediction("a")], _form([("a", {**_judgment(R2_alpha="A304"), "reviewer_id": None}), ("b", dict.fromkeys(driver.JUDGMENT_KEYS))]))
    assert result["scoring_status"] == "BLOCKED_NO_REFERENCE_JUDGMENTS"
    assert result["skipped"] == {"REVIEWER_ID_MISSING": 1, "PENDING_REVIEW": 1}


@needs_saved_runs
def test_each_link_keeps_its_own_denominator_and_unchecked_claims_are_counted_by_reason():
    predictions = [
        _prediction("a"),
        _prediction("b", l1="CONDITIONAL", stance="opposes_alpha", qualifies=False),
        _prediction("c", l1_status=driver.NOT_SUBMITTED),
        _prediction("d", alpha=None),
        _prediction("e", alpha="A101"),
    ]
    full = {"R1_claim_fidelity": "FAITHFUL", "R1_source_relation": "SUPPORTS", "R2_alpha": "A304", "R3_direction": "supports_alpha", "R4_evidence_eligibility": "QUALIFIES"}
    form = _form([
        ("a", _judgment(**full)), ("b", _judgment(**full)), ("c", _judgment(**full)),
        ("d", _judgment(R2_alpha="NONE", R3_direction="NOT_APPLICABLE")),
        ("e", _judgment(R2_alpha="A103", R3_direction="supports_alpha", R4_evidence_eligibility="QUALIFIES")),
    ])
    result = driver.score(predictions, form)
    assert result["L2_alpha"]["scored_sample_count"] == 5 and result["L2_alpha"]["overall_accuracy"] == 0.8
    assert result["L1_source_to_claim"]["counts"]["compared"] == 2 and result["L1_source_to_claim"]["agreement_rate"] == 0.5
    assert result["L1_source_to_claim"]["not_checked_by_production_vs_reviewer_relation"]["NOT_SUBMITTED | reviewer SUPPORTS"] == 1
    assert result["L3_direction"]["counts"] == {"compared": 3, "agree": 2, "not_applicable_no_system_alpha": 1, "not_applicable_alpha_differs": 1}
    assert result["L4_claim_eligibility"]["counts"]["compared"] == 3 and result["L4_claim_eligibility"]["counts"]["agree"] == 2


@needs_saved_runs
def test_values_outside_the_vocabulary_are_reported_not_coerced():
    result = driver.score([_prediction("a"), _prediction("b")], _form([("a", _judgment(R2_alpha="A304")), ("b", _judgment(R2_alpha="Multiple Compression"))]))
    assert result["skipped"] == {"VALUE_OUTSIDE_VOCABULARY": 1} and result["reference_items"] == 1


def test_a_form_that_drifted_from_the_predictions_refuses_to_score():
    with pytest.raises(driver.SampleVersionMismatch):
        driver.score([_prediction("a", claim_text="other text")], _form([("a", _judgment(R2_alpha="A304"))]))


# ---------------------------------------------------------------------------------------------------------------------------------
# the two minimal fixes to the older joint driver
# ---------------------------------------------------------------------------------------------------------------------------------


def test_older_joint_driver_reads_the_records_key_and_labels_its_stance_as_baseline(tmp_path):
    from tests.test_t3_joint_verification_driver import (
        _build_fixture_run,
        _fake_gateway,
        driver as old_driver,
    )

    run_dir, _run_id, claim_id = _build_fixture_run(tmp_path, alpha_decision="select", selected_alpha_id="A501")
    path = run_dir / "structured_agent_outputs.json"
    path.write_text(json.dumps({"records": json.loads(path.read_text())["claims"]}))  # the shape real runs save
    gateway = _fake_gateway(json.dumps({"decision": "select", "selected_alpha_id": "A501"}))("gateway-run", tmp_path)
    result = old_driver.run_joint_verification(run_dir, llm_gateway=gateway, fixture_mode=True)
    assert [r.claim_id for r in result.claim_records] == [claim_id]
    stance = result.claim_records[0].system_output["stance"]
    assert stance["status"] == "DETERMINISTIC_BASELINE_ONLY" and stance["method"].startswith("deterministic_baseline")


def test_the_gateway_class_is_the_production_one():
    assert Week2LLMGateway.__module__ == "comqutor_alpha.structure_engine.week2_llm"
