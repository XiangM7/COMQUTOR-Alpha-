"""W4.3 Pipeline / Conflicts API integration tests.

Covers the new orchestration wiring added on top of the already-frozen
W4.1 Conflict Detector and W4.2 persistence repository: automatic Week 4
execution inside the research pipeline, the canonical research response's
additive fields (``dominant_alphas``/``main_conflict``/``conflict_status``/
``summary``), and ``GET /api/research/{run_id}/conflicts``.

Never modifies W4.1/W4.2 business logic, taxonomy, formulas, or the
database schema -- only exercises the new integration seam.
"""

from __future__ import annotations

import json
import logging

from comqutor_alpha.api.routes_research import (
    build_research_response,
    get_persisted_conflicts,
    get_persisted_structure_graph,
    get_research_run,
    run_research_request,
)
from comqutor_alpha.conflict_engine.conflict_detector import detect_alpha_conflicts
from comqutor_alpha.storage.db.engine import build_engine
from comqutor_alpha.storage.db.migrations import apply_migrations
from comqutor_alpha.storage.db.repository import GraphPersistenceError, GraphPersistenceRepository
from tests.test_week3_nvda_sanity import _nvda_offline_outputs

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
        "while executing SELECT * FROM alpha_conflicts\nTraceback (most recent call last):"
    )


def _repo():
    engine = build_engine("sqlite:///:memory:")
    apply_migrations(engine)
    return GraphPersistenceRepository(engine)


def _nvda_payload():
    return {
        "ticker": "NVDA",
        "analysis_date": "2026-06-30",
        "selected_analysts": ["market", "news", "fundamentals", "sentiment"],
        "offline_raw_agent_outputs": _nvda_offline_outputs(),
    }


def _empty_evidence_payload():
    return {
        "ticker": "NVDA",
        "analysis_date": "2026-06-30",
        "offline_raw_agent_outputs": [],
    }


def _seed_week1_2_artifacts(tmp_path, run_id, ticker="NVDA", matches=None):
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


# ---------------------------------------------------------------------------
# A. Pipeline happy path
# ---------------------------------------------------------------------------


def test_pipeline_happy_path_completes_week1_through_4(tmp_path):
    repo = _repo()
    response = run_research_request(_nvda_payload(), output_root=tmp_path, graph_repository=repo)
    run_id = response["run_id"]

    assert response["status"] == "completed"
    assert response["structure_graph_status"] == "ready"
    assert response["conflict_status"] == "ready"

    # dominant_alphas comes straight from the persisted graph, not recomputed.
    graph_row = repo.get_graph(run_id)
    assert response["dominant_alphas"] == graph_row["graph_json"]["dominant_alphas"]

    # main_conflict comes straight from the persisted W4 conflict result.
    conflict_result = repo.get_week4_conflict_result(run_id)
    assert conflict_result is not None
    assert response["main_conflict"] == conflict_result["main_conflict"]
    assert response["main_conflict"]["conflict_id"] == "A101__A304"

    assert response["summary"] == conflict_result["main_conflict"]["explanation"]
    for forbidden in ("Buy", "Sell", "Hold", "position", "price target"):
        assert forbidden.lower() not in response["summary"].lower()

    # artifacts dict shape is frozen -- untouched by W4.3.
    assert response["artifacts"] == {
        "metadata": True,
        "raw_agent_outputs": True,
        "structured_agent_outputs": True,
        "final_report": False,
        "alpha_matches": True,
        "extracted_structures": True,
        "structured_output_error_logs": False,
        "week2_llm_error_logs": False,
        "week2_pipeline_error_logs": False,
    }

    # W4.1 detector was reachable exactly through the taxonomy-declared
    # six-pair enumeration -- persisted activation snapshot matches Week 3.
    activation_rows = repo.get_alpha_activations(run_id)
    assert len(activation_rows) == 10
    conflict_rows = repo.get_alpha_conflicts(run_id)
    assert len(conflict_rows) == 6  # six taxonomy-declared candidate pairs


# ---------------------------------------------------------------------------
# B. Zero admitted conflict
# ---------------------------------------------------------------------------


