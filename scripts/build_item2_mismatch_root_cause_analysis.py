#!/usr/bin/env python3
"""QA Closure v0.1.2, Item 2 Mismatch Root-Cause Analysis.

Diagnosis only -- never changes production code, thresholds, weights, or
prompts. Joins already-frozen artifacts (current B1 stance, independent J3
reviewer, independent LLM provisional Alpha/quality review, source
alpha_matches.json candidate rankings) with this analysis's own explicit,
auditable analytical judgments (root_cause/severity/plausibility), embedded
below as literal per-sample_id data -- never silently inferred, never
recomputed from a heuristic. Every judgment is a human-legible claim you can
independently disagree with by re-reading the same evidence text.

Pure, deterministic, offline: no Provider/LLM call anywhere in this script.
"""

from __future__ import annotations

import csv
import json
import sys
from pathlib import Path
from typing import Any

REPO_ROOT = Path(__file__).resolve().parents[1]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

SAMPLE_PATH = REPO_ROOT / "docs" / "evidence_review_sample_records.json"
LLM_CSV_PATH = REPO_ROOT / "docs" / "audit_artifacts" / "evidence_review_llm_provisional.csv"
B1_CURRENT_CSV_PATH = REPO_ROOT / "docs" / "audit_artifacts" / "b1_llm_stance_50_validation_after_parser_fix.csv"
J3_PATH = REPO_ROOT / "comqutor_alpha" / "config" / "j3_provisional_semantic_benchmark_v0.1.json"
OUTPUTS_RUNS_ROOT = REPO_ROOT / "outputs" / "runs"

POLARITY_CSV_OUT = REPO_ROOT / "docs" / "audit_artifacts" / "item2_polarity_mismatch_analysis.csv"
ALPHA_CSV_OUT = REPO_ROOT / "docs" / "audit_artifacts" / "item2_alpha_mismatch_analysis.csv"
SUMMARY_JSON_OUT = REPO_ROOT / "docs" / "audit_artifacts" / "item2_mismatch_root_cause_summary.json"
REPORT_MD_OUT = REPO_ROOT / "docs" / "audit_artifacts" / "item2_mismatch_root_cause_report.md"

# ---------------------------------------------------------------------------
# This analysis's own explicit judgments. Every field here is a human
# analytical claim made by reading the evidence text directly (see the
# report's row-by-row section for the reasoning) -- never mechanically
# derived from the stance/alpha labels themselves.
# ---------------------------------------------------------------------------

