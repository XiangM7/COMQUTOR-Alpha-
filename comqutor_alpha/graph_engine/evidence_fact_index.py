"""Canonical Evidence Fact Index (Structure Integrity Repair Sprint, Track 2).

The single, shared near-paraphrase-aware evidence-grouping algorithm used by
BOTH production Activation v2 scoring
(``activation_scorer_v2._evidence_quality_component`` /
``_agent_independence_component``) AND the Evidence Integrity shadow audit
layer (``evidence_integrity.py``). Before this sprint each layer grouped
evidence with its own logic -- production only merged byte-identical
(normalized) claim text or an explicit ``duplicate_group_id`` stamped by
segmentation-level dedup, while the shadow layer additionally merged
cross-agent near-paraphrases via relation-triple/factor-signature agreement
and a conservative token-Jaccard near-match pass. That divergence is exactly
why the same alpha could show production ``unique_evidence_count == 11``
and shadow ``independent_evidence_group_count == 5`` for the same run: two
different, silently-inconsistent definitions of "one independent fact."
There is now exactly one grouping implementation; every consumer listed
above must call :func:`group_evidence_candidates` rather than deriving an
equivalent grouping key of its own.

Deterministic and order-independent: every merge pass iterates its
candidates in a stable, sorted order, and a union-find keyed by claim_id
means the final grouping never depends on input processing order. No LLM,
no unbounded semantic embedding -- purely deterministic text signatures
(numeric/date/fiscal-period/event-predicate/canonical-factor) plus a
bounded, blocked, conservative token-Jaccard near-match pass.
"""

from __future__ import annotations

import hashlib
import json
import re
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from typing import Any

from comqutor_alpha.graph_engine.claim_data_grounding import dependency_anchors
from comqutor_alpha.graph_engine.evidence_consumption import (
    REASON_STANCE_MODEL_NOT_SUPPORTING,
    effective_text_rule,
    positive_admission_exclusion,
)
from comqutor_alpha.graph_engine.graph_schema import is_finite_number
from comqutor_alpha.structure_engine.claim_quality import (
    CONSUMER_ACTIVATION,
    EVENT_PREDICATE_TERMS,
    is_claim_eligible,
)
from comqutor_alpha.structure_engine.factor_normalizer import normalize_factor_label

EVIDENCE_FACT_INDEX_VERSION = "evidence_fact_index.v1"

# ---------------------------------------------------------------------------
# Canonical relation resolution + supporting-evidence eligibility (Evidence
# Integrity Completion Sprint, Track A). Moved here (not duplicated) so
# Activation v2 production scoring and the Evidence Integrity shadow layer
# import the exact same resolver/filter -- the previous split (Activation
# had its own private ``_relation_for_match``/``QUALIFYING_RELATIONS``, the
# shadow layer had none at all) was exactly why the two consumers still
# disagreed on which raw claims are even eligible to be counted, even after
# sharing one grouping algorithm.
# ---------------------------------------------------------------------------

ALPHA_ACTIVATION_EVIDENCE_V1 = "alpha_activation_evidence.v1"

QUALIFYING_RELATIONS = frozenset({"activation", "conditional", "mixed"})

REASON_NON_ANALYTICAL_QUALITY = "NON_ANALYTICAL_QUALITY"
REASON_MISSING_CLAIM_ID_OR_EVIDENCE = "MISSING_CLAIM_ID_OR_EVIDENCE"
REASON_INVALID_MATCH_SCORE = "INVALID_MATCH_SCORE"
REASON_RELATION_NOT_SUPPORTING = "RELATION_NOT_SUPPORTING"
REASON_ASSERTION_NEGATED = "ASSERTION_NEGATED"
# T1 follow-up migration (alpha_evidence_consumption.v2, R-1): the one reason code for a claim a MODEL-JUDGED stance keeps out
# of this Alpha's positive pool. Defined in graph_engine.evidence_consumption so every entry reads the same constant.
REASON_STANCE_NOT_SUPPORTING = REASON_STANCE_MODEL_NOT_SUPPORTING
REASON_DUPLICATE_CLAIM_ID = "DUPLICATE_CLAIM_ID"
WARNING_NON_FINITE_OR_OUT_OF_RANGE_MATCH_SCORE = "NON_FINITE_OR_OUT_OF_RANGE_MATCH_SCORE"


