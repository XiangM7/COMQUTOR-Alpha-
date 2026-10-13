"""alpha_evidence_consumption.v2: the new JSON fields through the production persistence path on an INDEPENDENT PostgreSQL database.

Scope (owner, round 36): only the necessary round-trip checks -- consumption version, raw baseline, effective weight and reasons are
saved by the production Week 3 pipeline, read back from PostgreSQL and equal to what the file store holds; a rollback and a failed
pass leave PostgreSQL consistent. This is not a T4 re-verification.

The database must be the dedicated one (its name contains ``t1_migration``): the shared ``comqutor_alpha_test`` database the other
PostgreSQL tests use is refused. ``COMQUTOR_T1_MIGRATION_TEST_DATABASE_URL`` unset is the only normal skip (the repository's PostgreSQL
convention); any other misconfiguration fails. Failure messages never include the URL. The tests only write rows of the run they copy
(``persist_run`` replaces them), never drop or truncate anything; the working copy of the saved run lives in ``tmp_path``.
"""

from __future__ import annotations

import json
import os

import pytest
import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.engine import make_url
from sqlalchemy.exc import SQLAlchemyError

from comqutor_alpha.graph_engine.evidence_consumption import (
    CONSUMPTION_CONTRACT_V2,
    CONSUMPTION_METADATA_KEY,
    canonical_sha256,
)
from comqutor_alpha.storage.db.engine import build_engine
from comqutor_alpha.storage.db.migrations import apply_migrations
from comqutor_alpha.storage.db.repository import GraphPersistenceRepository
from tests.test_t1_migration_p3_pipeline_persistence import (  # noqa: F401  (the fixtures are used by name)
    RUN_ID,
    SOURCE_RUN,
    _load,
    _run,
    _set_metadata,
    assert_persistence_round_trip,
    run_copy,
    source_hashes,
)

ENV_VAR = "COMQUTOR_T1_MIGRATION_TEST_DATABASE_URL"
DEDICATED_NAME_PART = "t1_migration"

pytestmark = [
    pytest.mark.integration,
    pytest.mark.skipif(not (SOURCE_RUN / "alpha_matches.json").is_file(), reason="the saved NVDA Fresh Run #2 is not present (local run data)"),
]


@pytest.fixture(scope="module")
def pg_engine():
    url = os.environ.get(ENV_VAR, "").strip()
    if not url:
        pytest.skip(f"{ENV_VAR} not configured")
    if not url.startswith(("postgresql://", "postgresql+psycopg://")):
        pytest.fail(f"{ENV_VAR} is not a PostgreSQL DSN")
    if DEDICATED_NAME_PART not in (make_url(url).database or ""):
        pytest.fail(f"{ENV_VAR} does not name the dedicated round-36 database (the shared test database is refused)")
    try:
        engine = build_engine(url)
    except ImportError:
        pytest.fail("PostgreSQL verification was configured but the driver is unavailable")
    try:
        with engine.connect() as conn:
            conn.execute(sa.text("SELECT 1"))
    except SQLAlchemyError:
        engine.dispose()
        pytest.fail("PostgreSQL verification was configured but the database is unreachable")
    apply_migrations(engine)
    yield engine
    engine.dispose()


@pytest.fixture
def pg_repo(pg_engine):
    return GraphPersistenceRepository(pg_engine)


def _count(engine, where: str, **params) -> int:
    with engine.connect() as conn:
        return int(conn.execute(sa.text(f"SELECT count(*) FROM alpha_matches WHERE run_id = :run_id AND {where}"), {"run_id": RUN_ID, **params}).scalar())


def _db_state_hash(repo) -> str:
    rows = [(r["claim_id"], r["match_score"], r["candidate_scores"]) for r in repo.get_alpha_matches(RUN_ID)]
    return canonical_sha256({"rows": rows, "graph": repo.get_graph(RUN_ID)["graph_json"]})


def test_the_columns_are_real_jsonb_in_the_dedicated_database(pg_engine):
    inspector = sa.inspect(pg_engine)
    assert isinstance({c["name"]: c["type"] for c in inspector.get_columns("alpha_matches")}["candidate_scores"], JSONB)
    assert isinstance({c["name"]: c["type"] for c in inspector.get_columns("structure_graphs")}["graph_json"], JSONB)
    assert DEDICATED_NAME_PART in (pg_engine.url.database or "")


