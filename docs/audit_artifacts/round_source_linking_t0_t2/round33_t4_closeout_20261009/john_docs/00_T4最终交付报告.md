# COMQUTOR Alpha T4 最终交付报告

- **收件人**：John（项目负责人、验收人）。
- **版本**：Round 33（2026-10-09）。在 Round 32 的基础上，本版只收尾三项：
  - D1 的离线定位；
  - 最终查看入口的一致性；
  - 超长输入“6 次拒绝／5 条更正”的对账。
- **Round 32 的已有材料原样保留在 `round32/`**：
  - 两份证据文档改了措辞，改动逐条记在 `round33/records/文档修改记录.json`；
  - 被本报告取代的 3 个文件没有复制，见第 8 节。
- **身份**：
  - 两次 Fresh 都由 Xiang Mao 在网页上亲自点击发起。
  - 本报告和全部工程材料，由工程侧使用的 AI 编码代理（Claude Code）在项目仓库中生成。
  - 本包不含 John 的审核或签收记录。
- **两个代码身份，不混用**：

| 代码 | git HEAD | tracked diff sha256 | untracked sha256 | 提交状态 |
|---|---|---|---|---|
| 两次 Fresh 真实执行时的代码 | `7a9aefa` | `1b53b921…` | `38ef636f…` | 未提交 |
| 最终代码（Round 32 修复后；本版没有再改代码） | `7a9aefa` | `6cdd51e3…` | `10ee7518…` | 未提交。完整 diff、未跟踪源码 tar 和清单在 `round32/02_code/` |

- **边界**：
  - 零新增 Provider、模型、搜索或取数请求，没有第三次 Fresh，没有重跑研究 Agent；
  - 没有修改 prompt、模型、taxonomy、Gold、核验标准、评分阈值或 PD-006；
  - 原始 run 和旧 ZIP 只读；
  - 没有 commit 或 push。

## 1. 本版三项的结果

| 项 | 是否完成 | 结果 | 证据 |
|---|---|---|---|
| D1：适配器校验器要求 `cited_source_id`，冻结 prompt 没有要求 | **定位完成；没有修复，仍是未关闭缺口** | • 这是 T1 来源关联改动留下的接口契约缺口，不是接线或消费错误，也不是模型质量问题。<br>• 第二次 Fresh 中拿到回复体的两批，缺这个字段是唯一的阻断点。<br>• 正确修复需要修改冻结 prompt，超出本版边界。见第 2 节 | `round33/01_d1/` |
| 最终查看入口一致 | **完成** | • 入口是前端 5179 加 API 8005，即 Round 32 的最终隔离实例在原端口重启，运行最终代码。<br>• 阶段披露、历史重开、Export 都核对通过。<br>• 5177 加 8002 是新旧混搭，不作为最终入口。<br>• 最终视频继续有效，没有重录。见第 3 节 | `round33/02_viewer/` |
| “6 次拒绝／5 条更正”对账 | **完成** | • 6 次本地拒绝对应 6 条账本记录：其中 5 条是内容核验，各对应 1 条 claim 结果，就是那 5 条更正；第 6 条是适配器的一批，原记录就是正确的。<br>• 更正没有遗漏。<br>• Round 31 主报告有一句摘要写错了。见第 4 节 | `round33/03_not_sent_reconcile/` |

本版没有修改生产代码，所以没有新的 diff，也没有重跑生产测试。最终代码上的测试结果沿用 Round 32（第 6 节）。

## 2. D1 离线定位（`round33/01_d1/D1_离线定位.md`）

