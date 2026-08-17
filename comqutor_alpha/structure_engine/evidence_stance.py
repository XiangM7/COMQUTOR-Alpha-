"""Alpha-relative Evidence Stance Classification (Sprint 2, Track B1).

Every existing semantic field COMQUTOR already computes is claim-global: it
describes one claim's own language, independent of which Alpha is being
asked about.

  * ``direction`` (claim_semantics / structured adapter) -- positive /
    negative / neutral, a property of the sentence alone.
  * ``semantic_polarity`` (claim_semantics.analyze_claim_semantics) --
    activation / invalidation / risk_relief / mention / mixed / unknown, also
    computed from the claim's own text alone (``analyze_claim_semantics``
    never takes an ``alpha_id`` argument).
  * ``relation`` (claim_semantics.alpha_relation) -- the closest existing
    field to being Alpha-relative (it does take an ``alpha_id``), but it
    exists to feed the Alpha Mapper's *admission and scoring* formula, which
    this Sprint is explicitly forbidden from touching. Its vocabulary
    (activation / invalidation / risk_relief / conditional / mixed /
    mention) is deliberately narrow -- calibrated for scoring stability, not
    for expressing "this evidence rebuts this Alpha's thesis in plain
    English." John's own fixed example proves the gap directly:
    ``alpha_relation("The valuation risk argument is a lazy heuristic that
    ignores the actual numbers.", "A304")`` returns ``"activation"`` --
    exactly backwards -- because no existing pattern recognizes a rebuttal
    phrased as a meta-critique of the risk argument itself, only surface
    valuation-relief phrasing (falling multiples, easing discount rates).

None of these three fields can be bound to a specific *other* candidate
Alpha at the same time: the same claim ("AI demand remains strong, but most
of the benefit is already priced in.") must be able to read as opposing
A101 (AI Expansion) while simultaneously supporting A304 (Multiple
Compression) -- two different verdicts for the same sentence, keyed by
which Alpha is being asked about. A single claim-level field cannot hold
two answers at once. Evidence Stance is therefore always a function of
``(claim_id, target_alpha_id)``, never of the claim alone, and every result
is bound explicitly to ``target_alpha_id`` and (when the stance is
``supports_counter_alpha``) ``counter_alpha_id``.

This module is a pure, additive, deterministic *shadow* layer:
  * it never re-scores, re-admits, or re-groups anything;
  * it reuses ``claim_semantics.alpha_relation`` / ``analyze_claim_semantics``
    and ``claim_quality.classify_claim_quality`` as its foundation rather
    than re-implementing sentence-level semantics;
  * it reuses the taxonomy's own ``conflict_alphas`` registry
    (``alpha_schema.AlphaDefinition.conflict_alphas``) as the *only* source
    of canonical counter-Alpha pairs -- it never maintains a second list;
  * it must never be imported by, or feed a value back into,
    ``claim_semantics`` / ``claim_quality`` / ``alpha_mapper`` scoring --
    callers (Alpha Mapper) import this module, never the reverse, so no
    admission or score computation can ever depend on a stance result.
"""

from __future__ import annotations

import re
from collections.abc import Mapping
from dataclasses import asdict, dataclass
from typing import Any

from comqutor_alpha.alpha_library.alpha_schema import AlphaDefinition
from comqutor_alpha.structure_engine.claim_quality import (
    QUALITY_ANALYTICAL,
    QUALITY_CONTEXT_ONLY,
    QUALITY_NON_SUBSTANTIVE,
    classify_claim_quality,
)
from comqutor_alpha.structure_engine.claim_semantics import (
    OPPORTUNITY_ALPHA_IDS,
    RISK_ALPHA_IDS,
    VALID_ASSERTION_STATUSES,
    VALID_SEMANTIC_POLARITIES,
    alpha_relation,
    analyze_claim_semantics,
)
from comqutor_alpha.structure_engine.factor_normalizer import normalize_text, term_in_text

CLASSIFIER_VERSION = "evidence_stance.deterministic.v1"

