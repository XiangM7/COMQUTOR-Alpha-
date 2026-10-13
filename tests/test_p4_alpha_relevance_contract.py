"""P4 phase 1 (2026-10-12): the experimental Alpha relevance judgment -- task contract, binding, ledger, states and the default-off switch.

Every judgment here comes from a SCRIPTED provider behind the real ``Week2LLMGateway`` (retry / timeout / semantic recorder unchanged),
writing real ``alpha_relevance_ledger/`` records into temporary run directories. Nothing calls a model, a search or a data provider. The
answers are scripted per test to exercise the contract; no saved sample's answer is asserted as a fact.
"""

from __future__ import annotations

import json
import time
from collections.abc import Callable
from pathlib import Path
from typing import Any

import pytest
import yaml

from comqutor_alpha import alpha_relevance_experiment as ex
from comqutor_alpha.alpha_library.alpha_loader import TAXONOMY_PATH
from comqutor_alpha.alpha_library.alpha_relevance_elements import (
    CORE_LISTS,
    ELEMENTS_PATH,
    STRONG_LISTS,
    RelevanceElementsError,
    load_relevance_definitions,
)
from comqutor_alpha.graph_engine.alpha_relevance_judgment import (
    LEDGER_DIRNAME,
    RESULTS_FILENAME,
    verify_relevance_judgments,
)
from comqutor_alpha.llm_runtime.contracts import SEMANTIC_TASKS
from comqutor_alpha.structure_engine import alpha_relevance_llm as rl

REPO_ROOT = Path(__file__).resolve().parents[1]
DEFS = load_relevance_definitions()
TICKER = "NVDA"


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
    """Answers each call with ``responder(batch payload)``: a dict (sent as JSON), a raw string, or an exception (raised)."""

    def __init__(self, responder: Callable[[dict[str, Any]], Any]) -> None:
        self.responder = responder
        self.calls = 0

    def invoke(self, prompt: str) -> _Message:
        self.calls += 1
        payload = json.loads(prompt.split(rl.PROMPT_IDENTITY_SEPARATOR, 1)[1])
        out = self.responder(payload)
        if isinstance(out, BaseException):
            raise out
        return _Message(out if isinstance(out, str) else json.dumps(out))


class ExplodingProvider:
    calls = 0

    def invoke(self, prompt: str) -> Any:  # pragma: no cover - must never run
        type(self).calls += 1
        raise AssertionError("the relevance task must not call a provider here")


def answer(claim_id: str, alpha_id: str, outcome: str = "DETERMINED", tier: str | None = "weak", anchors: list[str] | None = None,
           basis: str = "scripted basis", unresolved: str | None = None, quote: str | None = None) -> dict[str, Any]:
    """An entry of the current output contract (v2): every anchor carries a quote. ``quote`` None = the claim's own words, filled in
    by ``by_pair`` from the request (a direct validator call passes the item's text)."""
    anchors = anchors or []
    return {"claim_id": claim_id, "alpha_id": alpha_id, "outcome": outcome, "tier": tier, "anchor_element_ids": anchors,
            "anchor_evidence": [{"element_id": a, "quote": quote} for a in anchors], "basis": basis, "unresolved_reason": unresolved}


def _quoted(entry: Any, claim_text: str) -> Any:
    if not isinstance(entry, dict) or not isinstance(entry.get("anchor_evidence"), list):
        return entry
    return {**entry, "anchor_evidence": [{**e, "quote": claim_text if e.get("quote") is None else e["quote"]} for e in entry["anchor_evidence"]]}


def by_pair(answers: dict[tuple[str, str], Any]) -> Callable[[dict[str, Any]], dict[str, Any]]:
    """A responder that returns the scripted entry (or entries) of every requested pair it knows, and nothing for the others."""
    def responder(payload: dict[str, Any]) -> dict[str, Any]:
        items: list[Any] = []
        for request in payload["items"]:
            scripted = answers.get((request["claim_id"], request["alpha_id"]))
            if scripted is None:
                continue
            items.extend(_quoted(entry, request["claim_text"]) for entry in (scripted if isinstance(scripted, list) else [scripted]))
        return {"items": items}
    return responder


def core_of(alpha_id: str) -> list[str]:
    return [e for e, o in DEFS[alpha_id].ownership.items() if o == "core"]


def strong_of(alpha_id: str) -> list[str]:
    return [e for e, o in DEFS[alpha_id].ownership.items() if o == "strong"]


