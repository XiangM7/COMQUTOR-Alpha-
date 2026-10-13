"""P4 phase 2, session 6 (2026-10-12): criterion exp3 + prompt v3 + input v2 + output v3 -- the structured judgment.

What these tests prove: the identities and the version registry (v1 and v2 keep verifying as themselves), the element hint register
and its validation, the exact request (prompt v3, hints, mechanical text notes), the v3 contract -- structure, identity, vocabulary,
quotes, element ownership, the hit / no-hit consistency -- and that core / strong are DERIVED here from ownership (Q1) while weak /
none / UNRESOLVED stay the model's; that records are reproduced and shown under their own version; repaired samples, isolated and
not-sent samples. Answers are scripted or simulated TEST DATA: nothing here says how well a real model applies the criterion.
"""

from __future__ import annotations

import csv
import io
import json
from collections.abc import Callable
from pathlib import Path
from types import SimpleNamespace
from typing import Any

import pytest

from comqutor_alpha import (
    alpha_relevance_eval_prep as ep,
    alpha_relevance_evaluation as ev,
    alpha_relevance_experiment as ex,
)
from comqutor_alpha.alpha_library import alpha_relevance_elements as el
from comqutor_alpha.alpha_library.alpha_relevance_elements import (
    RelevanceElementsError,
    canonical_json_text,
    load_relevance_definitions,
    load_relevance_hints,
)
from comqutor_alpha.graph_engine.alpha_relevance_judgment import (
    RESULTS_FILENAME,
    verify_relevance_judgments,
    verify_relevance_records,
)
from comqutor_alpha.structure_engine import alpha_relevance_llm as rl

REPO_ROOT = Path(__file__).resolve().parents[1]
DEFS = load_relevance_definitions()
TICKER = "NVDA"
PHASE2 = REPO_ROOT / "docs/audit_artifacts/round_source_linking_t0_t2/round36_t1_migration_20261010/p4_phase2_eval_prep_20261012"
RETEST_V2 = PHASE2 / "exp2_v2_20261012/retest"
needs_phase2 = pytest.mark.skipif(not (PHASE2 / "sample/sample_manifest.json").is_file(), reason="the phase-2 evidence folder is local only")


# ----------------------------------------------------------------------------------------------------------- helpers
class _Message:
    def __init__(self, content: str) -> None:
        self.content = content


class ScriptedProvider:
    def __init__(self, responder: Callable[[dict[str, Any]], Any]) -> None:
        self.responder = responder
        self.calls = 0

    def invoke(self, prompt: str) -> _Message:
        self.calls += 1
        return _Message(json.dumps(self.responder(json.loads(prompt.split(rl.PROMPT_IDENTITY_SEPARATOR, 1)[1]))))


def owned(alpha_id: str, ownership: str) -> str:
    return next(e for e, o in DEFS[alpha_id].ownership.items() if o == ownership)


def item_for(text: str = "AI-server demand stayed strong through the quarter.", alpha_id: str = "A103", claim_id: str = "c1") -> rl.RelevanceRequestItem:
    items, _missing = rl.build_request_items([{"claim_id": claim_id, "claim": text, "match_status": "matched", "matched_alpha": alpha_id}],
                                             ticker=TICKER, definitions=DEFS)
    return items[0]


def st(quote: str, element: str | None = None, hit: bool = False, mode: str = "assertion", **overrides: Any) -> dict[str, Any]:
    return {"quote": quote, "object": "TEST object", "property": "TEST property", "mode": mode, "element_id": element, "hit": hit,
            "why": "TEST DATA", **overrides}


def v3(item: rl.RelevanceRequestItem, statements: list[dict[str, Any]], no_hit: str | None = None, outcome: str = "DETERMINED",
       unresolved: str | None = None, **extra: Any) -> dict[str, Any]:
    return {"claim_id": item.claim_id, "alpha_id": item.alpha_id, "outcome": outcome, "statements": statements, "no_hit_tier": no_hit,
            "basis": "scripted basis", "unresolved_reason": unresolved, **extra}


def make_run(root: Path, run_id: str = "run-a", pairs: list[tuple[str, str]] | None = None) -> Path:
    run_dir = root / run_id
    run_dir.mkdir(parents=True)
    pairs = pairs or [("AI-server demand stayed strong through the quarter.", "A103"), ("Retail sentiment on social media turned euphoric.", "A601")]
    matches = [{"claim_id": f"{run_id}:agent:report:claim:{i}", "claim": text, "evidence": text, "match_status": "matched",
                "matched_alpha": alpha, "ticker": TICKER} for i, (text, alpha) in enumerate(pairs, start=1)]
    (run_dir / "alpha_matches.json").write_text(json.dumps({"run_id": run_id, "ticker": TICKER, "matches": matches}), encoding="utf-8")
    (run_dir / "metadata.json").write_text(json.dumps({"run_id": run_id, "ticker": TICKER}), encoding="utf-8")
    return run_dir


def claim(run_id: str, i: int) -> str:
    return f"{run_id}:agent:report:claim:{i}"


def scripted_v3(payload: dict[str, Any]) -> dict[str, Any]:
    """TEST DATA: an A103 claim hits server demand (forecast mode), an A601 claim hits the strong sentiment element."""
    out = []
    for request in payload["items"]:
        element = "A103.server_demand" if request["alpha_id"] == "A103" else owned(request["alpha_id"], "strong")
        out.append({"claim_id": request["claim_id"], "alpha_id": request["alpha_id"], "outcome": "DETERMINED",
                    "statements": [st(request["claim_text"][:30], element, True, "forecast" if request["alpha_id"] == "A103" else "assertion")],
                    "no_hit_tier": None, "basis": "TEST DATA", "unresolved_reason": None})
    return {"items": out}


def judge(root: Path, run_id: str, responder: Callable[[dict[str, Any]], Any]) -> dict[str, Any]:
    return ex.judge_run_relevance(run_id, output_root=root, config=ex.P4_RELEVANCE_SIMULATED_20261012, provider=ScriptedProvider(responder))


def verify(root: Path, run_id: str):
    matches = json.loads((root / run_id / "alpha_matches.json").read_text(encoding="utf-8"))["matches"]
    return verify_relevance_judgments(root / run_id, run_id=run_id, ticker=TICKER, matches=matches)


def pin(monkeypatch: pytest.MonkeyPatch, version: str) -> None:
    for name, value in rl.version_constants(version).items():
        monkeypatch.setattr(rl, name, value)


