"""Regime Evidence Integrity Shadow Layer.

Product Findings Closure and Regime Evidence Integrity Sprint, Track B.

Pure functions only: no I/O, no database, no network, no Provider/LLM calls,
no API response generation. A read-only, internal, additive shadow analysis
layered on top of Activation v2's already-admitted evidence
(``graph_engine/activation_scorer_v2.py``, entirely untouched by this
module) -- never recomputes, overrides, or otherwise changes John's
production Activation score, status, or regime gate.

Why this exists: the same real fact can legitimately support multiple
Alphas (an AI-infrastructure-demand claim can be genuine evidence for both
A101 and A103), but multiple paraphrases of that ONE fact across different
agents must not be counted as multiple INDEPENDENT pieces of evidence. This
module:

1. builds deterministic Evidence Groups across an alpha's admitted matches
   (:func:`build_evidence_groups`);
2. attributes each group to a primary Alpha and zero or more secondary
   Alphas (:func:`build_evidence_groups` again -- attribution is computed
   per group, not as a separate pass);
3. computes per-Alpha overlap metrics (:func:`compute_alpha_evidence_metrics`);
4. evaluates a shadow regime verdict using the SAME frozen threshold
   constants John's production gate already uses
   (``activation_scorer_v2.REGIME_GATE_MIN_*``), with only the
   evidence-count input substituted for the group-deduplicated count
   (:func:`evaluate_shadow_regime_verdict`);
5. assembles the full additive sidecar payload for one run
   (:func:`build_alpha_evidence_integrity_payload`).

Complexity: candidates are bucketed by a blocking key (ticker, factor
signature, assertion status, numeric/date signature) before any pairwise
comparison, so near-match comparison is bounded within (typically small)
buckets -- never an unbounded O(n^2) scan of the full candidate pool.

Grouping is a pure function of its inputs and is order-independent:
processing candidates in a different order produces the same groups (a
union-find keyed by claim_id, merged via priority-ordered passes, each pass
itself iterating in a stable, sorted order).
"""

from __future__ import annotations

import hashlib
import json
import re
from collections.abc import Iterable, Mapping, Sequence
from dataclasses import asdict, dataclass
from typing import Any

from comqutor_alpha.graph_engine.activation_scorer_v2 import (
    REGIME_GATE_MIN_DISTINCT_AGENTS,
    REGIME_GATE_MIN_LOCAL_EDGES,
    REGIME_GATE_MIN_LOCAL_STRUCTURE_SUPPORT,
    REGIME_GATE_MIN_SCORE,
    REGIME_GATE_MIN_TICKER_SPECIFIC,
    REGIME_GATE_MIN_UNIQUE_EVIDENCE,
)
from comqutor_alpha.structure_engine.claim_quality import (
    CONSUMER_ACTIVATION,
    EVENT_PREDICATE_TERMS,
    is_claim_eligible,
)
from comqutor_alpha.structure_engine.factor_normalizer import normalize_factor_label

EVIDENCE_INTEGRITY_SCHEMA_VERSION = "week_regime_evidence_integrity.v1"

# ---------------------------------------------------------------------------
# Shadow regime verdict statuses.
# ---------------------------------------------------------------------------

STATUS_CONSISTENT = "CONSISTENT"
STATUS_OVERLAP_RISK = "OVERLAP_RISK"
STATUS_INSUFFICIENT_PRIMARY_EVIDENCE = "INSUFFICIENT_PRIMARY_EVIDENCE"
STATUS_UNVERIFIED_EXPOSURE = "UNVERIFIED_EXPOSURE"
STATUS_NOT_REGIME_CANDIDATE = "NOT_REGIME_CANDIDATE"
VALID_INTEGRITY_STATUSES = frozenset(
    {
        STATUS_CONSISTENT,
        STATUS_OVERLAP_RISK,
        STATUS_INSUFFICIENT_PRIMARY_EVIDENCE,
        STATUS_UNVERIFIED_EXPOSURE,
        STATUS_NOT_REGIME_CANDIDATE,
    }
)

_REGIME_LEVEL_STATUS = "regime_level"

# ---------------------------------------------------------------------------
# Signature helpers (text-only, deterministic, no ML/embeddings).
# ---------------------------------------------------------------------------

