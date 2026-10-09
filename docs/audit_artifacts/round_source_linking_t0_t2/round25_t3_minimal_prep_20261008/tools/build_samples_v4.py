#!/usr/bin/env python3
"""Round 25 part B, item 1: complete the material conditions of the frozen 40-item joint sample (v3 -> v4) without fetching anything.

For every sample the claim's factual elements are listed by hand (SPEC below) and each element is tied to material the SAME run saved at run time
-- registered data rows / fields (source_registry.json), saved news titles (source_registry.json) or the run's saved daily market rows
(market_data_snapshot.json). Agent text never counts as material. This script RESOLVES every reference against the saved files (it fails if a
field, period or title does not exist) and writes the values it found; the element analysis itself is engineering judgment and is labelled so.

Element status:  LOCATED  the figure / fact is stated in the material
                 DERIVED  computable from located rows (the derivation is written down)
                 RELATED  material bears on the element but does not state or reproduce it (the reviewer judges how far it supports it)
                 NOT_SAVED  no material for it was saved by the run (prediction-market odds, article bodies, social posts, ...)
Sample material status:  COMPLETE (no NOT_SAVED element) / PARTIAL / NO_MATERIAL (every element NOT_SAVED) / NO_FACTUAL_ELEMENT

The 15 v3 samples without saved source content were handled in the user's order: (1) complete from saved material; (2) otherwise replace by the
first candidate of the same cell, in the frozen hash order (salt "t3v3|"), whose material is COMPLETE and which is not a duplicate; (3) otherwise
list it for collection (or as an exact gap when the claim states no checkable fact). No prediction exists yet; nothing was chosen by looking at
a model answer.

    python build_samples_v4.py --out-dir <new dir>
"""
from __future__ import annotations

import argparse
import csv
import json
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
REPO = next(p for p in HERE.parents if (p / "comqutor_alpha").is_dir())
sys.path.insert(0, str(REPO))
sys.path.insert(0, str(HERE))

import select_joint_sample as sel  # noqa: E402

PACKAGE = HERE.parent
V3_MANIFEST = PACKAGE / "04_joint_sample" / "joint_sample_v3_manifest.json"

R1 = "1bad76a7-72ac-4c8b-8189-2e5c0f1a6105"
RC = "c904d4cc-dc09-495c-aec5-b056979948e1"
RN = "034a0a60-430e-41f8-8321-03a11389707a"
F1, FC = "src_5bd8a947130d1949", "src_7e133fa786f7aaa0"  # fundamentals snapshots (AMD 10-05 / 10-06)
IS, BS, CF = "src_582ac24bf4319648", "src_d889dd1e36a5d55a", "src_4045667791b919f9"  # income statement / balance sheet / cash flow
MK = "src_388228ad9e12e09d"  # AMD verified market snapshot 2026-10-06
Q2, Q1, Y1 = "2026-06-30", "2026-03-31", "2025-06-30"
TITLE_10Y_2002 = ("title", RC, "src_a213d06f42bbdca9")


def fund(run, sid, key):
    return ("fund", run, sid, key)


def stmt(run, field, periods, sid=None):
    return ("stmt", run, sid or {"Free Cash Flow": CF, "Capital Expenditure": CF}.get(field) or (BS if field in BS_FIELDS else IS), field, list(periods))


def mkt(key):
    return ("mkt", RC, MK, key)


def title(run, sid):
    return ("title", run, sid)


BS_FIELDS = {"Receivables", "Work In Process", "Cash Cash Equivalents And Short Term Investments", "Total Debt", "Working Capital", "Net PPE", "Construction In Progress"}
L, D, REL, NS = "LOCATED", "DERIVED", "RELATED", "NOT_SAVED"
VOLUME_ROWS = ("mrows", RC, ["2026-09-21", "2026-09-22", "2026-10-01", "2026-10-02", "2026-10-05", "2026-10-06"], ["close", "volume"])
FED_TITLES_1BAD = [title(R1, "src_a36554814b0dc85c"), title(R1, "src_0d3e38ccb1b90ff9")]