def make_run(root: Path, run_id: str = "run-a", pairs: list[tuple[str, str]] | None = None) -> Path:
    """A minimal saved run: matched claims (claim text, alpha) plus one unmatched claim."""
    run_dir = root / run_id
    run_dir.mkdir(parents=True)
    pairs = pairs or [("Demand for data-center GPUs beat expectations again.", "A301"),
                      ("Gross margins held near 75% for the quarter.", "A301"),
                      ("Retail sentiment on social media turned euphoric.", "A601")]
    matches = [{"claim_id": f"{run_id}:agent:report:claim:{i}", "claim": text, "evidence": text, "match_status": "matched",
                "matched_alpha": alpha, "ticker": TICKER} for i, (text, alpha) in enumerate(pairs, start=1)]
    matches.append({"claim_id": f"{run_id}:agent:report:claim:99", "claim": "An unrelated remark.", "match_status": "unmatched",
                    "matched_alpha": None, "ticker": TICKER})
    (run_dir / "alpha_matches.json").write_text(json.dumps({"run_id": run_id, "ticker": TICKER, "matches": matches}), encoding="utf-8")
    (run_dir / "metadata.json").write_text(json.dumps({"run_id": run_id, "ticker": TICKER}), encoding="utf-8")
    return run_dir


def claim(run_id: str, i: int) -> str:
    return f"{run_id}:agent:report:claim:{i}"


def judge(root: Path, run_id: str, responder: Callable[[dict[str, Any]], Any], **config_overrides: Any) -> dict[str, Any]:
    config = ex.P4_RELEVANCE_SIMULATED_20261012
    if config_overrides:
        config = ex.RelevanceExperimentConfig(**{**config.__dict__, **config_overrides})
    return ex.judge_run_relevance(run_id, output_root=root, config=config, provider=ScriptedProvider(responder))


def verify(root: Path, run_id: str, **kwargs: Any):
    matches = json.loads((root / run_id / "alpha_matches.json").read_text(encoding="utf-8"))["matches"]
    return verify_relevance_judgments(root / run_id, run_id=run_id, ticker=TICKER, matches=matches, **kwargs)


def item_for(alpha_id: str = "A301", claim_id: str = "c1", text: str = "Some claim.") -> rl.RelevanceRequestItem:
    items, _missing = rl.build_request_items(
        [{"claim_id": claim_id, "claim": text, "match_status": "matched", "matched_alpha": alpha_id}], ticker=TICKER, definitions=DEFS)
    return items[0]


# ----------------------------------------------------------------------------------------------------------- definition anchors
def test_ownership_is_derived_from_where_each_element_has_its_head_in_the_taxonomy():
    taxonomy = {a["alpha_id"]: a for a in yaml.safe_load(TAXONOMY_PATH.read_text(encoding="utf-8"))["alphas"]}
    for alpha_id, definition in DEFS.items():
        for element_id, heads in definition.occurrences.items():
            in_core = any(name in CORE_LISTS for name, _ in heads)
            assert definition.ownership[element_id] == ("core" if in_core else "strong"), element_id
            for name, phrase in heads:  # every anchor phrase is the taxonomy's own text
                text = taxonomy[alpha_id][name]
                assert phrase.casefold() in (text.casefold() if isinstance(text, str) else [e.casefold() for e in text]), (element_id, phrase)
        shadowed = {s["phrase"] for s in definition.payload["shadowed_confirmation_entries"]}
        expected = {p for e, heads in definition.occurrences.items() if definition.ownership[e] == "core" for n, p in heads if n in STRONG_LISTS}
        assert shadowed == expected, alpha_id
    # the documented conflict: "EPS revisions" is in A301's core thesis, so its confirmation entry is shadowed (never strong)
    assert DEFS["A301"].ownership["A301.eps_revisions"] == "core"
    assert {"phrase": "EPS revisions rise", "element_id": "A301.eps_revisions"} in DEFS["A301"].payload["shadowed_confirmation_entries"]


