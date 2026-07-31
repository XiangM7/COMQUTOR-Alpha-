"""Unified, deterministic Claim Quality Gate.

Pure functions only: no I/O, no database, no Provider/LLM/network calls, no
Mapper/Graph calls. Classifies one claim's (claim, evidence) pair into
exactly one of ``ANALYTICAL`` / ``CONTEXT_ONLY`` / ``NON_SUBSTANTIVE``, and
exposes a single shared eligibility function (:func:`is_claim_eligible`)
every downstream consumer (Mapper, Structure Extractor, Activation, Conflict
Detector, persistence, product findings) calls instead of inventing its own
ad hoc quality judgment.

Complexity: a single pass over the claim's text against a fixed, compiled
set of pattern families -- O(n + p) for text length n and a constant number
of pattern families p, never a combinatorial search over every word or
phrase pair.

Reuses (never re-derives) ``claim_semantics.analyze_claim_semantics`` for
conditional/negation/risk-relief/invalidation detection, ``factor_normalizer``
for domain-term matching, and ``relation_grammar``'s compiled relation-verb
patterns for relation-predicate detection -- so this module's own notion of
"the text expresses a relation" can never drift from the Structure Graph's
own relation vocabulary.
"""

from __future__ import annotations

import re
from collections.abc import Mapping
from dataclasses import asdict, dataclass
from typing import Any

from comqutor_alpha.structure_engine.claim_semantics import analyze_claim_semantics
from comqutor_alpha.structure_engine.factor_normalizer import (
    extract_known_factors_from_text,
    normalize_text,
)
from comqutor_alpha.structure_engine.relation_grammar import (
    CONFLICT_WORDS,
    FORWARD_MULTIWORD_PATTERN,
    FORWARD_TRANSITIVE_CAUSAL_PATTERN,
    FORWARD_TRANSITIVE_SUPPORTIVE_PATTERN,
    REVERSE_MULTIWORD_PATTERN,
    REVERSE_PASSIVE_PATTERN,
)
from comqutor_alpha.structure_engine.structure_schema import normalize_direction

# ---------------------------------------------------------------------------
# Quality classes
# ---------------------------------------------------------------------------

QUALITY_ANALYTICAL = "analytical"
QUALITY_CONTEXT_ONLY = "context_only"
QUALITY_NON_SUBSTANTIVE = "non_substantive"
VALID_QUALITY_CLASSES = frozenset({QUALITY_ANALYTICAL, QUALITY_CONTEXT_ONLY, QUALITY_NON_SUBSTANTIVE})

# ---------------------------------------------------------------------------
# Stable reason codes (persisted/audited; never renamed once shipped).
# ---------------------------------------------------------------------------

REASON_BOILERPLATE_META_COMMENTARY = "BOILERPLATE_META_COMMENTARY"
REASON_NON_ASSERTIVE_TRANSITION = "NON_ASSERTIVE_TRANSITION"
REASON_DISCLAIMER_ONLY = "DISCLAIMER_ONLY"
REASON_PLACEHOLDER_UNKNOWN = "PLACEHOLDER_UNKNOWN"
REASON_NO_EXTERNAL_ASSERTION = "NO_EXTERNAL_ASSERTION"
REASON_BARE_HEADING_OR_LABEL = "BARE_HEADING_OR_LABEL"
# Adapter-level (not returned by classify_claim_quality itself): recorded
# when every LLM-proposed claim for one raw output was rejected by this
# gate and the adapter fell back to the deterministic splitter.
REASON_LLM_ALL_CLAIMS_REJECTED = "LLM_ALL_CLAIMS_REJECTED"

REASON_ANALYTICAL_RELATION_SIGNAL = "ANALYTICAL_RELATION_SIGNAL"
REASON_ANALYTICAL_STATE_OR_CHANGE_SIGNAL = "ANALYTICAL_STATE_OR_CHANGE_SIGNAL"
REASON_ANALYTICAL_RISK_OR_FORECAST_SIGNAL = "ANALYTICAL_RISK_OR_FORECAST_SIGNAL"
REASON_ANALYTICAL_DIRECTIONAL_SIGNAL = "ANALYTICAL_DIRECTIONAL_SIGNAL"
REASON_CONTEXT_ONLY_FACTUAL_ASSERTION = "CONTEXT_ONLY_FACTUAL_ASSERTION"

