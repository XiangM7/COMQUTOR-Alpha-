"""J2 six-ticker provisional regression labels: schema loader and
validator for
``comqutor_alpha/config/j2_provisional_regression_labels_v0.1.yaml``.

Provisional, shadow-evaluation-only labels -- authorized by the user as
the current development stage's product judgment, never John-approved,
never formal gold, never final semantic accuracy. Read only by the A4
regression evaluator (``comqutor_alpha.regression.evaluator``); never
imported by the Alpha Mapper, Activation, Exposure, Conflict Detector, or
any production API/UI response -- doing so would let a label answer the
question it is supposed to be graded against (a circular evaluation).

``evaluation_mode``/``formal_product_owner_approval``/``approved_by`` are
read verbatim from the file and never altered here -- in particular,
never read from an environment variable. The only promotion path from
"shadow"/"pending" to "authoritative"/"approved" is a human edit to this
file, verified here only for internal cross-field consistency (an
"authoritative" claim must carry real approval fields), never granted by
this loader itself.
"""

from __future__ import annotations

import re
from pathlib import Path
from typing import Any

import yaml

from comqutor_alpha.alpha_library.alpha_loader import load_alpha_taxonomy
from comqutor_alpha.conflict_engine.conflict_schema import canonical_pair_key, conflict_id

_PACKAGE_ROOT = Path(__file__).resolve().parents[1]
DEFAULT_LABEL_PATH = _PACKAGE_ROOT / "config" / "j2_provisional_regression_labels_v0.1.yaml"

SCHEMA_VERSION = "regression_labels.v1"

STATUS_PROVISIONAL_AI_PREDICTED = "provisional_ai_predicted"
EVALUATION_MODE_SHADOW = "shadow"
EVALUATION_MODE_AUTHORITATIVE = "authoritative"
EVALUATION_AUTHORITY_PROVISIONAL = "provisional"
EVALUATION_AUTHORITY_AUTHORITATIVE = "authoritative"
APPROVAL_PENDING = "pending"
APPROVAL_APPROVED = "approved"

_VALID_EVALUATION_MODES = frozenset({EVALUATION_MODE_SHADOW, EVALUATION_MODE_AUTHORITATIVE})
_VALID_APPROVAL_STATES = frozenset({APPROVAL_PENDING, APPROVAL_APPROVED})
_REQUIRED_TOP_LEVEL_KEYS = (
    "schema_version",
    "label_version",
    "evaluation_mode",
    "evaluation_authority",
    "approved_by",
    "approved_at",
    "formal_product_owner_approval",
    "tickers",
)
_REQUIRED_TICKER_KEYS = (
    "expected_positive_alphas",
    "expected_negative_alphas",
    "conditional_alphas",
    "allowed_main_conflicts",
)
_CONFLICT_PAIR_PATTERN = re.compile(r"^[A-Za-z0-9]+__[A-Za-z0-9]+$")


class LabelValidationError(Exception):
    """A structural/vocabulary violation in the label file itself -- never
    raised for a provisional-vs-detected mismatch (that is a comparison
    result, reported by the evaluator, not a load-time error)."""

    def __init__(self, reason_code: str, detail: str = "") -> None:
        self.reason_code = reason_code
        self.detail = detail
        super().__init__(f"{reason_code}: {detail}" if detail else reason_code)


def _canonical_conflict_pairs(taxonomy: dict[str, Any]) -> frozenset[str]:
    pairs: set[str] = set()
    for alpha_id, alpha in taxonomy.items():
        for partner in getattr(alpha, "conflict_alphas", None) or ():
            other = getattr(partner, "alpha_id", partner)
            a, b = canonical_pair_key(alpha_id, str(other))
            pairs.add(conflict_id(a, b))
    return frozenset(pairs)


def _as_id_list(value: Any) -> list[str]:
    return [str(v) for v in value] if isinstance(value, list) else []


def _validate_top_level(raw: dict[str, Any]) -> None:
    for key in _REQUIRED_TOP_LEVEL_KEYS:
        if key not in raw:
            raise LabelValidationError("LABEL_MISSING_REQUIRED_FIELD", key)
    if raw["schema_version"] != SCHEMA_VERSION:
        raise LabelValidationError("LABEL_SCHEMA_VERSION_MISMATCH", str(raw["schema_version"]))
    if raw["evaluation_mode"] not in _VALID_EVALUATION_MODES:
        raise LabelValidationError("LABEL_INVALID_EVALUATION_MODE", str(raw["evaluation_mode"]))
    if raw["formal_product_owner_approval"] not in _VALID_APPROVAL_STATES:
        raise LabelValidationError(
            "LABEL_INVALID_APPROVAL_STATE", str(raw["formal_product_owner_approval"])
        )
    # Cross-field consistency: a genuine "authoritative" claim requires
    # real approval provenance -- never a bare mode flip with no approver.
    claims_authoritative = (
        raw["evaluation_mode"] == EVALUATION_MODE_AUTHORITATIVE
        or raw["formal_product_owner_approval"] == APPROVAL_APPROVED
    )
    fully_approved = (
        raw["evaluation_mode"] == EVALUATION_MODE_AUTHORITATIVE
        and raw["formal_product_owner_approval"] == APPROVAL_APPROVED
        and raw.get("approved_by")
        and raw.get("approved_at")
    )
    if claims_authoritative and not fully_approved:
        raise LabelValidationError("LABEL_AUTHORITATIVE_CLAIM_MISSING_APPROVAL_PROVENANCE")
    if not isinstance(raw["tickers"], dict) or not raw["tickers"]:
        raise LabelValidationError("LABEL_NO_TICKERS_DECLARED")