def test_the_local_canonical_hashing_is_byte_identical_to_the_semantic_runtime():
    from comqutor_alpha.alpha_library import alpha_relevance_elements as el
    from comqutor_alpha.llm_runtime import canonical_json as runtime

    items, _missing = rl.build_request_items(
        [{"claim_id": "c1", "claim": "Demand beat — guidance raised 12%.", "match_status": "matched", "matched_alpha": "A301"}],
        ticker=TICKER, definitions=DEFS)
    samples = [{"elements_version": "v", "taxonomy_content_version": "1.1.0", "definition": d.payload} for d in DEFS.values()]
    samples.append(rl.batch_payload(items))
    for value in samples:
        assert el.canonical_json_text(value) == runtime.canonical_json_text(value)
        assert el.sha256_canonical_json(value) == runtime.sha256_canonical_json(value)
    assert el.sha256_text(rl.prompt_identity_text()) == runtime.sha256_text(rl.prompt_identity_text())


def test_a_phrase_missing_from_the_taxonomy_or_a_taxonomy_version_change_refuses_the_table(tmp_path):
    table = json.loads(ELEMENTS_PATH.read_text(encoding="utf-8"))
    table["alphas"]["A301"]["elements"][0]["occurrences"][0]["phrase"] = "demand that the taxonomy never states"
    bad = tmp_path / "elements.json"
    bad.write_text(json.dumps(table), encoding="utf-8")
    with pytest.raises(RelevanceElementsError) as exc:
        load_relevance_definitions(bad)
    assert exc.value.reason_code == "ELEMENT_PHRASE_NOT_IN_TAXONOMY"
    table = json.loads(ELEMENTS_PATH.read_text(encoding="utf-8"))
    table["taxonomy_content_version"] = "0.0.0"
    bad.write_text(json.dumps(table), encoding="utf-8")
    with pytest.raises(RelevanceElementsError) as exc:
        load_relevance_definitions(bad)
    assert exc.value.reason_code == "ELEMENTS_TAXONOMY_VERSION_MISMATCH"


def test_the_definition_hash_moves_with_the_taxonomy_text(tmp_path):
    taxonomy = yaml.safe_load(TAXONOMY_PATH.read_text(encoding="utf-8"))
    next(a for a in taxonomy["alphas"] if a["alpha_id"] == "A301")["keywords"].append("an extra topic term")
    edited = tmp_path / "taxonomy.yaml"
    edited.write_text(yaml.safe_dump(taxonomy, sort_keys=False, allow_unicode=True), encoding="utf-8")
    changed = load_relevance_definitions(taxonomy_path=edited)
    assert changed["A301"].sha256 != DEFS["A301"].sha256
    assert changed["A501"].sha256 == DEFS["A501"].sha256  # only the edited Alpha's definition moved


# ----------------------------------------------------------------------------------------------------------- response contract
@pytest.mark.parametrize("tier", rl.TIERS)
def test_each_of_the_four_tiers_is_accepted_with_consistent_anchors(tier):
    item = item_for()
    anchors = {"core": core_of("A301")[:1], "strong": strong_of("A301")[:1], "weak": [], "none": []}[tier]
    validated, reason = rl.validate_response_item(item, answer(item.claim_id, "A301", tier=tier, anchors=anchors, quote=item.claim_text))
    assert reason is None and validated["state"] == rl.STATE_JUDGED and validated["tier"] == tier


def test_unresolved_is_a_state_without_a_tier_and_needs_a_reason():
    item = item_for()
    validated, reason = rl.validate_response_item(item, answer(item.claim_id, "A301", outcome="UNRESOLVED", tier=None, unresolved="proxy or quantity?"))
    assert reason is None and validated == {"state": rl.STATE_UNRESOLVED, "tier": None, "anchor_element_ids": [], "basis": "scripted basis",
                                            "unresolved_reason": "proxy or quantity?", "anchor_evidence": []}
    assert rl.validate_response_item(item, answer(item.claim_id, "A301", outcome="UNRESOLVED", tier=None, unresolved=None))[1] == rl.FAILURE_MALFORMED_RESPONSE
    assert rl.validate_response_item(item, answer(item.claim_id, "A301", outcome="UNRESOLVED", tier="weak", unresolved="x"))[1] == rl.FAILURE_INVALID_LABEL


def test_q1_first_core_wins_when_core_and_strong_elements_are_both_engaged():
    item = item_for()
    validated, reason = rl.validate_response_item(item, answer(item.claim_id, "A301", tier="core", anchors=[core_of("A301")[0], strong_of("A301")[0]],
                                                               quote=item.claim_text))
    assert reason is None and validated["tier"] == "core"
    # the same anchors under "strong" contradict Q1 and are refused, never re-labelled
    assert rl.validate_response_item(item, answer(item.claim_id, "A301", tier="strong", anchors=[core_of("A301")[0], strong_of("A301")[0]],
                                                  quote=item.claim_text))[1] == rl.FAILURE_TIER_ANCHOR_INCONSISTENT


