"""Deterministic JSON serialization and SHA-256 primitives.

The accepted value domain is deliberately narrower than ``json.dumps``:
objects with string keys, lists, strings, booleans, finite integers/floats,
and null. Tuples, sets, dataclasses, bytes, Decimal, custom encoders, and
``repr`` fallbacks are rejected explicitly.
"""

from __future__ import annotations

import hashlib
import json
import math
from typing import Any

from comqutor_alpha.llm_runtime.errors import CanonicalJSONError


def _validate_json_value(value: Any, *, path: str = "$", ancestors: set[int] | None = None) -> None:
    if value is None or isinstance(value, (str, bool, int)):
        return
    if isinstance(value, float):
        if not math.isfinite(value):
            raise CanonicalJSONError(
                "CANONICAL_JSON_NON_FINITE_NUMBER",
                f"Non-finite number at {path}",
                path=path,
            )
        return

    active = ancestors if ancestors is not None else set()
    if isinstance(value, dict):
        identity = id(value)
        if identity in active:
            raise CanonicalJSONError(
                "CANONICAL_JSON_CYCLE",
                f"Circular object at {path}",
                path=path,
            )
        active.add(identity)
        try:
            for key, item in value.items():
                if not isinstance(key, str):
                    raise CanonicalJSONError(
                        "CANONICAL_JSON_NON_STRING_KEY",
                        f"Object key at {path} must be a string",
                        path=path,
                    )
                _validate_json_value(item, path=f"{path}.{key}", ancestors=active)
        finally:
            active.remove(identity)
        return

    if isinstance(value, list):
        identity = id(value)
        if identity in active:
            raise CanonicalJSONError(
                "CANONICAL_JSON_CYCLE",
                f"Circular array at {path}",
                path=path,
            )
        active.add(identity)
        try:
            for index, item in enumerate(value):
                _validate_json_value(item, path=f"{path}[{index}]", ancestors=active)
        finally:
            active.remove(identity)
        return

    raise CanonicalJSONError(
        "CANONICAL_JSON_UNSUPPORTED_TYPE",
        f"Unsupported type {type(value).__name__} at {path}",
        path=path,
    )


def canonical_json_text(value: Any) -> str:
    """Return canonical UTF-8-compatible JSON text for a supported value."""

    _validate_json_value(value)
    try:
        return json.dumps(
            value,
            ensure_ascii=False,
            sort_keys=True,
            separators=(",", ":"),
            allow_nan=False,
        )
    except (TypeError, ValueError) as exc:  # defensive: domain is pre-validated
        raise CanonicalJSONError(
            "CANONICAL_JSON_SERIALIZATION_ERROR",
            f"Canonical JSON serialization failed: {type(exc).__name__}",
        ) from exc


def canonical_json_bytes(value: Any) -> bytes:
    """Return canonical JSON encoded exactly once as UTF-8."""

    return canonical_json_text(value).encode("utf-8")


def sha256_bytes(value: bytes) -> str:
    if not isinstance(value, bytes):
        raise TypeError("sha256_bytes requires bytes")
    return hashlib.sha256(value).hexdigest()


def sha256_text(value: str) -> str:
    if not isinstance(value, str):
        raise TypeError("sha256_text requires str")
    return sha256_bytes(value.encode("utf-8"))


def sha256_canonical_json(value: Any) -> str:
    return sha256_bytes(canonical_json_bytes(value))
