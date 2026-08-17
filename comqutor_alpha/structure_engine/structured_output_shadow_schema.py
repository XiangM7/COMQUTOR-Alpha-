"""Offline-only schema and deterministic validator for Phase 1A claim proposals.

This module has no production importers and performs no I/O.  A semantic
invoker may propose records, but caller-owned identity, source fidelity, and
admission remain deterministic here.
"""

from __future__ import annotations

import hashlib
import json
import math
import re
from collections.abc import Mapping, Sequence
from dataclasses import dataclass, field
from typing import Any

STRUCTURED_OUTPUT_SHADOW_SCHEMA_VERSION = "comqutor.structured_claim_shadow.v1"
SHADOW_CLAIM_ID_VERSION = "comqutor.shadow_claim_id.v1"
SHADOW_INPUT_SCHEMA_VERSION = "comqutor.structured_claim_shadow_input.v1"

VALID_DIRECTIONS = frozenset({"positive", "negative", "neutral", "unknown"})
VALID_SOURCE_TYPES = frozenset(
    {"news", "filing", "price", "analyst", "social", "technical", "unknown"}
)
VALID_EXTRACTION_STATUSES = frozenset({"proposed", "abstained"})

SHADOW_SCHEMA_INVALID = "SHADOW_SCHEMA_INVALID"
SHADOW_IDENTITY_MISMATCH = "SHADOW_IDENTITY_MISMATCH"
SHADOW_SOURCE_HASH_MISMATCH = "SHADOW_SOURCE_HASH_MISMATCH"
SHADOW_SOURCE_SPAN_INVALID = "SHADOW_SOURCE_SPAN_INVALID"
SHADOW_EVIDENCE_NOT_PROVENANCED = "SHADOW_EVIDENCE_NOT_PROVENANCED"
SHADOW_FACTOR_VOCABULARY_INVALID = "SHADOW_FACTOR_VOCABULARY_INVALID"
SHADOW_DIRECTION_INVALID = "SHADOW_DIRECTION_INVALID"
SHADOW_DUPLICATE_CLAIM = "SHADOW_DUPLICATE_CLAIM"
SHADOW_UNAPPROVED_FIELD = "SHADOW_UNAPPROVED_FIELD"
SHADOW_OUTPUT_TOO_LARGE = "SHADOW_OUTPUT_TOO_LARGE"
SHADOW_PROMPT_VERSION_MISMATCH = "SHADOW_PROMPT_VERSION_MISMATCH"
SHADOW_EMPTY_OR_NON_SUBSTANTIVE = "SHADOW_EMPTY_OR_NON_SUBSTANTIVE"
SHADOW_INVOKER_ERROR = "SHADOW_INVOKER_ERROR"
SHADOW_JSON_INVALID = "SHADOW_JSON_INVALID"
SHADOW_SOURCE_REF_INVALID = "SHADOW_SOURCE_REF_INVALID"
SHADOW_ENTITY_NOT_GROUNDED = "SHADOW_ENTITY_NOT_GROUNDED"
SHADOW_SENSITIVE_CONTENT_REJECTED = "SHADOW_SENSITIVE_CONTENT_REJECTED"

STABLE_REASON_CODES = frozenset(
    {
        SHADOW_SCHEMA_INVALID,
        SHADOW_IDENTITY_MISMATCH,
        SHADOW_SOURCE_HASH_MISMATCH,
        SHADOW_SOURCE_SPAN_INVALID,
        SHADOW_EVIDENCE_NOT_PROVENANCED,
        SHADOW_FACTOR_VOCABULARY_INVALID,
        SHADOW_DIRECTION_INVALID,
        SHADOW_DUPLICATE_CLAIM,
        SHADOW_UNAPPROVED_FIELD,
        SHADOW_OUTPUT_TOO_LARGE,
        SHADOW_PROMPT_VERSION_MISMATCH,
        SHADOW_EMPTY_OR_NON_SUBSTANTIVE,
        SHADOW_INVOKER_ERROR,
        SHADOW_JSON_INVALID,
        SHADOW_SOURCE_REF_INVALID,
        SHADOW_ENTITY_NOT_GROUNDED,
        SHADOW_SENSITIVE_CONTENT_REJECTED,
    }
)