**字段要求和依据**：
- 字段要求在 `structured_output_adapter._LLM_BATCH_ENRICHMENT_REQUIRED_FIELDS` 和 `_validate_llm_batch_enrichment`：每条回复的字段集合必须恰好是 9 个字段，其中包括可以为 null 的 `cited_source_id`。
- 依据是 John 任务单 T1 第 B 条：“结构化输出引用这些已有 ID，后端必须校验”，以及 T1 来源关联改动（2026-09-28）的代码注释。
- 冻结的任务说明 `week2.claim_batch_enrichment.v1` 只要求 8 个字段，没有提到 `candidate_sources` 或 `cited_source_id`。
- T1 新增必填字段之后，prompt 和输出 schema 的版本都没有变。
- 提交基线 HEAD 中，校验器只要求 8 个字段，与 prompt 一致。
- 消费侧能正确处理 null：null 时依次退回原文标记、内容匹配、数字归一匹配。

**第二次 Fresh 的 9 批分开记录**：
- 7 次超时（attempt 1–7），run 中都没有解析到回复，**与缺字段无关**；
  - 其中 attempt 2 的 200 回复在发出后 46 s 才到达，客户端已记为超时；
- 1 次未发送：输入 61,127 字符，超过 60,000 上限；
- 1 次有回复后校验失败：attempt 8，30 段。

**用原生产路径离线复现**：
- 使用：
  - 生产网关；
  - 真实语义会话；
  - 未改动的 `_llm_batch_enrichment`。
- 底层 HTTP 用保存的回复体作答；网络陷阱拦截外部调用 0 次。
- 重建的请求与当时发出的正文逐字节相同。
- 校验器报 `enrichment item fields do not match the strict schema`，富集被拒，回退到确定性抽取，与 run 中的结果一致。
- **诊断对照**：每条只补 `"cited_source_id": null`，按时返回的一批整批通过（30/30），晚到的一批整批通过（64/64）。这个对照不是修复，也不填任何来源 ID。
- **第一次 Fresh（补充）**：5 批有回复，第一失败点都是这个字段。补 null 后 3 批整批通过，另 2 批各有 2 条 `invalid direction`，仍会被整批拒绝。

**能证明和不能证明的**：
- 严格按 prompt 作答的 8 字段回复，一定会被当前校验器拒绝（代码事实）。
- “所有回复必然被拒”不能这样写：模型可能自行加上这个字段；而第一次 Fresh 有 2 批即使补了字段，也会因为其他原因被拒。

**字段来源**：
- 应由模型从本次请求的候选来源中选择，再由后端校验。
- 调用上下文不能代填，原因有两个：
  - 候选按批汇总，不是逐段的事实；
  - 代填等于替模型猜来源。
- 逐条的确定性来源关联已经单独运行，并用各自的方法名记录。

**为什么本版没修**：
- 正确修复是在任务说明中要求返回该字段，并按 ADR-005 为 prompt 和输出 schema 升版本。这需要修改冻结 prompt，本版禁止。
- 把缺字段当作 null 放行，会改变 T1 设定的严格字段要求，模型也仍然不会给出引用。所以这既不是正确修复，也在禁止范围内。

**影响**：
- 第二次 Fresh 中，适配器的模型富集一次都没有被采用。951 条 claim 的 entities、factors、direction、confidence 都来自确定性抽取。
- 9 批中只有 1 批是因为 D1 被拒。另外 7 批超时、1 批输入超限，是另外的问题。
- 离线已证明的只是：缺字段是两份回复唯一的阻断点。修复后富集会被采用多少、对 Alpha 分类有什么影响，只能通过真实调用观察。本版不安排真实执行。

## 3. 最终查看入口（`round33/02_viewer/查看入口核对.md`）

**最终视频**：
- 由 Round 32 用 5179 加 8005 录制。
- 实例 `/ready` 返回最终代码 `6cdd51e3…` / `10ee7518…`，真实执行关闭，库是隔离的 `comqutor_alpha_t4_r32_demo_test`。
- 本版没有改代码，因此视频保留。

**5177 与 8002 是混搭**：
- 8002 返回 Fresh 代码 `1b53b921…` / `38ef636f…`，其第二次 Fresh 的详情响应中没有 `stage_disclosure`。
- 5177 提供的是最终前端，但它连接 8002，所以新面板没有数据。
- 8002 当时没有运行中的研究作业；本版没有重启它，因为不需要。

