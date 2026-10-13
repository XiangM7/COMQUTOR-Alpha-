"""P4 phase 2, session 4 (2026-10-12): criterion exp2 + prompt v2 + output contract v2, their version binding, and the development retest.

What these tests prove: the task identity and its registered versions, the exact request the task assembles, the v2 evidence check,
that a judgment is re-validated and shown under the version it was RECORDED with (an older record is never relabelled), that the first
real run (prompt v1) still re-evaluates to identical results, and that a retest sample / plan is an exact, bound subset. Answers here are
scripted or simulated TEST DATA. A passing test says nothing about how well a real model applies the criterion.
"""

from __future__ import annotations

import csv
import io
import json
import re
from collections.abc import Callable
from datetime import datetime, timedelta, timezone
from pathlib import Path
from types import SimpleNamespace
from typing import Any

import pytest

from comqutor_alpha import (
    alpha_relevance_eval_prep as ep,
    alpha_relevance_evaluation as ev,
    alpha_relevance_experiment as ex,
)
from comqutor_alpha.alpha_library.alpha_relevance_elements import (
    canonical_json_text,
    load_relevance_definitions,
)
from comqutor_alpha.graph_engine.alpha_relevance_judgment import (
    LEDGER_DIRNAME,
    RESULTS_FILENAME,
    verify_relevance_judgments,
    verify_relevance_records,
)
from comqutor_alpha.structure_engine import alpha_relevance_llm as rl

REPO_ROOT = Path(__file__).resolve().parents[1]
DEFS = load_relevance_definitions()
TICKER = "NVDA"
NOW = datetime(2026, 10, 12, 12, 0, tzinfo=timezone.utc)
PHASE2 = REPO_ROOT / "docs/audit_artifacts/round_source_linking_t0_t2/round36_t1_migration_20261010/p4_phase2_eval_prep_20261012"
LIVE_V1 = PHASE2 / "live/relevance-eval-20261012T201725Z-0732ac3c"
RECORDED_V1_PROMPT_SHA256 = "e173b92d842b6ac2b167671a8d5ef941c58eadbd5cdf91681e0c8add7f0128c4"  # what the 30 real calls recorded
needs_phase2 = pytest.mark.skipif(not (PHASE2 / "sample/sample_manifest.json").is_file(), reason="the phase-2 evidence folder is local only")
needs_live_v1 = pytest.mark.skipif(not (LIVE_V1 / "execution_record.json").is_file(), reason="the first real run is local only")


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
    def __init__(self, responder: Callable[[dict[str, Any]], Any]) -> None:
        self.responder = responder
        self.calls = 0

    def invoke(self, prompt: str) -> _Message:
        self.calls += 1
        return _Message(json.dumps(self.responder(json.loads(prompt.split(rl.PROMPT_IDENTITY_SEPARATOR, 1)[1]))))


def core_of(alpha_id: str) -> str:
    return next(e for e, o in DEFS[alpha_id].ownership.items() if o == "core")


def strong_of(alpha_id: str) -> str:
    return next(e for e, o in DEFS[alpha_id].ownership.items() if o == "strong")


def item_for(text: str = "Demand for AI accelerators rose sharply this quarter.", alpha_id: str = "A301", claim_id: str = "c1") -> rl.RelevanceRequestItem:
    items, _missing = rl.build_request_items([{"claim_id": claim_id, "claim": text, "match_status": "matched", "matched_alpha": alpha_id}],
                                             ticker=TICKER, definitions=DEFS)
    return items[0]


def v2(item: rl.RelevanceRequestItem, tier: str = "core", anchors: list[str] | None = None, evidence: list[dict[str, Any]] | None = None,
       outcome: str = "DETERMINED", unresolved: str | None = None) -> dict[str, Any]:
    anchors = [core_of(item.alpha_id)] if anchors is None else anchors
    return {"claim_id": item.claim_id, "alpha_id": item.alpha_id, "outcome": outcome, "tier": tier, "anchor_element_ids": anchors,
            "anchor_evidence": evidence if evidence is not None else [{"element_id": a, "quote": "Demand for AI accelerators rose"} for a in anchors],
            "basis": "scripted basis", "unresolved_reason": unresolved}


def make_run(root: Path, run_id: str = "run-a") -> Path:
    run_dir = root / run_id
    run_dir.mkdir(parents=True)
    pairs = [("Demand for data-center GPUs beat expectations again.", "A301"), ("Retail sentiment on social media turned euphoric.", "A601")]
    matches = [{"claim_id": f"{run_id}:agent:report:claim:{i}", "claim": text, "evidence": text, "match_status": "matched",
                "matched_alpha": alpha, "ticker": TICKER} for i, (text, alpha) in enumerate(pairs, start=1)]
    (run_dir / "alpha_matches.json").write_text(json.dumps({"run_id": run_id, "ticker": TICKER, "matches": matches}), encoding="utf-8")
    (run_dir / "metadata.json").write_text(json.dumps({"run_id": run_id, "ticker": TICKER}), encoding="utf-8")
    return run_dir


def claim(run_id: str, i: int) -> str:
    return f"{run_id}:agent:report:claim:{i}"


def scripted_answers(with_evidence: bool) -> Callable[[dict[str, Any]], dict[str, Any]]:
    """TEST DATA: claim 1 core on A301's demand element, claim 2 strong on A601's first confirmation element."""
    def responder(payload: dict[str, Any]) -> dict[str, Any]:
        out = []
        for request in payload["items"]:
            alpha = request["alpha_id"]
            anchor = core_of(alpha) if alpha == "A301" else strong_of(alpha)
            entry = {"claim_id": request["claim_id"], "alpha_id": alpha, "outcome": "DETERMINED", "tier": "core" if alpha == "A301" else "strong",
                     "anchor_element_ids": [anchor], "basis": "TEST DATA", "unresolved_reason": None}
            if with_evidence:
                entry["anchor_evidence"] = [{"element_id": anchor, "quote": request["claim_text"][:40]}]
            out.append(entry)
        return {"items": out}
    return responder


def judge(root: Path, run_id: str, responder: Callable[[dict[str, Any]], Any]) -> dict[str, Any]:
    return ex.judge_run_relevance(run_id, output_root=root, config=ex.P4_RELEVANCE_SIMULATED_20261012, provider=ScriptedProvider(responder))


def verify(root: Path, run_id: str):
    matches = json.loads((root / run_id / "alpha_matches.json").read_text(encoding="utf-8"))["matches"]
    return verify_relevance_judgments(root / run_id, run_id=run_id, ticker=TICKER, matches=matches)


