# Week 4.2 Alpha Activation and Conflict Persistence Report

审查日期：2026-07-14

## 1. Current branch / HEAD

- Branch: `comqutor-structure-layer`
- HEAD: `49e2dfb535a07b3b8daca9790dc27ebe6535e93b`
- Commit: `49e2dfb w4v31`

## 2. Branch operations

未创建、切换、合并或删除 branch，未修改 branch ref，未 commit，未 push。

## 3. Starting git status

工作树为空，无 staged、unstaged 或 untracked change。

## 4. Pre-existing changes

无。

## 5. Files changed

- `comqutor_alpha/storage/db/schema.py`
- `comqutor_alpha/storage/db/repository.py`
- `comqutor_alpha/storage/db/week4_persistence.py`
- `tests/test_week4_persistence.py`
- `tests/test_week4_postgres_persistence.py`
- `docs/week4_persistence_report.md`

`migrations.py` 无需修改：当前 migration registry 本来就在 `schema.py`。

## 6. Scope implemented

新增 Week 4 两表、0002 migration、activation/conflict validation、原子 replace、
确定性读取与重建、SQLite tests 和 PostgreSQL integration profile。

**修正（2026-07-14 Correctness Patch）**：初始版本本节曾使用"递归 whitelist"
描述 activation component 校验，但当时的实现只校验了 component 一级字段*名称*
（所有五个 component 共享同一个扁平字段名集合），并未对每个 component 的字段
*类型/取值范围*做验证，也没有验证 activation 与 conflict 两个 payload 之间的
交叉一致性——即两者严格意义上都不是"递归"的。这一节的原始措辞是不准确的自我
描述，不是事后才发现的新缺陷；本补丁（见文末 "W4.2 Correctness Patch" 一节）
关闭了这个差距，现在才真正符合"per-component typed recursive whitelist"。

## 7. Scope deferred

W4.3 API、research pipeline 自动调用、Exposure Engine、MSFT A102-A304、Dashboard、
authentication、authorization、tenant ownership、Alpha Memory 和跨 run feedback 均未实施。

## 8. Existing DB architecture reviewed

继续使用 SQLAlchemy Core、显式 `sa.Table`、`_json_type()`、顺序 migration registry
和单一 cross-dialect repository。Repository 构造不迁移；只读 factory 不建文件；
写 factory 才调用 `ensure_schema()`。现有 `persist_run()` 语义未改变。

## 9. alpha_activations design

每个 run/Alpha 一行，含正式 activation 字段、原 payload 位置 `activation_rank`、
whitelist `activation_json`、时间字段和 `UNIQUE(run_id, alpha_id)`。按 run_id 和
ticker 建普通索引，不存在 ticker-only uniqueness。

## 10. alpha_conflicts design

每个 run/taxonomy-declared canonical pair 一行，保存 outcome、admitted query fields、
main flag、rank、reason codes、evidence audit、whitelist candidate/conflict JSON 和
W4.1 schema/formula version。约束为 `UNIQUE(run_id, alpha_a, alpha_b)`。

## 11. Why every outcome is persisted

`admitted`、`suppressed`、`rejected` 全部持久化，避免数据库只保留 selection、丢失
W4.1 non-selection reason 和 evidence audit。正常冻结 taxonomy run 为六行。

## 12. Migration 0002

精确名称：`0002_create_week4_alpha_activations_and_alpha_conflicts`。0001 名称及表集合
未修改，0002 只包含 `alpha_activations` 和 `alpha_conflicts`。

## 13. Upgrade behavior

测试模拟已有 0001、`alpha_matches` 和 `structure_graphs` 数据的数据库；apply 只返回
0002，Week 3 rows 全部保留。再次 apply 返回空列表，migration version 无重复。

## 14. Activation validation

验证 run/ticker、正式 activation formula version、alphas list、唯一 Alpha、名称、
finite `[0,100]` score、status、direction、JSON 安全性和可选内嵌 identity。
Partial/empty activation payload 可持久化。

