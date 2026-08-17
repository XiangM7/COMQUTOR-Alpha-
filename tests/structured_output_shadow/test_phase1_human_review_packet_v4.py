"""Phase 1 Master evidence-alignment fix, round 2: focused tests for the
v4 human review packet builder (comqutor_alpha/evaluation/
phase1_human_review_packet_v4.py) -- an additive sibling of the already-
tested v2/v3 packet builders. No Provider calls, no network. Mirrors
test_phase1_human_review_packet_v3.py exactly, one version up.
"""

from __future__ import annotations

import json

import pytest

from comqutor_alpha.evaluation.phase1_human_review_packet_v3 import (
    ALLOWED_REVIEW_VALUES as V3_ALLOWED_REVIEW_VALUES,
    REVIEW_FIELDS as V3_REVIEW_FIELDS,
)
from comqutor_alpha.evaluation.phase1_human_review_packet_v4 import (
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


def test_required_prompt_version_is_the_frozen_v4_identity():
    assert REQUIRED_PROMPT_VERSION == "structured_adapter.claim_extraction_shadow.v4"


def test_review_vocabulary_matches_v3_exactly_so_existing_validator_works_unmodified():
    assert REVIEW_FIELDS == V3_REVIEW_FIELDS
    assert ALLOWED_REVIEW_VALUES == V3_ALLOWED_REVIEW_VALUES


def test_collect_review_rows_rejects_a_v3_prompt_identity_evaluation(tmp_path):
    (tmp_path / "evaluation_metadata.json").write_text(
        json.dumps(
            {
                "prompt_version": "structured_adapter.claim_extraction_shadow.v3",
                "prompt_sha256": "a" * 64,
            }
        ),
        encoding="utf-8",
    )
    with pytest.raises(HumanReviewPacketError) as excinfo:
        collect_review_rows(tmp_path)
    assert excinfo.value.reason_code == PROVENANCE_FAILURE
    assert "prompt_v4_identity_invalid" in excinfo.value.detail


def test_collect_review_rows_rejects_missing_evaluation_metadata(tmp_path):
    with pytest.raises(HumanReviewPacketError):
        collect_review_rows(tmp_path)


def _sample_row() -> dict[str, str]:
    row = dict.fromkeys(CSV_FIELDS, "")
    row.update(
        {
            "review_row_id": "phase1-review-v4-abc123",
            "ticker": "NVDA",
            "agent": "fundamental_agent",
            "report_family": "fundamental",
            "claim_ordinal": "1",
            "shadow_claim_id": "shadow-claim-v1-deadbeef",
            "claim_text": "Backlog reached $4.2 billion.",
            "shadow_evidence_text": "Backlog reached **$4.2 billion**, a record.",
            "source_evidence_text": "Backlog reached **$4.2 billion**, a record.",
            "source_spans": "Backlog reached **$4.2 billion**, a record.",
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
    assert rows[0]["claim_text"] == "Backlog reached $4.2 billion."
    for field in REVIEW_FIELDS:
        assert rows[0][field] == ""


def test_render_review_html_contains_claim_evidence_and_v4_title():
    metrics = {
        "total_reports": 1,
        "accepted_reports": 1,
        "rejected_reports": 0,
        "total_claims": 1,
        "total_source_spans": 1,
        "claims_with_multiple_spans": 0,
    }
    html_text = render_review_html([_sample_row()], metrics)
    assert "<title>Phase 1 Human Review Packet v4</title>" in html_text
    assert "Backlog reached $4.2 billion." in html_text
    assert "Backlog reached **$4.2 billion**, a record." in html_text


def test_render_review_instructions_mentions_markdown_root_cause_and_evidence_correctness():
    metrics = {
        "total_claims": 5,
        "total_reports": 24,
        "accepted_reports": 20,
        "rejected_reports": 4,
        "context_char_limit_each_side": 350,
    }
    text = render_review_instructions(metrics)
    assert "evidence_correctness" in text
    assert "Markdown" in text
    assert "5 claims" in text
    assert "20 of 24" in text
    assert "4 report(s)" in text
