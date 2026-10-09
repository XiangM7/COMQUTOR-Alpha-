#!/usr/bin/env python3
"""Round 19 -- the complete, filterable 975-claim acceptance list for the AMD fresh run, built from SAVED artifacts only.

Zero model calls, zero network, read-only on outputs/. Every status shown here is either copied from a saved artifact or recomputed by calling the
production function on the saved record (and checked against the saved totals). Chinese labels come from the fixed table in zh_mapping.py.

Outputs (next to this script):
  claims_975_list.json     full rows (codes + Chinese labels)
  claims_975_list.csv      the same, Chinese columns, UTF-8 with BOM (opens in Excel)
  claims_975_summary.json  counts used by the report: statuses, per-agent, per-Alpha funnel, unlinked-claim diagnostic, 19/24 destinations
"""
import collections, csv, hashlib, json, re, sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
REPO = HERE.parents[3]
sys.path.insert(0, str(REPO))
sys.path.insert(0, str(HERE))

from zh_mapping import ZH, zh
from comqutor_alpha.graph_engine import activation_scorer_v2 as act
from comqutor_alpha.graph_engine import evidence_fact_index as efi
from comqutor_alpha.graph_engine.evidence_source_role import source_role_for_agent
from comqutor_alpha.source_provenance import compute_verified_support_eligibility, evaluate_source_availability

ROOT = "c904d4cc-dc09-495c-aec5-b056979948e1"
RECOVERY = "recovery-20261007T053635Z-26d6cd1a"
DERIVED = "requal-20261007T174744Z-664040d6"
runs = REPO / "outputs" / "runs"
jload = lambda p: json.loads(Path(p).read_text())

d = runs / DERIVED
records = jload(d / "structured_agent_outputs.json")["records"]
payload = jload(d / "alpha_matches.json")
matches = {m["claim_id"]: m for m in payload["matches"]}
sources = jload(d / "source_registry.json")["sources"]
src_by = {s["source_id"]: s for s in sources}
activation = jload(d / "alpha_activations.json")["activation_versions"]["v2_verified"]
act_by = {a["alpha_id"]: a for a in activation["alphas"]}
elig_art = jload(d / "evidence_eligibility_requalification.json")
raw_outputs = {o["agent_output_id"]: o["raw_output"] for o in jload(runs / ROOT / "raw_agent_outputs.json")["agent_outputs"]}
list19 = {c["claim_id"] for c in jload(REPO / "docs/audit_artifacts/round_source_linking_t0_t2/round12_alpha_classifier_audit_fix_20261006/19_analytical_supports_claim_list.json")["claims"]}
list24 = {c["claim_id"] for c in elig_art["claims_requalified"]}
a301_pool = set(act_by["A301"]["claim_ids"])
official_pool_of = {cid: a["alpha_id"] for a in activation["alphas"] for cid in a["claim_ids"]}

# -------------------------------------------------------------------- raw-pool membership (selector only, no verification) per Alpha
raw_pool = {}
raw_excluded = {}
for alpha_id in sorted(act_by):
    eligible, excluded, _ = efi.select_supporting_alpha_claims(payload["matches"], alpha_id)
    raw_pool[alpha_id] = {str(r["claim_id"]) for r in eligible}
    raw_excluded[alpha_id] = {e["claim_id"]: e for e in excluded}

# -------------------------------------------------------------------- numeric-token diagnostic (candidate overlap, NOT verification)
_NUM = re.compile(r"(?<![\w.$])\$?(-?\d{1,3}(?:,\d{3})+(?:\.\d+)?|-?\d+(?:\.\d+)?)(\s?(?:%|[MBK]\b|bn\b|million\b|billion\b))?", re.I)
_UNIT = {"m": 1e6, "million": 1e6, "b": 1e9, "bn": 1e9, "billion": 1e9, "k": 1e3}


