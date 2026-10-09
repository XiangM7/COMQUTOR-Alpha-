"""Alpha-classification recovery: derived-run finalization, task isolation, and
the (separately authorized) direction-task follow-up manifest.

2026-10-06 (round 15). A real run whose ``alpha_classifier`` calls were lost to
a defect must not be edited in place. Recovery therefore produces a NEW
execution (``recovery-<UTC stamp>-<hex8>``) that carries ``based_on_run_id``,
and the original run directory is only ever read.

Three independent pieces, all zero-Provider-call by construction:

* ``finalize_classification_recovery_execution`` -- assembles the derived run
  from the original's frozen artifacts plus an already-assembled alpha-matches
  payload, then runs the SAME production completion flow
  (``routes_research._run_week3_graph_pipeline``) that a new run uses.
  Follows the precedent of ``trigger_content_support_reevaluation`` (new
  execution id, ``run_id``-only rebasing, ``based_on_run_id``) and
  deliberately does NOT replicate its one write into the original run's
  directory (the ``reevaluation_executions.jsonl`` index).
* ``TaskAllowlistGateway`` -- a transparent proxy that refuses to forward any
  Provider call whose task is not on an allowlist. Recovery wraps its Gateway
  in it so classification can never send a second kind of request (for
  example ``evidence_stance_classifier``).
* ``build_stance_followup_manifest`` -- sizes and lists the direction
  (``evidence_stance_classifier``) requests that the recovered matches would
  need, with an independent budget and a reuse check. It sends nothing.
"""

from __future__ import annotations

import copy
import hashlib
import json
import math
import threading
from collections.abc import Callable, Iterable, Mapping, Sequence
from datetime import UTC, datetime
from pathlib import Path
from typing import Any
from uuid import uuid4

from comqutor_alpha.storage.file_store import (
    load_json_record,
    load_json_record_if_exists,
    run_dir_for,
    save_json_record,
    validate_run_id_for_path,
)

RECOVERY_EXECUTION_TYPE = "alpha_classification_recovery"
RECOVERY_EXECUTION_MODE = "recovery"  # research_runs.execution_mode (<= 16 chars)
RECOVERY_LINEAGE_FILENAME = "recovery_lineage.json"
# Round 17: the direction-evaluation execution reuses this saver with its own identity (see direction_evaluation.py).
DIRECTION_EXECUTION_TYPE = "alpha_direction_evaluation"
DIRECTION_EXECUTION_MODE = "direction"  # research_runs.execution_mode (<= 16 chars)
DIRECTION_LINEAGE_FILENAME = "direction_lineage.json"
DIRECTION_RESULTS_FILENAME = "evidence_stance_direction_results.json"
# Round 18: re-qualification of evidence eligibility from ALREADY-SAVED results (zero model calls).
REQUALIFICATION_EXECUTION_TYPE = "alpha_evidence_requalification"
REQUALIFICATION_EXECUTION_MODE = "requalification"
REQUALIFICATION_LINEAGE_FILENAME = "requalification_lineage.json"
REQUALIFICATION_RESULTS_FILENAME = "evidence_eligibility_requalification.json"
# T1 closure: an offline recompute of a saved run under the fact-dependency contract (no model, no network).
DEPENDENCY_EXECUTION_TYPE = "alpha_fact_dependency"
DEPENDENCY_EXECUTION_MODE = "dependency"  # research_runs.execution_mode (<= 16 chars)
DEPENDENCY_LINEAGE_FILENAME = "dependency_lineage.json"
RECOVERY_LINEAGE_SCHEMA_VERSION = "comqutor.classification_recovery_lineage.v1"
STANCE_FOLLOWUP_MANIFEST_FILENAME = "evidence_stance_followup_manifest.json"
STANCE_FOLLOWUP_MANIFEST_SCHEMA_VERSION = "comqutor.evidence_stance_followup_manifest.v1"
ALPHA_CLASSIFIER_TASK = "alpha_classifier"
STANCE_TASK = "evidence_stance_classifier"

CHECKPOINT_ORIGIN_FAKE = "fake_http_test"
CHECKPOINT_ORIGIN_REAL = "real"

