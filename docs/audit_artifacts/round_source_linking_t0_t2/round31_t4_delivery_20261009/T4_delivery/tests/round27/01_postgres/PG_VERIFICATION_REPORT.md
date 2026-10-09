# A. PostgreSQL 验证报告（T4 Phase A）

范围：任务书 A1–A6。全部在本机回环完成：PostgreSQL 16.15（127.0.0.1:5433）和 T4 实例（127.0.0.1:8002）。
- 8000 服务和它的数据库 `comqutor_alpha_test` 没有被修改、清空、停止或重启。
- `databases.json` 记录了建库前后 8000 库 `research_runs` 的行数：9 → 9，未变。

## 1. 数据库与实例隔离（A4）

| 用途 | 数据库 | 说明 |
|---|---|---|
| 8000 服务（未触碰） | `comqutor_alpha_test` | 只在只读事务里读过行数 |
| T4 实例（8002）：验证 run，之后用于 NVDA Fresh Run | `comqutor_alpha_t4_test` | 本轮新建，空库启动 |
| PostgreSQL 集成测试 | `comqutor_alpha_t4_pytest_test` | 本轮新建 |
| 零网络演练 | `comqutor_alpha_t4_rehearsal_test` | 本轮新建 |

- T4 实例的输出目录是 `outputs/t4_runs`，端口 8002，前端来源 `http://127.0.0.1:5177`。
- 启动脚本 `tools/start_t4_instance.sh` 在启动前和服务进程内部各检查一次数据库：
  - 启动前：数据库 URL 必须是 PostgreSQL，且库名必须是 `comqutor_alpha_t4_test`。
  - 服务进程内部：由 `COMQUTOR_REQUIRE_DATABASE_DIALECT=postgresql` 和 `COMQUTOR_REQUIRE_DATABASE_NAME` 再检查一次。
- 两种模式：
  - verify：真实执行关闭，Week 2 LLM 关闭，外发 HTTP 指向一个不存在的回环代理。
  - fresh：经常驻启动器 `scripts/start_live_comqutor.sh` 启动，带它的 live 预检。

## 2. 强制 PostgreSQL（A1）

`comqutor_alpha/storage/db/engine.py::resolve_database_url`：设置了 `COMQUTOR_REQUIRE_DATABASE_DIALECT` 时，有两种情况会直接报错，不会退回本地 SQLite 文件：
- 缺 URL → `REQUIRED_DATABASE_URL_MISSING`
- URL 是别的后端 → `DATABASE_DIALECT_MISMATCH`

不设置时行为与原来相同。按题意，开发模式的 SQLite 行为不在本轮改造范围内。

| 证据 | 结果 |
|---|---|
| 单元测试 `test_required_dialect_refuses_a_missing_url_instead_of_falling_back_to_sqlite`、`..._refuses_a_url_of_another_backend`、`..._accepts_a_matching_url_and_unset_keeps_the_sqlite_fallback` | 通过 |
| PG 集成测试 `tests/test_t4_required_postgres_integration.py`（真实 PG）：通过、库名不符被拒（`DATABASE_TARGET_MISMATCH`）、缺 URL 被拒（`REQUIRED_DATABASE_URL_MISSING`）、拒绝时不生成 SQLite 文件 | 3 个全部通过 |
| 写路径的错误外形 | `build_write_repository_from_env` 把配置错误包装成只带原因码的 `GraphPersistenceError`。第一次测试按未包装的异常写断言，失败了；保留在 `test_evidence/pg_attempt1_test_expectation_bug.log`，属于测试断言写错，不是产品问题 |

## 3. `/ready` 显示数据库与身份（A2）

`/ready` 新增三项，每一项取不到时都降级为 `null`/unknown，不会让 readiness 失败：
- `database_backend`：只有 dialect 和库名，不含 DSN、用户、主机或密码；
- `week2_semantic`：是否启用、execution profile、模型、调用上限、是否开审计；
- `code_identity`：git HEAD、是否有未提交改动、tracked diff 的 sha256、untracked 运行源码的 sha256。

前端状态行显示这三项：
- verify 实例上的实际文字（录屏 `05_demo/recording_frozen/screens/01_instance.png`）："Server ready, live research disabled · PostgreSQL comqutor_alpha_t4_test · code 7a9aefa+uncommitted(b5e91198)"；
- fresh 实例的显示见 `04_fresh_prep/`。

对照：8000 服务运行的是本轮之前的代码，它的 `/ready` 没有这三项（只读查询，`database_backend`、`week2_semantic`、`code_identity` 都为 `null`）。这一点在网页上就能区分新旧实例。

## 4. 新 run 的元数据（A3）

新 run 的 `metadata.json` 新增 `run_environment` 块（`comqutor_alpha/run_environment.py`，schema `comqutor.run_environment.v1`），内容如下：
- `execution_type`：John 定义的三种之一，`fresh_run` / `frozen_input_recompute` / `old_result_reevaluation`；
- `database`：dialect 和库名；
- `code_identity`；
- `effective_config`：研究 agent 的 profile、模型、请求上限和重试，以及 Week 2 各任务的超时、重试、批大小、并发和 max_tokens。

写入位置：

| 路径 | 写入点 |
|---|---|
| Fresh Run | `tradingagents_output_writer.py` |
| 冻结输入重算 | 离线 API 路径 |
| 旧结果重评 | `classification_recovery.py`，同时写入 `based_on_run_environment` |

其他规则：
- 历史 run 不回填。
- 取不到的值记为 unavailable，并写明原因。
- 不含凭证（单元测试断言密码字符串不出现在输出里）。

## 5. 在当前代码上的链路验证（A5）

