# Phase 0.5 — Development Plan LLM Boundary Audit Reconciliation

## Status and Scope

`APPROVED_PROJECT_DECISION`: specification reconciliation only. No production behavior is changed or enforced by this document.

The original Phase 0 report was a code-fact audit conducted without a canonical Development Plan file in the repository. It correctly recorded many implementation facts, but some verdict language inferred source intent from task excerpts and repository paraphrases. Phase 0.5 now reconciles those verdicts against the formal, byte-identical Development Plan v1.0 repository copy:

- Canonical file: `docs/specs/COMQUTOR_Alpha_Development_Plan_v1.0.docx`
- Canonical SHA-256: `cabf3381aaa633b7b88035ab6df2d7dac0def3d5ddd337f6384f23f4c439a8d9`
- Reference index: `docs/specs/development_plan_v1.0_reference_index.md`

The original Phase 0 report and artifacts remain historical evidence and are not overwritten. Their starting hashes are recorded in `docs/audit_artifacts/phase0_5/phase0_original_file_hashes.json`. This reconciliation changes verdicts only; it does not revise the underlying code facts reported by Phase 0.

## Source Classification Rules

- `SOURCE_FROZEN`: explicit Development Plan v1.0 text.
- `JOHN_LATER_REQUIREMENT`: product requirements introduced by John after v1.0.
- `APPROVED_PROJECT_DECISION`: approved target architecture where v1.0 leaves room for a choice.
- `CURRENT_IMPLEMENTATION`: observed present behavior, never treated as source authority.
- `PROPOSED_EXTENSION`: unapproved future design.
- `UNKNOWN`: insufficient evidence.
- `BLOCKED_BY_PRODUCT_OWNER`: a required product-owner input is unavailable.

## Reconciled Verdicts

### A. §5.1 Structured Output Adapter

**STATUS: `PARTIAL`**

**VALIDATION: `SEMANTIC_QUALITY_UNPROVEN`**

`SOURCE_FROZEN`: §5.1 says the adapter converts each agent's natural-language output into the standard claim schema, downstream consumes only that JSON, and malformed LLM JSON must fail soft with explicit safe defaults.

`CURRENT_IMPLEMENTATION`: deterministic segmentation produces claim/evidence/source-section boundaries. An optional LLM tier enriches entities, factors, direction, and confidence, but cannot change claim/evidence/source-section. `COMQUTOR_WEEK2_LLM_ENABLED` is opt-in and currently defaults off.

`RECONCILIATION`: v1.0 does not say every segment boundary must be LLM-generated and does not prohibit deterministic candidate segmentation. Deterministic segmentation alone therefore does not justify the Phase 0 `DIVERGED` verdict. The material gap is that semantic quality has not been formally evaluated and the LLM does not yet hold the future approved proposer authority for open-language claim boundaries and claim/evidence pairing.

The former “stricter and safer” characterization is withdrawn as a verdict basis: no independent quality evaluation establishes that comparison.

### B. §5.2 Alpha Mapper

**STATUS: `IMPLEMENTATION_STRUCTURE_COMPLIANT`**

**VALIDATION: `PRODUCT_VALIDATION_MISSING`**

`CURRENT_IMPLEMENTATION`: Tier 1 deterministic keyword/factor scoring, optional Tier 2 LLM selection, and Tier 3 deterministic fallback exist in priority order. Threshold 0.35 and top-3 output exist. The LLM is gated and off by default.

`SOURCE_FROZEN`: §5.2 and Week 2 require overall accuracy of at least 80% on John's 20 labeled claims.

`BLOCKED_BY_PRODUCT_OWNER`: the named 20-claim set was not found in the repository, and no formal ≥80% acceptance result was found. The implementation structure is compliant, but the section must not receive an unqualified `COMPLIANT` product verdict.

### C. §5.3 Structure Extractor

**FUNCTIONAL_REQUIREMENT_STATUS: `PARTIAL`**