@pytest.mark.parametrize("tier", ["moderate", "CORE", "Core", "", "medium", 1])
def test_an_illegal_tier_label_is_refused(tier):
    item = item_for()
    assert rl.validate_response_item(item, answer(item.claim_id, "A301", tier=tier))[1] == rl.FAILURE_INVALID_LABEL


@pytest.mark.parametrize("outcome", ["determined", "UNSURE", "", None])
def test_an_illegal_outcome_is_refused(outcome):
    item = item_for()
    assert rl.validate_response_item(item, answer(item.claim_id, "A301", outcome=outcome))[1] == rl.FAILURE_INVALID_LABEL


@pytest.mark.parametrize("missing", rl.RESPONSE_FIELDS_V2)
def test_every_field_is_required(missing):
    item = item_for()
    returned = answer(item.claim_id, "A301")
    del returned[missing]
    assert rl.validate_response_item(item, returned)[1] == rl.FAILURE_MALFORMED_RESPONSE


@pytest.mark.parametrize(("field", "value"), [("anchor_element_ids", "A301.demand"), ("anchor_element_ids", [1]), ("basis", ""), ("basis", None),
                                              ("basis", "x" * (rl.MAX_BASIS_CHARS + 1)), ("unresolved_reason", "not allowed when determined")])
def test_wrong_field_shapes_are_malformed(field, value):
    item = item_for()
    returned = answer(item.claim_id, "A301")
    returned[field] = value
    assert rl.validate_response_item(item, returned)[1] == rl.FAILURE_MALFORMED_RESPONSE


def test_anchors_must_be_elements_of_the_matched_alpha_and_fit_the_tier():
    item = item_for()
    assert rl.validate_response_item(item, answer(item.claim_id, "A301", tier="core", anchors=["A301.not_an_element"]))[1] == rl.FAILURE_ANCHOR_INVALID
    assert rl.validate_response_item(item, answer(item.claim_id, "A301", tier="core", anchors=core_of("A501")[:1]))[1] == rl.FAILURE_ANCHOR_INVALID
    for tier, anchors in (("core", []), ("core", strong_of("A301")[:1]), ("strong", []), ("weak", core_of("A301")[:1]), ("none", strong_of("A301")[:1])):
        assert rl.validate_response_item(item, answer(item.claim_id, "A301", tier=tier, anchors=anchors))[1] == rl.FAILURE_TIER_ANCHOR_INCONSISTENT, (tier, anchors)


def test_duplicate_missing_and_borrowed_answers():
    a, b = item_for(claim_id="c1"), item_for(claim_id="c2")
    out = rl.judge_returned_items([a, b], [
        answer("c1", "A301"), answer("c1", "A301", tier="none"),  # duplicate for c1
        answer("c3", "A301", tier="none"),  # an unrequested claim cannot lend its answer
        answer("c2", "A501", tier="none"),  # the same claim under another Alpha is not this pair
    ])
    assert out[a.key]["state"] == rl.STATE_FAILED and out[a.key]["failure_reason"] == rl.FAILURE_DUPLICATE_RESULT
    assert out[b.key]["state"] == rl.STATE_FAILED and out[b.key]["failure_reason"] == rl.FAILURE_MISSING_RESULT
    assert all(r["tier"] is None for r in out.values())


