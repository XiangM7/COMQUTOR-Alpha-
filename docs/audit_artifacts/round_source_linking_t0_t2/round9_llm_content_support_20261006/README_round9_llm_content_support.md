# 第九轮：真实 LLM 内容支持核验 + 生产接线（2026-10-06）

零 Provider 调用、未启动 Fresh Run。保留第八轮已完成的来源捕获、引用
传递、派生计算、去重、时间修复、API/Export 链路，没有重建系统。未改
评分公式、阈值、taxonomy、Alpha 语义准入规则，未处理 Demo，未扩展全仓
清理，未碰历史 Gold，未 commit、未 push。John 指定的 AMD 原 34 条历史
冲突证据继续只读保留，未用新材料回填。

## 一、为什么要改第八轮的做法

第八轮"删掉数字/日期/字段名，剩余文字为空才通过"的方法，本质只能证明
一句话是"纯数字枚举"，对任何带分析性判断的句子（比如"PEG 0.64 说明
便宜""这是最重要的拐点"）天然不可能通过——这不是该方法的 bug，是它
的设计边界。本轮不再试图用正则/关键词白名单去扩大这个边界，而是把
"这段保存材料是否支持这句话"这件事交给真正能读懂语义的 LLM，代码只
做身份、范围、位置、时间、数值这些可机械核查的部分。第八轮的确定性
核验器本身不变，继续作为更便宜的"先试一次"和喂给 LLM 的机械依据。

## 二、最小代码改动

| 文件 | 改动内容 |
|---|---|
| `comqutor_alpha/structure_engine/content_support_llm.py`（新文件，626 行） | 新任务 `content_support_verification` 的完整实现：请求构建（每条声明只带该声明自己已解析到的有限候选来源，从不挂整个 registry）、批处理（复用 `evidence_stance_llm.py` 的批次+并发骨架）、响应校验（身份、候选集合membership、引文/数据真实存在性、状态合法性）、部分支持降级、失败原因记录、真实生产入口 `apply_llm_content_support_verification`。 |
| `comqutor_alpha/structure_engine/week2_llm.py` | 新增 `_TASK_INSTRUCTIONS["content_support_verification"]`（真实 prompt 文本）与 `_TASK_RUNTIME_METADATA["content_support_verification"]`（`prompt_version: content_support.llm.v1`）。沿用同一个 `Week2LLMGateway`，未新建客户端。 |
| `comqutor_alpha/source_provenance.py` | 新增 `REVIEW_METHOD_LLM_CONTENT_SUPPORT_VERIFIED`，加入 `AUTOMATICALLY_ELIGIBLE_REVIEW_METHODS`；修正 `build_content_support_review` 的绑定校验（`status==PENDING_REVIEW` 时豁免绑定要求，因为 LLM 判定"材料不足"时确实没有来源可绑定，且 PENDING_REVIEW 本来就不会获得资格——这是本轮发现的一个真实边界 bug，已修复并补测试）。 |
| `comqutor_alpha/structure_engine/structured_output_adapter.py` | 在 `adapt_run_outputs` 的 `records` 构建完成后，追加真实生产调用 `apply_llm_content_support_verification(records, sources, llm_gateway=llm_gateway)`——和 `alpha_mapper.py` 里 `apply_llm_stance_upgrade` 同样的"收集完整列表后一次性批处理"接线方式，`llm_gateway=None` 时保证零成本空操作。 |

新增测试：`tests/test_content_support_llm.py`（17 个，正向+反向，见下）。

