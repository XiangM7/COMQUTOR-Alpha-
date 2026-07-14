"""Transactional, idempotent repository for Week 3 persistence.

Two related writes -- replacing a run's ``alpha_matches`` rows and
upserting its ``structure_graphs`` row -- happen inside a single database
transaction, so a failure partway through never leaves a half-written run:
either both writes land, or neither does and the previously committed state
(if any) is untouched.

Supports exactly two dialects: PostgreSQL (production) and SQLite (offline
default / test fallback), both through the same code path via SQLAlchemy's
dialect-specific ``INSERT ... ON CONFLICT DO UPDATE``. Any other dialect is
rejected explicitly rather than silently mishandled.
"""

from __future__ import annotations

from collections.abc import Mapping
from typing import Any

import sqlalchemy as sa
from sqlalchemy.engine import Engine
from sqlalchemy.exc import SQLAlchemyError

from comqutor_alpha.storage.db.engine import (
    DatabaseConfigurationError,
    build_engine_from_env,
)
from comqutor_alpha.storage.db.migrations import apply_migrations
from comqutor_alpha.storage.db.schema import alpha_matches, structure_graphs


class GraphPersistenceError(Exception):
    """Safe persistence-layer error: carries a stable reason code only.

    Never carries a DSN, file path, or raw driver exception text -- those
    stay in the chained ``__cause__`` for server-side logging, never in the
    message a caller might serialize into an API response.
    """

    def __init__(self, reason_code: str) -> None:
        self.reason_code = reason_code
        super().__init__(reason_code)


def _coerce_optional_str(value: Any) -> str | None:
    if value is None:
        return None
    text = str(value)
    return text if text.strip() else None


class GraphPersistenceRepository:
    def __init__(self, engine: Engine) -> None:
        self._engine = engine
        try:
            apply_migrations(engine)
        except SQLAlchemyError as exc:
            raise GraphPersistenceError("DB_MIGRATION_FAILED") from exc

    @property
    def dialect_name(self) -> str:
        return self._engine.dialect.name

    def _alpha_match_rows(
        self,
        run_id: str,
        ticker: str,
        alpha_matches_payload: Mapping[str, Any],
    ) -> list[dict[str, Any]]:
        records = alpha_matches_payload.get("matches") if isinstance(alpha_matches_payload, Mapping) else None
        rows: list[dict[str, Any]] = []
        if not isinstance(records, list):
            return rows
        seen_claim_ids: set[str] = set()
        for record in records:
            if not isinstance(record, Mapping):
                continue
            claim_id = _coerce_optional_str(record.get("claim_id"))
            if not claim_id or claim_id in seen_claim_ids:
                # No usable claim identity, or a duplicate row for the same
                # claim within one payload: skip rather than violate the
                # (run_id, claim_id) uniqueness contract or silently
                # overwrite with last-write-wins.
                continue
            seen_claim_ids.add(claim_id)
            match_status = str(record.get("match_status") or "no_match")
            rows.append(
                {
                    "run_id": run_id,
                    "ticker": ticker,
                    "claim_id": claim_id,
                    "source_agent_output_id": _coerce_optional_str(record.get("source_agent_output_id")),
                    "agent": _coerce_optional_str(record.get("agent")),
                    "alpha_id": record.get("matched_alpha") if match_status == "matched" else None,
                    "alpha_name": record.get("matched_alpha_name") if match_status == "matched" else None,
                    "match_score": float(record.get("score") or 0.0),
                    "match_status": match_status,
                    "direction": _coerce_optional_str(record.get("direction")),
                    "assertion_status": _coerce_optional_str(record.get("assertion_status")),
                    "semantic_polarity": _coerce_optional_str(record.get("semantic_polarity")),
                    "claim_text": record.get("claim"),
                    "evidence": record.get("evidence"),
                    "reason": record.get("reason"),
                    "candidate_scores": list(record.get("candidate_scores") or []),
                }
            )
        return rows

    def _graph_upsert_statement(self, values: Mapping[str, Any]):
        dialect = self.dialect_name
        if dialect == "postgresql":
            from sqlalchemy.dialects.postgresql import insert as dialect_insert
        elif dialect == "sqlite":
            from sqlalchemy.dialects.sqlite import insert as dialect_insert
        else:
            raise GraphPersistenceError("UNSUPPORTED_DATABASE_DIALECT")

        stmt = dialect_insert(structure_graphs).values(**values)
        update_values = {key: stmt.excluded[key] for key in values}
        update_values["updated_at"] = sa.func.now()
        return stmt.on_conflict_do_update(index_elements=["run_id"], set_=update_values)

    def persist_run(
        self,
        *,
        run_id: str,
        ticker: str,
        alpha_matches_payload: Mapping[str, Any],
        graph_payload: Mapping[str, Any],
    ) -> None:
        """Replace this run's alpha_matches rows and upsert its graph row.

        Idempotent: re-persisting the same run_id with the same input
        produces the same end state. Isolated: only rows/graph for this
        run_id are touched. Atomic: both writes share one transaction.
        """
        rows = self._alpha_match_rows(run_id, ticker, alpha_matches_payload)
        graph_coherence = (
            graph_payload.get("graph_coherence") if isinstance(graph_payload, Mapping) else None
        )
        graph_values = {
            "run_id": run_id,
            "ticker": ticker,
            "graph_json": dict(graph_payload),
            "graph_coherence_score": float((graph_coherence or {}).get("score", 0.0)),
            "schema_version": str(graph_payload.get("schema_version")),
            "graph_builder_version": str(graph_payload.get("graph_builder_version")),
            "activation_scorer_version": str(graph_payload.get("activation_scorer_version")),
        }
        try:
            with self._engine.begin() as conn:
                conn.execute(sa.delete(alpha_matches).where(alpha_matches.c.run_id == run_id))
                if rows:
                    conn.execute(sa.insert(alpha_matches), rows)
                conn.execute(self._graph_upsert_statement(graph_values))
        except SQLAlchemyError as exc:
            raise GraphPersistenceError("DB_WRITE_FAILED") from exc

    def get_graph(self, run_id: str) -> dict[str, Any] | None:
        try:
            with self._engine.connect() as conn:
                row = conn.execute(
                    sa.select(structure_graphs).where(structure_graphs.c.run_id == run_id)
                ).mappings().first()
        except SQLAlchemyError as exc:
            raise GraphPersistenceError("DB_READ_FAILED") from exc
        return dict(row) if row is not None else None

    def get_alpha_matches(self, run_id: str) -> list[dict[str, Any]]:
        try:
            with self._engine.connect() as conn:
                rows = conn.execute(
                    sa.select(alpha_matches)
                    .where(alpha_matches.c.run_id == run_id)
                    .order_by(alpha_matches.c.claim_id)
                ).mappings().all()
        except SQLAlchemyError as exc:
            raise GraphPersistenceError("DB_READ_FAILED") from exc
        return [dict(row) for row in rows]


def build_repository_from_env(output_root: str | None = None) -> GraphPersistenceRepository:
    """Build the default repository from server environment configuration.

    Funnels ``DatabaseConfigurationError`` (e.g. production with no
    ``COMQUTOR_DATABASE_URL``) through the same ``GraphPersistenceError``
    contract as every other persistence-layer failure, so callers only ever
    need to handle one exception type with a stable ``reason_code``.
    """
    try:
        engine = build_engine_from_env(output_root)
    except DatabaseConfigurationError as exc:
        raise GraphPersistenceError(exc.reason_code) from exc
    return GraphPersistenceRepository(engine)
