# COMQUTOR Alpha T4 最终交付报告（Round 32）

- **交付对象**：项目负责人 Xiang Mao、John。
- **日期**：2026-10-09。
- **两个代码身份，不混用**：

| 代码 | git HEAD | tracked diff sha256 | untracked sha256 | 提交状态 |
|---|---|---|---|---|
| 两次 Fresh 真实执行时的代码 | `7a9aefa` | `1b53b921…` | `38ef636f…` | 未提交 |
| 本轮最终修复代码 | `7a9aefa` | `6cdd51e3…` | `10ee7518…` | 未提交；完整 diff、未跟踪源码 tar 和清单在 `02_code/` |

  **最终修复版不是两次 Fresh 当时用的代码**。相对 Fresh 代码的改动见 `02_code/round32_changes.diff`（20 个文件）。
- **本轮边界**：
  - 零新增 Provider、模型、搜索或取数请求，没有第三次 Fresh，没有重跑研究 Agent，没有重试失败请求；
  - 没有修改 prompt、模型、taxonomy、Gold、核验标准、评分阈值或 PD-006；
  - 原始 run、Round 31 包和旧 ZIP 只读（前后哈希见包外的 `hash_proof/`）；
  - 没有 commit 或 push，没有给 John 发消息。

## 1. 停止条件

| # | 条件 | 结果 | 证据 |
|---|---|---|---|
| 1 | 最终代码上的必需 PG 及相关验证完成 | **满足**：PG 集成测试 65 passed、0 skipped；PG 链路（空库迁移 → 生产持久化 → 正常停止 / 重启 → 历史重开 → API 与 Export → 一致性）全部通过；Replay mismatch 测试、ESLint、受影响回归都在最终代码上通过 | `04_tests/`、`03_postgres/` |
| 2 | 两个必需回归失败已解决或有正式处理决定 | **满足**：两项都定位为测试错误，已按正确预期修复；有修复前快照和修复后复现，有负对照；不涉及冻结哈希 | `01_regressions/` |
| 3 | 本地拒绝、真实失败、回退和完成状态披露正确 | **满足**：未发送请求记为 `input_too_large`；API、页面、Export 都有阶段降级披露；completed 规则没有改 | `03_not_sent/`、`05_stage_disclosure/` |
| 4 | 冻结数据检查和规定 Demo 场景有可核查证据 | **满足**：AMD 引用核对、QQQ 冻结输入正式验收、SNDK 三方一致；最终版本视频 11 个场景，含烧录字幕 | `06_frozen_checks/`、`07_demo/` |
| 5 | 最终交付可追溯、可解压核验、可离线复现 | **满足**：解压到新目录后六项检查通过，见第 11 节 | `unzip_verification/`（包外） |

**结论：T4 工程验收要求已完成，提交 John 签收。**

- 这是工程验收结论，不是 John 的签收。
- 模型语义层面的不足仍按原样保留（第 10 节），不因本结论变成通过。
- 有一项新发现的工程缺陷需要负责人决定（第 9 节）。它不在 T4 四项要求之内，本轮没有修。

## 2. John T4 四项要求：逐条关闭表

