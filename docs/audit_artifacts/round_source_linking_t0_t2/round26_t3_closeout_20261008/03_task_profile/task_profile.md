# 本次验证配置接入可选择的执行 profile

## 1. 怎么选择

设置 `COMQUTOR_WEEK2_LLM_PROFILE=t3_verified_20261008` 即可选用（定义在 `comqutor_alpha/structure_engine/week2_execution_profile.py`）。

- **不设置时**（所有现有部署，包括正在运行的服务）：行为与改动前完全相同。
- **名称写错时**：不构建网关，记录配置错误 `WEEK2_LLM_PROFILE_UNKNOWN`，不会悄悄退回默认值。
- **当前服务**：没有重启。正在运行的进程仍是旧代码，也没有设置这个变量。

## 2. 配置对照（实测）

数据来自 `config_before_after.json`，由 `tools/build_config_comparison.py` 生成。做法是用生产函数 `build_server_week2_llm_gateway` 真正构建网关，再从对象上读回每个值，不是照抄配置描述，也不发送请求。

| 任务 | 项 | (a) 现行部署（.env 加代码默认值，不选 profile；本轮未改） | (b) T3 执行时的冻结配置（签署计划） | (c) profile `t3_verified_20261008` |
|---|---|---|---|---|
| 内容核验 | 客户端读超时／应用层超时 | 45 s／45 s | 120 s／120 s | 120 s／120 s |
| | 每批条数 | 5 | 1 | 1 |
| | 应用层重试／SDK 重试 | 1／0 | 0／0 | 0／0 |
| | 请求与回复审计 | 关（除非启动器打开） | 开 | 开 |
| Alpha | 超时 | 45 s／45 s | 45 s／45 s | 45 s／45 s |
| | 调用方式／并发 | 单条／4 | 单条／4 | 单条／4 |
| | 重试 | 1／0 | 0／0 | 0／0 |
| 方向 | 超时 | 45 s／45 s | 120 s／120 s | 120 s／120 s |
| | 批次／并发 | 10 条一批（生产常量）／4 | 10／4 | 10／4 |
| | 重试 | **2**／0（方向任务在重试数大于 0 时被提高到 2） | 0／0 | 0／0 |
| 三个任务共同 | 模型、output cap、prompt | deepseek-v4-flash，不发送 output cap，v2.1／v7／v3 | 相同 | 相同 |

- **(c) 与 (b) 逐项相同**：`profile_equals_execution: true`。
- **(a) 与 (b) 不同**，所以：
  - 本次 T3 成绩只代表 (b) 这套配置，不代表现行部署。
  - 过去的执行仍按当时冻结的配置解释，不改写成使用新 profile。
- **profile 不改变的东西**：模型、prompt 模板、候选范围、判断标准；不涉及的任务（structured_adapter、structure_extractor）继续使用共享的环境超时。
- **重试设置作用于整个网关**：网关只有一个重试设置。选用 profile 后，同一网关上的其他任务应用层重试也是 0。
- **120 s 是配置选择，不保证成功**：本次执行中内容核验最长 82.5 s，方向任务只有 3 个小批次（最长 15.9 s）。

## 3. 生效证明（零网络；真实生产构造，只替换最底层 HTTP transport）

`tests/test_week2_execution_profile.py` 覆盖以下 7 项：

1. **不选 profile 时**：超时、重试、审计、并发都按环境变量取值，行为不变。
2. **选用 profile 后，网关层面的值**：
   - 三个任务的应用层超时分别是 120／45／120；
   - 应用层重试为 0，方向任务也是 0；
   - 审计开启；
   - 并发 4／4，即使环境变量写的是 8；
   - 不在 profile 内的任务仍用环境超时。
3. **每个任务各发一个请求后，从线路审计核对**：
   - `x-stainless-read-timeout` 分别是 120.0／45.0／120.0，`x-stainless-retry-count` 为 0；
   - 请求体只有 `messages, model, stream` 三个键，没有意外增加的控制字段；
   - 鉴权头已脱敏为 `REDACTED`；
   - 应用层 `call_with_timeout` 实际收到的超时分别是 120／45／120。
4. **批次大小**：profile 的批次大小 1 确实传到了内容核验的生产调用，即使环境变量写的是 5。
5. **名称写错**：不构建网关，并记录原因。
6. **超时和 HTTP 500**：
   - 发出后没有回复（unknown）时，只发送 1 次，不自动重发；
   - HTTP 500 时，同样只发送 1 次；
   - 两种情况都记为调用失败：`valid_none_count = 0`，`call_failure_count = 1`，不会变成有效 NONE。
7. **与 T3 执行的线路审计对照**：`execution_wire_headers.json` 汇总了原执行全部 60 个请求，读超时、重试数、请求体键、模型和 URL 与上面 profile 测试的值完全相同。

## 4. 内容核验接入现有调用账本（最小接线，不另建审计系统）

**改动前**：`content_support_verification` 不在 `SEMANTIC_TASKS` 中。生产中每次内容核验都无法开始语义记录（`SEMANTIC_RUNTIME_CALL_START_FAILED`，会话被标为 incomplete），调用账本里没有它。

**改动**（共 3 处）：
1. `llm_runtime/contracts.py`：登记该任务。先例是 `evidence_stance_classifier` 也是这样补登记的。
2. `replay/source_bundle.py`：在任务清单和身份表中登记它的 v2.1 身份。prompt 哈希从生产代码实时读取，与签署计划中的一致。
3. `content_support_llm._process_batch`：
   - 把 claim id 作为带外参数传给网关。只在网关声明了这个参数时才传，规则与 `alpha_mapper` 相同，不进入 prompt，也不进入缓存键。
   - 等逐项校验完成后再结束这次调用的记录。如果批内所有条目都被拒绝，账本记为 rejected 并写明原因，例如 `quote_or_data_not_found`。
**验证**：测试 `test_content_support_calls_are_recorded_in_the_semantic_ledger_with_item_outcome` 用生产网关、真实会话和保存的真实回复验证，账本记录中包含：
   - task、prompt 版本和哈希、provider、model；
   - claim id、attempt id、usage、retry_count；
   - 被拒条目的 `validation_status=rejected` 和 `fallback_reason=quote_or_data_not_found`；
   - 会话不再出现 incomplete 或 `SEMANTIC_RUNTIME_CALL_START_FAILED`。

**限制**
- 一批多条且部分被拒时，账本只能记为整次调用 accepted，每条的原因保留在各自记录上。profile 每批 1 条，所以没有这种情况。
- Exact Replay 还没有内容核验的绑定实现（`replay/semantic_binding.py`）。带这类记录的 run 会报 `EXACT_REPLAY_SEMANTIC_TASK_UNSUPPORTED`。这类 run 原本就因账本不完整而不能精确重放，本轮没有改变这一点。
- 冻结的 T3 驱动有意不给内容核验挂会话，所以离线重放中内容核验的账本仍为 0 条。生产路径由上面的测试证明。

**后续真实产品运行的证明**归入原定 T4，本轮不追加付费验证。
