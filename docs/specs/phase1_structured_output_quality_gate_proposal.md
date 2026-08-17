# Phase 1 Structured Output Quality Gate Proposal

Status: mixed provenance. Safety gates labeled `APPROVED_PROJECT_DECISION` are binding for Shadow admission. Semantic targets labeled `PROPOSED_EXTENSION` require independent approval before cutover. Phase 1A passing does not show those targets were achieved.

## `SOURCE_FROZEN`

Development Plan v1.0 §5.1 requires Agent natural language to become the standard Claim schema; mandatory identity/Claim/Evidence fields; factors best effort; entities possibly empty; confidence in `[0,1]`; and safe failure that does not propagate malformed JSON or crash the run. §12 states “JSON output failure rate <10%” and “golden-case alpha-match accuracy ≥80%.” The latter is an overall downstream product threshold, not a measured Phase 1A Claim-quality result. The Plan does not specify numeric human accuracy targets for Claim boundaries, Evidence pairing, semantic fidelity, entities, factors, direction, or critical-error tolerance.

## `APPROVED_PROJECT_DECISION` safety gates

| Gate | Required result |
| --- | --- |
| admitted Claim provenance validation | 100% |
| admitted evidence span validity | 100% |
| schema-valid admitted output | 100% |
| identity mismatch admitted | 0 |
| fabricated source reference admitted | 0 |
| malformed JSON propagation | 0 |
| production behavior changes during Shadow phases | 0 |

Any safety-gate miss blocks cutover regardless of aggregate semantic metrics. Empty/abstained/rejected results remain observable and cannot be counted as admitted success.

## `PROPOSED_EXTENSION` semantic targets

`REQUIRES_INDEPENDENT_APPROVAL_BEFORE_CUTOVER`:

| Human-reviewed measure | Proposed target |
| --- | --- |
| critical semantic errors | 0 in the approved cutover sample |
| invented evidence | 0 |
| negation or attribution reversal | 0 |
| Claim-boundary `correct` or approved minor-edit rate | ≥95% |
| Evidence-pairing `correct` or approved partial-support rate | ≥98% |
| semantic-fidelity `correct` rate | ≥98% |
| entity extraction `correct|partial|not_applicable` rate | ≥90% |
| factor extraction `correct|partial|not_applicable` rate | ≥90% |
| direction `correct|not_applicable` rate | ≥95% |
| combined fallback plus abstention rate on eligible reports | ≤10% |

These values are proposals, not Development Plan text and not approved product thresholds. Before Phase 1B or cutover, an independent owner must approve the sample definition, minimum per-Agent/ticker coverage, reviewer training, adjudication, confidence intervals, cost/latency budget, malformed/fallback denominator, and rollback criteria.

## Explicit exclusions

No Phase 1 quality gate evaluates Evidence Stance, ticker specificity, Counter-Alpha, B2 Conflict membership, Clause Graph, dynamic invalidation, Alpha mapping accuracy, relation extraction accuracy, or investment recommendations. Those are separate later requirements/phases and are not `SOURCE_FROZEN` §5.1 criteria.
