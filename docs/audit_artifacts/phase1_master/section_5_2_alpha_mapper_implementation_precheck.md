# §5.2 Alpha Mapper — Implementation Precheck (Read-Only)

Status: **PRECHECK ONLY. No §5.2 implementation performed.** Zero Provider calls,
zero subagents, zero production/test file modifications. HEAD unchanged at
`b5837e80a4550fc35165d0013a8ef0f27ccb4c8f` throughout.

## 0. Frozen source confirmation

`docs/specs/COMQUTOR_Alpha_Development_Plan_v1.0.docx` SHA-256 re-verified
byte-for-byte against `docs/specs/development_plan_v1.0_manifest.json`:
`cabf3381aaa633b7b88035ab6df2d7dac0def3d5ddd337f6384f23f4c439a8d9` — match confirmed.
The actual document XML was extracted read-only (zip/XML parse, no external
tool, no network) and the real §5.1–§5.7 and §3/§4/§10 text was read directly
— not recalled from memory, and not taken solely from the secondary
`development_plan_v1.0_reference_index.md` navigation aid (which was used only
as a pointer, then independently verified against the primary document).

## 1. Actual frozen §5.1, §5.2, §5.3 text (verbatim)

**§5.1 Structured Output Adapter** (doc paragraphs ~198–214):

> Converts each agent's natural-language output into the standard claim schema.
> Downstream modules consume only this JSON.
> ```
> {
> "run_id": "uuid", "ticker": "NVDA", "agent": "news_agent",
> "timestamp": "2026-01-01T10:00:00Z",
> "claim": "AI capex remains strong and is supporting GPU demand.",
> "evidence": "Recent cloud capex commentary indicates continued AI infra spending.",
> "entities": ["NVDA", "GPU", "AI CapEx", "Datacenter"],
> "factors": ["AI demand", "GPU demand", "datacenter capex"],
> "direction": "positive | negative | neutral",
> "confidence": 0.82,
> "source_type": "news | filing | price | analyst | social | technical | unknown",
> "source_refs": []
> }
> ```
> Mandatory fields: run_id, ticker, agent, claim, evidence. factors must be
> extracted best-effort; entities may be an empty array; confidence ∈ [0,1].
> On LLM parse failure return the safe default {direction:"unknown",
> confidence:0, factors:[], entities:[], source_type:"unknown"} — never
> propagate malformed JSON, never crash the run.

**§5.2 Alpha Mapper** (doc paragraphs ~215–220):

> Maps a structured claim to Alpha IDs. Three-tier matching, in priority
> order: (1) keyword match + factor match against the taxonomy keyword index;
> (2) LLM classification; (3) rule-based fallback if the LLM fails. First
> version: merge claim+evidence+factors into one text; keyword hits raise
> match_score; threshold 0.35; return top-3 alphas.
> ```
> in : {"claim": "...", "factors": [...], "direction": "positive", "confidence": 0.82}
> out: {"matched_alphas": [{"alpha_id": "A101", "name": "AI Expansion",
> "match_score": 0.91, "direction": "positive", "evidence": "..."}]}
> ```
> Acceptance sentences (must map correctly): [8 sentences → A101/A102/A103/
> A201/A301/A304/A501/A601]. **Overall ≥80% accuracy on John's 20 labeled claims.**

**§5.3 Structure Extractor** (doc paragraphs ~221–225):

> LLM-extracts cause-effect relations from claims into StructureNode /
> StructureEdge objects. Strict-JSON output with fallback on empty results;
> merge duplicate nodes and synonyms... Minimum edge types: causal,
> supportive, conflicting.
> `"AI capex is increasing, which drives GPU demand and supports NVDA revenue
> growth." -> nodes: AI CapEx (factor), GPU Demand (factor), NVDA Revenue
> Growth (fundamental) -> edges: AI CapEx -(causal 0.85)-> GPU Demand
> -(causal 0.80)-> NVDA Revenue Growth`

**§3 end-to-end MVP data flow** (doc paragraphs ~95–104) — this is the
authoritative wiring order and directly settles §10 of this precheck:

> ticker -> structured_output_adapter: raw text -> standard JSON (L3) ->
> **alpha_mapper: claims -> matched Alpha IDs (L3/L5)** -> **structure_extractor:
> claims -> causal nodes & edges (L3)** -> graph_builder (networkx): merged
> Structure Graph (L6) -> activation_scorer (L5) -> conflict_detector (L5) ->
> FastAPI response + dashboard.

**Both `alpha_mapper` and `structure_extractor` consume "claims" directly —
i.e. §5.1's output — as parallel siblings, not a serial chain.** `graph_builder`
is the point where the two branches merge ("merged Structure Graph"). This is
corroborated independently by the current code's own artifact-lineage table
(`comqutor_alpha/api/routes_research.py:1034-1036`):

```
structured_agent_outputs.json  <- structured_output_adapter.adapt_run_outputs
                                -> consumed by: alpha_mapper, structure_extractor, run_audit
alpha_matches.json             <- alpha_mapper.build_alpha_matches_payload
                                -> consumed by: graph_builder, activation_scorer_v2, conflict_detector
extracted_structures.json      <- structure_extractor.save_extracted_structures
                                -> consumed by: graph_builder
```

**§5.3 does not consume §5.2's output at all**, in either the frozen plan or
the current code. This corrects the working assumption in this precheck task's
own §10 framing — see Q23 below.

**§5.7 Exposure Engine** (doc paragraphs ~251–252, for §11 of this precheck):

> Maps each ticker to per-Alpha exposure... Formula: exposure =
> historical_mapping × 50% + current_evidence × 30% + agent_confidence × 20%.
> MVP starts from a static seed table (entity_alpha_exposure_seed.yaml) that
> John supplies.

