# COMQUTOR Alpha — v0.2 QA 提交报告

## 1. Gold Labels v0.2

**附件：** `v0_2_gold_operational_contract.md`

Evidence-Conditional Acceptance（证据条件式验收）已生效。

**Formal Gold / blocking：** NVDA / QQQ / SNDK
**Silver Diagnostic / non-blocking：** MSFT / TSM / AMD

六项 Gold 规则语义：`must_detect_if_evidence_present`、`should_detect_if_supported`、`conditional_only`、`do_not_force`、`allowed_main_conflicts`、`forbidden_dominant_without_strong_evidence`。

---

## 2. Final Acceptance Table

**附件：** `v0_2_final_acceptance_table.json`

最终 Formal Gold：

NVDA PASS
QQQ PASS
SNDK PASS

**3 PASS / 0 FAIL / 0 REVIEW**
**`release_blocking_status = PASS`**

MSFT / TSM / AMD 保持非阻塞的 Silver Diagnostic 状态。

---

## 3. Conflict Discrepancy Adjudication

**附件：** `v0_2_conflict_discrepancy_final_resolution.md`

QQQ / MSFT / SNDK / TSM 的冲突差异裁定已完成，分类见附件。

`MARKET_CONDITION_CHANGED` 确认案例数 = **0**
未解决的阻塞性冲突问题数 = **0**

---

## 4. Version Naming

版本命名已经统一。原 v0.1.4 Final Acceptance Cleanup 基于 v0.1.3 feature baseline；相关 acceptance requirements 后续已迁移至 Gold v0.2，当前最终 Gold / acceptance / QA authority 统一使用 v0.2。

---

## 5. Evidence Failure Analysis

**附件：** `v0_2_evidence_failure_analysis.md`

34 / 34 Alpha Match failures 已分析
9 / 9 polarity failures 已分析

Alpha Match = **83.00%**
Polarity = **85.25%**
critical accepted support/opposition reversals = **0**

---

## 6. Alpha Memory

**SHADOW**

`activation_modulation_applied = false`

不影响 activation / dominant Alpha / regime / conflict admission / main conflict 的结果。

---

## 7. Product Demo Hardening

**附件：** `v0_2_product_demo_hardening_summary.md`

- Demo mode：`DEMO_READY`
- Structured summary：已实现并在 NVDA / QQQ / SNDK 验证通过
- Invalidation conditions：10/10 MVP Alphas 已接线，未接线 0，fallback 0
- Semantic classifier cost / latency：基线 ≈3141s → 最终 2043s，降低 **34.96%**，Requirement 已关闭
