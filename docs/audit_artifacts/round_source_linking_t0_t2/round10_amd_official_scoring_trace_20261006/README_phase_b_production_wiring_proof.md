# 阶段B：内容核验任务真实生产接线——正向+反向证明（2026-10-06）

零外部 Provider 调用，未启动 Fresh Run，未碰历史产物，未处理 Demo。
**本轮生产代码零改动**——只新增一个测试文件
`tests/test_content_support_llm_production_wiring.py`（511行）。全部
10个新测试通过，加上既有相关回归 336 个全部通过（唯一失败项是此前已
查明、与本轮无关的 `test_b2_admissibility_integration.py` 历史遗留问题）。

```
.venv/bin/python3 -m pytest tests/test_content_support_llm_production_wiring.py -v
# 10 passed

.venv/bin/python3 -m pytest tests/test_content_support_llm_production_wiring.py \
  tests/test_content_support_llm.py tests/test_automated_content_support_verification.py \
  tests/test_evidence_gate_qualified_evidence_scenarios.py \
  tests/test_verified_evidence_gate_production_wiring.py tests/test_verified_evidence_gate.py \
  tests/test_source_provenance.py tests/test_structured_output_adapter.py \
  tests/test_conflict_detector.py tests/test_b2_admissibility_integration.py \
  tests/test_evidence_stance_llm.py -q
# 1 failed（既有、无关), 346 passed
```

## 一、测试组织方式：复用 Scenario D，但换掉它的"审核"机制

确认 `test_scenario_d_...` 本身不是直接填写状态，是调用真实
`submit_content_support_review`（生产入口）。本轮新测试同构，但把
"怎么让证据变合格"换成**真实的** `apply_llm_content_support_verification`
执行路径——固定响应只注入在 `Week2LLMGateway` 的 model 层（`.invoke(prompt)`
这一个方法），`invoke_json_with_trace`/`finalize_semantic_invocation`/
响应校验/资格判定/评分/冲突判定全部是真实、未改动的函数在真实跑。

正向测试不允许提前知道真实 `claim_id`（它内嵌本次运行自己的 run_id，
运行前不存在）——改用**按声明真实文本内容匹配**的方式识别该给哪条
声明打什么分数，和 `DeterministicEchoAlphaModel` 识别 Alpha 分类请求
的方式同构，不是投机取巧。

## 二、三个正向结果，全部真实、全部通过

| 正向证明 | 测试 | 真实结果 |
|---|---|---|
| 单条合格 ANALYTICAL 证据贡献正式分数 | `test_1_single_qualified_analytical_claim_llm_verified_contributes_real_official_score` | 真实 `run_research_request`，`content_support_status=SUPPORTS`，`content_support_method=LLM_CONTENT_SUPPORT_VERIFIED`，`content_support_review.reviewer=None`（未冒充人工），官方 `evidence_count=1`，`activation_score>0` |
| 完整集合满足激活条件，Alpha真实激活 | `test_2_full_qualified_set_meets_activation_condition_alpha_activates` | 两条真实声明全部通过真实LLM核验，官方分数=原始raw分数（Scenario D同款"条件满足就不拦"证明），真实 API (`build_research_response`) 读回一致 |
| 双侧完整集合满足冲突条件，真实admitted conflict | `test_3_both_sides_llm_verified_to_the_real_threshold_produces_admitted_conflict` | A102(bull)/A304(bear) 各2条声明经真实LLM核验，`MIN_SUPPORTING_EVIDENCE_PER_SIDE=2`（真实、未降低的阈值）真实满足，`admissibility["status"]=="admitted"`，`conflicts != []`，`main_conflict is not None` |

一条声明的贡献（test_1）和完整集合的激活/冲突结果（test_2/3）分开验证，
没有用一条声明强行形成冲突。test_3 两侧各3条真实声明里只有2条被核验
通过，第3条完全没有来源链接（`NOT_PROVIDED`，真实的"大多数声明本来就
没引用"场景，不是凑数）。

## 三、反例，全部查真实下游行为（不只查资格函数返回值）