## 15. Conflict validation

验证 W4.1 schema/formula/identity、candidate counts、canonical unique pairs、outcome、
reason codes、evidence audit、admitted-to-conflict 一一对应、main 等于 conflicts[0]、
rank、bull/bear、score/level、components 和所有数值范围。不重新计算 W4.1 公式。

## 16. JSON whitelist

Activation、component、candidate、evidence audit、conflict、bull/bear structure 和
components 均显式 whitelist。未知字段被丢弃；NaN、Infinity 和非标准 JSON 被拒绝；
`_sort_*`、prompt、provider response、path、DSN、env 和 traceback 不进入 JSON columns。

## 17. Safe error contract

Public repository 只返回稳定 `GraphPersistenceError(reason_code)`：activation/conflict
invalid、identity mismatch、data inconsistent、DB corrupted、migration/write/read failure
和 unsupported dialect。错误文本不包含 payload、evidence、DSN、路径或 traceback。

## 18. Atomic write semantics

`persist_week4_results()` 在 validation 完成后，于同一 transaction 删除两表旧 rows，
插入 activation rows 和 conflict rows。任一 insert 失败时两表均 rollback。

## 19. Replace and idempotency

同 run 重试使用 delete-and-insert replace，不累积或混合旧数据；相同 payload 重试行数
和 reconstruction 不变，changed payload 完整替换。

## 20. Run isolation

所有 delete/read 均以 run_id 为边界。不同 run、同 ticker 不同 run 都通过隔离测试。

## 21. Read methods

- `get_alpha_activations()`: activation_rank、alpha_id 稳定排序。
- `get_alpha_conflicts()`: canonical pair 排序，可过滤三个正式 outcome。
- `get_week4_conflict_result()`: 重建 W4.1 payload；unknown run 返回 `None`。

## 22. Deterministic reconstruction

Candidate 按 pair 排序，conflicts 按保存的 rank 排序，唯一 main 必须是 rank 0。
读取时重新验证 whitelist、row/JSON columns、version、ticker、rank 和 main 一致性；
损坏数据不修复，返回 `DB_DATA_CORRUPTED`。

## 23. Read-only SQLite safety

三个 Week 4 read method 均扩展 missing-file guard。在未写 output root 上返回
`[]`/`None`，不创建 `_comqutor_alpha_graph.db`，不迁移、不写 migration row。

## 24. SQLite schema tests

覆盖全部列、primary key、两个 unique constraint、JSON type、migration 名称和顺序。

## 25. SQLite persistence tests

覆盖 activation/conflict round trip、所有 outcome、audit、main/rank、白名单、identity、
version、非法 JSON、replace、idempotency、run isolation、filters 和 unknown run。

## 26. Transaction rollback tests

分别在 activation insert 和 conflict insert 注入数据库失败；两表恢复先前已提交状态。
Validation failure 也发生在 transaction 前且保留原状态。

## 27. W4.1 to W4.2 round trip

测试由真实 `detect_alpha_conflicts()` 生成 payload。DB reconstruction 与原 W4.1
payload 完全相等，包括 conflicts 顺序、main、counts 和 evidence audit。

## 28. NVDA persistence sanity

真实 Week 1–3 NVDA offline fixture → W4.1 detector → W4.2 persistence 全链路通过。
A101-A304 admitted、`is_main_conflict=true`、rank 0，reconstruction main 正确。

## 29. MSFT status

`BLOCKED_BY_SPEC_CONFLICT`。未添加或持久化 A102-A304。

## 30. PostgreSQL configuration

Integration profile 只读取 `COMQUTOR_TEST_DATABASE_URL`，只接受 PostgreSQL DSN，
使用唯一 run prefix，只清理自身 rows，不 drop/truncate table/database，不修改 migration。

## 31. PostgreSQL result

`COMQUTOR_TEST_DATABASE_URL` 未配置：9 个 integration invocations 明确 skipped。
PostgreSQL JSONB、constraint 和 transaction 行为尚未真实验证。

