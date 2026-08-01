"""Expectation-type evaluation for Golden Case ``expected.yaml`` files.

Every check here is a pure function of two already-materialized inputs (an
``expected.yaml``-shaped dict and an "actual" metrics dict built by
``runner.py`` from a replayed case) -- never a network call, never a
Provider call, never a comparison against a live LLM's exact stochastic
text (see ``must_not_be_manual_review_of_exact_text`` boundary: a
``live_smoke_result`` case must never carry an ``exact`` text expectation).
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

_LEAF_EXPECTATION_KEYS = frozenset(
    {
        "exact",
        "range",
        "set_equals",
        "set_contains",
        "one_of",
        "minimum",
        "maximum",
        "must_exist",
        "must_not_exist",
        "path_exists",
        "evidence_link_exists",
        "manual_review",
    }
)


@dataclass(frozen=True)
class ExpectationResult:
    name: str
    expectation_type: str
    passed: bool
    detail: str
    manual: bool = False

    def to_dict(self) -> dict[str, Any]:
        return {
            "name": self.name,
            "expectation_type": self.expectation_type,
            "passed": self.passed,
            "detail": self.detail,
            "manual": self.manual,
        }


def _is_leaf_expectation(spec: Any) -> bool:
    return isinstance(spec, dict) and bool(_LEAF_EXPECTATION_KEYS & set(spec))


def evaluate_leaf(name: str, spec: dict[str, Any], actual: Any) -> ExpectationResult:
    """Evaluate a single leaf expectation dict against one actual value.

    Exactly one expectation-type key is expected per leaf; if more than one
    is present, every one is checked and all must pass (never silently
    picking the first).
    """
    checks: list[tuple[str, bool, str]] = []

    if "exact" in spec:
        expected_value = spec["exact"]
        checks.append(("exact", actual == expected_value, f"expected exactly {expected_value!r}, got {actual!r}"))
    if "range" in spec:
        lo, hi = spec["range"][0], spec["range"][1]
        ok = isinstance(actual, (int, float)) and lo <= actual <= hi
        checks.append(("range", ok, f"expected in range [{lo}, {hi}], got {actual!r}"))
    if "minimum" in spec:
        ok = isinstance(actual, (int, float)) and actual >= spec["minimum"]
        checks.append(("minimum", ok, f"expected >= {spec['minimum']}, got {actual!r}"))
    if "maximum" in spec:
        ok = isinstance(actual, (int, float)) and actual <= spec["maximum"]
        checks.append(("maximum", ok, f"expected <= {spec['maximum']}, got {actual!r}"))
    if "set_equals" in spec:
        expected_set = set(spec["set_equals"])
        actual_set = set(actual or [])
        checks.append(("set_equals", actual_set == expected_set, f"expected set {sorted(expected_set)}, got {sorted(actual_set)}"))
    if "set_contains" in spec:
        expected_subset = set(spec["set_contains"])
        actual_set = set(actual or [])
        missing = expected_subset - actual_set
        checks.append(("set_contains", not missing, f"missing required members {sorted(missing)}" if missing else "ok"))
    if "one_of" in spec:
        allowed = set(spec["one_of"])
        checks.append(("one_of", actual in allowed, f"expected one of {sorted(allowed)}, got {actual!r}"))
    if "must_exist" in spec and spec["must_exist"]:
        checks.append(("must_exist", actual is not None, "expected a value to be present, got None"))
    if "must_not_exist" in spec and spec["must_not_exist"]:
        checks.append(("must_not_exist", actual is None, f"expected no value, got {actual!r}"))
    if "path_exists" in spec:
        # Consumed structurally by the caller (graph.required_paths); a bare
        # leaf usage just checks truthiness of a precomputed boolean.
        checks.append(("path_exists", bool(actual), "expected path to exist"))
    if "evidence_link_exists" in spec:
        checks.append(("evidence_link_exists", bool(actual), "expected an evidence link to exist"))
    if "manual_review" in spec and spec["manual_review"]:
        # Never auto-verified -- always reported, never silently dropped,
        # and never counted as an automatic pass/fail for gating purposes.
        return ExpectationResult(name, "manual_review", True, "flagged for manual review, not auto-verified", manual=True)

    if not checks:
        return ExpectationResult(name, "unknown", False, f"no recognized expectation key in {spec!r}")

    all_passed = all(passed for _, passed, _ in checks)
    detail = "; ".join(f"{etype}: {msg}" for etype, passed, msg in checks if not passed) or "ok"
    expectation_type = "+".join(etype for etype, _, _ in checks)
    return ExpectationResult(name, expectation_type, all_passed, detail)


def _check_required_paths(name_prefix: str, path_specs: list[dict[str, Any]], edges: list[dict[str, Any]]) -> list[ExpectationResult]:
    adjacency: dict[str, set[str]] = {}
    for edge in edges:
        if not isinstance(edge, dict):
            continue
        adjacency.setdefault(str(edge.get("source")), set()).add(str(edge.get("target")))

    results = []
    for i, path_spec in enumerate(path_specs):
        source = str(path_spec.get("source"))
        target = str(path_spec.get("target"))
        max_hops = int(path_spec.get("max_hops") or len(adjacency) or 1)
        found = _bfs_reachable(adjacency, source, target, max_hops)
        results.append(
            ExpectationResult(
                f"{name_prefix}[{i}]:{source}->{target}",
                "path_exists",
                found,
                "ok" if found else f"no path from {source!r} to {target!r} within {max_hops} hops",
            )
        )
    return results


def _bfs_reachable(adjacency: dict[str, set[str]], source: str, target: str, max_hops: int) -> bool:
    frontier = {source}
    seen = {source}
    for _ in range(max_hops):
        next_frontier: set[str] = set()
        for node in frontier:
            for neighbor in adjacency.get(node, ()):
                if neighbor == target:
                    return True
                if neighbor not in seen:
                    seen.add(neighbor)
                    next_frontier.add(neighbor)
        frontier = next_frontier
        if not frontier:
            break
    return False


def _check_forbidden_patterns(patterns: list[str], claim_texts: list[str]) -> list[ExpectationResult]:
    results = []
    lowered_texts = [str(t).lower() for t in claim_texts]
    for pattern in patterns:
        needle = str(pattern).lower()
        hits = [t for t in lowered_texts if needle in t]
        results.append(
            ExpectationResult(
                f"claims.forbidden_patterns:{pattern!r}",
                "forbidden_pattern",
                not hits,
                "ok" if not hits else f"found {len(hits)} claim(s) matching forbidden pattern {pattern!r}",
            )
        )
    return results


def evaluate_expected(expected: dict[str, Any], actual: dict[str, Any]) -> list[ExpectationResult]:
    """Evaluate every expectation declared in an ``expected.yaml`` dict.

    Only sections actually present in ``expected`` are checked -- a case
    with no ``conflicts`` block, for example, asserts nothing about
    conflicts (never an implicit pass *or* fail).
    """
    results: list[ExpectationResult] = []

    graph_expected = expected.get("graph") or {}
    graph_actual = actual.get("graph") or {}
    for key in ("node_count", "edge_count"):
        if key in graph_expected and _is_leaf_expectation(graph_expected[key]):
            results.append(evaluate_leaf(f"graph.{key}", graph_expected[key], graph_actual.get(key)))
    if "required_paths" in graph_expected:
        results.extend(
            _check_required_paths("graph.required_paths", graph_expected["required_paths"], graph_actual.get("edges") or [])
        )
    # zero_edges_allowed / minimum_edges are declarative opt-ins read
    # directly by graph.edge_count above (minimum) -- zero_edges_allowed
    # itself never generates a check; it exists purely so a case author can
    # be explicit that 0 is an accepted outcome, silencing no other
    # existing edge_count expectation.

    activation_expected = expected.get("activation") or {}
    activation_actual = actual.get("activation") or {}
    if "required_active_alphas" in activation_expected and _is_leaf_expectation(activation_expected["required_active_alphas"]):
        results.append(
            evaluate_leaf(
                "activation.required_active_alphas",
                activation_expected["required_active_alphas"],
                activation_actual.get("active_alpha_ids") or [],
            )
        )
    if "forbidden_regime_alphas" in activation_expected:
        forbidden_spec = activation_expected["forbidden_regime_alphas"]
        forbidden_ids = set(forbidden_spec.get("set_contains") or forbidden_spec.get("set_equals") or [])
        regime_ids = set(activation_actual.get("regime_level_alpha_ids") or [])
        hit = forbidden_ids & regime_ids
        results.append(
            ExpectationResult(
                "activation.forbidden_regime_alphas",
                "forbidden_set",
                not hit,
                "ok" if not hit else f"forbidden alpha(s) reached regime_level: {sorted(hit)}",
            )
        )

    conflicts_expected = expected.get("conflicts") or {}
    conflicts_actual = actual.get("conflicts") or {}
    if "main_conflict" in conflicts_expected and _is_leaf_expectation(conflicts_expected["main_conflict"]):
        results.append(
            evaluate_leaf("conflicts.main_conflict", conflicts_expected["main_conflict"], conflicts_actual.get("main_conflict_id"))
        )
    if conflicts_expected.get("all_admitted_require_bull_evidence"):
        admitted = conflicts_actual.get("admitted") or []
        missing = [c.get("pair_id") for c in admitted if not (c.get("bull_raw_claim_count") or 0) > 0]
        results.append(
            ExpectationResult(
                "conflicts.all_admitted_require_bull_evidence",
                "invariant",
                not missing,
                "ok" if not missing else f"admitted pair(s) with no bull evidence: {missing}",
            )
        )
    if conflicts_expected.get("all_admitted_require_bear_evidence"):
        admitted = conflicts_actual.get("admitted") or []
        missing = [c.get("pair_id") for c in admitted if not (c.get("bear_raw_claim_count") or 0) > 0]
        results.append(
            ExpectationResult(
                "conflicts.all_admitted_require_bear_evidence",
                "invariant",
                not missing,
                "ok" if not missing else f"admitted pair(s) with no bear evidence: {missing}",
            )
        )

    claims_expected = expected.get("claims") or {}
    if "forbidden_patterns" in claims_expected:
        results.extend(_check_forbidden_patterns(claims_expected["forbidden_patterns"], actual.get("claims", {}).get("texts") or []))

    return results
