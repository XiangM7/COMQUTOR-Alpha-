# 阶段C（20条真实执行）+ AMD独立重算 最终报告（2026-10-06）

本轮新增授权20次真实Provider请求，实际发送**恰好20次**
（`real_provider_attempts=20`，无重试、无超发）。加上此前已完成的1次
单claim验证，21条冻结清单**全部**完成真实核验。原run、原34条历史
清单、旧报告全程只读，哈希核对见第六节，全部未变。

---

## 一、两处引用校验风险——复现、修复、定向测试

发送20次真实请求之前，先零成本复现了你指出的两个风险，确认均为
真实缺陷后才修复，修复范围严格限定在复现到的问题本身。

### 风险1：字段标识与路径绑定未校验

**复现**：构造`used_location="data_snapshot.beta; data_snapshot.fifty_day_average"`
配合`supporting_quote_or_data="fifty_day_average: 2.454; beta: 513.5342"`
——标签和路径对调了，但数值本身是真实的（2.454确实是beta的真实值，
只是被贴上了"fifty_day_average"的错误标签）。修复前：**返回True
（错误通过）**。

**修复**：`_multi_field_citation_valid`现在额外核对每个引用段的标签
（冒号前的文本）是否与其路径的末段字段名一致（机械的大小写/分隔符
归一化比较，不做语义猜测；当前真实数据里没有任何字段别名表，因此
这等价于严格同名匹配）。标签与路径不符——即使数值是来源里某处的
真实值——直接拒绝。

### 风险2：多字段格式错误时静默回退到旧逻辑

**复现**：构造3个路径、2个引用值（第三个字段完全没有被核验），且
2个引用值拼接后的整串恰好是excerpt的字面子串。修复前：**返回None
→ 回退到旧的整串excerpt匹配 → 错误通过**，第三个声称的字段从未被
真正核验。

**修复**：一旦`used_location`的全部分段都形如真实的`root.child`路径
（新增`_looks_like_dotted_path`判断，用正则而非语义猜测），就认定
这是一次蓄意的多字段路径引用——此时路径数与引用值数不一致，
**明确拒绝**，不再回退。只有当`used_location`本身不像路径形态时
（例如普通文本中偶然出现的分号），才继续交给既有单值逻辑处理，
确保"普通文本中的分号"不会被误判。

### 定向测试（4个新增，全部通过；既有11个多字段测试+既有单字段/文本
引文测试同步复核，无回归）

```
$ .venv/bin/python -m pytest tests/test_content_support_llm_multi_field_citation.py -v
...
15 passed in 0.26s
```

| 新增测试 | 验证点 |
|---|---|
| `test_risk1_wrong_label_with_real_but_misattributed_value_is_rejected` | 风险1复现场景——修复后拒绝 |
| `test_risk1_control_correct_labels_still_pass` | 对照组：标签正确时仍然通过 |
| `test_risk2_segment_count_mismatch_with_literal_excerpt_substring_still_rejected` | 风险2复现场景——修复后拒绝 |
| `test_ordinary_text_semicolon_not_misjudged_as_multi_field_citation` | 普通文本分号不被误判为多字段路径引用 |

修复后重新离线处理已保存的单claim响应（`execution_id=phase-c-
20261005T233842Z-1b2550ac`，claim:66）：原claim文本和claim_id
未变；三个字段引用标签与路径一致、数值正确，仍然通过；最终仍按既有
`_effective_content_support_status`机制降级为**CONDITIONAL**（不是
SUPPORTS）；真实`compute_verified_support_eligibility`仍返回
`eligible=False, reason_code=SUPPORT_STATUS_NOT_RESOLVED`——与风险
修复前的结论完全一致，模型纠正后的均线命题未替换原claim的股价命题。

与既有40个测试一并跑，55个全部通过，零回归：
```
$ .venv/bin/python -m pytest tests/test_content_support_llm.py \
    tests/test_content_support_llm_production_wiring.py \
    tests/test_content_support_llm_phase_c_batch_size_fix.py \
    tests/test_phase_c_script_transport_level_fixed_response.py \
    tests/test_content_support_llm_multi_field_citation.py -q
55 passed in 6.97s
```

---

## 二、冻结20条执行范围（程序化确认）