## 32. pip check

`No broken requirements found.` 本地 pip cache 权限 warning 不影响依赖完整性。

## 33. compileall

通过，无编译错误。

## 34. Ruff

本阶段全部新增/修改文件：`All checks passed!`

## 35. W4.2 focused tests

`tests/test_week4_persistence.py`: 44 passed。

## 36. W4.1 regression

Conflict unit + NVDA + QQQ：164 passed。

## 37. Week 3 persistence regression

Graph persistence + graph API + Week 3 security：78 passed，1 个既有 deprecation warning。

## 38. Key Week 1–3 regression

Week 1A gate、alpha loader、graph builder、activation scorer、research validation：
85 passed，1 个既有 deprecation warning。

## 39. Full offline regression

`1011 passed, 1 skipped, 17 deselected, 17 warnings, 69 subtests passed`。
相较 W4.1 基线净增 44 个 offline tests；新增 9 个 PostgreSQL tests 被 integration
marker 排除。既有 skip 仍是缺少可选 `langchain_aws`。

## 40. Known limitations

PostgreSQL 未验证；W4.2 尚未接入 pipeline/API；无 authentication/tenant ownership；
当前能力不是 production-ready。Conflict payload 保留 W4.1 已批准的 evidence 文本，
但 audit 不复制 evidence，未知字段无法进入 JSON columns。

## 41. Files intentionally untouched

未修改 `conflict_engine/`、`graph_engine/`、`structure_engine/`、`alpha_library/`、
`api/`、`routes_research.py`、`tradingagents/`、taxonomy YAML、NVDA/QQQ fixture、
W4.1 tests/docs、`.env` 和 `docker-compose.yml`。

## 42. Final verdict

- W4.2 Schema: PASS
- W4.2 Migration 0002: PASS
- W4.2 Activation Persistence: PASS
- W4.2 Conflict Persistence: PASS
- W4.2 Evidence Audit Persistence: PASS
- W4.2 Transaction Atomicity: PASS
- W4.2 Deterministic Reconstruction: PASS
- W4.2 SQLite Persistence: PASS
- W4.2 PostgreSQL Integration: UNVERIFIED
- MSFT Golden Gate: BLOCKED_BY_SPEC_CONFLICT
- Exposure Engine: BLOCKED_BY_SEED
- Research API: NOT STARTED
- W4.2 Overall: BLOCKED_BY_POSTGRESQL_VERIFICATION
- W4.3 API Entry: NOT READY

## 43. git diff --stat

Tracked diff before this untracked report: 2 files changed, 166 insertions, 3 deletions.
New implementation/tests/report remain untracked and therefore are not included by plain
`git diff --stat` until staged.

## 44. git status --short

Expected final worktree contains two modified DB files and four new W4.2 files. No staged files,
commit or push.

---

## W4.2 Correctness Patch（2026-07-14）

历史记录，不抹去问题：初始 W4.2 实现（第 1–44 节）为 activation 和 conflict
两个 payload 分别做了内部自洽性校验，但从未验证两者属于*同一次*计算——一个
admitted conflict row 内嵌的 activation 快照（`components.activation_a/b`、
`bull_structure`/`bear_structure`）理论上可以和同一次调用里实际持久化的
activation rows 互相矛盾而不被发现。同时，activation component 的 whitelist
只校验了一级字段名（五个 component 共享一套字段名集合），未对字段值做类型/
范围校验，且未按 component 区分允许字段——严格来说都不是"递归"的（见第 6
节的修正）。本补丁关闭这两个缺口，并补充 candidate reason-code 完整性校验
和 PostgreSQL 验证测试的 fail-loud gate。

### 1. Cross-Payload Snapshot Validation

新增纯函数 `_validate_week4_snapshot(activation_rows, conflict_rows)`，在
`build_week4_rows()` 构造完两组 canonical rows 之后、返回之前调用（因此发生
在 `persist_week4_results()` 打开数据库 transaction 之前）。不访问数据库，
不修改传入的 rows。对每一个 `outcome == "admitted"` 的 conflict row 验证：

