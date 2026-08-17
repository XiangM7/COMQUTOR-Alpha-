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

## PD-017 — MSFT A102__A304 Canonical Conflict Taxonomy Adjudication

- **Status:** `REJECTED_BY_INDEPENDENT_LLM_ADJUDICATION`
- **Source:** User-authorized independent LLM product adjudication (Coding Agent, task `MSFT_A102_A304_TAXONOMY_ADJUDICATION`). **No human review was performed. John did not personally review or approve this decision.** The user explicitly authorized the Coding Agent to make this specific taxonomy judgment call without per-item human sign-off.
- **Owner:** User-authorized independent LLM adjudication — not a human Product Owner decision. Any future human Product Owner (including John) may reopen or override this record.
- **Decision:** `A102__A304` (Inference Explosion vs. Multiple Compression) is **not added** to the canonical conflict taxonomy (`comqutor_alpha/alpha_library/alpha_taxonomy_v1.yaml`). `alpha_taxonomy_v1.yaml` remains byte-identical; A102's `conflict_alphas` remains `[]`. The MVP taxonomy's canonical conflict-pair set remains exactly the six pairs `MANDATORY_CONFLICT_WEIGHTS` in `comqutor_alpha/alpha_library/alpha_loader.py` already enforces: A101–A304, A301–A304, A001–A501, A003–A501, A601–A304, A601–A501.
- **Reasoning:**
  1. **Alpha definitions (rank-1 authority).** A102 ("Inference Explosion") is a Theme-layer demand/growth driver whose own `relations` are exclusively `supportive` — to A103 (weight 0.80) and A301 (weight 0.70) — never to A304. A304 ("Multiple Compression") is a Valuation-layer risk driver whose `conflict_alphas` explicitly names A101, A301, and A601 — never A102. Neither canonical definition declares a tension between these two specific Alphas.
  2. **No approved Product Decision or ADR (rank-2 authority) exists for this pair.** PD-001 through PD-016 and ADR-001 through ADR-010 were searched; none addresses `A102__A304` or MSFT's conflict-pair set. PD-013 addresses a different, unrelated A101/A102/A103 matter (the Alpha *matching*-threshold carve-out in `ai_alpha_discriminator.py`), not conflict-pair declaration.
  3. **The canonical conflict taxonomy contract (rank-3 authority) deliberately excludes A102 from every conflict.** `alpha_taxonomy_v1.yaml` gives A102 `conflict_alphas: []`, structurally identical to A103 (AI Infrastructure) and A201 (Semiconductor Supercycle) — the taxonomy's design pattern lets A304 conflict with exactly one representative Alpha per causal layer that terminates a growth thesis (A101 = Theme-top, A301 = Fundamental-terminal, A601 = Sentiment cross-cutting), deliberately omitting the supportive chain-input Alphas (A102, A103, A201) that feed into A101/A301 via `relations` rather than duplicating the same tension at every layer. `alpha_loader.py`'s `MANDATORY_CONFLICT_WEIGHTS` hard-codes exactly six pairs and `validate_taxonomy` enforces them as mandatory; treating this set as closed (not "at least six, more allowed on demand") is consistent with the whole MVP-10 taxonomy's frozen-contract history (see `docs/adr/*`, `docs/specs/development_plan_v1.0_reference_index.md`).
  4. **The Development Plan v1.0 (rank-4 authority, `SOURCE_FROZEN` per PD-001) is internally self-contradictory on this exact point**, and the contradiction cannot be resolved in A102__A304's favor without overriding the higher-ranked taxonomy contract above it. §4 states "Conflict (all six are mandatory in MVP): A101 vs A304 · A301 vs A304 · A001 vs A501 · A003 vs A501 · A601 vs A304 · A601 vs A501" — A102 vs A304 is not one of the six. §12's "Golden Test Cases" table (attributed to "John supplies expectations") lists MSFT's "Expected main conflict" as "Bull A102 vs Bear A304" — the only one of the three worked golden rows (NVDA: A101 vs A304; QQQ: A001 vs A501; MSFT: A102 vs A304) that does not name one of §4's own six mandatory pairs. MSFT's own "Expected dominant alphas" cell in the same row already lists A101 (`A101, A102, A301, A304`), so a MSFT main-conflict of "Bull A101 vs Bear A304" — consistent with NVDA's row and with §4 — was directly available from the same table without inventing anything. Given A101/A102 are adjacent, similarly-named Theme-layer IDs ("AI Expansion" / "Inference Explosion"), the far more parsimonious reading is a drafting slip in §12, not a deliberate, reasoned decision to special-case MSFT's conflict pair — nothing elsewhere in the Development Plan explains *why* MSFT specifically would need a distinct conflict pair from every other AI-exposed ticker.
  5. **Saved production artifacts (rank-5 authority) provide no supporting signal.** The one available MSFT saved run with a completed offline replay (`0cb43bae-1a4d-4003-bb29-55d420498842`, `deterministic_baseline` stance source, `artifact_completeness=fail`) shows A102 at `activation_score=0.0`, `evidence_count=0`, `ticker_specific_evidence_count=0` — no claim in that run mapped to A102 at all. This is not treated as proof the pair "doesn't exist" (a single incomplete run cannot prove that), only as the absence of any empirical push toward approval.
  6. **Approving the pair risks uncontrolled taxonomy expansion.** A102's own reasoning applies equally to A103 (AI Infrastructure) and A201 (Semiconductor Supercycle) — both are structurally identical "supportive chain-input, zero declared conflicts" Theme/Infrastructure/Industry Alphas. Approving `A102__A304` on the general "any AI-growth Alpha can conflict with valuation risk" logic would create pressure to also add `A103__A304` and `A201__A304`, which is exactly the semantic over-generalization / duplicate-conflict risk this adjudication was asked to guard against (the tension A102 might carry against A304 is already transitively expressed via the existing A301↔A304 pair, since A102 →(supports 0.70)→ A301 →(conflicts 0.85)→ A304).
  7. **Not ticker-general.** The only evidence favoring approval is a single MSFT-specific line in one golden-case table, not a general Alpha-to-Alpha semantic argument that would apply the same way to every other A102-exposed ticker (e.g. NVDA, AMD). Per this task's own instruction, a pair that "only seems reasonable for one ticker, without general structural meaning for others" should not enter the canonical taxonomy.
