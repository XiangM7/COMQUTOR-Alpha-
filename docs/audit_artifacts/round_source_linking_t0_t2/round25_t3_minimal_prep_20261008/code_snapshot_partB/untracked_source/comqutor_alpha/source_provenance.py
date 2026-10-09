"""John MVP Final Gap Closure -- Structured External Source Traceability.

This module owns exactly one job: turning genuine, upstream-supplied source
metadata (captured at the data-acquisition boundary -- see
``tradingagents.dataflows.source_capture``) into a per-run, persisted
``source_registry.json`` artifact, and deterministically joining a claim's
already-persisted text against that registry at read time.

Hard rules this module enforces (see the task's own anti-hallucination
section):

- No field here is ever inferred by an LLM from claim prose. Every
  ``SourceRecord`` is built exclusively from fields a real upstream tool
  adapter actually returned (see ``tradingagents/dataflows/*``).
- Linking a claim to a source is a pure, deterministic substring match
  against that source's own genuine ``title`` -- never a model-returned
  reference, so there is nothing for a model to invent. ``resolve_source_by_id``
  additionally exists as a defensive validator: an id not present in the
  run's own registry is always rejected, never trusted.
- Absence of a match, or absence of a registry entirely (e.g. a historical
  run predating this feature), always resolves to ``UNAVAILABLE`` -- never a
  fabricated value.

This module is never imported by ``tradingagents/`` (the acquisition layer
only ever calls its own self-contained
``tradingagents.dataflows.source_capture``) -- the dependency direction
stays comqutor_alpha -> tradingagents, matching every other integration
point in this codebase.
"""

from __future__ import annotations

import datetime as dt
import hashlib
import re
from collections.abc import Mapping
from typing import Any

SOURCE_REGISTRY_SCHEMA_VERSION = "source_registry.v2"

# Section 14's small, explicit status vocabulary. VERIFIED is deliberately
# never emitted anywhere in this module -- a URL/title being present is
# proof of *traceability*, never proof that the underlying claim is true,
# and this codebase never performs a separate fact-verification action.
STATUS_TRACEABLE = "TRACEABLE"
STATUS_PARTIAL = "PARTIAL"
STATUS_UNAVAILABLE = "UNAVAILABLE"
VALID_SOURCE_STATUSES = frozenset({STATUS_TRACEABLE, STATUS_PARTIAL, STATUS_UNAVAILABLE})

# ---------------------------------------------------------------------------
# T1 source-linking / evidence-support chain (COMQUTOR Alpha next-round
# task, 2026-09-26). Two DELIBERATELY SEPARATE axes -- never conflated:
#
#   source_link_status  -- is this claim's cited source_id/fragment_id a
#                           real, resolvable, in-scope, time-valid reference
#                           into THIS run's own source_registry.json.
#   content_support_status -- does that source's actual content support the
#                           claim's assertion (a semantic question this
#                           module can NEVER answer by string equality,
#                           title/keyword hits, or the mere existence of a
#                           valid link -- SOURCE_LINK_VALID never implies
#                           SUPPORT_SUPPORTS).
#
# A candidate source_id/fragment_id may arrive two ways: (a) a deterministic
# content match this module itself proposes (match_evidence_to_source_
# candidates, below -- content-based, never title-only, never LLM-invented),
# or (b) in a future live wiring, a value an extraction-stage LLM call
# proposes. Either way, validate_source_reference is the ONE gate both must
# pass before a link is ever treated as valid -- a model-supplied id is
# never trusted without it.
# ---------------------------------------------------------------------------

SOURCE_LINK_VALID = "VALID"
SOURCE_LINK_UNKNOWN_ID = "UNKNOWN_ID"
SOURCE_LINK_CONTENT_UNAVAILABLE = "CONTENT_UNAVAILABLE"
SOURCE_LINK_TIME_INVALID = "TIME_INVALID"
SOURCE_LINK_NOT_PROVIDED = "NOT_PROVIDED"
VALID_SOURCE_LINK_STATUSES = frozenset(
    {
        SOURCE_LINK_VALID,
        SOURCE_LINK_UNKNOWN_ID,
        SOURCE_LINK_CONTENT_UNAVAILABLE,
        SOURCE_LINK_TIME_INVALID,
        SOURCE_LINK_NOT_PROVIDED,
    }
)

SUPPORT_SUPPORTS = "SUPPORTS"
SUPPORT_OPPOSES = "OPPOSES"
SUPPORT_BACKGROUND = "BACKGROUND"
SUPPORT_CITATION_ONLY = "CITATION_ONLY"
SUPPORT_CONDITIONAL = "CONDITIONAL"
SUPPORT_PENDING_REVIEW = "PENDING_REVIEW"
SUPPORT_NOT_APPLICABLE = "NOT_APPLICABLE"
VALID_CONTENT_SUPPORT_STATUSES = frozenset(
    {
        SUPPORT_SUPPORTS,
        SUPPORT_OPPOSES,
        SUPPORT_BACKGROUND,
        SUPPORT_CITATION_ONLY,
        SUPPORT_CONDITIONAL,
        SUPPORT_PENDING_REVIEW,
        SUPPORT_NOT_APPLICABLE,
    }
)

# ---------------------------------------------------------------------------
# Content-support review record (COMQUTOR Alpha T1 follow-up, 2026-09-28):
# a small, structured audit trail for HOW a content_support_status came to
# be what it is -- who/what judged it, by what method, on what basis, and
# under which review-contract version. No reviewer exists in this codebase
# yet (offline, no model call authorized this round) -- every record this
# module itself produces is REVIEW_METHOD_UNREVIEWED, honestly pending.
# apply_content_support_review is the one function a future human-review
# tool (or, separately authorized, a semantic-review pass) would call to
# record a real verdict -- this module never calls it on its own.
# ---------------------------------------------------------------------------

REVIEW_METHOD_UNREVIEWED = "UNREVIEWED"
REVIEW_METHOD_UNVERIFIED_OFFLINE_CONTENT_MATCH = "UNVERIFIED_OFFLINE_CONTENT_MATCH"
REVIEW_METHOD_AGENT_CITED_UNVERIFIED_SUPPORT = "AGENT_CITED_UNVERIFIED_SUPPORT"
# T1 follow-up, 2026-09-28: distinct from REVIEW_METHOD_AGENT_CITED_
# UNVERIFIED_SUPPORT above -- that one names the LATER, SEPARATE
# extraction-stage enrichment Agent's own structured citation
# (``cited_source_id``). This one names a marker DETECTED IN THE ORIGINAL
# research agent's own already-generated report text (see
# ``extract_source_marker_from_text``) -- a different pipeline stage, never
# conflated with the extraction-stage citation.
REVIEW_METHOD_ORIGINAL_AGENT_CITED_UNVERIFIED_SUPPORT = "ORIGINAL_AGENT_CITED_UNVERIFIED_SUPPORT"
REVIEW_METHOD_HUMAN_REVIEWED = "HUMAN_REVIEWED"
# T1 automated-eligibility round (2026-10-06): a claim's content support can
# also be established WITHOUT any human review, when a real, deterministic,
# re-checkable comparison against this run's own saved source data succeeds
# -- never a human click, never an LLM guess presented as fact. Two narrow,
# distinct, honestly-named methods (never disguised as REVIEW_METHOD_
# HUMAN_REVIEWED, which stays reserved for an actual human verdict):
#   - DATA_FACT: the claim states one object/metric/value/unit/period tuple
#     (or a short enumeration of such tuples) with NO additional
#     interpretive language, and every stated value is found verbatim (after
#     numeric normalization) at the matching period/line-item position in
#     the linked source's own ``data_snapshot``.
#   - DERIVED_CALC: the claim states an explicit arithmetic combination
#     (addition/subtraction/period-over-period delta) of values that are
#     each independently a DATA_FACT per above, and the claim's own stated
#     result is recomputed, within tolerance, from those same inputs.
# See ``verify_data_fact_or_derived_calculation`` for the real matcher --
# this module never upgrades a compound sentence that mixes a verifiable
# number with unverifiable editorializing ("expensive", "a healthy sign",
# "consistent with...") to either of these; such claims stay PENDING_REVIEW.
REVIEW_METHOD_AUTOMATED_DATA_FACT_VERIFIED = "AUTOMATED_DATA_FACT_VERIFIED"
REVIEW_METHOD_AUTOMATED_DERIVED_CALC_VERIFIED = "AUTOMATED_DERIVED_CALC_VERIFIED"
# Round 9 (2026-10-06): a real LLM content-support judgment -- see
# comqutor_alpha.structure_engine.content_support_llm. Distinct from the two
# automated methods above (which only ever cover a claim reducible to a pure
# numeric statement): this covers an ANALYTICAL claim whose support
# determination requires reading the claim's own actual proposition against
# real saved source material, backed by this module's own identity/
# candidate-membership/citation-reality validation -- never a bare "the
# model said so". Defined here (not in content_support_llm.py) because
# every other REVIEW_METHOD_* constant lives in this module; content_support_
# llm.py imports it from here.
REVIEW_METHOD_LLM_CONTENT_SUPPORT_VERIFIED = "LLM_CONTENT_SUPPORT_VERIFIED"
VALID_REVIEW_METHODS = frozenset(
    {
        REVIEW_METHOD_UNREVIEWED,
        REVIEW_METHOD_UNVERIFIED_OFFLINE_CONTENT_MATCH,
        REVIEW_METHOD_AGENT_CITED_UNVERIFIED_SUPPORT,
        REVIEW_METHOD_ORIGINAL_AGENT_CITED_UNVERIFIED_SUPPORT,
        REVIEW_METHOD_HUMAN_REVIEWED,
        REVIEW_METHOD_AUTOMATED_DATA_FACT_VERIFIED,
        REVIEW_METHOD_AUTOMATED_DERIVED_CALC_VERIFIED,
        REVIEW_METHOD_LLM_CONTENT_SUPPORT_VERIFIED,
    }
)
# Eligible, WITHOUT a human reviewer, to count as officially verified
# support (see ``compute_verified_support_eligibility`` condition 2) -- a
# real, re-checkable automated or LLM-judged method stands on its own
# evidentiary footing, the same way a human verdict does; never conflated
# with the UNVERIFIED/AGENT_CITED_UNVERIFIED methods above, which remain
# ineligible.
AUTOMATICALLY_ELIGIBLE_REVIEW_METHODS = frozenset(
    {
        REVIEW_METHOD_HUMAN_REVIEWED,
        REVIEW_METHOD_AUTOMATED_DATA_FACT_VERIFIED,
        REVIEW_METHOD_AUTOMATED_DERIVED_CALC_VERIFIED,
        REVIEW_METHOD_LLM_CONTENT_SUPPORT_VERIFIED,
    }
)

CONTENT_SUPPORT_REVIEW_SCHEMA_VERSION = "content_support_review.v1"


def build_content_support_review(
    status: str,
    *,
    method: str = REVIEW_METHOD_UNREVIEWED,
    reviewer: str | None = None,
    rationale: str | None = None,
    claim_id: str | None = None,
    linked_source_id: str | None = None,
    content_hash: str | None = None,
) -> dict[str, Any]:
    """Builds one structured review record for a claim's
    ``content_support_status``. ``status`` must be one of
    ``VALID_CONTENT_SUPPORT_STATUSES``. ``method`` names HOW this status was
    reached (an unreviewed default, an unverified automatic mechanism, or a
    real human review); ``reviewer``/``rationale`` are only ever populated
    by :func:`apply_content_support_review`'s own human-review path -- never
    fabricated by this module itself.

    ``claim_id``/``linked_source_id``/``content_hash`` (T1 follow-up,
    2026-09-28; extended 2026-10-06 to the automated methods) BIND this
    review to the exact claim, source, and source CONTENT VERSION it was
    judged against -- required, non-null, for ``REVIEW_METHOD_HUMAN_
    REVIEWED`` and equally for either automated/LLM method in
    ``AUTOMATICALLY_ELIGIBLE_REVIEW_METHODS`` whenever ``status`` is a
    RESOLVED verdict (a review -- human or automated -- with no
    identifiable subject/content-version is not a real review). The one
    exception: ``status == SUPPORT_PENDING_REVIEW`` (Round 9's LLM task
    judging ``INSUFFICIENT`` -- the saved material does not bear on the
    claim at all, so there is honestly no source to bind to, and
    ``PENDING_REVIEW`` can never become eligible regardless of binding, per
    :func:`compute_verified_support_eligibility`'s own resolved-status
    check). A future re-check comparing a resolved review's own
    ``content_hash`` against the source's CURRENT content_hash is exactly
    how :func:`compute_verified_support_eligibility` detects a stale review
    after the underlying content changed.
    """
    if status not in VALID_CONTENT_SUPPORT_STATUSES:
        raise ValueError(f"invalid content_support_status: {status!r}")
    if method not in VALID_REVIEW_METHODS:
        raise ValueError(f"invalid review method: {method!r}")
    if (
        method in AUTOMATICALLY_ELIGIBLE_REVIEW_METHODS
        and status != SUPPORT_PENDING_REVIEW
        and not (claim_id and linked_source_id and content_hash)
    ):
        raise ValueError(
            f"a {method} review with status {status!r} must bind claim_id, linked_source_id, and content_hash"
        )
    return {
        "schema_version": CONTENT_SUPPORT_REVIEW_SCHEMA_VERSION,
        "status": status,
        "method": method,
        "reviewer": reviewer,
        "rationale": rationale,
        "reviewed_at": None,
        "claim_id": claim_id,
        "linked_source_id": linked_source_id,
        "content_hash": content_hash,
    }


