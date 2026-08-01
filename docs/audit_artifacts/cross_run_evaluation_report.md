# Cross-run Evaluation Report (eval-20260801T002017Z-d19cb673)

Generated: 2026-08-01T00:22:26Z

## Operational correctness
- Cases: 11 total, 6 completed, 5 pending_fixture, 0 blocked, 0 error
- Provider calls: 0 (must be 0)
- Policy violations: none

## Structural correctness (per case, from expected.yaml)
- nvda_historical_v1: PASS (7 expectation(s) checked)
- msft_historical_v1: PASS (7 expectation(s) checked)
- sndk_historical_v1: PASS (7 expectation(s) checked)
- amd_historical_v1: PASS (7 expectation(s) checked)
- googl_historical_v1: PASS (7 expectation(s) checked)
- qqq_historical_v1: PASS (7 expectation(s) checked)
- avgo_pending_v1: SKIPPED (pending_fixture: GOLDEN_CASE_BUNDLE_NOT_PRESENT: evaluation/golden_cases/avgo_pending_v1)
- spy_pending_v1: SKIPPED (pending_fixture: GOLDEN_CASE_BUNDLE_NOT_PRESENT: evaluation/golden_cases/spy_pending_v1)
- tsm_pending_v1: SKIPPED (pending_fixture: GOLDEN_CASE_BUNDLE_NOT_PRESENT: evaluation/golden_cases/tsm_pending_v1)
- smci_pending_v1: SKIPPED (pending_fixture: GOLDEN_CASE_BUNDLE_NOT_PRESENT: evaluation/golden_cases/smci_pending_v1)
- amzn_pending_v1: SKIPPED (pending_fixture: GOLDEN_CASE_BUNDLE_NOT_PRESENT: evaluation/golden_cases/amzn_pending_v1)

## Semantic/domain correctness
Not automatically verified by this harness -- see any `manual_review` expectations above
and each case's own `manual_claim_labels.csv` (when present). A passing structural check
is evidence the pipeline behaved consistently, not a claim that the investment thesis is
correct.

## Manually unverified expectations
- none declared
