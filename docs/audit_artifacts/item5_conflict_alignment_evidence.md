# Item 5 — Canonical Conflict Pairs / Regression Labels 对齐验证

John 原始要求：
"Align canonical conflict pairs with regression labels. If A102__A304 and A201__A304 are expected conflicts, add them to the canonical conflict ontology."

本项首先对这些 historical expected pairs 进行 authority audit，只有得到有效 authority 支持的 pair 才允许进入 canonical ontology。不得为了 regression 数字直接添加 provisional / rejected pair。

---

## 1. Historical Expected Pair Authority Audit

| Ticker | Historical Expected Pair | Authority Result | Final Treatment |
|---|---|---|---|
| MSFT | A102 ↔ A304 | REJECTED_OR_SUPERSEDED | NOT ADDED |
| SNDK | A201 ↔ A304 | REJECTED_OR_SUPERSEDED / NON-CANONICAL | NOT ADDED |
| TSM | A201 ↔ A304 | REJECTED_OR_SUPERSEDED / NON-CANONICAL | NOT ADDED |
| AMD | A201 ↔ A304 | REJECTED_OR_SUPERSEDED / NON-CANONICAL | NOT ADDED |

**Authority note：**

- MSFT A102__A304 is covered by the existing rejection/supersession authority identified in the regression-label authority audit / PD-017 history。
- A201__A304 is not declared by the current canonical ontology for the affected ticker expectations。
- These historical expectations must not be used to force production ontology。

---

## 2. Regression Contract Alignment

- REJECTED_OR_SUPERSEDED expectations are excluded from formal regression acceptance denominators。
- PROVISIONAL_AI_PREDICTED expectations remain diagnostic-only。
- Only valid canonical / approved authority may define production conflict behavior。
- No rejected pair was added merely to improve regression match rate。

---

## 3. Final Fresh Production Validation

| Ticker | Final Main Conflict | Canonical Validation |
|---|---|---|
| NVDA | A101 ↔ A304 | PASS |
| QQQ | A101 ↔ A304 | PASS |
| MSFT | A101 ↔ A304 | PASS |
| SNDK | A304 ↔ A601 | PASS |
| TSM | A101 ↔ A304 | PASS |
| AMD | A101 ↔ A304 | PASS |

**Final Main Conflicts: 6 / 6 non-null**

**Rejected / undeclared conflict pairs admitted: 0**

**Negative constraint violations: 0**

---

## Conclusion

**本项已完成。**

完成内容不是将 A102__A304 / A201__A304 强行加入 ontology，而是完成 regression-label authority audit 后，使 regression contract 与 canonical ontology 对齐：

- 应保留的 canonical pair 保留；
- rejected / superseded pair 不进入 ontology；
- rejected expectations 不再被错误计入正式 regression PASS/FAIL；
- Final Fresh Production E2E 中 negative constraint violations = 0。
