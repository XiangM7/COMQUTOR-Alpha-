# Alpha/Conflict Gold Benchmark v1

```
benchmark_version:                alpha_conflict_gold.v1
benchmark_type:                   external_analyst_gold
as_of_date:                       2026-09-08
validation_mode_for_existing_runs: RETROSPECTIVE_GOLD_VALIDATION
created_after_current_run_outputs: true
frozen:                           true
SHA-256:                          99b1cd0247637054de360c3b5c0c00c7d8052152f3db1d29045eae1850bd8e9a
```

This Gold Benchmark defines **both**:
- Expected Alpha Hit Gold
- Main Conflict Gold

for the six FINAL_FRESH_SELECTED tickers. It is authored externally (analyst-provided expected sets), independent of these six runs' own outputs, and is **not** derived from `regression_label_authority_audit_v0.1.2.1.json` (whose own `APPROVED_GOLD` count remains zero, untouched).

**This benchmark was created after the current six runs already existed.** Any comparison against it is therefore `RETROSPECTIVE_GOLD_VALIDATION`, never a blind prospective benchmark. Once frozen, the identical file may be reused prospectively for a future six-ticker regression run without changing its labels — freeze the SHA-256 above, run new research later, and compare against this same file.

## Expected Alphas

| Ticker | Expected Alpha Set |
|---|---|
| NVDA | A101 AI Expansion, A102 Inference Explosion, A103 AI Infrastructure, A201 Semiconductor Supercycle, A301 Revenue Expansion, A304 Multiple Compression, A601 Narrative Momentum |
| QQQ | A101 AI Expansion, A103 AI Infrastructure, A201 Semiconductor Supercycle, A301 Revenue Expansion, A304 Multiple Compression, A601 Narrative Momentum |
| MSFT | A101 AI Expansion, A102 Inference Explosion, A103 AI Infrastructure, A301 Revenue Expansion, A304 Multiple Compression, A601 Narrative Momentum |
| SNDK | A102 Inference Explosion, A103 AI Infrastructure, A201 Semiconductor Supercycle, A301 Revenue Expansion, A601 Narrative Momentum |
| TSM | A101 AI Expansion, A103 AI Infrastructure, A201 Semiconductor Supercycle, A301 Revenue Expansion, A304 Multiple Compression, A601 Narrative Momentum |
| AMD | A101 AI Expansion, A102 Inference Explosion, A103 AI Infrastructure, A201 Semiconductor Supercycle, A301 Revenue Expansion, A304 Multiple Compression, A601 Narrative Momentum |

## Expected Main Conflict

| Ticker | Gold Main Conflict |
|---|---|
| NVDA | `A101__A304` |
| QQQ | `A304__A601` |
| MSFT | `A301__A304` |
| SNDK | `NO_ADMITTED_MAIN_CONFLICT` (expected_main_conflict=null, expected_no_admitted_main_conflict=true) |
| TSM | `A101__A304` |
| AMD | `A101__A304` |

For SNDK, a final run with **no admitted main conflict counts as a correct match** against this Gold entry.

## Evaluator authority (not invented here)

- **Alpha "hit" definition**: reused unmodified from `comqutor_alpha/regression/regression_report_v3.py::_detected_alphas()` — an Alpha counts as detected only at level `active`, `dominant`, or `regime_level`. `candidate` (including one gated down from `active` by the B4 fix), `blocked`, `ambiguous`, and `unavailable` never count. Presence alone is not sufficient.
- **Hit-rate arithmetic**: reused unmodified from `comqutor_alpha/regression/authority_contract.py::apply_alpha_authority()` — per-ticker `hit_rate = |gold ∩ detected| / |gold|`.
- **Aggregation**: reused unmodified from `authority_contract.py::expected_alpha_gate()` — the aggregate is the **macro-average of per-ticker hit rates** across gold-evaluable tickers (not a pooled/micro hit-total ratio).
- **Main-conflict matching**: reused unmodified from `authority_contract.py::apply_main_conflict_authority()` — exact string equality against the production system's own already-canonicalized `conflict_id` (`conflict_engine/conflict_schema.py` always sorts `alpha_a < alpha_b` before joining, so `A101__A304`/`A304__A101` never both occur — no additional canonicalization needed).
- **The one additive rule**: SNDK's `NO_ADMITTED_MAIN_CONFLICT` case, not present in `apply_main_conflict_authority()` — match = (actual admitted main conflict is `None`), applied only for this explicit null-expectation entry.

## Immutability

This file must not be silently modified after evaluation begins. A correction requires a new version, `alpha_conflict_gold.v2` — never a silent edit to v1. Its SHA-256 is recorded above and in `v0_1_3_gold_validation.json/.md`.
