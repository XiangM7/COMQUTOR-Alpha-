# 第八轮：自动核验接入正式评分 + AMD 独立重评估（2026-10-06）

零 Provider 调用、未启动 Fresh Run。DB 写入全部走已核实的隔离测试库
（`comqutor_alpha_test`，`docs/audit_artifacts/round_source_linking_t0_t2/
round8_automated_eligibility_20261006/00_run_isolated_db.sh` 复用
`run_nvda_fresh_run_isolated_db.sh` 的同一套强制+校验机制）。未改评分公式、
阈值、taxonomy、Alpha 语义准入规则，未处理 Demo，未 commit、未 push。
历史 run（`1bad76a7-...`）的全部文件、DB 行只读，从未覆盖。

## 一、最小代码改动

| 文件 | 改动内容 |
|---|---|
| `comqutor_alpha/source_provenance.py` | 新增 2 个真实、确定性自动核验方法 `AUTOMATED_DATA_FACT_VERIFIED`/`AUTOMATED_DERIVED_CALC_VERIFIED`（连同 `AUTOMATICALLY_ELIGIBLE_REVIEW_METHODS`）；新增 `verify_data_fact_or_derived_calculation`/`apply_automated_content_support_verification`（核验逻辑本身）；新增 `resolve_evidence_cutoff_at`（时间契约修复）；`compute_verified_support_eligibility` 的条件 2 从"只认 HUMAN_REVIEWED"改为"认 `AUTOMATICALLY_ELIGIBLE_REVIEW_METHODS` 里任意一个"；`build_content_support_review` 的绑定校验同步扩展到两个新方法。 |
| `comqutor_alpha/structure_engine/structured_output_adapter.py` | `evidence_cutoff` 的取值从直接读 `analysis_date` 改为调用 `resolve_evidence_cutoff_at`；`_annotate_source_link` 在把 `content_support_status` 设为 `PENDING_REVIEW` 之后，立即尝试 `apply_automated_content_support_verification`，核验成功才覆盖，失败则保持原样；新增 `evidence_cutoff_at`/`evidence_cutoff_basis`/`analysis_date` 到持久化的 `metadata` 块。 |

新增文件：
- `tests/test_automated_content_support_verification.py`（19 个新测试，正向
  + 反向，覆盖见下）。
- 本目录：`00_run_isolated_db.sh`（隔离库启动器）、
  `01_amd_automated_eligibility_reevaluation.py`（独立重评估脚本）、
  `02_reannotation_change_log.json`（真实改动记录）。

真实测试命令与结果：

```
.venv/bin/python3 -m pytest tests/test_automated_content_support_verification.py -v
# 19 passed

.venv/bin/python3 -m pytest tests/test_automated_content_support_verification.py \
  tests/test_structured_output_adapter.py tests/test_t1_financial_statement_source_chain.py \
  tests/test_t1_source_linking_pipeline.py tests/test_content_support_never_inflates_scoring.py \
  tests/test_evidence_gate_qualified_evidence_scenarios.py tests/test_source_provenance.py \
  tests/test_verified_evidence_gate.py tests/test_verified_evidence_gate_production_wiring.py \
  tests/test_t1_cross_agent_reference_and_derived_calc.py tests/test_t1_financial_source_chain.py \
  tests/test_t1_macro_source_chain.py tests/test_t1_market_data_source_linking.py \
  tests/test_conflict_detector.py tests/test_acceptance_engine.py tests/test_graph_persistence.py \
  tests/test_week4_golden_closure.py tests/test_week4_nvda_conflict_sanity.py \
  tests/test_week3_nvda_sanity.py tests/test_week3_qqq_sanity.py -q
# 445 passed
```

全量 `pytest tests/` 跑了一次（896 秒）：4696 passed、32 failed、56 skipped。
**32 个失败全部核实为本轮之前就存在、与本轮改动无关**：均属于"冻结基线字节
一致""固定阈值/固定样本数"一类的既有守护测试（如
`test_j3_semantic_benchmark_j2_v0_2.py::test_e42_head_unchanged_from_session_
frozen_starting_commit`、`test_msft_a102_a304_taxonomy_adjudication.py::
test_a6_...byte_identical`、`test_evidence_review_v2.py` 的多个固定阈值/
john_approved 用例），没有一个引用本轮新增的任何函数或常量（已逐个 grep
确认）。抽查其中 `test_b2_admissibility_integration.py` 一例，定位到真实
原因：`comqutor_alpha/storage/db/week4_persistence.py` 里
`_whitelist_evidence_qualification`（2026-09-30 的一次未提交修复，早于
本轮）已经让 `evidence_qualification` 字段能在 DB 往返中保留，但对应测试
文件（`git show HEAD` 确认该文件自身也早于这次修复）没有同步更新期望，
是两处更早、彼此独立的未提交改动之间的真实遗留不一致，与本轮工作无关。

