"""W5.1B: async HTTP POST /api/research semantics, stable status-code
mapping, and fake real-execution wiring proof.

Uses a real FastAPI ``TestClient`` (as a context manager, so the app's
``lifespan`` -- job manager startup/reconciliation/shutdown -- actually
runs) against ``comqutor_alpha.api.main.create_app``. Real-execution tests
swap in a ``JobManager`` with an injected fake worker entrypoint after
startup -- never a real TradingAgentsGraph, never a real LLM/provider/
network call.
"""

from __future__ import annotations

import json
import time

import pytest


@pytest.fixture()
def app_client(tmp_path, monkeypatch):
    from fastapi.testclient import TestClient

    from comqutor_alpha.api.main import create_app

    for var in ("COMQUTOR_REAL_TRADINGAGENTS_ENABLED", "COMQUTOR_CORS_ORIGINS", "COMQUTOR_ENV"):
        monkeypatch.delenv(var, raising=False)

    app = create_app(output_root=str(tmp_path))
    with TestClient(app) as client:
        yield client, tmp_path


def _offline_body(marker="a"):
    return {
        "ticker": "NVDA",
        "analysis_date": "2026-06-30",
        "offline_raw_agent_outputs": [{"agent": "news_agent", "raw_output": f"offline marker {marker}"}],
    }


def _poll_status(client, run_id, *, until_statuses, timeout=10.0):
    deadline = time.monotonic() + timeout
    last = None
    while time.monotonic() < deadline:
        response = client.get(f"/api/research/{run_id}/status")
        last = response.json()
        if last.get("status") in until_statuses:
            return last
        time.sleep(0.05)
    raise AssertionError(f"status never reached {until_statuses}, last={last}")


# ---------------------------------------------------------------------------
# POST semantics
# ---------------------------------------------------------------------------


def test_post_new_offline_request_returns_202_queued(app_client):
    client, _tmp_path = app_client
    response = client.post("/api/research", json=_offline_body("new"))
    assert response.status_code == 202
    body = response.json()
    assert body["status"] == "queued"
    assert body["run_status"] == "queued"
    assert body["cache_disposition"] == "created"
    assert body["stage"] == "accepted"


def test_polling_reaches_completed(app_client):
    client, _tmp_path = app_client
    response = client.post("/api/research", json=_offline_body("poll"))
    run_id = response.json()["run_id"]

    final = _poll_status(client, run_id, until_statuses={"completed", "partial", "failed"})
    assert final["status"] == "completed"


def test_post_force_refresh_returns_202_force_refreshed(app_client):
    client, _tmp_path = app_client
    first = client.post("/api/research", json=_offline_body("fr"))
    first_run_id = first.json()["run_id"]
    _poll_status(client, first_run_id, until_statuses={"completed", "partial", "failed"})

    second = client.post("/api/research", json={**_offline_body("fr"), "force_refresh": True})
    assert second.status_code == 202
    body = second.json()
    assert body["cache_disposition"] == "force_refreshed"
    assert body["run_id"] != first_run_id


def test_post_completed_reuse_returns_200(app_client):
    client, _tmp_path = app_client
    first = client.post("/api/research", json=_offline_body("reuse"))
    run_id = first.json()["run_id"]
    _poll_status(client, run_id, until_statuses={"completed", "partial", "failed"})

    second = client.post("/api/research", json=_offline_body("reuse"))
    assert second.status_code == 200
    body = second.json()
    assert body["cache_disposition"] == "reused_completed"
    assert body["run_id"] == run_id
    assert body["run_status"] == "completed"


def test_post_active_reuse_returns_202(app_client, monkeypatch):
    client, tmp_path = app_client

    # Force the queue to never actually start the worker (max_workers via
    # env is read only once at job-manager construction time inside
    # lifespan; instead, directly hold the manager's only worker slot busy
    # by claiming+submitting a long-running fake job first).
    import comqutor_alpha.api.main as main_module

    job_manager = client.app.state.job_manager
    assert job_manager is not None

    from comqutor_alpha.research_lifecycle import (
        build_research_request_fingerprint,
        build_research_request_identity,
    )

    payload = _offline_body("active")
    identity = build_research_request_identity(payload)
    fingerprint = build_research_request_fingerprint(identity)

    from comqutor_alpha.storage.db.repository import build_write_repository_from_env

    repo = build_write_repository_from_env(str(tmp_path))
    claim = repo.claim_research_run(
        run_id=None,
        request_fingerprint=fingerprint,
        ticker=identity["ticker"],
        analysis_date=identity["analysis_date"],
        selected_analysts=identity["selected_analysts"],
        execution_mode=identity["execution_mode"],
        provider_identity=identity["provider_identity"],
        model_identity=identity["model_identity"],
        pipeline_identity=identity["pipeline_identity"],
        force_refresh=False,
    )
    assert claim["disposition"] == "created"  # row is now active (queued), never submitted to the job manager

    response = client.post("/api/research", json=payload)
    assert response.status_code == 202
    body = response.json()
    assert body["cache_disposition"] == "reused_in_flight"
    assert body["run_id"] == claim["run_id"]
    del main_module  # unused, imported only to document app module context


