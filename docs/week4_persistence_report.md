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

新增 Week 4 两表、0002 migration、activation/conflict validation、递归 whitelist、
原子 replace、确定性读取与重建、SQLite tests 和 PostgreSQL integration profile。

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
