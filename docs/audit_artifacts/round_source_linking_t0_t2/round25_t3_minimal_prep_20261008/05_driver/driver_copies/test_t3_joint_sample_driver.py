"""Round 25 (T3 minimal preparation): zero-call tests for the five-link joint driver
(docs/audit_artifacts/round_source_linking_t0_t2/t3_joint_sample_driver.py).

Every link runs through the REAL production function and a REAL Week2LLMGateway (retry loop, call budget, validation); only the model
object at the Provider boundary is a fake that answers from the request payload -- zero network, zero paid calls. The frozen round-25
sample and the saved runs it points to are read, never written. These tests prove bookkeeping (which result goes where, what is counted,
what is refused); they are not a measurement of model quality.
"""

from __future__ import annotations

import hashlib
import importlib.util
import json
import sys
from pathlib import Path

import pytest

from comqutor_alpha.llm_runtime.session import SemanticRuntimeSession
from comqutor_alpha.source_provenance import compute_verified_support_eligibility
from comqutor_alpha.structure_engine.week2_llm import Week2LLMGateway
from tests._content_support_v2_fixture_helpers import v2_response

REPO = Path(__file__).resolve().parents[1]
AUDIT = REPO / "docs/audit_artifacts/round_source_linking_t0_t2"
PACKAGE = AUDIT / "round25_t3_minimal_prep_20261008"
MANIFEST = PACKAGE / "04_joint_sample/joint_sample_v3_manifest.json"
FORM = PACKAGE / "04_joint_sample/review_form_v3.json"
RUNS = ("1bad76a7-72ac-4c8b-8189-2e5c0f1a6105", "c904d4cc-dc09-495c-aec5-b056979948e1", "034a0a60-430e-41f8-8321-03a11389707a")

_spec = importlib.util.spec_from_file_location("t3_joint_sample_driver", AUDIT / "t3_joint_sample_driver.py")
driver = importlib.util.module_from_spec(_spec)
sys.modules[_spec.name] = driver
_spec.loader.exec_module(driver)

needs_saved_runs = pytest.mark.skipif(
    not MANIFEST.is_file() or not all((REPO / "outputs/runs" / r / "structured_agent_outputs.json").is_file() for r in RUNS),
    reason="the frozen round-25 sample or its saved runs are not present in this checkout",
)


class _Response:
    def __init__(self, content: str) -> None:
        self.content = content


class _TaskModel:
    """Fake model at the Provider boundary: answers from the request payload only."""

    def __init__(self, answer) -> None:
        self.answer = answer
        self.calls = 0
        self.payloads: list = []

    def invoke(self, prompt: str) -> _Response:
        self.calls += 1
        payload = json.loads(prompt.split("\nINPUT_JSON:\n", 1)[1])
        self.payloads.append(payload)
        return _Response(self.answer(payload))


def alpha_select(alpha_id):
    return lambda _payload: json.dumps({"decision": "select", "selected_alpha_id": alpha_id})


def alpha_none(_payload):
    return json.dumps({"decision": "none", "selected_alpha_id": None})


def stance_all(stance):
    return lambda payload: json.dumps({"items": [
        {"claim_id": i["claim_id"], "target_alpha_id": i["target_alpha_id"], "stance": stance, "counter_alpha_id": None} for i in payload["items"]
    ]})


def content_supports(payload):
    items = []
    for item in payload["items"]:
        candidate = item["allowed_candidates"][0]
        items.append(v2_response(claim_id=item["claim_id"], status="SUPPORTS", used_source_id=candidate["source_id"], used_location="excerpt",
                                 supporting_quote_or_data=(candidate.get("excerpt") or "")[:30], supported_proposition=item["proposition"]))
    return json.dumps({"items": items})


def broken(_payload):
    return "{not valid json"