**最终查看入口**：
- 地址：`http://127.0.0.1:5179`，连接 `http://127.0.0.1:8005`。
- 做法：在原端口重启 Round 32 的最终隔离实例，用的是原启动脚本和原配置。
- 启动命令见 `round33/02_viewer/查看入口核对.md` 第 2 节，需要仓库环境。

**只读核对第二次 Fresh**：
- 非 GET 请求拦截 0 次，没有点击 Start Research，36 个 API 请求都是 GET。

| 检查 | 结果 |
|---|---|
| API 阶段披露 | 与 Round 32 保存的披露相同（副本保存时加的两个说明字段除外） |
| 页面 “Processing completeness” | 逐阶段显示：<br>• 适配器 7 超时、1 未发送、1 回复未被接受；<br>• 内容核验 185 被采用、5 未发送、3 格式不合格、48 引文找不到；<br>• 结构抽取 0 条边 |
| 历史重开 | 从 Recent runs 打开两次，加上一次整页刷新，面板文字三次相同 |
| Export | 下载 ZIP 的 sha256 为 `49bd4650b60a8c9f6bf5b3d57d3baecba196889a1bfb70c1f4329ecd1b79cef3`，与 Round 30、Round 32 相同 |

## 4. “6 次拒绝／5 条更正”对账（`round33/03_not_sent_reconcile/对账.md`）

**发送总账**（第二次 Fresh）：
- 账本 1220 条 = 实际发送 1204 + 同 run 缓存命中 10 + 本地拒绝 6。
- HTTP 尝试 1204 = 网关预算占用 1204 = 线路审计请求 1204。
- 回复 1198 行，差的 6 行是没有回复的超时，与“6 次拒绝”无关。

**6 次本地拒绝逐条**（都没有 attempt_id，都没有发送）：

| task | 对象 | call_sequence | 输入字符 | 保存的原因 | 对应结果记录 | 最终代码 |
|---|---|---|---|---|---|---|
| 适配器 | fundamental_agent 一批 64 段 | 7 | 61,127 | `WEEK2_LLM_INPUT_TOO_LARGE` | 0 条：适配器不在 claim 上记原因 | 原因不变；账本补写实际字符数 |
| 内容核验 | claim `fundamental_agent:fundamentals_report:claim:50` | 88 | 77,234 | `malformed_response` | 1 条 claim | `input_too_large` |
| 内容核验 | claim `fundamental_agent:fundamentals_report:claim:115` | 106 | 62,278 | `malformed_response` | 1 条 claim | `input_too_large` |
| 内容核验 | claim `bull_researcher:investment_debate_state.bull_history:claim:17` | 136 | 64,400 | `malformed_response` | 1 条 claim | `input_too_large` |
| 内容核验 | claim `bear_researcher:investment_debate_state.bear_history:claim:27` | 151 | 71,120 | `malformed_response` | 1 条 claim | `input_too_large` |
| 内容核验 | claim `bear_researcher:investment_debate_state.bear_history:claim:43` | 154 | 75,951 | `malformed_response` | 1 条 claim | `input_too_large` |

**答案：6 次事件对应 6 条账本记录，其中 5 条对应 5 条结果记录，就是那 5 条更正**：
- 5 条 claim 的状态仍是 PENDING_REVIEW，没有被记成有效 NONE、不支持或成功判断。
- 适配器那 1 次的原因一直是正确的，所以没有需要更正的结果记录。更正没有遗漏。
- 内容核验的 `malformed_response` 标签原来共 8 条：5 条未发送，3 条是模型确实返回了不合格的回复。这 3 条在最终代码中仍是 `malformed_response`。

**摘要错误**：
- Round 31 主报告第 1 节写的是“6 个请求输入超限，且被标成 `malformed_response`”。
- 实际是 6 个未发送，其中 5 个被这样标记。
- 其余 11 条报告原句与记录一致，逐条列在对账文件第 4 节。
- 历史 run 和 Round 31 包都没有改。

## 5. John T4 四项要求：逐条关闭表

