"""Round 9 (2026-10-06): real LLM content-support verification -- the task
that actually judges whether a claim's own stated PROPOSITION is supported
by this run's own saved source material, replacing Round 8's "strip
numbers/dates/field-names, check residual is empty" approach for anything
beyond a pure data-fact/derived-calc statement (Round 8's deterministic
checker is KEPT, unmodified, as the cheaper first attempt and as a
mechanical corroboration input to this task -- see
``comqutor_alpha.source_provenance.verify_data_fact_or_derived_calculation``).

Responsibility split (per this round's task spec):
  * LLM = semantic authority. It reads the claim's own proposition plus the
    REAL, already-saved source material this run allows for THIS claim, and
    judges the support relationship -- never asked to confirm an external
    fact is true in the world, only whether the SAVED MATERIAL supports the
    CLAIM.
  * This module (program) = contract authority only: identity (claim_id
    matches the request), that the cited source is one of THIS request's
    own allowed candidates (never the whole registry), that the cited
    quote/data field is REAL (found verbatim/within tolerance in the
    source's own saved content), object/unit/period/time consistency, and
    content-hash freshness. It never re-judges whether a structurally valid
    LLM verdict "sounds right" semantically.
  * The existing scoring modules (activation/conflict/exposure) are
    unchanged -- this module only ever writes
    ``content_support_status``/``content_support_method``/
    ``content_support_review`` (plus the additive diagnostic fields below),
    exactly the fields Round 8's automated verifier already writes, via the
    SAME ``AUTOMATICALLY_ELIGIBLE_REVIEW_METHODS`` gate.

Reuses, never duplicates:
  * ``comqutor_alpha.structure_engine.week2_llm.Week2LLMGateway`` -- the
    same shared gateway, retry/timeout/budget/cache machinery every other
    Week 2 semantic task already uses, via one new registered task name
    (``content_support_verification``).
  * ``comqutor_alpha.source_provenance.verify_data_fact_or_derived_
    calculation`` -- reused as BOTH a cheaper first attempt (a pure data
    fact never needs a real Provider call) and as mechanical-check input
    handed to the LLM for any numbers the claim also states.
  * ``comqutor_alpha.source_provenance.resolve_fragment_by_id`` /
    ``resolve_source_by_id`` -- the same real source-resolution functions
    the deterministic source-link chain already uses.
"""

from __future__ import annotations

import re
import threading
from collections.abc import Mapping, Sequence
from typing import Any

from comqutor_alpha.source_provenance import (
    REVIEW_METHOD_LLM_CONTENT_SUPPORT_VERIFIED,
    SOURCE_LINK_VALID,
    SUPPORT_BACKGROUND,
    SUPPORT_CITATION_ONLY,
    SUPPORT_CONDITIONAL,
    SUPPORT_OPPOSES,
    SUPPORT_PENDING_REVIEW,
    SUPPORT_SUPPORTS,
    build_content_support_review,
    resolve_fragment_by_id,
    resolve_source_by_id,
    verify_data_fact_or_derived_calculation,
)
from comqutor_alpha.source_provenance import (
    _all_numeric_values_in_source as _all_numeric_values_in_source,
    _parse_claim_numbers as _parse_claim_numbers,
    _value_matches_any as _value_matches_any,
)

LLM_TASK_NAME = "content_support_verification"
# v1 identity preserved permanently -- every record a v1 call ever produced
# keeps this exact string stamped in its own content_support_llm_detail.
# schema_version forever.
LLM_METHOD_VERSION_V1 = "content_support.llm.v1"
# v2 identity preserved for history too -- NEVER sent to a real Provider
# call under this exact identity (confirmed: every real execution to date
# is v1-shaped; v2 only ever ran in zero-cost fixed-response tests) before
# the v2.1 correction below replaced it. Kept distinct, never silently
# reused for v2.1's different text, per "同一身份不能对应不同文本".
LLM_METHOD_VERSION_V2 = "content_support.llm.v2"
# v2.1 (2026-10-06, limited real-verification round): the active version.
# Diff from v2 -- see _v2_structural_contradiction's own docstring and
# week2_llm.py's _TASK_RUNTIME_METADATA entry for the full prompt diff:
# (1) inference_assumptions is no longer forced non-empty for GROUNDED_
# INFERENCE (a real inference needing no assumption must not be rejected
# on a format technicality); (2) a NON_MATERIAL materiality judgment now
# requires a real, non-empty rationale (never a bare label).
LLM_METHOD_VERSION = "content_support.llm.v2.1"

# --- section 3: the exact six-value response vocabulary this task's own
# prompt requires, mapped onto the EXISTING content_support_status
# vocabulary (source_provenance.py) -- no new status values invented.
# INSUFFICIENT maps to PENDING_REVIEW: "not enough saved material to judge"
# is honestly still unresolved, never promoted to any resolved status.
STATUS_SUPPORTS = "SUPPORTS"
STATUS_OPPOSES = "OPPOSES"
STATUS_BACKGROUND = "BACKGROUND"
STATUS_CITATION_ONLY = "CITATION_ONLY"
STATUS_CONDITIONAL = "CONDITIONAL"
STATUS_INSUFFICIENT = "INSUFFICIENT"

VALID_RESPONSE_STATUSES = frozenset(
    {STATUS_SUPPORTS, STATUS_OPPOSES, STATUS_BACKGROUND, STATUS_CITATION_ONLY, STATUS_CONDITIONAL, STATUS_INSUFFICIENT}
)

# v2 (2026-10-06): the LLM's own disclosed basis for a SUPPORTS/OPPOSES/
# CONDITIONAL verdict -- a TradingAgents report is a restatement/summary/
# analysis, never a transcript, so "the source already says this verbatim"
# (DIRECT_FACT) is only one of several legitimate real bases; faithful
# paraphrase, real recomputation, and a disclosed, reasonable inference are
# equally real support. Required precisely when a basis is meaningful
# (SUPPORTS/OPPOSES/CONDITIONAL); NONE for BACKGROUND/CITATION_ONLY/
# INSUFFICIENT, where there is no support relationship to attribute a basis to.
SUPPORT_BASIS_DIRECT_FACT = "DIRECT_FACT"
SUPPORT_BASIS_SEMANTIC_PARAPHRASE = "SEMANTIC_PARAPHRASE"
SUPPORT_BASIS_DERIVED_CALCULATION = "DERIVED_CALCULATION"
SUPPORT_BASIS_GROUNDED_INFERENCE = "GROUNDED_INFERENCE"
SUPPORT_BASIS_NONE = "NONE"

VALID_SUPPORT_BASES = frozenset(
    {
        SUPPORT_BASIS_DIRECT_FACT,
        SUPPORT_BASIS_SEMANTIC_PARAPHRASE,
        SUPPORT_BASIS_DERIVED_CALCULATION,
        SUPPORT_BASIS_GROUNDED_INFERENCE,
        SUPPORT_BASIS_NONE,
    }
)

_SUPPORT_BASES_REQUIRING_INFERENCE_DISCLOSURE = frozenset(
    {SUPPORT_BASIS_DERIVED_CALCULATION, SUPPORT_BASIS_GROUNDED_INFERENCE}
)

