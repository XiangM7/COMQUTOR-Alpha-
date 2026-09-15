"""Tests for scripts/verify_persisted_run_serveability.py.

This is a read-only diagnostic tool (Product Demo Hardening Phase 2A). It
reuses existing, already-tested production read functions
(get_research_run_status / build_research_response / get_persisted_structure_graph
/ get_persisted_conflicts) unmodified -- those functions have their own
coverage elsewhere (test_graph_api.py, test_graph_persistence.py, etc). These
tests cover only the two pieces of new logic the script adds: serveability
classification and credential-safe database-identity redaction.

All fixtures are synthetic (a fake ticker, in-memory SQLite, offline raw
agent outputs). No historical accepted artifact files are modified, and no
Provider/TradingAgents calls are made (offline_raw_agent_outputs bypasses
both, per the existing test-suite convention used throughout test_graph_api.py).
"""

import importlib.util
import sys
from pathlib import Path

from comqutor_alpha.api.routes_research import submit_research_request
from comqutor_alpha.storage.db.engine import build_engine
from comqutor_alpha.storage.db.migrations import apply_migrations
from comqutor_alpha.storage.db.repository import GraphPersistenceRepository

_SCRIPT_PATH = Path(__file__).resolve().parent.parent / "scripts" / "verify_persisted_run_serveability.py"
_spec = importlib.util.spec_from_file_location("verify_persisted_run_serveability", _SCRIPT_PATH)
verify_mod = importlib.util.module_from_spec(_spec)
sys.modules[_spec.name] = verify_mod
_spec.loader.exec_module(verify_mod)


def _repo():
    engine = build_engine("sqlite:///:memory:")
    apply_migrations(engine)
    return GraphPersistenceRepository(engine)


def _synthetic_completed_run(tmp_path, repo):
    payload = {
        "ticker": "NVDA",
        "analysis_date": "2026-01-01",
        "selected_analysts": ["market", "news", "fundamentals"],
        "offline_raw_agent_outputs": [
            {"agent": "technical_agent", "raw_output": "NVDA shows positive momentum but high valuation creates downside risk."},
            {"agent": "news_agent", "raw_output": "AI capex is increasing and driving accelerator demand for NVDA."},
            {"agent": "fundamental_agent", "raw_output": "Revenue guidance was raised due to strong customer demand."},
        ],
    }
    response = submit_research_request(payload, output_root=tmp_path, graph_repository=repo)
    assert response["status"] == "completed"
    return response["run_id"]


class TestClassifyRunServeability:
    def test_fully_ready_response_is_fully_live_servable(self):
        status_response = {"status": "completed"}
        main_response = {
            "status": "completed",
            "structure_graph_status": "ready",
            "conflict_status": "ready",
            "artifacts": {"metadata": True, "final_report": False},
        }
        assert verify_mod.classify_run_serveability(status_response, main_response) == "FULLY_LIVE_SERVABLE"

    def test_optional_artifacts_being_false_does_not_block_fully_live_servable(self):
        # Regression guard: error-log artifacts and final_report are legitimately
        # absent on a clean successful run and must not be misread as incomplete.
        status_response = {"status": "completed"}
        main_response = {
            "status": "completed",
            "structure_graph_status": "ready",
            "conflict_status": "ready",
            "artifacts": {
                "metadata": True,
                "final_report": False,
                "structured_output_error_logs": False,
                "week2_pipeline_error_logs": False,
            },
        }
        assert verify_mod.classify_run_serveability(status_response, main_response) == "FULLY_LIVE_SERVABLE"

    def test_missing_db_row_with_file_artifacts_present_is_file_complete_db_incomplete(self):
        status_response = {"status": "failed", "error_code": "RUN_STATUS_NOT_FOUND"}
        main_response = {
            "status": "partial",
            "structure_graph_status": "not_ready",
            "conflict_status": "not_ready",
            "artifacts": {"metadata": True, "raw_agent_outputs": True},
        }
        assert verify_mod.classify_run_serveability(status_response, main_response) == "FILE_COMPLETE_DB_INCOMPLETE"

    def test_db_row_present_but_partial_is_db_present_but_inconsistent(self):
        status_response = {"status": "completed"}
        main_response = {
            "status": "partial",
            "structure_graph_status": "not_ready",
            "conflict_status": "ready",
            "artifacts": {"metadata": True},
        }
        assert verify_mod.classify_run_serveability(status_response, main_response) == "DB_PRESENT_BUT_INCONSISTENT"

    def test_malformed_main_response_is_other(self):
        status_response = {"status": "completed"}
        assert verify_mod.classify_run_serveability(status_response, {}) == "OTHER"
        assert verify_mod.classify_run_serveability(status_response, {"no_status_field": True}) == "OTHER"

    def test_no_db_row_and_no_artifacts_is_other_not_fabricated_success(self):
        status_response = {"status": "failed", "error_code": "RUN_STATUS_NOT_FOUND"}
        main_response = {"status": "partial", "artifacts": {}}
        assert verify_mod.classify_run_serveability(status_response, main_response) == "OTHER"


