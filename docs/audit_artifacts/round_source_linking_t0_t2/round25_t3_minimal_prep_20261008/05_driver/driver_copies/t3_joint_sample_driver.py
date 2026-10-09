#!/usr/bin/env python3
"""T3 joint five-link driver for the FROZEN round-25 sample (round25_t3_minimal_prep_20261008/04_joint_sample/).

John's T3 joint check, per sample:

    source content -> claim faithful? -> Alpha correct? -> direction toward that Alpha correct? -> eligible for the activation / conflict pool?

Every system answer comes from the production function that produces it in a real run -- never a re-implementation:

  L1 source -> claim      content_support_llm.apply_llm_content_support_verification   (the production content-support pass)
  L2 Alpha                alpha_mapper.map_structured_records                          (the production classifier call, single path)
  L3 direction            evidence_stance_llm.apply_llm_stance_upgrade                 (the production LLM stance pass, batches of 10)
  L4 claim eligibility    evidence_fact_index.select_supporting_alpha_claims           (activation / conflict supporting-evidence selector)
                          + source_provenance.compute_verified_support_eligibility     (the verified-support gate)

L2 and L3 run in the same order build_alpha_matches_payload runs them in production; L3 may use its own gateway so the stance step can be
given its own timeout (a frozen, disclosed deviation, see the execution proposal). A deterministic stance is NEVER reported as a direction
result: when the LLM stance fails, production falls back to the deterministic baseline, and this driver records that as TASK_FAILED with
the fallback reason.

Outcomes kept apart, never folded into each other: NONE (the model's own explicit none), SELECTED_BUT_NOT_MATCHED (a production gate
overrode the selection), NOT_APPLICABLE (the link has nothing to judge, e.g. no Alpha), TASK_FAILED (call / parse / timeout / truncation /
budget), NOT_JUDGEABLE_NO_SOURCE_CONTENT (the sample carries no saved source content).

Modes:
  prepare   zero calls: freeze identity (sample, form, taxonomy, prompts, code, configuration)
  sizing    zero calls: exact request counts (content support, Alpha) and the stance upper bound, for the budget
  predict   real calls ONLY with --authorized-plan <plan.json> whose sha256 matches --plan-sha256, marked authorized by a named person,
            matching the frozen manifest and prompts; never run in round 25
  score     zero calls: per-link statistics against reviewer judgments that carry a reviewer_id

Predictions are written to their own file and never into the review form.
"""
from __future__ import annotations

import argparse
import hashlib
import importlib.util
import json
import subprocess
import sys
from collections import Counter
from collections.abc import Callable
from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

HERE = Path(__file__).resolve().parent
REPO = next(p for p in HERE.parents if (p / "comqutor_alpha").is_dir())
sys.path.insert(0, str(REPO))

_DIAG_SPEC = importlib.util.spec_from_file_location("t3_diagnostic_evaluation_driver_for_joint", HERE / "t3_diagnostic_evaluation_driver.py")
assert _DIAG_SPEC is not None and _DIAG_SPEC.loader is not None
_diag = importlib.util.module_from_spec(_DIAG_SPEC)
sys.modules[_DIAG_SPEC.name] = _diag
_DIAG_SPEC.loader.exec_module(_diag)
classify_outcome = _diag.classify_outcome
score_alpha_against_labels = _diag.score_against_human_labels

SCHEMA_VERSION = "t3_joint_sample_driver.v1"
NOT_JUDGEABLE_NO_SOURCE_CONTENT = "NOT_JUDGEABLE_NO_SOURCE_CONTENT"
NOT_APPLICABLE = "NOT_APPLICABLE"
TASK_FAILED = "TASK_FAILED"
NOT_SUBMITTED = "NOT_SUBMITTED"
LLM_RESULT = "LLM_RESULT"
DETERMINISTIC_VERIFIER_RESULT = "DETERMINISTIC_VERIFIER_RESULT"  # production's own L1 answer for a pure data fact, labeled as such
REVIEWER_UNABLE = "UNABLE_TO_JUDGE"
ELIGIBILITY_VOCAB = ("QUALIFIES", "DOES_NOT_QUALIFY")
# production writes the LLM's INSUFFICIENT as content_support_status PENDING_REVIEW; the form offers INSUFFICIENT
SYSTEM_TO_REVIEWER_RELATION = {"PENDING_REVIEW": "INSUFFICIENT"}
# a failure of these verified-gate conditions is a mechanical fact (link / time / binding), not a semantic disagreement
MECHANICAL_GATE_REASONS = frozenset({"SOURCE_LINK_NOT_VALID", "DISCLOSURE_TIME_UNKNOWN", "SOURCE_NOT_RESOLVABLE", "CONTENT_VERSION_CHANGED_SINCE_REVIEW",
                                     "REVIEW_CLAIM_MISMATCH", "REVIEW_SOURCE_NOT_LINKED_TO_CLAIM", "AVAILABILITY_NOT_BEFORE_EVIDENCE_CUTOFF"})
NEW_REQUEST = "NEW_REQUEST"
REUSED_SAVED_PRODUCTION_ANSWER = "REUSED_SAVED_PRODUCTION_ANSWER"
# where a sample's saved Alpha answer may come from: the sample's own run, plus (c904d4cc) the classification-recovery run that re-ran the
# same frozen inputs with the current prompt (round 15)
ALPHA_REUSE_LEDGERS = {
    "c904d4cc-dc09-495c-aec5-b056979948e1": ("c904d4cc-dc09-495c-aec5-b056979948e1", "recovery-20261007T053635Z-26d6cd1a"),
}


class SampleVersionMismatch(Exception):
    """The form's claim text for a judged sample differs from the claim the prediction was made for."""


# ----------------------------------------------------------------------------------------------------------------------------------
# frozen configuration and identity
# ----------------------------------------------------------------------------------------------------------------------------------


TASKS = ("content_support_verification", "alpha_classifier", "evidence_stance_classifier")


