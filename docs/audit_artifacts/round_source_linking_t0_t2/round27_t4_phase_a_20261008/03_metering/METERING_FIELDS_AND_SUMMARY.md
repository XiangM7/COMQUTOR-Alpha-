# C. 两层计量：字段、汇总规则与复现（T4 Phase A）

实现：`comqutor_alpha/llm/run_usage_report.py`（新增，schema `comqutor.llm_usage_report.v1`）和 `comqutor_alpha/llm/cost_basis.py::estimate_cost_with_cache_split`。

两种使用方式：
- **新 run**：完成时把报告写进自己的 run 目录（`llm_usage_report.json`，写在 artifact manifest 之前；Export 中"存在才带"）。写报告失败不会让 run 失败，只记一条 `llm_usage_report` 错误日志。
- **已有 run**：用 `tools/build_usage_reports.py` 生成派生报告，写进本目录。原 run 目录只读，哈希证明见 `hash_proof/`。

## 1. 逐次请求记录（`requests[]`，一次 HTTP 请求一条）

| 字段 | 含义 / 来源 |
|---|---|
| `layer` | `research_agent`（TradingAgents 自己的调用，`tradingagents_llm_calls.jsonl`）或 `week2_semantic`（语义网关，`llm_semantic_calls.jsonl` + 线路审计） |
| `run_id`、`step` | 所属 run 和步骤。Week 2 用语义任务名；线路审计里的网关任务名映射到同一个名字，例如 `claim_batch_enrichment` → `structured_adapter` |
| `client_api_style` | 客户端协议，都是 `openai_compatible` |
| `provider_reported` | 原记录中的 provider，原样保留。研究 agent 层是 LangChain 打的 `openai` 标签 |
| `provider_resolved` | 实际计费的 provider，由模型名和配置的 DeepSeek 端点确定。与 `provider_reported` 并列保存，不覆盖原值 |
| `model_requested`、`model_returned` | 请求的模型和回复里的模型（DeepSeek 对 `deepseek-v4-flash` 回 `deepseek-flash`）。研究 agent 层的原记录没有回复模型，记为 null |
| `call_id`、`attempt_id`、`attempt_number`、`provider_request_id` | 逻辑调用、尝试、请求身份。Week 2 尝试的身份是 (任务, attempt_id)，因为 attempt id 按网关编号，不同任务会重复 |
| `started_at`、`completed_at` | 来自线路审计的时间；没有审计时用账本时间（首次尝试开始、末次尝试结束） |
| `outcome` | `success` / `failure` / `timeout` / `unknown` / `not_sent`（规则见第 3 节） |
| `error_code`、`finish_reason`、`is_retry`、`client_retries_within_call` | 失败码、结束原因、是否重试。研究 agent 层的重试发生在单次调用内部 |
| `raw_usage` | 提供方返回的原始 usage，原样保留 |
| `tokens` | input、output、reasoning、cache_hit、cache_miss，都取自 `raw_usage`；没有报告的种类是 null，不是 0 |
| `usage_status` | `known` / `missing` |
| `cost` | `estimated`（带 `basis`、`usd_off_peak_floor` 闲时下限、`usd_peak_ceiling` 高峰上限）或 `not_estimable`（带原因）或 `not_sent` |

## 2. 每个 run 的统一汇总（`totals.research_agent` / `totals.week2_semantic` / `totals.all`，以及 `per_step`）

| 字段 | 含义 |
|---|---|
| `upstream_agents` | 上游 agent 数和名单（来自 `raw_agent_outputs.json`） |
| `logical_calls` | 逻辑调用数（Week 2 账本一条记录算一次） |
| `served_from_cache` | 命中本 run 内存缓存、没有发请求的调用 |
| `not_sent`、`not_sent_reasons` | 发送前就被拒的调用，例如调用预算用完、审计不可用 |
| `budget_reservations` | 实际发出的请求数（每次都先占预算） |
| `actual_http_requests` | 实际 HTTP 请求数，等于 `budget_reservations` 加研究 agent 层调用内部的重试 |
| `retries` | 重试数 |
| `outcomes` | success / failure / timeout / unknown 各多少 |
| `tokens_known` | 各类 token 合计。没有任何请求报告过的种类是 null |
| `requests_with_usage`、`requests_missing_usage`、`usage_missing_ratio` | usage 已知 / 缺失的请求数和缺失比例 |
| `cache_split_reported_requests` | 报告了缓存命中拆分的请求数 |
| `cost_estimate_usd` | 已知部分的估算（闲时下限、高峰上限），可估算和不可估算的请求数，以及不可估算的原因 |
| `deduplication`、`corrections`、`pricing`、`known_gaps`、`data_sources` | 去重规则和计数；provider 更正；价格来源；已知缺口；每个输入文件的 sha256 |

## 3. 规则（任务书 C 的约束逐条对应）

