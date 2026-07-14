# Week 3 Completion Report

审查日期：2026-07-13

## 原始要求

Week 3 在 Week 2 冻结基线之上新增 Graph Builder、Activation Score、真实
PostgreSQL 持久化和 Graph API：将 claim-level `alpha_matches`/
`extracted_structures` 组装为 run-level Structure Graph，为 MVP-10 个 Alpha
计算 activation_score，落库到真实 `alpha_matches`/`structure_graphs` 表，
并通过 `GET /api/research/{run_id}/graph` 提供只读查询。

本文档只描述 Week 3 范围内已完成的内容。Week 2 的行为、契约和测试保持冻结，
未做任何修改。

**2026-07-13 correctness pass**：在首次 Week 3 实现之后，针对四项验收问题做了
专项修订：(1) evidence-gating 策略——完全无证据的 Alpha 不再能仅凭全局
graph coherence/recency 进入 watch/active/dominant；(2) POST 状态语义——
Week 3 阶段失败后 `status` 不再报告 `completed`；(3) 生产环境数据库配置——
`COMQUTOR_ENV=production` 且缺少 `COMQUTOR_DATABASE_URL` 时不再静默退化到
本地 SQLite；(4) 确认并锁定 `alpha_matches` 的行基数语义。四项均在下方对应
小节中标注，不再单独维护变更日志。

**2026-07-14 security hardening pass**：针对已确认的安全与状态一致性问题做了
专项修订，不涉及新功能、不涉及 Week 4、不改动 Week 2 Mapper/Extractor/
taxonomy/golden labels。四项：(1) GET 只读边界——默认 `GET .../graph` 路径不再
执行 schema migration、不创建数据库表/文件，读写 repository 构造职责分离；
(2) 服务端日志脱敏——Graph GET 的兜底异常处理默认只记录 `run_id`+异常类型名，
完整 traceback 仅在本地显式开启 DEBUG 级别日志时才输出；(3) Week 3
重试生命周期——引入独立、每次尝试覆盖写入的 `week3_pipeline_status.json`
标记文件，修复"同一 run 重试成功后仍被旧失败记录永久钉死在 partial/
not_ready"的问题；(4) Docker Compose 本地开发数据库安全默认值——移除硬编码
密码与含明文密码的 DSN 注释，端口改为仅绑定 `127.0.0.1`。详见下方
第二、十一、十五、十六节。

## 一、Graph JSON schema

`structure_graph.json`（文件产物）与 `structure_graphs.graph_json`（数据库
字段）内容完全一致，顶层字段：

```
schema_version              "week3.structure_graph.v1"
graph_builder_version       "week3.graph_builder.v1"
activation_scorer_version   "week3.activation_scorer.v1"
run_id, ticker
nodes[]                     见下方 Graph Builder 一节
edges[]                     见下方 Graph Builder 一节
graph_metrics                node_count/edge_count/valid_edges/
                              connected_components/longest_causal_chain/
                              duplicate_nodes_merged/duplicate_edges_merged/
                              rejected_edges
graph_coherence               formula_version/valid_edges/
                              alpha_covered_count/edge_contribution/
                              coverage_contribution/unclamped_score/score
activation                    formula_version/weights/run_timestamp/as_of/
                              alphas[]（恰好 10 项，见下）
dominant_alphas[]
provenance                    source_artifacts schema 版本、
                              committed/ambiguous/no_match 计数
```

图体内不写入墙钟时间戳；`run_timestamp`/`as_of` 来自 run 自身的
`analysis_date`/`created_at`。相同语义输入（不论字典迭代顺序、输入记录顺序、
重复执行、数据库行顺序）序列化结果完全一致——已由
`test_graph_builder.py::test_serialization_is_deterministic_across_repeated_calls`
与 `test_input_record_order_does_not_affect_serialized_graph` 验证。

## 二、PostgreSQL 表结构与迁移

