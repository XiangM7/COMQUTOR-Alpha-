"""W5.1A: research_runs schema/migration/repository persistence tests.

Covers migration 0003, row round-trip (including JSON/JSONB
selected_analysts/pipeline_identity), the active_fingerprint UNIQUE
constraint, the lifecycle state machine as enforced by the repository, cache
reuse at the repository layer, explicit run_id handling, and concurrent
duplicate-claim suppression against a real file-based SQLite database.
"""

from __future__ import annotations

import threading

import pytest
import sqlalchemy as sa

from comqutor_alpha.storage.db.engine import build_engine
from comqutor_alpha.storage.db.migrations import apply_migrations
from comqutor_alpha.storage.db.repository import GraphPersistenceError, GraphPersistenceRepository
from comqutor_alpha.storage.db.schema import research_runs


def _memory_repo():
    engine = build_engine("sqlite:///:memory:")
    apply_migrations(engine)
    return GraphPersistenceRepository(engine)


def _file_repo(tmp_path):
    db_path = tmp_path / "research_runs.db"
    engine = build_engine(f"sqlite:///{db_path}")
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


# ---------------------------------------------------------------------------
# G. Persistence
# ---------------------------------------------------------------------------


def test_migration_0003_creates_research_runs_table_sqlite():
    engine = build_engine("sqlite:///:memory:")
    applied = apply_migrations(engine)
    assert "0003_create_research_runs" in applied
    with engine.connect() as conn:
        conn.execute(sa.select(research_runs).limit(0))  # table exists, queryable


def test_migration_idempotent_reapply_is_a_no_op():
    engine = build_engine("sqlite:///:memory:")
    first = apply_migrations(engine)
    assert "0003_create_research_runs" in first
    second = apply_migrations(engine)
    assert second == []


def test_migration_does_not_alter_0001_0002_semantics():
    engine = build_engine("sqlite:///:memory:")
    applied = apply_migrations(engine)
    assert applied == [
        "0001_create_week3_alpha_matches_and_structure_graphs",
        "0002_create_week4_alpha_activations_and_alpha_conflicts",
        "0003_create_research_runs",
    ]


def test_row_round_trip_preserves_json_fields():
    repo = _memory_repo()
    claim = repo.claim_research_run(
        **_claim_kwargs(
            selected_analysts=["news", "market"],
            pipeline_identity={"a": 1, "b": {"nested": True}},
        )
    )
    record = repo.get_research_run_record(claim["run_id"])
    assert record["selected_analysts"] == ["news", "market"]
    assert record["pipeline_identity"] == {"a": 1, "b": {"nested": True}}


def test_active_fingerprint_unique_constraint_enforced_at_db_level():
    repo = _memory_repo()
    repo.claim_research_run(**_claim_kwargs(request_fingerprint="fp-unique"))
    with repo._engine.connect() as conn:  # noqa: SLF001 -- direct DB assertion, test-only
        rows = conn.execute(
            sa.select(research_runs).where(research_runs.c.active_fingerprint == "fp-unique")
        ).mappings().all()
    assert len(rows) == 1


def test_multiple_terminal_rows_can_share_same_fingerprint():
    """active_fingerprint is NULL for terminal rows -- SQL UNIQUE constraints
    allow unlimited NULLs, so many historical completed/failed rows for the
    same logical request must coexist."""
    repo = _memory_repo()
    run_ids = []
    for _ in range(3):
        claim = repo.claim_research_run(**_claim_kwargs(request_fingerprint="fp-shared", force_refresh=bool(run_ids)))
        repo.mark_research_run_running(claim["run_id"])
        repo.mark_research_run_terminal(claim["run_id"], status="completed")
        run_ids.append(claim["run_id"])
    assert len(set(run_ids)) == 3
    records = repo.list_research_run_records(limit=10)
    assert len({r["run_id"] for r in records if r["request_fingerprint"] == "fp-shared"}) == 3


def test_terminal_status_frees_fingerprint_for_a_new_run():
    repo = _memory_repo()
    claim1 = repo.claim_research_run(**_claim_kwargs(request_fingerprint="fp-retry"))
    repo.mark_research_run_running(claim1["run_id"])
    repo.mark_research_run_terminal(claim1["run_id"], status="failed", error_code="X", error_message="boom")

    claim2 = repo.claim_research_run(**_claim_kwargs(request_fingerprint="fp-retry"))
    assert claim2["disposition"] == "created"
    assert claim2["run_id"] != claim1["run_id"]