# ----------------------------------------------------------------------------------------------------------- identity and registry
def test_v1_and_v2_identities_are_unchanged_and_carry_no_hints():
    v1, v2 = rl.task_identity(rl.PROMPT_VERSION_V1), rl.task_identity(rl.PROMPT_VERSION_V2)
    assert v1["prompt_sha256"] == "e173b92d842b6ac2b167671a8d5ef941c58eadbd5cdf91681e0c8add7f0128c4"
    assert v2["prompt_sha256"] == "9989394138bdd0146b768010bc70cb2929415f5c3bf8f801dc7c176030c3e37a"
    assert v1["input_schema_version"] == v2["input_schema_version"] == rl.INPUT_SCHEMA_V1
    assert "hints_version" not in v1 and "hints_version" not in v2


def test_v3_is_current_and_binds_the_hint_register():
    current = rl.task_identity()
    assert current == rl.task_identity(rl.PROMPT_VERSION_V3)
    assert (current["prompt_version"], current["criterion_version"], current["output_schema_version"], current["input_schema_version"]) == (
        rl.PROMPT_VERSION_V3, rl.CRITERION_EXP3, rl.OUTPUT_SCHEMA_V3, rl.INPUT_SCHEMA_V2)
    assert (current["hints_version"], current["hints_sha256"]) == (el.HINTS_VERSION, rl.current_hints().sha256)
    assert {v: rl.PROMPT_VERSIONS[v]["status"].split(" ")[0] for v in rl.PROMPT_VERSIONS} == {
        rl.PROMPT_VERSION_V1: "retired", rl.PROMPT_VERSION_V2: "retired", rl.PROMPT_VERSION_V3: "current"}
    assert all(rl.is_known_task_identity(rl.task_identity(v)) for v in rl.PROMPT_VERSIONS)


def test_a_changed_hint_register_is_a_new_identity(tmp_path, monkeypatch):
    table = json.loads(el.HINTS_PATH.read_text(encoding="utf-8"))
    table["hints"][0]["expressions"].append("demand for AI server racks")
    edited = tmp_path / "hints.json"
    edited.write_text(json.dumps(table), encoding="utf-8")
    before = rl.task_identity()
    monkeypatch.setattr(rl, "HINTS_PATH", edited)
    assert rl.task_identity()["hints_sha256"] != before["hints_sha256"]
    assert not rl.is_known_task_identity(before)  # an identity bound to the earlier register is no longer a registered identity


def test_version_constants_pin_a_version_completely(monkeypatch):
    pin(monkeypatch, rl.PROMPT_VERSION_V2)
    assert rl.task_identity() == rl.task_identity(rl.PROMPT_VERSION_V2)
    assert "element_hints" not in json.dumps(rl.batch_payload([item_for()]))  # input v1: no hints, no text notes


# ----------------------------------------------------------------------------------------------------------- the element hint register
def test_the_register_holds_only_definition_supported_hints_and_never_sends_the_not_registered_ones():
    hints = load_relevance_hints()
    sent = {h["element_id"]: h for hints_of in hints.by_alpha.values() for h in hints_of}
    assert set(sent) == {"A103.server_demand", "A201.semiconductor_demand", "A501.economic_slowdown"}
    assert "AI-server demand" in sent["A103.server_demand"]["expressions"]
    payload_text = json.dumps(rl.batch_payload([item_for(), item_for("x", "A102", "c2"), item_for("y", "A601", "c3")]))
    for not_registered in ("agentic AI demand", "inference market growth", "AI capex", "AI-server backlog", "current ratio"):
        assert not_registered not in payload_text
    assert all(set(h) == set(el.HINT_SENT_FIELDS) for h in sent.values())  # basis / source are documentation, not sent


@pytest.mark.parametrize(("edit", "code"), [
    (lambda t: t["hints"][0].update(element_id="A103.no_such_element"), "HINT_UNKNOWN_ELEMENT"),
    (lambda t: t["hints"][0].update(relation="proxy"), "HINT_RELATION_INVALID"),
    (lambda t: t["hints"][0].update(expressions=[]), "HINT_EXPRESSIONS_INVALID"),
    (lambda t: t["hints"][0].update(expressions=["AI-server demand", "ai-server   demand"]), "HINT_EXPRESSIONS_INVALID"),
    (lambda t: t["hints"][0].update(scope=""), "HINT_FIELDS_MISSING"),
    (lambda t: t["hints"][1].update(id=t["hints"][0]["id"]), "HINT_ID_INVALID"),
    (lambda t: t.update(schema="hints.v0"), "HINTS_SCHEMA_INVALID"),
    (lambda t: t.update(elements_version="alpha_relevance_elements.v0"), "HINTS_ELEMENTS_VERSION_MISMATCH"),
    (lambda t: t.pop("hints"), "HINTS_MISSING"),
])
def test_an_invalid_register_is_refused(tmp_path, edit, code):
    table = json.loads(el.HINTS_PATH.read_text(encoding="utf-8"))
    edit(table)
    bad = tmp_path / "hints.json"
    bad.write_text(json.dumps(table), encoding="utf-8")
    with pytest.raises(RelevanceElementsError) as exc:
        load_relevance_hints(bad, definitions=DEFS)
    assert exc.value.reason_code == code


@pytest.mark.parametrize("content", [None, "{not json"])
def test_an_unreadable_register_is_refused(tmp_path, content):
    bad = tmp_path / "hints.json"
    if content is not None:
        bad.write_text(content, encoding="utf-8")
    with pytest.raises(RelevanceElementsError) as exc:
        load_relevance_hints(bad, definitions=DEFS)
    assert exc.value.reason_code == "HINTS_UNREADABLE"


@needs_phase2
def test_the_register_does_not_change_any_definition_hash():
    manifest = json.loads((PHASE2 / "sample/sample_manifest.json").read_text(encoding="utf-8"))
    assert all(DEFS[s["target_alpha_id"]].sha256 == s["alpha_definition_sha256"] for s in manifest["samples"])


