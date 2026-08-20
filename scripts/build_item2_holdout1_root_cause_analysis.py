#!/usr/bin/env python3
"""QA Closure v0.1.2 -- Blind Holdout #1 Root-Cause Analysis.

Diagnosis only -- never changes production code, thresholds, weights, or
prompts, never resamples the holdout. Reads only the already-frozen Blind
Holdout #1 artifacts (docs/audit_artifacts/item2_blind_holdout_100*.csv/
.json). PROVIDER_CALLS=0 -- no B1/Alpha Mapper/reviewer call is made here;
this script performs deterministic joins/aggregation plus this analysis's
own explicit, auditable judgments (root_cause/severity/plausibility),
embedded below as literal per-sample_id data -- never mechanically derived
from the labels themselves.
"""

from __future__ import annotations

import csv
import json
import re
import sys
from collections import Counter, defaultdict
from pathlib import Path
from typing import Any

REPO_ROOT = Path(__file__).resolve().parents[1]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

HOLDOUT_PATH = REPO_ROOT / "docs" / "audit_artifacts" / "item2_blind_holdout_100.csv"
B1_PATH = REPO_ROOT / "docs" / "audit_artifacts" / "item2_blind_holdout_b1_predictions.csv"
ALPHA_PATH = REPO_ROOT / "docs" / "audit_artifacts" / "item2_blind_holdout_alpha_predictions.csv"
REVIEW_PATH = REPO_ROOT / "docs" / "audit_artifacts" / "item2_blind_holdout_independent_review.csv"

POLARITY_CSV_OUT = REPO_ROOT / "docs" / "audit_artifacts" / "item2_holdout1_polarity_root_cause.csv"
ALPHA_CSV_OUT = REPO_ROOT / "docs" / "audit_artifacts" / "item2_holdout1_alpha_root_cause.csv"
AI_GATE_CSV_OUT = REPO_ROOT / "docs" / "audit_artifacts" / "item2_holdout1_ai_gate_analysis.csv"
QUALITY_JSON_OUT = REPO_ROOT / "docs" / "audit_artifacts" / "item2_holdout1_quality_conditioned_metrics.json"
SUMMARY_JSON_OUT = REPO_ROOT / "docs" / "audit_artifacts" / "item2_holdout1_root_cause_summary.json"

AI_IDS = {"A101", "A102", "A103"}

# ---------------------------------------------------------------------------
# This analysis's own explicit judgments -- every root_cause/severity/
# plausibility value is a human analytical claim from reading the evidence
# text directly (see item2_holdout1_root_cause_report.md for the reasoning).
# ---------------------------------------------------------------------------

POLARITY_ROOT_CAUSE_LABELS = {
    "A": "SUPPORT_VS_MENTION_BOUNDARY", "B": "SUPPORT_VS_NEUTRAL_BOUNDARY", "C": "OPPOSE_VS_MENTION_BOUNDARY",
    "D": "OPPOSE_VS_NEUTRAL_BOUNDARY", "E": "COUNTER_ALPHA_BOUNDARY", "F": "MIXED_OR_CONDITIONAL_LANGUAGE",
    "G": "MULTI_TOPIC_LANGUAGE", "H": "TARGET_ALPHA_AMBIGUITY", "I": "LOW_INFORMATION_OR_GENERIC",
    "J": "TICKER_CONTEXT_MISSING", "K": "REVIEWER_AMBIGUITY", "L": "B1_PROMPT_INTERPRETATION_ERROR", "M": "OTHER",
}
ALPHA_ROOT_CAUSE_LABELS = {
    "A": "TOP1_RANKING_ERROR", "B": "CANDIDATE_RECALL_ERROR", "C": "AI_HARD_GATE_EXCLUSION",
    "D": "THRESHOLD_EXCLUSION", "E": "TAXONOMY_OVERLAP", "F": "MULTI_TOPIC_SINGLE_TOP1_LIMITATION",
    "G": "KEYWORD_FACTOR_OVERWEIGHT", "H": "DIRECTION_RELATION_RANKING_EFFECT", "I": "EXPECTED_NONE_GENERIC",
    "J": "REVIEWER_AMBIGUITY", "K": "SOURCE_INPUT_QUALITY", "L": "OTHER",
}

