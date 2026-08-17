# Phase 1 §5.1 — Canary Repair Verification

`FAILURE_A_OFFLINE_VERIFICATION=PASS`

The Shadow Gateway error path is now isolated under its existing run-local Shadow runtime namespace. Offline real-Gateway-path tests reproduced validation rejection, Provider exception, and malformed output without toggling canonical Week2 error metadata. Shared Week2's default canonical behavior remains covered and unchanged.

`FAILURE_B_CLASSIFICATION=B1_EXPECTED_SAFE_AMBIGUOUS_REJECTION`

No resolver or Prompt change was made. The resolver correctly refused to choose between two exact matches. The exact rejected Provider proposal was not retained in the historical artifacts, so recorded-response revalidation is not applicable and the missing quote/offset data is not guessed.

The original Canary artifacts and Provider ledgers remain unchanged. Original Exact Replay remains `3/3 PASS` with zero Provider calls. The repair verifier passed `9/9`, the original Canary verifier passed `14/14`, the Phase 1 Master verifier passed `22/22`, and Ruff, JSON validation, sensitive-content scanning, and `git diff --check` all passed.

`CANARY_FAILURE_REPAIR=PARTIAL`

`READY_FOR_RECANARY=NO`

`NEXT_ALLOWED_STAGE=PRODUCT_OWNER_DECISION`