# ----------------------------------------------------------------------------------------------------------- prompt v3 and the request
@pytest.mark.parametrize("rule", [
    "every other explicit\nstatement in the same sentence",
    "Never stop at the first indicator",
    "A label such as \"Factor: X\", \"Theme: X\",\n    \"Category: X\" or \"Signal: X\" only names a topic",
    "\"assertion\" (as a fact), \"forecast\", \"probability\" (odds, likelihood or risk), \"condition\"",
    "\"hit\": true only when the object, the property and the scope",
    "A\nhint is only a hint",
    "a hint word\nappearing is never enough by itself",
    "never treat a forecast or a probability as the event having happened",
    "\"liquidity\" read from a company's current ratio is balance-sheet liquidity",
    "An indicator (a backlog, a share, an estimate, a price move) states its own property",
    "list the linking words as a statement with \"hit\" false",
    "A missing keyword is never by itself a reason for \"none\"",
    "belonging to the same industry, sector or asset class is never\n    by itself a reason for \"weak\"",
    "would change whether an element is hit or the weak / none decision",
    "the tier is derived from\nthe elements you find",
])
def test_prompt_v3_states_each_exp3_rule(rule):
    assert rule in rl.PROMPT_TEXT_V3


def test_prompt_v3_never_asks_the_model_for_core_or_strong():
    contract = rl.PROMPT_TEXT_V3.split("Return exactly one JSON object", 1)[1]
    assert '"tier"' not in contract and "core" not in contract and "strong" not in contract


class RecordingGateway:
    def __init__(self, answers: Callable[[dict[str, Any]], list[dict[str, Any]]]) -> None:
        self.answers = answers
        self.sent: list[dict[str, Any]] = []

    def invoke_prebuilt_json_prompt(self, **kwargs: Any) -> Any:
        self.sent.append(kwargs)
        return SimpleNamespace(validation_accepted=True, validated_output=self.answers(kwargs["payload_for_identity"]), provider_attempt_count=1,
                               trace_handle=SimpleNamespace(call_id=f"call-{len(self.sent)}"))

    def finalize_semantic_invocation(self, invocation: Any, **kwargs: Any) -> None:
        pass


def test_the_task_sends_prompt_v3_with_hints_and_text_notes():
    whole, cut = item_for(), item_for("OpenAI's custom chip and the Roundtable 100 ranking (No.", "A101", "c2")
    gateway = RecordingGateway(lambda payload: [])
    rl.judge_relevance([whole, cut], gateway, batch_size=1)
    first, second = gateway.sent
    identity = rl.task_identity()
    assert (first["prompt_version"], first["prompt_sha256"], first["input_schema_version"], first["output_schema_version"]) == (
        rl.PROMPT_VERSION_V3, identity["prompt_sha256"], rl.INPUT_SCHEMA_V2, rl.OUTPUT_SCHEMA_V3)
    payload = first["payload_for_identity"]
    assert first["prompt"] == rl.PROMPT_TEXT_V3 + rl.PROMPT_IDENTITY_SEPARATOR + canonical_json_text(payload)
    assert payload["criterion_version"] == rl.CRITERION_EXP3 and payload["hints_version"] == el.HINTS_VERSION
    assert [h["element_id"] for h in payload["alpha_definitions"][0]["element_hints"]] == ["A103.server_demand"]
    assert payload["items"][0]["text_notes"] == []
    assert second["payload_for_identity"]["items"][0]["text_notes"] == ["unclosed_parenthesis", "ends_with_abbreviation"]
    assert second["payload_for_identity"]["alpha_definitions"][0]["element_hints"] == []  # A101 has no registered hint


@pytest.mark.parametrize(("text", "notes"), [
    ("OpenAI's custom chip (Jalapeño, with Broadcom/Celestica) and the Roundtable 100 ranking (No.", ["unclosed_parenthesis", "ends_with_abbreviation"]),
    ("Revenue rose [per the filing", ["unclosed_bracket"]),
    ('The CEO said "demand is strong', ["unclosed_quote"]),
    ("The CEO said “demand is strong", ["unclosed_quote"]),
    ("Factor: Valuation; Signal: Bearish; Evidence: 24x forward earnings", []),  # a structured line without final punctuation
    ("Nasdaq best day in six weeks", []),  # a headline
    ("Macro fears are overblown.", []),
    ("Shares rose 3% vs. the index (after the call).", []),
])
def test_text_notes_only_flag_structural_signs_of_a_cut(text, notes):
    assert rl.text_completeness_notes(text) == notes


# ----------------------------------------------------------------------------------------------------------- output v3
def test_core_and_strong_are_derived_from_ownership_and_q1():
    item = item_for("Demand beat expectations and margins held at 75%.", "A301")
    core, strong = owned("A301", "core"), owned("A301", "strong")
    only_strong, reason = rl.validate_response_item(item, v3(item, [st("margins held at 75%", strong, True)]))
    assert reason is None and (only_strong["tier"], only_strong["tier_source"], only_strong["anchor_element_ids"]) == ("strong", rl.TIER_SOURCE_OWNERSHIP, [strong])
    both, _ = rl.validate_response_item(item, v3(item, [st("margins held at 75%", strong, True), st("Demand beat expectations", core, True)]))
    assert both["tier"] == "core" and both["anchor_element_ids"] == [strong, core]  # Q1: core wins


@pytest.mark.parametrize("mode", ["forecast", "probability", "condition", "negation", "question"])
def test_a_forecast_probability_condition_negation_or_question_can_state_an_element_and_its_mode_is_kept(mode):
    item = item_for("Recession odds fell to 8% this month.", "A501")
    validated, reason = rl.validate_response_item(item, v3(item, [st("Recession odds fell to 8%", "A501.economic_slowdown", True, mode)]))
    assert reason is None and validated["tier"] == "core"
    assert validated["anchor_evidence"] == [{"element_id": "A501.economic_slowdown", "quote": "Recession odds fell to 8%", "mode": mode}]


def test_weak_and_none_stay_the_models_judgment():
    item = item_for("Macro fears are overblown.", "A501")
    weak, reason = rl.validate_response_item(item, v3(item, [st("Macro fears", None, False)], "weak"))
    assert reason is None and (weak["tier"], weak["tier_source"], weak["anchor_element_ids"]) == ("weak", rl.TIER_SOURCE_MODEL_NO_HIT, [])
    none, _ = rl.validate_response_item(item, v3(item, [], "none"))
    assert none["tier"] == "none"
    considered, _ = rl.validate_response_item(item, v3(item, [st("Macro fears", "A501.economic_slowdown", False)], "none"))
    assert considered["tier"] == "none" and considered["statements"][0]["element_id"] == "A501.economic_slowdown"


def test_the_models_own_tier_field_is_ignored():
    item = item_for("The company appointed a new chief financial officer.", "A001")
    validated, reason = rl.validate_response_item(item, v3(item, [], "none", tier="core", anchor_element_ids=["A001.interest_rates"]))
    assert reason is None and validated["tier"] == "none" and validated["anchor_element_ids"] == []


