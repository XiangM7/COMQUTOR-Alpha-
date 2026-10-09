# 04 新 40 条联合样本：清单、来源、实际用途与缺口

**本文件含系统侧信息**（run 内链接状态、实际用途），**不交给复核人**。复核人只拿 `04_joint_sample/review_form_v3.json`（或 `review_worksheet_v3.csv`）和 `04_reviewer_instructions.md`。

文件：
- `04_joint_sample/joint_sample_v3_manifest.json`：冻结清单，sha256 `b49224c3…`，执行授权文件里写入完整哈希。
- `04_joint_sample/review_form_v3.json`：盲审表单，不含任何系统答案。
- `04_joint_sample/review_worksheet_v3.csv`：同一表单的表格版。
- `04_joint_sample_pool_scan.json`：候选池扫描结果。

脚本：`tools/scan_joint_pool.py`、`tools/select_joint_sample.py`。重跑后三个输出文件逐字节相同。

## 1. 选样规则（机械规则，不看被评模型的答案）

- **候选来源。** 只用三个带来源登记表的根 run：034a0a60（NVDA，10-02）、1bad76a7（AMD，10-05）、c904d4cc（AMD，10-06）。选样时**没有打开** `alpha_matches.json` 或方向审计。
- **按 claim 文本归格。** 一条 claim 匹配某格的情形规则（`scan_joint_pool.SCENARIOS`），就是该格的候选。规则只看 claim 文本。
- **格内排序。** 按 `sha256("t3v3|"+claim_id)` 排序，不按"好不好预测"挑。
- **优先级。**
  1. 来源带真实正文（数据行或摘录）的 claim 优先。
  2. 在这些里，关键结论 claim 先取。判定用生产规则 `evidence_trace.key_conclusion_group`，它只看 agent、章节和措辞。
  3. A304 格按 John 五类情形的文本线索轮流取。
  4. 只有 Agent 文本、没有来源正文的 claim，只在有正文的候选用完后才补位，并标为"部分链"。
- **去重。** 去掉同一 claim 的复述：Jaccard 相似度 ≥0.8；或两条都 ≥6 个词且重叠系数 ≥0.6；或同一来源、同一组数字。
- **事后标注。** 选完之后才附上"实际用途"和"文档曝光"，只写在清单里，不给复核人看。
- **John 没有规定关键结论样本的比例**，本轮也不设比例，只报告实际覆盖。

## 2. 配额与缺口

| 格 | 配额 | 完整链（有来源正文） | 部分链（无来源正文） | 有正文的候选数 | 说明 |
|---|---|---|---|---|---|
| A304 边界 | 16 | 16 | 0 | 62 | 足够 |
| A101/A103 | 8 | 5 | 3 | 7 | 有正文的候选只有 7 条，去重后剩 5 条 |
| A001 | 4 | 1 | 3 | 2 | 缺口 |
| A003 | 4 | 3 | 1 | 4 | 缺口 1 条 |
| A102 | 4 | **0** | 4 | 0 | **全部缺正文** |
| A501 | 4 | **0** | 4 | 1 | **全部缺正文**（唯一 1 条候选见下） |
| 合计 | 40 | 25 | 15 | — | — |

**缺口原因。** 这些 run 里，news 类来源只保存了标题和 URL，没有正文。带正文的来源只有 financial 和 market 两类，都是 yfinance 数据快照。所以宏观类（A001、A501）和推理需求类（A102）几乎没有能对上原始依据的 claim。

**A501 唯一的有正文候选**（c904d4cc bull_researcher claim 96，"…recession odds at 7% and falling…"）被去重规则排除：它和 t3v3-012 引用同一来源、同一组数字（41.67、0.64）。而且它链接的来源是 AMD fundamentals 快照，里面**没有任何衰退相关内容**。就算选进来，A501 那部分也没有原始依据。

