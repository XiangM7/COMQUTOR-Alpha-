# v0.2 QQQ A001 Positive-Requirement Remediation

**Step 7A.2: fix the second proven layer of the QQQ A001 semantic-mapping defect.** Complementary to, not a replacement for, the Step-7A negative veto. Offline only — no live QQQ run, no Provider call.

## Problem

Step 7A's negative invalidation veto reduced the historical QQQ run's A001 mappings from 66 to 29. The independent Step-7A.1 residual audit then found that **0 of those 29** were genuine positive A001 evidence: 19 were explicit opposition/invalidation, 8 were generic non-directional rate commentary, 1 was a conditional mention-only hedge, and 1 was genuinely mixed. This proved a systematic gap a pure negative blocklist cannot close: content that never asserts A001's thesis is false (so the veto never fires) but also never asserts the thesis is true.

## Independent Residual Audit Authority

`docs/audit_artifacts/v0_2_qqq_a001_residual_mapping_audit.json` (verified unchanged, SHA256 `f8d6b59e...`) is treated as diagnostic ground truth for this task: its 29 row-level labels are the regression set this remediation must correctly reject, without hard-coding any specific sample ID — the general semantic rule alone must produce the rejection.

## Positive A001 Semantic Requirement

A new `classify_a001_directional_semantics()` classifies claim text into exactly one of five directional classes; **only `POSITIVE_EASING` satisfies the gate**:

| Class | Meaning |
|---|---|
| `POSITIVE_EASING` | Affirmative, non-hedged, non-negated easing (actual cuts, an easing cycle, falling/lower rates, or a confident, non-hedged expectation of cuts) |
| `NEGATIVE_OR_HAWKISH` | Opposes/invalidates the easing thesis (no cuts, hikes, hawkish repricing, rising yields, cuts delayed/less likely, tightening, etc.) |
| `CONDITIONAL_OR_UNCERTAIN` | Hedged/modal speculation ("could," "may," "if," "unless") or mention-only "whether a cut will happen" framing |
| `GENERIC_RATE_CONTEXT` | Rate/Fed/macro-adjacent vocabulary with no cut/easing assertion either way |
| `NO_RATE_SEMANTICS` | No rate-policy content at all |

This is **not a literal five-string gate**: each class is a tuple of regex patterns covering real semantic variants (explicit cuts, "cutting rates," "rate-cut cycle," "easing cycle," "monetary/policy easing," "fed is cutting/easing," "falling/declining/lower rates," "borrowing costs falling," "central bank shifting to easier policy," "rate decline," plus a separate confident-expectation group: "markets expect/anticipate/are pricing in cuts," "fed is set to/poised to/expected to cut") — not merely the five taxonomy anchor phrases quoted in the Step-7A.1 recommendation.

**Generic taxonomy keywords never independently satisfy the gate**: `discount rate`, `duration`, `treasury yield`, `interest rate(s)`, `fed`, `monetary policy`, `macro`, `inflation`, `yield(s)`, `rate sensitivity`, `rate environment` can only ever route a claim to `GENERIC_RATE_CONTEXT`, never `POSITIVE_EASING`.

**Mention-only excluded**: a dedicated check ("focused on whether," "debate/question/uncertainty...whether," "whether the fed will") resolves to `CONDITIONAL_OR_UNCERTAIN` *before* the positive patterns are even checked, so a bare "cut rates" inside a "will the Fed cut?" framing never counts (found and fixed during test-writing for this task).

**Modality handling**: a direct-positive match still carrying a conditional/modal marker (if/unless/could/may/might/would/potentially — reusing the existing `_CONDITIONAL_PATTERN`) downgrades to `CONDITIONAL_OR_UNCERTAIN`. Confident affirmative-expectation phrasing is exempt from this downgrade, since it already encodes non-hedged certainty in its own wording.

## Production Change

| File | Change |
|---|---|
| `comqutor_alpha/structure_engine/claim_semantics.py` | New `classify_a001_directional_semantics()`, `ALPHA_POSITIVE_REQUIREMENT_CLASSIFIERS` (table-driven registry, currently `{"A001": classify_a001_directional_semantics}`), `alpha_positive_requirement_satisfied()` — the semantic classification logic. |
| `comqutor_alpha/structure_engine/alpha_mapper.py` | One call site in `map_claim_to_alpha`, immediately after the Step-7A negative veto: if the final `matched_alpha` fails `alpha_positive_requirement_satisfied`, it is reset to `None`/`no_match`, mirroring exactly how the Step-7A veto is wired in. New additive diagnostic field `alpha_positive_requirement_override`. |

