# Week 4 Spec Freeze and Repository Audit（W4.0）

审查日期：2026-07-14

本文档是 W4.0 阶段的唯一交付物：一次纯审计，不实现 Week 4 任何代码。
每条结论都标注下列四种分类之一：

- **SOURCE-FROZEN** — 三份正式文件（Development Plan v1.0 / Helix Quantum
  Intelligence Operating System White Paper v2.0 / SIC Omnibus Provisional
  Draft v2）已经明确规定，不得自行修改。
- **REPO-CONFIRMED** — 当前代码、taxonomy、schema 或测试已经确定（本次审计
  通过直接阅读源文件核实，不是转述任务说明）。
- **PROPOSED** — 工程推荐，尚未获得批准，不能写入正式规格或实现。
- **APPROVED — SPEC-FROZEN FOR W4.1** — 原本是 PROPOSED 的工程推荐，已在
  2026-07-14 的 W4.0 closure 指示中被规格负责人正式批准，自此视为 W4.1
  实现基线的一部分。**这不等同于 SOURCE-FROZEN**：三份正式文件本身并未
  规定这些细节，这是本次审计流程产生、经批准后补上的规格空白，标注
  APPROVED 是为了如实记录"何时、经由谁批准"，不得倒叙为三份原始文件
  "本来就规定了这个"。
- **BLOCKED** — 存在冲突或缺少正式输入，当前不能实施。

---

## 1. Executive Verdict

**本节已在 2026-07-14 W4.0 closure 指示后更新**（原始 W4.0 审计判定见
第 23 节末尾的历史记录）：

```
W4.0 Repository Audit: PASS
W4.0 Specification Freeze for Conflict Core: PASS
W4.1 Conflict Core Entry: READY
Exposure Engine Entry: BLOCKED_BY_SEED
MSFT Golden Gate: BLOCKED_BY_SPEC_CONFLICT
Week 4 Implementation: NOT STARTED
```

理由概述：taxonomy 中六组 mandatory conflict pairs 已经**完全、精确**声明
（双向、权重一致，见第 5、6 节），Week 3 提供的 activation/alpha_matches
字段已经足以支撑一个不重新解析原文的 Conflict Detector（见第 7 节）。
W4.0 审计原本识别出的四处规格空白——evidence_strength 聚合方式、canonical
pair 存储形式、admissibility threshold、main_conflict tie-break——已经
在本次 closure 指示中被规格负责人正式批准并 **SPEC-FROZEN FOR W4.1**
（见第 9、10、11、12 节，标注为 APPROVED），migration 命名与
`/agent-outputs` 默认暴露范围同样已批准（见第 14 节）。因此 Conflict
Core 的 Specification Freeze 现在判 **PASS**，W4.1 Conflict Core Entry
判 **READY**。Exposure Engine 所需的 seed 文件依然不存在（见第 13 节），
Golden Case 中 MSFT 要求的 A102-A304 关系依然不在 taxonomy 的六组
mandatory pairs 中、也未以任何形式声明（见第 16 节）——这两项不属于本次
closure 的批准范围，继续保持 BLOCKED。Week 4 代码实现依然是 NOT STARTED
——本次 closure 与 W4.0 审计一样，只更新规格文档，不写任何 Python/YAML/
测试/数据库/API 代码。

---

## 2. Branch / HEAD / Worktree

- `git branch --show-current`: `comqutor-structure-layer`
- `git rev-parse HEAD`: `c758e4eb40890d1ea228bbd70d525ea82e247d99`
- `git status --short`（审计开始前）: 空（clean）
- Worktree: 主工作树（非 linked worktree）
- Python executable: `/opt/miniconda3/bin/python`（系统默认 shell python；
  实际用于运行本仓库测试/代码的是项目 venv `.venv/bin/python`）
- Python version: 3.13.5（两者版本相同，仅 site-packages 不同——`.venv` 装有
  本仓库依赖如 `networkx`/`sqlalchemy`/`fastapi`，系统 python 没有）

本次审计**未**创建、修改仓库中除 `docs/week4_spec_freeze_audit.md` 之外的
任何文件；**未**运行 `pytest`、`docker compose config`，**未**读取/打印/
展开 `.env`。分类：**REPO-CONFIRMED**（工作树状态已直接核实）。

---

## 3. Source-of-Truth Hierarchy

1. **COMQUTOR Alpha Development Plan v1.0** — 决定 Week 4 工程范围、Gate、
   mandatory conflict pairs、Golden Cases、conflict formula 的官方组成
   （min(Activation A, Activation B) × contradiction_weight ×
   evidence_strength）与 level 分档边界。
2. **Helix Quantum Intelligence Operating System White Paper v2.0** —
   决定 admissibility 原则：structure 决定哪些候选是 admissible；AI 不得
   创建或推翻 admissibility；arbitration 只在 admissible candidates 内
   进行；non-selection 必须可审计。
3. **SIC Omnibus Provisional Draft v2** — 与 White Paper 共同约束 readout
   必须来自稳定、确定的结构状态，Week 4 MVP 不实现跨 run 结构反馈学习或
   完整 phi-token runtime。

三份文件共同构成的原则在本文档中出现时标注 **SOURCE-FROZEN**；本仓库
当前代码/数据/测试的实际状态标注 **REPO-CONFIRMED**；三份文件都未覆盖、
需要工程判断的空白标注 **PROPOSED**（需规格负责人批准）；三份文件之间或
与 Golden Case 之间存在冲突、无法在不违反其一的前提下实施的标注
**BLOCKED**。

---

## 4. Current Week 0–3 Baseline

已知人工验收基线（按你消息中提供的原文引用）：

- Full offline regression：803 passed, 1 skipped, 8 deselected
- Focused Week 3/security selection：93 passed
- Week 3 Security Hardening：PASS
- PostgreSQL Integration：UNVERIFIED
- Public/Multi-tenant Deployment：NOT READY

**测试数字澄清（2026-07-14 W4.0 closure 指示中已确认，三者范围不同，
不构成结果矛盾）**：

- **803 passed, 1 skipped, 8 deselected** —— 用户实际运行的完整
  `pytest -m "not integration"` offline suite（覆盖全仓库）。
- **93 passed** —— 用户实际运行的四文件 focused selection（范围更窄，
  只覆盖用户自己选定的四个文件，具体文件未在本文档中转述，因为审计方
  未被告知确切文件列表，不代为猜测）。
- **208 passed, 1 skipped** —— 此前 Codex（即本次 W3 Security Hardening
  Pass 会话）运行的更广泛 11-file focused selection（`tests/
  test_week3_security_hardening.py` / `test_graph_api.py` /
  `test_graph_persistence.py` / `test_file_store.py` / `test_research_
  input_validation.py` / `test_week2_llm.py` / `test_week1a_gate.py` /
  `test_activation_scorer.py` / `test_graph_builder.py` / `test_week3_
  nvda_sanity.py` / `test_week3_qqq_sanity.py`），其中仅新增的
  `tests/test_week3_security_hardening.py` 一个文件贡献 30 passed。

三者选择的文件集合不同（全量 vs 四文件子集 vs 十一文件子集），因此通过
数字不同是范围差异导致的，不是同一范围下的两次运行给出了不一致的结果。
本次 W4.0 closure 沿用这三组数字作为历史记录，**不重新运行测试**（本次
closure 明确要求不修改任何 Python/YAML/测试/数据库/API 文件，重新运行
测试也不会产生新的代码变更，但为了严格遵守"只更新
docs/week4_spec_freeze_audit.md 一个文件"的边界，本次同样不主动触发
pytest）。第 22 节仍然建议 W4.1 启动前做一次新的、显式的全量运行，产出
统一口径的基线数字。

