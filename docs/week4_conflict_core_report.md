# Week 4 Conflict Core Completion Report (W4.1)

审查日期：2026-07-14

本文档报告 W4.1 — Deterministic Conflict Core 的实施结果。范围严格限定于
纯确定性的 Conflict Detector、其数据契约和测试；不包含数据库新表、
migration、新 API endpoint、Exposure Engine、Dashboard 或 Alpha Memory。
所有规则均来自 `docs/week4_spec_freeze_audit.md` 中标注为
**APPROVED — SPEC-FROZEN FOR W4.1** 的条目，本次实施未新增任何未经批准的
业务规则。

第 1–35 节保留初始 W4.1 实施时的历史快照；当前实现状态和最新验证结果
以文末 `W4.1 Correctness Patch` 为准。历史问题不回写成“从未发生”。

---

## 1. Current branch / HEAD（只记录，未进行任何 branch 操作）

- `git branch --show-current`: `comqutor-structure-layer`
- `git rev-parse HEAD`: `0c7d7c24be8b2996a9b08b5306b59c14b778ce03`（实施全程未变）
- `git log -1 --oneline`: `0c7d7c2 w4v1`

本次实施**未**创建、切换、合并、删除任何 branch，**未**修改任何 branch ref。

## 2. Starting worktree

`git status --short` 在实施开始前为空（clean）。

## 3. Pre-existing changes

无。开始前工作树完全干净，不存在任何需要保留或标记为 pre-existing 的
未提交/未追踪修改（包括 `docs/week4_spec_freeze_audit.md` 本身——它在
开始前已经通过 `w4v1` 提交，不是未提交状态）。

## 4. Files changed by W4.1

全部为**新增**文件，**没有修改任何既有文件**：

```
comqutor_alpha/conflict_engine/__init__.py
comqutor_alpha/conflict_engine/conflict_schema.py
comqutor_alpha/conflict_engine/conflict_detector.py
tests/fixtures/week4_conflict_cases.py
tests/test_conflict_detector.py
tests/test_week4_nvda_conflict_sanity.py
tests/test_week4_qqq_conflict_sanity.py
docs/week4_conflict_core_report.md（本文档）
```

`tradingagents/`、`comqutor_alpha/api/`、`comqutor_alpha/storage/db/`、
Week 2 mapper/extractor、Week 3 graph builder/activation scorer、
alpha taxonomy YAML、既有 golden label 文件、`docs/week4_spec_freeze_audit.md`
均未被本次实施触碰——见第 32 节完整清单。

## 5. Scope implemented

1. deterministic conflict data schema（`conflict_schema.py`）
2. taxonomy-declared conflict pair enumeration（`_enumerate_canonical_pairs`）
3. 双向 taxonomy declaration 去重（canonical pair key 折算）
4. qualifying committed evidence 筛选（`_gather_qualifying_evidence`）
5. evidence-strength 计算（每侧均值再双方均值，0–1 尺度）
6. conflict candidate admissibility（11 项条件全部实现）
7. admitted / suppressed / rejected 分类（`_classify_outcome`）
8. 稳定 reason codes（18 个候选级 + 3 个顶层输入完整性级 + 7 个证据排除级）
9. bull/bear semantic role resolution（`resolve_bull_bear`，仅依据 direction）
10. Conflict Score（官方公式，复用 `graph_schema.clamp_percent`）
11. Conflict Level（`[0,25]`/`(25,50]`/`(50,75]`/`(75,100]`）
12. deterministic main-conflict arbitration（4 级排序）
13. no-conflict contract（`conflicts=[]`/`main_conflict=null`）
14. deterministic explanation（模板生成，语言守卫）
15. NVDA offline conflict sanity（10 项测试，复用真实 Week 1-3 pipeline）
16. QQQ offline conflict sanity（9 项测试，复用真实 Week 3 QQQ fixture）
17. MSFT blocked boundary test（5 项测试）
18. 完整 Week 0–3 regression（见第 20/21 节）

