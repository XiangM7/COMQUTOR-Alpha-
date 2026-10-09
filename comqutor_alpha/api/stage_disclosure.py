"""Stage completion / degradation disclosure of one run (T4 round 32, 2026-10-09).

``build_stage_disclosure`` reads only what the run already saved -- the semantic call ledger
(``llm_semantic_calls.jsonl``), ``structured_agent_outputs.json``, ``extracted_structures.json``,
``structure_graph.json``, ``alpha_matches.json`` and the Week 3 status marker -- and reports, per model-assisted
stage, how many calls produced a result that was used, how many fell back and why, and which fields therefore come
from deterministic processing rather than a model judgment. Nothing is recomputed and no status is changed: a run's
``completed`` status keeps its existing meaning (flow finished, Alpha classification without call failures); this
block is what tells a reader which sub-steps were degraded.

Ground truth for "sent or not" is the ledger itself (``request_attempts`` empty + ``WEEK2_LLM_INPUT_TOO_LARGE``),
so a historical record whose fallback label predates the round-32 fix is still disclosed correctly here without
rewriting it. A run without a ledger is reported as ``not_recorded`` -- never as complete.
"""

from __future__ import annotations

import json
import threading
from collections import Counter
from pathlib import Path
from typing import Any

SCHEMA_VERSION = "comqutor.stage_disclosure.v1"
STAGE_DISCLOSURE_FILENAME = "stage_disclosure.json"
LEDGER_FILENAME = "llm_semantic_calls.jsonl"

STATUS_MODEL_COMPLETE = "model_complete"  # every call produced a model result that was used
STATUS_DEGRADED = "degraded"  # some calls fell back / were not accepted
STATUS_MODEL_NOT_USED = "model_not_used"  # no call produced a used model result
STATUS_NOT_RUN = "not_run"  # the stage made no model call
STATUS_NOT_RECORDED = "not_recorded"  # the run saved no ledger to tell

_ADAPTER_FIELDS = ["entities", "factors", "direction", "confidence", "cited_source_id"]
_INPUT_FILES = ("llm_semantic_calls.jsonl", "structured_agent_outputs.json", "extracted_structures.json", "structure_graph.json",
                "week3_pipeline_status.json")
_cache_lock = threading.Lock()
_cache: dict[str, tuple[tuple, dict[str, Any]]] = {}  # run dir -> (input files' (size, mtime_ns), disclosure)


def _load_json(path: Path) -> Any:
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return None


def _load_ledger(run_dir: Path) -> list[dict[str, Any]] | None:
    path = run_dir / LEDGER_FILENAME
    if not path.is_file():
        return None
    records = []
    try:
        for line in path.read_text(encoding="utf-8").splitlines():
            if line.strip():
                value = json.loads(line)
                if isinstance(value, dict):
                    records.append(value)
    except (OSError, ValueError):
        return None
    return records


def _outcome(record: dict[str, Any]) -> str:
    """One logical call's outcome from its own ledger fields."""
    attempts = record.get("request_attempts") or []
    cache = record.get("cache") or {}
    if record.get("validation_status") == "accepted" and not record.get("fallback_used"):
        return "used_from_cache" if cache.get("hit") and not attempts else "used"
    if not attempts and not cache.get("hit"):
        code = record.get("error_code")
        if code == "WEEK2_LLM_INPUT_TOO_LARGE":
            return "not_sent_input_too_large"
        if code == "WEEK2_LLM_RUN_STOPPED_AFTER_PROVIDER_REFUSAL":
            return "not_sent_provider_stopped"
        if record.get("provider_status") == "budget_exhausted" or code == "WEEK2_LLM_CALL_BUDGET_EXHAUSTED":
            return "not_sent_budget_exhausted"
        return f"not_sent:{code or 'unknown'}"
    status = record.get("provider_status")
    if status == "timeout":
        return "timeout"
    if status == "provider_error":
        return "provider_error"
    reason = str(record.get("fallback_reason") or record.get("error_code") or "rejected")
    if reason == "WEEK2_LLM_EMPTY_RESULT_FALLBACK":
        return "valid_empty_result_not_used"
    return f"reply_not_accepted:{reason}"


def _stage_status(outcomes: Counter, *, used_keys: tuple[str, ...] = ("used", "used_from_cache")) -> str:
    total = sum(outcomes.values())
    if total == 0:
        return STATUS_NOT_RUN
    used = sum(outcomes.get(key, 0) for key in used_keys)
    if used == total:
        return STATUS_MODEL_COMPLETE
    return STATUS_MODEL_NOT_USED if used == 0 else STATUS_DEGRADED


def _task_block(ledger: list[dict[str, Any]], task: str) -> tuple[list[dict[str, Any]], Counter]:
    calls = [r for r in ledger if r.get("task") == task]
    return calls, Counter(_outcome(r) for r in calls)


