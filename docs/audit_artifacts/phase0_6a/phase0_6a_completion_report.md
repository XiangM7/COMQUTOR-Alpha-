# Phase 0.6A Completion Report

## Final gate

`PHASE_0_6A_OFFLINE_FOUNDATION: PASS`

The offline, unintegrated contract foundation is complete. No current production module imports it, and current live/replay behavior and semantic authority are unchanged.

## Task and repository

- Task: Phase 0.6A — Offline LLM Semantic Runtime Contract, Cache Primitives, and Exact-Replay Artifact Foundation
- Branch: `comqutor-structure-layer`
- HEAD: `b5837e80a4550fc35165d0013a8ef0f27ccb4c8f`
- Dirty worktree preserved: yes, 162/162 preexisting dirty/untracked files unchanged by size, SHA-256, and mtime
- Production runtime files changed by Phase 0.6A: 0
- TradingAgents files changed by Phase 0.6A: 0
- Week2 gateway changed: no
- Adapter/Mapper/Extractor changed: no
- Replay pipeline changed: no
- `outputs/runs` changed: no, 133/133 files match
- `outputs/replays` changed: no, 108/108 files match
- Staged files: 0
- Commit/push/reset/restore/clean/stash: no

Existing tracked changes shown by Git remain the user's preexisting work. Phase 0.6A added 32 files, all within the authorized paths; disallowed additions are zero.

## Specification

- Development Plan SHA unchanged: yes, `cabf3381aaa633b7b88035ab6df2d7dac0def3d5ddd337f6384f23f4c439a8d9`
- Phase 0 and Phase 0.5 specifications/audits unchanged: yes, 37/37 checked
- ADR-001 through ADR-004 unchanged: yes
- ADR-005: `ACCEPTED_FOR_OFFLINE_FOUNDATION`, `NOT_INTEGRATED`, `NO_PRODUCTION_AUTHORITY`
- Semantic call contract: `docs/specs/llm_semantic_call_contract_v1.md`
- Exact replay artifact contract: `docs/specs/exact_semantic_replay_artifact_contract_v1.md`

The documents preserve provenance labels: Development Plan statements remain `SOURCE_FROZEN`; future substrate rules are `APPROVED_PROJECT_DECISION`; current behavior is reported as `CURRENT_IMPLEMENTATION`. Later B1/B2/B3/B4/B5/J1/J2/J3 work was not implemented or attributed to the frozen plan.

## Runtime foundation

- Semantic call schema: `comqutor.semantic_call.v1`
- Cache entry schema: `comqutor.llm_cache_entry.v1`
- Cache-key schema: `comqutor.llm_cache_key.v1`
- Manifest schema: `comqutor.semantic_manifest.v1`
- Canonical JSON/hash: deterministic UTF-8, sorted keys, strict supported domain, SHA-256, non-finite values rejected
- Cache-key contract: versioned semantic identity; raw prompt/input and `run_id` excluded
- Null cache: network-free, permanent miss
- Redis adapter: injected client only; fake-client tests only; corrupt data raises explicit failure
- Real Redis connections: 0
- Recorder: validated append-only JSONL with lock, monotonic sequence, duplicate rejection, corruption detection, optional fsync
- Manifest: derived counts/hash/readiness, atomic same-directory replace, strict verification
- Production importer count: 0

## Behavior and integrity

- Live behavior changed: no
- Replay behavior changed: no
- Default LLM setting changed: no; explicit opt-in remains required
- Semantic authority changed: no
- Canonical prompt injection changed: no
- Protected runtime files: 7/7 unchanged by size, SHA-256, and mtime
- Source artifacts unchanged: yes
- Provider calls: 0
- Completed external connections: 0
- Database writes: 0
- Commit: no
- Push: no

## Verification results

- LLM runtime tests: 74 passed
- Related existing tests: 297 passed, 1 Provider smoke skipped because its explicit opt-in was not enabled
- LLM boundary audit: 4/4 PASS
- Phase 0.6A verifier: 20/20 PASS; `PHASE_0_6A_OFFLINE_FOUNDATION: PASS`
- Ruff: PASS
- Guarded full suite: `KNOWN_TEST_ISOLATION_GAP_ONLY`
- Full suite totals: 2663 passed, 5 known failed, 1 skipped, 47 deselected, 69 subtests passed
- New failures: 0

The five failures are exactly the Phase 0.5 baseline node IDs:

1. `tests/test_structured_agents.py::TestSentimentAnalystAgent::test_structured_path_produces_rendered_markdown`
2. `tests/test_structured_agents.py::TestSentimentAnalystAgent::test_sentiment_report_also_in_messages`
3. `tests/test_structured_agents.py::TestSentimentAnalystAgent::test_prompt_contains_ticker`
4. `tests/test_structured_agents.py::TestSentimentAnalystAgent::test_falls_back_to_freetext_when_structured_unavailable`
5. `tests/test_structured_agents.py::TestSentimentAnalystAgent::test_falls_back_to_freetext_when_structured_call_fails`

Each attempted the existing unmocked Stocktwits path. The fail-closed socket guard raised `PHASE_0_6A_NETWORK_BLOCKED` before connection completion.

The unchanged Phase 0.5 verifier has one expected forward-phase scope failure: its allowed-path rule admits only Phase 0.5 additions and therefore rejects the authorized Phase 0.6A runtime/tests/script paths. Its other 18 checks pass, including canonical Plan/manifest, ADRs, original hashes, preexisting worktree, outputs, prompt files, Week2 default, required outputs, references, branch, and HEAD. This verifier was not modified and its aggregate result is recorded as FAIL rather than being misreported.

## Outputs

- ADR: `docs/adr/ADR-005-llm-execution-substrate.md`
- Contracts: `docs/specs/llm_semantic_call_contract_v1.md`, `docs/specs/exact_semantic_replay_artifact_contract_v1.md`
- Runtime package: `comqutor_alpha/llm_runtime/`
- Tests: `tests/llm_runtime/`
- Verification: `scripts/verify_phase0_6a.py`
- Audit evidence: `docs/audit_artifacts/phase0_6a/`

## Next allowed phase

Phase 0.6B may begin only after independent review and explicit approval. It was not started automatically.