def test_zero_admitted_conflict_is_still_ready_not_not_ready(tmp_path):
    repo = _repo()
    response = run_research_request(_empty_evidence_payload(), output_root=tmp_path, graph_repository=repo)
    run_id = response["run_id"]

    assert response["structure_graph_status"] == "ready"
    assert response["conflict_status"] == "ready"
    assert response["main_conflict"] is None

    conflict_result = repo.get_week4_conflict_result(run_id)
    assert conflict_result is not None
    assert conflict_result["conflicts"] == []
    # All six taxonomy-declared candidates were still evaluated and persisted.
    assert conflict_result["arbitration"]["declared_pair_count"] == 6
    assert len(repo.get_alpha_conflicts(run_id)) == 6

    if response["dominant_alphas"]:
        assert response["summary"] == (
            "Dominant Alpha structures were identified, but no "
            "taxonomy-declared conflict was admitted for this research run."
        )
    else:
        assert response["summary"] == (
            "No dominant Alpha structure or admitted conflict was identified "
            "for this research run."
        )


# ---------------------------------------------------------------------------
# C. Week 3 failure
# ---------------------------------------------------------------------------


def test_week3_failure_never_calls_week4_detector_or_persistence(tmp_path, monkeypatch):
    import comqutor_alpha.api.routes_research as routes_research
    import comqutor_alpha.conflict_engine.pipeline as week4_pipeline

    detector_calls = []
    monkeypatch.setattr(
        week4_pipeline, "detect_alpha_conflicts", lambda **kwargs: detector_calls.append(kwargs)
    )
    monkeypatch.setattr(
        routes_research,
        "build_structure_graph_stage",
        lambda *a, **k: (_ for _ in ()).throw(RuntimeError("boom - construction")),
    )

    repo = _repo()
    persist_calls = []
    original_persist = repo.persist_week4_results

    def spy_persist(**kwargs):
        persist_calls.append(kwargs)
        return original_persist(**kwargs)

    repo.persist_week4_results = spy_persist

    response = run_research_request(_nvda_payload(), output_root=tmp_path, graph_repository=repo)
    run_id = response["run_id"]

    assert response["status"] != "completed"
    assert response["structure_graph_status"] == "not_ready"
    assert response["conflict_status"] == "not_ready"
    assert response["main_conflict"] is None
    assert response["dominant_alphas"] == []
    assert detector_calls == []
    assert persist_calls == []
    assert repo.get_week4_conflict_result(run_id) is None


# ---------------------------------------------------------------------------
# D. Detector failure
# ---------------------------------------------------------------------------


def test_detector_failure_preserves_week1_3_and_logs_safely(tmp_path, monkeypatch, caplog):
    import comqutor_alpha.conflict_engine.pipeline as week4_pipeline

    def poison(**_kwargs):
        raise _secret_bearing_exception()

    monkeypatch.setattr(week4_pipeline, "detect_alpha_conflicts", poison)

    repo = _repo()
    with caplog.at_level(logging.WARNING, logger="comqutor_alpha.conflict_engine.pipeline"):
        response = run_research_request(_nvda_payload(), output_root=tmp_path, graph_repository=repo)
    run_id = response["run_id"]

    assert response["status"] == "partial"
    assert response["structure_graph_status"] == "ready"
    assert response["conflict_status"] == "not_ready"
    assert response["main_conflict"] is None

    graph = get_persisted_structure_graph(run_id, output_root=tmp_path, graph_repository=repo)
    assert graph["status"] == "ok"

    # No half-written Week 4 rows.
    assert repo.get_alpha_activations(run_id) == []
    assert repo.get_alpha_conflicts(run_id) == []
    assert repo.get_week4_conflict_result(run_id) is None

    jsonl_path = tmp_path / run_id / "error_logs" / "week4_pipeline_errors.jsonl"
    jsonl_text = jsonl_path.read_text(encoding="utf-8")
    record = json.loads(jsonl_text.strip().splitlines()[-1])
    assert record["run_id"] == run_id
    assert record["stage"] == "conflict_detection"
    assert record["error_code"]
    assert set(record) == {"run_id", "stage", "error_code", "created_at"}

    app_log_text = "\n".join(r.getMessage() for r in caplog.records)
    for marker in _FORBIDDEN_MARKERS:
        assert marker not in jsonl_text
        assert marker not in app_log_text
    assert all(r.exc_info is None for r in caplog.records)


