"""DB-first reader for public Week 1-2 structured agent outputs.

New runs are served from ``agent_outputs`` database rows. Runs created before
migration 0004 may fall back to exactly one artifact,
``structured_agent_outputs.json``. Neither path opens, stats, or otherwise
references ``raw_agent_outputs.json``. Raw transcript authorization,
redaction, and audit remain deferred and out of scope for this endpoint.

W4.3 security patch: every record is additionally projected through a
public-field whitelist (``PUBLIC_STRUCTURED_OUTPUT_FIELDS``) before it ever
leaves this module. Structural validity of a record is still delegated to
the structured-output adapter's own ``validate_structured_output`` (reused,
not re-implemented) -- the whitelist projection only decides *which of the
already-valid fields* are safe to expose publicly, so a structured record
that was tampered with (or a future adapter change that starts embedding
``raw_output``/``prompt``/``final_state``/etc. inside a "structured" record)
can never smuggle that content through this endpoint.

Product Findings Closure Sprint: every candidate record (DB row or legacy
artifact record) is additionally required to pass
``claim_quality.is_claim_eligible(record, "product_findings")`` before it is
kept -- reusing the same shared quality gate every other consumer (Mapper,
Structure Extractor, Activation, Conflict, persistence) already calls,
never a second, locally-invented classification. A record with no stamped
``claim_quality`` (any DB row, since ``claim_quality`` is not a persisted
column, or a legacy pre-Sprint artifact) is classified ephemerally, at read
time, from its own already-persisted fields (claim/evidence/direction/
entities/factors/assertion_status) -- this never mutates the record, the
database, or the source artifact. The eligibility check runs on the raw
record, before whitelist projection (``claim_quality`` itself is not, and
never becomes, a public field); ``NON_SUBSTANTIVE`` records are always
dropped and ``CONTEXT_ONLY`` records are dropped by this consumer's default
(hidden), so only ``ANALYTICAL`` claims -- the same ones every other
downstream consumer treats as real evidence -- reach the response. This
runs for every candidate record independent of pagination (this endpoint
returns one run's full eligible set in a single response, so ``count``
always equals the number of items actually present in
``structured_agent_outputs``, i.e. the number of *displayable* findings,
never the raw pre-filter row count).
"""

from __future__ import annotations

import json
import logging
import math
from collections.abc import Mapping
from typing import Any

from comqutor_alpha.source_provenance import (
    SOURCE_LINK_VALID,
    STATUS_UNAVAILABLE,
    classify_verified_support_diagnostic,
    public_source_fields,
    resolve_external_source_for_claim,
    resolve_fragment_by_id,
    resolve_source_by_id,
)
from comqutor_alpha.storage.db.repository import (
    GraphPersistenceError,
    build_repository_from_env,
)
from comqutor_alpha.storage.file_store import (
    load_json_record_if_exists,
    run_dir_for,
    validate_run_id_for_path,
)
from comqutor_alpha.structure_engine.claim_quality import (
    CONSUMER_PRODUCT_FINDINGS,
    is_claim_eligible,
)
from comqutor_alpha.structure_engine.structure_schema import VALID_DIRECTIONS
from comqutor_alpha.structure_engine.structured_output_adapter import (
    MAX_CLAIM_CHARS,
    SCHEMA_VERSION,
    validate_structured_output,
)

logger = logging.getLogger(__name__)

STRUCTURED_ARTIFACT_FILENAME = "structured_agent_outputs.json"

