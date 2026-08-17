"""Validation and DB-row projection for Entity Alpha Exposure."""

from __future__ import annotations

import json
import math
from collections.abc import Mapping
from datetime import date
from typing import Any

from comqutor_alpha.exposure_engine import ENTITY_EXPOSURE_ARTIFACT_SCHEMA_VERSION

EXPOSURE_PERSISTENCE_PAYLOAD_INVALID = "EXPOSURE_PERSISTENCE_PAYLOAD_INVALID"


class ExposurePersistenceDataError(Exception):
    def __init__(self, reason_code: str) -> None:
        self.reason_code = reason_code
        super().__init__(reason_code)


def _fail() -> None:
    raise ExposurePersistenceDataError(EXPOSURE_PERSISTENCE_PAYLOAD_INVALID)


def _text(value: Any) -> str:
    if not isinstance(value, str) or not value.strip():
        _fail()
    return value


def _unit(value: Any, *, nullable: bool = False) -> float | None:
    if value is None and nullable:
        return None
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        _fail()
    number = float(value)
    if not math.isfinite(number) or not 0.0 <= number <= 1.0:
        _fail()
    return number


def _count(value: Any) -> int:
    if isinstance(value, bool) or not isinstance(value, int) or value < 0:
        _fail()
    return value


def _boolean(value: Any) -> bool:
    if not isinstance(value, bool):
        _fail()
    return value


def _json_copy(value: Any) -> Any:
    try:
        return json.loads(json.dumps(value, allow_nan=False))
    except (TypeError, ValueError) as exc:
        raise ExposurePersistenceDataError(EXPOSURE_PERSISTENCE_PAYLOAD_INVALID) from exc


def build_entity_exposure_rows(
    *, run_id: str, ticker: str, artifact: Mapping[str, Any]
) -> list[dict[str, Any]]:
    run_id = _text(run_id)
    ticker = _text(ticker)
    if not isinstance(artifact, Mapping):
        _fail()
    if artifact.get("schema_version") != ENTITY_EXPOSURE_ARTIFACT_SCHEMA_VERSION:
        _fail()
    if artifact.get("run_id") != run_id or artifact.get("ticker") != ticker:
        _fail()
    records = artifact.get("records")
    if not isinstance(records, list):
        _fail()

    rows: list[dict[str, Any]] = []
    seen: set[str] = set()
    for record in records:
        if not isinstance(record, Mapping):
            _fail()
        alpha_id = _text(record.get("alpha_id"))
        if record.get("run_id") != run_id or record.get("ticker") != ticker or alpha_id in seen:
            _fail()
        seen.add(alpha_id)
        raw_date = record.get("seed_effective_date")
        try:
            effective_date = date.fromisoformat(raw_date) if isinstance(raw_date, str) else raw_date
        except ValueError as exc:
            raise ExposurePersistenceDataError(EXPOSURE_PERSISTENCE_PAYLOAD_INVALID) from exc
        if effective_date is not None and not isinstance(effective_date, date):
            _fail()
        reason_codes = record.get("reason_codes")
        provenance = record.get("provenance")
        if not isinstance(reason_codes, list) or not all(
            isinstance(item, str) for item in reason_codes
        ):
            _fail()
        if not isinstance(provenance, Mapping):
            _fail()
        # John's B3 gated seed lifecycle (task B3_ENTITY_EXPOSURE_GATED_STATES):
        # owner/approved_by/approved_at/configured_status/effective_status
        # are additive, per-ticker provenance -- stored inside the existing
        # provenance_json blob (never a new column/table; this repo's
        # migration runner only supports CREATE TABLE IF NOT EXISTS, never
        # ALTER TABLE, so an existing DB's entity_alpha_exposures table
        # cannot safely gain new columns). Nested under its own key so it
        # can never collide with the pre-existing provenance fields.
        for optional_text_field in ("owner", "approved_by", "approved_at"):
            value = record.get(optional_text_field)
            if value is not None and not isinstance(value, str):
                _fail()
        for required_status_field in ("configured_status", "effective_status"):
            if not isinstance(record.get(required_status_field), str) or not record.get(
                required_status_field
            ):
                _fail()
        provenance_with_lifecycle = {
            **provenance,
            "b3_lifecycle": {
                "owner": record.get("owner"),
                "approved_by": record.get("approved_by"),
                "approved_at": record.get("approved_at"),
                "configured_status": record.get("configured_status"),
                "effective_status": record.get("effective_status"),
            },
        }
        rows.append(
            {
                "run_id": run_id,
                "ticker": ticker,
                "alpha_id": alpha_id,
                "seed_version": _text(record.get("seed_version")),
                "seed_effective_date": effective_date,
                "seed_approval_status": _text(record.get("seed_approval_status")),
                "historical_mapping": _unit(record.get("historical_mapping"), nullable=True),
                "current_evidence": _unit(record.get("current_evidence"), nullable=True),
                "agent_confidence": _unit(record.get("agent_confidence"), nullable=True),
                "final_exposure": _unit(record.get("final_exposure"), nullable=True),
                "unique_evidence_fact_count": _count(record.get("unique_evidence_fact_count")),
                "ticker_specific_fact_count": _count(record.get("ticker_specific_fact_count")),
                "distinct_supporting_agent_count": _count(
                    record.get("distinct_supporting_agent_count")
                ),
                "mode": _text(record.get("mode")),
                "exposure_status": _text(record.get("exposure_status")),
                "would_block_dominant": _boolean(record.get("would_block_dominant")),
                "would_block_regime_level": _boolean(record.get("would_block_regime_level")),
                "override_candidate": _boolean(record.get("override_candidate")),
                "qualification_effect_applied": _boolean(
                    record.get("qualification_effect_applied")
                ),
                "reason_codes_json": _json_copy(reason_codes),
                "provenance_json": _json_copy(provenance_with_lifecycle),
            }
        )
    return rows


