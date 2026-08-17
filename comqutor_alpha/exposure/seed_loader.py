"""Strict loader and fail-closed lifecycle gate for Entity Alpha Exposure
seeds (task B3_ENTITY_EXPOSURE_GATED_STATES).

Lifecycle status is per-ticker, not a single global manifest value: one
seed file can legitimately hold ``NVDA: approved_gating`` and
``GOOGL: draft_shadow`` at the same time. The three canonical values --
``draft_shadow`` / ``approved_gating`` / ``disabled`` -- are the product
authority; the pre-existing internal ``off``/``shadow``/``enforced``
vocabulary ``exposure_engine.compute_run_entity_alpha_exposures`` already
branches on is kept unchanged beneath a deterministic mapping
(:data:`LEGACY_MODE_BY_STATUS`), so that function's own qualification-
ceiling logic required zero changes for this upgrade.
"""

from __future__ import annotations

import hashlib
import os
import re
from collections.abc import Mapping
from dataclasses import dataclass
from pathlib import Path
from types import MappingProxyType
from typing import Any

import yaml

from comqutor_alpha.alpha_library.alpha_loader import EXPECTED_ALPHA_IDS

SEED_FILE_MISSING = "SEED_FILE_MISSING"
SEED_HASH_MISMATCH = "SEED_HASH_MISMATCH"
SEED_VALUE_OUT_OF_RANGE = "SEED_VALUE_OUT_OF_RANGE"
UNKNOWN_ALPHA_ID = "UNKNOWN_ALPHA_ID"
SEED_ENTRY_MISSING = "SEED_ENTRY_MISSING"
INVALID_TICKER_FORMAT = "INVALID_TICKER_FORMAT"
INVALID_LIFECYCLE_STATUS = "INVALID_LIFECYCLE_STATUS"

# Fail-closed gating-eligibility reason codes (task section 7). Emitted by
# resolve_exposure_mode, never by the loader -- an approved_gating ticker
# missing approval metadata still LOADS successfully (it may legitimately
# still be displayed in shadow); only the GATING decision fails closed.
APPROVAL_METADATA_INCOMPLETE = "APPROVAL_METADATA_INCOMPLETE"
GATING_NOT_ALLOWED = "GATING_NOT_ALLOWED"
TICKER_SEED_NOT_CONFIGURED = "TICKER_SEED_NOT_CONFIGURED"
REQUESTED_UPGRADE_IGNORED = "REQUESTED_UPGRADE_IGNORED"
REQUESTED_STATUS_DOWNGRADE = "REQUESTED_STATUS_DOWNGRADE"

# Backward-compatible aliases: several existing call sites/tests import
# these two legacy names for what is now expressed by
# APPROVAL_METADATA_INCOMPLETE/GATING_NOT_ALLOWED together. Same reason a
# ticker fails closed, kept so nothing importing the old names breaks.
SEED_NOT_APPROVED = APPROVAL_METADATA_INCOMPLETE
ENFORCEMENT_NOT_ALLOWED = GATING_NOT_ALLOWED

# John's canonical lifecycle vocabulary (task section 5/7) -- the product
# authority. draft_shadow is the safe default for any ticker not present in
# the seed file at all, or whose configured status cannot be trusted.
DRAFT_SHADOW = "draft_shadow"
APPROVED_GATING = "approved_gating"
DISABLED = "disabled"
CANONICAL_STATUSES = frozenset({DRAFT_SHADOW, APPROVED_GATING, DISABLED})
DEFAULT_STATUS = DRAFT_SHADOW

# Deterministic mapping to/from the pre-existing internal mode vocabulary
# (task section 7: "如果为兼容性继续保留旧内部模式，可以进行确定性映射").
# compute_run_entity_alpha_exposures branches on effective_mode alone and
# is otherwise unmodified by this task.
LEGACY_MODE_BY_STATUS = {
    DRAFT_SHADOW: "shadow",
    APPROVED_GATING: "enforced",
    DISABLED: "off",
}
STATUS_BY_LEGACY_MODE = {mode: status for status, mode in LEGACY_MODE_BY_STATUS.items()}