POLARITY_JUDGMENTS: dict[str, dict[str, Any]] = {
    "evrs-006": {"root_cause": "G", "severity": "LOW", "b2_impact": "none (neither stance is supports_alpha; presentation/UI-level only)", "plausibility": "REVIEWER_MORE_PLAUSIBLE", "note": "Third-party hearsay framing ('some people are going to look at...and say') about narrative/backlog, evaluated against a Liquidity Expansion (A003) target it barely engages; neutral_background is the cleaner read."},
    "evrs-007": {"root_cause": "F", "severity": "MEDIUM", "b2_impact": "none (neither stance is supports_alpha)", "plausibility": "REVIEWER_MORE_PLAUSIBLE", "note": "MIXED_STANCE_UNRESOLVED; sentence's own resolution clause ('validated the quarter but not yet the multi-year conversion') leans skeptical, supporting opposes_alpha over the more conservative mentions_alpha."},
    "evrs-008": {"root_cause": "E", "severity": "HIGH", "b2_impact": "none on target A601's own supporting count (neither stance is supports_alpha); possible secondary effect on counter-alpha A501's own count not confirmed by this diagnostic", "plausibility": "REVIEWER_MORE_PLAUSIBLE", "note": "Text explicitly invokes 'recession risk' language matching A501's core thesis; J3's supports_counter_alpha(A501) is more precise than B1's plain opposes_alpha."},
    "evrs-013": {"root_cause": "C", "severity": "MEDIUM", "b2_impact": "none (neither stance is supports_alpha)", "plausibility": "SYSTEM_MORE_PLAUSIBLE", "note": "'AI demand narrative increasingly contested' is a real directional claim undermining A101, not just topic-mention; B1's opposes_alpha reads the skepticism J3's mentions_alpha under-reads."},
    "evrs-020": {"root_cause": "F", "severity": "MEDIUM", "b2_impact": "B2 supporting_evidence_count for A304: +1 under J3's supports_alpha, +0 under B1's mentions_alpha", "plausibility": "GENUINELY_AMBIGUOUS", "note": "Explicit parenthetical hedge '(though sources call it reasonable)' cuts against the primary valuation-risk claim; reasonable to read either way."},
    "evrs-026": {"root_cause": "F", "severity": "MEDIUM", "b2_impact": "B2 supporting_evidence_count for A601: +1 vs +0", "plausibility": "GENUINELY_AMBIGUOUS", "note": "Sentence explicitly frames a 'dominant tension' between two competing narratives; genuinely balanced framing, not a clean directional claim."},
    "evrs-034": {"root_cause": "F", "severity": "MEDIUM", "b2_impact": "B2 supporting_evidence_count for A301: +1 vs +0", "plausibility": "GENUINELY_AMBIGUOUS", "note": "'driving near-term FCF compression BUT positions...for growth' gives roughly equal rhetorical weight to both clauses."},
    "evrs-036": {"root_cause": "F", "severity": "MEDIUM", "b2_impact": "none (neither stance is supports_alpha)", "plausibility": "GENUINELY_AMBIGUOUS", "note": "Meta-rebuttal of a bear narrative ('the bear narrative...ignores...') structurally similar to John's own fixed rebuttal example; genuinely unclear whether the rebuttal itself counts as opposing or merely mentioning Narrative Momentum."},
    "evrs-040": {"root_cause": "F", "severity": "MEDIUM", "b2_impact": "B2 supporting_evidence_count for A304: +1 vs +0", "plausibility": "GENUINELY_AMBIGUOUS", "note": "Explicitly named 'constructive tension...yet elevated sensitivity'; balanced bull/bear framing by the text's own design."},
    "evrs-042": {"root_cause": "E", "severity": "HIGH", "b2_impact": "none on target A301's own count (neither stance is supports_alpha); possible secondary effect on counter-alpha A304's own count not confirmed by this diagnostic", "plausibility": "SYSTEM_MORE_PLAUSIBLE", "note": "Text is explicitly about P/E-multiple compression mechanics (20x->25x+); B1's precise supports_counter_alpha(A304) attribution is better-grounded than J3's plain opposes_alpha."},
    "evrs-045": {"root_cause": "E", "severity": "HIGH", "b2_impact": "none -- row is not used_in_activation or used_in_conflict at all currently, regardless of which stance wins", "plausibility": "REVIEWER_MORE_PLAUSIBLE", "note": "'Headwind for any premium multiple' is squarely A304's thesis; J3's supports_counter_alpha(A304) is more precise than B1's plain opposes_alpha."},
}

