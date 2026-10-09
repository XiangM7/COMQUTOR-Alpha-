# 第七轮：纠正统计口径 + AMD 根因诊断（2026-10-05）

零 Provider 调用、未启动 Fresh Run。全部结论来自对已落盘真实数据
（`t3_eval_records.jsonl`、`outputs/runs/1bad76a7-.../*.json`、
`comqutor_alpha/` 现行代码）的离线重新计算/代码追踪。未修改评分阈值、
人工审核政策、任何历史产物；`outputs/t3_evaluations/.../t3score_
20261005T174932Z_3c3b6b32_score_result.json`（旧评分文件）保持不变，
本轮修正版单独存放在本目录。

## 1. T3 评分口径纠正：50% 精确率确系 17/34 与 17/30 混用

**原始模型选择（任何产品门之前，`classifier_status_raw` 原始分布）**：
`llm_selected`=35，`llm_none`=5（合计 40）。

**产品门过滤后的结果**（`classify_outcome` 当前、正确版本重新计算 40 条
各自的 `outcome_code`，而不是沿用冻结文件里的旧字段）：
`MATCHED`=30，`SELECTED_BUT_NOT_MATCHED`=5，`NONE`=5。

**旧评分 vs 修正评分**（同一份、未改动的 `score_against_human_labels`
函数，仅输入的 `outcome_code` 不同）：

| 指标 | 旧评分（沿用冻结文件里 5 条过期 outcome_code） | 修正评分（按当前 classify_outcome 重算） |
|---|---|---|
| overall_accuracy | 56.41%（不变） | 56.41%（不变） |
| non_none_recall | 68.0%（不变） | 68.0%（不变） |
| **non_none_precision** | **50.00% = 17/34** | **56.67% = 17/30** |
| outcome_code_counts | MATCHED=34, NONE=5 | MATCHED=30, NONE=5, SELECTED_BUT_NOT_MATCHED=4 |

**确认你的判断完全正确**：差的 4 个百分点精确率，来自 5 条记录的
`outcome_code` 过期——这 5 条在 2026-10-01 执行时用的是
`classify_outcome` 当时一个已知有 bug 的旧版本，把
`(llm_selected, no_match)` 错误映射成 `"MATCHED"`（`predicted_alpha=None`），
而不是正确的 `"SELECTED_BUT_NOT_MATCHED"`。该函数自己的 docstring
（2026-10-01 AI-review 对照轮）早已记录这个历史 bug 和修复，但明确说明
"未回溯应用到那次执行自己已保存的 `t3_eval_records.jsonl`"——所以旧评分
文件沿用的 34 这个分母，混进了 4 条本不该算作"系统判了一个 Alpha"的
记录（第 5 条 `gold-final-030` 因为是 `UNABLE_TO_JUDGE` 被打分逻辑单独
排除，不计入 39 条参与打分样本）。

真实、未改动的混淆矩阵对角线真阳性（tp）两次都是 **17**（分子不变）；
唯一变化是分母：34（含 4 条过期"MATCHED"误判） → 30（正确排除后）。

产出物：
- `01_t3_corrected_rescore_script.py` —— 离线重算脚本（读
  `t3_eval_records.jsonl` + 人工判断表，用当前 `classify_outcome`
  重新计算 outcome_code，再用未改动的 `score_against_human_labels`
  两次打分对照）。
- `02_t3_corrected_rescore_result.json` —— 完整输出（原始选择分布、
  产品门分布、5 条过期记录明细、新旧混淆矩阵）。
- 旧评分文件原样保留：`outputs/t3_evaluations/t3live_20261001T014648Z_1fb9c9d5/t3score_20261005T174932Z_3c3b6b32_score_result.json`（未改动）。

## 2. AMD 新 Fresh Run 逐层追踪：HUMAN_REVIEWED 确实直接清空了方向判定，而非"证据总量"

run_id=`1bad76a7-72ac-4c8b-8189-2e5c0f1a6105`。

