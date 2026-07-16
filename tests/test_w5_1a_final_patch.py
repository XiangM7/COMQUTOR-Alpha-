"""W5.1A Final Correctness Patch tests.

Covers the three confirmed gaps closed in this patch:

1. ``claim_research_run`` UNIQUE-race recovery now re-runs the *entire*
   claim decision (explicit run_id -> active fingerprint -> completed
   cache -> insert) from scratch, bounded by a fixed retry count, instead
   of a single ad-hoc active-fingerprint re-query.
2. Explicit-run_id terminal reuse (partial/failed) is reported straight
   from the ``research_runs`` row -- never re-derived from, or upgraded
   by, a leftover/misleading filesystem artifact, and never re-executed.
3. ``decode_run_history_cursor`` performs full semantic validation
   (JSON shape, non-blank strings, a real ISO datetime, a safe run_id) and
   always raises ``ResearchLifecycleError("INVALID_CURSOR")`` -- the
   repository never sees an unvalidated cursor and never maps a cursor
   ValueError into DB_READ_FAILED / RUN_HISTORY_UNAVAILABLE.
"""

from __future__ import annotations

import pytest
from sqlalchemy.exc import IntegrityError

from comqutor_alpha.research_lifecycle import (
    ResearchLifecycleError,
    build_research_request_fingerprint,
    build_research_request_identity,
    decode_run_history_cursor,
    encode_run_history_cursor,
    submit_research_request,
)
from comqutor_alpha.storage.db.engine import build_engine
from comqutor_alpha.storage.db.migrations import apply_migrations
from comqutor_alpha.storage.db.repository import GraphPersistenceError, GraphPersistenceRepository


def _file_repo(tmp_path, name="w51a_patch.db"):
    engine = build_engine(f"sqlite:///{tmp_path / name}")
    apply_migrations(engine)
    return GraphPersistenceRepository(engine)


def _claim_kwargs(**overrides):
    kwargs = {
        "run_id": None,
        "request_fingerprint": "fp-default",
        "ticker": "NVDA",
        "analysis_date": "2026-06-30",
        "selected_analysts": ["fundamentals", "market", "news", "sentiment"],
        "execution_mode": "offline",
        "provider_identity": "server_unconfigured",
        "model_identity": "server_unconfigured",
        "pipeline_identity": {"graph_schema_version": "week3.structure_graph.v1"},
        "force_refresh": False,
    }
    kwargs.update(overrides)
    return kwargs


def _rig_one_shot_race(repo):
    """Force exactly one IntegrityError out of the *next* call to
    ``_insert_new_run`` -- deterministic race simulation via the
    repository's private seam, no real threads/sleeps required."""
    original_insert = repo._insert_new_run  # noqa: SLF001 -- test-only seam
    state = {"raised": False}

    def racy_insert(conn, values):
        if not state["raised"]:
            state["raised"] = True
            raise IntegrityError("INSERT INTO research_runs ...", {}, Exception("UNIQUE constraint failed"))
        return original_insert(conn, values)

    repo._insert_new_run = racy_insert  # noqa: SLF001
    return state


# ---------------------------------------------------------------------------
# 1. UNIQUE race recovery
# ---------------------------------------------------------------------------


def test_race_winner_completes_before_loser_recovery_returns_reused_completed(tmp_path):
    repo = _file_repo(tmp_path)
    fingerprint = "fp-race-completed"
    winner_holder: dict[str, str] = {}

    _rig_one_shot_race(repo)

    def on_race(attempt, request_fingerprint):
        assert attempt == 0
        winner = repo.claim_research_run(**_claim_kwargs(request_fingerprint=request_fingerprint))
        repo.mark_research_run_running(winner["run_id"])
        repo.mark_research_run_terminal(winner["run_id"], status="completed")
        winner_holder["run_id"] = winner["run_id"]

    repo._on_claim_race = on_race  # noqa: SLF001

    loser = repo.claim_research_run(**_claim_kwargs(request_fingerprint=fingerprint))

    assert loser["disposition"] == "reused_completed"
    assert loser["run_id"] == winner_holder["run_id"]
    assert loser["record"]["status"] == "completed"