def apply_content_support_review(
    record: Mapping[str, Any],
    *,
    status: str,
    reviewer: str,
    rationale: str,
    reviewed_at: str,
    sources: list[dict[str, Any]] | None = None,
) -> dict[str, Any]:
    """Returns a NEW record dict (never mutates ``record`` in place) with
    ``content_support_status``/``content_support_review`` updated to
    reflect a genuine human (or otherwise explicitly authorized) review
    verdict. This is the one, real, callable mechanism T1 requires for
    recording a review -- this module never invokes it on its own, and no
    production code path in this repository calls it automatically: a
    caller (a review tool, or an explicitly-authorized separate task) must
    supply a real ``reviewer``/``rationale``/``reviewed_at``. Never accepts
    an empty reviewer or rationale -- an unattributed, unexplained status
    change is refused, not silently recorded as reviewed.

    Requires ``record`` to already carry a ``SOURCE_LINK_VALID`` reference
    (``source_link_status``/``linked_source_id``) and ``sources`` (this
    run's own registry) to resolve the linked source's CURRENT
    ``content_hash`` -- a review with no resolvable, content-hash-bearing
    source is refused (there is nothing to bind the review to). This is
    also what makes a LATER content change detectable: the review binds
    the hash as it was AT REVIEW TIME, not a live reference.
    """
    if status not in VALID_CONTENT_SUPPORT_STATUSES:
        raise ValueError(f"invalid content_support_status: {status!r}")
    if not reviewer or not str(reviewer).strip():
        raise ValueError("apply_content_support_review requires a non-empty reviewer")
    if not rationale or not str(rationale).strip():
        raise ValueError("apply_content_support_review requires a non-empty rationale")
    claim_id = record.get("claim_id")
    if not claim_id or not str(claim_id).strip():
        raise ValueError("apply_content_support_review requires record to carry a claim_id")
    if record.get("source_link_status") != SOURCE_LINK_VALID or not record.get("linked_source_id"):
        raise ValueError(
            "apply_content_support_review requires an already-VALID source_link_status/linked_source_id "
            "-- a review needs a real, resolvable source to bind to"
        )
    resolved = resolve_fragment_by_id(record["linked_source_id"], sources or []) or resolve_source_by_id(
        record["linked_source_id"], sources or []
    )
    if resolved is None or not resolved.get("content_hash"):
        raise ValueError(
            "apply_content_support_review requires the linked source to resolve in `sources` with a "
            "real content_hash -- there is nothing to bind the review's content version to"
        )
    updated = dict(record)
    updated["content_support_status"] = status
    updated["content_support_method"] = REVIEW_METHOD_HUMAN_REVIEWED
    updated["content_support_review"] = {
        "schema_version": CONTENT_SUPPORT_REVIEW_SCHEMA_VERSION,
        "status": status,
        "method": REVIEW_METHOD_HUMAN_REVIEWED,
        "reviewer": str(reviewer),
        "rationale": str(rationale),
        "reviewed_at": str(reviewed_at),
        "claim_id": str(claim_id),
        "linked_source_id": str(record["linked_source_id"]),
        "content_hash": str(resolved["content_hash"]),
    }
    return updated


# ---------------------------------------------------------------------------
# Automated data-fact / derived-calculation verification (2026-10-06): a
# fully-automated research product cannot require a human reviewer before
# production scoring will use a claim -- see
# ``AUTOMATICALLY_ELIGIBLE_REVIEW_METHODS`` above. This section is the one
# real, deterministic, re-checkable mechanism that lets a claim earn
# verified-support eligibility WITHOUT a human: it reuses the SAME already-
# captured ``data_snapshot``/``periods``/``all_line_items`` structure every
# ``financial``-type source already carries (see
# ``tradingagents.dataflows.y_finance``) -- no new Provider call, no new
# extraction pass, just a real arithmetic/lookup check against already-saved
# numbers.
#
# Deliberately NARROW and conservative: a claim is only ever verified WHOLE
# -- never a verified fragment inside an otherwise-uninspected sentence --
# and only when, after removing its own recognized numeric/date/period
# tokens and a tiny fixed set of purely structural connector words, nothing
# of substance is left. A claim that mixes a real number with ANY
# interpretive, evaluative, or causal language ("expensive", "a healthy
# sign", "consistent with", "nearly doubled", "the single most important
# fundamental inflection") is left exactly as it was (PENDING_REVIEW) --
# this module has no way to safely attribute verification to only part of a
# claim at the current extraction granularity, and the task this round is
# explicit that an unsafe whole-claim upgrade is worse than an honest gap.
# ---------------------------------------------------------------------------

_NUMBER_TOKEN_RE = re.compile(
    r"[≈~]?\$?-?\d[\d,]*(?:\.\d+)?\s*(?:[MBKT%]|x)?\b", re.IGNORECASE
)
_DATE_TOKEN_RE = re.compile(
    r"\b\d{4}-\d{2}-\d{2}\b|\b[A-Z][a-z]{2}-\d{2}\b"
)
# Purely structural words/punctuation that carry no evaluative content of
# their own when surrounding a bare number/date/period enumeration -- NOT a
# license to strip real content; anything else left over blocks automated
# verification.
_STRUCTURAL_CONNECTOR_TOKENS = frozenset(
    {
        "line", "item", "metric", "value", "verified", "as", "of", "from",
        "to", "vs", "versus", "and", "a", "an", "the", "quarter", "quarters",
        "year", "ago", "qoq", "yoy", "sequential", "sequentially", "over",
        "four", "which", "is", "equal", "equals",
    }
)
_PUNCTUATION_RE = re.compile(r"[\$,;:()\[\]→–—\-+=/%.]")


def _residual_text_after_stripping_numeric_content(
    text: str, *, known_field_names: list[str] = ()
) -> str:
    """Returns whatever is LEFT of ``text`` after removing every recognized
    number/date/period token, the fixed structural-connector words,
    punctuation, and -- CRITICALLY -- any exact (case-insensitive)
    occurrence of one of ``known_field_names`` (the linked source's OWN
    real ``data_snapshot`` line-item/metric names, e.g. "Total Revenue",
    "Market Cap"; never an arbitrary word). Stripping a real field NAME is
    safe precisely because it is independently verified against the
    source's own schema, unlike an arbitrary word from the claim text --
    this is what lets "Line Item: Total Revenue; ..." reduce to empty while
    "...is the single most important fundamental inflection" (no real field
    name, pure editorializing) never does. An empty (or whitespace-only)
    result means ``text`` is reducible to a pure numeric/period/known-field
    enumeration -- see this section's own module-level comment for why that
    is the ONLY case this module will automatically verify."""
    without_markers = re.sub(r"\[fragment_?id:\s*[^\]]+\]", " ", text, flags=re.IGNORECASE)
    without_numbers = _NUMBER_TOKEN_RE.sub(" ", without_markers)
    without_dates = _DATE_TOKEN_RE.sub(" ", without_numbers)
    without_punctuation = _PUNCTUATION_RE.sub(" ", without_dates)
    remaining = without_punctuation
    for name in sorted(known_field_names, key=len, reverse=True):
        if not name:
            continue
        remaining = re.sub(re.escape(name), " ", remaining, flags=re.IGNORECASE)
    words = remaining.lower().split()
    residual = [w for w in words if w not in _STRUCTURAL_CONNECTOR_TOKENS]
    return " ".join(residual)


def _iter_source_line_item_values(source: Mapping[str, Any]) -> dict[str, dict[str, float]]:
    """Returns ``{line_item_name: {period: value}}`` from ``source``'s own
    ``data_snapshot`` -- merges the single ``line_item``/``periods`` pair
    (the source's own primary metric) with ``all_line_items`` (Round 3's
    additive sibling-field capture) when present. Never fabricates a period/
    value pair not already saved on this exact source."""
    snapshot = source.get("data_snapshot")
    if not isinstance(snapshot, Mapping):
        return {}
    by_line_item: dict[str, dict[str, float]] = {}
    primary_name = snapshot.get("line_item")
    primary_periods = snapshot.get("periods")
    if isinstance(primary_name, str) and isinstance(primary_periods, Mapping):
        by_line_item[primary_name] = {
            str(period): value for period, value in primary_periods.items() if isinstance(value, (int, float))
        }
    all_line_items = snapshot.get("all_line_items")
    if isinstance(all_line_items, Mapping):
        for name, periods in all_line_items.items():
            if isinstance(periods, Mapping):
                by_line_item[str(name)] = {
                    str(period): value for period, value in periods.items() if isinstance(value, (int, float))
                }
    return by_line_item


def _iter_source_scalar_fields(source: Mapping[str, Any]) -> dict[str, float]:
    """Returns ``{field_key: value}`` for a ``.info``-style live-snapshot
    source's own ``data_snapshot`` (flat numeric fields, e.g. market_cap,
    trailing_pe -- see ``y_finance._fundamentals_summary_sentence``). Never
    includes non-numeric bookkeeping keys (``field_units``/``currency``)."""
    snapshot = source.get("data_snapshot")
    if not isinstance(snapshot, Mapping):
        return {}
    return {
        str(key): value
        for key, value in snapshot.items()
        if isinstance(value, (int, float)) and key not in {"field_units"}
    }


def _all_numeric_values_in_source(source: Mapping[str, Any]) -> set[float]:
    """Every real number this source actually carries, from any of its own
    saved structured fields (line items across periods, or flat live-
    snapshot scalar fields) -- the universe a claim's own stated values must
    be drawn from for this source to automatically verify it."""
    values: set[float] = set()
    for periods in _iter_source_line_item_values(source).values():
        values.update(periods.values())
    values.update(_iter_source_scalar_fields(source).values())
    return values


def _parse_claim_numbers(text: str) -> list[float]:
    """Deterministically extracts every number the claim's own text states
    (after removing fragment-id markers), normalizing thousands separators
    and M/B/K scale suffixes -- the SAME normalization family
    ``match_evidence_to_source_candidates_normalized`` already uses
    elsewhere in this module, reused here rather than re-invented."""
    without_markers = re.sub(r"\[fragment_?id:\s*[^\]]+\]", " ", text, flags=re.IGNORECASE)
    # Dates (e.g. "2026-06-30") must be removed BEFORE number extraction --
    # otherwise their own year/month/day digits would be misread as three
    # separate bare numeric values.
    without_dates = _DATE_TOKEN_RE.sub(" ", without_markers)
    values: list[float] = []
    for match in re.finditer(r"(-?)[≈~]?\$?([\d,]+(?:\.\d+)?)\s*([MBKT%]|x)?", without_dates, re.IGNORECASE):
        sign, raw, suffix = match.group(1), match.group(2), (match.group(3) or "").upper()
        try:
            value = float(raw.replace(",", ""))
        except ValueError:
            continue
        if sign == "-":
            value = -value
        if suffix == "M":
            value *= 1_000_000
        elif suffix == "B":
            value *= 1_000_000_000
        elif suffix == "K":
            value *= 1_000
        elif suffix == "T":
            value *= 1_000_000_000_000
        elif suffix == "%":
            value /= 100.0
        values.append(value)
    return values


_NUMERIC_TOLERANCE_RELATIVE = 0.005  # 0.5% -- display-rounding/unit-scale slack only


def _value_matches_any(candidate: float, universe: set[float]) -> bool:
    for real_value in universe:
        if real_value == 0.0:
            if abs(candidate) < 1.0:
                return True
            continue
        if abs(candidate - real_value) <= abs(real_value) * _NUMERIC_TOLERANCE_RELATIVE:
            return True
    return False