def numbers(text, informative_only):
    out = []
    for m in _NUM.finditer(text or ""):
        raw = m.group(1).replace(",", "")
        try:
            value = float(raw)
        except ValueError:
            continue
        unit = (m.group(2) or "").strip().lower()
        digits = re.sub(r"\D", "", raw.split(".")[0])
        has_dec = "." in raw
        is_year = (not has_dec) and not unit and 1990 <= abs(value) <= 2100
        informative = bool(unit) or (has_dec and len(re.sub(r"\D", "", raw)) >= 3) or ((not has_dec) and abs(value) >= 100 and not is_year)
        if informative_only and not informative:
            continue
        cands = {value}
        if unit == "%":
            cands.add(value / 100.0)
        elif unit in _UNIT:
            cands.add(value * _UNIT[unit])
        else:
            cands.update({value * 1e6, value * 1e9, value * 1e3} if (not has_dec and abs(value) >= 100) else set())
        out.append((m.group(0).strip(), cands))
    return out


def snapshot_numbers(source):
    vals = set()
    for m in _NUM.finditer(source.get("excerpt") or ""):
        try:
            vals.add(float(m.group(1).replace(",", "")))
        except ValueError:
            pass

    def walk(o):
        if isinstance(o, dict):
            for v in o.values():
                walk(v)
        elif isinstance(o, list):
            for v in o:
                walk(v)
        elif isinstance(o, (int, float)) and not isinstance(o, bool):
            vals.add(float(o))
    walk(source.get("data_snapshot") or {})
    return vals


def found_in(cands, values):
    return any(abs(c - s) <= 0.006 * abs(s) for c in cands for s in values if s != 0.0) or any(c == 0.0 and 0.0 in values for c in cands)


body_sources = {sid: snapshot_numbers(s) for sid, s in src_by.items() if s.get("excerpt") or s.get("data_snapshot")}
analyst_reports = {k: v for k, v in raw_outputs.items() if k.split(":")[1] in ("market_agent", "news_agent", "fundamental_agent")}
analyst_numbers = {k: {float(m.group(1).replace(",", "")) for m in _NUM.finditer(v) if m.group(1).replace(",", "").replace(".", "", 1).replace("-", "", 1).isdigit()} for k, v in analyst_reports.items()}


def numeric_diagnostic(rec):
    nums = numbers(rec["claim"], informative_only=True)
    if not nums:
        return "U1_NO_NUMERIC_LOCATOR", None, []
    hit_sources = [sid for sid, vals in body_sources.items() if all(found_in(c, vals) for _, c in nums)]
    if hit_sources:
        return "U2_ALL_NUMBERS_IN_A_REGISTERED_SOURCE_BODY", [t for t, _ in nums], hit_sources
    some = [sid for sid, vals in body_sources.items() if any(found_in(c, vals) for _, c in nums)]
    if some:
        return "U3_SOME_NUMBERS_IN_A_REGISTERED_SOURCE_BODY", [t for t, _ in nums], some
    in_reports = [k.split(":", 2)[1] for k, vals in analyst_numbers.items() if all(found_in(c, vals) for _, c in nums)]
    if in_reports:
        return "U4_NUMBERS_ONLY_IN_AN_UPSTREAM_ANALYST_REPORT", [t for t, _ in nums], in_reports
    return "U5_NUMBERS_FOUND_NOWHERE_SAVED", [t for t, _ in nums], []


UNLINKED_ZH = {
    "U1_NO_NUMERIC_LOCATOR": "声明不含可定位的数值（观点/预测/定性表述），无数据记录可供匹配",
    "U2_ALL_NUMBERS_IN_A_REGISTERED_SOURCE_BODY": "声明中的全部数值都出现在某个已保存来源的正文/数据中（仅为候选重合，未经核验；说明存在改进关联算法的空间，不需要外部取数）",
    "U3_SOME_NUMBERS_IN_A_REGISTERED_SOURCE_BODY": "声明中部分数值出现在已保存来源中（候选重合，未经核验）",
    "U4_NUMBERS_ONLY_IN_AN_UPSTREAM_ANALYST_REPORT": "数值只出现在上游分析师报告文本中，未登记为来源（Agent当时所见材料未被保存为来源，或由Agent自行推算；本次保存的材料无法区分）",
    "U5_NUMBERS_FOUND_NOWHERE_SAVED": "数值在已保存的来源和分析师报告中都找不到（可能来自未保存的工具输出，或为Agent自行推算）",
}