def test_race_plus_force_refresh_winner_completed_loser_creates_new_run(tmp_path):
    repo = _file_repo(tmp_path)
    fingerprint = "fp-race-force-refresh"
    winner_holder: dict[str, str] = {}

    _rig_one_shot_race(repo)

    def on_race(attempt, request_fingerprint):
        winner = repo.claim_research_run(**_claim_kwargs(request_fingerprint=request_fingerprint))
        repo.mark_research_run_running(winner["run_id"])
        repo.mark_research_run_terminal(winner["run_id"], status="completed")
        winner_holder["run_id"] = winner["run_id"]

    repo._on_claim_race = on_race  # noqa: SLF001

    loser = repo.claim_research_run(**_claim_kwargs(request_fingerprint=fingerprint, force_refresh=True))

    assert loser["disposition"] == "force_refreshed"
    assert loser["run_id"] != winner_holder["run_id"]


@pytest.mark.parametrize("winner_terminal_status", ["partial", "failed"])
def test_race_winner_partial_or_failed_loser_creates_new_run(tmp_path, winner_terminal_status):
    repo = _file_repo(tmp_path)
    fingerprint = f"fp-race-{winner_terminal_status}"
    winner_holder: dict[str, str] = {}

    _rig_one_shot_race(repo)

    def on_race(attempt, request_fingerprint):
        winner = repo.claim_research_run(**_claim_kwargs(request_fingerprint=request_fingerprint))
        repo.mark_research_run_running(winner["run_id"])
        repo.mark_research_run_terminal(winner["run_id"], status=winner_terminal_status)
        winner_holder["run_id"] = winner["run_id"]

    repo._on_claim_race = on_race  # noqa: SLF001

    loser = repo.claim_research_run(**_claim_kwargs(request_fingerprint=fingerprint))

    assert loser["disposition"] == "created"
    assert loser["run_id"] != winner_holder["run_id"]


def test_race_recovery_is_never_reported_as_internal_error(tmp_path):
    repo = _file_repo(tmp_path)
    fingerprint = "fp-race-no-internal-error"
    _rig_one_shot_race(repo)

    def on_race(attempt, request_fingerprint):
        winner = repo.claim_research_run(**_claim_kwargs(request_fingerprint=request_fingerprint))
        repo.mark_research_run_running(winner["run_id"])
        repo.mark_research_run_terminal(winner["run_id"], status="completed")

    repo._on_claim_race = on_race  # noqa: SLF001

    # Must not raise at all -- the whole point of the fix.
    result = repo.claim_research_run(**_claim_kwargs(request_fingerprint=fingerprint))
    assert result["disposition"] == "reused_completed"


def test_race_retries_are_bounded_and_report_claim_conflict(tmp_path):
    repo = _file_repo(tmp_path)
    fingerprint = "fp-race-persistent"
    attempt_count = {"n": 0}

    def always_racy_insert(conn, values):
        attempt_count["n"] += 1
        raise IntegrityError("INSERT ...", {}, Exception("UNIQUE constraint failed"))

    repo._insert_new_run = always_racy_insert  # noqa: SLF001

    with pytest.raises(GraphPersistenceError) as exc_info:
        repo.claim_research_run(**_claim_kwargs(request_fingerprint=fingerprint))

    assert exc_info.value.reason_code == "RESEARCH_RUN_CLAIM_CONFLICT"
    assert attempt_count["n"] == repo._MAX_CLAIM_ATTEMPTS  # noqa: SLF001


