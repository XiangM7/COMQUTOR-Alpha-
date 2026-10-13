"""The production sentence split must not end a claim at an abbreviation's full stop (2026-10-13).

Saved run c9abf687 cut "OpenAI's custom chip (Jalapeño, with Broadcom/Celestica) and the Roundtable 100 ranking (No. 76) introduce mild
competitive/reputational noise, though neither is framed as an imminent threat to NVDA." into two claims, the first ending at "(No."
(``re.split(r"(?<=[.!?。！？])\\s+", ...)`` treated every full stop followed by whitespace as a sentence end). These tests pin the minimal
fix: three closed abbreviation lists, everything else split exactly as before -- normal English and Chinese sentence ends, decimals,
complete headlines and structured short lines.
"""
from __future__ import annotations

import json
from pathlib import Path

import pytest

from comqutor_alpha.structure_engine.structured_output_adapter import (
    _split_sentences,
    extract_claim_segments,
)

S047_SENTENCE = (
    "OpenAI's custom chip (Jalapeño, with Broadcom/Celestica) and the Roundtable 100 ranking (No. 76) introduce mild "
    "competitive/reputational noise, though neither is framed as an imminent threat to NVDA."
)
S047_RUN = Path(__file__).resolve().parents[1] / "outputs/runs/c9abf687-1fe2-4a48-9039-c8fd7cf2e3a6/raw_agent_outputs.json"


def claims(raw_text: str) -> list[str]:
    return [segment["claim"] for segment in extract_claim_segments(raw_text)]


# ------------------------------------------------------------------------------------------------------------- the confirmed S047 cut
def test_the_s047_sentence_stays_one_claim():
    raw = f"Sentiment is mixed this week. {S047_SENTENCE} Retail chatter remains bullish into earnings."
    assert claims(raw) == ["Sentiment is mixed this week.", S047_SENTENCE, "Retail chatter remains bullish into earnings."]


@pytest.mark.skipif(not S047_RUN.is_file(), reason="needs the saved run c9abf687 (local evidence, not in a fresh clone)")
def test_the_saved_s047_report_now_gives_the_whole_sentence():
    report = json.loads(S047_RUN.read_text(encoding="utf-8"))["agent_outputs"][1]["raw_output"]
    extracted = claims(report)
    assert S047_SENTENCE in extracted
    assert not any(claim.endswith("(No.") or claim.endswith(" No.") for claim in extracted)


# ---------------------------------------------------------------------------------------------- the same kind of abbreviation, kept whole
@pytest.mark.parametrize("sentence", [
    "AMD trades at 25x forward earnings vs. 40x for NVDA, a discount the market keeps.",       # never a sentence end
    "This is a classic retail-chasing vs. institutional-caution divergence in the tape.",
    "Category: Momentum; Key Metric: Price vs. 50-day SMA; Signal: Bullish",
    "Opex grew from $3,193M to $4,213M, i.e. +32%, while revenue grew +50%.",
    "A price hike is cited as a catalyst, e.g. pricing power rather than volume.",
    'Retail traders wrote "Please don\'t ruin it tomorrow Mr. Warsh" before the meeting.',
    "Roundtable 100 ranking: NVDA placed only No. 76 in a new tech power ranking.",            # before a number
    "See Fig. 3 for the quarterly breakdown of the data-center segment revenue.",
    'Motley Fool: "TSMC Stock Will Soar After Aug. 26 Thanks to Nvidia" led the feed.',
    "Margins were approx. 75% in the quarter, the highest level on record.",
    "Samsung sank 7% in Seoul, dragging down the entire U.S. memory sector in sympathy.",     # can end a sentence; not before lowercase / "("
    "Analysts at 24/7 Wall St. published bold 2028 price predictions for MU.",
    "Advanced Micro Devices, Inc. (AMD) reported record data-center revenue this quarter.",
])
def test_an_abbreviation_full_stop_does_not_end_the_sentence(sentence):
    assert _split_sentences(sentence) == [sentence]


# ----------------------------------------------------------------------------------------------------- real sentence ends still split
@pytest.mark.parametrize(("text", "expected"), [
    ("Revenue rose 50% year over year. Margins expanded to 75% in the quarter.",
     ["Revenue rose 50% year over year.", "Margins expanded to 75% in the quarter."]),
    ("Is demand slowing? Orders fell 10% this quarter. Guidance was cut! Shares dropped.",
     ["Is demand slowing?", "Orders fell 10% this quarter.", "Guidance was cut!", "Shares dropped."]),
    ("Rebuttal: No. The bear only needs one catalyst to win this argument.",                  # "No" the word: a capital follows
     ["Rebuttal: No.", "The bear only needs one catalyst to win this argument."]),
    ("The technicals say no. Look at the moving average stack before buying.",
     ["The technicals say no.", "Look at the moving average stack before buying."]),
    ("Prices went up. 5 analysts raised their targets this week.",                            # "up." is not the abbreviation "p."
     ["Prices went up.", "5 analysts raised their targets this week."]),
    ("The model ignores interest. 5 analysts disagree with that view.",                       # "interest." is not "est."
     ["The model ignores interest.", "5 analysts disagree with that view."]),
    ("Gross margin rose 2.3pp. 2027 guidance implies further expansion.",                    # percentage points, not pages
     ["Gross margin rose 2.3pp.", "2027 guidance implies further expansion."]),
    ("Retail flows into AI names were up. 3 of 5 sentiment gauges turned bullish.",
     ["Retail flows into AI names were up.", "3 of 5 sentiment gauges turned bullish."]),
    ("Sales rose in the U.S. The company raised guidance for the year.",                       # "U.S." before a capital: as before
     ["Sales rose in the U.S.", "The company raised guidance for the year."]),
])
def test_a_real_sentence_end_still_splits(text, expected):
    assert _split_sentences(text) == expected


@pytest.mark.parametrize(("text", "expected"), [
    ("营收同比增长50%。 毛利率提升到75%！ 需求会放缓吗？ 订单下降。",                            # whitespace after 。！？: split, as before
     ["营收同比增长50%。", "毛利率提升到75%！", "需求会放缓吗？", "订单下降。"]),
    ("营收同比增长50%。毛利率提升到75%。", ["营收同比增长50%。毛利率提升到75%。"]),            # no whitespace: one piece, as before
])
def test_chinese_sentence_ends_split_as_before(text, expected):
    assert _split_sentences(text) == expected


@pytest.mark.parametrize(("text", "expected"), [
    ("Gross margin was 75.5% and EPS was $1.05 in the quarter.", ["Gross margin was 75.5% and EPS was $1.05 in the quarter."]),
    ("EPS rose to $1.05. Revenue reached $4.2B. Guidance implies 3.5% growth.",
     ["EPS rose to $1.05.", "Revenue reached $4.2B.", "Guidance implies 3.5% growth."]),
])
def test_decimals_are_never_a_sentence_end(text, expected):
    assert _split_sentences(text) == expected


@pytest.mark.parametrize("line", [
    "Q2 FY2027 Earnings Review: Revenue Up 50% YoY",
    "Factor: Valuation; Signal: Bearish; Direction: Down; Source: Market",
    "Direction: Bearish; Source: News; Supporting Evidence: OpenAI custom chip (Jalapeño); Roundtable 100 ranking No. 76",
])
def test_complete_headlines_and_structured_lines_stay_whole(line):
    assert _split_sentences(line) == [line]
    assert claims(f"- {line}") == [line]