| John 的要求 | 关闭状态 | 证据 | 验证方式 | 限制 |
|---|---|---|---|---|
| **1. PostgreSQL 验证，不以 SQLite 回退代替**（迁移、来源持久化、重启、历史重开、Export、run_id 与输入一致；Replay 测试根因；两项 ESLint；必需测试不能用 skip 收口） | **关闭** | `round32/03_postgres/`、`round32/04_tests/` | 在最终代码上：<br>• 独立库 `comqutor_alpha_t4_r32_verify_test`，从空库开始；<br>• 派生验证执行经生产生命周期写入；<br>• 实例正常停止后重启，重启前后快照逐项相同；<br>• Export 与 manifest 和目录逐字节一致；<br>• PG 测试组 0 skipped；<br>• Replay mismatch 测试通过；<br>• ESLint 0 问题。<br>本版又在最终查看入口上完成了历史重开和 Export 核对 | 只验证了本机 PostgreSQL 16.15；Replay 修复前的原始失败日志缺失（Round 27 已说明） |
| **2. 调用与费用计量** | **关闭** | `round32/references/T4_delivery_round31_20261009.zip`（`usage_cost/`）、`round32/03_not_sent/not_sent_appendix.json`、`round33/03_not_sent_reconcile/` | 两层、按任务、逐请求对账（Round 31）；输入超限的请求记为未发送（Round 32）；本版逐条对账了“6 次／5 条” | 金额是估算；7 个超时请求没有 usage；价格表是 2026-09-30 查询的 |
| **3. 一次必要的 Fresh 验证** | **关闭**（两次 Fresh 都由 Xiang Mao 在网页上亲自点击；之后没有新的 Fresh） | `round32/05_replay/`、Round 31 包 | 第二次 Fresh 真实执行：completed，951 条 claim。最终代码消费它保存的真实回复，研究结果不变（第 6 节） | 第二次 Fresh 事先没有书面说明目的；只证明了本机的指定 profile |
| **4. 实际 Demo 视频** | **关闭** | `round32/07_demo/recording_final/t4_demo_final.mp4`、`round32/07_demo/视频场景索引.md`、`round33/02_viewer/` | 最终代码只读打开第二次 Fresh，11 个场景；本版确认视频所用实例和代码就是最终版本 | 没有 Start Research 的点击录像（John 没有要求这一项） |

**工程侧结论**：
- T4 四项要求的工程工作已完成，请 John 按任务单验收。这不是 John 的签收。
- D1 不在 T4 四项要求之内，仍是未关闭缺口（第 9 节）。

## 6. Round 32 完成并在本版沿用的内容

### 6.1 两个回归失败（`round32/01_regressions/回归失败分析.md`）

| 代码树 | 结果 |
|---|---|
| HEAD | 2 passed |
| Fresh 代码快照（修复前） | 2 failed |
| 修复前的工作区 | 2 failed |
| 修复后的工作区 | 2 passed |
| 负对照 | 3 个对照全部失败（测试仍然有效） |

**原因与处理**：
- 两项都是测试本身的错误，已按正确预期修复。
- 被测的两个生产文件在修复前后逐字节相同，不涉及冻结哈希。

### 6.2 未发送请求的标签（`round32/03_not_sent/`）

**真实边界**：输入超过 60,000 字符时，网关在预算占用和 HTTP 之前就本地拒绝。

**修复**：
- 内容核验和方向判断把 `WEEK2_LLM_INPUT_TOO_LARGE` 记为 `input_too_large`，不再混进 `malformed_response`；
- 账本写明实际字符数和上限。

**历史记录不改写**：

| run | 未发送 | 其中误标为 `malformed_response` |
|---|---|---|
| 第二次 Fresh | 6（内容核验 5、适配器 1） | 5 |
| 第一次 Fresh | 33 | 31 |

### 6.3 结构抽取与降级披露（`round32/05_stage_disclosure/`）

