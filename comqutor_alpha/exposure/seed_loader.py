"""Strict loader and enforcement gate for Entity Alpha Exposure seeds."""

from __future__ import annotations

import hashlib
import os
from collections.abc import Mapping
from dataclasses import dataclass
from datetime import date
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
SEED_NOT_APPROVED = "SEED_NOT_APPROVED"
ENFORCEMENT_NOT_ALLOWED = "ENFORCEMENT_NOT_ALLOWED"

VALID_EXPOSURE_MODES = frozenset({"off", "shadow", "enforced"})
DEFAULT_EXPOSURE_MODE = "shadow"

_PACKAGE_ROOT = Path(__file__).resolve().parents[1]
_REPO_ROOT = _PACKAGE_ROOT.parent
DEFAULT_SEED_PATH = _PACKAGE_ROOT / "config" / "entity_alpha_exposure_seed_v0.1.yaml"
DEFAULT_MANIFEST_PATH = _PACKAGE_ROOT / "config" / "entity_alpha_exposure_seed_manifest_v0.1.yaml"
DEFAULT_REVIEW_PATH = _REPO_ROOT / "docs" / "entity_alpha_exposure_seed_review_v0.1.csv"
DEFAULT_METHODOLOGY_PATH = _REPO_ROOT / "docs" / "entity_alpha_exposure_methodology_v0.1.md"


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


def _manifest_date(value: Any) -> str:
    if isinstance(value, date):
        return value.isoformat()
    text = str(value or "").strip()
    return text


def _strict_bool(value: Any) -> bool:
    return value is True


def _freeze_seed(raw_seed: Mapping[str, Any], allowed_tickers: set[str]) -> Mapping[str, Mapping[str, float]]:
    frozen: dict[str, Mapping[str, float]] = {}
    valid_alpha_ids = set(EXPECTED_ALPHA_IDS)
    for raw_ticker in sorted(raw_seed):
        ticker = str(raw_ticker or "").strip().upper()
        values = raw_seed[raw_ticker]
        if not ticker or ticker not in allowed_tickers or not isinstance(values, Mapping):
            raise ExposureSeedError(UNKNOWN_ALPHA_ID)
        row: dict[str, float] = {}
        for raw_alpha_id in sorted(values):
            alpha_id = str(raw_alpha_id or "").strip()
            if alpha_id not in valid_alpha_ids:
                raise ExposureSeedError(UNKNOWN_ALPHA_ID)
            value = values[raw_alpha_id]
            if isinstance(value, bool) or not isinstance(value, (int, float)):
                raise ExposureSeedError(SEED_VALUE_OUT_OF_RANGE)
            number = float(value)
            if not 0.0 <= number <= 1.0:
                raise ExposureSeedError(SEED_VALUE_OUT_OF_RANGE)
            row[alpha_id] = number
        frozen[ticker] = MappingProxyType(row)
    return MappingProxyType(frozen)


@dataclass(frozen=True)
class ExposureSeedManifest:
    schema_version: str
    seed_version: str
    methodology_version: str
    effective_date: str
    approval_status: str
    approved_by: str | None
    enforcement_allowed: bool
    seed_sha256: str
    review_csv_sha256: str
    methodology_sha256: str
    formal_plan_tickers: tuple[str, ...]
    extension_tickers: tuple[str, ...]

    def to_dict(self) -> dict[str, Any]:
        return {
            "schema_version": self.schema_version,
            "seed_version": self.seed_version,
            "methodology_version": self.methodology_version,
            "effective_date": self.effective_date,
            "approval_status": self.approval_status,
            "approved_by": self.approved_by,
            "enforcement_allowed": self.enforcement_allowed,
            "seed_sha256": self.seed_sha256,
            "review_csv_sha256": self.review_csv_sha256,
            "methodology_sha256": self.methodology_sha256,
            "formal_plan_tickers": list(self.formal_plan_tickers),
            "extension_tickers": list(self.extension_tickers),
        }


@dataclass(frozen=True)
class ExposureSeedBundle:
    manifest: ExposureSeedManifest
    values: Mapping[str, Mapping[str, float]]

    def historical_mapping(self, ticker: str, alpha_id: str) -> float | None:
        row = self.values.get(str(ticker or "").upper())
        return None if row is None else row.get(alpha_id)


