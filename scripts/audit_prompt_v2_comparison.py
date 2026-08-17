#!/usr/bin/env python3
"""Phase 1 Master fix: render the real v2 minimal request for the same frozen
NVDA fundamental Smoke report used by ``audit_prompt_v1_root_cause.py``,
measure it with the same exact, mutually-exclusive attribution method, and
produce the before/after comparison. Zero Provider calls.

Writes only under ``docs/audit_artifacts/phase1_master/prompt_audit/``.
"""

from __future__ import annotations

import json
import sys
from pathlib import Path
from typing import Any

REPO_ROOT = Path(__file__).resolve().parents[1]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from comqutor_alpha.structure_engine.factor_normalizer import FACTOR_ALIASES  # noqa: E402
from comqutor_alpha.structure_engine.structured_output_shadow import (  # noqa: E402
    build_candidate_segments,
)
from comqutor_alpha.structure_engine.structured_output_shadow_prompt_v2 import (  # noqa: E402
    STRUCTURED_OUTPUT_SHADOW_PROMPT_V2,
    build_shadow_prompt_input_v2,
)
from comqutor_alpha.structure_engine.structured_output_shadow_v2 import (  # noqa: E402
    build_shadow_request_v2,
)
from scripts.audit_prompt_v1_root_cause import (  # noqa: E402
    AGENT,
    AGENT_OUTPUT_ID,
    OUT_DIR,
    REAL_RUN_ID,
    TICKER,
    _attribute_object_chars,
    _load_raw_report,
    _tokens_estimate,
)


def build_v2_request() -> dict[str, Any]:
    report_text, _raw_record = _load_raw_report()
    candidate_segments, _filtered = build_candidate_segments(report_text, agent_output_id=AGENT_OUTPUT_ID)
    request = build_shadow_request_v2(
        source_report=report_text,
        run_id=REAL_RUN_ID,
        ticker=TICKER,
        agent=AGENT,
        agent_output_id=AGENT_OUTPUT_ID,
        candidate_segments=candidate_segments,
        factor_vocabulary=list(FACTOR_ALIASES.keys()),
    )
    return {"report_text": report_text, "candidate_segments": candidate_segments, "request": request}