# ---------------------------------------------------------------------------
# Stable status-code mapping
# ---------------------------------------------------------------------------


def test_run_id_conflict_returns_409(app_client):
    client, _tmp_path = app_client
    first = client.post("/api/research", json={**_offline_body("conflict"), "run_id": "shared-run-id"})
    assert first.status_code == 202

    second = client.post(
        "/api/research",
        json={**_offline_body("conflict-different"), "run_id": "shared-run-id"},
    )
    assert second.status_code == 409
    assert second.json()["error_code"] == "RUN_ID_CONFLICT"


def test_invalid_force_refresh_returns_409(app_client):
    client, _tmp_path = app_client
    first = client.post("/api/research", json={**_offline_body("ifr"), "run_id": "ifr-run-id"})
    assert first.status_code == 202

    second = client.post(
        "/api/research",
        json={**_offline_body("ifr"), "run_id": "ifr-run-id", "force_refresh": True},
    )
    assert second.status_code == 409
    assert second.json()["error_code"] == "INVALID_FORCE_REFRESH"


def test_real_disabled_returns_503_before_claim(app_client):
    client, tmp_path = app_client
    response = client.post("/api/research", json={"ticker": "NVDA"})
    assert response.status_code == 503
    body = response.json()
    assert body["error_code"] == "REAL_RUN_DISABLED"

    from comqutor_alpha.storage.db.repository import build_write_repository_from_env

    repo = build_write_repository_from_env(str(tmp_path))
    history = repo.list_research_run_records(limit=50)
    assert history == []  # no fake queued row was ever created


def test_production_offline_returns_before_claim(tmp_path, monkeypatch):
    from fastapi.testclient import TestClient

    from comqutor_alpha.api.main import create_app
    from comqutor_alpha.storage.db.repository import build_write_repository_from_env

    # Production requires an explicit COMQUTOR_DATABASE_URL (no local SQLite
    # fallback) -- set one here purely so this test can independently verify
    # "no row was created", without that verification itself depending on
    # the very offline-in-production gate under test.
    db_path = tmp_path / "prod.db"
    monkeypatch.setenv("COMQUTOR_DATABASE_URL", f"sqlite:///{db_path}")
    monkeypatch.setenv("COMQUTOR_ENV", "production")
    app = create_app(output_root=str(tmp_path))
    with TestClient(app) as client:
        response = client.post("/api/research", json=_offline_body("prod"))
    assert response.json()["error_code"] == "OFFLINE_DISABLED"

    repo = build_write_repository_from_env(str(tmp_path))
    assert repo.list_research_run_records(limit=50) == []


def test_pydantic_validation_error_returns_422(app_client):
    client, _tmp_path = app_client
    response = client.post("/api/research", json={"ticker": "'; DROP TABLE"})
    assert response.status_code == 422


# ---------------------------------------------------------------------------
# Fake real execution wiring: server-side config, client config ignored
# ---------------------------------------------------------------------------


def _fake_real_worker_entrypoint(run_id, execution_payload, output_root, disposition, ticker):
    """Module-level, picklable. Proves the worker received server-side
    ``allow_real_tradingagents_run``/``config`` (never from the client) by
    writing them to a marker file next to the run, then completes via a
    fake executor -- never imports/instantiates a real TradingAgentsGraph."""
    import json as _json
    from pathlib import Path

    from comqutor_alpha.research_lifecycle import execute_claimed_research_run
    from comqutor_alpha.storage.db.repository import build_write_repository_from_env

    marker_path = Path(output_root) / f"{run_id}.fake_worker_marker.json"
    marker_path.write_text(
        _json.dumps(
            {
                "allow_real_tradingagents_run": execution_payload.get("allow_real_tradingagents_run"),
                "config": execution_payload.get("config"),
                "had_client_config_key": "config" in execution_payload and execution_payload.get("__client_config_marker__") is not None,
            }
        ),
        encoding="utf-8",
    )

    def _fake_executor(_payload, **_kwargs):
        return {"run_id": run_id, "ticker": ticker, "status": "completed"}

    repository = build_write_repository_from_env(output_root)
    execute_claimed_research_run(
        run_id,
        execution_payload,
        output_root=output_root,
        graph_repository=repository,
        disposition=disposition,
        ticker=ticker,
        executor=_fake_executor,
    )


