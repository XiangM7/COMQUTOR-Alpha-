from __future__ import annotations

import csv
import hashlib
import io
import json
import socket
from pathlib import Path

import pytest

from comqutor_alpha.evaluation.phase1_human_review_packet import (
    PROVENANCE_FAILURE,
    REVIEW_FIELDS,
    HumanReviewPacketError,
    build_review_packet,
)
from scripts import run_phase1_master as master

TICKERS = ("NVDA", "QQQ", "MSFT", "SNDK", "TSM", "AMD")
FAMILY_TO_AGENT = {
    "fundamental": "fundamental_agent",
    "news": "news_agent",
    "sentiment": "sentiment_agent",
    "technical": "market_agent",
}


def _write_json(path: Path, payload) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, indent=2) + "\n", encoding="utf-8")


def _build_fixture(tmp_path: Path) -> tuple[Path, Path]:
    evaluation_dir = tmp_path / "phase1-evaluation"
    evaluation_dir.mkdir()
    original_csv = evaluation_dir / "phase1_human_review.csv"
    original_csv.write_text("original,audit\nkeep,me\n", encoding="utf-8")
    _write_json(
        evaluation_dir / "evaluation_metadata.json",
        {
            "prompt_version": "structured_adapter.claim_extraction_shadow.v2",
            "prompt_sha256": "prompt-v2-hash",
            "human_labels_created": False,
            "semantic_quality": "UNPROVEN",
            "production_authority": "LEGACY_ADAPTER",
        },
    )

    for ticker in TICKERS:
        for family, agent in FAMILY_TO_AGENT.items():
            report_dir = evaluation_dir / "reports" / ticker / family
            report_text = f"Before {ticker} {family}. Exact evidence. After source context."
            quote = "Exact evidence."
            start = report_text.index(quote)
            end = start + len(quote)
            agent_output_id = f"source-{ticker}:{agent}:report"
            claim_id = f"shadow-{ticker}-{family}"
            source_hash = hashlib.sha256(report_text.encode()).hexdigest()
            source_spans = [{"start": start, "end": end, "exact_quote": quote}]
            if ticker == "NVDA" and family == "fundamental":
                second_quote = "After source context."
                second_start = report_text.index(second_quote)
                source_spans.append(
                    {
                        "start": second_start,
                        "end": second_start + len(second_quote),
                        "exact_quote": second_quote,
                    }
                )
            claim = {
                "shadow_claim_id": claim_id,
                "claim": f"Claim for {ticker} {family}",
                "evidence": quote,
                "source_spans": source_spans,
                "entities": [ticker],
                "factors": ["AI Demand"],
                "direction": "positive",
                "confidence": 0.9,
            }
            bundle = {
                "schema_version": "comqutor.structured_claim_shadow.v1",
                "run_id": f"evaluation-{ticker}-{family}",
                "ticker": ticker,
                "agent": agent,
                "agent_output_id": agent_output_id,
                "source_report_sha256": source_hash,
                "prompt_version": "structured_adapter.claim_extraction_shadow.v2",
                "prompt_sha256": "prompt-v2-hash",
                "claims": [claim],
                "abstentions": [],
            }
            source = {
                "run_id": bundle["run_id"],
                "source_run_id": f"source-{ticker}",
                "ticker": ticker,
                "agent": agent,
                "agent_output_id": agent_output_id,
                "report_text": report_text,
                "report_sha256": source_hash,
            }
            result = {
                "provider_status": "success",
                "validation_status": "accepted",
                "shadow_status": "accepted",
                "validation_accepted": True,
                "prompt_version": bundle["prompt_version"],
                "prompt_sha256": bundle["prompt_sha256"],
            }
            validation = {"status": "accepted", "valid": True, "reason_codes": []}
            legacy = [
                {
                    "claim_id": f"legacy-{ticker}-{family}",
                    "claim": f"Legacy claim for {ticker} {family}",
                    "evidence": quote,
                }
            ]
            comparison = {
                "exact_text_overlaps": (
                    [
                        {
                            "legacy_record_id": f"legacy-{ticker}-{family}",
                            "shadow_claim_id": claim_id,
                            "overlap_basis": "evidence",
                        }
                    ]
                    if ticker == "NVDA" and family == "fundamental"
                    else []
                )
            }
            _write_json(report_dir / "shadow_bundle.json", bundle)
            _write_json(report_dir / "source_report_snapshot.json", source)
            _write_json(report_dir / "report_result.json", result)
            _write_json(report_dir / "validation_report.json", validation)
            _write_json(report_dir / "legacy_claims_snapshot.json", legacy)
            _write_json(report_dir / "legacy_vs_shadow_comparison.json", comparison)

    state_path = tmp_path / "phase1_master_state.json"
    _write_json(
        state_path,
        {
            "current_state": "WAITING_FOR_HUMAN_REVIEW",
            "evaluation_dir": f"outputs/evaluations/{evaluation_dir.name}",
            "prompt_version_in_use": "structured_adapter.claim_extraction_shadow.v2",
            "prompt_sha256_in_use": "prompt-v2-hash",
        },
    )
    return evaluation_dir, state_path


