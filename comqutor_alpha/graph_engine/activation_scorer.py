"""Week 3 deterministic, explainable Activation Scorer.

Consumes ``alpha_matches.json`` (already-committed/ambiguous/no_match claim
decisions from Week 2) plus the run's own Structure Graph coherence result.
Never re-derives claim semantics and never reparses raw TradingAgents
reports: the "relation" used for every weighting decision below is read back
from the ``relation`` field the Week 2 mapper already attached to each
claim's matched candidate, not recomputed here.

Official Week 3 MVP formula (weights sum to 1.0, every component pre-clamped
to 0..100 before weighting)::

    Activation = MatchedEvidence * 35%
               + AgentAgreement  * 20%
               + GraphCoherence  * 25%
               + Recency         * 10%
               + DirectionStrength * 10%

``ConflictPenalty`` is Week 4 scope and is intentionally absent.
"""

from __future__ import annotations

from collections.abc import Mapping
from datetime import date, datetime
from typing import Any

from comqutor_alpha.alpha_library.alpha_loader import load_alpha_taxonomy
from comqutor_alpha.alpha_library.alpha_schema import AlphaDefinition
from comqutor_alpha.graph_engine.graph_schema import (
    ACTIVATION_FORMULA_VERSION,
    MVP_ALPHA_IDS,
    activation_status_band,
    clamp_percent,
)
from comqutor_alpha.structure_engine.claim_semantics import (
    OPPORTUNITY_ALPHA_IDS,
    RISK_ALPHA_IDS,
)

ACTIVATION_WEIGHTS = {
    "matched_evidence": 0.35,
    "agent_agreement": 0.20,
    "graph_coherence": 0.25,
    "recency": 0.10,
    "direction_strength": 0.10,
}

# Per-claim evidence weight by the Week 2 `relation` label. Counter-evidence
# (invalidation of an opportunity thesis, relief of a risk thesis) must not
# strengthen the alpha it is attached to, so it is weighted zero here -- its
# signal instead only shows up in DirectionStrength, as a negative pull.
_EVIDENCE_RELATION_WEIGHT = {
    "activation": 1.0,
    "conditional": 0.65,
    "mixed": 0.5,
    "invalidation": 0.0,
    "risk_relief": 0.0,
    "mention": 0.0,
    "unknown": 0.0,
}
EVIDENCE_SATURATION = 2.0
AMBIGUOUS_EVIDENCE_WEIGHT = 0.15
RECENCY_DECAY_WINDOW_DAYS = 90
RECENCY_FALLBACK_SCORE = 50.0


def _relation_for_match(record: Mapping[str, Any], alpha_id: str) -> str:
    for pool_key in ("eligible_candidates", "top_candidates", "candidate_scores"):
        pool = record.get(pool_key)
        if not isinstance(pool, list):
            continue
        for candidate in pool:
            if isinstance(candidate, Mapping) and str(candidate.get("alpha_id")) == alpha_id:
                relation = str(candidate.get("relation") or "unknown").strip().lower()
                return relation if relation in _EVIDENCE_RELATION_WEIGHT else "unknown"
    return "unknown"


def _gather_alpha_evidence(
    alpha_matches_payload: Mapping[str, Any],
    alpha_id: str,
) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    """Return (committed, ambiguous) unique-by-claim_id evidence for one alpha.

    Deduplication by claim_id happens here so repeated storage rows (e.g. a
    retried pipeline stage or a hand-built test fixture with accidental
    duplicates) can never inflate a score.
    """
    matches = alpha_matches_payload.get("matches") if isinstance(alpha_matches_payload, Mapping) else None
    committed: dict[str, dict[str, Any]] = {}
    ambiguous: dict[str, dict[str, Any]] = {}
    if not isinstance(matches, list):
        return [], []

    for record in matches:
        if not isinstance(record, Mapping):
            continue
        claim_id = record.get("claim_id")
        if not claim_id:
            continue
        claim_id = str(claim_id)
        status = record.get("match_status")
        agent = str(record.get("agent") or "").strip() or None
        evidence_text = str(record.get("evidence") or record.get("claim") or "").strip()

        if status == "matched" and record.get("matched_alpha") == alpha_id:
            if claim_id in committed:
                continue
            committed[claim_id] = {
                "claim_id": claim_id,
                "agent": agent,
                "relation": _relation_for_match(record, alpha_id),
                "score": clamp_percent(record.get("score", 0.0), 0.0, 1.0),
                "evidence": evidence_text,
            }
        elif status == "ambiguous" and alpha_id in (record.get("plausible_alphas") or []):
            if claim_id in ambiguous:
                continue
            ambiguous[claim_id] = {
                "claim_id": claim_id,
                "agent": agent,
                "relation": _relation_for_match(record, alpha_id),
                "score": clamp_percent(record.get("score", 0.0), 0.0, 1.0),
                "evidence": evidence_text,
            }

    return list(committed.values()), list(ambiguous.values())


