"""Week 3 Security and Reliability Hardening Pass (2026-07-14).

Covers four confirmed issues in the first Week 3 implementation, all
exercised against the real default resolution paths (not just injected
stub repositories) wherever practical:

1. GET /api/research/{run_id}/graph must be a genuinely read-only path: no
   schema migration, no table creation, no local SQLite file creation, no
   mutation of existing rows, stable across repeated calls.
2. Server-side log/artifact leakage: unexpected exceptions must not put a
   DSN, password, path, raw SQL, or traceback into the client response, the
   application log (by default), or the Week 3 JSONL error log.
3. Retry lifecycle: a failed Week 3 attempt must not permanently pin a run
   to partial/not_ready once a later retry succeeds.
4. Docker Compose local Postgres profile must not ship a usable hardcoded
   password or an all-interfaces port binding.

Plus regression coverage for the public input boundary (extra/dangerous
POST fields, path traversal variants against the graph endpoint) and a
documentation contract test locking in the current no-auth deployment
disclosure.
"""

from __future__ import annotations

import json
import logging
import re
import subprocess
from pathlib import Path

import pytest
import yaml

from comqutor_alpha.api.routes_research import (
    WEEK3_PIPELINE_STATUS_ARTIFACT_FILENAME,
    ResearchRequest,
    _model_to_payload,
    build_research_response,
    get_persisted_structure_graph,
    run_research_request,
)
from comqutor_alpha.storage.db.engine import build_engine
from comqutor_alpha.storage.db.migrations import apply_migrations
from comqutor_alpha.storage.db.repository import GraphPersistenceRepository

REPO_ROOT = Path(__file__).resolve().parents[1]

_FORBIDDEN_MARKERS = [
    "/private/user/database.sqlite",
    "postgresql://user:super-secret@host/db",
    "token=secret-value",
    "api_key=secret-value",
    "SELECT ",
    "Traceback",
]


def _secret_bearing_exception() -> RuntimeError:
    return RuntimeError(
        "connection failed: postgresql://user:super-secret@host/db "
        "path=/private/user/database.sqlite token=secret-value api_key=secret-value "
        "while executing SELECT * FROM structure_graphs\nTraceback (most recent call last):"
    )


def _repo():
    engine = build_engine("sqlite:///:memory:")
    apply_migrations(engine)
    return GraphPersistenceRepository(engine)


def _offline_payload():
    return {
        "ticker": "NVDA",
        "analysis_date": "2026-06-30",
        "offline_raw_agent_outputs": [
            {"agent": "news_agent", "raw_output": "AI capex is rising and driving GPU demand."},
        ],
    }


def _seed_week1_2_artifacts(tmp_path, run_id, ticker="NVDA", matches=None):
    """Seed a *complete* Week 1-2 run (all four REQUIRED_COMPLETION_ARTIFACTS)
    so build_research_response's status can actually reach "completed" once
    Week 3 also succeeds -- not just the two artifacts Week 3 itself reads."""
    run_dir = tmp_path / run_id
    run_dir.mkdir()
    (run_dir / "metadata.json").write_text(
        json.dumps({"run_id": run_id, "ticker": ticker, "analysis_date": "2026-06-30"}), encoding="utf-8"
    )
    (run_dir / "raw_agent_outputs.json").write_text(
        json.dumps({"run_id": run_id, "ticker": ticker, "agent_outputs": []}), encoding="utf-8"
    )
    (run_dir / "structured_agent_outputs.json").write_text(
        json.dumps({"run_id": run_id, "ticker": ticker, "records": []}), encoding="utf-8"
    )
    (run_dir / "alpha_matches.json").write_text(
        json.dumps({"run_id": run_id, "ticker": ticker, "matches": matches or []}), encoding="utf-8"
    )
    (run_dir / "extracted_structures.json").write_text(
        json.dumps({"run_id": run_id, "ticker": ticker, "nodes": [], "edges": []}), encoding="utf-8"
    )
    return run_dir


