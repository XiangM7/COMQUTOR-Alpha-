# T1内容核验判断方式修正：v2契约 + 21条逐条分析（2026-10-06）

本轮零新增Provider调用。单claim验证、20条真实执行、独立重算均已
结束，未重启任何诊断轮次；全部历史结果（真实请求/响应、原AMD run、
原34条清单）只读未动（哈希核对见文末）。

---

## 一、先核对：阶段C报告的统计矛盾 + PEG声明的原始分类

### 1.1 统计矛盾（已程序化核对、已定位、现予更正）

对照真实`attempt_log`/`records`重新逐条核对后，发现
`12_final_20claim_execution_and_independent_recompute_report_20261006.md`
第三节的**逐条表**里有2行与**汇总统计行**矛盾：

- 表格把`bear:54`标成"SUPPORTS→CONDITIONAL（unsupported_remainder非空
  降级）"，但真实数据是`llm_status=None, fallback=quote_or_data_not_
  found`——它从未进入过验证通过的状态，是被引用校验拒绝的（根因见下
  第三节，已修复）。
- 表格把`conservative:31`标成"SUPPORTS→CONDITIONAL"，但真实数据是
  `llm_status=BACKGROUND`，根本没有触发降级机制（BACKGROUND从一开始
  就不走SUPPORTS的降级判断）。

两处错误使表格里"SUPPORTS→CONDITIONAL"的行数变成10行，而汇总统计
（正确）说的是"9条原始SUPPORTS,8条被降级"。10≠8+1，这正是矛盾所在
——**汇总统计是对的（直接来自真实计数），逐条表是错的（人工誊写时
张冠李戴）**。已重新生成逐条表（见第四节），不再有此矛盾。

### 1.2 PEG声明（`bull:13`）的原始分类

在Round 10任何真实LLM调用之前，这条声明的状态分两段真实历史：

- **原始AMD run（`1bad76a7-...`）**：`source_link_status=TIME_INVALID`，
  `content_support_status=NOT_APPLICABLE`，
  `content_support_method=NOT_LINKED`——这是被一个**真实但与内容无关
  的产品门**挡住的（round7修复前的证据截止时间判定错误），从未进入
  内容核验流程。
- **round8的reeval run（round7时间修复后，零新增抓取的重新标注，
  Round 9/10实际使用的正确输入）**：`source_link_status=VALID`，
  `content_support_status=PENDING_REVIEW`，
  `content_support_method=UNVERIFIED_OFFLINE_CONTENT_MATCH`——这是
  **"调用未完成"**（自动启发式匹配找到了候选来源，但从未经过任何
  真实核验,人工或LLM都没有),不是"有效NONE"（没有NONE这个状态),
  也不是被内容类产品门拒绝。

**直接回答**：PEG声明在进入Round 10真实LLM核验之前,是"调用未完成"
状态，不是确定性诊断给出的分数或判断——本轮的真实SUPPORTS结果
（见第四节）是这条声明第一次真正被核验，不是用确定性分数冒充的。

---

## 二、多字段引用校验——发现并修复第二处真实缺口

构建21条逐条分析时，重放`bear:54`的真实响应发现一个新的真实bug
（不是本轮新引入的,是上一轮修复遗留的边界情况）：

**根因**：`bear:54`的真实回答是`used_location="data_snapshot.
forward_eps"`（单一路径）、`supporting_quote_or_data="forward_eps:
15.63089"`（单一、**带字段名标签**的引用，真实、可核实）。上一轮的
多字段修复只处理"2个及以上路径"的情况（`len(paths) < 2`时直接判
None,回退旧逻辑）——单一字段但带标签的引用，既不触发新的多字段
匹配，也不符合旧的`_data_field_found`（旧逻辑要求整串等于/包含于
某个裸值叶子，"forward_eps: 15.63089"≠任何真实叶子"15.63089"）——
一条真实、可核实的引用被错误拒绝。

**修复**：允许恰好1个路径的情况也走新的路径+标签+值校验，但**仅当**
这唯一一段引用本身带标签（含":"）时才启用——裸值（如"0.64"，不含
":"的常见情况）继续走原有逻辑不变,零回归。