分类：**REPO-CONFIRMED**（工作树/HEAD/分支状态）+ 引用性陈述（三组测试
通过数字均为历史引用，本次未重新验证，范围差异已在上方澄清）。

---

## 5. Actual Taxonomy Conflict Matrix

数据来源：`comqutor_alpha/alpha_library/alpha_taxonomy_v1.yaml`（直接读取
全文，非转述）。taxonomy 共 10 个 Alpha（A001/A003/A101/A102/A103/A201/
A301/A304/A501/A601），与 `alpha_loader.py::EXPECTED_ALPHA_IDS` 完全一致。

### 5.1 原始声明（12 条有向 `conflict_alphas` 记录，逐条列出）

| # | source_alpha | target_alpha | contradiction_weight | declared description | weight finite | weight in [0,1] | self-conflict | dangling ref | duplicate within source |
|---|---|---|---:|---|---|---|---|---|---|
| 1 | A001 | A501 | 0.85 | *(字段不存在，见 5.3)* | Yes | Yes | No | No | No |
| 2 | A003 | A501 | 0.85 | *(字段不存在)* | Yes | Yes | No | No | No |
| 3 | A101 | A304 | 0.90 | *(字段不存在)* | Yes | Yes | No | No | No |
| 4 | A301 | A304 | 0.85 | *(字段不存在)* | Yes | Yes | No | No | No |
| 5 | A304 | A101 | 0.90 | *(字段不存在)* | Yes | Yes | No | No | No |
| 6 | A304 | A301 | 0.85 | *(字段不存在)* | Yes | Yes | No | No | No |
| 7 | A304 | A601 | 0.80 | *(字段不存在)* | Yes | Yes | No | No | No |
| 8 | A501 | A001 | 0.85 | *(字段不存在)* | Yes | Yes | No | No | No |
| 9 | A501 | A003 | 0.85 | *(字段不存在)* | Yes | Yes | No | No | No |
| 10 | A501 | A601 | 0.80 | *(字段不存在)* | Yes | Yes | No | No | No |
| 11 | A601 | A304 | 0.80 | *(字段不存在)* | Yes | Yes | No | No | No |
| 12 | A601 | A501 | 0.80 | *(字段不存在)* | Yes | Yes | No | No | No |

A102、A103、A201 的 `conflict_alphas` 字段均为空列表 `[]`（直接读取自
YAML 第 92、114、133 行）。

### 5.2 折算为 6 组无向 pair（双向一致性核验）

| pair | weight A→B | weight B→A | 对称 | 属于六组 mandatory pairs | 权重与 loader 期望值一致 |
|---|---:|---:|---|---|---|
| A001–A501 | 0.85 | 0.85 | Yes | Yes | Yes (0.85) |
| A003–A501 | 0.85 | 0.85 | Yes | Yes | Yes (0.85) |
| A101–A304 | 0.90 | 0.90 | Yes | Yes | Yes (0.90) |
| A301–A304 | 0.85 | 0.85 | Yes | Yes | Yes (0.85) |
| A601–A304 | 0.80 | 0.80 | Yes | Yes | Yes (0.80) |
| A601–A501 | 0.80 | 0.80 | Yes | Yes | Yes (0.80) |

### 5.3 逐项结论

1. **仓库中实际声明了哪些 conflict pairs？** 恰好上表 6 组（12 条有向
   记录），无更多、无更少。**REPO-CONFIRMED**
2. **是否精确覆盖六组 mandatory pairs？** 是，逐一核对：A101-A304 / A301-A304
   / A001-A501 / A003-A501 / A601-A304 / A601-A501 全部存在，权重与
   `alpha_loader.py::MANDATORY_CONFLICT_WEIGHTS` 完全一致（不只是在容差
   内，是精确相等）。**REPO-CONFIRMED**
3. **是否存在额外 pair？** 没有。12 条有向记录 = 6 组无向 pair = 6 组
   mandatory pairs，一一对应，没有超出集合的声明。**REPO-CONFIRMED**
4. **A102-A304 当前是否存在？** 不存在。A102 的 `conflict_alphas` 是空
   列表；A304 的 `conflict_alphas` 只包含 A101/A301/A601，不包含 A102；
   反过来 A304 一侧也没有指向 A102 的记录。**REPO-CONFIRMED**（详见第 16
   节 Golden Case 冲突）
5. **双向记录是否一致？** 是，6 组全部双向声明、双向权重相等。
   **REPO-CONFIRMED**
6. **contradiction_weight 是否存在缺失或不对称？** 不存在。12 条记录权重
   均为有限数值、均在 `[0,1]`（0.80/0.85/0.90），6 组配对权重两侧完全相等。
   **REPO-CONFIRMED**
7. **当前 loader 是否验证这些约束？** 部分验证。`alpha_loader.py::
   validate_taxonomy()` 显式检查：(a) alpha_id 集合恰好等于 MVP-10；
   (b) 六组 mandatory pairs 双向都存在、且权重与期望值的绝对误差
   ≤0.05；(c) 每个 Alpha 至少有一个 keyword。**它不做的事**：不遍历全部
   `conflict_alphas` 通用地检查"是否存在 mandatory 六组之外的额外 pair"、
   不通用检查"任意 conflict 权重是否为有限数值/在 [0,1] 范围"、不检查
   self-conflict、不检查 dangling alpha_id 引用——这些约束今天恰好因为
   数据本身干净而成立，但不是由通用校验逻辑强制保证的。如果未来有人往
   taxonomy 里加一条六组之外的、权重非法的 conflict_alphas 记录，
   `validate_taxonomy()` **不会**报错。**REPO-CONFIRMED**（校验覆盖面
   本身，不是数据当前是否合规）
8. **当前测试是否真正锁定这些约束？** `tests/test_alpha_loader.py::
   test_loader_returns_mvp_10_and_required_conflicts` 只锁定"六组 pair
   的双向存在性"，**不**断言具体权重数值、**不**断言"没有额外 pair"、
   **不**断言 A102 的 conflict_alphas 为空。也就是说：如果有人误改了
   六组之一的权重数值（只要仍然双向对称），或者给 A102 加了一条新的
   conflict 声明，现有测试套件**不会**失败。**REPO-CONFIRMED**（本次
   审计不修改这个测试，仅如实报告覆盖缺口）

---

## 6. Mandatory-Pair Compliance

| Pair | 声明存在 | 双向对称 | 权重（两侧） | 与 Development Plan 一致 |
|---|---|---|---:|---|
| A101 vs A304 | Yes | Yes | 0.90 | Yes |
| A301 vs A304 | Yes | Yes | 0.85 | Yes |
| A001 vs A501 | Yes | Yes | 0.85 | Yes |
| A003 vs A501 | Yes | Yes | 0.85 | Yes |
| A601 vs A304 | Yes | Yes | 0.80 | Yes |
| A601 vs A501 | Yes | Yes | 0.80 | Yes |

结论：六组 mandatory pairs **100% 合规**，可以直接作为 Conflict Detector
的数据输入，无需修改 taxonomy。**REPO-CONFIRMED**

---

## 7. Week 3 Input Contract for Week 4

以下字段名均为直接阅读源码后确认的**实际**字段名（非任务说明中的推测）：

### 7.1 Activation（`activation_scorer.score_alpha()` 返回值，
`comqutor_alpha/graph_engine/activation_scorer.py`）

顶层字段：`alpha_id`, `alpha_name`, `activation_score`, `status`,
`direction`, `components`, `evidence_count`, `distinct_supporting_agents`,
`claim_ids`, `evidence`, `reason_codes`。