- **Impact:** `J2_V0.2` for MSFT: `A102__A304` moves from `product_decision_pending` to `remove_while_undeclared` (see `comqutor_alpha/config/j2_provisional_regression_labels_v0.2.yaml`) — a formally rejected, non-canonical, non-executable pair, distinct from the still-open "pending" status it carried before this adjudication. `J2_v0.1` (`j2_provisional_regression_labels_v0.1.yaml`) is left byte-identical as a frozen historical snapshot, consistent with its existing "preserved, never superseded" status. `alpha_taxonomy_v1.yaml` is byte-identical (no code or schema change was needed in `comqutor_alpha/regression/evaluation_contract.py` — `remove_while_undeclared` pairs were already surfaced informationally regardless of ticker evaluability by the existing J2 v0.2 evaluator).
- **Blocking phase:** None — this closes a previously-open `product_decision_pending` item; it does not block any phase.
- **Required resolution:** None outstanding for this pair. A future human Product Owner (John or delegate) may reopen this decision with new formal evidence (e.g. an explicit ADR, a corrected Development Plan addendum, or a substantive general Alpha-semantics argument extending beyond MSFT) — until then, `A102__A304` must not be silently reintroduced as an executable (`required`/`conditional`/`allowed`) conflict via any future provisional label file; `comqutor_alpha/regression/labels_v2.py`'s existing `LABEL_V2_UNDECLARED_EXECUTABLE_CONFLICT_PAIR` validation already enforces this structurally for as long as the pair remains outside the canonical taxonomy.