# v2: replaces v1's blanket "any non-empty unsupported_remainder ->
# CONDITIONAL" mechanical rule with the LLM's own disclosed materiality
# judgment -- MATERIAL (changes the claim's own object/causal-or-
# comparative relationship/direction/certainty) still downgrades exactly as
# strictly as v1 always did; NON_MATERIAL (a genuinely minor rhetorical
# add-on riding alongside an otherwise fully-supported core fact) no longer
# does. This is an LLM judgment, never inferred by this module from text.
MATERIALITY_NONE = "NONE"
MATERIALITY_NON_MATERIAL = "NON_MATERIAL"
MATERIALITY_MATERIAL = "MATERIAL"

VALID_MATERIALITY = frozenset({MATERIALITY_NONE, MATERIALITY_NON_MATERIAL, MATERIALITY_MATERIAL})

_STATUS_TO_CONTENT_SUPPORT_STATUS = {
    STATUS_SUPPORTS: SUPPORT_SUPPORTS,
    STATUS_OPPOSES: SUPPORT_OPPOSES,
    STATUS_BACKGROUND: SUPPORT_BACKGROUND,
    STATUS_CITATION_ONLY: SUPPORT_CITATION_ONLY,
    STATUS_CONDITIONAL: SUPPORT_CONDITIONAL,
    STATUS_INSUFFICIENT: SUPPORT_PENDING_REVIEW,
}

# --- fallback reason vocabulary (section 4: never silently become NONE or
# SUPPORTS -- every rejection is a distinct, recorded reason, and the
# record's content_support_status is left exactly as it already was). ---
FALLBACK_PROVIDER_ERROR = "provider_error"
FALLBACK_TIMEOUT = "timeout"
FALLBACK_BUDGET_EXHAUSTED = "budget_exhausted"
FALLBACK_MALFORMED_RESPONSE = "malformed_response"
FALLBACK_MISSING_RESULT = "missing_result"
FALLBACK_DUPLICATE_RESULT = "duplicate_result"
FALLBACK_IDENTITY_MISMATCH = "identity_mismatch"
FALLBACK_INVALID_STATUS = "invalid_status"
FALLBACK_SOURCE_NOT_IN_CANDIDATES = "source_not_in_candidates"
FALLBACK_QUOTE_OR_DATA_NOT_FOUND = "quote_or_data_not_found"
FALLBACK_TIME_INVALID = "time_invalid"
FALLBACK_CONTENT_HASH_STALE = "content_hash_stale"
# 2026-10-06 (Phase C controlled single-request verification round):
# distinct from FALLBACK_PROVIDER_ERROR -- this means the request was
# NEVER sent (or, for a response-save failure, a later one was never
# sent) because Week2LLMGateway's own wire-level audit record failed to
# persist, not because the Provider itself returned an error.
FALLBACK_AUDIT_WRITE_FAILED = "audit_write_failed"
# v2 (2026-10-06): the LLM's OWN structured answer is internally
# inconsistent -- e.g. status=SUPPORTS with support_basis=NONE (claims
# support but discloses no basis for it), or unsupported_remainder empty
# while materiality != NONE (or vice versa), or support_basis requiring
# inference disclosure (DERIVED_CALCULATION/GROUNDED_INFERENCE) with no
# inference_facts given. This is a mechanical, structural self-consistency
# check on the response's OWN declared fields -- never a semantic
# re-judgment of whether the verdict "sounds right" -- and is recorded
# distinctly so "the LLM contradicted itself" is never silently resolved
# by picking whichever field looks more favorable.
FALLBACK_INTERNAL_CONTRADICTION = "internal_contradiction"

VALID_FALLBACK_REASONS = frozenset(
    {
        FALLBACK_PROVIDER_ERROR,
        FALLBACK_TIMEOUT,
        FALLBACK_BUDGET_EXHAUSTED,
        FALLBACK_MALFORMED_RESPONSE,
        FALLBACK_MISSING_RESULT,
        FALLBACK_DUPLICATE_RESULT,
        FALLBACK_IDENTITY_MISMATCH,
        FALLBACK_INVALID_STATUS,
        FALLBACK_SOURCE_NOT_IN_CANDIDATES,
        FALLBACK_QUOTE_OR_DATA_NOT_FOUND,
        FALLBACK_TIME_INVALID,
        FALLBACK_CONTENT_HASH_STALE,
        FALLBACK_AUDIT_WRITE_FAILED,
        FALLBACK_INTERNAL_CONTRADICTION,
    }
)

BATCH_SIZE = 5  # smaller than evidence_stance_classifier's 10: each item's
# payload is much larger here (real excerpt/data_snapshot content, not just
# a claim/evidence string), so a smaller batch keeps request size bounded.

_REQUIRED_RESPONSE_ITEM_KEYS = frozenset({"claim_id", "status"})
_ALLOWED_RESPONSE_ITEM_KEYS = frozenset(
    {
        "claim_id",
        "status",
        "used_source_id",
        "used_location",
        "supporting_quote_or_data",
        "rationale",
        "supported_proposition",
        "unsupported_remainder",
        # v2 additive fields
        "core_proposition",
        "support_basis",
        "inference_facts",
        "inference_assumptions",
        "unsupported_remainder_materiality",
    }
)