def relation_for_match(record: Mapping[str, Any], alpha_id: str) -> str:
    """Read back the Alpha Mapper's own resolved relation for ``alpha_id``
    from whichever candidate pool the record carries it in. Never
    recomputes semantics -- only surfaces what the mapper already
    attached."""
    for pool_key in ("eligible_candidates", "top_candidates", "candidate_scores"):
        pool = record.get(pool_key)
        if not isinstance(pool, list):
            continue
        for candidate in pool:
            if isinstance(candidate, Mapping) and str(candidate.get("alpha_id")) == alpha_id:
                return str(candidate.get("relation") or "unknown").strip().lower()
    return "unknown"


def select_supporting_alpha_claims(
    matches: Sequence[Mapping[str, Any]] | None,
    alpha_id: str,
    *,
    policy_version: str = ALPHA_ACTIVATION_EVIDENCE_V1,
) -> tuple[list[Mapping[str, Any]], list[dict[str, Any]], list[str]]:
    """The single canonical "is this claim eligible SUPPORTING evidence for
    this alpha" filter (Evidence Integrity Completion Sprint, Track A).

    Every consumer that needs a claim_id -> supporting-evidence-eligible
    raw match record set for one alpha (Activation production scoring, the
    Evidence Integrity shadow layer, Conflict Detector, Run Audit, API
    evidence statistics) must call this instead of re-deriving an
    equivalent filter. Returns ``(eligible_records, excluded, warnings)``:

    - ``eligible_records``: the raw match dict for each claim_id that
      passed every gate, deduplicated by claim_id (first occurrence wins),
      sorted by claim_id.
    - ``excluded``: one ``{"claim_id", "reason"}`` entry per claim relevant
      to this alpha (committed match, ``matched_alpha == alpha_id``) that
      failed a later gate -- never silent.
    - ``warnings``: stable integrity warning codes (e.g. a non-finite/out-
      of-range match score), matching Activation v2's existing contract.

    ``policy_version`` is currently always ``ALPHA_ACTIVATION_EVIDENCE_V1``
    (Activation's own frozen "supporting evidence" definition: committed
    match, analytical claim quality, relation in
    ``{activation, conditional, mixed}``, assertion status not negated) --
    kept as an explicit parameter, not a hardcoded assumption, so a future
    second policy can be added without breaking this contract.
    """
    if not isinstance(matches, Sequence) or isinstance(matches, (str, bytes)):
        return [], [], []

    warnings: list[str] = []
    excluded: list[dict[str, Any]] = []
    by_claim_id: dict[str, Mapping[str, Any]] = {}
    for record in matches:
        if not isinstance(record, Mapping):
            continue
        if record.get("match_status") != "matched":
            continue
        if str(record.get("matched_alpha") or "") != alpha_id:
            continue

        claim_id = str(record.get("claim_id") or "").strip()

        if not is_claim_eligible(record, CONSUMER_ACTIVATION):
            if claim_id:
                excluded.append({"claim_id": claim_id, "reason": REASON_NON_ANALYTICAL_QUALITY})
            continue

        evidence_text = str(record.get("evidence") or record.get("claim") or "").strip()
        if not claim_id or not evidence_text:
            excluded.append({"claim_id": claim_id or None, "reason": REASON_MISSING_CLAIM_ID_OR_EVIDENCE})
            continue

        score = record.get("score", None)
        if not is_finite_number(score) or not 0.0 <= float(score) <= 1.0:
            warnings.append(WARNING_NON_FINITE_OR_OUT_OF_RANGE_MATCH_SCORE)
            excluded.append({"claim_id": claim_id, "reason": REASON_INVALID_MATCH_SCORE})
            continue

        # alpha_evidence_consumption.v2 (alpha_statement_scope): under the contract the relation / assertion gates read the
        # block's per-pair negation scope (a negator that does not govern this Alpha's statement no longer turns the whole claim
        # into a mention); a legacy record has no block and reads the stored text-rule fields exactly as before.
        effective = effective_text_rule(record, alpha_id)
        relation = (
            str(effective.get("relation") or "unknown").strip().lower() if effective is not None else relation_for_match(record, alpha_id)
        )
        if relation not in QUALIFYING_RELATIONS:
            excluded.append(
                {"claim_id": claim_id, "reason": REASON_RELATION_NOT_SUPPORTING, "relation": relation}
            )
            continue

        assertion_status = str(
            (effective.get("assertion_status") if effective is not None else record.get("assertion_status")) or "unknown"
        ).strip().lower()
        if assertion_status == "negated":
            excluded.append({"claim_id": claim_id, "reason": REASON_ASSERTION_NEGATED})
            continue

        # alpha_evidence_consumption.v2 (R-1): an explicit, subtractive positive-admission field -- NOT a rewritten relation.
        # Legacy records carry no consumption block and are never affected; an invalid block raises (never a silent fallback).
        stance_exclusion = positive_admission_exclusion(record, alpha_id)
        if stance_exclusion is not None:
            excluded.append(
                {"claim_id": claim_id, "reason": stance_exclusion["reason_code"], "label": stance_exclusion.get("label")}
            )
            continue

        if claim_id in by_claim_id:
            excluded.append({"claim_id": claim_id, "reason": REASON_DUPLICATE_CLAIM_ID})
            continue

        by_claim_id[claim_id] = record

    eligible = [by_claim_id[claim_id] for claim_id in sorted(by_claim_id)]
    return eligible, excluded, sorted(set(warnings))


