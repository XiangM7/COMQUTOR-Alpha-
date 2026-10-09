"""Run-scoped stop after a provider authentication / permission / rate-limit refusal (2026-10-08, T4 round 28).

The first HTTP 401, 403 or 429 that any model request of a research run receives -- on either LLM layer, the
TradingAgents research agents or the Week 2 semantic gateway -- stops that run's further model requests:

* the refusal is recorded once: status code, layer, task, call / attempt identity, time and a redacted reason;
* every later request of the same run is checked immediately before it would be sent and is refused unsent
  (``RunProviderStopped`` on the research-agent layer; a ``not_called`` gateway result carrying
  ``STOP_ERROR_CODE`` on the Week 2 layer, which every task maps to "not sent", never to a valid NONE);
* requests already on the wire when the stop was triggered finish and keep their own responses; they are listed
  as in flight at the stop;
* nothing is retried, resumed after a wait, or re-sent with another model or credential.

The state is one object per run_id (``run_provider_stop``). Its lock guards only the in-memory state and the small
artifact write -- never a network wait -- so concurrent requests of the same run still overlap, and another run's
state is a different object. ``provider_stop.json`` (atomic write) is saved in the run directory once a directory is
attached.
"""

from __future__ import annotations

import json
import logging
import os
import re
import tempfile
import threading
from collections import Counter
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

logger = logging.getLogger(__name__)

SCHEMA_VERSION = "comqutor.provider_stop.v1"
ARTIFACT_FILENAME = "provider_stop.json"
STOP_STATUS_CODES = frozenset({401, 403, 429})
STOP_ERROR_CODE = "WEEK2_LLM_RUN_STOPPED_AFTER_PROVIDER_REFUSAL"
STOP_FALLBACK_REASON = "provider_stopped"
LAYER_RESEARCH_AGENT = "research_agent"
LAYER_WEEK2 = "week2_semantic"

_SECRET_PATTERNS = (
    re.compile(r"sk-[A-Za-z0-9_\-]{6,}"),
    re.compile(r"(?i)bearer\s+[A-Za-z0-9._\-]+"),
    re.compile(r"(?i)\b(api[_-]?key|authorization|x-api-key|token)\b\s*[=:]\s*['\"]?[^\s'\",}]+"),
)
_MAX_REASON_CHARS = 500


class RunProviderStopped(Exception):
    """Raised in place of a research-agent request that would have been sent after the run was stopped."""

    def __init__(self, trigger: dict[str, Any]) -> None:
        self.trigger = dict(trigger)
        super().__init__(
            f"run stopped after provider HTTP {trigger.get('status_code')} on {trigger.get('layer')}:{trigger.get('task')}"
        )


def provider_status_code(exc: BaseException | None, *, max_depth: int = 5) -> int | None:
    """HTTP status code carried by a provider exception (``status_code`` on the exception or its ``response``),
    following ``__cause__`` / ``__context__`` -- the client libraries wrap one another's errors."""
    current, depth = exc, 0
    while current is not None and depth < max_depth:
        for candidate in (current, getattr(current, "response", None)):
            value = getattr(candidate, "status_code", None)
            if isinstance(value, int) and not isinstance(value, bool):
                return value
        current = current.__cause__ or current.__context__
        depth += 1
    return None


def redact_reason(text: Any) -> str | None:
    if text is None:
        return None
    value = str(text)
    for pattern in _SECRET_PATTERNS:
        value = pattern.sub("[REDACTED]", value)
    return value[:_MAX_REASON_CHARS]


def _now() -> str:
    return datetime.now(UTC).isoformat()


