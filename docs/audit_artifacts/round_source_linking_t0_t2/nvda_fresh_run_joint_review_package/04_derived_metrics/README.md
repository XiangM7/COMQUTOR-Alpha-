# Derived metrics -- real inputs, versions, and where to find the formulas

All four files in this directory are copied verbatim from this run's real,
persisted export bundle -- nothing here is re-derived or re-computed.

- **`alpha_activations.json`**: Week-3 Activation score per Alpha.
  `formula_version = week3.activation.mvp_v1`
  (`comqutor_alpha/graph_engine/activation_scorer_v2.py`, constant
  `ACTIVATION_V2_WEIGHTS`). Each Alpha's `components` object inside this
  file shows the real per-component raw value, weight, and contribution
  (matched_evidence 0.35, agent_agreement 0.20, graph_coherence 0.25,
  recency 0.10, direction_strength 0.10) -- the actual input data this
  run's own activation scores were computed from, including the specific
  `claim_ids` and `evidence` strings that fed each Alpha's score.
- **`entity_alpha_exposures.json`**: Week-4 Exposure qualification layer.
  `formula_version = week4.exposure_score.mvp_v1`
  (`comqutor_alpha/graph_engine/...` exposure scoring + seed file). Each
  record's `provenance` object shows the real inputs (seed `historical_
  mapping`, this run's own `current_evidence`/`agent_confidence`, the
  blended `final_exposure`) and `reason_codes` explaining every
  qualification effect applied.
- **`conflicts.json`**: Week-4 Conflict detection/arbitration.
  `formula_version` and `activation_formula_version` are recorded at the
  top level of this file. `arbitration.candidate_evaluations` shows the
  real per-pair evidence audit (which claims were excluded from each side
  and why) that produced this run's "0 admitted, 8 rejected" outcome.
- **`structure_graph.json`**: the real structure graph (nodes/edges) this
  run's Activation/Conflict computations were run against, plus
  `graph_coherence_score` and its own formula/builder version fields.

No derived metric in this run is missing its version or its real input
data -- where a value came back `0.0` (e.g. `current_evidence` for every
Alpha in the Exposure layer), that `0.0` is the real computed value, not a
placeholder for a missing one; the distinction matters for review and is
preserved as-is throughout.
