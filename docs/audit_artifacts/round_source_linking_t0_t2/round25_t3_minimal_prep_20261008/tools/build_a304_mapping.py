#!/usr/bin/env python3
"""Round 25 (T3 prep), deliverable 3: John's five A304 situations mapped onto the ORIGINAL error samples and onto the current v7 prompt clauses,
plus the A101/A103 boundary record.

Population: every historical Final Gold sample where the Candidate-3 A304 decision was wrong (10 false positives, 2 false negatives -- John's
"A304 output 16 times, 6 correct"), plus every other A304-boundary and A101/A103 sample of the old 40-item T3 pool. For each: its text and every
saved answer (historical Gold, Candidate-3, v6, v7 dev, ChatGPT AI_REVIEW, the 2026-10-05 label whose reviewer is not recorded).

The SITUATION column is an ENGINEERING TRIAGE written by the coding agent from the claim text alone -- it is not a reference judgment and must
not be scored as one; it exists to show which prompt clause speaks to which situation and where no clause (or a clause that conflicts with the
historical Gold label) exists. No prompt, code or taxonomy is changed by this script.

    python build_a304_mapping.py --out <json>
"""
from __future__ import annotations

import argparse
import csv
import glob
import json
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
REPO = next(p for p in HERE.parents if (p / "comqutor_alpha").is_dir())
sys.path.insert(0, str(REPO))
from comqutor_alpha.structure_engine import week2_llm  # noqa: E402

