"""Stable error and validation types for the offline LLM runtime foundation."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any


@dataclass(frozen=True)
class ValidationIssue:
    """One stable validation failure with an optional record path."""

    reason_code: str
    message: str
    path: str | None = None

    def to_dict(self) -> dict[str, str | None]:
        return {
            "reason_code": self.reason_code,
            "message": self.message,
            "path": self.path,
        }


@dataclass(frozen=True)
class ValidationResult:
    """Validation outcome that always carries explicit reason codes."""

    valid: bool
    issues: tuple[ValidationIssue, ...] = ()

    @property
    def reason_codes(self) -> tuple[str, ...]:
        return tuple(issue.reason_code for issue in self.issues)

    def to_dict(self) -> dict[str, Any]:
        return {
            "valid": self.valid,
            "reason_codes": list(self.reason_codes),
            "issues": [issue.to_dict() for issue in self.issues],
        }


def validation_success() -> ValidationResult:
    return ValidationResult(valid=True)


def validation_failure(*issues: ValidationIssue) -> ValidationResult:
    return ValidationResult(valid=False, issues=tuple(issues))


class LLMRuntimeError(Exception):
    """Base class with a stable machine-readable reason code."""

    def __init__(self, reason_code: str, message: str, *, path: str | None = None) -> None:
        super().__init__(message)
        self.reason_code = reason_code
        self.path = path


class CanonicalJSONError(LLMRuntimeError):
    """Raised when a value cannot enter the canonical JSON domain."""


class ContractValidationError(LLMRuntimeError):
    """Raised when a semantic-call or cache-entry contract is invalid."""

    def __init__(self, result: ValidationResult, message: str = "Contract validation failed") -> None:
        reason_code = result.reason_codes[0] if result.reason_codes else "CONTRACT_INVALID"
        super().__init__(reason_code, message)
        self.result = result


class CacheCorruptionError(LLMRuntimeError):
    """Raised when an injected cache returns malformed or tampered content."""


class RecorderIntegrityError(LLMRuntimeError):
    """Raised for JSONL corruption or append-order violations."""


class ManifestIntegrityError(LLMRuntimeError):
    """Raised when a semantic manifest cannot be built safely."""
