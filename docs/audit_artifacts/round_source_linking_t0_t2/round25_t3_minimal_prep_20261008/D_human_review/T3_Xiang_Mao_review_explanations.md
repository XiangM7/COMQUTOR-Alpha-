# Xiang Mao｜T3 40条人工审查记录

**审查人：Xiang Mao。全部40条已完成人工审查。**

完成确认时间：2026-10-08 11:28:05（America/Los_Angeles）。

本文记录逐条判定及其理由。材料不足或事实无法确定的条目保留对应状态；这些状态描述证据限制。

## 判断口径

- 允许忠实语义转述、复算和有明确事实输入的合理推论；不要求来源逐字说出投资结论。
- 对象、期间、单位和计算口径须对应。真实四舍五入按声明精度处理；3%不能用来掩盖股价/均线错配或期间改变。“约3倍”与精确3.00倍也不采用同一精度。
- `UNABLE_TO_JUDGE`表示本条材料不足以确定，不表示声明错误。`CONDITIONAL`表示可确认部分但有关键剩余；不是所有if句都自动降级。
- 来源支持与Alpha立场分开；看空事实可以成为有效证据，反驳A304也不能因含not而被当作无效。
- `R2_alpha`按taxonomy语义选择，不把场景格名称当答案；不复现生产门对A001的覆盖作为参考真值。
- `R4`仅为单条内容/Alpha语义资格建议：`QUALIFIES`不代表已通过生产的时间、hash、角色、去重、权重、分数、Exposure或冲突双侧门。未执行这些门，不能补成已通过。
- 已读取随后上传的 `review_materials_frozen_ADDENDUM.json`，仅更新037–040。日采样历史价格可以支持有限比较，不能还原原报告盘中报价，也不证明原run已保存该材料。
- 不采用今天的网络信息回填旧run，也没有新增Provider或搜索请求；只做本地数值计算。

## 关键审查结果

- **005、006、014、039**：人工判定具有单条语义资格；039只支持市场隐含风险低且周下降的有限判断，并且是A501反向证据。这些判定未写回正式评分池。
- **026**：股价/均线对象错配可直接复现，37%不是所附股价高于200日均线的幅度。
- **002、004**：调整EPS及483M投资收益口径未提供；不能把无法复现直接写成造假。
- **001、009、024R、038**：分类或方向具有语义边界，逐条理由保留了相应限制。
- **029–031**：材料正确，但属于公司流动性，不是A003宏观流动性。
- **037–040**：补充件已读。037的精确周变化未证实；038的历史成交量仍缺；039的周下降2pp可复算，8%精确盘中值未确认；040的排他性推论仍缺依据。

## 数值复算

| 项目 | 输入与结果 | 限制 |
|---|---|---|
| FCF环比 | 1558/2566−1 = −39.2829% | 同一单位/季度比较 |
| 应收账款环比 | 7281/6035−1 = +20.6462% | 同一单位/季度比较 |
| 收入环比 | 11536/10253−1 = +12.5134% | 同一单位/季度比较 |
| forward EPS/静态年化 | 15.72189/(1.38×4) = 2.84817倍 | 假设年度口径可比；不预测季节性 |
| forward EPS/TTM EPS | 15.63089/3.92 = 3.98747倍 | 不是已兑现增长 |
| 50日均线/200日均线 | 513.5342/374.7236−1 = 37.0435% | 对象是两根均线 |
| 所附股价/200日均线 | 631.205017/374.7236−1 = 68.4455% | 股价抓取较晚，不能冒充更早价格 |
| 10-06股价/200日均线 | 654.91/379.12−1 = 72.7448% | 仅按所附快照复算 |
| 研发同比 | 2528/1894−1 = 33.4741% | 不证明研发用于哪些产品 |
| 毛利率 | 6203/11536 = 53.7708%；3059/7685 = 39.8048% | 不唯一证明AI产品组合变化 |
| capex比值 | 808/389 = 2.07712倍 | 不是3倍 |
| 上轨/均线距离 | +5.5611%、−5.5565%、−20.7632% | 不是发生概率或确定的目标价 |
| 净现金 | 13.111−4.276 = 8.835（十亿原始币种） | 原币种UNKNOWN不擅自认证USD |

## 037–040补充材料核对（本次更新）

材料是2026-10-08为本次验证采集的历史Yes价格点；不是原run已保存的输入。以下均为对应日期约00:00 UTC的单点，非收盘、均价或原报告盘中取数。相邻两个日采样点不能证明盘中报价一定介于它们之间。

