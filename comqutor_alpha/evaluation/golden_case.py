"""Golden Case bundle loader (Track C: Golden Case Bundle format).

A bundle lives at ``evaluation/golden_cases/<case_id>/`` and is a directory
shaped exactly like a source run directory (``raw_agent_outputs.json`` +
``metadata.json``) plus a ``case.yaml`` manifest and an ``expected.yaml``
oracle. Loading a bundle never runs the pipeline and never touches the
network -- it only validates structure and (optionally) artifact hashes.
"""

from __future__ import annotations

import hashlib
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import yaml

REQUIRED_CASE_YAML_FIELDS = (
    "case_id",
    "ticker",
    "case_type",
    "approval_status",
)
VALID_APPROVAL_STATUSES = frozenset({"draft", "reviewed", "approved", "deprecated"})
VALID_CASE_TYPES = frozenset({"frozen_golden_case", "historical_replay_case", "live_smoke_result"})
REQUIRED_BUNDLE_ARTIFACTS = ("case.yaml", "expected.yaml")


class GoldenCaseError(Exception):
    """Raised for a structurally invalid Golden Case bundle -- never a
    silent skip; the caller decides whether that's a hard failure or a
    reported ``pending_fixture``."""


@dataclass(frozen=True)
class GoldenCase:
    case_id: str
    case_dir: Path
    case_yaml: dict[str, Any]
    expected: dict[str, Any]

    @property
    def ticker(self) -> str:
        return str(self.case_yaml.get("ticker") or "")

    @property
    def case_type(self) -> str:
        return str(self.case_yaml.get("case_type") or "")

    @property
    def approval_status(self) -> str:
        return str(self.case_yaml.get("approval_status") or "draft")

    @property
    def source_run_id(self) -> str | None:
        return self.case_yaml.get("source_run_id")

    def has_frozen_raw_outputs(self) -> bool:
        return (self.case_dir / "raw_agent_outputs.json").exists()


def _sha256_file(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def verify_artifact_hashes(case: GoldenCase) -> list[str]:
    """Returns a list of mismatch descriptions (empty == all declared
    hashes match). A case with no ``artifact_hashes`` declared has nothing
    to verify -- never treated as a failure."""
    declared = case.case_yaml.get("artifact_hashes")
    if not isinstance(declared, dict):
        return []
    mismatches = []
    for filename, expected_hash in declared.items():
        path = case.case_dir / filename
        if not path.exists():
            mismatches.append(f"{filename}: declared in artifact_hashes but file is missing")
            continue
        actual_hash = _sha256_file(path)
        if actual_hash != expected_hash:
            mismatches.append(f"{filename}: hash mismatch (expected {expected_hash}, got {actual_hash})")
    return mismatches


def load_golden_case(case_dir: Path | str) -> GoldenCase:
    case_dir = Path(case_dir)
    if not case_dir.is_dir():
        raise GoldenCaseError(f"GOLDEN_CASE_DIR_NOT_FOUND: {case_dir}")

    for filename in REQUIRED_BUNDLE_ARTIFACTS:
        if not (case_dir / filename).exists():
            raise GoldenCaseError(f"GOLDEN_CASE_MISSING_REQUIRED_ARTIFACT: {filename} under {case_dir}")

    try:
        case_yaml = yaml.safe_load((case_dir / "case.yaml").read_text(encoding="utf-8")) or {}
    except yaml.YAMLError as exc:
        raise GoldenCaseError(f"GOLDEN_CASE_INVALID_YAML: case.yaml under {case_dir}: {exc}") from exc
    if not isinstance(case_yaml, dict):
        raise GoldenCaseError(f"GOLDEN_CASE_INVALID_YAML: case.yaml under {case_dir} is not a mapping")

    missing_fields = [f for f in REQUIRED_CASE_YAML_FIELDS if not case_yaml.get(f)]
    if missing_fields:
        raise GoldenCaseError(f"GOLDEN_CASE_MISSING_FIELDS: {missing_fields} in case.yaml under {case_dir}")

    if case_yaml["approval_status"] not in VALID_APPROVAL_STATUSES:
        raise GoldenCaseError(
            f"GOLDEN_CASE_INVALID_APPROVAL_STATUS: {case_yaml['approval_status']!r} "
            f"(must be one of {sorted(VALID_APPROVAL_STATUSES)})"
        )
    if case_yaml["case_type"] not in VALID_CASE_TYPES:
        raise GoldenCaseError(
            f"GOLDEN_CASE_INVALID_CASE_TYPE: {case_yaml['case_type']!r} (must be one of {sorted(VALID_CASE_TYPES)})"
        )

    try:
        expected = yaml.safe_load((case_dir / "expected.yaml").read_text(encoding="utf-8")) or {}
    except yaml.YAMLError as exc:
        raise GoldenCaseError(f"GOLDEN_CASE_INVALID_YAML: expected.yaml under {case_dir}: {exc}") from exc
    if not isinstance(expected, dict):
        raise GoldenCaseError(f"GOLDEN_CASE_INVALID_YAML: expected.yaml under {case_dir} is not a mapping")

    return GoldenCase(case_id=str(case_yaml["case_id"]), case_dir=case_dir, case_yaml=case_yaml, expected=expected)


def load_manual_claim_labels(path: Path | str) -> list[dict[str, Any]]:
    """Loads the optional manual_claim_labels.csv template/data. An empty
    or absent file is a legitimate, honest state -- returns ``[]``, never
    fabricated rows."""
    import csv

    path = Path(path)
    if not path.exists():
        return []
    with path.open(encoding="utf-8", newline="") as handle:
        return list(csv.DictReader(handle))


__all__ = [
    "GoldenCase",
    "GoldenCaseError",
    "REQUIRED_CASE_YAML_FIELDS",
    "VALID_APPROVAL_STATUSES",
    "VALID_CASE_TYPES",
    "load_golden_case",
    "load_manual_claim_labels",
    "verify_artifact_hashes",
]
