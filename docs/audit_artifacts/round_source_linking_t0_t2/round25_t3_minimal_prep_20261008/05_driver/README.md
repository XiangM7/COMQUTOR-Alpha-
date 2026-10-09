# 05 五环驱动：必要改动与零调用测试结果

## 改动范围

| 文件 | 本轮改动 |
|---|---|
| `docs/audit_artifacts/round_source_linking_t0_t2/t3_joint_sample_driver.py` | **新增**：针对冻结的 40 条样本做五环联合检查 |
| `docs/audit_artifacts/round_source_linking_t0_t2/t3_joint_verification_driver.py` | **最小修复两处**，见 `t3_joint_verification_driver.round25.diff`：① 读取真实 run 保存的 `records` 键（原来只认测试夹具用的 `claims`，真实 run 读出来是 0 条）；② 方向阶段原来把确定性基线的结果写进 `status`，现在改为 `DETERMINISTIC_BASELINE_ONLY`，基线值放到单独标注的字段里，不再冒充方向结果 |
| `tests/test_t3_joint_sample_driver.py` | **新增** 14 个零调用测试 |
| `round25…/tools/select_joint_sample.py` | 表单加入作答词表和说明指针；run 内链接状态（系统输出）从表单移到清单；工作表加 `reviewed_at`。重跑后选中的 40 条与之前逐条相同 |

**生产代码（`comqutor_alpha/`）本轮未改。** 文件哈希见 `driver_files.json`，副本在 `driver_copies/`，冻结身份在 `freeze_identity.json`（HEAD、工作区差异哈希、代码快照、prompt 身份、样本与表单哈希）。

## 五环怎么接，每环结果从哪来

| 环 | 系统答案来自（生产函数） | 结果状态（分开记录，不合并） |
|---|---|---|
| L1 来源 → claim | `content_support_llm` 的请求构造器和批处理函数，就是 `apply_llm_content_support_verification` 内部调用的那两个。请求项在**整条 run** 上构造后再限定到样本，所以 `report_context` 与真实运行相同 | `LLM_RESULT`、`TASK_FAILED`（附原因）、`NOT_SUBMITTED`（生产规则不送，例如链接不是 VALID）、`DETERMINISTIC_VERIFIER_RESULT`（生产的确定性数据核验，单独标注）、`NOT_JUDGEABLE_NO_SOURCE_CONTENT`（部分链） |
| L2 Alpha | `alpha_mapper.map_structured_records`，单条路径 | `MATCHED`、`NONE`（模型自己给出 none）、`SELECTED_BUT_NOT_MATCHED`（模型选了，被生产门槛否决）、`ABSTAINED_AMBIGUOUS`、`CALL_FAILED` / `PARSE_FAILED` / `TRUNCATED` / `UNAVAILABLE`（任务失败）。另记答案来源：`REUSED_SAVED_PRODUCTION_ANSWER`（附 run、call_id、输入哈希）或 `NEW_REQUEST`（附不能复用的原因） |
| L3 方向 | `evidence_stance_llm.apply_llm_stance_upgrade`，即生产 LLM 路径，10 项一批，运行顺序与 `build_alpha_matches_payload` 相同 | `LLM_RESULT`、`TASK_FAILED`（生产回退到确定性基线时的结果，基线值只放在 `deterministic_baseline_not_a_result` 里，**不作为方向结果**）、`NOT_APPLICABLE`（L2 没有匹配的 Alpha） |
| L4 证据池资格（单条 claim） | `evidence_fact_index.select_supporting_alpha_claims`（激活和冲突共用的支持性证据筛选）加上 `source_provenance.compute_verified_support_eligibility`（已验证支持门） | 激活池资格 = 两项都通过；冲突一侧还要求 L3 为 `supports_alpha`，L3 不是 LLM 结果时记为"未定"。不一致的原因分成机械性（链接、时间、绑定）和语义或复核两类。**不涉及** run 级的等级或冲突是否成立 |

**复用已保存的 Alpha 答案（D1）。**
- 条件是请求逐项相同：同一 prompt 身份、同一输入哈希、同一模型，首次尝试即成功、`finish_reason=stop`、校验通过。
- 保存的账本只留了校验后的回复对象（没有原文）。Alpha 的回复格式恰好就是这个对象，所以重放后得到的答案与当时被接受的答案相同。
- 重放走生产网关，校验、门槛、账本都照常执行；只有模型这一层换成"按输入哈希回放已存答案"，账本模式记为 `replay_fixture`，不会被当成真实调用。
- 33 条的最终 Alpha 与原 run 保存的结果逐条一致。

**之前存过的内容核查结论不复用。** L1 运行之前，样本记录上已有的 LLM 内容核查结论和失败原因会被移除：5 条结论、7 条失败，来源都是 c904d4cc 之前跑过的那一轮。这样 L1 和 L4 都看不到它们。