**Both files were necessary for the same reason Step 7A needed both**: the classification logic and the single wiring point are naturally separate concerns, matching the existing module split.

**Path tracing (Section 19)**: `matched_alpha` can only be set to a non-`None` value via the LLM "selected" outcome under Pure-LLM Alpha semantic authority — deterministic scoring is diagnostic-only and never assigns the final result; the LLM "none"/"unavailable" outcomes never risk a positive A001 result. There is exactly one call site to guard, confirmed during the Step-7A investigation and re-confirmed here; the new gate is placed there, immediately after the existing veto.

**No QQQ-specific or run-ID-specific condition anywhere in the change.**

## Positive Controls

5 controls, including 2 that deliberately avoid the literal phrase "rate cut":

| Claim | Result |
|---|---|
| "The Fed cut rates by 25bp, beginning an easing cycle." | A001 ✓ |
| "Falling discount rates are supporting long-duration growth...as the Fed's easing cycle continues." | A001 ✓ |
| "Monetary easing is increasing risk appetite and supporting long-duration growth assets." | A001 ✓ |
| "Policy rates are expected to decline materially as inflation cools." | A001 ✓ |
| "Borrowing costs are falling as the central bank shifts to easier policy." (no "rate cut" phrase) | A001 ✓ |

**5/5 pass.**

## Negative Controls

15 controls covering every Step-7A.1 residual mechanism and every class listed in Section 18(A–O):

| Class | Example | Result |
|---|---|---|
| Opposition/hawkish | "distinctly hawkish repricing..." | Rejected ✓ |
| Generic rates | "high-beta play on the direction of interest rates..." | Rejected ✓ |
| Rising yields | "rising yields directly pressure...holdings" | Rejected ✓ |
| Higher-for-longer | "rates will stay higher for longer" | Rejected ✓ |
| Cuts delayed | "rate cuts have been delayed..." | Rejected ✓ |
| Fewer cuts expected | "fewer cuts are expected this year..." | Rejected ✓ |
| Pricing a hike | "the market is pricing a hike..." | Rejected ✓ |
| Generic "discount rate" alone | "sensitive to discount rates" | Rejected ✓ |
| Generic "duration" alone | "long duration, QQQ tracks..." | Rejected ✓ |
| Generic "treasury yield" alone | "10-year Treasury yield remains a key input..." | Rejected ✓ |
| Rate-sensitive valuation | "high yields pressure technology valuations" | Rejected ✓ |
| Recession implying possible future cuts | "recession risk...could eventually prompt the Fed to act" | Rejected ✓ |
| Liquidity without cuts | "liquidity conditions are improving..." | Rejected ✓ |
| Mention-only Fed policy | "focused on whether the Fed will cut rates..." | Rejected ✓ |
| Conditional cuts without affirmative thesis | "if inflation falls further, the Fed may eventually cut rates" | Rejected ✓ |

**15/15 pass.**

## Boundary Controls

| Boundary | Test | Result |
|---|---|---|
| A001 vs A003 | Liquidity-only evidence selected as A003 | Maps to A003 normally ✓ |
| A001 vs A501 | Recession-risk evidence selected as A501 | Maps to A501 normally ✓ |
| A001 vs A304 | Rate-sensitive valuation pressure selected as A304 | Maps to A304 normally ✓ |
| Gate scope | A601 narrative claim selected as A601 | Unaffected by A001-only gate ✓ |

**4/4 pass.** All three boundaries preserved; the gate is a no-op for every non-A001 Alpha.

## Historical 66-Claim Offline Replay

| Stage | Count |
|---|---:|
| Original historical (`f88c8956-...`) | 66 |
| After Step 7A (negative veto only) | 29 |
| **After Step 7A.2 (both gates)** | **0** |

**Every one of the original 66 claims is now correctly rejected.**

## 29-Claim Residual Replay

| Stage | Count |
|---|---:|
| Residual input (Step-7A.1 output) | 29 |
| Survivors after positive-requirement gate | **0** |
| Rejected | 29 |