# ----------------------------------------------------------------------------------------------------------- the gateway chain
def test_a_mixed_batch_keeps_every_outcome_distinct_and_is_recorded_in_the_relevance_ledger(tmp_path):
    run_id = "run-a"
    make_run(tmp_path, run_id, pairs=[("c-1 text", "A301"), ("c-2 text", "A301"), ("c-3 text", "A301"), ("c-4 text", "A301")])
    result = judge(tmp_path, run_id, by_pair({
        (claim(run_id, 1), "A301"): answer(claim(run_id, 1), "A301", tier="none"),  # an explicit "none"
        (claim(run_id, 2), "A301"): answer(claim(run_id, 2), "A301", outcome="UNRESOLVED", tier=None, unresolved="unspecified quantity"),
        (claim(run_id, 3), "A301"): answer(claim(run_id, 3), "A301", tier="moderate"),  # failed: illegal label
        # claim 4: no answer -> failed: missing_result
    }))
    assert result["status"] == "ok" and result["provider_calls"] == 1
    states = {k[0]: v for k, v in verify(tmp_path, run_id).pairs.items()}
    assert (states[claim(run_id, 1)]["state"], states[claim(run_id, 1)]["tier"]) == (rl.STATE_JUDGED, "none")
    assert (states[claim(run_id, 2)]["state"], states[claim(run_id, 2)]["tier"]) == (rl.STATE_UNRESOLVED, None)
    assert (states[claim(run_id, 3)]["state"], states[claim(run_id, 3)]["reason"]) == (rl.STATE_FAILED, rl.FAILURE_INVALID_LABEL)
    assert (states[claim(run_id, 4)]["state"], states[claim(run_id, 4)]["reason"]) == (rl.STATE_FAILED, rl.FAILURE_MISSING_RESULT)
    assert states[claim(run_id, 3)]["tier"] is None and states[claim(run_id, 4)]["tier"] is None
    records = [json.loads(line) for line in (tmp_path / run_id / LEDGER_DIRNAME / "llm_semantic_calls.jsonl").read_text().splitlines()]
    assert [r["task"] for r in records] == [rl.LLM_TASK_NAME] and records[0]["validation_status"] == "accepted"
    assert not (tmp_path / run_id / "llm_semantic_calls.jsonl").exists(), "the run's main ledger is never written by the relevance task"


@pytest.mark.parametrize(("response", "reason"), [
    (RuntimeError("provider down"), rl.FAILURE_PROVIDER_ERROR),
    ("this is not json", rl.FAILURE_MALFORMED_RESPONSE),
    ({"no_items": []}, rl.FAILURE_MALFORMED_RESPONSE),
])
def test_a_failed_call_fails_every_pair_of_its_batch_with_the_reason(tmp_path, response, reason):
    make_run(tmp_path)
    judge(tmp_path, "run-a", lambda payload: response)
    views = verify(tmp_path, "run-a").pairs.values()
    assert {(v["state"], v["reason"], v["tier"]) for v in views} == {(rl.STATE_FAILED, reason, None)}


def test_a_timeout_is_disclosed_as_timeout(tmp_path):
    make_run(tmp_path)

    def slow(payload):
        time.sleep(0.3)
        return {"items": []}

    judge(tmp_path, "run-a", slow, timeout_seconds=0.05)
    assert {v["reason"] for v in verify(tmp_path, "run-a").pairs.values()} == {rl.FAILURE_TIMEOUT}


# ----------------------------------------------------------------------------------------------------------- binding and source verification
@pytest.fixture
def judged(tmp_path):
    run_id = "run-a"
    make_run(tmp_path, run_id)
    answers = {
        (claim(run_id, 1), "A301"): answer(claim(run_id, 1), "A301", tier="core", anchors=["A301.demand"], basis="demand beat is the core variable"),
        (claim(run_id, 2), "A301"): answer(claim(run_id, 2), "A301", tier="strong", anchors=["A301.margins"], basis="margins: confirmation only"),
        (claim(run_id, 3), "A601"): answer(claim(run_id, 3), "A601", tier="strong", anchors=strong_of("A601")[:1], basis="sentiment"),
    }
    assert judge(tmp_path, run_id, by_pair(answers))["status"] == "ok"
    return tmp_path, run_id


def test_saved_results_read_back_identically(judged):
    root, run_id = judged
    pairs = verify(root, run_id).pairs
    assert {k[0][-1]: (v["state"], v["tier"], v["anchor_element_ids"]) for k, v in pairs.items()} == {
        "1": (rl.STATE_JUDGED, "core", ["A301.demand"]), "2": (rl.STATE_JUDGED, "strong", ["A301.margins"]),
        "3": (rl.STATE_JUDGED, "strong", strong_of("A601")[:1])}
    assert len(pairs) == 3, "the unmatched claim is never given an Alpha"


def _edit_results(root: Path, run_id: str, edit: Callable[[dict[str, Any]], None]) -> None:
    path = root / run_id / RESULTS_FILENAME
    payload = json.loads(path.read_text(encoding="utf-8"))
    edit(payload)
    path.write_text(json.dumps(payload), encoding="utf-8")


def _edit_matches(root: Path, run_id: str, edit: Callable[[list[dict[str, Any]]], None]) -> None:
    path = root / run_id / "alpha_matches.json"
    payload = json.loads(path.read_text(encoding="utf-8"))
    edit(payload["matches"])
    path.write_text(json.dumps(payload), encoding="utf-8")


