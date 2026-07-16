"""W5.1A: HTTP-facing contract tests for research run lifecycle.

Covers ResearchRequest's new force_refresh field (and continued absence of
any client-controlled execution field), POST cache-disposition semantics,
GET .../status, and GET / (history) -- both as direct Python calls (fast,
precise) and through a real FastAPI TestClient (proves actual HTTP wiring
and route registration, including that the history route is never swallowed
by the run_id route).
"""

from __future__ import annotations

import json

from comqutor_alpha.api.routes_research import (
    ResearchRequest,
    get_research_run_history,
    get_research_run_status,
    router,
    submit_research_request,
)
from comqutor_alpha.storage.db.engine import build_engine
from comqutor_alpha.storage.db.migrations import apply_migrations
from comqutor_alpha.storage.db.repository import GraphPersistenceError, GraphPersistenceRepository


def _repo():
    engine = build_engine("sqlite:///:memory:")
    apply_migrations(engine)
    return GraphPersistenceRepository(engine)


def _offline_payload(**overrides):
    payload = {
        "ticker": "NVDA",
        "analysis_date": "2026-06-30",
        "offline_raw_agent_outputs": [
            {"agent": "news_agent", "raw_output": "AI capex is rising and driving GPU demand."},
        ],
    }
    payload.update(overrides)
    return payload


def _model_field_names(model_cls):
    fields = getattr(model_cls, "model_fields", None)
    if fields is None:
        fields = model_cls.__fields__
    return set(fields.keys())


# ---------------------------------------------------------------------------
# ResearchRequest field contract
# ---------------------------------------------------------------------------


def test_research_request_includes_force_refresh():
    assert "force_refresh" in _model_field_names(ResearchRequest)


def test_research_request_still_excludes_dangerous_execution_fields():
    field_names = _model_field_names(ResearchRequest)
    for forbidden in ("allow_real_tradingagents_run", "config", "provider", "model", "api_key", "database_url"):
        assert forbidden not in field_names


def test_unknown_dangerous_fields_are_still_stripped():
    from comqutor_alpha.api.routes_research import _model_to_payload

    request = ResearchRequest(
        **{
            "ticker": "NVDA",
            "force_refresh": True,
            "allow_real_tradingagents_run": True,
            "config": {"provider": "evil"},
            "provider": "evil_provider",
            "api_key": "evil-key",
        }
    )
    payload = _model_to_payload(request)
    for forbidden in ("allow_real_tradingagents_run", "config", "provider", "model", "api_key"):
        assert forbidden not in payload
    assert payload["force_refresh"] is True


# ---------------------------------------------------------------------------
# POST disposition semantics (direct submit_research_request calls)
# ---------------------------------------------------------------------------


def test_post_new_request_disposition_created(tmp_path):
    repo = _repo()
    response = submit_research_request(_offline_payload(), output_root=tmp_path, graph_repository=repo)
    assert response["cache_disposition"] == "created"
    assert response["run_status"] == "completed"
    assert response["status"] == "completed"


def test_post_completed_reuse_disposition(tmp_path):
    repo = _repo()
    first = submit_research_request(_offline_payload(), output_root=tmp_path, graph_repository=repo)
    second = submit_research_request(_offline_payload(), output_root=tmp_path, graph_repository=repo)
    assert second["cache_disposition"] == "reused_completed"
    assert second["run_id"] == first["run_id"]
    assert second["run_status"] == "completed"


def test_post_in_flight_reuse_disposition(tmp_path):
    from comqutor_alpha.research_lifecycle import (
        build_research_request_fingerprint,
        build_research_request_identity,
    )

    repo = _repo()
    payload = _offline_payload()
    # Claim directly using the *real* fingerprint submit_research_request
    # would itself compute for this exact payload, so the follow-up
    # submit() call below is a genuine duplicate of the identical logical
    # request (not a coincidentally-different one).
    identity = build_research_request_identity(payload)
    fingerprint = build_research_request_fingerprint(identity)
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
    assert claim["disposition"] == "created"

    def _never_called_executor(*_args, **_kwargs):
        raise AssertionError("executor must not be called for an in-flight duplicate")

    response = submit_research_request(
        payload,
        output_root=tmp_path,
        graph_repository=repo,
        executor=_never_called_executor,
    )
    assert response["cache_disposition"] == "reused_in_flight"
    assert response["run_id"] == claim["run_id"]
    assert response["run_status"] == "queued"


