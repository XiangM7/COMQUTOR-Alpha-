# Alpha Recall Root-Cause Analysis — v0.1.2.1 (Step 5B)

**Analysis only. No Alpha Mapper, taxonomy, B1/B2/B4, conflict ontology, or regression-label changes.** Branch `comqutor-structure-layer`, HEAD `9f228723fad5406c72e62beca67ec70ea0fdb004` (unchanged — no commit, no push). Zero new Provider calls, zero TradingAgents calls — this analysis reads only the already-persisted healthy semantic-validation outputs (single claim + full taxonomy + one LLM decision, claim concurrency 4, ticker concurrency 1) from Step 5A's `six_ticker_semantic_coverage_validation_v0.1.2.1`.

## Authority Rule

John's 12 historical callouts are **diagnostic targets, not approved gold labels**. Each was judged directly against the actual fresh source claims and actual successful LLM results — never on "John expected it, therefore it's a bug" alone. Canonical Alpha definitions (`comqutor_alpha/alpha_library/alpha_taxonomy_v1.yaml`) are the sole semantic authority; keyword presence was used only to locate candidate claims for inspection, never as proof.

## Headline Result

**12 / 12 DETECTED. Zero true semantic recall candidates.**

The near-total Alpha absence observed in Step 4 (~2% coverage) was **entirely a runtime-execution-capacity artifact** (Step 5A's root cause: unbatched single-claim calls sharing a fixed 32-call budget with a slower batch task). Now that runtime coverage is 99.20%, every one of John's 12 callouts has at least one — usually many — genuinely on-thesis, successfully-evaluated MATCHED claim.

## Per-Target Result Table

| Ticker | Target | Detected? | Relevant source? | Evaluated? | Outcome | Recall candidate? | Reason |
|---|---|---|---|---|---|---|---|
| QQQ | A001 Rate Cut Cycle | YES | YES | YES | DETECTED | NO | 35 matched claims on the Fed/rate-cut theme (mostly hawkish-direction, still on-thesis) |
| QQQ | A003 Liquidity Expansion | YES | YES | YES | DETECTED | NO | 9 matched claims on risk-appetite/liquidity-tailwind theme |
| MSFT | A101 AI Expansion | YES | YES | YES | DETECTED | NO | 28 matches; Google Cloud/Nvidia-beat claims explicitly "validate the AI demand thesis" |
| MSFT | A102 Inference Explosion | YES | YES | YES | DETECTED | NO | Only 3 matches, all genuinely on-thesis (Copilot/inference-revenue mechanism) |
| MSFT | A304 Multiple Compression | YES | YES | YES | DETECTED | NO | 69 matches include explicit "priced for perfection"/de-rating language |
| SNDK | A201 Semiconductor Supercycle | YES | YES | YES | DETECTED | NO | 134 matches, mixed quality, but several explicitly invoke "AI-driven memory supercycle"/NAND-ASP-cycle mechanism |
| SNDK | A301 Revenue Expansion | YES | YES | YES | DETECTED | NO | 48 matches include explicit 251% YoY revenue-growth claims |
| SNDK | A304 Multiple Compression | YES | YES | YES | DETECTED | NO | 43 matches include explicit "trigger multiple compression" language |
| TSM | A103 AI Infrastructure | YES | YES | YES | DETECTED | NO | 27 matches include explicit hyperscaler-datacenter-buildout mechanism |
| TSM | A304 Multiple Compression | YES | YES | YES | DETECTED | NO | 90 matches include explicit "priced for perfection"/compression language |
| AMD | A101 AI Expansion | YES | YES | YES | DETECTED | NO | 42 matches on the AI-buildout/Nvidia-linkage theme |
| AMD | A201 Semiconductor Supercycle | YES | YES | YES | DETECTED | NO | Weakest of the 12 — most of 16 matches are AMD's own company-specific balance-sheet line items, not industry-cycle claims (see note below); still clears the DETECTED bar via at least one genuinely industry-level match |

## Counts

```
John callouts total = 12
DETECTED = 12
TRUE_SEMANTIC_NONE_WITH_RELEVANT_SOURCE = 0
  FALSE_NONE = 0
  WRONG_ALPHA = 0
SOURCE_EVIDENCE_INSUFFICIENT = 0
PROVIDER_FAILURE = 0
AMBIGUOUS_NEEDS_ADJUDICATION = 0
```

## Canonical Definitions Used

| Alpha | Name | Core Thesis |
|---|---|---|
| A001 | Rate Cut Cycle | Falling rates lower discount rates and support long-duration growth assets. |
| A003 | Liquidity Expansion | Improving liquidity supports risk appetite and equity inflows. |
| A101 | AI Expansion | AI training and adoption increase demand for accelerators and AI-related equities. |
| A102 | Inference Explosion | Enterprise AI applications and AI agents increase inference compute demand. |
| A103 | AI Infrastructure | AI buildout drives datacenter, power, cooling, networking, and server demand. |
| A201 | Semiconductor Supercycle | A chip-cycle upturn improves inventory, pricing, capex, and semiconductor demand. |
| A301 | Revenue Expansion | Strong demand raises revenue guidance, EPS revisions, and repricing potential. |
| A304 | Multiple Compression | Rich valuation and high multiples create downside risk despite strong fundamentals. |

## A304 Special Care (Section 10)

Every A304 DETECTED verdict above (MSFT, SNDK, TSM) is backed by claims that explicitly reference the **compression/de-rating mechanism** ("priced for perfection", "trigger multiple compression", "if the broader AI infrastructure complex de-rates") — never merely "the stock is expensive" or a bare P/E figure. This satisfies the stricter bar this task required.

## A201 Special Care (Section 13) — the one genuinely mixed case

SNDK A201 and AMD A201 were checked against the requirement that being a semiconductor-related ticker does NOT automatically establish A201; company-specific strength alone is insufficient.

- **SNDK A201**: of 134 matched claims, only ~8 explicitly reference the cycle mechanism (ASP, inventory, "AI-driven memory supercycle") — but those 8 are unambiguous and sufficient for DETECTED.
- **AMD A201**: of 16 matched claims, the large majority are AMD's own inventory-dollar/capex/margin line items — genuinely company-specific, not industry-cycle evidence per Section 13's own example list. DETECTED is still justified by at least one clearly industry-level claim ("BofA flagged eight chip stocks as enhanced buying opportunities... semiconductors despite near-term pressure") and one that explicitly frames AMD's inventory build against "the semiconductor industry['s]" historical cycle pattern. **This is flagged as the one target where match precision, not recall, deserves a future look** — out of scope for repair in this task.