def _http_requests(calls: list[dict[str, Any]]) -> int:
    return sum(len(r.get("request_attempts") or []) for r in calls)


def _outcome_phrase(outcomes: Counter) -> str:
    labels = {
        "timeout": "timed out",
        "not_sent_input_too_large": "not sent (input over the local size limit)",
        "not_sent_provider_stopped": "not sent (run stopped after a provider refusal)",
        "not_sent_budget_exhausted": "not sent (call budget exhausted)",
        "provider_error": "failed at the provider",
        "valid_empty_result_not_used": "returned a valid empty result, deterministic processing used instead",
    }
    parts = []
    for key, count in sorted(outcomes.items()):
        if key in ("used", "used_from_cache"):
            continue
        if key.startswith("reply_not_accepted:"):
            parts.append(f"{count} reply not accepted ({key.split(':', 1)[1]})")
        else:
            parts.append(f"{count} {labels.get(key, key)}")
    return ", ".join(parts)


def build_stage_disclosure(run_dir: str | Path) -> dict[str, Any]:
    """Cached per run directory and invalidated whenever one of the input files changes (the page polls this)."""
    run_dir = Path(run_dir)
    key = str(run_dir.resolve())
    stamp = tuple((p.stat().st_size, p.stat().st_mtime_ns) if p.is_file() else None for p in (run_dir / n for n in _INPUT_FILES))
    with _cache_lock:
        hit = _cache.get(key)
        if hit is not None and hit[0] == stamp:
            return json.loads(json.dumps(hit[1]))
    disclosure = _build_stage_disclosure(run_dir)
    with _cache_lock:
        _cache[key] = (stamp, disclosure)
    return json.loads(json.dumps(disclosure))