新增 `comqutor_alpha/storage/db/`：

- `schema.py`：显式 SQLAlchemy Core `Table` 定义（非 ORM、非反射），
  `alpha_matches`、`structure_graphs`、`schema_migrations` 三张表。JSON 列用
  `JSON().with_variant(JSONB(), "postgresql")`：PostgreSQL 下是真实
  JSONB，SQLite（离线/测试后端）下走同一份 repository 代码，退化为
  JSON-over-TEXT。
- `migrations.py`：显式、幂等的迁移执行器（不是 Alembic）。每条迁移是
  `(version_id, tables)`，通过 `Table.create(engine, checkfirst=True)` 建表，
  并在 `schema_migrations` 表登记版本号；重复执行是安全的空操作。当前唯一
  迁移：`0001_create_week3_alpha_matches_and_structure_graphs`。
- `engine.py`：`COMQUTOR_DATABASE_URL` 只从服务端环境变量读取；未设置时默认
  退化到 `<output_root>/_comqutor_alpha_graph.db` 的本地 SQLite 文件（文件名
  含 `.`，不会与合法 `run_id` 冲突），保证默认执行仍然离线。**生产环境例外**
  （correctness pass 新增）：`COMQUTOR_ENV=production` 时不允许这个退化——
  `resolve_database_url()` 在缺少 `COMQUTOR_DATABASE_URL` 时抛出
  `DatabaseConfigurationError("PRODUCTION_DATABASE_URL_REQUIRED")`，不创建
  任何本地文件、不暴露路径或异常文本；`repository.build_repository_from_env()`
  把它包装成同一个 `GraphPersistenceError` 契约。开发/测试环境
  （`COMQUTOR_ENV` 非 `production`）行为不变，仍然退化到 SQLite。见
  `tests/test_graph_persistence.py::TestProductionDatabaseFallback`。
- `repository.py`：`GraphPersistenceRepository`，两个公开写入方法
  `persist_run()`/两个读取方法 `get_graph()`/`get_alpha_matches()`。
  所有失败都包装为 `GraphPersistenceError(reason_code)`，绝不携带 DSN、
  路径或原始异常文本。**读/写构造职责分离**（security hardening pass
  新增）：`GraphPersistenceRepository.__init__` 本身不再执行任何 migration
  ——构造实例不产生任何 schema 副作用。`build_repository_from_env()` 是
  只读构造路径（不建目录、不建本地 SQLite 文件、不调用
  `ensure_schema()`），唯一被 `GET .../graph` 使用；`build_write_repository_
  from_env()` 是写入构造路径（按需建目录/文件、调用
  `ensure_schema()` 应用 migration），只被 `POST /api/research` 内部的
  Week 3 管线使用。对本地 SQLite 后端，读路径额外用
  `engine.sqlite_file_path()` 判断目标文件是否存在：不存在时
  `get_graph()`/`get_alpha_matches()` 直接返回“无记录”，绝不通过
  `.connect()` 触发 SQLite 默认的“连接时自动建空文件”行为。schema 缺失时
  读路径返回稳定的 `DB_READ_FAILED`→`GRAPH_UNAVAILABLE`，而不是静默建表。
  见 `tests/test_week3_security_hardening.py::TestReadOnlyGetBoundary`。

`docker-compose.yml` 新增 profile-gated `postgres` 服务
（`docker compose --profile postgres up -d postgres`），默认不启动。
**安全默认值**（security hardening pass 新增）：`POSTGRES_PASSWORD` 不再有
硬编码值，改用 Compose 的 `${POSTGRES_PASSWORD:?...}` 必填语法——本地环境
未显式提供时 `docker compose` 直接拒绝启动该 profile，而不是退化到一个
可公开猜到的默认密码；`POSTGRES_USER`/`POSTGRES_DB` 保留安全的本地开发
默认值。宿主端口从 `5433:5432`（绑定所有网卡）改为 `127.0.0.1:5433:5432`
（仅本机可达）。注释中不再出现任何包含明文密码的完整 DSN 示例，改为
`<POSTGRES_USER>`/`<POSTGRES_PASSWORD>` 占位符。`.env.example` 新增对应
占位符条目。见 `tests/test_week3_security_hardening.py::TestDockerComposeSecurityDefaults`。

