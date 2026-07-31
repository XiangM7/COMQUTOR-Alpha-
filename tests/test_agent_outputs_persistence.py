"""Formal Week 1 structured agent-output database persistence tests."""

from __future__ import annotations

import copy
import json

import pytest
import sqlalchemy as sa

from comqutor_alpha.api.agent_output_reader import get_agent_outputs_response
from comqutor_alpha.api.routes_research import run_research_request
from comqutor_alpha.research_lifecycle import submit_research_request
from comqutor_alpha.storage.db.engine import build_engine
from comqutor_alpha.storage.db.migrations import apply_migrations
from comqutor_alpha.storage.db.repository import GraphPersistenceError, GraphPersistenceRepository
from comqutor_alpha.storage.db.schema import agent_outputs, schema_migrations
from scripts.w5_demo_fixtures import approved_demo_outputs


def _repo():
    engine = build_engine("sqlite:///:memory:")
    apply_migrations(engine)
    return engine, GraphPersistenceRepository(engine)


def _record(run_id: str, claim_id: str = "claim-1", **overrides):
    record = {
        "claim_id": claim_id,
        "agent_output_id": claim_id,
        "source_agent_output_id": "raw-news-1",
        "run_id": run_id,
        "ticker": "NVDA",
        "agent": "news_agent",
        "timestamp": "2026-06-30T12:00:00Z",
        "claim": "GPU demand is increasing due to AI training.",
        "evidence": "GPU demand is increasing due to AI training.",
        "entities": ["NVDA"],
        "factors": ["AI Demand", "GPU Demand"],
        "direction": "positive",
        "confidence": 0.8,
        "source_type": "news",
        "output_type": "analyst",
        "source_refs": ["raw-news-1"],
        "claim_index": 0,
        "source_section": "Demand",
        "assertion_status": "asserted",
        "semantic_polarity": "activation",
        "extraction_method": "deterministic_splitter",
    }
    record.update(overrides)
    return record


def _payload(run_id: str, *records):
    return {
        "schema_version": "week1a.structured_agent_outputs.v2",
        "run_id": run_id,
        "ticker": "NVDA",
        "records": list(records),
    }


def test_migration_0004_creates_agent_outputs_contract():
    engine, _ = _repo()
    inspector = sa.inspect(engine)

    assert "agent_outputs" in inspector.get_table_names()
    assert set(agent_outputs.c.keys()).issuperset(
        {
            "id",
            "run_id",
            "claim_id",
            "ticker",
            "agent",
            "claim",
            "evidence",
            "entities",
            "factors",
            "direction",
            "confidence",
            "source_type",
            "source_refs",
            "created_at",
        }
    )
    assert agent_outputs.c.id.primary_key
    assert any(
        {column.name for column in constraint.columns} == {"run_id", "claim_id"}
        for constraint in agent_outputs.constraints
        if isinstance(constraint, sa.UniqueConstraint)
    )
    indexes = {index.name: tuple(index.columns.keys()) for index in agent_outputs.indexes}
    assert indexes["ix_agent_outputs_run_id"] == ("run_id",)
    assert indexes["ix_agent_outputs_run_agent"] == ("run_id", "agent")
    assert isinstance(agent_outputs.c.entities.type.dialect_impl(engine.dialect), sa.JSON)

    with engine.connect() as conn:
        versions = set(conn.execute(sa.select(schema_migrations.c.version)).scalars())
    assert "0004_create_agent_outputs" in versions


def test_replace_is_transactional_idempotent_and_preserves_stable_ids():
    engine, repo = _repo()
    first_payload = _payload("run-1", _record("run-1", "c1"), _record("run-1", "c2"))
    repo.persist_agent_outputs(run_id="run-1", ticker="NVDA", structured_payload=first_payload)

    with engine.connect() as conn:
        before = {
            row.claim_id: (row.id, row.created_at)
            for row in conn.execute(
                sa.select(agent_outputs).where(agent_outputs.c.run_id == "run-1")
            )
        }

    repo.persist_agent_outputs(run_id="run-1", ticker="NVDA", structured_payload=first_payload)
    replacement = _payload("run-1", _record("run-1", "c2"), _record("run-1", "c3"))
    repo.persist_agent_outputs(run_id="run-1", ticker="NVDA", structured_payload=replacement)

    with engine.connect() as conn:
        after = {
            row.claim_id: (row.id, row.created_at)
            for row in conn.execute(
                sa.select(agent_outputs).where(agent_outputs.c.run_id == "run-1")
            )
        }
    assert set(after) == {"c2", "c3"}
    assert after["c2"] == before["c2"]
    assert repo.count_agent_outputs("run-1") == 2