# ---------------------------------------------------------------------------
# Public enum: the five stances (section 5)
# ---------------------------------------------------------------------------
SUPPORTS_ALPHA = "supports_alpha"
OPPOSES_ALPHA = "opposes_alpha"
MENTIONS_ALPHA = "mentions_alpha"
NEUTRAL_BACKGROUND = "neutral_background"
SUPPORTS_COUNTER_ALPHA = "supports_counter_alpha"

VALID_EVIDENCE_STANCES = frozenset(
    {SUPPORTS_ALPHA, OPPOSES_ALPHA, MENTIONS_ALPHA, NEUTRAL_BACKGROUND, SUPPORTS_COUNTER_ALPHA}
)

# ---------------------------------------------------------------------------
# Confidence bands (section 9) -- three coarse bands only, never a fake
# two-decimal score.
# ---------------------------------------------------------------------------
CONFIDENCE_HIGH = "high"
CONFIDENCE_MEDIUM = "medium"
CONFIDENCE_LOW = "low"
VALID_CONFIDENCE_BANDS = frozenset({CONFIDENCE_HIGH, CONFIDENCE_MEDIUM, CONFIDENCE_LOW})

# ---------------------------------------------------------------------------
# Reason codes (section 7) -- a single centralized, testable vocabulary.
# ---------------------------------------------------------------------------
REASON_SUPPORTS_TARGET_THESIS = "SUPPORTS_TARGET_THESIS"
REASON_SUPPORTS_TARGET_TRIGGER = "SUPPORTS_TARGET_TRIGGER"
REASON_SUPPORTS_TARGET_CONFIRMATION = "SUPPORTS_TARGET_CONFIRMATION"
REASON_RISK_ALPHA_ACTIVATION = "RISK_ALPHA_ACTIVATION"
REASON_OPPORTUNITY_ALPHA_ACTIVATION = "OPPORTUNITY_ALPHA_ACTIVATION"

REASON_EXPLICIT_REBUTTAL_OF_TARGET_ALPHA = "EXPLICIT_REBUTTAL_OF_TARGET_ALPHA"
REASON_EXPLICIT_NEGATION_OF_TARGET_ALPHA = "EXPLICIT_NEGATION_OF_TARGET_ALPHA"
REASON_INVALIDATION_OF_OPPORTUNITY_ALPHA = "INVALIDATION_OF_OPPORTUNITY_ALPHA"
REASON_RISK_RELIEF_OPPOSES_RISK_ALPHA = "RISK_RELIEF_OPPOSES_RISK_ALPHA"
REASON_ALREADY_PRICED_IN_OPPOSES_UPSIDE_ALPHA = "ALREADY_PRICED_IN_OPPOSES_UPSIDE_ALPHA"
REASON_WEAKENS_TARGET_CAUSAL_CHAIN = "WEAKENS_TARGET_CAUSAL_CHAIN"

REASON_MENTION_ONLY = "MENTION_ONLY"
REASON_GENERIC_BACKGROUND = "GENERIC_BACKGROUND"
REASON_CONTEXT_ONLY = "CONTEXT_ONLY"
REASON_NON_SUBSTANTIVE = "NON_SUBSTANTIVE"

REASON_CANONICAL_COUNTER_ALPHA_SUPPORTED = "CANONICAL_COUNTER_ALPHA_SUPPORTED"
REASON_COUNTER_ALPHA_NOT_CANONICAL = "COUNTER_ALPHA_NOT_CANONICAL"

REASON_CONDITIONAL_SUPPORT = "CONDITIONAL_SUPPORT"
REASON_CONDITIONAL_OPPOSITION = "CONDITIONAL_OPPOSITION"
REASON_MIXED_STANCE_UNRESOLVED = "MIXED_STANCE_UNRESOLVED"
REASON_INSUFFICIENT_ALPHA_RELATIVE_SEMANTICS = "INSUFFICIENT_ALPHA_RELATIVE_SEMANTICS"
REASON_NO_TARGET_ALPHA = "NO_TARGET_ALPHA"
REASON_UNKNOWN_ALPHA = "UNKNOWN_ALPHA"
REASON_LOW_CLASSIFICATION_CERTAINTY = "LOW_CLASSIFICATION_CERTAINTY"

