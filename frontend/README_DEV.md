# COMQUTOR Alpha Frontend -- Local Development

This is the COMQUTOR research frontend: a React + TypeScript (Vite) single-page
app for the Research, Structure Graph, and Conflict Radar pages, talking to
the COMQUTOR Alpha FastAPI backend. It has no backend of its own and never
calls TradingAgents, market/news providers or an LLM directly.

## Running the backend

From the repository root, with the project's Python virtual environment
active:

    COMQUTOR_CORS_ORIGINS=http://127.0.0.1:5175 comqutor-api

This starts the API on `http://127.0.0.1:8000` (the defaults for
`COMQUTOR_API_HOST` / `COMQUTOR_API_PORT`) and allows the Vite dev server's
origin to call it.

Real TradingAgents execution is disabled server-side by default -- this
frontend never enables it and never accepts provider/model/API-key/config
input from the user. `GET /ready` reports whether real execution is
`disabled`, `configured`, or `misconfigured`; the Research page surfaces this
without ever leaking a database URL, filesystem path, or credential.

When enabled by an operator, the server uses the fixed Anthropic, Claude
Sonnet 4.6, Medium, English Research Profile. The operator must provide
`ANTHROPIC_API_KEY` in the ignored server environment. Live Provider smoke is
manual and is never run by frontend tests or CI.

## Running the frontend

    cd frontend
    npm ci
    npm run dev

The dev server runs at `http://127.0.0.1:5175` by default. Open that URL in a
browser; it redirects to `/research`.

### API base URL

Copy `.env.example` to `.env.local` if you need to point at a non-default API
origin, and set `VITE_COMQUTOR_API_BASE_URL` there. Left unset/empty, the
frontend calls the same origin it is served from. No API key or credential
belongs in this file, in any other `VITE_*` variable, or anywhere else in the
frontend -- everything under `import.meta.env` is bundled into public
client-side JavaScript.

## Viewing existing completed research runs

The Research page's "Recent research runs" list (backed by
`GET /api/research`) shows previously submitted runs. Queued, running and
failed rows open Processing; completed and partial rows open Research. Mouse,
Enter and Space use the same routing. Every page restores from `run_id` in the
URL.

The submission form sends only ticker, analysis date and analysts. Public
analyst order is Market, Sentiment, News, Fundamentals. The server resolves
the asset type; `BTC-USD` is crypto and does not support Fundamentals under
the TradingAgents CLI contract.

Processing displays persisted backend milestones only. It does not increase
progress on a timer. Failed-run Retry performs a new POST with the original
three public fields; Refresh status only polls the failed run.

## Scripts

| Command | Purpose |
| --- | --- |
| `npm run dev` | Start the Vite dev server |
| `npm run build` | Type-check and produce a production build in `dist/` |
| `npm run test -- --run` | Run the Vitest suite once (non-watch) |
| `npm run typecheck` | `tsc --noEmit` over the app and Vite config |
| `npm run lint` | ESLint over the project |
| `npm run test:e2e` | Run the isolated local Demo Playwright suite |

No globally-installed tool is required beyond Node.js/npm.
