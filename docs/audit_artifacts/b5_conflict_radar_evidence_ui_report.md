# B5 Conflict Radar Evidence UI — Implementation and Validation Report

Status:

```
B5 IMPLEMENTATION COMPLETE
B5 INVALIDATION CONTENT COVERAGE PARTIAL
B5 FORMAL PRODUCT OWNER ACCEPTANCE PENDING
```

`HEAD` re-verified below. No commit, no push. Every data structure, backend
computation, persistence path, API surface, and frontend UI region this
task requires is implemented and verified — for **every** Alpha. Only the
*product content* of Invalidation Conditions is partial: John supplied
exact, approved text for A101 only; every other Alpha honestly reports
"not yet product-approved" rather than fabricated content. That is
expected, per the task's own explicit instruction, not a defect — and does
not block declaring the implementation itself complete.

## 1. Preserved state

`git branch --show-current` → `comqutor-structure-layer`. `git rev-parse
HEAD` → `b5837e80a4550fc35165d0013a8ef0f27ccb4c8f` — unchanged before and
after this task, re-verified at report-writing time. No
`reset`/`restore`/`checkout`/`clean`/`stash` run at any point.
`PROVIDER_CALLS=0` and `SUBAGENTS=0` held throughout. No commit, no push.

## 2. The layering this task preserves

```
B1 = semantic authority
B2 = deterministic conflict admissibility authority
B4 = Alpha level classification authority
B5 = presentation and audit layer
```

B5 never re-judges Evidence semantics, never modifies `ConflictScore`,
never changes admitted/main conflict, never calls an LLM/Provider. Every
new backend module either reuses an existing function directly
(`conflict_admissibility.stance_for_alpha`'s pool-search pattern,
`conflict_detector._group_qualifying_claims_into_facts`'s Evidence Fact
grouping, `evaluate_conflict_admissibility`'s already-computed
`AdmissibilityResult`) or consumes its output read-only.

## 3. Audit before implementation (task section 3)

Performed before writing any code, using the required `rg` searches:

1. **`bull_evidence`/`bear_evidence`'s real, current structure**: built at
   API **read time** (not persisted) by `routes_research.
   _attach_conflict_evidence`, joining `bull_structure`/`bear_structure`'s
   `claim_ids` against persisted `alpha_matches` rows. This is a **raw,
   unfiltered, non-deduplicated per-claim list** — it included *any*
   qualifying claim regardless of B1 stance (`opposes_alpha`/
   `mentions_alpha`/`neutral_background` all leaked through) and never
   deduplicated near-paraphrase claims into Evidence Facts. This is
   exactly the stale behavior task section 4 required fixing.
2. **Raw claims vs. unique Evidence Facts**: confirmed raw — `conflict_
   detector._structure_block`'s own `evidence_facts` field (the *correct*,
   already-deduplicated view) exists but is entirely separate from
   `bull_evidence`/`bear_evidence`, and is unfiltered by stance either.
