"""J2 v0.2 evaluation contract: schema loader and validator for
``comqutor_alpha/config/j2_provisional_regression_labels_v0.2.yaml``.

v0.1 (``comqutor_alpha.regression.labels``) is untouched and remains
independently loadable -- this module is purely additive. v0.2 replaces
v0.1's flat "expected Alpha" framing with five explicitly distinct
categories (task section 7):

  * ``structural_expectations`` -- ticker-general, never a strict
    per-run requirement; a missing structural Alpha never fails a run.
  * ``run_bound_expectations`` -- only meaningful as a strict per-run
    expectation once bound to a specific reference_run_id/analysis_date/
    taxonomy_version/B1 stance source+version/artifact completeness.
  * ``required_conflicts`` -- only for an approved, complete,
    version-locked reference run; a miss here is a real fail. Always
    canonical taxonomy pairs (an undeclared pair here is a validator
    error, unlike v0.1's lenient allow-and-flag).
  * ``conditional_conflicts`` -- reasonable if evidence/thresholds are
    met; a miss is informational only, never fails the ticker. Always
    canonical taxonomy pairs.
  * ``product_decision_pending`` -- an unresolved conflict between
    product documentation and the canonical taxonomy; never computed as
    pass/fail, never used to silently modify the taxonomy. Pair need not
    be canonical (that is exactly what makes it "pending").
  * ``remove_while_undeclared`` -- a pair that is no longer an executable
    regression expectation because it is not in the canonical taxonomy.
    Never deletes any production/historical data -- purely a label-side
    exclusion. Must genuinely be non-canonical (a canonical pair listed
    here is a label inconsistency, rejected).
  * ``allowed_conflicts`` -- a real, canonical pair that may legitimately
    appear as admitted/candidate, but is not (yet) required or even
    conditional -- distinct from silence, distinct from a promise.

Every one of the five "which category is this pair in" sets is mutually
exclusive per ticker (task test #20) -- validated here, never left to the
evaluator to discover at runtime.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

from comqutor_alpha.alpha_library.alpha_loader import load_alpha_taxonomy
from comqutor_alpha.regression.labels import _CONFLICT_PAIR_PATTERN, _canonical_conflict_pairs

_PACKAGE_ROOT = Path(__file__).resolve().parents[1]
DEFAULT_LABEL_V2_PATH = _PACKAGE_ROOT / "config" / "j2_provisional_regression_labels_v0.2.yaml"

SCHEMA_VERSION_V2 = "regression_labels.v2"

_VALID_EVALUATION_MODES = frozenset({"shadow", "authoritative"})
_VALID_APPROVAL_STATES = frozenset({"pending", "approved"})

_REQUIRED_TOP_LEVEL_KEYS = (
    "schema_version",
    "label_version",
    "taxonomy_version",
    "evaluation_mode",
    "evaluation_authority",
    "approved_by",
    "approved_at",
    "formal_product_owner_approval",
    "tickers",
)
_REQUIRED_TICKER_KEYS = (
    "structural_expectations",
    "run_bound_expectations",
    "required_conflicts",
    "conditional_conflicts",
    "product_decision_pending",
    "remove_while_undeclared",
    "allowed_conflicts",
)
# The categories A4 may ever treat as an executable, canonical-taxonomy
# expectation -- product_decision_pending and remove_while_undeclared are
# deliberately excluded (their entire purpose is to hold a pair the
# taxonomy does not declare).
_EXECUTABLE_CONFLICT_CATEGORIES = ("required_conflicts", "conditional_conflicts", "allowed_conflicts")
_ALL_CONFLICT_CATEGORIES = (
    "required_conflicts",
    "conditional_conflicts",
    "allowed_conflicts",
    "remove_while_undeclared",
)
_RUN_BOUND_REQUIRED_KEYS = (
    "reference_run_id",
    "analysis_date",
    "taxonomy_version",
    "b1_stance_source",
    "b1_stance_version",
    "artifact_completeness_required",
)


class LabelV2ValidationError(Exception):
    """A structural/vocabulary/mutual-exclusivity violation in the v0.2
    label file itself -- never raised for a provisional-vs-detected
    mismatch (that is an evaluation result, reported by the evaluator)."""

    def __init__(self, reason_code: str, detail: str = "") -> None:
        self.reason_code = reason_code
        self.detail = detail
        super().__init__(f"{reason_code}: {detail}" if detail else reason_code)


def _as_pair_list(value: Any) -> list[str]:
    return [str(v) for v in value] if isinstance(value, list) else []


def _validate_conflict_pair_format(pair: Any, *, ticker: str, category: str) -> tuple[str, str]:
    if not isinstance(pair, str) or not _CONFLICT_PAIR_PATTERN.match(pair):
        raise LabelV2ValidationError("LABEL_V2_MALFORMED_CONFLICT_PAIR", f"{ticker}.{category}: {pair!r}")
    half_a, half_b = pair.split("__", 1)
    return half_a, half_b


def _validate_top_level(raw: dict[str, Any]) -> None:
    for key in _REQUIRED_TOP_LEVEL_KEYS:
        if key not in raw:
            raise LabelV2ValidationError("LABEL_V2_MISSING_REQUIRED_FIELD", key)
    if raw["schema_version"] != SCHEMA_VERSION_V2:
        raise LabelV2ValidationError("LABEL_V2_SCHEMA_VERSION_MISMATCH", str(raw["schema_version"]))
    if raw["evaluation_mode"] not in _VALID_EVALUATION_MODES:
        raise LabelV2ValidationError("LABEL_V2_INVALID_EVALUATION_MODE", str(raw["evaluation_mode"]))
    if raw["formal_product_owner_approval"] not in _VALID_APPROVAL_STATES:
        raise LabelV2ValidationError("LABEL_V2_INVALID_APPROVAL_STATE", str(raw["formal_product_owner_approval"]))
    claims_authoritative = (
        raw["evaluation_mode"] == "authoritative" or raw["formal_product_owner_approval"] == "approved"
    )
    fully_approved = (
        raw["evaluation_mode"] == "authoritative"
        and raw["formal_product_owner_approval"] == "approved"
        and raw.get("approved_by")
        and raw.get("approved_at")
    )
    if claims_authoritative and not fully_approved:
        raise LabelV2ValidationError("LABEL_V2_AUTHORITATIVE_CLAIM_MISSING_APPROVAL_PROVENANCE")
    if not isinstance(raw["tickers"], dict) or not raw["tickers"]:
        raise LabelV2ValidationError("LABEL_V2_NO_TICKERS_DECLARED")


def _validate_run_bound_expectations(ticker: str, run_bound: Any) -> None:
    if run_bound is None:
        return
    if not isinstance(run_bound, dict):
        raise LabelV2ValidationError("LABEL_V2_RUN_BOUND_NOT_A_MAPPING", ticker)
    for key in _RUN_BOUND_REQUIRED_KEYS:
        if key not in run_bound:
            raise LabelV2ValidationError("LABEL_V2_RUN_BOUND_MISSING_REQUIRED_FIELD", f"{ticker}.{key}")


def _validate_structural_expectations(ticker: str, block: Any, known_alpha_ids: frozenset[str]) -> None:
    if not isinstance(block, dict):
        raise LabelV2ValidationError("LABEL_V2_STRUCTURAL_EXPECTATIONS_NOT_A_MAPPING", ticker)
    for group_name in ("positive_alphas", "negative_alphas", "conditional_alphas"):
        ids = set(_as_pair_list(block.get(group_name)))
        unknown = ids - known_alpha_ids
        if unknown:
            raise LabelV2ValidationError(
                "LABEL_V2_UNKNOWN_ALPHA_ID", f"{ticker}.structural_expectations.{group_name}: {sorted(unknown)}"
            )
    positive = set(_as_pair_list(block.get("positive_alphas")))
    negative = set(_as_pair_list(block.get("negative_alphas")))
    conditional = set(_as_pair_list(block.get("conditional_alphas")))
    overlap = (positive & negative) | (positive & conditional) | (negative & conditional)
    if overlap:
        raise LabelV2ValidationError("LABEL_V2_STRUCTURAL_GROUPS_OVERLAP", f"{ticker}: {sorted(overlap)}")


def _validate_ticker_block(
    ticker: str, block: Any, *, known_alpha_ids: frozenset[str], canonical_pairs: frozenset[str]
) -> None:
    if not isinstance(block, dict):
        raise LabelV2ValidationError("LABEL_V2_TICKER_BLOCK_NOT_A_MAPPING", ticker)
    for key in _REQUIRED_TICKER_KEYS:
        if key not in block:
            raise LabelV2ValidationError("LABEL_V2_TICKER_MISSING_REQUIRED_FIELD", f"{ticker}.{key}")

    _validate_structural_expectations(ticker, block["structural_expectations"], known_alpha_ids)
    _validate_run_bound_expectations(ticker, block["run_bound_expectations"])

    pairs_by_category: dict[str, set[str]] = {}
    for category in _ALL_CONFLICT_CATEGORIES:
        pairs = _as_pair_list(block.get(category))
        validated: set[str] = set()
        for pair in pairs:
            half_a, half_b = _validate_conflict_pair_format(pair, ticker=ticker, category=category)
            if category in _EXECUTABLE_CONFLICT_CATEGORIES:
                # Task test #25: an undeclared executable pair is
                # rejected outright -- v0.2 is strict where v0.1 was
                # lenient (allow + flag), precisely because v0.2 exists
                # to move undeclared pairs OUT of the executable
                # categories in the first place.
                if pair not in canonical_pairs:
                    raise LabelV2ValidationError(
                        "LABEL_V2_UNDECLARED_EXECUTABLE_CONFLICT_PAIR", f"{ticker}.{category}: {pair!r}"
                    )
                if half_a not in known_alpha_ids or half_b not in known_alpha_ids:
                    raise LabelV2ValidationError("LABEL_V2_UNKNOWN_ALPHA_ID", f"{ticker}.{category}: {pair!r}")
            elif category == "remove_while_undeclared" and pair in canonical_pairs:
                # A label inconsistency: this pair IS canonical, so it
                # cannot legitimately be "removed while undeclared".
                raise LabelV2ValidationError(
                    "LABEL_V2_REMOVE_WHILE_UNDECLARED_IS_ACTUALLY_CANONICAL", f"{ticker}: {pair!r}"
                )
            validated.add(pair)
        pairs_by_category[category] = validated

    # product_decision_pending: structural format only (never required to
    # be canonical -- that is exactly what "pending" means), and its own
    # pair_ids also participate in the mutual-exclusivity check below.
    pending_entries = block.get("product_decision_pending") or ()
    pending_pair_ids: set[str] = set()
    for entry in pending_entries:
        if not isinstance(entry, dict) or "pair_id" not in entry or "reason" not in entry:
            raise LabelV2ValidationError("LABEL_V2_MALFORMED_PENDING_ENTRY", f"{ticker}: {entry!r}")
        pair_id = entry["pair_id"]
        _validate_conflict_pair_format(pair_id, ticker=ticker, category="product_decision_pending")
        pending_pair_ids.add(pair_id)
    pairs_by_category["product_decision_pending"] = pending_pair_ids

    # Task test #20: required/conditional/pending/remove/allowed are
    # mutually exclusive per ticker -- the same pair must never appear in
    # more than one category, which would leave its evaluation status
    # ambiguous.
    seen: dict[str, str] = {}
    for category, pairs in pairs_by_category.items():
        for pair in pairs:
            if pair in seen:
                raise LabelV2ValidationError(
                    "LABEL_V2_PAIR_IN_MULTIPLE_CATEGORIES", f"{ticker}: {pair!r} in both {seen[pair]!r} and {category!r}"
                )
            seen[pair] = category


def load_j2_labels_v2(path: str | Path | None = None) -> dict[str, Any]:
    """Loads and structurally validates the J2 v0.2 label file. Raises
    :class:`LabelV2ValidationError` for any structural/vocabulary/mutual-
    exclusivity violation. Never reads an environment variable to alter
    ``evaluation_mode``/``formal_product_owner_approval``/``approved_by``."""
    import yaml

    resolved_path = Path(path) if path is not None else DEFAULT_LABEL_V2_PATH
    if not resolved_path.exists():
        raise LabelV2ValidationError("LABEL_V2_FILE_NOT_FOUND", str(resolved_path))
    try:
        raw = yaml.safe_load(resolved_path.read_text(encoding="utf-8"))
    except yaml.YAMLError as exc:
        raise LabelV2ValidationError("LABEL_V2_FILE_MALFORMED_YAML", str(exc)) from exc
    if not isinstance(raw, dict):
        raise LabelV2ValidationError("LABEL_V2_FILE_NOT_A_MAPPING")

    _validate_top_level(raw)

    taxonomy = load_alpha_taxonomy()
    known_alpha_ids = frozenset(taxonomy.keys())
    canonical_pairs = _canonical_conflict_pairs(taxonomy)

    for ticker, block in raw["tickers"].items():
        _validate_ticker_block(
            str(ticker), block, known_alpha_ids=known_alpha_ids, canonical_pairs=canonical_pairs
        )

    raw["canonical_conflict_pairs"] = sorted(canonical_pairs)
    raw["source_path"] = str(resolved_path)
    return raw


def ticker_label_v2(labels: dict[str, Any], ticker: str) -> dict[str, Any] | None:
    tickers = labels.get("tickers")
    if not isinstance(tickers, dict):
        return None
    block = tickers.get(str(ticker).upper())
    return block if isinstance(block, dict) else None


__all__ = [
    "SCHEMA_VERSION_V2",
    "DEFAULT_LABEL_V2_PATH",
    "LabelV2ValidationError",
    "load_j2_labels_v2",
    "ticker_label_v2",
]
