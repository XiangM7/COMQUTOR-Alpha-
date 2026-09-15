"""Alpha Memory Implementation Step 4B -- API exposure tests.

build_research_response() (the existing research-result API path, already
consumed by the frontend) now additively surfaces run_audit.json's own
"alpha_memory" section -- reusing the SAME already-loaded run_audit_for_gate
variable this function already reads for ticker_consistency/
artifact_completeness/evidence_stance_summary, exactly mirroring that
existing pattern. No new file read, no new API route, no write endpoint.

Pure, offline, deterministic. Zero Provider calls, zero TradingAgents
calls.
"""

from __future__ import annotations

import json

from comqutor_alpha.api.routes_research import build_research_response


def _seed_run(tmp_path, run_id, ticker="NVDA"):
    run_dir = tmp_path / run_id
    run_dir.mkdir()
    (run_dir / "metadata.json").write_text(
        json.dumps({"run_id": run_id, "ticker": ticker, "analysis_date": "2026-09-05"}), encoding="utf-8"
    )
    (run_dir / "raw_agent_outputs.json").write_text(
        json.dumps({"run_id": run_id, "ticker": ticker, "agent_outputs": []}), encoding="utf-8"
    )
    return run_dir


_SAMPLE_ALPHA_MEMORY = {
    "mode": "shadow",
    "activation_modulation_applied": False,
    "identity_model": "atomic_edge_phi",
    "identity_version": "alpha_memory.phi_edge.v1",
    "phi_structures": [
        {
            "phi_id": "abc123",
            "ticker": "NVDA",
            "alpha_id": "A101",
            "source": "ai_capex",
            "edge_type": "causal",
            "target": "gpu_demand",
            "is_recurring": True,
            "has_prior_observation": True,
            "prior_observation_count": 5,
            "prior_run_ids": ["run-a", "run-b", "run-c", "run-d", "run-e"],
            "first_seen": "2026-08-01T00:00:00Z",
            "last_seen_prior": "2026-08-20T00:00:00Z",
            "current_seen_at": "2026-09-05T00:00:00Z",
        }
    ],
    "alpha_memory_summary": [
        {
            "alpha_id": "A101",
            "current_phi_count": 5,
            "first_seen_phi_count": 3,
            "recurring_phi_count": 2,
            "recurrence_ratio": 0.4,
            "prior_observation_total": 7,
        }
    ],
    "aggregate_fingerprints": [{"aggregate_fingerprint_id": "xyz789", "alpha_id": "A101"}],
    "instability_signals": {"alpha_attribution_variance": [], "edge_type_variance": []},
}


def _write_run_audit(run_dir, *, alpha_memory=None, extra=None):
    payload = {
        "schema_version": "run_audit.v2",
        "ticker_consistency": "pass",
        "evidence_stance": {"summary": "unchanged"},
    }
    if alpha_memory is not None:
        payload["alpha_memory"] = alpha_memory
    if extra:
        payload.update(extra)
    (run_dir / "run_audit.json").write_text(json.dumps(payload), encoding="utf-8")
    (run_dir / "artifact_manifest.json").write_text(json.dumps({"artifact_completeness": "pass"}), encoding="utf-8")


# ---------------------------------------------------------------------------
# 1. API exposes alpha_memory without changing existing result fields.
# ---------------------------------------------------------------------------


def test_api_exposes_alpha_memory_without_changing_existing_fields(tmp_path):
    run_dir = _seed_run(tmp_path, "run-1")
    _write_run_audit(run_dir, alpha_memory=_SAMPLE_ALPHA_MEMORY)

    response = build_research_response("run-1", output_root=tmp_path)

    assert response["alpha_memory"] == _SAMPLE_ALPHA_MEMORY
    # Pre-existing fields untouched -- same shape/values as before this step.
    assert response["evidence_stance_summary"] == {"summary": "unchanged"}
    assert response["run_id"] == "run-1"
    assert response["ticker"] == "NVDA"
    assert "dominant_alphas" in response
    assert "main_conflict" in response
    assert "unclassified_findings_status" in response


def test_alpha_memory_section_carries_shadow_and_modulation_flag_verbatim(tmp_path):
    run_dir = _seed_run(tmp_path, "run-1")
    _write_run_audit(run_dir, alpha_memory=_SAMPLE_ALPHA_MEMORY)
    response = build_research_response("run-1", output_root=tmp_path)
    assert response["alpha_memory"]["mode"] == "shadow"
    assert response["alpha_memory"]["activation_modulation_applied"] is False


# ---------------------------------------------------------------------------
# Historical run predating Step 1: no alpha_memory section at all -- must
# report None, never a fabricated empty/default structure.
# ---------------------------------------------------------------------------


def test_historical_run_without_alpha_memory_section_reports_none(tmp_path):
    run_dir = _seed_run(tmp_path, "run-old")
    _write_run_audit(run_dir, alpha_memory=None)
    response = build_research_response("run-old", output_root=tmp_path)
    assert response["alpha_memory"] is None


def test_run_with_no_run_audit_json_at_all_reports_none(tmp_path):
    _seed_run(tmp_path, "run-no-audit")
    response = build_research_response("run-no-audit", output_root=tmp_path)
    assert response["alpha_memory"] is None
