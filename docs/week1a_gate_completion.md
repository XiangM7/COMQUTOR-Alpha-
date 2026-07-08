# Week 1A Gate Completion

Week 1A 是 Engineer A 的 backend / agent-output / research-entrypoint 工作。

本次实现只补 Week 1A Gate，不做 alpha mapping、graph、activation、conflict detector、dashboard、Alpha Memory 或 outcome tracking。

## Week 1A 任务映射

| 任务 | 实现位置 |
|---|---|
| A1-1 locate hook points | `docs/week1a_hook_points.md`, `comqutor_alpha/adapters/tradingagents_output_writer.py` |
| A1-2 structured output adapter | `comqutor_alpha/structure_engine/structured_output_adapter.py` |
| A1-3 run_id | `comqutor_alpha/adapters/tradingagents_output_writer.py`, `structured_output_adapter.py`, `comqutor_alpha/api/routes_research.py` |
| A1-4 agent_outputs table / file-backed equivalent | `outputs/runs/{run_id}/raw_agent_outputs.json`, `outputs/runs/{run_id}/structured_agent_outputs.json` |
| A1-5 persist outputs | `comqutor_alpha/adapters/tradingagents_output_writer.py`, `structured_output_adapter.py`, `comqutor_alpha/api/routes_research.py` |
| A1-6 first POST /api/research | `comqutor_alpha/api/routes_research.py`, `comqutor_alpha/api/main.py` |

## 已完成内容

`run_research_request(payload, runner=None, output_root="outputs/runs")` 是 Week 1A 的本地 research entrypoint。

它支持三种路径：

- 注入 fake runner，用于测试。
- 使用 `offline_raw_agent_outputs` 创建本地 fake run，不需要付费 API。
- 调用 guarded real TradingAgents runner wrapper，用户必须显式 opt in 并提供环境/config。

每次 run 都会有 `run_id`，并写入：

- `metadata.json`
- `raw_agent_outputs.json`
- `structured_agent_outputs.json`

`structured_agent_outputs.json` 使用 `records` 字段保存结构化 rows。

## Week 1A hardening changes

- COMQUTOR writer 逻辑已移动到 `comqutor_alpha/adapters/tradingagents_output_writer.py`。
- `tradingagents/comqutor_outputs.py` 只保留 compatibility shim。
- `raw_agent_outputs.json` 增加 `schema_version`。
- raw output 单条最大保存 50000 字符，超出时显式标记 `truncated`。
- `final_report.md` 改为 opt-in，默认不写，减少 raw output 重复扩散。
- 文件写入集中到 `comqutor_alpha/storage/file_store.py`。
- JSON artifact 使用 atomic write。
- `run_id` 和 artifact filename 做路径校验。
- metadata 只保存 provider/model 白名单字段，不保存 API key、secret、token、password、backend_url 或完整 config。
- `POST /api/research` response 不再暴露 raw output、本地路径或 config，只返回 artifact booleans。

## File-backed 说明

Week 1A 目前不使用数据库。

`agent_outputs table` 的本地等价物是：

- raw rows: `outputs/runs/{run_id}/raw_agent_outputs.json`
- structured rows: `outputs/runs/{run_id}/structured_agent_outputs.json`

这样可以在没有 PostgreSQL 的情况下完成 gate 验证。

## API 行为

如果 FastAPI 可用：

- `POST /api/research` 调用 `run_research_request(payload)`
- `GET /api/research/{run_id}` 调用 `get_research_run(run_id)`

如果 FastAPI 不可用：

- `comqutor_alpha.api.main` 仍然可以 import。
- helper functions 仍然可以直接测试。

## 测试方式

运行：

python -m compileall tradingagents/comqutor_outputs.py comqutor_alpha/structure_engine/structured_output_adapter.py comqutor_alpha/api/routes_research.py comqutor_alpha/api/main.py comqutor_alpha/runners/tradingagents_runner.py

运行：

python -m pytest tests/test_structured_output_adapter.py tests/test_week1a_gate.py

## 重要说明

`POST /api/research` 支持 test/offline mode，不需要付费 API。

真实 TradingAgents mode 需要用户显式设置 `allow_real_tradingagents_run=True`，并提供可用的 provider/model/API 配置。测试不会触发真实 TradingAgents。

`.env` 不会被修改。

`outputs/runs/` 不应提交。

## 仍未 production-ready

- 没有 authentication。
- 没有 rate limit。
- 当前仍是 file-backed storage，不是真实数据库。
- 没有 background job queue。
- 没有 admin authorization for raw artifacts。
- API 当前适合本地 Gate 验证，不应直接作为公开生产服务。
