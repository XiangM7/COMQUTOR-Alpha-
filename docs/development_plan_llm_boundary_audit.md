# Phase 0 — Development-Plan LLM Boundary and Repository Audit

Read-only architecture audit. No production behavior, LLM/Provider call, database write, or historical source artifact was changed by this audit. No commit/push occurred.

## 1. Executive Verdict

- **Canonical Development Plan source: NOT FOUND IN REPOSITORY.** No file named or titled "COMQUTOR Alpha Development Plan v1.0" exists anywhere in this repo (PDF/DOCX/Markdown). This is a zero-canonical-copy situation, not a multi-version-ambiguity situation — see §2 and `docs/audit_artifacts/development_plan_source_inventory.json`. This audit therefore treats the task instructions' own quoted §5.1/§5.2/§5.3 wording as authoritative input, cross-checked against independent in-repo paraphrases wherever they exist.
- **§5.1 Structured Output Adapter: DIVERGED (but stricter/safer than the plan's literal wording).** Claim/evidence segmentation is fully deterministic; the LLM is an optional, bounded per-batch *enrichment* layer (entities/factors/direction/confidence only), not the primary NL→claim converter the plan's wording implies. Off by default (`COMQUTOR_WEEK2_LLM_ENABLED`).
- **§5.2 Alpha Mapper: COMPLIANT.** All three tiers present, correctly prioritized, threshold 0.35 and top-3 output unchanged. The plan-mandated 20-labeled-claims / ≥80%-accuracy evaluation was **not found** in this repository (MISSING, see compliance matrix).
- **§5.3 Structure Extractor: DIVERGED.** A third, plan-unlisted edge source exists in production (`CANONICAL_BLOCK`, sourced from TradingAgents' own single existing call via a prompt-injected structured-output contract), alongside the plan's two expected sources (LLM/rule).
- **TradingAgents modification rule ("output capture hooks only"): DIVERGED — this is the audit's single highest-severity finding.** `comqutor_alpha/llm/canonical_prompt_injection.py` monkeypatches all 12 native agent prompt-builder modules at runtime to append a new structured-output instruction. Zero files under `tradingagents/` are edited on disk and zero new LLM calls are added, but the *effective prompt content* every agent receives is changed for the duration of every run. This satisfies the letter of "don't edit tradingagents/ files" while not satisfying the substance of "output capture hooks only."
- **Deterministic core (Activation/Conflict/Graph/Exposure/replay identity/API serialization): COMPLIANT.** Zero LLM imports, confirmed by grep and by the new read-only `scripts/audit_llm_boundary.py` (all 4 automated checks PASS).
- **Replay Provider-zero path: COMPLIANT for zero-Provider-calls, PARTIAL for semantic reproducibility.** Replay never calls TradingAgents/an LLM/a market-data provider/the DB — confirmed both by direct code read and by the automated script. It cannot, however, reproduce a historical live run's LLM-tier decisions (it always substitutes the deterministic fallback) — see §16 and `replay_semantic_reproducibility.json`.
- **Evidence Stance: correctly out of Development-Plan scope.** Zero LLM calls anywhere in this module; shadow-mode only; John-later-requirement, not source-frozen.
- **No production code, historical source artifact, or `outputs/runs/` content was changed. No commit/push.**

## 2. Canonical Development Plan Source

Search commands run (see `development_plan_source_inventory.json` for the full record):

```
find . -iname '*COMQUTOR*Development*Plan*' -o -iname '*development_plan*' -o -iname '*Development_Plan*'
grep -rl "COMQUTOR Alpha Development Plan" . --include=*.md --include=*.txt --include=*.pdf
grep -rl "Development Plan" . --exclude-dir=.git --exclude-dir=node_modules --exclude-dir=.venv
```

**Result: zero files found matching the Development Plan by filename or by exact title string.** `DEVELOPMENT_PLAN_VERSION_AMBIGUITY` does not apply (no two differing copies exist to disagree) — the correct flag is that the canonical source document itself is absent from this repository. The Development Plan is, however, referenced by name dozens of times across prior sprint reports and frozen-constant docstrings (see the six corroborating fragments quoted in the JSON artifact), alongside two other named external documents ("Helix Quantum Intelligence Operating System White Paper v2.0", "SIC Omnibus Provisional Draft v2") that together form the project's documented three-document source-of-truth hierarchy (`docs/week4_spec_freeze_audit.md` §3). Every plan requirement this report cites is either (a) quoted verbatim from the task instructions themselves, or (b) independently corroborated by an in-repo paraphrase — the two are distinguished throughout.

## 3. Frozen LLM Boundaries (as given in task instructions, treated as authoritative)

- **Module scope**: all new code lives in `comqutor_alpha/`; TradingAgents source modified only minimally; modifications are output capture hooks.
- **§5.1**: LLM converts NL agent output → standard claim schema; downstream consumes only this JSON; 12 required fields; safe default on parse failure; malformed JSON must not propagate/crash; NVDA acceptance covers fundamental/news/sentiment/technical.
- **§5.2**: 3-tier matching (keyword+factor → LLM → rule fallback); threshold 0.35; top-3 output; John's 20 labeled claims; ≥80% accuracy target.
- **§5.3**: LLM extracts cause-effect relations → StructureNode/StructureEdge; strict JSON; fallback on empty result; duplicate/synonym merge; edge types causal/supportive/conflicting.

Evidence Stance, ticker specificity, Clause Graph, Counter-Alpha stance, and dynamic invalidation conditions are **not** part of this frozen scope (see §14).

## 4. Current Semantic Pipeline

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

## 5. Live Call Graph

See `semantic_pipeline_call_graph.json`, `path_summary.A_live_run_path`. Entry: `POST /api/research` → `run_research_request` (`routes_research.py:2286`) → `run_original_tradingagents_research`/`run_streaming_tradingagents_research` (`tradingagents_runner.py:113`/`280`) → `_run_week1_week2_artifact_pipeline` (`routes_research.py:694`) → `_run_week3_graph_pipeline` (`routes_research.py:2101`).

## 6. Replay Call Graph

See `semantic_pipeline_call_graph.json`, `path_summary.C_architecture_replay_path`. Entry: `run_structure_replay` (`replay/pipeline.py:363`), reprocessing only the source run's saved `raw_agent_outputs.json`, writing exclusively to a new `outputs/replays/replay-<ts>-<uuid>/` directory. `llm_gateway=None` is explicit (adapter) or defaulted (mapper/extractor) at every stage; `tradingagents_calls`/`llm_provider_calls`/`market_data_provider_calls`/`database_writes` are hardcoded literal `0` in every `ReplayResult` return path.

## 7. LLM Call-Site Inventory

Full inventory: `docs/audit_artifacts/llm_call_site_inventory.json` (COMQUTOR Week2 tier, chokepointed through `Week2LLMGateway.invoke_json`) plus the repo-wide sub-agent findings for the TradingAgents native tier (13 native call sites across 12 agents + 1 reflection call), test/fake sites, and dead/legacy code. Three real COMQUTOR call sites: `CS-01` claim_batch_enrichment (§5.1), `CS-02` alpha_classifier (§5.2), `CS-03` structure_extractor (§5.3) — all three share one `Week2LLMGateway` instance per run and therefore one per-run call budget (default 32, server cap 100), not independent per-module budgets. No call site was misreported from a bare import or variable name; every entry above was confirmed by locating the actual `.invoke(`/`invoke_json(` call.

## 8. Prompt Inventory

Full inventory with hashing/versioning/retry/failure behavior per prompt: `docs/audit_artifacts/llm_prompt_inventory.csv`. Six prompt families: three Week2LLMGateway task instructions (claim_batch_enrichment / alpha_classifier / structure_extractor), the shared gateway wrapper, the TradingAgents Structure Output Contract suffix (`canonical_relation_prompt.py`, deterministically hashable via `compute_prompt_contract_sha256`, recorded per-run in `tradingagents_comqutor_vocabulary_snapshot.json`), and the 12 native TradingAgents agent prompts themselves (upstream, unmodified on disk). All three Week2 prompts require strict JSON and restrict output vocabulary to caller-supplied allowed IDs; none allow free invention of new Alpha/factor/relation IDs; none allow fabricated source quotes (the Structure Output Contract explicitly requires `evidence_quote` to be a verbatim substring of the agent's own report, rule 11 of 14).

## 9. Provider-Call Baseline

Full stage matrix and direct answers to all required questions: `docs/audit_artifacts/provider_call_baseline.json`. Key facts, never invented:

- Adapter is called **per raw agent output (report), batched** in groups of ≤64 segments — never per individual claim.
- Alpha Mapper Tier 2 is called **only for claims with ≥2 deterministically-eligible candidates** — this is the code-level definition of "ambiguous" (`alpha_mapper.py:340`).
- Structure Extractor is called **per claim** with ≥2 deterministic factors.
- Exact per-run call counts: **UNKNOWN_NOT_INSTRUMENTED** — no fleet-wide counter exists; each run's own realized count *is* reconstructable from that run's own `structured_agent_outputs.json`/`alpha_matches.json`/`extracted_structures.json` metadata, but no aggregate baseline was computed in this repo prior to this audit, and this audit did not fabricate one.
- **No LLM response cache exists anywhere.** Duplicate-text re-calling is a real, currently-unaddressed risk when the LLM tier is enabled.
- Replay cannot accidentally trigger a Provider call (§6, confirmed by both manual read and automated script).

## 10. §5.1 Structured Output Adapter Verdict

**5.1_STATUS: DIVERGED** (stricter/safer than literal plan wording, not unsafe).

Full field-level matrix: `docs/audit_artifacts/structured_adapter_gap_matrix.csv`. Evidence: claim/evidence text is deterministically segmented first and is **never** LLM-originated; an LLM enrichment batch must return `claim`/`evidence`/`source_section` byte-for-byte identical to the input or the entire batch is rejected and falls back to deterministic enrichment (`_validate_llm_batch_enrichment`, `structured_output_adapter.py:882-953`). All 12 required fields are present and validated (`validate_structured_output`). Malformed JSON/timeout/budget-exhaustion never propagate or crash (`Week2LLMGateway.invoke_json`'s exhaustive except chain, `week2_llm.py:187-196`). LLM_STRUCTURED_AGENTS covers fundamental/fundamentals/news/sentiment/technical/market — a superset of the plan's named four. Boilerplate/disclaimer/transition filtering and dedupe both happen deterministically **before** any LLM involvement, never after.

## 11. §5.2 Alpha Mapper Verdict

**5.2_STATUS: COMPLIANT** (implementation), **MISSING** (plan-mandated evaluation).

Three-tier matrix: `docs/audit_artifacts/alpha_mapper_gap_matrix.csv`. Tier 1 (keyword+factor+direction+semantic, weights 0.50/0.30/0.08/0.12) always runs first for all 10 taxonomy alphas. Tier 2 LLM classifier can only select-or-defer among the ≤3 already-deterministically-eligible candidates (`allowed_alpha_ids`); cannot create candidates, change admissibility, or emit a trading decision; gated behind `COMQUTOR_WEEK2_LLM_ENABLED`, off by default. Tier 3 fallback is literally "keep the pre-computed deterministic decision" on any LLM failure — never a crash, never a bare "unknown." Threshold 0.35 and top-3 output confirmed unchanged since Week 2. Evidence Stance is co-located in the same function (`map_claim_to_alpha`) and the same `alpha_matches.json` artifact, but does **not** share scoring/eligibility/matched_alpha authority — see §14 for the precise distinction between code co-location and decision authority. **John's 20 labeled claims and the ≥80% accuracy evaluation were not found anywhere in this repository** — this is reported as MISSING, not assumed complete and not assumed never-run.

## 12. §5.3 Structure Extractor Verdict

**5.3_STATUS: DIVERGED.**

Full Q&A matrix with edge-source classification: `docs/audit_artifacts/structure_extractor_gap_matrix.csv`. Edge types are exactly `{causal, supportive, conflicting}` (`VALID_EDGE_TYPES`, `structure_schema.py:16`) with no additions. Three edge sources feed one merged graph: `LLM_EXTRACTED` (dedicated `structure_extractor` Week2LLMGateway task, per-claim, deterministic evidence-backing + causal-direction re-validated before acceptance), `RULE_EXTRACTED` (`relation_grammar.py` pattern rules, always the fallback and the only path when the gateway is off), and `CANONICAL_BLOCK` (edges reported inside TradingAgents' own single existing call's response, via the prompt-injected Structure Output Contract — **not** a second LLM call, but also **not** the plan's named §5.3 LLM extractor). All three sources share one deterministic dedup key and one lineage/provenance contract. The `CANONICAL_BLOCK` source is the direct consequence of the TradingAgents-modification finding in §13 — the two are one underlying architectural decision, reported from two angles.

## 13. TradingAgents Modification Verdict

Full modification table: `docs/audit_artifacts/tradingagents_modification_audit.csv`.

- **On-disk footprint inside `tradingagents/` is minimal**: one 9-line, zero-importer dead shim (`tradingagents/comqutor_outputs.py`). A clean vendor-add baseline commit (`cc97cb6d`, TradingAgents v0.1.0) exists in git history; 160 of 162 subsequent commits touching `tradingagents/` are attributed to upstream-style contributors and contain zero "comqutor" string hits in their diffs (strong internal signal, not a cryptographic guarantee — no `upstream/*` ref was fetched in this offline audit).
- **(a) Has any agent prompt been modified to add canonical-relation-block output?** Yes, functionally, via `comqutor_alpha/llm/canonical_prompt_injection.py:66-100`, which monkeypatches the `get_language_instruction` attribute already imported by all 12 native agent modules, for the duration of every `propagate()`/`stream()` call (activated at `tradingagents_runner.py` lines ~171 and ~383). The injected text (`canonical_relation_prompt.py:103-174`) instructs the LLM to append a `COMQUTOR_CANONICAL_RELATIONS` JSON block after its normal report. Zero files under `tradingagents/` are edited on disk.
- **(b) Hooks-only or behavior change?** Both exist and must be judged separately: `tradingagents_output_writer.py` (reads `final_state` after the run, writes JSON) is a genuine passive capture hook. `canonical_prompt_injection.py` is not passive — it actively changes what every agent is asked to produce.
- **(c) Extra LLM calls added?** No. Confirmed by direct grep of `canonical_relation_block.py`/`structured_output_adapter.py`/`tradingagents_output_writer.py` for `.invoke(`/`ChatOpenAI(`/`ChatAnthropic(`/`get_llm(` — zero hits. The canonical block is parsed out of the same single response each agent already produces.
- **This is the audit's central, highest-severity compliance finding** (DIVERGED/MAJOR in the compliance matrix): it satisfies "don't edit files under `tradingagents/`" literally, while not satisfying "output capture hooks only" in substance. This is a product decision, not an engineering defect — flagged, not resolved, by Phase 0 (see Proposed Addendum, §19).

## 14. Evidence Stance Provenance

- **Classification: C — John-later-requirement**, not A (source-frozen) and not B (directly implied by source-frozen functionality). No fragment of the Development Plan found anywhere in this repository (§2) mentions stance, polarity, or the five-way `supports_alpha`/`opposes_alpha`/`mentions_alpha`/`neutral_background`/`supports_counter_alpha` vocabulary. The module's own delivery report is explicit about this provenance: `docs/evidence_stance_and_review_sample_report.md` attributes its test cases and validation criteria directly to "John's own fixed test case" / "John's own judgment," never to the Development Plan.
- **Zero LLM calls anywhere in `evidence_stance.py`** — confirmed by import-statement inspection (§16 of the deterministic-core-boundary artifact) and corroborated by the module's own prior-sprint AST-import-graph proof that it is a dependency-free leaf module, never imported by `activation_scorer_v2.py`/`conflict_detector.py`, and never importing `alpha_mapper.py`.
- **Not Alpha Mapper Tier 3.** Tier 3 in the Development Plan sense is the *rule fallback when the LLM classifier fails* (§11) — a completely different mechanism, already implemented and unrelated to Evidence Stance. Evidence Stance instead runs as an always-on, additive, shadow-mode classification alongside Tier 1 scoring, inside the same `map_claim_to_alpha` function call and the same `alpha_matches.json` artifact.
- **Does it substitute for the ambiguous-semantics-processing the plan expected an LLM to do?** In effect, yes for a narrow slice: it performs rule-based, alpha-relative direction/stance classification of free text, which is exactly the kind of task the Development Plan's overall philosophy (LLM handles ambiguity, rules handle the rest) would have routed to an LLM. It was built as a **deterministic** substitute specifically because the task that commissioned it explicitly forbade any new LLM/Provider call.
- **Does it affect production scoring today?** No — `effect_mode="shadow"`, `stance_effect_applied=False` on every artifact; proven unchanged both structurally (import-graph) and empirically (real replay comparison against the pre-Evidence-Stance baseline) in the prior sprint that built it.
- **Future role**: could become a validator/fallback signal once John's 50-row human review (currently `PENDING`) completes, but that decision requires explicit product approval, not an inference from this audit.
- **Fields requiring product approval before any LLM output could ever be used for stance**: none currently planned — Evidence Stance LLM-ification is deliberately unscoped (Proposed Addendum, §19) pending a future explicit request.

## 15. Deterministic Core Boundary

Full 15-module matrix: `docs/audit_artifacts/deterministic_core_boundary_audit.json`. Every module — taxonomy loading, Evidence Fact grouping, claim dedupe, graph admission/normalization, Activation scoring + qualification ceiling, Exposure calculation, Conflict pair registry/admission/score/main-conflict arbitration, ticker/run identity, artifact export, replay identity, API serialization — has **zero LLM imports**, confirmed both manually (grep) and mechanically (`scripts/audit_llm_boundary.py::check_deterministic_core_no_llm_import`, which re-runs the same check on demand). `DOWNSTREAM_FREE_TEXT_LEAKAGE` is **not** flagged for any of these 14 modules — all consume only already-structured JSON. It **is** correctly present for the 15th module, Evidence Stance, whose entire job is re-parsing claim/evidence free text — but that module never feeds a decision any of the other 14 treat as authoritative, so it is a contained, documented exception rather than a leakage defect.

## 16. Replay Semantic Reproducibility

**REPLAY_SEMANTIC_REPRODUCIBILITY: PARTIAL.** Full detail: `docs/audit_artifacts/replay_semantic_reproducibility.json`.

Confirmed **PASS** on every zero-Provider/zero-DB/zero-TradingAgents guarantee (both by direct code read and the automated script). Confirmed **gap**: replay always forces `llm_gateway=None`, so it can never reproduce a historical live run's LLM-tier enrichment/classification/edge decisions — it silently substitutes the deterministic fallback for exactly those claims/edges instead, and `replay_comparison.json` will show the resulting deltas honestly (it does not hide this) but does not attempt to close the gap. Practical impact is currently believed low because the LLM tier defaults off, but this was **not** independently verified across every historical run in `outputs/runs/` — reported as an acknowledged unknown, not swept under a PASS verdict. `CANONICAL_BLOCK` edges, being derived from already-saved raw text, **do** replay identically.

## 17. Retry / Cache / Observability

- **Retry**: `Week2LLMGateway` — yes, explicit bounded loop, default 1 retry, server cap 2 (`week2_llm.py:176-196`). TradingAgents native agent calls — **UNKNOWN/SDK-default**, no explicit COMQUTOR-side retry wrapper found (per repo-wide sub-agent inventory).
- **Timeout**: `Week2LLMGateway` — yes, explicit wall-clock deadline via `ThreadPoolExecutor`, default 15s, bounded [1, 120]s (`call_with_timeout`, `week2_llm.py:55-65`). Native agents — **UNKNOWN/SDK-default**.
- **JSON repair / schema validation**: yes, strict, at every one of the three Week2 call sites (`_validate_llm_batch_enrichment`, the `alpha_classifier` inline validator, `_validated_llm_edges`) — none silently accept a malformed payload.
- **Safe default / error logs**: yes — every gateway failure is logged with a stable `error_code` to `error_logs/week2_llm_errors.jsonl`; adapter failures additionally log to `error_logs/structured_output_adapter_errors.jsonl` with secrets/local-path redaction (`_redact_secrets`).
- **Cache**: **NOT_IMPLEMENTED** anywhere in the LLM call path (repo-wide search, zero hits beyond an unrelated yfinance ticker-lookup `lru_cache`).
- **Prompt/model version, input/output hash, latency, token usage, cost**: **NOT_IMPLEMENTED** as first-class fields on any LLM call site. The Structure Output Contract prompt suffix is the one exception with a real deterministic hash (`compute_prompt_contract_sha256`, recorded per run).
- **Rate-limit handling, cancellation**: not found as dedicated mechanisms beyond the generic exception→retry→give-up chain above.
- Test fakes (`_FakeBatchLLMGateway`, `FakeClient`, `MagicMock`) exposing retry/cache-like attributes in `tests/` were **not** treated as evidence of a production capability — flagged explicitly per the "no unproven inference" rule.

## 18. Compliance Matrix

Full machine-readable matrix (plan_section / requirement / evidence / file / symbol / behavior / status / severity / source classification / recommended phase / notes): `docs/audit_artifacts/development_plan_compliance_matrix.csv`. Summary counts: 9 COMPLIANT, 4 DIVERGED (module scope's TradingAgents rule, §5.1 LLM-vs-deterministic inversion, §5.3 third edge source, replay LLM-tier reproducibility), 2 MISSING/NOT_IMPLEMENTED (20-labeled-claims evaluation, LLM response cache), 1 NOT_APPLICABLE (Evidence Stance, correctly excluded from Development-Plan scope).

## 19. Phase 1–3 Recommendations

Full detail (gap / files / reusable code / provider/prompt/schema/replay impact / backward compatibility / tests needed / cutover / blockers / explicit non-goals) for each phase: `docs/audit_artifacts/proposed_phase_1_3_plan.json`.

- **Phase 1 (Structured Output Adapter)**: implementation is already compliant; the real work is measuring LLM-enrichment quality before any default-on rollout decision, since the tier is currently off by default and its real-world accuracy is unmeasured.
- **Phase 2 (Hybrid Alpha Mapper)**: implementation is already compliant; the blocking gap is that John's 20 labeled claims and the ≥80% accuracy evaluation do not exist in this repository and must be sourced from the product owner.
- **Phase 3 (LLM Structure Extractor)**: implementation is already compliant; the recommended work is purely reporting/documentation — surfacing the already-tracked `llm_edge_count`/`deterministic_edge_count`/`canonical_relation_edge_count` split so the `CANONICAL_BLOCK` source's real contribution is visible, not silently folded into "the LLM extractor."
- **Proposed Addendum**: a product decision on whether `canonical_prompt_injection.py`'s runtime monkeypatch satisfies "output capture hooks only" (§13). Evidence Stance LLM-ification is explicitly and deliberately **not** proposed anywhere in this report, per instruction — it remains fully unscoped for any future request to address separately.

## 20. Unknowns and Required Product Decisions

- Whether `canonical_prompt_injection.py`'s prompt-content change at runtime is acceptable under "output capture hooks only," or requires either a design change or an explicit Development-Plan amendment (§13, §19).
- Real per-run/fleet-wide LLM call counts for all three Week2 tasks — `UNKNOWN_NOT_INSTRUMENTED`, not fabricated (§9).
- Whether any historical run in `outputs/runs/` actually had `COMQUTOR_WEEK2_LLM_ENABLED=true` — not enumerated in this audit (§16).
- Whether the 160 non-`xiangmao` commits touching `tradingagents/` are byte-identical to genuine upstream TradingAgents commits — best available internal signal only (zero "comqutor" string hits in their diffs); a true diff against `upstream/main` requires network access this offline audit did not use (§13).
- Location/existence of John's 20 labeled Alpha-Mapper claims and any historical ≥80%-accuracy evaluation run — not found in this repository (§11, §18).
- Whether `tradingagents/comqutor_outputs.py` (the dead 9-line shim) should be removed, given it appears to have zero importers anywhere in the repo (§13).

## 21. Tests and Commands

Targeted offline suite (Structured Output Adapter, Alpha Mapper, Week2 LLM gateway, Structure Extractor, Replay Identity, Evidence Stance classifier/integration, Evidence Review Sample, Artifact Export/API, Conflict Detector) and the full offline suite (`pytest -q -m "not integration"`) were both run — see the final terminal summary for exact pass/fail counts. `scripts/audit_llm_boundary.py` (new, read-only, not imported by any production module, zero network/DB/Provider calls) was run directly and reports `OVERALL: PASS` on all 4 structural invariants it re-derives mechanically. `ruff check` on the new script: clean.

## 22. Worktree/Source Integrity

Git baseline recorded at the start (branch `comqutor-structure-layer`, HEAD `b5837e80a4550fc35165d0013a8ef0f27ccb4c8f`) and re-verified at the end of this audit — see the final terminal summary. All pre-existing dirty-worktree modifications from prior sprints were preserved untouched; this audit's only new filesystem changes are `scripts/audit_llm_boundary.py` and the files under `docs/` (this report plus `docs/audit_artifacts/*`). No file under `outputs/runs/` was modified. No historical source artifact's sha256/size/mtime was touched (this audit never wrote to any existing run directory).

## 23. Outputs

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
