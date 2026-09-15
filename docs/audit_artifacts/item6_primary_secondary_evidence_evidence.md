# Item 6 — Primary / Secondary Evidence Qualification

John 原始要求：

"Separate Primary Evidence Agents from Secondary / Decision Agents. Trader / portfolio_manager / debate agents should not directly inflate activation unless they contain ticker-specific causal evidence."

---

## 1. Evidence Source Role

| Source Type | Role | Activation Eligibility |
|---|---|---|
| Primary research agents | PRIMARY_RESEARCH | 按原有 Evidence qualification rules |
| trader | SECONDARY_DECISION_OR_DEBATE | 仅在自身提供独立 ticker-specific causal evidence 时 |
| portfolio_manager | SECONDARY_DECISION_OR_DEBATE | 仅在自身提供独立 ticker-specific causal evidence 时 |
| bull/bear debate agents | SECONDARY_DECISION_OR_DEBATE | 仅在自身提供独立 ticker-specific causal evidence 时 |
| unknown source | UNKNOWN | 默认不参与 Activation |

---

## 2. Qualification Rule

Secondary evidence duplicates an existing Primary fact
→ SECONDARY_DUPLICATE_OF_PRIMARY
→ does NOT increase Activation
→ does NOT independently satisfy B2 evidence count

Secondary-only evidence
→ must pass existing ticker-specific qualification
→ must contain asserted causal activation evidence
→ only then may qualify

否则：Evidence remains auditable but does not count toward Activation / B2。

**Secondary evidence is NOT globally banned。Independent ticker-specific causal evidence may still qualify。**

---

## 3. Six-Ticker Before / After Validation

| Metric | Before | After | Result |
|---|---:|---:|---|
| Unique evidence facts feeding Activation | 1145 | 623 | -45.6% |
| Active Alphas | 46 | 38 | -8 |
| Admitted B2 Conflicts | 16 | 8 | -50% |

**Secondary duplicate inflation prevented: YES**

**Original Evidence retained for audit: YES**

**B1 semantic rules changed: NO**

**B2 thresholds changed: NO**

**B4 thresholds changed: NO**

---

## Conclusion

**本项已完成。**

Primary Research Evidence 与 Secondary / Decision Evidence 已建立明确资格边界。Trader、portfolio_manager 和 debate outputs 不能因为重复转述已有 Primary Evidence 而直接抬高 Activation 或 B2 Conflict；只有自身包含独立、ticker-specific、符合既有 causal evidence 条件的内容时才允许参与。
