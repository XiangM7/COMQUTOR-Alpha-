# B2 Conflict Evidence Admissibility — Implementation and Validation Report

Status: **Implementation complete, wired end-to-end, and offline-tested**
(0 Provider calls throughout — no LLM, no network, at any point in this
task). `HEAD = b5837e80a4550fc35165d0013a8ef0f27ccb4c8f` unchanged
throughout. No commit, no push. Layered strictly on top of the existing,
unmodified Week 4 Conflict Core (`conflict_detector.py`,
`conflict_schema.py`, the taxonomy-declared canonical pair registry, the
Evidence Fact Index, and the now-complete B1 Evidence Stance) — this is not
a new Conflict engine.

## A. Existing (pre-B2) conflict candidate call path

`detect_alpha_conflicts(run_id, ticker, activation_payload, alpha_matches,
taxonomy=None)` → `_enumerate_canonical_pairs(taxonomy)` (six
taxonomy-declared undirected pairs) → per pair,
`_evaluate_candidate(alpha_a, alpha_b, contradiction_weight,
pair_reason_codes, ...)`, which: gathers each side's qualifying evidence
(`_gather_qualifying_evidence`, unchanged — quality gate, relation
resolution via `activation_scorer._relation_for_match`, match-score
validation), extracts each side's activation fields
(`_extract_activation_fields` — score/status/direction, unchanged), checks
the *old*, looser admission gate (`status ∈ ADMISSIBLE_STATUSES =
{"watch","active","dominant","regime_level"}`), resolves bull/bear
identity (`conflict_schema.resolve_bull_bear`, from each side's activation
`direction` alone), groups each side's qualifying claims into unique
Evidence Facts (`_group_qualifying_claims_into_facts`, delegating to the
shared `evidence_fact_index.group_evidence_candidates`), and — if every one
of those checks passes — builds the full `conflict` dict (bull/bear
structure, components, conflict_score, evidence_facts, etc.).

## B. Where John's B2 gate is inserted

At the very end of `_evaluate_candidate`'s "fully admitted" branch
(`conflict_detector.py:898-934`), strictly *after* the `conflict` dict
above is completely built (so every pre-B2 field — bull/bear identity,
activation scores, Evidence Fact groups, conflict_score — is already
final) and *before* that dict is allowed to be returned as an admitted
conflict:

```python
admissibility = evaluate_conflict_admissibility(
    bull_alpha_id=bull_id, bear_alpha_id=bear_id,
    bull_score=bull_fields.score, bear_score=bear_fields.score,
    bull_qualifying_claims=bull_qualifying, bear_qualifying_claims=bear_qualifying,
    alpha_matches=alpha_matches, ticker=ticker,
    group_into_facts=lambda claims: _group_qualifying_claims_into_facts(claims, run_id=run_id, ticker=ticker),
)
conflict["admissibility"] = admissibility.to_dict()

if admissibility.status != B2_ADMITTED:
    audit_item = _audit_item(alpha_a, alpha_b, "suppressed", list(admissibility.reason_codes), evidence_audit)
    audit_item["admissibility"] = admissibility.to_dict()
    return audit_item, None          # no `conflict` object is ever returned

audit_item = _audit_item(alpha_a, alpha_b, "admitted", [], evidence_audit)
audit_item["admissibility"] = admissibility.to_dict()
return audit_item, conflict
```

A candidate that fails B2 never has its `conflict` object returned at all
— not filtered out afterward, but never constructed as an output in the
first place. This was a deliberate design choice (see section K) driven by
a pre-existing DB persistence invariant.

## C. New module

`comqutor_alpha/conflict_engine/conflict_admissibility.py` (new file).
Public entry point: `evaluate_conflict_admissibility(*, bull_alpha_id,
bear_alpha_id, bull_score, bear_score, bull_qualifying_claims,
bear_qualifying_claims, alpha_matches, ticker, group_into_facts) ->
AdmissibilityResult`. `ADMISSIBILITY_VERSION = "week4.conflict_admissibility.b2.v1"`.
Pure function: no filesystem/DB/network/env/randomness/wall-clock reads,
matching the Conflict Detector's own purity contract.

## D. Existing functionality reused (never re-derived)

