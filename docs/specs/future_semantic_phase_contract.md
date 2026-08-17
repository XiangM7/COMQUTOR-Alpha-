# Future Semantic Phase Contract

## Status

`APPROVED_PROJECT_DECISION` for future scope only. Phase 0.5 implements none of these phases and changes no live or replay behavior.

## Phase 0.6 — LLM Execution Substrate

- **Objective:** Establish versioned, observable, cacheable, persisted semantic-call infrastructure and the exact replay artifact contract.
- **Source basis:** Development Plan v1.0 fail-soft retry/validation/cache requirements plus ADR-003.
- **Allowed scope:** prompt version/hash; schema version/hash; model/provider identity; input/output hash; latency/token/cost; bounded retry and fallback metadata; response cache; semantic-call persistence; exact replay artifact schema.
- **Explicit non-goals:** No semantic-authority change, no production LLM cutover, no default enablement, no prompt calibration for product behavior, and no canonical prompt injection removal.
- **Prerequisites:** Independent Phase 0.5 review and explicit approval; immutable source/decision identity contract.
- **Cutover blocker:** Production LLM remains disabled by default; infrastructure tests, privacy/cost review, and Provider-zero replay contract must pass.

## Phase 1 — §5.1 Structured Output Adapter Shadow/Evaluation

- **Objective:** Evaluate LLM semantic proposal for Claim boundaries, Claim/Evidence pairing, entities, factors, and direction behind deterministic validation.
- **Source basis:** `SOURCE_FROZEN` §5.1 plus ADR-001 target authority.
- **Allowed scope:** shadow prompts, validation, human-labeled evaluation, fallback metadata, semantic deltas, and quality reporting.
- **Explicit non-goals:** No immediate production authority; no Graph/Activation/Conflict formula change; no TradingAgents prompt change.
- **Prerequisites:** Phase 0.6 substrate; approved evaluation dataset and rubric.
- **Cutover blocker:** Semantic quality, malformed-output, provenance, cost, and fallback thresholds must be explicitly approved.

## Phase 2 — §5.2 Hybrid Alpha Mapper Formal Evaluation

- **Objective:** Formally validate bounded Tier 2 select/defer behavior while preserving deterministic Tier 1 eligibility and Tier 3 fallback.
- **Source basis:** `SOURCE_FROZEN` §5.2 and Week 2 acceptance; ADR-001.
- **Allowed scope:** John-20 evaluation harness, candidate-bound classifier evaluation, mismatch analysis, and fallback observability.
- **Explicit non-goals:** No taxonomy invention, no hard-gate override, no Evidence Stance authority, and no production cutover before acceptance.
- **Prerequisites:** John's 20 labeled claims supplied by the product owner; Phase 0.6 substrate.
- **Cutover blocker:** `BLOCKED_BY_PRODUCT_OWNER` until the named set exists; ≥80% formal accuracy and product sign-off required.

## Phase 3 — §5.3 COMQUTOR-Owned Structure Extractor Shadow/Evaluation

- **Objective:** Establish the COMQUTOR extractor as the evaluated primary relation semantic proposer behind deterministic validation.
- **Source basis:** `SOURCE_FROZEN` §5.3 plus ADR-001.
- **Allowed scope:** shadow extraction, strict validation, synonym/dedupe evaluation, rule fallback comparison, and relation-quality reporting.
- **Explicit non-goals:** No canonical prompt injection disablement, no Graph/Activation/Conflict authority change, and no silent removal of existing edge sources.
- **Prerequisites:** Phase 0.6 substrate; approved relation gold set and lineage rubric.
- **Cutover blocker:** Relation precision/recall, provenance, fallback, downstream-delta, and product-review gates must pass.

## Phase 4 — Layered Semantic Cutover

- **Objective:** Cut over validated semantic stages independently and migrate away from canonical-block production authority.
- **Source basis:** ADR-001 and ADR-002.
- **Allowed scope:** per-stage feature flags, shadow comparisons, baseline measurement, staged rollout, rollback, and canonical-injection disablement after impact analysis.
- **Explicit non-goals:** No one-shot global cutover; no baseline-free removal; no scoring-formula redesign.
- **Prerequisites:** Successful Phases 1–3; canonical-edge effects on Graph/Activation/Conflict measured; exact replay artifacts available.
- **Cutover blocker:** Independent product approval, observable rollback criteria, and zero unexplained deterministic-core regressions.

## Addendum A — Evidence Stance and Ticker Specificity

- **Objective:** Freeze later-requirement semantics, human-review ownership, and any future proposer/validator authority.
- **Source basis:** `JOHN_LATER_REQUIREMENT` for Evidence Stance; ticker specificity remains not approved; ADR-004.
- **Allowed scope:** stance, assertion mode, ticker specificity, mixed/ambiguous, abstention, human review, gold sets, and exact Conflict evidence membership.
- **Explicit non-goals:** No production gate before approval; no retroactive Development Plan labeling; no B2 implementation.
- **Prerequisites:** John-approved ontology, definitions, examples, and gold-set ownership.
- **Cutover blocker:** Separate signed addendum, quality thresholds, downstream impact analysis, and rollback plan.

## Phase 5 — B2 Conflict Admissibility

- **Objective:** Implement explicitly approved evidence-membership and admissibility rules for Conflict.
- **Source basis:** Future Addendum A and a separately approved B2 contract; not Development Plan v1.0.
- **Allowed scope:** deterministic membership/admission rules, reason codes, tests, shadow deltas, and controlled cutover.
- **Explicit non-goals:** No new stance ontology, no unbounded LLM conflict authority, and no change without Addendum A.
- **Prerequisites:** Addendum A approved and validated; Phases 0.6–4 complete as applicable.
- **Cutover blocker:** Product-owned golden conflicts, exact evidence membership, regression thresholds, and explicit approval.