| John 的要求 | 关闭状态 | 证据 | 验证方式 | 限制 |
|---|---|---|---|---|
| **1. PostgreSQL 验证，不以 SQLite 回退代替**（迁移、来源持久化、重启、历史重开、Export、run_id 与输入一致；Replay 测试根因；两项 ESLint；必需测试不能用 skip 收口） | **关闭** | `03_postgres/`、`04_tests/pg.*`、`04_tests/replay.*`、`04_tests/frontend.log`、Round 27 `REPLAY_AND_ESLINT.md`（引用） | 在最终代码上：独立库 `comqutor_alpha_t4_r32_verify_test`，从空库开始；派生验证执行经生产生命周期写入；实例正常停止后重启；重启前后快照逐项相同；Export 与 manifest 和目录逐字节一致；PG 测试组 65 passed、0 skipped（独立库 `comqutor_alpha_t4_r32_pytest_test`）；Replay mismatch 测试通过；ESLint 0 问题，本次日志记录了时间和代码身份 | 只验证了本机 PostgreSQL 16.15；Replay 修复前的原始失败日志仍然缺失（Round 27 已说明） |
| **2. 调用与费用计量** | **关闭**（沿用 Round 31 的核对，并更正未发送记录） | `references/T4_delivery_round31_20261009.zip`（`usage_cost/`）、`03_not_sent/not_sent_appendix.json` | 两层、按任务、逐请求对账（Round 31）；本轮修正：输入超限的请求记为未发送，账本写明实际字符数和上限 | 金额是估算；7 个超时请求没有 usage；价格表是 2026-09-30 查询的 |
| **3. 一次必要的 Fresh 验证** | **关闭**（两次 Fresh 都由 Xiang Mao 在网页亲自点击；本轮没有新 Fresh） | Round 29 / 30 / 31 包、`05_replay/` | 第二次 Fresh 真实执行（completed，951 条 claim）；本轮再用最终代码消费它保存的真实回复，研究结果不变（第 5 节） | 第二次 Fresh 事先没有书面说明目的；只证明本机指定 profile |
| **4. 实际 Demo 视频** | **关闭** | `07_demo/recording_final/t4_demo_final.mp4`、`07_demo/视频场景索引.md` | 最终代码只读打开第二次 Fresh 的结果，覆盖 Research → 重要结论 → 来源片段 / 计算依据 → Structure Graph → Conflict Radar → 历史重开 → Export，另有证据不足、没有主冲突、标注的模拟失败；代码身份和 run_id 烧录在画面里 | 没有 Start Research 的点击录像（John 没有要求这一项）；旧视频保留 |

## 3. 本轮修复

### 3.1 两个回归失败（`01_regressions/回归失败分析.md`）

**复现结果**：

| 代码树 | 结果 |
|---|---|
| HEAD | 2 passed |
| Fresh 代码快照（修复前） | 2 failed |
| 修复前的工作区 | 2 failed |
| 修复后的工作区 | 2 passed |
| 负对照 | 3 个对照全部失败（测试仍然有效） |

被测的两个生产文件在修复前后逐字节相同，修复只在测试里。

| 测试 | 原因 | 处理 |
|---|---|---|
| `test_structured_adapter_concurrency_touches_no_alpha_mapping_code` | 全文子串检查命中了 Round 9 写的一条注释（只是类比说明）。该模块不 import、也不调用 alpha_mapper | 去掉 `#` 注释后再做原来三个子串断言，另加 AST import 断言 |
| `test_structured_claim_shadow_is_additive_to_semantic_tasks` | Round 26 在 `SEMANTIC_TASKS` 登记了 `content_support_verification`（有记录），测试期望没有跟着更新 | 期望集合加入该任务，严格相等断言保留 |

**本轮自身引起的第三个失败**：`test_semantic_artifact_live_pipeline.py::test_cache_miss_integration_adds_only_sidecars_not_business_semantics`。
- 原因：新增的 `stage_disclosure` 来自语义账本，没有账本的一方必然显示 `not_recorded`。
- 处理：比较时排除这个字段，并新增明确断言（无账本 = `not_recorded`；有账本 = 列出 6 个阶段）；其余响应字段仍要求完全相同。
- 第一次冻结上的试跑和原因见 `04_tests/probe_run_before_test_fix/`。

### 3.2 "未发送却记为 malformed_response"（`03_not_sent/`）

**真实边界**：输入超过 60,000 字符时，网关在预算占用和 HTTP 之前就本地拒绝。

