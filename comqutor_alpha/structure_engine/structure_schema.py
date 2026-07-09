"""Shared schema helpers for COMQUTOR official structure outputs."""

from __future__ import annotations

from dataclasses import asdict, dataclass, field


VALID_DIRECTIONS = {"positive", "negative", "neutral", "unknown"}


def clamp_score(value, minimum=0.0, maximum=1.0):
    try:
        number = float(value)
    except (TypeError, ValueError):
        number = minimum
    return round(min(max(number, minimum), maximum), 4)


def normalize_direction(direction):
    normalized = str(direction or "unknown").strip().lower()
    if normalized in {"bullish", "buy", "upside"}:
        return "positive"
    if normalized in {"bearish", "sell", "downside"}:
        return "negative"
    if normalized in {"mixed", "hold", "balanced"}:
        return "neutral"
    return normalized if normalized in VALID_DIRECTIONS else "unknown"


@dataclass
class StructuredAgentOutput:
    run_id: str
    ticker: str
    agent: str
    timestamp: str
    claim: str
    evidence: str
    entities: list[str] = field(default_factory=list)
    factors: list[str] = field(default_factory=list)
    direction: str = "unknown"
    confidence: float = 0.0
    source_type: str = "unknown"
    output_type: str = "unknown"
    source_agent_output_id: str | None = None
    source_refs: list[str] = field(default_factory=list)

    def to_dict(self):
        data = asdict(self)
        data["direction"] = normalize_direction(data["direction"])
        data["confidence"] = clamp_score(data["confidence"])
        return data


@dataclass
class AlphaMatch:
    run_id: str
    ticker: str
    agent: str
    claim: str
    alpha_id: str
    name: str
    match_score: float
    direction: str
    evidence: str

    def to_dict(self):
        data = asdict(self)
        data["match_score"] = clamp_score(data["match_score"])
        data["direction"] = normalize_direction(data["direction"])
        return data


@dataclass
class StructureNode:
    id: str
    label: str
    node_type: str = "unknown"
    alpha_ids: list[str] = field(default_factory=list)
    evidence: list[str] = field(default_factory=list)
    score: float = 0.0

    def to_dict(self):
        data = asdict(self)
        data["score"] = clamp_score(data["score"])
        return data


@dataclass
class StructureEdge:
    source: str
    target: str
    edge_type: str
    weight: float = 0.0
    evidence: str = ""

    def to_dict(self):
        data = asdict(self)
        data["weight"] = clamp_score(data["weight"])
        return data
