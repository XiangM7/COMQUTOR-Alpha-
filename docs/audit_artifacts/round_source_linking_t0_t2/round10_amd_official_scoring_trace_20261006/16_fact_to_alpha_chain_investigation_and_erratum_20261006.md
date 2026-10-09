# 事实→分析结论→Alpha使用链核查 + 第15号报告独立勘误（2026-10-06）

本轮零新增Provider请求、零代码改动生产行为、零重新计算。全部结论
基于读取现有真实代码、真实冻结数据（`alpha_matches.json`/
`llm_semantic_calls.jsonl`/真实execution产物）直接得出，不猜测、
不用旧代码快照代替当前实现。所有离线脚本均为只读分析（`json.loads`
读取已有文件 + 直接调用`is_claim_eligible`/
`compute_verified_support_eligibility`等真实函数本身，从未构造或
调用任何Gateway/client对象），不存在发出真实请求的代码路径——
已逐一核实每段脚本不包含`invoke`/`requests`/`httpx`等网络调用。
执行前后哈希核对一致（见文末）。

---

## 一、对`15_v2_limited_verification_and_final_recompute_report_20261006.md`的独立勘误

**不覆盖原文件，以下是需要更正的具体条目：**

1. **"内容核验通过3/6"的表述需要拆分**：原报告第四节把
   aggressive:42/fundamental:119/bull:61计为"3条完整回答"，但
   **三条最终状态均为CONDITIONAL，不是"充分支持"**。应分列：
   响应完整=3/6；协议/引用校验有效=3/6（与响应完整数相同，因为
   这3条都通过了校验,没有被拒绝)；**最终SUPPORTS=0/6**（3条raw
   verdict都是SUPPORTS但全部因MATERIAL被降级)；**正式资格通过
   （eligible=True）=0/6**。原报告第四节的表格本身已经如实写了
   "最终状态：CONDITIONAL"，但正文叙述"3条完整回答"容易被误读为
   "3条核验通过且构成支持"，此处明确澄清。

2. **"材料不足0条"需要更具体**：原报告第十节写"材料不足:0条——
   候选来源真实存在且内容真实可核实"。这个表述把"来源存在"和
   "材料足以支持核心结论"混为一谈。更准确的拆分：
   - 来源存在：6/6（`src_5bd8a947130d1949`真实存在）。
   - 材料包含与声明相关的真实事实：6/6（50日均线、beta、PEG等
     数值确实在候选材料里)。
   - **材料足以支持声明的核心结论：0/6**——例如bull:61声明"Q2财报
     显示在正轨上"，但候选材料是一份**估值快照**，根本不包含任何
     Q2财报相关内容，这是真实的材料范围缺口，不是"材料不足"
     一句话能概括的（材料存在,但范围不覆盖声明引用的那类事实）。
     aggressive:42的"策略建议是否合理"同样不是这份快照能回答的
     问题类型。应记录为"候选材料的范围/类型与声明引用的事实类型
     不匹配"，不是笼统的"材料不足"。

3. **3条截断确认保持"本次无有效判断"，不是"内容不支持"**：
   原报告表格已正确标注为`PENDING_REVIEW`/`provider_error`，第十节
   正文也正确单列了"核验失败（截断）"，没有把截断和实质不支持混在
   一起——**此项核对后确认原报告表述正确，无需更正**。

4. **"v2.1也判CONDITIONAL"不能单独证明v1过严已被排除——已在原报告
   明确限定措辞，但补充范围说明**：原报告写"真实v2.1判断...独立
   得出相同的材料性缺口判断，证明v1的'过严'不是这3条的真实阻塞
   原因"——这个结论**仅适用于这3条具体声明**，样本量为3，不能
   推广为"v1从未过严"的普遍结论，原报告没有做这个推广，此处确认
   范围限定没有问题。

5. **独立重算需要标注为混合版本重算——已在原报告第5.2节做了逐条
   execution/版本表格，确认准确**，此项核对后无需更正。