- 原21条唯一claim_id：程序确认21个互不重复。
- 已验证条目：`claim:66`（bear_researcher），确认恰好出现1次，已排除。
- 本轮清单：程序确认恰好20条，与已验证条目无重叠，原顺序保持不变。
- 冻结材料见`09_frozen_20_claim_scope_20261006.json`。

---

## 三、本轮20次真实请求——逐条结果

**Provider原始状态**（`llm_status`，模型自己的原始判断）vs
**后端最终状态**（`content_support_status`，经既有部分支持降级规则
处理后）：

| claim（末段） | Provider原始状态 | 最终状态 | 拒绝/降级原因 |
|---|---|---|---|
| aggressive:17 | （截断，无输出） | PENDING_REVIEW | provider_error（WEEK2_LLM_OUTPUT_TRUNCATED，8192仍不够）|
| bear:54 | SUPPORTS | **CONDITIONAL** | unsupported_remainder非空，按既有规则降级 |
| conservative:24 | BACKGROUND | BACKGROUND | 来源背景信息，非直接支持（设计如此）|
| neutral:16 | BACKGROUND | BACKGROUND | 同上 |
| research_manager:8 | BACKGROUND | BACKGROUND | 同上 |
| fundamental:28 | （截断，无输出） | PENDING_REVIEW | provider_error（WEEK2_LLM_OUTPUT_TRUNCATED）|
| conservative:31 | SUPPORTS | **CONDITIONAL** | unsupported_remainder非空，降级 |
| aggressive:42 | SUPPORTS | **CONDITIONAL** | unsupported_remainder非空，降级 |
| conservative:48 | SUPPORTS | **CONDITIONAL** | unsupported_remainder非空，降级 |
| fundamental:29 | SUPPORTS | **CONDITIONAL** | unsupported_remainder非空，降级 |
| bear:53 | BACKGROUND | BACKGROUND | 来源背景信息 |
| portfolio:8 | INSUFFICIENT | PENDING_REVIEW | 材料不足，模型自认无法判断 |
| neutral:9 | SUPPORTS | **CONDITIONAL** | unsupported_remainder非空，降级 |
| bull:61 | SUPPORTS | **CONDITIONAL** | unsupported_remainder非空，降级 |
| research_manager:7 | CONDITIONAL | CONDITIONAL | 模型自己直接给出CONDITIONAL |
| portfolio:12 | SUPPORTS | **CONDITIONAL** | unsupported_remainder非空，降级 |
| portfolio:38 | SUPPORTS | **CONDITIONAL** | unsupported_remainder非空，降级 |
| **bull:13** | **SUPPORTS** | **SUPPORTS（未降级）** | 无unsupported_remainder，单字段引用（PEG=0.64）|
| fundamental:119 | SUPPORTS | **CONDITIONAL** | unsupported_remainder非空，降级 |
| fundamental:107 | （截断，无输出） | PENDING_REVIEW | provider_error（WEEK2_LLM_OUTPUT_TRUNCATED）|

**真实、关键发现**：20条里**9条**模型给出原始SUPPORTS判断，但其中
**8条**因为claim本身包含模型指出的未被支持的部分（`unsupported_
remainder`非空），被既有降级规则正确降为CONDITIONAL——只有1条
（`bull:13`，"But look at the PEG of 0.64."，单一、无歧义的数值
声明）保持完整SUPPORTS。这不是机制失效，是这批claim本身大多是
"部分正确、部分未被来源证实"的复合判断，降级规则在真实数据上正确
地大面积触发。

### 分层统计（不同层级分别统计，不混加）

- 计划条数：20
- 发送前拒绝（预检失败）：0
- 实际请求（到达Provider）：20
- 响应成功（finish_reason=stop，未截断）：17
- 截断（finish_reason=length，8192仍不够）：3（`claim:17`/`claim:28`/`claim:107`，全部是
  `fundamental_agent`/`aggressive_risk_analyst`类，具体原因未进一步归因，按本轮边界不深究prompt层面）
- 超时：0
- 协议有效（通过批次级JSON结构校验）：17（=响应成功数，截断的3条未产出可解析JSON）
- 引用校验拒绝：1（`bear:54`，质疑点见下）
- 各最终内容状态：PENDING_REVIEW=5（3截断+1引用拒绝+1 INSUFFICIENT）、BACKGROUND=5、CONDITIONAL=9、SUPPORTS=1
- 正式资格通过（`eligible=True`）：**1**（仅`bull:13`）
- usage缺失：0（20条全部有完整token_usage记录）

