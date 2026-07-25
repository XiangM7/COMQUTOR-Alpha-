"""Strict loader, validator, deterministic scorer, and semantic fingerprint
for the Entity Alpha Exposure Rubric Contract v1.

``exposure_rubric_contract_v1.yaml`` is the sole canonical source of truth.
This module never creates an entity Exposure Seed, never reads a ticker or
current Research evidence, never calls an LLM or the network, and never
lets an environment variable or HTTP request select a different contract.
"""

from __future__ import annotations

import hashlib
import json
import math
from importlib import resources

import yaml

from comqutor_alpha.alpha_library.alpha_loader import TAXONOMY_PATH, load_alpha_taxonomy

CONTRACT_PACKAGE = "comqutor_alpha.exposure"
CONTRACT_RESOURCE_NAME = "exposure_rubric_contract_v1.yaml"

EXPECTED_SCHEMA_VERSION = "comqutor.entity_alpha_exposure_rubric_contract.v1"
EXPECTED_CONTRACT_VERSION = "exposure-rubric-contract-v1"
EXPECTED_TAXONOMY_VERSION = "alpha_taxonomy_v1"

# The five discrete scoring rungs -- exact float identity, not a tolerance
# comparison, since these are the literal allowed values, not a computed
# quantity.
EXPECTED_SCORE_SCALE = (0.0, 0.25, 0.5, 0.75, 1.0)
EXPECTED_SCORE_SEMANTICS_LABELS = {
    0.0: "none_confirmed",
    0.25: "peripheral",
    0.5: "meaningful",
    0.75: "major",
    1.0: "core",
}
EXPECTED_ALLOWED_IMPACT_SEMANTICS = frozenset(
    {"supportive_sensitivity", "adverse_sensitivity", "reflexive_dependency"}
)
EXPECTED_MVP10_ALPHA_IDS = frozenset(
    {"A001", "A003", "A101", "A102", "A103", "A201", "A301", "A304", "A501", "A601"}
)
# Only the operating_theme_rubric.v1 assignments (A101/A102/A103) carry a
# scope_key/scope_definition pair -- every other Alpha assignment must not.
SCOPE_REQUIRED_ALPHA_IDS = frozenset({"A101", "A102", "A103"})

_DIMENSIONS_PER_RUBRIC = 4
_WEIGHT_SUM_TOLERANCE = 1e-9

_TOP_LEVEL_KEYS = frozenset(
    {
        "schema_version",
        "contract_version",
        "taxonomy_version",
        "score_scale",
        "score_semantics",
        "allowed_impact_semantics",
        "rubrics",
        "alpha_assignments",
    }
)
_SCORE_SEMANTICS_KEYS = frozenset(
    {"scale", "interpretation", "structural_exposure_formula", "missing_exposure_semantics"}
)
_RUBRIC_KEYS = frozenset({"purpose", "dimensions"})
_DIMENSION_KEYS = frozenset({"dimension_id", "weight", "definition"})
_ASSIGNMENT_BASE_KEYS = frozenset({"name", "rubric_id", "impact_semantics"})
_ASSIGNMENT_SCOPE_KEYS = frozenset({"scope_key", "scope_definition"})


class ExposureContractError(ValueError):
    """Safe contract-violation error: a stable reason code only."""

    def __init__(self, reason_code: str) -> None:
        self.reason_code = reason_code
        super().__init__(reason_code)


def _fail(reason_code: str):
    raise ExposureContractError(reason_code)


def _is_finite_number(value) -> bool:
    if isinstance(value, bool):
        return False
    if not isinstance(value, (int, float)):
        return False
    return math.isfinite(float(value))


def _require_dict(value, reason_code: str) -> dict:
    if not isinstance(value, dict):
        _fail(reason_code)
    return value


def _require_exact_keys(mapping: dict, expected_keys, reason_code: str) -> None:
    if set(mapping) != set(expected_keys):
        _fail(reason_code)


def _require_nonempty_string(value, reason_code: str) -> str:
    if not isinstance(value, str) or not value.strip():
        _fail(reason_code)
    return value


# ---------------------------------------------------------------------------
# Loader
# ---------------------------------------------------------------------------