_REAL_RUNS_DIR = (Path(__file__).resolve().parents[1] / "outputs" / "runs").resolve()

# Artifacts copied from the original run. "rebased" = only run_id fields equal
# to the original run id are rewritten to the new execution id; every other
# byte of content is preserved. Anything not listed (the original's own
# model-call ledger, TradingAgents usage files, downstream results) is NOT
# copied: downstream results are recomputed by the production pipeline and the
# call ledgers describe what the ORIGINAL run spent, not this one.
_REBASED_COPIES = (
    "raw_agent_outputs.json",
    "structured_agent_outputs.json",
    "extracted_structures.json",
    "source_registry.json",
    "market_data_snapshot.json",
    "data_sanity.json",
)
_REQUIRED_COPIES = ("raw_agent_outputs.json", "structured_agent_outputs.json", "extracted_structures.json")
_RUN_ID_LIST_KEYS = ("agent_outputs", "records", "matches", "sources", "canonical_relations")
_CLAIM_ECHO_FIELDS = ("agent", "ticker", "claim", "evidence", "source_agent_output_id")


def new_requalification_execution_id() -> str:
    stamp = datetime.now(UTC).strftime("%Y%m%dT%H%M%SZ")
    return f"requal-{stamp}-{uuid4().hex[:8]}"


def new_dependency_execution_id() -> str:
    stamp = datetime.now(UTC).strftime("%Y%m%dT%H%M%SZ")
    return f"dependency-{stamp}-{uuid4().hex[:8]}"


def new_recovery_execution_id() -> str:
    stamp = datetime.now(UTC).strftime("%Y%m%dT%H%M%SZ")
    return f"recovery-{stamp}-{uuid4().hex[:8]}"


def _utc_timestamp() -> str:
    return datetime.now(UTC).strftime("%Y-%m-%dT%H:%M:%SZ")


def _sha256_bytes(raw: bytes) -> str:
    return hashlib.sha256(raw).hexdigest()


def _sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1 << 20), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _canonical_json(value: Any) -> str:
    return json.dumps(value, sort_keys=True, ensure_ascii=False, separators=(",", ":"), default=str)


def snapshot_directory_hashes(directory: Path) -> dict[str, str]:
    """relative path -> sha256 for every regular file under ``directory``."""
    directory = Path(directory)
    return {
        str(path.relative_to(directory)): _sha256_file(path)
        for path in sorted(directory.rglob("*"))
        if path.is_file()
    }


def rebase_run_id(payload: Any, *, base_run_id: str, execution_id: str) -> Any:
    """Copy of ``payload`` with every ``run_id`` that EQUALS ``base_run_id`` at
    the top level, or on the items of the known list keys, rewritten to
    ``execution_id``. Nothing else changes -- claim ids, agent output ids,
    text, evidence, sources and verification bindings are preserved verbatim
    (the same rule as ``_rebase_run_id_for_reevaluation_execution``)."""
    out = copy.deepcopy(payload)
    if not isinstance(out, dict):
        return out
    if out.get("run_id") == base_run_id:
        out["run_id"] = execution_id
    for key in _RUN_ID_LIST_KEYS:
        items = out.get(key)
        if isinstance(items, list):
            for item in items:
                if isinstance(item, dict) and item.get("run_id") == base_run_id:
                    item["run_id"] = execution_id
    return out


def _count_run_id_fields_equal_to(value: Any, run_id: str) -> int:
    """Deep count of ``run_id`` keys whose value equals ``run_id``."""
    count = 0
    stack = [value]
    while stack:
        node = stack.pop()
        if isinstance(node, dict):
            for key, child in node.items():
                if key == "run_id" and child == run_id:
                    count += 1
                elif isinstance(child, (dict, list)):
                    stack.append(child)
        elif isinstance(node, list):
            stack.extend(child for child in node if isinstance(child, (dict, list)))
    return count


def _normalized_content_sha256(payload: Any, run_ids: Iterable[str]) -> str:
    """Hash of ``payload`` with every string value that is exactly one of
    ``run_ids`` replaced by a placeholder: equal hashes prove two payloads
    differ at most in their run id fields."""
    ids = set(run_ids)

    def walk(node: Any) -> Any:
        if isinstance(node, dict):
            return {key: walk(child) for key, child in node.items()}
        if isinstance(node, list):
            return [walk(child) for child in node]
        if isinstance(node, str) and node in ids:
            return "<RUN_ID>"
        return node

    return hashlib.sha256(_canonical_json(walk(payload)).encode("utf-8")).hexdigest()