## 三、claim_id / source_agent_output_id 持久化映射

Development Plan 原始方案使用单一 `agent_output_id` 外键字段。当前 v2 契约
已将其拆分为两个不同身份：

- `claim_id`：Week 2 v2 引入的 claim 级身份，`alpha_matches` 表的
  `UNIQUE(run_id, claim_id)` 约束以它为准。
- `source_agent_output_id`：claim 所属原始 TradingAgents 输出的身份，即
  Development Plan 中 `agent_output_id` 所指的对象。

两者作为独立列持久化，未合并、未用新列名掩盖旧概念。

**行基数确认**（correctness pass）：`alpha_matches` 表对每条 structured
claim 精确持久化**一行**——即该 claim 的 primary 决定（`matched`/
`ambiguous`/`no_match` 三选一），不是每个候选 Alpha 一行。这直接对应 Week 2
mapper 的契约：`map_claim_to_alpha()` 对每条 claim 只返回一个结果，
`matched_alpha` 至多一个。约束是 `UNIQUE(run_id, claim_id)`，**不是**
`UNIQUE(run_id, claim_id, alpha_id)`，因为同一 claim 从不会有第二个 committed
alpha_id。次要/plausible 候选（`secondary_alphas`、ambiguous 的
`plausible_alphas`）不会被提升为额外的 committed 行，而是完整保留在该行自己的
`candidate_scores` JSON 列里，以及图的 `ambiguous_alpha_ids` provenance 中。
见 `tests/test_graph_persistence.py::TestAlphaMatchesCardinality`。

## 四、Graph Builder 归一化与去重

`comqutor_alpha/graph_engine/graph_builder.py`，仅消费 `alpha_matches.json`
与 `extracted_structures.json`，不重新解析原始 TradingAgents 报告。

- 用 `networkx.DiGraph` 构建图；`graph_metrics.connected_components` 用
  `nx.number_weakly_connected_components`，`longest_causal_chain` 用
  `nx.dag_longest_path_length`（仅在 causal 子图上，该子图按构造保证无环）。
- 节点按 canonical `id`（已经是 Week 2 输出的稳定 slug）合并，从不
  last-write-wins：`claim_ids`/`source_agent_output_ids`/`evidence`/`agents`
  全部按并集+排序输出，`score` 取最大值。
- 边按 `(source, target, edge_type)` 合并（比 Week 2 的 per-claim 边键更粗，
  这是刻意的 run-level 汇总)，`weight` 取合并实例的最大 confidence，
  provenance 全部并集保留；`assertion_status` 冲突时的合并规则：全部相同则
  保留；同时出现 `asserted` 与 `negated` 视为真实矛盾归为 `mixed`；否则按
  `asserted > conditional > mixed > negated > unknown` 优先级取值——纯集合
  运算，与合并顺序无关。
- 拒绝/安全忽略：self-loop、悬空引用（source/target 不在节点集合中）、
  不在 `{causal, supportive, conflicting}` 内的 edge_type、非有限或超出
  `[0,1]` 范围的 weight。拒绝计数记录在 `graph_metrics.rejected_edges`，
  不静默丢失信号。
- conditional/negated 边保留在图中作为可审计信息，计入 `valid_edges`，但
  activation 从不读取边的 assertion_status——反对/条件证据不会被当作
  asserted causal 证据去强化任何 Alpha。
