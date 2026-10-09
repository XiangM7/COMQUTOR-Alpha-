#!/usr/bin/env python3
"""Round 22 item 5: every number the corrected acceptance report quotes, computed from the saved final execution -- plus the 34-item
coverage mapping and John's optional spot-check sheet. Read-only on ``outputs/``; zero Provider / search / fetch calls.

* ``report_numbers.json``      link methods (88 + 172 + 1 = 261), the technical-failure subset (107 of the 261), the 51 key conclusions,
                               analytical / numeric-claim link rates, sources by type
* ``coverage_mapping_34.json`` which PROBLEM TYPES behind the original 34 items the new flow was exercised on in real runs. It says what the
                               flow demonstrated; it does NOT say any of the old 34 items was verified (they stay 未验证, never backfilled)
* ``john_spot_check_sample.csv`` a deterministic sample of claims the system counts as verified, with the saved material beside them, so the
                               reviewer can judge "does the content correspond to the claim". REFERENCE ONLY: not a gate, no approval flag is set,
                               nothing reads it back.
"""
from __future__ import annotations

import csv
import json
import sys
from collections import Counter, defaultdict
from pathlib import Path

HERE = Path(__file__).resolve().parent
REPO = HERE.parents[3]
sys.path.insert(0, str(REPO))

from comqutor_alpha.graph_engine.claim_data_grounding import extract_number_tokens  # noqa: E402
from comqutor_alpha.source_provenance import compute_verified_support_eligibility  # noqa: E402

FINAL = "dependency-20261007T220450Z-33128621"
RUN = REPO / "outputs" / "runs" / FINAL
ROUND19 = REPO / "docs/audit_artifacts/round_source_linking_t0_t2/round19_consumption_and_acceptance_20261007"
UPSTREAM = {"fundamental_agent", "market_agent", "news_agent"}
jload = lambda p: json.loads(Path(p).read_text(encoding="utf-8"))  # noqa: E731

records = jload(RUN / "structured_agent_outputs.json")["records"]
matches = {m["claim_id"]: m for m in jload(RUN / "alpha_matches.json")["matches"]}
sources = jload(RUN / "source_registry.json")["sources"]
by_id = {s["source_id"]: s for s in sources}
trace = jload(RUN / "evidence_trace.json")
key_ids = {r["claim_id"] for g in trace["key_conclusions"]["groups"] for r in g["rows"]}
metadata = jload(RUN / "metadata.json")

linked = [r for r in records if r.get("source_link_status") == "VALID"]
tech = [r for r in linked if r.get("content_support_llm_fallback_reason")]
eligibility = {r["claim_id"]: compute_verified_support_eligibility(r, sources) for r in linked}
numeric = lambda r: bool(extract_number_tokens(r.get("claim", "")))  # noqa: E731

analytical = [r for r in records if r.get("claim_quality") == "analytical"]
numbers = {
    "execution": FINAL, "claims_total": len(records),
    "link_methods_among_the_linked": {
        "linked_total": len(linked), **dict(Counter(r.get("source_link_method") for r in linked)),
        "reading": ("ORIGINAL_AGENT_MARKER_CITED = the agent wrote the saved fragment marker; NORMALIZED_FIELD_MATCH_CANDIDATE = a deterministic field/number "
                    "match by the system; CONTENT_MATCH_CANDIDATE = a deterministic whole-excerpt content match (one claim: the company-name heading of the "
                    "fundamentals report); title matching accounts for none. 88 + 172 + 1 = 261."),
        "the_one_content_match_claim": [r["claim_id"].split(":", 1)[1] for r in linked if r.get("source_link_method") == "CONTENT_MATCH_CANDIDATE"],
    },
    "technical_failure_subset": {
        "population": "the 261 linked claims (NOT a subset of the 141 linked analytical claims)",
        "technical_fallbacks": len(tech), "by_reason": dict(Counter(r["content_support_llm_fallback_reason"] for r in tech)),
        "by_claim_quality": dict(Counter(r.get("claim_quality") for r in tech)),
        "matched_an_alpha": sum(1 for r in tech if matches.get(r["claim_id"], {}).get("match_status") == "matched"),
        "analytical_and_matched_an_alpha": sum(1 for r in tech if r.get("claim_quality") == "analytical" and matches.get(r["claim_id"], {}).get("match_status") == "matched"),
        "analytical_and_matched_by_alpha": dict(Counter(matches[r["claim_id"]].get("matched_alpha") for r in tech
                                                        if r.get("claim_quality") == "analytical" and matches.get(r["claim_id"], {}).get("match_status") == "matched")),
        "in_the_51_key_conclusions": sum(1 for r in tech if r["claim_id"] in key_ids),
        "note": ("No retry was made in this closeout; the real status and reason of each stays as saved. The saved record of a rejected "
                 "'quote_or_data_not_found' keeps no copy of the rejected quote, so its cause (a fabricated quote vs a locating/format problem) cannot be "
                 "told from the saved data."),
        "rejected_quote_retained_on_the_record": sum(1 for r in tech if r["content_support_llm_fallback_reason"] == "quote_or_data_not_found" and r.get("content_support_llm_detail")),
    },
    "key_conclusions": {"count": trace["key_conclusions"]["claim_count"], "status_counts": trace["key_conclusions"]["status_counts"]},
    "analytical_claims": {
        "total": len(analytical), "linked": sum(1 for r in analytical if r.get("source_link_status") == "VALID"),
        "with_a_number": sum(1 for r in analytical if numeric(r)), "with_a_number_and_unlinked": sum(1 for r in analytical if numeric(r) and r.get("source_link_status") != "VALID"),
        "reading": "an analytical claim without a number is judged by importance (key conclusion or not), not by the absence of a number; the 27 unlinked key conclusions are shown as 'not linked / not verified'",
    },
    "sources_by_type": dict(Counter(s["source_type"] for s in sources)), "news_sources_with_saved_body": sum(1 for s in sources if s["source_type"] == "news" and s.get("excerpt")),
    "selected_analysts": metadata.get("selected_analysts"),
    "linked_by_source_type": dict(Counter(by_id[r["linked_source_id"]]["source_type"] for r in linked if r.get("linked_source_id") in by_id)),
    "eligible_by_source_type": dict(Counter(by_id[r["linked_source_id"]]["source_type"] for r in linked if eligibility[r["claim_id"]]["eligible"] and r.get("linked_source_id") in by_id)),
}
(HERE / "report_numbers.json").write_text(json.dumps(numbers, indent=1, ensure_ascii=False), encoding="utf-8")

