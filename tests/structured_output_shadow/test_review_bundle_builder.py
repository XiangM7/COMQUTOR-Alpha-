from __future__ import annotations

import json
from pathlib import Path

import pytest
from conftest import claim_for

from comqutor_alpha.structure_engine.structured_output_shadow_prompt import (
    STRUCTURED_OUTPUT_SHADOW_PROMPT_SHA256,
    STRUCTURED_OUTPUT_SHADOW_PROMPT_VERSION,
)
from comqutor_alpha.structure_engine.structured_output_shadow_schema import (
    assign_deterministic_claim_ids,
    build_shadow_bundle,
    sha256_text,
)
from scripts.build_phase1a_shadow_review_bundle import (
    build_review_bundle,
    validate_output_directory,
)


def _source_run(tmp_path: Path) -> tuple[Path, str, dict]:
    run_dir = tmp_path / "source-run"
    run_dir.mkdir()
    report = "GPU demand increased in June."
    raw_record = {
        "run_id": "run-shadow-1",
        "ticker": "NVDA",
        "agent": "news_agent",
        "agent_output_id": "run-shadow-1:news_agent:news_report",
        "source_path": "news_report",
        "source_field": "news_report",
        "raw_output": report,
    }
    (run_dir / "raw_agent_outputs.json").write_text(
        json.dumps({"agent_outputs": [raw_record]}), encoding="utf-8"
    )
    (run_dir / "structured_agent_outputs.json").write_text(
        json.dumps(
            {
                "records": [
                    {
                        "claim_id": "legacy-1",
                        "source_agent_output_id": raw_record["agent_output_id"],
                        "claim": report,
                        "evidence": report,
                    }
                ]
            }
        ),
        encoding="utf-8",
    )
    return run_dir, report, raw_record


def test_builder_without_fixture_never_invokes_semantics(tmp_path):
    run_dir, _report, _raw_record = _source_run(tmp_path)
    output_dir = tmp_path / "review-output"
    manifest = build_review_bundle(source_run=run_dir, output_dir=output_dir)
    assert manifest["shadow_output_status"] == "NOT_GENERATED"
    assert manifest["provider_calls"] == 0
    assert manifest["fake_semantic_invoker_calls"] == 0
    assert (output_dir / "blank_human_review.csv").is_file()


def test_builder_uses_explicit_fixture_only(tmp_path):
    run_dir, report, raw_record = _source_run(tmp_path)
    fixture = build_shadow_bundle(
        run_id=raw_record["run_id"],
        ticker=raw_record["ticker"],
        agent=raw_record["agent"],
        agent_output_id=raw_record["agent_output_id"],
        source_report_sha256=sha256_text(report),
        prompt_version=STRUCTURED_OUTPUT_SHADOW_PROMPT_VERSION,
        prompt_sha256=STRUCTURED_OUTPUT_SHADOW_PROMPT_SHA256,
        claims=[claim_for(report, report, source_refs=["news_report"])],
    )
    fixture = assign_deterministic_claim_ids(fixture)
    fixture_path = tmp_path / "fixture.json"
    fixture_path.write_text(json.dumps(fixture), encoding="utf-8")
    output_dir = tmp_path / "review-output"
    manifest = build_review_bundle(
        source_run=run_dir,
        output_dir=output_dir,
        fixture_output=fixture_path,
    )
    assert manifest["shadow_output_status"] == "FIXTURE_GENERATED"
    assert manifest["fake_semantic_invoker_calls"] == 1
    assert manifest["provider_calls"] == 0


def test_builder_rejects_historical_outputs_and_traversal():
    with pytest.raises(ValueError, match="historical outputs"):
        validate_output_directory("outputs/runs/forbidden")
    with pytest.raises(ValueError, match="traversal"):
        validate_output_directory("docs/audit_artifacts/phase1a/../escaped")