- Alpha 标签：节点/边的 `alpha_ids` 只从自身 `claim_ids` 反查
  `alpha_matches` 中 `match_status == "matched"` 的记录得到，一个 claim 的
  Alpha 不会传染到另一个不相关 claim 构建的节点上。`ambiguous_alpha_ids`
  单独保留，不计入 `graph_coherence.alpha_covered_count`。

## 五、Graph Coherence 公式与版本

官方 Week 3 MVP 简化公式，未替换为自定义公式：

```
graph_coherence_score = min(100, valid_edges * 15 + alpha_covered_count * 10)
```

`formula_version = "week3.graph_coherence.mvp_v1"`。返回值包含
`valid_edges`、`alpha_covered_count`、`edge_contribution`、
`coverage_contribution`、`unclamped_score`、`score`。`valid_edges` 是图构建
后校验通过、去重后的边数；`alpha_covered_count` 是图中至少一个节点携带
committed（非 ambiguous/no_match）证据的 MVP-10 Alpha 去重个数。

## 六、Activation 公式

`comqutor_alpha/graph_engine/activation_scorer.py`，官方 Week 3 MVP 公式：

```
Activation = MatchedEvidence * 35% + AgentAgreement * 20%
           + GraphCoherence * 25% + Recency * 10% + DirectionStrength * 10%
```

`formula_version = "week3.activation.mvp_v1"`。未实现 ConflictPenalty
（Week 4 范围）。每个分量在加权前都归一化到 0..100；每个 Alpha 结果都暴露
`components` 字典（每项含 `raw`/`weight`/`contribution` 及分量专属明细）、
`evidence_count`、`distinct_supporting_agents`、`claim_ids`、`evidence`、
`reason_codes`，计算过程完全可审计。

## 七、五个分量定义

1. **MatchedEvidence（35%）**：按 `claim_id` 去重的 committed 证据（同一
   claim 的重复存储行不会重复计分）。每条证据按 Week 2 已标注的 `relation`
   加权：`activation=1.0`、`conditional=0.65`、`mixed=0.5`；
   `invalidation`/`risk_relief`/`mention` 权重为 0——它们是"反向"或无关证据，
   不能强化被匹配到的 Alpha。加权和除以饱和阈值 `2.0` 映射到 0-100 并封顶。
   ambiguous 证据只按 `0.15` 的保守权重叠加，且单独统计
   `unique_ambiguous_claims`，不等同于 committed。
2. **AgentAgreement（20%）**：committed 证据里、relation 权重 > 0 的去重
   `agent` 集合大小，除以该 Alpha 在 taxonomy `agent_sources` 中定义的期望
   agent 数（分母显式来自 taxonomy，恒 > 0，不会除零）。缺失 `agent` 字段
   的记录不计入去重集合，不编造一致性。