def as_v1(monkeypatch: pytest.MonkeyPatch) -> None:
    """Make prompt v1 the module's current version, the way the task stood when the first real run was made."""
    monkeypatch.setattr(rl, "PROMPT_VERSION", rl.PROMPT_VERSION_V1)
    monkeypatch.setattr(rl, "PROMPT_TEXT", rl.PROMPT_TEXT_V1)
    monkeypatch.setattr(rl, "OUTPUT_SCHEMA_VERSION", rl.OUTPUT_SCHEMA_V1)
    monkeypatch.setattr(rl, "CRITERION_VERSION", rl.CRITERION_EXP1)


# ----------------------------------------------------------------------------------------------------------- identity and registry
def test_the_retired_v1_identity_reproduces_what_the_real_calls_recorded():
    v1 = rl.task_identity(rl.PROMPT_VERSION_V1)
    assert v1["prompt_sha256"] == RECORDED_V1_PROMPT_SHA256
    assert (v1["criterion_version"], v1["output_schema_version"], v1["input_schema_version"]) == (
        rl.CRITERION_EXP1, rl.OUTPUT_SCHEMA_V1, "alpha_relevance.judge.input.v1")


def test_the_current_identity_is_v2_and_differs_from_v1_in_every_changed_version():
    current, v1 = rl.task_identity(), rl.task_identity(rl.PROMPT_VERSION_V1)
    assert current == rl.task_identity(rl.PROMPT_VERSION_V2)
    assert (current["prompt_version"], current["criterion_version"], current["output_schema_version"]) == (
        rl.PROMPT_VERSION_V2, rl.CRITERION_EXP2, rl.OUTPUT_SCHEMA_V2)
    assert current["input_schema_version"] == v1["input_schema_version"] and current["elements_version"] == v1["elements_version"]
    assert {k for k in current if current[k] != v1[k]} == {"prompt_version", "prompt_sha256", "criterion_version", "output_schema_version"}
    assert rl.PROMPT_VERSIONS[rl.PROMPT_VERSION]["text"] == rl.PROMPT_TEXT  # the registry's current entry is what is sent


def test_the_current_identity_is_read_when_called_not_frozen_at_import(monkeypatch):
    """The current identity follows the module's versions at call time (how the task stood for the first run is reproducible by setting
    them), while a registered version always gives its own fixed identity."""
    as_v1(monkeypatch)
    assert rl.task_identity() == rl.task_identity(rl.PROMPT_VERSION_V1)
    assert rl.task_identity(rl.PROMPT_VERSION_V2)["prompt_version"] == rl.PROMPT_VERSION_V2


def test_only_registered_identities_are_known():
    assert rl.is_known_task_identity(rl.task_identity()) and rl.is_known_task_identity(rl.task_identity(rl.PROMPT_VERSION_V1))
    for edit in ({"criterion_version": rl.CRITERION_EXP2}, {"prompt_sha256": "0" * 64}, {"output_schema_version": rl.OUTPUT_SCHEMA_V2}):
        assert not rl.is_known_task_identity({**rl.task_identity(rl.PROMPT_VERSION_V1), **edit})  # a v1/v2 hybrid is no identity


# ----------------------------------------------------------------------------------------------------------- prompt v2 text
@pytest.mark.parametrize("rule", [
    "explicitly named subcategory of the element's object whose SAME property is stated",  # A: subcategory
    "Stating one element never implies another",  # A: demand is not inventory / prices / orders
    "is not\n     automatically the quantity it relates to",  # A: backlog / share / probability
    "A forecast or a probability is not the event having\n     happened",  # A: a forecast is not the event
    "judge that\n     statement on its own",  # A: an explicit statement next to an indicator
    "Never\nanchor an element by inference from general knowledge",  # B: no supplied facts
    "A clearly stated\n    strong-eligible element with no core evidence is \"strong\", not UNRESOLVED",  # B
    "Lacking core evidence is not, by itself, an ambiguity",  # B: UNRESOLVED is narrow
    "Background and contrast still count when they actually state",  # C
    "A name used only as a label, a modifier, a setting or a scene does not",  # C
    "Belonging to the same industry, sector or asset class is not enough by itself",  # D
    "Never answer \"none\" merely because a keyword is absent",  # D
])
def test_prompt_v2_states_each_exp2_rule(rule):
    assert rule in rl.PROMPT_TEXT_V2


def test_prompt_v1_text_is_kept_unchanged_and_never_sent():
    assert rl.prompt_identity_sha256(rl.PROMPT_VERSION_V1) == RECORDED_V1_PROMPT_SHA256
    assert rl.PROMPT_VERSIONS[rl.PROMPT_VERSION_V1]["status"].startswith("retired")
    assert rl.PROMPT_TEXT != rl.PROMPT_TEXT_V1


@needs_phase2
def test_prompt_v2_quotes_no_development_sample():
    """The examples in prompt v2 are the owner's rule examples or constructed ones: no 4-word run of any of the 60 sample claims."""
    words = lambda s: re.findall(r"[a-z0-9']+", s.casefold())  # noqa: E731
    prompt = f" {' '.join(words(rl.PROMPT_TEXT_V2))} "
    manifest = json.loads((PHASE2 / "sample/sample_manifest.json").read_text(encoding="utf-8"))
    for sample in manifest["samples"]:
        w = words(sample["claim_text"])
        assert not [i for i in range(len(w) - 3) if f" {' '.join(w[i:i + 4])} " in prompt], sample["sample_id"]


# ----------------------------------------------------------------------------------------------------------- request assembly
class RecordingGateway:
    """Captures what the task hands to the shared gateway; answers with ``answers(payload)`` as an accepted call."""

    def __init__(self, answers: Callable[[dict[str, Any]], list[dict[str, Any]]]) -> None:
        self.answers = answers
        self.sent: list[dict[str, Any]] = []
        self.finalized: list[dict[str, Any]] = []

    def invoke_prebuilt_json_prompt(self, **kwargs: Any) -> Any:
        self.sent.append(kwargs)
        return SimpleNamespace(validation_accepted=True, validated_output=self.answers(kwargs["payload_for_identity"]), provider_attempt_count=1,
                               trace_handle=SimpleNamespace(call_id=f"call-{len(self.sent)}"))

    def finalize_semantic_invocation(self, invocation: Any, **kwargs: Any) -> None:
        self.finalized.append(kwargs)


