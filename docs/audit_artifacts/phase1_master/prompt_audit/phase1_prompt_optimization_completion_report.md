# Phase 1 Master — Prompt Root-Cause Audit and Safe Request Compression (completion report)

This is a fix within the current Phase 1 Master (`BLOCKED_ANTHROPIC_PROVIDER_RELIABILITY`), not a new phase. Provider calls made during the audit and implementation: **0**.

## What was asked

Find out why the real `structured_claim_shadow` Provider request grew from a 13,887-char report to a 98,529-char request, measure — not guess — the cause, and design a smaller but semantically-equivalent v2 request without weakening the canonical schema, the deterministic validator, or production boundaries.

## What was measured (zero Provider calls)

Using real production code (`build_candidate_segments` → `build_shadow_request` → `build_shadow_prompt_input`) against the exact, already-attempted frozen NVDA `fundamental_agent` Smoke report, the real v1 request is **98,633 chars** (the earlier ad-hoc diagnostic saw 98,529 chars for the same content under a different `run_id` string length — a match within rounding, not a new independent estimate).

Top 5 contributors (of 98,633 total):

1. `candidate_segment_id` — 163 candidates × the full 75-char `agent_output_id` re-embedded in each one — 22,331 chars (22.64%)
2. `evidence_hint` — byte-identical to `claim_hint` in **100% of 163 segments** — 17,993 chars (18.24%)
3. `claim_hint` — 163 cleaned report fragments — 17,504 chars (17.75%)
4. `agent_report` — the report itself, needed exactly once — 14,160 chars (14.36%)
5. `source_section` — 163 heading strings — 7,087 chars (7.19%)

`candidate_segments` as a whole is 80.33% of the request. Full breakdown, source map, and duplication findings: `v1_request_breakdown.json`, `v1_component_inventory.json`, `v1_prompt_source_map.json`, `v1_duplication_map.json`, `v1_root_cause_report.md`.

**ASSUMED_CAUSE_CONFIRMED** for the headline claim (candidate segments dominate; report-derived text is duplicated). **ASSUMED_CAUSE_REFINED** on the mechanism: the single largest bucket is ID/metadata verbosity, not text duplication — both had to be fixed. **ASSUMED_CAUSE_REJECTED** for the pre-listed alternative suspects: the fixed prompt does not triple-explain its schema (`duplicated_schema_chars=0`, measured), `factor_vocabulary` was already minimal (248 chars, id-only), and examples (842 chars) are not material at this scale.

A hard constraint discovered during measurement, not assumed in advance: only 21 of 163 candidates (12.9%) have a source span `_locate_exact_hint()` can actually verify against the raw report; the other 142 are cleaned paraphrases with no exact offset. v2 cannot replace all 163 hints with offsets — it sends offsets only for the 21 verified ones and relies on the model's own reading of the one full report copy for the rest, which is exactly what ADR-008 already designates candidate segments as (non-authoritative hints, not a required coverage mechanism).

## What v2 does

New, additive modules — nothing in `structured_output_shadow.py` / `structured_output_shadow_schema.py` / `structured_output_adapter.py` was modified:

- `comqutor_alpha/structure_engine/structured_output_shadow_prompt_v2.py` — frozen prompt `structured_adapter.claim_extraction_shadow.v2`, sha `c0d904dd...4fdea0` (frozen with the same drift-guard pattern as v1).
- `comqutor_alpha/structure_engine/structured_output_shadow_v2.py` — `build_shadow_request_v2`, `select_located_candidate_hints`, `normalize_v2_proposal_to_canonical_bundle`, `StructuredOutputShadowParserV2`.
- `structured_output_shadow_provider.py` — additive `Week2GatewaySemanticInvokerV2` / `run_real_provider_shadow_smoke_for_report_v2`.
- `scripts/run_phase1_master.py` — additive `_switch_structured_claim_shadow_to_prompt_v2` state migration, a new `BLOCKED_ANTHROPIC_PROVIDER_RELIABILITY` retry branch in `main()`'s loop, and `run_evaluation_batch` now branches on `state["prompt_version_in_use"]` to call the v1 or v2 real-Gateway path.
- `scripts/verify_phase1_master.py` — additive `check_prompt_v2_hash_frozen_and_consistent_with_state` (18/18 PASS).

