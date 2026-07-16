import json
import shutil

import pytest

from comqutor_alpha.api.routes_research import (
    get_persisted_structure_graph,
    run_research_request,
)
from comqutor_alpha.storage.db.engine import build_engine
from comqutor_alpha.storage.db.migrations import apply_migrations
from comqutor_alpha.storage.db.repository import GraphPersistenceError, GraphPersistenceRepository


def _offline_outputs():
    return [
        {"agent": "technical_agent", "raw_output": "NVDA shows positive momentum but high valuation creates downside risk."},
        {"agent": "news_agent", "raw_output": "AI capex is increasing and driving GPU demand."},
        {"agent": "fundamental_agent", "raw_output": "Revenue guidance was raised due to strong customer demand."},
    ]


def _payload():
    return {
        "ticker": "NVDA",
        "analysis_date": "2026-06-30",
        "selected_analysts": ["market", "news", "fundamentals"],
        "offline_raw_agent_outputs": _offline_outputs(),
    }


def _repo():
    # GraphPersistenceRepository's constructor no longer applies migrations
    # itself (write-path-only now); apply explicitly for direct construction.
    engine = build_engine("sqlite:///:memory:")
    apply_migrations(engine)
    return GraphPersistenceRepository(engine)


def test_post_research_returns_run_id(tmp_path):
    repo = _repo()
    response = run_research_request(_payload(), output_root=tmp_path, graph_repository=repo)

    assert response["status"] == "completed"
    assert response["run_id"]


def test_post_response_shape_is_unchanged_by_week3(tmp_path):
    """Frozen Week 2 contract: adding Week 3 must not add/remove/rename any
    field of the POST /api/research response."""
    repo = _repo()
    response = run_research_request(_payload(), output_root=tmp_path, graph_repository=repo)

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


def test_graph_stage_completes_file_and_db(tmp_path):
    repo = _repo()
    response = run_research_request(_payload(), output_root=tmp_path, graph_repository=repo)
    run_id = response["run_id"]

    graph_file = tmp_path / run_id / "structure_graph.json"
    assert graph_file.exists()
    file_payload = json.loads(graph_file.read_text())

    db_row = repo.get_graph(run_id)
    assert db_row is not None
    assert db_row["graph_json"] == file_payload  # file artifact and DB source-of-truth agree


def test_get_graph_returns_the_exact_persisted_run(tmp_path):
    repo = _repo()
    response = run_research_request(_payload(), output_root=tmp_path, graph_repository=repo)
    run_id = response["run_id"]

    graph = get_persisted_structure_graph(run_id, output_root=tmp_path, graph_repository=repo)

    assert graph["status"] == "ok"
    assert graph["run_id"] == run_id
    assert graph["ticker"] == "NVDA"
    assert len(graph["activation"]["alphas"]) == 10
    assert "nodes" in graph and "edges" in graph
    assert "graph_coherence" in graph
    assert "dominant_alphas" in graph

    db_row = repo.get_graph(run_id)
    assert graph["nodes"] == db_row["graph_json"]["nodes"]
    assert graph["activation"] == db_row["graph_json"]["activation"]


def test_get_graph_is_db_first_when_local_run_directory_is_missing(tmp_path):
    repo = _repo()
    response = run_research_request(_payload(), output_root=tmp_path, graph_repository=repo)
    run_id = response["run_id"]
    shutil.rmtree(tmp_path / run_id)

    graph = get_persisted_structure_graph(
        run_id, output_root=tmp_path, graph_repository=repo
    )

    assert graph["status"] == "ok"
    assert graph["run_id"] == run_id


def test_get_graph_invalid_run_id(tmp_path):
    repo = _repo()
    response = get_persisted_structure_graph("../secret", output_root=tmp_path, graph_repository=repo)

    assert response["status"] == "failed"
    assert response["error_code"] == "INVALID_RUN_ID"


