"""J3 Provisional Semantic Benchmark construction (task
J3_PROVISIONAL_SEMANTIC_BENCHMARK_INTEGRATION).

Builds ``comqutor_alpha/config/j3_provisional_semantic_benchmark_v0.1.json``
by joining the independent LLM reviewer's 50 verdicts (embedded verbatim
below -- this task's own formal input, never re-inferred, never re-called)
with the identity/claim-text fields already present in the existing blind
review packet (``docs/audit_artifacts/j3_llm_blind_review_packet.json``),
by the packet's own pre-existing ``sample_id`` -- never a new locator.

Export-only: never calls an LLM, never modifies any stance, never
re-samples, never writes back to the blind packet or comparison
reference. Fails closed (raises ``J3BenchmarkValidationError``) on any
row-count/identity/vocabulary/counter-Alpha-legality violation -- never
silently drops or coerces a bad row.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from comqutor_alpha.alpha_library.alpha_loader import load_alpha_taxonomy
from comqutor_alpha.structure_engine.evidence_stance import (
    SUPPORTS_COUNTER_ALPHA,
    VALID_EVIDENCE_STANCES,
)

BENCHMARK_SCHEMA_VERSION = "j3.provisional_semantic_benchmark.v0.1"
DEFAULT_BLIND_PACKET_PATH = Path("docs/audit_artifacts/j3_llm_blind_review_packet.json")
DEFAULT_BENCHMARK_OUTPUT_PATH = Path("comqutor_alpha/config/j3_provisional_semantic_benchmark_v0.1.json")

EXPECTED_ROW_COUNT = 50
_VALID_CONFIDENCE_LEVELS = frozenset({"high", "medium", "low"})

# Task section 5 -- the independent LLM reviewer's formal, verbatim
# verdicts. Never re-called, never re-inferred, never edited to match a
# hoped-for distribution -- this is this task's own authorized input.
EMBEDDED_REVIEWED_ROWS: tuple[dict[str, Any], ...] = (
    {"sample_id": "evrs-001", "reviewed_stance": "supports_alpha", "reviewed_counter_alpha_id": None, "review_confidence": "medium"},
    {"sample_id": "evrs-002", "reviewed_stance": "opposes_alpha", "reviewed_counter_alpha_id": None, "review_confidence": "medium"},
    {"sample_id": "evrs-003", "reviewed_stance": "opposes_alpha", "reviewed_counter_alpha_id": None, "review_confidence": "high"},
    {"sample_id": "evrs-004", "reviewed_stance": "mentions_alpha", "reviewed_counter_alpha_id": None, "review_confidence": "high"},
    {"sample_id": "evrs-005", "reviewed_stance": "supports_alpha", "reviewed_counter_alpha_id": None, "review_confidence": "high"},
    {"sample_id": "evrs-006", "reviewed_stance": "neutral_background", "reviewed_counter_alpha_id": None, "review_confidence": "high"},
    {"sample_id": "evrs-007", "reviewed_stance": "opposes_alpha", "reviewed_counter_alpha_id": None, "review_confidence": "high"},
    {"sample_id": "evrs-008", "reviewed_stance": "supports_counter_alpha", "reviewed_counter_alpha_id": "A501", "review_confidence": "high"},
    {"sample_id": "evrs-009", "reviewed_stance": "supports_alpha", "reviewed_counter_alpha_id": None, "review_confidence": "high"},
    {"sample_id": "evrs-010", "reviewed_stance": "supports_alpha", "reviewed_counter_alpha_id": None, "review_confidence": "high"},
    {"sample_id": "evrs-011", "reviewed_stance": "supports_alpha", "reviewed_counter_alpha_id": None, "review_confidence": "high"},
    {"sample_id": "evrs-012", "reviewed_stance": "opposes_alpha", "reviewed_counter_alpha_id": None, "review_confidence": "high"},
    {"sample_id": "evrs-013", "reviewed_stance": "mentions_alpha", "reviewed_counter_alpha_id": None, "review_confidence": "medium"},
    {"sample_id": "evrs-014", "reviewed_stance": "opposes_alpha", "reviewed_counter_alpha_id": None, "review_confidence": "high"},
    {"sample_id": "evrs-015", "reviewed_stance": "supports_alpha", "reviewed_counter_alpha_id": None, "review_confidence": "high"},
    {"sample_id": "evrs-016", "reviewed_stance": "supports_alpha", "reviewed_counter_alpha_id": None, "review_confidence": "high"},
    {"sample_id": "evrs-017", "reviewed_stance": "supports_alpha", "reviewed_counter_alpha_id": None, "review_confidence": "high"},
    {"sample_id": "evrs-018", "reviewed_stance": "opposes_alpha", "reviewed_counter_alpha_id": None, "review_confidence": "high"},
    {"sample_id": "evrs-019", "reviewed_stance": "supports_alpha", "reviewed_counter_alpha_id": None, "review_confidence": "high"},
    {"sample_id": "evrs-020", "reviewed_stance": "supports_alpha", "reviewed_counter_alpha_id": None, "review_confidence": "medium"},
    {"sample_id": "evrs-021", "reviewed_stance": "opposes_alpha", "reviewed_counter_alpha_id": None, "review_confidence": "high"},
    {"sample_id": "evrs-022", "reviewed_stance": "supports_alpha", "reviewed_counter_alpha_id": None, "review_confidence": "medium"},
    {"sample_id": "evrs-023", "reviewed_stance": "supports_alpha", "reviewed_counter_alpha_id": None, "review_confidence": "medium"},
    {"sample_id": "evrs-024", "reviewed_stance": "supports_alpha", "reviewed_counter_alpha_id": None, "review_confidence": "high"},
    {"sample_id": "evrs-025", "reviewed_stance": "supports_alpha", "reviewed_counter_alpha_id": None, "review_confidence": "medium"},
    {"sample_id": "evrs-026", "reviewed_stance": "supports_alpha", "reviewed_counter_alpha_id": None, "review_confidence": "medium"},
    {"sample_id": "evrs-027", "reviewed_stance": "opposes_alpha", "reviewed_counter_alpha_id": None, "review_confidence": "high"},
    {"sample_id": "evrs-028", "reviewed_stance": "supports_alpha", "reviewed_counter_alpha_id": None, "review_confidence": "high"},
    {"sample_id": "evrs-029", "reviewed_stance": "mentions_alpha", "reviewed_counter_alpha_id": None, "review_confidence": "medium"},
    {"sample_id": "evrs-030", "reviewed_stance": "supports_alpha", "reviewed_counter_alpha_id": None, "review_confidence": "high"},
    {"sample_id": "evrs-031", "reviewed_stance": "supports_alpha", "reviewed_counter_alpha_id": None, "review_confidence": "high"},
    {"sample_id": "evrs-032", "reviewed_stance": "opposes_alpha", "reviewed_counter_alpha_id": None, "review_confidence": "high"},
    {"sample_id": "evrs-033", "reviewed_stance": "supports_alpha", "reviewed_counter_alpha_id": None, "review_confidence": "high"},
    {"sample_id": "evrs-034", "reviewed_stance": "supports_alpha", "reviewed_counter_alpha_id": None, "review_confidence": "high"},
    {"sample_id": "evrs-035", "reviewed_stance": "opposes_alpha", "reviewed_counter_alpha_id": None, "review_confidence": "high"},
    {"sample_id": "evrs-036", "reviewed_stance": "mentions_alpha", "reviewed_counter_alpha_id": None, "review_confidence": "high"},
    {"sample_id": "evrs-037", "reviewed_stance": "supports_alpha", "reviewed_counter_alpha_id": None, "review_confidence": "high"},
    {"sample_id": "evrs-038", "reviewed_stance": "supports_alpha", "reviewed_counter_alpha_id": None, "review_confidence": "high"},
    {"sample_id": "evrs-039", "reviewed_stance": "opposes_alpha", "reviewed_counter_alpha_id": None, "review_confidence": "high"},
    {"sample_id": "evrs-040", "reviewed_stance": "supports_alpha", "reviewed_counter_alpha_id": None, "review_confidence": "medium"},
    {"sample_id": "evrs-041", "reviewed_stance": "opposes_alpha", "reviewed_counter_alpha_id": None, "review_confidence": "high"},
    {"sample_id": "evrs-042", "reviewed_stance": "opposes_alpha", "reviewed_counter_alpha_id": None, "review_confidence": "high"},
    {"sample_id": "evrs-043", "reviewed_stance": "opposes_alpha", "reviewed_counter_alpha_id": None, "review_confidence": "medium"},
    {"sample_id": "evrs-044", "reviewed_stance": "supports_alpha", "reviewed_counter_alpha_id": None, "review_confidence": "high"},
    {"sample_id": "evrs-045", "reviewed_stance": "supports_counter_alpha", "reviewed_counter_alpha_id": "A304", "review_confidence": "high"},
    {"sample_id": "evrs-046", "reviewed_stance": "supports_alpha", "reviewed_counter_alpha_id": None, "review_confidence": "high"},
    {"sample_id": "evrs-047", "reviewed_stance": "opposes_alpha", "reviewed_counter_alpha_id": None, "review_confidence": "high"},
    {"sample_id": "evrs-048", "reviewed_stance": "opposes_alpha", "reviewed_counter_alpha_id": None, "review_confidence": "high"},
    {"sample_id": "evrs-049", "reviewed_stance": "mentions_alpha", "reviewed_counter_alpha_id": None, "review_confidence": "medium"},
    {"sample_id": "evrs-050", "reviewed_stance": "supports_alpha", "reviewed_counter_alpha_id": None, "review_confidence": "high"},
)


class J3BenchmarkValidationError(Exception):
    """Fail-closed error for any row-count/identity/vocabulary/legality
    violation while constructing the J3 semantic benchmark -- never
    silently dropped, coerced, or worked around."""

    def __init__(self, reason_code: str, detail: str = "") -> None:
        self.reason_code = reason_code
        self.detail = detail
        super().__init__(f"{reason_code}: {detail}" if detail else reason_code)


def _load_blind_packet(path: Path) -> dict[str, Any]:
    if not path.exists():
        raise J3BenchmarkValidationError("J3_BLIND_PACKET_NOT_FOUND", str(path))
    return json.loads(path.read_text(encoding="utf-8"))


def build_j3_semantic_benchmark(
    *,
    blind_packet_path: Path = DEFAULT_BLIND_PACKET_PATH,
    reviewed_rows: tuple[dict[str, Any], ...] = EMBEDDED_REVIEWED_ROWS,
) -> dict[str, Any]:
    """Joins ``reviewed_rows`` (this task's own embedded, verbatim input)
    with the existing blind packet's identity/claim-text fields by
    ``sample_id``. Fails closed on any of task section 5's required
    checks. Never re-derives ``claim_text``/``run_id``/``claim_id``/
    ``target_alpha_id`` -- those are copied verbatim from the blind
    packet, never regenerated."""
    blind_packet = _load_blind_packet(blind_packet_path)
    blind_rows = blind_packet.get("rows")
    if not isinstance(blind_rows, list) or len(blind_rows) != EXPECTED_ROW_COUNT:
        raise J3BenchmarkValidationError(
            "J3_SOURCE_SAMPLE_MISMATCH",
            f"blind packet row_count={len(blind_rows) if isinstance(blind_rows, list) else 'n/a'} (expected {EXPECTED_ROW_COUNT})",
        )
    blind_by_sample_id = {row["sample_id"]: row for row in blind_rows}
    if len(blind_by_sample_id) != EXPECTED_ROW_COUNT:
        raise J3BenchmarkValidationError("J3_SOURCE_SAMPLE_MISMATCH", "duplicate sample_id in blind packet")

    if len(reviewed_rows) != EXPECTED_ROW_COUNT:
        raise J3BenchmarkValidationError(
            "J3_BENCHMARK_ROW_COUNT_MISMATCH", f"embedded reviewed_rows count={len(reviewed_rows)} (expected {EXPECTED_ROW_COUNT})"
        )
    reviewed_sample_ids = [row["sample_id"] for row in reviewed_rows]
    if len(set(reviewed_sample_ids)) != EXPECTED_ROW_COUNT:
        raise J3BenchmarkValidationError("J3_BENCHMARK_DUPLICATE_SAMPLE_ID", "duplicate sample_id in embedded reviewed_rows")

    blind_ids = set(blind_by_sample_id.keys())
    reviewed_ids = set(reviewed_sample_ids)
    if blind_ids != reviewed_ids:
        raise J3BenchmarkValidationError(
            "J3_BENCHMARK_IDENTITY_MISMATCH",
            f"only-in-blind-packet={sorted(blind_ids - reviewed_ids)}, only-in-reviewed-rows={sorted(reviewed_ids - blind_ids)}",
        )

    taxonomy = load_alpha_taxonomy()
    known_alpha_ids = frozenset(taxonomy.keys())

    rows: list[dict[str, Any]] = []
    # Iterate in the blind packet's own existing order -- never re-sorted,
    # never re-sampled.
    for blind_row in blind_rows:
        sample_id = blind_row["sample_id"]
        reviewed = next(r for r in reviewed_rows if r["sample_id"] == sample_id)

        stance = reviewed.get("reviewed_stance")
        if stance not in VALID_EVIDENCE_STANCES:
            raise J3BenchmarkValidationError("J3_BENCHMARK_INVALID_STANCE_VOCABULARY", f"{sample_id}: {stance!r}")

        confidence = reviewed.get("review_confidence")
        if confidence not in _VALID_CONFIDENCE_LEVELS:
            raise J3BenchmarkValidationError("J3_BENCHMARK_INVALID_CONFIDENCE", f"{sample_id}: {confidence!r}")

        target_alpha_id = blind_row["target_alpha_id"]
        if target_alpha_id not in known_alpha_ids:
            raise J3BenchmarkValidationError("J3_BENCHMARK_UNKNOWN_TARGET_ALPHA", f"{sample_id}: {target_alpha_id!r}")

        counter_alpha_id = reviewed.get("reviewed_counter_alpha_id")
        legal_counter_alphas = set(blind_row.get("legal_counter_alphas") or ())
        if stance == SUPPORTS_COUNTER_ALPHA:
            if not counter_alpha_id:
                raise J3BenchmarkValidationError("J3_BENCHMARK_MISSING_COUNTER_ALPHA_ID", sample_id)
            if counter_alpha_id not in known_alpha_ids:
                raise J3BenchmarkValidationError("J3_BENCHMARK_UNKNOWN_COUNTER_ALPHA", f"{sample_id}: {counter_alpha_id!r}")
            if counter_alpha_id not in legal_counter_alphas:
                raise J3BenchmarkValidationError(
                    "J3_BENCHMARK_ILLEGAL_COUNTER_ALPHA",
                    f"{sample_id}: {counter_alpha_id!r} not in legal_counter_alphas={sorted(legal_counter_alphas)}",
                )
        elif counter_alpha_id is not None:
            raise J3BenchmarkValidationError(
                "J3_BENCHMARK_UNEXPECTED_COUNTER_ALPHA_ID", f"{sample_id}: stance={stance!r} counter_alpha_id={counter_alpha_id!r}"
            )

        rows.append(
            {
                "sample_id": sample_id,
                "run_id": blind_row["run_id"],
                "claim_id": blind_row["claim_id"],
                "target_alpha_id": target_alpha_id,
                "claim_text": blind_row["claim"],
                "reviewed_stance": stance,
                "reviewed_counter_alpha_id": counter_alpha_id,
                "review_confidence": confidence,
            }
        )

    return {
        "schema_version": BENCHMARK_SCHEMA_VERSION,
        "authority": "independent_llm_provisional",
        "human_review_performed": False,
        "john_approved": False,
        "production_authority": False,
        "intended_use": "offline_semantic_evaluation_only",
        "row_count": len(rows),
        "source_blind_packet_path": str(blind_packet_path),
        "rows": rows,
    }


def write_j3_semantic_benchmark(
    benchmark: dict[str, Any], path: Path = DEFAULT_BENCHMARK_OUTPUT_PATH
) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(benchmark, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    return path


def load_j3_semantic_benchmark(path: Path = DEFAULT_BENCHMARK_OUTPUT_PATH) -> dict[str, Any]:
    """Read-only accessor for the already-built benchmark file. Never
    reads an environment variable to alter ``human_review_performed``/
    ``john_approved``/``production_authority`` -- those are always read
    verbatim from the file."""
    if not path.exists():
        raise J3BenchmarkValidationError("J3_BENCHMARK_FILE_NOT_FOUND", str(path))
    payload = json.loads(path.read_text(encoding="utf-8"))
    if payload.get("schema_version") != BENCHMARK_SCHEMA_VERSION:
        raise J3BenchmarkValidationError(
            "J3_BENCHMARK_SCHEMA_VERSION_MISMATCH", str(payload.get("schema_version"))
        )
    rows = payload.get("rows")
    if not isinstance(rows, list) or len(rows) != EXPECTED_ROW_COUNT:
        raise J3BenchmarkValidationError(
            "J3_BENCHMARK_ROW_COUNT_MISMATCH", f"{len(rows) if isinstance(rows, list) else 'n/a'}"
        )
    return payload


__all__ = [
    "BENCHMARK_SCHEMA_VERSION",
    "DEFAULT_BLIND_PACKET_PATH",
    "DEFAULT_BENCHMARK_OUTPUT_PATH",
    "EXPECTED_ROW_COUNT",
    "EMBEDDED_REVIEWED_ROWS",
    "J3BenchmarkValidationError",
    "build_j3_semantic_benchmark",
    "write_j3_semantic_benchmark",
    "load_j3_semantic_benchmark",
]
