# Alpha Memory — Step 3: Historical Observation + Recurrence

SHADOW ONLY, descriptive only. **Provider calls: 0. TradingAgents calls: 0. No fresh research. No commit, no push.**

## Recurrence definition

`is_recurring = prior_observation_count >= 1` — exact atomic φ_id equality against at least one prior, history-eligible run. No fuzzy/semantic/edge-type/Alpha equivalence. No recurrence strength, confidence, weight, streak, or decay exists anywhere in this step.

## Historical-run eligibility

Excludes the current run; requires same ticker; requires derivable structure-graph data; taxonomy/version compatibility is enforced structurally by the φ_id hash itself. **New**: a run whose own `artifact_manifest.json` explicitly says `artifact_completeness != "pass"` is excluded — reusing the one existing authoritative per-run signal, never inventing a new "healthy run" standard. A run with no manifest at all is *not* excluded on that basis alone.

**Honest limitation reported**: this doesn't catch every bad run. NVDA run `40bd7e3d` ran with Week2 LLM disabled (zero committed Alpha matches, zero Activation) yet its manifest says "pass" — no existing field distinguishes "complete but semantically empty" from "complete and meaningful." That specific case is instead caught incidentally: it has 7 edges, zero with any `alpha_ids`, so it contributes zero phi and can never produce a false match. A real gap, not smoothed over.

## Deduplication

`(run_id, phi_id)` deduplicated explicitly before counting — `prior_observation_count` is the number of distinct prior runs, never a count of duplicate edge rows. Belt-and-suspenders on top of Step 2's own within-run dedup.

## Alpha-level recurrence summary

`alpha_id, current_phi_count, first_seen_phi_count, recurring_phi_count, recurrence_ratio, prior_observation_total` (plus Step 2's field names retained as exact aliases). No `score`/`weight`/`confidence` key exists; never imported by B1/B2/B4/Conflict modules.

## Real NVDA result

Current run `2f8ee897`, scanned against its full eligible history: **15 current φ, 6 recurring, 9 first-seen, 13 total prior observations.** Confirms Step 2's two matches (A101, A102 vs `c9abf687`) as genuine recurring structures with real source run IDs, plus additional matches against `a8d47429`, `e3eb3909`, `948be419`, `5ffe121a`.

## Real MSFT result

Current run `6cd2566d`: **0 recurring** of 12 current φ, even scanning the full eligible MSFT history — not manufactured. Same root cause as before (the paired prior run has almost no alpha-linked edges, and no other eligible MSFT run happens to share an exact edge).

## Atomic recurrence with differing aggregate fingerprint

**Yes, occurred and confirmed on real data.** NVDA's A101/A102/A103 each show at least one atomic edge recurring against prior run `a8d47429` while their whole-Alpha aggregate fingerprint does *not* match it — exactly the useful "some structures recur while the overall Alpha changed" result, reported purely descriptively, never called drift or invalidation.

## Instability signals cannot create/remove recurrence

Verified by dedicated tests — the variance diagnostics remain pure and read-only, never called by the identity/matching functions.

## API / UI

**API**: no new route. `alpha_memory` (with all Step 3 fields) continues through the existing internal `run_audit.json` path — which has no public GET route by original design. **UI**: deferred — no frontend code reads `run_audit.json` today, so there's no minimal-change surface to extend; building one would mean inventing new product design, reserved for a dedicated later step.

## Files changed

`comqutor_alpha/memory/history_reader.py` rewritten (eligibility filter, dedup, extended history/summary fields); `phi_identity.py` and `routes_research.py` untouched this step (the identity model is frozen, and the wiring already calls through). Test file rewritten (28 tests, was 13); `test_run_audit_v2.py` +1 assertion update. Both real NVDA `run_audit.json` files regenerated offline at zero cost.

## DB migration: NO.

## Proof B1/B2/B4/Conflict unchanged

AST-verified no import by B1/B2/B4/Conflict modules; the Step 2 integration test (unmodified) still proves official sections stay byte-identical. Full 14-file sweep: 446 passed, only the same 13 pre-existing `evidence_review_v2.json` failures remain.

## Remaining lifecycle Product decisions

All prior open items from Steps 1/1.5/1.6/2; whether/how absence should ever become meaningful (deliberately deferred here); invalidation/expiration/failure/non-execution operational definitions; whether the aggregate-vs-atomic drift observation should become a formal diagnostic category; timing/scope of a dedicated Alpha Memory UI step.

**Provider calls: 0. TradingAgents calls: 0.**
