# Week 1J 验收清单：Raw Agent Output Capture

## 目的

Week 1J 用来验证 Week 1B 的 COMQUTOR raw-output capture pipeline 是否端到端可用。

它不跑真实 TradingAgents，不调用付费 LLM/API，只用 fake `final_state` 验证保存链路。

## 涉及文件

- `tradingagents/comqutor_outputs.py`
- `cli/main.py`
- `outputs/runs/{run_id}/raw_agent_outputs.json`
- `outputs/runs/{run_id}/metadata.json`
- `outputs/runs/{run_id}/final_report.md`

## 语法检查

运行：

    python -m compileall tradingagents/comqutor_outputs.py cli/main.py

通过标准：无 syntax error。

## Fake final_state 验证

运行下面命令，不需要真实 API：

    python -c 'from tradingagents.comqutor_outputs import save_comqutor_run_outputs; s={"market_report":"Strong bullish momentum.","news_report":"Neutral news flow.","fundamentals_report":"Revenue growth is positive.","investment_debate_state":{"bull_history":"Bull sees upside.","bear_history":"Bear sees risk."},"investment_plan":"Hold with caution.","trader_investment_plan":"Trader proposes hold.","risk_debate_state":{"aggressive_history":"Upside opportunity.","conservative_history":"Downside risk.","neutral_history":"Balanced view."},"final_trade_decision":"Hold."}; c={"llm_provider":"fake","quick_think_llm":"fake_quick","deep_think_llm":"fake_deep"}; p=save_comqutor_run_outputs(s,"NVDA",c,["market","news"],analysis_date="2026-07-01"); print(p); print((p/"raw_agent_outputs.json").exists(), (p/"metadata.json").exists(), (p/"final_report.md").exists())'

需要确认生成：

- `raw_agent_outputs.json`
- `metadata.json`
- `final_report.md`

## 验收标准

- 无语法错误。
- `outputs/runs/{run_id}/` 被创建。
- `metadata.json` 包含 `run_id` 和 `ticker`。
- `raw_agent_outputs.json` 包含 `agent_outputs`。
- `final_report.md` 存在。
- 原始 TradingAgents 的 `reports/` 行为不变。
- `outputs/runs/` 被 Git ignore，不会误提交 fake run。
