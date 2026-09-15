# v0.1.3 Provider Failure Blast-Radius Audit

Offline / read-only. **Provider calls: 0. TradingAgents calls: 0. Ticker runs: 0. HEAD unchanged (`9f228723fad5406c72e62beca67ec70ea0fdb004`). No commit. No push.**

## John — Provider Reliability Impact

```
Ticker  Provider Failures  Semantic-Critical  Gold Misses Affected  Run Quality
NVDA    113                99                 0                    raw failures present, no confirmed impact
QQQ     83                 71                 0                    raw failures present, no confirmed impact
MSFT    126                110                0                    raw failures present, no confirmed impact
SNDK    144                128                0                    highest raw volume, no confirmed impact
TSM     128                114                1 (A301)              CONFIRMED provider-failure-affected
AMD     115                99                 0                    distinct TRANSPORT_ERROR profile, no confirmed impact

Official Alpha Hit: 61.03%

Provider-clean algorithmic estimate: 63.81% (diagnostic only, excludes TSM A301)

Most affected ticker: TSM

TSM A301: PROVIDER_FAILURE_CAUSAL

Recommended next action: NEXT_PROVIDER_C (add run-quality diagnostics) +
  narrow TSM-only rerun consideration
```

## Executive Summary

```
Final runs audited: 6

Total Provider failures (raw log lines, all 4 Week2 LLM tasks): 709
Semantic-critical Provider failures (alpha_classifier + evidence_stance_classifier
  + structure_extractor, raw): 621
alpha_classifier failures (raw retry-attempt log lines): 216
alpha_classifier final per-claim orphans (match_status=unavailable): 47
  of which "strong deterministic candidate" orphans: 8

Runs with semantic-critical failures: 6 / 6
Gold misses potentially affected: 1 (TSM A301)
Gold misses likely/confirmed affected: 1 (TSM A301)

Runs potentially "not clean" by raw volume: all 6 -- but only TSM shows a
  confirmed Gold-miss consequence after claim-level tracing

Current official Alpha Hit: 61.0317%
Clean estimate of algorithmic recall: PARTIALLY

Recommended next step: NEXT_PROVIDER_C (add run-quality/benchmark-eligibility
  diagnostics), plus a narrow, separately-authorized TSM-only rerun

Code changes: 0.  Provider calls: 0.  Ticker runs: 0.
```

## Provider-Dependent Stage Map

| Stage | Task | Can change | Fallback |
|---|---|---|---|
| Claim batch enrichment | `claim_batch_enrichment` | claim quality tags (indirect) | deterministic extraction continues |
| Alpha Mapper Semantic Authority | `alpha_classifier` | `matched_alpha`, structure edge `alpha_ids`, activation score | `match_status='unavailable'` — never falls back to the deterministic pick (intentional design) |
| B1 Evidence Stance | `evidence_stance_classifier` | `evidence_stance`, ticker-specific eligibility | `stance_method='deterministic_fallback'` — a real, existing baseline classifier |
| Structure extraction | `structure_extractor` | LLM-sourced canonical-relation edges only | deterministic `_extract_edges()`/relation-grammar path always runs regardless |

Research/debate/risk/portfolio agents (Week1 TradingAgents Provider calls) are a separate logging surface not captured in `week2_llm_errors.jsonl` and out of this offline task's scope.

## Provider Failures by Ticker (raw log lines)

| Ticker | claim_batch_enrichment | alpha_classifier | evidence_stance_classifier | structure_extractor | Total |
|---|---:|---:|---:|---:|---:|
| NVDA | 14 | 32 | 60 | 7 | 113 |
| QQQ | 12 | 17 | 50 | 4 | 83 |
| MSFT | 16 | 45 | 58 | 7 | 126 |
| SNDK | 16 | 52 | 76 | 0 | 144 |
| TSM | 14 | 47 | 61 | 6 | 128 |
| AMD | 16 | 23 | 66 | 10 | 115 |

Dominant error type is `WEEK2_LLM_TIMEOUT` for 5 of 6 tickers; **AMD is a distinct outlier** — 57 of its 66 `evidence_stance_classifier` failures and all 10 `structure_extractor` failures are `WEEK2_LLM_TRANSPORT_ERROR`, not timeout.

**Raw counts include every retry attempt** (a batch failing on attempt 1 then succeeding on attempt 2 still logs one failure line). The definitive, final-outcome measure is each claim's own persisted `match_status` field.

## alpha_classifier Special Focus

| Ticker | Total claims | Final orphans (`match_status=unavailable`) | Orphan rate | Strong-deterministic orphans |
|---|---:|---:|---:|---:|
| NVDA | 733 | 5 | 0.68% | 0 |
| QQQ | 647 | 5 | 0.77% | 2 |
| MSFT | 750 | 9 | 1.20% | 1 |
| SNDK | 918 | 15 | 1.63% | 1 |
| TSM | 766 | 9 | 1.17% | 3 |
| AMD | 787 | 4 | 0.51% | 1 |