VALID_REASON_CODES = frozenset(
    {
        REASON_SUPPORTS_TARGET_THESIS,
        REASON_SUPPORTS_TARGET_TRIGGER,
        REASON_SUPPORTS_TARGET_CONFIRMATION,
        REASON_RISK_ALPHA_ACTIVATION,
        REASON_OPPORTUNITY_ALPHA_ACTIVATION,
        REASON_EXPLICIT_REBUTTAL_OF_TARGET_ALPHA,
        REASON_EXPLICIT_NEGATION_OF_TARGET_ALPHA,
        REASON_INVALIDATION_OF_OPPORTUNITY_ALPHA,
        REASON_RISK_RELIEF_OPPOSES_RISK_ALPHA,
        REASON_ALREADY_PRICED_IN_OPPOSES_UPSIDE_ALPHA,
        REASON_WEAKENS_TARGET_CAUSAL_CHAIN,
        REASON_MENTION_ONLY,
        REASON_GENERIC_BACKGROUND,
        REASON_CONTEXT_ONLY,
        REASON_NON_SUBSTANTIVE,
        REASON_CANONICAL_COUNTER_ALPHA_SUPPORTED,
        REASON_COUNTER_ALPHA_NOT_CANONICAL,
        REASON_CONDITIONAL_SUPPORT,
        REASON_CONDITIONAL_OPPOSITION,
        REASON_MIXED_STANCE_UNRESOLVED,
        REASON_INSUFFICIENT_ALPHA_RELATIVE_SEMANTICS,
        REASON_NO_TARGET_ALPHA,
        REASON_UNKNOWN_ALPHA,
        REASON_LOW_CLASSIFICATION_CERTAINTY,
    }
)

# ---------------------------------------------------------------------------
# New, Evidence-Stance-only pattern layer (section 8.3). These are additive
# to -- never a replacement for -- claim_semantics.py's own (frozen,
# scoring-facing) patterns. They exist specifically to catch phrasing the
# scoring-calibrated patterns were never designed to catch, such as John's
# fixed example ("a lazy heuristic that ignores the actual numbers") and
# "already priced in" -- both of which alpha_relation() resolves to plain
# "activation" today (verified empirically; see the module docstring).
# ---------------------------------------------------------------------------

# Direct, explicit rebuttal of whatever proposition the target Alpha's
# concept is bound up in ("the valuation risk argument is a lazy heuristic
# that ignores the actual numbers"). Each entry only fires when the claim
# text is already topical for the target Alpha (see `_is_topical`) --
# section 8.3's "必须验证其作用对象是 target Alpha" requirement.
_EXPLICIT_REBUTTAL_PATTERNS: tuple[tuple[re.Pattern[str], str], ...] = (
    (re.compile(r"\blazy heuristic\b"), REASON_EXPLICIT_REBUTTAL_OF_TARGET_ALPHA),
    (re.compile(r"\bignores? the actual numbers\b"), REASON_EXPLICIT_REBUTTAL_OF_TARGET_ALPHA),
    (re.compile(r"\boverstated\b"), REASON_EXPLICIT_REBUTTAL_OF_TARGET_ALPHA),
    (re.compile(r"\bnot supported by the (?:data|numbers|evidence|facts)\b"), REASON_EXPLICIT_REBUTTAL_OF_TARGET_ALPHA),
    (re.compile(r"\bis (?:flawed|unfounded|a myth|a misread)\b"), REASON_EXPLICIT_REBUTTAL_OF_TARGET_ALPHA),
    (re.compile(r"\bdoes(?:n.t| not) hold up\b"), REASON_EXPLICIT_REBUTTAL_OF_TARGET_ALPHA),
    (re.compile(r"\bfails? to account for\b"), REASON_WEAKENS_TARGET_CAUSAL_CHAIN),
    (re.compile(r"\bdoes not imply\b"), REASON_EXPLICIT_NEGATION_OF_TARGET_ALPHA),
    (re.compile(r"\bno evidence (?:that|of|for)\b"), REASON_EXPLICIT_NEGATION_OF_TARGET_ALPHA),
    (re.compile(r"\bunlikely to\b"), REASON_EXPLICIT_NEGATION_OF_TARGET_ALPHA),
    (re.compile(r"\balready (?:fully |mostly )?priced in\b"), REASON_ALREADY_PRICED_IN_OPPOSES_UPSIDE_ALPHA),
)