def test_unresolved_keeps_what_is_missing_and_may_record_statements():
    item = item_for("The aggressive analyst's language is dangerous because it blurs that line.", "A601")
    validated, reason = rl.validate_response_item(item, v3(item, [st("blurs that line", None, False)], outcome="UNRESOLVED", unresolved="which line is meant"))
    assert reason is None and (validated["state"], validated["tier"], validated["unresolved_reason"]) == (rl.STATE_UNRESOLVED, None, "which line is meant")
    assert rl.validate_response_item(item, v3(item, [], outcome="UNRESOLVED", unresolved=None))[1] == rl.FAILURE_MALFORMED_RESPONSE
    assert rl.validate_response_item(item, v3(item, [], outcome="UNRESOLVED", unresolved="x", no_hit="weak"))[1] == rl.FAILURE_TIER_ANCHOR_INCONSISTENT
    assert rl.validate_response_item(item, v3(item, [], "none", unresolved="not allowed when determined"))[1] == rl.FAILURE_MALFORMED_RESPONSE


@pytest.mark.parametrize(("answer", "reason"), [
    (lambda i: v3(i, [st("AI-server demand", "A103.server_demand", True)], "weak"), rl.FAILURE_TIER_ANCHOR_INCONSISTENT),  # a hit with a no-hit tier
    (lambda i: v3(i, [st("AI-server demand", None, False)]), rl.FAILURE_TIER_ANCHOR_INCONSISTENT),  # nothing hit, no tier
    (lambda i: v3(i, [], "weak"), rl.FAILURE_EVIDENCE_INVALID),  # weak without the linking words
    (lambda i: v3(i, [st("AI-server demand", None, True)]), rl.FAILURE_ANCHOR_INVALID),  # a hit that names no element
    (lambda i: v3(i, [st("AI-server demand", "A201.semiconductor_demand", True)]), rl.FAILURE_ANCHOR_INVALID),  # another Alpha's element
    (lambda i: v3(i, [st("AI-server demand", "A103.unknown", False)], "none"), rl.FAILURE_ANCHOR_INVALID),
    (lambda i: v3(i, [st("server demand from hyperscalers", "A103.server_demand", True)]), rl.FAILURE_EVIDENCE_INVALID),  # not the claim's words
    (lambda i: v3(i, [st("AI-server demand", "A103.server_demand", True, "speculation")]), rl.FAILURE_INVALID_LABEL),
    (lambda i: v3(i, [], "strong"), rl.FAILURE_INVALID_LABEL),
    (lambda i: v3(i, [], "none", outcome="MAYBE"), rl.FAILURE_INVALID_LABEL),
    (lambda i: v3(i, [st("AI-server demand", "A103.server_demand", "yes")]), rl.FAILURE_MALFORMED_RESPONSE),
    (lambda i: v3(i, [st("AI-server demand", "A103.server_demand", True, object="")]), rl.FAILURE_MALFORMED_RESPONSE),
    (lambda i: v3(i, [{k: v for k, v in st("AI-server demand").items() if k != "why"}], "none"), rl.FAILURE_MALFORMED_RESPONSE),
    (lambda i: v3(i, [st("AI-server demand")] * (rl.MAX_STATEMENTS + 1), "weak"), rl.FAILURE_MALFORMED_RESPONSE),
    (lambda i: v3(i, "AI-server demand", "none"), rl.FAILURE_MALFORMED_RESPONSE),
    (lambda i: {k: v for k, v in v3(i, [], "none").items() if k != "no_hit_tier"}, rl.FAILURE_MALFORMED_RESPONSE),
    (lambda i: {**v3(i, [], "none"), "claim_id": "other"}, rl.FAILURE_IDENTITY_MISMATCH),
])
def test_the_v3_contract_refuses_what_it_can_check(answer, reason):
    item = item_for()
    assert rl.validate_response_item(item, answer(item))[1] == reason


def test_a_label_quote_passes_the_contract_because_the_contract_never_judges_semantics():
    item = item_for("Factor: Valuation; Evidence: 30.8x trailing is reasonable", "A304")
    validated, reason = rl.validate_response_item(item, v3(item, [st("Factor: Valuation", "A304.valuation", True)]))
    assert reason is None and validated["tier"] == "core"  # a semantic error is a rule-check finding, not a contract failure


def test_each_output_contract_is_checked_as_itself():
    item = item_for()
    v3_answer = v3(item, [st("AI-server demand", "A103.server_demand", True)])
    v2_answer = {"claim_id": item.claim_id, "alpha_id": item.alpha_id, "outcome": "DETERMINED", "tier": "core",
                 "anchor_element_ids": ["A103.server_demand"], "anchor_evidence": [{"element_id": "A103.server_demand", "quote": "AI-server demand"}],
                 "basis": "b", "unresolved_reason": None}
    assert rl.validate_response_item(item, v3_answer)[1] is None and rl.validate_response_item(item, v2_answer)[1] == rl.FAILURE_MALFORMED_RESPONSE
    assert rl.validate_response_item(item, v2_answer, output_schema_version=rl.OUTPUT_SCHEMA_V2)[1] is None
    assert rl.validate_response_item(item, v3_answer, output_schema_version=rl.OUTPUT_SCHEMA_V2)[1] == rl.FAILURE_MALFORMED_RESPONSE


def test_missing_and_duplicate_answers_stay_failed():
    a, b = item_for(claim_id="c1"), item_for(claim_id="c2")
    out = rl.judge_returned_items([a, b], [v3(a, [], "none"), v3(a, [], "none")])
    assert (out[a.key]["failure_reason"], out[b.key]["failure_reason"]) == (rl.FAILURE_DUPLICATE_RESULT, rl.FAILURE_MISSING_RESULT)


# ----------------------------------------------------------------------------------------------------------- the chain, the record, the trace
@pytest.fixture
def judged_v3(tmp_path):
    make_run(tmp_path)
    assert judge(tmp_path, "run-a", scripted_v3)["status"] == "ok"
    return tmp_path, "run-a"


def test_v3_records_verify_under_v3_with_their_statements(judged_v3):
    root, run_id = judged_v3
    views = verify(root, run_id).pairs
    server = views[(claim(run_id, 1), "A103")]
    assert (server["state"], server["tier"], server["tier_source"], server["anchor_element_ids"]) == (rl.STATE_JUDGED, "core", rl.TIER_SOURCE_OWNERSHIP, ["A103.server_demand"])
    assert server["statements"][0]["mode"] == "forecast" and server["versions"]["output_schema_version"] == rl.OUTPUT_SCHEMA_V3
    sentiment = views[(claim(run_id, 2), "A601")]
    assert (sentiment["tier"], sentiment["tier_source"]) == ("strong", rl.TIER_SOURCE_OWNERSHIP)


