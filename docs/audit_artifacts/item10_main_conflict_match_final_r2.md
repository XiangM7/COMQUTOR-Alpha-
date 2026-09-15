# ❌ Main Conflict Regression Match（r2，修正版）

本页取代 `item10_main_conflict_match_final.md`（r1）。r1 仅有 1/6 ticker 可评估；r2 使用正确的权威层级（Development Plan 明文 > canonical ontology + John 已批准 exposure seed > provisional label > 历史 run 观测）重新裁定，全部 6 个 ticker 现在均可评估。

| Ticker | Expected | Final Observed | Result |
|---|---|---|---|
| NVDA | A101↔A304 | A101↔A304 | ✅ |
| QQQ | A001↔A501 | A101↔A304 | ❌ |
| MSFT | A301↔A304 | A101↔A304 | ❌ |
| SNDK | A301↔A304 | A304↔A601 | ❌ |
| TSM | A301↔A304 | A101↔A304 | ❌ |
| AMD | A101↔A304 | A101↔A304 | ✅ |

---

## Main Conflict Match

**2 / 6**

## Acceptance Target

**>= 4 / 6**

## Final Status

**FAIL**

---

## Gold Evaluable Ticker Count

**6 / 6**（相比 r1 的 1/6，本次全部 ticker 均有合法、独立、冻结的 Expected Main Conflict）

## Rejected / Undeclared Pair Violations

**0**

## Gold Labels Frozen Before Final Comparison

**YES**（见 `main_conflict_gold_contract_v0.1.2.1_r2.json`，SHA-256 `20a2056539812caf979c878b60a77c30621979ba965b4fa7e207b85e9b4a9d22`）

---

## 结论

使用正确的权威层级后，Gold 覆盖率从 1/6 提升到 6/6，但**实际命中数仍为 2/6，仍未达到 John 要求的 ≥4/6**，结果仍为 **FAIL**。这不是流程问题——而是当前生产系统的实际 Main Conflict 输出（对 QQQ、MSFT、SNDK、TSM 四个 ticker）确实偏离了基于 Development Plan、canonical ontology 与 John 已批准 exposure seed 得出的期望结构。这是一个关于系统行为本身的真实发现，而非证据收集不完整导致的假阴性。
