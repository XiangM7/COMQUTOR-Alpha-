# 1. Final acceptance table

| Acceptance Target | Final Result | Requirement | Status |
|---|---:|---:|---|
| Fresh E2E smoke test | NVDA YES / QQQ YES（6/6 proven fresh） | NVDA + QQQ minimum | **PASS** |
| Ticker consistency | **6/6** | 6/6 | **PASS** |
| Artifact completeness | **54/54** | 54/54 | **PASS** |
| Expected Alpha hit rate | **12/12 = 100%** | >=75% | **PASS** |
| Evidence polarity accuracy | **85.25% (52/61)** | >=80% | **PASS** |
| Alpha match accuracy | **83.00% (166/200)** | >=80% | **PASS** |
| Internal QA contradictions | **0** | 0 | **PASS** |

---

# 2. Provider / TradingAgents calls

- **provider_calls = 3639**
  Week2/B1 semantic LLM attempts summed from the 6 final selected runs' persisted manifests。

- **tradingagents_calls = 6 successful executions**
  最终选定六个 ticker 基线中的成功执行次数。

- **TradingAgents dispatch attempts across the full establishing lineage = 14**

- Provider health probes / retries 已与最终基线调用数明确分开统计，未混入以上数字。

---

# 3. Final Fresh E2E result

**Six-ticker production runs: 6/6 PASS**

**Semantic execution coverage: 98.38%**

**Historical Alpha callouts detected: 12/12**

**Negative constraint violations: 0**

**Fresh E2E Validation: PASS**