| 样本 | 补充件可复现内容 | 仍未确认的部分 | 审查判定 |
|---|---|---|---|
| 037 | 10-05美国8%、英国7%、日本4.5%；美国09-28→10-05为−0.5pp | 原句日本4%、美国−1pp的同一时刻报价；低风险不能排除宽松理由 | CONDITIONAL，暂不合格 |
| 038 | 日本合约及10-02日采样4.5% | 原句盘中4%和历史成交量$4K | CONDITIONAL，背景，不计为分析性依据 |
| 039 | 美国09-25为10.5%、10-02为8.5%，一周−2.0pp | 原句盘中8%的精确取数/舍入规则 | 核心有限判断获支持，MINOR_DEVIATION；语义资格成立，反对A501 |
| 040 | 美国10-05为8%，对应一周−0.5pp | “熊方论证必须依赖需求崩溃”的排他性连接 | CONDITIONAL，暂不合格 |

美国合约除GDP判据还包含NBER判据，区间涉及2025或2026；英国GDP判据覆盖2026年，日本覆盖Q4 2025至Q4 2026，不能当作同一事件定义的直接横向估计。低市场报价只提供有限风险预期信息，不证明宏观风险为零。039的0.5pp差异相对8.5%为5.88%，不是3%规则内自动相等；这里把精度/时点差异视为核心判断的非材料性限制，保留精确值未确认，而不是追认原句盘中8%已被证实。

本次更新不计算模型准确率；新增采集没有写回旧run，也没有发出任何Provider、搜索或取数请求。

## 40条速览

| 样本 | 来源忠实性 | 来源关系 | Alpha | 对Alpha方向 | 单条资格判定 |
|---|---|---|---|---|---|
| t3v3-001 | UNABLE_TO_JUDGE | CONDITIONAL | A304 | supports_alpha | DOES_NOT_QUALIFY |
| t3v3-002 | UNABLE_TO_JUDGE | CONDITIONAL | A304 | supports_alpha | DOES_NOT_QUALIFY |
| t3v3-003 | UNABLE_TO_JUDGE | CONDITIONAL | A304 | supports_alpha | DOES_NOT_QUALIFY |
| t3v3-004 | UNABLE_TO_JUDGE | CONDITIONAL | A304 | supports_alpha | DOES_NOT_QUALIFY |
| t3v3-005 | FAITHFUL | SUPPORTS | A304 | supports_alpha | QUALIFIES |
| t3v3-006 | FAITHFUL | SUPPORTS | A304 | supports_alpha | QUALIFIES |
| t3v3-007 | UNABLE_TO_JUDGE | CONDITIONAL | A304 | supports_alpha | DOES_NOT_QUALIFY |
| t3v3-008 | UNABLE_TO_JUDGE | CONDITIONAL | A304 | supports_alpha | DOES_NOT_QUALIFY |
| t3v3-009 | UNABLE_TO_JUDGE | CONDITIONAL | A304 | opposes_alpha | DOES_NOT_QUALIFY |
| t3v3-010 | FAITHFUL | SUPPORTS | NONE | NOT_APPLICABLE | DOES_NOT_QUALIFY |
| t3v3-011 | UNABLE_TO_JUDGE | CONDITIONAL | A304 | supports_alpha | DOES_NOT_QUALIFY |
| t3v3-012 | UNABLE_TO_JUDGE | CONDITIONAL | A304 | supports_alpha | DOES_NOT_QUALIFY |
| t3v3-013 | UNABLE_TO_JUDGE | CONDITIONAL | A304 | supports_alpha | DOES_NOT_QUALIFY |
| t3v3-014 | FAITHFUL | SUPPORTS | A304 | supports_alpha | QUALIFIES |
| t3v3-015 | UNABLE_TO_JUDGE | CONDITIONAL | A304 | supports_alpha | DOES_NOT_QUALIFY |
| t3v3-016 | UNABLE_TO_JUDGE | CONDITIONAL | A001 | supports_alpha | DOES_NOT_QUALIFY |
| t3v3-017 | UNABLE_TO_JUDGE | CONDITIONAL | NONE | NOT_APPLICABLE | DOES_NOT_QUALIFY |
| t3v3-018 | UNABLE_TO_JUDGE | CONDITIONAL | A101 | supports_alpha | DOES_NOT_QUALIFY |
| t3v3-019 | UNABLE_TO_JUDGE | CONDITIONAL | A001 | opposes_alpha | DOES_NOT_QUALIFY |
| t3v3-020 | UNABLE_TO_JUDGE | CONDITIONAL | A101 | supports_alpha | DOES_NOT_QUALIFY |
| t3v3-021 | UNABLE_TO_JUDGE | CONDITIONAL | NONE | NOT_APPLICABLE | DOES_NOT_QUALIFY |
| t3v3-022R | UNABLE_TO_JUDGE | CONDITIONAL | NONE | NOT_APPLICABLE | DOES_NOT_QUALIFY |
| t3v3-023 | UNABLE_TO_JUDGE | CONDITIONAL | A101 | supports_alpha | DOES_NOT_QUALIFY |
| t3v3-024R | UNABLE_TO_JUDGE | CONDITIONAL | A103 | supports_alpha | DOES_NOT_QUALIFY |
| t3v3-025 | UNABLE_TO_JUDGE | CONDITIONAL | NONE | NOT_APPLICABLE | DOES_NOT_QUALIFY |
| t3v3-026 | MATERIAL_DEVIATION | CONDITIONAL | A304 | supports_alpha | DOES_NOT_QUALIFY |
| t3v3-027R | FAITHFUL | CITATION_ONLY | A001 | mentions_alpha | DOES_NOT_QUALIFY |
| t3v3-028 | UNABLE_TO_JUDGE | CONDITIONAL | A001 | opposes_alpha | DOES_NOT_QUALIFY |
| t3v3-029 | FAITHFUL | SUPPORTS | NONE | NOT_APPLICABLE | DOES_NOT_QUALIFY |
| t3v3-030 | FAITHFUL | SUPPORTS | NONE | NOT_APPLICABLE | DOES_NOT_QUALIFY |
| t3v3-031 | FAITHFUL | SUPPORTS | NONE | NOT_APPLICABLE | DOES_NOT_QUALIFY |
| t3v3-032 | UNABLE_TO_JUDGE | UNABLE_TO_JUDGE | NONE | NOT_APPLICABLE | DOES_NOT_QUALIFY |
| t3v3-033 | UNABLE_TO_JUDGE | CONDITIONAL | A102 | supports_alpha | DOES_NOT_QUALIFY |
| t3v3-034 | UNABLE_TO_JUDGE | CONDITIONAL | A102 | supports_alpha | DOES_NOT_QUALIFY |
| t3v3-035 | UNABLE_TO_JUDGE | CONDITIONAL | A102 | supports_alpha | DOES_NOT_QUALIFY |
| t3v3-036 | UNABLE_TO_JUDGE | UNABLE_TO_JUDGE | A102 | supports_alpha | DOES_NOT_QUALIFY |
| t3v3-037 | UNABLE_TO_JUDGE | CONDITIONAL | A501 | opposes_alpha | DOES_NOT_QUALIFY |
| t3v3-038 | UNABLE_TO_JUDGE | CONDITIONAL | A501 | neutral_background | DOES_NOT_QUALIFY |
| t3v3-039 | MINOR_DEVIATION | SUPPORTS | A501 | opposes_alpha | QUALIFIES |
| t3v3-040 | UNABLE_TO_JUDGE | CONDITIONAL | A501 | opposes_alpha | DOES_NOT_QUALIFY |