def _gateways(tmp_path, answers, caps=None):
    session = SemanticRuntimeSession(run_id="t3-joint-test", output_directory=tmp_path, execution_mode="test", provider="fake", model="fake")
    models, gateways = {}, {}
    for task in driver.TASKS:
        models[task] = _TaskModel(answers[task])
        gateways[task] = Week2LLMGateway(models[task], run_id="t3-joint-test", output_root=str(tmp_path), timeout_seconds=5.0, max_retries=0,
                                         max_calls=(caps or {}).get(task, 100), provider="fake", model_name="fake", semantic_runtime=session)
    return gateways, models


NO_REUSE = {"reuse_saved_alpha_answers": False}


def _saved_run_hashes():
    return {r: hashlib.sha256((REPO / "outputs/runs" / r / "structured_agent_outputs.json").read_bytes()).hexdigest() for r in RUNS}


# ---------------------------------------------------------------------------------------------------------------------------------
# the frozen sample through all five links
# ---------------------------------------------------------------------------------------------------------------------------------


@needs_saved_runs
def test_every_link_is_recorded_separately_and_requests_match_the_sizing(tmp_path):
    before = _saved_run_hashes()
    gateways, models = _gateways(tmp_path, {"content_support_verification": content_supports, "alpha_classifier": alpha_select("A304"),
                                            "evidence_stance_classifier": stance_all("supports_alpha")})
    audit: dict = {}
    predictions = driver.predict(driver.load_samples(MANIFEST), gateways=gateways, config=driver.FrozenConfig(), audit=audit, work_dir=tmp_path)
    sizing = driver.sizing(driver.load_samples(MANIFEST), driver.FrozenConfig())

    assert len(predictions) == 40
    # requests: exactly the zero-call sizing for content support and Alpha, within the bound for stance; with both retry layers at 0 the
    # gateway's reservations equal the requests the model received
    assert models["content_support_verification"].calls == sizing["content_support_verification"]["requests"] == 17
    # 33 claims replay a bound saved production answer, 7 are new requests
    assert models["alpha_classifier"].calls == sizing["alpha_classifier"]["requests"] == 7
    assert audit["alpha_reuse"]["bound"] == audit["alpha_reuse"]["replay_hits"] == 33 and audit["alpha_reuse"]["replay_misses"] == 0
    assert models["evidence_stance_classifier"].calls <= sizing["evidence_stance_classifier"]["requests_upper_bound"]
    for task, gateway in gateways.items():
        assert gateway._call_count == models[task].calls
    assert all(len(p["items"]) == 1 for p in models["content_support_verification"].payloads)
    assert all(len(p["items"]) <= 10 for p in models["evidence_stance_classifier"].payloads)
    # the content-support pass's own per-request log is kept (the semantic-call ledger does not register this task)
    assert sum(len(r["attempt_log"]) for r in audit["content_support_verification"].values()) == 17

    l1 = [p["L1"]["status"] for p in predictions]
    assert l1.count(driver.NOT_JUDGEABLE_NO_SOURCE_CONTENT) == sum(1 for p in predictions if p["chain"] != "FULL") == 15
    assert l1.count(driver.LLM_RESULT) == 17
    assert l1.count(driver.NOT_SUBMITTED) == 8
    assert all("TIME_INVALID" in p["L1"]["reason"] for p in predictions if p["L1"]["status"] == driver.NOT_SUBMITTED)
    removed = [p["L1"].get("saved_llm_content_result_removed") for p in predictions]
    assert removed.count("verdict") == 5 and removed.count("failure") == 7  # c904d4cc's earlier content-support pass, never reused

    for p in predictions:
        if p["L2"]["outcome_code"] == "MATCHED":
            assert p["L3"] == {"status": driver.LLM_RESULT, "target_alpha": p["L2"]["predicted_alpha"], "stance": "supports_alpha", "counter_alpha": None}
            assert p["L4"]["status"] == "DETERMINED"
        else:
            assert p["L2"]["predicted_alpha"] is None
            assert p["L3"]["status"] == p["L4"]["status"] == driver.NOT_APPLICABLE
        if p["L4"]["status"] == "DETERMINED" and not p["L4"]["verified_support"]["eligible"]:
            assert p["L4"]["activation_pool_eligible"] is False and p["L4"]["conflict_side_eligible"] is False
    assert _saved_run_hashes() == before  # read-only