6. **字节一致 vs 规范化语义一致需要统一表述**：核对第15号报告，
   发现`conflicts.json`/`structured_agent_outputs.json`/
   `alpha_activations.json`(ZIP vs disk)使用"逐字节相同"是准确的
   （直接`==`比较整个JSON对象，Python字典比较在键值完全一致时
   等价于内容相同，此处表述不是真正的"逐字节"但语义准确，可接受）；
   原始run vs 新recompute的`alpha_activations.json`比较明确使用了
   "已用忽略run_id/evidence_fact_group_id/列表顺序的规范化比较"——
   这个表述本身已经区分清楚，**无需更正**。

**勘误小结**：真正需要更正的是第1、2条——"3条完整回答"和"材料
不足0条"这两处表述过于笼统，容易被理解为比真实情况更积极，本勘误
已在上面给出更准确的拆分表述。

---

## 二、七条声明的真实Alpha分类状态（代码+数据直接证据，非诊断推断）

**先确认当前真实代码**（`comqutor_alpha/structure_engine/alpha_mapper.
py`第770-813行，直接读取）：关键词/因子评分
（`candidates`/`eligible_candidates`/`top`/`second`/
`deterministic_top_alpha`/`deterministic_match_status`）**明确是
诊断/反事实字段，从未作为正式匹配依据**——代码自己的注释写明
"captured here as a diagnostic/counterfactual ONLY -- it never becomes
the semantic result, including on any LLM operational failure"。
正式匹配结果**唯一**来自`_classify_alpha_with_llm`这个真实LLM调用
（`alpha_match_method="llm"`时），或在该调用不可用时记为
`alpha_match_method="llm_unavailable"`（附真实`alpha_match_
fallback_reason`）。额外还有2个A001专属的否决门（本轮全部7条
`alpha_specific_invalidation_override=False`，`alpha_positive_
requirement_override=False`，均未触发，且这2个门只对A001生效，
与本轮A304无关）。

**交叉核实**：不只读`alpha_matches.json`的摘要字段，直接在真实
`llm_semantic_calls.jsonl`（536条alpha_classifier记录之一）里按
claim原文逐条定位对应的真实call记录，核对`call_id`/
`provider_status`/`validation_status`/`validated_output`。

| 声明 | matched_alpha | 真实call_id（末12位） | provider_status | validated_output | 分类 |
|---|---|---|---|---|---|
| aggressive:42 | None | ...35165fb9be7b | success | `{"decision":"none","selected_alpha_id":null}` | **①模型完成并明确返回NONE** |
| fundamental:29 | **A304** | ...c8d56ac0fad7 | success | `{"decision":"select","selected_alpha_id":"A304"}` | 已匹配（非0分类之一） |
| **portfolio:38** | None | ...ad45946b01ca | **budget_exhausted** | 无（`validation_status=not_run`） | **④预算拒绝，真实未发送**（call_sequence=536，整个run的alpha_classifier预算在此耗尽，`error_code=WEEK2_LLM_CALL_BUDGET_EXHAUSTED`，`fallback_used=True`） |
| fundamental:119 | None | ...b75b0078b76f | success | `{"decision":"none","selected_alpha_id":null}` | **①模型完成并明确返回NONE** |
| bull:61 | **A304** | ...bd86c1a44632 | success | `{"decision":"select","selected_alpha_id":"A304"}` | 已匹配（非0分类之一） |
| bear:66 | None | ...0fa0dc79bd1b | success | `{"decision":"none","selected_alpha_id":null}` | **①模型完成并明确返回NONE** |
| **bull:13** | None | ...e2463f3fc81c | success | `{"decision":"none","selected_alpha_id":null}` | **①模型完成并明确返回NONE** |