AUDIT = REPO / "docs/audit_artifacts/round_source_linking_t0_t2"
SITUATIONS = {
    "S1_MENTIONS_VALUATION": "提到了估值 -- valuation vocabulary without a valuation conclusion",
    "S2_DISCUSSES_VALUATION_RISK": "讨论估值风险 -- raises or frames valuation risk (incl. as a question) without asserting it",
    "S3_REFUTES_VALUATION_RISK": "反驳估值风险 -- argues against a valuation-risk view (with or without its own verdict)",
    "S4_CONDITIONAL_RISK": "提出条件性风险 -- a hypothetical / conditional or general-mechanism compression statement",
    "S5_DATA_SUPPORTS_COMPRESSION": "已有数据支持估值压缩 -- a stated multiple characterized as rich / compression asserted with data",
    "X_PRICE_HISTORY": "(adjacent) price moved vs its own history -- not a valuation-vs-fundamentals claim",
    "X_DRIVER_PLUS_CONSEQUENCE": "(adjacent) a macro driver (rates) and its valuation consequence in one sentence",
    "X_GENERIC_RISK": "(adjacent) generic risk rhetoric naming no mechanism",
}
# v7 clause numbers = sentence index in _TASK_INSTRUCTIONS["alpha_classifier"].split(". ") (printed into the output for the reader)
CLAUSES_BY_SITUATION = {
    "S1_MENTIONS_VALUATION": [9, 14],
    "S2_DISCUSSES_VALUATION_RISK": [0, 1, 12, 14],
    "S3_REFUTES_VALUATION_RISK": [4, 11, 14],
    "S4_CONDITIONAL_RISK": [0, 11, 12],
    "S5_DATA_SUPPORTS_COMPRESSION": [10, 12],
    "X_PRICE_HISTORY": [13],
    "X_DRIVER_PLUS_CONSEQUENCE": [],
    "X_GENERIC_RISK": [8, 9],
}
# ENGINEERING TRIAGE (coding agent, from the text alone) -- not a reference label
TRIAGE = {
    "nh-final-001": "X_PRICE_HISTORY", "nh-final-008": "X_GENERIC_RISK", "nh-final-020": "S3_REFUTES_VALUATION_RISK",
    "nh-final-033": "S2_DISCUSSES_VALUATION_RISK", "nh-final-045": "S2_DISCUSSES_VALUATION_RISK", "nh-final-055": "S3_REFUTES_VALUATION_RISK",
    "nh-final-058": "S3_REFUTES_VALUATION_RISK", "nh-final-059": "S2_DISCUSSES_VALUATION_RISK", "nh-final-083": "X_DRIVER_PLUS_CONSEQUENCE",
    "nh-final-115": "S3_REFUTES_VALUATION_RISK", "nh-final-124": "S3_REFUTES_VALUATION_RISK", "nh-reserve-020": "S4_CONDITIONAL_RISK",
    "gold-final-057": "S2_DISCUSSES_VALUATION_RISK", "gold-final-061": "S5_DATA_SUPPORTS_COMPRESSION", "gold-final-079": "S4_CONDITIONAL_RISK",
    "gold-final-083": "S5_DATA_SUPPORTS_COMPRESSION", "gold-final-085": "X_DRIVER_PLUS_CONSEQUENCE", "gold-final-097": "S5_DATA_SUPPORTS_COMPRESSION",
}
# Open semantic questions the saved answers expose (the historical Gold label and a prompt clause point different ways, or saved
# labels disagree with each other). Raised for John; nothing is resolved by code.
AMBIGUITIES = [
    {
        "id": "A304-Q1 conditional valuation risk (S4)",
        "samples": ["gold-final-079 'Any slowdown in AI spending could trigger significant multiple compression.'",
                    "nh-reserve-020 'When rates rise, the discount rate rises, and the multiple compresses.'"],
        "conflict": "historical Gold = A304 for both; clause 11 (conditional framing judged by what it asserts now, already in v6) and clause 12 "
                    "(A304 needs valuation asserted rich vs fundamentals) point to NONE; v7 dev returned NONE for 079; the 2026-10-05 label is NONE",
        "question": "Is a conditional or general-mechanism compression statement evidence for A304 (whose thesis is itself a risk), or NONE?",
    },
    {
        "id": "A304-Q2 refutation that states its own valuation verdict (S3)",
        "samples": ["gold-final-051 '... Bull Counter: 30.4x forward P/E, PEG 1.03; Verdict: Fairly valued'",
                    "gold-final-099 'You are applying a backward-looking multiple to a forward-looking earnings explosion.'"],
        "conflict": "clause 4 says a substantive opposition still selects the Alpha (A304 with an opposing stance); historical Gold = NONE (051) and "
                    "A301 (099); the 2026-10-05 label is A304 for 051 and A301 for 099",
        "question": "Does an explicit 'fairly valued / not rich' verdict engage A304 as opposition, or is it NONE (or the growth Alpha it argues from)?",
    },
    {
        "id": "A304-Q3 valuation risk raised as a question (S2)",
        "samples": ["gold-final-041 (Trefis headline 'central question')", "gold-final-052 'whether the current price offers a favorable risk-reward'",
                    "gold-final-057 '... raising whether even the strongest growth numbers can justify where these stocks are priced.'"],
        "conflict": "historical Gold labels these inconsistently (NONE, NONE, A304); clauses 0/1 treat a question as not yet a conclusion; the "
                    "2026-10-05 label for 057 is A301",
        "question": "Is a reported or rhetorical valuation question ever A304 evidence?",
    },
    {
        "id": "A304-Q4 macro driver + valuation consequence in one claim",
        "samples": ["gold-final-072 '89% probability of no Fed cuts ... a headwind for high-multiple growth stocks.'",
                    "gold-final-085 '... odds of no cuts repricing long-duration growth at 29x PE ...'"],
        "conflict": "historical Gold = A304 for both; ChatGPT AI_REVIEW and the 2026-10-05 label = A001 for both; no prompt clause sets a priority "
                    "(already flagged in the v7 adjudication document, section 5)",
        "question": "When a claim states a rate driver and its valuation consequence, which Alpha does it engage -- the driver (A001) or the consequence (A304)?",
    },
    {
        "id": "A101/A103-Q5 named foundry / packaging capacity carrying chip demand",
        "samples": ["gold-final-059 '... demand for Nvidia chips. Every single one of these demand signals flows through TSM's foundry and CoWoS advanced packaging.'"],
        "conflict": "historical Gold = A101; clause 17 (prefer A103 when foundry/advanced-packaging capacity is named) produces A103 -- Candidate-3, "
                    "v6, v7 dev, ChatGPT and the 2026-10-05 label all say A103",
        "question": "Does the facility tie-break rule reflect John's intended A101/A103 boundary, or should chip-demand claims stay A101 even when "
                    "they name the foundry they flow through?",
    },
    {
        "id": "A101/A103-Q6 'AI capex / spending' with no named facility",
        "samples": ["gold-final-077 'When hyperscalers get squeezed ... to justify their AI capex spending, they do not stop spending.'"],
        "conflict": "historical Gold = A101 and ChatGPT = A101; Candidate-3, v6, v7 dev and the 2026-10-05 label = A103 (flagged in the v7 "
                    "adjudication document, section 5)",
        "question": "Which Alpha does bare 'AI capex continues' engage?",
    },
    {
        "id": "A101/A103-Q7 AI infrastructure capex monetized through inference",
        "samples": ["gold-final-084 'Google Cloud & AI Infrastructure: The massive CapEx buildout ... monetizing through cloud services and AI inference demand.'"],
        "conflict": "historical Gold, Candidate-3, v6 and ChatGPT = A103; the 2026-10-05 label = A102",
        "question": "When infrastructure buildout and inference demand are both named, is it A103 or A102?",
    },
]