`components` 是一个 dict，key 为五个官方分量名
（`matched_evidence`/`agent_agreement`/`graph_coherence`/`recency`/
`direction_strength`），每个分量至少含 `raw`/`weight`/`contribution`，
外加各自的元信息（例如 `matched_evidence` 还带
`unique_committed_claims`/`weighted_evidence_sum`；`graph_coherence`/
`recency` 在 evidence-gated 时还带 `evidence_gated: true`）。

`score_alpha_activations()` 顶层再包一层：`formula_version`, `weights`,
`run_timestamp`, `as_of`, `alphas`（列表，恰好 10 项）, `dominant_alphas`。

**没有** `conflict_penalty` 字段——`test_activation_scorer.py` 显式断言
它不存在。**REPO-CONFIRMED**

### 7.2 Alpha Match（`alpha_matches.json` / DB 表
`comqutor_alpha/storage/db/schema.py::alpha_matches`）

实际列名：`run_id`, `ticker`, `claim_id`, `source_agent_output_id`,
`agent`, `alpha_id`（仅 `match_status == "matched"` 时非空）,
`alpha_name`, `match_score`, `match_status`, `direction`,
`assertion_status`, `semantic_polarity`, `claim_text`, `evidence`,
`reason`, `candidate_scores`（JSON 列，逐候选携带 `alpha_id`/`score`/
`relation` 等）。

每个结构化 claim 对应**恰好一行**（`UNIQUE(run_id, claim_id)`），不是
每候选 Alpha 一行——次要候选保留在该行自己的 `candidate_scores` JSON
列里，不会成为额外的委托行（Week 3 correctness pass 已锁定并测试这个
语义，见 `tests/test_graph_persistence.py::TestAlphaMatchesCardinality`）。

### 7.3 逐项结论

1. **`activation_score` 是 0–100 还是 0–1？** **0–100**。
   `activation_scorer.py` 使用 `graph_schema.clamp_percent()`，默认
   区间就是 `0.0..100.0`；`activation_status_band()` 的分档边界
   （30/50/70/85/100）也是 0–100 尺度。**REPO-CONFIRMED**
2. **`match_score` 是 0–1 还是 0–100？** **0–1**。取自 Week 2
   `alpha_matches.json` 的 `score` 字段（测试 fixture 中实际值如
   `0.8`），`activation_scorer._gather_alpha_evidence()` 内部用
   `clamp_percent(record.get("score", 0.0), 0.0, 1.0)` 把它钳制在
   `[0,1]`。**但** DB 表 `alpha_matches.match_score` 列在写入时
   （`repository.py::_alpha_match_rows`）只做了
   `float(record.get("score") or 0.0)`，**没有**做 0–1 钳制——如果
   上游 Week 2 产出了越界值，DB 里的原始列可能不在 `[0,1]`。
   **REPO-CONFIRMED**（这是一个需要 Week 4 复用时注意的细节，不是
   本次要修的 bug，因为它不属于本审计允许修改的范围）
3. **哪个字段代表 committed match？** `match_status == "matched"` 且
   `alpha_id`（DB 列，来自 `matched_alpha`）非空。**REPO-CONFIRMED**
4. **ambiguous/no_match 当前如何表示？** `match_status` 取值
   `"matched"`/`"ambiguous"`/`"no_match"`
   （`graph_schema.VALID_MATCH_STATUSES`）。`ambiguous` 时
   `plausible_alphas` 列出候选 Alpha，但 DB 行的 `alpha_id` 列仍为
   `None`（不会伪装成已提交匹配）。**REPO-CONFIRMED**
5. **`relation` 中哪些值可作为支持 Alpha 的 admissible evidence？**
   `activation_scorer._EVIDENCE_RELATION_WEIGHT`：`activation`(1.0)、
   `conditional`(0.65)、`mixed`(0.5) 为正权重，可作为支持证据；
   `invalidation`(0.0)、`risk_relief`(0.0)、`mention`(0.0)、
   `unknown`(0.0) 权重为零，不构成正向支持。**REPO-CONFIRMED**
6. **`risk_relief`/`invalidation` 是否应强化 conflict？** Week 3 现状：
   两者权重为 0，**不**贡献 MatchedEvidence/AgentAgreement 的正向分量，
   只在 DirectionStrength 里作为负向拉力使用。**已在 2026-07-14 W4.0
   closure 中随 evidence_strength 的 qualifying relations 定义一并
   批准解决**（见第 9 节）：qualifying relations 仅
   `activation`/`conditional`/`mixed`，`risk_relief`/`invalidation`
   （以及 `ambiguous`/`no_match`/`mention`/`unknown`）明确不计入
   evidence_strength——即两者**不**强化 conflict。**APPROVED — SPEC-FROZEN
   FOR W4.1**
7. **同一 claim 是否可能重复进入计算？** 不会，前提是复用 Week 3 自己的
   聚合结果或遵守它已有的去重规则。`activation_scorer._gather_alpha_evidence()`
   按 `claim_id` 去重（同一 claim_id 只计一次）；DB 层
   `UNIQUE(run_id, claim_id)` 约束在存储层也保证同一 claim 不会有多行。
   一个 claim 只能是"committed"给至多一个 Alpha（`match_status=="matched"`
   时只有一个 `matched_alpha`），所以不存在"同一 claim 同时是 A 和 B 的
   committed 证据"的情况。**REPO-CONFIRMED**
8. **evidence 是否足以构建 bull_structure/bear_structure？** 足以。
   `activation.alphas[].evidence`（去重后的证据原文列表）、`claim_ids`、
   `direction`、`components` 逐分量分解，加上 graph JSON 节点/边上的
   `claim_ids`/`source_agent_output_ids`/`agents`/`evidence`，已经能够
   在不回读原始 TradingAgents 报告的前提下，重建"哪些证据、来自哪些
   agent、支持哪个方向"的完整叙事骨架。**REPO-CONFIRMED**
9. **Week 3 Graph JSON 是否已经携带足够 provenance？** 是。见
   `graph_builder.py` 的节点/边序列化（`_serialize_node`/`_serialize_edge`），
   claim/agent/evidence 全部保留。**REPO-CONFIRMED**
10. **是否需要 Week 4 回读 raw text，还是只消费结构化边界？** 只消费结构化
    边界。这既是任务本身重申的强制要求，也已经被第 8/9 条的实际能力
    核实为可行。**SOURCE-FROZEN**（任务书原文强制此约束）+
    **REPO-CONFIRMED**（现有结构化产物足以支撑，不需要例外）

---

## 8. Conflict Formula and Data-Scale Audit

Development Plan 公式（不可修改）：

```
Conflict Score = min(Activation A, Activation B)
                 × contradiction_weight
                 × evidence_strength

Level: 0-25 low / 26-50 medium / 51-75 medium_high / 76-100 high
```

- `Activation A`/`Activation B`：**0–100**（第 7.3.1 条已核实，且 Week 3
  每个 Alpha 分数都已 clamp）。
- `contradiction_weight`：**0–1**（第 5 节已核实，当前三档取值
  0.80/0.85/0.90）。
- `evidence_strength`：**APPROVED — SPEC-FROZEN FOR W4.1**（2026-07-14
  closure）：最终尺度固定为 **0–1**，不再是推断——见第 9 节的完整
  批准定义。`match_score` 本身也是 0–1（第 7.3.2 条），两者尺度一致。
- **公式在 0–100 范围内自洽的前提**：`min(Activation A, Activation B)`
  已经是 0–100，`contradiction_weight` 和 `evidence_strength` 都严格是
  0–1（前者第 5 节 REPO-CONFIRMED，后者第 9 节现已 APPROVED），乘积的
  上界是 `100 × 1 × 1 = 100`，下界是 0，天然落在 0–100，不需要额外的
  重新缩放。**REPO-CONFIRMED + APPROVED**（尺度前提不再是隐含推断，已
  写入 spec）