**修复**：
- 内容核验和方向判断都把 `WEEK2_LLM_INPUT_TOO_LARGE` 记为 `input_too_large`（沿用 alpha_mapper 已有的原因码），不再混进 `malformed_response`；
- 账本 `error_message` 写明实际字符数、上限，以及没有预算占用、没有 HTTP、没有 usage；
- 页面和 API 的解释改为"未发送"。
- 状态不变：claim 仍是 PENDING_REVIEW（技术未完成），不会变成有效 NONE 或"不支持"。

**测试**：只替换底层 HTTP。超限请求到达传输层 0 次、预算不变；合法请求结论与 Fresh 当时相同。

**历史记录不改写**，逐条更正见附录：

| run | 未发送 | 其中误标为 `malformed_response` |
|---|---|---|
| 第二次 Fresh | 6（内容核验 5、适配器 1） | 5 |
| 第一次 Fresh | 33 | 31 |

### 3.3 结构抽取与降级披露（`05_stage_disclosure/`）

**结构抽取**：
- 第 1 个回复格式合规，但被既有的"证据支撑"规则拒绝，**保留失败**；
- 第 2 个回复是合规的空结果（没有关系），既有策略改用确定性语法；
- 两条 claim 都没有边。模型结构抽取贡献 0 条边，Structure Graph 的边全部来自 TradingAgents canonical relations。

**适配器**：
- 9 批全部回退，951 条 claim 的 entities、factors、direction、confidence、cited_source_id 都来自确定性抽取；
- direction 为 unknown 表示"没有判断"，不是模型判断为 unknown；
- 另发现一项工程缺陷，见第 9 节。

**披露**：
- 新增 `stage_disclosure`：逐阶段列出调用数和各类结果，以及哪些字段来自确定性处理；Graph 构建和模型结构抽取分开报告；
- 出现在 API、页面（Research summary 下的 "Processing completeness"）、Export（本轮之后完成的 run 写入 `stage_disclosure.json`，与 API 完全一致）；
- completed 的含义没有改。

## 4. 最终代码上的 PostgreSQL 验证（`03_postgres/`）

| 步骤 | 结果 |
|---|---|
| 1. 空库迁移 | 派生执行前 0 张表 → 7 个迁移、9 张表；方言 postgresql，库名 `comqutor_alpha_t4_r32_verify_test` |
| 2. 生产持久化 | 派生验证执行经生产生命周期（`claim_research_run` + `execute_claimed_research_run`）写入：research_runs 1、agent_outputs 951、alpha_matches 951、structure_graphs 1、alpha_activations 10、alpha_conflicts 8 |
| 3. 停止 / 重启 | SIGTERM 正常停止，日志 "Application shutdown complete"，然后重启 |
| 4. 历史重开 | 重启前后快照（历史、详情、状态、图、冲突、agent 输出、关键证据追溯、产物）完全相同 |
| 5. API 与 Export | Export 20 个 manifest 文件，与 manifest 和目录逐字节一致；ZIP 含 `stage_disclosure.json`，与 API 相同；重启前后 ZIP 的 sha256 相同 |
| 6. 一致性 | run_id、DB 行、metadata 一致；原始输入、来源登记、来源内容哈希与第二次 Fresh 相同（run_id 归一后）；`based_on_run_id` 指向 `12591384…`；`run_environment` 记录最终代码和 `old_result_reevaluation` |

**PG 集成测试**：11 个文件，65 passed，0 skipped，显式配置独立测试库 `comqutor_alpha_t4_r32_pytest_test`。

### 最终代码上的测试（`04_tests/`）

所有测试组都在代码冻结后运行。每组前后都记录了代码身份（`6cdd51e3…` / `10ee7518…`），运行期间代码没有变化。外部网络陷阱的拦截次数都是 0。

| 组 | 结果 | 退出码 |
|---|---|---|
| new：本轮测试，Round 27 / 28 的环境、计量、停止测试，以及两个修复的测试 | 46 passed | 0 |
| replay：`test_replay_conflict_does_not_get_run_id_mismatch` | 1 passed | 0 |
| pg：11 个 PostgreSQL 集成文件 | 65 passed，0 skipped | 0 |
| affected：Round 28 的 53 个文件，加上本轮受影响面的 20 个文件 | 1313 passed，1 skipped，0 failed | 0 |
| frontend | ESLint 退出码 0；typecheck 退出码 0；vitest 4 个文件 102 passed | 0 |

