# Offline Demo Runbook

A fully local, Provider-free demo of the COMQUTOR Alpha research pipeline:
Structure Graph, Activation, Conflict, and Data Quality, driven entirely
by an approved deterministic offline fixture -- 0 LLM calls, 0 market-data
Provider calls.

## Demo prerequisites

- Backend installed: `.venv/bin/python -m pip install -e ".[api,dev]"`
- Frontend dependencies installed: `cd frontend && npm install`
- Ports `8001` (API) and `5175` (frontend) free, or override with
  `COMQUTOR_API_PORT` / `COMQUTOR_FRONTEND_PORT`.

## Which fixed case this demo uses

`scripts/demo_offline.sh` (a thin wrapper around the existing
`scripts/run_w5_demo.sh`) seeds two approved, deterministic offline
fixtures via `scripts/seed_w5_demo.py`:

- **NVDA**, analysis date `2026-06-30`, analysts `market, news,
  fundamentals, sentiment`
- **QQQ**, analysis date `2026-06-30`, analysts `market, news,
  fundamentals, sentiment`

Both are drawn from `scripts/w5_demo_fixtures.py`'s
`approved_demo_outputs()` -- the same fixture used by
`tests/test_week3_nvda_sanity.py` and several other test suites, so its
shape is exercised continuously by CI, not just by this demo.

## How to start

```bash
scripts/demo_offline.sh
```

This will:

1. Seed the two fixtures into an isolated demo state
   (`.demo/w5/outputs/runs/`, `.demo/w5/comqutor_demo.db` -- never your
   real `outputs/runs/`).
2. Start the API with `COMQUTOR_REAL_TRADINGAGENTS_ENABLED=false` and
   `COMQUTOR_WEEK2_LLM_ENABLED=false`, wait for `/health` and `/ready`.
3. Start the Vite frontend, wait for it to serve `/research`.
4. Print the reachable URLs and block until you press Ctrl+C (which stops
   both processes cleanly).

If port 8001 or 5175 is already occupied by something else, the script
fails loudly with a clear message rather than silently reusing the wrong
process -- see [README_DEV.md](../README_DEV.md#troubleshooting).

## What you should see

Once ready, open `http://127.0.0.1:5175/research`:

- **Research list**: the seeded NVDA and QQQ runs, both `completed`.
- **Graph path**: open a run -> Structure Graph tab -- factor nodes and
  causal/supportive/conflicting edges, each edge showing its qualifying
  claim IDs and lineage.
- **Activation / evidence**: each Alpha's AlphaCard shows activation
  score/status plus (from the Evidence Integrity Completion sprint) raw
  supporting claim count, independent evidence fact count, distinct
  supporting agents, evidence overlap, and (when present) an overlap
  warning -- distinct from incident vs. qualifying local structural edges.
- **Conflict evidence**: the Conflict Radar's cards group evidence by
  independent fact (not one card per raw paraphrase), with per-side fact
  stats and an expandable "N merged paraphrase(s)" detail.
- **Data Quality**: the Data Quality panel's numeric-semantics summary
  (role breakdown, e.g. how many candidates were skipped as
  moving-average/technical-level rather than compared against the daily
  OHLC range).

## Common failure modes

| Symptom | Likely cause | Fix |
| --- | --- | --- |
| `Missing .venv` | Backend venv not created | `python3 -m venv .venv && .venv/bin/python -m pip install -e ".[api,dev]"` |
| `API dependencies are missing` | `[api]` extra not installed | `.venv/bin/python -m pip install -e ".[api,dev]"` |
| `Frontend dependencies are missing` | `npm install` not run | `cd frontend && npm install` |
| `INCOMPATIBLE_COMQUTOR_API on port 8001` | A non-COMQUTOR process (or an old server) already on that port | Stop it, or `COMQUTOR_API_PORT=8002 scripts/demo_offline.sh` |
| `Port 5175 is already occupied` | Another dev server (e.g. your own `npm run dev`) is running | Stop it, or `COMQUTOR_FRONTEND_PORT=5176 scripts/demo_offline.sh` |
| API readiness checks did not pass | See `.demo/w5/api.log` | Usually a DB/migration error -- check the log for the real exception |

## How to verify programmatically

```bash
scripts/healthcheck.sh   # defaults to http://127.0.0.1:8001 / :5175
```

Exits non-zero and prints which specific check(s) failed (backend health,
DB connectivity, fixture presence, run/graph/conflict API readability,
frontend build presence) -- see
[README_DEV.md](../README_DEV.md#provider-free-offline-workflow).

## How to stop

Press `Ctrl+C` in the terminal running `scripts/demo_offline.sh` -- it
traps `EXIT`/`INT`/`TERM` and stops both the API and frontend processes.
If it was started detached/backgrounded, its PIDs are recorded at
`.demo/w5/api.pid` / `.demo/w5/frontend.pid`.