# ---------------------------------------------------------------------------
# Task isolation
# ---------------------------------------------------------------------------


class RecoveryTaskNotAllowedError(RuntimeError):
    """A Provider call for a task outside the recovery allowlist was refused."""

    def __init__(self, task: str, allowed: Iterable[str]) -> None:
        super().__init__(f"task {task!r} is not allowed here (allowed: {sorted(allowed)}); nothing was sent")
        self.task = task


class TaskAllowlistGateway:
    """Transparent proxy over a ``Week2LLMGateway``.

    Every attribute is forwarded unchanged, except the three methods that can
    reach the Provider: each first checks the task name against
    ``allowed_tasks`` and raises ``RecoveryTaskNotAllowedError`` BEFORE
    forwarding anything. Refusals are recorded in ``refused_tasks`` because the
    callers in the mapping layer deliberately convert exceptions into per-claim
    fallbacks -- a refusal must stay visible to the executor even then.

    ``invoke_json_with_trace`` takes ``**kwargs`` so the mapping layer's
    signature detection still passes the out-of-band ``claim_ids`` through.
    """

    def __init__(self, gateway: Any, allowed_tasks: Iterable[str] = (ALPHA_CLASSIFIER_TASK,)) -> None:
        self._gateway = gateway
        self._allowed = frozenset(allowed_tasks)
        self._refused: list[str] = []
        self._lock = threading.Lock()

    @property
    def wrapped_gateway(self) -> Any:
        return self._gateway

    @property
    def allowed_tasks(self) -> frozenset[str]:
        return self._allowed

    @property
    def refused_tasks(self) -> list[str]:
        with self._lock:
            return list(self._refused)

    def __getattr__(self, name: str) -> Any:  # only reached for names not defined above
        return getattr(self._gateway, name)

    def _check(self, task: Any) -> None:
        if task not in self._allowed:
            with self._lock:
                self._refused.append(str(task))
            raise RecoveryTaskNotAllowedError(str(task), self._allowed)

    def invoke_json_with_trace(self, task, payload, validator, **kwargs):
        self._check(task)
        return self._gateway.invoke_json_with_trace(task, payload, validator, **kwargs)

    def invoke_json(self, task, payload, validator):
        self._check(task)
        return self._gateway.invoke_json(task, payload, validator)

    def invoke_prebuilt_json_prompt(self, *, task, **kwargs):
        self._check(task)
        return self._gateway.invoke_prebuilt_json_prompt(task=task, **kwargs)


# ---------------------------------------------------------------------------
# Direction-task (evidence_stance_classifier) follow-up manifest
# ---------------------------------------------------------------------------


