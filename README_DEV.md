# COMQUTOR Alpha -- Developer Guide

This document is the COMQUTOR-specific developer guide for this repository.
The root [README.md](README.md) is the upstream TradingAgents framework's
own README (this repo is packaged as `tradingagents`, with COMQUTOR Alpha
added on top as `comqutor_alpha/`) -- start here for anything COMQUTOR
Alpha specific.

## Product boundary: TradingAgents vs COMQUTOR

- `tradingagents/` is the vendored/forked multi-agent LLM trading-research
  framework this repo builds on (Apache-2.0, upstream: TauricResearch's
  TradingAgents). By convention it is not edited for COMQUTOR work -- see
  [docs/license_boundary_report.md](docs/license_boundary_report.md) for
  the full boundary audit and a list of files that already carry local
  edits.
- `comqutor_alpha/` is 100% COMQUTOR-original code: it calls into
  `tradingagents` (see `comqutor_alpha/runners/tradingagents_runner.py`,
  `comqutor_alpha/adapters/tradingagents_output_writer.py`) to obtain raw
  agent report text, then owns everything downstream: claim extraction,
  Alpha matching, the Structure Graph, Activation scoring, Conflict
  detection, Data Sanity checks, Evidence Fact grouping, Run Audit,
  Architecture Replay, and Cross-run Evaluation.
- `cli/` is the TradingAgents-style terminal UI (`tradingagents` console
  script). `comqutor_alpha/api/` is a separate, additive FastAPI service
  (`comqutor-api` console script) the COMQUTOR frontend talks to.

## Architecture overview

Research pipeline (one `POST /api/research` request):

```
TradingAgents multi-agent debate (news/market/fundamentals/sentiment
  analysts -> bull/bear researchers -> risk debate)
  -> raw_agent_outputs.json          (comqutor_alpha/adapters)
  -> structured_agent_outputs.json   (comqutor_alpha/structure_engine/structured_output_adapter.py:
                                       claim segmentation, boilerplate/disclaimer
                                       filtering, claim-quality gate, dedupe)
  -> alpha_matches.json              (comqutor_alpha/structure_engine/alpha_mapper.py)
  -> extracted_structures.json       (comqutor_alpha/structure_engine/structure_extractor.py)
  -> structure_graph.json            (comqutor_alpha/graph_engine/{graph_builder,pipeline}.py:
                                       factor graph + Activation v1/v2 scoring)
  -> conflict results (DB)           (comqutor_alpha/conflict_engine/conflict_detector.py)
  -> data_sanity.json                (comqutor_alpha/data_sanity/: OHLCV/dividend/split
                                       cross-checks against the reports' own numeric claims)
  -> run_audit.json                  (comqutor_alpha/api/routes_research.py:
                                       build_run_audit_payload -- additive, internal-only)
```

Every stage is a pure function of its already-materialized JSON input
(never re-reads global state), which is what makes Architecture Replay and
the Cross-run Evaluation Harness possible without touching a Provider.

### Structure Graph

`comqutor_alpha/graph_engine/graph_builder.py` merges claim-level candidate
edges (deduped by `(source, target, edge_type)`) into the run-level graph,
validating/rejecting malformed edges (self-loop, dangling reference,
invalid type/weight) and recording `graph_metrics` (node/edge counts,
`rejected_edges` by reason). `graph_engine/pipeline.py` then scores every
MVP-10 Alpha (both the frozen v1 formula and the v2 formula with Local
Structure Support + Evidence Fact Index inputs) and assembles the final
`structure_graph.json`.

### Activation

