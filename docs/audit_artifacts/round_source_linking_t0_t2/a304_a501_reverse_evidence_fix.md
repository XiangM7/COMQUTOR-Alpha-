# A304/A501 reverse-evidence fix (NVDA joint-review round 2)

## Root cause, confirmed by direct code trace

Two independent axes already exist in the frozen production design, correctly separated:
1. **Source->claim support** (`evidence_fact_index.select_supporting_alpha_claims`, frozen `QUALIFYING_RELATIONS = {"activation", "conditional", "mixed"}`) -- `risk_relief` is already, deliberately excluded from counting as supporting evidence.
2. **Claim->Alpha direction** (`activation_scorer_v2.DIRECTION_SIGNED_RELATIONS["risk_relief"] = -1.0`) -- a risk_relief claim already, deliberately pulls `direction_consistency` the opposing way.

**Neither axis was broken.** The defect was entirely upstream, in `comqutor_alpha/structure_engine/claim_semantics.py`'s text->relation classification (`_RECESSION_RELIEF_PATTERNS` for A501, `_VALUATION_RELIEF_PATTERNS` for A304): both pattern sets required the easing/cheapness wording in a narrow grammatical shape that several common, equally explicit real NVDA-run phrasings didn't match:
- "recession risk **is a** diminishing concern" (article between copula and adjective -- not covered)
- "recession risk **at 8% and** falling" (a quantitative aside between the risk noun and its easing verb -- not covered)
- "**PEG** of 0.48 is unusually **low**" / "**objectively cheap/undemanding** relative to growth" (a PEG-ratio or growth-vs-multiple cheapness argument -- an entirely different valuation-relief vocabulary than "multiple expansion"/"discount rates falling", not covered at all)
- "the bear's 'valuation risk' argument **isn't a valuation argument** at all" (an explicit rebuttal of a quoted risk framing -- not covered)

One phrasing (terse categorical/numeric framing with no easing-verb vocabulary, e.g. "-2.0pp on week; ... Demand-destruction tail removed") is **confirmed real and left unfixed** -- generalizing a regex from this one idiomatic example risks exactly the overfitting this project has previously been warned against; documented as an accepted, known gap, not silently absorbed.

## Fix

Added 2 new patterns to `_RECESSION_RELIEF_PATTERNS` and 3 new patterns to `_VALUATION_RELIEF_PATTERNS` in `claim_semantics.py`, each grammatically anchored to the specific real construction found (never a bare keyword window). No change to `QUALIFYING_RELATIONS`, `DIRECTION_SIGNED_RELATIONS`, the taxonomy, quality thresholds, or any other frozen contract. No new global "NONE" gate; no regex change outside these two pattern tuples.

## Verified -- real output, not just function docstrings

**6 of 7 flagged claims now correctly classify as `risk_relief`** (the 7th, the categorical-framing one, is the confirmed, documented, unfixed gap above), verified via the real, unmodified `alpha_relation()`/`recession_risk_is_relief()`/`valuation_risk_is_relief()` functions.

**Real counter-examples remain unaffected** (requirement: must not pass by excluding everything): 8 real `bear_researcher` claims from this same run that discuss valuation/PEG while pushing back on the "cheap" framing (e.g. "the bull's 'cheap' valuation is entirely a function of an untested estimate") all remain `relation=activation` (or an unrelated, untouched relation) -- confirmed individually, not assumed.

**Real, independent, frozen-input recomputation** of this run's actual A304/A501 scores (`docs/audit_artifacts/round_source_linking_t0_t2/nvda_034a0a60_a304_a501_relation_fix_recompute_20261002.json`, execution_id `nvda_034a0a60_a304_a501_relation_fix_recompute_20261002`) -- reads the real frozen `structured_agent_outputs.json`/`alpha_matches.json`, calls the real `score_alpha_v2()` with the original vs. corrected `relation` values, makes no Provider call, and does not write to or overwrite `outputs/runs/034a0a60-.../`:

| Alpha | score BEFORE | score AFTER | status BEFORE -> AFTER | evidence_count BEFORE -> AFTER |
|---|---|---|---|---|
| A304 (Multiple Compression) | 19.6667 | **0.0** | inactive -> inactive | 1 -> 0 |
| A501 (Recession Risk) | 51.0271 | **34.6677** | active -> **watch** | 6 -> 4 |

A304's entire diagnostic-v2 evidence base was reverse evidence; after the fix it correctly shows zero. A501 keeps real, still-qualifying recession-risk evidence (4 remaining claims) after the 2 reverse-evidence claims are excluded.

**Both reclassified-pool consistency**: `relation_for_match` (the real consumer) reads whichever of `eligible_candidates`/`top_candidates`/`candidate_scores` a record carries, in that order -- all three are populated identically by the real production Alpha Mapper from the same single `alpha_relation()` call, so this fix (made at that single source) reaches all three consistently in any future real run; the recomputation artifact patches all three to faithfully simulate that.

**Historical run integrity**: `outputs/runs/034a0a60-430e-41f8-8321-03a11389707a/` was not written to. No Fresh Run, no Provider call. The recomputation is clearly labeled as a fixed-input recomputation, not a new model-accuracy claim, and does not claim John's T3 acceptance.

**Tests**: `tests/test_a304_a501_reverse_evidence_fix.py` (14 new tests: 7 real-phrasing classification tests including the one confirmed-unfixed case, 6 real counter-example non-regression tests, 1 end-to-end score_alpha_v2 test proving the already-correct downstream exclusion mechanism actually receives the corrected classification). 187 tests pass across every directly-dependent suite (`test_qqq_a001_mapping_remediation.py`, `test_activation_scorer_v2.py`, `test_evidence_eligibility_unification.py`, `test_alpha_mapper_llm_authority.py`, `test_structure_integrity_lineage.py`, `test_p0_p1_evidence_correctness_fix.py`), zero regressions.

## Remaining, explicitly flagged ambiguity (not resolved, not unilaterally decided)

The medium-confidence AI_REVIEW opinions on competing-narrative/crowded-trade classification boundaries are reference material only this round -- no model/prompt change, no new regex gate, per the explicit scope limit.
