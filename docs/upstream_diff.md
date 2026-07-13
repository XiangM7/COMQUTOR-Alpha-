# Upstream compatibility differences

## Baseline mapping

The repository matches the master implementation prompt with these naming
details:

| Prompt concept | Actual repository interface | Handling |
|---|---|---|
| `propagate(ticker, trade_date, asset_type)` | Parameter is named `company_name`; positional semantics match | Adapter exposes `ticker` and passes it positionally |
| Sentiment analyst key | Configuration/wire key remains `social` | Captured output field is `sentiment_report`; public COMQUTOR agent enum is `sentiment` |
| Analyst outputs | Four strings on `final_state` | Captured after `propagate()` returns |
| Final decision | `final_state["final_trade_decision"]` plus processed return value | Stored comparison-only |

## Upstream modifications

None for Phase 1. The planned MVP integration is external to
`tradingagents/`. If a future incompatibility cannot be handled by the
adapter, this document must record the exact upstream edit, regression test,
risk, and upgrade strategy before that edit is accepted.

## Upgrade check

After an upstream merge or rebase, run:

```bash
.venv/bin/python scripts/verify_upstream_baseline.py
.venv/bin/pytest tests/comqutor_alpha/contract/test_upstream_baseline.py -q
```

Any failure blocks subsequent COMQUTOR phases until the seam is remapped and
the evidence documents are updated.
