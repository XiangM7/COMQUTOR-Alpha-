# Product Decisions and Unknowns Register

## PD-001 — Canonical Development Plan v1.0 Copy and SHA

- **Status:** `RESOLVED`
- **Source:** Product-provided local DOCX; `docs/specs/development_plan_v1.0_manifest.json`
- **Owner:** Product owner / repository maintainers
- **Impact:** Establishes the only repository source that may be cited as Development Plan v1.0 `SOURCE_FROZEN`.
- **Blocking phase:** None for Phase 0.5
- **Required resolution:** Preserve the byte-identical file at SHA-256 `cabf3381aaa633b7b88035ab6df2d7dac0def3d5ddd337f6384f23f4c439a8d9`; add future versions separately.

## PD-002 — Semantic Authority Target Architecture

- **Status:** `APPROVED_PROJECT_DECISION`
- **Source:** ADR-001
- **Owner:** Product owner / architecture owner
- **Impact:** Separates LLM semantic proposal from deterministic validation/admission/scoring authority.
- **Blocking phase:** Phases 1–4
- **Required resolution:** Implement only through the gated future-phase contract; Phase 0.5 performs no enforcement.

## PD-003 — TradingAgents Canonical Prompt Injection

- **Status:** `FUTURE_REMOVAL_OR_DISABLEMENT_APPROVED; RUNTIME_CHANGE_DEFERRED`
- **Source:** Development Plan v1.0 L1/L2 as-is and output-capture-hooks boundary; ADR-002
- **Owner:** Product owner / architecture owner
- **Impact:** Current active prompt modification is not future production authority, but immediate removal could change Graph/Activation/Conflict.
- **Blocking phase:** Phase 4
- **Required resolution:** Measure canonical-edge effects, establish a no-injection baseline, and approve flagged rollout plus rollback before changing runtime.

## PD-004 — Exact Semantic Replay vs Raw Rebuild Diagnostic

- **Status:** `APPROVED_PROJECT_DECISION`
- **Source:** ADR-003
- **Owner:** Architecture owner
- **Impact:** Prevents raw deterministic rebuild from being represented as exact replay of historical LLM-tier decisions.
- **Blocking phase:** Phase 0.6
- **Required resolution:** Freeze and implement persisted semantic artifacts, explicit mode names, completeness policy, and Provider-zero invariants.

## PD-005 — John's 20 Alpha Mapper Labels

- **Status:** `BLOCKED_BY_PRODUCT_OWNER`
- **Source:** Development Plan v1.0 §5.2 and Week 2 acceptance
- **Owner:** John / product owner
- **Impact:** Formal ≥80% Alpha Mapper acceptance cannot be completed.
- **Blocking phase:** Phase 2 production cutover
- **Required resolution:** Supply the original 20 labeled claims, labels, rubric, version, and sign-off owner; do not substitute a locally invented set.

## PD-006 — Evidence Stance LLM Authority

- **Status:** `NOT_APPROVED`
- **Source:** `JOHN_LATER_REQUIREMENT`; ADR-004
- **Owner:** John / product owner
- **Impact:** Evidence Stance remains deterministic shadow and cannot affect Activation or Conflict.
- **Blocking phase:** Addendum A and Phase 5
- **Required resolution:** Approve a separate versioned addendum defining proposer/validator/fallback authority and evaluation gates.

## PD-007 — Ticker Specificity Definition

- **Status:** `NOT_APPROVED`
- **Source:** Not defined in Development Plan v1.0; current review limitation
- **Owner:** John / product owner
- **Impact:** No reliable ticker-specificity classification or production evidence gate exists.
- **Blocking phase:** Addendum A and Phase 5
- **Required resolution:** Define categories, peer/reference handling, ambiguity, abstention, examples, gold set, and acceptance thresholds.

## PD-008 — Historical LLM-Enabled Runs

