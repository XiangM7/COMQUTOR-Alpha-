# v0.1.3 Provider Health Diagnostics — Six-Run Offline Replay

Offline / read-only replay using `comqutor_alpha.regression.provider_health_diagnostics`. **Provider calls: 0. TradingAgents calls: 0. Ticker runs: 0.**

## John — Provider Health

```
Ticker  Provider Health     Raw Failures  Final Orphans  Impacted Alphas   Benchmark Review
NVDA    PROVIDER_DEGRADED   113           45             []                false
QQQ     PROVIDER_DEGRADED   83            38             [A501, A601]      true
MSFT    PROVIDER_DEGRADED   126           40             [A301]            true
SNDK    PROVIDER_DEGRADED   144           54             [A201]            true
TSM     PROVIDER_DEGRADED   128           42             [A301, A601]      true
AMD     PROVIDER_DEGRADED   115           42             [A301]            true

Runs semantic PASS:        6/6 (unaffected by this diagnostic layer)
Runs Provider DEGRADED:    6/6
Runs requiring benchmark review: 5/6 (all except NVDA)

Confirmed Provider-impacted Gold Alpha: TSM A301

Official Alpha Hit: 61.03% unchanged
No Alpha semantics changed.
```

**Note on scope**: `alphas_impacted_by_provider_failure` is a pure lineage-loss metric (Section 7's rule), not filtered to current Gold misses — it also correctly flags alphas that already have OTHER supporting evidence and remain Gold hits regardless (QQQ A601, TSM A601, MSFT A301-is-actually-a-hit... wait MSFT A301 IS the case: MSFT's impacted alpha A301 is already a Gold HIT via other evidence; SNDK's A201 is already a Gold HIT; AMD's A301 is already a Gold HIT). **Of the 5 flagged runs, only TSM's impacted set includes an Alpha (A301) that is currently a Gold MISS** — this is the one case with a real, actionable Gold-benchmark consequence; the other 4 runs' flagged alphas are already resolved via independent evidence and require no action beyond the manual-review acknowledgment the flag exists for.

## Validation Against Prior Audit

All six runs' `provider_failure_events` and `semantic_critical_failure_events` match the prior blast-radius audit's expected regression values exactly (NVDA 113/99, QQQ 83/71, MSFT 126/110, SNDK 144/128, TSM 128/114, AMD 115/99). `provider_final_orphans_total` is more precise than the prior audit's raw-log approximation, since it uses the canonical per-call `llm_semantic_calls.jsonl` `fallback_used` flag for evidence_stance_classifier/structure_extractor rather than raw retry-attempt counts — an intentional refinement, not a discrepancy.

---

**Provider calls: 0. TradingAgents calls: 0. Ticker runs: 0. No historical artifact mutated (byte-identical before/after, verified in tests).**
