# Week 4 Adversarial Engineering Audit — COMQUTOR Alpha
Repo: `/Users/xiangmao/COMQUTOR-Alpha-` · branch `comqutor-structure-layer` · HEAD `64e657958aa1db32528d55e8b9c5520b387f86fc`

Scope: `conflict_schema.py`, `conflict_detector.py`, `pipeline.py`, `week4_persistence.py`, `schema.py`, `repository.py`, `routes_research.py` (conflicts endpoint), `exposure_engine.py`.

---

## 1. Doc / frozen-spec claims (doc:line)

| Claim | Source |
|---|---|
| Formula: `min(Activation A, Activation B) × contradiction_weight × evidence_strength` | `docs/week4_conflict_core_report.md:232-233`, `docs/w4_3_gate_contract.md:77` (using `min`, explicitly, twice) |
| `evidence_strength = (strength_A + strength_B) / 2`, `strength` = mean match_score per side | `docs/week4_conflict_core_report.md:156` |
| Admissibility: both sides `status` ≥ `watch`; ≥1 qualifying committed evidence per side; `evidence_strength > 0` | `docs/week4_conflict_core_report.md:177` |
| Qualifying relations = exactly `{activation, conditional, mixed}` (Week 3's positive-weight subset, frozen independently) | `docs/week4_spec_freeze_audit.md` #9; `conflict_schema.py:23-30` |
| Level bands: `[0,25] low, (25,50] medium, (50,75] medium_high, (75,100] high` | `docs/week4_conflict_core_report.md` (audit #8, referenced at line 141 of `conflict_schema.py`) |
| Main-conflict tie-break: `conflict_score` desc → `evidence_strength` desc → `minimum_activation` desc → canonical `conflict_id` asc | `docs/week4_conflict_core_report.md:272-273`; `docs/w4_3_gate_contract.md:580,587` |
| Bull/bear role from Week 3 `direction` only, never canonical order/alpha_id/ticker | `docs/week4_conflict_core_report.md` audit #10 |
| `/conflicts` must read only the DB (`get_week4_conflict_result`), never recompute, never touch local run dir or `alpha_matches.json`/`structure_graph.json` | `docs/w4_3_gate_contract.md:152-158` |
| W4.2 persistence must be atomic: one run's activation+conflict rows replaced together | `week4_persistence.py:1-18` header; `repository.py:637-668` |
| MSFT `A102`/`A304` is explicitly `BLOCKED_BY_SPEC_CONFLICT` — taxonomy never declares this pair | `docs/week4_spec_freeze_audit.md` §16; `docs/w4_3_gate_contract.md:402-403` |
| Exposure Engine core formula: `historical_mapping*0.50 + current_evidence*0.30 + agent_confidence*0.20`; product gate `BLOCKED_BY_SEED` (no `entity_alpha_exposure_seed.yaml` exists yet) | `exposure_engine.py:1-24`; `docs/w4_3_gate_contract.md:402` |
| `docs/w4_3_gate_contract.md` itself records that its authoring session found a **real conflict** between its own instruction (default-expose raw agent transcripts) and the frozen `week4_spec_freeze_audit.md` #14 clause (structured-only), and that it stopped and escalated rather than silently picking a side — resolved 2026-07-15 as `STRUCTURED_ONLY` | `docs/w4_3_gate_contract.md` §7 (lines 254-389) |

---

## 2. Actual code behavior per question (file:line)

**Q1 — Taxonomy pair enumeration.** `conflict_detector._enumerate_canonical_pairs` (`conflict_detector.py:102-173`) builds `directed` strictly from `alpha.conflict_alphas` entries read out of the taxonomy mapping passed in (defaults to `load_alpha_taxonomy()`, `conflict_detector.py:839-840`); `detect_alpha_conflicts` then iterates only `declared_pairs` (`conflict_detector.py:864`). There is no code path that adds a pair not present in some alpha's `conflict_alphas` list. `evaluate_conflict_pair` (single-pair helper, `conflict_detector.py:915-962`) explicitly rejects any pair absent from `declared_pairs` with `PAIR_NOT_DECLARED` (`conflict_detector.py:940-948`) — confirmed both by unit tests and by direct invocation with synthetic strong A102/A304 evidence (`tests/test_conflict_detector.py:1334-1352`, `tests/test_week4_golden_closure.py:273-325`), all showing rejection.

**Q2 — Qualifying committed evidence filter.** `_gather_qualifying_evidence` (`conflict_detector.py:405-492`) requires, per claim: non-empty `claim_id`; `match_status == "matched"`; `matched_alpha == alpha_id`; non-empty evidence text; `_relation_for_match(...)` (reused from Week 3) in `QUALIFYING_RELATIONS = {"activation","conditional","mixed"}` (`conflict_schema.py:30`); finite `score`. Anything else is excluded with a stable reason code (`EXCLUDED_*`). In `_evaluate_candidate` (`conflict_detector.py:639-652`), a side with zero qualifying claims is rejected/suppressed (`REASON_MISSING_LEFT_EVIDENCE`/`REASON_MISSING_RIGHT_EVIDENCE`, or `REASON_AMBIGUOUS_ONLY` if all exclusions were the `ambiguous` status). An Alpha with weak/no evidence is excluded from admission — verified live via mutation (§7).

**Q3 — evidence_strength aggregation.** `_mean_match_score` (`conflict_detector.py:495-498`): `sum(match_score for c in qualifying) / len(qualifying)` per side (arithmetic mean, not sum/min/max/weighted). `evidence_strength_raw = (strength_a_raw + strength_b_raw) / 2.0` (`conflict_detector.py:656`). Matches `docs/week4_conflict_core_report.md:156` exactly.

**Q4 — Conflict score formula.** `conflict_detector.py:681-682`:
```python
minimum_activation = min(fields_a.score, fields_b.score)
conflict_score_raw = minimum_activation * float(contradiction_weight) * evidence_strength_raw
```
Uses `min()`, matching the frozen spec's `min(Activation A, Activation B)` exactly. **No max() substitution found anywhere in the formula path.** Confirmed by mutation testing (§7) — swapping to `max` breaks `test_conflict_score_formula_matches_official_definition` and 19 other tests.

**Q5 — Conflict level thresholds.** `conflict_schema.py:141-165`, `_CONFLICT_LEVEL_UPPER_BOUNDS = ((25.0,"low"),(50.0,"medium"),(75.0,"medium_high"),(100.0,"high"))`; `conflict_level()` clamps via `clamp_percent` then returns the first band whose upper bound the score does not exceed, i.e. half-open-low/closed-high: `score<=25.0 -> low`, `25.0<score<=50.0 -> medium`, etc. Matches spec exactly (`25.0` is `low`, `25.0001` is `medium` — verified by `tests/test_conflict_detector.py:912-926` parametrized boundary test, including exact `25.0001`/`50.0001`/`75.0001` edges).

**Q6 — Bull/bear role assignment.** `resolve_bull_bear` (`conflict_schema.py:182-195`) returns `(alpha_a, alpha_b)` only if `direction_a=="positive" and direction_b=="negative"`, `(alpha_b, alpha_a)` only if reversed, else `(None,None)`. Role comes solely from each side's own Week 3 `direction` field, never from canonical order/alpha_id — cannot be "assigned backwards" because it is derived, not chosen; two positives or two negatives correctly yield `(None,None)` → `REASON_DIRECTION_ROLE_UNRESOLVED` (`conflict_detector.py:660-662`, tested at `tests/test_conflict_detector.py:818-859`, including a case that specifically proves role is not canonical-order-dependent, lines 846-859).

**Q7 — Main-conflict tie-break.** `_conflict_sort_key` (`conflict_detector.py:790-800`) sorts on `(-_sort_conflict_score, -_sort_evidence_strength, -_sort_minimum_activation, conflict_id)` — a real deterministic 4-level key, using unrounded internal `_sort_*` fields (never re-derived from rounded display values, per the code comment at `conflict_detector.py:713-719`) so display rounding cannot change ranking. `admitted_conflicts.sort(key=_conflict_sort_key)` (`conflict_detector.py:878`); `main_conflict = conflicts[0]` (`conflict_detector.py:890`). This is a real sort, not insertion-order luck — verified further in §7.

**Q8 — Admitted/suppressed/rejected persistence.** `build_conflict_rows` (`week4_persistence.py:580-688`) builds one row per **every** declared candidate regardless of outcome (`rows.append(...)` inside the loop over all `candidates`, `week4_persistence.py:658-687`), with `outcome` stored per row. `repository.persist_week4_results` (`repository.py:637-668`) inserts all `conflict_rows` (all outcomes) into the single `alpha_conflicts` table in one transaction — there is exactly one table (`schema.py:120-151`) with an `outcome` column (`admitted`/`suppressed`/`rejected`), not three separate tables and not an admitted-only table. Confirmed: `test_all_six_candidate_outcomes_and_admitted_details_are_persisted` (`tests/test_week4_persistence.py:324-336`) does a real DB round-trip and asserts `{row["outcome"] for row in rows} == {"admitted","suppressed","rejected"}`. Mutation-confirmed in §7.

**Q9 — A102/A304 literal search.** `grep -rn "A102\|A304"` across `comqutor_alpha/`: hits are (a) `alpha_taxonomy_v1.yaml` data (each ID appears only inside its own alphas' own `conflict_alphas` list — A102 never lists A304 and vice versa, confirmed directly by reading the YAML and by `tests/test_week4_golden_closure.py:215-230`); (b) `alpha_loader.py` `EXPECTED_ALPHA_IDS`/`MANDATORY_CONFLICT_WEIGHTS` — a **validation-only** constant used by `validate_taxonomy()` (`alpha_loader.py:116-141`) to assert the loaded YAML declares 6 specific mandatory pairs with expected weights (tolerance 0.05); it does not inject/override pairs into detection, it only fails-closed if the YAML doesn't match; A102/A304 is **not** among the 6 `MANDATORY_CONFLICT_WEIGHTS` entries; (c) `conflict_schema.py:178` — a docstring example (`"A101__A304"`), not logic; (d) `claim_semantics.py`/`alpha_mapper.py` — unrelated Week 2/3 alpha classification sets, not conflict-pair logic. **No production code combines A102+A304 into a fabricated conflict pair.** The detector actively rejects this exact pair with `PAIR_NOT_DECLARED` even when fed maximal synthetic evidence for both sides (`conflict_detector.py:940-948`, exercised live at `tests/test_week4_golden_closure.py:273-325`).

**Q10 — Persistence atomicity.** `repository.persist_week4_results` (`repository.py:657-668`) wraps delete-both-tables + insert-both-tables in a single `with self._engine.begin() as conn:` block; any `SQLAlchemyError` is caught and re-raised as `GraphPersistenceError("DB_WRITE_FAILED")` (`repository.py:667-668`), and SQLAlchemy's `engine.begin()` context manager rolls back on exception. Verified against **real PostgreSQL** (not sqlite) by running `tests/test_week4_postgres_persistence.py::test_transaction_rollback_preserves_prior_state`, which registers a `before_cursor_execute` hook that raises `OperationalError` specifically on the `alpha_conflicts` INSERT (the second table write), then queries the DB directly afterward and asserts `get_alpha_activations`/`get_alpha_conflicts` are byte-for-byte unchanged from before the failed call. **PASSED** (see §6/§7) — confirmed zero partial rows land.

**Q11 — Conflict-read API source of truth.** `get_persisted_conflicts` (`routes_research.py:895-919`) calls `repository.get_week4_conflict_result(safe_run_id)` (`routes_research.py:903`) — a pure DB read (`repository.py:707-712` → `reconstruct_conflict_result`, which only takes already-fetched `rows`, never touches the filesystem). No call to `detect_alpha_conflicts` or any file path (`alpha_matches.json`/`structure_graph.json`) exists in this function. Confirmed live: `tests/test_week4_pipeline_api.py::test_conflicts_api_survives_deleted_local_run_directory` (lines 362-374) deletes the local run directory with `shutil.rmtree` and asserts the API still returns `status="ok"` with the correct `main_conflict`.

**Q12 — Exposure Engine fail-closed behavior.** `exposure_engine.py` never reads any seed file at all — it is architecturally not wired to `entity_alpha_exposure_seed.yaml` (which does not exist anywhere in the repo — confirmed by `find`). `_require_unit_interval_number` (`exposure_engine.py:56-70`) rejects `bool`/non-numeric/non-finite/out-of-[0,1] values by raising `ExposureInputError("INVALID_EXPOSURE_INPUT")` — no default substitution, no clamping. `compute_entity_alpha_exposures` requires `current_evidence`/`agent_confidence` to declare **exactly** the same `alpha_id` set as `historical_mapping`, else `ExposureInputError("EXPOSURE_INPUT_SET_MISMATCH")` (`exposure_engine.py:177-179`) — a missing per-Alpha input never silently defaults to 0. Live-invoked (§5): passing `agent_confidence={}` while `historical_mapping={"A101": 0.8}` raises `EXPOSURE_INPUT_SET_MISMATCH`; passing `historical_mapping=None` raises `INVALID_EXPOSURE_INPUT`. Confirmed **fail-closed**, not fail-open.

---

## 3. Spec-vs-code conflicts

**None found in the reviewed Week 4 code.** Formula, evidence-strength aggregation, level bands, tie-break, bull/bear resolution, admissibility, and persistence atomicity all match the frozen docs exactly, and all were independently re-derived (manual oracle, §5) and mutation-tested (§7), not just doc-compared.

One **process-level** finding worth flagging even though it resolved correctly: `docs/w4_3_gate_contract.md` §7 documents that the W4.3 task instruction itself, as originally given, contradicted the frozen spec (`week4_spec_freeze_audit.md` #14) by asking for a default-exposed `raw_agent_outputs` field on `/agent-outputs`. The session stopped, escalated, and the spec owner resolved it `STRUCTURED_ONLY` (2026-07-15) — i.e. the raw transcript is never exposed by that endpoint. This is not a Week-4-conflict-core defect but is exactly the kind of spec-authority conflict this audit is meant to catch; it was caught and resolved correctly by the implementation process itself.

---

## 4. Exact formulas as found in code

```
minimum_activation  = min(activation_a, activation_b)                    # conflict_detector.py:681
strength_side        = mean(qualifying claim match_scores for that side)  # conflict_detector.py:495-498
evidence_strength    = (strength_a + strength_b) / 2                      # conflict_detector.py:656
conflict_score_raw   = minimum_activation * contradiction_weight * evidence_strength   # conflict_detector.py:682
conflict_score       = clamp(conflict_score_raw, 0, 100)                  # conflict_detector.py:683
conflict_level(score):
    score <= 25.0            -> "low"
    25.0 < score <= 50.0     -> "medium"
    50.0 < score <= 75.0     -> "medium_high"
    75.0 < score <= 100.0    -> "high"
main-conflict sort key = (-conflict_score, -evidence_strength, -minimum_activation, conflict_id)  # ascending sort
exposure_score = historical_mapping*0.50 + current_evidence*0.30 + agent_confidence*0.20  # exposure_engine.py:91-95
```

---

## 5. Manual oracle calculations vs production output

Built with `tests/fixtures/week4_conflict_cases.py` helpers (`two_alpha_taxonomy`, `activation_entry`, `activation_payload`, `match_record`) — synthetic alpha IDs `X99/Y99`, `P99/Q99` never seen by production code, so the detector cannot special-case them. Expected values computed **by hand first**, then compared to `detect_alpha_conflicts()`'s real output.

**Scenario 1** (X99 bull / Y99 bear, contradiction_weight=0.75):
- `min(activation_X99=72.0, activation_Y99=88.0) = 72.0`
- `strength_X99 = mean([0.6, 0.9]) = 0.75`
- `strength_Y99 = mean([0.4]) = 0.4`
- `evidence_strength = (0.75 + 0.4) / 2 = 0.575`
- `conflict_score_raw = 72.0 * 0.75 * 0.575 = 31.05`
- Hand result: **score=31.05, level=medium**
- Production result: **score=31.05, level=medium** — `components` = `{activation_a:72.0, activation_b:88.0, minimum_activation:72.0, contradiction_weight:0.75, alpha_a_evidence_strength:0.75, alpha_b_evidence_strength:0.4, evidence_strength:0.575}`
- **MATCH: exact.**

**Scenario 2** (P99 bull / Q99 bear, contradiction_weight=0.95):
- `min(90.0, 99.0) = 90.0`
- `strength_P99 = mean([1.0]) = 1.0`, `strength_Q99 = mean([1.0]) = 1.0`
- `evidence_strength = (1.0+1.0)/2 = 1.0`
- `conflict_score_raw = 90.0 * 0.95 * 1.0 = 85.5`
- Hand result: **score=85.5, level=high**
- Production result: **score=85.5, level=high**
- **MATCH: exact.**

Script: `/private/tmp/claude-501/-Users-xiangmao-COMQUTOR-Alpha-/15b53a10-aac2-49e2-ab0e-6e4580d9d8ed/scratchpad/manual_oracle.py` — no defect found; **min() confirmed correct**, not min/max-swapped.

---

## 6. Test run results

Offline suite (`tests/test_conflict_detector.py tests/test_week4_golden_closure.py tests/test_week4_nvda_conflict_sanity.py tests/test_week4_persistence.py tests/test_week4_pipeline_api.py tests/test_week4_qqq_conflict_sanity.py tests/test_exposure_engine.py`): **292 passed**, 0 failed.

Integration suite `tests/test_week4_postgres_persistence.py -m integration`: **initially 10 SKIPPED** — `COMQUTOR_TEST_DATABASE_URL not configured`, despite the task brief's claim that pytest picks up `.env` automatically. Root cause found: no `conftest.py`/dotenv auto-load wires `.env` into the test process env; only `tests/test_week2_llm.py` calls `load_dotenv()` explicitly, and it isn't a fixture other test files import. **This claim in the task setup was false** — env vars had to be exported manually (`set -a && source .env && set +a`) before the DB tests would run at all; treated as **not a normal skip** and worked around rather than accepted as PASS-by-skip. After exporting: **10 passed, 0 skipped**, against the real docker Postgres on port 5433, including the atomicity/rollback test (Q10).

### Test effectiveness table

| Test file / representative test | Entry point | Mock layer | Assertion specificity | Tautology risk | Rating |
|---|---|---|---|---|---|
| `test_conflict_detector.py` (113 tests) | `detect_alpha_conflicts` (production, direct) | None — synthetic fixtures only | Exact numeric values (`pytest.approx`), exact reason codes, exact IDs | None — expected values hand-derived in test code (e.g. `min(80,60)*0.90*1.0`), not copied from detector output | **STRONG** |
| `::test_conflict_score_formula_matches_official_definition` | production | none | exact formula recomputation, `abs=1e-6` | none — independent formula literal in test | **STRONG** |
| `::test_tie_break_uses_canonical_pair_id_ascending` | production | none | exact winner ID by string comparison, independent of detector | none | **STRONG** |
| `test_week4_nvda_conflict_sanity.py` / `_qqq_conflict_sanity.py` | full Week1-3 pipeline → detector (real E2E) | none | exact conflict_id/bull/bear/weight; `test_no_ticker_specific_production_branch` does literal source grep | none | **STRONG** |
| `::test_main_conflict_is_decided_by_formal_sort_rule_not_hardcoded` | production | none | `main_conflict==conflicts[0]` + scores monotonic desc | **does not exercise a tie** — see Test Gap below | **PARTIAL** (proves ordering correctness for the realized, non-tied case only) |
| `::test_no_pairwise_conflict_hardcoded_as_main_by_ticker` | source introspection (`inspect.getsource`) | n/a | literal-string absence check (`'"QQQ"' not in source`) | Weak in isolation, but corroborated by full manual source read (§2 Q1/Q7) confirming no ticker branches exist anywhere in `conflict_detector.py` | **PARTIAL→STRONG when combined with manual code read** |
| `test_week4_persistence.py` (round-trip, corruption, atomicity subset) | `repository.persist_week4_results`/`get_week4_conflict_result` against real sqlalchemy engine (sqlite in-mem) | none | Direct DB row assertions, exact outcome sets | none | **STRONG** |
| `test_week4_postgres_persistence.py::test_transaction_rollback_preserves_prior_state` | `repository.persist_week4_results` against real Postgres | `before_cursor_execute` hook forces a real `OperationalError` on the 2nd INSERT | queries DB directly before/after, asserts byte-identical | none — this is exactly the mutation the audit asked to run manually; it already exists and passes | **STRONG** |
| `test_week4_pipeline_api.py::test_conflicts_api_success_equals_repository_reconstruction` / `::_survives_deleted_local_run_directory` | `get_persisted_conflicts` (production route helper) | none | exact dict equality against direct repo call; directory-deletion + still-correct result | none | **STRONG** |
| `test_week4_golden_closure.py` (2 full E2E tests) | full POST→GET→DB→`/conflicts` chain | none | exact conflict_id/bull/bear/weight, POST==GET==DB==API equality | none | **STRONG** |
| `test_exposure_engine.py` | `calculate_exposure`/`compute_entity_alpha_exposures` (production, direct) | none | exact contribution values, exhaustive fail-closed input matrix | none | **STRONG** |

### Confirmed test gap (not a code defect)

**No test constructs a scenario where `conflict_score` ties but `evidence_strength` or `minimum_activation` differ** — i.e. levels 2 and 3 of the documented 4-level tie-break are never independently exercised. Confirmed by mutation (§7): removing both levels from `_conflict_sort_key` causes **zero** test failures across the full Week 4 offline suite. Level 1 (`conflict_score`) and level 4 (`conflict_id`) are both independently, strongly tested.

---

## 7. Mutation results table

All mutations performed by substituting a modified copy of `conflict_detector.py`/`repository.py` into `sys.modules` before pytest import (no tracked file touched — copies live under `/private/tmp/.../scratchpad/`).

| # | Mutation | Result | Verdict |
|---|---|---|---|
| 1 | `minimum_activation = min(...)` → `max(...)` | 20/292 relevant tests fail (`test_conflict_score_formula_matches_official_definition` + cascading golden/E2E tests) | **CAUGHT** |
| 2 | Reverse 4th-level tie-break (`conflict_id` ascending → descending, via custom comparator) | 1 test fails (`test_tie_break_uses_canonical_pair_id_ascending`) | **CAUGHT** |
| 3 | Remove 2nd/3rd-level tie-break (`evidence_strength`, `minimum_activation`) from sort key entirely, keep only `conflict_score`/`conflict_id` | **0 tests fail** | **TEST GAP** (confirmed, see §6) |
| 4 | `_mean_match_score`: mean → sum | 20 tests fail (`test_evidence_strength_is_mean_of_side_means` + cascading E2E, because summed evidence_strength saturates past the persistence [0,1] validator) | **CAUGHT** |
| 5 | `contradiction_weight` perturbed by `+0.05` before multiplication | 2 tests fail (`test_conflict_score_formula_matches_official_definition`, `test_component_breakdown_is_complete_and_matches_score`) via exact-value `pytest.approx(abs=1e-3)` assertions | **CAUGHT** |
| 6 | Remove evidence requirement on side A entirely (a pair can be admitted with zero qualifying evidence for alpha_a) | 15 tests fail across `TestQualifyingEvidence`/`TestEvidenceAuditContract`/`TestEvidenceStrengthCalculation` | **CAUGHT** |
| 7 | Force real PostgreSQL to raise on the `alpha_conflicts` INSERT (2nd table write) mid-`persist_week4_results` | DB queried directly afterward: activation/conflict rows byte-identical to pre-call state — **zero partial rows** | **NO ROLLBACK BUG** (test already exists and passes: `test_transaction_rollback_preserves_prior_state`) |
| 8 | Monkeypatch `build_week4_rows` to silently drop non-`admitted` conflict rows before persistence | 11 tests fail, including a direct DB-outcome-set assertion (`test_all_six_candidate_outcomes_and_admitted_details_are_persisted`) and a pipeline round-trip cross-check (`test_conflict_detector_inputs_come_from_this_runs_own_persisted_artifacts`) | **CAUGHT** |

---

## 8. Confirmed defects

**No P0 or P1 defects found in Week 4 code.** One P2 finding:

| Severity | file:function | test | actual problem | why tests missed it | minimal repro | blast radius | fix direction |
|---|---|---|---|---|---|---|---|
| P2 | `conflict_detector.py:790-800` (`_conflict_sort_key`) | none exists for levels 2-3 | The formally-specified 4-level main-conflict tie-break (`conflict_score` desc → `evidence_strength` desc → `minimum_activation` desc → `conflict_id` asc) has real, independent unit coverage only for level 1 and level 4. A regression that silently dropped or corrupted the `evidence_strength`/`minimum_activation` tie-break levels (e.g. an accidental key-tuple truncation during a future refactor) would ship with 0 failing tests. | Existing fixtures that exercise ties (`test_tie_break_uses_canonical_pair_id_ascending`) construct scenarios where `conflict_score` AND `evidence_strength` AND `minimum_activation` are all simultaneously equal by construction (two structurally identical two-alpha taxonomies), so they never probe a case where the score ties but the finer-grained levels differ. | Add a unit test with two admitted conflicts sharing identical `conflict_score` (e.g. via different weight/activation/evidence combinations that multiply to the same product) but different `evidence_strength`, and assert the higher-`evidence_strength` one wins main-conflict; repeat for `minimum_activation` with `evidence_strength` tied. | Low in practice — production formula is currently correct (manual oracle + full mutation battery on levels 1/4 pass) — but the mid-tier tie-break levels are unverified against regression. | Add the two missing tie-break unit tests to `tests/test_conflict_detector.py::TestMainConflictArbitration`. |

**Task-setup finding (not a Week 4 code defect):** the audit brief's claim "`COMQUTOR_TEST_DATABASE_URL` ... pytest picks these up automatically" is **false** for this repo — no dotenv auto-load wires `.env` into the pytest process; the integration suite silently reports 10 SKIPPED unless the operator manually exports the `.env` vars first. This is a documentation/tooling gap in the audit's own premises, reported per instructions rather than treated as a pass-by-skip.

---

## 9. Week 4 verdict

```
VERIFIED_WITH_LIMITATIONS
```

**Justification:** Every formula, threshold, admissibility rule, bull/bear resolution rule, taxonomy-enumeration boundary, persistence-atomicity guarantee, and API read-path claimed by the frozen Week 4 docs was independently re-derived by hand (manual oracle, exact match), cross-checked against the real production code path (not a re-implemented helper), and survived a battery of 8 targeted mutations — 7 of 8 were caught immediately by existing tests with exact-value assertions; the DB rollback-atomicity mutation was verified directly against a real running PostgreSQL instance and showed correct zero-partial-row rollback. The `min()` vs `max()` question — explicitly flagged as the likely bug target — is **confirmed correct**: code and docs both use `min(activation_A, activation_B)`, and a live `min→max` mutation breaks 20 tests. No `A102`/`A304` fabrication exists anywhere in production code; that exact pair is actively, repeatedly, and successfully rejected as undeclared, including under adversarial maximal-evidence input. The `exposure_engine.py` module fails closed on every missing/invalid input tested, live-invoked, not just doc-claimed.

The "_WITH_LIMITATIONS" qualifier reflects: (1) one confirmed, narrow test gap — the 2nd/3rd tie-break levels are unexercised by any test (P2, not a live defect); (2) the task brief's premise about `.env`/pytest auto-configuration was false and required a manual workaround to actually exercise the PostgreSQL integration profile at all.