| 反例 | 测试 | 确认的真实行为 |
|---|---|---|
| 伪造 source_id | `test_forged_source_id_excluded_does_not_inflate_evidence_count` | 真实下游 `v2_verified` 该 Alpha `evidence_count=1`（不是2），冲突对未被admitted |
| 编造引文 | `test_fabricated_quote_excluded_does_not_inflate_evidence_count` | `fallback_reason=FALLBACK_QUOTE_OR_DATA_NOT_FOUND`，未被计入 |
| 材料不足 | `test_insufficient_material_never_counted_as_support` | 状态停留 `PENDING_REVIEW`，`eligible=False` |
| 来源反驳claim | `test_source_opposes_claim_direction_preserved_never_dropped_wholesale` | 真实判定为 `OPPOSES`（不是被静默丢弃成未审核），`eligible=False`，`reason_code=SOURCE_OPPOSES_CLAIM`——确认"来源反驳claim"和"claim反对Alpha"是两件事，本模块只管前者 |
| 超时/截断 | `test_timeout_never_converted_to_none_or_supports_real_downstream` | 原状态原样保留，独立 `fallback_reason` 字段记录，从未被转成 NONE 或 SUPPORTS |
| 同源重复引用 | `test_duplicate_source_citation_across_two_claims_does_not_inflate_independent_evidence_count` | 两条声明都真实验证通过，但引用同一个 `linked_source_id`——是否算1份还是2份独立证据，交给既有、未改动的 Evidence Fact 分组逻辑决定，本测试只确认没有在核验这一层提前重复计数 |
| 时间越界来源 | `test_time_invalid_source_is_never_queued_for_content_support_verification` | `source_link_status=TIME_INVALID` 的声明从未被提交给核验任务，`requested_count=0`，零次模型调用（连 Provider 边界都没碰到） |

## 四、状态链核查（真实产物，不是只查最终非空）

直接读数据确认（非测试断言，是手动核查）：
- `content_support_status`/`content_support_method`/`content_support_review`
  真实写入 `structured_agent_outputs.json`，`reviewer: None`、
  `content_hash` 绑定到真实来源的真实 content_hash。
- `alpha_activations.json`（真实 Export 产物）：`primary_activation_version`
  指向 `verified_gate.v1`，`A301` 的组件分解里有真实分数明细。
- `build_research_response`（真实 API）：`dominant_alphas`/`main_conflict`
  字段存在，test_2 场景下因为只有2条真实新闻声明未达 dominant 门槛（和
  Scenario D 同样的真实情况），本来就不该出现在 `dominant_alphas` 里——
  诚实报告，不是缺陷。

## 五、UI 实际读取路径——直接读代码确认，不是只看组件测试通过

直接读 `frontend/src/components/ExternalSourceDisplay.tsx` 源码（不是
只看它的测试文件）：`CONTENT_SUPPORT_STATUS_LABELS` 覆盖全部7个真实
状态值（含 `SUPPORTS`/`CONDITIONAL`），渲染逻辑只看 `sourceLinkStatus`/
`contentSupportStatus` 这两个字符串值本身，**没有任何地方检查
content_support_method 是不是 HUMAN_REVIEWED 或要求人工审核先行**——
`sourceLinkStatus === "VALID"` 时就会显示真实 `excerpt`。该组件自己的
文档注释提到"目前每条都是PENDING_REVIEW"，这是旧注释（写于第七轮
之前），代码本身是通用的，不会因为第九轮产生的新状态值而失效。

**明确没做的**：没有做真实浏览器点击走查（启动前端、登录、点击一次
真实结论、截图确认渲染结果）。上面的结论来自直接读取真实渲染源码，
比"组件测试通过"更强，但不等于端到端人工走查。

## 六、第一个真实断点——没有找到

按计划要求"测试失败时，定位第一个具体断点，只修实际复现的问题"——
**10个测试在生产代码零改动的情况下全部通过**，只在我自己的测试脚手架上
改了两处非生产问题：①不能提前预知真实 claim_id（内嵌运行自己的
run_id），改成按声明文本内容匹配；②复用的 `_match()` 辅助函数内嵌了
另一个测试文件自己的 `RUN_ID`/`TICKER` 常量，需要对齐。两处都是**测试
工具本身的问题，不是生产代码缺陷**——第九轮建好的真实生产接线，在
真实生产入口上第一次真实跑通，没有触发需要修 claim_quality、taxonomy
或候选材料选择的情况，没有降低任何阈值。

## 七、阶段C提案：具体claim清单、真实材料、模型配置、预算

见本目录 `02_phase_c_proposal.json`——21条声明的真实 claim_id、完整
原文、已核实的真实候选来源（全部指向 `src_5bd8a947130d1949`，真实
content_hash 待运行前最终核对一致性）、冻结的 `content_support.llm.v1`
prompt、`deepseek-v4-flash` 模型、单条独立请求（batch_size=1，便于
逐条诊断）、输出token上限4096（不用已证明不足的200，理由见第九轮
报告引用的真实先例）、重试沿用Gateway默认、预算上限21次真实请求、
失败/截断如实记录不自动用同配置重试。**本轮未执行，等待付费授权**。