**结构抽取**：
- 第 1 个回复被既有的“证据支撑”规则拒绝，保留失败；
- 第 2 个回复是合规的空结果；
- 模型结构抽取贡献 0 条边，Structure Graph 的边全部来自 TradingAgents canonical relations。

**新增 `stage_disclosure`**：
- 出现在 API、页面（“Processing completeness”）和 Export（本轮之后完成的 run）；
- completed 的含义没有改。

### 6.4 最终代码上的 PostgreSQL 验证（`round32/03_postgres/`）

| 步骤 | 结果 |
|---|---|
| 1. 空库迁移 | 派生执行前 0 张表 → 7 个迁移、9 张表 |
| 2. 生产持久化 | 写入 research_runs 1、agent_outputs 951 |
| 3. 停止 / 重启 | SIGTERM 正常停止后重启 |
| 4. 历史重开 | 重启前后快照（历史、详情、状态、图、冲突、agent 输出、关键证据追溯、产物）完全相同 |
| 5. API 与 Export | Export 20 个 manifest 文件，与 manifest 和目录逐字节一致；ZIP 含 `stage_disclosure.json`，与 API 相同；重启前后 ZIP 的 sha256 相同 |
| 6. 一致性 | run_id、DB 行、metadata 一致；`based_on_run_id` 指向第二次 Fresh |

**PG 集成测试**：PG 集成测试 65 passed、0 skipped，使用独立测试库。

### 6.5 最终代码上的测试（`round32/04_tests/`）

每组测试前后都记录了代码身份，运行期间代码没有变化。外部网络陷阱的拦截次数都是 0。

| 组 | 结果 | 退出码 |
|---|---|---|
| new：Round 32 测试，以及 Round 27 / 28 的环境、计量、停止测试 | 46 passed | 0 |
| replay：`test_replay_conflict_does_not_get_run_id_mismatch` | 1 passed | 0 |
| pg：11 个 PostgreSQL 集成文件 | 65 passed，0 skipped | 0 |
| affected：受影响面 73 个文件 | 1313 passed，1 skipped，0 failed | 0 |
| frontend | ESLint 退出码 0；typecheck 退出码 0；vitest 4 个文件 102 passed | 0 |

- 跳过的 1 项需要设置变量才会发真实请求，不是必需测试。
- 没有跑全量回归。

### 6.6 修复没有改变研究答案（`round32/05_replay/`）

**派生验证执行**：
- 最终代码跑完整生产流水线；
- 每个 Week 2 请求都在 HTTP 传输层用第二次 Fresh 保存的真实回复作答：1204 个请求全部匹配，未匹配 0；
- 当时超时的 7 个请求在这里也按超时处理。

| 检查项 | 结果 |
|---|---|
| claim 与来源绑定 | 951 条 claim，文本和来源绑定完全相同 |
| Alpha 原始选择 / 最终匹配 | 完全相同（187 / 164） |
| 分数、等级、冲突 | 激活分数和等级完全相同；Structure Graph 完全相同；冲突评估完全相同（准入 0） |
| 请求与 prompt | 请求集合相同；5 个任务的 prompt sha256 相同 |
| 唯一的差异 | 5 条从未发送的内容核验，原因由 `malformed_response` 改为 `input_too_large`；6 条账本记录新增 `error_message` |

### 6.7 AMD / QQQ / SNDK（`round32/06_frozen_checks/`）

| 对象 | 结果 |
|---|---|
| **AMD** | 固定清单哈希与 Round 21 完整性核对记录相同；34 项仍是“未验证” |
| **QQQ** | 冻结 run 走正式验收入口，零网络，run 目录不变。结果 `needs_review`：未声明的准入冲突 A501__A601 需要复核；QQQ 的 6 条合约规则本入口没有执行。没有改成 PASS |
| **SNDK** | 数据库、保存的 `conflicts.json`、最终代码 API 和页面一致：没有主冲突 |

### 6.8 最终版本演示（`round32/07_demo/`）

