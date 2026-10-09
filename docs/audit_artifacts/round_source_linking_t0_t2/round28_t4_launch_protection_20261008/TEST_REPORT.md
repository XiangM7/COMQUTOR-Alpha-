# Round 28：测试命令、结果、退出码与失败归因

- 所有 pytest 组都挂了 `net_trap_plugin`：任何非回环连接都会报错并计数。
- 原始日志、junit（含每个 nodeid）、命令、开始时间和退出码都在 `test_evidence/`。
- 最终测试所跑的代码身份记录在 `code_identity_under_final_tests.txt`：tracked `1b53b921…`，untracked `38ef636f…`。这与重启后的 8002 和 `04_refreeze/frozen_config.json` 是同一代码。

## 1. 最终结果（最终代码）

| 组 | 命令 | 结果 | 退出码 | 外网尝试 |
|---|---|---|---|---|
| 本轮新增 + Round 27 环境/计量测试 | `bash tools/run_r28_tests.sh new` | **38 passed** | **0** | 0 |
| 受影响回归（53 个文件，不是 Round 27 的 1067 项整组） | `bash tools/run_r28_tests.sh affected` | **918 passed，2 failed，1 skipped** | 1 | 0 |
| 作业超时探针（真实作业管理器，30 秒） | `tools/run_termination_probe.py --plan hang …`（`02_timeout_preservation/final_code/job_timeout_probe/`） | failed `RESEARCH_TIMEOUT`，31 秒；已完成 2、在途 2、未发送 4 | 0 | 0 |
| 作业超时后的零调用重建 | `tools/inspect_terminated_run.py`（在网络陷阱下运行） | 2 条已完成结果与账本一致；模型调用 0 次；原目录未变 | 0 | 0 |
| 内容核验中途终止探针 | `tools/run_cs_termination_probe.py`（`02_timeout_preservation/final_code/cs_termination_probe/`） | worker −15；已完成 1、在途 1；重建结果一致；模型调用 0 次 | 0 | 0 |

- 跳过的 1 个：`tests/test_week2_llm.py:1214`，需要设置 `COMQUTOR_RUN_WEEK2_PROVIDER_SMOKE=1` 才会做真实调用，本轮不开启。
- 剩下的 2 个失败都不是本轮引起的。两个测试读取的输入与 Round 27 冻结版本**逐字节相同**（`preexisting_failure_inputs_unchanged.txt`，方法：从 HEAD 加 Round 27 快照差异重建出这两个文件后比较），测试文件本身本轮也没有改：

| 测试 | 断言 | 原因 |
|---|---|---|
| `test_structured_adapter_concurrency.py::test_structured_adapter_concurrency_touches_no_alpha_mapping_code` | `structured_output_adapter.py` 全文不得出现 `alpha_mapper` | 该文件已有的注释含 "mirrors alpha_mapper's own …"。本轮没有改这个文件 |
| `structured_output_shadow/test_shadow_semantic_runtime.py::test_structured_claim_shadow_is_additive_to_semantic_tasks` | `SEMANTIC_TASKS` 等于不含 `content_support_verification` 的集合 | Round 26 把内容核验登记进了 `SEMANTIC_TASKS`（`contracts.py`）。本轮没有改这个文件 |

## 2. 过程中的失败与修复（如实记录）

| 次序 | 结果 | 原因 | 处理 |
|---|---|---|---|
| `new_run1` | 37 passed | — | — |
| `affected_run1` | 905 passed，**15 failed** | **13 个是我造成的**：（1）我把停止状态挂在共享的网关构建函数里，所有使用它的驱动都受影响，包括恢复和评估驱动（它们有自己的停止规则）；同一测试文件复用 run_id，一个测试中的 401 让后续测试被拒（`not_sent` 而不是 `failed`）。（2）没有挂停止状态的网关也不再重试 429，违背了"没挂停止状态时行为不变"。另外 2 个是上面那两个与本轮无关的失败 | 停止状态改为只由研究流水线挂上（`routes_research.attach_run_provider_stop`，请求结束时释放）；不重试和中断只在挂了停止状态时生效。新增测试：没挂停止状态的网关仍按原规则重试 429。两个恢复测试文件随后 33/33 通过 |
| `affected_stopped_partial` | 中途停止 | 运行期间我修改了代码（加 `week2_gateway_budget.json`），有子进程的测试会读到混合代码 | 停止，改完后重跑 |
| `new_run2`、`affected_run2_stopped_import_order` | 38 passed；后者中途停止 | 运行开始后我又调整了 `routes_research.py` 和 `tradingagents_runner.py` 的 import 顺序（ruff I001） | 停止，在最终代码上重跑（即第 1 节的结果） |

ruff 检查本轮改动的文件：
- 新增文件没有问题；
- 改动文件中只剩改动前就存在的问题（`routes_research.py:369`、`tradingagents_runner.py:528` 的 I001，以及 `week2_llm.py` 中已有的 E402 系列）；
- 本轮在 `week2_llm.py` 新增的那行 import 也是 E402，和该文件既有写法一致（它的 import 本来就排在模块级 contextvar 之后）。

## 3. 探针的第一次运行（保留作为过程证据）

| 运行 | 说明 |
|---|---|
| `probe_evidence/hang_reused_calibration_run/` | 请求与校准运行完全相同，系统按请求指纹复用了已完成的 run，没有执行新的请求。之后给每次运行分配不同的 analysis_date |
| `probe_evidence/hang/`、`cs_probe_evidence/` | 在停止状态挂载位置调整之前的代码上运行。超时保留的机制（逐次写账本、审计、作业管理器）在之后没有改，最终代码上重跑的结果相同（`final_code/`） |
| `cs_probe_evidence/*_attempt1_without_profile*` | 第一次重建没有带执行 profile，内容核验按默认每批 5 条打包，请求与原来不同，缓存全部未命中。说明重建必须使用该 run 自己的配置；新 run 的 `metadata.run_environment` 记录了 profile，工具会自动读取 |
