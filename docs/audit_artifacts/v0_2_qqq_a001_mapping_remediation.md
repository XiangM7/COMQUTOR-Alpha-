# v0.2 QQQ A001 Mapping Remediation

**Step 7A: repair the production mapping defect behind the Formal-Gold blocking failure `QQQ-A001-RATE-CUT-CYCLE`.** Diagnose-and-fix, not retune. No Gold, Trigger Matrix, Final Acceptance, or Acceptance Adjudication file was touched. The historical frozen QQQ acceptance result remains **FAIL** — this remediation does not, and cannot, retroactively change what that already-completed run produced.

## Release-Blocking Defect

| Field | Value |
|---|---|
| Ticker | QQQ |
| Rule | `QQQ-A001-RATE-CUT-CYCLE` |
| Authoritative run | `f88c8956-cb62-48aa-9951-89f8e8a95f83` |
| Frozen trigger (Step 3) | ABSENT (STRONG contrary evidence) |
| Actual level (Step 4) | `active`, score 66.4226 |
| Step-4 result | **FAIL** |
| Step-5 root cause | `SYSTEM_ERROR` / `SEMANTIC_MAPPING_FALSE_POSITIVE` |
| Step-5 first incorrect stage | **MAPPING** |

Per Step 6's own explicit framing, this remains a **P0 release blocker** for this remediation task — the Step-6 "P0: none identified" statement applied only to prioritization *within* the historical 34+9 Evidence Review failure set, not to the current release-blocking defect.

## Root Cause

