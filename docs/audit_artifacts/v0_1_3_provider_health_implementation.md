# v0.1.3 Provider Health Diagnostic Layer

Implementation authorized, diagnostics only. **Provider calls: 0. TradingAgents calls: 0. Ticker runs: 0. HEAD unchanged (`9f228723fad5406c72e62beca67ec70ea0fdb004`). No commit. No push.**

## Executive Summary

```
Provider diagnostics implemented: YES
Alpha semantics changed:          NO

Runs replayed offline: 6
Provider degraded:     6/6
Benchmark review required: 5/6 (all except NVDA)

Confirmed impacted Alpha with a current Gold-miss consequence: TSM A301

New regressions: 0
Provider calls: 0
Ticker runs: 0
Gold unchanged: YES
```

## What Was Built

A single new, purely observational, read-only module: `comqutor_alpha/regression/provider_health_diagnostics.py`, plus `tests/test_provider_health_diagnostics.py` (32 tests). **Zero existing production files were modified.**

### Canonical Data Sources (no second logging system created)

- **`provider_failure_events`** — `error_logs/week2_llm_errors.jsonl` (raw, per-retry-attempt events).
- **`alpha_classifier_final_orphans`** — `alpha_matches.json`'s `match_status=='unavailable'` (canonical, since Pure-LLM Semantic Authority has no intermediate fallback for this task).
- **`evidence_stance_final_orphans` / `structure_extractor_final_orphans`** — `llm_semantic_calls.jsonl`'s `fallback_used` flag per task (both tasks *do* have a deterministic fallback; `fallback_used=True` is that call's final, non-LLM outcome — more precise than raw retry counting).
- **Call-attempt denominators** — `llm_semantic_manifest.json`'s `tasks`/`provider_call_count`, where available.

The existing `comqutor_alpha.regression.semantic_execution_health.compute_semantic_execution_health` is **reused directly** (imported, not duplicated) for its alpha_classifier coverage/health status. `regression_report_v3.py` (the Gold-adjacent report generator) was **deliberately left untouched** to keep zero coupling to any Gold-result computation path.

## No Alpha Semantic Effect — Proof

1. The module never imports `alpha_mapper.py`, `activation_scorer_v2.py`, `structure_extractor.py`, `graph_builder.py`, or `pipeline.py` (verified by test).
2. It only reads already-persisted JSON/JSONL files — never writes to any of them.
3. Byte-identical before/after hash checks on `alpha_matches.json` and `structure_graph.json` for all six real runs (verified by test) confirm zero mutation.
4. `pipeline.py` and `activation_scorer_v2.py` (the P0/P1-patched files) are confirmed byte-identical to their pre-this-task state via direct diff.

Detected Alpha sets, activation scores, levels, evidence groups, structure edges, main conflicts, Entity Exposure, and Alpha Memory are all **unchanged**.

## Metrics, Status Rules, and Policy

All required run-level metrics from Section 6 are implemented, each with an explicit denominator; every rate returns `None` (never a guess) when its denominator is unavailable.

- **`provider_health`**: `PROVIDER_DEGRADED` iff `provider_final_orphans_total > 0`; otherwise `PROVIDER_HEALTHY`. No arbitrary numeric threshold introduced.
- **`benchmark_review_required`**: `TRUE` iff `alphas_impacted_by_provider_failure >= 1` — a **manual-review trigger**, never an automatic rejection. `benchmark_auto_rejected` is always `False` in this implementation.
- **Policy**: `DEPENDS_ON_IMPACT` — manual review when ≥1 Alpha shows deterministic lineage-loss evidence; no automatic threshold-based exclusion yet.
- **`semantic_status`** (existing, unmodified) and **`provider_health`/`benchmark_review_required`** (new) are reported side by side, never collapsed — exactly the TSM example the task specifies:

```
semantic_status: PASS (unmodified)
provider_health: DEGRADED
benchmark_review_required: true
impacted_alpha_ids: ["A301", "A601"]
```

## Six-Run Offline Replay

| Ticker | Provider Health | Raw Failures | Final Orphans | Impacted Alphas | Benchmark Review |
|---|---|---:|---:|---|---|
| NVDA | DEGRADED | 113 | 45 | [] | false |
| QQQ | DEGRADED | 83 | 38 | [A501, A601] | true |
| MSFT | DEGRADED | 126 | 40 | [A301] | true |
| SNDK | DEGRADED | 144 | 54 | [A201] | true |
| TSM | DEGRADED | 128 | 42 | [A301, A601] | true |
| AMD | DEGRADED | 115 | 42 | [A301] | true |

All six runs' `provider_failure_events`/`semantic_critical_failure_events` match the prior blast-radius audit's regression expectations **exactly** (see `v0_1_3_provider_health_diagnostics.json`). Of the 5 flagged runs, only **TSM's** impacted set (A301) corresponds to a currently-open Gold miss — the other four runs' flagged alphas (QQQ A601, MSFT A301, SNDK A201, AMD A301, TSM's own A601) are already resolved Gold hits via independent evidence.

## Tests

- **`tests/test_provider_health_diagnostics.py`**: **32 passed, 0 failed** — covering event counting (A), retry-then-success (B), repeated-retry collapse (C), semantic-critical vs. presentation-only (D), the TSM A301 positive fixture (E), unrelated-miss negative controls across NVDA/MSFT/AMD/QQQ/SNDK (F), the benchmark-review trigger (G), no-auto-rejection (H), null-denominator handling (I), error-type aggregation including AMD's TRANSPORT_ERROR profile (J), traceability-unknown (K), no-artifact-mutation and no-scoring-module-coupling (L), and P0/P1 decoupling (M).
- **P0/P1 + 3 SHA guards**: **61 passed, 0 failed**.
- **Full backend suite**: **4075 passed, 21 failed, 3 errors, 47 skipped** — the 21 failures + 3 errors are byte-for-byte identical (by test name) to the accepted pre-existing baseline. **New regressions: 0.** (4075 = 4043 baseline + 32 new tests.)

## TSM Fresh-Rerun Readiness

**`TSM_FRESH_RERUN_READY = YES`** — the diagnostics layer works, Provider impact is visible (`A301` in `impacted_alpha_ids`, `benchmark_review_required=True`), zero Alpha semantic change, zero new regressions (full-suite confirmed). A fresh, separately-authorized TSM rerun is a live-Provider action outside this task's scope and was **not** performed here.

## Explicitly Not Done (deferred)

No Provider timeout/retry/backoff/concurrency/model/transport/prompt change. No frontend UI change (`UI_DEFERRED=true` — backend/audit-artifact output only). No wiring into `regression_report_v3.py`'s live Gold path. No automatic benchmark-rejection threshold. No fresh ticker rerun of any kind.

---

## Final Validation

Gold v1 / Gold Validity SHA-256 unchanged. P0/P1 CLOSED PASS intact. AMD A201 contamination still excluded; `company_names` still active; SNDK A102 negative control intact; QQQ ETF behavior unchanged. Alpha scores/levels/conflicts unchanged. No Provider config, retry logic, or prompts changed.

**Provider calls: 0. TradingAgents calls: 0. Ticker runs: 0. No commit. No push. No destructive git operations.**
