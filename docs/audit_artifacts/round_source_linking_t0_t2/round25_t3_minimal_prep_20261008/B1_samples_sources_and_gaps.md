# B1 冻结的 40 条联合样本（v4）：材料、替换记录与剩余缺口

本文件含系统侧信息（run 内链接状态、实际用途），**不交给复核人**。

| 文件 | 内容 |
|---|---|
| `B1_samples_v4/joint_sample_v4_manifest.json` | 冻结清单，含系统侧信息 |
| `review_form_v4.json`、`review_worksheet_v4.csv` | 盲审表，只含材料 |
| `material_coverage.json` | 每条的事实要素及其材料状态 |
| `replacement_log.json` | 替换时逐个审查过的候选及理由 |
| `collection_list.json` | 采集清单 |

脚本：`tools/build_samples_v4.py`。它对每个材料引用都回到已保存的 run 文件里解析；字段、期间或标题不存在就报错退出。重跑后逐字节相同（有测试）。

## 规则

1. **材料只来自同一 run 当时保存的内容**：`source_registry.json` 里登记的数据行或字段、新闻标题（含来源名称和发布时间），以及 run 保存的日线行情 `market_data_snapshot.json`。Agent 文本（包括其他 Agent 的报告）从不算材料。
2. **事实要素**：claim 本身陈述的具体数字、事件、公告或日期；如果 claim 用"that / its / this"明确指向相邻句，也包括相邻句里的事实。纯评价性措辞（例如"stretched""underappreciated"）不算事实要素。
3. **要素状态（工程判断，逐条写明）**：

   | 状态 | 含义 |
   |---|---|
   | LOCATED | 材料直接写明 |
   | DERIVED | 可由材料计算，算式已写出 |
   | RELATED | 材料相关，但不直接写明，由复核人判断支持程度 |
   | NOT_SAVED | run 没有保存相应材料 |

   一条样本没有 NOT_SAVED 要素为 COMPLETE，部分有为 PARTIAL，全部是 NOT_SAVED 为 NO_MATERIAL，没有事实要素为 NO_FACTUAL_ELEMENT。
4. **15 条原缺材料样本的处理顺序**：
   - 先用已保存材料补齐；
   - 补不齐的，在同格内按冻结的哈希顺序（盐值 `t3v3|`）找第一个材料 COMPLETE 且不重复的候选替换；
   - 再不行，列入采集；
   - 如果 claim 本身没有可核对的事实，记为精确缺口。
5. **选样始终与预测无关**：此时还没有任何预测；没有看任何模型答案；没有为容易答对而换样本；没有用重复表达凑数。

## 原有 25 条的核对结论（对象、期间、单位、时间、上下文）

- **对象**：全部是 AMD 自身的数据、行情或新闻标题，与 claim 的对象一致。
- **期间**：财报行逐条写明期间。"一年前"对照的是 2025-06-30，"环比"对照的是 2026-03-31。
- **单位**：沿用数据源的单位标注，未标注的为货币原值。
- **时间**：
  - 8 条来自 1bad76a7 当天 10:34 的 fundamentals 快照，run 自身判为 TIME_INVALID。材料在 run 开始（17:36Z）之前已存在，是否算"截止前可得"由复核人依表中时间判断。
  - 财报行没有披露日期，`published_at` 为空。
- **上下文**：每条附前后各 2 句。
- 其中 **7 条是 PARTIAL**：t3v3-009、013、016、017、019、025（以及补齐后的 033）。缺的都是预测市场概率、CPI 日期或 AI 芯片出口许可概率。
  - 按"材料真实可核对但不支持也可以是有效样本"的原则保留，由复核人判断支持程度。
  - 本提案没有为这些要素安排采集；如需要，可另行加入采集清单。

## 40 条清单