def evidence_fact_group_id(run_id: str, ticker: str, claim_ids: Sequence[str]) -> str:
    """Stable canonical-payload hash -- never a random UUID, never a
    processing-order-dependent string. A pure function of (run_id, ticker,
    the group's own member claim_ids), so the SAME run/ticker/claim-id-set
    always produces the SAME group id everywhere it is computed (Activation
    production scoring, the Evidence Integrity shadow layer, Conflict
    Detector, Run Audit) -- one canonical id scheme, never independently
    reinvented per consumer."""
    payload = json.dumps(
        {"run_id": run_id, "ticker": ticker, "claim_ids": sorted(claim_ids)},
        sort_keys=True,
    )
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()[:24]

_NUMBER_TOKEN_PATTERN = re.compile(r"-?\d+(?:[.,]\d+)*%?")
_MONTH_TOKEN_PATTERN = re.compile(
    r"\b(?:january|february|march|april|may|june|july|august|september|october|november|december"
    r"|jan|feb|mar|apr|jun|jul|aug|sep|sept|oct|nov|dec)\b",
    re.IGNORECASE,
)
_FISCAL_PERIOD_PATTERN = re.compile(r"\bfy ?20\d\d\b|\bq[1-4] ?(?:fy ?)?20\d\d\b", re.IGNORECASE)
_WORD_TOKEN_PATTERN = re.compile(r"[a-z0-9]+")
_EVENT_TERM_PATTERN = re.compile(
    "|".join(
        r"\b" + r"\s+".join(re.escape(word) for word in term.split()) + r"\b"
        for term in sorted(EVENT_PREDICATE_TERMS, key=len, reverse=True)
    ),
    re.IGNORECASE,
)

NEAR_MATCH_JACCARD_THRESHOLD = 0.85


def numeric_signature(text: str) -> str:
    return "|".join(sorted(_NUMBER_TOKEN_PATTERN.findall(text)))


def date_signature(text: str) -> str:
    lowered = text.lower()
    months = sorted({m.lower()[:3] for m in _MONTH_TOKEN_PATTERN.findall(lowered)})
    fiscal = sorted({f.lower().replace(" ", "") for f in _FISCAL_PERIOD_PATTERN.findall(lowered)})
    return "|".join(months + fiscal)


def event_signature(text: str) -> str:
    return "|".join(sorted({m.lower() for m in _EVENT_TERM_PATTERN.findall(text)}))


def factor_signature(factors: Sequence[Any]) -> str:
    canonical = sorted({normalize_factor_label(f) for f in factors if str(f or "").strip()})
    return "|".join(c for c in canonical if c)


def token_set(text: str) -> frozenset[str]:
    return frozenset(_WORD_TOKEN_PATTERN.findall(text.lower()))


def _jaccard(a: frozenset[str], b: frozenset[str]) -> float:
    if not a and not b:
        return 1.0
    union = a | b
    if not union:
        return 0.0
    return len(a & b) / len(union)


