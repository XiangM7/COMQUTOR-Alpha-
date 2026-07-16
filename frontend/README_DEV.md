# COMQUTOR Alpha Frontend -- Local Development

This is the W5.2 dashboard frontend: a React + TypeScript (Vite) single-page
app for the Research, Structure Graph, and Conflict Radar pages, talking to
the existing COMQUTOR Alpha FastAPI backend. It has no backend of its own and
never calls a real TradingAgents/LLM/market/news provider or any other paid
external service.

## Running the backend

From the repository root, with the project's Python virtual environment
active:

```bash
COMQUTOR_CORS_ORIGINS=http://127.0.0.1:5173 comqutor-api
```

This starts the API on `http://127.0.0.1:8000` (the defaults for
`COMQUTOR_API_HOST` / `COMQUTOR_API_PORT`) and allows the Vite dev server's
origin to call it.

Real TradingAgents execution is disabled server-side by default -- this
frontend never enables it and never accepts provider/model/API-key/config
input from the user. `GET /ready` reports whether real execution is
`disabled`, `configured`, or `misconfigured`; the Research page surfaces this
without ever leaking a database URL, filesystem path, or credential.

## Running the frontend

```bash
cd frontend
npm install
npm run dev
```

The dev server runs at `http://127.0.0.1:5173` by default (Vite's standard
port). Open that URL in a browser; it redirects to `/research`.

### API base URL

Copy `.env.example` to `.env.local` if you need to point at a non-default API
origin, and set `VITE_COMQUTOR_API_BASE_URL` there. Left unset/empty, the
frontend calls the same origin it is served from. No API key or credential
belongs in this file, in any other `VITE_*` variable, or anywhere else in the
frontend -- everything under `import.meta.env` is bundled into public
client-side JavaScript.

## Viewing existing completed research runs

The Research page's "Recent research runs" list (backed by
`GET /api/research`) shows previously submitted runs. Click any row to open
its Research / Structure Graph / Conflict Radar pages directly by `run_id`,
without resubmitting a new request. Each of the three run pages restores its
state purely from the `run_id` in the URL, so refreshing the page or sharing
the URL works without depending on prior in-memory navigation state.

## Scripts

| Command | Purpose |
| --- | --- |
| `npm run dev` | Start the Vite dev server |
| `npm run build` | Type-check and produce a production build in `dist/` |
| `npm run test -- --run` | Run the Vitest suite once (non-watch) |
| `npm run typecheck` | `tsc --noEmit` over the app and Vite config |
| `npm run lint` | ESLint over the project |

No globally-installed tool is required beyond Node.js/npm.