**直接回答bull:13的无匹配属于哪一种**：属于**第①类**——真实LLM
分类调用成功完成（`provider_status=success`），模型明确返回
`decision=none`（"But look at the PEG of 0.64."这条声明过于
脱离上下文，模型判定没有任何canonical Alpha真正适用）。**不是**
调用失败、不是预算拒绝、不是产品门否决。

**重要更正（相对本轮之前所有报告）**：`portfolio:38`此前被我
笼统归入"Alpha分类已真实执行完毕(评分为0)"——**这是错误的**。
真实call记录证明它是**第④类（预算拒绝，从未真正发送）**，不是
"执行后判定不匹配"。这是本轮核查发现的、此前报告里存在的一处
真实分类错误，现予更正。

---

## 三、事实→分析结论→Alpha 实际使用链（逐条）

### aggressive:42
- **原claim**："But I'd argue the smarter aggressive play is to hold the full position, sell covered calls into the October FOMC vol spike to monetize the event risk, and add on any pullback toward the 50-day average of $513.53."
- **候选来源可定位字段**：`data_snapshot.fifty_day_average=513.5342`（真实存在）。
- **已保存响应认可的支持部分**：`supported_proposition="AMD's 50-day average is $513.53."`（`support_basis=DIRECT_FACT`）。
- **未支持部分及materiality**："持有满仓/卖covered call/逢低加仓"的策略建议，`materiality=MATERIAL`——模型rationale明确：这部分是claim的核心行动建议，候选材料（一份估值快照）根本不包含任何交易策略相关内容。
- **是否持久化**：是，`content_support_llm_detail`已写入`structured_agent_outputs.json`（本轮recompute execution产物里可读）。
- **是否进入Evidence Fact**：**否**——`matched_alpha=None`（真实LLM分类返回none），Evidence Fact Index按Alpha分组，没有Alpha就没有分组入口，`evidence_facts.json`里零命中（已直接搜索确认）。
- **Alpha匹配/stance针对哪个命题**：`_classify_alpha_with_llm`读取的是`record["claim"]`**完整原文**（含策略建议部分），不是`supported_proposition`。
- **采用/保留/降级/排除的生产函数**：`_effective_content_support_status`（降级为CONDITIONAL）→`compute_verified_support_eligibility`（判定不eligible，reason=SUPPORT_STATUS_NOT_RESOLVED）→因`matched_alpha=None`，`activation_scorer_v2`/`evidence_fact_index`均不处理此claim。

### fundamental:119
- **原claim**："Beta of 2.45 — this is a high-volatility instrument that will amplify any broad semiconductor or AI-theme [moves]"
- **候选来源可定位字段**：`data_snapshot.beta=2.454`（真实存在）。
- **已保存响应认可的支持部分**：`supported_proposition="Beta of 2.45 — this is a high-volatility instrument"`，**真实support_basis=GROUNDED_INFERENCE**，`inference_facts=["beta=2.454来自data_snapshot.beta","beta字段单位是ratio"]`，`inference_assumptions=["假设beta比率高于1代表相对大盘的高波动性"]`——v2.1机制在此真实生效,不是形同虚设。
- **未支持部分及materiality**："会放大半导体/AI主题的任何波动"，`materiality=MATERIAL`——这是一个独立的、主题特定的因果外推，模型明确指出候选材料不建立这层因果关系。
- **是否持久化**：是。
- **是否进入Evidence Fact**：**否**——`matched_alpha=None`（真实LLM分类返回none），同aggressive:42，`evidence_facts.json`零命中。
- **采用/保留/降级/排除**：同上链路，`CONDITIONAL`→不eligible→无Alpha可归属。

