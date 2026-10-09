# NVDA product walkthrough -- Demo status: PENDING (not recorded this round)

**This round did not produce a video.** This environment (a CLI agent session, no browser/screen-capture access, and no Chromium browser binary installed for the repo's own Playwright e2e harness -- confirmed by checking `~/Library/Caches/ms-playwright/`, empty) cannot record a screen video. This document is the accurate startup/recording checklist requested for whoever (a human, or an agent session with browser + screen-recording access) performs the actual recording -- it is not a substitute for the video and must not be represented as one.

## Code version and run identity to state on camera

- Branch: `comqutor-source-linking-t0-t2`, HEAD `7a9aefa5c7b5c820515447c6289aeef80eac9bdc` + this round's uncommitted diff (dirty-diff sha256 recorded in `nvda_fresh_run_plan_b_frozen_config.md`; recompute fresh with `git diff | shasum -a 256` immediately before recording since further uncommitted work may have landed by then).
- `run_id`: `034a0a60-430e-41f8-8321-03a11389707a` (NVDA, analysis_date 2026-10-02). **Do not start a new Fresh Run to produce this demo** -- the walkthrough must open this exact, already-completed run.

## Prerequisite: restore this run's data into the isolated test database

This run's own backup was already created, restore-validated, and cleaned up earlier this round (see `incident_prod_db_writes_20261002/`). To show it live in the UI, restore it into `comqutor_alpha_test` again immediately before recording (same safe, zero-Provider-call operation already proven, not a new one):

```bash
# From the repo root. Restores the 2111-row backup into comqutor_alpha_test.
# Real command used earlier this round (adjust only the path if files moved):
.venv/bin/python3 - <<'PY'
import os, json, psycopg
from dotenv import load_dotenv
load_dotenv('.env')
test_url = os.environ['COMQUTOR_TEST_DATABASE_URL'].replace('postgresql+psycopg://','postgresql://')
conn = psycopg.connect(test_url); conn.autocommit = False
cur = conn.cursor()
run_id = '034a0a60-430e-41f8-8321-03a11389707a'
backup_dir = 'docs/audit_artifacts/round_source_linking_t0_t2/incident_prod_db_writes_20261002/db_backup'
manifest = json.load(open(os.path.join(backup_dir, 'manifest.json')))
for table, info in manifest['tables'].items():
    records = json.load(open(os.path.join(backup_dir, info['file'])))
    if not records: continue
    cols = list(records[0].keys())
    sql = f"INSERT INTO {table} ({', '.join(cols)}) VALUES ({', '.join(['%s']*len(cols))})"
    for rec in records:
        values = [json.dumps(rec[c]) if isinstance(rec[c], (dict, list)) else rec[c] for c in cols]
        cur.execute(sql, values)
conn.commit()
print("restored")
PY
```

**Before recording, re-check this is still empty-then-restored (never overwrite an unrelated row)**: query `SELECT count(*) FROM research_runs WHERE run_id != '034a0a60-430e-41f8-8321-03a11389707a'` and confirm the count is unchanged from before the restore.

## Startup commands (offline, zero Provider calls)

```bash
# Terminal 1: backend, pointed at the isolated test DB (the real, already-
# fixed launcher -- fails closed if the resolved DB name doesn't end in
# "_test"). Do NOT export COMQUTOR_REAL_TRADINGAGENTS_ENABLED-overriding
# budget vars here -- this is a read-only walkthrough, not a new submission.
bash docs/audit_artifacts/round_source_linking_t0_t2/run_nvda_fresh_run_isolated_db.sh

# Terminal 2: frontend dev server
cd frontend && npm run dev
# Vite will print the real local URL (typically http://127.0.0.1:5173) --
# use that exact URL, and confirm CORS is satisfied (the backend's own
# COMQUTOR_CORS_ORIGINS is forced to http://127.0.0.1:5175 by
# start_live_comqutor.sh -- if Vite picks a different port, either set
# COMQUTOR_CORS_ORIGINS to match before starting the backend, or open the
# frontend at :5175 if Vite is free to bind there).
```

**This starts a real server that CAN accept a new `POST /api/research` if someone clicks a "new research" submit button on the `/research` page.** The recording must navigate directly to the existing run's URLs below and never submit a new ticker.

## Step-by-step recording checklist

1. **Research** (`http://127.0.0.1:5173/research`) -- show the research list/history view; locate and open run `034a0a60-430e-41f8-8321-03a11389707a` (NVDA) from history -- do not submit a new ticker.
2. **Key conclusions** (`/runs/034a0a60-430e-41f8-8321-03a11389707a/research`) -- show the run's summary. **Narrate explicitly on camera**: "dominant_alphas is empty, main_conflict is null -- this is the real, official result because zero claims in this run have been human-reviewed, not because the UI is hiding a result." Point out the diagnostic candidate list (if surfaced in this view) separately from the official empty result.
3. **Source content / data basis** -- open a claim with a real linked source (e.g. a `market_agent` claim referencing the real OHLCV/indicator snapshot) and show its real source reference (URL/fragment/timestamp) in the UI; then open one of the 1016 claims with no source link and show the UI's own honest "no source" / `CANNOT_JUDGE` treatment -- do not cherry-pick only the clean examples.
4. **Structure Graph** (`/runs/034a0a60-430e-41f8-8321-03a11389707a/structure`) -- show the real structure graph for this run.
5. **Conflict Radar** (`/runs/034a0a60-430e-41f8-8321-03a11389707a/conflicts`) -- show all 8 real candidate pairs and their real `rejected` outcome with `DIRECTION_ROLE_UNRESOLVED` -- this is the "no main conflict" state to capture on camera, labeled as the real result, not a demo placeholder.
6. **Reopen from history** -- navigate back to `/research`, then reopen the same run_id again from the list, confirming it loads the identical, already-completed state (not re-running anything).
7. **Export** -- trigger the real export download from the run page and show the resulting ZIP's file listing (15 real artifact files, per this round's own earlier verification).
8. **One explicitly-labeled test-injected failure/partial-completion state** -- two options, pick based on what the real frontend test suite already covers at recording time (check `frontend/src/pages/ProcessingPage.retry.test.tsx` for an existing, intentional retry/failure fixture):
   - **(a) Preferred -- use the real run's own genuine partial state**: the 370/1040 budget-rejected claims and the `PENDING_REVIEW` content-support status on all 24 VALID-linked claims are real, disclosed partial-completion states already in this run's data -- show one of these in the UI and caption on camera: "this is the real run's own disclosed limitation, not a forced success."
   - **(b) If a synthetic UI-level failure state is specifically wanted**: reuse the frontend's own existing component-test fixture for a processing/retry failure (do not invent a new one) and caption on camera: "this is a synthetic UI state from the frontend's own test fixture, not from run 034a0a60's real data" -- so it is never confused with the real run's own results.

## Explicitly offline vs. potentially-paid

Every command above is offline / zero-Provider-call (the backend serves already-completed data; no `POST /api/research` is submitted). **The only way this demo could trigger a paid call is if someone clicks "submit new research" on the `/research` page during recording -- the checklist explicitly says not to do this.**
