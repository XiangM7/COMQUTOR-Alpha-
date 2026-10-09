"""T1 Part Four (COMQUTOR Alpha next-round task, 2026-09-28): real ORM
schema/migration/read-write coverage for the six new source-linking columns
on ``agent_outputs`` (source_link_status/linked_source_id/
source_link_method/content_support_status/content_support_method/
content_support_review).

SQLite (in-memory) is used here as the dialect-portable, offline-testable
target this repository's own migration/repository code already treats as a
first-class backend (see comqutor_alpha.storage.db.schema's own module
docstring: "SQLite (the offline/test fallback backend)"). This is NOT
offered as PostgreSQL verification -- see
tests/test_agent_outputs_postgres_integration.py (pytest.mark.integration,
run against the real, isolated COMQUTOR_TEST_DATABASE_URL) for that. Every
test here exercises the REAL comqutor_alpha.storage.db.migrations /
comqutor_alpha.storage.db.repository code, never a re-implementation.
"""

from __future__ import annotations

import sqlalchemy as sa

from comqutor_alpha.storage.db.engine import build_engine
from comqutor_alpha.storage.db.migrations import (
    apply_column_migrations,
    apply_migrations,
)
from comqutor_alpha.storage.db.repository import GraphPersistenceRepository
from comqutor_alpha.storage.db.schema import COLUMN_MIGRATIONS, agent_outputs, schema_migrations


def _record(run_id: str, claim_id: str, **overrides):
    record = {
        "claim_id": claim_id,
        "agent_output_id": claim_id,
        "source_agent_output_id": "raw-news-1",
        "run_id": run_id,
        "ticker": "NVDA",
        "agent": "news_agent",
        "claim": "NVDA revenue growth accelerated sharply.",
        "evidence": "NVDA revenue growth accelerated sharply.",
        "entities": ["NVDA"],
        "factors": ["Revenue Growth"],
        "direction": "positive",
        "confidence": 0.8,
        "source_type": "news",
    }
    record.update(overrides)
    return record


class TestFreshDatabaseGetsColumnsViaTableCreation:
    def test_a_brand_new_database_has_all_six_columns_from_table_create(self):
        engine = build_engine("sqlite:///:memory:")
        apply_migrations(engine)
        columns = {col["name"] for col in sa.inspect(engine).get_columns("agent_outputs")}
        assert {
            "source_link_status",
            "linked_source_id",
            "source_link_method",
            "content_support_status",
            "content_support_method",
            "content_support_review",
        }.issubset(columns)


class TestExistingDatabaseGetsColumnsViaAlterTable:
    def _build_pre_migration_database(self):
        """Simulates a database that already ran migration 0004 (the
        ORIGINAL agent_outputs table, before this round's 6 new columns
        existed) -- the real regression scenario this migration exists
        for. Built from a hand-written CREATE TABLE using only the
        pre-existing column set, deliberately NOT importing today's
        ``agent_outputs`` Table object (which already carries the new
        columns) so this test cannot accidentally cheat."""
        engine = build_engine("sqlite:///:memory:")
        schema_migrations.create(engine, checkfirst=True)
        with engine.begin() as conn:
            conn.execute(
                sa.text(
                    """
                    CREATE TABLE agent_outputs (
                        id VARCHAR(64) PRIMARY KEY,
                        run_id VARCHAR(80) NOT NULL,
                        claim_id VARCHAR(300) NOT NULL,
                        source_agent_output_id VARCHAR(300) NOT NULL,
                        ticker VARCHAR(16) NOT NULL,
                        agent VARCHAR(100) NOT NULL,
                        claim TEXT NOT NULL,
                        evidence TEXT NOT NULL,
                        entities JSON NOT NULL,
                        factors JSON NOT NULL,
                        direction VARCHAR(16) NOT NULL,
                        confidence FLOAT NOT NULL,
                        source_type VARCHAR(64) NOT NULL,
                        source_refs JSON NOT NULL,
                        agent_output_id VARCHAR(300),
                        timestamp VARCHAR(40),
                        output_type VARCHAR(64),
                        claim_index INTEGER NOT NULL DEFAULT 0,
                        record_index INTEGER NOT NULL,
                        source_section VARCHAR(200),
                        assertion_status VARCHAR(24),
                        semantic_polarity VARCHAR(24),
                        extraction_method VARCHAR(64),
                        created_at DATETIME NOT NULL
                    )
                    """
                )
            )
            conn.execute(
                sa.insert(schema_migrations).values(version="0004_create_agent_outputs")
            )
        return engine

    def test_pre_migration_database_is_missing_the_new_columns(self):
        engine = self._build_pre_migration_database()
        columns = {col["name"] for col in sa.inspect(engine).get_columns("agent_outputs")}
        assert "source_link_status" not in columns
        assert "content_support_review" not in columns

    def test_apply_column_migrations_adds_exactly_the_missing_columns(self):
        engine = self._build_pre_migration_database()
        applied = apply_column_migrations(engine)
        assert applied == [v for v, _t, _c in COLUMN_MIGRATIONS]

        columns = {col["name"] for col in sa.inspect(engine).get_columns("agent_outputs")}
        assert {
            "source_link_status",
            "linked_source_id",
            "source_link_method",
            "content_support_status",
            "content_support_method",
            "content_support_review",
        }.issubset(columns)

    def test_apply_column_migrations_is_idempotent_safe_to_run_twice(self):
        engine = self._build_pre_migration_database()
        first = apply_column_migrations(engine)
        second = apply_column_migrations(engine)
        assert first == [v for v, _t, _c in COLUMN_MIGRATIONS]
        assert second == []  # already applied -- never re-attempted, never an error

    def test_existing_rows_survive_the_migration_untouched(self):
        engine = self._build_pre_migration_database()
        with engine.begin() as conn:
            conn.execute(
                sa.text(
                    """
                    INSERT INTO agent_outputs
                    (id, run_id, claim_id, source_agent_output_id, ticker, agent, claim, evidence,
                     entities, factors, direction, confidence, source_type, source_refs,
                     claim_index, record_index, created_at)
                    VALUES
                    ('row1', 'run1', 'c1', 'raw1', 'NVDA', 'news_agent', 'Old claim.', 'Old claim.',
                     '[]', '[]', 'positive', 0.7, 'news', '[]', 0, 0, '2026-01-01 00:00:00')
                    """
                )
            )
        apply_column_migrations(engine)
        with engine.connect() as conn:
            row = conn.execute(sa.text("SELECT claim, source_link_status FROM agent_outputs WHERE id = 'row1'")).one()
        assert row[0] == "Old claim."
        assert row[1] is None  # NULL, never fabricated as a real status

    def test_apply_migrations_top_level_entrypoint_also_runs_column_migrations(self):
        # The real production entrypoint (apply_migrations, not the lower-
        # level apply_column_migrations) must cover this too -- this is
        # what every real caller (including the Postgres integration test
        # fixture) actually invokes.
        engine = self._build_pre_migration_database()
        apply_migrations(engine)
        columns = {col["name"] for col in sa.inspect(engine).get_columns("agent_outputs")}
        assert "content_support_review" in columns


