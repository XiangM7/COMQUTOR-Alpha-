# T4 Round 28：启动保护（认证／限流停止、超时后结果保留）

承接 Round 27 T4 Phase A。本轮只做两项保护，没有新增任何 Provider、搜索或取数调用：

- 本地 PostgreSQL、回环 API 和底层假 HTTP 测试用于验证；
- 8000／8001／5175／5176 没有触碰；
- 没有修改模型、prompt、taxonomy、Gold、核验标准、评分阈值或 PD-006；
- 没有 commit 或 push；Round 27 包未改动（哈希证明见 `hash_proof/`）。

固定回复只证明工程行为，不证明模型语义质量。

## 1. 认证或限流后的停止保护

### 结论
在网页 Fresh Run 的生产路径上，首次收到 HTTP 401、403 或 429 后，同一个 run 的两层都不再发送新的模型请求：

- 研究 Agent 层：`tradingagents_runner` 加上预算守卫；
- Week 2 层：`run_research_request` 构建的网关，带审计传输层。

### 实现
- **停止状态。** 新模块 `comqutor_alpha/run_provider_stop.py`，每个 run_id 一个停止状态对象。
  - 首次拒绝记录：状态码、层、任务、call_id、attempt_id、时间、脱敏后的原因（去掉 `sk-…`、Bearer 和 api key）。
  - 锁只保护内存状态和一次小文件写入，从不跨越网络等待；其他 run 是另一个对象。
  - `provider_stop.json` 原子写入 run 目录，Export 中"存在才带"。
- **研究 Agent 层**（`runners/request_budget.py`、`tradingagents_runner.py`）：
  - 预算守卫在每次请求真正发送前检查停止状态，停止后抛 `RunProviderStopped`，不计入已发送；
  - 收到 401／403／429 时触发停止，并且不重试。这一点修复了一个实际缺口：Research Manager、Trader、Portfolio Manager、Sentiment 的结构化调用失败后，TradingAgents 会再发一次纯文本请求，以前这次请求会真实发出，现在发送前就被拒；
  - 停止时沿用预算停止的部分保存：已收到的 agent 输出、停止原因、调用账本都保留；即使没有可保存的 agent 输出，停止记录和调用账本也写入该 run 目录；
  - 失败映射为 `PROVIDER_REFUSED_RUN_STOPPED`，不再是笼统的 `INTERNAL_ERROR`。
- **Week 2 层**（`week2_llm.py`）。只有研究流水线会挂上停止状态（`routes_research.attach_run_provider_stop`）；恢复和评估驱动有自己的停止规则，行为不变。
  - 三个尝试循环（带 trace、prebuilt、legacy）在占用预算之前检查停止状态；
  - 审计传输层的请求钩子（转发前的最后一点）再检查一次，用来覆盖"通过网关检查之后、转发之前，别的请求刚触发了停止"的竞态；
  - 401／403／429 最早在响应审计处就触发停止（客户端库抛异常之前），该次尝试记为失败，不重试；
  - 停止后才返回的在途请求照常保存各自的响应，并列在 `answered_after_stop_in_flight`；
  - 未发送的调用记为 `not_called` 加 `WEEK2_LLM_RUN_STOPPED_AFTER_PROVIDER_REFUSAL`。
- **下游映射。** Alpha 记为 `provider_stopped`，属于"故障导致未执行"，不会变成 NONE；内容核验和方向判断各新增 `provider_stopped` 回退原因，不再误标为 `provider_error`。
- **状态。** 被停止的 run 永远不会是 completed，沿用 partial／failed 规则。停止记录在 Week 1-2 结束、artifact manifest 写入之前最终落盘，所以 manifest 中的哈希与文件一致。

### 测试证据
`tests/test_t4_round28_provider_stop.py` 走真实客户端、网关、任务调度和审计，只替换底层 transport：
- 401、403、429 分别测试；
- 并发：4 个 Alpha 请求在途，1 个被拒，3 个在停止后返回并保存（身份逐一对应），排队的 4 条未发送；
- 停止之后到达 transport 的请求为 0，后续阶段也没有请求；
- 研究 Agent 层：Research Manager 的结构化调用收到 401／403／429 后，纯文本兜底请求没有发出，Week 2 层发出 0 次；
- 同一 run 两层共享停止状态，其他 run 不受影响；其他 run 的 4 个并发请求能同时在途，说明没有锁跨越网络等待；
- 传输层钩子的竞态被拦下；
- 成功路径、预算守卫、审计、零重试不变；没挂停止状态的网关仍按原来的重试规则处理 429；
- 原因已脱敏。

