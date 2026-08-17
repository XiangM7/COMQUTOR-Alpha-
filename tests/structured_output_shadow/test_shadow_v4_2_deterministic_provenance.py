"""Phase 1 Master §5.1 v4.2 repair: focused, deterministic, zero-Provider
tests for the confirmed root-cause fix (candidate binding removed;
duplicate exact quotes accept the earliest occurrence instead of
requiring Provider-selected disambiguation). See
docs/audit_artifacts/phase1_master/phase1_v4_1_location_root_cause.md for
the real-data diagnosis this repair addresses.
"""

from __future__ import annotations

import inspect

import pytest

from comqutor_alpha.structure_engine.structured_output_shadow_prompt_v4 import (
    STRUCTURED_OUTPUT_SHADOW_PROMPT_V4,
)
from comqutor_alpha.structure_engine.structured_output_shadow_prompt_v4_2 import (
    CANDIDATE_BINDING_ACTIVE,
    STRUCTURED_OUTPUT_SHADOW_PROMPT_V4_2,
    STRUCTURED_OUTPUT_SHADOW_PROMPT_V4_2_SHA256,
    STRUCTURED_OUTPUT_SHADOW_PROMPT_VERSION_V4_2,
)
from comqutor_alpha.structure_engine.structured_output_shadow_v4_2 import (
    INACTIVE_V4_1_CANDIDATE_ONLY_FAILURE_MODES,
    RESOLUTION_DUPLICATE_ACCEPTED_EARLIEST_OCCURRENCE,
    RESOLUTION_INVALID_QUOTE,
    RESOLUTION_NO_EXACT_MATCH,
    RESOLUTION_STATUSES,
    RESOLUTION_STATUSES_LOCATED,
    RESOLUTION_UNIQUE_EXACT_MATCH,
    SELECTION_POLICY_FIRST_EXACT_OCCURRENCE,
    SELECTION_POLICY_UNIQUE_EXACT_OCCURRENCE,
    StructuredOutputShadowParserV4_2,
    build_shadow_request_v4_2,
    normalize_v4_2_proposal_to_canonical_bundle,
    provider_proposal_shape_valid_v4_2,
    resolve_supporting_quote_v4_2,
)

# ---------------------------------------------------------------------------
# TEST 1 -- unique exact match
# ---------------------------------------------------------------------------


def test_1_unique_exact_match_accepts_with_correct_offset():
    source = "abc\nEvidence sentence\nxyz"
    resolved = resolve_supporting_quote_v4_2(report=source, quote="Evidence sentence")
    assert resolved.status == RESOLUTION_UNIQUE_EXACT_MATCH
    assert resolved.exact_match_count == 1
    assert resolved.exact_match_offsets == (source.index("Evidence sentence"),)
    assert resolved.start == source.index("Evidence sentence")
    assert resolved.end == resolved.start + len("Evidence sentence")
    assert resolved.selection_policy == SELECTION_POLICY_UNIQUE_EXACT_OCCURRENCE
    assert resolved.duplicate_exact_quote is False


# ---------------------------------------------------------------------------
# TEST 2 -- two identical matches
# ---------------------------------------------------------------------------


def test_2_two_identical_matches_accepts_earliest_and_records_all_offsets():
    source = "AAA\nDuplicate text here\nBBB\nDuplicate text here\nCCC"
    offsets = [source.index("Duplicate text here")]
    offsets.append(source.index("Duplicate text here", offsets[0] + 1))
    resolved = resolve_supporting_quote_v4_2(report=source, quote="Duplicate text here")
    assert resolved.status == RESOLUTION_DUPLICATE_ACCEPTED_EARLIEST_OCCURRENCE
    assert resolved.exact_match_count == 2
    assert resolved.exact_match_offsets == tuple(offsets)
    assert resolved.selected_match_index == 0
    assert resolved.start == offsets[0] == min(offsets)
    assert resolved.selection_policy == SELECTION_POLICY_FIRST_EXACT_OCCURRENCE
    assert resolved.duplicate_exact_quote is True


# ---------------------------------------------------------------------------
# TEST 3 -- three identical matches
# ---------------------------------------------------------------------------