# -------------------------------------------------------------------- per-claim rows
CONTEXT_CACHE = {}


def context_offset(rec):
    key = rec["source_agent_output_id"]
    text = raw_outputs.get(key)
    if text is None:
        return None
    i = text.find(rec["claim"][:40])
    return None if i < 0 else i


def time_basis(src):
    if src is None:
        return "NOT_APPLICABLE", None
    if src.get("published_at"):
        return "PUBLISHED_AT", src["published_at"]
    av = evaluate_source_availability(src)
    if av.get("available_before_cutoff"):
        return "REGISTRY_WRITE_TIME_UPPER_BOUND", (src.get("availability") or {}).get("available_by")
    return "UNKNOWN", None


def llm_detail(rec):
    detail = rec.get("content_support_llm_detail")
    return json.loads(detail) if isinstance(detail, str) else (detail or {})


rows = []
elig_counter = collections.Counter()
for rec in records:
    cid = rec["claim_id"]
    m = matches[cid]
    review = rec.get("content_support_review") or {}
    detail = llm_detail(rec)
    elig = compute_verified_support_eligibility(rec, sources)
    elig_counter[elig["reason_code"]] += 1
    linked_ids = [rec["linked_source_id"]] + [s for s in (rec.get("linked_source_ids") or []) if s != rec["linked_source_id"]] if rec.get("linked_source_id") else []
    bound = src_by.get(review.get("linked_source_id") or rec.get("linked_source_id"))
    tb, tb_value = time_basis(bound) if rec["source_link_status"] == "VALID" else ("NOT_APPLICABLE", None)
    hash_ok = None
    if bound is not None and review.get("content_hash"):
        hash_ok = review["content_hash"] == bound.get("content_hash") and hashlib.sha256((bound.get("excerpt") or "").strip().encode()).hexdigest() == bound.get("content_hash")

    # --- classification
    selected_raw = m.get("llm_selected_alpha_id")
    classifier_status = (m.get("classifier") or {}).get("status")
    overrides = [k for k in ("alpha_positive_requirement_override", "alpha_specific_invalidation_override") if m.get(k)]
    matched_alpha = m.get("matched_alpha")
    cand = next((c for c in m["candidate_scores"] if c["alpha_id"] == matched_alpha), None) if matched_alpha else None
    relation = cand["relation"] if cand else "n/a"
    stance = cand["evidence_stance"] if cand else "n/a"

    # --- official-path first failing gate (verified gate -> selector -> role)
    in_pool = official_pool_of.get(cid)
    in_raw = bool(matched_alpha and cid in raw_pool.get(matched_alpha, ()))
    if m["match_status"] == "unavailable":
        gate = "CLASSIFICATION_UNAVAILABLE"
    elif m["match_status"] == "no_match":
        gate = "MAPPER_GATE_OVERRIDE" if overrides else "MODEL_NONE"
    elif in_pool:
        gate = "IN_OFFICIAL_POOL"
    elif not elig["eligible"]:
        gate = f"VERIFIED_GATE_{elig['reason_code']}" if f"VERIFIED_GATE_{elig['reason_code']}" in ZH["not_scored"] else "VERIFIED_GATE_OTHER"
    else:
        sel = raw_excluded.get(matched_alpha, {}).get(cid)
        gate = sel["reason"] if sel and sel["reason"] in ZH["not_scored"] else ("ROLE_OR_GROUPING_GATE" if not in_raw else "ROLE_OR_GROUPING_GATE")
    weight = None
    if in_pool:
        weight = round(m["score"] * act.RELATION_WEIGHTS.get(relation, 0.0) * act.ASSERTION_WEIGHTS.get(str(m["assertion_status"]).lower(), 0.0), 6)

    # --- verification detail
    status, method = rec["content_support_status"], rec["content_support_method"]
    fallback = rec.get("content_support_llm_fallback_reason")
    unsupported = detail.get("unsupported_remainder") or None
    orig_reason = None
    if fallback:
        orig_reason = zh("verification_fallback", fallback)
    elif status not in ("SUPPORTS", "NOT_APPLICABLE") and detail.get("rationale"):
        orig_reason = detail["rationale"][:500]
    used_location = detail.get("used_location")
    if not used_location and rec.get("source_link_method") == "ORIGINAL_AGENT_MARKER_CITED":
        used_location = "Agent原文所引用的片段标记（" + ", ".join(re.findall(r"src_?[0-9a-f]{16}:frag:\d+", rec["claim"])[:3]) + "）"
    fragments = [src_by[s]["fragment_id"] for s in linked_ids if s in src_by and src_by[s].get("fragment_id")]

    # --- steps not executed / not confirmable
    missing = []
    if rec["source_link_status"] != "VALID":
        missing.append("来源关联：未建立；因此内容核验、时间/哈希绑定均未进行")
    else:
        if fallback:
            missing.append(f"内容核验：未完成（{zh('verification_fallback', fallback)}）；该声明的支持关系尚无模型结论")
        elif method in ("UNVERIFIED_OFFLINE_CONTENT_MATCH", "ORIGINAL_AGENT_CITED_UNVERIFIED_SUPPORT"):
            missing.append("内容核验：未由具备资格的方法完成")
    if m["match_status"] == "unavailable":
        missing.append("Alpha分类：请求超时，未获得模型结果，未重试")
    if matched_alpha:
        missing.append("方向/立场：模型判断未获得（第17轮方向判断仅发送第1批即超时停止）；当前立场为确定性规则结果")
        missing.append("Alpha相关强度：模型未判断；match_score 是词面/规则分，不是模型相关强度")
    diag_cat = diag_numbers = diag_where = None
    if rec["source_link_status"] != "VALID":
        diag_cat, diag_numbers, diag_where = numeric_diagnostic(rec)

    rows.append({
        "claim_id": cid, "claim_text": rec["claim"], "agent": rec["agent"],
        "context": {"agent_output_id": rec["source_agent_output_id"], "report_section": rec.get("source_section"), "claim_index_0based": rec.get("claim_index"), "raw_report_char_offset": context_offset(rec)},
        "source": {"linked_source_ids": linked_ids, "fragment_ids": fragments, "data_location": used_location,
                   "source_titles": [src_by[s]["title"] for s in linked_ids if s in src_by], "source_types": sorted({src_by[s]["source_type"] for s in linked_ids if s in src_by})},
        "link": {"status": rec["source_link_status"], "method": rec["source_link_method"]},
        "verification": {"status": status, "method": method, "task_version": "content_support.llm.v2.1" if method == "LLM_CONTENT_SUPPORT_VERIFIED" else None,
                         "llm_status": detail.get("llm_status"), "support_basis": detail.get("support_basis"), "unsupported_part": unsupported,
                         "unsupported_materiality": detail.get("unsupported_remainder_materiality"), "original_reason": orig_reason, "technical_fallback_reason": fallback},
        "eligibility": {"code": elig["reason_code"], "eligible": elig["eligible"], "time_basis": tb, "time_basis_value": tb_value, "review_hash_binding_ok": hash_ok},
        "quality": {"claim_quality": rec["claim_quality"], "reason_codes": rec.get("claim_quality_reason_codes"), "method": "确定性规则（claim_quality，非模型）；声明由确定性断句程序切分（deterministic_splitter）"},
        "classification": {"llm_selected_alpha_raw": selected_raw, "classifier_status": classifier_status, "mapper_override": overrides[0] if overrides else "none",
                           "match_status": m["match_status"], "matched_alpha_final": matched_alpha},
        "relation": {"relation": relation, "assertion_status": m.get("assertion_status"), "semantic_polarity": m.get("semantic_polarity"), "record_direction": rec.get("direction"),
                     "evidence_stance": stance, "method": "确定性文本规则（claim_semantics）+ 确定性立场分类（evidence_stance.deterministic.v1，影子）；模型方向判断未获得"},
        "scoring": {"match_score_lexical": m["score"] if matched_alpha else None, "in_raw_pool_unverified_view": in_raw, "in_official_pool": bool(in_pool), "official_pool_alpha": in_pool,
                    "official_weight_contribution": weight, "not_scored_code": gate},
        "crossref": {"in_19_analytical_supports_list": cid in list19, "in_24_requalified_list": cid in list24, "in_a301_official_pool": cid in a301_pool},
        "unlinked_diagnostic": None if diag_cat is None else {"category": diag_cat, "informative_numbers": diag_numbers, "where_found": diag_where, "note_zh": UNLINKED_ZH[diag_cat], "is_verification": False},
        "steps_not_executed_or_unconfirmable": missing,
    })