@dataclass
class FrozenConfig:
    """Everything a prediction run depends on besides code, prompt and data. The defaults are the round-25 PROPOSAL (see
    06_execution_proposal.md); an authorized plan states its own values, and those are what run. ``None`` for an output cap means the
    parameter is not sent (provider default), exactly as the deployed stance path does today."""

    provider: str = "deepseek"
    model: str = "deepseek-v4-flash"
    # alpha 45 s = the deployed value; content support and stance 120 s = the server gateway's own upper bound (see the proposal)
    timeout_seconds: dict[str, float] = field(default_factory=lambda: {"content_support_verification": 120.0, "alpha_classifier": 45.0, "evidence_stance_classifier": 120.0})
    # not sent for any task = what the deployed .env does today (no per-task cap variable is set)
    max_tokens: dict[str, int | None] = field(default_factory=lambda: {"content_support_verification": None, "alpha_classifier": None, "evidence_stance_classifier": None})
    # = the zero-call sizing (06_proposal/request_sizing_zero_call.json): exact for content support and Alpha, an upper bound for stance
    max_requests: dict[str, int] = field(default_factory=lambda: {"content_support_verification": 17, "alpha_classifier": 7, "evidence_stance_classifier": 5})
    # reuse a saved production Alpha answer when its prompt identity, input hash, provider/model all equal this request's and it succeeded on
    # its first attempt with validation accepted and finish_reason stop; replayed through the current code's own gates
    reuse_saved_alpha_answers: bool = True
    application_retries: int = 0
    sdk_retries: int = 0
    alpha_classifier_concurrency: int = 4  # week2_llm.DEFAULT_ALPHA_CLASSIFIER_CONCURRENCY
    stance_concurrency: int = 4  # week2_llm.DEFAULT_EVIDENCE_STANCE_CONCURRENCY
    # 1, not the production default 5: at 5, three of this sample's four batches exceed the gateway's 60,000-character input cap and are
    # refused before sending (sizing shows it); one claim per request fits (largest 46,064). Same parameter round 10's Phase C used.
    content_support_batch_size: int = 1
    alpha_classifier_path: str = "single (one claim per request; use_batched_classifier=False, the production default)"
    stance_batch_size: int = 10  # evidence_stance_llm.BATCH_SIZE, production constant (not configurable)
    cache: str = "none -- the gateway is built without a semantic response cache"
    unsent_parameters: str = "temperature, top_p, thinking / reasoning settings, response_format: not sent -> provider defaults"


def build_task_gateways(config: FrozenConfig, execution_id: str, output_root: Path) -> dict[str, Any]:
    """Real construction, reachable only through ``predict`` with an authorized plan. One production ``Week2LLMGateway`` per task, each with
    its own client (timeout, output cap, SDK retries), its own request cap (``max_calls``; one reservation per attempt, so with both retry
    layers at 0 it is the exact number of requests the task can send) and application retries; all three record into one semantic-call
    session. Built directly rather than through ``build_server_week2_llm_gateway`` because that builder has one shared timeout and no per-task
    timeout; the per-task values are frozen in the authorized plan (06_execution_proposal.md)."""
    import os

    from comqutor_alpha.llm_runtime.session import SemanticRuntimeSession
    from comqutor_alpha.structure_engine.week2_llm import Week2LLMGateway
    from tradingagents.llm_clients import create_llm_client

    base_url = os.environ.get("COMQUTOR_WEEK2_LLM_BASE_URL") or os.environ.get("TRADINGAGENTS_LLM_BACKEND_URL") or None
    run_dir = Path(output_root) / execution_id
    run_dir.mkdir(parents=True, exist_ok=False)
    session = SemanticRuntimeSession(run_id=execution_id, output_directory=run_dir, execution_mode="live", provider=config.provider, model=config.model)
    gateways = {}
    for task in TASKS:
        client_kwargs: dict[str, Any] = {"provider": config.provider, "model": config.model, "base_url": base_url,
                                         "timeout": config.timeout_seconds[task], "max_retries": config.sdk_retries}
        cap = config.max_tokens.get(task)
        if cap is not None:
            client_kwargs["max_tokens"] = int(cap)
        model = create_llm_client(**client_kwargs).get_llm()
        gateways[task] = Week2LLMGateway(model, run_id=execution_id, output_root=output_root, timeout_seconds=config.timeout_seconds[task],
                                         max_retries=config.application_retries, max_calls=config.max_requests[task],
                                         provider=config.provider, model_name=config.model, semantic_runtime=session)
    return gateways


def _sha256_file(path: Path) -> str:
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def _git(*args: str) -> str:
    return subprocess.run(["git", *args], cwd=REPO, capture_output=True, text=True, check=False).stdout


def freeze_identity(manifest_path: Path, review_form_path: Path, config: FrozenConfig, code_snapshot_dir: Path | None = None) -> dict[str, Any]:
    from comqutor_alpha.structure_engine import week2_llm

    taxonomy = REPO / "comqutor_alpha/alpha_library/alpha_taxonomy_v1.yaml"
    diff = _git("diff", "HEAD", "--binary")
    return {
        "schema_version": SCHEMA_VERSION,
        "frozen_at": datetime.now(timezone.utc).isoformat(),
        "sample_manifest": {"path": str(manifest_path), "sha256": _sha256_file(manifest_path)},
        "review_form": {"path": str(review_form_path), "sha256": _sha256_file(review_form_path)},
        "taxonomy": {"path": str(taxonomy.relative_to(REPO)), "sha256": _sha256_file(taxonomy)},
        "prompts": {
            task: {"version": week2_llm._TASK_RUNTIME_METADATA[task]["prompt_version"], "identity_sha256": week2_llm.Week2LLMGateway.prompt_identity_sha256(task)}
            for task in TASKS
        },
        "code": {
            "git_head": _git("rev-parse", "HEAD").strip(),
            "tracked_diff_sha256": hashlib.sha256(diff.encode("utf-8")).hexdigest(),
            "untracked_source_snapshot": str(code_snapshot_dir) if code_snapshot_dir else None,
        },
        "config": asdict(config),
    }


# ----------------------------------------------------------------------------------------------------------------------------------
# inputs
# ----------------------------------------------------------------------------------------------------------------------------------


def load_samples(manifest_path: Path, runs_root: Path | None = None) -> list[dict[str, Any]]:
    """The frozen sample, each with its claim record and source registry read from the saved run (read-only)."""
    runs_root = runs_root or (REPO / "outputs" / "runs")
    manifest = json.loads(Path(manifest_path).read_text(encoding="utf-8"))
    cache: dict[str, tuple[list, dict, list]] = {}
    samples = []
    for item in manifest["samples"]:
        run_id = item["run_id"]
        if run_id not in cache:
            run_dir = runs_root / run_id
            structured = json.loads((run_dir / "structured_agent_outputs.json").read_text(encoding="utf-8"))
            # an in-memory copy of the WHOLE run: the content-support request builds each claim's report_context from its siblings
            run_records = json.loads(json.dumps(structured.get("records") or structured.get("claims") or []))
            registry = run_dir / "source_registry.json"
            sources = json.loads(registry.read_text(encoding="utf-8")).get("sources", []) if registry.exists() else []
            cache[run_id] = (run_records, {r["claim_id"]: r for r in run_records}, sources)
        run_records, by_id, sources = cache[run_id]
        record = by_id.get(item["claim_id"])
        if record is None:
            raise KeyError(f"claim {item['claim_id']} not found in run {run_id}")
        samples.append({"sample_id": item["sample_id"], "cell": item["cell"], "chain": item["chain"], "run_id": run_id,
                        "record": record, "run_records": run_records, "sources": sources})
    return samples


