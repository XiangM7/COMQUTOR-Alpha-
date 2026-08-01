"""Offline, provider-free cross-run evaluation harness.

Reuses the exact same pure pipeline functions the production request path
and the Historical Architecture Replay service already use (see
``comqutor_alpha.replay.pipeline.run_structure_replay``) -- this package
never re-runs TradingAgents, never calls an LLM/market-data Provider, and
never mutates a source run or golden-case bundle. It only orchestrates:
load a case definition -> replay it against already-materialized JSON ->
compare the result against ``expected.yaml`` -> aggregate metrics -> write
a report.
"""

from comqutor_alpha.evaluation.expectations import evaluate_expected
from comqutor_alpha.evaluation.golden_case import GoldenCaseError, load_golden_case
from comqutor_alpha.evaluation.policy import EvaluationPolicy, load_policy
from comqutor_alpha.evaluation.runner import CaseResult, run_case

__all__ = [
    "evaluate_expected",
    "GoldenCaseError",
    "load_golden_case",
    "EvaluationPolicy",
    "load_policy",
    "CaseResult",
    "run_case",
]