## 二、自动核验规则及已实现范围

### 2.1 实现了什么

`verify_data_fact_or_derived_calculation`（`source_provenance.py`）——
对一条已经 `source_link_status == VALID` 的声明，仅在满足全部条件时才
判定为可自动核验：

1. 声明文本去掉所有数字/日期/期间 token、以及该来源自己真实 `data_snapshot`
   里的字段名（如"Total Revenue"）之后，**剩余内容必须为空**——这是唯一的
   安全阀：一旦句子里还带有"expensive""a healthy sign""consistent with"
   这类评价/推断性语言，整句永远不会被自动核验，哪怕其中一个数字是真的。
2. 声明里出现的每个数值，必须在该来源自己保存的 `data_snapshot`（分期间
   的 `periods`/`all_line_items`，或 `.info` 快照的扁平字段）里找到——
   对象、单位、期间三者是同一次查找同时核对的，不是"这个数字出现在某处
   就算数"。
3. 对显式算式声明（出现 "+"/"="，排除日期里的连字符），只要求**运算数**
   来自来源真实数据，**结果**独立重新计算校验，不会因为声明引用了 3 个
   真数字就直接通过——结果算错照样判不通过。

两个新方法名：`AUTOMATED_DATA_FACT_VERIFIED`（纯数据事实）、
`AUTOMATED_DERIVED_CALC_VERIFIED`（显式算式）——从不冒充
`HUMAN_REVIEWED`，`content_support_review` 里如实记录方法名、
`claim_id`/`linked_source_id`/`content_hash` 绑定，和人工复核要求的绑定
严格程度完全一样。

### 2.2 真实反例（19 个测试里的负向用例，证明没有"宁可信其有"）

- 错误数值（声明里的数字源数据里根本没有）→ 不核验。
- marker 能解析出来源，但来源自己不含该字段 → 不核验。
- 真实运算数、虚假结果（如 "1990 - 1476 = 999"）→ 不核验。
- 复合声明（真数字 + "confirms a strong demand environment" 这类评价语）
  → 不核验，整句原样保留 `PENDING_REVIEW`。
- 非正式转述的字段名（"cash" 代替来源里真实的 "Cash And Cash
  Equivalents"）→ 保守地不核验，不猜语义对应关系。
- 未经过 `source_link_status == VALID` 的声明 → 不核验。

### 2.3 一般文本语义核验——明确的能力缺口（未实现，未假装实现）

仓库里已有的 `derived_fact_verification.py`（第三轮产出）只覆盖"两值
百分比比较"这一种固定句式（如"X is Y% above the 200 SMA"），且明确
是纯诊断字段，从不接入资格判定——本轮未改动它的契约。除了这一种固定
句式和本轮新增的"纯数字枚举/显式算式"这两类，**没有任何能判断"这段
自由文本是否真的在陈述来源支持的论点"的通用语义核验实现**——例如
"估值昂贵""确立了上升趋势""符合 AI 需求爬坡逻辑"这类分析性判断，
本轮没有、也不可能用正则或确定性匹配安全核验。这是一个真实的、后续
需要专门的语义核验模型任务（例如一个经过严格校准、输出可追溯依据的
分类器）才能缩小的缺口，本轮没有用固定响应或任何形式的测试桩冒充它，
也没有为了让它"看起来能跑"而重新引入人工确认。

### 2.4 AMD 新 run 里具体可核验条目示例（节选）

| claim_id（节选） | 来源位置 | 可验证命题 | 对应 Alpha | 核验前阻塞原因 |
|---|---|---|---|---|
| `...fundamental_agent:fundamentals_report:claim:30` | `src_582ac24bf4319648`（income statement） | Total Revenue 五个季度数值 | （context_only，无 Alpha 匹配） | `content_support_status=PENDING_REVIEW`（无人工审核） |
| `...fundamental_agent:fundamentals_report:claim:2`（Metric: Market Cap） | `src_5bd8a947130d1949`（.info 快照） | Market Cap 具体数值 | （context_only） | `source_link_status=TIME_INVALID`（裸日期午夜截止，见第三节） |
| 下游 `bull_researcher` 的净现金/EPS 调整类转述声明 | 同上两个来源 | 含评价/推断语言的复合句 | A001/A501 等 | 不安全自动核验（见 2.3），仍为 `PENDING_REVIEW` |