def main(argv=None) -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--out", required=True)
    args = ap.parse_args(argv)
    out = Path(args.out)
    if out.exists():
        print("refusing: output exists", out, file=sys.stderr)
        return 2
    clauses = [c.strip() for c in week2_llm._TASK_INSTRUCTIONS["alpha_classifier"].split(". ")]
    gold_rows = json.loads((REPO / "docs/audit_artifacts/v0_2_candidate3_final_predictions.json").read_text(encoding="utf-8"))["predictions"]
    s40 = {s["claim_id"]: s for s in json.loads((AUDIT / "t3_targeted_diagnostic_sample_2026-09-30.json").read_text(encoding="utf-8"))["samples"]}
    s40_by_id = {s["sample_id"]: s for s in s40.values()}
    v6 = {json.loads(line)["sample_id"]: json.loads(line) for line in (REPO / "outputs/t3_evaluations/t3live_20261001T014648Z_1fb9c9d5/t3_eval_records.jsonl").open()}
    ai = {json.loads(line)["sample_id"]: json.loads(line) for line in (REPO / "outputs/t3_ai_review_comparisons/t3_ai_review_comparison_two_stage_20261001T190922Z/stage1_all_40.jsonl").open()}
    labels = {r["sample_id"]: r["your_judgment"] for r in csv.DictReader((AUDIT / "t3_human_review_worksheet_COMPLETED_20261005.csv").open(encoding="utf-8"))}
    v7 = {}
    for path in glob.glob(str(REPO / "outputs/t3_prompt_v7_verification/*/t3_eval_records.jsonl")):
        with open(path, encoding="utf-8") as fh:
            for line in fh:
                rec = json.loads(line)
                v7[rec["sample_id"]] = {"raw": rec.get("classifier_status_raw"), "predicted": rec.get("predicted_alpha"), "outcome": rec.get("outcome_code")}
    text_cache: dict[str, dict] = {}

    def text_of(claim_id: str) -> str | None:
        run = claim_id.split(":")[0]
        if run not in text_cache:
            path = REPO / "outputs/runs" / run / "structured_agent_outputs.json"
            text_cache[run] = {r["claim_id"]: r for r in json.loads(path.read_text(encoding="utf-8"))["records"]} if path.exists() else {}
        rec = text_cache[run].get(claim_id)
        return (rec or {}).get("claim") or (s40.get(claim_id) or {}).get("claim_text")

    items = []
    # 1) the historical A304 errors (John's 16-outputs / 6-correct figure, plus the 2 misses)
    for r in gold_rows:
        if (r["candidate3_predicted_label"] == "A304") == (r["gold_label"] == "A304"):
            continue
        t3 = (s40.get(r["claim_id"]) or {}).get("sample_id")
        items.append({
            "population": "historical_A304_error", "gold_set_id": r["sample_id"], "t3_sample_id": t3, "claim_text": text_of(r["claim_id"]),
            "historical_gold": r["gold_label"], "candidate3": r["candidate3_predicted_label"],
            "v6": (v6.get(t3) or {}).get("predicted_alpha") if t3 else None, "v6_outcome": (v6.get(t3) or {}).get("outcome_code") if t3 else None,
            "v7_dev": v7.get(t3) if t3 else None, "chatgpt_ai_review": (ai.get(t3) or {}).get("chatgpt_ai_review_label") if t3 else None,
            "label_2026_10_05": labels.get(t3) if t3 else None, "situation_triage": TRIAGE.get(r["sample_id"]),
        })
    # 2) the other old-pool A304 boundary samples (correct historical A304 outputs etc.)
    seen = {i["t3_sample_id"] for i in items if i["t3_sample_id"]}
    for sid, s in s40_by_id.items():
        if s["quota_category"] != "A304_boundary" or sid in seen:
            continue
        items.append({
            "population": "old_pool_A304_boundary_other", "gold_set_id": None, "t3_sample_id": sid, "claim_text": s["claim_text"],
            "historical_gold": s["historical_gold_label"], "candidate3": s["historical_candidate3_predicted_label"],
            "v6": v6[sid].get("predicted_alpha"), "v6_outcome": v6[sid].get("outcome_code"), "v7_dev": v7.get(sid),
            "chatgpt_ai_review": ai[sid]["chatgpt_ai_review_label"], "label_2026_10_05": labels.get(sid), "situation_triage": TRIAGE.get(sid),
        })
    for item in items:
        sit = item["situation_triage"]
        item["v7_clauses"] = [{"n": n, "text": clauses[n][:400]} for n in CLAUSES_BY_SITUATION.get(sit, [])] if sit else []
    a101_a103 = []
    for sid, s in s40_by_id.items():
        if s["quota_category"] != "A101_A103_differentiation":
            continue
        a101_a103.append({
            "t3_sample_id": sid, "claim_text": s["claim_text"], "historical_gold": s["historical_gold_label"], "candidate3": s["historical_candidate3_predicted_label"],
            "v6": v6[sid].get("predicted_alpha"), "v7_dev": v7.get(sid), "chatgpt_ai_review": ai[sid]["chatgpt_ai_review_label"], "label_2026_10_05": labels.get(sid),
        })
    situation_counts = {}
    for item in items:
        situation_counts[item["situation_triage"]] = situation_counts.get(item["situation_triage"], 0) + 1
    document = {
        "schema_version": "t3_round25_a304_five_situations.v1",
        "prompt": {"version": week2_llm._TASK_RUNTIME_METADATA["alpha_classifier"]["prompt_version"], "identity_sha256": week2_llm.Week2LLMGateway.prompt_identity_sha256("alpha_classifier")},
        "situations": SITUATIONS,
        "clauses_by_situation": CLAUSES_BY_SITUATION,
        "triage_note": "situation_triage is the coding agent's reading of the text, NOT a reference label; it is never scored",
        "situation_counts_in_population": situation_counts,
        "a304_items": items,
        "a101_a103_items": a101_a103,
        "open_semantic_questions_for_john": AMBIGUITIES,
        "not_done": "no prompt, code, threshold or taxonomy change; no historical Gold label changed; nothing adjudicated",
    }
    out.write_text(json.dumps(document, ensure_ascii=False, indent=1) + "\n", encoding="utf-8")
    print(json.dumps({"a304_items": len(items), "a101_a103_items": len(a101_a103), "situations": situation_counts}, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