# ---------------------------------------------------------------------------
# Consumers (the shared eligibility matrix's column names).
# ---------------------------------------------------------------------------

CONSUMER_MAPPING = "mapping"
CONSUMER_STRUCTURE = "structure"
CONSUMER_ACTIVATION = "activation"
CONSUMER_CONFLICT = "conflict"
CONSUMER_PRODUCT_FINDINGS = "product_findings"
CONSUMER_ANALYTICAL_PERSISTENCE = "analytical_persistence"
VALID_CONSUMERS = frozenset(
    {
        CONSUMER_MAPPING,
        CONSUMER_STRUCTURE,
        CONSUMER_ACTIVATION,
        CONSUMER_CONFLICT,
        CONSUMER_PRODUCT_FINDINGS,
        CONSUMER_ANALYTICAL_PERSISTENCE,
    }
)

# has_directional_signal (a classification feature) requires an explicit
# bullish/bearish signal -- strictly positive/negative.
_POSITIVE_OR_NEGATIVE = frozenset({"positive", "negative"})

# ---------------------------------------------------------------------------
# Text prep. Two normalizations are used deliberately:
# - ``_collapse_whitespace``: whitespace-collapse only (preserves case,
#   punctuation, and "?") -- needed for the meta-commentary/transition/
#   disclaimer patterns (anchored, case-insensitive regexes) and for
#   interrogative detection.
# - ``factor_normalizer.normalize_text``: lowercase, alnum+%%+$ only -- used
#   for domain-anchor/event/state-change/relation/risk term matching, the
#   same normalization every other structure_engine module already uses.
# ---------------------------------------------------------------------------

_WHITESPACE_PATTERN = re.compile(r"\s+")


def _collapse_whitespace(value: Any) -> str:
    return _WHITESPACE_PATTERN.sub(" ", str(value or "")).strip()


def _combined_text(claim: Any, evidence: Any) -> str:
    claim_text = _collapse_whitespace(claim)
    evidence_text = _collapse_whitespace(evidence)
    if not evidence_text or evidence_text == claim_text:
        return claim_text
    return f"{claim_text} {evidence_text}"


# Exact-match placeholder texts beyond the bare "unknown" adapter sentinel:
# system/pipeline-generated stand-ins for "there is nothing here" that real
# analyst prose never organically produces verbatim. Matched after stripping
# trailing sentence punctuation, never as a substring/regex (avoids matching
# a genuine sentence that merely contains one of these phrases).
_PLACEHOLDER_EXACT_TEXTS = frozenset(
    {
        "",
        "unknown",
        "no body excerpt available",
        "all data is collected",
        "all data is now collected",
    }
)


def _is_placeholder_text(claim_text: str) -> bool:
    return claim_text.strip().lower().rstrip(".!?") in _PLACEHOLDER_EXACT_TEXTS


def _is_bare_heading_fragment(
    claim_text: str, *, has_quantitative_anchor: bool, analytical_signal: bool
) -> bool:
    """A bare report heading/label/list-introducer ("Operating Cash Flow
    (EXCEPTIONAL):", "Key inferences from news:") -- the spec's own "pure
    headings/formatting" NON_SUBSTANTIVE example. A colon-terminated
    fragment carrying a real figure or an independent analytical signal is
    never caught by this (e.g. "RSI at 48.46 places MU squarely in neutral
    territory (neither overbought nor oversold):" keeps its own real
    content), so this only fires on fragments whose entire payload is the
    label itself."""
    return (
        claim_text.strip().endswith(":")
        and not has_quantitative_anchor
        and not analytical_signal
    )