def test_the_task_sends_prompt_v2_with_its_identity_and_the_exp2_criterion():
    item = item_for()
    gateway = RecordingGateway(lambda payload: [v2(item)])
    results, stats = rl.judge_relevance([item], gateway)
    sent = gateway.sent[0]
    identity = rl.task_identity()
    assert (sent["prompt_version"], sent["prompt_sha256"], sent["input_schema_version"], sent["output_schema_version"]) == (
        rl.PROMPT_VERSION_V2, identity["prompt_sha256"], identity["input_schema_version"], rl.OUTPUT_SCHEMA_V2)
    assert sent["payload_for_identity"]["criterion_version"] == rl.CRITERION_EXP2
    assert sent["prompt"] == rl.PROMPT_TEXT_V2 + rl.PROMPT_IDENTITY_SEPARATOR + canonical_json_text(sent["payload_for_identity"])
    assert results[item.key]["state"] == rl.STATE_JUDGED and results[item.key]["anchor_evidence"] == [
        {"element_id": core_of("A301"), "quote": "Demand for AI accelerators rose"}]
    assert gateway.finalized == [{"accepted": True}] and stats.batches == 1


def test_a_recorded_request_of_another_version_is_rebuilt_with_its_own_text_and_criterion():
    item = item_for()
    payload = rl.batch_payload([item], criterion_version=rl.CRITERION_EXP1)
    assert payload["criterion_version"] == rl.CRITERION_EXP1 and rl.batch_payload([item])["criterion_version"] == rl.CRITERION_EXP2
    assert rl.build_prompt(payload, rl.PROMPT_VERSION_V1).startswith(rl.PROMPT_TEXT_V1 + rl.PROMPT_IDENTITY_SEPARATOR)


# ----------------------------------------------------------------------------------------------------------- output v2: locatable evidence
def test_a_core_answer_with_a_quote_of_the_claim_is_accepted_and_keeps_the_quote():
    item = item_for()
    validated, reason = rl.validate_response_item(item, v2(item))
    assert reason is None and validated["tier"] == "core" and validated["anchor_evidence"] == [
        {"element_id": core_of("A301"), "quote": "Demand for AI accelerators rose"}]


@pytest.mark.parametrize("quote", [
    "demand for ai accelerators ROSE",  # case
    "Demand  for AI\naccelerators rose",  # whitespace
    "“Demand for AI accelerators rose sharply”",  # the quote's own curly quotes
    "rose sharply this quarter.",  # its own trailing punctuation
])
def test_a_quote_is_found_after_folding_case_whitespace_and_its_own_punctuation(quote):
    item = item_for()
    assert rl.validate_response_item(item, v2(item, evidence=[{"element_id": core_of("A301"), "quote": quote}]))[1] is None


def test_curly_quotes_and_dashes_in_the_claim_fold_too():
    item = item_for(text="The CEO said “demand is lean” — inventories, too.")
    anchor = core_of("A301")
    assert rl.validate_response_item(item, v2(item, evidence=[{"element_id": anchor, "quote": '"demand is lean" - inventories'}]))[1] is None


@pytest.mark.parametrize(("evidence", "reason"), [
    ([{"element_id": "A301.demand", "quote": "demand for accelerators increased"}], rl.FAILURE_EVIDENCE_INVALID),  # a paraphrase
    ([{"element_id": "A301.demand", "quote": "AI"}], rl.FAILURE_EVIDENCE_INVALID),  # too short to locate anything
    ([], rl.FAILURE_EVIDENCE_INVALID),  # an anchor without a quote
    ([{"element_id": "A301.demand", "quote": "Demand for AI"}, {"element_id": "A301.margins", "quote": "this quarter"}], rl.FAILURE_EVIDENCE_INVALID),
    ([{"element_id": "A301.demand", "quote": "x" * (rl.MAX_QUOTE_CHARS + 1)}], rl.FAILURE_MALFORMED_RESPONSE),
    ([{"element_id": "A301.demand"}], rl.FAILURE_MALFORMED_RESPONSE),
    ([{"quote": "Demand for AI"}], rl.FAILURE_MALFORMED_RESPONSE),
    (["Demand for AI"], rl.FAILURE_MALFORMED_RESPONSE),
    ("Demand for AI", rl.FAILURE_MALFORMED_RESPONSE),
])
def test_unlocatable_or_misshaped_evidence_is_refused_never_repaired(evidence, reason):
    item = item_for()
    assert core_of("A301") == "A301.demand"
    assert rl.validate_response_item(item, v2(item, anchors=["A301.demand"], evidence=evidence))[1] == reason


def test_weak_and_none_carry_no_evidence_and_unresolved_needs_none():
    item = item_for()
    assert rl.validate_response_item(item, v2(item, tier="weak", anchors=[]))[1] is None
    assert rl.validate_response_item(item, v2(item, tier="none", anchors=[], evidence=[{"element_id": "A301.demand", "quote": "Demand for AI"}]))[1] \
        == rl.FAILURE_EVIDENCE_INVALID
    validated, reason = rl.validate_response_item(item, v2(item, tier=None, anchors=[], outcome="UNRESOLVED", unresolved="the referent is cut off"))
    assert reason is None and validated["state"] == rl.STATE_UNRESOLVED and validated["anchor_evidence"] == []


def test_a_missing_evidence_field_is_malformed_and_earlier_contract_failures_keep_their_reason():
    item = item_for()
    answer = v2(item)
    del answer["anchor_evidence"]
    assert rl.validate_response_item(item, answer)[1] == rl.FAILURE_MALFORMED_RESPONSE
    assert rl.validate_response_item(item, v2(item, tier="strong", anchors=[core_of("A301")]))[1] == rl.FAILURE_TIER_ANCHOR_INCONSISTENT
    assert rl.validate_response_item(item, v2(item, anchors=["A301.unknown"]))[1] == rl.FAILURE_ANCHOR_INVALID


# ----------------------------------------------------------------------------------------------------------- version dispatch
def test_each_output_contract_is_checked_as_itself():
    item = item_for()
    v1_answer = {k: v for k, v in v2(item).items() if k != "anchor_evidence"}
    assert rl.validate_response_item(item, v1_answer, output_schema_version=rl.OUTPUT_SCHEMA_V1)[1] is None
    assert rl.validate_response_item(item, v1_answer)[1] == rl.FAILURE_MALFORMED_RESPONSE  # the current contract needs the evidence
    assert rl.validate_response_item(item, v2(item), output_schema_version="alpha_relevance.judge.output.v9")[1] == rl.FAILURE_MALFORMED_RESPONSE
    assert rl.validate_response_item(item, v2(item), output_schema_version="")[1] == rl.FAILURE_MALFORMED_RESPONSE  # missing is not "current"
    out = rl.judge_returned_items([item], [v1_answer], output_schema_version=rl.OUTPUT_SCHEMA_V1)
    assert out[item.key]["state"] == rl.STATE_JUDGED and "anchor_evidence" not in out[item.key]