## 6. Scope explicitly deferred

`alpha_activations` 数据库表、`alpha_conflicts` 数据库表、migration
`0002`、database persistence、`/api/research/{run_id}/conflicts`、
`/api/research/{run_id}/agent-outputs`、`/api/research` 新增
summary/main_conflict 字段、Exposure Engine、
`entity_alpha_exposure_seed.yaml`、MSFT A102-A304 规格修复、Dashboard、
frontend、authentication、tenant ownership、跨 run feedback、Alpha
Memory、完整 phi-token lifecycle、portfolio construction、broker
integration、backtesting、Neo4j——**均未实施**。

## 7. Input contract

`detect_alpha_conflicts(*, run_id, ticker, activation_payload,
alpha_matches, taxonomy=None)`：

- `activation_payload`：Week 3 `score_alpha_activations()` 返回形状
  （即 `structure_graph.json` 的 `activation` 键：
  `{"formula_version", "weights", "run_timestamp", "as_of", "alphas": [...]}`）。
- `alpha_matches`：Week 2 `alpha_matches.json` 的 `matches` 列表（原始
  JSON artifact 形状，与 `activation_scorer._gather_alpha_evidence` 消费
  的是同一形状，不是数据库行形状）。
- `taxonomy`：默认调用 `load_alpha_taxonomy()`，与 Week 3 使用同一份
  loader，不接受自定义硬编码权重表。

纯函数：无文件系统、无数据库、无环境变量、无网络、无随机性、无当前时间
依赖（`tests/test_conflict_detector.py::TestDeterminism::
test_no_wall_clock_or_random_dependence_in_source` 静态扫描源码验证）。

**顶层结构性违规**（空 `run_id`/`ticker`、非 mapping 的
`activation_payload`、activation formula version 不匹配、`alphas` 不是
list、`alpha_matches` 不是 Sequence、activation 中存在重复或 taxonomy
未知 `alpha_id`、同一 `claim_id` 的记录存在语义冲突）抛出
`ConflictInputError(reason_code)`——只携带稳定 reason_code，不携带原始
异常文本。**单个候选或单条证据的问题**（缺失、不合格、非法数值）不抛异常，
在返回结果中以 `suppressed`/`rejected` 优雅呈现。

## 8. Taxonomy pair enumeration

`_enumerate_canonical_pairs()` 直接从 `load_alpha_taxonomy()` 的真实返回
（`alpha_id -> AlphaDefinition`，`AlphaDefinition.conflict_alphas: list[
ConflictAlpha]`）读取，从不复制硬编码权重表。每组合法 pair 必须有且仅有
一条 `A→B` 和一条 `B→A` 声明，且两侧 weight 完全相等。单向声明、双向
weight 不一致和同向重复声明分别以稳定 reason code 拒绝，不使用 min、max、
平均值或 first-seen 修复。当前六组 mandatory pairs：

| Pair | contradiction_weight |
|---|---:|
| A101 ↔ A304 | 0.90 |
| A301 ↔ A304 | 0.85 |
| A001 ↔ A501 | 0.85 |
| A003 ↔ A501 | 0.85 |
| A601 ↔ A304 | 0.80 |
| A601 ↔ A501 | 0.80 |

默认真实 taxonomy 的 `declared_pair_count` 为 6；显式 `taxonomy={}` 时为
0，且不会回退到默认 taxonomy。A102-A304 因 taxonomy 未声明而永不出现
（`TestMSFTBoundary` 系列测试专门锁定这一点）。额外新增
`DUPLICATE_PAIR` 防御逻辑：如果一个 canonical pair 被超过两条有向声明
（例如损坏的 taxonomy 数据）折算出来，该候选会被明确 `rejected`，而不是
静默去重。

## 9. Canonical relation resolution

