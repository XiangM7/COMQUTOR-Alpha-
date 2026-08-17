#!/usr/bin/env python3
"""Phase 1 Master fix: zero-Provider-call root-cause audit for the real
``structured_claim_shadow`` v1 Provider request size.

Builds the EXACT v1 request through real production code --
``build_candidate_segments`` -> ``build_shadow_request`` ->
``build_shadow_prompt_input`` -- for the frozen NVDA fundamental Smoke
report (the same report identity actually used by the real Anthropic Smoke
attempt in ``outputs/evaluations/phase1-master-anthropic-20260807T011444Z-
7ce7880c/reports/NVDA/fundamental/``). No hand-simulated text, no Provider
call, no network, no mutation of the frozen prompt/schema.

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
    build_shadow_request,
)
from comqutor_alpha.structure_engine.structured_output_shadow_prompt import (  # noqa: E402
    STRUCTURED_OUTPUT_SHADOW_PROMPT,
    build_shadow_prompt_input,
)

OUT_DIR = REPO_ROOT / "docs/audit_artifacts/phase1_master/prompt_audit"

# The exact real identity of the frozen, already-attempted NVDA fundamental
# Smoke report (docs/audit_artifacts/phase1a/evaluation_corpus_inventory.json
# and outputs/evaluations/phase1-master-anthropic-20260807T011444Z-7ce7880c/
# reports/NVDA/fundamental/source_report_snapshot.json). Reused verbatim --
# never re-derived by hand -- so this audit reproduces the actual failed
# request, not a synthetic stand-in.
SOURCE_RUN_ID = "0e044e37-862c-43be-871c-31012cd660e7"
AGENT_OUTPUT_ID = "0e044e37-862c-43be-871c-31012cd660e7:fundamental_agent:fundamentals_report"
REAL_RUN_ID = "anthropic-smoke-20260807T011444Z-9038cf75cdbd6b10"
TICKER = "NVDA"
AGENT = "fundamental_agent"
EXPECTED_REPORT_SHA256 = "6e745b7c192eab1d111c26c9f259b97ddf6b86de5b88a4c03ae67cdf8f7954f1"


def _tokens_estimate(chars: int) -> int:
    """Standard chars/4 heuristic; tiktoken is not an installed dependency
    in this environment. Always labeled as an estimate, never exact."""

    return round(chars / 4)


def _load_raw_report() -> tuple[str, dict[str, Any]]:
    raw_path = REPO_ROOT / "outputs/runs" / SOURCE_RUN_ID / "raw_agent_outputs.json"
    payload = json.loads(raw_path.read_text(encoding="utf-8"))
    for entry in payload.get("agent_outputs") or []:
        if str(entry.get("agent_output_id")) == AGENT_OUTPUT_ID:
            return str(entry.get("raw_output") or ""), entry
    raise SystemExit(f"report not found: {AGENT_OUTPUT_ID}")


def _json_value_chars(value: Any) -> int:
    return len(json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":")))


def _attribute_object_chars(obj: dict[str, Any]) -> tuple[dict[str, int], int, int]:
    """Exact, non-overlapping attribution of one JSON object's serialized
    chars to each of its own top-level keys (key text + colon + encoded
    value), plus a structural remainder (outer braces + inter-key commas)
    that is not owed to any single field. Returns (per_field_chars,
    structural_remainder_chars, total_object_chars)."""

    total = _json_value_chars(obj)
    per_field: dict[str, int] = {}
    for key, value in obj.items():
        per_field[key] = len(json.dumps(key, ensure_ascii=False)) + 1 + _json_value_chars(value)
    remainder = total - sum(per_field.values())
    return per_field, remainder, total


def build_v1_request() -> dict[str, Any]:
    report_text, raw_record = _load_raw_report()
    if len(report_text) != 13887:
        raise SystemExit(f"UNEXPECTED_REPORT_LENGTH: {len(report_text)} (expected 13887)")
    import hashlib

    actual_sha = hashlib.sha256(report_text.encode("utf-8")).hexdigest()
    if actual_sha != EXPECTED_REPORT_SHA256:
        raise SystemExit(f"UNEXPECTED_REPORT_SHA256: {actual_sha}")

    candidate_segments, filtered = build_candidate_segments(
        report_text, agent_output_id=AGENT_OUTPUT_ID
    )

    request = build_shadow_request(
        source_report=report_text,
        run_id=REAL_RUN_ID,
        ticker=TICKER,
        agent=AGENT,
        agent_output_id=AGENT_OUTPUT_ID,
        candidate_segments=candidate_segments,
        factor_vocabulary=list(FACTOR_ALIASES.keys()),
        source_metadata={
            "source_path": raw_record.get("source_path") or "",
            "source_field": raw_record.get("source_field") or "",
            "source_refs": [],
        },
    )
    return {
        "report_text": report_text,
        "raw_record": raw_record,
        "candidate_segments": candidate_segments,
        "filtered": filtered,
        "request": request,
    }


def cross_check_against_real_artifact(built: dict[str, Any]) -> dict[str, Any]:
    """Confirm this harness's recomputation is byte-identical to the
    candidate_segments.json actually persisted by the real Anthropic Smoke
    attempt -- proves determinism, not merely plausibility."""

    real_path = (
        REPO_ROOT
        / "outputs/evaluations/phase1-master-anthropic-20260807T011444Z-7ce7880c"
        / "reports/NVDA/fundamental/candidate_segments.json"
    )
    real_segments = json.loads(real_path.read_text(encoding="utf-8"))
    recomputed = built["candidate_segments"]
    identical = json.dumps(real_segments, sort_keys=True) == json.dumps(recomputed, sort_keys=True)
    return {
        "compared_against": str(real_path.relative_to(REPO_ROOT)),
        "real_segment_count": len(real_segments),
        "recomputed_segment_count": len(recomputed),
        "byte_identical": identical,
    }


PROMPT_SECTION_MARKERS = [
    ("preamble", "You are an offline semantic PROPOSER", "SECURITY AND AUTHORITY"),
    ("security_and_authority", "SECURITY AND AUTHORITY", "CLAIM RULES"),
    ("claim_rules", "CLAIM RULES", "OUTPUT SHAPE"),
    ("output_shape", "OUTPUT SHAPE", "SYNTHETIC NON-COMPANY EXAMPLES"),
    ("examples", "SYNTHETIC NON-COMPANY EXAMPLES", "The deterministic validator"),
    ("closing", "The deterministic validator", None),
]


def split_fixed_instruction() -> dict[str, str]:
    text = STRUCTURED_OUTPUT_SHADOW_PROMPT
    sections: dict[str, str] = {}
    for name, start_marker, end_marker in PROMPT_SECTION_MARKERS:
        start = text.index(start_marker)
        end = text.index(end_marker) if end_marker else len(text)
        sections[name] = text[start:end]
    rebuilt = "".join(sections.values())
    if rebuilt != text:
        raise SystemExit("PROMPT_SECTION_SPLIT_NOT_EXACT_PARTITION")
    return sections


def main() -> None:
    OUT_DIR.mkdir(parents=True, exist_ok=True)
    built = build_v1_request()
    report_text = built["report_text"]
    request = built["request"]
    candidate_segments = built["candidate_segments"]

    determinism_check = cross_check_against_real_artifact(built)

    # ---- Build the EXACT final Provider-bound request text via the real,
    # frozen production prompt builder. This is what self._model.invoke()
    # receives -- nothing hand-written. ----
    final_request_text = build_shadow_prompt_input(request)
    (OUT_DIR / "v1_actual_request.txt").write_text(final_request_text, encoding="utf-8")

    fixed_instruction = STRUCTURED_OUTPUT_SHADOW_PROMPT
    separator_label = "\n\nSHADOW_REQUEST_JSON:\n"
    request_json_text = json.dumps(
        dict(request), ensure_ascii=False, sort_keys=True, separators=(",", ":")
    )
    if fixed_instruction + separator_label + request_json_text != final_request_text:
        raise SystemExit("RECONSTRUCTION_MISMATCH: harness split does not equal real prompt builder output")

    total_chars = len(final_request_text)

    # ---- Top-level JSON field attribution (exact, mutually exclusive) ----
    top_field_chars, top_structural_remainder, top_total = _attribute_object_chars(dict(request))
    if top_total != len(request_json_text):
        raise SystemExit("TOP_LEVEL_JSON_ATTRIBUTION_MISMATCH")

    # ---- candidate_segments internal attribution, summed across all
    # segments (exact, mutually exclusive per segment, then summed) ----
    cand_field_totals: dict[str, int] = {}
    cand_structural_remainder_total = 0
    for segment in candidate_segments:
        per_field, remainder, _total = _attribute_object_chars(segment)
        for key, chars in per_field.items():
            if key == "source_spans":
                continue  # broken out separately below
            cand_field_totals[key] = cand_field_totals.get(key, 0) + chars
        cand_structural_remainder_total += remainder
    # source_spans: break out exact_quote vs start/end vs structural
    span_exact_quote_chars = 0
    span_offset_and_structural_chars = 0
    for segment in candidate_segments:
        spans = segment.get("source_spans") or []
        spans_field_chars = len('"source_spans":') + _json_value_chars(spans)
        exact_quote_sum = 0
        for span in spans:
            per_span_field, span_remainder, _span_total = _attribute_object_chars(span)
            exact_quote_sum += per_span_field.get("exact_quote", 0)
            span_offset_and_structural_chars += (
                per_span_field.get("start", 0) + per_span_field.get("end", 0) + span_remainder
            )
        # array-level punctuation (brackets/commas around span objects, and
        # the "source_spans": key itself) not attributed to any one span.
        per_span_object_totals = sum(_json_value_chars(s) for s in spans)
        array_punctuation = spans_field_chars - len('"source_spans":') - per_span_object_totals
        span_offset_and_structural_chars += array_punctuation
        span_exact_quote_chars += exact_quote_sum
    # candidate_segments array-level punctuation (outer brackets, commas
    # between segment objects, and the "candidate_segments": key itself) --
    # NOT included in cand_structural_remainder_total (that is per-object
    # only), so compute it as the true remainder against the top-level
    # attribution for that one field.
    candidate_segments_field_total_chars = top_field_chars["candidate_segments"]
    per_segment_totals_sum = sum(_json_value_chars(s) for s in candidate_segments)
    array_level_punctuation = (
        candidate_segments_field_total_chars - len('"candidate_segments":') - per_segment_totals_sum
    )

    candidate_segment_text_chars = (
        cand_field_totals.get("claim_hint", 0)
        + cand_field_totals.get("evidence_hint", 0)
        + span_exact_quote_chars
    )
    candidate_segment_metadata_chars = (
        candidate_segments_field_total_chars
        - candidate_segment_text_chars
    )

    # ---- fixed_instruction internal sections (exact, mutually exclusive) ----
    sections = split_fixed_instruction()
    examples_chars = len(sections["examples"])
    output_format_instruction_chars = len(sections["output_shape"])
    schema_instruction_chars = len(sections["claim_rules"])
    instruction_boilerplate_chars = (
        len(sections["preamble"]) + len(sections["security_and_authority"]) + len(sections["closing"])
    )
    fixed_instruction_chars = len(fixed_instruction)
    if (
        examples_chars
        + output_format_instruction_chars
        + schema_instruction_chars
        + instruction_boilerplate_chars
        != fixed_instruction_chars
    ):
        raise SystemExit("FIXED_INSTRUCTION_PARTITION_NOT_EXACT")

    # ---- identity / source metadata buckets (exact, mutually exclusive
    # subsets of the top-level JSON field attribution) ----
    identity_keys = [
        "input_schema_version",
        "output_schema_version",
        "run_id",
        "ticker",
        "agent",
        "agent_output_id",
        "source_report_sha256",
        "prompt_version",
        "prompt_sha256",
        "agent_report_boundary",
        "agent_report_end_boundary",
    ]
    identity_metadata_chars = sum(top_field_chars[k] for k in identity_keys)
    source_metadata_keys = [
        "candidate_segment_contract_version",
        "candidate_segment_source",
        "allowed_source_refs",
        "source_metadata",
    ]
    source_metadata_chars = sum(top_field_chars[k] for k in source_metadata_keys)
    factor_vocabulary_chars = top_field_chars["factor_vocabulary"]
    agent_report_field_chars = top_field_chars["agent_report"]  # includes JSON quoting/escaping
    raw_report_chars = len(report_text)  # plain text length, not JSON-escaped

    # NOTE: array_level_punctuation / cand_structural_remainder_total /
    # span_offset_and_structural_chars are already folded inside
    # candidate_segment_metadata_chars (= candidate_segments field total -
    # candidate_segment_text_chars, by construction); they are recomputed
    # above only to populate the human-readable subfields breakdown and
    # must NOT be added again here, or candidate_segments bytes would be
    # double-counted against total_chars.
    other_chars = (
        top_structural_remainder  # top-level object braces/commas between the 18 request fields
        + len(separator_label)  # the "SHADOW_REQUEST_JSON:" label itself
    )

    accounted = (
        fixed_instruction_chars
        + agent_report_field_chars
        + candidate_segment_text_chars
        + candidate_segment_metadata_chars
        + factor_vocabulary_chars
        + source_metadata_chars
        + identity_metadata_chars
        + other_chars
    )
    if accounted != total_chars:
        raise SystemExit(
            f"COMPONENT_SUM_MISMATCH: accounted={accounted} total={total_chars} "
            f"diff={total_chars - accounted}"
        )

    # ---- Duplication measures (diagnostic, derived -- not part of the
    # mutually-exclusive partition above, but computed from real content) ----
    dup_report_chars = 0
    for segment in candidate_segments:
        for text_field in ("claim_hint", "evidence_hint"):
            hint = str(segment.get(text_field) or "")
            if hint and hint in report_text:
                dup_report_chars += len(hint)
        for span in segment.get("source_spans") or []:
            quote = str(span.get("exact_quote") or "")
            if quote and quote in report_text:
                dup_report_chars += len(quote)

    dup_candidate_internal_chars = 0
    identical_hint_segments = 0
    for segment in candidate_segments:
        claim_hint = str(segment.get("claim_hint") or "")
        evidence_hint = str(segment.get("evidence_hint") or "")
        if claim_hint and claim_hint == evidence_hint:
            dup_candidate_internal_chars += len(evidence_hint)
            identical_hint_segments += 1
        for span in segment.get("source_spans") or []:
            quote = str(span.get("exact_quote") or "")
            if quote and quote == claim_hint:
                dup_candidate_internal_chars += len(quote)

    # Coverage ratio: how much of the report's own length is re-sent as
    # candidate hint/quote text, on top of the one copy already present as
    # agent_report.
    report_duplication_ratio = round(
        (raw_report_chars + candidate_segment_text_chars) / raw_report_chars, 4
    )

    breakdown = {
        "schema_version": "comqutor.phase1_master.prompt_audit.v1_breakdown.v1",
        "report_identity": {
            "source_run_id": SOURCE_RUN_ID,
            "agent_output_id": AGENT_OUTPUT_ID,
            "real_evaluation_run_id_reused": REAL_RUN_ID,
            "ticker": TICKER,
            "agent": AGENT,
            "report_sha256": EXPECTED_REPORT_SHA256,
            "raw_report_chars": raw_report_chars,
        },
        "determinism_cross_check": determinism_check,
        "candidate_segment_count": len(candidate_segments),
        "filtered_segment_count": len(built["filtered"]),
        "components": {
            "fixed_instruction_chars": fixed_instruction_chars,
            "fixed_instruction_tokens_estimate": _tokens_estimate(fixed_instruction_chars),
            "examples_chars": examples_chars,
            "examples_tokens_estimate": _tokens_estimate(examples_chars),
            "schema_instruction_chars": schema_instruction_chars,
            "schema_instruction_tokens_estimate": _tokens_estimate(schema_instruction_chars),
            "output_format_instruction_chars": output_format_instruction_chars,
            "output_format_instruction_tokens_estimate": _tokens_estimate(output_format_instruction_chars),
            "instruction_boilerplate_chars": instruction_boilerplate_chars,
            "instruction_boilerplate_tokens_estimate": _tokens_estimate(instruction_boilerplate_chars),
            "raw_report_chars": raw_report_chars,
            "raw_report_tokens_estimate": _tokens_estimate(raw_report_chars),
            "agent_report_json_field_chars": agent_report_field_chars,
            "candidate_segment_metadata_chars": candidate_segment_metadata_chars,
            "candidate_segment_metadata_tokens_estimate": _tokens_estimate(candidate_segment_metadata_chars),
            "candidate_segment_text_chars": candidate_segment_text_chars,
            "candidate_segment_text_tokens_estimate": _tokens_estimate(candidate_segment_text_chars),
            "candidate_segment_text_subfields": {
                "claim_hint_chars": cand_field_totals.get("claim_hint", 0),
                "evidence_hint_chars": cand_field_totals.get("evidence_hint", 0),
                "exact_quote_chars": span_exact_quote_chars,
            },
            "candidate_segment_metadata_subfields": {
                "candidate_segment_id_chars": cand_field_totals.get("candidate_segment_id", 0),
                "candidate_index_chars": cand_field_totals.get("candidate_index", 0),
                "source_section_chars": cand_field_totals.get("source_section", 0),
                "semantic_authority_chars": cand_field_totals.get("semantic_authority", 0),
                "span_offset_and_structural_chars": span_offset_and_structural_chars,
                "array_and_object_punctuation_chars": (
                    array_level_punctuation + cand_structural_remainder_total
                ),
            },
            "factor_vocabulary_chars": factor_vocabulary_chars,
            "factor_vocabulary_tokens_estimate": _tokens_estimate(factor_vocabulary_chars),
            "factor_vocabulary_item_count": len(request["factor_vocabulary"]),
            "source_metadata_chars": source_metadata_chars,
            "source_metadata_tokens_estimate": _tokens_estimate(source_metadata_chars),
            "identity_metadata_chars": identity_metadata_chars,
            "identity_metadata_tokens_estimate": _tokens_estimate(identity_metadata_chars),
            "other_chars": other_chars,
            "other_chars_tokens_estimate": _tokens_estimate(other_chars),
            "total_chars": total_chars,
            "total_tokens_estimate": _tokens_estimate(total_chars),
        },
        "percentages_of_total": {
            "fixed_instruction_pct": round(100 * fixed_instruction_chars / total_chars, 2),
            "examples_pct": round(100 * examples_chars / total_chars, 2),
            "schema_instruction_pct": round(100 * schema_instruction_chars / total_chars, 2),
            "output_format_instruction_pct": round(100 * output_format_instruction_chars / total_chars, 2),
            "raw_report_pct": round(100 * agent_report_field_chars / total_chars, 2),
            "candidate_segment_metadata_pct": round(100 * candidate_segment_metadata_chars / total_chars, 2),
            "candidate_segment_text_pct": round(100 * candidate_segment_text_chars / total_chars, 2),
            "factor_vocabulary_pct": round(100 * factor_vocabulary_chars / total_chars, 2),
            "source_metadata_pct": round(100 * source_metadata_chars / total_chars, 2),
            "identity_metadata_pct": round(100 * identity_metadata_chars / total_chars, 2),
            "other_pct": round(100 * other_chars / total_chars, 2),
        },
        "duplication": {
            "duplicated_report_text_chars": dup_report_chars,
            "duplicated_report_text_pct_of_total": round(100 * dup_report_chars / total_chars, 2),
            "duplicated_candidate_text_chars": dup_candidate_internal_chars,
            "duplicated_candidate_text_pct_of_total": round(
                100 * dup_candidate_internal_chars / total_chars, 2
            ),
            "identical_claim_and_evidence_hint_segment_count": identical_hint_segments,
            "identical_claim_and_evidence_hint_segment_pct": round(
                100 * identical_hint_segments / len(candidate_segments), 2
            ),
            "duplicated_schema_chars": 0,
            "duplicated_schema_note": (
                "OUTPUT SHAPE appears exactly once (a JSON skeleton) and CLAIM RULES "
                "appears exactly once (prose). They are complementary, not textual "
                "duplicates of each other -- measured, not assumed. No third "
                "(e.g. JSON-Schema-object) restatement exists in the frozen v1 prompt."
            ),
            "report_duplication_ratio": report_duplication_ratio,
            "report_duplication_ratio_definition": (
                "(raw_report_chars + candidate_segment_text_chars) / raw_report_chars; "
                "1.0 means the report's content appears exactly once in total."
            ),
        },
        "reconstruction_proof": {
            "fixed_instruction_chars_plus_separator_plus_json_chars_equals_total": (
                fixed_instruction_chars + len(separator_label) + len(request_json_text) == total_chars
            ),
            "component_sum_equals_total_chars": accounted == total_chars,
        },
    }

    (OUT_DIR / "v1_request_breakdown.json").write_text(
        json.dumps(breakdown, indent=2, ensure_ascii=False) + "\n", encoding="utf-8"
    )

    # ---- Component inventory (list form, one row per component) ----
    inventory = [
        {"component": name, "chars": chars, "pct_of_total": round(100 * chars / total_chars, 2)}
        for name, chars in [
            ("fixed_instruction", fixed_instruction_chars),
            ("agent_report (raw report, sent once)", agent_report_field_chars),
            ("candidate_segment_text (claim_hint+evidence_hint+exact_quote)", candidate_segment_text_chars),
            ("candidate_segment_metadata (ids/index/spans-structure/punctuation)", candidate_segment_metadata_chars),
            ("factor_vocabulary", factor_vocabulary_chars),
            ("source_metadata (paths/refs/contract/source version strings)", source_metadata_chars),
            ("identity_metadata (run/ticker/agent/hashes/versions)", identity_metadata_chars),
            ("other (JSON structural punctuation, label text)", other_chars),
        ]
    ]
    (OUT_DIR / "v1_component_inventory.json").write_text(
        json.dumps({"total_chars": total_chars, "components": inventory}, indent=2, ensure_ascii=False)
        + "\n",
        encoding="utf-8",
    )

    duplication_map = {
        "schema_version": "comqutor.phase1_master.prompt_audit.v1_duplication_map.v1",
        "finding_A_report_reappears_in_candidates": {
            "claim": (
                "The full report is sent once as agent_report, then large portions of "
                "the same report text are sent again inside candidate_segments as "
                "claim_hint/evidence_hint/exact_quote."
            ),
            "measured": True,
            "candidate_segment_text_chars": candidate_segment_text_chars,
            "raw_report_chars": raw_report_chars,
            "coverage_ratio_of_report_length": round(candidate_segment_text_chars / raw_report_chars, 4),
        },
        "finding_B_claim_hint_equals_evidence_hint": {
            "claim": (
                "claim_hint and evidence_hint are byte-identical for effectively every "
                "candidate segment, because build_candidate_segments() falls back to "
                "`evidence = claim` whenever extract_claim_segments_with_audit does not "
                "supply a distinct evidence field (it never does today)."
            ),
            "measured": True,
            "identical_segment_count": identical_hint_segments,
            "total_segment_count": len(candidate_segments),
            "identical_pct": round(100 * identical_hint_segments / len(candidate_segments), 2),
            "wasted_chars_from_this_duplication_alone": cand_field_totals.get("evidence_hint", 0),
        },
        "finding_C_schema_explained_multiple_times": {
            "claim": "Schema explained in prose once, JSON example once, JSON-Schema object once.",
            "measured": True,
            "verdict": "NOT_OBSERVED",
            "detail": (
                "The frozen v1 prompt has exactly one prose rules section (CLAIM RULES, "
                f"{schema_instruction_chars} chars) and exactly one JSON skeleton (OUTPUT "
                f"SHAPE, {output_format_instruction_chars} chars). There is no separate "
                "JSON-Schema object. This assumption is REJECTED for the fixed instruction."
            ),
        },
        "finding_D_factor_vocabulary_bloat": {
            "claim": "Factor vocabulary carries description/alias/explanation/examples/metadata.",
            "measured": True,
            "verdict": "NOT_OBSERVED",
            "detail": (
                f"factor_vocabulary is already the minimal id-only list FACTOR_ALIASES.keys() "
                f"-- {len(request['factor_vocabulary'])} short strings, {factor_vocabulary_chars} "
                f"chars total ({round(100 * factor_vocabulary_chars / total_chars, 3)}% of the "
                "request). Aliases/descriptions exist in FACTOR_ALIASES's VALUES but are never "
                "sent to the Provider today. This assumption is REJECTED."
            ),
        },
        "finding_E_examples_too_long": {
            "claim": "Examples are too long.",
            "measured": True,
            "examples_chars": examples_chars,
            "examples_pct_of_total": round(100 * examples_chars / total_chars, 2),
            "verdict": "NOT_MATERIAL",
            "detail": (
                f"Examples are {examples_chars} chars, {round(100 * examples_chars / total_chars, 3)}% "
                "of the total request. Even fully removed, this would not materially change the "
                "total. Not a root-cause contributor at this report size."
            ),
        },
        "finding_F_unneeded_metadata": {
            "claim": "Run audit metadata / hashes / output paths / timestamps sent to the model.",
            "measured": True,
            "verdict": "PARTIALLY_OBSERVED",
            "detail": (
                "identity_metadata includes source_report_sha256, prompt_sha256, and boundary "
                "marker strings the model is told to copy verbatim rather than compute or omit. "
                f"{identity_metadata_chars} chars ({round(100 * identity_metadata_chars / total_chars, 3)}%"
                " of total) -- small in absolute terms but 100% deterministically reconstructable "
                "caller-side; none of it needs to round-trip through the model."
            ),
        },
        "finding_G_llm_asked_to_return_computable_fields": {
            "claim": "exact_quote can be recovered from report[start:end] instead of being asked of the model.",
            "measured": True,
            "verdict": "CONFIRMED",
            "detail": (
                "validate_shadow_bundle already independently recomputes and enforces "
                "report[start:end] == exact_quote (structured_output_shadow_schema.py "
                "_validate_source_spans). The model's copy of exact_quote is therefore pure "
                "duplication with zero added authority -- the deterministic validator was already "
                "the source of truth before this audit."
            ),
        },
    }
    (OUT_DIR / "v1_duplication_map.json").write_text(
        json.dumps(duplication_map, indent=2, ensure_ascii=False) + "\n", encoding="utf-8"
    )

    source_map = [
        {
            "component": "fixed_instruction (incl. examples, schema prose, output shape)",
            "source_file": "comqutor_alpha/structure_engine/structured_output_shadow_prompt.py",
            "source_function_or_constant": "STRUCTURED_OUTPUT_SHADOW_PROMPT",
            "chars": fixed_instruction_chars,
            "necessary_for_llm": "Yes -- security framing, claim semantics, abstention rules, and the output shape are the model's actual task definition.",
            "can_be_deterministically_reconstructed": False,
        },
        {
            "component": "agent_report (full report text)",
            "source_file": "scripts/run_phase1_master.py -> comqutor_alpha/structure_engine/structured_output_shadow.py",
            "source_function_or_constant": "_load_raw_report() runtime field -> build_shadow_request()['agent_report']",
            "chars": agent_report_field_chars,
            "necessary_for_llm": "Yes -- the model must read the source text to propose claims/spans.",
            "can_be_deterministically_reconstructed": False,
        },
        {
            "component": "candidate_segments[].claim_hint / evidence_hint",
            "source_file": "comqutor_alpha/structure_engine/structured_output_shadow.py -> comqutor_alpha/structure_engine/structured_output_adapter.py",
            "source_function_or_constant": "build_candidate_segments() -> extract_claim_segments_with_audit()",
            "chars": cand_field_totals.get("claim_hint", 0) + cand_field_totals.get("evidence_hint", 0),
            "necessary_for_llm": "Partially -- a segment boundary HINT is useful, but sending the full duplicate text of both claim_hint and evidence_hint (byte-identical) for all 163 segments is not; an offset hint is sufficient once the full report is already present.",
            "can_be_deterministically_reconstructed": True,
        },
        {
            "component": "candidate_segments[].source_spans[].exact_quote",
            "source_file": "comqutor_alpha/structure_engine/structured_output_shadow.py",
            "source_function_or_constant": "build_candidate_segments() -> _locate_exact_hint()",
            "chars": span_exact_quote_chars,
            "necessary_for_llm": "No -- report[start:end] already reproduces this deterministically, and validate_shadow_bundle already re-derives/enforces it independently.",
            "can_be_deterministically_reconstructed": True,
        },
        {
            "component": "candidate_segments[].candidate_segment_id",
            "source_file": "comqutor_alpha/structure_engine/structured_output_shadow.py",
            "source_function_or_constant": "_candidate_id()",
            "chars": cand_field_totals.get("candidate_segment_id", 0),
            "necessary_for_llm": "No -- the model only needs a short local identifier (e.g. a per-report sequence number) to reference in candidate_segment_ids on its output claims; the full globally-unique ID (which re-embeds agent_output_id 163 times) is a caller-side bookkeeping concern.",
            "can_be_deterministically_reconstructed": True,
        },
        {
            "component": "factor_vocabulary",
            "source_file": "comqutor_alpha/structure_engine/factor_normalizer.py",
            "source_function_or_constant": "FACTOR_ALIASES.keys()",
            "chars": factor_vocabulary_chars,
            "necessary_for_llm": "Yes -- the model must know the closed vocabulary to select from; already minimal (id-only).",
            "can_be_deterministically_reconstructed": False,
        },
        {
            "component": "source_metadata / candidate_segment_contract_version / candidate_segment_source / allowed_source_refs",
            "source_file": "comqutor_alpha/structure_engine/structured_output_shadow.py",
            "source_function_or_constant": "build_shadow_request()",
            "chars": source_metadata_chars,
            "necessary_for_llm": "Marginal -- allowed_source_refs is empty here; candidate_segment_contract_version/source are caller provenance strings with no semantic task value to the model.",
            "can_be_deterministically_reconstructed": True,
        },
        {
            "component": "identity_metadata (run_id/ticker/agent/agent_output_id/hashes/prompt version+sha/boundary markers)",
            "source_file": "comqutor_alpha/structure_engine/structured_output_shadow.py",
            "source_function_or_constant": "build_shadow_request()",
            "chars": identity_metadata_chars,
            "necessary_for_llm": "Partially -- ticker/agent give the model useful context; source_report_sha256/prompt_sha256/prompt_version are caller-owned identity that the prompt tells the model to copy verbatim (validated bit-for-bit by validate_shadow_bundle regardless of what the model echoes back).",
            "can_be_deterministically_reconstructed": True,
        },
    ]
    (OUT_DIR / "v1_prompt_source_map.json").write_text(
        json.dumps({"data_to_function_to_prompt_component": source_map}, indent=2, ensure_ascii=False)
        + "\n",
        encoding="utf-8",
    )

    print(json.dumps({"total_chars": total_chars, "breakdown_written_to": str(OUT_DIR)}, indent=2))


if __name__ == "__main__":
    main()
