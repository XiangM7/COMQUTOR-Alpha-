"""Configuration and safe request normalization for COMQUTOR Alpha."""

from __future__ import annotations

import hashlib
import json
import re
from dataclasses import asdict, dataclass
from datetime import date
from pathlib import Path

_TICKER_PATTERN = re.compile(r"^[A-Z0-9^][A-Z0-9.^=\-]{0,19}$")
_ASSET_TYPES = frozenset({"stock", "crypto"})


class ConfigurationError(ValueError):
    """Configuration or request data is unsafe or invalid."""


def normalize_ticker(value: str) -> str:
    normalized = value.strip().upper()
    if (
        not normalized
        or ".." in normalized
        or "/" in normalized
        or "\\" in normalized
        or not _TICKER_PATTERN.fullmatch(normalized)
    ):
        raise ConfigurationError(f"invalid ticker: {value!r}")
    return normalized


def normalize_asset_type(value: str) -> str:
    normalized = value.strip().lower()
    if normalized not in _ASSET_TYPES:
        raise ConfigurationError(f"unsupported asset_type: {value!r}")
    return normalized


def normalize_analysis_date(value: str | date) -> date:
    if isinstance(value, date):
        return value
    try:
        return date.fromisoformat(value)
    except (TypeError, ValueError) as exc:
        raise ConfigurationError(f"analysis_date must be ISO YYYY-MM-DD: {value!r}") from exc


@dataclass(frozen=True, slots=True)
class ComqutorConfig:
    output_dir: Path = Path("outputs/runs")
    llm_provider: str = "unconfigured"
    quick_model: str = "unconfigured"
    deep_model: str = "unconfigured"
    adapter_model: str = "unconfigured"

    def public_dict(self) -> dict[str, str]:
        values = asdict(self)
        values["output_dir"] = str(self.output_dir)
        return values

    def fingerprint(self) -> str:
        payload = json.dumps(self.public_dict(), sort_keys=True, separators=(",", ":"))
        return hashlib.sha256(payload.encode("utf-8")).hexdigest()