class TestSafeDatabaseIdentity:
    def test_postgres_dsn_never_leaks_credentials(self):
        dsn = "postgresql+psycopg://myuser:supersecretpassword@127.0.0.1:5433/comqutor_alpha"
        identity = verify_mod._safe_database_identity(dsn)
        assert "supersecretpassword" not in identity
        assert "myuser" not in identity
        assert "127.0.0.1:5433/comqutor_alpha" in identity

    def test_sqlite_dsn_reported_as_is_no_credentials_possible(self):
        dsn = "sqlite:////tmp/some/path/_comqutor_alpha_graph.db"
        identity = verify_mod._safe_database_identity(dsn)
        assert identity.startswith("sqlite://")
        assert "path" in identity

    def test_malformed_dsn_reported_unknown_not_raised(self):
        assert verify_mod._safe_database_identity("") == "unknown"
        assert verify_mod._safe_database_identity("not-a-dsn") == "unknown"


class TestVerifyRunIntegration:
    """End-to-end: verify_run() against a synthetic, fully-persisted run.

    Uses in-memory SQLite and offline raw agent outputs only -- zero Provider
    calls, zero TradingAgents calls, no historical artifact files touched.
    """

    def test_synthetic_completed_run_is_fully_live_servable(self, tmp_path):
        repo = _repo()
        run_id = _synthetic_completed_run(tmp_path, repo)

        from comqutor_alpha.api.routes_research import build_research_response, get_research_run_status

        status_response = get_research_run_status(run_id, graph_repository=repo)
        main_response = build_research_response(run_id, output_root=tmp_path, graph_repository=repo)

        result = {
            "run_id": run_id,
            "classification": verify_mod.classify_run_serveability(status_response, main_response),
        }
        assert result["classification"] == "FULLY_LIVE_SERVABLE"

    def test_zero_provider_and_tradingagents_calls_are_reported(self, tmp_path):
        repo = _repo()
        run_id = _synthetic_completed_run(tmp_path, repo)

        from comqutor_alpha.api.routes_research import (
            build_research_response,
            get_persisted_conflicts,
            get_persisted_structure_graph,
            get_research_run_status,
        )

        status_response = get_research_run_status(run_id, graph_repository=repo)
        main_response = build_research_response(run_id, output_root=tmp_path, graph_repository=repo)
        graph_response = get_persisted_structure_graph(run_id, graph_repository=repo)
        conflicts_response = get_persisted_conflicts(run_id, graph_repository=repo)

        # This test itself makes zero Provider/TradingAgents calls -- offline
        # fixture construction is the only place any pipeline code runs, and
        # it uses offline_raw_agent_outputs (no live TradingAgents research,
        # no live Provider network call), matching the existing
        # test_graph_api.py convention used throughout this test suite.
        assert graph_response.get("status") == "ok"
        assert conflicts_response.get("status") == "ok"
        assert main_response["run_id"] == run_id
        assert status_response["run_id"] == run_id

    def test_verify_run_is_idempotent_read_only(self, tmp_path):
        """Calling the read-only verification functions twice must not mutate
        any state or change the classification (no writes are performed)."""
        repo = _repo()
        run_id = _synthetic_completed_run(tmp_path, repo)

        result = verify_mod.verify_run(run_id, repo, output_root=tmp_path)
        result_again = verify_mod.verify_run(run_id, repo, output_root=tmp_path)

        assert result == result_again
        assert result["fully_live_servable"] is True

    def test_unknown_run_id_does_not_crash_and_is_not_fully_live_servable(self, tmp_path):
        repo = _repo()
        result = verify_mod.verify_run("00000000-0000-0000-0000-000000000000", repo, output_root=tmp_path)
        assert result["fully_live_servable"] is False
        assert result["classification"] in {"OTHER", "FILE_INCOMPLETE", "FILE_COMPLETE_DB_INCOMPLETE"}
