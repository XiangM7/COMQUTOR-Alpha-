"""Explicit SQLAlchemy Core table definitions for Week 3 persistence.

Hand-written column/type/constraint definitions (no ORM auto-mapping, no
reflection) so the schema is fully auditable from this one file. JSON columns
use :func:`_json_type` so PostgreSQL gets real JSONB while SQLite (the
offline/test fallback backend) gets a portable JSON-over-TEXT column through
the same table definition and the same repository code path.

Column identity note (Week 2 -> Week 3 mapping): the Development Plan's
original ``agent_output_id`` foreign-key field is, in the current hardened
v2 contract, split into two distinct identities that must not be collapsed
back together:

- ``claim_id``: the Week 2 claim-level identity (one row per structured
  claim). This is the new identity introduced in Week 2 v2.
- ``source_agent_output_id``: the identity of the raw TradingAgents output
  the claim was extracted from (what the Development Plan's
  ``agent_output_id`` referred to).

Both are stored as separate, explicit columns below.
"""

from __future__ import annotations

import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import JSONB

metadata = sa.MetaData()


def _json_type() -> sa.types.TypeEngine:
    return sa.JSON().with_variant(JSONB(), "postgresql")


schema_migrations = sa.Table(
    "schema_migrations",
    metadata,
    sa.Column("version", sa.String(200), primary_key=True),
    sa.Column("applied_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
)


alpha_matches = sa.Table(
    "alpha_matches",
    metadata,
    sa.Column("id", sa.Integer, primary_key=True, autoincrement=True),
    sa.Column("run_id", sa.String(80), nullable=False),
    sa.Column("ticker", sa.String(16), nullable=False),
    sa.Column("claim_id", sa.String(300), nullable=False),
    sa.Column("source_agent_output_id", sa.String(300), nullable=True),
    sa.Column("agent", sa.String(100), nullable=True),
    sa.Column("alpha_id", sa.String(16), nullable=True),
    sa.Column("alpha_name", sa.String(200), nullable=True),
    sa.Column("match_score", sa.Float, nullable=False, server_default="0"),
    sa.Column("match_status", sa.String(16), nullable=False),
    sa.Column("direction", sa.String(16), nullable=True),
    sa.Column("assertion_status", sa.String(16), nullable=True),
    sa.Column("semantic_polarity", sa.String(16), nullable=True),
    sa.Column("claim_text", sa.Text, nullable=True),
    sa.Column("evidence", sa.Text, nullable=True),
    sa.Column("reason", sa.Text, nullable=True),
    sa.Column("candidate_scores", _json_type(), nullable=True),
    sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
    sa.UniqueConstraint("run_id", "claim_id", name="uq_alpha_matches_run_claim"),
    sa.Index("ix_alpha_matches_run_id", "run_id"),
)


structure_graphs = sa.Table(
    "structure_graphs",
    metadata,
    sa.Column("id", sa.Integer, primary_key=True, autoincrement=True),
    sa.Column("run_id", sa.String(80), nullable=False, unique=True),
    sa.Column("ticker", sa.String(16), nullable=False),
    sa.Column("graph_json", _json_type(), nullable=False),
    sa.Column("graph_coherence_score", sa.Float, nullable=False),
    sa.Column("schema_version", sa.String(64), nullable=False),
    sa.Column("graph_builder_version", sa.String(64), nullable=False),
    sa.Column("activation_scorer_version", sa.String(64), nullable=False),
    sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
    sa.Column(
        "updated_at",
        sa.DateTime(timezone=True),
        server_default=sa.func.now(),
        onupdate=sa.func.now(),
        nullable=False,
    ),
    sa.Index("ix_structure_graphs_run_id", "run_id"),
)


# Explicit, versioned migration path (see migrations.py for the runner).
# Each entry is (version_id, tables_to_create) applied in order and recorded
# in `schema_migrations` so re-running is a safe no-op.
MIGRATIONS: tuple[tuple[str, tuple[sa.Table, ...]], ...] = (
    ("0001_create_week3_alpha_matches_and_structure_graphs", (alpha_matches, structure_graphs)),
)