@pytest.mark.parametrize("edit", [
    lambda record: record["statements"][0].update(mode="assertion"),
    lambda record: record["statements"][0].update(why="an edited reason"),
    lambda record: record.update(tier_source=rl.TIER_SOURCE_MODEL_NO_HIT),
])
def test_an_edited_statement_or_tier_source_is_not_reproduced_by_the_ledger(judged_v3, edit):
    root, run_id = judged_v3
    path = root / run_id / RESULTS_FILENAME
    payload = json.loads(path.read_text(encoding="utf-8"))
    edit(payload["records"][0])
    path.write_text(json.dumps(payload), encoding="utf-8")
    assert verify(root, run_id).pairs[(claim(run_id, 1), "A103")]["reason"] == "ledger_label_mismatch"


def test_the_trace_shows_modes_statements_and_the_tier_source(judged_v3):
    from comqutor_alpha.api import evidence_trace as et

    root, run_id = judged_v3
    view = et._relevance_view(SimpleNamespace(relevance=verify(root, run_id), run_id=run_id, metadata={}), claim(run_id, 1), {"matched_alpha": "A103"})
    assert (view["tier"], view["tier_source"], view["source"]["prompt_version"]) == ("core", rl.TIER_SOURCE_OWNERSHIP, rl.PROMPT_VERSION_V3)
    assert view["anchors"][0]["evidence_quotes"] == ["AI-server demand stayed strong "[:30]] and view["anchors"][0]["evidence_modes"] == ["forecast"]
    assert view["statements"][0]["hit"] is True and view["statements"][0]["mode"] == "forecast"


def test_a_v2_judgment_is_stale_under_v3_and_still_verifies_as_v2(tmp_path, monkeypatch):
    with monkeypatch.context() as m:
        pin(m, rl.PROMPT_VERSION_V2)
        make_run(tmp_path)
        assert judge(tmp_path, "run-a", lambda payload: {"items": [
            {"claim_id": r["claim_id"], "alpha_id": r["alpha_id"], "outcome": "DETERMINED", "tier": "weak", "anchor_element_ids": [],
             "anchor_evidence": [], "basis": "TEST DATA", "unresolved_reason": None} for r in payload["items"]]})["status"] == "ok"
    views = verify(tmp_path, "run-a").pairs
    assert {(v["state"], v["reason"]) for v in views.values()} == {(rl.STATE_FAILED, "binding_stale")}
    assert {v["versions"]["prompt_version"] for v in views.values()} == {rl.PROMPT_VERSION_V2}
    matches = json.loads((tmp_path / "run-a" / "alpha_matches.json").read_text(encoding="utf-8"))["matches"]
    as_v2 = verify_relevance_records(tmp_path / "run-a", owner_run_id="run-a", pairs={(m["claim_id"], m["matched_alpha"]): (TICKER, m) for m in matches},
                                     identity=rl.task_identity(rl.PROMPT_VERSION_V2))
    assert {(v["state"], v["tier"]) for v in as_v2.pairs.values()} == {(rl.STATE_JUDGED, "weak")}


@pytest.mark.skipif(not (RETEST_V2 / "live_evaluation/evaluation_report.json").is_file(), reason="the v2 retest is local only")
def test_the_v2_development_retest_re_evaluates_to_identical_results_as_v2():
    manifest = json.loads((RETEST_V2 / "retest_sample/retest_manifest.json").read_text(encoding="utf-8"))
    plan = json.loads((RETEST_V2 / "plan/execution_plan.json").read_text(encoding="utf-8"))
    eval_dir = next((RETEST_V2 / "live").glob("relevance-eval-*"))
    report = ev.evaluate(manifest=manifest, plan=plan, eval_dir=eval_dir, review_a=RETEST_V2 / "retest_sample/reference_A_subset.csv")
    original = json.loads((RETEST_V2 / "live_evaluation/evaluation_report.json").read_text(encoding="utf-8"))
    for key in ("totals", "reference", "repeat_consistency", "samples", "verification", "thresholds", "banner"):
        assert report[key] == original[key], key
    assert report["inputs"]["task"] == rl.task_identity(rl.PROMPT_VERSION_V2)


# ----------------------------------------------------------------------------------------------------------- simulated provider v3
def _bucket_claim(bucket: int, alpha: str = "A103") -> str:
    import hashlib  # noqa: PLC0415

    return next(f"c{i}" for i in range(20_000) if int(hashlib.sha256(f"c{i}|{alpha}".encode()).hexdigest()[:8], 16) % 23 == bucket)


@pytest.mark.parametrize(("bucket", "state", "reason"), [
    (0, rl.STATE_JUDGED, None), (9, rl.STATE_JUDGED, None), (12, rl.STATE_JUDGED, None), (14, rl.STATE_UNRESOLVED, None),
    (16, rl.STATE_FAILED, rl.FAILURE_INVALID_LABEL), (17, rl.STATE_FAILED, rl.FAILURE_MISSING_RESULT), (18, rl.STATE_FAILED, rl.FAILURE_DUPLICATE_RESULT),
    (19, rl.STATE_FAILED, rl.FAILURE_ANCHOR_INVALID), (20, rl.STATE_FAILED, rl.FAILURE_EVIDENCE_INVALID), (21, rl.STATE_FAILED, rl.FAILURE_EVIDENCE_INVALID),
    (22, rl.STATE_FAILED, rl.FAILURE_TIER_ANCHOR_INCONSISTENT),
])
def test_the_simulated_provider_answers_exp3_requests_in_output_v3(bucket, state, reason):
    item = item_for("AI-server demand stayed strong through the quarter.", "A103", _bucket_claim(bucket))
    provider = ex.SimulatedRelevanceProvider()
    out = json.loads(provider.invoke("x" + rl.PROMPT_IDENTITY_SEPARATOR + json.dumps(rl.batch_payload([item]))).content)["items"]
    result = rl.judge_returned_items([item], out)[item.key]
    assert (result["state"], result.get("failure_reason")) == (state, reason)


def test_the_simulated_provider_keeps_v2_answers_for_exp2_requests(monkeypatch):
    pin(monkeypatch, rl.PROMPT_VERSION_V2)
    item = item_for(claim_id=_bucket_claim(0))
    out = json.loads(ex.SimulatedRelevanceProvider().invoke("x" + rl.PROMPT_IDENTITY_SEPARATOR + json.dumps(rl.batch_payload([item]))).content)["items"]
    assert "anchor_evidence" in out[0] and "statements" not in out[0]


