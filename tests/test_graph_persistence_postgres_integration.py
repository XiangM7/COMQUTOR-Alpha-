"""PostgreSQL-specific integration tests for the Week 3 persistence repository.

Marked ``integration`` so these never run as part of the default offline
suite (``pytest -m "not integration"``). When run explicitly:

- If ``COMQUTOR_TEST_DATABASE_URL`` is not set at all, every test in this
  module is skipped (there is nothing to verify against).
- If ``COMQUTOR_TEST_DATABASE_URL`` *is* set, this module never silently
  skips again: an unusable DSN, a missing PostgreSQL driver, or an
  unreachable database all fail loudly with a fixed, safe message (no DSN,
  host, credentials, or raw driver exception text), so a misconfigured
  environment is reported as a failure, not mistaken for "not applicable".

All fixtures/records this module writes live under a per-run-session unique
``run_id`` prefix and are deleted by ``run_id`` in fixture teardown -- this
suite never truncates or deletes the full ``alpha_matches`` /
``structure_graphs`` tables, so it is safe to run against a shared
integration database that also holds other tests' or developers' data.

To run locally (POSTGRES_PASSWORD must be set in your local .env first --
the postgres profile refuses to start without it; see .env.example):
    docker compose --profile postgres up -d postgres
    COMQUTOR_TEST_DATABASE_URL=postgresql+psycopg://comqutor:<your-local-password>@localhost:5433/comqutor_alpha \
        python -m pytest tests/test_graph_persistence_postgres_integration.py -m integration -q
"""

from __future__ import annotations

import os
import uuid
from urllib.parse import urlsplit

import pytest
import sqlalchemy as sa

from comqutor_alpha.storage.db.engine import build_engine
from comqutor_alpha.storage.db.migrations import apply_migrations
from comqutor_alpha.storage.db.repository import GraphPersistenceRepository
from comqutor_alpha.storage.db.schema import alpha_matches, structure_graphs

pytestmark = pytest.mark.integration

TEST_DATABASE_URL = os.environ.get("COMQUTOR_TEST_DATABASE_URL", "").strip()

_FAIL_NOT_POSTGRES = (
    "COMQUTOR_TEST_DATABASE_URL is set but does not point to a PostgreSQL "
    "database. This suite only verifies real PostgreSQL persistence."
)
_FAIL_DRIVER_UNAVAILABLE = (
    "COMQUTOR_TEST_DATABASE_URL is set but the PostgreSQL driver required "
    "to connect is not available in this environment."
)
_FAIL_UNREACHABLE = (
    "COMQUTOR_TEST_DATABASE_URL is set but the target PostgreSQL database "
    "could not be reached. Verify local PostgreSQL is running and the "
    "test database is configured correctly."
)
_FAIL_MIGRATION = (
    "COMQUTOR_TEST_DATABASE_URL is set and reachable, but applying Week 3 "
    "migrations against it failed."
)


class _PostgresIntegrationContext:
    """Per-module PostgreSQL handle plus the set of run_ids this module owns.

    Teardown only ever deletes rows for run_ids recorded here -- never a
    full-table delete -- so this suite is safe to run against a database
    that also holds other tests' or developers' data.
    """

    def __init__(self, repo: GraphPersistenceRepository, engine: sa.engine.Engine, run_prefix: str) -> None:
        self.repo = repo
        self.engine = engine
        self.run_prefix = run_prefix
        self.run_ids: set[str] = set()

    def new_run_id(self) -> str:
        run_id = f"{self.run_prefix}-{uuid.uuid4().hex[:12]}"
        self.run_ids.add(run_id)
        return run_id