真实测试命令与结果：
```
.venv/bin/python3 -m pytest tests/test_content_support_llm.py -v
# 17 passed

.venv/bin/python3 -m pytest tests/test_content_support_llm.py tests/test_automated_content_support_verification.py \
  tests/test_structured_output_adapter.py tests/test_t1_financial_statement_source_chain.py \
  tests/test_t1_source_linking_pipeline.py tests/test_content_support_never_inflates_scoring.py \
  tests/test_evidence_gate_qualified_evidence_scenarios.py tests/test_source_provenance.py \
  tests/test_verified_evidence_gate.py tests/test_verified_evidence_gate_production_wiring.py \
  tests/test_t1_cross_agent_reference_and_derived_calc.py tests/test_t1_financial_source_chain.py \
  tests/test_t1_macro_source_chain.py tests/test_t1_market_data_source_linking.py \
  tests/test_conflict_detector.py tests/test_acceptance_engine.py tests/test_graph_persistence.py \
  tests/test_week4_golden_closure.py tests/test_week4_nvda_conflict_sanity.py \
  tests/test_week3_nvda_sanity.py tests/test_week3_qqq_sanity.py \
  tests/test_evidence_stance_llm.py tests/test_evidence_stance_integration.py tests/test_evidence_stance_classifier.py -q
# 576 passed

.venv/bin/python3 -m pytest tests/test_week2_llm.py tests/test_week2_llm_semantic_runtime_integration.py -q
# 38 passed, 1 skipped（既有、需要真实 Provider smoke 测试的用例，未开启）
```

## 三、任务契约

**只在外部模型边界用固定响应**（`FakeContentSupportGateway`，复用
`test_evidence_stance_llm.py` 同样的"真实校验器跑在假响应上"手法）。

每条请求只包含：`claim_id`、`proposition`（声明原文）、`context`
（`evidence_text`/`source_section`/`agent`）、`allowed_candidates`（这条
声明自己已解析到的 `linked_source_id`/`linked_source_ids`，附真实
`excerpt`/`data_snapshot`，从不是标题/URL）、`mechanical_checks`（第八轮
确定性核验器已经独立确认过的数字，供 LLM 参考而非要求它重新推导）。

每条响应要求：`claim_id`、`status`（SUPPORTS/OPPOSES/BACKGROUND/
CITATION_ONLY/CONDITIONAL/INSUFFICIENT，映射到既有
`content_support_status` 词表，INSUFFICIENT→PENDING_REVIEW）、
`used_source_id`、`used_location`、`supporting_quote_or_data`、
`rationale`、`supported_proposition`、`unsupported_remainder`。

**后端真实校验**（`_validate_response_item`，从不只看"支持=true"）：
1. `claim_id` 必须对应本次请求。
2. `used_source_id` 必须在**这条声明自己的**候选集合里（不是整个
   registry）——伪造一个真实存在、但不属于这条声明候选集合的 source_id
   会被拒绝（`test_source_id_outside_the_allowed_candidate_set_is_
   rejected`）。
3. `supporting_quote_or_data` 必须真实存在于该来源的 `excerpt` 或
   `data_snapshot`（逐层遍历比对，不信任模型自己报的 `used_location`
   路径字符串）——编造一个来源里没有的数字会被拒绝
   (`test_quote_not_actually_present_in_the_source_is_rejected`)。
4. 状态值非法、claim_id 不匹配、重复结果、额外未请求的结果——都有独立
   的 `fallback_reason`，从不转成 NONE 或 SUPPORTS
   (`test_malformed_status_is_rejected`/`test_identity_mismatch_is_
   rejected`/`test_duplicate_results_for_the_same_claim_are_rejected_
   not_arbitrarily_picked`)。
5. 超时、Provider 错误、预算耗尽、截断（`WEEK2_LLM_VALIDATION_FAILED`）
   各自独立记录在 `content_support_llm_fallback_reason`，原有
   `content_support_status` 原样保留，不被覆盖
   (`test_timeout_is_recorded_distinctly_and_record_is_left_unchanged`/
   `test_budget_exhausted_is_recorded_distinctly_never_as_none_or_
   supports`)。

**部分支持降级**（第 5 点，本轮明确的能力边界）：当模型返回
`status=SUPPORTS` 但 `unsupported_remainder` 非空（复合句只有一部分
被支持），后端把有效状态降级为 `CONDITIONAL`——既有
`compute_verified_support_eligibility` 自己的契约里 CONDITIONAL
"never count as direct support"，不需要新状态值
(`test_partial_support_with_unsupported_remainder_is_downgraded_to_
conditional`)。**本轮没有实现安全的句子拆分**（把真正支持的部分拆成
独立子声明参评、其余部分保留原句）——这是一个明确记录、未实现的能力
边界，不是被忽略的缺口：现有抽取粒度没有可靠的句内支持范围标注，
强行拆分本身就是本轮任务明确警告过的风险操作。