### 2.1 三层 activation 对照（10 个 Alpha 全量）

| Alpha | v1（历史同类 run 当正式结果用的层级） | v2（这次 run 的原始/未过人工审核层） | v2_verified（这次 run 的正式/官方层） |
|---|---|---|---|
| A001 | active, dir=positive, score=67.12, ev=3 | watch, dir=mixed, score=37.60, ev=2 | candidate, dir=**unknown**, score=0, ev=0 |
| A003 | inactive, dir=unknown, score=0 | inactive, dir=unknown, score=0 | candidate, dir=unknown, score=0, ev=0 |
| A101 | dominant, dir=positive, score=79.40, ev=6 | watch, dir=positive, score=31.25, ev=3 | candidate, dir=**unknown**, score=0, ev=0 |
| A102 | inactive, dir=unknown, score=0 | inactive, dir=unknown, score=0 | candidate, dir=unknown, score=0, ev=0 |
| A103 | active, dir=neutral, score=53.95, ev=3 | inactive, dir=negative, score=0 | candidate, dir=unknown, score=0, ev=0 |
| A201 | dominant, dir=positive, score=73.96, ev=11 | inactive, dir=positive, score=27.07, ev=6 | candidate, dir=**unknown**, score=0, ev=0 |
| A301 | regime_level, dir=positive, score=99.0, ev=13 | watch, dir=positive, score=40.80, ev=5 | candidate, dir=**unknown**, score=0, ev=0 |
| A304 | regime_level, dir=negative, score=99.33, ev=24 | watch, dir=negative, score=45.83, ev=4 | candidate, dir=**unknown**, score=0, ev=0 |
| A501 | regime_level, dir=negative, score=96.67, ev=13 | watch, dir=mixed, score=35.93, ev=4 | candidate, dir=**unknown**, score=0, ev=0 |
| A601 | dominant, dir=positive, score=74.92, ev=4 | inactive, dir=positive, score=0 | candidate, dir=unknown, score=0, ev=0 |

**v2（原始层）本身就已经不足以形成冲突**：没有一个 Alpha 在原始层达到
`active`/`dominant`/`regime_level`，全部封顶在 `watch`/`inactive`——这和
历史 run（v1 那一栏，此处借来对照）判若两run。

**v2_verified（正式层）是彻底归零**：10/10 全部 `status=candidate`、
`score=0`、`evidence_count=0`、**`direction=unknown`**——因为这次 run 里
`content_support_status` 全部是 `PENDING_REVIEW`，没有一条经过人工
内容复核，`evidence_gate_applied=True` 的人工复核门把所有证据都挡在了
"官方可用"之外。

### 2.2 为什么 8 对候选冲突全部 `admissibility: null`——不是遗漏字段，是真的没跑到那一步

真实追踪 `conflicts.json`→`arbitration.candidate_evaluations`（8 对）：

| Alpha A | Alpha B | 真实拒绝原因 | A 侧原始合格证据数 | B 侧原始合格证据数 |
|---|---|---|---|---|
| A001 | A501 | DIRECTION_ROLE_UNRESOLVED | 2 | 8 |
| A003 | A501 | MISSING_LEFT_EVIDENCE + DIRECTION_ROLE_UNRESOLVED | 0 | 8 |
| A101 | A304 | DIRECTION_ROLE_UNRESOLVED | 6 | 18 |
| A102 | A304 | MISSING_LEFT_EVIDENCE + DIRECTION_ROLE_UNRESOLVED | 0 | 18 |
| A201 | A304 | DIRECTION_ROLE_UNRESOLVED | 9 | 18 |
| A301 | A304 | DIRECTION_ROLE_UNRESOLVED | 12 | 18 |
| A304 | A601 | MISSING_RIGHT_EVIDENCE + DIRECTION_ROLE_UNRESOLVED | 18 | 2 |
| A501 | A601 | MISSING_RIGHT_EVIDENCE + DIRECTION_ROLE_UNRESOLVED | 8 | 2 |