def strip_saved_llm_content_verdict(record: dict[str, Any]) -> str | None:
    """A content-support result saved by an earlier LLM pass is not reused: the saved runs do not record which prompt, model, budget and
    attempt produced it. It is removed from the sampled record before L1 so that neither L1 nor L4 can see it; a deterministic or human
    review is left untouched. Returns "verdict" (a saved LLM verdict was removed), "failure" (only a saved failure reason was removed)
    or None."""
    from comqutor_alpha.source_provenance import REVIEW_METHOD_LLM_CONTENT_SUPPORT_VERIFIED

    review = record.get("content_support_review")
    had_verdict = bool(record.get("content_support_llm_detail")) or (
        isinstance(review, dict) and review.get("method") == REVIEW_METHOD_LLM_CONTENT_SUPPORT_VERIFIED)
    had_failure = bool(record.get("content_support_llm_fallback_reason"))
    record.pop("content_support_llm_detail", None)
    record.pop("content_support_llm_fallback_reason", None)
    if isinstance(review, dict) and review.get("method") == REVIEW_METHOD_LLM_CONTENT_SUPPORT_VERIFIED:
        for key in ("content_support_review", "content_support_status", "content_support_method"):
            record.pop(key, None)
    return "verdict" if had_verdict else ("failure" if had_failure else None)


# ----------------------------------------------------------------------------------------------------------------------------------
# prediction (the four production calls)
# ----------------------------------------------------------------------------------------------------------------------------------


def content_support_request_items(samples: list[dict]) -> dict[str, list]:
    """run_id -> the production request items for the sampled FULL-chain claims of that run. Built by the production builder over the
    whole run (so each payload, report_context included, is byte-for-byte what a real run would send) and then restricted to the sample.
    Zero calls; also used to size the budget."""
    from comqutor_alpha.structure_engine.content_support_llm import (
        build_content_support_request_items,
    )

    out: dict[str, list] = {}
    by_run: dict[str, list[dict]] = {}
    for s in samples:
        if s["chain"] == "FULL":
            by_run.setdefault(s["run_id"], []).append(s)
    for run_id, group in by_run.items():
        wanted = {s["record"]["claim_id"] for s in group}
        out[run_id] = [i for i in build_content_support_request_items(group[0]["run_records"], group[0]["sources"]) if i.claim_id in wanted]
    return out


def _not_submitted_reason(record: dict, sources: list) -> tuple[str, dict | None]:
    from comqutor_alpha.source_provenance import verify_data_fact_or_derived_calculation

    if record.get("source_link_status") != "VALID":
        return f"source link {record.get('source_link_status')}: the production pass only checks VALID links", None
    mechanical = verify_data_fact_or_derived_calculation(record, sources)
    if mechanical is not None:
        return "resolved by the production deterministic data-fact / derived-calculation verifier (no LLM request needed)", mechanical
    return "no candidate source content for this claim", None


def _l1(samples: list[dict], gateway: Any, batch_size: int, audit: dict) -> dict[str, dict]:
    """The production content-support pass: the same request builder and the same batch processor
    ``apply_llm_content_support_verification`` runs, with the batch size frozen in the configuration. The pass's own per-request
    attempt log is kept in ``audit``: this task is not in the semantic-call ledger's task registry (llm_runtime.contracts.SEMANTIC_TASKS),
    so the ledger does not record it."""
    from comqutor_alpha.structure_engine import content_support_llm as cs

    out: dict[str, dict] = {}
    for s in samples:
        if s["chain"] == "FULL":
            s["saved_llm_content_result_removed"] = strip_saved_llm_content_verdict(s["record"])
    items_by_run = content_support_request_items(samples)
    results: dict[str, dict] = {}
    for run_id, items in items_by_run.items():
        stats = cs.ContentSupportRunStats()
        stats.llm_gateway_used = True
        stats.requested_count = len(items)
        for batch in cs.chunk_items(items, size=batch_size):
            cs._process_batch(batch, gateway, stats, results)
        audit.setdefault("content_support_verification", {})[run_id] = stats.to_dict()
    for s in samples:
        sid = s["sample_id"]
        if s["chain"] != "FULL":
            out[sid] = {"status": NOT_JUDGEABLE_NO_SOURCE_CONTENT}
            continue
        rec = results.get(s["record"]["claim_id"])
        base = {"saved_llm_content_result_removed": s.get("saved_llm_content_result_removed")}
        if rec is None:
            reason, mechanical = _not_submitted_reason(s["record"], s["sources"])
            if mechanical is not None:
                out[sid] = {**base, "status": DETERMINISTIC_VERIFIER_RESULT, "content_support_status": s["record"].get("content_support_status"),
                            "method": mechanical.get("method"), "reason": reason}
            else:
                out[sid] = {**base, "status": NOT_SUBMITTED, "reason": reason}
            continue
        s["record"] = rec  # L4 judges the record exactly as this pass left it
        if rec.get("content_support_llm_detail"):
            out[sid] = {**base, "status": LLM_RESULT, "content_support_status": rec.get("content_support_status"), "llm_detail": rec["content_support_llm_detail"]}
        else:
            out[sid] = {**base, "status": TASK_FAILED, "reason": rec.get("content_support_llm_fallback_reason")}
    return out


class _PayloadCapture:
    """Gateway stand-in that records the request the production mapper builds and refuses to answer (never calls anything)."""

    semantic_runtime = None

    def __init__(self) -> None:
        self.payloads: list[dict] = []

    def invoke_json_with_trace(self, task, payload, validator, **_kwargs):
        self.payloads.append(dict(payload))
        raise LookupError("payload capture only")

    def invoke_json(self, task, payload, validator, **_kwargs):
        self.payloads.append(dict(payload))
        raise LookupError("payload capture only")


def ledger_input_sha256(payload: dict) -> str:
    """The input hash the semantic-call ledger records for a request payload (session._allocate_trace)."""
    from comqutor_alpha.llm_runtime.cache import sha256_canonical_json
    from comqutor_alpha.llm_runtime.session import _sanitize_payload

    return sha256_canonical_json(_sanitize_payload(dict(payload))[0])