- **Status:** `UNKNOWN_NOT_ENUMERATED`
- **Source:** Phase 0 replay audit
- **Owner:** Engineering / audit owner
- **Impact:** The historical prevalence of LLM-tier semantic decisions and exact-replay exposure is unknown.
- **Blocking phase:** Phase 0.6 planning; Phase 4 migration baseline
- **Required resolution:** Read-only enumerate run metadata and record whether `COMQUTOR_WEEK2_LLM_ENABLED=true` was realized, without modifying artifacts.

## PD-009 — Real Per-Run/Fleet-Wide LLM Call Count

- **Status:** `UNKNOWN_NOT_INSTRUMENTED`
- **Source:** Phase 0 Provider-call baseline
- **Owner:** Engineering / observability owner
- **Impact:** Cost, latency, duplicate-call, and budget baselines cannot be stated as measured facts.
- **Blocking phase:** Phase 0.6 and later cutovers
- **Required resolution:** Persist semantic call records and aggregate provider/task counts without enabling production LLM by default.

## PD-010 — LLM Response Cache

- **Status:** `MISSING`
- **Source:** Development Plan v1.0 §6, §7 non-functional requirements, and Week 5; Phase 0 code audit
- **Owner:** Phase 0.6 execution-substrate owner
- **Impact:** Duplicate semantic inputs may trigger repeated calls when the optional LLM tier is enabled.
- **Blocking phase:** Phase 0.6
- **Required resolution:** Define stable cache identity, validation/version invalidation, privacy/retention, observability, and replay interaction before cutover.

## PD-011 — §5.2 Alpha Mapping Cardinality

- **Status:** `APPROVED_PROJECT_DECISION`
- **Source:** Product Owner directive, closing the Development Plan v1.0 §5.2/§10 singular ("matched_alpha") vs. plural ("matched_alphas") inconsistency identified by the §5.2 implementation precheck
- **Owner:** Product owner
- **Decision:** A structured Claim has exactly ONE authoritative primary Alpha (`matched_alpha`), plus up to TWO informational, non-authoritative secondary Alpha candidates (`secondary_alphas`). `PRIMARY_ALPHA_COUNT <= 1`; `SECONDARY_ALPHA_COUNT <= 2`; `TOTAL_RETAINED_ALPHA_CANDIDATES <= 3`. Secondary Alphas are never co-authoritative with the primary.
- **Impact:** Resolves the `AMBIGUOUS` "output cardinality" gap-table row from the §5.2 precheck. No schema/persistence change required — see `section_5_2_product_decisions_and_john_gold_provenance.md` §Cardinality Audit.
- **Blocking phase:** Phase 2 (§5.2 formal acceptance)
- **Required resolution:** None outstanding. Future implementation work must not redesign `matched_alpha` into a multi-authoritative-alpha schema.

## PD-012 — §5.2 Alpha Score Semantics and Claim Confidence Role

- **Status:** `APPROVED_PROJECT_DECISION`
- **Source:** Product Owner directive
- **Owner:** Product owner
- **Decision:** The §5.2 Alpha match score represents semantic relevance of the Claim to the Alpha ONLY — never claim truth probability, evidence reliability, claim confidence, activation strength, or investment conviction. §5.1 Claim `confidence` must not be multiplied into or otherwise used to modify the Alpha relevance score; it may continue to be carried as metadata only.
- **Impact:** Resolves the `AMBIGUOUS` "confidence role" item from the §5.2 precheck. Current implementation already complies (confidence is not read anywhere in `alpha_mapper.py`) — no code change required.
- **Blocking phase:** None (already satisfied)
- **Required resolution:** None.

## PD-013 — §5.2 Global Minimum Match Threshold

