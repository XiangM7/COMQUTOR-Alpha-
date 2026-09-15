# ❌ Main Conflict Regression Match

| Ticker | Expected | Final Observed | Result |
|---|---|---|---|
| NVDA | A301↔A304（唯一有冻结 reference run 证据支持） | A101↔A304 | ❌ |
| QQQ | 无合法冻结期望值 | A101↔A304 | ⚪ N/A |
| MSFT | 无合法冻结期望值（唯一候选 A102↔A304 已被 PD-017 正式拒绝） | A101↔A304 | ⚪ N/A |
| SNDK | 无合法冻结期望值 | A304↔A601 | ⚪ N/A |
| TSM | 无合法冻结期望值 | A101↔A304 | ⚪ N/A |
| AMD | 无合法冻结期望值 | A101↔A304 | ⚪ N/A |

---

## Main Conflict Match

**0 / 6**

（6 个 ticker 中，只有 NVDA 拥有独立、冻结、可验证的 Expected Main Conflict；其余 5 个 ticker 不存在任何合法的冻结期望值，因此不可评估。唯一可评估的 NVDA 也未命中——预期 A301↔A304，实际生产输出为 A101↔A304。）

## Acceptance Target

**>= 4 / 6**

## Final Status

**FAIL**

---

## Gold Evaluable Ticker Count

**1 / 6**（仅 NVDA，依据一次真实、独立、冻结的 reference run `e3eb3909-3744-4a02-9b32-b225cf6ef665` 的历史观测结果）

即使这唯一可评估的 ticker 命中，理论上限也只有 1/6，无法达到 John 要求的 ≥4/6 门槛。

## Rejected / Undeclared Pair Violations

**0**

（MSFT A102↔A304、SNDK/TSM/AMD 的 A201↔A304 均保持已拒绝/非 canonical 状态，未被复活或强行纳入 Gold。）

## Gold Labels Frozen Before Final Comparison

**YES**

裁定过程（见 `main_conflict_gold_adjudication_v0.1.2.1.json`，SHA-256 `efbc284b7a67990737136511e9734205b5e8fd3888015602121b848ab0ec47c4`）与冻结合约（见 `main_conflict_gold_contract_v0.1.2.1.json`）均在查看当前 v0.1.2.1 最终生产输出的 Main Conflict 结果**之前**完成并冻结。比对之后未对任何 Gold 标签做任何修改。

---

## 结论

在不违反"不得从最终输出反推期望值 / 不得复活已拒绝 pair / 不得把 provisional 标签当作已批准 gold"这些约束的前提下，经过对 Development Plan、当前权威 label 文件、canonical taxonomy 与既有 PD 决定的完整核查，**当前只有 1 个 ticker（NVDA）拥有真正独立、冻结的 Main Conflict 期望值，且该唯一可评估项也未命中**。这不是流程未完成，而是现有证据本身的客观结论——真正的修复路径是由 John 为其余 5 个 ticker 正式批准一次 version-locked reference run，而不是在缺乏证据的情况下人为制造及格结果。