```python
paths = [p.strip() for p in used_location.split(";") if p.strip()]
if not paths or not all(_looks_like_dotted_path(p) for p in paths):
    return None
quotes = [q.strip() for q in quote_or_data.split(";") if q.strip()]
if len(paths) == 1 and len(quotes) == 1 and ":" not in quotes[0]:
    return None  # 裸值，交给旧逻辑，零回归
if len(paths) != len(quotes):
    return False
# ...（与多字段版本相同的逐项路径+标签+值校验）
```

真实重放确认：`bear:54`的真实引用现在验证通过；裸值单字段、错误
标签单字段分别有专门测试覆盖。4个新增定向测试 + 既有15个多字段测试
全部通过（19 passed）。

---

## 三、纠正核验目标：v2契约（prompt + schema新版本，v1身份保留）

### 3.1 版本身份

`LLM_METHOD_VERSION_V1 = "content_support.llm.v1"`——永久保留，已有
v1产出的记录`schema_version`字段永远保持这个值，不回填、不升级。
`LLM_METHOD_VERSION = "content_support.llm.v2"`——新调用使用的活跃
版本。`prompt_version`/`output_schema_version`同步升版（ADR-005：
契约变了,版本必须变,防止旧缓存被误当新结果复用）。

### 3.2 新契约要求LLM明确回答（最小必要字段，扩展已有字段，未另建
大系统）

```
核心命题 core_proposition（新增，仅供审计，从不替代原claim计分）
status（不变：SUPPORTS/OPPOSES/BACKGROUND/CITATION_ONLY/CONDITIONAL/INSUFFICIENT）
support_basis（新增）：DIRECT_FACT / SEMANTIC_PARAPHRASE / DERIVED_CALCULATION / GROUNDED_INFERENCE / NONE
inference_facts（新增，DERIVED_CALCULATION/GROUNDED_INFERENCE时必须非空）
inference_assumptions（新增，仅GROUNDED_INFERENCE时必须非空——这正是它与
    DERIVED_CALCULATION的区别：后者是纯真实数字运算，不需要额外假设）
unsupported_remainder（不变）
unsupported_remainder_materiality（新增）：NONE / NON_MATERIAL / MATERIAL
```

Prompt原文已重写（保留v1全部既有安全约束：语法敏感性、
allowed_candidates专属引用、身份/词表纪律），核心修正：

- 明确"这是转述/概括/分析，不是逐字转录"——允许有依据的改写、
  真实重算、有明确假设支撑的合理推论，不再要求来源逐字写出结论。
- 同样明确：话题相似、数字存在、模型表态赞同都不等于支持——必须
  真正warrant这条声明自己的对象、方向、确定程度。
- 明确禁止把预测当已发生事实、把因果/方向/对象搞混。
- 明确主观评价词（"便宜""最大风险""必然增长"）不是自动的无关修辞
  ——是否构成核心结论必须由LLM判断并说明理由，程序代码从不用关键词
  表模拟这个判断（已用测试直接证明：`content_support_llm.py`的
  校验路径从不读取`record["claim"]`的文本内容做判断，只读结构化
  字段）。

### 3.3 report_context（新增，复用已有数据，不新抓取）

同一Agent同一报告段落里的其他声明（`source_agent_output_id`相同），
明确标注"仅用于消除指代/恢复论证，是Agent自己的转述，绝不能被当作
独立证据引用"——`_validate_response_item`从未把`report_context`加入
`candidates_by_id`，即使返回的`used_source_id`试图指向它也会被真实
候选集合校验拒绝。

### 3.4 修正"未支持部分非空就整句清空"

`_effective_content_support_status`不再对任何非空`unsupported_
remainder`一刀切降级，改为消费LLM自己披露的`unsupported_remainder_
materiality`：

```python
if status == STATUS_SUPPORTS:
    if validated.get("unsupported_remainder_materiality") == MATERIALITY_MATERIAL:
        return SUPPORT_CONDITIONAL
    return SUPPORT_SUPPORTS  # NON_MATERIAL或NONE——不再被错误降级
```