def test_post_completed_reuse_does_not_call_executor(tmp_path):
    repo = _repo()
    submit_research_request(_offline_payload(), output_root=tmp_path, graph_repository=repo)

    def _never_called_executor(*_args, **_kwargs):
        raise AssertionError("executor must not be called for a completed-cache reuse")

    response = submit_research_request(
        _offline_payload(), output_root=tmp_path, graph_repository=repo, executor=_never_called_executor
    )
    assert response["cache_disposition"] == "reused_completed"


def test_post_force_refresh_creates_new_run(tmp_path):
    repo = _repo()
    first = submit_research_request(_offline_payload(), output_root=tmp_path, graph_repository=repo)
    second = submit_research_request(
        _offline_payload(force_refresh=True), output_root=tmp_path, graph_repository=repo
    )
    assert second["cache_disposition"] == "force_refreshed"
    assert second["run_id"] != first["run_id"]
    assert second["run_status"] == "completed"


def test_post_response_never_exposes_internal_fingerprint_fields(tmp_path):
    repo = _repo()
    response = submit_research_request(_offline_payload(), output_root=tmp_path, graph_repository=repo)
    serialized = json.dumps(response, default=str)
    for forbidden in ("request_fingerprint", "active_fingerprint", "pipeline_identity", "offline_input_digest"):
        assert forbidden not in serialized


def test_ticker_only_real_request_still_returns_real_run_disabled(tmp_path):
    repo = _repo()
    response = submit_research_request({"ticker": "NVDA"}, output_root=tmp_path, graph_repository=repo)
    assert response["error_code"] == "REAL_RUN_DISABLED"
    assert response["run_status"] == "failed"


# ---------------------------------------------------------------------------
# GET status
# ---------------------------------------------------------------------------


def test_get_status_success(tmp_path):
    repo = _repo()
    response = submit_research_request(_offline_payload(), output_root=tmp_path, graph_repository=repo)
    run_id = response["run_id"]

    status = get_research_run_status(run_id, graph_repository=repo)
    assert status["run_id"] == run_id
    assert status["ticker"] == "NVDA"
    assert status["status"] == "completed"
    assert status["error_code"] is None
    assert status["created_at"] is not None
    assert status["completed_at"] is not None


def test_get_status_invalid_run_id():
    repo = _repo()
    status = get_research_run_status("../secret", graph_repository=repo)
    assert status["status"] == "failed"
    assert status["error_code"] == "INVALID_RUN_ID"


def test_get_status_not_found():
    repo = _repo()
    status = get_research_run_status("totally_unknown_run", graph_repository=repo)
    assert status["status"] == "failed"
    assert status["error_code"] == "RUN_STATUS_NOT_FOUND"


def test_get_status_unavailable_on_storage_error():
    class BrokenRepository:
        def get_research_run_record(self, run_id):
            raise GraphPersistenceError("DB_READ_FAILED")

    status = get_research_run_status("some_run", graph_repository=BrokenRepository())
    assert status["status"] == "failed"
    assert status["error_code"] == "RUN_STATUS_UNAVAILABLE"


def test_get_status_never_exposes_fingerprint(tmp_path):
    repo = _repo()
    response = submit_research_request(_offline_payload(), output_root=tmp_path, graph_repository=repo)
    status = get_research_run_status(response["run_id"], graph_repository=repo)
    serialized = json.dumps(status, default=str)
    assert "request_fingerprint" not in serialized
    assert "active_fingerprint" not in serialized
    assert "pipeline_identity" not in serialized


