# Gold v0.2 — Formal-Gold Post-Fix Impact Analysis

**Step 7C: determine whether the Step-7A/7A.2 QQQ A001 remediation can materially affect the already-passing Formal Gold results for NVDA and SNDK.** Analysis-only — no Provider calls, no TradingAgents calls, no fresh ticker runs, no production/test changes.

## Executive Decision

**Revalidation scope: `QQQ_ONLY_REVALIDATION_SUFFICIENT`.**

Both NVDA and SNDK show **impact_level = NONE**, established through (1) static code tracing proving the patch is structurally A001-specific with zero fallthrough/redirect mechanism, and (2) empirical offline replay of the actual historical persisted claim-mapping data showing **zero** non-A001 claims affected in either ticker's corpus. **`release_closure_ready = YES`** (readiness only — full v0.2 release PASS is not declared here).

## Patch Scope

Two production files: `comqutor_alpha/structure_engine/claim_semantics.py`, `comqutor_alpha/structure_engine/alpha_mapper.py`. Intended target: **A001 (Rate Cut Cycle)** only.

**Call sites traced** (both inside `map_claim_to_alpha`, both keyed by `matched_alpha` — the already-finalized Alpha ID for a claim):

| Function | Registry | Behavior for any alpha_id ≠ `"A001"` |
|---|---|---|
| `alpha_specific_invalidation_matched(text, alpha_id)` | `ALPHA_SPECIFIC_INVALIDATION_PATTERNS = {"A001": ...}` | Returns `False` unconditionally — confirmed pure no-op |
| `alpha_positive_requirement_satisfied(text, alpha_id)` | `ALPHA_POSITIVE_REQUIREMENT_CLASSIFIERS = {"A001": ...}` | Returns `True` unconditionally — confirmed pure no-op |

**Fallthrough behavior traced directly in code**: when either gate rejects a claim, `status` resets to `"no_match"` and `matched_alpha`/`matched_alpha_name` reset to `None`. **No second-ranked candidate is selected, no fallback classifier runs, no top-k re-ranking occurs, and no other Alpha's candidate entry is touched.** `candidates`/`eligible_candidates`/`top`/`second`/ambiguity-detection are all computed via the deterministic `_candidate_score()` layer *before* either new gate runs and are never recomputed afterward.

**Graph-layer verification**: `graph_engine/graph_builder.py::_committed_alpha_ids_for_claim()` reads a single, exclusive `matched_alpha` per `claim_id`. When a claim's `matched_alpha` becomes `None`, the function returns `[]` for that claim — the edge is marked with a reason code (e.g. `NO_COMMITTED_ALPHA_MATCH`), **never silently re-attributed to a different Alpha.** A claim can only ever be committed to the one Alpha its own `matched_alpha` field names, so no other Alpha's `local_structure_support` can gain evidence from a rejected A001 claim.

**Conclusion**: rejecting an A001 match cannot redirect that claim's evidence into another Alpha, at either the Alpha Mapper layer or the graph-edge/local-structure-support layer. No shared tokenization, claim normalization, or evidence-qualification helper was modified — `git diff --stat` confirms changes confined to the two gate functions and their call sites.

## QQQ Post-Fix Status

Carried forward unchanged: **PASS** (run `f239a53f-4ebe-455c-bb76-5f5485903901`). Not reevaluated here.

**Diagnostic open item preserved**: actual main conflict `A301__A304`; `A601__A304` not admitted; conflict Gold diagnostic `REVIEW`. This does not block QQQ's PASS because QQQ's frozen Gold v0.2 contract has no blocking composite/conflict-family rule — remains an open, non-blocking diagnostic item.

## NVDA Impact Analysis

| Question | Finding |
|---|---|
| Historical status | PASS |
| Historical A001 state | `candidate`, score 38.8213 — **already non-detected** |
| A001 mapping changed offline? | Yes — all 36 historically-matched A001 claims are rejected by the new gates (25 by the negative pattern, 11 by the positive-requirement gate); **0 survivors** |
| Non-A001 mappings changed? | **No** — all 277 non-A001 matched claims (A601: 40, A101: 62, A301: 41, A304: 81, A103: 28, A501: 6, A003: 1, A201: 12, A102: 6) are empirically unaffected |
| Blocking Alpha state can change? | No — A101/A301/A304 evidence pools are byte-identical to the historical run |
| Main conflict can change? | No — `A101__A304` admissibility depends only on A101's and A304's own fact groups, neither touched |
| Impact level | **NONE** |
| Fresh rerun required? | **NO_RERUN_REQUIRED** |