MATERIAL仍然和v1一样严格降级，没有放宽；只是不再把NON_MATERIAL也
误伤。

### 3.5 新增内部矛盾检测（Provider说SUPPORTS不能自动通过）

`_v2_structural_contradiction`——纯结构化、机械的自洽性检查（不是
语义再判断）：status=SUPPORTS但support_basis=NONE（声称支持却不
披露依据）、unsupported_remainder与materiality不一致、
DERIVED_CALCULATION/GROUNDED_INFERENCE却不给inference_facts等，
一律判定为`FALLBACK_INTERNAL_CONTRADICTION`，不静默选择有利字段。

### 3.6 计分范围保护（可计分命题不替换原claim）

`compute_verified_support_eligibility`——已用源码直接检查（非行为
巧合）确认：**从未读取**`supported_proposition`或`core_proposition`，
只读`content_support_status`/`content_support_review`。`_apply_result`
也从未触碰`record["claim"]`/`record["evidence"]`。模型纠正后的命题
（如"50日均线高于200日均线"）只会出现在`content_support_llm_detail.
supported_proposition`里，**绝不会**替换原claim用于计分或展示——已
用测试直接证明（`test_scorable_proposition_never_consumed_by_
eligibility_function`、`test_original_claim_text_and_claim_id_never_
altered`）。实质改写/新命题的情形（如claim:66的50日/200日均线混淆）
通过MATERIAL降级机制自动停在CONDITIONAL，不会自动升级——不是新增
"候选池"，是复用已验证正确的既有降级机制本身。

### 3.7 重新分类路径（已接线，本轮未发送任何真实请求触发）

新增`identify_claims_needing_alpha_reclassification(records,
alpha_matches_by_claim_id)`——纯只读诊断：找出"MATERIAL未支持余项
且已被匹配到某个Alpha"的声明，因为该Alpha的原始匹配/方向判断是基于
声明的**完整原文**算出来的，核验后暴露的"真实核心命题"可能更窄。
用合成数据证明检测机制本身正确；用真实21条数据证明**不会对缺少v2
字段的旧响应瞎猜**——真实20条执行的记录全部是v1契约产出
（`schema_version=content_support.llm.v1`，没有`unsupported_
remainder_materiality`字段），该函数对它们如实返回空列表，不编造
判断。真正触发重新分类需要调用已有的`alpha_classifier`/
`evidence_stance_llm`真实任务——本轮未调用，需要新授权。

---

## 四、21条原claim逐条分析（程序核对真实数据，不代替LLM真实判断）

**明确声明**：这21条真实响应全部是v1契约产出的（`schema_version=
content_support.llm.v1`），没有`support_basis`/`unsupported_
remainder_materiality`字段——以下分类是**我基于阅读真实rationale/
unsupported_remainder文本得出的推测性判断**，不是v2真实核验结果。
真正确认需要第五节提出的有限真实验证。

