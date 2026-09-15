# ✅ Item 5 — Conflict Ontology / Regression Labels 对齐

| Conflict Pair | Authority Review | Canonical Ontology | Regression Treatment | Result |
|---|---|---|---|---|
| A102 ↔ A304 | REJECTED / SUPERSEDED (PD-017) | NOT ADDED | NOT REQUIRED | ✅ ALIGNED |
| A201 ↔ A304 | NON-CANONICAL / NOT AUTHORIZED | NOT ADDED | NOT REQUIRED | ✅ ALIGNED |

---

**Regression / Ontology contradictions: 0**

**Rejected / non-canonical pairs added: 0**

**Negative constraint violations: 0**

---

## 验证依据

**Canonical Ontology**（`alpha_taxonomy_v1.yaml`，SHA-256 与冻结基线一致，未改动）：A102 与 A201 的 `conflict_alphas` 均为空列表 `[]`，即两者从未在 canonical taxonomy 中声明与 A304 存在冲突关系。当前合法 canonical pair 集合保持六对不变：A101↔A304、A301↔A304、A001↔A501、A003↔A501、A601↔A304、A601↔A501。

**Authority 决定**：A102↔A304 由 PD-017（`docs/specs/product_decisions_and_unknowns.md`）正式裁定为 `REJECTED_BY_INDEPENDENT_LLM_ADJUDICATION`，未加入 canonical ontology。A201↔A304 结构上同样非法（`conflict_alphas=[]`），PD-017 自身的推理已明确将其列为同类应被拒绝的过度泛化风险（"would create pressure to also add ... A201__A304"）。两者均未被复活。

**当前 Regression Acceptance 逻辑**（实际运行验证，非仅阅读代码）：
- `comqutor_alpha/regression/labels_v2.py` 的 `load_j2_labels_v2()` 对当前 `j2_provisional_regression_labels_v0.2.yaml` 加载校验 **通过，无异常** —— A102__A304 位于 MSFT 的 `remove_while_undeclared`，A201__A304 位于 SNDK/TSM/AMD 的 `remove_while_undeclared`，均不在任何 executable 类别（`required_conflicts`/`conditional_conflicts`/`allowed_conflicts`）中。该 validator 会对任何试图把非 canonical pair 放入 executable 类别的行为**主动报错**（`LABEL_V2_UNDECLARED_EXECUTABLE_CONFLICT_PAIR`），已有专项测试锁定此行为。
- `comqutor_alpha/regression/authority_contract.py` 的 `apply_main_conflict_authority()` 对 MSFT/SNDK/TSM/AMD 实际运行结果计算，均返回 `excluded_from_acceptance_denominator` 包含该拒绝 pair，`ticker_acceptance_status = NOT_GOLD_EVALUABLE`（从不计入正式 PASS/FAIL 分母）。
- `check_negative_constraints()` 对**当前最终选定六个生产 run**（NVDA/QQQ/MSFT/SNDK/TSM/AMD 全部六个 run_id 的真实 `conflicts.json`）逐一核查：A102__A304 与 A201__A304 在全部六个 run 的 admitted 与 candidate 结果中**从未出现**（结构上根本不会被枚举，因为不是 canonical pair）—— **违规数 = 0**。

## Conclusion

John Item 5 已完成。

John 的要求是：
若 A102__A304 / A201__A304 确实属于有效 expected conflicts，
则补入 canonical ontology。

Authority review 最终确认这两个条件均不成立，因此没有强行加入 ontology；
同时 current regression acceptance 已与 canonical ontology 对齐，
不再要求 rejected / non-canonical pair 作为正式 PASS 条件。

---

# PASS — JOHN ITEM 5 FULLY ALIGNED