- `alpha_a`/`alpha_b` 必须都存在于由 activation rows 构造的
  `activation_by_alpha_id` 索引中；
- `components.activation_a`/`activation_b` 必须等于对应 activation row 的
  `activation_score`；`components.minimum_activation` 必须等于两者的 `min()`；
- `bull_alpha_id`/`bear_alpha_id` 必须都能在 activation 索引中找到；
- `bull_structure`/`bear_structure` 的 `alpha_id`/`alpha_name`/
  `activation_score`/`status`/`direction` 必须与对应 activation row 逐字段
  相等，且 `bull_structure.direction == "positive"`、
  `bear_structure.direction == "negative"`；
- `{bull_alpha_id, bear_alpha_id} == {alpha_a, alpha_b}`。

任一条件不满足抛出 `Week4PersistenceDataError(WEEK4_CONFLICT_DATA_INCONSISTENT)`，
经 repository 转换为 `GraphPersistenceError("WEEK4_CONFLICT_DATA_INCONSISTENT")`。
不重新决定 `contradiction_weight`/`evidence_strength`/`conflict_score`/排序——
这些继续完全信任 W4.1 Conflict Detector 的输出，本函数只做交叉一致性检查。

### 2. Per-Component Typed Recursive Whitelist

`_whitelist_activation_components()` 不再对五个 component 使用同一个扁平
字段名集合；改为按 component 名称分派到五个独立的 `_whitelist_<name>()`
函数（`matched_evidence`/`agent_agreement`/`graph_coherence`/`recency`/
`direction_strength`），每个函数只接受该 component 官方定义的字段，并对每个
字段值做类型/范围校验（复用/新增 `_number`/`_positive_number`/
`_nonnegative_number`/`_integer`/`_positive_integer`/`_optional_integer`/
`_bool`/`_text`/`_agents_list` 等强类型 helper）。`raw`/`weight`/`contribution`
三个公共字段（`[0,100]`/`[0,1]`/`[0,100]`）对全部五个 component 一致。

关键区别：数值字段拒绝 `bool`（Python 的 `True`/`False` 是 `int` 子类，之前
的 `_integer`/`_number` 已经显式排除，本次未改变这一行为，只是现在更多字段
真正被校验到）、拒绝 NaN/Infinity、拒绝嵌套 `dict`/`list`；`bool` 字段拒绝
字符串 `"true"`；`agent_agreement.agents` 校验为 `list[非空 str]` 后按
`sorted(set(...))` 归一化，不依赖原始输入顺序。未知 component 整体丢弃；
已知 component 内未知字段逐一丢弃；已知字段类型错误使整个持久化请求失败
（`WEEK4_ACTIVATION_PAYLOAD_INVALID`），不会"尽量保留能保留的部分"。

### 3. Candidate Reason-Code Contract

`_whitelist_candidate()` 新增：`admitted` 的 `reason_codes` 必须为空（已有）；
`suppressed`/`rejected` 的 `reason_codes` 必须至少一项（新增）；同一 candidate
的 `reason_codes` 不允许重复（新增）；每个 reason code 必须是非空字符串
（新增）。`_whitelist_audit_side()` 新增：`qualifying_claim_ids` 每项必须
非空字符串、且列表内不允许重复（新增；排序性校验已有）。

### 4. PostgreSQL 验证测试不再对"已配置但错误"静默 skip

