"""B4 Active/Dominant/Regime-level logic alignment -- the single,
deterministic, authoritative final Alpha classifier (task
B4_ACTIVATION_LEVEL_ALIGNMENT).

Not a new Activation scorer: this module never recomputes
``activation_score``/``uncapped_score``, never re-groups Evidence Facts,
never re-evaluates the regime gate, and never recomputes B3 Entity
Exposure. It consumes each of those already-computed, already-authoritative
results exactly once and resolves them into one final, auditable
classification per the deterministic order John specified:

    target_level   -- what the score alone (preferring the *uncapped*
                       score, so a qualification ceiling can never hide
                       what level the evidence itself supports) would
                       reach.
    qualified_level -- what the Alpha actually qualifies for once every
                       existing qualification gate (Evidence, local
                       Structure Graph, ticker-specific evidence, B3
                       Entity Exposure, regime gate) is applied.
    is_blocked      -- True exactly when qualified_level < target_level.
    blocked_from    -- which level(s) were reached by score but denied by
                       qualification, in fixed order (dominant, then
                       regime_level).

``blocked`` is qualification metadata, never a fifth Activation level --
the four canonical levels remain exactly candidate/active/dominant/
regime_level (task section 3, Decision 1).

Before this module, ``status`` was written independently in two places
(``activation_scorer_v2.score_alpha_v2``, then again by
``exposure_engine.compute_run_entity_alpha_exposures`` via
``_cap_status``) -- this module is now the *only* writer; both of those
callers supply inputs to it instead of writing ``status`` themselves (see
``graph_engine.pipeline`` for the call site).
"""

from __future__ import annotations

import math
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from typing import Any

CLASSIFICATION_VERSION = "b4.alpha_level.v1"

# John's exact, frozen boundaries (task section 4) -- half-open on the
# lower side: score >= threshold, never score <= or score >. Centralized
# here as the single source of truth; nothing else should hardcode 50/70/86.
ACTIVE_THRESHOLD = 50.0
DOMINANT_THRESHOLD = 70.0
REGIME_LEVEL_THRESHOLD = 86.0

CANDIDATE = "candidate"
ACTIVE = "active"
DOMINANT = "dominant"
REGIME_LEVEL = "regime_level"
CANONICAL_LEVELS = (CANDIDATE, ACTIVE, DOMINANT, REGIME_LEVEL)
_LEVEL_RANK = {CANDIDATE: 0, ACTIVE: 1, DOMINANT: 2, REGIME_LEVEL: 3}

# John's four canonical, product-facing blocked reasons (task section 9).
# Never invent a fifth; a diagnostic condition with no clean match among
# these four is still recorded in diagnostic_reason_codes, just omitted
# from blocked_reason_codes.
REASON_NO_LOCAL_STRUCTURE_SUPPORT = "NO_LOCAL_STRUCTURE_SUPPORT"
REASON_INSUFFICIENT_EVIDENCE = "INSUFFICIENT_EVIDENCE"
REASON_LOW_ENTITY_EXPOSURE = "LOW_ENTITY_EXPOSURE"
REASON_NO_TICKER_SPECIFIC_EVIDENCE = "NO_TICKER_SPECIFIC_EVIDENCE"
CANONICAL_BLOCKED_REASONS = frozenset(
    {
        REASON_NO_LOCAL_STRUCTURE_SUPPORT,
        REASON_INSUFFICIENT_EVIDENCE,
        REASON_LOW_ENTITY_EXPOSURE,
        REASON_NO_TICKER_SPECIFIC_EVIDENCE,
    }
)

# task section 9's mapping table, verbatim. Every key here is an existing,
# unmodified diagnostic reason code already produced by
# activation_scorer_v2.py (_apply_caps/_evaluate_regime_gate) or
# exposure_engine.py -- this module never invents a new diagnostic
# condition, only relabels the existing ones for product display.
# SCORE_BELOW_REGIME_THRESHOLD and EVIDENCE_INTEGRITY_WARNING are
# deliberately absent: neither has a clean match among John's four
# canonical reasons, so they surface in diagnostic_reason_codes only.
_CANONICAL_REASON_MAP: dict[str, str] = {
    "INSUFFICIENT_UNIQUE_EVIDENCE": REASON_INSUFFICIENT_EVIDENCE,
    "INSUFFICIENT_AGENT_INDEPENDENCE": REASON_INSUFFICIENT_EVIDENCE,
    "KEYWORD_ONLY_SUPPORT": REASON_INSUFFICIENT_EVIDENCE,
    "NO_LOCAL_STRUCTURE_SUPPORT": REASON_NO_LOCAL_STRUCTURE_SUPPORT,
    "NO_TICKER_SPECIFIC_EVIDENCE": REASON_NO_TICKER_SPECIFIC_EVIDENCE,
    "INSUFFICIENT_UNIQUE_EVIDENCE_FOR_REGIME": REASON_INSUFFICIENT_EVIDENCE,
    "INSUFFICIENT_SUPPORTING_AGENTS_FOR_REGIME": REASON_INSUFFICIENT_EVIDENCE,
    "INSUFFICIENT_TICKER_SPECIFIC_EVIDENCE_FOR_REGIME": REASON_NO_TICKER_SPECIFIC_EVIDENCE,
    "NO_LOCAL_STRUCTURE_FOR_REGIME": REASON_NO_LOCAL_STRUCTURE_SUPPORT,
    "INSUFFICIENT_LOCAL_STRUCTURE_STRENGTH_FOR_REGIME": REASON_NO_LOCAL_STRUCTURE_SUPPORT,
    "EXPOSURE_BELOW_DOMINANT_THRESHOLD": REASON_LOW_ENTITY_EXPOSURE,
    "EXPOSURE_BELOW_REGIME_THRESHOLD": REASON_LOW_ENTITY_EXPOSURE,
    "SEED_ENTRY_MISSING": REASON_LOW_ENTITY_EXPOSURE,
    "EXPOSURE_SEED_MISSING": REASON_LOW_ENTITY_EXPOSURE,
}