def test_another_claim_cannot_read_a_result(judged):
    root, run_id = judged
    _edit_results(root, run_id, lambda p: p["records"][0].update(claim_id=claim(run_id, 2)))  # claim 1's record re-labelled as claim 2's
    pairs = verify(root, run_id).pairs
    assert pairs[(claim(run_id, 1), "A301")]["state"] == rl.STATE_UNJUDGED
    assert pairs[(claim(run_id, 2), "A301")]["state"] == rl.STATE_FAILED  # two records now claim this pair
    assert all(v["tier"] is None for k, v in pairs.items() if k[0] != claim(run_id, 3))


def test_another_alpha_cannot_read_a_result(judged):
    root, run_id = judged
    _edit_matches(root, run_id, lambda matches: matches[0].update(matched_alpha="A501"))  # claim 1 is now matched to another Alpha
    verification = verify(root, run_id)
    assert verification.pairs[(claim(run_id, 1), "A501")]["state"] == rl.STATE_UNJUDGED
    assert (claim(run_id, 1), "A301") in verification.orphan_records


def test_a_changed_claim_text_makes_the_old_judgment_stale(judged):
    root, run_id = judged
    _edit_matches(root, run_id, lambda matches: matches[0].update(claim="A different statement entirely.", evidence="A different statement entirely."))
    view = verify(root, run_id).pairs[(claim(run_id, 1), "A301")]
    assert (view["state"], view["reason"], view["tier"]) == (rl.STATE_FAILED, "binding_stale", None) and "claim_text_sha256" in view["reason_detail"]


def test_a_changed_alpha_definition_makes_the_old_judgment_stale(judged, tmp_path_factory):
    root, run_id = judged
    taxonomy = yaml.safe_load(TAXONOMY_PATH.read_text(encoding="utf-8"))
    next(a for a in taxonomy["alphas"] if a["alpha_id"] == "A301")["keywords"].append("an extra topic term")
    edited = tmp_path_factory.mktemp("taxonomy") / "taxonomy.yaml"
    edited.write_text(yaml.safe_dump(taxonomy, sort_keys=False, allow_unicode=True), encoding="utf-8")
    pairs = verify(root, run_id, definitions=load_relevance_definitions(taxonomy_path=edited)).pairs
    assert pairs[(claim(run_id, 1), "A301")]["reason"] == "binding_stale" and "alpha_definition_sha256" in pairs[(claim(run_id, 1), "A301")]["reason_detail"]
    assert pairs[(claim(run_id, 3), "A601")]["state"] == rl.STATE_JUDGED  # another Alpha's definition did not change


@pytest.mark.parametrize("constant", ["PROMPT_VERSION", "OUTPUT_SCHEMA_VERSION", "CRITERION_VERSION"])
def test_a_version_change_makes_the_old_judgment_stale(judged, monkeypatch, constant):
    root, run_id = judged
    monkeypatch.setattr(rl, constant, getattr(rl, constant) + ".next")
    views = verify(root, run_id).pairs.values()
    assert {(v["state"], v["reason"]) for v in views} == {(rl.STATE_FAILED, "binding_stale")}


def test_results_copied_into_another_run_belong_to_their_owner(judged):
    root, run_id = judged
    other = root / "run-b"
    other.mkdir()
    for name in ("alpha_matches.json", "metadata.json", RESULTS_FILENAME):
        (other / name).write_bytes((root / run_id / name).read_bytes())
    matches = json.loads((other / "alpha_matches.json").read_text())["matches"]
    views = verify_relevance_judgments(other, run_id="run-b", ticker=TICKER, matches=matches).pairs.values()
    assert {(v["state"], v["reason"]) for v in views} == {(rl.STATE_FAILED, "owner_mismatch")}


def test_a_missing_or_damaged_ledger_is_disclosed_never_judged(judged):
    root, run_id = judged
    calls = root / run_id / LEDGER_DIRNAME / "llm_semantic_calls.jsonl"
    calls.write_text(calls.read_text() + "\n", encoding="utf-8")  # one byte more: the manifest no longer matches
    assert {(v["state"], v["reason"]) for v in verify(root, run_id).pairs.values()} == {(rl.STATE_FAILED, "ledger_integrity_failed")}
    (root / run_id / LEDGER_DIRNAME).rename(root / run_id / "moved_aside")
    assert {(v["state"], v["reason"]) for v in verify(root, run_id).pairs.values()} == {(rl.STATE_FAILED, "ledger_unavailable")}