def test_the_new_fields_survive_postgresql_unchanged_and_are_queryable_as_jsonb(run_copy, pg_engine, pg_repo):  # noqa: F811
    _set_metadata(run_copy, **{CONSUMPTION_METADATA_KEY: CONSUMPTION_CONTRACT_V2})
    _run(run_copy, pg_repo)
    assert _load(run_copy, "week3_pipeline_status.json")["outcome"] == "success"
    # what PostgreSQL returns equals what the file store holds, block by block (version, raw baseline, effective weight, reasons)
    assert assert_persistence_round_trip(run_copy, pg_repo) == 164
    # and the fields are real JSONB content: a containment query finds exactly the expected rows
    contract = json.dumps([{"consumption": {"contract": CONSUMPTION_CONTRACT_V2}}])
    excluded = json.dumps([{"consumption": {"positive_admission": {"admitted": False, "reason_code": "STANCE_MODEL_NOT_SUPPORTING"}}}])
    fallback = json.dumps([{"consumption": {"relevance": {"weight_authority": "LEXICAL_RULE_FALLBACK", "model_weight": None}}}])
    assert _count(pg_engine, "candidate_scores @> CAST(:frag AS jsonb)", frag=contract) == 164
    assert _count(pg_engine, "candidate_scores @> CAST(:frag AS jsonb)", frag=excluded) == 87
    assert _count(pg_engine, "candidate_scores @> CAST(:frag AS jsonb)", frag=fallback) == 164
    with pg_engine.connect() as conn:
        summary = conn.execute(sa.text("SELECT graph_json -> 'evidence_consumption' FROM structure_graphs WHERE run_id = :r"), {"r": RUN_ID}).scalar()
    assert summary == _load(run_copy, "structure_graph.json")["evidence_consumption"] and summary["contract"] == CONSUMPTION_CONTRACT_V2


def test_a_rollback_leaves_no_consumption_field_in_postgresql(run_copy, pg_engine, pg_repo):  # noqa: F811
    _set_metadata(run_copy, **{CONSUMPTION_METADATA_KEY: CONSUMPTION_CONTRACT_V2})
    _run(run_copy, pg_repo)
    assert _count(pg_engine, "candidate_scores::text LIKE '%\"consumption\"%'") == 164
    _set_metadata(run_copy, **{CONSUMPTION_METADATA_KEY: None})
    _run(run_copy, pg_repo)
    assert _load(run_copy, "week3_pipeline_status.json")["outcome"] == "success"
    assert _count(pg_engine, "candidate_scores::text LIKE '%\"consumption\"%'") == 0
    with pg_engine.connect() as conn:
        has_summary = conn.execute(sa.text("SELECT jsonb_exists(graph_json, 'evidence_consumption') FROM structure_graphs WHERE run_id = :r"), {"r": RUN_ID}).scalar()
    assert has_summary is False
    # the legacy rows equal the legacy payload (no contract marker, the original candidate lists)
    assert assert_legacy_rows_equal_file(run_copy, pg_repo) > 0


def assert_legacy_rows_equal_file(run_dir, repo) -> int:
    payload = _load(run_dir, "alpha_matches.json")
    rows = {r["claim_id"]: r for r in repo.get_alpha_matches(RUN_ID)}
    compared = 0
    for match in payload["matches"]:
        if match["match_status"] != "matched":
            continue
        assert rows[match["claim_id"]]["candidate_scores"] == match["candidate_scores"]
        compared += 1
    return compared


def test_a_failed_pass_leaves_the_persisted_rows_exactly_as_the_last_good_pass_wrote_them(run_copy, pg_repo):  # noqa: F811
    _set_metadata(run_copy, **{CONSUMPTION_METADATA_KEY: CONSUMPTION_CONTRACT_V2})
    _run(run_copy, pg_repo)
    before = _db_state_hash(pg_repo)
    _set_metadata(run_copy, **{CONSUMPTION_METADATA_KEY: "v3"})
    _run(run_copy, pg_repo)
    status = _load(run_copy, "week3_pipeline_status.json")
    assert status["outcome"] == "failed" and status["stage"] == "evidence_consumption:EVIDENCE_CONSUMPTION_ILLEGAL_CONTRACT_VERSION"
    assert _db_state_hash(pg_repo) == before  # nothing was half-written, nothing was silently re-derived
