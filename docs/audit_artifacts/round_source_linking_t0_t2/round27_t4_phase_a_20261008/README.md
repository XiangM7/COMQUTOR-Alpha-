# T4 Phase A：零外部调用准备（2026-10-08）

本目录是 T4 Phase A 的全部新增成果。本轮保持零真实请求：
- 没有点击 Start Research，也没有用 API、脚本、录制器或后台任务发起研究；
- 没有修改或清空 8000 服务的数据库，没有停止或重启现有服务；
- 没有修改模型、prompt、taxonomy、Gold 答案或评分阈值；
- 没有 commit 或 push。

**NVDA Fresh Run 由负责人 Xiang Mao 亲自在 `http://127.0.0.1:5177/research` 点击 Start Research 发起。**

## 入口

| 交付物（任务书） | 文件 |
|---|---|
| 1. PG 验证报告和原始测试日志 | `01_postgres/PG_VERIFICATION_REPORT.md`、`test_evidence/pg*` |
| 2. Replay／ESLint 说明 | `02_replay_eslint/REPLAY_AND_ESLINT.md` |
| 3. 两层计量字段、统一汇总、复现命令 | `03_metering/METERING_FIELDS_AND_SUMMARY.md`、`03_metering/usage_report_*.json` |
| 4. 配置对照、代码身份、差异 | `04_fresh_prep/CONFIG_COMPARISON.md`、`04_fresh_prep/frozen_config.json`、`04_fresh_prep/code_snapshot/`、`06_code/` |
| 5. NVDA 预算、成本估算、停止条件 | `04_fresh_prep/BUDGET_COST_STOP_RULES.md`、`04_fresh_prep/budget.json` |
| 6. 录制流程和冻结走查证据 | `05_demo/DEMO_FLOW.md`、`05_demo/recording_frozen/` |
| 7. 就绪状态表（完成／阻塞／已知限制）和待决定事项 | `READINESS_STATUS.md` |
| 测试命令、结果、退出码和失败归因 | `TEST_REPORT.md`、`test_evidence/` |
| 只读产物哈希证明 | `hash_proof/` |

## 目录

- `01_postgres/`：建库、迁移、生产路径落库、重启、历史重开、Export、一致性。`final_code/` 是在最终代码上的复核。
- `02_replay_eslint/`
- `03_metering/`
- `04_fresh_prep/`：演练（1800 上限和 60 上限）、预算、冻结配置、网页检查（`web_check/`）、8000 服务配置（只读）。`superseded/` 存放计量修复前的旧演练结果。
- `05_demo/`：录制器 `t4_demo_recorder.mjs` 和冻结走查。
- `06_code/`：本轮代码差异，以及改动前后的 sha256。
- `code_before/`：改动前的副本。
- `tools/`：本轮所有脚本（建库、启动实例、落库、验证、计量、演练、预算、冻结、测试）。

## 实例

| 实例 | 端口 | 数据库 | 说明 |
|---|---|---|---|
| T4 API | 8002 | PostgreSQL `comqutor_alpha_t4_test` | `tools/start_t4_instance.sh fresh`：profile `t3_verified_20261008`，上限见预算文档 |
| T4 前端 | 5177 | — | `VITE_COMQUTOR_API_BASE_URL=http://127.0.0.1:8002` |
| 现有服务（未触碰） | 8000 / 5175 | `comqutor_alpha_test` | 运行旧代码，也开着真实执行。**不要在 5175 点击** |