直接 `import` Week 3 的 `activation_scorer._relation_for_match`（私有名
按原样导入，未复制其逻辑，未重新发明另一套解释）。该函数依次检查
`eligible_candidates`/`top_candidates`/`candidate_scores` 三个候选池
字段名（当前仓库实际数据使用 `candidate_scores`），返回归一化后的
`relation` 字符串。qualifying relations 固定为
`{"activation", "conditional", "mixed"}`——Week 4 自己的冻结常量（不是
从 Week 3 内部字典派生），并有一条一致性 canary 测试
（`test_qualifying_relations_constant_matches_current_week3_positive_weights`）
验证它与 Week 3 当前正权重 relation 集合一致，充当未来漂移的警报而非
硬绑定。

## 10. Evidence-strength implementation

```
strength_A = mean(A 方 qualifying committed claims 的 match_score)
strength_B = mean(B 方 qualifying committed claims 的 match_score)
evidence_strength = (strength_A + strength_B) / 2
```

Qualifying committed evidence 必须同时满足：`match_status == "matched"`、
committed alpha_id 等于当前一侧、`claim_id` 非空且同侧去重、evidence 非空、
relation ∈ `{activation, conditional, mixed}`。`match_score` 参与聚合前
先用 `is_finite_number` 拒绝非有限值（排除，不计入），再用复用的
`graph_schema.clamp_percent(value, 0, 1)` 防御性 clamp——不修改原始
artifact，只影响本次计算用的本地副本。最终尺度固定 0.0–1.0。

排除审计（`excluded` 列表，未进入 committed 集合但曾与该 Alpha 相关的
claim）区分 7 种 reason：`NON_COMMITTED_MATCH`、`WRONG_ALPHA`、
`MISSING_CLAIM_ID`、`DUPLICATE_CLAIM`、`EMPTY_EVIDENCE`、
`UNSUPPORTED_RELATION`、`INVALID_MATCH_SCORE`。初始实现只在内部计算这些
记录，却没有放入 `candidate_evaluations`；Correctness Patch 已将其作为
每个 admitted/suppressed/rejected candidate 的 `evidence_audit` 输出。

## 11. Admissibility rules

一个候选进入 `conflicts[]` 必须同时满足：(1) taxonomy 正式声明；
(2) 双侧 activation entry 存在；(3) 双侧 `status` 至少 `watch`；
(4) 双侧至少一条 qualifying committed evidence；(5) `evidence_strength >
0`；(6) `contradiction_weight` finite 且在 `[0,1]`；(7) 双侧
`activation_score` finite 且在 `[0,100]`；(8)/(9) 无 run_id/ticker
mismatch；(10) schema 合法；(11) bull/bear role 可稳定确定。全部十一项
均已实现并测试覆盖（`TestAdmissibility`/`TestDirectionRoleResolution`/
`TestInputValidation` 三个测试类）。

## 12. Candidate outcomes

`admitted` / `suppressed` / `rejected` 三态，本阶段不使用运行时
`deferred`。分类规则：`REJECTED_CLASS_REASONS`（`MISSING_LEFT/RIGHT_
ACTIVATION`、`INVALID_CONTRADICTION_WEIGHT`、`INVALID_ACTIVATION_SCORE`、
`NON_FINITE_SCORE_COMPONENT`、`RUN_ID_MISMATCH`、`TICKER_MISMATCH`、
`SCHEMA_INVALID`、`DIRECTION_ROLE_UNRESOLVED`、`DUPLICATE_PAIR`、
`MISSING_RECIPROCAL_DECLARATION`、`ASYMMETRIC_CONTRADICTION_WEIGHT`、
`PAIR_NOT_DECLARED`）中任一 reason 出现即为 `rejected`，其余非空
reason 集合归为 `suppressed`，reason 集合为空则 `admitted`。

## 13. Reason codes