## Provider-Failure Check (Section 14)

39 UNAVAILABLE rows exist across all six tickers. All 39 were inspected against all 12 targets: **none constitutes the sole or primary evidence for any target Alpha** — every target already has multiple independently-successful MATCHED claims. A few UNAVAILABLE rows are topically adjacent (e.g. a QQQ "no tailwind, no cliff" macro claim relevant to A001) but do not change any classification.

## High-Value Valid-NONE Discovery (Section 17, preliminary)

Scanned all 2,764 valid NONE results (UNAVAILABLE excluded) for keyword-level compatibility with any of the 10 canonical Alphas: **23 raw hits**. Manual review against the canonical taxonomy found:

- **1 STRONG candidate**: AMD — *"Macro context: Lower Treasury yields, easing selling pressure, positive Asian markets."* → genuinely on-thesis for A001 (discount-rate mechanism), received NONE. Worth a closer look in a future precision pass.
- **3 WEAK/borderline candidates** (NVDA/AMD ×2 competitive-risk framing for A101, AMD data-center-market-share for A103) — plausibly correctly NONE (risk/competitive framing, not a demand-expansion claim).
- **15 rejected as false positives**: company-level balance-sheet "liquidity" (current ratio, net cash) superficially keyword-matching A003's macro *monetary*-liquidity thesis — semantically unrelated. These NONE decisions are almost certainly **correct**, a useful confirmation of classifier precision rather than a defect.

**Do not read this as "20+ recoverable rows."** After manual review, the realistic recoverable set from this preliminary scan is 1 strong candidate.

## Files

**Created:** `docs/audit_artifacts/alpha_recall_root_cause_analysis_v0.1.2.1.json`, this file, `docs/audit_artifacts/high_value_true_none_candidates_v0.1.2.1.json`.
**Not touched:** any previous audit artifact, Alpha Mapper, taxonomy, B1/B2/B4, conflict ontology, regression labels.
**Provider calls:** 0. **TradingAgents calls:** 0. **Commit:** NO. **Push:** NO.
