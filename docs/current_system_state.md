# Current System State

Review date: 2026-07-17

## Baseline

- Branch: `comqutor-structure-layer`
- Base HEAD: `26bf47a020c03b912c08d0fa0f5eb78f6356f464` (`26bf47a w6v2`)
- Worktree: uncommitted W7 Final Closure Patch; no commit, push or tag
- Python: 3.13.5 in `.venv`; project support is Python 3.10+

## Stage Status

| Stage | Status |
| --- | --- |
| Week 0 baseline | PASS |
| Week 1A output/research entry | PASS |
| Week 2 Alpha mapping / structure extraction | PASS |
| Week 3 graph / activation / persistence / graph API | PASS |
| Week 4 conflict / persistence / API | PASS |
| Week 5 lifecycle, API, frontend and local Demo | PASS |
| Week 6 hardening and engineering delivery | PASS |
| W7 Live Research Final Closure | PASS |
| Live Anthropic Provider smoke | USER_ACTION_REQUIRED |
| Public production | NOT_READY |

## W7 Contract

- Browser input is limited to ticker, analysis date and analysts.
- Real execution uses the fixed Anthropic / Claude Sonnet 4.6 / Medium / English profile.
- Public analyst order is `market`, `sentiment`, `news`, `fundamentals`; `sentiment` maps to
  TradingAgents `social` only at the graph boundary.
- `current_stage` is current or next work; percent and completed units count completed milestones.
- Lifecycle and progress failure updates are atomic in the production repository.
- Failed-run Retry submits a new request. Recent Runs restores processing or result routes by status.
- Ticker and asset-type handling follows TradingAgents CLI rules; `BTC-USD` resolves to `crypto`.
- Streaming execution preserves memory, context, checkpoint and post-run semantics of `propagate`.

## Verification

- Targeted backend: 227 passed
- Lifecycle/security regression: 134 passed
- Offline suite, two consecutive runs: each 1591 passed, 1 skipped, 46 deselected,
  69 subtests, 0 failed
- PostgreSQL integration: 44 passed, 0 skipped
- Frontend: typecheck PASS; ESLint PASS; 90 Vitest passed; build PASS; 7 Playwright passed
- `pip check`, compileall, changed-file Ruff, CI YAML and diff checks: PASS
- Live Anthropic request: not run by design

The one offline skip is the optional Bedrock extra (`langchain_aws` is not installed).

## Persistence

- SQLite is the offline and local Demo fallback.
- PostgreSQL 16 is the local development and integration-verification database.
- Migrations `0001` through `0005` are present; no migration `0006` was added.
- `0005` provides `research_run_progress`.
- PostgreSQL progress initialization, monotonic updates, terminal protection, JSONB, constraints,
  rollback, replacement and run isolation are verified.

## Remaining Boundaries

- Fixed Anthropic Profile: implemented, but live Provider smoke remains a user action.
- Authentication, authorization and tenant ownership: not implemented.
- Public deployment: not ready.
- MSFT Golden: `BLOCKED_BY_SPEC_CONFLICT`.
- Exposure Engine: `BLOCKED_BY_SEED`.
- Final Report product contract: deferred.
- Alpha Memory, cross-run feedback and portfolio execution: deferred.
- `.env` remains ignored and was not modified.