The Provider is asked for exactly: `claims: [{claim, source_spans:[{start,end}], entities, factors, direction, confidence, candidate_ids?}]`, `abstentions: [...]`. Everything else — `exact_quote` (`report[start:end]`), `evidence` (bounded join of `exact_quote`s), `shadow_claim_id` (existing `generate_shadow_claim_id`, unchanged), identity fields, `shadow_only`/`production_authority` — is spliced in by `normalize_v2_proposal_to_canonical_bundle`, then validated by the **unchanged** `validate_shadow_bundle` against the **unchanged** `comqutor.structured_claim_shadow.v1` schema. Native structured output (`langchain-anthropic`'s `with_structured_output`, already a dependency and already used elsewhere in this codebase for exactly this fallback pattern) was confirmed available but deliberately not adopted this pass: the compact-JSON route already meets the size target without restructuring `Week2LLMGateway`'s shared text-response contract (used by the 3 existing production tasks); this is recorded as a deliberate, reversible scope decision, not a gap.

## Before / after (same frozen report, same real code path)

| | v1 | v2 | Δ |
|---|---:|---:|---:|
| Total chars | 98,633 | 18,874 | **-80.86%** |
| Total tokens (chars/4 estimate) | 24,658 | 4,718 | -80.86% |
| Report duplication ratio | 3.70 | 1.00 | target ≤1.05 met |
| Candidate text+metadata chars | 79,235 | 745 | |
| Schema instruction chars | 1,907 | 1,391 | |
| Factor vocabulary chars | 248 | 248 | unchanged (already minimal) |

Full diff, removed/retained/reconstructed component lists: `v1_vs_v2_prompt_comparison.json`.

## Proof nothing was silently lost

53 new, Provider-call-free tests (Fake Provider / virtual data only), all passing, none touching `validate_shadow_bundle`:

- `test_shadow_v2_semantic_equivalence.py` (16) — single claim, split, merge, negation, hypothetical→abstain, quoted attribution, temporal qualification, uncertainty, multi-span evidence, factor/direction/entity enforcement, claims outside any hint, candidate lineage resolution, identity never trusted from the Provider, full parser round trip.
- `test_shadow_v2_provenance_safety.py` (11) — `exact_quote` reconstruction (unicode/emoji/newline/punctuation), overlap-as-warning, non-int/negative/out-of-range/inverted/missing/malformed spans all **rejected, never repaired**.
- `test_shadow_v2_injection_safety.py` (7) — untrusted report text containing "ignore previous instructions" / a fabricated schema / a fake API key cannot mutate `schema_version`, identity, or authority flags; a deterministically-reconstructed credential-like evidence string still triggers the existing `SHADOW_SENSITIVE_CONTENT_REJECTED` filter.
- `test_shadow_v2_prompt_size.py` (5) — real v2 request ≤40K (regression-pinned), duplication ratio at target, deterministic construction, v1 baseline pinned against silent drift.
- `test_shadow_provider_invoker_v2.py` (5) + `test_phase1_master_prompt_v2_migration.py` (9) — the real-Gateway wiring and the state-machine BLOCKED→v2→SMOKE transition.

## Verification

- Targeted: `structured_output_shadow` full suite 187 passed; `llm_runtime`+`replay` 123 passed; Adapter/Mapper/Extractor 279 passed; Graph/Conflict 268 passed; API regression 163 passed.
- `python scripts/audit_llm_boundary.py`: 4/4 PASS (three-task Gateway chokepoint, zero deterministic-core LLM imports, live-route opt-in gate all unaffected).
- `python scripts/verify_phase1_master.py`: 18/18 PASS.
- `COMQUTOR_WEEK2_LLM_ENABLED=false pytest -q -m "not integration"`: **2903 passed, 1 skipped (pre-existing, unrelated missing optional `langchain_aws`), 0 failed.**
- `git status`: zero changes to `structured_output_adapter.py`, `alpha_mapper.py`, `structure_extractor.py`, Graph/Activation/Exposure/Conflict, or `tradingagents/` this session (pre-existing diffs in those files predate this work and were never touched). Production authority remains `LEGACY_ADAPTER`; v2 remains `SHADOW_ONLY`. HEAD unchanged; no commit.

## Result

`READY_TO_RESUME_PHASE1: YES`. Per task section 22, the Master was resumed directly (no new phase): the state machine switched from `BLOCKED_ANTHROPIC_PROVIDER_RELIABILITY` to `SMOKE` under prompt v2, voiding (not deleting) the 4 prior v1-prompted Anthropic Smoke attempts.

## Real resume outcome (two further real bugs found and fixed along the way)

The first real v2 Smoke attempt surfaced two genuine defects, neither a prompt-size problem, both fixed and disclosed before any further real spend:

1. **`FAIL_ACCEPTED_OUTPUT_EXACT_REPLAY` (false positive)** -- `structured_output_shadow_replay.py`'s exact-replay verifier hardcoded a single-element, v1-only prompt-identity allowlist, so it flagged the (correctly recorded) v2 prompt identity as drift. Fixed by recognizing both frozen (version, sha256) pairs (`KNOWN_PROMPT_VERSIONS`/`KNOWN_PROMPT_HASHES`) instead of only the first one that ever existed -- a detection-allowlist correction, not a leniency relaxation; a third, truly unknown prompt identity still fails closed.
2. **`WEEK2_LLM_INVALID_JSON` on 4/4 real reports** -- claude-sonnet-4-6 reliably wrapped its JSON response in a `` ```json `` markdown code fence despite the explicit "Do not return Markdown" instruction. Confirmed via two disclosed, isolated diagnostic calls (`v2_json_format_diagnostic_findings.json`): the content inside the fence was valid, semantically strong JSON (29 real claims + 1 sensible abstention on the frozen NVDA fundamental report). Fixed with `_MarkdownFenceStrippingModel`, scoped entirely to `structured_claim_shadow` gateway construction -- never touches `week2_llm.py`, never weakens `_strict_json_object`'s strict, fail-closed parsing for genuinely malformed content, adds zero new dependencies.

Both fixes were verified (18/18 `verify_phase1_master.py`, full `structured_output_shadow` suite) before any further real Provider call, and the recovery path re-verified the OLD failed artifacts read-only (confirming the exact-replay bug, not a data problem) before voiding them and making new real calls.

**With both fixes in place, the real retry succeeded completely.** Smoke (4 reports) → Pilot (+8) → Core Evaluation (+12) = 24/24 unique reports, all real Anthropic calls:

| Metric | Result |
|---|---:|
| Provider-completed response rate | 24/24 (100%) |
| Timeouts / transport errors | 0 / 0 |
| Accepted (validated) | 24/24 (100%) |
| Exact Replay | 24/24 `PASS` |
| Median / p95 latency | 47.2s / 67.2s (well under the 180s policy) |
| Cumulative budget used | 43/53 logical calls, 50/105 attempts |

`current_state: WAITING_FOR_HUMAN_REVIEW` -- the one allowed pause, reached automatically without further instruction, exactly as specified. Review CSV: `outputs/evaluations/phase1-master-anthropic-v2-20260807T193700Z-2e0f896b/phase1_human_review.csv` (314 blank rows, no auto-filled labels). `SEMANTIC_QUALITY` remains `UNPROVEN` -- 100% schema/provenance acceptance is not semantic correctness; that determination is exactly what human review is for. `PRODUCTION_AUTHORITY` remains `LEGACY_ADAPTER`. HEAD unchanged (`b5837e80a4550fc35165d0013a8ef0f27ccb4c8f`); no commit.