@needs_saved_runs
def test_sizing_shows_the_production_batch_would_be_refused_before_sending(tmp_path):
    sizing = driver.sizing(driver.load_samples(MANIFEST), driver.FrozenConfig())["content_support_verification"]
    assert sizing["frozen_batch_size"]["batches_over_input_cap_refused_before_sending"] == 0
    assert sizing["production_default_batch_size"]["batch_size"] == 5
    assert sizing["production_default_batch_size"]["batches_over_input_cap_refused_before_sending"] == 3
    # and the gateway really refuses such a batch without calling the model
    gateways, models = _gateways(tmp_path, {"content_support_verification": content_supports, "alpha_classifier": alpha_none,
                                            "evidence_stance_classifier": stance_all("supports_alpha")})
    driver._l1(driver.load_samples(MANIFEST), gateways["content_support_verification"], 5, {})
    assert models["content_support_verification"].calls == 1  # only the 2-claim batch fits


@needs_saved_runs
def test_bound_saved_alpha_answers_are_replayed_exactly_and_only_the_rest_are_sent(tmp_path):
    samples = driver.load_samples(MANIFEST)
    reuse = driver.saved_alpha_answers(samples, driver.FrozenConfig())
    bound = {sid: b for sid, b in reuse.items() if b["status"] == "BOUND"}
    assert len(bound) == 33
    # a live Alpha answer that would always fail: the 33 replayed claims must not depend on it
    gateways, models = _gateways(tmp_path, {"content_support_verification": content_supports, "alpha_classifier": broken,
                                            "evidence_stance_classifier": stance_all("supports_alpha")})
    audit: dict = {}
    predictions = {p["sample_id"]: p for p in driver.predict(samples, gateways=gateways, config=driver.FrozenConfig(), audit=audit, work_dir=tmp_path)}
    assert models["alpha_classifier"].calls == 7
    for sid, p in predictions.items():
        source = p["L2"]["answer_source"]
        if sid in bound:
            assert source["kind"] == driver.REUSED_SAVED_PRODUCTION_ANSWER and source["call_id"] == bound[sid]["call_id"]
            saved = bound[sid]["validated_output"]
            assert p["L2"]["raw_selected_alpha"] == (saved["selected_alpha_id"] if saved["decision"] == "select" else None)
            assert p["L2"]["outcome_code"] not in {"PARSE_FAILED", "CALL_FAILED", "UNAVAILABLE", "TRUNCATED"}
        else:
            assert source["kind"] == driver.NEW_REQUEST and source["why_not_reused"]
            assert p["L2"]["outcome_code"] in {"PARSE_FAILED", "CALL_FAILED", "UNAVAILABLE", "TRUNCATED"}
    replay_ledger = tmp_path / "alpha_replay" / "llm_semantic_calls.jsonl"
    modes = {json.loads(line)["execution_mode"] for line in replay_ledger.read_text().splitlines() if line.strip()}
    assert modes == {"replay_fixture"}  # never recorded as a live call


@needs_saved_runs
def test_a_failed_stance_is_a_task_failure_never_the_deterministic_baseline(tmp_path):
    gateways, _models = _gateways(tmp_path, {"content_support_verification": content_supports, "alpha_classifier": alpha_select("A304"),
                                             "evidence_stance_classifier": broken})
    predictions = driver.predict(driver.load_samples(MANIFEST), gateways=gateways, config=driver.FrozenConfig(**NO_REUSE))
    matched = [p for p in predictions if p["L2"]["outcome_code"] == "MATCHED"]
    assert matched
    for p in matched:
        assert p["L3"]["status"] == driver.TASK_FAILED
        assert "stance" not in p["L3"]  # the baseline's value only appears under its own label
        assert p["L3"]["reason"]
        assert "deterministic_baseline_not_a_result" in p["L3"]
        assert p["L4"]["conflict_side_eligible"] is None  # undetermined without an LLM direction