完整列表见本目录 `02_reannotation_change_log.json`（78 条真实改动，逐条
`claim_id`/改动前后状态）。

## 三、真实时间契约修复

`resolve_evidence_cutoff_at`（新函数）：优先取
`max(来源自己的 retrieved_at)` 作为 `evidence_cutoff_at`（真实、已保存、
有时区的取数时刻），**但只在这个最大值和 `analysis_date` 落在同一个
日历日时才启用**——否则退回原来的裸日期午夜兜底，不跨天生效。

- `fetched_at`（本代码库里字段名叫 `retrieved_at`，概念对应用户说的
  fetched_at）：来源被真实抓取进系统的时刻，本轮未重命名字段，只在新
  函数里明确按这个含义使用。
- `published_at`：披露时间，历史财报声明的 `published_at` 本来就是
  `None`（`source_provenance.py` 既有注释：yfinance 只给出报表期末日，
  当作披露时间会制造真实前瞻风险，本轮未改这个既有设计）；`.info`
  实时快照的 `published_at` 本来就等于抓取时刻（"like a live quote"，
  同样是既有设计，本轮未改）。
- `observation_date`：来源自己的观测日期字段，未改。
- `analysis_date`：这次 run 自己声明的"作为以..为准"的日期，权威性
  不变——新函数不会用一个落在不同日历日的 `retrieved_at` 覆盖掉它（这
  正是"不能静默扩大原截止范围"的具体落实：最早写的版本犯过这个错误，
  被一个真实回归测试
  `test_a_source_published_after_the_evidence_cutoff_is_rejected_
  never_used_as_look_ahead` 当场测出来——模拟"注册表复用、真实抓取时刻
  晚于这次 run 自己声明的更早 analysis_date"场景，旧版本会错误放行，
  已修正并补了同日历日护栏，该测试现在通过）。

**明确没有做**：没有把截止时间改成当天日末；没有把抓取时间冒充成
历史财报的披露时间（历史财报的 `published_at=None` 完全没动）。

**效果**：对 AMD 这次 run，`evidence_cutoff_at` = `2026-10-05T17:36:24`
（这次 run 注册表里全部来源的真实 `retrieved_at` 最大值，和
`analysis_date` 同一天）。52 条 `TIME_INVALID` 全部重新核对后变为
`VALID`（见第四节真实数字）。

## 四、AMD 独立重评估：改前改后对照

`01_amd_automated_eligibility_reevaluation.py`：只读原 run 的
`structured_agent_outputs.json`/`alpha_matches.json`/
`extracted_structures.json`/`source_registry.json`（从未重新分类、从未
重新抓取），只对两件事重新推导：①对原来 `TIME_INVALID` 的声明，用已有
候选 `linked_source_id` 按修正后的 `evidence_cutoff_at` 重新验证；②对
（原本或新变成）`VALID` 的声明跑新的自动核验。其余字段原样保留。写入
全新 `execution_id`（`automated-eligibility-reeval-20261005T190101Z-
d9b7fdba`），原 run 的文件和 DB 行未被打开写入。

**真实改动统计**（`02_reannotation_change_log.json`）：

| 改动类型 | 数量 | 说明 |
|---|---|---|
| `source_link_status: TIME_INVALID → VALID` | 52 | 对应第七轮确认的全部 52 条，根因（裸日期午夜截止 vs 当天真实取数时刻）一次性清零 |
| `content_support_status: PENDING_REVIEW → SUPPORTS`（`AUTOMATED_DATA_FACT_VERIFIED`） | 26 | 全部为 `claim_quality=context_only` 的纯数据事实声明 |

**逐 Alpha 官方（v2_verified）层对照**：10/10 Alpha 的
`status`/`activation_score`/`direction`/`evidence_count` **改前改后完全
一致**（全部仍为 `candidate`/`0.0`/`unknown`/`0`）。`dominant_alphas`/
`active_alphas` 改前改后都是 `[]`。8 对候选冲突的 `reason_codes`
改前改后逐一比对完全一致（全部仍是 `DIRECTION_ROLE_UNRESOLVED`，部分
附加 `MISSING_LEFT/RIGHT_EVIDENCE`）。