### bull:61
- **原claim**："PEG of 0.64 — cheap if the forward ramp is delivered, and the Q2 print says it's on track."
- **候选来源可定位字段**：`data_snapshot.peg_ratio=0.64`（真实存在）。
- **已保存响应认可的支持部分**：`supported_proposition="PEG of 0.64"`，`support_basis=DIRECT_FACT`。
- **未支持部分及materiality**："如果ramp兑现就便宜""Q2财报说在正轨上"，`materiality=MATERIAL`——模型rationale明确区分两类缺口：(a)"便宜"是一个估值结论，候选材料（单一时点快照）不包含"delivered"这个时间维度的判断；(b)"Q2财报"是一个**完全独立的事实声明**，候选材料类型（估值快照）根本不覆盖财报内容,不是同一类材料能回应的。
- **是否持久化**：是。
- **是否进入Evidence Fact**：**是**——这是本轮最重要的真实发现。`evidence_facts.json`的`groups[31]`真实包含这条claim（`representative_claim_id`/`member_claim_ids`均为本claim），`supporting_alpha_ids=["A304"]`，`alpha_stances.A304.representative_stance="supports_alpha"`，`requires_manual_review=true`。**真实content_support_status=CONDITIONAL的claim,其Evidence Fact分组和stance归属并未被整体抹除**——`is_claim_eligible`（`claim_quality.py`第725行）对`quality=ANALYTICAL`的claim**无条件**返回True，完全不检查`content_support_status`，这是两个独立的门。
- **是否与分析结论建立明确关系**：是,在RAW评分层面——真实`alpha_activations.json`确认：`v1`视图A304包含此claim,分数99.33,status=`regime_level`;`v2`（raw）视图同样包含,分数45.83,status=`watch`;**唯一在`v2_verified`（官方视图）里被排除**（claim_ids不含它,score=0.0,status=`candidate`）。
- **采用/保留/降级/排除的生产函数**：`is_claim_eligible`（保留进RAW评分+Evidence Fact）→`_run_week3_graph_pipeline`内部的verified-gate逻辑调用`compute_verified_support_eligibility`（CONDITIONAL不满足`_RESOLVED_SUPPORT_STATUSES`，具体排除点是`score_alpha_activations_v2`为`v2_verified`视图单独过滤输入claim列表时）→从官方视图的`claim_ids`中移除。

### 3条截断声明（fundamental:29/portfolio:38/bear:66）
- 均为`provider_error`/`finish_reason=length`，**本次无有效LLM判断可读**——未生成`content_support_llm_detail`，`supported_proposition`/`unsupported_remainder`均不存在。记为"本次无有效判断"，不写"内容不支持"。
- `fundamental:29`真实Alpha已匹配A304（见第二节），但因**assertion_status=negated**（与content_support_status完全独立的字段，由`structured_output_adapter.py`的断言状态分类器产出，怀疑与claim原文本身的让步/条件句式有关，本轮未深入这个分类器本身）被`evidence_facts.json`排除；真实`alpha_activations.json`显示它在legacy `v1`视图里仍被计入（`claim_ids`含有），但在`v2`/`v2_verified`均被排除——**这个排除发生在v2架构本身（与verified-gate无关），不是content_support_status造成的**。
- `bear:66`：唯一真实回答（2026-10-05原始执行）当时因多字段引用bug被拒绝；本轮重试截断；离线重放（第七节）确认其v2.1状态**真实、仍未解决**。

### bull:13（已知eligible，作为对照）
- **已持久化**，`content_support_status=SUPPORTS`，真实eligible=True。
- `matched_alpha=None`——真实LLM分类call（`e2463f3fc81c`）明确返回`decision=none`（第①类，非产品门否决、非预算拒绝）。
- **未进入Evidence Fact**（零命中，同原因：无Alpha可归属）。
- 唯一真正"内容核验通过"的声明,止步于Alpha分类阶段——这个阶段本身是真实、完整执行过的,不是"未执行"或"被否决",是模型真实判断"这条声明本身不包含材料上足以单独关联到任何canonical Alpha的内容"（原文"But look at the PEG of 0.64."脱离上下文,仅引用一个数字，没有因子/方向信号）。

---

## 四、核心问题的直接回答