# -------------------------------------------------------------------- sanity: recomputed eligibility equals the saved totals
saved_counts = elig_art["summary"]["eligibility_reason_counts_after"]
assert dict(elig_counter) == saved_counts, (dict(elig_counter), saved_counts)
assert {r["claim_id"] for r in rows if r["scoring"]["in_official_pool"]} == a301_pool

# -------------------------------------------------------------------- validate the numeric heuristic on LINKED numeric claims (should mostly be 'all numbers in a source body')
check = collections.Counter()
for rec in records:
    if rec["source_link_status"] != "VALID":
        continue
    nums = numbers(rec["claim"], informative_only=True)
    if not nums:
        check["linked_no_numeric_locator"] += 1
        continue
    own = [s for s in ([rec["linked_source_id"]] + (rec.get("linked_source_ids") or [])) if s in body_sources]
    check["linked_all_numbers_in_own_source" if any(all(found_in(c, body_sources[s]) for _, c in nums) for s in own) else "linked_numbers_not_all_in_own_source"] += 1

# -------------------------------------------------------------------- summaries
C = lambda it: dict(collections.Counter(it).most_common())
by_agent = {}
for agent in sorted({r["agent"] for r in rows}):
    rr = [r for r in rows if r["agent"] == agent]
    by_agent[agent] = {"claims": len(rr), "linked": sum(1 for r in rr if r["link"]["status"] == "VALID"), "eligible": sum(1 for r in rr if r["eligibility"]["eligible"]),
                       "matched": sum(1 for r in rr if r["classification"]["match_status"] == "matched"), "in_official_pool": sum(1 for r in rr if r["scoring"]["in_official_pool"])}