`tests/test_week4_postgres_persistence.py::postgres_context`：只有
`COMQUTOR_TEST_DATABASE_URL` 完全未设置时才 `pytest.skip`。一旦设置了值，
以下任一情况改为 `pytest.fail`（不再是 skip）：DSN scheme 不是
`postgresql://`/`postgresql+psycopg://`；驱动缺失（`ImportError`）；数据库
不可连接。失败消息固定为不含 DSN/host/用户名/密码/原始 driver 异常文本的
安全字符串。本次用三个合成场景直接验证了这三条 fail 路径（非法 scheme、
`postgresql://`裸 scheme 因为本环境未装 `psycopg2`/`psycopg2-binary` 触发
驱动缺失、`postgresql+psycopg://`指向不可达地址触发不可达），均正确
`pytest.fail` 而非静默通过或 skip；未设置 DSN 时仍正确 `pytest.skip`。

### 5. PostgreSQL Migration Reapply Test

新增 `test_migration_reapply_is_idempotent_and_records_0002_exactly_once`：
对已迁移的共享 integration 数据库再次调用 `apply_migrations(engine)`，断言
返回空列表，且 `schema_migrations` 中 `0002` 版本行数恰好为 1。不删除
migration 行、不 drop/truncate 任何表。

### 6. 新增测试数量与结果

`tests/test_week4_persistence.py`：新增 24 个（原 44 个全部保留、未削弱），
分三个测试类：`TestCrossPayloadSnapshotIntegrity`（10 个，覆盖 activation
score/name/status/direction 错配、bull/bear 方向错误、admitted conflict
缺失一侧 activation、相同 identity 但快照不同、validation 保留旧状态、
validation 发生在任何 SQL 执行之前）、`TestTypedRecursiveActivationWhitelist`
（10 个，覆盖 `recency.reason`/`agents`/`graph_coherence.scope` 嵌套 dict、
bool 字段传字符串、numeric 字段传嵌套对象、integer 字段传 bool、
`age_days`传 NaN、`average_signed_strength`传 list、`saturation`必须为正、
真实 Week 3 NVDA activation components 完整 round trip）、
`TestCandidateReasonCodeContract`（4 个，覆盖 suppressed/rejected 空
reason_codes、重复 reason code、重复 qualifying_claim_id）。
`tests/test_week4_postgres_persistence.py`：新增 1 个（migration reapply）。

全部新增测试首次运行即通过（未出现"写测试时预期失败但被迫放宽实现"的情况）。

### 7. 重新运行的结果

- W4.2 focused (`tests/test_week4_persistence.py`)：**68 passed**（原 44 +
  新增 24）。
- W4.1 regression（conflict detector + NVDA + QQQ）：**164 passed**，与补丁前
  完全一致，无回归。
- Week 3 persistence regression（graph persistence + graph API + Week 3
  security hardening）：**78 passed**，与补丁前完全一致。
- Key Week 1–3 regression（Week1A gate、alpha loader、graph builder、
  activation scorer、research input validation）：**85 passed**，与补丁前
  完全一致。
- PostgreSQL profile（`-m integration`）：**10 skipped**（原 9 个 + 新增的
  migration reapply 测试 1 个），`COMQUTOR_TEST_DATABASE_URL` 未配置，
  誠实 skip，未伪造通过；额外用三个合成 DSN 场景手动验证了 fail-loud 路径
  （见上）。
- 完整 offline suite：**1035 passed, 1 skipped, 18 deselected**（补丁前
  1011 passed, 1 skipped, 17 deselected；净增 24 个 offline 测试，
  deselected 净增 1 个新的 integration-marked 测试，与预期完全对应）。

### 8. 更新后的最终 verdict

```
W4.2 Snapshot Integrity: PASS
W4.2 Recursive Whitelist: PASS
W4.2 Candidate Contract: PASS
W4.2 SQLite Persistence: PASS
W4.2 PostgreSQL Integration: UNVERIFIED
W4.2 Correctness Patch: PASS
W4.2 Overall: BLOCKED_BY_POSTGRESQL_VERIFICATION
W4.3 API Entry: NOT READY
```

PostgreSQL 依然只是"未验证"（无可达服务器、且本地环境未安装
`psycopg2`/`psycopg2-binary`，只有 `psycopg` v3 可用），不是"已验证失败"，
也不是伪造的"已验证通过"。