1. **原声明中的真实事实是否被保存？** 是，持久化在`content_support_
   llm_detail`里；对于`bull:61`（唯一真实匹配到Alpha的CONDITIONAL
   claim），其事实/stance进一步被保存进Evidence Fact Index并计入
   RAW（v1/v2）activation评分——不是"随CONDITIONAL整体排除"。
2. **若保留，能否作为分析结论的输入？** 能，但仅在RAW/legacy视图里
   （`v1`/`v2`），且已经真的在起作用（把A304在RAW视图推到
   `regime_level`/`watch`）。**官方（`v2_verified`）视图不采用**——
   这是`compute_verified_support_eligibility`这个验证门有意、正确
   的设计行为,不是消费链路缺陷。
3. **若不能（指官方视图），具体缺少什么？** 不是材料、不是引用
   关系、不是生产消费入口的问题——消费入口本身工作正常（RAW视图
   已证明读得到）。缺的是"claim的核心结论本身缺乏真实依据"这个
   真实情况本身：bull:61的"便宜"结论和"Q2财报"声明，材料类型
   （单时点估值快照）结构性地覆盖不到。
4. **即便能用这些输入，是否仍不足以证明当前分析结论？** 是,
   不足。PEG=0.64本身只是一个比率,不能单独证明"便宜"（需要一个
   明确的估值基准/同业比较/历史分位数等bull:61原文没有提供的
   比较对象）,也不能证明任何Q2财报相关的具体业绩表现（需要
   财报本身,不是快照）。
5. **事实本身没有Alpha含义时，系统是否正确保留为上下文？** 是——
   `aggressive:42`/`fundamental:119`/`bear:66`/`bull:13`的
   matched_alpha=None都来自真实LLM分类器的明确none判断，不是
   系统错误地把无Alpha含义的事实硬塞进某个Alpha；`bull:61`/
   `fundamental:29`确实被分类器判定与A304相关（真实select
   决策），系统也没有因为内容只部分支持就撤销这个Alpha归属判断
   本身（Alpha归属和内容验证是两个独立、正确分离的判断轴）。

---

## 五、历史版本重放能力的真实限制

`bear:66`的完整版本谱系：
1. **原v1回答**（2026-10-05，execution `phase-c-20261005T233842Z-1b2550ac`磁盘记录）：`PENDING_REVIEW`/`quote_or_data_not_found`——当时的多字段引用bug导致。
2. **本次v2.1截断**（本轮execution `phase-c-20261006T034452Z-1ab992d0`）：`PENDING_REVIEW`/`provider_error`——8192仍不够。
3. **独立重算实际采用的记录**：对原始真实回答做了**零成本离线重放**（复用`_process_batch`，未新增Provider调用），**真实结果是`FALLBACK_INTERNAL_CONTRADICTION`**——因为现在的`_process_batch`已经同时跑v2.1结构自洽检查，旧v1回答缺`support_basis`等必需字段，被正确拒绝,不是"证明了CONDITIONAL"。

**当前代码的真实限制**：`_validate_response_item`把"引用真实性校验"
（多字段修复相关）和"v2.1结构自洽检查"耦合在**同一个函数**里，
没有一个"只用修复后的引用校验、不触发v2.1新增必填字段检查"的
中间版本入口——所以**无法零成本、不编造任何字段地重建出"仅引用
修复、不含v2.1新字段"条件下bear:66会得到什么结果**。已尝试过的
唯一"CONDITIONAL"演示（上上轮的单元测试）是**人工附加了v2字段
后的重建**，不是模型自己的判断，不能当作历史记录。

**最小兼容方案（本轮不实现，仅提出）**：在`content_support_llm.py`
里新增一个独立、明确标注"仅诊断用途"的函数（如
`_validate_response_item_citation_only`），只复用`_multi_field_
citation_valid`/`_quote_found_in_excerpt`/`_data_field_found`等
引用相关函数,不运行`_v2_structural_contradiction`,供历史版本
重放诊断专用,不进入任何生产调用路径。这是新增一个明确隔离的诊断
函数，不是修改/删除现有生产校验、不是伪造字段。

