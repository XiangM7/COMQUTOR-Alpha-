"""Sprint 3 (Unclassified Findings Control), Track A3: deterministic
canonical-reason assignment and Top-20 ordering for claims that are
retained (never deleted) but do not enter the normal classified/research
finding display path.

Every reason here is read straight off an already-computed upstream
signal -- this module never runs a second Alpha Mapper, Evidence Stance
classifier, Evidence Fact grouping pass, or dedup pass, and never calls
an LLM:

  * ``no_alpha_match`` -- alpha_matches.json's own authoritative
    ``matched_alpha`` (PD-014: no-match claims are retained, never
    dropped, never LLM-forced into a match).
  * ``generic_background`` -- the Alpha Mapper's own top-level
    ``matched_evidence_stance`` (Sprint 2, Track B1) for the claim's
    matched_alpha: ``neutral_background`` or ``mentions_alpha``. A
    ``mentions_alpha`` claim is never treated as supporting the Alpha;
    its target Alpha identity (``matched_alpha``) is preserved on the
    finding regardless.
  * ``duplicate_supporting_text`` -- evidence_facts.json's own
    ``representative_claim_id``/``member_claim_ids`` (Evidence Fact
    Index, already computed by Activation v2's evidence-fact grouping)
    for a group whose ``supporting_alpha_ids`` includes the claim's
    matched_alpha. ``structured_agent_outputs.json``'s own
    ``duplicate_group_id`` is surfaced on every finding for provenance,
    but does not by itself drive this reason: unlike Evidence Fact Index
    groups, it carries no explicit representative-claim signal, and
    inventing one would be exactly the kind of new dedup rule this task
    forbids.
  * ``no_ticker_specific_evidence`` -- the same
    ``activation_scorer_v2._is_ticker_specific`` deterministic check
    Activation v2 and B2 already use (see conflict_admissibility.py's
    identical ``company_names=()``/``entities_by_claim={}`` call
    convention -- behaviorally identical to production, not a new
    heuristic).
  * ``low_confidence`` -- deliberately never assigned. No formally
    defined, actually-used threshold against
    StructuredAgentOutputRecord.confidence exists anywhere in this
    repository. ``candidate_scores[].stance_confidence_band`` /
    ``matched_stance_confidence_band`` is a different concept (confidence
    in the Evidence Stance classification itself, not in the claim), and
    every existing CONFIDENCE_LOW case in evidence_stance.py already
    coincides with a generic_background-eligible stance -- repurposing it
    as claim-level confidence would be exactly the kind of
    confidence/relevance conflation PD-012 already forbids for match
    scores. See LOW_CONFIDENCE_THRESHOLD_NOT_FORMALLY_DEFINED below.

A finding with zero applicable reasons is fully classified and is not
included in this artifact at all -- this is what keeps a direction-
neutral-but-validly-matched, ticker-specific, non-duplicate claim out of
the unclassified universe (see docs/audit_artifacts/
a3_unclassified_findings_control_report.md). A finding whose matched
Alpha carries an Evidence Stance outside the known five-value ontology
(a genuine data anomaly, never expected in a well-formed run) is
reported honestly via UNCLASSIFIED_REASON_UNRESOLVED rather than being
guessed into one of the five canonical reasons.
"""

from __future__ import annotations

from collections.abc import Mapping
from typing import Any

from comqutor_alpha.graph_engine.activation_scorer_v2 import _is_ticker_specific
from comqutor_alpha.storage.file_store import load_json_record_if_exists
from comqutor_alpha.structure_engine.evidence_stance import (
    MENTIONS_ALPHA,
    NEUTRAL_BACKGROUND,
    OPPOSES_ALPHA,
    SUPPORTS_ALPHA,
    SUPPORTS_COUNTER_ALPHA,
)

SCHEMA_VERSION = "unclassified_findings.v1"
ARTIFACT_FILENAME = "unclassified_findings.json"
DEFAULT_DISPLAY_LIMIT = 20