def build_stance_followup_manifest(
    match_records: Sequence[Mapping[str, Any]],
    *,
    base_run_id: str | None = None,
    execution_id: str | None = None,
    base_match_records: Sequence[Mapping[str, Any]] | None = None,
    taxonomy: Mapping[str, Any] | None = None,
) -> dict[str, Any]:
    """The direction requests the recovered classification would need, with an
    INDEPENDENT budget (never part of the classification cap) and a reuse
    check. Sends nothing; the production request builder is the only code that
    decides which (claim, Alpha) pairs are needed.

    A pair is reusable only when the ORIGINAL run already holds an LLM stance
    for the same ``claim_id`` and Alpha (``stance_method == "llm"``); a
    deterministic stance never counts as a reusable direction result.
    Reusing is reported, not applied -- this function changes nothing.
    """
    from comqutor_alpha.alpha_library.alpha_loader import load_alpha_taxonomy
    from comqutor_alpha.structure_engine import evidence_stance_llm as esl

    taxonomy = taxonomy or load_alpha_taxonomy()
    items = esl.build_stance_request_items(list(match_records), taxonomy)

    base_llm_pairs: set[tuple[str, str]] = set()
    for match in base_match_records or ():
        if not isinstance(match, Mapping):
            continue
        for candidate in match.get("candidate_scores") or ():
            if isinstance(candidate, Mapping) and candidate.get("stance_method") == esl.STANCE_METHOD_LLM:
                base_llm_pairs.add((str(match.get("claim_id")), str(candidate.get("alpha_id"))))

    listed: list[dict[str, Any]] = []
    for item in items:
        reusable = (item.claim_id, item.target_alpha_id) in base_llm_pairs
        listed.append({
            "claim_id": item.claim_id,
            "target_alpha_id": item.target_alpha_id,
            "request_payload_sha256": hashlib.sha256(_canonical_json(item.payload).encode("utf-8")).hexdigest(),
            "reusable_from_base_run": reusable,
        })
    needing = [entry for entry in listed if not entry["reusable_from_base_run"]]
    batches = math.ceil(len(needing) / esl.BATCH_SIZE) if needing else 0
    matched_claims = sum(1 for m in match_records if isinstance(m, Mapping) and m.get("matched_alpha"))
    return {
        "schema_version": STANCE_FOLLOWUP_MANIFEST_SCHEMA_VERSION,
        "based_on_run_id": base_run_id,
        "execution_id": execution_id,
        "task": STANCE_TASK,
        "sent_by_this_manifest": 0,
        "requires_separate_authorization": True,
        "counted_against_classification_cap": False,
        "matched_claims": matched_claims,
        "pairs_total": len(listed),
        "pairs_reusable_from_base_run": len(listed) - len(needing),
        "pairs_needing_request": len(needing),
        "items_per_request": esl.BATCH_SIZE,
        "max_target_alphas_per_claim": esl.MAX_TARGET_ALPHAS_PER_CLAIM,
        "independent_request_budget": batches,
        "budget_note": (
            "requests = ceil(pairs_needing_request / items_per_request); valid only with "
            "COMQUTOR_WEEK2_LLM_MAX_RETRIES=0 exported (otherwise this task gets max(value, 2) retries)"
        ),
        "items": needing,
        "reusable_items": [entry for entry in listed if entry["reusable_from_base_run"]],
    }


# ---------------------------------------------------------------------------
# Derived-run finalization
# ---------------------------------------------------------------------------


def _fail(error_code: str, **extra: Any) -> dict[str, Any]:
    return {"status": "failed", "error_code": error_code, **extra}


def _verify_claim_identity(base_matches: Sequence[Mapping], assembled_matches: Sequence[Mapping]) -> str | None:
    """None when the assembled matches carry exactly the original claims in the
    original order with unchanged claim text/evidence/source ids; else a reason."""
    base_ids = [m.get("claim_id") for m in base_matches]
    new_ids = [m.get("claim_id") for m in assembled_matches]
    if base_ids != new_ids:
        return "claim ids or their order differ from the original run"
    for base, new in zip(base_matches, assembled_matches):
        for field in _CLAIM_ECHO_FIELDS:
            if base.get(field) != new.get(field):
                return f"claim {base.get('claim_id')!r}: field {field!r} differs from the original run"
    return None


def _claim_sources(
    base_matches: Sequence[Mapping],
    assembled_matches: Sequence[Mapping],
    declared: Mapping[str, str] | None,
) -> list[str]:
    out = []
    for base, new in zip(base_matches, assembled_matches):
        label = (declared or {}).get(str(base.get("claim_id")))
        if label is None:
            label = "unchanged_from_base" if base == new else "reclassified"
        out.append(label)
    return out


