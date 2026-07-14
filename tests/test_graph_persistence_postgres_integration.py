"""PostgreSQL-specific integration tests for the Week 3 persistence repository.

Marked ``integration`` and skipped automatically unless a real, reachable
PostgreSQL DSN is configured via ``COMQUTOR_TEST_DATABASE_URL``. These never
run as part of the default offline suite (``pytest -m "not integration"``)
and never fake a passing result when PostgreSQL is unavailable.

To run locally:
    docker compose --profile postgres up -d postgres
    COMQUTOR_TEST_DATABASE_URL=postgresql+psycopg://comqutor:comqutor@localhost:5433/comqutor_alpha \
        python -m pytest tests/test_graph_persistence_postgres_integration.py -m integration -q
"""

import os

import pytest
import sqlalchemy as sa

from comqutor_alpha.storage.db.engine import build_engine
from comqutor_alpha.storage.db.repository import GraphPersistenceRepository
from comqutor_alpha.storage.db.schema import alpha_matches, structure_graphs

pytestmark = pytest.mark.integration

TEST_DATABASE_URL = os.environ.get("COMQUTOR_TEST_DATABASE_URL", "").strip()


def _postgres_reachable(url: str) -> bool:
    if not url:
        return False
    try:
        engine = build_engine(url)
        with engine.connect() as conn:
            conn.execute(sa.text("SELECT 1"))
        engine.dispose()
        return True
    except Exception:
        return False


_SKIP_REASON = "COMQUTOR_TEST_DATABASE_URL is not set or PostgreSQL is unreachable"
_REACHABLE = _postgres_reachable(TEST_DATABASE_URL)


def _repo():
    engine = build_engine(TEST_DATABASE_URL)
    repo = GraphPersistenceRepository(engine)
    # Start each test from a clean slate on the shared integration database.
    with engine.begin() as conn:
        conn.execute(sa.delete(alpha_matches))
        conn.execute(sa.delete(structure_graphs))
    return repo


def _alpha_matches_payload(claim_id="c1", alpha_id="A101"):
    return {
        "schema_version": "week2.alpha_matches.v2",
        "run_id": "pg_r1",
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


def _graph_payload(run_id="pg_r1", ticker="NVDA", score=42.0):
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
        "activation": {"alphas": []},
        "dominant_alphas": [],
        "provenance": {},
    }


@pytest.mark.skipif(not _REACHABLE, reason=_SKIP_REASON)
class TestPostgresIntegration:
    def test_dialect_is_really_postgresql(self):
        repo = _repo()
        assert repo.dialect_name == "postgresql"

    def test_graph_json_column_is_real_jsonb(self):
        engine = build_engine(TEST_DATABASE_URL)
        with engine.connect() as conn:
            row = conn.execute(
                sa.text(
                    "SELECT data_type FROM information_schema.columns "
                    "WHERE table_name = 'structure_graphs' AND column_name = 'graph_json'"
                )
            ).first()
        assert row is not None
        assert row[0] == "jsonb"

    def test_persist_and_retrieve_round_trips_on_real_postgres(self):
        repo = _repo()
        graph_payload = _graph_payload()

        repo.persist_run(
            run_id="pg_r1", ticker="NVDA", alpha_matches_payload=_alpha_matches_payload(), graph_payload=graph_payload
        )

        row = repo.get_graph("pg_r1")
        assert row["graph_json"] == graph_payload
        matches = repo.get_alpha_matches("pg_r1")
        assert len(matches) == 1
        assert matches[0]["alpha_id"] == "A101"

    def test_idempotent_retry_on_real_postgres(self):
        repo = _repo()
        payload = _alpha_matches_payload()
        graph_payload = _graph_payload()

        repo.persist_run(run_id="pg_r1", ticker="NVDA", alpha_matches_payload=payload, graph_payload=graph_payload)
        repo.persist_run(run_id="pg_r1", ticker="NVDA", alpha_matches_payload=payload, graph_payload=graph_payload)

        assert len(repo.get_alpha_matches("pg_r1")) == 1

    def test_run_isolation_on_real_postgres(self):
        repo = _repo()
        repo.persist_run(
            run_id="pg_r1",
            ticker="NVDA",
            alpha_matches_payload=_alpha_matches_payload("c1", "A101"),
            graph_payload=_graph_payload("pg_r1", "NVDA", 10.0),
        )
        repo.persist_run(
            run_id="pg_r2",
            ticker="QQQ",
            alpha_matches_payload=_alpha_matches_payload("c9", "A001"),
            graph_payload=_graph_payload("pg_r2", "QQQ", 90.0),
        )

        assert repo.get_graph("pg_r1")["ticker"] == "NVDA"
        assert repo.get_graph("pg_r2")["ticker"] == "QQQ"
        assert [row["claim_id"] for row in repo.get_alpha_matches("pg_r1")] == ["c1"]
        assert [row["claim_id"] for row in repo.get_alpha_matches("pg_r2")] == ["c9"]


def test_reports_unreachable_rather_than_faking_success():
    """Marked ``integration`` like the rest of this module, so the default
    offline suite (``-m "not integration"``) still deselects it -- but a
    direct/explicit run of this file gives a clear reason for the skip
    instead of silently reporting nothing, so 'unverified' is never
    confused with 'passed'."""
    if not TEST_DATABASE_URL:
        pytest.skip("COMQUTOR_TEST_DATABASE_URL not set: PostgreSQL integration unverified")
    if not _REACHABLE:
        pytest.skip("COMQUTOR_TEST_DATABASE_URL set but PostgreSQL is unreachable: integration unverified")
    assert _REACHABLE
