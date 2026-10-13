"""W4.3 Week 4 pipeline orchestration: wires the existing, unmodified W4.1
Conflict Detector and W4.2 persistence repository into the research
pipeline.

This module does not reimplement or alter any W4.1/W4.2 business logic --
it only sequences two already-frozen calls (``detect_alpha_conflicts`` then
``repository.persist_week4_results``) and translates any failure into a
safe, stable-reason-code log entry. Never raises: a Week 4 failure must
never take down or alter an already-successful Week 1-3 response (see
``docs/w4_3_gate_contract.md`` section 2).
"""

from __future__ import annotations

import json
import logging
from collections.abc import Mapping
from datetime import UTC, datetime
from typing import Any

from comqutor_alpha.conflict_engine.conflict_detector import detect_alpha_conflicts
from comqutor_alpha.graph_engine.evidence_consumption import EvidenceConsumptionError
from comqutor_alpha.graph_engine.verified_evidence_gate import EvidenceGateInputError
from comqutor_alpha.storage.file_store import atomic_write_text, run_dir_for

logger = logging.getLogger(__name__)

WEEK4_PIPELINE_ERROR_LOG_FILENAME = "week4_pipeline_errors.jsonl"
_WEEK4_PIPELINE_ERROR_CODE = "WEEK4_CONFLICT_PIPELINE_FAILED"


def _utc_timestamp() -> str:
    return datetime.now(UTC).replace(microsecond=0).isoformat().replace("+00:00", "Z")


def _log_week4_pipeline_error(run_id: str, output_root: Any, stage: str) -> None:
    """Append a safe audit record: run_id/stage/stable error_code/timestamp
    only -- never the triggering exception's text, type, or traceback, a
    DSN, a host, credentials, a local absolute path, raw agent output, or a
    provider response. This is the only thing ever recorded for a Week 4
    pipeline stage failure.

    Deliberately bypasses ``file_store.append_jsonl_record``'s artifact-path
    allowlist (which does not include this new path) rather than widening
    that shared allowlist -- ``file_store.py`` is out of scope for this
    task. Reuses ``file_store``'s own atomic-write primitive instead of
    hand-rolling file I/O.
    """
    run_dir = run_dir_for(run_id, output_root)
    path = run_dir / "error_logs" / WEEK4_PIPELINE_ERROR_LOG_FILENAME
    existing = path.read_text(encoding="utf-8") if path.exists() else ""
    record = {
        "run_id": run_id,
        "stage": stage,
        "error_code": _WEEK4_PIPELINE_ERROR_CODE,
        "created_at": _utc_timestamp(),
    }
    line = json.dumps(record, ensure_ascii=False) + "\n"
    atomic_write_text(path, existing + line, encoding="utf-8")
    logger.warning("week4 pipeline stage failed (run_id=%s, stage=%s)", run_id, stage)


def run_week4_conflict_pipeline(
    *,
    run_id: str,
    ticker: str,
    graph_payload: Mapping[str, Any],
    alpha_matches_payload: Mapping[str, Any],
    repository: Any,
    output_root: Any,
    structured_records: Any = None,
    sources: list[dict[str, Any]] | None = None,
    require_verified_evidence_gate: bool = False,
) -> bool:
    """Detect and persist this run's Week 4 conflicts. Returns True on
    success, False on a safely-logged failure. Never raises.

    Only ever called after Week 3 has already built, scored, and persisted
    the Structure Graph for this run -- the caller is responsible for that
    ordering (see ``routes_research._run_week3_graph_pipeline``). Does not
    recompute activation: consumes ``graph_payload["activation"]`` exactly
    as Week 3 produced it in this same request -- Week 3 has already made
    that the OFFICIAL (verified-primary, when the gate applies) view, so no
    separate "verified activation" is threaded here. Does not write a
    ``conflicts.json`` artifact -- the W4.2 database row is the only source
    of truth for W4.3 conflicts.

    ``structured_records``/``sources`` (T1 verified-support eligibility
    gate; escalated 2026-09-28 from "additive diagnostic" to "official
    result"): OPTIONAL, forwarded unchanged to ``detect_alpha_conflicts``
    -- see that function's own docstring for how they make ADMITTED/
    conflicts/main_conflict itself gate-filtered. Omitting them (every
    pre-existing caller) computes exactly today's original behavior.

    ``require_verified_evidence_gate`` (2026-09-28 closing fix): OPTIONAL,
    default ``False``, forwarded unchanged to ``detect_alpha_conflicts``.
    Must be the SAME value the caller passed to this same run's
    ``graph_engine.pipeline.score_and_assemble_structure_graph`` call, so
    Activation and conflict admissibility can never diverge (one gated, the
    other not). A resulting
    :class:`~comqutor_alpha.graph_engine.verified_evidence_gate.
    EvidenceGateInputError` is still caught here like any other failure
    (this function's own "never raises" contract is unchanged) but logged
    under the distinct ``evidence_gate_required_input_unavailable`` stage
    rather than the generic ``conflict_detection`` one.
    """
    activation_payload = graph_payload.get("activation") if isinstance(graph_payload, Mapping) else None
    # When Week 3 escalated to a verified-primary official result, its own
    # activation_versions["v2"] is the TRUE raw view (pre-exposure/
    # classification for this run) -- passed through only so
    # detect_alpha_conflicts's diagnostic-only comparison field can score
    # like-for-like against the raw pipeline; never consulted for the
    # official result itself.
    activation_versions = graph_payload.get("activation_versions") if isinstance(graph_payload, Mapping) else None
    activation_payload_diagnostic_raw = (
        activation_versions.get("v2")
        if isinstance(activation_versions, Mapping) and graph_payload.get("evidence_gate_applied")
        else None
    )
    matches = alpha_matches_payload.get("matches") if isinstance(alpha_matches_payload, Mapping) else None
    if not isinstance(matches, list):
        matches = []

    try:
        conflict_payload = detect_alpha_conflicts(
            run_id=run_id,
            ticker=ticker,
            activation_payload=activation_payload,
            alpha_matches=matches,
            structured_records=structured_records,
            sources=sources,
            activation_payload_diagnostic_raw=activation_payload_diagnostic_raw,
            require_verified_evidence_gate=require_verified_evidence_gate,
        )
    except EvidenceGateInputError:
        _log_week4_pipeline_error(run_id, output_root, "evidence_gate_required_input_unavailable")
        return False
    except EvidenceConsumptionError as exc:
        # an invalid consumption block (unknown contract version, ticker/pair mismatch, stale binding): its own stage code
        _log_week4_pipeline_error(run_id, output_root, f"evidence_consumption:{exc.reason_code}")
        return False
    except Exception:
        _log_week4_pipeline_error(run_id, output_root, "conflict_detection")
        return False

    try:
        repository.persist_week4_results(
            run_id=run_id,
            ticker=ticker,
            activation_payload=activation_payload,
            conflict_payload=conflict_payload,
        )
    except Exception:
        _log_week4_pipeline_error(run_id, output_root, "conflict_persistence")
        return False

    return True


__all__ = ["run_week4_conflict_pipeline", "WEEK4_PIPELINE_ERROR_LOG_FILENAME"]
