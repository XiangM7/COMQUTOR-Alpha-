# TradingAgents 输出链路和 COMQUTOR 接入点

目标：每次运行 TradingAgents 后，把每个 Agent 的原始输出保存下来，形成 COMQUTOR structure layer 可以稳定读取的标准输入。

目标输出目录：

- `outputs/runs/{run_id}/raw_agent_outputs.json`
- `outputs/runs/{run_id}/final_report.md`
- `outputs/runs/{run_id}/metadata.json`

`metadata.json` 建议字段：

| 字段 | 示例 |
|---|---|
| `run_id` | `uuid` |
| `ticker` | `NVDA` |
| `created_at` | `2026-01-01T10:00:00Z` |
| `model` | `gpt-4.1` |
| `agents` | `fundamental_agent`, `technical_agent`, `news_agent`, `sentiment_agent` |

`raw_agent_outputs.json` 建议结构：`run_id`、`ticker`、`agent_outputs`。其中 `agent_outputs` 是数组，每一项包含 `agent` 和 `raw_output`。

## Week 1B implementation status

Week 1B 已经落地：

- `tradingagents/comqutor_outputs.py` 负责保存 COMQUTOR raw outputs。
- `cli/main.py` 在 `final_state` 合并完成后调用保存函数。
- 每次运行会创建 `outputs/runs/{run_id}/`。
- 输出文件是 `raw_agent_outputs.json`、`final_report.md`、`metadata.json`。
- 保存失败只会写入系统消息，不会中断 TradingAgents 原本流程。

## Week 1J End-to-End Validation

Week 1J 用 fake `final_state` 验证 raw-output capture，不运行真实 TradingAgents，也不调用付费 API。

验收重点：

- `raw_agent_outputs.json`、`metadata.json`、`final_report.md` 都能生成。
- `metadata.json` 包含 `run_id` 和 `ticker`。
- `raw_agent_outputs.json` 包含 `agent_outputs`。
- 原始 `reports/` 行为不变。
- `outputs/runs/` 被 Git ignore。

## Week 2 Structure Graph Layer

Week 2 已经新增第一版 COMQUTOR structure layer：

- Week 1B 保存 raw Agent output。
- Week 2 读取 `raw_agent_outputs.json`。
- Week 2 生成 `structure_graph.json`。
- `structure_graph.json` 包含 `nodes`、`edges`、`conflicts` 和 `summary`。
- 当前使用 deterministic rule-based extraction，不调用 LLM。
- Week 3 可以继续增强 conflict intelligence 和 admissibility scoring。

## Week 3 Conflict Intelligence Layer

Week 3 读取 `structure_graph.json`，生成 `conflict_intelligence.json`。

它负责：

- 识别结构冲突。
- 给冲突打 severity 和 confidence。
- 判断 admissibility。
- 判断是否需要人工复核。
- 判断最终决策是否可以自动接受。

Week 3 不调用 LLM。Week 3J 会用 fake state 验证完整 Week 3 pipeline。

## Week 4 Alpha Memory Layer

Week 4 读取 `metadata.json`、`structure_graph.json` 和 `conflict_intelligence.json`，生成 `alpha_memory_record.json`。

`alpha_memory_record.json` 是 COMQUTOR Alpha Memory v1 的本地记忆记录。它保存一次分析运行的：

- final decision snapshot
- structure summary
- conflict summary
- memory tags
- future outcome placeholder

Week 4 不抓取未来价格，不计算真实收益，不做 backtesting，也不调用 LLM。

Week 4 的目的，是把一次 TradingAgents + COMQUTOR 结构分析保存成未来可以检索、复盘和 outcome learning 的样本。

完整输出链路现在是：

- `metadata.json`
- `raw_agent_outputs.json`
- `final_report.md`
- `structure_graph.json`
- `conflict_intelligence.json`
- `alpha_memory_record.json`

## Week 4J End-to-End Validation

Week 4J 验证整个本地 pipeline，不运行真实 TradingAgents，也不调用付费 API。

本地 fake state 或旧报告 replay 成功后，预期 `outputs/runs/{run_id}/` 中包含六个文件：

- `metadata.json`
- `raw_agent_outputs.json`
- `final_report.md`
- `structure_graph.json`
- `conflict_intelligence.json`
- `alpha_memory_record.json`

验收重点：

- `alpha_memory_record.json` 存在。
- `schema_version` 是 `week4.alpha_memory.v1`。
- `decision_snapshot`、`agent_signal_summary`、`conflict_summary`、`memory_tags` 和 `future_outcome` 都存在。
- `future_outcome.status` 是 `pending`。
- `outputs/runs/` 仍然被 Git ignore，不提交生成数据。

## Week 5 Alpha Outcome Tracking Layer

Week 5 读取 `alpha_memory_record.json`，更新其中的 `future_outcome`。

它支持两种本地输入：

- 手动输入 `price_at_analysis`、`price_after_1d`、`price_after_5d`、`price_after_20d`
- 使用本地 CSV 文件输入 `ticker,date,close`

当价格存在时，Week 5 会计算：

- `realized_return_1d`
- `realized_return_5d`
- `realized_return_20d`