3. **GraphCoherence（25%）**：直接复用同一个 run 的全局
   `graph_coherence_score`，10 个 Alpha 共享同一个值（`scope:
   "global_run_level"`），未发明 Alpha-local 的图证据。

   **Evidence-gating 策略**（correctness pass，覆盖早期版本的"底噪"行为）：
   GraphCoherence 和 Recency 是 run 级别/全局信号，不是逐 Alpha 证据——如果不
   加约束，一个完全无证据的 Alpha 仍可能仅凭这两项在高一致性、高时效性的
   run 里拿到 `0.25*100 + 0.10*100 = 35` 分，触及 `watch` 档。这不符合"完全
   不受支持的 Alpha 绝不能进入 watch/active/dominant"的要求，因此实现了
   显式 gate：当某 Alpha 的 MatchedEvidence 加权和为 0 时（`has_admissible_
   evidence = weighted_evidence_sum > 0.0`，定义在 `score_alpha()` 里），
   GraphCoherence 和 Recency 这两个分量的 **contribution 被强制置零**
   （`components.graph_coherence.evidence_gated = true`），但 `raw` 值保留
   不变，仍可在响应里看到 run 的真实环境一致性/时效性用于审计。
   
   这个门槛覆盖两种情形，处理方式相同：(a) 真正零证据（无 committed 也无
   ambiguous claim）；(b) 只有反向证据（committed claim 全部是
   `risk_relief`/`invalidation`，MatchedEvidence 权重按定义为 0）——两者都是
   "完全不受支持"，`risk_relief`-only 的 Alpha 不能比真正零证据的 Alpha 打分
   更高。只要存在至少一条 `activation`/`conditional`/`mixed` 的证据
   （committed 或 ambiguous 皆可），Alpha 就不会被 gate，GraphCoherence/
   Recency 正常参与加权。
   
   五个官方权重（0.35/0.20/0.25/0.10/0.10）本身从未被修改，gate 只作用于
   两个分量的 contribution，不作用于权重定义。完全不受支持的 Alpha 最终
   `activation_score == 0.0`，`status == "inactive"`，`direction ==
   "unknown"`（文档化的无证据取值），因此天然被排除在 `dominant_alphas`
   之外。见 `test_activation_scorer.py::
   test_unsupported_alpha_stays_exactly_inactive_on_a_highly_coherent_recent_graph`
   与 `test_only_counter_evidence_is_gated_identically_to_true_zero_evidence`。
4. **Recency（10%）**：`run_timestamp`（默认取 run 的 `analysis_date`，否则
   `created_at`）与可注入的 `as_of`（默认等于 `run_timestamp`）逐日线性衰减，
   衰减窗口 90 天，年龄钳到 `>=0`（未来时间戳不产生额外加分）。两者都缺失
   或无法解析时使用文档化的中性回退值 `50.0`。单元测试全部使用显式注入的
   日期，不依赖墙钟时间。
5. **DirectionStrength（10%）**：committed 证据按 relation 取符号
   （`activation=+1`、`invalidation`/`risk_relief=-1`、`conditional=+0.4`、
   `mixed=0`）求平均后映射到 0-100。矛盾证据会把平均值拉向中性而不是被忽略。
   该分量衡量"证据是否支持这个 Alpha 自身的论点"，不假设"positive 方向对
   每个 Alpha 都更强"。展示给调用方的顶层 `direction` 字段则是"市场方向含义"：
   opportunity Alpha 被激活 → `positive`；risk Alpha（A304/A501）被激活 →
   `negative`（合法的看跌市场含义），risk_relief → `positive`（风险缓解对
   股价是利好）。这是两个不同但都必要的语义，前者是打分口径，后者是展示
   给使用者的市场含义。

## 八、Status-band 边界

`comqutor_alpha/graph_engine/graph_schema.py::activation_status_band`，唯一
的判定函数：

```
0..30       inactive
(30..50]    watch
(50..70]    active
(70..85]    dominant
(85..100]   regime_level
```

所有边界值（含小数）由 `test_activation_scorer.py::TestStatusBandBoundaries`
覆盖：0/30/30.1/31/50/50.1/51/70/70.1/71/85/85.1/86/100。超出 `[0,100]` 的
输入按文档化策略钳制（clamp），不拒绝。

## 九、dominant_alphas 选择规则

状态在 `{dominant, regime_level}` 内的 Alpha 才入选；按 `activation_score`
降序排序，同分按 `alpha_id` 升序稳定打破平局；不含 inactive/watch，不为任何
ticker 硬编码特定 Alpha ID，没有 Alpha 达标时返回空列表（不臆造）。

## 十、文件产物 vs 数据库 source-of-truth

数据库（`structure_graphs.graph_json`）是 Week 3 的持久化 source of
truth；`structure_graph.json` 文件产物用于本地检查、兼容、调试和可复现测试，
两者内容保证一致（`test_graph_api.py::test_graph_stage_completes_file_and_db`
逐字段断言相等）。`GET /api/research/{run_id}/graph` 只读数据库，从不读取
或重建文件产物。

