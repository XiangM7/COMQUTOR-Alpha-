# Week 1A Hook Points

本文记录 TradingAgents 输出进入 COMQUTOR Week 1A writer 的准确位置。

## final_state 来源

`tradingagents/graph/trading_graph.py` 中，`TradingAgentsGraph.propagate()` 会产生完整 `final_state`：

- debug/stream 模式：逐个 chunk 收集到 `trace`，再用 `final_state.update(chunk)` 合并。
- 非 debug 模式：直接使用 `self.graph.invoke(...)` 的返回值。
- 函数最后返回 `final_state, self.process_signal(final_state["final_trade_decision"])`。

`cli/main.py` 也使用同样模式：streaming chunks 是 per-node deltas，CLI 在运行结束后合并成 `final_state`，再调用 `save_comqutor_run_outputs(...)`。

## 字段映射

| COMQUTOR agent | TradingAgents agent | primary path | fallback path | 说明 |
|---|---|---|---|---|
| `market_agent` | Market Analyst | `market_report` |  | Market Analyst 的最终报告字段。 |
| `sentiment_agent` | Sentiment Analyst | `sentiment_report` |  | Sentiment Analyst 的最终报告字段。 |
| `news_agent` | News Analyst | `news_report` |  | News Analyst 的最终报告字段。 |
| `fundamental_agent` | Fundamentals Analyst | `fundamentals_report` |  | Fundamentals Analyst 的最终报告字段。 |
| `bull_researcher` | Bull Researcher | `investment_debate_state.bull_history` |  | Research debate 中 bull side 历史。 |
| `bear_researcher` | Bear Researcher | `investment_debate_state.bear_history` |  | Research debate 中 bear side 历史。 |
| `research_manager` | Research Manager | `investment_plan` | `investment_debate_state.judge_decision` | `investment_plan` 是 TradingAgents 最终投资计划；`judge_decision` 是 debate state 内的 manager 决策备份。 |
| `trader` | Trader | `trader_investment_plan` |  | Trader 的交易计划字段。 |
| `aggressive_risk_analyst` | Aggressive Analyst | `risk_debate_state.aggressive_history` |  | Risk debate aggressive side 历史。 |
| `conservative_risk_analyst` | Conservative Analyst | `risk_debate_state.conservative_history` |  | Risk debate conservative side 历史。 |
| `neutral_risk_analyst` | Neutral Analyst | `risk_debate_state.neutral_history` |  | Risk debate neutral side 历史。 |
| `portfolio_manager` | Portfolio Manager | `final_trade_decision` | `risk_debate_state.judge_decision` | `final_trade_decision` 是最终交易决策；`judge_decision` 是 risk debate 内的 portfolio manager 决策备份。 |

如果 primary 和 fallback 都存在，Week 1A writer 使用 primary 作为 `raw_output`，同时把 fallback 写入 `source_candidates`，不重复生成第二条 raw output。

## market_agent 命名

旧实现使用 `technical_agent` 指向 `market_report`。TradingAgents 原始 UI 和日志中对应角色是 Market Analyst，最终字段也是 `market_report`，所以 Week 1A writer 使用 `market_agent`。这避免把 market analysis 误标成 technical-only 输出。
