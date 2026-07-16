"""PostgreSQL verification for migration 0004 and structured output rows."""

from __future__ import annotations

import os
import uuid

import pytest
import sqlalchemy as sa
from sqlalchemy.exc import SQLAlchemyError

from comqutor_alpha.storage.db.engine import build_engine
from comqutor_alpha.storage.db.migrations import apply_migrations
from comqutor_alpha.storage.db.repository import GraphPersistenceError, GraphPersistenceRepository
from comqutor_alpha.storage.db.schema import agent_outputs, schema_migrations

pytestmark = pytest.mark.integration


@pytest.fixture(scope="module")
def postgres_context():
    url = os.environ.get("COMQUTOR_TEST_DATABASE_URL", "").strip()
    if not url:
        pytest.skip("COMQUTOR_TEST_DATABASE_URL not configured")
    if not url.startswith(("postgresql://", "postgresql+psycopg://")):
        pytest.fail("COMQUTOR_TEST_DATABASE_URL is not a PostgreSQL DSN")
    try:
        engine = build_engine(url)
        with engine.connect() as conn:
            conn.execute(sa.text("SELECT 1"))
        apply_migrations(engine)
    except (ImportError, SQLAlchemyError):
        pytest.fail("Configured PostgreSQL verification database is unavailable")

    context = {
        "engine": engine,
        "repo": GraphPersistenceRepository(engine),
        "prefix": f"w6_agent_outputs_{uuid.uuid4().hex}",
        "run_ids": set(),
    }
    yield context

    if context["run_ids"]:
        with engine.begin() as conn:
            conn.execute(
                sa.delete(agent_outputs).where(
                    agent_outputs.c.run_id.in_(context["run_ids"])
                )
            )
    engine.dispose()


def _run_id(context, suffix):
    run_id = f"{context['prefix']}_{suffix}"
    context["run_ids"].add(run_id)
    return run_id


def _record(run_id, claim_id="c1", confidence=0.8):
    return {
        "claim_id": claim_id,
        "source_agent_output_id": f"raw-{claim_id}",
        "run_id": run_id,
        "ticker": "NVDA",
        "agent": "news_agent",
        "claim": "GPU demand is increasing due to AI training.",
        "evidence": "GPU demand is increasing due to AI training.",
        "entities": ["NVDA"],
        "factors": ["GPU Demand", "AI Demand"],
        "direction": "positive",
        "confidence": confidence,
        "source_type": "news",
        "source_refs": [f"raw-{claim_id}"],
        "claim_index": 0,
        "assertion_status": "asserted",
        "semantic_polarity": "activation",
    }


def _payload(run_id, *records):
    return {"run_id": run_id, "ticker": "NVDA", "records": list(records)}


def test_migration_and_jsonb_columns(postgres_context):
    engine = postgres_context["engine"]
    inspector = sa.inspect(engine)
    assert "agent_outputs" in inspector.get_table_names()
    with engine.connect() as conn:
        version_count = conn.scalar(
            sa.select(sa.func.count())
            .select_from(schema_migrations)
            .where(schema_migrations.c.version == "0004_create_agent_outputs")
        )
        json_types = dict(
            conn.execute(
                sa.text(
                    "SELECT column_name, data_type FROM information_schema.columns "
                    "WHERE table_name = 'agent_outputs' "
                    "AND column_name IN ('entities', 'factors', 'source_refs')"
                )
            ).all()
        )
    assert version_count == 1
    assert json_types == {"entities": "jsonb", "factors": "jsonb", "source_refs": "jsonb"}


def test_round_trip_replace_and_idempotency(postgres_context):
    repo = postgres_context["repo"]
    run_id = _run_id(postgres_context, "replace")
    first = _payload(run_id, _record(run_id, "c1"), _record(run_id, "c2"))
    repo.persist_agent_outputs(run_id=run_id, ticker="NVDA", structured_payload=first)
    repo.persist_agent_outputs(run_id=run_id, ticker="NVDA", structured_payload=first)
    repo.persist_agent_outputs(
        run_id=run_id,
        ticker="NVDA",
        structured_payload=_payload(run_id, _record(run_id, "c2"), _record(run_id, "c3")),
    )

    assert [row["claim_id"] for row in repo.list_agent_outputs(run_id)] == ["c2", "c3"]
    assert repo.count_agent_outputs(run_id) == 2


def test_run_isolation(postgres_context):
    repo = postgres_context["repo"]
    run_a = _run_id(postgres_context, "isolation_a")
    run_b = _run_id(postgres_context, "isolation_b")
    repo.persist_agent_outputs(
        run_id=run_a,
        ticker="NVDA",
        structured_payload=_payload(run_a, _record(run_a, "a")),
    )
    repo.persist_agent_outputs(
        run_id=run_b,
        ticker="NVDA",
        structured_payload=_payload(run_b, _record(run_b, "b")),
    )

    assert [row["claim_id"] for row in repo.list_agent_outputs(run_a)] == ["a"]
    assert [row["claim_id"] for row in repo.list_agent_outputs(run_b)] == ["b"]


def test_invalid_replace_preserves_previous_rows(postgres_context):
    repo = postgres_context["repo"]
    run_id = _run_id(postgres_context, "rollback")
    good = _payload(run_id, _record(run_id))
    repo.persist_agent_outputs(run_id=run_id, ticker="NVDA", structured_payload=good)
    before = repo.list_agent_outputs(run_id)

    with pytest.raises(GraphPersistenceError) as exc_info:
        repo.persist_agent_outputs(
            run_id=run_id,
            ticker="NVDA",
            structured_payload=_payload(run_id, _record(run_id, confidence="0.8")),
        )

    assert exc_info.value.reason_code == "AGENT_OUTPUTS_PAYLOAD_INVALID"
    assert repo.list_agent_outputs(run_id) == before