class TestReadOnlyGetBoundary:
    def test_get_graph_never_calls_apply_migrations(self, tmp_path, monkeypatch):
        import comqutor_alpha.storage.db.repository as repository_module

        calls = []
        monkeypatch.setattr(repository_module, "apply_migrations", lambda engine: calls.append(engine))

        run_dir = tmp_path / "some_run"
        run_dir.mkdir()
        (run_dir / "metadata.json").write_text(json.dumps({"run_id": "some_run"}), encoding="utf-8")

        response = get_persisted_structure_graph("some_run", output_root=tmp_path)

        assert calls == []
        assert response["status"] == "failed"

    def test_get_graph_creates_no_output_root_directory_for_unknown_run(self, tmp_path):
        nonexistent_root = tmp_path / "does_not_exist_yet"

        response = get_persisted_structure_graph("some_run_id", output_root=nonexistent_root)

        assert response["status"] == "failed"
        assert response["error_code"] == "RUN_NOT_FOUND"
        assert not nonexistent_root.exists()

    def test_get_graph_default_resolution_creates_no_sqlite_file(self, tmp_path, monkeypatch):
        monkeypatch.delenv("COMQUTOR_ENV", raising=False)
        monkeypatch.delenv("COMQUTOR_DATABASE_URL", raising=False)
        run_dir = tmp_path / "never_persisted_run"
        run_dir.mkdir()
        (run_dir / "metadata.json").write_text(
            json.dumps({"run_id": "never_persisted_run"}), encoding="utf-8"
        )

        response = get_persisted_structure_graph("never_persisted_run", output_root=tmp_path)

        assert response["status"] == "failed"
        assert response["error_code"] == "GRAPH_NOT_READY"
        assert not list(tmp_path.glob("**/_comqutor_alpha_graph.db"))

    def test_get_graph_never_builds_llm_gateway(self, tmp_path):
        import comqutor_alpha.api.routes_research as routes_research

        calls = []
        run_dir = tmp_path / "some_run"
        run_dir.mkdir()
        (run_dir / "metadata.json").write_text(json.dumps({"run_id": "some_run"}), encoding="utf-8")

        original = routes_research.build_server_week2_llm_gateway
        try:
            routes_research.build_server_week2_llm_gateway = lambda *a, **k: calls.append((a, k))
            get_persisted_structure_graph("some_run", output_root=tmp_path)
        finally:
            routes_research.build_server_week2_llm_gateway = original

        assert calls == []

    def test_get_graph_default_path_does_not_mutate_existing_state_and_is_stable(
        self, tmp_path, monkeypatch
    ):
        """End-to-end via the real default (non-injected) repository
        resolution path on both write and read: proves GET never changes an
        existing row (including updated_at) and repeated calls agree."""
        monkeypatch.delenv("COMQUTOR_ENV", raising=False)
        monkeypatch.delenv("COMQUTOR_DATABASE_URL", raising=False)

        response = run_research_request(_offline_payload(), output_root=tmp_path)
        assert response["status"] == "completed"
        run_id = response["run_id"]

        from comqutor_alpha.storage.db.repository import build_repository_from_env

        read_repo = build_repository_from_env(output_root=tmp_path)
        before = read_repo.get_graph(run_id)
        assert before is not None

        for _ in range(3):
            graph = get_persisted_structure_graph(run_id, output_root=tmp_path)
            assert graph["status"] == "ok"

        after = read_repo.get_graph(run_id)
        assert after == before