def load_exposure_rubric_contract() -> dict:
    """Loads and strictly validates the canonical v1 contract.

    Uses ``importlib.resources`` exclusively (works from a source checkout,
    an installed wheel, or a zipped package -- never a hardcoded local path
    or the current working directory), ``yaml.safe_load`` only, and never
    consults the network or any environment variable. Raises
    :class:`ExposureContractError` on any contract violation.
    """
    resource = resources.files(CONTRACT_PACKAGE).joinpath(CONTRACT_RESOURCE_NAME)
    text = resource.read_text(encoding="utf-8")
    try:
        payload = yaml.safe_load(text)
    except yaml.YAMLError as exc:
        raise ExposureContractError("MALFORMED_CONTRACT_YAML") from exc
    validate_exposure_rubric_contract(payload)
    return payload


# ---------------------------------------------------------------------------
# Validator
# ---------------------------------------------------------------------------


def validate_exposure_rubric_contract(payload) -> None:
    """Strict, whole-document validation. Every top-level and nested object
    is checked for an exact field set (unknown fields rejected, missing
    fields rejected); every numeric value must be finite; every reference
    (rubric_id, taxonomy alpha_id/name) must resolve."""
    _require_dict(payload, "CONTRACT_NOT_A_MAPPING")
    _require_exact_keys(payload, _TOP_LEVEL_KEYS, "UNKNOWN_OR_MISSING_TOP_LEVEL_FIELD")

    if payload.get("schema_version") != EXPECTED_SCHEMA_VERSION:
        _fail("SCHEMA_VERSION_MISMATCH")
    if payload.get("contract_version") != EXPECTED_CONTRACT_VERSION:
        _fail("CONTRACT_VERSION_MISMATCH")
    taxonomy_version = payload.get("taxonomy_version")
    if taxonomy_version != EXPECTED_TAXONOMY_VERSION:
        _fail("TAXONOMY_VERSION_MISMATCH")

    _validate_score_scale(payload.get("score_scale"))
    _validate_score_semantics(payload.get("score_semantics"))
    _validate_allowed_impact_semantics(payload.get("allowed_impact_semantics"))
    rubrics = _validate_rubrics(payload.get("rubrics"))
    alpha_assignments = _validate_alpha_assignments(payload.get("alpha_assignments"), rubrics)
    _validate_taxonomy_consistency(alpha_assignments, taxonomy_version)


def _validate_score_scale(value) -> None:
    if not isinstance(value, list) or len(value) != len(EXPECTED_SCORE_SCALE):
        _fail("INVALID_SCORE_SCALE")
    for item, expected in zip(value, EXPECTED_SCORE_SCALE, strict=True):
        if not _is_finite_number(item) or float(item) != expected:
            _fail("INVALID_SCORE_SCALE")


def _validate_score_semantics(value) -> None:
    _require_dict(value, "INVALID_SCORE_SEMANTICS")
    _require_exact_keys(value, _SCORE_SEMANTICS_KEYS, "UNKNOWN_OR_MISSING_SCORE_SEMANTICS_FIELD")

    scale = _require_dict(value.get("scale"), "INVALID_SCORE_SEMANTICS_SCALE")
    if len(scale) != len(EXPECTED_SCORE_SEMANTICS_LABELS):
        _fail("INVALID_SCORE_SEMANTICS_SCALE")
    seen_keys = set()
    for key, label in scale.items():
        if not _is_finite_number(key):
            _fail("INVALID_SCORE_SEMANTICS_SCALE")
        numeric_key = float(key)
        if numeric_key not in EXPECTED_SCORE_SEMANTICS_LABELS:
            _fail("INVALID_SCORE_SEMANTICS_SCALE")
        if label != EXPECTED_SCORE_SEMANTICS_LABELS[numeric_key]:
            _fail("INVALID_SCORE_SEMANTICS_SCALE")
        seen_keys.add(numeric_key)
    if seen_keys != set(EXPECTED_SCORE_SEMANTICS_LABELS):
        _fail("INVALID_SCORE_SEMANTICS_SCALE")

    _require_nonempty_string(value.get("interpretation"), "INVALID_SCORE_SEMANTICS_INTERPRETATION")
    _require_nonempty_string(value.get("structural_exposure_formula"), "INVALID_SCORE_SEMANTICS_FORMULA")
    _require_nonempty_string(value.get("missing_exposure_semantics"), "INVALID_SCORE_SEMANTICS_MISSING")