| # | claim（末段） | 最终状态 | 分类 | 理由 |
|---|---|---|---|---|
| 1 | aggressive:17 | PENDING_REVIEW(截断) | **(c)无法判断** | 8192仍截断，零响应内容可读 |
| 2 | bear:54 | PENDING_REVIEW→**已修复可验证** | **(a)确认是bug，已修复** | 真实、可核实的单字段标签引用被错误拒绝（第二节），现已修复，重放后能进入校验（仍需v2真实核验materiality） |
| 3 | conservative:24 | BACKGROUND | (b)确实缺依据 | "PEG循环论证"是推理性评论，非可证伪事实；BACKGROUND不受降级机制影响 |
| 4 | neutral:16 | BACKGROUND | (b)确实缺依据 | "不是风险管理是投降定价"是主观策略评价 |
| 5 | research_manager:8 | BACKGROUND | (b)确实缺依据 | "循环论证+3x情景剧烈de-rate"是推测性论证 |
| 6 | fundamental:28 | PENDING_REVIEW(截断) | **(c)无法判断** | 同#1 |
| 7 | conservative:31 | BACKGROUND | (b)确实缺依据 | "长久期资产+鹰派冲击压缩倍数最快"是宏观论证，非数据 |
| 8 | aggressive:42 | CONDITIONAL | **(a)可能过严** | 未支持部分是"交易策略建议"（卖covered call等），不是事实断言；真实50日均线数值本身完整支持，策略建议部分或可判NON_MATERIAL |
| 9 | conservative:48 | CONDITIONAL | (b)倾向确实缺依据 | "52周低点才是真实下行参考"是有实质内容的分析判断，不只是策略措辞 |
| 10 | fundamental:29 | CONDITIONAL | **(a)可能过严** | "PEG=0.64+假设ramp兑现→估值不贵"是教科书式的有依据推论（真实事实+明示假设），v1框架要求来源直接写出结论，可能错误地没能识别这是GROUNDED_INFERENCE |
| 11 | bear:53 | BACKGROUND | (b)确实缺依据 | 转述bull方论点+对PEG可靠性的元评论 |
| 12 | portfolio:8 | PENDING_REVIEW(INSUFFICIENT) | (b)确实缺依据 | 多情景复合判断，超出来源范围，分类合理 |
| 13 | neutral:9 | CONDITIONAL | (b)确实缺依据 | "30%回撤抹去一年涨幅"是来源不含的全新具体数字，非仅表述问题 |
| 14 | bull:61 | CONDITIONAL | (a)/(b)混合 | "PEG+假设兑现→便宜"部分类似#10是合理推论；"Q2财报说在正轨上"是来源（估值快照）本来就不含的独立事实声明，这部分缺依据是真的 |
| 15 | research_manager:7 | CONDITIONAL(模型自判) | (b)确实缺依据 | 模型自己直接给CONDITIONAL，不经降级机制，判断本身合理 |
| 16 | portfolio:12 | CONDITIONAL | (b)确实缺依据 | 对另一分析师推理质量的评价性断言，来源无法确认 |
| 17 | portfolio:38 | CONDITIONAL | **(a)可能过严** | 未支持部分是"跌破50日均线应减仓"等交易规则，用真实数字做参照，不是独立事实断言，策略框架部分或可判NON_MATERIAL |
| 18 | **bull:13**(PEG) | **SUPPORTS（真）** | 已完整支持 | 唯一真正eligible；见第一节关于其原始分类的说明 |
| 19 | fundamental:119 | CONDITIONAL | **(a)可能过严** | "高波动性+放大半导体/AI主题波动"几乎是beta=2.45的数学直接推论（beta定义本身），v1可能把这个近乎同义改写误判为需要来源另外声明 |
| 20 | fundamental:107 | PENDING_REVIEW(截断) | **(c)无法判断** | 同#1 |
| 21 | bear:66(50日/200日混淆) | CONDITIONAL | (b)确实缺依据 | 已详细分析（见round10第08号报告）：对象错误（50日均线vs股价），真实、实质性错误，v1/v2判断应一致 |

**小结**：4条确认缺依据路径没问题（BACKGROUND/INSUFFICIENT本身不受
本轮修正影响）；3条截断、无法判断；1条是确认的程序bug已修复
（`bear:54`）；**5条（`aggressive:42`/`fundamental:29`/`portfolio:38`/
`fundamental:119`，以及`bull:61`的部分内容）是本轮判断标准修正后
真正值得用真实v2调用重新核验的候选**——v1的"来源必须直接写出结论"
标准可能把合理推论/策略框架/近乎同义改写都误判为材料性缺口。

---

## 五、有限真实验证提案（本轮不执行，需新授权）

**目标**：只验证判断标准修正本身——改写、合理推论、非实质性附带
表达、实质性错误——是否按预期工作，不是要让分数变为非零。

