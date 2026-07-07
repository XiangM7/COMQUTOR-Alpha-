# Week 1 Gate Completion

本文记录官方 Week 1 Gate 的当前完成状态。

## 1. GET /api/alpha-library 返回 10 个 alphas

已完成。Alpha Library 由本地 taxonomy 文件驱动，接口返回 MVP-10 alpha 列表、基础字段和 conflict_alphas。

相关文件：

- comqutor_alpha/alpha_library/alpha_taxonomy_v1.yaml
- comqutor_alpha/alpha_library/alpha_loader.py
- comqutor_alpha/alpha_library/alpha_schema.py
- comqutor_alpha/api/routes_alpha_library.py

## 2. POST /api/research 触发原始 agents 或 guarded/offline runner

已完成。`POST /api/research` 入口支持 offline raw agent outputs，用于本地验证；真实 TradingAgents 路径由 guarded runner 包住，避免测试时误触发付费 API。

相关文件：

- comqutor_alpha/api/routes_research.py
- comqutor_alpha/runners/tradingagents_runner.py
- tradingagents/comqutor_outputs.py

## 3. agent_outputs 保存结构化 rows

已完成。当前 MVP 使用 file-backed 方式保存 raw rows 和 structured rows。

相关文件：

- tradingagents/comqutor_outputs.py
- comqutor_alpha/structure_engine/structured_output_adapter.py
- outputs/runs/{run_id}/raw_agent_outputs.json
- outputs/runs/{run_id}/structured_agent_outputs.json

## 当前边界

- 当前 MVP 是 file-backed，不是 database-backed。
- 测试不会调用付费 API。
- 真实 TradingAgents run 需要显式 opt-in，并配置可用的 provider、model 和 API key。
- outputs/runs/ 是运行产物，不应提交到 Git。
