#!/usr/bin/env python3
"""T3 joint five-link driver for the frozen 40-item joint sample (round25_t3_minimal_prep_20261008/B1_samples_v4/).

John's T3 joint check, per sample:

    source content -> claim faithful? -> Alpha correct? -> direction toward that Alpha correct? -> eligible for the activation / conflict pool?

Every system answer comes from the production function that produces it in a real run -- never a re-implementation:

  L1 source -> claim      content_support_llm (the production request builder and batch processor of apply_llm_content_support_verification)
  L2 Alpha                alpha_mapper.map_structured_records                          (the production classifier call, single path)
  L3 direction            evidence_stance_llm.apply_llm_stance_upgrade                 (the production LLM stance pass, batches of 10)
  L4 claim eligibility    evidence_fact_index.select_supporting_alpha_claims           (activation / conflict supporting-evidence selector)
                          + source_provenance.compute_verified_support_eligibility     (the verified-support gate)

All 40 Alpha predictions are NEW requests of this execution. Saved production answers from earlier runs are exported only as a historical
comparison (``history``), never as this execution's prediction. A deterministic stance is never reported as a direction: when the LLM stance
fails, production falls back to the deterministic baseline and this driver records TASK_FAILED with the reason.

Real sending path (``predict``): one production Week2LLMGateway per task, each with its own client built by tradingagents' create_llm_client
(the factory production uses), whose httpx transport is   SendGuard -> AuditingTransport (production wire audit) -> network.
  * the guard admits a request only if its endpoint, body fields, model, prompt prefix and input hash match what was frozen (each frozen
    Alpha / content-support input at most once; stance items only for sampled claims); otherwise the request is NOT sent and the guard trips;
  * once tripped (field / input mismatch, request-audit save failure, response-audit save failure, HTTP 400/401/403/404/422/429) every later
    request of every task is refused before the network; nothing is retried or re-sent;
  * every request is written to checkpoint.jsonl (fsync'd) before it is forwarded and again when it returns or fails, so a request whose
    outcome is unknown stays visible as unknown -- it is never re-sent automatically (an existing execution directory is never reused).
Before anything is sent, ``predict`` re-derives every frozen input from the current code and data, checks the code identity, and runs the
whole pipeline once against a fixed-response transport (rehearsal, zero network); any mismatch refuses the execution.

Outcomes kept apart, never folded into each other: NONE (the model's own explicit none), SELECTED_BUT_NOT_MATCHED (a production gate
overrode the selection), NOT_APPLICABLE (the link has nothing to judge, e.g. no Alpha), TASK_FAILED (call / parse / timeout / truncation /
budget / guard), NOT_SUBMITTED (production does not send this claim, e.g. no VALID source link).

Modes (all zero-call except predict):
  freeze     frozen requests (input hashes, request shape, prompt prefixes), code identity and an UNSIGNED plan template
  sizing     request counts and upper bounds, input-size check
  history    the saved production Alpha answers bound to the same request -- historical comparison only
  preflight  every plan check except authorization, plus the full rehearsal
  predict    real calls ONLY with --authorized-plan <plan.json> whose sha256 matches --plan-sha256, marked authorized by a named person
  status     sent / not sent / success / failure / unknown from a checkpoint
  score      per-link statistics against reviewer judgments that carry a reviewer_id
"""
from __future__ import annotations

import argparse
import hashlib
import importlib.util
import json
import os
import shutil
import subprocess
import sys
import threading
from collections import Counter
from collections.abc import Callable
from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import httpx

HERE = Path(__file__).resolve().parent
REPO = next(p for p in HERE.parents if (p / "comqutor_alpha").is_dir())
sys.path.insert(0, str(REPO))

from comqutor_alpha.structure_engine.week2_llm_request_audit import (  # noqa: E402
    AuditingTransport,
    AuditingTransportError,
)

_DIAG_SPEC = importlib.util.spec_from_file_location("t3_diagnostic_evaluation_driver_for_joint", HERE / "t3_diagnostic_evaluation_driver.py")
assert _DIAG_SPEC is not None and _DIAG_SPEC.loader is not None
_diag = importlib.util.module_from_spec(_DIAG_SPEC)
sys.modules[_DIAG_SPEC.name] = _diag
_DIAG_SPEC.loader.exec_module(_diag)
classify_outcome = _diag.classify_outcome
score_alpha_against_labels = _diag.score_against_human_labels

SCHEMA_VERSION = "t3_joint_sample_driver.v2"
TASKS = ("content_support_verification", "alpha_classifier", "evidence_stance_classifier")
NOT_APPLICABLE = "NOT_APPLICABLE"
TASK_FAILED = "TASK_FAILED"
NOT_SUBMITTED = "NOT_SUBMITTED"
LLM_RESULT = "LLM_RESULT"
DETERMINISTIC_VERIFIER_RESULT = "DETERMINISTIC_VERIFIER_RESULT"  # production's own L1 answer for a pure data fact, labeled as such
NOT_REACHED_GUARD_TRIPPED = "NOT_REACHED_GUARD_TRIPPED"
REVIEWER_UNABLE = "UNABLE_TO_JUDGE"
ELIGIBILITY_VOCAB = ("QUALIFIES", "DOES_NOT_QUALIFY")
# production writes the LLM's INSUFFICIENT as content_support_status PENDING_REVIEW; the form offers INSUFFICIENT
SYSTEM_TO_REVIEWER_RELATION = {"PENDING_REVIEW": "INSUFFICIENT"}
# a failure of these verified-gate conditions is a mechanical fact (link / time / binding), not a semantic disagreement
MECHANICAL_GATE_REASONS = frozenset({"SOURCE_LINK_NOT_VALID", "DISCLOSURE_TIME_UNKNOWN", "SOURCE_NOT_RESOLVABLE", "CONTENT_VERSION_CHANGED_SINCE_REVIEW",
                                     "REVIEW_CLAIM_MISMATCH", "REVIEW_SOURCE_NOT_LINKED_TO_CLAIM", "AVAILABILITY_NOT_BEFORE_EVIDENCE_CUTOFF"})
# where a sample's saved Alpha answer may come from (historical comparison only): its own run, plus (c904d4cc) the classification-recovery
# run that re-ran the same frozen inputs with the current prompt
ALPHA_HISTORY_LEDGERS = {
    "c904d4cc-dc09-495c-aec5-b056979948e1": ("c904d4cc-dc09-495c-aec5-b056979948e1", "recovery-20261007T053635Z-26d6cd1a"),
}
DRIVER_FILES = (HERE / "t3_joint_sample_driver.py", HERE / "t3_diagnostic_evaluation_driver.py")


class SampleVersionMismatch(Exception):
    """The form's claim text for a judged sample differs from the claim the prediction was made for."""


class GuardRefused(AuditingTransportError):
    """Raised by the send guard instead of forwarding a request. A subclass of the production AuditingTransportError on purpose: the gateway
    already treats that error as 'never sent' (provider_status audit_unavailable, not a provider call) and refuses its later attempts. The
    checkpoint records the guard's actual reason."""


# ----------------------------------------------------------------------------------------------------------------------------------
# frozen configuration
# ----------------------------------------------------------------------------------------------------------------------------------


