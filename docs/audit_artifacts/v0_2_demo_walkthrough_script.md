# v0.2 Demo Walkthrough Script

**For a single, real screen recording covering NVDA, QQQ, SNDK.** Uses Demo Mode (clearly dated/versioned/run_id-labelled persisted results) — does not depend on a new 30+ minute live Fresh Research run during the recording. Fresh Research is described, not re-triggered live, except optionally as a background-task demonstration (Step 0 below).

**DEMO_RECORDING_REQUIRES_MANUAL_CAPTURE = YES.** This script is the guide for that capture; no recording exists yet.

All three runs below were verified live through the actual application/API this task, immediately before writing this script (see `v0_2_demo_walkthrough_checklist.json`).

---

## Step 0 (optional, ~30s): Fresh Research as a background task

Open the "New Research" flow, submit a ticker, and show the resulting `run_id` with `status: queued → running`, `progress_percent`, and `current_stage` (e.g. "Running the Sentiment Analyst"). Narrate: *"A fresh run takes 25–35 minutes end-to-end and executes in the background — the UI never blocks on it. For the rest of this walkthrough we'll use already-completed runs so we can show every view without idle waiting."* Do not wait for this run to finish on camera.

---

## Part 1 — NVDA (run `ded99ecd-a186-4a90-859e-0f1a0efa43db`, 2026-09-17, Fresh)

1. **Research view.** Open the run. Point out the visible `run_id` and `analysis_date: 2026-09-17`. Status: `completed`, 12 agents, 1102 structured outputs.
2. **Structure Graph.** Show dominant Alphas **A301** (Revenue Expansion, +74.21) and **A304** (Multiple Compression, −71.73), and active **A601** (Narrative Momentum, +69.66). Graph coherence 100.0.
3. **Evidence.** Trace A304's bear-side evidence, e.g. *"89% probability of no Fed cuts in 2026... discount rates stay high; multiple headwind"* — genuinely ticker-specific.
4. **Conflict Radar.** Main conflict admitted: **A304__A601**. Explain: this is a canonical taxonomy pair, cleanly admitted under the frozen admissibility formula — but it is **not** on NVDA's own predeclared allowed list (`A101__A304`, `A301__A304`). State plainly: *"This run is reported as REVIEW_REQUIRED, not PASS — we do not force a match to the allow-list."*
5. **Do-not-force demonstration.** Point out A301__A304 (an allowed pair) was evaluated and **suppressed** (`NO_BULL_TICKER_SPECIFIC_SUPPORT`) despite A301 being independently dominant — the system did not force it into the conflict role just because it could have.

## Part 2 — QQQ (run `0d890564-2479-4361-94e8-25c48af3b9a8`, 2026-09-17, Fresh)

1. **Research view.** `run_id` and `analysis_date: 2026-09-17` visible, `completed`.
2. **Structure Graph.** **No dominant Alpha this run** — narrate: *"This is legitimate, not a defect — a dominant Alpha is never required."* Active: A003, A304, A501, A601.
3. **Evidence.** Trace A003's bull-side evidence: *"QQQ inflows totaled nearly $1B on 2026-09-16 (etf.com)"* — genuinely fund-level, not one constituent stock.
4. **Conflict Radar.** Main conflict admitted: **A003__A501** — on QQQ's own allowed list. Contrast briefly with QQQ's separate, older, carried Formal Gold history (an earlier run's off-list A301__A304, `REVIEW_REQUIRED`, unchanged) to show the product's history is preserved honestly, not overwritten.

## Part 3 — SNDK (run `e8e0f398-7b26-4462-8135-a1410ea5b335`, 2026-09-04, persisted)

1. **Research view.** `run_id` and `analysis_date: 2026-09-04` visible — narrate clearly: *"This is a persisted run from an earlier date, reused for this demo — not a fresh run today."* `completed`, 918 structured outputs.
2. **Structure Graph.** Dominant: **A201** (Semiconductor Supercycle, +84.22, 42 evidence groups/9 agents).
3. **Evidence.** Trace: *"Motley Fool frames both Micron and SanDisk as beneficiaries of a surge in memory demand with no sign of it slowing down."*
4. **Conflict Radar — the key demonstration.** **No main conflict admitted at all.** Show the full arbitration: 3 rejected, 3 suppressed, zero admitted. Narrate: *"This is the product deliberately NOT manufacturing a conflict. A301__A304 — an allowed pair for SNDK — was suppressed because neither side had ticker-specific support. The absence of a conflict here is itself evidence the system is working correctly."*

## Closing note (source citations)

Anywhere a `claim_id` is shown, state explicitly: *"A claim_id is our own internal identifier into this run's persisted agent output — it is not, by itself, proof the underlying source was externally verified."*
