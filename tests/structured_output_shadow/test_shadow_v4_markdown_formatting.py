"""Phase 1 Master evidence-alignment fix, round 2: tests for the actual
new behavior v4 adds over v3 -- the FORMATTING RULES prompt instruction and
the fact that a Markdown-formatting-preserving quote resolves while the
old v3-observed failure mode (silently dropping/repositioning **bold**
markers) is still correctly rejected, unrepaired. The resolver algorithm
itself is unchanged from v3 (see test_shadow_v3_evidence_resolver.py for
its exhaustive coverage, which applies identically here); these tests
target only what v4 actually changes. No Provider calls.
"""

from __future__ import annotations

import json

from conftest import FakeSemanticInvoker, v4_claim, v4_proposal

from comqutor_alpha.structure_engine.structured_output_shadow_prompt_v3 import (
    STRUCTURED_OUTPUT_SHADOW_PROMPT_V3,
)
from comqutor_alpha.structure_engine.structured_output_shadow_prompt_v4 import (
    STRUCTURED_OUTPUT_SHADOW_PROMPT_V4,
    STRUCTURED_OUTPUT_SHADOW_PROMPT_V4_SHA256,
    STRUCTURED_OUTPUT_SHADOW_PROMPT_VERSION_V4,
)
from comqutor_alpha.structure_engine.structured_output_shadow_v4 import (
    RESOLUTION_NO_EXACT_MATCH,
    RESOLUTION_UNIQUE_EXACT_MATCH,
    parse_report_shadow_v4,
    resolve_supporting_quote,
)


def test_v4_prompt_adds_formatting_rules_section_v3_never_had():
    assert "FORMATTING RULES" in STRUCTURED_OUTPUT_SHADOW_PROMPT_V4
    assert "FORMATTING RULES" not in STRUCTURED_OUTPUT_SHADOW_PROMPT_V3
    assert "Markdown formatting characters" in STRUCTURED_OUTPUT_SHADOW_PROMPT_V4
    assert "**bold**" in STRUCTURED_OUTPUT_SHADOW_PROMPT_V4


def test_v4_prompt_identity_is_distinct_from_v3():
    assert STRUCTURED_OUTPUT_SHADOW_PROMPT_VERSION_V4 == "structured_adapter.claim_extraction_shadow.v4"
    assert STRUCTURED_OUTPUT_SHADOW_PROMPT_V4 != STRUCTURED_OUTPUT_SHADOW_PROMPT_V3
    assert len(STRUCTURED_OUTPUT_SHADOW_PROMPT_V4_SHA256) == 64


def test_markdown_preserving_quote_resolves_exactly():
    """The real failure mode v3's evaluation measured: the report bolds a
    number, and the correctly-formatted quote must resolve."""

    report = "Backlog reached **$4.2 billion**, a record high for the company."
    quote = "Backlog reached **$4.2 billion**, a record high for the company."
    resolved = resolve_supporting_quote(report=report, quote=quote)
    assert resolved.status == RESOLUTION_UNIQUE_EXACT_MATCH
    assert report[resolved.start : resolved.end] == quote


def test_markdown_stripped_quote_still_correctly_rejected_not_repaired():
    """The exact v3 failure mode: the model drops the ** when quoting.
    v4's resolver must still reject this -- v4 fixes the PROMPT (getting
    better input from the model), never adds leniency to the resolver
    itself. Repairing this quote by re-inserting the missing ** would be
    exactly the fuzzy/approximate repair this whole design forbids."""

    report = "Backlog reached **$4.2 billion**, a record high for the company."
    stripped_quote = "Backlog reached $4.2 billion, a record high for the company."
    resolved = resolve_supporting_quote(report=report, quote=stripped_quote)
    assert resolved.status == RESOLUTION_NO_EXACT_MATCH


def test_markdown_repositioned_quote_still_correctly_rejected():
    """A quote that re-bolds a DIFFERENT substring than the source (wrong
    marker placement) is also not a byte-exact match and must be rejected."""

    report = "Revenue grew **14%** year over year, beating estimates."
    wrong_marker_quote = "Revenue grew *14%* year over year, beating estimates."
    resolved = resolve_supporting_quote(report=report, quote=wrong_marker_quote)
    assert resolved.status == RESOLUTION_NO_EXACT_MATCH


def test_table_pipe_and_heading_formatting_preserved_end_to_end():
    report = "## Technicals\n| RSI | 74.03 |\n| MACD | 1.2 |\n"
    quote = "| RSI | 74.03 |"
    invoker = FakeSemanticInvoker(
        json.dumps(v4_proposal(claims=[v4_claim(claim="RSI reached 74.03", supporting_quotes=[quote])]))
    )
    bundle = parse_report_shadow_v4(
        semantic_invoker=invoker,
        source_report=report,
        run_id="run-1",
        ticker="NVDA",
        agent="market_agent",
        agent_output_id="run-1:market_agent:market_report",
        factor_vocabulary=[],
    )
    assert bundle["validation_summary"]["valid"] is True
    assert bundle["claims"][0]["source_spans"][0]["exact_quote"] == quote


def test_end_to_end_markdown_bold_claim_accepted(report):
    formatted_report = "**GPU demand increased in June.** Revenue growth remained strong."
    quote = "**GPU demand increased in June.**"
    invoker = FakeSemanticInvoker(
        json.dumps(v4_proposal(claims=[v4_claim(claim="GPU demand increased in June.", supporting_quotes=[quote])]))
    )
    bundle = parse_report_shadow_v4(
        semantic_invoker=invoker,
        source_report=formatted_report,
        run_id="run-1",
        ticker="NVDA",
        agent="news_agent",
        agent_output_id="run-1:news_agent:news_report",
        factor_vocabulary=[],
    )
    assert bundle["validation_summary"]["status"] == "accepted"
    assert bundle["claims"][0]["evidence"] == quote


def test_end_to_end_markdown_stripped_claim_rejected(report):
    """Proves v4's resolver is not more lenient than v3's -- only the
    PROMPT changed. A model that still strips ** (as v3's real model
    sometimes did) is still correctly rejected under v4.

    The real v3 failures (docs/audit_artifacts/phase1_master/prompt_audit/
    root-cause analysis) had the ** wrap only PART of the sentence the
    model wanted as its full quote, with plain text continuing afterward
    (e.g. "**SNDK plunged approximately 11-12%**, making it the worst
    performer..."). That is the case that actually breaks contiguity when
    stripped -- unlike a quote where ** happens to wrap its entire span
    (whose stripped inner text remains trivially a substring regardless)."""

    formatted_report = (
        "**GPU demand increased in June**, marking the third straight month of growth. "
        "Revenue growth remained strong."
    )
    stripped_quote = (
        "GPU demand increased in June, marking the third straight month of growth."
    )
    assert stripped_quote not in formatted_report  # sanity: genuinely not a substring
    invoker = FakeSemanticInvoker(
        json.dumps(v4_proposal(claims=[v4_claim(claim="GPU demand increased in June.", supporting_quotes=[stripped_quote])]))
    )
    bundle = parse_report_shadow_v4(
        semantic_invoker=invoker,
        source_report=formatted_report,
        run_id="run-1",
        ticker="NVDA",
        agent="news_agent",
        agent_output_id="run-1:news_agent:news_report",
        factor_vocabulary=[],
    )
    assert bundle["validation_summary"]["valid"] is False
    assert bundle["claims"] == []
