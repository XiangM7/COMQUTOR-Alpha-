# D1 修复附录：适配器输出契约补齐 `cited_source_id`（Round 34）

- **收件人**：John（项目负责人、验收人）。
- **范围**：本附录是 T4 最终交付包（Round 33，`T4_final_round33_20261009.zip`）的补充。Round 33 包保持不变，本附录只新增 D1 的修复材料。
- **身份与授权**：
  - 冻结 prompt 原则上不改。这次修改适配器 prompt，是项目负责人（Xiang Mao）书面授权的例外，只限补齐 `cited_source_id` 输出契约这一处。
  - 修改、测试和本附录由工程侧 AI 编码代理（Claude Code）在项目仓库中完成。
  - 本附录不含 John 的审核或签收记录。
- **日期**：2026-10-09。

## 结论

| 部分 | 状态 |
|---|---|
| **契约修复** | 已完成。适配器 prompt 升为 v2，明确要求返回 `cited_source_id`，并说明可以引用的范围；校验器按段落核对引用范围；v1 原文和身份保留，供历史回放 |
| **离线工程验证** | 通过。走真实生产路径，只在最底层 HTTP 用固定回复，外部请求 0 次。见第 3 节 |
| **真实模型验证** | **尚未进行**。固定回复只能证明代码怎样处理各种回复，不能证明真实模型会按 v2 作答。本轮没有发送任何真实请求 |
| **历史结果** | 没有改写。两次 Fresh 的请求、回复和结果，以及 Round 33 的 ZIP，前后哈希一致（第 6 节） |
| **另外的问题** | 适配器超时（第二次 Fresh 9 批中 7 批）和输入超限（1 批）与 D1 无关，本轮没有处理 |

## 1. 改了什么

**prompt 与版本**（全文见 `02_code/prompt_versions.json`）：

| 项 | 旧 | 新 |
|---|---|---|
| prompt 版本 | `week2.claim_batch_enrichment.v1` | `week2.claim_batch_enrichment.v2` |
| prompt 身份 sha256 | `c6822099e2171c6fbad72c36bf2881bcd59bd4d4ad2fc20e10ab62af50b5bfd9` | `fc01ae0d261f63bf081610a22c99486186d10677d94ddbabb21f2fa602d4f628` |
| 输入 schema | `week2.claim_batch_enrichment.input.v1` | `week2.claim_batch_enrichment.input.v2`：每个候选来源多一个 `segment_ids` |
| 输出 schema | `week2.claim_batch_enrichment.output.v1` | `week2.claim_batch_enrichment.output.v2`：每条 9 个字段，含 `cited_source_id` |

v2 的指令相对 v1 只有两处改动，v1 的其余 4 句逐字保留：
- 必填字段那一句加入 `cited_source_id`；
- 新增一段引用规则：
  - 值只能是 `candidate_sources` 中某个 `fragment_id`，或 null；
  - 只能引用 `segment_ids` 列出了本段的候选，而且只有当该摘录确实是本段 claim 或 evidence 的来源时才引用；
  - 没有候选或无法确定时填 null；
  - 不得引用给其他段落的候选，不得引用未提供的 ID，不得写 URL、来源名或新 ID。

原 prompt 没有示例，这次也没有增加。

**代码**（最小 diff 见 `02_code/round34_d1_changes.diff`，文件清单和前后 sha256 见 `02_code/changed_files.json`）：

| 文件 | 改动 |
|---|---|
| `comqutor_alpha/structure_engine/week2_llm.py` | v2 指令与版本号；v1 原文移入 `_RETIRED_TASK_PROMPTS`；新增 `retired_prompt_identity_sha256`，能重算出 v1 的身份 `c6822099…` |
| `comqutor_alpha/structure_engine/structured_output_adapter.py` | 候选来源改为按段落计算，请求中每个候选写明 `segment_ids`。校验器按段落核对：引用了给其他段的候选、未提供的真实 ID 或虚构 ID，整批拒绝。原来这些情况会被静默置空，与合法的 null 无法区分。其余校验不变 |
| `comqutor_alpha/replay/source_bundle.py` | 回放身份登记表中，适配器同时接受 v1（原样保留）和 v2 |
| `docs/specs/week2_semantic_runtime_integration_contract_v1.md` | 版本表中适配器一行改为 v2，注明 v1 保留供回放 |
| `tests/test_t1_source_linking_pipeline.py` | 一个测试原本让模拟回复给每段都引用同一个 ID，按新规则这属于串位。改为只在请求声明了该候选的段上引用；另外两个“拒绝”测试的断言不变，只更新注释 |
| `tests/test_t4_round34_d1_adapter_citation_contract.py` | 新增，见第 3 节 |

**没有改**：
- 模型；
- Alpha 分类、内容核验、方向判断的 prompt；
- taxonomy、Gold、评分阈值、核验标准、PD-006；
- 超时、批大小、重试、预算；
- 数据库和前端。

