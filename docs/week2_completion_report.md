# Week 2 Completion Report

审查日期：2026-07-13

## 原始要求

Week 2 将 validated structured claims 映射到 MVP-10 Alpha，并提取 claim-level cause-effect structure。正式路径要求 keyword/factor candidates、受约束 LLM classification、deterministic fallback、top-3、证据追踪，以及 causal/supportive/conflicting edges。

## 完成情况

### Structured output

- fundamental、news、sentiment、technical outputs 均可生成 validated records。
- 长 Markdown 可拆为多个 claim；标题、表格、代码块和 disclaimer 被过滤。
- `claim_id` 与 `source_agent_output_id` 分离。
- LLM strict-JSON 路径默认关闭，可由服务端启用；invalid JSON、invalid field、timeout 和 retry exhaustion 均回退到 deterministic splitter。

### Alpha Mapper

- 输入使用 claim、evidence、factors 和 taxonomy keyword index。
- 初始 match threshold 与 Development Plan 对齐为 `0.35`。
- `matched_alpha` 是 primary match；`top_candidates` 是最多三个排序候选；`candidate_scores` 作为最多五项的 v1 兼容诊断字段保留。
- candidate score 保存 keyword、factor、direction、semantic components，以及 matched keywords/factors。
- deterministic logic 决定 admissibility。LLM 只能在最多三个 admissible candidates 中 select 或 defer，不能创建 Alpha、恢复非法候选或改写 deterministic no-match。
- MVP taxonomy 保持 10 个 Alpha。

### Structure Extractor

- LLM strict-JSON path 可启用，deterministic rules 负责 evidence validation 和 fallback。
- 支持 causal、supportive、conflicting、active、passive、conditional 和 negated relations。
- vague coexistence 不生成 causal edge；`no evidence that ... drives ...` 不生成 asserted edge。
- edge 保留 claim ID、raw output ID、evidence、method 和 confidence。
- 同一 raw output 内不同 claim 的相同关系不会因共享 raw ID 被去重。
- 输出仍是 claim-level structures，不是 Week 3 Structure Graph。

## LLM 与 deterministic 职责

LLM 负责有限范围的 JSON extraction、admissible candidate selection 和 relation proposal。Deterministic code负责字段验证、taxonomy/factor 约束、evidence 校验、candidate admissibility、fallback 和 artifact contract。

真实 gateway 复用 `tradingagents.llm_clients.create_llm_client()`。它只在服务端显式启用后初始化，并设置 timeout、有限 retry 和每-run 调用预算。普通测试不会初始化 provider。

## Artifact pipeline

Research orchestration 当前依次生成：

1. `raw_agent_outputs.json`
2. `structured_agent_outputs.json`
3. `alpha_matches.json`
4. `extracted_structures.json`

单个 Week 2 stage 失败时，已成功 artifacts 保留，其他可执行 stage 继续。API 不返回本地路径、traceback、raw exception、prompt 或 provider response。

## Schema versions

- `week1a.raw_agent_outputs.v1`
- `week1a.structured_agent_outputs.v2`
- `week2.alpha_matches.v2`
- `week2.extracted_structures.v2`

v2 是 additive/versioned contract。旧 structured v1 artifacts 仍可作为 Mapper 和 Extractor 输入。

## 评估

- 验收 HEAD：`652a6281495f852b8a25487db7b509eade4f812e`。
- 完整离线 suite：`658 passed, 1 skipped, 2 deselected`。
- FastAPI/API：`19 passed`。
- Week 1→2 end-to-end：`16 passed`。
- Week 2 LLM offline：`12 passed, 1 deselected`。
- Clean 20-case gate：`20/20`，`100%`。
- Clean labels 中八类代表性验收 claims：`8/8`。正式 clean gate 仍以完整 20 条为准。
- NVDA 修改前：strict `18/30`，allowed `20/30`。
- NVDA 当前：strict `23/30`，allowed `29/30`。

NVDA 结果是 robustness diagnostic，不是市场预测准确率，也未用于修改人工标签、降低 gate 或添加 case-specific branch。

## Persistence boundary

当前实现是 file-backed MVP。run_id、原始输出、structured claims、matches 和 extracted structures 均通过 allowlisted storage boundary 写入。Development Plan 中的 `alpha_matches` 和 `structure_graphs` 数据库表仍然推迟，不能视为已完成。

## 明确推迟

以下内容不属于本次 Week 2 completion：graph builder、NetworkX run graph、graph coherence、activation score、dominant alphas、graph endpoint、正式 conflict detector、exposure engine、Alpha Memory、outcome feedback、portfolio construction 和 dashboard。

## 当前风险

1. Provider SDK 已安装，但没有 provider/model/credential 配置，因此真实 smoke test 尚未执行。
2. deterministic NLP 对复杂嵌套语义仍有覆盖边界。
3. file-backed artifacts 适合 MVP 验收，但不替代并发、迁移和查询能力完整的数据库层。
4. Ruff check 有 `33` 项，Ruff format check 有 `109` 个文件需要格式化。