# Reporting-only verb constructions ("management discussed X during the
# call") -- a claim can be quality-analytical (e.g. because it happens to
# contain a RISK_TERMS word like "risk") while still being a pure mention
# with no supporting or opposing proposition of its own. Section 5.3.
_MENTION_REPORTING_PATTERN = re.compile(
    r"\b(?:discussed|was mentioned|is mentioned|merely mentions|"
    r"touched on|brought up|noted in passing|referenced)\b"
)

# A broader (Evidence-Stance-only) risk-easing detector than
# claim_semantics.recession_risk_is_relief/valuation_risk_is_relief, which
# both require the risk noun to appear in singular form immediately before
# the easing verb ("recession risk is easing") and therefore miss the
# equally common plural phrasing ("recession risks are easing"). Only
# applied when the target Alpha is itself a risk Alpha and the text is
# already topical for it.
_RISK_EASING_PATTERN = re.compile(
    r"\b(?:risk|risks|probability|spreads?)\b\s*(?:are|is|remains?|stay|stays)?\s*"
    r"(?:easing|falling|declining|receding|contained|limited|low|lower|fading|diminishing|narrowing|tightening)\b"
)

# The Opportunity-Alpha analog: a causal driver of the target Alpha's own
# thesis explicitly weakening ("capex is slowing", "GPU demand is
# weakening"). claim_semantics._INVALIDATION_PATTERN requires the noun and
# verb to sit directly adjacent ("demand weakens") and therefore misses the
# equally common continuous/copula phrasing ("demand is weakening").
_OPPORTUNITY_WEAKENING_PATTERN = re.compile(
    r"\b(?:capex|demand|spending|growth|orders|bookings|revenue|shipments)\b\s*"
    r"(?:is|are|remains?|stay|stays)?\s*(?:slowing|weakening|declining|falling|contracting|deteriorating|cooling|softening)\b"
)


@dataclass(frozen=True)
class EvidenceStanceResult:
    target_alpha_id: str | None
    evidence_stance: str | None
    counter_alpha_id: str | None
    stance_reason_codes: tuple[str, ...]
    stance_confidence_band: str | None
    requires_manual_review: bool
    classification_method: str
    source_relation: str | None
    source_assertion_status: str | None
    source_semantic_polarity: str | None

    def to_dict(self) -> dict[str, Any]:
        data = asdict(self)
        data["stance_reason_codes"] = list(self.stance_reason_codes)
        return data


def _claim_evidence_text(record: Mapping[str, Any]) -> str:
    claim = str(record.get("claim") or "").strip() if isinstance(record, Mapping) else ""
    evidence = str(record.get("evidence") or "").strip() if isinstance(record, Mapping) else ""
    if not evidence or normalize_text(evidence) == normalize_text(claim):
        return claim
    return f"{claim} {evidence}"


def _alpha_topic_terms(alpha: AlphaDefinition) -> tuple[str, ...]:
    return tuple(
        str(term)
        for term in (*alpha.keywords, *alpha.trigger_signals, *alpha.confirmation_signals)
        if str(term or "").strip()
    )


def _is_topical(normalized_text: str, alpha: AlphaDefinition, candidate: Mapping[str, Any] | None) -> bool:
    """Whether the claim text is about the target Alpha's own concept at
    all. Prefers the caller's already-computed candidate keyword/factor
    scores (Alpha Mapper's own values -- single source of truth, no
    recomputation/drift); falls back to an independent, self-contained
    keyword check for standalone use (e.g. classifier unit tests called
    without going through the Mapper)."""
    if candidate is not None:
        try:
            keyword_score = float(candidate.get("keyword_score") or 0.0)
        except (TypeError, ValueError):
            keyword_score = 0.0
        try:
            factor_score = float(candidate.get("factor_score") or 0.0)
        except (TypeError, ValueError):
            factor_score = 0.0
        return keyword_score > 0.0 or factor_score > 0.0
    return any(term_in_text(normalize_text(term), normalized_text) for term in _alpha_topic_terms(alpha))


def _match_explicit_rebuttal(normalized_text: str) -> str | None:
    for pattern, reason in _EXPLICIT_REBUTTAL_PATTERNS:
        if pattern.search(normalized_text):
            return reason
    return None