**对输入大小的影响**（60,000 字符上限）：v2 在每个候选来源中增加 `segment_ids`，每个段 ID 约 70–90 个字符。按第二次 Fresh 的输入重建：
- 没有候选的 4 批大小不变；
- 有候选的 5 批各增加 1,778–2,802 字符（seq 3：49,441 → 52,243；seq 8：47,807 → 49,585）。
- 没有任何一批因此改变“是否超限”：seq 7 原本就超限（61,127 → 62,985），其余都仍在上限以内。
- 不过离上限的余量变小了，这与独立的输入超限问题相关。
- 明细见 `01_before_after/after.json` 的 `batch_sizes`。

## 2. 修复前与修复后：第二次 Fresh 的两份真实回复

两份回复是 attempt 8（30 条，按时返回）和 attempt 2（64 条，超时后才到达），原样使用，回复体 sha256 未变。

| | 修复前（代码 `6cdd51e3…`） | 修复后（最终代码） |
|---|---|---|
| 请求中的 prompt | v1，与当时发出的请求逐字节相同 | v2，因此与当时的请求不同 |
| 结果 | 两份都被拒：`enrichment item fields do not match the strict schema`，回退到确定性抽取 | **仍然被拒**，原因相同 |

修复后仍被拒是正常结果：这两份回复是对 v1 prompt 的回答，本来就没有这个字段。

**补 null 的诊断副本只在 Round 33 中用于定位，不是模型的真实输出**。本轮没有用它证明任何结论。

命令、完整输出和退出码见 `01_before_after/before_log.txt`、`after_log.txt`。两次复现都在网络陷阱下运行，外部请求 0 次。

## 3. 零调用验证（真实生产路径）

**路径**：
- 生产网关构造函数 `build_server_week2_llm_gateway`；
- 真实语义会话；
- 生产入口 `save_structured_agent_outputs`，覆盖分段、`_llm_batch_enrichment`、解析器和校验器、记录构建与来源关联、持久化、紧接着的内容核验请求；
- API 读取函数。

**替换与防护**：只替换最底层 HTTP transport，它按收到的请求给出固定回复。网络防护在任何外部连接尝试时都会让测试失败。

**来源登记**：用生产函数生成，包括：
- 两家媒体刊登同一句话，即一段有两个候选；
- 一个只匹配另一段的来源；
- 一个真实但不匹配任何段的来源。

| # | 验证项 | 结果 |
|---|---|---|
| 1 | transport 收到的请求要求全部必需字段，候选范围正确 | prompt 列出 9 个字段并说明引用规则；账本记录 v2 身份。每个候选都是真实来源，带原文摘录，`segment_ids` 恰好是包含该摘录的段落；不匹配的来源不提供 |
| 2 | 合法候选的完整回复被解析、接受，并在持久化和下游消费中保留正确引用 | 被接受。持久化记录为 `AGENT_CITED`、`VALID`，指向被引用的来源。API 显示相同。紧接着的内容核验请求中，这条 claim 的候选正是被引用的来源 |
| 3 | 合法 null 保持未关联，不升级为已验证支持 | 没有候选的段填 null：`NONE`、未关联、`NOT_APPLICABLE`。有候选的段填 null 时，也不会被记为 `AGENT_CITED`。既有的确定性内容匹配仍照常运行，记为 `CONTENT_MATCH_CANDIDATE`，与模型引用分开，见第 5 节 |
| 4 | 缺字段、虚构 ID、候选范围外 ID 均被拒绝 | 都被整批拒绝，回退到确定性抽取。覆盖 5 种情况：<br>• 缺字段，即 v1 的 8 字段回复；<br>• 虚构 ID；<br>• 真实但未提供的 ID；<br>• 给其他段的候选的 fragment_id；<br>• 给其他段的候选的 source_id |
| 5 | 原有非法 direction 等错误仍被拒绝 | 非法 direction、改写 claim、漏段、confidence 超出范围，都被拒绝 |
| 6 | 多条 claim 不串位；多个候选时不替模型选择 | 两段各自引用自己的候选，都正确落位；引用别段候选被拒。模型在两个候选中选了第二个时，结果保留第二个，代码不会改选第一个 |
| 7 | 来源关联成功不等于内容支持通过，不能抬高评分 | 被引用的 claim 内容支持仍是 `PENDING_REVIEW`；`compute_verified_support_eligibility` 判为不合格；`filter_verified_qualifying_claims` 不保留它 |
| 8 | 外部请求为 0；失败不会变成有效 NONE 或成功富集 | 网络防护 0 次；测试组的网络陷阱插件统计 0 次。每个拒绝情形都记为 `rejected` / `WEEK2_LLM_VALIDATION_FAILED`、`fallback_used`，没有 `validated_output`，记录全部来自确定性抽取，没有任何 `AGENT_CITED` 或 SUPPORTS |