BUNDLE_FIELDS = frozenset(
    {
        "schema_version",
        "run_id",
        "ticker",
        "agent",
        "agent_output_id",
        "source_report_sha256",
        "prompt_version",
        "prompt_sha256",
        "claims",
        "abstentions",
        "validation_summary",
        "shadow_only",
        "production_authority",
    }
)
CLAIM_FIELDS = frozenset(
    {
        "shadow_claim_id",
        "claim",
        "evidence",
        "source_spans",
        "entities",
        "factors",
        "direction",
        "confidence",
        "source_type",
        "source_refs",
        "candidate_segment_ids",
        "extraction_status",
    }
)
SPAN_FIELDS = frozenset({"start", "end", "exact_quote"})
ABSTENTION_FIELDS = frozenset({"candidate_segment_ids", "reason_code", "notes"})

_SHA256_RE = re.compile(r"^[0-9a-f]{64}$")
_CREDENTIAL_RE = re.compile(
    r"(?i)(?:sk-[a-z0-9_-]{12,}|bearer\s+[a-z0-9._~+/-]{12,}|"
    r"(?:api[_ -]?key|password|secret|access[_ -]?token)\s*[:=]\s*\S+)"
)


def sha256_text(value: str) -> str:
    """Return lowercase SHA-256 of exact UTF-8 text."""

    return hashlib.sha256(value.encode("utf-8")).hexdigest()


def _canonical_claim_text(value: str) -> str:
    return " ".join(str(value or "").casefold().split())


def _canonical_span_offsets(source_spans: Sequence[Mapping[str, Any]]) -> list[list[int]]:
    offsets: set[tuple[int, int]] = set()
    for span in source_spans:
        start = span.get("start")
        end = span.get("end")
        if isinstance(start, int) and not isinstance(start, bool) and isinstance(end, int) and not isinstance(end, bool):
            offsets.add((start, end))
    return [[start, end] for start, end in sorted(offsets)]