class TestLogAndResponseLeakage:
    def test_get_graph_unexpected_failure_leaks_nothing_by_default(self, tmp_path, monkeypatch, caplog):
        import comqutor_alpha.api.routes_research as routes_research

        def poison(*_a, **_k):
            raise _secret_bearing_exception()

        monkeypatch.setattr(routes_research, "build_repository_from_env", poison)

        run_dir = tmp_path / "leak_run"
        run_dir.mkdir()
        (run_dir / "metadata.json").write_text(json.dumps({"run_id": "leak_run"}), encoding="utf-8")

        with caplog.at_level(logging.WARNING, logger="comqutor_alpha.api.routes_research"):
            response = routes_research.get_persisted_structure_graph("leak_run", output_root=tmp_path)

        assert response["status"] == "failed"
        assert response["error_code"] == "GRAPH_UNAVAILABLE"
        serialized_response = json.dumps(response)
        default_log_text = "\n".join(r.getMessage() for r in caplog.records)

        for marker in _FORBIDDEN_MARKERS:
            assert marker not in serialized_response
            assert marker not in default_log_text
        assert all(r.exc_info is None for r in caplog.records)

    def test_get_graph_unexpected_failure_traceback_only_at_explicit_debug_level(
        self, tmp_path, monkeypatch, caplog
    ):
        import comqutor_alpha.api.routes_research as routes_research

        def poison(*_a, **_k):
            raise _secret_bearing_exception()

        monkeypatch.setattr(routes_research, "build_repository_from_env", poison)

        run_dir = tmp_path / "leak_run_debug"
        run_dir.mkdir()
        (run_dir / "metadata.json").write_text(json.dumps({"run_id": "leak_run_debug"}), encoding="utf-8")

        with caplog.at_level(logging.DEBUG, logger="comqutor_alpha.api.routes_research"):
            routes_research.get_persisted_structure_graph("leak_run_debug", output_root=tmp_path)

        debug_records = [r for r in caplog.records if r.levelname == "DEBUG"]
        assert len(debug_records) == 1
        assert debug_records[0].exc_info is not None  # explicit local opt-in only

    def test_week3_stage_failure_with_secret_bearing_exception_logs_and_writes_safely(
        self, tmp_path, monkeypatch, caplog
    ):
        import comqutor_alpha.api.routes_research as routes_research

        def poison(*_a, **_k):
            raise _secret_bearing_exception()

        monkeypatch.setattr(routes_research, "build_structure_graph_stage", poison)
        run_id = "stage_leak_run"
        run_dir = _seed_week1_2_artifacts(tmp_path, run_id)

        with caplog.at_level(logging.WARNING, logger="comqutor_alpha.api.routes_research"):
            routes_research._run_week3_graph_pipeline(run_dir)

        jsonl_text = (run_dir / "error_logs" / "week3_pipeline_errors.jsonl").read_text(encoding="utf-8")
        app_log_text = "\n".join(r.getMessage() for r in caplog.records)

        for marker in _FORBIDDEN_MARKERS:
            assert marker not in jsonl_text
            assert marker not in app_log_text
        assert all(r.exc_info is None for r in caplog.records)

        status = json.loads((run_dir / WEEK3_PIPELINE_STATUS_ARTIFACT_FILENAME).read_text(encoding="utf-8"))
        assert status["outcome"] == "failed"
        assert status["stage"] == "structure_graph_construction"
        assert status["run_id"] == run_id