- affected 组跳过的 1 个是 `tests/test_week2_llm.py:1214`，需要设 `COMQUTOR_RUN_WEEK2_PROVIDER_SMOKE=1` 才会发真实请求，不是必需测试。
- 没有跑全量回归。

## 5. 本轮修复没有改变研究答案（`05_replay/`）

**派生验证执行** `t4r32-replay-20261009T202841Z-12f19149`：
- 最终代码跑完整的生产流水线；
- 每个 Week 2 请求都在 HTTP 传输层用第二次 Fresh **已保存的真实回复**作答，按请求正文匹配：1204 个请求全部匹配，未匹配 0；
- 当时超时的 7 个请求在这里也按超时处理；
- 外部网络尝试 0；没有合成任何回复。

| 检查项 | 结果 |
|---|---|
| claim 与来源绑定 | 951 条 claim，文本和来源绑定完全相同 |
| Alpha 原始选择 / 最终匹配 | 完全相同（187 / 164） |
| 内容判断 | 状态完全相同 |
| 已保存方向 | 方向审计完全相同，证据事实分组相同（79 组） |
| 分数、等级、冲突 | 激活分数和等级完全相同，Structure Graph 完全相同，冲突评估完全相同（准入 0），正式验收相同 |
| 请求正文与 prompt 身份 | 请求集合相同，5 个任务的 prompt sha256 相同 |
| 唯一的差异 | 5 条从未发送的内容核验，原因由 `malformed_response` 改为 `input_too_large`；6 条账本记录新增 `error_message`。这正是本轮修复要带来的变化 |
| 失败不变成有效答案 | 这 5 条状态仍是 PENDING_REVIEW，没有模型判定；Alpha 分类不可用 0 |

过程中有三次尝试被取代，原因都是验证工具本身，不是被测代码：回复 run_id 处理、超时重放方式、运行行登记。见 `05_replay/superseded_attempt1/`、`05_replay/superseded_attempt2/`、`05_replay/superseded_attempt3/`。

## 6. AMD / QQQ / SNDK（`06_frozen_checks/`）

| 对象 | 做法 | 结果 |
|---|---|---|
| **AMD** | 只引用，不重审 34 项 | 固定清单 json / csv 的哈希与 Round 21 完整性核对记录相同；34 项仍是"未验证"，没有回填 |
| **QQQ** | 冻结 run `0d890564` 走现有正式验收入口，零网络，run 目录不变 | 结果 `needs_review`：未声明的准入冲突 A501__A601 需要复核；QQQ 的 6 条合约规则本入口没有执行；配置错误 0；产物完整。与 Round 24 结论相同。没有改成 PASS |
| **SNDK** | 只读打开历史 run | 数据库（8 个冲突对全部 rejected，主冲突 0）、两份保存的 `conflicts.json`（准入 0，没有主冲突）、最终代码 API 和页面一致，都是"没有主冲突" |

## 7. 最终版本演示（`07_demo/`）

- 视频 `t4_demo_final.mp4`，120 s，11 个场景全部完成。
- 只读走查：拦截的非 GET 请求 0 次，研究提交尝试 0 次。
- **烧录字幕**：标签、场景、完整 run_id、Fresh 代码和最终代码都在画面里。
- 页面下载的 Export sha256 `49bd4650…`，与 Round 30 相同。
- 场景时间见 `07_demo/视频场景索引.md`。

## 8. 两次 Fresh 的身份、调用、用量、费用和结果清单

沿用 Round 31 已验证的材料，作为原样副本放在 `references/T4_delivery_round31_20261009.zip`，没有重做语义审核。内容包括：
- 两次 run 的完整目录；
- 身份与配置；
- 951 / 57 / 61 清单；
- 用量和费用。

