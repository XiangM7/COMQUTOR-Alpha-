# B4 Activation Level Alignment — Implementation and Validation Report

Status: **B4 IMPLEMENTATION COMPLETE.** `HEAD` re-verified below. No
commit, no push. Every numeric threshold, decision tree, canonical reason
set, and UI partition rule this task requires (Decisions 1–3, section 4's
threshold table, section 7's Case A–D tree, section 9's four canonical
reasons) was supplied verbatim and pre-approved by the task specification
itself — this report certifies that specification was implemented and
verified correctly. It is not, and does not claim to be, independent
Product Owner acceptance (there is no analogous "John's seed values"
external judgment call here to sign off on).

## 1. Preserved state

`git branch --show-current` → `comqutor-structure-layer`. `git rev-parse
HEAD` → `b5837e80a4550fc35165d0013a8ef0f27ccb4c8f` — unchanged before and
after this task, re-verified at report-writing time. No
`reset`/`restore`/`checkout`/`clean`/`stash` run at any point. `PROVIDER_CALLS=0`
and `SUBAGENTS=0` held throughout every test run and verification script.
No commit, no push.

## 2. The core problem this task fixes

Before this task, `status`/level classification was written independently
in **two places**: `activation_scorer_v2.score_alpha_v2` wrote an initial
status via its own (boundary-buggy) band function, and
`exposure_engine.compute_run_entity_alpha_exposures` then independently
overwrote it via `_cap_status` when Exposure was enforced. Nothing
resolved Evidence/Graph qualification, the regime gate, and B3 Exposure
qualification into one final, auditable decision — a downstream reader
had no single place to trust for "what level is this alpha actually at,
and why."

`comqutor_alpha/graph_engine/alpha_level_classifier.py` is the fix: one
new module, two public entry points
(`classify_alpha_level`/`classify_and_rebuild_collections`), called
exactly once in the real pipeline, after every qualification input
(Activation v2's own score/caps/regime gate, and B3 Exposure's per-alpha
record) is already available. It **never recomputes** any of those
inputs — it only arbitrates between them per John's exact Case A–D
decision tree.

## 3. Existing implementation reused vs. what had to change

Confirmed by direct code reading before any edit:

1. **Activation v2's 5 dominant-qualification caps unchanged**:
   `_apply_caps`'s `CAP_INSUFFICIENT_UNIQUE_EVIDENCE`/
   `CAP_INSUFFICIENT_AGENT_INDEPENDENCE`/`CAP_NO_TICKER_SPECIFIC_EVIDENCE`/
   `CAP_NO_LOCAL_STRUCTURE_SUPPORT`/`CAP_KEYWORD_ONLY_SUPPORT` and their
   `cap_reason_codes` output are consumed exactly as computed — B4 checks
   only whether the list is empty, never re-derives the underlying
   evidence/graph conditions.
2. **Activation v2's regime gate unchanged**: `_evaluate_regime_gate`'s 7
   frozen gates (already using the correct `REGIME_GATE_MIN_SCORE=86.0`)
   are consumed via `regime_gate_passed`/`regime_gate_failures` exactly as
   computed.
3. **B3 Exposure's qualification signals unchanged**: `would_block_dominant`/
   `would_block_regime_level`/`exposure_status`/`effective_status`/
   `reason_codes` (all computed by `exposure_engine.py`, untouched) are
   consumed as one input among several — B4 never recomputes exposure
   itself.
4. **Evidence Fact Index untouched.**

**What genuinely had to change**: the *act* of writing `status` and
rebuilding `dominant_alphas` had to move out of `exposure_engine.py` and
into the new classifier, called once, later in the pipeline, after both
Activation v2 scoring and B3 Exposure evaluation have run.

## 4. `exposure_engine.py`: removed, not replaced

Removed: the 3 `entry["status"] = _cap_status(...)` call sites inside the
`effective_mode == "enforced"` branch, and the
`activation["dominant_alphas"] = dominant` rebuild block under the same
condition. The now-dead `_cap_status`/`_LEVEL_RANK` helpers were deleted
(confirmed via repo-wide grep — no remaining references anywhere in
`comqutor_alpha/`). `would_block_dominant`/`would_block_regime_level`/
`qualification_effect_applied`/`exposure_status`/`reason_codes` are
**still computed and still attached** to each alpha's `entity_exposure`
record exactly as before — these become B4's qualification *input*
rather than something Exposure applies itself. A comment block at the old
call sites explains the new architecture for any future reader.