def _validate_allowed_impact_semantics(value) -> None:
    _require_dict(value, "INVALID_ALLOWED_IMPACT_SEMANTICS")
    _require_exact_keys(value, EXPECTED_ALLOWED_IMPACT_SEMANTICS, "UNKNOWN_OR_MISSING_IMPACT_SEMANTICS")
    for definition in value.values():
        _require_nonempty_string(definition, "INVALID_IMPACT_SEMANTICS_DEFINITION")


def _validate_rubrics(value) -> dict:
    _require_dict(value, "INVALID_RUBRICS")
    if not value:
        _fail("EMPTY_RUBRICS")
    for rubric_id, rubric in value.items():
        _require_nonempty_string(rubric_id, "INVALID_RUBRIC_ID")
        _require_dict(rubric, "INVALID_RUBRIC")
        _require_exact_keys(rubric, _RUBRIC_KEYS, "UNKNOWN_OR_MISSING_RUBRIC_FIELD")
        _require_nonempty_string(rubric.get("purpose"), "INVALID_RUBRIC_PURPOSE")
        _validate_dimensions(rubric.get("dimensions"))
    return value


def _validate_dimensions(value) -> None:
    if not isinstance(value, list) or len(value) != _DIMENSIONS_PER_RUBRIC:
        _fail("RUBRIC_MUST_HAVE_EXACTLY_FOUR_DIMENSIONS")

    seen_ids: set[str] = set()
    weight_sum = 0.0
    for dimension in value:
        _require_dict(dimension, "INVALID_DIMENSION")
        _require_exact_keys(dimension, _DIMENSION_KEYS, "UNKNOWN_OR_MISSING_DIMENSION_FIELD")

        dimension_id = _require_nonempty_string(dimension.get("dimension_id"), "INVALID_DIMENSION_ID")
        if dimension_id in seen_ids:
            _fail("DUPLICATE_DIMENSION_ID")
        seen_ids.add(dimension_id)

        weight = dimension.get("weight")
        if not _is_finite_number(weight):
            _fail("INVALID_DIMENSION_WEIGHT")
        weight = float(weight)
        if weight <= 0:
            _fail("NON_POSITIVE_DIMENSION_WEIGHT")
        weight_sum += weight

        _require_nonempty_string(dimension.get("definition"), "INVALID_DIMENSION_DEFINITION")

    if abs(weight_sum - 1.0) > _WEIGHT_SUM_TOLERANCE:
        _fail("DIMENSION_WEIGHTS_MUST_SUM_TO_ONE")


def _validate_alpha_assignments(value, rubrics: dict) -> dict:
    _require_dict(value, "INVALID_ALPHA_ASSIGNMENTS")
    alpha_ids = set(value)
    if alpha_ids != EXPECTED_MVP10_ALPHA_IDS:
        _fail("ALPHA_ASSIGNMENT_SET_MISMATCH")

    for alpha_id, assignment in value.items():
        _require_dict(assignment, "INVALID_ALPHA_ASSIGNMENT")
        requires_scope = alpha_id in SCOPE_REQUIRED_ALPHA_IDS
        expected_keys = _ASSIGNMENT_BASE_KEYS | (_ASSIGNMENT_SCOPE_KEYS if requires_scope else frozenset())
        _require_exact_keys(assignment, expected_keys, "UNKNOWN_OR_MISSING_ALPHA_ASSIGNMENT_FIELD")

        _require_nonempty_string(assignment.get("name"), "INVALID_ALPHA_NAME")
        rubric_id = _require_nonempty_string(assignment.get("rubric_id"), "INVALID_ALPHA_RUBRIC_ID")
        if rubric_id not in rubrics:
            _fail("ALPHA_ASSIGNMENT_REFERENCES_UNKNOWN_RUBRIC")

        impact_semantics = _require_nonempty_string(
            assignment.get("impact_semantics"), "INVALID_ALPHA_IMPACT_SEMANTICS"
        )
        if impact_semantics not in EXPECTED_ALLOWED_IMPACT_SEMANTICS:
            _fail("ALPHA_IMPACT_SEMANTICS_NOT_ALLOWED")

        if requires_scope:
            _require_nonempty_string(assignment.get("scope_key"), "INVALID_ALPHA_SCOPE_KEY")
            _require_nonempty_string(assignment.get("scope_definition"), "INVALID_ALPHA_SCOPE_DEFINITION")

    return value