# ---- 34-item coverage mapping (problem types, not items) --------------------------------------------------------------
l34 = jload(ROUND19 / "amd_34_fixed_acceptance_list.json")
by_code = Counter(i["failure_reason_code"] for i in l34["items"])
downstream = [r for r in records if r["agent"] not in UPSTREAM]
down_numeric = [r for r in downstream if r.get("claim_quality") == "analytical" and numeric(r)]
coverage = {
    "what_this_is": ("For each PROBLEM TYPE behind John's original 34 items: was the new flow exercised on it in a REAL run (the fresh AMD run c904d4cc and the "
                     "executions derived from it), and what is still uncovered. It says what the flow demonstrated. It does NOT say that any of the old 34 items "
                     "was verified: they stay 未验证 and are never backfilled from newer material."),
    "historical_run": "d5b60b8a-66b8-44c1-9f55-ee345e58c48d (evidence cutoff 2026-09-21): 46 news sources, 0 with a saved body; the 34 items are unchanged",
    "new_flow_run": {"run": "c904d4cc-dc09-495c-aec5-b056979948e1", "selected_analysts": metadata.get("selected_analysts"), "sources_by_type": numbers["sources_by_type"]},
    "problem_types": [
        {"type": "C: financial data never saved as a source (nothing to link to)", "old_items": by_code["SOURCE_TYPE_NEVER_CAPTURED_FOR_THIS_RUN__FINANCIAL"], "old_producing_agent": "fundamental_agent",
         "new_flow_exercised": True,
         "evidence": (f"4 financial snapshots saved; {numbers['linked_by_source_type'].get('financial', 0)} claims linked to financial sources, "
                      f"{numbers['eligible_by_source_type'].get('financial', 0)} of them verified-eligible; positive sample claim 31 traced end to end (Round 21)"),
         "still_uncovered": "claims whose verification failed technically (63 financial-linked claims are NOT_REVIEWED) are not yet shown verified"},
        {"type": "C: sentiment data never saved as a source", "old_items": by_code["SOURCE_TYPE_NEVER_CAPTURED_FOR_THIS_RUN__SENTIMENT"], "old_producing_agent": "sentiment_agent",
         "new_flow_exercised": False,
         "evidence": f"the fresh run selected analysts {metadata.get('selected_analysts')}: no sentiment analyst ran, so no sentiment source exists to test against",
         "still_uncovered": "everything: this type has never been exercised by a real run of the new flow"},
        {"type": "B: news source registered (title/URL) but its body never saved", "old_items": by_code["SOURCE_IDENTITY_EXISTS_BODY_NEVER_SAVED__NEWS"], "old_producing_agent": "news_agent",
         "new_flow_exercised": False,
         "evidence": (f"{numbers['sources_by_type'].get('news', 0)} news sources saved with title/URL/publish time, {numbers['news_sources_with_saved_body']} with a body; news_agent claims linked: "
                      f"{sum(1 for r in linked if r['agent'] == 'news_agent')}. The problem type persists in the new run"),
         "still_uncovered": ("a news item WITH a saved summary has never been seen in a real run; why none was saved (provider supplied none / parser did not read the field) cannot be "
                             "told from existing runs. Round 22 adds raw-response saving and offline tests for with/without-summary shapes; no real fetch was made")},
        {"type": "D: downstream agent restates upstream data that was never captured", "old_items": by_code["DOWNSTREAM_SYNTHESIS_OF_UNCAPTURED_UPSTREAM_DATA"], "old_producing_agent": "bull_researcher, portfolio_manager",
         "new_flow_exercised": "partly",
         "evidence": (f"{len(down_numeric)} downstream analytical claims state a number; {sum(1 for r in down_numeric if r.get('source_link_status') == 'VALID')} link to a saved source and "
                      f"{sum(1 for r in down_numeric if eligibility.get(r['claim_id'], {}).get('eligible'))} are verified-eligible"),
         "still_uncovered": "downstream restatement of NEWS-derived data (no news body exists); and most linked downstream claims ended in technical verification failure or an unresolved status"},
    ],
    "total_old_items": len(l34["items"]),
}
(HERE / "coverage_mapping_34.json").write_text(json.dumps(coverage, indent=1, ensure_ascii=False), encoding="utf-8")