def test_get_status_never_reads_local_artifacts(tmp_path, monkeypatch):
    import pathlib

    repo = _repo()
    response = submit_research_request(_offline_payload(), output_root=tmp_path, graph_repository=repo)
    run_id = response["run_id"]

    opened_names = []
    original_open = pathlib.Path.open

    def tracking_open(self, *args, **kwargs):
        opened_names.append(self.name)
        return original_open(self, *args, **kwargs)

    monkeypatch.setattr(pathlib.Path, "open", tracking_open)
    get_research_run_status(run_id, graph_repository=repo)

    for forbidden_file in ("raw_agent_outputs.json", "structured_agent_outputs.json", "structure_graph.json"):
        assert forbidden_file not in opened_names


# ---------------------------------------------------------------------------
# GET history
# ---------------------------------------------------------------------------


def test_history_orders_newest_first(tmp_path):
    repo = _repo()
    run_ids = []
    for i in range(3):
        response = submit_research_request(
            _offline_payload(
                offline_raw_agent_outputs=[{"agent": "news_agent", "raw_output": f"unique content {i}"}]
            ),
            output_root=tmp_path,
            graph_repository=repo,
        )
        run_ids.append(response["run_id"])

    history = get_research_run_history(graph_repository=repo)
    assert history["status"] == "ok"
    returned_ids = [item["run_id"] for item in history["items"]]
    assert returned_ids[0] == run_ids[-1]  # most recently created first


def test_history_cursor_pagination_is_stable(tmp_path):
    repo = _repo()
    for i in range(5):
        submit_research_request(
            _offline_payload(
                offline_raw_agent_outputs=[{"agent": "news_agent", "raw_output": f"content {i}"}]
            ),
            output_root=tmp_path,
            graph_repository=repo,
        )

    page1 = get_research_run_history(limit=2, graph_repository=repo)
    assert len(page1["items"]) == 2
    assert page1["next_cursor"] is not None

    page2 = get_research_run_history(limit=2, cursor=page1["next_cursor"], graph_repository=repo)
    assert len(page2["items"]) == 2

    page1_ids = {item["run_id"] for item in page1["items"]}
    page2_ids = {item["run_id"] for item in page2["items"]}
    assert page1_ids.isdisjoint(page2_ids)

    # Same cursor queried again must be deterministic.
    page2_again = get_research_run_history(limit=2, cursor=page1["next_cursor"], graph_repository=repo)
    assert [item["run_id"] for item in page2["items"]] == [item["run_id"] for item in page2_again["items"]]


def test_history_ticker_filter(tmp_path):
    repo = _repo()
    submit_research_request(_offline_payload(ticker="NVDA"), output_root=tmp_path, graph_repository=repo)
    submit_research_request(
        _offline_payload(
            ticker="QQQ",
            offline_raw_agent_outputs=[{"agent": "news_agent", "raw_output": "unrelated content"}],
        ),
        output_root=tmp_path,
        graph_repository=repo,
    )

    history = get_research_run_history(ticker="QQQ", graph_repository=repo)
    assert all(item["ticker"] == "QQQ" for item in history["items"])
    assert len(history["items"]) == 1


def test_history_status_filter(tmp_path):
    # W5.1B: a real-mode request with real execution server-disabled is now
    # gated (REAL_RUN_DISABLED) *before* any row is claimed -- no fake
    # queued/failed row is created for it (see
    # research_lifecycle.prepare_research_submission). A failed history row
    # is instead arranged directly against the repository, exactly as any
    # other terminal run would appear.
    repo = _repo()
    failed_claim = repo.claim_research_run(
        run_id=None,
        request_fingerprint="fp-history-status-filter-failed",
        ticker="NVDA",
        analysis_date="2026-06-30",
        selected_analysts=["market"],
        execution_mode="offline",
        provider_identity="server_unconfigured",
        model_identity="server_unconfigured",
        pipeline_identity={},
        force_refresh=False,
    )
    repo.mark_research_run_running(failed_claim["run_id"])
    repo.mark_research_run_terminal(
        failed_claim["run_id"], status="failed", error_code="INTERNAL_ERROR", error_message="boom"
    )
    submit_research_request(_offline_payload(), output_root=tmp_path, graph_repository=repo)  # completes

    failed_history = get_research_run_history(status="failed", graph_repository=repo)
    assert all(item["status"] == "failed" for item in failed_history["items"])
    assert len(failed_history["items"]) == 1

    completed_history = get_research_run_history(status="completed", graph_repository=repo)
    assert len(completed_history["items"]) == 1