def test_get_graph_unknown_run_id(tmp_path):
    repo = _repo()
    response = get_persisted_structure_graph("totally_unknown_run", output_root=tmp_path, graph_repository=repo)

    assert response["status"] == "failed"
    assert response["error_code"] == "RUN_NOT_FOUND"


def test_get_graph_not_ready_when_run_exists_but_graph_was_never_persisted(tmp_path):
    repo = _repo()
    run_dir = tmp_path / "partial_run"
    run_dir.mkdir()
    (run_dir / "metadata.json").write_text(json.dumps({"run_id": "partial_run", "ticker": "NVDA"}), encoding="utf-8")

    response = get_persisted_structure_graph("partial_run", output_root=tmp_path, graph_repository=repo)

    assert response["status"] == "failed"
    assert response["error_code"] == "GRAPH_NOT_READY"


def test_week2_failure_leaves_graph_not_ready_but_preserves_week1_artifacts(tmp_path, monkeypatch):
    import comqutor_alpha.api.routes_research as routes_research

    def fail_alpha_matches(*_args, **_kwargs):
        raise RuntimeError("boom")

    monkeypatch.setattr(routes_research, "save_alpha_matches", fail_alpha_matches)
    repo = _repo()
    response = run_research_request(_payload(), output_root=tmp_path, graph_repository=repo)
    run_id = response["run_id"]

    assert response["status"] == "partial"
    assert (tmp_path / run_id / "raw_agent_outputs.json").exists()
    assert (tmp_path / run_id / "structured_agent_outputs.json").exists()

    graph = get_persisted_structure_graph(run_id, output_root=tmp_path, graph_repository=repo)
    assert graph["status"] == "failed"
    assert graph["error_code"] == "GRAPH_NOT_READY"


def test_get_graph_database_failure_is_safe(tmp_path):
    class BrokenRepository:
        def get_graph(self, run_id):
            raise GraphPersistenceError("DB_READ_FAILED")

    run_dir = tmp_path / "some_run"
    run_dir.mkdir()
    (run_dir / "metadata.json").write_text(json.dumps({"run_id": "some_run"}), encoding="utf-8")

    response = get_persisted_structure_graph("some_run", output_root=tmp_path, graph_repository=BrokenRepository())

    assert response["status"] == "failed"
    assert response["error_code"] == "GRAPH_UNAVAILABLE"


def test_get_graph_unexpected_non_persistence_error_is_also_safe(tmp_path):
    """Engine/repository construction can fail in ways that are not
    GraphPersistenceError (e.g. a raw OSError creating a SQLite file); that
    must still degrade to a safe GRAPH_UNAVAILABLE body, not an uncaught
    traceback."""

    class ExplodingRepository:
        def get_graph(self, run_id):
            raise OSError("disk full")

    run_dir = tmp_path / "some_run"
    run_dir.mkdir()
    (run_dir / "metadata.json").write_text(json.dumps({"run_id": "some_run"}), encoding="utf-8")

    response = get_persisted_structure_graph(
        "some_run", output_root=tmp_path, graph_repository=ExplodingRepository()
    )

    assert response["status"] == "failed"
    assert response["error_code"] == "GRAPH_UNAVAILABLE"
    assert "disk full" not in json.dumps(response)


def test_graph_corrupted_missing_required_keys(tmp_path):
    class StubRepository:
        def get_graph(self, run_id):
            return {"run_id": run_id, "ticker": "NVDA", "graph_json": {"schema_version": "week3.structure_graph.v1"}}

    run_dir = tmp_path / "corrupt_run"
    run_dir.mkdir()
    (run_dir / "metadata.json").write_text(json.dumps({"run_id": "corrupt_run"}), encoding="utf-8")

    response = get_persisted_structure_graph("corrupt_run", output_root=tmp_path, graph_repository=StubRepository())

    assert response["status"] == "failed"
    assert response["error_code"] == "GRAPH_CORRUPTED"


