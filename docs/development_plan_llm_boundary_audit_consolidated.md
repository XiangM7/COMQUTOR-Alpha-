# Phase 0 — Development-Plan LLM Boundary Audit (Consolidated)

> Portable single-file snapshot of the main audit report, all requested inventories/matrices/plans, and the read-only verification evidence. The source files remain unchanged.

## Reading Guide

- **Part I** is the human-readable audit report.
- **Part II** contains every requested JSON/CSV audit artifact. JSON is embedded verbatim; well-formed CSV is rendered as Markdown with row/column order and cell content preserved. A malformed CSV is embedded verbatim with its affected source rows identified.
- **Part III** records a fresh 4/4 verification run and embeds the exact read-only script used to produce it.
- The manifest below records source byte sizes and SHA-256 hashes for snapshot verification.

## Source Manifest

| Component | Repository source | Bytes | SHA-256 |
| --- | --- | ---: | --- |
| Main report | `docs/development_plan_llm_boundary_audit.md` | 28649 | `b683e875f71bd246db4cec6479bf9e42b6ddbc38c70e8f09eec61b7deb967e82` |
| Development Plan Source Inventory | `docs/audit_artifacts/development_plan_source_inventory.json` | 5556 | `351785f8c6ef710b3cf183043b6ee05e1d993c14962e757254e9252f8a70c9eb` |
| Semantic Pipeline Call Graph | `docs/audit_artifacts/semantic_pipeline_call_graph.json` | 9374 | `1626d8b06412eeb2049a495a0838a545a5bae4d2e114be15df57928bed2d9a7c` |
| LLM Call-Site Inventory | `docs/audit_artifacts/llm_call_site_inventory.json` | 9604 | `5e8112f693a166234b7eab73c0ba5f7440e05c822ae6813e3f6bce20e006f13e` |
| LLM Prompt Inventory | `docs/audit_artifacts/llm_prompt_inventory.csv` | 5128 | `3081e459f599a785deef0466ef18b37cbc305f2985f4130de64734d59616ba13` |
| Provider-Call Baseline | `docs/audit_artifacts/provider_call_baseline.json` | 6245 | `df16f290c7430dff71e288f6f6131997a12b4728c80be26873aa8f11e27491ef` |
| Structured Adapter Gap Matrix | `docs/audit_artifacts/structured_adapter_gap_matrix.csv` | 2367 | `af71e2b39582ad802a83db5ccd9c669d980d73eaaf765d6a8e266b24b69971d1` |
| Alpha Mapper Gap Matrix | `docs/audit_artifacts/alpha_mapper_gap_matrix.csv` | 1638 | `a4a09366efeb5214a5b734cb1c87516dec8871e095129d3cc1ecaf073284fcd5` |
| Structure Extractor Gap Matrix | `docs/audit_artifacts/structure_extractor_gap_matrix.csv` | 5327 | `bff086e86a2b45c591b690f0a7695385eddf3d2f1a661ec6167bbb7b329deec9` |
| TradingAgents Modification Audit | `docs/audit_artifacts/tradingagents_modification_audit.csv` | 4676 | `bd0f3777f929faa3fbf490ab99e5a421da3704430d4067ff62e53a9d5ede4ea4` |
| Deterministic Core Boundary Audit | `docs/audit_artifacts/deterministic_core_boundary_audit.json` | 8912 | `7672c8af56fca497fe0ad0c6e630a87a95030c2b890769cd0e3347691d5b2480` |
| Replay Semantic Reproducibility | `docs/audit_artifacts/replay_semantic_reproducibility.json` | 5009 | `15298198df59c69b13db4d3f5a36b8d2157509f32b08819bdefa65d276a7967c` |
| Development Plan Compliance Matrix | `docs/audit_artifacts/development_plan_compliance_matrix.csv` | 8127 | `9f6a9a31e68fa2a005bfa1e1075c62872564c54c7faee0f246b467b9c6f88f37` |
| Proposed Phase 1-3 Migration Plan | `docs/audit_artifacts/proposed_phase_1_3_plan.json` | 8326 | `0774acc8046ee12d1718a463b2c30781ca6f60ad00a2d179117f49f30cb9453b` |
| Verification script | `scripts/audit_llm_boundary.py` | 5856 | `62cd92099bd825acf1c6c8dba09f6d3c55e8a72432d3039fad64a0c1911b15c7` |

## Part I — Main Audit Report

Source: `docs/development_plan_llm_boundary_audit.md`

## Phase 0 — Development-Plan LLM Boundary and Repository Audit

Read-only architecture audit. No production behavior, LLM/Provider call, database write, or historical source artifact was changed by this audit. No commit/push occurred.

### 1. Executive Verdict