This is a **separate, later stage** (§5.7, not §5.2) using a **different term**
("exposure") from §5.2's own term ("match_score"). The precheck task's own §2
working assumption ("Alpha exposure scores... threshold 0.35... Top 3") conflates
these two distinct frozen concepts — worth flagging precisely: §5.2 produces
per-claim `match_score`; ticker-level "Alpha exposure" is a §5.7 concept computed
from §5.2's output plus a separate historical/seed input, not a synonym for it.

## 2. §5.2 working-assumption verification table

| Working assumption (from this task's §2) | Classification | Evidence |
|---|---|---|
| Structured §5.1 Claim is the input | CONFIRMED_BY_PLAN | §3 data flow, §5.2 "in:" example |
| keyword + factor candidate mapping (Tier 1) | CONFIRMED_BY_PLAN | §5.2 text, item (1) |
| LLM classification (Tier 2) | CONFIRMED_BY_PLAN | §5.2 text, item (2) |
| deterministic fallback (Tier 3) | CONFIRMED_BY_PLAN | §5.2 text, item (3) |
| "Alpha exposure scores" | AMBIGUOUS / TERMINOLOGY CONFLATION | §5.2 calls it `match_score`; "exposure" is §5.7's distinct term |
| threshold ≈ 0.35 | CONFIRMED_BY_PLAN (verbatim "threshold 0.35") | §5.2 text; Step 7 (¶373) repeats it |
| Top 3 Alpha mappings | CONFIRMED_BY_PLAN (verbatim "top-3 alphas") | §5.2 text; Step 7 |
| input = Claim + Evidence + Factors | CONFIRMED_BY_PLAN, with an internal tension | Prose says "merge claim+evidence+factors"; the plan's own worked `in:` JSON example omits `evidence`. See Q19/Q21. |
| John has 20 labeled Claims | CONFIRMED_BY_PLAN as a **requirement**; the labeled set itself is NOT_FOUND in the repo | §5.2 ¶220, §10 ¶344, DoD ¶402; PD-005 |
| Target ≥ 80% | CONFIRMED_BY_PLAN (requirement exists); exact metric definition NOT_FOUND | Same three citations; no formula given anywhere |

## 3. Current authoritative §5.1 output contract

Two live producers exist and were both inspected directly (not assumed
equivalent):

**Legacy** (`structured_output_adapter.py`, `SCHEMA_VERSION =
"week1a.structured_agent_outputs.v2"`, `ADAPTER_VERSION =
"week1.claim_extraction.v2"`) and **v4.2 Shadow/Primary**
(`structured_output_shadow_v4_2.py`, the module Stage G's `select_primary_authority`
can make authoritative when `structured_adapter_mode="primary"` and every
report in the run was accepted). Both currently emit the same core field set:

| field | type | required/optional | nullable | producer | meaning | consumed by §5.2 today? |
|---|---|---|---|---|---|---|
| `run_id` | str | required | no | both | run identity | yes (carried through, not scored on) |
| `ticker` | str | required | no | both | scoping key | yes (carried through, not scored on) |
| `agent` | str | required | no | both | source agent name | yes (carried through) |
| `timestamp` | str (ISO8601) | present (Legacy) | — | Legacy | capture time | no |
| `claim` | str | required | no ("unknown" safe default) | both | the assertion | **yes** — primary scoring text |
| `evidence` | str | required | no ("unknown" safe default) | both | supporting quote/text | **yes** — merged into scoring text |
| `entities` | list[str] | best-effort | may be `[]` | both | named entities | no (not read by alpha_mapper.py) |
| `factors` | list[str] | best-effort | may be `[]` | both | semantic factor labels | **yes** — matched against `FACTOR_ALPHA_WEIGHTS` |
| `direction` | enum(positive/negative/neutral/unknown) | required w/ safe default | no | both | claim polarity | **yes** — 8% weight in score, ambiguity detection |
| `confidence` | float [0,1] | required w/ safe default `0` | no | both | claim confidence | **no — never read anywhere in `alpha_mapper.py`** |
| `source_type` | enum | required w/ safe default | no | both | provenance class | no |
| `source_refs` | list | optional | may be `[]`/`None` | both | source references | no |
| `claim_id` | str | required (Legacy schema) | no | Legacy | stable claim identity | yes (lineage passthrough) |
| `source_agent_output_id` | str | required | no | both | raw-output lineage | yes (lineage passthrough) |
| `claim_quality` | enum(analytical/context_only/non_substantive) | additive, later Sprint | no | Legacy (`claim_quality.py`) | eligibility class | yes (gates whether the record is mapped at all, and passed through unchanged) |

v4.2's minimal payload (Stage G primary success case) does not carry Legacy's
diagnostic-only `metadata`/`canonical_relations` blocks, but does carry every
field `alpha_mapper.py` actually reads. This was independently verified by
reading `structured_output_shadow_v4_2.py`'s canonical-bundle builder
(`normalize_v4_2_proposal_to_canonical_bundle`), not assumed.

## 4. True §5.2 input contract

The exact object Alpha Mapper receives today, confirmed by reading
`build_alpha_matches_payload` → `map_structured_records` → `map_claim_to_alpha`:
**one structured claim record at a time**, iterated from the full list in
`structured_payload["records"]` for one run (i.e. the caller passes "an entire
run's records"; the Mapper itself processes them one claim at a time, is
stateless across claims, and does no cross-claim aggregation).

| Field | REQUIRED_BY_SPEC | USEFUL_BUT_NOT_REQUIRED | CURRENTLY_AVAILABLE | CURRENTLY_USED |
|---|---|---|---|---|
| Claim | yes (§5.2 prose + `in:` example) | — | yes | yes |
| Evidence | yes (§5.2 prose says "merge claim+evidence+factors"), but absent from the `in:` example | — | yes | yes |
| Factors | yes (§5.2 prose + `in:` example) | — | yes | yes |
| Direction | yes (`in:` example) | — | yes | yes (scoring + ambiguity) |
| Confidence | present in `in:` example; role unstated | arguably | yes | **no** |
| Entities | not mentioned in §5.2 | possibly | yes | no |
| Ticker | not in §5.2's `in:`/`out:` example, but required for scoping downstream | yes, for lineage/exposure | yes | carried, not scored |
| Agent | not in §5.2 example | yes, for lineage | yes | carried, not scored |
| claim_id / source_agent_output_id | not in §5.2 example | yes, for lineage/dedup | yes | yes |

## 5. Existing Alpha Mapper code — full inventory

| File | Classification | Notes |
|---|---|---|
| `comqutor_alpha/structure_engine/alpha_mapper.py` (741 lines) | **PRODUCTION_ACTIVE** | Wired into `routes_research.py:_run_week1_week2_artifact_pipeline` (`save_alpha_matches(run_id, output_root=output_root, llm_gateway=llm_gateway)`), writes `alpha_matches.json` + the `alpha_matches` DB table via `repository.py`. |
| `comqutor_alpha/alpha_library/alpha_taxonomy_v1.yaml` | PRODUCTION_ACTIVE | 10/10 alphas, committed, clean git status (pre-existing). |
| `comqutor_alpha/alpha_library/alpha_schema.py` | PRODUCTION_ACTIVE | `AlphaDefinition` frozen dataclass. |
| `comqutor_alpha/alpha_library/alpha_loader.py` | PRODUCTION_ACTIVE | Loader + `validate_taxonomy` (enforces exact MVP-10 ID set + 6 mandatory conflict pairs + weights + ≥1 keyword each). |
| `comqutor_alpha/structure_engine/ai_alpha_discriminator.py` (349 lines) | PARTIAL_IMPLEMENTATION / PROPOSED_EXTENSION-ish | "AI Alpha Mapper Discrimination Sprint": independent hard admission gate for exactly A101/A102/A103, **bypassing the 0.35 threshold** for those three. No PD/ADR entry found naming this sprint; its own golden fixture self-describes as "the current implementation's acceptance fixture, not a permanent frozen contract." |
| `comqutor_alpha/structure_engine/claim_quality.py` | PRODUCTION_ACTIVE | Shared eligibility gate (Mapper/Extractor/Activation/Conflict/persistence) — "Unified Claim Admissibility Sprint," documented in `docs/unified_claim_admissibility_and_context_only_routing_sprint.md`. |
| `comqutor_alpha/structure_engine/evidence_stance.py` | SHADOW_ONLY, attached additively | PD-006/ADR-004: `JOHN_LATER_REQUIREMENT`, `NOT_APPROVED` for production authority. Attached onto Mapper output as `matched_evidence_stance` etc., never affects `matched_alpha`/`score`. |
| `comqutor_alpha/structure_engine/factor_normalizer.py`, `claim_semantics.py` | PRODUCTION_ACTIVE | Shared text-normalization / semantic-relation helpers, used by both Mapper and Extractor. |
| `comqutor_alpha/api/routes_alpha_library.py` (67 lines) | PRODUCTION_ACTIVE, read-only | `GET /api/alpha-library`, `GET /api/alpha-library/{alpha_id}` — taxonomy display API, not part of the mapping pipeline. |
| `comqutor_alpha/storage/db/schema.py` (`alpha_matches` table) | PRODUCTION_ACTIVE | See §25 below. |
| `tests/test_alpha_mapper.py`, `test_alpha_mapper_nvda_real_report.py`, `test_ai_alpha_mapper_discrimination.py`, `test_week2_labeled_accuracy.py` | TEST_ONLY | 163 tests total; **all pass** on current HEAD (verified by running them, read-only, no files changed). |

No dead code, no pure placeholders found. Nothing here is inconsistent with
the frozen plan's *architecture*; several pieces (AI-alpha hard gate, the
weighted 0.50/0.30/0.08/0.12 scoring blend, `match_status="ambiguous"`) are
**elaborations beyond the frozen plan's literal text**, implemented and
tested, but without a located PD/ADR entry specifically blessing them as
approved extensions (see §7's SPEC_CODE_CONFLICTS).

## 6. Canonical Alpha taxonomy

**ONE canonical taxonomy, no competing definitions found.**

- Source of truth: `comqutor_alpha/alpha_library/alpha_taxonomy_v1.yaml`
  (exactly the path the frozen plan names, ¶180: "Engineer B transcribes all
  10 into comqutor_alpha/alpha_library/alpha_taxonomy_v1.yaml").
- Count: **10** (A001, A003, A101, A102, A103, A201, A301, A304, A501, A601)
  — matches the frozen plan's table exactly; `alpha_loader.EXPECTED_ALPHA_IDS`
  hard-enforces this exact set.
- Per entry: `alpha_id`, `name_en`, `name_cn`, `layer`, `status`,
  `core_thesis`, `keywords[]`, `trigger_signals[]`, `confirmation_signals[]`,
  `beneficiary_assets[]`, `risk_assets[]`, `conflict_alphas[]` (with
  `contradiction_weight`), `invalidation_conditions[]`, `agent_sources[]`,
  `relations[]` (`target_alpha_id`, `relation_type`, `weight`).
- The frozen plan's own "Canonical Alpha schema" block (¶164-179) additionally
  names `causal_graph`, `activation_score`, `confidence_score` as per-alpha
  fields — the current YAML uses `relations` instead of `causal_graph` and
  omits the two runtime-score placeholders. This matches Step 6's explicit
  instruction (¶372) to enter an "engineering-simplified version first: id,
  names, layer, keywords, conflict_alphas with contradiction weights" — not a
  conflict, an intentionally deferred subset.
- The plan also references a separate document, **"Alpha Taxonomy v1.0"**
  (¶180, distinct from the Development Plan docx itself, containing the full
  per-alpha detail John owns) — this document was **not found anywhere in the
  repository**. The in-repo YAML appears to be the "engineering-simplified"
  transcription Step 6 asked for, not a copy of that fuller source document.
  Reported factually; not something to reconstruct here.
- All 6 mandatory conflict pairs from §4 (¶183) are present in both
  directions with matching weights, enforced by `alpha_loader.validate_taxonomy`.

## 7. Factor vs. Alpha — explicit distinction

**The repository consistently treats these as two different concepts, never conflated:**

- **Factors** are §5.1-level, per-claim semantic descriptors extracted from
  text (e.g. `"AI demand"`, `"GPU demand"`, `"datacenter capex"` — verbatim
  from the frozen §5.1 example). They describe *what a claim is about*.
- **Alphas** are the canonical, taxonomy-frozen (MVP-10) market-structure
  hypotheses (`A001`...`A601`) that downstream stages (Activation, Conflict,
  Exposure) score and arbitrate.
- §5.2's entire job is to bridge the two, via an explicit, code-visible
  many-to-many table: `FACTOR_ALPHA_WEIGHTS` in `alpha_mapper.py` (e.g.
  `"AI Demand": {"A101": 1.0, "A301": 0.45, "A601": 0.25}`), plus independent
  keyword matching against the taxonomy's own `keywords[]`.

No `PRODUCT_DECISION_REQUIRED` here — the distinction is unambiguous in both
spec and code.

## 8–9. John's 20 labeled claims

**JOHN_20_LABELS = NOT_FOUND**, and this is not merely an absence — it is an
explicitly recorded, still-open product decision:

> **PD-005 — John's 20 Alpha Mapper Labels** (`docs/specs/product_decisions_and_unknowns.md`)
> Status: `BLOCKED_BY_PRODUCT_OWNER`. Impact: "Formal ≥80% Alpha Mapper
> acceptance cannot be completed." Required resolution: "Supply the original
> 20 labeled claims, labels, rubric, version, and sign-off owner; **do not
> substitute a locally invented set.**"

Two unrelated fixtures exist in `tests/` and must not be confused with John's set:

1. **`tests/golden_cases/labeled_claims_v1.json`** — exactly 20 cases, single-label
   (`expected_alpha` singular, one per case), includes `expected_direction`,
   **no** scores, rationale, Top-K, or negative/"no-alpha" cases, **no** provenance
   header (no owner/rubric/version/sign-off — exactly what PD-005 says is
   required and missing). Referenced by `tests/test_week2_labeled_accuracy.py`,
   whose docstring calls it "the approved labeled set" / "Standalone Formal
   Week 2 accuracy gate" and asserts `case_count == 20` and `accuracy >= 0.80`.
   **This self-description directly conflicts with PD-005 in the same
   repository** — flagged as a SPEC_CODE_CONFLICT below, not resolved here.
   The test currently passes (verified by running it, unmodified).
2. **`tests/golden_cases/nvda_real_report_labeled_claims_v1.json`** — a
   different, unrelated 30-case set (`schema_version:
   "week2.robust_labeled_claims.v1"`), sourced from a real uploaded NVDA
   report, includes `no_match_expected_count`/`ambiguous_expected_count`. Not
   a candidate for "John's 20" (wrong count, different declared purpose, no
   claim to be John's set).
3. **`tests/fixtures/ai_alpha_mapper_golden_v1.json`** — AI-alpha-discrimination
   -specific fixture (A101/A102/A103 only), self-declared as a revisable
   implementation-acceptance fixture, not a frozen benchmark.

Format John's real set is expected to use (per PD-005's own required-resolution
text): labeled claims + labels + a rubric + a version + a named sign-off owner.
Whether single- or multi-alpha, whether scored, whether it includes negatives
— **all unknown until John supplies it.** Nothing was manufactured here.

## 10–11. The ≥80% metric

**EVALUATION_METRIC_DEFINED = NO.** All three frozen citations state the
target number but never the computation:

- §5.2 ¶220: "Overall ≥80% accuracy on John's 20 labeled claims."
- §10 ¶344 (Week 2 gate): "≥80% accuracy on John's labeled set."
- DoD ¶402: "golden-case alpha-match accuracy ≥80%."

No frozen or later-requirement text specifies exact-top-1 vs. top-3-contains
vs. multi-label set match vs. precision/recall/F1. The existing (unconfirmed,
see §8-9) test harness implements one plausible reading — simple per-claim
pass/fail on exact top-1 match, averaged — but this is an engineering
interpretation baked into a test whose own underlying labeled set is itself
unconfirmed, not a product-approved metric definition. → `PRODUCT_DECISION_REQUIRED`.

## 12. §5.3's actual expected input

Already established in §1 above with primary-source citations: **§5.3
Structure Extractor does not expect anything from §5.2.** It is a parallel
consumer of §5.1's `structured_agent_outputs.json`, confirmed by:
(a) the frozen plan's own §3 end-to-end data-flow list (both stages listed as
direct, independent branches from "claims"), and (b) the current code's
self-documented artifact-lineage table in `routes_research.py`. Verified by
also reading `structure_extractor.py` directly — it imports nothing from
`alpha_mapper.py` and never reads `matched_alpha`/`alpha_id`/`alpha_matches.json`.

§5.2's real downstream consumers are **Graph Builder (§5.4), Activation Scorer
(§5.5), and Conflict Detector (§5.6)**, all reading `alpha_matches.json`'s
`matches` list directly (confirmed by grep across `graph_engine/` and
`conflict_engine/`).

## 13. Entity Exposure (ticker × alpha) construction stage

**§5.7 RESPONSIBILITY — confirmed, not §5.2's job.** `comqutor_alpha/exposure_engine.py`
implements the frozen formula exactly (`historical_mapping*0.50 +
current_evidence*0.30 + agent_confidence*0.20`, `EXPOSURE_WEIGHTS` matches
¶252 verbatim) and writes a separate artifact, `entity_alpha_exposures.json`,
in a **later pipeline stage** (`_run_week3_graph_pipeline`, confirmed by
reading `routes_research.py`), downstream of both `alpha_matches.json` and
`extracted_structures.json`. §5.2's only obligation toward this later stage is
to carry `ticker` on every output record — which it already does (§5.2's
scoring logic itself is ticker-agnostic; ticker is metadata, never used to
adjust `keyword_score`/`factor_score`/`direction_score`).

## 14. Direction/stance responsibility boundary

The later stance vocabulary this precheck was asked to check for
(`supports_alpha`/`opposes_alpha`/`mentions_alpha`/`neutral_background`/
`supports_counter_alpha`) belongs to **Evidence Stance**, a `JOHN_LATER_REQUIREMENT`
(PD-006, ADR-004) that is explicitly `NOT_APPROVED` for any production
authority and `SHADOW_ONLY`. `alpha_mapper.py` does attach Evidence Stance
fields onto its output (`matched_evidence_stance`, `counter_alpha_id`,
`stance_reason_codes`, `stance_confidence_band`, `requires_manual_review`) —
but these are clearly-namespaced, additive fields that never influence
`matched_alpha`, `score`, or eligibility. §5.2's own `direction` field (from
§5.1) is used only as: (a) an 8%-weighted scoring input, and (b) an
opposing-pair/ambiguity signal — it is never converted into the later stance
vocabulary anywhere in §5.2 itself. `OUT_OF_SCOPE_FOR_5_2`.