def _build_stage_disclosure(run_dir: Path) -> dict[str, Any]:
    ledger = _load_ledger(run_dir)
    structured = _load_json(run_dir / "structured_agent_outputs.json") or {}
    extracted = _load_json(run_dir / "extracted_structures.json") or {}
    graph = _load_json(run_dir / "structure_graph.json") or {}
    week3 = _load_json(run_dir / "week3_pipeline_status.json") or {}
    meta = structured.get("metadata") if isinstance(structured, dict) else None
    meta = meta if isinstance(meta, dict) else {}

    if ledger is None:
        return {
            "schema_version": SCHEMA_VERSION,
            "source": "not_recorded: this run saved no semantic call ledger",
            "stages": [],
            "degraded_stages": [],
            "notes": ["This run saved no semantic call ledger, so sub-step completion cannot be disclosed (not recorded)."],
        }

    stages: list[dict[str, Any]] = []
    notes: list[str] = []

    # --- claim enrichment (structured_adapter) ---------------------------------------------------------------------
    calls, outcomes = _task_block(ledger, "structured_adapter")
    segments = sum(len((r.get("input_payload") or {}).get("segments") or []) for r in calls)
    used_segments = sum(len((r.get("input_payload") or {}).get("segments") or []) for r in calls if _outcome(r).startswith("used"))
    methods = Counter(str(r.get("extraction_method")) for r in structured.get("records") or [] if isinstance(r, dict))
    status = _stage_status(outcomes)
    stage = {
        "stage": "claim_enrichment",
        "task": "structured_adapter",
        "status": status,
        "calls": len(calls),
        "http_requests": _http_requests(calls),
        "outcomes": dict(sorted(outcomes.items())),
        "segments_in_calls": segments,
        "segments_with_model_result_used": used_segments,
        "record_extraction_methods": dict(sorted(methods.items())),
        "fields_from_model": _ADAPTER_FIELDS if status == STATUS_MODEL_COMPLETE else ([] if status == STATUS_MODEL_NOT_USED else "mixed: see record_extraction_methods"),
        "fields_from_deterministic_processing": _ADAPTER_FIELDS if status in (STATUS_MODEL_NOT_USED, STATUS_NOT_RUN) else ([] if status == STATUS_MODEL_COMPLETE else "mixed: see record_extraction_methods"),
    }
    stages.append(stage)
    if status not in (STATUS_MODEL_COMPLETE, STATUS_NOT_RUN):
        notes.append(
            f"Claim enrichment: {len(calls) - sum(outcomes.get(k, 0) for k in ('used', 'used_from_cache'))} of {len(calls)} batches "
            f"did not use a model result ({_outcome_phrase(outcomes)}); for those claims entities, factors, direction, "
            "confidence and cited source come from deterministic extraction, not from a model judgment "
            "(a direction of 'unknown' there means 'not judged', not a model answer)."
        )

    # --- content support verification -------------------------------------------------------------------------------
    calls, outcomes = _task_block(ledger, "content_support_verification")
    status = _stage_status(outcomes)
    stages.append({
        "stage": "content_support_verification",
        "task": "content_support_verification",
        "status": status,
        "calls": len(calls),
        "claims_in_calls": sum(len(r.get("claim_ids") or []) for r in calls),
        "http_requests": _http_requests(calls),
        "outcomes": dict(sorted(outcomes.items())),
    })
    if status not in (STATUS_MODEL_COMPLETE, STATUS_NOT_RUN):
        notes.append(
            f"Content support verification: {sum(outcomes.get(k, 0) for k in ('used', 'used_from_cache'))} of {len(calls)} "
            f"requested verifications produced an accepted model result ({_outcome_phrase(outcomes)}); the others stay "
            "pending review -- a technical failure or a request that was never sent is not a judgment that the claim is unsupported."
        )

    # --- Alpha classification ----------------------------------------------------------------------------------------
    calls, outcomes = _task_block(ledger, "alpha_classifier")
    status = _stage_status(outcomes)
    stages.append({
        "stage": "alpha_classification",
        "task": "alpha_classifier",
        "status": status,
        "calls": len(calls),
        "http_requests": _http_requests(calls),
        "outcomes": dict(sorted(outcomes.items())),
    })
    if status not in (STATUS_MODEL_COMPLETE, STATUS_NOT_RUN):
        failed = len(calls) - sum(outcomes.get(k, 0) for k in ("used", "used_from_cache"))
        notes.append(
            f"Alpha classification: {failed} of {len(calls)} claims have no usable classification ({_outcome_phrase(outcomes)}); "
            "they are never counted as 'no Alpha'."
        )

    # --- evidence stance --------------------------------------------------------------------------------------------
    calls, outcomes = _task_block(ledger, "evidence_stance_classifier")
    status = _stage_status(outcomes)
    stages.append({
        "stage": "evidence_stance",
        "task": "evidence_stance_classifier",
        "status": status,
        "calls": len(calls),
        "items_in_calls": sum(len((r.get("input_payload") or {}).get("items") or []) for r in calls),
        "http_requests": _http_requests(calls),
        "outcomes": dict(sorted(outcomes.items())),
    })
    if status not in (STATUS_MODEL_COMPLETE, STATUS_NOT_RUN):
        failed = len(calls) - sum(outcomes.get(k, 0) for k in ("used", "used_from_cache"))
        notes.append(f"Evidence stance: {failed} of {len(calls)} batches without a used model result ({_outcome_phrase(outcomes)}); "
                     "those items keep the deterministic rule stance.")

    # --- structure extraction and the graph (kept separate) ---------------------------------------------------------
    calls, outcomes = _task_block(ledger, "structure_extractor")
    status = _stage_status(outcomes)
    xmeta = extracted.get("metadata") if isinstance(extracted, dict) else None
    xmeta = xmeta if isinstance(xmeta, dict) else {}
    edges_by_source = {
        "model_structure_extraction": xmeta.get("llm_edge_count"),
        "deterministic_grammar": xmeta.get("deterministic_edge_count"),
        "tradingagents_canonical_relations": xmeta.get("canonical_relation_edge_count"),
    }
    stages.append({
        "stage": "structure_extraction",
        "task": "structure_extractor",
        "status": status,
        "calls": len(calls),
        "http_requests": _http_requests(calls),
        "outcomes": dict(sorted(outcomes.items())),
        "extracted_edges_by_source": edges_by_source,
    })
    if status not in (STATUS_MODEL_COMPLETE, STATUS_NOT_RUN):
        notes.append(
            f"Structure extraction: {len(calls) - sum(outcomes.get(k, 0) for k in ('used', 'used_from_cache'))} of {len(calls)} "
            f"model calls contributed no edge ({_outcome_phrase(outcomes)}); extracted edges by source: "
            f"model {edges_by_source['model_structure_extraction']}, deterministic grammar {edges_by_source['deterministic_grammar']}, "
            f"TradingAgents canonical relations {edges_by_source['tradingagents_canonical_relations']}."
        )
    metrics = graph.get("graph_metrics") if isinstance(graph, dict) else None
    metrics = metrics if isinstance(metrics, dict) else {}
    built = bool(graph) and week3.get("outcome") == "success"
    stages.append({
        "stage": "structure_graph",
        "task": None,
        "status": "built" if built else "not_built",
        "nodes": metrics.get("node_count"),
        "edges": metrics.get("edge_count"),
        "note": "Graph construction finishing is separate from model structure extraction succeeding; see structure_extraction.",
    })

    degraded = [s["stage"] for s in stages if s["status"] in (STATUS_DEGRADED, STATUS_MODEL_NOT_USED)]
    return {
        "schema_version": SCHEMA_VERSION,
        "source": f"{LEDGER_FILENAME} and the run's saved stage artifacts (read-only; nothing recomputed)",
        "llm_record_count": meta.get("llm_record_count"),
        "stages": stages,
        "degraded_stages": degraded,
        "notes": notes,
    }


__all__ = ["LEDGER_FILENAME", "SCHEMA_VERSION", "STAGE_DISCLOSURE_FILENAME", "build_stage_disclosure"]
