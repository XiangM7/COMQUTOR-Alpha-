# 01 四步模型配置对照（历史评估 / 各真实运行 / 拟冻结）

数据源是 `01_config_comparison.json`，由 `tools/build_config_comparison.py` 从各 run 自己的 `llm_semantic_calls.jsonl` 逐条重新统计，只读。下面三类配置分列，不合并：

- **历史评估配置**：历史分数当时是在什么配置下测出来的。
- **真实运行实际配置**：保存的请求里实际发了什么。
- **拟冻结配置**：提案，详见 `06_execution_proposal.md`。

写法约定：
- 请求里没有带的参数写"未发送 → 服务端默认"。
- 从保存记录无法核实的写"未知"。
- 分数只归属于产生它的配置：v6 的成绩不算到 v7 头上，Anthropic 的成绩不算到 DeepSeek 头上。

## 共同设置（当前部署）

| 项目 | 当前值 |
|---|---|
| 模型 | deepseek / deepseek-v4-flash（`.env`） |
| 超时 | `.env` 中 45 s，所有任务共用一个值；服务端网关限定在 1–120 s |
| 应用层重试 | `.env` 中为 1；方向任务只要配置大于 0 就提到 2；显式 0 会被遵守 |
| SDK 重试 | 0（构建客户端时硬编码） |
| 未发送参数 | temperature、top_p、thinking、reasoning_effort、response_format、stop → 服务端默认；回复中有 reasoning tokens，说明思考模式默认开启 |
| 代码身份 | 当前：HEAD `7a9aefa` + `code_snapshot/`（已跟踪文件的完整差异 + 未跟踪源码副本 + 哈希）。历史 run（034a0a60、1bad76a7、c904d4cc、recovery）的代码身份**未知**，执行时没有做工作区快照；但它们每次调用都记录了 prompt 身份，与现在相同 |

## Step 1：Structured Adapter（`claim_batch_enrichment` v1，身份 `c6822099e217…`）

| 配置类别 | 内容 |
|---|---|
| 历史评估 | **没有找到**任何针对此任务的评估 |
| 真实运行：034a0a60 NVDA 10-02 | 8 次调用；max_tokens 未发送；5 次超时、3 次成功；补全 p50 14,713、最大 15,604 tokens |
| 真实运行：1bad76a7 AMD 10-05 | 4 次；未发送；2 次超时、2 次成功；补全最大 12,922 |
| 真实运行：c904d4cc AMD 10-06 | 7 次；未发送；4 次超时（45 s）、3 次成功 |
| 拟冻结 | **T3 联合批次不执行此任务**：五环直接读取已保存的 claim，没有请求，不需要冻结 |

## Step 2：Alpha Classifier（`alpha_classifier`）

| 配置类别 | 内容 |
|---|---|
| 历史评估：Candidate-3（82.67%） | Anthropic claude-sonnet-4-6；prompt 版本标签未知，只记录了分类器哈希 `d53b2d75…`；单条；max_tokens 未知；重试 0。**不适用于当前配置**：Provider、模型都不同 |
| 历史评估：v6 诊断 t3live_20261001T014648Z（40 条） | deepseek-v4-flash；v6（身份 `bb2dbdf0…`）；配置了 200，但字段序列化成 `max_completion_tokens`，平均输出约 881，可见 200 没有生效，服务端怎么处理的未知。**分数留作 v6 的历史结果**，不算给 v7 |
| 历史评估：v7 开发验证（19 条） | deepseek-v4-flash；v7（身份 `ac48723f…`）；200 / 2,048 / 4,096 三种上限混用，2,048 下 3 次截断；只和 ChatGPT AI_REVIEW 对比过。**不是合格的人工参考评估** |
| 真实运行：034a0a60 NVDA 10-02 | v7，身份与现在相同；430 次发送且带 `max_tokens=4096`；370 次 budget_exhausted 未发送；补全最大 1,451；p95 耗时 3.5 s |
| 真实运行：1bad76a7 AMD 10-05 | v7；max_tokens 未发送；441 次成功、92 次 budget_exhausted、1 次 45 s 超时；补全 p95 2,565、最大 7,979 |
| 真实运行：recovery-20261007T053635Z（c904d4cc 的冻结输入） | v7；未发送；954 次成功、1 次超时、18 次 not_called；补全 p95 2,352、最大 8,566 |
| 拟冻结 | deepseek-v4-flash；v7；单条；max_tokens 未发送（D2，备选 4,096）；45 s；重试 0/0；并发 4；无缓存；新请求 7 个，另有 33 条重放已保存的生产答案（D1） |