候选级 18 个（含 Correctness Patch 新增的 reciprocal/asymmetric codes，
以及仅通过可选 single-pair helper 触达的 `PAIR_NOT_DECLARED`）：
`MISSING_LEFT_ACTIVATION`、`MISSING_RIGHT_ACTIVATION`、
`BELOW_ACTIVATION_THRESHOLD`、`MISSING_LEFT_EVIDENCE`、
`MISSING_RIGHT_EVIDENCE`、`AMBIGUOUS_ONLY`、`ZERO_EVIDENCE_STRENGTH`、
`INVALID_CONTRADICTION_WEIGHT`、`INVALID_ACTIVATION_SCORE`、
`NON_FINITE_SCORE_COMPONENT`、`RUN_ID_MISMATCH`、`TICKER_MISMATCH`、
`SCHEMA_INVALID`、`DIRECTION_ROLE_UNRESOLVED`、`DUPLICATE_PAIR`、
`MISSING_RECIPROCAL_DECLARATION`、`ASYMMETRIC_CONTRADICTION_WEIGHT`、
`PAIR_NOT_DECLARED`。同一 candidate 多个 reason 时去重且保持稳定顺序
（`dedupe_stable`，先出现先保留，不依赖发现顺序之外的任何排序，因为
所有条件按固定代码顺序依次评估）。Reason code 输出经测试确认不包含
原始异常文本、traceback、本地路径（`test_reason_codes_never_contain_
raw_exception_or_path_text`）。

`AMBIGUOUS_ONLY` 与 `MISSING_LEFT/RIGHT_EVIDENCE` 的区分：前者要求该侧
没有 qualifying evidence、至少有一条相关排除记录，且所有相关记录均为
`match_status == "ambiguous"`。ambiguous 与 `no_match`、wrong-alpha、
unsupported relation、empty evidence 或 invalid score 混合时，使用
`MISSING_LEFT/RIGHT_EVIDENCE`，具体原因由 `evidence_audit` 展示。

## 14. Bull/Bear role resolution

`resolve_bull_bear(alpha_a, direction_a, alpha_b, direction_b)`：角色
只依据双方 Week 3 `direction` 字段（`positive`→bull，`negative`→bear），
与 canonical 排序、alpha_id、ticker 完全无关。两侧同为 positive/negative、
任一侧 unknown/缺失/非法，均返回 `(None, None)`，候选被 `rejected`，
reason `DIRECTION_ROLE_UNRESOLVED`。测试专门验证了"A304 在字典序中排在
A101 之后但方向为 positive"这种反直觉场景，确认角色不受 canonical
顺序影响（`test_negative_positive_resolves_bull_bear_correctly_not_by_
dict_order`）。

## 15. Conflict formula

```
minimum_activation = min(activation_A, activation_B)
conflict_score = minimum_activation × contradiction_weight × evidence_strength
```

非法输入（非 finite/超范围的 activation 或 weight）在计算前已经被
admissibility 拒绝，不会进入乘法；`evidence_strength <= 0` 同样提前
suppressed。最终 score 仍用复用的 `graph_schema.clamp_percent` 做防御性
`[0,100]` clamp（4 位小数）。Component breakdown 完整输出
`activation_a`/`activation_b`/`minimum_activation`/
`contradiction_weight`/`alpha_a_evidence_strength`/
`alpha_b_evidence_strength`/`evidence_strength`。排序（main-conflict
tie-break）使用未 round 的原始值，显示 rounding 不影响排序结果
（`test_rounding_does_not_change_main_conflict_ranking`）。

## 16. Conflict-level boundaries

`[0,25]` low / `(25,50]` medium / `(50,75]` medium_high / `(75,100]`
high——`conflict_schema.conflict_level()` 独立、可直接单测的公开函数，
8 个边界值（0/25/25.0001/50/50.0001/75/75.0001/100）全部测试覆盖，
非法/非 finite 输入不会抛异常（先经复用的 `clamp_percent` 钳制）。与
Week 3 `activation_status_band` 的命名空间完全独立，不复用其状态名。