def test_3_three_identical_matches_accepts_earliest():
    source = "X quote here X quote here X quote here X"
    resolved = resolve_supporting_quote_v4_2(report=source, quote="quote here")
    assert resolved.status == RESOLUTION_DUPLICATE_ACCEPTED_EARLIEST_OCCURRENCE
    assert resolved.exact_match_count == 3
    assert resolved.start == min(resolved.exact_match_offsets)
    assert resolved.start == source.index("quote here")


# ---------------------------------------------------------------------------
# TEST 4 -- zero match
# ---------------------------------------------------------------------------


def test_4_zero_match_rejects():
    resolved = resolve_supporting_quote_v4_2(report="abc def ghi", quote="not present anywhere")
    assert resolved.status == RESOLUTION_NO_EXACT_MATCH
    assert resolved.exact_match_count == 0
    assert resolved.start is None
    assert resolved.end is None
    assert resolved.status not in RESOLUTION_STATUSES_LOCATED


# ---------------------------------------------------------------------------
# TEST 5 -- wrong source (quote exists elsewhere, not here)
# ---------------------------------------------------------------------------


def test_5_quote_present_in_a_different_report_but_not_this_one_rejects():
    other_report = "The quarterly revenue grew 14% year over year."
    this_report = "The quarterly revenue grew 9% year over year."
    assert "The quarterly revenue grew 14% year over year." in other_report
    resolved = resolve_supporting_quote_v4_2(
        report=this_report, quote="The quarterly revenue grew 14% year over year."
    )
    assert resolved.status == RESOLUTION_NO_EXACT_MATCH


# ---------------------------------------------------------------------------
# TEST 6 -- Markdown exactness, no repair
# ---------------------------------------------------------------------------


def test_6_markdown_stripped_quote_is_not_repaired_and_rejects():
    source = "Revenue grew **14%** year over year, beating estimates."
    stripped_quote = "Revenue grew 14% year over year, beating estimates."
    resolved = resolve_supporting_quote_v4_2(report=source, quote=stripped_quote)
    assert resolved.status == RESOLUTION_NO_EXACT_MATCH
    exact = resolve_supporting_quote_v4_2(report=source, quote=source)
    assert exact.status == RESOLUTION_UNIQUE_EXACT_MATCH


# ---------------------------------------------------------------------------
# TEST 7 -- Unicode / punctuation exactness, no normalization
# ---------------------------------------------------------------------------


def test_7_unicode_and_punctuation_variants_are_not_normalized_into_a_match():
    source = "The CEO said “we are confident” in a statement."  # curly quotes
    straight_quote_variant = 'The CEO said "we are confident" in a statement.'
    resolved = resolve_supporting_quote_v4_2(report=source, quote=straight_quote_variant)
    assert resolved.status == RESOLUTION_NO_EXACT_MATCH
    exact = resolve_supporting_quote_v4_2(report=source, quote=source)
    assert exact.status == RESOLUTION_UNIQUE_EXACT_MATCH


# ---------------------------------------------------------------------------
# TEST 8 -- multi-evidence claim: one unique + one duplicate, independently resolved
# ---------------------------------------------------------------------------


def test_8_multi_evidence_claim_resolves_unique_and_duplicate_independently():
    source = (
        "Unique opening statement.\n"
        "Repeated closing remark.\n"
        "Middle filler text.\n"
        "Repeated closing remark.\n"
    )
    proposal = {
        "claims": [
            {
                "claim": "Combined claim citing two spans.",
                "supporting_quotes": ["Unique opening statement.", "Repeated closing remark."],
                "entities": [],
                "factors": [],
                "direction": "neutral",
                "confidence": 0.8,
            }
        ],
        "abstentions": [],
    }
    bundle, log = normalize_v4_2_proposal_to_canonical_bundle(
        proposal,
        source_report=source,
        run_id="r",
        ticker="T",
        agent="a",
        agent_output_id="id",
    )
    spans = bundle["claims"][0]["source_spans"]
    assert len(spans) == 2
    assert spans[0]["exact_quote"] == "Unique opening statement."
    assert spans[0]["start"] == source.index("Unique opening statement.")
    assert spans[1]["exact_quote"] == "Repeated closing remark."
    assert spans[1]["start"] == source.index("Repeated closing remark.")
    assert log[0]["status"] == RESOLUTION_UNIQUE_EXACT_MATCH
    assert log[1]["status"] == RESOLUTION_DUPLICATE_ACCEPTED_EARLIEST_OCCURRENCE
    assert log[1]["duplicate_exact_quote"] is True