# ---------------------------------------------------------------------------
# NON_SUBSTANTIVE hard-reject patterns (meta-commentary / transition /
# disclaimer). Same vocabulary the structured-output adapter's sentence-level
# boundary filter uses -- kept here as the single source of truth so both the
# early sentence-segmentation boundary and this later, unified claim-level
# gate can never drift apart. structured_output_adapter.py imports these.
# ---------------------------------------------------------------------------

DISCLAIMER_MARKERS = (
    "disclaimer",
    "not investment advice",
    "not financial advice",
    "for informational purposes only",
    "past performance is not indicative",
)

META_COMMENTARY_PATTERNS = (
    re.compile(
        r"(?i)\b(?:i|we)\s+(?:now\s+)?(?:have|will(?:\s+now)?|can(?:\s+now)?|am going to|"
        r"'m going to)\s+"
        r"(?:all\s+the\s+data|enough\s+(?:data|information)|the\s+(?:data|information)|"
        r"now\s+)?[^.!?]*"
        r"\b(?:compile|synthesize|synthesise|summarize|summarise|write|draft|produce|"
        r"present|prepare|proceed|begin|gather)\b"
    ),
    re.compile(
        r"(?i)^\s*(?:excellent|great|perfect|okay|ok|alright)?\s*[-—,.!]*\s*(?:now\s+)?"
        r"(?:let\s+me|let's|i\s+will|i'll|i\s+can\s+now|i\s+now\s+have)\b"
    ),
    re.compile(r"(?i)^\s*here\s+is\s+(?:the|a|my)\s+(?:comprehensive|full|final|complete)\b"),
    re.compile(r"(?i)\bi\s+now\s+have\s+(?:all\s+the|a\s+comprehensive|enough)\b"),
)

TRANSITION_PATTERNS = (
    re.compile(r"(?i)^\s*(?:moving|turning)\s+(?:on\s+)?to\b"),
    re.compile(r"(?i)^\s*(?:now\s+)?(?:for|onto)\s+the\s+next\s+(?:section|part|topic)\b"),
    re.compile(r"(?i)^\s*(?:as|with)\s+(?:mentioned|noted|discussed)\s+(?:above|earlier|previously)\b[^a-z0-9]*$"),
)


def _terms_pattern(terms: tuple[str, ...]) -> re.Pattern[str]:
    """Compile a set of (possibly multi-word) terms into one alternation
    pattern, whole-word/phrase bounded. One compiled pattern -> one
    ``.search()`` call per feature, never a per-term loop."""
    parts = [r"\b" + r"\s+".join(re.escape(word) for word in term.split()) + r"\b" for term in terms]
    return re.compile("|".join(parts))


# Substantive-signal markers (this module's own copy -- see the "moved-from-
# adapter" note above; NOT shared with structured_output_adapter.py's own,
# separate boundary-level pattern of the same name, so trimming this one
# cannot affect that earlier, already-tested filter): meta-commentary/
# transition patterns only ever reject a claim that ALSO lacks every one of
# these signals.
#
# Deliberately narrower than a first draft that also matched pure
# grammatical connectives (because/due to/if/unless/could/may/might/would/
# despite): a bare connective carries no substance on its own, and letting
# one satisfy this carve-out let genuine meta-commentary sentences that
# merely happen to contain "because" (e.g. a debate-analyst's "Now let me
# address the technical picture, because I think both analysts are
# selectively reading the same data.") slip through as CONTEXT_ONLY instead
# of being correctly rejected -- found via the Product Findings Closure
# Sprint's context-only precision audit. Every term kept below is a
# substantive financial noun/verb/phrase, not a connective.
_SUBSTANTIVE_SIGNAL_PATTERN = re.compile(
    r"(?i)(?:\d|%|\$"
    r"|\b(?:revenue|earnings|margin|guidance|demand|supply|price|prices|pricing|valuation"
    r"|growth|decline|risk|rally|selloff|sell-off|upside|downside|bullish|bearish"
    r"|buy|sell|hold|underweight|overweight|capex|debt|cash|inventory|volume"
    r"|driven by|leads to|supports|pressures|constrains|increases"
    r"|reduces|headwind|tailwind)\b)"
)

