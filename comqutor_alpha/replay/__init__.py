"""Provider-zero replay services with explicit semantic-source modes.

Reprocesses a completed run's ``raw_agent_outputs.json`` through the
*current* COMQUTOR structure pipeline (claim segmentation -> structured
claims -> factor resolution -> Alpha mapping -> relation extraction ->
structure graph -> activation -> conflict), writing the result to a new,
independent ``replay-<...>`` run directory. Never re-invokes TradingAgents
or any LLM/market-data Provider, and never overwrites the source run.

``run_exact_semantic_replay`` reuses saved validated semantic artifacts.
``run_structure_replay`` preserves the raw-rebuild diagnostic workflow.
"""

from comqutor_alpha.replay.exact_semantic import (
    ExactReplayResult,
    run_exact_semantic_replay,
)
from comqutor_alpha.replay.modes import ReplayMode, require_replay_mode
from comqutor_alpha.replay.pipeline import (
    ReplayResult,
    ReplaySourceIncompleteError,
    run_structure_replay,
)
from comqutor_alpha.replay.source_bundle import ExactReplayError

__all__ = [
    "ExactReplayError",
    "ExactReplayResult",
    "ReplayMode",
    "ReplayResult",
    "ReplaySourceIncompleteError",
    "require_replay_mode",
    "run_exact_semantic_replay",
    "run_structure_replay",
]