def verify_data_fact_or_derived_calculation(
    record: Mapping[str, Any], sources: list[dict[str, Any]] | None
) -> dict[str, Any] | None:
    """Real, deterministic, zero-Provider-call check for whether ``record``
    (an already source-linked claim) is SAFE to automatically verify as
    DATA_FACT or DERIVED_CALC support -- see this section's own module
    comment for the exact, narrow rule. Returns ``None`` (never verified)
    unless EVERY one of the following holds:

      1. ``record`` already carries ``source_link_status ==
         SOURCE_LINK_VALID`` and a resolvable ``linked_source_id`` -- this
         function never does its own source resolution/matching, it only
         decides whether an ALREADY-linked claim's content is safe to mark
         as verified support.
      2. The claim's own text, after stripping every recognized number/
         date/period token and the fixed structural-connector words, is
         EMPTY -- i.e. the claim states nothing beyond a numeric/period
         enumeration (see ``_residual_text_after_stripping_numeric_content``).
      3. Every number literally present in the claim's text is found (after
         the same normalization ``match_evidence_to_source_candidates_
         normalized`` already applies elsewhere) among the linked source's
         own saved numeric fields (``data_snapshot``'s periods/all_line_
         items/flat scalar fields) -- object/unit/period are checked
         together here, by construction: a value is only ever considered
         "found" at the specific (line_item, period) or (scalar field)
         position the source itself recorded it at, never a bare "this
         number appears somewhere".

    Returns a structured verification record (never ``None``) with the
    chosen method name and the exact basis (matched line items/periods/
    fields) when eligible; a caller uses this to build a real
    ``content_support_review`` via ``build_content_support_review``.
    """
    if record.get("source_link_status") != SOURCE_LINK_VALID or not record.get("linked_source_id"):
        return None

    source = resolve_fragment_by_id(record["linked_source_id"], sources or []) or resolve_source_by_id(
        record["linked_source_id"], sources or []
    )
    if source is None:
        return None

    claim_text = str(record.get("claim") or record.get("evidence") or "").strip()
    if not claim_text:
        return None

    known_field_names = list(_iter_source_line_item_values(source).keys())
    for key in _iter_source_scalar_fields(source):
        known_field_names.append(key.replace("_", " "))
        known_field_names.append(key.replace("_", "-"))
        known_field_names.append(key.replace("_", "/"))

    residual = _residual_text_after_stripping_numeric_content(claim_text, known_field_names=known_field_names)
    if residual:
        return None

    claim_numbers = _parse_claim_numbers(claim_text)
    if not claim_numbers:
        return None

    numeric_universe = _all_numeric_values_in_source(source)
    if not numeric_universe:
        return None

    # "=" or "+" are the only unambiguous signals of a STATED arithmetic
    # relationship -- a bare "-" is far too ambiguous to use on its own: it
    # appears in every "2026-06-30"-style date and in every negative number,
    # neither of which implies the claim asserts a computed result. Dates
    # are stripped first so only a genuine minus-as-subtraction (rare
    # without an accompanying "=") could still trip this.
    text_for_operator_check = _DATE_TOKEN_RE.sub(" ", re.sub(r"\[fragment_?id:[^\]]+\]", "", claim_text))
    is_derived_calc = bool(re.search(r"[+=]", text_for_operator_check))

    if is_derived_calc and len(claim_numbers) >= 3:
        # A stated "A (+/-) B = C" (or longer chain) relationship: only the
        # OPERANDS need to be real, already-saved source values -- the
        # claim's own STATED RESULT is independently re-derived by
        # recomputation below, never required to also appear verbatim in
        # the source (it generally will not, being a computed figure). A
        # claim can cite real operands while asserting a FALSE relationship
        # between them, and that must still fail here.
        *operands, stated_result = claim_numbers
        if not all(_value_matches_any(value, numeric_universe) for value in operands):
            return None
        if abs(sum(operands) - stated_result) > max(abs(stated_result) * _NUMERIC_TOLERANCE_RELATIVE, 1.0):
            # Try alternating-sign (A - B - C = D style) before giving up --
            # still a real recomputation, never a guessed pass.
            alt = operands[0] - sum(operands[1:])
            if abs(alt - stated_result) > max(abs(stated_result) * _NUMERIC_TOLERANCE_RELATIVE, 1.0):
                return None
        method = REVIEW_METHOD_AUTOMATED_DERIVED_CALC_VERIFIED
    else:
        if not all(_value_matches_any(value, numeric_universe) for value in claim_numbers):
            return None
        method = REVIEW_METHOD_AUTOMATED_DATA_FACT_VERIFIED

    return {
        "method": method,
        "linked_source_id": source.get("source_id"),
        "content_hash": source.get("content_hash"),
        "verified_claim_numbers": claim_numbers,
        "verification_basis": "claim_reduces_to_pure_numeric_statement_matched_against_source_data_snapshot",
    }


def apply_automated_content_support_verification(
    record: Mapping[str, Any], *, sources: list[dict[str, Any]] | None
) -> dict[str, Any] | None:
    """Returns a NEW record dict (never mutates ``record``) with
    ``content_support_status``/``content_support_method``/
    ``content_support_review`` set from a REAL, deterministic automated
    verification -- or ``None`` (record left untouched by the caller) when
    :func:`verify_data_fact_or_derived_calculation` finds nothing safe to
    verify. This is the one, real, production-wired counterpart to
    :func:`apply_content_support_review` that requires no human: every
    field it writes uses the actual verification method name (never
    disguised as ``HUMAN_REVIEWED``), bound to this exact claim_id/
    linked_source_id/content_hash exactly as a human review would be.
    """
    verification = verify_data_fact_or_derived_calculation(record, sources)
    if verification is None:
        return None
    claim_id = str(record.get("claim_id") or "")
    if not claim_id:
        return None
    updated = dict(record)
    updated["content_support_status"] = SUPPORT_SUPPORTS
    updated["content_support_method"] = verification["method"]
    updated["content_support_review"] = {
        "schema_version": CONTENT_SUPPORT_REVIEW_SCHEMA_VERSION,
        "status": SUPPORT_SUPPORTS,
        "method": verification["method"],
        "reviewer": None,
        "rationale": verification["verification_basis"],
        "reviewed_at": None,
        "claim_id": claim_id,
        "linked_source_id": str(verification["linked_source_id"]),
        "content_hash": str(verification["content_hash"]),
    }
    return updated


# ---------------------------------------------------------------------------
# Verified-support eligibility gate (T1 follow-up, 2026-09-28): the explicit,
# traceable "would this claim count if we required only human-reviewed,
# content-version-bound support" rule the task calls for when no existing
# rule already defines this. This is a NEW, ADDITIVE eligibility check --
# it never modifies, and is never consulted by, the existing (frozen)
# B1 evidence_stance / B2 admissibility / Activation v2 formulas, which
# keep operating on every run (historical and new) exactly as before. A
# caller that wants a "verified-only" view filters its own claim pool
# through this function BEFORE calling those existing, unmodified
# functions -- see comqutor_alpha.graph_engine.verified_evidence_gate for
# the ready-made filtering wrappers around score_alpha_v2/
# evaluate_conflict_admissibility.
# ---------------------------------------------------------------------------

ELIGIBILITY_REASON_ELIGIBLE = "ELIGIBLE"
ELIGIBILITY_REASON_SOURCE_LINK_NOT_VALID = "SOURCE_LINK_NOT_VALID"
ELIGIBILITY_REASON_NOT_REVIEWED = "NOT_REVIEWED"
ELIGIBILITY_REASON_SUPPORT_STATUS_NOT_RESOLVED = "SUPPORT_STATUS_NOT_RESOLVED"
ELIGIBILITY_REASON_REVIEW_CLAIM_MISMATCH = "REVIEW_CLAIM_MISMATCH"
ELIGIBILITY_REASON_CONTENT_VERSION_CHANGED_SINCE_REVIEW = "CONTENT_VERSION_CHANGED_SINCE_REVIEW"
ELIGIBILITY_REASON_SOURCE_NOT_RESOLVABLE = "SOURCE_NOT_RESOLVABLE"
ELIGIBILITY_REASON_SOURCE_OPPOSES_CLAIM = "SOURCE_OPPOSES_CLAIM"
# 2026-09-29 (financial-statement source chain + macro chain closing fix):
# a resolvable, content-locatable, even HUMAN_REVIEWED-SUPPORTS source can
# still genuinely not carry a known disclosure/publish timestamp (e.g.
# yfinance's balance sheet/cashflow/income statement expose only a fiscal
# PERIOD END date, never a filing date; FRED's realtime_start can be absent
# from a given observation). ``validate_source_reference``'s own time check
# only fires when BOTH the cutoff and published_at are parseable -- a None
# published_at silently falls through as "no violation" rather than "time
# eligibility unknown", which would let genuinely undated evidence count as
# officially verified support. This is a SEPARATE, additional gate (never
# a replacement for the frozen validate_source_reference's own VALID/
# TIME_INVALID check): a source with published_at=None is real, locatable,
# content-comparable evidence -- still shown as research text/candidates/
# PENDING_REVIEW-eligible-for-content-review -- but never promoted to
# officially verified support until its disclosure timing is genuinely
# known, however the review itself resolved.
ELIGIBILITY_REASON_DISCLOSURE_TIME_UNKNOWN = "DISCLOSURE_TIME_UNKNOWN"

# ---------------------------------------------------------------------------
# Round 18 (2026-10-07): "available before the evidence cutoff" as a SECOND,
# honestly-named time basis next to ``published_at``.
#
# What the time gate protects against is look-ahead: a source that was not
# yet obtainable at the analysis's evidence cutoff must not support a
# judgment made as of that cutoff. ``published_at`` proves that directly for
# a dated source. A fiscal-statement snapshot has no disclosure date (the
# provider exposes only each column's PERIOD END), and that stays UNKNOWN:
# ``published_at`` is never backfilled, a period end or a capture time is
# never written into it, and a period end earlier than the cutoff proves
# nothing about when the figure became known.
#
# What a live capture CAN prove is narrower and different: this exact,
# content-hashed snapshot had already been obtained by ``available_by`` --
# so it was available no later than that instant. That is recorded in a
# separate, versioned ``availability`` block on the registry entry, which
# this module re-validates at consumption time (it never trusts the flag):
#   * the source is a live-captured financial data snapshot (provider and
#     data_snapshot present) -- not a news item, not an undated macro value;
#   * ``content_hash`` is the sha256 of the saved excerpt (binding intact);
#   * ``available_by`` equals the source's own ``retrieved_at`` -- the
#     registry-write time, an UPPER BOUND on the capture moment (the exact
#     tool-call time is not recorded for these sources);
#   * ``available_by`` is not later than the block's ``evidence_cutoff_at``
#     (which comes from ``resolve_evidence_cutoff_at``: the run's own
#     same-day fetched moments, else the bare analysis date as midnight --
#     so a snapshot fetched on a later day than an earlier analysis date is
#     AFTER the cutoff and is refused).
# Anything missing or inconsistent stays DISCLOSURE_TIME_UNKNOWN.
# ---------------------------------------------------------------------------
SOURCE_AVAILABILITY_VERSION = "source_availability.v1"
AVAILABILITY_BASIS_REGISTRY_WRITE_UPPER_BOUND = "REGISTRY_WRITE_TIME_UPPER_BOUND"
_AVAILABILITY_BASES = frozenset({AVAILABILITY_BASIS_REGISTRY_WRITE_UPPER_BOUND})
_AVAILABILITY_SOURCE_TYPES = frozenset({"financial"})
AVAILABILITY_ANNOTATION_REGISTRY_WRITE = "REGISTRY_WRITE"
AVAILABILITY_ANNOTATION_DERIVED_FROM_SAVED_REGISTRY = "DERIVED_FROM_SAVED_REGISTRY"


def _is_live_data_snapshot(source: Mapping[str, Any]) -> bool:
    snapshot = source.get("data_snapshot")
    return bool(
        source.get("source_type") in _AVAILABILITY_SOURCE_TYPES
        and (source.get("provider") or "").strip()
        and isinstance(snapshot, Mapping)
        and snapshot
    )