# B3's own generic "something happened" marker -- never a diagnostic
# condition by itself, always paired with a specific reason; excluded from
# both diagnostic_reason_codes and the canonical mapping input.
_EXPOSURE_APPLIED_MARKER = "EXPOSURE_QUALIFICATION_APPLIED"

APPROVED_GATING = "approved_gating"


class AlphaLevelInputError(Exception):
    """Safe input-contract violation: carries a stable reason code only."""

    def __init__(self, reason_code: str) -> None:
        self.reason_code = reason_code
        super().__init__(reason_code)


def _require_score(value: Any, reason_code: str) -> float:
    """A finite number in [0, 100]. NaN/Inf/bool/str are all rejected --
    never silently clamped or guessed (task section 16.A)."""
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise AlphaLevelInputError(reason_code)
    number = float(value)
    if not math.isfinite(number) or not (0.0 <= number <= 100.0):
        raise AlphaLevelInputError(reason_code)
    return number


def _dedupe_stable(codes: Sequence[str]) -> list[str]:
    seen: set[str] = set()
    ordered: list[str] = []
    for code in codes:
        if code not in seen:
            seen.add(code)
            ordered.append(code)
    return ordered


def level_for_score(score: Any) -> str:
    """John's exact four-band classification (task section 4). Half-open
    lower-bound comparisons only (``>=``) -- never ``<=``/``>``, which is
    exactly the class of boundary bug this task exists to eliminate."""
    number = _require_score(score, "INVALID_ACTIVATION_LEVEL_SCORE")
    if number >= REGIME_LEVEL_THRESHOLD:
        return REGIME_LEVEL
    if number >= DOMINANT_THRESHOLD:
        return DOMINANT
    if number >= ACTIVE_THRESHOLD:
        return ACTIVE
    return CANDIDATE


def _canonicalize(reason_codes: Sequence[str]) -> list[str]:
    mapped = [_CANONICAL_REASON_MAP[code] for code in reason_codes if code in _CANONICAL_REASON_MAP]
    return _dedupe_stable(mapped)


def _exposure_diagnostic_codes(entity_exposure: Mapping[str, Any] | None) -> tuple[list[str], bool, bool]:
    """Only an ``approved_gating`` Exposure result may ever block
    qualification (task section 8) -- ``draft_shadow``/``disabled``
    (or a missing/absent Exposure result entirely) never contribute a
    diagnostic code and never block anything, regardless of what
    would_block_dominant/would_block_regime_level literally say (B3
    computes those observationally in every mode). A missing approved
    seed entry fails closed (blocks both dominant and regime_level) even
    though would_block_* is False for a null final_exposure -- "missing"
    is not "computed and merely low"."""
    if not isinstance(entity_exposure, Mapping):
        return [], False, False
    if entity_exposure.get("effective_status") != APPROVED_GATING:
        return [], False, False

    codes = [
        str(code)
        for code in (entity_exposure.get("reason_codes") or ())
        if str(code) != _EXPOSURE_APPLIED_MARKER
    ]
    if entity_exposure.get("exposure_status") == "missing_seed":
        return _dedupe_stable(codes), True, True
    blocks_dominant = bool(entity_exposure.get("would_block_dominant"))
    blocks_regime = bool(entity_exposure.get("would_block_regime_level"))
    return _dedupe_stable(codes), blocks_dominant, blocks_regime