# ----------------------------------------------------------------------------------------------------------- repaired, isolated and not-sent samples
def _source_run(tmp_path: Path) -> tuple[Path, dict[str, Any]]:
    run = tmp_path / "run-src"
    run.mkdir()
    report = "4. **Competitive positioning.** OpenAI's custom chip and the ranking (No. 76) introduce mild noise, though neither is a threat."
    (run / "raw_agent_outputs.json").write_text(json.dumps({"agent_outputs": [{"raw_output": report}]}), encoding="utf-8")
    original = {"sample_id": "S900", "claim_id": "run-src:agent:report:claim:1", "claim_text": "OpenAI's custom chip and the ranking (No.",
                "claim_text_sha256": rl.claim_text_sha256({"claim": "OpenAI's custom chip and the ranking (No."}), "ticker": TICKER,
                "target_alpha_id": "A101", "alpha_definition_sha256": DEFS["A101"].sha256, "source_run_id": "run-src", "agent": "agent",
                "selection": {"primary_stratum": "ORDINARY"}}
    return run, original


def test_a_repaired_sample_is_a_new_sample_read_from_its_saved_source(tmp_path):
    run, original = _source_run(tmp_path)
    report = json.loads((run / "raw_agent_outputs.json").read_text(encoding="utf-8"))["agent_outputs"][0]["raw_output"]
    start = report.index("OpenAI")
    end = report.index("threat.") + len("threat.")
    repaired = ep.build_repaired_sample(original, run_path=run, source_file="raw_agent_outputs.json", json_path=["agent_outputs", 0, "raw_output"],
                                        char_start=start, char_end=end, defect="TEST: split at 'No.'", method="TEST")
    assert repaired["sample_id"] == "S900R" and repaired["claim_id"].endswith(":repaired:1") and repaired["claim_text"].endswith("neither is a threat.")
    assert repaired["claim_text_sha256"] == rl.claim_text_sha256({"claim": repaired["claim_text"]}) and original["claim_text"] == "OpenAI's custom chip and the ranking (No."
    assert repaired["repair"]["original_claim_text"] == original["claim_text"] and rl.text_completeness_notes(repaired["claim_text"]) == []
    assert ep.repaired_text_from_source(run, repaired["repair"]) == repaired["claim_text"]
    (run / "raw_agent_outputs.json").write_text("{}", encoding="utf-8")  # the source changed: the repair can no longer be confirmed
    assert ep.repaired_text_from_source(run, repaired["repair"]) is None
    with pytest.raises(ValueError, match="REPAIR_SOURCE_UNREADABLE"):
        ep.build_repaired_sample(original, run_path=run, source_file="raw_agent_outputs.json", json_path=["agent_outputs", 0, "raw_output"],
                                 char_start=start, char_end=end, defect="d", method="m")


def test_a_repaired_sample_is_re_verified_against_its_source_before_sending(tmp_path, monkeypatch):
    run, original = _source_run(tmp_path)
    (run / "alpha_matches.json").write_text(json.dumps({"matches": []}), encoding="utf-8")  # makes it a saved run the verifier can find
    monkeypatch.setattr(ep, "SAVED_RUN_ROOTS", (tmp_path,))
    report = json.loads((run / "raw_agent_outputs.json").read_text(encoding="utf-8"))["agent_outputs"][0]["raw_output"]
    start = report.index("OpenAI")
    repaired = ep.build_repaired_sample(original, run_path=run, source_file="raw_agent_outputs.json", json_path=["agent_outputs", 0, "raw_output"],
                                        char_start=start, char_end=report.index("threat.") + len("threat."), defect="TEST", method="TEST")
    assert ep.verify_manifest_sources({"samples": [repaired]}) == []
    assert ep.verify_manifest_sources({"samples": [{**repaired, "claim_text": repaired["claim_text"] + " EDITED"}]}) == [
        {"sample_id": "S900R", "problem": "SOURCE_REPAIR_CHANGED"}]


def test_a_repair_must_extend_the_original_sentence(tmp_path):
    run, original = _source_run(tmp_path)
    with pytest.raises(ValueError, match="REPAIR_NOT_AN_EXTENSION_OF_THE_ORIGINAL"):
        ep.build_repaired_sample(original, run_path=run, source_file="raw_agent_outputs.json", json_path=["agent_outputs", 0, "raw_output"],
                                 char_start=0, char_end=40, defect="d", method="m")


@needs_phase2
def test_the_real_s047_truncation_is_confirmed_and_recovered_from_the_saved_raw_output():
    manifest = json.loads((PHASE2 / "sample/sample_manifest.json").read_text(encoding="utf-8"))
    s047 = next(s for s in manifest["samples"] if s["sample_id"] == "S047")
    run = ep._run_path(s047["source_run_id"])  # noqa: SLF001
    if run is None:
        pytest.skip("the saved run is local only")
    report = json.loads((run / "raw_agent_outputs.json").read_text(encoding="utf-8"))["agent_outputs"][1]["raw_output"]
    start = report.index(s047["claim_text"])
    end = report.index("threat to NVDA.", start) + len("threat to NVDA.")
    repaired = ep.build_repaired_sample(s047, run_path=run, source_file="raw_agent_outputs.json", json_path=["agent_outputs", 1, "raw_output"],
                                        char_start=start, char_end=end, defect="split at 'No.'", method="read from the saved raw output")
    assert repaired["claim_text"].startswith(s047["claim_text"] + " 76)") and rl.text_completeness_notes(s047["claim_text"]) == ["unclosed_parenthesis", "ends_with_abbreviation"]