# John's 5 canonical reasons (task A3_UNCLASSIFIED_FINDINGS_CONTROL,
# section 7) -- the only values this module ever writes to `reason`/
# `reason_codes`. Never extended with a 6th reason.
REASON_NO_ALPHA_MATCH = "no_alpha_match"
REASON_LOW_CONFIDENCE = "low_confidence"
REASON_GENERIC_BACKGROUND = "generic_background"
REASON_DUPLICATE_SUPPORTING_TEXT = "duplicate_supporting_text"
REASON_NO_TICKER_SPECIFIC_EVIDENCE = "no_ticker_specific_evidence"
# Honest escape hatch (task section 9) -- never a guessed/invented 6th
# canonical reason; a stable diagnostic instead.
REASON_UNRESOLVED = "UNCLASSIFIED_REASON_UNRESOLVED"

# Frozen priority order (task section 8) -- highest priority first.
# Determines the single primary `reason` when more than one canonical
# reason applies; every applicable reason still appears in `reason_codes`.
REASON_PRIORITY = (
    REASON_DUPLICATE_SUPPORTING_TEXT,
    REASON_GENERIC_BACKGROUND,
    REASON_LOW_CONFIDENCE,
    REASON_NO_ALPHA_MATCH,
    REASON_NO_TICKER_SPECIFIC_EVIDENCE,
)
CANONICAL_REASONS = frozenset(REASON_PRIORITY)

LOW_CONFIDENCE_THRESHOLD_NOT_FORMALLY_DEFINED = "LOW_CONFIDENCE_THRESHOLD_NOT_FORMALLY_DEFINED"

_BACKGROUND_STANCES = frozenset({NEUTRAL_BACKGROUND, MENTIONS_ALPHA})
_NON_BACKGROUND_STANCES = frozenset({SUPPORTS_ALPHA, OPPOSES_ALPHA, SUPPORTS_COUNTER_ALPHA})


def _structured_index(structured_payload: Any) -> dict[str, dict[str, Any]]:
    """claim_id -> structured_agent_outputs.json record. Pure identity
    join -- never re-derives confidence, claim_index, or source_refs."""
    records = structured_payload.get("records") if isinstance(structured_payload, Mapping) else None
    index: dict[str, dict[str, Any]] = {}
    for record in records or ():
        if isinstance(record, Mapping) and record.get("claim_id"):
            index[str(record["claim_id"])] = record
    return index


def _evidence_fact_membership(evidence_facts_payload: Any) -> dict[str, list[dict[str, Any]]]:
    """claim_id -> every Evidence Fact group (evidence_facts.json, already
    computed by Activation v2's own evidence-fact grouping) it is a
    member of. Pure membership extraction -- never a new grouping pass."""
    groups = evidence_facts_payload.get("groups") if isinstance(evidence_facts_payload, Mapping) else None
    index: dict[str, list[dict[str, Any]]] = {}
    for group in groups or ():
        if not isinstance(group, Mapping):
            continue
        group_id = group.get("evidence_fact_group_id")
        if not group_id:
            continue
        representative_claim_id = group.get("representative_claim_id")
        supporting_alpha_ids = frozenset(group.get("supporting_alpha_ids") or ())
        for claim_id in group.get("member_claim_ids") or ():
            index.setdefault(str(claim_id), []).append(
                {
                    "evidence_fact_group_id": group_id,
                    "representative_claim_id": representative_claim_id,
                    "supporting_alpha_ids": supporting_alpha_ids,
                }
            )
    return index


def _matching_fact_group(
    claim_id: str, matched_alpha: str | None, membership: Mapping[str, list[dict[str, Any]]]
) -> dict[str, Any] | None:
    """The one Evidence Fact group (if any) this claim belongs to *as
    supporting evidence for its own matched_alpha* -- never a group
    supporting a different Alpha the claim happens to also appear
    under."""
    if not matched_alpha:
        return None
    for entry in membership.get(claim_id, ()):
        if matched_alpha in entry["supporting_alpha_ids"]:
            return entry
    return None