# ---------------------------------------------------------------------------
# Feature vocabularies (spec section "特征提取").
# ---------------------------------------------------------------------------

DOMAIN_ANCHOR_TERMS = (
    "the company",
    "revenue",
    "earnings",
    "margin",
    "guidance",
    "demand",
    "supply",
    "capex",
    "inventory",
    "valuation",
    "rates",
    "liquidity",
    "price",
    "volume",
    "market",
    "industry",
    "product",
    "customer",
    "semiconductor",
    "datacenter",
    "data center",
)
_DOMAIN_ANCHOR_PATTERN = _terms_pattern(DOMAIN_ANCHOR_TERMS)

EVENT_PREDICATE_TERMS = (
    # Bare "report"/"sign"/"signs" are deliberately excluded: they collide
    # too often with common noun usage ("the report", "signs of weakness")
    # to be a reliable event-predicate signal on their own.
    "reports",
    "reported",
    "reporting",
    "announce",
    "announces",
    "announced",
    "announcing",
    "launch",
    "launches",
    "launched",
    "launching",
    "introduce",
    "introduces",
    "introduced",
    "introducing",
    "signed",
    "signing",
    "acquire",
    "acquires",
    "acquired",
    "acquiring",
    "acquisition",
    "announcement",
    "raise guidance",
    "raises guidance",
    "raised guidance",
    "raising guidance",
    "cut guidance",
    "cuts guidance",
    "cutting guidance",
)
_EVENT_PATTERN = _terms_pattern(EVENT_PREDICATE_TERMS)

STATE_OR_CHANGE_TERMS = (
    "increase",
    "increases",
    "increased",
    "increasing",
    "decline",
    "declines",
    "declined",
    "declining",
    "accelerate",
    "accelerates",
    "accelerated",
    "accelerating",
    "acceleration",
    "decelerate",
    "decelerates",
    "decelerated",
    "decelerating",
    "deceleration",
    "slow",
    "slows",
    "slowed",
    "slowing",
    "remains elevated",
    "remained elevated",
    "remaining elevated",
    "improve",
    "improves",
    "improved",
    "improving",
    "weaken",
    "weakens",
    "weakened",
    "weakening",
    "weakness",
    "expand",
    "expands",
    "expanded",
    "expanding",
    "expansion",
    "contract",
    "contracts",
    "contracted",
    "contracting",
    "contraction",
    "grow",
    "grows",
    "grew",
    "growing",
    "growth",
    "broaden",
    "broadens",
    "broadened",
    "broadening",
    "recover",
    "recovers",
    "recovered",
    "recovering",
    "recovery",
    "normalize",
    "normalizes",
    "normalized",
    "normalizing",
    "stabilize",
    "stabilizes",
    "stabilized",
    "stabilizing",
    "stabilization",
    "deteriorate",
    "deteriorates",
    "deteriorated",
    "deteriorating",
    "deterioration",
    "widening",
    "narrowing",
    "turning upward",
    "turned upward",
    "turns upward",
    "turning downward",
    "turned downward",
    "turns downward",
    "rise",
    "rises",
    "rising",
    "rose",
    "fall",
    "falls",
    "falling",
    "fell",
    "trading above",
    "trading below",
    "paid down debt",
    "debt paydown",
    "doubled",
    "tripled",
    "more than double",
)
_STATE_CHANGE_PATTERN = _terms_pattern(STATE_OR_CHANGE_TERMS)

# "up 180%", "down 12% year over year", "up from $542 to $1,255": a
# directional adverb immediately anchored to a quantitative figure -- a very
# common financial-prose idiom for a magnitude move that no single fixed
# STATE_OR_CHANGE_TERMS phrase can enumerate (the actual number varies).
# Bounded to "up"/"down" followed (optionally through a short hedge word or
# connector) by a digit, so it does not fire on unrelated uses ("up to
# date", "signed up", "growing up") that are never followed by a number.
_MAGNITUDE_MOVE_PATTERN = re.compile(
    r"(?i)\b(?:up|down)\b\s+"
    r"(?:nearly\s+|almost\s+|over\s+|more\s+than\s+|about\s+|roughly\s+|from\s+|to\s+)?"
    r"\$?\d"
)