@pytest.fixture
def judged_under_v1(tmp_path, monkeypatch):
    with monkeypatch.context() as m:
        as_v1(m)
        assert rl.task_identity() == rl.task_identity(rl.PROMPT_VERSION_V1)
        make_run(tmp_path)
        assert judge(tmp_path, "run-a", scripted_answers(with_evidence=False))["status"] == "ok"
    return tmp_path, "run-a"


def test_a_v1_judgment_is_stale_under_v2_and_shown_with_its_own_versions(judged_under_v1):
    root, run_id = judged_under_v1
    views = verify(root, run_id).pairs
    assert {(v["state"], v["reason"], v["tier"]) for v in views.values()} == {(rl.STATE_FAILED, "binding_stale", None)}
    for view in views.values():
        assert view["versions"] == {"prompt_version": rl.PROMPT_VERSION_V1, "criterion_version": rl.CRITERION_EXP1,
                                    "output_schema_version": rl.OUTPUT_SCHEMA_V1}
        assert {"prompt_version", "criterion_version", "output_schema_version"} <= set(view["reason_detail"].split(","))


def test_a_v1_judgment_still_verifies_as_v1_against_its_own_identity(judged_under_v1):
    root, run_id = judged_under_v1
    matches = json.loads((root / run_id / "alpha_matches.json").read_text(encoding="utf-8"))["matches"]
    pairs = {(m["claim_id"], m["matched_alpha"]): (TICKER, m) for m in matches}
    verification = verify_relevance_records(root / run_id, owner_run_id=run_id, pairs=pairs, identity=rl.task_identity(rl.PROMPT_VERSION_V1))
    assert {(v["state"], v["tier"]) for v in verification.pairs.values()} == {(rl.STATE_JUDGED, "core"), (rl.STATE_JUDGED, "strong")}
    assert all(v["versions"]["prompt_version"] == rl.PROMPT_VERSION_V1 and v["anchor_evidence"] == [] for v in verification.pairs.values())
    hybrid = {**rl.task_identity(rl.PROMPT_VERSION_V1), "criterion_version": rl.CRITERION_EXP2}
    refused = verify_relevance_records(root / run_id, owner_run_id=run_id, pairs=pairs, identity=hybrid)
    assert refused.error == "unknown_task_identity" and {v["state"] for v in refused.pairs.values()} == {rl.STATE_FAILED}


def test_the_trace_view_shows_each_record_with_the_versions_it_was_made_under(judged_under_v1, tmp_path_factory):
    from comqutor_alpha.api import evidence_trace as et

    root, run_id = judged_under_v1
    old = et._relevance_view(SimpleNamespace(relevance=verify(root, run_id), run_id=run_id, metadata={}), claim(run_id, 1), {"matched_alpha": "A301"})
    assert (old["state"], old["tier"], old["reason"]) == (rl.STATE_FAILED, None, "binding_stale")
    assert (old["source"]["prompt_version"], old["source"]["criterion_version"]) == (rl.PROMPT_VERSION_V1, rl.CRITERION_EXP1)
    new_root = tmp_path_factory.mktemp("v2")
    make_run(new_root)
    assert judge(new_root, "run-a", scripted_answers(with_evidence=True))["status"] == "ok"
    view = et._relevance_view(SimpleNamespace(relevance=verify(new_root, "run-a"), run_id="run-a", metadata={}), claim("run-a", 1), {"matched_alpha": "A301"})
    assert (view["state"], view["tier"]) == (rl.STATE_JUDGED, "core")
    assert (view["source"]["prompt_version"], view["source"]["criterion_version"], view["source"]["output_schema_version"]) == (
        rl.PROMPT_VERSION_V2, rl.CRITERION_EXP2, rl.OUTPUT_SCHEMA_V2)
    assert view["anchors"][0]["evidence_quotes"] == ["Demand for data-center GPUs beat expectations again."[:40]]  # what the answer quoted
    unjudged = et._relevance_view(SimpleNamespace(relevance=verify(new_root, "run-a"), run_id="run-a", metadata={}), "no-such-claim", {"matched_alpha": "A301"})
    assert unjudged["state"] == rl.STATE_UNJUDGED and unjudged["source"]["prompt_version"] is None  # no record: no version is claimed


def test_an_edited_quote_in_the_saved_results_is_not_reproduced_by_the_ledger(tmp_path):
    make_run(tmp_path)
    assert judge(tmp_path, "run-a", scripted_answers(with_evidence=True))["status"] == "ok"
    path = tmp_path / "run-a" / RESULTS_FILENAME
    payload = json.loads(path.read_text(encoding="utf-8"))
    payload["records"][0]["anchor_evidence"] = [{"element_id": payload["records"][0]["anchor_element_ids"][0], "quote": "Demand for data-center GPUs"}]
    path.write_text(json.dumps(payload), encoding="utf-8")
    assert verify(tmp_path, "run-a").pairs[(claim("run-a", 1), "A301")]["reason"] == "ledger_label_mismatch"


# ----------------------------------------------------------------------------------------------------------- the first real run (prompt v1)
@needs_live_v1
def test_the_first_real_run_re_evaluates_to_identical_results_as_v1():
    manifest = json.loads((PHASE2 / "sample/sample_manifest.json").read_text(encoding="utf-8"))
    plan = json.loads((PHASE2 / "plan/execution_plan.json").read_text(encoding="utf-8"))
    report = ev.evaluate(manifest=manifest, plan=plan, eval_dir=LIVE_V1, review_a=PHASE2 / "review/blind_review_sheet_A.csv")
    original = json.loads((PHASE2 / "live_evaluation/evaluation_report.json").read_text(encoding="utf-8"))
    for key in ("totals", "reference", "repeat_consistency", "samples", "verification", "by_primary_stratum", "thresholds", "banner"):
        assert report[key] == original[key], key
    assert report["inputs"]["task"] == rl.task_identity(rl.PROMPT_VERSION_V1)
    # read against the CURRENT identity, the same records are stale -- never relabelled v2
    samples = {s["sample_id"]: s for s in manifest["samples"]}
    round_id = f"{LIVE_V1.name}-r1"
    pairs = {(s["claim_id"], s["target_alpha_id"]): (s["ticker"], {"claim_id": s["claim_id"], "matched_alpha": s["target_alpha_id"], "claim": s["claim_text"]})
             for s in samples.values()}
    current = verify_relevance_records(LIVE_V1 / round_id, owner_run_id=round_id, pairs=pairs)
    assert {(v["state"], v["reason"]) for v in current.pairs.values()} == {(rl.STATE_FAILED, "binding_stale")}
    assert {v["versions"]["prompt_version"] for v in current.pairs.values()} == {rl.PROMPT_VERSION_V1}