_NUMBER_TOKEN_PATTERN = re.compile(r"-?\d+(?:[.,]\d+)*%?")
_MONTH_TOKEN_PATTERN = re.compile(
    r"\b(?:january|february|march|april|may|june|july|august|september|october|november|december"
    r"|jan|feb|mar|apr|jun|jul|aug|sep|sept|oct|nov|dec)\b",
    re.IGNORECASE,
)
_FISCAL_PERIOD_PATTERN = re.compile(r"\bfy ?20\d\d\b|\bq[1-4] ?(?:fy ?)?20\d\d\b", re.IGNORECASE)
_WORD_TOKEN_PATTERN = re.compile(r"[a-z0-9]+")
# Reuses claim_quality's own EVENT_PREDICATE_TERMS vocabulary (imported, not
# re-derived) so "which event predicate is present" can never drift from
# the Claim Quality Gate's own definition.
_EVENT_TERM_PATTERN = re.compile(
    "|".join(
        r"\b" + r"\s+".join(re.escape(word) for word in term.split()) + r"\b"
        for term in sorted(EVENT_PREDICATE_TERMS, key=len, reverse=True)
    ),
    re.IGNORECASE,
)


def _numeric_signature(text: str) -> str:
    return "|".join(sorted(_NUMBER_TOKEN_PATTERN.findall(text)))


def _date_signature(text: str) -> str:
    lowered = text.lower()
    months = sorted({m.lower()[:3] for m in _MONTH_TOKEN_PATTERN.findall(lowered)})
    fiscal = sorted({f.lower().replace(" ", "") for f in _FISCAL_PERIOD_PATTERN.findall(lowered)})
    return "|".join(months + fiscal)


def _event_signature(text: str) -> str:
    return "|".join(sorted({m.lower() for m in _EVENT_TERM_PATTERN.findall(text)}))


def _factor_signature(factors: Sequence[Any]) -> str:
    canonical = sorted({normalize_factor_label(f) for f in factors if str(f or "").strip()})
    return "|".join(c for c in canonical if c)


def _token_set(text: str) -> frozenset[str]:
    return frozenset(_WORD_TOKEN_PATTERN.findall(text.lower()))


def _jaccard(a: frozenset[str], b: frozenset[str]) -> float:
    if not a and not b:
        return 1.0
    union = a | b
    if not union:
        return 0.0
    return len(a & b) / len(union)


# ---------------------------------------------------------------------------
# Candidate assembly.
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class _Candidate:
    claim_id: str
    agent: str
    source_agent_output_id: str
    claim_text: str
    matched_alpha: str
    match_score: float
    factors: tuple[str, ...]
    assertion_status: str
    semantic_polarity: str
    duplicate_group_id: str | None
    relation_triple: tuple[str, str, str, str] | None
    factor_signature: str
    numeric_signature: str
    date_signature: str
    event_signature: str
    token_set: frozenset[str]


def _duplicate_group_index(
    structured_records: Iterable[Mapping[str, Any]] | None,
) -> dict[str, str]:
    index: dict[str, str] = {}
    for record in structured_records or ():
        if not isinstance(record, Mapping):
            continue
        claim_id = str(record.get("claim_id") or "")
        group_id = record.get("duplicate_group_id")
        if claim_id and isinstance(group_id, str) and group_id.strip():
            index[claim_id] = group_id.strip()
    return index


def _relation_triple_index(
    graph_edges: Sequence[Mapping[str, Any]] | None,
) -> dict[str, tuple[str, str, str, str]]:
    """One relation triple per claim_id: (source, edge_type, target,
    assertion_status) for the first admitted structure-graph edge that
    claim contributed to. Uses the *graph's own* edges (post
    ``build_structure_graph``, which carries ``claim_ids``) -- never the
    raw ``extracted_structures.json`` edges, which key claims under a
    different field name."""
    index: dict[str, tuple[str, str, str, str]] = {}
    for edge in graph_edges or ():
        if not isinstance(edge, Mapping):
            continue
        source = str(edge.get("source") or "")
        target = str(edge.get("target") or "")
        edge_type = str(edge.get("edge_type") or "")
        assertion_status = str(edge.get("assertion_status") or "unknown")
        triple = (source, edge_type, target, assertion_status)
        for claim_id in edge.get("claim_ids") or ():
            claim_id = str(claim_id or "").strip()
            if claim_id and claim_id not in index:
                index[claim_id] = triple
    return index