**修正一个我自己中途的误判**：我最初用错误的字段名查询（`included`
而非真实字段名 `qualifying_claim_ids`/`qualifying_count`），误以为 8 对
全部双侧 0 证据。重新核对后，**6/8 对其实双侧都有非零的原始（未经人工
复核）合格证据**（例如 A301 vs A304：12 对 18），只有 2/8 对
（A003/A501、A102/A304）才是真的一侧完全 0 条。

**但全部 8 对，无一例外，都带 `DIRECTION_ROLE_UNRESOLVED`**——这才是
真正的、统一的拒绝原因，直接追到代码：`conflict_detector.py` 第 944 行
`resolve_bull_bear(alpha_a, fields_a.direction, alpha_b, fields_b.direction)`，
其中 `fields_a.direction`/`fields_b.direction` 来自 `activations_by_id`
——本次 run 的官方（verified-primary）版本。由 2.1 表格已经证实：
v2_verified 层每一个 Alpha 的 `direction` 字段都是 `"unknown"`。
`resolve_bull_bear` 在两侧方向都不是明确 positive/negative 时返回
`bull_id=None` → 追加 `DIRECTION_ROLE_UNRESOLVED` → 函数在第 946-957 行
**直接提前返回**，`evaluate_conflict_admissibility_verified`（真正计算
`admissibility.status`/`reason_codes` 的函数）**根本没有被调用**——这就
是 `admissibility: null` 的真实、精确原因：不是字段丢失，是这一步代码
从未执行到。

**这就是对你"特别确认HUMAN_REVIEWED条件是否直接清空了正式证据池"这个
问题的精确回答：是，而且有确切的机械链条**——人工复核门把所有 Alpha
的方向判定清空成 `unknown`（不是把证据数清零这么简单，是连"这个 Alpha
是看多还是看空"这个最基本的方向标签都清空了）→ 冲突仲裁的方向角色
消解步骤在任何一对候选上都无法成立 → 真正的可采性（admissibility）
评估从未被触发，不是"评估后被拒绝"，是"从未被评估"。

**另一个独立发现**（不是今天的阻塞原因，但解释了"即使修好人工复核门，
也不能保证就能形成冲突"）：`evidence_audit` 阶段（来自 `alpha_matches.json`
的原始分类结果，独立于人工复核门）里，全部 8 对累计 2659 次候选证据
排除中，`NON_COMMITTED_MATCH`（分类器没有给出明确、可采信的匹配）占
2011 次（75.6%），`WRONG_ALPHA` 510 次——这和第 1 点测出的 T3 真实分类
精确率只有 56.67%是同一个根因在不同环节的重复体现：即使跳过人工复核门，
分类器自身真实的匹配质量也会独立限制能形成冲突的证据规模。

### 2.3 历史 run 不是同口径对照组（之前报告没写清楚，这里补上）

历史 AMD run（`d5b60b8a-66b8-44c1-9f55-ee345e58c48d`，2026-09-21）：
`activation_versions` 只有 `v1`/`v2` 两层，**根本不存在 `v2_verified`
层**；`primary_activation_version = "...v1"`（直接把未经任何人工复核的
原始层当正式结果用）；`evidence_gate_applied = None`（人工复核门从未
在那次 run 里生效）。它的 A304 在这个"原始即正式"的口径下是
`dominant, score=81.53, evidence_count=24`，这才是它当年真实形成冲突/
dominant alpha 的原因。

**结论**：历史 run 和这次 Fresh Run 不是同一套正式性口径——不能说
"同一个 AMD，这次反而测不出冲突了，所以来源链接机制退步了"；真实情况
是，这次 run 诚实地跑在了当前、更严格的人工复核门之下，而历史 run
从未经过这道门。两次"有没有冲突"的比较，在人工复核门这一项上不是
对照实验。

