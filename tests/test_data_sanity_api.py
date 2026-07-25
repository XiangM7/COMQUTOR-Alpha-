"""API-contract tests for the Data Sanity Cross-Check v1 additive fields on
the canonical Research response and run_audit.json, plus the end-to-end
non-blocking guarantee (a Data Sanity failure never affects Research
completion, Activation, the Structure Graph, or Conflict detection)."""

from __future__ import annotations

import json

from comqutor_alpha.api.routes_research import (
    build_research_response,
    build_run_audit_payload,
    run_research_request,
)
from tests.test_week3_nvda_sanity import _nvda_offline_outputs


def _seed_run(tmp_path, run_id, ticker="MU", analysis_date="2026-07-24"):
    run_dir = tmp_path / run_id
    run_dir.mkdir()
    (run_dir / "metadata.json").write_text(
        json.dumps({"run_id": run_id, "ticker": ticker, "analysis_date": analysis_date}), encoding="utf-8"
    )
    (run_dir / "raw_agent_outputs.json").write_text(
        json.dumps({"run_id": run_id, "ticker": ticker, "agent_outputs": []}), encoding="utf-8"
    )
    return run_dir


def _write_data_sanity(run_dir, payload):
    (run_dir / "data_sanity.json").write_text(json.dumps(payload), encoding="utf-8")


def _base_payload(run_id, ticker, status, **overrides):
    payload = {
        "schema_version": "comqutor.data_sanity.v1",
        "run_id": run_id,
        "ticker": ticker,
        "analysis_date": "2026-07-24",
        "provider": "yfinance",
        "provider_version": "1.0",
        "retrieved_at": "2026-07-24T00:00:00Z",
        "status": status,
        "last_available_session": "2026-07-24",
        "analysis_date_has_exact_session": True,
        "summary": {
            "warning_count": 0, "critical_count": 0, "ohlcv_row_count": 1,
            "reported_price_check_count": 0, "split_event_count": 0,
            "reverse_split_event_count": 0, "dividend_event_count": 0,
            "capital_gain_event_count": 0, "extreme_return_count": 0,
        },
        "checks": [],
        "warnings": [],
    }
    payload.update(overrides)
    return payload


class TestResponseStatuses:
    def test_ok_status_reflected(self, tmp_path):
        run_dir = _seed_run(tmp_path, "run-ok")
        _write_data_sanity(run_dir, _base_payload("run-ok", "MU", "ok"))
        response = build_research_response("run-ok", output_root=tmp_path)
        assert response["data_sanity_status"] == "ok"
        assert response["data_sanity_warning_count"] == 0
        assert response["data_sanity_critical_count"] == 0
        assert response["data_sanity_warnings"] == []

    def test_warning_status_reflected(self, tmp_path):
        run_dir = _seed_run(tmp_path, "run-warn")
        payload = _base_payload(
            "run-warn", "MU", "warning",
            summary={
                "warning_count": 1, "critical_count": 0, "ohlcv_row_count": 1,
                "reported_price_check_count": 1, "split_event_count": 0,
                "reverse_split_event_count": 0, "dividend_event_count": 0,
                "capital_gain_event_count": 0, "extreme_return_count": 0,
            },
            warnings=[{"code": "REPORTED_PRICE_MISMATCH", "severity": "warning", "message": "msg", "details": {"claim_id": "c1"}}],
        )
        _write_data_sanity(run_dir, payload)
        response = build_research_response("run-warn", output_root=tmp_path)
        assert response["data_sanity_status"] == "warning"
        assert response["data_sanity_warning_count"] == 1
        assert len(response["data_sanity_warnings"]) == 1
        assert response["data_sanity_warnings"][0]["code"] == "REPORTED_PRICE_MISMATCH"

    def test_critical_status_reflected(self, tmp_path):
        run_dir = _seed_run(tmp_path, "run-crit")
        payload = _base_payload(
            "run-crit", "MU", "critical",
            summary={
                "warning_count": 0, "critical_count": 1, "ohlcv_row_count": 1,
                "reported_price_check_count": 0, "split_event_count": 0,
                "reverse_split_event_count": 0, "dividend_event_count": 0,
                "capital_gain_event_count": 0, "extreme_return_count": 0,
            },
        )
        _write_data_sanity(run_dir, payload)
        response = build_research_response("run-crit", output_root=tmp_path)
        assert response["data_sanity_status"] == "critical"
        assert response["data_sanity_critical_count"] == 1

    def test_unavailable_status_reflected(self, tmp_path):
        run_dir = _seed_run(tmp_path, "run-unavail")
        _write_data_sanity(run_dir, _base_payload("run-unavail", "MU", "unavailable"))
        response = build_research_response("run-unavail", output_root=tmp_path)
        assert response["data_sanity_status"] == "unavailable"

    def test_disabled_status_reflected(self, tmp_path):
        run_dir = _seed_run(tmp_path, "run-disabled")
        _write_data_sanity(run_dir, _base_payload("run-disabled", "MU", "disabled"))
        response = build_research_response("run-disabled", output_root=tmp_path)
        assert response["data_sanity_status"] == "disabled"

    def test_historical_run_without_artifact_is_not_available(self, tmp_path):
        _seed_run(tmp_path, "run-historical")
        response = build_research_response("run-historical", output_root=tmp_path)
        assert response["data_sanity_status"] == "not_available"
        assert response["data_sanity_warning_count"] == 0
        assert response["data_sanity_critical_count"] == 0
        assert response["data_sanity_warnings"] == []