RISK_TERMS = (
    "risk",
    "risks",
    "downside",
    "headwind",
    "headwinds",
    "exposed to",
    "vulnerable to",
    "vulnerability",
    "creates risk",
    "poses a risk",
    "risk of",
    "warning sign",
    "warning signs",
    "underpriced",
    "overpriced",
    "contingent on",
    "volatility",
    "volatile",
    "drawdown",
    "maximum loss",
    "selloff",
    "sell-off",
    "distribution volume",
)
_RISK_PATTERN = _terms_pattern(RISK_TERMS)

DIRECTIONAL_TERMS = (
    "bullish",
    "bearish",
    "upside",
    "downside",
    "outperform",
    "underperform",
    "overweight",
    "underweight",
    "selling opportunity",
    "selling opportunities",
    "buying opportunity",
    "buying opportunities",
    "accumulation zone",
    "accumulation zones",
)
_DIRECTIONAL_PATTERN = _terms_pattern(DIRECTIONAL_TERMS)

_QUANTITATIVE_PATTERN = re.compile(r"\d|%|\$")
_INTERROGATIVE_MARK = "?"

# Relation-predicate detection reuses relation_grammar's own compiled
# vocabulary (presence-only -- this module never resolves endpoints, that
# stays the Structure Extractor's job) plus its CONFLICT_WORDS, so
# "does this text talk about a relationship" can never drift from the
# Structure Graph's own definition of a relation.
_RELATION_PATTERNS = (
    FORWARD_TRANSITIVE_CAUSAL_PATTERN,
    FORWARD_TRANSITIVE_SUPPORTIVE_PATTERN,
    FORWARD_MULTIWORD_PATTERN,
    REVERSE_MULTIWORD_PATTERN,
    REVERSE_PASSIVE_PATTERN,
)
_CONFLICT_WORDS_PATTERN = _terms_pattern(CONFLICT_WORDS)


def _has_relation_predicate(normalized: str) -> bool:
    return any(pattern.search(normalized) for pattern in _RELATION_PATTERNS) or bool(
        _CONFLICT_WORDS_PATTERN.search(normalized)
    )


# ---------------------------------------------------------------------------
# Result types
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class ClaimQualityFeatures:
    has_meta_commentary: bool
    has_transition_language: bool
    has_disclaimer: bool
    has_placeholder: bool
    has_external_subject: bool
    has_domain_anchor: bool
    has_quantitative_anchor: bool
    has_event_predicate: bool
    has_state_or_change_predicate: bool
    has_risk_or_forecast_predicate: bool
    has_relation_predicate: bool
    has_directional_signal: bool
    has_factor: bool
    has_entity: bool
    is_interrogative: bool

    def to_dict(self) -> dict[str, bool]:
        return asdict(self)


@dataclass(frozen=True)
class ClaimQualityResult:
    quality_class: str
    reason_codes: tuple[str, ...]
    features: ClaimQualityFeatures

    def to_dict(self) -> dict[str, Any]:
        return {
            "quality_class": self.quality_class,
            "reason_codes": list(self.reason_codes),
            "feature_flags": self.features.to_dict(),
        }


def _result(quality_class: str, reason_codes: tuple[str, ...], features: ClaimQualityFeatures) -> ClaimQualityResult:
    return ClaimQualityResult(quality_class=quality_class, reason_codes=reason_codes, features=features)


# ---------------------------------------------------------------------------
# Classifier
# ---------------------------------------------------------------------------