def reconstruct_entity_exposure_record(row: Mapping[str, Any]) -> dict[str, Any]:
    effective_date = row.get("seed_effective_date")
    provenance = _json_copy(row.get("provenance_json") or {})
    # John's B3 gated seed lifecycle: unpacked back to top-level record
    # keys (matching the original in-memory record shape exactly) --
    # stored inside provenance_json only as a persistence-layer detail
    # (see build_entity_exposure_rows), never exposed as nested there.
    lifecycle = provenance.pop("b3_lifecycle", None)
    lifecycle = lifecycle if isinstance(lifecycle, Mapping) else {}
    return {
        "run_id": row.get("run_id"),
        "ticker": row.get("ticker"),
        "alpha_id": row.get("alpha_id"),
        "seed_version": row.get("seed_version"),
        "seed_effective_date": (
            effective_date.isoformat() if isinstance(effective_date, date) else effective_date
        ),
        "seed_approval_status": row.get("seed_approval_status"),
        "historical_mapping": row.get("historical_mapping"),
        "current_evidence": row.get("current_evidence"),
        "agent_confidence": row.get("agent_confidence"),
        "final_exposure": row.get("final_exposure"),
        "unique_evidence_fact_count": row.get("unique_evidence_fact_count"),
        "ticker_specific_fact_count": row.get("ticker_specific_fact_count"),
        "distinct_supporting_agent_count": row.get("distinct_supporting_agent_count"),
        "mode": row.get("mode"),
        "exposure_status": row.get("exposure_status"),
        "would_block_dominant": row.get("would_block_dominant"),
        "would_block_regime_level": row.get("would_block_regime_level"),
        "override_candidate": row.get("override_candidate"),
        "qualification_effect_applied": row.get("qualification_effect_applied"),
        "owner": lifecycle.get("owner"),
        "approved_by": lifecycle.get("approved_by"),
        "approved_at": lifecycle.get("approved_at"),
        "configured_status": lifecycle.get("configured_status"),
        "effective_status": lifecycle.get("effective_status"),
        "reason_codes": _json_copy(row.get("reason_codes_json") or []),
        "provenance": provenance,
    }


__all__ = [
    "EXPOSURE_PERSISTENCE_PAYLOAD_INVALID",
    "ExposurePersistenceDataError",
    "build_entity_exposure_rows",
    "reconstruct_entity_exposure_record",
]
