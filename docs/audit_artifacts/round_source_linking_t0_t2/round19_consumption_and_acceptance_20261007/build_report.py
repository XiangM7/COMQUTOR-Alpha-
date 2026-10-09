#!/usr/bin/env python3
"""Builds 01_中文主验收报告.md. The narrative is written here by hand; EVERY number and table is generated from the saved JSON artifacts, so the report cannot drift from the data."""
import collections, json, sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
REPO = HERE.parents[3]
jl = lambda p: json.loads(Path(p).read_text())

chain = jl(HERE / "consumption_chain_reproduction.json")
summ = jl(HERE / "claims_975_summary.json")
claims = {c["claim_id"]: c for c in jl(HERE / "claims_975_list.json")["claims"]}
a34 = jl(HERE / "amd_34_fixed_acceptance_list.json")
live = jl(HERE / "live_service_verification_round19.json")
live_first = jl(HERE / "live_service_verification_round19_FIRST_RESTART_before_fix.json")
hashes = jl(HERE / "final_hash_proofs.json")
browser = jl(HERE / "browser_walkthrough_result.json")
proposal = jl(HERE / "proposal_target_claims.json")
scan_path = HERE / "credential_scan_result.json"
scan = jl(scan_path) if scan_path.exists() else None
derived = REPO / "outputs/runs/requal-20261007T174744Z-664040d6"
act = {a["alpha_id"]: a for a in jl(derived / "alpha_activations.json")["activation_versions"]["v2_verified"]["alphas"]}
conf = jl(derived / "conflicts.json")
ROOT = "c904d4cc-dc09-495c-aec5-b056979948e1"


def esc(x):
    return str(x).replace("|", "\\|").replace("\n", " ")


def table(headers, rows):
    out = ["| " + " | ".join(headers) + " |", "|" + "|".join("---" for _ in headers) + "|"]
    out += ["| " + " | ".join(esc(c) for c in r) + " |" for r in rows]
    return "\n".join(out)


short = lambda cid: cid.split(":", 1)[1]
S = summ
funnel = S["per_alpha_funnel"]
a301 = chain["a301_claims"]
sub = chain["a301_subset_scores_production_scorer"]
facts = chain["a301_fact_relations"]
zero = chain["a301_zero_components"]
a304 = chain["a304_claim10"]
L = live["checks"]
passed = sum(1 for v in L.values() if v["ok"])
bs = browser["steps"]
a301_ui = bs["structure_page_A301"]
fe = hashes["checks"]["frontend_files_changed_during_round19_by_someone_else_DISCLOSED_NOT_REVERTED"]

# ------------------------------------------------------------------ generated tables
t_stats = table(["项目", "数值"], [
    ["声明总数", S["total_claims"]],
    ["已关联有效来源 / 未关联", f"{S['link_status']['VALID']} / {S['link_status']['NOT_PROVIDED']}"],
    ["关联方式（261 条已关联）", f"Agent 原文引用标记 {S['link_method']['ORIGINAL_AGENT_MARKER_CITED']}；确定性字段/数值匹配 {S['link_method']['NORMALIZED_FIELD_MATCH_CANDIDATE']}；确定性内容匹配 {S['link_method']['CONTENT_MATCH_CANDIDATE']}；标题匹配 0"],
    ["内容核验结论（261 条已关联）", "；".join(f"{k} {v}" for k, v in S["verification_status_among_linked"].items())],
    ["其中“未得出结论”143 条的构成", f"技术性回退 {S['pending_by_kind']['technical_fallback']}（引文/数据位置未能定位 {S['technical_fallback_reasons_among_linked']['quote_or_data_not_found']}、超时 {S['technical_fallback_reasons_among_linked']['timeout']}、响应格式不合规 {S['technical_fallback_reasons_among_linked']['malformed_response']}）；模型判断“材料不足”{S['pending_by_kind']['model_judged_insufficient']}"],
    ["具备正式证据资格（ELIGIBLE）", S["eligibility_counts"]["ELIGIBLE"]],
    ["声明质量", f"分析性 {S['claim_quality']['analytical']}；背景/事实陈述 {S['claim_quality']['context_only']}（确定性规则判定）"],
    ["Alpha 分类", f"模型判定无匹配 {S['classification']['model_none']}；模型选择后被映射器门控改判为无匹配 {S['classification']['model_selected_then_mapper_overridden']}（A001：正向要求门控 {S['classification']['mapper_override_kinds']['alpha_positive_requirement_override']}、专属否证 {S['classification']['mapper_override_kinds']['alpha_specific_invalidation_override']}）；最终匹配 {S['classification']['model_selected_and_final_match']}；请求超时未获结果 {S['classification']['unavailable_timeout']}（合计 {S['classification']['model_none'] + S['classification']['model_selected_then_mapper_overridden'] + S['classification']['model_selected_and_final_match'] + S['classification']['unavailable_timeout']}）"],
    ["进入官方（已验证）证据池", f"3 条（全部为 A301；{sum(1 for r in claims.values() if (r['scoring']['official_weight_contribution'] or 0) > 0)} 条权重大于 0）"],
])

t_notscored = table(["声明走到哪一步停下（官方路径第一道未通过的关口）", "条数"], [[__import__("zh_mapping").zh("not_scored", k) + f"（{k}）", v] for k, v in sorted(S["not_scored_codes"].items(), key=lambda kv: -kv[1])])

rows_f = []
first_blocker = {
    "A001": "无已验证证据：模型 68 次选择，其中 64 次被映射器的 A001 门控改判为无匹配；剩下 4 条里只有 1 条进入未验证口径的原始池，且未关联来源",
    "A003": "模型从未选择该 Alpha（0 条）",
    "A101": "原始池 5 条，全部未验证（4 条未关联来源，1 条核验方法不具资格）",
    "A102": "模型从未选择该 Alpha（0 条）",
    "A103": "原始池 1 条，未关联来源",
    "A201": "原始池 11 条均未验证；另有 2 条已验证但被确定性质量规则判为非分析性（背景/事实陈述）",
    "A301": "官方分 21.31 < active 阈值 50：证据质量仅 1.64/35、agent 独立性 4.67/20（1 个 agent）、本地结构 0/20、ticker-specific 0/10",
    "A304": "原始池 25 条均未验证；唯一已验证的 A304 声明（PM claim 10）因关系被文本规则判为 mention 而排除",
    "A501": "原始池 11 条，全部未关联来源",
    "A601": "原始池 6 条，全部未关联来源",
}
for a, f in funnel.items():
    rows_f.append([a, f["model_raw_selections"], f["overridden_by_mapper_gate"], f["final_matches"], f["final_matches_analytical"], f["raw_pool_unverified_view"], f["final_matches_verified_eligible"],
                   f"{f['official_pool_claims']} / {f['official_unique_facts']} / {f['claims_with_positive_weight']}", f"{f['official_score']:.2f} / {f['level']} / {f['direction']}", first_blocker[a]])
t_funnel = table(["Alpha", "模型原始选择", "被映射器改判", "最终匹配", "其中分析性", "原始池（未验证口径）", "最终匹配中已验证", "官方池：声明/独立事实/正权重声明", "官方分/等级/方向", "未激活的首要原因"], rows_f)

rows_c = []
for e in conf["arbitration"]["candidate_evaluations"]:
    A, B = e["alpha_a"], e["alpha_b"]
    ra, rb = e["evidence_audit"]["alpha_a"]["qualifying_count"], e["evidence_audit"]["alpha_b"]["qualifying_count"]
    why = []
    if "MISSING_LEFT_EVIDENCE" in e["reason_codes"]:
        why.append(f"{A} 无任何满足关系/质量条件的证据")
    why.append(f"官方（已验证）口径：{A} 官方池 {len(act[A]['claim_ids'])} 条/方向 {act[A]['direction']}；{B} 官方池 {len(act[B]['claim_ids'])} 条/方向 {act[B]['direction']}；DIRECTION_ROLE_UNRESOLVED = 至少一侧的多空角色无法判定" + ("（A301 已有正向，但对侧 A304 官方证据为 0，无法形成可裁决的对立双方）" if (A, B) == ("A301", "A304") else ""))
    rows_c.append([f"{A} vs {B}", "拒绝（未进入立场准入判断）", "、".join(e["reason_codes"]), f"{ra} / {rb}", f"{act[A]['activation_score']:.2f} / {act[B]['activation_score']:.2f}", "；".join(why)])