class TestRetryLifecycle:
    def test_construction_failure_then_retry_success_recovers_status(self, tmp_path, monkeypatch):
        import comqutor_alpha.api.routes_research as routes_research

        run_dir = _seed_week1_2_artifacts(tmp_path, "retry_construction")
        repo = _repo()

        monkeypatch.setattr(
            routes_research,
            "build_structure_graph_stage",
            lambda *a, **k: (_ for _ in ()).throw(RuntimeError("boom - construction")),
        )
        routes_research._run_week3_graph_pipeline(run_dir, graph_repository=repo)

        response = build_research_response("retry_construction", output_root=tmp_path, graph_repository=repo)
        assert response["status"] == "partial"
        assert response["structure_graph_status"] == "not_ready"

        monkeypatch.undo()
        routes_research._run_week3_graph_pipeline(run_dir, graph_repository=repo)

        response = build_research_response("retry_construction", output_root=tmp_path, graph_repository=repo)
        assert response["status"] == "completed"
        assert response["structure_graph_status"] == "ready"

        graph = get_persisted_structure_graph(
            "retry_construction", output_root=tmp_path, graph_repository=repo
        )
        assert graph["status"] == "ok"

        # the earlier failure remains auditable
        jsonl_text = (run_dir / "error_logs" / "week3_pipeline_errors.jsonl").read_text(encoding="utf-8")
        assert "structure_graph_construction" in jsonl_text

    def test_scoring_failure_then_retry_success_recovers_status(self, tmp_path, monkeypatch):
        import comqutor_alpha.api.routes_research as routes_research

        run_dir = _seed_week1_2_artifacts(tmp_path, "retry_scoring")
        repo = _repo()

        monkeypatch.setattr(
            routes_research,
            "score_and_assemble_structure_graph",
            lambda *a, **k: (_ for _ in ()).throw(RuntimeError("boom - scoring")),
        )
        routes_research._run_week3_graph_pipeline(run_dir, graph_repository=repo)

        response = build_research_response("retry_scoring", output_root=tmp_path, graph_repository=repo)
        assert response["status"] == "partial"
        assert response["structure_graph_status"] == "not_ready"

        monkeypatch.undo()
        routes_research._run_week3_graph_pipeline(run_dir, graph_repository=repo)

        response = build_research_response("retry_scoring", output_root=tmp_path, graph_repository=repo)
        assert response["status"] == "completed"
        assert response["structure_graph_status"] == "ready"

    def test_persistence_failure_then_retry_success_recovers_status(self, tmp_path):
        import comqutor_alpha.api.routes_research as routes_research

        class _FirstCallFailsRepository:
            def __init__(self, inner):
                self._inner = inner
                self._calls = 0

            def persist_run(self, **kwargs):
                self._calls += 1
                if self._calls == 1:
                    raise RuntimeError("boom - first attempt persistence failure")
                return self._inner.persist_run(**kwargs)

            def get_graph(self, run_id):
                return self._inner.get_graph(run_id)

            def get_alpha_matches(self, run_id):
                return self._inner.get_alpha_matches(run_id)

            def persist_week4_results(self, **kwargs):
                return self._inner.persist_week4_results(**kwargs)

            def get_week4_conflict_result(self, run_id):
                return self._inner.get_week4_conflict_result(run_id)

        run_dir = _seed_week1_2_artifacts(tmp_path, "retry_persistence")
        inner = _repo()
        flaky = _FirstCallFailsRepository(inner)

        routes_research._run_week3_graph_pipeline(run_dir, graph_repository=flaky)
        response = build_research_response("retry_persistence", output_root=tmp_path, graph_repository=flaky)
        assert response["status"] == "partial"
        assert response["structure_graph_status"] == "not_ready"
        assert inner.get_graph("retry_persistence") is None

        routes_research._run_week3_graph_pipeline(run_dir, graph_repository=flaky)
        response = build_research_response("retry_persistence", output_root=tmp_path, graph_repository=flaky)
        assert response["status"] == "completed"
        assert response["structure_graph_status"] == "ready"
        assert inner.get_graph("retry_persistence") is not None

    def test_current_failure_is_not_masked_by_an_earlier_success(self, tmp_path, monkeypatch):
        """The reverse direction of the retry-lifecycle guarantee: a run
        that succeeded once must not keep reporting completed/ready if a
        later attempt (e.g. after an upstream input changed) fails. Every
        attempt overwrites the status marker unconditionally, so this holds
        by construction -- this test pins it down explicitly since it is
        called out as its own pass criterion."""
        import comqutor_alpha.api.routes_research as routes_research

        run_dir = _seed_week1_2_artifacts(tmp_path, "success_then_failure")
        repo = _repo()

        routes_research._run_week3_graph_pipeline(run_dir, graph_repository=repo)
        response = build_research_response("success_then_failure", output_root=tmp_path, graph_repository=repo)
        assert response["status"] == "completed"
        assert response["structure_graph_status"] == "ready"

        monkeypatch.setattr(
            routes_research,
            "build_structure_graph_stage",
            lambda *a, **k: (_ for _ in ()).throw(RuntimeError("boom - later failure")),
        )
        routes_research._run_week3_graph_pipeline(run_dir, graph_repository=repo)

        response = build_research_response("success_then_failure", output_root=tmp_path, graph_repository=repo)
        assert response["status"] == "partial"
        assert response["structure_graph_status"] == "not_ready"

        # GET .../graph queries the database directly and is intentionally
        # independent of these filesystem status signals (see docs section
        # 十: the DB is the Week 3 source of truth). The second attempt
        # failed at construction, before ever touching the DB, so the last
        # genuinely successful persist is still valid, real data -- GET
        # correctly keeps serving it rather than hiding it. The (honest)
        # "not_ready" verdict above is what tells a caller the *latest*
        # attempt did not refresh it.
        graph = get_persisted_structure_graph(
            "success_then_failure", output_root=tmp_path, graph_repository=repo
        )
        assert graph["status"] == "ok"

    def test_repeated_successful_retry_remains_idempotent(self, tmp_path):
        import comqutor_alpha.api.routes_research as routes_research

        run_dir = _seed_week1_2_artifacts(
            tmp_path,
            "retry_idempotent",
            matches=[
                {
                    "claim_id": "c1",
                    "match_status": "no_match",
                    "score": 0.0,
                    "claim": "irrelevant",
                    "evidence": "irrelevant",
                }
            ],
        )
        repo = _repo()

        for _ in range(3):
            routes_research._run_week3_graph_pipeline(run_dir, graph_repository=repo)

        response = build_research_response("retry_idempotent", output_root=tmp_path, graph_repository=repo)
        assert response["status"] == "completed"
        assert len(repo.get_alpha_matches("retry_idempotent")) == 1  # no duplicate rows

    def test_second_failing_retry_reports_its_own_stage_not_the_first_failure(
        self, tmp_path, monkeypatch
    ):
        import comqutor_alpha.api.routes_research as routes_research

        run_dir = _seed_week1_2_artifacts(tmp_path, "retry_double_failure")
        repo = _repo()

        monkeypatch.setattr(
            routes_research,
            "build_structure_graph_stage",
            lambda *a, **k: (_ for _ in ()).throw(RuntimeError("boom - construction")),
        )
        routes_research._run_week3_graph_pipeline(run_dir, graph_repository=repo)
        status = json.loads((run_dir / WEEK3_PIPELINE_STATUS_ARTIFACT_FILENAME).read_text(encoding="utf-8"))
        assert status["stage"] == "structure_graph_construction"

        monkeypatch.undo()
        monkeypatch.setattr(
            routes_research,
            "score_and_assemble_structure_graph",
            lambda *a, **k: (_ for _ in ()).throw(RuntimeError("boom - scoring")),
        )
        routes_research._run_week3_graph_pipeline(run_dir, graph_repository=repo)

        status = json.loads((run_dir / WEEK3_PIPELINE_STATUS_ARTIFACT_FILENAME).read_text(encoding="utf-8"))
        assert status["outcome"] == "failed"
        assert status["stage"] == "activation_scoring"  # latest attempt's own failure

        response = build_research_response("retry_double_failure", output_root=tmp_path, graph_repository=repo)
        assert response["status"] == "partial"
        assert response["structure_graph_status"] == "not_ready"


