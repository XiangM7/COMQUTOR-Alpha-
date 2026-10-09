#!/usr/bin/env python3
"""Round 25 (T3 prep), deliverable 2: exposure ledger of the OLD 40-item T3 sample and identity ledger of the human labels imported on
2026-10-05. Every fact is read from a saved file (sample file, code comments, v7 verification records, adjudication and root-cause documents,
the AI-review comparison, the review form); nothing is inferred about a reviewer's identity, authority or blindness.

Exposure categories (the user's three, applied per sample):
  USED_FOR_FIX           the sample was used to change a prompt or code: named as a target in the production prompt/code comments, run in
                         the v7 development verification that accepted the prompt change, or part of the Development Gold set used for
                         Candidate-3 tuning
  PREDICTED_OR_ANALYZED  predicted / AI-reviewed / scored / listed in an analysis, with no record of being used to change prompt or code
  UNCONFIRMABLE          quoted in an error analysis that preceded the prompt change without being named by it -- whether it shaped the
                         change cannot be confirmed either way

    python build_exposure_ledger.py --out <json>
"""
from __future__ import annotations

import argparse
import csv
import json
import re
import sys
from collections import Counter
from pathlib import Path

HERE = Path(__file__).resolve().parent
REPO = next(p for p in HERE.parents if (p / "comqutor_alpha").is_dir())
AUDIT = REPO / "docs" / "audit_artifacts" / "round_source_linking_t0_t2"
SAMPLES = AUDIT / "t3_targeted_diagnostic_sample_2026-09-30.json"
WORKSHEET = AUDIT / "t3_human_review_worksheet_COMPLETED_20261005.csv"
FORM = AUDIT / "t3_human_review_form_2026-09-30.json"
ROOT_CAUSE = AUDIT / "t3_a304_a101_a103_root_cause_analysis_2026-09-29.md"
ADJUDICATION = AUDIT / "t3live_20261001T014648Z_1fb9c9d5_prompt_v7_adjudication.md"
V7_RECORDS = [
    AUDIT / "t3_prompt_v7_verification_phase1_smoke.json",
    AUDIT / "t3_prompt_v7_verification_phase2_remaining18.json",
    AUDIT / "t3_prompt_v7_verification_truncation_retest_4096.json",
]
AI_REVIEW = REPO / "outputs/t3_ai_review_comparisons/t3_ai_review_comparison_two_stage_20261001T190922Z/stage1_all_40.jsonl"
CODE_ROOTS = [REPO / "comqutor_alpha"]
SAMPLE_ID = re.compile(r"(?:gold-final|gold-dev|prod-run)-\d{3}")


def norm(text: str) -> str:
    text = (text or "").replace("\u2019", "'").replace("\u201c", '"').replace("\u201d", '"')
    return re.sub(r"\s+", " ", text).strip().lower()


def quoted_heads(markdown: str) -> list[str]:
    """The claims the root-cause document quotes (*"..."*), cut at the first elision; heads shorter than 15 characters are dropped so a
    bare ticker ("QQQ ...") cannot match an unrelated sample."""
    heads = []
    for quote in re.findall(r'\*"(.+?)"\*', markdown):
        head = norm(re.split(r"\.\.\.|\u2026", quote)[0])[:35]
        if len(head) >= 15:
            heads.append(head)
    return heads


def code_mentions() -> dict[str, list[str]]:
    """sample_id -> production source files whose comments name it (expanding "gold-final-019/041/052/048")."""
    found: dict[str, list[str]] = {}
    for root in CODE_ROOTS:
        for path in root.rglob("*.py"):
            text = path.read_text(encoding="utf-8")
            for match in re.finditer(r"((?:gold-final|gold-dev|prod-run)-\d{3}(?:/\d{3})*)", text):
                head, *tail = match.group(1).split("/")
                prefix = head.rsplit("-", 1)[0]
                for sid in [head] + [f"{prefix}-{n}" for n in tail]:
                    found.setdefault(sid, [])
                    rel = path.relative_to(REPO).as_posix()
                    if rel not in found[sid]:
                        found[sid].append(rel)
    return found