---

## 六、具体断点清单（代码位置+真实反例，优先级排序）

### 断点1：`portfolio:38`代表的Alpha分类预算真实耗尽
- **位置**：原始run执行时`alpha_classifier`任务的`max_calls`预算
  在call_sequence=536处耗尽（`comqutor_alpha/structure_engine/
  week2_llm.py`的`_reserve_call()`机制）。
- **真实反例**：`llm_semantic_calls.jsonl`里`call_id=...ad45946b01ca`
  记录`provider_status=budget_exhausted, validation_status=not_run`。
- **性质**：不是实现缺陷,是真实、当时的预算配置不足以覆盖这个
  run的全部536+条claim。
- **影响**：`portfolio:38`的真实Alpha归属**至今未知**（不是
  "no_match",是"从未真正判断过"）。

### 断点2：`bear:66`的v2.1真实状态仍未确定
- **位置**：两次真实尝试（原始2026-10-05 + 本轮2026-10-06）均因
  不同原因（引用bug/截断）未能产出可用v2.1判断。
- **真实反例**：见第五节完整版本谱系。
- **性质**：不是实现缺陷,是这条声明本身（可能涉及更复杂的
  推理链:50日均线vs股价混淆+beta+convexity概念）对8192 token预算
  的真实压力,具体原因未深挖。

### 断点3：历史版本重放入口缺失（见第五节）
- **位置**：`comqutor_alpha/structure_engine/content_support_llm.
  py`的`_validate_response_item`。
- **性质**：设计限制,不是bug——当初设计时没有预留"仅citation、
  不含v2.1结构检查"的中间形态。

### 断点4（非缺陷，澄清项）：Evidence Fact/RAW评分与官方视图的
真实分离机制本身工作正常
- 不是断点,是本轮确认的一个**正确工作的真实机制**（见第三、四节
  bull:61的例子）,列在此处是为了明确：**不需要修复**，如果未来
  误以为"CONDITIONAL claim完全消失"而去"修复"这个分离机制,会
  是真正的回归。

---

## 七、最小下一步方案（仅提出，本轮不实现）

### 方案A：新增历史版本专用重放诊断函数（对应断点3）
- **具体问题**：无法零成本证明"仅citation修复"条件下的历史结果。
- **缺口类型**：设计限制（缺少隔离入口），非材料缺口、非实现缺陷。
- **最小修改位置**：`content_support_llm.py`新增一个独立函数，
  不改动`_validate_response_item`/`_v2_structural_contradiction`
  本身。
- **可复用模块**：`_multi_field_citation_valid`/
  `_quote_found_in_excerpt`/`_data_field_found`（全部已存在,直接
  调用)。
- **预期解决的断点**：让"仅citation层面是否通过"这个历史问题可以
  零成本、不编造字段地单独回答。
- **仍不能保证的结果**：不能告诉我们模型在v2.1契约下**真的会**
  说什么（那仍需要一次新的真实v2.1调用）——这个诊断函数只能回答
  "citation本身在技术上能否核实",不能替代materiality判断。
- **零调用验证方式**：用已保存的真实历史响应(`exec1`的真实
  response body)直接单元测试这个新函数,断言结果。
- **是否需要新语义调用**：不需要。

### 方案B：对`portfolio:38`的真实Alpha归属，需要明确新授权
- **具体问题**：真实归属从未被判断过（预算耗尽,非拒绝)。
- **缺口类型**：记录不足（从未执行），不是实现缺陷。
- **最小方案**：不是"再跑几条"——而是明确提出：若需要知道
  `portfolio:38`的真实Alpha归属,需要**一次新的、独立计费的
  alpha_classifier真实调用**（复用已有、未改动的`_classify_
  alpha_with_llm`函数本身，只是单独为这一条claim发起),本轮不
  执行,需单独授权与单独的预算上限。