class TestSafeFieldsAndContractMismatch:
    def test_malformed_artifact_degrades_safely(self, tmp_path):
        run_dir = _seed_run(tmp_path, "run-malformed")
        (run_dir / "data_sanity.json").write_text(json.dumps({"not": "a valid contract"}), encoding="utf-8")
        response = build_research_response("run-malformed", output_root=tmp_path)
        assert response["data_sanity_status"] == "not_available"
        assert response["data_sanity_warnings"] == []

    def test_unsafe_detail_values_are_stripped(self, tmp_path):
        run_dir = _seed_run(tmp_path, "run-unsafe")
        payload = _base_payload(
            "run-unsafe", "MU", "warning",
            warnings=[
                {
                    "code": "REPORTED_PRICE_MISMATCH",
                    "severity": "warning",
                    "message": "msg",
                    "details": {
                        "claim_id": "c1",
                        "local_path": "/Users/someone/secret.env",
                        "db_url": "postgresql://user:pw@host/db",
                        "reported_price": 100.0,
                    },
                }
            ],
        )
        _write_data_sanity(run_dir, payload)
        response = build_research_response("run-unsafe", output_root=tmp_path)
        details = response["data_sanity_warnings"][0]["details"]
        assert "local_path" not in details
        assert "db_url" not in details
        assert details["claim_id"] == "c1"
        assert details["reported_price"] == 100.0

    def test_malformed_warning_entry_dropped_not_partially_trusted(self, tmp_path):
        run_dir = _seed_run(tmp_path, "run-bad-warning")
        payload = _base_payload(
            "run-bad-warning", "MU", "warning",
            warnings=[{"code": "X", "severity": 42, "message": "msg"}, {"not": "a warning"}],
        )
        _write_data_sanity(run_dir, payload)
        response = build_research_response("run-bad-warning", output_root=tmp_path)
        assert response["data_sanity_warnings"] == []

    def test_response_never_leaks_exception_or_path(self, tmp_path):
        run_dir = _seed_run(tmp_path, "run-leak-check")
        _write_data_sanity(run_dir, _base_payload("run-leak-check", "MU", "unavailable"))
        response = build_research_response("run-leak-check", output_root=tmp_path)
        text = json.dumps(response)
        for forbidden in ("/Users/", "Traceback", "postgresql://", "Bearer "):
            assert forbidden not in text


class TestRunAuditIntegration:
    def test_run_audit_includes_data_sanity_fields(self, tmp_path):
        run_dir = _seed_run(tmp_path, "run-audit")
        (run_dir / "structured_agent_outputs.json").write_text(
            json.dumps({"run_id": "run-audit", "ticker": "MU", "records": []}), encoding="utf-8"
        )
        (run_dir / "alpha_matches.json").write_text(json.dumps({"matches": []}), encoding="utf-8")
        payload = _base_payload(
            "run-audit", "MU", "warning",
            summary={
                "warning_count": 2, "critical_count": 1, "ohlcv_row_count": 5,
                "reported_price_check_count": 3, "split_event_count": 0,
                "reverse_split_event_count": 0, "dividend_event_count": 0,
                "capital_gain_event_count": 0, "extreme_return_count": 0,
            },
        )
        _write_data_sanity(run_dir, payload)
        (run_dir / "market_data_snapshot.json").write_text(
            json.dumps({"rows": [{"date": "2026-07-24"}] * 5}), encoding="utf-8"
        )
        audit = build_run_audit_payload("run-audit", tmp_path)
        assert audit["data_sanity_status"] == "warning"
        assert audit["data_sanity_warning_count"] == 2
        assert audit["data_sanity_critical_count"] == 1
        assert audit["market_data_row_count"] == 5
        assert audit["reported_price_check_count"] == 3

    def test_run_audit_unaffected_by_missing_data_sanity(self, tmp_path):
        _seed_run(tmp_path, "run-audit-none")
        audit = build_run_audit_payload("run-audit-none", tmp_path)
        assert audit["data_sanity_status"] == "not_available"
        assert audit["market_data_row_count"] == 0
        assert audit["reported_price_check_count"] == 0
        # Unrelated counters still computed normally.
        assert "raw_agent_output_count" in audit


class TestEndToEndNonBlocking:
    def _nvda_payload(self):
        return {
            "ticker": "NVDA",
            "analysis_date": "2026-06-30",
            "selected_analysts": ["market", "news", "fundamentals", "sentiment"],
            "offline_raw_agent_outputs": _nvda_offline_outputs(),
        }

    def test_data_sanity_failure_never_blocks_completion_or_downstream_pipeline(
        self, tmp_path, monkeypatch
    ):
        import comqutor_alpha.api.routes_research as routes_research

        def _broken_stage(*_args, **_kwargs):
            raise RuntimeError("simulated unexpected bug in the data sanity sidecar")

        monkeypatch.setattr(routes_research, "run_data_sanity_stage", _broken_stage)

        response = run_research_request(self._nvda_payload(), output_root=tmp_path)
        assert response["status"] == "completed"
        assert response["structure_graph_status"] == "ready"
        assert response["conflict_status"] == "ready"

    def test_disabled_data_sanity_does_not_affect_completion(self, tmp_path, monkeypatch):
        monkeypatch.delenv("COMQUTOR_DATA_SANITY_ENABLED", raising=False)
        response = run_research_request(self._nvda_payload(), output_root=tmp_path)
        assert response["status"] == "completed"
        assert response["data_sanity_status"] == "disabled"