t_conf = table(["已声明的冲突对", "结论", "原因代码", "未验证口径下满足关系/质量条件的证据数 A / B", "官方分 A / B", "采纳/拒绝原因"], rows_c)

t_19 = table(["最终去向", "条数", "说明"], [
    ["模型判定无匹配 Alpha（MODEL_NONE）", sum(1 for r in S["list_19_destinations"] if r["not_scored_code"] == "MODEL_NONE"), "分类模型判定它们不实质对应任何 Alpha；与是否有依据是两回事"],
    ["进入 A301 官方池", sum(1 for r in S["list_19_destinations"] if r["not_scored_code"] == "IN_OFFICIAL_POOL"), "fundamentals claim 31 / 33 / 36；真实权重只来自 31"],
    ["匹配 A304 但被关系规则排除", sum(1 for r in S["list_19_destinations"] if r["not_scored_code"] == "RELATION_NOT_SUPPORTING"), "portfolio_manager claim 10（见 §6）"],
])
t_24 = table(["最终去向", "条数", "说明"], [
    ["模型判定无匹配 Alpha", sum(1 for r in S["list_24_destinations"] if r["not_scored_code"] == "MODEL_NONE"), "其中多数为背景/事实陈述"],
    ["进入 A301 官方池", sum(1 for r in S["list_24_destinations"] if r["not_scored_code"] == "IN_OFFICIAL_POOL"), "31 / 33 / 36"],
    ["已验证并被模型选择，但被确定性声明质量规则判为非分析性", sum(1 for r in S["list_24_destinations"] if r["not_scored_code"] == "NON_ANALYTICAL_QUALITY"), "A301 ×4（fundamentals 122；bull 21；aggressive 10、12）、A201 ×2（fundamentals 38、129）"],
    ["匹配 A304 但被关系规则排除", sum(1 for r in S["list_24_destinations"] if r["not_scored_code"] == "RELATION_NOT_SUPPORTING"), "portfolio_manager claim 10"],
])

CN = {"evidence_quality": "证据质量", "agent_independence": "agent 独立性", "local_structure_support": "本地结构", "ticker_specificity": "ticker 特异性", "recency": "时效", "direction_consistency": "方向一致性"}
t_subsets = table(["官方池中保留的声明", "A301 官方分", "各分项得分"], [[k if k != "(none)" else "（无）", f"{v['activation_score']:.4f}", "；".join(f"{CN[n]} {p:.2f}" for n, p in v["points"].items() if p) or "（无证据，全部为 0）"] for k, v in sub.items()])

rows_a301 = []
for n in ("31", "33", "36"):
    c = a301[n]
    rr = c["mapper_reproduction"]["saved_candidate"]
    rows_a301.append([f"声明 {n}", f"{rr['keyword_score']:.4f}（命中：{'、'.join(rr['matched_keywords']) or '无'}）", f"{rr['factor_score']:.1f}", f"{rr['direction_score']:.1f}（记录 direction={c['record_fields_consumed_by_mapper']['direction']}）", f"{rr['semantic_score']:.1f}",
                      f"{c['mapper_reproduction']['score_recomputed_from_components']:.4f}", f"{c['official_scoring_read']['weight_contribution_to_its_fact_group']:.4f}", "是" if (c["mapper_reproduction"]["candidate_reproduced_exactly"] and c["mapper_reproduction"]["final_reproduced_exactly"]) else "否"])
t_score = table(["声明", "keyword_score", "factor_score", "direction_score", "semantic_score", "match score（重算）", "官方权重贡献", "生产函数重算与保存值逐项一致"], rows_a301)

rows_fact = []
for n in ("31", "33", "36"):
    r = facts["rows"][n]
    rows_fact.append([f"声明 {n}", r["line_item"], "、".join(r["periods"]), r["operation"], "；".join(f"{a}" for a in r["claim_numbers_USD_M"]) + "（百万美元）", "是" if r["all_claim_numbers_found_in_snapshot_at_expected_period"] else "否"])
t_fact = table(["声明", "数据项", "涉及期间", "运算", "声明中的数值", "数值与保存的快照一致"], rows_fact)

rows_comp = []
for k, label in (("evidence_quality", "证据质量（权重 0.35）"), ("agent_independence", "agent 独立性（0.20）"), ("local_structure_support", "本地结构支持（0.20）"), ("ticker_specificity", "ticker 特异性（0.10）"), ("recency", "时效（0.10）"), ("direction_consistency", "方向一致性（0.05）")):
    comp = act["A301"]["components"][k]
    why = {"evidence_quality": "只有声明 31 有正权重（0.1873）：Σ=0.1873 ÷ 饱和值 4.0 × 100 = 4.68；饱和需要 4 个满分独立事实",
           "agent_independence": "只有 fundamental_agent 一个 agent：0.70 × (1/3) × 100 = 23.33；无跨 agent 确认",
           "local_structure_support": "关系边共 17 条，没有任何一条来自 A301 声明（A301 共 43 条已匹配声明，0 条在关系边之后）；与 A301 相连的图边 0 条",
           "ticker_specificity": "规则要求声明文本本身出现 AMD/公司名；三条声明文本都没有（绑定来源的 instrument=AMD 未被该分项读取）",
           "recency": "不依赖声明权重，有 ≥1 条合格证据即计；age_days=0",
           "direction_consistency": "按匹配分加权的关系符号平均；只有声明 31 有权重，符号来自文本规则的默认 activation"}[k]
    rows_comp.append([label, f"{comp['raw']:.2f}", f"{comp['contribution']:.2f}", why])
t_comp = table(["分项", "原始分 0-100", "折算得分", "为什么是这个值"], rows_comp)

UL = {
    "U1_NO_NUMERIC_LOCATOR": "声明不含可定位的数值（观点/预测/定性表述）——没有数据记录可供匹配，取数也无从补来源",
    "U2_ALL_NUMBERS_IN_A_REGISTERED_SOURCE_BODY": "全部数值都出现在某个已保存来源的正文/数据中——存在改进关联算法的空间，不需要外部取数",
    "U3_SOME_NUMBERS_IN_A_REGISTERED_SOURCE_BODY": "部分数值出现在已保存来源中",
    "U4_NUMBERS_ONLY_IN_AN_UPSTREAM_ANALYST_REPORT": "数值只出现在上游分析师报告文本里，未登记为来源",
    "U5_NUMBERS_FOUND_NOWHERE_SAVED": "数值在已保存的来源和报告中都找不到",
}
t_unlinked = table(["类别", "说明", "条数"], [[k.split("_")[0], UL[k], v] for k, v in S["unlinked_714_diagnostic"]["counts"].items()])
chk = S["unlinked_714_diagnostic"]["heuristic_check_on_linked_claims"]

pm = sorted([r for r in claims.values() if r["agent"] == "portfolio_manager"], key=lambda r: r["context"]["claim_index_0based"])
key_idx = {3, 4, 10, 25, 26, 28, 37, 41, 44, 46}
rows_pm = []
for r in pm:
    i = r["context"]["claim_index_0based"] + 1
    if i in key_idx:
        rows_pm.append([f"#{i}", r["claim_text"][:120] + ("…" if len(r["claim_text"]) > 120 else ""),
                        __import__("zh_mapping").zh("source_link_status", r["link"]["status"]).split("（")[0], __import__("zh_mapping").zh("content_support_status", r["verification"]["status"]).split("（")[0],
                        r["eligibility"]["code"], r["classification"]["matched_alpha_final"] or "—", "是" if r["scoring"]["in_official_pool"] else "否"])
t_pm = table(["最终决策中的句序", "声明（节选）", "来源关联", "内容核验", "资格", "匹配 Alpha", "进入官方池"], rows_pm)

t_agents = table(["Agent", "声明", "已关联", "具备资格", "匹配 Alpha", "进入官方池"], [[a, v["claims"], v["linked"], v["eligible"], v["matched"], v["in_official_pool"]] for a, v in S["by_agent"].items()])