def _evaluate_finding(
    match: Mapping[str, Any],
    *,
    structured_record: Mapping[str, Any] | None,
    membership: Mapping[str, list[dict[str, Any]]],
    ticker: str,
) -> dict[str, Any] | None:
    """Evaluate one alpha_matches.json record. Returns a finding dict when
    at least one canonical reason (or the honest UNRESOLVED fallback)
    applies, or ``None`` when the finding is fully classified -- such a
    finding must not be included in the unclassified universe at all."""
    claim_id = str(match.get("claim_id") or "")
    matched_alpha = match.get("matched_alpha") or None
    stance = match.get("matched_evidence_stance") if matched_alpha else None

    # Ticker-specificity is computed unconditionally (useful for display/
    # sorting on every finding, matched or not) via the exact same
    # deterministic signal Activation v2/B2 already use.
    ticker_specific = bool(_is_ticker_specific(match, ticker, (), {}))

    fact_group = _matching_fact_group(claim_id, matched_alpha, membership)
    is_duplicate = bool(fact_group is not None and fact_group["representative_claim_id"] != claim_id)

    reasons: set[str] = set()
    diagnostics: list[str] = []

    if not matched_alpha:
        reasons.add(REASON_NO_ALPHA_MATCH)
        match_reason = match.get("reason")
        if match_reason:
            diagnostics.append(str(match_reason))
    else:
        if is_duplicate:
            reasons.add(REASON_DUPLICATE_SUPPORTING_TEXT)
        if stance in _BACKGROUND_STANCES:
            reasons.add(REASON_GENERIC_BACKGROUND)
            diagnostics.append(str(stance))
            diagnostics.extend(str(code) for code in (match.get("matched_stance_reason_codes") or ()))
        if not ticker_specific:
            reasons.add(REASON_NO_TICKER_SPECIFIC_EVIDENCE)

    if not reasons:
        if matched_alpha and stance not in _NON_BACKGROUND_STANCES:
            # Anomaly: a matched claim whose stance is neither a known
            # "clearly classified" value nor a known background value
            # (e.g. missing/unexpected -- never expected in a
            # well-formed run). Reported honestly, never guessed into one
            # of the five canonical reasons.
            reasons.add(REASON_UNRESOLVED)
            diagnostics.append(f"unexpected_stance:{stance}" if stance is not None else "missing_matched_evidence_stance")
        else:
            return None  # fully classified; not part of the unclassified universe

    reason_codes = [r for r in REASON_PRIORITY if r in reasons] or [REASON_UNRESOLVED]
    primary_reason = reason_codes[0]

    confidence = None
    claim_index = None
    source_refs: list[str] = []
    if structured_record is not None:
        raw_confidence = structured_record.get("confidence")
        confidence = raw_confidence if isinstance(raw_confidence, int | float) else None
        raw_claim_index = structured_record.get("claim_index")
        claim_index = raw_claim_index if isinstance(raw_claim_index, int) else None
        source_refs = [str(ref) for ref in (structured_record.get("source_refs") or ())]

    return {
        "claim_id": claim_id,
        "claim": match.get("claim"),
        "evidence": match.get("evidence"),
        "agent": match.get("agent"),
        "confidence": confidence,
        "matched_alpha": matched_alpha,
        "secondary_alphas": list(match.get("secondary_alphas") or ()),
        "direction": match.get("direction"),
        "reason": primary_reason,
        "reason_codes": reason_codes,
        "diagnostic_reason_codes": sorted(set(diagnostics)),
        "ticker_specific": ticker_specific,
        "duplicate_group_id": (structured_record or {}).get("duplicate_group_id"),
        "evidence_fact_group_id": fact_group["evidence_fact_group_id"] if fact_group else None,
        "representative_claim_id": fact_group["representative_claim_id"] if fact_group else None,
        "source_refs": source_refs,
        "source_agent_output_id": match.get("source_agent_output_id"),
        "claim_index": claim_index,
    }


