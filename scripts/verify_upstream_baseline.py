#!/usr/bin/env python3
"""Offline evidence check for the COMQUTOR/TradingAgents integration seam.

This verifier intentionally inspects source and a small sanitized fixture.  It
does not construct a real LLM client, access the network, or use API secrets.
"""

from __future__ import annotations

import ast
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
GRAPH_SOURCE = ROOT / "tradingagents/graph/trading_graph.py"
STATE_SOURCE = ROOT / "tradingagents/agents/utils/agent_states.py"
SETUP_SOURCE = ROOT / "tradingagents/graph/setup.py"
FIXTURE = ROOT / "tests/comqutor_alpha/fixtures/upstream_state_minimal.json"
REPORT_KEYS = (
    "market_report",
    "sentiment_report",
    "news_report",
    "fundamentals_report",
)


class BaselineVerificationError(RuntimeError):
    """Raised when the upstream seam no longer matches its recorded contract."""


def _class_method(tree: ast.AST, class_name: str, method_name: str) -> ast.FunctionDef:
    for node in ast.walk(tree):
        if isinstance(node, ast.ClassDef) and node.name == class_name:
            for child in node.body:
                if isinstance(child, ast.FunctionDef) and child.name == method_name:
                    return child
    raise BaselineVerificationError(f"missing {class_name}.{method_name}")


def verify_repository(root: Path = ROOT) -> dict[str, object]:
    graph_path = root / GRAPH_SOURCE.relative_to(ROOT)
    state_path = root / STATE_SOURCE.relative_to(ROOT)
    setup_path = root / SETUP_SOURCE.relative_to(ROOT)
    fixture_path = root / FIXTURE.relative_to(ROOT)

    graph_text = graph_path.read_text(encoding="utf-8")
    graph_tree = ast.parse(graph_text)
    propagate = _class_method(graph_tree, "TradingAgentsGraph", "propagate")
    run_graph = _class_method(graph_tree, "TradingAgentsGraph", "_run_graph")

    propagate_delegates = any(
        isinstance(node, ast.Call)
        and isinstance(node.func, ast.Attribute)
        and node.func.attr == "_run_graph"
        for node in ast.walk(propagate)
    )
    returns_pair = any(
        isinstance(node, ast.Return)
        and isinstance(node.value, ast.Tuple)
        and len(node.value.elts) == 2
        for node in ast.walk(run_graph)
    )
    if not propagate_delegates or not returns_pair:
        raise BaselineVerificationError("propagate() no longer delegates to a two-value return")

    state_text = state_path.read_text(encoding="utf-8")
    missing_state_fields = [key for key in REPORT_KEYS if key not in state_text]
    if missing_state_fields:
        raise BaselineVerificationError(
            f"AgentState is missing report fields: {', '.join(missing_state_fields)}"
        )

    setup_text = setup_path.read_text(encoding="utf-8")
    expected_nodes = (
        "Bull Researcher",
        "Bear Researcher",
        "Research Manager",
        "Trader",
        "Aggressive Analyst",
        "Neutral Analyst",
        "Conservative Analyst",
        "Portfolio Manager",
    )
    missing_nodes = [node for node in expected_nodes if node not in setup_text]
    if missing_nodes:
        raise BaselineVerificationError(
            f"GraphSetup is missing expected downstream nodes: {', '.join(missing_nodes)}"
        )

    fixture = json.loads(fixture_path.read_text(encoding="utf-8"))
    return_value = fixture.get("return_value")
    if not isinstance(return_value, list) or len(return_value) != 2:
        raise BaselineVerificationError("fixture must encode the propagate two-value return")
    final_state, processed_decision = return_value
    if not isinstance(final_state, dict):
        raise BaselineVerificationError("fixture final_state must be an object")
    missing_fixture_fields = [key for key in REPORT_KEYS if not final_state.get(key)]
    if missing_fixture_fields:
        raise BaselineVerificationError(
            f"fixture has missing/empty reports: {', '.join(missing_fixture_fields)}"
        )
    if not isinstance(processed_decision, str):
        raise BaselineVerificationError("fixture processed_decision must be a string")

    return {
        "status": "pass",
        "offline": True,
        "propagate_delegates_to_run_graph": True,
        "run_graph_returns_pair": True,
        "report_keys": list(REPORT_KEYS),
        "downstream_nodes": list(expected_nodes),
        "fixture": str(fixture_path.relative_to(root)),
    }


def main() -> int:
    print(json.dumps(verify_repository(), indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