ALPHA_JUDGMENTS: dict[str, dict[str, Any]] = {
    "evrs-002": {"root_cause": "C", "plausibility": "SYSTEM_MORE_PLAUSIBLE", "note": "'a downturn in AI demand or a broader economic slowdown could compress earnings' echoes A501's own core_thesis almost verbatim ('economic slowdown pressure earnings'); system's A501 (score 0.81) is a tighter semantic match than the LLM's A201 (rank3, score 0.32), which the LLM itself flagged too_generic/conditional."},
    "evrs-007": {"root_cause": "D", "plausibility": "GENUINELY_AMBIGUOUS", "note": "Expected A304 never generated as a candidate at all. Evidence is about CapEx-to-revenue *conversion timing* risk, not literally about valuation multiples; A304's definition ('rich valuation and high multiples') doesn't cleanly cover 'spending not yet proven to convert to revenue' -- a real taxonomy boundary gap, not obviously a recall bug."},
    "evrs-011": {"root_cause": "A", "plausibility": "GENUINELY_AMBIGUOUS", "note": "Confirmed directly via candidate_scores[].rejection_reason: BOTH A101 (rank1 raw score 0.82, this row's own target_alpha_id) AND A103 (rank2 raw score 0.51, the LLM's independently expected alpha) carry the identical rejection_reason 'AI alpha hard gate not satisfied: missing an alpha-specific anchor phrase with a locally co-occurring change predicate' (comqutor_alpha/structure_engine/ai_alpha_discriminator.py, gating AI_ALPHA_IDS={A101,A102,A103}). matched_alpha fell to A301 (rank3 raw score 0.43, the highest-scoring ELIGIBLE candidate). This is NOT a ranking bug -- it is the confirmed, intended operation of a deliberately-built anti-false-positive gate (see alpha_mapper.py:515-519 comment: loosening this would 'reopen exactly the weak-recall gap this Sprint closes')."},
    "evrs-016": {"root_cause": "A", "plausibility": "GENUINELY_AMBIGUOUS", "note": "Confirmed directly via candidate_scores[].rejection_reason: A103 (rank1 raw score 0.85, the LLM's independently expected alpha) AND A101 (rank2, 0.71) both carry the AI hard-gate rejection_reason; matched_alpha fell to A601 (rank3 by raw score, 0.39, the highest-scoring eligible candidate). Evidence text literally contains the word 'narrative' ('reinforcing the AI spending boom remains alive narrative'), which independently supports A601 on its own textual merits, not just as a gate-driven fallback."},
    "evrs-017": {"root_cause": "A", "plausibility": "GENUINELY_AMBIGUOUS", "note": "Near-tied race: system A501 (0.86) vs LLM's A304 (0.79), both legitimately eligible, both explicitly named side-by-side in the evidence text ('Valuation Risk...and Recession Risk'). LLM's own confidence=medium and too_generic=True flags signal low self-confidence in its own pick."},
    "evrs-023": {"root_cause": "C", "plausibility": "SYSTEM_MORE_PLAUSIBLE", "note": "Evidence is a multi-topic 'kitchen sink' sentence naming AI CapEx, semiconductor cycle, rate cuts, AND liquidity together. System's A003 pick matches the sentence's own closing clause almost verbatim ('Liquidity Expansion supporting the premium multiple'); LLM's A103 pick (rank5, lowest score 0.69) is a looser inference, and the LLM itself flagged too_generic=True."},
    "evrs-030": {"root_cause": "C", "plausibility": "SYSTEM_MORE_PLAUSIBLE", "note": "Byte-identical evidence text to evrs-023 (both QQQ, same sentence) -- same judgment applies; this is one underlying disagreement counted twice by the sampling, not two independent errors."},
    "evrs-031": {"root_cause": "C", "plausibility": "GENUINELY_AMBIGUOUS", "note": "Evidence names BOTH hyperscaler AI CapEx (supports A101) AND AMD's own 34% revenue growth explicitly (textually on-thesis for A301, the system's pick). Close score race (0.76 vs 0.71); genuinely defensible either way."},
    "evrs-041": {"root_cause": "J", "plausibility": "GENUINELY_AMBIGUOUS", "note": "OTHER, precisely: this evidence item is a meta-summary of a bull/bear debate ('the debate produced no decisive winner...') rather than a discrete claim -- an input shape the taxonomy was never designed to cleanly classify. The LLM's own admissibility=conditional flag acknowledges this directly ('meta-summary...rather than a discrete, actionable evidence item')."},
    "evrs-042": {"root_cause": "A", "plausibility": "REVIEWER_MORE_PLAUSIBLE", "note": "A304 present at rank2 (0.32) behind A301 (0.69) -- a real ranking loss, not an eligibility exclusion. The sentence's own rhetorical climax ('the cheap 20x P/E will quickly become an expensive 25x+ P/E') is precisely A304's domain; LLM's pick tracks the sentence's actual emphasis better than the system's A301 top-1."},
    "evrs-043": {"root_cause": "B", "plausibility": "REVIEWER_MORE_PLAUSIBLE", "note": "Expected A201 never generated as a candidate. Evidence is specifically about inventory ($25.80B) and receivables ($40.71B) outpacing revenue -- squarely within A201's own vocabulary (inventory improves/degrades, chip demand cycle) even though the polarity here is cautionary rather than confirmatory; a real candidate-generation gap, not just a close ranking loss."},
    "evrs-044": {"root_cause": "A", "plausibility": "GENUINELY_AMBIGUOUS", "note": "Confirmed directly via candidate_scores[].rejection_reason: A103 (rank1 raw score 0.85, the LLM's independently expected alpha) carries the AI hard-gate rejection_reason; A101 does not (eligible=True) and becomes matched_alpha (rank2 by raw score, 0.52). The LLM's own reasoning flags weak ticker-specificity for its own A103 pick ('references MSFT rather than NVDA'), which cuts toward the system's A101 being the more defensible choice for this specific row."},
    "evrs-045": {"root_cause": "C", "plausibility": "GENUINELY_AMBIGUOUS", "note": "Evidence bridges two alphas by its own construction: 'headwind for any premium multiple' (A304) 'attached to...AI supercycle narrative' (A601, the system's pick). LLM's own confidence=low (the lowest of all 14) signals genuine uncertainty, not a confident correction."},
    "evrs-049": {"root_cause": "C", "plausibility": "GENUINELY_AMBIGUOUS", "note": "Evidence explicitly names both institutional AI-growth positioning (A601, LLM's pick) and retail's rich-valuation wariness (A304, system's pick) in the same sentence; genuinely a dual-topic claim."},
}