@dataclass
class FrozenConfig:
    """Everything a prediction run depends on besides code, prompt and data. The defaults are the round-25 part-B PROPOSAL
    (B_execution_proposal.md); an authorized plan states its own values, and those are what run. ``None`` for an output cap means the
    parameter is not sent (provider default), which is what the deployed .env does for every task today."""

    provider: str = "deepseek"
    model: str = "deepseek-v4-flash"
    base_url: str = "https://api.deepseek.com"  # tradingagents' registered DeepSeek endpoint
    api_key_env: str = "DEEPSEEK_API_KEY"
    # alpha 45 s = the deployed value; content support and stance 120 s = CANDIDATE values (the server gateway's own upper bound); no saved
    # measurement shows either task completing within 120 s
    timeout_seconds: dict[str, float] = field(default_factory=lambda: {"content_support_verification": 120.0, "alpha_classifier": 45.0, "evidence_stance_classifier": 120.0})
    max_tokens: dict[str, int | None] = field(default_factory=lambda: {"content_support_verification": None, "alpha_classifier": None, "evidence_stance_classifier": None})
    # hard caps per task (each task's own gateway call budget): content support exact, Alpha exact (40 new), stance = worst case of the new
    # Alpha answers (every sample matched with 3 retained targets, batched 10 per request within each run)
    max_requests: dict[str, int] = field(default_factory=lambda: {"content_support_verification": 17, "alpha_classifier": 40, "evidence_stance_classifier": 13})
    application_retries: int = 0
    sdk_retries: int = 0
    alpha_classifier_concurrency: int = 4  # week2_llm.DEFAULT_ALPHA_CLASSIFIER_CONCURRENCY
    stance_concurrency: int = 4  # week2_llm.DEFAULT_EVIDENCE_STANCE_CONCURRENCY
    # 1, not the production default 5: at 5, three of this sample's four batches exceed the gateway's 60,000-character input cap and are
    # refused before sending; one claim per request fits (largest 46,064)
    content_support_batch_size: int = 1
    alpha_classifier_path: str = "single (one claim per request; use_batched_classifier=False, the production default)"
    stance_batch_size: int = 10  # evidence_stance_llm.BATCH_SIZE, production constant (not configurable)
    cache: str = "none -- no semantic response cache is attached (NullLLMResponseCache)"
    unsent_parameters: str = "temperature, top_p, thinking, reasoning_effort, response_format: not sent -> provider defaults"
    stop_on_http_status: tuple[int, ...] = (400, 401, 403, 404, 422, 429)