## 5. Threshold boundary results (task section 4/16.A)

| Threshold | Value | Comparison |
|---|---|---|
| `ACTIVE_THRESHOLD` | 50.0 | `score >= 50.0` |
| `DOMINANT_THRESHOLD` | 70.0 | `score >= 70.0` |
| `REGIME_LEVEL_THRESHOLD` | 86.0 | `score >= 86.0` |

Half-open lower-bound comparisons only (`>=`) — never `<=`/`>`, the exact
class of boundary bug this task exists to eliminate. Verified exactly:

| Score | Level |
|---|---|
| 49.999 | candidate |
| 50.000 | active |
| 69.999 | active |
| 70.000 | dominant |
| 85.999 | dominant |
| 86.000 | regime_level |

Type/range rejection verified for: NaN, `+Infinity`, `-Infinity`, `bool`
(`True`/`False` — Python's `bool` is an `int` subclass, checked first and
rejected explicitly), string, `None`/missing, and out-of-`[0,100]`-range
values. None are ever silently clamped or guessed — every one raises
`AlphaLevelInputError`.

**Pre-existing boundary bug found, deliberately not touched at its
source**: `activation_scorer_v2.py`'s own `activation_status_band_v2`
uses inclusive `<=` at 30/50/70/85, and its 85.0 cutoff doesn't even
match `REGIME_GATE_MIN_SCORE=86.0`. B4's `level_for_score` never consults
this function at all, so it cannot propagate this bug into any final B4
result. Case analysis (the `_apply_caps` cap floor of 60.0, and the
invariant `activation_score == uncapped_score` whenever no cap actually
triggers) proves this pre-existing inconsistency can, at most, produce an
*incomplete diagnostic list* for an alpha that is already blocked for
other reasons — never an incorrect final classification. Left untouched
per the task's own instruction to fix only genuinely-found real
differences, minimizing scope and risk.

## 6. Qualification contract (task section 6/7)

`target_level = level_for_score(uncapped_score if uncapped_score is not
None else activation_score)` — what the evidence alone supports, ignoring
every qualification gate. `qualified_level` is the actual final level
after arbitration:

- **Case A/B** (`target_level` is `candidate`/`active`): passes through
  with **no additional gate** — verified via a dedicated test
  (`test_b_candidate_and_active_never_gain_a_new_evidence_graph_or_exposure_gate`)
  that even a synthetic alpha carrying every possible failing signal
  (dominant cap failure, regime gate failure, approved_gating Exposure
  block) still reaches its full target level at candidate/active.
- **Case C** (`target_level == dominant`): qualifies iff
  `dominant_cap_reason_codes` is empty AND Exposure (if `approved_gating`)
  doesn't block dominant; otherwise falls back to `active`,
  `blocked_from=(dominant,)`.
- **Case D** (`target_level == regime_level`): qualifies iff the regime
  gate passed AND Exposure doesn't block regime; else falls back to
  `dominant` if dominant qualification alone still holds
  (`blocked_from=(regime_level,)`); else falls back to `active` if *both*
  fail (`blocked_from=(dominant, regime_level)` — **always** in that
  order, verified by a dedicated test that the classifier never skips
  dominant to jump straight from a regime failure to active).

B4 **never modifies** `activation_score` or `uncapped_score` — verified
directly (`test_h_classification_never_mutates_any_field_it_does_not_own`)
and against the real saved run (section 10 below).

## 7. B3 Entity Exposure interaction (task section 8)

Only consulted when `entity_exposure.effective_status == "approved_gating"`.
`draft_shadow`/`disabled`/an absent Exposure record **never** block,
regardless of what `would_block_dominant`/`would_block_regime_level`
literally say (B3 computes those observationally in every mode). A
missing approved seed entry (`exposure_status == "missing_seed"`) fails
closed for **both** dominant and regime — even though
`would_block_dominant`/`would_block_regime_level` are individually
`False` for a `None` `final_exposure` (computed as `final_exposure is not
None and final_exposure < threshold`) — "missing" is never read as
"computed and merely low." All 5 states tested directly against the
classifier (`draft_shadow` never blocks, `disabled` never blocks, absent
record never blocks, `approved_gating` actually blocks, missing-seed
fails closed for both levels).