@pytest.fixture(scope="module")
def postgres_ctx():
    if not TEST_DATABASE_URL:
        pytest.skip("COMQUTOR_TEST_DATABASE_URL is not set")

    if not urlsplit(TEST_DATABASE_URL).scheme.startswith("postgresql"):
        pytest.fail(_FAIL_NOT_POSTGRES)

    try:
        engine = build_engine(TEST_DATABASE_URL)
    except ImportError:
        pytest.fail(_FAIL_DRIVER_UNAVAILABLE)
    except Exception:
        pytest.fail(_FAIL_UNREACHABLE)

    try:
        with engine.connect() as conn:
            conn.execute(sa.text("SELECT 1"))
    except ImportError:
        engine.dispose()
        pytest.fail(_FAIL_DRIVER_UNAVAILABLE)
    except Exception:
        engine.dispose()
        pytest.fail(_FAIL_UNREACHABLE)

    try:
        apply_migrations(engine)
    except Exception:
        engine.dispose()
        pytest.fail(_FAIL_MIGRATION)

    repo = GraphPersistenceRepository(engine)
    run_prefix = f"pgtest-{uuid.uuid4().hex[:12]}"
    ctx = _PostgresIntegrationContext(repo, engine, run_prefix)

    yield ctx

    if ctx.run_ids:
        with engine.begin() as conn:
            conn.execute(sa.delete(alpha_matches).where(alpha_matches.c.run_id.in_(ctx.run_ids)))
            conn.execute(sa.delete(structure_graphs).where(structure_graphs.c.run_id.in_(ctx.run_ids)))
    engine.dispose()


def _alpha_matches_payload(run_id: str, claim_id="c1", alpha_id="A101"):
    return {
        "schema_version": "week2.alpha_matches.v2",
        "run_id": run_id,
        "ticker": "NVDA",
        "matches": [
            {
                "claim_id": claim_id,
                "source_agent_output_id": f"o_{claim_id}",
                "agent": "news_agent",
                "match_status": "matched",
                "matched_alpha": alpha_id,
                "matched_alpha_name": "AI Expansion",
                "score": 0.8,
                "direction": "positive",
                "assertion_status": "asserted",
                "semantic_polarity": "activation",
                "claim": "AI demand is strong.",
                "evidence": "AI demand is strong.",
                "reason": "top eligible alpha",
                "candidate_scores": [{"alpha_id": alpha_id, "score": 0.8}],
            }
        ],
    }


def _graph_payload(run_id: str, ticker="NVDA", score=42.0):
    return {
        "schema_version": "week3.structure_graph.v1",
        "graph_builder_version": "week3.graph_builder.v1",
        "activation_scorer_version": "week3.activation_scorer.v1",
        "run_id": run_id,
        "ticker": ticker,
        "nodes": [{"id": "ai_demand", "label": "AI Demand"}],
        "edges": [],
        "graph_metrics": {},
        "graph_coherence": {"score": score, "valid_edges": 1, "alpha_covered_count": 1},
        "activation": {"formula_version": "week3.activation.mvp_v1", "alphas": []},
        "dominant_alphas": [],
        "provenance": {},
    }


