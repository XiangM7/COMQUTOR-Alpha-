"""T1 verified-support eligibility gate -- Part 2 closing acceptance
(2026-09-29): ONE targeted real-PostgreSQL verification of the content-
support review -> re-evaluation path (the same real functions exercised
offline against SQLite in
``tests/test_content_support_reevaluation_export_roundtrip.py``), proving
the gate-filtered official result, the history-protected original row set,
and the new execution's own independent row set all persist and read back
correctly through a REAL PostgreSQL dialect -- never a SQLite result passed
off as PostgreSQL.

Marked ``integration`` so this never runs as part of the default offline
suite (``pytest -m "not integration"``). When run explicitly:

- If ``COMQUTOR_TEST_DATABASE_URL`` is not set at all, this module is
  skipped (there is nothing to verify against).
- If it *is* set, this module never silently skips again: an unusable DSN,
  a missing PostgreSQL driver, or an unreachable database all fail loudly
  (see the shared ``postgres_ctx`` fixture pattern in
  ``test_graph_persistence_postgres_integration.py``, mirrored here).

Every fixture/record this module writes lives under a per-session unique
``run_id`` prefix and is deleted by that prefix in fixture teardown --
this suite never truncates or deletes a full table, so it is safe to run
against a shared integration database that also holds other tests' or
developers' data. Never connects to production (``comqutor_alpha``); only
the isolated ``COMQUTOR_TEST_DATABASE_URL`` (``comqutor_alpha_test``) the
operator configures is used.

To run locally (POSTGRES_PASSWORD must already be set in your local .env):
    docker compose --profile postgres up -d postgres
    COMQUTOR_TEST_DATABASE_URL=postgresql+psycopg://comqutor:<your-local-password>@localhost:5433/comqutor_alpha_test \\
        python -m pytest tests/test_content_support_reevaluation_postgres_integration.py -m integration -q
"""

from __future__ import annotations

import json
import os
import uuid
from urllib.parse import urlsplit

import pytest
import sqlalchemy as sa

from comqutor_alpha.api.agent_output_reader import get_agent_outputs_response
from comqutor_alpha.api.routes_research import (
    _run_week3_graph_pipeline,
    build_research_response,
    submit_content_support_review,
)
from comqutor_alpha.graph_engine.verified_evidence_gate import (
    ACTIVATION_V2_VERIFIED_FORMULA_VERSION,
)
from comqutor_alpha.source_provenance import SOURCE_LINK_VALID
from comqutor_alpha.storage.db.engine import build_engine
from comqutor_alpha.storage.db.migrations import apply_migrations
from comqutor_alpha.storage.db.repository import GraphPersistenceRepository
from comqutor_alpha.storage.db.schema import (
    alpha_activations,
    alpha_conflicts,
    alpha_matches,
    entity_alpha_exposures,
    structure_graphs,
)

pytestmark = pytest.mark.integration

TEST_DATABASE_URL = os.environ.get("COMQUTOR_TEST_DATABASE_URL", "").strip()

_FAIL_NOT_POSTGRES = (
    "COMQUTOR_TEST_DATABASE_URL is set but does not point to a PostgreSQL "
    "database. This suite only verifies real PostgreSQL persistence."
)
_FAIL_UNREACHABLE = (
    "COMQUTOR_TEST_DATABASE_URL is set but the target PostgreSQL database "
    "could not be reached, or the required driver is unavailable."
)
_FAIL_MIGRATION = (
    "COMQUTOR_TEST_DATABASE_URL is set and reachable, but applying "
    "migrations against it failed."
)

_TICKER = "NVDA"
# published_at is REQUIRED here, not optional fixture detail -- see the
# identical fix and justification in
# tests/test_verified_evidence_gate.py's own _source() helper (the same
# 2026-09-29 DISCLOSURE_TIME_UNKNOWN gate; this file shared the same
# systemic staleness, found and fixed together this round).
_SOURCE = {
    "source_id": "s1",
    "fragment_id": "s1:frag-0",
    "content_hash": "sha256:realhash",
    "published_at": "2026-06-25T00:00:00Z",
}
_RUN_TABLES = (alpha_matches, structure_graphs, alpha_activations, alpha_conflicts, entity_alpha_exposures)


@pytest.fixture(scope="module")
def postgres_ctx():
    if not TEST_DATABASE_URL:
        pytest.skip("COMQUTOR_TEST_DATABASE_URL is not set")
    if not urlsplit(TEST_DATABASE_URL).scheme.startswith("postgresql"):
        pytest.fail(_FAIL_NOT_POSTGRES)
    try:
        engine = build_engine(TEST_DATABASE_URL)
        with engine.connect() as conn:
            conn.execute(sa.text("SELECT 1"))
    except ImportError:
        pytest.fail(_FAIL_UNREACHABLE)
    except Exception:
        pytest.fail(_FAIL_UNREACHABLE)
    try:
        apply_migrations(engine)
    except Exception:
        engine.dispose()
        pytest.fail(_FAIL_MIGRATION)

    repo = GraphPersistenceRepository(engine)
    run_ids: set[str] = set()
    yield {"engine": engine, "repo": repo, "run_ids": run_ids}

    if run_ids:
        with engine.begin() as conn:
            for table in _RUN_TABLES:
                conn.execute(sa.delete(table).where(table.c.run_id.in_(run_ids)))
    engine.dispose()


