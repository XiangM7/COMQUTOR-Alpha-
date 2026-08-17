# Exact Semantic Replay Integration Contract v1

Status: `APPROVED_PROJECT_DECISION`; `IMPLEMENTED_PHASE_0_6C`; `PROVIDER_ZERO`; `FAIL_CLOSED`.

## Replay modes

The versioned mode names are exactly:

- `EXACT_SEMANTIC_REPLAY`: reuse the source live run's saved validated semantic decisions and rerun deterministic downstream stages.
- `RAW_REBUILD_DIAGNOSTIC`: rerun the current parser and deterministic fallback from `raw_agent_outputs.json` for architecture diagnosis.

The modes have different semantic sources and are not interchangeable. `run_structure_replay` remains the backward-compatible Raw Rebuild entrypoint. `run_exact_semantic_replay` is the Exact entrypoint. An Exact failure never dispatches Raw Rebuild.

Every output identifies its `replay_mode`, `source_run_id`, replay identity, `semantic_source`, and `provider_zero=true`. The legacy CLI alias `structure-only` remains a compatibility dispatch to Raw Rebuild only; it is not accepted by the strict mode parser.

## Eligibility and source artifacts

Exact Replay reads one source run directory and requires the current canonical artifacts:

- `metadata.json`
- `raw_agent_outputs.json`
- `llm_semantic_calls.jsonl`
- `llm_semantic_manifest.json`
- `structured_agent_outputs.json`
- `alpha_matches.json`
- `extracted_structures.json`
- `structure_graph.json`
- `entity_alpha_exposures.json`
- `conflicts.json`
- `run_audit.json`
- `artifact_manifest.json`

The raw artifact is provenance and completeness evidence only. It is never passed to semantic parsing during Exact Replay.

Eligibility requires all files to exist as regular non-symlink files inside the source directory; supported JSON/schema/version identities; one consistent source run and ticker; a complete and exact-ready self-verifying manifest; an intact newline-terminated calls stream; valid canonical input/output hashes; supported task/prompt/schema/taxonomy identities; only accepted, saved, no-fallback results; no Provider timeout/error/budget exhaustion; valid source artifact-manifest hashes; and a unique binding for every call and saved semantic decision.

The loader snapshots every source file's relative path, byte length, SHA-256, and nanosecond mtime before reading and verifies the same snapshot after loading and before output promotion. It rejects lexical traversal, a symlink source directory, symlink files, or a resolved path outside the source directory. It never repairs, rewrites, normalizes, or updates source artifacts.

## Semantic binding algorithm

All records first verify exact `run_id`, task, `input_sha256`, `validated_output_sha256`, prompt version/hash, input/output schema version, and taxonomy version. The task-specific proof is then:

| Task | Required exact binding evidence |
|---|---|
| `structured_adapter` | agent, ticker, the full unique segment-ID set, claim/evidence/source section, validated factor set, direction, confidence, `source_agent_output_id`, and `claim_index`-derived artifact segment identity |
| `alpha_classifier` | unique exact claim/evidence/factors/direction composite, the complete ordered candidate identities and score components, allowed Alpha IDs, classifier-used marker, and exact select/defer artifact result |
| `structure_extractor` | unique claim ID and claim/evidence, allowed factors, and the complete multiset of saved LLM edge source/target/type/confidence identities |

`call_sequence` is integrity evidence, not a selection key. Task name, array position, occurrence order, substring matching, semantic similarity, and fuzzy text are prohibited matching mechanisms. Exact duplicate composites remain ambiguous.

The binding audit records total/accepted/by-task counts, bound call IDs, decision keys, orphans, missing decisions, ambiguities, input/output hash mismatches, decision mismatches, version mismatches, and a final `PASS` or `FAIL`. One call owning multiple artifact locations, or multiple calls owning one decision key, fails closed.

## Semantic authority, copy, and identity policy

`llm_semantic_calls.jsonl`, `llm_semantic_manifest.json`, `structured_agent_outputs.json`, `alpha_matches.json`, and `extracted_structures.json` are copied with `shutil.copyfile`, then compared byte-for-byte and by SHA-256. They keep source formatting, ordering, timestamps, and embedded source `run_id`. The bundle records source and copy hashes and `byte_identical` for each file.

The source run owns saved semantic artifacts. The replay run owns newly calculated downstream artifacts. Metadata states both identities. No third identity model is introduced.