funnel = {}
for alpha_id in sorted(act_by):
    a = act_by[alpha_id]
    selected = [r for r in rows if r["classification"]["llm_selected_alpha_raw"] == alpha_id]
    final = [r for r in rows if r["classification"]["matched_alpha_final"] == alpha_id]
    ver = [r for r in final if r["eligibility"]["eligible"]]
    weighted = [r for r in rows if r["scoring"]["official_pool_alpha"] == alpha_id and (r["scoring"]["official_weight_contribution"] or 0) > 0]
    funnel[alpha_id] = {
        "model_raw_selections": len(selected), "overridden_by_mapper_gate": sum(1 for r in selected if r["classification"]["mapper_override"] != "none"),
        "final_matches": len(final), "final_matches_analytical": sum(1 for r in final if r["quality"]["claim_quality"] == "analytical"),
        "raw_pool_unverified_view": len(raw_pool[alpha_id]), "final_matches_verified_eligible": len(ver),
        "verified_but_excluded_reasons": C(r["scoring"]["not_scored_code"] for r in ver if not r["scoring"]["in_official_pool"]),
        "raw_pool_not_verified_reasons": C(r["eligibility"]["code"] for r in final if r["claim_id"] in raw_pool[alpha_id] and not r["eligibility"]["eligible"]),
        "official_pool_claims": len(a["claim_ids"]), "official_unique_facts": a.get("unique_evidence_count"), "claims_with_positive_weight": len(weighted),
        "official_score": a["activation_score"], "level": a["activation_level"], "direction": a["direction"],
    }
