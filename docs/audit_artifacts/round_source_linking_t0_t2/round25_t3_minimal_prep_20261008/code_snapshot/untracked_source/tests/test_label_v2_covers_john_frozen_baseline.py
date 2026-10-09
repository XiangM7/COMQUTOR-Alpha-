"""T2 (2026-10-07), John's task sheet section 4, "1. 当前问题": 现有 YAML 列出了六类语义和 16 条“标的—允许冲突”配置，但自身注明不代表实现已经对齐 ...
这项是上一轮已经明确要求的工作，本轮必须实际关闭.

docs/audit_artifacts/v0_2_john_frozen_gold_baseline.yaml (authority JOHN_WRITTEN_V0_2_BASELINE) is John's own list of the 16 ticker-pair allowed_main_conflicts and
its `implementation_alignment_required` section records which of them no repo rule file carried. This test makes that alignment a standing invariant instead
of a one-time edit: every one of the 16 pairs is a canonical taxonomy pair AND is carried by the v0.2 label file the formal acceptance entry reads.

The baseline file is frozen and read only here. Nothing in this test is a synthetic fixture: both files are the real, committed rule sources.
"""

from __future__ import annotations

from pathlib import Path

import yaml

from comqutor_alpha.regression.labels_v2 import load_j2_labels_v2

REPO = Path(__file__).resolve().parents[1]
BASELINE_PATH = REPO / "docs" / "audit_artifacts" / "v0_2_john_frozen_gold_baseline.yaml"

EXECUTABLE_CATEGORIES = ("required_conflicts", "conditional_conflicts", "allowed_conflicts")

# The five pairs the baseline recorded as absent from every repo rule file, filed under John's own family name allowed_main_conflicts -> allowed_conflicts.
ADDED_ON_2026_10_07 = {
    "QQQ": {"A003__A501", "A304__A601"},
    "MSFT": {"A101__A304", "A301__A304"},
    "TSM": {"A101__A304"},
}


def _baseline() -> dict[str, list[str]]:
    return yaml.safe_load(BASELINE_PATH.read_text(encoding="utf-8"))["allowed_main_conflicts"]


def test_the_baseline_still_lists_exactly_sixteen_pairs():
    baseline = _baseline()
    assert sum(len(pairs) for pairs in baseline.values()) == 16
    assert set(baseline) == {"NVDA", "QQQ", "SNDK", "MSFT", "TSM", "AMD"}


def test_every_baseline_pair_is_a_canonical_taxonomy_pair():
    canonical = set(load_j2_labels_v2()["canonical_conflict_pairs"])
    missing = {(ticker, pair) for ticker, pairs in _baseline().items() for pair in pairs if pair not in canonical}
    assert not missing, f"baseline pairs the taxonomy does not declare reciprocally: {sorted(missing)}"


def test_every_baseline_pair_is_carried_by_the_v0_2_label_file_as_an_executable_category():
    label = load_j2_labels_v2()
    not_carried = []
    for ticker, pairs in _baseline().items():
        block = label["tickers"][ticker]
        carried = {pair for category in EXECUTABLE_CATEGORIES for pair in (block.get(category) or ())}
        not_carried += [(ticker, pair) for pair in pairs if pair not in carried]
    assert not not_carried, f"John's baseline pairs no executable v0.2 category carries: {sorted(not_carried)}"


def test_no_baseline_pair_is_parked_in_a_category_that_is_never_evaluated():
    label = load_j2_labels_v2()
    parked = []
    for ticker, pairs in _baseline().items():
        block = label["tickers"][ticker]
        pending = {entry["pair_id"] for entry in (block.get("product_decision_pending") or ())}
        removed = set(block.get("remove_while_undeclared") or ())
        parked += [(ticker, pair) for pair in pairs if pair in pending | removed]
    assert not parked, f"baseline pairs parked as pending/removed: {sorted(parked)}"


def test_the_five_pairs_the_baseline_recorded_as_missing_are_filed_as_allowed_conflicts():
    """John files all 16 under allowed_main_conflicts ("ALLOWED structures when supported by evidence -- never mandatory outputs. Absence ... is not
    automatically a failure"); the equivalent v0.2 field is allowed_conflicts, which adds no review trigger on absence. The ten pairs that were already
    carried under conditional_conflicts were left as they were; whether to move them is an open question for John (see the label file's change log)."""
    label = load_j2_labels_v2()
    for ticker, pairs in ADDED_ON_2026_10_07.items():
        assert pairs <= set(label["tickers"][ticker]["allowed_conflicts"]), ticker
    in_conditional = {
        ticker: sorted(set(label["tickers"][ticker]["conditional_conflicts"]) & set(_baseline()[ticker])) for ticker in _baseline()
    }
    assert sum(len(pairs) for pairs in in_conditional.values()) == 10
