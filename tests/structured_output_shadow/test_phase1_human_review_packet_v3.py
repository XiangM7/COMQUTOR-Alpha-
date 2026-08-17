"""Phase 1 Master evidence-alignment fix: focused tests for the v3 human
review packet builder (comqutor_alpha/evaluation/phase1_human_review_packet_v3.py)
-- an additive sibling of the already-tested v2 packet builder. No Provider
calls, no network. Full build_review_packet() integration (24 real report
directories) is exercised for real only during the actual v3 evaluation
run, not here; these tests target the pieces that are new or genuinely
different from v2: the prompt-identity gate and the pure CSV/HTML renderers.
"""

from __future__ import annotations

import json

import pytest

from comqutor_alpha.evaluation.phase1_human_review_packet import (
    ALLOWED_REVIEW_VALUES as V2_ALLOWED_REVIEW_VALUES,
    REVIEW_FIELDS as V2_REVIEW_FIELDS,
)
from comqutor_alpha.evaluation.phase1_human_review_packet_v3 import (
    ALLOWED_REVIEW_VALUES,
    CSV_FIELDS,
    PROVENANCE_FAILURE,
    REQUIRED_PROMPT_VERSION,
    REVIEW_FIELDS,
    HumanReviewPacketError,
    collect_review_rows,
    render_review_csv,
    render_review_html,
    render_review_instructions,
)


def test_required_prompt_version_is_the_frozen_v3_identity():
    assert REQUIRED_PROMPT_VERSION == "structured_adapter.claim_extraction_shadow.v3"


def test_review_vocabulary_matches_v2_exactly_so_existing_validator_works_unmodified():
    """scripts/run_phase1_master.py's validate_human_review_csv /
    _validate_human_review_v2_csv import their allowed-values table from the
    v2 module and are never modified for v3 -- this is only safe because the
    v3 vocabulary is byte-identical to v2's."""

    assert REVIEW_FIELDS == V2_REVIEW_FIELDS
    assert ALLOWED_REVIEW_VALUES == V2_ALLOWED_REVIEW_VALUES


def test_collect_review_rows_rejects_a_v2_prompt_identity_evaluation(tmp_path):
    (tmp_path / "evaluation_metadata.json").write_text(
        json.dumps(
            {
                "prompt_version": "structured_adapter.claim_extraction_shadow.v2",
                "prompt_sha256": "a" * 64,
            }
        ),
        encoding="utf-8",
    )
    with pytest.raises(HumanReviewPacketError) as excinfo:
        collect_review_rows(tmp_path)
    assert excinfo.value.reason_code == PROVENANCE_FAILURE
    assert "prompt_v3_identity_invalid" in excinfo.value.detail


def test_collect_review_rows_rejects_missing_evaluation_metadata(tmp_path):
    with pytest.raises(HumanReviewPacketError):
        collect_review_rows(tmp_path)


def test_collect_review_rows_rejects_v3_version_with_missing_sha(tmp_path):
    (tmp_path / "evaluation_metadata.json").write_text(
        json.dumps({"prompt_version": REQUIRED_PROMPT_VERSION, "prompt_sha256": ""}),
        encoding="utf-8",
    )
    with pytest.raises(HumanReviewPacketError):
        collect_review_rows(tmp_path)


def _sample_row() -> dict[str, str]:
    row = dict.fromkeys(CSV_FIELDS, "")
    row.update(
        {
            "review_row_id": "phase1-review-v3-abc123",
            "ticker": "NVDA",
            "agent": "fundamental_agent",
            "report_family": "fundamental",
            "claim_ordinal": "1",
            "shadow_claim_id": "shadow-claim-v1-deadbeef",
            "claim_text": "Net margin reached 71.5%.",
            "shadow_evidence_text": "Net margin reached 71.5% for the quarter.",
            "source_evidence_text": "Net margin reached 71.5% for the quarter.",
            "source_spans": "Net margin reached 71.5% for the quarter.",
            "source_context_before": "Before context.",
            "source_context_after": "After context.",
            "entities": "[]",
            "factors": "[]",
            "direction": "positive",
            "confidence": "0.9",
        }
    )
    return row


def test_render_review_csv_round_trips_through_csv_module():
    import csv
    import io

    text = render_review_csv([_sample_row()])
    reader = csv.DictReader(io.StringIO(text))
    assert reader.fieldnames == list(CSV_FIELDS)
    rows = list(reader)
    assert len(rows) == 1
    assert rows[0]["claim_text"] == "Net margin reached 71.5%."
    for field in REVIEW_FIELDS:
        assert rows[0][field] == ""


def test_render_review_html_contains_claim_and_evidence_and_v3_title():
    metrics = {"total_reports": 1, "total_claims": 1, "total_source_spans": 1, "claims_with_multiple_spans": 0}
    html_text = render_review_html([_sample_row()], metrics)
    assert "<title>Phase 1 Human Review Packet v3</title>" in html_text
    assert "Net margin reached 71.5%." in html_text
    assert "Net margin reached 71.5% for the quarter." in html_text
    for field in REVIEW_FIELDS:
        assert field.replace("_", " ").title() in html_text


def test_render_review_instructions_mentions_evidence_correctness_and_provenance_vs_semantics():
    metrics = {"total_claims": 5, "total_reports": 1, "context_char_limit_each_side": 350}
    text = render_review_instructions(metrics)
    assert "evidence_correctness" in text
    assert "exact-match" in text.lower() or "exact match" in text.lower()
    assert "5 claims" in text
