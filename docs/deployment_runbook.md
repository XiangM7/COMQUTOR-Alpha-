# Deployment Runbook

Scope note (MVP Audit, Evaluation, Golden Fixtures, and Delivery Readiness
Sprint, Track D, section 26): this repository already has a root
`Dockerfile` and `docker-compose.yml`, both authored for the upstream
TradingAgents CLI, not the COMQUTOR API/frontend. Extending them into a
full production container architecture (API image, frontend image,
reverse proxy, secrets management, TLS termination, horizontal scaling)
would meaningfully expand this sprint's scope beyond "audit + evaluation +
delivery infrastructure." Per this sprint's own instructions, that is
explicitly marked an **optional follow-up**, not delivered here. What
follows is the honest, minimal path to running COMQUTOR Alpha locally and
on a single small server -- this is **not** a claim of production security
hardening.

## What exists today

- `Dockerfile` (repo root): two-stage `python:3.12-slim` build,
  `pip install .`, non-root `appuser`, `ENTRYPOINT ["tradingagents"]` --
  i.e. it runs the **CLI**, not the FastAPI server. There is currently no
  Dockerfile stage that runs `comqutor-api` or serves the frontend.
- `docker-compose.yml` (repo root): `tradingagents` service (the CLI
  container above), `ollama` / `tradingagents-ollama` (local-LLM profile),
  and `postgres` (profile `postgres`, image `postgres:16-alpine`, requires
  `POSTGRES_PASSWORD` with no default, binds `127.0.0.1:5433:5432`, not
  started by the default `docker compose up`). No frontend service.

## Local development deployment (recommended path today)

This is the fastest, fully real path -- no Docker required.

```bash
python3 -m venv .venv
.venv/bin/python -m pip install -e ".[api,dev]"
cd frontend && npm ci && cd ..

# Optional: real Postgres instead of the SQLite dev fallback
# (.env: set POSTGRES_PASSWORD)
docker compose --profile postgres up -d postgres

COMQUTOR_DATABASE_URL="postgresql+psycopg://<user>:<password>@127.0.0.1:5433/<db>" \
COMQUTOR_CORS_ORIGINS=http://127.0.0.1:5175 \
.venv/bin/comqutor-api &

cd frontend && npm run dev
```

Verify with `scripts/healthcheck.sh` once both are up (see
[demo_runbook.md](demo_runbook.md) for the fully offline, no-Provider
variant of this same flow).

## Minimal single-server deployment

For a small internal/demo server (not a hardened production deployment):

1. Provision a host with Python 3.12+, Node 20+, and (optionally)
   PostgreSQL 16.
2. Clone the repo, `pip install -e ".[api,dev]"`, `cd frontend && npm ci
   && npm run build` (produces `frontend/dist/`).
3. Serve `frontend/dist/` as static files behind any web server (nginx,
   Caddy, etc.) -- this repo does not currently ship a reverse-proxy
   config; add one appropriate to your host.
4. Run `comqutor-api` as a systemd service (or any process supervisor) with:
   - `COMQUTOR_ENV=production`
   - `COMQUTOR_DATABASE_URL=<real Postgres DSN>` (production mode refuses
     to start without this -- see `DatabaseConfigurationError`
     `PRODUCTION_DATABASE_URL_REQUIRED` in
     `comqutor_alpha/storage/db/engine.py`)
   - `COMQUTOR_API_HOST=127.0.0.1` (bind loopback-only; put a reverse
     proxy in front for TLS/external access -- the API itself never binds
     `0.0.0.0` by convention)
   - `COMQUTOR_CORS_ORIGINS=<your frontend origin>`
   - Provider API keys (`DEEPSEEK_API_KEY` / `ANTHROPIC_API_KEY` / etc. --
     see `.env.example`), only if enabling real (non-offline) research
     runs.
5. Run `scripts/healthcheck.sh` (with `API_URL`/`FRONTEND_URL` pointed at
   your deployment) after every deploy.

## Explicitly out of scope for this sprint

- A production-grade Dockerfile for `comqutor-api` / the frontend build.
- Container orchestration (k8s manifests, health/readiness probes as
  container-native checks, autoscaling).
- Secrets management beyond "set an environment variable" (no Vault/KMS
  integration).
- TLS termination, WAF, or rate limiting -- put a reverse proxy in front
  and configure these at that layer.

These are flagged here as a recommended follow-up, not silently omitted.

## No-commit reminder

Never commit `.env`, `.env.local`, a populated `outputs/runs/`, or any
`POSTGRES_PASSWORD`/API key value. `.env.example` and
`.env.enterprise.example` list variable *names* only.