def test_indexes_exist_on_expected_columns():
    engine = build_engine("sqlite:///:memory:")
    apply_migrations(engine)
    with engine.connect() as conn:
        rows = conn.execute(sa.text("PRAGMA index_list('research_runs')")).all()
        index_names = {row[1] for row in rows}
    assert any("request_fingerprint" in name for name in index_names)
    assert any("status" in name for name in index_names)
    assert any("created_at" in name for name in index_names)
    assert any("ticker" in name for name in index_names)


# ---------------------------------------------------------------------------
# B. Lifecycle (repository-enforced)
# ---------------------------------------------------------------------------


def test_queued_to_running_to_completed():
    repo = _memory_repo()
    claim = repo.claim_research_run(**_claim_kwargs())
    record = repo.get_research_run_record(claim["run_id"])
    assert record["status"] == "queued"
    assert record["started_at"] is None
    assert record["completed_at"] is None
    assert record["active_fingerprint"] == record["request_fingerprint"]

    running = repo.mark_research_run_running(claim["run_id"])
    assert running["status"] == "running"
    assert running["started_at"] is not None
    assert running["completed_at"] is None

    completed = repo.mark_research_run_terminal(claim["run_id"], status="completed")
    assert completed["status"] == "completed"
    assert completed["completed_at"] is not None
    assert completed["active_fingerprint"] is None


def test_queued_to_failed_directly():
    repo = _memory_repo()
    claim = repo.claim_research_run(**_claim_kwargs())
    failed = repo.mark_research_run_terminal(
        claim["run_id"], status="failed", error_code="INVALID_TICKER", error_message="Invalid ticker."
    )
    assert failed["status"] == "failed"
    assert failed["active_fingerprint"] is None
    assert failed["error_code"] == "INVALID_TICKER"


def test_running_to_partial():
    repo = _memory_repo()
    claim = repo.claim_research_run(**_claim_kwargs())
    repo.mark_research_run_running(claim["run_id"])
    partial = repo.mark_research_run_terminal(claim["run_id"], status="partial")
    assert partial["status"] == "partial"
    assert partial["active_fingerprint"] is None


def test_running_to_failed():
    repo = _memory_repo()
    claim = repo.claim_research_run(**_claim_kwargs())
    repo.mark_research_run_running(claim["run_id"])
    failed = repo.mark_research_run_terminal(claim["run_id"], status="failed", error_code="INTERNAL_ERROR")
    assert failed["status"] == "failed"


@pytest.mark.parametrize("terminal_status", ["completed", "partial", "failed"])
def test_terminal_to_running_rejected(terminal_status):
    repo = _memory_repo()
    claim = repo.claim_research_run(**_claim_kwargs())
    repo.mark_research_run_running(claim["run_id"])
    repo.mark_research_run_terminal(claim["run_id"], status=terminal_status)
    with pytest.raises(GraphPersistenceError) as exc_info:
        repo.mark_research_run_running(claim["run_id"])
    assert exc_info.value.reason_code == "RESEARCH_RUN_TRANSITION_INVALID"


@pytest.mark.parametrize("terminal_status", ["completed", "partial", "failed"])
def test_terminal_clears_active_fingerprint(terminal_status):
    repo = _memory_repo()
    claim = repo.claim_research_run(**_claim_kwargs())
    repo.mark_research_run_running(claim["run_id"])
    record = repo.mark_research_run_terminal(claim["run_id"], status=terminal_status)
    assert record["active_fingerprint"] is None


def test_terminal_run_cannot_transition_to_another_terminal_status():
    repo = _memory_repo()
    claim = repo.claim_research_run(**_claim_kwargs())
    repo.mark_research_run_running(claim["run_id"])
    repo.mark_research_run_terminal(claim["run_id"], status="failed")
    with pytest.raises(GraphPersistenceError) as exc_info:
        repo.mark_research_run_terminal(claim["run_id"], status="completed")
    assert exc_info.value.reason_code == "RESEARCH_RUN_TRANSITION_INVALID"


def test_started_at_set_only_on_first_running_transition():
    repo = _memory_repo()
    claim = repo.claim_research_run(**_claim_kwargs())
    first = repo.mark_research_run_running(claim["run_id"])
    second = repo.mark_research_run_running(claim["run_id"])  # idempotent no-op
    assert first["started_at"] == second["started_at"]