# Public-field whitelist (W4.3 security patch): only these keys may ever
# appear in a record returned by GET /api/research/{run_id}/agent-outputs.
# Anything else present on a record -- raw_output, full_transcript, prompt,
# system_prompt, provider_response, model_response, final_state,
# debate_history, investment_plan, final_trade_decision, an adapter raw
# preview, or any other field not listed here -- is silently dropped, never
# copied into the response.
#
# external_source/external_source_status (John MVP Final Gap Closure --
# Structured External Source Traceability) are the one deliberate exception
# to "copied from the raw record via _project_public_record": they are
# never present on the raw record at all -- _annotate_external_sources
# computes and attaches them afterward, from a deterministic, read-time
# join against this run's own source_registry.json. Listed here so the
# whitelist remains the single source of truth for "every key this endpoint
# may return", which is what this module's own tests check against.
PUBLIC_STRUCTURED_OUTPUT_FIELDS = frozenset(
    {
        "claim_id",
        "agent_output_id",
        "source_agent_output_id",
        "run_id",
        "ticker",
        "agent",
        "timestamp",
        "claim",
        "evidence",
        "entities",
        "factors",
        "direction",
        "confidence",
        "source_type",
        "external_source",
        "external_source_status",
        "output_type",
        "source_refs",
        "claim_index",
        "source_section",
        "assertion_status",
        "semantic_polarity",
        "extraction_method",
        # T1 source-linking chain (COMQUTOR Alpha next-round task,
        # 2026-09-26): unlike external_source/external_source_status (a
        # read-time title-match join computed below), these four are
        # computed and PERSISTED at structured-extraction time
        # (comqutor_alpha.structure_engine.structured_output_adapter's own
        # _annotate_source_link) via ID-based validation against this run's
        # source_registry.json -- copied through as-is like any other
        # adapter-produced field. source_link_status/content_support_status
        # are two deliberately separate axes (see
        # comqutor_alpha.source_provenance's own module docstring):
        # SOURCE_LINK_VALID never implies SUPPORT_SUPPORTS.
        "source_link_status",
        "linked_source_id",
        # source_link_method (2026-09-28): distinguishes an explicit Agent
        # citation (AGENT_CITED, validated against exactly what this
        # extraction step's own request offered) from the auxiliary
        # content-based matcher (CONTENT_MATCH_CANDIDATE) -- never let a
        # UI/reviewer confuse an explicit reference with a same-text
        # coincidence.
        "source_link_method",
        "content_support_status",
        "content_support_method",
        "content_support_review",
        # linked_source, like external_source above, is never present on
        # the raw record -- _annotate_validated_source_link resolves it
        # afterward from linked_source_id against this run's own registry.
        "linked_source",
        # verified_support_diagnostic (2026-09-29 gate-bypass closing fix):
        # like linked_source, never present on the raw record --
        # _annotate_verified_support_diagnostic computes it afterward via
        # comqutor_alpha.source_provenance.classify_verified_support_
        # diagnostic, distinguishing "this claim's source type has no real
        # linking mechanism yet" from "linking was attempted and failed"
        # from "linked and simply awaiting review" -- never inferred from a
        # bare source_link_status alone.
        "verified_support_diagnostic",
    }
)

# Fields the structured-output adapter itself guarantees are present and
# structurally valid (via validate_structured_output) once a record passes
# that check. Copied through as-is -- the adapter validator already confirms
# these are non-empty text (claim/evidence/entities/factors/direction get
# their own, stricter, whitelist-specific checks below on top of that).
_ADAPTER_GUARANTEED_TEXT_FIELDS = (
    "claim_id",
    "source_agent_output_id",
    "run_id",
    "ticker",
    "agent",
)

# Optional whitelist fields with no adapter-level guarantee: included in the
# response only when present on the source record, and only after passing a
# type check here. Anything else on the record (known or unknown) is never
# copied.
_OPTIONAL_SCALAR_TEXT_FIELDS = (
    "agent_output_id",
    "timestamp",
    "source_type",
    "output_type",
    "source_section",
    "assertion_status",
    "semantic_polarity",
    "extraction_method",
    "source_link_status",
    "linked_source_id",
    "source_link_method",
    "content_support_status",
    "content_support_method",
)

_ERROR_MESSAGES = {
    "INVALID_RUN_ID": "Invalid run_id.",
    "RUN_NOT_FOUND": "Run not found.",
    "AGENT_OUTPUTS_NOT_READY": "Structured agent outputs have not been generated for this run yet.",
    "AGENT_OUTPUTS_CORRUPTED": "Persisted structured agent outputs are missing required fields.",
    "AGENT_OUTPUTS_UNAVAILABLE": "Agent output storage is temporarily unavailable.",
}

_CORRUPTED = "AGENT_OUTPUTS_CORRUPTED"


class AgentOutputsReadError(Exception):
    """Safe read-path error: carries a stable reason code only. Never
    carries a raw exception message, a traceback, a local path, or the
    content of a rejected/dropped field."""

    def __init__(self, reason_code: str) -> None:
        self.reason_code = reason_code
        super().__init__(reason_code)