## 逐条理由

### t3v3-001 · AMD

> Where the conservative analyst overreaches: He is right on valuation, right on rate transmission, right on earnings quality — but he commits a category error by sizing the residual against the 52-week low of $188.22.

52周低点188.22与附带字段一致。但“保守派对估值、利率传导和盈利质量都判断正确”及“用52周低点定仓位构成类别错误”不能由一个最低价证明。结合上下文，这里认可估值风险，反对的是过度减仓方案，并非反驳A304本身；该分类存在语义边界。当前缺的是风险与仓位判断的依据，不是188.22这个数造假。

### t3v3-002 · AMD

> His own concession that clean EPS is $1.12 versus reported $1.38 is the tell: at 161x trailing earnings, the market capitalizes the headline, and the headline was partly non-operating.

报告EPS=1.38、TTM P/E=161.08163、非营业项目598M均可在材料定位。clean EPS=1.12没有调整项目、税率或会计口径；简单用(2297−598)/1659约得1.024，也不能替代正确的税后调整计算。因此不认定1.12错误，但不能确认这个关键调整值。高倍数建立在含非营业收益的盈利上，是A304方向的分析；完整命题暂缺支撑。

### t3v3-003 · AMD

> Reasoning: The bear case wins on the three factors that matter for this entry point: FCF collapsed 39% sequentially to $1,558,000,000 as of 2026-06-30 from $2,566,000,000 as of 2026-03-31 [fragmentid: src4045667791b919f9:frag:0] while receivables grew +20.6% QoQ faster than +12.5% revenue growth; the macro setup offers no scenario with both strong demand and falling rates, a direct multiple headwind for a 2.45-beta long-duration asset; and the bull's PEG of 0.64 is circular, built on the very forward EPS estimate in question.

FCF环比−39.283%、应收账款+20.646%、收入+12.513%均复算成立，beta与PEG也一致。现金转换变弱与预测依赖可以支持估值风险分析；但“没有任何强需求与降息并存情景”是过强的排他结论，现有金价/就业标题不能证明；PEG的具体计算口径也未保存。该复合句有可靠财务部分，尚不足以把整项宏观论断一并认证。