def test_unexpected_terminal_write_still_clears_active_fingerprint_via_repository():
    """Simulates the orchestration layer's failure path: even an
    unexpected-exception outcome must route through mark_research_run_terminal
    (status=failed), which always clears active_fingerprint."""
    repo = _memory_repo()
    claim = repo.claim_research_run(**_claim_kwargs())
    repo.mark_research_run_running(claim["run_id"])
    record = repo.mark_research_run_terminal(
        claim["run_id"], status="failed", error_code="INTERNAL_ERROR", error_message="Research request failed."
    )
    assert record["active_fingerprint"] is None
    assert record["status"] == "failed"
    # The freed fingerprint immediately allows a fresh claim.
    retry = repo.claim_research_run(**_claim_kwargs(request_fingerprint=claim["record"]["request_fingerprint"]))
    assert retry["disposition"] == "created"


# ---------------------------------------------------------------------------
# C. Cache reuse (repository layer)
# ---------------------------------------------------------------------------


def test_first_claim_is_created():
    repo = _memory_repo()
    claim = repo.claim_research_run(**_claim_kwargs(request_fingerprint="fp-c1"))
    assert claim["disposition"] == "created"


def test_completed_claim_is_reused_completed():
    repo = _memory_repo()
    claim = repo.claim_research_run(**_claim_kwargs(request_fingerprint="fp-c2"))
    repo.mark_research_run_running(claim["run_id"])
    repo.mark_research_run_terminal(claim["run_id"], status="completed")

    reuse = repo.claim_research_run(**_claim_kwargs(request_fingerprint="fp-c2"))
    assert reuse["disposition"] == "reused_completed"
    assert reuse["run_id"] == claim["run_id"]


def test_force_refresh_bypasses_completed_reuse():
    repo = _memory_repo()
    claim = repo.claim_research_run(**_claim_kwargs(request_fingerprint="fp-c3"))
    repo.mark_research_run_running(claim["run_id"])
    repo.mark_research_run_terminal(claim["run_id"], status="completed")

    refreshed = repo.claim_research_run(**_claim_kwargs(request_fingerprint="fp-c3", force_refresh=True))
    assert refreshed["disposition"] == "force_refreshed"
    assert refreshed["run_id"] != claim["run_id"]


def test_force_refresh_keeps_same_fingerprint():
    repo = _memory_repo()
    claim = repo.claim_research_run(**_claim_kwargs(request_fingerprint="fp-c4"))
    repo.mark_research_run_running(claim["run_id"])
    repo.mark_research_run_terminal(claim["run_id"], status="completed")

    refreshed = repo.claim_research_run(**_claim_kwargs(request_fingerprint="fp-c4", force_refresh=True))
    assert refreshed["record"]["request_fingerprint"] == "fp-c4"


@pytest.mark.parametrize("terminal_status", ["partial", "failed"])
def test_partial_and_failed_are_not_used_as_completed_cache(terminal_status):
    repo = _memory_repo()
    claim = repo.claim_research_run(**_claim_kwargs(request_fingerprint="fp-c5"))
    repo.mark_research_run_running(claim["run_id"])
    repo.mark_research_run_terminal(claim["run_id"], status=terminal_status)

    retry = repo.claim_research_run(**_claim_kwargs(request_fingerprint="fp-c5"))
    assert retry["disposition"] == "created"
    assert retry["run_id"] != claim["run_id"]


def test_active_run_is_reused_in_flight_regardless_of_force_refresh():
    repo = _memory_repo()
    claim = repo.claim_research_run(**_claim_kwargs(request_fingerprint="fp-c6"))

    reuse = repo.claim_research_run(**_claim_kwargs(request_fingerprint="fp-c6", force_refresh=True))
    assert reuse["disposition"] == "reused_in_flight"
    assert reuse["run_id"] == claim["run_id"]


# ---------------------------------------------------------------------------
# E. Explicit run_id
# ---------------------------------------------------------------------------


def test_explicit_new_run_id_can_be_created():
    repo = _memory_repo()
    claim = repo.claim_research_run(**_claim_kwargs(run_id="explicit-new-run", request_fingerprint="fp-e1"))
    assert claim["disposition"] == "created"
    assert claim["run_id"] == "explicit-new-run"


def test_explicit_run_id_same_fingerprint_reuses_correctly():
    repo = _memory_repo()
    first = repo.claim_research_run(**_claim_kwargs(run_id="explicit-reuse", request_fingerprint="fp-e2"))
    again = repo.claim_research_run(**_claim_kwargs(run_id="explicit-reuse", request_fingerprint="fp-e2"))
    assert again["disposition"] == "reused_in_flight"
    assert again["run_id"] == first["run_id"]


