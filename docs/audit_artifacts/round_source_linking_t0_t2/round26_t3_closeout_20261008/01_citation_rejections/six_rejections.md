# 六条引用拒绝：逐条定位与处理

执行 `t3joint-20261008T170322Z-bd99811e` 中，内容核验有 6 条回复被生产校验以 `quote_or_data_not_found` 拒绝。本文件逐条记录：

- 模型实际引用了什么；
- 请求实际给了模型哪些候选内容；
- 哪个函数、哪个条件拒绝了它；
- 问题属于哪一类，以及本轮怎么处理。

**数据来源**
- 逐条事实：`six_rejections_before_fix.json`（修复前）和 `six_rejections_after_all_fixes.json`（修复后），由 `tools/diagnose_citation_rejections.py` 在网络陷阱下生成。
- 请求：用生产请求构建器重建，6 条都与当时实际发送的请求逐字相同。
- 回复：从执行的线路审计里原样读取，没有重新输入。

**判断依据只有一条：引文是否在被引用候选的原文里逐字存在。**
- 人工复核认为 claim 有依据，不等于模型的引用合法；
- 人工复核认为 claim 不成立，也不等于校验器有错。

## 拒绝路径（修复前）

`content_support_llm._validate_response_item` 依次做三项检查：

1. **`_multi_field_citation_valid`**：只在 `used_location` 是点号路径列表（如 `data_snapshot.beta; data_snapshot.x`）时生效。
   - 每一段引文必须写成 `字段名: 值`，字段名要与路径末段相同，值要与路径解析出的真实值相等。
   - 有任何一段不满足，就直接拒绝。
2. **整句原文检查**（`_quote_found_in_excerpt`）：整句引文必须是候选原文的一个连续子串。
3. **数据值检查**（`_data_field_found`）：整句引文作为一个值，要能在数据快照中找到。

三项都不通过时，回复以 `quote_or_data_not_found` 被拒绝。

## 逐条结论

| 样本 | 引用的来源 | 位置（`used_location`） | 引文（原样） | 每段是否在原文里逐字存在 | 修复前被哪项拒绝 | 分类 | 本轮处理 | 修复后系统结论 | 复核人 L1 |
|---|---|---|---|---|---|---|---|---|---|
| t3v3-005 | `src_7e133fa786f7aaa0`，AMD 基本面快照 | `data_snapshot.forward_pe; data_snapshot.forward_eps; data_snapshot.trailing_pe` | `Forward PE=41.668015; Forward EPS=15.72189; PE Ratio (TTM)=167.11734` | 3/3 段逐字存在，各出现 1 次；三条路径的值都相等 | 第 1 项：引文用的是原文自己的 `标签=值` 写法，没有 `:`；而且 `PE Ratio (TTM)` 与字段名 `trailing_pe` 不同 | 定位／格式问题，属于校验器缺陷 | 已修复 | CONDITIONAL（模型自己声明了重要的未支持部分：Underweight 结论、净现金与 10 年期利率） | FAITHFUL／SUPPORTS |
| t3v3-015 | `src_7e133fa786f7aaa0` | 自由文本："data_snapshot.peg_ratio, … ; excerpt containing 'PEG Ratio=0.64' …" | `PEG Ratio=0.64; EPS (TTM)=3.92; Forward EPS=15.72189` | 3/3 段逐字存在 | 第 2 项：用 `; ` 拼接后的整句不是原文子串 | 定位／格式问题，属于校验器缺陷 | 已修复 | CONDITIONAL | UNABLE／CONDITIONAL |
| t3v3-019 | `src_388228ad9e12e09d`，AMD 行情快照 | `data_snapshot.indicators.rsi; data_snapshot.indicators.close_200_sma; data_snapshot.ohlcv.Close` | `rsi=72.95; close_200_sma=379.12; Close=654.91` | 3/3 段逐字存在；标签与字段名完全相同；值都相等 | 第 1 项：唯一原因是分隔符用了 `=`，不是 `:` | 定位／格式问题，属于校验器缺陷 | 已修复 | CONDITIONAL | UNABLE／CONDITIONAL |
| t3v3-029 | `src_d889dd1e36a5d55a`，AMD 资产负债表 | `data_snapshot.all_line_items['Cash …']['2026-06-30'] and …['Total Debt']['2026-06-30']`（不是路径列表） | `Cash Cash Equivalents And Short Term Investments: 2026-06-30=13111000000.0; Total Debt: 2026-06-30=4276000000.0` | 2/2 段逐字存在 | 第 2 项：拼接后的整句不是原文子串 | 定位／格式问题，属于校验器缺陷 | 已修复 | SUPPORTS | FAITHFUL／SUPPORTS |
| t3v3-031 | `src_d889dd1e36a5d55a` | `data_snapshot.all_line_items.Working Capital; …`（含空格，不是合法路径） | `Working Capital: 2026-06-30=19441000000.0; 2025-06-30=14676000000.0; Current Assets: …; Current Liabilities: …` | 4/4 段逐字存在；`2025-06-30=14676000000.0` 在原文中只出现 1 次 | 第 2 项：拼接后的整句不是原文子串 | 定位／格式问题，属于校验器缺陷 | 已修复 | SUPPORTS | FAITHFUL／SUPPORTS |
| t3v3-002 | `src_582ac24bf4319648`，AMD 利润表 | `data_snapshot.all_line_items['Diluted EPS']['2026-06-30']; …['Other Non Operating Income Expenses']['2026-06-30']`（方括号路径） | `Diluted EPS 2026-06-30=1.38; Other Non Operating Income Expenses 2026-06-30=598000000.0` | **0/2 段存在**：原文写的是 `Diluted EPS: 2026-06-30=1.38`，模型去掉了冒号 | 三项都不通过 | 定位／格式问题：模型改写了原文格式，并使用校验器不解析的方括号路径 | **继续拒绝**（发现未修，产品口径待决定） | `quote_or_data_not_found` | UNABLE／CONDITIONAL |