@needs_live_v1
def test_the_cost_basis_is_measured_from_the_task_own_real_calls_with_exactly_rebuilt_prompts():
    ledgers = sorted(LIVE_V1.glob("*/alpha_relevance_ledger/llm_semantic_calls.jsonl"))
    basis = ep.measure_relevance_ledgers(ledgers)
    assert basis["basis_kind"] == "relevance_task_own_real_calls" and basis["basis_prompt_versions"] == {rl.PROMPT_VERSION_V1: 30}
    assert basis["basis"]["calls"] == 30 and basis["basis"]["excluded"] == {}
    assert 3.0 < basis["basis"]["chars_per_input_token"]["median"] < 4.5
    assert basis["max_tokens_enforcement"]["calls_over_cap"] == 0 and list(basis["max_tokens_enforcement"]["by_cap"]) == ["16384"]
    assert ep.estimate_basis(basis) is basis["basis"]


def test_a_relevance_ledger_measurement_excludes_what_it_cannot_rebuild(tmp_path):
    item = item_for()
    payload = rl.batch_payload([item], criterion_version=rl.CRITERION_EXP1)
    good = {"task": rl.LLM_TASK_NAME, "execution_mode": "live", "run_id": "r", "call_id": "1", "prompt_version": rl.PROMPT_VERSION_V1,
            "prompt_sha256": RECORDED_V1_PROMPT_SHA256, "input_payload": payload, "validation_status": "accepted", "latency_ms": 20000,
            "token_usage": {"input_tokens": 1000, "output_tokens": 3000}, "request_control": {"max_tokens_value": 16384, "request_model": "m"},
            "provider_response": {"finish_reason": "stop", "response_model": "served"}, "provider": "p", "model": "m", "started_at": "2026-10-12T20:00:00Z"}
    rows = [good, {**good, "call_id": "2", "prompt_sha256": "0" * 64}, {**good, "call_id": "3", "task": "evidence_stance_classifier"},
            {**good, "call_id": "4", "execution_mode": "test"}, good]
    path = tmp_path / "calls.jsonl"
    path.write_text("".join(json.dumps(r) + "\n" for r in rows), encoding="utf-8")
    basis = ep.measure_relevance_ledgers([path])
    assert basis["basis"]["calls"] == 1 and basis["basis"]["excluded"] == {"prompt_identity_not_reproduced": 1}
    assert basis["basis"]["chars_per_input_token"]["median"] == round(len(rl.build_prompt(payload, rl.PROMPT_VERSION_V1)) / 1000, 3)
    assert basis["basis"]["output_tokens_per_item"]["median"] == 3000.0 and basis["basis"]["latency_seconds_per_item"]["median"] == 20.0
    assert basis["max_tokens_enforcement"]["calls"] == 2  # cap evidence does not depend on the prompt identity
    assert basis["model_names_observed"]["pairs"] == [{"requested": "m", "returned_by_provider": "served", "calls": 2}]


# ----------------------------------------------------------------------------------------------------------- simulated provider v2
def _bucket_pair(bucket: int) -> tuple[str, str]:
    import hashlib  # noqa: PLC0415

    return next((f"c{i}", "A301") for i in range(10_000) if int(hashlib.sha256(f"c{i}|A301".encode()).hexdigest()[:8], 16) % 22 == bucket)


def test_the_simulated_provider_quotes_the_claim_and_one_bucket_quotes_foreign_words():
    definition = {"elements": [{"id": e, "ownership": o} for e, o in DEFS["A301"].ownership.items()]}
    text = "Demand   for AI accelerators rose sharply this quarter."
    for bucket, expected in ((0, None), (21, rl.FAILURE_EVIDENCE_INVALID)):
        claim_id, alpha = _bucket_pair(bucket)
        entries = ex.SimulatedRelevanceProvider._answers(claim_id, alpha, definition, text)  # noqa: SLF001
        assert "TEST DATA" in entries[0]["basis"] and ex.SIMULATION_RULE in entries[0]["basis"]
        assert rl.validate_response_item(item_for(text=text, claim_id=claim_id), entries[0])[1] == expected


# ----------------------------------------------------------------------------------------------------------- development retest
def test_a_review_sheet_subset_copies_rows_field_by_field():
    rows = [{"sample_id": f"S00{i}", "tier": t, "basis": f"basis, with a comma {i}"} for i, t in enumerate(("core", "weak", "strong"), start=1)]
    text = ep.render_csv(rows, ["sample_id", "tier", "basis"])
    subset, check = ep.review_sheet_subset(text, ["S003", "S001"])
    kept = list(csv.DictReader(io.StringIO(subset.lstrip("﻿"))))
    assert [r["sample_id"] for r in kept] == ["S001", "S003"] and kept[1] == rows[2] and check["every_field_identical_to_source"] is True
    with pytest.raises(ValueError, match="REVIEW_SUBSET_ROWS"):
        ep.review_sheet_subset(text, ["S001", "S009"])


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
    """A small REAL sample (two saved GOOGL runs, re-read from disk), the way the phase-2 tests build one."""
    if len(GOOGL_RUNS) < 2:
        pytest.skip("the saved GOOGL runs are not present (local run data)")
    selection = ep.select_sample(ep.scan_candidates(GOOGL_RUNS, DEFS), quotas={ep.STRATUM_ORDINARY: 9})
    return ep.build_manifest(selection, DEFS, pool_runs=[r.name for r in GOOGL_RUNS])


