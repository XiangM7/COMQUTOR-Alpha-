"""Deterministic, single-claim semantic cues shared by Week 1 and Week 2.

The helpers in this module deliberately stay narrow. They annotate one claim;
they do not aggregate agents, score a ticker, or make an investment decision.
"""

from __future__ import annotations

import re
from collections.abc import Callable
from dataclasses import asdict, dataclass
from typing import Any

from comqutor_alpha.structure_engine.factor_normalizer import normalize_text, term_in_text


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
    r"rates? (?:stay|stays|remain|remains) (?:high|restrictive)|fed (?:stays|remains) restrictive|"
    # v0.2 QQQ A001 mapping remediation (Step 7A): the original pattern above
    # already covered the most explicit "no cut" phrasing, but the Step-5/6
    # persisted QQQ evidence corpus (run f88c8956-...) showed the dominant
    # real-world false-positive surface is rate-HIKE / hawkish-repricing
    # language -- the direct economic opposite of a rate-cut cycle, which is
    # never itself a "no cut" sentence and so was not previously matched.
    r"rate hikes?|hike odds|probability of a hike|odds of a hike|hawkish|"
    r"(?:rising yields|yields? (?:rising|rose|are rising|is rising)))\b"
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


# v0.2 QQQ A001 mapping remediation (Step 7A): a general, table-driven
# registry of each Alpha's OWN explicit, high-precision "core thesis is
# false" pattern -- currently only A001 has one (_RATE_CUT_INVALIDATION_
# PATTERN), reusing the exact same alpha-specific check `alpha_relation`
# already applies at line ~196 above, exposed here as its own named
# predicate so callers outside this module (the Alpha Mapper) can apply it
# as a deterministic veto on a *specific candidate alpha_id* without
# duplicating the pattern or depending on `alpha_relation`'s full priority
# chain (which also folds in the generic, lower-precision multi-Alpha
# `_INVALIDATION_PATTERN`). Deliberately NOT keyed by ticker or run_id --
# extensible to any future Alpha that gets its own taxonomy-native
# invalidation pattern, never a per-ticker special case.
ALPHA_SPECIFIC_INVALIDATION_PATTERNS: dict[str, re.Pattern[str]] = {
    "A001": _RATE_CUT_INVALIDATION_PATTERN,
}


def alpha_specific_invalidation_matched(text: Any, alpha_id: str) -> bool:
    """True when `text` explicitly asserts that `alpha_id`'s own core thesis
    is false, per that Alpha's dedicated taxonomy-native pattern (if any).
    Returns False (never a false positive) for any alpha_id without a
    registered pattern -- this is a high-precision veto, not a general
    negativity/opposition detector."""
    pattern = ALPHA_SPECIFIC_INVALIDATION_PATTERNS.get(alpha_id)
    if pattern is None:
        return False
    return bool(pattern.search(normalize_text(text)))