def evaluate_source_availability(source: Mapping[str, Any]) -> dict[str, Any]:
    """Re-validates ``source["availability"]`` from the source's own fields.
    Never trusts a stored boolean. ``reason_code`` is None only when the
    snapshot is proven available no later than the evidence cutoff."""

    def refuse(code: str, detail: str) -> dict[str, Any]:
        return {"available_before_cutoff": False, "reason_code": code, "detail": detail}

    block = source.get("availability")
    if not isinstance(block, Mapping):
        return refuse(ELIGIBILITY_REASON_DISCLOSURE_TIME_UNKNOWN, "no availability record")
    if block.get("version") != SOURCE_AVAILABILITY_VERSION or block.get("basis") not in _AVAILABILITY_BASES:
        return refuse(ELIGIBILITY_REASON_DISCLOSURE_TIME_UNKNOWN, "unknown availability version or basis")
    if not _is_live_data_snapshot(source):
        return refuse(ELIGIBILITY_REASON_DISCLOSURE_TIME_UNKNOWN, "not a live-captured financial data snapshot")
    excerpt = source.get("excerpt")
    if not excerpt or not source.get("content_hash") or hashlib.sha256(str(excerpt).encode("utf-8")).hexdigest() != source.get("content_hash"):
        return refuse(ELIGIBILITY_REASON_DISCLOSURE_TIME_UNKNOWN, "content hash does not match the saved snapshot")
    retrieved = _parse_iso_like(source.get("retrieved_at"))
    available_by = _parse_iso_like(block.get("available_by"))
    cutoff = _parse_iso_like(block.get("evidence_cutoff_at"))
    if retrieved is None or available_by is None or cutoff is None:
        return refuse(ELIGIBILITY_REASON_DISCLOSURE_TIME_UNKNOWN, "retrieved_at / available_by / evidence_cutoff_at missing or unparseable")
    if available_by != retrieved:
        return refuse(ELIGIBILITY_REASON_DISCLOSURE_TIME_UNKNOWN, "available_by is not this source's own retrieved_at")
    if available_by > cutoff:
        return refuse(ELIGIBILITY_REASON_AVAILABILITY_AFTER_CUTOFF, "snapshot obtained after the evidence cutoff")
    return {
        "available_before_cutoff": True,
        "reason_code": None,
        "detail": None,
        "basis": block.get("basis"),
        "available_by": block.get("available_by"),
        "evidence_cutoff_at": block.get("evidence_cutoff_at"),
        "cutoff_basis": block.get("cutoff_basis"),
    }


def annotate_sources_availability(
    sources: list[dict[str, Any]] | None, analysis_date: Any, *, mode: str
) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    """Returns (copies of ``sources`` with an ``availability`` block added to
    each undated live data snapshot, a per-source summary). Pure and
    deterministic: nothing but the sources' own saved fields and the run's
    ORIGINAL ``analysis_date`` is read -- never the current time -- so
    re-running it months later yields the same cutoff. ``published_at`` and
    every other field are left exactly as saved."""
    import copy

    sources = list(sources or [])
    cutoff, cutoff_basis = resolve_evidence_cutoff_at(analysis_date, sources)
    annotated: list[dict[str, Any]] = []
    summary: list[dict[str, Any]] = []
    for source in sources:
        copied = copy.deepcopy(source) if isinstance(source, Mapping) else source
        if isinstance(copied, dict) and not copied.get("published_at") and _is_live_data_snapshot(copied):
            copied["availability"] = {
                "version": SOURCE_AVAILABILITY_VERSION,
                "basis": AVAILABILITY_BASIS_REGISTRY_WRITE_UPPER_BOUND,
                "available_by": copied.get("retrieved_at"),
                "evidence_cutoff_at": cutoff,
                "cutoff_basis": cutoff_basis,
                "published_at_status": "UNKNOWN_NOT_BACKFILLED",
                "annotation_mode": mode,
            }
            summary.append({"source_id": copied.get("source_id"), **evaluate_source_availability(copied)})
        annotated.append(copied)
    return annotated, summary

# Round 18 (2026-10-07): two more explicit reasons, so a failure is never
# folded into a vaguer neighbouring code.
#  * REVIEW_SOURCE_NOT_LINKED_TO_CLAIM: a review names (``linked_source_id``)
#    a source that is not one of THIS claim's own linked sources at all.
#  * AVAILABILITY_NOT_BEFORE_EVIDENCE_CUTOFF: the source's availability
#    record is well-formed but says the snapshot was obtained AFTER the
#    run's evidence cutoff (a later retrieval can never support an earlier
#    judgment).
ELIGIBILITY_REASON_REVIEW_SOURCE_NOT_LINKED = "REVIEW_SOURCE_NOT_LINKED_TO_CLAIM"
ELIGIBILITY_REASON_AVAILABILITY_AFTER_CUTOFF = "AVAILABILITY_NOT_BEFORE_EVIDENCE_CUTOFF"

# A resolved, positive-or-negative verdict is required before this gate will
# even consider a review -- BACKGROUND/CITATION_ONLY/CONDITIONAL/
# PENDING_REVIEW are real, legitimate content-support classifications, but
# T1 explicitly requires they never count as DIRECT supporting (or
# opposing) evidence on their own. SUPPORTS and OPPOSES both pass this
# initial gate; they diverge below only once the review's binding (claim_id
# + content_hash) has ALSO been verified current.
_RESOLVED_SUPPORT_STATUSES = frozenset({SUPPORT_SUPPORTS, SUPPORT_OPPOSES})


def compute_verified_support_eligibility(
    record: Mapping[str, Any], sources: list[dict[str, Any]] | None
) -> dict[str, Any]:
    """Whether ``record`` (an already-persisted claim/evidence dict carrying
    ``source_link_status``/``linked_source_id``/``content_support_review``)
    qualifies as VERIFIED supporting evidence -- eligible to feed a
    "verified-only" admissibility/activation check. Every failure mode
    names a specific, traceable reason code; never a bare boolean.

    Eligible (``eligible=True``) requires ALL of:
      1. ``source_link_status == SOURCE_LINK_VALID`` (a real, resolvable,
         in-scope, time-valid reference -- never a candidate/unvalidated
         one).
      2. A ``content_support_review`` whose ``method`` is one of
         ``AUTOMATICALLY_ELIGIBLE_REVIEW_METHODS`` -- today, ``HUMAN_
         REVIEWED`` or one of the two real, deterministic, re-checkable
         automated methods (``AUTOMATED_DATA_FACT_VERIFIED``/
         ``AUTOMATED_DERIVED_CALC_VERIFIED``, see
         ``verify_data_fact_or_derived_calculation``). An UNVERIFIED/
         AGENT_CITED_UNVERIFIED method -- a mere marker or text-overlap
         match with no real object/unit/period/formula check behind it,
         however confident-sounding -- never counts here. Production
         eligibility is decided by WHETHER a real verification (human or
         automated) actually happened, never by WHO performed it -- this is
         the whole point of the gate (2026-10-06: a fully-automated research
         product cannot gate production scoring on a human reviewer who may
         never click anything).
      3. That review's own ``status`` is SUPPORTS (BACKGROUND/CITATION_
         ONLY/CONDITIONAL/PENDING_REVIEW never count as direct support,
         however they may still be shown as candidates elsewhere).
      4. The review's bound ``claim_id`` matches THIS record's own
         ``claim_id`` (a review recorded against a different claim never
         transfers).
      5. The review's bound ``content_hash`` matches the linked source's
         CURRENT ``content_hash`` (if the source's content changed since
         review, the review is stale and does not carry forward).
      6. The linked source's own ``published_at`` is genuinely known
         (2026-09-29: ``DISCLOSURE_TIME_UNKNOWN`` otherwise -- a source can
         be real, resolvable, content-locatable, and even HUMAN_REVIEWED
         SUPPORTS, yet still never known to have existed by any particular
         date, e.g. a fiscal-statement line item with no real disclosure
         date on record. This is checked independently of
         ``validate_source_reference``'s own VALID/TIME_INVALID check,
         which only fires when a cutoff comparison is actually possible --
         a missing ``published_at`` never violates that check by itself,
         so this function closes that gap for the specific "counts as
         verified support" question, never altering ``source_link_status``
         itself).

    ``OPPOSES`` (2026-09-28 correction): a genuinely current, correctly-
    bound HUMAN_REVIEWED verdict that the source REBUTS this claim's own
    assertion is real, resolved information -- but it is the OPPOSITE of
    verified support, so it returns ``eligible=False`` with the distinct
    reason code ``SOURCE_OPPOSES_CLAIM`` (never lumped in with an
    unreviewed/ambiguous status, and never silently counted toward
    whichever camp the claim's own ``evidence_stance`` happened to place it
    in). This function never auto-reassigns/flips the claim to argue the
    opposite thesis -- it only reports the rebuttal relationship via
    ``support_status`` in the returned dict; a caller decides what, if
    anything, to do with that signal. A source genuinely SUPPORTING a
    bearish claim is unaffected by this -- it is still ordinary verified
    support for that (bearish) claim, exactly as evidence_stance already
    routes it.

    Never conflates this with ``evidence_stance`` (the claim's OWN
    direction relative to an Alpha) -- this function does not read or
    return anything about direction; a caller keeps using evidence_stance
    for bull/bear role assignment exactly as today, and uses this
    function's ``eligible`` flag only to decide whether that already-
    classified claim counts as VERIFIED.
    """
    if record.get("source_link_status") != SOURCE_LINK_VALID or not record.get("linked_source_id"):
        return {"eligible": False, "reason_code": ELIGIBILITY_REASON_SOURCE_LINK_NOT_VALID}

    review = record.get("content_support_review")
    if not isinstance(review, Mapping) or review.get("method") not in AUTOMATICALLY_ELIGIBLE_REVIEW_METHODS:
        return {"eligible": False, "reason_code": ELIGIBILITY_REASON_NOT_REVIEWED}

    status = review.get("status")
    if status not in _RESOLVED_SUPPORT_STATUSES:
        return {"eligible": False, "reason_code": ELIGIBILITY_REASON_SUPPORT_STATUS_NOT_RESOLVED}

    if str(review.get("claim_id") or "") != str(record.get("claim_id") or ""):
        return {"eligible": False, "reason_code": ELIGIBILITY_REASON_REVIEW_CLAIM_MISMATCH}

    # Round 18: a review binds the source the verifier actually USED
    # (``review["linked_source_id"]`` and that source's hash -- see
    # content_support_llm._apply_result). For a claim that cites several
    # sources that is not necessarily the record's primary link, so the
    # binding (and the time check) must be resolved against the REVIEW'S
    # source, which must itself be one of this claim's linked sources.
    # Reviews without their own source id (and every single-source claim)
    # resolve exactly as before.
    def _resolve(source_id: Any) -> dict[str, Any] | None:
        return resolve_fragment_by_id(source_id, sources or []) or resolve_source_by_id(source_id, sources or [])

    resolved = _resolve(record["linked_source_id"])
    review_source_id = review.get("linked_source_id")
    if review_source_id and review_source_id != record["linked_source_id"]:
        review_source = _resolve(review_source_id)
        allowed_ids = {record["linked_source_id"], *(record.get("linked_source_ids") or ())}
        allowed = {
            candidate.get("source_id") for candidate in map(_resolve, allowed_ids) if candidate is not None
        }
        if review_source is None or review_source.get("source_id") not in allowed:
            return {"eligible": False, "reason_code": ELIGIBILITY_REASON_REVIEW_SOURCE_NOT_LINKED}
        resolved = review_source
    if resolved is None or not resolved.get("content_hash"):
        return {"eligible": False, "reason_code": ELIGIBILITY_REASON_SOURCE_NOT_RESOLVABLE}

    if not resolved.get("published_at"):
        availability = evaluate_source_availability(resolved)
        if not availability["available_before_cutoff"]:
            return {"eligible": False, "reason_code": availability["reason_code"]}

    if str(review.get("content_hash") or "") != str(resolved.get("content_hash") or ""):
        return {"eligible": False, "reason_code": ELIGIBILITY_REASON_CONTENT_VERSION_CHANGED_SINCE_REVIEW}

    if status == SUPPORT_OPPOSES:
        return {
            "eligible": False,
            "reason_code": ELIGIBILITY_REASON_SOURCE_OPPOSES_CLAIM,
            "support_status": SUPPORT_OPPOSES,
        }

    return {"eligible": True, "reason_code": ELIGIBILITY_REASON_ELIGIBLE, "support_status": SUPPORT_SUPPORTS}


