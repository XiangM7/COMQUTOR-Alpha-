"""T1/T2 verification, 2026-09-29 follow-up, item 4: PostgreSQL verification
for THIS round's own new source-linking record structure, using a REAL
isolated test database -- never the fact that migration 0007 merely applies
cleanly (already covered by tests/test_agent_outputs_postgres_integration.py
's own test_source_linking_migration_0007_was_applied, using a synthetic,
hand-built record). This file instead drives a REAL claim produced by this
round's own market-data source chain (market_data_validator.
build_verified_market_snapshot -> source_capture -> save_structured_agent_
outputs, llm_gateway=None, deterministic) through:

  1. Real persistence to an isolated PostgreSQL test database (never the
     production COMQUTOR_DATABASE_URL -- see postgres_context's own
     COMQUTOR_TEST_DATABASE_URL requirement, the same isolated DB every
     other *_postgres_integration.py test in this repo already uses).
  2. A GENUINE reconnect: the engine used to write is disposed, and a BRAND
     NEW engine/repository instance (a fresh connection pool, not merely a
     fresh transaction on the same connection) is built to read back --
     proving the data actually persisted to the database itself, not just
     to an in-process cache.
  3. The real production API entrypoint (get_agent_outputs_response),
     fed the reconnected repository, correctly reconstructs the FULL
     picture -- the 6 DB-backed source-linking columns (source_link_status/
     linked_source_id/source_link_method/content_support_status/
     content_support_method/content_support_review) read from Postgres,
     STITCHED with the file-based source_registry.json's own instrument/
     observation_date/unit/data_snapshot fields -- exactly the same way it
     does for a real production run.
  4. Consistency against the exported structured_agent_outputs.json FILE
     artifact (this repo's own "export" of the raw claim records) --
     proving the Postgres-backed path and the file-based export path never
     silently diverge for the SAME real claim.

Skipped (not failed) when COMQUTOR_TEST_DATABASE_URL is not configured --
the same convention every other postgres_context-based test in this repo
already follows. Zero paid Provider calls, zero new market data fetch, zero
writes to COMQUTOR_DATABASE_URL (the production database) anywhere in this
file.
"""

from __future__ import annotations

import json
import os
import uuid

import pandas as pd
import pytest
import sqlalchemy as sa
from sqlalchemy.exc import SQLAlchemyError

import tradingagents.dataflows.market_data_validator as validator
from comqutor_alpha.api.agent_output_reader import get_agent_outputs_response
from comqutor_alpha.source_provenance import build_source_registry
from comqutor_alpha.storage.db.engine import build_engine
from comqutor_alpha.storage.db.migrations import apply_migrations
from comqutor_alpha.storage.db.repository import GraphPersistenceRepository
from comqutor_alpha.storage.db.schema import agent_outputs
from comqutor_alpha.storage.file_store import save_json_record
from comqutor_alpha.structure_engine.structured_output_adapter import save_structured_agent_outputs
from tradingagents.dataflows.source_capture import source_capture_scope

pytestmark = pytest.mark.integration

TICKER = "NVDA"
ANALYSIS_DATE = "2026-08-10"


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

    context = {"url": url, "run_ids": set()}
    yield context

    with build_engine(url).begin() as conn:
        if context["run_ids"]:
            conn.execute(sa.delete(agent_outputs).where(agent_outputs.c.run_id.in_(context["run_ids"])))


def _sample_ohlcv():
    dates = pd.bdate_range("2026-06-01", ANALYSIS_DATE)
    closes = [400.0 + i * 0.75 for i in range(len(dates))]
    return pd.DataFrame({
        "Date": dates,
        "Open": [c - 1.0 for c in closes],
        "High": [c + 2.0 for c in closes],
        "Low": [c - 2.0 for c in closes],
        "Close": closes,
        "Volume": [30_000_000 + i * 1000 for i in range(len(dates))],
    })


