# Verdict delta over every saved run of the six tickers

- Runs compared: **76**; formal_status changed on **18**; reasons changed with the status unchanged on **15**.
- Transitions: {"needs_review -> pass": 2, "pass -> fail": 1, "pass -> needs_review": 15}

## Runs whose formal_status changed

| Ticker | Run | Analysis date | Before | After | Cause |
|---|---|---|---|---|---|
| AMD | b71765a0 | 2026-07-31 | pass | needs_review | a Gold contract rule that should execute could not be evaluated for this run (the frozen trigger matrix is bound to another run) |
| AMD | eb714c04 | 2026-08-25 | pass | needs_review | a Gold contract rule that should execute could not be evaluated for this run (the frozen trigger matrix is bound to another run) |
| AMD | 4d8385ef | 2026-08-28 | pass | needs_review | a Gold contract rule that should execute could not be evaluated for this run (the frozen trigger matrix is bound to another run) |
| AMD | 1bad76a7 | 2026-10-05 | pass | needs_review | a Gold contract rule that should execute could not be evaluated for this run (the frozen trigger matrix is bound to another run) |
| AMD | c904d4cc | 2026-10-06 | pass | needs_review | a Gold contract rule that should execute could not be evaluated for this run (the frozen trigger matrix is bound to another run) |
| AMD | dependen | 2026-10-06 | pass | needs_review | a Gold contract rule that should execute could not be evaluated for this run (the frozen trigger matrix is bound to another run) |
| AMD | dependen | 2026-10-06 | pass | needs_review | a Gold contract rule that should execute could not be evaluated for this run (the frozen trigger matrix is bound to another run) |
| AMD | recovery | 2026-10-06 | pass | needs_review | a Gold contract rule that should execute could not be evaluated for this run (the frozen trigger matrix is bound to another run) |
| AMD | requal-2 | 2026-10-06 | pass | needs_review | a Gold contract rule that should execute could not be evaluated for this run (the frozen trigger matrix is bound to another run) |
| MSFT | 07ddc074 | 2026-08-14 | pass | needs_review | a Gold contract rule that should execute could not be evaluated for this run (the frozen trigger matrix is bound to another run) |
| MSFT | ce6b9628 | 2026-08-25 | pass | needs_review | a Gold contract rule that should execute could not be evaluated for this run (the frozen trigger matrix is bound to another run) |
| MSFT | c715460c | 2026-08-28 | pass | needs_review | a Gold contract rule that should execute could not be evaluated for this run (the frozen trigger matrix is bound to another run) |
| MSFT | 43472ace | 2026-09-04 | pass | fail | a Gold contract rule FAILs on this run (the frozen trigger matrix is bound to it) |
| NVDA | 6f4e07f9 | 2026-08-25 | pass | needs_review | a Gold contract rule that should execute could not be evaluated for this run (the frozen trigger matrix is bound to another run) |
| NVDA | a8d47429 | 2026-08-28 | pass | needs_review | a Gold contract rule that should execute could not be evaluated for this run (the frozen trigger matrix is bound to another run) |
| NVDA | 034a0a60 | 2026-10-02 | pass | needs_review | a Gold contract rule that should execute could not be evaluated for this run (the frozen trigger matrix is bound to another run) |
| QQQ | f88c8956 | 2026-09-04 | needs_review | pass | conflict-pair should_detect is now a diagnostic that decides nothing (its review item left the verdict) |
| SNDK | e8e0f398 | 2026-09-04 | needs_review | pass | conflict-pair should_detect is now a diagnostic that decides nothing (its review item left the verdict) |

## Runs whose reasons changed but whose status did not