- **Bull/bear identity**: `conflict_schema.resolve_bull_bear` — called
  once by `conflict_detector.py` before B2 ever runs; B2 receives
  `bull_alpha_id`/`bear_alpha_id` as already-resolved parameters and never
  calls a resolver of its own.
- **Activation score**: `bull_fields.score`/`bear_fields.score` — the same
  `activation_score` field (0–100 scale) `_extract_activation_fields`
  already extracted from the run's activation payload. Never rescaled,
  never recomputed.
- **Evidence Fact Index**: `evidence_fact_index.group_evidence_candidates`,
  via the *same* `conflict_detector._group_qualifying_claims_into_facts`
  the detector already uses for its own `bull_facts`/`bear_facts` —
  injected into `conflict_admissibility.py` as the `group_into_facts`
  callback (partially applied with `run_id`/`ticker`) rather than
  imported, so B2 never duplicates that function's parameter threading.
  Applied to a *stance-filtered subset* of the already-qualifying claim
  pool — never a second grouping algorithm, never a widened/narrowed
  qualifying set.
- **Ticker-specificity**: `activation_scorer_v2._is_ticker_specific` — the
  real, existing, per-claim, whole-token-boundary text-match check. Called
  with `company_names=()`/`entities_by_claim={}`, the exact values real
  production Activation v2 already passes at its own call site
  (`graph_engine.pipeline.score_and_assemble_structure_graph`), so B2's use
  of it is behaviorally identical to production, not a new heuristic (see
  section J for the verification this required).
- **B1 stance**: `stance_for_alpha(record, alpha_id)` (new, in
  `conflict_admissibility.py`) mirrors `_relation_for_match`'s exact
  candidate-pool search pattern (`eligible_candidates`/`top_candidates`/
  `candidate_scores`), reading `evidence_stance` instead of `relation`. It
  reads the already-attached final field
  `evidence_stance_llm.apply_llm_stance_upgrade` writes; it never
  reclassifies, never calls an LLM, never branches on `stance_method`.

## E. Exact fields used for admission

Per side (bull, then bear — identical logic, named reason codes):

1. `score >= 50.0` (`ALPHA_SCORE_THRESHOLD`, exact boundary passes —
   `score < ALPHA_SCORE_THRESHOLD` is the only failing comparison).
2. `len(unique Evidence Fact groups among qualifying claims whose
   stance_for_alpha(...) == "supports_alpha") >= 2`
   (`MIN_SUPPORTING_EVIDENCE_PER_SIDE`).
3. `>= 1` of those unique facts has at least one member claim for which
   `activation_scorer_v2._is_ticker_specific(...)` is `True`
   (`MIN_TICKER_SPECIFIC_SUPPORT_PER_SIDE`).

All three must hold on **both** sides for `status = ADMITTED`; any single
failure on either side yields `status = CANDIDATE`. No other field
(`direction`, `alpha_relation`, `stance_method`, claim count irrespective
of dedup, activation `status` string) is consulted.

## F. Output contract

`AdmissibilityResult.to_dict()`:

```json
{
  "admissibility_version": "week4.conflict_admissibility.b2.v1",
  "status": "admitted | candidate",
  "reason_codes": ["..."],
  "bull_score": 56.08, "bear_score": 31.87,
  "bull_supporting_evidence_count": 1, "bear_supporting_evidence_count": 1,
  "bull_ticker_specific_support_count": 1, "bear_ticker_specific_support_count": 1,
  "bull_supporting_fact_group_ids": ["..."], "bear_supporting_fact_group_ids": ["..."]
}
```

Attached verbatim as `conflict["admissibility"]` (admitted path) or
`audit_item["admissibility"]` (candidate path) — never a second,
differently-shaped diagnostic object.

## G. Reason codes (closed vocabulary)