def test_graph_schema_mismatch_is_rejected_safely(tmp_path):
    class StubRepository:
        def get_graph(self, run_id):
            return {
                "run_id": run_id,
                "ticker": "NVDA",
                "graph_json": {
                    "schema_version": "week99.some_future_schema",
                    "nodes": [],
                    "edges": [],
                    "activation": {},
                    "dominant_alphas": [],
                },
            }

    run_dir = tmp_path / "mismatch_run"
    run_dir.mkdir()
    (run_dir / "metadata.json").write_text(json.dumps({"run_id": "mismatch_run"}), encoding="utf-8")

    response = get_persisted_structure_graph("mismatch_run", output_root=tmp_path, graph_repository=StubRepository())

    assert response["status"] == "failed"
    assert response["error_code"] == "GRAPH_SCHEMA_MISMATCH"


def test_no_paths_dsn_secrets_or_traceback_in_any_graph_response(tmp_path):
    repo = _repo()
    response = run_research_request(_payload(), output_root=tmp_path, graph_repository=repo)
    run_id = response["run_id"]
    graph = get_persisted_structure_graph(run_id, output_root=tmp_path, graph_repository=repo)

    serialized = json.dumps(graph, ensure_ascii=False)
    assert str(tmp_path) not in serialized
    assert "sqlite:///" not in serialized
    assert "Traceback" not in serialized
    assert "run_dir" not in graph


def test_get_graph_performs_no_llm_or_graph_rebuild_calls(tmp_path, monkeypatch):
    import comqutor_alpha.api.routes_research as routes_research

    repo = _repo()
    response = run_research_request(_payload(), output_root=tmp_path, graph_repository=repo)
    run_id = response["run_id"]

    def poison(*_args, **_kwargs):
        raise AssertionError("GET must never rebuild the graph")

    monkeypatch.setattr(routes_research, "build_structure_graph_stage", poison)
    monkeypatch.setattr(routes_research, "score_and_assemble_structure_graph", poison)

    graph = get_persisted_structure_graph(run_id, output_root=tmp_path, graph_repository=repo)
    assert graph["status"] == "ok"  # did not raise -> build_and_score_structure_graph was never called


def test_get_graph_does_not_mutate_storage(tmp_path):
    repo = _repo()
    response = run_research_request(_payload(), output_root=tmp_path, graph_repository=repo)
    run_id = response["run_id"]

    before = repo.get_graph(run_id)
    get_persisted_structure_graph(run_id, output_root=tmp_path, graph_repository=repo)
    get_persisted_structure_graph(run_id, output_root=tmp_path, graph_repository=repo)
    after = repo.get_graph(run_id)

    assert before == after


class _PersistenceFailingRepository:
    """Wraps a real repository so persist_run fails but reads still hit the
    same underlying engine -- lets a test prove nothing was written, rather
    than just querying a separate, trivially-empty database."""

    def __init__(self, inner):
        self._inner = inner

    def persist_run(self, **_kwargs):
        raise RuntimeError("boom - db write failed")

    def persist_agent_outputs(self, **kwargs):
        return self._inner.persist_agent_outputs(**kwargs)

    def get_graph(self, run_id):
        return self._inner.get_graph(run_id)

    def get_alpha_matches(self, run_id):
        return self._inner.get_alpha_matches(run_id)


def test_post_does_not_return_completed_when_graph_construction_fails(tmp_path, monkeypatch):
    import comqutor_alpha.api.routes_research as routes_research

    def broken_construction(*_args, **_kwargs):
        raise RuntimeError("boom - graph construction")

    monkeypatch.setattr(routes_research, "build_structure_graph_stage", broken_construction)
    repo = _repo()
    response = run_research_request(_payload(), output_root=tmp_path, graph_repository=repo)
    run_id = response["run_id"]

    assert response["status"] != "completed"
    assert response["status"] == "partial"  # Week 1-2 still fully succeeded
    assert response["structure_graph_status"] == "not_ready"
    assert response["artifacts"]["alpha_matches"] is True  # Week 1-2 artifacts preserved
    assert response["artifacts"]["extracted_structures"] is True
    assert not (tmp_path / run_id / "structure_graph.json").exists()

    graph = get_persisted_structure_graph(run_id, output_root=tmp_path, graph_repository=repo)
    assert graph["status"] == "failed"
    assert graph["error_code"] == "GRAPH_NOT_READY"


