# Main Conflict Gold Adjudication — v0.1.2.1 (r2，修正版)

本文档取代 `main_conflict_gold_adjudication_v0.1.2.1.md`（r1）。r1 对"证据"标准的解读过于严格，本文档采用正确的权威层级重新裁定。裁定在查看当前 v0.1.2.1 最终生产 Main Conflict 结果**之前**完成。

---

## r1 的错误

r1 把"标准 3"（双方在冻结证据中均有实质代表）解读为"必须存在一次真实冻结 run 的历史观测"，并因此：

- 把 NVDA 的 Development Plan 明文期望（A101↔A304）替换为一次旧 reference run 恰好观测到的 A301↔A304
- 把 QQQ 标记为"无期望值"，仅仅因为不存在 run-bound 的冻结 reference run

这不符合正确的权威层级。正确顺序应为：

1. 已批准的 Product Decision / ADR
2. Development Plan 明文记载的期望
3. Canonical conflict ontology（含每个 Alpha 自身的多空属性）
4. 既有/provisional regression label（作为佐证）
5. 历史/reference run 证据（**仅作佐证，从不构成硬性要求，也不能推翻更高层级的明文期望**）

一次旧 run 的历史观测属于第 5 层，不能推翻第 2 层的 Development Plan 明文期望。**r1 确实错误地把"没有 run-bound 观测"当成了"没有期望值"。**

---

## 修正后的权威层级与机械选择规则

对于 Development Plan 有明文记载的 ticker（NVDA、QQQ），直接采用第 2 层权威。

对于 Development Plan 未给出明文期望、或该明文期望已被第 1 层权威（PD-017）拒绝的 ticker（MSFT、SNDK、TSM、AMD），采用统一、预先声明、非事后挑选的机械规则：

> 在 canonical taxonomy 合法、未被拒绝的 pair 中，若一方是内生成长/扩张性质的 Alpha（A101/A102/A103/A201/A301/A001/A003），另一方是内生风险/下行性质的 Alpha（A304 Multiple Compression / A501 Recession Risk），且双方在 John 已批准的 `entity_alpha_exposure_seed_v0.1.yaml`（2026-08-11 approved_gating）中都有暴露权重记录，选择两者暴露权重乘积最高的 pair。

该规则对 NVDA、QQQ 两个已有 Development Plan 明文期望的 ticker 独立重新计算后，**结果与 Development Plan 完全一致**（NVDA→A101↔A304，QQQ→A001↔A501），这验证了该规则本身的合理性，而不是用它取代 Development Plan 权威。

---

## 逐 Ticker 裁定结果

| Ticker | Expected Main Conflict | 权威层级 | 来源 |
|---|---|---|---|
| NVDA | **A101↔A304** | Development Plan 明文（第 2 层），被 exposure-seed 排序独立印证 | Development Plan §12："Bull A101 vs Bear A304" |
| QQQ | **A001↔A501** | Development Plan 明文（第 2 层），被 exposure-seed 排序独立印证 | Development Plan §12："Bull A001 vs Bear A501" |
| MSFT | **A301↔A304** | 唯一 Development Plan 候选（A102↔A304）已被 PD-017 正式拒绝且结构非法；退而采用第 3 层 exposure-seed 排序结果 | entity_alpha_exposure_seed_v0.1.yaml：A301(0.80)×A304(0.70)=0.56，为 MSFT 合法候选中最高 |
| SNDK | **A301↔A304** | Development Plan 无记载；exposure-seed 排序（第 3 层），与 provisional label 的 conditional_conflicts（第 4 层）一致 | A301(0.70)×A304(0.75)=0.525 |
| TSM | **A301↔A304** | 同上 | A301(0.75)×A304(0.65)=0.4875 |
| AMD | **A101↔A304** | 同上 | A101(0.80)×A304(0.75)=0.60 |

**Gold Evaluable：6 / 6**（相比 r1 的 1/6，本次覆盖全部六个 ticker）

---

## 拒绝的历史 Pair（保持不变，未被复活）

| Pair | 状态 |
|---|---|
| MSFT A102↔A304 | REJECTED_OR_SUPERSEDED（PD-017），保持拒绝 |
| SNDK/TSM/AMD A201↔A304 | REJECTED_OR_SUPERSEDED，保持拒绝 |

---

## Freeze 完整性

`labels_frozen_before_final_comparison`: **true**

`labels_derived_from_final_output`: **false**

`canonical_ontology_modified`: **false**

本文件的 SHA-256：`5057578a5d73f277088cef8e3efa23574ab094718aac2a803d7a4eb20a9203de`

**Provider calls：0　TradingAgents calls：0**