CRITICAL_REVERSAL_SAMPLE_IDS: list[str] = []  # re-verified empty below, not assumed


def _load_system_records() -> dict[str, dict[str, Any]]:
    data = json.loads(SAMPLE_PATH.read_text(encoding="utf-8"))
    return {r["sample_id"]: r for r in data["records"]}


def _load_llm_rows() -> dict[str, dict[str, Any]]:
    with LLM_CSV_PATH.open(encoding="utf-8", newline="") as f:
        return {r["sample_id"]: r for r in csv.DictReader(f)}


def _load_b1_current() -> dict[str, dict[str, Any]]:
    with B1_CURRENT_CSV_PATH.open(encoding="utf-8", newline="") as f:
        return {r["sample_id"]: r for r in csv.DictReader(f)}


def _load_j3() -> dict[str, dict[str, Any]]:
    payload = json.loads(J3_PATH.read_text(encoding="utf-8"))
    return {r["sample_id"]: r for r in payload["rows"]}


def _candidate_ranking_for(sample_id: str, system: dict[str, dict[str, Any]]) -> list[dict[str, Any]]:
    """Diagnostic-only re-sort by raw score descending (NOT the production
    eligible-first order alpha_mapper.py actually uses for its own
    matched_alpha selection -- see alpha_mapper._sort_candidates). Labeled
    explicitly as such everywhere it is reported."""
    row = system[sample_id]
    run_id = row["source_run_id"]
    matches_path = OUTPUTS_RUNS_ROOT / run_id / "alpha_matches.json"
    matches = json.loads(matches_path.read_text(encoding="utf-8"))["matches"]
    by_claim = {m["claim_id"]: m for m in matches}
    m = by_claim.get(row["claim_id"])
    if m is None:
        return []
    return sorted(m.get("candidate_scores") or [], key=lambda c: -(c.get("score") or 0))


