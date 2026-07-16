# COMQUTOR Alpha Installation and Usage

## Requirements

- macOS or Linux
- Python 3.10 or newer
- Node.js 22 LTS and npm
- Git and curl
- Docker Desktop only for PostgreSQL integration tests

## Install

Clone the repository and enter it:

    git clone https://github.com/XiangM7/COMQUTOR-Alpha-.git
    cd COMQUTOR-Alpha-

Create the Python environment and install runtime and development dependencies:

    python3 -m venv .venv
    source .venv/bin/activate
    python -m pip install -e ".[api,dev]"
    python -c "import fastapi, uvicorn, sqlalchemy"

Install frontend dependencies:

    cd frontend
    npm ci
    cd ..

## Environment

The local offline Demo needs no credentials. Supported configuration names include:

    COMQUTOR_API_HOST=127.0.0.1
    COMQUTOR_API_PORT=8001
    COMQUTOR_FRONTEND_PORT=5175
    COMQUTOR_DATABASE_URL=sqlite:////safe/local/path/comqutor.db
    COMQUTOR_OUTPUT_DIR=/safe/local/path/outputs/runs
    COMQUTOR_CORS_ORIGINS=http://127.0.0.1:5175
    VITE_COMQUTOR_API_BASE_URL=http://127.0.0.1:8001

Provider credentials belong only in an ignored local `.env`. Never put credentials in a
`VITE_*` variable: Vite embeds those values in public browser JavaScript.

## Offline Demo

Start the seeded NVDA and QQQ Demo:

    ./scripts/run_w5_demo.sh

Open `http://127.0.0.1:5175/research`. COMQUTOR uses frontend port `5175` and API port
`8001`. Port `5173` is the separate Payroll project and is not COMQUTOR. Playwright uses
isolated frontend port `15173`.

If a default port is occupied:

    COMQUTOR_API_PORT=18001 COMQUTOR_FRONTEND_PORT=15175 ./scripts/run_w5_demo.sh

Use these approved inputs:

- NVDA: date `2026-06-30`; analysts `market, news, fundamentals, sentiment`
- QQQ: date `2026-06-30`; analysts `market, news, fundamentals, sentiment`

Press Ctrl+C in the Demo terminal to stop both API and frontend. The launcher handles TERM
and removes its own pid files.

## Development Mode

Start the API from the repository root:

    COMQUTOR_ENV=development COMQUTOR_API_PORT=8001 COMQUTOR_CORS_ORIGINS=http://127.0.0.1:5175 .venv/bin/python -m comqutor_alpha.api.server

In another terminal, start the frontend:

    cd frontend
    VITE_COMQUTOR_API_BASE_URL=http://127.0.0.1:8001 npm run dev

SQLite is the offline and local Demo fallback. PostgreSQL is the local development and
integration-verification database; start it with `docker compose up -d postgres`. Do not use
the Demo SQLite database as a production service database.

## Verification

Run backend offline tests:

    COMQUTOR_DATABASE_URL='' COMQUTOR_ENV='' .venv/bin/python -m pytest -m "not integration" -q

Run frontend checks:

    cd frontend
    npm run typecheck
    npm run lint
    npm run test -- --run
    npm run build
    npm run test:e2e

Rehearse a clean installation in an isolated temporary directory:

    ./scripts/verify_clean_install.sh

The rehearsal excludes `.git`, `.venv`, `node_modules`, build output, generated Demo data,
caches, and environment files. It removes only its own `/tmp/comqutor-w6-clean-*` directory.

## Troubleshooting

- `fastapi` or `uvicorn` missing: reinstall with `python -m pip install -e ".[api,dev]"`.
- `address already in use`: stop the known service or set both COMQUTOR port variables.
- `/ready` returns 404: the selected port is not a compatible COMQUTOR API.
- CORS failure: include the exact frontend origin in `COMQUTOR_CORS_ORIGINS`.
- Wrong API origin: set `VITE_COMQUTOR_API_BASE_URL` before starting or building Vite.
- Old Vite process: identify the owning project before stopping it; COMQUTOR defaults to 5175.
- Missing `node_modules`: run `npm ci` in `frontend/`.
- PostgreSQL unavailable: start Docker and `docker compose up -d postgres`, or use SQLite.

Generated local state belongs under `.demo/`, `outputs/`, `frontend/dist/`, and cache folders.
Do not commit it. Do not upload `.env`, place keys in `VITE_*`, run `docker compose down -v`,
or run `git clean -fd` as a cleanup shortcut.

## Product Boundary

- Local Demo: ready
- Live Provider execution: not run
- Public production deployment: not ready
- Authentication and tenant authorization: not implemented
