"""Track D: productized Historical Architecture Replay.

Reprocesses a completed run's ``raw_agent_outputs.json`` through the
*current* COMQUTOR structure pipeline (claim segmentation -> structured
claims -> factor resolution -> Alpha mapping -> relation extraction ->
structure graph -> activation -> conflict), writing the result to a new,
independent ``replay-<...>`` run directory. Never re-invokes TradingAgents
or any LLM/market-data Provider, and never overwrites the source run.

See ``pipeline.py`` for the core service function and ``cli.py`` for the
``python -m comqutor_alpha.replay`` entrypoint.
"""

from comqutor_alpha.replay.pipeline import (
    ReplayResult,
    ReplaySourceIncompleteError,
    run_structure_replay,
)

__all__ = ["ReplayResult", "ReplaySourceIncompleteError", "run_structure_replay"]
