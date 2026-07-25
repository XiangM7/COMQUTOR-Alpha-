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

import hashlib
import math
from collections.abc import Mapping, Sequence
from datetime import UTC, datetime
from typing import Any
from uuid import uuid4

import sqlalchemy as sa
from sqlalchemy.engine import Engine
from sqlalchemy.exc import IntegrityError, SQLAlchemyError

from comqutor_alpha.graph_engine.graph_schema import (
    GraphSchemaContractError,
    validate_structure_graph_contract,
)
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
    agent_outputs,
    alpha_activations,
    alpha_conflicts,
    alpha_matches,
    research_run_progress,
    research_runs,
    structure_graphs,
)
from comqutor_alpha.storage.db.week4_persistence import (
    WEEK4_CONFLICT_PAYLOAD_INVALID,
    Week4PersistenceDataError,
    build_week4_rows,
    reconstruct_conflict_result,
)
from comqutor_alpha.structure_engine.structure_schema import (
    VALID_ASSERTION_STATUSES,
    VALID_DIRECTIONS,
)
from comqutor_alpha.structure_engine.structured_output_adapter import (
    MAX_CLAIM_CHARS,
    contains_sensitive_text,
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


def _invalid_payload(reason_code: str) -> None:
    raise GraphPersistenceError(reason_code)


def _required_text(value: Any, *, maximum: int, reason_code: str) -> str:
    if not isinstance(value, str) or not value.strip() or len(value) > maximum:
        _invalid_payload(reason_code)
    return value


def _optional_text(value: Any, *, maximum: int, reason_code: str) -> str | None:
    if value is None:
        return None
    if not isinstance(value, str) or len(value) > maximum:
        _invalid_payload(reason_code)
    return value


def _strict_number(
    value: Any,
    *,
    minimum: float,
    maximum: float,
    reason_code: str,
) -> float:
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        _invalid_payload(reason_code)
    number = float(value)
    if not math.isfinite(number) or not minimum <= number <= maximum:
        _invalid_payload(reason_code)
    return number


def _string_list(value: Any, *, reason_code: str, maximum_items: int = 128) -> list[str]:
    if not isinstance(value, list) or len(value) > maximum_items:
        _invalid_payload(reason_code)
    result: list[str] = []
    for item in value:
        if not isinstance(item, str) or len(item) > MAX_CLAIM_CHARS:
            _invalid_payload(reason_code)
        result.append(item)
    return result


def _reject_sensitive_agent_output(value: Any, *, reason_code: str) -> None:
    if isinstance(value, Mapping):
        for child in value.values():
            _reject_sensitive_agent_output(child, reason_code=reason_code)
    elif isinstance(value, (list, tuple)):
        for child in value:
            _reject_sensitive_agent_output(child, reason_code=reason_code)
    elif isinstance(value, str) and contains_sensitive_text(value):
        _invalid_payload(reason_code)


def _stable_agent_output_id(run_id: str, claim_id: str) -> str:
    return hashlib.sha256(f"{run_id}\0{claim_id}".encode()).hexdigest()


_NAMED_SCORE_RANGES = {
    "confidence": (0.0, 1.0),
    "match_score": (0.0, 1.0),
    "activation_score": (0.0, 100.0),
    "conflict_score": (0.0, 100.0),
    "evidence_strength": (0.0, 1.0),
    "exposure_score": (0.0, 1.0),
}


def _validate_persisted_score_fields(value: Any, *, reason_code: str) -> None:
    if isinstance(value, Mapping):
        for key, child in value.items():
            if key in _NAMED_SCORE_RANGES:
                minimum, maximum = _NAMED_SCORE_RANGES[key]
                _strict_number(
                    child,
                    minimum=minimum,
                    maximum=maximum,
                    reason_code=reason_code,
                )
            else:
                _validate_persisted_score_fields(child, reason_code=reason_code)
        return
    if isinstance(value, (list, tuple)):
        for child in value:
            _validate_persisted_score_fields(child, reason_code=reason_code)
        return
    if isinstance(value, float) and not math.isfinite(value):
        _invalid_payload(reason_code)


def _validated_candidate_scores(value: Any, *, reason_code: str) -> list[dict[str, Any]]:
    if value is None:
        return []
    if not isinstance(value, list):
        _invalid_payload(reason_code)
    result: list[dict[str, Any]] = []
    for candidate in value:
        if not isinstance(candidate, Mapping):
            _invalid_payload(reason_code)
        copied = dict(candidate)
        for key in (
            "score",
            "keyword_score",
            "factor_score",
            "direction_score",
            "semantic_score",
        ):
            if key in copied:
                _strict_number(
                    copied[key], minimum=0.0, maximum=1.0, reason_code=reason_code
                )
        _validate_persisted_score_fields(copied, reason_code=reason_code)
        result.append(copied)
    return result


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
        reason = "ALPHA_MATCHES_PAYLOAD_INVALID"
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
            score_value = record.get("score")
            if score_value is None:
                score_value = 0.0
            rows.append(
                {
                    "run_id": run_id,
                    "ticker": ticker,
                    "claim_id": claim_id,
                    "source_agent_output_id": _coerce_optional_str(record.get("source_agent_output_id")),
                    "agent": _coerce_optional_str(record.get("agent")),
                    "alpha_id": record.get("matched_alpha") if match_status == "matched" else None,
                    "alpha_name": record.get("matched_alpha_name") if match_status == "matched" else None,
                    "match_score": _strict_number(
                        score_value, minimum=0.0, maximum=1.0, reason_code=reason
                    ),
                    "match_status": match_status,
                    "direction": _coerce_optional_str(record.get("direction")),
                    "assertion_status": _coerce_optional_str(record.get("assertion_status")),
                    "semantic_polarity": _coerce_optional_str(record.get("semantic_polarity")),
                    "claim_text": record.get("claim"),
                    "evidence": record.get("evidence"),
                    "reason": record.get("reason"),
                    "candidate_scores": _validated_candidate_scores(
                        record.get("candidate_scores"), reason_code=reason
                    ),
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

    @staticmethod
    def _agent_output_rows(
        run_id: str,
        ticker: str,
        structured_payload: Mapping[str, Any],
        *,
        reason_code: str = "AGENT_OUTPUTS_PAYLOAD_INVALID",
    ) -> list[dict[str, Any]]:
        reason = reason_code
        _required_text(run_id, maximum=80, reason_code=reason)
        _required_text(ticker, maximum=16, reason_code=reason)
        if not isinstance(structured_payload, Mapping):
            _invalid_payload(reason)
        if structured_payload.get("run_id") != run_id or structured_payload.get("ticker") != ticker:
            _invalid_payload(reason)
        records = structured_payload.get("records")
        if not isinstance(records, list):
            _invalid_payload(reason)

        rows: list[dict[str, Any]] = []
        seen_claim_ids: set[str] = set()
        now = datetime.now(UTC)
        for record_index, record in enumerate(records):
            if not isinstance(record, Mapping):
                _invalid_payload(reason)
            claim_id = _required_text(record.get("claim_id"), maximum=300, reason_code=reason)
            if claim_id in seen_claim_ids:
                _invalid_payload(reason)
            seen_claim_ids.add(claim_id)
            if record.get("run_id") != run_id or record.get("ticker") != ticker:
                _invalid_payload(reason)

            source_agent_output_id = _required_text(
                record.get("source_agent_output_id"), maximum=300, reason_code=reason
            )
            direction = _required_text(record.get("direction"), maximum=16, reason_code=reason)
            if direction not in VALID_DIRECTIONS:
                _invalid_payload(reason)
            confidence = _strict_number(
                record.get("confidence"), minimum=0.0, maximum=1.0, reason_code=reason
            )
            claim_index = record.get("claim_index", 0)
            if isinstance(claim_index, bool) or not isinstance(claim_index, int) or claim_index < 0:
                _invalid_payload(reason)
            assertion_status = _optional_text(
                record.get("assertion_status"), maximum=24, reason_code=reason
            )
            if assertion_status is not None and assertion_status not in VALID_ASSERTION_STATUSES:
                _invalid_payload(reason)

            row = {
                    "id": _stable_agent_output_id(run_id, claim_id),
                    "run_id": run_id,
                    "claim_id": claim_id,
                    "source_agent_output_id": source_agent_output_id,
                    "ticker": ticker,
                    "agent": _required_text(record.get("agent"), maximum=100, reason_code=reason),
                    "claim": _required_text(
                        record.get("claim"), maximum=MAX_CLAIM_CHARS, reason_code=reason
                    ),
                    "evidence": _required_text(
                        record.get("evidence"), maximum=MAX_CLAIM_CHARS, reason_code=reason
                    ),
                    "entities": _string_list(record.get("entities"), reason_code=reason),
                    "factors": _string_list(record.get("factors"), reason_code=reason),
                    "direction": direction,
                    "confidence": confidence,
                    "source_type": _required_text(
                        record.get("source_type"), maximum=64, reason_code=reason
                    ),
                    "source_refs": _string_list(
                        record.get("source_refs", [source_agent_output_id]), reason_code=reason
                    ),
                    "agent_output_id": _optional_text(
                        record.get("agent_output_id"), maximum=300, reason_code=reason
                    ),
                    "timestamp": _optional_text(
                        record.get("timestamp"), maximum=40, reason_code=reason
                    ),
                    "output_type": _optional_text(
                        record.get("output_type"), maximum=64, reason_code=reason
                    ),
                    "claim_index": claim_index,
                    "record_index": record_index,
                    "source_section": _optional_text(
                        record.get("source_section"), maximum=200, reason_code=reason
                    ),
                    "assertion_status": assertion_status,
                    "semantic_polarity": _optional_text(
                        record.get("semantic_polarity"), maximum=24, reason_code=reason
                    ),
                    "extraction_method": _optional_text(
                        record.get("extraction_method"), maximum=64, reason_code=reason
                    ),
                    "created_at": now,
                }
            _reject_sensitive_agent_output(row, reason_code=reason)
            rows.append(row)
        return rows

    def _agent_output_upsert_statement(self, values: Mapping[str, Any]):
        if self.dialect_name == "postgresql":
            from sqlalchemy.dialects.postgresql import insert as dialect_insert
        elif self.dialect_name == "sqlite":
            from sqlalchemy.dialects.sqlite import insert as dialect_insert
        else:
            raise GraphPersistenceError("UNSUPPORTED_DATABASE_DIALECT")

        stmt = dialect_insert(agent_outputs).values(**values)
        update_values = {
            key: stmt.excluded[key] for key in values if key not in {"id", "created_at"}
        }
        return stmt.on_conflict_do_update(index_elements=["id"], set_=update_values)

    def persist_agent_outputs(
        self,
        *,
        run_id: str,
        ticker: str,
        structured_payload: Mapping[str, Any],
    ) -> None:
        """Transactionally replace one run's public structured claim rows."""
        self._require_supported_dialect()
        rows = self._agent_output_rows(run_id, ticker, structured_payload)
        row_ids = [row["id"] for row in rows]
        try:
            with self._engine.begin() as conn:
                stale = sa.delete(agent_outputs).where(agent_outputs.c.run_id == run_id)
                if row_ids:
                    stale = stale.where(agent_outputs.c.id.not_in(row_ids))
                conn.execute(stale)
                for row in rows:
                    conn.execute(self._agent_output_upsert_statement(row))
        except GraphPersistenceError:
            raise
        except SQLAlchemyError as exc:
            raise GraphPersistenceError("DB_WRITE_FAILED") from exc

    @staticmethod
    def _public_agent_output_row(row: Mapping[str, Any]) -> dict[str, Any]:
        reason = "DB_DATA_CORRUPTED"
        run_id = _required_text(row.get("run_id"), maximum=80, reason_code=reason)
        ticker = _required_text(row.get("ticker"), maximum=16, reason_code=reason)
        payload = {"run_id": run_id, "ticker": ticker, "records": [dict(row)]}
        normalized = GraphPersistenceRepository._agent_output_rows(
            run_id, ticker, payload, reason_code=reason
        )[0]
        public = {
            key: normalized[key]
            for key in (
                "claim_id",
                "source_agent_output_id",
                "run_id",
                "ticker",
                "agent",
                "claim",
                "evidence",
                "entities",
                "factors",
                "direction",
                "confidence",
                "source_type",
                "source_refs",
            )
        }
        for key in (
            "agent_output_id",
            "timestamp",
            "output_type",
            "source_section",
            "assertion_status",
            "semantic_polarity",
            "extraction_method",
        ):
            if normalized[key] is not None:
                public[key] = normalized[key]
        public["claim_index"] = normalized["claim_index"]
        return public

    def list_agent_outputs(self, run_id: str) -> list[dict[str, Any]]:
        if self._missing_sqlite_guard is not None and not self._missing_sqlite_guard.exists():
            return []
        self._require_supported_dialect()
        try:
            with self._engine.connect() as conn:
                rows = conn.execute(
                    sa.select(agent_outputs)
                    .where(agent_outputs.c.run_id == run_id)
                    .order_by(agent_outputs.c.record_index, agent_outputs.c.id)
                ).mappings().all()
            return [self._public_agent_output_row(row) for row in rows]
        except GraphPersistenceError:
            raise
        except SQLAlchemyError as exc:
            raise GraphPersistenceError("DB_READ_FAILED") from exc

    def count_agent_outputs(self, run_id: str) -> int:
        if self._missing_sqlite_guard is not None and not self._missing_sqlite_guard.exists():
            return 0
        self._require_supported_dialect()
        try:
            with self._engine.connect() as conn:
                return int(
                    conn.scalar(
                        sa.select(sa.func.count())
                        .select_from(agent_outputs)
                        .where(agent_outputs.c.run_id == run_id)
                    )
                    or 0
                )
        except SQLAlchemyError as exc:
            raise GraphPersistenceError("DB_READ_FAILED") from exc

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
        graph_score = (graph_coherence or {}).get("score", 0.0)
        graph_values = {
            "run_id": run_id,
            "ticker": ticker,
            "graph_json": dict(graph_payload),
            "graph_coherence_score": _strict_number(
                graph_score,
                minimum=0.0,
                maximum=100.0,
                reason_code="STRUCTURE_GRAPH_PAYLOAD_INVALID",
            ),
            "schema_version": str(graph_payload.get("schema_version")),
            "graph_builder_version": str(graph_payload.get("graph_builder_version")),
            "activation_scorer_version": str(graph_payload.get("activation_scorer_version")),
        }
        _validate_persisted_score_fields(
            graph_values["graph_json"], reason_code="STRUCTURE_GRAPH_PAYLOAD_INVALID"
        )
        try:
            validate_structure_graph_contract(graph_values["graph_json"])
        except GraphSchemaContractError as exc:
            raise GraphPersistenceError(exc.reason_code) from exc
        try:
            with self._engine.begin() as conn:
                conn.execute(sa.delete(alpha_matches).where(alpha_matches.c.run_id == run_id))
                if rows:
                    conn.execute(sa.insert(alpha_matches), rows)
                conn.execute(self._graph_upsert_statement(graph_values))
        except GraphPersistenceError:
            raise
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
        if row is None:
            return None
        result = dict(row)
        graph_json = result.get("graph_json")
        if not isinstance(graph_json, Mapping):
            raise GraphPersistenceError("DB_DATA_CORRUPTED")
        stored_score = _strict_number(
            result.get("graph_coherence_score"),
            minimum=0.0,
            maximum=100.0,
            reason_code="DB_DATA_CORRUPTED",
        )
        graph_coherence = graph_json.get("graph_coherence")
        if not isinstance(graph_coherence, Mapping):
            raise GraphPersistenceError("DB_DATA_CORRUPTED")
        embedded_score = _strict_number(
            graph_coherence.get("score"),
            minimum=0.0,
            maximum=100.0,
            reason_code="DB_DATA_CORRUPTED",
        )
        if stored_score != embedded_score:
            raise GraphPersistenceError("DB_DATA_CORRUPTED")
        _validate_persisted_score_fields(graph_json, reason_code="DB_DATA_CORRUPTED")
        return result

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
        result = [dict(row) for row in rows]
        for row in result:
            _strict_number(
                row.get("match_score"),
                minimum=0.0,
                maximum=1.0,
                reason_code="DB_DATA_CORRUPTED",
            )
            _validated_candidate_scores(
                row.get("candidate_scores"), reason_code="DB_DATA_CORRUPTED"
            )
        return result

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
            result = reconstruct_conflict_result(run_id, rows)
        except Week4PersistenceDataError as exc:
            raise GraphPersistenceError(exc.reason_code) from exc
        if result is None:
            return None
        # Additive: report which activation formula this run's conflicts
        # were computed against, read from the run's own persisted
        # activation rows (v1 for historical runs, v2 for new runs). Never
        # required -- a run with no activation rows simply omits a value.
        try:
            with self._engine.connect() as conn:
                formula_version = conn.scalar(
                    sa.select(alpha_activations.c.formula_version)
                    .where(alpha_activations.c.run_id == run_id)
                    .order_by(alpha_activations.c.alpha_id)
                    .limit(1)
                )
        except SQLAlchemyError:
            formula_version = None
        result["activation_formula_version"] = formula_version
        return result

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

    # Bounded retry count for the race-recovery loop in claim_research_run.
    # Not infinite: a run of genuinely pathological concurrency (far beyond
    # what a LOCAL_SINGLE_INSTANCE_READY deployment ever sees) must still
    # terminate in a stable, safe RESEARCH_RUN_CLAIM_CONFLICT rather than
    # spin forever.
    _MAX_CLAIM_ATTEMPTS = 3

    def _insert_new_run(self, conn: sa.engine.Connection, values: Mapping[str, Any]) -> None:
        """Isolated so tests can inject a one-shot ``IntegrityError`` here to
        deterministically exercise the race-recovery loop without relying on
        real thread timing."""
        conn.execute(sa.insert(research_runs).values(**values))

    def _on_claim_race(self, attempt: int, request_fingerprint: str) -> None:
        """Test seam invoked immediately after a race is detected and the
        losing transaction has cleanly rolled back, before the next
        full-decision retry attempt. No-op in production; tests use it to
        deterministically advance "the winner" (e.g. to completed) inside
        the recovery window."""
        return None

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
        ``reused_in_flight`` (or, if the winner has already reached a
        terminal status by the time a loser recovers, whatever that
        terminal outcome actually is) -- never an internal error.

        Each race re-runs the *entire* decision (explicit run_id -> active
        fingerprint -> completed cache -> insert) from scratch in a fresh
        transaction, bounded by ``_MAX_CLAIM_ATTEMPTS``. A loser is never
        satisfied by a single ad-hoc re-query of just the active-fingerprint
        row -- the winner may have already finished (completed/partial/
        failed) before the loser's recovery runs.
        """
        self._require_supported_dialect()
        for attempt in range(self._MAX_CLAIM_ATTEMPTS):
            try:
                return self._claim_research_run_once(
                    run_id=run_id,
                    request_fingerprint=request_fingerprint,
                    ticker=ticker,
                    analysis_date=analysis_date,
                    selected_analysts=selected_analysts,
                    execution_mode=execution_mode,
                    provider_identity=provider_identity,
                    model_identity=model_identity,
                    pipeline_identity=pipeline_identity,
                    force_refresh=force_refresh,
                )
            except _ResearchRunClaimRace:
                self._on_claim_race(attempt, request_fingerprint)
                continue
            except SQLAlchemyError as exc:
                raise GraphPersistenceError("DB_WRITE_FAILED") from exc
        raise GraphPersistenceError("RESEARCH_RUN_CLAIM_CONFLICT")

    def _claim_research_run_once(
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
        force_refresh: bool,
    ) -> dict[str, Any]:
        """One full claim decision inside one fresh transaction. Raises
        ``_ResearchRunClaimRace`` (transaction already rolled back by the
        surrounding ``engine.begin()`` context) when a concurrent claim wins
        the ``active_fingerprint``/``run_id`` race at INSERT time -- the
        caller (``claim_research_run``) is responsible for retrying this
        from scratch."""
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
                self._insert_new_run(conn, values)
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

    def mark_research_run_failed_if_active(
        self,
        run_id: str,
        *,
        error_code: str,
        error_message: str | None = None,
    ) -> bool:
        """Atomically fail a run only if it is currently queued/running.

        A single conditional ``UPDATE ... WHERE status IN (queued, running)``
        -- never a SELECT-then-overwrite -- so this is safe to call from a
        supervisor racing against the worker process itself finishing
        normally: whichever writes first wins, and the loser's update simply
        matches zero rows (returns ``False``) instead of clobbering an
        already-terminal outcome. Always clears ``active_fingerprint`` when
        it does apply, exactly like :meth:`mark_research_run_terminal`.
        """
        self._require_supported_dialect()
        now = datetime.now(UTC)
        try:
            with self._engine.begin() as conn:
                result = conn.execute(
                    sa.update(research_runs)
                    .where(research_runs.c.run_id == run_id)
                    .where(research_runs.c.status.in_(list(ACTIVE_RESEARCH_RUN_STATUSES)))
                    .values(
                        status="failed",
                        stage="failed",
                        error_code=error_code,
                        error_message=error_message,
                        active_fingerprint=None,
                        completed_at=now,
                        updated_at=now,
                    )
                )
        except SQLAlchemyError as exc:
            raise GraphPersistenceError("DB_WRITE_FAILED") from exc
        return result.rowcount > 0

    def mark_research_run_and_progress_failed_if_active(
        self,
        run_id: str,
        *,
        error_code: str,
        error_message: str | None = None,
    ) -> bool:
        """Atomically fail an active lifecycle row and its progress row.

        The lifecycle update remains conditional on queued/running. A losing
        supervisor race therefore changes neither table, while a winning
        update releases ``active_fingerprint`` and marks progress failed in
        the same transaction without changing its last real percentage.
        """
        reason = "RESEARCH_PROGRESS_INVALID"
        self._require_supported_dialect()
        message = self._validated_progress_message(error_message, reason_code=reason)
        now = datetime.now(UTC)
        try:
            with self._engine.begin() as conn:
                lifecycle_result = conn.execute(
                    sa.update(research_runs)
                    .where(research_runs.c.run_id == run_id)
                    .where(research_runs.c.status.in_(list(ACTIVE_RESEARCH_RUN_STATUSES)))
                    .values(
                        status="failed",
                        stage="failed",
                        error_code=error_code,
                        error_message=error_message,
                        active_fingerprint=None,
                        completed_at=now,
                        updated_at=now,
                    )
                )
                if lifecycle_result.rowcount <= 0:
                    return False

                progress_values: dict[str, Any] = {
                    "current_stage": "failed",
                    "updated_at": now,
                }
                if message is not None:
                    progress_values["progress_message"] = message
                conn.execute(
                    sa.update(research_run_progress)
                    .where(research_run_progress.c.run_id == run_id)
                    .where(
                        research_run_progress.c.current_stage.not_in(
                            ("completed", "completed_partial", "failed")
                        )
                    )
                    .values(**progress_values)
                )
        except SQLAlchemyError as exc:
            raise GraphPersistenceError("DB_WRITE_FAILED") from exc
        return True

    def list_active_research_run_records(self) -> list[dict[str, Any]]:
        """All currently queued/running rows. Local single-instance startup
        reconciliation only -- never paginated, since a healthy local
        instance never accumulates more than a handful of these."""
        if self._missing_sqlite_guard is not None and not self._missing_sqlite_guard.exists():
            return []
        self._require_supported_dialect()
        try:
            with self._engine.connect() as conn:
                rows = conn.execute(
                    sa.select(research_runs).where(
                        research_runs.c.status.in_(list(ACTIVE_RESEARCH_RUN_STATUSES))
                    )
                ).mappings().all()
        except SQLAlchemyError as exc:
            raise GraphPersistenceError("DB_READ_FAILED") from exc
        return [dict(row) for row in rows]

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
        except SQLAlchemyError as exc:
            # Deliberately does NOT also catch ValueError here: a cursor's
            # semantic validity (JSON shape, parseable timestamp, safe
            # run_id) is decode_run_history_cursor's job, called before this
            # method ever runs. A ValueError reaching this far would be a
            # caller bug, not a "storage is unavailable" condition, so it is
            # never mapped into DB_READ_FAILED.
            raise GraphPersistenceError("DB_READ_FAILED") from exc
        return [dict(row) for row in rows]


    # -----------------------------------------------------------------
    # W7: research_run_progress -- real, monotonic run progress telemetry.
    # -----------------------------------------------------------------

    @staticmethod
    def _strict_progress_int(value: Any, *, minimum: int, maximum: int, reason_code: str) -> int:
        """Progress numbers are integers only: bool, float (including NaN/
        Infinity), numeric strings, and out-of-range values are all rejected
        with the same stable reason code -- a bad number must never be
        silently clamped into fake progress."""
        if isinstance(value, bool) or not isinstance(value, int):
            _invalid_payload(reason_code)
        if not (minimum <= value <= maximum):
            _invalid_payload(reason_code)
        return value

    @staticmethod
    def _validated_progress_stage(value: Any, *, reason_code: str) -> str:
        if not isinstance(value, str) or not value.strip() or len(value) > 64:
            _invalid_payload(reason_code)
        return value

    @staticmethod
    def _validated_progress_message(value: Any, *, reason_code: str) -> str | None:
        if value is None:
            return None
        if not isinstance(value, str) or len(value) > 300:
            _invalid_payload(reason_code)
        return value

    def initialize_research_progress(
        self,
        run_id: str,
        *,
        profile_id: str,
        total_units: int,
        current_stage: str = "queued",
        progress_percent: int = 8,
        progress_message: str | None = None,
    ) -> bool:
        """Create this run's progress row if it does not exist yet.

        Idempotent: a second call for the same run_id is a no-op (returns
        ``False``) and never resets progress a worker has already made --
        INSERT ... ON CONFLICT DO NOTHING, not an upsert.
        """
        reason = "RESEARCH_PROGRESS_INVALID"
        self._require_supported_dialect()
        _required_text(run_id, maximum=80, reason_code=reason)
        _required_text(profile_id, maximum=120, reason_code=reason)
        total = self._strict_progress_int(total_units, minimum=1, maximum=10_000, reason_code=reason)
        percent = self._strict_progress_int(progress_percent, minimum=0, maximum=100, reason_code=reason)
        stage = self._validated_progress_stage(current_stage, reason_code=reason)
        message = self._validated_progress_message(progress_message, reason_code=reason)

        if self.dialect_name == "postgresql":
            from sqlalchemy.dialects.postgresql import insert as dialect_insert
        else:
            from sqlalchemy.dialects.sqlite import insert as dialect_insert

        now = datetime.now(UTC)
        stmt = dialect_insert(research_run_progress).values(
            run_id=run_id,
            profile_id=profile_id,
            progress_percent=percent,
            current_stage=stage,
            completed_units=0,
            total_units=total,
            progress_message=message,
            started_at=now,
            updated_at=now,
        ).on_conflict_do_nothing(index_elements=["run_id"])
        if self.dialect_name == "postgresql":
            stmt = stmt.returning(research_run_progress.c.run_id)
        try:
            with self._engine.begin() as conn:
                result = conn.execute(stmt)
                if self.dialect_name == "postgresql":
                    return result.scalar_one_or_none() is not None
        except SQLAlchemyError as exc:
            raise GraphPersistenceError("DB_WRITE_FAILED") from exc
        return result.rowcount > 0

    def update_research_progress(
        self,
        run_id: str,
        *,
        progress_percent: int,
        current_stage: str,
        completed_units: int,
        progress_message: str | None = None,
    ) -> bool:
        """Monotonic, idempotent progress advance.

        A single conditional ``UPDATE ... WHERE progress_percent <= :new AND
        completed_units <= :new`` -- progress can therefore never move
        backwards (72 -> 48 is impossible by construction), and repeating an
        identical update is a harmless re-write of the same values. Returns
        ``False`` (never raises) when the row does not exist or the update
        would regress. ``total_units`` is never changed after initialization.
        """
        reason = "RESEARCH_PROGRESS_INVALID"
        self._require_supported_dialect()
        _required_text(run_id, maximum=80, reason_code=reason)
        percent = self._strict_progress_int(progress_percent, minimum=0, maximum=100, reason_code=reason)
        completed = self._strict_progress_int(completed_units, minimum=0, maximum=10_000, reason_code=reason)
        stage = self._validated_progress_stage(current_stage, reason_code=reason)
        message = self._validated_progress_message(progress_message, reason_code=reason)

        try:
            with self._engine.begin() as conn:
                result = conn.execute(
                    sa.update(research_run_progress)
                    .where(research_run_progress.c.run_id == run_id)
                    .where(
                        research_run_progress.c.current_stage.not_in(
                            ("completed", "completed_partial", "failed")
                        )
                    )
                    .where(research_run_progress.c.progress_percent <= percent)
                    .where(research_run_progress.c.completed_units <= completed)
                    .where(research_run_progress.c.total_units >= completed)
                    .values(
                        progress_percent=percent,
                        current_stage=stage,
                        completed_units=completed,
                        progress_message=message,
                        updated_at=datetime.now(UTC),
                    )
                )
        except SQLAlchemyError as exc:
            raise GraphPersistenceError("DB_WRITE_FAILED") from exc
        return result.rowcount > 0

    def get_research_progress(self, run_id: str) -> dict[str, Any] | None:
        if self._missing_sqlite_guard is not None and not self._missing_sqlite_guard.exists():
            return None
        self._require_supported_dialect()
        try:
            with self._engine.connect() as conn:
                row = conn.execute(
                    sa.select(research_run_progress).where(research_run_progress.c.run_id == run_id)
                ).mappings().first()
        except SQLAlchemyError as exc:
            raise GraphPersistenceError("DB_READ_FAILED") from exc
        return dict(row) if row is not None else None

    def mark_research_progress_completed(self, run_id: str, *, partial: bool = False) -> bool:
        """Terminal success at 100%.

        A fully completed run accounts for every unit. A partial run keeps
        its last real completed-unit count so the UI never presents skipped
        work as successful.

        ``partial=True`` records ``completed_partial`` instead of
        ``completed`` so a degraded run is never presented as a full one.
        Idempotent."""
        self._require_supported_dialect()
        stage = "completed_partial" if partial else "completed"
        message = (
            "Research run completed with partial results."
            if partial
            else "Research run completed."
        )
        try:
            with self._engine.begin() as conn:
                values: dict[str, Any] = {
                    "progress_percent": 100,
                    "current_stage": stage,
                    "progress_message": message,
                    "updated_at": datetime.now(UTC),
                }
                if not partial:
                    values["completed_units"] = research_run_progress.c.total_units
                result = conn.execute(
                    sa.update(research_run_progress)
                    .where(research_run_progress.c.run_id == run_id)
                    .where(
                        research_run_progress.c.current_stage.not_in(
                            ("completed", "completed_partial", "failed")
                        )
                    )
                    .values(**values)
                )
        except SQLAlchemyError as exc:
            raise GraphPersistenceError("DB_WRITE_FAILED") from exc
        return result.rowcount > 0

    def mark_research_progress_failed(
        self, run_id: str, *, progress_message: str | None = None
    ) -> bool:
        """Terminal failure: the stage flips to ``failed`` but the last real
        percentage is preserved -- a failed run must never fake 100%.
        Idempotent."""
        reason = "RESEARCH_PROGRESS_INVALID"
        self._require_supported_dialect()
        message = self._validated_progress_message(progress_message, reason_code=reason)
        values: dict[str, Any] = {
            "current_stage": "failed",
            "updated_at": datetime.now(UTC),
        }
        if message is not None:
            values["progress_message"] = message
        try:
            with self._engine.begin() as conn:
                result = conn.execute(
                    sa.update(research_run_progress)
                    .where(research_run_progress.c.run_id == run_id)
                    .where(
                        research_run_progress.c.current_stage.not_in(
                            ("completed", "completed_partial", "failed")
                        )
                    )
                    .values(**values)
                )
        except SQLAlchemyError as exc:
            raise GraphPersistenceError("DB_WRITE_FAILED") from exc
        return result.rowcount > 0

    def list_real_completed_run_durations(
        self,
        *,
        profile_id: str,
        selected_analysts: Sequence[str],
        limit: int = 50,
    ) -> list[float]:
        """Historical wall-clock durations (seconds) of normally-completed
        real runs matching this exact profile and canonical analyst
        selection -- the only samples the ETA estimate may use. Partial and
        failed runs never qualify; neither does a run missing a valid
        started_at/completed_at pair."""
        if self._missing_sqlite_guard is not None and not self._missing_sqlite_guard.exists():
            return []
        self._require_supported_dialect()
        wanted_analysts = list(selected_analysts)
        stmt = (
            sa.select(
                research_runs.c.selected_analysts,
                research_runs.c.started_at,
                research_runs.c.completed_at,
            )
            .select_from(
                research_runs.join(
                    research_run_progress,
                    research_runs.c.run_id == research_run_progress.c.run_id,
                )
            )
            .where(research_runs.c.status == "completed")
            .where(research_runs.c.execution_mode == "real")
            .where(research_run_progress.c.profile_id == profile_id)
            .where(research_runs.c.started_at.is_not(None))
            .where(research_runs.c.completed_at.is_not(None))
            .order_by(research_runs.c.completed_at.desc())
            .limit(max(1, min(500, int(limit) * 5)))
        )
        try:
            with self._engine.connect() as conn:
                rows = conn.execute(stmt).mappings().all()
        except SQLAlchemyError as exc:
            raise GraphPersistenceError("DB_READ_FAILED") from exc

        durations: list[float] = []
        for row in rows:
            # selected_analysts equality is checked in Python -- JSON-column
            # equality is not portable across SQLite/PostgreSQL.
            if list(row.get("selected_analysts") or []) != wanted_analysts:
                continue
            started_at = row.get("started_at")
            completed_at = row.get("completed_at")
            try:
                duration = (completed_at - started_at).total_seconds()
            except (TypeError, AttributeError):
                continue
            if duration > 0:
                durations.append(float(duration))
            if len(durations) >= limit:
                break
        return durations


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