| 样本 | 格 | 标的 | run | agent | 处理 | 材料状态 | 已保存材料 | 没有保存材料的要素 | run 内链接 | 关键结论 | 原 run 用途 |
|---|---|---|---|---|---|---|---|---|---|---|---|
| t3v3-001 | A304 边界 | AMD | 1bad76a7 | portfolio_manager | 保留 | COMPLETE | 数据字段×1 | — | TIME_INVALID | 是 | — |
| t3v3-002 | A304 边界 | AMD | 1bad76a7 | portfolio_manager | 保留 | COMPLETE | 报表行×4、数据字段×1 | — | VALID | 是 | — |
| t3v3-003 | A304 边界 | AMD | 1bad76a7 | trader | 保留 | COMPLETE | 标题×2、报表行×3、数据字段×3 | — | VALID | 是 | — |
| t3v3-004 | A304 边界 | AMD | 1bad76a7 | portfolio_manager | 保留 | COMPLETE | 标题×2、报表行×1、数据字段×1 | — | TIME_INVALID | 是 | — |
| t3v3-005 | A304 边界 | AMD | c904d4cc | trader | 保留 | COMPLETE | 标题×1、报表行×3、数据字段×3 | — | VALID | 是 | — |
| t3v3-006 | A304 边界 | AMD | c904d4cc | portfolio_manager | 保留 | COMPLETE | 报表行×3、数据字段×2 | — | VALID | 是 | — |
| t3v3-007 | A304 边界 | AMD | 1bad76a7 | conservative_risk_analyst | 保留 | COMPLETE | 数据字段×2 | — | TIME_INVALID | 否 | — |
| t3v3-008 | A304 边界 | AMD | 1bad76a7 | research_manager | 保留 | COMPLETE | 数据字段×3 | — | TIME_INVALID | 否 | 冲突原始池 A304 |
| t3v3-009 | A304 边界 | AMD | c904d4cc | neutral_risk_analyst | 保留 | PARTIAL | 标题×1、数据字段×1 | 96% 不降息概率；76% 再加息概率 | VALID | 否 | — |
| t3v3-010 | A304 边界 | AMD | 1bad76a7 | fundamental_agent | 保留 | COMPLETE | 数据字段×1 | — | TIME_INVALID | 否 | — |
| t3v3-011 | A304 边界 | AMD | 1bad76a7 | conservative_risk_analyst | 保留 | COMPLETE | 数据字段×2 | — | TIME_INVALID | 否 | — |
| t3v3-012 | A304 边界 | AMD | c904d4cc | neutral_risk_analyst | 保留 | COMPLETE | 报表行×1、数据字段×2 | — | VALID | 否 | — |
| t3v3-013 | A304 边界 | AMD | c904d4cc | research_manager | 保留 | PARTIAL | 标题×1、报表行×1、数据字段×5、日线×1 | 政策尾部风险（出口许可概率） | VALID | 否 | 冲突原始池 A304 |
| t3v3-014 | A304 边界 | AMD | c904d4cc | fundamental_agent | 保留 | COMPLETE | 报表行×3、数据字段×1 | — | VALID | 否 | 冲突原始池 A301 |
| t3v3-015 | A304 边界 | AMD | c904d4cc | conservative_risk_analyst | 保留 | COMPLETE | 数据字段×1 | — | VALID | 否 | — |
| t3v3-016 | A304 边界 | AMD | c904d4cc | bull_researcher | 保留 | PARTIAL | 数据字段×1 | 96% 不降息；10 月 15 日 CPI；3.4% 档 4% | VALID | 否 | — |
| t3v3-017 | A101/A103 | AMD | c904d4cc | trader | 保留 | PARTIAL | 数据字段×4 | 10 月 15 日 CPI；45% 出口许可概率 | VALID | 是 | — |
| t3v3-018 | A101/A103 | AMD | 1bad76a7 | bull_researcher | 保留 | COMPLETE | 报表行×1 | — | VALID | 否 | 冲突原始池 A101 |
| t3v3-019 | A101/A103 | AMD | c904d4cc | bear_researcher | 保留 | PARTIAL | 标题×4、报表行×2、数据字段×4、日线×1 | 96%/76% 利率概率；45% 出口许可概率 | VALID | 否 | — |
| t3v3-020 | A101/A103 | AMD | c904d4cc | fundamental_agent | 保留 | COMPLETE | 报表行×2 | — | VALID | 否 | 冲突原始池 A101 |
| t3v3-021 | A101/A103 | AMD | 1bad76a7 | fundamental_agent | 保留 | COMPLETE | 数据字段×1 | — | TIME_INVALID | 否 | — |
| **t3v3-022R** | A101/A103 | AMD | c904d4cc | news_agent | **替换入选** | COMPLETE | 标题×3 | — | 无链接 | 否 | — |
| **t3v3-023** | A101/A103 | AMD | 1bad76a7 | fundamental_agent | **补齐** | COMPLETE | 报表行×4（毛利率 53.8% / 39.8%） | — | 无链接 | 否 | 冲突原始池 A101 |
| **t3v3-024R** | A101/A103 | AMD | 1bad76a7 | fundamental_agent | **替换入选** | COMPLETE | 报表行×3（资本开支、PP&E、在建工程） | — | 无链接 | 否 | 冲突原始池 A101 |
| t3v3-025 | A001 | AMD | 1bad76a7 | aggressive_risk_analyst | 保留 | PARTIAL | 数据字段×1 | 10 月 FOMC 波动率 | TIME_INVALID | 否 | — |
| **t3v3-026** | A001 | AMD | 1bad76a7 | conservative_risk_analyst | **补齐** | COMPLETE | 标题×2、报表行×2、数据字段×3、日线×1 | — | 无链接 | 否 | — |
| **t3v3-027R** | A001 | AMD | 1bad76a7 | news_agent | **替换入选** | COMPLETE | 标题×1 | — | 无链接 | 否 | — |
| **t3v3-028** | A001 | AMD | c904d4cc | news_agent | **补齐** | COMPLETE | 标题×10 | — | 无链接 | 否 | — |
| t3v3-029 | A003 | AMD | 1bad76a7 | fundamental_agent | 保留 | COMPLETE | 报表行×2 | — | VALID | 否 | — |
| t3v3-030 | A003 | AMD | c904d4cc | fundamental_agent | 保留 | COMPLETE | 数据字段×1 | — | VALID | 否 | — |
| t3v3-031 | A003 | AMD | 1bad76a7 | fundamental_agent | 保留 | COMPLETE | 报表行×1 | — | VALID | 否 | — |
| **t3v3-032** | A003 | AMD | c904d4cc | aggressive_risk_analyst | **缺口** | NO_FACTUAL_ELEMENT | — | （修辞，无可核对事实） | 无链接 | 否 | — |
| **t3v3-033** | A102 | NVDA | 034a0a60 | bull_researcher | **保留（部分）** | PARTIAL | 标题×2 | "Multiply that" 指向的 Anthropic 数据点 | 无链接 | 否 | — |
| **t3v3-034** | A102 | NVDA | 034a0a60 | bull_researcher | **补齐** | COMPLETE | 标题×2（Accenture 创纪录订单） | — | 无链接 | 否 | — |
| **t3v3-035** | A102 | NVDA | 034a0a60 | portfolio_manager | **补齐** | COMPLETE | 标题×4（Accenture、IBM 主权 AI、IBM Bob 自托管） | — | 无链接 | 否 | — |
| **t3v3-036** | A102 | NVDA | 034a0a60 | news_agent | **缺口** | NO_FACTUAL_ELEMENT | — | （评价，无可核对事实） | 无链接 | 否 | 冲突原始池 A102 |
| **t3v3-037** | A501 | AMD | 1bad76a7 | news_agent | **待采集** | NO_MATERIAL | — | 美/英/日衰退概率 | 无链接 | 否 | 冲突原始池 A501 |
| **t3v3-038** | A501 | NVDA | 034a0a60 | news_agent | **待采集** | NO_MATERIAL | — | 日本衰退 4%，成交 $4K | 无链接 | 否 | — |
| **t3v3-039** | A501 | NVDA | 034a0a60 | news_agent | **待采集** | NO_MATERIAL | — | 8% 且周降 2pp | 无链接 | 否 | 冲突原始池 A501 |
| **t3v3-040** | A501 | AMD | 1bad76a7 | aggressive_risk_analyst | **待采集** | NO_MATERIAL | — | 衰退概率 8% 且下降 | 无链接 | 否 | 冲突原始池 A501 |