def test_build_packet_is_provider_zero_self_contained_and_preserves_inputs(
    tmp_path,
    monkeypatch,
):
    evaluation_dir, state_path = _build_fixture(tmp_path)
    original_csv_bytes = (evaluation_dir / "phase1_human_review.csv").read_bytes()
    state_bytes = state_path.read_bytes()

    def forbidden(*_args, **_kwargs):
        raise AssertionError("network access attempted")

    monkeypatch.setattr(socket, "create_connection", forbidden)
    verification = build_review_packet(
        evaluation_dir,
        master_state_path=state_path,
        context_chars=250,
    )

    assert verification["provider_calls"] == 0
    assert verification["coverage"]["total_reports"] == 24
    assert verification["coverage"]["total_claims"] == 24
    assert verification["coverage"]["claims_with_multiple_spans"] == 1
    assert all(verification["checks"].values())
    assert (evaluation_dir / "phase1_human_review.csv").read_bytes() == original_csv_bytes
    assert state_path.read_bytes() == state_bytes

    rows = list(
        csv.DictReader(
            io.StringIO(
                (evaluation_dir / "phase1_human_review_v2.csv").read_text(
                    encoding="utf-8"
                )
            )
        )
    )
    assert len(rows) == 24
    assert all(all(row[field] == "" for field in REVIEW_FIELDS) for row in rows)
    matched = next(row for row in rows if row["legacy_record_id"])
    assert matched["legacy_claim_text"].startswith("Legacy claim")
    assert "[SPAN 2" in matched["source_spans"]
    assert matched["claim_text"].startswith("Claim for")

    html_text = (evaluation_dir / "phase1_human_review_v2.html").read_text(
        encoding="utf-8"
    )
    assert "SHADOW CLAIM" in html_text
    assert "HUMAN REVIEW" in html_text
    assert "external" not in html_text.lower()


def test_source_span_mismatch_fails_closed_before_packet_write(tmp_path):
    evaluation_dir, state_path = _build_fixture(tmp_path)
    bundle_path = evaluation_dir / "reports/NVDA/fundamental/shadow_bundle.json"
    bundle = json.loads(bundle_path.read_text(encoding="utf-8"))
    bundle["claims"][0]["source_spans"][0]["exact_quote"] = "silently repaired"
    _write_json(bundle_path, bundle)

    with pytest.raises(HumanReviewPacketError) as caught:
        build_review_packet(evaluation_dir, master_state_path=state_path)

    assert caught.value.reason_code == PROVENANCE_FAILURE
    assert "source_span_mismatch" in caught.value.detail
    assert not (evaluation_dir / "phase1_human_review_v2.csv").exists()
    assert not (evaluation_dir / "phase1_human_review_v2.html").exists()


def _completed_v2_csv(template_path: Path, destination: Path) -> list[dict[str, str]]:
    rows = list(csv.DictReader(io.StringIO(template_path.read_text(encoding="utf-8"))))
    values = {
        "semantic_fidelity": "PASS",
        "claim_boundary": "PASS",
        "evidence_correctness": "PASS",
        "entity_correctness": "PASS",
        "factor_correctness": "PASS",
        "direction_correctness": "PASS",
        "critical_error_type": "NONE",
        "overall_disposition": "ACCEPT",
        "severity": "NONE",
        "reviewer": "human-reviewer",
        "review_timestamp": "2026-08-07T20:00:00Z",
        "notes": "",
    }
    for row in rows:
        row.update(values)
    buffer = io.StringIO(newline="")
    writer = csv.DictWriter(buffer, fieldnames=rows[0].keys(), lineterminator="\n")
    writer.writeheader()
    writer.writerows(rows)
    destination.write_text(buffer.getvalue(), encoding="utf-8")
    return rows


def test_master_accepts_completed_v2_and_rejects_semantic_column_changes(tmp_path):
    evaluation_dir, state_path = _build_fixture(tmp_path)
    build_review_packet(evaluation_dir, master_state_path=state_path)
    template_path = evaluation_dir / "phase1_human_review_v2.csv"
    original_rows = list(
        csv.DictReader(io.StringIO(template_path.read_text(encoding="utf-8")))
    )
    completed_path = tmp_path / "completed.csv"
    completed_rows = _completed_v2_csv(template_path, completed_path)

    result = master.validate_human_review_csv(original_rows, completed_path)
    assert result["valid"] is True, result["errors"]
    assert result["template_version"] == "v2"
    assert result["rows"][0]["review_label"] == "accept"
    assert result["rows"][0]["severity"] == "none"

    completed_rows[0]["claim_text"] = "human must not edit semantic content"
    buffer = io.StringIO(newline="")
    writer = csv.DictWriter(
        buffer,
        fieldnames=completed_rows[0].keys(),
        lineterminator="\n",
    )
    writer.writeheader()
    writer.writerows(completed_rows)
    completed_path.write_text(buffer.getvalue(), encoding="utf-8")
    rejected = master.validate_human_review_csv(original_rows, completed_path)
    assert rejected["valid"] is False
    assert any(error.endswith(":claim_text") for error in rejected["errors"])