`outcome_label` 使用最长可用 horizon：

- 优先使用 20d
- 其次使用 5d
- 再使用 1d
- 如果没有 realized return，则保持 `pending`

Week 5 不联网抓价格，不调用 LLM，不做完整 backtesting。

Week 5 的目标，是把 Alpha Memory 从“只有分析时判断”推进到“可以记录后来结果”，为未来 outcome learning 做准备。

## Week 5J End-to-End Validation

Week 5J 验证本地 outcome update，不运行真实 TradingAgents，不调用付费 API。

验证方式：

- 使用 `compileall` 检查 `tradingagents/comqutor_outcome.py` 和 `scripts/update_alpha_outcome.py`
- 使用 manual price update 更新 `future_outcome`
- 使用 `data/manual_prices/NVDA_outcome_sample.csv` 做 CSV update
- 确认 `future_outcome.status` 从 `pending` 变成 `partially_updated` 或 `completed`
- 确认原来的 `decision_snapshot` 和 `conflict_summary` 保持不变
- 确认 `outputs/runs/` 仍然不提交

## 1. ticker 输入后的入口

CLI 入口：`cli/main.py`

主要函数：

- `get_user_selections()`
- `run_analysis()`

`get_user_selections()` 负责收集 ticker、分析日期、输出语言、analyst、LLM provider、quick/deep 模型等用户选择。

`run_analysis()` 负责创建 `TradingAgentsGraph`，初始化 state，然后执行 `graph.graph.stream(...)`。CLI 会把 stream 过程中产生的 `chunk` 放进 `trace`，最后合并成 `final_state`。

程序化入口：`tradingagents/graph/trading_graph.py`

主要函数：

- `TradingAgentsGraph.propagate(...)`
- `TradingAgentsGraph._run_graph(...)`

未来如果做平台化自动运行，优先考虑从 `TradingAgentsGraph.propagate(...)` 或 `_run_graph(...)` 进入，而不是依赖 CLI 交互。

## 2. TradingAgents 整体流程

流程定义位置：`tradingagents/graph/setup.py`

核心函数：`GraphSetup.setup_graph(selected_analysts)`

整体链路：

用户输入 ticker -> Analyst Team -> Bull / Bear Research Debate -> Research Manager -> Trader -> Risk Analysts -> Portfolio Manager -> Final Decision

用户可选 analyst：

- `market`
- `social`
- `news`
- `fundamentals`

后续固定流程：

- `Bull Researcher`
- `Bear Researcher`
- `Research Manager`
- `Trader`
- `Aggressive Analyst`
- `Conservative Analyst`
- `Neutral Analyst`
- `Portfolio Manager`

## 3. 每个 Agent 的输出位置

状态字段定义在：`tradingagents/agents/utils/agent_states.py`

核心 state：`AgentState`

| Agent | 生成文件 / 函数 | 输出字段 | 含义 |
|---|---|---|---|
| Market Analyst | `tradingagents/agents/analysts/market_analyst.py` / `create_market_analyst(...)` | `market_report` | 市场/技术分析 |
| Sentiment Analyst | `tradingagents/agents/analysts/sentiment_analyst.py` / `create_sentiment_analyst(...)` | `sentiment_report` | 情绪分析 |
| News Analyst | `tradingagents/agents/analysts/news_analyst.py` / `create_news_analyst(...)` | `news_report` | 新闻和宏观分析 |
| Fundamentals Analyst | `tradingagents/agents/analysts/fundamentals_analyst.py` / `create_fundamentals_analyst(...)` | `fundamentals_report` | 基本面分析 |
| Bull Researcher | `tradingagents/agents/researchers/bull_researcher.py` / `create_bull_researcher(...)` | `investment_debate_state.bull_history` | 多头观点 |
| Bear Researcher | `tradingagents/agents/researchers/bear_researcher.py` / `create_bear_researcher(...)` | `investment_debate_state.bear_history` | 空头观点 |
| Research Manager | `tradingagents/agents/managers/research_manager.py` / `create_research_manager(...)` | `investment_plan` / `investment_debate_state.judge_decision` | 多空辩论后的投资计划 |
| Trader | `tradingagents/agents/trader/trader.py` / `create_trader(...)` | `trader_investment_plan` | 交易计划 |
| Aggressive Analyst | `tradingagents/agents/risk_mgmt/aggressive_debator.py` / `create_aggressive_debator(...)` | `risk_debate_state.aggressive_history` | 激进风险观点 |
| Conservative Analyst | `tradingagents/agents/risk_mgmt/conservative_debator.py` / `create_conservative_debator(...)` | `risk_debate_state.conservative_history` | 保守风险观点 |
| Neutral Analyst | `tradingagents/agents/risk_mgmt/neutral_debator.py` / `create_neutral_debator(...)` | `risk_debate_state.neutral_history` | 中性风险观点 |
| Portfolio Manager | `tradingagents/agents/managers/portfolio_manager.py` / `create_portfolio_manager(...)` | `final_trade_decision` / `risk_debate_state.judge_decision` | 最终交易决策 |

## 4. Bull / Bear debate 的输入和输出