def test_isolated_and_not_sent_samples_are_planned_and_reported_honestly(tmp_path):
    items = [("S001", "A103", "AI-server demand stayed strong."), ("S002", "A103", "Server orders slowed."), ("S003", "A103", "Power demand rose."),
             ("S004", "A103", "Networking orders rose.")]
    manifest = {"content_sha256": "TEST", "sample_count": 4, "samples": [
        {"sample_id": sid, "claim_id": f"c-{sid}", "target_alpha_id": alpha, "ticker": TICKER, "claim_text": text,
         "claim_text_sha256": rl.claim_text_sha256({"claim": text}), "alpha_definition_sha256": DEFS[alpha].sha256,
         "selection": {"primary_stratum": "ORDINARY"}} for sid, alpha, text in items]}
    batches = ep.plan_batches(manifest, DEFS, batch_size=4, isolate=["S002"], exclude=["S004"])
    assert [b["sample_ids"] for b in batches] == [["S001", "S003"], ["S002"]]
    with pytest.raises(ValueError, match="PLAN_SAMPLE_SELECTION_INVALID"):
        ep.plan_batches(manifest, DEFS, batch_size=4, isolate=["S002"], exclude=["S002"])
    plan = ep.build_plan(manifest, DEFS, manifest_file_sha256="x", reference={"basis": {"chars_per_input_token": {"median": 3.6, "min": 3.5, "max": 3.9},
                         "output_tokens_per_item": {"median": 1000.0, "max": 3000.0}, "latency_seconds_per_item": {"median": 9.0, "max": 30.0}}},
                         provider=ep.LIVE_PROVIDER, model=ep.LIVE_MODEL, batch_size=4, repeat_every=2, timeout_seconds=300.0, max_output_tokens=16384,
                         repo_root=REPO_ROOT, isolate=["S002"], not_sent=[{"sample_id": "S004", "reason": "TEST: confirmed unjudgeable", "evidence": "TEST"}])
    assert plan["not_sent_count"] == 1 and plan["isolated_samples"] == ["S002"]
    assert [(r["sample_id"], r["status"], r["round_1_batch"]) for r in plan["sample_table"]] == [
        ("S001", "PLANNED", "B01"), ("S002", "PLANNED", "B02"), ("S003", "PLANNED", "B01"), ("S004", "NOT_SENT", None)]
    with pytest.raises(ValueError, match="NOT_SENT_REASON_MISSING"):
        ep.build_plan(manifest, DEFS, manifest_file_sha256="x", reference=plan["reference"], provider=ep.LIVE_PROVIDER, model=ep.LIVE_MODEL, batch_size=4,
                      repeat_every=2, timeout_seconds=300.0, max_output_tokens=16384, repo_root=REPO_ROOT, not_sent=[{"sample_id": "S004", "reason": " "}])
    eval_id = "relevance-eval-TEST"
    (tmp_path / eval_id).mkdir()
    (tmp_path / eval_id / ev.EVAL_RECORD_FILENAME).write_text(json.dumps({"plan_sha256": plan["plan_sha256"], "sample_manifest_content_sha256": "TEST",
                                                                         "evaluation_id": eval_id}), encoding="utf-8")
    views = ev.load_execution(tmp_path / eval_id, manifest, plan, DEFS)["rounds"][1]["views"]
    assert (views["S004"]["model_outcome"], views["S004"]["reason"], views["S004"]["reason_detail"]) == (ev.NOT_SENT, "not_sent_by_plan", "TEST: confirmed unjudgeable")
    assert ev.round_totals(views)["planned_pairs"] == 4  # the not-sent sample stays in the totals


def test_the_input_quality_table_never_excludes_a_sample():
    manifest = {"samples": [{"sample_id": "S1", "target_alpha_id": "A101", "claim_text": "the ranking (No."},
                            {"sample_id": "S2", "target_alpha_id": "A501", "claim_text": "Nasdaq best day in six weeks"},
                            {"sample_id": "S3", "target_alpha_id": "A501", "claim_text": "Macro fears are overblown."}]}
    rows = {r["sample_id"]: r for r in ep.input_quality_rows(manifest)}
    assert rows["S1"]["text_notes"] == ["unclosed_parenthesis", "ends_with_abbreviation"]
    assert rows["S2"]["text_notes"] == [] and rows["S2"]["report_only_notes"] == ["no_terminal_punctuation"]
    assert rows["S3"]["text_notes"] == rows["S3"]["report_only_notes"] == []
    assert {r["handling"] for r in rows.values()} == {"sent as is; notes are hints only"}


def test_a_rulecheck_plan_is_built_under_v3_and_pins_the_hint_register():
    items = [("S001", "A103", "AI-server demand stayed strong through the quarter."), ("S002", "A103", "Server orders slowed sharply this month."),
             ("S003", "A501", "Recession odds fell to 8% this month.")]
    manifest = {"schema": ep.SAMPLE_SCHEMA, "sample_count": 3, "samples": [
        {"sample_id": sid, "claim_id": f"c-{sid}", "target_alpha_id": alpha, "ticker": TICKER, "claim_text": text, "source_run_id": "none",
         "claim_text_sha256": rl.claim_text_sha256({"claim": text}), "alpha_definition_sha256": DEFS[alpha].sha256,
         "selection": {"primary_stratum": "ORDINARY"}} for sid, alpha, text in items]}
    manifest["content_sha256"] = ep.manifest_content_sha256(manifest)
    plan = ep.build_plan(manifest, DEFS, manifest_file_sha256="x", reference={"basis": {"chars_per_input_token": {"median": 3.6, "min": 3.5, "max": 3.9},
                         "output_tokens_per_item": {"median": 1000.0, "max": 3000.0}, "latency_seconds_per_item": {"median": 9.0, "max": 30.0}}},
                         provider=ep.LIVE_PROVIDER, model=ep.LIVE_MODEL, batch_size=ep.LIVE_BATCH_SIZE, repeat_every=1, timeout_seconds=ep.LIVE_TIMEOUT_SECONDS,
                         max_output_tokens=ep.LIVE_MAX_OUTPUT_TOKENS, repo_root=REPO_ROOT, experiment_config=ex.P4_RELEVANCE_LIVE_RULECHECK_V3_20261012.name,
                         purpose="TEST", purpose_kind=ep.RETEST_PURPOSE_KIND, quality_thresholds=ep.RETEST_THRESHOLDS, isolate=["S002"])
    assert plan["task"] == rl.task_identity() and plan["task"]["prompt_version"] == rl.PROMPT_VERSION_V3
    assert "comqutor_alpha/alpha_library/alpha_relevance_hints_v1.json" in plan["code_identity"]["files"]


@needs_phase2
def test_the_rule_check_relies_on_the_claims_own_words():
    """The rule-check validation reads quotes; the claim texts it relies on must be the final manifest's (never retyped)."""
    manifest = {s["sample_id"]: s for s in json.loads((PHASE2 / "sample/sample_manifest.json").read_text(encoding="utf-8"))["samples"]}
    for sid, fragment in (("S027", "Strong liquidity"), ("S055", "AI-server demand"), ("S005", "as the market expands"), ("S017", "a real demand driver"),
                          ("S001", "Factor: Valuation"), ("S032", "89% odds of NO cuts"), ("S039", "US recession by end of 2026")):
        assert rl.quote_in_text(fragment, manifest[sid]["claim_text"]), sid


