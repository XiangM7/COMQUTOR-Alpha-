"""Deterministic, single-claim semantic cues shared by Week 1 and Week 2.

The helpers in this module deliberately stay narrow. They annotate one claim;
they do not aggregate agents, score a ticker, or make an investment decision.
"""

from __future__ import annotations

import re
from dataclasses import asdict, dataclass
from typing import Any

from comqutor_alpha.structure_engine.factor_normalizer import normalize_text


VALID_ASSERTION_STATUSES = {"asserted", "conditional", "negated", "mixed", "unknown"}
VALID_SEMANTIC_POLARITIES = {
    "activation",
    "invalidation",
    "risk_relief",
    "mention",
    "mixed",
    "unknown",
}

OPPORTUNITY_ALPHA_IDS = {"A001", "A003", "A101", "A102", "A103", "A201", "A301", "A601"}
RISK_ALPHA_IDS = {"A304", "A501"}
COMPETITION_SENSITIVE_ALPHA_IDS = {"A101", "A102", "A103", "A201", "A301"}

_CONDITIONAL_PATTERN = re.compile(r"\b(if|unless|could|may|might|would|potentially)\b")
_CONTRAST_PATTERN = re.compile(r"\b(but|however|although|despite|yet|while|whereas)\b")
_NEGATION_PATTERN = re.compile(
    r"\b(no evidence|not(?! only)|never|unlikely|without|fails? to|failed to|"
    r"does not|do not|did not)\b"
)
_POSITIVE_PATTERN = re.compile(
    r"\b(growth|strong|strengthen|rise|rises|rising|increase|increases|increasing|"
    r"expand|expands|expansion|upside|support|supports|accelerat\w*|improv\w*|benefit\w*)\b"
)
_NEGATIVE_PATTERN = re.compile(
    r"\b(risk|threat|decline|declines|fall|falls|falling|pressure|compress\w*|"
    r"slow|slows|slowing|weak|weakens|downside|headwind|ceiling|delay\w*|peak|peaks)\b"
)

_COMPETITION_PATTERN = re.compile(
    r"\b(competitor|competition|competitive threat|custom silicon|alternative accelerator|"
    r"substitut\w*|displac\w*|reduce\w* (?:their )?dependency|niche competition|"
    r"niche competitor|rival chip|cuda moat)\b"
)
_TECHNICAL_PATTERN = re.compile(
    r"\b(sma|ema|rsi|macd|vwma|bollinger|support level|resistance level|technical breakdown)\b"
)
_POSITIONING_PATTERN = re.compile(
    r"\b(covered call|call selling|options positioning|dealer gamma|systematic flow)\b"
)

_RECESSION_RELIEF_PATTERNS = (
    re.compile(
        r"\b(?:low|lower|falling|declining|receding|easing|limited|contained)\s+"
        r"(?:u s )?(?:recession|slowdown)\s+(?:risk|probability)\b"
    ),
    re.compile(
        r"\b(?:recession|slowdown)\s+(?:risk|probability)\s+(?:is |remains )?"
        r"(?:low|lower|falling|declining|receding|easing|limited|contained)\b"
    ),
    re.compile(r"\bcredit spreads\s+(?:are )?(?:tightening|narrowing)\b"),
    re.compile(r"\b(?:recession|economic slowdown)\s+(?:is )?unlikely\b"),
    re.compile(r"\bno evidence\b.*\b(?:recession|economic slowdown)\b"),
)
_VALUATION_RELIEF_PATTERNS = (
    re.compile(r"\bvaluation (?:risk|pressure)\s+(?:is )?(?:falling|easing|receding)\b"),
    re.compile(r"\bmultiple (?:expansion|re rating)\b"),
    re.compile(r"\bmultiples?\s+(?:are )?(?:expanding|recovering|re rating)\b"),
    re.compile(r"\bdiscount rates?\s+(?:are )?(?:falling|declining|easing)\b"),
)
_RATE_CUT_INVALIDATION_PATTERN = re.compile(
    r"\b(zero (?:fed )?rate cuts?|no (?:fed )?rate cuts?|higher for longer|"
    r"rates? (?:stay|stays|remain|remains) (?:high|restrictive)|fed (?:stays|remains) restrictive)\b"
)
_INVALIDATION_PATTERN = re.compile(
    r"\b(demand (?:peaks?|weakens?|slows?|falls?|declines?)|"
    r"capex (?:cuts?|falls?|declines?|is delayed)|"
    r"revenue (?:misses?|slows?|falls?|is delayed|is still .* away)|"
    r"not (?:a )?booked revenue|air pocket|downside pressure|upside pressure|"
    r"headwind|valuation ceiling|dampens? upside|reduce\w* momentum)\b"
)
_MENTION_ONLY_PATTERN = re.compile(
    r"\b(is mentioned|was mentioned|merely mentions|watch item|rather than an immediate threat|"
    r"not an immediate threat|niche watch item)\b"
)