`comqutor_alpha/graph_engine/activation_scorer_v2.py` computes each Alpha's
score from qualifying evidence (`evidence_fact_index.select_supporting_alpha_claims`,
the single canonical eligibility filter shared with Conflict and the
Evidence Integrity shadow layer), local structural support (which graph
edges genuinely back that Alpha's own committed claims), and a
regime-gate on minimum unique evidence.

### Conflict

`comqutor_alpha/conflict_engine/conflict_detector.py` evaluates every
taxonomy-declared bull/bear Alpha pair (`alpha_library/alpha_taxonomy.yaml`)
and admits/suppresses/rejects each with an auditable reason-code trail. Its
own qualifying-evidence gathering is frozen; the shared Evidence Fact Index
sits strictly on top of that output as an additive fact-grouping layer
(dedup input only, never the admission logic or the score formula).

### Data Sanity

`comqutor_alpha/data_sanity/`: cross-checks numeric claims in the agent
reports (reported prices, moving averages, technical levels) against a
fetched OHLCV/dividend/split snapshot, classifying each candidate's
semantic role before deciding whether a daily-range comparison even
applies (a 200-day SMA is never compared against a single day's range).

### Evidence Fact Index

`comqutor_alpha/graph_engine/evidence_fact_index.py`: the single shared
module for "is this claim eligible supporting evidence for this Alpha" and
"which raw claims are the same underlying fact" (union-find over
duplicate-group / relation-triple / factor-signature / near-paraphrase
matches). Activation, the Evidence Integrity shadow layer, and Conflict
all consume this same module -- never a second, independently-derived
count of the same thing.

### Architecture Replay

`comqutor_alpha/replay/pipeline.py` (`run_structure_replay`) re-runs the
*current* pipeline against a prior run's frozen `raw_agent_outputs.json`
-- 0 Provider calls, source-artifact integrity (sha256/size/mtime)
verified before and after, output always written to a brand-new
`outputs/replays/<replay_id>/` directory, never overwriting the source
run. CLI: `python -m comqutor_alpha.replay --source-run-id <id>`.

### Run Audit

`comqutor_alpha/api/routes_research.py::build_run_audit_payload` (schema
`structure_correctness.run_audit.v2`) assembles an internal-only,
additive, self-consistency audit of one run: run identity, code/config
provenance, an artifact manifest with sha256 hashes, claim/relation/graph
accounting with verified conservation invariants, lineage completeness,
Activation/Conflict summaries (every declared pair, not only admitted
ones), and a self-validation verdict (`PASS` /
`PASS_WITH_WARNINGS` / `FAIL`). Every v1 field is preserved unchanged --
v2 is purely additive. There is no public GET route for `run_audit.json`
today; read it directly from the run directory.

### Cross-run Evaluation

`comqutor_alpha/evaluation/` (Track B of this sprint): an offline harness
that replays one or more "cases" (declared in
`evaluation/manifests/mvp_cases.yaml`) via the same Architecture Replay
service above, checks each case's real output against its own
`expected.yaml` oracle, and aggregates operational/structural metrics
across the batch. See [docs/demo_runbook.md](docs/demo_runbook.md) and
the "Cross-run Evaluation" section below for how to run it.

### Golden Cases

`evaluation/golden_cases/<case_id>/` bundles (`case.yaml` + `expected.yaml`
+ either a self-contained `raw_agent_outputs.json` for a
`frozen_golden_case`, or a `source_run_id` reference for a
`historical_replay_case`). See `evaluation/golden_cases/_template/` for a
fully-commented starting point.

## Backend setup

```bash
python3 -m venv .venv
.venv/bin/python -m pip install -e ".[api,dev]"
```

Run the API locally (SQLite fallback, no Postgres needed):

```bash
COMQUTOR_OUTPUT_DIR=outputs/runs \
COMQUTOR_CORS_ORIGINS=http://127.0.0.1:5175 \
.venv/bin/comqutor-api
```

- Default host/port: `127.0.0.1:8000` (override with `COMQUTOR_API_HOST` /
  `COMQUTOR_API_PORT`).
- With no `COMQUTOR_DATABASE_URL`, the API falls back to a local SQLite
  file at `<output_root>/_comqutor_alpha_graph.db` for dev/test. Schema
  migrations apply automatically on first write
  (`comqutor_alpha/storage/db/migrations.py`) -- there is no separate
  manual migration command to run.
- Setting `COMQUTOR_ENV=production` with no `COMQUTOR_DATABASE_URL` set
  raises `PRODUCTION_DATABASE_URL_REQUIRED` rather than silently falling
  back to SQLite.

## Frontend setup

```bash
cd frontend
npm ci
npm run dev
```

Dev server: `http://127.0.0.1:5175` (fixed port, `frontend/vite.config.ts`),
redirects to `/research`. Point it at a non-default API with
`VITE_COMQUTOR_API_BASE_URL` in `frontend/.env.local` (see
`frontend/.env.example`; empty = same-origin). See also
[frontend/README_DEV.md](frontend/README_DEV.md) for frontend-specific
detail (this file covers the whole repo).

## PostgreSQL setup

SQLite is the offline/local-demo fallback; PostgreSQL is the intended
local-development and integration-verification database (see
[docs/installation_and_usage.md](docs/installation_and_usage.md)).

```bash
# .env: set POSTGRES_PASSWORD (no default -- never commit a real one)
docker compose --profile postgres up -d postgres
COMQUTOR_DATABASE_URL="postgresql+psycopg://<user>:<password>@127.0.0.1:5433/<db>" .venv/bin/comqutor-api
```

The `postgres` compose service binds `127.0.0.1:5433:5432` and is not
started by the default `docker compose up`.

## Environment variables

See `.env.example` (LLM Provider API keys) and `.env.enterprise.example`
(Azure OpenAI). COMQUTOR-specific variables (not currently listed in
`.env.example` -- see the table below) are read directly via
`os.environ`/`os.getenv` in `comqutor_alpha/`:

| Variable | Purpose | Default |
| --- | --- | --- |
| `COMQUTOR_API_HOST` | API bind host | `127.0.0.1` |
| `COMQUTOR_API_PORT` | API bind port | `8000` |
| `COMQUTOR_CORS_ORIGINS` | Allowed CORS origins (comma-separated) | none |
| `COMQUTOR_DATABASE_URL` | SQLAlchemy DSN | SQLite fallback (dev/test only) |
| `COMQUTOR_ENV` | `production` disables the SQLite fallback | unset |
| `COMQUTOR_OUTPUT_DIR` | Root directory for `outputs/runs/<run_id>/` artifacts | `./outputs/runs` |
| `COMQUTOR_WEEK2_LLM_ENABLED` | Enable the optional Week-2 LLM claim-quality gate | `false` |
| `COMQUTOR_WEEK2_LLM_PROVIDER` / `_MODEL` / `_BASE_URL` / `_TIMEOUT_SECONDS` / `_MAX_RETRIES` / `_MAX_CALLS` | Week-2 LLM gate configuration | see `structure_engine/week2_llm.py` |
| `TRADINGAGENTS_LLM_PROVIDER` | TradingAgents LLM provider selection | see `tradingagents/default_config.py` |
| `TRADINGAGENTS_QUICK_THINK_LLM` | TradingAgents quick-think model override | see `tradingagents/default_config.py` |
| `TRADINGAGENTS_LLM_BACKEND_URL` | TradingAgents LLM backend URL override | see `tradingagents/default_config.py` |

## DeepSeek configuration

The default research profile (`comqutor_deepseek_default_v1`, see
`comqutor_alpha/research_profiles.py`) uses DeepSeek via an
OpenAI-compatible chat-completions endpoint. Set `DEEPSEEK_API_KEY` in
`.env` (see `.env.example`); no separate `deepseek` SDK package is
required (`comqutor_alpha/llm/deepseek_smoke.py`'s own docstring covers
the client shape).

## Tests

```bash
# Backend (excludes the Postgres-only integration suite)
.venv/bin/python -m pytest -m "not integration" -q

# Postgres integration tests (needs COMQUTOR_TEST_DATABASE_URL, see CI config)
.venv/bin/python -m pytest -m integration -q

# Frontend
cd frontend && npm run test -- --run
```

## Lint / build

```bash
.venv/bin/ruff check comqutor_alpha/ tests/ cli/
cd frontend && npm run lint && npm run typecheck && npm run build
```

## Troubleshooting

- `Missing .venv` from `scripts/run_w5_demo.sh` / `scripts/demo_offline.sh`:
  create the venv and `pip install -e ".[api,dev]"` first.
- `Frontend dependencies are missing`: `cd frontend && npm install`.
- `INCOMPATIBLE_COMQUTOR_API on port <n>`: another process (not a COMQUTOR
  API) is already listening on that port -- stop it or set
  `COMQUTOR_API_PORT`.
- `PRODUCTION_DATABASE_URL_REQUIRED`: you set `COMQUTOR_ENV=production`
  without `COMQUTOR_DATABASE_URL` -- either unset `COMQUTOR_ENV` for local
  dev or set a real Postgres URL.
- A Run Audit `accounting_invariants` entry with `passed: false` means a
  real bookkeeping identity broke (see `docs/mvp_audit_evaluation_delivery_sprint_report.md`
  for how these are derived) -- treat it as a genuine defect signal, not
  noise.

## Provider-free offline workflow

Everything below performs 0 Provider calls (no LLM, no market-data
fetch) and never mutates a source run:

- **Architecture Replay**: `python -m comqutor_alpha.replay --source-run-id <run_id>`
  (writes to `outputs/replays/`, never `outputs/runs/<run_id>/`).
- **Cross-run Evaluation**: `python -m comqutor_alpha.evaluation.cross_run --manifest evaluation/manifests/mvp_cases.yaml --output-dir outputs/evaluations/<id>`.
- **Offline demo**: `scripts/demo_offline.sh` (seeds approved deterministic
  fixtures, starts the API with `COMQUTOR_REAL_TRADINGAGENTS_ENABLED=false`
  and `COMQUTOR_WEEK2_LLM_ENABLED=false`, starts the frontend).
- **Offline research request**: `POST /api/research` with
  `offline_raw_agent_outputs` supplied directly in the request body
  (disabled when `COMQUTOR_ENV=production`).

## Artifact locations

- `outputs/runs/<run_id>/`: one directory per completed/in-progress
  research run (`metadata.json`, `raw_agent_outputs.json`,
  `structured_agent_outputs.json`, `alpha_matches.json`,
  `extracted_structures.json`, `structure_graph.json`, `data_sanity.json`,
  `market_data_snapshot.json`, `run_audit.json`,
  `tradingagents_comqutor_vocabulary_snapshot.json`,
  `week3_pipeline_status.json`). Allowlisted filenames only -- see
  `comqutor_alpha/storage/file_store.py::ALLOWED_ARTIFACT_FILENAMES`.
- `outputs/replays/<replay_id>/`: Architecture Replay output (never
  written into `outputs/runs/`).
- `outputs/evaluations/<evaluation_id>/`: Cross-run Evaluation Harness
  output (`evaluation_summary.json`, `case_results.json`,
  `case_results.csv`, `evaluation_report.md`, `failures.json`, plus a
  `replays/` subdirectory of the harness's own replay runs).
- `.demo/w5/`: isolated demo state (SQLite DB, seeded run outputs, logs)
  used by `scripts/run_w5_demo.sh` / `scripts/demo_offline.sh` -- never
  the same directory as your real dev `outputs/runs/`.

## No-commit / no-Provider development patterns

- Prefer `offline_raw_agent_outputs` or Architecture Replay over a live
  TradingAgents run when iterating on anything downstream of claim
  extraction -- both are deterministic and free.
- Never commit `.env`, `.env.local`, real API keys, or a populated
  `outputs/runs/`/`.demo/` directory.
- This repository's convention throughout the Structure/Evidence/Conflict
  integrity sprints has been: audit first (report exact files/functions
  before changing anything), verify every fix against a real historical
  run via Architecture Replay (never just unit tests), and never
  overwrite a historical run's own artifacts.