def saved_alpha_answers(samples: list[dict], config: FrozenConfig, runs_root: Path | None = None) -> dict[str, dict]:
    """sample_id -> the saved production Alpha answer bound to exactly this request, or why there is none. Zero calls; reads ledgers only.

    Bound means: the same task, prompt identity, input hash (the payload today's mapper builds for the claim), provider and model; the
    saved call succeeded on its FIRST attempt (so it is what a zero-retry request would have returned), finished with finish_reason stop
    and passed validation. The saved ledgers keep the validated response, not the raw text; the alpha_classifier response schema is
    exactly the validated object ({decision, selected_alpha_id}), so replaying it reproduces the accepted answer."""
    from comqutor_alpha.alpha_library.alpha_loader import load_alpha_taxonomy
    from comqutor_alpha.structure_engine.alpha_mapper import map_structured_records
    from comqutor_alpha.structure_engine.week2_llm import Week2LLMGateway

    runs_root = runs_root or (REPO / "outputs" / "runs")
    taxonomy = load_alpha_taxonomy()
    prompt_now = Week2LLMGateway.prompt_identity_sha256("alpha_classifier")
    by_sha: dict[str, list[tuple[str, dict]]] = {}
    for run_id in sorted({s["run_id"] for s in samples}):
        for ledger_run in ALPHA_REUSE_LEDGERS.get(run_id, (run_id,)):
            path = runs_root / ledger_run / "llm_semantic_calls.jsonl"
            if not path.is_file():
                continue
            with path.open(encoding="utf-8") as fh:
                for line in fh:
                    if '"alpha_classifier"' not in line:
                        continue
                    r = json.loads(line)
                    if r.get("task") == "alpha_classifier" and r.get("input_sha256"):
                        by_sha.setdefault(r["input_sha256"], []).append((ledger_run, r))
    out: dict[str, dict] = {}
    for s in samples:
        capture = _PayloadCapture()
        map_structured_records([s["record"]], taxonomy, llm_gateway=capture, concurrency=1)
        sha = ledger_input_sha256(capture.payloads[0])
        saved = by_sha.get(sha, [])

        def usable(entry: tuple[str, dict]) -> bool:
            r = entry[1]
            attempts = r.get("request_attempts") or []
            return (r.get("prompt_sha256") == prompt_now and r.get("provider") == config.provider and r.get("model") == config.model
                    and r.get("provider_status") == "success" and r.get("retry_count") == 0 and r.get("validation_status") == "accepted"
                    and isinstance(r.get("validated_output"), dict) and bool(attempts) and attempts[0].get("finish_reason") == "stop")

        good = [e for e in saved if usable(e)]
        if not good:
            reason = ("no saved call with this input" if not saved
                      else "saved call(s) not usable: " + ", ".join(sorted({str(r.get("provider_status")) for _run, r in saved})))
            out[s["sample_id"]] = {"status": "NOT_BOUND", "input_sha256": sha, "reason": reason}
            continue
        # the sample's own run first, otherwise the most recent
        own = [e for e in good if e[0] == s["run_id"]]
        ledger_run, r = own[0] if own else max(good, key=lambda e: str(e[1].get("completed_at") or ""))
        out[s["sample_id"]] = {
            "status": "BOUND", "input_sha256": sha, "ledger_run": ledger_run, "call_id": r.get("call_id"), "completed_at": r.get("completed_at"),
            "validated_output": r["validated_output"], "request_control": {k: v for k, v in (r.get("request_control") or {}).items() if k != "schema_version"},
            "distinct_saved_answers_for_this_input": len({json.dumps(e[1]["validated_output"], sort_keys=True) for e in good}),
        }
    return out


class _Replayed:
    def __init__(self, content: str, metadata: dict) -> None:
        self.content = content
        self.response_metadata = metadata


class _SavedAnswerModel:
    """Model behind the replay gateway: answers a request only with the saved production answer bound to exactly that input hash."""

    def __init__(self, bound: dict[str, dict]) -> None:
        self.answers = {b["input_sha256"]: b for b in bound.values() if b["status"] == "BOUND"}
        self.hits = 0
        self.misses = 0

    def invoke(self, prompt: str) -> _Replayed:
        from comqutor_alpha.structure_engine.week2_llm import _INPUT_JSON_SEPARATOR

        answer = self.answers.get(ledger_input_sha256(json.loads(prompt.split(_INPUT_JSON_SEPARATOR, 1)[1])))
        if answer is None:
            self.misses += 1
            raise LookupError("REPLAY_INPUT_NOT_BOUND")
        self.hits += 1
        return _Replayed(json.dumps(answer["validated_output"]), {"finish_reason": "stop", "replayed_call_id": answer["call_id"]})


def build_replay_gateway(bound: dict[str, dict], config: FrozenConfig, work_dir: Path) -> Any:
    """A production gateway (validation, gates and call ledger unchanged) whose model replays the bound saved answers; its own ledger is
    written in execution mode replay_fixture so it can never be mistaken for a live call."""
    from comqutor_alpha.llm_runtime.session import SemanticRuntimeSession
    from comqutor_alpha.structure_engine.week2_llm import Week2LLMGateway

    work_dir = Path(work_dir)
    work_dir.mkdir(parents=True, exist_ok=True)
    session = SemanticRuntimeSession(run_id="alpha-replay", output_directory=work_dir, execution_mode="replay_fixture", provider=config.provider, model=config.model)
    n = sum(1 for b in bound.values() if b["status"] == "BOUND")
    return Week2LLMGateway(_SavedAnswerModel(bound), run_id="alpha-replay", output_root=str(work_dir), timeout_seconds=config.timeout_seconds["alpha_classifier"],
                           max_retries=0, max_calls=max(n, 1), provider=config.provider, model_name=config.model, semantic_runtime=session)