def test_post_does_not_return_completed_when_activation_scoring_fails(tmp_path, monkeypatch):
    import comqutor_alpha.api.routes_research as routes_research

    def broken_scoring(*_args, **_kwargs):
        raise RuntimeError("boom - activation scoring")

    monkeypatch.setattr(routes_research, "score_and_assemble_structure_graph", broken_scoring)
    repo = _repo()
    response = run_research_request(_payload(), output_root=tmp_path, graph_repository=repo)
    run_id = response["run_id"]

    assert response["status"] != "completed"
    assert response["status"] == "partial"
    assert response["structure_graph_status"] == "not_ready"
    assert response["artifacts"]["alpha_matches"] is True
    assert response["artifacts"]["extracted_structures"] is True
    assert not (tmp_path / run_id / "structure_graph.json").exists()

    graph = get_persisted_structure_graph(run_id, output_root=tmp_path, graph_repository=repo)
    assert graph["status"] == "failed"
    assert graph["error_code"] == "GRAPH_NOT_READY"


def test_post_does_not_return_completed_when_graph_persistence_fails(tmp_path):
    real_repo = _repo()
    failing_repo = _PersistenceFailingRepository(real_repo)

    response = run_research_request(_payload(), output_root=tmp_path, graph_repository=failing_repo)
    run_id = response["run_id"]

    assert response["status"] != "completed"
    assert response["status"] == "partial"
    assert response["structure_graph_status"] == "not_ready"
    # In this failure mode the file artifact was already written before the
    # DB write was attempted and failed -- file and DB are allowed to
    # briefly disagree on a failed run, but "completed" must still not be
    # reported and the DB (source of truth) must show nothing persisted.
    assert (tmp_path / run_id / "structure_graph.json").exists()
    assert real_repo.get_graph(run_id) is None
    assert real_repo.get_alpha_matches(run_id) == []

    graph = get_persisted_structure_graph(run_id, output_root=tmp_path, graph_repository=failing_repo)
    assert graph["status"] == "failed"
    assert graph["error_code"] == "GRAPH_NOT_READY"


try:
    from fastapi.testclient import TestClient

    from comqutor_alpha.api.routes_research import router

    FASTAPI_AVAILABLE = router is not None
except ImportError:
    FASTAPI_AVAILABLE = False


@pytest.mark.skipif(not FASTAPI_AVAILABLE, reason="fastapi is not installed")
def test_graph_route_is_registered_and_returns_safe_body_for_invalid_run_id():
    from fastapi import FastAPI

    app = FastAPI()
    app.include_router(router)
    client = TestClient(app)

    response = client.get("/api/research/../secret/graph")

    # Either FastAPI's own path normalization rejects this, or the handler
    # does -- either way it must never 500 or leak a traceback.
    assert response.status_code < 500
    if response.status_code == 200:
        body = response.json()
        assert body["status"] == "failed"
        assert body["error_code"] == "INVALID_RUN_ID"


@pytest.mark.skipif(not FASTAPI_AVAILABLE, reason="fastapi is not installed")
def test_graph_route_unknown_run_returns_stable_error_body():
    from fastapi import FastAPI

    app = FastAPI()
    app.include_router(router)
    client = TestClient(app)

    response = client.get("/api/research/unknown_run_xyz/graph")

    assert response.status_code == 200
    body = response.json()
    assert body["status"] == "failed"
    assert body["error_code"] == "RUN_NOT_FOUND"
