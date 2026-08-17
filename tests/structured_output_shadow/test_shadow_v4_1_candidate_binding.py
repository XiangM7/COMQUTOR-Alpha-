"""Provider-zero tests for the additive v4.1 evidence-location protocol."""

from __future__ import annotations

from comqutor_alpha.llm_runtime.canonical_json import sha256_text
from comqutor_alpha.structure_engine.structured_output_shadow import candidate_segment_id
from comqutor_alpha.structure_engine.structured_output_shadow_prompt_v4 import (
    FROZEN_STRUCTURED_OUTPUT_SHADOW_PROMPT_V4_SHA256,
    STRUCTURED_OUTPUT_SHADOW_PROMPT_V4_SHA256,
)
from comqutor_alpha.structure_engine.structured_output_shadow_prompt_v4_1 import (
    FROZEN_STRUCTURED_OUTPUT_SHADOW_PROMPT_V4_1_SHA256,
    LOCATION_PROTOCOL_DELTA,
    SEMANTIC_RULE_DELTA,
    STRUCTURED_OUTPUT_SHADOW_PROMPT_V4_1,
    STRUCTURED_OUTPUT_SHADOW_PROMPT_V4_1_SHA256,
    STRUCTURED_OUTPUT_SHADOW_PROMPT_VERSION_V4_1,
)
from comqutor_alpha.structure_engine.structured_output_shadow_replay import (
    KNOWN_PROMPT_IDENTITY_PAIRS,
)
from comqutor_alpha.structure_engine.structured_output_shadow_v4_1 import (
    RESOLUTION_CANDIDATE_LOCAL_MULTIPLE,
    RESOLUTION_CANDIDATE_LOCAL_ZERO,
    RESOLUTION_CANDIDATE_REQUIRED,
    RESOLUTION_CANDIDATE_SOURCE_MISMATCH,
    RESOLUTION_CANDIDATE_UNKNOWN,
    RESOLUTION_DISAMBIGUATED_VIA_CANDIDATE,
    StructuredOutputShadowParserV4_1,
    resolve_supporting_evidence_v4_1,
)

QUOTE = "Demand increased 20%."
REPORT = f"Section A\n{QUOTE}\nSection B\n{QUOTE}"
SOURCE_HASH = sha256_text(REPORT)
AGENT_OUTPUT_ID = "run-duplicate:news_agent:news_report"
FIRST = REPORT.index(QUOTE)
SECOND = REPORT.rindex(QUOTE)


def _candidate(candidate_id: str, start: int, end: int, source_hash: str = SOURCE_HASH):
    return {
        "candidate_id": candidate_id,
        "run_id": "run-duplicate",
        "ticker": "TEST",
        "agent": "news_agent",
        "agent_output_id": AGENT_OUTPUT_ID,
        "source_report_sha256": source_hash,
        "source_start": start,
        "source_end": end,
        "candidate_text_sha256": sha256_text(REPORT[start:end]),
    }


FIRST_ID = candidate_segment_id(AGENT_OUTPUT_ID, 0, "first duplicate")
SECOND_ID = candidate_segment_id(AGENT_OUTPUT_ID, 1, "second duplicate")
WIDE_ID = candidate_segment_id(AGENT_OUTPUT_ID, 2, "wide duplicate")
ZERO_ID = candidate_segment_id(AGENT_OUTPUT_ID, 3, "zero duplicate")


def _resolve(candidate_id=None, *, manifest=None):
    candidates = manifest or {
        FIRST_ID: _candidate(FIRST_ID, FIRST, FIRST + len(QUOTE)),
        SECOND_ID: _candidate(SECOND_ID, SECOND, SECOND + len(QUOTE)),
    }
    return resolve_supporting_evidence_v4_1(
        report=REPORT,
        evidence={"quote": QUOTE, "candidate_id": candidate_id},
        candidate_manifest=candidates,
        source_report_sha256=SOURCE_HASH,
        run_id="run-duplicate",
        ticker="TEST",
        agent="news_agent",
        agent_output_id=AGENT_OUTPUT_ID,
    )


def test_duplicate_quote_without_candidate_is_rejected():
    resolved = _resolve()
    assert resolved.status == RESOLUTION_CANDIDATE_REQUIRED
    assert resolved.resolved_start is None


def test_candidate_a_selects_first_occurrence():
    resolved = _resolve(FIRST_ID)
    assert resolved.status == RESOLUTION_DISAMBIGUATED_VIA_CANDIDATE
    assert resolved.resolved_start == FIRST


def test_candidate_b_selects_second_occurrence():
    resolved = _resolve(SECOND_ID)
    assert resolved.status == RESOLUTION_DISAMBIGUATED_VIA_CANDIDATE
    assert resolved.resolved_start == SECOND


def test_unknown_candidate_is_rejected():
    assert _resolve("provider-created-id").status == RESOLUTION_CANDIDATE_UNKNOWN