**TSM's 47 figure independently reconfirmed**: exactly 47 `alpha_classifier` entries in `week2_llm_errors.jsonl` (44 timeout, 1 validation, 2 transport) — the *raw retry-attempt* count, distinct from TSM's *9 final per-claim orphans*. `alpha_classifier_calls_expected` is **UNKNOWN** — no per-claim call-attempt ledger exists beyond the aggregate log and the final `match_status` field.

## The 8 Strong-Deterministic-Orphan Claims — Full Lineage

Of the 47 final orphans across all six runs, only 8 had a deterministic layer that found a **clean, singularly-eligible** Alpha candidate before the Provider failure erased it. Traced all 8:

| Ticker | Claim | Det. top Alpha | Gold relevance |
|---|---|---|---|
| QQQ | news_agent:claim:10 | A601 | Already a QQQ HIT — no consequence |
| QQQ | aggressive_risk_analyst:claim:56 | A501 | Not a Gold-tracked Alpha — no consequence |
| MSFT | bear_researcher:claim:67 | A301 | Already a MSFT HIT; A102-adjacent text is rhetorical/Secondary, not material |
| SNDK | news_agent:claim:40 | A201 | Already a SNDK HIT — no consequence |
| TSM | sentiment_agent:claim:70 | A601 | Already a TSM HIT — no consequence |
| **TSM** | **fundamental_agent:claim:37** | **A301** | **Gold MISS — second confirmed A301 orphan (generic financial-table row)** |
| **TSM** | **fundamental_agent:claim:42** | **A301** | **Gold MISS — the primary, previously-identified case** |
| AMD | bear_researcher:claim:31 | A301 | Already an AMD HIT; also substantively about NVIDIA, not AMD |

**Only TSM A301 shows a confirmed Gold-miss consequence — and TSM has two such orphaned claims, not just one.** All 8 cases have full claim-level traceability (no `TRACEABILITY_GAP`).

## Failure Impact Classification

- **alpha_classifier's 47 orphans**: `F3 ALPHA_MAPPING_ATTRITION` for all; escalates to `F7 ACTIVATION_ATTRITION` only for the TSM pair (claim:37, claim:42) via A301's `local_structure_support`.
- **evidence_stance_classifier's 371 raw failures**: `F0 NO_SEMANTIC_IMPACT` for the fallback *path* (a real designed deterministic baseline, not a drop); `F8 TRACEABILITY_UNKNOWN` for output-equivalence in every individual case (not exhaustively re-verified).
- **structure_extractor's 34 raw failures**: `F0` for the extraction *capability* overall (deterministic path always runs); `F5 STRUCTURE_ATTRITION` scoped narrowly to the LLM-sourced canonical-relation edge subset.
- **claim_batch_enrichment's 88 raw failures**: `F1 PRESENTATION_ONLY` / not semantic-critical.

## TSM A301 Case Study

Claim `fundamental_agent:claim:42`: *"TSM has delivered two consecutive years of >30% revenue growth (2024 and 2025), driven by the AI infrastructure buildout."* Primary, ticker-specific. Deterministic layer: **singularly eligible for A301** (score 0.7596, no competing eligible candidate). `alpha_classifier` task → `WEEK2_LLM_TIMEOUT` (retries exhausted) → `match_status='unavailable'`, `matched_alpha=None` (intentional design: no deterministic fallback for the semantic authority). Structure consequence: the `ai_infrastructure→tsm_revenue_growth` edge carries `alpha_ids=[]`. Activation consequence: A301's `local_structure_support` stays 0.0.

**Would claim:42 likely have contributed to A301 had the call succeeded?** Using only deterministic evidence: this is the strongest possible circumstantial case (no ambiguity, no competing candidate) — but the actual LLM answer remains `PROVIDER_OUTPUT_UNKNOWN`, never invented. **Classification: `PROVIDER_FAILURE_CAUSAL`** — causal to the *absence of any Alpha commitment*, not proof of what the commitment would have been.

## Six-Run Gold Miss Crosscheck (summary)

Of all Gold misses, only **TSM A301** classifies as `MISS_PROVIDER_FAILURE_CONFIRMED`. NVDA A102, MSFT A102, AMD A102, MSFT A304, QQQ A101, SNDK A103, SNDK A301 all classify as `MISS_UNAFFECTED_BY_PROVIDER_FAILURE` — their prior root-cause diagnoses are **reconfirmed, not contradicted**. NVDA A201 and AMD A201 are marked `MISS_PROVIDER_TRACEABILITY_UNKNOWN` (not exhaustively re-traced beyond the fully-traced 8-case population, given its demonstrated near-zero yield).

## Revisit of Prior Root-Cause Audits