# Rank used only to decide whether a requested override is a safe
# downgrade (allowed) or an upgrade (never allowed -- task section 7:
# "draft_shadow 永远不能被环境变量升级成 approved_gating; disabled 永远不能
# 被环境变量重新启用; approved_gating 可以被安全开关降级或全局关闭").
_STATUS_RANK = {DISABLED: 0, DRAFT_SHADOW: 1, APPROVED_GATING: 2}

REQUIRED_APPROVAL_FIELDS = ("seed_version", "owner", "approved_by", "approved_at")

_TICKER_FORMAT = re.compile(r"^[A-Z][A-Z0-9.]{0,9}$")

_PACKAGE_ROOT = Path(__file__).resolve().parents[1]
_REPO_ROOT = _PACKAGE_ROOT.parent
DEFAULT_SEED_PATH = _PACKAGE_ROOT / "config" / "entity_alpha_exposure_seed_v0.1.yaml"
DEFAULT_MANIFEST_PATH = _PACKAGE_ROOT / "config" / "entity_alpha_exposure_seed_manifest_v0.1.yaml"
DEFAULT_REVIEW_PATH = _REPO_ROOT / "docs" / "entity_alpha_exposure_seed_review_v0.1.csv"
DEFAULT_METHODOLOGY_PATH = _REPO_ROOT / "docs" / "entity_alpha_exposure_methodology_v0.1.md"

# Legacy env var (pre-existing, off/shadow/enforced vocabulary) -- still
# honored as a downgrade-only override, mapped through the table above.
LEGACY_MODE_ENV_VAR = "COMQUTOR_ENTITY_EXPOSURE_MODE"
# New canonical-vocabulary env var, checked first when set.
STATUS_ENV_VAR = "COMQUTOR_ENTITY_EXPOSURE_STATUS"


class ExposureSeedError(Exception):
    """Safe seed-contract failure carrying only a stable reason code."""

    def __init__(self, reason_code: str) -> None:
        self.reason_code = reason_code
        super().__init__(reason_code)


def _sha256(path: Path) -> str:
    try:
        return hashlib.sha256(path.read_bytes()).hexdigest()
    except (FileNotFoundError, OSError) as exc:
        raise ExposureSeedError(SEED_FILE_MISSING) from exc


def _load_yaml(path: Path) -> Any:
    try:
        return yaml.safe_load(path.read_text(encoding="utf-8"))
    except FileNotFoundError as exc:
        raise ExposureSeedError(SEED_FILE_MISSING) from exc
    except (OSError, UnicodeError, yaml.YAMLError) as exc:
        raise ExposureSeedError(SEED_FILE_MISSING) from exc


def _optional_text(value: Any) -> str | None:
    if value is None:
        return None
    if not isinstance(value, str) or not value.strip():
        raise ExposureSeedError(INVALID_LIFECYCLE_STATUS)
    return value


@dataclass(frozen=True)
class TickerSeedLifecycle:
    """Per-ticker lifecycle metadata -- the product authority for this
    ticker's gating eligibility. Never a global/file-wide value."""

    ticker: str
    seed_version: str | None
    owner: str | None
    approved_by: str | None
    approved_at: str | None
    configured_status: str

    def missing_approval_fields(self) -> tuple[str, ...]:
        values = {
            "seed_version": self.seed_version,
            "owner": self.owner,
            "approved_by": self.approved_by,
            "approved_at": self.approved_at,
        }
        return tuple(name for name in REQUIRED_APPROVAL_FIELDS if not values[name])

    def to_dict(self) -> dict[str, Any]:
        return {
            "ticker": self.ticker,
            "seed_version": self.seed_version,
            "owner": self.owner,
            "approved_by": self.approved_by,
            "approved_at": self.approved_at,
            "configured_status": self.configured_status,
        }