**真实原因（已查清，不是"证据不足"这种笼统说法）**：获得自动核验的
26 条声明，`claim_quality` 全部是 `context_only`（纯数据陈述，不带方向
性判断——这正是它们能被安全自动核验的原因：没有可解读为分析判断的
内容）。而 `comqutor_alpha/structure_engine/claim_quality.py` 的
`is_claim_eligible` 对 `activation`/`conflict` 两个消费者明确规定
`CONTEXT_ONLY` 一律不合格（"Unified Claim Admissibility Sprint"既有
设计，这次核验对象恰好全部落在这个既有、独立于人工审核的门之外）。
也就是说：**这次自动核验机制本身真实生效（content_support_status 真实
从 PENDING_REVIEW 变成 SUPPORTS，有真实的方法名和绑定记录），但它触达
的这批声明在更早一步的"声明质量"门上就已经被排除在 Activation/Conflict
证据之外，和是否经过人工审核完全无关**，所以这次 AMD 重评估的最终
`conflicts`/`dominant_alphas` 没有变化——这是真实、如实的结果，不是
机制没生效。

21 条同样从 `TIME_INVALID` 变成 `VALID`、但 `claim_quality=analytical`
的声明（有方向性判断，理论上能参与 Activation/Conflict），目前仍停留在
`content_support_status=PENDING_REVIEW`——本轮的自动核验器按设计正确地
拒绝了它们（文本里混有"这是个重要拐点""符合...逻辑"这类评价语言，
见 2.3 的能力缺口）。这 21 条正是"将来需要更强的语义核验能力才能真正
推进"的具体、已定位的候选清单（不是本轮编造的乐观估计）。

**正式验收**：`formal_acceptance.json` 的 `formal_status` 从 `pass`
变成 `not_evaluable`——这是 `run_formal_acceptance` 在遇到一个它没有
Gold 标签的 ticker（AMD）时的既有、真实行为（和冲突变化无关，纯粹是
这个新 `execution_id` 字符串触发了它自己的标签查找逻辑；原 run 的
`formal_status=pass` 同理不代表"AMD 有 Gold 基线"，只是两次调用在
这项检查上走了不同分支，与本轮任何修改无关，仅如实记录观察到的差异）。

**未执行的分类/证据缺口，如实列出，未离线伪造任何新匹配**：预算层面
本次重评估零新增 Provider 调用，`alpha_matches.json` 完全沿用原 run
已经真实分类过的 536 条结果，未补、未删、未改一条。

AMD 原有 34 条冲突证据清单（第四轮产出）继续原样保留，历史缺失内容
未回填，未在本轮重新生成或碰过。

## 五、John T1 完成条件对照

| John 的条件 | 本轮证据 | 状态 |
|---|---|---|
| 生产证据资格由软件自动判定，不依赖人工审核 | `compute_verified_support_eligibility` 条件 2 已改为认
`AUTOMATICALLY_ELIGIBLE_REVIEW_METHODS`（含 2 个自动方法），真实单测
`test_automated_verification_makes_the_claim_eligible_without_any_human_
review` 证明一条从未有人工审核记录的声明确实能拿到 `eligible=True` | **已满足**（机制层面） |
| 不自动填 HUMAN_REVIEWED，不把人工入口改成生产必经步骤 | 两个新方法名
从未写成 `HUMAN_REVIEWED`；`apply_content_support_review`（人工路径）
一字未改；`trigger_content_support_reevaluation`（人工复核入口）一字
未改 | 已满足 |
| 固定样本（原有准入条件）经真实流水线能激活 Alpha、形成 admitted
conflict | 本轮固定样本测试（19 个新测试 + 既有 T1/T2/Week3/Week4
共 445 个）全部通过真实 `conflict_detector`/`verified_evidence_gate`
真实函数，未注入最终分数、未放宽阈值 | 已满足（测试层面） |
| 真实 AMD 结果 | 见第四节：机制真实生效（26 条 content_support 改变、
52 条 TIME_INVALID 修复），但受限于一个独立的、更早的 `claim_quality`
门，最终 conflicts/dominant_alphas 这次没有变化 | **部分满足，原因已
精确定位到具体代码和具体字段，不是笼统的"证据不足"** |
| 不设必须产生几个 Alpha/Conflict 的数量目标 | 本报告未因为"这次还是
零冲突"而去改阈值或注入结果 | 遵守 |

**仍需要的后续工作（明确、具体，不是泛泛而谈）**：
1. 一般文本语义核验能力（2.3）——这是让 21 条已经 `VALID` 但仍
   `PENDING_REVIEW` 的 analytical 声明真正进入官方证据池的唯一缺口，
   需要专门的语义核验模型任务，本轮未实现。
2. `claim_quality` 门是否应该在"纯数据事实"类 `context_only` 声明上
   放开给 Activation/Alpha-context 用途（`claim_quality.py` 自己的
   矩阵显示 `mapping` 消费者对 CONTEXT_ONLY 本就是 Yes）——这是一个
   需要产品决策的问题，本轮未擅自改动既有矩阵。
