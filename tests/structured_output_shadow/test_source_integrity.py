from __future__ import annotations

import hashlib
import json
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]


def _sha(path: str) -> str:
    return hashlib.sha256((REPO_ROOT / path).read_bytes()).hexdigest()


def test_canonical_development_plan_is_unchanged():
    assert _sha("docs/specs/COMQUTOR_Alpha_Development_Plan_v1.0.docx") == (
        "cabf3381aaa633b7b88035ab6df2d7dac0def3d5ddd337f6384f23f4c439a8d9"
    )


def test_current_semantic_components_match_approved_phase1_master_baseline():
    expected = {
        "comqutor_alpha/structure_engine/structured_output_adapter.py": "6bb63ac110a36411bfc88847fde82a8b74d48344589dae54f507d402a0235d6f",
        "comqutor_alpha/structure_engine/week2_llm.py": "84f07f477354b96de824e9102e0c4a3bd1c4e73926ff44e2c96790abc9e0e902",
        "comqutor_alpha/structure_engine/alpha_mapper.py": "f47e27396382ea7b3fde1b0cb3d73c47b27a0ee3e978c70a0c3e12e49b862431",
        "comqutor_alpha/structure_engine/structure_extractor.py": "5254cdf157c7d5ed88a7b06db34a9f0e3104259dde4fe5c52ecd922710fec416",
    }
    assert {path: _sha(path) for path in expected} == expected


def test_acceptance_fixtures_are_source_classified_and_traceable():
    payload = json.loads(
        (REPO_ROOT / "docs/audit_artifacts/phase1a/development_plan_acceptance_fixture_index.json").read_text()
    )
    assert payload["canonical_sha256"] == "cabf3381aaa633b7b88035ab6df2d7dac0def3d5ddd337f6384f23f4c439a8d9"
    assert all(item["classification"] == "SOURCE_FROZEN" for item in payload["fixtures"])
    assert payload["invented_source_frozen_examples"] == 0


def test_phase1a_has_no_files_under_historical_outputs():
    for root in (REPO_ROOT / "outputs/runs", REPO_ROOT / "outputs/replays"):
        assert not any("phase1a" in path.name.casefold() for path in root.rglob("*"))