| Ticker | Run | Status | Review items removed | Review items added | Failures removed | Failures added |
|---|---|---|---|---|---|---|
| AMD | 949f685a | needs_review | [('should_detect_if_supported', 'A101__A304', 'pending_review')] | — | — | — |
| AMD | d5b60b8a | needs_review | — | [('conditional_only', 'AMD-AI-GROWTH-VS-VALUATION', 'not_evaluable')] | — | — |
| MSFT | 6cd2566d | needs_review | — | [('must_detect_if_evidence_present', 'MSFT-A102-DIRECT-INFERENCE-TRIGGER', 'not_evaluable')] | — | — |
| MSFT | 64568bfb | needs_review | — | [('must_detect_if_evidence_present', 'MSFT-A102-DIRECT-INFERENCE-TRIGGER', 'not_evaluable')] | — | — |
| NVDA | e3eb3909 | needs_review | [('should_detect_if_supported', 'A101__A304', 'pending_review'), ('should_detect_if_supported', 'A301__A304', 'pending_review')] | [('conditional_only', 'NVDA-GROWTH-VS-VALUATION-CONFLICT', 'not_evaluable'), ('must_detect_if_evidence_present', 'NVDA-A101-AI-GROWTH', 'not_evaluable'), ('must_detect_if_evidence_present', 'NVDA-A304-VALUATION-RISK', 'not_evaluable')] | — | — |
| NVDA | 5ffe121a | needs_review | [('should_detect_if_supported', 'A101__A304', 'pending_review'), ('should_detect_if_supported', 'A301__A304', 'pending_review')] | [('conditional_only', 'NVDA-GROWTH-VS-VALUATION-CONFLICT', 'not_evaluable'), ('must_detect_if_evidence_present', 'NVDA-A101-AI-GROWTH', 'not_evaluable'), ('must_detect_if_evidence_present', 'NVDA-A304-VALUATION-RISK', 'not_evaluable')] | — | — |
| NVDA | 948be419 | needs_review | [('should_detect_if_supported', 'A101__A304', 'pending_review'), ('should_detect_if_supported', 'A301__A304', 'pending_review')] | [('conditional_only', 'NVDA-GROWTH-VS-VALUATION-CONFLICT', 'not_evaluable'), ('must_detect_if_evidence_present', 'NVDA-A101-AI-GROWTH', 'not_evaluable'), ('must_detect_if_evidence_present', 'NVDA-A304-VALUATION-RISK', 'not_evaluable')] | — | — |
| NVDA | 2f8ee897 | needs_review | — | [('conditional_only', 'NVDA-GROWTH-VS-VALUATION-CONFLICT', 'not_evaluable'), ('must_detect_if_evidence_present', 'NVDA-A101-AI-GROWTH', 'not_evaluable'), ('must_detect_if_evidence_present', 'NVDA-A304-VALUATION-RISK', 'not_evaluable')] | — | — |
| NVDA | c9abf687 | needs_review | [('should_detect_if_supported', 'A101__A304', 'pending_review'), ('should_detect_if_supported', 'A301__A304', 'pending_review')] | [('conditional_only', 'NVDA-GROWTH-VS-VALUATION-CONFLICT', 'not_evaluable'), ('must_detect_if_evidence_present', 'NVDA-A101-AI-GROWTH', 'not_evaluable'), ('must_detect_if_evidence_present', 'NVDA-A304-VALUATION-RISK', 'not_evaluable')] | — | — |
| NVDA | 421bca7a | needs_review | [('should_detect_if_supported', 'A301__A304', 'needs_review')] | [('conditional_only', 'NVDA-GROWTH-VS-VALUATION-CONFLICT', 'not_evaluable'), ('must_detect_if_evidence_present', 'NVDA-A101-AI-GROWTH', 'not_evaluable'), ('must_detect_if_evidence_present', 'NVDA-A304-VALUATION-RISK', 'not_evaluable')] | — | — |
| NVDA | ded99ecd | needs_review | [('should_detect_if_supported', 'A101__A304', 'needs_review'), ('should_detect_if_supported', 'A301__A304', 'needs_review')] | [('conditional_only', 'NVDA-GROWTH-VS-VALUATION-CONFLICT', 'not_evaluable'), ('must_detect_if_evidence_present', 'NVDA-A101-AI-GROWTH', 'not_evaluable'), ('must_detect_if_evidence_present', 'NVDA-A304-VALUATION-RISK', 'not_evaluable')] | — | — |
| QQQ | defeb528 | needs_review | [('should_detect_if_supported', 'A001__A501', 'needs_review')] | — | — | — |
| QQQ | 0d890564 | needs_review | [('should_detect_if_supported', 'A001__A501', 'needs_review')] | — | — | — |
| SNDK | 519c93f4 | needs_review | [('should_detect_if_supported', 'A301__A304', 'needs_review')] | — | — | — |
| TSM | dfc7ceb3 | needs_review | [('should_detect_if_supported', 'A301__A304', 'needs_review')] | — | — | — |