def _error_response(run_id: str | None, error_code: str) -> dict[str, Any]:
    return {
        "run_id": run_id,
        "ticker": None,
        "status": "failed",
        "error_code": error_code,
        "message": _ERROR_MESSAGES[error_code],
    }


def _require(condition: bool) -> None:
    if not condition:
        raise AgentOutputsReadError(_CORRUPTED)


def _validate_flat_str_list(value: Any) -> list[str]:
    """entities/factors/source_refs: flat list[str] only -- no nested
    dict/list smuggled in through a field whose public shape is "just a
    list of strings"."""
    _require(isinstance(value, list))
    result: list[str] = []
    for item in value:
        _require(isinstance(item, str))
        result.append(item)
    return result


def _validate_bounded_nonempty_text(value: Any) -> str:
    """claim/evidence: non-empty string, within the adapter's own public
    max length. An over-length value is never silently truncated -- it is
    treated as corrupted, since a truncate-and-continue policy would let an
    oversized (potentially smuggled) payload partially through."""
    _require(isinstance(value, str) and value.strip() != "")
    _require(len(value) <= MAX_CLAIM_CHARS)
    return value


def _validate_confidence(value: Any) -> float:
    _require(not isinstance(value, bool))
    _require(isinstance(value, (int, float)))
    number = float(value)
    _require(math.isfinite(number))
    _require(0.0 <= number <= 1.0)
    return number


_CONTENT_SUPPORT_REVIEW_FIELDS = frozenset(
    {
        "schema_version",
        "status",
        "method",
        "reviewer",
        "rationale",
        "reviewed_at",
        "claim_id",
        "linked_source_id",
        "content_hash",
    }
)

# Historical records persisted before the 2026-09-28 claim/source/content-
# version binding was added to build_content_support_review/
# apply_content_support_review (see source_provenance.py) lack these three
# keys entirely. They must still read back compatibly -- never rejected as
# corrupted, and never backfilled as if a binding had been verified.
_CONTENT_SUPPORT_REVIEW_OPTIONAL_FIELDS = frozenset({"claim_id", "linked_source_id", "content_hash"})


def _validate_content_support_review(value: Any) -> dict[str, Any] | None:
    """content_support_review (T1 follow-up, 2026-09-28): a small, fixed-
    shape audit record (comqutor_alpha.source_provenance.
    build_content_support_review/apply_content_support_review) -- validated
    and whitelist-projected exactly like every other field here, never a
    raw passthrough of whatever the persisted record happens to contain.

    ``claim_id``/``linked_source_id``/``content_hash`` bind a review to the
    exact claim, source, and content version it was judged against (added
    2026-09-28). Older persisted records predate this binding and legally
    omit all three -- they are read back as ``None``, never defaulted to a
    verified binding."""
    if value is None:
        return None
    _require(isinstance(value, Mapping))
    _require(set(value) <= _CONTENT_SUPPORT_REVIEW_FIELDS)
    _require(_CONTENT_SUPPORT_REVIEW_FIELDS - _CONTENT_SUPPORT_REVIEW_OPTIONAL_FIELDS <= set(value))
    for key in ("schema_version", "status", "method"):
        _require(isinstance(value.get(key), str) and value[key].strip() != "")
    for key in ("reviewer", "rationale", "reviewed_at", "claim_id", "linked_source_id", "content_hash"):
        _require(value.get(key) is None or isinstance(value.get(key), str))
    projected = {key: value.get(key) for key in _CONTENT_SUPPORT_REVIEW_FIELDS if key in value or key not in _CONTENT_SUPPORT_REVIEW_OPTIONAL_FIELDS}
    return projected


def _validate_claim_index(value: Any) -> int:
    _require(not isinstance(value, bool))
    _require(isinstance(value, int))
    _require(value >= 0)
    return value


def _validate_optional_text(value: Any) -> str | None:
    if value is None:
        return None
    _require(isinstance(value, str))
    return value