def _match(claim_id, run_id, *, alpha_id="A102"):
    candidate = {
        "alpha_id": alpha_id, "relation": "activation", "matched_keywords": ["demand"],
        "matched_factors": ["Revenue Growth"], "evidence_stance": "supports_alpha",
    }
    claim = f"{_TICKER} datacenter revenue growth is accelerating."
    return {
        "run_id": run_id, "ticker": _TICKER, "agent": "market_agent", "claim_id": claim_id,
        "source_agent_output_id": "market_agent:source", "claim": claim, "evidence": claim,
        "match_status": "matched", "matched_alpha": alpha_id, "score": 1.0,
        "assertion_status": "asserted", "semantic_polarity": "activation",
        "factor_score": 1.0, "keyword_score": 1.0, "eligible_candidates": [candidate],
        "claim_quality": "analytical", "direction": "positive",
    }


def _build_run_dir(tmp_path, run_id):
    run_dir = tmp_path / run_id
    run_dir.mkdir()
    (run_dir / "metadata.json").write_text(
        json.dumps({"run_id": run_id, "ticker": _TICKER, "analysis_date": "2026-06-30"}), encoding="utf-8"
    )
    (run_dir / "alpha_matches.json").write_text(
        json.dumps({"run_id": run_id, "ticker": _TICKER, "matches": [_match("c1", run_id)]}), encoding="utf-8"
    )
    (run_dir / "extracted_structures.json").write_text(
        json.dumps({"run_id": run_id, "ticker": _TICKER, "nodes": [], "edges": []}), encoding="utf-8"
    )
    record = {
        "claim_id": "c1", "run_id": run_id, "ticker": _TICKER, "agent": "market_agent",
        "source_agent_output_id": "market_agent:source",
        "claim": f"{_TICKER} datacenter revenue growth is accelerating.",
        "evidence": f"{_TICKER} datacenter revenue growth is accelerating.",
        "entities": [], "factors": ["Revenue Growth"], "direction": "positive", "confidence": 0.8,
        "content_support_status": "PENDING_REVIEW",
        "source_link_status": SOURCE_LINK_VALID,
        "linked_source_id": _SOURCE["fragment_id"],
    }
    (run_dir / "structured_agent_outputs.json").write_text(
        json.dumps(
            {"schema_version": "structured_agent_outputs.v1", "run_id": run_id, "ticker": _TICKER, "records": [record]}
        ),
        encoding="utf-8",
    )
    (run_dir / "source_registry.json").write_text(
        json.dumps(
            {"schema_version": "source_registry.v1", "run_id": run_id, "ticker": _TICKER, "source_count": 1, "sources": [_SOURCE]}
        ),
        encoding="utf-8",
    )
    return run_dir


def test_reevaluation_official_result_and_history_protection_on_real_postgres(tmp_path, postgres_ctx):
    repo = postgres_ctx["repo"]
    assert repo.dialect_name == "postgresql"  # never SQLite passed off as PostgreSQL

    run_id = f"pgtest-t1-reeval-{uuid.uuid4().hex[:12]}"
    postgres_ctx["run_ids"].add(run_id)
    run_dir = _build_run_dir(tmp_path, run_id)
    _run_week3_graph_pipeline(run_dir, graph_repository=repo)

    # Baseline: the original run's own real Postgres rows before any review.
    original_conflict_before = repo.get_week4_conflict_result(run_id)
    original_graph_before = repo.get_graph(run_id)

    review_result = submit_content_support_review(
        run_id, "c1", status="SUPPORTS", reviewer="analyst_a",
        rationale="the captured excerpt directly states the same revenue figure the claim asserts",
        output_root=tmp_path, graph_repository=repo,
    )
    assert review_result["status"] == "ok"
    assert review_result["reevaluation"]["status"] == "ok"
    execution_id = review_result["reevaluation"]["execution_id"]
    postgres_ctx["run_ids"].add(execution_id)

    # The NEW execution's own real Postgres rows reflect the gate-filtered
    # official result -- read back through the same real, page-facing
    # functions the frontend calls, backed this time by real PostgreSQL.
    execution_research = build_research_response(execution_id, output_root=tmp_path, graph_repository=repo)
    assert execution_research["run_id"] == execution_id
    assert execution_research["structure_graph_status"] == "ready"
    assert execution_research["conflict_status"] == "ready"
    execution_agent_outputs = get_agent_outputs_response(execution_id, output_root=tmp_path, graph_repository=repo)
    execution_record = next(r for r in execution_agent_outputs["structured_agent_outputs"] if r["claim_id"] == "c1")
    assert execution_record["content_support_status"] == "SUPPORTS"

    execution_graph_row = repo.get_graph(execution_id)
    assert execution_graph_row["graph_json"]["evidence_gate_applied"] is True
    assert (
        execution_graph_row["graph_json"]["primary_activation_version"]
        == ACTIVATION_V2_VERIFIED_FORMULA_VERSION
    )
    execution_conflict_row = repo.get_week4_conflict_result(execution_id)
    assert execution_conflict_row is not None
    assert execution_conflict_row["activation_formula_version"] == ACTIVATION_V2_VERIFIED_FORMULA_VERSION

    # History protection, on REAL Postgres rows: the original run's own
    # graph/conflict rows are untouched by the new execution's writes --
    # two independent row sets, never overwritten in place.
    original_conflict_after = repo.get_week4_conflict_result(run_id)
    original_graph_after = repo.get_graph(run_id)
    assert original_conflict_after == original_conflict_before
    assert original_graph_after == original_graph_before
    assert execution_graph_row["run_id"] == execution_id
    assert original_graph_after["run_id"] == run_id