# sample -> (action, elements); element = (text, status, refs, note)
SPEC: dict[str, tuple[str, list]] = {
    "t3v3-001": ("keep", [("52-week low of $188.22", L, [fund(R1, F1, "fifty_two_week_low")], "")]),
    "t3v3-002": ("keep", [
        ("reported $1.38", L, [stmt(R1, "Diluted EPS", [Q2])], "quarterly diluted EPS"),
        ("clean EPS is $1.12", REL, [stmt(R1, "Net Income", [Q2]), stmt(R1, "Other Non Operating Income Expenses", [Q2]), stmt(R1, "Diluted Average Shares", [Q2])],
         "1.12 is not stated; it depends on which items are treated as non-operating"),
        ("161x trailing earnings", L, [fund(R1, F1, "trailing_pe")], "a different saved source than the claim's link"),
        ("the headline was partly non-operating", L, [stmt(R1, "Other Non Operating Income Expenses", [Q2])], "")]),
    "t3v3-003": ("keep", [
        ("FCF collapsed 39% sequentially to $1,558,000,000 from $2,566,000,000", D, [stmt(R1, "Free Cash Flow", [Q2, Q1])], "1558/2566-1 = -39.3%"),
        ("receivables grew +20.6% QoQ", D, [stmt(R1, "Receivables", [Q2, Q1])], "7281/6035-1 = +20.6%"),
        ("+12.5% revenue growth", D, [stmt(R1, "Total Revenue", [Q2, Q1])], "11536/10253-1 = +12.5%"),
        ("the macro setup offers no scenario with both strong demand and falling rates", REL, FED_TITLES_1BAD, "only headlines on Fed rate-hike expectations were saved"),
        ("a 2.45-beta asset", L, [fund(R1, F1, "beta")], ""),
        ("the bull's PEG of 0.64 ... built on the forward EPS estimate", L, [fund(R1, F1, "peg_ratio"), fund(R1, F1, "forward_eps")], "")]),
    "t3v3-004": ("keep", [
        ("a 2.45-beta long-duration multiple", L, [fund(R1, F1, "beta")], ""),
        ("a $483M non-operating investment gain", REL, [stmt(R1, "Other Non Operating Income Expenses", [Q2])], "the saved row shows 598M; no 483M item was saved"),
        ("a hawkish rate path", REL, FED_TITLES_1BAD, "")]),
    "t3v3-005": ("keep", [
        ("forward P/E of 41.67x", L, [fund(RC, FC, "forward_pe")], ""),
        ("an EPS estimate of $15.72", L, [fund(RC, FC, "forward_eps")], ""),
        ("the current $1.38 quarterly / $5.52 annualized run-rate", D, [stmt(RC, "Diluted EPS", [Q2])], "1.38 x 4 = 5.52"),
        ("a 167x trailing multiple", L, [fund(RC, FC, "trailing_pe")], ""),
        ("net cash", D, [stmt(RC, "Cash Cash Equivalents And Short Term Investments", [Q2]), stmt(RC, "Total Debt", [Q2])], "13111 - 4276 = 8835 (M)"),
        ("the 10-year at a 24-year high", L, [TITLE_10Y_2002], "2002 -> 2026")]),
    "t3v3-006": ("keep", [
        ("PEG 0.64", L, [fund(RC, FC, "peg_ratio")], ""),
        ("a forward EPS of $15.72", L, [fund(RC, FC, "forward_eps")], ""),
        ("a current quarterly run-rate of $1.38", L, [stmt(RC, "Diluted EPS", [Q2])], ""),
        ("the last four quarters support a trailing inflection", REL, [stmt(RC, "Total Revenue", [Q2, Q1, "2025-12-31", "2025-09-30"]), stmt(RC, "Diluted EPS", [Q2, Q1, "2025-12-31", "2025-09-30"])], "")]),
    "t3v3-007": ("keep", [("52-week low of $188.22", L, [fund(R1, F1, "fifty_two_week_low")], ""), ("the 50-day average", L, [fund(R1, F1, "fifty_day_average")], "")]),
    "t3v3-008": ("keep", [
        ("PEG of 0.64", L, [fund(R1, F1, "peg_ratio")], ""),
        ("the 4x ramp from TTM $3.92 to $15.63", D, [fund(R1, F1, "trailing_eps"), fund(R1, F1, "forward_eps")], "15.63/3.92 = 3.99")]),
    "t3v3-009": ("keep", [
        ("96% odds of no Fed rate cuts in 2026", NS, [], "prediction-market data not saved"),
        ("76% odds of another hike", NS, [], "prediction-market data not saved"),
        ("the 10-year is at a 24-year high", L, [TITLE_10Y_2002], ""),
        ("AMD's beta is 2.454", L, [fund(RC, FC, "beta")], "")]),
    "t3v3-010": ("keep", [("Forward P/E 40.40", L, [fund(R1, F1, "forward_pe")], "")]),
    "t3v3-011": ("keep", [("PEG of 0.64 ... computed off the forward estimate", L, [fund(R1, F1, "peg_ratio"), fund(R1, F1, "forward_eps")], "")]),
    "t3v3-012": ("keep", [
        ("forward P/E of 41.67 with a PEG of 0.64", L, [fund(RC, FC, "forward_pe"), fund(RC, FC, "peg_ratio")], ""),
        ("the last four quarters of data", REL, [stmt(RC, "Total Revenue", [Q2, Q1, "2025-12-31", "2025-09-30"])], "")]),
    "t3v3-013": ("keep", [
        ("At $654.91", L, [mkt("Close")], ""),
        ("a 24-year-high yield backdrop", L, [TITLE_10Y_2002], ""),
        ("a forward estimate requiring a 3x acceleration from the current run-rate", D, [fund(RC, FC, "forward_eps"), stmt(RC, "Diluted EPS", [Q2])], "15.72 / (1.38 x 4) = 2.85"),
        ("stretched technicals on fading volume", REL, [mkt("rsi"), mkt("close_200_sma"), mkt("Volume"), VOLUME_ROWS], ""),
        ("a live policy tail risk", NS, [], "AI-chip export licensing odds (prediction market) not saved")]),
    "t3v3-014": ("keep", [
        ("the forward EPS of $15.72", L, [fund(RC, FC, "forward_eps")], ""),
        ("gross-margin defense above 53%", D, [stmt(RC, "Gross Profit", [Q2]), stmt(RC, "Total Revenue", [Q2])], "6203/11536 = 53.8%"),
        ("continued sequential revenue growth", D, [stmt(RC, "Total Revenue", [Q2, Q1])], "")]),
    "t3v3-015": ("keep", [("a PEG of 0.64", L, [fund(RC, FC, "peg_ratio")], "")]),
    "t3v3-016": ("keep", [
        ("AMD can rally to $654.91", L, [mkt("Close")], ""),
        ("96% odds of no cuts priced in", NS, [], "prediction-market data not saved"),
        ("the October 15 CPI", NS, [], "release date not in any saved source"),
        ("the cooler 3.4% bucket sits at just 4%", NS, [], "prediction-market data not saved")]),
    "t3v3-017": ("keep", [
        ("At $654.91", L, [mkt("Close")], ""),
        ("the 691.33 upper band / the 10 EMA at 618.52 / the 50 SMA at 518.93", L, [mkt("boll_ub"), mkt("close_10_ema"), mkt("close_50_sma")], ""),
        ("5.5% upside ... 5.5% downside ... 21%", D, [mkt("Close"), mkt("boll_ub"), mkt("close_10_ema"), mkt("close_50_sma")], "691.33/654.91-1 = 5.6%; 618.52/654.91-1 = -5.6%; 518.93/654.91-1 = -20.8%"),
        ("a hot-skewed October 15 CPI", NS, [], "not in any saved source"),
        ("45% implied odds of AI-chip export licensing legislation", NS, [], "prediction-market data not saved")]),
    "t3v3-018": ("keep", [("Work-in-process rose to $5,265M from $4,167M", L, [stmt(R1, "Work In Process", [Q2, Y1])], "year-ago comparison")]),
    "t3v3-019": ("keep", [
        ("24-year-high yields", L, [TITLE_10Y_2002], ""),
        ("96% odds of no cuts, 76% odds of a hike", NS, [], "prediction-market data not saved"),
        ("hot inflation leaning", REL, [title(RC, "src_c34c040e23bfdc61"), title(RC, "src_8b53d16c45771ed9"), title(RC, "src_d21e4147133b09d8")], "one saved headline reports a cooler-than-expected read"),
        ("73% above the 200 SMA, RSI 72.95", D, [mkt("Close"), mkt("close_200_sma"), mkt("rsi")], "654.91/379.12-1 = 72.7%"),
        ("contracting MACD histogram, fading volume", REL, [mkt("macdh"), VOLUME_ROWS], "the snapshot holds one MACD-histogram value; a trend needs recomputation from the daily rows"),
        ("the working-capital build", REL, [stmt(RC, "Working Capital", [Q2, Q1]), stmt(RC, "Receivables", [Q2, Q1])], ""),
        ("a live 45% policy tail risk on AI-chip export licensing", NS, [], "prediction-market data not saved")]),
    "t3v3-020": ("keep", [
        ("R&D $2,528M in Q2'26", L, [stmt(RC, "Research And Development", [Q2])], ""),
        ("up 33.5% YoY", D, [stmt(RC, "Research And Development", [Q2, Y1])], "2528/1894-1 = +33.5%")]),
    "t3v3-021": ("keep", [("Beta of 2.45", L, [fund(R1, F1, "beta")], "")]),
    "t3v3-025": ("keep", [
        ("the October FOMC vol spike", NS, [], "no options / event data saved"),
        ("the 50-day average of $513.53", L, [fund(R1, F1, "fifty_day_average")], "")]),
    "t3v3-029": ("keep", [
        ("$13.1B cash + short-term investments", L, [stmt(R1, "Cash Cash Equivalents And Short Term Investments", [Q2])], ""),
        ("$4.28B total debt", L, [stmt(R1, "Total Debt", [Q2])], ""),
        ("net cash position of $8.8B", D, [stmt(R1, "Cash Cash Equivalents And Short Term Investments", [Q2]), stmt(R1, "Total Debt", [Q2])], "13111 - 4276 = 8835 (M)")]),
    "t3v3-030": ("keep", [("Current ratio 2.609", L, [fund(RC, FC, "current_ratio")], "")]),
    "t3v3-031": ("keep", [("Working capital expanded to $19,441M from $14,676M a year ago", L, [stmt(R1, "Working Capital", [Q2, Y1])], "")]),
    # ---- the 15 v3 samples without saved source content ----
    "t3v3-022": ("replace", ("A101_A103", 21)),
    "t3v3-023": ("complete", [
        ("Gross margin ... 53.8%", D, [stmt(R1, "Gross Profit", [Q2]), stmt(R1, "Total Revenue", [Q2])], "6203/11536 = 53.8%"),
        ("from 39.8% a year ago", D, [stmt(R1, "Gross Profit", [Y1]), stmt(R1, "Total Revenue", [Y1])], "3059/7685 = 39.8%")]),
    "t3v3-024": ("replace", ("A101_A103", 29)),
    "t3v3-026": ("complete", [
        ("At 161x trailing earnings", L, [fund(R1, F1, "trailing_pe")], ""),
        ("37% above the 200-day", REL, [fund(R1, F1, "fifty_day_average"), fund(R1, F1, "two_hundred_day_average"),
                                         ("mrows", R1, ["2026-10-02", "2026-10-05"], ["close"])],
         "the 50-day average is 37.0% above the 200-day; the latest close is about 69% above it"),
        ("receivables outrunning revenue", D, [stmt(R1, "Receivables", [Q2, Q1]), stmt(R1, "Total Revenue", [Q2, Q1])], "+20.6% vs +12.5% QoQ"),
        ("a hawkish Fed", REL, FED_TITLES_1BAD, "the saved headlines report rate-hike expectations being reduced")]),
    "t3v3-027": ("replace", ("A001", 16)),
    "t3v3-028": ("complete", [
        ("Global market news (Yahoo Finance, 2026-09-22 -> 2026-10-06)", REL, [title(RC, "src_86b41d2459c3f6ca")], "the saved Yahoo Finance headlines are dated 2026-09-28 .. 2026-10-06"),
        ("rates rising sharply", L, [title(RC, "src_86b41d2459c3f6ca"), title(RC, "src_2b9c6f4f9e87b926"), title(RC, "src_c6c89691a2e8dd18"), TITLE_10Y_2002], ""),
        ("inflation sticky-to-hot", REL, [title(RC, "src_c34c040e23bfdc61"), title(RC, "src_d21e4147133b09d8")], "one saved headline reports a cooler-than-expected read"),
        ("Fed officials hawkish", L, [title(RC, "src_8b53d16c45771ed9")], ""),
        ("equities at all-time highs led by tech/chips", L, [title(RC, "src_2f806ac2cc4fb09b"), title(RC, "src_344d88acaf74bc29"), title(RC, "src_2938152ab26ed51a")], "")]),
    "t3v3-032": ("gap", [("(rhetorical: 'you take liquidity when it's offered')", None, [], "no checkable factual element; the only other A003 text-only candidate rests on prediction-market data")]),
    "t3v3-033": ("partial", [
        ("Multiply that (Anthropic compute and infrastructure expense +190% Y/Y to $7.33B, from the context)", NS, [], "cited from the sentiment report; the original source was not saved"),
        ("add sovereign deployments", REL, [title(RN, "src_e055413056226d0c")], ""),
        ("add enterprise inference", REL, [title(RN, "src_b06e70e9b96f69dc")], "")]),
    "t3v3-034": ("complete", [("Its (Accenture's) bookings", L, [title(RN, "src_e9c1b0802ec94021"), title(RN, "src_a2678074875af649")], "the claim's relation to NVDA demand is its own inference")]),
    "t3v3-035": ("complete", [
        ("Accenture's record bookings", L, [title(RN, "src_e9c1b0802ec94021")], ""),
        ("IBM's sovereign AI agents", L, [title(RN, "src_e055413056226d0c")], ""),
        ("self-hosted enterprise deployment scaling", REL, [title(RN, "src_b06e70e9b96f69dc"), title(RN, "src_299527b4eccbd2fd")], "the headlines announce the deployment option; 'scaling' is not stated")]),
    "t3v3-036": ("gap", [("(evaluative: 'the most underappreciated positive')", None, [], "no checkable factual element; same-cell candidates are duplicates of t3v3-034/035 or rest on unsaved social posts")]),
    "t3v3-037": ("collect", [("Recession risk: US 8% (-1.0pp); UK 7%; Japan 4%", NS, [], "prediction-market data not saved")]),
    "t3v3-038": ("collect", [("Japan recession in 2026: 4% Yes; Volume $4K", NS, [], "prediction-market data not saved")]),
    "t3v3-039": ("collect", [("At 8% and falling 2pp on the week", NS, [], "prediction-market data not saved")]),
    "t3v3-040": ("collect", [("recession odds are 8% and falling", NS, [], "prediction-market data not saved")]),
}
SPEC.update({
    "t3v3-022R": ("replacement", [
        ("Records are being set by a handful of AI/chip leaders", L, [title(RC, "src_344d88acaf74bc29"), title(RC, "src_2f806ac2cc4fb09b")], "'a handful' is the claim's own characterisation"),
        ("consumer discretionary is being 'pummeled' by rates", L, [title(RC, "src_921d7c6267af1cdc")], "")]),
    "t3v3-024R": ("replacement", [
        ("AMD is building out capacity/labs", D, [stmt(R1, "Capital Expenditure", [Q2, Q1]), stmt(R1, "Net PPE", [Q2, Q1]), stmt(R1, "Construction In Progress", [Q2, Q1])],
         "capex -808 vs -389; net PPE 3439 vs 2723; construction in progress 1148 vs 646 (M)")]),
    "t3v3-027R": ("replacement", [("'Gold Edges Higher as Weak US Jobs Data Reduces Fed Rate-Hike Expectations' (InvestorsHub)", L, [title(R1, "src_a36554814b0dc85c")], "")]),
})