- **仍不能保证的结果**：不能保证结果是"select"而非"none"。

### 方案C：对bull:61/fundamental:119类"部分支持"声明，若要让RAW
视图里已经存在的真实证据贡献官方分数，需要的不是代码修改
- **具体问题**：这2条的核心可验证事实(50日均线/PEG/beta)真实、
  已保存、已进入RAW评分，官方视图因为声明整体CONDITIONAL而不采用。
- **缺口类型**：**不是实现缺陷,是真实、具体的证据缺口**——
  bull:61需要一个真实的"ramp是否已交付"的判断依据和一份真实Q2
  财报引用(不是估值快照);aggressive:42需要的不是"数据"而是一个
  完全不同类型的判断(策略合理性,这类内容本来就不是content-support
  这个机制设计要验证的对象)。
- **最小方案**：不提出代码修改——如实列出每条缺的具体输入类型
  (已如上),是否值得专门抓取这类材料是产品决策,不是本轮工程范围。
- **零调用验证方式**：不适用(无代码改动)。

### 遗留证明状态更新
- **正式active fixture**：仍未完成，`test_2`证明的是`candidate`
  不是`active`，本轮未扩展实现，维持"未完成"标注。
- **自动去重生成端**：仍未核实，维持"未执行"标注。

---

## 八、输入及历史产物哈希核对

执行前后对比`outputs/runs/1bad76a7-...`全部文件
（`metadata.json`/`structured_agent_outputs.json`/
`alpha_matches.json`/`llm_semantic_calls.jsonl`）、reeval run、
`04_phase_c_real_results.json`、原34条清单——**全部一致，本轮
零修改**（纯读取分析,未执行任何写入操作到这些路径)。

---

## 九、最终直接回答

- **当前零分中，哪些来自调用未完成？** `portfolio:38`的Alpha
  归属（预算耗尽,真实未判断)；`bear:66`的v2.1内容核验状态
  （两次真实尝试均未产出可用判断)；`fundamental:29`/
  `portfolio:38`的本轮v2.1重试本身（截断)。
- **哪些来自材料确实不能支持关键结论？** `aggressive:42`的策略
  建议部分、`fundamental:119`的"放大AI主题"因果外推、`bull:61`的
  "便宜"估值结论与独立Q2财报声明——均为真实、已用具体rationale
  确认的材料范围缺口，不是模型误判。
- **哪些来自Alpha分类（而非内容核验）？** `aggressive:42`/
  `fundamental:119`/`bear:66`/`bull:13`——四条真实LLM分类器
  明确返回none，即使内容核验满分也不会贡献任何Alpha分数,因为
  模型判定它们本就不构成对任何canonical Alpha的实质性证据。
- **哪些来自真实事实未能进入或服务于分析链？** 没有——本轮核实
  确认,真实支持的核心事实（如`bull:61`的PEG值）**确实进入了**
  Evidence Fact Index和RAW评分链条，只是官方视图按设计不采用
  CONDITIONAL声明。不存在"消费入口缺失"这个问题。
- **下一步最先修哪一个具体断点，为什么？** 如果目标是"让更多真实
  分析性声明有机会贡献官方分数"，最值得先处理的不是本轮发现的
  任何一个"缺陷"（因为本轮没有发现真正的生产链路缺陷），而是
  **方案A**（历史版本重放诊断入口)——这是本轮唯一确认的、纯
  工程性、零材料依赖、零新调用就能补上的真实缺口,优先级最高
  因为成本最低、不依赖任何新的产品/材料决策。`portfolio:38`的
  预算问题和bull:61/fundamental:119的材料类型缺口,都需要你先做
  产品决策（是否授权新调用/是否值得抓取新材料类型）,不是纯工程
  问题,排在方案A之后。

本轮调查到此停止，不追加付费调用，不重算已经算过的零分结果，
不宣称T1或John整体验收通过。