def classify_claim_quality(
    claim: Any,
    evidence: Any,
    *,
    entities: Any = None,
    factors: Any = None,
    direction: Any = None,
    assertion_status: Any = None,
) -> ClaimQualityResult:
    """Classify one claim into ANALYTICAL / CONTEXT_ONLY / NON_SUBSTANTIVE.

    ``entities``/``factors``/``direction``/``assertion_status`` are optional:
    when omitted, factors are recomputed from the text itself (via
    ``factor_normalizer.extract_known_factors_from_text``) so the function
    remains usable standalone, without requiring a caller to have already
    run the rest of the pipeline. ``assertion_status`` is accepted for
    interface completeness (spec's suggested signature) but is not itself a
    classification input -- assertion (asserted/negated/conditional) is
    orthogonal to substantive quality; a negated or conditional risk claim is
    still analytically meaningful.
    """
    claim_text = _collapse_whitespace(claim)
    combined = _combined_text(claim, evidence)
    is_interrogative = _INTERROGATIVE_MARK in combined
    normalized = normalize_text(combined)

    factor_list = list(factors) if factors else extract_known_factors_from_text(normalized)
    entity_list = list(entities) if entities else []

    has_domain_anchor = bool(_DOMAIN_ANCHOR_PATTERN.search(normalized))
    has_quantitative_anchor = bool(_QUANTITATIVE_PATTERN.search(normalized))
    has_event_predicate = bool(_EVENT_PATTERN.search(normalized))
    has_state_or_change_predicate = bool(_STATE_CHANGE_PATTERN.search(normalized)) or bool(
        _MAGNITUDE_MOVE_PATTERN.search(normalized)
    )
    has_relation_predicate = _has_relation_predicate(normalized)
    has_factor = bool(factor_list)
    has_entity = bool(entity_list)

    semantics = analyze_claim_semantics(combined)
    has_risk_or_forecast_predicate = (
        semantics.conditional
        or semantics.semantic_polarity in ("invalidation", "risk_relief")
        or bool(_RISK_PATTERN.search(normalized))
    )
    resolved_direction = normalize_direction(direction) if direction is not None else "unknown"
    has_text_directional_signal = bool(_DIRECTIONAL_PATTERN.search(normalized))
    has_directional_signal = resolved_direction in _POSITIVE_OR_NEGATIVE or has_text_directional_signal

    lowered = combined.lower()
    has_disclaimer = any(marker in lowered for marker in DISCLAIMER_MARKERS)
    has_meta_commentary = any(pattern.search(combined) for pattern in META_COMMENTARY_PATTERNS)
    has_transition_language = any(pattern.search(combined) for pattern in TRANSITION_PATTERNS)
    has_placeholder = _is_placeholder_text(claim_text)

    has_external_subject = has_domain_anchor or has_factor or has_entity
    analytical_signal = (
        has_state_or_change_predicate
        or has_risk_or_forecast_predicate
        or has_relation_predicate
        or has_directional_signal
    )
    # Text-only variant (excludes the `direction` field's own contribution
    # to has_directional_signal): used solely to decide whether a bare
    # heading/label fragment has independent content of its own. A stored
    # direction value inherited from the surrounding evidence context must
    # never, by itself, keep a content-free label fragment ("While FRED data
    # was unavailable, global news indicates:") out of the heading rule --
    # the same "never let an ambient, non-text-derived signal paper over an
    # empty fragment" principle already applied to has_any_substance above.
    text_only_analytical_signal = (
        has_state_or_change_predicate
        or has_risk_or_forecast_predicate
        or has_relation_predicate
        or has_text_directional_signal
    )
    # Broad "this claim carries some substantive signal at all" carve-out --
    # meta-commentary/transition patterns must never reject a sentence that
    # also states real content, however it starts. Deliberately built only
    # from TEXT-derived signals (never `has_entity`/`has_external_subject`):
    # `entities` always includes the run's own ticker regardless of whether
    # the text mentions it (see `structured_output_adapter.extract_entities`),
    # so a bare entity presence would make this carve-out fire for every
    # real claim -- including genuine meta-commentary like "Let me
    # synthesize everything." -- silently disabling the hard-reject checks
    # below whenever this function is called with a real record's entities.
    has_any_substance = (
        analytical_signal
        or has_event_predicate
        or has_quantitative_anchor
        or has_domain_anchor
        or has_factor
        or bool(_SUBSTANTIVE_SIGNAL_PATTERN.search(combined))
    )

    features = ClaimQualityFeatures(
        has_meta_commentary=has_meta_commentary,
        has_transition_language=has_transition_language,
        has_disclaimer=has_disclaimer,
        has_placeholder=has_placeholder,
        has_external_subject=has_external_subject,
        has_domain_anchor=has_domain_anchor,
        has_quantitative_anchor=has_quantitative_anchor,
        has_event_predicate=has_event_predicate,
        has_state_or_change_predicate=has_state_or_change_predicate,
        has_risk_or_forecast_predicate=has_risk_or_forecast_predicate,
        has_relation_predicate=has_relation_predicate,
        has_directional_signal=has_directional_signal,
        has_factor=has_factor,
        has_entity=has_entity,
        is_interrogative=is_interrogative,
    )

    # 1. NON_SUBSTANTIVE hard rejects, in priority order.
    if has_placeholder:
        return _result(QUALITY_NON_SUBSTANTIVE, (REASON_PLACEHOLDER_UNKNOWN,), features)
    if has_disclaimer:
        return _result(QUALITY_NON_SUBSTANTIVE, (REASON_DISCLAIMER_ONLY,), features)
    if _is_bare_heading_fragment(
        claim_text,
        has_quantitative_anchor=has_quantitative_anchor,
        analytical_signal=text_only_analytical_signal,
    ):
        return _result(QUALITY_NON_SUBSTANTIVE, (REASON_BARE_HEADING_OR_LABEL,), features)
    if has_meta_commentary and not has_any_substance:
        return _result(QUALITY_NON_SUBSTANTIVE, (REASON_BOILERPLATE_META_COMMENTARY,), features)
    if has_transition_language and not has_any_substance:
        return _result(QUALITY_NON_SUBSTANTIVE, (REASON_NON_ASSERTIVE_TRANSITION,), features)

    # 2. ANALYTICAL: external/domain subject + at least one analytical signal.
    if has_external_subject and analytical_signal:
        reasons: list[str] = []
        if has_relation_predicate:
            reasons.append(REASON_ANALYTICAL_RELATION_SIGNAL)
        if has_state_or_change_predicate:
            reasons.append(REASON_ANALYTICAL_STATE_OR_CHANGE_SIGNAL)
        if has_risk_or_forecast_predicate:
            reasons.append(REASON_ANALYTICAL_RISK_OR_FORECAST_SIGNAL)
        if has_directional_signal:
            reasons.append(REASON_ANALYTICAL_DIRECTIONAL_SIGNAL)
        return _result(QUALITY_ANALYTICAL, tuple(reasons), features)

    # 3. CONTEXT_ONLY: has an external/domain subject but no analytical
    # signal. Deliberately not restricted to the `has_event_predicate` verb
    # list: real agent reports assert genuine, substantive facts in far more
    # forms than that fixed vocabulary could ever enumerate (a bare price
    # print, a technical-indicator reading, a balance-sheet figure, an
    # analyst-rating change, a company description, a quoted deal headline)
    # -- none of these are process language (already ruled out above by the
    # meta-commentary/transition/disclaimer/placeholder checks), so once a
    # real external subject is established, the fact stands as CONTEXT_ONLY
    # on its own rather than being forced through a second, narrower
    # vocabulary gate. `has_event_predicate` is still computed and exposed
    # in `feature_flags` for audit, it is just no longer a required gate.
    if has_external_subject:
        return _result(QUALITY_CONTEXT_ONLY, (REASON_CONTEXT_ONLY_FACTUAL_ASSERTION,), features)

    # 4. Conservative default: no external/domain subject at all (no
    # anchor term, no resolved factor, no entity) -- genuinely subject-less
    # fragments only.
    return _result(QUALITY_NON_SUBSTANTIVE, (REASON_NO_EXTERNAL_ASSERTION,), features)


