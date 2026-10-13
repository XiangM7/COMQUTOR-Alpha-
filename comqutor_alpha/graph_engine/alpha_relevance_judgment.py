"""P4 phase 1 (2026-10-12): the versioned record of Alpha relevance judgments and its read-time verification.

``alpha_relevance_judgments.json`` (``alpha_relevance_judgment.v1``) is a run artifact of its own. It never changes the meaning of the
``alpha_evidence_consumption.v2`` block (whose ``relevance.model_weight`` stays ``None``) and nothing reads it for selection, stance,
admission or scoring. Each record belongs to ONE (claim_id, matched Alpha) pair and is bound to the target ticker, the claim-text
hash, the Alpha-definition hash and every task version (``alpha_relevance_llm.task_identity``).

Source verification uses the relevance task's OWN semantic records only. They live in the run's separate ``alpha_relevance_ledger/``
directory (same recorder, same ``llm_semantic_calls.jsonl`` + ``llm_semantic_manifest.json`` hash check as the main ledger), never in
the run's main ledger -- so a stance record can never corroborate a relevance judgment, and the stance policy never mistakes the
relevance calls for its own ledger.

Read-time states, per pair: ``UNJUDGED`` (no result), ``JUDGED`` (valid determined result whose bindings hold and which the ledger
reproduces), ``UNRESOLVED`` (valid explicit "cannot determine", ledger-reproduced), ``FAILED`` (the call, parsing, validation or a
binding failed -- with the reason). Only ``JUDGED`` carries a tier; a stale binding, an identity mismatch, a damaged ledger or a
result the ledger does not reproduce is FAILED, never JUDGED.

Versions (2026-10-12): a record is re-validated under the output contract its call was made under, and every view carries the
versions from the record's OWN binding. Against the current identity an older record is ``binding_stale`` (shown with its own,
older versions -- never relabelled); an evaluation of an execution planned under a retired version verifies it against that version.
"""

from __future__ import annotations

import hashlib
import json
from collections.abc import Mapping, Sequence
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from comqutor_alpha.alpha_library.alpha_relevance_elements import (
    AlphaRelevanceDefinition,
    RelevanceElementsError,
    load_relevance_definitions,
)
from comqutor_alpha.structure_engine.alpha_relevance_llm import (
    FAILURE_DEFINITION_UNAVAILABLE,
    LLM_TASK_NAME,
    STATE_FAILED,
    STATE_JUDGED,
    STATE_UNJUDGED,
    STATE_UNRESOLVED,
    TIERS,
    RelevanceRequestItem,
    claim_text_sha256,
    is_known_task_identity,
    judge_returned_items,
    matched_pairs,
    task_identity,
)

RESULTS_FILENAME = "alpha_relevance_judgments.json"
RESULTS_SCHEMA_VERSION = "alpha_relevance_judgment.v1"
LEDGER_DIRNAME = "alpha_relevance_ledger"
LEDGER_CALLS_FILENAME = "llm_semantic_calls.jsonl"
LEDGER_MANIFEST_FILENAME = "llm_semantic_manifest.json"
LEDGER_USABLE_INTEGRITY = "MATCHES_MANIFEST"

# read-time reasons (the task's own call / validation reasons are kept as recorded)
FAILURE_RECORD_INVALID = "record_invalid"
FAILURE_OWNER_MISMATCH = "owner_mismatch"
FAILURE_BINDING_STALE = "binding_stale"
FAILURE_LEDGER_UNAVAILABLE = "ledger_unavailable"
FAILURE_LEDGER_INTEGRITY = "ledger_integrity_failed"
FAILURE_PAIR_NOT_IN_LEDGER = "pair_not_in_ledger"
FAILURE_LEDGER_CONFLICT = "ledger_conflict"
FAILURE_LEDGER_LABEL_MISMATCH = "ledger_label_mismatch"
UNJUDGED_NO_RESULTS = "no_relevance_results_for_run"
UNJUDGED_PAIR_NOT_REQUESTED = "pair_not_in_results"

SIMULATED_PROVIDER = "simulated"
TEST_EXECUTION_MODES = frozenset({"test", "replay_fixture"})