## 十一、API 契约

`GET /api/research/{run_id}/graph`：与现有 `/api/research/{run_id}` 相同的
风格——恒定 HTTP 200，用 body 内 `status`/`error_code` 表达失败，不用
HTTP 4xx/5xx。安全错误码：`INVALID_RUN_ID`、`RUN_NOT_FOUND`、
`GRAPH_NOT_READY`、`GRAPH_UNAVAILABLE`、`GRAPH_CORRUPTED`、
`GRAPH_SCHEMA_MISMATCH`。成功响应包含 `run_id`/`ticker`/`nodes`/`edges`/
`graph_coherence`/`activation`/`dominant_alphas`/`provenance`，不包含本地
路径、数据库连接串或原始异常文本。GET 路径只做一次运行目录存在性检查
（文件系统、只读）加一次数据库 SELECT，不调用 TradingAgents/LLM，不重建图，
不修改任何存储。

`POST /api/research` 的 `artifacts` 字典结构**保持完全不变**（仍是原来那
9 个 key，`test_week1a_gate.py::test_run_research_request_with_offline_raw_outputs`
对它做逐字段全等断言）。Week 3 图构建/打分/持久化作为 POST 编排链的内部
步骤执行（写文件、写数据库）。

**POST 状态语义更新**（correctness pass）：早期版本里 `status` 只看 Week
1-2 的 4 个必需 artifact，Week 3 失败与否完全不影响它——这会导致 Week 1-2
成功但 Week 3（图构建/打分/持久化任一环节）失败的 run 仍然报告
`status: "completed"`，具有误导性。现在 `build_research_response()` 额外
检查 `structure_graph.json` 文件是否存在、且最近一次 Week 3 尝试的
`week3_pipeline_status.json` 标记是否记录 `outcome: "success"`（纯文件系统
信号，不需要查数据库；这个管线保证 Week 1-2 一旦成功就无条件尝试 Week 3，
且每次尝试结束时都会写下自己的结果，因此这两个信号在真实 run 里等价于
"数据库是否真的写成功"）：

- `complete`（Week 1-2 四个 artifact 齐全）且 `structure_graph_ready`
  （Week 3 图已写出且最近一次尝试成功）→ `status: "completed"`。
- `complete` 但 Week 3 未就绪，或 Week 1-2 本身只是部分完成 → 复用既有的
  `status: "partial"` 词汇，不引入新枚举值。
- Week 1-2 连一个必需 artifact 都没有 → `status: "failed"`（不变）。

**重试生命周期修复**（security hardening pass）：`error_logs/
week3_pipeline_errors.jsonl` 是纯追加、从不清空的审计日志。早期版本直接用
"这个文件是否存在"作为就绪判定，导致一个 run 只要失败过一次，即使后续重试
成功写库，`status`/`structure_graph_status` 也会被那条旧记录永久钉死在
`partial`/`not_ready`。现在改用独立的 `week3_pipeline_status.json`
标记文件：每次 Week 3 尝试（无论成功或失败）结束时都会**整体覆盖**（而非
追加）这个文件，记录 `{run_id, outcome, stage, updated_at}`；就绪判定只看
这个文件的最新内容，不再看 JSONL 日志是否存在。效果：最近一次尝试成功
→ 状态恢复为 `completed`/`ready`；最近一次尝试失败 → 诚实报告
`partial`/`not_ready`（即使更早的尝试曾经成功过）；`week3_pipeline_errors.
jsonl` 继续保留完整失败历史供审计，但不再参与就绪判定，因此不会污染当前
状态。见 `tests/test_week3_security_hardening.py::TestRetryLifecycle`。