## 17. Output schema

顶层：`schema_version`（`"week4.alpha_conflicts.v1"`）、
`formula_version`（`"week4.conflict_score.mvp_v1"`）、`run_id`、
`ticker`、`conflicts`（已按 arbitration 顺序稳定排序的列表）、
`main_conflict`（`conflicts[0]` 或 `null`）、`arbitration`
（`declared_pair_count`/`admitted_count`/`suppressed_count`/
`rejected_count`/`candidate_evaluations`）。每个 admitted conflict 含
`conflict_id`、`alpha_a`/`alpha_b`、`bull_alpha_id`/`bear_alpha_id`、
`bull_structure`/`bear_structure`（各含 `claim_ids`/
`source_agent_output_ids`/`agents`/`evidence`/`match_scores`，均已排序）、
`components`、`conflict_score`、`conflict_level`、`reason_codes`（admitted
恒为空列表）、`explanation`。每个 candidate audit item 均含
`alpha_a`/`alpha_b`/`outcome`/`reason_codes`/`evidence_audit`；audit 只保存
排序后的 claim ID 和稳定 exclusion reason，不复制 evidence 原文或内部异常。

## 18. Main-conflict arbitration

只在 admitted conflicts 内选择，四级排序：`conflict_score` 降序 →
`evidence_strength` 降序 → `minimum_activation` 降序 → canonical
conflict ID 升序。`conflicts` 列表本身即最终排序输出（不是偶然的
taxonomy 遍历顺序）。测试验证了完全打平场景下 canonical ID 决定胜负
（`test_tie_break_uses_canonical_pair_id_ascending`），以及排序不受
display rounding 影响。无 admitted 候选时 `conflicts=[]`/
`main_conflict=null`，不会从 suppressed/rejected 候选中补位
（`test_arbitration_does_not_backfill_from_suppressed_or_rejected`）。

## 19. Determinism guarantees

- taxonomy A→B/B→A 折算为一个 candidate（第 8 节）。
- `alpha_matches` 在 evidence qualification 前按规范化 `claim_id` 全局分组；
  exact duplicate 选择稳定 canonical representative 并只计一次，语义冲突
  duplicate 则安全抛出 `DUPLICATE_CLAIM_CONFLICT`。
- `alpha_matches`/`activation_payload["alphas"]`/`taxonomy` 输入顺序
  变化不影响结果（三条独立测试，逐字节比较 `json.dumps(..., sort_keys=
  True)` 输出）。
- 重复执行产生完全相同的序列化结果。
- 所有 claim_ids/agents/source_agent_output_ids 等集合在输出前显式排序。
- 源码静态扫描确认不出现 `datetime.now`/`time.time(`/`uuid.uuid4`/
  `random.`/`os.urandom`。
- 同分 main_conflict 用 canonical pair ID 稳定打破平局。

## 20. NVDA result

`tests/test_week4_nvda_conflict_sanity.py`：复用
`test_week3_nvda_sanity._nvda_offline_outputs()`（未修改），跑真实
Week 1-3 离线 pipeline 得到真实 `alpha_matches`/`activation`，喂给
Conflict Detector。**10/10 通过**：A101/A304 均有 qualifying committed
evidence；A101-A304 是 taxonomy-declared 且 `admitted`；双侧 status
（`dominant`/`watch`）均 ≥ watch；bull=A101(positive)/bear=A304
(negative)；component breakdown 完整（`contradiction_weight == 0.90`）；
`conflict_score` 在 `[0,100]`，level 与公式一致；**main_conflict 就是
A101-A304**；explanation 无裸交易建议；生产代码无 `"NVDA"` 字面量分支；
结果可 JSON 序列化。

## 21. QQQ result