def test_race_recovery_reruns_full_decision_not_just_active_lookup(tmp_path):
    """Explicit proof that recovery re-checks the completed cache (not
    merely the active_fingerprint row) -- the historical bug this patch
    fixes: a loser whose winner already finished and cleared
    active_fingerprint before recovery must still find it via the
    completed-cache branch of a fresh full decision."""
    repo = _file_repo(tmp_path)
    fingerprint = "fp-race-full-decision"
    _rig_one_shot_race(repo)
    calls = {"active_checks": 0}

    original_active_stmt = repo._active_fingerprint_statement

    def counting_active_stmt(request_fingerprint):
        calls["active_checks"] += 1
        return original_active_stmt(request_fingerprint)

    repo._active_fingerprint_statement = counting_active_stmt  # noqa: SLF001

    def on_race(attempt, request_fingerprint):
        winner = repo.claim_research_run(**_claim_kwargs(request_fingerprint=request_fingerprint))
        repo.mark_research_run_terminal(
            repo.mark_research_run_running(winner["run_id"])["run_id"], status="completed"
        )

    repo._on_claim_race = on_race  # noqa: SLF001

    result = repo.claim_research_run(**_claim_kwargs(request_fingerprint=fingerprint))
    assert result["disposition"] == "reused_completed"
    # At least 2 active-fingerprint checks: the loser's first (failed)
    # attempt, and the loser's retry -- proving the retry re-ran the whole
    # decision rather than short-circuiting straight to a completed lookup.
    assert calls["active_checks"] >= 2


# ---------------------------------------------------------------------------
# 2. Explicit terminal reuse source-of-truth
# ---------------------------------------------------------------------------


def _explicit_payload(run_id, ticker="NVDA", analysis_date="2026-06-30"):
    return {"ticker": ticker, "run_id": run_id, "analysis_date": analysis_date}