def test_non_substantive_record_is_never_inserted():
    """Unified Claim Admissibility Sprint, spec test #6 / persistence
    admission boundary: an adapter-error placeholder (or any record the
    shared quality gate rejects) must never reach the agent_outputs table,
    even though it is a structurally valid row on its own."""
    _, repo = _repo()
    placeholder = _record(
        "run-1",
        "c-placeholder",
        claim="unknown",
        evidence="unknown",
        direction="unknown",
        confidence=0.0,
        factors=[],
        claim_quality="non_substantive",
        analysis_eligible=False,
    )
    real = _record("run-1", "c-real")
    payload = _payload("run-1", placeholder, real)

    repo.persist_agent_outputs(run_id="run-1", ticker="NVDA", structured_payload=payload)

    stored_ids = {row["claim_id"] for row in repo.list_agent_outputs("run-1")}
    assert stored_ids == {"c-real"}
    assert repo.count_agent_outputs("run-1") == 1


@pytest.mark.parametrize("bad_confidence", [float("nan"), float("inf"), -0.1, 1.1, "0.8", True])
def test_invalid_confidence_rejected_without_deleting_prior_rows(bad_confidence):
    _, repo = _repo()
    good = _payload("run-1", _record("run-1"))
    repo.persist_agent_outputs(run_id="run-1", ticker="NVDA", structured_payload=good)
    before = repo.list_agent_outputs("run-1")

    bad = _payload("run-1", _record("run-1", confidence=bad_confidence))
    with pytest.raises(GraphPersistenceError) as exc_info:
        repo.persist_agent_outputs(run_id="run-1", ticker="NVDA", structured_payload=bad)

    assert exc_info.value.reason_code == "AGENT_OUTPUTS_PAYLOAD_INVALID"
    assert repo.list_agent_outputs("run-1") == before


@pytest.mark.parametrize(
    "unsafe_text",
    [
        "Leaked api_key=sk-sensitive-value in analysis.",
        "Evidence was loaded from /Users/example/private/report.md.",
    ],
)
def test_sensitive_text_is_rejected_without_deleting_prior_rows(unsafe_text):
    _, repo = _repo()
    good = _payload("run-1", _record("run-1"))
    repo.persist_agent_outputs(run_id="run-1", ticker="NVDA", structured_payload=good)
    before = repo.list_agent_outputs("run-1")

    unsafe = _payload("run-1", _record("run-1", evidence=unsafe_text))
    with pytest.raises(GraphPersistenceError) as exc_info:
        repo.persist_agent_outputs(run_id="run-1", ticker="NVDA", structured_payload=unsafe)

    assert exc_info.value.reason_code == "AGENT_OUTPUTS_PAYLOAD_INVALID"
    assert repo.list_agent_outputs("run-1") == before


def test_db_first_reader_works_without_local_run_directory(tmp_path):
    _, repo = _repo()
    db_record = _record("db-run", claim="Database source of truth claim.")
    repo.persist_agent_outputs(
        run_id="db-run", ticker="NVDA", structured_payload=_payload("db-run", db_record)
    )

    result = get_agent_outputs_response(
        "db-run", output_root=tmp_path, graph_repository=repo
    )

    assert result["status"] == "ok"
    assert result["count"] == 1
    assert result["structured_agent_outputs"][0]["claim"] == "Database source of truth claim."
    assert not (tmp_path / "db-run").exists()


def test_db_rows_override_tampered_legacy_artifact(tmp_path):
    _, repo = _repo()
    repo.persist_agent_outputs(
        run_id="db-wins",
        ticker="NVDA",
        structured_payload=_payload(
            "db-wins", _record("db-wins", claim="Trusted database claim.")
        ),
    )
    run_dir = tmp_path / "db-wins"
    run_dir.mkdir()
    artifact = _payload(
        "db-wins", _record("db-wins", claim="Tampered artifact claim.")
    )
    (run_dir / "structured_agent_outputs.json").write_text(json.dumps(artifact), encoding="utf-8")

    result = get_agent_outputs_response(
        "db-wins", output_root=tmp_path, graph_repository=repo
    )

    serialized = json.dumps(result)
    assert "Trusted database claim." in serialized
    assert "Tampered artifact claim." not in serialized