@dataclass(frozen=True)
class EvidenceFactCandidate:
    """One piece of evidence eligible to be grouped. ``claim_id`` must be
    unique across the candidate pool passed to one
    :func:`group_evidence_candidates` call.

    ``linked_source_id`` (T1 source-linking chain, COMQUTOR Alpha
    next-round task, 2026-09-26): this claim's own already-validated
    ``comqutor_alpha.source_provenance.validate_source_reference`` result
    (``SOURCE_LINK_VALID`` only -- never a candidate/unvalidated id). Two
    claims that cite the SAME real, validated underlying source are, by
    definition, not independent evidence, however differently worded --
    this is a strong, ID-based merge signal, checked before the text-
    signature/Jaccard passes below and independent of them. ``None`` (no
    validated link, or a historical claim predating this field) never
    merges anything on this basis alone -- every other pass still applies
    unchanged."""

    claim_id: str
    claim_text: str
    factors: tuple[str, ...] = ()
    assertion_status: str = "unknown"
    semantic_polarity: str = "unknown"
    duplicate_group_id: str | None = None
    relation_triple: tuple[str, str, str, str] | None = None
    linked_source_id: str | None = None
    # T1 closure (claim_data_points.v1, ``claim_data_grounding``): the saved observations this claim literally
    # states (``data_stated``) and all it relies on (``data_inputs`` = stated + the inputs of a reproduced
    # calculation). Empty -> the dependency pass below never fires for this claim (legacy grouping, byte-identical).
    data_stated: tuple[str, ...] = ()
    data_inputs: tuple[str, ...] = ()


@dataclass(frozen=True)
class _Signed:
    candidate: EvidenceFactCandidate
    factor_signature: str
    numeric_signature: str
    date_signature: str
    event_signature: str
    token_set: frozenset[str]


def _sign(candidate: EvidenceFactCandidate) -> _Signed:
    return _Signed(
        candidate=candidate,
        factor_signature=factor_signature(candidate.factors),
        numeric_signature=numeric_signature(candidate.claim_text),
        date_signature=date_signature(candidate.claim_text),
        event_signature=event_signature(candidate.claim_text),
        token_set=token_set(candidate.claim_text),
    )


class _UnionFind:
    def __init__(self, items) -> None:
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


def _blocking_key(signed: _Signed, ticker: str) -> tuple[str, str, str, str, str]:
    return (
        ticker,
        signed.factor_signature,
        signed.candidate.assertion_status,
        signed.numeric_signature,
        signed.date_signature,
    )


