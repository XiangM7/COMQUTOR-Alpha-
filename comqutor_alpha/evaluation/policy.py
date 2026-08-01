"""Loads ``evaluation/policies/mvp_evaluation_policy.yaml``.

Thresholds live in one config file, never scattered/hardcoded across the
harness -- see the sprint boundary: "Thresholds 放在独立配置... 不得散落
硬编码". A per-case graph-edge minimum is a *Golden Case* concern
(``expected.yaml``'s own ``graph.edge_count.minimum`` /
``zero_edges_allowed``), never a global policy default -- this file
deliberately carries no global "every run needs N edges" threshold.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

import yaml

DEFAULT_POLICY_PATH = Path("evaluation/policies/mvp_evaluation_policy.yaml")

_DEFAULTS: dict[str, Any] = {
    "max_schema_failure_rate": 0.0,
    "max_parse_failure_rate": 0.0,
    "min_lineage_resolution_rate": 0.0,
    "min_production_shadow_consistency_rate": 1.0,
    "max_shared_conflict_fact_violations": 0,
}


@dataclass(frozen=True)
class EvaluationPolicy:
    max_schema_failure_rate: float = _DEFAULTS["max_schema_failure_rate"]
    max_parse_failure_rate: float = _DEFAULTS["max_parse_failure_rate"]
    min_lineage_resolution_rate: float = _DEFAULTS["min_lineage_resolution_rate"]
    min_production_shadow_consistency_rate: float = _DEFAULTS["min_production_shadow_consistency_rate"]
    max_shared_conflict_fact_violations: int = _DEFAULTS["max_shared_conflict_fact_violations"]
    raw: dict[str, Any] = field(default_factory=dict)

    def evaluate_operational_gates(self, metrics: dict[str, Any]) -> list[str]:
        """Returns a list of policy-violation reason codes (empty ==
        every configured gate passed). Only gates whose required input
        metric is actually present are evaluated -- an unavailable metric
        is never treated as a violation."""
        violations = []
        if metrics.get("schema_failure_rate") is not None and metrics["schema_failure_rate"] > self.max_schema_failure_rate:
            violations.append("SCHEMA_FAILURE_RATE_EXCEEDED")
        if metrics.get("parse_failure_rate") is not None and metrics["parse_failure_rate"] > self.max_parse_failure_rate:
            violations.append("PARSE_FAILURE_RATE_EXCEEDED")
        if (
            metrics.get("lineage_resolution_rate") is not None
            and metrics["lineage_resolution_rate"] < self.min_lineage_resolution_rate
        ):
            violations.append("LINEAGE_RESOLUTION_RATE_BELOW_MINIMUM")
        if (
            metrics.get("production_shadow_consistency_rate") is not None
            and metrics["production_shadow_consistency_rate"] < self.min_production_shadow_consistency_rate
        ):
            violations.append("PRODUCTION_SHADOW_CONSISTENCY_RATE_BELOW_MINIMUM")
        if (
            metrics.get("shared_conflict_fact_violations") is not None
            and metrics["shared_conflict_fact_violations"] > self.max_shared_conflict_fact_violations
        ):
            violations.append("SHARED_CONFLICT_FACT_VIOLATIONS_EXCEEDED")
        return violations


def load_policy(path: Path | str = DEFAULT_POLICY_PATH) -> EvaluationPolicy:
    path = Path(path)
    if not path.exists():
        return EvaluationPolicy(raw={})
    raw = yaml.safe_load(path.read_text(encoding="utf-8")) or {}
    if not isinstance(raw, dict):
        raw = {}
    kwargs = {key: raw[key] for key in _DEFAULTS if key in raw}
    return EvaluationPolicy(raw=raw, **kwargs)


__all__ = ["EvaluationPolicy", "load_policy", "DEFAULT_POLICY_PATH"]