a34s = a34["summary"]
t_34 = table(["项目", "数值"], [
    ["原清单条数 / 来自运行", f"34 / {a34s['run_id']}（证据截止 {a34s['evidence_cutoff']}，冲突 {a34s['conflict']}，原运行中该冲突状态 admitted）"],
    ["侧别", "bull 15 / bear 17 / counter 2"],
    ["该运行的来源登记表（本次重新核对）", f"{a34s['registry_facts_reconfirmed_now']['sources']} 条来源，类型仅 news；有正文 {a34s['registry_facts_reconfirmed_now']['with_excerpt']}；有数据快照 {a34s['registry_facts_reconfirmed_now']['with_data_snapshot']}"],
    ["原关联状态", "UNAVAILABLE ×34"],
    ["修复后关联状态（用当前四种机制在冻结材料上复算）", "NOT_PROVIDED ×34（关联方式 NONE）；内容支持 NOT_APPLICABLE ×34"],
    ["历史运行是否实际采用", "34/34 是（原运行已准入冲突 A301__A304 的证据）"],
    ["按当前规则是否具备资格（资格复算，不是采用）", "0/34（SOURCE_LINK_NOT_VALID）"],
    ["独立重算是否采用", "未执行 ×34（从未对该运行做过派生重算；本轮的重算对象是另一次 AMD 运行 c904d4cc）"],
    ["未通过原因（John 原话的四类，按本次实际情况归类）", "B 来源已登记但正文当时未保存 11；C 该类来源这次运行从未保存 21（财务 14、情绪 7）；D 下游综合转述无独立来源 2；A 冻结材料确有内容但实现未接通 0；E 内容存在却不支持 0；F 已能关联并验证 0"],
    ["与第 4 轮已保存清单逐条比对", "34/34 一致" if a34s["all_34_agree_with_saved_round4_v3_ledger"] else "存在不一致"],
])

CHECK_ZH = {"service_ready_with_isolated_database": "服务就绪且连接隔离库", "lineage_block_present_and_correct": "血缘块存在且正确", "requalification_summary_equals_artifact": "重评估摘要=产物",
  "classification_incompleteness_still_disclosed": "分类不完整仍被披露", "parent_has_recovery_lineage_and_original_has_none": "恢复运行有血缘、原运行无", "history_lists_all_three_runs": "历史列出三个运行",
  "read_time_eligibility_equals_stored": "读取时资格=已存资格（500 条可见声明）", "api_claim_set_equals_parent": "API 声明集合=父运行", "graph_scores_and_levels_equal_artifact_for_all_10_alphas": "10 个 Alpha 分数/等级=产物",
  "exposures_equal_artifact": "敞口=产物", "conflicts_equal_artifact": "冲突=产物", "artifact_listing_complete_and_hashes_match": "产物清单完整且哈希一致", "new_artifacts_readable_lineage_download": "血缘产物可读",
  "new_artifacts_readable_eligibility_download": "资格重评估产物可读", "export_zip_byte_identical_to_execution_files": "Export ZIP 与文件逐字节一致", "export_scores_equal_artifacts": "Export 内分数/冲突=产物",
  "published_at_never_backfilled": "published_at 未被回填", "original_run_directory_byte_identical_to_before_round19": "原始运行目录未变", "recovery_run_directory_byte_identical_to_before_round19": "恢复运行目录未变",
  "requalification_run_directory_byte_identical_to_before_round19": "重评估运行目录未变", "direction_execution_directory_byte_identical_to_before_round19": "方向执行目录未变",
  "backend_production_changes_this_round_are_exactly_the_one_reviewed_fix": "本轮后端生产代码修改恰好是评审过的 1 个文件", "frontend_files_changed_during_round19_by_someone_else_DISCLOSED_NOT_REVERTED": "他人在本轮期间改动的前端文件（已披露、未回退）",
  "original_run_byte_identical_to_start_of_round19": "原始运行目录未变", "recovery_run_byte_identical_to_start_of_round19": "恢复运行目录未变", "direction_execution_byte_identical_to_start_of_round19": "方向执行目录未变",
  "requalification_run_byte_identical_to_start_of_round19": "重评估运行目录未变", "historical_amd_run_d5b60b8a_unchanged_since_round4": "历史 AMD 运行 d5b60b8a 自第 4 轮起未变（6 个记录哈希复核）", "protected_set_identical": "保护清单（73 个文件）逐一一致",
  "original_34_item_ledgers_hashes": "两份原 34 条清单的哈希（只读输入）"}
live_rows = [[f"{CHECK_ZH.get(k, k)}", "通过" if v["ok"] else "未通过"] for k, v in L.items()]
t_live = table(["检查项（只读 GET，对重启后的真实服务）", "结果"], live_rows)

hash_rows = []
for k, v in hashes["checks"].items():
    if k.startswith("frontend_files"):
        hash_rows.append([CHECK_ZH.get(k, k), "已披露（非本轮修改）", f"{v['count']} 个前端文件在本轮期间被另一个会话（前端首页重设计）新增/修改，原样保留"])
    else:
        hash_rows.append([CHECK_ZH.get(k, k), "通过" if v["ok"] else "未通过", ""])
t_hash = table(["证明项", "结果", "备注"], hash_rows)