summary = {
    "total_claims": len(rows), "eligibility_recomputed_equals_saved": True, "eligibility_counts": dict(elig_counter),
    "link_status": C(r["link"]["status"] for r in rows), "link_method": C(r["link"]["method"] for r in rows),
    "verification_status_among_linked": C(r["verification"]["status"] for r in rows if r["link"]["status"] == "VALID"),
    "verification_method_among_linked": C(r["verification"]["method"] for r in rows if r["link"]["status"] == "VALID"),
    "technical_fallback_reasons_among_linked": C(r["verification"]["technical_fallback_reason"] for r in rows if r["verification"]["technical_fallback_reason"]),
    "pending_by_kind": {"technical_fallback": sum(1 for r in rows if r["verification"]["status"] == "PENDING_REVIEW" and r["verification"]["technical_fallback_reason"]),
                        "model_judged_insufficient": sum(1 for r in rows if r["verification"]["status"] == "PENDING_REVIEW" and r["verification"]["llm_status"] == "INSUFFICIENT")},
    "claim_quality": C(r["quality"]["claim_quality"] for r in rows),
    "classification": {"final_match_status": C(r["classification"]["match_status"] for r in rows),
                       "model_none": sum(1 for r in rows if r["classification"]["classifier_status"] == "llm_none"),
                       "model_selected_then_mapper_overridden": sum(1 for r in rows if r["classification"]["mapper_override"] != "none"),
                       "model_selected_and_final_match": sum(1 for r in rows if r["classification"]["match_status"] == "matched"),
                       "unavailable_timeout": sum(1 for r in rows if r["classification"]["match_status"] == "unavailable"),
                       "mapper_override_kinds": C(r["classification"]["mapper_override"] for r in rows if r["classification"]["mapper_override"] != "none")},
    "not_scored_codes": C(r["scoring"]["not_scored_code"] for r in rows),
    "by_agent": by_agent, "per_alpha_funnel": funnel,
    "unlinked_714_diagnostic": {"counts": C(r["unlinked_diagnostic"]["category"] for r in rows if r["unlinked_diagnostic"]),
                                "by_agent_and_category": {a: C(r["unlinked_diagnostic"]["category"] for r in rows if r["unlinked_diagnostic"] and r["agent"] == a) for a in sorted({r["agent"] for r in rows})},
                                "heuristic_check_on_linked_claims": dict(check),
                                "meaning": "deterministic candidate-overlap diagnostic ONLY (numbers appearing in saved material); it is not a verification and creates no link"},
    "sources_registry": {"total": len(sources), "with_body": len(body_sources), "news_without_body": sum(1 for s in sources if s["source_type"] == "news" and not s.get("excerpt")),
                         "linked_claims_per_source": C(r["source"]["linked_source_ids"][0] for r in rows if r["source"]["linked_source_ids"])},
    "list_19_destinations": [{"claim_id": r["claim_id"], "classification": r["classification"]["match_status"], "llm_selected": r["classification"]["llm_selected_alpha_raw"], "matched_alpha": r["classification"]["matched_alpha_final"],
                              "eligibility": r["eligibility"]["code"], "quality": r["quality"]["claim_quality"], "relation": r["relation"]["relation"], "in_official_pool": r["scoring"]["in_official_pool"],
                              "weight": r["scoring"]["official_weight_contribution"], "not_scored_code": r["scoring"]["not_scored_code"]} for r in rows if r["crossref"]["in_19_analytical_supports_list"]],
    "list_24_destinations": [{"claim_id": r["claim_id"], "classification": r["classification"]["match_status"], "llm_selected": r["classification"]["llm_selected_alpha_raw"], "matched_alpha": r["classification"]["matched_alpha_final"],
                              "eligibility": r["eligibility"]["code"], "quality": r["quality"]["claim_quality"], "relation": r["relation"]["relation"], "in_official_pool": r["scoring"]["in_official_pool"],
                              "weight": r["scoring"]["official_weight_contribution"], "not_scored_code": r["scoring"]["not_scored_code"]} for r in rows if r["crossref"]["in_24_requalified_list"]],
}
(HERE / "claims_975_list.json").write_text(json.dumps({"schema_version": "amd_975_claim_acceptance_list.v1", "execution_id": DERIVED, "original_run_id": ROOT, "claims": rows}, ensure_ascii=False, indent=1))
(HERE / "claims_975_summary.json").write_text(json.dumps(summary, ensure_ascii=False, indent=1))

