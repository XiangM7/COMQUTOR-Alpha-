# ADR-004 — Evidence Stance Provenance

- **Status:** `RECORDED`
- **Production authority:** `NO_PRODUCTION_AUTHORITY`
- **Source classification:** `JOHN_LATER_REQUIREMENT`
- **Current effect:** `SHADOW_ONLY`

## Context

The five-way Evidence Stance vocabulary was introduced by John's later B1 requirement. It is absent from Development Plan v1.0 and must not be presented as a source-frozen plan feature.

The current deterministic implementation operates in shadow mode. It adds diagnostic fields but does not change Alpha eligibility, Activation, Conflict admission, Conflict scoring, or the selected main conflict.

## Recorded Decision

- The current classifier remains a shadow diagnostic.
- It is not Alpha Mapper Tier 3. Tier 3 is the §5.2 rule fallback after LLM classification failure.
- It cannot be used as B2 production admissibility authority.
- The current 50-row review sample is development evidence, not John's final gold set.
- No production gate may consume it until a separate addendum is approved and validated.

## Required Future Addendum

An Evidence Stance and Ticker Specificity Addendum must independently freeze:

- stance vocabulary and semantics;
- assertion mode;
- ticker-specificity definition;
- mixed/ambiguous handling;
- abstention and unknown behavior;
- human-review workflow and gold-set ownership;
- exact Conflict evidence membership and exclusion rules;
- LLM proposer/validator/fallback authority, if any;
- evaluation thresholds, cutover, rollback, and audit metadata.

Until then, Evidence Stance LLM authority and ticker-specificity semantics are `NOT_APPROVED`.

## Consequences

- Development Plan compliance matrices must mark Evidence Stance `NOT_APPLICABLE` with `JOHN_LATER_REQUIREMENT` provenance.
- Shadow outputs may support diagnosis and human review but not production scoring or admission.
- Phase 0.5 does not modify the classifier or begin B2 Conflict Admissibility.
