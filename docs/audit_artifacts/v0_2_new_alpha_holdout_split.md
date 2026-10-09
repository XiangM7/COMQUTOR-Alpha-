# v0.2 New Alpha Holdout — Master Split

Dataset version `new_alpha_holdout.v1`. Full detail (sample_number → claim_id/run_id/ticker mapping, no claim text) in `v0_2_new_alpha_holdout_split.json`. **No claim/evidence text is exposed in this document** — full text appears only in the development adjudication packet for the 100 development samples.

## Source Population

**42,048** deduplicated claim/evidence records from **61** real, already-persisted research runs (`outputs/runs/*/structured_agent_outputs.json`), across 8 tickers, after excluding all **838** known-touched claim_ids (Holdouts #1–#5 + the "old-50" set) and filtering to eligible, non-placeholder, sufficiently-substantive, non-duplicate claims. No new research run, no TradingAgents call, no Provider call.

## Sampling

- **Ticker quota for the 300-item pool** (deterministic, seed `20260917`): AMD 38, GOOGL 38, MSFT 38, MU 38, NVDA 37, QQQ 37, SNDK 37, TSM 37.
- **Split into dev/final/reserve** via one further seeded shuffle (seed `20260917+100`) and positional slice — guarantees exact target sizes (100/150/50) but only approximate, not exact, per-ticker proportionality within each split (disclosed, not hidden).
- Stratification used **ticker only** — never COMQUTOR's own predicted Alpha.

## Splits

| Split | Purpose | Count | Content Hash (SHA256) | Status |
|---|---|---:|---|---|
| **Development** | Future Candidate 3 development | 100 | `51fb39e2...` → `d73331bd...` (final) | `FROZEN` |
| **Final Independent** | One-time final validation only | 150 | `a7c84445...` | `SEALED_UNADJUDICATED_NOT_USED_FOR_TUNING` |
| **Reserve** | Replacement for ambiguous/invalid samples | 50 | `07ea4b74...` | `SEALED_UNUSED` |

*(Exact hashes as recorded in the JSON: dev=`d73331bd76944062e589174d79fca1647e499324fcd56561846649128cd9486b`, final=`a7c84445247f0ce0fdf187e6e73d62c04eb82e64557c40a98704a49bcd4bf70c`, reserve=`07ea4b74c8a91ff534dbc339d66185779646fb01531b71b5f03e2845bd232611`.)*

## Verified Zero Overlap

| Check | Result |
|---|---:|
| Dev ∩ Final | 0 |
| Dev ∩ Reserve | 0 |
| Final ∩ Reserve | 0 |
| (Dev ∪ Final ∪ Reserve) ∩ 838-item touched union | 0 |
| Verbatim substring match against `tests/` and the prompt source file | 0 / 300 |

## Label Status

**`UNADJUDICATED`.** No system prediction, confidence, or mapper score is included anywhere in this dataset. No labels have been assigned.