class TestReadWriteRoundTripThroughTheRealRepository:
    def _repo(self):
        engine = build_engine("sqlite:///:memory:")
        apply_migrations(engine)
        return engine, GraphPersistenceRepository(engine)

    def test_new_run_writes_and_reads_back_all_six_fields(self):
        _engine, repo = self._repo()
        record = _record(
            "run1", "c1",
            source_link_status="VALID",
            linked_source_id="src_abc123",
            source_link_method="AGENT_CITED",
            content_support_status="PENDING_REVIEW",
            content_support_method="AGENT_CITED_UNVERIFIED_SUPPORT",
            content_support_review={
                "schema_version": "content_support_review.v1",
                "status": "PENDING_REVIEW",
                "method": "AGENT_CITED_UNVERIFIED_SUPPORT",
                "reviewer": None,
                "rationale": None,
                "reviewed_at": None,
            },
        )
        repo.persist_agent_outputs(run_id="run1", ticker="NVDA", structured_payload={
            "run_id": "run1", "ticker": "NVDA", "records": [record],
        })
        rows = repo.list_agent_outputs("run1")
        assert len(rows) == 1
        row = rows[0]
        assert row["source_link_status"] == "VALID"
        assert row["linked_source_id"] == "src_abc123"
        assert row["source_link_method"] == "AGENT_CITED"
        assert row["content_support_status"] == "PENDING_REVIEW"
        assert row["content_support_review"]["method"] == "AGENT_CITED_UNVERIFIED_SUPPORT"

    def test_old_style_record_with_no_source_linking_fields_writes_and_reads_as_null(self):
        _engine, repo = self._repo()
        record = _record("run2", "c1")  # no new fields at all
        repo.persist_agent_outputs(run_id="run2", ticker="NVDA", structured_payload={
            "run_id": "run2", "ticker": "NVDA", "records": [record],
        })
        rows = repo.list_agent_outputs("run2")
        row = rows[0]
        # Never fabricated -- simply absent from the public projection,
        # exactly like every other optional field with no value.
        assert "source_link_status" not in row
        assert "content_support_review" not in row

    def test_api_reads_the_same_db_persisted_fields_get_agent_outputs_response(self):
        from comqutor_alpha.api.agent_output_reader import get_agent_outputs_response

        engine, repo = self._repo()
        record = _record(
            "run3", "c1",
            source_link_status="VALID",
            linked_source_id="src_abc123",
            source_link_method="CONTENT_MATCH_CANDIDATE",
            content_support_status="PENDING_REVIEW",
            content_support_method="UNVERIFIED_OFFLINE_CONTENT_MATCH",
        )
        repo.persist_agent_outputs(run_id="run3", ticker="NVDA", structured_payload={
            "run_id": "run3", "ticker": "NVDA", "records": [record],
        })
        response = get_agent_outputs_response("run3", output_root="outputs/runs", graph_repository=repo)
        assert response["status"] == "ok"
        api_record = response["structured_agent_outputs"][0]
        assert api_record["source_link_status"] == "VALID"
        assert api_record["source_link_method"] == "CONTENT_MATCH_CANDIDATE"