### t3v3-004 · AMD

> The conservative analyst's three scenarios (multiple already paid for the front-running; a hawkish rate path compressing a 2.45-beta long-duration multiple; a headline beat flattered by a $483M non-operating investment gain) require no demand collapse.

估值压缩可以在需求没有崩溃时发生，这个机制本身合理，不要求新闻逐字写出结论。beta=2.454成立；但483M“投资收益”未在材料中分项出现，598M是另一口径的非营业项目，不能直接当作同一值，也不能直接判483M错。鹰派路径与已提前定价程度缺具体依据，因此保留部分支持，暂不认证整个复合命题。

### t3v3-005 · AMD

> Reasoning: The Research Manager's verdict is Underweight: the bear won the two decisive exchanges (the forward P/E of 41.67x rests on an EPS estimate of $15.72 [fragmentid: src7e133fa786f7aaa0:frag:0] that requires a 3x acceleration from the current $1.38 quarterly / $5.52 annualized run-rate [fragmentid: src582ac24bf4319648:frag:0], and net cash does not immunize a 167x trailing multiple from duration-driven compression with the 10-year at a 24-year high).

41.668015→41.67、15.72189→15.72、167.11734→167均为合理舍入。季度EPS 1.38按4倍年化为5.52，预测EPS/当前年化约2.848倍，“约3倍”可作一位有效数字的概括，不把它认成精确3.000倍。现金减债为8.835B。高预测倍数依赖未来盈利、净现金不能消除估值风险，是有事实输入的合理推论，来源无需逐字给出Underweight。建议作为A304风险证据；前提是forward EPS为可比年度口径、季度年化只作静态参考。最高收益率信息仅由标题有限支持，不认证收益率水平。这里的QUALIFIES是语义资格建议，不是已通过生产时间/绑定/角色门。

### t3v3-006 · AMD

> His second overreach is the PEG defense — he calls 0.64 "priced for a ramp that the last four quarters of data actually support," but the last four quarters support a trailing inflection, not a forward EPS of $15.72 [fragmentid: src7e133fa786f7aaa0:frag:0] against a current quarterly run-rate of $1.38 [fragmentid: src582ac24bf4319648:frag:0].

PEG 0.64、forward EPS 15.72189与季度EPS 1.38真实可定位；四季度EPS为0.75、0.92、0.84、1.38，收入序列也提供了历史改善依据。命题是“过去改善不能自动证明未来估计已经兑现”，没有断言未来预测必然失败。这个区分可以由已保存数据加逻辑推论支持，属于A304风险而非简单否定词mention。建议具备单条语义资格；年度/季度口径须保持可比，不把原句重写成“未来EPS不可能达到”。

### t3v3-007 · AMD

> If anything, I'd argue for the upper end of that range, and I'd want the residual sized against the 52-week low of $188.22, not the 50-day average, because that's the actual downside reference in a genuine de-rating.

188.22与50日均线513.5342均真实。把52周低点选为减仓压力测试锚，是一种可讨论的策略，不因为含if而自动否决；但“它就是实际下行参考”尚无情景或估值方法说明。上下文确实在表达估值去评级风险，故判A304支持方向。保留分析，不把一个历史最低价当成已核实的未来跌幅或唯一正确仓位锚。

### t3v3-008 · AMD

> Third, valuation rigor: the bull's PEG of 0.64 is circular — it's built on the very sell-side forward EPS estimate that is in question, and if the 4x ramp from TTM $3.92 to $15.63 comes in at 3x, the multiple de-rates violently.

TTM EPS 3.92与forward EPS 15.63089比值约3.987，概括为4倍成立；预测未兑现可能损害高倍数估值，也是合理的条件性风险机制。仍有两处不能据材料认证：供应商PEG是否确实由所称sell-side预测构造，以及3倍兑现是否会导致“剧烈”去评级的幅度。并不是因为句子有条件就拒绝，而是关键计算口径及强度未说明。该句支持A304论点，但当前只能认证其有限部分。

### t3v3-009 · AMD

> He says the prediction markets are pricing 96% odds of no Fed rate cuts in 2026 and 76% odds of another hike, the 10-year is at a 24-year high, AMD's beta is 2.454, and therefore long-duration semiconductor multiples compress.

beta=2.454与标题中的收益率高位说法可定位，但96%和76%的预测市场输入缺失。尤其这是转述对手，后文作者明确“不同意其结论”；不能把引述的multiple compression当作者的正向支持。结合上下文暂选A304/反对方向，具体反驳机制未包含在本句，该方向存在语义边界。引用真实性和立场是两条独立轴。

### t3v3-010 · AMD

> Metric: Forward P/E; Value: 40.40

