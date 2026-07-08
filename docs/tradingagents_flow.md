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