**事实与结论不重复计数**：第八轮的确定性核验器和本轮的 LLM 核验器
对同一条声明是互斥的——`build_content_support_request_items` 在构建
请求前先跑一次 `verify_data_fact_or_derived_calculation`，已经被
第八轮机制核验过的声明不会再消耗一次真实 Provider 调用，也不会被
算两次独立证据。

## 四、生产接线位置

`comqutor_alpha/structure_engine/structured_output_adapter.py` 的
`adapt_run_outputs` 函数，`records` 完整构建完毕之后、函数返回之前，
作为一次性批处理 post-pass 调用——和 `alpha_mapper.py` 里
`apply_llm_stance_upgrade` 完全同构的接线方式。`llm_gateway=None`
（现有每一个调用方的默认值，包括 Architecture Replay）时是严格零成本
空操作，`records` 原样返回，已用 86 个既有 `structured_output_adapter`/
T1 来源链路测试验证零回归。

## 五、AMD 21 条分析性声明逐条材料核实（真实数据，不是估算）

第八轮已确认：这 21 条分析性声明的 `source_link_status` 修时间 bug后
全部变成 `VALID`，但因为文本里混有解释/比较/策略性语言，被第八轮确定性
核验器正确地保守拒绝，`content_support_status` 停留在 `PENDING_REVIEW`
至今。全部 21 条的 `linked_source_id` 指向同一个来源
`src_5bd8a947130d1949`（.info 实时估值快照，真实字段：market_cap、
trailing_pe、forward_pe、peg_ratio、price_to_book、eps_ttm、
forward_eps、dividend_yield、beta、52_week_high/low、
50_day_avg、200_day_avg）。完整原文见本目录
`01_amd_21_analytical_claims_raw.json`。逐条材料充分性核实（分三档，
材料不足的如实保留，不替换成更容易过的样本）：