POLARITY_JUDGMENTS: dict[str, dict[str, Any]] = {
    "holdout-005": {"rc": "I", "sev": "MEDIUM", "downstream": "NONE", "plaus": "REVIEWER_MORE_PLAUSIBLE", "note": "Tactical trading plan (price levels, SMA) -- positioning strategy, not a fundamental/macro claim. Not used_in_activation/conflict currently."},
    "holdout-006": {"rc": "H", "sev": "LOW", "downstream": "NONE", "plaus": "GENUINELY_AMBIGUOUS", "note": "Company-level cash balance loosely relates to A003 (macro liquidity) or A301 (financial health enabling growth) -- reasonable disagreement about which target is right, not a stance error."},
    "holdout-010": {"rc": "I", "sev": "MEDIUM", "downstream": "NONE", "plaus": "REVIEWER_MORE_PLAUSIBLE", "note": "Same trading-plan pattern as holdout-005 (near-duplicate wording)."},
    "holdout-012": {"rc": "E", "sev": "HIGH", "downstream": "NONE", "plaus": "REVIEWER_MORE_PLAUSIBLE", "note": "'Punished for capex without visible revenue acceleration' is precisely A304's own thesis; reviewer's supports_counter_alpha(A304) is more textually precise than B1's plain opposes_alpha."},
    "holdout-013": {"rc": "J", "sev": "LOW", "downstream": "NONE", "plaus": "REVIEWER_MORE_PLAUSIBLE", "note": "Evidence is about Intel (a competitor), not AMD -- genuinely off-target for AMD's own A101 thesis."},
    "holdout-031": {"rc": "J", "sev": "MEDIUM", "downstream": "B2_SUPPORT_COUNT", "plaus": "GENUINELY_AMBIGUOUS", "note": "OpenAI's own revenue figure requires an inferential step to become MSFT-specific A301 evidence; defensible either way. used_in_activation=True -- this row currently counts toward B2's A301 supporting-evidence tally for MSFT."},
    "holdout-032": {"rc": "I", "sev": "MEDIUM", "downstream": "B2_SUPPORT_COUNT", "plaus": "REVIEWER_MORE_PLAUSIBLE", "note": "Generic macro tail-risk language (yen carry-trade, Middle East tensions), reviewer's own too_generic=True flag. used_in_activation=True."},
    "holdout-033": {"rc": "F", "sev": "MEDIUM", "downstream": "B2_SUPPORT_COUNT", "plaus": "GENUINELY_AMBIGUOUS", "note": "Explicitly mixed (revenue growth vs leadership instability); reviewer's own reasoning says 'neither element clearly dominates'. used_in_activation=True."},
    "holdout-042": {"rc": "F", "sev": "MEDIUM", "downstream": "B2_SUPPORT_COUNT;CONFLICT_ADMISSION", "plaus": "GENUINELY_AMBIGUOUS", "note": "Classic qualified-risk structure ('primary risk is X if Y, but current data points to Z'); used_in_activation=True AND used_in_conflict=True -- highest-stakes row in the polarity mismatch set."},
    "holdout-050": {"rc": "F", "sev": "MEDIUM", "downstream": "B2_SUPPORT_COUNT;CONFLICT_ADMISSION", "plaus": "GENUINELY_AMBIGUOUS", "note": "Explicit balanced synthesis ('on balance... tilt constructive... but genuine valuation risk... argue against'). used_in_activation=True AND used_in_conflict=True."},
    "holdout-052": {"rc": "M", "sev": "LOW", "downstream": "NONE", "plaus": "REVIEWER_MORE_PLAUSIBLE", "note": "A rhetorical debate-mechanics prompt ('let's test that with actual numbers'), not a substantive claim at all -- source-shape issue, not a semantic boundary."},
    "holdout-056": {"rc": "M", "sev": "LOW", "downstream": "NONE", "plaus": "REVIEWER_MORE_PLAUSIBLE", "note": "A bare section header ('On \"Valuation Risk\" Being \"Actively Retired\"') with zero content -- source-segmentation artifact."},
    "holdout-058": {"rc": "I", "sev": "MEDIUM", "downstream": "NONE", "plaus": "GENUINELY_AMBIGUOUS", "note": "Identifies topical relevance (semiconductor exposure) without a directional claim; reviewer's mentions_alpha is slightly more precise but B1's supports_alpha is not unreasonable."},
    "holdout-065": {"rc": "F", "sev": "MEDIUM", "downstream": "NONE", "plaus": "REVIEWER_MORE_PLAUSIBLE", "note": "'Recession risk remains low (12%) but creeping higher' -- specific quantified data with a clear net reading (low = opposes A501); B1 under-committed here, the reverse direction of most other F-bucket rows in this set."},
    "holdout-068": {"rc": "M", "sev": "LOW", "downstream": "NONE", "plaus": "REVIEWER_MORE_PLAUSIBLE", "note": "Evidence text is a truncated fragment cut off mid-sentence ('...vs.') -- source-segmentation artifact, genuinely uninterpretable."},
    "holdout-069": {"rc": "K", "sev": "MEDIUM", "downstream": "NONE", "plaus": "GENUINELY_AMBIGUOUS", "note": "Hypothetical framing ('the neutral analyst might say...'); reviewer's own confidence=low signals real uncertainty in their own judgment."},
    "holdout-070": {"rc": "L", "sev": "MEDIUM", "downstream": "NONE", "plaus": "REVIEWER_MORE_PLAUSIBLE", "note": "Specific, dramatic, causally-linked data point (price move tied to rate expectations) that B1 under-committed on despite it being genuinely resolvable, non-generic text."},
    "holdout-074": {"rc": "F", "sev": "MEDIUM", "downstream": "NONE", "plaus": "GENUINELY_AMBIGUOUS", "note": "Bear-market-then-recovery is a genuinely mixed signal; also sector-level (SOX) rather than SNDK-specific, a secondary contributing factor."},
    "holdout-086": {"rc": "H", "sev": "MEDIUM", "downstream": "NONE", "plaus": "GENUINELY_AMBIGUOUS", "note": "De-rating risk plausibly ties to either A501 (macro-driven) or A304 (valuation-driven, reviewer's read) -- reasonable overlap, this row's target is A501."},
    "holdout-093": {"rc": "I", "sev": "MEDIUM", "downstream": "NONE", "plaus": "REVIEWER_MORE_PLAUSIBLE", "note": "Vague analyst-recommendation summary ('leans constructive/HOLD-to-BUY') with no substantive engagement with the target Alpha's mechanics."},
    "holdout-097": {"rc": "M", "sev": "MEDIUM", "downstream": "NONE", "plaus": "REVIEWER_MORE_PLAUSIBLE", "note": "A bare structured sentiment-score field ('Score: 6.2/10') masquerading as prose evidence -- source-format artifact, reviewer's own high confidence."},
}