`ALL_REASON_CODES` (`conflict_admissibility.py:79-89`):
`BULL_SCORE_BELOW_THRESHOLD`, `BEAR_SCORE_BELOW_THRESHOLD`,
`INSUFFICIENT_BULL_SUPPORTING_EVIDENCE`,
`INSUFFICIENT_BEAR_SUPPORTING_EVIDENCE`,
`NO_BULL_TICKER_SPECIFIC_SUPPORT`, `NO_BEAR_TICKER_SPECIFIC_SUPPORT`,
`TICKER_SPECIFIC_EVIDENCE_UNVERIFIED`. Named per bull/bear rather than per
alpha-A/alpha-B, matching this codebase's existing bull/bear-structure
naming convention (`bull_structure`/`bear_structure`,
`bull_raw_claim_count`/`bear_raw_claim_count`) established by W4.1/Evidence
Integrity Completion. `TICKER_SPECIFIC_EVIDENCE_UNVERIFIED` is a
documented, currently-unreachable fail-closed escape hatch (see section J)
— never emitted by the current, verified-real ticker signal, kept as a
named vocabulary member per task section 9/13 so a future caller that
cannot verify ticker-specificity fails closed rather than silently passing.
Multiple reasons persist simultaneously when multiple conditions fail
(`test_p_multiple_simultaneous_failure_reasons_are_all_persisted`,
`tests/test_conflict_admissibility.py`).

## H. `stance_method` is never a gate

`stance_for_alpha` reads only `candidate_scores[].evidence_stance`; it
never reads or branches on `stance_method`. Confirmed by dedicated test
`test_o_stance_method_llm_vs_deterministic_fallback_count_identically`
(`tests/test_conflict_admissibility.py`): identical fixtures differing only
in `stance_method="llm"` vs `"deterministic_fallback"` produce byte-identical
`AdmissibilityResult`s.

## I. Deduplication is the existing Evidence Fact Index, not a new system

`bull_supporting_evidence_count`/`bear_supporting_evidence_count` are
`len(fact_summary.fact_group_ids)` — unique Evidence Fact groups, not raw
qualifying-claim counts. Proven by
`test_d_three_near_duplicate_claims_count_as_one_not_three`: three distinct
`claim_id`s, all `supports_alpha`, all individually qualifying, collapse to
exactly one supporting-evidence count because the shared, unmodified
`evidence_fact_index.group_evidence_candidates` recognizes them as
paraphrases of the same underlying fact (same result observed live in the
NVDA `approved_demo_outputs` fixture — A101's two "AI training demand
accelerating" claims from two different raw outputs collapse to one fact,
see section S).

## J. Ticker-specific signal: verified real (Case A), reused directly