def _sha256_file(path: Path) -> str:
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def _sha256_text(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


def _git(*args: str) -> str:
    return subprocess.run(["git", *args], cwd=REPO, capture_output=True, text=True, check=False).stdout


def code_identity() -> dict[str, Any]:
    """HEAD, the complete tracked diff, every untracked runtime source file (comqutor_alpha/, tradingagents/) and the two driver files."""
    untracked = sorted(p for p in _git("ls-files", "--others", "--exclude-standard", "--", "comqutor_alpha", "tradingagents").splitlines()
                       if p and "__pycache__" not in p)
    listing = "".join(f"{p}\0{_sha256_file(REPO / p)}\n" for p in untracked)
    return {
        "git_head": _git("rev-parse", "HEAD").strip(),
        "tracked_diff_sha256": _sha256_text(_git("diff", "HEAD", "--binary")),
        "untracked_runtime_source_files": len(untracked),
        "untracked_runtime_source_sha256": _sha256_text(listing),
        "driver_files_sha256": {p.name: _sha256_file(p) for p in DRIVER_FILES},
    }


# ----------------------------------------------------------------------------------------------------------------------------------
# inputs
# ----------------------------------------------------------------------------------------------------------------------------------


def load_samples(manifest_path: Path, runs_root: Path | None = None) -> list[dict[str, Any]]:
    """The frozen sample, each with its claim record and source registry read from the saved run (read-only). Every call reads the files
    again, so a rehearsal never shares mutable records with the real run."""
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
        samples.append({"sample_id": item["sample_id"], "cell": item["cell"], "run_id": run_id,
                        "material_status": item.get("material_status") or item.get("chain"),
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


def ledger_input_sha256(payload: dict) -> str:
    """The input hash the semantic-call ledger records for a request payload (session._allocate_trace)."""
    from comqutor_alpha.llm_runtime.cache import sha256_canonical_json
    from comqutor_alpha.llm_runtime.session import _sanitize_payload

    return sha256_canonical_json(_sanitize_payload(dict(payload))[0])


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


def alpha_request_payload(record: dict, taxonomy: dict) -> dict:
    from comqutor_alpha.structure_engine.alpha_mapper import map_structured_records

    capture = _PayloadCapture()
    map_structured_records([record], taxonomy, llm_gateway=capture, concurrency=1)
    return capture.payloads[0]


def content_support_request_items(samples: list[dict]) -> dict[str, list]:
    """run_id -> the production request items for the sampled claims of that run. Built by the production builder over the whole run (so
    each payload, report_context included, is byte-for-byte what a real run would send) and then restricted to the sample; the builder
    alone decides which claims are sent (VALID link, candidate content, not already resolved deterministically). Zero calls."""
    from comqutor_alpha.structure_engine.content_support_llm import (
        build_content_support_request_items,
    )

    out: dict[str, list] = {}
    by_run: dict[str, list[dict]] = {}
    for s in samples:
        by_run.setdefault(s["run_id"], []).append(s)
    for run_id, group in by_run.items():
        wanted = {s["record"]["claim_id"] for s in group}
        items = [i for i in build_content_support_request_items(group[0]["run_records"], group[0]["sources"]) if i.claim_id in wanted]
        if items:
            out[run_id] = items
    return out


def _not_submitted_reason(record: dict, sources: list) -> tuple[str, dict | None]:
    from comqutor_alpha.source_provenance import verify_data_fact_or_derived_calculation

    if record.get("source_link_status") != "VALID":
        return f"source link {record.get('source_link_status')}: the production pass only checks VALID links", None
    mechanical = verify_data_fact_or_derived_calculation(record, sources)
    if mechanical is not None:
        return "resolved by the production deterministic data-fact / derived-calculation verifier (no LLM request needed)", mechanical
    return "no candidate source content for this claim", None


# ----------------------------------------------------------------------------------------------------------------------------------
# frozen requests (zero calls)
# ----------------------------------------------------------------------------------------------------------------------------------


def prompt_prefixes() -> dict[str, str]:
    """The exact text every request of a task starts with (shared JSON-only preamble + task instruction + INPUT_JSON separator)."""
    from comqutor_alpha.structure_engine.week2_llm import Week2LLMGateway

    return {task: Week2LLMGateway._provider_prompt_prefix(task) for task in TASKS}


def build_frozen_requests(samples: list[dict], config: FrozenConfig) -> dict[str, Any]:
    """Everything the send guard enforces, derived from the current code and data. Deterministic: re-deriving it before sending and
    comparing with the frozen file is how predict detects drift."""
    from comqutor_alpha.alpha_library.alpha_loader import load_alpha_taxonomy
    from comqutor_alpha.structure_engine.content_support_llm import chunk_items
    from comqutor_alpha.structure_engine.week2_llm import _TASK_RUNTIME_METADATA, Week2LLMGateway

    taxonomy = load_alpha_taxonomy()
    alpha_inputs: dict[str, list[str]] = {}
    for s in samples:
        alpha_inputs.setdefault(ledger_input_sha256(alpha_request_payload(s["record"], taxonomy)), []).append(s["sample_id"])
    for s in samples:
        strip_saved_llm_content_verdict(s["record"])
    content_inputs: dict[str, list[str]] = {}
    for items in content_support_request_items(samples).values():
        for batch in chunk_items(items, size=config.content_support_batch_size):
            content_inputs.setdefault(ledger_input_sha256({"items": [i.payload for i in batch]}), []).extend(i.claim_id for i in batch)
    prefixes = prompt_prefixes()
    shapes = {}
    for task in TASKS:
        keys = ["messages", "model", "stream"] + (["max_tokens"] if config.max_tokens.get(task) is not None else [])
        shapes[task] = {"method": "POST", "endpoint": config.base_url.rstrip("/") + "/chat/completions", "body_keys": sorted(keys),
                        "model": config.model, "stream": False, "max_tokens": config.max_tokens.get(task)}
    return {
        "schema_version": "t3_frozen_requests.v1",
        "request_shape": shapes,
        "prompt_prefix": {t: {"sha256": _sha256_text(p), "length": len(p)} for t, p in prefixes.items()},
        "prompt_identity_sha256": {t: Week2LLMGateway.prompt_identity_sha256(t) for t in TASKS},
        "prompt_version": {t: _TASK_RUNTIME_METADATA[t]["prompt_version"] for t in TASKS},
        "inputs": {"alpha_classifier": {k: sorted(v) for k, v in sorted(alpha_inputs.items())},
                   "content_support_verification": {k: sorted(v) for k, v in sorted(content_inputs.items())}},
        "stance_allowed_claim_ids": sorted(s["record"]["claim_id"] for s in samples),
        "taxonomy_ids": sorted(taxonomy),
        "stance_max_items_per_request": config.stance_batch_size,
        "stop_on_http_status": list(config.stop_on_http_status),
        "request_caps": dict(config.max_requests),
    }


# ----------------------------------------------------------------------------------------------------------------------------------
# checkpoint and send guard
# ----------------------------------------------------------------------------------------------------------------------------------


class Checkpoint:
    """Append-only, fsync'd event log of every request decision. The last event of an attempt is its state; an attempt whose last event is
    'sending' is UNKNOWN (sent, outcome not recorded) and is never re-sent automatically."""

    def __init__(self, path: Path) -> None:
        self.path = Path(path)
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self._lock = threading.Lock()

    def write(self, event: str, **fields: Any) -> None:
        record = {"event": event, "at": datetime.now(timezone.utc).isoformat(), **fields}
        line = json.dumps(record, ensure_ascii=False, default=str) + "\n"
        with self._lock, self.path.open("a", encoding="utf-8") as fh:
            fh.write(line)
            fh.flush()
            os.fsync(fh.fileno())


def summarize_checkpoint(path: Path) -> dict[str, Any]:
    events = [json.loads(line) for line in Path(path).read_text(encoding="utf-8").splitlines() if line.strip()] if Path(path).exists() else []
    last: dict[str, dict] = {}
    for e in events:
        # only request events set an attempt's state (guard_tripped also names the attempt that tripped it); ids are numbered per task gateway
        if e.get("attempt_id") and e["event"] in ("sending", "response", "transport_error", "not_sent"):
            last[f"{e.get('task')}|{e['attempt_id']}"] = e
    state = Counter()
    by_task: dict[str, Counter] = {}
    unknown = []
    for attempt_id, e in last.items():
        if e["event"] == "not_sent":
            s = "not_sent"
        elif e["event"] == "response":
            s = "returned_ok" if 200 <= int(e.get("status_code") or 0) < 300 else "returned_error"
        elif e["event"] == "transport_error":
            s = "sent_transport_error"
        else:
            s = "unknown"
            unknown.append({"attempt_id": attempt_id, "task": e.get("task"), "claim_ids": e.get("claim_ids")})
        state[s] += 1
        by_task.setdefault(e.get("task") or "?", Counter())[s] += 1
    return {"attempts": len(last), "by_state": dict(state), "by_task": {t: dict(c) for t, c in by_task.items()},
            "sent": sum(n for s, n in state.items() if s != "not_sent"), "unknown_never_resent": unknown,
            "guard_trips": [e for e in events if e["event"] == "guard_tripped"]}


class SendGuard:
    """Shared by the three task transports. Admits a request only if it matches the frozen shape and inputs; trips (and from then on refuses
    everything) on any mismatch or on a stop-listed HTTP status."""

    def __init__(self, frozen: dict[str, Any], checkpoint: Checkpoint) -> None:
        from comqutor_alpha.structure_engine.week2_llm import _INPUT_JSON_SEPARATOR

        self.frozen = frozen
        self.checkpoint = checkpoint
        self.separator = _INPUT_JSON_SEPARATOR
        self._lock = threading.Lock()
        self.tripped: str | None = None
        self._sent: Counter = Counter()

    def trip(self, reason: str, **detail: Any) -> None:
        with self._lock:
            first = self.tripped is None
            if first:
                self.tripped = reason
        if first:
            self.checkpoint.write("guard_tripped", reason=reason, **detail)

    def admit(self, task: str, request: httpx.Request) -> tuple[str | None, dict]:
        info: dict[str, Any] = {}
        if self.tripped:
            return f"GUARD_ALREADY_TRIPPED ({self.tripped})", info
        shape = self.frozen["request_shape"][task]
        if request.method != shape["method"] or str(request.url) != shape["endpoint"]:
            return "REQUEST_ENDPOINT_MISMATCH", info
        try:
            body = json.loads(request.content)
        except ValueError:
            return "REQUEST_BODY_NOT_JSON", info
        if sorted(body) != shape["body_keys"] or body.get("model") != shape["model"] or body.get("stream") is not shape["stream"] \
                or body.get("max_tokens") != shape["max_tokens"]:
            return "REQUEST_FIELDS_MISMATCH", {"body_keys": sorted(body)}
        messages = body.get("messages")
        if not (isinstance(messages, list) and len(messages) == 1 and messages[0].get("role") == "user" and isinstance(messages[0].get("content"), str)):
            return "REQUEST_MESSAGES_MISMATCH", info
        content = messages[0]["content"]
        prefix = self.frozen["prompt_prefix"][task]
        if _sha256_text(content[: prefix["length"]]) != prefix["sha256"]:
            return "PROMPT_PREFIX_MISMATCH", info
        try:
            payload = json.loads(content[prefix["length"]:])
        except ValueError:
            return "REQUEST_INPUT_NOT_JSON", info
        input_sha = ledger_input_sha256(payload)
        info["input_sha256"] = input_sha
        if task in self.frozen["inputs"]:
            allowed = self.frozen["inputs"][task].get(input_sha)
            if allowed is None:
                return "INPUT_NOT_FROZEN", info
            with self._lock:
                if self._sent[(task, input_sha)] >= len(allowed):
                    return "INPUT_ALREADY_SENT", info
                self._sent[(task, input_sha)] += 1
        else:
            items = payload.get("items")
            allowed_claims = set(self.frozen["stance_allowed_claim_ids"])
            if not (isinstance(items, list) and 1 <= len(items) <= self.frozen["stance_max_items_per_request"]):
                return "STANCE_BATCH_SHAPE_MISMATCH", info
            pairs = [(i.get("claim_id"), i.get("target_alpha_id")) for i in items if isinstance(i, dict)]
            if len(pairs) != len(items) or any(c not in allowed_claims or a not in self.frozen["taxonomy_ids"] for c, a in pairs):
                return "STANCE_ITEM_NOT_ALLOWED", info
            with self._lock:
                if any(self._sent[("stance", p)] for p in pairs):
                    return "STANCE_ITEM_ALREADY_SENT", info
                for p in pairs:
                    self._sent[("stance", p)] += 1
        return None, info

    def after_response(self, task: str, status_code: int, attempt_id: str | None) -> None:
        if status_code in self.frozen["stop_on_http_status"]:
            self.trip(f"HTTP_{status_code}", task=task, attempt_id=attempt_id)


class GuardTransport(httpx.BaseTransport):
    """Outermost transport of a task client: guard decision and checkpoint around the production AuditingTransport."""

    def __init__(self, wrapped: httpx.BaseTransport, guard: SendGuard, task: str) -> None:
        self._wrapped = wrapped
        self._guard = guard
        self._task = task

    def handle_request(self, request: httpx.Request) -> httpx.Response:
        from comqutor_alpha.structure_engine.week2_llm import (
            Week2LLMGateway,
            _current_audit_attempt,
        )

        request.read()
        pending = _current_audit_attempt.get() or {}
        ident = {"task": self._task, "attempt_id": pending.get("attempt_id"), "semantic_call_id": pending.get("semantic_call_id"),
                 "claim_ids": pending.get("claim_ids") or Week2LLMGateway._extract_claim_ids(pending.get("payload") or {}),
                 # the guard verifies the request's prompt prefix against this version's frozen prefix before admitting it
                 "prompt_version": self._guard.frozen["prompt_version"][self._task]}
        refusal, info = (("TASK_ROUTING_MISMATCH", {}) if pending.get("task") not in (None, self._task) else self._guard.admit(self._task, request))
        if refusal:
            if not refusal.startswith("GUARD_ALREADY_TRIPPED"):
                self._guard.trip(refusal, task=self._task, attempt_id=ident["attempt_id"])
            self._guard.checkpoint.write("not_sent", reason=refusal, **ident, **info)
            raise GuardRefused(f"T3_SEND_GUARD_REFUSED: {refusal}")
        self._guard.checkpoint.write("sending", **ident, **info)
        try:
            response = self._wrapped.handle_request(request)
        except AuditingTransportError as exc:
            self._guard.checkpoint.write("not_sent", reason="AUDIT_REQUEST_SAVE_FAILED", error=str(exc)[:300], **ident)
            self._guard.trip("AUDIT_REQUEST_SAVE_FAILED", task=self._task, attempt_id=ident["attempt_id"])
            raise
        except Exception as exc:
            self._guard.checkpoint.write("transport_error", error_type=type(exc).__name__, error=str(exc)[:300], **ident)
            raise
        self._guard.checkpoint.write("response", status_code=response.status_code, **ident)
        self._guard.after_response(self._task, response.status_code, ident["attempt_id"])
        return response

    def close(self) -> None:
        close = getattr(self._wrapped, "close", None)
        if callable(close):
            close()


def build_task_gateways(config: FrozenConfig, execution_dir: Path, execution_id: str, guard: SendGuard, *,
                        base_transport_factory: Callable[[], httpx.BaseTransport] | None = None, api_key: str | None = None) -> dict[str, Any]:
    """One production Week2LLMGateway per task, each with its own real client from tradingagents' create_llm_client (timeout, output cap,
    SDK retries 0) whose transport is GuardTransport -> AuditingTransport -> network; application retries 0; the task's own request cap as
    its call budget; production request/response audit enabled. Each task writes under its own directory (no cross-task file races).
    ``base_transport_factory`` replaces only the network (rehearsal and tests); ``api_key`` is passed only for rehearsal -- the real run
    reads the key from the environment, as production does."""
    from comqutor_alpha.llm_runtime.session import SemanticRuntimeSession
    from comqutor_alpha.structure_engine.week2_llm import Week2LLMGateway, _AuditTransportGatewayRef
    from tradingagents.llm_clients import create_llm_client

    gateways = {}
    for task in TASKS:
        task_root = Path(execution_dir) / task
        (task_root / execution_id).mkdir(parents=True, exist_ok=True)
        ref = _AuditTransportGatewayRef()

        def on_response_save_failed(ref=ref, task=task) -> None:
            ref.on_response_save_failed()
            guard.trip("AUDIT_RESPONSE_SAVE_FAILED", task=task)

        audited = AuditingTransport((base_transport_factory or httpx.HTTPTransport)(), save_request=ref.save_request, save_response=ref.save_response,
                                    on_response_save_failed=on_response_save_failed)
        client_kwargs: dict[str, Any] = {"timeout": config.timeout_seconds[task], "max_retries": config.sdk_retries,
                                         "http_client": httpx.Client(transport=GuardTransport(audited, guard, task))}
        if config.max_tokens.get(task) is not None:
            client_kwargs["max_tokens"] = int(config.max_tokens[task])
        if api_key is not None:
            client_kwargs["api_key"] = api_key
        model = create_llm_client(provider=config.provider, model=config.model, base_url=config.base_url, **client_kwargs).get_llm()
        # content support is not in the semantic-call ledger's task registry, so no session is attached for it (the wire audit and the
        # checkpoint record it); alpha and stance record into their own ledger
        session = None if task == "content_support_verification" else SemanticRuntimeSession(
            run_id=execution_id, output_directory=task_root / execution_id, execution_mode="live", provider=config.provider, model=config.model)
        gateway = Week2LLMGateway(model, run_id=execution_id, output_root=str(task_root), timeout_seconds=config.timeout_seconds[task],
                                  max_retries=config.application_retries, max_calls=config.max_requests[task], provider=config.provider,
                                  model_name=config.model, semantic_runtime=session, execution_id=execution_id, enable_request_response_audit=True)
        ref.gateway = gateway
        gateways[task] = gateway
    return gateways


# ----------------------------------------------------------------------------------------------------------------------------------
# prediction (the four production calls)
# ----------------------------------------------------------------------------------------------------------------------------------


def _l1(samples: list[dict], gateway: Any, batch_size: int, audit: dict) -> dict[str, dict]:
    """The production content-support pass: the same request builder and the same batch processor
    ``apply_llm_content_support_verification`` runs, with the batch size frozen in the configuration."""
    from comqutor_alpha.structure_engine import content_support_llm as cs

    out: dict[str, dict] = {}
    for s in samples:
        s["saved_llm_content_result_removed"] = strip_saved_llm_content_verdict(s["record"])
    results: dict[str, dict] = {}
    for run_id, items in content_support_request_items(samples).items():
        stats = cs.ContentSupportRunStats()
        stats.llm_gateway_used = True
        stats.requested_count = len(items)
        for batch in cs.chunk_items(items, size=batch_size):
            cs._process_batch(batch, gateway, stats, results)
        audit.setdefault("content_support_verification", {})[run_id] = stats.to_dict()
    for s in samples:
        sid = s["sample_id"]
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


def _l2_l3(samples: list[dict], alpha_gateway: Any, stance_gateway: Any, *, alpha_concurrency: int, stance_concurrency: int, audit: dict,
           stop: Callable[[], bool] = lambda: False) -> tuple[dict, dict, dict]:
    from comqutor_alpha.alpha_library.alpha_loader import load_alpha_taxonomy
    from comqutor_alpha.structure_engine.alpha_mapper import map_structured_records
    from comqutor_alpha.structure_engine.evidence_stance_llm import (
        STANCE_METHOD_LLM,
        apply_llm_stance_upgrade,
    )

    taxonomy = load_alpha_taxonomy()
    l2: dict[str, dict] = {}
    l3: dict[str, dict] = {}
    matches_by_sample: dict[str, dict] = {}
    by_run: dict[str, list[dict]] = {}
    for s in samples:
        by_run.setdefault(s["run_id"], []).append(s)
    matches_by_run = {run_id: map_structured_records([s["record"] for s in group], taxonomy, llm_gateway=alpha_gateway, concurrency=alpha_concurrency)
                      for run_id, group in by_run.items()}
    for run_id, group in by_run.items():
        matches = matches_by_run[run_id]
        if stop():
            audit.setdefault("evidence_stance_classifier", {})[run_id] = {"not_run": NOT_REACHED_GUARD_TRIPPED}
        else:
            audit.setdefault("evidence_stance_classifier", {})[run_id] = apply_llm_stance_upgrade(matches, taxonomy, llm_gateway=stance_gateway,
                                                                                                  concurrency=stance_concurrency).to_dict()
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
                "answer_source": "NEW_REQUEST_THIS_EXECUTION",
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
                                      "reason": cand.get("stance_fallback_reason") or (NOT_REACHED_GUARD_TRIPPED if stop() else "no LLM stance result"),
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
        conflict_side = (activation_pool and stance["stance"] == "supports_alpha") if stance["status"] == LLM_RESULT else None  # None: no LLM direction
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


def predict(samples: list[dict], *, gateways: dict[str, Any], config: FrozenConfig, audit: dict | None = None, guard: SendGuard | None = None,
            progress_dir: Path | None = None) -> list[dict]:
    """``gateways`` maps each of ``TASKS`` to its gateway (see ``build_task_gateways``). ``audit`` receives each pass's own statistics and
    per-request attempt log. With a ``guard``, a trip stops the later links from being attempted at all. ``progress_dir`` receives each
    link's result as soon as it exists."""
    audit = audit if audit is not None else {}

    def stop() -> bool:
        return guard is not None and guard.tripped is not None

    def save(name: str, data: Any) -> None:
        if progress_dir is not None:
            (Path(progress_dir) / name).write_text(json.dumps(data, ensure_ascii=False, indent=1, default=str) + "\n", encoding="utf-8")

    l1 = _l1(samples, gateways["content_support_verification"], config.content_support_batch_size, audit)
    save("progress_L1.json", l1)
    if stop():
        # the guard tripped during L1: no Alpha or direction request is attempted at all
        l2 = {s["sample_id"]: {"outcome_code": NOT_REACHED_GUARD_TRIPPED, "predicted_alpha": None, "raw_selected_alpha": None,
                               "answer_source": "NOT_SENT"} for s in samples}
        l3 = {s["sample_id"]: {"status": NOT_APPLICABLE, "reason": NOT_REACHED_GUARD_TRIPPED} for s in samples}
        matches: dict[str, dict] = {}
    else:
        l2, l3, matches = _l2_l3(samples, gateways["alpha_classifier"], gateways["evidence_stance_classifier"],
                                 alpha_concurrency=config.alpha_classifier_concurrency, stance_concurrency=config.stance_concurrency, audit=audit, stop=stop)
    save("progress_L2_L3.json", {"L2": l2, "L3": l3})
    l4 = _l4(samples, l2, l3, matches)
    return [
        {"sample_id": s["sample_id"], "cell": s["cell"], "material_status": s.get("material_status"), "claim_text": s["record"].get("claim"),
         "L1": l1[s["sample_id"]], "L2": l2[s["sample_id"]], "L3": l3[s["sample_id"]], "L4": l4[s["sample_id"]]}
        for s in samples
    ]


# ----------------------------------------------------------------------------------------------------------------------------------
# rehearsal (zero network): the whole pipeline against fixed responses
# ----------------------------------------------------------------------------------------------------------------------------------


def rehearsal_response(request: httpx.Request, prefixes: dict[str, str]) -> httpx.Response:
    """A fixed, well-formed answer for any frozen request. Only the plumbing is rehearsed; the answers carry no meaning (every Alpha request
    selects A304 so that the stance step is exercised at its largest)."""
    body = json.loads(request.content)
    content = body["messages"][0]["content"]
    task = next(t for t, p in prefixes.items() if content.startswith(p))
    payload = json.loads(content[len(prefixes[task]):])
    if task == "alpha_classifier":
        answer: Any = {"decision": "select", "selected_alpha_id": "A304"}
    elif task == "evidence_stance_classifier":
        answer = {"items": [{"claim_id": i["claim_id"], "target_alpha_id": i["target_alpha_id"], "stance": "supports_alpha", "counter_alpha_id": None}
                            for i in payload["items"]]}
    else:
        items = []
        for item in payload["items"]:
            candidate = item["allowed_candidates"][0]
            items.append({"claim_id": item["claim_id"], "core_proposition": "rehearsal", "status": "SUPPORTS", "support_basis": "DIRECT_FACT",
                          "used_source_id": candidate["source_id"], "used_location": "excerpt",
                          "supporting_quote_or_data": (candidate.get("excerpt") or "")[:30], "inference_facts": [], "inference_assumptions": [],
                          "rationale": "rehearsal", "supported_proposition": item["proposition"], "unsupported_remainder": "",
                          "unsupported_remainder_materiality": "NONE"})
        answer = {"items": items}
    return httpx.Response(200, json={"id": "rehearsal", "object": "chat.completion", "created": 0, "model": body["model"],
                                     "choices": [{"index": 0, "message": {"role": "assistant", "content": json.dumps(answer)}, "finish_reason": "stop"}],
                                     "usage": {"prompt_tokens": 1, "completion_tokens": 1, "total_tokens": 2}})


def rehearse(manifest: Path, config: FrozenConfig, frozen: dict[str, Any], work_dir: Path, *, execution_id: str = "rehearsal") -> dict[str, Any]:
    """Runs predict end to end through the real client construction, guard, checkpoint and production audit, with only the network replaced
    by fixed responses. Passes only if no request was refused, every frozen Alpha / content input was sent exactly once, and every sent
    request left a request record, a response record and (alpha / stance) a semantic-ledger record."""
    work_dir = Path(work_dir)
    work_dir.mkdir(parents=True, exist_ok=True)
    prefixes = prompt_prefixes()
    checkpoint = Checkpoint(work_dir / "checkpoint.jsonl")
    guard = SendGuard(frozen, checkpoint)
    gateways = build_task_gateways(config, work_dir, execution_id, guard,
                                   base_transport_factory=lambda: httpx.MockTransport(lambda r: rehearsal_response(r, prefixes)), api_key="rehearsal-not-a-key")
    predictions = predict(load_samples(manifest), gateways=gateways, config=config, guard=guard)
    summary = summarize_checkpoint(checkpoint.path)
    problems = []
    if guard.tripped:
        problems.append(f"guard tripped: {guard.tripped}")
    for task in ("alpha_classifier", "content_support_verification"):
        expected = sum(len(v) for v in frozen["inputs"][task].values())
        if guard._sent and sum(n for (t, _), n in guard._sent.items() if t == task) != expected:
            problems.append(f"{task}: frozen inputs not each sent exactly once")
    audit_counts = {}
    for task in TASKS:
        base = work_dir / task / execution_id / "error_logs"
        req = [json.loads(line) for line in (base / "week2_llm_provider_request_audit.jsonl").read_text(encoding="utf-8").splitlines()] if (base / "week2_llm_provider_request_audit.jsonl").exists() else []
        resp = [json.loads(line) for line in (base / "week2_llm_provider_response_audit.jsonl").read_text(encoding="utf-8").splitlines()] if (base / "week2_llm_provider_response_audit.jsonl").exists() else []
        ledger = work_dir / task / execution_id / "llm_semantic_calls.jsonl"
        led = [json.loads(line) for line in ledger.read_text(encoding="utf-8").splitlines()] if ledger.exists() else []
        sent = summary["by_task"].get(task, {}).get("returned_ok", 0)
        audit_counts[task] = {"sent": sent, "request_audit": len(req), "response_audit": len(resp), "semantic_ledger": len(led),
                              "request_records_complete": all(r.get("task") == task and r.get("attempt_id") and r.get("claim_ids") and r.get("body") for r in req),
                              "response_records_complete": all(r.get("status_code") == 200 and '"usage"' in r.get("body", "") for r in resp)}
        if len(req) != sent or len(resp) != sent:
            problems.append(f"{task}: audit records ({len(req)} request / {len(resp)} response) differ from requests sent ({sent})")
        if task != "content_support_verification" and len(led) != sent:
            problems.append(f"{task}: semantic ledger records ({len(led)}) differ from requests sent ({sent})")
        if not (audit_counts[task]["request_records_complete"] and audit_counts[task]["response_records_complete"]):
            problems.append(f"{task}: an audit record lacks task / attempt / claim / body / status / usage")
        if sent > config.max_requests[task]:
            problems.append(f"{task}: sent {sent} > cap {config.max_requests[task]}")
    return {"passed": not problems, "problems": problems, "checkpoint": summary, "audit": audit_counts,
            "requests_sent": {t: audit_counts[t]["sent"] for t in TASKS}, "predictions": len(predictions),
            "note": "fixed responses: shows the sending path, guard, audit and checkpoint work; says nothing about answer quality"}


# ----------------------------------------------------------------------------------------------------------------------------------
# historical comparison (zero calls): saved production Alpha answers bound to the same request
# ----------------------------------------------------------------------------------------------------------------------------------


def historical_alpha_answers(samples: list[dict], config: FrozenConfig, runs_root: Path | None = None) -> dict[str, dict]:
    """sample_id -> the saved production Alpha answer bound to exactly this request (same prompt identity, input hash, provider and model;
    first-attempt success, finish_reason stop, validation accepted), or why there is none. HISTORICAL COMPARISON ONLY: produced before
    this execution was frozen, under each run's own configuration (whose code identity was not snapshotted)."""
    from comqutor_alpha.alpha_library.alpha_loader import load_alpha_taxonomy
    from comqutor_alpha.structure_engine.week2_llm import Week2LLMGateway

    runs_root = runs_root or (REPO / "outputs" / "runs")
    taxonomy = load_alpha_taxonomy()
    prompt_now = Week2LLMGateway.prompt_identity_sha256("alpha_classifier")
    by_sha: dict[str, list[tuple[str, dict]]] = {}
    for run_id in sorted({s["run_id"] for s in samples}):
        for ledger_run in ALPHA_HISTORY_LEDGERS.get(run_id, (run_id,)):
            path = runs_root / ledger_run / "llm_semantic_calls.jsonl"
            if not path.is_file():
                continue
            with path.open(encoding="utf-8") as fh:
                for line in fh:
                    if '"alpha_classifier"' in line:
                        r = json.loads(line)
                        if r.get("task") == "alpha_classifier" and r.get("input_sha256"):
                            by_sha.setdefault(r["input_sha256"], []).append((ledger_run, r))
    out: dict[str, dict] = {}
    for s in samples:
        sha = ledger_input_sha256(alpha_request_payload(s["record"], taxonomy))
        saved = by_sha.get(sha, [])
        good = [(run, r) for run, r in saved
                if r.get("prompt_sha256") == prompt_now and r.get("provider") == config.provider and r.get("model") == config.model
                and r.get("provider_status") == "success" and r.get("retry_count") == 0 and r.get("validation_status") == "accepted"
                and isinstance(r.get("validated_output"), dict) and (r.get("request_attempts") or [{}])[0].get("finish_reason") == "stop"]
        if not good:
            out[s["sample_id"]] = {"status": "NO_HISTORICAL_ANSWER", "input_sha256": sha,
                                   "reason": "no saved call with this input" if not saved else "saved call(s) not usable: " + ", ".join(sorted({str(r.get("provider_status")) for _x, r in saved}))}
            continue
        own = [e for e in good if e[0] == s["run_id"]]
        run, r = own[0] if own else max(good, key=lambda e: str(e[1].get("completed_at") or ""))
        out[s["sample_id"]] = {"status": "HISTORICAL_ANSWER", "input_sha256": sha, "ledger_run": run, "call_id": r.get("call_id"),
                               "completed_at": r.get("completed_at"), "validated_output": r["validated_output"],
                               "request_control": {k: v for k, v in (r.get("request_control") or {}).items() if k != "schema_version"}}
    return out


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


def score(predictions: list[dict], review_form: dict, history: dict[str, dict] | None = None) -> dict[str, Any]:
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
    if history:
        both = [sid for sid, h in history.items() if h.get("status") == "HISTORICAL_ANSWER" and sid in preds]
        same = sum(1 for sid in both if (preds[sid]["L2"]["raw_selected_alpha"] or None) == (history[sid]["validated_output"].get("selected_alpha_id") or None))
        result["L2_historical_comparison"] = {"samples_with_historical_answer": len(both), "same_raw_selection": same,
                                              "note": "consistency with earlier production answers; not accuracy, not part of the evaluation"}

    # L1: the production content-support verdict vs the reviewer's source relation; samples production never checked are counted by reason
    l1 = Counter()
    disagreements_l1 = []
    not_checked = Counter()
    for sid, j in refs.items():
        p = preds[sid]
        relation = j.get("R1_source_relation")
        if p["L1"]["status"] not in (LLM_RESULT, DETERMINISTIC_VERIFIER_RESULT):
            not_checked[f"{p['L1']['status']} | reviewer {relation or 'blank'}"] += 1
            continue
        if relation in (None, "", REVIEWER_UNABLE):
            l1["reviewer_unable_or_blank"] += 1
            continue
        l1["compared"] += 1
        l1[f"compared_{p['L1']['status'].lower()}"] += 1
        system = SYSTEM_TO_REVIEWER_RELATION.get(p["L1"]["content_support_status"], p["L1"]["content_support_status"])
        if system == relation:
            l1["agree"] += 1
        else:
            disagreements_l1.append({"sample_id": sid, "system": system, "system_method": p["L1"]["status"], "reviewer": relation})
    result["L1_source_to_claim"] = {
        "counts": dict(l1), "agreement_rate": round(l1["agree"] / l1["compared"], 6) if l1["compared"] else None, "disagreements": disagreements_l1,
        "not_checked_by_production_vs_reviewer_relation": dict(not_checked),
        "reviewer_claim_fidelity_by_material_status": {
            status: dict(Counter(j.get("R1_claim_fidelity") or "blank" for sid, j in refs.items() if preds[sid].get("material_status") == status))
            for status in sorted({preds[sid].get("material_status") or "?" for sid in refs})}}

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
# sizing (zero calls)
# ----------------------------------------------------------------------------------------------------------------------------------


def sizing(samples: list[dict], config: FrozenConfig) -> dict[str, Any]:
    """Zero calls. Exact counts for content support and Alpha; the stance worst case for ANY answers the 40 new Alpha requests may give."""
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
        strip_saved_llm_content_verdict(s["record"])
    items = content_support_request_items(samples)
    per_run = Counter(s["run_id"] for s in samples)
    submitted = {i.claim_id for run_items in items.values() for i in run_items}
    not_submitted = Counter(_not_submitted_reason(s["record"], s["sources"])[0] for s in samples if s["record"]["claim_id"] not in submitted)

    def batch_sizes(size: int) -> list[int]:
        # serialized exactly as Week2LLMGateway.invoke_json_with_trace serializes before its input-size check
        return [len(json.dumps({"items": [i.payload for i in b]}, ensure_ascii=False, default=str)) for v in items.values() for b in chunk_items(v, size=size)]

    def cap_check(size: int) -> dict:
        sizes = batch_sizes(size)
        return {"batch_size": size, "requests": len(sizes), "largest_payload_chars": max(sizes, default=0),
                "batches_over_input_cap_refused_before_sending": sum(1 for n in sizes if n > MAX_PROMPT_PAYLOAD_CHARS)}

    stance_by_run = {run: -(-(n * MAX_TARGET_ALPHAS_PER_CLAIM) // STANCE_BATCH_SIZE) for run, n in per_run.items()}
    return {
        "content_support_verification": {
            "exact": True, "items": sum(len(v) for v in items.values()), "requests": len(batch_sizes(config.content_support_batch_size)),
            "items_by_run": {run: len(v) for run, v in items.items()}, "samples_not_submitted_by_production_rules": dict(not_submitted),
            "reusable_saved_results": 0, "input_cap_chars": MAX_PROMPT_PAYLOAD_CHARS,
            "frozen_batch_size": cap_check(config.content_support_batch_size), "production_default_batch_size": cap_check(PRODUCTION_CONTENT_SUPPORT_BATCH_SIZE),
        },
        "alpha_classifier": {"exact": True, "requests": len(samples), "path": config.alpha_classifier_path,
                             "note": "all 40 are new requests of this execution; saved production answers are a historical comparison only"},
        "evidence_stance_classifier": {
            "exact": False, "requests_upper_bound": sum(stance_by_run.values()), "upper_bound_by_run": stance_by_run,
            "basis": (f"any of the 40 new Alpha answers may match; worst case every sample matched with {MAX_TARGET_ALPHAS_PER_CLAIM} retained targets, "
                      f"batched {STANCE_BATCH_SIZE} per request within each run (the production pass runs once per run)"),
        },
    }


# ----------------------------------------------------------------------------------------------------------------------------------
# plan checks
# ----------------------------------------------------------------------------------------------------------------------------------


PLAN_KEYS = ("execution_id", "out_dir", "manifest", "manifest_sha256", "review_form", "review_form_sha256", "frozen_requests", "frozen_requests_sha256",
             "code_identity", "prompt_identity_sha256", "config")


def _check_plan(plan_path: Path, stated_sha256: str | None, *, require_authorized: bool) -> dict | str:
    """The plan must be the exact file the owner authorized, marked authorized by a named person, and must match the frozen sample, form,
    requests, prompts and code; anything else refuses before a gateway is built."""
    from comqutor_alpha.structure_engine.week2_llm import Week2LLMGateway

    if not plan_path.is_file():
        return "the plan file does not exist"
    if require_authorized and _sha256_file(plan_path) != stated_sha256:
        return "the plan file does not match the authorized sha256"
    plan = json.loads(plan_path.read_text(encoding="utf-8"))
    if require_authorized and (plan.get("authorized") is not True or not str(plan.get("authorized_by") or "").strip()):
        return "the plan is not marked authorized by a named person"
    for key in PLAN_KEYS:
        if key not in plan:
            return f"the plan lacks {key}"
    for key in ("manifest", "review_form", "frozen_requests"):
        path = REPO / plan[key]
        if not path.is_file() or _sha256_file(path) != plan[f"{key}_sha256"]:
            return f"the {key} changed since the plan was frozen"
    for task in TASKS:
        if Week2LLMGateway.prompt_identity_sha256(task) != plan["prompt_identity_sha256"].get(task):
            return f"the {task} prompt changed since the plan was frozen"
    if code_identity() != plan["code_identity"]:
        return "the code changed since the plan was frozen (HEAD, tracked diff, untracked runtime source or driver files)"
    try:
        FrozenConfig(**{**plan["config"], "stop_on_http_status": tuple(plan["config"].get("stop_on_http_status", ()))})
    except TypeError as exc:
        return f"the plan's config is not valid: {exc}"
    return plan


def _config_from_plan(plan: dict) -> FrozenConfig:
    return FrozenConfig(**{**plan["config"], "stop_on_http_status": tuple(plan["config"]["stop_on_http_status"])})


def _frozen_matches(plan: dict, samples: list[dict], config: FrozenConfig) -> str | None:
    fresh = build_frozen_requests(samples, config)
    frozen = json.loads((REPO / plan["frozen_requests"]).read_text(encoding="utf-8"))
    return None if fresh == frozen else "the requests derived from the current code and data differ from the frozen requests"


def _rel(path: Path) -> str:
    """Repository-relative when inside the repository (plans travel with it), absolute otherwise; readers join with REPO either way."""
    path = Path(path).resolve()
    return str(path.relative_to(REPO)) if path.is_relative_to(REPO) else str(path)


def _write_json(path: Path, data: Any) -> None:
    Path(path).parent.mkdir(parents=True, exist_ok=True)
    Path(path).write_text(json.dumps(data, ensure_ascii=False, indent=1, default=str) + "\n", encoding="utf-8")


# ----------------------------------------------------------------------------------------------------------------------------------
# material collection (real requests ONLY with an authorized plan whose collection section is authorized)
# ----------------------------------------------------------------------------------------------------------------------------------


# the exact market questions the runs' news agent reported (034a0a60 and 1bad76a7 news reports), and the samples that cite them
COLLECTION_TARGETS = {
    "US recession by end of 2026": ["t3v3-037", "t3v3-039", "t3v3-040"],
    "UK recession in 2026": ["t3v3-037"],
    "Japan recession in 2026": ["t3v3-037", "t3v3-038"],
}
GAMMA_SEARCH_URL = "https://gamma-api.polymarket.com/public-search"  # the endpoint tradingagents/dataflows/polymarket.py itself uses
CLOB_HISTORY_URL = "https://clob.polymarket.com/prices-history"
COLLECTION_WINDOW = ("2026-09-24", "2026-10-07")  # UTC dates, end exclusive: covers 034a0a60 (10-01/02) and 1bad76a7 (10-05) with a week before
COLLECTION_REQUEST_CAP = 4


class _CollectionStop(Exception):
    pass


def _question_key(text: Any) -> str:
    return " ".join(str(text or "").strip().rstrip("?").lower().split())


def _json_list(value: Any) -> list:
    if isinstance(value, list):
        return value
    try:
        parsed = json.loads(value)
    except (TypeError, ValueError):
        return []
    return parsed if isinstance(parsed, list) else []


def collect_materials(out_dir: Path, *, transport: httpx.BaseTransport | None = None, cap: int = COLLECTION_REQUEST_CAP) -> dict[str, Any]:
    """One Gamma search (the agents' own endpoint) to identify the three markets, then one daily price-history request per market. Every
    response is saved verbatim with its URL, status, retrieval time and sha256. Stops at the first transport error, non-200 status or
    unexpected shape; never searches again and never exceeds ``cap``. The result is material collected FOR THIS VERIFICATION -- not material
    the original runs saved."""
    out_dir = Path(out_dir)
    out_dir.mkdir(parents=True, exist_ok=False)
    record: dict[str, Any] = {"requests": [], "markets": {}, "stopped": None, "window_utc": list(COLLECTION_WINDOW), "request_cap": cap}
    client = httpx.Client(transport=transport or httpx.HTTPTransport(), timeout=30.0)

    def get(name: str, url: str, params: dict) -> Any:
        if len(record["requests"]) >= cap:
            raise _CollectionStop("REQUEST_CAP_REACHED")
        entry: dict[str, Any] = {"name": name, "url": url, "params": params, "retrieved_at": datetime.now(timezone.utc).isoformat()}
        record["requests"].append(entry)
        try:
            response = client.get(url, params=params)
        except httpx.HTTPError as exc:
            entry["error"] = type(exc).__name__
            raise _CollectionStop("TRANSPORT_ERROR") from exc
        body = response.content
        path = out_dir / f"{len(record['requests']):02d}_{name}.json"
        path.write_bytes(body)
        entry.update({"final_url": str(response.request.url), "status_code": response.status_code, "sha256": hashlib.sha256(body).hexdigest(),
                      "bytes": len(body), "file": path.name})
        if response.status_code != 200:
            raise _CollectionStop(f"HTTP_{response.status_code}")
        try:
            return response.json()
        except ValueError as exc:
            raise _CollectionStop("RESPONSE_NOT_JSON") from exc

    start, end = (int(datetime.fromisoformat(d).replace(tzinfo=timezone.utc).timestamp()) for d in COLLECTION_WINDOW)
    try:
        data = get("gamma_public_search", GAMMA_SEARCH_URL, {"q": "recession 2026", "limit_per_type": 20})
        if not isinstance(data, dict) or not isinstance(data.get("events"), list):
            raise _CollectionStop("SEARCH_UNEXPECTED_SHAPE")
        markets = [m for event in data["events"] if isinstance(event, dict) for m in (event.get("markets") or []) if isinstance(m, dict)]
        for question, sample_ids in COLLECTION_TARGETS.items():
            found = [m for m in markets if _question_key(m.get("question")) == _question_key(question)]
            if len(found) != 1:
                record["markets"][question] = {"status": "NOT_FOUND" if not found else "AMBIGUOUS", "samples": sample_ids}
                continue
            market = found[0]
            outcomes, tokens = _json_list(market.get("outcomes")), _json_list(market.get("clobTokenIds"))
            if "Yes" not in outcomes or len(tokens) != len(outcomes):
                record["markets"][question] = {"status": "UNEXPECTED_MARKET_SHAPE", "samples": sample_ids}
                continue
            token = tokens[outcomes.index("Yes")]
            history = get("clob_prices_history_" + _question_key(question).replace(" ", "_"), CLOB_HISTORY_URL,
                          {"market": token, "startTs": start, "endTs": end, "fidelity": 1440})
            points = history.get("history") if isinstance(history, dict) else None
            if not isinstance(points, list):
                raise _CollectionStop("HISTORY_UNEXPECTED_SHAPE")
            record["markets"][question] = {
                "status": "COLLECTED", "samples": sample_ids, "market_id": market.get("id"), "question": market.get("question"), "yes_token": token,
                "daily_yes_price_utc": {datetime.fromtimestamp(int(p["t"]), tz=timezone.utc).date().isoformat(): p["p"] for p in points
                                        if isinstance(p, dict) and "t" in p and "p" in p}}
    except _CollectionStop as stop:
        record["stopped"] = str(stop)
    finally:
        client.close()
    record["requests_sent"] = sum(1 for r in record["requests"] if "status_code" in r or "error" in r)
    addendum: dict[str, list] = {}
    for question, market in record["markets"].items():
        if market["status"] != "COLLECTED":
            continue
        for sample_id in market["samples"]:
            addendum.setdefault(sample_id, []).append({
                "type": "collected_prediction_market_history", "question": market["question"], "daily_yes_price_utc": market["daily_yes_price_utc"],
                "source": CLOB_HISTORY_URL, "collected_at": next(r["retrieved_at"] for r in record["requests"] if r["name"].endswith(_question_key(question).replace(" ", "_"))),
                "note": "collected for this verification; the run's agent saw the live price on its analysis date, not this file"})
    _write_json(out_dir / "collection_record.json", record)
    _write_json(out_dir / "review_form_v4_addendum.json", {"status": "ADDENDUM -- material collected for this verification, given to the reviewer with the v4 form",
                                                            "items": addendum})
    return record


# ----------------------------------------------------------------------------------------------------------------------------------
# CLI
# ----------------------------------------------------------------------------------------------------------------------------------


def _build_parser() -> argparse.ArgumentParser:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = ap.add_subparsers(dest="cmd", required=True)
    f = sub.add_parser("freeze")
    f.add_argument("--manifest", required=True)
    f.add_argument("--review-form", required=True)
    f.add_argument("--out-dir", required=True)
    z = sub.add_parser("sizing")
    z.add_argument("--manifest", required=True)
    z.add_argument("--out", required=True)
    h = sub.add_parser("history")
    h.add_argument("--manifest", required=True)
    h.add_argument("--out", required=True)
    pf = sub.add_parser("preflight")
    pf.add_argument("--plan", required=True)
    pf.add_argument("--work-dir", required=True)
    r = sub.add_parser("predict")
    r.add_argument("--authorized-plan", required=True)
    r.add_argument("--plan-sha256", required=True)
    c = sub.add_parser("collect")
    c.add_argument("--authorized-plan", required=True)
    c.add_argument("--plan-sha256", required=True)
    st = sub.add_parser("status")
    st.add_argument("--execution-dir", required=True)
    s = sub.add_parser("score")
    s.add_argument("--predictions", required=True)
    s.add_argument("--review-form", required=True)
    s.add_argument("--history")
    s.add_argument("--out", required=True)
    return ap


def _refuse_existing(path: Path) -> bool:
    if Path(path).exists():
        print("refusing: output exists", path, file=sys.stderr)
        return True
    return False


def main(argv: list[str] | None = None, *, base_transport_factory: Callable[[], httpx.BaseTransport] | None = None) -> int:
    """``base_transport_factory`` exists for tests only: it replaces the network under the real guard / audit / client stack."""
    args = _build_parser().parse_args(argv)
    config = FrozenConfig()
    if args.cmd == "freeze":
        out_dir = Path(args.out_dir)
        if out_dir.exists() and any(out_dir.iterdir()):
            print("refusing: output directory not empty", out_dir, file=sys.stderr)
            return 2
        manifest, form = Path(args.manifest).resolve(), Path(args.review_form).resolve()
        frozen = build_frozen_requests(load_samples(manifest), config)
        _write_json(out_dir / "frozen_requests.json", frozen)
        plan = {
            "authorized": False, "authorized_by": "", "authorization_reference": "",
            "execution_id": "t3joint-<UTC timestamp>-<8 hex>", "out_dir": "outputs/t3_joint_evaluations",
            "manifest": _rel(manifest), "manifest_sha256": _sha256_file(manifest),
            "review_form": _rel(form), "review_form_sha256": _sha256_file(form),
            "frozen_requests": _rel(out_dir / "frozen_requests.json"), "frozen_requests_sha256": _sha256_file(out_dir / "frozen_requests.json"),
            "code_identity": code_identity(), "prompt_identity_sha256": frozen["prompt_identity_sha256"], "config": asdict(config),
            "collection": {"authorized": False, "request_cap": COLLECTION_REQUEST_CAP, "targets": COLLECTION_TARGETS,
                           "endpoints": [GAMMA_SEARCH_URL, CLOB_HISTORY_URL], "window_utc": list(COLLECTION_WINDOW),
                           "out_dir": "<out_dir>/<execution_id>-materials",
                           "note": "run by `collect` only when this flag is true; separate from predict"},
            "note": "UNSIGNED TEMPLATE -- predict refuses it until authorized=true and authorized_by is filled; its sha256 must be passed as --plan-sha256",
        }
        _write_json(out_dir / "authorized_plan_TEMPLATE.json", plan)
        return 0
    if args.cmd == "sizing":
        if _refuse_existing(Path(args.out)):
            return 2
        _write_json(Path(args.out), sizing(load_samples(Path(args.manifest)), config))
        return 0
    if args.cmd == "history":
        if _refuse_existing(Path(args.out)):
            return 2
        samples = load_samples(Path(args.manifest))
        answers = historical_alpha_answers(samples, config)
        _write_json(Path(args.out), {"schema_version": "t3_historical_alpha_answers.v1",
                                     "status": "HISTORICAL COMPARISON ONLY -- not this execution's prediction; produced before freezing, under each saved run's own configuration",
                                     "counts": dict(Counter(a["status"] for a in answers.values())), "answers": answers})
        return 0
    if args.cmd == "status":
        execution_dir = Path(args.execution_dir)
        print(json.dumps(summarize_checkpoint(execution_dir / "checkpoint.jsonl"), ensure_ascii=False, indent=1))
        return 0
    if args.cmd == "score":
        if _refuse_existing(Path(args.out)):
            return 2
        predictions = [json.loads(line) for line in Path(args.predictions).read_text(encoding="utf-8").splitlines() if line.strip()]
        review_form = json.loads(Path(args.review_form).read_text(encoding="utf-8"))
        history = json.loads(Path(args.history).read_text(encoding="utf-8"))["answers"] if args.history else None
        _write_json(Path(args.out), score(predictions, review_form, history))
        return 0
    if args.cmd == "preflight":
        work_dir = Path(args.work_dir)
        if work_dir.exists() and any(work_dir.iterdir()):
            print("refusing: work directory not empty", work_dir, file=sys.stderr)
            return 2
        plan = _check_plan(Path(args.plan), None, require_authorized=False)
        if isinstance(plan, str):
            print("preflight failed:", plan, file=sys.stderr)
            return 3
        cfg = _config_from_plan(plan)
        drift = _frozen_matches(plan, load_samples(REPO / plan["manifest"]), cfg)
        report: dict[str, Any] = {"plan_checks": "passed (authorization not checked)", "frozen_requests": drift or "match"}
        frozen = json.loads((REPO / plan["frozen_requests"]).read_text(encoding="utf-8"))
        report["rehearsal"] = rehearse(REPO / plan["manifest"], cfg, frozen, work_dir / "rehearsal") if drift is None else "not run"
        _write_json(work_dir / "preflight_report.json", report)
        return 0 if drift is None and report["rehearsal"]["passed"] else 4

    # predict / collect: only with an authorized plan whose hash the caller states; round 25 never executes these branches
    plan = _check_plan(Path(args.authorized_plan), args.plan_sha256, require_authorized=True)
    if isinstance(plan, str):
        print("refusing:", plan, file=sys.stderr)
        return 3
    if args.cmd == "collect":
        if (plan.get("collection") or {}).get("authorized") is not True:
            print("refusing: the plan does not authorize material collection", file=sys.stderr)
            return 3
        out = REPO / plan["out_dir"] / f"{plan['execution_id']}-materials"
        if out.exists():
            print("refusing: collection directory exists (collection is never repeated)", file=sys.stderr)
            return 2
        record = collect_materials(out, transport=base_transport_factory() if base_transport_factory else None)
        return 0 if record["stopped"] is None else 5
    cfg = _config_from_plan(plan)
    execution_dir = REPO / plan["out_dir"] / plan["execution_id"]
    if execution_dir.exists():
        print("refusing: execution directory exists (an execution is never resumed or re-sent)", file=sys.stderr)
        return 2
    manifest = REPO / plan["manifest"]
    drift = _frozen_matches(plan, load_samples(manifest), cfg)
    if drift:
        print("refusing:", drift, file=sys.stderr)
        return 3
    if base_transport_factory is None:
        try:
            from dotenv import load_dotenv

            load_dotenv(REPO / ".env", override=False)
        except ImportError:
            pass
        if not os.environ.get(cfg.api_key_env):
            print(f"refusing: {cfg.api_key_env} is not set", file=sys.stderr)
            return 3
    execution_dir.mkdir(parents=True)
    shutil.copyfile(args.authorized_plan, execution_dir / "authorized_plan.json")
    frozen = json.loads((REPO / plan["frozen_requests"]).read_text(encoding="utf-8"))
    rehearsal = rehearse(manifest, cfg, frozen, execution_dir / "rehearsal")
    _write_json(execution_dir / "rehearsal_report.json", rehearsal)
    if not rehearsal["passed"]:
        print("refusing: the rehearsal did not pass; nothing was sent", rehearsal["problems"], file=sys.stderr)
        return 4
    checkpoint = Checkpoint(execution_dir / "checkpoint.jsonl")
    checkpoint.write("execution_started", execution_id=plan["execution_id"], plan_sha256=args.plan_sha256)
    guard = SendGuard(frozen, checkpoint)
    gateways = build_task_gateways(cfg, execution_dir, plan["execution_id"], guard, base_transport_factory=base_transport_factory,
                                   api_key="test-not-a-key" if base_transport_factory is not None else None)
    audit: dict = {}
    started = datetime.now(timezone.utc).isoformat()
    predictions = predict(load_samples(manifest), gateways=gateways, config=cfg, audit=audit, guard=guard, progress_dir=execution_dir)
    (execution_dir / "joint_predictions.jsonl").write_text("".join(json.dumps(p, ensure_ascii=False) + "\n" for p in predictions), encoding="utf-8")
    _write_json(execution_dir / "task_audit.json", audit)
    checkpoint.write("execution_finished", guard_tripped=guard.tripped)
    _write_json(execution_dir / "run_summary.json", {
        "execution_id": plan["execution_id"], "plan_sha256": args.plan_sha256, "started_at": started, "finished_at": datetime.now(timezone.utc).isoformat(),
        # reservations = attempts admitted to a gateway budget (a refused attempt is reserved but never sent; see the checkpoint)
        "gateway_reservations": {task: getattr(gw, "_call_count", None) for task, gw in gateways.items()}, "request_caps": cfg.max_requests,
        "checkpoint": summarize_checkpoint(checkpoint.path), "guard_tripped": guard.tripped,
        "outcomes": {link: dict(Counter((p[link].get("status") or p[link].get("outcome_code")) for p in predictions)) for link in ("L1", "L2", "L3", "L4")},
    })
    return 0 if guard.tripped is None else 5


if __name__ == "__main__":
    raise SystemExit(main())