def build_results_payload(
    *,
    run_id: str,
    ticker: str,
    items: Sequence[RelevanceRequestItem],
    results: Mapping[tuple[str, str], Mapping[str, Any]],
    without_definition: Sequence[Mapping[str, str]],
    ledger: Mapping[str, Any],
    experiment: Mapping[str, Any],
    stats: Mapping[str, Any],
    created_at: str,
) -> dict[str, Any]:
    identity = task_identity()
    records = []
    for item in items:
        result = results.get(item.key)
        if result is None:
            continue  # never sent (e.g. the budget ended the run): stays UNJUDGED on read, never a fabricated FAILED
        records.append({
            "claim_id": item.claim_id, "alpha_id": item.alpha_id, "state": result["state"], "tier": result.get("tier"),
            "anchor_element_ids": list(result.get("anchor_element_ids") or []), "basis": result.get("basis"),
            "anchor_evidence": list(result.get("anchor_evidence") or []),
            # output v3: the statements the model reported and where the tier came from (absent / empty for older contracts)
            "statements": list(result.get("statements") or []), "tier_source": result.get("tier_source"),
            "unresolved_reason": result.get("unresolved_reason"), "failure_reason": result.get("failure_reason"),
            "call_id": result.get("call_id"),
            "binding": {"ticker": item.ticker, "claim_id": item.claim_id, "alpha_id": item.alpha_id,
                        "claim_text_sha256": item.claim_text_sha256, "alpha_definition_sha256": item.definition.sha256, **identity},
        })
    for entry in without_definition:
        records.append({
            "claim_id": entry["claim_id"], "alpha_id": entry["alpha_id"], "state": STATE_FAILED, "tier": None, "anchor_element_ids": [],
            "basis": None, "unresolved_reason": None, "failure_reason": FAILURE_DEFINITION_UNAVAILABLE, "call_id": None,
            "binding": {"ticker": ticker, "claim_id": entry["claim_id"], "alpha_id": entry["alpha_id"], **identity},
        })
    return {
        "schema_version": RESULTS_SCHEMA_VERSION,
        "run_id": run_id,
        "ticker": ticker,
        "created_at": created_at,
        "task": identity,
        "experiment": dict(experiment),
        "ledger": dict(ledger),
        "stats": dict(stats),
        "consumption_effect": "none: the label is not read by Alpha selection, stance, admission or scoring; model_weight stays null",
        "records": records,
    }


@dataclass
class RelevanceLedger:
    """The relevance task's own semantic records of one run (``alpha_relevance_ledger/``)."""

    directory: str
    available: bool
    integrity: str | None = None
    calls_file_sha256: str | None = None
    manifest_calls_file_sha256: str | None = None
    records: dict[str, dict[str, Any]] = field(default_factory=dict)  # call_id -> record (relevance task only)
    other_task_records: int = 0
    pair_outcomes: dict[tuple[str, str], set[tuple[str, str | None]]] = field(default_factory=dict)

    @property
    def usable(self) -> bool:
        return self.available and self.integrity == LEDGER_USABLE_INTEGRITY

    def description(self) -> dict[str, Any]:
        return {"directory": Path(self.directory).name, "available": self.available, "integrity": self.integrity,
                "calls_file_sha256": self.calls_file_sha256, "manifest_calls_file_sha256": self.manifest_calls_file_sha256,
                "relevance_records": len(self.records), "other_task_records_ignored": self.other_task_records, "usable": self.usable}

    @classmethod
    def load(cls, run_dir: str | Path, definitions: Mapping[str, AlphaRelevanceDefinition] | None = None) -> RelevanceLedger:
        directory = Path(run_dir) / LEDGER_DIRNAME
        calls = directory / LEDGER_CALLS_FILENAME
        if not calls.is_file():
            return cls(directory=str(directory), available=False)
        raw = calls.read_bytes()
        sha = hashlib.sha256(raw).hexdigest()
        expected = None
        integrity = "NO_MANIFEST"
        manifest = directory / LEDGER_MANIFEST_FILENAME
        if manifest.is_file():
            try:
                expected = json.loads(manifest.read_text(encoding="utf-8")).get("calls_file_sha256")
            except ValueError:
                expected = None
            integrity = "MANIFEST_WITHOUT_HASH" if not expected else ("MATCHES_MANIFEST" if expected == sha else "MISMATCH_MANIFEST")
        ledger = cls(directory=str(directory), available=True, integrity=integrity, calls_file_sha256=sha, manifest_calls_file_sha256=expected)
        for line in raw.decode("utf-8", "replace").splitlines():
            try:
                record = json.loads(line)
            except ValueError:
                continue
            if not isinstance(record, Mapping):
                continue
            if record.get("task") != LLM_TASK_NAME:
                ledger.other_task_records += 1  # e.g. a stance record: never evidence for a relevance judgment
                continue
            call_id = str(record.get("call_id") or "")
            if call_id:
                ledger.records[call_id] = dict(record)
        if definitions is not None:
            for record in ledger.records.values():
                if record.get("validation_status") != "accepted":
                    continue
                for key, result in _reproduce_call(record, definitions).items():
                    ledger.pair_outcomes.setdefault(key, set()).add((result["state"], result.get("tier")))
        return ledger