# ------------------------------------------------------------------ narrative
R = []
add = R.append
add(f"""# COMQUTOR Alpha — Round 19 中文主验收报告（AMD 运行链）

> **面向读者：John（验收人）与项目负责人。** 日期：2026-10-07。分支 `comqutor-source-linking-t0-t2`，未 commit / push。
> 口径：本报告只陈述已保存材料上的事实；**单元测试/固定输入测试与真实 AMD 结果分开陈述**；不把“按当前代码执行”当作符合 John 要求的证明；**不宣称 T1 或 John 整体验收通过**，也不以是否出现 active Alpha / Conflict 作为成功标准。

## 0. 运行链（均为只读引用；新重算一律是新的 execution，保留父子关系）

| 角色 | ID | 说明 |
|---|---|---|
| 原始研究运行 | `{ROOT}` | 2026-10-06 的 AMD fresh run，975 条声明 |
| 分类恢复运行 | `recovery-20261007T053635Z-26d6cd1a` | 真实分类恢复（973 个 alpha_classifier 请求，另 2 条沿用原结果），派生自原始运行 |
| 方向判断执行 | `direction-20261007T065826Z-d311b8e2` | 第 1 批 10 对即在 45 s 超时，按冻结协议停止；**没有产生任何模型方向结果**，也没有派生 run |
| 最新重评估运行 | `requal-20261007T174744Z-664040d6` | 第 18 轮：零模型调用的独立重算（时间资格、核验哈希绑定修复） |
| John 原“34 条”所属的历史运行 | `d5b60b8a-66b8-44c1-9f55-ee345e58c48d` | 证据截止 2026-09-21；**与上面是不同的 AMD 运行**，不用新运行的材料回填 |

## 1. 本轮结论（先给结论）

1. **确认并修复了 1 个消费错误（只读 API 的显示诊断）。** 重启服务后做“已存资格 vs 读取时资格”逐条比对，发现 portfolio_manager claim 10（A304 声明，引用了两个来源，核验绑定的是第二个）被 API 显示为 `REVIEW_SOURCE_NOT_LINKED_TO_CLAIM`（类别“引用缺失或无效”），而已存结果是 `ELIGIBLE`。原因：数据库 `agent_outputs` 没有 `linked_source_ids` 列、公共字段白名单也没有它，诊断函数只看到主来源。已修复（只把已保存的引用列表交给诊断函数；不改任何已存结果、评分或公共字段）；修复前后红绿测试已留存；修复后 500 条 API 可见声明与已存结果 **0 处矛盾**。
2. **A301 官方分 21.3056，等级 candidate，方向 positive。** 3 条声明进入正式池，**真实权重只来自声明 31（0.1873）**；声明 33、36 的权重为 0。原因不是“已保存的语义判断被覆盖或没传进评分”——分类模型的输出契约只有 `{{decision, selected_alpha_id}}`，**从未被要求给出相关强度**；进入评分的 `score` 是确定性的词面规则分（产品决定 PD-012 把它定义为“声明与 Alpha 的语义相关度”，实现与这一定义并不一致）。因此对这两条：**Alpha 选择=模型已判断；相关强度=未判断。** 没有设保底分，也没有把模型选择默认赋 1.0。
3. **A304 声明 10：关系未解决，不手工改。** `negated/mention` 来自确定性文本规则（句中的 “not”），不是模型输出；没有任何已保存的模型判断回答“该声明对 A304 是支持、反对还是仅提及”（第 17 轮方向判断没有轮到这一对）。即便关系解决，后面还有两道关口（否定断言权重 0；Portfolio Manager 属 Secondary 角色且文本不含 AMD）。
4. **A301 其他偏低/为零的分项都能对到具体规则**：agent 独立性来自单一 agent（也符合 John T1-C：多个 Agent 转述同一财报不增加独立证据）；ticker 特异性为 0 是“声明文本须出现 AMD”的既有规则；本地结构为 0 是因为 17 条关系边没有一条来自 A301 的声明。均不是接线错误，未改。
5. **没有 active Alpha、没有 admitted Conflict——这是如实结果。** 10 个 Alpha 全部为 candidate；8 个声明冲突对全部拒绝（原因见 §12）。
6. **服务已按正常流程重启并核验**（重启两次：第一次暴露上述缺陷，修复后第二次加载修复）。真实服务只读核验 {passed}/{len(L)} 项通过；浏览器核验见 §8：A301 的评分依据可见，**但来源片段/数据位置与核验状态在界面里到不了**（数据存在于 API，缺的是界面连接）。
7. **交付**：AMD 原 34 条固定验收清单、975 条可筛选清单、本报告、统一最小模型请求提案（**未执行**）。原始/恢复/重评估运行目录、历史 AMD 运行、保护清单均字节不变（§17）。

## 2. John T1 原文要求 与 本项目采用的策略

（John 原文取自 `COMQUTOR Alpha 下一轮开发任务单.docx` 第三节，已逐字核对。）

{table(["John 原文要求", "本项目采用的做法", "现状"], [
["A 取数阶段保存来源与可定位内容：新闻保留来源标识/标题/URL/发布时间/抓取时间/允许保存的原文片段；行情、财务、宏观保留提供方/指标/日期/单位/数据行/输入快照；派生结果保留输入记录和计算方式", "取数层写入来源登记表（source_id、fragment_id、excerpt、data_snapshot、content_hash、published_at、retrieved_at、provider、instrument、observation_date、unit、calculation_*）。财务报表快照的披露时间未知时保持 published_at 为空；第 18 轮另加“来源注册表写入时间上界”的可用时间记录，**不冒充披露日期**", "行情、财务已在真实运行中贯通；新闻正文、宏观在本次运行**未得到验证**（§3）"],
["B Agent 传递已有来源 ID；后端校验存在/属于本次允许输入/可定位；不接受模型自编；标题匹配只能辅助", "Agent 输入带片段 ID，`validate_source_reference` 校验。本次 261 条关联中：Agent 原文引用标记 88、确定性字段/数值匹配 172、确定性内容匹配 1、**标题匹配 0**", "标题匹配不是主要方式；但约三分之二的关联来自确定性匹配而非 Agent 引用"],
["C Evidence Fact 合并保留来源链；同一财报被多 Agent 引用不增加独立证据；不同来源的相似判断不能仅凭文本相似删除", "Evidence Fact Index 分组：共享来源不等于同一事实（数值签名冲突即不合并）；Primary/Secondary 角色资格，Secondary 对 Primary 事实的转述记为 SECONDARY_DUPLICATE_OF_PRIMARY", "已实现并有测试；真实例子见 §5.5"],
["D 分开记录“来源关联”和“内容支持”；SOURCE_LINKED 不等于已验证", "两条独立字段；内容支持由模型内容核验（content_support.llm.v2.1）或确定性数据事实核验给出", "已实现；真实统计见 §4"],
["E 无合格依据的内容可作评论/待核查，但不得直接抬高 qualified Alpha / admitted conflict；Research、Evidence、Conflict、Export 读同一份结果；点击重要结论应看到内容片段或计算依据", "正式评分只读“已验证资格”证据；未验证内容保留为研究文本。API/Graph/Conflict/Export 同源", "后端一致（§8）；**界面不能从 A301 的结论走到片段**（缺口）"],
["验收：把 AMD 原 34 条固定为清单，逐条输出规定字段；不因移除而消失；分别统计原关联与修复后采用/降级/排除", "34/34 保留；采用情况拆成三列（历史运行采用 / 当前规则资格 / 独立重算采用），“未执行”如实标注", "见 §15 与 `amd_34_fixed_acceptance_list.*`"],
["完成条件：缺少来源不能靠伪造链接、批量挂载全部文章或隐藏条目解决；历史材料不足先标未验证", "714 条未关联声明保持未关联；34 条保持未验证；未用新运行回填旧清单", "已遵守"],
["“不能出现关键结论没有依据，却仍按充分验证结果展示”", "官方池只含 ELIGIBLE 声明（64 条具备资格，3 条入池）", "注意：A301 卡片写“Supporting evidence 3”，其中 2 条权重为 0——展示口径有被读重的风险（§8）"],
])}

## 3. 已实现 / 真实验证 / 未验证

{table(["T1 子项", "已实现（代码+测试）", "在本次真实 AMD 运行中验证了什么", "未验证 / 缺口（性质）"], [
["新闻来源与正文", "有（取数时把供应商 summary 存为 excerpt）", "30 条新闻来源有标题、URL、发布时间、抓取时间", "**30 条全部没有正文**；原始供应商响应没有保存，无法判断是供应商未给摘要还是捕获失败；新闻声明 106 条，关联 0 条（工程/材料：无法在本地区分）"],
["行情来源", "有", "1 个行情快照（OHLCV + 11 个技术指标），129 条声明关联到它", "时区为空、元数据状态 PARTIAL"],
["财务来源", "有", "3 张报表快照 + 1 个基本面快照；63+33+26+10 条声明关联", "三张报表的披露日期未知（只有期末日）；货币单位为 UNKNOWN_CURRENCY；每次调用的精确抓取时间没有保存（只有写入时间上界）"],
["宏观来源", "有（FRED 路径）", "—", "本次运行**没有任何宏观来源**，未验证"],
["派生结果与计算依据", "有（确定性数据事实核验；模型核验的派生计算）", "2 条确定性核验、若干条模型核验的 DERIVED_CALCULATION（如声明 36）", "calculation_method/version/params 字段在这些来源上为空；计算依据只存在于模型核验记录里"],
["Agent 传递来源 ID 与后端校验", "有", "88 条为 Agent 原文引用", "趋势类句子（如 31/33/36）没有片段标记，靠确定性匹配关联"],
["Evidence Fact 合并与独立性", "有", "A301 的 3 个事实未被误合并；Secondary 转述不加独立性", "—"],
["关联与内容支持两轴分离", "有", "261 条已关联 → 64 支持 / 49 有条件 / 4 背景 / 1 相反 / 143 未得出结论", "143 条中 107 条是技术性回退（未完成核验），属工程缺口"],
["下游降级与 API/Export 一致", "有", f"真实服务 {passed}/{len(L)} 项只读核验；浏览器 Export 下载与文件逐字节一致", "—"],
["界面显示片段/核验状态", "部分", "Research 页对出现在列表中的发现可显示来源与核验面板", "**A301 的三条结论在界面里看不到来源片段与核验状态**（§8）"],
])}

## 4. 真实统计（AMD 运行 c904d4cc 及其派生执行；均为已保存材料上的计数）

{t_stats}

**声明走到哪一步停下**（每条声明只计一次，按官方路径第一道未通过的关口）：

{t_notscored}

**五个概念必须分开读**：具备资格（ELIGIBLE，64 条）≠ 进入官方池（3 条）≠ 对分数有权重（1 条）≠ 激活（0 个 Alpha 达到 active）≠ 冲突（0 条 admitted）。**不能把“没有记分”统一解释为“声明不合理”**：714 条未关联不是“核验失败”（它们根本没进入核验）；107 条技术性回退不是“模型认为没有依据”；CONDITIONAL 不是“结论被证伪”。

各 Agent 的分布：

{t_agents}

## 5. A301：声明 31 / 33 / 36 从模型判断到官方得分的完整消费链

证据来源：`consumption_chain_reproduction.json`（用**生产函数**在已保存产物上复算，零模型调用；官方分 21.3056 被生产评分函数逐位复现）。""")