def _matched_evidence_component(
    committed: list[dict[str, Any]],
    ambiguous: list[dict[str, Any]],
) -> tuple[float, dict[str, Any]]:
    weighted_sum = 0.0
    for claim in committed:
        weighted_sum += _EVIDENCE_RELATION_WEIGHT.get(claim["relation"], 0.0) * claim["score"]
    for claim in ambiguous:
        weighted_sum += (
            AMBIGUOUS_EVIDENCE_WEIGHT
            * _EVIDENCE_RELATION_WEIGHT.get(claim["relation"], 0.0)
            * claim["score"]
        )
    raw = clamp_percent(100.0 * weighted_sum / EVIDENCE_SATURATION)
    return raw, {
        "unique_committed_claims": len(committed),
        "unique_ambiguous_claims": len(ambiguous),
        "weighted_evidence_sum": round(weighted_sum, 4),
        "saturation": EVIDENCE_SATURATION,
        "ambiguous_weight": AMBIGUOUS_EVIDENCE_WEIGHT,
    }


def _agent_agreement_component(
    committed: list[dict[str, Any]],
    alpha_def: AlphaDefinition | None,
) -> tuple[float, dict[str, Any]]:
    qualifying_agents = sorted(
        {
            claim["agent"]
            for claim in committed
            if claim["agent"] and _EVIDENCE_RELATION_WEIGHT.get(claim["relation"], 0.0) > 0
        }
    )
    denominator = len(alpha_def.agent_sources) if alpha_def and alpha_def.agent_sources else 0
    if denominator <= 0:
        return 0.0, {
            "distinct_agents": len(qualifying_agents),
            "denominator": 0,
            "denominator_source": "taxonomy.agent_sources",
            "agents": qualifying_agents,
        }
    raw = clamp_percent(100.0 * len(qualifying_agents) / denominator)
    return raw, {
        "distinct_agents": len(qualifying_agents),
        "denominator": denominator,
        "denominator_source": "taxonomy.agent_sources",
        "agents": qualifying_agents,
    }


def _direction_strength_component(committed: list[dict[str, Any]]) -> tuple[float, dict[str, Any]]:
    signed: list[float] = []
    for claim in committed:
        relation = claim["relation"]
        if relation == "activation":
            signed.append(1.0)
        elif relation in ("invalidation", "risk_relief"):
            signed.append(-1.0)
        elif relation == "conditional":
            signed.append(0.4)
        elif relation == "mixed":
            signed.append(0.0)
        # "mention"/"unknown" never reach here as committed evidence, but if
        # they did they would be un-scored (not appended), matching "no
        # committed direction signal" rather than fabricating one.

    if not signed:
        return 0.0, {"qualifying_claim_count": 0, "average_signed_strength": 0.0}

    average = sum(signed) / len(signed)
    raw = clamp_percent(((average + 1.0) / 2.0) * 100.0)
    return raw, {
        "qualifying_claim_count": len(signed),
        "average_signed_strength": round(average, 4),
        "mixed_direction_evidence": len(set(signed)) > 1,
    }


def _parse_reference_date(value: Any) -> date | None:
    if value is None:
        return None
    if isinstance(value, date):
        return value
    if isinstance(value, datetime):
        return value.date()
    text = str(value).strip()
    if not text:
        return None
    normalized = text[:-1] + "+00:00" if text.endswith("Z") else text
    try:
        return datetime.fromisoformat(normalized).date()
    except ValueError:
        try:
            return date.fromisoformat(text[:10])
        except ValueError:
            return None


def _recency_component(run_timestamp: Any, as_of: Any) -> tuple[float, dict[str, Any]]:
    run_date = _parse_reference_date(run_timestamp)
    as_of_date = _parse_reference_date(as_of) if as_of is not None else run_date

    if run_date is None or as_of_date is None:
        return RECENCY_FALLBACK_SCORE, {
            "age_days": None,
            "fallback": True,
            "reason": "missing or unparseable run_timestamp/as_of",
        }

    age_days = max(0, (as_of_date - run_date).days)
    raw = clamp_percent(100.0 * max(0.0, 1.0 - age_days / RECENCY_DECAY_WINDOW_DAYS))
    return raw, {
        "age_days": age_days,
        "decay_window_days": RECENCY_DECAY_WINDOW_DAYS,
        "fallback": False,
    }