# ---------------------------------------------------------------------------
# v0.2 QQQ A001 mapping remediation, Step 7A.2: Alpha-Specific Positive
# Requirement gate.
#
# Step 7A (the negative veto above) closed the most explicit false-positive
# surface, but an independent row-level residual audit
# (docs/audit_artifacts/v0_2_qqq_a001_residual_mapping_audit.json) found
# that ALL 29 still-surviving A001 mappings on the authoritative QQQ run
# were nonetheless false positives -- 0/29 expressed genuine affirmative
# easing. The dominant residual mechanism ("GENERIC_MACRO_OVERMATCH", 19/29)
# was generic rate-environment commentary (headwinds, repricing, sensitivity
# framing) that never triggers the negative veto because it never asserts
# the OPPOSITE of A001's thesis either -- it simply never asserts A001's
# thesis at all. A pure negative-blocklist approach cannot close this
# without an ever-growing enumeration; the fix is instead to require
# affirmative evidence before a match survives, symmetric to the existing
# negative veto.
#
# This classifies text into one of five directional classes; only
# POSITIVE_EASING satisfies the gate:
#   POSITIVE_EASING        -- affirmative, non-hedged, non-negated easing
#   NEGATIVE_OR_HAWKISH     -- opposes/invalidates the easing thesis
#   CONDITIONAL_OR_UNCERTAIN -- hedged/modal speculation about a future cut
#   GENERIC_RATE_CONTEXT    -- rate/Fed/macro-adjacent, no cut/easing content
#   NO_RATE_SEMANTICS       -- no rate-policy content at all
#
# Deliberately NOT a literal five-string match: each class is a tuple of
# patterns covering real semantic variants (see the residual audit and
# Step-7A.1 recommendation for the concrete phrasings this was built from),
# not just the taxonomy's five example anchor phrases. Reuses the existing
# _RATE_CUT_INVALIDATION_PATTERN (already alpha-specific to A001) as the
# core of the negative class rather than duplicating it.
_A001_DIRECT_POSITIVE_PATTERNS = (
    re.compile(r"\brate cuts?\b"),
    re.compile(r"\bcut(?:s|ting)? (?:the )?(?:policy )?rates?\b"),
    re.compile(r"\brate cut cycle\b"),
    re.compile(r"\beasing cycle\b"),
    re.compile(r"\b(?:monetary|policy) easing\b"),
    re.compile(r"\b(?:easier|looser) monetary policy\b"),
    re.compile(r"\bdovish pivot\b"),
    re.compile(r"\bfed .{0,20}\beas(?:e|es|ing)\b"),
    re.compile(r"\bfalling (?:policy |discount )?rates?\b"),
    re.compile(r"\bdeclining (?:policy |discount )?rates?\b"),
    re.compile(r"\blower(?:ing)? (?:policy |interest )?rates?\b"),
    re.compile(r"\brates?\b.{0,30}\b(?:falling|fall|declining|decline|dropping|drop)\b"),
    re.compile(r"\bborrowing costs (?:are |is )?(?:falling|declining|dropping|lower)\b"),
    re.compile(
        r"\b(?:central bank|fed|federal reserve) (?:moving toward|shifting to|pivoting to) "
        r"(?:an? )?(?:easier|looser) policy\b"
    ),
    re.compile(r"\brate decline\b"),
)
# Confident, non-hedged FUTURE expectation of cuts -- these already encode
# affirmative certainty in their own phrasing, so (unlike the direct-positive
# patterns above) a bare "could"/"may" elsewhere in the sentence does not
# downgrade them to CONDITIONAL_OR_UNCERTAIN.
_A001_AFFIRMATIVE_EXPECTATION_PATTERNS = (
    re.compile(
        r"\b(?:markets?|investors?) (?:are )?(?:expect|expects|expecting|anticipate|anticipates|"
        r"anticipating|pricing in|priced in) (?:the fed to )?(?:rate )?cuts?\b"
    ),
    re.compile(r"\bpricing in (?:rate )?cuts?\b"),
    re.compile(r"\banticipated (?:rate )?cuts?\b"),
    re.compile(r"\b(?:fed|central bank) (?:is |are )?(?:set to|poised to|going to|expected to) cut\b"),
)
# Broader than _RATE_CUT_INVALIDATION_PATTERN (which remains the Step-7A
# veto, unchanged): adds the Step-7A.1-identified negative phrasings that
# don't fit the veto's own narrow "core thesis is false" framing as cleanly
# but are still unambiguous NEGATIVE_OR_HAWKISH signals for this gate.
_A001_NEGATIVE_OR_HAWKISH_PATTERNS = (
    _RATE_CUT_INVALIDATION_PATTERN,
    re.compile(r"\bcuts?\b.{0,30}\b(?:delayed|pushed back|postponed)\b"),
    re.compile(r"\bfewer cuts?\b.{0,15}\bexpected\b"),
    re.compile(r"\bcuts?\b.{0,15}\bless likely\b"),
    re.compile(r"\btightening\b"),
    re.compile(r"\brestrictive policy persists?\b"),
    re.compile(r"\binflation prevents? easing\b"),
    re.compile(r"\b(?:cuts?|easing)\b.{0,15}\b(?:unlikely|off the table)\b"),
    re.compile(r"\brising discount rates?\b"),
    re.compile(r"\bdiscount rates? rise\b"),
    re.compile(r"\brates? (?:are )?rising\b"),
)
# Topic-adjacent but direction-neutral on their own -- must never
# independently satisfy the positive requirement (Section 7).
_A001_GENERIC_RATE_TERMS = (
    "discount rate", "duration", "treasury yield", "interest rate", "interest rates",
    "fed", "monetary policy", "macro", "inflation", "yield", "yields",
    "rate sensitivity", "rate environment",
)
# Mention-only "is this happening?" framing (Section 10): discussing WHETHER
# a cut will occur is not itself affirmative evidence that it is occurring
# or credibly expected -- checked before the direct-positive patterns so a
# bare "cut rates" inside a "whether...will..." question never counts.
_A001_MENTION_ONLY_PATTERNS = (
    re.compile(r"\bfocused on whether\b"),
    re.compile(r"\b(?:debate|discussion|question)s? (?:is |about |over )?whether\b"),
    re.compile(r"\buncertain(?:ty)? (?:about |over )?whether\b"),
    re.compile(r"\bwhether (?:the )?(?:fed|central bank) will\b"),
)