# ---------------------------------------------------------------------------
# Verified-support diagnostic category (2026-09-29 gate-bypass closing fix):
# a bare ELIGIBILITY_REASON_SOURCE_LINK_NOT_VALID is shared by two entirely
# different situations that must never be conflated for a human reading the
# result -- "this claim's own source type (market/financial/macro/derived-
# indicator) has no real source-capture-to-linking mechanism wired up at
# all this round" (a genuine SCOPE gap, not a defect in this specific claim)
# versus "this claim's source type IS wired up (today: news), but resolving
# THIS specific reference failed" (a real, per-claim problem). Never
# inferred from the bare NOT_PROVIDED status code alone -- this classifier
# additionally checks the record's own source_type against the currently-
# covered set.
# ---------------------------------------------------------------------------

DIAGNOSTIC_ELIGIBLE = "ELIGIBLE"
DIAGNOSTIC_SOURCE_TYPE_NOT_YET_COVERED = "SOURCE_TYPE_NOT_YET_COVERED"
DIAGNOSTIC_REFERENCE_MISSING_OR_INVALID = "REFERENCE_MISSING_OR_INVALID"
DIAGNOSTIC_CONTENT_SUPPORT_PENDING_REVIEW = "CONTENT_SUPPORT_PENDING_REVIEW"
DIAGNOSTIC_SOURCE_OPPOSES_CLAIM = "SOURCE_OPPOSES_CLAIM"
DIAGNOSTIC_DISCLOSURE_TIME_UNKNOWN = "DISCLOSURE_TIME_UNKNOWN"

# The only PRODUCTION AGENTS with a real capture-to-registry-to-linking
# mechanism wired up, keyed by the structured record's own ``agent`` field:
# - news_agent (tradingagents.dataflows.yfinance_news -> source_capture ->
#   build_source_registry -> structured_output_adapter's content-match/
#   marker linking; 2026-09-29: also tradingagents.dataflows.fred
#   .get_macro_data via the news_analyst's own get_macro_indicators tool --
#   the SAME marker-linking mechanism, macro-indicator claims only).
# - market_agent (2026-09-29: tradingagents.dataflows.market_data_validator
#   .build_verified_market_snapshot -> source_capture -> build_source_
#   registry -> the SAME marker-linking mechanism -- OHLCV/technical-
#   indicator claims only; get_stock_data's own raw CSV tool call is not
#   separately wired).
# - fundamental_agent (2026-09-29: tradingagents.dataflows.y_finance
#   .get_fundamentals ONLY -> source_capture -> build_source_registry ->
#   the SAME marker-linking mechanism -- current-snapshot valuation claims
#   (e.g. market cap, trailing P/E) only. get_balance_sheet/get_cashflow/
#   get_income_statement are deliberately NOT covered: yfinance exposes
#   only each statement's fiscal PERIOD END date, never a real disclosure/
#   filing date, so treating a period-end as the evidence-cutoff-relevant
#   "published_at" would create a real, unmitigated look-ahead risk --
#   exactly the report-period-vs-disclosure-time conflation this round's
#   task explicitly warns against. get_fundamentals itself sidesteps this
#   because its .info-derived figures are CURRENT/live-computed, so using
#   retrieval time as published_at is honest rather than assumed.)
# Deliberately keyed by ``agent``, NOT by the record's own ``source_type``
# field: source_type is set by structured_output_adapter.infer_source_type
# (agent, claim) from crude text/agent-name heuristics (e.g. market_agent
# claims classify as "price" or "unknown", never literally "market") --
# using it here would silently under- or over-match depending on
# incidental wording, rather than naming the real, wired production chain a
# claim actually came from. Extend this set ONLY when an agent's own claims
# gain a real capture-to-linking path -- never merely because a claim
# happens to carry a plausible-looking source_type string.
LINKED_AGENT_COVERAGE = frozenset({"news_agent", "market_agent", "fundamental_agent"})


def classify_verified_support_diagnostic(
    record: Mapping[str, Any], sources: list[dict[str, Any]] | None
) -> dict[str, Any]:
    """Explains WHY ``record`` does or does not count as verified support,
    at a level suitable for direct API/UI display. Reuses
    ``compute_verified_support_eligibility`` unmodified for the real
    eligibility determination -- this only adds a coarser, display-oriented
    ``category`` on top of its own ``reason_code``, distinguishing:

    - ``SOURCE_TYPE_NOT_YET_COVERED``: this claim's own producing AGENT has
      no real source-linking mechanism at all (a scope gap, not a
      per-claim defect).
    - ``REFERENCE_MISSING_OR_INVALID``: the producing agent IS covered, but
      resolving/keeping this specific reference valid failed (unresolved
      id, content unavailable, time-invalid, stale content hash, or a
      review recorded against a different claim).
    - ``CONTENT_SUPPORT_PENDING_REVIEW``: a real, current, resolvable
      reference exists; nothing has reviewed it yet (or review status was
      BACKGROUND/CITATION_ONLY/CONDITIONAL -- resolved-but-not-direct).
    - ``SOURCE_OPPOSES_CLAIM``: a real, current, HUMAN_REVIEWED verdict
      exists and it rebuts the claim -- real information, but the opposite
      of support (never counted as eligible; see ``compute_verified_
      support_eligibility``'s own OPPOSES handling).
    - ``DISCLOSURE_TIME_UNKNOWN`` (2026-09-29): a real, current, resolvable,
      even HUMAN_REVIEWED SUPPORTS reference exists, but its own
      ``published_at`` is genuinely unknown (e.g. a fiscal-statement line
      item with no recorded disclosure date) -- distinct from
      ``REFERENCE_MISSING_OR_INVALID``: the reference itself is valid, only
      its timing eligibility is unresolved, so it is never counted as
      officially verified support, but never claimed to be "invalid"
      either.
    - ``ELIGIBLE``: counts as verified support.
    """
    eligibility = compute_verified_support_eligibility(record, sources)
    detail_code = eligibility["reason_code"]
    if eligibility["eligible"]:
        return {"category": DIAGNOSTIC_ELIGIBLE, "detail_code": detail_code}
    if detail_code == ELIGIBILITY_REASON_SOURCE_OPPOSES_CLAIM:
        return {"category": DIAGNOSTIC_SOURCE_OPPOSES_CLAIM, "detail_code": detail_code}
    if detail_code in (ELIGIBILITY_REASON_DISCLOSURE_TIME_UNKNOWN, ELIGIBILITY_REASON_AVAILABILITY_AFTER_CUTOFF):
        return {"category": DIAGNOSTIC_DISCLOSURE_TIME_UNKNOWN, "detail_code": detail_code}
    if detail_code in (
        ELIGIBILITY_REASON_NOT_REVIEWED,
        ELIGIBILITY_REASON_SUPPORT_STATUS_NOT_RESOLVED,
    ):
        return {"category": DIAGNOSTIC_CONTENT_SUPPORT_PENDING_REVIEW, "detail_code": detail_code}
    if detail_code == ELIGIBILITY_REASON_SOURCE_LINK_NOT_VALID:
        if record.get("agent") not in LINKED_AGENT_COVERAGE:
            return {"category": DIAGNOSTIC_SOURCE_TYPE_NOT_YET_COVERED, "detail_code": detail_code}
        return {"category": DIAGNOSTIC_REFERENCE_MISSING_OR_INVALID, "detail_code": detail_code}
    # REVIEW_CLAIM_MISMATCH / CONTENT_VERSION_CHANGED_SINCE_REVIEW /
    # SOURCE_NOT_RESOLVABLE: a real reference/review existed at some point,
    # but the current binding no longer holds -- a genuine reference
    # problem, never a coverage gap or a pending-review state.
    return {"category": DIAGNOSTIC_REFERENCE_MISSING_OR_INVALID, "detail_code": detail_code}


# The genuine, upstream-suppliable fields a SourceRecord may carry. Every one
# of these is optional (an upstream item legitimately may not provide all of
# them) except source_type, name, and retrieved_at, which this module itself
# always sets deterministically for every record it builds.
_SOURCE_RECORD_FIELDS = (
    "source_id",
    "fragment_id",
    "source_type",
    "name",
    "title",
    "url",
    "published_at",
    "retrieved_at",
    "external_record_id",
    "locator",
    "provider",
    "metadata_status",
    "excerpt",
    "content_hash",
    # Market-data source chain (2026-09-29, reuses this SAME SourceRecord
    # shape/registry/gate/review/API/export machinery -- no parallel system):
    # a news article has no natural "instrument"/"unit"/"timezone"/raw-row
    # concept, so these four are additive and optional, always None for a
    # news-sourced record. instrument/observation_date/timezone/unit name
    # the axes the task spec requires distinctly (never folded into title/
    # locator as an opaque string); data_snapshot is the actual captured
    # row/indicator values (a plain, JSON-serializable dict), never
    # LLM-derived -- the same real-tool-output-only rule every other field
    # here already follows.
    "instrument",
    "observation_date",
    "timezone",
    "unit",
    "data_snapshot",
    # Derived-indicator source chain (2026-09-29, same reuse principle: a
    # raw market OHLCV record has no calculation to name, so these three
    # are additive and optional, always None for a plain market/news
    # record). calculation_method/calculation_version name WHAT formula and
    # WHICH library/version computed a derived value (e.g. "rsi" via
    # "stockstats==0.6.8") -- never a bare "the model said so."
    # calculation_params carries the real inputs a caller would need to
    # independently reproduce the SAME result from frozen data (e.g. the
    # exact OHLCV window/period the formula ran over) -- a plain, JSON-
    # serializable structure, never LLM-derived.
    "calculation_method",
    "calculation_version",
    "calculation_params",
    # Round 18: the versioned "available before the evidence cutoff" record
    # of an undated live data snapshot (see evaluate_source_availability).
    # Additive: only present on a source that carries one.
    "availability",
)

# A title/excerpt this short is not a reliable enough anchor for a substring
# match against free-text claim/evidence prose -- too likely to
# false-positive on an unrelated sentence that happens to share a short
# phrase. Below this length, the source is still registered (with whatever
# status its own fields justify) but is never offered as a claim match.
_MIN_MATCHABLE_TITLE_LENGTH = 12
_MIN_MATCHABLE_EXCERPT_LENGTH = 20


def make_source_id(*, source_type: str, name: str, title: str, url: str) -> str:
    """Deterministic, content-derived id: the SAME real source (same type,
    name, title, url) always yields the same id -- including across two
    different tool calls that happen to surface the identical article
    (e.g. ticker-specific news and global news both returning the same
    story). Never randomized, never dependent on fetch order."""
    digest_input = "|".join([source_type or "", name or "", title or "", url or ""])
    digest = hashlib.sha256(digest_input.encode("utf-8")).hexdigest()
    return f"src_{digest[:16]}"


def classify_metadata_status(*, name: str | None, title: str | None, url: str | None) -> str:
    """Section 14's vocabulary, derived purely from which genuine fields the
    upstream item actually supplied -- never from claim text, never from a
    model's opinion of confidence.

    TRACEABLE: a real name/publisher AND a real title AND a real URL.
    PARTIAL: at least a real name or title, but not all three (e.g. a
        filing/dataset record identified by name+title with no ordinary web
        URL -- test case B in the task's own spec).
    UNAVAILABLE: nothing genuinely identifying was supplied.
    """
    has_name = bool((name or "").strip())
    has_title = bool((title or "").strip())
    has_url = bool((url or "").strip())
    if has_name and has_title and has_url:
        return STATUS_TRACEABLE
    if has_name or has_title or has_url:
        return STATUS_PARTIAL
    return STATUS_UNAVAILABLE


def fragment_id_for(source_id: str, fragment_index: int = 0) -> str:
    """The id a claim cites for one specific locatable excerpt within a
    source. News/announcement sources captured by this round's chain carry
    exactly one excerpt (the whole captured summary) -- fragment_index 0 --
    but the id scheme itself supports a future source with several
    independently locatable excerpts (e.g. distinct paragraphs of one
    filing) without a breaking change."""
    return f"{source_id}:frag:{fragment_index}"