def _mapping(value: Any) -> Mapping[str, Any]:
    return value if isinstance(value, Mapping) else {}


def _request_item_from_ledger(record: Mapping[str, Any], key: tuple[str, str], definitions: Mapping[str, AlphaRelevanceDefinition]) -> tuple[RelevanceRequestItem | None, Mapping[str, Any] | None]:
    for entry in _mapping(record.get("input_payload")).get("items") or []:
        if isinstance(entry, Mapping) and (entry.get("claim_id"), entry.get("alpha_id")) == key:
            definition = definitions.get(key[1])
            if definition is None:
                return None, entry
            return RelevanceRequestItem(
                claim_id=key[0], alpha_id=key[1], ticker=str(entry.get("ticker") or ""), claim_text=str(entry.get("claim_text") or ""),
                claim_text_sha256=str(entry.get("claim_text_sha256") or ""), definition=definition,
            ), entry
    return None, None


def _reproduce_call(record: Mapping[str, Any], definitions: Mapping[str, AlphaRelevanceDefinition]) -> dict[tuple[str, str], dict[str, Any]]:
    """What the recorded output of one accepted call means for each pair it requested, re-validated today."""
    keys = [(str(e.get("claim_id")), str(e.get("alpha_id"))) for e in _mapping(record.get("input_payload")).get("items") or [] if isinstance(e, Mapping)]
    batch = [item for key in keys if (item := _request_item_from_ledger(record, key, definitions)[0]) is not None]
    output = record.get("validated_output")
    returned = output.get("items") if isinstance(output, Mapping) else None
    return judge_returned_items(batch, returned if isinstance(returned, list) else [], output_schema_version=str(record.get("output_schema_version") or ""))


def _versions(record: Mapping[str, Any] | None) -> dict[str, Any] | None:
    """The versions a saved record was made under (from its own binding) -- shown as they are, never as the current ones."""
    binding = _mapping((record or {}).get("binding"))
    if not binding:
        return None
    return {name: binding.get(name) for name in ("prompt_version", "criterion_version", "output_schema_version")}


def _failed(reason: str, record: Mapping[str, Any] | None = None, detail: str | None = None) -> dict[str, Any]:
    return {"state": STATE_FAILED, "tier": None, "reason": reason, "reason_detail": detail,
            "anchor_element_ids": [], "basis": None, "unresolved_reason": None, "anchor_evidence": [], "statements": [], "tier_source": None,
            "call_id": (record or {}).get("call_id"), "recorded_state": (record or {}).get("state"), "versions": _versions(record)}


@dataclass
class RelevanceVerification:
    present: bool
    owner_run_id: str | None
    pairs: dict[tuple[str, str], dict[str, Any]]
    ledger: RelevanceLedger | None
    experiment: Mapping[str, Any]
    orphan_records: list[tuple[str, str]]
    error: str | None = None
    definitions: Mapping[str, AlphaRelevanceDefinition] | None = None

    def summary(self) -> dict[str, Any]:
        states: dict[str, int] = {}
        tiers: dict[str, int] = {}
        reasons: dict[str, int] = {}
        for view in self.pairs.values():
            states[view["state"]] = states.get(view["state"], 0) + 1
            if view["state"] == STATE_JUDGED:
                tiers[view["tier"]] = tiers.get(view["tier"], 0) + 1
            if view.get("reason"):
                reasons[view["reason"]] = reasons.get(view["reason"], 0) + 1
        return {
            "contract": RESULTS_SCHEMA_VERSION, "present": self.present, "owner_run_id": self.owner_run_id,
            "matched_pairs": len(self.pairs), "states": dict(sorted(states.items())), "tiers": dict(sorted(tiers.items())),
            "reasons": dict(sorted(reasons.items())), "orphan_records": len(self.orphan_records),
            "ledger": self.ledger.description() if self.ledger is not None else None,
            "experiment": dict(self.experiment), "error": self.error,
            "consumption_effect": "none (the label is not consumed; model_weight stays null)",
        }


