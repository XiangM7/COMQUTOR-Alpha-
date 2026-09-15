# Alpha Memory Feedback-Loop Proof — Final (v0.1.3, Six-Ticker)

SHADOW ONLY. **Provider calls: 0. TradingAgents calls: 0. No fresh research this artifact.**

This is John's requested proof for Issue 6: memory/recurrence visibility exists end-to-end,
but remains audit-only/shadow — it never touches Activation, Conflict, or any other production
score. Built from the six FINAL_FRESH_SELECTED runs only (see
`v0_1_3_final_fresh_six_ticker_ledger.json`).

## End-to-end chain proved

1. **Persisted historical runs** — real prior runs' `structure_graph.json` +
   `tradingagents_comqutor_vocabulary_snapshot.json` exist on disk from previously-completed
   research, independent of this session.
2. **Stable atomic edge φ identity** — `comqutor_alpha/memory/phi_identity.py::compute_phi_edges`
   computes one `phi_id` per `(ticker, alpha_id, taxonomy_version, taxonomy_sha256, source,
   edge_type, target)` via `sha256` of canonical JSON. No runtime `hash()`, no timestamps/UUIDs
   in the identity.
3. **Exact cross-run matching** — `history_reader.py::find_prior_phi_edge_observations` finds
   prior runs sharing the *exact same* `phi_id` for this ticker, filtered by
   `artifact_manifest`-based run eligibility. No fuzzy/embedding/equivalence-table/motif matching
   anywhere.
4. **Recurrence observation** — `is_recurring = prior_observation_count >= 1`, plus real
   `first_seen` / `last_seen_prior` / `current_seen_at` timestamps.
5. **run_audit/API visibility** — the same `alpha_memory` section is written into
   `run_audit.json` at pipeline completion AND surfaced verbatim via
   `GET /api/research/{run_id}`'s `alpha_memory` field — confirmed byte-identical to the
   on-disk artifact for all six selected runs.

## Strongest example: NVDA (`57d7b4c4-dbb9-4134-b962-ee2a873941cc`)

9 current φ, **4 recurring**, 5 first-seen, 9 total prior observations, across 6 Alphas —
the clearest visible recurrence of the six.

| Alpha | Relation | Prior observations | Prior run IDs |
|---|---|---|---|
| A103 | `ai_capex --causal--> gpu_demand` | 3 | `2f8ee897`, `a8d47429`, `e3eb3909` |
| A103 | `inference_demand --supportive--> nvda_revenue_growth` | 1 | `948be419` |
| A301 | `gpu_demand --causal--> nvda_revenue_growth` | 2 | `2f8ee897`, `a8d47429` |
| A304 | `valuation_risk --conflicting--> nvda_revenue_growth` | 3 | `948be419`, `a8d47429`, `e3eb3909` |

(Full `phi_id`s and complete prior-run-ID lists are in the JSON companion.)

## All six tickers

| Ticker | Run ID | Current φ | Recurring φ | First-seen φ | Prior obs. total |
|---|---|---|---|---|---|
| NVDA | `57d7b4c4` | 9 | 4 | 5 | 9 |
| QQQ | `f88c8956` | 8 | 2 | 6 | 2 |
| MSFT | `43472ace` | 7 | 2 | 5 | 2 |
| SNDK | `e8e0f398` | 14 | 3 | 11 | 3 |
| TSM | `dfc7ceb3` | 9 | 2 | 7 | 3 |
| AMD | `949f685a` | 10 | 3 | 7 | 3 |

Zero recurrence would have been an equally acceptable, honestly-reported outcome — every
ticker here shows at least some real recurrence, none fabricated or lowered-threshold to
force a result.

## Explicit scope statement (what this is NOT)

- **No activation modulation** — `activation_modulation_applied` is hardcoded `false` in
  code, not merely false by data coincidence.
- **No conflict modulation** — Alpha Memory has zero code path into `conflict_detector.py`.
- **No invalidation implementation** — Lifecycle remains **MODEL 0**, confirmed by the
  Step 4A executability audit (0 of 30 taxonomy invalidation conditions executable from
  current data).
- **No expiry implementation.**
- **No failed/non-execution modulation.**

This is memory/recurrence **visibility**, not a feedback **effect** on scoring. That
distinction is the whole point of shadow mode.

**Provider calls: 0. TradingAgents calls: 0.**
