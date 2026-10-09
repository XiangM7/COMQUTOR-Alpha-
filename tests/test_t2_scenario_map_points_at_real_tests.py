"""T2 (2026-10-07): docs/specs/t2_acceptance_scenario_map.json maps each of John's seven required scenarios to the tests that prove it. A map that points
at tests that were renamed or deleted is worse than no map, so this test keeps it honest: every node it cites exists, every scenario has an engine-level
or end-to-end test, and the seven scenarios are exactly John's.

Round 24: a test NAME existing proves little, so the map also states, for every cited test, what kind of input it runs on (`fixture`) and what the
scenario's coverage really is (`coverage_status`). The checks below refuse a map that claims full coverage resting only on hand-made counts or on
hand-edited records, and refuse the earlier false statement that no rule file lists the Alphas John requires. Whether the cited tests PASS is recorded
by the test evidence of the round (the JUnit file), not guessed here.
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
    assert _node_exists("tests/test_acceptance_engine.py::TestScenarioB_NoEvidenceNeverForcesDetection::test_b_a_missing_arbitration_record_is_not_evaluated_and_never_read_as_no_evidence")
    assert not _node_exists("tests/test_acceptance_engine.py::TestScenarioB_NoEvidenceNeverForcesDetection::test_that_was_never_written")
    assert not _node_exists("tests/test_never_a_file.py::test_x")


_REAL_FIXTURES = {"real_detector_and_b2_on_synthetic_inputs", "real_pipeline_synthetic_text", "historical_saved_runs"}


def test_every_cited_test_says_what_kind_of_input_it_runs_on_and_what_it_proves():
    doc = _map()
    for scenario in doc["scenarios"]:
        for test in scenario["tests"]:
            assert test["fixture"] in doc["fixture_kinds"], (test["node"], test["fixture"])
            assert test["proves"].strip(), test["node"]


def test_a_scenario_is_only_marked_covered_when_something_beyond_hand_made_records_proves_it():
    doc = _map()
    assert {s["coverage_status"] for s in doc["scenarios"]} <= set(doc["coverage_statuses"])
    for scenario in doc["scenarios"]:
        fixtures = {t["fixture"] for t in scenario["tests"]}
        if scenario["coverage_status"] == "covered":
            assert fixtures & _REAL_FIXTURES or any(t["kind"] == "upstream_real_path" for t in scenario["tests"]), scenario["john_scenario"]
            assert fixtures != {"controlled_modification"}, scenario["john_scenario"]
        if scenario["coverage_status"] == "covered_with_limits":
            assert scenario["limits"].strip(), scenario["john_scenario"]


def test_scenario_one_states_that_the_alpha_layer_trigger_exists_only_for_the_bound_runs_and_never_the_false_no_list_claim():
    doc = _map()
    one = doc["scenarios"][0]
    assert one["coverage_status"] == "covered_with_limits"
    assert "frozen trigger matrix" in one["limits"] and "not evaluable" in one["limits"]
    assert "no rule file declares a list of required Alphas" not in json.dumps(doc, ensure_ascii=False)


def test_the_alpha_layer_tests_the_map_cites_really_use_the_frozen_contract_not_a_label_list():
    text = (REPO / "tests" / "test_t2_gold_contract_alpha_rules.py").read_text(encoding="utf-8")
    assert "v0_2_gold_operational_contract.json" in text and "required_conflicts" not in text.split("def test_", 1)[0]
