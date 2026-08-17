"""Phase 1 Master evidence-alignment fix: the three named anonymized
regression fixtures (task section 12) proving the deterministic layer
distinguishes a claim's real supporting sentence from a textually similar
but wrong-section sentence, for representative fundamental/sentiment/
technical report content. No Provider calls; end-to-end through the full
v3 parser (Provider proposal -> EvidenceQuoteResolver -> normalization ->
canonical schema -> validator).
"""

from __future__ import annotations

import json

from conftest import FakeSemanticInvoker, v3_claim, v3_proposal

from comqutor_alpha.structure_engine.structured_output_shadow_v3 import parse_report_shadow_v3

RUN_ID = "run-fixtures"
TICKER = "NVDA"


def _accepted_bundle(*, report: str, agent: str, claim: str, quotes: list[str], **claim_kwargs):
    agent_output_id = f"{RUN_ID}:{agent}:fixture_report"
    proposal = v3_proposal(claims=[v3_claim(claim=claim, supporting_quotes=quotes, **claim_kwargs)])
    return parse_report_shadow_v3(
        semantic_invoker=FakeSemanticInvoker(json.dumps(proposal)),
        source_report=report,
        run_id=RUN_ID,
        ticker=TICKER,
        agent=agent,
        agent_output_id=agent_output_id,
        factor_vocabulary=[],
    )


# ---------------------------------------------------------------------------
# Fixture A: Net margin 71.5% vs. a textually similar Gross margin sentence.
# ---------------------------------------------------------------------------

FIXTURE_A_REPORT = (
    "Fundamentals summary. Gross margin for the quarter was 46.2%, roughly in "
    "line with the prior quarter. Net margin reached 71.5% for the quarter, "
    "well above the prior year period, driven by operating leverage."
)
FIXTURE_A_CLAIM = "Net margin reached 71.5% for the quarter"
FIXTURE_A_CORRECT_QUOTE = (
    "Net margin reached 71.5% for the quarter, well above the prior year "
    "period, driven by operating leverage."
)
FIXTURE_A_WRONG_SECTION_QUOTE = (
    "Gross margin for the quarter was 46.2%, roughly in line with the prior quarter."
)


def test_fixture_a_correct_quote_resolves_from_net_margin_text_not_gross_margin():
    bundle = _accepted_bundle(
        report=FIXTURE_A_REPORT,
        agent="fundamental_agent",
        claim=FIXTURE_A_CLAIM,
        quotes=[FIXTURE_A_CORRECT_QUOTE],
    )
    assert bundle["validation_summary"]["valid"] is True
    span = bundle["claims"][0]["source_spans"][0]
    assert span["exact_quote"] == FIXTURE_A_CORRECT_QUOTE
    assert "71.5%" in span["exact_quote"]
    assert "Net margin" in span["exact_quote"]
    assert "Gross margin" not in span["exact_quote"]
    assert span["start"] == FIXTURE_A_REPORT.index(FIXTURE_A_CORRECT_QUOTE)


def test_fixture_a_wrong_section_quote_is_a_real_exact_quote_but_still_only_provenance_not_semantic_truth():
    """Deliberately documents the boundary the task itself calls out
    (section 10): exact-match provenance is NOT semantic correctness. A
    real, exact quote taken from the WRONG section (gross margin, not net
    margin) still satisfies the deterministic validator -- it genuinely is
    an exact substring of the report and the evidence field is a bounded
    combination of its own spans. The system must NOT invent a keyword-
    overlap or number-matching heuristic to catch this (section 11) --
    catching a real-but-wrong-section quote is exactly, and only, what
    human review's evidence_correctness judgment is for."""

    bundle = _accepted_bundle(
        report=FIXTURE_A_REPORT,
        agent="fundamental_agent",
        claim=FIXTURE_A_CLAIM,
        quotes=[FIXTURE_A_WRONG_SECTION_QUOTE],
    )
    assert bundle["validation_summary"]["valid"] is True
    span = bundle["claims"][0]["source_spans"][0]
    assert span["exact_quote"] == FIXTURE_A_WRONG_SECTION_QUOTE
    assert "46.2%" in span["exact_quote"]
    # The deterministic layer admits it -- catching this is a human review
    # job (evidence_correctness), not something this test asserts a
    # reason_code rejects.
    assert bundle["validation_summary"]["status"] == "accepted"