A001 was already non-detected in the historical run (well below the ~50-point activation threshold even with all 36 claims); removing those claims offline changes nothing about that outcome.

## SNDK Impact Analysis

| Question | Finding |
|---|---|
| Historical status | PASS |
| Historical A001 state | `candidate`, score 26.5915 — **already non-detected** |
| A001 mapping changed offline? | Yes — all 38 historically-matched A001 claims are rejected by the new gates (24 by the negative pattern, 14 by the positive-requirement gate); **0 survivors** |
| Non-A001 mappings changed? | **No** — all 375 non-A001 matched claims (A601: 76, A304: 55, A003: 2, A201: 160, A103: 22, A501: 12, A301: 39, A101: 9) are empirically unaffected |
| A201 blocking state can change? | No — A201's evidence pool (160 matched claims) is byte-identical to the historical run |
| A101/A102 negative controls can change? | No — 9 (A101) and 6 (A102) matched claims respectively are both empirically unaffected |
| Impact level | **NONE** |
| Fresh rerun required? | **NO_RERUN_REQUIRED** |

## Top-K / Fallback Analysis

Directly answered in the Patch Scope section above: rejecting a claim's A001 match produces `matched_alpha=None` with **no** redirect to a second-ranked candidate, no top-k re-ranking, and no other Alpha ever receiving that claim's evidence. Quantified for both tickers: 0/277 (NVDA) and 0/375 (SNDK) non-A001 claims show any behavioral difference under the new gates.

## Graph / Conflict Impact

Conflict admissibility (`conflict_admissibility.py`) computes `bull_score`/`bear_score` for a given pair from *only* that pair's own two Alphas' evidence fact groups. A001 never participates as a pair member in NVDA's `A101__A304` conflict or in any SNDK conflict pair. Combined with the empirical finding that zero A101/A301/A304 (NVDA) and zero A101/A102/A201 (SNDK) claims are affected, both tickers' conflict/negative-control inputs are proven unchanged.

## Known Test-Infrastructure Debt

The Step-7A.2 finding (39 new backend test *errors*, root-caused to `tests/replay/conftest.py`'s synthetic mock canned-selecting the alphabetically-first taxonomy Alpha for a fixed, non-rate-related synthetic claim) is **not material to this impact analysis**. That fixture issue is confined to a single, synthetic pytest mock that never touches real persisted production data. This analysis instead replays the *actual*, persisted historical `alpha_matches.json` records from the real NVDA/SNDK production runs — a completely independent data source and code path. The fixture issue does not reduce confidence in, or otherwise bear on, the findings above, and does not prevent reliable offline replay.

## Revalidation Scope

**`QQQ_ONLY_REVALIDATION_SUFFICIENT`.**

Both NVDA and SNDK show `impact_level = NONE`, established through static code tracing (structural A001-specificity, zero fallthrough) and empirical offline replay (zero non-A001 claims affected in either corpus, A001 already non-detected in both historical runs and remaining non-detected post-fix). No credible causal path from the patch to either ticker's blocking Formal Gold outcome exists. QQQ has already been independently, freshly revalidated and shown PASS. No further reruns are required before full v0.2 release closure evaluation.

## Release-Closure Readiness

**`release_closure_ready: YES`** — reporting readiness only. This task does **not** declare full v0.2 release PASS.

**Next step: STEP 8 — Final v0.2 Acceptance Closure**, a separate, subsequent task.

---

**Gold changed: no. Historical Trigger Matrix changed: no. Historical Acceptance changed: no. Post-fix QQQ Acceptance changed: no. Production files changed: 0. Test files changed: 0. Provider calls: 0. TradingAgents calls: 0. Fresh ticker runs: 0. Commits: 0. Pushes: 0. Destructive git operations: 0.**

**STEP 7C ONLY. NVDA/SNDK IMPACT = NONE. NO RERUN REQUIRED. QQQ-ONLY REVALIDATION SUFFICIENT. FULL RELEASE NOT DECLARED.**