## 15. Activation/Conflict/Graph responsibility boundary

All confirmed `OUT_OF_SCOPE_FOR_5_2`, both by the frozen plan's own module
boundaries (§5.4/§5.5/§5.6) and by current code location:

- Activation thresholds (active ≥50, dominant ≥70, regime ≥86) —
  `comqutor_alpha/graph_engine/activation_scorer*.py`.
- B2 evidence-admissibility / conflict logic — `comqutor_alpha/conflict_engine/conflict_detector.py`,
  gated further by PD-007 (`ticker specificity`, `NOT_APPROVED`, Addendum A).
- Graph relationships — `comqutor_alpha/graph_engine/graph_builder.py`. (The
  taxonomy's own static `conflict_alphas`/`relations` fields are read by
  `alpha_mapper.py` only incidentally, for opposing-pair ambiguity detection —
  not for graph construction.)

## 16. Reusable semantic runtime

**A reusable Provider abstraction already exists and is already wired into
§5.2** — confirmed by reading both modules directly, not assumed:

- `comqutor_alpha.structure_engine.week2_llm.Week2LLMGateway` — the same
  gateway class used by §5.1's optional LLM enrichment tier, with
  `semantic_runtime` (session/cache/replay integration), `invoke_json_with_trace`,
  `invoke_json`.