**15 条部分链样本的处理。**
- 照样进入表单，这样配额是满的。
- 但**来源忠实性环（R1/L1）在这 15 条上判定为"无法判断"**，系统侧记为 `NOT_JUDGEABLE_NO_SOURCE_CONTENT`，**不计入来源环的分母**。
- **不能说"来源忠实性环已完成"**：25 条完整链之外，A102 和 A501 两格没有一条有原始依据。

**另有 8 条完整链样本的链接在 run 内是 `TIME_INVALID`**（1bad76a7 当天 10:34 的 fundamentals 快照）。生产规则只对 `VALID` 链接做内容核查，所以这 8 条**系统不会给出 L1 答案**，L4 会因为链接状态在机械层面不合格。复核人仍可以根据快照内容判断 R1。

**有限补料方案**（**本轮不执行，不取数，不跑 Fresh**）：
- 将来如果要补齐 A102、A501、A001 的完整链，需要一次**专门保存新闻正文**的授权运行，或一次有授权的取数。
- 补进来的样本按同一选样脚本、新盐值另行冻结，不替换本轮的 40 条。
- 是否需要补、补多少，由负责人决定。

## 3. 覆盖事实（只报告，不设比例）

- **关键结论 claim：7/40**（A304 6 条、A101/A103 1 条）。
- **在保存 run 里实际进入冲突原始池：11/40**：A304 2 条、A301 1 条、A101 4 条、A102 1 条、A501 3 条。
  - c904d4cc 系列的正式 Alpha 证据池（dependency-20261007T220450Z 的 `evidence_trace`）对这些 claim **全部为空**。
  - 1bad76a7 和 034a0a60 **没有记录正式池**。
- **标的集中：AMD 33 条、NVDA 7 条。** 原因是只有这三个 run 带来源登记表。**不是对市场的代表性抽样。**
- **完整链的来源全部是数据行**（yfinance 快照），没有文本摘录类来源。
- **文档曝光：**
  - c904d4cc 和 034a0a60 的样本出现在 1–2 份既有报告里（`.md` 或 `.csv`），报告里可能有系统答案。
  - 1bad76a7 的样本没有出现在任何报告里。
  - 表单要求复核人声明是否看过系统输出。

## 4. 样本清单