@dataclass(frozen=True)
class AlphaLevelClassification:
    target_level: str
    qualified_level: str
    is_blocked: bool
    blocked_from: tuple[str, ...]
    blocked_reason_codes: tuple[str, ...]
    diagnostic_reason_codes: tuple[str, ...]
    classification_version: str = CLASSIFICATION_VERSION

    def to_dict(self) -> dict[str, Any]:
        return {
            "target_level": self.target_level,
            "qualified_level": self.qualified_level,
            "is_blocked": self.is_blocked,
            "blocked_from": list(self.blocked_from),
            "blocked_reason_codes": list(self.blocked_reason_codes),
            "diagnostic_reason_codes": list(self.diagnostic_reason_codes),
            "classification_version": self.classification_version,
        }


def classify_alpha_level(
    *,
    activation_score: Any,
    uncapped_score: Any = None,
    dominant_cap_reason_codes: Sequence[str] = (),
    regime_gate_passed: bool | None = None,
    regime_gate_failures: Sequence[str] = (),
    entity_exposure: Mapping[str, Any] | None = None,
) -> AlphaLevelClassification:
    """The single authoritative B4 classifier (task section 6).

    Every qualification input is consumed exactly as already computed --
    ``dominant_cap_reason_codes`` is Activation v2's own
    ``cap_reason_codes`` (empty means every dominant-qualification
    condition -- unique Evidence Facts, agent independence, ticker-specific
    evidence, local Structure Graph support, non-keyword-only support --
    already passes); ``regime_gate_passed``/``regime_gate_failures`` are
    ``_evaluate_regime_gate``'s own unmodified result;
    ``entity_exposure`` is B3's own per-alpha ``entity_exposure`` record
    (or ``None`` when Exposure produced no record for this alpha at all,
    e.g. an unconfigured ticker under draft_shadow). Never re-derives any
    of these; only arbitrates the final level per John's Case A-D decision
    order (task section 7).
    """
    # activation_score itself must always be a valid finite [0, 100] score
    # -- validated here for its own sake (the arbitration below only ever
    # consults target_basis_score's *level band*, never activation_score's
    # numeric value again).
    _require_score(activation_score, "INVALID_ACTIVATION_LEVEL_SCORE")
    target_basis = uncapped_score if uncapped_score is not None else activation_score
    target_basis_score = _require_score(target_basis, "INVALID_ACTIVATION_LEVEL_SCORE")
    target_level = level_for_score(target_basis_score)

    dominant_cap_reason_codes = list(dominant_cap_reason_codes or ())
    regime_gate_failures = list(regime_gate_failures or ())
    exposure_codes, exposure_blocks_dominant, exposure_blocks_regime = _exposure_diagnostic_codes(
        entity_exposure
    )

    dominant_diagnostic = _dedupe_stable([*dominant_cap_reason_codes, *exposure_codes])
    dominant_qualifies = not dominant_cap_reason_codes and not exposure_blocks_dominant

    regime_diagnostic = _dedupe_stable([*regime_gate_failures, *exposure_codes])
    regime_qualifies = bool(regime_gate_passed) and not exposure_blocks_regime

    diagnostic_reason_codes: list[str] = []
    blocked_reason_codes: list[str] = []

    # Case A/B (task section 7): candidate/active have no qualification
    # gate beyond the score itself -- John: "不要自行给 active 再增加新的
    # Evidence、Graph 或 Exposure gate."
    if target_level in (CANDIDATE, ACTIVE):
        qualified_level = target_level
        is_blocked = False
        blocked_from: tuple[str, ...] = ()
    elif target_level == DOMINANT:
        # Case C
        if dominant_qualifies:
            qualified_level, is_blocked, blocked_from = DOMINANT, False, ()
        else:
            qualified_level, is_blocked, blocked_from = ACTIVE, True, (DOMINANT,)
            diagnostic_reason_codes = dominant_diagnostic
            blocked_reason_codes = _canonicalize(dominant_diagnostic)
    else:
        # Case D (target_level == REGIME_LEVEL)
        if regime_qualifies:
            qualified_level, is_blocked, blocked_from = REGIME_LEVEL, False, ()
        elif dominant_qualifies:
            qualified_level, is_blocked, blocked_from = DOMINANT, True, (REGIME_LEVEL,)
            diagnostic_reason_codes = regime_diagnostic
            blocked_reason_codes = _canonicalize(regime_diagnostic)
        else:
            qualified_level, is_blocked, blocked_from = ACTIVE, True, (DOMINANT, REGIME_LEVEL)
            diagnostic_reason_codes = _dedupe_stable([*dominant_diagnostic, *regime_diagnostic])
            blocked_reason_codes = _canonicalize(diagnostic_reason_codes)

    return AlphaLevelClassification(
        target_level=target_level,
        qualified_level=qualified_level,
        is_blocked=is_blocked,
        blocked_from=tuple(blocked_from),
        blocked_reason_codes=tuple(blocked_reason_codes),
        diagnostic_reason_codes=tuple(diagnostic_reason_codes),
    )