ALPHA_JUDGMENTS: dict[str, dict[str, Any]] = {
    "holdout-001": {"rc": "B", "plaus": "REVIEWER_MORE_PLAUSIBLE", "note": "Explicitly challenges linear-growth assumption tied to valuation ('the forward P/E is only reasonable if...'); A304 not in top-5 despite on-thesis valuation language."},
    "holdout-002": {"rc": "B", "plaus": "GENUINELY_AMBIGUOUS", "note": "Vague ('no amount of narrative can overcome' a headwind never specified); reviewer's own too_generic=True. A304 not in top-5."},
    "holdout-005": {"rc": "I", "plaus": "REVIEWER_MORE_PLAUSIBLE", "note": "Trading plan, no fundamental Alpha engagement -- reviewer expects NONE."},
    "holdout-006": {"rc": "E", "plaus": "GENUINELY_AMBIGUOUS", "note": "Company cash balance defensibly maps to either A003 (system) or A301 (reviewer)."},
    "holdout-009": {"rc": "B", "plaus": "REVIEWER_MORE_PLAUSIBLE", "note": "Explicit numeric valuation multiple ('162x earnings') -- squarely A304's own vocabulary, yet A304 absent from top-5. Illustrative of a broader pattern: numeric multiple expressions ('Nx earnings') may under-trigger A304's keyword/factor recall even when semantically on-thesis."},
    "holdout-010": {"rc": "I", "plaus": "REVIEWER_MORE_PLAUSIBLE", "note": "Same trading-plan pattern as holdout-005/holdout-001-adjacent (near-duplicate wording)."},
    "holdout-011": {"rc": "E", "plaus": "GENUINELY_AMBIGUOUS", "note": "High-yield-as-headwind language genuinely engages A001's own domain (rates) even though reviewer's A304 (multiple) reading is also defensible."},
    "holdout-012": {"rc": "B", "plaus": "REVIEWER_MORE_PLAUSIBLE", "note": "Same row as the polarity COUNTER_ALPHA_BOUNDARY case -- A304 not in top-5 despite precise thematic fit."},
    "holdout-027": {"rc": "C", "plaus": "REVIEWER_MORE_PLAUSIBLE", "note": "AI_HARD_GATE_EXCLUSION: A103 (0.68, highest raw score) rejected by the AI hard gate; matched_alpha falls to A101 (0.30). Evidence is literally about 'AI infrastructure investment' scale -- A103's exact domain."},
    "holdout-032": {"rc": "D", "plaus": "REVIEWER_MORE_PLAUSIBLE", "note": "THRESHOLD_EXCLUSION (not AI-gate -- A501 is not an AI alpha): A501 present at score 0.08, below the 0.35 min-match threshold. Generic macro-risk language genuinely reads closer to A501."},
    "holdout-033": {"rc": "E", "plaus": "GENUINELY_AMBIGUOUS", "note": "Mixed OpenAI signal defensibly maps to A301 (revenue) or A601 (narrative framing around a potential $1T IPO)."},
    "holdout-042": {"rc": "A", "plaus": "GENUINELY_AMBIGUOUS", "note": "A101 (expected) present at rank2 (0.48) but ineligible via AI gate; however A304 (system, 0.77) would still outscore it even gate-free -- a genuine ranking gap, not solely a gate artifact. Same qualified-risk sentence as its polarity mismatch."},
    "holdout-043": {"rc": "E", "plaus": "GENUINELY_AMBIGUOUS", "note": "Both 'no rate-cut support' (A001) and 'binary event, elevated expectations' (~priced for perfection, A304) are genuinely present in the text."},
    "holdout-051": {"rc": "E", "plaus": "GENUINELY_AMBIGUOUS", "note": "Explicit recession-probability figure (12%) supports system's A501 reading; 'AI trend masking a slowdown... decoupled' supports reviewer's A601 reading. Both defensible."},
    "holdout-052": {"rc": "I", "plaus": "REVIEWER_MORE_PLAUSIBLE", "note": "Debate prompt, not evidence -- reviewer expects NONE."},
    "holdout-055": {"rc": "E", "plaus": "GENUINELY_AMBIGUOUS", "note": "'Earnings growth outpacing discount rate headwind' explicitly names both earnings (A301) and discount-rate (A001) concepts."},
    "holdout-056": {"rc": "I", "plaus": "REVIEWER_MORE_PLAUSIBLE", "note": "Bare section header, no content -- reviewer expects NONE."},
    "holdout-063": {"rc": "B", "plaus": "REVIEWER_MORE_PLAUSIBLE", "note": "'Hardware constraint, cloud compute capacity' is fairly clearly infrastructure-flavored (A103); A103 present but scored 0.0 -- a genuine recall gap, not just a close ranking loss."},
    "holdout-064": {"rc": "E", "plaus": "GENUINELY_AMBIGUOUS", "note": "'Structural headwind for high-duration growth holdings' could be rate-driven (A001, system) or recession-driven (A501, reviewer) -- genuinely under-specified which macro force is meant."},
    "holdout-068": {"rc": "I", "plaus": "REVIEWER_MORE_PLAUSIBLE", "note": "Truncated fragment -- reviewer expects NONE."},
    "holdout-069": {"rc": "C", "plaus": "GENUINELY_AMBIGUOUS", "note": "AI_HARD_GATE_EXCLUSION: A101 (0.50, highest raw score) rejected by the AI hard gate; system reaches no_match. Reviewer's own confidence=low reflects the evidence's hypothetical framing."},
    "holdout-071": {"rc": "C", "plaus": "REVIEWER_MORE_PLAUSIBLE", "note": "AI_HARD_GATE_EXCLUSION: A103 (0.68, highest raw score) rejected by the AI hard gate; system reaches no_match. 'Early innings of structural AI infrastructure demand shift' is fairly clear A103 language."},
    "holdout-077": {"rc": "C", "plaus": "REVIEWER_MORE_PLAUSIBLE", "note": "AI_HARD_GATE_EXCLUSION: A101 (0.64, highest raw score) rejected by the AI hard gate; matched_alpha falls to A201. High reviewer confidence, specific IBM reference -- one of the two rows (with holdout-027) where the gate appears to reject genuinely substantive, specific evidence, not merely generic AI chatter."},
    "holdout-079": {"rc": "C", "plaus": "GENUINELY_AMBIGUOUS", "note": "AI_HARD_GATE_EXCLUSION: A101 (0.64, highest raw score) rejected by the AI hard gate; system reaches no_match. Reviewer's own reasoning flags this as speculative/conditional with low confidence -- the gate's conservatism is plausibly appropriate here even though it drives the metric miss."},
    "holdout-081": {"rc": "D", "plaus": "GENUINELY_AMBIGUOUS", "note": "THRESHOLD_EXCLUSION (not really AI-gate-determinative): reviewer's A001 present at score 0.08, below threshold, independent of the AI-gate-blocked A102 that happens to be the row's raw top1. Multiple macro factors genuinely co-present in the text."},
    "holdout-084": {"rc": "C", "plaus": "GENUINELY_AMBIGUOUS", "note": "AI_HARD_GATE_EXCLUSION: A103 (0.68, highest raw score) rejected by the AI hard gate; system reaches no_match. Reviewer's own reasoning concedes this is 'a category tag rather than actual evidence', undercutting confidence in their own A103 pick."},
    "holdout-086": {"rc": "D", "plaus": "GENUINELY_AMBIGUOUS", "note": "THRESHOLD_EXCLUSION (not AI-gate -- A304 is not an AI alpha): A304 present at score 0.08, below threshold. De-rating risk from named triggers plausibly maps to either A501 (system) or A304 (reviewer)."},
}

