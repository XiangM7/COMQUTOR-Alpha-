# v0.2 Final Alpha Adjudication Policy (FROZEN)

**Status: `POLICY_FROZEN`.** This governs adjudication of the 150-sample final independent set. Frozen *before* any claim/evidence text is exposed.

Adjudicator mode: `INDEPENDENT_EXTERNAL_LLM_ADJUDICATION`

## What the Adjudicator May See

- Blinded `sample_id` / sample number
- Ticker
- Opaque `run_id`
- Claim
- Evidence
- The frozen canonical Alpha taxonomy (`alpha_id`, `name_en`, `core_thesis`)
- The frozen adjudication rubric (`v0_2_alpha_human_adjudication_rubric.md`)

## What the Adjudicator Must Never See

Candidate 3 prediction, any COMQUTOR `matched_alpha_id`, mapper score, `plausible_alphas`, system confidence, system explanation, Provider result, Candidate 1 result, Candidate 2 result, Candidate 3 result, production prompt worked examples, or historical expected labels for the same sample.

## Exclusion Rule

A non-null `ambiguity_flag` excludes that sample from the accepted scoring population — identical to the development-set discipline.

## Replacement Rule

If a final sample requires replacement, the next replacement is drawn **deterministically** from the remaining untouched reserve samples in their already-frozen reserve order. No hand-picking.

- Reserve samples already consumed by the development set (rounds 1–2): `nh-reserve-001` through `nh-reserve-018` (18 total — verified directly from `v0_2_alpha_dev_replacement_log.json`, not assumed).
- **Remaining untouched reserve samples: 32.**
- Next untouched reserve sample in frozen order: `nh-reserve-019`.

## Sequencing Requirement

Final Gold labels must be frozen **before** Candidate 3 is ever executed against the final set. This task performs no adjudication and no Candidate 3 execution — it prepares the blind packet only.

## Taxonomy

Uses the exact existing canonical `alpha_taxonomy_v1.yaml` `core_thesis` definitions verbatim. No taxonomy wording is modified.