def test_real_market_chain_record_round_trips_through_isolated_postgres_after_a_genuine_reconnect(
    postgres_context, tmp_path, monkeypatch
):
    run_id = f"pg_market_source_{uuid.uuid4().hex}"
    postgres_context["run_ids"].add(run_id)

    # 1. Build a REAL market-chain claim via the real production entrypoint
    # (never a hand-built/synthetic source record).
    monkeypatch.setattr(validator, "load_ohlcv", lambda s, d: _sample_ohlcv())
    with source_capture_scope() as sink:
        snapshot_text = validator.build_verified_market_snapshot(TICKER, ANALYSIS_DATE)
    captured = list(sink)
    assert len(captured) == 1

    save_json_record(
        run_id, "metadata.json",
        {"run_id": run_id, "ticker": TICKER, "analysis_date": ANALYSIS_DATE},
        output_root=str(tmp_path),
    )
    agent_outputs_payload = [
        {
            "agent": "market_agent",
            "agent_output_id": f"{run_id}:market_agent:market_report",
            "raw_output": (
                f"{snapshot_text}\n\nNVDA's close moved higher through the verified window, "
                "consistent with sustained buying interest."
            ),
        }
    ]
    save_json_record(
        run_id, "raw_agent_outputs.json",
        {"schema_version": "raw.v1", "run_id": run_id, "ticker": TICKER, "agent_outputs": agent_outputs_payload},
        output_root=str(tmp_path),
    )
    registry = build_source_registry(
        run_id=run_id, ticker=TICKER, retrieved_at="2026-08-10T00:00:00Z", captured_records=captured
    )
    save_json_record(run_id, "source_registry.json", registry, output_root=str(tmp_path))

    save_structured_agent_outputs(tmp_path / run_id, llm_gateway=None)
    structured_file = json.loads((tmp_path / run_id / "structured_agent_outputs.json").read_text(encoding="utf-8"))
    linked_file_records = [r for r in structured_file["records"] if r.get("source_link_status") == "VALID"]
    assert linked_file_records, "expected the real market snapshot to produce a VALID-linked claim"
    linked_claim_id = linked_file_records[0]["claim_id"]

    # 2. Persist the EXACT SAME structured payload the file holds into a
    # REAL, isolated PostgreSQL test database -- not a synthetic record.
    write_engine = build_engine(postgres_context["url"])
    write_repo = GraphPersistenceRepository(write_engine)
    write_repo.persist_agent_outputs(run_id=run_id, ticker=TICKER, structured_payload=structured_file)
    write_engine.dispose()

    # 3. A GENUINE reconnect: a brand-new engine/repository, never the one
    # used to write.
    read_engine = build_engine(postgres_context["url"])
    read_repo = GraphPersistenceRepository(read_engine)
    db_rows = read_repo.list_agent_outputs(run_id)
    db_row = next(r for r in db_rows if r["claim_id"] == linked_claim_id)
    file_row = next(r for r in structured_file["records"] if r["claim_id"] == linked_claim_id)

    assert db_row["source_link_status"] == file_row["source_link_status"] == "VALID"
    assert db_row["linked_source_id"] == file_row["linked_source_id"]
    assert db_row["content_support_status"] == file_row["content_support_status"] == "PENDING_REVIEW"
    assert db_row["content_support_review"]["status"] == file_row["content_support_review"]["status"]

    # 4. The real production API, fed the RECONNECTED repository, stitches
    # the Postgres-backed claim status with the file-based source_registry
    # .json's own instrument/observation_date/unit/data_snapshot fields --
    # the exact same way a real production run's own API response does.
    response = get_agent_outputs_response(run_id, output_root=str(tmp_path), graph_repository=read_repo)
    assert response["status"] == "ok"
    api_record = next(r for r in response["structured_agent_outputs"] if r["claim_id"] == linked_claim_id)
    assert api_record["source_link_status"] == "VALID"
    assert api_record["linked_source"]["instrument"] == TICKER
    assert api_record["linked_source"]["unit"] == "USD"
    assert api_record["linked_source"]["observation_date"] == ANALYSIS_DATE
    assert api_record["content_support_status"] == "PENDING_REVIEW"
    assert api_record["verified_support_diagnostic"]["category"] == "CONTENT_SUPPORT_PENDING_REVIEW"
    read_engine.dispose()


def test_pre_migration_style_market_row_without_source_linking_fields_still_reads_cleanly(postgres_context):
    """A row written with NONE of the 6 source-linking columns (exactly
    what a pre-T1 market_agent row looked like) must still read back
    cleanly from real Postgres after a reconnect -- never crash, never a
    fabricated status."""
    run_id = f"pg_market_source_premigration_{uuid.uuid4().hex}"
    postgres_context["run_ids"].add(run_id)

    write_engine = build_engine(postgres_context["url"])
    write_repo = GraphPersistenceRepository(write_engine)
    write_repo.persist_agent_outputs(
        run_id=run_id, ticker=TICKER,
        structured_payload={
            "run_id": run_id, "ticker": TICKER,
            "records": [
                {
                    "claim_id": "c1", "source_agent_output_id": "raw-c1", "run_id": run_id, "ticker": TICKER,
                    "agent": "market_agent", "claim": "NVDA closed higher.", "evidence": "NVDA closed higher.",
                    "entities": ["NVDA"], "factors": [], "direction": "positive", "confidence": 0.8,
                    "source_type": "price", "source_refs": ["raw-c1"], "claim_index": 0,
                    "assertion_status": "asserted", "semantic_polarity": "activation",
                }
            ],
        },
    )
    write_engine.dispose()

    read_engine = build_engine(postgres_context["url"])
    read_repo = GraphPersistenceRepository(read_engine)
    row = read_repo.list_agent_outputs(run_id)[0]
    assert "source_link_status" not in row
    assert "content_support_review" not in row
    read_engine.dispose()