def test_a_retest_sample_is_an_exact_tagged_subset_and_carries_no_answer(small_manifest):
    ids = sorted(s["sample_id"] for s in small_manifest["samples"])
    entries = [{"sample_id": ids[3], "category": "flip", "checks": "repeat stability"}, {"sample_id": ids[0], "category": "error", "checks": "subcategory rule"}]
    retest = ep.build_retest_manifest(small_manifest, entries, purpose="TEST")
    assert ep.manifest_content_sha256(retest) == retest["content_sha256"] and retest["sample_count"] == 2
    assert retest["derived_from"]["sample_manifest_content_sha256"] == small_manifest["content_sha256"]
    originals = {s["sample_id"]: s for s in small_manifest["samples"]}
    for sample in retest["samples"]:
        assert {k: v for k, v in sample.items() if k != "retest"} == originals[sample["sample_id"]]
    assert [s["sample_id"] for s in retest["samples"]] == [ids[0], ids[3]] and retest["task"] == rl.task_identity()
    assert all(set(s["retest"]) == {"category", "checks"} for s in retest["samples"])  # neither a reference nor an expected answer
    for bad, code in (([{"sample_id": "S999", "category": "x", "checks": "y"}], "UNKNOWN_SAMPLE"), ([entries[0], entries[0]], "DUPLICATE_SAMPLE"),
                      ([{"sample_id": ids[1], "category": "", "checks": "y"}], "RETEST_TAG_MISSING")):
        with pytest.raises(ValueError, match=code):
            ep.build_retest_manifest(small_manifest, bad, purpose="TEST")


RETEST_SAMPLE_DIR = PHASE2 / "exp2_v2_20261012/retest/retest_sample"


@pytest.mark.skipif(not (RETEST_SAMPLE_DIR / "retest_manifest.json").is_file(), reason="the retest deliverable is local only")
def test_the_saved_retest_sample_is_an_exact_subset_of_the_sample_and_of_sheet_a():
    manifest = json.loads((PHASE2 / "sample/sample_manifest.json").read_text(encoding="utf-8"))
    retest = json.loads((RETEST_SAMPLE_DIR / "retest_manifest.json").read_text(encoding="utf-8"))
    assert ep.manifest_content_sha256(retest) == retest["content_sha256"] and retest["derived_from"]["sample_manifest_content_sha256"] == manifest["content_sha256"]
    originals = {s["sample_id"]: s for s in manifest["samples"]}
    for sample in retest["samples"]:
        assert {k: v for k, v in sample.items() if k != "retest"} == originals[sample["sample_id"]]
    sheet = {r["sample_id"]: r for r in csv.DictReader(io.StringIO((PHASE2 / "review/blind_review_sheet_A.csv").read_text(encoding="utf-8-sig")))}
    subset = list(csv.DictReader(io.StringIO((RETEST_SAMPLE_DIR / "reference_A_subset.csv").read_text(encoding="utf-8-sig"))))
    assert [r["sample_id"] for r in subset] == [s["sample_id"] for s in retest["samples"]]
    assert all(row == sheet[row["sample_id"]] for row in subset)


TEST_OWN_BASIS = {
    "sources": [], "basis_task": rl.LLM_TASK_NAME, "basis_kind": "relevance_task_own_real_calls", "basis_prompt_versions": {rl.PROMPT_VERSION_V1: 30},
    "reference_provider_models": [], "model_names_observed": None,
    "basis": {"calls": 30, "chars_per_input_token": {"median": 3.6, "min": 3.5, "max": 3.9}, "output_tokens_per_item": {"median": 1700.0, "max": 4900.0},
              "latency_seconds_per_item": {"median": 8.0, "max": 30.0}},
    "max_tokens_enforcement": {"calls": 0, "calls_over_cap": 0, "by_cap": {}},
}


@pytest.fixture
def retest_inputs(tmp_path, small_manifest):
    chosen = sorted(s["sample_id"] for s in small_manifest["samples"])[:6]
    retest = ep.build_retest_manifest(small_manifest, [{"sample_id": s, "category": "TEST", "checks": "TEST"} for s in chosen], purpose="TEST retest")
    manifest_path = tmp_path / "retest_manifest.json"
    manifest_sha = ep.write_json(manifest_path, retest)
    plan = ep.build_plan(retest, DEFS, manifest_file_sha256=manifest_sha, reference=TEST_OWN_BASIS, provider=ep.LIVE_PROVIDER, model=ep.LIVE_MODEL,
                         batch_size=ep.LIVE_BATCH_SIZE, repeat_every=ep.LIVE_REPEAT_EVERY, timeout_seconds=ep.LIVE_TIMEOUT_SECONDS,
                         max_output_tokens=ep.LIVE_MAX_OUTPUT_TOKENS, repo_root=REPO_ROOT, repeat_sample_ids=[chosen[0]], purpose="TEST retest",
                         purpose_kind=ep.RETEST_PURPOSE_KIND, experiment_config=ex.P4_RELEVANCE_LIVE_DEV_RETEST_V2_20261012.name,
                         quality_thresholds=ep.RETEST_THRESHOLDS, pre_registered={"engineering_expectations_file_sha256": "TEST"})
    plan_path = tmp_path / "execution_plan.json"
    ep.write_json(plan_path, plan)
    auth = ep.rehearsal_authorization(plan, authorized_by="TEST DATA rehearsal", authorized_at=(NOW - timedelta(hours=1)).isoformat(),
                                      valid_until=(NOW + timedelta(hours=1)).isoformat())
    auth_path = tmp_path / "authorization_SIMULATED_REHEARSAL.json"
    ep.write_json(auth_path, auth)
    rows = ep.blind_review_rows(small_manifest, DEFS)
    for row in rows[:2]:  # TEST DATA confirmations, so the subset carries confirmed rows
        row.update(outcome="DETERMINED", tier="weak", anchor_element_ids="", basis="TEST DATA", review_status="CONFIRMED", reviewer="TEST DATA",
                   reviewed_at="2026-10-12")
    sheet, check = ep.review_sheet_subset(ep.render_csv(rows, ep.REVIEW_COLUMNS), chosen)
    assert check["every_field_identical_to_source"] is True
    sheet_path = tmp_path / "reference_A_subset.csv"
    sheet_path.write_text(sheet, encoding="utf-8")
    confirmed = sum(1 for row in rows[:2] if row["sample_id"] in chosen)
    return {"manifest": manifest_path, "plan": plan_path, "authorization": auth_path, "eval_root": tmp_path / "evaluations", "sheet": sheet_path,
            "plan_body": plan, "retest": retest, "chosen": chosen, "confirmed": confirmed}