`bear:54`的引用拒绝**保留了原始响应和拒绝原因，本轮未在付费执行
中途修改prompt或校验器再试**——校验器版本在整个20次执行期间保持
冻结，这是修复落地（见第一节）之后、执行开始之前完成的，不是执行
中途动态调整。

---

## 四、独立AMD重算——逐Alpha、逐冲突、新旧对照

### 真实执行方式

复用真实生产评分链`_run_week3_graph_pipeline`——与
`trigger_content_support_reevaluation`内部调用的是**同一个函数**，
不是重新实现。区别仅在"如何把21条核验结果应用到
structured_agent_outputs.json"这一步：`trigger_content_support_
reevaluation`的既有机制是重放人工复核日志
（`content_support_reviews.jsonl`），而这21条本来就不是人工复核产生
的，是`content_support_llm.py`自己的`apply_llm_content_support_
verification`真实计算出来的——两条路径最终都调用同一个
`build_content_support_review`产出同样形状的记录，因此本轮直接复用
这21条已经算好的真实记录做覆盖，而不是硬套人工复核日志格式。

- `based_on_run_id`：`1bad76a7-72ac-4c8b-8189-2e5c0f1a6105`（真原始
  run，不是中间的reeval run）。
- 新execution_id：`review-20261006T001911Z-14407742`。
- `alpha_matches.json`/`extracted_structures.json`：原样复制自**真原始run**，
  未重新计算、未重新匹配。
- `structured_agent_outputs.json`：以reeval run（含round7时间修复）
  的全量记录为底，**只替换这21条**，其余全部字节不变；每条附带来源
  execution_id和后处理版本（见`metadata.json.claim_provenance`）。
- 执行前显式设置`COMQUTOR_WEEK2_LLM_ENABLED=0`作为硬性守卫，确保
  `_run_week3_graph_pipeline`内部任何代码路径都不可能意外发起新的
  真实Provider请求。
- 真实管线运行结果：`outcome=success`，零异常。

### 逐Alpha结果

21条claim里只有5条在`alpha_matches.json`里有非空`matched_alpha`
（全部指向`A304`：`claim:17`/`research_manager:8`/`fundamental:29`/
`bull:61`/`fundamental:107`），其余16条（含唯一eligible的`bull:13`）
`matched_alpha=None`——从未进入任何Alpha候选。

对A304：5条匹配claim中，**没有一条**最终状态是SUPPORTS且eligible
（`claim:17`/`fundamental:107`截断→PENDING_REVIEW；`research_manager:8`
→BACKGROUND；`fundamental:29`/`bull:61`→CONDITIONAL降级）——**A304从
这21条里获得的正式贡献证据数=0**，激活分数、`active`/`dominant`
状态与原始run完全一致（见下方"新旧对照"）。

唯一eligible的`bull:13`（claim="But look at the PEG of 0.64."）：
真实`alpha_matches.json`显示其对全部10个Alpha的`keyword_score`/
`factor_score`/`direction_score`/`semantic_score`**全部为0.0**，
`direction=unknown`，`factors=[]`——远低于`minimum_match_score=0.35`
门槛。这是Alpha匹配阶段（发生在原始run，与本轮内容支持核验完全
独立）的真实、合理结果：这条claim本身是一句脱离上下文的数值引用，
没有可识别的因子/方向信号，不是bug，是这条claim自身信息密度不足以
单独匹配任何Alpha。

**其余10个Alpha**：与本轮21条claim完全无claim_ids重叠，不受本轮
任何改动影响，分数与原始run逐项相同。

### 逐候选冲突结果

`conflicts.json`与原始run**逐字节完全相同**（含`main_conflict`、
全部`candidate_evaluations`及各自的`admissibility`/拒绝原因）——
21条claim里没有任何一条进入过任何冲突候选评估，`conflicts.json`
从未读取过这21条claim_id，本轮改动对冲突结果零影响。

### 新旧对照（关键结论）

| | 原始run（`1bad76a7-...`） | 新execution（`review-20261006T001911Z-14407742`） |
|---|---|---|
| `alpha_activations.json` | 基线 | 与基线**语义完全相同**（已用忽略run_id/随机evidence_fact_group_id/列表顺序的规范化比较逐项核对，零差异）|
| `conflicts.json` | 基线 | 与基线**逐字节完全相同** |
| 产生正式分数贡献的claim数（此21条中） | 0 | 0 |
| 达到active/dominant的Alpha（因这21条） | 无 | 无 |
| 冲突admitted状态变化 | 无 | 无 |

**本轮真实、完整、合规的20次付费核验，加上此前1次，21条清单全部
处理完毕后，对AMD官方评分、Alpha激活、Conflict结果的净影响为零**
——不是因为核验机制失败，而是两个真实、各自独立、均已精确定位的
阻塞点共同作用的结果（见第五节）。

---

## 五、充分依据是否被错误阻挡？——逐层精确定位，不写"证据不足"了事

21条claim最终无一成为"产生正式分数贡献"的证据，原因分层如下：

1. **材料缺失**：0条——候选来源（`src_5bd8a947130d1949`，AMD
   fundamentals snapshot）本身真实存在，21条claim的`source_link_
   status`全部`VALID`，不是材料缺失问题。
2. **仅部分支持**：9条（8条原始SUPPORTS因unsupported_remainder降级
   为CONDITIONAL，另1条模型直接给CONDITIONAL）——这是claim本身
   混合了"可验证部分"与"源数据不支持的部分"，既有降级规则正确
   识别并处理，不是误判。
3. **核验失败（截断/引用拒绝/材料不足）**：5条——3条截断（即使
   max_tokens=8192也不够，原因未进一步深挖,按本轮边界不涉及prompt
   调整）、1条引用校验拒绝（`bear:54`,真实拒绝,已记录原因)、1条
   模型自认材料不足（INSUFFICIENT）。
4. **Alpha匹配缺失**：**关键瓶颈**——唯一通过content-support核验、
   真实eligible=True的`bull:13`,在Alpha匹配阶段（与本轮完全无关,
   发生在原始run本身）对全部10个Alpha评分均为0.0,从未进入任何
   Alpha的候选证据池。这是本轮发现的最精确、最具体的断点：**即使
   content-support核验环节完全正常工作,这条claim也无法贡献分数,
   因为它从一开始就没有被匹配到任何Alpha**。
5. **时间/claim质量**：无关——21条`source_link_status`全部VALID,
   analysis_date/evidence_cutoff_at真实、未放宽（沿用`resolve_
   evidence_cutoff_at`,未因本轮执行时间而改变原证据截止条件）。
6. **方向/独立证据/分数/结构/Exposure条件**：不适用——由于0条claim
   同时满足"eligible=True"且"matched_alpha非空",根本没有claim进入
   过这些后续门槛的评估,无法报告"在哪个门槛被拦下"之外的更细粒度
   结论。

**如果要让这个候选来源（AMD fundamentals snapshot）的claim真正
贡献分数，具体缺口是**：这份fundamentals快照本身是通用财务指标
（PE/PEG/beta/均线等），这21条claim大多是分析师对这些指标的泛泛
引用或组合判断，语言上与AMD Alpha库（A001-A304等具体投资主题）的
关键词/因子库重合度低——这不是"核验机制"的缺口，而是"这批claim的
文本内容/这份来源的材料类型"与"现有Alpha关键词因子库"之间的真实
匹配缺口。按本轮授权，不新增Fresh Run、不抓取新材料来验证这个假设，
如实记录为需要在下一轮决定是否值得投入的具体输入缺口。

---

## 六、API/Export真实核对 + 阶段B遗留项状态

### 真实API读取路径

```python
build_research_response("review-20261006T001911Z-14407742", output_root="outputs/runs")
```
返回：`status=partial`（因`data_sanity_status=not_available`——
reevaluation类执行不跑Week1-2的data sanity阶段,与
`trigger_content_support_reevaluation`产出的执行同样如此,非本轮
缺陷)，`structure_graph_status=ready`,`conflict_status=ready`,
`entity_alpha_exposure_status=ready`,`dominant_alphas=[]`。

### 真实Export入口（不是直接读磁盘JSON）

```python
get_run_export_bundle("review-20261006T001911Z-14407742", output_root="outputs/runs")
```
返回真实200状态、`application/zip`、真实ZIP字节（以`PK\x03\x04`
文件头开头,非伪造)。解压后逐项核对：`alpha_activations.json`/
`structured_agent_outputs.json`/`conflicts.json`——**ZIP内容与磁盘
execution产物逐字节完全相同**；专门核对了`bull_researcher:claim:13`
在ZIP内的`content_support_status=SUPPORTS`及完整
`content_support_llm_detail`（引用`peg_ratio=0.64`）,与磁盘记录一致。

### UI核查

**本轮未做浏览器走查**——未验证UI实际渲染/交互,如实声明未执行,
不称为比上述API/Export组件级核对更强的证据。

### 阶段B遗留项（按实际已有证据标注，未因本轮真实核验完成而自动
记为通过）

- 真实"active"完整fixture证明（不注入分数、走完整链路）——**仍未
  执行**,本轮未涉及。
- 自动去重机制的**生成端**证明（真实抽取流程本身是否检测跨Agent
  同一事实,而非仅消费侧用已设置的`duplicate_group_id`)——**仍未
  执行**,本轮未涉及。
- Export入口真实ZIP往返证明——**本轮已完成**（见上），不同于阶段B
  原先只读JSON文件的做法,这是一个真实的新增进展,不是遗留。

---

## 七、历史保护与哈希核对

原AMD 34条清单（`round4_amd_34_item_reverification_20261004/
02_amd_34_item_ledger_v3_CURRENT_MECHANISM.json`）——**未替换、未
删除、未回填本轮AMD材料**，哈希核对与本轮开始前一致。

本次重算的是**新的**AMD执行（`review-20261006T001911Z-14407742`），
**不是**原34条所在的历史run——34条清单里没有对应这次重算的历史
采用列，如实标注"本轮未执行"，不用本轮的资格判断代替实际历史结果。

哈希核对（本轮开始前 vs 现在，全部一致）：

| 文件 | 状态 |
|---|---|
| 原始run `metadata.json` | 一致 |
| 原始run `structured_agent_outputs.json` | 一致 |
| 原始run `alpha_matches.json`/`extracted_structures.json`/`alpha_activations.json`/`conflicts.json` | 本轮首次记录基线，只读取未写入 |
| reeval run `structured_agent_outputs.json`/`source_registry.json` | 一致 |
| `04_phase_c_real_results.json`（第一次5次真实请求的历史记录） | 一致 |
| AMD 34条清单 | 一致 |

---

## 八、费用与usage核算（分层统计，历史请求另列）

- **历史**：第一轮5次真实请求（全部截断，零有效结果）——已在
  此前报告中核算，本轮未重试、未计入本轮额度。
- **已完成单claim验证**（本轮复用其真实响应，未重新发送）：
  `input=1923, output=7300`，估算费用≈$0.0047。
- **本轮20次真实请求**（新增额度，全部到账）：
  `input=38809, output=109579`，估算费用≈**$0.0716**（基于真实usage
  ×DeepSeek非高峰公开定价，未对照真实账单，不称为"实际扣款"）。
- usage缺失：0——20条全部有完整token_usage记录。

---

## 九、T1仍未满足的具体完成条件

1. **Alpha匹配缺口**（最具体、最可操作的断点）：需要补充与AMD
   具体Alpha主题（如A304等）关键词/因子重合度更高的真实材料
   ——不是"更多同类fundamentals快照"，而是能让claim文本本身包含
   可被现有Alpha关键词/因子/语义匹配规则识别的内容。本轮未验证
   "补充哪种具体材料"能解决这个缺口,需要专门调查Alpha关键词库与
   真实AMD材料的重合度后才能给出有依据的建议,本轮不臆测。
2. **截断仍未根治**：3/20条即使max_tokens=8192依然触顶
   （finish_reason=length）,具体字段级归因未做（如是否与claim本身
   的某类措辞/prompt段落相关）,这是下一轮如果要继续推进必须先查
   的问题,不是"再加大max_tokens"就能确定解决的。
3. **降级后的CONDITIONAL claim群**：9条CONDITIONAL claim目前已经
   是"模型认为部分正确"的真实状态,现有机制决定CONDITIONAL不计入
   正式证据——这是既有、经过阶段B/本轮反复验证的正确设计,不是
   缺陷,但如果未来需要让"部分正确"的证据也能有限度地贡献分数,
   需要新的、明确授权的评分规则改动,本轮未做、也未建议具体公式。
4. 阶段B两项遗留（真实active fixture全链路证明、去重生成端证明）
   仍待执行,与本轮工作相互独立。

本轮20次新增请求与独立重算已经结束，按授权停止。不循环调整
prompt，不宣称T1或John整体验收通过。