def _sort_key(finding: Mapping[str, Any]) -> tuple:
    """John's frozen Top-20 ordering (task section 11): ticker-specific
    findings first, then higher confidence first, then original pipeline
    order (claim_index), then claim_id as the final stable tie-breaker.
    Missing confidence/claim_index sort stably *after* present values --
    never guessed as 0/1."""
    ticker_specific = bool(finding.get("ticker_specific"))
    confidence = finding.get("confidence")
    has_confidence = isinstance(confidence, int | float)
    claim_index = finding.get("claim_index")
    has_claim_index = isinstance(claim_index, int)
    return (
        0 if ticker_specific else 1,
        0 if has_confidence else 1,
        -float(confidence) if has_confidence else 0.0,
        0 if has_claim_index else 1,
        claim_index if has_claim_index else 0,
        str(finding.get("claim_id") or ""),
    )


def build_unclassified_findings_export(
    *,
    run_id: str,
    ticker: str,
    output_root: str,
    alpha_matches_payload: Any,
    evidence_facts_payload: Any = None,
    display_limit: int = DEFAULT_DISPLAY_LIMIT,
) -> dict[str, Any]:
    """Builds the unclassified_findings.json payload.

    Purely additive: reads alpha_matches.json (already computed by the
    Alpha Mapper), structured_agent_outputs.json (already computed by the
    structured output adapter), and evidence_facts.json (already computed
    by Activation v2's Evidence Fact grouping -- pass ``evidence_facts_payload``
    directly when the caller just built it in the same finalization pass,
    to avoid a second read of the same data). Never calls an LLM, never
    re-groups claims, never re-scores Alpha matches, never re-classifies
    Evidence Stance.
    """
    structured_payload = load_json_record_if_exists(run_id, "structured_agent_outputs.json", output_root=output_root)
    if evidence_facts_payload is None:
        evidence_facts_payload = load_json_record_if_exists(run_id, "evidence_facts.json", output_root=output_root)

    structured_index = _structured_index(structured_payload)
    membership = _evidence_fact_membership(evidence_facts_payload)

    matches = alpha_matches_payload.get("matches") if isinstance(alpha_matches_payload, Mapping) else None

    findings: list[dict[str, Any]] = []
    for match in matches or ():
        if not isinstance(match, Mapping):
            continue
        claim_id = str(match.get("claim_id") or "")
        finding = _evaluate_finding(
            match,
            structured_record=structured_index.get(claim_id),
            membership=membership,
            ticker=ticker,
        )
        if finding is not None:
            finding["run_id"] = run_id
            finding["ticker"] = ticker
            findings.append(finding)

    findings.sort(key=_sort_key)
    for rank, finding in enumerate(findings, start=1):
        finding["display_rank"] = rank

    reason_counts: dict[str, int] = dict.fromkeys(REASON_PRIORITY, 0)
    unresolved_count = 0
    for finding in findings:
        for code in finding["reason_codes"]:
            if code in reason_counts:
                reason_counts[code] += 1
        if finding["reason"] == REASON_UNRESOLVED:
            unresolved_count += 1

    return {
        "schema_version": SCHEMA_VERSION,
        "run_id": run_id,
        "ticker": ticker,
        "total_count": len(findings),
        "display_limit": display_limit,
        "reason_counts": reason_counts,
        "unresolved_reason_count": unresolved_count,
        "low_confidence_signal_status": LOW_CONFIDENCE_THRESHOLD_NOT_FORMALLY_DEFINED,
        "findings": findings,
    }


__all__ = [
    "SCHEMA_VERSION",
    "ARTIFACT_FILENAME",
    "DEFAULT_DISPLAY_LIMIT",
    "REASON_NO_ALPHA_MATCH",
    "REASON_LOW_CONFIDENCE",
    "REASON_GENERIC_BACKGROUND",
    "REASON_DUPLICATE_SUPPORTING_TEXT",
    "REASON_NO_TICKER_SPECIFIC_EVIDENCE",
    "REASON_UNRESOLVED",
    "REASON_PRIORITY",
    "CANONICAL_REASONS",
    "LOW_CONFIDENCE_THRESHOLD_NOT_FORMALLY_DEFINED",
    "build_unclassified_findings_export",
]