def canonical_conflict_partners(alpha_id: str, taxonomy: Mapping[str, AlphaDefinition]) -> frozenset[str]:
    """The canonical conflict registry, reused verbatim: taxonomy
    conflict_alphas lists are not guaranteed symmetric in the source YAML
    (e.g. A101 -> A304 is declared, and A304 -> A101 is *also* declared
    independently), so this checks both declaration directions rather than
    assuming symmetry or maintaining a second pair list.

    Public (Sprint 2, Track B1 LLM upgrade): the same, single canonical
    counter-Alpha source both ``classify_evidence_stance`` below and
    ``evidence_stance_llm``'s program-side counter-Alpha legality check
    (task spec section 13.C) read -- never a second conflict registry.
    """
    partners: set[str] = set()
    alpha = taxonomy.get(alpha_id)
    if alpha is not None:
        partners.update(conflict.alpha_id for conflict in alpha.conflict_alphas)
    for other_id, other in taxonomy.items():
        if other_id == alpha_id:
            continue
        if any(conflict.alpha_id == alpha_id for conflict in other.conflict_alphas):
            partners.add(other_id)
    return frozenset(partners)


def _support_reason(alpha: AlphaDefinition, normalized_text: str) -> str:
    if any(term_in_text(normalize_text(term), normalized_text) for term in alpha.trigger_signals):
        return REASON_SUPPORTS_TARGET_TRIGGER
    if any(term_in_text(normalize_text(term), normalized_text) for term in alpha.confirmation_signals):
        return REASON_SUPPORTS_TARGET_CONFIRMATION
    if alpha.alpha_id in RISK_ALPHA_IDS:
        return REASON_RISK_ALPHA_ACTIVATION
    if alpha.alpha_id in OPPORTUNITY_ALPHA_IDS:
        return REASON_OPPORTUNITY_ALPHA_ACTIVATION
    return REASON_SUPPORTS_TARGET_THESIS


def _resolve_quality_class(record: Mapping[str, Any]) -> str:
    stamped = record.get("claim_quality") if isinstance(record, Mapping) else None
    if isinstance(stamped, str) and stamped.strip().lower() in {
        QUALITY_ANALYTICAL,
        QUALITY_CONTEXT_ONLY,
        QUALITY_NON_SUBSTANTIVE,
    }:
        return stamped.strip().lower()
    result = classify_claim_quality(
        record.get("claim") if isinstance(record, Mapping) else None,
        record.get("evidence") if isinstance(record, Mapping) else None,
        entities=record.get("entities") if isinstance(record, Mapping) else None,
        factors=record.get("factors") if isinstance(record, Mapping) else None,
        direction=record.get("direction") if isinstance(record, Mapping) else None,
    )
    return result.quality_class


