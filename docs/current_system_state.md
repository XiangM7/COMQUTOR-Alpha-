# 当前系统状态

审查日期：2026-07-13

## 仓库与环境

- 分支：`comqutor-structure-layer`
- 审查基线 HEAD：`652a6281495f852b8a25487db7b509eade4f812e`
- 验收开始时工作树干净；本文件仅更新验收结果，尚未 commit
- Python：`3.13.5`
- Python 路径：`.venv/bin/python`
- 项目要求：Python `>=3.10`

当前 `.venv` 已安装项目依赖、dev 依赖、FastAPI、httpx 和声明的 provider SDK；`pip check` 无依赖破损。

## 当前主链路

`run_research_request()` 当前执行：

1. 捕获或接收 TradingAgents raw agent outputs。
2. 生成 validated structured claims。
3. 生成 Alpha matches。
4. 生成 claim-level extracted structures。
5. 根据实际 artifact 状态返回安全响应。

一次完整 Week 1-2 run 必须包含：

- `raw_agent_outputs.json`
- `structured_agent_outputs.json`
- `alpha_matches.json`
- `extracted_structures.json`

四项全部存在时状态才是 `completed`。部分生成时状态为 `partial`。

## Artifact 版本

- Raw outputs：`week1a.raw_agent_outputs.v1`
- Structured claims：`week1a.structured_agent_outputs.v2`
- Alpha matches：`week2.alpha_matches.v2`
- Extracted structures：`week2.extracted_structures.v2`

Structured v2 为每条 claim 提供独立 `claim_id`，并用 `source_agent_output_id` 保留原始输出身份。Week 2 reader 仍可处理已有 v1 structured artifacts。

## Week 2 LLM 路径

Week 2 LLM gateway 默认关闭。启用需要服务端设置 `COMQUTOR_WEEK2_LLM_ENABLED=1`，并配置：

- `COMQUTOR_WEEK2_LLM_PROVIDER`
- `COMQUTOR_WEEK2_LLM_MODEL`

也可复用 `TRADINGAGENTS_LLM_PROVIDER` 和 `TRADINGAGENTS_QUICK_THINK_LLM`。HTTP request 不能提交 provider、model、API key 或真实运行开关。

调用边界：

- 严格 JSON object
- 默认一次 retry
- provider timeout 和 caller-side timeout
- 每个 run 默认最多 32 次调用，硬上限 100
- 失败后 deterministic fallback
- 错误日志不保存 prompt、provider response、exception detail 或 credential

`.env` 保持忽略，未修改、未提交。验收仅检查 provider/model/credential 是否存在，未输出配置值。

## 当前验证结果

- Compileall：通过
- Ruff check：失败，`33` 项
- Ruff format check：失败，`109` 个文件需要格式化
- 完整离线 suite：`658 passed, 1 skipped, 2 deselected`，另有 `69` 个 subtests passed
- FastAPI/API：`19 passed`
- Week 1→2 end-to-end：`16 passed`
- Week 2 LLM offline：`12 passed, 1 deselected`
- Clean labeled claims：`20/20`，strict accuracy `100%`
- Development Plan 八句验收：`8/8`
- NVDA robustness：strict `23/30`，allowed `29/30`
- NVDA 修改前基线：strict `18/30`，allowed `20/30`

NVDA 数据仅为 robustness diagnostic，不代表真实市场准确率，也不是 80% gate。

## 已知限制

1. 当前持久化是 file-backed MVP，不是 Development Plan 中的正式数据库实现。
2. 当前没有 provider/model/credential 配置，真实 provider smoke test 未执行。
3. Structured deterministic splitter 和规则型 semantic parser 仍可能遗漏复杂长句。
4. Week 2 只输出 claim-level nodes/edges，不是 Week 3 run-level Structure Graph。
5. 可选 Bedrock SDK `langchain_aws` 未安装，对应测试跳过。
6. 当前 Ruff check 与 format check 未通过。
7. Graph coherence、activation、dominance、正式 conflict detection、Alpha Memory 和 outcome feedback 均未实现。