# ---------------------------------------------------------------------------
# E. Week 4 persistence failure
# ---------------------------------------------------------------------------


def test_week4_persistence_failure_preserves_week1_3_and_logs_safely(tmp_path, caplog):
    repo = _repo()

    def poison_persist(**_kwargs):
        raise _secret_bearing_exception()

    repo.persist_week4_results = poison_persist

    with caplog.at_level(logging.WARNING, logger="comqutor_alpha.conflict_engine.pipeline"):
        response = run_research_request(_nvda_payload(), output_root=tmp_path, graph_repository=repo)
    run_id = response["run_id"]

    assert response["status"] == "partial"
    assert response["structure_graph_status"] == "ready"
    assert response["conflict_status"] == "not_ready"
    assert response["main_conflict"] is None  # never fabricated

    graph = get_persisted_structure_graph(run_id, output_root=tmp_path, graph_repository=repo)
    assert graph["status"] == "ok"

    jsonl_path = tmp_path / run_id / "error_logs" / "week4_pipeline_errors.jsonl"
    jsonl_text = jsonl_path.read_text(encoding="utf-8")
    record = json.loads(jsonl_text.strip().splitlines()[-1])
    assert record["stage"] == "conflict_persistence"

    app_log_text = "\n".join(r.getMessage() for r in caplog.records)
    for marker in _FORBIDDEN_MARKERS:
        assert marker not in jsonl_text
        assert marker not in app_log_text
    assert all(r.exc_info is None for r in caplog.records)


# ---------------------------------------------------------------------------
# F. Conflicts API
# ---------------------------------------------------------------------------


def test_conflicts_api_success_equals_repository_reconstruction(tmp_path):
    repo = _repo()
    response = run_research_request(_nvda_payload(), output_root=tmp_path, graph_repository=repo)
    run_id = response["run_id"]

    expected = repo.get_week4_conflict_result(run_id)
    result = get_persisted_conflicts(run_id, output_root=tmp_path, graph_repository=repo)

    assert result["status"] == "ok"
    assert {k: v for k, v in result.items() if k != "status"} == expected


def test_conflicts_api_zero_admitted_conflict_still_status_ok(tmp_path):
    repo = _repo()
    response = run_research_request(_empty_evidence_payload(), output_root=tmp_path, graph_repository=repo)
    run_id = response["run_id"]

    result = get_persisted_conflicts(run_id, output_root=tmp_path, graph_repository=repo)
    assert result["status"] == "ok"
    assert result["conflicts"] == []
    assert result["main_conflict"] is None


def test_conflicts_api_invalid_run_id(tmp_path):
    repo = _repo()
    result = get_persisted_conflicts("../secret", output_root=tmp_path, graph_repository=repo)
    assert result["status"] == "failed"
    assert result["error_code"] == "INVALID_RUN_ID"


def test_conflicts_api_not_ready(tmp_path):
    repo = _repo()
    result = get_persisted_conflicts("totally_unknown_run", output_root=tmp_path, graph_repository=repo)
    assert result["status"] == "failed"
    assert result["error_code"] == "CONFLICTS_NOT_READY"


def test_conflicts_api_repository_unavailable():
    class BrokenRepository:
        def get_week4_conflict_result(self, run_id):
            raise GraphPersistenceError("DB_READ_FAILED")

    result = get_persisted_conflicts("some_run", output_root="unused", graph_repository=BrokenRepository())
    assert result["status"] == "failed"
    assert result["error_code"] == "CONFLICTS_UNAVAILABLE"


def test_conflicts_api_corrupted_reconstruction():
    class CorruptRepository:
        def get_week4_conflict_result(self, run_id):
            raise GraphPersistenceError("DB_DATA_CORRUPTED")

    result = get_persisted_conflicts("some_run", output_root="unused", graph_repository=CorruptRepository())
    assert result["status"] == "failed"
    assert result["error_code"] == "CONFLICTS_CORRUPTED"