| # | claim_id（节选 agent:claim） | 核心可验证锚点（若有） | 材料充分性判定 |
|---|---|---|---|
| 1 | conservative_risk_analyst:31 | beta=2.45（真实字段） | **部分**——beta 真实，"鹰派重定价压缩估值最快"是宏观因果推断，这一个估值快照无法独立证实 |
| 2 | bear_researcher:54 | forward_eps=15.63（真实字段） | **部分**——数字真实，"sell-side 估计总是滞后"是一般性论断，非本来源能证实 |
| 3 | neutral_risk_analyst:9 | beta=2.45 | **部分**——反驳另一方论点的修辞，仅 beta 本身可核 |
| 4 | research_manager:7 | 无（宏观利率情景推理） | **不足**——涉及利率/需求联合情景，这一个来源没有任何宏观/利率字段 |
| 5 | fundamental_agent:119 | beta=2.45 | **部分**——beta 真实，"会放大任何半导体/AI 题材波动"是从 beta 定义做的合理推论，但来源本身不直接陈述这个结论 |
| 6 | conservative_risk_analyst:48 | 52_week_low=188.22 | **部分**——数字真实，仓位处理策略建议不可核 |
| 7 | aggressive_risk_analyst:42 | 无（covered call 策略提案） | **不足**——纯交易策略提案，无对应可核数据 |
| 8 | aggressive_risk_analyst:17 | forward_eps=15.63, eps_ttm=3.92, peg_ratio=0.64（均真实） | **部分**——"4x ramp"是可重算的真实派生计算（15.63/3.92≈3.99），"70% 落地"是假设性条件，不可核 |
| 9 | bull_researcher:13 | peg_ratio=0.64 | **充分**（最接近纯引用）——句子本身只是指出这个数字，材料直接支持 |
| 10 | fundamental_agent:28 | trailing_pe=161, forward_pe=40.4, forward_eps=15.63, eps_ttm=3.92 | **部分**——4 个数字全真实且比例关系可重算，"市场正在定价巨大盈利爬坡"是解读 |
| 11 | research_manager:8 | peg_ratio=0.64 | **不足**——"PEG 是循环论证"是方法论批评，这一个快照无法证实或证伪 |
| 12 | portfolio_manager:8 | beta=2.45（旁引） | **不足**——综合转述另一分析师的三个情景，无单一可核事实 |
| 13 | portfolio_manager:38 | 50_day_avg=513.53, 52_week_low=188.22 | **部分**——两个数字真实，"跌破即应减仓"是交易规则主张 |
| 14 | neutral_risk_analyst:16 | 52_week_low=188.22 | **部分**——数字真实，"是投降式定价"是修辞判断 |
| 15 | bear_researcher:66 | 200_day_avg（真实字段），beta=2.45 | **部分**——"高于 200 日均线 37%"需要当前股价（这个来源 data_snapshot 没有独立的"当前价格"字段），37% 这个具体比例本身无法仅凭此来源重算 |
| 16 | bear_researcher:53 | peg_ratio=0.64 | **部分**——PEG 真实，"PEG 只和增长估计一样可靠"是方法论评论 |
| 17 | portfolio_manager:12 | 无 | **不足**——纯粹评价另一分析师论证质量，无可核数据点 |
| 18 | fundamental_agent:107 | forward_eps=15.63, eps_ttm=3.92, peg_ratio=0.64 | **部分**——同 #8/#10，4x ramp 可重算，"是否贵"的结论不可核 |
| 19 | fundamental_agent:29 | peg_ratio=0.64 | **部分**——PEG 真实，"整个论点取决于执行"是条件性判断 |
| 20 | bull_researcher:61 | peg_ratio=0.64 | **部分**——PEG 真实，"Q2 数据说明在轨道上"引用的是另一个来源（利润表）的信息，本来源单独看不完整 |
| 21 | conservative_risk_analyst:24 | peg_ratio=0.64 | **部分**——PEG 真实，"PEG 建立在待交付的前瞻估计上"是方法论批评 |

**汇总**：21 条中，1 条（#9）材料充分、大概率能拿到真实 SUPPORTS；
15 条材料部分充分（真实数字锚点存在，但整句的主要论断本身不可被这一个
来源证实，真实运行后按本轮设计应该被判 CONDITIONAL 或更保守的结果，
而不是整句 SUPPORTS）；5 条（#4/#7/#11/#12/#17）材料明显不足，预期
真实结果是 INSUFFICIENT。**这个预期分布本身就是本轮要验证的对象，
不是预先设定的结论**——有限真实验证的意义正是看真实模型是否和这个
基于材料本身做出的保守预期一致。

## 六、有限真实验证方案（本轮未执行，需另行确认付费）

**范围**：上表全部 21 条，不替换、不精简为"更容易通过"的子集。

**冻结项**：
- 输入：`outputs/runs/1bad76a7-72ac-4c8b-8189-2e5c0f1a6105/
  structured_agent_outputs.json`（这 21 条记录，claim_id/claim/evidence
  原样）+ `source_registry.json`（`src_5bd8a947130d1949` 的真实
  `content_hash`，本次核验前后必须一致，否则按
  `FALLBACK_CONTENT_HASH_STALE` 处理，不得静默放行）。
- prompt：`content_support.llm.v1`（本轮冻结的真实 prompt 文本，见
  `week2_llm.py` 的 `_TASK_INSTRUCTIONS["content_support_verification"]`）。
- 模型：`deepseek-v4-flash`（与本项目其余真实 Week2 语义任务一致，
  不临时换模型）。

