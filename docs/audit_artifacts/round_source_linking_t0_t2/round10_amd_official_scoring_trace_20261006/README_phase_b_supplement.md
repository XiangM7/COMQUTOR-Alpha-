# 阶段B有限收尾（2026-10-06）——进入阶段C前的5项补充

原阶段B日志（10/10通过）原样保留，未重跑整套回归，只跑了受影响的
`tests/test_content_support_llm_production_wiring.py`（更新后仍 10/10
通过）。

## 1. test_2 的真实激活状态——不只是"分数相等"

直接读真实数据发现一个一开始没注意到的真实现象：`official["status"]`
和 `raw["status"]` 在**完全相同的分数**（44.0534）下显示不同标签——
`official="candidate"`，`raw="watch"`。查清楚了，不是bug：OFFICIAL
（v2_verified）层多跑了一层真实的、未改动的 `alpha_level_classifier`
（版本`b4.alpha_level.v1`）晋级判定，RAW（v2）层从不跑这一层，两者
本来就是不同的状态词表（raw 用 `activation_status_band_v2` 的5档
inactive/watch/active/dominant/regime_candidate；official 用
b4分类器自己的 candidate/active/dominant/regime_level）。

已补上真实断言，如实报告：`official["activation_level"]=="candidate"`，
`official["status"]=="candidate"`，`raw["status"]=="watch"`，
`A301` 不在 `active_alphas`，不在 `dominant_alphas`——**真实原因是
`cap_reason_codes` 里的 `NO_LOCAL_STRUCTURE_SUPPORT`／
`INSUFFICIENT_AGENT_INDEPENDENCE`（单一agent、无本地结构支持），这2条
真实新闻证据本来就不够越过"active"门槛，不是机制失效，是真实证据量
的真实限制**，已在测试里写清楚，不是弱化成"分数>0就算过"。

## 2. 同源重复——查了真实 Evidence Fact 分组，不止看验证通过数

直接跑真实 `_run_week3_graph_pipeline` 查最终结果，发现一个重要事实：
**改写措辞的"同一事实"（"NVDA datacenter revenue growth is
accelerating this quarter." vs "...confirmed again."）用真实、未改动的
文本相似度分组逻辑并不会自动合并**——按真实 `_blocking_key`
（ticker/factor签名/assertion_status/数字签名/日期签名）分桶后，仍然
各自成组，说明真实系统目前不是靠语义相似度去重，是靠显式的
`duplicate_group_id` 字段（`evidence_fact_index.py` 自己文档里写明的
"stable, authoritative"优先级第一位）。改用这个真实、生产已有的字段后
（这正是 John T1 原文"同一财报被多个Agent引用，应保留这些引用关系，
不能因此增加独立证据数量"点名的机制），真实结果：3条声明全部真实
`SUPPORTS`，`raw_supporting_claim_count=3`，但
`unique_evidence_fact_count=2`（两条改写版合并成1组，另一条真正不同的
事实独立成组）——**没有强行把同源的全部声明合成一个事实**。

## 3. Export/API真实读回——新增断言，未发现已有等价证明可直接复用

搜索过 `tests/test_b2_admissibility_integration.py`/
`test_artifact_bundle_audit.py`/`test_artifact_export_and_api.py`/
`test_week4_postgres_persistence.py`——都调用了真实 export 函数，但
都用各自的最小fixture,没有一个验证的是"本模块的LLM核验结果能否经
Export/API正确读回"这件事,所以没有直接复用,在 test_2 里新增了真实断言：
直接读磁盘上真实产出的 `alpha_activations.json`（确认
`schema_version=="alpha_activations.export.v1"`，和
`extract_alpha_activations_export`真实产出的schema一致，不是另算的）,
核对claim_ids/evidence_count/score和真实`structure_graph.json`完全一致；
再反查`structured_agent_outputs.json`，确认每个官方计入的claim_id都有
真实`content_support_method=LLM_CONTENT_SUPPORT_VERIFIED`和真实引文。
真实 API (`build_research_response`) 的 `dominant_alphas` 字段也核对一致。

## 4. 阶段C参数——确认真正传到客户端，不只写在文档里

直接读 `build_server_week2_llm_gateway` 真实源码确认：
- **客户端重试**：这个函数自己已经无条件写死 `client_kwargs["max_retries"]=0`
  （对每一个调用方都生效，不是本轮新加的，是已有真实生产行为）。
- **应用层重试**：`COMQUTOR_WEEK2_LLM_MAX_RETRIES=0` → 真实
  `Week2LLMGateway.max_retries=0` → `invoke_json_with_trace`自己的重试
  循环变成`range(1,2)`，精确1次真实尝试，查代码确认，不是靠猜。
- **全局硬上限**：`COMQUTOR_WEEK2_LLM_MAX_CALLS=21` → 真实
  `_reserve_call()`预算计数器，21在真实上限`MAX_SERVER_CALLS=3000`内，
  不会被截断成别的数字。
- **输出上限**：`max_tokens=4096`作为显式关键字参数传给
  `build_server_week2_llm_gateway`，真实转发进`client_kwargs["max_tokens"]`，
  到达真实client。

已把真实执行脚本写好（`03_phase_c_execution_script_NOT_RUN.py`），脚本
末尾有硬性`SystemExit`自锁，已验证这个锁本身真实生效（运行过，只触发
了拒绝退出，零 Provider 调用）。`stats.real_provider_attempts`将作为
真实验证字段，执行后必须等于`requested_count`（≤21），超出就说明重试
真的漏了，需要先查再信结果。

## 5. 范围声明——已写入脚本与提案

`02_phase_c_proposal.json`新增`scope_statement`字段，脚本自己的
docstring同样写明：这是对已有AMD 21条材料的一次性有限语义核验,不是
Fresh Run,不是T3总体准确率评测。21条沿用已发布清单原样使用,不因
预期不足换样本。

## 后续（等待阶段C真实结果后再做，本轮未做）

阶段C真实结果保存后，用独立execution重算AMD（复用第八轮已验证过的
"只读原run、新execution_id、不隐藏Provider调用"模式），最终交付逐Alpha
（正式证据数/方向/分数/激活状态）和逐候选冲突（实际采用或拒绝原因）
报告。