def _require_nonempty_text(value: Any) -> str:
    """Strict, fail-closed text validator for the public identity fields
    (claim_id/source_agent_output_id/run_id/ticker/agent): must be a raw
    Python ``str`` -- dict/list/tuple/number/bool/None are all rejected
    outright, never coerced. ``validate_structured_output()`` normalizes
    some of these values internally for its own presence check, which does
    NOT guarantee the original value was actually a string -- this is the
    whitelist projection layer's own, independent type guarantee, not a
    substitute for (or a duplicate of) that adapter check. Returns the
    original string unchanged -- never ``str(value)`` forced, which would
    silently accept a dict/list by stringifying it."""
    _require(isinstance(value, str))
    _require(value.strip() != "")
    return value


def _require_valid_direction(value: Any) -> str:
    """direction: must be a raw ``str`` that is itself already a member of
    ``VALID_DIRECTIONS`` -- never accepted via ``normalize_direction()``'s
    lenient coercion (which a dict/list could indirectly slip through), and
    never auto-corrected to a valid value."""
    _require(isinstance(value, str))
    _require(value in VALID_DIRECTIONS)
    return value


def _project_public_record(record: dict[str, Any], *, run_id: str, ticker: str) -> dict[str, Any]:
    """Validate one already-dict record, then project it onto exactly the
    public field whitelist. Never copies a field by iterating over the
    record's own keys -- only ever reads out the specific whitelisted keys
    it knows about, so an unknown field (including a nested object smuggled
    under an unexpected name) can never reach the output by construction.
    """
    # 1. Structural validity is delegated to the structured-output adapter's
    # own validator -- reused, not duplicated into a second, possibly
    # out-of-sync required-field ruleset. This alone does not guarantee
    # every field's *type* though (see _require_nonempty_text/
    # _require_valid_direction below), so it is a first-pass gate, not the
    # whitelist projection's own type boundary.
    _require(validate_structured_output(record))

    # 2. Record identity must agree with the top-level payload it lives in.
    _require(record.get("run_id") == run_id)
    _require(record.get("ticker") == ticker)

    projected: dict[str, Any] = {}
    for field in _ADAPTER_GUARANTEED_TEXT_FIELDS:
        projected[field] = _require_nonempty_text(record[field])

    projected["claim"] = _validate_bounded_nonempty_text(record["claim"])
    projected["evidence"] = _validate_bounded_nonempty_text(record["evidence"])
    projected["entities"] = _validate_flat_str_list(record["entities"])
    projected["factors"] = _validate_flat_str_list(record["factors"])
    projected["direction"] = _require_valid_direction(record["direction"])
    projected["confidence"] = _validate_confidence(record["confidence"])

    for field in _OPTIONAL_SCALAR_TEXT_FIELDS:
        if field in record:
            projected[field] = _validate_optional_text(record[field])
    if "source_refs" in record:
        projected["source_refs"] = _validate_flat_str_list(record["source_refs"])
    if "claim_index" in record:
        projected["claim_index"] = _validate_claim_index(record["claim_index"])
    if "content_support_review" in record:
        projected["content_support_review"] = _validate_content_support_review(record["content_support_review"])

    return projected


def _read_structured_payload(run_id: str, output_root: Any) -> dict[str, Any]:
    """Load, structurally validate, and publicly project
    ``structured_agent_outputs.json``.

    Never constructs a path to, checks for, or opens
    ``raw_agent_outputs.json`` -- structured-only by construction, not by a
    field filter applied after reading both files.
    """
    run_dir = run_dir_for(run_id, output_root)
    path = run_dir / STRUCTURED_ARTIFACT_FILENAME

    if not path.exists():
        raise AgentOutputsReadError("AGENT_OUTPUTS_NOT_READY")

    try:
        with path.open(encoding="utf-8") as handle:
            payload = json.load(handle)
    except (json.JSONDecodeError, UnicodeDecodeError) as exc:
        raise AgentOutputsReadError(_CORRUPTED) from exc
    except OSError as exc:
        raise AgentOutputsReadError("AGENT_OUTPUTS_UNAVAILABLE") from exc

    if not isinstance(payload, dict):
        raise AgentOutputsReadError(_CORRUPTED)
    if payload.get("run_id") != run_id:
        raise AgentOutputsReadError(_CORRUPTED)
    ticker = payload.get("ticker")
    if not isinstance(ticker, str) or not ticker.strip():
        raise AgentOutputsReadError(_CORRUPTED)
    schema_version = payload.get("schema_version")
    if not isinstance(schema_version, str) or not schema_version.strip():
        raise AgentOutputsReadError(_CORRUPTED)
    raw_records = payload.get("records")
    if not isinstance(raw_records, list) or any(not isinstance(item, dict) for item in raw_records):
        raise AgentOutputsReadError(_CORRUPTED)

    # Order preserved: appended in the same sequence records were read.
    # Every record is still structurally validated and whitelist-projected
    # (same as before this Sprint) -- a corrupt record anywhere in the
    # artifact still fails the whole response closed. The product_findings
    # eligibility check runs on the *raw* record (the only place
    # ``claim_quality`` -- stamped or ephemerally recomputed -- is still
    # visible) and only decides whether the already-projected result is
    # kept, so it can never weaken the corruption check above or the
    # whitelist projection below.
    public_records = []
    for record in raw_records:
        projected = _project_public_record(record, run_id=run_id, ticker=ticker)
        if is_claim_eligible(record, CONSUMER_PRODUCT_FINDINGS):
            public_records.append(projected)

    return {"ticker": ticker, "schema_version": schema_version, "records": public_records}