def classify_a001_directional_semantics(text: Any) -> str:
    """Classify `text` into one of POSITIVE_EASING / NEGATIVE_OR_HAWKISH /
    CONDITIONAL_OR_UNCERTAIN / GENERIC_RATE_CONTEXT / NO_RATE_SEMANTICS for
    A001 (Rate Cut Cycle). Order matters: negative evidence takes priority
    over positive-looking keywords (e.g. "rate cuts have been delayed"
    contains "rate cuts" but is NEGATIVE_OR_HAWKISH, never POSITIVE_EASING),
    and mention-only "whether a cut will happen" framing is checked before
    direct-positive patterns for the same reason. A direct-positive match
    still carrying a conditional/modal marker (if/unless/could/may/might/
    would/potentially) downgrades to CONDITIONAL_OR_UNCERTAIN -- confident
    affirmative-expectation phrasing does not."""
    normalized = normalize_text(text)
    if not normalized:
        return "NO_RATE_SEMANTICS"
    if _matches_any(_A001_NEGATIVE_OR_HAWKISH_PATTERNS, normalized):
        return "NEGATIVE_OR_HAWKISH"
    if _matches_any(_A001_MENTION_ONLY_PATTERNS, normalized):
        return "CONDITIONAL_OR_UNCERTAIN"
    if _matches_any(_A001_AFFIRMATIVE_EXPECTATION_PATTERNS, normalized):
        return "POSITIVE_EASING"
    if _matches_any(_A001_DIRECT_POSITIVE_PATTERNS, normalized):
        if _CONDITIONAL_PATTERN.search(normalized):
            return "CONDITIONAL_OR_UNCERTAIN"
        return "POSITIVE_EASING"
    if any(term_in_text(term, normalized) for term in _A001_GENERIC_RATE_TERMS):
        return "GENERIC_RATE_CONTEXT"
    return "NO_RATE_SEMANTICS"


# General, table-driven registry of each Alpha's own positive-requirement
# classifier (symmetric counterpart to ALPHA_SPECIFIC_INVALIDATION_PATTERNS
# above) -- currently only A001. Extensible to any future Alpha whose
# thesis requires directional confirmation; a no-op (always satisfied) for
# every Alpha without a registered classifier, per Section 20's explicit
# instruction not to build a broad ten-Alpha framework now.
ALPHA_POSITIVE_REQUIREMENT_CLASSIFIERS: dict[str, Callable[[Any], str]] = {
    "A001": classify_a001_directional_semantics,
}


def alpha_positive_requirement_satisfied(text: Any, alpha_id: str) -> bool:
    """True when `alpha_id` has no registered positive-requirement classifier
    (no gate applies -- never a false rejection for an Alpha this mechanism
    doesn't cover), or when its classifier resolves `text` to POSITIVE_EASING
    (the only class that satisfies the gate)."""
    classifier = ALPHA_POSITIVE_REQUIREMENT_CLASSIFIERS.get(alpha_id)
    if classifier is None:
        return True
    return classifier(text) == "POSITIVE_EASING"


def semantic_score_for_relation(relation: str) -> float:
    return {
        "activation": 1.0,
        "invalidation": 0.9,
        "risk_relief": 0.9,
        "conditional": 0.65,
        "mixed": 0.7,
        "mention": 0.0,
    }.get(relation, 0.0)
