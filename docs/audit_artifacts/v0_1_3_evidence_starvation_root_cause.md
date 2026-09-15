# v0.1.3 Evidence Starvation Root-Cause Audit

Offline only. **Provider calls: 0. TradingAgents calls: 0. Ticker runs: 0. No production code, test, threshold, taxonomy, or Gold file changed.**

## John — Why Strong Gold Alphas Were Evidence-Starved

```
Ticker  Alpha  Gold Class        Primary Break Point            Subtype  Judgment                Recoverability
NVDA    A102   STRONG_GOLD       B1 research corpus content     B1       RESEARCH_COVERAGE_GAP   MEDIUM
NVDA    A201   SUPPORTED_GOLD    Alpha mapping misattribution   B3       DESIGN_GAP              LOW
QQQ     A101   SUPPORTED_GOLD    ETF ticker-specificity gap     B4       DESIGN_GAP              LOW
MSFT    A102   STRONG_GOLD       company_names=() empty tuple   B4       DESIGN_GAP              MEDIUM
SNDK    A102   REVIEW_CANDIDATE  true evidence vacuum           B8       GOLD_REVIEW_ONLY        SHOULD_NOT_TARGET
AMD     A102   STRONG_GOLD       AI semantic hard-gate          B1       RESEARCH_COVERAGE_GAP   MEDIUM
AMD     A201   SUPPORTED_GOLD    cross-company mapping error    B3       DESIGN_GAP              LOW
```

**Headline finding**: MSFT A102's rejection is the most concrete, code-verified defect in this audit — the production activation-scorer call site (`comqutor_alpha/graph_engine/pipeline.py`) never populates `company_names`, so `_is_ticker_specific()` can only ever match the bare ticker string, never a company's real name. Directly tested: `_token_boundary_match("Microsoft", <the actual MSFT A102 claim text>)` returns `True` — the claim explicitly says "Microsoft's AI products," yet it was rejected as `NO_TICKER_SPECIFIC_EVIDENCE` purely because `company_names` defaults to `()` everywhere in production. Even so, fixing ticker-specificity alone only raises MSFT A102's score from 34.97 to 44.97 — still short of the 50.0 activation threshold.

---

## Executive Summary

```
Gold Benchmark SHA-256 (before/after):            99b1cd0247637054de360c3b5c0c00c7d8052152f3db1d29045eae1850bd8e9a  (UNCHANGED)
Gold Validity Judgment SHA-256 (before/after):     3643ea45168c029d7c2a2ceb6d1d61cac3d5de80770d3dccb1f57d005c0c1cdf  (UNCHANGED)

Original Evidence-Starvation (B) cases:            7
System-recovery-priority cases (STRONG/SUPPORTED): 6
Benchmark-review-only cases (REVIEW_CANDIDATE):    1  (SNDK A102)

B-subtype counts (primary, sums to 7):
  B1 (source acquisition gap):        2  (NVDA A102, AMD A102)
  B3 (alpha mapping / stance gap):    2  (NVDA A201, AMD A201)
  B4 (ticker-specificity gap):        2  (QQQ A101, MSFT A102)
  B8 (true evidence vacuum):          1  (SNDK A102)

Judgment counts (sums to 7):
  DESIGN_GAP:              4
  RESEARCH_COVERAGE_GAP:   2
  GOLD_REVIEW_ONLY:        1

Recoverability (sums to 7):
  MEDIUM_CONFIDENCE_RECOVERABLE:  3  (NVDA A102, MSFT A102, AMD A102)
  LOW_CONFIDENCE_RECOVERABLE:     3  (NVDA A201, QQQ A101, AMD A201)
  SHOULD_NOT_TARGET:              1  (SNDK A102)

HIGH_CONFIDENCE recoveries found: 0
```

---

## Why Legitimate Gold Evidence Starved

Three distinct, independently-verified mechanisms explain all 6 system-recovery-priority cases:

1. **`company_names=()` is always empty in production** (proven by reading `comqutor_alpha/graph_engine/pipeline.py`'s call to `score_alpha_activations_v2`, which omits `company_names` entirely, defaulting to `()`). This means ticker-specificity can only ever match the literal ticker symbol string, never a company's real name or product brand. Directly implicated: **MSFT A102** (proven), contributes to **AMD A201** ("Ryzen processors" mention) and **NVDA A201**.
2. **ETF ticker-specificity has no constituent-equivalence concept.** QQQ's real AI exposure is inherently expressed via named constituents (Intel, AMD, Marvell), which the current single-company-oriented ticker-specificity check cannot recognize as QQQ-relevant. Implicated: **QQQ A101**.
3. **The AI semantic hard-gate requires an isolated, alpha-specific anchor phrase.** Claims that discuss "training/inference" as one bundled market default to the broader A101 rather than the narrower A102, even when real, high-quality, ticker-specific evidence exists. Implicated: **AMD A102**, and a contributing factor for **NVDA A102**.

**NVDA A102** and **AMD A102**'s remaining component (research coverage) is different in kind: NVDA's raw corpus discusses "inference" 8 times but exclusively as a competitive threat to NVDA (never the bullish "tokens=inference explosion" narrative that is externally real); AMD's raw corpus has 7 real MI-series claims but none isolates the inference-vs-training technical distinction that made this genuinely STRONG_GOLD externally.

---

## Per-Case Findings

### NVDA A102 — Inference Explosion (STRONG_GOLD)
Zero claims ever qualified (score=0.0, all six components at 0). The raw research corpus contains **zero** mentions of "token" and only 8 mentions of "inference," all framed as a *competitive threat* (custom ASICs eroding NVIDIA's inference-market dominance) rather than the real, bullish "inference explosion benefits NVIDIA" narrative confirmed externally by the Gold Validity Audit. This is a genuine research-coverage gap, not a classifier defect — the deterministic stance rules correctly rejected content that is substantively non-supportive. **Judgment: RESEARCH_COVERAGE_GAP. Recoverability: MEDIUM.**

### NVDA A201 — Semiconductor Supercycle (SUPPORTED_GOLD)
Score 18.58. The 2 claims that did qualify for A201 discuss inventory/receivables *risk*, not supercycle growth — NVDA's real growth evidence (DC revenue acceleration) was instead mapped to A101/A103. Ticker-specificity is also 0 despite the claims naming NVDA-specific dollar figures (QUESTIONABLE rejection, same `company_names=()` mechanism plausibly contributing). **Judgment: DESIGN_GAP (Alpha mapping). Recoverability: LOW** — multiple compounding gaps, no single fix identified.

### QQQ A101 — AI Expansion (SUPPORTED_GOLD)
Score 32.21. 4 relevant Secondary-sourced claims exist; 3 name individual constituents (Intel, AMD, Marvell) and are correctly rejected as non-ticker-specific under the *current* single-company-oriented contract — but this is an architectural gap for ETF/index tickers, not a bug in the existing rule. No Primary-Research-agent claim on this topic exists in the run at all. **Judgment: DESIGN_GAP (ETF ticker-specificity). Recoverability: LOW.**

### MSFT A102 — Inference Explosion (STRONG_GOLD)
Score 34.97. The single qualifying claim literally says "Microsoft's AI products... are driving inference demand" — a clean, LLM-classified, Primary-sourced, factor_score=1.0 match — yet rejected as non-ticker-specific solely because `company_names` is never populated in production. Code-verified: `_token_boundary_match("Microsoft", <claim>)` returns `True` in isolation. Fixing this alone raises the score to 44.97 — still short of 50; an additional independent qualifying fact would also be needed. **Judgment: DESIGN_GAP. Recoverability: MEDIUM** (the clearest, most concrete defect found in this audit).

### SNDK A102 — Inference Explosion (REVIEW_CANDIDATE — benchmark review only)
Score 0.0, true evidence vacuum (0 raw supporting claims out of 819 candidate-scoring attempts). Consistent with the Gold Validity Audit's own finding that A102 is a poorer thematic fit for SNDK than A103 (storage, not compute). **Per explicit instruction, this case is NOT a system-recovery target** — audited for completeness only, and its v1 miss status is left unchanged. **Judgment: GOLD_REVIEW_ONLY. Recoverability: SHOULD_NOT_TARGET.**

### AMD A102 — Inference Explosion (STRONG_GOLD)
Score 35.63. AMD's raw corpus genuinely contains 7 real MI-series claims (a source-acquisition success), but the strongest candidate is rejected by the AI hard-gate (`missing an alpha-specific anchor phrase with a locally co-occurring change predicate`) because it bundles "training/inference" as one market rather than isolating inference specifically — a defensible, correctly-functioning gate, not a bug. The 1 claim that does qualify is generic industry-wide commentary, not AMD-specific. **Judgment: RESEARCH_COVERAGE_GAP (semantic-gate interaction). Recoverability: MEDIUM.**

### AMD A201 — Semiconductor Supercycle (SUPPORTED_GOLD)
Score 25.73. 5 Primary claims qualify, but one (`Silicon Motion up 186%... SanDisk soaring`) is about **entirely different companies** — a genuine Alpha-mapping error independent of ticker-specificity. The remaining 4 are generic financial-statement line items or a "Ryzen processors" product-brand mention blocked by the same `company_names=()` gap. Weakest evidence_quality (raw=4.0) of the six system-recovery cases. **Judgment: DESIGN_GAP (mapping + ticker-specificity). Recoverability: LOW.**

---

## Comparison Tables

**Table A — all 7 original Evidence-Starvation cases**

| Ticker | Alpha | Gold Class | Subtype | Judgment | Recoverability |
|---|---|---|---|---|---|
| NVDA | A102 | STRONG_GOLD | B1 | RESEARCH_COVERAGE_GAP | MEDIUM |
| NVDA | A201 | SUPPORTED_GOLD | B3 | DESIGN_GAP | LOW |
| QQQ | A101 | SUPPORTED_GOLD | B4 | DESIGN_GAP | LOW |
| MSFT | A102 | STRONG_GOLD | B4 | DESIGN_GAP | MEDIUM |
| SNDK | A102 | REVIEW_CANDIDATE | B8 | GOLD_REVIEW_ONLY | SHOULD_NOT_TARGET |
| AMD | A102 | STRONG_GOLD | B1 | RESEARCH_COVERAGE_GAP | MEDIUM |
| AMD | A201 | SUPPORTED_GOLD | B3 | DESIGN_GAP | LOW |

**Table B — STRONG/SUPPORTED-only (6 cases, SNDK A102 excluded per explicit instruction)**

Identical to Table A minus the SNDK row — no metric is inflated or deflated by this exclusion; it is a filter for system-recovery targeting only, not a rescoring.

---

## Path-to-75% Reality Check

Current: 61.0317%. Target: ≥75%. Minimum additional whole-ticker-equivalent hits needed: 5.

This audit found **zero HIGH-confidence** Evidence-side recoveries — only 3 MEDIUM (NVDA A102, MSFT A102, AMD A102) and 3 LOW. Combined with the prior Structure-side audit (TSM A301 = high confidence, MSFT A304 = medium, QQQ A201 = uncertain, SNDK A103 = insufficient), the maximally optimistic combination of every Medium-or-better candidate from **both** tracks (TSM A301, MSFT A304, NVDA A102, MSFT A102, AMD A102 = 5 conversions) reaches exactly 5 on paper (~74.92% macro-average) — but this audit's own counterfactual work shows several of these (e.g., MSFT A102's ticker-specificity-only fix reaches only 44.97, still short of 50) require **more** than the single identified fix to actually flip. **This is not a credible, ready-to-execute path to 75%** — it is a plausible direction requiring real implementation and re-validation, not a proof that 75% is reachable with the fixes identified so far.

---

## Final Validation

- Gold Benchmark SHA-256: unchanged (`99b1cd0247637054de360c3b5c0c00c7d8052152f3db1d29045eae1850bd8e9a`)
- Gold Validity Judgment SHA-256: unchanged (`3643ea45168c029d7c2a2ceb6d1d61cac3d5de80770d3dccb1f57d005c0c1cdf`)
- SNDK A102 not used as a system-recovery target anywhere in this document
- B1-B9 primary-subtype counts sum to 7; judgment counts sum to 7; recoverability counts sum to 7
- Zero Provider calls, zero TradingAgents calls, zero ticker runs, zero code/test/threshold/taxonomy/Gold file changes
- No PASS manufactured, no recovery claimed as certain

**Provider calls: 0. TradingAgents calls: 0. No ticker run. No production code changed. No commit. No push.**
