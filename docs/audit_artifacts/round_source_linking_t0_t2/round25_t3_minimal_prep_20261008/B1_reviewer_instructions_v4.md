# 复核说明 v4（给 John 或 John 指定的复核人）

请填写 `B1_samples_v4/review_form_v4.json`，或同内容的 `review_worksheet_v4.csv`。表中**没有任何系统答案**。

复核时请**不要**查看以下内容；如果看过，请在声明栏如实填写：
- `outputs/` 里的系统输出；
- 本目录其他文件；
- 既往报告。

## 每条样本你会看到

- **claim 原文**，以及同一份报告里它前后各 2 句的上下文。
- **时间基准**：分析日期（`analysis_date`）和这次 run 开始的时间（`run_started_at`）。
- **材料**（`material`），是这次 run 当时保存下来的内容，分三种：
  - 数据行或字段：财报某行在各期间的数值，或基本面、行情快照里的字段，带单位、观测日期、发布时间（若有）和获取时间；
  - 新闻标题：标题原文、来源名称、发布时间、URL。**只保存了标题，没有正文**；
  - 日线行情：收盘价、成交量。
- 有些样本写着 **"NO SAVED MATERIAL"**：这次 run 没有为它保存任何材料，来源相关两项请填 UNABLE_TO_JUDGE。
- 如果负责人授权了采集，A501 的几条样本会另外附**补充件**（`review_form_v4_addendum.json`），是为这次验证事后采集的预测市场日线价格：
  - 请按 claim 当天的数值判断；
  - 注意它不是 run 当时保存的材料，Agent 当时看到的是那一天的实时价格。

请只依据提供的材料判断。如果你另外打开过 URL 或查过其他资料，请在 `rationale` 里注明。

## 要填的字段

| 字段 | 可选值 | 怎么判断 |
|---|---|---|
| `R1_claim_fidelity` claim 是否忠实于材料 | FAITHFUL / MINOR_DEVIATION / MATERIAL_DEVIATION / NOT_IN_SOURCE / UNABLE_TO_JUDGE | 把 claim 里的事实（数字、对象、期间、单位）和材料对照。材料里没有的事实算 NOT_IN_SOURCE；没有材料填 UNABLE_TO_JUDGE |
| `R1_source_relation` 材料与 claim 命题的关系 | SUPPORTS / CONDITIONAL / BACKGROUND / CITATION_ONLY / OPPOSES / INSUFFICIENT / UNABLE_TO_JUDGE | 见下方定义 |
| `R2_alpha` | A001 / A003 / A101 / A102 / A103 / A201 / A301 / A304 / A501 / A601 / NONE / UNABLE_TO_JUDGE | 这句 claim 在实质上支持或反对**哪一个** Alpha 的核心论点（只选一个）；都不涉及时填 NONE。只依据下方的 taxonomy 定义 |
| `R3_direction` 对 R2 所选 Alpha 的方向 | supports_alpha / opposes_alpha / mentions_alpha / neutral_background / supports_counter_alpha / NOT_APPLICABLE / UNABLE_TO_JUDGE | R2 填 NONE 时填 NOT_APPLICABLE；supports_counter_alpha 只用于支持下表"对立 Alpha"一列里的某个 Alpha |
| `R4_evidence_eligibility` 单条 claim 的证据资格 | QUALIFIES / DOES_NOT_QUALIFY / UNABLE_TO_JUDGE | 见下方说明 |
| `rationale` | 自由文本 | 一两句理由 |
| `reviewer_id`、`reviewer_role`、`reviewed_at` | — | 复核人身份；角色写"John"或"John 指定（由谁、何时指定）"；复核时间 |
| `attests_no_prior_view_of_system_outputs` | true / false | 复核前是否**没有**看过这条样本的系统输出或既往报告；如实填写，填 false 不作废，会单独统计 |

**R1_source_relation 的定义：**
- SUPPORTS：材料为 claim 的核心命题提供了可靠依据。
- CONDITIONAL：只有在材料本身没有证实的某个假设成立时才算支持；或者 claim 中有实质部分没有依据。
- BACKGROUND：材料是相关背景，但对这个命题既不支持也不反驳。
- CITATION_ONLY：claim 只是提到了这个来源，材料内容本身与命题真假无关。
- OPPOSES：材料实质上反驳或否定这个命题。
- INSUFFICIENT：给出的材料里没有与命题相关的内容。

