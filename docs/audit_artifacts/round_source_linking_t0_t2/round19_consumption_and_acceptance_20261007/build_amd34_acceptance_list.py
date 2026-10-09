#!/usr/bin/env python3
"""Round 19 -- John's ORIGINAL AMD 34-item fixed acceptance list, in John's own field names.

The 34 items are the evidence of the admitted main conflict A301__A304 of the ORIGINAL historical AMD run d5b60b8a-... (cutoff 2026-09-21).
This script re-runs the four CURRENT linking mechanisms on that run's FROZEN material (read-only; zero model / network calls), compares every item with the
saved round-4 ledger (v3), and splits "is it still used for the conflict" into three separate facts that must never be merged:
    (a) historical run actually adopted   -- read from the run's own admitted conflict
    (b) eligible under the current rules  -- the production eligibility function applied to the frozen record (a computation, NOT an adoption)
    (c) adopted in an independent execution -- 未执行: no execution has ever been derived from this run
The newer AMD fresh run (c904d4cc-...) is a different run and is never used to backfill this list.
"""
import csv, json, sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
REPO = HERE.parents[3]
sys.path.insert(0, str(REPO))
sys.path.insert(0, str(HERE))

from zh_mapping import zh
from comqutor_alpha.source_provenance import (
    compute_verified_support_eligibility,
    extract_all_source_markers_from_text,
    match_evidence_to_source_candidates,
    match_evidence_to_source_candidates_normalized,
    resolve_external_source_for_claim,
    validate_source_reference,
)

RUN_ID = "d5b60b8a-66b8-44c1-9f55-ee345e58c48d"
RUN = REPO / "outputs" / "runs" / RUN_ID
LEDGER_V3 = REPO / "docs/audit_artifacts/round_source_linking_t0_t2/round4_amd_34_item_reverification_20261004/02_amd_34_item_ledger_v3_CURRENT_MECHANISM.json"
LEDGER_V2 = REPO / "docs/audit_artifacts/round_source_linking_t0_t2/amd_34_item_ledger.json"
jload = lambda p: json.loads(Path(p).read_text())

conflicts, registry, metadata, structured = (jload(RUN / n) for n in ("conflicts.json", "source_registry.json", "metadata.json", "structured_agent_outputs.json"))
sources = registry["sources"]
cutoff = metadata["analysis_date"]
records = {r["claim_id"]: r for r in structured["records"]}
main = conflicts["main_conflict"]
ui = main["evidence_ui"]
v3 = {i["evidence_id"]: i for i in jload(LEDGER_V3)["items"]}
v2 = {i["evidence_id"]: i for i in jload(LEDGER_V2)["items"]}

BUCKET_ZH = {
    "SOURCE_IDENTITY_EXISTS_BODY_NEVER_SAVED__NEWS": ("B", "来源已登记（标题/URL），但当时未保存正文，没有可定位的内容"),
    "SOURCE_TYPE_NEVER_CAPTURED_FOR_THIS_RUN__FINANCIAL": ("C", "该次运行从未把财务数据保存为来源（登记表只有新闻类），数据无处可关联"),
    "SOURCE_TYPE_NEVER_CAPTURED_FOR_THIS_RUN__SENTIMENT": ("C", "该次运行从未把情绪类数据保存为来源，数据无处可关联"),
    "DOWNSTREAM_SYNTHESIS_OF_UNCAPTURED_UPSTREAM_DATA": ("D", "下游Agent对上游未保存材料的综合转述，没有可指向的独立来源"),
}
CATEGORY_ZH = {
    "A": "冻结材料中确有内容，但实现没有接通",
    "B": "来源已登记，但正文/数据行当时未保存",
    "C": "该类来源在这次运行中从未保存",
    "D": "下游综合转述，无独立来源可指",
    "E": "来源内容存在，却不支持该结论",
    "F": "已能关联并验证支持关系",
}
CONTENT_AVAILABLE_ZH = {
    "NO_SOURCE_RECORD_OF_THIS_TYPE_EXISTS": "不可用：这次运行没有此类来源记录",
    "IDENTITY_ONLY_NO_BODY": "不可用：只有来源身份（标题/URL），没有保存正文",
    "DEPENDS_ON_UPSTREAM": "不可用：依赖上游Agent未保存的材料",
}