def _googl_runs() -> list[Path]:
    runs = []
    for root in ep.SAVED_RUN_ROOTS:
        for path in sorted(root.iterdir()) if root.is_dir() else []:
            meta = path / "metadata.json"
            if ep.is_original_run_dir(path) and meta.is_file() and json.loads(meta.read_text(encoding="utf-8")).get("ticker") == "GOOGL":
                runs.append(path)
    return runs


GOOGL_RUNS = _googl_runs()


@pytest.fixture(scope="module")
def small_manifest() -> dict[str, Any]:
    if len(GOOGL_RUNS) < 2:
        pytest.skip("the saved GOOGL runs are not present (local run data)")
    selection = ep.select_sample(ep.scan_candidates(GOOGL_RUNS, DEFS), quotas={ep.STRATUM_ORDINARY: 9})
    return ep.build_manifest(selection, DEFS, pool_runs=[r.name for r in GOOGL_RUNS])


def test_a_plan_with_isolated_and_not_sent_samples_rehearses_end_to_end_under_v3(tmp_path, small_manifest):
    from datetime import datetime, timedelta, timezone  # noqa: PLC0415

    now = datetime(2026, 10, 12, 12, 0, tzinfo=timezone.utc)
    ids = sorted(s["sample_id"] for s in small_manifest["samples"])
    manifest_path = tmp_path / "manifest.json"
    manifest_sha = ep.write_json(manifest_path, small_manifest)
    plan = ep.build_plan(small_manifest, DEFS, manifest_file_sha256=manifest_sha, reference={"basis": {"chars_per_input_token": {"median": 3.6, "min": 3.5, "max": 3.9},
                         "output_tokens_per_item": {"median": 1000.0, "max": 3000.0}, "latency_seconds_per_item": {"median": 9.0, "max": 30.0}}},
                         provider=ep.LIVE_PROVIDER, model=ep.LIVE_MODEL, batch_size=ep.LIVE_BATCH_SIZE, repeat_every=1, timeout_seconds=ep.LIVE_TIMEOUT_SECONDS,
                         max_output_tokens=ep.LIVE_MAX_OUTPUT_TOKENS, repo_root=REPO_ROOT, experiment_config=ex.P4_RELEVANCE_LIVE_RULECHECK_V3_20261012.name,
                         purpose="TEST", purpose_kind=ep.RETEST_PURPOSE_KIND, quality_thresholds=ep.RETEST_THRESHOLDS, isolate=[ids[0]],
                         not_sent=[{"sample_id": ids[1], "reason": "TEST: confirmed unjudgeable", "evidence": "TEST"}])
    plan_path = tmp_path / "plan.json"
    ep.write_json(plan_path, plan)
    auth_path = tmp_path / "auth.json"
    ep.write_json(auth_path, ep.rehearsal_authorization(plan, authorized_by="TEST DATA", authorized_at=(now - timedelta(hours=1)).isoformat(),
                                                        valid_until=(now + timedelta(hours=1)).isoformat()))
    result = ex.run_relevance_evaluation_plan(plan_path=plan_path, manifest_path=manifest_path, authorization_path=auth_path, eval_root=tmp_path / "ev",
                                              mode=ex.EVAL_MODE_REHEARSAL, now=now, config=ex.P4_RELEVANCE_LIVE_RULECHECK_V3_20261012,
                                              provider=ex.SimulatedRelevanceProvider())
    assert result["status"] == "ok" and result["requests_sent"] == plan["request_cap"]
    record = json.loads((Path(result["evaluation_dir"]) / ex.EVAL_RECORD_FILENAME).read_text(encoding="utf-8"))
    assert record["not_sent_by_plan"] == plan["not_sent"]
    sheet = tmp_path / "sheet.csv"
    sheet.write_text(ep.render_csv(ep.blind_review_rows(small_manifest, DEFS), ep.REVIEW_COLUMNS), encoding="utf-8")
    report = ev.evaluate(manifest=small_manifest, plan=plan, eval_dir=result["evaluation_dir"], review_a=sheet)
    row = next(r for r in report["samples"] if r["sample_id"] == ids[1])
    assert (row["round_1_outcome"], row["round_1_reason"]) == (ev.NOT_SENT, "not_sent_by_plan")
    assert report["totals"]["round_1"]["planned_pairs"] == small_manifest["sample_count"] and report["inputs"]["task"]["prompt_version"] == rl.PROMPT_VERSION_V3
    assert all(t["failure_categories"]["read_time_verification"] == 0 for t in report["totals"].values())


@needs_phase2
def test_a_repaired_sample_is_verified_against_its_saved_source():
    manifest = json.loads((PHASE2 / "sample/sample_manifest.json").read_text(encoding="utf-8"))
    s047 = next(s for s in manifest["samples"] if s["sample_id"] == "S047")
    run = ep._run_path(s047["source_run_id"])  # noqa: SLF001
    if run is None:
        pytest.skip("the saved run is local only")
    report = json.loads((run / "raw_agent_outputs.json").read_text(encoding="utf-8"))["agent_outputs"][1]["raw_output"]
    start = report.index(s047["claim_text"])
    repaired = ep.build_repaired_sample(s047, run_path=run, source_file="raw_agent_outputs.json", json_path=["agent_outputs", 1, "raw_output"],
                                        char_start=start, char_end=report.index("threat to NVDA.", start) + len("threat to NVDA."), defect="d", method="m")
    assert ep.verify_manifest_sources({"samples": [repaired]}) == []
    assert ep.verify_manifest_sources({"samples": [{**repaired, "claim_text": repaired["claim_text"] + " EDITED"}]}) == [
        {"sample_id": "S047R", "problem": "SOURCE_REPAIR_CHANGED"}]


def _sheet_rows(text: str) -> list[dict[str, str]]:
    return list(csv.DictReader(io.StringIO(text.lstrip("﻿"))))


def test_review_sheet_subset_can_skip_a_repaired_sample_without_inventing_a_row():
    rows = [{"sample_id": "S047", "tier": "core"}, {"sample_id": "S048", "tier": "weak"}]
    text = ep.render_csv(rows, ["sample_id", "tier"])
    subset, check = ep.review_sheet_subset(text, ["S047"])
    assert [r["sample_id"] for r in _sheet_rows(subset)] == ["S047"] and check["every_field_identical_to_source"] is True