- `alpha_mapper.py`'s Tier-2 classifier (`_apply_optional_classifier`) already
  calls `llm_gateway.invoke_json_with_trace("alpha_classifier", request,
  validate_response)` when a real gateway is supplied.
- **Production wiring already threads it through**: `routes_research.py`'s
  `_run_week1_week2_artifact_pipeline` passes the *same* `llm_gateway` object
  used for §5.1 straight into `save_alpha_matches(..., llm_gateway=llm_gateway)`.
  This means Tier 2 is not merely "wired but dormant" — **it will actually
  fire real Provider calls whenever the shared Week 2 LLM tier is enabled**
  (off by default, consistent with this project's established pattern), for
  any claim with ≥2 deterministic eligible candidates.
- A new Provider client would be **entirely redundant** — this is a `REUSE`,
  not a gap.
- Formal graduation of this already-live path to trusted production authority
  is a separate question (see §9/§17 below): `semantic_authority_matrix.csv`
  row "alpha ambiguous classification" explicitly marks it
  `PRODUCT_VALIDATION_MISSING`, gated on the same missing John-20 set.

## 17. Deterministic candidate generation

`CANDIDATE_GENERATION_SPECIFIED = YES`, and it is already implemented:

- Frozen plan, item (1): "keyword match + factor match against the taxonomy
  keyword index."
- Code: `alpha_loader.build_keyword_index()` indexes `alpha_id`, `name_en`,
  `name_cn`, `core_thesis`, `keywords[]`, `trigger_signals[]`,
  `confirmation_signals[]`; `alpha_mapper.keyword_score()` /
  `_indexed_keyword_matches()` do direct substring/phrase matching (no
  embeddings, no vector search, no fuzzy matching, no candidate IDs — matches
  every explicit prohibition in this precheck's own instructions); `factor_score()`
  uses the explicit `FACTOR_ALPHA_WEIGHTS` table (§7 above).

## 18. Deterministic fallback (Tier 3)

Already specified by the frozen plan ("(3) rule-based fallback if the LLM
fails") and glossed precisely by `semantic_authority_matrix.csv` ("Precomputed
deterministic decision retained on LLM absence/failure... explicit degradation
metadata"). **Current implementation matches this gloss exactly**: Tier 3 is
not a separate algorithm — it is literally "keep the already-computed Tier-1
deterministic result unchanged," annotated with an explicit `classifier`
status dict (`disabled` / `blocked_by_deterministic_no_match` / `not_needed` /
`unavailable` / `timeout` / `error` / `invalid_output` / `applied` /
`confirmed_ambiguous`) recording exactly why the LLM path did or didn't apply.
One plausible alternative reading of the frozen phrase — "rule-based fallback"
as a *distinct third scoring algorithm* — is **not** what's implemented; worth
noting as a minor textual-ambiguity resolution, not a conflict, since the
later semantic-authority matrix explicitly endorses the "retain Tier 1"
reading.

## 19. Score / threshold / Top-K

| | Value | Source |
|---|---|---|
| SCORE_RANGE | `[0.0, 1.0]`, rounded to 4dp | `structure_schema.clamp_score()`; not literally stated as a bound in the frozen text, but consistent with every example given (0.91, 0.35) |
| THRESHOLD | **0.35 confirmed** | Frozen plan verbatim ("threshold 0.35", ¶216 and ¶373); code `DEFAULT_MIN_MATCH_SCORE = 0.35` — matches exactly |
| TOP_K | **3 confirmed** | Frozen plan verbatim ("top-3 alphas", "top-3"); code slices `[:3]` in three places (`candidate_scores`, `top_candidates`, `eligible_candidates`/`plausible_candidates`) |

**One conflict inside the current implementation**: for exactly `A101`/`A102`/
`A103`, the AI-alpha hard gate (§5 inventory above) **bypasses the 0.35
threshold entirely** — eligibility is `ai_gate_passed` (boolean), not `score
>= 0.35`, per an explicit code comment ("min_score was calibrated for the old
keyword/factor recall mechanism these three Alphas no longer use for
eligibility"). This is a real, load-bearing deviation from the frozen
"threshold 0.35" text for 3 of the 10 alphas, done deliberately but without a
located PD/ADR entry approving it as an intentional extension.

## 20. Multi-alpha mapping

`MULTI_ALPHA_MAPPING = AMBIGUOUS` — **the frozen plan is internally
inconsistent on this point**, not just under-specified:

- §5.2's own worked `out:` example uses a **plural** JSON key,
  `"matched_alphas": [...]` (an array), though the example shown contains
  exactly one entry.
- §10's Week 2 acceptance gate (¶344) uses **singular** prose: "claims map to
  **matched_alpha**."

Current code has already committed to one specific resolution — **one
authoritative `matched_alpha` (singular, nullable) per claim**, plus clearly
separate, lower-priority list fields (`secondary_alphas`, `plausible_alphas`,
`ai_alpha_matches`) that some downstream consumers do read (ambiguous-status
handling in `activation_scorer.py`, secondary-conflict checks in
`conflict_detector.py`) but never treat as co-equal "this claim maps to N
Alphas." This is reinforced at the persistence layer: the `alpha_matches` DB
table has `UniqueConstraint("run_id", "claim_id")` — one row per claim,
structurally incompatible with a genuine one-to-many claim→alpha model without
a schema change. **This was never explicitly product-approved as the
resolution of the plan's own plural/singular inconsistency** —
`PRODUCT_DECISION_REQUIRED`.

## 21. No-match behavior

`NOT_FOUND` in the frozen plan (it is silent on the below-threshold case).
Current implementation: the claim's record is **retained** in `matches` with
`match_status="no_match"`, `matched_alpha=None`, `score=0.0` — never dropped,
no special `"NONE"` alpha_id exists in the 10-alpha taxonomy, no dedicated
review queue. Coherent and already implemented, but its specific shape
(retain-with-null vs. omit vs. a sentinel value) was never product-specified.

## 22. Invalid LLM output behavior

Already fully specified and implemented — `REUSE`, no new validation
architecture needed. `_apply_optional_classifier`'s `validate_response`
closure enforces: exact field-set match (`{"decision","selected_alpha_id"}`
for the `llm_gateway` path, `{"match_status","alpha_id"}` for the legacy
`classifier` callable path), enum-checked decision/status values, and
`selected_alpha_id`/`alpha_id` **must be a member of the same deterministic
eligible-candidate set** (`allowed_ids`) — the LLM can never introduce an
alpha_id, never bypass Tier 1's candidate set, matching the frozen plan's
implicit intent and the reference index's explicit gloss ("does not permit
the LLM to invent Alpha IDs"). Unknown alpha_id, wrong field set, and
malformed/non-mapping responses all resolve deterministically to a recorded
`classifier` status (`invalid_output`/`error`/`timeout`) and fall through to
the Tier-3 fallback behavior in §18.

## 23. Evidence passed to the Mapper

**YES, Evidence is used**, by both tiers — but note the frozen plan's own
textual tension already flagged in §1/§4: the descriptive sentence says
"merge claim+evidence+factors into one text," while the worked `in:` JSON
example a few lines later omits an `"evidence"` key. Current code follows the
prose, not the abbreviated example: `_record_text()` concatenates claim +
evidence (de-duplicated when evidence ≈ claim) and feeds every deterministic
scoring function; the Tier-2 LLM request payload also explicitly includes
`"evidence": str(record.get("evidence") or "")`.

## 24. Does §5.2 see Factors? Does it use Direction? Does Confidence affect score?

- **Factors: YES**, explicitly — matched against `FACTOR_ALPHA_WEIGHTS` (§7).
- **Direction: YES**, as a genuine scoring input (8% weight in the final
  blend) and as an opposing-pair/ambiguity signal — but never reinterpreted
  into later stance vocabulary (§14). Also passed through unchanged to the
  output, matching the plan's own `out:` example which echoes `"direction":
  "positive"`.
- **Confidence: NO** — `record.get("confidence")` is never read anywhere in
  `alpha_mapper.py`: not in `keyword_score`, `factor_score`, `direction_score`,
  `_candidate_score`'s final blend, or the Tier-2 LLM request payload — despite
  being present in the frozen plan's own `in:` example with its role left
  unstated. `PRODUCT_DECISION_REQUIRED` — this is exactly the kind of gap this
  precheck task's own §23 anticipated (claim confidence ≠ alpha relevance
  score unless explicitly defined, and it has not been).

## 25. §5.2 output schema — as currently required by real downstream code

Reconstructed only from what `alpha_matches.json`'s actual downstream readers
(`graph_engine/*.py`, `conflict_engine/conflict_detector.py`) and the
`alpha_matches` DB table (`storage/db/schema.py`) genuinely consume — not from
convenience:

**File artifact** (`alpha_matches.json`, `SCHEMA_VERSION =
"week2.alpha_matches.v2"`): `{schema_version, mapper_version,
minimum_match_score, run_id, ticker, matches: [...]}`. Each element of
`matches`:

| Field | Status | Notes |
|---|---|---|
| `run_id`, `ticker`, `agent` | REQUIRED_CONFIRMED | scoping/lineage |
| `claim_id`, `source_agent_output_id` | REQUIRED_CONFIRMED | lineage; DB `UNIQUE(run_id, claim_id)` |
| `claim`, `evidence`, `factors`, `direction` | REQUIRED_CONFIRMED | passthrough from §5.1 |
| `matched_alpha` (singular, nullable) | REQUIRED_CONFIRMED | the one committed alpha_id, or `None` |
| `matched_alpha_name`, `score`, `keyword_score`, `factor_score`, `direction_score` | REQUIRED_CONFIRMED | read by Activation/Conflict for evidence gathering and decomposability |
| `match_status` (`matched`/`ambiguous`/`no_match`) | REQUIRED_CONFIRMED | drives downstream admission logic |
| `candidate_scores`, `top_candidates`, `eligible_candidates`/`plausible_alphas`, `secondary_alphas` | OPTIONAL_CONFIRMED (read by some but not all downstream consumers) | used for ambiguous-status handling and secondary-conflict detection |
| `ai_alpha_matches` | OPTIONAL_CONFIRMED | additive diagnostic |
| `matched_evidence_stance` + related fields | NOT_REQUIRED for §5.2's own core decision | Evidence Stance, PD-006-gated, additive only |
| `claim_quality` | REQUIRED_CONFIRMED (passthrough) | avoids re-deriving eligibility downstream |
| A literal plural `matched_alphas: [...]` array (as the frozen plan's own worked example shows) | AMBIGUOUS | not what current code or the DB schema implement — see §20 |

**DB table** (`alpha_matches`, `comqutor_alpha/storage/db/schema.py:43-65`):
`id, run_id, ticker, claim_id, source_agent_output_id, agent, alpha_id
(nullable), alpha_name (nullable), match_score, match_status, direction,
assertion_status, semantic_polarity, claim_text, evidence, reason,
candidate_scores (JSON blob), created_at`. One row per `(run_id, claim_id)`.

## 26. Spec vs. current-code gap table

| Requirement | Spec source | Current implementation | Status | Implementation needed | Product decision needed |
|---|---|---|---|---|---|
| MVP-10 taxonomy content + file | §4 ¶110-183 | `alpha_taxonomy_v1.yaml`, validated | IMPLEMENTED | None | None |
| Tier 1 deterministic keyword/factor matching | §5.2 ¶216 | `keyword_score`/`factor_score` | IMPLEMENTED | None | Confirm the elaborated 0.50/0.30/0.08/0.12 weighted blend is approved |
| Threshold 0.35 | §5.2 ¶216, ¶373 | `DEFAULT_MIN_MATCH_SCORE=0.35`, bypassed for A101/A102/A103 | PARTIAL / CONFLICT for 3 alphas | None | Confirm the AI-alpha carve-out is intended |
| Top-3 output | §5.2 ¶216 | `[:3]` slicing, 3 places | IMPLEMENTED | None | None |
| Tier 2 LLM classification | §5.2 ¶216; matrix row 11 | `_apply_optional_classifier` + `Week2LLMGateway`, code-complete and live-wired | PARTIAL (code done, authority not graduated) | None | Approve production authority once John-20 gate clears |
| Tier 3 deterministic fallback | §5.2 ¶216; matrix row 12 | retains Tier-1 result + status metadata | IMPLEMENTED | None | None |
| Output cardinality (`matched_alpha` vs `matched_alphas[]`) | §5.2 ¶217-219 vs §10 ¶344 | singular `matched_alpha` + auxiliary lists; DB enforces 1 row/claim | CONFLICT (spec self-inconsistent) | Possibly none | Confirm single-vs-multi is the intended contract |
| John's 20 labeled claims | §5.2 ¶220; PD-005 | NOT_FOUND; unconfirmed 20-case stand-in exists in `tests/` | MISSING | None (no engineering task) | John must supply the real set (PD-005, still open) |
| ≥80% metric definition | §5.2 ¶220; §10 ¶344; DoD ¶402 | test harness assumes top-1 exact-match accuracy | AMBIGUOUS | None | Confirm metric definition |
| Confidence role in score | `in:` example only | unused | AMBIGUOUS | None yet | Define role, if any |
| §5.2 → §5.3 dependency | §3 ¶95-104 (parallel) | confirmed parallel in code | IMPLEMENTED (task's own framing corrected) | None | None |
| Entity Exposure (ticker×alpha) | §5.7 ¶251-252 | `exposure_engine.py`, later stage | IMPLEMENTED (§5.7, not §5.2) | None for §5.2 | None |
| Evidence Stance / stance vocabulary | Not in v1.0; PD-006 | attached additively, non-authoritative | OUT_OF_SCOPE for §5.2 | None | Governed separately by PD-006 |
| Activation/Conflict/Graph thresholds | §5.4/§5.5/§5.6 | separate modules | OUT_OF_SCOPE | None | None |
| Reusable semantic runtime | ADR-005/006 | `Week2LLMGateway`, already wired into §5.2 | IMPLEMENTED | None (new client would be redundant) | None |

## 27. Implementation boundary (units only — not written)

Every unit below already has a real, tested implementation to `REUSE`; none
require a new mechanism invented from scratch:

- Alpha taxonomy loader — **REUSE** (`alpha_loader.py`).
- Deterministic keyword/factor candidate generation — **REUSE** (`alpha_mapper.py` Tier 1).
- LLM classification adapter — **REUSE** (`alpha_mapper.py` Tier 2 + `Week2LLMGateway`); blocked only on formal authority graduation, not code.
- Schema validator (LLM response) — **REUSE** (`validate_response` closures).
- Score threshold / Top-K — **REUSE** (`DEFAULT_MIN_MATCH_SCORE`, `[:3]` slicing).
- Deterministic fallback — **REUSE** (retained Tier-1 result + status metadata).
- Mapper result persistence — **REUSE** (`save_alpha_matches`, `alpha_matches.json`, DB table, already wired into the real pipeline).
- John-20 benchmark runner — **PARTIAL REUSE**: the harness mechanism (`measure_labeled_accuracy`-style pattern) already works; what's missing is the actual product-owner-supplied data, not the runner.

No new taxonomy, embeddings, vector DB, candidate IDs, quality gate, or Canary
infrastructure is indicated by spec or code — consistent with this precheck's
own prohibitions.

## 28. Genuine PRODUCT_DECISION_REQUIRED items

Only items that cannot be resolved from the frozen plan, later requirements,
current authoritative code, or the John-labeled benchmark:

1. **John's 20 real labeled claims** (text, expected alpha(s), rubric,
   version, sign-off owner) — PD-005 remains open; nothing can formally
   graduate §5.2 to the plan's own Phase 2 acceptance without this.
2. **Exact ≥80% metric definition** — top-1 exact match vs. top-3-contains
   vs. multi-label set match vs. precision/recall/F1 — never stated anywhere found.
3. **Single- vs. multi-alpha mapping cardinality per claim** — the frozen
   plan's own text is internally inconsistent (§20 above); current code/DB
   have already committed to one answer without documented product sign-off.
4. **Role of claim `confidence` in Alpha match score** — present in the
   frozen `in:` example, intended use never stated, currently unused entirely.
5. **Whether the elaborated Tier-1 scoring formula** (0.50 keyword + 0.30
   factor + 0.08 direction + 0.12 semantic) **and the AI-alpha hard-gate
   0.35-threshold carve-out** for A101/A102/A103 are approved evolutions of
   the frozen plan's simpler text, or need explicit product sign-off as
   extensions.
6. **Formal production-authority graduation of the Tier-2 LLM classifier**
   (`semantic_authority_matrix.csv`: `PRODUCT_VALIDATION_MISSING`) — code-live
   today whenever the shared `llm_gateway` is enabled, but not yet approved as
   trustworthy without item 1/2 above.
7. **No-match wire shape** (retain-with-null vs. omit vs. sentinel) — never
   specified; current behavior is reasonable but unconfirmed.

## 29. SPEC_CODE_CONFLICTS (direct contradictions, distinct from open decisions)

1. §5.2's own worked JSON example uses a **plural** key (`"matched_alphas":
   [...]`) while §10's Week 2 acceptance-gate prose uses **singular**
   ("matched_alpha") — an inconsistency inside the frozen document itself, not
   introduced by engineering.
2. `tests/test_week2_labeled_accuracy.py` / `tests/golden_cases/labeled_claims_v1.json`
   self-describe as "the approved labeled set" / "Standalone Formal Week 2
   accuracy gate," while **PD-005 — in the same repository's own authoritative
   product-decision register — explicitly states John's 20 labels are
   `BLOCKED_BY_PRODUCT_OWNER`/absent, and explicitly prohibits substituting a
   locally invented set.** The test currently passes (≥80%) against a set its
   own product-decision register disclaims. Not resolved here.
3. The AI-alpha hard gate bypasses the frozen "threshold 0.35" rule entirely
   for A101/A102/A103 — implemented and tested, but not traced to any PD/ADR
   approval.

## 30. Summary of what is genuinely missing before §5.2 implementation can begin

Given how much is already real, tested, and wired (Tier 1 + Tier 3 in full
production use; Tier 2 code-complete and live-wired; taxonomy complete and
validated; persistence, both file and DB, complete), **the blocking gap is
not engineering** — it is exactly the two things the plan itself names as the
Phase 2 acceptance gate: **John's real 20 labeled claims, and an explicit
metric definition**, plus the smaller, genuinely-open cardinality/confidence/
formula-approval questions in §28.