# ---------------------------------------------------------------------------
# Fixture B: Nasdaq-100 rose ~3.5% (sentiment/market report).
# ---------------------------------------------------------------------------

FIXTURE_B_REPORT = (
    "Market sentiment summary. The Nasdaq-100 rose approximately 3.5% over "
    "the trading week, its strongest weekly gain since March, as risk "
    "appetite for large-cap technology names improved. The Russell 2000 was "
    "roughly flat over the same period."
)
FIXTURE_B_CLAIM = "Nasdaq-100 rose approximately 3.5% over the trading week"
FIXTURE_B_CORRECT_QUOTE = (
    "The Nasdaq-100 rose approximately 3.5% over the trading week, its "
    "strongest weekly gain since March, as risk appetite for large-cap "
    "technology names improved."
)


def test_fixture_b_correct_quote_resolves_from_the_sentence_stating_the_rise():
    bundle = _accepted_bundle(
        report=FIXTURE_B_REPORT,
        agent="sentiment_agent",
        claim=FIXTURE_B_CLAIM,
        quotes=[FIXTURE_B_CORRECT_QUOTE],
        direction="positive",
    )
    assert bundle["validation_summary"]["valid"] is True
    span = bundle["claims"][0]["source_spans"][0]
    assert "Nasdaq-100" in span["exact_quote"]
    assert "3.5%" in span["exact_quote"]
    assert span["exact_quote"] == FIXTURE_B_CORRECT_QUOTE


def test_fixture_b_fabricated_evidence_for_the_nasdaq_claim_is_rejected():
    """A quote for the SAME claim that does not actually appear in the
    report (e.g. citing the unrelated Russell 2000 sentence's numbers,
    paraphrased) must be rejected, never admitted."""

    bundle = _accepted_bundle(
        report=FIXTURE_B_REPORT,
        agent="sentiment_agent",
        claim=FIXTURE_B_CLAIM,
        quotes=["The Nasdaq-100 rose approximately 5.0% over the trading week."],
        direction="positive",
    )
    assert bundle["validation_summary"]["valid"] is False
    assert bundle["claims"] == []


# ---------------------------------------------------------------------------
# Fixture C: RSI = 74.03 (technical report).
# ---------------------------------------------------------------------------

FIXTURE_C_REPORT = (
    "Technical summary. RSI reached 74.03 on the daily chart, its highest "
    "reading in the past quarter and inside overbought territory. MACD "
    "remained positive but showed early signs of a bearish crossover."
)
FIXTURE_C_CLAIM = "RSI reached 74.03, inside overbought territory"
FIXTURE_C_CORRECT_QUOTE = (
    "RSI reached 74.03 on the daily chart, its highest reading in the past "
    "quarter and inside overbought territory."
)


def test_fixture_c_correct_quote_resolves_from_the_sentence_containing_rsi_74_03():
    bundle = _accepted_bundle(
        report=FIXTURE_C_REPORT,
        agent="market_agent",
        claim=FIXTURE_C_CLAIM,
        quotes=[FIXTURE_C_CORRECT_QUOTE],
        factors=[],
    )
    assert bundle["validation_summary"]["valid"] is True
    span = bundle["claims"][0]["source_spans"][0]
    assert "RSI" in span["exact_quote"]
    assert "74.03" in span["exact_quote"]
    assert span["exact_quote"] == FIXTURE_C_CORRECT_QUOTE


def test_fixture_c_quote_from_a_different_indicator_sentence_is_rejected_when_not_verbatim():
    """A quote mixing MACD language with the RSI number (never actually
    written that way in the report) is a fabricated quote, not a real
    exact substring -- rejected on exact-match grounds."""

    bundle = _accepted_bundle(
        report=FIXTURE_C_REPORT,
        agent="market_agent",
        claim=FIXTURE_C_CLAIM,
        quotes=["MACD reached 74.03 and showed a bearish crossover."],
    )
    assert bundle["validation_summary"]["valid"] is False
    assert bundle["claims"] == []
