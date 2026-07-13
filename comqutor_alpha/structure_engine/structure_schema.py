"""Shared schema helpers for COMQUTOR official structure outputs.

These dataclasses mirror the actual dict shapes produced by
alpha_mapper.map_claim_to_alpha and structure_extractor.extract_structures_from_records.
They are optional typed helpers (the mapper/extractor return plain dicts),
useful for callers that want a validated, normalized view of a record.
"""

from __future__ import annotations

from dataclasses import asdict, dataclass, field
from typing import Any


VALID_DIRECTIONS = {"positive", "negative", "neutral", "unknown"}
VALID_EDGE_TYPES = {"causal", "supportive", "conflicting"}
VALID_MATCH_STATUSES = {"matched", "no_match", "ambiguous"}
VALID_ASSERTION_STATUSES = {"asserted", "conditional", "negated", "mixed", "unknown"}
MAX_CANDIDATE_SCORES = 5


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


def _dedupe(values: list[Any]) -> list[Any]:
    seen = set()
    result = []
    for value in values:
        if value not in seen:
            result.append(value)
            seen.add(value)
    return result


@dataclass
class StructuredAgentOutput:
    """Mirrors a record in structured_agent_outputs.json (structured_output_adapter.py)."""

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
    agent_output_id: str | None = None
    source_agent_output_id: str | None = None
    source_refs: list[str] = field(default_factory=list)
    claim_index: int = 0
    source_section: str | None = None
    assertion_status: str = "unknown"
    semantic_polarity: str = "unknown"

    def to_dict(self):
        data = asdict(self)
        data["direction"] = normalize_direction(data["direction"])
        data["confidence"] = clamp_score(data["confidence"])
        assertion_status = str(data.get("assertion_status") or "unknown").strip().lower()
        data["assertion_status"] = (
            assertion_status if assertion_status in VALID_ASSERTION_STATUSES else "unknown"
        )
        return data


@dataclass
class AlphaCandidateScore:
    """Mirrors one entry of `candidate_scores` from alpha_mapper._candidate_score."""

    alpha_id: str
    alpha_name: str
    score: float = 0.0
    keyword_score: float = 0.0
    factor_score: float = 0.0
    direction_score: float = 0.0
    semantic_score: float = 0.0
    relation: str = "unknown"
    eligible: bool = False
    rejection_reason: str | None = None

    def to_dict(self):
        data = asdict(self)
        for key in (
            "score",
            "keyword_score",
            "factor_score",
            "direction_score",
            "semantic_score",
        ):
            data[key] = clamp_score(data[key])
        return data


@dataclass
class AlphaMatchRecord:
    """Mirrors the dict returned by alpha_mapper.map_claim_to_alpha."""

    run_id: str
    ticker: str
    agent: str
    source_agent_output_id: str | None
    claim: str
    direction: str
    matched_alpha: str | None
    matched_alpha_name: str | None
    score: float
    keyword_score: float
    factor_score: float
    direction_score: float
    candidate_scores: list[dict[str, Any]] = field(default_factory=list)
    match_status: str = "no_match"
    reason: str = ""
    assertion_status: str = "unknown"
    semantic_polarity: str = "unknown"
    taxonomy_gap_context: str | None = None
    eligible_candidates: list[dict[str, Any]] = field(default_factory=list)
    plausible_alphas: list[str] = field(default_factory=list)
    secondary_alphas: list[str] = field(default_factory=list)
    classifier: dict[str, Any] = field(default_factory=dict)

    def to_dict(self):
        data = asdict(self)
        data["direction"] = normalize_direction(data["direction"])
        for key in ("score", "keyword_score", "factor_score", "direction_score"):
            data[key] = clamp_score(data[key])

        status = str(data.get("match_status") or "no_match").strip().lower()
        data["match_status"] = status if status in VALID_MATCH_STATUSES else "no_match"
        if data["match_status"] != "matched":
            # A non-matched record must never carry a matched alpha, regardless
            # of what the caller passed in.
            data["matched_alpha"] = None
            data["matched_alpha_name"] = None

        normalized_candidates = []
        for candidate in data.get("candidate_scores") or []:
            if isinstance(candidate, AlphaCandidateScore):
                normalized_candidates.append(candidate.to_dict())
            elif isinstance(candidate, dict):
                normalized_candidates.append(
                    AlphaCandidateScore(
                        alpha_id=str(candidate.get("alpha_id", "")),
                        alpha_name=str(candidate.get("alpha_name", "")),
                        score=candidate.get("score", 0.0),
                        keyword_score=candidate.get("keyword_score", 0.0),
                        factor_score=candidate.get("factor_score", 0.0),
                        direction_score=candidate.get("direction_score", 0.0),
                        semantic_score=candidate.get("semantic_score", 0.0),
                        relation=str(candidate.get("relation", "unknown")),
                        eligible=bool(candidate.get("eligible", False)),
                        rejection_reason=candidate.get("rejection_reason"),
                    ).to_dict()
                )
        data["candidate_scores"] = normalized_candidates[:MAX_CANDIDATE_SCORES]
        return data


@dataclass
class StructureNode:
    """Mirrors the dict returned by structure_extractor._make_node."""

    id: str
    label: str
    canonical_factor: str = "Unknown"
    node_type: str = "factor"
    source_records: list[str] = field(default_factory=list)
    evidence: list[str] = field(default_factory=list)
    score: float = 0.0

    def to_dict(self):
        data = asdict(self)
        data["score"] = clamp_score(data["score"])
        data["source_records"] = _dedupe([v for v in data["source_records"] if v])
        data["evidence"] = _dedupe([v for v in data["evidence"] if v])
        return data


@dataclass
class StructureEdge:
    """Mirrors the dict returned by structure_extractor._edge."""

    source: str
    target: str
    source_label: str
    target_label: str
    edge_type: str
    confidence: float = 0.0
    rule_name: str = ""
    reason: str = ""
    source_claim: str = ""
    source_record_id: str | None = None
    source_agent_output_id: str | None = None
    assertion_status: str = "asserted"

    def to_dict(self):
        data = asdict(self)
        data["confidence"] = clamp_score(data["confidence"])
        edge_type = str(data.get("edge_type") or "").strip().lower()
        if edge_type in VALID_EDGE_TYPES:
            data["edge_type"] = edge_type
        assertion_status = str(data.get("assertion_status") or "unknown").strip().lower()
        data["assertion_status"] = (
            assertion_status if assertion_status in VALID_ASSERTION_STATUSES else "unknown"
        )
        return data