def _build_candidates(
    alpha_matches_payload: Mapping[str, Any],
    *,
    graph_edges: Sequence[Mapping[str, Any]] | None,
    structured_records: Iterable[Mapping[str, Any]] | None,
) -> list[_Candidate]:
    matches = alpha_matches_payload.get("matches") if isinstance(alpha_matches_payload, Mapping) else None
    if not isinstance(matches, list):
        return []

    duplicate_group_ids = _duplicate_group_index(structured_records)
    relation_triples = _relation_triple_index(graph_edges)

    candidates: list[_Candidate] = []
    seen_claim_ids: set[str] = set()
    for record in matches:
        if not isinstance(record, Mapping):
            continue
        if record.get("match_status") != "matched":
            continue
        matched_alpha = str(record.get("matched_alpha") or "").strip()
        if not matched_alpha:
            continue
        # Same quality gate every other Activation consumer uses -- never a
        # separately-invented eligibility check.
        if not is_claim_eligible(record, CONSUMER_ACTIVATION):
            continue
        claim_id = str(record.get("claim_id") or "").strip()
        if not claim_id or claim_id in seen_claim_ids:
            continue
        seen_claim_ids.add(claim_id)

        claim_text = str(record.get("claim") or record.get("evidence") or "")
        factors = tuple(str(f) for f in (record.get("factors") or []) if str(f or "").strip())
        assertion_status = str(record.get("assertion_status") or "unknown").strip().lower()
        semantic_polarity = str(record.get("semantic_polarity") or "unknown").strip().lower()
        combined_text = f"{claim_text} {record.get('evidence') or ''}"

        candidates.append(
            _Candidate(
                claim_id=claim_id,
                agent=str(record.get("agent") or "").strip(),
                source_agent_output_id=str(record.get("source_agent_output_id") or "").strip(),
                claim_text=claim_text,
                matched_alpha=matched_alpha,
                match_score=float(record.get("score") or 0.0),
                factors=factors,
                assertion_status=assertion_status,
                semantic_polarity=semantic_polarity,
                duplicate_group_id=duplicate_group_ids.get(claim_id),
                relation_triple=relation_triples.get(claim_id),
                factor_signature=_factor_signature(factors),
                numeric_signature=_numeric_signature(combined_text),
                date_signature=_date_signature(combined_text),
                event_signature=_event_signature(combined_text),
                token_set=_token_set(claim_text),
            )
        )
    return sorted(candidates, key=lambda c: c.claim_id)


# ---------------------------------------------------------------------------
# Deterministic grouping (union-find over a priority-ordered set of merge
# passes; blocking keys bound the O(n^2)-shaped lexical-near-match pass to
# small buckets).
# ---------------------------------------------------------------------------


class _UnionFind:
    def __init__(self, items: Iterable[str]) -> None:
        self._parent = {item: item for item in items}

    def find(self, item: str) -> str:
        root = item
        while self._parent[root] != root:
            root = self._parent[root]
        while self._parent[item] != root:
            self._parent[item], item = root, self._parent[item]
        return root

    def union(self, a: str, b: str) -> None:
        ra, rb = self.find(a), self.find(b)
        if ra == rb:
            return
        # Stable, deterministic tie-break: the lexicographically smaller
        # claim_id always becomes the root, independent of call order.
        if rb < ra:
            ra, rb = rb, ra
        self._parent[rb] = ra


def _blocking_key(candidate: _Candidate, ticker: str) -> tuple[str, str, str, str, str]:
    return (
        ticker,
        candidate.factor_signature,
        candidate.assertion_status,
        candidate.numeric_signature,
        candidate.date_signature,
    )