@needs_saved_runs
def test_the_stance_request_cap_is_exact_and_exhaustion_is_recorded_as_failure(tmp_path):
    gateways, models = _gateways(tmp_path, {"content_support_verification": content_supports, "alpha_classifier": alpha_select("A304"),
                                            "evidence_stance_classifier": stance_all("opposes_alpha")}, caps={"evidence_stance_classifier": 1})
    config = driver.FrozenConfig(stance_concurrency=1, **NO_REUSE)
    predictions = driver.predict(driver.load_samples(MANIFEST), gateways=gateways, config=config)
    assert models["evidence_stance_classifier"].calls == 1
    statuses = [p["L3"]["status"] for p in predictions if p["L2"]["outcome_code"] == "MATCHED"]
    assert statuses.count(driver.LLM_RESULT) >= 1
    failed = [p["L3"] for p in predictions if p["L3"]["status"] == driver.TASK_FAILED]
    assert failed and all(f["reason"] for f in failed)


@needs_saved_runs
def test_none_and_a_failed_alpha_call_are_kept_apart(tmp_path):
    gateways, models = _gateways(tmp_path, {"content_support_verification": content_supports, "alpha_classifier": alpha_none,
                                            "evidence_stance_classifier": stance_all("supports_alpha")})
    predictions = driver.predict(driver.load_samples(MANIFEST), gateways=gateways, config=driver.FrozenConfig(**NO_REUSE))
    assert {p["L2"]["outcome_code"] for p in predictions} == {"NONE"}
    assert all(p["L3"]["status"] == driver.NOT_APPLICABLE and p["L4"]["status"] == driver.NOT_APPLICABLE for p in predictions)
    assert models["evidence_stance_classifier"].calls == 0  # no Alpha, no direction request

    second = tmp_path / "second"
    second.mkdir()
    gateways, _ = _gateways(second, {"content_support_verification": content_supports, "alpha_classifier": broken,
                                     "evidence_stance_classifier": stance_all("supports_alpha")})
    predictions = driver.predict(driver.load_samples(MANIFEST), gateways=gateways, config=driver.FrozenConfig(**NO_REUSE))
    outcomes = {p["L2"]["outcome_code"] for p in predictions}
    assert "NONE" not in outcomes and "MATCHED" not in outcomes
    assert outcomes <= {"PARSE_FAILED", "CALL_FAILED", "UNAVAILABLE", "TRUNCATED"}


@needs_saved_runs
def test_a_saved_llm_content_verdict_is_never_reused(tmp_path):
    samples = driver.load_samples(MANIFEST)
    with_saved = [s["sample_id"] for s in samples if (s["record"].get("content_support_review") or {}).get("method") == "LLM_CONTENT_SUPPORT_VERIFIED"]
    assert len(with_saved) == 5
    gateways, _ = _gateways(tmp_path, {"content_support_verification": broken, "alpha_classifier": alpha_select("A304"),
                                       "evidence_stance_classifier": stance_all("supports_alpha")})
    predictions = {p["sample_id"]: p for p in driver.predict(samples, gateways=gateways, config=driver.FrozenConfig(**NO_REUSE))}
    by_id = {s["sample_id"]: s for s in samples}
    for sid in with_saved:
        assert predictions[sid]["L1"]["status"] == driver.TASK_FAILED
        assert predictions[sid]["L1"]["saved_llm_content_result_removed"] == "verdict"
        assert compute_verified_support_eligibility(by_id[sid]["record"], by_id[sid]["sources"])["reason_code"] == "NOT_REVIEWED"
        if predictions[sid]["L4"]["status"] == "DETERMINED":
            assert predictions[sid]["L4"]["verified_support"]["eligible"] is False