def _validate_taxonomy_consistency(alpha_assignments: dict, taxonomy_version) -> None:
    """Read-only cross-check against the frozen alpha_taxonomy_v1.yaml --
    never mutates it, never auto-adds a taxonomy Alpha the contract doesn't
    already declare, and never invents a default rubric for one missing
    from the contract."""
    with TAXONOMY_PATH.open(encoding="utf-8") as f:
        raw_taxonomy = yaml.safe_load(f)
    if not isinstance(raw_taxonomy, dict) or raw_taxonomy.get("schema_version") != taxonomy_version:
        _fail("TAXONOMY_SCHEMA_VERSION_MISMATCH")

    taxonomy = load_alpha_taxonomy()
    for alpha_id, assignment in alpha_assignments.items():
        alpha = taxonomy.get(alpha_id)
        if alpha is None:
            _fail("ALPHA_ID_NOT_IN_TAXONOMY")
        if alpha.name_en != assignment.get("name"):
            _fail("ALPHA_NAME_TAXONOMY_MISMATCH")


# ---------------------------------------------------------------------------
# Deterministic scoring
# ---------------------------------------------------------------------------


def compute_structural_exposure(rubric_id, dimension_scores, *, contract: dict | None = None) -> float:
    """Deterministic weighted sum of exactly one rubric's four dimension
    scores.

    Every dimension must be present, no unknown dimension is accepted, and
    every score must be exactly one of the five ``score_scale`` rungs. Reads
    only the rubric's fixed weights from the contract -- no confidence, no
    ticker, no current Research evidence, no Activation input, no LLM call.
    The same input always produces the same output, regardless of the
    ``dimension_scores`` mapping's insertion order.
    """
    payload = contract if contract is not None else load_exposure_rubric_contract()
    rubrics = payload["rubrics"]
    if not isinstance(rubric_id, str) or rubric_id not in rubrics:
        _fail("UNKNOWN_RUBRIC_ID")
    if not isinstance(dimension_scores, dict):
        _fail("INVALID_DIMENSION_SCORES")

    dimensions = rubrics[rubric_id]["dimensions"]
    expected_ids = {dimension["dimension_id"] for dimension in dimensions}
    provided_ids = set(dimension_scores)
    if provided_ids != expected_ids:
        _fail("DIMENSION_SCORE_SET_MISMATCH")

    allowed_scores = {float(v) for v in payload["score_scale"]}
    total = 0.0
    for dimension in dimensions:
        raw_score = dimension_scores[dimension["dimension_id"]]
        if not _is_finite_number(raw_score):
            _fail("INVALID_DIMENSION_SCORE")
        score = float(raw_score)
        if score not in allowed_scores:
            _fail("DIMENSION_SCORE_NOT_ON_SCALE")
        total += score * float(dimension["weight"])

    result = round(total, 4)
    if not math.isfinite(result) or not (0.0 <= result <= 1.0):
        _fail("NON_FINITE_STRUCTURAL_EXPOSURE_RESULT")
    return result


# ---------------------------------------------------------------------------
# Semantic fingerprint
# ---------------------------------------------------------------------------


def compute_contract_fingerprint(payload) -> str:
    """SHA-256 hex digest of a canonical JSON serialization of the
    already-validated semantic payload.

    UTF-8 encoded, keys sorted, fixed ``(",", ":")`` separators -- the
    result depends only on the payload's semantic content, never on YAML
    whitespace, comments, blank lines, or field-write order. Never reads a
    fingerprint value back out of the payload being fingerprinted (the
    contract does not declare one).
    """
    serialized = json.dumps(payload, sort_keys=True, separators=(",", ":"), ensure_ascii=True)
    return hashlib.sha256(serialized.encode("utf-8")).hexdigest()
