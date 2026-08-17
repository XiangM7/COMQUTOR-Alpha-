# Phase 1 Master — Anthropic routing execution report

Final gate: `BLOCKED` (`BLOCKED_ANTHROPIC_PROVIDER_RELIABILITY`)

The requested task-specific Anthropic route was implemented and exercised against the frozen NVDA Smoke corpus. Qualification passed, but the 4-report Smoke did not meet the Provider reliability threshold, so the state machine correctly stopped before Pilot/Core and did not send the remaining 20 historical reports.

## Implemented contract

- `structured_claim_shadow` routes only to `comqutor_anthropic_medium_sonnet46_v1` (`anthropic` / `claude-sonnet-4-6`).
- `structured_adapter`, `alpha_classifier`, and `structure_extractor` retain the existing DeepSeek default configuration.
- The Shadow-only execution policy is `timeout_seconds=180`, `max_retries=1`. Retry is limited to timeout, HTTP 429/5xx, and explicit transient transport failures.
- Malformed JSON, validation/provenance/identity rejection, abstention, valid-empty output, and semantic quality do not trigger retries.
- Provider/model/profile and execution-policy identity are persisted on semantic-call records; cross-provider cache identity remains distinct.
- Prompt version, SHA, schema, candidate segments, validator, and semantic authority remain frozen.
- Provider failures are audited per report as `AUDITABLE_NO_ACCEPTED_OUTPUT`; they are not mislabeled as Exact Replay defects.
- The global Provider ledger is append-only and includes the two historical interrupted executions and the three ad-hoc DeepSeek diagnostics.

## Credential and qualification result

The sanitized preflight passed:

- Profile: `comqutor_anthropic_medium_sonnet46_v1`
- Provider/model: `anthropic` / `claude-sonnet-4-6`
- Credential variable: `ANTHROPIC_API_KEY`
- Key present: `true`; recorded length: `108`; value never printed or persisted
- Host: `api.anthropic.com`

The first qualification attempt was made inside the restricted sandbox and ended client-side with `BLOCKED_ANTHROPIC_NETWORK`; it remains preserved in the append-only ledger. After the product owner explicitly authorized the stated data egress, one replacement qualification request was made with unrestricted network access and returned the required parsed JSON. No raw Provider response was persisted.

## Anthropic Smoke result

Evaluation directory: `outputs/evaluations/phase1-master-anthropic-20260807T011444Z-7ce7880c`

| NVDA family | Provider result | Attempts | Retry | Validation |
|---|---:|---:|---:|---|
| fundamental | timeout | 2 | 1 | not run |
| news | malformed JSON | 2 | 1 transient retry before final response | not run |
| sentiment | malformed JSON | 1 | 0 | not run |
| technical | timeout | 2 | 1 | not run |

Summary:

- Provider-completed responses: 2/4 (50%)
- Timeouts: 2/4
- Accepted: 0; valid-empty: 0; abstained: 0
- Unique reports: 4/4; duplicate logical calls: 0
- Prompt version/SHA: unchanged
- Production artifacts and production authority: unchanged

The engineering gate requires at least 3/4 Provider-completed responses. The observed 2/4 therefore yields `BLOCKED_ANTHROPIC_PROVIDER_RELIABILITY`. Because the Smoke gate failed, Pilot (8 new reports), Core (12 new reports), and the human-review CSV were not started. The same reports were not called again, and there was no fallback to DeepSeek or a third model.

## Exact Replay correction

Provider-zero per-report replay passed for all four report records:

- fundamental: `AUDITABLE_NO_ACCEPTED_OUTPUT`
- news: `AUDITABLE_NO_ACCEPTED_OUTPUT`
- sentiment: `AUDITABLE_NO_ACCEPTED_OUTPUT`
- technical: `AUDITABLE_NO_ACCEPTED_OUTPUT`

There were no accepted outputs to replay. Each failure record is nevertheless complete and auditable, so the replay audit's final status is `PASS` with zero Provider calls. Exact Replay is not the root blocker.

## Provider accounting

Master contract budget was preserved, never reset:

- 15/53 logical calls
- 22/105 Provider attempts

All Phase 1 actual usage in the global ledger:

- 15 append-only events
- 22 exactly known logical calls
- 2 historical `UNKNOWN_MINIMUM` events, each with a minimum of 4 logical calls
- Minimum total logical calls: 30
- Total known Provider attempts: 47
- The 3 ad-hoc diagnostic calls are included as 3 logical calls / 3 attempts

## Verification

- Phase 1 Master targeted tests: `21 passed`
- Structured-output Shadow suite: `134 passed`
- LLM runtime suite: `83 passed`
- Replay suite: `40 passed`
- Master verifier: `17/17 PASS`
- LLM boundary audit: `4/4 PASS`
- Guarded full suite: `2864 passed, 1 skipped, 47 deselected, 69 subtests passed`
- Ruff: PASS
- `git diff --check`: PASS
- HEAD remains `b5837e80a4550fc35165d0013a8ef0f27ccb4c8f`; no commit or push was performed

## Final status and next action

```text
SEMANTIC_QUALITY=UNPROVEN
HUMAN_REVIEW=PENDING
PRODUCTION_AUTHORITY=LEGACY_ADAPTER
```

No automatic continuation is permitted from this blocker. A product-owner decision is required before evaluating any third profile/model. Do not retry the same four Anthropic reports, do not silently fall back to DeepSeek, and do not start Pilot/Core while the Smoke reliability gate remains blocked.