**服务端日志脱敏**（security hardening pass）：`GET .../graph` 的兜底异常
分支（非 `GraphPersistenceError` 的意外异常，例如驱动 `ImportError`、原始
`OSError`）此前用 `logger.exception(...)` 无条件记录完整 traceback——
SQLAlchemy/驱动异常的文本经常直接包含 DSN、主机名或用户名，这是服务端日志
（不是客户端响应）的真实泄漏面。现在默认（`WARNING`）只记录
`run_id`+异常类型名；完整 traceback 改为单独的 `logger.debug(..., exc_info=
True)` 调用，只有当运维方显式把日志 handler 配置到 `DEBUG` 级别（一个本地、
显式的动作，绝不是生产默认状态）时才会输出。Week 3 管线各阶段失败只写入
安全字段（`run_id`/`stage`/稳定 `error_code`/时间戳）到 JSONL 和一条同样
安全的 `logger.warning`，从不记录触发异常本身的文本或 traceback。见
`tests/test_week3_security_hardening.py::TestLogAndResponseLeakage`。

新增顶层字段 `structure_graph_status`：`"ready"` 或 `"not_ready"`，是一个
稳定、可加字段（不影响 `artifacts` 的形状，也不影响任何既有逐字段断言）。
"not_ready" 统一覆盖"从未尝试"、"构建失败"、"打分失败"、"持久化失败"四种
情形——需要具体原因的调用方应查询 `GET .../graph`，它有自己更细的
`error_code` 契约（见上）。三种失败注入的行为验证见
`tests/test_graph_api.py::test_post_does_not_return_completed_when_graph_construction_fails`
/`..._activation_scoring_fails`/`..._graph_persistence_fails`；三者都确认
`status != "completed"` 且 GET 返回稳定的 `GRAPH_NOT_READY`，不重建图。

## 十二、NVDA sanity 解读

`tests/test_week3_nvda_sanity.py` 使用手写的、覆盖四类 agent 的离线 NVDA
fixture（不复制、不修改任何 golden label 文件），跑完整 Week 1-3 离线管线。
观测结果（fixture 相关，非通用市场结论）：A101/A103/A201/A301/A304/A601 全部
获得 committed 证据；A101(≈97.5)/A601(≈89.4) 进入 dominant_alphas，A304 在
拥有真实负向证据（valuation risk）的同时仍然获得非零、`direction=negative`
的 activation（未被同时存在的正向 AI 证据掩盖）。测试断言范围/排序/差异化而
非精确分数，避免公式微调后出现脆弱失败。这是结构一致性诊断，不是市场预测
准确率，也不产生 Buy/Sell/Hold 结论。

## 十三、QQQ sanity 解读

`tests/test_week3_qqq_sanity.py` 明确标注为**合成（synthetic）**宏观
fixture（仓库中不存在真实 QQQ TradingAgents 报告产物），claim 文本取自
taxonomy 自身的 trigger/confirmation 信号语言。A001/A003/A501 均获得非零
committed 证据；A001/A003（3-agent 佐证）进入 dominant，A501（1-agent
佐证）差异化地更低。opportunity Alpha 激活方向为 `positive`，risk Alpha
（A501）激活方向为 `negative`——合法的看跌含义，不是错误。响应体中不出现
`main_conflict`/`conflict_score`/`conflict_level`；A001/A003 与 A501 的
pairwise 冲突仲裁明确推迟到 Week 4。

## 十四、Week 4 明确推迟

`alpha_activations`/`alpha_conflicts` 数据库表、`conflict_detector.py`、
`conflict_score`/`conflict_level`/`main_conflict`、bull/bear structure
仲裁、`exposure_engine.py`、`entity_alpha_exposure_seed.yaml`、
`/api/research/{run_id}/conflicts`、`/api/research/{run_id}/agent-outputs`、
完整 canonical research response、Alpha Memory、outcome feedback、组合逻辑、
dashboard、Neo4j 均未实现。Week 2 遗留的 claim-level `conflicting` 边可能
仍存在于图中（可审计信息），这不等同于 Week 4 的 Alpha 级冲突仲裁；taxonomy
的 `conflict_alphas` 未被用于计算 pairwise conflict score。