def build_source_record(
    *,
    source_type: str,
    name: str | None = None,
    title: str | None = None,
    url: str | None = None,
    published_at: str | None = None,
    retrieved_at: str,
    external_record_id: str | None = None,
    locator: str | None = None,
    provider: str | None = None,
    excerpt: str | None = None,
    instrument: str | None = None,
    observation_date: str | None = None,
    timezone: str | None = None,
    unit: str | None = None,
    data_snapshot: Any | None = None,
    calculation_method: str | None = None,
    calculation_version: str | None = None,
    calculation_params: Any | None = None,
) -> dict[str, Any]:
    """Build one ``SourceRecord`` dict from fields already supplied by a
    real upstream tool adapter (see ``tradingagents.dataflows.source_capture
    .record_source`` call sites). Never called with LLM-generated content --
    every keyword argument here must trace back to an actual tool/API
    response field.

    ``excerpt`` (T1 source-linking chain): the genuine, already-extracted
    raw text snippet the upstream adapter itself returned for this item
    (e.g. yfinance's own article summary) -- never LLM-paraphrased, never
    re-derived from claim prose. When present, a ``content_hash`` (sha256
    of the excerpt) and a ``fragment_id`` are both stamped so a claim can
    cite a specific, content-addressed, locatable piece of text rather than
    only the source's bare identity. Absent excerpt -> no fragment_id, no
    content_hash -- this source is registered (identity is still real and
    traceable) but has no content a claim could actually be linked to,
    which :func:`validate_source_reference` reports honestly as
    ``SOURCE_LINK_CONTENT_UNAVAILABLE`` rather than silently accepting a
    plain identity match as if it were content-locatable.

    ``instrument``/``observation_date``/``timezone``/``unit``/
    ``data_snapshot`` (market-data source chain, 2026-09-29): additive,
    optional -- always ``None`` for a news-sourced record, and reused
    as-is (never a parallel schema) by any future non-news source type
    that has its own real structured-value concept (financial/macro/
    derived-indicator). ``data_snapshot`` is the actual captured row/
    indicator values, a plain JSON-serializable structure -- never
    LLM-derived, same as every other field here.

    ``calculation_method``/``calculation_version``/``calculation_params``
    (derived-indicator source chain, 2026-09-29): additive, optional --
    always ``None`` for a raw (non-derived) record. Names WHAT formula and
    WHICH library/version computed a derived value, and the real inputs
    (e.g. the exact OHLCV window/period) needed to independently reproduce
    it from frozen data -- never a bare reference to a model-generated
    number.
    """
    name = (name or "").strip() or None
    title = (title or "").strip() or None
    url = (url or "").strip() or None
    excerpt = (excerpt or "").strip() or None
    source_id = make_source_id(source_type=source_type, name=name or "", title=title or "", url=url or "")
    record: dict[str, Any] = {
        "source_id": source_id,
        "source_type": source_type,
        "name": name,
        "title": title,
        "url": url,
        "published_at": published_at,
        "retrieved_at": retrieved_at,
        "external_record_id": external_record_id,
        "locator": locator,
        "provider": provider,
        "excerpt": excerpt,
        "content_hash": hashlib.sha256(excerpt.encode("utf-8")).hexdigest() if excerpt else None,
        "fragment_id": fragment_id_for(source_id, 0) if excerpt else None,
        "instrument": instrument,
        "observation_date": observation_date,
        "timezone": timezone,
        "unit": unit,
        "data_snapshot": data_snapshot,
        "calculation_method": calculation_method,
        "calculation_version": calculation_version,
        "calculation_params": calculation_params,
    }
    record["metadata_status"] = classify_metadata_status(name=name, title=title, url=url)
    return record


def build_source_registry(
    *, run_id: str, ticker: str, retrieved_at: str, captured_records: list[dict[str, Any]] | None
) -> dict[str, Any]:
    """Turn one run's raw captured items (plain dicts with whatever subset
    of ``source_type``/``name``/``title``/``url``/``published_at``/
    ``external_record_id``/``locator``/``provider``/``excerpt``/
    ``instrument``/``observation_date``/``timezone``/``unit``/
    ``data_snapshot`` a dataflow call site actually had -- see
    ``tradingagents.dataflows.source_capture``) into fully-built, deduped
    (by the resulting deterministic ``source_id``) ``SourceRecord`` dicts,
    wrapped in the persisted ``source_registry.json`` shape. ``retrieved_at``
    is stamped onto every record built here -- "when this run's registry
    was assembled", a single honest timestamp per run rather than requiring
    the acquisition layer to format its own."""
    by_id: dict[str, dict[str, Any]] = {}
    for raw in captured_records or []:
        if not isinstance(raw, dict) or not raw.get("source_type"):
            continue
        built = build_source_record(
            source_type=raw.get("source_type"),
            name=raw.get("name"),
            title=raw.get("title"),
            url=raw.get("url"),
            published_at=raw.get("published_at"),
            retrieved_at=retrieved_at,
            external_record_id=raw.get("external_record_id"),
            locator=raw.get("locator"),
            provider=raw.get("provider"),
            excerpt=raw.get("excerpt"),
            instrument=raw.get("instrument"),
            observation_date=raw.get("observation_date"),
            timezone=raw.get("timezone"),
            unit=raw.get("unit"),
            data_snapshot=raw.get("data_snapshot"),
            calculation_method=raw.get("calculation_method"),
            calculation_version=raw.get("calculation_version"),
            calculation_params=raw.get("calculation_params"),
        )
        by_id.setdefault(built["source_id"], built)
    sources = [by_id[key] for key in sorted(by_id)]
    return {
        "schema_version": SOURCE_REGISTRY_SCHEMA_VERSION,
        "run_id": run_id,
        "ticker": ticker,
        "source_count": len(sources),
        "sources": sources,
    }


def resolve_source_by_id(source_id: Any, sources: list[dict[str, Any]]) -> dict[str, Any] | None:
    """Defensive lookup: returns the matching source only if ``source_id``
    is a real member of THIS run's own registry. Any id this run's registry
    does not recognize -- including one a model invented or one from a
    different run -- resolves to ``None``, never a partial/best-guess match.
    This is the validation boundary Section 6 requires for any source
    reference, model-supplied or otherwise."""
    if not isinstance(source_id, str) or not source_id:
        return None
    for source in sources or []:
        if isinstance(source, dict) and source.get("source_id") == source_id:
            return source
    return None


def find_matching_source(text: str, sources: list[dict[str, Any]] | None) -> dict[str, Any] | None:
    """Deterministic, case-insensitive substring match of a source's own
    genuine ``title`` against already-persisted claim/evidence text --
    never the reverse (never extracts/guesses a title FROM the text). No LLM
    call, no fuzzy matching, no publisher-name-only matching (a bare
    publisher mention is too weak a signal on its own -- see module
    docstring). Returns the first matching source in registry order, or
    ``None`` when nothing matches."""
    if not text or not sources:
        return None
    haystack = text.lower()
    for source in sources:
        if not isinstance(source, dict):
            continue
        title = source.get("title")
        if not isinstance(title, str):
            continue
        if len(title) < _MIN_MATCHABLE_TITLE_LENGTH:
            continue
        if title.lower() in haystack:
            return source
    return None


def resolve_external_source_for_claim(
    *, claim: str | None, evidence: str | None, sources: list[dict[str, Any]] | None
) -> tuple[dict[str, Any] | None, str]:
    """The one function API/export code should call to annotate a claim.
    Tries the evidence text first (the more specific, usually longer field),
    then the claim text. Returns ``(source_or_None, external_source_status)``
    -- status is always one of ``VALID_SOURCE_STATUSES``, and is
    ``UNAVAILABLE`` whenever no source is returned, including when the
    registry itself is empty or absent."""
    match = find_matching_source(evidence or "", sources) or find_matching_source(claim or "", sources)
    if match is None:
        return None, STATUS_UNAVAILABLE
    return match, match.get("metadata_status", STATUS_UNAVAILABLE)


def resolve_fragment_by_id(fragment_id: Any, sources: list[dict[str, Any]]) -> dict[str, Any] | None:
    """Same defensive-lookup contract as :func:`resolve_source_by_id`, keyed
    by the per-fragment id a claim would cite for one specific locatable
    excerpt. An id this run's registry does not recognize -- including one
    a model invented -- resolves to ``None``, never a best-guess match."""
    if not isinstance(fragment_id, str) or not fragment_id:
        return None
    for source in sources or []:
        if isinstance(source, dict) and source.get("fragment_id") == fragment_id:
            return source
    return None


def match_evidence_to_source_candidates(
    evidence: str | None, claim: str | None, sources: list[dict[str, Any]] | None
) -> list[str]:
    """Deterministic, CONTENT-based candidate linkage proposal (T1: "title
    matching must no longer be the primary linkage mechanism"): proposes
    ``fragment_id``s whose captured excerpt -- a real sentence/paragraph the
    upstream adapter itself extracted, never a headline -- overlaps this
    claim's evidence/claim text as an exact (whitespace-normalized)
    substring, in either direction (the claim's evidence contains the
    excerpt verbatim, or -- when a deterministic segmenter copied a
    source's own summary text into the segment -- the excerpt contains the
    evidence text).

    This is still only ever a LINKAGE CANDIDATE, never proof of content
    support: every id returned here must still pass
    :func:`validate_source_reference` before being treated as
    ``SOURCE_LINK_VALID``, and a valid link is never, by itself, treated as
    ``SUPPORT_SUPPORTS`` (see :func:`validate_source_reference`'s own
    docstring and this module's top-of-file section on the two separate
    axes). Returns candidate ``fragment_id``s in registry order; never
    raises; empty input or an empty/absent registry yields ``[]``.
    """
    candidates: list[str] = []
    haystacks = [" ".join(t.split()).lower() for t in (evidence, claim) if isinstance(t, str) and t.strip()]
    if not haystacks or not sources:
        return candidates
    for source in sources:
        if not isinstance(source, dict):
            continue
        excerpt = source.get("excerpt")
        fragment_id = source.get("fragment_id")
        if not isinstance(excerpt, str) or not fragment_id:
            continue
        normalized_excerpt = " ".join(excerpt.split()).lower()
        if len(normalized_excerpt) < _MIN_MATCHABLE_EXCERPT_LENGTH:
            continue
        for haystack in haystacks:
            if normalized_excerpt in haystack or haystack in normalized_excerpt:
                candidates.append(fragment_id)
                break
    return candidates


# Round 3 (2026-10-04), no-marker candidate linking: "全体子串匹配" above
# requires the WHOLE excerpt (or WHOLE claim) to be a substring of the
# other -- it cannot handle a claim that reformats a single captured
# NUMBER (thousands separators, M/million/B/billion/K/thousand scale
# suffixes, or rounds to fewer display digits than the raw stored value)
# while wrapping it in ordinary prose. This is a SEPARATE, additive
# mechanism -- it never replaces or loosens the whole-excerpt matcher
# above, and it only ever matches a SPECIFIC, already-saved NUMERIC field,
# never free text. See match_evidence_to_source_candidates_normalized's
# own docstring for the exact scope and the ambiguity-preservation
# contract (COMQUTOR Alpha 下一轮开发任务单 section 5: 受约束的数字格式差异,
# 从不无约束模糊匹配, 多个同样合理候选必须保留歧义).
_SCALE_SUFFIX_MULTIPLIERS: dict[str, float] = {
    "k": 1e3, "thousand": 1e3,
    "m": 1e6, "mm": 1e6, "million": 1e6,
    "b": 1e9, "bn": 1e9, "billion": 1e9,
    "t": 1e12, "trillion": 1e12,
}
_SCALED_NUMBER_PATTERN = re.compile(
    r"(?<![\w.])(?P<num>\d{1,3}(?:,\d{3})+(?:\.\d+)?|\d+\.\d+|\d+)"
    r"\s?(?P<suffix>thousand|million|billion|trillion|mm|bn|[kmbt])?\b",
    re.IGNORECASE,
)
# A number with no scale suffix and 3 or fewer digits (e.g. "14", "200")
# is too common/unspecific to serve as a confident linking signal on its
# own -- it would false-positive-match almost any source with ANY nearby
# count. Only a number carrying a scale suffix, a decimal point, or at
# least 4 integer digits is specific enough to be used here.
_MIN_UNSCALED_INTEGER_DIGITS = 4


def _extract_scaled_numeric_tokens(text: str) -> list[dict[str, Any]]:
    tokens: list[dict[str, Any]] = []
    for match in _SCALED_NUMBER_PATTERN.finditer(text or ""):
        raw_num = match.group("num").replace(",", "")
        suffix = (match.group("suffix") or "").lower()
        try:
            value = float(raw_num)
        except ValueError:
            continue
        scale = _SCALE_SUFFIX_MULTIPLIERS.get(suffix, 1.0)
        decimal_places = len(raw_num.split(".", 1)[1]) if "." in raw_num else 0
        has_decimal = "." in raw_num
        integer_digits = len(raw_num.split(".", 1)[0])
        if scale == 1.0 and not has_decimal and integer_digits < _MIN_UNSCALED_INTEGER_DIGITS:
            continue
        tokens.append({"value": value, "scale": scale, "decimal_places": decimal_places, "raw": match.group(0)})
    return tokens