CRITICAL_REVERSAL_IDS: list[str] = []


def _load(path: Path) -> dict[str, dict[str, Any]]:
    with path.open(encoding="utf-8", newline="") as f:
        return {r["sample_id"]: r for r in csv.DictReader(f)}


def _bl(v: str) -> bool:
    return str(v).strip().lower() == "true"


def _parse_ranking(s: str) -> list[tuple[str, float, str]]:
    out = []
    for part in s.split(";"):
        part = part.strip()
        m = re.match(r"([A-Z0-9]+)=([\d.]+)\((\w+)\)", part)
        if m:
            out.append((m.group(1), float(m.group(2)), m.group(3)))
    return out


def build_polarity_rows(holdout, b1, review) -> list[dict[str, Any]]:
    rows = []
    for sid in sorted(POLARITY_JUDGMENTS):
        h, b, r = holdout[sid], b1[sid], review[sid]
        j = POLARITY_JUDGMENTS[sid]
        b_stance, r_stance = b["current_b1_stance"], r["llm_expected_stance"]
        if {b_stance, r_stance} == {"supports_alpha", "opposes_alpha"}:
            CRITICAL_REVERSAL_IDS.append(sid)
        rows.append(
            {
                "sample_id": sid, "ticker": h["ticker"], "target_alpha_id": h["target_alpha_id"],
                "target_alpha_name": None, "claim": h["claim"], "evidence": h["evidence"],
                "current_b1_stance": b_stance, "independent_llm_stance": r_stance,
                "current_b1_counter_alpha_id": b["current_b1_counter_alpha_id"],
                "independent_counter_alpha_id": r["llm_counter_alpha_id"],
                "current_b1_confidence_or_reason_codes": "NOT CAPTURED BY CURRENT B1 ARCHITECTURE",
                "reviewer_confidence": r["llm_confidence"], "reviewer_reason": r["llm_reason"],
                "too_generic": r["llm_too_generic"], "llm_ticker_specific": r["llm_ticker_specific"],
                "duplicate": r["llm_duplicate"], "used_in_activation": h["system_used_in_activation"],
                "used_in_conflict": h["system_used_in_conflict"],
                "root_cause": POLARITY_ROOT_CAUSE_LABELS[j["rc"]], "severity": j["sev"],
                "downstream_consequence": j["downstream"], "plausibility": j["plaus"], "analyst_note": j["note"],
            }
        )
    return rows