def generate_shadow_claim_id(
    *,
    run_id: str,
    agent_output_id: str,
    claim: str,
    source_spans: Sequence[Mapping[str, Any]],
) -> str:
    """Generate a stable ID without time, randomness, ordinals, or model IDs."""

    material = {
        "identity_version": SHADOW_CLAIM_ID_VERSION,
        "schema_version": STRUCTURED_OUTPUT_SHADOW_SCHEMA_VERSION,
        "run_id": str(run_id),
        "agent_output_id": str(agent_output_id),
        "source_span_offsets": _canonical_span_offsets(source_spans),
        "canonical_claim_sha256": sha256_text(_canonical_claim_text(claim)),
    }
    encoded = json.dumps(material, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
    return f"shadow-claim-v1-{sha256_text(encoded)}"


@dataclass(frozen=True)
class ShadowValidationIssue:
    reason_code: str
    location: str
    message: str

    def to_dict(self) -> dict[str, str]:
        return {
            "reason_code": self.reason_code,
            "location": self.location,
            "message": self.message,
        }


@dataclass
class ShadowValidationResult:
    valid: bool
    status: str
    issues: list[ShadowValidationIssue] = field(default_factory=list)
    warnings: list[ShadowValidationIssue] = field(default_factory=list)

    @property
    def reason_codes(self) -> list[str]:
        return list(dict.fromkeys(issue.reason_code for issue in self.issues))

    def to_summary(self) -> dict[str, Any]:
        return {
            "status": self.status,
            "valid": self.valid,
            "reason_codes": self.reason_codes,
            "issues": [issue.to_dict() for issue in self.issues],
            "warnings": [warning.to_dict() for warning in self.warnings],
        }


def build_shadow_bundle(
    *,
    run_id: str,
    ticker: str,
    agent: str,
    agent_output_id: str,
    source_report_sha256: str,
    prompt_version: str,
    prompt_sha256: str,
    claims: Sequence[Mapping[str, Any]] | None = None,
    abstentions: Sequence[Mapping[str, Any]] | None = None,
    validation_summary: Mapping[str, Any] | None = None,
) -> dict[str, Any]:
    """Build a caller-owned Shadow bundle with permanently false authority."""

    return {
        "schema_version": STRUCTURED_OUTPUT_SHADOW_SCHEMA_VERSION,
        "run_id": str(run_id),
        "ticker": str(ticker),
        "agent": str(agent),
        "agent_output_id": str(agent_output_id),
        "source_report_sha256": str(source_report_sha256),
        "prompt_version": str(prompt_version),
        "prompt_sha256": str(prompt_sha256),
        "claims": [dict(claim) for claim in claims or []],
        "abstentions": [dict(item) for item in abstentions or []],
        "validation_summary": dict(validation_summary or {}),
        "shadow_only": True,
        "production_authority": False,
    }


def build_failure_bundle(
    *,
    run_id: str,
    ticker: str,
    agent: str,
    agent_output_id: str,
    source_report_sha256: str,
    prompt_version: str,
    prompt_sha256: str,
    status: str,
    reason_code: str,
    message: str,
) -> dict[str, Any]:
    issue = ShadowValidationIssue(reason_code, "$", message)
    return build_shadow_bundle(
        run_id=run_id,
        ticker=ticker,
        agent=agent,
        agent_output_id=agent_output_id,
        source_report_sha256=source_report_sha256,
        prompt_version=prompt_version,
        prompt_sha256=prompt_sha256,
        validation_summary=ShadowValidationResult(False, status, [issue]).to_summary(),
    )


def assign_deterministic_claim_ids(bundle: Mapping[str, Any]) -> dict[str, Any]:
    """Return a copy whose claim IDs are computed by deterministic code."""

    result = dict(bundle)
    claims: list[dict[str, Any]] = []
    for raw_claim in bundle.get("claims") or []:
        claim = dict(raw_claim)
        claim["shadow_claim_id"] = generate_shadow_claim_id(
            run_id=str(bundle.get("run_id") or ""),
            agent_output_id=str(bundle.get("agent_output_id") or ""),
            claim=str(claim.get("claim") or ""),
            source_spans=claim.get("source_spans") or [],
        )
        claims.append(claim)
    result["claims"] = claims
    return result


def _normalize_ws(value: str) -> str:
    return " ".join(str(value or "").split())


def _add(
    issues: list[ShadowValidationIssue], reason_code: str, location: str, message: str
) -> None:
    issues.append(ShadowValidationIssue(reason_code, location, message))


def _valid_string_list(value: Any) -> bool:
    return isinstance(value, list) and all(isinstance(item, str) for item in value)


def _validate_source_spans(
    *, report: str, spans: Any, location: str, issues: list[ShadowValidationIssue]
) -> tuple[list[dict[str, Any]], bool]:
    if not isinstance(spans, list) or not spans:
        _add(issues, SHADOW_SOURCE_SPAN_INVALID, location, "source_spans must be a non-empty list")
        return [], False
    valid_spans: list[dict[str, Any]] = []
    valid = True
    for index, raw_span in enumerate(spans):
        span_location = f"{location}[{index}]"
        if not isinstance(raw_span, Mapping):
            _add(issues, SHADOW_SOURCE_SPAN_INVALID, span_location, "span must be an object")
            valid = False
            continue
        extra = set(raw_span) - SPAN_FIELDS
        missing = SPAN_FIELDS - set(raw_span)
        if extra:
            _add(issues, SHADOW_UNAPPROVED_FIELD, span_location, "span has unapproved fields")
            valid = False
        if missing:
            _add(issues, SHADOW_SCHEMA_INVALID, span_location, "span is missing required fields")
            valid = False
            continue
        start, end, quote = raw_span.get("start"), raw_span.get("end"), raw_span.get("exact_quote")
        if (
            not isinstance(start, int)
            or isinstance(start, bool)
            or not isinstance(end, int)
            or isinstance(end, bool)
            or not isinstance(quote, str)
            or start < 0
            or end <= start
            or end > len(report)
        ):
            _add(issues, SHADOW_SOURCE_SPAN_INVALID, span_location, "span offsets or quote type are invalid")
            valid = False
            continue
        if report[start:end] != quote:
            _add(issues, SHADOW_SOURCE_SPAN_INVALID, span_location, "exact_quote does not match report[start:end]")
            valid = False
            continue
        valid_spans.append({"start": start, "end": end, "exact_quote": quote})
    return valid_spans, valid


def _evidence_is_provenanced(evidence: str, spans: Sequence[Mapping[str, Any]]) -> bool:
    normalized_evidence = _normalize_ws(evidence)
    if not normalized_evidence:
        return False
    quotes = [_normalize_ws(str(span["exact_quote"])) for span in spans]
    bounded_combinations = {quote for quote in quotes if quote}
    bounded_combinations.add(_normalize_ws(" ".join(str(span["exact_quote"]) for span in spans)))
    bounded_combinations.add(_normalize_ws("\n".join(str(span["exact_quote"]) for span in spans)))
    return normalized_evidence in bounded_combinations


def validate_shadow_bundle(
    bundle: Any,
    *,
    source_report: str,
    run_id: str,
    ticker: str,
    agent: str,
    agent_output_id: str,
    prompt_version: str,
    prompt_sha256: str,
    factor_vocabulary: Sequence[str],
    allowed_source_refs: Sequence[str] = (),
    allowed_candidate_segment_ids: Sequence[str] | None = None,
    max_claims: int = 128,
    max_output_bytes: int = 1_000_000,
) -> ShadowValidationResult:
    """Validate only deterministic schema/provenance facts, never semantic truth."""

    issues: list[ShadowValidationIssue] = []
    warnings: list[ShadowValidationIssue] = []
    if not isinstance(bundle, Mapping):
        _add(issues, SHADOW_SCHEMA_INVALID, "$", "bundle must be an object")
        return ShadowValidationResult(False, "validation_rejected", issues, warnings)

    try:
        encoded = json.dumps(bundle, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
    except (TypeError, ValueError):
        _add(issues, SHADOW_SCHEMA_INVALID, "$", "bundle is not JSON serializable")
        return ShadowValidationResult(False, "validation_rejected", issues, warnings)
    if len(encoded.encode("utf-8")) > max_output_bytes:
        _add(issues, SHADOW_OUTPUT_TOO_LARGE, "$", "bundle exceeds the configured output limit")

    keys = set(bundle)
    extra = keys - BUNDLE_FIELDS
    missing = BUNDLE_FIELDS - keys
    if extra:
        _add(issues, SHADOW_UNAPPROVED_FIELD, "$", "bundle has unapproved fields")
    if missing:
        _add(issues, SHADOW_SCHEMA_INVALID, "$", "bundle is missing required fields")

    if bundle.get("schema_version") != STRUCTURED_OUTPUT_SHADOW_SCHEMA_VERSION:
        _add(issues, SHADOW_SCHEMA_INVALID, "$.schema_version", "unsupported schema version")
    expected_identity = {
        "run_id": str(run_id),
        "ticker": str(ticker),
        "agent": str(agent),
        "agent_output_id": str(agent_output_id),
    }
    for key, expected in expected_identity.items():
        if bundle.get(key) != expected:
            _add(issues, SHADOW_IDENTITY_MISMATCH, f"$.{key}", "caller-owned identity mismatch")
    expected_source_hash = sha256_text(source_report)
    if bundle.get("source_report_sha256") != expected_source_hash:
        _add(
            issues,
            SHADOW_SOURCE_HASH_MISMATCH,
            "$.source_report_sha256",
            "source report hash mismatch",
        )
    if bundle.get("prompt_version") != prompt_version or bundle.get("prompt_sha256") != prompt_sha256:
        _add(
            issues,
            SHADOW_PROMPT_VERSION_MISMATCH,
            "$.prompt_version",
            "prompt version or hash mismatch",
        )
    if bundle.get("shadow_only") is not True:
        _add(issues, SHADOW_SCHEMA_INVALID, "$.shadow_only", "shadow_only must be true")
    if bundle.get("production_authority") is not False:
        _add(
            issues,
            SHADOW_SCHEMA_INVALID,
            "$.production_authority",
            "production_authority must be false",
        )

    claims = bundle.get("claims")
    abstentions = bundle.get("abstentions")
    if not isinstance(claims, list):
        _add(issues, SHADOW_SCHEMA_INVALID, "$.claims", "claims must be a list")
        claims = []
    if len(claims) > max_claims:
        _add(issues, SHADOW_OUTPUT_TOO_LARGE, "$.claims", "claim count exceeds the configured limit")
    if not isinstance(abstentions, list):
        _add(issues, SHADOW_SCHEMA_INVALID, "$.abstentions", "abstentions must be a list")
        abstentions = []
    if not isinstance(bundle.get("validation_summary"), Mapping):
        _add(
            issues,
            SHADOW_SCHEMA_INVALID,
            "$.validation_summary",
            "validation_summary must be an object",
        )

    factor_set = frozenset(str(value) for value in factor_vocabulary)
    source_ref_set = frozenset(str(value) for value in allowed_source_refs)
    candidate_id_set = (
        None
        if allowed_candidate_segment_ids is None
        else frozenset(str(value) for value in allowed_candidate_segment_ids)
    )
    report_folded = source_report.casefold()
    seen_ids: set[str] = set()
    seen_exact_claims: set[tuple[str, str]] = set()
    span_ranges: list[tuple[int, int, int]] = []
    for index, raw_claim in enumerate(claims):
        location = f"$.claims[{index}]"
        if not isinstance(raw_claim, Mapping):
            _add(issues, SHADOW_SCHEMA_INVALID, location, "claim must be an object")
            continue
        claim_keys = set(raw_claim)
        if claim_keys - CLAIM_FIELDS:
            _add(issues, SHADOW_UNAPPROVED_FIELD, location, "claim has unapproved fields")
        if CLAIM_FIELDS - claim_keys:
            _add(issues, SHADOW_SCHEMA_INVALID, location, "claim is missing required fields")
            continue
        claim_text = raw_claim.get("claim")
        evidence = raw_claim.get("evidence")
        if not isinstance(claim_text, str) or not claim_text.strip():
            _add(issues, SHADOW_EMPTY_OR_NON_SUBSTANTIVE, f"{location}.claim", "claim is empty")
        if not isinstance(evidence, str) or not evidence.strip():
            _add(
                issues,
                SHADOW_EMPTY_OR_NON_SUBSTANTIVE,
                f"{location}.evidence",
                "evidence is empty",
            )
        spans, spans_valid = _validate_source_spans(
            report=source_report,
            spans=raw_claim.get("source_spans"),
            location=f"{location}.source_spans",
            issues=issues,
        )
        if spans_valid and isinstance(evidence, str) and not _evidence_is_provenanced(evidence, spans):
            _add(
                issues,
                SHADOW_EVIDENCE_NOT_PROVENANCED,
                f"{location}.evidence",
                "evidence is not an exact bounded combination of source spans",
            )
        for span in spans:
            span_ranges.append((span["start"], span["end"], index))

        expected_claim_id = generate_shadow_claim_id(
            run_id=str(run_id),
            agent_output_id=str(agent_output_id),
            claim=str(claim_text or ""),
            source_spans=spans,
        )
        claim_id = raw_claim.get("shadow_claim_id")
        if claim_id != expected_claim_id:
            _add(
                issues,
                SHADOW_IDENTITY_MISMATCH,
                f"{location}.shadow_claim_id",
                "claim ID was not generated from the frozen identity inputs",
            )
        if isinstance(claim_id, str):
            if claim_id in seen_ids:
                _add(issues, SHADOW_DUPLICATE_CLAIM, f"{location}.shadow_claim_id", "duplicate claim ID")
            seen_ids.add(claim_id)
        exact_claim_signature = (_normalize_ws(str(claim_text)), _normalize_ws(str(evidence)))
        if exact_claim_signature in seen_exact_claims:
            _add(
                issues,
                SHADOW_DUPLICATE_CLAIM,
                location,
                "exact duplicate claim/evidence proposal",
            )
        seen_exact_claims.add(exact_claim_signature)

        direction = raw_claim.get("direction")
        if direction not in VALID_DIRECTIONS:
            _add(issues, SHADOW_DIRECTION_INVALID, f"{location}.direction", "invalid direction")
        confidence = raw_claim.get("confidence")
        if (
            not isinstance(confidence, (int, float))
            or isinstance(confidence, bool)
            or not math.isfinite(float(confidence))
            or not 0 <= float(confidence) <= 1
        ):
            _add(issues, SHADOW_SCHEMA_INVALID, f"{location}.confidence", "confidence must be finite in [0,1]")
        if raw_claim.get("source_type") not in VALID_SOURCE_TYPES:
            _add(issues, SHADOW_SCHEMA_INVALID, f"{location}.source_type", "invalid source_type")
        if raw_claim.get("extraction_status") not in VALID_EXTRACTION_STATUSES:
            _add(
                issues,
                SHADOW_SCHEMA_INVALID,
                f"{location}.extraction_status",
                "invalid extraction_status",
            )

        factors = raw_claim.get("factors")
        if not _valid_string_list(factors):
            _add(issues, SHADOW_SCHEMA_INVALID, f"{location}.factors", "factors must be strings")
        elif any(value not in factor_set for value in factors):
            _add(
                issues,
                SHADOW_FACTOR_VOCABULARY_INVALID,
                f"{location}.factors",
                "factor is outside the caller-supplied vocabulary",
            )
        entities = raw_claim.get("entities")
        if not _valid_string_list(entities):
            _add(issues, SHADOW_SCHEMA_INVALID, f"{location}.entities", "entities must be strings")
        else:
            for entity in entities:
                if entity.strip() and entity.casefold() not in report_folded:
                    _add(
                        issues,
                        SHADOW_ENTITY_NOT_GROUNDED,
                        f"{location}.entities",
                        "entity is not textually grounded in the source report",
                    )
        refs = raw_claim.get("source_refs")
        if not _valid_string_list(refs):
            _add(issues, SHADOW_SCHEMA_INVALID, f"{location}.source_refs", "source_refs must be strings")
        elif any(value not in source_ref_set for value in refs):
            _add(
                issues,
                SHADOW_SOURCE_REF_INVALID,
                f"{location}.source_refs",
                "source_ref was not supplied by caller metadata",
            )
        candidate_ids = raw_claim.get("candidate_segment_ids")
        if not _valid_string_list(candidate_ids):
            _add(
                issues,
                SHADOW_SCHEMA_INVALID,
                f"{location}.candidate_segment_ids",
                "candidate_segment_ids must be strings",
            )
        elif candidate_id_set is not None and any(
            value not in candidate_id_set for value in candidate_ids
        ):
            _add(
                issues,
                SHADOW_IDENTITY_MISMATCH,
                f"{location}.candidate_segment_ids",
                "candidate lineage references an unknown caller-supplied ID",
            )
        if isinstance(evidence, str) and _CREDENTIAL_RE.search(evidence):
            _add(
                issues,
                SHADOW_SENSITIVE_CONTENT_REJECTED,
                f"{location}.evidence",
                "credential-like text cannot be admitted as evidence",
            )

    sorted_ranges = sorted(span_ranges)
    for left, right in zip(sorted_ranges, sorted_ranges[1:], strict=False):
        if left[2] != right[2] and right[0] < left[1]:
            warnings.append(
                ShadowValidationIssue(
                    "SHADOW_SOURCE_SPAN_OVERLAP",
                    "$.claims",
                    "source spans overlap across claims; recorded as a diagnostic signal",
                )
            )

    for index, abstention in enumerate(abstentions):
        location = f"$.abstentions[{index}]"
        if not isinstance(abstention, Mapping):
            _add(issues, SHADOW_SCHEMA_INVALID, location, "abstention must be an object")
            continue
        if set(abstention) - ABSTENTION_FIELDS:
            _add(issues, SHADOW_UNAPPROVED_FIELD, location, "abstention has unapproved fields")
        if ABSTENTION_FIELDS - set(abstention):
            _add(issues, SHADOW_SCHEMA_INVALID, location, "abstention is missing required fields")
            continue
        if not _valid_string_list(abstention.get("candidate_segment_ids")):
            _add(issues, SHADOW_SCHEMA_INVALID, location, "abstention candidate IDs must be strings")
        if not isinstance(abstention.get("reason_code"), str) or not abstention.get("reason_code", "").strip():
            _add(issues, SHADOW_SCHEMA_INVALID, location, "abstention reason_code is required")
        if not isinstance(abstention.get("notes"), str):
            _add(issues, SHADOW_SCHEMA_INVALID, location, "abstention notes must be a string")

    if issues:
        return ShadowValidationResult(False, "validation_rejected", issues, warnings)
    if not claims and abstentions:
        return ShadowValidationResult(True, "abstained", issues, warnings)
    if not claims:
        warnings.append(
            ShadowValidationIssue(
                SHADOW_EMPTY_OR_NON_SUBSTANTIVE,
                "$.claims",
                "valid empty output; semantic quality is not inferred",
            )
        )
        return ShadowValidationResult(True, "empty_valid_output", issues, warnings)
    return ShadowValidationResult(True, "accepted", issues, warnings)


__all__ = [
    "ABSTENTION_FIELDS",
    "BUNDLE_FIELDS",
    "CLAIM_FIELDS",
    "SHADOW_CLAIM_ID_VERSION",
    "SHADOW_INPUT_SCHEMA_VERSION",
    "STABLE_REASON_CODES",
    "STRUCTURED_OUTPUT_SHADOW_SCHEMA_VERSION",
    "VALID_DIRECTIONS",
    "VALID_EXTRACTION_STATUSES",
    "VALID_SOURCE_TYPES",
    "ShadowValidationIssue",
    "ShadowValidationResult",
    "assign_deterministic_claim_ids",
    "build_failure_bundle",
    "build_shadow_bundle",
    "generate_shadow_claim_id",
    "sha256_text",
    "validate_shadow_bundle",
]
