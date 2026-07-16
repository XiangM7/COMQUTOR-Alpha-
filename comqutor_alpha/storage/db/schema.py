"""Explicit SQLAlchemy Core table definitions for Week 3/4 persistence.

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


alpha_activations = sa.Table(
    "alpha_activations",
    metadata,
    sa.Column("id", sa.Integer, primary_key=True, autoincrement=True),
    sa.Column("run_id", sa.String(80), nullable=False),
    sa.Column("ticker", sa.String(16), nullable=False),
    sa.Column("alpha_id", sa.String(16), nullable=False),
    sa.Column("alpha_name", sa.String(200), nullable=False),
    sa.Column("activation_score", sa.Float, nullable=False),
    sa.Column("status", sa.String(24), nullable=False),
    sa.Column("direction", sa.String(24), nullable=False),
    sa.Column("formula_version", sa.String(64), nullable=False),
    sa.Column("activation_rank", sa.Integer, nullable=False),
    sa.Column("activation_json", _json_type(), nullable=False),
    sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
    sa.Column(
        "updated_at",
        sa.DateTime(timezone=True),
        server_default=sa.func.now(),
        onupdate=sa.func.now(),
        nullable=False,
    ),
    sa.UniqueConstraint("run_id", "alpha_id", name="uq_alpha_activations_run_alpha"),
    sa.Index("ix_alpha_activations_run_id", "run_id"),
    sa.Index("ix_alpha_activations_ticker", "ticker"),
)


alpha_conflicts = sa.Table(
    "alpha_conflicts",
    metadata,
    sa.Column("id", sa.Integer, primary_key=True, autoincrement=True),
    sa.Column("run_id", sa.String(80), nullable=False),
    sa.Column("ticker", sa.String(16), nullable=False),
    sa.Column("alpha_a", sa.String(16), nullable=False),
    sa.Column("alpha_b", sa.String(16), nullable=False),
    sa.Column("outcome", sa.String(16), nullable=False),
    sa.Column("bull_alpha_id", sa.String(16), nullable=True),
    sa.Column("bear_alpha_id", sa.String(16), nullable=True),
    sa.Column("conflict_score", sa.Float, nullable=True),
    sa.Column("conflict_level", sa.String(24), nullable=True),
    sa.Column("contradiction_weight", sa.Float, nullable=True),
    sa.Column("evidence_strength", sa.Float, nullable=True),
    sa.Column("minimum_activation", sa.Float, nullable=True),
    sa.Column("is_main_conflict", sa.Boolean, nullable=False, server_default=sa.false()),
    sa.Column("conflict_rank", sa.Integer, nullable=True),
    sa.Column("reason_codes", _json_type(), nullable=False),
    sa.Column("evidence_audit", _json_type(), nullable=False),
    sa.Column("candidate_json", _json_type(), nullable=False),
    sa.Column("conflict_json", _json_type(), nullable=True),
    sa.Column("schema_version", sa.String(64), nullable=False),
    sa.Column("formula_version", sa.String(64), nullable=False),
    sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
    sa.Column(
        "updated_at",
        sa.DateTime(timezone=True),
        server_default=sa.func.now(),
        onupdate=sa.func.now(),
        nullable=False,
    ),
    sa.UniqueConstraint("run_id", "alpha_a", "alpha_b", name="uq_alpha_conflicts_run_pair"),
    sa.Index("ix_alpha_conflicts_run_id", "run_id"),
    sa.Index("ix_alpha_conflicts_ticker", "ticker"),
    sa.Index("ix_alpha_conflicts_run_outcome", "run_id", "outcome"),
)


research_runs = sa.Table(
    "research_runs",
    metadata,
    sa.Column("run_id", sa.String(80), primary_key=True),
    # SHA-256 hex of the canonical request identity (see
    # research_lifecycle.build_research_request_fingerprint). Many historical
    # rows may share the same fingerprint -- every completed/partial/failed
    # attempt of "the same logical request" keeps its own row.
    sa.Column("request_fingerprint", sa.String(64), nullable=False),
    # Mirrors request_fingerprint while status is queued/running, NULL once
    # terminal. UNIQUE (not per-value -- SQLite/PostgreSQL both allow
    # unlimited NULLs under a UNIQUE constraint) so at most one row can ever
    # be "the" active run for a given fingerprint -- this is the concurrency
    # arbitration primitive: a second concurrent claim's INSERT collides on
    # this constraint rather than needing an external lock.
    sa.Column("active_fingerprint", sa.String(64), nullable=True, unique=True),
    sa.Column("ticker", sa.String(16), nullable=False),
    sa.Column("analysis_date", sa.String(32), nullable=True),
    sa.Column("selected_analysts", _json_type(), nullable=False),
    sa.Column("execution_mode", sa.String(16), nullable=False),
    sa.Column("provider_identity", sa.String(120), nullable=False),
    sa.Column("model_identity", sa.String(120), nullable=False),
    sa.Column("pipeline_identity", _json_type(), nullable=False),
    sa.Column("status", sa.String(16), nullable=False),
    sa.Column("stage", sa.String(64), nullable=True),
    sa.Column("error_code", sa.String(64), nullable=True),
    sa.Column("error_message", sa.String(300), nullable=True),
    sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
    sa.Column("started_at", sa.DateTime(timezone=True), nullable=True),
    sa.Column("completed_at", sa.DateTime(timezone=True), nullable=True),
    sa.Column(
        "updated_at",
        sa.DateTime(timezone=True),
        server_default=sa.func.now(),
        onupdate=sa.func.now(),
        nullable=False,
    ),
    sa.Index("ix_research_runs_request_fingerprint", "request_fingerprint"),
    sa.Index("ix_research_runs_status", "status"),
    sa.Index("ix_research_runs_created_at", "created_at"),
    sa.Index("ix_research_runs_ticker", "ticker"),
)


agent_outputs = sa.Table(
    "agent_outputs",
    metadata,
    # Deterministic SHA-256 of (run_id, claim_id). The primary key remains
    # stable across an idempotent replace of the same run.
    sa.Column("id", sa.String(64), primary_key=True),
    sa.Column("run_id", sa.String(80), nullable=False),
    sa.Column("claim_id", sa.String(300), nullable=False),
    sa.Column("source_agent_output_id", sa.String(300), nullable=False),
    sa.Column("ticker", sa.String(16), nullable=False),
    sa.Column("agent", sa.String(100), nullable=False),
    sa.Column("claim", sa.Text, nullable=False),
    sa.Column("evidence", sa.Text, nullable=False),
    sa.Column("entities", _json_type(), nullable=False),
    sa.Column("factors", _json_type(), nullable=False),
    sa.Column("direction", sa.String(16), nullable=False),
    sa.Column("confidence", sa.Float, nullable=False),
    sa.Column("source_type", sa.String(64), nullable=False),
    sa.Column("source_refs", _json_type(), nullable=False),
    sa.Column("agent_output_id", sa.String(300), nullable=True),
    sa.Column("timestamp", sa.String(40), nullable=True),
    sa.Column("output_type", sa.String(64), nullable=True),
    sa.Column("claim_index", sa.Integer, nullable=False, server_default="0"),
    sa.Column("record_index", sa.Integer, nullable=False),
    sa.Column("source_section", sa.String(200), nullable=True),
    sa.Column("assertion_status", sa.String(24), nullable=True),
    sa.Column("semantic_polarity", sa.String(24), nullable=True),
    sa.Column("extraction_method", sa.String(64), nullable=True),
    sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
    sa.UniqueConstraint("run_id", "claim_id", name="uq_agent_outputs_run_claim"),
    sa.CheckConstraint(
        "confidence >= 0.0 AND confidence <= 1.0",
        name="ck_agent_outputs_confidence_range",
    ),
    sa.CheckConstraint(
        "direction IN ('positive', 'negative', 'neutral', 'unknown')",
        name="ck_agent_outputs_direction",
    ),
    sa.Index("ix_agent_outputs_run_id", "run_id"),
    sa.Index("ix_agent_outputs_run_agent", "run_id", "agent"),
)


# Explicit, versioned migration path (see migrations.py for the runner).
# Each entry is (version_id, tables_to_create) applied in order and recorded
# in `schema_migrations` so re-running is a safe no-op.
MIGRATIONS: tuple[tuple[str, tuple[sa.Table, ...]], ...] = (
    ("0001_create_week3_alpha_matches_and_structure_graphs", (alpha_matches, structure_graphs)),
    (
        "0002_create_week4_alpha_activations_and_alpha_conflicts",
        (alpha_activations, alpha_conflicts),
    ),
    ("0003_create_research_runs", (research_runs,)),
    ("0004_create_agent_outputs", (agent_outputs,)),
)