## 8. Canonical reason mapping (task section 9)

Four canonical, deterministic, natural-language-free reasons —
`NO_LOCAL_STRUCTURE_SUPPORT`, `INSUFFICIENT_EVIDENCE`,
`LOW_ENTITY_EXPOSURE`, `NO_TICKER_SPECIFIC_EVIDENCE` — mapped from every
existing, unmodified diagnostic code `_apply_caps`/`_evaluate_regime_gate`/
`exposure_engine.py` already produce. `SCORE_BELOW_REGIME_THRESHOLD` and
`EVIDENCE_INTEGRITY_WARNING` are deliberately left unmapped (no clean
match among the four) — they surface in `diagnostic_reason_codes` only,
never in `blocked_reason_codes`, never inventing a fifth canonical
reason. Duplicate raw codes that map to the same canonical reason (e.g.
`INSUFFICIENT_UNIQUE_EVIDENCE` and `KEYWORD_ONLY_SUPPORT`, both
→ `INSUFFICIENT_EVIDENCE`) collapse to one entry, stably ordered.
`diagnostic_reason_codes` (raw, unmapped) is always preserved in full for
audit, separately from the canonical `blocked_reason_codes`.

## 9. Collection consistency and the five-way UI partition (task sections 11/12)

`dominant_alphas` keeps its **exact pre-existing meaning** (dominant OR
regime_level) — an A2-frozen field, never redefined, kept for backward
compatibility. Four new, additive, sibling top-level fields —
`active_alphas`/`regime_level_alphas`/`candidate_alphas`/`blocked_alphas`
— are rebuilt exactly once by `classify_and_rebuild_collections`, split
by the single true `qualified_level`/`is_blocked` it just computed. These
backend collections may legitimately overlap (`blocked_alphas` shares
members with whichever `qualified_level` bucket a blocked alpha landed
in) — backend qualified *counts* stay accurate independent of any UI
partitioning choice.

The frontend's five-way **mutually exclusive** partition (Decision 2) is
a presentation-only concern, computed separately in
`StructureGraphPage.tsx` via one pass over the full per-alpha activation
list using exactly this priority order — `is_blocked` (wins first) →
`qualified_level==regime_level` → `dominant` → `active` → else
`candidate` — reading `is_blocked`/`qualified_level` directly, never
recomputing them, and falling back to the legacy `status` field only for
a historical payload with no `qualified_level` at all (clearly labeled
"Legacy classification"). Verified exclusive by a dedicated synthetic
test (`test_f_collections_partition_correctly_and_dominant_alphas_keeps_backward_compat_meaning`)
and a frontend rendering test
(`StructureGraphPage.test.tsx`'s five-way-partition describe block).

## 10. B2 Conflict Core compatibility (task section — must-not-touch list)

Not modified: `supports_alpha` definition, Evidence Fact dedup, bull/bear
evidence counts, ticker-specific admissibility, B2's own 50-point
threshold, `ConflictScore` formula, declared pairs, main-conflict
arbitration. Verified directly (`test_h_classification_never_mutates_any_field_it_does_not_own`)
that `classify_and_rebuild_collections` leaves every field it doesn't own
byte-identical on a synthetic entry, and against the real saved run
(section 11).

**One observed, root-caused, non-breaking change**: `conflict_schema.
ADMISSIBLE_STATUSES` gained `"candidate"` additively (`"watch"` kept, for
v1/historical-payload compatibility). Reasoning: B2's own independent
`score >= 50` admissibility check is strictly *stronger* than the old
status-based floor, so this can only ever change *which gate names the
rejection* for an already-doomed-to-fail pair, never the admission
outcome itself. Observed exactly this in
`test_week4_golden_closure.py`'s QQQ fixture: two thin, weak pairs
(previously classified `inactive` under the old boundary-buggy v2 band,
now correctly `candidate` under B4) no longer trip the early, terse
`BELOW_ACTIVATION_THRESHOLD` gate — they instead reach B2's own richer
per-side check and are rejected there with more specific reasons
(`BULL_SCORE_BELOW_THRESHOLD`/`INSUFFICIENT_BULL_SUPPORTING_EVIDENCE`
plus `BEAR_SCORE_BELOW_THRESHOLD`). The outcome (`suppressed`) is
unchanged; the test was updated to assert the new, more informative
reason codes, with a comment explaining exactly why. `graph_schema.
VALID_ACTIVATION_STATUSES` received the same additive fix, confirmed via
repo-wide grep to be genuinely dead/unused code — hygiene only,
non-blocking.

## 11. Real saved run verification — NVDA `e3eb3909-3744-4a02-9b32-b225cf6ef665`

**Primary method (zero confound)**: `classify_and_rebuild_collections`
applied directly to the real, unmodified saved `activation_versions.v2`
payload. `activation_score`/`uncapped_score` are the true, unmodified
production numbers throughout — no replay, no re-derivation.

| Alpha | activation_score | uncapped_score | target_level | qualified_level | is_blocked | blocked_from |
|---|---|---|---|---|---|---|
| A301 | 84.5319 (unchanged) | 84.5319 (unchanged) | dominant | dominant | False | [] |
| A101 | 63.1069 (unchanged) | 63.1069 (unchanged) | active | active | False | [] |
| A304 | 61.2757 (unchanged) | 61.2757 (unchanged) | active | active | False | [] |

Every field outside B4's own 8 owned fields (`status`/`target_level`/
`qualified_level`/`is_blocked`/`blocked_from`/`blocked_reason_codes`/
`diagnostic_reason_codes`/`classification_version`) is **byte-identical**
before vs. after, across all 10 scored alphas — confirmed programmatically,
not sampled.

