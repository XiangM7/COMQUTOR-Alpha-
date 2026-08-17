# Phase 1 §5.1 — LIVE_SHADOW_CANARY Report

## Outcome

`LIVE_SHADOW_CANARY=FAIL`. Production authority remains `LEGACY_ADAPTER`; production cutover was not run and is not authorized.

All four preregistered historical NVDA report slots received one real Anthropic response. Three semantic outputs were accepted and one was correctly rejected fail-closed. The run nevertheless fails the strict Canary contract because the rejected Shadow call created a canonical Week2 error-log artifact, changing the user-visible API response's `artifacts.week2_llm_error_logs` flag from `false` to `true`.

No Shadow claims reached Claims / Mapper / Extractor / Graph / Activation / Exposure / Conflict. Those authoritative artifacts remained equal between Legacy-only and Shadow runs. The isolation failure is specifically the API-visible error-artifact flag; it is not a semantic-authority cutover.

## Fixed execution budget

- Planned/executed slots: `4/4`
- Logical calls: `4/4`
- Real Provider attempts: `4/4`
- Retries: `0`
- Replacement calls: `0`
- Provider responses received: `4/4`
- Semantic outputs accepted: `3/4`
- Strict Canary slots passed: `0/4` because run-wide response isolation is mandatory
- Provider/model: `anthropic` / `claude-sonnet-4-6`
- Profile: `comqutor_anthropic_medium_sonnet46_v1`
- Prompt: `structured_adapter.claim_extraction_shadow.v4`

The four calls used 24,664 input tokens and 12,031 output tokens (36,695 total). Cost is intentionally `null`: the repository does not freeze a pricing table, so no cost was inferred.

## Per-slot results

| Slot | Family | Provider | Validation | Claims admitted | Evidence resolution | Exact replay | Strict status |
|---:|---|---|---|---:|---|---|---|
| 1 | fundamental | success, 1 attempt | accepted | 27 | 29/29 unique exact | PASS | FAIL — run-wide response isolation |
| 2 | news | success, 1 attempt | accepted | 15 | 16/16 unique exact | PASS | FAIL — run-wide response isolation |
| 3 | sentiment | success, 1 attempt | accepted | 15 | 17/17 unique exact | PASS | FAIL — run-wide response isolation |
| 4 | technical | success, 1 attempt | rejected fail-closed | 0 | 23 unique exact, 1 ambiguous exact match | N/A | FAIL |

The technical rejection reason was `SHADOW_SOURCE_SPAN_INVALID`. It was not retried. Across accepted results, 57 claims were admitted and every evidence quote resolved uniquely and exactly. Fabricated or unresolved evidence admitted: `0`. Identity failures admitted: `0`.

## Replay and safety

Exact replay passed for all three accepted semantic artifacts (`3/3`) with `0` Provider calls. The semantic manifest passed validation. The frozen source artifact was unchanged, and the artifact scan found no Provider secret or hidden reasoning disclosure.

The API response comparison found exactly one difference:

```json
{
  "artifacts.week2_llm_error_logs": {
    "legacy": false,
    "shadow": true
  }
}
```

This is a strict contract failure and is recorded as data; no repair, prompt change, additional diagnostic call, or rerun was performed in this task.

## Artifacts

- Execution contract: `phase1_v4_live_shadow_canary_execution_contract.json`
- Runtime result: `phase1_v4_live_shadow_canary_runtime_result.json`
- Pre-Provider incident record: `phase1_v4_live_shadow_canary_pre_provider_incident.json` (zero Provider calls and no data egress)
- Provider-zero verifier: `scripts/verify_phase1_v4_live_shadow_canary.py` — `14/14 PASS`
- Runtime root: `outputs/canaries/phase1-v4-live-shadow-canary-20260810T213811Z`

## Decision

`READY_FOR_PRODUCTION_CUTOVER=NO`

`PRODUCTION_CUTOVER=NOT_RUN`

`NEXT_STAGE=NONE_STOP_FOR_PRODUCT_OWNER_DIRECTION`