## 3. 52 条 TIME_INVALID：单一真实根源确认，修复方案（未实现，仅提案）

**根因**（已完整核对）：52 条全部来自同一个来源
`src_5bd8a947130d1949`（`source_type="financial"`，标题
"AMD fundamentals snapshot 2026-10-05 10:34:46"，`published_at =
"2026-10-05T10:34:46.683873"`，这是 `get_fundamentals` 的真实抓取时刻,
被源头代码自己标注为"CURRENT/live-computed"快照，不是披露时间)。
这次 run 的 `analysis_date = "2026-10-05"`，作为 `evidence_cutoff`
传入 `validate_source_reference`，被 `_parse_iso_like`（
`comqutor_alpha/source_provenance.py:1176`）解析成当天**午夜**
(`2026-10-05T00:00:00`)。源头真实抓取时刻（10:34:46）晚于这个午夜
截止点 → `published_dt > cutoff_dt` → `SOURCE_LINK_TIME_INVALID`
(`source_provenance.py:1258-1266`)。方法分布：49 条
`NORMALIZED_FIELD_MATCH_CANDIDATE`、2 条 `ORIGINAL_AGENT_MARKER_CITED`、
1 条 `CONTENT_MATCH_CANDIDATE`——同一个源头，不同的匹配路径，结果一致。
**不是新 bug，是第一轮测试文件里已经记录过的已知特性**（"同一天内的
真实取数时间�不可能早于午夜"），今天只是第一次在真实、非离线构造的
Fresh Run 上真实复现。

**明确不采用的两种做法**（按你的要求）：
- 不把截止时间直接改成当天日末（会反过来允许任何"当天收盘后才发生"的
  真实未来信息，制造新的前瞻风险，而不是修正时区/粒度问题）。
- 不把抓取时间当成披露时间使用（`get_balance_sheet`/`get_cashflow`/
  `get_income_statement` 故意没有接入这条链路，正是为了避免这种混淆——
  `source_provenance.py:441-450` 的既有注释已经写明原因）。

**提案（二选一或组合，均未实现）**：

- **方案 A——按来源自身性质分级比较粒度**：只对明确标注为"当前/实时
  计算快照"而非"某个具体披露事件"的来源类型（目前唯一这样接入的就是
  `fundamental_agent` 的 `get_fundamentals`，`source_provenance.py:441-450`
  已经有这段自我说明文字）在 `validate_source_reference` 里改成
  "两边都归一化到日历日期再比较"，而不是全量日期时间比较；对真正带
  披露时间戳的来源（新闻、`market_agent`）继续用现在的完整日期时间比较，
  不放宽。这样"同一天内抓取"会被接受，但真正跨天的未来数据仍会被拒绝，
  不引入新的前瞻风险。需要新增一个显式的"按来源类型区分比较粒度"的
  开关/参数，而不是全局改行为。
- **方案 B——给 `evidence_cutoff` 补上真实时区下的真实运行时刻，而不是
  裸日期**：如果 `analysis_date` 在产生时能携带这次分析实际发生的墙钟
  时间（而不是被截断成"YYYY-MM-DD"），`_parse_iso_like` 自然能解析出
  一个真实的、当天某一时刻的截止点，而不是被迫退化成午夜。这需要追溯
  `analysis_date` 本身在 run 发起处是怎么产生/传递的（本轮未展开排查，
  只是作为可能的第二条路径记录）。

两个方案都不改变现有的"迟于截止点一律拒绝"的保守默认行为，只是让
"当天但发生在截止点之后"这个具体场景有一个比"永远按裸日期午夜算"更
贴近真实情况的判断依据。本轮未实现任何一个方案。

## 4. 引用保留率表述纠正：真实 VALID 主要不是来自"保留了引用标记"

**(a) 原始报告文本里，字面 `[fragment_id: ...]` 标记出现次数**
（`extract_source_marker_from_text` 实际识别的格式，正则见
`comqutor_alpha/source_provenance.py:1088`）：

