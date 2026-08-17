# ADR-001 — Semantic Authority

- **Status:** `ACCEPTED_FOR_FUTURE_IMPLEMENTATION`
- **Production enforcement:** `NOT_YET_ENFORCED_IN_PRODUCTION`
- **Decision classification:** `APPROVED_PROJECT_DECISION`
- **Canonical source:** Development Plan v1.0, SHA-256 `cabf3381aaa633b7b88035ab6df2d7dac0def3d5ddd337f6384f23f4c439a8d9`

## Context

Development Plan v1.0 defines LLM-assisted structured claims, hybrid Alpha mapping, and LLM relation extraction, while also requiring structured module boundaries, fail-soft behavior, and decomposable deterministic scores. It does not fully allocate semantic proposer, validator, fallback, and production authority among current components.

Phase 0 established that the current implementation has deterministic claim segmentation, optional LLM enrichment, constrained optional Alpha classification, three relation sources, and a deterministic scoring/admission core. This ADR freezes the future authority model without changing current runtime behavior.

## Decision

### 1. Structured Output Adapter

`SOURCE_FROZEN`:

- Agent natural-language output is converted to the standard claim schema.
- Downstream modules consume structured JSON rather than parsing agent free text.
- Malformed LLM JSON does not propagate.
- Failures do not crash a run and produce explicit safe defaults.

`APPROVED_PROJECT_DECISION`:

- The deterministic segmenter may remain as a candidate-segment generator.
- For open-language input, the LLM is the primary semantic proposer for Claim boundaries, Claim/Evidence pairing, entities, factors, and direction.
- A deterministic validator has final authority over provenance, source-span fidelity, schema, identity, bounded vocabulary, and acceptance into downstream artifacts.
- Unvalidated LLM output has no downstream authority.
- Deterministic fallback remains available but must carry explicit generator, fallback/degradation reason, and validation status metadata.

This decision does **not** claim that Development Plan v1.0 requires every Claim boundary to be LLM-generated.

### 2. Alpha Mapper

`SOURCE_FROZEN`: Tier 1 keyword/factor matching → Tier 2 LLM classification → Tier 3 rule fallback, with threshold 0.35, top-3 output, and ≥80% accuracy on John's 20 labeled claims.

`APPROVED_PROJECT_DECISION`:

- Tier 1 is the deterministic eligibility authority.
- Tier 2 may only select or defer among eligible taxonomy candidates.
- Tier 2 cannot create an Alpha, change the taxonomy, change hard-gate eligibility, or restore a rejected candidate.
- Tier 3 must be explicitly marked as fallback.
- Production cutover is prohibited until John's named 20-label acceptance set is available and the frozen evaluation passes.

### 3. Structure Extractor

`SOURCE_FROZEN`: the LLM extracts cause-effect relations; output is strict JSON; empty results fall back; duplicates/synonyms merge; minimum types are causal, supportive, and conflicting.

`APPROVED_PROJECT_DECISION`:

- The COMQUTOR-owned extractor becomes the only primary relation semantic proposer in the target architecture.
- Graph Builder is the final deterministic admission authority.
- Rule extraction is permitted only as an explicit fallback or shadow comparator.
- `CANONICAL_BLOCK` has no future production authority unless the Development Plan is formally revised or superseded by an approved versioned addendum.

### 4. Deterministic Core

The following retain unique deterministic final authority:

- taxonomy and factor/relation vocabulary validity;
- evidence provenance and source-span fidelity;
- ticker, run, claim, factor, relation, and artifact identity;
- dedupe and lineage;
- graph normalization and admission;
- Activation and qualification ceilings;
- Exposure calculation;
- conflict-pair registry, conflict score, and conflict admission;
- artifact and API serialization;
- replay execution and mode enforcement.

LLM output may propose semantic records but cannot directly override these authorities.

### 5. Evidence Stance

- Provenance is `JOHN_LATER_REQUIREMENT`, not Development Plan v1.0.
- Current authority remains `SHADOW_ONLY`.
- Future LLM design requires a separate approved Addendum.
- No stance result enters Activation or Conflict before that approval and its cutover gates.

## Current Implementation Gap

| Area | `CURRENT_IMPLEMENTATION` | Target decision | Enforced now? |
| --- | --- | --- | --- |
| Claim semantics | Deterministic boundaries; optional bounded enrichment cannot revise claim/evidence | LLM primary semantic proposal behind deterministic validation | No |
| Alpha semantics | Bounded optional select/defer among deterministic candidates | Retain architecture; formally validate before cutover | Partially, but validation missing |
| Relation semantics | Rule + optional LLM + canonical-block merge | COMQUTOR extractor primary; rule fallback/shadow; no canonical-block authority | No |
| Deterministic core | Deterministic final computation | Preserve | Yes for audited scope |
| Evidence Stance | Deterministic shadow | Separate Addendum before authority | Yes: shadow only |

## Consequences and Non-Goals

- Future semantic artifacts require explicit generator, validation, fallback, prompt/schema/model, and lineage metadata.
- Semantic cutover must be layered and reversible, not a single global switch.
- This ADR does not enable an LLM, change prompts, change production gates, implement replay persistence, or approve Evidence Stance semantics.