- **是否需要 clamp**：需要，且应复用 Week 3 已有的
  `graph_schema.clamp_percent`/`is_finite_number`，不建议 Week 4 另起
  一套钳制逻辑。理由：`clamp_percent` 已经把 NaN→下界、+Inf→上界、
  -Inf→下界的语义定义清楚并测试覆盖，Conflict Score 沿用同一套语义可以
  保持全仓库一致的"非法输入不报错、确定性钳制"策略。**PROPOSED**
- **NaN/Infinity/负数如何处理**：沿用 `clamp_percent`/`is_finite_number`
  的既有约定（見上）。Development Plan 未对此单独说明。**PROPOSED**
- **边界 25/26、50/51、75/76 如何解释**：**APPROVED — SPEC-FROZEN FOR
  W4.1**（2026-07-14 closure）：采用下开上闭约定，与建议一致：

  ```
  [0, 25]     low
  (25, 50]    medium
  (50, 75]    medium_high
  (75, 100]   high
  ```

  即 25.0 落在 low，25.0001 落在 medium，以此类推；50.0 落在 medium，
  75.0 落在 medium_high，100.0 落在 high。与 Week 3 `activation_status_band()`
  的下开上闭先例一致（现在是独立批准的规则，不是援引先例）。

---

## 9. Evidence-Strength (APPROVED — SPEC-FROZEN FOR W4.1)

**2026-07-14 W4.0 closure 指示已正式批准本节 9.2/9.3 的定义，冻结为
W4.1 实现基线。** 以下保留原始分析过程（方案对比）作为审计留痕，9.2/9.3
的结论部分已从"推荐待批准"更新为"已批准"。

Development Plan 原文：`evidence_strength = average match score of both
alphas`。这句话没有说明"一个 Alpha 有多个 qualifying claims 时如何聚合
成一个数"，是真实的规格空白，不是本仓库的实现缺陷。

- **A. Source-mandated facts**：evidence_strength 是"两个 Alpha 的平均
  match score"；match_score 本身取值 0–1。
- **B. Current repository behavior**：Week 3/Week 4 都还没有任何
  evidence_strength 的实现——仓库中不存在这个字段、这个函数、这个概念的
  任何代码。
- **C. Undefined specification**：单个 Alpha 一侧有多个 qualifying
  committed claims 时怎么聚合成一个"这一侧的强度"，Development Plan
  完全没写。
- **D. Recommended proposal requiring approval**：见下方对比与推荐。

### 9.1 四种方案对比

| 方案 | 对称性（双方等权） | 是否被 claim 数量偏置 | 是否易被重复 claim 放大 | 可解释性 | 是否贴合原文措辞 | 复用 vs 重新计算 | 测试稳定性 |
|---|---|---|---|---|---|---|---|
| 1. 每侧 qualifying committed claims 的 match_score 均值，再对两侧均值取平均 | 是 | 否（均值已按数量归一） | 低（`UNIQUE(run_id, claim_id)` 已防止同一 claim 重复入库；`_gather_alpha_evidence` 也按 claim_id 去重） | 高 | **最贴合**（"average" 的最直接读法） | 可复用 Week 3 已聚合的证据集合，或直接重新按 match_score 计算 | 高，纯算术、确定性 |
| 2. 每侧取最高 match_score，再对两侧取平均 | 是 | 否 | 极低（max 对重复免疫） | 中（"最强单条证据"，但丢失多证据佐证信号） | 中（比"average"更像"peak"，是对原文的引申） | 需重新计算（Week 3 没有现成的"每侧 max"字段） | 高 |
| 3. 双方全部 qualifying claims 混合成一个池子统一取平均 | 否（claim 数量多的一侧会拉偏整体均值） | 是（明显偏置） | 中高（claim 越多影响越大） | 低（对"pairwise 冲突强度"这个概念而言，把两个对立方的证据混在一起取一个数，语义含糊） | 弱 | 需重新计算 | 高但语义可疑 |
| 4. 复用 activation components 里的 MatchedEvidence（`matched_evidence.raw`/100） | 是 | 否（Week 3 自己的饱和/去重逻辑已处理） | 低（Week 3 已有 `EVIDENCE_SATURATION` 饱和上限与去重） | 中（复用现成、已测试的既定分量，但其内部含 relation 加权与 ambiguous 折扣，不是字面意义的"平均分"） | 最弱（不是"average match score"，是"加权饱和证据分量"） | 完全复用，零新增计算 | 高（Week 3 已有完整测试覆盖，Week 4 只需再测 min/×/× 组合本身） |

### 9.2 已批准定义（APPROVED — SPEC-FROZEN FOR W4.1）

采用方案 1，**已批准**：

```
strength_A = mean(A 方 qualifying committed claims 的 match_score)
strength_B = mean(B 方 qualifying committed claims 的 match_score)
evidence_strength = mean(strength_A, strength_B)
```

最终尺度：**固定为 0–1**（不是 0–100，与第 8 节的公式尺度前提一致）。

理由（批准前的分析留档）：对双方对称、不受 claim 数量偏置、对重复 claim
天然免疫（配合下方 qualifying evidence 定义与既有的
`UNIQUE(run_id, claim_id)` 约束）、最贴合 Development Plan 原文措辞、
可解释、可稳定测试。方案 4（复用 MatchedEvidence 分量）曾作为最 DRY 的
替代方案记录在案，本次批准采纳的是方案 1，方案 4 不再是待选项。

**APPROVED — SPEC-FROZEN FOR W4.1**（2026-07-14）

### 9.3 已批准的 qualifying evidence 定义（APPROVED — SPEC-FROZEN FOR W4.1）

qualifying committed claim 必须同时满足：

- `match_status == "matched"`
- `alpha_id` 等于当前 pair 中对应的一侧
- `claim_id` 唯一去重（同一 claim 只计一次）
- `evidence` 非空，或满足当前结构化 evidence contract
- `relation` 属于 qualifying relations：**仅**
  `activation`/`conditional`/`mixed`

明确**不计入** evidence_strength 的情形：

- `ambiguous`（不是 committed evidence）
- `no_match`（不是 committed evidence）
- `mention`（relation 权重为 0，非 qualifying）
- `risk_relief`（relation 权重为 0，非 qualifying——呼应第 7.3.6 条，
  不得被误当作激活"该风险 Alpha"的正向支持）
- `invalidation`（relation 权重为 0，非 qualifying，同上）
- `unknown`（relation 权重为 0，非 qualifying）

**APPROVED — SPEC-FROZEN FOR W4.1**（2026-07-14）

---

## 10. Canonical Pair (APPROVED — SPEC-FROZEN FOR W4.1)

**2026-07-14 W4.0 closure 指示已正式批准本节 10.2 的定义，冻结为 W4.1
实现基线。** 以下保留原始方案对比作为审计留痕。

Development Plan 未规定数据库中 conflict pair 的存储顺序/去重键。

### 10.1 三种方案对比

