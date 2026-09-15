# Alpha Memory Feedback Loop — Proof (John's QA Issue #6)

**Real, selected, healthy NVDA production run. Zero Provider calls, zero TradingAgents calls used to produce this artifact — it reads only already-persisted data.**

## The feedback loop, shown end to end

```
current structure (NVDA run 2f8ee897, 15 causal structures)
        │
        ▼
matched stable phi identity (exact ticker+alpha+source+edge_type+target hash)
        │
        ▼
prior persisted run(s) — REAL run_ids, not simulated
        │
        ▼
recurrence/history summary
```

## Headline numbers (run `2f8ee897`, NVDA)

| Metric | Value |
|---|---|
| Current structures (atomic φ) | **15** |
| Recurring (matched to a prior run) | **6** |
| First seen (no prior match) | **9** |
| Total prior observations across the 6 recurring | **13** |

## The 6 recurring structures, with real source run evidence

| Alpha | Relation | Seen before in | First seen | Last prior |
|---|---|---|---|---|
| A001 | `rate_cut_cycle` --conflicting--> `valuation_risk` | 1 prior run | 2026-08-28 | 2026-08-28 |
| A101 | `ai_capex` --causal--> `gpu_demand` | **5 prior runs** | 2026-08-11 | 2026-09-02 |
| A102 | `inference_demand` --supportive--> `nvda_revenue_growth` | 2 prior runs | 2026-08-11 | 2026-09-02 |
| A103 | `ai_capex` --causal--> `gpu_demand` | 2 prior runs | 2026-08-11 | 2026-08-28 |
| A103 | `ai_capex` --supportive--> `nvda_revenue_growth` | 2 prior runs | 2026-08-27 | 2026-08-28 |
| A301 | `gpu_demand` --causal--> `nvda_revenue_growth` | 1 prior run | 2026-08-28 | 2026-08-28 |

Every prior run listed above is a real, independently-executed NVDA production run already on disk — not a synthetic example.

## Why atomic recurrence, not whole-Alpha aggregate, is the proof

Only **1 of the 5** Alphas above (A301, which happens to have just one edge) shows a whole-Alpha aggregate match against any prior run. The other 4 Alphas' *overall* structure changed run to run — yet their individual causal relations **did** recur, exactly. This is why atomic edge identity, not the coarser whole-Alpha fingerprint, is the meaningful feedback-loop signal: the aggregate alone would show almost no memory at all.

## This does not change research conclusions

`activation_modulation_applied: false` throughout. Every number above is computed *after* Activation, Conflict, and Evidence qualification already finished — descriptive and audit-only, never an input back into them.

## Files used

`structure_graph.json` + `tradingagents_comqutor_vocabulary_snapshot.json` for the current run and every prior run listed above — all already-persisted, real production artifacts.
