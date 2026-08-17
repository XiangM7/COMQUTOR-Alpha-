"""Sprint 3, Track J3: independent-LLM blind review packet + comparison
reference exporter.

Export-only. Never executes a new LLM review, never modifies any stance,
never touches B1's prompt/taxonomy/B2-B5/J2 labels, never re-samples.
Reuses the existing, already-verified 50-row sample
(``docs/evidence_review_sample_records.json``, sampling_version
``evidence_review_sample.v1``) and the existing, already-verified
LLM-vs-deterministic stance comparison
(``docs/audit_artifacts/b1_llm_stance_50_validation_after_parser_fix.csv``,
the *final combined* artifact -- 20 rows from the original validation run
plus 30 from the parser-fix rerun, merged; see
``docs/audit_artifacts/b1_shared_json_parser_fix_report.json``'s own
``final_combined_*`` fields) -- never a second sampling or classification
pass.

Produces two physically separate files, joined only by the sample's own
existing identity fields (``run_id``, ``claim_id``, ``target_alpha_id`` --
plus the sample's own pre-existing ``sample_id``, reused, never a new
locator):

  * ``j3_llm_blind_review_packet.json`` -- claim/evidence/taxonomy context
    only, zero prior stance/disagreement/confidence/reasoning/counter-Alpha
    answers.
  * ``j3_llm_comparison_reference.json`` -- the full historical comparison
    (original LLM verdict, deterministic.v1 verdict, system final stance,
    disagreement/reversal flags), for use only *after* the blind review.
"""

from __future__ import annotations

import csv
import hashlib
import json
from pathlib import Path
from typing import Any

from comqutor_alpha.alpha_library.alpha_loader import load_alpha_taxonomy
from comqutor_alpha.structure_engine.evidence_stance import (
    CLASSIFIER_VERSION as DETERMINISTIC_CLASSIFIER_VERSION,
)
from comqutor_alpha.structure_engine.evidence_stance_llm import LLM_CLASSIFIER_VERSION

BLIND_PACKET_SCHEMA_VERSION = "j3.llm_blind_review_packet.v1"
COMPARISON_REFERENCE_SCHEMA_VERSION = "j3.llm_comparison_reference.v1"

DEFAULT_SOURCE_SAMPLE_PATH = Path("docs/evidence_review_sample_records.json")
DEFAULT_STANCE_COMPARISON_PATH = Path("docs/audit_artifacts/b1_llm_stance_50_validation_after_parser_fix.csv")
DEFAULT_REPLAY_OUTPUT_ROOT = Path("outputs/review_sample_replays")
DEFAULT_BLIND_PACKET_OUTPUT_PATH = Path("docs/audit_artifacts/j3_llm_blind_review_packet.json")
DEFAULT_COMPARISON_REFERENCE_OUTPUT_PATH = Path("docs/audit_artifacts/j3_llm_comparison_reference.json")

EXPECTED_ROW_COUNT = 50
EXPECTED_LLM_DETERMINISTIC_DISAGREEMENT_COUNT = 31
EXPECTED_SUPPORT_OPPOSE_REVERSAL_COUNT = 7
EXPECTED_LLM_NEUTRAL_BACKGROUND_COUNT = 0

# Fields that must NEVER appear anywhere in a blind-packet row (task
# section 4) -- checked both at construction time (this module only ever
# builds rows from the fixed allowlist below) and by the dedicated test
# suite (which additionally greps the written file).
FORBIDDEN_BLIND_PACKET_ROW_FIELDS = frozenset(
    {
        "evidence_stance",
        "deterministic_v1_stance",
        "deterministic_stance",
        "llm_v1_stance",
        "original_llm_stance",
        "system_final_stance",
        "final_stance",
        "stance_method",
        "counter_alpha_id",
        "reviewer_counter_alpha_id",
        "original_llm_counter_alpha_id",
        "deterministic_counter_alpha_id",
        "system_final_counter_alpha_id",
        "llm_deterministic_disagreement",
        "support_oppose_reversal",
        "confidence",
        "stance_confidence_band",
        "review_confidence",
        "reviewer_confidence",
        "stance_reason_codes",
        "reviewer_notes",
        "reviewer_expected_stance",
        "requires_manual_review",
        "provenance",
    }
)