def _alpha_summary(entry: Mapping[str, Any]) -> dict[str, Any]:
    return {
        "alpha_id": entry.get("alpha_id"),
        "alpha_name": entry.get("alpha_name"),
        "activation_score": entry.get("activation_score"),
        "status": entry.get("status"),
        "direction": entry.get("direction"),
        "evidence_summary": {
            "evidence_count": entry.get("evidence_count"),
            "distinct_supporting_agents": entry.get("distinct_supporting_agents"),
        },
        "target_level": entry.get("target_level"),
        "qualified_level": entry.get("qualified_level"),
        "is_blocked": entry.get("is_blocked"),
        "blocked_from": entry.get("blocked_from"),
        "blocked_reason_codes": entry.get("blocked_reason_codes"),
    }


def _sort_key(entry: Mapping[str, Any]) -> tuple[float, str]:
    score = entry.get("activation_score")
    return (-(score if isinstance(score, (int, float)) else 0.0), str(entry.get("alpha_id") or ""))


def classify_and_rebuild_collections(activation_payload: dict[str, Any]) -> dict[str, Any]:
    """The single call site (task section 6/10): classify every alpha in
    an already-scored, already-Exposure-evaluated v2 activation payload,
    write the final ``status``/classification fields onto each alpha entry
    (the only place ``status`` is written from this point in the pipeline
    onward), and rebuild every authoritative collection exactly once.

    Mutates and returns ``activation_payload`` in place. Must be called
    only after both Activation v2 scoring and B3 Entity Exposure have
    already run on this same payload -- it consumes
    ``entry["entity_exposure"]`` (B3's own record, or absent) as one
    qualification input and never recomputes it.

    ``dominant_alphas`` keeps its exact pre-existing meaning (qualified для
    dominant *or* regime_level -- task section 12: never redefine an
    A2-frozen field) for backward compatibility; ``active_alphas``/
    ``regime_level_alphas``/``candidate_alphas``/``blocked_alphas`` are new,
    additive collections split by the single true ``qualified_level``/
    ``is_blocked`` this function itself just computed.
    """
    entries = activation_payload.get("alphas")
    if not isinstance(entries, list):
        raise AlphaLevelInputError("INVALID_ACTIVATION_LEVEL_PAYLOAD")

    for entry in entries:
        classification = classify_alpha_level(
            activation_score=entry.get("activation_score"),
            uncapped_score=entry.get("uncapped_score"),
            dominant_cap_reason_codes=entry.get("cap_reason_codes") or (),
            regime_gate_passed=entry.get("regime_gate_passed"),
            regime_gate_failures=entry.get("regime_gate_failures") or (),
            entity_exposure=entry.get("entity_exposure"),
        )
        entry.update(classification.to_dict())
        entry["status"] = classification.qualified_level

    by_level: dict[str, list[Mapping[str, Any]]] = {level: [] for level in CANONICAL_LEVELS}
    blocked: list[Mapping[str, Any]] = []
    for entry in entries:
        by_level[entry["qualified_level"]].append(entry)
        if entry["is_blocked"]:
            blocked.append(entry)

    activation_payload["dominant_alphas"] = sorted(
        (_alpha_summary(e) for e in (*by_level[DOMINANT], *by_level[REGIME_LEVEL])), key=_sort_key
    )
    activation_payload["active_alphas"] = sorted(
        (_alpha_summary(e) for e in by_level[ACTIVE]), key=_sort_key
    )
    activation_payload["regime_level_alphas"] = sorted(
        (_alpha_summary(e) for e in by_level[REGIME_LEVEL]), key=_sort_key
    )
    activation_payload["candidate_alphas"] = sorted(
        (_alpha_summary(e) for e in by_level[CANDIDATE]), key=_sort_key
    )
    activation_payload["blocked_alphas"] = sorted(
        (_alpha_summary(e) for e in blocked), key=_sort_key
    )
    return activation_payload


__all__ = [
    "ACTIVE",
    "ACTIVE_THRESHOLD",
    "APPROVED_GATING",
    "CANDIDATE",
    "CANONICAL_BLOCKED_REASONS",
    "CANONICAL_LEVELS",
    "CLASSIFICATION_VERSION",
    "DOMINANT",
    "DOMINANT_THRESHOLD",
    "REASON_INSUFFICIENT_EVIDENCE",
    "REASON_LOW_ENTITY_EXPOSURE",
    "REASON_NO_LOCAL_STRUCTURE_SUPPORT",
    "REASON_NO_TICKER_SPECIFIC_EVIDENCE",
    "REGIME_LEVEL",
    "REGIME_LEVEL_THRESHOLD",
    "AlphaLevelClassification",
    "AlphaLevelInputError",
    "classify_alpha_level",
    "classify_and_rebuild_collections",
    "level_for_score",
]