- 视频 120 s，11 个场景全部完成，代码身份和 run_id 烧录在画面里。
- 只读走查：拦截的非 GET 请求 0 次。
- 页面下载的 Export sha256 `49bd4650…`，与 Round 30 相同。

## 7. 两次 Fresh 的身份、调用、用量和费用

沿用 Round 31 已验证的材料，原样副本是 `round32/references/T4_delivery_round31_20261009.zip`，内容包括：
- 两次 run 的完整目录；
- 951 / 57 / 61 清单；
- 用量和费用。

**证据截止**：第二次 Fresh 的 `evidence_cutoff_at` 是 2026-10-09T14:47:37，记录在 `structured_agent_outputs.json` 的 metadata 中。

## 8. 对以往材料的更正

1. **Round 31 主报告第 1 节**写的是“6 个请求输入超限，且被标成 `malformed_response`”。
   - 应为：6 个未发送，其中 5 个（内容核验）被这样标记；适配器那 1 个一直记为 `WEEK2_LLM_INPUT_TOO_LARGE`。
   - 详见第 4 节。
2. **Round 32 关于 D1 的说法**：
   - 原说法“严格按 prompt 作答的回复必然被拒，适配器富集永远走回退”，只对严格 8 字段的回复成立；
   - 原说法“第一次 Fresh 的 5 个返回也都是这样被拒的”，只说明了第一失败点，其中 2 批即使补了字段也会被拒；
   - Round 32 提出的“为 D1 再做一次约 1,200 请求的 Fresh”，不再作为本版建议。离线证明与真实效果分开说明，见第 2 节。
3. **Round 32 包中被取代、没有复制进 `round32/` 的文件**：主报告、README、`report_figures.json`。
   - 它们的内容已并入本报告；
   - 数字台账由本包的 `report_figures.json` 接替，其中沿用 Round 32 的全部 61 个数字，并新增本版的数字；
   - 原件仍在 Round 32 的 ZIP 中，该 ZIP 没有修改。
4. **`round32/` 中改写的两份证据文档**：
   - `05_stage_disclosure/结构抽取与降级披露.md`：D1 段落改为指向本版定位；
   - `01_regressions/回归失败分析.md`：去掉内部授权和决定措辞。
   - 原文 sha256 和改动见 `round33/records/文档修改记录.json`。

## 9. 未关闭项与限制（如实保留）

| 项 | 状态 |
|---|---|
| D1 适配器契约缺口 | 未修复。需要修改冻结 prompt 才能正确关闭，超出本版边界；修复后的真实效果没有验证 |
| 适配器超时 | 第二次 Fresh 9 批中有 7 批在 45 s 内没有回复（P-3），与 D1 无关 |
| 输入超限 | 第二次 Fresh 有 6 个请求因超过 60,000 字符没有发送 |
| active Alpha / 主冲突 | 第二次 Fresh 没有 active Alpha，也没有主冲突 |
| T2 正式验收 | needs_review；T4 不替 T2 宣称通过 |
| AMD 34 项 | 仍是“未验证” |
| 内容核验 | 48 条引文在来源中找不到，3 条格式无效，仍待复核 |
| 研究 Agent 层 | 运行时没有记录 prompt 哈希 |
| 用量 | 7 个超时请求没有 usage |
| 第二次 Fresh | 事先没有书面说明目的 |
| PG | 只验证了本机 PostgreSQL 16.15 |
| 查看入口 | 只在本机可用；5177 加 8002 仍是混搭 |
| T1–T3 | 各自的未关闭项保持原状（`round32/references/prior_packages.json`） |

## 10. 包与验证

**入口**：本报告和 `README.md`。

**验证**：`python3 verify_package33.py`，只需 Python 3.11 及以上的标准库。它检查：
- 全部文件哈希；
- Round 32 材料与原记录一致；
- 本版三项的结论与原始结果一致；
- 报告中的全部数字可以离线重算；
- 报告引用的路径都存在；
- 凭据扫描。

本版前后的原 run、旧报告和旧 ZIP 的哈希比较，在 `round33/records/原件前后哈希/`。