**预算与停止条件**（明确引用已有真实先例，不重复过去已验证不足的配置）：
- **输出 token 上限：4096**（不是 200）——`200` 这个值已经在
  `t3live_20261001T014648Z_1fb9c9d5` 这次真实执行里被证明不足：
  DeepSeek 的推理开销（观测到 1341–2316 reasoning tokens）算在同一个
  completion token 预算里，`max_tokens=200` 导致两次真实尝试全部
  TRUNCATED（见 `docs/audit_artifacts/round_source_linking_t0_t2/
  t3live_20261001T014648Z_1fb9c9d5_max_output_tokens_diagnostic.md`）；
  后续 `t3_prompt_v7_limited_verification_final_index.md` 记录的真实
  3 次验证改用 4096 后，没有一次再触顶。本轮直接复用这个已证明充足的值，
  不再用 200 测一遍。
- 请求总上限：21（每条声明单独一个批次，batch_size=1，避免一次批量
  失败连带影响全部样本的诊断清晰度——这和生产环境默认 `BATCH_SIZE=5`
  不同，是本次验证专门为了"每条独立可诊断"选的参数，不代表生产配置
  改变）。
- 可见重试上限：沿用 Gateway 默认 `max_retries`（不单独放宽，也不为
  这次验证关闭重试）。
- 截断/预算耗尽/任何一次真实请求失败：**如实记录该条的
  `content_support_llm_fallback_reason`，不用同一套配置自动重试**——
  如果出现新的截断，先诊断真实原因（而不是直接再加 token 上限），按
  本轮同样的方式写一份诊断记录。
- 成本依据：21 次真实请求，单价参照 `cost_basis.py` 当前 DeepSeek
  定价（$0.14/M input, $0.28/M output，均为真实已生效定价），每条请求
  输入约 1-2KB（候选来源的 excerpt+data_snapshot，规模远小于 T3 分类
  任务），输出上限 4096 token——**最坏情况下**（21 条全部打满 4096
  输出）总成本量级在个位数美分到约 1 美元区间（精确数字取决于真实
  reasoning token 消耗，T3 先例显示通常远低于上限的 50-60%）。这是
  一次性、一次完成的验证，不是重复运行。

**明确不做**：不预先调整这 21 条声明的内容或候选来源让它们"更容易通过"；
不因为预期有 5 条会是 INSUFFICIENT 就排除它们；不把这次验证的真实结果
用来自动调整评分阈值或人工审核政策。

**本轮未执行**此方案——以上是提案，等待另行批准。

## 七、尚未经过真实模型验证的部分（明确声明，不含糊）

1. **真实语义质量未知**：本轮全部 17 个新测试、576 个回归测试，仅验证
   了"协议和接线正确"（身份校验、候选集合边界、引文真实性核查、失败
   记录、资格准入链路）——FakeContentSupportGateway 的固定响应从不
   证明真实 DeepSeek 模型会对 21 条真实声明做出语义正确的判断。这需要
   第六节的有限真实验证,目前未执行。
2. **未建立完整 `run_research_request` 端到端集成测试**：本轮的正向/
   反向测试在 `apply_llm_content_support_verification`/
   `compute_verified_support_eligibility` 这一层直接验证（真实、
   未修改的函数，非手搓的模拟），但没有像
   `test_evidence_gate_qualified_evidence_scenarios.py` 那样搭一个
   完整的、经过真实 `run_research_request` 入口、注入 FakeGateway 的
   端到端测试。机制本身（`AUTOMATICALLY_ELIGIBLE_REVIEW_METHODS`→
   `compute_verified_support_eligibility`→`score_alpha_v2_verified`/
   `evaluate_conflict_admissibility_verified`）在第八轮已经被同样真实、
   未改动的函数证明过真的在生产入口生效，本轮新方法只是这个集合里
   新增的一个成员，但一次专门针对 LLM 路径的完整端到端复测尚未做，
   是一个明确、具体的剩余工作项,不是被掩盖的缺口。
3. **安全句子拆分未实现**（第五节已述）——复合声明目前只有"整句降级
   为 CONDITIONAL"一条路径，没有"拆出真正支持的子命题独立参评"的能力。
4. **真实生产预算/并发参数未针对这个新任务调优**（`BATCH_SIZE=5`、
   重试策略沿用默认）——这些是可用但未经真实负载验证的初始值。
