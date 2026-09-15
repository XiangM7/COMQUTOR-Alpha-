# v0.1.2.1 — John Acceptance Closure

| Acceptance Target | Final Result | Requirement | Status |
|---|---:|---:|---|
| Fresh E2E smoke test | NVDA YES / QQQ YES (6/6 proven fresh) | NVDA + QQQ minimum | PASS |
| Ticker consistency | 6/6 (4 authoritative sources agree) | 6/6 | PASS |
| Artifact completeness | 54/54 | 54/54 | PASS |
| Expected Alpha hit rate | 12/12 = 100% | >=75% | DIAGNOSTIC |
| Main Conflict match | 0/6 tickers gold-evaluable | >=4/6 | NOT_GOLD_EVALUABLE |
| Evidence polarity accuracy | 85.25% (52/61 eligible) | >=80% | PASS |
| Alpha match accuracy | 83.00% (166/200) | >=80% | PASS |
| Internal QA contradictions | 0 | 0 | PASS |

---

## 1. Fresh E2E 证明

NVDA fresh production E2E: **YES**（run_id `a8d47429-a47a-446b-93c4-dd718b8e2ff9`，Step 11 真实重跑，非 dedup 命中，真实 TradingAgents 派发 + 真实 Provider 调用）

QQQ fresh production E2E: **YES**（run_id `defeb528-673e-44f7-8d94-c0abdfef03d4`，Step 10 原始真实执行并保留，非 offline replay）

MSFT / SNDK / TSM / AMD 同样均为真实 fresh production E2E（详见 JSON `fresh_e2e_proof`）。本项结论：**不需要为本次 closure 任务重新发起 Provider / TradingAgents 调用** —— 现有已完成的 fresh E2E 证据已经充分。

---

## 2. Ticker Consistency（6/6）

已对照 4 份当前权威文件（`qa_closure_index.json`、`a4_regression_runner_report.json`、`item6_a2_artifact_completeness.json`、`final_six_ticker_production_e2e_v0.1.2.1_r2.json`）逐 ticker 核对最终选定 run_id，**全部一致，无矛盾**。历史（Step 10 原始、后被替换的）run_id 均已在各文件中明确标注为历史/已被 Step 11 取代，未被计入当前矛盾。

---

## 3. Artifact Completeness（54/54）

6 个 ticker × 9 个核心 artifact（metadata.json / raw_agent_outputs.json / structured_agent_outputs.json / evidence_facts.json / alpha_matches.json / structure_graph.json / alpha_activations.json / conflicts.json / run_audit.json）= 54，**全部存在，无缺失**。

---

## 4. Expected Alpha Hit Rate — 诊断结果，非已批准 Gold

12/12 = 100%，达到 John 要求的 ≥75% 门槛。

但 `approved_gold_alpha_expectations = 0` —— 这 12 项历史 callout 目前**没有任何一项获得正式批准的 Gold 权威**，均为 documented/provisional 参考。因此本结果标注为 **DIAGNOSTIC**，而非 approved-gold PASS。

---

## 5. Main Conflict Match — 严格评估结果：NOT_GOLD_EVALUABLE

| Ticker | Expected Main Conflict | Authority | Final Observed | Match? |
|---|---|---|---|---|
| NVDA | A101↔A304 (DOCUMENTED_EXPECTATION，已降级为 conditional，无批准/无绑定参考 run) | 非 Gold | A101↔A304 | 文本相符，但无 Gold 权威 |
| QQQ | A001↔A501 (DOCUMENTED_EXPECTATION，已降级为 conditional) | 非 Gold | A101↔A304 | 不符 |
| MSFT | A102↔A304 (REJECTED_OR_SUPERSEDED，PD-017) | 已拒绝 | A101↔A304 | 参考本身无效 |
| SNDK | A201↔A304 (REJECTED_OR_SUPERSEDED) / A301↔A304 (PROVISIONAL) | 均非 Gold | A304↔A601 | 均不符 |
| TSM | A201↔A304 (REJECTED_OR_SUPERSEDED) / A301↔A304 (PROVISIONAL) | 均非 Gold | A101↔A304 | 均不符 |
| AMD | A201↔A304 (REJECTED) / A101↔A304 (PROVISIONAL) / A301↔A304 (PROVISIONAL) | 均非 Gold | A101↔A304 | 与 provisional 项文本相符，但无 Gold 权威 |

**6 个 ticker 中，0 个拥有 `valid_as_exact_regression_gold = true` 的期望标签。**

