# Phase 1B.1 Provider Smoke Contract v1

Status: `APPROVED_PROJECT_DECISION` for one controlled real-Provider smoke; `NOT_LIVE_INTEGRATED`; `NO_PRODUCTION_AUTHORITY`; `SEMANTIC_QUALITY_UNPROVEN`.

## Purpose

Verify, with a real LLM Provider, that the frozen Phase 1A Shadow prompt and deterministic validator can be executed end-to-end -- Provider call, JSON parse, Shadow admission, persistence, Provider-zero exact replay, and blank human-review generation -- without asserting anything about semantic quality. This is a mechanical smoke test, not a quality gate.

## Source basis

- Development Plan v1.0 §5.1 (`SOURCE_FROZEN`): NL-to-Claim-schema conversion, malformed-JSON fail-soft, required Agent family coverage.
- ADR-008 (`SOURCE_FROZEN` for its own decisions): offline-only Shadow contract, deterministic validator as sole admission authority, human review determines quality.
- ADR-009 (`APPROVED_PROJECT_DECISION`): this phase's own scope and authorization rules, summarized below.

## 4-report selection algorithm

1. Read `docs/audit_artifacts/phase1a/evaluation_corpus_inventory.json`.
2. Iterate `target_tickers` in the fixed order `NVDA, QQQ, MSFT, SNDK, TSM, AMD`.
3. Select the first ticker where all four target Agent families (`fundamental`, `news`, `sentiment`, `technical`) have `slot_covered=true` and `target_slot=true` in `coverage`.
4. For each family, reuse `coverage[*].selected_agent_output_id` verbatim (Phase 1A's own deterministic per-slot selection) rather than re-deriving a second tie-break rule.
5. If no ticker has complete coverage, raise `PHASE1B1_NO_TICKER_WITH_COMPLETE_FAMILY_COVERAGE` before any Provider work begins.
6. The selection is recorded in `phase1b1_smoke_selection.json` before any Provider call and is never changed after the fact based on results.

## Provider opt-in

Real Provider calls require ALL of:

- `--execute-provider-smoke` CLI flag,
- `--research-profile <existing-profile-id>`, `--max-provider-calls <=4>`, `--output-dir <path under outputs/evaluations/>` all supplied,
- environment variable `COMQUTOR_PHASE1B1_PROVIDER_SMOKE_APPROVED` exactly equal to the string `"true"`.

Absence of any one input yields `BLOCKED_PROVIDER_SMOKE_NOT_AUTHORIZED` with zero Provider calls. Authorization is never inferred from `COMQUTOR_WEEK2_LLM_ENABLED`, from Provider credential presence, or from any other implicit signal.

## Profile selection

`--research-profile` resolves through `comqutor_alpha.research_profiles.get_research_profile`, the same fixed, versioned registry real web-submitted runs use. An unregistered id yields `BLOCKED_RESEARCH_PROFILE_INVALID`. No credential is read, logged, or persisted by this contract; only the profile's `provider`/`model` identity strings are recorded.

## Call/attempt limits

- Logical calls: exactly `min(--max-provider-calls, 4)`, one per selected report.
- Provider attempts: `logical_calls * (1 + Week2LLMGateway.DEFAULT_MAX_RETRIES)`, derived and printed/recorded before any call, never independently configured.
- `--max-provider-calls > 4` yields `FAIL_PROVIDER_CALL_LIMIT_EXCEEDED` before any Provider work.

## Prompt immutability

The Provider receives the byte-identical Phase 1A prompt (`STRUCTURED_OUTPUT_SHADOW_PROMPT`, version `structured_adapter.claim_extraction_shadow.v1`, SHA-256 `c60f1526fd927e4593ab5913bc3c653cd2a05f6d24dc5fdf3e258a3e62128d1e`) plus the dynamic per-report request JSON built by the unmodified `build_shadow_prompt_input`/`build_shadow_request`. Only the dynamic request fields (report text, identity metadata, candidate segments, factor vocabulary, source metadata) vary between calls; the fixed instruction text is never edited, and a hash drift blocks this phase (`PHASE1B1_BLOCKED_PROMPT_CHANGE_REQUIRED`) rather than silently continuing under the same version.

## Semantic task identity

`structured_claim_shadow` -- additive entry in `SEMANTIC_TASKS`; distinct cache key, distinct manifest task-count bucket; never aliases or shares identity with `structured_adapter`/`alpha_classifier`/`structure_extractor`.

## Validation flow

Real Provider JSON is validated by the exact same `validate_shadow_bundle` deterministic authority Phase 1A already uses (schema, identity, source-report hash, source-span exactness against the real report text, evidence provenance, factor/source-ref vocabulary bounded to caller-supplied values, direction/confidence/source-type enums, duplicate-claim rejection). A Gateway-level closure runs this same validator so the persisted `SemanticCallRecord.validation_status` reflects true Shadow-contract acceptance; `StructuredOutputShadowParser.parse_report_shadow` independently re-derives the final bundle/failure state from the same raw proposal, so no logic is duplicated or allowed to diverge.

## Persistence

One atomically promoted directory under `outputs/evaluations/phase1b1-smoke-<timestamp>-<id>/` containing `evaluation_metadata.json`, `phase1b1_smoke_selection.json`, `llm_semantic_calls.jsonl`, `llm_semantic_manifest.json`, `provider_usage_summary.json`, `reports/<family>/{source_report_snapshot,candidate_segments,shadow_bundle,validation_report,legacy_claims_snapshot,legacy_vs_shadow_comparison}.json`, `phase1b1_shadow_review.csv`, `phase1b1_shadow_review_instructions.md`, `shadow_exact_replay_audit.json`, and `artifact_manifest.json`. `outputs/runs/` and `outputs/replays/` are never written by this phase.

## Sensitive-data policy

`raw_output_text`/`raw_output_sha256` remain null per the existing `SemanticCallRecord` contract; no full Provider response text is persisted. `input_payload` (report text, identity, candidates) is persisted as the semantic call's own input, redacted for credential-like text and full local home paths by the existing `redact_sensitive_text`/session sanitization before it is ever hashed or written.

## Shadow replay

`structured_output_shadow_replay.verify_phase1b1_shadow_exact_replay` re-verifies one persisted bundle with zero Provider/Gateway/network/Redis/database calls: manifest and JSONL integrity, prompt version/hash stability, report-hash identity, validator reproducibility, stable Claim-ID reproducibility, and comparison-signal reproducibility. Any mismatch is a stable reason code, never a silent pass.

## Human review generation

`phase1b1_shadow_review.csv` is built with `build_blank_review_rows`/`render_blank_review_csv` (unchanged from Phase 1A) covering all four reports' accepted/rejected Shadow claims and Legacy claims. Every human-judgment column is blank; `human_labels_created=false` is recorded explicitly.

## PASS/BLOCKED/FAIL semantics

- **PASS**: exactly 4 reports selected across 4 families; logical calls `<=4`; Provider attempts within the derived cap; prompt version/hash unchanged; every result has an explicit accepted/rejected/abstained status; Shadow replay reports `PASS`; review bundle generated with empty labels; no production behavior or historical artifact changed; no new test failures.
- **BLOCKED**: authorization missing, research profile invalid, Provider credentials missing/unavailable, or output-directory isolation cannot be guaranteed. Zero Provider calls in every BLOCKED case.
- **FAIL**: prompt hash drift, call/attempt limit exceeded, an accepted Claim with invalid provenance, any production/historical artifact mutation, automated human labels, or an out-of-scope network/DB/Redis call.

## Non-goals

Does not integrate a live Shadow route; does not replace or modify the current Adapter, Alpha Mapper, Structure Extractor, Graph, Activation, Exposure, or Conflict; does not implement Evidence Stance, ticker specificity, or B2; does not change the Phase 1A prompt; does not run a 12-report Pilot or 24-report Evaluation.

## Requirements for Phase 1B.2

Independent review of this smoke's four-report artifacts and a completed (non-blank) human review CSV are prerequisites before any 12-report Pilot may be scoped. This document does not itself authorize Phase 1B.2.