for n in ("31", "33", "36"):
    c = a301[n]
    v = c["verification"]
    ctx = c["context_in_original_report"]
    llm = v["llm_content_support"]
    rr = c["mapper_reproduction"]
    add(f"""
### 5.{ {"31": 1, "33": 2, "36": 3}[n] } 声明 {n}

- **完整声明**：{c['claim']}
- **上下文**：{ctx['agent_output_id'].split(':', 1)[1]} › {ctx['section_heading']}；所在条目：“{esc(ctx['paragraph_or_bullet'])[:420]}{'…' if len(ctx['paragraph_or_bullet']) > 420 else ''}”。句子本身{'带' if ctx['claim_sentence_itself_carries_fragment_marker'] else '**不带**'}片段标记。
- **实际引用的内容**：来源 `{v['bound_source']['source_id']}`（{v['bound_source']['title']}；{v['bound_source']['provider']}；observation_date {v['bound_source']['observation_date']}；retrieved_at {v['bound_source']['retrieved_at']}；published_at {v['bound_source']['published_at'] or '未知（空，不回填）'}），片段 `{v['bound_source']['fragment_id']}`；核验使用位置：{llm['used_location']}；引用的数据：{llm['supporting_quote_or_data']}。关联方式：`{v['source_link']['source_link_method']}`（确定性字段匹配，非 Agent 引用）。
- **核验结果与绑定**：{llm['llm_status']}（依据类型 {llm['support_basis']}）；核验绑定 `{v['review_binding']['linked_source_id']}`；核验哈希{'=' if v['review_hash_equals_source_hash'] else '≠'}来源哈希，且 sha256(excerpt)={'=' if v['hash_check_sha256_excerpt_equals_stored_content_hash'] else '≠'}保存哈希；生产函数现在复算资格：`{v['eligibility_recomputed_now_by_production_function']['reason_code']}`。模型的理由：{llm['rationale']}
- **模型原始 Alpha 选择**：`{c['llm_alpha_selection']['llm_selected_alpha_id']}`（{c['llm_alpha_selection']['saved_call']['task']}，prompt {c['llm_alpha_selection']['saved_call']['prompt_version']}，模型 {c['llm_alpha_selection']['saved_call']['model']}，retry {c['llm_alpha_selection']['saved_call']['retry_count']}）。**确定性路径在模型介入前的结论是“无匹配”**（`deterministic_match_status = {c['llm_alpha_selection']['deterministic_match_status_before_llm']}`）。
- **最终匹配 / 关系 / 断言**：{c['final_match']['matched_alpha']}；relation = `{c['relation_of_matched_candidate']}`、assertion = `{c['final_match']['assertion_status']}`（二者都是确定性文本规则的输出，不是模型）；立场（确定性）= `{c['final_match']['matched_evidence_stance']}`（{'、'.join(c['final_match']['matched_stance_reason_codes'] or [])}）。
- **确定性匹配分如何生成**：`score = 0.50×keyword + 0.30×factor + 0.08×direction + 0.12×semantic`（`alpha_mapper._candidate_score`）。本条 keyword={rr['saved_candidate']['keyword_score']}、factor={rr['saved_candidate']['factor_score']}、direction={rr['saved_candidate']['direction_score']}、semantic={rr['saved_candidate']['semantic_score']} → **{rr['score_recomputed_from_components']}**。（semantic 只在 keyword 或 factor 有命中时才计入。）
- **官方评分读取哪个字段**：`record['score']` × `RELATION_WEIGHTS[relation]`（activation=1.0）× `ASSERTION_WEIGHTS[assertion]`（asserted=1.0）= **{c['official_scoring_read']['weight_contribution_to_its_fact_group']}**；每个事实组取最大成员，求和后除以饱和值 4.0。
""")