# why each same-cell candidate before the accepted one (hash order, text-only pool) was not taken -- engineering reading, recorded per the
# instruction to give the reason of every replacement
REASON = {
    "PM": "rests on prediction-market odds that the run did not save",
    "NEWS_BODY": "rests on an article fact or date that is in no saved headline",
    "SOCIAL": "rests on a social-media post that the run did not save",
    "DATA_NOT_SAVED": "rests on company data the run did not save",
    "AGENT_INTERNAL": "rests on agent-internal records (tool failures, prior-decision returns), not on a source",
    "NO_FACT": "states no checkable fact (opinion, conditional, rhetoric or meta-statement)",
    "PARTIAL": "some elements are in saved material, others are not",
    "DUP": "restates a fact or event already in a selected sample",
    "SELECTED": "already in the sample",
    "ACCEPT": "every element located in material the run saved; accepted",
}
EXAMINED = {
    "A101_A103": {3: "AGENT_INTERNAL", 4: "NEWS_BODY", 5: "NO_FACT", 6: "SOCIAL", 8: "NO_FACT", 9: "PM", 10: "NO_FACT", 11: "NO_FACT", 12: "NO_FACT",
                  13: "PM", 14: "PM", 15: "SOCIAL", 16: "DUP", 18: "DATA_NOT_SAVED", 19: "NO_FACT", 20: "NEWS_BODY", 21: "ACCEPT", 22: "SOCIAL",
                  23: "DATA_NOT_SAVED", 24: "NO_FACT", 25: "PM", 26: "PM", 27: "SOCIAL", 28: "NO_FACT", 29: "ACCEPT"},
    "A001": {3: "PM", 4: "PM", 5: "PM", 6: "AGENT_INTERNAL", 7: "PM", 8: "PM", 9: "AGENT_INTERNAL", 10: "PM", 11: "PM", 12: "PM", 13: "PM", 14: "PM",
             15: "PM", 16: "ACCEPT"},
    "A003": {1: "PM"},
    "A102": {3: "DUP", 4: "DUP", 6: "NO_FACT", 7: "DUP", 8: "DUP", 9: "DUP", 10: "SOCIAL", 11: "DUP"},
    "A501": {**dict.fromkeys((3, 7, 8, 11, 12, 13, 14, 15, 17, 18, 19, 22, 23, 24, 25, 26, 27, 28, 29, 30, 31, 34, 36, 37, 38, 42, 43, 44, 46, 47, 48, 49, 50, 53, 54, 57, 58, 59, 60), "PM"),
             **dict.fromkeys((5, 6, 10, 21, 33), "PARTIAL"),
             **dict.fromkeys((9, 16, 20, 32, 39, 45, 51, 52, 55, 56), "NO_FACT"),
             **dict.fromkeys((35, 40, 41), "AGENT_INTERNAL")},
}
COLLECTION = [
    {"id": "C0", "object": "Polymarket Gamma public-search, query 'recession 2026' -- the endpoint the run's news agent itself used "
                           "(tradingagents/dataflows/polymarket.py)", "samples": ["t3v3-037", "t3v3-038", "t3v3-039", "t3v3-040"],
     "source": "GET https://gamma-api.polymarket.com/public-search?q=recession 2026&limit_per_type=20",
     "purpose": "find the three markets by their exact question and read each market's Yes token id", "request_cap": 1,
     "limits": "returns today's prices only; used solely to identify the markets"},
    {"id": "C1", "object": "daily Yes-price history of 'US recession by end of 2026?', 2026-09-24 .. 2026-10-06", "samples": ["t3v3-037", "t3v3-039", "t3v3-040"],
     "source": "GET https://clob.polymarket.com/prices-history?market=<Yes token>&startTs=..&endTs=..&fidelity=1440",
     "purpose": "the 8% level and its weekly change as of 2026-10-01/02 (034a0a60) and 2026-10-05 (1bad76a7)", "request_cap": 1,
     "limits": "the traded volume quoted in the claims is cumulative and cannot be recovered as of those dates"},
    {"id": "C2", "object": "daily Yes-price history of 'UK recession in 2026?', same window", "samples": ["t3v3-037"], "source": "as C1",
     "purpose": "the 7% level as of 2026-10-05", "request_cap": 1, "limits": "as C1"},
    {"id": "C3", "object": "daily Yes-price history of 'Japan recession in 2026?', same window", "samples": ["t3v3-037", "t3v3-038"], "source": "as C1",
     "purpose": "the 4% level as of 2026-10-01 and 2026-10-05", "request_cap": 1, "limits": "the $4K volume cannot be recovered as of those dates"},
]
NOT_PROPOSED = {"t3v3-033": ("the Anthropic compute-expense figure (+190% Y/Y to $7.33B) the claim multiplies: the run saved no pointer to its "
                             "original source, so finding it would be an open-ended web search; the sample stays PARTIAL (its other elements "
                             "have saved headlines)")}


