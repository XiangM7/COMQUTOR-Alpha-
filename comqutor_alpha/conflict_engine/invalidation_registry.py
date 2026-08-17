"""Alpha Invalidation Conditions registry (task B5_CONFLICT_RADAR_EVIDENCE_UI,
sections 8-10).

Product content ("what would invalidate this Alpha's thesis?"), never a
deterministic count and never LLM-generated. This module only loads and
looks up an already-versioned, already-approved YAML file -- it never
invents, drafts, or upgrades an Alpha's approval status at runtime. An
Alpha with no entry in the registry (or an entry not marked
``approval_status: approved``) is reported honestly as ``not_defined`` with
an empty ``conditions`` list -- never silently populated with a guess.

Deliberately separate from ``alpha_library.alpha_loader``/
``alpha_taxonomy_v1.yaml``: that taxonomy's own ``invalidation_conditions``
field is older, unversioned, and carries no explicit source/approval
metadata -- it predates this registry and is not treated as a formal
Product Owner approval source here (see the B5 report's
``NON_AUTHORITATIVE_DRAFT_PROPOSALS`` section). This module never reads or
writes the taxonomy file.
"""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import yaml

INVALIDATION_REGISTRY_SCHEMA_VERSION = "alpha_invalidation_conditions.v1"

_PACKAGE_ROOT = Path(__file__).resolve().parents[1]
DEFAULT_INVALIDATION_REGISTRY_PATH = (
    _PACKAGE_ROOT / "config" / "alpha_invalidation_conditions_v0.1.yaml"
)

APPROVED = "approved"
NOT_DEFINED = "not_defined"
VALID_APPROVAL_STATUSES = frozenset({APPROVED, NOT_DEFINED})


class InvalidationRegistryError(Exception):
    """Safe input-contract violation: carries a stable reason code only."""

    def __init__(self, reason_code: str) -> None:
        self.reason_code = reason_code
        super().__init__(reason_code)


@dataclass(frozen=True)
class InvalidationCondition:
    condition_id: str
    condition_text: str

    def to_dict(self) -> dict[str, Any]:
        return {"condition_id": self.condition_id, "condition_text": self.condition_text}


@dataclass(frozen=True)
class AlphaInvalidationEntry:
    alpha_id: str
    alpha_name: str | None
    approval_status: str
    source: str | None
    version: str | None
    conditions: tuple[InvalidationCondition, ...]

    def to_dict(self) -> dict[str, Any]:
        return {
            "alpha_id": self.alpha_id,
            "alpha_name": self.alpha_name,
            "approval_status": self.approval_status,
            "source": self.source,
            "version": self.version,
            "conditions": [c.to_dict() for c in self.conditions],
        }


def _not_defined(alpha_id: str, alpha_name: str | None = None) -> AlphaInvalidationEntry:
    return AlphaInvalidationEntry(
        alpha_id=alpha_id,
        alpha_name=alpha_name,
        approval_status=NOT_DEFINED,
        source=None,
        version=None,
        conditions=(),
    )


@dataclass(frozen=True)
class InvalidationRegistry:
    schema_version: str
    entries: Mapping[str, AlphaInvalidationEntry]

    def entry_for(self, alpha_id: str, alpha_name: str | None = None) -> AlphaInvalidationEntry:
        """Never raises for an unknown alpha_id -- returns an honest
        ``not_defined`` entry instead, since "no approved content yet" is
        an expected, common, non-error state (task section 10)."""
        existing = self.entries.get(alpha_id)
        if existing is None:
            return _not_defined(alpha_id, alpha_name)
        if alpha_name is not None and existing.alpha_name is None:
            return AlphaInvalidationEntry(
                alpha_id=existing.alpha_id,
                alpha_name=alpha_name,
                approval_status=existing.approval_status,
                source=existing.source,
                version=existing.version,
                conditions=existing.conditions,
            )
        return existing


def _require_text(value: Any, reason_code: str) -> str:
    if not isinstance(value, str) or not value.strip():
        raise InvalidationRegistryError(reason_code)
    return value.strip()


def _parse_entry(alpha_id: str, raw: Mapping[str, Any]) -> AlphaInvalidationEntry:
    reason = "INVALIDATION_REGISTRY_ENTRY_INVALID"
    if not isinstance(raw, Mapping):
        raise InvalidationRegistryError(reason)
    approval_status = raw.get("approval_status")
    if approval_status not in VALID_APPROVAL_STATUSES:
        raise InvalidationRegistryError(reason)
    alpha_name = raw.get("alpha_name")
    alpha_name = str(alpha_name) if isinstance(alpha_name, str) and alpha_name.strip() else None

    if approval_status == NOT_DEFINED:
        return _not_defined(alpha_id, alpha_name)

    # approval_status == APPROVED: source/version/every condition text are
    # mandatory -- an "approved" entry with missing provenance is a
    # malformed registry, never silently downgraded to not_defined.
    source = _require_text(raw.get("source"), reason)
    version = _require_text(raw.get("version"), reason)
    raw_conditions = raw.get("conditions")
    if not isinstance(raw_conditions, list) or not raw_conditions:
        raise InvalidationRegistryError(reason)
    conditions = tuple(
        InvalidationCondition(
            condition_id=f"{alpha_id}_INV_{index + 1}",
            condition_text=_require_text(text, reason),
        )
        for index, text in enumerate(raw_conditions)
    )
    return AlphaInvalidationEntry(
        alpha_id=alpha_id,
        alpha_name=alpha_name,
        approval_status=APPROVED,
        source=source,
        version=version,
        conditions=conditions,
    )


def load_invalidation_registry(
    registry_path: str | Path = DEFAULT_INVALIDATION_REGISTRY_PATH,
) -> InvalidationRegistry:
    """Load and validate the invalidation conditions registry. Raises
    :class:`InvalidationRegistryError` for a malformed file -- never
    returns a partially-parsed or guessed result."""
    path = Path(registry_path)
    try:
        raw = yaml.safe_load(path.read_text(encoding="utf-8"))
    except FileNotFoundError as exc:
        raise InvalidationRegistryError("INVALIDATION_REGISTRY_NOT_FOUND") from exc
    except yaml.YAMLError as exc:
        raise InvalidationRegistryError("INVALIDATION_REGISTRY_MALFORMED_YAML") from exc

    if not isinstance(raw, Mapping):
        raise InvalidationRegistryError("INVALIDATION_REGISTRY_MALFORMED_YAML")
    schema_version = raw.get("schema_version")
    if schema_version != INVALIDATION_REGISTRY_SCHEMA_VERSION:
        raise InvalidationRegistryError("INVALIDATION_REGISTRY_SCHEMA_VERSION_MISMATCH")
    raw_alphas = raw.get("alphas")
    if not isinstance(raw_alphas, Mapping):
        raise InvalidationRegistryError("INVALIDATION_REGISTRY_MALFORMED_YAML")

    entries = {
        str(alpha_id): _parse_entry(str(alpha_id), raw_entry)
        for alpha_id, raw_entry in raw_alphas.items()
    }
    return InvalidationRegistry(schema_version=schema_version, entries=entries)


__all__ = [
    "APPROVED",
    "DEFAULT_INVALIDATION_REGISTRY_PATH",
    "INVALIDATION_REGISTRY_SCHEMA_VERSION",
    "NOT_DEFINED",
    "VALID_APPROVAL_STATUSES",
    "AlphaInvalidationEntry",
    "InvalidationCondition",
    "InvalidationRegistry",
    "InvalidationRegistryError",
    "load_invalidation_registry",
]
