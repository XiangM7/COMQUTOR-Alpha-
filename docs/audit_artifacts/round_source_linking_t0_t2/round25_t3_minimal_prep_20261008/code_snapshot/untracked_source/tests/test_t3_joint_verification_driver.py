"""Tests for the joint (multi-stage) T3 verification driver
(docs/audit_artifacts/round_source_linking_t0_t2/t3_joint_verification_driver.py).

Every test uses FIXED, synthetic fixture data (a fake run directory built
here, never a real Fresh Run) -- per the task's own explicit instruction,
this only proves the entry point is RUNNABLE end to end and produces the
right shape; it is never presented as a measurement of real model quality.
Zero network, zero paid Provider calls (the Alpha-classification stage uses
a fixed-response fake gateway, the same convention already used by
tests/test_t3_diagnostic_evaluation_driver.py).
"""

from __future__ import annotations

import importlib.util
import json
import sys
import uuid
from pathlib import Path

_DRIVER_PATH = (
    Path(__file__).resolve().parents[1]
    / "docs/audit_artifacts/round_source_linking_t0_t2/t3_joint_verification_driver.py"
)
_spec = importlib.util.spec_from_file_location("t3_joint_verification_driver", _DRIVER_PATH)
driver = importlib.util.module_from_spec(_spec)
sys.modules[_spec.name] = driver
_spec.loader.exec_module(driver)


class _FixedResponse:
    def __init__(self, content):
        self.content = content


class _FixedModel:
    def __init__(self, response_text):
        self.response_text = response_text

    def invoke(self, _prompt):
        return _FixedResponse(self.response_text)


def _build_fixture_run(tmp_path: Path, *, alpha_decision="select", selected_alpha_id="A501"):
    """A minimal, self-contained fake run directory with just enough real
    shape for every stage to execute -- not real research output."""
    run_id = f"fixture-{uuid.uuid4().hex[:8]}"
    ticker = "NVDA"
    run_dir = tmp_path / run_id
    run_dir.mkdir()

    (run_dir / "metadata.json").write_text(
        json.dumps({"ticker": ticker, "run_id": run_id, "evidence_cutoff": "2026-09-30T00:00:00Z"})
    )

    claim_id = f"{run_id}:news_agent:news_report:claim:1"
    claim_text = "Recession risk is elevated as credit spreads widen sharply."
    claims = [
        {
            "run_id": run_id,
            "ticker": ticker,
            "claim_id": claim_id,
            "agent_output_id": f"{run_id}:news_agent:news_report",
            "claim": claim_text,
            "evidence": claim_text,
            "factors": [],
            "direction": "negative",
            "cited_source_id": "frag-1",
        }
    ]
    (run_dir / "structured_agent_outputs.json").write_text(json.dumps({"claims": claims}))
    (run_dir / "raw_agent_outputs.json").write_text(json.dumps({"agent_outputs": []}))

    sources = [
        {
            "source_id": "src-1",
            "fragment_id": "frag-1",
            "excerpt": "Credit spreads have widened sharply this week, a classic recession-risk signal noted by strategists.",
            "content_hash": "deadbeef" * 8,
            "published_at": "2026-09-29T00:00:00Z",
            "title": "Credit spreads widen",
            "url": "https://example.invalid/article",
        }
    ]
    (run_dir / "source_registry.json").write_text(json.dumps({"sources": sources}))

    # Alpha classification's real match_claim_to_alpha reads alpha_matches.json
    # only via save_alpha_matches in production; this driver calls
    # map_claim_to_alpha directly on the claim dict, so no alpha_matches.json
    # is needed for THAT stage -- but run_formal_eligibility_stage's own
    # _ticker_is_evaluable check does require these files to exist.
    (run_dir / "alpha_matches.json").write_text(
        json.dumps({"run_id": run_id, "ticker": ticker, "matches": [
            {"claim_id": claim_id, "matched_alpha": selected_alpha_id if alpha_decision == "select" else None,
             "match_status": "matched" if alpha_decision == "select" else "no_match"}
        ]})
    )
    (run_dir / "alpha_activations.json").write_text(json.dumps({"run_id": run_id, "ticker": ticker, "activations": []}))
    (run_dir / "conflicts.json").write_text(json.dumps({"run_id": run_id, "ticker": ticker, "conflicts": []}))
    (run_dir / "structure_graph.json").write_text(json.dumps({"run_id": run_id, "ticker": ticker, "nodes": [], "edges": []}))

    return run_dir, run_id, claim_id


def _fake_gateway(response_json):
    from comqutor_alpha.llm_runtime.session import SemanticRuntimeSession
    from comqutor_alpha.structure_engine.week2_llm import Week2LLMGateway

    def factory(run_id, output_root):
        run_dir = Path(output_root) / run_id
        run_dir.mkdir(parents=True, exist_ok=True)
        session = SemanticRuntimeSession(
            run_id=run_id, output_directory=run_dir, execution_mode="test",
            provider="fake-provider", model="fake-model",
        )
        gateway = Week2LLMGateway(
            _FixedModel(response_json), run_id=run_id, output_root=output_root,
            timeout_seconds=0.2, max_retries=0, max_calls=50,
            provider="fake-provider", model_name="fake-model", semantic_runtime=session,
        )
        return gateway
    return factory