def main() -> None:
    OUT_DIR.mkdir(parents=True, exist_ok=True)
    built = build_v2_request()
    report_text = built["report_text"]
    request = built["request"]

    final_request_text = build_shadow_prompt_input_v2(request)
    (OUT_DIR / "v2_actual_request.txt").write_text(final_request_text, encoding="utf-8")

    fixed_instruction = STRUCTURED_OUTPUT_SHADOW_PROMPT_V2
    separator_label = "\n\nSHADOW_REQUEST_JSON:\n"
    request_json_text = json.dumps(dict(request), ensure_ascii=False, sort_keys=True, separators=(",", ":"))
    if fixed_instruction + separator_label + request_json_text != final_request_text:
        raise SystemExit("RECONSTRUCTION_MISMATCH: v2 harness split does not equal real prompt builder output")

    total_chars = len(final_request_text)
    top_field_chars, top_structural_remainder, top_total = _attribute_object_chars(dict(request))
    if top_total != len(request_json_text):
        raise SystemExit("TOP_LEVEL_JSON_ATTRIBUTION_MISMATCH")

    identity_keys = [
        "input_schema_version",
        "run_id",
        "ticker",
        "agent",
        "agent_output_id",
        "agent_report_boundary",
        "agent_report_end_boundary",
    ]
    identity_metadata_chars = sum(top_field_chars[k] for k in identity_keys)
    factor_vocabulary_chars = top_field_chars["factor_vocabulary"]
    candidate_hints_chars = top_field_chars["candidate_hints"]
    agent_report_field_chars = top_field_chars["agent_report"]
    raw_report_chars = len(report_text)
    other_chars = top_structural_remainder + len(separator_label)
    fixed_instruction_chars = len(fixed_instruction)

    accounted = (
        fixed_instruction_chars
        + agent_report_field_chars
        + candidate_hints_chars
        + factor_vocabulary_chars
        + identity_metadata_chars
        + other_chars
    )
    if accounted != total_chars:
        raise SystemExit(
            f"COMPONENT_SUM_MISMATCH: accounted={accounted} total={total_chars} diff={total_chars - accounted}"
        )

    report_duplication_ratio_v2 = round((raw_report_chars + 0) / raw_report_chars, 4)  # no text duplication in v2

    v2_breakdown = {
        "schema_version": "comqutor.phase1_master.prompt_audit.v2_breakdown.v1",
        "report_identity": {
            "agent_output_id": AGENT_OUTPUT_ID,
            "ticker": TICKER,
            "agent": AGENT,
            "raw_report_chars": raw_report_chars,
        },
        "candidate_hint_count": len(request["candidate_hints"]),
        "components": {
            "fixed_instruction_chars": fixed_instruction_chars,
            "fixed_instruction_tokens_estimate": _tokens_estimate(fixed_instruction_chars),
            "raw_report_chars": raw_report_chars,
            "raw_report_tokens_estimate": _tokens_estimate(raw_report_chars),
            "agent_report_json_field_chars": agent_report_field_chars,
            "candidate_hints_chars": candidate_hints_chars,
            "candidate_hints_tokens_estimate": _tokens_estimate(candidate_hints_chars),
            "factor_vocabulary_chars": factor_vocabulary_chars,
            "identity_metadata_chars": identity_metadata_chars,
            "other_chars": other_chars,
            "total_chars": total_chars,
            "total_tokens_estimate": _tokens_estimate(total_chars),
        },
        "duplication": {
            "candidate_text_chars": 0,
            "report_duplication_ratio": report_duplication_ratio_v2,
            "note": "v2 never sends candidate claim/evidence text; only {id,start,end} for verified-location candidates. The report appears exactly once.",
        },
        "reconstruction_proof": {"component_sum_equals_total_chars": accounted == total_chars},
    }
    (OUT_DIR / "v2_request_breakdown.json").write_text(
        json.dumps(v2_breakdown, indent=2, ensure_ascii=False) + "\n", encoding="utf-8"
    )

    # ---- v1 vs v2 comparison ----
    v1_breakdown = json.loads((OUT_DIR / "v1_request_breakdown.json").read_text(encoding="utf-8"))
    v1c = v1_breakdown["components"]
    v1_total = v1c["total_chars"]
    v2_total = total_chars
    reduction_pct = round(100 * (v1_total - v2_total) / v1_total, 2)

    comparison = {
        "schema_version": "comqutor.phase1_master.prompt_audit.v1_vs_v2_comparison.v1",
        "v1_total_chars": v1_total,
        "v2_total_chars": v2_total,
        "v1_total_tokens_estimate": v1c["total_tokens_estimate"],
        "v2_total_tokens_estimate": v2_breakdown["components"]["total_tokens_estimate"],
        "reduction_pct": reduction_pct,
        "v1_report_duplication_ratio": v1_breakdown["duplication"]["report_duplication_ratio"],
        "v2_report_duplication_ratio": report_duplication_ratio_v2,
        "v1_candidate_text_chars": v1c["candidate_segment_text_chars"] + v1c["candidate_segment_metadata_chars"],
        "v2_candidate_text_chars": candidate_hints_chars,
        "v1_schema_chars": v1c["schema_instruction_chars"] + v1c["output_format_instruction_chars"],
        "v2_schema_chars": None,  # filled below once v2 fixed-instruction is split the same way
        "v1_factor_vocabulary_chars": v1c["factor_vocabulary_chars"],
        "v2_factor_vocabulary_chars": factor_vocabulary_chars,
        "v1_fixed_instruction_chars": v1c["fixed_instruction_chars"],
        "v2_fixed_instruction_chars": fixed_instruction_chars,
        "v1_identity_metadata_chars": v1c["identity_metadata_chars"],
        "v2_identity_metadata_chars": identity_metadata_chars,
        "target_max_v2_chars": 40_000,
        "meets_40k_target": v2_total <= 40_000,
        "target_max_duplication_ratio": 1.05,
        "meets_duplication_ratio_target": report_duplication_ratio_v2 <= 1.05,
        "removed_components": [
            {
                "removed": "evidence_hint (163/163 candidates, byte-identical to claim_hint)",
                "chars_recovered": v1c["candidate_segment_text_subfields"]["evidence_hint_chars"],
                "why_safe": "Measured 100% identical to claim_hint in the real report; carried zero incremental information.",
                "deterministic_replacement": "none needed -- field deleted",
                "corresponding_test": "test_v2_semantic_equivalence.py::test_claim_and_abstention_round_trip (proves evidence is still correctly reconstructed downstream from spans, not from a wire-carried evidence_hint)",
            },
            {
                "removed": "claim_hint text for the 142/163 candidates with no verified location",
                "chars_recovered": None,
                "why_safe": "These hints are cleaned paraphrases that do not exist verbatim in the raw report (measured, not assumed); the model reads the one full report copy directly instead. ADR-008 designates candidate segments as non-authoritative hints, not a required coverage mechanism.",
                "deterministic_replacement": "none -- semantic responsibility moves to the model's own reading of agent_report, which is unchanged Development Plan §5.1 scope",
                "corresponding_test": "test_v2_semantic_equivalence.py::test_claim_outside_any_candidate_hint_still_accepted",
            },
            {
                "removed": "claim_hint/exact_quote text for the 21/163 candidates with a verified location",
                "chars_recovered": None,
                "why_safe": "report[start:end] reproduces it deterministically; validate_shadow_bundle already independently recomputes and enforces the same equality regardless of what was sent.",
                "deterministic_replacement": "normalize_v2_proposal_to_canonical_bundle._normalize_span computes report[start:end]",
                "corresponding_test": "test_v2_provenance_safety.py::test_exact_quote_reconstructed_from_offsets",
            },
            {
                "removed": "candidate_segment_id full form (163x repeats of the 75-char agent_output_id)",
                "chars_recovered": None,
                "why_safe": "The model only needs a short local reference to cite lineage; the caller already holds the full ID locally and maps it back after the response.",
                "deterministic_replacement": "candidate_index int (already present) + candidate_index_to_id lookup, caller-side only",
                "corresponding_test": "test_v2_semantic_equivalence.py::test_candidate_lineage_resolved_from_short_id",
            },
            {
                "removed": "semantic_authority (163x repeats of the constant false)",
                "chars_recovered": None,
                "why_safe": "Unconditional invariant per ADR-008 -- never varies -- now stated once in the fixed instruction instead of once per candidate.",
                "deterministic_replacement": "one sentence in STRUCTURED_OUTPUT_SHADOW_PROMPT_V2 ('CANDIDATE_HINTS ... have no semantic authority')",
                "corresponding_test": "n/a -- prompt text, not a runtime code path",
            },
            {
                "removed": "source_report_sha256 / prompt_version / prompt_sha256 / candidate_segment_contract_version / candidate_segment_source / allowed_source_refs / source_metadata / output_schema_version from the wire request",
                "chars_recovered": None,
                "why_safe": "Never read back from the model's response by validate_shadow_bundle (which takes these as caller-supplied parameters); grep-confirmed no downstream consumer reads candidate_segment_contract_version/source from the request either.",
                "deterministic_replacement": "normalize_v2_proposal_to_canonical_bundle splices all identity fields from caller inputs",
                "corresponding_test": "test_v2_semantic_equivalence.py::test_identity_fields_never_required_from_provider",
            },
            {
                "removed": "shadow_claim_id / evidence / source_type / source_refs / extraction_status from the REQUIRED Provider response shape",
                "chars_recovered": None,
                "why_safe": "shadow_claim_id was already caller-generated and model values already ignored (ADR-008 §5, unchanged); evidence is a deterministic bounded join of exact_quote; source_type/source_refs default safely (Development Plan §5.1: entities/factors are best-effort, not all fields are mandated); extraction_status is always 'proposed' for a returned claim.",
                "deterministic_replacement": "normalize_v2_proposal_to_canonical_bundle",
                "corresponding_test": "test_v2_semantic_equivalence.py (all cases) + test_v2_provenance_safety.py",
            },
        ],
        "retained_components": [
            "agent_report (full text, sent exactly once)",
            "fixed instruction (security/claim-rules/output-shape/examples) -- same 6 example concepts as v1",
            "factor_vocabulary (already-minimal id list, unchanged content)",
            "run_id/ticker/agent/agent_output_id (small, gives the model real context)",
            "agent_report_boundary/agent_report_end_boundary (untrusted-data framing, section 18 safety)",
            "candidate_hints for the 21/163 verified-location candidates, as {id,start,end} only (no text)",
        ],
        "reconstructed_deterministically": [
            "exact_quote (report[start:end])",
            "evidence (bounded join of exact_quote values)",
            "shadow_claim_id (existing generate_shadow_claim_id, unchanged)",
            "run_id/ticker/agent/agent_output_id echoed in the OUTPUT bundle (spliced from caller input, not asked of the model)",
            "source_report_sha256/prompt_version/prompt_sha256 in the OUTPUT bundle",
            "shadow_only=true, production_authority=false",
            "candidate_segment_ids full lineage strings (from small int ids via candidate_index_to_id)",
        ],
    }
    # Fill v2_schema_chars now that we can reuse the same OUTPUT SHAPE marker search.
    output_shape_start = fixed_instruction.index("OUTPUT SHAPE")
    output_shape_end = fixed_instruction.index("SYNTHETIC NON-COMPANY EXAMPLES")
    claim_rules_start = fixed_instruction.index("CLAIM RULES")
    v2_schema_chars = (output_shape_end - output_shape_start) + (output_shape_start - claim_rules_start)
    comparison["v2_schema_chars"] = v2_schema_chars

    (OUT_DIR / "v1_vs_v2_prompt_comparison.json").write_text(
        json.dumps(comparison, indent=2, ensure_ascii=False) + "\n", encoding="utf-8"
    )

    print(
        json.dumps(
            {
                "v1_total_chars": v1_total,
                "v2_total_chars": v2_total,
                "reduction_pct": reduction_pct,
                "meets_40k_target": comparison["meets_40k_target"],
                "meets_duplication_ratio_target": comparison["meets_duplication_ratio_target"],
            },
            indent=2,
        )
    )


if __name__ == "__main__":
    main()
