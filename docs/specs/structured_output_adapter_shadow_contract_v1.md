# Structured Output Adapter Shadow Contract v1

Status: `APPROVED_PROJECT_DECISION` for offline Shadow evaluation; `NOT_LIVE_INTEGRATED`; `NO_PRODUCTION_AUTHORITY`; `SEMANTIC_QUALITY_UNPROVEN`.

## Source boundary

Development Plan v1.0 §5.1 is `SOURCE_FROZEN`: Agent natural language becomes the standard Claim schema, downstream consumes structured JSON, required identity/Claim/Evidence fields are retained, factors are best effort, entities may be empty, confidence is bounded, and malformed LLM JSON must fail soft without crashing the run. LLM-wide segmentation, source-span format, Shadow identity, comparison signals, and the evaluation workflow below are `APPROVED_PROJECT_DECISION`, not quotations from the Plan.

## Versioned identities

- output schema: `comqutor.structured_claim_shadow.v1`
- input schema: `comqutor.structured_claim_shadow_input.v1`
- Claim ID: `comqutor.shadow_claim_id.v1`
- candidate contract: `comqutor.shadow_candidate_segment.v1`
- prompt: `structured_adapter.claim_extraction_shadow.v1`
- prompt SHA-256: `c60f1526fd927e4593ab5913bc3c653cd2a05f6d24dc5fdf3e258a3e62128d1e`

Breaking field, semantic, canonicalization, identity-input, or prompt changes require a new version. The fixed prompt hash prevents silent drift.

## Bundle schema

The exact top-level fields are:

```json
{
  "schema_version": "comqutor.structured_claim_shadow.v1",
  "run_id": "caller-owned",
  "ticker": "caller-owned",
  "agent": "caller-owned",
  "agent_output_id": "caller-owned",
  "source_report_sha256": "sha256(exact UTF-8 report)",
  "prompt_version": "structured_adapter.claim_extraction_shadow.v1",
  "prompt_sha256": "c60f1526fd927e4593ab5913bc3c653cd2a05f6d24dc5fdf3e258a3e62128d1e",
  "claims": [],
  "abstentions": [],
  "validation_summary": {},
  "shadow_only": true,
  "production_authority": false
}
```

Each Claim has exactly `shadow_claim_id`, `claim`, `evidence`, `source_spans`, `entities`, `factors`, `direction`, `confidence`, `source_type`, `source_refs`, `candidate_segment_ids`, and `extraction_status`. Direction is `positive|negative|neutral|unknown`; source type is `news|filing|price|analyst|social|technical|unknown`; extraction status is `proposed|abstained`; confidence is finite in `[0,1]`.

Each span has exactly `start`, `end`, and `exact_quote`. Offsets are Python half-open character offsets `[start,end)`, and `exact_quote` must equal `source_report[start:end]`. Evidence is either one exact quote or the whitespace-bounded concatenation of its declared quotes. Claim may be a concise faithful paraphrase; automatic validation does not claim to prove that semantic fidelity.

An abstention has exactly `candidate_segment_ids`, `reason_code`, and `notes`. It contains no chain of thought.

## Stable Claim identity

Caller code ignores the proposed `shadow_claim_id` and computes:

`shadow-claim-v1-` + SHA-256(canonical JSON of Claim-ID version, schema version, run ID, Agent-output ID, unique sorted span offsets, and SHA-256 of case-folded/whitespace-normalized Claim text).

Identity uses no time, randomness, object address, model value, or ordinal-only key. A Claim or span change changes identity; duplicate computed identities are rejected.

## Candidate segments

The compatibility layer calls the current public `structured_output_adapter.extract_claim_segments_with_audit` without modifying it. Its output is a hint only. Candidate IDs are deterministic hashes over candidate-contract version, Agent-output ID, candidate index, and hint text. When the exact cleaned hint is findable in the report, the request adds a convenience exact span; absence of a hint span does not weaken the final Claim-span requirement.

The proposer may retain, merge adjacent candidates, split, omit headings/disclaimers/transitions/procedural text, return no Claims, or abstain. It cannot introduce outside facts, change identity, invent a source reference, reverse negation, assert questions/hypotheticals, collapse quoted attribution into Agent assertion, or emit trading-advice/later-phase fields.

## Offline invocation and admission

`StructuredOutputShadowParser` accepts only an injected `SemanticInvoker`/callable. Phase 1A uses `FakeSemanticInvoker` or an explicit fixture. It never constructs a Provider or reads credentials. The request includes the exact report between untrusted-data boundaries, caller identity/hash, candidates, current canonical factor names, and caller-approved source references.

The validator fail-closes on exact schema/field sets, authority flags, identity, report and prompt hashes, claim/output bounds, span offsets/quotes, bounded evidence, source references, textually grounded entities, fixed enums, current factor vocabulary, and duplicate identity. Span overlap is recorded as a diagnostic warning, not an automatic semantic error.

Stable rejection codes include:

- `SHADOW_SCHEMA_INVALID`
- `SHADOW_IDENTITY_MISMATCH`
- `SHADOW_SOURCE_HASH_MISMATCH`
- `SHADOW_SOURCE_SPAN_INVALID`
- `SHADOW_EVIDENCE_NOT_PROVENANCED`
- `SHADOW_FACTOR_VOCABULARY_INVALID`
- `SHADOW_DIRECTION_INVALID`
- `SHADOW_DUPLICATE_CLAIM`
- `SHADOW_UNAPPROVED_FIELD`
- `SHADOW_OUTPUT_TOO_LARGE`
- `SHADOW_PROMPT_VERSION_MISMATCH`
- `SHADOW_EMPTY_OR_NON_SUBSTANTIVE`
- `SHADOW_INVOKER_ERROR`
- `SHADOW_JSON_INVALID`

Additional narrow codes cover unapproved source references, ungrounded entities, and credential-like admitted evidence.

## Fail-soft states

- `parser_error`: malformed JSON or injected invoker exception.
- `validation_rejected`: deterministic validation failure.
- `empty_valid_output`: valid empty Claims with no abstention.
- `abstained`: valid explicit abstention.
- `input_too_large`: report exceeds the configured offline guard.

All failure bundles contain no fake Claims, remain Shadow-only, and have no production fallback. Legacy output is never relabeled as Shadow output.

## Comparison and human review

Automated output is limited to exact/normalized-exact overlaps, candidate lineage, potential merge/split candidates, unmatched records, set/direction deltas, duplicates, abstentions, and validation failures. These are `comparison signals` and `diagnostic candidates`, never semantic errors or gold labels. Human evaluation follows `structured_output_adapter_review_contract_v1.md`.

## Non-goals

No live route/Gateway/replay import, production write, Provider/network/Redis/database operation, current prompt change, Adapter/Mapper/Extractor change, or deterministic-core change is authorized. Evidence Stance, ticker specificity, Counter-Alpha, B2, Clause Graph, dynamic invalidation, and investment decisions are outside this schema.