def _l2_l3(samples: list[dict], alpha_gateway: Any, stance_gateway: Any, *, alpha_concurrency: int, stance_concurrency: int, audit: dict,
           reuse: dict[str, dict] | None = None, replay_gateway: Any = None) -> tuple[dict, dict, dict]:
    from comqutor_alpha.alpha_library.alpha_loader import load_alpha_taxonomy
    from comqutor_alpha.structure_engine.alpha_mapper import map_structured_records
    from comqutor_alpha.structure_engine.evidence_stance_llm import (
        STANCE_METHOD_LLM,
        apply_llm_stance_upgrade,
    )

    reuse = reuse or {}
    taxonomy = load_alpha_taxonomy()
    l2: dict[str, dict] = {}
    l3: dict[str, dict] = {}
    matches_by_sample: dict[str, dict] = {}
    by_run: dict[str, list[dict]] = {}
    for s in samples:
        by_run.setdefault(s["run_id"], []).append(s)
    for run_id, group in by_run.items():
        # one claim per request either way, so splitting the run's claims between the replay and the live gateway changes no request
        replayed = [s for s in group if replay_gateway is not None and reuse.get(s["sample_id"], {}).get("status") == "BOUND"]
        live = [s for s in group if s not in replayed]
        matches = []
        if replayed:
            matches += map_structured_records([s["record"] for s in replayed], taxonomy, llm_gateway=replay_gateway, concurrency=alpha_concurrency)
        if live:
            matches += map_structured_records([s["record"] for s in live], taxonomy, llm_gateway=alpha_gateway, concurrency=alpha_concurrency)
        order = {s["record"]["claim_id"]: i for i, s in enumerate(group)}
        matches.sort(key=lambda m: order[m["claim_id"]])
        stance_stats = apply_llm_stance_upgrade(matches, taxonomy, llm_gateway=stance_gateway, concurrency=stance_concurrency)
        audit.setdefault("evidence_stance_classifier", {})[run_id] = stance_stats.to_dict()
        by_claim = {m["claim_id"]: m for m in matches}
        for s in group:
            match = by_claim[s["record"]["claim_id"]]
            matches_by_sample[s["sample_id"]] = match
            classifier = match.get("classifier") or {}
            outcome = classify_outcome(str(classifier.get("status")), str(match.get("match_status")))
            l2[s["sample_id"]] = {
                "outcome_code": outcome,
                "predicted_alpha": match.get("matched_alpha") if outcome == "MATCHED" else None,
                "raw_selected_alpha": match.get("llm_selected_alpha_id"),
                "classifier_status": classifier.get("status"),
                "fallback_reason": match.get("alpha_match_fallback_reason"),
                "override": {"alpha_specific_invalidation": bool(match.get("alpha_specific_invalidation_override")),
                             "positive_requirement": bool(match.get("alpha_positive_requirement_override"))},
                "answer_source": (
                    {"kind": REUSED_SAVED_PRODUCTION_ANSWER, **{k: reuse[s["sample_id"]][k] for k in ("ledger_run", "call_id", "input_sha256", "request_control")}}
                    if s in replayed else
                    {"kind": NEW_REQUEST, "why_not_reused": reuse.get(s["sample_id"], {}).get("reason", "reuse disabled")}
                ),
            }
            alpha = match.get("matched_alpha") if outcome == "MATCHED" else None
            if not alpha:
                l3[s["sample_id"]] = {"status": NOT_APPLICABLE, "reason": f"no matched Alpha (L2 {outcome})"}
                continue
            cand = next((c for c in match.get("candidate_scores") or [] if isinstance(c, dict) and c.get("alpha_id") == alpha), {})
            if cand.get("stance_method") == STANCE_METHOD_LLM:
                l3[s["sample_id"]] = {"status": LLM_RESULT, "target_alpha": alpha, "stance": cand.get("evidence_stance"), "counter_alpha": cand.get("counter_alpha_id")}
            else:
                # production fell back to the deterministic baseline (or never stamped a method): recorded as a task failure,
                # the baseline's value kept only as a labeled diagnostic
                l3[s["sample_id"]] = {"status": TASK_FAILED, "target_alpha": alpha,
                                      "reason": cand.get("stance_fallback_reason") or "no LLM stance result",
                                      "deterministic_baseline_not_a_result": cand.get("evidence_stance")}
    return l2, l3, matches_by_sample


def _l4(samples: list[dict], l2: dict, l3: dict, matches: dict) -> dict[str, dict]:
    from comqutor_alpha.graph_engine.evidence_fact_index import select_supporting_alpha_claims
    from comqutor_alpha.source_provenance import compute_verified_support_eligibility

    out: dict[str, dict] = {}
    for s in samples:
        alpha = l2[s["sample_id"]]["predicted_alpha"]
        if not alpha:
            out[s["sample_id"]] = {"status": NOT_APPLICABLE, "reason": "no matched Alpha"}
            continue
        eligible, excluded, _warnings = select_supporting_alpha_claims([matches[s["sample_id"]]], alpha)
        selector = {"eligible": bool(eligible), "excluded_reason": (excluded[0]["reason"] if excluded else None)}
        verified = compute_verified_support_eligibility(s["record"], s["sources"])
        stance = l3[s["sample_id"]]
        activation_pool = selector["eligible"] and bool(verified.get("eligible"))
        if stance["status"] == LLM_RESULT:
            conflict_side = activation_pool and stance["stance"] == "supports_alpha"
        else:
            conflict_side = None  # undetermined: no LLM direction
        out[s["sample_id"]] = {
            "status": "DETERMINED",
            "alpha": alpha,
            "selector": selector,
            "verified_support": {"eligible": bool(verified.get("eligible")), "reason_code": verified.get("reason_code")},
            "activation_pool_eligible": activation_pool,
            "conflict_side_eligible": conflict_side,
            "failing_condition_kind": None if activation_pool else (
                "mechanical" if (not verified.get("eligible") and verified.get("reason_code") in MECHANICAL_GATE_REASONS and selector["eligible"]) else "semantic_or_review"
            ),
        }
    return out


def predict(samples: list[dict], *, gateways: dict[str, Any], config: FrozenConfig, audit: dict | None = None, work_dir: Path | None = None,
            runs_root: Path | None = None) -> list[dict]:
    """``gateways`` maps each of ``TASKS`` to its gateway (see ``build_task_gateways``). ``audit`` (optional) receives each pass's own
    statistics and per-request attempt log. ``work_dir`` receives the replay gateway's own ledger (required when saved Alpha answers are
    reused)."""
    audit = audit if audit is not None else {}
    reuse: dict[str, dict] = {}
    replay_gateway = None
    if config.reuse_saved_alpha_answers:
        reuse = saved_alpha_answers(samples, config, runs_root)  # before L1 touches the records; the Alpha payload ignores content fields
        if any(b["status"] == "BOUND" for b in reuse.values()):
            if work_dir is None:
                raise ValueError("work_dir is required to replay saved Alpha answers")
            replay_gateway = build_replay_gateway(reuse, config, Path(work_dir) / "alpha_replay")
    l1 = _l1(samples, gateways["content_support_verification"], config.content_support_batch_size, audit)
    l2, l3, matches = _l2_l3(samples, gateways["alpha_classifier"], gateways["evidence_stance_classifier"],
                             alpha_concurrency=config.alpha_classifier_concurrency, stance_concurrency=config.stance_concurrency, audit=audit,
                             reuse=reuse, replay_gateway=replay_gateway)
    if replay_gateway is not None:
        model = replay_gateway._model
        audit["alpha_reuse"] = {"bound": sum(1 for b in reuse.values() if b["status"] == "BOUND"), "replay_hits": model.hits, "replay_misses": model.misses,
                                "not_bound": {sid: b["reason"] for sid, b in reuse.items() if b["status"] != "BOUND"}}
    l4 = _l4(samples, l2, l3, matches)
    return [
        {"sample_id": s["sample_id"], "cell": s["cell"], "chain": s["chain"], "claim_text": s["record"].get("claim"),
         "L1": l1[s["sample_id"]], "L2": l2[s["sample_id"]], "L3": l3[s["sample_id"]], "L4": l4[s["sample_id"]]}
        for s in samples
    ]


