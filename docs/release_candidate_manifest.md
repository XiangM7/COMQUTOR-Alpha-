# COMQUTOR Alpha Research MVP RC1

## Identity

- Release candidate name: `COMQUTOR Alpha Research MVP RC1`
- Base HEAD: `d697c356458a7c70085f2874d6c537fa199c2161`
- Branch: `comqutor-structure-layer`
- Worktree: expected uncommitted W6 implementation, tests, scripts and documents
- Runtime: local/internal, single instance; no commit, push or tag performed

## Database Migrations

1. `0001_create_week3_alpha_matches_and_structure_graphs`
2. `0002_create_week4_alpha_activations_and_alpha_conflicts`
3. `0003_create_research_runs`
4. `0004_create_agent_outputs`

## Public API

- `GET /health`, `GET /ready`
- `GET /api/alpha-library`, `GET /api/alpha-library/{alpha_id}`
- `POST /api/research`, `GET /api/research`
- `GET /api/research/{run_id}`, `/status`, `/agent-outputs`, `/graph`, `/conflicts`

## Frontend Pages

- `/research`
- `/runs/:runId/research`
- `/runs/:runId/structure`
- `/runs/:runId/conflicts`

## Delivery Scripts and Documents

- Demo: `run_w5_demo.sh`, `seed_w5_demo.py`, `verify_w5_demo.py`
- Clean install: `verify_clean_install.sh`
- Recording: `record_w6_demo.sh`, `w6_demo_recorder.mjs`
- Primary docs: installation/usage, evaluation, recording script, innovation map, deck outline,
  final gap audit, current state and this manifest

## Verification Set

- Formal Week 1 and Week 2 groups
- Lifecycle/security and Week 3/4 persistence groups
- NVDA/QQQ Golden closure and Demo verification
- Full offline suite twice
- All PostgreSQL integration tests
- Frontend typecheck, ESLint, Vitest, build and Playwright
- Clean-machine rebuild and non-mocked Chromium recording
- Ruff on changed Python, compileall, pip check, npm audits, YAML parse and `git diff --check`

Approved Golden cases: NVDA and QQQ (`2/5`). NVDA main conflict is `A101__A304`.
QQQ admits `A001__A501` and `A003__A501`; backend arbitration selects the first result.

## Boundaries and Blockers

- Structured API fields are whitelisted; raw Provider text, prompts, credentials, DSNs, paths
  and tracebacks are not public contracts.
- `.env`, generated Demo state, videos, build output, caches and run artifacts are excluded.
- MSFT is `BLOCKED_BY_SPEC_CONFLICT`; five-ticker Gate is
  `BLOCKED_BY_APPROVED_FIXTURES`.
- Live Provider is `NOT_RUN_BY_DESIGN`; Remote CI is `NOT_YET_RUN`.
- Authentication, authorization, tenant ownership and public production are not implemented.
- Deployment is `LOCAL_INTERNAL_ONLY`; public production is `NOT_READY`.
- Whole-repository Ruff retains 19 pre-existing Week 1/2 style findings; the W6 changed-file
  lint Gate passes and RC1 does not include a broad formatting rewrite.

Suggested commit message: `chore(release): freeze COMQUTOR Alpha MVP RC1`

Suggested tag after review: `comqutor-alpha-research-mvp-rc1`

## Freeze Policy

After RC1, modifications are allowed only for:

1. A reproducible bug.
2. A frozen-specification violation.
3. A real security vulnerability.
4. Downstream inability to use the release.
5. Formal arrival of an external specification input.

Do not continue modifying RC1 for code-style preferences, architecture preferences, speculative
extra strictness or additional feature ideas.