@dataclass(frozen=True)
class ExposureModeDecision:
    requested_mode: str
    effective_mode: str
    reason_codes: tuple[str, ...]
    allow_draft_enforcement: bool


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

    formal = tuple(str(item).upper() for item in (raw_manifest.get("formal_plan_tickers") or ()))
    extensions = tuple(str(item).upper() for item in (raw_manifest.get("extension_tickers") or ()))
    raw_seed = _load_yaml(seed_path)
    if not isinstance(raw_seed, Mapping):
        raise ExposureSeedError(SEED_FILE_MISSING)

    manifest = ExposureSeedManifest(
        schema_version=str(raw_manifest.get("schema_version") or ""),
        seed_version=str(raw_manifest.get("seed_version") or ""),
        methodology_version=str(raw_manifest.get("methodology_version") or ""),
        effective_date=_manifest_date(raw_manifest.get("effective_date")),
        approval_status=str(raw_manifest.get("approval_status") or ""),
        approved_by=(
            str(raw_manifest["approved_by"]) if raw_manifest.get("approved_by") is not None else None
        ),
        enforcement_allowed=_strict_bool(raw_manifest.get("enforcement_allowed")),
        seed_sha256=str(raw_manifest.get("seed_sha256") or ""),
        review_csv_sha256=str(raw_manifest.get("review_csv_sha256") or ""),
        methodology_sha256=str(raw_manifest.get("methodology_sha256") or ""),
        formal_plan_tickers=formal,
        extension_tickers=extensions,
    )
    values = _freeze_seed(raw_seed, set(formal) | set(extensions))
    return ExposureSeedBundle(manifest=manifest, values=values)


def resolve_exposure_mode(
    manifest: ExposureSeedManifest,
    requested_mode: str | None = None,
    *,
    allow_draft_enforcement: bool | None = None,
) -> ExposureModeDecision:
    """Resolve off/shadow/enforced without ever silently enforcing a draft."""
    requested = str(
        requested_mode if requested_mode is not None else os.getenv("COMQUTOR_ENTITY_EXPOSURE_MODE", DEFAULT_EXPOSURE_MODE)
    ).strip().lower()
    if requested not in VALID_EXPOSURE_MODES:
        raise ValueError("INVALID_ENTITY_EXPOSURE_MODE")
    if allow_draft_enforcement is None:
        allow_draft_enforcement = os.getenv(
            "COMQUTOR_ALLOW_DRAFT_EXPOSURE_ENFORCEMENT", "false"
        ).strip().lower() in {"1", "true", "yes", "on"}

    reasons: list[str] = []
    effective = requested
    if requested == "enforced":
        if manifest.approval_status != "approved":
            reasons.append(SEED_NOT_APPROVED)
        if not manifest.enforcement_allowed:
            reasons.append(ENFORCEMENT_NOT_ALLOWED)
        # The opt-in variable is recorded for operational visibility, but it
        # never overrides either signed-manifest gate.
        if reasons:
            effective = "shadow"
    return ExposureModeDecision(
        requested_mode=requested,
        effective_mode=effective,
        reason_codes=tuple(reasons),
        allow_draft_enforcement=bool(allow_draft_enforcement),
    )


__all__ = [
    "DEFAULT_EXPOSURE_MODE",
    "DEFAULT_MANIFEST_PATH",
    "DEFAULT_METHODOLOGY_PATH",
    "DEFAULT_REVIEW_PATH",
    "DEFAULT_SEED_PATH",
    "ENFORCEMENT_NOT_ALLOWED",
    "ExposureModeDecision",
    "ExposureSeedBundle",
    "ExposureSeedError",
    "ExposureSeedManifest",
    "SEED_ENTRY_MISSING",
    "SEED_FILE_MISSING",
    "SEED_HASH_MISMATCH",
    "SEED_NOT_APPROVED",
    "SEED_VALUE_OUT_OF_RANGE",
    "UNKNOWN_ALPHA_ID",
    "load_exposure_seed",
    "resolve_exposure_mode",
]