class RunProviderStop:
    def __init__(self, run_id: str) -> None:
        self.run_id = str(run_id)
        self._lock = threading.Lock()
        self._trigger: dict[str, Any] | None = None
        self._refused: Counter = Counter()
        self._in_flight: list[dict[str, Any]] = []
        self._artifact_dir: Path | None = None
        self._dirty = False  # changed since the last write of provider_stop.json

    @property
    def triggered(self) -> dict[str, Any] | None:
        with self._lock:
            return dict(self._trigger) if self._trigger is not None else None

    def attach_artifact_dir(self, directory: Any) -> None:
        with self._lock:
            self._artifact_dir = Path(directory)
            stopped = self._trigger is not None
        if stopped:
            self.persist()

    def trigger(self, *, status_code: int, layer: str, task: Any, call_id: Any = None, attempt_id: Any = None,
                reason: Any = None) -> bool:
        """Record the first refusal; later calls (another concurrent refusal, the same refusal seen again at a
        second layer of the client stack) change nothing. Returns True only for the first."""
        with self._lock:
            if self._trigger is not None:
                return False
            self._trigger = {
                "status_code": int(status_code),
                "layer": str(layer),
                "task": None if task is None else str(task),
                "call_id": None if call_id is None else str(call_id),
                "attempt_id": None if attempt_id is None else str(attempt_id),
                "at": _now(),
                "reason_redacted": redact_reason(reason),
            }
            self._dirty = True
        logger.error("provider refusal stops run %s: HTTP %s on %s:%s", self.run_id, status_code, layer, task)
        self.persist()
        return True

    def refusal(self, *, layer: str, task: Any) -> dict[str, Any] | None:
        """Check made immediately before a request would be sent: the trigger when the run is stopped (the
        refusal is counted), else None."""
        with self._lock:
            if self._trigger is None:
                return None
            self._refused[f"{layer}:{task}"] += 1
            self._dirty = True
            return dict(self._trigger)

    def raise_if_stopped(self, *, layer: str, task: Any) -> None:
        trigger = self.refusal(layer=layer, task=task)
        if trigger is not None:
            raise RunProviderStopped(trigger)

    def note_answer_after_stop(self, *, layer: str, task: Any, call_id: Any = None, attempt_id: Any = None,
                               status_code: Any = None) -> bool:
        """A request that passed the pre-send check before the stop and was answered after it: kept, and listed
        as in flight at the stop. The triggering response itself is not listed."""
        with self._lock:
            if self._trigger is None:
                return False
            if attempt_id is not None and str(attempt_id) == self._trigger.get("attempt_id") and layer == self._trigger.get("layer"):
                return False
            self._in_flight.append({"layer": str(layer), "task": None if task is None else str(task),
                                    "call_id": None if call_id is None else str(call_id),
                                    "attempt_id": None if attempt_id is None else str(attempt_id),
                                    "status_code": status_code, "answered_at": _now()})
            self._dirty = True
        return True

    def snapshot(self) -> dict[str, Any]:
        with self._lock:
            return {
                "schema_version": SCHEMA_VERSION,
                "run_id": self.run_id,
                "stopped": self._trigger is not None,
                "stop_status_codes": sorted(STOP_STATUS_CODES),
                "trigger": dict(self._trigger) if self._trigger is not None else None,
                "refused_before_send": dict(sorted(self._refused.items())),
                "refused_before_send_total": sum(self._refused.values()),
                "answered_after_stop_in_flight": [dict(item) for item in self._in_flight],
                "policy": "no retry, no automatic resume, no other model or credential; refused requests were never sent",
                "updated_at": _now(),
            }

    def persist(self, *, only_if_changed: bool = False) -> Path | None:
        """Atomic write (temporary file + replace) of the snapshot into the attached run directory; a failed write
        is logged and never raised -- the stop itself is already in effect in memory. ``only_if_changed`` skips the
        write when nothing changed since the last one (the file may already be listed, with its hash, in the run's
        artifact manifest)."""
        with self._lock:
            directory = self._artifact_dir
            if directory is None or (only_if_changed and not self._dirty):
                return None
            self._dirty = False
        try:
            directory.mkdir(parents=True, exist_ok=True)
            text = json.dumps(self.snapshot(), ensure_ascii=False, indent=1) + "\n"
            with tempfile.NamedTemporaryFile("w", encoding="utf-8", dir=directory, prefix=".provider_stop.", suffix=".tmp",
                                             delete=False) as handle:
                handle.write(text)
                tmp_path = handle.name
            os.replace(tmp_path, directory / ARTIFACT_FILENAME)
            return directory / ARTIFACT_FILENAME
        except Exception:
            logger.exception("provider_stop.json write failed for run %s", self.run_id)
            return None


_REGISTRY: dict[str, RunProviderStop] = {}
_REGISTRY_LOCK = threading.Lock()


def run_provider_stop(run_id: str) -> RunProviderStop:
    """The one stop state of ``run_id`` in this process (a research job runs in its own worker process)."""
    with _REGISTRY_LOCK:
        state = _REGISTRY.get(str(run_id))
        if state is None:
            state = _REGISTRY[str(run_id)] = RunProviderStop(str(run_id))
        return state


def persist_run_provider_stop(run_id: Any) -> None:
    """Write the run's stop record if it changed since its last write (no-op for a run that was never stopped, or not
    known here). Called when a run's last model-calling stage is over, before its artifact manifest is written."""
    if run_id is None:
        return
    with _REGISTRY_LOCK:
        state = _REGISTRY.get(str(run_id))
    if state is not None and state.triggered is not None:
        state.persist(only_if_changed=True)


def release_run_provider_stop(run_id: Any) -> None:
    if run_id is None:
        return
    with _REGISTRY_LOCK:
        state = _REGISTRY.pop(str(run_id), None)
    if state is not None and state.triggered is not None:
        state.persist(only_if_changed=True)


def load_provider_stop_artifact(run_dir: Any) -> dict[str, Any] | None:
    path = Path(run_dir) / ARTIFACT_FILENAME
    if not path.is_file():
        return None
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return None
    return value if isinstance(value, dict) else None


__all__ = [
    "ARTIFACT_FILENAME",
    "LAYER_RESEARCH_AGENT",
    "LAYER_WEEK2",
    "STOP_ERROR_CODE",
    "STOP_FALLBACK_REASON",
    "STOP_STATUS_CODES",
    "RunProviderStop",
    "RunProviderStopped",
    "load_provider_stop_artifact",
    "persist_run_provider_stop",
    "provider_status_code",
    "redact_reason",
    "release_run_provider_stop",
    "run_provider_stop",
]