def test_wrong_source_candidate_is_rejected():
    manifest = {
        FIRST_ID: _candidate(FIRST_ID, FIRST, FIRST + len(QUOTE), "0" * 64)
    }
    assert (
        _resolve(FIRST_ID, manifest=manifest).status
        == RESOLUTION_CANDIDATE_SOURCE_MISMATCH
    )


def test_candidate_from_wrong_run_identity_is_rejected():
    candidate = _candidate(FIRST_ID, FIRST, FIRST + len(QUOTE))
    candidate["run_id"] = "another-run"
    assert (
        _resolve(FIRST_ID, manifest={FIRST_ID: candidate}).status
        == RESOLUTION_CANDIDATE_SOURCE_MISMATCH
    )


def test_candidate_containing_both_occurrences_is_rejected():
    manifest = {WIDE_ID: _candidate(WIDE_ID, 0, len(REPORT))}
    assert (
        _resolve(WIDE_ID, manifest=manifest).status
        == RESOLUTION_CANDIDATE_LOCAL_MULTIPLE
    )


def test_candidate_containing_zero_occurrences_is_rejected():
    section_end = REPORT.index("\n")
    manifest = {ZERO_ID: _candidate(ZERO_ID, 0, section_end)}
    assert _resolve(ZERO_ID, manifest=manifest).status == RESOLUTION_CANDIDATE_LOCAL_ZERO


def test_v4_is_unchanged_and_v4_1_is_frozen_additive_location_delta():
    assert STRUCTURED_OUTPUT_SHADOW_PROMPT_V4_SHA256 == (
        FROZEN_STRUCTURED_OUTPUT_SHADOW_PROMPT_V4_SHA256
    )
    assert STRUCTURED_OUTPUT_SHADOW_PROMPT_V4_1_SHA256 == (
        FROZEN_STRUCTURED_OUTPUT_SHADOW_PROMPT_V4_1_SHA256
    )
    assert STRUCTURED_OUTPUT_SHADOW_PROMPT_VERSION_V4_1.endswith(".v4.1")
    assert SEMANTIC_RULE_DELTA == "NONE"
    assert LOCATION_PROTOCOL_DELTA == "DETERMINISTIC_CANDIDATE_BINDING"
    assert '"supporting_evidence"' in STRUCTURED_OUTPUT_SHADOW_PROMPT_V4_1
    assert "supporting_quotes" not in STRUCTURED_OUTPUT_SHADOW_PROMPT_V4_1
    assert "first-match" in STRUCTURED_OUTPUT_SHADOW_PROMPT_V4_1
    assert (
        STRUCTURED_OUTPUT_SHADOW_PROMPT_VERSION_V4_1,
        STRUCTURED_OUTPUT_SHADOW_PROMPT_V4_1_SHA256,
    ) in KNOWN_PROMPT_IDENTITY_PAIRS


def test_parser_sends_stable_ids_and_admits_only_bound_duplicate_occurrence():
    observed = {}

    def invoker(*, prompt, request):
        observed["prompt"] = prompt
        observed["request"] = request
        return {
            "claims": [
                {
                    "claim": "Demand increased 20%.",
                    "supporting_evidence": [
                        {"quote": QUOTE, "candidate_id": SECOND_ID}
                    ],
                    "entities": [],
                    "factors": [],
                    "direction": "positive",
                    "confidence": 0.8,
                }
            ],
            "abstentions": [],
        }

    candidates = [
        {
            "candidate_segment_id": FIRST_ID,
            "candidate_index": 0,
            "claim_hint": "first duplicate",
            "source_spans": [
                {"start": FIRST, "end": FIRST + len(QUOTE), "exact_quote": QUOTE}
            ],
        },
        {
            "candidate_segment_id": SECOND_ID,
            "candidate_index": 1,
            "claim_hint": "second duplicate",
            "source_spans": [
                {"start": SECOND, "end": SECOND + len(QUOTE), "exact_quote": QUOTE}
            ],
        },
    ]
    parser = StructuredOutputShadowParserV4_1(invoker, factor_vocabulary=[])
    bundle = parser.parse_report_shadow_v4_1(
        source_report=REPORT,
        run_id="run-duplicate",
        ticker="TEST",
        agent="news_agent",
        agent_output_id=AGENT_OUTPUT_ID,
        candidate_segments=candidates,
    )

    assert bundle["validation_summary"]["valid"] is True
    assert bundle["claims"][0]["source_spans"][0]["start"] == SECOND
    assert bundle["claims"][0]["candidate_segment_ids"] == [SECOND_ID]
    assert [item["candidate_id"] for item in observed["request"]["candidate_hints"]] == [
        FIRST_ID,
        SECOND_ID,
    ]
    assert "source_start" in observed["request"]["candidate_hints"][0]
    assert '"candidate_id"' in observed["prompt"]