# ---------------------------------------------------------------------------------------------------------------------------------
# review form and scoring
# ---------------------------------------------------------------------------------------------------------------------------------


@needs_saved_runs
def test_the_review_form_carries_no_system_answer():
    form = json.loads(FORM.read_text(encoding="utf-8"))
    manifest = json.loads(MANIFEST.read_text(encoding="utf-8"))
    text = json.dumps(form)
    for marker in ("matched_alpha", "source_link_status", "evidence_stance", "content_support", "claim_id", "run_id", "conflict_raw_pool", "key_conclusion"):
        assert marker not in text
    assert set(form["judgment_vocabulary"]) == set(driver.JUDGMENT_KEYS)
    assert [i["claim_text"] for i in form["items"]] == [s["claim_text"] for s in manifest["samples"]]
    assert all(all(v is None for v in i["judgments"].values()) for i in form["items"])


def _prediction(sid, cell="A304_boundary", chain="FULL", alpha="A304", l1="SUPPORTS", stance="supports_alpha", qualifies=True, claim_text="c"):
    return {"sample_id": sid, "cell": cell, "chain": chain, "claim_text": claim_text,
            "L1": {"status": driver.LLM_RESULT, "content_support_status": l1} if chain == "FULL" else {"status": driver.NOT_JUDGEABLE_NO_SOURCE_CONTENT},
            "L2": {"outcome_code": "MATCHED" if alpha else "NONE", "predicted_alpha": alpha},
            "L3": {"status": driver.LLM_RESULT, "target_alpha": alpha, "stance": stance} if alpha else {"status": driver.NOT_APPLICABLE},
            "L4": {"status": "DETERMINED", "alpha": alpha, "activation_pool_eligible": qualifies, "failing_condition_kind": None, "selector": {}, "verified_support": {}}
            if alpha else {"status": driver.NOT_APPLICABLE}}


def _form(items):
    vocabulary = json.loads(FORM.read_text(encoding="utf-8"))["judgment_vocabulary"] if FORM.is_file() else {}
    return {"judgment_vocabulary": vocabulary, "items": [{"sample_id": sid, "claim_text": "c", "judgments": j} for sid, j in items]}


def _judgment(**values):
    base = dict.fromkeys(driver.JUDGMENT_KEYS)
    base.update({"reviewer_id": "reviewer-1", "reviewer_role": "designated", "attests_no_prior_view_of_system_outputs": True})
    base.update(values)
    return base


def test_scoring_is_blocked_without_named_reviewers():
    result = driver.score([_prediction("a")], _form([("a", {**_judgment(R2_alpha="A304"), "reviewer_id": None}), ("b", dict.fromkeys(driver.JUDGMENT_KEYS))]))
    assert result["scoring_status"] == "BLOCKED_NO_REFERENCE_JUDGMENTS"
    assert result["skipped"] == {"REVIEWER_ID_MISSING": 1, "PENDING_REVIEW": 1}