def _parse_ticker_block(raw_ticker: Any, raw_block: Any) -> tuple[str, TickerSeedLifecycle, Mapping[str, float]]:
    if not isinstance(raw_ticker, str) or not raw_ticker.strip():
        raise ExposureSeedError(INVALID_TICKER_FORMAT)
    ticker = raw_ticker.strip().upper()
    if not _TICKER_FORMAT.match(ticker):
        raise ExposureSeedError(INVALID_TICKER_FORMAT)
    if not isinstance(raw_block, Mapping):
        raise ExposureSeedError(UNKNOWN_ALPHA_ID)

    status = raw_block.get("status")
    if not isinstance(status, str) or status not in CANONICAL_STATUSES:
        raise ExposureSeedError(INVALID_LIFECYCLE_STATUS)

    lifecycle = TickerSeedLifecycle(
        ticker=ticker,
        seed_version=_optional_text(raw_block.get("seed_version")),
        owner=_optional_text(raw_block.get("owner")),
        approved_by=_optional_text(raw_block.get("approved_by")),
        approved_at=_optional_text(raw_block.get("approved_at")),
        configured_status=status,
    )

    raw_exposures = raw_block.get("exposures")
    if not isinstance(raw_exposures, Mapping):
        raise ExposureSeedError(UNKNOWN_ALPHA_ID)
    valid_alpha_ids = set(EXPECTED_ALPHA_IDS)
    row: dict[str, float] = {}
    for raw_alpha_id in sorted(raw_exposures):
        alpha_id = str(raw_alpha_id or "").strip()
        if alpha_id not in valid_alpha_ids:
            raise ExposureSeedError(UNKNOWN_ALPHA_ID)
        value = raw_exposures[raw_alpha_id]
        if isinstance(value, bool) or not isinstance(value, (int, float)):
            raise ExposureSeedError(SEED_VALUE_OUT_OF_RANGE)
        number = float(value)
        if not 0.0 <= number <= 1.0:
            raise ExposureSeedError(SEED_VALUE_OUT_OF_RANGE)
        row[alpha_id] = number

    return ticker, lifecycle, MappingProxyType(row)


def _freeze_seed(
    raw_seed: Mapping[str, Any],
) -> tuple[Mapping[str, Mapping[str, float]], Mapping[str, TickerSeedLifecycle]]:
    values: dict[str, Mapping[str, float]] = {}
    lifecycle: dict[str, TickerSeedLifecycle] = {}
    for raw_ticker in sorted(raw_seed, key=lambda item: str(item)):
        ticker, ticker_lifecycle, row = _parse_ticker_block(raw_ticker, raw_seed[raw_ticker])
        if ticker in values:
            raise ExposureSeedError(INVALID_TICKER_FORMAT)
        values[ticker] = row
        lifecycle[ticker] = ticker_lifecycle
    return MappingProxyType(values), MappingProxyType(lifecycle)


@dataclass(frozen=True)
class ExposureSeedManifest:
    """File-level identity/integrity only -- no approval status. See
    TickerSeedLifecycle for the per-ticker product authority."""

    schema_version: str
    methodology_version: str
    seed_sha256: str
    review_csv_sha256: str
    methodology_sha256: str

    def to_dict(self) -> dict[str, Any]:
        return {
            "schema_version": self.schema_version,
            "methodology_version": self.methodology_version,
            "seed_sha256": self.seed_sha256,
            "review_csv_sha256": self.review_csv_sha256,
            "methodology_sha256": self.methodology_sha256,
        }


@dataclass(frozen=True)
class ExposureSeedBundle:
    manifest: ExposureSeedManifest
    values: Mapping[str, Mapping[str, float]]
    lifecycle: Mapping[str, TickerSeedLifecycle]

    def historical_mapping(self, ticker: str, alpha_id: str) -> float | None:
        row = self.values.get(str(ticker or "").upper())
        return None if row is None else row.get(alpha_id)

    def ticker_lifecycle(self, ticker: str) -> TickerSeedLifecycle | None:
        return self.lifecycle.get(str(ticker or "").upper())