Resulting collections: `dominant_alphas=[A301]`,
`active_alphas=[A001,A101,A103,A304]`, `regime_level_alphas=[]`,
`candidate_alphas=[A003,A102,A201,A501,A601]`, `blocked_alphas=[]`.

None of the 10 real alphas happen to land exactly on a 50.000/70.000/86.000
boundary — honestly reported rather than fabricated; exhaustive exact-
boundary correctness is separately covered by the new test file's
synthetic Section A.

**B2 conflict pair verification**: `detect_alpha_conflicts` run against
the B4-classified payload (still the real, unmodified `activation_score`)
and the run's real `alpha_matches.json`, compared field-by-field against
the originally-persisted `conflicts.json`:

| Pair | conflict_score | conflict_level | main_conflict | Identical before/after |
|---|---|---|---|---|
| A301__A304 | 32.0131 | medium | **True** | **Yes** |
| A101__A304 | 30.1956 | medium | False | **Yes** |

`conflicts` count (2) and admitted IDs are identical before/after.

**Supplementary check (raw-rebuild replay)**: additionally ran the
Provider-zero raw-rebuild diagnostic replay
(`comqutor_alpha.replay.pipeline.run_structure_replay`) for a full
structured→matches→graph→conflicts end-to-end pass. `0` provider calls,
`0` TradingAgents calls, `0` market-data calls, `0` database writes,
source raw artifact hash unchanged before/after, claim/factor/edge counts
identical. **One confound found and root-caused**: every alpha's
`activation_score` shifted uniformly by exactly `-5.0` under this replay
mode. Root cause: `run_structure_replay` does not pass the original run's
`run_timestamp`/`as_of` through, so `activation_scorer_v2.
_recency_component` falls back to `RECENCY_FALLBACK_SCORE=50.0`
(contribution 5.0 at the recency component's 0.10 weight) instead of the
original run's genuinely-fresh `age_days=0` (contribution 10.0) — a
pre-existing characteristic of the replay tool itself, not modified by B4
or anything in this session. Despite this unrelated confound, the
qualitative conflict admission outcome (both pairs admitted, A301__A304
still main_conflict) held steady — reinforcing, not undermining, the
primary zero-confound verification above.

**Live end-to-end check**: run `e3eb3909...` itself has zero DB rows (a
pre-existing, already-documented, out-of-scope gap from the B2 diagnostic
task). To confirm the full pipeline → DB persistence → Research API read
path (`get_persisted_structure_graph`) genuinely carries B4 fields
end-to-end, ran a fresh offline NVDA request (w5 demo fixtures, 0
provider calls) through a real in-memory SQLite DB: POST `status:
completed`, GET graph `status: ok`, every alpha carries
`target_level`/`qualified_level`, `status` always equals `qualified_level`,
and all five collections are present as top-level fields in the API
response — closing the loop on the `get_persisted_structure_graph` bug
fix (section 13) against a real persisted DB row, not only an in-memory
payload.

## 12. Frontend

`frontend/src/api/types.ts`: `"candidate"` added to `ACTIVATION_STATUSES`
(legacy `"inactive"`/`"watch"` kept for historical-payload narrowing,
never produced by a new B4 run); new `CANONICAL_ALPHA_LEVELS`/
`CANONICAL_BLOCKED_REASONS` exported as the single source of truth (never
hardcoded a second time elsewhere); `DominantAlpha` and `AlphaActivation`
both gained the 7 new optional B4 fields (optional only because a
historical payload never carried them — a current backend response always
includes all 7 together); `StructureGraphResponse` gained the 4 new
optional collections.

`AlphaCard.tsx`: renders `target_level` (only when it differs from
`qualified_level`), a `Blocked` row (`blocked_from` + canonical reason
via friendly-text lookup + a collapsible `<details>` for the full raw
`diagnostic_reason_codes`) when `is_blocked`, and a "Legacy classification"
fallback row when `qualified_level`/`target_level` are both absent. Never
recomputes a level from `activation_score`, never re-derives qualification
from reason codes, never hardcodes 50/70/86.

`StructureGraphPage.tsx`: the single "Dominant alphas" panel is replaced
by five sections (Active/Dominant/Regime-level/Candidate/Blocked),
partitioned by one pass over the full per-alpha list using the exact
priority order from Decision 2 (never recomputed from score). The
overview `<dl>` keeps its existing "Dominant alphas" count reading the
backward-compatible `dominant_alphas` collection — relabeled "Dominant or
regime-level alphas" to avoid ambiguity with the new, stricter "Dominant
alphas" section below — and gains four new counts sourced from the same
partition used for the sections themselves, so the numbers can never
drift apart. A page-level "Legacy classification" note renders when every
scored alpha in the run predates `qualified_level` entirely.

## 13. Backend consumers updated (additive only)

- `week4_persistence.py`'s `_whitelist_activation`: the 7 new fields
  added to `_V2_ONLY_ACTIVATION_FIELDS` (a v1 entry smuggling any of them
  is rejected, matching the existing pattern for every other v2-only
  field) and whitelisted with the same `if field in entry:` pattern
  already used for `uncapped_score`/`eligible_cap` — an old, pre-B4 v2
  row round-trips unchanged, never fabricating the new fields.
- `routes_research.py`: `_ACTIVATION_STATUS_KEYS`/`_activation_summary_section`
  gained `candidate_count`; the main `run_audit.json` payload gained
  additive `candidate_alpha_count`/`blocked_alpha_count` (computed from
  `status`/`is_blocked` directly, never re-derived); the already-correct,
  already-A2-frozen `active_alpha_count`/`dominant_alpha_count`/
  `regime_level_alpha_count` fields were **not** touched (they already
  read `status` and require no change).
- `entity_exposure_audit`: `qualification_effect_applied`'s meaning
  drifted (it no longer directly implies a status mutation happened,
  since B4 — not Exposure — is now the sole decider). Documented in-place
  with an explicit comment, and closed the gap with a new
  `exposure_actually_blocked_alpha_count` field, sourced from B4's own
  `is_blocked`/`blocked_reason_codes` output (the actually-accurate
  post-B4 answer to "did Exposure really change an outcome").
- **Real bug found and fixed**: `routes_research.py`'s
  `get_persisted_structure_graph` builds an explicit, narrow
  reconstruction dict (not a spread of `graph_json`) — the four new
  collections were correct in the persisted file/DB row but silently
  dropped by this one read-path function. Fixed additively, matching the
  existing `dominant_alphas` pattern exactly. Confirmed fixed via the
  live end-to-end check in section 11.

## 14. Test results

- **New dedicated test file** `tests/test_b4_activation_level_alignment.py`
  (sections A–H, 54 tests): **54/54 passed.**
- **Targeted regression** (15 files spanning Activation v2, Exposure, B3,
  Conflict Detector, persistence, NVDA/QQQ sanity, golden closure, run
  audit, structure correctness, artifact export): **443/443 passed.**
- **Full repository regression**: **3321 passed, 3 failed, 47 skipped, 69
  subtests passed**, 548.45s (0:09:08). All 3 failures verbatim-match the
  already-documented, already-investigated pre-existing/unrelated
  failures recorded in this session's own B3 report (written before any
  B4 edit began): `test_source_integrity.py::
  test_current_semantic_components_match_approved_phase1_master_baseline`
  (pre-existing, unrelated); `test_w5_demo_seed.py::
  test_seed_is_complete_idempotent_and_reusable_without_provider` and
  `test_w5_demo_seed.py::test_only_nvda_and_qqq_are_seeded` (both left
  failing by prior explicit user decision, unrelated to B3 or B4). **Zero
  new B4-caused failures.**