Existing deterministic functions require replay-local execution identity. Exact Replay therefore builds deep-copied, in-memory context views that change only artifact-level `run_id` fields used by downstream assembly. Persisted semantic copies remain byte-identical, and content identities such as Claim IDs, evidence, factors, Alpha decisions, and extracted edges are not rewritten.

## Deterministic recalculation and comparison

After source and binding validation, Exact Replay may execute only:

1. Graph assembly and admission;
2. Activation;
3. Entity/Alpha Exposure;
4. Conflict detection; and
5. deterministic artifact serialization.

It uses the source run's saved semantic artifacts and the source analysis timestamp. It does not execute Adapter, Alpha Mapper, Structure Extractor, any semantic fallback, Gateway, Provider, TradingAgents, market-data, Redis, network, or database code.

`exact_replay_comparison.json` separately states that semantic inputs were reused exactly and compares source/replay Graph, Activation, Exposure, and Conflict. Normalization is limited to generated timestamps, explicit source/replay execution-owner IDs, and evidence-fact-group IDs mapped from their exact member Claim IDs. Scores, statuses, claims, evidence, matched Alphas, factors, edges, activation, conflicts, exposures, ticker, and explicit source/replay provenance remain visible. A future deterministic change is `DETERMINISTIC_ENGINE_DELTA`; it is not a semantic-input failure.

## Output and atomicity

The final Exact bundle contains:

- `metadata.json`
- the five byte-identical semantic authority copies
- `structure_graph.json`
- `entity_alpha_exposures.json`
- `alpha_activations.json`
- `evidence_facts.json`
- `conflicts.json`
- `summary.json`
- `exact_semantic_source_snapshot.json`
- `semantic_binding_audit.json`
- `exact_replay_comparison.json`
- `run_audit.json`
- `artifact_manifest.json`

The implementation creates a hidden, unique staging sibling, writes all files, validates required presence/identity/zero-call metadata and semantic byte identity, rechecks source integrity, and atomically renames the directory. Write, validation, or rename failure cleans staging and leaves no successful final directory. Existing final directories are never overwritten.

## Failure semantics

Stable Exact errors cover missing artifacts, invalid/not-ready manifest, corrupted calls, input/output/version mismatch, ambiguous/missing/orphan binding, run/ticker mismatch, invalid/hash-mismatched source artifacts, staging/output failures, attempted Provider/database work, and forbidden mode fallback. Errors expose stable codes and optional artifact basenames only; they do not include Provider bodies, secrets, authorization values, hidden reasoning, or full home paths.

Every eligibility or binding error occurs before Graph and Conflict work. No failure calls a Provider, writes a database, modifies the source, creates semantic sidecars, fabricates semantic calls, or falls back to Raw Rebuild.

## Provider-zero and side-effect guarantees

Production imports in the Exact path are limited to local file/integrity helpers, the saved-artifact binder, deterministic Graph/Activation/Exposure/Conflict functions, and deterministic exporters. There is no Adapter/Mapper/Extractor/Gateway/TradingAgents/Provider/market/Redis/database client call.

Offline tests make Provider factory, both Gateway invocation APIs, TradingAgents, Adapter/Mapper/Extractor builders, socket/HTTP, yfinance, database engine construction, and repository persistence fail immediately if reached. Eligible Exact Replay still completes and records zero Provider, TradingAgents, market-data, and database calls in both result and metadata.

## Historical runs and backward compatibility

A historical run with missing Phase 0.6B sidecars returns `EXACT_REPLAY_SEMANTIC_ARTIFACT_MISSING`. A run with `exact_replay_ready=false` returns `EXACT_REPLAY_SEMANTIC_NOT_READY`. Neither is upgraded, mutated, or reconstructed.

Raw Rebuild continues to read raw outputs and run its existing deterministic semantic fallback with `llm_gateway=None`. Its function signature, return type, core artifacts, Provider-zero behavior, and API consumers remain compatible. Additive result/metadata fields identify it as `RAW_REBUILD_DIAGNOSTIC` and `semantic_source=raw_rebuild`.

## Non-goals

Phase 0.6C does not modify live LLM behavior, enable LLM by default, change prompts or canonical prompt injection, change cache or semantic validators/authority, change Adapter/Mapper/Extractor semantics, change TradingAgents, implement Development Plan §5.1 Phase 1, implement Evidence Stance or ticker specificity, unblock B2, implement John's B1/B2/B3/B4/B5/J1/J2/J3 requirements, or change any Graph, Activation, Exposure, or Conflict algorithm.