The task flagged this as the one dependency requiring careful
re-verification, since a prior sprint found a *different* field
(`alpha_matches.json`'s `ticker_specific` key) was always `True`
(auto-appended-entity trap). Re-read, this task, from first principles:
`activation_scorer_v2._is_ticker_specific` (lines 224-249) is a **different,
real** function — token-boundary match of the ticker symbol (and, only if
supplied, resolved company names) against `record["claim"]`/`record["evidence"]`
text, with an explicit guard rejecting an auto-appended-ticker *entity* that
does not also appear in the claim text. Traced the real production call
site (`graph_engine/pipeline.py`): it always calls this function with
`company_names=()`, so the real-world operative check is pure
ticker-symbol-in-text matching. **Case A: a real signal exists — reused
directly, unmodified, with the exact same argument values production
already passes.** `TICKER_SPECIFIC_EVIDENCE_UNVERIFIED` is defined but
unreachable in the current wiring (documented in section G) as the
required fail-closed escape hatch, never invoked as a live heuristic.
Proven non-fake by `test_ticker_specific_signal_is_not_a_fake_always_true_field`
(`tests/test_conflict_admissibility.py`): claims mentioning a *different*
ticker/company ("AAPL"/"AMD") with otherwise-identical shape, stance, and
qualifying status correctly score `ticker_specific_support_count == 0`; a
same-shaped positive control (only the ticker token changed to the run's
own ticker) correctly scores `>= 1`. This test deliberately does **not**
default every fixture claim to ticker-specific=True (task section 9's
explicit warning) — most fixture claims across the whole new test suite are
built with plain, non-ticker-specific text unless a test is specifically
proving the ticker-specific path.

## K. A CANDIDATE conflict can never become `main_conflict`

`CANDIDATE_CONFLICT_CAN_BE_MAIN = NO`, and not merely by a filter — **by
construction**. `_assemble_result`'s `main_conflict = conflicts[0] if
conflicts else None`, and `conflicts` is built exclusively from
`admitted_conflicts`, which only ever receives a candidate's `conflict`
object when `_evaluate_candidate` returns a non-`None` second value — which
section B shows happens *only* when `admissibility.status == ADMITTED`. A
CANDIDATE-status pair's `conflict` object (with its `conflict_score`) is
never returned by `_evaluate_candidate` at all, so it cannot appear in the
list `_conflict_sort_key` ranks, regardless of how high that score would
have been. This was a deliberate design decision, not an accident: an
earlier draft considered filtering `main_conflict` selection independently
of which candidates enter `conflicts`, but `storage/db/week4_persistence.py`'s
`_whitelist_conflict()` enforces a pre-existing, hard invariant
(`main_conflict == conflicts[0]` exactly, `(outcome=="admitted") ==
has_conflict_entry`) that any independent-filtering approach would have
violated for every real conflict-bearing run (`WEEK4_CONFLICT_DATA_INCONSISTENT`).
Restructuring so B2-failing candidates never produce a `conflict` object in
the first place satisfies John's requirement with zero risk to that
existing DB invariant. Proven by
`test_m_candidate_conflict_can_never_become_main_conflict_regardless_of_score`
(`tests/test_conflict_admissibility.py`): a deliberately strong-looking
candidate (activation 95/95, visible in its own `admissibility.bull_score`/
`bear_score`) loses to a modest admitted pair (51/51); and by
`test_n_zero_admitted_conflicts_main_is_none_and_candidates_are_preserved`:
when every declared pair fails B2, `main_conflict is None`, `conflicts ==
[]`, and every candidate remains fully visible in
`arbitration.candidate_evaluations` with its own admissibility diagnostic
— never silently deleted.

## L. `conflict_count` vs. the two new explicit counts

`conflict_count`'s existing meaning (`routes_research.py`) is, and always
was, `len(conflict_payload["conflicts"])` — the admitted-conflicts list.
Since B2, that list only ever holds B2-admitted conflicts, so
`conflict_count` **is already** `admitted_conflict_count`; no existing
field silently changed meaning. Two new, explicit, additive fields were
added rather than overloading it further:

- `admitted_conflict_count` — a same-named, same-source alias of
  `conflict_count`/`arbitration.admitted_count`, added at the top level of
  `run_audit.json` (`routes_research.py`) and of the conflicts export
  (`artifact_export.extract_conflicts_export`).
- `candidate_conflict_count` — new: taxonomy-declared pairs that reached B2
  evaluation but were denied (`admissibility.status == "candidate"`), a
  **strict subset** of the pre-existing `suppressed_count` (which also
  includes pairs suppressed for pre-B2 reasons — missing evidence, below
  the *old* activation threshold, unresolved bull/bear direction — that
  never reach B2 evaluation at all and so carry no `admissibility` block).

`_conflict_summary_section` (`routes_research.py`) additionally now
attaches the full `admissibility` diagnostic to each `per_pair` entry
(verbatim, never recomputed), and `extract_conflicts_export`
(`artifact_export.py`) additively exposes `candidate_conflicts` (the list
of denied-but-evaluated pairs) alongside the two new counts.

## M. `ConflictScore`/ranking formula: unchanged

`CONFLICT_SCORE_UNCHANGED = YES`, `MAIN_CONFLICT_RANKING_FORMULA_UNCHANGED
= YES`. `conflict_score = min(activation_a, activation_b) ×
contradiction_weight × evidence_strength` and `_conflict_sort_key`
(conflict_score desc, evidence_strength desc, minimum_activation desc,
canonical id asc) are byte-identical to before B2
(`test_conflict_evidence_fact_integration.py::test_conflict_score_formula_and_registry_are_unchanged`,
verified again with B2-satisfying fixtures this task). B2 never merges
with, weights into, or reorders by admissibility — it is a hard pass/fail
gate strictly upstream of ranking; the existing score only ever ranks
*among already-B2-admitted* conflicts (section K).

## N. Single computation, multiple consumers (no recomputation)

`admissibility` is computed exactly once, inside
`conflict_detector._evaluate_candidate` (section B). Every downstream
consumer — `storage/db/week4_persistence.py` (`_CANDIDATE_FIELDS`/
`_CONFLICT_FIELDS` both extended with `"admissibility"`, the only DB schema
change required), `artifact_export.extract_conflicts_export`,
`routes_research._conflict_summary_section`/`build_run_audit_payload`, and
the `/conflicts` API (`get_persisted_conflicts`, which spreads the DB
reconstruction verbatim) — reads that same object back; none re-derives
it. Proven end-to-end by
`tests/test_b2_admissibility_integration.py::test_b2_result_is_computed_once_and_identical_across_detector_db_and_export`,
which asserts the admitted A/B pair's and the denied C/D pair's
`admissibility` dicts are `==` across the in-memory detector result, the
DB round-trip, the artifact export, and the run_audit conflict summary.

## O. Architecture Replay / Provider calls

`PROVIDER_CALLS = 0`. `conflict_admissibility.py` imports nothing from any
LLM/provider/gateway module; its only imports are
`activation_scorer_v2._is_ticker_specific` and
`structure_engine.evidence_stance.SUPPORTS_ALPHA` (a plain string
constant). B2 runs unconditionally as part of the existing, already-replay-safe
`detect_alpha_conflicts` call — Architecture Replay's own 0-Provider-call
contract is untouched; B2 works identically during replay using whatever
final stance data the replayed run's `alpha_matches` already carries.

## P. Test results

- `tests/test_conflict_detector.py` — **146/146 passed** (fixtures updated
  to carry two qualifying claims per side and B2-clearing scores/stance/
  ticker text where a test's original intent required an admitted
  conflict; every edit preserves that test's original diagnostic purpose —
  see section Q).
- `tests/test_week4_persistence.py` — **72/72 passed**.
- `tests/test_week4_nvda_conflict_sanity.py` — **8/8 passed** (rewritten to
  assert the honest CANDIDATE outcome this real fixture now produces).
- `tests/test_week4_qqq_conflict_sanity.py` — **8/8 passed** (same).
- `tests/test_conflict_evidence_fact_integration.py` — **7/7 passed**
  (fixtures additively enriched with a second, ticker-specific,
  supports_alpha claim per side so each test's pre-B2 Evidence-Fact-Index
  assertions remain reachable; per-fact assertions retargeted at the
  specific fact group under test rather than aggregate/positional indexing
  so an added, unrelated fact cannot dilute what was proven).
- `tests/test_week4_golden_closure.py` — **8/8 passed** (NVDA/QQQ golden
  cases rewritten to the honest CANDIDATE/no-admission outcome; MSFT
  blocker guard untouched and still passing).
- `tests/test_conflict_admissibility.py` — **18/18 passed** (new; the 16
  lettered cases plus the dedicated ticker-signal-is-not-fake test).
- `tests/test_b2_admissibility_integration.py` — **1/1 passed** (new; the
  required focused end-to-end integration test).
- Consumers of the newly-extended fields —
  `tests/test_artifact_export_and_api.py`, `tests/test_data_sanity_api.py`,
  `tests/test_run_audit_v2.py`, `tests/test_structure_correctness_sprint.py`
  — **75/75 passed** unchanged (additive dict keys only).
- **Total B2-relevant regression: 343/343 passed.**
- `ruff check` on all 17 touched/new files: **clean, 0 errors** (one
  import-order autofix applied to the two new test files; no logic
  change).

### P.1 Full repository-wide sweep (`pytest tests/ -q`, 3301 collected)

Run to completion after this report's first draft (536.86s — slow because
an unrelated, pre-existing test opens a **real** network connection to
Yahoo Finance, `py-yfinance`, confirmed via `lsof`; independent of B2 and
of this task's "0 Provider calls" constraint, which governs LLM/model
provider calls — `conflict_admissibility.py` itself imports nothing
network-related, section O). Result: **7 failed** on the first pass. Each
was individually investigated (never assumed unrelated):

- `tests/structured_output_shadow/test_source_integrity.py::test_current_semantic_components_match_approved_phase1_master_baseline`
  — pre-existing, predates this task, already documented as unrelated in
  `docs/audit_artifacts/b1_llm_evidence_stance_upgrade_report.md`. Not
  touched.
- **4 genuine B2 gaps missed by the conflict-focused regression above**,
  because they live in files this task had not previously identified as
  conflict-relevant. Investigated and fixed with the same established
  patterns as section Q (additive claims to legitimately clear B2 where a
  test's core scenario allows it; honest assertion rewrites where a real,
  shared, "not modified" fixture no longer clears B2):
  - `tests/test_week4_pipeline_api.py::test_pipeline_happy_path_completes_week1_through_4`
    and `::test_conflicts_api_survives_deleted_local_run_directory` — both
    asserted `main_conflict["conflict_id"] == "A101__A304"` against
    `test_week3_nvda_sanity._nvda_offline_outputs()`, the same fixture
    `test_week4_nvda_conflict_sanity.py` already documents as B2-CANDIDATE,
    not admitted. Rewritten to assert the honest `None` outcome (with the
    DB-survives-deletion test additionally asserting all 6 pairs are still
    present in the reconstructed `candidate_evaluations`, proving the
    reconstruction itself is intact, not merely empty).
  - `tests/test_activation_scorer_v2.py::test_mutation_conflict_formula_min_to_max_still_fails_existing_tests`
    — a min()-vs-max() conflict-score-formula mutation test with one
    qualifying claim per side and no stance data. Fixed additively (a
    second, distinct, ticker-specific, `supports_alpha` claim per side) —
    except A304's hand-fixed `activation_score` also had to move from
    `40.0` to `55.0` (still clearly the lower of the two, preserving the
    exact min()-vs-max() distinction the test proves) since 40.0 sits
    below B2's own 50.0 threshold, which is a real, correct B2 constraint,
    not a fixture-volume issue this test's original design anticipated.
  - `tests/test_evidence_stance_integration.py::test_29_conflict_evidence_audit_carries_stance_via_used_in_conflict`
    — asserted `used_in_conflict=True` existed against the shared
    `approved_demo_outputs("NVDA")` fixture, which (section S) no longer
    has an admitted conflict. Rewritten to assert the honest, current
    outcome (`used_in_conflict=False` for every record on this real run),
    plus one new synthetic companion test
    (`test_29b_conflict_evidence_audit_used_in_conflict_flag_can_be_true`)
    added so the flag's positive path (it genuinely responds to an
    admitted conflict's `bull_fact_group_ids`/`bear_fact_group_ids`, not
    merely always `False`) remains directly, independently verified.
- **2 failures left deliberately unfixed, reported not patched**:
  `tests/test_w5_demo_seed.py::test_seed_is_complete_idempotent_and_reusable_without_provider`
  and `::test_only_nvda_and_qqq_are_seeded`, both failing with
  `NVDA_MAIN_CONFLICT_NOT_ARBITRATED` from `scripts/seed_w5_demo.py`. This
  is materially different from every other fixture-staleness fix above:
  `seed_w5_demo.py` **deliberately, by design**, requires NVDA's local demo
  case to show an admitted `A101__A304` main_conflict (with full bull/bear
  traceability), as the intentional complement to QQQ's demo case, which
  the script already explicitly allows to show zero admitted conflicts
  (pre-existing comment: "the deliberately thin QQQ fixture... legitimately
  admits zero conflicts... must still be arbitrated"). Under B2, NVDA's
  approved fixture no longer clears admission (same root cause as
  section S), which genuinely breaks this asymmetric, intentional demo
  design — not a stale pre-B1/B2 assumption safe to reassert around. This
  is a real product question (should the demo fixture be enriched, should
  a different ticker anchor the "shows a conflict" demo case, should the
  requirement be relaxed?), not a code-correctness question, and per this
  task's own repeated instruction not to tune results to look prettier, it
  was surfaced rather than silently resolved. **Explicitly confirmed with
  the user**, who selected: leave `scripts/seed_w5_demo.py` and
  `tests/test_w5_demo_seed.py` untouched, and leave these two tests
  honestly failing as a visible, documented signal for separate follow-up.
  Neither file was modified.

**Final full-sweep result after the above fixes: 3 failed (1 pre-existing
unrelated + 2 deliberately-left-failing by explicit decision), 3251
passed, 47 skipped** (3246 originally-passing + 4 flipped from fail to
pass + 1 new companion test, computed from the verified per-file delta
above rather than a fresh full re-run, to avoid a second ~9-minute
network-bound sweep once every individual file was independently
re-verified passing).

## Q. Pre-existing tests repaired — what and why

~28 tests in `test_conflict_detector.py` and ~4 payload helpers in
`test_week4_persistence.py` were built (pre-B1/B2) with one qualifying
claim per side and no B1 stance/ticker-specific text, so they no longer
clear B2's stricter (correct, intended) per-side minimum. Every one of
these was individually reviewed and fixed by either (a) adding one
additional, genuinely distinct, ticker-specific, `supports_alpha` claim so
the test's original scenario is preserved and now also clears B2 (the
majority), or (b) — in the one case where a real fixture's real,
deterministic evidence genuinely does not clear B2
(`test_real_nvda_w41_to_w42_persistence_sanity`, and the four
sanity/golden/integration files listed in section P) — rewriting the
assertions to honestly reflect the current, correct CANDIDATE/no-admission
outcome, per this task's own explicit instruction (section 23): never tune
upstream stages, never inflate a fixture, to force a prettier result. Every
edit was checked to confirm it preserves, never weakens, what that specific
test originally proved (e.g. a "watch-status" test's activation score was
raised from 35 to 50 while its asserted `status` stayed `"watch"`, so it
still proves what it always proved, just now also above B2's threshold).

One genuine bug in this task's own new code was caught this way, not
introduced and left unnoticed: `conflict_admissibility.py`'s claim-id index
initially used raw (non-whitespace-normalized) `claim_id` values, which
`test_exact_duplicates_are_order_independent_and_audited_once`'s
whitespace-padded duplicate-claim-id scenario correctly failed against.
Fixed by normalizing the key the same way
`conflict_detector._gather_qualifying_evidence`/`_canonicalize_alpha_matches`
already do (`" ".join(str(record.get("claim_id") or "").split())`).

## R. New dedicated tests

`tests/test_conflict_admissibility.py` — one test per lettered case in the
task spec (full pass; score just below threshold; single insufficient
fact; three-duplicate-collapse; opposes/mentions/neutral_background/
supports_counter_alpha each fail to count; mixed 2-supports/3-opposes/
4-mentions evidence counts as 2; zero ticker-specific support; one-side-only
ticker-specific; exact boundary at 50 (and just below at 49.999);
stance_method neutrality; multiple simultaneous reasons persisted; the
dedicated not-a-fake-ticker-signal test with a same-shaped negative and
positive control) plus the two main-conflict-arbitration cases
(candidate-cannot-become-main; zero-admitted-conflicts) evaluated through
the real `detect_alpha_conflicts`, since those are arbitration properties
across multiple declared pairs, not single-pair admissibility.
`tests/test_b2_admissibility_integration.py` — the required focused
end-to-end test (section N).

## S. Real saved run inspected

Per this task's own "do not manufacture a prettier result" instruction
(section 23/25), the real offline NVDA fixture already exercised by
`test_real_nvda_w41_to_w42_persistence_sanity`
(`tests/test_week3_nvda_sanity._nvda_offline_outputs()`, run through the
real deterministic Week 1–3 pipeline, 0 Provider calls) was used as the
"one real saved run" inspection, re-verified fresh for this report:

- `declared_pair_count = 6`, `admitted_count = 0`, `suppressed_count = 3`,
  `rejected_count = 3`. `main_conflict = None`.
- Two pairs reach B2 evaluation and are denied as CANDIDATE:
  - `A101-A304`: `reasons = [INSUFFICIENT_BULL_SUPPORTING_EVIDENCE,
    BEAR_SCORE_BELOW_THRESHOLD, INSUFFICIENT_BEAR_SUPPORTING_EVIDENCE]`.
    A101's two "AI training demand accelerating" claims (from two
    different raw agent outputs) genuinely near-paraphrase-collapse to one
    unique Evidence Fact (section I) — one short of B2's minimum — and
    A304's activation score (31.87) is below 50.
  - `A304-A601`: `reasons = [BULL_SCORE_BELOW_THRESHOLD,
    INSUFFICIENT_BULL_SUPPORTING_EVIDENCE, NO_BULL_TICKER_SPECIFIC_SUPPORT,
    BEAR_SCORE_BELOW_THRESHOLD, INSUFFICIENT_BEAR_SUPPORTING_EVIDENCE]`.
  - The remaining four declared pairs (`A001-A501`, `A003-A501`,
    `A301-A304`, `A501-A601`) fail *before* ever reaching B2 (old
    `BELOW_ACTIVATION_THRESHOLD`/missing-evidence/unresolved-direction
    reasons), so B2 correctly never evaluates them and attaches no
    `admissibility` block.
- The separate `approved_demo_outputs("NVDA")`/`("QQQ")` golden-closure
  fixtures were also inspected live (section P); both show the identical
  qualitative pattern — real evidence volume, built before B1/B2 existed,
  is one unique fact short of B2's per-side minimum on at least one side of
  their previously-admitted pair.

This is a real, honest, unmodified-fixture finding, not a defect in B2:
this is what John's stricter bar looks like against real, current
evidence volume for these specific (pre-B1/B2, Week-3-vintage) offline
fixtures. No upstream stage was tuned to produce a different result.

## T. Files modified / created

**New**:
- `comqutor_alpha/conflict_engine/conflict_admissibility.py`
- `tests/test_conflict_admissibility.py`
- `tests/test_b2_admissibility_integration.py`
- This report.

**Modified** (all additive; no existing field's value or meaning changed
for any request that predates B2, except that `conflicts`/`main_conflict`
now additionally require B2 admission, which is this task's entire
purpose):
- `comqutor_alpha/conflict_engine/conflict_detector.py` — B2 import;
  admissibility evaluation + branch at the end of `_evaluate_candidate`;
  `evaluate_conflict_pair`/`_evaluate_candidate` signatures extended with
  optional `run_id`/`ticker` (defaulted to `""`, matching prior behavior
  for any caller that omits them).
- `comqutor_alpha/storage/db/week4_persistence.py` — `_CANDIDATE_FIELDS`/
  `_CONFLICT_FIELDS` extended with `"admissibility"`.
- `comqutor_alpha/api/artifact_export.py` — `extract_conflicts_export`
  additively returns `candidate_conflicts`/`admitted_conflict_count`/
  `candidate_conflict_count`.
- `comqutor_alpha/api/routes_research.py` — `_conflict_summary_section`
  additively attaches `admissibility` per pair and
  `admitted_conflict_count`/`candidate_conflict_count`;
  `build_run_audit_payload` additively surfaces the same two counts at the
  top level alongside the unchanged `conflict_count`.
- `tests/fixtures/week4_conflict_cases.py` — `match_record` gains
  `evidence_stance`/`ticker_specific_text` parameters, defaulted to
  already-B2-friendly values (`"supports_alpha"`/`"NVDA"`) following this
  file's own established "happy path by default" convention; never
  overrides an explicit `evidence=...`.
- `tests/test_conflict_detector.py`, `tests/test_week4_persistence.py`,
  `tests/test_week4_nvda_conflict_sanity.py`,
  `tests/test_week4_qqq_conflict_sanity.py`,
  `tests/test_conflict_evidence_fact_integration.py`,
  `tests/test_week4_golden_closure.py` — see sections P/Q.
- `tests/test_week4_pipeline_api.py`, `tests/test_activation_scorer_v2.py`,
  `tests/test_evidence_stance_integration.py` — discovered via the full
  repository-wide sweep (section P.1), fixed with the same established
  patterns; not part of the originally-scoped conflict-focused regression.

**Deliberately not touched, left honestly failing** (section P.1, explicit
user decision): `tests/test_w5_demo_seed.py`,
`scripts/seed_w5_demo.py` — a real, still-live product requirement
(NVDA's local demo case must show an admitted conflict) that the approved
NVDA demo fixture's real evidence can no longer satisfy under B2; a
product decision, not a code-correctness fix, so it was surfaced rather
than silently resolved either direction.

**Not touched**: the B1 prompt, the B1 stance ontology/vocabulary,
`evidence_stance.py`, `evidence_stance_llm.py`, `deterministic.v1`, §5.1/§5.2
Alpha scoring, §5.3, Activation scoring (`activation_scorer.py`/
`activation_scorer_v2.py` — only *read* via the already-existing
`_is_ticker_specific` import, never modified), Entity Exposure, B3, B4, B5,
A3, A4, the Conflict UI, and the existing `ConflictScore`/ranking formula
(section M).

## U. Branch / HEAD / commit / push

`HEAD = b5837e80a4550fc35165d0013a8ef0f27ccb4c8f` (unchanged before and
after this task, re-verified at report-writing time). `BRANCH =
comqutor-structure-layer`. `COMMIT = NO`. `PUSH = NO`. No
`git reset/restore/checkout/clean/stash` used at any point. No LLM call
made. No 6-ticker A4/J2 regression run (out of scope per task's explicit
STOP conditions).