| 方案 | 防止 A-B/B-A 重复入库 | 与数据库唯一约束的兼容性 | API 输出稳定性 | bull/bear 角色表达 | 应对 taxonomy 双向描述不同 | main_conflict tie-break 确定性 |
|---|---|---|---|---|---|---|
| A. 按 alpha_id 字典序排序 `(min, max)` 作为唯一键 | 好（天然唯一） | 好，可直接做 `UNIQUE(alpha_a, alpha_b)` | 好（同一 pair 永远同一顺序输出） | 无——字典序第一个不一定是 bull | 不处理，只解决去重，不解决角色 | 好（可作为最终 tie-break 的确定性小键） |
| B. 保持 taxonomy 中 source→target 的声明顺序 | **差**——本仓库 taxonomy 对六组 mandatory pairs 全部是双向声明（A→B 与 B→A 都存在，见第 5 节），"taxonomy 声明顺序"本身不唯一，取决于 YAML/dict 遍历顺序，无法确定性地选出"谁在前" | 差，需要额外规则打破双向声明的对称性 | 差（顺序依赖遍历实现细节，不稳定） | 同样没有解决 | 不解决，反而放大了这个问题 | 差 |
| C. 显式保存 `bull_alpha_id`/`bear_alpha_id`（语义角色）+ 单独保存 canonical pair key（去重用） | 好（canonical key 唯一） | 好 | 好 | 好——语义角色与去重键分离，互不干扰 | 好——两条声明只是同一去重键下的两个视角，语义角色由运行时的 activation/direction 决定，不依赖 taxonomy 声明顺序 | 好（canonical key 仍可作为最终 tie-break 依据） |

### 10.2 已批准定义（APPROVED — SPEC-FROZEN FOR W4.1）

采用方案 C，且 canonical key 的排序规则取方案 A，**已批准**：

```
alpha_a / alpha_b = sorted(alpha_id_1, alpha_id_2)             # 去重键，按 alpha_id 排序
bull_alpha_id / bear_alpha_id = 由运行时语义决定，与字典序无关          # 角色，独立保存
```

理由（批准前的分析留档）：`bull`/`bear` 角色不等于字典序（例如 A101 vs
A304 谁是 bull 取决于两者当前 run 的 `direction`/`activation_score`，
不是 alpha_id 本身的字母顺序），必须分开存储；taxonomy 中双向声明的权重
虽然一致但两侧各自的 `core_thesis`/`name_en` 描述不同，canonical key
只解决"同一对 Alpha 不能生成两条 conflict 记录"这一件事，不代表哪一侧的
描述"更权威"。

**APPROVED — SPEC-FROZEN FOR W4.1**（2026-07-14）

---

## 11. Admissibility and Suppression Contract (核心条件 APPROVED — SPEC-FROZEN FOR W4.1)

**2026-07-14 W4.0 closure 指示已正式批准下方五项核心 admissibility 条件
（含 activation threshold 的最终选择），冻结为 W4.1 实现基线。** 11.2 的
reason-code 清单与 11.3 的四态划分未在本次 closure 中被逐项重新确认，
仍标注 PROPOSED（详见各自小节说明）。

基于 White Paper / SIC 的 admissibility 原则（structure 决定候选是否
admissible；AI 不得创建或推翻 admissibility；non-selection 必须可
审计），一个 conflict pair 要进入正式 `conflicts[]`，必须同时满足下列
**已批准**的五项条件：

- pair 必须由 taxonomy 正式声明（即在第 5 节矩阵中，不能是 AI 临时判断
  出的关系）——**SOURCE-FROZEN**（直接来自 White Paper 的 admissibility
  原则：AI 不得创建 admissibility）
- 双方 `status` 至少 `watch`——**APPROVED — SPEC-FROZEN FOR W4.1**
  （2026-07-14，见 11.1 的最终选择）
- 双方必须有 qualifying committed evidence（第 9.3 节已批准定义）——
  **APPROVED — SPEC-FROZEN FOR W4.1**
- `evidence_strength` 必须 > 0（第 9.2 节已批准定义）——**APPROVED —
  SPEC-FROZEN FOR W4.1**
- `contradiction_weight` 必须合法（有限数值、在 taxonomy 声明范围内）——
  **REPO-CONFIRMED** 可直接复用第 5 节的校验结果
- `run_id` 必须一致（两侧数据必须来自同一 run，不能跨 run 拼接）——
  **SOURCE-FROZEN**（SIC/White Paper：readout 必须来自稳定确定的结构
  状态，不做跨 run 拼接）
- schema 必须有效（graph_json/alpha_matches 均通过 Week 3 既有的
  corrupted/mismatch 校验）——**REPO-CONFIRMED**（Week 3 已有
  `GRAPH_CORRUPTED`/`GRAPH_SCHEMA_MISMATCH` 校验，可直接复用同一套
  safe-reject 逻辑，不需要另起一套）

（原审计中"双方必须在 activation 结果中存在对应 entry"一条已被"双方
status 至少 watch"取代——后者是更强的条件，蕴含前者，MVP-10 恒定输出
全部 10 项这一事实本身仍然是 **REPO-CONFIRMED**，但不再单独作为
admissibility 条件列出，避免与已批准的 threshold 重复。）

### 11.1 Activation Threshold — 已批准（APPROVED — SPEC-FROZEN FOR W4.1）

四个原始选项：

1. `activation_score > 0` 即可；
2. `status` 至少 `watch`；
3. 双方至少 `active`；
4. 不设额外 threshold，只依赖 evidence 和 score。

**已批准选项 2**：双方 `status` 至少 `watch`（即 `activation_score`
按 `activation_status_band()` 落在 `watch`/`active`/`dominant`/
`regime_level` 之一，不能是 `inactive`）。

**APPROVED — SPEC-FROZEN FOR W4.1**（2026-07-14）

### 11.2 Reason-Code 清单（审计用途，本次只定义不实现——PROPOSED，未在
2026-07-14 closure 中逐项重新确认）

`PAIR_NOT_DECLARED` / `MISSING_LEFT_ACTIVATION` /
`MISSING_RIGHT_ACTIVATION` / `MISSING_LEFT_EVIDENCE` /
`MISSING_RIGHT_EVIDENCE` / `AMBIGUOUS_ONLY` / `ZERO_EVIDENCE_STRENGTH` /
`INVALID_CONTRADICTION_WEIGHT` / `INACTIVE_LEFT_ALPHA` /
`INACTIVE_RIGHT_ALPHA` / `DUPLICATE_PAIR` / `SCHEMA_INVALID`

### 11.3 四态划分（PROPOSED，未在 2026-07-14 closure 中逐项重新确认）

- **suppressed**：候选合法存在（taxonomy 已声明），但本 run 不满足进入
  条件（例如证据不足、activation 未达 threshold）。
- **rejected**：数据或 schema 本身非法（例如 contradiction_weight 越界、
  graph JSON 损坏）。
- **deferred**：依赖尚未可用，或规格本身尚未冻结（例如 A102-A304，见
  第 16 节——这不是"这次 run 证据不够"，而是"这个 pair 根本不在 taxonomy
  声明范围内"，本质上更接近 `rejected`/`PAIR_NOT_DECLARED`，但因为
  Golden Case 明确要求它，暂归类为需要规格层面重新决策的 `deferred`，
  而不是运行时的 `suppressed`）。
- **admitted**：进入正式 conflict scoring。

本节只定义审计 contract，不实现跨 run non-execution feedback 或 Alpha
Memory（SOURCE-FROZEN 边界，SIC/White Paper 明确排除）。

**核心五项 admissibility 条件（含 threshold）：APPROVED — SPEC-FROZEN
FOR W4.1（2026-07-14）。reason-code 清单（11.2）与 suppressed/rejected/
deferred/admitted 四态划分（11.3）：仍为 PROPOSED——这两者是实现上述
已批准条件时的命名/分类建议，本次 closure 未逐项重新确认，采纳前建议
再单独过一轮确认，不能因为核心条件已批准就默认这两项细节也自动批准。**

---

## 12. Main-Conflict Arbitration (APPROVED — SPEC-FROZEN FOR W4.1)