3. **B2's supporting evidence pool**: `conflict_admissibility.
   evaluate_conflict_admissibility` already stance-filters (`supports_
   alpha` only) and fact-groups each side internally, but only exposes
   counts/IDs via `SideAdmissibility` — never the full fact objects a UI
   needs. B5 reuses the *same* stance-filtering and grouping functions
   directly rather than re-deriving equivalent logic.
4. **B1 final stance storage**: `candidate_scores[].evidence_stance` on
   each `alpha_matches.json` record.
5. **`supports_counter_alpha`'s `counter_alpha_id`**: present exactly when
   that stance value is set — confirmed directly in real saved-run data.
6. **Persistence whitelist risk**: `week4_persistence._whitelist_conflict`/
   `_whitelist_candidate` rebuild an explicit, narrow object (not a raw
   pass-through) — the same risk class as prior B3/B4 findings. Confirmed
   by a failing round-trip test before any fix.
7. **Conflict API read path**: `get_persisted_conflicts` spreads the full
   reconstructed result — safe once persistence carries the field.
8. **Frontend's current display**: only a Main Conflict card, an admitted-
   conflicts list, and bare arbitration *counts* — candidate/suppressed/
   rejected pairs were never individually rendered at all.
9. **Candidate conflict API exposure**: `arbitration.candidate_
   evaluations[]` (with each pair's own `admissibility` detail) already
   flowed through the Conflicts API — the frontend TypeScript type simply
   never declared it and the UI never rendered it.
10. **Existing taxonomy invalidation content**: `alpha_taxonomy_v1.yaml`
    already has a per-Alpha `invalidation_conditions` field, including for
    A101: `[AI capex cuts, model demand slows, GPU oversupply]` — see
    section 8 below for why this is *not* treated as the formal approval
    source.

## 4. Bull/Bear Evidence contract

Both use the identical mechanism, scoped to their own alpha:

- Stance filter: `supports_alpha` only, relative to `bull_alpha_id`/
  `bear_alpha_id` respectively.
- Deduplication: unique Evidence Fact groups, via `conflict_detector.
  _group_qualifying_claims_into_facts` (the exact production grouping
  function, injected the same way `conflict_admissibility.py` already
  receives it) — never a raw claim count.
- Excludes: `opposes_alpha`, `mentions_alpha`, `neutral_background`,
  `supports_counter_alpha`.
- Each item carries: `evidence_fact_group_id`, `representative_claim_id`,
  `member_claim_ids`, `evidence_text`, `agents`, `source_agent_output_ids`,
  `target_alpha_id`, `evidence_stance`, `stance_method`, `evidence_stance_
  version`, `stance_confidence_band`, `ticker_specific`, `representative_
  match_score`.

Verified: raw duplicate paraphrase claims collapse to one Evidence Fact
(`test_a_raw_duplicate_paraphrase_claims_collapse_to_one_evidence_fact`);
every non-supporting stance is excluded (parametrized across `opposes_
alpha`/`mentions_alpha`/`neutral_background`); `supports_counter_alpha`
never directly counts as target support.

## 5. Counter Evidence routing

**Case A** (`opposes_alpha(target)`): a claim whose stance relative to a
conflict side's own alpha_id is `opposes_alpha` becomes Counter Evidence
against that alpha. **Case B** (`supports_counter_alpha`): a claim with
`counter_alpha_id` equal to the conflict's *other* side becomes Counter
Evidence against the side it was evaluated relative to, tagged with
`supports_counter_alpha_id`. An unrelated `counter_alpha_id` never
qualifies. `mentions_alpha`/`neutral_background` are excluded by
construction. Dedup key: `evidence_fact_group_id` + `counter_target_alpha_
id` (task section 6).

**Real design gap found and fixed**: the initial implementation searched
only the target alpha's own qualifying pool for Counter Evidence — this
missed task section 6's explicit "dual role" requirement (the *same*
claim simultaneously `supports_alpha` toward its own matched alpha *and*
`opposes_alpha`/`supports_counter_alpha` toward a *different* alpha via a
secondary `candidate_scores` entry), because a claim's qualifying-pool
membership is scoped by its own `matched_alpha`, not by every alpha its
`candidate_scores` mentions. Found via a failing synthetic test
(`test_b_same_fact_supporting_one_side_and_opposing_the_other_keeps_
both_roles`) *before* real-run verification. Fixed by searching the union
of both sides' already B2-quality-gated qualifying pools (never a third,
wider, unrelated-to-this-pair search) — then **independently reconfirmed
against real production data**: the real saved NVDA run's own PEG-
rebuttal claim (section 10 below) exhibits exactly this scenario.

## 6. Missing Evidence

Computed solely from B2's own already-computed `AdmissibilityResult` — no
new admissibility threshold:

| Reason code | Trigger |
|---|---|
| `INSUFFICIENT_SUPPORTING_EVIDENCE` | `supporting_evidence_count < 2` (reused `MIN_SUPPORTING_EVIDENCE_PER_SIDE`) |
| `NO_TICKER_SPECIFIC_SUPPORTING_EVIDENCE` | `ticker_specific_support_count < 1` (reused `MIN_TICKER_SPECIFIC_SUPPORT_PER_SIDE`) |
| `NO_ADMISSIBLE_SUPPORTING_POLARITY` | side has qualifying evidence of *some* polarity but zero `supports_alpha` — an additive, more specific diagnosis, never a replacement for the bare deficit above |

An admitted conflict's `missing_evidence` is always `[]` — this falls out
naturally from B2's own `ADMITTED` status requiring zero `reason_codes` on
both sides; no special-casing was needed. `ALPHA_SCORE_BELOW_THRESHOLD`
lives in a separate `qualification_gaps` list, never `missing_evidence`,
per the task's explicit instruction that a score shortfall is a
qualification concern, not an evidence-content one.

## 7. Invalidation Conditions

New registry: `comqutor_alpha/config/alpha_invalidation_conditions_v0.1.
yaml`, loaded by `comqutor_alpha/conflict_engine/invalidation_registry.
py`. Every entry carries `alpha_id`/`condition_id`/`condition_text`/
`source`/`version`/`approval_status`; an Alpha absent from the registry
(or present with `approval_status: not_defined`) returns an honest empty
result — never a fabricated guess.

**A101 — exact match verified** (`test_d_a101_conditions_match_johns_
text_exactly`, `test_d_a101_source_version_approval_status_correct`):

```
hyperscaler capex slows
GPU demand weakens
revenue growth decelerates
AI demand already priced in
```

`source: John`, `version: v0.1`, `approval_status: approved` — transcribed
verbatim from the task, never reworded or expanded.

**Every other Alpha**: `approval_status: not_defined`, `conditions: []`
(`test_d_unapproved_alpha_never_produces_fabricated_conditions`,
`test_d_registry_contains_no_other_approved_alpha_besides_a101`).

**`alpha_taxonomy_v1.yaml`'s own pre-existing `invalidation_conditions`
field for A101 — deliberately NOT treated as a formal approval source**:
it reads `[AI capex cuts, model demand slows, GPU oversupply]` — three
items, differently worded from John's four, and carries no `source`/
`version`/`approval_status` metadata at all. If that taxonomy field had
already been the formally-approved product source, John would not have
needed to re-supply a fresh, differently-worded, explicitly-attributed
version specifically for this task. This existing content is a plausible
future starting point for a Product Owner review, but is not read,
modified, or promoted to `approved` anywhere in this implementation —
recorded here as a `NON_AUTHORITATIVE_DRAFT_PROPOSAL`, per task section
10's explicit allowance, and nowhere else.

`test_d_invalidation_conditions_never_affect_conflict_score_or_admission`
confirms invalidation content is purely additive/display-only: an
otherwise-identical pair with no approved invalidation content at all
produces a byte-identical `ConflictScore`/`conflict_level`.

## 8. Artifact / DB / API consistency

`evidence_ui` is computed once inside `conflict_detector._evaluate_
candidate`, at the exact same call site and using the exact same
unconditional-computation pattern as `admissibility` — immediately after
it. It is attached to **both** the full conflict dict (`conflicts[]`/
`main_conflict`) **and** the audit item (`arbitration.candidate_
evaluations[]`), for every pair that reaches B2 evaluation (admitted or
suppressed) — never only for admitted ones. A pair rejected *before*
reaching B2 (missing evidence entirely, unresolved bull/bear role) has
neither `admissibility` nor `evidence_ui`, exactly mirroring the
pre-existing `admissibility` attachment contract.

**Real gap found and fixed**: `audit_item` never carried `bull_alpha_id`/
`bear_alpha_id` at all (even before B5) — without them, a UI rendering a
suppressed candidate's `evidence_ui` would have no reliable way to label
which side is bull vs. bear on a pair where `bull_evidence`/`bear_
evidence`/`counter_evidence` all happen to be empty. Added additively,
whitelisted with the same consistency check `_whitelist_conflict` already
uses (`{bull_id, bear_id} == {alpha_a, alpha_b}`).

**Persistence whitelist**: `week4_persistence._whitelist_evidence_ui` is a
new, fully-typed validator (every nested item — Bull/Bear/Counter Evidence
items, Missing Evidence items, Qualification Gap items, both Invalidation
entries — individually validated, every enum checked against the exact
set the producing module defines) wired additively (`if "evidence_ui" in
payload: ...`) into both `_whitelist_conflict` and `_whitelist_candidate`
— **never** via the pre-existing narrow tuple-based pass-through, so a
malformed value fails closed rather than silently persisting unchecked.
`test_e_malformed_evidence_stance_value_is_rejected_not_silently_dropped`
confirms this.

**API read path**: `get_persisted_conflicts` already spreads the full
DB-reconstructed result — no separate fix needed once persistence itself
carried the field correctly.

**Real, pre-existing frontend bug found and fixed** (discovered via visual
verification, section 11): `frontend/src/api/adapters.ts`'s
`adaptAlphaConflict`/`adaptConflictSideStructure`/`adaptConflictCandidate
Evaluation` each rebuild an explicit, narrow object literal — **not** a
spread of the validated payload. This was *already* silently dropping
several fields that shipped before this task ever started:
`bull_structure.evidence_facts` (meaning `ConflictSideEvidence`'s
per-Evidence-Fact card rendering had never actually activated in
production — every conflict card was always falling back to the raw
per-claim view) and all 13 Evidence Integrity Completion Sprint Track B
fields (`bull_raw_claim_count`/`bull_unique_fact_count`/
`bull_distinct_agent_count`/`bull_overlap_ratio`/`bull_fact_group_ids` and
their bear/shared counterparts — meaning `ConflictSideFactStats` had never
rendered a real count). Fixed comprehensively alongside the new B5 fields
(`admissibility`, `evidence_ui`, `bull_alpha_id`/`bear_alpha_id` on
candidate evaluations) with proper, fully runtime-validated adapter
functions for every one of them — TypeScript alone could not have caught
this, since every affected field is `?:` optional and an adapter silently
omitting an optional field type-checks perfectly.

## 9. Historical payload compatibility

`evidence_ui`/`admissibility`/`bull_alpha_id`/`bear_alpha_id` are optional
at every layer (classifier output → persistence whitelist → API) —
genuinely absent, never defaulted, for a payload predating this task.
`ConflictCard` shows an explicit "Counter Evidence, Missing Evidence, and
Invalidation Conditions are not available for this historical run" note
(never a silently-empty section that could be misread as a verified empty
result) and falls back to the pre-existing raw Bull/Bear evidence display,
now explicitly labeled "legacy — not B1-stance-filtered."
`test_e_historical_payload_without_evidence_ui_persists_and_reads_back_
without_fabrication` verifies the backend side of this contract.

## 10. B1 stance source of the real saved run

The specific rebuttal-shaped claim the task calls out by name:

```
claim_id: e3eb3909-3744-4a02-9b32-b225cf6ef665:bull_researcher:
          investment_debate_state.bull_history:claim:88