def build_alpha_rows(holdout, alpha, review) -> list[dict[str, Any]]:
    rows = []
    for sid in sorted(ALPHA_JUDGMENTS):
        h, a, r = holdout[sid], alpha[sid], review[sid]
        j = ALPHA_JUDGMENTS[sid]
        ranking = _parse_ranking(a["candidate_ranking"])
        expected = r["llm_expected_alpha_id"]
        expected_entry = next((c for c in ranking if c[0] == expected), None)
        raw_top1 = max(ranking, key=lambda c: c[1]) if ranking else None
        rows.append(
            {
                "sample_id": sid, "ticker": h["ticker"], "claim": h["claim"], "evidence": h["evidence"],
                "system_matched_alpha_id": a["matched_alpha_id"] or "NONE",
                "system_matched_alpha_name": a["matched_alpha_name"], "system_match_score": a["match_score"],
                "independent_expected_alpha_id": expected, "reviewer_confidence": r["llm_confidence"],
                "reviewer_reason": r["llm_reason"], "target_alpha_id": h["target_alpha_id"],
                "system_candidate_ranking": a["candidate_ranking"],
                "expected_alpha_candidate_generated": expected_entry is not None,
                "expected_alpha_rank_score": expected_entry[1] if expected_entry else None,
                "expected_alpha_eligible": expected_entry[2] if expected_entry else None,
                "expected_alpha_would_be_raw_top1": bool(raw_top1 and raw_top1[0] == expected),
                "root_cause": ALPHA_ROOT_CAUSE_LABELS[j["rc"]], "plausibility": j["plaus"], "analyst_note": j["note"],
            }
        )
    return rows