@dataclass(frozen=True)
class ExposureModeDecision:
    """Per-ticker lifecycle resolution result.

    ``requested_mode``/``effective_mode`` keep the pre-existing internal
    off/shadow/enforced vocabulary byte-for-byte (so
    ``compute_run_entity_alpha_exposures`` needed no changes to its own
    branching); ``configured_status``/``effective_status`` are John's
    canonical vocabulary and are what artifacts/API/UI should read.
    """

    ticker: str
    requested_mode: str
    effective_mode: str
    configured_status: str
    effective_status: str
    reason_codes: tuple[str, ...]
    allow_draft_enforcement: bool = False


def load_exposure_seed(
    seed_path: str | Path = DEFAULT_SEED_PATH,
    manifest_path: str | Path = DEFAULT_MANIFEST_PATH,
    *,
    review_path: str | Path = DEFAULT_REVIEW_PATH,
    methodology_path: str | Path = DEFAULT_METHODOLOGY_PATH,
) -> ExposureSeedBundle:
    """Load the exact versioned seed after validating hashes and domains."""
    seed_path = Path(seed_path)
    manifest_path = Path(manifest_path)
    review_path = Path(review_path)
    methodology_path = Path(methodology_path)
    raw_manifest = _load_yaml(manifest_path)
    if not isinstance(raw_manifest, Mapping):
        raise ExposureSeedError(SEED_FILE_MISSING)

    expected_hashes = {
        seed_path: str(raw_manifest.get("seed_sha256") or ""),
        review_path: str(raw_manifest.get("review_csv_sha256") or ""),
        methodology_path: str(raw_manifest.get("methodology_sha256") or ""),
    }
    if any(not expected or _sha256(path) != expected for path, expected in expected_hashes.items()):
        raise ExposureSeedError(SEED_HASH_MISMATCH)

    raw_seed = _load_yaml(seed_path)
    if not isinstance(raw_seed, Mapping):
        raise ExposureSeedError(SEED_FILE_MISSING)

    manifest = ExposureSeedManifest(
        schema_version=str(raw_manifest.get("schema_version") or ""),
        methodology_version=str(raw_manifest.get("methodology_version") or ""),
        seed_sha256=str(raw_manifest.get("seed_sha256") or ""),
        review_csv_sha256=str(raw_manifest.get("review_csv_sha256") or ""),
        methodology_sha256=str(raw_manifest.get("methodology_sha256") or ""),
    )
    values, lifecycle = _freeze_seed(raw_seed)
    return ExposureSeedBundle(manifest=manifest, values=values, lifecycle=lifecycle)


def _requested_status_override(requested_status: str | None) -> tuple[str | None, str]:
    """Resolve the requested override, in priority order: explicit param,
    then the new canonical-vocabulary env var, then the legacy off/shadow/
    enforced env var (mapped). Returns (status_or_None, source_label)."""
    if requested_status is not None:
        status = str(requested_status).strip().lower()
        if status not in CANONICAL_STATUSES:
            raise ValueError("INVALID_ENTITY_EXPOSURE_STATUS")
        return status, "param"

    env_status = os.getenv(STATUS_ENV_VAR)
    if env_status:
        status = env_status.strip().lower()
        if status not in CANONICAL_STATUSES:
            raise ValueError("INVALID_ENTITY_EXPOSURE_STATUS")
        return status, "status_env"

    env_mode = os.getenv(LEGACY_MODE_ENV_VAR)
    if env_mode:
        mode = env_mode.strip().lower()
        if mode not in STATUS_BY_LEGACY_MODE:
            raise ValueError("INVALID_ENTITY_EXPOSURE_MODE")
        return STATUS_BY_LEGACY_MODE[mode], "mode_env"

    return None, "none"


