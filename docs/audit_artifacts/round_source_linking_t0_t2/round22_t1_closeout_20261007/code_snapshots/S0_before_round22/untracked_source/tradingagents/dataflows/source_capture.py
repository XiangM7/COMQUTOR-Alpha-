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

_CURRENT_SINK: ContextVar[list[dict[str, Any]] | None] = ContextVar(
    "tradingagents_source_capture_sink", default=None
)


@contextlib.contextmanager
def source_capture_scope() -> Iterator[list[dict[str, Any]]]:
    """Open a fresh capture scope. The yielded list is mutated in place by
    any :func:`record_source` call made anywhere during the ``with`` block
    (including from deep inside a LangGraph tool-call chain) -- read it
    after the block exits; it keeps every item collected, exactly as
    appended, in call order."""
    sink: list[dict[str, Any]] = []
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


__all__ = ["source_capture_scope", "record_source"]