def _validate_ticker_block(ticker: str, block: Any, known_alpha_ids: frozenset[str]) -> None:
    if not isinstance(block, dict):
        raise LabelValidationError("LABEL_TICKER_BLOCK_NOT_A_MAPPING", ticker)
    for key in _REQUIRED_TICKER_KEYS:
        if key not in block:
            raise LabelValidationError("LABEL_TICKER_MISSING_REQUIRED_FIELD", f"{ticker}.{key}")

    positive = set(_as_id_list(block["expected_positive_alphas"]))
    negative = set(_as_id_list(block["expected_negative_alphas"]))
    conditional = set(_as_id_list(block["conditional_alphas"]))

    for group_name, group in (
        ("expected_positive_alphas", positive),
        ("expected_negative_alphas", negative),
        ("conditional_alphas", conditional),
    ):
        unknown = group - known_alpha_ids
        if unknown:
            raise LabelValidationError(
                "LABEL_UNKNOWN_ALPHA_ID", f"{ticker}.{group_name}: {sorted(unknown)}"
            )

    dominance_guard = block.get("should_not_be_dominant_without_strong_evidence") or {}
    if not isinstance(dominance_guard, dict):
        raise LabelValidationError("LABEL_DOMINANCE_GUARD_NOT_A_MAPPING", ticker)
    unknown_guard_ids = set(dominance_guard.keys()) - known_alpha_ids
    if unknown_guard_ids:
        raise LabelValidationError(
            "LABEL_UNKNOWN_ALPHA_ID",
            f"{ticker}.should_not_be_dominant_without_strong_evidence: {sorted(unknown_guard_ids)}",
        )

    overlaps = {
        "expected_positive_alphas__expected_negative_alphas": sorted(positive & negative),
        "expected_positive_alphas__conditional_alphas": sorted(positive & conditional),
        "expected_negative_alphas__conditional_alphas": sorted(negative & conditional),
    }
    for pair_name, overlap in overlaps.items():
        if overlap:
            raise LabelValidationError("LABEL_ALPHA_GROUPS_OVERLAP", f"{ticker}.{pair_name}: {overlap}")

    for pair in block["allowed_main_conflicts"] or ():
        if not isinstance(pair, str) or not _CONFLICT_PAIR_PATTERN.match(pair):
            raise LabelValidationError("LABEL_MALFORMED_CONFLICT_PAIR", f"{ticker}: {pair!r}")
        half_a, half_b = pair.split("__", 1)
        if half_a not in known_alpha_ids or half_b not in known_alpha_ids:
            raise LabelValidationError("LABEL_UNKNOWN_ALPHA_ID", f"{ticker}.allowed_main_conflicts: {pair!r}")


def load_j2_labels(path: str | Path | None = None) -> dict[str, Any]:
    """Loads and structurally validates the J2 label file.

    Raises :class:`LabelValidationError` for any structural/vocabulary
    violation. Never raises for a provisional conflict pair absent from
    the canonical taxonomy -- that is reported via the returned dict's
    ``undeclared_conflict_pairs`` (task section 5: report
    ``PREDICTED_CONFLICT_PAIR_NOT_DECLARED``, never silently drop the
    prediction, never modify the taxonomy to accommodate it).
    """
    resolved_path = Path(path) if path is not None else DEFAULT_LABEL_PATH
    if not resolved_path.exists():
        raise LabelValidationError("LABEL_FILE_NOT_FOUND", str(resolved_path))
    try:
        raw = yaml.safe_load(resolved_path.read_text(encoding="utf-8"))
    except yaml.YAMLError as exc:
        raise LabelValidationError("LABEL_FILE_MALFORMED_YAML", str(exc)) from exc
    if not isinstance(raw, dict):
        raise LabelValidationError("LABEL_FILE_NOT_A_MAPPING")

    _validate_top_level(raw)

    taxonomy = load_alpha_taxonomy()
    known_alpha_ids = frozenset(taxonomy.keys())
    canonical_pairs = _canonical_conflict_pairs(taxonomy)

    undeclared_conflict_pairs: dict[str, list[str]] = {}
    for ticker, block in raw["tickers"].items():
        _validate_ticker_block(str(ticker), block, known_alpha_ids)
        undeclared = sorted(
            pair for pair in (block.get("allowed_main_conflicts") or ()) if pair not in canonical_pairs
        )
        if undeclared:
            undeclared_conflict_pairs[str(ticker)] = undeclared

    raw["undeclared_conflict_pairs"] = undeclared_conflict_pairs
    raw["canonical_conflict_pairs"] = sorted(canonical_pairs)
    raw["source_path"] = str(resolved_path)
    return raw


def ticker_label(labels: dict[str, Any], ticker: str) -> dict[str, Any] | None:
    """Read-only accessor for one ticker's label block, or ``None`` when
    this ticker has no J2 label at all (a real, honest gap -- never
    fabricated)."""
    tickers = labels.get("tickers")
    if not isinstance(tickers, dict):
        return None
    block = tickers.get(str(ticker).upper())
    return block if isinstance(block, dict) else None


__all__ = [
    "SCHEMA_VERSION",
    "STATUS_PROVISIONAL_AI_PREDICTED",
    "EVALUATION_MODE_SHADOW",
    "EVALUATION_MODE_AUTHORITATIVE",
    "EVALUATION_AUTHORITY_PROVISIONAL",
    "EVALUATION_AUTHORITY_AUTHORITATIVE",
    "APPROVAL_PENDING",
    "APPROVAL_APPROVED",
    "DEFAULT_LABEL_PATH",
    "LabelValidationError",
    "load_j2_labels",
    "ticker_label",
]