**还有两项验证**：
- v1 原文能重算出 `c6822099…`，回放登记表同时列出 v1 和 v2；
- 第二次 Fresh 的两份真实回复在最终代码上仍被拒。

**本节的证明范围**：固定回复只证明了契约和代码处理。真实模型会不会按 v2 返回 `cited_source_id`、引用是否恰当，没有验证。

## 4. 测试结果（`03_tests/`）

测试组在代码冻结后运行，前后都记录了代码身份。

| 组 | 内容 | 结果 |
|---|---|---|
| d1 | 新测试（15 项），以及适配器、来源引用传递、Gateway 与版本身份、回放登记、语义运行时、实际消费路径的相关测试，共 19 个测试文件加 `tests/replay`、`tests/llm_runtime` 两个目录 | **482 passed，1 skipped，0 failed**，退出码 0，耗时 15 分 18 秒。跳过的 1 项需要手动开启才会发真实请求。网络陷阱拦截 0 次；运行前后代码身份相同（tracked `0070cdf4…`，untracked `10ee7518…`） |
| pin | `tests/structured_output_shadow/test_source_integrity.py`（冻结文件哈希钉） | 修复前、修复后都是 1 failed、3 passed，失败的是同一项 `test_current_semantic_components_match_approved_phase1_master_baseline`。它在本轮之前就因三个文件的既有哈希漂移而失败，本轮没有重新钉 |

**没有运行的部分**：
- 没有跑全项目回归；
- 没有改数据库和前端，所以没有重复 PG 组和录屏。

## 5. 限制和尚未验证的部分

1. **真实模型效果未验证**：
   - 不知道真实模型按 v2 作答的比例，也不知道引用是否恰当。
   - 不知道适配器富集被采用后，对 Alpha 分类输入和结果有什么影响。
2. **既有的确定性内容匹配没有改**：模型填 null 或富集被拒时，确定性匹配仍会按文本把 claim 关联到来源，记为 `CONTENT_MATCH_CANDIDATE`。同一句话出现在多个来源时，它取登记中的第一个。这是本轮之前就有的行为，不在 D1 范围内。
3. **回放绑定按当前版本核对**：语义绑定一步按当前版本（v2）核对适配器记录，与 Alpha 分类 v6/v7 的既有做法相同。回放身份登记表保留 v1。
4. **既有失败没有处理**：冻结文件哈希钉测试在本轮之前就已失败，原因是三个文件既有的哈希漂移。本轮的改动没有改变它的状态，也没有重新钉。
5. **正在运行的查看实例没有重启**：8005 是在本轮修复之前启动的，内存中仍是修复前的代码。它只读展示已保存的 run，不发起富集请求。按要求本轮没有重启服务。
6. **适配器超时和输入超限**是独立的问题，本轮没有处理。
7. **Round 33 包的仓库命令以旧代码为前提**：Round 33 包中需要仓库环境的命令，前提是 Round 32 的代码身份（tracked `6cdd51e3…`）。本轮修复后，代码身份变为 tracked `0070cdf4…`。在新代码上重跑那些命令时，适配器请求会按 v2 构造，结果与 Round 33 包中的记录不同，这是预期的。Round 33 包本身没有改动。

## 6. 历史结果和旧件未变（`05_hash_proof/`）

本轮开始前和结束时各做一次哈希快照，范围包括：
- 两次 Fresh 的 run 目录，含请求和回复审计；
- Round 25–33 的材料，含 Round 33 的交付包和 ZIP；
- Round 32 两个实例的输出目录；
- 历史 run 和 T3 执行。

**结果**：2295 个受保护文件全部不变，变化 0、缺失 0、新增 0。代码身份中只有 tracked diff 变化，即本轮修复本身。本轮没有向任何服务发送请求。

说明见 `05_hash_proof/README.md`。

## 7. 如果需要真实验证（只列出，本轮不执行）

| 项 | 内容 |
|---|---|
| 目的 | 只看适配器契约：真实模型按 v2 作答时，是否返回 9 个字段、引用是否在本段候选内、被接受的比例。不验证下游 Alpha 分类 |
| 输入 | 第二次 Fresh 已保存的适配器输入，用最终代码按 v2 重建请求。不重跑研究 Agent，不取数，不调用其他任务 |
| 批次 | 9 批中能发送的 8 批（seq 0–6、seq 8）。seq 7 输入超限，不会发送 |
| 请求上限 | 8 个 HTTP 请求，0 次重试，沿用现有 45 秒超时和模型 |
| 已知限制 | 第二次 Fresh 中有 7 批超时。不调整超时的话，真实验证很可能又只拿到少数回复 |

这一步需要单独授权，本轮没有发送任何请求。