| Agent | 原始报告里的字面 marker 次数 |
|---|---|
| news_agent | 0 |
| fundamental_agent | 5 |
| bull_researcher | 1 |
| bear_researcher | 3 |
| research_manager | 2 |
| trader | 1 |
| aggressive_risk_analyst | 2 |
| conservative_risk_analyst | 1 |
| neutral_risk_analyst | 1 |
| portfolio_manager | 1 |

**(b)/(c)/(d) 按 Agent 拆分：claim/evidence 文本里实际保留的 marker 数、
`source_link_status`、`source_link_method`（真实方法 × 真实结果交叉表，
只报告观察计数，不给没有干净分母的百分比）**：

| Agent | 总声明数 | marker 保留数(b) | VALID | TIME_INVALID | NOT_PROVIDED | VALID 中来自 ORIGINAL_AGENT_MARKER_CITED | VALID 中来自 NORMALIZED_FIELD_MATCH_CANDIDATE |
|---|---|---|---|---|---|---|---|
| fundamental_agent | 119 | 5 | 59 | 25 | 35 | 3 | 56 |
| bull_researcher | 67 | 1 | 7 | 5 | 55 | 1 | 6 |
| bear_researcher | 72 | 3 | 9 | 6 | 57 | 3 | 6 |
| research_manager | 17 | 2 | 2 | 2 | 13 | 2 | 0 |
| trader | 7 | 1 | 1 | 0 | 6 | 1 | 0 |
| aggressive_risk_analyst | 49 | 2 | 6 | 3 | 40 | 2 | 4 |
| conservative_risk_analyst | 60 | 1 | 7 | 5 | 48 | 1 | 6 |
| neutral_risk_analyst | 37 | 1 | 5 | 3 | 29 | 1 | 4 |
| portfolio_manager | 40 | 1 | 2 | 3 | 35 | 1 | 1 |
| news_agent | 68 | 0 | 0 | 0 | 68 | 0 | 0 |

**这是对第六轮报告（`round6_amd_fresh_run_20261005.md`）的直接纠正**：
那份报告把 VALID 状态说成"模型真实保留了引用标记"（"真实引用保留率"）
——这个表述不准确。真实情况是：**VALID 的主要来源是
`NORMALIZED_FIELD_MATCH_CANDIDATE`**（后端用claim里提到的某个具体数字，
归一化千分位/M-B-K 量级/四舍五入后，去匹配该 run 自己来源注册表里一个
已保存字段，和模型是否"引用"无关，纯粹是数值巧合匹配）——fundamental_agent
59 条 VALID 里 56 条是这种方式，只有 3 条是真正的字面 marker 保留
(`ORIGINAL_AGENT_MARKER_CITED`)；下游 Agent（bull/bear/风险辩论等）同样
以 `NORMALIZED_FIELD_MATCH_CANDIDATE` 为主，真正保留字面 marker 的只有
1-3 条（占各自总声明数不到 5%）。`CONTENT_MATCH_CANDIDATE`（整段文本
重合，同样不需要显式引用）在本次 run 里一次 VALID 都没有产生。

**结论**：第三轮加的"转述时保留引用"指令，从字面 marker 保留这个角度
衡量，真实效果很弱（下游每个 Agent 平均只有 1-3 条真的把 `[fragment_id:
...]` 字样原样保留下来）。目前测出来的 VALID 率，绝大部分是靠后端
"数字对得上"这条独立机制撑起来的，不能当作"引用转发指令生效"的证据。
两者是完全不同的真实机制，报告里必须分开说，不能合并成一个"保留率"。

## 5. 新闻空返回归因：仅限已保存证据，结论为"未能证实"而非"确认供应商问题"