def _group_candidates(candidates: Sequence[_Candidate], ticker: str) -> list[list[_Candidate]]:
    if not candidates:
        return []
    uf = _UnionFind(c.claim_id for c in candidates)
    by_claim_id = {c.claim_id: c for c in candidates}

    # Priority 1: explicit duplicate_group_id (stable, authoritative).
    by_dup_group: dict[str, list[str]] = {}
    for c in candidates:
        if c.duplicate_group_id:
            by_dup_group.setdefault(c.duplicate_group_id, []).append(c.claim_id)
    for claim_ids in by_dup_group.values():
        ordered = sorted(claim_ids)
        for other in ordered[1:]:
            uf.union(ordered[0], other)

    # Priority 2: identical legal relation triple (source, edge_type,
    # target, assertion_status) -- claims backing the exact same admitted
    # structure-graph edge are, by that edge's own definition, the same
    # structural fact.
    by_relation: dict[tuple[str, str, str, str], list[str]] = {}
    for c in candidates:
        if c.relation_triple:
            by_relation.setdefault(c.relation_triple, []).append(c.claim_id)
    for claim_ids in by_relation.values():
        ordered = sorted(claim_ids)
        for other in ordered[1:]:
            uf.union(ordered[0], other)

    # Blocking buckets for priorities 3 and 4 -- ticker + factor signature +
    # assertion status + numeric/date signature. Comparisons below never
    # cross a bucket boundary.
    buckets: dict[tuple[str, str, str, str, str], list[str]] = {}
    for c in candidates:
        buckets.setdefault(_blocking_key(c, ticker), []).append(c.claim_id)

    # Priority 3: exact canonical factor/event signature match within a
    # bucket (semantic polarity and event signature must also agree exactly
    # -- the blocking key alone already pins ticker/factor/assertion/
    # numeric/date). Pairwise (not a plain dict-group-by) specifically so
    # the same relation-endpoint safety check priority 4 uses also applies
    # here: two candidates each backing a *different* established
    # structure-graph relation triple must never merge merely because their
    # factor/polarity/event signature happens to coincide.
    for bucket_claim_ids in sorted(buckets.values(), key=lambda ids: sorted(ids)):
        ordered = sorted(bucket_claim_ids)
        for i in range(len(ordered)):
            for j in range(i + 1, len(ordered)):
                a = by_claim_id[ordered[i]]
                b = by_claim_id[ordered[j]]
                if uf.find(a.claim_id) == uf.find(b.claim_id):
                    continue
                if a.semantic_polarity != b.semantic_polarity:
                    continue
                if a.event_signature != b.event_signature:
                    continue
                if a.relation_triple and b.relation_triple and a.relation_triple != b.relation_triple:
                    continue
                uf.union(a.claim_id, b.claim_id)

    # Priority 4: conservative lexical near-match within a bucket. Every
    # pairwise comparison additionally requires exact semantic-polarity
    # agreement and, when either candidate has an established relation
    # triple, that the triples agree too (never lexical-merge across a
    # claim with a different, explicit structural relation).
    for bucket_claim_ids in sorted(buckets.values(), key=lambda ids: sorted(ids)):
        ordered = sorted(bucket_claim_ids)
        for i in range(len(ordered)):
            for j in range(i + 1, len(ordered)):
                a = by_claim_id[ordered[i]]
                b = by_claim_id[ordered[j]]
                if uf.find(a.claim_id) == uf.find(b.claim_id):
                    continue
                if a.semantic_polarity != b.semantic_polarity:
                    continue
                if a.relation_triple and b.relation_triple and a.relation_triple != b.relation_triple:
                    continue
                if _jaccard(a.token_set, b.token_set) >= 0.85:
                    uf.union(a.claim_id, b.claim_id)

    groups: dict[str, list[_Candidate]] = {}
    for c in candidates:
        root = uf.find(c.claim_id)
        groups.setdefault(root, []).append(c)
    return [sorted(members, key=lambda c: c.claim_id) for members in groups.values()]


# ---------------------------------------------------------------------------
# Evidence group assembly + primary/secondary attribution.
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class EvidenceGroup:
    evidence_group_id: str
    run_id: str
    ticker: str
    claim_ids: tuple[str, ...]
    agents: tuple[str, ...]
    source_refs: tuple[str, ...]
    factor_signature: str
    relation_signature: str | None
    numeric_signature: str
    assertion_status: str
    semantic_polarity: str
    supported_alpha_ids: tuple[str, ...]
    primary_alpha_id: str | None
    secondary_alpha_ids: tuple[str, ...]
    group_confidence: float

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


def _evidence_group_id(run_id: str, ticker: str, claim_ids: Sequence[str]) -> str:
    """Stable canonical-payload hash -- never a random UUID. A pure
    function of (run_id, ticker, the group's own member claim_ids), so
    re-running this module over the same inputs always reproduces the same
    ids, and the id is independent of input processing order."""
    payload = json.dumps(
        {"run_id": run_id, "ticker": ticker, "claim_ids": sorted(claim_ids)},
        sort_keys=True,
    )
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()[:24]


