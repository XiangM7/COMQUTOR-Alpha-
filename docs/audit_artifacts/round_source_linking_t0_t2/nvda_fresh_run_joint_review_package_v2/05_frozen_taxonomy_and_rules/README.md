# Frozen taxonomy and Alpha/stance classification rules actually used this run

- **`alpha_taxonomy_v1.yaml`**: the real, current working-tree taxonomy file
  (`schema_version: alpha_taxonomy_v1`, sha256 `18a0dc6b5de7bbae3541272fbd66fa1172e62eed172fd86e97a72e1a40d90972`) --
  defines all 10 canonical Alphas (A001/A003/A101/A102/A103/A201/A301/
  A304/A501/A601), their conflict pairs, and their factor/keyword
  definitions.
- **`alpha_classifier_prompt_v7.txt`**: the exact, real Alpha-classification
  LLM prompt instructions used for 800 of this run's real Provider calls
  (`prompt_version=week2.alpha_classifier.v7`, `prompt_identity_sha256=
  ac48723f15cf347590ad2cb175f76cd438dbc4181c7b781aa0cfffaafe589b95`,
  confirmed by direct count against this run's own
  `llm_semantic_calls.jsonl`). This is the single-claim classifier; this
  run never used `alpha_classifier_batch`, which remains untouched and
  uncovered by any of this round's verification.
- **Evidence/stance determination**: the Alpha/stance result this run's
  Activation and Conflict stages actually used is
  `evidence_stance.deterministic.v1` (the production default;
  `effect_mode=shadow`), confirmed by this run's own
  `evidence_stance_summary.classifier_version` field. An LLM stance
  classifier (`evidence_stance.llm_classifier.v3`) was also invoked 14
  times this run in shadow mode only (per PD-006/ADR-006, not yet approved
  for production semantic authority) -- it never affected this run's
  canonical Activation/Conflict outcome; see
  `evidence_stance_summary.stance_effect_applied=false` /
  `activation_scores_unchanged=true` / `conflict_outcomes_unchanged=true`
  in this run's own GET API response.
- Deterministic Alpha-matching rules (used as a diagnostic/counterfactual
  only, never as semantic authority, per the Alpha Mapper Authority
  Migration) live in `comqutor_alpha/structure_engine/claim_semantics.py`
  and `comqutor_alpha/structure_engine/ai_alpha_discriminator.py` in the
  main repository -- not duplicated here since the LLM classifier above is
  this run's actual semantic authority.