def test_fake_real_execution_completes_with_server_side_config(tmp_path, monkeypatch):
    from fastapi.testclient import TestClient

    from comqutor_alpha.api.main import create_app
    from comqutor_alpha.research_jobs import JobManager

    monkeypatch.setenv("COMQUTOR_REAL_TRADINGAGENTS_ENABLED", "true")

    app = create_app(output_root=str(tmp_path))
    with TestClient(app) as client:
        # Swap the lifespan-started job manager for one whose worker never
        # touches real TradingAgents.
        client.app.state.job_manager.shutdown()
        fake_manager = JobManager(
            max_workers=1,
            queue_capacity=2,
            timeout_seconds=60,
            shutdown_grace_seconds=5,
            output_root=str(tmp_path),
            worker_entrypoint=_fake_real_worker_entrypoint,
            poll_interval=0.02,
        )
        fake_manager.start()
        client.app.state.job_manager = fake_manager

        # Client sends ticker-only (real mode) plus a dangerous field the
        # ResearchRequest model cannot even carry -- Pydantic drops it
        # before this ever reaches the server.
        response = client.post(
            "/api/research",
            json={
                "ticker": "NVDA",
                "config": {"llm_provider": "should-be-ignored", "deep_think_llm": "evil-model"},
            },
        )
        assert response.status_code == 202
        run_id = response.json()["run_id"]

        final = _poll_status(client, run_id, until_statuses={"completed", "partial", "failed"})
        assert final["status"] == "completed"

        marker_path = tmp_path / f"{run_id}.fake_worker_marker.json"
        marker = json.loads(marker_path.read_text())
        assert marker["allow_real_tradingagents_run"] is True
        # W7: the fixed server Research Profile is the only source of the
        # provider/model configuration -- never an env var, never a client
        # payload field. Default profile is now DeepSeek.
        assert marker["config"]["llm_provider"] == "deepseek"
        assert marker["config"]["deep_think_llm"] == "deepseek-v4-flash"
        assert marker["config"]["quick_think_llm"] == "deepseek-v4-flash"
        assert marker["config"]["output_language"] == "English"
        assert marker["config"]["max_debate_rounds"] == 1
        assert marker["config"]["max_risk_discuss_rounds"] == 1
        # Client's attempted "config" override never reached the worker.
        assert marker["config"]["llm_provider"] != "should-be-ignored"
        assert marker["config"]["deep_think_llm"] != "evil-model"


def test_invalid_real_analyst_selection_returns_before_claim(tmp_path, monkeypatch):
    from fastapi.testclient import TestClient

    from comqutor_alpha.api.main import create_app

    monkeypatch.setenv("COMQUTOR_REAL_TRADINGAGENTS_ENABLED", "true")
    app = create_app(output_root=str(tmp_path))
    with TestClient(app) as client:
        response = client.post(
            "/api/research", json={"ticker": "NVDA", "selected_analysts": ["market", "not_a_real_analyst"]}
        )
    body = response.json()
    assert body["error_code"] == "INVALID_ANALYST_SELECTION"


def test_real_force_refresh_disabled_by_default_returns_403(tmp_path, monkeypatch):
    from fastapi.testclient import TestClient

    from comqutor_alpha.api.main import create_app

    monkeypatch.setenv("COMQUTOR_REAL_TRADINGAGENTS_ENABLED", "true")
    app = create_app(output_root=str(tmp_path))
    with TestClient(app) as client:
        response = client.post("/api/research", json={"ticker": "NVDA", "force_refresh": True})
    assert response.status_code == 403
    assert response.json()["error_code"] == "REAL_FORCE_REFRESH_DISABLED"


# ---------------------------------------------------------------------------
# status/history never expose fingerprints/config
# ---------------------------------------------------------------------------


def test_status_and_history_never_expose_fingerprint_or_config(app_client):
    client, _tmp_path = app_client
    post_response = client.post("/api/research", json=_offline_body("safe"))
    run_id = post_response.json()["run_id"]
    _poll_status(client, run_id, until_statuses={"completed", "partial", "failed"})

    status_response = client.get(f"/api/research/{run_id}/status")
    history_response = client.get("/api/research")

    for response in (status_response, history_response):
        serialized = json.dumps(response.json())
        for forbidden in ("request_fingerprint", "active_fingerprint", "pipeline_identity", "config_identity_sha256"):
            assert forbidden not in serialized
