"""W5.1B: health/readiness/CORS tests.

Covers ``comqutor_alpha/api/routes_system.py`` (pure functions and, via
``TestClient`` used as a context manager so the FastAPI ``lifespan`` actually
runs, the real HTTP routes), and ``comqutor_alpha/api/main.py``'s CORS
configuration.
"""

from __future__ import annotations

import pathlib

import pytest

from comqutor_alpha.api.routes_system import health_response, readiness_response
from comqutor_alpha.storage.db.engine import build_engine
from comqutor_alpha.storage.db.migrations import apply_migrations


class _FakeJobManager:
    def __init__(self, accepting: bool):
        self._accepting = accepting

    def is_accepting(self) -> bool:
        return self._accepting


# ---------------------------------------------------------------------------
# health_response: pure liveness, never touches DB/filesystem
# ---------------------------------------------------------------------------


def test_health_response_is_ok():
    assert health_response() == {"status": "ok"}


def test_health_never_touches_database(tmp_path, monkeypatch):
    opened_names = []
    original_open = pathlib.Path.open

    def tracking_open(self, *args, **kwargs):
        opened_names.append(str(self))
        return original_open(self, *args, **kwargs)

    monkeypatch.setattr(pathlib.Path, "open", tracking_open)
    health_response()
    assert opened_names == []


# ---------------------------------------------------------------------------
# readiness_response: pure function
# ---------------------------------------------------------------------------


def test_ready_requires_job_manager(tmp_path):
    db_path = tmp_path / "_comqutor_alpha_graph.db"
    engine = build_engine(f"sqlite:///{db_path}")
    apply_migrations(engine)
    body, ok = readiness_response(job_manager=None, output_root=str(tmp_path))
    assert ok is False
    assert body["job_manager"] == "unavailable"
    assert body["status"] == "not_ready"


def test_ready_requires_database(tmp_path):
    # No sqlite file exists yet at this output_root -- never created by
    # readiness_response itself (would violate "must not write").
    body, ok = readiness_response(job_manager=_FakeJobManager(True), output_root=str(tmp_path))
    assert ok is False
    assert body["database"] == "unavailable"
    db_path = tmp_path / "_comqutor_alpha_graph.db"
    assert not db_path.exists()


def test_ready_all_green_disabled_real_execution_is_still_overall_ready(tmp_path, monkeypatch):
    for var in ("COMQUTOR_REAL_TRADINGAGENTS_ENABLED",):
        monkeypatch.delenv(var, raising=False)
    db_path = tmp_path / "_comqutor_alpha_graph.db"
    engine = build_engine(f"sqlite:///{db_path}")
    apply_migrations(engine)

    body, ok = readiness_response(job_manager=_FakeJobManager(True), output_root=str(tmp_path))
    assert ok is True
    assert body == {
        "status": "ready",
        "database": "ready",
        "job_manager": "ready",
        "real_execution": "disabled",
        "real_execution_reason": None,
    }


def test_ready_disabled_never_reported_as_credential_problem(tmp_path, monkeypatch):
    # Real execution deliberately disabled AND no Anthropic credential in
    # the environment: readiness must say "disabled" -- never misreport the
    # disabled state as a missing-key misconfiguration.
    monkeypatch.delenv("COMQUTOR_REAL_TRADINGAGENTS_ENABLED", raising=False)
    monkeypatch.delenv("ANTHROPIC_API_KEY", raising=False)
    db_path = tmp_path / "_comqutor_alpha_graph.db"
    engine = build_engine(f"sqlite:///{db_path}")
    apply_migrations(engine)

    body, ok = readiness_response(job_manager=_FakeJobManager(True), output_root=str(tmp_path))
    assert ok is True
    assert body["real_execution"] == "disabled"
    assert body["real_execution_reason"] is None


def test_ready_misconfigured_when_credential_missing(tmp_path, monkeypatch):
    monkeypatch.setenv("COMQUTOR_REAL_TRADINGAGENTS_ENABLED", "true")
    monkeypatch.delenv("ANTHROPIC_API_KEY", raising=False)

    db_path = tmp_path / "_comqutor_alpha_graph.db"
    engine = build_engine(f"sqlite:///{db_path}")
    apply_migrations(engine)

    body, ok = readiness_response(job_manager=_FakeJobManager(True), output_root=str(tmp_path))
    assert ok is False
    assert body["real_execution"] == "misconfigured"
    assert body["real_execution_reason"] == "credential_missing"
    assert body["status"] == "not_ready"


def test_ready_misconfigured_enabled_real_execution_returns_not_ready(tmp_path, monkeypatch):
    from comqutor_alpha import server_execution

    monkeypatch.setenv("COMQUTOR_REAL_TRADINGAGENTS_ENABLED", "true")

    def raising_config_builder():
        raise server_execution.ServerExecutionConfigError("REAL_RUN_CONFIG_INVALID")

    monkeypatch.setattr(
        server_execution, "build_server_tradingagents_config", raising_config_builder
    )

    db_path = tmp_path / "_comqutor_alpha_graph.db"
    engine = build_engine(f"sqlite:///{db_path}")
    apply_migrations(engine)

    body, ok = readiness_response(job_manager=_FakeJobManager(True), output_root=str(tmp_path))
    assert ok is False
    assert body["real_execution"] == "misconfigured"
    assert body["real_execution_reason"] == "profile_invalid"
    assert body["status"] == "not_ready"