"无链接"是 run 内的 `NOT_PROVIDED`：生产内容核验不会核查这些 claim，系统没有 L1 答案。

## 替换记录（`replacement_log.json` 有逐条理由）

| 被替换 | 原因 | 替换为（同格哈希顺序位置） | 依据的已保存材料 | 审查过的候选 |
|---|---|---|---|---|
| t3v3-022 | 唯一依据是预测市场的衰退概率（未保存） | 022R：c904d4cc news_agent claim 91，"Records are being set by a handful of AI/chip leaders while consumer discretionary is being 'pummeled' by rates."（位置 21） | 两个标题："Nasdaq, Nvidia post record highs…"、"Higher rates are pummeling consumer discretionary stocks…" | 位置 3–21 |
| t3v3-024 | 唯一依据是 AI 芯片出口许可概率 45%（未保存） | 024R：1bad76a7 fundamental_agent claim 95，"AMD is building out capacity/labs, consistent with an AI-driven expansion cycle."（位置 29） | 资本开支 −808 vs −389；net PPE 3,439 vs 2,723；在建工程 1,148 vs 646（百万） | 位置 3–29 |
| t3v3-027 | 唯一依据是预测市场的 FOMC 概率 | 027R：1bad76a7 news_agent claim 23，标题 "Gold Edges Higher as Weak US Jobs Data Reduces Fed Rate-Hike Expectations"（位置 16） | 该标题本身（InvestorsHub，10-05） | 位置 3–16 |