def build_claim_identity_map(
    base_run_id: str,
    execution_id: str,
    structured_records: Sequence[Mapping],
    base_matches: Sequence[Mapping],
    assembled_matches: Sequence[Mapping],
    declared_sources: Mapping[str, str] | None,
    cache_sources: Mapping[str, str] | None = None,
) -> list[dict[str, Any]]:
    """One entry per original claim: the original identity, the derived
    identity, and how the classification was obtained. ``claim_id`` /
    ``agent_output_id`` / ``source_agent_output_id`` are preserved verbatim
    (they embed the original run id by construction of the source run); only
    the ``run_id`` field is rebased."""
    records_by_id = {r.get("claim_id"): r for r in structured_records if isinstance(r, Mapping)}
    labels = _claim_sources(base_matches, assembled_matches, declared_sources)
    entries = []
    for base, new, label in zip(base_matches, assembled_matches, labels):
        claim_id = base.get("claim_id")
        record = records_by_id.get(claim_id) or {}
        entries.append({
            "claim_id": claim_id,
            "agent_output_id": record.get("agent_output_id"),
            "source_agent_output_id": base.get("source_agent_output_id"),
            "original_run_id": base_run_id,
            "derived_run_id": execution_id,
            "classification_source": label,
            "cache_source_call_id": (cache_sources or {}).get(claim_id),
            "original_alpha_match_method": base.get("alpha_match_method"),
            "derived_alpha_match_method": new.get("alpha_match_method"),
            "original_matched_alpha": base.get("matched_alpha"),
            "derived_matched_alpha": new.get("matched_alpha"),
            "original_fallback_reason": base.get("alpha_match_fallback_reason"),
            "derived_fallback_reason": new.get("alpha_match_fallback_reason"),
        })
    return entries


def _refuse_fake_under_real_runs(origin: Any, output_root: Any) -> None:
    if origin != CHECKPOINT_ORIGIN_FAKE:
        return
    try:
        Path(output_root).resolve().relative_to(_REAL_RUNS_DIR)
    except ValueError:
        return
    raise RuntimeError(
        f"refusing to write a fake-HTTP recovery under the real runs directory {_REAL_RUNS_DIR}"
    )


