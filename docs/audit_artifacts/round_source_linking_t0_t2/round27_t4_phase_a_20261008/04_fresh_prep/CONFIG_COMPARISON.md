# D. 配置对照、代码身份与差异（T4 Phase A）

## 1. 四列对照

四列的来源：
- **8000 现有服务**：进程环境（只读，按白名单过滤，见 `service_8000_effective_env_readonly.json`）。它运行的是第 19 轮启动时加载的代码；
- **T3 签署执行**：`round25_t3_minimal_prep_20261008/B4_execution/authorized_plan_SIGNED_t3joint-20261008T170322Z-bd99811e.json` 的 `config`；
- **profile**：`comqutor_alpha/structure_engine/week2_execution_profile.py::T3_VERIFIED_20261008`；
- **T4 Fresh 实例（8002）**：进程环境加生产解析器的结果，由 `frozen_config.json` 从运行中的进程读出，并逐项检查。

| 项 | 8000 现有服务 | T3 签署执行 | profile `t3_verified_20261008` | **T4 Fresh 实例** |
|---|---|---|---|---|
| 代码 | 第 19 轮启动时加载的代码（`/ready` 没有身份字段） | 冻结的计划代码身份 | — | `7a9aefa` + 未提交改动，tracked diff `b5e91198…`，untracked `a61cb62c…`（代码快照见 `code_snapshot/`） |
| 数据库 | PostgreSQL `comqutor_alpha_test` | 无（执行驱动不落库） | — | PostgreSQL `comqutor_alpha_t4_test`（强制方言和库名） |
| 真实执行 / Week 2 | 开 / 开 | — / 只调用三个任务 | — | 开 / 开（经常驻启动器的 live 预检） |
| Week 2 profile | 无 | — | — | `t3_verified_20261008` |
| 提供方 / 模型 | deepseek / deepseek-v4-flash | deepseek / deepseek-v4-flash | — | deepseek / deepseek-v4-flash |
| 内容核验 | 45 s，批大小 1，max_tokens 16384 | 120 s，批大小 1，不设 max_tokens | 120 s，批大小 1 | 120 s，批大小 1，不设 max_tokens（启动脚本清掉了旧变量） |
| Alpha 分类 | 45 s，单条 | 45 s，单条，并发 4 | 45 s，并发 4 | 45 s，单条，并发 4 |
| 方向（stance） | 45 s | 120 s，10 条一批，并发 4 | 120 s，并发 4 | 120 s，10 条一批，并发 4 |
| 适配器 / 结构抽取 | 45 s（共享） | 不调用 | 不覆盖 | **45 s（共享）**，见 P-3 |
| 应用重试 / SDK 重试 | 0 / 0 | 0 / 0 | 0 / 0 | 0 / 0 |
| 请求和回复审计 | 开 | 开 | 开 | 开（由 profile 打开） |
| Week 2 调用上限 | 1500 | 每个任务单独设上限（17/40/13） | — | **1800**（提案） |
| 研究 agent profile | `comqutor_deepseek_default_v1`（deepseek-v4-flash，thinking 关，辩论 1 轮，风险讨论 1 轮） | 不调用 | — | 同左 |
| 研究 agent 请求上限 / 重试 | 150 / 0 | — | — | **100** / 0（提案） |
| 作业墙钟 / 并发作业 | 7200 s / 默认 | — | — | **14400 s** / 1（提案） |
| 遇 4xx/429 整体停止 | 无 | 有（400/401/403/404/422/429） | — | **无**，见 P-5 |
| Data Sanity（真实取数） | 开 | — | — | 开（`.env`） |
| 强制刷新 | 关 | — | — | 关 |
| 端口 / 前端来源 | 8000 / 5175 | — | — | 8002 / 5177 |

## 2. 代码身份与差异

| 时间点 | git HEAD | tracked diff sha256 | untracked 运行源码 sha256 | 来源 |
|---|---|---|---|---|
| 本轮开始前 | `7a9aefa` | `cb81f23f…` | 见文件 | `hash_proof/state_before.json` |
| 最终（Fresh 实例和最终冻结走查） | `7a9aefa` | `b5e91198…` | `a61cb62c…` | `frozen_config.json` → `code_snapshot/` |

- 本轮改动的文件，以及改动前后的 sha256：`06_code/code_changes.json`。共 16 个文件修改、4 个新增；另有 4 个文件在改动前做了备份，但最终没有修改。
- 统一差异：`06_code/t4_phase_a_code.diff`。
- 改动前的副本：`code_before/`。
- 代码快照（`code_snapshot/`）：
  - `tracked_diff_vs_HEAD.diff`：完整的 tracked 差异；
  - `untracked_runtime_source.tar.gz`：untracked 运行源码。
  - 它们的 sha256 必须等于运行中进程报告的身份，否则冻结工具拒绝写出。

模型与 prompt 身份（`frozen_config.json` → `prompt_identities`）：
- 内容核验 `content_support.llm.v2.1`，sha256 `6abae47b…`；
- Alpha `ac48723f…`；
- 方向 `d9455fd5ff33…`；
- 三项都与 T3 签署时钉住的值相同（检查项 `week2_prompts_equal_t3_pins`）；
- 适配器和结构抽取的 prompt 身份也一并记录；
- 研究 agent 的 prompt 在 `tradingagents/` 源码中，记录的是该目录的源码清单 sha256。