forward_pe=40.39693舍入到两位小数就是40.40。这个数据陈述有依据，没有文字错误。但单独列出P/E不等于断言估值过高、倍数将压缩或存在风险机制；附近也是指标列表。可保存为有效事实，不能仅因出现P/E就当作A304激活证据。

### t3v3-011 · AMD

> You say the PEG of 0.64 means we're "buying growth at a discount." But that PEG is computed off the very forward estimate that has to be delivered.

0.64与15.63089都存在；指出低PEG依赖未来兑现而非无条件安全，语义上支持A304。可是本条材料没有PEG计算公式、增长期限或预测来源，不能直接认证“该PEG就是由这个forward EPS算出”的具体事实。保留合理估值警示，明确其尚未验证的供应商口径，不要求来源逐字写出投资结论。

### t3v3-012 · AMD

> He says the forward P/E of 41.67 with a PEG of 0.64 is "priced for a ramp that the last four quarters of data actually support." That is the single weakest link in his entire argument, and he states it as if it were self-evident.

41.67和0.64正确，四季度收入也说明已有增长。作者是在反驳估值辩护，不是反驳A304，因此支持A304。关键对比所需的forward EPS和季度EPS只有上下文中的Agent陈述，未列入本条材料；不能用Agent文字代替外部数据。对风险推论可理解，但本条完整核验依据不齐。

### t3v3-013 · AMD

> At $654.91, with a 24-year-high yield backdrop, a forward estimate requiring a 3x acceleration from the current run-rate, stretched technicals on fading volume, and a live policy tail risk, the stock argument governs.

价格654.91、forward EPS 15.72189、季度EPS 1.38及RSI等有材料；年化预测比约2.848倍、股价高于200日均线约72.745%，合理支持预期和价格风险。政策尾部事件缺来源；不同抓取时点的成交量也不宜直接当作同一时刻序列。结论方向是A304，但该复合理由中还有材料性未核实部分，不能把整句全部认证。

### t3v3-014 · AMD

> Traders should treat the forward EPS of $15.72 as the key hurdle — evidence of continued sequential revenue growth and gross-margin defense above 53% is required to justify the multiple.

forward EPS 15.72189、收入11536/10253以及毛利6203提供了输入；当季毛利率约53.771%，环比收入约+12.513%。原句把继续增长及毛利率保持53%以上作为未来估值检验条件，并未声称未来已经满足。这个明确、可追踪的条件性估值警示可以支持A304，不需要材料原文写出同一句交易建议。53%是作者提出的检验线，不是由来源证明的唯一公允估值阈值；不据此宣称Alpha已经active。

### t3v3-015 · AMD

> When you underwrite a position on a PEG of 0.64, you are not underwriting the company — you are underwriting the analyst consensus.

PEG=0.64存在。作者讨论的是把预测当保证的估值风险，A304语义相关，不因“not”自动改mention。但材料只有比率本身，缺供应商预测口径与consensus身份，无法核实“完全是在押注分析师共识”的具体归因。修辞不要求逐字证明，关键口径仍需有依据。

### t3v3-016 · AMD

> If AMD can rally to $654.91 with 96% odds of no cuts priced in, imagine what happens if the October 15 CPI comes in cool — the bear's own report notes the cooler 3.4% bucket sits at just 4%, meaning any downside surprise to inflation is a massive asymmetric upside catalyst.

材料只确认股价654.91；96%无降息、4%凉通胀概率和CPI发布日期没有可核对材料。作者推论是通胀下行可能带来鸽派/折现率利好，故A001、条件性支持方向，并非A304的正向风险证据。但这些概率是“巨大非对称催化剂”的关键依据，当前不具备正式资格；未来事件不能写成已发生。

### t3v3-017 · AMD

> At $654.91 the asymmetry is unfavorable: 5.5% upside to the 691.33 upper band [fragmentid: src388228ad9e12e09d:frag:0] versus 5.5% downside to the 10 EMA at 618.52 and 21% to the 50 SMA at 518.93 [fragmentid: src388228ad9e12e09d:frag:0], with a hot-skewed October 15 CPI and 45% implied odds of AI-chip export licensing legislation as live tail risks.

向上至691.33约5.561%，向下至618.52约5.556%、至518.93约20.763%，数字概括成立。CPI倾向和45%政策概率没有材料。原句主张技术位置/政策风险，不是在讨论AI训练需求或机房、电力等基础设施需求，不能为了A101/A103样本格强行归类。保留有依据的技术计算，不把它自动变为AI Alpha证据。

### t3v3-018 · AMD

> Work-in-process rose to $5,265M from $4,167M — consistent with ramping advanced-node AI products.