def _load_source_registry(run_id: str, output_root: Any) -> list[dict[str, Any]]:
    """Best-effort load of this run's ``source_registry.json`` -- absent
    entirely for a historical run predating this feature, or a run with no
    genuine sources captured. Never raises: a missing/corrupted registry
    degrades to "no sources available" rather than failing the whole
    agent-outputs response."""
    try:
        registry = load_json_record_if_exists(run_id, "source_registry.json", output_root=output_root)
    except Exception:
        return []
    if not isinstance(registry, dict):
        return []
    sources = registry.get("sources")
    return sources if isinstance(sources, list) else []


def _annotate_external_sources(
    records: list[dict[str, Any]], sources: list[dict[str, Any]]
) -> list[dict[str, Any]]:
    """John MVP Final Gap Closure -- Structured External Source
    Traceability: purely additive read-time join. Never mutates, rewrites,
    or reorders anything already in ``records`` -- only ever appends two new
    keys (``external_source``, ``external_source_status``) computed by a
    deterministic substring match (see comqutor_alpha.source_provenance),
    never by an LLM. Records already in ``records`` keep every one of their
    existing fields unchanged."""
    if not sources:
        for record in records:
            record["external_source"] = None
            record["external_source_status"] = STATUS_UNAVAILABLE
        return records
    for record in records:
        match, status = resolve_external_source_for_claim(
            claim=record.get("claim"), evidence=record.get("evidence"), sources=sources
        )
        record["external_source"] = public_source_fields(match) if match else None
        record["external_source_status"] = status
    return records


def _annotate_validated_source_link(
    records: list[dict[str, Any]], sources: list[dict[str, Any]]
) -> list[dict[str, Any]]:
    """T1 source-linking chain (COMQUTOR Alpha next-round task,
    2026-09-26): re-resolves the record's own already-persisted,
    already-validated ``linked_source_id`` (from
    ``comqutor_alpha.structure_engine.structured_output_adapter``'s
    extraction-time ``_annotate_source_link`` -- ID-based, never a
    read-time title match) against THIS run's own registry, and attaches
    the full public source object as ``linked_source`` -- so a UI can show
    the real excerpt/title/url a claim's ``source_link_status ==
    SOURCE_LINK_VALID`` actually points to, distinct from the legacy
    ``external_source`` title-match join above. Never mutates
    ``source_link_status``/``linked_source_id`` themselves -- those already
    came from ``_project_public_record``'s whitelist copy-through; this
    only adds the resolved object alongside them. A record with no
    validated link (or a historical record predating this field) gets
    ``linked_source: None``, never a fabricated value.
    """
    for record in records:
        linked_id = record.get("linked_source_id")
        if record.get("source_link_status") != SOURCE_LINK_VALID or not linked_id:
            record["linked_source"] = None
            continue
        resolved = resolve_fragment_by_id(linked_id, sources) or resolve_source_by_id(linked_id, sources)
        record["linked_source"] = public_source_fields(resolved) if resolved else None
    return records