- **Evidence Starvation audit**: UNCHANGED.
- **Structure Starvation audit**: PARTIALLY_REVISED for TSM A301 only (already reconciled in the QQQ/SNDK audit; independently reconfirmed here with error-log corroboration and a second orphaned claim).
- **Phase-2 audit**: UNCHANGED.
- **QQQ/SNDK audit**: UNCHANGED — its TSM A301 reconciliation stands, now further corroborated.

## Failure Cluster Analysis

Failures span each run's **entire** processing window (56–142 minutes) — a persistent, run-long elevated error rate, not one localized burst. `evidence_stance_classifier` is the single most failure-prone stage by volume across all six runs. AMD's `TRANSPORT_ERROR`-dominated profile is a distinct anomaly from the other five (timeout-dominated) runs, despite an identical configured model (`deepseek-v4-flash`). NVDA/QQQ/MSFT/SNDK ran 2026-09-04; TSM/AMD ran 2026-09-06 — a timing observation only, no causal claim made.

## Timeout vs. Semantic Failure (mandatory separation)

- **A. Provider execution failure**: `WEEK2_LLM_TIMEOUT` + `WEEK2_LLM_TRANSPORT_ERROR` = 657 of 709 (92.7%).
- **B. Model semantic disagreement**: not observable from these logs — a wrong-but-successful classification produces no error entry at all.
- **C. Parser/schema failure**: `WEEK2_LLM_VALIDATION_FAILED` + `WEEK2_LLM_INVALID_JSON` = 27 (3.8%).
- **D. Retry/fallback failure**: the 47 final per-claim orphans — every retry exhausted.

No semantic misclassification is anywhere labeled a timeout in this analysis.

## Fallback Audit

No stage silently drops a claim without a recorded reason code. **Silent semantic attrition: NO at the per-claim level, YES at the aggregate/run level** — no run-level metric anywhere surfaces "this run experienced substantial semantic-critical Provider failure."

## Failure Visibility Audit

All six runs are marked artifact-complete (9/9) and were used for official Gold benchmark evaluation with **zero visibility** into their 83–144 raw Provider failures each. `data_sanity_status` exists but covers only numeric/price data, never LLM/Provider health. **Can a run be PASS despite material Provider degradation? YES — this is a confirmed QA blind spot.**

## Proposed Run-Quality Metrics (design only)

`provider_call_failure_rate`, `alpha_classifier_failure_rate`, `semantic_critical_failure_count/rate`, `claims_orphaned_by_provider_failure`, `alphas_impacted_by_provider_failure` (the single most actionable metric — currently 1 across all six runs: TSM A301). **No defensible threshold exists yet** from only 6 data points and no pre-existing Provider-health convention in this codebase — metrics are recommended to be **reported without gating** for now.

## Benchmark Eligibility Question

**DEPENDS_ON_IMPACT.** Raw failure volume does not predict Gold-relevant impact (TSM's 128 raw failures are mid-pack, not the highest — SNDK's 144 show zero confirmed consequence). A volume-based exclusion rule is not supported by this data; the claim-level `alphas_impacted_by_provider_failure` metric is the actual decision-relevant signal. Gold benchmark validity is unaffected — this is a run-quality question only.

## Fresh-Run Priority

**1. TSM** (confirmed consequence). 2. SNDK (highest raw/orphan volume, but zero confirmed consequence — lower-priority confirmatory check only). 3. MSFT (tangential A102-adjacent orphan, low incremental value). 4. AMD (distinct failure profile, lowest orphan count). 5. NVDA. 6. QQQ.

## Provider Reliability Recommendation

**NEXT_PROVIDER_C** — add run-quality diagnostics. `NEXT_PROVIDER_B` is not justified: the existing retry mechanism is reasonably effective (only 0.51%–1.63% final orphan rate despite high raw failure counts). A narrow, separately-authorized TSM-only rerun is the natural companion action, not a blanket rerun.

## Alpha Hit Interpretation

Confidence in 61.0317% w.r.t. Provider execution quality: **MEDIUM**. Is it a clean estimate of algorithmic recall? **PARTIALLY** — 36 of 37 Gold expectations (97.3%) show no Provider-failure contamination; exactly 1 (TSM A301, 2.7%) is confirmed causal. Excluding it from evaluability raises the diagnostic macro-average by 2.7781pp (61.0317% → 63.8095%) — real but small, nowhere near explaining the 13.9683pp gap to 75%.

## Provider-Clean Gold Diagnostic

Excluding TSM A301: **36 expected, 23 hits, 63.8095%** hit rate. **DIAGNOSTIC_ONLY** — does not replace the official v1 metric (61.0317%, all 37 expectations, TSM A301 counted as a miss exactly as computed).

---

## Final Validation

Gold v1 / Gold Validity SHA-256 unchanged. No Gold v2. Production files changed: 0. Test files changed: 0. P0/P1 and SHA guards untouched.

**Provider calls: 0. TradingAgents calls: 0. Ticker runs: 0. No commit. No push. No destructive git operations.**