def classify_evidence_stance(
    *,
    record: Mapping[str, Any],
    target_alpha_id: str,
    candidate: Mapping[str, Any] | None,
    taxonomy: Mapping[str, AlphaDefinition],
) -> EvidenceStanceResult:
    """Classify one claim's stance toward one specific ``target_alpha_id``.

    Deterministic and side-effect-free: never recomputes/overrides Alpha
    Mapper admission or scoring, never re-groups Evidence Facts. See the
    module docstring for why this must be keyed on (claim, target_alpha_id)
    rather than being a claim-global field, and the precedence walked
    through step-by-step below matches the task spec's section 8 ordering.
    """
    normalized_target = str(target_alpha_id or "").strip()

    def _finish(
        stance: str | None,
        reasons: list[str],
        band: str | None,
        manual_review: bool,
        *,
        counter: str | None = None,
        relation: str | None = None,
        assertion_status: str | None = None,
        semantic_polarity: str | None = None,
    ) -> EvidenceStanceResult:
        if band == CONFIDENCE_LOW:
            manual_review = True
        return EvidenceStanceResult(
            target_alpha_id=normalized_target or None,
            evidence_stance=stance,
            counter_alpha_id=counter,
            stance_reason_codes=tuple(reasons),
            stance_confidence_band=band,
            requires_manual_review=bool(manual_review),
            classification_method=CLASSIFIER_VERSION,
            source_relation=relation,
            source_assertion_status=assertion_status,
            source_semantic_polarity=semantic_polarity,
        )

    # --- 8.1 input validity -------------------------------------------------
    if not normalized_target:
        return _finish(None, [REASON_NO_TARGET_ALPHA], None, False)

    alpha_def = taxonomy.get(normalized_target) if taxonomy else None
    if alpha_def is None:
        return _finish(None, [REASON_UNKNOWN_ALPHA], None, True)

    text = _claim_evidence_text(record)
    normalized_text = normalize_text(text)
    semantics = analyze_claim_semantics(text)

    stamped_relation = str((candidate or {}).get("relation") or "").strip().lower() if candidate else ""
    relation = stamped_relation or alpha_relation(text, normalized_target)

    stamped_assertion = record.get("assertion_status") if isinstance(record, Mapping) else None
    source_assertion_status = (
        stamped_assertion if stamped_assertion in VALID_ASSERTION_STATUSES else semantics.assertion_status
    )
    stamped_polarity = record.get("semantic_polarity") if isinstance(record, Mapping) else None
    source_semantic_polarity = (
        stamped_polarity if stamped_polarity in VALID_SEMANTIC_POLARITIES else semantics.semantic_polarity
    )

    common = {"relation": relation, "assertion_status": source_assertion_status, "semantic_polarity": source_semantic_polarity}

    if not normalized_text:
        return _finish(NEUTRAL_BACKGROUND, [REASON_NON_SUBSTANTIVE], CONFIDENCE_HIGH, False, **common)

    quality_class = _resolve_quality_class(record)
    topical = _is_topical(normalized_text, alpha_def, candidate)

    # --- 8.2 (hard reject only) --------------------------------------------
    if quality_class == QUALITY_NON_SUBSTANTIVE:
        return _finish(NEUTRAL_BACKGROUND, [REASON_NON_SUBSTANTIVE], CONFIDENCE_HIGH, False, **common)

    # --- 8.3 explicit opposition / negation (highest priority among
    # substantive claims -- intentionally checked BEFORE the context_only
    # downgrade below, since a context-only-tagged claim can still carry a
    # complete, verifiable rebuttal the quality label must not paper over) --
    if topical:
        rebuttal_reason = _match_explicit_rebuttal(normalized_text)
        if rebuttal_reason:
            return _finish(OPPOSES_ALPHA, [rebuttal_reason], CONFIDENCE_HIGH, False, **common)
        if normalized_target in RISK_ALPHA_IDS and _RISK_EASING_PATTERN.search(normalized_text):
            return _finish(OPPOSES_ALPHA, [REASON_RISK_RELIEF_OPPOSES_RISK_ALPHA], CONFIDENCE_HIGH, False, **common)
        if normalized_target in OPPORTUNITY_ALPHA_IDS and _OPPORTUNITY_WEAKENING_PATTERN.search(normalized_text):
            return _finish(OPPOSES_ALPHA, [REASON_WEAKENS_TARGET_CAUSAL_CHAIN], CONFIDENCE_HIGH, False, **common)
        if _MENTION_REPORTING_PATTERN.search(normalized_text):
            return _finish(MENTIONS_ALPHA, [REASON_MENTION_ONLY], CONFIDENCE_HIGH, False, **common)

    # --- context_only downgrade (not overridden above) ---------------------
    if quality_class == QUALITY_CONTEXT_ONLY:
        return _finish(NEUTRAL_BACKGROUND, [REASON_CONTEXT_ONLY], CONFIDENCE_HIGH, False, **common)

    # --- 8.4 existing structural relation semantics -------------------------
    if relation == "risk_relief" and normalized_target in RISK_ALPHA_IDS:
        return _finish(OPPOSES_ALPHA, [REASON_RISK_RELIEF_OPPOSES_RISK_ALPHA], CONFIDENCE_HIGH, False, **common)
    if relation == "invalidation":
        return _finish(OPPOSES_ALPHA, [REASON_INVALIDATION_OF_OPPORTUNITY_ALPHA], CONFIDENCE_HIGH, False, **common)
    if relation == "mention":
        return _finish(MENTIONS_ALPHA, [REASON_MENTION_ONLY], CONFIDENCE_HIGH, False, **common)
    if relation == "mixed" or semantics.mixed:
        return _finish(NEUTRAL_BACKGROUND, [REASON_MIXED_STANCE_UNRESOLVED], CONFIDENCE_LOW, True, **common)
    if relation == "conditional":
        if semantics.negated:
            return _finish(OPPOSES_ALPHA, [REASON_CONDITIONAL_OPPOSITION], CONFIDENCE_MEDIUM, True, **common)
        return _finish(SUPPORTS_ALPHA, [REASON_CONDITIONAL_SUPPORT], CONFIDENCE_MEDIUM, True, **common)

    # --- 8.5 / 8.6 activation-default bucket --------------------------------
    matched_alpha = str(record.get("matched_alpha") or "").strip() if isinstance(record, Mapping) else ""
    if matched_alpha and matched_alpha != normalized_target:
        partners = canonical_conflict_partners(matched_alpha, taxonomy)
        if normalized_target in partners:
            return _finish(
                SUPPORTS_COUNTER_ALPHA,
                [REASON_CANONICAL_COUNTER_ALPHA_SUPPORTED],
                CONFIDENCE_MEDIUM,
                False,
                counter=matched_alpha,
                **common,
            )
        return _finish(
            MENTIONS_ALPHA if topical else NEUTRAL_BACKGROUND,
            [REASON_COUNTER_ALPHA_NOT_CANONICAL, REASON_INSUFFICIENT_ALPHA_RELATIVE_SEMANTICS],
            CONFIDENCE_LOW,
            True,
            **common,
        )

    if topical:
        return _finish(SUPPORTS_ALPHA, [_support_reason(alpha_def, normalized_text)], CONFIDENCE_HIGH, False, **common)

    return _finish(NEUTRAL_BACKGROUND, [REASON_GENERIC_BACKGROUND], CONFIDENCE_LOW, True, **common)


