"""T2 (2026-10-07): docs/specs/t2_acceptance_scenario_map.json maps each of John's seven required scenarios to the tests that prove it. A map that points
at tests that were renamed or deleted is worse than no map, so this test keeps it honest: every node it cites exists, every scenario has an engine-level
or end-to-end test, and the seven scenarios are exactly John's.
"""

from __future__ import annotations

import ast
import json
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]
MAP_PATH = REPO / "docs" / "specs" / "t2_acceptance_scenario_map.json"

JOHN_SCENARIOS = [
    "有明确支持证据，却漏掉必须识别的 Alpha",
    "没有支持证据",
    "只有反驳、引用或背景文字",
    "必需规则缺失或无法执行",
    "同源证据增加多份重复表达",
    "实际冲突不在标的验收列表",
    "同一输入做纯 replay，只更换执行编号",
]


def _node_exists(node: str) -> bool:
    path_part, *names = node.split("::")
    path = REPO / path_part
    if not path.is_file() or not names:
        return False
    body = ast.parse(path.read_text(encoding="utf-8")).body
    for name in names[:-1]:
        cls = next((n for n in body if isinstance(n, ast.ClassDef) and n.name == name), None)
        if cls is None:
            return False
        body = cls.body
    return any(isinstance(n, (ast.FunctionDef, ast.AsyncFunctionDef)) and n.name == names[-1] for n in body)


def _map() -> dict:
    return json.loads(MAP_PATH.read_text(encoding="utf-8"))


def test_the_map_has_exactly_johns_seven_scenarios_in_order():
    assert [s["john_scenario"] for s in _map()["scenarios"]] == JOHN_SCENARIOS
    assert [s["id"] for s in _map()["scenarios"]] == list(range(1, 8))


def test_every_cited_test_exists():
    missing = [t["node"] for s in _map()["scenarios"] for t in s["tests"] if not _node_exists(t["node"])]
    assert missing == [], f"the scenario map cites tests that do not exist: {missing}"


def test_every_scenario_has_a_test_of_the_acceptance_layer_itself():
    for scenario in _map()["scenarios"]:
        kinds = {t["kind"] for t in scenario["tests"]}
        assert kinds & {"engine_level", "end_to_end_formal_status"}, scenario["john_scenario"]


def test_the_node_checker_really_rejects_a_missing_test():
    assert _node_exists("tests/test_acceptance_engine.py::TestScenarioB_NoEvidenceNeverForcesDetection::test_b_no_supporting_evidence_never_forces_activation_or_a_conflict")
    assert not _node_exists("tests/test_acceptance_engine.py::TestScenarioB_NoEvidenceNeverForcesDetection::test_that_was_never_written")
    assert not _node_exists("tests/test_never_a_file.py::test_x")