def _load_cited_source_lists(
    run_id: str, output_root: Any, records: list[dict[str, Any]]
) -> dict[str, dict[str, Any]]:
    """Round 19: supplies the plural citation list (``linked_source_ids``) of
    the claims whose review binds a source OTHER than the primary
    ``linked_source_id``.

    ``source_provenance.compute_verified_support_eligibility`` accepts such a
    review only when its source is one of the claim's cited sources. The
    structured-output adapter produces that list, but the ``agent_outputs``
    table has no column for it and the public whitelist above omits it, so a
    DB-served record reached the read-time diagnostic with the primary link
    alone and was wrongly reported ``REVIEW_SOURCE_NOT_LINKED_TO_CLAIM`` while
    the stored result (computed from the full record) is ``ELIGIBLE``.

    This reads the run's own saved ``structured_agent_outputs.json`` -- the
    file the rows were persisted from -- and only when at least one record
    needs it. Best-effort and read-only: it never raises, never changes a
    public field or any stored result, ignores a claim whose primary link
    disagrees with the artifact's, and a run without the artifact gets
    ``{}`` (exactly the previous behaviour)."""

    def binds_non_primary_source(record: dict[str, Any]) -> bool:
        review = record.get("content_support_review")
        bound = review.get("linked_source_id") if isinstance(review, dict) else None
        return bool(bound) and bound != record.get("linked_source_id")

    if not any(binds_non_primary_source(record) for record in records):
        return {}
    try:
        payload = load_json_record_if_exists(run_id, STRUCTURED_ARTIFACT_FILENAME, output_root=output_root)
    except Exception:
        return {}
    saved = payload.get("records") if isinstance(payload, dict) else None
    if not isinstance(saved, list):
        return {}
    cited: dict[str, dict[str, Any]] = {}
    for item in saved:
        if not isinstance(item, dict):
            continue
        claim_id, ids = item.get("claim_id"), item.get("linked_source_ids")
        if isinstance(claim_id, str) and isinstance(ids, list) and ids and all(isinstance(i, str) and i for i in ids):
            cited[claim_id] = {"linked_source_id": item.get("linked_source_id"), "linked_source_ids": list(ids)}
    return cited


def _annotate_verified_support_diagnostic(
    records: list[dict[str, Any]],
    sources: list[dict[str, Any]],
    cited_source_lists: dict[str, dict[str, Any]] | None = None,
) -> list[dict[str, Any]]:
    """Gate-bypass closing fix (2026-09-29): attaches ``verified_support_
    diagnostic`` (``{"category": ..., "reason_code": ...}``), explaining
    WHY this claim does or does not count as verified support at a level
    suitable for direct display -- distinguishing a source-type coverage
    gap from a per-claim reference problem from a normal pending-review
    state. Never mutates source_link_status/content_support_status/
    content_support_review themselves; purely additive, like linked_source
    above.

    ``cited_source_lists`` (round 19, see ``_load_cited_source_lists``) feeds
    the saved ``linked_source_ids`` to the DIAGNOSTIC ONLY: the public record
    is not given the field, and it is applied only when the artifact's
    primary link equals this record's."""
    for record in records:
        subject = record
        cited = (cited_source_lists or {}).get(record.get("claim_id"))
        if cited and not record.get("linked_source_ids") and cited.get("linked_source_id") == record.get("linked_source_id"):
            subject = {**record, "linked_source_ids": cited["linked_source_ids"]}
        record["verified_support_diagnostic"] = classify_verified_support_diagnostic(subject, sources)
    return records