- **Frontend**: **165/165 passed** (17 files; 159 pre-B4 baseline + 6 new
  — 4 in `AlphaCard.test.tsx` covering blocked display/legacy fallback,
  2 in `StructureGraphPage.test.tsx` covering the five-way partition and
  its legacy-payload fallback). `npx tsc --noEmit` clean. `npm run build`
  clean.
- **Ruff**: clean on all 13 touched/new backend and test files. 13
  pre-existing findings remain in 6 unrelated, untouched files elsewhere
  in the repo (alpha_library/routes_alpha_library/adapters/
  research_profiles/structure_engine and their tests) — out of scope, not
  modified.
- **Real bugs found and fixed during this task**: (1) the
  `get_persisted_structure_graph` API read-path bug (section 13); (2) an
  unused local variable and an unsorted import, both caught by Ruff and
  fixed.

## 15. Not touched (explicit non-goals confirmed)

B5, A3, A4, J3 human review, cold-start history fix, repository cleanup,
old artifact deletion, B1 semantic canary, "John-20" gold audit. Alpha
taxonomy, Exposure seed values/formula, Activation Score weights, B2
thresholds/`ConflictScore`, Evidence stance ontology, `Week2LLMGateway`,
Evidence Fact deduplication — none modified.

## 16. Files changed