**2026-07-14 W4.0 closure 指示已正式批准下方排序规则与 no-conflict
contract，冻结为 W4.1 实现基线。**

Development Plan 只要求输出 `main_conflict`，未给出完整 tie-break 规则。

**已批准排序**（依次比较，直到分出唯一胜者）：

1. `conflict_score` 降序
2. `evidence_strength` 降序
3. `min_activation`（即 `min(Activation A, Activation B)`）降序
4. canonical pair ID（第 10 节已批准的 `(alpha_a, alpha_b)` 字典序）升序

**APPROVED — SPEC-FROZEN FOR W4.1**（2026-07-14）

### 12.1 性质核验

- **deterministic**：是——第 4 级 tie-break（canonical pair ID）保证
  即使前三项完全打平也有唯一确定的结果，不存在需要随机或依赖字典遍历
  顺序的情况。
- **与输入顺序无关**：是——排序键全部来自数据本身（score/strength/
  activation/canonical id），不依赖 `conflicts[]` 数组的原始生成顺序。
- **不依赖 ticker**：是——排序逻辑不读取 ticker 字段。
- **不依赖 LLM**：是——纯数值/字符串比较。
- **可稳定测试**：是——给定同一组 admitted conflicts，输出恒定。
- **不会制造不存在的 conflict**：是，因为 tie-break 只在已经
  `admitted` 的 conflicts 集合内选择，不创造新记录。

### 12.2 No-Conflict Contract

```
conflicts = []
main_conflict = null
```

当没有任何 pair 满足 admissibility 条件时，必须原样输出空数组/null，
**不允许**为了让前端"看起来有内容"而强行选一个 suppressed/rejected 的
pair 冒充 main_conflict。这一点直接来自 White Paper 的 admissibility
原则（AI 不得创建 admissibility），是 **SOURCE-FROZEN** 的推论，不是
工程偏好；具体的四级排序规则本身经 2026-07-14 closure 批准，现为
**APPROVED — SPEC-FROZEN FOR W4.1**。

---

## 13. Exposure Seed Audit

全仓库搜索结果（`find`/`grep`，排除 `.venv`/`.git`）：

1. **seed 是否存在？** 不存在。
2. **文件路径是什么？** 无——`entity_alpha_exposure_seed.yaml` 或任何
   同类文件在仓库中不存在。
3. **schema 是什么？** 无——没有 exposure schema 定义。
4. **是否有版本号？** 不适用（文件不存在）。
5. **是否有 validation？** 不适用。
6. **是否覆盖指定 ticker（NVDA/AMD/MSFT/GOOGL/AMZN/AVGO/TSM/SMCI/
   QQQ/SPY）？** 不适用。
7. **数值是否为 0–1 或 0–100？** 不适用。
8. **是否有 John 的正式 sign-off 记录？** 未找到——对 `John` 的全仓库
   （`.md`/`.yaml`/`.py`）不区分大小写搜索无匹配结果。
9. **`exposure_engine.py` 是否已存在？** 不存在。
10. **是否存在旧实现或 legacy 文件？** 不存在——没有找到任何历史/废弃的
    exposure 相关文件。

Development Plan 的 exposure 公式（记录留档，不实现）：

```
exposure = historical_mapping × 50% + current_evidence × 30%
           + agent_confidence × 20%
```

结论：

```
EXPOSURE_SEED_UNAVAILABLE
Week 4 Conflict Core 可继续
Exposure Engine Full Gate blocked
```

未编造任何 seed 数值。**REPO-CONFIRMED**（不存在性）+ **BLOCKED**
（Exposure Engine Full Gate，直到 seed 与 sign-off 正式提供）。

---

## 14. Database Delta

当前已有（直接读取 `comqutor_alpha/storage/db/schema.py`/`migrations.py`/
`repository.py`）：

- `alpha_matches` 表（claim 级，`UNIQUE(run_id, claim_id)`）
- `structure_graphs` 表（run 级，`graph_json` 整体存储，含 Week 3
  activation 结果——`activation.alphas[]` 是嵌在 `graph_json` 里的，
  **不是**独立的 `alpha_activations` 表）
- `schema_migrations` 表，单条迁移
  `0001_create_week3_alpha_matches_and_structure_graphs`
- 迁移执行器 `migrations.py::apply_migrations`（显式、幂等、非
  Alembic）
- 读/写 repository 构造已经分离（`build_repository_from_env`只读 /
  `build_write_repository_from_env`写入，Week 3 Security Hardening Pass
  引入）

Week 4 目标（Development Plan）：

- `alpha_activations` 表（全新）
- `alpha_conflicts` 表（全新）
- `/conflicts`、`/agent-outputs` 端点（全新）
- `dominant_alphas` + `main_conflict` + `summary` 出现在
  `/api/research` 响应中（增量）

### 14.1 逐项结论

- **哪些是全新表？** `alpha_activations`、`alpha_conflicts` 都是全新表，
  当前 schema.py 中不存在任何同名或同构表。
- **哪些数据已经存在但尚未独立持久化？** activation 结果（每个 Alpha
  的 `activation_score`/`status`/`direction`/`components`/...）**已经**
  作为 `structure_graphs.graph_json.activation.alphas[]` 的一部分持久化，
  只是嵌在一个大 JSON 列里，不是独立的、可按 `alpha_id` 单独查询/索引的
  关系表行。Week 4 如果要建 `alpha_activations` 表，本质是把这份已经
  存在的数据"拆解落地"，而不是从零计算新东西。
- **当前 repository 是否适合扩展？** 结构上适合：`GraphPersistenceRepository`
  已经是"一次事务内同时处理 alpha_matches 替换 + structure_graphs
  upsert"的模式，`alpha_activations`/`alpha_conflicts` 可以按同样的
  "delete-then-insert / upsert" 模式加入同一个 `persist_run()` 事务，
  沿用相同的 dialect-portable `INSERT ... ON CONFLICT DO UPDATE`。
- **migration 应如何版本化？** **APPROVED — SPEC-FROZEN FOR W4.1**
  （2026-07-14 closure）：迁移版本号确定为
  `0002_create_week4_alpha_activations_and_alpha_conflicts`，遵循现有
  `MIGRATIONS` tuple 的 `(version_id, tables)` 模式，不修改
  `0001_...`（保持已应用迁移不可变，是 `migrations.py` 现有设计的隐含
  约定）。注意：本次批准的是**版本号命名**，不是完整表结构——
  `alpha_activations`/`alpha_conflicts` 的具体列定义（字段名、类型、
  约束）仍未给出，属于实现阶段的工作，不属于本次规格冻结范围（见
  第 19 节剩余事项）。
- **GET read-only 安全边界需要复用哪些 Week 3 规则？** 全部复用：
  构造只读 repository 时不得触发 `ensure_schema()`/`apply_migrations`；
  本地 SQLite 文件不存在时不得因为一次 `.connect()` 而被自动创建
  （`sqlite_file_path` 守卫）；异常处理默认不记录完整 traceback/DSN，
  只在显式 DEBUG 级别输出；`/conflicts`、`/agent-outputs` 应该复用
  同一个只读 repository 工厂函数，不应该各自重新发明一套构造逻辑。
- **`agent-outputs` endpoint 的 raw/structured 暴露风险？** **APPROVED —
  SPEC-FROZEN FOR W4.1**（2026-07-14 closure）：`/agent-outputs`
  **默认 structured-only**（`structured_agent_outputs.json` 的 claim
  级结果），**不**暴露完整 raw transcript。`raw_agent_outputs.json`
  目前是内部产物，从未通过任何现有 endpoint 直接对外暴露原文；这个
  批准延续了这一现状，也延续了本次任务反复强调的"Week 4 不应重新
  解析/暴露原始自由文本"的精神。是否在未来提供一个显式、额外的 raw
  暴露开关（而非默认行为）不在本次批准范围内，若需要应作为单独决策
  处理。