`tests/test_week4_qqq_conflict_sanity.py`：复用
`test_week3_qqq_sanity._SYNTHETIC_QQQ_OFFLINE_OUTPUTS`（未修改，仍明确
标注合成数据）。**9/9 通过**：A001-A501 与 A003-A501 均产生 admitted
conflict 且都保留在 `conflicts` 中；A501 在两组中都是 bear side
（negative），A001/A003 都是 bull side（positive）；main_conflict 由
真实公式排序决定（实测为 `A003__A501`，score ≈44.94 > `A001__A501`
≈37.87，由数据决定，生产代码中未出现 `"QQQ"` 字面量分支/未硬编码哪组
获胜）；component breakdown 与 evidence 可追踪；explanation 无裸交易
建议。

## 22. MSFT blocked status

`TestMSFTBoundary`（`tests/test_conflict_detector.py`，5 项测试）：确认
真实 taxonomy 中 A102/A304 互不在对方 `conflict_alphas` 中；真实 loader
枚举结果中不存在该 pair（`declared_pair_count` 恒为 6）；即使人为构造
双方都有强证据的 activation/matches，detector 仍不会生成
`A102__A304`/`A304__A102`；可选单 pair helper 对该 pair 返回
`PAIR_NOT_DECLARED`/`rejected`；`docs/week4_spec_freeze_audit.md` 仍
包含 `BLOCKED_BY_SPEC_CONFLICT` 与 `MSFT` 字样（doc-content 断言，防止
未来误改）。**MSFT Golden Case 本身未实施、未伪造通过。**

## 23. Security boundaries

- 不读取/解析原始 TradingAgents 报告、`complete_report.md`、prompt、
  LLM/provider response——只消费 `activation_payload`/`alpha_matches`/
  `taxonomy` 三个结构化边界（源码不 import 任何 raw-text 读取路径）。
- `ConflictInputError`/reason codes 只携带稳定字符串，不携带原始异常
  文本、traceback、本地路径（测试断言）。
- 无文件系统、无数据库、无网络、无环境变量读取（源码审查 + 静态
  determinism 测试）。
- 未新增/修改任何 API endpoint、未写数据库、未修改 `.env`、未运行会
  展开环境变量的 `docker compose config`。

## 24. `pip check`

```
No broken requirements found.
```

## 25. Compileall

```
.venv/bin/python -m compileall comqutor_alpha/conflict_engine \
  tests/test_conflict_detector.py tests/test_week4_nvda_conflict_sanity.py \
  tests/test_week4_qqq_conflict_sanity.py tests/fixtures/week4_conflict_cases.py
```
干净通过，无编译错误。

## 26. Ruff

对本次新增的全部文件运行 `ruff check`：首次运行发现 6 处（import 排序
×4、未使用的 `math` 导入 ×1、Yoda condition ×1），全部通过
`ruff check --fix` 自动修复（均是本次新文件内的机械/风格修正，未涉及
任何既有文件）。修复后重新运行：

```
All checks passed!
```

## 27. Focused tests

```
tests/test_conflict_detector.py .......................... 113 passed
tests/test_week4_nvda_conflict_sanity.py .................. 10 passed
tests/test_week4_qqq_conflict_sanity.py ................... 9 passed
```
合计 **132 passed**，0 failed，0 skipped。

## 28. Key regressions

```
tests/test_week1a_gate.py
tests/test_alpha_loader.py
tests/test_graph_builder.py
tests/test_activation_scorer.py
tests/test_graph_api.py
tests/test_graph_persistence.py
tests/test_week3_security_hardening.py
tests/test_research_input_validation.py
```
**163 passed**，0 failed。与 W4.1 实施前完全一致，无回归。

## 29. Full offline regression

```
python -m pytest -m "not integration" -q
935 passed, 1 skipped, 8 deselected
```