def _reason_codes(
    *,
    committed: list[dict[str, Any]],
    ambiguous: list[dict[str, Any]],
    matched_evidence_meta: dict[str, Any],
    agent_meta: dict[str, Any],
    direction_meta: dict[str, Any],
) -> list[str]:
    codes: list[str] = []
    if not committed and not ambiguous:
        codes.append("NO_EVIDENCE")
    elif not committed and ambiguous:
        codes.append("AMBIGUOUS_EVIDENCE_ONLY")
    elif committed and matched_evidence_meta["weighted_evidence_sum"] == 0.0:
        codes.append("ONLY_COUNTER_EVIDENCE_PRESENT")
    if agent_meta["distinct_agents"] == 1:
        codes.append("SINGLE_AGENT_ONLY")
    if direction_meta.get("mixed_direction_evidence"):
        codes.append("MIXED_DIRECTION_EVIDENCE")
    return codes


def _direction_label(direction_meta: Mapping[str, Any], alpha_id: str) -> str:
    """Market-direction implication of this alpha's net evidence.

    ``direction_meta["average_signed_strength"]`` measures alpha-thesis
    consistency (does the evidence support or contradict *this alpha's own*
    thesis), which is what feeds the DirectionStrength score. The market
    direction implied by that consistency is *not* the same sign for every
    alpha: an opportunity alpha being confirmed is bullish, but a risk alpha
    (A304/A501) being confirmed is legitimately bearish, and -- symmetrically
    -- risk_relief evidence (the risk thesis weakening) is bullish, not
    bearish. Only the label below is alpha-direction-aware; the numeric
    DirectionStrength score itself is not (per spec, it must not assume
    positive means stronger for every alpha).
    """
    if direction_meta["qualifying_claim_count"] == 0:
        return "unknown"
    average = direction_meta["average_signed_strength"]
    is_risk = alpha_id in RISK_ALPHA_IDS
    if average > 0.15:
        return "negative" if is_risk else "positive"
    if average < -0.15:
        return "positive" if is_risk else "negative"
    return "neutral"


def score_alpha(
    alpha_id: str,
    alpha_matches_payload: Mapping[str, Any],
    taxonomy: Mapping[str, AlphaDefinition],
    graph_coherence_score: float,
    *,
    run_timestamp: Any = None,
    as_of: Any = None,
) -> dict[str, Any]:
    """Score exactly one MVP alpha. Public so callers/tests can isolate one Alpha."""
    alpha_def = taxonomy.get(alpha_id)
    committed, ambiguous = _gather_alpha_evidence(alpha_matches_payload, alpha_id)
    matched_evidence_raw, matched_evidence_meta = _matched_evidence_component(committed, ambiguous)

    # Evidence-gating policy: an alpha is "completely unsupported" -- and
    # gated to activation_score 0 / status inactive -- when it has no
    # *positively weighted* evidence, i.e. MatchedEvidence's weighted sum is
    # zero. That covers both true zero evidence (no committed/ambiguous
    # claims at all) and the "only counter-evidence" case (every committed
    # claim is risk_relief/invalidation/mention, each weighted 0 by design):
    # a risk_relief-only claim must not outscore true absence of evidence,
    # so both must be gated identically. An alpha with any activation/
    # conditional/mixed evidence -- committed or ambiguous -- is not gated,
    # since it has real (if conservatively weighted) support.
    #
    # Without this gate, GraphCoherence and Recency are the only two
    # components that can be nonzero with no supporting evidence at all
    # (they are run-level/global signals, not per-alpha evidence), and on a
    # highly coherent, very recent run their combined floor
    # (0.25*100 + 0.10*100 = 35) could otherwise reach the "watch" band
    # purely from ambient run quality -- exactly what this gate prevents.
    # The five official weights are never changed; only the *contribution*
    # of these two evidence-independent components is suppressed to zero
    # for a gated alpha. Their `raw` values are left untouched (and marked
    # `evidence_gated: true`) so the run's ambient coherence/recency stays
    # visible for audit even though it did not count toward the score.
    has_admissible_evidence = matched_evidence_meta["weighted_evidence_sum"] > 0.0

    agent_agreement_raw, agent_meta = _agent_agreement_component(committed, alpha_def)
    graph_coherence_raw = clamp_percent(graph_coherence_score)
    recency_raw, recency_meta = _recency_component(run_timestamp, as_of)
    direction_raw, direction_meta = _direction_strength_component(committed)

    components = {
        "matched_evidence": {
            "raw": matched_evidence_raw,
            "weight": ACTIVATION_WEIGHTS["matched_evidence"],
            "contribution": round(matched_evidence_raw * ACTIVATION_WEIGHTS["matched_evidence"], 4),
            **matched_evidence_meta,
        },
        "agent_agreement": {
            "raw": agent_agreement_raw,
            "weight": ACTIVATION_WEIGHTS["agent_agreement"],
            "contribution": round(agent_agreement_raw * ACTIVATION_WEIGHTS["agent_agreement"], 4),
            **agent_meta,
        },
        "graph_coherence": {
            "raw": graph_coherence_raw,
            "weight": ACTIVATION_WEIGHTS["graph_coherence"],
            "contribution": (
                round(graph_coherence_raw * ACTIVATION_WEIGHTS["graph_coherence"], 4)
                if has_admissible_evidence
                else 0.0
            ),
            "scope": "global_run_level",
            "evidence_gated": not has_admissible_evidence,
        },
        "recency": {
            "raw": recency_raw,
            "weight": ACTIVATION_WEIGHTS["recency"],
            "contribution": (
                round(recency_raw * ACTIVATION_WEIGHTS["recency"], 4) if has_admissible_evidence else 0.0
            ),
            "evidence_gated": not has_admissible_evidence,
            **recency_meta,
        },
        "direction_strength": {
            "raw": direction_raw,
            "weight": ACTIVATION_WEIGHTS["direction_strength"],
            "contribution": round(direction_raw * ACTIVATION_WEIGHTS["direction_strength"], 4),
            **direction_meta,
        },
    }
    activation_score = clamp_percent(sum(c["contribution"] for c in components.values()))
    status = activation_status_band(activation_score)
    direction = _direction_label(direction_meta, alpha_id)

    evidence_texts = sorted({c["evidence"] for c in committed if c["evidence"]})
    claim_ids = sorted({c["claim_id"] for c in committed})

    return {
        "alpha_id": alpha_id,
        "alpha_name": alpha_def.name_en if alpha_def else alpha_id,
        "activation_score": activation_score,
        "status": status,
        "direction": direction,
        "components": components,
        "evidence_count": len(committed),
        "distinct_supporting_agents": agent_meta["distinct_agents"],
        "claim_ids": claim_ids,
        "evidence": evidence_texts,
        "reason_codes": _reason_codes(
            committed=committed,
            ambiguous=ambiguous,
            matched_evidence_meta=matched_evidence_meta,
            agent_meta=agent_meta,
            direction_meta=direction_meta,
        ),
    }