def test_legacy_artifact_fallback_remains_available(tmp_path):
    _, repo = _repo()
    run_dir = tmp_path / "legacy-run"
    run_dir.mkdir()
    (run_dir / "structured_agent_outputs.json").write_text(
        json.dumps(_payload("legacy-run", _record("legacy-run"))), encoding="utf-8"
    )

    result = get_agent_outputs_response(
        "legacy-run", output_root=tmp_path, graph_repository=repo
    )

    assert result["status"] == "ok"
    assert result["count"] == 1


def test_database_failure_does_not_fall_back_to_artifact(tmp_path):
    class UnavailableRepository:
        def list_agent_outputs(self, run_id):
            raise GraphPersistenceError("DB_READ_FAILED")

    run_dir = tmp_path / "new-run"
    run_dir.mkdir()
    (run_dir / "structured_agent_outputs.json").write_text(
        json.dumps(_payload("new-run", _record("new-run"))), encoding="utf-8"
    )

    result = get_agent_outputs_response(
        "new-run", output_root=tmp_path, graph_repository=UnavailableRepository()
    )

    assert result["status"] == "failed"
    assert result["error_code"] == "AGENT_OUTPUTS_UNAVAILABLE"
    assert "structured_agent_outputs" not in result


def test_pipeline_persists_claims_before_alpha_mapping_and_keeps_traceability(tmp_path):
    _, repo = _repo()
    response = run_research_request(
        {
            "ticker": "NVDA",
            "analysis_date": "2026-06-30",
            "offline_raw_agent_outputs": approved_demo_outputs("NVDA"),
        },
        output_root=tmp_path,
        graph_repository=repo,
    )

    assert response["status"] == "completed"
    rows = repo.list_agent_outputs(response["run_id"])
    alpha_matches = repo.get_alpha_matches(response["run_id"])
    assert rows
    assert repo.count_agent_outputs(response["run_id"]) == len(rows)
    output_by_claim = {row["claim_id"]: row for row in rows}
    for match in alpha_matches:
        output = output_by_claim[match["claim_id"]]
        assert match["source_agent_output_id"] == output["source_agent_output_id"]
        assert match["evidence"] == output["evidence"]


def test_database_write_failure_is_safe_and_terminal(tmp_path, monkeypatch):
    _, repo = _repo()

    def fail_write(**_kwargs):
        raise GraphPersistenceError("DB_WRITE_FAILED")

    monkeypatch.setattr(repo, "persist_agent_outputs", fail_write)
    response = submit_research_request(
        {
            "ticker": "NVDA",
            "analysis_date": "2026-06-30",
            "offline_raw_agent_outputs": copy.deepcopy(approved_demo_outputs("NVDA")),
        },
        output_root=tmp_path,
        graph_repository=repo,
    )

    assert response["status"] == "failed"
    assert response["error_code"] == "AGENT_OUTPUTS_DB_WRITE_FAILED"
    assert response["run_status"] == "failed"
    record = repo.get_research_run_record(response["run_id"])
    assert record["status"] == "failed"
    assert record["error_code"] == "AGENT_OUTPUTS_DB_WRITE_FAILED"
    serialized = json.dumps(response)
    assert str(tmp_path) not in serialized
    assert "sqlite" not in serialized.lower()


def test_malformed_database_row_fails_closed():
    engine, repo = _repo()
    repo.persist_agent_outputs(
        run_id="corrupt-run",
        ticker="NVDA",
        structured_payload=_payload("corrupt-run", _record("corrupt-run")),
    )
    with engine.begin() as conn:
        conn.execute(
            sa.update(agent_outputs)
            .where(agent_outputs.c.run_id == "corrupt-run")
            .values(entities={"not": "a list"})
        )

    with pytest.raises(GraphPersistenceError) as exc_info:
        repo.list_agent_outputs("corrupt-run")
    assert exc_info.value.reason_code == "DB_DATA_CORRUPTED"