def test_a_saved_result_the_ledger_does_not_reproduce_is_refused(judged):
    root, run_id = judged
    _edit_results(root, run_id, lambda p: p["records"][1].update(tier="core", anchor_element_ids=["A301.demand"]))
    assert verify(root, run_id).pairs[(claim(run_id, 2), "A301")]["reason"] == "ledger_label_mismatch"
    _edit_results(root, run_id, lambda p: p["records"][2].update(basis="an edited basis"))
    assert verify(root, run_id).pairs[(claim(run_id, 3), "A601")]["reason"] == "ledger_label_mismatch"


def _rewrite_ledger(root: Path, run_id: str, edit: Callable[[dict[str, Any]], None]) -> None:
    """Edit every relevance record and re-seal the manifest, so only the edited CONTENT (not the integrity check) can fail."""
    import hashlib  # noqa: PLC0415

    ledger_dir = root / run_id / LEDGER_DIRNAME
    calls = ledger_dir / "llm_semantic_calls.jsonl"
    records = [json.loads(line) for line in calls.read_text().splitlines()]
    for record in records:
        edit(record)
    calls.write_text("".join(json.dumps(r) + "\n" for r in records), encoding="utf-8")
    manifest = ledger_dir / "llm_semantic_manifest.json"
    payload = json.loads(manifest.read_text())
    payload["calls_file_sha256"] = hashlib.sha256(calls.read_bytes()).hexdigest()
    manifest.write_text(json.dumps(payload), encoding="utf-8")


def test_a_ledger_call_made_for_different_inputs_does_not_corroborate(judged):
    root, run_id = judged

    def other_inputs(record: dict[str, Any]) -> None:
        for item in record["input_payload"]["items"]:
            item["claim_text_sha256"] = "0" * 64

    _rewrite_ledger(root, run_id, other_inputs)
    assert {(v["state"], v["reason"]) for v in verify(root, run_id).pairs.values()} == {(rl.STATE_FAILED, "ledger_label_mismatch")}


def test_stance_records_never_corroborate_a_relevance_judgment(judged):
    root, run_id = judged
    ledger_dir = root / run_id / LEDGER_DIRNAME
    calls = ledger_dir / "llm_semantic_calls.jsonl"
    stance_lines = []
    for line in calls.read_text().splitlines():
        record = json.loads(line)
        record["task"] = "evidence_stance_classifier"  # the same recorded output, but under the stance task's identity
        stance_lines.append(json.dumps(record))
    calls.write_text("\n".join(stance_lines) + "\n", encoding="utf-8")
    manifest = ledger_dir / "llm_semantic_manifest.json"
    payload = json.loads(manifest.read_text())
    import hashlib  # noqa: PLC0415

    payload["calls_file_sha256"] = hashlib.sha256(calls.read_bytes()).hexdigest()  # an intact ledger -- of the wrong task
    manifest.write_text(json.dumps(payload), encoding="utf-8")
    verification = verify(root, run_id)
    assert {(v["state"], v["reason"]) for v in verification.pairs.values()} == {(rl.STATE_FAILED, "pair_not_in_ledger")}
    assert verification.ledger.other_task_records == len(stance_lines) and not verification.ledger.records


def test_the_main_ledger_is_never_read_as_relevance_evidence(tmp_path):
    run_dir = make_run(tmp_path)
    (run_dir / "llm_semantic_calls.jsonl").write_text(json.dumps({"task": rl.LLM_TASK_NAME, "call_id": "x", "validation_status": "accepted"}) + "\n")
    assert {v["state"] for v in verify(tmp_path, "run-a").pairs.values()} == {rl.STATE_UNJUDGED}


def test_missing_failed_unresolved_and_explicit_none_stay_distinguishable(tmp_path):
    run_id = "run-a"
    make_run(tmp_path, run_id, pairs=[("t1", "A301"), ("t2", "A301"), ("t3", "A301"), ("t4", "A301")])
    judge(tmp_path, run_id, by_pair({
        (claim(run_id, 1), "A301"): answer(claim(run_id, 1), "A301", tier="none"),
        (claim(run_id, 2), "A301"): answer(claim(run_id, 2), "A301", outcome="UNRESOLVED", tier=None, unresolved="cannot tell"),
        (claim(run_id, 3), "A301"): answer(claim(run_id, 3), "A301", tier="none", anchors=["A301.demand"]),  # failed: inconsistent
    }), batch_size=8)
    _edit_results(tmp_path, run_id, lambda p: p.update(records=[r for r in p["records"] if r["claim_id"] != claim(run_id, 4)]))
    seen = {k[0][-1]: (v["state"], v["tier"], v["reason"]) for k, v in verify(tmp_path, run_id).pairs.items()}
    assert seen == {"1": (rl.STATE_JUDGED, "none", None), "2": (rl.STATE_UNRESOLVED, None, None),
                    "3": (rl.STATE_FAILED, None, rl.FAILURE_TIER_ANCHOR_INCONSISTENT), "4": (rl.STATE_UNJUDGED, None, "pair_not_in_results")}