__all__ = [
    "CLASSIFIER_VERSION",
    "SUPPORTS_ALPHA",
    "OPPOSES_ALPHA",
    "MENTIONS_ALPHA",
    "NEUTRAL_BACKGROUND",
    "SUPPORTS_COUNTER_ALPHA",
    "VALID_EVIDENCE_STANCES",
    "CONFIDENCE_HIGH",
    "CONFIDENCE_MEDIUM",
    "CONFIDENCE_LOW",
    "VALID_CONFIDENCE_BANDS",
    "REASON_SUPPORTS_TARGET_THESIS",
    "REASON_SUPPORTS_TARGET_TRIGGER",
    "REASON_SUPPORTS_TARGET_CONFIRMATION",
    "REASON_RISK_ALPHA_ACTIVATION",
    "REASON_OPPORTUNITY_ALPHA_ACTIVATION",
    "REASON_EXPLICIT_REBUTTAL_OF_TARGET_ALPHA",
    "REASON_EXPLICIT_NEGATION_OF_TARGET_ALPHA",
    "REASON_INVALIDATION_OF_OPPORTUNITY_ALPHA",
    "REASON_RISK_RELIEF_OPPOSES_RISK_ALPHA",
    "REASON_ALREADY_PRICED_IN_OPPOSES_UPSIDE_ALPHA",
    "REASON_WEAKENS_TARGET_CAUSAL_CHAIN",
    "REASON_MENTION_ONLY",
    "REASON_GENERIC_BACKGROUND",
    "REASON_CONTEXT_ONLY",
    "REASON_NON_SUBSTANTIVE",
    "REASON_CANONICAL_COUNTER_ALPHA_SUPPORTED",
    "REASON_COUNTER_ALPHA_NOT_CANONICAL",
    "REASON_CONDITIONAL_SUPPORT",
    "REASON_CONDITIONAL_OPPOSITION",
    "REASON_MIXED_STANCE_UNRESOLVED",
    "REASON_INSUFFICIENT_ALPHA_RELATIVE_SEMANTICS",
    "REASON_NO_TARGET_ALPHA",
    "REASON_UNKNOWN_ALPHA",
    "REASON_LOW_CLASSIFICATION_CERTAINTY",
    "VALID_REASON_CODES",
    "EvidenceStanceResult",
    "classify_evidence_stance",
    "canonical_conflict_partners",
]