def build_ai_gate_rows(holdout, alpha, review) -> list[dict[str, Any]]:
    ai_gate_row_ids = [sid for sid, j in ALPHA_JUDGMENTS.items() if j["rc"] == "C"]
    rows = []
    for sid in sorted(ai_gate_row_ids):
        h, a, r = holdout[sid], alpha[sid], review[sid]
        ranking = _parse_ranking(a["candidate_ranking"])
        ai_candidates = [c for c in ranking if c[0] in AI_IDS]
        raw_top1 = max(ranking, key=lambda c: c[1]) if ranking else None
        rows.append(
            {
                "sample_id": sid, "ticker": h["ticker"],
                "system_matched_alpha": a["matched_alpha_id"] or "NONE",
                "reviewer_expected_alpha": r["llm_expected_alpha_id"],
                "ai_alpha_involved": ";".join(f"{c[0]}={c[1]}({c[2]})" for c in ai_candidates),
                "candidate_score": raw_top1[1] if raw_top1 else None,
                "candidate_rank_before_gate": "1 (highest raw score)" if raw_top1 and raw_top1[0] in AI_IDS else "n/a",
                "gate_passed": False,
                "rejection_reason": "AI alpha hard gate not satisfied: missing an alpha-specific anchor phrase with a locally co-occurring change predicate",
                "final_winner": a["matched_alpha_id"] or "NONE (no_match)",
                "reviewer_confidence": r["llm_confidence"], "too_generic": r["llm_too_generic"],
                "ticker_specific": r["llm_ticker_specific"], "duplicate": r["llm_duplicate"],
                "would_fix_if_gate_removed": ALPHA_JUDGMENTS[sid]["rc"] == "C" and raw_top1 and raw_top1[0] == r["llm_expected_alpha_id"],
            }
        )
    return rows