对比 W4.1 实施前基线（803 passed, 1 skipped, 8 deselected）：净增 132
（113+10+9，与第 27 节 focused 数字完全对应），无一失败，无回归。1
skipped 为既有的 `test_bedrock_provider.py`（`langchain_aws` 未安装，
与本次改动无关，实施前后一致）。

## 30. PostgreSQL status

**UNVERIFIED**——本阶段不修改数据库，未要求验证。确认
`COMQUTOR_TEST_DATABASE_URL` 未设置、本地无 postgres docker 镜像，与
之前所有会话状态一致，未伪造通过。

## 31. Known limitations

1. `_relation_for_match` 是 Week 3 的私有（下划线前缀）函数，本次按
   任务明确指示直接 import 而非复制；这在 Python 语言层面没有强制的
   跨模块私有性保护，但如果 Week 3 未来重命名或删除该函数而不保留
   兼容签名，Week 4 会直接 `ImportError`——这是一个已知的、有意接受的
   紧耦合，优于复制一份可能漂移的同义实现。
2. `evaluate_conflict_pair`（可选单 pair helper）覆盖了
   `PAIR_NOT_DECLARED` 这一在主枚举流程中天然不可达的 reason code；
   它不是 `/conflicts` 端点的一部分（该端点本身也未实施），目前只是
   detector 模块自身导出的一个便利函数。
3. `DUPLICATE_PAIR` 只在人为构造的损坏 taxonomy fixture 下触发；真实
   冻结 taxonomy 从未产生这个 reason code，目前是纯防御性代码路径。
4. `RUN_ID_MISMATCH`/`TICKER_MISMATCH` 的判定依赖
   `activation_payload`/`alpha_matches` 记录**是否恰好携带**内嵌的
   `run_id`/`ticker` 字段；当前真实 Week 2/3 JSON artifact 形状不携带
   这些字段（只有外层 payload 才有），所以这条路径在真实离线 pipeline
   中天然不会触发，只通过合成输入测试验证。这不是缺陷——是对"调用方
   传入了跨 run 混合数据"这一情形的防御性检测，其设计前提就是"多数
   真实调用不会触发它"。
5. 本报告的 NVDA/QQQ 结果（例如 QQQ 的 main_conflict 具体是哪一组）
   依赖当前 fixture 的具体数值，不是产品承诺的市场结论，且与 Week 3
   sanity 测试一样，是结构一致性诊断，不是投资建议。

## 32. Files intentionally untouched

`tradingagents/`、`comqutor_alpha/api/`（含 `routes_research.py`）、
`comqutor_alpha/storage/db/`（`schema.py`/`migrations.py`/
`repository.py`/`engine.py`）、
`comqutor_alpha/structure_engine/`（Week 2 mapper/extractor）、
`comqutor_alpha/graph_engine/`（Week 3 graph builder/activation
scorer/graph schema——仅被 import，未被修改）、
`comqutor_alpha/alpha_library/alpha_taxonomy_v1.yaml`（及 `alpha_
schema.py`/`alpha_loader.py`——仅被 import）、既有 golden label 文件、
`docs/week4_spec_freeze_audit.md`、`.env`、`docker-compose.yml`、
任何既有测试文件。

## 33. Final W4.1 verdict

```
W4.1 Conflict Schema: PASS
W4.1 Conflict Detector: PASS
W4.1 Evidence Strength: PASS
W4.1 Admissibility: PASS
W4.1 Bull/Bear Resolution: PASS
W4.1 Main-Conflict Arbitration: PASS
W4.1 NVDA Gate: PASS
W4.1 QQQ Gate: PASS
MSFT Golden Gate: BLOCKED_BY_SPEC_CONFLICT
Exposure Engine: BLOCKED_BY_SEED
Database/API Integration: NOT STARTED
PostgreSQL Integration: UNVERIFIED
W4.1 Overall: PASS
```

未夸大：Week 4 **未**全部完成；persistence **未**完成；API **未**完成；
Exposure Engine **未**完成；MSFT Gate **未**通过（明确 BLOCKED）；
**非** production-ready；PostgreSQL **未**验证。