@needs_saved_runs
def test_each_link_keeps_its_own_denominator():
    predictions = [
        _prediction("a"),  # agrees everywhere
        _prediction("b", l1="CONDITIONAL", stance="opposes_alpha", qualifies=False),
        _prediction("c", chain="PARTIAL_NO_SAVED_SOURCE_CONTENT"),
        _prediction("d", alpha=None),
        _prediction("e", alpha="A101"),
    ]
    form = _form([
        ("a", _judgment(R1_claim_fidelity="FAITHFUL", R1_source_relation="SUPPORTS", R2_alpha="A304", R3_direction="supports_alpha", R4_evidence_eligibility="QUALIFIES")),
        ("b", _judgment(R1_claim_fidelity="FAITHFUL", R1_source_relation="SUPPORTS", R2_alpha="A304", R3_direction="supports_alpha", R4_evidence_eligibility="QUALIFIES")),
        ("c", _judgment(R1_claim_fidelity="UNABLE_TO_JUDGE", R1_source_relation="UNABLE_TO_JUDGE", R2_alpha="A304", R3_direction="supports_alpha", R4_evidence_eligibility="QUALIFIES")),
        ("d", _judgment(R2_alpha="NONE", R3_direction="NOT_APPLICABLE")),
        ("e", _judgment(R2_alpha="A103", R3_direction="supports_alpha", R4_evidence_eligibility="QUALIFIES")),
    ])
    result = driver.score(predictions, form)
    assert result["L2_alpha"]["scored_sample_count"] == 5
    assert result["L2_alpha"]["overall_accuracy"] == 0.8
    assert result["L1_source_to_claim"]["counts"]["compared"] == 2 and result["L1_source_to_claim"]["agreement_rate"] == 0.5
    assert result["L1_source_to_claim"]["counts"]["not_judgeable_no_source_content"] == 1
    assert result["L3_direction"]["counts"] == {"compared": 3, "agree": 2, "not_applicable_no_system_alpha": 1, "not_applicable_alpha_differs": 1}
    assert result["L4_claim_eligibility"]["counts"]["compared"] == 3 and result["L4_claim_eligibility"]["counts"]["agree"] == 2
    assert result["reviewers"] == {"reviewer-1 (designated)": 5}


@needs_saved_runs
def test_values_outside_the_vocabulary_are_reported_not_coerced():
    result = driver.score([_prediction("a"), _prediction("b")],
                          _form([("a", _judgment(R2_alpha="A304")), ("b", _judgment(R2_alpha="Multiple Compression"))]))
    assert result["skipped"] == {"VALUE_OUTSIDE_VOCABULARY": 1}
    assert result["invalid"] == [{"sample_id": "b", "values_outside_vocabulary": {"R2_alpha": "Multiple Compression"}}]
    assert result["reference_items"] == 1


def test_a_form_that_drifted_from_the_predictions_refuses_to_score():
    with pytest.raises(driver.SampleVersionMismatch):
        driver.score([_prediction("a", claim_text="other text")], _form([("a", _judgment(R2_alpha="A304"))]))


# ---------------------------------------------------------------------------------------------------------------------------------
# the real-call branch refuses without an authorized, matching plan (and never builds a gateway)
# ---------------------------------------------------------------------------------------------------------------------------------


@needs_saved_runs
def test_predict_refuses_without_an_authorized_matching_plan(tmp_path):
    built = []

    def factory(*args):
        built.append(args)
        raise AssertionError("a gateway must never be built here")

    plan = {
        "authorized": True, "authorized_by": "owner", "execution_id": "x", "out_dir": str(tmp_path / "out"), "manifest": str(MANIFEST),
        "manifest_sha256": hashlib.sha256(MANIFEST.read_bytes()).hexdigest(), "config": {},
        "prompt_identity_sha256": {t: Week2LLMGateway.prompt_identity_sha256(t) for t in driver.TASKS},
    }

    def write(name, body):
        path = tmp_path / name
        path.write_text(json.dumps(body), encoding="utf-8")
        return str(path), hashlib.sha256(path.read_bytes()).hexdigest()

    path, digest = write("ok.json", plan)
    assert driver.main(["predict", "--authorized-plan", path, "--plan-sha256", "0" * 64], gateway_factory=factory) == 3
    for name, body in (("unauthorized.json", {**plan, "authorized": False}), ("anonymous.json", {**plan, "authorized_by": " "}),
                       ("drifted_prompt.json", {**plan, "prompt_identity_sha256": {**plan["prompt_identity_sha256"], "alpha_classifier": "0" * 64}}),
                       ("drifted_sample.json", {**plan, "manifest_sha256": "0" * 64})):
        path, digest = write(name, body)
        assert driver.main(["predict", "--authorized-plan", path, "--plan-sha256", digest], gateway_factory=factory) == 3
    assert built == []
    assert not (tmp_path / "out").exists()


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
    assert stance["status"] == "DETERMINISTIC_BASELINE_ONLY"
    assert stance["method"].startswith("deterministic_baseline")
