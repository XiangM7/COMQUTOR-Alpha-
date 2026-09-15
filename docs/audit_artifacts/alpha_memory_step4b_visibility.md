# Alpha Memory — Step 4B: Feedback Loop Visibility

SHADOW ONLY. **Provider calls: 0. TradingAgents calls: 0. No fresh research.**

## Existing API path audit

Before changing anything: `run_audit.json` (where `alpha_memory` lives) had no public GET route, and the existing research-result endpoint (`GET /api/research/{run_id}`, backed by `build_research_response()`) did not include it. **Reused, not replaced** — added one key to the response by reading the SAME already-loaded `run_audit_for_gate` variable that function already reads for `evidence_stance_summary`, mirroring that exact existing pattern. Zero new routes, zero new file reads, zero write endpoint.

## Frontend location

`frontend/src/pages/ResearchRunPage.tsx` — the existing research-result page, immediately after the existing "Unclassified findings" panel. New `AlphaMemoryPanel` component defined inline, same convention as its neighbor, no new page/route.

## What's visible

"Alpha Memory **SHADOW**" header → "Activation modulation: Off" → shadow explanation sentence → one compact line per Alpha (e.g. "A101 — 5 current structures, 2 recurring, 3 first seen, 40% recurrence") → expandable recurring-structure detail showing `source --edge_type--> target`, "Previously observed: N prior runs", real first-seen/last-prior-observation timestamps. Raw `phi_id` and source run IDs are tucked inside a nested, closed-by-default "Technical detail" — never the primary label.

## Shadow/modulation-off communication

`activation_modulation_applied` is read straight from the API and rendered verbatim as "On"/"Off" — never derived or assumed. The shadow-only sentence is always present, unconditionally.

## Real NVDA values displayed

Verified through the actual `GET /api/research/{run_id}` path (not a synthetic mock) against real persisted run `2f8ee897`: **15 current, 6 recurring, 9 first-seen, 13 total prior observations** — matching Step 3's own finding exactly.

## MSFT zero-recurrence behavior

Verified the same way against real run `6cd2566d`: **12 current, 0 recurring** — renders "No exact historical recurrence found for this Alpha" for every Alpha, never "memory failed" or any lifecycle word.

## Aggregate fingerprint — a deliberate scoping note

The panel states the aggregate is "a secondary diagnostic only" but does **not** claim whether it changed vs. a specific prior run, because that cross-run aggregate comparison isn't computed/exposed by the current API payload (only the current run's own fingerprint id is). Rather than fabricate that comparison in the frontend, the wording stays narrower than the task's own suggested example. Reported here as a conscious decision, not an oversight.

## John-facing proof artifact

`docs/audit_artifacts/alpha_memory_feedback_loop_proof.json`/`.md` — built from the same real, selected NVDA run, showing the full loop (current structure → matched φ → real prior run IDs → recurrence summary) with concrete numbers and a table of all 6 recurring relations and their actual historical source runs.

## Files changed

Backend: `routes_research.py` (+1 field). Frontend: `types.ts` (+4 interfaces), `adapters.ts` (+4 functions), `ResearchRunPage.tsx` (+component), `styles.css` (+rule block). Tests: 4 new backend, 17 new frontend (21 total, all passing). Three real runs' `run_audit.json` regenerated offline at zero cost.

## Proof B1/B2/B4/Conflict unchanged

Every existing field in the API response and every existing frontend section remain byte-identical with `alpha_memory` present — verified by dedicated tests on both sides. Full regression sweep: 188 backend tests (only the same pre-existing, unrelated replay failure); 238/238 frontend tests, zero new regressions.

## Lifecycle status

**MODEL 0, unchanged.** No invalidation/expiration/failure/non-execution/reason-code lifecycle, no memory weight/decay/reinforcement, no B4/Conflict history gating. `activation_modulation_applied` remains hardcoded `false`.

**Provider calls: 0. TradingAgents calls: 0.**