| 项目 | 内容 |
|---|---|
| 固定材料 | 第四节标记为**(a)可能过严**的5条真实claim_id（`aggressive:42`/`fundamental:29`/`portfolio:38`/`fundamental:119`/`bull:61`），逐字沿用原claim文本、候选来源、`src_5bd8a947130d1949`及其content_hash |
| 对照材料 | `bear:66`（已知实质错误，第四节分类(b)）作为"必须仍被拒绝"的阴性对照；`bear:54`（本轮刚修复的真实单字段引用）作为引用机制回归检查 |
| 模型/prompt | `deepseek-v4-flash`，`content_support.llm.v2`（本提案冻结，不随结果调整） |
| 请求配置 | `batch_size=1`，顺序执行，`max_tokens=8192`，客户端+应用层重试均为0 |
| 请求上限 | 本次新execution全局最多**6次**真实请求（5条候选+1条阴性对照），不使用此前任何剩余额度 |
| 判定规则 | 每条最多1次，不因失败重试、不因成功追加；协议有效只证明该条在该配置下完成核验，不代表其余候选也会通过；仍截断则保存停止，不临时加大上限或改prompt |
| 产出 | 新execution目录，原21条真实结果/原run/原34条清单只读不变；逐条报告`support_basis`/`materiality`/最终状态/资格reason_code，明确区分"v2真实判断"与本报告第四节的"推测性阅读" |

---

## 六、新机制接线确认

- **正式计分/资格**：`compute_verified_support_eligibility`完全未改
  动，继续只读`content_support_status`/`content_support_review`；
  v2新增字段只存在于`content_support_llm_detail`（诊断用途），
  已用源码直接检查+测试证明从未被资格函数读取。
- **Active/Conflict**：`test_content_support_llm_production_wiring.py`
  的test_1/test_2/test_3（真实official分数贡献、真实active、真实
  admitted conflict）已更新为v2契约形状，全部真实通过，证明v2契约
  不影响既有评分/激活/冲突链路的真实接线。
- **跨Agent同源去重**：`test_duplicate_source_citation_across_two_
  claims_does_not_inflate_independent_evidence_count`在v2契约下
  仍然通过，`duplicate_group_id`机制不受影响。
- **API/Export**：已用零成本测试证明v2新字段（`core_proposition`/
  `support_basis`/`inference_facts`/`materiality`）经过真实
  `json.dumps`/`json.loads`往返后完整保留，且原claim文本与
  `supported_proposition`始终不相等、从未互相替换
  （`test_api_export_round_trip_preserves_v2_fields_and_scope`）。
  真实API（`build_research_response`）/真实Export入口
  （`get_run_export_bundle`）的完整走查，本轮未重做（上一轮
  `review-20261006T001911Z-14407742`执行已验证过，本轮代码改动
  不影响这条链路的结构，未因此重跑）。

---

## 七、测试日志

```
$ .venv/bin/python -m pytest tests/test_content_support_llm.py \
    tests/test_content_support_llm_production_wiring.py \
    tests/test_content_support_llm_phase_c_batch_size_fix.py \
    tests/test_phase_c_script_transport_level_fixed_response.py \
    tests/test_content_support_llm_multi_field_citation.py \
    tests/test_content_support_llm_v2_semantic_contract.py \
    tests/test_week2_llm.py -q
91 passed, 1 skipped in 8.03s
```

新增2个测试文件：`test_content_support_llm_v2_semantic_contract.py`
（9个，覆盖忠实改写、合理推论、预测当事实拒绝、主观评价词不走关键词
表、内部矛盾检测、计分范围保护、重新分类检测、API/Export往返）、
`test_content_support_llm_multi_field_citation.py`新增4个（单字段
标签引用修复及其阴性对照）。既有测试文件全部迁移到v2契约形状
（新增`tests/_content_support_v2_fixture_helpers.py`共享辅助函数，
避免在每个文件重复样板字段）。

---

## 八、历史保护哈希核对

原AMD run（`1bad76a7-...`）的`metadata.json`/`structured_agent_
outputs.json`/`alpha_matches.json`/`extracted_structures.json`/
`alpha_activations.json`/`conflicts.json`，reeval run的
`structured_agent_outputs.json`/`source_registry.json`，
`04_phase_c_real_results.json`，原34条清单——**全部与本轮开始前
记录的哈希一致，本轮零修改**。真实20条/1条执行结果文件、真实请求/
响应审计日志——本轮只读取，未覆盖。

---

本轮未发送任何新Provider请求，不宣称T1或John整体验收通过。第五节
提案（6次真实请求）需要你的新授权才会执行。