# ---------------------------------------------------------------------------
# TEST 9 -- candidate_id irrelevance / absence
# ---------------------------------------------------------------------------


def test_9_resolver_signature_has_no_candidate_parameter_of_any_kind():
    params = set(inspect.signature(resolve_supporting_quote_v4_2).parameters)
    assert params == {"report", "quote"}
    for name in params:
        assert "candidate" not in name


def test_9_candidate_id_on_a_claim_is_an_unapproved_wire_field_and_rejected():
    with_candidate_id = {
        "claims": [
            {
                "claim": "x",
                "supporting_quotes": ["y"],
                "entities": [],
                "factors": [],
                "direction": "unknown",
                "confidence": 0.5,
                "candidate_id": "phase1-v4-1-fake:market_agent:market_report:0:shadow-candidate:deadbeef",
            }
        ],
        "abstentions": [],
    }
    assert provider_proposal_shape_valid_v4_2(with_candidate_id) is False
    without = {
        "claims": [
            {
                "claim": "x",
                "supporting_quotes": ["y"],
                "entities": [],
                "factors": [],
                "direction": "unknown",
                "confidence": 0.5,
            }
        ],
        "abstentions": [],
    }
    assert provider_proposal_shape_valid_v4_2(without) is True


def test_9_normalize_never_produces_a_nonempty_candidate_segment_ids():
    proposal = {
        "claims": [
            {
                "claim": "x",
                "supporting_quotes": ["abc"],
                "entities": [],
                "factors": [],
                "direction": "unknown",
                "confidence": 0.5,
            }
        ],
        "abstentions": [{"reason_code": "NO_RELIABLE_CLAIM", "notes": ""}],
    }
    bundle, _log = normalize_v4_2_proposal_to_canonical_bundle(
        proposal, source_report="abc", run_id="r", ticker="T", agent="a", agent_output_id="id"
    )
    assert bundle["claims"][0]["candidate_segment_ids"] == []
    assert bundle["abstentions"][0]["candidate_segment_ids"] == []


def test_9_active_v4_2_resolution_statuses_never_include_v4_1_candidate_only_failure_modes():
    assert RESOLUTION_STATUSES.isdisjoint(INACTIVE_V4_1_CANDIDATE_ONLY_FAILURE_MODES)


def test_9_wire_request_has_no_candidate_hints_field():
    request = build_shadow_request_v4_2(
        source_report="abc",
        run_id="r",
        ticker="T",
        agent="a",
        agent_output_id="id",
        factor_vocabulary=[],
    )
    assert "candidate_hints" not in request
    assert set(request) == {
        "input_schema_version",
        "run_id",
        "ticker",
        "agent",
        "agent_output_id",
        "factor_vocabulary",
        "agent_report_boundary",
        "agent_report",
        "agent_report_end_boundary",
    }


def test_9_prompt_text_never_mentions_candidate_id_or_hints():
    for forbidden in ("candidate_id", "CANDIDATE_HINTS", "candidate_ids", "candidate_index"):
        assert forbidden not in STRUCTURED_OUTPUT_SHADOW_PROMPT_V4_2
    # Sanity: v4's own frozen prompt DID contain these (proves this is a
    # genuine removal, not an accidental no-op edit).
    assert "candidate_id" in STRUCTURED_OUTPUT_SHADOW_PROMPT_V4
    assert "CANDIDATE_HINTS" in STRUCTURED_OUTPUT_SHADOW_PROMPT_V4
    assert CANDIDATE_BINDING_ACTIVE is False


# ---------------------------------------------------------------------------
# TEST 10 -- first occurrence used for provenance only, never for semantics
# ---------------------------------------------------------------------------