def build_polarity_rows() -> list[dict[str, Any]]:
    system = _load_system_records()
    llm = _load_llm_rows()
    b1 = _load_b1_current()
    j3 = _load_j3()
    rows = []
    for sample_id in sorted(POLARITY_JUDGMENTS):
        s = system[sample_id]
        b = b1[sample_id]
        j = j3[sample_id]
        judgment = POLARITY_JUDGMENTS[sample_id]
        current_b1_stance = b["final_stance"]
        independent_stance = j["reviewed_stance"]
        if {current_b1_stance, independent_stance} == {"supports_alpha", "opposes_alpha"}:
            CRITICAL_REVERSAL_SAMPLE_IDS.append(sample_id)
        rows.append(
            {
                "sample_id": sample_id,
                "ticker": s["ticker"],
                "target_alpha_id": s["target_alpha_id"],
                "target_alpha_name": s["target_alpha_name"],
                "evidence": s["evidence"],
                "current_b1_stance": current_b1_stance,
                "independent_llm_stance": independent_stance,
                "current_b1_counter_alpha_id": b["counter_alpha_id"] or "",
                "independent_counter_alpha_id": j.get("reviewed_counter_alpha_id") or "",
                "current_b1_confidence_or_reason": "NOT CAPTURED BY b1_llm_stance_50_validation_after_parser_fix.csv (no confidence/reason column)",
                "independent_confidence": j.get("review_confidence") or "",
                "independent_reason": "NOT CAPTURED BY j3_provisional_semantic_benchmark_v0.1.json (no review_reason field in frozen benchmark rows)",
                "used_in_activation": s["used_in_activation"],
                "used_in_conflict": s["used_in_conflict"],
                "root_cause": judgment["root_cause"],
                "severity": judgment["severity"],
                "b2_downstream_impact": judgment["b2_impact"],
                "plausibility_assessment": judgment["plausibility"],
                "analyst_note": judgment["note"],
            }
        )
    return rows


def build_alpha_rows() -> list[dict[str, Any]]:
    system = _load_system_records()
    llm = _load_llm_rows()
    rows = []
    for sample_id in sorted(ALPHA_JUDGMENTS):
        s = system[sample_id]
        l = llm[sample_id]
        judgment = ALPHA_JUDGMENTS[sample_id]
        candidates = _candidate_ranking_for(sample_id, system)
        expected = l["llm_expected_alpha_id"]
        rank = next((i for i, c in enumerate(candidates, 1) if c.get("alpha_id") == expected), None)
        expected_score = next((c.get("score") for c in candidates if c.get("alpha_id") == expected), None)
        rows.append(
            {
                "sample_id": sample_id,
                "ticker": s["ticker"],
                "evidence": s["evidence"],
                "system_matched_alpha_id": s["matched_alpha_id"],
                "system_matched_alpha_name": s["matched_alpha_name"],
                "system_match_score_top1_raw": candidates[0]["score"] if candidates else None,
                "system_candidate_ranking_by_raw_score": "; ".join(
                    f"{c['alpha_id']}={c.get('score')}" for c in candidates
                ),
                "independent_expected_alpha_id": expected,
                "independent_expected_alpha_confidence": l["llm_confidence"],
                "independent_expected_alpha_reason": l["llm_reason"],
                "target_alpha_id": s["target_alpha_id"],
                "expected_alpha_in_system_candidate_set": rank is not None,
                "expected_alpha_rank_by_raw_score": rank,
                "expected_alpha_score_by_raw_score": expected_score,
                "root_cause": judgment["root_cause"],
                "plausibility_assessment": judgment["plausibility"],
                "analyst_note": judgment["note"],
            }
        )
    return rows


ROOT_CAUSE_LABELS_POLARITY = {
    "A": "SUPPORT_VS_MENTION_BOUNDARY", "B": "SUPPORT_VS_NEUTRAL_BOUNDARY", "C": "OPPOSE_VS_MENTION_BOUNDARY",
    "D": "OPPOSE_VS_NEUTRAL_BOUNDARY", "E": "COUNTER_ALPHA_BOUNDARY", "F": "MIXED_OR_CONDITIONAL_LANGUAGE",
    "G": "TARGET_ALPHA_AMBIGUITY", "H": "PROMPT_INTERPRETATION_ERROR", "I": "TAXONOMY_DEFINITION_AMBIGUITY",
    "J": "REVIEWER_AMBIGUITY", "K": "OTHER",
}
ROOT_CAUSE_LABELS_ALPHA = {
    "A": "TOP1_RANKING_ERROR", "B": "CANDIDATE_RECALL_ERROR", "C": "TAXONOMY_OVERLAP",
    "D": "ALPHA_DEFINITION_AMBIGUITY", "E": "KEYWORD_OR_FACTOR_OVERWEIGHT", "F": "DIRECTION_OR_RELATION_EFFECT",
    "G": "LLM_TIER_DISAGREEMENT", "H": "GENERIC_OR_UNMAPPABLE", "I": "REVIEWER_AMBIGUITY", "J": "OTHER",
}