# ----------------------------------------------------------------------------------------------------------------------------------
# scoring (zero calls) -- each link with its own denominator
# ----------------------------------------------------------------------------------------------------------------------------------


JUDGMENT_KEYS = ("R1_claim_fidelity", "R1_source_relation", "R2_alpha", "R3_direction", "R4_evidence_eligibility")


def _reference_items(review_form: dict) -> tuple[dict[str, dict], dict[str, int], list[dict]]:
    """Only judgments that name their reviewer count as reference judgments; the rest are counted, never scored. A value outside the
    form's own vocabulary is reported, never coerced."""
    vocabulary = review_form.get("judgment_vocabulary") or {}
    refs, skipped, invalid = {}, Counter(), []
    for item in review_form["items"]:
        j = item.get("judgments") or {}
        if not any(j.get(k) for k in JUDGMENT_KEYS):
            skipped["PENDING_REVIEW"] += 1
            continue
        if not j.get("reviewer_id"):
            skipped["REVIEWER_ID_MISSING"] += 1
            continue
        bad = {k: j[k] for k in JUDGMENT_KEYS if j.get(k) and k in vocabulary and j[k] not in vocabulary[k]}
        if bad:
            invalid.append({"sample_id": item["sample_id"], "values_outside_vocabulary": bad})
            skipped["VALUE_OUTSIDE_VOCABULARY"] += 1
            continue
        refs[item["sample_id"]] = {**j, "_claim_text": item.get("claim_text")}
    return refs, dict(skipped), invalid


def score(predictions: list[dict], review_form: dict) -> dict[str, Any]:
    refs, skipped, invalid = _reference_items(review_form)
    if not refs:
        return {"scoring_status": "BLOCKED_NO_REFERENCE_JUDGMENTS", "skipped": skipped, "invalid": invalid}
    preds = {p["sample_id"]: p for p in predictions}
    for sid, j in refs.items():
        if sid not in preds:
            raise SampleVersionMismatch(f"{sid}: judged on the form but has no prediction")
        if preds[sid].get("claim_text") != j["_claim_text"]:
            raise SampleVersionMismatch(f"{sid}: the form's claim text differs from the predicted claim")
    result: dict[str, Any] = {"scoring_status": "SCORED", "reference_items": len(refs), "skipped": skipped, "invalid": invalid,
                              "reviewers": dict(Counter(f"{j.get('reviewer_id')} ({j.get('reviewer_role') or 'role not stated'})" for j in refs.values())),
                              "attested_no_prior_view": dict(Counter(str(j.get("attests_no_prior_view_of_system_outputs")) for j in refs.values()))}

    # L2: John's Alpha metrics, through the existing scorer (failures and abstentions stay in the matrix)
    alpha_records = [{"sample_id": sid, "predicted_alpha": p["L2"]["predicted_alpha"], "outcome_code": p["L2"]["outcome_code"], "quota_category": p["cell"]}
                     for sid, p in preds.items() if sid in refs and refs[sid].get("R2_alpha")]
    alpha_items = [{"sample_id": sid, "your_judgment": refs[sid].get("R2_alpha")} for sid in refs if refs[sid].get("R2_alpha")]
    result["L2_alpha"] = score_alpha_against_labels(alpha_records, alpha_items)
    result["L2_alpha"]["task_failures"] = sum(1 for r in alpha_records if r["outcome_code"] not in ("MATCHED", "NONE", "SELECTED_BUT_NOT_MATCHED", "ABSTAINED_AMBIGUOUS"))

    # L1: agreement of the production content-support verdict with the reviewer's source relation (full-chain samples only)
    l1 = Counter()
    disagreements_l1 = []
    for sid, j in refs.items():
        p = preds[sid]
        if p["chain"] != "FULL":
            l1["not_judgeable_no_source_content"] += 1
            continue
        if j.get("R1_source_relation") in (None, "", REVIEWER_UNABLE):
            l1["reviewer_unable_or_blank"] += 1
            continue
        if p["L1"]["status"] not in (LLM_RESULT, DETERMINISTIC_VERIFIER_RESULT):
            l1[f"system_{p['L1']['status'].lower()}"] += 1
            continue
        l1["compared"] += 1
        l1[f"compared_{p['L1']['status'].lower()}"] += 1
        system = SYSTEM_TO_REVIEWER_RELATION.get(p["L1"]["content_support_status"], p["L1"]["content_support_status"])
        if system == j["R1_source_relation"]:
            l1["agree"] += 1
        else:
            disagreements_l1.append({"sample_id": sid, "system": system, "system_method": p["L1"]["status"], "reviewer": j["R1_source_relation"]})
    fidelity = Counter(j.get("R1_claim_fidelity") or "blank" for sid, j in refs.items() if preds[sid]["chain"] == "FULL")
    result["L1_source_to_claim"] = {"counts": dict(l1), "agreement_rate": round(l1["agree"] / l1["compared"], 6) if l1["compared"] else None,
                                    "disagreements": disagreements_l1, "reviewer_claim_fidelity_distribution": dict(fidelity)}

    # L3: direction, only where the system and the reviewer name the same Alpha and the system has an LLM direction
    l3 = Counter()
    disagreements_l3 = []
    for sid, j in refs.items():
        p = preds[sid]
        if p["L3"]["status"] == NOT_APPLICABLE:
            l3["not_applicable_no_system_alpha"] += 1
            continue
        if j.get("R2_alpha") != p["L3"].get("target_alpha"):
            l3["not_applicable_alpha_differs"] += 1
            continue
        if j.get("R3_direction") in (None, "", REVIEWER_UNABLE, NOT_APPLICABLE):
            l3["reviewer_unable_or_blank"] += 1
            continue
        if p["L3"]["status"] != LLM_RESULT:
            l3["system_task_failed"] += 1
            continue
        l3["compared"] += 1
        if p["L3"]["stance"] == j["R3_direction"]:
            l3["agree"] += 1
        else:
            disagreements_l3.append({"sample_id": sid, "system": p["L3"]["stance"], "reviewer": j["R3_direction"]})
    result["L3_direction"] = {"counts": dict(l3), "agreement_rate": round(l3["agree"] / l3["compared"], 6) if l3["compared"] else None, "disagreements": disagreements_l3}

    # L4: claim-level eligibility (never the run's Alpha level or conflict admission)
    l4 = Counter()
    disagreements_l4 = []
    for sid, j in refs.items():
        p = preds[sid]
        if p["L4"]["status"] != "DETERMINED":
            l4["not_applicable_no_system_alpha"] += 1
            continue
        if j.get("R2_alpha") != p["L4"]["alpha"]:
            l4["not_applicable_alpha_differs"] += 1
            continue
        if j.get("R4_evidence_eligibility") not in ELIGIBILITY_VOCAB:
            l4["reviewer_unable_or_blank"] += 1
            continue
        l4["compared"] += 1
        system = "QUALIFIES" if p["L4"]["activation_pool_eligible"] else "DOES_NOT_QUALIFY"
        if system == j["R4_evidence_eligibility"]:
            l4["agree"] += 1
        else:
            disagreements_l4.append({"sample_id": sid, "system": system, "reviewer": j["R4_evidence_eligibility"], "failing_condition_kind": p["L4"]["failing_condition_kind"],
                                     "selector": p["L4"]["selector"], "verified_support": p["L4"]["verified_support"]})
    result["L4_claim_eligibility"] = {"counts": dict(l4), "agreement_rate": round(l4["agree"] / l4["compared"], 6) if l4["compared"] else None, "disagreements": disagreements_l4}
    result["note"] = ("Each link has its own denominator; links are never merged into one score. Diagnostic sample (40 items, 4 per A001/A003/A102/A501 "
                      "cell): not a market-representative sample and not a re-measurement of the 80% target.")
    return result