def test_a_retest_plan_repeats_the_batches_of_its_chosen_samples_and_freezes_its_purpose(retest_inputs):
    plan, first = retest_inputs["plan_body"], retest_inputs["chosen"][0]
    assert len(plan["rounds"][0]["batches"]) > 1, "the sample must span several batches for the repeat selection to mean anything"
    assert [b["batch_id"][1:] for b in plan["rounds"][1]["batches"]] == [b["batch_id"] for b in plan["rounds"][0]["batches"] if first in b["sample_ids"]]
    assert plan["requests"]["repeat_selected_by_samples"] == [first]
    assert plan["task"] == rl.task_identity() and plan["purpose"] == {"kind": ep.RETEST_PURPOSE_KIND, "text": "TEST retest"}
    assert plan["experiment_config"] == ex.P4_RELEVANCE_LIVE_DEV_RETEST_V2_20261012.name and plan["quality_thresholds"] == ep.RETEST_THRESHOLDS
    assert plan["pre_registered"] == {"engineering_expectations_file_sha256": "TEST"} and ep.plan_content_sha256(plan) == plan["plan_sha256"]
    assert plan["request_cap"] <= ex.P4_RELEVANCE_LIVE_DEV_RETEST_V2_20261012.max_calls
    assert "this task's own real calls" in plan["estimate_method"]["input_tokens"] and rl.PROMPT_VERSION_V2 in plan["unknowns"][0]
    out = plan["estimates"]["total"]["output_tokens"]
    items = plan["estimates"]["total"]["items"]
    assert out["hard_bound"] == plan["request_cap"] * ep.LIVE_MAX_OUTPUT_TOKENS
    assert out["high"] == min(round(items * 4900.0 * ep.OUTPUT_HIGH_MULTIPLIER), out["hard_bound"])
    assert plan["cost_estimate"]["high_usd_peak"] <= plan["cost_estimate"]["hard_bound_usd_peak"]
    with pytest.raises(ValueError, match="REPEAT_SAMPLE_NOT_IN_PLAN"):
        ep.build_plan(retest_inputs["retest"], DEFS, manifest_file_sha256="x", reference=TEST_OWN_BASIS, provider=ep.LIVE_PROVIDER, model=ep.LIVE_MODEL,
                      batch_size=ep.LIVE_BATCH_SIZE, repeat_every=2, timeout_seconds=300.0, max_output_tokens=16384, repo_root=REPO_ROOT,
                      repeat_sample_ids=["S999"])


def test_the_high_output_estimate_never_exceeds_the_hard_bound():
    batches = [{"prompt_chars": 8000, "items": 4}, {"prompt_chars": 8000, "items": 4}]
    rates = {"chars_per_input_token": {"median": 3.6, "min": 3.5, "max": 3.9}, "latency_seconds_per_item": {"median": 9.0, "max": 28.0}}
    large = ep._estimates(batches, {"basis": {**rates, "output_tokens_per_item": {"median": 1500.0, "max": 5000.0}}},  # noqa: SLF001
                          max_output_tokens=16384, timeout_seconds=300.0)["output_tokens"]
    assert large == {"central": 12000, "high": 2 * 16384, "hard_bound": 2 * 16384}  # 8 x 5000 x 2 = 80,000 would exceed what max_tokens allows
    small = ep._estimates(batches, {"basis": {**rates, "output_tokens_per_item": {"median": 500.0, "max": 1000.0}}},  # noqa: SLF001
                          max_output_tokens=16384, timeout_seconds=300.0)["output_tokens"]
    assert small == {"central": 4000, "high": 16000, "hard_bound": 2 * 16384}


def test_a_retest_plan_runs_only_under_its_own_configuration(retest_inputs):
    paths = retest_inputs
    refused = ex.run_relevance_evaluation_plan(plan_path=paths["plan"], manifest_path=paths["manifest"], authorization_path=paths["authorization"],
                                               eval_root=paths["eval_root"], mode=ex.EVAL_MODE_REHEARSAL, now=NOW,
                                               config=ex.P4_RELEVANCE_LIVE_SMALL_SAMPLE_20261012, provider=ex.SimulatedRelevanceProvider())
    assert refused["error_code"] == "PLAN_CONFIG_MISMATCH" and not paths["eval_root"].exists()
    assert not Path(str(paths["authorization"]) + ex.AUTHORIZATION_CONSUMED_SUFFIX).exists()


def test_a_retest_rehearsal_is_verified_under_v2_and_reported_as_a_development_result(retest_inputs):
    paths = retest_inputs
    result = ex.run_relevance_evaluation_plan(plan_path=paths["plan"], manifest_path=paths["manifest"], authorization_path=paths["authorization"],
                                              eval_root=paths["eval_root"], mode=ex.EVAL_MODE_REHEARSAL, now=NOW,
                                              config=ex.P4_RELEVANCE_LIVE_DEV_RETEST_V2_20261012, provider=ex.SimulatedRelevanceProvider())
    assert result["status"] == "ok" and result["requests_sent"] == paths["plan_body"]["request_cap"]
    report = ev.evaluate(manifest=paths["retest"], plan=paths["plan_body"], eval_dir=result["evaluation_dir"], review_a=paths["sheet"])
    assert report["banner"].startswith("DEVELOPMENT-SET RETEST") and "TEST DATA" in report["banner"]
    assert report["inputs"]["task"] == rl.task_identity() and report["thresholds"]["status"] == "NOT_APPLIED"
    assert report["reference"]["reference_rows"]["CONFIRMED"] == paths["confirmed"]
    assert report["verification"] and all(r["error"] is None and r["results_present"] for r in report["verification"].values())
    assert all(row["round_1_outcome"] in ev.MODEL_OUTCOMES for row in report["samples"])
    assert all(t["failure_categories"]["read_time_verification"] == 0 for t in report["totals"].values())  # every record verifies under v2


