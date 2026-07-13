# COMQUTOR Alpha deterministic scoring specification

## Graph Coherence

The MVP uses the Development Plan simplification:

```text
GraphCoherence = min(100, valid_edge_count * 15 + covered_alpha_count * 10)
```

`GraphBuilder` merges duplicate node IDs and same source/target/type edges by
unioning all claim, evidence, agent, label, and Alpha provenance. Duplicate
edge weights use deterministic `max`; the serialized nodes and edges are
sorted. The networkx representation is a `DiGraph`; multiple relation types
on the same node pair are stored as a sorted `edge_records` list, preventing
DiGraph overwrite from losing provenance.

## Activation

For an Alpha with admitted evidence:

```text
Activation = MatchedEvidence * 0.35
           + AgentAgreement * 0.20
           + GraphCoherence * 0.25
           + Recency * 0.10
           + DirectionStrength * 0.10
```

All raw components are 0–100. The response stores raw value, weight, and
contribution separately.

- `MatchedEvidence`: average accepted match score for independent evidence.
- `AgentAgreement`: independent contributing agents / four.
- `GraphCoherence`: run graph score when the graph covers the Alpha.
- `Recency`: 100 at 0–1 days, 80 at 2–7, 50 at 8–30, otherwise 20.
- `DirectionStrength`: absolute net confidence after positive/negative signs.

Evidence is deduplicated by normalized evidence text before scoring. Repeated
same-origin prose from several agents therefore cannot be multiplied into
false consensus. All original provenance is still retained for audit.

An Alpha with no admitted evidence is forced to score 0 with `inactive` status;
global graph or recency values cannot activate it by themselves.

### Bands and exact boundaries

The decimal-safe intervals are:

- `[0, 30]`: `inactive`
- `(30, 50]`: `watch`
- `(50, 70]`: `active`
- `(70, 85]`: `dominant`
- `(85, 100]`: `regime_level`

Thus 30.1 is `watch`, 50.1 is `active`, 70.1 is `dominant`, and 85.1 is
`regime_level`. There are no gaps or overlaps.

## Exposure

```text
Exposure = historical_mapping * 0.50
         + current_evidence * 0.30
         + agent_confidence * 0.20
```

Exposure inputs and output are 0–1. If `(ticker, alpha_id)` has no supplied
seed, the engine returns `no_seed` with no historical or computed value. It
does not synthesize a seed. The current file contains only the NVDA values
explicitly provided in the Development Plan.

## Conflict

Only pairs declared by the loaded taxonomy are considered. Both activations
must have evidence and opposing positive/negative direction. The deterministic
formula is:

```text
ConflictScore = min(ActivationA, ActivationB)
              * contradiction_weight
              * average(mean_match_strength_A, mean_match_strength_B)
```

Bands use `[0,25] low`, `(25,50] medium`, `(50,75] medium_high`, and
`(75,100] high`. Both evidence sides, all formula inputs, and the explanation
are serialized.

Known product-definition blocker: the reviewed MSFT golden expectation names
`A102 vs A304`, while the mandatory taxonomy conflict list does not declare
that pair and supplies no contradiction weight. The detector intentionally
does not manufacture this seventh pair.
