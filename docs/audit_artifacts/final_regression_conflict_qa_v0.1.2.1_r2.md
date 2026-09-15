# FINAL Regression / Conflict QA — Composite Repaired Baseline (Step 11, r2)

Supersedes `final_regression_conflict_qa_v0.1.2.1.json` (Step 10, preserved unmodified as historical) for final-acceptance purposes. Branch `comqutor-structure-layer`, HEAD `9f228723fad5406c72e62beca67ec70ea0fdb004` (unchanged).

## Gold authority state (unchanged since Steps 1–3/10)

Approved-gold Alpha expectations: **0**. Approved-gold Main Conflict expectations: **0**. Documented: 15/2, Provisional: 22/5.

## Expected-Alpha regression

**Diagnostic hit rate: 12 / 12 = 100.00%.** John's ≥75% threshold is **DIAGNOSTIC ONLY**.

**Formal gate**: `PENDING_APPROVED_GOLD_OR_VALIDATED_CONTRACT` (unchanged — no approved gold exists yet, regardless of how strong the diagnostic result is).

## Main-Conflict regression

**Diagnostic: 6 / 6 tickers produce a non-null admitted main conflict.** John's ≥4/6 threshold is **DIAGNOSTIC ONLY**.

**Formal gate**: `PENDING_GOLD_CONTRACT` (unchanged).

| Ticker | Main conflict |
|---|---|
| NVDA | A101__A304 |
| QQQ | A101__A304 |
| MSFT | A101__A304 |
| SNDK | A304__A601 |
| TSM | A101__A304 |
| AMD | A101__A304 |

## Negative constraints: PASS (0 violations)

MSFT `A102__A304`, SNDK/TSM/AMD `A201__A304` — all correctly non-admitted.

## Step 8 / Step 9 — unchanged, not revisited

- **Evidence Review v2**: Alpha 83.00% PASS, Polarity 83.87% PASS, raw critical reversal 1, status `PENDING_CRITICAL_REVERSAL_ADJUDICATION`, John approval `PENDING_JOHN_APPROVAL`.
- **Step 9**: `TARGET_NOT_SUPPORTED_BY_HEALTHY_SEMANTIC_DATA`, unchanged.

## Summary

| Gate | Result |
|---|---|
| Expected-Alpha diagnostic | 12/12 = 100% |
| Expected-Alpha formal | PENDING_APPROVED_GOLD_OR_VALIDATED_CONTRACT |
| Main-Conflict diagnostic | 6/6 non-null |
| Main-Conflict formal | PENDING_GOLD_CONTRACT |
| Negative constraints | PASS |

A dramatically stronger diagnostic result than Step 10, but the formal gates remain exactly where they were — this is an authority/product state (no approved gold contract exists), not something a technical rerun can close.