class TestPostgresIntegration:
    def test_dialect_is_really_postgresql(self, postgres_ctx):
        assert postgres_ctx.repo.dialect_name == "postgresql"

    def test_graph_json_column_is_real_jsonb(self, postgres_ctx):
        with postgres_ctx.engine.connect() as conn:
            row = conn.execute(
                sa.text(
                    "SELECT data_type FROM information_schema.columns "
                    "WHERE table_name = 'structure_graphs' AND column_name = 'graph_json'"
                )
            ).first()
        assert row is not None
        assert row[0] == "jsonb"

    def test_persist_and_retrieve_round_trips_on_real_postgres(self, postgres_ctx):
        run_id = postgres_ctx.new_run_id()
        graph_payload = _graph_payload(run_id)

        postgres_ctx.repo.persist_run(
            run_id=run_id,
            ticker="NVDA",
            alpha_matches_payload=_alpha_matches_payload(run_id),
            graph_payload=graph_payload,
        )

        row = postgres_ctx.repo.get_graph(run_id)
        assert row["graph_json"] == graph_payload
        matches = postgres_ctx.repo.get_alpha_matches(run_id)
        assert len(matches) == 1
        assert matches[0]["alpha_id"] == "A101"

    def test_v1_and_v2_structure_graph_round_trip_on_real_postgres(self, postgres_ctx):
        """Structure Graph Schema v1/v2 contract test #8: both a historical
        v1-shaped payload and a new v2-shaped payload (with
        activation_versions/primary_activation_version) persist and read
        back byte-identical on real PostgreSQL."""
        v1_run_id = postgres_ctx.new_run_id()
        v1_payload = _graph_payload(v1_run_id)
        postgres_ctx.repo.persist_run(
            run_id=v1_run_id,
            ticker="NVDA",
            alpha_matches_payload=_alpha_matches_payload(v1_run_id),
            graph_payload=v1_payload,
        )
        v1_row = postgres_ctx.repo.get_graph(v1_run_id)
        assert v1_row["graph_json"]["schema_version"] == "week3.structure_graph.v1"
        assert v1_row["graph_json"] == v1_payload

        v2_run_id = postgres_ctx.new_run_id()
        v2_block = {
            "formula_version": "activation.v2.evidence_local_structure.v1",
            "alphas": [],
        }
        v2_payload = {
            **_graph_payload(v2_run_id),
            "schema_version": "week3.structure_graph.v2",
            "activation": v2_block,
            "activation_versions": {
                "v1": {"formula_version": "week3.activation.mvp_v1", "alphas": []},
                "v2": v2_block,
            },
            "primary_activation_version": v2_block["formula_version"],
        }
        postgres_ctx.repo.persist_run(
            run_id=v2_run_id,
            ticker="NVDA",
            alpha_matches_payload=_alpha_matches_payload(v2_run_id),
            graph_payload=v2_payload,
        )
        v2_row = postgres_ctx.repo.get_graph(v2_run_id)
        assert v2_row["graph_json"]["schema_version"] == "week3.structure_graph.v2"
        assert v2_row["graph_json"] == v2_payload

    def test_idempotent_retry_on_real_postgres(self, postgres_ctx):
        run_id = postgres_ctx.new_run_id()
        payload = _alpha_matches_payload(run_id)
        graph_payload = _graph_payload(run_id)

        postgres_ctx.repo.persist_run(run_id=run_id, ticker="NVDA", alpha_matches_payload=payload, graph_payload=graph_payload)
        postgres_ctx.repo.persist_run(run_id=run_id, ticker="NVDA", alpha_matches_payload=payload, graph_payload=graph_payload)

        assert len(postgres_ctx.repo.get_alpha_matches(run_id)) == 1

    def test_run_isolation_on_real_postgres(self, postgres_ctx):
        run_id_1 = postgres_ctx.new_run_id()
        run_id_2 = postgres_ctx.new_run_id()

        postgres_ctx.repo.persist_run(
            run_id=run_id_1,
            ticker="NVDA",
            alpha_matches_payload=_alpha_matches_payload(run_id_1, "c1", "A101"),
            graph_payload=_graph_payload(run_id_1, "NVDA", 10.0),
        )
        postgres_ctx.repo.persist_run(
            run_id=run_id_2,
            ticker="QQQ",
            alpha_matches_payload=_alpha_matches_payload(run_id_2, "c9", "A001"),
            graph_payload=_graph_payload(run_id_2, "QQQ", 90.0),
        )

        assert postgres_ctx.repo.get_graph(run_id_1)["ticker"] == "NVDA"
        assert postgres_ctx.repo.get_graph(run_id_2)["ticker"] == "QQQ"
        assert [row["claim_id"] for row in postgres_ctx.repo.get_alpha_matches(run_id_1)] == ["c1"]
        assert [row["claim_id"] for row in postgres_ctx.repo.get_alpha_matches(run_id_2)] == ["c9"]