命令、结果和退出码见 `TEST_REPORT.md`。

## 2. 超时或 worker 终止后的结果保留

### 普通 Fresh 路径在各时点保存了什么（来自代码，并由下面两个探针在真实运行中核对）

| 时点 | 原始请求和响应日志 | 已校验、下游可用的结构化结果 |
|---|---|---|
| 研究报告和来源保存后 | 研究 Agent 层没有线路审计 | `raw_agent_outputs.json`、`metadata.json`（含 `run_environment`，带 profile）、来源登记，以及 `tradingagents_llm_calls.jsonl`（在完成时写出） |
| 声明抽取和富集完成后 | 适配器每批的请求和响应审计（原子写入） | 每次调用完成即写一行语义账本（任务、call_id、claim、输入哈希、prompt 身份、已校验输出及其哈希）；**`structured_agent_outputs.json` 要等整个阶段（含内容核验）结束才写** |
| 内容核验逐条完成后 | 每条的请求和响应审计 | 每条一行账本，含 claim_id 和已校验的判定；阶段文件同上 |
| Alpha 和方向判断逐批完成后 | 同上 | 每次调用一行账本；**`alpha_matches.json` 和 `evidence_stance_audit.json` 在阶段结束时才写** |
| 作业超时或 worker 被终止后 | 已发出、未收到响应的请求：请求审计里有，响应审计里没有，是"在途、结果未知"的证据 | 已完成调用的账本行都在；被中断阶段的阶段文件不存在；Week 3/4 产物、`llm_usage_report.json`、manifest 都不存在；数据库状态 failed `RESEARCH_TIMEOUT`，或 worker 终止时的对应状态 |

### 真实复现
| 探针 | 做法 | 结果 |
|---|---|---|
| 作业超时（`02_timeout_preservation/probe_evidence/`） | 独立的一次性 API 实例（8003），真实作业管理器和 spawn 出来的 worker，作业时限缩短为 30 秒，PostgreSQL 演练库；从回环提交一个离线请求；Alpha 第 3、4 个请求挂住不返回 | 31 秒时 failed `RESEARCH_TIMEOUT`；已完成 2 条（账本）；在途 2 条（审计有请求、没有响应）；未发送 4 条（账本 `budget_exhausted`）；`alpha_matches.json` 不存在；外网尝试 0 次 |
| 内容核验中途终止（`02_timeout_preservation/cs_probe_evidence/`） | spawn 出来的 worker 跑真实流水线；第 2 条内容核验请求挂住；按作业管理器 `_terminate_process` 的方式终止 | worker 退出码 −15；第 1 条已完成（账本）；第 2 条在途；`structured_agent_outputs.json` 不存在；外网尝试 0 次 |

### 零调用重建（`tools/inspect_terminated_run.py`）
- 读取账本，检查每行的哈希，半写的行不会被使用。
- 只用"已完成"的账本行生成缓存条目，用的是与实际运行缓存时相同的 `cache_entry_from_record`。
- 准备一个真实网关：预算已用完，未命中缓存时拒绝发送；模型一旦被调用就报错。
- 用这些条件在副本上重跑生产阶段函数（`save_alpha_matches`、`save_structured_agent_outputs`）。

| 探针 | 结果 |
|---|---|
| Alpha | 2 条已完成结果与账本逐条一致；其余 6 条都不可用，没有一条是有效 NONE；模型调用 0 次，外网尝试 0 次；原 run 目录未变 |
| 内容核验 | 已完成的判定与账本一致；在途和未到达的条目保持未核验 |

- **必须使用该 run 自己的执行配置。** 第一次重建没有带 profile：内容核验按默认每批 5 条打包，请求与原来的每次 1 条不同，缓存全部未命中。失败结果保留在 `inspect_result_attempt1_without_profile.json`。新 run 的 `metadata.run_environment` 记录了 profile，工具会自动读取。
- **结论：Week 2 各阶段的已完成结果在终止后已经在磁盘上，可以零调用重建。所以没有新增保存机制，只增加了读取和重建工具。**
- 重建产物带 `*.REBUILD_NOTE.json`，标为部分结果，不冒充完整评分或完整研究结果。
- 不会自动重发结果未知的请求，也不会自动恢复付费任务。

### 仍未完成或未覆盖的部分（如实列出）
1. **研究 Agent 阶段本身（约前 30 分钟）的中间状态只在内存中。** 这一阶段在 4 小时作业上限之内必然先跑完，所以不会被作业超时打断；但如果服务器在这一阶段停止或崩溃，这部分输出会丢失。研究 Agent 的请求也没有线路审计。本轮没有改。
2. 终止后，run 详情接口按产物推算显示 partial，数据库和历史列表显示 failed `RESEARCH_TIMEOUT`。两者都不是 completed，但口径不同。本轮没有改。
3. 终止后不会有 Week 3/4 产物、`llm_usage_report.json` 和 manifest。用量可以事后用 `run_usage_report` 只读重建。