def build_quality_conditioned(holdout, b1, alpha, review) -> dict[str, Any]:
    def polarity_ok(sid): return b1[sid]["current_b1_stance"] == review[sid]["llm_expected_stance"]
    def alpha_ok(sid): return (alpha[sid]["matched_alpha_id"] or "NONE") == review[sid]["llm_expected_alpha_id"]

    def sub(pred, cond):
        c = t = 0
        for sid in holdout:
            if cond(sid):
                t += 1
                c += int(pred(sid))
        return {"correct": c, "total": t, "accuracy": (c / t if t else None)}

    conditions = {
        "too_generic_false": lambda s: not _bl(review[s]["llm_too_generic"]),
        "too_generic_true": lambda s: _bl(review[s]["llm_too_generic"]),
        "ticker_specific_true": lambda s: _bl(review[s]["llm_ticker_specific"]),
        "ticker_specific_false": lambda s: not _bl(review[s]["llm_ticker_specific"]),
        "duplicate_false": lambda s: not _bl(review[s]["llm_duplicate"]),
        "duplicate_true": lambda s: _bl(review[s]["llm_duplicate"]),
        "not_generic_and_ticker_specific": lambda s: not _bl(review[s]["llm_too_generic"]) and _bl(review[s]["llm_ticker_specific"]),
        "generic_or_non_ticker_specific": lambda s: _bl(review[s]["llm_too_generic"]) or not _bl(review[s]["llm_ticker_specific"]),
    }
    polarity_conditions = dict(conditions, **{
        "used_in_conflict_true": lambda s: _bl(holdout[s]["system_used_in_conflict"]),
        "used_in_conflict_false": lambda s: not _bl(holdout[s]["system_used_in_conflict"]),
        "used_in_activation_true": lambda s: _bl(holdout[s]["system_used_in_activation"]),
        "used_in_activation_false": lambda s: not _bl(holdout[s]["system_used_in_activation"]),
    })
    alpha_conditions = dict(conditions, **{
        "ai_gate_involved": lambda s: (alpha[s]["matched_alpha_id"] in AI_IDS) or (review[s]["llm_expected_alpha_id"] in AI_IDS),
        "ai_gate_not_involved": lambda s: (alpha[s]["matched_alpha_id"] not in AI_IDS) and (review[s]["llm_expected_alpha_id"] not in AI_IDS),
        "reviewer_expected_ai_alpha": lambda s: review[s]["llm_expected_alpha_id"] in AI_IDS,
        "reviewer_expected_non_ai_alpha": lambda s: review[s]["llm_expected_alpha_id"] not in AI_IDS,
        "system_matched_ai_alpha": lambda s: alpha[s]["matched_alpha_id"] in AI_IDS,
        "system_matched_non_ai_alpha": lambda s: alpha[s]["matched_alpha_id"] not in AI_IDS,
    })

    by_ticker_polarity = {t: sub(polarity_ok, lambda s, t=t: holdout[s]["ticker"] == t) for t in sorted({h["ticker"] for h in holdout.values()})}
    by_ticker_alpha = {t: sub(alpha_ok, lambda s, t=t: holdout[s]["ticker"] == t) for t in sorted({h["ticker"] for h in holdout.values()})}
    by_target_alpha_polarity = {a: sub(polarity_ok, lambda s, a=a: holdout[s]["target_alpha_id"] == a) for a in sorted({h["target_alpha_id"] for h in holdout.values()})}
    by_reviewer_alpha = {a: sub(alpha_ok, lambda s, a=a: review[s]["llm_expected_alpha_id"] == a) for a in sorted({review[s]["llm_expected_alpha_id"] for s in review})}
    by_relation_polarity = {rel: sub(polarity_ok, lambda s, rel=rel: holdout[s]["system_relation"] == rel) for rel in sorted({h["system_relation"] for h in holdout.values()})}

    return {
        "polarity_quality_conditioned": {k: sub(polarity_ok, cond) for k, cond in polarity_conditions.items()},
        "alpha_quality_conditioned": {k: sub(alpha_ok, cond) for k, cond in alpha_conditions.items()},
        "polarity_by_ticker": by_ticker_polarity,
        "alpha_by_ticker": by_ticker_alpha,
        "polarity_by_target_alpha": by_target_alpha_polarity,
        "alpha_by_reviewer_expected_alpha": by_reviewer_alpha,
        "polarity_by_relation": by_relation_polarity,
        "note": "DIAGNOSTICS ONLY. Official metrics remain polarity=79/100=79%% and alpha_match=73/100=73%%, both FAIL -- no subgroup accuracy here replaces or is averaged into the official acceptance metric.",
    }