Verified via a dedicated regression test (`test_all_29_step7a1_residual_rows_rejected_by_positive_gate`) that reads the frozen Step-7A.1 audit JSON directly and asserts zero rows classify `POSITIVE_EASING` — no sample ID is hard-coded; the general classifier alone produces this result.

## Remaining Survivors

**None.** No claim ID, text, or rationale to report — the full 66 and the 29-row residual set both fully reject under the new gate.

**`SYSTEMATIC_FALSE_POSITIVE_PATTERN_REMAINS: NO`** — determined by semantic inspection (every original opposition/hawkish, generic-rate, mention-only, and conditional-cut claim correctly resolves to a non-`POSITIVE_EASING` class), not merely from the zero count.

## Regression Results

| Suite | Result |
|---|---|
| Focused (`tests/test_qqq_a001_mapping_remediation.py`, extended) | **56/56 passed** |
| Relevant Alpha Mapper + broader `claim_semantics`-dependent subsystem (11 files) | **508/508 passed** |
| Full backend suite (`pytest -m "not integration"`) | **4168 passed, 27 failed, 42 errors, 3 skipped, 47 deselected** (723.22s) |

**FAILED list: identical to the Step-7A baseline (27/27, same test names).** No new FAILED test. All 27 already individually traced in the Step-7A remediation report: 22 pre-existing/unrelated (JSON data-schema gaps, hardcoded-HEAD pins, already-documented pre-existing failures) + 5 expected `FROZEN_HASHES` collateral from the (unchanged-in-this-task) `alpha_mapper.py`/`claim_semantics.py` edits.

**ERRORS: 3 pre-existing (unchanged) + 39 NEW — fully root-caused, one single cause, not a production regression.**

The 39 new errors span 6 files under `tests/replay/` (`test_exact_semantic_replay.py`, `test_replay_behavioral_equivalence.py`, `test_replay_modes.py`, `test_replay_provider_zero.py`, `test_semantic_call_artifact_binding.py`, `test_semantic_source_bundle_validation.py`). Every one was traced to the **same single line**: `tests/replay/conftest.py:221`, inside the shared `eligible_live_source` fixture, which asserts `model.calls == 4` on its `OfflineSemanticModel` mock.

That mock's alpha-classifier branch always returns `payload["alpha_taxonomy"][0]["alpha_id"]` — "the taxonomy's own first alpha_id, sorted," per its own docstring — which is **A001** (alphabetically/numerically first among the 10 canonical Alpha IDs), regardless of the fixture's fixed claim text: *"AI demand drives GPU demand and revenue growth while valuation risk creates downside"* — pure NVDA/AI content, zero rate/cut/easing language. Before this task, that synthetic A001 selection passed through unchallenged (the Step-7A negative veto never fires on unrelated text), so `matched_alpha` stayed non-null and B1's own LLM stance-upgrade pass legitimately fired a real 4th call. The new positive-requirement gate correctly classifies this claim `NO_RATE_SEMANTICS` for A001 and rejects the match, so `matched_alpha` becomes `None`, B1's stance upgrade has no Alpha to evaluate and never fires, and `model.calls` drops to 3 — tripping the fixture's hardcoded `== 4` assertion for every one of the 39 dependent tests.

**This is a test-infrastructure artifact, not a production regression**: no real Provider/LLM would plausibly select A001 (Rate Cut Cycle) for "AI demand drives GPU demand" content. The mock's "always pick the alphabetically-first taxonomy entry" convenience convention happens to coincide with A001 by alphabetical accident; these 39 tests use A001 only as an arbitrary non-null placeholder to exercise exact-replay atomicity, semantic-call binding, and corruption-handling mechanics unrelated to Alpha-semantic accuracy. Tellingly, the fixture's own comment already documents that this exact assertion (`model.calls == 4`) was bumped once before, from 3, during a prior "Alpha Mapper Authority Migration" — confirming this is a known, precedented, expected-to-need-future-maintenance call-count tripwire, not a stable production invariant. None of this task's own 56 focused tests or the 508 relevant Alpha-Mapper/`claim_semantics`-dependent subsystem tests regressed.