## 3. 新冻结、预算与费用估算

### 重启和重新冻结
- **重启前检查**（`04_refreeze/pre_restart_active_jobs_check.txt`）：8002 数据库中排队或运行中的 run 为 0；历史只有 5 个验证 run，没有 Fresh Run。
- **重启**：对 pid 51194 发 SIGTERM 正常停止，再用 Round 27 的启动脚本、相同上限以 fresh 模式启动（pid 24192，日志 `04_refreeze/instance_fresh_start.log`）。启动后没有任何非回环连接。
- **冻结**：用 Round 27 的冻结工具读取运行中的进程，输出到 `04_refreeze/`（`frozen_config.json` 的 sha256 为 `f16c6abaab94…`）。**21 项检查全部通过**。
  - 代码：`7a9aefa` + tracked diff `1b53b921…` + untracked `38ef636f…`，与最终测试所跑的代码相同；`code_snapshot/` 的哈希与进程报告一致；
  - 数据库：PostgreSQL `comqutor_alpha_t4_test`；
  - Week 2：profile `t3_verified_20261008`，内容核验 120 s／每批 1 条，Alpha 45 s／并发 4，方向 120 s／并发 4；两层重试 0；审计开启；
  - 研究 Agent：上限 100，重试 0；作业上限 14400 s，同时 1 个作业；
  - prompt 身份与 T3 签署值相同（内容核验 `6abae47b…`、Alpha `ac48723f…`、方向 `d9455fd5…`）。
- **网页检查**（`04_refreeze/web_check/`，只读，没有填写表单）：5177 状态行为 "Server ready, live research configured · PostgreSQL comqutor_alpha_t4_test · profile t3_verified_20261008 · code 7a9aefa+uncommitted(1b53b921)"，Start research 按钮不可用（没有输入 ticker）。
- **Round 27 包**：冻结配置、快照、日志都没有改动，只有一处例外，见 `hash_proof/round27_log_append_check.txt`。Round 27 实例的 stdout 日志 `04_fresh_prep/instance_fresh_start.log` 在本轮被该进程追加了 7 行：我重启前的 3 次只读 GET，以及它自己的 4 行关停信息。去掉这 7 行后与本轮开始时的哈希相同，属于纯追加。

- **Week 2 上限 1800 限制的是网关预算占用次数，不是实际 HTTP 请求数**：
  - 每次尝试之前占用一次预算；
  - 占用后在传输层被拒（停止保护、审计失败）的尝试不会成为 HTTP 请求。
  - 两个数分开统计：新 run 写出 `week2_gateway_budget.json`（上限和占用次数）；`llm_usage_report.json` 的 `week2_cap_accounting` 同时列出占用次数和线路审计看到的已转发 HTTP 请求数。
- 其余上限不变：研究 Agent 实际请求 100、两层重试 0、同时一个作业、作业上限 14400 秒。
- 费用估算沿用 Round 27 的 `budget.json`，本轮的改动不影响请求量：
  - 1040 条 claim 时闲时约 $1.41–1.95，高峰上限约 $3.90；
  - 理论最坏上界 $27.54；
  - 没有美元硬上限，金额都是估算。

## 4. 启动结论

**可以等待人工启动。** 本轮两项保护都没有剩下阻塞缺陷：

- 认证或限流停止：已在生产路径上接好，并通过测试；
- 超时保留：已证明，Week 2 已完成的结果可以零调用重建；
- 8002 已加载修复后的代码并重新冻结；5177 已连接修复后的 8002。

仍然存在、但不阻塞启动的已知限制：

- 研究 Agent 阶段的中间状态只在内存中（§2）；
- 终止后详情接口和历史列表的状态口径不同（§2）；
- 内容核验串行，最坏情况可能超过 4 小时作业上限（Round 27 的 P-2）；
- PD-006、A304 召回偏低、T2 对新 run 不可评估，照旧保留。

这次 Fresh 只用来验证冻结版本的来源传递、实际配置、状态、持久化和计量，不能据此宣布语义评分或 T1–T3 通过。

由 Xiang Mao 确认预算后，在 **http://127.0.0.1:5177/research** 亲自输入 NVDA 并点击 Start Research。不会代点，也不会用 API、脚本、录制工具或后台方式代替提交。