text: "Valuation risk is mitigated by a PEG of 0.60, 65%+ earnings
       growth, and a fortress balance sheet with $68 billion net cash."
```

- Relative to **A304** (its own `matched_alpha`): `evidence_stance =
  supports_alpha`, `stance_reason_codes = [RISK_ALPHA_ACTIVATION]`.
- Relative to **A101** (a secondary `candidate_scores` entry on the *same*
  claim): `evidence_stance = supports_counter_alpha`, `counter_alpha_id =
  A304`.
- `stance_method: null` for both → **`STANCE_SOURCE = deterministic
  baseline`** (`evidence_stance.deterministic.v1`) — the LLM upgrade was
  never attempted for this candidate. Not claimed as LLM-derived anywhere.

B5 displays this **exactly as saved, in both roles**: as A304's Bear
Evidence (a plausible-questionable classification the task itself flags —
B5 does not silently correct it), and as Counter Evidence against A101
("Supports counter Alpha A304"), confirmed directly in the live frontend
screenshot (section 11). No manual recorrection was made anywhere.

## 11. Frontend visual verification

Real backend API server (0 Provider calls) + Vite dev server + Playwright,
against the real saved NVDA run (persisted for live serving — see the
DB-gap note in section 12). Confirmed directly via screenshot:

- All five sections present on both admitted conflict cards (A301 vs A304
  main conflict; A101 vs A304).
- Counter Evidence correctly grouped "Against bull structure (A301)" /
  "Against bear structure (A304)", including the correct empty-state text
  when one side has none.
- Missing Evidence shows "No B2 evidence gaps identified." for both
  admitted pairs (as expected — see section 6).
- "What would invalidate the bull alpha — A301 (Revenue Expansion)?" /
  "...bear alpha — A304 (Multiple Compression)?" headings render clearly,
  each showing the honest "not yet product-approved" message.
- Main Conflict / Admitted Conflict badges visually distinct; the
  Candidate/Rejected pairs section shows a clear, separate "Not evaluated"
  (dashed card, pre-B2 rejection, e.g. `A001 vs A501` —
  `DIRECTION_ROLE_UNRESOLVED`) vs. "Candidate conflict" (e.g. `A304 vs
  A601`, reached B2, full score/count/reason-code detail shown) — the
  exact distinction task section 12 requires, confirmed never conflated.
- "Show all (N)" / "Show less" present and functional wherever a section
  exceeds 5 items; full data always available underneath.
- Long evidence text wraps within its card; `document.documentElement.
  scrollWidth === clientWidth` (no horizontal page overflow).
- No `BUY`/`SELL`/`HOLD` trading-recommendation language anywhere (a
  word-boundary check found only "expected to **hold**" inside real
  analyst evidence text — a legitimate English usage, not a recommendation
  — and zero literal `BUY`/`SELL` occurrences).
- Zero browser console/page errors during load.

This visual pass is exactly what surfaced the `adapters.ts` bug in section
8 — the unit/component tests alone did not, because they exercise
hand-built fixtures that bypass the real adapter function entirely.

## 12. Real saved run before/after table

`e3eb3909-3744-4a02-9b32-b225cf6ef665` (NVDA). `detect_alpha_conflicts`
called directly against the real, unmodified saved `activation_versions.
v2` payload and real `alpha_matches.json` — zero confound.

| Pair | Status | Bull facts | Bear facts | Counter facts | Missing gaps | Invalidation coverage |
|---|---|---:|---:|---:|---|---|
| A301__A304 | Admitted (main) | 12 | 6 | 1 | 0 | bull(A301): not_defined; bear(A304): not_defined |
| A101__A304 | Admitted | 4 | 6 | 4 | 0 | bull(A101): **approved** (John, v0.1); bear(A304): not_defined |

Confirmed for both pairs, before vs. after B5 wiring: `conflict_score`
byte-identical (32.0131 / 30.1956), `conflict_level` identical (both
`medium`), `admissibility` byte-identical, `main_conflict` identical
(`A301__A304`), supporting-fact counts byte-identical. B5 adds display
fields only.

**Note on the run's own DB state**: this run's database had zero rows for
its conflict data despite complete file artifacts — a previously-reported,
out-of-scope gap from the B2 diagnostic task (unrelated to B5). To drive
the live frontend visual verification in section 11 against real,
representative data, the same already-independently-verified-correct
conflict computation was persisted under this run's own authentic
`run_id` (required — the data's own embedded claim/agent-output identity
strings are bound to it, so a different `run_id` fails the detector's own
identity-mismatch check and evaluates nothing). This incidentally
populated that pre-existing gap with correct data; no file artifact was
touched, and no new/fabricated `run_id` was used.

## 13. Test results

- **New dedicated test file** `tests/test_b5_conflict_radar_evidence_ui.py`
  (sections A–G, driving the real `detect_alpha_conflicts` entry point
  end-to-end, never a hand-built `group_into_facts`): **36/36 passed.**
- **Targeted regression** (16 files spanning Conflict Detector, B2
  admissibility, persistence, structure correctness, NVDA/QQQ sanity,
  golden closure, run audit, artifact export, pipeline API, B3, B4):
  **480/480 passed.**
- **Full repository regression**: **3357 passed, 3 failed, 47 skipped, 69
  subtests passed**, 528.25s (0:08:48). All 3 failures verbatim-match the
  same already-documented, pre-existing/unrelated failures recorded during
  the B4 segment (`test_source_integrity.py::
  test_current_semantic_components_match_approved_phase1_master_baseline`;
  `test_w5_demo_seed.py::
  test_seed_is_complete_idempotent_and_reusable_without_provider`;
  `test_w5_demo_seed.py::test_only_nvda_and_qqq_are_seeded`). Passed count
  increased by exactly 36 versus the B4-segment baseline (3321 → 3357),
  matching the 36 new B5 tests precisely. **Zero new B5-caused failures.**
- **Frontend**: **165/165 passed** (unchanged count — coverage for the new
  UI came from the live real-run visual verification in section 11, which
  is what this task explicitly emphasizes, rather than additional
  synthetic component tests). `npx tsc --noEmit` clean. `npm run build`
  clean.
- **Ruff**: clean on all 6 touched/new backend files. 13 pre-existing
  findings remain in 6 unrelated, untouched files (identical set already
  documented in the B4 report) — out of scope.
- **Real bugs found and fixed**: (1) Counter Evidence's dual-role search
  scope (section 5); (2) the pre-existing `adapters.ts` narrow-
  reconstruction bug (section 8).

## 14. Not touched (explicit non-goals confirmed)

A3 Neutral/Unclassified cleanup, A4 Regression Runner, J2 regression
labels, J3 human semantic review, cold-start history fix, repository
cleanup, old artifact deletion, B1 live configuration repair, "John-20"
gold audit. Alpha taxonomy score thresholds, Activation formula, Exposure
formula, B2 formula, `ConflictScore`, Evidence stance prompt,
`Week2LLMGateway`, Evidence Fact Index grouping — none modified.

## 15. Files changed

**Created**: `comqutor_alpha/config/alpha_invalidation_conditions_v0.1.
yaml`, `comqutor_alpha/conflict_engine/conflict_evidence_ui.py`,
`comqutor_alpha/conflict_engine/invalidation_registry.py`,
`frontend/src/components/CandidateConflictCard.tsx`,
`frontend/src/components/ConflictEvidenceSections.tsx`,
`tests/test_b5_conflict_radar_evidence_ui.py`,
`docs/audit_artifacts/b5_conflict_radar_evidence_ui_report.md`,
`docs/audit_artifacts/b5_conflict_radar_evidence_ui_report.json`.

**Modified**: `comqutor_alpha/api/routes_research.py`,
`comqutor_alpha/conflict_engine/conflict_detector.py`,
`comqutor_alpha/storage/db/week4_persistence.py`,
`frontend/src/api/adapters.ts`, `frontend/src/api/types.ts`,
`frontend/src/components/ConflictCard.tsx`,
`frontend/src/pages/ConflictRadarPage.tsx`, `frontend/src/styles.css`.

## 16. Summary

`head`: `b5837e80a4550fc35165d0013a8ef0f27ccb4c8f`. `branch`:
`comqutor-structure-layer`. `commit`: NO. `push`: NO. `PROVIDER_CALLS`: 0
throughout.

```
B5 IMPLEMENTATION COMPLETE
B5 INVALIDATION CONTENT COVERAGE PARTIAL
B5 FORMAL PRODUCT OWNER ACCEPTANCE PENDING
```

Every data structure, backend computation, persistence path, API surface,
and all five UI regions (Bull/Bear/Counter/Missing Evidence, Invalidation
Conditions) are implemented and verified for every Alpha, against both
synthetic tests and the real saved NVDA production run — with zero change
to B1/B2/B3/B4's own authoritative results. Only A101 currently carries
Product-Owner-approved invalidation content; this is an honest, expected,
non-blocking content gap, not a defect, and not something this report
claims Product Owner acceptance on behalf of anyone.