def test_joint_verification_runs_end_to_end_with_fixed_fixture_data(tmp_path):
    run_dir, run_id, claim_id = _build_fixture_run(tmp_path, alpha_decision="select", selected_alpha_id="A501")
    gateway = _fake_gateway(json.dumps({"decision": "select", "selected_alpha_id": "A501"}))(
        "gateway-run", tmp_path
    )

    result = driver.run_joint_verification(run_dir, llm_gateway=gateway, fixture_mode=True)

    assert result.run_id == run_id
    assert result.ticker == "NVDA"
    assert len(result.claim_records) == 1

    record = result.claim_records[0]
    assert record.claim_id == claim_id
    assert record.human_reference is None  # never fabricated

    stages = record.system_output
    # Stage 1: source link -- the cited_source_id resolves against the real registry.
    assert stages["source_link"]["status"] == "VALID"
    assert stages["source_link"]["linked_source_id"] == "src-1"
    # Stage 2: content support -- honestly PENDING_REVIEW, never a fabricated verdict.
    assert stages["content_support"]["status"] == "PENDING_REVIEW"
    # Stage 3: Alpha -- real map_claim_to_alpha call through the fixed gateway.
    assert stages["alpha_classification"]["status"] == "MATCHED"
    assert stages["alpha_classification"]["matched_alpha"] == "A501"
    # Stage 4: stance -- ran because an Alpha was matched.
    assert stages["stance"]["status"] != "NOT_APPLICABLE_NO_ALPHA_MATCHED"

    # Stage 5: formal eligibility ran the REAL run_formal_acceptance and
    # returned SOME real, structured verdict -- never crashed, never faked.
    assert "formal_status" in result.formal_eligibility


def test_joint_verification_reports_no_candidate_source_honestly(tmp_path):
    run_dir, run_id, claim_id = _build_fixture_run(tmp_path)
    # Break the source link deliberately: wrong cited id, no content overlap.
    structured = json.loads((run_dir / "structured_agent_outputs.json").read_text())
    structured["claims"][0]["cited_source_id"] = "does-not-exist"
    structured["claims"][0]["evidence"] = "Completely unrelated text with no overlap at all."
    (run_dir / "structured_agent_outputs.json").write_text(json.dumps(structured))

    gateway = _fake_gateway(json.dumps({"decision": "none", "selected_alpha_id": None}))("gateway-run2", tmp_path)
    result = driver.run_joint_verification(run_dir, llm_gateway=gateway, fixture_mode=True)

    stage = result.claim_records[0].system_output["source_link"]
    assert stage["status"] == "UNKNOWN_ID"
    assert stage["exclusion_reason"] == "UNKNOWN_ID"
    # content support correctly reports NOT_APPLICABLE, not a fabricated review.
    assert result.claim_records[0].system_output["content_support"]["status"] == "NOT_APPLICABLE_NO_VALID_SOURCE_LINK"


def test_joint_verification_reports_no_alpha_matched_and_stance_not_applicable(tmp_path):
    run_dir, run_id, claim_id = _build_fixture_run(tmp_path, alpha_decision="none")
    gateway = _fake_gateway(json.dumps({"decision": "none", "selected_alpha_id": None}))("gateway-run3", tmp_path)
    result = driver.run_joint_verification(run_dir, llm_gateway=gateway, fixture_mode=True)

    record = result.claim_records[0]
    assert record.system_output["alpha_classification"]["status"] == "NO_MATCH"
    assert record.system_output["alpha_classification"]["matched_alpha"] is None
    assert record.system_output["stance"]["status"] == "NOT_APPLICABLE_NO_ALPHA_MATCHED"


def test_joint_verification_write_produces_records_and_summary_never_only_aggregate_score(tmp_path):
    run_dir, run_id, claim_id = _build_fixture_run(tmp_path)
    gateway = _fake_gateway(json.dumps({"decision": "select", "selected_alpha_id": "A501"}))("gateway-run4", tmp_path)
    result = driver.run_joint_verification(run_dir, llm_gateway=gateway, fixture_mode=True)

    output_dir = tmp_path / "joint_output"
    result.write(output_dir)

    records_path = output_dir / "joint_verification_records.jsonl"
    summary_path = output_dir / "joint_verification_summary.json"
    assert records_path.exists()
    assert summary_path.exists()

    records = [json.loads(line) for line in records_path.read_text().splitlines() if line]
    assert len(records) == 1
    assert set(records[0]["system_output"].keys()) == {"source_link", "content_support", "alpha_classification", "stance"}

    summary = json.loads(summary_path.read_text())
    assert summary["fixture_mode"] is True
    assert summary["claim_count"] == 1
    # per-stage status counts, not a single aggregate Alpha score.
    assert "source_link" in summary["stage_status_counts"]
    assert "alpha_classification" in summary["stage_status_counts"]
    assert "formal_eligibility" in summary


def test_formal_eligibility_stage_reports_real_not_evaluable_when_artifacts_missing(tmp_path):
    run_dir, run_id, claim_id = _build_fixture_run(tmp_path)
    (run_dir / "conflicts.json").unlink()  # simulate a genuinely incomplete run

    result = driver.run_formal_eligibility_stage("NVDA", run_id, run_dir)
    # run_formal_acceptance itself must report the REAL incomplete state --
    # never silently treated as "pass" because most files exist.
    assert result["formal_status"] in ("NOT_EVALUABLE", "not_evaluable") or "NOT_EVALUABLE" in str(result.get("formal_status", "")).upper()