items = []
for side_key, side in (("bull_evidence", "bull"), ("bear_evidence", "bear"), ("counter_evidence", "counter")):
    for entry in ui.get(side_key) or []:
        cid = entry["representative_claim_id"]
        text = entry.get("evidence_text") or ""
        agent = (entry.get("agents") or ["unknown"])[0]
        record = records.get(cid)
        # --- the four current mechanisms, re-run on the frozen material (same calls as round 4)
        legacy_source, legacy_status = resolve_external_source_for_claim(claim=None, evidence=text, sources=sources)
        old_candidates = match_evidence_to_source_candidates(text, None, sources)
        markers = extract_all_source_markers_from_text(text, sources)
        normalized = match_evidence_to_source_candidates_normalized(text, None, sources, instrument="AMD")
        final, method = None, "NONE"
        if markers:
            v = validate_source_reference(markers[0], sources=sources, evidence_cutoff=cutoff)
            if v["source_link_status"] == "VALID":
                final, method = v, "ORIGINAL_AGENT_MARKER_CITED"
        if final is None:
            for cand, name in [(c, "CONTENT_MATCH_CANDIDATE") for c in old_candidates] + [(c, "NORMALIZED_FIELD_MATCH_CANDIDATE") for c in normalized["candidates"]]:
                v = validate_source_reference(cand, sources=sources, evidence_cutoff=cutoff)
                if v["source_link_status"] == "VALID":
                    final, method = v, name
                    break
        if final is None:
            final = validate_source_reference(None, sources=sources, evidence_cutoff=cutoff)
        prior = v3[cid]
        agrees = (final["source_link_status"], method, final.get("linked_source_id")) == (prior["post_fix_source_link_status"], prior["post_fix_source_link_method"], prior["current_source_id_or_content_location"])
        # --- (b) eligibility under the current rules: the production function on the frozen persisted record (this run predates the link/review fields)
        elig = compute_verified_support_eligibility(record or {}, sources)
        bucket = prior["classification_bucket"]
        category, bucket_zh = BUCKET_ZH.get(bucket, ("?", bucket))
        items.append({
            "n": len(items) + 1,
            "evidence_id": cid, "side": side, "target_alpha_id": entry.get("target_alpha_id"), "producing_agent": agent,
            "evidence_text": (record or {}).get("claim") or text,
            "original_link_status": "UNAVAILABLE", "original_source_id_or_position": None,
            "original_link_status_basis": "John T1原文与原审计记载：34条冲突证据中没有一条关联来源；本次用旧标题匹配机制在冻结材料上复算 = " + str(legacy_status),
            "current_source_id": final.get("linked_source_id"), "current_content_location": None,
            "source_content_available": prior["source_content_available"], "source_content_available_zh": CONTENT_AVAILABLE_ZH.get(prior["source_content_available"], prior["source_content_available"]),
            "post_fix_link_status": final["source_link_status"], "post_fix_link_method": method,
            "content_support_review_result": "NOT_APPLICABLE" if final["source_link_status"] != "VALID" else "PENDING_REVIEW",
            "historical_run_actually_adopted": {"adopted": True, "evidence_side_in_run": side, "conflict_id": main["conflict_id"], "conflict_status_in_run": main["admissibility"]["status"], "conflict_level": main["conflict_level"], "conflict_score": main["conflict_score"]},
            "eligible_under_current_rules": {"eligible": bool(elig["eligible"]), "reason_code": elig["reason_code"], "basis": "生产函数 compute_verified_support_eligibility 作用于该运行冻结的原记录（该运行早于来源关联字段；复算当前机制后仍为 " + final["source_link_status"] + "）。这是资格复算，不是采用。"},
            "adopted_in_independent_execution": "未执行",
            "failure_reason_code": bucket, "failure_reason_category": category, "failure_reason_zh": bucket_zh,
            "mechanism_recomputed": {"legacy_title_match_status": legacy_status, "old_whole_excerpt_candidates": len(old_candidates), "agent_markers_in_text": markers,
                                     "normalized_candidates": len(normalized["candidates"]), "normalized_ambiguous_numbers": normalized["ambiguous_numbers"]},
            "agrees_with_saved_round4_v3_ledger": agrees,
            "also_in_v2_ledger": cid in v2,
        })