**Created**: `comqutor_alpha/graph_engine/alpha_level_classifier.py`,
`tests/test_b4_activation_level_alignment.py`,
`docs/audit_artifacts/b4_activation_level_alignment_report.md`,
`docs/audit_artifacts/b4_activation_level_alignment_report.json`.

**Modified**: `comqutor_alpha/exposure_engine.py`,
`comqutor_alpha/graph_engine/pipeline.py`,
`comqutor_alpha/conflict_engine/conflict_schema.py`,
`comqutor_alpha/graph_engine/graph_schema.py`,
`comqutor_alpha/storage/db/week4_persistence.py`,
`comqutor_alpha/api/routes_research.py`,
`tests/test_entity_alpha_exposure_productization.py`,
`tests/test_week4_golden_closure.py`,
`frontend/src/api/types.ts`, `frontend/src/components/AlphaCard.tsx`,
`frontend/src/components/AlphaCard.test.tsx`,
`frontend/src/pages/StructureGraphPage.tsx`,
`frontend/src/pages/StructureGraphPage.test.tsx`.

## 17. Summary

`head`: `b5837e80a4550fc35165d0013a8ef0f27ccb4c8f`. `branch`:
`comqutor-structure-layer`. `commit`: NO. `push`: NO. `PROVIDER_CALLS`: 0
throughout.

**B4 IMPLEMENTATION COMPLETE** — one single, authoritative classifier now
resolves Activation v2 scoring, Evidence/Graph qualification, the regime
gate, and B3 Exposure qualification into the final `target_level`/
`qualified_level`/`is_blocked`/`blocked_from`/`blocked_reason_codes`
contract, wired through the real pipeline, persistence, API, and frontend,
with zero regressions in B2's own conflict-detection behavior — verified
directly against real saved production data, not only synthetic fixtures.
