"""Transactional, idempotent repository for Week 3/4 persistence.

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

from collections.abc import Mapping, Sequence
from datetime import UTC, datetime
from typing import Any
from uuid import uuid4

import sqlalchemy as sa
from sqlalchemy.engine import Engine
from sqlalchemy.exc import IntegrityError, SQLAlchemyError

from comqutor_alpha.research_lifecycle import (
    ACTIVE_RESEARCH_RUN_STATUSES,
    TERMINAL_RESEARCH_RUN_STATUSES,
    is_allowed_transition,
)
from comqutor_alpha.storage.db.engine import (
    DatabaseConfigurationError,
    build_engine,
    resolve_database_url,
    sqlite_file_path,
)
from comqutor_alpha.storage.db.migrations import apply_migrations
from comqutor_alpha.storage.db.schema import (
    alpha_activations,
    alpha_conflicts,
    alpha_matches,
    research_runs,
    structure_graphs,
)
from comqutor_alpha.storage.db.week4_persistence import (
    WEEK4_CONFLICT_PAYLOAD_INVALID,
    Week4PersistenceDataError,
    build_week4_rows,
    reconstruct_conflict_result,
)


class _ResearchRunClaimRace(Exception):
    """Internal sentinel: the INSERT in claim_research_run hit either the
    active_fingerprint UNIQUE constraint or a run_id primary-key collision
    from a genuinely concurrent claim. Never surfaced to callers -- handled
    by re-querying in a fresh transaction after this one cleanly rolls
    back."""


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
    """Read/write executor over an assumed-provisioned schema.

    Construction never mutates the database: it does not create tables, does
    not create a ``schema_migrations`` row, and (for a local SQLite file that
    does not exist yet) never even opens a connection that would auto-create
    the file. Schema provisioning is a separate, explicit step -- see
    :meth:`ensure_schema` -- so a read-only caller (the GET graph endpoint)
    can hold a repository instance without ever acquiring DDL-equivalent
    side effects. Only :func:`build_write_repository_from_env` (the
    POST/write pipeline's construction path) calls it.
    """

    def __init__(self, engine: Engine, *, database_url: str | None = None) -> None:
        self._engine = engine
        # Guards get_graph/get_alpha_matches against SQLite's default
        # behavior of silently creating an empty file on first connection:
        # if this is a local file DSN and the file does not exist, there is
        # provably nothing to read yet, so reads short-circuit before ever
        # calling .connect(). None for Postgres/in-memory SQLite, neither of
        # which has this footgun.
        self._missing_sqlite_guard = sqlite_file_path(database_url) if database_url else None

    def ensure_schema(self) -> list[str]:
        """Apply any pending migrations. Write-path only -- never called from
        a read-only GET request."""
        try:
            return apply_migrations(self._engine)
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

    def _require_supported_dialect(self) -> None:
        if self.dialect_name not in {"postgresql", "sqlite"}:
            raise GraphPersistenceError("UNSUPPORTED_DATABASE_DIALECT")

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
        if self._missing_sqlite_guard is not None and not self._missing_sqlite_guard.exists():
            return None
        try:
            with self._engine.connect() as conn:
                row = conn.execute(
                    sa.select(structure_graphs).where(structure_graphs.c.run_id == run_id)
                ).mappings().first()
        except SQLAlchemyError as exc:
            raise GraphPersistenceError("DB_READ_FAILED") from exc
        return dict(row) if row is not None else None

    def get_alpha_matches(self, run_id: str) -> list[dict[str, Any]]:
        if self._missing_sqlite_guard is not None and not self._missing_sqlite_guard.exists():
            return []
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

    def persist_week4_results(
        self,
        *,
        run_id: str,
        ticker: str,
        activation_payload: Mapping[str, Any],
        conflict_payload: Mapping[str, Any],
    ) -> None:
        """Atomically replace one run's activation and conflict rows."""
        self._require_supported_dialect()
        try:
            activation_rows, conflict_rows = build_week4_rows(
                run_id=run_id,
                ticker=ticker,
                activation_payload=activation_payload,
                conflict_payload=conflict_payload,
            )
        except Week4PersistenceDataError as exc:
            raise GraphPersistenceError(exc.reason_code) from exc

        try:
            with self._engine.begin() as conn:
                conn.execute(
                    sa.delete(alpha_activations).where(alpha_activations.c.run_id == run_id)
                )
                conn.execute(sa.delete(alpha_conflicts).where(alpha_conflicts.c.run_id == run_id))
                if activation_rows:
                    conn.execute(sa.insert(alpha_activations), activation_rows)
                if conflict_rows:
                    conn.execute(sa.insert(alpha_conflicts), conflict_rows)
        except SQLAlchemyError as exc:
            raise GraphPersistenceError("DB_WRITE_FAILED") from exc

    def get_alpha_activations(self, run_id: str) -> list[dict[str, Any]]:
        if self._missing_sqlite_guard is not None and not self._missing_sqlite_guard.exists():
            return []
        self._require_supported_dialect()
        try:
            with self._engine.connect() as conn:
                rows = conn.execute(
                    sa.select(alpha_activations)
                    .where(alpha_activations.c.run_id == run_id)
                    .order_by(alpha_activations.c.activation_rank, alpha_activations.c.alpha_id)
                ).mappings().all()
        except SQLAlchemyError as exc:
            raise GraphPersistenceError("DB_READ_FAILED") from exc
        return [dict(row) for row in rows]

    def get_alpha_conflicts(
        self,
        run_id: str,
        *,
        outcome: str | None = None,
    ) -> list[dict[str, Any]]:
        if outcome is not None and outcome not in {"admitted", "suppressed", "rejected"}:
            raise GraphPersistenceError(WEEK4_CONFLICT_PAYLOAD_INVALID)
        if self._missing_sqlite_guard is not None and not self._missing_sqlite_guard.exists():
            return []
        self._require_supported_dialect()
        statement = sa.select(alpha_conflicts).where(alpha_conflicts.c.run_id == run_id)
        if outcome is not None:
            statement = statement.where(alpha_conflicts.c.outcome == outcome)
        statement = statement.order_by(alpha_conflicts.c.alpha_a, alpha_conflicts.c.alpha_b)
        try:
            with self._engine.connect() as conn:
                rows = conn.execute(statement).mappings().all()
        except SQLAlchemyError as exc:
            raise GraphPersistenceError("DB_READ_FAILED") from exc
        return [dict(row) for row in rows]

    def get_week4_conflict_result(self, run_id: str) -> dict[str, Any] | None:
        rows = self.get_alpha_conflicts(run_id)
        try:
            return reconstruct_conflict_result(run_id, rows)
        except Week4PersistenceDataError as exc:
            raise GraphPersistenceError(exc.reason_code) from exc

    # -----------------------------------------------------------------
    # W5.1A: research_runs lifecycle / fingerprint bookkeeping.
    # -----------------------------------------------------------------

    def _active_fingerprint_statement(self, request_fingerprint: str):
        return sa.select(research_runs).where(research_runs.c.active_fingerprint == request_fingerprint)

    def _latest_completed_statement(self, request_fingerprint: str):
        return (
            sa.select(research_runs)
            .where(research_runs.c.request_fingerprint == request_fingerprint)
            .where(research_runs.c.status == "completed")
            .order_by(research_runs.c.created_at.desc(), research_runs.c.run_id.desc())
            .limit(1)
        )

    @staticmethod
    def _existing_run_disposition(existing: Mapping[str, Any], request_fingerprint: str) -> tuple[str, dict[str, Any]]:
        """Given a research_runs row already found by explicit run_id,
        decide the disposition for *this* request. Raises
        ``GraphPersistenceError("RUN_ID_CONFLICT")`` if the row belongs to a
        genuinely different logical request."""
        if existing["request_fingerprint"] != request_fingerprint:
            raise GraphPersistenceError("RUN_ID_CONFLICT")
        if existing["status"] in ACTIVE_RESEARCH_RUN_STATUSES:
            return "reused_in_flight", dict(existing)
        # Any terminal status (completed/partial/failed): never revived,
        # never re-executed -- reported as-is via the same disposition value
        # used for fingerprint-based completed-cache reuse. The caller
        # (research_lifecycle.submit_research_request) reports the row's
        # real status through ``run_status`` regardless of this value.
        return "reused_completed", dict(existing)

    def claim_research_run(
        self,
        *,
        run_id: str | None,
        request_fingerprint: str,
        ticker: str,
        analysis_date: str | None,
        selected_analysts: Sequence[str],
        execution_mode: str,
        provider_identity: str,
        model_identity: str,
        pipeline_identity: Mapping[str, Any],
        force_refresh: bool = False,
    ) -> dict[str, Any]:
        """Atomically decide the disposition of one research request and,
        when nothing existing can be reused, claim a fresh ``queued`` row.

        Returns ``{"run_id": ..., "disposition": ..., "record": {...}}``.
        ``disposition`` is one of ``created``/``force_refreshed``/
        ``reused_completed``/``reused_in_flight``. Concurrent callers
        claiming the identical ``request_fingerprint`` are arbitrated by the
        ``active_fingerprint`` UNIQUE constraint -- exactly one of them ever
        gets ``created``/``force_refreshed``; the rest observe
        ``reused_in_flight``, never an internal error.
        """
        self._require_supported_dialect()
        try:
            with self._engine.begin() as conn:
                if run_id is not None:
                    existing = conn.execute(
                        sa.select(research_runs).where(research_runs.c.run_id == run_id)
                    ).mappings().first()
                    if existing is not None:
                        if force_refresh and existing["request_fingerprint"] == request_fingerprint:
                            raise GraphPersistenceError("INVALID_FORCE_REFRESH")
                        disposition, record = self._existing_run_disposition(existing, request_fingerprint)
                        return {"run_id": record["run_id"], "disposition": disposition, "record": record}

                active_row = conn.execute(self._active_fingerprint_statement(request_fingerprint)).mappings().first()
                if active_row is not None:
                    return {"run_id": active_row["run_id"], "disposition": "reused_in_flight", "record": dict(active_row)}

                if not force_refresh:
                    completed_row = conn.execute(self._latest_completed_statement(request_fingerprint)).mappings().first()
                    if completed_row is not None:
                        return {
                            "run_id": completed_row["run_id"],
                            "disposition": "reused_completed",
                            "record": dict(completed_row),
                        }

                new_run_id = run_id or str(uuid4())
                now = datetime.now(UTC)
                values = {
                    "run_id": new_run_id,
                    "request_fingerprint": request_fingerprint,
                    "active_fingerprint": request_fingerprint,
                    "ticker": ticker,
                    "analysis_date": analysis_date,
                    "selected_analysts": list(selected_analysts),
                    "execution_mode": execution_mode,
                    "provider_identity": provider_identity,
                    "model_identity": model_identity,
                    "pipeline_identity": dict(pipeline_identity),
                    "status": "queued",
                    "stage": "accepted",
                    "error_code": None,
                    "error_message": None,
                    "created_at": now,
                    "updated_at": now,
                }
                try:
                    conn.execute(sa.insert(research_runs).values(**values))
                except IntegrityError as exc:
                    raise _ResearchRunClaimRace() from exc
                record = dict(values)
                record["started_at"] = None
                record["completed_at"] = None
                return {
                    "run_id": new_run_id,
                    "disposition": "force_refreshed" if force_refresh else "created",
                    "record": record,
                }
        except _ResearchRunClaimRace:
            pass
        except SQLAlchemyError as exc:
            raise GraphPersistenceError("DB_WRITE_FAILED") from exc

        # A concurrent claim won the active_fingerprint (or run_id) race --
        # this transaction was cleanly rolled back above. Re-query in a
        # fresh transaction and report the winner, rather than surfacing a
        # normal concurrency outcome as an internal error.
        try:
            with self._engine.begin() as conn:
                active_row = conn.execute(self._active_fingerprint_statement(request_fingerprint)).mappings().first()
                if active_row is not None:
                    return {"run_id": active_row["run_id"], "disposition": "reused_in_flight", "record": dict(active_row)}
                if run_id is not None:
                    existing = conn.execute(
                        sa.select(research_runs).where(research_runs.c.run_id == run_id)
                    ).mappings().first()
                    if existing is not None:
                        disposition, record = self._existing_run_disposition(existing, request_fingerprint)
                        return {"run_id": record["run_id"], "disposition": disposition, "record": record}
        except SQLAlchemyError as exc:
            raise GraphPersistenceError("DB_WRITE_FAILED") from exc
        raise GraphPersistenceError("RESEARCH_RUN_CLAIM_CONFLICT")

    def mark_research_run_running(self, run_id: str) -> dict[str, Any]:
        """queued -> running. Idempotent no-op if already running. Sets
        ``started_at`` only on the first transition into running."""
        self._require_supported_dialect()
        now = datetime.now(UTC)
        try:
            with self._engine.begin() as conn:
                row = conn.execute(
                    sa.select(research_runs).where(research_runs.c.run_id == run_id)
                ).mappings().first()
                if row is None:
                    raise GraphPersistenceError("RESEARCH_RUN_NOT_FOUND")
                if row["status"] == "running":
                    return dict(row)
                if not is_allowed_transition(row["status"], "running"):
                    raise GraphPersistenceError("RESEARCH_RUN_TRANSITION_INVALID")
                conn.execute(
                    sa.update(research_runs)
                    .where(research_runs.c.run_id == run_id)
                    .values(status="running", stage="research_pipeline", started_at=now, updated_at=now)
                )
                updated = conn.execute(
                    sa.select(research_runs).where(research_runs.c.run_id == run_id)
                ).mappings().first()
                return dict(updated)
        except GraphPersistenceError:
            raise
        except SQLAlchemyError as exc:
            raise GraphPersistenceError("DB_WRITE_FAILED") from exc

    def mark_research_run_terminal(
        self,
        run_id: str,
        *,
        status: str,
        error_code: str | None = None,
        error_message: str | None = None,
    ) -> dict[str, Any]:
        """running/queued -> completed/partial/failed. Always clears
        ``active_fingerprint`` so a terminal run never keeps blocking future
        claims of the same logical request. Never accepts a transition out
        of an already-terminal status -- a retry must claim a new run_id."""
        if status not in TERMINAL_RESEARCH_RUN_STATUSES:
            raise GraphPersistenceError("RESEARCH_RUN_TRANSITION_INVALID")
        self._require_supported_dialect()
        now = datetime.now(UTC)
        try:
            with self._engine.begin() as conn:
                row = conn.execute(
                    sa.select(research_runs).where(research_runs.c.run_id == run_id)
                ).mappings().first()
                if row is None:
                    raise GraphPersistenceError("RESEARCH_RUN_NOT_FOUND")
                if not is_allowed_transition(row["status"], status):
                    raise GraphPersistenceError("RESEARCH_RUN_TRANSITION_INVALID")
                conn.execute(
                    sa.update(research_runs)
                    .where(research_runs.c.run_id == run_id)
                    .values(
                        status=status,
                        stage=status,
                        error_code=error_code,
                        error_message=error_message,
                        active_fingerprint=None,
                        completed_at=now,
                        updated_at=now,
                    )
                )
                updated = conn.execute(
                    sa.select(research_runs).where(research_runs.c.run_id == run_id)
                ).mappings().first()
                return dict(updated)
        except GraphPersistenceError:
            raise
        except SQLAlchemyError as exc:
            raise GraphPersistenceError("DB_WRITE_FAILED") from exc

    def get_research_run_record(self, run_id: str) -> dict[str, Any] | None:
        if self._missing_sqlite_guard is not None and not self._missing_sqlite_guard.exists():
            return None
        self._require_supported_dialect()
        try:
            with self._engine.connect() as conn:
                row = conn.execute(
                    sa.select(research_runs).where(research_runs.c.run_id == run_id)
                ).mappings().first()
        except SQLAlchemyError as exc:
            raise GraphPersistenceError("DB_READ_FAILED") from exc
        return dict(row) if row is not None else None

    def find_active_research_run(self, request_fingerprint: str) -> dict[str, Any] | None:
        if self._missing_sqlite_guard is not None and not self._missing_sqlite_guard.exists():
            return None
        self._require_supported_dialect()
        try:
            with self._engine.connect() as conn:
                row = conn.execute(self._active_fingerprint_statement(request_fingerprint)).mappings().first()
        except SQLAlchemyError as exc:
            raise GraphPersistenceError("DB_READ_FAILED") from exc
        return dict(row) if row is not None else None

    def find_latest_completed_research_run(self, request_fingerprint: str) -> dict[str, Any] | None:
        if self._missing_sqlite_guard is not None and not self._missing_sqlite_guard.exists():
            return None
        self._require_supported_dialect()
        try:
            with self._engine.connect() as conn:
                row = conn.execute(self._latest_completed_statement(request_fingerprint)).mappings().first()
        except SQLAlchemyError as exc:
            raise GraphPersistenceError("DB_READ_FAILED") from exc
        return dict(row) if row is not None else None

    def list_research_run_records(
        self,
        *,
        limit: int = 20,
        cursor: tuple[str, str] | None = None,
        ticker: str | None = None,
        status: str | None = None,
    ) -> list[dict[str, Any]]:
        """Keyset-paginated listing ordered by (created_at DESC, run_id DESC).

        ``cursor``, when given, is ``(created_at_iso_text, run_id)`` of the
        last row of the previous page -- rows are filtered to strictly
        after that position in the same ordering, never an unstable
        offset."""
        if self._missing_sqlite_guard is not None and not self._missing_sqlite_guard.exists():
            return []
        self._require_supported_dialect()
        stmt = sa.select(research_runs)
        if ticker is not None:
            stmt = stmt.where(research_runs.c.ticker == ticker)
        if status is not None:
            stmt = stmt.where(research_runs.c.status == status)
        if cursor is not None:
            cursor_created_at_text, cursor_run_id = cursor
            cursor_created_at = datetime.fromisoformat(cursor_created_at_text)
            stmt = stmt.where(
                sa.or_(
                    research_runs.c.created_at < cursor_created_at,
                    sa.and_(
                        research_runs.c.created_at == cursor_created_at,
                        research_runs.c.run_id < cursor_run_id,
                    ),
                )
            )
        stmt = stmt.order_by(research_runs.c.created_at.desc(), research_runs.c.run_id.desc()).limit(limit)
        try:
            with self._engine.connect() as conn:
                rows = conn.execute(stmt).mappings().all()
        except (SQLAlchemyError, ValueError) as exc:
            raise GraphPersistenceError("DB_READ_FAILED") from exc
        return [dict(row) for row in rows]


def _resolve_engine_and_url(
    output_root: str | None, *, create_if_missing: bool
) -> tuple[Engine, str]:
    try:
        database_url = resolve_database_url(output_root)
    except DatabaseConfigurationError as exc:
        raise GraphPersistenceError(exc.reason_code) from exc
    engine = build_engine(database_url, create_if_missing=create_if_missing)
    return engine, database_url


def build_repository_from_env(output_root: str | None = None) -> GraphPersistenceRepository:
    """Build a read-only repository from server environment configuration.

    Never creates a directory, a local SQLite file, or database schema --
    safe to call from a GET/read request. If the schema has never been
    provisioned (or a local SQLite file has never been written), reads fail
    safely (``DB_READ_FAILED`` / not-found) rather than silently creating it.

    Funnels ``DatabaseConfigurationError`` (e.g. production with no
    ``COMQUTOR_DATABASE_URL``) through the same ``GraphPersistenceError``
    contract as every other persistence-layer failure, so callers only ever
    need to handle one exception type with a stable ``reason_code``.
    """
    engine, database_url = _resolve_engine_and_url(output_root, create_if_missing=False)
    return GraphPersistenceRepository(engine, database_url=database_url)


def build_write_repository_from_env(output_root: str | None = None) -> GraphPersistenceRepository:
    """Build a write-ready repository from server environment configuration.

    Creates the local SQLite directory/file if that is the resolved backend,
    and ensures required schema exists (applying migrations if needed).
    Only the POST/write pipeline may call this -- never a GET/read request.
    """
    engine, database_url = _resolve_engine_and_url(output_root, create_if_missing=True)
    repository = GraphPersistenceRepository(engine, database_url=database_url)
    repository.ensure_schema()
    return repository