def _units(snapshot: dict, field: str):
    return (snapshot.get("line_item_units") or {}).get(field) or (snapshot.get("field_units") or {}).get(field)


def resolve(ref, runs: dict) -> dict:
    kind, run = ref[0], ref[1]
    reg = runs[run]["registry"]
    if kind == "title":
        s = reg[ref[2]]
        assert s["source_type"] == "news", ref
        return {"type": "news_title", "source_id": s["source_id"], "source_name": s.get("name"), "title": s["title"], "url": s.get("url"),
                "published_at": s.get("published_at"), "retrieved_at": s.get("retrieved_at"), "provider": s.get("provider")}
    if kind == "mrows":
        snap = runs[run]["market_rows"]
        rows = {r["date"]: r for r in snap["rows"]}
        missing = [d for d in ref[2] if d not in rows]
        assert not missing, (ref, missing)
        return {"type": "market_rows", "artifact": "market_data_snapshot.json", "provider": snap.get("provider"), "retrieved_at": snap.get("retrieved_at"),
                "rows": [{"date": d, **{f: rows[d][f] for f in ref[3]}} for d in ref[2]]}
    s = reg[ref[2]]
    ds = s.get("data_snapshot") or {}
    base = {"source_id": s["source_id"], "source_title": s["title"], "provider": s.get("provider"), "published_at": s.get("published_at"),
            "observation_date": s.get("observation_date"), "retrieved_at": s.get("retrieved_at"), "content_hash": s.get("content_hash")}
    if kind == "fund":
        assert ref[3] in ds, ref
        return {"type": "data_field", **base, "field": ref[3], "value": ds[ref[3]], "unit": _units(ds, ref[3])}
    if kind == "mkt":
        holder = ds.get("indicators") if ref[3] in (ds.get("indicators") or {}) else ds.get("ohlcv")
        assert holder is not None and ref[3] in holder, ref
        return {"type": "data_field", **base, "field": ref[3], "value": holder[ref[3]], "unit": None}
    if kind == "stmt":
        series = (ds.get("all_line_items") or {}).get(ref[3])
        assert series is not None, ref
        missing = [p for p in ref[4] if series.get(p) is None]
        assert not missing, (ref, missing)
        return {"type": "data_rows", **base, "statement": ds.get("statement_type"), "field": ref[3], "values": {p: series[p] for p in ref[4]},
                "unit": _units(ds, ref[3]), "freq": ds.get("freq")}
    raise ValueError(ref)