def _attribute_primary_secondary(members: Sequence[_Candidate]) -> tuple[str | None, tuple[str, ...]]:
    """Primary Alpha selection, in the spec's stated priority order:

    1. already Mapper-admitted -- trivially true for every member here
       (only ``match_status == "matched"`` candidates ever reach this
       function);
    2. higher existing match score;
    3. more alpha-specific matched factors (also stands in for priority 4,
       "relation endpoints more directly tied to alpha factors": a claim
       matched on more of an alpha's own factors is, by construction, more
       directly tied to that alpha's factor set -- no ticker-specific or
       alpha-specific keyword rule is added);
    4. stable alpha_id tie-break.

    Never introduces a ticker-specific or alpha-specific rule -- every
    input here already came from the existing, frozen Mapper admission.
    """
    by_alpha: dict[str, list[_Candidate]] = {}
    for member in members:
        by_alpha.setdefault(member.matched_alpha, []).append(member)
    if not by_alpha:
        return None, ()

    def _strength(alpha_id: str) -> tuple[float, int]:
        members_for_alpha = by_alpha[alpha_id]
        best_score = max(m.match_score for m in members_for_alpha)
        most_factors = max(len(m.factors) for m in members_for_alpha)
        return (best_score, most_factors)

    ordered_alphas = sorted(
        by_alpha, key=lambda alpha_id: (-_strength(alpha_id)[0], -_strength(alpha_id)[1], alpha_id)
    )
    return ordered_alphas[0], tuple(ordered_alphas[1:])


def build_evidence_groups(
    alpha_matches_payload: Mapping[str, Any],
    *,
    run_id: str,
    ticker: str,
    graph_edges: Sequence[Mapping[str, Any]] = (),
    structured_records: Iterable[Mapping[str, Any]] | None = None,
) -> list[EvidenceGroup]:
    """Build deterministic, cross-Alpha Evidence Groups from one run's
    already quality-filtered, Mapper-admitted claims.

    Every group is attributed a primary Alpha and zero or more secondary
    Alphas; no admitted Alpha association is ever dropped -- a group
    supporting multiple Alphas keeps every one of them, split only into
    primary/secondary metadata. Deterministic and input-order independent.
    """
    candidates = _build_candidates(
        alpha_matches_payload, graph_edges=graph_edges, structured_records=structured_records
    )
    grouped = _group_candidates(candidates, ticker)

    results: list[EvidenceGroup] = []
    for members in grouped:
        claim_ids = tuple(sorted({m.claim_id for m in members}))
        agents = tuple(sorted({m.agent for m in members if m.agent}))
        source_refs = tuple(sorted({m.source_agent_output_id for m in members if m.source_agent_output_id}))
        # A group can legitimately mix members whose individual assertion
        # status/polarity/numeric signature differ only when they were
        # merged via priority 1/2 (duplicate_group_id or an identical
        # relation triple, both of which are authoritative regardless of
        # surface text); report the majority/first-sorted value rather than
        # requiring uniformity that priority-1/2 merges do not guarantee.
        assertion_statuses = sorted({m.assertion_status for m in members})
        semantic_polarities = sorted({m.semantic_polarity for m in members})
        factor_signatures = sorted({m.factor_signature for m in members if m.factor_signature})
        numeric_signatures = sorted({m.numeric_signature for m in members if m.numeric_signature})
        relation_triples = sorted({m.relation_triple for m in members if m.relation_triple})

        primary_alpha_id, secondary_alpha_ids = _attribute_primary_secondary(members)
        supported_alpha_ids = tuple(
            sorted({m.matched_alpha for m in members if m.matched_alpha})
        )
        group_confidence = round(max((m.match_score for m in members), default=0.0), 4)

        results.append(
            EvidenceGroup(
                evidence_group_id=_evidence_group_id(run_id, ticker, claim_ids),
                run_id=run_id,
                ticker=ticker,
                claim_ids=claim_ids,
                agents=agents,
                source_refs=source_refs,
                factor_signature=factor_signatures[0] if len(factor_signatures) == 1 else "|".join(factor_signatures),
                relation_signature=(
                    ">".join(relation_triples[0]) if len(relation_triples) == 1 else None
                ),
                numeric_signature=numeric_signatures[0] if len(numeric_signatures) == 1 else "|".join(numeric_signatures),
                assertion_status=assertion_statuses[0] if len(assertion_statuses) == 1 else "mixed",
                semantic_polarity=semantic_polarities[0] if len(semantic_polarities) == 1 else "mixed",
                supported_alpha_ids=supported_alpha_ids,
                primary_alpha_id=primary_alpha_id,
                secondary_alpha_ids=secondary_alpha_ids,
                group_confidence=group_confidence,
            )
        )

    return sorted(results, key=lambda g: g.evidence_group_id)