def verify_relevance_judgments(
    run_dir: str | Path,
    *,
    run_id: str,
    ticker: str,
    matches: Sequence[Mapping[str, Any]],
    definitions: Mapping[str, AlphaRelevanceDefinition] | None = None,
) -> RelevanceVerification:
    """Every current matched pair of the run, with its verified relevance state (see the module docstring)."""
    current = {(str(m["claim_id"]), str(m["matched_alpha"])): m for m in matched_pairs(matches)}
    path = Path(run_dir) / RESULTS_FILENAME
    if not path.is_file():
        return RelevanceVerification(False, None, {k: _unjudged(UNJUDGED_NO_RESULTS) for k in current}, None, {}, [])
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except ValueError:
        payload = None
    if not isinstance(payload, Mapping) or payload.get("schema_version") != RESULTS_SCHEMA_VERSION or not isinstance(payload.get("records"), list):
        return RelevanceVerification(True, None, {k: _failed(FAILURE_RECORD_INVALID) for k in current}, None, {}, [], error=FAILURE_RECORD_INVALID)
    if definitions is None:
        try:
            definitions = load_relevance_definitions()
        except RelevanceElementsError as exc:
            pairs = {k: _failed(FAILURE_DEFINITION_UNAVAILABLE, detail=exc.reason_code) for k in current}
            return RelevanceVerification(True, payload.get("run_id"), pairs, None, payload.get("experiment") or {}, [], error=exc.reason_code)
    ledger = RelevanceLedger.load(run_dir, definitions)
    identity = task_identity()
    index: dict[tuple[str, str], list[Mapping[str, Any]]] = {}
    for record in payload["records"]:
        if isinstance(record, Mapping):
            index.setdefault((str(record.get("claim_id")), str(record.get("alpha_id"))), []).append(record)
    owner = payload.get("run_id")
    pairs: dict[tuple[str, str], dict[str, Any]] = {}
    for key, match in current.items():
        records = index.get(key) or []
        if not records:
            pairs[key] = _unjudged(UNJUDGED_PAIR_NOT_REQUESTED)
        elif len(records) > 1:
            pairs[key] = _failed(FAILURE_LEDGER_CONFLICT, records[0], "more than one record for this pair in the results file")
        else:
            pairs[key] = _verify_record(records[0], key, match, ticker=ticker, run_id=run_id, owner=owner, ledger=ledger,
                                        definitions=definitions, identity=identity)
    orphans = sorted(k for k in index if k not in current)
    return RelevanceVerification(True, owner, pairs, ledger, payload.get("experiment") or {}, orphans, definitions=definitions)