检查范围：`error_logs/`（只有 `week2_llm_errors.jsonl`，与新闻/工具调用层
无关）、`tradingagents_llm_calls.jsonl`（15 条，只记录 cost/延迟/成功与否/
token 数，从未记录真实消息或工具调用内容）——**全程没有找到任何一条
原始的 news 工具请求/响应日志**。

news_agent 真实报告原文（133 行，已读取完整）确实明确声明：对 AMD 的
`get_news` 查询（1 周/5 周两个窗口）"返回 no articles"，并声称对 NVDA
的对照查询也"返回 no articles"，据此推断"vendor-level news coverage
gap"。真实捕获的 40 条新闻类来源，经核对全部是非 AMD 专属的宏观/大宗
商品类标题（金矿银矿铜矿小盘股、美联储政策、医疗板块），这与模型"转而
抓取宏观新闻"的说法**不矛盾**，但也**不是独立证据**——没有任何原始
工具响应能直接证实"AMD 专属查询真的返回了空列表"这件事本身。

**结论：circumstantially consistent，但 UNDETERMINED**。不升级为
"确认是供应商问题、不是代码问题"，因为没有原始响应可以验证；按你的
要求，本轮没有发起任何新的网络查询去核实。

## 最终结论（简短）

**已证明有效的机制**：
1. 财务来源捕获链路（`get_fundamentals` → `source_capture` →
   `source_registry`）在真实模型、真实数据上确实工作——4 条 financial
   来源全部带真实 excerpt/data_snapshot。
2. 数值归一化匹配（`NORMALIZED_FIELD_MATCH_CANDIDATE`）是目前真实撑起
   VALID 结果的主力机制，在 fundamental_agent 和全部下游 Agent 上都
   真实产生了 VALID 链接。
3. T3 Alpha 分类器在修正口径后，真实精确率 56.67%（17/30）、召回率
   68%——不算高，但是真实、已验证的数字（此前 50% 是统计口径混用导致
   的偏低）。

**正式证据池在哪一步被清零（精确到函数和字段）**：`graph_engine` 的
`v2_verified` 层要求 `content_support_status == HUMAN_REVIEWED`，这次
run 零条通过人工内容复核 → 10/10 Alpha 的 `direction` 字段被清空成
`"unknown"` → `conflict_detector.py` 第 944 行 `resolve_bull_bear` 在
两侧方向都是 `unknown` 时返回 `bull_id=None` → 追加
`DIRECTION_ROLE_UNRESOLVED` → 函数提前返回，真正的可采性评估函数
(`evaluate_conflict_admissibility_verified`) **从未被调用**——这就是
8 对候选冲突 `admissibility` 全部为 `null` 的精确原因，不是证据总量
不够，是方向标签本身被这道门清空了。

**仍需修正的设计/实现问题**：
1. 人工内容复核（HUMAN_REVIEWED）目前是全有或全无的硬门——只要 0 条
   claim 走完人工复核，不论原始层证据多充分（这次 v2 原始层 6/10
   Alpha 有真实、非零证据），正式层都会整体清零到无法判断方向。是否
   需要一个"部分复核也能部分生效"的中间状态，是一个需要产品决策的
   设计问题，本轮不擅自建议具体方案。
2. T3 真实分类精确率只有 56.67%，独立于人工复核门之外也在限制冲突
   证据的真实规模（`evidence_audit` 阶段 75.6% 的候选排除是
   `NON_COMMITTED_MATCH`）。
3. 52 条 TIME_INVALID 的裸日期截止时间 vs 真实抓取时刻冲突，是一个
   真实、尚未修复的设计缺口（本轮只给出两个未实现的方案，见第 3 节）。
4. "引用保留率"这个说法本身具有误导性，必须拆分成"字面 marker 保留"
   和"数值归一化匹配"两个独立数字，不能合并报告。
5. 新闻空返回的供应商侧归因缺乏可独立验证的原始日志——这是一个真实的
   可观测性缺口（工具调用层没有留痕原始请求/响应），不是这次新闻为空
   本身的问题。