## 34. `git diff --stat`

```
(empty — every change this session is a new/untracked file, not a
modification to a tracked file; `git diff` only shows tracked-file
changes)
```

## 35. `git status --short`

```
?? comqutor_alpha/conflict_engine/
?? tests/fixtures/
?? tests/test_conflict_detector.py
?? tests/test_week4_nvda_conflict_sanity.py
?? tests/test_week4_qqq_conflict_sanity.py
```

（`docs/week4_conflict_core_report.md` 本身在此次 `git status` 快照之后
写入，会作为第六个 `??` 条目出现——见最终回复中的确认。）未 commit，
未 push，未执行任何 branch 操作。

## W4.1 Correctness Patch

修复日期：2026-07-14。Patch 基于 `0f1edc917c0c09ed5d59ed191766a2d8d77113e4`
执行，未进行 branch 操作、commit 或 push。

1. 初始 duplicate claim 处理按输入先后选择 first-seen record，反转
   `alpha_matches` 可能改变 evidence 和 conflict score。
2. Patch 在 qualification 前按规范化 `claim_id` 全局分组。语义等价记录
   使用稳定排序选择 canonical representative，只计分一次；其余副本以
   `DUPLICATE_CLAIM` 进入 audit。
3. 同一 `claim_id` 在 status、matched Alpha、resolved relation、score、
   normalized evidence、source、agent 或候选关系语义上不一致时，安全抛出
   `ConflictInputError("DUPLICATE_CLAIM_CONFLICT")`，异常不带原始记录。
4. 初始实现 computed excluded records internally but did not expose them in
   `candidate_evaluations`。Patch 已为 admitted、suppressed、rejected 全部
   输出稳定的 `evidence_audit`，且不复制 evidence 原文。
5. taxonomy 不再通过 `min(weights)` 静默处理异常声明。合法 pair 要求
   双向各一次且 weight 完全一致。
6. 单向声明返回 `MISSING_RECIPROCAL_DECLARATION`；不对称 weight 返回
   `ASYMMETRIC_CONTRADICTION_WEIGHT`；同向重复返回 `DUPLICATE_PAIR`。
   dangling reference、self-conflict 和 key/alpha_id mismatch 安全拒绝。
7. `taxonomy is None` 才加载默认 taxonomy；显式空 mapping 返回 0 个 pair、
   空 conflicts 和 null main conflict。
8. activation payload 必须使用正式 `ACTIVATION_FORMULA_VERSION`；缺失或
   不匹配返回 `ACTIVATION_VERSION_MISMATCH`，taxonomy 未知 Alpha 返回
   `UNKNOWN_ACTIVATION_ALPHA`。partial activation 仍进入候选级缺侧判断。
9. `AMBIGUOUS_ONLY` 仅用于纯 ambiguous exclusion；混入 no-match、
   unsupported committed evidence 或其他排除原因时返回对应 `MISSING_*`。
10. rounding arbitration 测试现在断言公开 rounded score 相同、内部未舍入
    score 较高的唯一 pair 获胜，并验证 taxonomy、activation、matches
    反序后完整 JSON 不变。
11. 新增 32 个 correctness tests，覆盖 duplicate、全部七类 evidence
    exclusion、taxonomy、activation、ambiguous-only 和 rounding 边界。
12. 最新验证结果：`pip check` 通过；compileall 通过；Ruff 通过；focused
    `164 passed`；Week 1–3 关键回归 `163 passed`；完整 offline
    `967 passed, 1 skipped, 8 deselected`。NVDA 仍以 A101-A304 为 main
    conflict；QQQ 的 A001-A501 与 A003-A501 均 admitted；MSFT 仍为
    `BLOCKED_BY_SPEC_CONFLICT`。PostgreSQL Integration: UNVERIFIED。