- **当前无 auth/tenant ownership 对新 endpoint 的影响？** 与 Week 3
  完全相同的限制：新增的 `/conflicts`、`/agent-outputs` 端点如果不加
  auth，任何知道 `run_id` 的人都能读取该 run 的完整冲突分析和（如果
  暴露）原始 agent 输出，风险随暴露面扩大而线性增加（`agent-outputs`
  比 `graph` 端点潜在暴露更多原始信息）。
- **哪些内容属于 Week 4？** `alpha_activations`/`alpha_conflicts` 建表、
  `conflict_detector.py`、`/conflicts`、`/agent-outputs`、response
  additive 字段、`exposure_engine.py` v1（若 seed 就绪）。
- **哪些必须推迟到 Week 5 或 production hardening？** 真正的
  authentication/tenant ownership 实现、跨 run Alpha Memory/结构反馈
  学习、完整 phi-token runtime、Dashboard/前端、portfolio
  construction、broker 集成、backtesting、Neo4j。

本节只审计差异，**不实现**任何一项。

---

## 15. API Delta

当前实际注册的全部 HTTP 端点（直接读取 `comqutor_alpha/api/main.py` 及其
引用的两个 router 文件）：

| 方法 | 路径 | 来源 |
|---|---|---|
| GET | `/api/alpha-library` | `routes_alpha_library.py`（Week 1 范围，taxonomy 只读） |
| GET | `/api/alpha-library/{alpha_id}` | 同上 |
| POST | `/api/research` | `routes_research.py` |
| GET | `/api/research/{run_id}` | `routes_research.py` |
| GET | `/api/research/{run_id}/graph` | `routes_research.py`（Week 3） |

Week 4 目标新增：`GET /api/research/{run_id}/conflicts`、
`GET /api/research/{run_id}/agent-outputs`，以及 `POST /api/research`
响应体新增 `summary`/`dominant_alphas`/`main_conflict`（additive，
不改变现有字段——沿用 Week 3 Security Hardening Pass 已确立的"新增顶层
字段，不修改 `artifacts` 形状"的先例）。

本节只列差异，**不实现**。

---

## 16. Golden Case Matrix

| Ticker | Required pair | Taxonomy declared | Weight available | Current fixture support | Status |
|---|---|---:|---:|---:|---|
| NVDA | A101 vs A304 | Yes | 0.90 | Yes（`tests/test_week3_nvda_sanity.py` 已覆盖 A101/A304 双方均有 committed 证据且方向分化） | READY |
| QQQ | A001 vs A501 | Yes | 0.85 | Yes（`tests/test_week3_qqq_sanity.py` 已覆盖 A001/A501 双方均有 committed 证据） | READY |
| QQQ | A003 vs A501 | Yes | 0.85 | Yes（同上，A003/A501 双方均有 committed 证据） | READY |
| MSFT | A102 vs A304 | **No** | **N/A** | 无 MSFT fixture（仓库中不存在任何 MSFT 相关测试数据） | **SPEC_CONFLICT / BLOCKED** |

MSFT 行的阻塞原因：

- Golden Case 明确要求 A102 vs A304 的冲突仲裁；
- 六组 mandatory taxonomy pairs 不包含 A102-A304 这一关系（第 5、6 节
  已逐条核实：A102 的 `conflict_alphas` 为空列表）；
- taxonomy 中不存在 A102-A304 的 `contradiction_weight`，无法计算
  Conflict Score 的这一项输入；
- Conflict Detector 按 admissibility 原则（第 11 节）只能计算 taxonomy
  正式声明的关系——若为了满足这一个 Golden Case 而让 Conflict Detector
  计算一个 taxonomy 未声明的关系，等同于让 AI/工程实现临时创建
  admissibility，直接违反 White Paper 的 SOURCE-FROZEN 原则。

本次审计**未**修改 Golden Case，**未**修改 taxonomy，**未**替代选择一个
六组 mandatory pairs 内的 pair 去"顶替" MSFT 的 Golden Case。这是一个
需要产品/规格层面裁决的真实冲突：或者正式把 A102-A304 加入 taxonomy 的
mandatory conflict pairs（并给出权重来源），或者修改 MSFT Golden Case
使用一个已声明的 pair，两者都不属于 W4.0 审计的权限范围。

---

## 17. Security and Deployment Boundaries

Week 4 新增的持久化与端点必须复用 Week 3 Security Hardening Pass 已经
确立、并经过测试锁定的规则，不得重新发明或放松：

- GET 类端点（`/conflicts`、`/agent-outputs`）默认路径不得触发 schema
  migration、不得创建数据库表/本地 SQLite 文件、不需要 DDL 权限；
- 意外异常默认不得向客户端响应或默认生产日志泄漏 DSN/路径/原始
  异常文本/traceback；完整 traceback 只能在本地显式 DEBUG 级别可见；
- 新增的错误/状态日志只应包含 `run_id`/`stage`/稳定 `reason_code`/
  时间戳；
- 新表的写入路径必须遵循参数化查询、事务 rollback、run 隔离（不得让
  ticker 成为绕过 run_id 隔离的替代键）；
- 生产环境缺少 `COMQUTOR_DATABASE_URL` 时依然不允许静默退化到本地
  SQLite（`DatabaseConfigurationError`/`PRODUCTION_DATABASE_URL_REQUIRED`
  契约对新表同样适用）；
- 当前**没有** authentication/authorization、**没有** owner_id/
  tenant_id 强制隔离——这个限制对新增的 `/conflicts`、`/agent-outputs`
  同样成立，且 `/agent-outputs` 潜在暴露面比现有 `/graph` 更大（见
  第 14 节），部署前必须先完成真正的 authentication 与 run ownership，
  不应该为了赶 Week 4 进度而给单个新 endpoint 拼凑临时认证方案。

---

## 18. Decisions Already Determined by Source Documents

- 六组 mandatory conflict pairs 及其权重（Development Plan + taxonomy
  已完整声明，见第 5、6 节）。
- Conflict Score 公式的三个乘法项与四档 level 名称（Development Plan）。
- structure 决定 admissibility；AI 不得创建/推翻 admissibility；
  arbitration 只在 admissible candidates 内进行；non-selection 必须
  可审计（White Paper / SIC）。
- Week 4 MVP 不实现跨 run 结构反馈学习或完整 phi-token runtime
  （White Paper / SIC）。
- Week 4 downstream 模块不应重新解析原始 TradingAgents 自由文本（任务
  边界，且已被第 7 节的实际字段能力核实为可行）。
- No-conflict 时必须输出 `conflicts=[]`/`main_conflict=null`，不得为
  UI 强行制造冲突（White Paper admissibility 原则的直接推论）。

---

## 19. Decisions Requiring Product/Specification Approval

**2026-07-14 W4.0 closure 已批准原列表中的第 1、2、4、5、7、8（仅版本号
部分）、9 项**（详见各自小节，现标注 APPROVED — SPEC-FROZEN FOR W4.1）。
以下是 closure 之后**仍然真实未决**的事项，不应被误当作已批准：

1. Conflict Score 是否字面复用 `clamp_percent`/`is_finite_number` 这两个
   具体工具函数、以及 NaN/Infinity/负数在 Conflict Score 计算链路中的
   处理方式（第 8 节）——level 边界的开闭区间约定本身已批准
   （`[0,25]`/`(25,50]`/`(50,75]`/`(75,100]`），但"是否复用这两个具体
   函数"这一实现细节未被本次 closure 消息提及，不能自动视为批准，
   仍标注 PROPOSED。