def material_status(elements: list) -> str:
    statuses = [e["status"] for e in elements if e["status"] is not None]
    if not statuses:
        return "NO_FACTUAL_ELEMENT"
    if all(s == NS for s in statuses):
        return "NO_MATERIAL"
    return "PARTIAL" if NS in statuses else "COMPLETE"


def main(argv=None) -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--out-dir", required=True)
    args = ap.parse_args(argv)
    out_dir = Path(args.out_dir)
    if out_dir.exists() and any(out_dir.iterdir()):
        print("refusing: output directory not empty", out_dir, file=sys.stderr)
        return 2
    out_dir.mkdir(parents=True, exist_ok=True)
    v3 = json.loads(V3_MANIFEST.read_text(encoding="utf-8"))
    runs = {}
    for run in (R1, RC, RN):
        run_dir = REPO / "outputs" / "runs" / run
        runs[run] = {"registry": {s["source_id"]: s for s in json.loads((run_dir / "source_registry.json").read_text(encoding="utf-8"))["sources"]},
                     "market_rows": json.loads((run_dir / "market_data_snapshot.json").read_text(encoding="utf-8")),
                     "metadata": json.loads((run_dir / "metadata.json").read_text(encoding="utf-8"))}
    cands = sel.candidates()
    pools = {}
    for cell in ("A101_A103", "A001", "A003", "A102", "A501"):
        pool = [c for c in cands if cell in c["cells"] and not c["content_kind"]]
        pool.sort(key=lambda c: sel.order_key(c["record"]["claim_id"]))
        pools[cell] = pool

    manifest, form_items, csv_rows, coverage, replacement_log = [], [], [], [], []
    for item in v3["samples"]:
        sid = item["sample_id"]
        action, payload = SPEC[sid]
        if action == "replace":
            cell, pos = payload
            cand = pools[cell][pos]
            r = cand["record"]
            new_sid = sid + "R"
            examined = [{"position": i, "claim_id": pools[cell][i]["record"]["claim_id"], "claim": pools[cell][i]["record"]["claim"],
                         "reason_code": code, "reason": REASON[code]} for i, code in sorted(EXAMINED[cell].items()) if i <= pos]
            replacement_log.append({"replaced": sid, "replaced_claim_id": item["claim_id"], "replaced_claim": item["claim_text"],
                                    "why_replaced": "no element of its factual basis is in material the run saved (prediction-market odds only)",
                                    "replacement": new_sid, "cell": cell, "hash_order_position": pos, "replacement_claim_id": r["claim_id"],
                                    "examined_before_and_including": examined})
            base = {"sample_id": new_sid, "cell": item["cell"], "ticker": r.get("ticker") or cand["run"]["metadata"].get("ticker"),
                    "analysis_date": cand["run"]["metadata"].get("analysis_date"), "agent": r.get("agent"), "report_section": r.get("source_section"),
                    "claim_text": r.get("claim"), "evidence_text": r.get("evidence") if r.get("evidence") != r.get("claim") else None,
                    "context": sel.context(cand["run"], r)}
            system = {"run_id": cand["run_id"], "claim_id": r["claim_id"], "claim_quality_in_run": r.get("claim_quality"),
                      "key_conclusion_group": sel.key_conclusion_group(r), "source_link_status_in_run": r.get("source_link_status"),
                      "linked_source_id_in_run": r.get("linked_source_id"), "real_use_in_saved_run": sel.real_use(cand["run_id"], r["claim_id"]),
                      "prior_mentions_in_docs": sel.exposure(r["claim_id"]), "selection": f"replacement of {sid}: first COMPLETE, non-duplicate candidate at hash position {pos}"}
            elements_spec = SPEC[new_sid][1]
            action = "replacement"
        else:
            base = {k: item[k] for k in ("sample_id", "cell", "ticker", "analysis_date", "agent", "report_section", "claim_text", "evidence_text", "context")}
            system = {"run_id": item["run_id"], "claim_id": item["claim_id"], "claim_quality_in_run": item["claim_quality_in_run"],
                      "key_conclusion_group": item["key_conclusion_group"], "source_link_status_in_run": item["time_facts"].get("source_link_status_in_run"),
                      "linked_source_id_in_run": (item.get("source") or {}).get("source_id"), "real_use_in_saved_run": item["real_use_in_saved_run"],
                      "prior_mentions_in_docs": item["prior_mentions_in_docs"], "selection": item["selection_reason"]}
            elements_spec = payload
        run_id = system["run_id"]
        elements, fragments = [], {}
        for text, status, refs, note in elements_spec:
            resolved = []
            for ref in refs:
                key = json.dumps(ref)
                if key not in fragments:
                    fragments[key] = resolve(ref, runs)
                resolved.append(key)
            elements.append({"text": text, "status": status, "material_refs": [fragments[k].get("source_id") or fragments[k].get("artifact") for k in resolved],
                             "note": note})
        status = material_status(elements)
        meta = runs[run_id]["metadata"]
        time_basis = {"analysis_date": meta.get("analysis_date"), "run_started_at": meta.get("created_at")}
        manifest.append({**base, **system, "action": action, "material_status": status, "elements": elements, "material": list(fragments.values()),
                         "time_basis": time_basis})
        coverage.append({"sample_id": base["sample_id"], "cell": base["cell"], "action": action, "material_status": status,
                         "elements": [{"text": e["text"], "status": e["status"], "note": e["note"]} for e in elements]})
        form_items.append({**base, "time_basis": time_basis,
                           "material": list(fragments.values()) or "NO SAVED MATERIAL for this claim",
                           "judgments": dict.fromkeys(("R1_claim_fidelity", "R1_source_relation", "R2_alpha", "R3_direction", "R4_evidence_eligibility", "rationale", "reviewer_id", "reviewer_role", "reviewed_at", "attests_no_prior_view_of_system_outputs"))})
        csv_rows.append({"sample_id": base["sample_id"], "ticker": base["ticker"], "analysis_date": base["analysis_date"], "agent": base["agent"],
                         "report_section": base["report_section"], "claim_text": base["claim_text"],
                         "context_before": " || ".join(x or "" for x in base["context"]["before"]), "context_after": " || ".join(x or "" for x in base["context"]["after"]),
                         "material": json.dumps(list(fragments.values()), ensure_ascii=False) if fragments else "NO SAVED MATERIAL",
                         **dict.fromkeys(("R1_claim_fidelity", "R1_source_relation", "R2_alpha", "R3_direction", "R4_evidence_eligibility", "rationale", "reviewer_id", "reviewer_role", "reviewed_at", "attests_no_prior_view_of_system_outputs"), "")})

    from collections import Counter
    summary = {"by_material_status": dict(Counter(c["material_status"] for c in coverage)),
               "by_action": dict(Counter(c["action"] for c in coverage)),
               "by_cell_and_status": {cell: dict(Counter(c["material_status"] for c in coverage if c["cell"] == cell)) for cell in sel.QUOTA}}
    vocabulary = sel.JUDGMENT_VOCABULARY
    (out_dir / "joint_sample_v4_manifest.json").write_text(json.dumps({
        "schema_version": "t3_joint_sample_v4_manifest.v1", "derived_from": "joint_sample_v3_manifest.json", "quota": sel.QUOTA, "summary": summary,
        "rule": __doc__, "samples": manifest,
        "note": "MANIFEST: contains run usage, links and the element analysis -- never give this file to the reviewer"}, ensure_ascii=False, indent=1) + "\n", encoding="utf-8")
    (out_dir / "review_form_v4.json").write_text(json.dumps({
        "schema_version": "t3_joint_review_form_v4.v1", "system_answers": "NOT INCLUDED -- predictions are produced later and kept in a separate file",
        "instructions": "see B1_reviewer_instructions_v4.md", "judgment_vocabulary": vocabulary, "items": form_items}, ensure_ascii=False, indent=1) + "\n", encoding="utf-8")
    with (out_dir / "review_worksheet_v4.csv").open("w", encoding="utf-8", newline="") as fh:
        writer = csv.DictWriter(fh, fieldnames=list(csv_rows[0].keys()))
        writer.writeheader()
        writer.writerows(csv_rows)
    (out_dir / "material_coverage.json").write_text(json.dumps({"summary": summary, "status_meaning": {
        "COMPLETE": "no element lacks saved material", "PARTIAL": "at least one element has saved material and at least one has none",
        "NO_MATERIAL": "no element has saved material", "NO_FACTUAL_ELEMENT": "the claim states no checkable fact"},
        "samples": coverage}, ensure_ascii=False, indent=1) + "\n", encoding="utf-8")
    (out_dir / "replacement_log.json").write_text(json.dumps({"rule": "first candidate of the same cell, in the frozen hash order, whose material is COMPLETE and which is not a duplicate",
                                                              "reasons": REASON, "replacements": replacement_log}, ensure_ascii=False, indent=1) + "\n", encoding="utf-8")
    (out_dir / "collection_list.json").write_text(json.dumps({
        "status": "PROPOSAL -- not fetched; needs the same authorization as the execution",
        "binding": ("collected material is saved under the new verification execution (URL, retrieval time, HTTP status, sha256), given to the reviewer as an "
                    "addendum before review, and never written into the original runs; it is not presented as material those runs had"),
        "unfixable_by_collection": {"t3v3-032": "states no checkable fact", "t3v3-036": "states no checkable fact"},
        "not_proposed": NOT_PROPOSED, "how": "t3_joint_sample_driver.py collect (stops at the first non-200 or unexpected shape; never exceeds the cap)",
        "items": COLLECTION, "request_cap_total": sum(c["request_cap"] for c in COLLECTION)}, ensure_ascii=False, indent=1) + "\n", encoding="utf-8")
    print(json.dumps(summary, ensure_ascii=False, indent=1))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