`matched_alpha` is produced under **Pure-LLM Alpha semantic authority** (`alpha_mapper.py::map_claim_to_alpha`): the LLM classifier (`week2_llm.py`'s `alpha_classifier`/`alpha_classifier_batch` prompts) is the *sole* source of `matched_alpha` — deterministic keyword/factor/direction scoring is diagnostic/counterfactual only and never gates or overrides the LLM's decision.

Two contributing factors were traced:

1. **Prompt design.** The `alpha_classifier` prompt instructs the LLM to select the Alpha whose thesis the evidence "most directly and substantively supports **or opposes**" — by design, evidence opposing an Alpha's thesis is a valid reason to select that Alpha, with direction/stance meant to be captured separately (`evidence_stance.py`, a shadow layer). The taxonomy context actually sent to the LLM (`_alpha_taxonomy_request_block`) is only `{alpha_id, alpha_name, definition=core_thesis}` — it does **not** include the taxonomy's own `invalidation_conditions` field (already defined for every Alpha, e.g. A001's own `[inflation reaccelerates, rates rise, Fed stays restrictive]`), so the LLM has no explicit contrastive signal for what would invalidate the thesis.
2. **Downstream amplification.** Activation Scorer v2's `evidence_quality` (weight 0.35) and `agent_independence` (weight 0.20) components are computed from matched-claim **volume** and distinct-agent **breadth**, with no net-directional weighting once a claim carries a given `matched_alpha`. A large, direction-mixed pool of topically-adjacent claims — many explicitly *opposing* the Alpha — is therefore sufficient on its own to push the Alpha to an official `active` level. (Documented previously in `v0_2_acceptance_adjudication.json` Case A.)

**A related, deterministic code-level defect was found but deliberately NOT changed in this task**: `alpha_mapper.py`'s `direction_score()` has an inverted branch (`if relation == "invalidation" and alpha_id in POSITIVE_ALPHA_IDS: return 1.0`) that treats explicit thesis-invalidation text as *maximal positive* direction alignment. Reproduced offline (`direction_score()` returns `1.0` for "93% probability of NO Fed rate cuts..." against A001). This feeds only the diagnostic/counterfactual deterministic layer, which never determines `matched_alpha` under Pure-LLM authority — it is not the mapping-path stage that produced this specific defect, and fixing it is out of this task's minimal-repair scope. Flagged for a possible separate follow-up, not implemented here.

**`evidence_stance.py` was investigated and ruled out** as the root cause for this specific defect: it is an explicitly-documented shadow layer that never feeds back into Alpha Mapper scoring or admission, and Step 6 independently found **0 overlap** between QQQ-A001 and the historical 34-row Alpha Match failure set. Stance behavior is left untouched, per this task's explicit scope.

## False-Positive Patterns

Clustering all 66 claims persisted as `matched_alpha="A001"` in the authoritative run by actual economic meaning:

| Cluster | Count | Corrected by this fix? |
|---|---:|---|
| Explicit "no cut" / rate-hike probability language (e.g. "72% probability of a Fed rate hike") | 30 | **Yes** |
| Hawkish repricing language | 5 | **Yes** |
| Rising-yields language | 1 | **Yes** |
| Generic rate-environment commentary with no explicit direction | 26 | No |
| Negated/conditional easing references (e.g. "reduces the case for Fed easing") | 4 | No |

**Total: 66.** The 30-claim "explicit no cut / hike probability" cluster is the single largest and most direct manifestation of the defect — the persisted corpus's own strongest evidence (93% no-cut probability, 72% hike probability) was, ironically, exactly what got pooled into A001's "supporting" evidence set.

## Production Change

A narrow, taxonomy-native, **general** (not QQQ- or run-ID-specific) deterministic veto: an Alpha can never be the final `matched_alpha` for a claim whose text explicitly asserts that Alpha's own core thesis is false, per that Alpha's own registered high-precision pattern.

**Files changed:**

| File | Change |
|---|---|
| `comqutor_alpha/structure_engine/claim_semantics.py` | Expanded `_RATE_CUT_INVALIDATION_PATTERN` (A001's existing, alpha-specific pattern) with real, persisted-evidence-driven phrasings: `rate hike(s)`, `hike odds`, `probability of a hike`, `odds of a hike`, `hawkish`, `rising yields`/`yields rising\|rose`. Added a new general, table-driven `ALPHA_SPECIFIC_INVALIDATION_PATTERNS` registry (`{"A001": _RATE_CUT_INVALIDATION_PATTERN}`) and `alpha_specific_invalidation_matched(text, alpha_id)` predicate — extensible to any future Alpha, never ticker- or run-ID-keyed. |
| `comqutor_alpha/structure_engine/alpha_mapper.py` | In `map_claim_to_alpha`, added the deterministic veto applied to the **final** `matched_alpha` (however produced): when `alpha_specific_invalidation_matched(text, matched_alpha)` is True, `matched_alpha`/`matched_alpha_name` reset to `None` and `match_status` to `"no_match"`, with a clear `reason` string. Added an additive-only diagnostic field `alpha_specific_invalidation_override` (bool). No existing field's meaning changed. |

This is a deliberate, documented, narrow exception to the "Pure-LLM Alpha semantic authority" invariant, scoped only to explicit taxonomy-native invalidation signals — it does not reintroduce deterministic scoring as a general fallback authority, and is a no-op for every Alpha without a registered pattern (today, every Alpha except A001).

**No ticker-specific hack. No run-ID hardcode. No Gold, Trigger Matrix, Acceptance, or Adjudication file touched.**

## Positive Controls

Genuine Rate Cut Cycle evidence must still map to A001 when the (unchanged) LLM selects it — verified via `_FakeLLMGateway` (no live Provider call):

- "The Fed cut rates by 25 basis points, beginning an easing cycle." → **A001** ✓
- "Falling discount rates are supporting long-duration growth equity valuations as the Fed's easing cycle continues." → **A001** ✓
- "Markets are pricing an ongoing rate-cut cycle as inflation cools and the Fed pivots dovish." → **A001** ✓
- "Lower rates are expected to support QQQ's long-duration growth holdings." → **A001** ✓

All 4 pass; `alpha_specific_invalidation_override` is `False` in every case.

## Negative Controls

Real false-positive classes drawn from the persisted QQQ evidence, verbatim or near-verbatim:

| Class | Example | Result |
|---|---|---|
| Explicit no-cut probability | "93% probability of NO Fed rate cuts in 2026" | **Vetoed → no_match** |
| Rate-hike probability | "72% probability of a Fed rate hike in 2026" | **Vetoed → no_match** |
| Rate-hike odds | "rate-hike odds past 60%, pressuring long-duration growth" | **Vetoed → no_match** |
| Hawkish repricing | "a distinctly hawkish repricing that pressures long-duration...names" | **Vetoed → no_match** |
| Rising yields | "rising yields directly pressure QQQ's long-duration...holdings" | **Vetoed → no_match** |
| Higher-for-longer | "The Fed is signaling rates will stay higher for longer." | **Vetoed → no_match** |

All 6 pass; `alpha_specific_invalidation_override` is `True` in every case.

## Boundary Controls

- **A003 (Liquidity Expansion)** evidence selected by the LLM maps normally to A003 — the veto is a no-op for A003 (no registered pattern). ✓
- **A501 (Recession Risk)** evidence selected by the LLM maps normally to A501 — no-op. ✓
- Recession-risk commentary containing **no** rate-cut/hike language does **not** get vetoed even if (hypothetically) selected as A001 — confirming the fix is scoped to explicit rate-direction contradiction, not a general macro-risk exclusion. ✓
- "Rates remain restrictive and the Fed remains restrictive on policy" → vetoed for A001, as required. ✓

All boundary tests pass — the A001/A003 and A001/A501 distinctions are preserved, and the veto does not overreach into an unintended general suppression rule.

**Collateral damage check**: representative A304 (valuation) and A601 (narrative) claims for unrelated tickers (NVDA) map normally, confirming the `claim_semantics.py` pattern expansion has no effect outside A001.

## Offline QQQ Replay

Reproduced entirely offline against the persisted `f88c8956-cb62-48aa-9951-89f8e8a95f83` claim text — no Provider call, no fresh run.

| Metric | Value |
|---|---:|
| `before_a001_mapped_count` | 66 |
| `after_a001_mapped_count` (would remain mapped, LLM decision held fixed) | 29 |
| Vetoed (corrected) | 37 |
| `before_supports_alpha_shadow_count` (Step-5 reference, not a target) | 13 |

No target count was set in advance, and none was optimized for. The 29 remaining claims lack the explicit hike/no-cut/hawkish/rising-yield phrasing this narrow, evidence-driven fix targets (see the "generic rate-environment" and "negated/conditional easing" clusters above) — closing that gap further would require either a broader (riskier) deterministic pattern or, more appropriately, the prompt/context enrichment idea noted above (using the taxonomy's own `invalidation_conditions`), which cannot be validated without a live LLM call and is explicitly out of scope for this task.

This replay answers "would this specific defect mechanism still let this claim stand as A001 today," not "what would a fresh LLM call now decide" — a genuine resolution requires the fresh QQQ validation run this task does not perform.

## Regression Results

| Suite | Result |
|---|---|
| Focused (`tests/test_qqq_a001_mapping_remediation.py`) | **20/20 passed** |
| Relevant Alpha Mapper subsystem (`test_alpha_mapper.py`, `test_alpha_mapper_llm_authority.py`, `test_alpha_mapper_nvda_real_report.py`, `test_ai_alpha_mapper_discrimination.py`) | **181/181 passed** |
| Broader `claim_semantics`-dependent subsystem (`test_activation_scorer.py`, `test_b5_conflict_radar_evidence_ui.py`, `test_conflict_detector.py`, `test_evidence_stance_classifier.py`, `test_evidence_eligibility_unification.py`, `test_evidence_integrity.py`, `test_msft_a304_negation_aware_extraction.py`) | **327/327 passed** |
| Full backend suite (`COMQUTOR_DATABASE_URL="" COMQUTOR_ENV="" pytest -m "not integration"`) | **4171 passed, 27 failed, 3 errors, 3 skipped, 47 deselected** (742.37s) |

**Every one of the 30 failures/errors was individually inspected — zero are new, unexplained regressions:**

- **25 confirmed pre-existing, unrelated to this task.** Traceback inspection showed 23 of these (`test_evidence_review_v2.py`'s 13 `test_case*` failures, `test_evidence_review_v2_directional_eligibility.py`'s `test_f`/`test_g`/`test_g`(eligibility) and its 3 setup `ERROR`s) all stem from `evidence_review_summary_v2.json` itself lacking keys (`raw_h5_metrics`, `directional_eligibility`) that these tests expect — a pre-existing JSON data/schema gap on disk, with zero code path through anything this task touched. `test_evidence_review_sample.py::test_60_sample_includes_conflict_and_activation_evidence` reads `used_in_activation` directly from a persisted historical `evidence_stance_audit.json` (not recomputed) — also structurally impossible to be caused by this change. `test_source_integrity.py`, both `test_w5_demo_seed.py` tests, and `test_j3_semantic_benchmark_j2_v0_2.py::test_e42_...` are the already-documented pre-existing failures from this repository's own prior-session memory. The one case with a real code path, `test_artifact_export_and_api.py::test_replay_conflict_does_not_get_run_id_mismatch`, was actively verified: re-running the identical NVDA replay (`e434f80b-...`) with `alpha_specific_invalidation_matched` monkey-patched to a permanent no-op (behaviorally identical to pre-Step-7A code) still produced `admitted_count=0` — proving this failure predates and is unrelated to this change (all 6 candidate conflict pairs showed `MISSING_LEFT_EVIDENCE`/`ZERO_EVIDENCE_STRENGTH`, a total evidence-computation gap in that replay path, not an A001-specific effect).
- **5 expected collateral**, all the same well-established, repeatedly-precedented `FROZEN_HASHES`/"production semantic files unchanged" pattern already documented in this repository's own history for any authorized `alpha_mapper.py` edit: `test_evidence_review_v2.py::test_case17[...alpha_mapper.py]`, `test_high_value_unclassified_recovery.py::test_case10_...`, `test_msft_a102_a304_taxonomy_adjudication.py::test_a6_...byte_identical`, `test_step10_final_e2e_qa.py::test_production_semantic_files_unchanged_during_step10`, `test_step11_provider_health_rerun.py::test_production_semantic_files_unchanged_during_step11`. Per established precedent: reported honestly, not silently fixed or re-pinned by this change's own author.
- **New, unexplained regressions: 0.**

## Scope Exclusions

Per Step 6/this task's explicit instruction, the following were **not** addressed here (separate future workstreams):

- `A201↔A304`/`A301`, `A103↔A304`, `A501↔A301`, `A101↔A103`/`A102` taxonomy-overlap confusion (Step 6's `TAXONOMY_OVERLAP` category, 12 rows) — unrelated to the A001 mapping path.
- `MENTION_VS_OPPOSITION_OVERCALL` stance-classifier miscalibration (Step 6, 5 rows) — not touched; no production provenance in this task's trace required a stance-code change for the A001 defect specifically.
- Broad LLM-prompt/taxonomy-context redesign (the `invalidation_conditions`-enrichment idea) — noted as a promising complementary improvement but deliberately not implemented, since its real effect cannot be verified without a live Provider call, which this task does not authorize.

## Next Validation Step

**The historical frozen QQQ acceptance result remains FAIL.** This code repair does not, and cannot, retroactively change what the already-completed authoritative run (`f88c8956-...`) actually produced — `v0_2_final_acceptance_table.json` and `v0_2_acceptance_adjudication.json` are unmodified and remain the frozen record of that outcome.

**A new, fresh QQQ validation run is required** (a separately authorized Step 7B or later task) before Gold v0.2 can be reevaluated for QQQ-A001. Only that fresh run — inspected under the same Step-4/Step-5 comparison discipline already established — can determine whether this fix resolves the release-blocking defect in practice.

---

**Production files changed: 2** (`claim_semantics.py`, `alpha_mapper.py`). **Test files added: 1**. **Provider calls: 0. TradingAgents calls: 0. Fresh ticker runs: 0. Gold changed: no. Trigger Matrix changed: no. Final Acceptance changed: no. Acceptance Adjudication changed: no. Commits: 0. Pushes: 0. Destructive git operations: 0.**

**STEP 7A ONLY. MAPPING DEFECT REPAIRED AND OFFLINE-TESTED. HISTORY NOT REWRITTEN. GOLD UNTOUCHED. NO LIVE RUN PERFORMED.**