文件位置：

- Bull：`tradingagents/agents/researchers/bull_researcher.py`
- Bear：`tradingagents/agents/researchers/bear_researcher.py`

输入字段：

- `market_report`
- `sentiment_report`
- `news_report`
- `fundamentals_report`
- `investment_debate_state.history`
- `investment_debate_state.current_response`

Bull 输出：

- `investment_debate_state.bull_history`
- `investment_debate_state.history`
- `investment_debate_state.current_response`

Bear 输出：

- `investment_debate_state.bear_history`
- `investment_debate_state.history`
- `investment_debate_state.current_response`

Research Manager 位置：`tradingagents/agents/managers/research_manager.py`

Research Manager 读取 `investment_debate_state.history`，生成 `investment_plan` 和 `investment_debate_state.judge_decision`。

## 5. Final decision 生成位置

Final Decision 由 Portfolio Manager 生成。

文件：`tradingagents/agents/managers/portfolio_manager.py`

函数：

- `create_portfolio_manager(llm)`
- `portfolio_manager_node(state)`

主要输入：

- `investment_plan`
- `trader_investment_plan`
- `risk_debate_state.history`
- `past_context`

输出：

- `final_trade_decision`
- `risk_debate_state.judge_decision`

## 6. 当前 markdown report 保存位置

保存逻辑：`tradingagents/reporting.py`

函数：`write_report_tree(final_state, ticker, save_path)`

保存内容：

- `1_analysts/market.md`
- `1_analysts/sentiment.md`
- `1_analysts/news.md`
- `1_analysts/fundamentals.md`
- `2_research/bull.md`
- `2_research/bear.md`
- `2_research/manager.md`
- `3_trading/trader.md`
- `4_risk/aggressive.md`
- `4_risk/conservative.md`
- `4_risk/neutral.md`
- `5_portfolio/decision.md`
- `complete_report.md`

这套 markdown 输出适合人看。COMQUTOR 还需要额外保存结构化 JSON，方便后续程序稳定读取。

## 7. 最适合插入 COMQUTOR structure layer 的位置

第一阶段插入点：`cli/main.py -> run_analysis()`

具体位置：`final_state` 合并完成后。

代码位置特征：

- 先执行 `trace = []`
- 在 `for chunk in graph.graph.stream(...):` 中不断 `trace.append(chunk)`
- 然后执行 `final_state = {}`
- 再用 `for chunk in trace: final_state.update(chunk)` 合并最终状态

建议在 `final_state` 合并完成后调用：

`save_comqutor_run_outputs(final_state, ticker, config, selected_analysts)`

原因：

1. 所有 Agent 输出已经在 `final_state` 里。
2. 不需要改每个 Agent。
3. 不影响原来的 TradingAgents 流程。
4. 适合先做 P1 前的原始数据留存和可观测性。

第二阶段插入点：`tradingagents/graph/trading_graph.py -> TradingAgentsGraph._run_graph()`

这个位置更适合未来做 headless runner 或平台化自动运行。

## 8. COMQUTOR 输出设计

建议新增文件：`tradingagents/comqutor_outputs.py`

建议新增函数：`save_comqutor_run_outputs(final_state, ticker, config, selected_analysts)`

每次运行后生成：

- `outputs/runs/{run_id}/raw_agent_outputs.json`
- `outputs/runs/{run_id}/final_report.md`
- `outputs/runs/{run_id}/metadata.json`

`raw_agent_outputs.json` 字段来源：

| COMQUTOR agent | final_state 来源 |
|---|---|
| `market_analyst` | `final_state["market_report"]` |
| `sentiment_agent` | `final_state["sentiment_report"]` |
| `news_agent` | `final_state["news_report"]` |
| `fundamental_agent` | `final_state["fundamentals_report"]` |
| `bull_researcher` | `final_state["investment_debate_state"]["bull_history"]` |
| `bear_researcher` | `final_state["investment_debate_state"]["bear_history"]` |
| `research_manager` | `final_state["investment_plan"]` |
| `trader` | `final_state["trader_investment_plan"]` |
| `aggressive_risk_analyst` | `final_state["risk_debate_state"]["aggressive_history"]` |
| `conservative_risk_analyst` | `final_state["risk_debate_state"]["conservative_history"]` |
| `neutral_risk_analyst` | `final_state["risk_debate_state"]["neutral_history"]` |
| `portfolio_manager` | `final_state["final_trade_decision"]` |

`metadata.json` 建议补充：

- `analysis_date`
- `llm_provider`
- `quick_think_llm`
- `deep_think_llm`
- `selected_analysts`
- `commit`
- `run_command`
- `markdown_report_path`

## 9. 结论

TradingAgents 已经能产出完整的 Agent 分析链条，但当前主要输出是 markdown report。

COMQUTOR 下一步应该先建立稳定的结构化输出入口：在 `final_state` 生成后，把每个 Agent 的原始输出保存到 `outputs/runs/{run_id}/raw_agent_outputs.json`。

这样后续 Structure Graph、Conflict Intelligence 和 Alpha Memory 都可以从统一输入开始，不需要反复解析 markdown，也不需要猜报告目录。