# ---------------------------------------------------------------------------
# Per-Alpha evidence metrics.
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class AlphaEvidenceMetrics:
    alpha_id: str
    raw_evidence_claim_count: int
    deduplicated_claim_count: int
    independent_evidence_group_count: int
    primary_evidence_group_count: int
    secondary_evidence_group_count: int
    distinct_agent_count: int
    distinct_source_ref_count: int
    structured_relation_group_count: int
    overlap_ratio: float

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


def compute_alpha_evidence_metrics(
    alpha_id: str,
    groups: Sequence[EvidenceGroup],
    candidates_for_alpha: Sequence[_Candidate],
) -> AlphaEvidenceMetrics:
    raw_evidence_claim_count = len(candidates_for_alpha)

    # "Obvious duplicate" tier only (exact duplicate_group_id or byte-
    # identical claim text) -- deliberately coarser than the full grouping
    # below, so raw >= deduplicated >= independent are three genuinely
    # different, all-preserved numbers (spec: "不得用一个覆盖另一个").
    exact_dup_keys = {
        c.duplicate_group_id or f"text:{c.claim_text.strip().lower()}" for c in candidates_for_alpha
    }
    deduplicated_claim_count = len(exact_dup_keys)

    supporting_groups = [g for g in groups if alpha_id in g.supported_alpha_ids]
    primary_groups = [g for g in supporting_groups if g.primary_alpha_id == alpha_id]
    secondary_groups = [g for g in supporting_groups if alpha_id in g.secondary_alpha_ids]
    structured_relation_groups = [g for g in supporting_groups if g.relation_signature]

    independent_evidence_group_count = len(supporting_groups)
    distinct_agent_count = len({c.agent for c in candidates_for_alpha if c.agent})
    distinct_source_ref_count = len(
        {c.source_agent_output_id for c in candidates_for_alpha if c.source_agent_output_id}
    )
    overlap_ratio = round(
        1.0 - independent_evidence_group_count / max(raw_evidence_claim_count, 1), 4
    )

    return AlphaEvidenceMetrics(
        alpha_id=alpha_id,
        raw_evidence_claim_count=raw_evidence_claim_count,
        deduplicated_claim_count=deduplicated_claim_count,
        independent_evidence_group_count=independent_evidence_group_count,
        primary_evidence_group_count=len(primary_groups),
        secondary_evidence_group_count=len(secondary_groups),
        distinct_agent_count=distinct_agent_count,
        distinct_source_ref_count=distinct_source_ref_count,
        structured_relation_group_count=len(structured_relation_groups),
        overlap_ratio=overlap_ratio,
    )


# ---------------------------------------------------------------------------
# Shadow regime verdict.
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class ShadowRegimeVerdict:
    alpha_id: str
    production_status: str
    production_regime_eligible: bool
    shadow_regime_eligible: bool | None
    shadow_regime_failures: tuple[str, ...]
    regime_evidence_integrity_status: str

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


def _evaluate_shadow_gate(
    *,
    activation_score: float,
    independent_evidence_group_count: int,
    distinct_agents: int,
    ticker_specific_count: int,
    local_edge_count: int,
    local_structure_raw: float,
    integrity_warnings: Sequence[str],
) -> tuple[bool, list[str]]:
    """Re-evaluates John's own seven frozen regime-qualification thresholds
    (imported, not redefined) with exactly one input substituted:
    ``independent_evidence_group_count`` in place of production's own
    (already per-alpha semantically deduplicated) ``unique_evidence_count``.
    Every other input is production's own already-computed value -- this
    function does not, and must not, alter John's production gate itself
    (``activation_scorer_v2._evaluate_regime_gate``), which stays
    byte-for-byte unchanged and is never called from here."""
    failures: list[str] = []
    if activation_score < REGIME_GATE_MIN_SCORE:
        failures.append("SCORE_BELOW_REGIME_THRESHOLD")
    if independent_evidence_group_count < REGIME_GATE_MIN_UNIQUE_EVIDENCE:
        failures.append("INSUFFICIENT_INDEPENDENT_EVIDENCE_FOR_REGIME")
    if distinct_agents < REGIME_GATE_MIN_DISTINCT_AGENTS:
        failures.append("INSUFFICIENT_SUPPORTING_AGENTS_FOR_REGIME")
    if ticker_specific_count < REGIME_GATE_MIN_TICKER_SPECIFIC:
        failures.append("INSUFFICIENT_TICKER_SPECIFIC_EVIDENCE_FOR_REGIME")
    if local_edge_count < REGIME_GATE_MIN_LOCAL_EDGES:
        failures.append("NO_LOCAL_STRUCTURE_FOR_REGIME")
    if local_structure_raw < REGIME_GATE_MIN_LOCAL_STRUCTURE_SUPPORT:
        failures.append("INSUFFICIENT_LOCAL_STRUCTURE_STRENGTH_FOR_REGIME")
    if integrity_warnings:
        failures.append("EVIDENCE_INTEGRITY_WARNING")
    return (not failures), failures


