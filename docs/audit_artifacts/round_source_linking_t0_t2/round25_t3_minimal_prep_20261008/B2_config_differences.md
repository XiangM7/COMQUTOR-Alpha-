# B2 当前产品配置与拟执行配置（Alpha、内容核验、方向）

依据：
- **产品配置**：取自当前代码（`build_server_week2_llm_gateway`、`routes_research.py`、各任务模块常量）和 `.env` 里的变量名与取值。密钥只确认存在，不读出。
- **拟执行配置**：取自冻结计划 `B4_execution/authorized_plan_TEMPLATE.json` 的 `config`。
- **实际发送形状**：取自离线演练审计中真实客户端产生的原始请求，见 `B2_config/actual_request_shapes.json`；测试 `test_the_real_clients_send_exactly_the_frozen_request_shape` 逐项断言。

"相同 prompt、相同输入、相同模型"不等于完整配置相同，所以下表逐项列出。

## 三个任务共同

| 项目 | 当前产品 | 本次执行 | 是否相同 |
|---|---|---|---|
| 真实客户端 | tradingagents `create_llm_client(provider="deepseek")` → `DeepSeekChatOpenAI`（langchain-openai 1.3.5 / openai 2.45.0 / httpx 0.28.1） | 同一工厂、同一类 | 相同 |
| 接口 | `https://api.deepseek.com/chat/completions` | 同左（冻结；守卫逐次核对） | 相同 |
| 模型 | deepseek-v4-flash（`.env`） | deepseek-v4-flash（冻结） | 相同 |
| 输出协议 | prompt 要求只输出 JSON，从回复正文解析，不发 `response_format` | 同左 | 相同 |
| 请求体字段 | `messages`、`model`、`stream=false` | 同左（冻结；多一个或少一个字段都不发送） | 相同 |
| max_tokens | `.env` 未设分任务上限 → 不发送 | 不发送 | 相同 |
| thinking / reasoning_effort / temperature / top_p | 都不发送 → 服务端默认（回复里有 reasoning tokens，说明思考模式默认开启） | 都不发送 | 相同 |
| SDK 重试 | 0（构建客户端时写死） | 0（请求头 `x-stainless-retry-count: 0`） | 相同 |
| 应用层重试 | `.env` `COMQUTOR_WEEK2_LLM_MAX_RETRIES=1`；方向任务在配置大于 0 时提到 2 | **0** | **不同** |
| 任务路由 | 一个网关、一个共享客户端，按任务名分派（仅在设了分任务 max_tokens 时才有独立客户端） | 每个任务一个网关、一个客户端，同类同工厂 | **不同**（为了分任务超时） |
| 语义缓存 | 每个 run 一个进程内精确缓存（`InMemoryLLMResponseCache`） | 无缓存 | **不同**，但本次 40 条输入各不相同，守卫限制每个输入只发一次，不会出现命中 |
| 服务端前缀缓存 | DeepSeek 自动缓存相同前缀，usage 里的 `prompt_cache_hit_tokens` 可见；无法关闭 | 同左 | 相同（只影响计费，不影响语义） |
| 审计 | 默认关闭；`COMQUTOR_WEEK2_LLM_ENABLE_REQUEST_AUDIT` 可开启 | **开启**（同一套生产 `AuditingTransport`），另加发送守卫和检查点 | **不同**（只增加记录，不改变请求） |
| 代码身份 | 当时的 run 没有工作区快照 | HEAD `7a9aefa` + 完整工作区差异 sha `ed8ea188…` + 未跟踪运行时源码 sha + 驱动 sha（冻结在计划中，执行前重新核对）；快照见 `code_snapshot_partB/` | — |
| 输入哈希 | 不冻结 | 40 个 Alpha 输入和 17 个内容核验输入逐一冻结；方向只允许样本内的 claim 和 taxonomy 中的 Alpha | — |

## 分任务

| 项目 | Alpha（`alpha_classifier`） | 内容核验（`content_support_verification`） | 方向（`evidence_stance_classifier`） |
|---|---|---|---|
| prompt | week2.alpha_classifier.v7，身份 `ac48723f…` | content_support.llm.v2.1，身份 `6abae47b…` | evidence_stance.llm_classifier.v3，身份 `d9455fd5…` |
| 路径 | 单条（产品默认，相同） | 产品为 5 条一批；**本次单条**（不同：5 条一批时 4 批中 3 批超过 6 万字符上限，会在本地被拒） | 10 项一批（生产常量，相同） |
| 客户端超时 | 产品 45 s；本次 45 s（请求头 `x-stainless-read-timeout: 45.0`） | 产品 45 s；**本次 120 s，候选值**（不同） | 产品 45 s；**本次 120 s，候选值**（不同） |
| 应用层超时（`call_with_timeout`） | 45 s / 45 s | 45 s / **120 s** | 45 s / **120 s** |
| 应用层重试 | 1 / **0** | 1 / **0** | 2 / **0** |
| 并发 | 4 / 4 | 串行 / 串行 | 4 / 4 |
| 请求上限 | 无专门上限（共享预算） / **40** | 共享预算 / **17** | 共享预算 / **13** |
| 是否记入语义账本 | 是 / 是 | **否**（任务不在登记表里）/ 否；由线上审计和检查点记录 | 是 / 是 |

**120 s 的说明：**
- 已保存数据中没有任何一次方向请求在 45 s 以后完成；内容核验在 Phase C 中最长 38 s，但那次的输出上限和请求体都比本次小。
- 120 s 是服务端网关自身允许的上限，**不是由成功耗时数据推出的保证**。
- 超时的请求可能仍被服务端处理并计费；本次记为该条失败，不重试。

## 如果要让产品采用本次配置，需要的变更（本轮未做，等待统一授权）

1. 代码支持按任务设置超时（目前网关只有一个共用超时）。
2. 内容核验批大小可配置或改为 1（目前是 `content_support_llm.BATCH_SIZE = 5`）。
3. `.env` 的 `COMQUTOR_WEEK2_LLM_MAX_RETRIES` 设为 0（方向任务会随之变为 0）。
4. 如果需要内容核验进入语义账本：在 `llm_runtime.contracts.SEMANTIC_TASKS` 中登记该任务（本次执行不依赖它）。

本次结果只代表"冻结的执行配置在这 40 条上的表现"，**不能据此宣称当前产品配置通过**。