# -------------------------------------------------------------------- CSV (Chinese headers, filterable)
HEAD = ["claim_id", "原文", "Agent", "上下文定位", "来源ID", "真实片段ID", "数据/片段位置", "关联状态", "关联状态代码", "关联方式", "核验方法", "核验任务版本", "核验结果", "核验结果代码",
        "未被支持部分", "核验原始原因", "时间与绑定资格", "资格代码", "声明质量", "声明质量代码", "声明质量判定方法", "模型原始Alpha选择", "映射器最终结果", "分类状态", "关系", "断言状态",
        "立场（确定性）", "关系/方向判定方法", "词面匹配分（非模型相关强度）", "是否进入正式证据池", "实际权重贡献", "未计分原因", "未计分原因代码", "属于19条分析性SUPPORTS清单", "属于24条重评估清单", "未关联声明的诊断（仅为已保存数值的候选重合，不是核验，不建立关联）", "未执行或无法确认的步骤"]
with open(HERE / "claims_975_list.csv", "w", newline="", encoding="utf-8-sig") as f:
    w = csv.writer(f)
    w.writerow(HEAD)
    for r in rows:
        el, lk, vf, cl, rl, sc = r["eligibility"], r["link"], r["verification"], r["classification"], r["relation"], r["scoring"]
        tb_text = zh("time_basis", el["time_basis"]) + (f"；{el['time_basis_value']}" if el["time_basis_value"] else "") + ("" if el["review_hash_binding_ok"] is None else ("；核验哈希与来源内容一致" if el["review_hash_binding_ok"] else "；核验哈希与来源内容不一致"))
        w.writerow([
            r["claim_id"], r["claim_text"], r["agent"], f"{r['context']['agent_output_id'].split(':', 1)[1]} › {r['context']['report_section']} › 第{(r['context']['claim_index_0based'] or 0) + 1}句（原文偏移{r['context']['raw_report_char_offset']}）",
            "; ".join(r["source"]["linked_source_ids"]), "; ".join(r["source"]["fragment_ids"]), r["source"]["data_location"] or "",
            zh("source_link_status", lk["status"]), lk["status"], zh("source_link_method", lk["method"]),
            zh("content_support_method", vf["method"]), vf["task_version"] or "", zh("content_support_status", vf["status"]), vf["status"],
            vf["unsupported_part"] or "", vf["original_reason"] or "", tb_text if lk["status"] == "VALID" else "不适用（未关联来源）", el["code"] + "（" + zh("eligibility", el["code"]) + "）",
            zh("claim_quality", r["quality"]["claim_quality"]), r["quality"]["claim_quality"], r["quality"]["method"],
            cl["llm_selected_alpha_raw"] or "（模型无选择）", (cl["matched_alpha_final"] or "无") + ("；" + zh("mapper_override", cl["mapper_override"]) if cl["mapper_override"] != "none" else ""), zh("classifier_status", cl["classifier_status"]) if cl["classifier_status"] else zh("match_status", cl["match_status"]),
            zh("relation", rl["relation"]), zh("assertion_status", rl["assertion_status"]), zh("evidence_stance", rl["evidence_stance"]), rl["method"],
            "" if sc["match_score_lexical"] is None else sc["match_score_lexical"], "是" if sc["in_official_pool"] else "否", "" if sc["official_weight_contribution"] is None else sc["official_weight_contribution"],
            zh("not_scored", sc["not_scored_code"]), sc["not_scored_code"], "是" if r["crossref"]["in_19_analytical_supports_list"] else "", "是" if r["crossref"]["in_24_requalified_list"] else "",
            (r["unlinked_diagnostic"]["category"] + "：" + r["unlinked_diagnostic"]["note_zh"]) if r["unlinked_diagnostic"] else "",
            " | ".join(r["steps_not_executed_or_unconfirmable"]),
        ])

print("rows:", len(rows), "| eligibility recomputed == saved:", dict(elig_counter) == saved_counts, "| official pool == A301's 3 claims")
print("heuristic check on linked claims:", dict(check))
print("unlinked diagnostic:", summary["unlinked_714_diagnostic"]["counts"])
print("not_scored:", summary["not_scored_codes"])
print("wrote claims_975_list.json / .csv / claims_975_summary.json")
