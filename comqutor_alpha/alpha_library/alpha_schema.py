"""Simple schema objects for the COMQUTOR Alpha taxonomy."""

from __future__ import annotations

from dataclasses import dataclass, field


@dataclass(frozen=True)
class ConflictAlpha:
    alpha_id: str
    contradiction_weight: float


@dataclass(frozen=True)
class AlphaSignal:
    signal_type: str
    text: str
    weight: float = 1.0


@dataclass(frozen=True)
class AlphaDefinition:
    alpha_id: str
    name_en: str
    name_cn: str
    layer: str
    status: str
    core_thesis: str
    keywords: list[str] = field(default_factory=list)
    trigger_signals: list[str] = field(default_factory=list)
    confirmation_signals: list[str] = field(default_factory=list)
    beneficiary_assets: list[str] = field(default_factory=list)
    risk_assets: list[str] = field(default_factory=list)
    conflict_alphas: list[ConflictAlpha] = field(default_factory=list)
    invalidation_conditions: list[str] = field(default_factory=list)
    agent_sources: list[str] = field(default_factory=list)
    relations: list[dict] = field(default_factory=list)

    @classmethod
    def from_dict(cls, data: dict) -> "AlphaDefinition":
        conflicts = [
            ConflictAlpha(
                alpha_id=str(item["alpha_id"]),
                contradiction_weight=float(item.get("contradiction_weight", 0.0)),
            )
            for item in data.get("conflict_alphas", [])
        ]
        return cls(
            alpha_id=str(data["alpha_id"]),
            name_en=str(data["name_en"]),
            name_cn=str(data["name_cn"]),
            layer=str(data["layer"]),
            status=str(data["status"]),
            core_thesis=str(data["core_thesis"]),
            keywords=[str(item) for item in data.get("keywords", [])],
            trigger_signals=[str(item) for item in data.get("trigger_signals", [])],
            confirmation_signals=[str(item) for item in data.get("confirmation_signals", [])],
            beneficiary_assets=[str(item) for item in data.get("beneficiary_assets", [])],
            risk_assets=[str(item) for item in data.get("risk_assets", [])],
            conflict_alphas=conflicts,
            invalidation_conditions=[
                str(item) for item in data.get("invalidation_conditions", [])
            ],
            agent_sources=[str(item) for item in data.get("agent_sources", [])],
            relations=list(data.get("relations", [])),
        )