def test_10_earliest_occurrence_selection_is_identical_regardless_of_claim_semantics():
    source = (
        "## Bullish section\nShared exact phrase appears here.\n"
        "## Bearish section\nShared exact phrase appears here.\n"
    )
    bullish_proposal = {
        "claims": [
            {
                "claim": "Positive framing",
                "supporting_quotes": ["Shared exact phrase appears here."],
                "entities": [],
                "factors": [],
                "direction": "positive",
                "confidence": 0.9,
            }
        ],
        "abstentions": [],
    }
    bearish_proposal = {
        "claims": [
            {
                "claim": "Negative framing",
                "supporting_quotes": ["Shared exact phrase appears here."],
                "entities": [],
                "factors": [],
                "direction": "negative",
                "confidence": 0.9,
            }
        ],
        "abstentions": [],
    }
    bundle_a, _ = normalize_v4_2_proposal_to_canonical_bundle(
        bullish_proposal, source_report=source, run_id="r", ticker="T", agent="a", agent_output_id="id"
    )
    bundle_b, _ = normalize_v4_2_proposal_to_canonical_bundle(
        bearish_proposal, source_report=source, run_id="r", ticker="T", agent="a", agent_output_id="id"
    )
    span_a = bundle_a["claims"][0]["source_spans"][0]
    span_b = bundle_b["claims"][0]["source_spans"][0]
    # Identical selected span regardless of the claim's own direction --
    # resolution never reads claim-level semantic fields.
    assert span_a["start"] == span_b["start"] == source.index("Shared exact phrase appears here.")
    assert bundle_a["claims"][0]["direction"] == "positive"
    assert bundle_b["claims"][0]["direction"] == "negative"


# ---------------------------------------------------------------------------
# TEST 11 -- Provider source == resolver source invariant
# ---------------------------------------------------------------------------


def test_11_provider_wire_source_and_resolver_source_are_the_same_string():
    source_report = "Some exact report text used for both the wire request and resolution."
    request = build_shadow_request_v4_2(
        source_report=source_report,
        run_id="r",
        ticker="T",
        agent="a",
        agent_output_id="id",
        factor_vocabulary=[],
    )
    # This is exactly what Week2GatewaySemanticInvokerV4_2's gateway
    # validator closure does: source_report=str(request.get("agent_report")).
    resolver_source = str(request.get("agent_report") or "")
    assert resolver_source == source_report
    resolved = resolve_supporting_quote_v4_2(report=resolver_source, quote=source_report)
    assert resolved.status == RESOLUTION_UNIQUE_EXACT_MATCH


def test_11_no_provider_call_required_for_offline_parser_use():
    calls = []

    def fake_invoker(*, prompt, request):
        calls.append((prompt, request))
        return {"claims": [], "abstentions": []}

    parser = StructuredOutputShadowParserV4_2(fake_invoker)
    result = parser.parse_report_shadow_v4_2(
        source_report="abc", run_id="r", ticker="T", agent="a", agent_output_id="id"
    )
    assert len(calls) == 1
    assert "candidate_hints" not in calls[0][1]
    assert result["claims"] == []


# ---------------------------------------------------------------------------
# Constants / identity sanity
# ---------------------------------------------------------------------------


def test_prompt_version_and_hash_are_stable_and_distinct_from_v4():
    assert STRUCTURED_OUTPUT_SHADOW_PROMPT_VERSION_V4_2 == "structured_adapter.claim_extraction_shadow.v4.2"
    assert len(STRUCTURED_OUTPUT_SHADOW_PROMPT_V4_2_SHA256) == 64
    assert STRUCTURED_OUTPUT_SHADOW_PROMPT_V4_2 != STRUCTURED_OUTPUT_SHADOW_PROMPT_V4


def test_invalid_quote_status_for_non_string_or_empty_quote():
    assert resolve_supporting_quote_v4_2(report="abc", quote="").status == RESOLUTION_INVALID_QUOTE
    assert resolve_supporting_quote_v4_2(report="abc", quote=None).status == RESOLUTION_INVALID_QUOTE
    assert resolve_supporting_quote_v4_2(report="abc", quote=123).status == RESOLUTION_INVALID_QUOTE


@pytest.mark.parametrize("bad_field", ["candidate_id", "candidate_ids", "segment_id", "offset"])
def test_any_location_addressing_field_on_a_claim_is_rejected_as_unapproved(bad_field):
    proposal = {
        "claims": [
            {
                "claim": "x",
                "supporting_quotes": ["y"],
                "entities": [],
                "factors": [],
                "direction": "unknown",
                "confidence": 0.5,
                bad_field: "anything",
            }
        ],
        "abstentions": [],
    }
    assert provider_proposal_shape_valid_v4_2(proposal) is False