def _claim_explicit_terminal(repo, run_id, *, status, error_code=None, error_message=None, ticker="NVDA"):
    """Claim run_id with the *actual* fingerprint submit_research_request
    would compute for the matching payload (so the later submit call is a
    genuine same-fingerprint explicit-run_id reuse, not a RUN_ID_CONFLICT),
    then drive it straight to the given terminal status."""
    payload = _explicit_payload(run_id, ticker=ticker)
    identity = build_research_request_identity(payload)
    fingerprint = build_research_request_fingerprint(identity)
    claim = repo.claim_research_run(
        run_id=run_id,
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
    repo.mark_research_run_running(claim["run_id"])
    repo.mark_research_run_terminal(
        claim["run_id"], status=status, error_code=error_code, error_message=error_message
    )
    return claim["run_id"]


def _misleading_complete_artifacts(tmp_path, run_id, ticker="NVDA"):
    """Write a full, completion-looking artifact set on disk for a run_id
    whose research_runs row says something else (partial/failed) -- proves
    the response is built from the DB row, never upgraded by the artifact."""
    from comqutor_alpha.storage.file_store import save_json_record

    save_json_record(run_id, "metadata.json", {"run_id": run_id, "ticker": ticker}, output_root=tmp_path)
    save_json_record(
        run_id, "raw_agent_outputs.json", {"ticker": ticker, "agent_outputs": [{"a": 1}]}, output_root=tmp_path
    )
    save_json_record(run_id, "structured_agent_outputs.json", {"ticker": ticker, "records": [{"a": 1}]}, output_root=tmp_path)
    save_json_record(run_id, "alpha_matches.json", {"matches": []}, output_root=tmp_path)
    save_json_record(run_id, "extracted_structures.json", {"structures": []}, output_root=tmp_path)


def test_explicit_failed_run_with_misleading_artifact_still_reports_failed(tmp_path):
    repo = _file_repo(tmp_path)
    run_id = "explicit-failed-misleading"
    _claim_explicit_terminal(
        repo, run_id, status="failed", error_code="INVALID_TICKER", error_message="Invalid ticker."
    )
    _misleading_complete_artifacts(tmp_path, run_id)

    def _never_called_executor(*_args, **_kwargs):
        raise AssertionError("executor must not be called for a failed terminal reuse")

    response = submit_research_request(
        _explicit_payload(run_id),
        output_root=tmp_path,
        graph_repository=repo,
        executor=_never_called_executor,
    )
    assert response["status"] == "failed"
    assert response["run_status"] == "failed"
    assert response["error_code"] == "INVALID_TICKER"
    assert response["message"] == "Invalid ticker."
    assert response["cache_disposition"] == "reused_completed"


def test_explicit_partial_run_with_complete_looking_artifact_still_reports_partial(tmp_path):
    repo = _file_repo(tmp_path)
    run_id = "explicit-partial-misleading"
    _claim_explicit_terminal(repo, run_id, status="partial")
    _misleading_complete_artifacts(tmp_path, run_id)

    def _never_called_executor(*_args, **_kwargs):
        raise AssertionError("executor must not be called for a partial terminal reuse")

    response = submit_research_request(
        _explicit_payload(run_id),
        output_root=tmp_path,
        graph_repository=repo,
        executor=_never_called_executor,
    )
    assert response["status"] == "partial"
    assert response["run_status"] == "partial"
    assert response["cache_disposition"] == "reused_completed"


def test_explicit_failed_run_error_code_and_message_come_from_db(tmp_path):
    repo = _file_repo(tmp_path)
    run_id = "explicit-failed-safe-fields"
    _claim_explicit_terminal(
        repo,
        run_id,
        status="failed",
        error_code="REAL_RUN_DISABLED",
        error_message="Real TradingAgents execution is disabled by default.",
    )

    response = submit_research_request(_explicit_payload(run_id), output_root=tmp_path, graph_repository=repo)
    assert response["error_code"] == "REAL_RUN_DISABLED"
    assert response["message"] == "Real TradingAgents execution is disabled by default."
    assert "Traceback" not in response["message"]


def test_completed_reuse_with_missing_artifacts_returns_cached_run_unavailable(tmp_path):
    repo = _file_repo(tmp_path)
    run_id = "explicit-completed-gone"
    _claim_explicit_terminal(repo, run_id, status="completed")
    # No artifacts were ever written to tmp_path for this run_id.

    response = submit_research_request(_explicit_payload(run_id), output_root=tmp_path, graph_repository=repo)
    assert response["status"] == "failed"
    assert response["error_code"] == "CACHED_RUN_UNAVAILABLE"


@pytest.mark.parametrize("terminal_status", ["partial", "failed"])
def test_terminal_reuse_never_calls_executor(tmp_path, terminal_status):
    repo = _file_repo(tmp_path)
    run_id = f"explicit-{terminal_status}-no-executor"
    if terminal_status == "failed":
        _claim_explicit_terminal(repo, run_id, status="failed", error_code="X", error_message="boom")
    else:
        _claim_explicit_terminal(repo, run_id, status="partial")

    calls = {"n": 0}

    def _counting_executor(*_args, **_kwargs):
        calls["n"] += 1
        raise AssertionError("executor must never be called for a terminal reuse")

    submit_research_request(
        _explicit_payload(run_id), output_root=tmp_path, graph_repository=repo, executor=_counting_executor
    )
    assert calls["n"] == 0


@pytest.mark.parametrize("terminal_status", ["completed", "partial", "failed"])
def test_terminal_row_status_is_unchanged_by_reuse(tmp_path, terminal_status):
    repo = _file_repo(tmp_path)
    run_id = f"explicit-{terminal_status}-unchanged"
    if terminal_status == "completed":
        _claim_explicit_terminal(repo, run_id, status="completed")
        _misleading_complete_artifacts(tmp_path, run_id)
    elif terminal_status == "failed":
        _claim_explicit_terminal(repo, run_id, status="failed", error_code="X", error_message="boom")
    else:
        _claim_explicit_terminal(repo, run_id, status="partial")
    before = repo.get_research_run_record(run_id)

    submit_research_request(_explicit_payload(run_id), output_root=tmp_path, graph_repository=repo)
    after = repo.get_research_run_record(run_id)
    assert before == after


def test_terminal_reuse_response_never_exposes_internal_fields(tmp_path):
    repo = _file_repo(tmp_path)
    run_id = "explicit-partial-no-leak"
    _claim_explicit_terminal(repo, run_id, status="partial")

    import json

    response = submit_research_request(_explicit_payload(run_id), output_root=tmp_path, graph_repository=repo)
    serialized = json.dumps(response, default=str)
    for forbidden in ("request_fingerprint", "active_fingerprint", "pipeline_identity", str(tmp_path)):
        assert forbidden not in serialized


# ---------------------------------------------------------------------------
# 3. Cursor semantic validation
# ---------------------------------------------------------------------------


def test_cursor_valid_json_but_invalid_date_raises_invalid_cursor():
    with pytest.raises(ResearchLifecycleError) as exc_info:
        decode_run_history_cursor('["not-a-date", "run-123"]')
    assert exc_info.value.reason_code == "INVALID_CURSOR"


def test_cursor_date_is_pure_whitespace():
    with pytest.raises(ResearchLifecycleError) as exc_info:
        decode_run_history_cursor('["   ", "run-123"]')
    assert exc_info.value.reason_code == "INVALID_CURSOR"


def test_cursor_list_length_one_is_rejected():
    with pytest.raises(ResearchLifecycleError):
        decode_run_history_cursor('["2026-06-30T00:00:00+00:00"]')


def test_cursor_list_length_three_is_rejected():
    with pytest.raises(ResearchLifecycleError):
        decode_run_history_cursor('["2026-06-30T00:00:00+00:00", "run-123", "extra"]')


def test_cursor_run_id_as_number_is_rejected():
    with pytest.raises(ResearchLifecycleError):
        decode_run_history_cursor('["2026-06-30T00:00:00+00:00", 123]')


def test_cursor_run_id_path_traversal_is_rejected():
    with pytest.raises(ResearchLifecycleError) as exc_info:
        decode_run_history_cursor('["2026-06-30T00:00:00+00:00", "../../etc/passwd"]')
    assert exc_info.value.reason_code == "INVALID_CURSOR"


def test_cursor_accepts_timezone_aware_timestamp():
    decoded = decode_run_history_cursor('["2026-06-30T00:00:00+00:00", "run-123"]')
    assert decoded == ("2026-06-30T00:00:00+00:00", "run-123")


def test_cursor_accepts_sqlite_naive_timestamp():
    decoded = decode_run_history_cursor('["2026-06-30 00:00:00", "run-123"]')
    assert decoded == ("2026-06-30 00:00:00", "run-123")


def test_cursor_dict_root_is_rejected():
    with pytest.raises(ResearchLifecycleError):
        decode_run_history_cursor('{"created_at": "2026-06-30T00:00:00+00:00", "run_id": "run-123"}')


def test_cursor_completely_malformed_json_is_rejected():
    with pytest.raises(ResearchLifecycleError):
        decode_run_history_cursor("not json at all {{{")


def test_cursor_encode_decode_round_trip():
    import datetime as dt

    encoded = encode_run_history_cursor(dt.datetime(2026, 6, 30, tzinfo=dt.UTC), "run-abc")
    assert decode_run_history_cursor(encoded) == ("2026-06-30T00:00:00+00:00", "run-abc")


def test_history_api_maps_semantically_invalid_cursor_to_invalid_cursor_not_unavailable(tmp_path):
    from comqutor_alpha.api.routes_research import get_research_run_history

    repo = _file_repo(tmp_path, "history_cursor.db")
    result = get_research_run_history(cursor='["not-a-date", "run-123"]', graph_repository=repo)
    assert result["status"] == "failed"
    assert result["error_code"] == "INVALID_CURSOR"


def test_repository_never_maps_cursor_valueerror_to_db_read_failed(tmp_path):
    """The repository only ever receives an already-validated cursor tuple;
    confirms it does not itself swallow a ValueError from a hypothetically
    malformed cursor into DB_READ_FAILED."""
    repo = _file_repo(tmp_path, "history_repo_valueerror.db")
    with pytest.raises(ValueError):
        repo.list_research_run_records(cursor=("not-a-date", "run-123"))