def verify_relevance_records(
    run_dir: str | Path,
    *,
    owner_run_id: str,
    pairs: Mapping[tuple[str, str], tuple[str, Mapping[str, Any]]],
    definitions: Mapping[str, AlphaRelevanceDefinition] | None = None,
    identity: Mapping[str, Any] | None = None,
) -> RelevanceVerification:
    """P4 phase 2 (2026-10-12): ``verify_relevance_judgments`` for a results file whose pairs span several tickers (one round of a
    small-sample evaluation). Each expected pair -- key -> (ticker, the record its request was built from) -- is checked by the same
    ``_verify_record`` rules against the same task-own ledger; a pair without a record stays UNJUDGED (never sent), never FAILED.
    ``identity`` (2026-10-12): the task identity the execution was planned under -- a REGISTERED version, current or retired -- so an
    execution made under prompt v1 is verified as v1 (its records are never read as, or relabelled to, a later version). Default: the
    current identity. An unknown identity verifies nothing."""
    path = Path(run_dir) / RESULTS_FILENAME
    if not path.is_file():
        return RelevanceVerification(False, None, {k: _unjudged(UNJUDGED_NO_RESULTS) for k in pairs}, None, {}, [])
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except ValueError:
        payload = None
    if not isinstance(payload, Mapping) or payload.get("schema_version") != RESULTS_SCHEMA_VERSION or not isinstance(payload.get("records"), list):
        return RelevanceVerification(True, None, {k: _failed(FAILURE_RECORD_INVALID) for k in pairs}, None, {}, [], error=FAILURE_RECORD_INVALID)
    if definitions is None:
        try:
            definitions = load_relevance_definitions()
        except RelevanceElementsError as exc:
            failed = {k: _failed(FAILURE_DEFINITION_UNAVAILABLE, detail=exc.reason_code) for k in pairs}
            return RelevanceVerification(True, payload.get("run_id"), failed, None, payload.get("experiment") or {}, [], error=exc.reason_code)
    if identity is not None and not is_known_task_identity(identity):
        return RelevanceVerification(True, payload.get("run_id"), {k: _failed(FAILURE_RECORD_INVALID, detail="unknown task identity") for k in pairs},
                                     None, payload.get("experiment") or {}, [], error="unknown_task_identity")
    ledger = RelevanceLedger.load(run_dir, definitions)
    identity = dict(identity) if identity is not None else task_identity()
    index: dict[tuple[str, str], list[Mapping[str, Any]]] = {}
    for record in payload["records"]:
        if isinstance(record, Mapping):
            index.setdefault((str(record.get("claim_id")), str(record.get("alpha_id"))), []).append(record)
    owner = payload.get("run_id")
    verified: dict[tuple[str, str], dict[str, Any]] = {}
    for key, (ticker, source) in pairs.items():
        records = index.get(key) or []
        if not records:
            verified[key] = _unjudged(UNJUDGED_PAIR_NOT_REQUESTED)
        elif len(records) > 1:
            verified[key] = _failed(FAILURE_LEDGER_CONFLICT, records[0], "more than one record for this pair in the results file")
        else:
            verified[key] = _verify_record(records[0], key, source, ticker=ticker, run_id=owner_run_id, owner=owner, ledger=ledger,
                                           definitions=definitions, identity=identity)
    orphans = sorted(k for k in index if k not in pairs)
    return RelevanceVerification(True, owner, verified, ledger, payload.get("experiment") or {}, orphans, definitions=definitions)


def _unjudged(reason: str) -> dict[str, Any]:
    return {"state": STATE_UNJUDGED, "tier": None, "reason": reason, "reason_detail": None, "anchor_element_ids": [], "basis": None,
            "unresolved_reason": None, "anchor_evidence": [], "statements": [], "tier_source": None, "call_id": None, "recorded_state": None,
            "versions": None}