def group_evidence_candidates(
    candidates: Sequence[EvidenceFactCandidate], ticker: str = ""
) -> list[list[EvidenceFactCandidate]]:
    """Deterministically group ``candidates`` into Evidence Facts.

    Priority-ordered union-find merge passes (identical semantics for every
    caller -- production Activation and the shadow audit layer alike):

    1. explicit ``duplicate_group_id`` (stable, authoritative);
    2. identical legal relation triple (source, edge_type, target,
       assertion_status) -- claims backing the exact same admitted
       structure-graph edge are, by that edge's own definition, the same
       structural fact;
    3. exact canonical factor/event signature match within a
       (ticker, factor_signature, assertion_status, numeric_signature,
       date_signature) blocking bucket, requiring semantic polarity
       agreement and no conflicting relation triple;
    4. conservative token-Jaccard near-match (>= 0.85) within the same
       blocking bucket, with the same polarity/relation-triple safety
       checks -- never a plain global string-similarity scan.

    Never merges across a different ticker, a conflicting numeric/date
    signature, a conflicting assertion status, a conflicting semantic
    polarity, or a conflicting already-established relation triple.
    """
    if not candidates:
        return []
    signed_by_id = {c.claim_id: _sign(c) for c in candidates}
    uf = _UnionFind(signed_by_id)

    by_dup_group: dict[str, list[str]] = {}
    for c in candidates:
        if c.duplicate_group_id:
            by_dup_group.setdefault(c.duplicate_group_id, []).append(c.claim_id)
    for claim_ids in by_dup_group.values():
        ordered = sorted(claim_ids)
        for other in ordered[1:]:
            uf.union(ordered[0], other)

    by_relation: dict[tuple[str, str, str, str], list[str]] = {}
    for c in candidates:
        if c.relation_triple:
            by_relation.setdefault(c.relation_triple, []).append(c.claim_id)
    for claim_ids in by_relation.values():
        ordered = sorted(claim_ids)
        for other in ordered[1:]:
            uf.union(ordered[0], other)

    buckets: dict[tuple[str, str, str, str, str], list[str]] = {}
    for claim_id, signed in signed_by_id.items():
        buckets.setdefault(_blocking_key(signed, ticker), []).append(claim_id)

    for bucket_claim_ids in sorted(buckets.values(), key=lambda ids: sorted(ids)):
        ordered = sorted(bucket_claim_ids)
        for i in range(len(ordered)):
            for j in range(i + 1, len(ordered)):
                a = signed_by_id[ordered[i]]
                b = signed_by_id[ordered[j]]
                if uf.find(a.candidate.claim_id) == uf.find(b.candidate.claim_id):
                    continue
                # An empty factor signature and an empty event signature are
                # not a real signal that two claims describe the same fact
                # -- they are simply "neither claim mentioned a known factor
                # or event predicate." Requiring at least one non-empty
                # signature here prevents two claims about completely
                # unrelated topics from merging merely because both lack
                # extracted factors (the blocking key alone cannot guard
                # against this: an empty signature trivially equals another
                # empty signature).
                if not a.factor_signature and not a.event_signature:
                    continue
                if a.candidate.semantic_polarity != b.candidate.semantic_polarity:
                    continue
                if a.event_signature != b.event_signature:
                    continue
                if (
                    a.candidate.relation_triple
                    and b.candidate.relation_triple
                    and a.candidate.relation_triple != b.candidate.relation_triple
                ):
                    continue
                uf.union(a.candidate.claim_id, b.candidate.claim_id)

    for bucket_claim_ids in sorted(buckets.values(), key=lambda ids: sorted(ids)):
        ordered = sorted(bucket_claim_ids)
        for i in range(len(ordered)):
            for j in range(i + 1, len(ordered)):
                a = signed_by_id[ordered[i]]
                b = signed_by_id[ordered[j]]
                if uf.find(a.candidate.claim_id) == uf.find(b.candidate.claim_id):
                    continue
                if a.candidate.semantic_polarity != b.candidate.semantic_polarity:
                    continue
                if (
                    a.candidate.relation_triple
                    and b.candidate.relation_triple
                    and a.candidate.relation_triple != b.candidate.relation_triple
                ):
                    continue
                if _jaccard(a.token_set, b.token_set) >= NEAR_MATCH_JACCARD_THRESHOLD:
                    uf.union(a.candidate.claim_id, b.candidate.claim_id)

    # T1 source-linking chain (COMQUTOR Alpha next-round task, 2026-09-26,
    # tightened 2026-09-28 per explicit review: "不要仅凭签名不冲突就断定两个
    # 内容是同一个事实"): claims sharing the same VALIDATED linked_source_id
    # trace to the identical underlying source -- but a shared source_id is
    # NEVER used as a fact identity on its own (one article can report
    # several distinct, non-contradictory facts too, e.g. "revenue beat
    # estimates" and "the company hired a new CFO" -- absence of a
    # signature CONFLICT is not evidence of SAMENESS). This pass now
    # requires BOTH:
    #   1. no conflicting deterministic signature (semantic polarity must
    #      agree -- a same-source supporting claim is never merged with a
    #      same-source OPPOSING one, direction is never lost to a merge --
    #      and any of numeric/date/event/relation_triple BOTH sides
    #      actually carry must agree where present); AND
    #   2. POSITIVE evidence the two claims describe the SAME fact: a
    #      shared non-empty factor_signature, a shared non-empty
    #      event_signature, a shared relation_triple, OR the SAME strict
    #      token-Jaccard threshold the standalone near-match pass already
    #      uses (NEAR_MATCH_JACCARD_THRESHOLD -- no new, weaker threshold
    #      invented just for this pass). A shared source lowers evidentiary
    #      friction for wording differences of an ALREADY-similar pair; it
    #      is never, by itself, proof that two otherwise-unrelated
    #      sentences are the same fact.
    by_linked_source: dict[str, list[str]] = {}
    for c in candidates:
        if c.linked_source_id:
            by_linked_source.setdefault(c.linked_source_id, []).append(c.claim_id)
    for claim_ids in by_linked_source.values():
        ordered = sorted(claim_ids)
        for i in range(len(ordered)):
            for j in range(i + 1, len(ordered)):
                a = signed_by_id[ordered[i]]
                b = signed_by_id[ordered[j]]
                if uf.find(a.candidate.claim_id) == uf.find(b.candidate.claim_id):
                    continue
                if a.candidate.semantic_polarity != b.candidate.semantic_polarity:
                    continue
                if a.numeric_signature and b.numeric_signature and a.numeric_signature != b.numeric_signature:
                    continue
                if a.date_signature and b.date_signature and a.date_signature != b.date_signature:
                    continue
                if a.event_signature and b.event_signature and a.event_signature != b.event_signature:
                    continue
                if (
                    a.candidate.relation_triple
                    and b.candidate.relation_triple
                    and a.candidate.relation_triple != b.candidate.relation_triple
                ):
                    continue
                same_fact_signal = (
                    (a.factor_signature and a.factor_signature == b.factor_signature)
                    or (a.event_signature and a.event_signature == b.event_signature)
                    or (
                        a.candidate.relation_triple is not None
                        and a.candidate.relation_triple == b.candidate.relation_triple
                    )
                    or _jaccard(a.token_set, b.token_set) >= NEAR_MATCH_JACCARD_THRESHOLD
                )
                if not same_fact_signal:
                    continue
                uf.union(a.candidate.claim_id, b.candidate.claim_id)

    # T1 closure (claim_data_points.v1): a claim that is a DERIVED EXPRESSION of another claim's saved observations
    # (every observation it relies on is one the other claim literally states) is the same underlying evidence, so
    # it joins that claim's group instead of adding an independent fact. Deliberately narrow: sharing a source, or
    # sharing only some observations, never merges (see claim_data_grounding.dependency_anchors); an opposite
    # semantic polarity never merges (a contradiction about the same numbers is not a restatement); and a claim
    # with no grounded observations is untouched, so every run without the data-point annotation groups exactly
    # as before.
    if any(c.data_inputs for c in candidates):
        anchors = dependency_anchors(
            {c.claim_id: c.data_inputs for c in candidates if c.data_inputs},
            {c.claim_id: c.data_stated for c in candidates if c.data_stated},
        )
        for claim_id, anchor_id in sorted(anchors.items()):
            if signed_by_id[claim_id].candidate.semantic_polarity != signed_by_id[anchor_id].candidate.semantic_polarity:
                continue
            uf.union(claim_id, anchor_id)

    groups: dict[str, list[EvidenceFactCandidate]] = {}
    for c in candidates:
        root = uf.find(c.claim_id)
        groups.setdefault(root, []).append(c)
    return [sorted(members, key=lambda c: c.claim_id) for members in groups.values()]


