# 受影响测试：命令、原始日志、退出码和失败归因

## 运行方式

在仓库根目录运行 `bash docs/audit_artifacts/round_source_linking_t0_t2/round26_t3_closeout_20261008/tools/run_affected_tests.sh <label>`。测试清单写在脚本里：

- 本轮新增的 3 个测试文件；
- 内容核验、网关、profile、审计和并发相关测试；
- 语义账本和 Exact Replay 的任务登记；
- 只被读取、没有修改的消费方（方向、筛选器、验证门、完成度指标）；
- 冻结的 T3 驱动；
- 指向已改文件的冻结哈希测试。

所有测试都在出站网络陷阱下运行（`tools/net_trap_plugin.py`）。

| 标签 | 命令 | 日志 | JUnit | 退出码 | 结果 | 外网尝试 |
|---|---|---|---|---|---|---|
| `first_pass` | `command_first_pass.txt` | `pytest_first_pass.log` | `junit_first_pass.xml` | 1 | 704 passed，4 failed，1 skipped | 0 |
| `final`（最终代码） | `command_final.txt` | `pytest_final.log` | `junit_final.xml` | **1** | **704 passed，4 failed，1 skipped** | 0（`net_trap_final.json`） |

`superseded_final_before_lint_fix/` 里是上一次 `final` 的结果，结果相同。之后 `week2_llm.py` 只做了一处 lint 改写（`try/except/pass` 改为 `contextlib.suppress`），行为不变。改写后，代码差异、离线重放、诊断、配置对照和上表的 `final` 都在最终代码上重新生成过。

新增的 3 个测试文件共 46 个用例，全部通过：
- 引用与账本 17 个；
- profile 7 个；
- 关系消费 22 个。

## 4 个失败：逐个归因（没有删除断言、没有加 skip、没有重钉哈希）

| 测试 | 失败原因 | 归因 | 证据 |
|---|---|---|---|
| `tests/structured_output_shadow/test_source_integrity.py::test_current_semantic_components_match_approved_phase1_master_baseline` | 钉住的 `week2_llm.py`、`structured_output_adapter.py` 等哈希与当前文件不同 | **本轮之前已失败**：钉住的值（例如 `week2_llm.py` 为 `5c9106a3…`）与改动前的文件（`fd338648…`，与执行冻结快照一致）本来就不同 | `pytest_pre_change_attribution.log`：在只含改动前代码的临时目录中运行，同样失败 |
| `tests/structured_output_shadow/test_phase1b1_boundaries.py::test_existing_three_task_instructions_text_unchanged` | `_TASK_INSTRUCTIONS` 多了 `content_support_verification` | **本轮之前已失败**：这个任务说明在改动前就存在（第 9 轮加入），本轮没有增加任务说明 | 同上 |
| `tests/test_structured_adapter_concurrency.py::test_structured_adapter_concurrency_touches_no_alpha_mapping_code` | 适配器源码中出现字符串 `alpha_mapper` | **本轮之前已失败**：出现在改动前就有的注释里（"mirrors alpha_mapper's own …"）；本轮在适配器中加入的只有 profile 导入 | 同上 |
| `tests/test_t3_joint_sample_driver.py::test_the_v4_sample_and_its_materials_rebuild_byte_for_byte` | 重建出的 v4 清单中，3 个替换样本的 `prior_mentions_in_docs.data_files_count` 变大（23→38、3→18、1→10） | **由本轮新增文件引起，不是代码问题**：Round 25 的构建器会统计 `docs/audit_artifacts` 下提到该 claim 的数据文件数，本收尾目录新增的重放和诊断文件正好提到这些 claim | `v4_rebuild_excluding_closeout.json`：只把本收尾目录排除出统计，6 个文件与冻结的 `B1_samples_v4/` 逐字节相同；冻结的 v4 文件本身没有变化（见 `hash_proof/`） |

**跳过的 1 个**：`tests/test_week2_llm.py::test_explicit_low_cost_provider_smoke`。这个测试只有设置 `COMQUTOR_RUN_WEEK2_PROVIDER_SMOKE=1` 才会发出真实调用，属于原有设计，本轮不发送请求。

## 改动前对照（`pytest_pre_change_attribution.log`）

上表前 3 个失败在改动前的代码上也失败：

- 临时目录中放的是改动前的 `comqutor_alpha/`：用 `code_before/` 覆盖已改文件，并删除新增的 profile 模块；这些副本已与执行的冻结代码快照或 HEAD 核对过哈希。
- 通过 `PYTHONPATH` 让 Python 导入临时目录中的代码，导入路径已打印确认。
- 3 failed，退出码见 `exitcode_pre_change_attribution.txt`。

## 证明范围

- 离线重放、固定 HTTP 响应和构造夹具只证明接线和规则，不代表新的真实模型验证。
- 真实模型证据只有原执行保存的 60 个回复。
