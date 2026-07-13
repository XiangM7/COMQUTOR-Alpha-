"""Explicit seed-based entity exposure; missing data is never guessed."""

from __future__ import annotations

from pathlib import Path

import yaml
from pydantic import Field

from comqutor_alpha.config import normalize_ticker
from comqutor_alpha.structure_engine.structure_schema import (
    AlphaId,
    DomainModel,
    ExposureResult,
    ExposureStatus,
    NonEmptyStr,
    UnitFloat,
)

DEFAULT_SEED_PATH = Path(__file__).parents[1] / "alpha_library/entity_alpha_exposure_seed.yaml"


class ExposureSeedDocument(DomainModel):
    schema_version: NonEmptyStr
    source_note: NonEmptyStr
    review_status: NonEmptyStr
    entities: dict[NonEmptyStr, dict[AlphaId, UnitFloat]] = Field(default_factory=dict)


class ExposureSeedError(ValueError):
    pass


class ExposureEngine:
    def __init__(self, seeds: ExposureSeedDocument):
        self.seeds = seeds

    @classmethod
    def from_yaml(cls, path: Path | str = DEFAULT_SEED_PATH) -> ExposureEngine:
        source = Path(path)
        try:
            raw = yaml.safe_load(source.read_text(encoding="utf-8"))
            return cls(ExposureSeedDocument.model_validate(raw))
        except Exception as exc:
            raise ExposureSeedError(f"invalid exposure seed {source}: {exc}") from exc

    def calculate(
        self,
        *,
        ticker: str,
        alpha_id: str,
        current_evidence: float,
        agent_confidence: float,
        evidence_references: list[str] | None = None,
    ) -> ExposureResult:
        normalized = normalize_ticker(ticker)
        historical = self.seeds.entities.get(normalized, {}).get(alpha_id)
        common = {
            "ticker": normalized,
            "alpha_id": alpha_id,
            "current_evidence": current_evidence,
            "agent_confidence": agent_confidence,
            "evidence_references": evidence_references or [],
        }
        if historical is None:
            return ExposureResult(status=ExposureStatus.NO_SEED, **common)
        score = historical * 0.5 + current_evidence * 0.3 + agent_confidence * 0.2
        return ExposureResult(
            status=ExposureStatus.SEEDED,
            historical_mapping=historical,
            exposure_score=score,
            **common,
        )