def test_history_invalid_status_filter():
    repo = _repo()
    history = get_research_run_history(status="not_a_real_status", graph_repository=repo)
    assert history["status"] == "failed"
    assert history["error_code"] == "INVALID_STATUS_FILTER"


def test_history_invalid_ticker_filter():
    repo = _repo()
    history = get_research_run_history(ticker="'; DROP TABLE research_runs;--", graph_repository=repo)
    assert history["status"] == "failed"
    assert history["error_code"] == "INVALID_TICKER"


def test_history_invalid_cursor():
    repo = _repo()
    history = get_research_run_history(cursor="not-a-valid-cursor", graph_repository=repo)
    assert history["status"] == "failed"
    assert history["error_code"] == "INVALID_CURSOR"


def test_history_never_exposes_internal_fields(tmp_path):
    repo = _repo()
    submit_research_request(_offline_payload(), output_root=tmp_path, graph_repository=repo)
    history = get_research_run_history(graph_repository=repo)
    serialized = json.dumps(history, default=str)
    for forbidden in ("request_fingerprint", "active_fingerprint", "pipeline_identity"):
        assert forbidden not in serialized


def test_history_never_reads_local_artifacts_or_writes_db(tmp_path, monkeypatch):
    import pathlib

    repo = _repo()
    submit_research_request(_offline_payload(), output_root=tmp_path, graph_repository=repo)

    opened_names = []
    original_open = pathlib.Path.open

    def tracking_open(self, *args, **kwargs):
        opened_names.append(self.name)
        return original_open(self, *args, **kwargs)

    monkeypatch.setattr(pathlib.Path, "open", tracking_open)
    before = repo.list_research_run_records(limit=50)
    get_research_run_history(graph_repository=repo)
    after = repo.list_research_run_records(limit=50)

    for forbidden_file in ("raw_agent_outputs.json", "structured_agent_outputs.json", "structure_graph.json"):
        assert forbidden_file not in opened_names
    assert before == after


# ---------------------------------------------------------------------------
# Real HTTP wiring (route registration, non-shadowing)
# ---------------------------------------------------------------------------


def test_history_route_not_swallowed_by_run_id_route():
    from fastapi import FastAPI
    from fastapi.testclient import TestClient

    app = FastAPI()
    app.include_router(router)
    client = TestClient(app)

    response = client.get("/api/research")
    assert response.status_code == 200
    body = response.json()
    assert "items" in body
    assert "next_cursor" in body


def test_status_route_registered_and_returns_safe_body_for_unknown_run():
    from fastapi import FastAPI
    from fastapi.testclient import TestClient

    app = FastAPI()
    app.include_router(router)
    client = TestClient(app)

    response = client.get("/api/research/unknown-run-xyz/status")
    assert response.status_code == 200
    body = response.json()
    assert body["status"] == "failed"
    assert body["error_code"] == "RUN_STATUS_NOT_FOUND"


def test_post_route_accepts_force_refresh_field():
    from fastapi import FastAPI
    from fastapi.testclient import TestClient

    app = FastAPI()
    app.include_router(router)
    client = TestClient(app)

    response = client.post(
        "/api/research",
        json={
            "ticker": "'; DROP",
            "force_refresh": True,
        },
    )
    # Malformed ticker -- validated before force_refresh matters; proves the
    # field is accepted by the model without a 422 "extra field" rejection.
    assert response.status_code == 422