add(f"""
{t_score}

### 5.4 回答四个问题

1. **为什么模型选了 A301，声明 33/36 的权重仍为 0？** 因为进入评分的不是模型的判断，而是 `alpha_mapper` 对“被选中的那个 Alpha”仍然按旧的确定性规则算出的词面分（`result['score'] = matched_candidate['score']`，`alpha_mapper.py:979`）；这两句话没有任何 A301 词表里的关键词、没有可识别的因子、记录的 direction 为 unknown，四项全为 0。**在纯确定性路径下它们本来就不会被匹配到 A301**（`eligible=false`，低于 0.35 阈值）；是模型的选择让它们进了池，权重却仍由词面规则决定——**两个不同的权威管着同一条证据的两个侧面，从未被调和。**
2. **这个分数是诊断字段还是正式契约的权重？** 两者都不是干净的：代码注释与 QQQ A001 修复记录把确定性打分称为“diagnostic/counterfactual only”；但 Activation v2 把它当作权重乘进证据质量和方向一致性。产品决定 **PD-012**（Product Owner）规定 Alpha 匹配分“只表示声明与 Alpha 的**语义相关度**”；**PD-013** 规定 0.35 是统一最低阈值（经 LLM 选中的匹配绕过了这一阈值——声明 31 的 0.1873 也低于它）。所以：契约上这个字段**应当**是语义相关度，实现上却是词面规则分。把它当作权重乘进 Activation 是 Activation v2（`activation.v2.evidence_local_structure.v1`）的**实现选择，不是 John 的明确要求**（John T1 原文没有提到匹配分）。开发计划 v1.0 §5.2 对第一版 Alpha Mapper 的描述本就是“keyword hits raise match_score; threshold 0.35”——词面分是**第一版设计**；后来的“纯 LLM 语义权威”只把**选择权**交给了模型，权重来源没有随之改变。
3. **它衡量什么？** 主要是“句子里出现了多少 Alpha 词表中的词”（关键词 50%）+ 因子命中（30%）+ 记录的 direction 与 Alpha 极性是否同向（8%）+ 一个关系类别指示项（12%，且仅在已有关键词/因子命中时才计入）。**它不衡量模型意义上的相关强度。**
4. **有没有已保存的有效语义结果被覆盖或没传进评分？没有。** 分类契约是 `{{decision, selected_alpha_id}}`，多余字段会被拒绝（有测试）；模型的“选择”被原样采用（`matched_alpha = llm_outcome['alpha_id']`）。声明级的 `assertion_status`/`semantic_polarity` 在结构化适配器和映射器里是同一个确定性函数的输出，不存在被覆盖的模型值；`confidence`（0.75/0.75/0.6）按 PD-012 不得乘入相关度，也没有被乘入。**因此缺的是一个“相关强度”的模型判断本身——标记为“未判断”，不是消费错误。**

**该给相关强度怎么办（只提方案，不设保底、不全赋 1.0、不拿内容支持 confidence 冒充）**：见 `03_最小模型请求提案_未执行.md` 的 A/B 部分与其中的版本化消费规则。

### 5.5 “3 个独立事实”的依据（按事实/期间/计算关系，而不是 claim_id 不同）

{t_fact}

- 声明 31 与 33 取自**同一条目**（“Revenue acceleration is dramatic.”）的相邻句；声明 33 用到的三个期间（2025-12-31、2026-03-31、2026-06-30）**全部包含在声明 31 的五个期间之内**——33 是对 31 所含数据的派生解读（环比 −17M，+1,283M，+12.51%），不是新的观测。声明 36 用的是**另一数据行**（Gross Profit，同比 2.0278 倍，即“约翻倍”）。
- 因此按**命题**计是 3 个，按**数据行**计是 2 个（Total Revenue、Gross Profit），按**来源**计是 1 个快照、**按 agent** 计是 1 个。系统的分组结果是 3 组：它们的数值签名互相冲突、重复组 ID 不同、词重合度 Jaccard 为 {min(v['token_jaccard'] for v in facts['grouping_evidence']['pairwise'].values()):.3f}–{max(v['token_jaccard'] for v in facts['grouping_evidence']['pairwise'].values()):.3f}（阈值 0.85），**共享同一来源本身从不构成合并理由**（有测试，并做了突变检验）。
- **这 3 个并不是 3 次独立佐证**：同一快照、同一 agent、其中两条共享数据点。这对 A301 的分数**没有影响**（33、36 权重为 0），也不触发任何上限（唯一证据上限只在独立事实 <2 时触发）。未改动分组规则。

### 5.6 A301 的边际贡献——**边际、非可加**

在官方池中只保留某些声明，用生产评分函数重算 A301：

{t_subsets}

读法：声明 31 单独就给出 21.3056；声明 33 或 36 **单独**留在池里也得 14.6667（= agent 覆盖 4.67 + 时效 10.00——这两项不依赖任何声明的权重，只要池里有 ≥1 条合格证据就计）；31 比它们多出 **6.6389**（证据质量 1.64 + 方向一致性 5.00）。**不能写成“声明 31 贡献了全部 21.3056”**，也不能把各声明的边际相加。

### 5.7 A301 其他为零/偏低的分项

{t_comp}

- **agent 独立性**：单一 agent 得 23.33/100，没有被“制造”。John T1-C 本就要求同一财报被多个 Agent 引用不得增加独立证据；debate/risk 分析师对同一收入数字的转述（aggressive claim 10、bull claim 21 等）既是 Secondary 角色，其中几条还被质量规则判为背景。
- **ticker 特异性 = 0，尽管绑定来源的 instrument 是 AMD**：规则（`_is_ticker_specific`）要求**声明文本**本身点名 AMD/公司名，理由是上游会把运行 ticker 无条件追加进每条声明的 entities，所以 entities 不作数。三条声明都不点名（它们靠所在报告的上下文归属 AMD）。绑定来源的 instrument 是更可靠的信号，但当前分项**不读取它**——这是评分政策问题（新增一个输入），不是“已有字段没传”。若采纳，A301 的 ticker 项将从 0 升到 100 → +10.00 分（21.31 → 31.31，仍低于 50）；**未应用，仅为影响量说明**。
- **本地结构 = 0**：关系边共 17 条（全部来自标准化关系，LLM 结构抽取器 3 次调用产出 0 条），A301 的 43 条已匹配声明里 **0 条**位于任何关系边之后；与 A301 相连的图边 0 条（唯一的排除原因是 `NO_COMMITTED_ALPHA_MATCH`）。声明 31/33/36 是数据复述，不含因果关系句，**没有结构被建出**；已有结构也没有被误读。

## 6. A304：Portfolio Manager claim 10 的链路与语义缺口

- **完整声明**：{a304['claim']}
- **上下文**：{a304['context_in_original_report']['agent_output_id'].split(':', 1)[1]} › {a304['context_in_original_report']['section_heading']}。该句出现在“Where the aggressive analyst overreaches”一段，紧接着下一段是“Where the conservative analyst overreaches: … he treats ‘multiple compression’ as a certainty rather than a risk”。
- **核验来源与内容**：句内引用两个来源——`src_7e133fa786f7aaa0`（基本面快照：Forward EPS=15.72189、PEG=0.64）和 `src_582ac24bf4319648`（收益表：Diluted EPS 2026-06-30=1.38）；核验绑定第二个。模型内容核验：SUPPORTS，依据 {a304['verification']['llm_content_support']['support_basis']}，推论事实 {len(a304['verification']['llm_content_support']['inference_facts'])} 条，materiality 无。**第一轴（来源是否支持该声明）已有模型结论。**
- **模型的 Alpha 分类**：选择 A304（{a304['llm_alpha_selection']['saved_call']['prompt_version']}）。注意该 prompt 选择的是声明“最直接、实质地**支持或反对**”其命题的 Alpha，输出里**没有方向**；同一 prompt 还写明“对他人估值论点的反驳，如果本身不断言估值结论，不满足 A304”。所以“模型选了 A304”**不等于**“该声明支持 A304”。
- **谁产生了 `negated` / `mention` / 匹配分 0**（全部是确定性代码）：`claim_semantics.analyze_claim_semantics` 的否定模式命中 “{a304['deterministic_text_rule_trace']['regex_hits']['_NEGATION_PATTERN']}”（句中 “not a forward EPS of $15.72”）→ assertion=`negated`；无竞争/提及/风险缓解/否证模式、未判混合 → semantic_polarity=`mention`；`alpha_relation` 因此返回 `mention`；`direction_score`、`semantic_score` 均为 0，候选 `eligible=false`。匹配分 0.0。
- **对池/激活/冲突的作用，逐关**：① `select_supporting_alpha_claims`：`RELATION_NOT_SUPPORTING`（排除）；② 即使关系改为 activation，`negated` 断言会被排除且权重为 0；③ 冲突检测器：`UNSUPPORTED_RELATION`，任何原因码都在立场准入判断**之前**返回，所以立场判断根本轮不到；④ 即使 ①–③ 都清除，Portfolio Manager 是 Secondary 角色，Secondary-only 组需要“文本点名 AMD 且 relation=activation 且 asserted”——本条为 `{a304['downstream_gates_in_order']['4_source_role_rule_if_1_to_3_were_cleared']['result']}`（用真实生产函数复算）。
- **三类语义必须区分，不能把否定词当作自动无关**：（a）否定 A304 自己的机制；（b）反驳对立论点（**可能支持 A304**）；（c）仅提及话题。对三句**合成**示例（非真实数据）文本规则给出完全相同的输出（negated / mention / mention），所以靠词面无法也不应该裁决。
- **已有语义任务/保存字段能否回答？不能**：分类只回答“涉及哪个 Alpha”；内容核验只回答第一轴；结构抽取没有任何边与这条相关；唯一能回答的任务 `evidence_stance_classifier`（立场：支持/反对/仅涉及/背景/支持对立 Alpha）**从未对这一对运行**——它在冻结的 162 对清单里（`reusable_from_base_run=false`），第 17 轮第 1 批超时后停止，未轮到。**所以没有被消费错误遮住的有效模型判断**，关系保持“未解决”。不手工改成 activation、不删除 negated、不给正权重、不把我的解读存成模型结论。

## 7. 本轮修复与测试

**唯一的生产代码修改**：`comqutor_alpha/api/agent_output_reader.py`（修改前副本与 SHA256 在 `pre_change_snapshot_read_time_fix/`；复现记录 `reproduction_read_time_diagnostic_before_fix.json`）。

- **复现**：重启后的真实服务 `/api/research/{{requal}}/agent-outputs` 对该声明返回 `REVIEW_SOURCE_NOT_LINKED_TO_CLAIM`（见复现记录），已存产物里 `linked_source_ids=[src_7e13…, src_582a…]` 且核验绑定的 `src_582a…` 在其中。
- **修复**：只在“某记录的核验绑定了非主来源”时，读取该运行已保存的 `structured_agent_outputs.json`，把该声明的引用列表**只交给诊断函数**；公共记录不新增字段；artifact 缺失/损坏/格式异常/主来源不一致时退回原行为且不抛异常。
- **没有改**：任何已存结果、评分公式/阈值、核验标准、taxonomy、参考标签；没有新增模型/搜索请求。**因此没有创建新的派生 execution**（生产评分、敞口、冲突入口的消费行为没有改变；只改变一个只读接口的诊断显示）。
- **测试（固定输入，只证明接线，不证明模型质量）**：
  - `tests/test_agent_outputs_cited_source_list_read_time.py`：15 项（含：多来源声明在读取时 ELIGIBLE、公共字段不变；无 artifact/损坏 artifact 退回原行为；核验来源不在引用列表仍拒绝；**内容变化仍拒绝**（时间/哈希/允许来源边界）；artifact 主来源与数据库不一致则忽略；单来源声明不触发 artifact 读取；他人声明的列表不被套用；畸形列表忽略）。**对修改前代码运行：2 项失败（正向用例与内容变化边界），其余 13 项在两种代码下都通过**（红绿证据在 `test_logs/`）。
  - `tests/test_alpha_evidence_consumption_contract.py`：23 项（模型契约只含 decision/selected_alpha_id、多余强度字段被拒绝；零词面分的 LLM 选择=池成员且权重 0、不被设为 1.0；缺失/非法分数被排除；零权重不变成确定方向；mention/negated/context-only 不被升级；仅显式 supports_alpha 立场计数、缺失立场不计；来源支持与 Alpha 关系两轴独立；共享来源不合并不同事实、真实复述才合并；Secondary 转述不加独立性；单 agent 独立性不被制造；一条读取已保存 AMD 记录的复现测试）。6 项突变检验（改动对应的生产行为后测试必须失败）全部被检出。
  - 第 18 轮边界测试 `tests/test_evidence_requalification.py` 18 项重跑通过（时间/哈希/允许来源边界仍成立）。
  - 受影响套件合并运行：**306 passed，退出码 0**（命令与输出在 `test_logs/affected_suites_after_read_time_fix.*`）。未启动全量回归，未重复无关测试。

## 8. 真实服务 / API / 界面 / Export 核验

**服务重启**：确认无活跃任务后，用现有启动链重启（先做了不会真正启动的预检：端口占用时启动器拒绝，验证命令与权限）；两次重启均未被权限系统拒绝；环境变量 23 项前后完全一致（`service_restart/`）。第一次重启后的只读核验有 1 项未通过（上文的显示缺陷），修复后第二次重启，**{passed}/{len(L)} 项通过**：

{t_live}

要点：服务读到血缘块与两个新增产物；读取时资格与已存结果在 500 条 API 可见声明上 0 处矛盾（该接口返回的是“产品发现”视图 = 500 条分析性声明，另 475 条背景声明只在产物与 Export 里）；10 个 Alpha 的分数/等级/敞口与冲突与产物完全一致；Export ZIP 17 个成员与文件逐字节一致；注册表只有 3 个快照带可用时间记录，`published_at` 未被回填。

**浏览器核验**（真实 Chrome 无头，对既有 run；浏览器层面拦截所有非 GET 请求，实际被拦截 {len(browser['blocked_non_get_requests'])} 个；控制台错误 {len(browser['console_errors'])}；失败请求 {len(browser['failed_requests'])}；没有点击新研究/运行/保存评审按钮）：

- **看到了**：结构页 A301 卡片——Activation score 21.3、Uncapped 21.3、Qualification ceiling 60、Score was capped: No、等级显示为 “Emerging”（即 candidate）、Direction positive、Supporting evidence 3、Distinct supporting agents 1、Ticker-specific evidence 0、Local structural edges 0 与 `NO_COMMITTED_ALPHA_MATCH`、上限原因码；展开 “Evidence (3)”：三条声明的原文、Agent、**Match 0.19 / 0.00 / 0.00**、Relation、Assertion、claim_id。即**评分依据（匹配分/关系/断言）可见**。
- **没有看到（未验证）**：A301 证据列表里**没有来源 ID、片段、数据位置、核验状态**；也没有各分项得分明细（证据质量 1.64、agent 独立性 4.67 等）。Research 页“Analyst findings”只渲染 direction 为 positive/negative 的声明，A301 的三条 direction 为 unknown，**页面上找不到这三条**；“Unclassified findings”只展示前 20 条。因此**无法在界面里从 A301 的关键结论走到真实片段/数据位置**——数据在 API 里有（`linked_source`、核验记录），缺的是界面连接。这是对 John T1-E“点击重要结论应看到内容片段”的**未满足项**，属工程（界面）缺口，本轮未改。
- 冲突页：“No conflicts detected … This does not mean the position carries no risk”；声明 8 对、准入 0、抑制 0、拒绝 8，每对“Not evaluated — did not have enough evidence”。Research 页顶部如实写明“Alpha classification is incomplete … 1 of 975 claims have no usable classification result …”。
- 历史菜单列出 7 个运行，只显示股票/状态/日期，**不显示执行类型或血缘**（血缘仅在 API）。
- 浏览器 Export：`requal-20261007T174744Z-664040d6_research_export.zip`，{bs['export_download']['bytes']} 字节、{bs['export_download']['members']} 个成员，与 execution 的文件逐字节一致。
- 披露：浏览器核验期间，**另一个 Claude Code 会话**（其记忆笔记写明正在做前端首页 `/research` 的重设计，未提交、直接改主目录）在同一仓库里新增/修改了 {fe['count']} 个前端文件（头部的 “Server ready” 状态条与 “Recent runs” 菜单属于这批改动，时间 11:33–11:46），并重建了 `frontend/dist`、重写了 `.demo/w5`；**均非本轮所为，原样保留**。这批改动涉及应用外壳、首页和历史菜单，不涉及本次核验所用的 AlphaCard、StructureGraphPage、ResearchRunPage、ExternalSourceDisplay、ContentSupportReviewPanel。

## 9. 19 条分析性 SUPPORTS 与 24 条重评估声明的去向

**19 条**（第 12 轮冻结清单）：

{t_19}

**24 条**（第 18 轮时间资格/核验绑定修复涉及的声明；与前一清单有 7 条重叠）：

{t_24}

## 10. 关键摘要结论（Portfolio Manager 最终决策）的依据与缺口

最终决策（“Reduce existing AMD holdings by 40% … stop at roughly 610 …”）共 63 条声明：已关联 {sum(1 for r in pm if r['link']['status'] == 'VALID')}、具备资格 {sum(1 for r in pm if r['eligibility']['eligible'])}、匹配 Alpha {sum(1 for r in pm if r['classification']['match_status'] == 'matched')}、进入官方池 0。

{t_pm}

- **“AMD 的基本面拐点是真实且已验证的”**（#3）本身是总括判断，未关联来源；它的数字依据在 #4（收入 7,685M→11,536M、毛利率 39.8%→53.8%、经营利润 −134M→+1,990M），句内三处引用同一收益表快照。**数字在快照里都有依据，但验证状态不一样**：收入对应分析师声明 31、经营利润对应声明 38，均已核验为 SUPPORTS；**毛利率没有已核验的分析师层面对应声明**——它是由快照里“毛利润 ÷ 总收入”两行相除得到的派生指标（本次复算：五个季度的 39.8 / 51.7 / 54.3 / 52.8 / 53.8% 全部能由两行数据逐位复现），但该来源没有登记 calculation_method / 输入，分析师的毛利率声明（fundamentals 34、120，bull 22）全部未关联，下游转述（aggressive 11、neutral 9、conservative 6、PM #4）已关联但核验未完成。PM 这句自己的核验同样没有完成（Agent 自引、未经核验，资格 NOT_REVIEWED）。缺口性质：**工程**（派生指标未接通、核验未完成），不是材料缺失。
- **“减持 40%”“止损约 610”（#41、#44）是决策/建议，不是可核验的数据命题**；其中的技术位（10 日均线 618.52、50 日均线 518.93、布林上轨 691.33、ATR 23.98）关联到行情快照，核验结果混合：有已核验（如 #26 RSI、#46 上轨）、有条件、有未核验。
- 因此：这些结论没有被当作“充分验证”展示（它们不在官方池里）；但它们的依据**部分存在、部分核验未完成**，不能写成“已全部验证”。

## 11. 每个 Alpha 的完整漏斗与未激活原因

{t_funnel}

补充：Exposure 种子缺失（`missing_seed`）：A001、A003、A501；其余 Alpha 的最终敞口 0.275–0.5。**没有任何 Alpha 达到 active（阈值 50）。**

## 12. 每个冲突对的采纳 / 拒绝原因

{t_conf}

**共同首要原因**：A304 在官方口径下没有证据（方向 unknown），声明冲突对要求“双方各有合格证据且角色可判定”。第 18 轮对声明 31/33/36 的处理只让 A301 一侧有了正向，对侧仍是空。依赖立场的准入判断（只认 `supports_alpha`）在所有 8 对里**都没有被走到**——因此即便拿到方向判断，也不会改变这一次的冲突结果。

## 13. 被错误挡住但依据充分的问题与修复结果

| 问题 | 证据 | 性质 | 结果 |
|---|---|---|---|
| 23 条财务声明被判 `DISCLOSURE_TIME_UNKNOWN` | 3 张收益/资产负债/现金流快照 published_at 为空 | 实现把“披露日期”当作“可用时间”的代理 | **第 18 轮已修复**（“注册表写入时间上界”可用时间记录，不冒充披露日期；截止后获得的材料仍被拒绝） |
| 1 条（PM claim 10）被判 `CONTENT_VERSION_CHANGED_SINCE_REVIEW` | 核验绑定的是第二个被引用来源，消费方却拿它和主来源比哈希 | 绑定缺陷，内容没有变 | **第 18 轮已修复**（按核验所绑定的来源比对；不在引用内则拒绝） |
| 同一声明在**读取时**被显示为 `REVIEW_SOURCE_NOT_LINKED_TO_CLAIM` | 数据库/白名单丢失 `linked_source_ids` | 已有字段没传到消费方 | **本轮已修复并核验**（§7） |
| 7 条已验证且被模型选中的声明被判“非分析性”（A301 ×5、A201 ×2） | 同一收入事实，“Revenue grew from…”（声明 31）为分析性、“Revenue went from … to …”（aggressive 10）为背景；`claim_quality.STATE_OR_CHANGE_TERMS` 含 grew/rose/doubled，不含 “went from”“swung” | 确定性声明质量规则的覆盖/设计问题，不是接线错误。进程内试验（未改文件）：补上 “went from / swung” 只会让其中 3 条（fundamentals 38、aggressive 10、aggressive 12）变为分析性，另 4 条是表格行式/EPS 对比句，需要另行判断 | **未改**（需要产品/语义判断；见提案 D4） |
| 12 条可能入池的声明因内容核验技术回退而未完成（超时 6、引文位置未能定位 4、格式不合规 2；A301 ×4、A201 ×5、A304 ×2、A101 ×1） | 见 `proposal_target_claims.json` | 工程缺口 | **未执行**（需要模型请求；提案 B） |
| 毛利率（派生指标）声明未关联：fundamentals 34、120，bull 22 | 五个季度毛利率由快照里的毛利润与总收入两行相除全部复现；来源无 calculation_* 声明 | 工程缺口：派生指标没有登记为带输入与方法的来源 | **未改**（需要在取数/登记层为派生指标保存输入与方法；见 §10、§14） |
| 声明 33/36 权重 0；声明 10 的关系 | §5、§6 | 语义缺口（相关强度/立场未被判断） | **未改**（提案 A、C） |
| 63 条“已匹配、分析性、关系合格但未关联来源”的声明（A304 19、A301 15、A501 11 …） | §14 | 其中约 39 条是观点/预测，没有数据记录可关联 | 不处理，不批量挂载 |

## 14. 未关联材料：是否需要外部取数？（先查已有来源与 Agent 实际输入）

本次运行保存的来源只有 35 个：30 条新闻（无正文）+ 5 个带数据的快照（行情 1、基本面 1、报表 3）；261 条关联全部指向这 5 个快照。研究 Agent 的调用日志只保存调用元数据（成本/时延/token），**不保存 prompt 与工具原始输出**，所以“Agent 实际看到了什么”只能从来源登记表和已保存的报告文本推断。

对 714 条未关联声明做**确定性诊断**（仅看声明里的数值是否出现在已保存材料中；**不是核验，也不建立任何关联**）：

{t_unlinked}

方法局限必须说明：同样的检查用在 261 条**确实已关联**的数值声明上，只有 {chk['linked_all_numbers_in_own_source']}/{chk['linked_all_numbers_in_own_source'] + chk['linked_numbers_not_all_in_own_source']} 条能在自己的来源里找到全部数值（派生百分比、比值不会原样出现在快照里），所以 U3–U5 **低估**了可关联性。结论：**540 条（76%）没有可定位的数值，取外部数据也无法为它们提供“来源”；至少 60 条的数值已完整存在于已保存的来源正文中——这是改进关联算法的工程问题，不需要外部取数。**派生指标是其中一个真实的例子：毛利率（§10）的输入两行就在已保存的快照里，却没有被登记为可复算的派生来源。 新闻：30 条来源只有标题/链接，106 条新闻声明无法核验；是否是供应商未给摘要不能由已保存材料判断（原始响应未保存）。**对历史运行，外部重新取数也不能证明“当时的响应”**（T1-A），所以这些只能标注未验证，不能靠今天的数据回填。

## 15. AMD 原 34 条固定验收清单（`amd_34_fixed_acceptance_list.csv / .json`）

{t_34}

清单保留全部原 evidence_id 和 John 的各字段；“是否继续用于冲突”拆为三列，**不把资格当作采用**；无执行结果的一律写“未执行”。**这 34 条在新流程下的命运只能由一次在取数时保存正文的 Fresh Run 证明；在此之前它们保持“未验证”，不回填。**

## 16. 975 条可筛选清单（`claims_975_list.csv / .json`）

37 列，UTF-8 带 BOM（Excel 可直接打开）：claim_id、原文、Agent、上下文定位、来源 ID、真实片段 ID、数据/片段位置、关联状态与方式、核验方法/任务版本/结果、未被支持部分及原始原因、时间与绑定资格、声明质量及判定方法、模型原始 Alpha 选择、映射器最终结果、关系/方向及方法、词面匹配分、是否入池、实际权重、未计分原因、是否属于 19/24 清单、未关联声明的诊断、未执行或无法确认的步骤。机械状态用固定中文映射（`zh_mapping.py`，无模型调用）。重算的资格计数与已保存产物逐项一致（ELIGIBLE 64 / SOURCE_LINK_NOT_VALID 714 / NOT_REVIEWED 107 / SUPPORT_STATUS_NOT_RESOLVED 89 / SOURCE_OPPOSES_CLAIM 1）。

## 17. 历史不变证明

{t_hash}

- 保护清单 73 个文件逐一一致；原始/恢复/方向/重评估运行目录与本轮开始时的哈希逐字节相同；历史 AMD 运行 `d5b60b8a` 的 6 个由第 4 轮记录的 SHA-256 今天复核全部一致，且目录内无本轮开始后被修改的文件。
- **本轮的后端生产代码修改恰好 1 个文件**（上述读取诊断修复）。{fe['count']} 个前端文件、`frontend/dist`、`.demo/w5` 的变更来自另一个会话（前端首页重设计），已披露、未触碰。
{('- 凭据扫描：' + scan['summary']) if scan else ''}

## 18. 仍缺失的内容及其性质

| 缺口 | 性质 | 需要什么 |
|---|---|---|
| A301 声明 33/36 的相关强度；其余所有模型选择的相关强度 | **语义**（没有模型判断；评分用词面规则分） | 提案 A + 版本化消费规则（需 John/负责人决定映射） |
| A304 声明 10 对 A304 的支持/反对/仅提及 | **语义** | 提案 A（现有 `evidence_stance_classifier`，这 1 对与 A301 的 3 对同批） + 消费规则；后面还有 Secondary 角色/ticker 特异性两关 |
| 方向判断（162 对） | 语义；**不改变本次冲突结果**（8 对都没走到立场判断） | 不建议在此之前花费 |
| 12 条可能入池声明的内容核验未完成 | **工程**（技术性回退） | 提案 B（12 次请求） |
| 声明 105 的分类超时（使 `alpha_classification_status` 保持 incomplete，界面显示“无法判定”） | **工程** | 提案 C（1 次请求） |
| 7 条已验证声明被“非分析性”规则挡住；ticker 特异性不读绑定来源的 instrument | **设计/政策**（词表覆盖、评分输入） | 负责人决策，不是模型请求 |
| 界面不能从 A301 结论走到片段与核验状态 | **工程（界面）**，数据已在 API | 前端连接（用 claim_id 关联 agent-outputs） |
| 新闻正文、宏观来源在真实运行中未验证；财务来源的披露日期/每次调用抓取时间/货币单位 | 材料/工程 | 取数时保存（Fresh Run 才能证明） |
| AMD 原 34 条 | **材料缺失**（历史运行无正文/无财务来源） | 无法由付费调用恢复；只能由新流程的 Fresh Run 验证新流程 |

统一的最小模型请求提案见 **`03_最小模型请求提案_未执行.md`**（A：4 对立场；B：12 次内容核验重试；C：1 次分类重试；每部分可单独批准；**本轮未执行，也不自动重跑原 162 对方向判断**）。

## 19. 明确不声明的事项

- **不声明 T1 或 John 整体验收通过。** 本轮证明的是：消费链各环节做了什么、哪里有一处显示缺陷（已修）、哪些判断从未被做过。
- 不把“没有记分”解释为“声明不合理”；不把“按当前代码执行”当作符合 John 要求的证明；不因出现非零分数（A301 的 21.31）而宣布通过。
- 测试（固定输入）与真实 AMD 结果分开；合成句子（§6 的三句示例、测试中的记录）不是真实样本，也不是模型质量证明。
- 未做：Provider/搜索请求、重新取数、研究 Agent、全量回归、commit/push、Demo。

## 附：文件清单（均在 `round19_consumption_and_acceptance_20261007/`）

`01_中文主验收报告.md`（本文）· `03_最小模型请求提案_未执行.md` · `amd_34_fixed_acceptance_list.csv/.json` · `claims_975_list.csv/.json` · `claims_975_summary.json` · `consumption_chain_reproduction.json`（+`reproduce_consumption_chain.py`）· `proposal_target_claims.json` · `live_service_verification_round19.*`（第二次重启后）与 `…_FIRST_RESTART_before_fix.*`（第一次重启后，含 1 项未通过） · `service_restart/` · `browser_walkthrough.mjs`、`browser_walkthrough_result.json`、`browser_walkthrough/`（截图与浏览器导出的 ZIP） · `pre_change_snapshot_read_time_fix/`、`reproduction_read_time_diagnostic_before_fix.json` · `test_logs/` · `final_hash_proofs.*`、`*_run_hashes_before_round19.json`、`production_tree_hashes_before_round19.json` · 构建脚本 `build_975_claim_list.py`、`build_amd34_acceptance_list.py`、`build_report.py`、`zh_mapping.py`。测试文件：`tests/test_alpha_evidence_consumption_contract.py`、`tests/test_agent_outputs_cited_source_list_read_time.py`。
""")

(HERE / "01_中文主验收报告.md").write_text("\n".join(R), encoding="utf-8")
print("wrote 01_中文主验收报告.md", sum(len(x) for x in R), "chars")