在制品5265M与4167M可定位，但比较期间是2026-06对2025-06，不能写成QoQ。原句的“consistent with”是温和推论，可以理解为AI产品扩张论点，较贴近A101而非数据中心设施A103。然而总在制品无法辨认advanced-node AI产品占比，不能排除其他产品/库存原因；AI归因这个核心连接尚缺依据。

### t3v3-019 · AMD

> The macro backdrop is hostile (24-year-high yields, 96% odds of no cuts, 76% odds of a hike, hot inflation leaning), the technicals are stretched (73% above the 200 SMA, RSI 72.95, contracting MACD histogram, fading volume), the working-capital build is a two-edged sword, and there's a live 45% policy tail risk on AI-chip export licensing.

价格/200日均线约+72.745%、RSI=72.95与部分利率标题可核对。96%、76%、45%缺材料；单个MACD值也不足以单独证明“持续收缩”。核心宏观段在表达紧缩/高利率对增长股不利，语义上是A001的反向证据，不能把opposes误当supports或有效NONE。整句包含多项未核实的关键依据，资格暂不成立。

### t3v3-020 · AMD

> R&D is scaling aggressively — $2,528M in Q2'26, up 33.5% YoY — signaling continued heavy investment in AI/accelerator roadmaps.

研发2528M对1894M同比约+33.474%，33.5%成立。总研发增长支持“研发投入加大”，但不能识别其中AI/accelerator项目的实际分配。原句确实提出A101扩张判断；不归A103，因为没有设施/电力/网络需求命题。AI项目归因缺证据，不能把财务数字正确直接等同主题判断已核实。

### t3v3-021 · AMD

> Beta of 2.45 — this is a high-volatility instrument that will amplify any broad semiconductor or AI-theme

beta 2.454舍入2.45正确，可说明对其基准的市场敏感度较高；它不等于总波动率，也不能证明对任何半导体/AI主题变化都放大。本句还在“AI-theme”处截断，不能替作者补完整预测。没有AI需求增长或基础设施建设机制，因此不选A101/A103。

### t3v3-022R · AMD

> Records are being set by a handful of AI/chip leaders while consumer discretionary is being "pummeled" by rates.

标题明确报道Nasdaq/Nvidia创新高和高利率冲击消费可选；这些有限新闻陈述可对应原句。但“只有少数AI/chip领头股”需要市场广度证据，现有标题不足。价格领涨也不能单独证明AI需求或基础设施扩张；没有明确叙事/资金流机制时不硬选A601。可作为市场背景，暂不作为某个Alpha的正式支持。

### t3v3-023 · AMD

> Gross margin expansion to 53.8% from 39.8% a year ago signals a favorable mix shift toward higher-value data center/AI silicon — the core of the AMD investment thesis.

6203/11536约53.771%，3059/7685约39.805%，毛利率提升真实。把它解释为高价值AI/数据中心芯片组合变化，是A101方向的分析，而非A103设施需求。但是总毛利率不能唯一识别产品组合、成本改善或低基数影响，材料没有分部收入/毛利占比。保留推论，AI混合贡献尚未证实。

### t3v3-024R · AMD

> AMD is building out capacity/labs, consistent with an AI-driven expansion cycle.

PPE与在建工程增长支持实物资本投入增加；capex绝对值808/389约2.077倍，上下文“tripled”不是成立的复算，注意它不是本句直接陈述。原句直接谈capacity/labs的实体建设，暂选最接近的A103，但AMD生产/研发设施是否属于taxonomy的计算基础设施需求，是重要边界，A101或NONE仍属于可讨论的替代分类。材料未说明项目性质和AI用途，当前不具备完整资格。

### t3v3-025 · AMD

> But I'd argue the smarter aggressive play is to hold the full position, sell covered calls into the October FOMC vol spike to monetize the event risk, and add on any pullback toward the 50-day average of $513.53.

513.5342→513.53成立。卖covered calls、持满仓及逢回撤加仓是策略建议；FOMC波动率上升和期权溢价未提供。提到FOMC不等于支持降息周期，后文AI建设也不能把本句交易方式改成A101/A103。保留评论或策略，不作为当前Alpha证据。

### t3v3-026 · AMD

> At 161x trailing earnings, 37% above the 200-day, with receivables outrunning revenue and a hawkish Fed, the asymmetry favors the seller.

TTM P/E 161x和应收账款增速快于收入可复现。但513.5342/374.7236−1约37.043%，这是50日均线相对200日均线；所附股价631.205/374.7236−1约68.445%，不是37%。属于对象错配，不能用3%容差或四舍五入放行。鹰派Fed也未由这里的弱就业/加息预期下降标题证明。句子语义支持A304，但内容有材料性偏差；后取的股价快照亦不能假装为更早时点精确价格。

### t3v3-027R · AMD