**本轮对 Round 31 的更正**：
1. **证据截止**：run 其实记录了，在 `structured_agent_outputs.json` 的 metadata 中。
   - 第二次 Fresh：`evidence_cutoff_at` 2026-10-09T14:47:37，依据 MAX_SOURCE_FETCHED_AT；
   - 第一次 Fresh：2026-10-08，依据 ANALYSIS_DATE_FALLBACK_MIDNIGHT。
   - Round 31 写的"未记录"是错的。
2. **未发送请求**：Round 31 已经指出标签不准；逐条附录见 `03_not_sent/not_sent_appendix.json`。
3. **适配器"返回但校验失败"的原因**：校验器要求的字段，prompt 从来没有要求（第 9 节）。
4. **结构抽取第 2 个"rejected"**：实为合规的空结果。

## 9. 需要负责人决定的事项

**D1（适配器校验器与冻结 prompt 不一致）**

- **现象**：
  - 适配器校验器要求每条回复必须有 `cited_source_id`；
  - 冻结的任务说明（`week2.claim_batch_enrichment.v1`，sha256 `c6822099…`）只要求 8 个字段，从没要求这个字段；
  - 因此严格按 prompt 作答的回复必然被拒，适配器富集永远走回退。
- **证据**：第二次 Fresh 的 attempt 8（30 条）和晚到的 attempt 2（64 条），以及第一次 Fresh 的 5 个返回，每条都是 8 个字段，失败点相同（`05_stage_disclosure/结构抽取与降级披露.md`）。
- **为什么本轮没修**：
  - 让校验器接受缺少 `cited_source_id` 的回复，或修改 prompt（本轮禁止），都会改变送进 Alpha 分类的 factors 和 direction；
  - 已保存的真实回复无法证明修复后的结果，必须用新的真实调用才能观察，这会改变研究结果。
- **需要决定**：是否修、怎么修（改校验器，或经批准改 prompt）。如果修，需要一次新的 Fresh 来观察效果：
  - 目的：验证适配器富集被采用，以及它对下游 Alpha 分类的影响；
  - 预算参照第二次 Fresh：约 1,200 个 Week 2 请求，估算 $1.80–3.60，约 2 小时 16 分；
  - 本轮没有运行，真实启动仍由 Xiang Mao 亲自点击。

## 10. 保留的材料和语义限制（如实保留，不制造成功）

| 项 | 状态 |
|---|---|
| active Alpha / 主冲突 | 第二次 Fresh 没有 active Alpha，也没有主冲突 |
| T2 正式验收 | needs_review：NVDA 触发矩阵绑定的是另一个 run，规则不可评估；T4 不替 T2 宣称通过 |
| AMD 34 项 | 仍是"未验证" |
| 内容核验 | 48 条引文在来源中找不到，3 条格式无效，仍待复核 |
| 适配器富集 | 没有使用模型结果（D1） |
| 研究 Agent 层 | 运行时没有记录 prompt 哈希 |
| 用量 | 7 个超时请求没有 usage |
| 第二次 Fresh | 事先没有书面说明目的 |
| PG | 只验证了本机 PostgreSQL 16.15，不代表其他部署 |
| T1–T3 | 各自的未关闭项保持原状（`references/prior_packages.json`） |

## 11. 包与验证

**入口**：`README.md`。验证命令只需 Python 标准库：`tools/verify_package32.py`。

六项检查：
1. 逐文件哈希；
2. 报告引用和 README 命令；
3. 离线重算报告数字（`report_figures.json`）；
4. 嵌套的 Round 31 ZIP、派生执行的 Export、演示的页面下载 ZIP；
5. 凭据扫描；
6. 代码身份。

**解压验证**：在包外的 `unzip_verification/` 中，记录了命令、完整输出和退出码。**原 run、旧 ZIP 和受保护文件的前后哈希**也在包外：`hash_proof/`。