def test_ready_configured_real_execution_is_reported(tmp_path, monkeypatch):
    monkeypatch.setenv("COMQUTOR_REAL_TRADINGAGENTS_ENABLED", "true")
    db_path = tmp_path / "_comqutor_alpha_graph.db"
    engine = build_engine(f"sqlite:///{db_path}")
    apply_migrations(engine)

    body, ok = readiness_response(job_manager=_FakeJobManager(True), output_root=str(tmp_path))
    assert ok is True
    assert body["real_execution"] == "configured"


def test_ready_missing_migrations_is_not_ready(tmp_path):
    db_path = tmp_path / "_comqutor_alpha_graph.db"
    engine = build_engine(f"sqlite:///{db_path}")
    # Deliberately do NOT apply migrations -- file exists but schema_migrations
    # table (and everything else) is absent.
    with engine.connect():
        pass

    body, ok = readiness_response(job_manager=_FakeJobManager(True), output_root=str(tmp_path))
    assert ok is False
    assert body["database"] == "unavailable"


def test_ready_never_applies_a_migration(tmp_path):
    db_path = tmp_path / "_comqutor_alpha_graph.db"
    engine = build_engine(f"sqlite:///{db_path}")
    with engine.connect():
        pass

    readiness_response(job_manager=_FakeJobManager(True), output_root=str(tmp_path))

    import sqlalchemy as sa

    with engine.connect() as conn:
        tables = sa.inspect(conn).get_table_names()
    assert "schema_migrations" not in tables
    assert "research_runs" not in tables


def test_ready_error_body_never_leaks_dsn_or_path(tmp_path):
    body, _ok = readiness_response(job_manager=None, output_root=str(tmp_path))
    serialized = str(body)
    assert str(tmp_path) not in serialized
    assert "sqlite://" not in serialized
    assert "postgresql://" not in serialized


# ---------------------------------------------------------------------------
# Full HTTP app: health/ready routes + CORS
# ---------------------------------------------------------------------------


@pytest.fixture()
def app_client(tmp_path, monkeypatch):
    from fastapi.testclient import TestClient

    from comqutor_alpha.api.main import create_app

    for var in ("COMQUTOR_REAL_TRADINGAGENTS_ENABLED", "COMQUTOR_CORS_ORIGINS"):
        monkeypatch.delenv(var, raising=False)

    app = create_app(output_root=str(tmp_path))
    with TestClient(app) as client:
        yield client


def test_http_health_route(app_client):
    response = app_client.get("/health")
    assert response.status_code == 200
    assert response.json() == {"status": "ok"}


def test_http_ready_route_is_ready_after_lifespan_startup(app_client):
    response = app_client.get("/ready")
    assert response.status_code == 200
    body = response.json()
    assert body["status"] == "ready"
    assert body["database"] == "ready"
    assert body["job_manager"] == "ready"
    assert body["real_execution"] == "disabled"


def test_http_ready_route_503_when_misconfigured(tmp_path, monkeypatch):
    from fastapi.testclient import TestClient

    from comqutor_alpha.api.main import create_app

    monkeypatch.setenv("COMQUTOR_REAL_TRADINGAGENTS_ENABLED", "true")
    monkeypatch.delenv("ANTHROPIC_API_KEY", raising=False)

    app = create_app(output_root=str(tmp_path))
    with TestClient(app) as client:
        response = client.get("/ready")
    assert response.status_code == 503
    body = response.json()
    assert body["real_execution"] == "misconfigured"
    assert body["real_execution_reason"] == "credential_missing"


def test_default_no_cors_headers(app_client):
    response = app_client.get("/health", headers={"Origin": "http://example.com"})
    assert "access-control-allow-origin" not in {k.lower() for k in response.headers}


def test_exact_allowed_origin_succeeds(tmp_path, monkeypatch):
    from fastapi.testclient import TestClient

    from comqutor_alpha.api.main import create_app

    monkeypatch.setenv("COMQUTOR_CORS_ORIGINS", "http://allowed.example.com")
    app = create_app(output_root=str(tmp_path))
    with TestClient(app) as client:
        response = client.get("/health", headers={"Origin": "http://allowed.example.com"})
    assert response.headers.get("access-control-allow-origin") == "http://allowed.example.com"


def test_unknown_origin_is_rejected(tmp_path, monkeypatch):
    from fastapi.testclient import TestClient

    from comqutor_alpha.api.main import create_app

    monkeypatch.setenv("COMQUTOR_CORS_ORIGINS", "http://allowed.example.com")
    app = create_app(output_root=str(tmp_path))
    with TestClient(app) as client:
        response = client.get("/health", headers={"Origin": "http://evil.example.com"})
    assert "access-control-allow-origin" not in {k.lower() for k in response.headers}