> "Gold Edges Higher as Weak US Jobs Data Reduces Fed Rate-Hike Expectations" (InvestorsHub) — [fragmentid: not provided]

原句与所附标题吻合，是忠实引述。但“减少加息预期”不等于“已经降息/已启动宽松周期”；上下文也把它与另一市场信号并列，强调不确定性。本句可关联A001话题，暂按引用/提及处理，不当作作者已经论证降息周期成立。标题的真实性不认证文章未提供的正文。

### t3v3-028 · AMD

> Global market news (Yahoo Finance, 2026-09-22 → 2026-10-06) — a clear regime: rates rising sharply, inflation sticky-to-hot, Fed officials hawkish, yet equities at all-time highs led by tech/chips.

多条标题确实涉及收益率走高、通胀压力、鹰派官员和科技股创新高，也有收益率回落/通胀较凉的标题。它们支持对新闻主题的有限概括；“整个时间段是一个明确宏观regime”仍需正文或宏观序列。作者显式将背景与降息周期相反，故A001/反对，不应因为属于失效条件就把语义相关性抹成NONE。当前材料不足以认证完整regime判断。

### t3v3-029 · AMD

> Liquidity is excellent: $13.1B cash + short-term investments against only $4.28B total debt = net cash position of $8.8B.

同一期现金及短期投资13.111B减总债4.276B=净现金8.835B；13.1、4.28、8.8是合理舍入，净现金缓冲的有限推论成立。这里是AMD企业资产负债表流动性，不是A003的宏观货币流动性/风险资产资金流。应保留有效财务事实，但不能因同一个liquidity词就计入A003。货币单位未知须保留，不能补写已确认USD。

### t3v3-030 · AMD

> Current ratio 2.609 — strong liquidity.

current_ratio=2.609直接吻合。在流动资产质量正常的前提下，称其短期偿债缓冲较强是合理有限推论，不代表所有流动资产都能即时变现金。它不是宏观流动性扩张，因此不选A003；正确公司指标可以保留，但不自动成为Alpha激活依据。

### t3v3-031 · AMD

> Working capital expanded to $19,441M from $14,676M a year ago — a strong liquidity buffer.

2026-06营运资本19441M、2025-06为14676M正确，同比约+32.468%。称其为资产负债表缓冲是合理的限定推论，但不把营运资本等同即时现金，库存/应收周转仍需另查。这是企业流动性而非A003宏观扩张，可保存为财务事实，不计为该宏观Alpha的直接支持。

### t3v3-032 · AMD

> That's the aggressive play — you take liquidity when it's offered, not when it's demanded.

没有附来源材料。这是“趁流动性好主动卖出”的交易执行格言，不是在提出货币供给扩张或风险资金流入的事实命题；与A003同词不同义。来源忠实性不能评价，语义上也没有需要计入Alpha的实质事实。保留策略评论，不认定它错误。

### t3v3-033 · NVDA

> Multiply that across the entire AI-native cohort, add sovereign deployments, add enterprise inference — and the demand runway is not a hyperscaler-only story.

IBM主权AI及自托管部署的标题支持相关事件被报道，但Anthropic算力支出、整个AI-native群体规模与NVDA需求传导没有完整材料。句子核心是企业/agent推理需求扩大，选择A102而非单纯训练A101。多场景需求推论有方向，但不能仅凭两条标题认证整个群体扩张。

### t3v3-034 · NVDA

> Its bookings are a direct leading indicator of enterprise AI deployment — the exact inference and agent workload layer that consumes NVDA accelerators.

标题报道Accenture订单及AI需求讨论，不能拆出AI订单占比，也不能证明具体是inference/agent工作负载，更不能直接证明一定消耗NVDA加速器。语义论点明确是A102；从广义IT服务订单到具体芯片需求的关键传导缺来源，当前只能部分支持。

### t3v3-035 · NVDA

> Accenture's record bookings, IBM's sovereign AI agents, and self-hosted enterprise deployment scaling represent a genuine shift from hyperscaler training capex into the inference and enterprise layer — the exact vector that makes NVDA's revenue base more durable, not less.

标题提供Accenture订单、IBM主权AI代理与自托管产品事件的有限依据。核心“企业/推理需求拓宽并使NVDA收入更持久”属于A102支持；但产品推出不等于规模化采用，也不证明NVDA份额、硬件需求量或持久性。因此不是所有内容都无依据，尚缺核心传导与规模的实证。

### t3v3-036 · NVDA

> The enterprise/inference demand vector is the most underappreciated positive.

没有附材料。“企业/推理需求是最被低估的利好”包含A102支持方向，可以判其语义；“underappreciated”还涉及市场定价比较，并非完全无可检验内容。上下文Agent自述不能替代来源，无法验证需求或低估程度，当前作为观点保留。

### t3v3-037 · AMD