def relation_triple_index(
    graph_edges: Sequence[Mapping[str, Any]] | None,
) -> dict[str, tuple[str, str, str, str]]:
    """One relation triple per claim_id: (source, edge_type, target,
    assertion_status) for the first admitted structure-graph edge that
    claim contributed to. Uses the graph's own edges (post
    ``build_structure_graph``) and prefers each edge's ``source_claim_ids``
    (the real, Alpha-Mapper-linkable claim pool -- see
    ``graph_builder``/Track 1) over its legacy ``claim_ids`` field when
    present, so a canonical-relation edge's real lineage claims get a
    relation-triple key too, not just deterministically-extracted ones."""
    index: dict[str, tuple[str, str, str, str]] = {}
    for edge in graph_edges or ():
        if not isinstance(edge, Mapping):
            continue
        source = str(edge.get("source") or "")
        target = str(edge.get("target") or "")
        edge_type = str(edge.get("edge_type") or "")
        assertion_status = str(edge.get("assertion_status") or "unknown")
        triple = (source, edge_type, target, assertion_status)
        claim_pool = edge.get("source_claim_ids")
        if claim_pool is None:
            claim_pool = edge.get("claim_ids") or ()
        for claim_id in claim_pool:
            claim_id = str(claim_id or "").strip()
            if claim_id and claim_id not in index:
                index[claim_id] = triple
    return index


__all__ = [
    "EVIDENCE_FACT_INDEX_VERSION",
    "NEAR_MATCH_JACCARD_THRESHOLD",
    "ALPHA_ACTIVATION_EVIDENCE_V1",
    "QUALIFYING_RELATIONS",
    "REASON_NON_ANALYTICAL_QUALITY",
    "REASON_MISSING_CLAIM_ID_OR_EVIDENCE",
    "REASON_INVALID_MATCH_SCORE",
    "REASON_RELATION_NOT_SUPPORTING",
    "REASON_ASSERTION_NEGATED",
    "REASON_DUPLICATE_CLAIM_ID",
    "WARNING_NON_FINITE_OR_OUT_OF_RANGE_MATCH_SCORE",
    "relation_for_match",
    "select_supporting_alpha_claims",
    "evidence_fact_group_id",
    "EvidenceFactCandidate",
    "group_evidence_candidates",
    "relation_triple_index",
    "numeric_signature",
    "date_signature",
    "event_signature",
    "factor_signature",
    "token_set",
]