def finalize_classification_recovery_execution(
    base_run_id: str,
    execution_id: str,
    *,
    assembled_alpha_matches: Mapping[str, Any],
    recovery_provenance: Mapping[str, Any] | None = None,
    output_root: Any = "outputs/runs",
    graph_repository: Any = None,
    run_pipeline: Callable[..., Any] | None = None,
    execution_type: str = RECOVERY_EXECUTION_TYPE,
    execution_mode: str = RECOVERY_EXECUTION_MODE,
    lineage_filename: str = RECOVERY_LINEAGE_FILENAME,
    assembled_transformation: str = "assembled_from_recovery",
    root_run_id: str | None = None,
    lineage_extras: Mapping[str, Any] | None = None,
    artifact_transforms: Mapping[str, Callable[[Any], tuple[Any, dict[str, Any]]]] | None = None,
    metadata_extras: Mapping[str, Any] | None = None,
) -> dict[str, Any]:
    """Builds and completes the derived run. Returns a status dict; never
    raises for an input problem. The original run directory is only read --
    its file hashes are recorded before anything is written and compared again
    at the end (``base_run_unchanged``).

    ``execution_id`` may already exist as a directory (the recovery Gateway
    writes its request/response audit and semantic-call ledger there); a
    directory that already holds ``recovery_lineage.json`` is refused, so a
    finalized execution is never overwritten.

    ``run_pipeline`` is a test seam; production passes nothing and gets
    ``routes_research._run_week3_graph_pipeline``.
    """
    from comqutor_alpha.api import routes_research as rr
    from comqutor_alpha.research_lifecycle import _pipeline_identity, mark_research_run_failed_consistently

    provenance = dict(recovery_provenance or {})
    try:
        safe_base = validate_run_id_for_path(base_run_id)
        safe_execution = validate_run_id_for_path(execution_id)
    except ValueError:
        return _fail("INVALID_RUN_ID", base_run_id=str(base_run_id), execution_id=str(execution_id))
    if safe_base == safe_execution:
        return _fail("RECOVERY_EXECUTION_ID_EQUALS_BASE", base_run_id=safe_base)
    _refuse_fake_under_real_runs(provenance.get("checkpoint_origin"), output_root)

    base_dir = run_dir_for(safe_base, output_root)
    if not base_dir.is_dir():
        return _fail("BASE_RUN_NOT_FOUND", base_run_id=safe_base)
    execution_dir = run_dir_for(safe_execution, output_root)
    if (execution_dir / lineage_filename).exists():
        return _fail("RECOVERY_EXECUTION_ALREADY_FINALIZED", execution_id=safe_execution)

    base_hashes_before = snapshot_directory_hashes(base_dir)
    root_dir = run_dir_for(validate_run_id_for_path(root_run_id), output_root) if root_run_id else None
    root_hashes_before = snapshot_directory_hashes(root_dir) if root_dir is not None and root_dir.is_dir() else None
    try:
        metadata = load_json_record(safe_base, "metadata.json", output_root=output_root)
        base_alpha_matches = load_json_record(safe_base, "alpha_matches.json", output_root=output_root)
        loaded = {
            name: load_json_record_if_exists(safe_base, name, output_root=output_root)
            for name in _REBASED_COPIES
        }
    except Exception:
        return _fail("AGENT_OUTPUTS_NOT_READY", base_run_id=safe_base)
    missing = [name for name in _REQUIRED_COPIES if not loaded.get(name)]
    if missing:
        return _fail("AGENT_OUTPUTS_NOT_READY", base_run_id=safe_base, missing=missing)

    base_matches = base_alpha_matches.get("matches") or []
    assembled_matches = assembled_alpha_matches.get("matches") or []
    problem = _verify_claim_identity(base_matches, assembled_matches)
    if problem:
        return _fail("RECOVERY_IDENTITY_NOT_PRESERVED", detail=problem)

    rebased: dict[str, Any] = {}
    for name in _REBASED_COPIES:
        payload = loaded.get(name)
        if payload:
            rebased[name] = rebase_run_id(payload, base_run_id=safe_base, execution_id=safe_execution)
    # Declared, verified transforms (Round 18): each takes the already run_id-rebased copy and returns
    # (new payload, info). The transform must itself prove that the payload is unchanged apart from its
    # declared additions (info["content_equal_apart_from_declared_additions"]); otherwise nothing is written.
    transform_infos: dict[str, Any] = {}
    for name, transform in (artifact_transforms or {}).items():
        if name not in rebased:
            return _fail("RECOVERY_TRANSFORM_TARGET_MISSING", artifact=name)
        rebased[name], info = transform(rebased[name])
        transform_infos[name] = info
        if not info.get("content_equal_apart_from_declared_additions"):
            return _fail("RECOVERY_TRANSFORM_CHANGED_CONTENT", artifact=name, info=info)
    rebased_matches = rebase_run_id(
        assembled_alpha_matches, base_run_id=safe_base, execution_id=safe_execution
    )
    residual = {
        name: _count_run_id_fields_equal_to(payload, safe_base)
        for name, payload in {**rebased, "alpha_matches.json": rebased_matches}.items()
    }
    if any(residual.values()):
        return _fail("RECOVERY_RUN_ID_REBASE_INCOMPLETE", residual_base_run_id_fields=residual)

    artifact_records = {}
    for name in _REBASED_COPIES:
        if name in rebased:
            transformed = transform_infos.get(name)
            artifact_records[name] = {
                "transformation": "run_id_rebased" + (f"+{transformed['transformation']}" if transformed else ""),
                "original_sha256": _sha256_file(base_dir / name),
                # A declared transform changes the content on purpose; its own proof replaces this comparison.
                "content_equal_modulo_run_id": None if transformed else (
                    _normalized_content_sha256(loaded[name], (safe_base, safe_execution))
                    == _normalized_content_sha256(rebased[name], (safe_base, safe_execution))
                ),
                **({"declared_transform": transformed} if transformed else {}),
            }
    artifact_records["alpha_matches.json"] = {
        "transformation": assembled_transformation,
        "original_sha256": _sha256_file(base_dir / "alpha_matches.json"),
        "content_equal_modulo_run_id": None,
    }
    if not all(
        record["content_equal_modulo_run_id"] is not False for record in artifact_records.values()
    ):
        return _fail("RECOVERY_COPY_CONTENT_CHANGED", artifacts=artifact_records)

    triggered_at = _utc_timestamp()
    execution_metadata = {
        **metadata,
        "run_id": safe_execution,
        "based_on_run_id": safe_base,
        "execution_type": execution_type,
        "lineage_artifact": lineage_filename,
        **({"root_research_run_id": root_run_id} if root_run_id else {}),
        "based_on_created_at": metadata.get("created_at"),
        "created_at": triggered_at,
        "triggered_at": triggered_at,
        "recovery_origin": provenance.get("checkpoint_origin"),
        "input_alpha_matches_sha256": artifact_records["alpha_matches.json"]["original_sha256"],
        # T1 closure: run-level contract markers the production pipeline reads (e.g. fact_dependency_contract).
        **(dict(metadata_extras) if metadata_extras else {}),
    }
    execution_dir.mkdir(parents=True, exist_ok=True)
    save_json_record(safe_execution, "metadata.json", execution_metadata, output_root=output_root)
    for name, payload in rebased.items():
        save_json_record(safe_execution, name, payload, output_root=output_root)
    save_json_record(safe_execution, "alpha_matches.json", rebased_matches, output_root=output_root)

    identity_map = build_claim_identity_map(
        safe_base,
        safe_execution,
        rebased["structured_agent_outputs.json"].get("records") or [],
        base_matches,
        assembled_matches,  # still carries the original run id, so unchanged claims compare equal
        provenance.get("claim_sources"),
        provenance.get("claim_cache_sources"),
    )
    source_counts: dict[str, int] = {}
    for entry in identity_map:
        source_counts[entry["classification_source"]] = source_counts.get(entry["classification_source"], 0) + 1
    for name, record in artifact_records.items():
        record["derived_sha256"] = _sha256_file(execution_dir / name)
    lineage = {
        "schema_version": RECOVERY_LINEAGE_SCHEMA_VERSION,
        "run_id": safe_execution,
        "ticker": metadata.get("ticker"),
        "execution_id": safe_execution,
        "based_on_run_id": safe_base,
        "execution_type": execution_type,
        **({"root_research_run_id": root_run_id,
            "lineage_chain": [{"run_id": safe_execution, "role": "this_execution"},
                              {"run_id": safe_base, "role": "direct_parent"},
                              {"run_id": root_run_id, "role": "original_research_run"}],
            "root_run_file_hashes_at_derivation": root_hashes_before} if root_run_id else {}),
        **(dict(lineage_extras) if lineage_extras else {}),
        "created_at": triggered_at,
        "identity_rule": (
            "claim_id, agent_output_id, source_agent_output_id, claim text, evidence, source links and "
            "verification bindings are preserved verbatim from the original run; only run_id fields "
            "equal to the original run id are rewritten to this execution id"
        ),
        "claim_count": len(identity_map),
        "classification_source_counts": source_counts,
        "artifacts": artifact_records,
        "residual_original_run_id_fields": residual,
        **({"artifact_transforms": transform_infos} if transform_infos else {}),
        "original_run_file_hashes_at_derivation": base_hashes_before,
        "not_copied": [
            "original model-call ledgers and TradingAgents usage files (they describe the original run's own spend)",
            "downstream results (recomputed by the production pipeline in this execution)",
        ],
        "recovery": provenance,
        "claim_identity_map": identity_map,
    }
    save_json_record(safe_execution, lineage_filename, lineage, output_root=output_root)

    repository = graph_repository
    try:
        if repository is None:
            from comqutor_alpha.storage.db.repository import build_write_repository_from_env

            repository = build_write_repository_from_env(str(output_root))
        analysis_date = metadata.get("analysis_date")
        claim = repository.claim_research_run(
            run_id=safe_execution,
            request_fingerprint=hashlib.sha256(
                _canonical_json({
                    "execution_type": execution_type,
                    "based_on_run_id": safe_base,
                    "execution_id": safe_execution,
                }).encode("utf-8")
            ).hexdigest(),
            ticker=metadata.get("ticker"),
            analysis_date=str(analysis_date) if analysis_date is not None else None,
            selected_analysts=list(metadata.get("selected_analysts") or []),
            execution_mode=execution_mode,
            provider_identity=str(metadata.get("llm_provider") or "UNKNOWN")[:120],
            model_identity=str(metadata.get("quick_model") or "UNKNOWN")[:120],
            pipeline_identity=_pipeline_identity(),
            force_refresh=False,
        )
        if claim.get("disposition") != "created":
            return _fail("RECOVERY_RUN_CLAIM_NOT_CREATED", execution_id=safe_execution, disposition=claim.get("disposition"))
        repository.mark_research_run_running(safe_execution)
        repository.persist_agent_outputs(
            run_id=safe_execution,
            ticker=metadata.get("ticker"),
            structured_payload=rebased["structured_agent_outputs.json"],
        )
    except Exception as exc:  # noqa: BLE001 -- surfaced as a stable code, never raised
        return _fail("RECOVERY_RUN_REGISTRATION_FAILED", execution_id=safe_execution, exc_type=type(exc).__name__)

    pipeline = run_pipeline or rr._run_week3_graph_pipeline
    try:
        pipeline(execution_dir, graph_repository=repository, require_verified_evidence_gate=True)
    except Exception:  # noqa: BLE001
        mark_research_run_failed_consistently(
            repository, safe_execution, error_code="RECOVERY_EXECUTION_FAILED", error_message="Recovery execution failed."
        )
        return _fail("RECOVERY_EXECUTION_FAILED", execution_id=safe_execution)

    pipeline_status = load_json_record_if_exists(
        safe_execution, "week3_pipeline_status.json", output_root=output_root
    )
    base_unchanged = snapshot_directory_hashes(base_dir) == base_hashes_before
    root_unchanged = None if root_hashes_before is None else snapshot_directory_hashes(root_dir) == root_hashes_before
    if pipeline_status.get("outcome") != "success":
        mark_research_run_failed_consistently(
            repository, safe_execution, error_code="RECOVERY_EXECUTION_FAILED",
            error_message="Recovery pipeline did not succeed.",
        )
        return _fail(
            "RECOVERY_EXECUTION_FAILED",
            execution_id=safe_execution,
            pipeline_stage=pipeline_status.get("stage"),
            base_run_unchanged=base_unchanged,
            root_run_unchanged=root_unchanged,
        )

    response = rr.build_research_response(safe_execution, output_root=output_root, graph_repository=repository)
    result_status = response.get("status")
    if result_status in ("completed", "partial"):
        repository.mark_research_run_terminal(safe_execution, status=result_status)
    else:
        mark_research_run_failed_consistently(
            repository, safe_execution,
            error_code=str(response.get("error_code") or "RECOVERY_EXECUTION_FAILED"),
            error_message="Recovery run did not reach a completed state.",
        )
    return {
        "status": "ok" if result_status in ("completed", "partial") else "failed",
        "run_status": result_status,
        "execution_id": safe_execution,
        "based_on_run_id": safe_base,
        "claim_count": len(identity_map),
        "classification_source_counts": source_counts,
        "base_run_unchanged": base_unchanged,
        "root_run_unchanged": root_unchanged,
        "alpha_classification_status": response.get("alpha_classification_status"),
    }