**Not fixed in this task**: touching the widely-shared `tests/replay/conftest.py` fixture (used across 6+ files for unrelated mechanics) is outside this task's narrow-scope authorization ("prefer extending `tests/test_qqq_a001_mapping_remediation.py`," "do not touch unrelated modules"). **Recommended narrow follow-up** (not implemented): update the shared fixture's fixed claim text to include genuine rate-cut/easing language, or change the mock's placeholder-alpha-selection convention to avoid the implicit "alphabetical sort produces A001" assumption — then re-bump the call-count assertion as needed, exactly as was done once before.

**One pre-existing Step-7A test updated** (not weakened): `test_boundary_recession_evidence_does_not_become_a001_even_if_llm_selected_it` → renamed `test_boundary_recession_evidence_negative_veto_does_not_overreach`. Its original assertion (`matched_alpha == "A001"`) is now stale, because with the new positive-requirement gate also active, this recession-only claim (no rate language at all) is correctly rejected — but for a *different, legitimate* reason (the positive gate, not the negative veto). The test now explicitly asserts both: the negative veto still does not fire (preserving the original documented invariant) AND the positive gate does fire, so `matched_alpha` is `None`. This is an expected, correct consequence of adding a second, complementary gate — not a loosened test.

Prior Step-7A full-suite baseline: 4171 passed / 27 failed / 3 errors / 3 skipped / 47 deselected, with every failure/error already individually traced to either pre-existing JSON-schema gaps or the well-precedented `FROZEN_HASHES` collateral pattern. This task's own full run is compared against that baseline in the final response.

## Fresh QQQ Readiness

### READY_FOR_FRESH_QQQ_VALIDATION: **YES**

- No systematic false-positive mechanism remains in the audited residual set (0/29 and 0/66 survivors, semantically confirmed).
- Opposition/hawkish claims no longer survive (15/15 negative controls, including all Step-7A.1 mechanisms).
- Generic rate/macro claims no longer survive.
- Mention-only does not survive without affirmative easing.
- Positive A001 controls remain functional (5/5, including two that avoid the literal phrase "rate cut").
- A001/A003, A001/A501, and A001/A304 boundaries all pass.
- No *production-semantic* regression attributable to this patch in 56 focused + 508 relevant-subsystem tests; one pre-existing test was correctly updated to reflect the new, intended two-gate behavior.
- **Full disclosure**: the broader full-suite run surfaced 39 new test *errors*, all root-caused to one single shared test fixture (`tests/replay/conftest.py`'s `eligible_live_source`) whose synthetic mock happens to canned-select A001 for unrelated NVDA/AI-demand content and is now correctly rejected by the new gate (see Regression Results above for full root-cause tracing). This is a test-infrastructure artifact — not a real Provider/LLM would ever select A001 for that content — and does not bear on QQQ/A001 production-semantic correctness, which is what this readiness gate evaluates. It is flagged as a distinct, narrow, out-of-scope follow-up, not silently absorbed into a "no new regression" claim.

**Next recommended step: Step 7B — one fresh QQQ validation run**, to be separately authorized.

## Historical Acceptance Immutability

**`v0_2_final_acceptance_table.*` was not modified.** The historical, authoritative QQQ run (`f88c8956-...`) actually produced unsupported A001 activity (`active`, score 66.4226) and its Formal Gold result remains **FAIL**. Offline replay demonstrates what the *current* code would now produce against that run's persisted claim text — it does not, and cannot, rewrite what that run's own live LLM calls actually returned at the time. Only a new, fresh QQQ run can establish post-fix validation, and this task does not perform one.

---

**Production files changed: 2** (`claim_semantics.py`, `alpha_mapper.py`). **Test files changed: 1** (extended, not new). **Provider calls: 0. TradingAgents calls: 0. Fresh QQQ runs: 0. Fresh six-ticker runs: 0. Gold changed: no. Trigger Matrix changed: no. Final Acceptance changed: no. Step-5 Adjudication changed: no. Step-6 Failure Analysis changed: no. Step-7A artifact changed: no. Step-7A.1 audit changed: no. Commits: 0. Pushes: 0. Destructive git operations: 0.**

**STEP 7A.2 ONLY. AFFIRMATIVE DIRECTIONAL EASING NOW REQUIRED FOR A001. NO LIVE RUN PERFORMED. HISTORICAL ACCEPTANCE UNCHANGED.**