| 步骤 | 做法 | 结果 | 文件 |
|---|---|---|---|
| 空库迁移 | 实例第一次启动时，`build_write_repository_from_env` 对空的 `comqutor_alpha_t4_test` 执行迁移 | 7 个迁移，9 张表 | `migrations_result.json`、`final_code/migrations_result.json` |
| 冻结材料经生产持久化路径（1）| 生产 API 作业路径（POST /api/research，离线模式）：V1 = NVDA 10-02 run 保存的 12 份 agent 输出（冻结输入重算） | completed；raw 输出、agent 列表、sha256 与源 run 完全相同 | `submit_result.json`、`consistency_result.json` |
| 冻结材料经生产持久化路径（2）| 生产派生路径 `finalize_classification_recovery_execution`：AMD 最终执行（root c904d4cc）和 SNDK 历史 run，作为旧结果重评 | AMD：partial（1 次分类调用失败）；SNDK：completed；基准 run 不变；复制件与原件逐字节相同 | `frozen_runs_persisted.json` |
| 模拟失败（标注 SIMULATED）| V5：提交后在运行中有意重启实例 | failed，`SERVER_SHUTDOWN`；重启后未自动续跑 | `submit_interrupt_result.json`、`instance_connections_during_v5.txt` |
| 模拟空输入（标注 SIMULATED）| V4：一份内容为空的 agent 输出 | **记为 completed**，0 条 claim，摘要为"已验证证据不足"。这一点作为发现和产品决定列出，见 `READINESS_STATUS.md` | `submit_result.json` |
| 重启后重开历史 | 重启前后各对全部 run 做快照（详情、状态、图、冲突、agent 输出、关键证据追溯、产物）| 完全相同 | `compare_pre_restart_post_restart_result.json` |
| 最终代码上再核一次 | 实例在最终代码（tracked diff `b5e91198…`）上重启后，再快照、比较、Export、一致性 | 与重启后快照完全相同；Export 哈希与前一次相同 | `final_code/` |
| Export | 对每个 run 调 GET /export，ZIP 与 artifact_manifest 和 run 目录逐文件比对 | 4 个 run：清单内文件全部在 ZIP 中，且逐字节一致；中断的 run 返回 409 `EXPORT_NOT_READY` | `export_result.json`、`final_code/export_result.json` |
| run_id／输入／哈希一致 | 数据库行、run 目录、metadata 三方比对；派生 run 的 lineage 与输入哈希；`run_environment` | 5 个 run 全部一致 | `consistency_result.json`、`final_code/consistency_result.json` |

已知范围限制（不是本轮改动造成的）：
- Export 只包含 `artifact_export.py` 文件清单里的文件。
- run 目录中的以下文件不在任何清单里，所以不进 ZIP：`market_data_snapshot.json`、`data_sanity.json`、`extracted_structures.json`、`formal_acceptance.json`、`week3_pipeline_status.json`。
- `error_logs/` 下的请求/回复审计也不进 ZIP。

## 6. 必需的 PG 测试（A6）

命令：`bash tools/run_t4_tests.sh pg`。
- 连接 `comqutor_alpha_t4_pytest_test`，不连 8000 的库。
- 只要有跳过，整组就判失败（退出码 3）。

| 次序 | 代码 | 结果 | 退出码 | 日志 |
|---|---|---|---|---|
| 第 1 次 | 中间代码 | 2 failed（新测试的断言写错，见第 2 节），62 passed | 1 | `pg_attempt1_test_expectation_bug.log` |
| 第 2 次 | 修正断言后 | 64 passed，0 skipped | 0 | `pg_run1.*` |
| 最终 | 最终代码 | **64 passed，0 skipped** | **0** | `test_evidence/pg.log`、`pg_junit.xml`（含每个 nodeid）、`pg_command.txt` |

10 个文件：
- `test_agent_outputs_postgres_integration.py`
- `test_agent_outputs_source_linking_db_migration.py`
- `test_content_support_reevaluation_postgres_integration.py`
- `test_graph_persistence_postgres_integration.py`
- `test_research_progress_postgres_integration.py`
- `test_research_runs_postgres_integration.py`
- `test_t1_market_source_fields_postgres_integration.py`
- `test_w5_1b_postgres_integration.py`
- `test_week4_postgres_persistence.py`
- `test_t4_required_postgres_integration.py`（新增）

网络陷阱：外发尝试 0 次。陷阱只覆盖 Python 层的 socket；psycopg 经 libpq 在本地代码中连接 PostgreSQL，所以回环计数显示 0。PG 连接地址本身是 127.0.0.1:5433。

## 7. 复现命令

```
T=docs/audit_artifacts/round_source_linking_t0_t2/round27_t4_phase_a_20261008
python $T/tools/create_t4_databases.py --out $T/01_postgres/databases.json
bash $T/tools/start_t4_instance.sh verify                 # 8002，只能处理冻结或离线输入
python $T/tools/run_with_network_trap.py $T/tools/persist_frozen_runs.py --report $T/01_postgres/frozen_runs_persisted.json
python $T/tools/verify_postgres_chain.py submit --out-dir $T/01_postgres
python $T/tools/verify_postgres_chain.py snapshot pre_restart --out-dir $T/01_postgres
#   （重启 8002）
python $T/tools/verify_postgres_chain.py snapshot post_restart --out-dir $T/01_postgres
python $T/tools/verify_postgres_chain.py compare pre_restart post_restart --out-dir $T/01_postgres
python $T/tools/verify_postgres_chain.py export --out-dir $T/01_postgres
python $T/tools/verify_postgres_chain.py consistency --out-dir $T/01_postgres
bash $T/tools/run_t4_tests.sh pg
```