assert len(items) == 34 and {i["evidence_id"] for i in items} == set(v3) == set(v2)
registry_facts = {"sources": len(sources), "source_types": sorted({s["source_type"] for s in sources}), "with_excerpt": sum(1 for s in sources if s.get("excerpt")), "with_data_snapshot": sum(1 for s in sources if s.get("data_snapshot")),
                  "sources_with_published_at": sum(1 for s in sources if s.get("published_at"))}
C = lambda it: {k: v for k, v in sorted(__import__("collections").Counter(it).items())}
summary = {
    "run_id": RUN_ID, "evidence_cutoff": cutoff, "conflict": main["conflict_id"], "item_count": 34, "by_side": C(i["side"] for i in items),
    "registry_facts_reconfirmed_now": registry_facts,
    "original_link_status": C(i["original_link_status"] for i in items), "post_fix_link_status": C(i["post_fix_link_status"] for i in items), "post_fix_link_method": C(i["post_fix_link_method"] for i in items),
    "content_support_result": C(i["content_support_review_result"] for i in items),
    "historical_run_actually_adopted": C(i["historical_run_actually_adopted"]["adopted"] for i in items),
    "eligible_under_current_rules": C(i["eligible_under_current_rules"]["eligible"] for i in items), "eligibility_reason": C(i["eligible_under_current_rules"]["reason_code"] for i in items),
    "adopted_in_independent_execution": C(i["adopted_in_independent_execution"] for i in items),
    "failure_reason_buckets": C(i["failure_reason_code"] for i in items), "john_categories": {k: {"zh": CATEGORY_ZH[k], "count": sum(1 for i in items if i["failure_reason_category"] == k)} for k in CATEGORY_ZH},
    "all_34_agree_with_saved_round4_v3_ledger": all(i["agrees_with_saved_round4_v3_ledger"] for i in items),
    "note": "The 34 are NOT backfilled with the newer AMD fresh run's material. Their fate under the new flow can only be shown by a fresh run that captures bodies at fetch time; until then they stay 未验证.",
}
(HERE / "amd_34_fixed_acceptance_list.json").write_text(json.dumps({"schema_version": "amd_34_fixed_acceptance_list.v2", "summary": summary, "items": items}, ensure_ascii=False, indent=1))
head = ["序号", "原 evidence_id", "立场", "目标Alpha", "产生Agent", "证据原文", "原关联状态", "现 source_id", "现内容位置", "来源内容是否可用", "修复后关联状态", "修复后关联方式", "内容支持审核结果",
        "历史运行是否实际采用", "按当前规则是否具备资格", "资格代码", "独立重算是否采用", "未通过原因", "未通过原因代码", "原因类别（A-F）"]
with open(HERE / "amd_34_fixed_acceptance_list.csv", "w", newline="", encoding="utf-8-sig") as f:
    w = csv.writer(f)
    w.writerow(head)
    for i in items:
        h = i["historical_run_actually_adopted"]
        w.writerow([i["n"], i["evidence_id"], i["side"], i["target_alpha_id"], i["producing_agent"], i["evidence_text"], "UNAVAILABLE（不可用/未关联）", i["current_source_id"] or "无", i["current_content_location"] or "无（0/46来源有正文）",
                    i["source_content_available_zh"], "NOT_PROVIDED（" + zh("source_link_status", i["post_fix_link_status"]) + "）", zh("source_link_method", i["post_fix_link_method"]), zh("content_support_status", i["content_support_review_result"]),
                    f"是：原运行已准入冲突 {h['conflict_id']}（{h['conflict_status_in_run']}，{h['conflict_level']}，{h['conflict_score']}），本条列为{h['evidence_side_in_run']}侧证据",
                    "否" if not i["eligible_under_current_rules"]["eligible"] else "是", i["eligible_under_current_rules"]["reason_code"] + "（" + zh("eligibility", i["eligible_under_current_rules"]["reason_code"]) + "）", "未执行",
                    i["failure_reason_zh"], i["failure_reason_code"], i["failure_reason_category"] + "：" + CATEGORY_ZH[i["failure_reason_category"]]])
print(json.dumps(summary, ensure_ascii=False, indent=1))
