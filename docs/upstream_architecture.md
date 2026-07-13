# TradingAgents upstream architecture and COMQUTOR seam

## Verified flow

```text
ticker + trade_date + asset_type
  -> TradingAgentsGraph.propagate(...)
  -> Propagator.create_initial_state(...)
  -> Market Analyst       -> market_report
  -> Sentiment Analyst    -> sentiment_report
  -> News Analyst         -> news_report
  -> Fundamentals Analyst -> fundamentals_report
  -> Bull/Bear Researchers -> Research Manager
  -> Trader
  -> Aggressive/Conservative/Neutral Risk Analysts
  -> Portfolio Manager -> final_trade_decision
  -> (final_state, processed_decision)
```

Source evidence:

- `tradingagents/graph/trading_graph.py`: `propagate()` delegates to
  `_run_graph()`, which returns the two-value result.
- `tradingagents/graph/setup.py`: builds the analyst sequence and downstream
  debate, trader, risk, and portfolio-manager nodes.
- `tradingagents/graph/analyst_execution.py`: maps the legacy wire key
  `social` to `Sentiment Analyst` and `sentiment_report`.
- `tradingagents/agents/utils/agent_states.py`: defines all four report fields.
- `tradingagents/graph/propagation.py`: initializes the four fields to empty
  strings before graph execution.

Run the evidence check with:

```bash
.venv/bin/python scripts/verify_upstream_baseline.py
```

## COMQUTOR integration boundary

COMQUTOR will call `propagate()` once through
`comqutor_alpha.integration.tradingagents_runner`, then capture only:

- `market_report`
- `sentiment_report`
- `news_report`
- `fundamentals_report`

The following upstream fields are excluded from COMQUTOR structure judgments:

- `investment_debate_state`
- `investment_plan`
- `trader_investment_plan`
- `risk_debate_state`
- `final_trade_decision`
- upstream trading memory

The processed decision and `final_trade_decision` may be saved only as an
explicitly labelled comparison artifact. They are not inputs to claim
extraction, Alpha mapping, activation, conflict arbitration, or product
summary generation.

## Analyst implementations

- Market: tool-calling prose report with a deterministic market snapshot.
- Sentiment: pre-fetches news, StockTwits, and Reddit and uses upstream
  structured output with a free-text fallback.
- News: tool-calling report using ticker, macro, and prediction-market data.
- Fundamentals: tool-calling report using fundamental statements and metrics.

COMQUTOR does not rewrite these prompts in the MVP. Its adapter accepts their
current report text and produces separate evidence-bearing Claim objects.