def _candidate_for_claim(record: Mapping[str, Any], sources: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """The LIMITED, per-claim allowed-candidate set -- never the whole
    registry (section 2's explicit requirement). Reuses exactly the
    source(s) the deterministic source-link chain already resolved for THIS
    claim: ``linked_source_id`` (the primary) plus ``linked_source_ids``
    (Round 3's additive plural field for a genuinely multi-source claim),
    when present. A claim with no resolved link at all gets an empty
    candidate list -- this task never searches the registry on its own."""
    if record.get("source_link_status") != SOURCE_LINK_VALID:
        return []
    ids: list[str] = []
    primary = record.get("linked_source_id")
    if primary:
        ids.append(str(primary))
    for extra in record.get("linked_source_ids") or ():
        extra = str(extra or "")
        if extra and extra not in ids:
            ids.append(extra)
    candidates = []
    for source_id in ids:
        resolved = resolve_fragment_by_id(source_id, sources) or resolve_source_by_id(source_id, sources)
        if resolved is not None:
            candidates.append(resolved)
    return candidates


def _public_candidate_fields(source: Mapping[str, Any]) -> dict[str, Any]:
    """Only the REAL, already-saved fields the LLM needs to judge support --
    never a title/URL alone (section 2's explicit requirement: no bare
    metadata standing in for actual content)."""
    return {
        "source_id": source.get("source_id"),
        "fragment_id": source.get("fragment_id"),
        "source_type": source.get("source_type"),
        "instrument": source.get("instrument"),
        "observation_date": source.get("observation_date"),
        "published_at": source.get("published_at"),
        "unit": source.get("unit"),
        "excerpt": source.get("excerpt"),
        "data_snapshot": source.get("data_snapshot"),
    }


def _report_context_for_claim(
    record: Mapping[str, Any], records_by_agent_output_id: Mapping[str, list[Mapping[str, Any]]]
) -> dict[str, Any]:
    """v2 (2026-10-06): this claim's OWN agent's other claims from the SAME
    report section (``source_agent_output_id``) -- already-available real
    data (no new raw-text fetch), given to the LLM ONLY to resolve
    pronouns/referents and recover the surrounding argument structure.
    Explicitly labeled as context, never citable evidence -- the prompt
    itself repeats this, and this module never treats report_context as a
    candidate source (it is never added to candidates_by_id, so even a
    returned used_source_id naming it would fail the real candidate-
    membership check in _validate_response_item)."""
    source_agent_output_id = record.get("source_agent_output_id")
    own_claim_id = str(record.get("claim_id") or "")
    siblings = records_by_agent_output_id.get(source_agent_output_id, []) if source_agent_output_id else []
    neighbors = [
        {"claim_index": sibling.get("claim_index"), "text": str(sibling.get("claim") or sibling.get("evidence") or "")}
        for sibling in siblings
        if str(sibling.get("claim_id") or "") != own_claim_id
    ]
    neighbors.sort(key=lambda item: (item["claim_index"] is None, item["claim_index"]))
    return {
        "note": (
            "CONTEXT ONLY -- these are this claim's own Agent's other claims from the same report "
            "section, given solely to resolve pronouns/referents and recover the surrounding "
            "argument. This is the Agent's own paraphrase, never independent evidence -- never cite "
            "it as support."
        ),
        "neighboring_claims": neighbors,
    }


def _mechanical_checks_hint(record: Mapping[str, Any], candidates: list[dict[str, Any]]) -> dict[str, Any]:
    """Section 2's "已有派生计算的输入...可以保留，作为 LLM 判断的输入及
    机械检查" -- a claim that FAILED Round 8's strict whole-claim gate
    (residual text present, so it was never fully auto-verified) can still
    have some of its own individual numbers independently confirmed real.
    Reported here as an honest, narrow auxiliary signal -- never a claim
    that the whole proposition is verified (that remains the LLM's own job
    to judge from the full material)."""
    claim_text = str(record.get("claim") or record.get("evidence") or "")
    claim_numbers = _parse_claim_numbers(claim_text)
    if not claim_numbers:
        return {"claim_numbers_independently_confirmed_in_source": []}
    universe: set[float] = set()
    for candidate in candidates:
        universe |= _all_numeric_values_in_source(candidate)
    confirmed = [value for value in claim_numbers if _value_matches_any(value, universe)]
    return {"claim_numbers_independently_confirmed_in_source": confirmed}


def build_content_support_request_items(
    records: Sequence[Mapping[str, Any]], sources: list[dict[str, Any]]
) -> list["ContentSupportRequestItem"]:
    """One request item per claim that (a) has a real, resolved source link
    and (b) was NOT already resolved by Round 8's cheaper deterministic
    verifier (a pure data fact never needs a real Provider call -- see
    ``verify_data_fact_or_derived_calculation``). A claim with no candidate
    source at all is never submitted (section 2: never a bare title/URL
    stand-in, and nothing for the LLM to judge against)."""
    # v2 (2026-10-06): grouped once, up front, from the SAME records list
    # already passed in -- no new raw-output fetch -- so report_context can
    # give each claim its own agent's OTHER claims from the same section.
    records_by_agent_output_id: dict[str, list[Mapping[str, Any]]] = {}
    for candidate_record in records:
        if not isinstance(candidate_record, Mapping):
            continue
        agent_output_id = candidate_record.get("source_agent_output_id")
        if agent_output_id:
            records_by_agent_output_id.setdefault(agent_output_id, []).append(candidate_record)

    items: list[ContentSupportRequestItem] = []
    for record in records:
        if not isinstance(record, Mapping):
            continue
        claim_id = record.get("claim_id")
        if not claim_id:
            continue
        if record.get("source_link_status") != SOURCE_LINK_VALID:
            continue
        mechanical = verify_data_fact_or_derived_calculation(record, sources)
        if mechanical is not None:
            continue  # already resolved, cheaper and already proven -- no Provider call needed
        candidates = _candidate_for_claim(record, sources)
        if not candidates:
            continue
        payload = {
            "claim_id": str(claim_id),
            "ticker": str(record.get("ticker") or ""),
            "proposition": str(record.get("claim") or ""),
            "context": {
                "evidence_text": str(record.get("evidence") or ""),
                "source_section": record.get("source_section"),
                "agent": record.get("agent"),
            },
            "report_context": _report_context_for_claim(record, records_by_agent_output_id),
            "allowed_candidates": [_public_candidate_fields(c) for c in candidates],
            "mechanical_checks": _mechanical_checks_hint(record, candidates),
        }
        items.append(
            ContentSupportRequestItem(
                claim_id=str(claim_id), payload=payload, record=record, candidates_by_id={
                    str(c.get("source_id")): c for c in candidates
                }
            )
        )
    return items


class ContentSupportRequestItem:
    __slots__ = ("claim_id", "payload", "record", "candidates_by_id")

    def __init__(self, *, claim_id: str, payload: dict[str, Any], record: Mapping[str, Any], candidates_by_id: dict[str, Any]) -> None:
        self.claim_id = claim_id
        self.payload = payload
        self.record = record
        self.candidates_by_id = candidates_by_id


def chunk_items(items: Sequence[ContentSupportRequestItem], size: int = BATCH_SIZE) -> list[list[ContentSupportRequestItem]]:
    return [list(items[i : i + size]) for i in range(0, len(items), size)]


def _validate_batch_shape(payload: Any) -> list[Any]:
    """Batch-level structural validator only (passed to
    ``invoke_json_with_trace``) -- per-item identity/vocabulary/citation
    legality is checked separately in ``_validate_response_item``, so one
    bad item never fails the others."""
    if not isinstance(payload, Mapping):
        raise TypeError("content_support_verification response must be a JSON object")
    items = payload.get("items")
    if not isinstance(items, list):
        raise TypeError("content_support_verification response missing an items array")
    return items


def _reason_from_invocation(invocation: Any) -> str:
    status = getattr(invocation, "provider_status", None)
    error_code = getattr(invocation, "error_code", None)
    if status == "timeout":
        return FALLBACK_TIMEOUT
    if status == "budget_exhausted" or error_code == "WEEK2_LLM_CALL_BUDGET_EXHAUSTED":
        return FALLBACK_BUDGET_EXHAUSTED
    if status == "audit_unavailable" or error_code == "WEEK2_LLM_AUDIT_WRITE_FAILED":
        return FALLBACK_AUDIT_WRITE_FAILED
    if error_code in {"WEEK2_LLM_INVALID_JSON", "WEEK2_LLM_VALIDATION_FAILED", "WEEK2_LLM_INPUT_TOO_LARGE"}:
        return FALLBACK_MALFORMED_RESPONSE
    return FALLBACK_PROVIDER_ERROR


def _quote_found_in_excerpt(quote: str, excerpt: str) -> bool:
    quote = quote.strip()
    if not quote:
        return False
    return quote in excerpt


def _data_field_found(value_text: str, data_snapshot: Any) -> bool:
    """Best-effort real-field check: walks the WHOLE source data_snapshot
    (not only the LLM's own claimed ``used_location`` path -- this function
    deliberately does not trust that path string either, only confirms the
    cited VALUE is real somewhere in the source) for a leaf whose
    stringified value matches ``value_text`` -- the SAME kind of real,
    re-checkable comparison Round 8's deterministic verifier already
    performs, reused here to corroborate the LLM's own citation rather than
    trusting it blindly."""
    if not isinstance(data_snapshot, Mapping):
        return False
    target = value_text.strip().lower()
    if not target:
        return False

    def _walk(node: Any) -> bool:
        if isinstance(node, Mapping):
            return any(_walk(v) for v in node.values())
        if isinstance(node, (list, tuple)):
            return any(_walk(v) for v in node)
        return str(node).strip().lower() == target or target in str(node).strip().lower()

    return _walk(data_snapshot)


_MISSING_PATH = object()


def _resolve_candidate_path(candidate: Mapping[str, Any], path: str) -> Any:
    """Walks a dotted path (e.g. ``"data_snapshot.beta"``) directly on
    ``candidate`` -- the same candidate dict ``_data_field_found`` already
    searches, but here the LLM's own claimed path is actually RESOLVED,
    not ignored. Returns ``_MISSING_PATH`` the instant any segment is
    absent or the current node is not a mapping (never guesses, never
    searches elsewhere for a same-named key)."""
    node: Any = candidate
    for segment in path.strip().split("."):
        segment = segment.strip()
        if not segment or not isinstance(node, Mapping) or segment not in node:
            return _MISSING_PATH
        node = node[segment]
    return node


def _values_match(claimed_text: str, real_value: Any) -> bool:
    """Mechanical equality, not fuzzy/semantic matching: exact string
    match after normalization, or (for numeric fields) exact numeric
    equality within floating-point tolerance -- never a substring/
    contains/similarity check, which is precisely what would let a wrong
    value sharing some digits slip through."""
    claimed = claimed_text.strip()
    real_str = str(real_value).strip()
    if claimed.lower() == real_str.lower():
        return True
    try:
        return abs(float(claimed) - float(real_value)) < 1e-9
    except (TypeError, ValueError):
        return False


_DOTTED_PATH_RE = re.compile(r"[A-Za-z_][A-Za-z0-9_]*(\.[A-Za-z_][A-Za-z0-9_]*)+")


def _looks_like_dotted_path(segment: str) -> bool:
    """True only for a real ``root.child.leaf``-shaped identifier path --
    deliberately strict so an ordinary semicolon in free text (e.g. two
    independent clauses in a text citation) is never mistaken for a
    deliberate multi-field path citation just because it happens to
    contain a ``';'``."""
    return bool(_DOTTED_PATH_RE.fullmatch(segment.strip()))


def _normalize_field_label(text: str) -> str:
    """Mechanical normalization only (case + separator-insensitive) --
    never a semantic/fuzzy alias lookup. No field-alias table exists
    anywhere in the current real source structure (data_snapshot carries
    only field_units, a unit map, not alternate names), so this is
    presently equivalent to exact identity once case/punctuation is
    stripped; it is not a synonym dictionary."""
    return "".join(ch for ch in text.lower() if ch.isalnum())


def _multi_field_citation_valid(
    candidate: Mapping[str, Any], used_location: str, quote_or_data: str
) -> bool | None:
    """2026-10-06 (real single-claim execution finding, then two more
    risks confirmed by direct reproduction before being fixed here):

    a REAL request returned ``used_location="data_snapshot.beta; data_
    snapshot.fifty_day_average; data_snapshot.two_hundred_day_average"``
    with ``supporting_quote_or_data="beta: 2.454; fifty_day_average:
    513.5342; two_hundred_day_average: 374.7236"`` -- three real,
    individually-verifiable field citations combined into one string.
    ``_data_field_found`` rejected it outright (checks the WHOLE combined
    string as one unit against each leaf, which can never match a leaf
    holding a single number). This function instead splits both strings
    on ``";"`` and verifies EACH (path, label, value) triple explicitly.

    Two further risks, each reproduced with a constructed counter-example
    BEFORE this fix, confirmed real, and closed here:

    1. The first version of this function took only the text AFTER the
       colon as the claimed value and compared it to the path's real
       value, discarding the LABEL before the colon entirely -- so
       ``used_location="data_snapshot.beta"`` with ``supporting_quote_or_
       data="fifty_day_average: 2.454"`` (a real value, but attached to a
       field name that does NOT match the path) wrongly validated,
       because 2.454 genuinely is beta's value. Now the label is
       required and must identify the SAME field as the path's own
       trailing segment (mechanical, case/punctuation-insensitive
       comparison -- see ``_normalize_field_label`` -- never a semantic
       guess, and no alias table exists in real data to consult).
    2. A segment-COUNT mismatch (e.g. 3 claimed paths, only 2 quoted
       values) used to return ``None`` and fall through to the OLD
       whole-string check, which could accept it if the combined string
       happened to be a literal excerpt substring -- silently leaving
       the THIRD claimed field completely unverified. A genuine multi-
       field path ATTEMPT (used_location's segments all look like real
       dotted paths, see ``_looks_like_dotted_path``) with a mismatched
       quote-segment count is now an explicit reject, never a fallback.

    2026-10-06 (round 2, found while building the 21-claim per-item
    analysis for the judgment-standard correction): the SAME phenomenon
    also happens with exactly ONE field -- a REAL response for a
    different claim returned ``used_location="data_snapshot.forward_eps"``
    (a single real path) with ``supporting_quote_or_data="forward_eps:
    15.63089"`` (a single, genuinely correct, LABELED citation). Because
    there was only one segment, the old gate (``len(paths) < 2``) deferred
    entirely to the legacy single-value check -- which also failed, since
    ``_data_field_found`` compares the WHOLE labeled string against bare
    leaf values (``15.63089``, never ``"forward_eps: 15.63089"``), and
    ``_quote_found_in_excerpt`` never matches a value the model
    reformatted with a label either. A correct, verifiable citation was
    wrongly rejected purely because of this formatting mismatch. Fixed by
    allowing exactly ONE path too, but ONLY when its single quote segment
    is itself labeled (contains ``":"``) -- an unlabeled single bare value
    (the common, already-working case, e.g. ``"0.64"`` with no colon)
    still returns ``None`` here and keeps using the legacy check exactly
    as before, so this is additive, never a behavior change for the
    already-correct bare-value path.

    Returns ``None`` when ``used_location`` does not look like a
    deliberate field-path citation at all (any segment not shaped like
    ``root.child`` -- e.g. ordinary text whose stray ``';'`` is not a
    field-path delimiter), or when there is exactly one segment whose
    quote is a bare, unlabeled value -- the caller then uses the existing,
    unchanged single-value check. Once recognized as a genuine field-path
    attempt (two or more segments, or exactly one labeled segment), every
    failure mode (unknown path, wrong field-value binding, fabricated
    value, segment-count mismatch) is an explicit ``False`` -- never a
    silent partial pass.
    """
    paths = [p.strip() for p in used_location.split(";") if p.strip()]
    if not paths or not all(_looks_like_dotted_path(p) for p in paths):
        return None

    quotes = [q.strip() for q in quote_or_data.split(";") if q.strip()]
    if len(paths) == 1 and len(quotes) == 1 and ":" not in quotes[0]:
        return None  # single bare, unlabeled value -- defer to the existing, unchanged legacy check
    if len(paths) != len(quotes):
        return False

    for path, quote_segment in zip(paths, quotes, strict=True):
        if ":" not in quote_segment:
            return False  # no stated field identifier to bind against the path -- cannot verify, reject
        label, _, claimed_value = quote_segment.partition(":")
        claimed_value = claimed_value.strip()
        expected_field = path.strip().rsplit(".", 1)[-1]
        if _normalize_field_label(label) != _normalize_field_label(expected_field):
            return False
        resolved = _resolve_candidate_path(candidate, path)
        if resolved is _MISSING_PATH or not _values_match(claimed_value, resolved):
            return False
    return True


def _literal_at_token_boundaries(part: str, excerpt: str) -> bool:
    """``part`` occurs verbatim in ``excerpt`` and is not a fragment of a
    longer token there (``"rsi=7"`` inside ``"rsi=72.95"`` does not count)."""
    return re.search(r"(?<![A-Za-z0-9])" + re.escape(part) + r"(?![A-Za-z0-9]|\.\d)", excerpt) is not None


def _segmented_literal_citation_valid(candidate: Mapping[str, Any], used_location: str, quote_or_data: str) -> bool:
    """2026-10-08 (T3 closeout, execution t3joint-20261008T170322Z-bd99811e):
    five real replies were rejected as quote_or_data_not_found although
    every part they cited is printed verbatim in the cited candidate's own
    excerpt -- e.g. ``"Forward PE=41.668015; Forward EPS=15.72189; PE Ratio
    (TTM)=167.11734"`` against an excerpt that prints exactly those three
    ``Label=value`` pairs. The whole-quote check needs the JOINED string to be
    one excerpt substring (it never is), and the path check needs each part
    written ``field_name: value`` (the excerpt's own ``Label=value`` form and
    display labels never are).

    Accepted here only when the quote has two or more ``';'`` parts and EACH
    part is itself a verbatim excerpt quote at token boundaries -- the same
    reality rule a single quote already meets, applied per part, never a
    normalized or fuzzy match. When ``used_location`` is a dotted path list,
    it must have exactly one path per part and each part's value (the text
    after its last ``=``/``:``) must equal that path's real value
    (``_values_match``), so a real excerpt pair cited against the wrong field
    still fails. A part the excerpt does not print verbatim -- a reformatted,
    relabeled or invented one -- fails, so the whole citation does."""
    excerpt = str(candidate.get("excerpt") or "")
    parts = [part.strip() for part in quote_or_data.split(";") if part.strip()]
    if len(parts) < 2 or not excerpt or not all(_literal_at_token_boundaries(part, excerpt) for part in parts):
        return False
    paths = [path.strip() for path in used_location.split(";") if path.strip()]
    if not paths or not all(_looks_like_dotted_path(path) for path in paths):
        return True
    if len(paths) != len(parts):
        return False
    for path, part in zip(paths, parts, strict=True):
        resolved = _resolve_candidate_path(candidate, path)
        if resolved is _MISSING_PATH or not _values_match(re.split(r"[=:]", part)[-1].strip(), resolved):
            return False
    return True


def _coerce_str_list(value: Any) -> list[str] | None:
    """Returns a list[str] only when ``value`` really is a list of strings
    (empty list included) -- ``None`` for anything else (missing, wrong
    type, or containing a non-string element), so a malformed
    inference_facts/inference_assumptions is a real validation failure,
    never silently coerced into an empty list."""
    if not isinstance(value, list):
        return None
    if not all(isinstance(item, str) for item in value):
        return None
    return list(value)


def _v2_structural_contradiction(returned: Mapping[str, Any], status: str) -> bool:
    """v2.1 (2026-10-06, limited real-verification round correction):
    mechanical, structural self-consistency checks on the response's OWN
    declared fields -- never a semantic re-judgment of whether the verdict
    itself "sounds right". Catches the scenario the correction round
    named: a response that claims SUPPORTS while simultaneously disclosing
    no real basis for it, or whose own unsupported_remainder/materiality/
    inference-disclosure fields do not agree with each other.

    v2.1 fix (found during this round's own zero-cost pre-send review,
    never sent to a real Provider under v2's own identity): v2 wrongly
    REQUIRED non-empty inference_assumptions whenever support_basis was
    GROUNDED_INFERENCE, on the theory that an inference "by definition"
    needs an assumption the material doesn't state. That is not always
    true -- a real inference can follow directly from two or more stated
    facts via plain logical entailment, with no gap-filling assumption
    needed at all (e.g. "beta of 2.45 means high volatility" follows from
    beta's own definition, not an added assumption). Requiring a non-
    empty inference_assumptions list in that case would force the model
    to either invent a fake assumption or get rejected for a genuinely
    reasonable inference -- exactly the kind of unnecessary FORMAT
    condition this round was asked to check for. Fixed: inference_
    assumptions may legitimately be empty for GROUNDED_INFERENCE;
    inference_facts remains required non-empty for both DERIVED_
    CALCULATION and GROUNDED_INFERENCE (a real inference must still cite
    the real facts it reasons from)."""
    support_basis = returned.get("support_basis")
    if support_basis not in VALID_SUPPORT_BASES:
        return True

    basis_required_statuses = {STATUS_SUPPORTS, STATUS_OPPOSES, STATUS_CONDITIONAL}
    if status in basis_required_statuses and support_basis == SUPPORT_BASIS_NONE:
        return True  # claims a support relationship but discloses no basis for it
    if status not in basis_required_statuses and support_basis != SUPPORT_BASIS_NONE:
        return True  # BACKGROUND/CITATION_ONLY/INSUFFICIENT has no support relationship to attribute a basis to

    inference_facts = _coerce_str_list(returned.get("inference_facts"))
    inference_assumptions = _coerce_str_list(returned.get("inference_assumptions"))
    if inference_facts is None or inference_assumptions is None:
        return True
    requires_facts = support_basis in _SUPPORT_BASES_REQUIRING_INFERENCE_DISCLOSURE
    if requires_facts and not inference_facts:
        return True  # claims a derived/inferred basis but cites no facts relied upon
    if not requires_facts and inference_facts:
        return True  # DIRECT_FACT/SEMANTIC_PARAPHRASE/NONE needs no inference disclosure
    # v2.1: inference_assumptions is no longer FORCED non-empty for
    # GROUNDED_INFERENCE (see docstring) -- only still forbidden for bases
    # that involve no inference at all.
    if not requires_facts and inference_assumptions:
        return True  # DIRECT_FACT/SEMANTIC_PARAPHRASE/NONE needs no disclosed assumption either

    if status != STATUS_INSUFFICIENT:
        materiality = returned.get("unsupported_remainder_materiality")
        if materiality not in VALID_MATERIALITY:
            return True
        unsupported_remainder = str(returned.get("unsupported_remainder") or "").strip()
        if not unsupported_remainder and materiality != MATERIALITY_NONE:
            return True  # declares no unsupported remainder but still assigns it a materiality
        if unsupported_remainder and materiality == MATERIALITY_NONE:
            return True  # a real unsupported remainder with no materiality judgment at all
        # v2.1 fix (Part 二 point 4: "便宜"/"风险最大"/"应减仓" etc. may BE
        # the core conclusion -- NON_MATERIAL must never be a bare label):
        # requires a real, non-empty rationale whenever NON_MATERIAL is
        # asserted -- a minimum structural completeness bar (never a
        # content/quality judgment this module has no business making).
        if materiality == MATERIALITY_NON_MATERIAL and not str(returned.get("rationale") or "").strip():
            return True

    return False


def _validate_response_item(
    requested: ContentSupportRequestItem, returned: Any
) -> tuple[dict[str, Any] | None, str | None]:
    """Section 4: identity, candidate-set membership, citation reality,
    vocabulary, and (v2) internal structural self-consistency -- never a
    semantic re-judgment of whether the LLM's verdict "sounds right".
    Returns ``(validated_fields, fallback_reason)``; ``fallback_reason``
    is ``None`` iff accepted."""
    if not isinstance(returned, Mapping):
        return None, FALLBACK_INVALID_STATUS
    keys = set(returned.keys())
    if not _REQUIRED_RESPONSE_ITEM_KEYS.issubset(keys) or not keys.issubset(_ALLOWED_RESPONSE_ITEM_KEYS):
        return None, FALLBACK_INVALID_STATUS
    if str(returned.get("claim_id") or "") != requested.claim_id:
        return None, FALLBACK_IDENTITY_MISMATCH
    status = returned.get("status")
    if status not in VALID_RESPONSE_STATUSES:
        return None, FALLBACK_INVALID_STATUS
    if _v2_structural_contradiction(returned, status):
        return None, FALLBACK_INTERNAL_CONTRADICTION

    core_proposition = str(returned.get("core_proposition") or "")
    inference_facts = _coerce_str_list(returned.get("inference_facts")) or []
    inference_assumptions = _coerce_str_list(returned.get("inference_assumptions")) or []
    support_basis = returned.get("support_basis", SUPPORT_BASIS_NONE)

    if status == STATUS_INSUFFICIENT:
        return (
            {
                "status": status,
                "core_proposition": core_proposition,
                "support_basis": SUPPORT_BASIS_NONE,
                "used_source_id": None,
                "used_location": None,
                "supporting_quote_or_data": None,
                "inference_facts": [],
                "inference_assumptions": [],
                "rationale": str(returned.get("rationale") or ""),
                "supported_proposition": "",
                "unsupported_remainder": str(returned.get("unsupported_remainder") or requested.payload.get("proposition") or ""),
                "unsupported_remainder_materiality": MATERIALITY_MATERIAL,
            },
            None,
        )

    used_source_id = str(returned.get("used_source_id") or "")
    candidate = requested.candidates_by_id.get(used_source_id)
    if candidate is None:
        return None, FALLBACK_SOURCE_NOT_IN_CANDIDATES

    quote_or_data = str(returned.get("supporting_quote_or_data") or "").strip()
    if not quote_or_data:
        return None, FALLBACK_QUOTE_OR_DATA_NOT_FOUND
    used_location = str(returned.get("used_location") or "")
    multi_field_result = _multi_field_citation_valid(candidate, used_location, quote_or_data)
    if multi_field_result is not None:
        found = multi_field_result
    else:
        excerpt = str(candidate.get("excerpt") or "")
        found = _quote_found_in_excerpt(quote_or_data, excerpt) or _data_field_found(
            quote_or_data, candidate.get("data_snapshot")
        )
    if not found:
        found = _segmented_literal_citation_valid(candidate, used_location, quote_or_data)
    if not found:
        return None, FALLBACK_QUOTE_OR_DATA_NOT_FOUND

    return (
        {
            "status": status,
            "core_proposition": core_proposition,
            "support_basis": support_basis,
            "used_source_id": used_source_id,
            "used_location": returned.get("used_location"),
            "supporting_quote_or_data": quote_or_data,
            "inference_facts": inference_facts,
            "inference_assumptions": inference_assumptions,
            "rationale": str(returned.get("rationale") or ""),
            "supported_proposition": str(returned.get("supported_proposition") or ""),
            "unsupported_remainder": str(returned.get("unsupported_remainder") or ""),
            "unsupported_remainder_materiality": returned.get("unsupported_remainder_materiality", MATERIALITY_NONE),
        },
        None,
    )


def _effective_content_support_status(validated: dict[str, Any]) -> str:
    """v2 (2026-10-06, T1 judgment-standard correction): replaces v1's
    blanket mechanical rule (ANY non-empty ``unsupported_remainder`` on a
    SUPPORTS verdict downgrades to CONDITIONAL, no exceptions) with the
    LLM's own disclosed, auditable ``unsupported_remainder_materiality``
    judgment. A real finding drove this: round10's own 21-claim AMD
    execution found 8 of 9 raw SUPPORTS verdicts carried SOME non-empty
    remainder, and v1's rule downgraded every single one, with no way to
    tell a genuinely MATERIAL correction (changes the claim's own object,
    causal/comparative relationship, direction, or certainty -- e.g. "the
    50-day average is 37% above the 200-day average" silently correcting
    "the stock price is 37% above its 200-day average": a different
    OBJECT, always MATERIAL) apart from a non-material rhetorical add-on
    riding alongside an otherwise fully-supported core fact.

    A MATERIAL remainder still downgrades to CONDITIONAL exactly as
    strictly as v1 always did -- this function does not loosen that case
    at all, only stops loosely treating NON_MATERIAL the same way.
    ``compute_verified_support_eligibility`` already treats CONDITIONAL as
    NOT direct support (its own docstring: "CONDITIONAL... never count as
    direct support"), unchanged by this round."""
    status = validated["status"]
    if status == STATUS_SUPPORTS:
        materiality = validated.get("unsupported_remainder_materiality")
        if materiality == MATERIALITY_MATERIAL:
            return SUPPORT_CONDITIONAL
        return SUPPORT_SUPPORTS
    return _STATUS_TO_CONTENT_SUPPORT_STATUS[status]


def _apply_result(record: dict[str, Any], validated: dict[str, Any]) -> dict[str, Any]:
    """``record`` must already carry ``_content_support_llm_content_hash_hint``
    (the used candidate's real, current ``content_hash`` -- stamped by
    ``_process_batch`` before calling this function) when ``used_source_id``
    is set; this binds the review exactly like ``HUMAN_REVIEWED``/
    ``AUTOMATED_DATA_FACT_VERIFIED`` already do, so a later content change
    is detectable the same way."""
    effective_status = _effective_content_support_status(validated)
    candidate = validated.get("used_source_id")
    updated = dict(record)
    updated["content_support_status"] = effective_status
    updated["content_support_method"] = REVIEW_METHOD_LLM_CONTENT_SUPPORT_VERIFIED
    content_hash = updated.pop("_content_support_llm_content_hash_hint", None) if candidate else None
    updated.pop("_content_support_llm_content_hash_hint", None)
    updated["content_support_review"] = build_content_support_review(
        effective_status,
        method=REVIEW_METHOD_LLM_CONTENT_SUPPORT_VERIFIED,
        claim_id=str(record.get("claim_id") or ""),
        linked_source_id=candidate,
        content_hash=content_hash,
    )
    updated["content_support_llm_detail"] = {
        "schema_version": LLM_METHOD_VERSION,
        "llm_status": validated["status"],
        # v2 additive fields -- the LLM's own disclosed basis/inference/
        # materiality judgment, kept alongside (never instead of) the
        # original v1-shaped fields. A v1-produced record simply never has
        # these keys (schema_version stays LLM_METHOD_VERSION_V1 on those,
        # forever -- see content_support_llm.py's own module docstring).
        "core_proposition": validated.get("core_proposition"),
        "support_basis": validated.get("support_basis"),
        "used_source_id": candidate,
        "used_location": validated.get("used_location"),
        "supporting_quote_or_data": validated.get("supporting_quote_or_data"),
        "inference_facts": validated.get("inference_facts"),
        "inference_assumptions": validated.get("inference_assumptions"),
        "rationale": validated.get("rationale"),
        # The scorable/supported sub-proposition -- diagnostic/audit only.
        # NEVER read by compute_verified_support_eligibility or any scoring
        # path (confirmed by direct code reading and by a dedicated
        # regression test); content_support_status/content_support_review
        # are computed from status + unsupported_remainder_materiality
        # alone, never from this text. record["claim"]/record["evidence"]
        # (the ORIGINAL claim) are never touched by this function at all --
        # a material correction can appear here for transparency, but can
        # never substitute for or score in place of the original claim.
        "supported_proposition": validated.get("supported_proposition"),
        "unsupported_remainder": validated.get("unsupported_remainder"),
        "unsupported_remainder_materiality": validated.get("unsupported_remainder_materiality"),
    }
    updated["content_support_llm_fallback_reason"] = None
    return updated


def _apply_fallback(record: dict[str, Any], reason: str) -> dict[str, Any]:
    """Section 4: a rejected/failed LLM result NEVER converts
    content_support_status to NONE or SUPPORTS -- the record is returned
    completely unchanged except for one additive diagnostic field recording
    WHY this claim did not get upgraded this pass."""
    updated = dict(record)
    updated["content_support_llm_fallback_reason"] = reason
    return updated


class ContentSupportRunStats:
    def __init__(self) -> None:
        self._lock = threading.Lock()
        self.llm_gateway_used = False
        self.requested_count = 0
        self.llm_verified_count = 0
        self.fallback_count = 0
        self.fallback_reason_counts: dict[str, int] = dict.fromkeys(sorted(VALID_FALLBACK_REASONS), 0)
        self.batch_count = 0
        self.logical_provider_calls = 0
        self.real_provider_attempts = 0
        self.status_counts: dict[str, int] = dict.fromkeys(sorted(VALID_RESPONSE_STATUSES), 0)
        # Round 10 (2026-10-06, Phase C preflight): one entry per REAL
        # invoke_json_with_trace call, success or failure -- the audit trail
        # a real, paid run must be able to save (request_control/
        # provider_response_metadata/token_usage/finish_reason/claim_ids/
        # outcome), never only the aggregate counters above. Never includes
        # an API key, auth header, or raw credential -- only what Week2LLM
        # Invocation's own request_control/provider_response_metadata
        # already sanitize (see week2_llm.py's own _request_control_
        # snapshot/_response_provider_metadata).
        self.attempt_log: list[dict[str, Any]] = []

    def record_verified(self, status: str) -> None:
        with self._lock:
            self.llm_verified_count += 1
            if status in self.status_counts:
                self.status_counts[status] += 1

    def record_fallback(self, reason: str) -> None:
        with self._lock:
            self.fallback_count += 1
            if reason in self.fallback_reason_counts:
                self.fallback_reason_counts[reason] += 1

    def record_batch_started(self) -> None:
        with self._lock:
            self.batch_count += 1

    def record_provider_attempt(self, real_attempts: int) -> None:
        with self._lock:
            self.logical_provider_calls += 1
            self.real_provider_attempts += max(0, int(real_attempts))

    def record_attempt_detail(self, detail: dict[str, Any]) -> None:
        with self._lock:
            self.attempt_log.append(detail)

    def to_dict(self) -> dict[str, Any]:
        return {
            "llm_gateway_used": self.llm_gateway_used,
            "requested_count": self.requested_count,
            "llm_verified_count": self.llm_verified_count,
            "fallback_count": self.fallback_count,
            "fallback_reason_counts": dict(self.fallback_reason_counts),
            "status_counts": dict(self.status_counts),
            "batch_count": self.batch_count,
            "logical_provider_calls": self.logical_provider_calls,
            "real_provider_attempts": self.real_provider_attempts,
            "attempt_log": list(self.attempt_log),
        }


def _process_batch(
    batch: list[ContentSupportRequestItem],
    llm_gateway: Any,
    stats: ContentSupportRunStats,
    results_by_claim_id: dict[str, dict[str, Any]],
) -> None:
    stats.record_batch_started()
    requested_by_id = {item.claim_id: item for item in batch}
    claim_ids_in_batch = [item.claim_id for item in batch]
    invocation = None
    finalized = False
    try:
        from comqutor_alpha.structure_engine.alpha_mapper import _gateway_accepts_claim_ids

        payload = {"items": [item.payload for item in batch]}
        # 2026-10-08 (T3 closeout): the batch's claim ids reach the semantic
        # ledger record (out-of-band, never part of the prompt or cache key),
        # offered only to a gateway that declares the parameter -- the same
        # compatibility rule alpha_mapper applies.
        claim_ids_kwarg = {"claim_ids": tuple(claim_ids_in_batch)} if _gateway_accepts_claim_ids(llm_gateway) else {}
        invocation = llm_gateway.invoke_json_with_trace(LLM_TASK_NAME, payload, _validate_batch_shape, **claim_ids_kwarg)
        stats.record_provider_attempt(int(getattr(invocation, "provider_attempt_count", 0) or 0))
        stats.record_attempt_detail(
            {
                "claim_ids": claim_ids_in_batch,
                "provider_status": getattr(invocation, "provider_status", None),
                "error_code": getattr(invocation, "error_code", None),
                "cache_hit": getattr(invocation, "cache_hit", None),
                "provider_attempt_count": getattr(invocation, "provider_attempt_count", None),
                "validation_accepted": getattr(invocation, "validation_accepted", None),
                "request_control": getattr(invocation, "request_control", None),
                "provider_response_metadata": getattr(invocation, "provider_response_metadata", None),
                "token_usage": getattr(invocation, "token_usage", None),
                "attempt_history": list(getattr(invocation, "attempt_history", None) or ()),
                "model_name": getattr(llm_gateway, "model_name", None),
                "provider": getattr(llm_gateway, "provider", None),
            }
        )

        if not invocation.validation_accepted:
            reason = _reason_from_invocation(invocation)
            finalized = True
            llm_gateway.finalize_semantic_invocation(invocation, accepted=False, fallback_reason=reason)
            for item in batch:
                results_by_claim_id[item.claim_id] = _apply_fallback(dict(item.record), reason)
                stats.record_fallback(reason)
            return

        returned_items = invocation.validated_output or []

        by_id: dict[str, Any] = {}
        duplicate_ids: set[str] = set()
        for returned in returned_items:
            if not isinstance(returned, Mapping):
                continue
            claim_id = str(returned.get("claim_id") or "")
            if claim_id not in requested_by_id:
                continue  # extra unrequested result -- never admitted
            if claim_id in by_id:
                duplicate_ids.add(claim_id)
            else:
                by_id[claim_id] = returned

        item_rejections: list[str] = []
        for item in batch:
            if item.claim_id in duplicate_ids:
                results_by_claim_id[item.claim_id] = _apply_fallback(dict(item.record), FALLBACK_DUPLICATE_RESULT)
                stats.record_fallback(FALLBACK_DUPLICATE_RESULT)
                item_rejections.append(FALLBACK_DUPLICATE_RESULT)
                continue
            returned = by_id.get(item.claim_id)
            if returned is None:
                results_by_claim_id[item.claim_id] = _apply_fallback(dict(item.record), FALLBACK_MISSING_RESULT)
                stats.record_fallback(FALLBACK_MISSING_RESULT)
                item_rejections.append(FALLBACK_MISSING_RESULT)
                continue
            validated, reason = _validate_response_item(item, returned)
            if reason is not None:
                results_by_claim_id[item.claim_id] = _apply_fallback(dict(item.record), reason)
                stats.record_fallback(reason)
                item_rejections.append(reason)
            else:
                candidate = item.candidates_by_id.get(validated.get("used_source_id") or "")
                record_with_hint = dict(item.record)
                if candidate is not None:
                    record_with_hint["_content_support_llm_content_hash_hint"] = candidate.get("content_hash")
                results_by_claim_id[item.claim_id] = _apply_result(record_with_hint, validated)
                stats.record_verified(validated["status"])
        # 2026-10-08 (T3 closeout): the semantic call is finalized only after
        # its items were judged, so a call none of whose items survived item
        # validation is recorded as rejected with those reasons (e.g.
        # quote_or_data_not_found), never as accepted. A multi-item call with
        # at least one accepted item stays accepted; per-item reasons remain on
        # each record's content_support_llm_fallback_reason.
        finalized = True
        if item_rejections and len(item_rejections) == len(batch):
            llm_gateway.finalize_semantic_invocation(
                invocation, accepted=False, fallback_reason=",".join(sorted(set(item_rejections)))
            )
        else:
            llm_gateway.finalize_semantic_invocation(invocation, accepted=True)
    except Exception:
        if invocation is not None and not finalized:
            llm_gateway.finalize_semantic_invocation(invocation, accepted=False, fallback_reason=FALLBACK_PROVIDER_ERROR)
        for item in batch:
            results_by_claim_id[item.claim_id] = _apply_fallback(dict(item.record), FALLBACK_PROVIDER_ERROR)
            stats.record_fallback(FALLBACK_PROVIDER_ERROR)


def apply_llm_content_support_verification(
    records: Sequence[Mapping[str, Any]],
    sources: list[dict[str, Any]] | None,
    *,
    llm_gateway: Any = None,
    batch_size: int | None = None,
) -> tuple[list[dict[str, Any]], ContentSupportRunStats]:
    """Additive post-pass over a run's full structured ``records`` list --
    mirrors ``evidence_stance_llm.apply_llm_stance_upgrade``'s own shape
    exactly. When ``llm_gateway`` is ``None`` (every existing caller's
    default, and Architecture Replay, which never passes one) this is a
    guaranteed zero-cost no-op: ``records`` is returned unchanged. Every
    record not submitted this pass (no real source link, no candidate,
    already resolved by Round 8's deterministic verifier) is returned
    byte-identical to its input.

    ``batch_size`` (2026-10-06, real-execution bug fix): explicit, optional
    override of the module's own ``BATCH_SIZE`` default -- ``None`` (every
    existing caller) reproduces exactly today's behavior. Deliberately a
    real function PARAMETER, never a module-global a caller mutates after
    import: Python binds a function's own default-argument value (``def
    chunk_items(items, size: int = BATCH_SIZE)``) ONCE, at function
    DEFINITION time -- reassigning the module's ``BATCH_SIZE`` attribute
    afterward (as round10's own first real Phase C execution script
    mistakenly did) silently has NO effect on that already-bound default,
    which is exactly why that run's real batches stayed at size 5 despite
    the script's own intent to force size 1. This parameter closes that
    real gap with an explicit, testable, correctly-threaded override."""
    stats = ContentSupportRunStats()
    records = list(records)
    if llm_gateway is None or not sources:
        return records, stats
    stats.llm_gateway_used = True
    items = build_content_support_request_items(records, sources)
    stats.requested_count = len(items)
    if not items:
        return records, stats
    results_by_claim_id: dict[str, dict[str, Any]] = {}
    effective_batch_size = batch_size if batch_size is not None else BATCH_SIZE
    for batch in chunk_items(items, size=effective_batch_size):
        _process_batch(batch, llm_gateway, stats, results_by_claim_id)

    updated_records = []
    for record in records:
        claim_id = str(record.get("claim_id") or "")
        updated_records.append(results_by_claim_id.get(claim_id, record))
    return updated_records, stats


def identify_claims_needing_alpha_reclassification(
    records: Sequence[Mapping[str, Any]], alpha_matches_by_claim_id: Mapping[str, Any]
) -> list[dict[str, Any]]:
    """v2 (2026-10-06): a PURE, read-only, zero-cost diagnostic -- never
    makes or triggers any Provider call itself. ``alpha_matches.json``'s
    own per-claim ``matched_alpha``/``direction``/``factors`` were computed
    from the claim's ORIGINAL, full text, before content-support
    verification ever ran. When verification later finds a MATERIAL
    unsupported remainder (the claim's own core OBJECT/causal-or-
    comparative relationship/direction/certainty changes once the
    unsupported part is set aside), the original Alpha match may no longer
    reflect what the claim's VERIFIED core proposition actually says --
    e.g. a claim originally matched because it asserted "the stock price
    crossed its 200-day average" when the verified core is actually about
    the 50-day/200-day relationship instead.

    This function only DETECTS that gap and names the specific claim_id/
    matched_alpha/content_support_llm_detail involved -- it never re-runs
    alpha_classifier/evidence_stance_llm itself. Re-running those (the
    SAME real, already-registered Week2LLM tasks every other claim's
    classification already goes through -- never a new, separate
    mechanism) is a real, paid Provider call and requires its own explicit
    authorization; this function's only job is to make that decision
    point visible and traceable, not to act on it."""
    flagged: list[dict[str, Any]] = []
    for record in records:
        claim_id = str(record.get("claim_id") or "")
        detail = record.get("content_support_llm_detail")
        if not isinstance(detail, Mapping):
            continue
        if detail.get("unsupported_remainder_materiality") != MATERIALITY_MATERIAL:
            continue
        match = alpha_matches_by_claim_id.get(claim_id)
        matched_alpha = match.get("matched_alpha") if isinstance(match, Mapping) else None
        if not matched_alpha:
            continue  # never matched to any Alpha in the first place -- nothing to reclassify
        flagged.append(
            {
                "claim_id": claim_id,
                "matched_alpha": matched_alpha,
                "original_direction": match.get("direction") if isinstance(match, Mapping) else None,
                "unsupported_remainder": detail.get("unsupported_remainder"),
                "supported_proposition": detail.get("supported_proposition"),
                "reason": (
                    "content-support verification found a MATERIAL unsupported remainder -- the "
                    "claim's verified core proposition differs from the full original text the "
                    "existing Alpha match/direction was computed from"
                ),
            }
        )
    return flagged


__all__ = [
    "LLM_TASK_NAME",
    "LLM_METHOD_VERSION",
    "LLM_METHOD_VERSION_V1",
    "REVIEW_METHOD_LLM_CONTENT_SUPPORT_VERIFIED",
    "STATUS_SUPPORTS",
    "STATUS_OPPOSES",
    "STATUS_BACKGROUND",
    "STATUS_CITATION_ONLY",
    "STATUS_CONDITIONAL",
    "STATUS_INSUFFICIENT",
    "VALID_RESPONSE_STATUSES",
    "SUPPORT_BASIS_DIRECT_FACT",
    "SUPPORT_BASIS_SEMANTIC_PARAPHRASE",
    "SUPPORT_BASIS_DERIVED_CALCULATION",
    "SUPPORT_BASIS_GROUNDED_INFERENCE",
    "SUPPORT_BASIS_NONE",
    "VALID_SUPPORT_BASES",
    "MATERIALITY_NONE",
    "MATERIALITY_NON_MATERIAL",
    "MATERIALITY_MATERIAL",
    "VALID_MATERIALITY",
    "FALLBACK_INTERNAL_CONTRADICTION",
    "FALLBACK_PROVIDER_ERROR",
    "FALLBACK_TIMEOUT",
    "FALLBACK_BUDGET_EXHAUSTED",
    "FALLBACK_MALFORMED_RESPONSE",
    "FALLBACK_MISSING_RESULT",
    "FALLBACK_DUPLICATE_RESULT",
    "FALLBACK_IDENTITY_MISMATCH",
    "FALLBACK_INVALID_STATUS",
    "FALLBACK_SOURCE_NOT_IN_CANDIDATES",
    "FALLBACK_QUOTE_OR_DATA_NOT_FOUND",
    "FALLBACK_TIME_INVALID",
    "FALLBACK_CONTENT_HASH_STALE",
    "FALLBACK_AUDIT_WRITE_FAILED",
    "VALID_FALLBACK_REASONS",
    "BATCH_SIZE",
    "ContentSupportRequestItem",
    "ContentSupportRunStats",
    "build_content_support_request_items",
    "chunk_items",
    "apply_llm_content_support_verification",
    "identify_claims_needing_alpha_reclassification",
]