- **Status:** `APPROVED_PROJECT_DECISION`
- **Source:** Development Plan v1.0 §5.2 ("threshold 0.35"), reaffirmed by explicit Product Owner directive
- **Owner:** Product owner
- **Decision:** 0.35 is the uniform minimum Alpha match threshold for all 10 canonical Alphas. The existing A101/A102/A103 independent hard-gate threshold bypass (`comqutor_alpha/structure_engine/ai_alpha_discriminator.py`, consumed at `alpha_mapper.py`'s `eligible_candidates` filter) has no Product Owner or ADR approval found anywhere in the repository — see `section_5_2_product_decisions_and_john_gold_provenance.md` §AI-Alpha Hard Gate Audit — and is therefore `NOT_APPROVED`. Unless a genuine prior or later approval is separately discovered, the future implementation alignment target is `ALL_10_ALPHAS_USE_0_35_MINIMUM_MATCH_THRESHOLD`.
- **Impact:** Closes the "AI-alpha threshold carve-out" spec/code conflict from the §5.2 precheck.
- **Blocking phase:** Phase 2 (§5.2 formal acceptance) — implementation alignment itself is a future task, not performed by this decision record.
- **Required resolution:** A future implementation task must remove or align the A101/A102/A103 carve-out to the uniform 0.35 threshold.

## PD-014 — §5.2 No-Match Behavior

- **Status:** `APPROVED_PROJECT_DECISION`
- **Source:** Product Owner directive
- **Owner:** Product owner
- **Decision:** A valid §5.1 structured Claim with no Alpha at or above threshold must be retained (never dropped) with `matched_alpha = null` and its existing explicit no-match status. No fake "NONE" Alpha; no forcing a low-confidence Alpha through the threshold.
- **Impact:** Resolves the "no-match behavior" item (not found in the frozen plan) from the §5.2 precheck. Current implementation already complies — no code change required.
- **Blocking phase:** None (already satisfied)
- **Required resolution:** None.

## PD-015 — §5.2 Tier-2 LLM Classifier Authority Graduation Condition

- **Status:** `APPROVED_PROJECT_DECISION`
- **Source:** Product Owner directive, formalizing the pre-existing `docs/specs/semantic_authority_matrix.csv` "PRODUCT_VALIDATION_MISSING" gate and PD-005 as an explicit decision record
- **Owner:** Product owner
- **Decision:** The Tier-2 LLM classifier (code-complete, already wired to the shared Week2LLMGateway) does not receive production semantic authority merely because it exists. It graduates only after (a) the authentic Product Owner benchmark (PD-005) becomes available and (b) the approved §5.2 acceptance metric (PD-016) reaches ≥80% against it. Until then: `TIER_2_IMPLEMENTATION = CODE_COMPLETE`, `TIER_2_AUTHORITY = PRODUCT_VALIDATION_PENDING`.
- **Impact:** No change to current runtime behavior (Tier-2 already gated behind `COMQUTOR_WEEK2_LLM_ENABLED`, off by default); makes explicit as a Product Decision what was previously stated only in a non-PD architecture document.
- **Blocking phase:** Phase 2 production cutover
- **Required resolution:** Same as PD-005 — an authentic Product Owner benchmark must be supplied and pass.

## PD-016 — §5.2 Evaluation Metric (Conditional on Authentic Benchmark Label Format)

- **Status:** `APPROVED_PROJECT_DECISION (conditional — not yet applicable, see PD-005)`
- **Source:** Product Owner directive
- **Owner:** Product owner
- **Decision:** IF the authentic John-approved benchmark (PD-005) is confirmed single-label (exactly one canonical expected primary Alpha per Claim), THEN the §5.2 acceptance metric is `TOP_1_EXACT_PRIMARY_ALPHA_ACCURACY`: a prediction counts correct only when predicted `matched_alpha` equals John's expected primary Alpha exactly (Top-3/secondary-alpha hits do not count; F1/precision/recall/weighted/semantic-similarity substitutes are not approved), and the pass condition for a 20-claim set is `>=16/20`. IF the authentic benchmark is genuinely multi-label or uses different label semantics, this metric does NOT apply and a new Product Owner decision is required before evaluation.
- **Impact:** Pre-resolves the metric-definition ambiguity from the §5.2 precheck, conditionally. Cannot yet be applied to produce an acceptance result — the authentic benchmark itself remains unverified/missing per PD-005.
- **Blocking phase:** Phase 2 production cutover
- **Required resolution:** Confirm the authentic benchmark's label format once supplied by the product owner; if single-label, this metric applies without further decision-making.