> Category: Recession risk; Signal: Low & falling; Evidence: US 8% (−1.0pp); UK 7%; Japan 4%; Implication for AMD: Supports semi demand; removes easing case

补充件中10月5日约00:00 UTC的Yes价格为美国8%、英国7%、日本4.5%；美国9月28日8.5%到10月5日8%是一周−0.5个百分点，不能由这组点确认原句−1.0个百分点。日本10月4日为4%，但不能用另一日的值替代10月5日的取数。原报告实际盘中报价和时间未保存，因此这些差异暂不定为原句数字错误，也不把相邻日价格当作盘中上下界。三个合约的衰退定义和结算区间不同，只能有限支持各自市场隐含风险较低。语义为A501反向；“移除宽松理由”不能由低衰退概率推出，半导体需求传导也没有单独材料。核心有部分支持，整个复合命题仍不足以取得单条资格。

### t3v3-038 · NVDA

> Market: Japan recession in 2026; Implied Probability: 4% Yes; Volume: $4K; 1-Week Move: —

已能定位日本2026衰退合约及其定义：Q4 2025至Q4 2026范围内连续两个季度实际GDP季环比负增长。10月2日约00:00 UTC的Yes价格为4.5%，原句4%的同一盘中时刻不能由日采样确认；不把这个精度/时点差异自动定为错误。4K历史成交量在补充件中明确无法恢复，当前累计成交量不能替代它。来源因此只有部分支持。本条是概率及成交量的表格行，暂保留A501主题、中性背景，不自动成为NVDA需求或全球风险趋势的分析性证据。单条正式语义资格暂不成立；低概率按上下文也可能被解读为opposes_alpha，但这种方向解释不补足成交量。

### t3v3-039 · NVDA

> Read: At 8% and falling 2pp on the week, recession risk is a diminishing concern.

同一美国合约9月25日约00:00 UTC为10.5%，10月2日约00:00 UTC为8.5%，周变化准确为−2.0个百分点；这支持“市场隐含衰退概率低且一周下降，相关担忧减轻”的有限推论。原句8%与日采样8.5%相差0.5个百分点，相对差约5.88%，不能用3%容差自动放行；但它处于整数百分比表述的半个百分点精度边界，也未还原原报告盘中报价及舍入规则。暂标MINOR_DEVIATION，表示核心判断获得支持而精确8%尚未核实，不认定原句错误。假设该合约价格可作市场风险预期的有限代理，不把它当作客观衰退发生率或风险已消失。建议单条语义资格成立，方向是反对A501风险上升，不是正向抬高A501；QUALIFIES不代表已经通过生产时间/来源绑定或进入评分。

### t3v3-040 · AMD

> You can't, because the bear case requires a demand collapse, and recession odds are 8% and falling.

美国合约10月5日约00:00 UTC为8%，9月28日为8.5%，可以支持相应日采样口径下“概率较低、一周下降”的部分；不是每一天都下降，也没有恢复原报告盘中报价。语义是在反驳需求崩溃/衰退风险，仍为A501反方向。但“熊方论证必须以需求崩溃为前提”没有从概率或上下文事实中得到证明，高估值/利率风险可在需求未崩溃时存在。这个排他性连接是原claim的材料性部分，不能仅因8%可定位就认证整句，也不能把低概率解释为风险被排除。因此来源部分支持，完整单条语义资格暂不成立。

## 审查记录与材料范围

- 审查人：Xiang Mao；角色：项目负责人、人工审查人。
- 审查状态：全部40条人工审查已完成。
- 审查完成确认时间：`2026-10-08T11:28:05-07:00`；JSON中的reviewed_at使用该确认时间。
- 本次仅整理审查状态、署名和说明文字；40条的R1、R2、R3、R4判定值、原声明、上下文、材料和排序不变。
- 输入文件SHA256：`6842817f90dd3c4fba1c5adc84301cea2ac971a613d20e51959f54edd756ff42`
- 采用你已提供的T2 taxonomy定义，文件SHA256：`c6d523beaee4942c71756a3fddbb8213d4ba2f8653fded088d73031ca80f3bfa`；与T1快照的10个core_thesis一致，但未取得Round25执行冻结taxonomy文件，不能称完整文件身份已核实一致。
- 补充件SHA256：`afcc90b579dc4e3aacfa9b743351033321f191ce43abf67a2294376efa8631ba`；其review_form绑定哈希与原上传表一致。
- 当前材料未包含补充件所引用的供应商原始响应文件；附件内数值可复算，原始响应hash及上游完整性无法独立核对。
- 本表不证明完整生产时间、hash绑定、角色、去重、Exposure及冲突双侧门已经执行。

本表列示人工审查结果；模型准确率和系统成绩应另由逐条系统预测与本表计算。