BLIND_PACKET_ROW_FIELDS = (
    "sample_id",
    "run_id",
    "ticker",
    "claim_id",
    "evidence_fact_group_id",
    "agent",
    "claim",
    "evidence",
    "target_alpha_id",
    "target_alpha_name",
    "target_alpha_definition",
    "legal_counter_alphas",
    "source_refs",
    "source_context",
)

# Task section 5.1 -- verbatim semantics (English rendering of the task's
# own specified meaning; the taxonomy/ontology values themselves are
# unchanged from evidence_stance.VALID_EVIDENCE_STANCES).
STANCE_ONTOLOGY = {
    "supports_alpha": (
        "The Evidence directly supports the target Alpha's thesis."
    ),
    "opposes_alpha": (
        "The Evidence directly weakens, negates, or rebuts the target Alpha's thesis."
    ),
    "mentions_alpha": (
        "The Evidence references a concept related to the target Alpha, but does not "
        "take a clear supporting or opposing position on it."
    ),
    "neutral_background": (
        "The Evidence is background information only and cannot form a meaningful "
        "semantic stance toward the target Alpha."
    ),
    "supports_counter_alpha": (
        "The Evidence primarily supports the target Alpha's canonical conflict "
        "(counter) Alpha. Only this stance may return a counter_alpha_id."
    ),
}

STANCE_ONTOLOGY_NOTES = (
    "Stance is always an Alpha-relative judgment, evaluated with respect to the given "
    "target_alpha_id -- it is not the claim's own directional tone, not the reporting "
    "agent's bull/bear role, and not a keyword match."
)

REVIEW_INSTRUCTIONS = {
    "response_schema": {
        "run_id": "string, returned exactly as given",
        "claim_id": "string, returned exactly as given",
        "target_alpha_id": "string, returned exactly as given",
        "reviewed_stance": "one of: supports_alpha | opposes_alpha | mentions_alpha | neutral_background | supports_counter_alpha",
        "reviewed_counter_alpha_id": "string (must be one of legal_counter_alphas) or null",
        "review_confidence": "one of: high | medium | low",
        "review_reason": "short, specific statement of the semantic basis for the stance",
    },
    "contract_rules": [
        "Identity fields (run_id, claim_id, target_alpha_id) must be returned unchanged.",
        "reviewed_stance must be exactly one of the five canonical values.",
        "Only reviewed_stance == supports_counter_alpha may carry a non-null reviewed_counter_alpha_id.",
        "reviewed_counter_alpha_id, when present, must be a member of this row's own legal_counter_alphas.",
        "Every other stance's reviewed_counter_alpha_id must be null.",
        "review_reason must briefly state the specific semantic basis for the judgment.",
        "Do not infer stance from the reporting agent's name or role.",
        "Do not classify a stance merely because a keyword (e.g. valuation, risk, AI, growth) appears.",
        "Explicitly look for negation, rebuttal, quoted opposing arguments, and meta-commentary about an argument.",
        "Do not alter claim, evidence, or any identity field.",
    ],
}


class J3SourceSampleMismatchError(Exception):
    """Raised when the historically-recorded numbers (31 disagreement / 7
    reversal / 0 neutral_background in the LLM distribution) cannot be
    reproduced from the located source files -- signals
    J3_SOURCE_SAMPLE_MISMATCH rather than silently exporting a conclusion
    the data does not actually support."""