- **按请求身份去重。** 请求只从 Week 2 账本的 `request_attempts` 计数。账本顶层的 `token_usage` 只是最后一次尝试的副本，不重复计入，并在 `ledger_records_where_top_level_usage_is_last_attempt_only` 中计数。账本有、审计也有的尝试按 (任务, attempt_id) 合并成一条；只在审计中出现的请求单独记一次（`audit_only_requests`）。
- **客户端与提供方分开记录。** 更正只出现在派生报告的 `corrections` 中，原记录不改。
- **不从耗时推算 token。**
- **超时或结果未知且没有 usage 的请求，成本记为 `not_estimable`**（原因 `usage_missing`），不记为 0。
- **outcome 的判定：**
  - 发出后连接断开、没有收到回复（`WEEK2_LLM_TRANSPORT_ERROR`）记为 `unknown`：提供方可能已经处理并计费，也可能没有。
  - 线路审计显示收到了错误回复（如 HTTP 500）记为 `failure`。
- **金额都是估算。** 价格表是 DeepSeek `deepseek-v4-flash`（官方文档注明是 deepseek-flash 的旧别名），文档查询日期 2026-09-30，来源 https://api-docs.deepseek.com/quick_start/pricing。
  - 闲时：输入（未命中缓存）$0.15/M，命中缓存 $0.003/M，输出 $0.60/M。
  - 高峰：上述价格的 2 倍。
  - reasoning token 算在输出里。
  - 回复没有报告缓存拆分时，全部输入按未命中价计。

## 4. 三个 run 的派生报告（NVDA、AMD、T3）

| run | 层 | 逻辑调用 | HTTP 请求 | 未发送 | 成功 / 失败 / 超时 / 未知 | usage 缺失 | 已知部分估算（美元，闲时–高峰） | 不可估算请求 |
|---|---|---|---|---|---|---|---|---|
| NVDA `034a0a60`（10-02 Fresh） | 研究 agent | 20 | 20 | 0 | 20/0/0/0 | 0 | 0.066–0.132 | 0 |
| | Week 2 | 838 | 448 | 400（预算用完） | 437/0/9/2 | 11 | 0.172–0.345 | 11 |
| AMD `1bad76a7`（10-05） | 研究 agent | 15 | 15 | 0 | 15/0/0/0 | 0 | 0.037–0.073 | 0 |
| | Week 2 | 555 | 450 | 107 | 445/0/5/0 | 5 | 0.250–0.501 | 5 |
| AMD `c904d4cc`（10-06） | 研究 agent | 21 | 21 | 0 | 21/0/0/0 | 0 | 0.064–0.128 | 0 |
| | Week 2 | 12 | 12 | 0 | 8/0/4/0 | 4 | 0.020–0.041 | 4 |
| AMD 恢复 `recovery-…26d6cd1a` | Week 2 | 973 | 955 | 0 | 954/0/1/0 | 1 | 0.428–0.857 | 1 |
| T3 `t3joint-…bd99811e` | Week 2 | 43 | 60 | 0 | 60/0/0/0 | 0 | 0.143–0.285 | 0 |

各报告的已知缺口（引自之前的核对记录，不补数）：
- **NVDA `034a0a60`**：账本只记录了 448 次真实尝试，实际约 688 次。约 240 次尝试因并发审计缺陷（第 12/13 轮已修）丢了逐次记录，它们的 usage 和成本未知，**不在合计内**。另有 400 次 Alpha 调用在 700 次预算处被拒，没有发送。
- **AMD `c904d4cc`**：975 次 Alpha 调用中有 973 次在审计层失败，没有留下语义账本记录。每次是否到达提供方，记在第 12 轮目录里，不在本报告内。
- **T3**：执行时内容核验还没有登记到语义账本（第 26 轮已修），17 次请求只来自线路审计。T3 的请求数和 token 合计与执行报告完全一致。
- **研究 agent 层（所有 run）**：
  - TradingAgents 的原记录中 `agent_label` 是"股票代码:日期"，不是 agent 角色，所以研究 agent 层的 `per_step` 只能按这个标签分组；
  - 原记录没有回复模型，也没有缓存拆分。

演练验证（04_fresh_prep）：
- 在 1800 上限的演练中，假传输层看到 1213 次请求，报告也是 1213 次，结果为 1005 成功、105 失败（HTTP 500）、103 未知（发出后断开）。
- 在 60 上限的演练中，60 次发送，1126 次未发送（`WEEK2_LLM_CALL_BUDGET_EXHAUSTED`）。

## 5. 复现命令

```
T=docs/audit_artifacts/round_source_linking_t0_t2/round27_t4_phase_a_20261008
python $T/tools/run_with_network_trap.py $T/tools/build_usage_reports.py --out-dir $T/03_metering
# 新 run：完成时自动写 <run_dir>/llm_usage_report.json；手动重建（只读 run 目录，输出到 stdout）：
python -c "import json,sys; from comqutor_alpha.llm.run_usage_report import build_usage_report, sources_for_run_dir; print(json.dumps(build_usage_report(sources_for_run_dir(sys.argv[1]))['totals'], indent=1))" outputs/t4_runs/<run_id>
```

测试：`tests/test_t4_phase_a_environment_and_metering.py` 中与 usage report 和成本相关的测试覆盖以下情况：
- 逐请求计数、跨网关同号尝试、任务名映射；
- outcome 判定、缺失 usage 不记为 0、未报告的 token 种类为 null；
- provider 更正、只写一个文件且不改其他文件；
- 缓存拆分计价。