def build_summary(polarity_rows: list[dict[str, Any]], alpha_rows: list[dict[str, Any]]) -> dict[str, Any]:
    from collections import Counter

    polarity_root_causes = Counter(ROOT_CAUSE_LABELS_POLARITY[r["root_cause"]] for r in polarity_rows)
    polarity_severity = Counter(r["severity"] for r in polarity_rows)
    polarity_plausibility = Counter(r["plausibility_assessment"] for r in polarity_rows)

    alpha_root_causes = Counter(ROOT_CAUSE_LABELS_ALPHA[r["root_cause"]] for r in alpha_rows)
    alpha_plausibility = Counter(r["plausibility_assessment"] for r in alpha_rows)

    absent = sum(1 for r in alpha_rows if not r["expected_alpha_in_system_candidate_set"])
    rank2 = sum(1 for r in alpha_rows if r["expected_alpha_rank_by_raw_score"] == 2)
    rank3plus = sum(
        1 for r in alpha_rows if isinstance(r["expected_alpha_rank_by_raw_score"], int) and r["expected_alpha_rank_by_raw_score"] >= 3
    )
    eligibility_gate_excluded = sum(
        1 for r in alpha_rows if r["sample_id"] in ("evrs-011", "evrs-016", "evrs-044")
    )

    def systematic(counter: Counter) -> dict[str, str]:
        return {k: ("SYSTEMATIC" if v >= 2 else "ISOLATED") for k, v in counter.items()}

    return {
        "schema_version": "item2_mismatch_root_cause_summary.v1",
        "current_metrics": {"b1_polarity": "39/50 = 78%", "alpha_match": "36/50 = 72%"},
        "polarity_mismatches": {
            "count": len(polarity_rows),
            "critical_reversal_count": len(CRITICAL_REVERSAL_SAMPLE_IDS),
            "critical_reversal_sample_ids": CRITICAL_REVERSAL_SAMPLE_IDS,
            "severity_breakdown": dict(polarity_severity),
            "root_cause_breakdown": dict(polarity_root_causes),
            "root_cause_systematic_vs_isolated": systematic(polarity_root_causes),
            "plausibility_breakdown": dict(polarity_plausibility),
        },
        "alpha_mismatches": {
            "count": len(alpha_rows),
            "expected_alpha_absent_count": absent,
            "expected_alpha_rank2_count": rank2,
            "expected_alpha_rank3plus_count": rank3plus,
            "expected_alpha_ai_gate_eligibility_excluded_count": eligibility_gate_excluded,
            "root_cause_breakdown": dict(alpha_root_causes),
            "root_cause_systematic_vs_isolated": systematic(alpha_root_causes),
            "plausibility_breakdown": dict(alpha_plausibility),
        },
        "note": "All root_cause/severity/plausibility fields are this analysis's own explicit judgments (see scripts/build_item2_mismatch_root_cause_analysis.py POLARITY_JUDGMENTS/ALPHA_JUDGMENTS and the accompanying .md report's row-by-row reasoning) -- never mechanically derived from the labels themselves.",
    }


def _write_csv(path: Path, rows: list[dict[str, Any]]) -> None:
    with path.open("w", encoding="utf-8", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=list(rows[0].keys()))
        writer.writeheader()
        writer.writerows(rows)


def main() -> int:
    polarity_rows = build_polarity_rows()
    alpha_rows = build_alpha_rows()
    summary = build_summary(polarity_rows, alpha_rows)

    _write_csv(POLARITY_CSV_OUT, polarity_rows)
    _write_csv(ALPHA_CSV_OUT, alpha_rows)
    SUMMARY_JSON_OUT.write_text(json.dumps(summary, ensure_ascii=False, indent=2, sort_keys=True) + "\n", encoding="utf-8")

    print(f"Wrote {len(polarity_rows)} polarity mismatch rows -> {POLARITY_CSV_OUT}")
    print(f"Wrote {len(alpha_rows)} alpha mismatch rows -> {ALPHA_CSV_OUT}")
    print(f"Wrote summary -> {SUMMARY_JSON_OUT}")
    print(json.dumps(summary, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
