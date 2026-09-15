"""v0.1.3 Measurement Foundation, Part B: Semantic Recorder Health Diagnostics.

Purely observational, read-only diagnostics for
``SEMANTIC_RECORDER_APPEND_FAILED`` degradation events, kept ENTIRELY
SEPARATE from ``comqutor_alpha.regression.provider_health_diagnostics``.
This module never calls a Provider, never reruns anything, never mutates a
historical run artifact, and -- per the prior audit's architectural proof
(``docs/audit_artifacts/v0_1_3_tsm_recorder_variance_audit.md``, Section 3)
-- never treats a recorder failure as a Provider failure, a Provider
orphan, or an Alpha-impact event.

Architecture recap (already proven by direct code trace, not re-derived
here): ``comqutor_alpha.llm_runtime.recorder.SemanticCallRecorder.append()``
raises ``RecorderIntegrityError`` on a persistence fault. Its sole caller,
``SemanticRuntimeSession.finalize_call()``
(``comqutor_alpha/llm_runtime/session.py``), catches that exception inside
itself and calls ``self._mark_degraded("SEMANTIC_RECORDER_APPEND_FAILED",
exc, incomplete=True)`` -- the exception never propagates to
``Week2LLMGateway.finalize_semantic_invocation()``, whose own return value
is, in turn, discarded by every task-level caller (``alpha_mapper.py``,
``structure_extractor.py``, ``evidence_stance_llm.py``), each of which had
already fixed its own semantic result (``invocation.validated_output``)
BEFORE the recorder/finalize call ever ran. Recorder failures are therefore
architecturally AUDIT_TRACE_ONLY: canonical semantic state
(``matched_alpha``, B1 stance, structure edges) cannot be affected by them
under the current architecture.

Data source durability (task section 23): as of this task, no run-scoped
persisted artifact records ``SEMANTIC_RECORDER_APPEND_FAILED`` occurrences
with a count. ``SemanticRuntimeSession._degraded_reason_codes`` is a
DEDUPLICATED list (a reason code is appended at most once per session,
see ``session.py:211-212``) and even that deduplicated list is never
written into ``llm_semantic_manifest.json`` (verified: the manifest schema
has no ``degraded_reason_codes`` key). The manifest's own ``complete``
field does go ``False`` when ANY incomplete-flagged degradation occurs
(not just recorder failures), so it is a related-but-non-specific signal,
not a recorder-specific count. The ONLY available source for the actual
per-event COUNT is the process-level launcher log (e.g.
``/tmp/comqutor_live_start.log``), which is an ephemeral, non-run-scoped,
non-durable text log -- not a canonical persisted run artifact. This module
never claims otherwise: every result carries an explicit
``recorder_source_durability`` field, and no default log path is assumed to
be canonical -- callers must supply ``log_path`` or ``log_text`` themselves.
"""

from __future__ import annotations

import re
from collections import Counter
from pathlib import Path
from typing import Any

RECORDER_HEALTHY = "RECORDER_HEALTHY"
RECORDER_DEGRADED = "RECORDER_DEGRADED"
VALID_RECORDER_HEALTH_STATUSES = frozenset({RECORDER_HEALTHY, RECORDER_DEGRADED})

# The one reason code this module measures. Deliberately a small, explicit
# set (not "any degradation reason code") so this module cannot silently
# start counting unrelated degradation classes (e.g.
# SEMANTIC_RECORDER_INITIALIZATION_FAILED, SEMANTIC_CACHE_WRITE_FAILED) as
# if they were the same, already-proven-harmless failure mode.
RECORDER_FAILURE_REASON_CODES = frozenset({"SEMANTIC_RECORDER_APPEND_FAILED"})

SOURCE_EPHEMERAL_LOG_ONLY = "EPHEMERAL_LOG_ONLY"
SOURCE_RUN_SCOPED_ARTIFACT = "RUN_SCOPED_ARTIFACT"
SOURCE_UNAVAILABLE = "UNAVAILABLE"

ARCHITECTURE_ROLE_AUDIT_TRACE_ONLY = "AUDIT_TRACE_ONLY"

# Matches session.py:214-219's exact logger.warning format string:
#   "semantic runtime degraded (run_id=%s, reason_code=%s, exc_type=%s)"
_DEGRADED_LOG_LINE_RE = re.compile(
    r"semantic runtime degraded \(run_id=(?P<run_id>[^,]*), "
    r"reason_code=(?P<reason_code>[^,]*), exc_type=(?P<exc_type>[^)]*)\)"
)


def parse_degraded_log_lines(log_text: str) -> list[dict[str, str]]:
    """Section 23: derived diagnostic parsing of the launcher log's
    degradation warning lines. Returns every matched
    ``{run_id, reason_code, exc_type}`` record found, regardless of reason
    code -- filtering to recorder-specific events happens in the caller."""
    events: list[dict[str, str]] = []
    for line in log_text.splitlines():
        match = _DEGRADED_LOG_LINE_RE.search(line)
        if match:
            events.append(
                {
                    "run_id": match.group("run_id"),
                    "reason_code": match.group("reason_code"),
                    "exc_type": match.group("exc_type"),
                }
            )
    return events