| 样本 | 格 | 标的 | run | agent | 链 | 来源 | run 内链接 | 关键结论 | 保存 run 中的实际用途 | 曾出现的报告数 |
|---|---|---|---|---|---|---|---|---|---|---|
| t3v3-001 | A304 边界 | AMD | 1bad76a7 | portfolio_manager | 完整 | AMD fundamentals snapshot 2026-10-05 10:34:46（数据行） | TIME_INVALID | 是 | 未进入冲突原始池；正式池未记录 | 0 |
| t3v3-002 | A304 边界 | AMD | 1bad76a7 | portfolio_manager | 完整 | AMD income statement Total Revenue 2026-06-30 季度（数据行） | VALID | 是 | 未进入冲突原始池；正式池未记录 | 0 |
| t3v3-003 | A304 边界 | AMD | 1bad76a7 | trader | 完整 | AMD cash flow Free Cash Flow 2026-06-30 季度（数据行） | VALID | 是 | 未进入冲突原始池；正式池未记录 | 0 |
| t3v3-004 | A304 边界 | AMD | 1bad76a7 | portfolio_manager | 完整 | AMD fundamentals snapshot 2026-10-05 10:34:46（数据行） | TIME_INVALID | 是 | 未进入冲突原始池；正式池未记录 | 0 |
| t3v3-005 | A304 边界 | AMD | c904d4cc | trader | 完整 | AMD fundamentals snapshot 2026-10-06 10:37:04（数据行） | VALID | 是 | 未进入（正式池已记录） | 1 |
| t3v3-006 | A304 边界 | AMD | c904d4cc | portfolio_manager | 完整 | AMD fundamentals snapshot 2026-10-06 10:37:04（数据行） | VALID | 是 | 未进入（正式池已记录） | 2 |
| t3v3-007 | A304 边界 | AMD | 1bad76a7 | conservative_risk_analyst | 完整 | AMD fundamentals snapshot 2026-10-05 10:34:46（数据行） | TIME_INVALID | 否 | 未进入冲突原始池；正式池未记录 | 0 |
| t3v3-008 | A304 边界 | AMD | 1bad76a7 | research_manager | 完整 | AMD fundamentals snapshot 2026-10-05 10:34:46（数据行） | TIME_INVALID | 否 | 冲突原始池 A304 | 0 |
| t3v3-009 | A304 边界 | AMD | c904d4cc | neutral_risk_analyst | 完整 | AMD fundamentals snapshot 2026-10-06 10:37:04（数据行） | VALID | 否 | 未进入（正式池已记录） | 1 |
| t3v3-010 | A304 边界 | AMD | 1bad76a7 | fundamental_agent | 完整 | AMD fundamentals snapshot 2026-10-05 10:34:46（数据行） | TIME_INVALID | 否 | 未进入冲突原始池；正式池未记录 | 0 |
| t3v3-011 | A304 边界 | AMD | 1bad76a7 | conservative_risk_analyst | 完整 | AMD fundamentals snapshot 2026-10-05 10:34:46（数据行） | TIME_INVALID | 否 | 未进入冲突原始池；正式池未记录 | 0 |
| t3v3-012 | A304 边界 | AMD | c904d4cc | neutral_risk_analyst | 完整 | AMD fundamentals snapshot 2026-10-06 10:37:04（数据行） | VALID | 否 | 未进入（正式池已记录） | 1 |
| t3v3-013 | A304 边界 | AMD | c904d4cc | research_manager | 完整 | AMD verified market snapshot 2026-10-06（数据行） | VALID | 否 | 冲突原始池 A304 | 1 |
| t3v3-014 | A304 边界 | AMD | c904d4cc | fundamental_agent | 完整 | AMD fundamentals snapshot 2026-10-06 10:37:04（数据行） | VALID | 否 | 冲突原始池 A301 | 1 |
| t3v3-015 | A304 边界 | AMD | c904d4cc | conservative_risk_analyst | 完整 | AMD fundamentals snapshot 2026-10-06 10:37:04（数据行） | VALID | 否 | 未进入（正式池已记录） | 1 |
| t3v3-016 | A304 边界 | AMD | c904d4cc | bull_researcher | 完整 | AMD verified market snapshot 2026-10-06（数据行） | VALID | 否 | 未进入（正式池已记录） | 1 |
| t3v3-017 | A101/A103 | AMD | c904d4cc | trader | 完整 | AMD verified market snapshot 2026-10-06（数据行） | VALID | 是 | 未进入（正式池已记录） | 1 |
| t3v3-018 | A101/A103 | AMD | 1bad76a7 | bull_researcher | 完整 | AMD balance sheet Total Assets 2026-06-30 季度（数据行） | VALID | 否 | 冲突原始池 A101 | 0 |
| t3v3-019 | A101/A103 | AMD | c904d4cc | bear_researcher | 完整 | AMD verified market snapshot 2026-10-06（数据行） | VALID | 否 | 未进入（正式池已记录） | 1 |
| t3v3-020 | A101/A103 | AMD | c904d4cc | fundamental_agent | 完整 | AMD income statement Total Revenue 2026-06-30 季度（数据行） | VALID | 否 | 冲突原始池 A101 | 1 |
| t3v3-021 | A101/A103 | AMD | 1bad76a7 | fundamental_agent | 完整 | AMD fundamentals snapshot 2026-10-05 10:34:46（数据行） | TIME_INVALID | 否 | 未进入冲突原始池；正式池未记录 | 0 |
| t3v3-022 | A101/A103 | AMD | 1bad76a7 | bull_researcher | 部分 | — | NOT_PROVIDED | 否 | 未进入冲突原始池；正式池未记录 | 0 |
| t3v3-023 | A101/A103 | AMD | 1bad76a7 | fundamental_agent | 部分 | — | NOT_PROVIDED | 否 | 冲突原始池 A101 | 0 |
| t3v3-024 | A101/A103 | AMD | c904d4cc | bear_researcher | 部分 | — | NOT_PROVIDED | 否 | 冲突原始池 A101 | 1 |
| t3v3-025 | A001 | AMD | 1bad76a7 | aggressive_risk_analyst | 完整 | AMD fundamentals snapshot 2026-10-05 10:34:46（数据行） | TIME_INVALID | 否 | 未进入冲突原始池；正式池未记录 | 0 |
| t3v3-026 | A001 | AMD | 1bad76a7 | conservative_risk_analyst | 部分 | — | NOT_PROVIDED | 否 | 未进入冲突原始池；正式池未记录 | 0 |
| t3v3-027 | A001 | AMD | 1bad76a7 | news_agent | 部分 | — | NOT_PROVIDED | 否 | 未进入冲突原始池；正式池未记录 | 0 |
| t3v3-028 | A001 | AMD | c904d4cc | news_agent | 部分 | — | NOT_PROVIDED | 否 | 未进入（正式池已记录） | 1 |
| t3v3-029 | A003 | AMD | 1bad76a7 | fundamental_agent | 完整 | AMD balance sheet Total Assets 2026-06-30 季度（数据行） | VALID | 否 | 未进入冲突原始池；正式池未记录 | 0 |
| t3v3-030 | A003 | AMD | c904d4cc | fundamental_agent | 完整 | AMD fundamentals snapshot 2026-10-06 10:37:04（数据行） | VALID | 否 | 未进入（正式池已记录） | 1 |
| t3v3-031 | A003 | AMD | 1bad76a7 | fundamental_agent | 完整 | AMD balance sheet Total Assets 2026-06-30 季度（数据行） | VALID | 否 | 未进入冲突原始池；正式池未记录 | 0 |
| t3v3-032 | A003 | AMD | c904d4cc | aggressive_risk_analyst | 部分 | — | NOT_PROVIDED | 否 | 未进入（正式池已记录） | 1 |
| t3v3-033 | A102 | NVDA | 034a0a60 | bull_researcher | 部分 | — | NOT_PROVIDED | 否 | 未进入冲突原始池；正式池未记录 | 2 |
| t3v3-034 | A102 | NVDA | 034a0a60 | bull_researcher | 部分 | — | NOT_PROVIDED | 否 | 未进入冲突原始池；正式池未记录 | 2 |
| t3v3-035 | A102 | NVDA | 034a0a60 | portfolio_manager | 部分 | — | NOT_PROVIDED | 否 | 未进入冲突原始池；正式池未记录 | 2 |
| t3v3-036 | A102 | NVDA | 034a0a60 | news_agent | 部分 | — | NOT_PROVIDED | 否 | 冲突原始池 A102 | 2 |
| t3v3-037 | A501 | AMD | 1bad76a7 | news_agent | 部分 | — | NOT_PROVIDED | 否 | 冲突原始池 A501 | 0 |
| t3v3-038 | A501 | NVDA | 034a0a60 | news_agent | 部分 | — | NOT_PROVIDED | 否 | 未进入冲突原始池；正式池未记录 | 2 |
| t3v3-039 | A501 | NVDA | 034a0a60 | news_agent | 部分 | — | NOT_PROVIDED | 否 | 冲突原始池 A501 | 2 |
| t3v3-040 | A501 | AMD | 1bad76a7 | aggressive_risk_analyst | 部分 | — | NOT_PROVIDED | 否 | 冲突原始池 A501 | 0 |

"冲突原始池"指：保存 run 的冲突仲裁中，这条 claim 被列为某一侧的 `qualifying_claim_ids`。它说明这条证据**真实进入过**冲突候选评估，但不代表冲突成立。