**计分（零调用）。** 只有填了 `reviewer_id` 的判断才算参考判断；没填的只计数，不计分；超出词表的值单独报告，不强行归类。每一环用自己的分母：
- **L2**：沿用现有计分器，报准确率、非 NONE 精确率与召回率、混淆矩阵、类别计数、结果码计数和任务失败。
- **L1**：只在完整链上比较一致率，另报忠实性分布。
- **L3**：只在系统和复核人选了同一个 Alpha 时比较。
- **L4**：同样只在两边 Alpha 相同时比较，不一致附上失败的条件。

表单里的 claim 文本与预测不一致时拒绝计分。

**真实执行入口受锁。** `predict` 只接受同时满足以下条件的计划文件，否则在构建任何网关之前就拒绝：
- sha256 与命令行给出的一致；
- `authorized=true`，且写明授权人；
- 样本清单哈希和三个 prompt 身份与冻结时相同。

本轮从未执行 `predict`。

## 零调用测试结果

最终命令、日志、退出码、JUnit、网络陷阱报告都在 `test_evidence/`（命令见 `command_final.txt`）。

- 受影响的三个测试文件：`tests/test_t3_joint_sample_driver.py`、`tests/test_t3_joint_verification_driver.py`、`tests/test_t3_diagnostic_evaluation_driver.py`。
- **65 passed，退出码 0；外网尝试 0 次，回环连接 0 次。**
- 所有测试都用真实的 `Week2LLMGateway`（重试循环、调用预算、校验），只把 Provider 边界上的模型换成假模型。
- `ruff check` 覆盖本轮新增或修改的 Python 文件，全部通过。旧驱动第 132 行有一处不是本轮引入的 import 排序提示，按最小改动原则没有动。

新增的 14 个测试分别证明：

1. 四环分开记录；内容核查 17、Alpha 7 个请求与零调用计算完全一致，方向请求不超过上限；两层重试为 0 时，网关预留数等于模型实际收到的请求数；内容核查的逐请求记录保存下来 17 条；保存的 run 文件哈希不变（只读）。
2. 按生产默认 5 条一批，本样本 4 批中有 3 批会在本地被拒，模型只收到 1 次请求；单条发送时 0 批超限。
3. 33 条已保存答案原样重放，不依赖实时模型（实时 Alpha 模型故意设成总是失败）；只有 7 条发出新请求；重放账本只有 `replay_fixture` 模式。
4. 方向失败时记为任务失败，不出现方向值，确定性基线只出现在它自己的标注字段里，冲突侧资格为"未定"。
5. 方向请求上限设为 1 时，恰好只发 1 次，其余记为预算耗尽导致的任务失败。
6. 模型给出 NONE 与 Alpha 调用失败分开记录；NONE 时不发任何方向请求。
7. 之前存过的 LLM 内容核查结论不复用：新核查失败时，已验证支持门给出 `NOT_REVIEWED`。
8. 表单中没有任何系统答案或系统标识，claim 文本与清单一致，判断栏全部为空。
9. 没有复核人身份的判断不计分。
10. 每环有自己的分母（构造 5 条用例，逐环核对计数）。
11. 词表外的值单独报告，不强行归类。
12. 表单与预测不一致时拒绝计分。
13. `predict` 遇到哈希不符、未授权、匿名授权、prompt 漂移、样本漂移时都拒绝，而且没有构建任何网关。
14. 旧驱动能读 `records` 键，方向阶段标注为基线。

## 本轮发现、未在本轮修的生产问题（范围外，只报告）

1. **内容核查任务不进调用账本。** `content_support_verification` 不在 `comqutor_alpha/llm_runtime/contracts.py` 的 `SEMANTIC_TASKS` 里。只要挂了语义会话，开 trace 就会失败（`SEMANTIC_RUNTIME_CALL_START_FAILED`），请求照常发送，但账本里没有记录。这就是 c904d4cc 的 152 条结论查不到模型和 prompt 来源的原因。驱动另存了逐请求记录作为替代。
2. **生产默认 5 条一批会超出网关的 6 万字符输入上限。** 本样本 4 批中有 3 批超限；c904d4cc 当时也记录了 7 次。超限请求在本地被拒，不发出、不计费，但这些 claim 拿不到结论。
3. **旧版本账本的耗时字段不可靠。** 8 月 28 日至 9 月 21 日之间有 10 个 run，账本里大部分或全部记录的 `completed_at` 都是账本收尾时刻，`latency_ms` 量的是"开始到收尾"。第 17 轮报告据此写的"方向成功批次中位 200–400 s、最长 657 s"不成立（见 `06_execution_proposal.md` 第 4 节的更正）。
4. 1bad76a7 当天 10:34 的 fundamentals 快照被 run 自己的时间规则判为 `TIME_INVALID`。这是生产规则的结果，不是缺陷，但会让 8 条样本的 L1 和 L4 在机械层面不合格。