def score_alpha_activations(
    alpha_matches_payload: Mapping[str, Any],
    graph_coherence_score: float,
    *,
    taxonomy: Mapping[str, AlphaDefinition] | None = None,
    run_timestamp: Any = None,
    as_of: Any = None,
) -> dict[str, Any]:
    """Score every MVP-10 alpha for one run. Deterministic and order-independent.

    ``run_timestamp`` should be the run's own ``analysis_date`` (preferred)
    or ``created_at``; ``as_of`` defaults to ``run_timestamp`` (a freshly
    scored run is fully recent) and exists purely so tests can exercise decay
    without depending on wall-clock time.
    """
    taxonomy = taxonomy or load_alpha_taxonomy()
    alphas = [
        score_alpha(
            alpha_id,
            alpha_matches_payload,
            taxonomy,
            graph_coherence_score,
            run_timestamp=run_timestamp,
            as_of=as_of,
        )
        for alpha_id in sorted(MVP_ALPHA_IDS)
    ]
    return {
        "formula_version": ACTIVATION_FORMULA_VERSION,
        "weights": dict(ACTIVATION_WEIGHTS),
        "run_timestamp": run_timestamp,
        "as_of": as_of if as_of is not None else run_timestamp,
        "alphas": alphas,
        "dominant_alphas": compute_dominant_alphas(alphas),
    }


def compute_dominant_alphas(alpha_results: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Deterministic dominant_alphas: status-band derived, never hardcoded per ticker."""
    dominant = [r for r in alpha_results if r["status"] in ("dominant", "regime_level")]
    dominant.sort(key=lambda r: (-r["activation_score"], r["alpha_id"]))
    return [
        {
            "alpha_id": r["alpha_id"],
            "alpha_name": r["alpha_name"],
            "activation_score": r["activation_score"],
            "status": r["status"],
            "direction": r["direction"],
            "evidence_summary": {
                "evidence_count": r["evidence_count"],
                "distinct_supporting_agents": r["distinct_supporting_agents"],
            },
        }
        for r in dominant
    ]


__all__ = [
    "OPPORTUNITY_ALPHA_IDS",
    "RISK_ALPHA_IDS",
    "ACTIVATION_WEIGHTS",
    "score_alpha",
    "score_alpha_activations",
    "compute_dominant_alphas",
]