def iter_source_numeric_leaves(value: Any, path: tuple[str, ...] = ()) -> list[tuple[tuple[str, ...], float]]:
    """Walks a source's own already-saved ``data_snapshot`` (or any nested
    dict/list within it -- e.g. Round 2's ``all_line_items``/``periods``)
    and yields every leaf that is genuinely numeric, including a numeric
    STRING (several real captured snapshots -- e.g. the market OHLCV
    excerpt's own ``data_snapshot["ohlcv"]``, store values as strings).
    Never a text field, never inferred -- only a value the acquisition
    layer itself already wrote."""
    leaves: list[tuple[tuple[str, ...], float]] = []
    if isinstance(value, Mapping):
        for key, sub_value in value.items():
            leaves.extend(iter_source_numeric_leaves(sub_value, path + (str(key),)))
    elif isinstance(value, (list, tuple)):
        for index, sub_value in enumerate(value):
            leaves.extend(iter_source_numeric_leaves(sub_value, path + (str(index),)))
    elif isinstance(value, bool):
        pass
    elif isinstance(value, (int, float)):
        leaves.append((path, float(value)))
    elif isinstance(value, str):
        try:
            leaves.append((path, float(value.replace(",", ""))))
        except ValueError:
            pass
    return leaves


def _scaled_value_matches(raw_value: float, token: dict[str, Any]) -> bool:
    """A claim token like ``121.7M`` is a ROUNDED display of a raw stored
    value (e.g. ``121732200``) -- not bit-exact equal to it. This compares
    after scaling the RAW value down by the claim's own stated scale and
    rounding to the claim's own stated decimal precision ("数值与展示精度"),
    never the other way around (the raw stored value is never rounded
    UP/invented to match a claim)."""
    scaled = raw_value / token["scale"]
    return round(scaled, token["decimal_places"]) == token["value"]


_DATE_LIKE_TOKEN_PATTERN = re.compile(
    r"\b\d{4}-\d{2}-\d{2}\b|\b\d{1,2}[/-]\d{1,2}\b"
)


def match_evidence_to_source_candidates_normalized(
    evidence: str | None,
    claim: str | None,
    sources: list[dict[str, Any]] | None,
    *,
    instrument: str | None = None,
) -> dict[str, Any]:
    """Round 3 (2026-10-04) addition, additive and separate from
    :func:`match_evidence_to_source_candidates` (never replaces it; tried
    only when the whole-excerpt matcher above found nothing). Locates a
    SPECIFIC already-saved numeric field whose value -- after honoring
    thousands separators, an M/million/B/billion/K/thousand scale suffix,
    and display-precision rounding -- equals a number genuinely present in
    the claim/evidence text, by walking each candidate source's own
    ``data_snapshot`` (never its excerpt prose).

    Scope, deliberately bounded (see John 下一轮开发任务单 section 5): this
    is NUMBER-FORMAT normalization only -- thousands separators, scale
    suffixes, percent/precision differences. It is never unconstrained
    fuzzy text matching, never a metric-name/alias resolver, and a bare
    low-specificity number (3 digits or fewer, no decimal, no scale
    suffix -- see ``_MIN_UNSCALED_INTEGER_DIGITS``) is never used as a
    matching signal on its own.

    Object/time guard: when ``instrument`` is given and a candidate
    source's own ``instrument`` field is a DIFFERENT real value, that
    source is skipped for this claim -- a claim's own run-ticker context
    is never used to override a source's own, more specific recorded
    identity. When the claim text contains an explicit calendar date/day
    token that differs from the source's own ``observation_date``, that
    source is also skipped -- a single-day snapshot never backs a claim
    about a different day's figure merely because some other number
    happens to coincide.

    Ambiguity is preserved, never silently resolved: when the SAME
    matching number is genuinely present in TWO OR MORE DISTINCT sources'
    (different ``source_id``) data, this returns no candidate for that
    number at all -- ``ambiguous_source_ids`` names every source involved,
    for transparency, but none of them is guessed as "the" answer.

    Returns ``{"candidates": [fragment_id, ...], "matched_fields":
    {fragment_id: [dotted_field_path, ...]}, "ambiguous_numbers":
    [{"raw": matched_text, "source_ids": [...]}]}``. Every returned
    ``fragment_id`` still has to separately pass
    :func:`validate_source_reference`, exactly like the whole-excerpt
    matcher's candidates -- this function only ever proposes, never
    validates."""
    result: dict[str, Any] = {"candidates": [], "matched_fields": {}, "ambiguous_numbers": []}
    haystacks = [t for t in (evidence, claim) if isinstance(t, str) and t.strip()]
    if not haystacks or not sources:
        return result

    tokens: list[dict[str, Any]] = []
    for haystack in haystacks:
        tokens.extend(_extract_scaled_numeric_tokens(haystack))
    if not tokens:
        return result

    claim_date_tokens = set()
    for haystack in haystacks:
        claim_date_tokens.update(m.group(0) for m in _DATE_LIKE_TOKEN_PATTERN.finditer(haystack))

    eligible_sources = []
    for source in sources:
        if not isinstance(source, dict):
            continue
        fragment_id = source.get("fragment_id")
        if not fragment_id:
            continue
        source_instrument = source.get("instrument")
        if instrument and source_instrument and str(source_instrument) != str(instrument):
            continue
        observation_date = source.get("observation_date")
        if observation_date and claim_date_tokens:
            # A short-form token ("09-30") is the SAME calendar day as the
            # source's full "2026-09-30" when one is a substring of the
            # other -- never only exact string equality. A claim naming
            # BOTH the matching day and a different day (e.g. contrasting
            # today's figure against a prior day's) still gets to use this
            # source -- only a claim naming EXCLUSIVELY other days skips it.
            any_matching_day = any(
                tok == observation_date or tok in observation_date or observation_date in tok
                for tok in claim_date_tokens
            )
            if not any_matching_day:
                continue
        snapshot = source.get("data_snapshot")
        if not isinstance(snapshot, (Mapping, list)):
            continue
        eligible_sources.append((source.get("source_id"), fragment_id, iter_source_numeric_leaves(snapshot)))

    seen_raw_tokens: set[str] = set()
    for token in tokens:
        if token["raw"] in seen_raw_tokens:
            continue
        seen_raw_tokens.add(token["raw"])
        matches_by_source: dict[str, tuple[str, list[tuple[str, ...]]]] = {}
        for source_id, fragment_id, leaves in eligible_sources:
            matched_paths = [path for path, raw_value in leaves if _scaled_value_matches(raw_value, token)]
            if matched_paths:
                matches_by_source[source_id] = (fragment_id, matched_paths)
        if len(matches_by_source) > 1:
            result["ambiguous_numbers"].append(
                {"raw": token["raw"], "source_ids": sorted(matches_by_source.keys())}
            )
            continue
        if len(matches_by_source) == 1:
            ((fragment_id, matched_paths),) = matches_by_source.values()
            if fragment_id not in result["candidates"]:
                result["candidates"].append(fragment_id)
            result["matched_fields"].setdefault(fragment_id, [])
            for path in matched_paths:
                label = ".".join(path)
                if label not in result["matched_fields"][fragment_id]:
                    result["matched_fields"][fragment_id].append(label)
    return result


# The label tolerates a missing underscore ("fragment_id" or "fragmentid")
# because comqutor_alpha.structure_engine.structured_output_adapter's own
# markdown-inline cleaner (`_clean_markdown_inline`, applied to every
# segmented claim/evidence text BEFORE this function ever sees it) strips
# every literal underscore character as a markdown emphasis marker -- this
# is pre-existing, deliberate, and out of scope to change; a marker format
# that assumed underscores survive would silently never match in real
# production text.
_SOURCE_REFERENCE_MARKER_PATTERN = re.compile(r"\[fragment_?id:\s*([^\]\s]+)\]")


def _without_underscores(value: str) -> str:
    return value.replace("_", "")


def extract_source_marker_from_text(text: str | None, sources: list[dict[str, Any]] | None) -> str | None:
    """T1 follow-up, 2026-09-28: detects a literal ``[fragment_id: ...]``
    marker -- see ``tradingagents.dataflows.yfinance_news.
    _source_reference_marker``, which embeds this SAME deterministic id
    directly into the tool message text the ORIGINAL research agent (e.g.
    ``news_analyst``) itself reads -- inside already-generated claim/report
    text.

    This is the one deterministic, offline way to tell whether the
    ORIGINAL research agent's own free-text output preserved the real
    source reference its own tool call offered it, as distinct from:
    - the separate, LATER extraction-stage enrichment Agent's own
      structured ``cited_source_id`` (an after-the-fact selection from an
      offered candidate list -- see ``structured_output_adapter.py``'s
      ``_llm_batch_enrichment``), and
    - :func:`match_evidence_to_source_candidates`'s pure excerpt-text
      overlap (no explicit reference at all, just coincidental wording).

    Matches the captured marker text against each real registry
    ``fragment_id`` with underscores stripped from BOTH sides first (see
    the pattern's own comment above for why) -- so this correctly resolves
    the marker whether or not the id's underscores happened to survive
    upstream text processing, while still only ever returning a REAL,
    already-registered fragment_id (a marker an LLM invented, mangled
    beyond this one known transformation, or copied from unrelated context
    still never resolves, never a best-guess match). Never raises;
    missing/empty text or registry returns ``None``.

    Finding a resolvable marker here proves the marker SURVIVED into this
    text -- it does not, by itself, measure how often a real model
    preserves it versus drops it while paraphrasing (that compliance rate
    is unmeasured and must never be claimed as proven by this function's
    mere existence).
    """
    if not text:
        return None
    match = _SOURCE_REFERENCE_MARKER_PATTERN.search(text)
    if not match:
        return None
    candidate = _without_underscores(match.group(1))
    for source in sources or ():
        if not isinstance(source, dict):
            continue
        fragment_id = source.get("fragment_id")
        if isinstance(fragment_id, str) and _without_underscores(fragment_id) == candidate:
            return fragment_id
    return None


def extract_all_source_markers_from_text(
    text: str | None, sources: list[dict[str, Any]] | None
) -> list[str]:
    """Round 3 (2026-10-04), multi-reference support: like
    :func:`extract_source_marker_from_text`, but returns EVERY distinct,
    resolvable ``[fragment_id: ...]`` marker found in ``text`` (in order of
    first appearance), not only the first. A claim combining several
    cited figures in one sentence (each carrying its own marker, per
    :func:`tradingagents.agents.utils.agent_utils.
    get_citation_forwarding_instruction`'s own instruction to keep every
    figure's own tag) must not lose every reference but the first --
    see ``get_citation_forwarding_instruction``'s explicit "do not drop
    any but the first" instruction, which this function's existence makes
    actually honorable downstream. An unresolvable marker (not a real,
    registered fragment_id in THIS run) is simply skipped, exactly like
    the single-marker function's own contract -- never a fabricated id."""
    if not text:
        return []
    found: list[str] = []
    for match in _SOURCE_REFERENCE_MARKER_PATTERN.finditer(text):
        candidate = _without_underscores(match.group(1))
        for source in sources or ():
            if not isinstance(source, dict):
                continue
            fragment_id = source.get("fragment_id")
            if isinstance(fragment_id, str) and _without_underscores(fragment_id) == candidate:
                if fragment_id not in found:
                    found.append(fragment_id)
                break
    return found


def _parse_iso_like(value: Any) -> dt.datetime | None:
    """Best-effort, deterministic ISO-8601 parse (date-only or full
    datetime, with or without a trailing ``Z``) -- returns ``None`` for
    anything else rather than raising, since a malformed timestamp must
    degrade to "cannot verify" (SOURCE_LINK_TIME_INVALID is only ever
    asserted from a genuinely-parsed, genuinely-later timestamp)."""
    if not isinstance(value, str) or not value.strip():
        return None
    text = value.strip()
    if text.endswith("Z"):
        text = text[:-1] + "+00:00"
    try:
        parsed = dt.datetime.fromisoformat(text)
    except ValueError:
        try:
            parsed = dt.datetime.strptime(text[:10], "%Y-%m-%d")
        except ValueError:
            return None
    if parsed.tzinfo is not None:
        parsed = parsed.astimezone(dt.UTC).replace(tzinfo=None)
    return parsed