2. Reason-code 清单与 suppressed/rejected/deferred/admitted 四态划分
   是否按第 11.2/11.3 节的定义采纳（admissibility 的五项核心条件与
   threshold 本身已批准，但这套命名/分类细节未被本次 closure 逐项
   重新确认）。
3. `alpha_activations`/`alpha_conflicts` 的具体表结构（列名、类型、
   约束）——第 14 节已批准的只是 migration **版本号命名**
   `0002_create_week4_alpha_activations_and_alpha_conflicts`，不是
   完整 DDL，具体列定义已经越过审计/规格范畴，进入实现阶段。
4. MSFT Golden Case 与 taxonomy mandatory pairs 之间的冲突如何解决——
    修改 taxonomy 还是修改 Golden Case（第 16 节，本次 closure 明确
    保持 BLOCKED_BY_SPEC_CONFLICT，未裁决，本审计不建议由工程单方面
    决定）。

---

## 20. Implementation-Ready Items

以下内容此前依赖"决策批准"，现已随 2026-07-14 closure 具备直接实现的
条件（数据/字段/校验/测试先例均已存在，规格已冻结）——但**仍然
NOT STARTED**，本次 closure 与 W4.0 审计一样只更新规格文档，不写任何
实现代码：

- 读取六组 mandatory pairs 并计算 `min(Activation A, Activation B) ×
  contradiction_weight × evidence_strength`（数据输入已全部就绪，公式
  尺度前提已批准，见第 8 节）。
- 按第 9 节已批准定义计算 `evidence_strength`（方案 1，0–1 尺度，
  qualifying relations 仅 activation/conditional/mixed）。
- 按第 10 节已批准定义存储 canonical pair（`alpha_a`/`alpha_b` 排序 +
  独立的 `bull_alpha_id`/`bear_alpha_id`）。
- 按第 11 节已批准的五项核心条件（含 `status` 至少 `watch` 的
  threshold）判定 admissibility。
- 按第 12 节已批准的四级排序规则计算 `main_conflict`，并遵循
  no-conflict 契约（`conflicts=[]`/`main_conflict=null`）。
- 迁移文件命名为 `0002_create_week4_alpha_activations_and_alpha_
  conflicts`（第 14 节已批准，具体列定义仍需实现阶段单独设计）。
- `/agent-outputs` 默认只暴露 structured 输出，不暴露完整 raw
  transcript（第 14 节已批准）。
- 复用 Week 3 已锁定的 GET 只读边界模式（`build_repository_from_env`
  / `ensure_schema` 分离）扩展到新表的读路径。
- 复用 `INSERT ... ON CONFLICT DO UPDATE` 的事务模式扩展到
  `alpha_activations`/`alpha_conflicts` 的写路径。

## 21. Blocked Items

- MSFT Golden Case（A102-A304 规格冲突，第 16 节）——**保持 BLOCKED_BY_
  SPEC_CONFLICT**，本次 closure 未裁决。
- Exposure Engine Full Gate（seed 文件不存在，第 13 节）——**保持
  BLOCKED_BY_SEED**，本次 closure 未提供 seed。
- 第 19 节列出的剩余四项未决事项（clamp 工具函数复用细节、reason-code/
  四态划分细节、`alpha_activations`/`alpha_conflicts` 具体表结构、
  MSFT 冲突解决路径）——在这些事项各自获得批准前实现即为提前臆造规格。

## 22. W4.1 Entry Criteria

**状态：已满足（原四条中的第 1、2 项被本次 closure 满足；第 3、4 项
仍待完成，但不阻塞 Conflict Core 本身进入 W4.1）。**

1. ~~第 19 节十项决策至少完成 1–8 项的书面批准~~ ——
   **已满足**：2026-07-14 closure 批准了 evidence_strength（含尺度、
   qualifying relations）、conflict level 边界、canonical pair、
   admissibility 五项核心条件（含 threshold）、main-conflict
   tie-break、migration 命名、`/agent-outputs` 默认暴露范围。
2. MSFT Golden Case 的处理方式（修改 taxonomy 或修改 Golden Case）——
   **仍未裁决**，但本次 closure 明确保持 MSFT Golden Gate
   BLOCKED_BY_SPEC_CONFLICT，不阻塞 Conflict Core 本身（六组
   mandatory pairs）进入 W4.1；MSFT 这一个 Golden Case 单独保持
   BLOCKED 直到裁决。
3. Exposure Engine 的 seed 来源与 sign-off 流程——**仍未确定**，
   Exposure Engine Entry 保持 BLOCKED_BY_SEED，不阻塞 Conflict Core。
4. 一次新的、显式的 `pytest -m "not integration"` 全量运行——**仍未
   执行**（本次 closure 明确要求只更新 docs 文件，不触发测试运行）；
   建议 W4.1 实现启动前补做，作为统一口径的回归基线（第 4 节已澄清
   803/93/208 三组历史数字范围不同，不是矛盾，但仍建议以一次新运行
   统一基线）。

**结论：Conflict Core 的 W4.1 Entry 条件已满足（READY）；Exposure
Engine 与 MSFT Golden Case 两条独立路径继续 BLOCKED，不影响 Conflict
Core 本身启动。**

## 23. Final W4.0 Verdict

```
W4.0 Repository Audit: PASS
W4.0 Specification Freeze for Conflict Core: PASS
W4.1 Conflict Core Entry: READY
Exposure Engine Entry: BLOCKED_BY_SEED
MSFT Golden Gate: BLOCKED_BY_SPEC_CONFLICT
Week 4 Implementation: NOT STARTED
```

本次审计（含 2026-07-14 closure 更新后）满足全部十五条 W4.0 通过标准：
taxonomy conflict matrix 已完整列出（第 5 节）；六组 mandatory pairs
已逐一核验（第 6 节）；A102-A304 已明确记录为 BLOCKED（第 16 节）；
全部 contradiction weights 已审计（第 5 节）；Week 3 实际输入字段已
核实（第 7 节）；conflict formula 数据尺度已核实并批准（第 8 节）；
evidence_strength 未定义部分已明确并**批准冻结**（第 9 节）；
canonical pair 未定义部分已明确并**批准冻结**（第 10 节）；
admissibility/suppression 核心条件已给出并**批准冻结**（第 11 节）；
main_conflict tie-break 已给出并**批准冻结**（第 12 节）；exposure
seed 不存在已确认（第 13 节）；DB/API delta 已列清、migration 命名与
`/agent-outputs` 默认暴露范围已**批准冻结**（第 14、15 节）；未实现
Week 4 任何代码；未修改 taxonomy、测试或 Week 1–3 旧代码；本次
closure 与 W4.0 审计一样，只新增/修改了
`docs/week4_spec_freeze_audit.md` 一个文件。

**历史记录**（W4.0 原始判定，2026-07-14 closure 前）：

```
W4.0 Repository Audit: PASS
W4.0 Specification Freeze: PARTIAL
Conflict Core Entry: READY WITH PROPOSED DECISIONS
Exposure Engine Entry: BLOCKED_BY_SEED
MSFT Golden Gate: BLOCKED_BY_SPEC_CONFLICT
Week 4 Implementation: NOT STARTED
```

## 24. `git status --short`

closure 完成后（应仍只有本文档一个文件发生变化）：

```
?? docs/week4_spec_freeze_audit.md
```

（其余全部路径应无任何变化——见正文第 2 节与最终回复中的确认；本次
closure 未修改任何 Python/YAML/测试/数据库/API 文件，未 commit，
未 push。）