def test_conflicts_api_survives_deleted_local_run_directory(tmp_path):
    import shutil

    repo = _repo()
    response = run_research_request(_nvda_payload(), output_root=tmp_path, graph_repository=repo)
    run_id = response["run_id"]

    shutil.rmtree(tmp_path / run_id)
    assert not (tmp_path / run_id).exists()

    result = get_persisted_conflicts(run_id, output_root=tmp_path, graph_repository=repo)
    assert result["status"] == "ok"
    assert result["main_conflict"]["conflict_id"] == "A101__A304"


def test_conflicts_api_default_resolution_creates_no_sqlite_file_or_migration(tmp_path, monkeypatch):
    import comqutor_alpha.storage.db.repository as repository_module

    monkeypatch.delenv("COMQUTOR_ENV", raising=False)
    monkeypatch.delenv("COMQUTOR_DATABASE_URL", raising=False)
    migration_calls = []
    monkeypatch.setattr(
        repository_module, "apply_migrations", lambda engine: migration_calls.append(engine)
    )

    result = get_persisted_conflicts("never_persisted_run", output_root=tmp_path)

    assert result["status"] == "failed"
    assert result["error_code"] == "CONFLICTS_NOT_READY"
    assert migration_calls == []
    assert not list(tmp_path.glob("**/_comqutor_alpha_graph.db"))


# ---------------------------------------------------------------------------
# H. Determinism (POST vs GET agreement)
# ---------------------------------------------------------------------------


def test_post_and_get_agree_on_week4_response_fields(tmp_path):
    repo = _repo()
    post_response = run_research_request(_nvda_payload(), output_root=tmp_path, graph_repository=repo)
    run_id = post_response["run_id"]

    get_response = get_research_run(run_id, output_root=tmp_path, graph_repository=repo)

    assert get_response["dominant_alphas"] == post_response["dominant_alphas"]
    assert get_response["main_conflict"] == post_response["main_conflict"]
    assert get_response["conflict_status"] == post_response["conflict_status"]
    assert get_response["summary"] == post_response["summary"]

    # build_research_response itself (used by both POST's return path and
    # the GET route) is independently deterministic across repeated calls.
    third = build_research_response(run_id, output_root=tmp_path, graph_repository=repo)
    assert third["main_conflict"] == post_response["main_conflict"]
    assert third["summary"] == post_response["summary"]


def test_week4_pipeline_replace_is_idempotent_across_retries(tmp_path):
    import comqutor_alpha.api.routes_research as routes_research

    run_dir = _seed_week1_2_artifacts(
        tmp_path,
        "w4_retry_idempotent",
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

    result = repo.get_week4_conflict_result("w4_retry_idempotent")
    assert result is not None
    assert len(repo.get_alpha_conflicts("w4_retry_idempotent")) == 6  # no duplicate rows

    response = build_research_response("w4_retry_idempotent", output_root=tmp_path, graph_repository=repo)
    assert response["conflict_status"] == "ready"


def test_conflict_detector_inputs_come_from_this_runs_own_persisted_artifacts(tmp_path):
    """Cross-check: the conflict result the pipeline persisted is exactly
    what a manual call to detect_alpha_conflicts() produces from this run's
    own persisted alpha_matches + graph activation -- proving the pipeline
    neither recomputes activation nor mixes in another run's data."""
    repo = _repo()
    response = run_research_request(_nvda_payload(), output_root=tmp_path, graph_repository=repo)
    run_id = response["run_id"]

    graph = get_persisted_structure_graph(run_id, output_root=tmp_path, graph_repository=repo)
    matches_payload = json.loads((tmp_path / run_id / "alpha_matches.json").read_text(encoding="utf-8"))

    recomputed = detect_alpha_conflicts(
        run_id=run_id,
        ticker="NVDA",
        activation_payload=graph["activation"],
        alpha_matches=matches_payload["matches"],
    )
    persisted = repo.get_week4_conflict_result(run_id)
    assert persisted == recomputed