__all__ = [
    "RECOVERY_EXECUTION_TYPE",
    "RECOVERY_EXECUTION_MODE",
    "RECOVERY_LINEAGE_FILENAME",
    "DEPENDENCY_EXECUTION_TYPE",
    "DEPENDENCY_EXECUTION_MODE",
    "DEPENDENCY_LINEAGE_FILENAME",
    "new_dependency_execution_id",
    "DIRECTION_EXECUTION_TYPE",
    "DIRECTION_EXECUTION_MODE",
    "DIRECTION_LINEAGE_FILENAME",
    "DIRECTION_RESULTS_FILENAME",
    "REQUALIFICATION_EXECUTION_TYPE",
    "REQUALIFICATION_EXECUTION_MODE",
    "REQUALIFICATION_LINEAGE_FILENAME",
    "REQUALIFICATION_RESULTS_FILENAME",
    "new_requalification_execution_id",
    "RECOVERY_LINEAGE_SCHEMA_VERSION",
    "STANCE_FOLLOWUP_MANIFEST_FILENAME",
    "STANCE_FOLLOWUP_MANIFEST_SCHEMA_VERSION",
    "ALPHA_CLASSIFIER_TASK",
    "STANCE_TASK",
    "RecoveryTaskNotAllowedError",
    "TaskAllowlistGateway",
    "new_recovery_execution_id",
    "snapshot_directory_hashes",
    "rebase_run_id",
    "build_claim_identity_map",
    "build_stance_followup_manifest",
    "finalize_classification_recovery_execution",
]