**INTEGRATION_BOUNDARY_STATUS: `DIVERGED_MAJOR`**

`CURRENT_IMPLEMENTATION`: a validated `LLM_EXTRACTED` path exists, with strict JSON, fallback behavior, and the required causal/supportive/conflicting relation types. Production also merges `RULE_EXTRACTED` and `CANONICAL_BLOCK` edges.

`RECONCILIATION`: a third edge source is not automatically a violation. The functional status remains partial because the source-frozen LLM extraction capability exists but its quality and intended primary authority are unproven. The major divergence is at the integration boundary: `CANONICAL_BLOCK` is solicited by a runtime prompt monkeypatch that changes TradingAgents agents' effective prompts and requested output behavior, conflicting with L1/L2 “as-is” and the §5 minimal output-capture-hooks boundary.

### D. TradingAgents Boundary

**STATUS: `CURRENT_IMPLEMENTATION_DIVERGED_MAJOR`**

- `CURRENT_IMPLEMENTATION`: `comqutor_alpha/adapters/tradingagents_output_writer.py` passively reads and saves final state; this is a compliant capture mechanism.
- `CURRENT_IMPLEMENTATION`: `comqutor_alpha/llm/canonical_prompt_injection.py` monkeypatches prompt-builder references at runtime. It adds no LLM call and changes no `tradingagents/` file on disk, but actively changes effective prompt/output behavior.
- `APPROVED_PROJECT_DECISION`: canonical prompt injection is not future production semantic authority. Phase 0.5 deliberately does not disable, delete, or modify it; migration is deferred until impact is measured and a flagged rollback path exists.

### E. Replay

**PROVIDER_ZERO: `COMPLIANT`**

**SEMANTIC_REPRODUCIBILITY: `PARTIAL`**

**CUTOVER IMPACT: `BLOCKER_BEFORE_DEFAULT_LLM_ENABLEMENT`**

`CURRENT_IMPLEMENTATION`: replay calls no TradingAgents graph, LLM Provider, market-data provider, or database. It rebuilds from saved raw output and forces `llm_gateway=None`.

This is `RAW_REBUILD_DIAGNOSTIC`-like behavior, not exact replay of historical LLM-tier semantic decisions. Before any default LLM enablement, live semantic outputs and their prompt/schema/model/validation metadata must be persisted for Provider-zero `EXACT_SEMANTIC_REPLAY`.

### F. Deterministic Core

**STATUS: `COMPLIANT_FOR_CURRENT_AUDITED_SCOPE`**

The audited taxonomy, evidence grouping, dedupe, graph admission/normalization, activation, qualification ceiling, exposure calculation, conflict registry/scoring/admission, identity, artifact serialization, API serialization, and replay execution boundaries remain deterministic. This scoped conclusion does not claim every Development Plan feature or later product requirement is implemented or accepted.

### G. Evidence Stance

**DEVELOPMENT_PLAN_STATUS: `NOT_APPLICABLE`**

**PROVENANCE: `JOHN_LATER_REQUIREMENT`**

**CURRENT_EFFECT: `SHADOW_ONLY`**

Evidence Stance's five classes are not in Development Plan v1.0. The current deterministic classifier is a John-later B1 diagnostic, does not act as Alpha Mapper Tier 3, and does not affect Activation or Conflict. Any future LLM authority or production gate requires a separate approved addendum.

## Resulting Architecture Decisions

The reconciled target is frozen in ADR-001 through ADR-004:

1. COMQUTOR-owned semantic proposers operate behind deterministic schema, provenance, vocabulary, identity, lineage, and admission authorities.
2. TradingAgents remains as-is with passive output capture in the target architecture.
3. Exact semantic replay and raw rebuild diagnostic are separate, explicitly named Provider-zero modes.
4. Evidence Stance remains a later-requirement shadow diagnostic until a separate addendum is approved.

None of these future decisions is enforced in production by Phase 0.5.
