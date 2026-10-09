# T4 Phase A：测试命令、结果、退出码与失败归因

- 测试结果和真实运行结果分开报告；真实运行本轮为 0 次。
- 所有 pytest 组都挂了 `net_trap_plugin`：任何非回环连接都会报错并计数。
- 原始日志、junit（含每个 nodeid）、命令和退出码都在 `test_evidence/`。

## 1. 汇总

| 组 | 代码 | 命令 | 结果 | 退出码 | 外网尝试 |
|---|---|---|---|---|---|
| PostgreSQL（必需） | 最终 | `bash tools/run_t4_tests.sh pg` | **64 passed，0 skipped** | **0** | 0 |
| PostgreSQL（第 1 次） | 中间 | 同上 | 62 passed，2 failed（新测试的断言写错，见 §3） | 1 | 0 |
| PostgreSQL（第 2 次） | 中间 | 同上 | 64 passed，0 skipped | 0 | 0 |
| 受影响单元测试（第 1 次） | 中间 | `bash tools/run_t4_tests.sh unit`（64 个文件） | 1059 passed，12 failed，1 skipped | 1 | 0 |
| **受影响单元测试（最终）** | 最终 | 同上 | **1067 passed，6 failed，1 skipped** | 1 | 0 |
| 环境类失败单独复跑 | 最终 | `bash tools/rerun_attributed_failures.sh` | 启动器 6 passed；作业时序 3 passed | 0 / 0 | — |
| v4 逐字节重建归因 | 最终 | `tools/check_v4_rebuild_excluding_later_rounds.py`（网络陷阱下） | 6 个文件逐字节一致 | 0 | 0 |
| T4 新增单元测试 | 最终 | `tests/test_t4_phase_a_environment_and_metering.py` | 24 passed（包含在受影响组内） | — | 0 |
| 前端 vitest（受影响） | 最终 | `npx vitest run src/utils/serverStatus.test.ts src/App.test.tsx src/pages/ResearchPage.test.tsx src/api/adapters.test.ts` | 4 个文件，63 passed | 0 | — |
| 前端类型检查 | 最终 | `npm run typecheck`（`tsc --noEmit -p tsconfig.app.json && tsc --noEmit -p tsconfig.node.json`） | 通过 | 0 | — |
| 前端 ESLint | 最终 | `npx eslint src e2e` | 0 个问题 | 0 | — |
| 零网络演练（1800 上限 / 60 上限） | 最终 | `tools/rehearse_fresh_pipeline.py`（网络陷阱下） | 见 `04_fresh_prep/rehearsal_*.json` | 0 / 0 | 0 / 0 |

- 跳过的 1 个是 `tests/test_week2_llm.py:1214`：需要 `COMQUTOR_RUN_WEEK2_PROVIDER_SMOKE=1` 才会做真实提供方调用，本轮按要求不开启。
- PG 组内没有任何跳过。
- 第 1 次单元组的日志是 `unit_run1.*`。它的 `command` 行写的 junit 路径是改名前的 `unit_junit.xml`，实际文件已改名为 `unit_run1_junit.xml`。

## 2. 最终单元组 6 个失败的归因（都不是本轮代码引起的）

| 测试 | 原因 | 证明 |
|---|---|---|
| `test_live_launcher_database_isolation.py` 中的 4 个 | 测试运行真实启动脚本，端口检查发现 **8000 已被现有服务占用**；按要求不能停止现有服务 | 把启动器端口移到空闲的 8099（`COMQUTOR_LIVE_API_PORT=8099`，本轮新增的覆盖变量）后，同一文件 6 个全部通过（`rerun_launcher_free_port.log`，退出码 0）。本轮新增的两个启动器测试在端口检查之前截取环境，不受影响 |
| `test_w5_1b_final_patch::test_status_and_history_and_graph_and_conflicts_all_use_same_output_root` | 在 20 分钟的大组中，后台作业在测试的轮询期限内仍是 `running`（机器负载）。第 1 次大组中另有 2 个同类测试失败，这次通过了 | 单独运行时 3 个同类测试全部通过（`rerun_job_timing_isolated.log`，退出码 0） |
| `test_t3_joint_sample_driver::test_the_v4_sample_and_its_materials_rebuild_byte_for_byte` | 构建器统计每个样本 claim 在 `docs/audit_artifacts` 下所有 json/jsonl 中的"历史提及次数"，只排除第 25 轮目录。第 26、27 轮后来写入的审计文件提高了这个计数（第 26 轮收尾报告已记录同一现象） | 扫描时同时排除第 26、27 轮目录后，6 个文件逐字节一致（`v4_rebuild_excluding_later_rounds.json`） |

## 3. 本轮修过的失败

| 失败 | 归因 | 处理 |
|---|---|---|
| PG 第 1 次：`test_required_postgresql_refuses_a_different_database_name_before_connecting`、`..._refuses_a_missing_url_instead_of_a_sqlite_file` | 我新写的测试断言写错。写路径把引擎的 `DatabaseConfigurationError` 包装成只带原因码的 `GraphPersistenceError`，拒绝本身是正常的（原因码 `DATABASE_TARGET_MISMATCH`、`REQUIRED_DATABASE_URL_MISSING`） | 改为按 `GraphPersistenceError` 和原因码断言。日志保留在 `pg_attempt1_test_expectation_bug.log`。该日志的 traceback 打印了测试库 DSN，**事后把其中 3 处数据库密码替换成了 `***REDACTED***`**，其余内容未改 |
| 单元第 1 次：`test_week3_security_hardening::TestRetryLifecycle::test_repeated_successful_retry_remains_idempotent` | 新的 completed 规则把没有 `alpha_match_method` 的旧版记录（确定性时代的 schema）当成故障，因为完成度汇总把这类记录放在调用失败桶里 | **产品代码窄修**：这类记录不算状态故障（`routes_research._legacy_records_without_classification_method`）。完成度的 4 态披露不变。新增 2 个测试 |
| 单元第 1 次：`test_direction_evaluation` 中 2 个、`test_recovery_real_path_gating` 中 1 个 | 这些测试断言"有真实分类调用失败的 run 是 completed"（分别有 1 次和 `973 - total` 次真实失败），这正是 T4 规则要纠正的情况 | 期望值改为 `partial`（共 4 行，其中历史列表 1 行），其余断言不动，没有删断言、没有加 skip。依据：T4 规则；与 T4 库中 AMD 重评一致 |

## 4. 没有做的

- 没有跑全量回归（约 45 分钟以上）。按任务书只跑受影响的测试：被改模块的直接测试，加上所有经过研究流水线的测试。
- 没有跑 e2e（Playwright e2e 在这台机器上不能运行，见此前记录）。
- 冻结走查录屏是用系统 Chrome 走查真实页面，不属于 e2e 测试。
