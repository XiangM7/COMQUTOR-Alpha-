"""Optional, self-contained per-run capture sink for genuine upstream
source metadata (article title/publisher/url/publish date, dataset series
id, filing accession, etc.).

Self-contained by design: this module has zero dependency on
``comqutor_alpha`` (the dependency direction in this codebase is always
comqutor_alpha -> tradingagents, never the reverse). Any dataflow function
that already extracts real, structured per-item metadata before flattening
it into the text it returns to an agent may additionally call
:func:`record_source` with that same metadata -- this NEVER changes the
text the function returns, so agent behavior and downstream Alpha/Evidence
semantics are provably unaffected by whether capture is active.

When no caller has entered :func:`source_capture_scope` (e.g. an offline
test, a direct dataflow call, or a caller that simply doesn't care), calls
to :func:`record_source` are a no-op -- capturing is opt-in per call site,
never a default requirement for a dataflow function to keep working.
"""

from __future__ import annotations

import contextlib
from collections.abc import Iterator
from contextvars import ContextVar
from typing import Any


class CapturedSources(list):
    """The per-run capture container: a plain ``list`` of source-record dicts (every existing caller keeps treating it
    as one) that additionally carries ``aux`` -- side-channel captures keyed by kind (T1 closeout, Round 22): the full
    input window behind a derived value (``derived_inputs``) and the sanitized raw provider response
    (``provider_responses``). ``aux`` is read by ``save_comqutor_run_outputs``; it never reaches the text an agent sees."""

    def __init__(self, *args: Any) -> None:
        super().__init__(*args)
        self.aux: dict[str, list[dict[str, Any]]] = {}


_CURRENT_SINK: ContextVar[CapturedSources | None] = ContextVar(
    "tradingagents_source_capture_sink", default=None
)


@contextlib.contextmanager
def source_capture_scope() -> Iterator[CapturedSources]:
    """Open a fresh capture scope. The yielded list is mutated in place by
    any :func:`record_source` call made anywhere during the ``with`` block
    (including from deep inside a LangGraph tool-call chain) -- read it
    after the block exits; it keeps every item collected, exactly as
    appended, in call order."""
    sink = CapturedSources()
    token = _CURRENT_SINK.set(sink)
    try:
        yield sink
    finally:
        _CURRENT_SINK.reset(token)


def record_source(source_record: dict[str, Any]) -> None:
    """Append one already-built source-record dict to the currently active
    capture scope, if any. A no-op outside any scope -- callers never need
    to check whether capture is active before calling this."""
    sink = _CURRENT_SINK.get()
    if sink is not None:
        sink.append(source_record)


def aux_capture_active() -> bool:
    """Whether a capture scope is open (lets a call site skip building an aux entry nobody will read)."""
    return _CURRENT_SINK.get() is not None


def record_aux(kind: str, entry: dict[str, Any]) -> None:
    """Append one side-channel capture entry (``kind`` e.g. ``derived_inputs`` / ``provider_responses``) to the active
    scope's ``aux``. A no-op outside any scope, like :func:`record_source`; never raises and never changes what the
    calling dataflow function returns."""
    sink = _CURRENT_SINK.get()
    if sink is not None:
        sink.aux.setdefault(kind, []).append(entry)


__all__ = ["CapturedSources", "source_capture_scope", "record_source", "record_aux", "aux_capture_active"]