def evaluate_shadow_regime_verdict(
    *,
    alpha_id: str,
    production_alpha_result: Mapping[str, Any],
    independent_evidence_group_count: int,
    primary_evidence_group_count: int,
    exposure_value: float | None,
) -> ShadowRegimeVerdict:
    """Compute the shadow regime verdict for one alpha.

    Priority order (evaluated in this exact sequence):

    1. production status != "regime_level" -> NOT_REGIME_CANDIDATE. Shadow
       analysis is only meaningful once production itself already believes
       an alpha is regime-level -- evaluating exposure/overlap for an
       alpha nowhere near regime level would be diagnostic noise.
    2. exposure_value is None -> UNVERIFIED_EXPOSURE (never assumes 0, 1,
       or fabricates a seed).
    3. exposure is available: re-evaluate the seven gates with
       independent_evidence_group_count substituted for unique_evidence_count.
       A failure (necessarily the evidence-count gate, since every other
       input is pinned to production's own already-passing value) ->
       OVERLAP_RISK.
    4. shadow gate passes but primary_evidence_group_count itself falls
       short of the same evidence threshold (the alpha only reaches the
       bar by counting groups where it is a *secondary* attribution) ->
       INSUFFICIENT_PRIMARY_EVIDENCE. Diagnostic only -- does not flip
       shadow_regime_eligible to False and is never treated as a new gate.
    5. otherwise -> CONSISTENT.
    """
    production_status = str(production_alpha_result.get("status") or "unknown")
    production_regime_eligible = production_status == _REGIME_LEVEL_STATUS

    if not production_regime_eligible:
        return ShadowRegimeVerdict(
            alpha_id=alpha_id,
            production_status=production_status,
            production_regime_eligible=False,
            shadow_regime_eligible=None,
            shadow_regime_failures=(),
            regime_evidence_integrity_status=STATUS_NOT_REGIME_CANDIDATE,
        )

    if exposure_value is None:
        return ShadowRegimeVerdict(
            alpha_id=alpha_id,
            production_status=production_status,
            production_regime_eligible=True,
            shadow_regime_eligible=None,
            shadow_regime_failures=(),
            regime_evidence_integrity_status=STATUS_UNVERIFIED_EXPOSURE,
        )

    activation_score = float(production_alpha_result.get("activation_score") or 0.0)
    distinct_agents = int(production_alpha_result.get("distinct_supporting_agents") or 0)
    ticker_specific_count = int(production_alpha_result.get("ticker_specific_evidence_count") or 0)
    local_edge_count = int(production_alpha_result.get("local_edge_count") or 0)
    local_structure_raw = float(
        (production_alpha_result.get("components") or {}).get("local_structure_support", {}).get("raw") or 0.0
    )
    integrity_warnings = production_alpha_result.get("evidence_integrity_warnings") or ()

    shadow_passed, shadow_failures = _evaluate_shadow_gate(
        activation_score=activation_score,
        independent_evidence_group_count=independent_evidence_group_count,
        distinct_agents=distinct_agents,
        ticker_specific_count=ticker_specific_count,
        local_edge_count=local_edge_count,
        local_structure_raw=local_structure_raw,
        integrity_warnings=integrity_warnings,
    )

    if not shadow_passed:
        status = STATUS_OVERLAP_RISK
    elif primary_evidence_group_count < REGIME_GATE_MIN_UNIQUE_EVIDENCE:
        status = STATUS_INSUFFICIENT_PRIMARY_EVIDENCE
    else:
        status = STATUS_CONSISTENT

    return ShadowRegimeVerdict(
        alpha_id=alpha_id,
        production_status=production_status,
        production_regime_eligible=True,
        shadow_regime_eligible=shadow_passed,
        shadow_regime_failures=tuple(shadow_failures),
        regime_evidence_integrity_status=status,
    )


