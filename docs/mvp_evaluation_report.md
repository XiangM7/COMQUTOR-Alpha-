# COMQUTOR Alpha Research MVP Evaluation

## Product

COMQUTOR turns multi-agent research into taxonomy-bounded Alpha structures, deterministic
activation and evidence-linked conflict readouts.

## Scope and Status Vocabulary

- **Implemented**: present in production code.
- **Verified**: exercised by the stated local test or rehearsal.
- **Not run**: intentionally not executed.
- **Blocked**: requires an approved specification, fixture or control.
- **Deferred**: outside the Research MVP.

Implemented scope: TradingAgents/offline input boundary, structured claims, Alpha mapping,
structure extraction, graph and activation, conflict persistence/API, run lifecycle/history,
local dashboard, SQLite Demo and PostgreSQL integration path.

## Gate Matrix

| Gate | Status | Evidence |
| --- | --- | --- |
| Week 0 baseline | Verified | Baseline reports and setup records |
| Week 1A output/research entry | Verified | Formal Week 1 API and persistence tests |
| Week 2 mapping/extraction | Verified | Acceptance, labeled and extractor gates |
| Week 3 graph/activation/persistence/API | Verified | SQLite and PostgreSQL graph tests |
| Week 4 conflict core/persistence/API | Verified | Unit, pipeline, NVDA and QQQ tests |
| Week 5 lifecycle/dashboard/Demo | Verified | API, Vitest and Playwright E2E |
| W6.0 audit | Verified | Final gap audit |
| W6.1 hardening | Verified | Migration 0004, DB-first reads, score and security tests |
| W6.2 Golden Gate | Verified for 2/5 | NVDA and QQQ approved; five-ticker Gate blocked |
| W6.3 frontend regression | Verified | TypeScript, ESLint, 53 unit tests, build and six E2E tests |
| W6.4 clean-machine delivery | Verified | Isolated `/tmp` reinstall, seed, HTTP and cleanup rehearsal |
| W6.5 delivery materials | Implemented | Evaluation, recording, patent map and deck outline |
| W6.6 release freeze | Verified | Final audit, RC manifest and current state agree |

## Architecture and Data Flow

Text architecture: TradingAgents or approved offline fixture → raw internal artifact → structured
claim adapter → `agent_outputs` DB rows → Alpha mapper → extracted structures → graph/activation →
conflict detector → persistence repositories → whitelisted FastAPI readout → React dashboard.

New-run structured outputs, graph and conflicts are DB-first. Artifacts remain for compatibility
and audit support. Stable run, claim and source IDs preserve lineage across every layer.

## Evaluation Evidence

- SQLite: migration, replacement, rollback, isolation and API behavior verified offline.
- PostgreSQL: JSONB, unique constraints, idempotency, rollback, replacement and run isolation
  verified against PostgreSQL 16.
- NVDA: approved main conflict `A101__A304`; A101 and A304 both retain claim/evidence links.
- QQQ: approved conflicts `A001__A501` and `A003__A501`; main conflict is the backend
  arbitration's first result, not a frontend rule.
- Explainability: activation components, admitted pair, bull/bear sides, reason codes and evidence
  remain inspectable.
- Traceability: conflict evidence resolves through Alpha matches to persisted structured claims.

No live Provider, LLM, market or news request was run for this evaluation.

## Security and Operating Boundary

Public responses whitelist structured fields. Raw Provider output, prompts, configuration,
credentials, DSNs, local paths and tracebacks are excluded. Numeric persistence boundaries reject
strings, booleans, non-finite and out-of-range scores. `.env` remains ignored and is not part of
clean-room copying.

This is a local single-instance Research MVP. Performance is bounded by synchronous local Demo
startup, SQLite single-process use and the tested fixture/data sizes. No public load, multi-tenant,
high-availability, latency SLO or horizontal-scale claim has been verified.

## Blocked and Deferred

- Approved Golden cases: `2/5`; three additional approved fixtures are blocked by availability.
- MSFT Golden Gate: blocked by taxonomy/specification conflict.
- Authentication, authorization and tenant ownership: blocked for public deployment.
- Formal external Week 4 product acceptance and public production: blocked.
- Live Provider validation: not run by design.
- Alpha Memory, cross-run feedback, exposure seed, portfolio execution and autonomous trading:
  deferred outside this MVP.

## Recommendation

Recommend a **local/internal Research MVP release candidate** after W6.6 final verification and
review. Do not present it as a five-ticker, live-Provider, authenticated or production-ready system.