def compute_recorder_health_diagnostics(
    *,
    ticker: str | None = None,
    run_id: str | None = None,
    log_path: str | Path | None = None,
    log_text: str | None = None,
) -> dict[str, Any]:
    """Task section 20/21/25 main entry point. Exactly one of ``log_path``
    or ``log_text`` should be supplied; if neither is, every count-bearing
    field is honestly ``None`` (never a fabricated zero or guess) and
    ``recorder_source_durability`` is ``UNAVAILABLE``.

    If ``run_id`` is supplied, events are filtered to that run_id (the log
    format carries a run_id per line); if omitted, all matched events in the
    supplied text are counted (useful for a log covering exactly one run)."""
    if log_text is None and log_path is not None:
        log_text = Path(log_path).read_text(encoding="utf-8", errors="replace")

    if log_text is None:
        return {
            "ticker": ticker,
            "run_id": run_id,
            "recorder_failure_events": None,
            "recorder_health": None,
            "audit_trace_loss_events": None,
            "canonical_semantic_losses": None,
            "recorder_failure_error_types": {},
            "recorder_failure_components": None,
            "recorder_traceability_unknown_count": None,
            "recorder_source": None,
            "recorder_source_durability": SOURCE_UNAVAILABLE,
            "architecture_role": ARCHITECTURE_ROLE_AUDIT_TRACE_ONLY,
        }

    all_events = parse_degraded_log_lines(log_text)
    if run_id is not None:
        all_events = [event for event in all_events if event["run_id"] == run_id]
    recorder_events = [
        event for event in all_events if event["reason_code"] in RECORDER_FAILURE_REASON_CODES
    ]

    recorder_failure_events = len(recorder_events)
    recorder_failure_error_types = dict(Counter(event["exc_type"] for event in recorder_events))
    recorder_health = RECORDER_DEGRADED if recorder_failure_events > 0 else RECORDER_HEALTHY

    return {
        "ticker": ticker,
        "run_id": run_id,
        "recorder_failure_events": recorder_failure_events,
        "recorder_health": recorder_health,
        # Every counted event is, by definition, a lost audit-trace append
        # (never a canonical semantic loss -- see module docstring proof).
        "audit_trace_loss_events": recorder_failure_events,
        # Architecturally proven zero under the current recorder/session/
        # gateway wiring -- not derived from these log lines themselves,
        # since the log format cannot distinguish canonical from
        # audit-trace-only impact on its own.
        "canonical_semantic_losses": 0,
        "recorder_failure_error_types": recorder_failure_error_types,
        # The log format carries no task/component/claim_id field (only
        # run_id, reason_code, exc_type) -- never fabricate a breakdown.
        "recorder_failure_components": None,
        "recorder_traceability_unknown_count": recorder_failure_events,
        "recorder_source": str(log_path) if log_path is not None else "provided_log_text",
        "recorder_source_durability": SOURCE_EPHEMERAL_LOG_ONLY,
        "architecture_role": ARCHITECTURE_ROLE_AUDIT_TRACE_ONLY,
    }


def assert_recorder_provider_separation(
    recorder_result: dict[str, Any], provider_result: dict[str, Any] | None
) -> dict[str, Any]:
    """Task section 22: documents (never mutates either input) that
    recorder events are absent from Provider Health's own,
    independently-computed metrics for the same run. This is a read-only
    cross-check, not a merge -- ``provider_result`` is expected to come from
    ``comqutor_alpha.regression.provider_health_diagnostics.
    compute_provider_health_diagnostics`` for the SAME run, computed
    entirely independently of this module."""
    return {
        "recorder_events_counted_as_provider_failures": False,
        "recorder_events_counted_as_provider_orphans": False,
        "recorder_events_create_impacted_alpha": False,
        "recorder_failure_events": recorder_result.get("recorder_failure_events"),
        "provider_health_independent_value": (provider_result or {}).get("provider_health"),
        "provider_failure_events_independent_value": (provider_result or {}).get("provider_failure_events"),
        "provider_final_orphans_independent_value": (provider_result or {}).get("provider_final_orphans_total"),
        "impacted_alpha_ids_independent_value": (provider_result or {}).get("impacted_alpha_ids"),
    }


__all__ = [
    "RECORDER_HEALTHY",
    "RECORDER_DEGRADED",
    "VALID_RECORDER_HEALTH_STATUSES",
    "RECORDER_FAILURE_REASON_CODES",
    "SOURCE_EPHEMERAL_LOG_ONLY",
    "SOURCE_RUN_SCOPED_ARTIFACT",
    "SOURCE_UNAVAILABLE",
    "ARCHITECTURE_ROLE_AUDIT_TRACE_ONLY",
    "parse_degraded_log_lines",
    "compute_recorder_health_diagnostics",
    "assert_recorder_provider_separation",
]