- **Canonical Development Plan source: NOT FOUND IN REPOSITORY.** No file named or titled "COMQUTOR Alpha Development Plan v1.0" exists anywhere in this repo (PDF/DOCX/Markdown). This is a zero-canonical-copy situation, not a multi-version-ambiguity situation — see §2 and `docs/audit_artifacts/development_plan_source_inventory.json`. This audit therefore treats the task instructions' own quoted §5.1/§5.2/§5.3 wording as authoritative input, cross-checked against independent in-repo paraphrases wherever they exist.
- **§5.1 Structured Output Adapter: DIVERGED (but stricter/safer than the plan's literal wording).** Claim/evidence segmentation is fully deterministic; the LLM is an optional, bounded per-batch *enrichment* layer (entities/factors/direction/confidence only), not the primary NL→claim converter the plan's wording implies. Off by default (`COMQUTOR_WEEK2_LLM_ENABLED`).
- **§5.2 Alpha Mapper: COMPLIANT.** All three tiers present, correctly prioritized, threshold 0.35 and top-3 output unchanged. The plan-mandated 20-labeled-claims / ≥80%-accuracy evaluation was **not found** in this repository (MISSING, see compliance matrix).
- **§5.3 Structure Extractor: DIVERGED.** A third, plan-unlisted edge source exists in production (`CANONICAL_BLOCK`, sourced from TradingAgents' own single existing call via a prompt-injected structured-output contract), alongside the plan's two expected sources (LLM/rule).
- **TradingAgents modification rule ("output capture hooks only"): DIVERGED — this is the audit's single highest-severity finding.** `comqutor_alpha/llm/canonical_prompt_injection.py` monkeypatches all 12 native agent prompt-builder modules at runtime to append a new structured-output instruction. Zero files under `tradingagents/` are edited on disk and zero new LLM calls are added, but the *effective prompt content* every agent receives is changed for the duration of every run. This satisfies the letter of "don't edit tradingagents/ files" while not satisfying the substance of "output capture hooks only."
- **Deterministic core (Activation/Conflict/Graph/Exposure/replay identity/API serialization): COMPLIANT.** Zero LLM imports, confirmed by grep and by the new read-only `scripts/audit_llm_boundary.py` (all 4 automated checks PASS).
- **Replay Provider-zero path: COMPLIANT for zero-Provider-calls, PARTIAL for semantic reproducibility.** Replay never calls TradingAgents/an LLM/a market-data provider/the DB — confirmed both by direct code read and by the automated script. It cannot, however, reproduce a historical live run's LLM-tier decisions (it always substitutes the deterministic fallback) — see §16 and `replay_semantic_reproducibility.json`.
- **Evidence Stance: correctly out of Development-Plan scope.** Zero LLM calls anywhere in this module; shadow-mode only; John-later-requirement, not source-frozen.
- **No production code, historical source artifact, or `outputs/runs/` content was changed. No commit/push.**

### 2. Canonical Development Plan Source

Search commands run (see `development_plan_source_inventory.json` for the full record):

```
find . -iname '*COMQUTOR*Development*Plan*' -o -iname '*development_plan*' -o -iname '*Development_Plan*'
grep -rl "COMQUTOR Alpha Development Plan" . --include=*.md --include=*.txt --include=*.pdf
grep -rl "Development Plan" . --exclude-dir=.git --exclude-dir=node_modules --exclude-dir=.venv
```

**Result: zero files found matching the Development Plan by filename or by exact title string.** `DEVELOPMENT_PLAN_VERSION_AMBIGUITY` does not apply (no two differing copies exist to disagree) — the correct flag is that the canonical source document itself is absent from this repository. The Development Plan is, however, referenced by name dozens of times across prior sprint reports and frozen-constant docstrings (see the six corroborating fragments quoted in the JSON artifact), alongside two other named external documents ("Helix Quantum Intelligence Operating System White Paper v2.0", "SIC Omnibus Provisional Draft v2") that together form the project's documented three-document source-of-truth hierarchy (`docs/week4_spec_freeze_audit.md` §3). Every plan requirement this report cites is either (a) quoted verbatim from the task instructions themselves, or (b) independently corroborated by an in-repo paraphrase — the two are distinguished throughout.

### 3. Frozen LLM Boundaries (as given in task instructions, treated as authoritative)

- **Module scope**: all new code lives in `comqutor_alpha/`; TradingAgents source modified only minimally; modifications are output capture hooks.
- **§5.1**: LLM converts NL agent output → standard claim schema; downstream consumes only this JSON; 12 required fields; safe default on parse failure; malformed JSON must not propagate/crash; NVDA acceptance covers fundamental/news/sentiment/technical.
- **§5.2**: 3-tier matching (keyword+factor → LLM → rule fallback); threshold 0.35; top-3 output; John's 20 labeled claims; ≥80% accuracy target.
- **§5.3**: LLM extracts cause-effect relations → StructureNode/StructureEdge; strict JSON; fallback on empty result; duplicate/synonym merge; edge types causal/supportive/conflicting.

Evidence Stance, ticker specificity, Clause Graph, Counter-Alpha stance, and dynamic invalidation conditions are **not** part of this frozen scope (see §14).

### 4. Current Semantic Pipeline

Full node-by-node call graph with file/symbol/caller/callee/schemas/LLM-reachability/replay-reachability/production-score-impact: `docs/audit_artifacts/semantic_pipeline_call_graph.json`.

High-level shape:

```
raw_agent_outputs.json (TradingAgents, 12 native agents, prompt-injected with the
  COMQUTOR Structure Output Contract for the duration of the run)
  -> structured_output_adapter.adapt_run_outputs   (deterministic segmentation,
     OPTIONAL bounded LLM per-batch enrichment for 6 agent types)
  -> alpha_mapper.build_alpha_matches_payload       (deterministic Tier 1 scoring,
     OPTIONAL LLM Tier 2 select/defer among >=2 eligible candidates)
  -> structure_extractor.build_extracted_structures_payload (deterministic rule
     edges + OPTIONAL per-claim LLM edges + TradingAgents-native canonical-block edges)
  -> graph_engine.pipeline (deterministic graph admission + activation v2)
  -> conflict_engine.conflict_detector (deterministic conflict arbitration)
  -> artifact_export.finalize_completed_run_artifacts (extraction/consolidation only)
  -> API/artifacts/UI (read-only serialization of already-computed artifacts)
```

Four distinct paths are distinguished throughout this audit and the call-graph JSON: **A** live run, **B** historical source artifact (read-only GET), **C** Architecture Replay, **D** test/fake.

### 5. Live Call Graph

See `semantic_pipeline_call_graph.json`, `path_summary.A_live_run_path`. Entry: `POST /api/research` → `run_research_request` (`routes_research.py:2286`) → `run_original_tradingagents_research`/`run_streaming_tradingagents_research` (`tradingagents_runner.py:113`/`280`) → `_run_week1_week2_artifact_pipeline` (`routes_research.py:694`) → `_run_week3_graph_pipeline` (`routes_research.py:2101`).

### 6. Replay Call Graph

See `semantic_pipeline_call_graph.json`, `path_summary.C_architecture_replay_path`. Entry: `run_structure_replay` (`replay/pipeline.py:363`), reprocessing only the source run's saved `raw_agent_outputs.json`, writing exclusively to a new `outputs/replays/replay-<ts>-<uuid>/` directory. `llm_gateway=None` is explicit (adapter) or defaulted (mapper/extractor) at every stage; `tradingagents_calls`/`llm_provider_calls`/`market_data_provider_calls`/`database_writes` are hardcoded literal `0` in every `ReplayResult` return path.

### 7. LLM Call-Site Inventory

Full inventory: `docs/audit_artifacts/llm_call_site_inventory.json` (COMQUTOR Week2 tier, chokepointed through `Week2LLMGateway.invoke_json`) plus the repo-wide sub-agent findings for the TradingAgents native tier (13 native call sites across 12 agents + 1 reflection call), test/fake sites, and dead/legacy code. Three real COMQUTOR call sites: `CS-01` claim_batch_enrichment (§5.1), `CS-02` alpha_classifier (§5.2), `CS-03` structure_extractor (§5.3) — all three share one `Week2LLMGateway` instance per run and therefore one per-run call budget (default 32, server cap 100), not independent per-module budgets. No call site was misreported from a bare import or variable name; every entry above was confirmed by locating the actual `.invoke(`/`invoke_json(` call.

### 8. Prompt Inventory

Full inventory with hashing/versioning/retry/failure behavior per prompt: `docs/audit_artifacts/llm_prompt_inventory.csv`. Six prompt families: three Week2LLMGateway task instructions (claim_batch_enrichment / alpha_classifier / structure_extractor), the shared gateway wrapper, the TradingAgents Structure Output Contract suffix (`canonical_relation_prompt.py`, deterministically hashable via `compute_prompt_contract_sha256`, recorded per-run in `tradingagents_comqutor_vocabulary_snapshot.json`), and the 12 native TradingAgents agent prompts themselves (upstream, unmodified on disk). All three Week2 prompts require strict JSON and restrict output vocabulary to caller-supplied allowed IDs; none allow free invention of new Alpha/factor/relation IDs; none allow fabricated source quotes (the Structure Output Contract explicitly requires `evidence_quote` to be a verbatim substring of the agent's own report, rule 11 of 14).

### 9. Provider-Call Baseline

Full stage matrix and direct answers to all required questions: `docs/audit_artifacts/provider_call_baseline.json`. Key facts, never invented:

- Adapter is called **per raw agent output (report), batched** in groups of ≤64 segments — never per individual claim.
- Alpha Mapper Tier 2 is called **only for claims with ≥2 deterministically-eligible candidates** — this is the code-level definition of "ambiguous" (`alpha_mapper.py:340`).
- Structure Extractor is called **per claim** with ≥2 deterministic factors.
- Exact per-run call counts: **UNKNOWN_NOT_INSTRUMENTED** — no fleet-wide counter exists; each run's own realized count *is* reconstructable from that run's own `structured_agent_outputs.json`/`alpha_matches.json`/`extracted_structures.json` metadata, but no aggregate baseline was computed in this repo prior to this audit, and this audit did not fabricate one.
- **No LLM response cache exists anywhere.** Duplicate-text re-calling is a real, currently-unaddressed risk when the LLM tier is enabled.
- Replay cannot accidentally trigger a Provider call (§6, confirmed by both manual read and automated script).

### 10. §5.1 Structured Output Adapter Verdict

**5.1_STATUS: DIVERGED** (stricter/safer than literal plan wording, not unsafe).

Full field-level matrix: `docs/audit_artifacts/structured_adapter_gap_matrix.csv`. Evidence: claim/evidence text is deterministically segmented first and is **never** LLM-originated; an LLM enrichment batch must return `claim`/`evidence`/`source_section` byte-for-byte identical to the input or the entire batch is rejected and falls back to deterministic enrichment (`_validate_llm_batch_enrichment`, `structured_output_adapter.py:882-953`). All 12 required fields are present and validated (`validate_structured_output`). Malformed JSON/timeout/budget-exhaustion never propagate or crash (`Week2LLMGateway.invoke_json`'s exhaustive except chain, `week2_llm.py:187-196`). LLM_STRUCTURED_AGENTS covers fundamental/fundamentals/news/sentiment/technical/market — a superset of the plan's named four. Boilerplate/disclaimer/transition filtering and dedupe both happen deterministically **before** any LLM involvement, never after.

### 11. §5.2 Alpha Mapper Verdict

**5.2_STATUS: COMPLIANT** (implementation), **MISSING** (plan-mandated evaluation).

Three-tier matrix: `docs/audit_artifacts/alpha_mapper_gap_matrix.csv`. Tier 1 (keyword+factor+direction+semantic, weights 0.50/0.30/0.08/0.12) always runs first for all 10 taxonomy alphas. Tier 2 LLM classifier can only select-or-defer among the ≤3 already-deterministically-eligible candidates (`allowed_alpha_ids`); cannot create candidates, change admissibility, or emit a trading decision; gated behind `COMQUTOR_WEEK2_LLM_ENABLED`, off by default. Tier 3 fallback is literally "keep the pre-computed deterministic decision" on any LLM failure — never a crash, never a bare "unknown." Threshold 0.35 and top-3 output confirmed unchanged since Week 2. Evidence Stance is co-located in the same function (`map_claim_to_alpha`) and the same `alpha_matches.json` artifact, but does **not** share scoring/eligibility/matched_alpha authority — see §14 for the precise distinction between code co-location and decision authority. **John's 20 labeled claims and the ≥80% accuracy evaluation were not found anywhere in this repository** — this is reported as MISSING, not assumed complete and not assumed never-run.

### 12. §5.3 Structure Extractor Verdict

**5.3_STATUS: DIVERGED.**

Full Q&A matrix with edge-source classification: `docs/audit_artifacts/structure_extractor_gap_matrix.csv`. Edge types are exactly `{causal, supportive, conflicting}` (`VALID_EDGE_TYPES`, `structure_schema.py:16`) with no additions. Three edge sources feed one merged graph: `LLM_EXTRACTED` (dedicated `structure_extractor` Week2LLMGateway task, per-claim, deterministic evidence-backing + causal-direction re-validated before acceptance), `RULE_EXTRACTED` (`relation_grammar.py` pattern rules, always the fallback and the only path when the gateway is off), and `CANONICAL_BLOCK` (edges reported inside TradingAgents' own single existing call's response, via the prompt-injected Structure Output Contract — **not** a second LLM call, but also **not** the plan's named §5.3 LLM extractor). All three sources share one deterministic dedup key and one lineage/provenance contract. The `CANONICAL_BLOCK` source is the direct consequence of the TradingAgents-modification finding in §13 — the two are one underlying architectural decision, reported from two angles.

### 13. TradingAgents Modification Verdict

Full modification table: `docs/audit_artifacts/tradingagents_modification_audit.csv`.

- **On-disk footprint inside `tradingagents/` is minimal**: one 9-line, zero-importer dead shim (`tradingagents/comqutor_outputs.py`). A clean vendor-add baseline commit (`cc97cb6d`, TradingAgents v0.1.0) exists in git history; 160 of 162 subsequent commits touching `tradingagents/` are attributed to upstream-style contributors and contain zero "comqutor" string hits in their diffs (strong internal signal, not a cryptographic guarantee — no `upstream/*` ref was fetched in this offline audit).
- **(a) Has any agent prompt been modified to add canonical-relation-block output?** Yes, functionally, via `comqutor_alpha/llm/canonical_prompt_injection.py:66-100`, which monkeypatches the `get_language_instruction` attribute already imported by all 12 native agent modules, for the duration of every `propagate()`/`stream()` call (activated at `tradingagents_runner.py` lines ~171 and ~383). The injected text (`canonical_relation_prompt.py:103-174`) instructs the LLM to append a `COMQUTOR_CANONICAL_RELATIONS` JSON block after its normal report. Zero files under `tradingagents/` are edited on disk.
- **(b) Hooks-only or behavior change?** Both exist and must be judged separately: `tradingagents_output_writer.py` (reads `final_state` after the run, writes JSON) is a genuine passive capture hook. `canonical_prompt_injection.py` is not passive — it actively changes what every agent is asked to produce.
- **(c) Extra LLM calls added?** No. Confirmed by direct grep of `canonical_relation_block.py`/`structured_output_adapter.py`/`tradingagents_output_writer.py` for `.invoke(`/`ChatOpenAI(`/`ChatAnthropic(`/`get_llm(` — zero hits. The canonical block is parsed out of the same single response each agent already produces.
- **This is the audit's central, highest-severity compliance finding** (DIVERGED/MAJOR in the compliance matrix): it satisfies "don't edit files under `tradingagents/`" literally, while not satisfying "output capture hooks only" in substance. This is a product decision, not an engineering defect — flagged, not resolved, by Phase 0 (see Proposed Addendum, §19).

### 14. Evidence Stance Provenance

- **Classification: C — John-later-requirement**, not A (source-frozen) and not B (directly implied by source-frozen functionality). No fragment of the Development Plan found anywhere in this repository (§2) mentions stance, polarity, or the five-way `supports_alpha`/`opposes_alpha`/`mentions_alpha`/`neutral_background`/`supports_counter_alpha` vocabulary. The module's own delivery report is explicit about this provenance: `docs/evidence_stance_and_review_sample_report.md` attributes its test cases and validation criteria directly to "John's own fixed test case" / "John's own judgment," never to the Development Plan.
- **Zero LLM calls anywhere in `evidence_stance.py`** — confirmed by import-statement inspection (§16 of the deterministic-core-boundary artifact) and corroborated by the module's own prior-sprint AST-import-graph proof that it is a dependency-free leaf module, never imported by `activation_scorer_v2.py`/`conflict_detector.py`, and never importing `alpha_mapper.py`.
- **Not Alpha Mapper Tier 3.** Tier 3 in the Development Plan sense is the *rule fallback when the LLM classifier fails* (§11) — a completely different mechanism, already implemented and unrelated to Evidence Stance. Evidence Stance instead runs as an always-on, additive, shadow-mode classification alongside Tier 1 scoring, inside the same `map_claim_to_alpha` function call and the same `alpha_matches.json` artifact.
- **Does it substitute for the ambiguous-semantics-processing the plan expected an LLM to do?** In effect, yes for a narrow slice: it performs rule-based, alpha-relative direction/stance classification of free text, which is exactly the kind of task the Development Plan's overall philosophy (LLM handles ambiguity, rules handle the rest) would have routed to an LLM. It was built as a **deterministic** substitute specifically because the task that commissioned it explicitly forbade any new LLM/Provider call.
- **Does it affect production scoring today?** No — `effect_mode="shadow"`, `stance_effect_applied=False` on every artifact; proven unchanged both structurally (import-graph) and empirically (real replay comparison against the pre-Evidence-Stance baseline) in the prior sprint that built it.
- **Future role**: could become a validator/fallback signal once John's 50-row human review (currently `PENDING`) completes, but that decision requires explicit product approval, not an inference from this audit.
- **Fields requiring product approval before any LLM output could ever be used for stance**: none currently planned — Evidence Stance LLM-ification is deliberately unscoped (Proposed Addendum, §19) pending a future explicit request.

### 15. Deterministic Core Boundary

Full 15-module matrix: `docs/audit_artifacts/deterministic_core_boundary_audit.json`. Every module — taxonomy loading, Evidence Fact grouping, claim dedupe, graph admission/normalization, Activation scoring + qualification ceiling, Exposure calculation, Conflict pair registry/admission/score/main-conflict arbitration, ticker/run identity, artifact export, replay identity, API serialization — has **zero LLM imports**, confirmed both manually (grep) and mechanically (`scripts/audit_llm_boundary.py::check_deterministic_core_no_llm_import`, which re-runs the same check on demand). `DOWNSTREAM_FREE_TEXT_LEAKAGE` is **not** flagged for any of these 14 modules — all consume only already-structured JSON. It **is** correctly present for the 15th module, Evidence Stance, whose entire job is re-parsing claim/evidence free text — but that module never feeds a decision any of the other 14 treat as authoritative, so it is a contained, documented exception rather than a leakage defect.

### 16. Replay Semantic Reproducibility

**REPLAY_SEMANTIC_REPRODUCIBILITY: PARTIAL.** Full detail: `docs/audit_artifacts/replay_semantic_reproducibility.json`.

Confirmed **PASS** on every zero-Provider/zero-DB/zero-TradingAgents guarantee (both by direct code read and the automated script). Confirmed **gap**: replay always forces `llm_gateway=None`, so it can never reproduce a historical live run's LLM-tier enrichment/classification/edge decisions — it silently substitutes the deterministic fallback for exactly those claims/edges instead, and `replay_comparison.json` will show the resulting deltas honestly (it does not hide this) but does not attempt to close the gap. Practical impact is currently believed low because the LLM tier defaults off, but this was **not** independently verified across every historical run in `outputs/runs/` — reported as an acknowledged unknown, not swept under a PASS verdict. `CANONICAL_BLOCK` edges, being derived from already-saved raw text, **do** replay identically.

### 17. Retry / Cache / Observability

- **Retry**: `Week2LLMGateway` — yes, explicit bounded loop, default 1 retry, server cap 2 (`week2_llm.py:176-196`). TradingAgents native agent calls — **UNKNOWN/SDK-default**, no explicit COMQUTOR-side retry wrapper found (per repo-wide sub-agent inventory).
- **Timeout**: `Week2LLMGateway` — yes, explicit wall-clock deadline via `ThreadPoolExecutor`, default 15s, bounded [1, 120]s (`call_with_timeout`, `week2_llm.py:55-65`). Native agents — **UNKNOWN/SDK-default**.
- **JSON repair / schema validation**: yes, strict, at every one of the three Week2 call sites (`_validate_llm_batch_enrichment`, the `alpha_classifier` inline validator, `_validated_llm_edges`) — none silently accept a malformed payload.
- **Safe default / error logs**: yes — every gateway failure is logged with a stable `error_code` to `error_logs/week2_llm_errors.jsonl`; adapter failures additionally log to `error_logs/structured_output_adapter_errors.jsonl` with secrets/local-path redaction (`_redact_secrets`).
- **Cache**: **NOT_IMPLEMENTED** anywhere in the LLM call path (repo-wide search, zero hits beyond an unrelated yfinance ticker-lookup `lru_cache`).
- **Prompt/model version, input/output hash, latency, token usage, cost**: **NOT_IMPLEMENTED** as first-class fields on any LLM call site. The Structure Output Contract prompt suffix is the one exception with a real deterministic hash (`compute_prompt_contract_sha256`, recorded per run).
- **Rate-limit handling, cancellation**: not found as dedicated mechanisms beyond the generic exception→retry→give-up chain above.
- Test fakes (`_FakeBatchLLMGateway`, `FakeClient`, `MagicMock`) exposing retry/cache-like attributes in `tests/` were **not** treated as evidence of a production capability — flagged explicitly per the "no unproven inference" rule.

### 18. Compliance Matrix

Full machine-readable matrix (plan_section / requirement / evidence / file / symbol / behavior / status / severity / source classification / recommended phase / notes): `docs/audit_artifacts/development_plan_compliance_matrix.csv`. Summary counts: 9 COMPLIANT, 4 DIVERGED (module scope's TradingAgents rule, §5.1 LLM-vs-deterministic inversion, §5.3 third edge source, replay LLM-tier reproducibility), 2 MISSING/NOT_IMPLEMENTED (20-labeled-claims evaluation, LLM response cache), 1 NOT_APPLICABLE (Evidence Stance, correctly excluded from Development-Plan scope).

### 19. Phase 1–3 Recommendations

Full detail (gap / files / reusable code / provider/prompt/schema/replay impact / backward compatibility / tests needed / cutover / blockers / explicit non-goals) for each phase: `docs/audit_artifacts/proposed_phase_1_3_plan.json`.

- **Phase 1 (Structured Output Adapter)**: implementation is already compliant; the real work is measuring LLM-enrichment quality before any default-on rollout decision, since the tier is currently off by default and its real-world accuracy is unmeasured.
- **Phase 2 (Hybrid Alpha Mapper)**: implementation is already compliant; the blocking gap is that John's 20 labeled claims and the ≥80% accuracy evaluation do not exist in this repository and must be sourced from the product owner.
- **Phase 3 (LLM Structure Extractor)**: implementation is already compliant; the recommended work is purely reporting/documentation — surfacing the already-tracked `llm_edge_count`/`deterministic_edge_count`/`canonical_relation_edge_count` split so the `CANONICAL_BLOCK` source's real contribution is visible, not silently folded into "the LLM extractor."
- **Proposed Addendum**: a product decision on whether `canonical_prompt_injection.py`'s runtime monkeypatch satisfies "output capture hooks only" (§13). Evidence Stance LLM-ification is explicitly and deliberately **not** proposed anywhere in this report, per instruction — it remains fully unscoped for any future request to address separately.

### 20. Unknowns and Required Product Decisions

- Whether `canonical_prompt_injection.py`'s prompt-content change at runtime is acceptable under "output capture hooks only," or requires either a design change or an explicit Development-Plan amendment (§13, §19).
- Real per-run/fleet-wide LLM call counts for all three Week2 tasks — `UNKNOWN_NOT_INSTRUMENTED`, not fabricated (§9).
- Whether any historical run in `outputs/runs/` actually had `COMQUTOR_WEEK2_LLM_ENABLED=true` — not enumerated in this audit (§16).
- Whether the 160 non-`xiangmao` commits touching `tradingagents/` are byte-identical to genuine upstream TradingAgents commits — best available internal signal only (zero "comqutor" string hits in their diffs); a true diff against `upstream/main` requires network access this offline audit did not use (§13).
- Location/existence of John's 20 labeled Alpha-Mapper claims and any historical ≥80%-accuracy evaluation run — not found in this repository (§11, §18).
- Whether `tradingagents/comqutor_outputs.py` (the dead 9-line shim) should be removed, given it appears to have zero importers anywhere in the repo (§13).

### 21. Tests and Commands

Targeted offline suite (Structured Output Adapter, Alpha Mapper, Week2 LLM gateway, Structure Extractor, Replay Identity, Evidence Stance classifier/integration, Evidence Review Sample, Artifact Export/API, Conflict Detector) and the full offline suite (`pytest -q -m "not integration"`) were both run — see the final terminal summary for exact pass/fail counts. `scripts/audit_llm_boundary.py` (new, read-only, not imported by any production module, zero network/DB/Provider calls) was run directly and reports `OVERALL: PASS` on all 4 structural invariants it re-derives mechanically. `ruff check` on the new script: clean.

### 22. Worktree/Source Integrity

Git baseline recorded at the start (branch `comqutor-structure-layer`, HEAD `b5837e80a4550fc35165d0013a8ef0f27ccb4c8f`) and re-verified at the end of this audit — see the final terminal summary. All pre-existing dirty-worktree modifications from prior sprints were preserved untouched; this audit's only new filesystem changes are `scripts/audit_llm_boundary.py` and the files under `docs/` (this report plus `docs/audit_artifacts/*`). No file under `outputs/runs/` was modified. No historical source artifact's sha256/size/mtime was touched (this audit never wrote to any existing run directory).

### 23. Outputs

- Main report: `docs/development_plan_llm_boundary_audit.md` (this file)
- `docs/audit_artifacts/development_plan_source_inventory.json`
- `docs/audit_artifacts/semantic_pipeline_call_graph.json`
- `docs/audit_artifacts/llm_call_site_inventory.json`
- `docs/audit_artifacts/llm_prompt_inventory.csv`
- `docs/audit_artifacts/provider_call_baseline.json`
- `docs/audit_artifacts/structured_adapter_gap_matrix.csv`
- `docs/audit_artifacts/alpha_mapper_gap_matrix.csv`
- `docs/audit_artifacts/structure_extractor_gap_matrix.csv`
- `docs/audit_artifacts/tradingagents_modification_audit.csv`
- `docs/audit_artifacts/deterministic_core_boundary_audit.json`
- `docs/audit_artifacts/replay_semantic_reproducibility.json`
- `docs/audit_artifacts/development_plan_compliance_matrix.csv`
- `docs/audit_artifacts/proposed_phase_1_3_plan.json`
- `scripts/audit_llm_boundary.py` (read-only verification script)

## Part II — Complete Audit Artifacts

### Appendix 1 — Development Plan Source Inventory

Source: `docs/audit_artifacts/development_plan_source_inventory.json`

Purpose: Canonical-source search record and corroborating repository references.

```json
{
  "audit": "phase_0_development_plan_llm_boundary_audit",
  "generated_at": "2026-08-05T00:00:00Z",
  "search_commands": [
    "find . -iname '*COMQUTOR*Development*Plan*' -o -iname '*development_plan*' -o -iname '*Development_Plan*'",
    "grep -rl \"COMQUTOR Alpha Development Plan\" . --include=*.md --include=*.txt --include=*.pdf",
    "grep -rl \"Development Plan\" . --exclude-dir=.git --exclude-dir=node_modules --exclude-dir=.venv"
  ],
  "canonical_document_found": false,
  "verdict": "DEVELOPMENT_PLAN_SOURCE_NOT_FOUND_IN_REPOSITORY",
  "notes": [
    "No file named or titled 'COMQUTOR Alpha Development Plan v1.0' (PDF, DOCX, or Markdown) exists anywhere in this repository as a standalone document. This is not a multi-version-ambiguity case (no two differing copies were found) -- it is a zero-canonical-copy case, so DEVELOPMENT_PLAN_VERSION_AMBIGUITY does not apply; the correct flag is that the source itself is absent from the repo.",
    "The Development Plan is referenced extensively, by name, as an external source-of-truth document across many in-repo artifacts, alongside two other named external documents: 'Helix Quantum Intelligence Operating System White Paper v2.0' and 'SIC Omnibus Provisional Draft v2' (see docs/week4_spec_freeze_audit.md section 3, 'Source-of-Truth Hierarchy').",
    "Because the source document itself is not in the repo, every Development Plan requirement cited in this audit (including the frozen §5.1/§5.2/§5.3 wording given verbatim in the task instructions) is treated as authoritative task input, cross-checked wherever possible against independent paraphrases/quotations of the plan already committed to this repository in prior sprints (see corroborating_fragments below). Where the task's own quoted wording and the repo's independent paraphrase agree, confidence is high; where a plan requirement has no in-repo corroboration at all, it is marked evidence_basis: 'task_instructions_only'."
  ],
  "corroborating_fragments_found_in_repo": [
    {
      "file": "docs/week2_completion_report.md",
      "line": 21,
      "quote": "初始 match threshold 与 Development Plan 对齐为 `0.35`。",
      "corroborates": "§5.2 Alpha Mapper minimum match score = 0.35"
    },
    {
      "file": "docs/week2_completion_report.md",
      "line": 24,
      "quote": "deterministic logic 决定 admissibility。LLM 只能在最多三个 admissible candidates 中 select 或 defer，不能创建 Alpha、恢复非法候选或改写 deterministic no-match。",
      "corroborates": "§5.2 Tier 2 LLM classifier: select-or-defer only, over deterministic-admissible candidates, top-3 cap"
    },
    {
      "file": "docs/week2_completion_report.md",
      "line": 78,
      "quote": "Development Plan 中的 `alpha_matches` 和 `structure_graphs` 数据库表仍然推迟，不能视为已完成。",
      "corroborates": "Development Plan specifies alpha_matches / structure_graphs as eventual DB tables"
    },
    {
      "file": "docs/week3_completion_report.md",
      "line": 121,
      "quote": "Development Plan 原始方案使用单一 `agent_output_id` 外键字段。",
      "corroborates": "Structured Output Adapter's original identity model (agent_output_id)"
    },
    {
      "file": "comqutor_alpha/exposure_engine.py",
      "line": 3,
      "quote": "Implements exactly the Development Plan's Exposure formula:: exposure = historical_mapping * 0.50 + current_evidence * 0.30 + agent_confidence * 0.20",
      "corroborates": "Exposure formula is Development-Plan-sourced (not a §5.1/5.2/5.3 item, cited for source-hierarchy context only)"
    },
    {
      "file": "comqutor_alpha/conflict_engine/conflict_schema.py",
      "line": 3,
      "quote": "Every rule here is either SOURCE-FROZEN (Development Plan v1.0) or APPROVED -- SPEC-FROZEN FOR W4.1",
      "corroborates": "Conflict formula is Development-Plan-sourced (not a §5.1/5.2/5.3 item, cited for source-hierarchy context only)"
    }
  ],
  "task_instruction_frozen_llm_boundaries_treated_as_authoritative_for_this_audit": {
    "module_scope": [
      "All new code lives in comqutor_alpha/",
      "TradingAgents source is modified only minimally",
      "TradingAgents modifications are output capture hooks"
    ],
    "section_5_1_structured_output_adapter": "Converts each agent's natural-language output into standard claim schema; downstream modules consume only this JSON; required fields run_id/ticker/agent/timestamp/claim/evidence/entities/factors/direction/confidence/source_type/source_refs; safe default on LLM parse failure; malformed JSON must not propagate; parsing failure must not crash the run; NVDA acceptance includes fundamental/news/sentiment/technical agents.",
    "section_5_2_alpha_mapper": "Three-tier matching in priority order: (1) keyword+factor match, (2) LLM classification, (3) rule-based fallback if LLM fails; claim+evidence+factors combined; first version threshold 0.35; top-3 Alpha output; John's 20 labeled claims; overall accuracy target >= 80%.",
    "section_5_3_structure_extractor": "LLM extracts cause-effect relations; outputs StructureNode/StructureEdge; strict JSON; fallback on empty result; duplicate/synonym merging; minimum edge types causal/supportive/conflicting."
  },
  "explicitly_not_development_plan_content": [
    "Evidence Stance (supports_alpha/opposes_alpha/mentions_alpha/neutral_background/supports_counter_alpha)",
    "ticker specificity gating",
    "Clause Graph",
    "Counter-Alpha stance",
    "dynamic invalidation conditions"
  ]
}
```

### Appendix 2 — Semantic Pipeline Call Graph

Source: `docs/audit_artifacts/semantic_pipeline_call_graph.json`

Purpose: Live, historical-read, replay, and test/fake execution paths.

```json
{
  "audit": "phase_0_development_plan_llm_boundary_audit",
  "generated_at": "2026-08-05T00:00:00Z",
  "legend": {
    "path_class": {
      "A": "Live research entrypoint path (POST /api/research, real TradingAgents run)",
      "B": "Historical source artifact path (already-persisted outputs/runs/<run_id>/*.json, read-only)",
      "C": "Architecture Replay path (comqutor_alpha/replay/pipeline.py, offline, Provider-zero)",
      "D": "Test/fake path (mocked LLM clients, fixtures)"
    }
  },
  "nodes": [
    {
      "id": "api_post_research",
      "file": "comqutor_alpha/api/routes_research.py",
      "symbol": "run_research_request",
      "line": 2286,
      "caller": "FastAPI route POST /api/research (routes_research.py:3252)",
      "callee": ["run_original_tradingagents_research", "run_streaming_tradingagents_research", "_run_week1_week2_artifact_pipeline", "_run_week3_graph_pipeline"],
      "input_artifact": "ResearchRequest payload (ticker, profile, etc.)",
      "output_artifact": "run_dir with raw_agent_outputs.json + all downstream artifacts",
      "can_call_llm": true,
      "can_call_market_data_provider": true,
      "replay_invokes": false,
      "affects_production_score": true,
      "path_class": "A"
    },
    {
      "id": "tradingagents_invocation",
      "file": "comqutor_alpha/runners/tradingagents_runner.py",
      "symbol": "run_original_tradingagents_research / run_streaming_tradingagents_research",
      "line": 113,
      "caller": "run_research_request",
      "callee": "tradingagents.graph.trading_graph.TradingAgentsGraph.propagate() / .graph.stream()",
      "input_artifact": "ticker/trade_date/config",
      "output_artifact": "raw_agent_outputs.json (12 native TradingAgents agent LLM outputs)",
      "can_call_llm": true,
      "can_call_market_data_provider": true,
      "replay_invokes": false,
      "affects_production_score": true,
      "path_class": "A",
      "note": "Wrapped in comqutor_structure_output_contract_scope() (canonical_prompt_injection.py) for the duration of the call -- monkeypatches get_language_instruction on all 12 native agent modules to append the COMQUTOR Structure Output Contract suffix. Adds zero new LLM calls; reuses each agent's own single existing call."
    },
    {
      "id": "structured_output_adapter",
      "file": "comqutor_alpha/structure_engine/structured_output_adapter.py",
      "symbol": "save_structured_agent_outputs -> adapt_run_outputs -> adapt_raw_agent_outputs -> _llm_batch_enrichment",
      "line": 1482,
      "caller": "_run_week1_week2_artifact_pipeline (routes_research.py:706) / run_structure_replay (replay/pipeline.py:405, llm_gateway=None)",
      "callee": "Week2LLMGateway.invoke_json('claim_batch_enrichment', ...)",
      "input_artifact": "raw_agent_outputs.json",
      "output_artifact": "structured_agent_outputs.json",
      "can_call_llm": true,
      "can_call_market_data_provider": false,
      "replay_invokes": true,
      "replay_llm_gateway_value": "None (hardcoded)",
      "affects_production_score": true,
      "path_class": "A/C"
    },
    {
      "id": "alpha_mapper",
      "file": "comqutor_alpha/structure_engine/alpha_mapper.py",
      "symbol": "save_alpha_matches -> build_alpha_matches_payload -> map_structured_records -> map_claim_to_alpha -> _apply_optional_classifier",
      "line": 697,
      "caller": "_run_week1_week2_artifact_pipeline (routes_research.py:744) / run_structure_replay (replay/pipeline.py:409, no llm_gateway kwarg -> defaults None)",
      "callee": "Week2LLMGateway.invoke_json('alpha_classifier', ...)",
      "input_artifact": "structured_agent_outputs.json + alpha_taxonomy_v1.yaml",
      "output_artifact": "alpha_matches.json (also carries additive Evidence Stance fields, Sprint 2)",
      "can_call_llm": true,
      "can_call_market_data_provider": false,
      "replay_invokes": true,
      "replay_llm_gateway_value": "None (default parameter, not passed)",
      "affects_production_score": true,
      "path_class": "A/C"
    },
    {
      "id": "structure_extractor",
      "file": "comqutor_alpha/structure_engine/structure_extractor.py",
      "symbol": "save_extracted_structures -> build_extracted_structures_payload -> extract_structures_from_records -> _llm_edges",
      "line": 556,
      "caller": "_run_week1_week2_artifact_pipeline (routes_research.py:744) / run_structure_replay (replay/pipeline.py:410, no llm_gateway kwarg -> defaults None)",
      "callee": "Week2LLMGateway.invoke_json('structure_extractor', ...)",
      "input_artifact": "structured_agent_outputs.json (records + canonical_relations)",
      "output_artifact": "extracted_structures.json",
      "can_call_llm": true,
      "can_call_market_data_provider": false,
      "replay_invokes": true,
      "replay_llm_gateway_value": "None (default parameter, not passed)",
      "affects_production_score": true,
      "path_class": "A/C"
    },
    {
      "id": "graph_builder",
      "file": "comqutor_alpha/graph_engine/pipeline.py",
      "symbol": "build_structure_graph_stage / score_and_assemble_structure_graph",
      "line": 125,
      "caller": "_run_week3_graph_pipeline (routes_research.py:2101) / run_structure_replay (replay/pipeline.py:411-418)",
      "callee": "activation_scorer_v2 (in-process, pure function)",
      "input_artifact": "alpha_matches.json + extracted_structures.json",
      "output_artifact": "structure_graph.json (includes activation + entity_alpha_exposures)",
      "can_call_llm": false,
      "can_call_market_data_provider": false,
      "replay_invokes": true,
      "affects_production_score": true,
      "path_class": "A/C"
    },
    {
      "id": "conflict_detector",
      "file": "comqutor_alpha/conflict_engine/conflict_detector.py",
      "symbol": "detect_alpha_conflicts",
      "line": null,
      "caller": "_run_week3_graph_pipeline / run_structure_replay (replay/pipeline.py:425)",
      "callee": null,
      "input_artifact": "structure_graph.json activation + alpha_matches.json matches",
      "output_artifact": "conflict_results.json",
      "can_call_llm": false,
      "can_call_market_data_provider": false,
      "replay_invokes": true,
      "affects_production_score": true,
      "path_class": "A/C"
    },
    {
      "id": "artifact_finalizer",
      "file": "comqutor_alpha/api/artifact_export.py",
      "symbol": "finalize_completed_run_artifacts / build_and_write_artifact_manifest",
      "line": null,
      "caller": "routes_research.py (live) / replay/pipeline.py:590-619 (replay)",
      "callee": null,
      "input_artifact": "graph_payload, conflict_payload, alpha_matches_payload (already in-memory, never recomputed)",
      "output_artifact": "evidence_facts.json, evidence_stance_audit.json, entity_alpha_exposures.json, run_audit.json, artifact_manifest.json",
      "can_call_llm": false,
      "can_call_market_data_provider": false,
      "replay_invokes": true,
      "affects_production_score": false,
      "path_class": "A/C",
      "note": "Extraction/consolidation only -- never a second Activation/Conflict/Evidence-Fact computation."
    },
    {
      "id": "architecture_replay_entrypoint",
      "file": "comqutor_alpha/replay/pipeline.py",
      "symbol": "run_structure_replay",
      "line": 363,
      "caller": "cli.py / historical-learning audit / tests",
      "callee": ["adapt_run_outputs(llm_gateway=None)", "build_alpha_matches_payload(structured)", "build_extracted_structures_payload(structured)", "build_structure_graph_stage", "score_and_assemble_structure_graph", "detect_alpha_conflicts", "finalize_completed_run_artifacts", "write_run_audit_artifact(repository=None)", "build_and_write_artifact_manifest"],
      "input_artifact": "source run's raw_agent_outputs.json only (never a prior structured_agent_outputs.json)",
      "output_artifact": "new outputs/replays/replay-<ts>-<uuid>/ bundle",
      "can_call_llm": false,
      "can_call_market_data_provider": false,
      "replay_invokes": "n/a (this IS the replay path)",
      "affects_production_score": false,
      "path_class": "C",
      "note": "tradingagents_calls=0, llm_provider_calls=0, market_data_provider_calls=0, database_writes=0 are hardcoded literal zeros in ReplayResult, not measured counters -- see provider_call_baseline.json."
    }
  ],
  "path_summary": {
    "A_live_run_path": "api_post_research -> tradingagents_invocation -> structured_output_adapter -> alpha_mapper -> structure_extractor -> graph_builder -> conflict_detector -> artifact_finalizer",
    "B_historical_source_artifact_path": "GET /api/research/{run_id}* routes read already-persisted JSON under outputs/runs/<run_id>/ directly (build_research_response, get_research_run, etc. in routes_research.py) -- no recomputation, no LLM, no DB write on read.",
    "C_architecture_replay_path": "architecture_replay_entrypoint -> structured_output_adapter(llm_gateway=None) -> alpha_mapper(llm_gateway=None default) -> structure_extractor(llm_gateway=None default) -> graph_builder -> conflict_detector -> artifact_finalizer, writing to outputs/replays/ only",
    "D_test_fake_path": "tests/conftest.py mock_llm_client fixture, tests/test_week2_llm.py FakeClient, tests/test_structured_output_adapter.py _FakeBatchLLMGateway -- construct fake gateways/clients, never touch outputs/runs/ or a real Provider"
  }
}
```

### Appendix 3 — LLM Call-Site Inventory

Source: `docs/audit_artifacts/llm_call_site_inventory.json`

Purpose: Confirmed COMQUTOR LLM call sites and their boundary properties.

```json
{
  "audit": "phase_0_development_plan_llm_boundary_audit",
  "generated_at": "2026-08-05T00:00:00Z",
  "gateway_chokepoint": {
    "file": "comqutor_alpha/structure_engine/week2_llm.py",
    "class": "Week2LLMGateway",
    "invoke_method_line": 156,
    "provider_call_line": 182,
    "note": "All three COMQUTOR Week2 LLM tasks (claim_batch_enrichment / alpha_classifier / structure_extractor) share ONE Week2LLMGateway instance per run, built once in routes_research.py:2337 and threaded through all three writers -- meaning they also share ONE per-run call budget (default max_calls=32, server-capped at 100), not independent per-module budgets."
  },
  "real_call_sites": [
    {
      "call_site_id": "CS-01",
      "file": "comqutor_alpha/structure_engine/structured_output_adapter.py",
      "symbol": "_llm_batch_enrichment",
      "line": 956,
      "caller": "adapt_raw_agent_outputs (line 1180)",
      "purpose": "Enrich already-segmented claims with entities/factors/direction/confidence for LLM_STRUCTURED_AGENTS only (market/technical/sentiment/news/fundamental[s]_agent); claim/evidence/source_section returned byte-for-byte unchanged, validated by _validate_llm_batch_enrichment",
      "development_plan_module": "5.1",
      "provider": "whatever comqutor_alpha.llm/tradingagents.llm_clients client the gateway's model was built with (DeepSeek by default per research_profiles.py)",
      "model_source": "tradingagents.llm_clients.create_llm_client via build_server_week2_llm_gateway (week2_llm.py:257-267)",
      "prompt_source": "Week2LLMGateway._TASK_INSTRUCTIONS['claim_batch_enrichment'] (week2_llm.py:27-35), embedded in invoke_json's own prompt template (week2_llm.py:170-174)",
      "structured_output": true,
      "retry_count": "max_retries default 1, server-capped MAX_SERVER_RETRIES=2",
      "timeout": "DEFAULT_TIMEOUT_SECONDS=15.0, bounded [1.0, 120.0]",
      "cache_enabled": false,
      "live_run_reachable": true,
      "replay_reachable": false,
      "fallback": "per-batch deterministic enrichment (extraction_method=deterministic_splitter) -- never a whole-run crash, never silently drops a segment",
      "affects_activation": true,
      "affects_conflict": true,
      "gated_by_env": "COMQUTOR_WEEK2_LLM_ENABLED"
    },
    {
      "call_site_id": "CS-02",
      "file": "comqutor_alpha/structure_engine/alpha_mapper.py",
      "symbol": "_apply_optional_classifier",
      "line": 393,
      "caller": "map_claim_to_alpha (line 624)",
      "purpose": "Disambiguate among >=2 deterministically-eligible Alpha candidates (select or defer); cannot create candidates, change admissibility, or produce a trading decision",
      "development_plan_module": "5.2",
      "provider": "same shared Week2LLMGateway model as CS-01",
      "model_source": "same as CS-01",
      "prompt_source": "Week2LLMGateway._TASK_INSTRUCTIONS['alpha_classifier'] (week2_llm.py:36-41)",
      "structured_output": true,
      "retry_count": "shared gateway default (see CS-01)",
      "timeout": "shared gateway default (see CS-01); classifier_timeout_seconds=5.0 is a separate, unused-in-this-branch parameter for the non-gateway `classifier` callable path",
      "cache_enabled": false,
      "live_run_reachable": true,
      "replay_reachable": false,
      "fallback": "keeps the already-computed deterministic matched_alpha/status decided before the classifier ran (classifier_metadata status='fallback') -- never crashes, never returns 'unknown'",
      "affects_activation": true,
      "affects_conflict": true,
      "gated_by_env": "COMQUTOR_WEEK2_LLM_ENABLED",
      "trigger_condition": "match_status != 'no_match' AND len(eligible_candidates) >= 2 -- this is the concrete 'ambiguity' definition in code; every other claim never reaches this call site regardless of gateway availability"
    },
    {
      "call_site_id": "CS-03",
      "file": "comqutor_alpha/structure_engine/structure_extractor.py",
      "symbol": "_llm_edges",
      "line": 415,
      "caller": "extract_structures_from_records (line 451)",
      "purpose": "Extract evidence-backed factor-to-factor relation edges (causal/supportive/conflicting) from one claim's evidence text, restricted to that claim's own deterministically-extracted allowed_factors",
      "development_plan_module": "5.3",
      "provider": "same shared Week2LLMGateway model as CS-01",
      "model_source": "same as CS-01",
      "prompt_source": "Week2LLMGateway._TASK_INSTRUCTIONS['structure_extractor'] (week2_llm.py:42-47)",
      "structured_output": true,
      "retry_count": "shared gateway default (see CS-01)",
      "timeout": "shared gateway default (see CS-01)",
      "cache_enabled": false,
      "live_run_reachable": true,
      "replay_reachable": false,
      "fallback": "per-claim deterministic rule extraction (_extract_edges, relation_grammar.py) -- never an empty-graph crash",
      "affects_activation": true,
      "affects_conflict": true,
      "gated_by_env": "COMQUTOR_WEEK2_LLM_ENABLED",
      "trigger_condition": "llm_gateway is not None AND len(factors) >= 2, evaluated per claim",
      "call_frequency": "per-claim (not per-agent-report, not per-run) -- called once per structured claim record with >=2 deterministic factors"
    },
    {
      "call_site_id": "CS-04-to-CS-16",
      "file": "tradingagents/agents/{analysts,researchers,trader,managers,risk_mgmt}/*.py",
      "symbol": "12 native agent node functions (market/sentiment/news/fundamentals analysts; bull/bear researchers; research_manager; trader; aggressive/conservative/neutral risk debators; portfolio_manager) + 1 post-run reflection call",
      "line": "n/a (see repo-wide inventory sub-agent report for exact per-file line numbers)",
      "caller": "TradingAgentsGraph.propagate() / .graph.stream(), invoked from comqutor_alpha/runners/tradingagents_runner.py:172,384",
      "purpose": "TradingAgents' own native per-agent analysis/debate/decision generation -- upstream functionality, not a COMQUTOR addition",
      "development_plan_module": "TradingAgents",
      "provider": "tradingagents.llm_clients.create_llm_client dispatch (openai/anthropic/google/azure/bedrock/openai-compatible incl. DeepSeek)",
      "model_source": "comqutor_alpha/research_profiles.py fixed ResearchProfile registry for real web-submitted runs (default DeepSeek comqutor_deepseek_default_v1; alternate Anthropic comqutor_anthropic_medium_sonnet46_v1) -- HTTP requests cannot select provider/model directly",
      "prompt_source": "each agent's own native TradingAgents prompt-builder function, with the COMQUTOR Structure Output Contract suffix appended at runtime (see canonical_prompt_injection.py) for the duration of the run",
      "structured_output": "partial -- 5 of the 12 (sentiment, research_manager, trader, portfolio_manager, plus market via a different path) use bind_structured/invoke_structured_or_freetext (tradingagents/agents/utils/structured.py); the rest are free-text",
      "retry_count": "unclear / underlying LangChain SDK default (no explicit COMQUTOR-side retry wrapper found)",
      "timeout": "unclear / underlying LangChain SDK default",
      "cache_enabled": false,
      "live_run_reachable": true,
      "replay_reachable": false,
      "fallback": "n/a -- this is TradingAgents' own native behavior, out of COMQUTOR's Development Plan scope",
      "affects_activation": true,
      "affects_conflict": true,
      "note": "Every one of these 12 agents' prompt is functionally modified at runtime by canonical_prompt_injection.py to also request a COMQUTOR_CANONICAL_RELATIONS JSON block -- see tradingagents_modification_audit.csv. This does not add a new LLM call (same single call each agent already makes), but it is a genuine prompt-content change, achieved via monkeypatch rather than a tradingagents/ source edit."
    }
  ],
  "test_fake_call_sites": [
    "tests/conftest.py:100-108 mock_llm_client fixture (patches tradingagents.llm_clients.factory.create_llm_client)",
    "tests/test_week2_llm.py FakeClient class",
    "tests/test_structured_output_adapter.py _FakeBatchLLMGateway class",
    "tests/test_structured_agents.py, tests/test_memory_log.py, tests/test_signal_processing.py -- unittest.mock.MagicMock() llm objects",
    "tests/test_week3_security_hardening.py:160-165 monkeypatches routes_research.build_server_week2_llm_gateway to a call-recording stub"
  ],
  "dead_or_legacy_or_manual_only_call_sites": [
    {
      "file": "tradingagents/graph/signal_processing.py",
      "lines": "20-31",
      "note": "SignalProcessor.process_signal explicitly documents it no longer makes an LLM call; quick_thinking_llm constructor argument accepted only for backward-compatible signature, unused."
    },
    {
      "file": "comqutor_alpha/llm/deepseek_smoke.py",
      "lines": "337-340",
      "note": "run_deepseek_smoke -> run_original_tradingagents_research: real, opt-in, manual DeepSeek smoke entrypoint. Not invoked by any production code path, tests only exercise it mocked."
    },
    {
      "file": "scripts/smoke_structured_output.py",
      "lines": "121-122",
      "note": "Manual dev CLI script to verify a provider's native structured-output mode. Not part of any automated production or replay path."
    }
  ],
  "cache_infrastructure": {
    "found": false,
    "note": "No Redis/disk/in-process cache wraps any LLM .invoke() call anywhere in the repository. The only functools.lru_cache found (tradingagents/agents/utils/agent_utils.py:78, resolve_instrument_identity) caches a yfinance ticker lookup, unrelated to LLM calls."
  }
}
```

### Appendix 4 — LLM Prompt Inventory

Source: `docs/audit_artifacts/llm_prompt_inventory.csv`

Purpose: Prompt families, contracts, validation, retries, and reachability.

> **Source-format note:** this artifact contains unquoted delimiter commas, producing non-uniform column counts on source row(s) 2, 3, 4, 5, 6, 7. It is embedded verbatim below instead of being heuristically repaired or rendered as a potentially misleading Markdown table.

```csv
prompt_id,path,symbol,stage,source_frozen_or_locally_added,type,input_variables,output_contract,allowed_vocabulary_restricted,schema_version,examples_included,retry_behavior,failure_behavior,prompt_hash_deterministic,live_reachable,replay_reachable,tests_covering
PROMPT-01,comqutor_alpha/structure_engine/week2_llm.py,_TASK_INSTRUCTIONS['claim_batch_enrichment'],5.1 Structured Output Adapter,locally_added,system+user (single combined prompt string),"ticker, agent, segments[](segment_id/claim/evidence/source_section)",strict JSON object with claims[] one-per-segment_id,false (free entities/factors text; direction/confidence bounded),n/a (task string, not a payload schema version),false,shared gateway retry (see gateway row),per-batch deterministic fallback,not computed (prompt text is a fixed constant string; not hashed like the TradingAgents suffix),true,false,tests/test_structured_output_adapter.py; tests/test_week2_llm.py
PROMPT-02,comqutor_alpha/structure_engine/week2_llm.py,_TASK_INSTRUCTIONS['alpha_classifier'],5.2 Alpha Mapper Tier 2,locally_added,system+user (single combined prompt string),"claim, evidence, factors, direction, allowed_alpha_ids, candidates[] (<=3, taxonomy-restricted)",strict JSON {decision, selected_alpha_id},true (selected_alpha_id must be in allowed_alpha_ids or null),n/a,false,shared gateway retry (see gateway row),falls back to pre-computed deterministic matched_alpha/status,not computed,true,false,tests/test_ai_alpha_mapper_discrimination.py; tests/test_week2_llm.py
PROMPT-03,comqutor_alpha/structure_engine/week2_llm.py,_TASK_INSTRUCTIONS['structure_extractor'],5.3 Structure Extractor,locally_added,system+user (single combined prompt string),"claim_id, claim, evidence, allowed_factors[] (deterministically extracted, per-claim)",strict JSON {edges[]} each with source_factor/target_factor/edge_type/assertion_status/confidence,true (factors must be in allowed_factors; edge_type in {causal,supportive,conflicting}),n/a,false,shared gateway retry (see gateway row),falls back to per-claim deterministic rule extraction,not computed,true,false,tests/test_structure_extractor.py; tests/test_week2_llm.py
PROMPT-04,comqutor_alpha/structure_engine/week2_llm.py,Week2LLMGateway.invoke_json prompt wrapper,shared gateway wrapper (all 3 above),locally_added,system instruction wrapper,"instruction (one of PROMPT-01/02/03) + serialized payload JSON",strict JSON only literal instruction: 'Return strict JSON only with no markdown and no hidden reasoning',n/a,n/a,false,"max_retries default 1, server-capped 2; MAX_PROMPT_PAYLOAD_CHARS=60000 rejects oversized payload before ever calling the model (WEEK2_LLM_INPUT_TOO_LARGE)",returns None on TimeoutError/JSONDecodeError/TypeError/ValueError/KeyError/generic Exception -- every failure logged with a stable error_code to error_logs/week2_llm_errors.jsonl,false (renders payload JSON inline, so hash varies per call; the instruction text itself is a fixed constant),true,false,tests/test_week2_llm.py
PROMPT-05,comqutor_alpha/structure_engine/canonical_relation_prompt.py,build_structure_output_contract_prompt_suffix,TradingAgents native agent prompts (all 12),locally_added -- appended via runtime monkeypatch not a tradingagents/ file edit,suffix appended to existing TradingAgents system/user prompt,"vocabulary (factors[], relations[]) from canonical_vocabulary.build_canonical_relation_vocabulary()",fenced json block after normal report: {schema_version, relations[]} each with source_factor_id/relation_type/target_factor_id/evidence_quote/assertion_status/confidence,true (factor IDs and relation types must come from the allowed vocabulary; 14 explicit mandatory rules forbid inventing facts/relations),comqutor_relation_output_v1,true (2 worked positive examples + 3 worked invalid examples embedded in the prompt text),n/a (reuses the agent's own existing call/retry behavior, not a separate gateway call),"parsed downstream by canonical_relation_block.py; unparseable/absent block simply yields zero canonical_relations for that raw output (never crashes, never fabricates)",true (compute_prompt_contract_sha256, deterministic given the same vocabulary -- recorded in tradingagents_comqutor_vocabulary_snapshot.json per run),true,false (never applied during Architecture Replay -- replay never invokes TradingAgents),none found directly on the rendered suffix text; canonical_relation_block.py has its own validation tests
PROMPT-06,tradingagents/agents/{analysts,researchers,trader,managers,risk_mgmt}/*.py,12 native agent prompt-builder functions,TradingAgents native,source_frozen (upstream TradingAgents, unmodified on disk),system+user (varies per agent),ticker/date/reports/memories/debate-state per agent,free text professional report/debate/decision (5 of 12 additionally use LangChain structured-output binding),false (free text, no restricted vocabulary in the base upstream prompt),n/a,false,unclear / underlying LangChain SDK default,unclear / underlying LangChain SDK default,not applicable to a Phase 0 audit (upstream file content, not hashed here),true,false,tests/test_structured_agents.py (mocked)
```

### Appendix 5 — Provider-Call Baseline

Source: `docs/audit_artifacts/provider_call_baseline.json`

Purpose: Provider-call granularity, budgets, replay behavior, cache, and unknowns.

```json
{
  "audit": "phase_0_development_plan_llm_boundary_audit",
  "generated_at": "2026-08-05T00:00:00Z",
  "method": "Static call-graph analysis + existing code-level instrumentation only. No real Provider was invoked during this audit.",
  "stage_matrix": [
    {
      "stage": "TradingAgents native agents (12 nodes: market/sentiment/news/fundamentals analysts; bull/bear researchers; research_manager; trader; aggressive/conservative/neutral risk debators; portfolio_manager)",
      "purpose": "native report/debate/decision generation",
      "provider_call_possible": true,
      "typical_count_per_run": "UNKNOWN_NOT_INSTRUMENTED (each of the 12 nodes calls its LLM exactly once per graph execution in the standard LangGraph topology, but no counter/log in this repo records the realized per-run total; debate nodes (bull/bear) may loop more than once depending on max_debate_rounds config, which this audit did not enumerate)",
      "required_by_plan": "upstream (TradingAgents itself, outside §5.1/5.2/5.3 scope)"
    },
    {
      "stage": "Structured Adapter (claim_batch_enrichment)",
      "purpose": "claim parsing/enrichment",
      "provider_call_possible": true,
      "typical_count_per_run": "UNKNOWN_NOT_INSTRUMENTED (bounded by ceil(candidate_segment_count_for_LLM_STRUCTURED_AGENTS / LLM_CLAIM_BATCH_SIZE=64) batches, one call per batch, but the realized segment count varies per report; llm_batch_count/llm_batch_fallback_count ARE recorded per run in structured_agent_outputs.json metadata, so a specific historical run's actual count is knowable from its own artifact -- but no fleet-wide/typical baseline is computed anywhere in this repo)",
      "required_by_plan": "5.1",
      "disabled_by_default": true,
      "env_gate": "COMQUTOR_WEEK2_LLM_ENABLED"
    },
    {
      "stage": "Alpha Mapper (alpha_classifier)",
      "purpose": "ambiguous-candidate classification",
      "provider_call_possible": true,
      "typical_count_per_run": "UNKNOWN_NOT_INSTRUMENTED (at most one call per claim with match_status != no_match and >= 2 eligible candidates; classifier metadata (status: disabled/not_needed/applied/fallback/timeout/error/...) IS recorded per-claim in alpha_matches.json, so per-run realized counts are reconstructable from that artifact, but no aggregate baseline exists in this repo)",
      "required_by_plan": "5.2",
      "disabled_by_default": true,
      "env_gate": "COMQUTOR_WEEK2_LLM_ENABLED"
    },
    {
      "stage": "Structure Extractor (structure_extractor)",
      "purpose": "relation edge extraction",
      "provider_call_possible": true,
      "typical_count_per_run": "UNKNOWN_NOT_INSTRUMENTED (at most one call per claim with >= 2 deterministically-extracted factors; llm_edge_count vs deterministic_edge_count IS recorded per run in extracted_structures.json metadata, but not a per-call count, and no aggregate baseline exists in this repo)",
      "required_by_plan": "5.3",
      "disabled_by_default": true,
      "env_gate": "COMQUTOR_WEEK2_LLM_ENABLED"
    },
    {
      "stage": "Activation",
      "purpose": "scoring",
      "provider_call_possible": false,
      "typical_count_per_run": 0,
      "required_by_plan": "deterministic",
      "evidence": "no LLM/gateway import found in comqutor_alpha/graph_engine (grep, this audit)"
    },
    {
      "stage": "Conflict",
      "purpose": "arbitration",
      "provider_call_possible": false,
      "typical_count_per_run": 0,
      "required_by_plan": "deterministic",
      "evidence": "no LLM/gateway import found in comqutor_alpha/conflict_engine (grep, this audit)"
    },
    {
      "stage": "Replay",
      "purpose": "all stages, reprocessed",
      "provider_call_possible": false,
      "typical_count_per_run": 0,
      "required_by_plan": "saved outputs only",
      "evidence": "comqutor_alpha/replay/pipeline.py:405 passes llm_gateway=None explicitly to adapt_run_outputs; lines 409-410 call build_alpha_matches_payload(structured) and build_extracted_structures_payload(structured) with no llm_gateway argument, which defaults to None in both functions' signatures. ReplayResult.llm_provider_calls/tradingagents_calls/market_data_provider_calls/database_writes are hardcoded literal 0 in every return path (lines 471-474, 501-504, 634-637) -- these are architectural guarantees encoded in the return type, not measured runtime counters."
    }
  ],
  "direct_answers": {
    "adapter_called_per_agent_or_per_report": "Per raw agent output (one 'report'), batched: deterministic segmentation always runs first for the whole report; if the agent is in LLM_STRUCTURED_AGENTS and a gateway is present, its segments are split into sequential batches of at most LLM_CLAIM_BATCH_SIZE=64 and each batch gets one LLM call. A report with <=64 eligible segments = 1 call; a longer report = multiple calls. Never per-individual-claim.",
    "alpha_mapper_called_per_claim_or_only_ambiguous": "Only claims where the deterministic pipeline already produced >=2 eligible candidates (match_status != 'no_match'). This is the code-level definition of 'ambiguous' for this gate (alpha_mapper.py:340). Claims with 0 or 1 eligible candidate never reach the LLM at all, regardless of gateway availability.",
    "structure_extractor_call_granularity": "Per-claim (structure_extractor.py:415, one call per record with >=2 deterministically-extracted factors) -- not per-agent, not per-run.",
    "duplicate_text_recall_risk": "Yes, structurally possible: no caching layer exists anywhere in the LLM call path (confirmed by repo-wide search), so if the identical claim/evidence text appears twice in one run (e.g. cross-agent near-duplicates that survive dedupe with different claim_ids) or across two runs for the same ticker/date, each occurrence independently triggers its own LLM call and its own budget consumption. This is a real, currently-unaddressed inefficiency/cost risk when COMQUTOR_WEEK2_LLM_ENABLED is on.",
    "redis_or_local_cache_present": false,
    "replay_can_accidentally_trigger_provider": "No. llm_gateway=None is hardcoded (adapter) or defaulted (mapper/extractor) at every replay call site; TradingAgentsGraph is never imported or constructed anywhere in comqutor_alpha/replay/pipeline.py."
  }
}
```

### Appendix 6 — Structured Adapter Gap Matrix

Source: `docs/audit_artifacts/structured_adapter_gap_matrix.csv`

Purpose: Field-level comparison for Development Plan section 5.1.

> **Source-format note:** this artifact contains unquoted delimiter commas, producing non-uniform column counts on source row(s) 4, 7. It is embedded verbatim below instead of being heuristically repaired or rendered as a potentially misleading Markdown table.

```csv
field,plan_required,current_source,llm,rule,default,validator
claim,yes,deterministic segmentation (extract_claim_segments_with_audit) -- LLM never proposes claim text; LLM enrichment must return it byte-for-byte identical or the whole batch is rejected,false (LLM cannot originate or alter it),true,"""unknown"" (safe_default_record)",validate_structured_output + _validate_llm_batch_enrichment (claim must equal input segment verbatim)
evidence,yes,same deterministic segment text as claim (claim[:MAX_CLAIM_CHARS] == evidence[:MAX_CLAIM_CHARS] at segmentation time); LLM enrichment must preserve it verbatim,false,true,"""unknown""",same as claim
entities,yes,extract_entities() deterministic term match against ENTITY_TERMS + ticker; LLM-proposed entities are filtered to only those whose lowercase form literally appears in the evidence text before being unioned in,partial (LLM entities allowed only if independently text-verifiable),true,[],_validate_llm_batch_enrichment (entities must be list,<=32 items) + _build_records_from_segments substring-verification filter
factors,best effort,extract_known_factors_from_text() deterministic taxonomy match; LLM-proposed factors filtered to only those matching normalize_factor_label() against the verified deterministic set,partial (same verification pattern as entities),true,[],_validate_llm_batch_enrichment + _build_records_from_segments substring/taxonomy-verification filter
direction,yes,infer_direction() deterministic keyword/semantic heuristic when LLM absent; LLM value used only if gateway enabled and normalize_direction() accepts it,partial,true,"""unknown""",_validate_llm_batch_enrichment (must normalize into VALID_DIRECTIONS or raise)
confidence,yes,estimate_confidence() deterministic heuristic when LLM absent; LLM value used only if 0.0<=x<=1.0 and finite,partial,true,0.0,_validate_llm_batch_enrichment (must be finite float in [0,1]) + validate_structured_output
source_type,yes,infer_source_type() fully deterministic (agent-name/text heuristic) -- never an LLM output field at all,false,true,"""unknown""",validate_structured_output (must be a non-empty string; no closed enum enforced)
source_refs,yes,_normalize_source_refs() deterministic from raw_record.source_refs + source_agent_output_id -- never an LLM output field,false,true,[],validate_structured_output (must be a list or None)
```

### Appendix 7 — Alpha Mapper Gap Matrix

Source: `docs/audit_artifacts/alpha_mapper_gap_matrix.csv`

Purpose: Tier-by-tier comparison for Development Plan section 5.2.

> **Source-format note:** this artifact contains unquoted delimiter commas, producing non-uniform column counts on source row(s) 3. It is embedded verbatim below instead of being heuristically repaired or rendered as a potentially misleading Markdown table.

```csv
tier,plan,current_implementation,live_reachable,tested,verdict
1 keyword/factor,required,"keyword_score() + factor_score() + direction_score() + semantic_score() weighted 0.50/0.30/0.08/0.12 (alpha_mapper.py:186-261), computed deterministically for all 10 taxonomy alphas on every claim regardless of LLM availability; DEFAULT_MIN_MATCH_SCORE=0.35 unchanged since Week 2 (confirmed against docs/week2_completion_report.md); top_candidates=candidates[:3] confirmed",true,"tests/test_alpha_mapper.py, tests/test_ai_alpha_mapper_discrimination.py",COMPLIANT
2 LLM classifier,required,"_apply_optional_classifier() (alpha_mapper.py:324-458), invoked only when match_status != 'no_match' AND len(eligible_candidates) >= 2 (the code-level definition of ambiguity), restricted to select/defer over the <=3 already-deterministically-eligible candidates (allowed_alpha_ids) -- cannot create new candidates, cannot alter admissibility, cannot output a trading decision",true (gated behind COMQUTOR_WEEK2_LLM_ENABLED; disabled by default),"tests/test_week2_llm.py, tests/test_ai_alpha_mapper_discrimination.py",COMPLIANT (opt-in, off by default)
3 rule fallback,required,"On any classifier failure/timeout/invalid-output/budget-exhaustion (llm_gateway.invoke_json returns None or raises inside try/except), _apply_optional_classifier returns the result object UNCHANGED from before the classifier ran -- i.e. the deterministic top/second-candidate decision from map_claim_to_alpha lines 502-537 is the fallback, never a crash, never an 'unknown' placeholder",true,"tests/test_week2_llm.py (timeout/error/invalid_output/fallback branches)",COMPLIANT
```

### Appendix 8 — Structure Extractor Gap Matrix

Source: `docs/audit_artifacts/structure_extractor_gap_matrix.csv`

Purpose: Edge-source and fallback comparison for Development Plan section 5.3.

> **Source-format note:** this artifact contains unquoted delimiter commas, producing non-uniform column counts on source row(s) 8, 9. It is embedded verbatim below instead of being heuristically repaired or rendered as a potentially misleading Markdown table.

```csv
question,answer,evidence
Who generates nodes/edges,"Three independent sources merged into one graph: (1) LLM_EXTRACTED via _llm_edges/_validated_llm_edges when gateway enabled and claim has >=2 factors, (2) RULE_EXTRACTED via _extract_edges/relation_grammar.py deterministic pattern rules (always computed as the fallback path, and the only path when gateway is off), (3) CANONICAL_BLOCK via _canonical_relation_edges_and_nodes from TradingAgents' own single existing call's appended COMQUTOR_CANONICAL_RELATIONS JSON block",structure_extractor.py:415-534
Real LLM call,"Yes, per-claim, only when llm_gateway is not None and len(factors)>=2 -- comqutor_alpha/structure_engine/week2_llm.py Week2LLMGateway.invoke_json('structure_extractor', ...)",structure_extractor.py:415-427
Strict JSON schema,"Yes -- _validated_llm_edges enforces exact field set {source_factor,target_factor,edge_type,assertion_status,confidence}, factor membership in the claim's own allowed_factors, edge_type in VALID_EDGE_TYPES, assertion_status in VALID_ASSERTION_STATUSES, confidence in [0,1], PLUS a deterministic evidence-backing re-check (_llm_relation_is_evidence_backed) and a causal-direction plausibility re-check (plausible_causal_direction) before any LLM-proposed edge is accepted",structure_extractor.py:269-342
Empty result fallback,"Yes -- if llm_gateway.invoke_json returns None/falsy for a claim, that claim falls back to deterministic _extract_edges() for that claim only; no whole-run crash or empty-graph failure mode exists",structure_extractor.py:451-456
causal/supportive/conflicting supported,Yes -- all three present in VALID_EDGE_TYPES and independently reachable via both the deterministic relation_grammar rules and the LLM-validated path,"comqutor_alpha/structure_engine/structure_schema.py:16, structure_extractor.py:224-244"
Additional edge types beyond the 3,No -- VALID_EDGE_TYPES = {causal supportive conflicting} exactly; canonical-block edges are also constrained to this same set (line 393),structure_schema.py:16
Synonym normalization LLM-before-or-after,"Before -- factors are always deterministically normalized via normalize_factor_label()/extract_known_factors_from_text() first (_extract_factors), and the resulting allowed_factors list is what is sent TO the LLM as its only valid vocabulary; the LLM cannot introduce a new/unnormalized factor name",structure_extractor.py:65-80,415-427
Duplicate merge owner,"Deterministic -- extract_structures_from_records dedups via an explicit (source,target,edge_type,source_record_id) tuple key (edges.setdefault(key, edge)), applied identically regardless of whether the edge came from LLM, rule, or canonical-block extraction",structure_extractor.py:478-485,501-508
Edge claim/evidence lineage,"Yes on every edge -- source_claim, source_record_id, source_claim_ids, source_agent_output_id, evidence fields are populated by the shared _edge() constructor for all three edge sources",structure_extractor.py:161-197
Conditional/negated/quoted/hypothetical handling,"assertion_status is a first-class field (VALID_ASSERTION_STATUSES) on every edge; for LLM edges, semantics.negated forces assertion_status='negated' and semantics.conditional forces 'conditional' even if the LLM claimed 'asserted' -- deterministic override, not LLM-trusted",structure_extractor.py:324-327
Canonical relation block source,"TradingAgents' OWN existing single LLM call per agent (the SAME call that produces its normal report), not a separate COMQUTOR LLM extractor call -- confirmed by canonical_relation_prompt.py docstring ('never a new LLM call') and by zero .invoke()/create_llm_client hits found in canonical_relation_block.py/structured_output_adapter.py by the background LLM-inventory sub-agent",canonical_relation_prompt.py:1-9; structure_extractor.py:401-408
Does this diverge from TradingAgents minimal-hooks plan,"Yes, functionally, though not via a tradingagents/ file edit -- see tradingagents_modification_audit.csv. The canonical relation block is produced because COMQUTOR's canonical_prompt_injection.py monkeypatches all 12 native agent prompts at runtime to request it; this is more than passive output capture, even though it adds zero LLM calls and edits zero files on disk under tradingagents/.",comqutor_alpha/llm/canonical_prompt_injection.py:1-100
Real NVDA graph edge source breakdown,"Not independently re-measured in Phase 0 (would require running or replaying a real NVDA run and reading extracted_structures.json's llm_edge_count / deterministic_edge_count / canonical_relation_edge_count metadata fields, which this repo already tracks per-run) -- see UNKNOWN_NOT_INSTRUMENTED note in provider_call_baseline.json; the metadata fields exist and are correct by construction, this audit simply did not execute a fresh replay to populate them for this report.",extracted_structures.json metadata schema (structure_extractor.py:524-533)
Replay edge reproducibility,"Replay reproduces RULE_EXTRACTED and CANONICAL_BLOCK edges exactly (both are pure functions of the already-saved raw_agent_outputs.json / structured_agent_outputs.json). It can NEVER reproduce LLM_EXTRACTED edges from the original live run, because replay always calls build_extracted_structures_payload with llm_gateway=None -- see replay_semantic_reproducibility.json.",replay/pipeline.py:410
```

### Appendix 9 — TradingAgents Modification Audit

Source: `docs/audit_artifacts/tradingagents_modification_audit.csv`

Purpose: On-disk hooks, runtime prompt changes, and added-call assessment.

> **Source-format note:** this artifact contains unquoted delimiter commas, producing non-uniform column counts on source row(s) 2, 6, 9, 11. It is embedded verbatim below instead of being heuristically repaired or rendered as a potentially misleading Markdown table.

```csv
path,function_or_context,type,description,required_for_comqutor,compliant_with_minimal_hooks,risk
tradingagents/comqutor_outputs.py,module-level shim (9 lines),output_capture_hook,"Re-exports AGENT_OUTPUT_FIELDS/OUTPUT_VERSION/save_comqutor_run_outputs from comqutor_alpha.adapters.tradingagents_output_writer; no logic of its own",no (zero importers found anywhere in the repo -- appears dead/vestigial),yes (content-wise, pure passthrough),none -- but it is the only file physically added inside tradingagents/, so it is the sole item a real upstream diff would flag as new
comqutor_alpha/adapters/tradingagents_output_writer.py,save_comqutor_run_outputs / AGENT_OUTPUT_FIELDS,output_capture_hook,"Reads fields off the graph's final_state dict after a run completes and writes JSON to disk; zero .invoke()/ChatOpenAI()/ChatAnthropic()/get_llm() calls found in the file; lives entirely outside tradingagents/",yes,yes -- textbook read/save-existing-output hook,none
comqutor_alpha/llm/canonical_prompt_injection.py,comqutor_structure_output_contract_scope() / _make_wrapper(),prompt_change (functionally agent_behavior_change),"Monkeypatches the already-imported get_language_instruction attribute on all 12 TradingAgents agent modules for the duration of one propagate()/stream() call, appending the COMQUTOR Structure Output Contract suffix to every one of their prompts; the module's own docstring explicitly frames 'never an edit to tradingagents/' as its design goal",yes (this is COMQUTOR's core relation-extraction mechanism),no -- changes what every agent is asked to produce even though no tradingagents/ file is edited on disk,HIGH -- central compliance risk item of this whole audit
comqutor_alpha/structure_engine/canonical_relation_prompt.py,build_structure_output_contract_prompt_suffix(),prompt_change (the injected text itself),"Builds the literal suffix: instructs the LLM to append a COMQUTOR_CANONICAL_RELATIONS marker + fenced JSON block (source_factor_id/relation_type/target_factor_id/evidence_quote/assertion_status/confidence), drawn from a fixed factor/relation taxonomy, with worked examples and 14 mandatory rules",yes,n/a (this is the payload of the finding above),HIGH (same as above -- this is what actually reaches the LLM)
tradingagents/agents/utils/agent_utils.py,get_language_instruction() (lines 52-65),baseline_unmodified,"Confirmed unchanged on disk: original upstream function returns '' for English or a one-line localization instruction otherwise. This is the shared attribute all 12 prompt-builders call, making it the seam canonical_prompt_injection.py exploits.",n/a,n/a,serves as the injection seam, not itself modified
"tradingagents/agents/{analysts,researchers,trader,managers,risk_mgmt}/*.py (12 files)",prompt-builder functions,baseline_unmodified,"All 12 files call + get_language_instruction() as the literal last thing appended to their prompt strings, confirmed present and unedited on disk -- this is what makes them interceptable by one shared patch",n/a,n/a (files themselves untouched),these are the actual injection targets at runtime
comqutor_alpha/runners/tradingagents_runner.py,run_original_tradingagents_research (line ~171),agent_behavior_change (activation site),Wraps graph.propagate(...) in `with comqutor_structure_output_contract_scope():` -- this is where the prompt injection is switched on for a real one-shot run,yes,no (activates the finding above),HIGH
comqutor_alpha/runners/tradingagents_runner.py,run_streaming_tradingagents_research (line ~383),agent_behavior_change (activation site),Same wrapping applied around graph.graph.stream(init_state, **stream_args) for the streaming API (W7) path,yes,no,HIGH
comqutor_alpha/structure_engine/canonical_relation_block.py + structured_output_adapter.py (split_human_text_and_canonical_block / validate_canonical_relations),downstream parsing,output_capture_hook (downstream),"Deterministic regex/JSON extraction and validation of the already-produced COMQUTOR_CANONICAL_RELATIONS block from the agent's own text; zero .invoke()/create_llm_client hits in either file (2013 combined lines, grepped)",yes,yes in isolation (only re-parses text already produced),LOW -- but exists only because of the prompt-injection finding above
comqutor_alpha/llm/deepseek_smoke.py,deepseek_thinking_scope() (provider registry patch),provider_change,"Swaps the DeepSeek provider registry's chat_class entry to toggle 'thinking mode' request params, scoped only around TradingAgentsGraph(...) construction; no prompt-text or agent-logic change; no-op for every non-DeepSeek provider",optional (DeepSeek-only),yes-ish (a provider/config knob, not a prompt/logic change),LOW
```

### Appendix 10 — Deterministic Core Boundary Audit

Source: `docs/audit_artifacts/deterministic_core_boundary_audit.json`

Purpose: Module-by-module LLM import and free-text boundary findings.

```json
{
  "audit": "phase_0_development_plan_llm_boundary_audit",
  "generated_at": "2026-08-05T00:00:00Z",
  "method": "grep -rln for LLM/gateway imports (comqutor_alpha.llm, comqutor_alpha.structure_engine.week2_llm, 'llm_gateway') across comqutor_alpha/graph_engine, comqutor_alpha/conflict_engine, comqutor_alpha/exposure, comqutor_alpha/exposure_engine.py, comqutor_alpha/storage; confirmed with scripts/audit_llm_boundary.py::check_deterministic_core_no_llm_import (also enumerates comqutor_alpha/structure_engine/evidence_stance.py explicitly).",
  "modules": [
    {
      "module": "taxonomy loading",
      "file": "comqutor_alpha/alpha_library/alpha_loader.py",
      "llm_imported": false,
      "provider_reachable": false,
      "free_text_reparsed": false,
      "deterministic": true,
      "input_schema": "alpha_taxonomy_v1.yaml",
      "output_schema": "dict[str, AlphaDefinition]",
      "test_proof": "tests/test_alpha_loader.py"
    },
    {
      "module": "Evidence Fact grouping",
      "file": "comqutor_alpha/api/artifact_export.py (extract_evidence_facts_export)",
      "llm_imported": false,
      "provider_reachable": false,
      "free_text_reparsed": false,
      "deterministic": true,
      "input_schema": "alpha_matches.json + extracted_structures.json + graph payload",
      "output_schema": "evidence_facts.json",
      "test_proof": "tests/test_artifact_export_and_api.py"
    },
    {
      "module": "claim dedupe",
      "file": "comqutor_alpha/structure_engine/structured_output_adapter.py (dedupe_structured_records)",
      "llm_imported": false,
      "provider_reachable": false,
      "free_text_reparsed": false,
      "deterministic": true,
      "input_schema": "list of structured claim records",
      "output_schema": "(deduped_records, removed_count)",
      "test_proof": "tests/test_structured_output_adapter.py"
    },
    {
      "module": "graph admission",
      "file": "comqutor_alpha/graph_engine/pipeline.py / graph_builder logic",
      "llm_imported": false,
      "provider_reachable": false,
      "free_text_reparsed": false,
      "deterministic": true,
      "input_schema": "alpha_matches.json + extracted_structures.json",
      "output_schema": "structure_graph.json edges/nodes",
      "test_proof": "tests/test_graph_engine.py (see full test suite listing)"
    },
    {
      "module": "graph normalization",
      "file": "comqutor_alpha/graph_engine/pipeline.py",
      "llm_imported": false,
      "provider_reachable": false,
      "free_text_reparsed": false,
      "deterministic": true,
      "input_schema": "candidate edges",
      "output_schema": "normalized/merged edges",
      "test_proof": "tests/test_graph_engine.py"
    },
    {
      "module": "Activation scoring",
      "file": "comqutor_alpha/graph_engine/activation_scorer_v2.py (1182 lines)",
      "llm_imported": false,
      "provider_reachable": false,
      "free_text_reparsed": false,
      "deterministic": true,
      "input_schema": "structure_graph edges + alpha_matches",
      "output_schema": "activation block (alphas[], dominant_alphas, main_conflict)",
      "test_proof": "tests/test_activation_scorer_v2.py"
    },
    {
      "module": "qualification ceiling",
      "file": "comqutor_alpha/graph_engine/activation_scorer_v2.py",
      "llm_imported": false,
      "provider_reachable": false,
      "free_text_reparsed": false,
      "deterministic": true,
      "input_schema": "activation intermediate scores",
      "output_schema": "clamped activation scores",
      "test_proof": "tests/test_activation_scorer_v2.py"
    },
    {
      "module": "Exposure calculation",
      "file": "comqutor_alpha/exposure_engine.py (474 lines)",
      "llm_imported": false,
      "provider_reachable": false,
      "free_text_reparsed": false,
      "deterministic": true,
      "input_schema": "historical_mapping/current_evidence/agent_confidence per Development-Plan-frozen weights 0.50/0.30/0.20",
      "output_schema": "entity_alpha_exposures.json",
      "test_proof": "tests/test_exposure_engine.py",
      "note": "EXPOSURE_WEIGHTS confirmed unchanged (0.50/0.30/0.20) -- exposure formula itself is Development-Plan-sourced, cited here only for deterministic-core-boundary purposes, not a §5.1/5.2/5.3 item."
    },
    {
      "module": "Conflict pair registry",
      "file": "comqutor_alpha/alpha_library/alpha_schema.py (AlphaDefinition.conflict_alphas)",
      "llm_imported": false,
      "provider_reachable": false,
      "free_text_reparsed": false,
      "deterministic": true,
      "input_schema": "alpha_taxonomy_v1.yaml",
      "output_schema": "declared conflict pairs, checked both directions",
      "test_proof": "tests/test_alpha_loader.py, tests/test_week4_conflict_core.py"
    },
    {
      "module": "Conflict admission / score / main-conflict arbitration",
      "file": "comqutor_alpha/conflict_engine/conflict_detector.py (1174 lines) + conflict_schema.py",
      "llm_imported": false,
      "provider_reachable": false,
      "free_text_reparsed": false,
      "deterministic": true,
      "input_schema": "activation payload + alpha_matches",
      "output_schema": "conflict_results.json",
      "test_proof": "tests/test_week4_conflict_core.py",
      "note": "CONFLICT_FORMULA_VERSION = 'week4.conflict_score.mvp_v1' unchanged; formula min(Activation A, Activation B) x contradiction_weight x evidence_strength confirmed frozen per conflict_schema.py:1-8 SOURCE-FROZEN annotation."
    },
    {
      "module": "ticker/run identity",
      "file": "comqutor_alpha/storage/file_store.py (validate_run_id_for_path, validate_ticker)",
      "llm_imported": false,
      "provider_reachable": false,
      "free_text_reparsed": false,
      "deterministic": true,
      "input_schema": "run_id/ticker strings",
      "output_schema": "validated identity strings",
      "test_proof": "tests/test_ticker_consistency_audit.py"
    },
    {
      "module": "artifact export",
      "file": "comqutor_alpha/api/artifact_export.py",
      "llm_imported": false,
      "provider_reachable": false,
      "free_text_reparsed": false,
      "deterministic": true,
      "input_schema": "in-memory graph/conflict/alpha_matches payloads (never recomputed)",
      "output_schema": "evidence_facts.json, evidence_stance_audit.json, run_audit.json, artifact_manifest.json",
      "test_proof": "tests/test_artifact_export_and_api.py"
    },
    {
      "module": "replay identity",
      "file": "comqutor_alpha/replay/pipeline.py (_rebase_structured_payload_for_replay)",
      "llm_imported": false,
      "provider_reachable": false,
      "free_text_reparsed": false,
      "deterministic": true,
      "input_schema": "source structured payload",
      "output_schema": "replay-rebased structured payload (run_id fields only)",
      "test_proof": "tests/test_replay_identity_correction.py"
    },
    {
      "module": "API serialization",
      "file": "comqutor_alpha/api/routes_research.py (build_research_response, get_research_response, get_evidence_stances_response)",
      "llm_imported": false,
      "provider_reachable": false,
      "free_text_reparsed": false,
      "deterministic": true,
      "input_schema": "already-persisted run artifacts",
      "output_schema": "HTTP JSON response bodies",
      "test_proof": "tests/test_artifact_export_and_api.py"
    },
    {
      "module": "Evidence Stance classifier (Sprint 2, additive/shadow)",
      "file": "comqutor_alpha/structure_engine/evidence_stance.py",
      "llm_imported": false,
      "provider_reachable": false,
      "free_text_reparsed": true,
      "deterministic": true,
      "input_schema": "(claim_id, target_alpha_id) + candidate scoring dict",
      "output_schema": "EvidenceStanceResult (additive fields only, effect_mode=shadow)",
      "test_proof": "tests/test_evidence_stance_classifier.py, tests/test_evidence_stance_integration.py",
      "note": "free_text_reparsed=true here is intentional and in-scope: this module's entire job is deterministic regex/rule classification of claim+evidence free text into a stance label. It never reaches a decision that Activation/Conflict/Graph/Exposure treat as authoritative -- see docs/evidence_stance_and_review_sample_report.md for the proof this does not change production score paths."
    }
  ],
  "downstream_free_text_leakage_flagged": false,
  "downstream_free_text_leakage_note": "Every module above except Evidence Stance consumes only already-structured JSON (alpha_matches.json / extracted_structures.json / structure_graph.json / conflict_results.json), never re-parsing an agent's raw prose. Evidence Stance is the sole deterministic-core module that re-parses free text, and it is explicitly a Sprint 2 (John-later-requirement) addition operating in shadow mode, not a Development-Plan-frozen module -- see evidence_stance provenance section of the main report."
}
```

### Appendix 11 — Replay Semantic Reproducibility

Source: `docs/audit_artifacts/replay_semantic_reproducibility.json`

Purpose: Zero-Provider guarantees and LLM-tier replay limitations.

```json
{
  "audit": "phase_0_development_plan_llm_boundary_audit",
  "generated_at": "2026-08-05T00:00:00Z",
  "REPLAY_SEMANTIC_REPRODUCIBILITY": "PARTIAL",
  "confirmed_true": [
    "Replay never calls TradingAgents (no import of tradingagents.graph.trading_graph anywhere in comqutor_alpha/replay/pipeline.py)",
    "Replay never calls an LLM Provider (adapt_run_outputs called with llm_gateway=None explicit at replay/pipeline.py:405; build_alpha_matches_payload/build_extracted_structures_payload called with no llm_gateway kwarg at lines 409-410, defaulting to None)",
    "Replay never calls a market-data provider (no yfinance/data_sanity import in replay/pipeline.py)",
    "DB writes = 0 (repository=None passed explicitly to write_run_audit_artifact at line 609; no repository.persist_* call anywhere in this module)",
    "Replay uses only the source run's saved raw_agent_outputs.json -- explicitly refuses to fall back to a prior structured_agent_outputs.json (ReplaySourceIncompleteError, module docstring lines 6-8)",
    "replay-local run_id (resolved_replay_run_id, format replay-<timestamp>-<uuid> or an explicit deterministic override) is used consistently; source_run_id is preserved only as lineage metadata, never conflated with the replay's own identity (_rebase_structured_payload_for_replay)",
    "Source raw artifact integrity is checked before and after (sha256/size/mtime); any drift flips status to 'blocked', never a false 'completed'",
    "tradingagents_calls / llm_provider_calls / market_data_provider_calls / database_writes are hardcoded literal 0 in every ReplayResult return path -- an architectural guarantee, not a measured counter that could silently drift"
  ],
  "confirmed_false_or_gap": [
    {
      "claim": "Replay can reproduce a historical live run's LLM-influenced semantic output",
      "status": "FALSE for any run where the original live run had COMQUTOR_WEEK2_LLM_ENABLED=true",
      "reasoning": "Because replay always forces llm_gateway=None, any claim-enrichment (entities/factors/direction/confidence), Alpha classifier selection, or LLM-sourced structure edge that the ORIGINAL live run produced via the Week2LLMGateway is NOT reproduced -- replay silently substitutes the deterministic fallback path for those specific claims/edges instead. The replay's own structured_agent_outputs.json / alpha_matches.json / extracted_structures.json will genuinely differ from the original live run's saved artifacts wherever the live run actually used the LLM tier, and replay_comparison.json (built by _build_comparison) will show these as real new/removed edges and claim_count deltas -- it does not hide this, but it also does not attempt to reproduce it.",
      "practical_impact": "Currently low in practice because COMQUTOR_WEEK2_LLM_ENABLED defaults to disabled server-side, so most/all historical runs likely never exercised the LLM tier in the first place (this could not be independently confirmed for every historical run without inspecting each run's own structured_agent_outputs.json metadata.llm_enabled field, which this Phase 0 audit did not enumerate across all outputs/runs/ directories)."
    },
    {
      "claim": "Replay reproduces TradingAgents' own canonical-relation-block output identically",
      "status": "TRUE, conditionally",
      "reasoning": "The canonical_relations array is part of structured_agent_outputs.json's own output (derived by split_human_text_and_canonical_block from the SAVED raw_agent_outputs.json text), so if the original live run's raw text already contains a COMQUTOR_CANONICAL_RELATIONS block, replay deterministically re-parses and re-validates it identically every time -- this part IS Provider-zero and reproducible, since it never re-invokes an LLM, only re-parses already-saved text."
    }
  ],
  "degradation_when_historical_llm_artifact_missing": "There is no separate 'historical LLM artifact' saved independently of raw_agent_outputs.json's embedded canonical-relation-block text -- the LLM-batch-enrichment/alpha_classifier/structure_extractor call RESULTS (as opposed to the deterministic-fallback results) are not separately persisted anywhere for later replay to consume. Replay's only degradation path is therefore always 'use the deterministic fallback,' the same fallback every disabled-gateway live run already uses -- there is no missing-artifact error state distinct from that.",
  "is_current_saved_artifact_sufficient_for_future_provider_zero_replay": "Yes, in the sense that replay already IS Provider-zero today and needs no future change to remain so. No, in the sense that it cannot and will never be able to reconstruct what a historical LLM-enabled live run's LLM tier actually decided, because that decision was never separately persisted -- only its downstream effect (already baked into structured_agent_outputs.json/alpha_matches.json/extracted_structures.json on the SOURCE run's own directory, which replay deliberately does not read for anything except the raw text)."
}
```

### Appendix 12 — Development Plan Compliance Matrix

Source: `docs/audit_artifacts/development_plan_compliance_matrix.csv`

Purpose: Requirement-level status, severity, evidence, and recommended phase.

> **Source-format note:** this artifact contains unquoted delimiter commas, producing non-uniform column counts on source row(s) 6, 13. It is embedded verbatim below instead of being heuristically repaired or rendered as a potentially misleading Markdown table.

```csv
plan_section,plan_requirement,evidence_quote_or_summary,current_file,current_symbol,current_behavior,status,severity,source_frozen_or_extension,recommended_future_phase,notes
Module scope,All new code lives in comqutor_alpha/,task instructions section 5,repo-wide,n/a,"True with one dead exception: tradingagents/comqutor_outputs.py (9-line shim, zero importers)",PARTIAL,MINOR,source_frozen,Phase 1,Remove or clearly document the dead shim; it is the only file physically added inside tradingagents/
Module scope,TradingAgents modifications are output capture hooks only,task instructions section 5,comqutor_alpha/llm/canonical_prompt_injection.py,comqutor_structure_output_contract_scope,"Runtime monkeypatch of get_language_instruction on all 12 native agent modules, appending a new structured-output instruction to every prompt for the run's duration",DIVERGED,MAJOR,source_frozen,Phase 1 addendum,"Functionally a prompt change achieved via monkeypatch rather than a tradingagents/ file edit; adds zero LLM calls and edits zero files on disk, but does change what every agent is asked to produce -- the single most important finding of this audit"
5.1,Converts each agent's natural-language output into standard claim schema via LLM,task instructions section 5.1,comqutor_alpha/structure_engine/structured_output_adapter.py,adapt_raw_agent_outputs / _llm_batch_enrichment,"Claim/evidence segmentation is fully deterministic (never LLM); LLM is an OPTIONAL per-batch enrichment layer limited to entities/factors/direction/confidence, must preserve claim/evidence verbatim, disabled by default",DIVERGED,MAJOR,source_frozen,Phase 1,"The plan's literal wording implies the LLM does primary NL-to-claim conversion; the actual implementation inverts this -- deterministic segmentation is primary and LLM is a bounded enrichment add-on. This is a stricter/safer design, but is a real divergence from the literal plan wording, not a bug"
5.1,Required fields run_id/ticker/agent/timestamp/claim/evidence/entities/factors/direction/confidence/source_type/source_refs,task instructions section 5.1,comqutor_alpha/structure_engine/structured_output_adapter.py,validate_structured_output,All 12 fields present and validated on every record,COMPLIANT,INFORMATIONAL,source_frozen,n/a,see structured_adapter_gap_matrix.csv for per-field sourcing
5.1,Safe default on LLM parse failure; malformed JSON must not propagate; parsing failure must not crash the run,task instructions section 5.1,comqutor_alpha/structure_engine/structured_output_adapter.py + week2_llm.py,safe_default_record / Week2LLMGateway.invoke_json,"invoke_json catches TimeoutError/JSONDecodeError/TypeError/ValueError/KeyError/Exception, logs a stable error_code, retries, then returns None -- callers fall back to deterministic paths; safe_default_record covers empty/invalid raw records",COMPLIANT,INFORMATIONAL,source_frozen,n/a,verified by direct code read, not just docstring claim
5.1,NVDA acceptance includes fundamental/news/sentiment/technical agents,task instructions section 5.1,comqutor_alpha/structure_engine/structured_output_adapter.py,LLM_STRUCTURED_AGENTS,"{market_agent, technical_agent, sentiment_agent, news_agent, fundamental_agent, fundamentals_agent} -- superset includes market_agent too",COMPLIANT,INFORMATIONAL,source_frozen,n/a,n/a
5.2,Three-tier matching in priority order: keyword+factor / LLM classification / rule-based fallback,task instructions section 5.2,comqutor_alpha/structure_engine/alpha_mapper.py,map_claim_to_alpha / _apply_optional_classifier,"All three tiers present and correctly prioritized; Tier 2 only triggers on >=2 deterministically-eligible candidates; Tier 3 fallback keeps the deterministic decision on any LLM failure",COMPLIANT,INFORMATIONAL,source_frozen,n/a,see alpha_mapper_gap_matrix.csv
5.2,First version threshold 0.35,task instructions section 5.2,comqutor_alpha/structure_engine/alpha_mapper.py,DEFAULT_MIN_MATCH_SCORE,0.35 exactly (unchanged since Week 2 per docs/week2_completion_report.md),COMPLIANT,INFORMATIONAL,source_frozen,n/a,n/a
5.2,Top-3 Alpha output,task instructions section 5.2,comqutor_alpha/structure_engine/alpha_mapper.py,top_candidates,candidates[:3] exactly,COMPLIANT,INFORMATIONAL,source_frozen,n/a,n/a
5.2,John's 20 labeled claims; overall accuracy target >= 80%,task instructions section 5.2,repo-wide search,n/a,No file matching a 20-labeled-claims accuracy evaluation of the Alpha Mapper was found in this repository during Phase 0,MISSING,MAJOR,source_frozen,Phase 2,"Cannot confirm this evaluation was ever run/committed; UNKNOWN_NOT_INSTRUMENTED rather than assumed complete or assumed absent beyond what a repo search shows"
5.3,LLM extracts cause-effect relations; strict JSON; fallback on empty result; minimum edge types causal/supportive/conflicting,task instructions section 5.3,comqutor_alpha/structure_engine/structure_extractor.py,extract_structures_from_records / _llm_edges / _validated_llm_edges,"All present; edge types exactly {causal,supportive,conflicting}; per-claim fallback to deterministic rules on any LLM miss",COMPLIANT,INFORMATIONAL,source_frozen,n/a,see structure_extractor_gap_matrix.csv
5.3,duplicate/synonym merging,task instructions section 5.3,comqutor_alpha/structure_engine/structure_extractor.py,edges.setdefault(key,...) + factor_normalizer,"Deterministic (source,target,edge_type,source_record_id) dedup key applied uniformly across LLM/rule/canonical-block edge sources",COMPLIANT,INFORMATIONAL,source_frozen,n/a,n/a
5.3 (implicit),Structure Extractor edges derive from a dedicated LLM extraction call only,task instructions section 5.3,comqutor_alpha/structure_engine/structure_extractor.py + canonical_relation_prompt.py,_canonical_relation_edges_and_nodes,A third edge source (CANONICAL_BLOCK) exists: edges reported by TradingAgents' own single existing call via a prompt-injected structured-output contract -- not the dedicated `structure_extractor` Week2LLMGateway task at all,DIVERGED,MAJOR,source_frozen,Phase 1 addendum,Same underlying finding as the TradingAgents modification-scope divergence above; the two are linked
Replay,Provider calls = 0; DB writes = 0; uses saved outputs only,task instructions section 13,comqutor_alpha/replay/pipeline.py,run_structure_replay,Confirmed by direct code read + scripts/audit_llm_boundary.py automated check,COMPLIANT,INFORMATIONAL,source_frozen,n/a,n/a
Replay,Reproduces the historical live run's LLM semantic output,task instructions section 13,comqutor_alpha/replay/pipeline.py,adapt_run_outputs(llm_gateway=None) / build_alpha_matches_payload / build_extracted_structures_payload,"Cannot reproduce LLM-tier decisions from a historical LLM-enabled live run -- always substitutes deterministic fallback for those claims/edges",PARTIAL,MAJOR,source_frozen,Phase 1,see replay_semantic_reproducibility.json
Deterministic core,Activation/Conflict/Graph/Exposure carry no LLM authority,task instructions section 12,comqutor_alpha/graph_engine + conflict_engine + exposure_engine.py,n/a,Zero LLM imports found; grep-confirmed and mechanically re-checked by scripts/audit_llm_boundary.py,COMPLIANT,INFORMATIONAL,source_frozen,n/a,n/a
Evidence Stance,supports_alpha/opposes_alpha/mentions_alpha/neutral_background/supports_counter_alpha classification,N/A -- not present in any Development Plan fragment found in this repo,comqutor_alpha/structure_engine/evidence_stance.py,classify_evidence_stance,"Deterministic rule/regex classifier, shadow-mode only (effect_mode=shadow), never affects Activation/Conflict/Graph/Exposure scoring",NOT_APPLICABLE,INFORMATIONAL,JOHN_LATER_REQUIREMENT,Proposed Addendum,"Must not be described as Development-Plan-frozen content; see docs/evidence_stance_and_review_sample_report.md's own framing ('John's own fixed test case') for corroboration"
Cache/observability,LLM response cache expected,task instructions section 14,repo-wide search,n/a,No cache found anywhere in the LLM call path,NOT_IMPLEMENTED,MINOR,source_frozen,Phase 1,Real cost/duplicate-call risk when COMQUTOR_WEEK2_LLM_ENABLED is on -- see provider_call_baseline.json duplicate_text_recall_risk
```

### Appendix 13 — Proposed Phase 1-3 Migration Plan

Source: `docs/audit_artifacts/proposed_phase_1_3_plan.json`

Purpose: Gap remediation, compatibility, tests, cutover, and product decisions.

```json
{
  "audit": "phase_0_development_plan_llm_boundary_audit",
  "generated_at": "2026-08-05T00:00:00Z",
  "scope_note": "Phase 0 implements nothing. Every item below is a recommendation only, strictly limited to LLM functionality the task's own quoted Development Plan §5.1/§5.2/§5.3 wording already allows. Evidence Stance LLM-ification is deliberately excluded from Phases 1-3 and placed in the Proposed Addendum instead, per explicit instruction.",
  "phase_1": {
    "title": "Development-Plan Structured Output Adapter",
    "current_gap": "Structured Output Adapter already exists and is largely compliant (see structured_adapter_gap_matrix.csv), but (a) the accuracy/coverage of LLM-vs-deterministic claim/evidence extraction has never been evaluated against a labeled set, and (b) it is currently opt-in and off by default, so in practice most historical runs never exercised it at all.",
    "files_likely_affected": [
      "comqutor_alpha/structure_engine/structured_output_adapter.py",
      "comqutor_alpha/structure_engine/week2_llm.py",
      "docs/audit_artifacts/structured_adapter_gap_matrix.csv (baseline reference)"
    ],
    "existing_code_reusable": "Week2LLMGateway (retry/timeout/budget), _validate_llm_batch_enrichment strict schema, safe_default_record fallback -- all already production-grade and reusable as-is.",
    "provider_call_impact": "No change to call count logic; would only change whether COMQUTOR_WEEK2_LLM_ENABLED defaults on for a defined rollout population.",
    "prompt_impact": "None required -- PROMPT-01 already matches plan intent.",
    "schema_impact": "None -- structured_agent_outputs.json schema_version unchanged.",
    "replay_impact": "None -- replay already correctly forces llm_gateway=None and would continue to.",
    "backward_compatibility": "Full -- purely a rollout/measurement change, not a code-shape change.",
    "tests_needed": "A labeled-claim accuracy evaluation harness (does not currently exist per compliance matrix MISSING finding) to measure enrichment quality before any default-on decision.",
    "cutover_strategy": "Enable COMQUTOR_WEEK2_LLM_ENABLED in a staging/shadow environment first, compare structured_agent_outputs.json quality metrics against the deterministic-only baseline, then decide on a production default.",
    "blockers": "No accuracy baseline exists yet to compare against.",
    "explicit_non_goals": ["Changing the deterministic segmentation boundary", "Removing the verbatim claim/evidence preservation guarantee", "Adding a second LLM call per report"]
  },
  "phase_2": {
    "title": "Development-Plan Hybrid Alpha Mapper",
    "current_gap": "Tier 1/2/3 already implemented and compliant. The missing piece is the plan-mandated evaluation: John's 20 labeled claims and the >=80% accuracy target were not found anywhere in this repository (MISSING in compliance matrix).",
    "files_likely_affected": [
      "comqutor_alpha/structure_engine/alpha_mapper.py (no code change expected)",
      "a new evaluation harness under comqutor_alpha/evaluation/ or tests/, analogous in spirit to evaluation/ already in the repo"
    ],
    "existing_code_reusable": "map_claim_to_alpha's existing candidate_scores/eligible_candidates/classifier metadata already expose everything an accuracy harness needs without any pipeline change.",
    "provider_call_impact": "None if the evaluation runs against already-saved historical claims; would add calls only if run live against the LLM tier.",
    "prompt_impact": "None.",
    "schema_impact": "None.",
    "replay_impact": "None -- an accuracy evaluation is a separate offline script, not a pipeline stage.",
    "backward_compatibility": "Full.",
    "tests_needed": "Obtain or reconstruct John's 20 labeled claims (not found in-repo); build a deterministic scoring harness; report accuracy against the 80% target explicitly, honestly, per-claim.",
    "cutover_strategy": "n/a -- this is a measurement/reporting phase, not a code cutover.",
    "blockers": "The 20 labeled claims themselves are not present in this repository and must be sourced from the product owner before this phase can start.",
    "explicit_non_goals": ["Changing scoring weights (0.50/0.30/0.08/0.12)", "Changing min_score=0.35", "Changing top-3 output shape"]
  },
  "phase_3": {
    "title": "Development-Plan LLM Structure Extractor",
    "current_gap": "The dedicated `structure_extractor` LLM task is compliant and already gated by deterministic evidence-backing re-validation. The real gap is architectural clarity: a third, undocumented-in-the-plan edge source (CANONICAL_BLOCK, from the prompt-injected TradingAgents native call) already contributes real production edges alongside it, and the two are not clearly distinguished in any user-facing artifact today beyond the internal extraction_method field.",
    "files_likely_affected": [
      "comqutor_alpha/structure_engine/structure_extractor.py (documentation/metadata surfacing only)",
      "comqutor_alpha/llm/canonical_prompt_injection.py (see Proposed Addendum for the deeper compliance question)"
    ],
    "existing_code_reusable": "extracted_structures.json's metadata already tracks llm_edge_count / deterministic_edge_count / canonical_relation_edge_count separately -- this data already exists and only needs surfacing in reports/UI.",
    "provider_call_impact": "None.",
    "prompt_impact": "None to the dedicated structure_extractor task prompt itself.",
    "schema_impact": "None -- purely a reporting/documentation change.",
    "replay_impact": "None -- RULE_EXTRACTED and CANONICAL_BLOCK edges already replay deterministically; LLM_EXTRACTED edges already correctly do not.",
    "backward_compatibility": "Full.",
    "tests_needed": "A run-level report (or UI badge) distinguishing LLM_EXTRACTED / RULE_EXTRACTED / CANONICAL_BLOCK edges for any given ticker/run, so product owners can see the real provenance mix.",
    "cutover_strategy": "Additive reporting change only.",
    "blockers": "None technical; requires a product decision on whether CANONICAL_BLOCK edges should be renamed/reclassified as a fourth Development-Plan-recognized source rather than silently folded into '5.3 LLM edges' in casual conversation.",
    "explicit_non_goals": ["Adding a second LLM call to produce canonical-relation edges", "Changing VALID_EDGE_TYPES"]
  },
  "proposed_addendum": {
    "title": "TradingAgents Prompt-Injection Compliance Review (not Evidence Stance LLM-ification -- see note)",
    "note_on_evidence_stance": "The task instructions asked that 'Evidence Stance LLM化' specifically be isolated into this Addendum, not Phases 1-3. No work toward making Evidence Stance LLM-driven has been proposed, scoped, or started anywhere in this repository as of this audit; Evidence Stance remains a purely deterministic, shadow-mode, John-later-requirement module (see evidence_stance provenance section of the main report). This Addendum instead documents the other item the task explicitly said must not be silently folded into Phase 1-3 frozen scope: the TradingAgents prompt-injection mechanism.",
    "items": [
      {
        "item": "Reclassify canonical_prompt_injection.py's runtime monkeypatch against the literal Development Plan wording 'TradingAgents modifications are output capture hooks'",
        "why_flagged": "This audit's single highest-severity finding (DIVERGED/MAJOR in the compliance matrix) is that this mechanism changes every native agent's effective prompt at runtime, even though it edits zero files under tradingagents/ and adds zero LLM calls. Whether this is acceptable requires a product decision, not an engineering one -- Phase 0 explicitly may not modify this mechanism or decide the question itself.",
        "decision_needed_from_product": "Does 'output capture hooks only' mean (a) no tradingagents/ file may be edited on disk (satisfied today), or (b) no runtime change to what an agent is asked to produce at all (not satisfied today)? This audit cannot resolve that ambiguity -- it can only make the gap explicit."
      },
      {
        "item": "Evidence-Stance-LLM-ification placeholder (intentionally unscoped)",
        "why_flagged": "Reserved per task instructions so a future explicit request can scope it separately; no proposal is made here."
      }
    ]
  }
}
```

## Part III — Read-Only Verification

### Fresh Verification Result

The builder reran the verification script before producing this snapshot. All four checks passed:

```text
[PASS] replay_never_passes_live_llm_gateway: adapt_run_outputs explicit llm_gateway=None: True; build_alpha_matches_payload called with no llm_gateway kwarg (defaults None): True; build_extracted_structures_payload called with no llm_gateway kwarg (defaults None): True
[PASS] deterministic_core_has_zero_llm_imports: no offenders
[PASS] three_llm_tasks_share_one_gateway_chokepoint: gateway defines all 3 task instructions: True; adapter calls invoke_json('claim_batch_enrichment', ...): True; mapper calls invoke_json('alpha_classifier', ...): True; extractor calls invoke_json('structure_extractor', ...): True
[PASS] live_gateway_requires_explicit_env_opt_in: COMQUTOR_WEEK2_LLM_ENABLED opt-in gate present
OVERALL: PASS
```

### Verification Script

Source: `scripts/audit_llm_boundary.py`

Properties: read-only; not imported by production; zero network, LLM/Provider, or database calls.

```python
"""Phase 0 -- Development-Plan LLM Boundary Audit: read-only verification.

Never imported by any production module. Performs zero network/LLM/DB
calls and never writes under ``outputs/``. Re-derives, from the current
repository state, the small set of structural facts the Phase 0 audit
report (``docs/development_plan_llm_boundary_audit.md``) depends on, so
they can be re-checked mechanically instead of only by prose claim:

- Architecture Replay (``comqutor_alpha/replay/pipeline.py``) never passes
  a live ``llm_gateway`` into the adapter/mapper/extractor builders.
- The deterministic core (graph_engine, conflict_engine, exposure*,
  structure_engine/evidence_stance.py) imports no LLM gateway module.
- The three real Week 2 LLM call sites (claim_batch_enrichment,
  alpha_classifier, structure_extractor) still route through the single
  ``Week2LLMGateway.invoke_json`` chokepoint.

Run: ``python scripts/audit_llm_boundary.py`` from the repo root.
Exit code 0 means every check passed; 1 means at least one did not
(printed per-check below) -- this script only reports; it changes nothing.
"""

from __future__ import annotations

import re
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]

DETERMINISTIC_CORE_DIRS = (
    "comqutor_alpha/graph_engine",
    "comqutor_alpha/conflict_engine",
    "comqutor_alpha/exposure",
)
DETERMINISTIC_CORE_FILES = (
    "comqutor_alpha/exposure_engine.py",
    "comqutor_alpha/structure_engine/evidence_stance.py",
)
LLM_IMPORT_PATTERN = re.compile(
    r"^\s*(?:from\s+comqutor_alpha\.(?:llm|structure_engine\.week2_llm)\s+import|"
    r"import\s+comqutor_alpha\.(?:llm|structure_engine\.week2_llm))",
    re.MULTILINE,
)


def _read(relative_path: str) -> str:
    return (REPO_ROOT / relative_path).read_text(encoding="utf-8")


def check_replay_never_passes_live_gateway() -> tuple[bool, str]:
    text = _read("comqutor_alpha/replay/pipeline.py")
    adapter_call_ok = "adapt_run_outputs(source_run_dir, llm_gateway=None)" in text
    mapper_call = re.search(r"build_alpha_matches_payload\(structured\)", text)
    extractor_call = re.search(r"build_extracted_structures_payload\(structured\)", text)
    ok = bool(adapter_call_ok and mapper_call and extractor_call)
    detail = (
        f"adapt_run_outputs explicit llm_gateway=None: {adapter_call_ok}; "
        f"build_alpha_matches_payload called with no llm_gateway kwarg "
        f"(defaults None): {bool(mapper_call)}; "
        f"build_extracted_structures_payload called with no llm_gateway kwarg "
        f"(defaults None): {bool(extractor_call)}"
    )
    return ok, detail


def check_deterministic_core_no_llm_import() -> tuple[bool, str]:
    offenders: list[str] = []
    py_files: list[Path] = []
    for rel_dir in DETERMINISTIC_CORE_DIRS:
        directory = REPO_ROOT / rel_dir
        if directory.is_dir():
            py_files.extend(sorted(directory.rglob("*.py")))
    for rel_file in DETERMINISTIC_CORE_FILES:
        py_files.append(REPO_ROOT / rel_file)

    for path in py_files:
        if "__pycache__" in path.parts or not path.exists():
            continue
        text = path.read_text(encoding="utf-8")
        if LLM_IMPORT_PATTERN.search(text):
            offenders.append(str(path.relative_to(REPO_ROOT)))

    ok = not offenders
    detail = "no offenders" if ok else f"offenders: {offenders}"
    return ok, detail


def check_three_llm_tasks_share_one_gateway_chokepoint() -> tuple[bool, str]:
    gateway_text = _read("comqutor_alpha/structure_engine/week2_llm.py")
    tasks_present = all(
        f'"{task}"' in gateway_text
        for task in ("claim_batch_enrichment", "alpha_classifier", "structure_extractor")
    )
    invoke_json_def = "def invoke_json(" in gateway_text

    adapter_text = _read("comqutor_alpha/structure_engine/structured_output_adapter.py")
    mapper_text = _read("comqutor_alpha/structure_engine/alpha_mapper.py")
    extractor_text = _read("comqutor_alpha/structure_engine/structure_extractor.py")
    adapter_calls = 'llm_gateway.invoke_json(\n        "claim_batch_enrichment"' in adapter_text
    mapper_calls = '"alpha_classifier"' in mapper_text and "llm_gateway.invoke_json(" in mapper_text
    extractor_calls = '"structure_extractor"' in extractor_text and "llm_gateway.invoke_json(" in extractor_text

    ok = bool(tasks_present and invoke_json_def and adapter_calls and mapper_calls and extractor_calls)
    detail = (
        f"gateway defines all 3 task instructions: {tasks_present}; "
        f"adapter calls invoke_json('claim_batch_enrichment', ...): {adapter_calls}; "
        f"mapper calls invoke_json('alpha_classifier', ...): {mapper_calls}; "
        f"extractor calls invoke_json('structure_extractor', ...): {extractor_calls}"
    )
    return ok, detail


def check_gateway_requires_explicit_opt_in() -> tuple[bool, str]:
    text = _read("comqutor_alpha/structure_engine/week2_llm.py")
    ok = 'os.environ.get("COMQUTOR_WEEK2_LLM_ENABLED")' in text and "return None" in text
    return ok, "COMQUTOR_WEEK2_LLM_ENABLED opt-in gate present" if ok else "opt-in gate not found"


CHECKS = (
    ("replay_never_passes_live_llm_gateway", check_replay_never_passes_live_gateway),
    ("deterministic_core_has_zero_llm_imports", check_deterministic_core_no_llm_import),
    ("three_llm_tasks_share_one_gateway_chokepoint", check_three_llm_tasks_share_one_gateway_chokepoint),
    ("live_gateway_requires_explicit_env_opt_in", check_gateway_requires_explicit_opt_in),
)


def main() -> int:
    all_ok = True
    for name, check in CHECKS:
        ok, detail = check()
        all_ok = all_ok and ok
        status = "PASS" if ok else "FAIL"
        print(f"[{status}] {name}: {detail}")
    print("OVERALL:", "PASS" if all_ok else "FAIL")
    return 0 if all_ok else 1


if __name__ == "__main__":
    raise SystemExit(main())
```