# ----------------------------------------------------------------------------------------------------------- default off
def test_the_default_configuration_sends_nothing_and_writes_nothing(tmp_path):
    run_dir = make_run(tmp_path)
    before = sorted(p.name for p in run_dir.iterdir())
    provider = ExplodingProvider()
    result = ex.judge_run_relevance("run-a", output_root=tmp_path, provider=provider)
    assert result == {"status": "disabled", "config": "default_off", "provider_calls": 0, "writes": []}
    assert ExplodingProvider.calls == 0 and sorted(p.name for p in run_dir.iterdir()) == before


def test_only_the_simulated_gateway_exists_in_this_phase_and_real_outputs_are_refused(tmp_path):
    make_run(tmp_path)
    real = ex.RelevanceExperimentConfig(**{**ex.P4_RELEVANCE_SIMULATED_20261012.__dict__, "name": "x", "gateway_mode": "LIVE"})
    assert ex.judge_run_relevance("run-a", output_root=tmp_path, config=real, provider=ExplodingProvider())["error_code"] == "REAL_GATEWAY_NOT_AUTHORIZED_IN_PHASE_1"
    assert not (tmp_path / "run-a" / LEDGER_DIRNAME).exists() and ExplodingProvider.calls == 0
    with pytest.raises(ValueError, match="REFUSED_REAL_OUTPUTS"):
        ex.judge_run_relevance("x", output_root=REPO_ROOT / "outputs" / "runs", config=ex.P4_RELEVANCE_SIMULATED_20261012)


def test_a_run_is_judged_once(judged):
    root, run_id = judged
    assert judge(root, run_id, lambda payload: {"items": []})["error_code"] == "RELEVANCE_ALREADY_JUDGED"


def test_the_task_is_registered_for_the_recorder_but_wired_into_no_pipeline():
    from comqutor_alpha.structure_engine import week2_llm

    assert rl.LLM_TASK_NAME in SEMANTIC_TASKS
    assert rl.LLM_TASK_NAME not in week2_llm._TASK_INSTRUCTIONS and rl.LLM_TASK_NAME not in week2_llm._TASK_RUNTIME_METADATA  # noqa: SLF001
    import ast  # noqa: PLC0415

    allowed = {"comqutor_alpha/alpha_relevance_experiment.py", "scripts/alpha_relevance_judgment.py", "comqutor_alpha/structure_engine/alpha_relevance_llm.py"}
    runners = {"judge_relevance", "judge_run_relevance"}
    offenders = []
    for path in [*(REPO_ROOT / "comqutor_alpha").rglob("*.py"), *(REPO_ROOT / "scripts").rglob("*.py")]:
        relative = str(path.relative_to(REPO_ROOT))
        if "__pycache__" in path.parts or relative in allowed:
            continue
        for node in ast.walk(ast.parse(path.read_text(encoding="utf-8", errors="ignore"))):
            imported = (node.module or "") if isinstance(node, ast.ImportFrom) else ""
            names = {alias.name for alias in node.names} if isinstance(node, (ast.Import, ast.ImportFrom)) else set()
            called = node.func.attr if isinstance(node, ast.Call) and isinstance(node.func, ast.Attribute) else (
                node.func.id if isinstance(node, ast.Call) and isinstance(node.func, ast.Name) else None)
            if "alpha_relevance_experiment" in imported or any("alpha_relevance_experiment" in n for n in names) or names & runners or called in runners:
                offenders.append(relative)
    assert offenders == [], "only the explicit experiment entry may run the relevance task"
    from comqutor_alpha.structure_engine.week2_execution_profile import T3_VERIFIED_20261008

    assert rl.LLM_TASK_NAME not in T3_VERIFIED_20261008.task_timeout_seconds  # the verified profile is untouched
