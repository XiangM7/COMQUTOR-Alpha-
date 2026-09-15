# Main Conflict Gold Adjudication — v0.1.2.1

本文档记录对"Main Conflict >= 4/6"验收要求的独立、基于既有冻结证据的裁定过程。裁定在查看当前 v0.1.2.1 最终六个生产 run 的实际 Main Conflict 结果**之前**完成，且过程中未查阅任何最终生产输出。

---

## 裁定方法与允许证据来源

- Development Plan v1.0（`COMQUTOR_Alpha_Development_Plan_v1.0.docx` §12 Golden Test Cases，直接从原始 docx XML 提取）
- 当前权威 label 文件 `comqutor_alpha/config/j2_provisional_regression_labels_v0.2.yaml`
- Canonical Alpha taxonomy（`alpha_taxonomy_v1.yaml` 的 `conflict_alphas` 关系）
- 已批准的 Product Decision（PD-017，MSFT A102↔A304 拒绝决定）
- 既有 `regression_label_authority_audit_v0.1.2.1.json`（交叉核对，未重新裁定）

候选 pair 必须同时满足 5 项标准：合法的 canonical pair、未被拒绝/取代、在**冻结**的 ticker 专属证据中双方均有实质代表、符合 B2 conflict 的本意、独立于最终生产输出也能自证成立。

---

## 逐 Ticker 裁定结果

| Ticker | Development Plan 候选 | 冻结 Reference Run 证据 | 最终裁定 Expected Main Conflict | Gold Evaluable |
|---|---|---|---|---|
| NVDA | A101↔A304（未曾在任何冻结 run 中实际出现） | e3eb3909-3744-4a02-9b32-b225cf6ef665（2026-08-11 冻结）实际观测到 **A301↔A304** | **A301↔A304** | ✅ 是 |
| QQQ | A001↔A501 | `run_bound_expectations: null`（不存在任何冻结 reference run） | 无 | ❌ 否 |
| MSFT | A102↔A304 | 该 pair 在 taxonomy 中 `conflict_alphas=[]`，PD-017 已正式拒绝 | 无（唯一候选已被拒绝，且结构非法） | ❌ 否 |
| SNDK | Development Plan 未给出任何期望值 | `run_bound_expectations: null`；A201↔A304 结构非法/已拒绝 | 无 | ❌ 否 |
| TSM | Development Plan 未给出任何期望值 | `run_bound_expectations: null`；A201↔A304 结构非法/已拒绝 | 无 | ❌ 否 |
| AMD | Development Plan 未给出任何期望值 | `run_bound_expectations: null`；A201↔A304 结构非法/已拒绝 | 无 | ❌ 否 |

**Gold Evaluable：1 / 6（仅 NVDA）**

---

## 为什么其余 5 个 ticker 无法构造合法 Gold 标签

`j2_provisional_regression_labels_v0.2.yaml` 文件本身在开头明确写道：

> "NONE of the six tickers currently has a formally John-approved, artifact-complete, version-locked reference run."

独立核查确认：QQQ、MSFT、SNDK、TSM、AMD 五个 ticker 的 `run_bound_expectations` 字段均为 `null`——即从未有任何一次冻结的历史执行为这些 ticker 产生过真实的 Main Conflict 观测证据。它们唯一的"候选"要么是从未被任何 run 实现过的规划期假设（QQQ），要么在 canonical taxonomy 中结构性非法且已被正式拒绝（MSFT、SNDK、TSM、AMD 的 A102/A201 相关候选）。

在不违反以下限制的前提下，没有办法为这 5 个 ticker 构造出真正独立、非拼凑的 Gold 标签：
- 不能从最终观测的 Main Conflict 反推期望值
- 不能仅因旧的 provisional regression label 曾经期望过而拿来当作 approved gold
- 不能复活已拒绝的 pair（MSFT A102↔A304；SNDK/TSM/AMD A201↔A304）

---

## 拒绝的历史 Pair（保持不变）

| Pair | 状态 |
|---|---|
| MSFT A102↔A304 | REJECTED_OR_SUPERSEDED（PD-017），保持拒绝，未被复活 |
| SNDK A201↔A304 | REJECTED_OR_SUPERSEDED，保持拒绝，未被复活 |
| TSM A201↔A304 | REJECTED_OR_SUPERSEDED，保持拒绝，未被复活 |
| AMD A201↔A304 | REJECTED_OR_SUPERSEDED，保持拒绝，未被复活 |

---

## Freeze 完整性

`labels_frozen_before_final_comparison`: **true**

`labels_derived_from_final_observed_main_conflict`: **false**

`canonical_ontology_modified`: **false**

`b1_b2_b4_semantics_modified`: **false**

本文件（`main_conflict_gold_adjudication_v0.1.2.1.json`）的 SHA-256：

`efbc284b7a67990737136511e9734205b5e8fd3888015602121b848ab0ec47c4`

**Provider calls：0　TradingAgents calls：0**