## 十五、已知限制

1. Recency 目前是 run 级别（而非 claim 级别）——`alpha_matches.json` 本身
   不携带逐 claim 时间戳，同一 run 内所有 Alpha 共享同一个 recency 值。
2. `structure_agent_output_id`/`claim_id` 的持久化列长度上限为 300 字符，
   继承自现有 claim_id 组装规则（`agent:field:claim:n`），目前未观察到
   越界场景。
3. PostgreSQL JSONB 与 SQLite JSON-over-TEXT 是仅有的两个受支持方言；其他
   方言会被 `UNSUPPORTED_DATABASE_DIALECT` 显式拒绝，而不是静默尝试。
4. `structure_graph_status`/`status` 的"是否就绪"判定基于文件系统信号
   （`structure_graph.json` 是否存在、`week3_pipeline_status.json` 最近一次
   记录的 `outcome` 是否为 `success`），不直接查库；这在当前管线（Week 3
   一旦启动就要么成功走到底要么在失败时覆盖写状态标记）下等价于真实的
   数据库落库结果，且重试后能正确恢复（见十一节"重试生命周期修复"），
   但如果未来出现"持久化成功后进程崩溃、来不及写成功标记"这类极端情形，
   信号可能短暂滞后于数据库真实状态。GET `.../graph` 本身仍然直接查库，
   不受这个限制影响。
5. 与 Week 2 相同：deterministic NLP 对复杂嵌套语义仍有覆盖边界；这不是
   Week 3 引入的新限制。
6. `docker compose config`（以及任何完整解析 Compose 栈变量插值的命令）会把
   `env_file`/`environment` 引用的真实本地密钥以明文形式打印出来——这是
   Docker Compose 自身的既有行为，不是本次改动引入的问题，但意味着这类命令
   绝不能在共享或被记录的终端环境中对着真实 `.env` 运行。仓库/文档层面无法
   完全消除这个风险，只能提示：本地开发者需自行避免在日志会被留存的场景下
   执行这类命令。

## 十六、部署假设与已知安全边界（Security Hardening Pass, 2026-07-14）

本节明确当前 Graph API 的部署假设，防止未来被误描述为已具备多租户授权：

1. **Graph API 仅适用于本地或可信内网部署。** `POST /api/research`、
   `GET /api/research/{run_id}`、`GET /api/research/{run_id}/graph` 均未实现
   任何身份认证（authentication）或访问控制（authorization）中间件。
2. **`run_id` 不是授权凭据。** 它只经过字符集/路径穿越安全性校验
   （`validate_run_id_for_path`），从未被当作访问令牌或密钥设计；知道一个
   `run_id` 字符串即可读取该 run 的完整 Graph/研究结果。
3. **当前没有 owner_id/tenant_id 强制隔离。** `schema.py` 的
   `alpha_matches`/`structure_graphs` 表没有归属者列；`GraphPersistenceRepository`
   的所有查询只按 `run_id` 过滤，不存在、也不检查"这个调用方是否有权访问
   这个 run_id"。
4. **不应直接暴露到公网。** 当前实现假设部署环境本身（网络边界、反向代理、
   VPN 等）已经限制了谁能连接到这个服务；服务自身不做这层防护。
5. **公网或多用户部署前必须先实现 authentication 与 run ownership**
   （例如 API key/session 认证 + `owner_id`/`tenant_id` 列与查询过滤），
   本次 security hardening pass 明确不实现这套体系——仓库中没有可复用的正式
   身份架构，临时拼凑一套（自制 header token、硬编码密码等）风险更高，
   故只在此处记录限制，不引入临时方案。

见 `tests/test_week3_security_hardening.py::TestAuthTenantDocumentationContract`
（防止这一节的免责声明被未来的改动删除或弱化，而没有同时补上真正的
authentication 实现）。