# ---- John's optional spot-check sheet ----------------------------------------------------------------------------------------
eligible = [r for r in linked if eligibility[r["claim_id"]]["eligible"]]
strata: dict[tuple[str, bool], list[dict]] = defaultdict(list)
for r in sorted(eligible, key=lambda x: x["claim_id"]):
    strata[(by_id[r["linked_source_id"]]["source_type"], r["agent"] in UPSTREAM)].append(r)
sample: list[dict] = []
quota = {("financial", True): 6, ("financial", False): 5, ("market", True): 4, ("market", False): 3}
for key, take in quota.items():
    pool = strata.get(key, [])
    step = max(1, len(pool) // take) if pool else 1
    sample += pool[::step][:take]
sample += [r for r in eligible if r["claim_id"] in key_ids and r not in sample]  # every verified key conclusion is always included
head = ["序号", "claim_id", "产生Agent", "是否重要结论", "声明原文", "关联来源ID", "来源类型", "来源标题", "关联方式", "核验方法", "核验依据类型", "核验定位", "核验引文/数据",
        "核验理由（节选）", "已保存来源内容（节选）", "【复核人】内容是否对应结论（是/否/部分/无法判断）", "【复核人】备注"]
with open(HERE / "john_spot_check_sample.csv", "w", newline="", encoding="utf-8-sig") as fh:
    writer = csv.writer(fh)
    writer.writerow(head)
    for n, r in enumerate(sample, 1):
        src = by_id[r["linked_source_id"]]
        detail = r.get("content_support_llm_detail") or {}
        if isinstance(detail, str):
            detail = {}
        excerpt = (src.get("excerpt") or "")
        quote = detail.get("supporting_quote_or_data") or ""
        at = excerpt.find(quote[:40]) if quote else -1
        snippet = excerpt[max(0, at - 80): at + 320] if at >= 0 else excerpt[:400]
        writer.writerow([n, r["claim_id"], r["agent"], "是" if r["claim_id"] in key_ids else "否", r.get("claim"), src["source_id"], src["source_type"], src.get("title"),
                         r.get("source_link_method"), r.get("content_support_method"), detail.get("support_basis"), detail.get("used_location"), quote,
                         (detail.get("rationale") or "")[:300], snippet, "", ""])
(HERE / "john_spot_check_sample_README.md").write_text(
    "# John 抽查参考表（仅供验收参考）\n\n"
    f"- 样本：从系统判为“已核验、具备资格”的 {len(eligible)} 条声明中按固定规则抽取 {len(sample)} 条（财务/行情 × 上游分析师/下游 Agent 分层，每层按声明 ID 排序后等距取样；"
    "4 条已核验的重要结论全部包含）。规则写在 `build_report_data.py`，同一份数据重跑得到同一张表。\n"
    "- 用途：让复核人对照右侧已保存的来源内容，判断“内容是否确实对应结论”。**这不是生产资格门槛**：系统不读取这张表，不设置任何 `john_approved` 之类字段，"
    "没有填写的行不改变任何状态。\n"
    "- 最后两列留空，由复核人填写。\n", encoding="utf-8")
print(json.dumps({"report_numbers": "report_numbers.json", "coverage_mapping": "coverage_mapping_34.json", "spot_check_rows": len(sample), "eligible_total": len(eligible),
                  "link_methods": numbers["link_methods_among_the_linked"], "technical_failure_subset": {k: numbers["technical_failure_subset"][k] for k in
                  ("technical_fallbacks", "by_reason", "analytical_and_matched_an_alpha", "in_the_51_key_conclusions", "rejected_quote_retained_on_the_record")}}, ensure_ascii=False, indent=1))
