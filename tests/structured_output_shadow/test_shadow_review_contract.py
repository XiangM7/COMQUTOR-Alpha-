from __future__ import annotations

from pathlib import Path

from conftest import bundle_for, claim_for

from comqutor_alpha.structure_engine.structured_output_shadow_review import (
    REVIEW_CSV_FIELDS,
    REVIEW_LABELS,
    REVIEW_SEVERITIES,
    build_blank_review_rows,
    compare_legacy_and_shadow,
    render_blank_review_csv,
)

REPO_ROOT = Path(__file__).resolve().parents[2]


def test_review_contract_contains_all_frozen_dimensions_and_severities():
    assert set(REVIEW_LABELS) == {
        "claim_boundary",
        "evidence_pairing",
        "semantic_fidelity",
        "entity_extraction",
        "factor_extraction",
        "direction",
        "overall_disposition",
    }
    assert REVIEW_SEVERITIES == ("critical", "major", "minor", "none")
    contract = (REPO_ROOT / "docs/specs/structured_output_adapter_review_contract_v1.md").read_text()
    assert "not a gold set" in contract
    assert "Human labels created: `No`" in contract


def test_review_rows_never_prefill_human_answers(report):
    shadow = bundle_for(report, claims=[claim_for(report, "GPU demand increased in June.")])
    legacy = [{"claim_id": "legacy-1", "claim": "GPU demand increased in June.", "evidence": "GPU demand increased in June."}]
    comparison = compare_legacy_and_shadow(legacy, shadow)
    rows = build_blank_review_rows(
        comparison=comparison, legacy_outputs=legacy, shadow_bundle=shadow
    )
    for field in ("review_dimension", "review_label", "severity", "reviewer", "review_timestamp", "notes"):
        assert rows[0][field] == ""
    csv_text = render_blank_review_csv(rows)
    assert csv_text.splitlines()[0] == ",".join(REVIEW_CSV_FIELDS)