class TestDockerComposeSecurityDefaults:
    @staticmethod
    def _compose_text() -> str:
        return (REPO_ROOT / "docker-compose.yml").read_text(encoding="utf-8")

    @staticmethod
    def _compose_data() -> dict:
        return yaml.safe_load(TestDockerComposeSecurityDefaults._compose_text())

    def test_no_hardcoded_postgres_password(self):
        text = self._compose_text()
        assert "POSTGRES_PASSWORD=comqutor" not in text
        # every POSTGRES_PASSWORD assignment must be a Compose interpolation,
        # never a bare literal value
        for line in text.splitlines():
            if "POSTGRES_PASSWORD=" in line:
                assert "${POSTGRES_PASSWORD" in line

    def test_no_password_bearing_postgres_url_anywhere_in_file(self):
        text = self._compose_text()
        assert re.search(r"postgresql\+?\w*://\w+:[^@$\s]+@", text) is None

    def test_postgres_password_env_var_is_required_not_defaulted(self):
        env = self._compose_data()["services"]["postgres"]["environment"]
        password_entry = next(e for e in env if e.startswith("POSTGRES_PASSWORD="))
        assert ":?" in password_entry  # Compose "fail if unset" syntax
        assert ":-" not in password_entry  # not a silently-defaulted value

    def test_postgres_port_binds_localhost_only(self):
        ports = self._compose_data()["services"]["postgres"]["ports"]
        assert ports == ["127.0.0.1:5433:5432"]

    def test_postgres_profile_is_gated_and_not_started_by_default(self):
        data = self._compose_data()
        assert data["services"]["postgres"]["profiles"] == ["postgres"]
        default_services = {
            name for name, svc in data["services"].items() if "profiles" not in svc
        }
        assert "postgres" not in default_services

    def test_env_file_is_gitignored_and_not_tracked(self):
        tracked = subprocess.run(
            ["git", "ls-files", ".env"], cwd=REPO_ROOT, capture_output=True, text=True, check=True
        ).stdout.strip()
        assert tracked == ""

        ignored = subprocess.run(
            ["git", "check-ignore", ".env"], cwd=REPO_ROOT, capture_output=True, text=True
        )
        assert ignored.returncode == 0