def main() -> int:
    holdout = _load(HOLDOUT_PATH)
    b1 = _load(B1_PATH)
    alpha = _load(ALPHA_PATH)
    review = _load(REVIEW_PATH)

    polarity_rows = build_polarity_rows(holdout, b1, review)
    alpha_rows = build_alpha_rows(holdout, alpha, review)
    ai_gate_rows = build_ai_gate_rows(holdout, alpha, review)
    quality = build_quality_conditioned(holdout, b1, alpha, review)

    for path, rows in [(POLARITY_CSV_OUT, polarity_rows), (ALPHA_CSV_OUT, alpha_rows), (AI_GATE_CSV_OUT, ai_gate_rows)]:
        with path.open("w", encoding="utf-8", newline="") as f:
            writer = csv.DictWriter(f, fieldnames=list(rows[0].keys()))
            writer.writeheader()
            writer.writerows(rows)

    QUALITY_JSON_OUT.write_text(json.dumps(quality, ensure_ascii=False, indent=2, sort_keys=True) + "\n", encoding="utf-8")

    polarity_rc = Counter(r["root_cause"] for r in polarity_rows)
    polarity_sev = Counter(r["severity"] for r in polarity_rows)
    polarity_plaus = Counter(r["plausibility"] for r in polarity_rows)
    alpha_rc = Counter(r["root_cause"] for r in alpha_rows)
    alpha_plaus = Counter(r["plausibility"] for r in alpha_rows)

    def systematic(counter):
        out = {}
        for k, v in counter.items():
            out[k] = "SYSTEMATIC" if v >= 3 else ("REPEATED_BUT_WEAK" if v == 2 else "ISOLATED")
        return out

    gate_rows = [r for r in ai_gate_rows]
    would_fix = [r for r in gate_rows if r["would_fix_if_gate_removed"]]

    summary = {
        "schema_version": "item2_holdout1_root_cause_summary.v1",
        "primary_result_preserved": {"polarity": "79/100=79% FAIL", "alpha_match": "73/100=73% FAIL", "critical_reversals": len(CRITICAL_REVERSAL_IDS)},
        "polarity": {
            "mismatch_count": len(polarity_rows),
            "root_cause_breakdown": dict(polarity_rc),
            "root_cause_systematic": systematic(polarity_rc),
            "severity_breakdown": dict(polarity_sev),
            "plausibility_breakdown": dict(polarity_plaus),
            "downstream_b2_support_count_rows": [r["sample_id"] for r in polarity_rows if "B2_SUPPORT_COUNT" in r["downstream_consequence"]],
            "downstream_conflict_admission_rows": [r["sample_id"] for r in polarity_rows if "CONFLICT_ADMISSION" in r["downstream_consequence"]],
        },
        "alpha": {
            "mismatch_count": len(alpha_rows),
            "root_cause_breakdown": dict(alpha_rc),
            "root_cause_systematic": systematic(alpha_rc),
            "plausibility_breakdown": dict(alpha_plaus),
        },
        "ai_gate_investigation": {
            "directly_caused_mismatch_count": len(gate_rows),
            "would_be_top1_without_gate_count": len(would_fix),
            "would_be_top1_without_gate_sample_ids": [r["sample_id"] for r in would_fix],
            "concentration_by_ticker": dict(Counter(r["ticker"] for r in gate_rows)),
            "verdict": "MIXED_INCONCLUSIVE",
            "verdict_reasoning": (
                "4 of 6 fixable-by-gate-removal rows (holdout-069/071/079/084) show reviewer's own too_generic=True "
                "and/or low confidence, matching the gate's documented target (generic AI/cloud/capex mentions "
                "without specific engagement) -- the gate is plausibly protective for these. 2 of 6 "
                "(holdout-027/077) show high reviewer confidence with specific, substantive content (named "
                "figures, named companies) that the gate still rejects -- a narrow, genuine over-strictness tail. "
                "Net: plausibly protective for the majority, with a real but low-volume (2/100 = 2%) over-strict cost."
            ),
        },
        "duplicate_effective_sample_size": {
            "llm_duplicate_count": 37,
            "system_duplicate_count": 6,
            "overlap_count": 5,
            "exact_text_duplicate_groups_within_holdout": 1,
            "note": "LLM duplicate judgment is genuine semantic/paraphrase clustering (e.g. holdout-005/holdout-010's near-identical trading-plan wording), materially broader than the system's narrow structural evidence_fact_group signal. Exact-text duplication within the 100-row holdout is rare (1 pair). Precise per-cluster membership was not persisted at the row level by this evaluation's own artifacts (only the boolean llm_duplicate survived into the CSV) and cannot be reconstructed without a new Provider call, which this diagnosis-only task does not make -- reported as a disclosed limitation, not fabricated. Duplicate-flagged rows do NOT score worse than non-duplicate rows (81% vs 78% polarity, 84% vs 67% alpha) -- duplication is not a driver of the metric shortfall.",
        },
        "provider_calls": 0,
        "production_code_changes": "NONE",
    }
    SUMMARY_JSON_OUT.write_text(json.dumps(summary, ensure_ascii=False, indent=2, sort_keys=True) + "\n", encoding="utf-8")

    print(f"Wrote {len(polarity_rows)} polarity rows -> {POLARITY_CSV_OUT}")
    print(f"Wrote {len(alpha_rows)} alpha rows -> {ALPHA_CSV_OUT}")
    print(f"Wrote {len(ai_gate_rows)} AI-gate rows -> {AI_GATE_CSV_OUT}")
    print(f"Wrote quality-conditioned metrics -> {QUALITY_JSON_OUT}")
    print(f"Wrote summary -> {SUMMARY_JSON_OUT}")
    print(json.dumps(summary, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