def get_agent_outputs_response(
    run_id: Any,
    output_root: str | None = "outputs/runs",
    *,
    graph_repository: Any = None,
) -> dict[str, Any]:
    """Build the full ``GET /api/research/{run_id}/agent-outputs`` response.

    Structured-only, public-field-whitelisted by design (see module
    docstring). Never invokes an LLM, TradingAgents, or a network call;
    never performs a database write, table creation, or migration; never
    returns a local filesystem path.

    ``output_root=None`` is a meaningful, distinct value from the literal
    string default -- it must reach ``run_dir_for``/``resolve_output_root``
    unchanged so ``COMQUTOR_OUTPUT_DIR`` is honored (see
    ``routes_research.py``'s route handler, which forwards
    ``app.state.output_root`` -- possibly ``None`` -- as-is rather than
    substituting a literal path).
    """
    try:
        safe_run_id = validate_run_id_for_path(run_id)
    except ValueError:
        return _error_response(str(run_id) if run_id is not None else None, "INVALID_RUN_ID")

    try:
        repository = graph_repository or build_repository_from_env(output_root)
        database_records = repository.list_agent_outputs(safe_run_id)
    except GraphPersistenceError as exc:
        if exc.reason_code == "DB_DATA_CORRUPTED":
            logger.warning(
                "agent outputs retrieval failed "
                "(run_id=%s, stage=%s, reason_code=%s)",
                safe_run_id,
                "agent_outputs_read",
                exc.reason_code,
            )
            return _error_response(safe_run_id, "AGENT_OUTPUTS_CORRUPTED")
        logger.warning(
            "agent outputs database read failed "
            "(run_id=%s, stage=%s, reason_code=%s)",
            safe_run_id,
            "agent_outputs_read",
            exc.reason_code,
        )
        return _error_response(safe_run_id, "AGENT_OUTPUTS_UNAVAILABLE")
    except Exception as exc:
        logger.warning(
            "agent outputs database read failed "
            "(run_id=%s, stage=%s, reason_code=%s, exc_type=%s)",
            safe_run_id,
            "agent_outputs_read",
            "AGENT_OUTPUTS_UNAVAILABLE",
            type(exc).__name__,
        )
        return _error_response(safe_run_id, "AGENT_OUTPUTS_UNAVAILABLE")

    if database_records:
        ticker = database_records[0]["ticker"]
        try:
            # Same pattern as the legacy-artifact path below: every DB row
            # is still structurally validated and whitelist-projected
            # unconditionally (no regression to the corruption check), then
            # kept only if the shared quality gate admits it for
            # product_findings. ``claim_quality`` is never a persisted DB
            # column, so this always runs the ephemeral (read-time-only,
            # never written back) classification path for every row --
            # including rows inserted before this Sprint existed.
            public_records = []
            for record in database_records:
                projected = _project_public_record(record, run_id=safe_run_id, ticker=ticker)
                if is_claim_eligible(record, CONSUMER_PRODUCT_FINDINGS):
                    public_records.append(projected)
        except AgentOutputsReadError:
            return _error_response(safe_run_id, "AGENT_OUTPUTS_CORRUPTED")
        sources = _load_source_registry(safe_run_id, output_root)
        public_records = _annotate_external_sources(public_records, sources)
        public_records = _annotate_validated_source_link(public_records, sources)
        public_records = _annotate_verified_support_diagnostic(
            public_records, sources, _load_cited_source_lists(safe_run_id, output_root, public_records)
        )
        return {
            "run_id": safe_run_id,
            "ticker": ticker,
            "status": "ok",
            "schema_version": SCHEMA_VERSION,
            "structured_agent_outputs": public_records,
            "count": len(public_records),
        }

    # Compatibility-only path for runs created before migration 0004. New
    # runs persist rows before Alpha mapping and are served above.
    run_dir = run_dir_for(safe_run_id, output_root)
    if not run_dir.exists():
        return _error_response(safe_run_id, "RUN_NOT_FOUND")

    try:
        parsed = _read_structured_payload(safe_run_id, output_root)
    except AgentOutputsReadError as exc:
        return _error_response(safe_run_id, exc.reason_code)
    except Exception as exc:
        logger.warning(
            "agent outputs read failed unexpectedly (run_id=%s, exc_type=%s)",
            safe_run_id,
            type(exc).__name__,
        )
        return _error_response(safe_run_id, "AGENT_OUTPUTS_UNAVAILABLE")

    structured_records = parsed["records"]
    sources = _load_source_registry(safe_run_id, output_root)
    structured_records = _annotate_external_sources(structured_records, sources)
    structured_records = _annotate_validated_source_link(structured_records, sources)
    structured_records = _annotate_verified_support_diagnostic(
        structured_records, sources, _load_cited_source_lists(safe_run_id, output_root, structured_records)
    )
    return {
        "run_id": safe_run_id,
        "ticker": parsed["ticker"],
        "status": "ok",
        "schema_version": parsed["schema_version"],
        "structured_agent_outputs": structured_records,
        "count": len(structured_records),
    }


__all__ = [
    "get_agent_outputs_response",
    "AgentOutputsReadError",
    "STRUCTURED_ARTIFACT_FILENAME",
    "PUBLIC_STRUCTURED_OUTPUT_FIELDS",
]