def test_wildcard_cors_origin_is_rejected(monkeypatch):
    from comqutor_alpha.api.main import ApiConfigurationError, _resolve_cors_origins

    monkeypatch.setenv("COMQUTOR_CORS_ORIGINS", "*")
    with pytest.raises(ApiConfigurationError) as exc_info:
        _resolve_cors_origins()
    assert exc_info.value.reason_code == "INVALID_CORS_ORIGINS"


def test_wildcard_mixed_with_real_origins_rejects_entire_config(monkeypatch):
    # A wildcard anywhere in the value -- even alongside otherwise-legal
    # origins -- invalidates the whole configuration. It must NOT be
    # interpreted as "drop the wildcard token, keep the rest".
    from comqutor_alpha.api.main import ApiConfigurationError, _resolve_cors_origins

    monkeypatch.setenv("COMQUTOR_CORS_ORIGINS", "http://a.example.com,*,http://b.example.com")
    with pytest.raises(ApiConfigurationError) as exc_info:
        _resolve_cors_origins()
    assert exc_info.value.reason_code == "INVALID_CORS_ORIGINS"


def test_cors_origins_deduplicated_preserving_order(monkeypatch):
    from comqutor_alpha.api.main import _resolve_cors_origins

    monkeypatch.setenv(
        "COMQUTOR_CORS_ORIGINS", "http://a.example.com,http://b.example.com,http://a.example.com"
    )
    assert _resolve_cors_origins() == ["http://a.example.com", "http://b.example.com"]


def test_cors_multiple_legal_origins(monkeypatch):
    from comqutor_alpha.api.main import _resolve_cors_origins

    monkeypatch.setenv("COMQUTOR_CORS_ORIGINS", "http://a.example.com,http://b.example.com")
    assert _resolve_cors_origins() == ["http://a.example.com", "http://b.example.com"]


@pytest.mark.parametrize(
    "value",
    [
        "http://a.example.com,",
        ",http://a.example.com",
        "http://a.example.com,,http://b.example.com",
    ],
)
def test_cors_blank_token_rejects_entire_config(monkeypatch, value):
    from comqutor_alpha.api.main import ApiConfigurationError, _resolve_cors_origins

    monkeypatch.setenv("COMQUTOR_CORS_ORIGINS", value)
    with pytest.raises(ApiConfigurationError) as exc_info:
        _resolve_cors_origins()
    assert exc_info.value.reason_code == "INVALID_CORS_ORIGINS"


def test_cors_whitespace_only_value_is_treated_as_unset(monkeypatch):
    from comqutor_alpha.api.main import _resolve_cors_origins

    monkeypatch.setenv("COMQUTOR_CORS_ORIGINS", "   ")
    assert _resolve_cors_origins() is None


def test_invalid_cors_config_makes_create_app_raise_not_a_partial_app(tmp_path, monkeypatch):
    from comqutor_alpha.api.main import ApiConfigurationError, create_app

    monkeypatch.setenv("COMQUTOR_CORS_ORIGINS", "*")
    with pytest.raises(ApiConfigurationError):
        create_app(output_root=str(tmp_path))


def test_server_main_exits_safely_on_invalid_cors_without_traceback(monkeypatch):
    import importlib
    import sys
    import types

    import comqutor_alpha.api.main as main_module
    import comqutor_alpha.api.server as server_module

    # uvicorn is not part of this test environment's installed set (only
    # fastapi/pydantic/starlette are) -- server.main() imports it before
    # ever reaching the CORS check, so a minimal stand-in module lets this
    # test reach (and verify) the actual code path under test without
    # requiring uvicorn to be installed.
    monkeypatch.setitem(sys.modules, "uvicorn", types.ModuleType("uvicorn"))
    monkeypatch.setenv("COMQUTOR_CORS_ORIGINS", "*")
    importlib.reload(main_module)
    try:
        with pytest.raises(SystemExit) as exc_info:
            server_module.main()
        message = str(exc_info.value)
        assert message == "COMQUTOR_CORS_ORIGINS is invalid."
        assert "Traceback" not in message
        assert "*" not in message
    finally:
        monkeypatch.delenv("COMQUTOR_CORS_ORIGINS", raising=False)
        importlib.reload(main_module)


def test_cors_unset_installs_no_middleware(monkeypatch):
    from comqutor_alpha.api.main import _resolve_cors_origins

    monkeypatch.delenv("COMQUTOR_CORS_ORIGINS", raising=False)
    assert _resolve_cors_origins() is None


def test_cors_allow_credentials_is_false(tmp_path, monkeypatch):
    from comqutor_alpha.api.main import create_app

    monkeypatch.setenv("COMQUTOR_CORS_ORIGINS", "http://allowed.example.com")
    app = create_app(output_root=str(tmp_path))
    cors_middlewares = [m for m in app.user_middleware if m.cls.__name__ == "CORSMiddleware"]
    assert len(cors_middlewares) == 1
    assert cors_middlewares[0].kwargs.get("allow_credentials") is False


def test_import_main_does_not_start_uvicorn_or_job_manager():
    import comqutor_alpha.api.main as main_module

    assert main_module.app is not None
    assert getattr(main_module.app.state, "job_manager", None) is None