# ----------------------------------------------------------------------------------------------------------------------------------
# CLI
# ----------------------------------------------------------------------------------------------------------------------------------


def _build_parser() -> argparse.ArgumentParser:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = ap.add_subparsers(dest="cmd", required=True)
    p = sub.add_parser("prepare")
    p.add_argument("--manifest", required=True)
    p.add_argument("--review-form", required=True)
    p.add_argument("--code-snapshot")
    p.add_argument("--out", required=True)
    s = sub.add_parser("score")
    s.add_argument("--predictions", required=True)
    s.add_argument("--review-form", required=True)
    s.add_argument("--out", required=True)
    z = sub.add_parser("sizing")
    z.add_argument("--manifest", required=True)
    z.add_argument("--out", required=True)
    r = sub.add_parser("predict")
    r.add_argument("--authorized-plan", required=True)
    r.add_argument("--plan-sha256", required=True)
    return ap


def sizing(samples: list[dict], config: FrozenConfig) -> dict[str, Any]:
    """Zero calls. The exact number of requests each task would send, or its upper bound where it depends on an earlier link's answer."""
    from comqutor_alpha.structure_engine.content_support_llm import (
        BATCH_SIZE as PRODUCTION_CONTENT_SUPPORT_BATCH_SIZE,
        chunk_items,
    )
    from comqutor_alpha.structure_engine.evidence_stance_llm import (
        BATCH_SIZE as STANCE_BATCH_SIZE,
        MAX_TARGET_ALPHAS_PER_CLAIM,
    )
    from comqutor_alpha.structure_engine.week2_llm import MAX_PROMPT_PAYLOAD_CHARS

    for s in samples:
        if s["chain"] == "FULL":
            strip_saved_llm_content_verdict(s["record"])
    items = content_support_request_items(samples)
    per_run = Counter(s["run_id"] for s in samples)
    full = [s for s in samples if s["chain"] == "FULL"]
    submitted = {i.claim_id for run_items in items.values() for i in run_items}
    not_submitted = Counter(_not_submitted_reason(s["record"], s["sources"])[0] for s in full if s["record"]["claim_id"] not in submitted)

    def batch_sizes(size: int) -> list[int]:
        # serialized exactly as Week2LLMGateway.invoke_json_with_trace serializes before its input-size check
        return [len(json.dumps({"items": [i.payload for i in b]}, ensure_ascii=False, default=str)) for v in items.values() for b in chunk_items(v, size=size)]

    def cap_check(size: int) -> dict:
        sizes = batch_sizes(size)
        return {"batch_size": size, "requests": len(sizes), "largest_payload_chars": max(sizes, default=0),
                "batches_over_input_cap_refused_before_sending": sum(1 for n in sizes if n > MAX_PROMPT_PAYLOAD_CHARS)}

    alpha_sizing: dict[str, Any] = {"exact": True, "path": config.alpha_classifier_path}
    stance_items_known: dict[str, int] = {}
    if config.reuse_saved_alpha_answers:
        import tempfile

        from comqutor_alpha.alpha_library.alpha_loader import load_alpha_taxonomy
        from comqutor_alpha.structure_engine.alpha_mapper import map_structured_records
        from comqutor_alpha.structure_engine.evidence_stance_llm import build_stance_request_items

        reuse = saved_alpha_answers(samples, config)
        bound = {sid: b for sid, b in reuse.items() if b["status"] == "BOUND"}
        if bound:
            taxonomy = load_alpha_taxonomy()
            with tempfile.TemporaryDirectory() as tmp:
                replay = build_replay_gateway(reuse, config, Path(tmp))
                for s in samples:
                    if s["sample_id"] in bound:
                        match = map_structured_records([s["record"]], taxonomy, llm_gateway=replay, concurrency=1)
                        stance_items_known[s["sample_id"]] = len(build_stance_request_items(match, taxonomy))
        alpha_sizing.update({
            "requests": len(samples) - len(bound),
            "reused_saved_production_answers": len(bound),
            "reused_from": dict(Counter(b["ledger_run"] for b in bound.values())),
            "reused_request_controls": dict(Counter(json.dumps(b["request_control"], sort_keys=True) for b in bound.values())),
            "new_request_reasons": dict(Counter(b["reason"] for b in reuse.values() if b["status"] != "BOUND")),
            "new_request_samples": sorted(sid for sid, b in reuse.items() if b["status"] != "BOUND"),
        })
    else:
        alpha_sizing["requests"] = len(samples)
    stance_items_bound: dict[str, int] = dict.fromkeys(per_run, 0)
    for s in samples:
        stance_items_bound[s["run_id"]] += stance_items_known.get(s["sample_id"], MAX_TARGET_ALPHAS_PER_CLAIM)

    return {
        "content_support_verification": {
            "exact": True,
            "items": sum(len(v) for v in items.values()),
            "requests": len(batch_sizes(config.content_support_batch_size)),
            "items_by_run": {run: len(v) for run, v in items.items()},
            "full_chain_samples_not_submitted_by_production_rules": dict(not_submitted),
            "input_cap_chars": MAX_PROMPT_PAYLOAD_CHARS,
            "frozen_batch_size": cap_check(config.content_support_batch_size),
            "production_default_batch_size": cap_check(PRODUCTION_CONTENT_SUPPORT_BATCH_SIZE),
        },
        "alpha_classifier": alpha_sizing,
        "evidence_stance_classifier": {
            "exact": False,
            "requests_upper_bound": sum(-(-stance_items_bound[run] // STANCE_BATCH_SIZE) for run in per_run),
            "items_upper_bound_by_run": stance_items_bound,
            "basis": (f"(claim, Alpha) items batched {STANCE_BATCH_SIZE} per request within each run (the production pass runs once per run); "
                      f"replayed Alpha answers give their exact item count (zero calls), every other sample is counted at the maximum "
                      f"{MAX_TARGET_ALPHAS_PER_CLAIM} targets; the real count depends on the new Alpha answers"),
            "items_from_replayed_answers": sum(stance_items_known.values()),
        },
    }


def main(argv: list[str] | None = None, *, gateway_factory: Callable[[FrozenConfig, str, Path], dict[str, Any]] | None = None) -> int:
    args = _build_parser().parse_args(argv)
    if args.cmd == "sizing":
        out = Path(args.out)
        if out.exists():
            print("refusing: output exists", out, file=sys.stderr)
            return 2
        out.write_text(json.dumps(sizing(load_samples(Path(args.manifest)), FrozenConfig()), ensure_ascii=False, indent=1) + "\n", encoding="utf-8")
        return 0
    if args.cmd == "prepare":
        out = Path(args.out)
        if out.exists():
            print("refusing: output exists", out, file=sys.stderr)
            return 2
        identity = freeze_identity(Path(args.manifest), Path(args.review_form), FrozenConfig(), Path(args.code_snapshot) if args.code_snapshot else None)
        out.write_text(json.dumps(identity, ensure_ascii=False, indent=1) + "\n", encoding="utf-8")
        return 0
    if args.cmd == "score":
        out = Path(args.out)
        if out.exists():
            print("refusing: output exists", out, file=sys.stderr)
            return 2
        predictions = [json.loads(line) for line in Path(args.predictions).read_text(encoding="utf-8").splitlines() if line.strip()]
        review_form = json.loads(Path(args.review_form).read_text(encoding="utf-8"))
        out.write_text(json.dumps(score(predictions, review_form), ensure_ascii=False, indent=1) + "\n", encoding="utf-8")
        return 0
    # predict: only with an authorized plan whose hash the caller states; round 25 never executes this branch
    refusal = _check_plan(Path(args.authorized_plan), args.plan_sha256)
    if isinstance(refusal, str):
        print("refusing:", refusal, file=sys.stderr)
        return 3
    plan = refusal
    config = FrozenConfig(**plan["config"])
    out_root = Path(plan["out_dir"])
    if (out_root / plan["execution_id"]).exists():
        print("refusing: execution directory exists", file=sys.stderr)
        return 2
    gateways = (gateway_factory or build_task_gateways)(config, plan["execution_id"], out_root)
    samples = load_samples(Path(plan["manifest"]))
    started = datetime.now(timezone.utc).isoformat()
    audit: dict = {}
    run_dir = out_root / plan["execution_id"]
    run_dir.mkdir(parents=True, exist_ok=True)
    predictions = predict(samples, gateways=gateways, config=config, audit=audit, work_dir=run_dir)
    (run_dir / "joint_predictions.jsonl").write_text("".join(json.dumps(p, ensure_ascii=False) + "\n" for p in predictions), encoding="utf-8")
    (run_dir / "task_audit.json").write_text(json.dumps(audit, ensure_ascii=False, indent=1, default=str) + "\n", encoding="utf-8")
    (run_dir / "run_summary.json").write_text(json.dumps({
        "execution_id": plan["execution_id"], "plan_sha256": args.plan_sha256, "started_at": started, "finished_at": datetime.now(timezone.utc).isoformat(),
        # reservations = requests sent or attempted (a timed-out request was sent and may still be billed)
        "requests_reserved": {task: getattr(gw, "_call_count", None) for task, gw in gateways.items()},
        "request_caps": config.max_requests,
        "outcomes": {link: dict(Counter((p[link].get("status") or p[link].get("outcome_code")) for p in predictions)) for link in ("L1", "L2", "L3", "L4")},
    }, ensure_ascii=False, indent=1) + "\n", encoding="utf-8")
    return 0


def _check_plan(plan_path: Path, stated_sha256: str) -> dict | str:
    """The plan must be the exact file the owner authorized, marked authorized by a named person, and must match the frozen sample and the
    current prompts; anything else refuses before a gateway is built."""
    from comqutor_alpha.structure_engine.week2_llm import Week2LLMGateway

    if not plan_path.is_file() or _sha256_file(plan_path) != stated_sha256:
        return "the plan file does not match the authorized sha256"
    plan = json.loads(plan_path.read_text(encoding="utf-8"))
    if plan.get("authorized") is not True or not str(plan.get("authorized_by") or "").strip():
        return "the plan is not marked authorized by a named person"
    for key in ("execution_id", "out_dir", "manifest", "manifest_sha256", "prompt_identity_sha256", "config"):
        if key not in plan:
            return f"the plan lacks {key}"
    if _sha256_file(Path(plan["manifest"])) != plan["manifest_sha256"]:
        return "the sample manifest changed since the plan was frozen"
    for task in TASKS:
        if Week2LLMGateway.prompt_identity_sha256(task) != plan["prompt_identity_sha256"].get(task):
            return f"the {task} prompt changed since the plan was frozen"
    return plan


if __name__ == "__main__":
    raise SystemExit(main())
