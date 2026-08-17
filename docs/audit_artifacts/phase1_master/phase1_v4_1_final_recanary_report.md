# Phase 1 v4.1 Final Live-Shadow Re-Canary Report

## Outcome

`FINAL_V4_1_RECANARY=FAIL`. The frozen four-slot run completed with exactly four logical calls and four real Provider attempts, sequentially, with zero retries and zero subagents. All four transports returned successfully, but no proposal passed deterministic v4.1 admission. Production cutover was therefore not run and `LEGACY_ADAPTER` remains authoritative.

## Slot results

| Slot | Family | Transport | Located / evidence | Duplicate items | Admission | Stable reasons |
|---:|---|---|---:|---:|---|---|
| 1 | fundamental | SUCCESS | 34 / 36 | 2 | FAIL | `SHADOW_EMPTY_OR_NON_SUBSTANTIVE`, `SHADOW_SOURCE_SPAN_INVALID` |
| 2 | news | SUCCESS | 0 / 17 | 0 | FAIL | `SHADOW_EMPTY_OR_NON_SUBSTANTIVE`, `SHADOW_SOURCE_SPAN_INVALID` |
| 3 | sentiment | SUCCESS | 0 / 24 | 0 | FAIL | `SHADOW_EMPTY_OR_NON_SUBSTANTIVE`, `SHADOW_SOURCE_SPAN_INVALID` |
| 4 | technical | SUCCESS | 4 / 22 | 1 | FAIL | `SHADOW_EMPTY_OR_NON_SUBSTANTIVE`, `SHADOW_SOURCE_SPAN_INVALID` |

The duplicate-quote branch was exercised. In the rejected proposals, globally duplicated quotes lacked a usable registered candidate binding, while many supplied candidate IDs pointed to spans that did not contain the supplied exact quote exactly once (`CANDIDATE_LOCAL_NO_EXACT_MATCH`). The strict resolver rejected all affected claims; no ambiguous, unresolved, fabricated, or identity-mismatched evidence entered authoritative output.

## Safety and persistence

- Rejected forensic payloads were persisted for 4/4 slots and remained non-authoritative.
- Identity binding and sidecar persistence passed for 4/4 slots.
- Legacy/API authoritative outputs remained equal between Legacy and Shadow executions for 4/4 slots.
- No Shadow claim entered Mapper, Extractor, Graph, Activation, or Conflict authoritative downstream artifacts.
- Provider-zero replay verification passed structurally with zero Provider calls, but there were zero accepted reports; therefore the required accepted-output Exact Replay gate was 0/4 and could not pass.
- Source reports and the frozen execution contract remained unchanged.

## Budget and stop decision

`LOGICAL_CALLS=4/4`, `REAL_PROVIDER_ATTEMPTS=4/4`, `RETRIES=0`, `SUBAGENTS=0`, and `POST_CANARY_PROVIDER_CALLS=0`. Cumulative Phase 1 accounting is 99 logical calls and 106 Provider attempts.

Per the frozen task rule, no code repair, v4.2/v5 protocol, second Re-Canary, fifth Provider call, or Production cutover was attempted after failure. Section §5.1 is `BLOCKED_AT_FINAL_RECANARY`; the next allowed stage is `NONE`.

## Verification note

Before Provider execution, 36 focused tests, both 9/9 hardening/repair verifiers, the 22/22 Phase 1 verifier, Ruff, and `git diff --check` passed. After the honest final state was recorded, the existing Phase 1 verifier reported 20/22: its state enum does not contain `FINAL_V4_1_RECANARY`, and its mode-flag check only recognizes the older live/cutover state names. These verifier bookkeeping failures were not repaired after Canary failure, in accordance with the stop rule; budget, ledger, secret scan, protected-file, history, and all other checks passed.