**R4 只判断这一条 claim 本身**，不判断 Alpha 应不应该激活、处于什么等级，也不判断应不应该产生 Conflict（这些取决于整个 run 的全部证据，一条 claim 决定不了）。

对 R2 所选的 Alpha，这条 claim 能不能作为一条支持性证据？满足以下全部条件填 QUALIFIES：
1. 它是作者自己的分析性陈述，不是问题、未认同的转述或套话；
2. 它是肯定地陈述，没有否定，而且与该 Alpha 的机制相关（支持或条件性支持）；
3. 材料支持它，并且材料在分析时已经存在。时间请对照材料的发布或观测时间、run 开始时间和分析日期。

没有材料的样本无法判断第 3 条，只按第 1、2 条判断。计分时，因链接、时间等机械条件造成的不一致会单独列出，不算语义分歧。

## Alpha 定义（来自 `alpha_taxonomy_v1.yaml`，sha256 `c6d523be…`；只有定义，没有系统 prompt 的规则）

| ID | 名称 | 核心论点 | 触发信号 | 确认信号 | 失效条件 | 对立 Alpha |
|---|---|---|---|---|---|---|
| A001 | Rate Cut Cycle 利率下降周期 | Falling rates lower discount rates and support long-duration growth assets. | Fed pivots dovish; yields fall; inflation cools | growth multiples expand; financial conditions ease | inflation reaccelerates; rates rise; Fed stays restrictive | A501 |
| A003 | Liquidity Expansion 流动性扩张 | Improving liquidity supports risk appetite and equity inflows. | cash moves into risk assets; liquidity improves; reserves rise | broad equity participation; credit conditions improve | liquidity drains; credit tightens; cash hoarding rises | A501 |
| A101 | AI Expansion AI 扩张 | AI training and adoption increase demand for accelerators and AI-related equities. | AI training demand increases; cloud providers raise AI capex | GPU demand rises; accelerator supply tightens; AI revenue grows | AI capex cuts; model demand slows; GPU oversupply | A304 |
| A102 | Inference Explosion 推理爆发 | Enterprise AI applications and AI agents increase inference compute demand. | enterprise AI usage rises; inference workloads grow | cloud inference capacity expands; deployment activity rises | enterprise AI adoption slows; inference costs block deployment | A304 |
| A103 | AI Infrastructure AI 基础设施 | AI buildout drives datacenter, power, cooling, networking, and server demand. | datacenter spending rises; power and cooling demand increases | networking orders rise; server demand rises | datacenter capex delayed; infrastructure bottlenecks worsen | （无） |
| A201 | Semiconductor Supercycle 半导体超级周期 | A chip-cycle upturn improves inventory, pricing, capex, and semiconductor demand. | inventory improves; orders recover; chip demand rises | ASP stabilizes; capex recovers; backlog improves | inventory glut returns; order cuts resume | A304 |
| A301 | Revenue Expansion 收入扩张 | Strong demand raises revenue guidance, EPS revisions, and repricing potential. | guidance raised; demand beats expectations; revenue accelerates | EPS revisions rise; margins hold; bookings strengthen | revenue misses; guide-down; demand weakens | A304 |
| A304 | Multiple Compression 估值压缩 | Rich valuation and high multiples create downside risk despite strong fundamentals. | multiples stretch; valuation risk rises; discount rate rises | stock falls despite earnings; estimates fail to support price | earnings growth exceeds valuation; rates fall sharply | A101、A102、A201、A301、A601 |
| A501 | Recession Risk 衰退风险 | Widening credit spreads and economic slowdown pressure earnings and risk appetite. | credit spreads widen; unemployment rises; PMIs weaken | earnings estimates fall; defensives outperform | growth accelerates; spreads tighten; earnings improve | A001、A003、A601 |
| A601 | Narrative Momentum 叙事动量 | Investor attention and crowded narratives drive reflexive flows and momentum. | media attention rises; flows chase theme; price momentum strengthens | sentiment improves; breadth within theme expands | narrative fatigue; flow reversal; positioning unwind | A304、A501 |

遇到 taxonomy 本身没有说清楚的边界（例如估值风险以问题形式出现、利率驱动和估值后果写在同一句里、点名代工或封装产能的 AI 需求），请按你的理解判断，在 `rationale` 里写明理由；拿不准时填 UNABLE_TO_JUDGE。