def _verify_record(
    record: Mapping[str, Any],
    key: tuple[str, str],
    match: Mapping[str, Any],
    *,
    ticker: str,
    run_id: str,
    owner: Any,
    ledger: RelevanceLedger,
    definitions: Mapping[str, AlphaRelevanceDefinition],
    identity: Mapping[str, str],
) -> dict[str, Any]:
    if owner != run_id:
        return _failed(FAILURE_OWNER_MISMATCH, record, f"results belong to run {owner}, read by run {run_id}")
    state, tier = record.get("state"), record.get("tier")
    if state not in (STATE_JUDGED, STATE_UNRESOLVED, STATE_FAILED) or (state == STATE_JUDGED) != (tier in TIERS) or (state != STATE_JUDGED and tier is not None):
        return _failed(FAILURE_RECORD_INVALID, record, "state / tier combination is not allowed")
    binding = _mapping(record.get("binding"))
    definition = definitions.get(key[1])
    expected_binding = {"ticker": ticker, "claim_id": key[0], "alpha_id": key[1], "claim_text_sha256": claim_text_sha256(match),
                        "alpha_definition_sha256": definition.sha256 if definition is not None else None, **identity}
    if definition is None:
        return _failed(FAILURE_DEFINITION_UNAVAILABLE, record, key[1])
    stale = [name for name, value in expected_binding.items() if binding.get(name) != value]
    if stale:
        return _failed(FAILURE_BINDING_STALE, record, ",".join(stale))
    if state == STATE_FAILED and not record.get("call_id"):
        # a failure before any semantic call was recorded (e.g. no definition): it claims no judgment, so nothing needs corroborating
        return _failed(str(record.get("failure_reason") or FAILURE_RECORD_INVALID), record, "no semantic call was recorded")
    if not ledger.available:
        return _failed(FAILURE_LEDGER_UNAVAILABLE, record)
    if not ledger.usable:
        return _failed(FAILURE_LEDGER_INTEGRITY, record, ledger.integrity)
    call = ledger.records.get(str(record.get("call_id") or ""))
    if call is None:
        return _failed(FAILURE_PAIR_NOT_IN_LEDGER, record, "the recorded call is not a relevance-task record of this run's relevance ledger")
    call_identity = {"prompt_version": call.get("prompt_version"), "prompt_sha256": call.get("prompt_sha256"),
                     "input_schema_version": call.get("input_schema_version"), "output_schema_version": call.get("output_schema_version")}
    stale_call = [name for name, value in call_identity.items() if value != identity[name]]
    if stale_call:
        return _failed(FAILURE_BINDING_STALE, record, "ledger call " + ",".join(stale_call))
    item, entry = _request_item_from_ledger(call, key, definitions)
    if entry is None:
        return _failed(FAILURE_PAIR_NOT_IN_LEDGER, record, "the recorded call did not request this pair")
    if entry.get("claim_text_sha256") != binding.get("claim_text_sha256") or entry.get("alpha_definition_sha256") != binding.get("alpha_definition_sha256"):
        return _failed(FAILURE_LEDGER_LABEL_MISMATCH, record, "the recorded request carries different input hashes")
    if call.get("validation_status") == "accepted":
        if item is None:
            return _failed(FAILURE_DEFINITION_UNAVAILABLE, record, key[1])
        returned = _mapping(call.get("validated_output")).get("items")
        expected = judge_returned_items([item], returned if isinstance(returned, list) else [], output_schema_version=str(call.get("output_schema_version") or ""))[key]
        if len(ledger.pair_outcomes.get(key, set())) > 1:
            return _failed(FAILURE_LEDGER_CONFLICT, record, "accepted relevance records disagree for this pair")
        same = (expected["state"] == state and expected.get("tier") == tier
                and list(expected.get("anchor_element_ids") or []) == list(record.get("anchor_element_ids") or [])
                and expected.get("basis") == record.get("basis") and expected.get("unresolved_reason") == record.get("unresolved_reason")
                and list(expected.get("anchor_evidence") or []) == list(record.get("anchor_evidence") or [])
                and list(expected.get("statements") or []) == list(record.get("statements") or [])
                and expected.get("tier_source") == record.get("tier_source")
                and (state != STATE_FAILED or expected.get("failure_reason") == record.get("failure_reason")))
    else:
        recorded_reasons = set(str(call.get("fallback_reason") or "").split(","))
        same = state == STATE_FAILED and record.get("failure_reason") in recorded_reasons
        expected = None
    if not same:
        return _failed(FAILURE_LEDGER_LABEL_MISMATCH, record, "the relevance ledger does not reproduce the saved result")
    return {
        "state": state, "tier": tier if state == STATE_JUDGED else None,
        "reason": record.get("failure_reason") if state == STATE_FAILED else None, "reason_detail": None,
        "anchor_element_ids": list(record.get("anchor_element_ids") or []) if state != STATE_FAILED else [],
        "basis": (expected or {}).get("basis") if expected else record.get("basis"),
        "unresolved_reason": record.get("unresolved_reason") if state == STATE_UNRESOLVED else None,
        "anchor_evidence": list(record.get("anchor_evidence") or []) if state != STATE_FAILED else [],
        "statements": list(record.get("statements") or []) if state != STATE_FAILED else [],
        "tier_source": record.get("tier_source") if state == STATE_JUDGED else None,
        "call_id": call.get("call_id"), "recorded_state": state, "versions": _versions(record),
        "source": {"provider": call.get("provider"), "model": call.get("model"), "execution_mode": call.get("execution_mode"),
                   "test_data": call.get("provider") == SIMULATED_PROVIDER or call.get("execution_mode") in TEST_EXECUTION_MODES},
    }


__all__ = [
    "LEDGER_DIRNAME",
    "RESULTS_FILENAME",
    "RESULTS_SCHEMA_VERSION",
    "SIMULATED_PROVIDER",
    "RelevanceLedger",
    "RelevanceVerification",
    "build_results_payload",
    "verify_relevance_judgments",
    "verify_relevance_records",
]
