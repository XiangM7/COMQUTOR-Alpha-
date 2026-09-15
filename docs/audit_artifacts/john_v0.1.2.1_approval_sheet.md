# COMQUTOR Alpha v0.1.2.1 — John Review & Approval

为了将当前 diagnostic QA 结果升级为正式 regression acceptance，需要确认以下 v0.1.2.1 frozen regression reference contract。以下建议基于现有 Development Plan、历史 regression expectations、canonical ontology 与最终 Fresh Production E2E 整理。请 John 确认、修改或拒绝。

---

## A. Alpha Regression Gold

| Ticker | Proposed v0.1.2.1 Gold Alpha | Final E2E |
|---|---|---|
| QQQ | A001, A003 | 2/2 detected |
| MSFT | A101, A102, A304 | 3/3 detected |
| SNDK | A201, A301, A304 | 3/3 detected |
| TSM | A103, A304 | 2/2 detected |
| AMD | A101, A201 | 2/2 detected |

**Overall：12 / 12 detected**

□ Approve as v0.1.2.1 frozen regression gold
□ Approve with modifications
□ Keep diagnostic-only

**重要说明：** 这些 Gold 仅适用于 v0.1.2.1 冻结 regression reference set，不代表未来任何时间同一 ticker 都必须产生完全相同的 Alpha。

---

## B. Main Conflict Regression Gold

当前最终 production 观测结果（Proposed Gold / Final Observed Output）：

| Ticker | Main Conflict |
|---|---|
| NVDA | A101 ↔ A304 |
| QQQ | A101 ↔ A304 |
| MSFT | A101 ↔ A304 |
| SNDK | A304 ↔ A601 |
| TSM | A101 ↔ A304 |
| AMD | A101 ↔ A304 |

- Final production Main Conflict：6/6 non-null
- Negative constraint violations：0
- 以上所有 pair 在当前 canonical ontology 下均合法。

□ Approve all six as v0.1.2.1 frozen Main Conflict gold
□ Approve with modifications
□ Keep diagnostic-only

**重要：** 以上结果为 **Proposed Gold / Final Observed Output**，尚未被正式批准为 gold。

---

## C. Evidence Review Critical Reversal

| 项目 | 内容 |
|---|---|
| Row | holdout5-005 |
| Ticker | AMD |
| Alpha | A601 Narrative Momentum |
| Frozen review | supports_alpha |
| System | opposes_alpha |
| Formal adjudication | BOTH_REASONABLE_AMBIGUOUS |
| 当前 raw critical reversal count | 1 |

请 John 选择：

□ supports_alpha is the final Gold label
□ opposes_alpha is the final Gold label
□ Treat this row as ambiguous / exclude it from the critical-reversal gate
□ Other：__________________

（此项由 John 决定，工程侧不代为判断。）

---

## D. candidate_active Product Definition

当前 authoritative display states 包括：

candidate / active / capped_active / dominant / regime_level

目前尚不存在针对 **candidate_active** 的 authoritative Product definition。工程侧刻意未自行发明新的 threshold 或语义状态。

请 John 选择：

□ Keep existing candidate; candidate_active is not needed
□ Define candidate_active as：__________________
□ Defer candidate_active to a later version

---

## E. Final Approval

当前技术状态：

| 指标 | 结果 |
|---|---|
| Fresh Production E2E | 6 / 6 |
| Artifact completeness | 54 / 54 |
| Run-id consistency | 6 / 6 |
| Semantic coverage | 98.38% |
| Historical Alpha callouts | 12 / 12 detected |
| Final Main Conflicts | 6 / 6 non-null |
| Negative constraint violations | 0 |
| Full test suite | 3900 passed / 6 known pre-existing failures / 47 skipped |
| New regression | 0 |

### John Final Decision

□ APPROVED

□ APPROVED WITH CHANGES

□ NEEDS REVISION

Comments:

____________________________________

____________________________________

Reviewer: John

Date: ____________