**002 为什么不放行**
- 方括号路径确实指向真实值（1.38 和 598000000.0），但引文文字本身在原文里不存在。
- 要放行，就得新增方括号路径语法，以及"行项目 + 期间"的绑定规则。这已超出现有真实性规则，本轮不加。
- 是否支持这种引用写法，需要负责人决定。
- 即使引用通过，模型的结论是 SUPPORTS，而复核人判断 clean EPS 1.12 无法核实（CONDITIONAL），两者仍不一致。
- 如果需要模型重新作答，列为后续候选，本轮不发送请求。

## 修复内容（`content_support_llm.py`）

新增 `_segmented_literal_citation_valid`，只在原有三项检查都失败后才调用。放行条件全部满足才通过：

- 引文至少有两段（按 `;` 分），而且每一段都在被引用候选的原文中逐字出现，并落在完整词边界上（`rsi=7` 嵌在 `rsi=72.95` 里不算）。
- 如果 `used_location` 是点号路径列表：路径数必须等于段数，且每段的值（最后一个 `=` 或 `:` 之后的部分）必须与对应路径的真实值相等（沿用原有数值规则 `_values_match`）。

以下情况仍然拒绝：
- 原文中真实存在的一对"标签=值"，绑到了错误的路径；
- 改写、换标签或编造的段；
- 路径数与段数不同；
- 未知路径；
- 标签与值被拆开引用。

这些都有构造夹具测试覆盖（`tests/test_t3_closeout_content_support_citation_and_ledger.py`）。

**没有放宽什么**
- 每一段仍要逐字存在，这是单段引文本来就要满足的标准，现在逐段执行；
- 不做归一化或模糊匹配；
- 不修改模型原回答，不代填引用。

## 离线重放证明

- **修复前**：用保存的 60 个真实回复重放整个预测流程，结果与原执行 40 条预测逐字段一致（`05_offline_replay/before_fix/replay_summary.json`）。
- **修复后**：与原执行只有 6 处不同（`05_offline_replay/after_all_fixes/replay_summary.json`）：
  - 上表 5 条的 L1，从任务失败变为有效结论；
  - t3v3-005 的来源资格原因码，从 NOT_REVIEWED 变为 SUPPORT_STATUS_NOT_RESOLVED，仍然不进入激活池。
  - 其他样本、Alpha 结果和方向结果都没有变化。
- **原执行已接受的 11 条**：判定逐条不变（同一测试文件中有测试）。

**这些样本已用于修复，现在转为开发回归用途。** 原冻结预测和正式计分不变；重放结果只作为开发回归视角，见 `05_offline_replay/after_all_fixes/score_DEV_REGRESSION_VIEW_not_official.json`。