# ---------------------------------------------------------------------------
# Shared downstream eligibility matrix
# ---------------------------------------------------------------------------


def _resolve_quality_class(record: Mapping[str, Any]) -> str:
    """Prefer an already-stamped ``claim_quality`` (the adapter's own
    classification, computed once with full context); fall back to a fresh,
    lazy classification for records that predate this gate (e.g. historical
    artifacts read back during a replay) -- always a pure function of the
    record's own already-persisted fields, so this can never require a
    historical artifact write."""
    stamped = record.get("claim_quality") if isinstance(record, Mapping) else None
    if isinstance(stamped, str) and stamped.strip().lower() in VALID_QUALITY_CLASSES:
        return stamped.strip().lower()
    result = classify_claim_quality(
        record.get("claim") if isinstance(record, Mapping) else None,
        record.get("evidence") if isinstance(record, Mapping) else None,
        entities=record.get("entities") if isinstance(record, Mapping) else None,
        factors=record.get("factors") if isinstance(record, Mapping) else None,
        direction=record.get("direction") if isinstance(record, Mapping) else None,
        assertion_status=record.get("assertion_status") if isinstance(record, Mapping) else None,
    )
    return result.quality_class


def is_claim_eligible(
    record: Mapping[str, Any],
    consumer: str,
    *,
    has_relation_candidate: bool = False,
) -> bool:
    """Single shared gate every downstream consumer calls -- no module may
    maintain its own separate quality judgment.

    ``consumer`` is one of :data:`VALID_CONSUMERS`. ``has_relation_candidate``
    is the one fact only the Structure Extractor itself can supply (whether
    *this specific claim's* evidence and resolved factors produced a legal
    relation candidate) -- it is ignored for every consumer except
    ``"structure"`` on a CONTEXT_ONLY claim.

    Eligibility matrix (spec "下游资格矩阵"):

    =============  ===========  ===========================================  ===========
    consumer       ANALYTICAL   CONTEXT_ONLY                                  NON_SUBSTANTIVE
    =============  ===========  ===========================================  ===========
    mapping        Yes          Yes (factor/Alpha context)                    No
    structure      Yes          only if a legal relation was found             No
    activation     Yes          No                                             No
    conflict       Yes          No                                             No
    product_findings  Yes       No (default hidden)                           No
    analytical_persistence  Yes Yes (tagged context_only)                     No
    =============  ===========  ===========================================  ===========

    ANALYTICAL is unconditionally eligible for every consumer, including
    activation/conflict: a claim's own generic ``direction`` field
    (``infer_direction()``'s word-counting heuristic) is not re-checked here
    as a second gate. Whether -- and how strongly -- an analytical claim's
    evidence actually counts toward one specific alpha's Activation score or
    a Conflict pair is already decided by the existing, frozen, alpha-
    relative ``relation`` field (activation/conditional/mixed vs.
    invalidation/risk_relief/mention) that both Activation formulas and the
    Conflict Detector score on unchanged -- a coarser, alpha-agnostic
    direction re-check on top of that would only ever be redundant (a claim
    the frozen formula already treats as real evidence) or actively wrong (a
    genuinely-matched, genuinely-substantive claim whose standalone sentiment
    heuristic simply does not happen to contain a bullish/bearish word).
    Concretely demonstrated against real pipeline fixtures during this
    Sprint: the QQQ Golden Closure's Liquidity Expansion evidence and the
    NVDA sanity fixture's Datacenter CapEx/Semiconductor Cycle evidence are
    both real, correctly-matched, `relation="activation"` claims whose
    `direction` resolves to "neutral"/"unknown" -- excluding them broke two
    existing, must-pass end-to-end tests for no analytical benefit.
    """
    if consumer not in VALID_CONSUMERS:
        raise ValueError(f"unknown consumer: {consumer!r}")

    quality = _resolve_quality_class(record)
    if quality == QUALITY_NON_SUBSTANTIVE:
        return False

    if quality == QUALITY_ANALYTICAL:
        return True

    if quality == QUALITY_CONTEXT_ONLY:
        if consumer == CONSUMER_MAPPING:
            return True
        if consumer == CONSUMER_STRUCTURE:
            return bool(has_relation_candidate)
        # activation, conflict, product_findings (default hidden): No.
        return consumer == CONSUMER_ANALYTICAL_PERSISTENCE

    return False