def test_explicit_run_id_different_fingerprint_is_run_id_conflict():
    repo = _memory_repo()
    repo.claim_research_run(**_claim_kwargs(run_id="explicit-conflict", request_fingerprint="fp-e3"))
    with pytest.raises(GraphPersistenceError) as exc_info:
        repo.claim_research_run(**_claim_kwargs(run_id="explicit-conflict", request_fingerprint="fp-DIFFERENT"))
    assert exc_info.value.reason_code == "RUN_ID_CONFLICT"


def test_force_refresh_with_existing_run_id_is_invalid_force_refresh():
    repo = _memory_repo()
    repo.claim_research_run(**_claim_kwargs(run_id="explicit-fr", request_fingerprint="fp-e4"))
    with pytest.raises(GraphPersistenceError) as exc_info:
        repo.claim_research_run(**_claim_kwargs(run_id="explicit-fr", request_fingerprint="fp-e4", force_refresh=True))
    assert exc_info.value.reason_code == "INVALID_FORCE_REFRESH"


def test_explicit_run_id_never_overwrites_existing_row_data():
    repo = _memory_repo()
    first = repo.claim_research_run(**_claim_kwargs(run_id="explicit-no-overwrite", request_fingerprint="fp-e5", ticker="NVDA"))
    repo.mark_research_run_running(first["run_id"])
    repo.mark_research_run_terminal(first["run_id"], status="completed")
    before = repo.get_research_run_record("explicit-no-overwrite")

    reuse = repo.claim_research_run(**_claim_kwargs(run_id="explicit-no-overwrite", request_fingerprint="fp-e5", ticker="NVDA"))
    after = repo.get_research_run_record("explicit-no-overwrite")
    assert reuse["disposition"] == "reused_completed"
    assert before == after  # untouched


# ---------------------------------------------------------------------------
# D. Concurrent duplicate suppression (file-based SQLite)
# ---------------------------------------------------------------------------


def test_concurrent_claims_same_fingerprint_produce_exactly_one_created(tmp_path):
    repo = _file_repo(tmp_path)
    barrier = threading.Barrier(4)
    results: list[dict] = []
    lock = threading.Lock()

    def worker():
        barrier.wait()
        result = repo.claim_research_run(**_claim_kwargs(request_fingerprint="fp-concurrent"))
        with lock:
            results.append(result)

    threads = [threading.Thread(target=worker) for _ in range(4)]
    for t in threads:
        t.start()
    for t in threads:
        t.join()

    dispositions = [r["disposition"] for r in results]
    assert dispositions.count("created") == 1
    assert dispositions.count("reused_in_flight") == 3
    assert len({r["run_id"] for r in results}) == 1

    rows = repo.list_research_run_records(limit=10)
    active_rows = [r for r in rows if r["status"] in ("queued", "running")]
    assert len(active_rows) == 1


def test_concurrent_claims_do_not_raise_internal_errors(tmp_path):
    repo = _file_repo(tmp_path)
    barrier = threading.Barrier(3)
    errors: list[BaseException] = []
    lock = threading.Lock()

    def worker():
        barrier.wait()
        try:
            repo.claim_research_run(**_claim_kwargs(request_fingerprint="fp-concurrent-2"))
        except BaseException as exc:  # noqa: BLE001 -- test assertion target
            with lock:
                errors.append(exc)

    threads = [threading.Thread(target=worker) for _ in range(3)]
    for t in threads:
        t.start()
    for t in threads:
        t.join()

    assert errors == []


def test_concurrent_claims_after_completion_allow_new_run(tmp_path):
    """Two threads race to claim the same fingerprint; the winner completes;
    a subsequent claim for the same fingerprint must then create a new run
    (not be blocked forever)."""
    repo = _file_repo(tmp_path)
    barrier = threading.Barrier(2)
    results: list[dict] = []
    lock = threading.Lock()

    def worker():
        barrier.wait()
        result = repo.claim_research_run(**_claim_kwargs(request_fingerprint="fp-concurrent-3"))
        with lock:
            results.append(result)

    threads = [threading.Thread(target=worker) for _ in range(2)]
    for t in threads:
        t.start()
    for t in threads:
        t.join()

    winner_run_id = next(r["run_id"] for r in results if r["disposition"] == "created")
    repo.mark_research_run_running(winner_run_id)
    repo.mark_research_run_terminal(winner_run_id, status="completed")

    after = repo.claim_research_run(**_claim_kwargs(request_fingerprint="fp-concurrent-3"))
    assert after["disposition"] == "reused_completed"
    assert after["run_id"] == winner_run_id
