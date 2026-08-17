"""Strict, versioned replay-mode identities.

The two modes have deliberately different semantic sources.  Callers must
never shorten or infer these names when deciding which replay path to run.
"""

from __future__ import annotations

from enum import StrEnum


class ReplayMode(StrEnum):
    """The only supported replay modes in the Phase 0.6C contract."""

    EXACT_SEMANTIC_REPLAY = "EXACT_SEMANTIC_REPLAY"
    RAW_REBUILD_DIAGNOSTIC = "RAW_REBUILD_DIAGNOSTIC"


def require_replay_mode(value: ReplayMode | str) -> ReplayMode:
    """Return an exact mode or fail instead of guessing from an alias."""

    if isinstance(value, ReplayMode):
        return value
    if not isinstance(value, str):
        raise ValueError("REPLAY_MODE_REQUIRED")
    try:
        return ReplayMode(value)
    except ValueError as exc:
        raise ValueError("REPLAY_MODE_UNSUPPORTED") from exc


__all__ = ["ReplayMode", "require_replay_mode"]