def _sha256_file(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def load_source_sample(path: Path = DEFAULT_SOURCE_SAMPLE_PATH) -> dict[str, Any]:
    payload = json.loads(path.read_text(encoding="utf-8"))
    records = payload.get("records")
    if not isinstance(records, list):
        raise J3SourceSampleMismatchError("J3_SOURCE_SAMPLE_MISMATCH: records missing or not a list")
    return payload


def load_stance_comparison(path: Path = DEFAULT_STANCE_COMPARISON_PATH) -> dict[str, dict[str, str]]:
    with path.open(encoding="utf-8", newline="") as handle:
        rows = list(csv.DictReader(handle))
    by_sample_id = {row["sample_id"]: row for row in rows}
    if len(by_sample_id) != len(rows):
        raise J3SourceSampleMismatchError("J3_SOURCE_SAMPLE_MISMATCH: duplicate sample_id in stance comparison CSV")
    return by_sample_id


def verify_historical_numbers(stance_rows: dict[str, dict[str, str]]) -> dict[str, Any]:
    """Recomputes the three historically-recorded numbers from the located
    source data using simple, unambiguous definitions (never a new
    semantic judgment -- purely set/equality comparisons over already-
    existing categorical values) and raises J3SourceSampleMismatchError if
    they do not match. Returns the recomputed numbers for the caller to
    embed in both output files' metadata."""
    rows = list(stance_rows.values())
    disagreement_count = sum(1 for r in rows if r["deterministic_v1_stance"] != r["llm_v1_stance"])
    reversal_count = sum(
        1
        for r in rows
        if {r["deterministic_v1_stance"], r["llm_v1_stance"]} == {"supports_alpha", "opposes_alpha"}
    )
    llm_neutral_background_count = sum(1 for r in rows if r["llm_v1_stance"] == "neutral_background")

    mismatches = []
    if len(rows) != EXPECTED_ROW_COUNT:
        mismatches.append(f"row_count={len(rows)} (expected {EXPECTED_ROW_COUNT})")
    if disagreement_count != EXPECTED_LLM_DETERMINISTIC_DISAGREEMENT_COUNT:
        mismatches.append(
            f"llm_deterministic_disagreement_count={disagreement_count} (expected {EXPECTED_LLM_DETERMINISTIC_DISAGREEMENT_COUNT})"
        )
    if reversal_count != EXPECTED_SUPPORT_OPPOSE_REVERSAL_COUNT:
        mismatches.append(
            f"support_oppose_reversal_count={reversal_count} (expected {EXPECTED_SUPPORT_OPPOSE_REVERSAL_COUNT})"
        )
    if llm_neutral_background_count != EXPECTED_LLM_NEUTRAL_BACKGROUND_COUNT:
        mismatches.append(
            f"llm_neutral_background_count={llm_neutral_background_count} (expected {EXPECTED_LLM_NEUTRAL_BACKGROUND_COUNT})"
        )
    if mismatches:
        raise J3SourceSampleMismatchError("J3_SOURCE_SAMPLE_MISMATCH: " + "; ".join(mismatches))

    return {
        "llm_deterministic_disagreement_count": disagreement_count,
        "support_oppose_reversal_count": reversal_count,
        "llm_neutral_background_count": llm_neutral_background_count,
    }


def load_source_refs_by_claim_id(
    records: list[dict[str, Any]], replay_output_root: Path = DEFAULT_REPLAY_OUTPUT_ROOT
) -> dict[str, list[str] | None]:
    """Cross-references each replay bundle's own structured_agent_outputs.json
    (already produced, read-only) for the real source_refs of every sample
    claim_id. A replay bundle or claim_id that is genuinely unavailable
    yields None for that claim -- never a guessed/fuzzy match."""
    replay_run_ids = sorted({r["replay_run_id"] for r in records if r.get("replay_run_id")})
    refs_by_claim: dict[str, list[str] | None] = {}
    for replay_run_id in replay_run_ids:
        structured_path = replay_output_root / replay_run_id / "structured_agent_outputs.json"
        if not structured_path.exists():
            continue
        try:
            structured = json.loads(structured_path.read_text(encoding="utf-8"))
        except (OSError, ValueError):
            continue
        for structured_record in structured.get("records") or ():
            claim_id = structured_record.get("claim_id")
            if claim_id and claim_id not in refs_by_claim:
                source_refs = structured_record.get("source_refs")
                refs_by_claim[claim_id] = (
                    [str(ref) for ref in source_refs] if isinstance(source_refs, list) else None
                )
    return refs_by_claim


def _taxonomy_export(taxonomy: dict[str, Any]) -> dict[str, dict[str, Any]]:
    export: dict[str, dict[str, Any]] = {}
    for alpha_id, alpha in sorted(taxonomy.items()):
        export[alpha_id] = {
            "alpha_id": alpha.alpha_id,
            "name": alpha.name_en,
            "layer": alpha.layer,
            "core_thesis": alpha.core_thesis,
            "core_function": None,  # not a field in AlphaDefinition -- honestly null, never guessed
            "conflict_alphas": sorted(c.alpha_id for c in (alpha.conflict_alphas or ())),
        }
    return export


def _legal_counter_alphas(target_alpha_id: str, taxonomy: dict[str, Any]) -> list[str]:
    alpha = taxonomy.get(target_alpha_id)
    if alpha is None:
        return []
    return sorted(c.alpha_id for c in (alpha.conflict_alphas or ()))


def _primary_evidence_fact_group_id(record: dict[str, Any]) -> str | None:
    group_ids = record.get("evidence_fact_group_ids")
    if isinstance(group_ids, list) and group_ids:
        return group_ids[0]
    return None


def build_blind_review_packet(
    *,
    sample_payload: dict[str, Any],
    taxonomy: dict[str, Any],
    source_refs_by_claim: dict[str, list[str] | None],
    source_sample_path: Path,
    created_at: str,
) -> dict[str, Any]:
    records = sample_payload["records"]
    taxonomy_export = _taxonomy_export(taxonomy)

    rows: list[dict[str, Any]] = []
    for record in records:
        target_alpha_id = record.get("target_alpha_id")
        taxonomy_entry = taxonomy_export.get(target_alpha_id)
        claim_id = record.get("claim_id")
        row = {
            "sample_id": record.get("sample_id"),
            "run_id": record.get("run_id"),
            "ticker": record.get("ticker"),
            "claim_id": claim_id,
            "evidence_fact_group_id": _primary_evidence_fact_group_id(record),
            "agent": record.get("agent"),
            "claim": record.get("claim"),
            "evidence": record.get("evidence"),
            "target_alpha_id": target_alpha_id,
            "target_alpha_name": taxonomy_entry["name"] if taxonomy_entry else record.get("target_alpha_name"),
            "target_alpha_definition": taxonomy_entry["core_thesis"] if taxonomy_entry else None,
            "legal_counter_alphas": _legal_counter_alphas(target_alpha_id, taxonomy),
            "source_refs": source_refs_by_claim.get(claim_id),
            "source_context": None,  # no existing, identity-derivable broader-context field found -- honest null
        }
        assert set(row.keys()) == set(BLIND_PACKET_ROW_FIELDS)
        assert not (set(row.keys()) & FORBIDDEN_BLIND_PACKET_ROW_FIELDS)
        rows.append(row)

    return {
        "schema_version": BLIND_PACKET_SCHEMA_VERSION,
        "created_at": created_at,
        "source_sample": {
            "path": str(source_sample_path),
            "sha256": _sha256_file(source_sample_path),
            "row_count": len(rows),
        },
        "review_status": "awaiting_independent_llm_adjudication",
        "intended_review_authority": "user_authorized_provisional",
        "human_review_required_by_runtime": False,
        "formal_john_approval": "pending",
        "stance_ontology": {
            "values": STANCE_ONTOLOGY,
            "notes": STANCE_ONTOLOGY_NOTES,
        },
        "canonical_taxonomy": taxonomy_export,
        "review_instructions": REVIEW_INSTRUCTIONS,
        "rows": rows,
    }


def build_comparison_reference(
    *,
    sample_payload: dict[str, Any],
    stance_rows: dict[str, dict[str, str]],
    historical_summary: dict[str, Any],
    source_sample_path: Path,
    stance_comparison_path: Path,
    created_at: str,
) -> dict[str, Any]:
    records = {r["sample_id"]: r for r in sample_payload["records"]}

    rows: list[dict[str, Any]] = []
    for sample_id, stance_row in stance_rows.items():
        record = records.get(sample_id)
        if record is None:
            raise J3SourceSampleMismatchError(
                f"J3_SOURCE_SAMPLE_MISMATCH: stance comparison sample_id {sample_id!r} not found in source sample"
            )
        deterministic_stance = stance_row["deterministic_v1_stance"] or None
        original_llm_stance = stance_row["llm_v1_stance"] or None
        system_final_stance = stance_row["final_stance"] or None
        csv_counter_alpha_id = stance_row.get("counter_alpha_id") or None
        record_counter_alpha_id = record.get("counter_alpha_id") or None
        stance_method = stance_row.get("stance_method") or None
        provenance = stance_row.get("provenance") or "original_50_row_validation"

        rows.append(
            {
                "sample_id": sample_id,
                "run_id": record.get("run_id"),
                "ticker": record.get("ticker"),
                "claim_id": record.get("claim_id"),
                "target_alpha_id": record.get("target_alpha_id"),
                "original_llm_stance": original_llm_stance,
                "original_llm_counter_alpha_id": (
                    csv_counter_alpha_id if original_llm_stance == "supports_counter_alpha" else None
                ),
                "original_llm_method": "llm" if original_llm_stance is not None else "unavailable",
                "original_llm_version": LLM_CLASSIFIER_VERSION if original_llm_stance is not None else None,
                "original_llm_provenance": provenance,
                "deterministic_stance": deterministic_stance,
                "deterministic_counter_alpha_id": (
                    record_counter_alpha_id if deterministic_stance == "supports_counter_alpha" else None
                ),
                "deterministic_version": DETERMINISTIC_CLASSIFIER_VERSION,
                "system_final_stance": system_final_stance,
                "system_final_counter_alpha_id": (
                    csv_counter_alpha_id if system_final_stance == "supports_counter_alpha" else None
                ),
                "system_final_method": stance_method,
                "llm_deterministic_disagreement": (
                    deterministic_stance != original_llm_stance
                    if deterministic_stance is not None and original_llm_stance is not None
                    else None
                ),
                "support_oppose_reversal": (
                    {deterministic_stance, original_llm_stance} == {"supports_alpha", "opposes_alpha"}
                    if deterministic_stance is not None and original_llm_stance is not None
                    else None
                ),
            }
        )

    rows.sort(key=lambda r: r["sample_id"])

    return {
        "schema_version": COMPARISON_REFERENCE_SCHEMA_VERSION,
        "created_at": created_at,
        "source_sample": {
            "path": str(source_sample_path),
            "sha256": _sha256_file(source_sample_path),
            "row_count": len(rows),
        },
        "stance_comparison_source": {
            "path": str(stance_comparison_path),
            "sha256": _sha256_file(stance_comparison_path),
            "row_count": len(rows),
            "provenance_note": (
                "Final combined artifact: 20 rows from the original 50-row validation run "
                "(3/5 batches failed with malformed_response, i.e. markdown-fence-wrapped JSON) "
                "plus 30 rows from the parser-fix rerun of exactly those failed rows, merged. "
                "See docs/audit_artifacts/b1_shared_json_parser_fix_report.json."
            ),
        },
        "historical_summary": historical_summary,
        "rows": rows,
    }


def export_j3_review_packets(
    *,
    source_sample_path: Path = DEFAULT_SOURCE_SAMPLE_PATH,
    stance_comparison_path: Path = DEFAULT_STANCE_COMPARISON_PATH,
    replay_output_root: Path = DEFAULT_REPLAY_OUTPUT_ROOT,
    blind_packet_output_path: Path = DEFAULT_BLIND_PACKET_OUTPUT_PATH,
    comparison_reference_output_path: Path = DEFAULT_COMPARISON_REFERENCE_OUTPUT_PATH,
    created_at: str,
) -> dict[str, Any]:
    """Loads, verifies, and exports both J3 files. Raises
    J3SourceSampleMismatchError (never silently exports a conclusion the
    data does not support) if the historically-recorded numbers cannot be
    reproduced. Returns a summary dict for the caller to report."""
    sample_payload = load_source_sample(source_sample_path)
    stance_rows = load_stance_comparison(stance_comparison_path)

    sample_ids_in_sample = {r["sample_id"] for r in sample_payload["records"]}
    sample_ids_in_stance = set(stance_rows.keys())
    if sample_ids_in_sample != sample_ids_in_stance:
        raise J3SourceSampleMismatchError(
            "J3_SOURCE_SAMPLE_MISMATCH: identity sets differ between source sample and stance comparison -- "
            f"only-in-sample={sorted(sample_ids_in_sample - sample_ids_in_stance)}, "
            f"only-in-stance={sorted(sample_ids_in_stance - sample_ids_in_sample)}"
        )

    historical_summary = verify_historical_numbers(stance_rows)

    taxonomy = load_alpha_taxonomy()
    source_refs_by_claim = load_source_refs_by_claim_id(sample_payload["records"], replay_output_root)

    blind_packet = build_blind_review_packet(
        sample_payload=sample_payload,
        taxonomy=taxonomy,
        source_refs_by_claim=source_refs_by_claim,
        source_sample_path=source_sample_path,
        created_at=created_at,
    )
    comparison_reference = build_comparison_reference(
        sample_payload=sample_payload,
        stance_rows=stance_rows,
        historical_summary=historical_summary,
        source_sample_path=source_sample_path,
        stance_comparison_path=stance_comparison_path,
        created_at=created_at,
    )

    blind_packet_output_path.parent.mkdir(parents=True, exist_ok=True)
    blind_packet_output_path.write_text(
        json.dumps(blind_packet, indent=2, ensure_ascii=False) + "\n", encoding="utf-8"
    )
    comparison_reference_output_path.parent.mkdir(parents=True, exist_ok=True)
    comparison_reference_output_path.write_text(
        json.dumps(comparison_reference, indent=2, ensure_ascii=False) + "\n", encoding="utf-8"
    )

    return {
        "source_sample_path": str(source_sample_path),
        "source_sample_sha256": _sha256_file(source_sample_path),
        "stance_comparison_path": str(stance_comparison_path),
        "stance_comparison_sha256": _sha256_file(stance_comparison_path),
        "row_count": len(sample_payload["records"]),
        "historical_summary": historical_summary,
        "blind_packet_output_path": str(blind_packet_output_path),
        "comparison_reference_output_path": str(comparison_reference_output_path),
    }


__all__ = [
    "BLIND_PACKET_SCHEMA_VERSION",
    "COMPARISON_REFERENCE_SCHEMA_VERSION",
    "DEFAULT_SOURCE_SAMPLE_PATH",
    "DEFAULT_STANCE_COMPARISON_PATH",
    "DEFAULT_REPLAY_OUTPUT_ROOT",
    "DEFAULT_BLIND_PACKET_OUTPUT_PATH",
    "DEFAULT_COMPARISON_REFERENCE_OUTPUT_PATH",
    "EXPECTED_ROW_COUNT",
    "EXPECTED_LLM_DETERMINISTIC_DISAGREEMENT_COUNT",
    "EXPECTED_SUPPORT_OPPOSE_REVERSAL_COUNT",
    "EXPECTED_LLM_NEUTRAL_BACKGROUND_COUNT",
    "FORBIDDEN_BLIND_PACKET_ROW_FIELDS",
    "BLIND_PACKET_ROW_FIELDS",
    "STANCE_ONTOLOGY",
    "J3SourceSampleMismatchError",
    "load_source_sample",
    "load_stance_comparison",
    "verify_historical_numbers",
    "load_source_refs_by_claim_id",
    "build_blind_review_packet",
    "build_comparison_reference",
    "export_j3_review_packets",
]