**v7 目前没有合格的人工参考评估。** v6 的诊断成绩属于 v6。v7 只做过开发验证，对照的是 AI 意见。2026-10-05 导入的标签身份未记录（见 02）。本轮不追加 H2 规模的重测；之前 40 条的方向结果只作为定向诊断报告。

## Step 3：Polarity / Evidence Stance（`evidence_stance_classifier` v3，身份 `d9455fd5ff33…`）

| 配置类别 | 内容 |
|---|---|
| 历史评估：H2（87.23%） | Anthropic claude-sonnet-4-6；版本字符串同为 v3；按批（141 条分 15 批）；max_tokens 未知。**不适用于当前配置**：Provider、模型都不同，**不算给 DeepSeek** |
| 真实运行：034a0a60、1bad76a7 | 14 次和 12 次全部 budget_exhausted，**从未发出** |
| 真实运行：direction-20261007T065826Z（第 17 轮） | 1 次，45 s 超时 |
| 真实运行：8 月 27 日至 9 月 21 日的 27 个 run（同一 prompt 哈希） | 可判定的 24 个 run 单次超时都是 20 s 或 45 s，另 3 个无法判定；45 s 下首次尝试成功率 9 月 9 日前为 0–7%，9 月 10 日至 21 日为 51–79%（详见 `06_proposal/stance_timeout_evidence.json`） |
| 拟冻结 | deepseek-v4-flash；v3；10 项一批；max_tokens 未发送；**120 s（D3）**；重试 0/0；并发 4；无缓存；上限 5 个请求 |

## Step 4：Structure Extractor（`structure_extractor` v1，身份 `326622a1786b…`）

| 配置类别 | 内容 |
|---|---|
| 历史评估 | **没有找到** |
| 真实运行 | 034a0a60 的 16 次和 1bad76a7 的 3 次都是 budget_exhausted；c904d4cc 3 次成功（补全最大 941） |
| 拟冻结 | **不属于五环，T3 联合批次不执行**，没有请求 |

## 附：联合检查第 1 环用到的内容核查（`content_support_verification` v2.1，身份 `6abae47b6a6a…`）

不在 John 列的四步之内，但"来源→claim"这一环由这个生产任务判断。

| 配置类别 | 内容 |
|---|---|
| 历史评估 | 没有准确率评估。Phase C（10-05）在 21 条 AMD claim 上发了 27 个请求，`max_tokens=8192`，其中 6 次触顶截断；耗时 p50 29 s、最长 38 s |
| 真实运行：c904d4cc | 只有错误日志：259 次 CACHE_READ_FAILED、42 次 45 s 超时、7 次 INPUT_TOO_LARGE、1 次校验失败。152 条已保存结论有 claim、来源和内容哈希，但**没有模型、prompt、原始回复**。原因是此任务**不在调用账本的任务登记表里**（`llm_runtime.contracts.SEMANTIC_TASKS`），会话无法为它开 trace（本轮发现） |
| 拟冻结 | deepseek-v4-flash；v2.1；**单条（D4）**；max_tokens 未发送（D5）；**120 s（D6）**；重试 0/0；串行；无缓存；17 个请求 |