# ---------------------------------------------------------------------------
# Top-level orchestration: one run's full additive sidecar payload.
# ---------------------------------------------------------------------------


def build_alpha_evidence_integrity_payload(
    *,
    run_id: str,
    ticker: str,
    alpha_matches_payload: Mapping[str, Any],
    activation_v2_alphas: Sequence[Mapping[str, Any]],
    graph_edges: Sequence[Mapping[str, Any]] = (),
    structured_records: Iterable[Mapping[str, Any]] | None = None,
    exposure_by_alpha: Mapping[str, float] | None = None,
) -> dict[str, Any]:
    """Assemble the full, additive Evidence Integrity sidecar for one run.

    Pure function of its inputs; performs no I/O and never mutates any
    argument. Intended to be embedded as an internal, versioned
    ``alpha_evidence_integrity`` block inside ``run_audit.json`` (never a
    public Research API field, never surfaced in Agent Findings) or written
    to a standalone ``evidence_integrity.json`` sidecar -- the choice of
    where to persist this payload is the caller's, not this module's.
    """
    exposure_by_alpha = exposure_by_alpha or {}
    candidates = _build_candidates(
        alpha_matches_payload, graph_edges=graph_edges, structured_records=structured_records
    )
    groups = build_evidence_groups(
        alpha_matches_payload,
        run_id=run_id,
        ticker=ticker,
        graph_edges=graph_edges,
        structured_records=structured_records,
    )
    candidates_by_alpha: dict[str, list[_Candidate]] = {}
    for c in candidates:
        candidates_by_alpha.setdefault(c.matched_alpha, []).append(c)

    alpha_entries: list[dict[str, Any]] = []
    for production_alpha in sorted(activation_v2_alphas, key=lambda a: str(a.get("alpha_id"))):
        alpha_id = str(production_alpha.get("alpha_id"))
        alpha_candidates = candidates_by_alpha.get(alpha_id, ())
        metrics = compute_alpha_evidence_metrics(alpha_id, groups, alpha_candidates)
        primary_groups = [
            g.to_dict() for g in groups if g.primary_alpha_id == alpha_id
        ]
        secondary_groups = [
            g.to_dict() for g in groups if alpha_id in g.secondary_alpha_ids
        ]
        verdict = evaluate_shadow_regime_verdict(
            alpha_id=alpha_id,
            production_alpha_result=production_alpha,
            independent_evidence_group_count=metrics.independent_evidence_group_count,
            primary_evidence_group_count=metrics.primary_evidence_group_count,
            exposure_value=exposure_by_alpha.get(alpha_id),
        )
        alpha_entries.append(
            {
                "alpha_id": alpha_id,
                "production_score": production_alpha.get("activation_score"),
                "production_status": production_alpha.get("status"),
                "metrics": metrics.to_dict(),
                "primary_evidence_groups": primary_groups,
                "secondary_evidence_groups": secondary_groups,
                "shadow_regime_verdict": verdict.to_dict(),
            }
        )

    return {
        "schema_version": EVIDENCE_INTEGRITY_SCHEMA_VERSION,
        "run_id": run_id,
        "ticker": ticker,
        "evidence_groups": [g.to_dict() for g in groups],
        "alphas": alpha_entries,
    }


__all__ = [
    "EVIDENCE_INTEGRITY_SCHEMA_VERSION",
    "STATUS_CONSISTENT",
    "STATUS_OVERLAP_RISK",
    "STATUS_INSUFFICIENT_PRIMARY_EVIDENCE",
    "STATUS_UNVERIFIED_EXPOSURE",
    "STATUS_NOT_REGIME_CANDIDATE",
    "VALID_INTEGRITY_STATUSES",
    "EvidenceGroup",
    "AlphaEvidenceMetrics",
    "ShadowRegimeVerdict",
    "build_evidence_groups",
    "compute_alpha_evidence_metrics",
    "evaluate_shadow_regime_verdict",
    "build_alpha_evidence_integrity_payload",
]