@dataclass(frozen=True)
class ClaimSemantics:
    assertion_status: str
    semantic_polarity: str
    conditional: bool
    negated: bool
    mixed: bool
    competition_context: bool
    taxonomy_gap_context: str | None = None

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


def _matches_any(patterns: tuple[re.Pattern[str], ...], text: str) -> bool:
    return any(pattern.search(text) for pattern in patterns)


def recession_risk_is_relief(text: Any) -> bool:
    return _matches_any(_RECESSION_RELIEF_PATTERNS, normalize_text(text))


def valuation_risk_is_relief(text: Any) -> bool:
    return _matches_any(_VALUATION_RELIEF_PATTERNS, normalize_text(text))


def analyze_claim_semantics(text: Any) -> ClaimSemantics:
    normalized = normalize_text(text)
    if not normalized:
        return ClaimSemantics("unknown", "unknown", False, False, False, False)

    conditional = bool(_CONDITIONAL_PATTERN.search(normalized))
    negated = bool(_NEGATION_PATTERN.search(normalized))
    has_contrast = bool(_CONTRAST_PATTERN.search(normalized))
    has_positive = bool(_POSITIVE_PATTERN.search(normalized))
    has_negative = bool(_NEGATIVE_PATTERN.search(normalized))
    mixed = has_contrast and has_positive and has_negative
    competition_context = bool(_COMPETITION_PATTERN.search(normalized))

    taxonomy_gap_context = None
    if competition_context:
        taxonomy_gap_context = "competition_or_substitution"
    elif _TECHNICAL_PATTERN.search(normalized):
        taxonomy_gap_context = "technical_market_state"
    elif _POSITIONING_PATTERN.search(normalized):
        taxonomy_gap_context = "positioning_or_flow"

    risk_relief = recession_risk_is_relief(normalized) or valuation_risk_is_relief(normalized)
    invalidation = bool(_INVALIDATION_PATTERN.search(normalized))
    mention_only = bool(_MENTION_ONLY_PATTERN.search(normalized))

    if mixed:
        assertion_status = "mixed"
    elif negated and not risk_relief:
        assertion_status = "negated"
    elif conditional:
        assertion_status = "conditional"
    else:
        assertion_status = "asserted"

    if competition_context or mention_only:
        semantic_polarity = "mention"
    elif mixed:
        semantic_polarity = "mixed"
    elif risk_relief:
        semantic_polarity = "risk_relief"
    elif invalidation:
        semantic_polarity = "invalidation"
    elif negated:
        semantic_polarity = "mention"
    else:
        semantic_polarity = "activation"

    return ClaimSemantics(
        assertion_status=assertion_status,
        semantic_polarity=semantic_polarity,
        conditional=conditional,
        negated=negated,
        mixed=mixed,
        competition_context=competition_context,
        taxonomy_gap_context=taxonomy_gap_context,
    )


def alpha_relation(text: Any, alpha_id: str) -> str:
    """Describe how one claim relates to one candidate alpha."""
    normalized = normalize_text(text)
    semantics = analyze_claim_semantics(normalized)

    if semantics.competition_context and alpha_id in COMPETITION_SENSITIVE_ALPHA_IDS:
        return "mention"
    if alpha_id == "A501" and recession_risk_is_relief(normalized):
        return "risk_relief"
    if alpha_id == "A304" and valuation_risk_is_relief(normalized):
        return "risk_relief"
    if alpha_id == "A001" and _RATE_CUT_INVALIDATION_PATTERN.search(normalized):
        return "invalidation"
    if alpha_id in OPPORTUNITY_ALPHA_IDS and _INVALIDATION_PATTERN.search(normalized):
        return "invalidation"
    if semantics.semantic_polarity == "mention":
        return "mention"
    if semantics.mixed:
        return "mixed"
    if semantics.conditional:
        return "conditional"
    if semantics.negated:
        return "mention"
    return "activation"


def semantic_score_for_relation(relation: str) -> float:
    return {
        "activation": 1.0,
        "invalidation": 0.9,
        "risk_relief": 0.9,
        "conditional": 0.65,
        "mixed": 0.7,
        "mention": 0.0,
    }.get(relation, 0.0)