落选理由类别：
- 依据是预测市场数据，未保存；
- 依据是文章正文或日期，不在任何已保存标题中；
- 依据是社交媒体帖子，未保存；
- 依据是公司数据，但 run 没有保存；
- 依据是 Agent 内部记录（工具失败、过往决策收益）；
- 没有可核对的事实；
- 只有部分要素有材料；
- 与已选样本是同一事实或事件。

**A003、A102、A501 三格没有任何合格替换：**
- A003 除 032 外只有 1 个候选，依据是预测市场；
- A102 的候选全部重复 034/035 的事实，或依据社交帖子；
- A501 的 57 个候选都依据预测市场概率，或只有部分材料。

## 剩余缺口与最小采集清单（`collection_list.json`）

| 编号 | 对象 | 来源 | 目的 | 请求上限 |
|---|---|---|---|---|
| C0 | Gamma public-search，查询 "recession 2026"。这是 run 中 news agent 自己用的接口（`tradingagents/dataflows/polymarket.py`） | `gamma-api.polymarket.com/public-search` | 按问题原文识别三个市场，取 Yes token | 1 |
| C1 | "US recession by end of 2026?" 日线价格，2026-09-24 至 10-06 | `clob.polymarket.com/prices-history`（日频） | 034a0a60（10-01/02）和 1bad76a7（10-05）当时的 8% 及周变化；对应 037、039、040 | 1 |
| C2 | "UK recession in 2026?"，同一窗口 | 同上 | 10-05 的 7%；对应 037 | 1 |
| C3 | "Japan recession in 2026?"，同一窗口 | 同上 | 4%；对应 037、038 | 1 |

采集的限制：
- claim 里引用的成交额是累计值，无法还原到当时；
- 遇到第一个非 200、形状不符或传输错误就停止，不再搜索，不超过上限；
- 采集结果绑定本次验证执行（单独目录、原样保存、带哈希和时间），作为复核表补充件交给复核人；不写回旧 run，也不说成旧 run 当时已有的材料。

**不提议的采集**：t3v3-033 的 Anthropic 数据点。run 没有保存它的原始来源线索，要找只能做无边界的网页搜索；这条保持 PARTIAL。

**采集也无法解决的缺口**：t3v3-032、036。claim 本身没有可核对的事实。建议保留它们参与 Alpha、方向和资格判断，R1 填"无法判断"；或从来源环分母中剔除，由负责人决定。