def resolve_exposure_mode(
    bundle: ExposureSeedBundle,
    ticker: str,
    requested_status: str | None = None,
    *,
    allow_draft_enforcement: bool | None = None,
) -> ExposureModeDecision:
    """Resolve one ticker's effective lifecycle status, fail-closed.

    Status lifecycle authority is per-ticker (``bundle.lifecycle``), never
    a single global manifest value. A ticker absent from the seed entirely
    defaults to ``draft_shadow`` (safe: every Alpha will show
    ``missing_seed`` via the existing per-Alpha pathway, never silently
    zeroed). ``approved_gating`` additionally requires all four approval
    fields to be present -- missing any one fails closed to
    ``draft_shadow`` with a stable reason code, never a silent gate.
    A requested override (explicit param, or either env var) may only ever
    DOWNGRADE the configured status (task section 7); an attempted upgrade
    is ignored, not applied, and is itself recorded as a reason code for
    auditability.
    """
    safe_ticker = str(ticker or "").upper()
    lifecycle = bundle.ticker_lifecycle(safe_ticker)
    reasons: list[str] = []

    if lifecycle is None:
        configured_status = DEFAULT_STATUS
        reasons.append(TICKER_SEED_NOT_CONFIGURED)
    else:
        configured_status = lifecycle.configured_status

    effective_status = configured_status
    if effective_status == APPROVED_GATING:
        missing = lifecycle.missing_approval_fields() if lifecycle is not None else REQUIRED_APPROVAL_FIELDS
        if missing:
            effective_status = DRAFT_SHADOW
            reasons.extend([APPROVAL_METADATA_INCOMPLETE, GATING_NOT_ALLOWED])

    requested, _source = _requested_status_override(requested_status)
    if allow_draft_enforcement is None:
        allow_draft_enforcement = os.getenv(
            "COMQUTOR_ALLOW_DRAFT_EXPOSURE_ENFORCEMENT", "false"
        ).strip().lower() in {"1", "true", "yes", "on"}
    # The opt-in variable is recorded for operational visibility only -- it
    # never overrides the fail-closed approval check above, matching the
    # pre-existing "never a silent upgrade" guarantee.

    if requested is not None:
        if _STATUS_RANK[requested] < _STATUS_RANK[effective_status]:
            effective_status = requested
            reasons.append(REQUESTED_STATUS_DOWNGRADE)
        elif _STATUS_RANK[requested] > _STATUS_RANK[effective_status]:
            reasons.append(REQUESTED_UPGRADE_IGNORED)

    effective_mode = LEGACY_MODE_BY_STATUS[effective_status]
    requested_mode = LEGACY_MODE_BY_STATUS[requested] if requested is not None else effective_mode

    return ExposureModeDecision(
        ticker=safe_ticker,
        requested_mode=requested_mode,
        effective_mode=effective_mode,
        configured_status=configured_status,
        effective_status=effective_status,
        reason_codes=tuple(reasons),
        allow_draft_enforcement=bool(allow_draft_enforcement),
    )


__all__ = [
    "APPROVAL_METADATA_INCOMPLETE",
    "APPROVED_GATING",
    "CANONICAL_STATUSES",
    "DEFAULT_STATUS",
    "DEFAULT_MANIFEST_PATH",
    "DEFAULT_METHODOLOGY_PATH",
    "DEFAULT_REVIEW_PATH",
    "DEFAULT_SEED_PATH",
    "DISABLED",
    "DRAFT_SHADOW",
    "ENFORCEMENT_NOT_ALLOWED",
    "GATING_NOT_ALLOWED",
    "INVALID_LIFECYCLE_STATUS",
    "INVALID_TICKER_FORMAT",
    "LEGACY_MODE_BY_STATUS",
    "REQUESTED_STATUS_DOWNGRADE",
    "REQUESTED_UPGRADE_IGNORED",
    "REQUIRED_APPROVAL_FIELDS",
    "ExposureModeDecision",
    "ExposureSeedBundle",
    "ExposureSeedError",
    "ExposureSeedManifest",
    "SEED_ENTRY_MISSING",
    "SEED_FILE_MISSING",
    "SEED_HASH_MISMATCH",
    "SEED_NOT_APPROVED",
    "SEED_VALUE_OUT_OF_RANGE",
    "STATUS_BY_LEGACY_MODE",
    "TICKER_SEED_NOT_CONFIGURED",
    "TickerSeedLifecycle",
    "UNKNOWN_ALPHA_ID",
    "load_exposure_seed",
    "resolve_exposure_mode",
]