class TestAuthTenantDocumentationContract:
    def test_deployment_assumptions_are_documented_and_not_overclaimed(self):
        doc_path = REPO_ROOT / "docs" / "week3_completion_report.md"
        text = doc_path.read_text(encoding="utf-8")

        required_phrases = [
            "不是授权凭据",
            "没有 owner_id/tenant_id",
            "不应直接暴露到公网",
            "必须先实现 authentication 与 run ownership",
        ]
        for phrase in required_phrases:
            assert phrase in text, f"missing required deployment-limitation disclosure: {phrase!r}"

        overclaim_phrases = [
            "已支持多租户",
            "已实现 authentication",
            "生产环境已可直接公开",
        ]
        for phrase in overclaim_phrases:
            assert phrase not in text, f"documentation overclaims auth/tenant support: {phrase!r}"


class TestPublicInputBoundary:
    def test_pydantic_request_model_strips_unknown_dangerous_fields(self):
        request = ResearchRequest(
            **{
                "ticker": "NVDA",
                "database_url": "postgresql://evil:evil@attacker.example/db",
                "database_credentials": {"user": "evil"},
                "provider": "evil_provider",
                "model": "evil_model",
                "api_key": "evil-key",
                "llm_enabled": True,
                "allow_real_tradingagents_run": True,
                "config": {"anything": "goes"},
                "artifact_path": "../../etc/passwd",
                "filename": "../../etc/passwd",
                "output_root": "/tmp/evil",
            }
        )
        payload = _model_to_payload(request)

        for forbidden_key in (
            "database_url",
            "database_credentials",
            "provider",
            "model",
            "api_key",
            "llm_enabled",
            "allow_real_tradingagents_run",
            "config",
            "artifact_path",
            "filename",
            "output_root",
        ):
            assert forbidden_key not in payload

    def test_run_research_request_ignores_extra_payload_fields(self, tmp_path, monkeypatch):
        monkeypatch.delenv("COMQUTOR_ENV", raising=False)
        monkeypatch.delenv("COMQUTOR_DATABASE_URL", raising=False)

        payload = {
            **_offline_payload(),
            "database_url": "postgresql://evil:evil@attacker.example/db",
            "output_root": "/tmp/evil",
            "provider": "evil_provider",
            "api_key": "evil-key",
        }
        response = run_research_request(payload, output_root=tmp_path)

        assert response["status"] == "completed"
        serialized = json.dumps(response)
        assert "evil" not in serialized
        assert "attacker.example" not in serialized
        # real default SQLite fallback was used -- the injected fake DSN was
        # never read from the payload
        assert list(tmp_path.glob("**/_comqutor_alpha_graph.db"))

    @pytest.mark.parametrize(
        "malicious_run_id",
        ["../secret", "../../etc/passwd", "/etc/passwd", "/", "C:\\Windows\\System32", "..\\..\\secret", "a/b"],
    )
    def test_get_graph_rejects_path_traversal_and_absolute_run_ids(self, tmp_path, malicious_run_id):
        response = get_persisted_structure_graph(malicious_run_id, output_root=tmp_path)

        assert response["status"] == "failed"
        assert response["error_code"] == "INVALID_RUN_ID"