def main(argv=None) -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--out", required=True)
    args = ap.parse_args(argv)
    out = Path(args.out)
    if out.exists():
        print("refusing: output exists", out, file=sys.stderr)
        return 2
    samples = json.loads(SAMPLES.read_text(encoding="utf-8"))["samples"]
    labels = {r["sample_id"]: r for r in csv.DictReader(WORKSHEET.open(encoding="utf-8"))}
    form = json.loads(FORM.read_text(encoding="utf-8"))
    form_items = {i["sample_id"]: i for i in form["review_items"]}
    ai = {}
    for line in AI_REVIEW.open(encoding="utf-8"):
        row = json.loads(line)
        ai[row["sample_id"]] = row
    in_code = code_mentions()
    v7_run = set()
    for path in V7_RECORDS:
        v7_run |= set(SAMPLE_ID.findall(path.read_text(encoding="utf-8")))
    adjudication_text = ADJUDICATION.read_text(encoding="utf-8")
    adjudicated = set(SAMPLE_ID.findall(adjudication_text.split("## 2.")[0]))
    root_cause_heads = quoted_heads(ROOT_CAUSE.read_text(encoding="utf-8"))

    rows = []
    for s in samples:
        sid = s["sample_id"]
        dev_status = s["development_exposure_status"].split(" --")[0]
        quoted_in_root_cause = any(head in norm(s["claim_text"]) for head in root_cause_heads)
        facts = {
            "historical_set": dev_status,
            "named_in_production_code_comments": in_code.get(sid, []),
            "run_in_v7_development_verification": sid in v7_run,
            "adjudicated_in_v7_prompt_document": sid in adjudicated,
            "quoted_in_root_cause_analysis_2026_09_29": quoted_in_root_cause,
            "predicted_by_v6_run": True,  # all 40 (t3live_20261001T014648Z, 40/40 records)
            "reviewed_by_chatgpt_ai_review": sid in ai,
            "labeled_2026_10_05": bool(labels.get(sid, {}).get("your_judgment")),
        }
        reasons = []
        if facts["named_in_production_code_comments"]:
            reasons.append("named as a target in " + ", ".join(facts["named_in_production_code_comments"]))
        if facts["run_in_v7_development_verification"]:
            reasons.append("run in the v7 development verification that accepted the prompt change")
        if dev_status == "DEVELOPMENT_SEEN":
            reasons.append("Development Gold set, used for Candidate-3 tuning / error analysis")
        if reasons:
            category = "USED_FOR_FIX"
        elif quoted_in_root_cause or facts["adjudicated_in_v7_prompt_document"]:
            category = "UNCONFIRMABLE"
            reasons.append("quoted in an error analysis written before the v7 prompt change, but not named by it")
        else:
            category = "PREDICTED_OR_ANALYZED"
            reasons.append("predicted by v6, AI-reviewed, labeled and scored; no record of use in a prompt or code change")
        label = labels.get(sid, {})
        rows.append({
            "sample_id": sid,
            "quota_category": s["quota_category"],
            "ticker": s["ticker"],
            "exposure_category": category,
            "exposure_reasons": reasons,
            "facts": facts,
            "label_2026_10_05": label.get("your_judgment") or None,
            "label_reviewer_id": label.get("reviewer_id") or None,
            "label_reviewed_at_in_form": form_items.get(sid, {}).get("reviewed_at"),
            "historical_gold_label": s.get("historical_gold_label") if not str(s.get("historical_gold_label", "")).startswith("NOT_APPLICABLE") else None,
            "chatgpt_ai_review_label": ai.get(sid, {}).get("chatgpt_ai_review_label"),
        })
    gold_disagreements = [
        {"sample_id": r["sample_id"], "historical_gold_label": r["historical_gold_label"], "label_2026_10_05": r["label_2026_10_05"], "exposure_category": r["exposure_category"]}
        for r in rows
        if r["historical_gold_label"] is not None and r["label_2026_10_05"] != r["historical_gold_label"]
    ]
    same_as_ai = sum(1 for r in rows if r["label_2026_10_05"] == r["chatgpt_ai_review_label"])
    document = {
        "schema_version": "t3_round25_exposure_and_label_ledger.v1",
        "old_sample_file": SAMPLES.relative_to(REPO).as_posix(),
        "exposure_counts": dict(Counter(r["exposure_category"] for r in rows)),
        "exposure_by_quota": {q: dict(Counter(r["exposure_category"] for r in rows if r["quota_category"] == q)) for q in sorted({r["quota_category"] for r in rows})},
        "label_identity": {
            "file": WORKSHEET.relative_to(REPO).as_posix(),
            "how_it_arrived": "uploaded into this working session as a CSV document on 2026-10-05 (~17:41Z) with no accompanying text, then written to the file above and imported (37 rows, then 3 more after the legal-label-set fix)",
            "reviewer_id_filled": sum(1 for r in rows if r["label_reviewer_id"]),
            "rows": len(rows),
            "form_claims": {"review_status": form.get("review_status"), "human_review_performed": form.get("human_review_performed")},
            "john_approved_recorded": False,
            "authorization_record": "none found",
            "blindness": "the worksheet hid system answers; whether the person labeling had seen the 2026-10-01/02 model outputs, the ChatGPT comparison or the v7 adjudication (all saved before 2026-10-05) is not recorded",
            "agreement_with_chatgpt_ai_review_labels": f"{same_as_ai}/{len(rows)} identical labels; rationales are worded differently (0/40 identical text)",
            "status": "HUMAN_LABELS_IDENTITY_UNRECORDED -- not proven non-human, but not shown to meet John's reference standard (John or a designated reviewer, blind); no approval written back",
        },
        "historical_gold_vs_2026_10_05_label_disagreements": gold_disagreements,
        "samples": rows,
    }
    out.write_text(json.dumps(document, ensure_ascii=False, indent=1) + "\n", encoding="utf-8")
    print(json.dumps({"exposure_counts": document["exposure_counts"], "gold_disagreements": len(gold_disagreements), "same_as_ai": same_as_ai}, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