def test_disagreeing_v1_records_are_still_a_conflict_when_reproduced_under_their_own_contract(judged_under_v1):
    import copy  # noqa: PLC0415
    import hashlib  # noqa: PLC0415

    root, run_id = judged_under_v1
    ledger_dir = root / run_id / LEDGER_DIRNAME
    calls = ledger_dir / "llm_semantic_calls.jsonl"
    records = [json.loads(line) for line in calls.read_text(encoding="utf-8").splitlines()]
    first = next(r for r in records if r["validation_status"] == "accepted" and r["input_payload"]["items"][0]["alpha_id"] == "A301")
    twin = copy.deepcopy(first)
    twin["call_id"] = first["call_id"] + ":twin"
    twin["validated_output"]["items"][0].update(tier="weak", anchor_element_ids=[])  # a second accepted v1 answer that disagrees
    calls.write_text("".join(json.dumps(r) + "\n" for r in [*records, twin]), encoding="utf-8")
    manifest = ledger_dir / "llm_semantic_manifest.json"
    sealed = json.loads(manifest.read_text(encoding="utf-8"))
    sealed["calls_file_sha256"] = hashlib.sha256(calls.read_bytes()).hexdigest()
    manifest.write_text(json.dumps(sealed), encoding="utf-8")
    matches = json.loads((root / run_id / "alpha_matches.json").read_text(encoding="utf-8"))["matches"]
    pairs = {(m["claim_id"], m["matched_alpha"]): (TICKER, m) for m in matches}
    views = verify_relevance_records(root / run_id, owner_run_id=run_id, pairs=pairs, identity=rl.task_identity(rl.PROMPT_VERSION_V1)).pairs
    assert (views[(claim(run_id, 1), "A301")]["state"], views[(claim(run_id, 1), "A301")]["reason"]) == (rl.STATE_FAILED, "ledger_conflict")
    assert views[(claim(run_id, 2), "A601")]["state"] == rl.STATE_JUDGED


def test_an_evaluation_reads_an_execution_under_the_identity_of_its_plan(tmp_path, monkeypatch):
    eval_id = "relevance-eval-TEST"
    round_id = f"{eval_id}-r1"
    eval_dir = tmp_path / eval_id
    eval_dir.mkdir()
    with monkeypatch.context() as m:
        as_v1(m)
        make_run(eval_dir, round_id)
        assert judge(eval_dir, round_id, scripted_answers(with_evidence=False))["status"] == "ok"
    matches = json.loads((eval_dir / round_id / "alpha_matches.json").read_text(encoding="utf-8"))["matches"]
    samples = [{"sample_id": f"S{i}", "claim_id": x["claim_id"], "target_alpha_id": x["matched_alpha"], "ticker": TICKER, "claim_text": x["claim"]}
               for i, x in enumerate(matches, start=1)]
    manifest = {"content_sha256": "TEST-M", "samples": samples}
    plan = {"plan_sha256": "TEST-P", "task": rl.task_identity(rl.PROMPT_VERSION_V1),
            "rounds": [{"round": 1, "batches": [{"sample_ids": [s["sample_id"] for s in samples]}]}]}
    (eval_dir / ev.EVAL_RECORD_FILENAME).write_text(json.dumps({"plan_sha256": "TEST-P", "sample_manifest_content_sha256": "TEST-M",
                                                                "evaluation_id": eval_id}), encoding="utf-8")
    as_planned = ev.load_execution(eval_dir, manifest, plan, DEFS)["rounds"][1]["views"]
    assert sorted(v["model_outcome"] for v in as_planned.values()) == ["core", "strong"]
    as_current = ev.load_execution(eval_dir, manifest, {**plan, "task": rl.task_identity()}, DEFS)["rounds"][1]["views"]
    assert {(v["state"], v["reason"]) for v in as_current.values()} == {(rl.STATE_FAILED, "binding_stale")}


# The CONSTRUCTED contrast cases of exp2_v2_20261012/04_相邻对照案例.md (engineering sentences, never sent to a model): the documented
# expectation must be a valid output-v2 answer -- its quotes are the sentence's own words and its anchors fit the tier. Self-consistency of
# the documentation only, not a statement about what a model answers.
CONSTRUCTED = [
    ("C1a", "A201", "Demand for HBM memory chips rose sharply this quarter.", "core", [("A201.semiconductor_demand", "Demand for HBM memory chips rose")]),
    ("C1b", "A201", "Shares of memory makers rallied on hopes of an AI boom.", "weak", []),
    ("C2a", "A101", "Cloud providers raised their AI capex budgets for next year.", "core", [("A101.ai_capex", "Cloud providers raised their AI capex budgets")]),
    ("C2b", "A101", "The company unveiled a three-generation GPU product roadmap.", "weak", []),
    ("C3a", "A201", "Unlike last year's glut, chip inventories are now lean.", "core", [("A201.inventory", "chip inventories are now lean")]),
    ("C3b", "A102", "Competition in inference chips is heating up as new entrants launch products.", "weak", []),
    ("C4a", "A001", "The Fed's next policy meeting is scheduled for December.", "weak", []),
    ("C4b", "A001", "The company appointed a new chief financial officer.", "none", []),
    ("C4c", "A201", "A semiconductor company announced a new chief executive officer.", "none", []),
]


@pytest.mark.parametrize(("case_id", "alpha", "text", "tier", "evidence"), CONSTRUCTED, ids=[c[0] for c in CONSTRUCTED])
def test_constructed_contrast_cases_are_well_formed_under_output_v2(case_id, alpha, text, tier, evidence):
    item = item_for(text=text, alpha_id=alpha, claim_id=case_id)
    payload = rl.batch_payload([item])
    assert payload["items"][0]["claim_text"] == text and text in rl.build_prompt(payload)  # the request carries the sentence verbatim
    answer = v2(item, tier=tier, anchors=[e for e, _q in evidence], evidence=[{"element_id": e, "quote": q} for e, q in evidence])
    validated, reason = rl.validate_response_item(item, answer)
    assert reason is None and validated["tier"] == tier


@needs_phase2
def test_constructed_contrast_cases_are_not_development_samples():
    texts = {s["claim_text"] for s in json.loads((PHASE2 / "sample/sample_manifest.json").read_text(encoding="utf-8"))["samples"]}
    assert not texts & {c[2] for c in CONSTRUCTED}


def test_an_evidence_failure_is_counted_as_a_contract_failure():
    views = {"S1": {"state": rl.STATE_FAILED, "tier": None, "reason": rl.FAILURE_EVIDENCE_INVALID, "model_outcome": rl.STATE_FAILED}}
    assert ev.round_totals(views)["failure_categories"] == {"call_level": 0, "contract_level": 1, "read_time_verification": 0}


def test_a_plan_without_thresholds_is_never_scored():
    plan = {"quality_thresholds": ep.RETEST_THRESHOLDS, "quality_thresholds_sha256": "x"}
    record = {"test_data": False, "authorization": {"quality_thresholds_confirmed": True, "quality_thresholds_sha256": "x"}}
    assert ev.apply_thresholds(plan, record, {})["status"] == "NOT_APPLICABLE"