"Main Conflict non-null"（当前 6/6 均产生 admitted main conflict）是一个诊断性技术事实，**绝不能替代**"Main Conflict 命中已批准期望值"这一要求。由于不存在任何一个具备 Gold 权威的期望 Main Conflict，John 要求的 ≥4/6 判定在当前权威状态下**不可评估**。

结果：**NOT_GOLD_EVALUABLE**（非制造性的 ≥4/6 数字）。

---

## 6. Evidence Review Acceptance（沿用 Item 9 已建立的 directional eligibility contract）

- Alpha match accuracy：166/200 = **83.00%**（≥80% PASS）
- Polarity accuracy（eligible set，已排除 1 条 AMBIGUOUS_DIRECTION 行 `holdout5-005`）：52/61 = **85.25%**（≥80% PASS）
- Critical support/opposition reversal（eligible）：**0**（原始历史值 1，因该行属于 AMBIGUOUS_DIRECTION 而被排除出 acceptance 分母，非因判定系统正确而清零；原始记录完整保留于 audit provenance）

---

## Call Accounting

**Provider calls（最终选定六个 run 自身 manifest 汇总，Week2/B1 语义 LLM 调用）：3639**

定义：仅统计 6 个最终选定 run_id 各自持久化的 `llm_semantic_manifest.json` 中的 `provider_attempts`（Alpha Mapper + evidence_stance_classifier）。不包含 Step 11 的 11 次 health-probe 调用（health-probe 属于额外 QA 探测，非最终 run 本身的执行成本，单独列出）。若合并 health-probe：3639 + 11 = 3650。

**TradingAgents calls：**

- 最终基线中成功执行数：**6**（每个最终选定 run_id 对应 1 次成功的 TradingAgents 执行：NVDA/MSFT/TSM 来自 Step 11 重跑，QQQ/SNDK/AMD 来自 Step 10 原始执行并保留）
- 建立该基线全过程中的真实派发尝试总数：**14**（Step 10：11 次 [1 次成功 NVDA + 5 次预充值前 402 失败 + 5 次充值后成功]；Step 11：3 次 [NVDA 1 次成功 + MSFT 1 次强制重试成功 + TSM 1 次强制重试成功]）
- 另有 2 次 Step 11 的 request-fingerprint dedup 命中（MSFT、TSM 首次重跑各 1 次），**从未真正到达 TradingAgents**，不计入以上派发尝试数，单独列出

**额外 QA / 重试 / 探测调用（不计入以上最终 run 执行成本）：**
- Health probes：11（Provider 调用，Step 11 重跑前的真实性探测）
- Degraded-run retries：3（NVDA/MSFT/TSM，已包含在上方 14 次真实派发尝试内）
- Payment-failed attempts：5（Step 10 预充值前的 402 失败）
- Request-dedup non-executions：2（MSFT、TSM 首次重跑，从未到达 TradingAgents/Provider）

本次 closure 任务自身执行期间：**Provider calls = 0，TradingAgents calls = 0**（本任务未发起任何新的 Provider 或 TradingAgents 调用，全部数字来自既有已持久化的审计 artifact）。

---

## Overall Engineering Acceptance

**PARTIAL — AUTHORITY BLOCKER ONLY**

所有工程侧可控、可机械验证的门槛均为清晰 PASS：Fresh E2E（NVDA/QQQ 及全部六个 ticker）、Ticker consistency 6/6、Artifact completeness 54/54、Evidence polarity accuracy 85.25% ≥80%、Alpha match accuracy 83.00% ≥80%、Internal QA contradictions = 0。

未能达成清晰数字 PASS 的两项——Expected Alpha hit rate（DIAGNOSTIC，12/12=100% 但未获批准 Gold）与 Main Conflict match（NOT_GOLD_EVALUABLE，6 个 ticker 中 0 个拥有已批准 Gold 期望标签）——完全是因为**缺少 John 对 Gold Alpha / Main Conflict 参考集的正式批准**（见 `john_v0.1.2.1_approval_sheet.md` A、B 两节），而不是因为存在任何未完成的工程工作、代码缺陷或未解决的 QA 问题。

---

## Production Integrity

**production_semantic_code_changed:** NO
**alpha_taxonomy_changed:** NO
**canonical_conflict_ontology_changed:** NO
**b1_b2_b4_thresholds_changed:** NO
**john_approved:** false（PENDING_JOHN_APPROVAL，本任务未且不能自行设置为 true）

**Provider calls (this closure task):** 0
**TradingAgents calls (this closure task):** 0

**Commit:** NO　**Push:** NO
