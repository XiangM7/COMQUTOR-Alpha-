# B3 Entity Exposure Gated States — Implementation and Validation Report

Status: **Implementation complete, wired end-to-end, offline-tested, and
validated against a real saved run.** `HEAD` re-verified below. No commit,
no push. Reuses the existing Exposure Engine formula, qualification-ceiling
logic, and Evidence Fact Index unchanged — this is an upgrade of the
existing experimental global `off`/`shadow`/`enforced` prototype mode to
John's formal, per-ticker `draft_shadow` / `approved_gating` / `disabled`
seed lifecycle, not a new Entity Exposure engine.

## 1. Preserved state

`git branch --show-current` → `comqutor-structure-layer`. `git rev-parse
HEAD` → `b5837e80a4550fc35165d0013a8ef0f27ccb4c8f` (unchanged before and
after this task — re-verified at report-writing time). `git status
--short` at task start: 484 lines, the same large, legitimate,
cumulative uncommitted worktree from every prior task in this session
(including the completed B1/B2 work) — used exactly as-is. No
`reset`/`restore`/`checkout`/`clean`/`stash` run at any point. Checked for
local uncommitted overlap on every file this task would touch before
editing anything: only `routes_research.py` and `week4_persistence.py`
already had unrelated staged changes (B1/B2 work, and — for
`routes_research.py` — an unrelated prior "structured adapter authority
routing" sprint); both were edited additively in clearly separate regions,
confirmed via `git diff HEAD` inspection before touching either file.

## 2. Existing implementation reused vs. what had to change

Confirmed by direct code reading before any edit (per task section 2):

1. **Formula unchanged**: `exposure_engine.py`'s `EXPOSURE_WEIGHTS` is
   still exactly `historical_mapping×0.50 + current_evidence×0.30 +
   agent_confidence×0.20`. Not touched.
2. **Shadow already guaranteed score/status/dominant-membership
   invariance**: `compute_run_entity_alpha_exposures`'s `off`/`shadow`
   branch already never wrote to `activation_score`/`status`/
   `dominant_alphas`; only the `enforced` branch (via `_cap_status`) ever
   does. This mechanism is unchanged — B3 only changes *how the effective
   mode is decided*, never what each mode does once decided.
3. **Enforced already only capped qualification, never the numeric
   score**: `_cap_status` only ever lowers `status` to a ceiling
   (`active` or `dominant`); `activation_score` is never written in either
   branch. Unchanged.
4. **Evidence reuse already correct**: `calculate_runtime_exposure_inputs`
   consumes `_exposure_evidence_summary`'s already-grouped canonical
   Evidence Fact Index output (`activation_scorer_v2._group_evidence`,
   the same grouping Activation v2 itself uses) — never regroups raw
   claims, never a second dedup implementation. Unchanged.
5. **Consumption points already existed** (`entity_alpha_exposures.json`,
   `structure_graph.json`'s per-alpha `entity_exposure`, `run_audit.json`'s
   `entity_exposure` section, the Research API's `entity_alpha_exposures`/
   `entity_alpha_exposure_status` fields, `GET /api/research/{run_id}/
   entity-exposures`, `AlphaCard.tsx`) — all extended additively, none
   rebuilt.

**What genuinely had to change** (John's core ask): lifecycle authority
moves from one global `ExposureSeedManifest.approval_status`/
`enforcement_allowed` pair to a **per-ticker** `TickerSeedLifecycle`
(`seed_version`/`owner`/`approved_by`/`approved_at`/`configured_status`),
because a single global flag cannot express `NVDA=approved_gating,
GOOGL=draft_shadow` simultaneously — exactly the scenario this batch
requires. `resolve_exposure_mode` gained a required `ticker` parameter and
now resolves fail-closed per ticker; the pre-existing internal
`off`/`shadow`/`enforced` vocabulary is kept underneath via a fixed,
deterministic mapping so `compute_run_entity_alpha_exposures`'s own
qualification-ceiling branching needed zero logic changes.

## 3. Schema change

`comqutor_alpha/config/entity_alpha_exposure_seed_v0.1.yaml`: each
top-level ticker is now `{seed_version, owner, approved_by, approved_at,
status, exposures: {alpha_id: value}}` instead of a flat `{alpha_id:
value}` map. `entity_alpha_exposure_seed_manifest_v0.1.yaml`
(`schema_version` bumped `v1`→`v2`): narrowed to file-level identity only
(`schema_version`, `methodology_version`, three source-file SHA256 hashes)
— `seed_version`/`approval_status`/`approved_by`/`enforcement_allowed`/
`effective_date`/`formal_plan_tickers`/`extension_tickers` all removed
from the manifest (they are per-ticker now, or — for the ticker
allow-list — implicit in the seed file's own top-level keys, which
removes an entire redundant list rather than adding one). No new database
table, no new database column: `EXISTING_DB_TABLE_REUSED = YES`. The five
new per-record fields (`owner`/`approved_by`/`approved_at`/
`configured_status`/`effective_status`) are persisted inside the
*existing* `provenance_json` column (nested under a `b3_lifecycle` key,
unpacked back to top-level on read) — this repository's migration runner
only supports `CREATE TABLE IF NOT EXISTS`, never `ALTER TABLE`, so a new
column could not safely reach an already-created database; storing inside
the existing JSON column avoids that gap entirely while adding zero schema
surface.

## 4. John's six-ticker seed: exact-match result

**`SIX_TICKER_SEED_EXACT_MATCH = YES`.** Every (ticker, alpha_id, value)
triple in `NVDA`/`SNDK`/`TSM`/`MSFT`/`QQQ`/`AMD` matches task section 4
exactly — verified two independent ways: (a) a standalone script
comparing every value against a hand-transcribed copy of the task's own
numbers before any test existed, and (b) `tests/test_b3_entity_exposure_
gated_states.py::test_2_johns_six_seed_values_match_exactly_ticker_by_
ticker_alpha_by_alpha`, a permanent regression snapshot. Each of the six
carries `seed_version="v0.1"`, `owner="John"`, `approved_by="John"`,
`approved_at="2026-08-11"` (the exact ISO date given — no time, timezone,
or seconds invented), `status="approved_gating"`.

**`OLD_ELEVEN_TICKER_DRAFT_LEAKED_INTO_APPROVED_SEED = NO`.** The prior
11-ticker draft file (`docs/entity_alpha_exposure_shadow_productization_
report.md`) is not simply relabeled `approved`: John's new values are
*genuinely different* from the old draft's values for the same six
tickers (e.g. old `NVDA.A103=0.70` vs. new `0.85`; old `TSM.A101=0.85` vs.
new `0.55`; old `SNDK.A102=0.25` vs. new `0.20` — 13 such differing pairs
checked explicitly in `test_2b_old_eleven_ticker_draft_values_do_not_leak_
into_approved_seed`), and several tickers' old Alpha *coverage* was wider
than John's new set (e.g. old `NVDA` included `A001`/`A003`/`A501`; John's
new `NVDA` does not — these three now correctly resolve to
`historical_mapping=None`/`exposure_status="missing_seed"`, never `0.0`).
`GOOGL`/`AMZN`/`AVGO`/`SMCI`/`SPY` — the five tickers John did not
re-approve in this batch — remain in the seed file (not deleted; real,
previously-imported data, kept for shadow-only display/audit continuity)
with their original, unchanged draft values, `status="draft_shadow"`, and
`owner`/`approved_by`/`approved_at` all `null` (never approved). They can
never reach `approved_gating` (see section 7).

## 5. Configured vs. effective status, and approval metadata

Every exposure record and the run-level artifact now carry both
`configured_status` (what the seed file declares for this ticker) and
`effective_status` (what actually applied this run, after the fail-closed
completeness check and any downgrade-only override) — always distinct
fields, so a caller can see *both* what was intended and what actually
happened, never conflate them. `owner`/`approved_by`/`approved_at` are
carried on every record (nullable — `null` for a `draft_shadow`/unapproved
ticker, never coerced to an empty string or a fabricated value).

## 6. Shadow invariants (`draft_shadow`)

Unchanged mechanism (section 2.2), now reached via `effective_status ==
"draft_shadow"` instead of a global `shadow` flag. Proven:
Exposure computed and visible in every record (`historical_mapping`/
`current_evidence`/`agent_confidence`/`final_exposure`/`would_block_*`);
`activation_score`, `status`, and `dominant_alphas` byte-identical
before/after, on both synthetic fixtures (`test_shadow_computes_flags_
without_changing_score_level_or_dominant_list`) and the real saved NVDA
run (section 12: all ten alphas' scores/statuses/dominant list identical);
Conflict outcomes byte-identical (`test_shadow_entity_exposure_does_not_
change_conflict_outcomes`, and section 12's real-run conflict comparison).

## 7. `approved_gating`: before/after and fail-closed behavior

**`APPROVED_GATING_CHANGES_ONLY_QUALIFICATION_NOT_SCORE = YES`.**
`activation_score` is never written in the `enforced`-mapped branch
(unchanged code, section 2.3); only `status` may be capped downward
(`dominant`/`regime_level` → `active`, or → `dominant` at the
regime-only threshold), and only when the *fail-closed* check below
passes. On the real saved NVDA run (section 12), qualification logic
evaluated for all ten alphas (`qualification_effect_applied=True` for
seven of them), yet the *final* status value was identical to the
pre-exposure baseline for all ten — the theoretical ceiling never actually
bound below each alpha's already-computed status for this specific real
evidence. This is an honest empirical finding for this run, not a
guarantee that gating can never change a status; the direct unit test
(`test_synthetic_enforced_qualification_ceiling`, three parametrized
cases) proves the ceiling *does* bind and change status when
`final_exposure` is genuinely low.

**`INCOMPLETE_APPROVAL_CAN_BE_UPGRADED = NO`.** A ticker configured
`approved_gating` but missing any one of `seed_version`/`owner`/
`approved_by`/`approved_at` fails closed to `effective_status=
"draft_shadow"` with `APPROVAL_METADATA_INCOMPLETE`+`GATING_NOT_ALLOWED`
reason codes, and gating does **not** execute (`mode` resolves to
`"shadow"`, `qualification_effect_applied` stays `False`) — proven by
`test_14_approved_gating_missing_approval_field_fails_closed`, mirroring
the exact same fail-closed pattern the pre-existing global
`SEED_NOT_APPROVED`/`ENFORCEMENT_NOT_ALLOWED` gate already used (kept as
back-compatible aliases of the two new reason codes).

**`ENV_VAR_CAN_UPGRADE_DRAFT_OR_DISABLED = NO`.** Neither the legacy
`COMQUTOR_ENTITY_EXPOSURE_MODE` env var nor the new canonical
`COMQUTOR_ENTITY_EXPOSURE_STATUS` env var can upgrade a `draft_shadow`
ticker to `approved_gating`, or re-enable a `disabled` ticker — an
attempted upgrade is detected and ignored (recorded as
`REQUESTED_UPGRADE_IGNORED`, never silently dropped), while a *downgrade*
(`approved_gating`→`draft_shadow`/`disabled`) is honored and recorded as
`REQUESTED_STATUS_DOWNGRADE` — proven against the real, current seed file
(`GOOGL`, genuinely `draft_shadow`) and synthetic `disabled`/
`approved_gating` fixtures in `test_17_env_var_cannot_upgrade_draft_or_
disabled_to_gating`.

## 8. `disabled` invariants

**`DISABLED_PRODUCES_ZERO_PER_ALPHA_RECORDS = YES`,
`DISABLED_AFFECTS_ACTIVATION_OR_CONFLICT = NO`.** Maps to the pre-existing
`off` branch, which already popped `_exposure_evidence`/`entity_exposure`
and emitted zero records without touching `activation_score`/`status`/
`dominant_alphas` — proven on synthetic fixtures
(`test_16_disabled_leaves_activation_score_and_status_completely_
unchanged`, deliberately using a historical_mapping of `0.05` that would
fail every threshold, to prove the *absence* of records isn't just
"nothing to block") and on the real saved NVDA run (section 12: zero
records, activation/conflicts identical to the pre-exposure baseline).
Per task section 6, the run-level artifact still records
`effective_status="disabled"` at its top level for audit, even though
`records` is empty — the only place a disabled run's lifecycle remains
visible.

## 9. Artifact / API / UI consistency

`entity_alpha_exposures.json`: every record carries `owner`/
`approved_by`/`approved_at`/`configured_status`/`effective_status`
alongside the pre-existing fields (`test_18`). `structure_graph.json`'s
per-alpha embedded `entity_exposure` is byte-identical, field-by-field, to
the corresponding artifact record (`test_19`) — computed once, never
independently re-derived for the graph. `run_audit.json`'s
`entity_exposure` section gained the same five canonical fields at both
the top level and per-alpha, plus corrected backward-compatible mappings:
`seed_approval_status` now reads the ticker's `configured_status` string
(was: the old global `approval_status`), `enforcement_allowed` is now
`effective_status == "approved_gating"` (was: the old global boolean) —
both documented inline in code as explicit compatibility aliases
(`test_20`). The `GET /api/research/{run_id}/entity-exposures` endpoint
exposes the same fields via the DB round-trip (`test_21`).
`frontend/src/api/types.ts`'s `EntityExposure` interface gained the same
vocabulary (`EntityExposureLifecycleStatus = "draft_shadow" |
"approved_gating" | "disabled"`), all five new fields marked optional
(`?:`) so a historical payload predating them type-checks safely.
`AlphaCard.tsx` labels all three canonical states with John's exact
required copy ("Draft shadow — Displayed only — not applied to
Activation", "Approved gating — Participates in qualification",
"Disabled — Seed not participating"), reads `effective_status`/
`qualification_effect_applied`/`reason_codes` directly from the backend
(never recomputes a threshold), and falls back to the legacy `mode` field
without crashing when `effective_status` is absent (17/17 component tests
passing, including three new dedicated lifecycle-display tests and the
existing historical-payload-safety test). `npx tsc -b` and `npm run build`
both clean.

## 10. Real saved run (`e3eb3909-3744-4a02-9b32-b225cf6ef665`)

Present and complete (same run validated for B2 previously in this
session). Reprocessed fully offline (0 Provider calls): Activation v2
recomputed from the run's own saved `alpha_matches.json`/
`structured_agent_outputs.json`, with the run's own persisted
`run_timestamp`/`as_of`, and independently confirmed **byte-identical**
to the originally persisted `structure_graph.json` scores and to
`conflicts.json`'s admitted pairs/`main_conflict` — establishing a
trustworthy, faithful pre-exposure baseline (not a second, drifting
approximation). NVDA is genuinely one of John's six `approved_gating`
tickers, so this run exercises the real gated path, not just shadow.

| | draft_shadow | approved_gating | disabled |
|---|---|---|---|
| configured_status | approved_gating | approved_gating | approved_gating |
| effective_status | draft_shadow | approved_gating | disabled |
| records produced | 10 | 10 | 0 |
| activation scores unchanged vs. pre-exposure baseline | yes | yes | yes |
| activation statuses unchanged vs. baseline | yes | yes (qualification evaluated for 7/10 alphas; ceiling never bound below the existing status for this real evidence) | yes |
| `dominant_alphas` unchanged | yes | yes | yes |
| Conflict result identical to pre-exposure baseline | yes | yes | yes |
| `main_conflict` | A301\_\_A304 | A301\_\_A304 | A301\_\_A304 |
| B2 admissibility diagnostic identical to baseline | — | yes (checked explicitly) | — |

## 11. Targeted test results

- `tests/test_exposure_engine.py` (pure formula core, untouched) —
  **29/29 passed**, unchanged.
- `tests/test_exposure_rubric_contract.py` (separate, not-yet-wired
  contract; confirmed via `exposure/__init__.py`'s own docstring and a
  direct import-graph check that it never touches `seed_loader`) —
  **unaffected**, part of the 659-test baseline below.
- `tests/test_entity_alpha_exposure_productization.py` — **21/21
  passed** (rewritten for the per-ticker API; every original test's
  diagnostic intent preserved, see section 13).
- `tests/test_b3_entity_exposure_gated_states.py` (new) — **16/16
  passed** — the task's section 11 checklist items not already covered
  by the file above (seed contract exact-match/rejection cases,
  fail-closed approval completeness, env-var upgrade blocking, disabled
  invariants, artifact/graph/audit/API consistency, B1/B2 non-interference).
- `frontend/src/components/AlphaCard.test.tsx` — **17/17 passed** (3
  new: approved_gating display, disabled display, fail-closed
  gating-downgraded warning).
- Full frontend suite — **159/159 passed** (17 files); `npx tsc -b` and
  `npm run build` both clean.
- Broader exposure-adjacent baseline (replay, structured-output-shadow
  boundaries, agent-outputs API, artifact export, evidence integrity/
  stance, ticker-consistency audit, Week 4 persistence, ai-alpha-mapper,
  evaluation harness, semantic-artifact live pipeline, signal processing)
  — **659/659 passed**, identical to the pre-B3 baseline count captured
  before any change was made.
- `ruff check` on all 8 touched/new backend files — **clean**.

A real, in-flight regression was caught and fixed during this work, not
left for later: `week4_persistence.py`'s `_whitelist_entity_exposure`
uses an exact-set (`set(value) != allowed`) validator for the
`entity_exposure` sub-object embedded in the activation payload Week 4
persists — adding the five new record fields without also adding them to
this whitelist caused every real run through `run_research_request` to
fail at the `conflict_persistence` stage (silently logged, `status:
"partial"`). Found via the broader regression sweep (not the narrower
exposure-only suite, which never exercises this cross-module path),
root-caused to the exact line, and fixed by extending the existing
whitelist additively (the same pattern already used for B2's
`admissibility` field) — never by loosening the check.

## 12. Full regression

Two complete `pytest tests/ -q` runs (~9 minutes each, 3317 collected: 47
skipped + the rest), before declaring completion:

- **Run 1**: 4 failed, 3266 passed. Three were the known baseline
  (section below); the fourth was a **genuine, B3-caused regression**,
  root-caused rather than dismissed:
  `tests/test_week3_nvda_sanity.py::test_graph_is_not_converted_into_a_
  buy_sell_hold_conclusion` asserted the naive substring `"hold" not in
  json.dumps(graph).lower()`. NVDA reaching `approved_gating` for the
  first time on this fixture caused the (pre-existing, unmodified)
  `EXPOSURE_BELOW_REGIME_THRESHOLD` reason code to appear in the
  serialized graph for the first time — and "threshold" contains "hold"
  as a bare substring. Confirmed directly (every "hold" occurrence traced
  to that exact string, 12 times, one per alpha) before touching
  anything. This is a **false positive**, not a trading-advice leak: the
  test's own real intent (no buy/sell/hold *conclusion* language) is
  untouched by a threshold reason code. Fixed by switching to
  word-boundary regex matching (`re.search(rf"\b{term}\b", serialized)`),
  mirroring the exact pattern this codebase already uses for the same
  purpose elsewhere (`test_week4_golden_closure.py`'s
  `_BARE_TRADING_TERMS = re.compile(r"\b(buy|sell|hold)\b", re.IGNORECASE)`)
  — not a weakened check, a more precise one; the same false positive was
  always latently possible from any unrelated content containing
  "shareholder"/"stakeholder"/"household". Verified fixed in isolation
  (9/9 passed) before the second full run.
- **Run 2** (after the fix above, no other changes): 4 failed, 3266
  passed — the `test_week3_nvda_sanity.py` failure is gone (confirmed),
  but a *different*, unrelated test appeared:
  `tests/test_deepseek_reasoning.py::TestDeepSeekLiveStructuredOutput::
  test_v4_flash_returns_structured_output` — its own class name says
  "Live"; it opens a real HTTPS connection to `api.deepseek.com` with a
  real API key. It has zero import or call relationship to any file this
  task touched, did not appear in Run 1 or in this session's earlier B2
  full-suite baseline, and passed cleanly (14/14) when the same file was
  re-run in isolation immediately after — conclusive evidence of
  transient network flakiness, not a regression this task caused.

**Net result: zero new, reproducible, B3-caused failures.** One real
issue was found and fixed at its root cause (not masked); one unrelated,
non-reproducible, live-network flake was investigated and ruled out with
direct evidence rather than assumed away.

Known, pre-existing, unrelated failures (from the B2 report, still valid,
present in both runs):
`tests/structured_output_shadow/test_source_integrity.py::test_current_
semantic_components_match_approved_phase1_master_baseline` (documented
pre-existing). `tests/test_w5_demo_seed.py`'s two failures remain, by
explicit prior user decision, an intentionally-preserved product signal
(the approved NVDA demo fixture doesn't clear B2 admission) — unrelated to
B3 and not touched.

## Provider calls

**`PROVIDER_CALLS = 0`** throughout this entire task. No TradingAgents
rerun, no LLM call, no B1-50-evidence rerun. `seed_loader.py`/
`exposure_engine.py` import nothing network- or LLM-related (verified by
AST import-graph inspection, `test_25_exposure_module_never_imports_b1_
stance_or_b2_admissibility`).

## Answers to the task's explicit questions

1. **六组 seed 是否与 John 给出的值逐项一致？** Yes — exact, verified two
   independent ways (section 4).
2. **是否仍有旧 11-ticker draft 数据进入 active seed？** No — the six
   reissued tickers' old values are demonstrably different from John's new
   ones and are never used; the five non-reissued tickers remain
   `draft_shadow` (never `approved_gating`/active) with their unchanged
   old values (section 4).
3. **`draft_shadow` 是否完全不影响 Activation？** Yes — score, status, and
   dominant membership all byte-identical before/after, on synthetic
   fixtures and the real saved run (section 6, 10).
4. **`approved_gating` 是否只影响资格、不修改 numeric score？** Yes —
   `activation_score` is never written by this code path; only `status`
   may be capped downward, gated by the fail-closed approval check
   (section 7).
5. **`disabled` 是否完全不参与？** Yes — zero per-Alpha records, zero
   effect on Activation or Conflict, on both synthetic fixtures and the
   real saved run (section 8, 10).
6. **审批不完整能否被错误升级？** No — fails closed to `draft_shadow` with
   two stable reason codes, gating does not execute (section 7).
7. **B2 admitted conflict/evidence count 是否被 B3 意外改变？** No, on the
   real saved run and on a dedicated synthetic B2-focused test
   (`test_27_28`): `conflicts`, `main_conflict`, and every candidate's full
   `admissibility` diagnostic (including `bull_supporting_evidence_count`/
   `bear_supporting_evidence_count`) are byte-identical whether Exposure
   is absent, `draft_shadow`, or `approved_gating`, for the same
   underlying evidence.
8. **哪些旧字段为了兼容保留，何时可以清理？** `mode` (off/shadow/enforced)
   and `seed_approval_status` (now the ticker's `configured_status`
   string) on every exposure record; `enforcement_allowed` in
   `run_audit.json`'s `entity_exposure` section (now `effective_status ==
   "approved_gating"`). All three are read by `AlphaCard.tsx`'s fallback
   path for historical payloads and by nothing else load-bearing found in
   this codebase — they can be removed once every persisted/cached
   `entity_alpha_exposures.json`/DB row predating this task has aged out
   or been migrated, which is a product/ops decision outside this task's
   scope, not a code question.

## Files modified / created

**Modified**: `comqutor_alpha/exposure/seed_loader.py` (rewritten:
per-ticker lifecycle, fail-closed resolution),
`comqutor_alpha/exposure_engine.py` (per-ticker provenance fields on
records/artifact; formula/thresholds untouched),
`comqutor_alpha/graph_engine/pipeline.py` (one call site: pass ticker into
`resolve_exposure_mode`), `comqutor_alpha/api/routes_research.py`
(`entity_exposure_audit` section additively extended),
`comqutor_alpha/storage/db/exposure_persistence.py` (round-trip the five
new fields via the existing `provenance_json` column),
`comqutor_alpha/storage/db/week4_persistence.py` (whitelist extended — the
real bug described in section 11),
`comqutor_alpha/config/entity_alpha_exposure_seed_v0.1.yaml` (new
per-ticker schema, John's six values, five preserved drafts),
`comqutor_alpha/config/entity_alpha_exposure_seed_manifest_v0.1.yaml`
(narrowed to file-level identity, new seed hash),
`tests/test_entity_alpha_exposure_productization.py` (adapted to the new
per-ticker API), `tests/test_week3_nvda_sanity.py` (word-boundary fix for
the false-positive described in section 12), `frontend/src/api/types.ts`,
`frontend/src/components/AlphaCard.tsx`,
`frontend/src/components/AlphaCard.test.tsx`.

**New**: `tests/test_b3_entity_exposure_gated_states.py`, this report and
its JSON companion.

**Not touched**: B1 stance ontology/LLM semantic authority/deterministic
fail-soft rules, B2 supporting-evidence-count/ticker-specific-evidence/
admissibility thresholds, `ConflictScore` formula, main-conflict
arbitration, Activation v2 numeric weights, the Alpha taxonomy, §5.1
evidence provenance, `Week2LLMGateway`, the Evidence Fact Index
deduplication algorithm itself, `comqutor_alpha/exposure/rubric_
contract.py` (confirmed independent, never wired to `seed_loader`), and
`DOMINANT_EXPOSURE_THRESHOLD`/`REGIME_EXPOSURE_THRESHOLD` (still `0.30`/
`0.60` — `EXISTING_EXPOSURE_THRESHOLD_POLICY_REUSED`, not a new product
decision).

## Branch / HEAD / commit / push

`HEAD = b5837e80a4550fc35165d0013a8ef0f27ccb4c8f` (unchanged before and
after this task). `BRANCH = comqutor-structure-layer`. `COMMIT = NO`.
`PUSH = NO`.

## Completion

```
IMPLEMENTATION_COMPLETE = YES
FORMAL_ACCEPTANCE_PENDING = N/A -- John's approval was already supplied as
  this task's own input (seed_version=v0.1, approved_by=John, approval
  date=2026-08-11) and is encoded directly in the seed file; no further
  external sign-off is outstanding for this specific six-ticker batch.
  Any FUTURE ticker/seed addition remains subject to the same fail-closed
  approval-completeness gate this task implements.
```