EVIDENCE_CUTOFF_BASIS_MAX_SOURCE_FETCHED_AT = "MAX_SOURCE_FETCHED_AT"
EVIDENCE_CUTOFF_BASIS_ANALYSIS_DATE_FALLBACK = "ANALYSIS_DATE_FALLBACK_MIDNIGHT"
EVIDENCE_CUTOFF_BASIS_UNKNOWN = "UNKNOWN"


def resolve_evidence_cutoff_at(
    analysis_date: Any, sources: list[dict[str, Any]] | None
) -> tuple[str | None, str]:
    """T1 time-contract fix (2026-10-06, round7 follow-up): the real,
    tz-aware ``evidence_cutoff_at`` a linked source's ``published_at`` must
    not be later than -- distinct from, and preferred over, the bare
    ``analysis_date`` (a calendar date with no time-of-day, whose only
    previous use here parsed to that date's own MIDNIGHT and incorrectly
    rejected same-day sources whose real ``published_at`` was any time
    after 00:00:00 -- the exact false-positive round7 diagnosed in all 52
    ``SOURCE_LINK_TIME_INVALID`` records that round traced to one financial
    snapshot retrieved mid-afternoon on its own ``analysis_date``).

    Prefers ``max(source["retrieved_at"] for source in sources)`` (this
    run's own saved ``fetched_at`` moments -- ``retrieved_at`` is the field
    name this codebase already uses for when a source was actually fetched)
    over the bare ``analysis_date`` -- but ONLY when that maximum falls on
    the SAME calendar date as ``analysis_date`` itself. ``analysis_date`` is
    this run's own explicit, authoritative "as of" declaration; a real
    Fresh Run fetches its sources during that same day, so this is exactly
    the same-day midnight-truncation case round7 diagnosed. A registry
    whose sources were fetched on a DIFFERENT calendar day (earlier --
    e.g. a reused/shared registry predating this run's own, deliberately
    earlier ``analysis_date`` -- or later) is left on the conservative,
    unmodified bare-``analysis_date``-as-midnight fallback: ``retrieved_at``
    answers "when was this physically captured into the system", not "what
    date is THIS run's own analysis as of", and the two must never be
    conflated across a day boundary -- doing so previously, if attempted
    here, could silently ADMIT a source a run's own explicitly-declared,
    earlier cutoff was supposed to exclude, which this function never does.

    For an INDEPENDENT RE-EVALUATION of an already-completed run, a caller
    passes that SAME run's own already-saved ``sources`` and its own
    original ``analysis_date`` (never newly-fetched data, never "now",
    never a different date) -- so re-evaluating months later reproduces the
    exact same ``evidence_cutoff_at`` as evaluating it today.

    Returns ``(None, EVIDENCE_CUTOFF_BASIS_UNKNOWN)`` when neither a usable
    ``retrieved_at`` nor ``analysis_date`` is available -- a caller must
    treat that exactly as "time eligibility cannot be determined", never
    silently skip the check.
    """
    latest: dt.datetime | None = None
    for source in sources or ():
        if not isinstance(source, Mapping):
            continue
        parsed = _parse_iso_like(source.get("retrieved_at"))
        if parsed is not None and (latest is None or parsed > latest):
            latest = parsed
    analysis_date_dt = _parse_iso_like(analysis_date) if isinstance(analysis_date, str) else None
    if latest is not None and analysis_date_dt is not None and latest.date() == analysis_date_dt.date():
        return latest.isoformat(), EVIDENCE_CUTOFF_BASIS_MAX_SOURCE_FETCHED_AT
    if isinstance(analysis_date, str) and analysis_date.strip():
        return analysis_date, EVIDENCE_CUTOFF_BASIS_ANALYSIS_DATE_FALLBACK
    if latest is not None:
        # No analysis_date to cross-check against at all -- still safe to
        # use the real fetched-at maximum (never fabricated, never "now").
        return latest.isoformat(), EVIDENCE_CUTOFF_BASIS_MAX_SOURCE_FETCHED_AT
    return None, EVIDENCE_CUTOFF_BASIS_UNKNOWN


def validate_source_reference(
    candidate_id: Any,
    *,
    sources: list[dict[str, Any]] | None,
    evidence_cutoff: str | None = None,
) -> dict[str, Any]:
    """The one real backend validation gate every candidate source/fragment
    reference must pass -- however it was proposed (this module's own
    deterministic :func:`match_evidence_to_source_candidates`, or in a
    future live wiring, a value an extraction-stage LLM call proposes).
    Never trusts a candidate id without checking, in order:

      1. Does it resolve at all against THIS run's own registry (by
         ``fragment_id`` first, then bare ``source_id`` -- both id spaces
         are checked so either granularity a caller supplies is honored)?
         An id this run's registry does not recognize -- including a model
         hallucination, or an id copied from a DIFFERENT run's registry --
         is ``SOURCE_LINK_UNKNOWN_ID``, never resolved.
      2. Does the resolved source actually carry locatable content (an
         excerpt/content_hash)? A source registered by identity alone (no
         excerpt ever captured) is ``SOURCE_LINK_CONTENT_UNAVAILABLE`` --
         its identity is real, but there is nothing a claim could actually
         be shown to trace to.
      3. Is its ``published_at`` no later than ``evidence_cutoff`` (when
         given)? A source published after the analysis's own evidence
         cutoff is ``SOURCE_LINK_TIME_INVALID`` -- never silently accepted
         as if it were contemporaneous (look-ahead safety, the same
         principle ``tradingagents.dataflows.yfinance_news``'s own
         ``_in_news_window`` already enforces at fetch time -- this is the
         same check re-asserted at claim-validation time, since a claim's
         own cited id must independently satisfy it).

    Returns a small structured result; never raises. ``SOURCE_LINK_VALID``
    is the only status that means "safe to treat as evidence provenance" --
    every other status still names a real, structured reason, never a bare
    boolean.

    IMPORTANT: ``SOURCE_LINK_VALID`` says nothing about whether the source's
    content actually SUPPORTS the claim's assertion -- that is
    ``content_support_status``, a semantic question this function never
    answers (see this module's top-of-file docstring section).
    """
    if not candidate_id:
        return {"source_link_status": SOURCE_LINK_NOT_PROVIDED, "linked_source_id": None, "source": None}

    resolved = resolve_fragment_by_id(candidate_id, sources or []) or resolve_source_by_id(
        candidate_id, sources or []
    )
    if resolved is None:
        return {"source_link_status": SOURCE_LINK_UNKNOWN_ID, "linked_source_id": None, "source": None}

    linked_source_id = resolved.get("source_id")
    if not resolved.get("excerpt") or not resolved.get("content_hash"):
        return {
            "source_link_status": SOURCE_LINK_CONTENT_UNAVAILABLE,
            "linked_source_id": linked_source_id,
            "source": resolved,
        }

    if evidence_cutoff is not None:
        cutoff_dt = _parse_iso_like(evidence_cutoff)
        published_dt = _parse_iso_like(resolved.get("published_at"))
        if cutoff_dt is not None and published_dt is not None and published_dt > cutoff_dt:
            return {
                "source_link_status": SOURCE_LINK_TIME_INVALID,
                "linked_source_id": linked_source_id,
                "source": resolved,
            }

    return {"source_link_status": SOURCE_LINK_VALID, "linked_source_id": linked_source_id, "source": resolved}


def public_source_fields(source: dict[str, Any]) -> dict[str, Any]:
    """Whitelist projection for API/export responses -- mirrors this
    codebase's established pattern (see agent_output_reader.py's own
    PUBLIC_STRUCTURED_OUTPUT_FIELDS) of only ever copying known-safe,
    known-named fields, never a raw passthrough of whatever the record
    happens to contain."""
    return {field: source.get(field) for field in _SOURCE_RECORD_FIELDS if field in source}


__all__ = [
    "iter_source_numeric_leaves",
    "match_evidence_to_source_candidates_normalized",
    "extract_all_source_markers_from_text",
    "SOURCE_REGISTRY_SCHEMA_VERSION",
    "STATUS_TRACEABLE",
    "STATUS_PARTIAL",
    "STATUS_UNAVAILABLE",
    "VALID_SOURCE_STATUSES",
    "SOURCE_LINK_VALID",
    "SOURCE_LINK_UNKNOWN_ID",
    "SOURCE_LINK_CONTENT_UNAVAILABLE",
    "SOURCE_LINK_TIME_INVALID",
    "SOURCE_AVAILABILITY_VERSION",
    "AVAILABILITY_BASIS_REGISTRY_WRITE_UPPER_BOUND",
    "AVAILABILITY_ANNOTATION_REGISTRY_WRITE",
    "AVAILABILITY_ANNOTATION_DERIVED_FROM_SAVED_REGISTRY",
    "ELIGIBILITY_REASON_REVIEW_SOURCE_NOT_LINKED",
    "ELIGIBILITY_REASON_AVAILABILITY_AFTER_CUTOFF",
    "evaluate_source_availability",
    "annotate_sources_availability",
    "SOURCE_LINK_NOT_PROVIDED",
    "VALID_SOURCE_LINK_STATUSES",
    "SUPPORT_SUPPORTS",
    "SUPPORT_OPPOSES",
    "SUPPORT_BACKGROUND",
    "SUPPORT_CITATION_ONLY",
    "SUPPORT_CONDITIONAL",
    "SUPPORT_PENDING_REVIEW",
    "SUPPORT_NOT_APPLICABLE",
    "VALID_CONTENT_SUPPORT_STATUSES",
    "REVIEW_METHOD_UNREVIEWED",
    "REVIEW_METHOD_UNVERIFIED_OFFLINE_CONTENT_MATCH",
    "REVIEW_METHOD_AGENT_CITED_UNVERIFIED_SUPPORT",
    "REVIEW_METHOD_ORIGINAL_AGENT_CITED_UNVERIFIED_SUPPORT",
    "REVIEW_METHOD_HUMAN_REVIEWED",
    "REVIEW_METHOD_AUTOMATED_DATA_FACT_VERIFIED",
    "REVIEW_METHOD_AUTOMATED_DERIVED_CALC_VERIFIED",
    "REVIEW_METHOD_LLM_CONTENT_SUPPORT_VERIFIED",
    "AUTOMATICALLY_ELIGIBLE_REVIEW_METHODS",
    "VALID_REVIEW_METHODS",
    "CONTENT_SUPPORT_REVIEW_SCHEMA_VERSION",
    "verify_data_fact_or_derived_calculation",
    "apply_automated_content_support_verification",
    "resolve_evidence_cutoff_at",
    "EVIDENCE_CUTOFF_BASIS_MAX_SOURCE_FETCHED_AT",
    "EVIDENCE_CUTOFF_BASIS_ANALYSIS_DATE_FALLBACK",
    "EVIDENCE_CUTOFF_BASIS_UNKNOWN",
    "make_source_id",
    "fragment_id_for",
    "classify_metadata_status",
    "build_source_record",
    "build_source_registry",
    "resolve_source_by_id",
    "resolve_fragment_by_id",
    "find_matching_source",
    "match_evidence_to_source_candidates",
    "extract_source_marker_from_text",
    "resolve_external_source_for_claim",
    "validate_source_reference",
    "build_content_support_review",
    "apply_content_support_review",
    "public_source_fields",
    "ELIGIBILITY_REASON_ELIGIBLE",
    "ELIGIBILITY_REASON_SOURCE_LINK_NOT_VALID",
    "ELIGIBILITY_REASON_NOT_REVIEWED",
    "ELIGIBILITY_REASON_SUPPORT_STATUS_NOT_RESOLVED",
    "ELIGIBILITY_REASON_REVIEW_CLAIM_MISMATCH",
    "ELIGIBILITY_REASON_CONTENT_VERSION_CHANGED_SINCE_REVIEW",
    "ELIGIBILITY_REASON_SOURCE_NOT_RESOLVABLE",
    "ELIGIBILITY_REASON_SOURCE_OPPOSES_CLAIM",
    "ELIGIBILITY_REASON_DISCLOSURE_TIME_UNKNOWN",
    "compute_verified_support_eligibility",
    "DIAGNOSTIC_ELIGIBLE",
    "DIAGNOSTIC_SOURCE_TYPE_NOT_YET_COVERED",
    "DIAGNOSTIC_REFERENCE_MISSING_OR_INVALID",
    "DIAGNOSTIC_CONTENT_SUPPORT_PENDING_REVIEW",
    "DIAGNOSTIC_SOURCE_OPPOSES_CLAIM",
    "DIAGNOSTIC_DISCLOSURE_TIME_UNKNOWN",
    "LINKED_AGENT_COVERAGE",
    "classify_verified_support_diagnostic",
]
