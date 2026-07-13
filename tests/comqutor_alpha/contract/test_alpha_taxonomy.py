from __future__ import annotations

from copy import deepcopy
from pathlib import Path

import pytest
import yaml

from comqutor_alpha.alpha_library.alpha_loader import (
    DEFAULT_TAXONOMY_PATH,
    EXPECTED_ALPHA_IDS,
    MANDATORY_CONFLICT_PAIRS,
    MANDATORY_RELATIONS,
    TaxonomyError,
    load_taxonomy,
)


def _raw_taxonomy():
    return yaml.safe_load(DEFAULT_TAXONOMY_PATH.read_text(encoding="utf-8"))


def _write(tmp_path: Path, raw: dict) -> Path:
    path = tmp_path / "taxonomy.yaml"
    path.write_text(yaml.safe_dump(raw, allow_unicode=True, sort_keys=False), encoding="utf-8")
    return path


@pytest.mark.contract
def test_mvp10_and_mandatory_relations_load() -> None:
    taxonomy = load_taxonomy()
    assert len(taxonomy.alphas) == 10
    assert {alpha.alpha_id for alpha in taxonomy.alphas} == EXPECTED_ALPHA_IDS
    pairs = {
        tuple(sorted((alpha.alpha_id, conflict.alpha_id)))
        for alpha in taxonomy.alphas
        for conflict in taxonomy.conflicts_for(alpha.alpha_id)
    }
    assert pairs == MANDATORY_CONFLICT_PAIRS
    relations = {
        (edge.source, edge.target)
        for alpha in taxonomy.alphas
        for edge in alpha.causal_graph
    }
    assert relations >= MANDATORY_RELATIONS
    assert {item.alpha_id for item in taxonomy.conflicts_for("A304")} == {
        "A101",
        "A301",
        "A601",
    }
    assert taxonomy.conflicts_for("A101")[0].alpha_id == "A304"


@pytest.mark.contract
@pytest.mark.parametrize("failure", ["duplicate", "unknown_conflict", "bad_weight", "empty_signals"])
def test_invalid_taxonomy_fails_at_load(tmp_path: Path, failure: str) -> None:
    raw = deepcopy(_raw_taxonomy())
    if failure == "duplicate":
        raw["alphas"][-1]["alpha_id"] = raw["alphas"][0]["alpha_id"]
    elif failure == "unknown_conflict":
        raw["alphas"][0]["conflict_alphas"][0]["alpha_id"] = "A999"
    elif failure == "bad_weight":
        raw["alphas"][0]["conflict_alphas"][0]["contradiction_weight"] = 1.5
    else:
        raw["alphas"][0]["trigger_signals"] = []
    with pytest.raises(TaxonomyError):
        load_taxonomy(_write(tmp_path, raw))


@pytest.mark.contract
def test_unknown_alpha_query_fails() -> None:
    with pytest.raises(TaxonomyError, match="unknown Alpha ID"):
        load_taxonomy().get("A999")
