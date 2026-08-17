# Phase 1 Master Execution Contract v1

Status: `APPROVED_PROJECT_DECISION` for staged execution under a single resumable state machine; `HUMAN_REVIEW_REQUIRED_BEFORE_CUTOVER`; `NO_PRODUCTION_AUTHORITY_UNTIL_STAGE_G`.

## Product-owner routing amendment (same Phase 1 Master)

The `structured_claim_shadow` evaluation task is fixed to registered profile
`comqutor_anthropic_medium_sonnet46_v1` (`anthropic` / `claude-sonnet-4-6`).
Its execution policy is `timeout_seconds=180`, `max_retries=1`; the single
retry is permitted only for timeout, HTTP 429, HTTP 5xx, or an explicitly
classified transient Provider transport error. Malformed JSON, deterministic
schema/provenance/identity rejection, abstention, valid-empty output, and poor
semantic quality are terminal and are never retried. The three existing
Week2 semantic tasks and the live/default research profile remain on their
existing DeepSeek configuration with unchanged prompt, timeout, retry, cache
identity, and semantic authority.

The prior DeepSeek blocker is classified as
`BLOCKED_PROVIDER_MODEL_UNSUITABLE_FOR_LONG_STRUCTURED_TASK`. Exact Replay was
a downstream consequence of absent accepted output, not the root defect.
DeepSeek artifacts remain immutable. A new Anthropic qualification and
evaluation namespace is additive. The global actual-usage ledger is
`docs/audit_artifacts/phase1_master/phase1_global_provider_call_ledger.jsonl`;
it includes Master-budget calls and out-of-state-machine diagnostics without
resetting the original Master budget ledger.

The corrected replay gate is per report: accepted, valid-empty, and abstained
outputs must reproduce; deterministic rejections reproduce their rejection;
Provider error/timeout records remain auditable but are never presented as an
accepted replay. A stage manifest may therefore be not-ready while every
accepted report still passes its mandatory Provider-zero replay.

## Purpose

Define the single Master Task that carries Phase 1 from its current state (Legacy Adapter is sole production authority; one real-Provider smoke attempted with 100% Provider timeout) through to a conditional Production Cutover of the new Structured Output Adapter, or to an honestly-reported `BLOCKED`/`FAIL` stop. This contract is the authoritative definition `scripts/run_phase1_master.py` and `scripts/verify_phase1_master.py` implement; ADR-010 records the governing decisions.

## Source basis

- Development Plan v1.0 §5.1 (`SOURCE_FROZEN`).
- `docs/specs/semantic_authority_matrix.csv` row "claim extraction" (target production authority, cutover gate).
- `docs/specs/future_semantic_phase_contract.md` Phase 1 (explicit non-goals, cutover blocker).
- ADR-001, ADR-003, ADR-006, ADR-007, ADR-008, ADR-009, ADR-010.

## State machine

States (exactly these; no ad-hoc sub-states): `PROVIDER_DIAGNOSTIC`, `PROVIDER_PROBE`, `ANTHROPIC_QUALIFICATION`, `SMOKE`, `PILOT`, `CORE_EVALUATION`, `WAITING_FOR_HUMAN_REVIEW`, `QUALITY_GATE`, `PROMPT_V2_REVISION`, `LIVE_SHADOW_INTEGRATION`, `LIVE_SHADOW_CANARY`, `PRODUCTION_CUTOVER`, `COMPLETE`, `BLOCKED`, `FAIL`.

State file: `docs/audit_artifacts/phase1_master/phase1_master_state.json`, updated atomically (write-staging-file then `os.rename`) after every transition. Contains: `current_state`, `cumulative_logical_calls`, `cumulative_provider_attempts`, `prompt_version_in_use`, `already_called_report_ids`, `bundle_directories`, `input_output_hashes`, `next_action`, `history` (append-only list of every transition with timestamp).

Entry point: `python scripts/run_phase1_master.py --resume` (and `--resume --human-review-csv <path>` after `WAITING_FOR_HUMAN_REVIEW`). No other invocation form starts or advances the Master Task.

## Call budget (hard cap, independent of and additive to Week2LLMGateway's own unmodified retry policy)

- Connectivity probe: 1 logical call, retry=0.
- Expected evaluation calls: up to 24 unique historical reports (v1) + 4 live-shadow canary calls = 28.
- Normal expected total: 29 logical calls.
- One optional full v2 re-run of the same 24 reports: +24.
- **Hard cap: 53 logical calls. Provider-attempt hard cap: 105** (`1*(1+0) + 28*(1+1) + 24*(1+1) = 1 + 56 + 48 = 105`).
- Reaching either cap halts all further Provider calls immediately: `FAIL_PHASE1_PROVIDER_CALL_LIMIT_EXCEEDED`. The cumulative counters are never reset, including calls made during interrupted/voided shell-level attempts (per Phase 1B.1 precedent) -- they are recorded in `provider_call_ledger.json` permanently.
- Deleting an evaluation output directory does not restore budget.

## Stage A — Provider connectivity recovery

1. `PROVIDER_DIAGNOSTIC`: zero-completion-token diagnostics only -- profile backend URL format validation, sanitized hostname logging (never full URL with credentials), DNS lookup, TCP 443 connect, TLS handshake, request-URL construction sanity, Provider SDK base-URL resolution, and which of connect-timeout vs read-timeout the prior all-timeout smoke actually hit. Never prints API key, Authorization header, full environment, or Provider client repr. May fix a project-local misconfiguration (e.g. a wrong `backend_url` field in `research_profiles.py`); must not modify global machine network settings, firewall, or `Week2LLMGateway`'s timeout/retry policy. If a fix requires a system-level action outside the repository, stop with `BLOCKED_PROVIDER_NETWORK_ENVIRONMENT` and list the single explicit action needed -- never call historical reports.
2. `PROVIDER_PROBE` (only after DNS/TCP/TLS all pass): exactly 1 logical call, retry=0, minimal fixed-shortest JSON test content (no historical report, no Shadow prompt), verifying only that the Provider returns *a* response -- not evaluating semantic quality. Probe failure: `BLOCKED_PROVIDER_CONNECTIVITY`, no historical calls. Probe success: auto-advance to `SMOKE`.

## Stage B/C/D — Historical corpus evaluation

Selection reuses `docs/audit_artifacts/phase1a/evaluation_corpus_inventory.json`'s frozen `coverage[*].selected_agent_output_id` exclusively across all three stages -- never re-picked, never re-called once successfully attempted under the active Prompt version.

| Stage | Tickers | Reports |
|---|---|---|
| `SMOKE` | NVDA | 4 (1 per family) |
| `PILOT` | NVDA, QQQ, MSFT | 12 total (8 new) |
| `CORE_EVALUATION` | NVDA, QQQ, MSFT, SNDK, TSM, AMD | 24 total (12 new) |

Smoke engineering gate (must pass to auto-advance to Pilot): >=3/4 calls receive *a* Provider response; every result has an explicit status; malformed JSON safely rejected; accepted-Claim provenance and source-span validity both 100%; identity-mismatch-admitted=0; invented-evidence-admitted=0; Prompt hash unchanged; call budget not exceeded; Exact Shadow Replay verifiable for every accepted output. All 4 timing out again -> `BLOCKED_PROVIDER_CONNECTIVITY` (do not retry beyond the Gateway's own bounded policy). Responses received but all safely rejected -> continue to Pilot, tagged `SMOKE_OUTPUT_ADMISSION_RATE_ZERO`; never re-run Smoke because a result is unwelcome.

Pilot produces `phase1_pilot_results.json`, `phase1_pilot_review.csv`, `phase1_pilot_diagnostics.json` (parse rate, admission rate, abstention rate, rejection-reason distribution, source-span/provenance validity, identity/schema errors, per-family and per-report-length deltas, Exact Replay completeness) -- diagnostic signals only, never a substitute for human semantic judgment. Auto-advances to Core Evaluation unless a safety failure occurs (invented evidence admitted, invalid source span admitted, identity mismatch admitted, Prompt drift, secret persistence, budget exceeded).

Core Evaluation writes the unified bundle to `outputs/evaluations/phase1-master-<id>/` (never `outputs/runs/` or `outputs/replays/`): `evaluation_metadata.json`, `provider_usage_summary.json`, `llm_semantic_calls.jsonl`, `llm_semantic_manifest.json`, `artifact_manifest.json`, `reports/<ticker>/<family>/{source_report_snapshot,candidate_segments,provider_candidate,shadow_bundle,validation_report,legacy_claims_snapshot,legacy_vs_shadow_comparison,exact_replay_audit}.json`, `phase1_human_review.csv`, `phase1_human_review_instructions.md`, `phase1_automatic_diagnostics.json`. Each of the 24 reports is called at most once per Prompt version.

## Human review checkpoint (the sole external pause)

After Core Evaluation completes: state -> `WAITING_FOR_HUMAN_REVIEW`, all Provider calls stop. This agent never auto-fills human labels, never uses Provider/Codex self-evaluation as a substitute, never auto-advances to Live Shadow or Cutover from this state. Resume: `python scripts/run_phase1_master.py --resume --human-review-csv <completed-csv>`. CSV validation before acceptance: required fields complete, `reviewer` non-empty, labels drawn from the approved vocabulary, source-row identity unchanged, no rows deleted, no signature of Provider auto-fill.

## Phase 1 Quality Gate (`QUALITY_GATE`)

Safety gates (all must be exactly met): schema-valid admitted output=100%; source-span validity=100%; evidence provenance validity=100%; identity validity=100%; fabricated source_ref admitted=0; invented evidence admitted=0; negation-reversal critical errors=0; attribution-reversal critical errors=0; malformed JSON propagation=0; secret/hidden-reasoning persistence=0.

Human semantic gates (from the completed review CSV): disposition accept+accept_with_minor_edit >=85%; semantic fidelity correct >=90%; evidence pairing correct+partially_supported >=90%; Claim boundary correct >=85%; critical severity errors=0; major+critical errors <=5%.

Operational gates: overall rejection+abstention <=25%; no single Agent family's rejection+abstention >40%; Exact Replay success for every accepted output=100%.

Legacy comparison is diagnostic only, never a primary gate; the new parser is not required to approach Legacy's Claim count.

## Prompt v2 (at most once)

Permitted only if v1 fails the Quality Gate. Preserves v1's directory and results untouched; derives changes only from named systematic errors in the completed human review; records every delta and its reason; generates a new SHA-256; does not modify the Shadow schema unless a real, un-expressible blocker is found; is not tuned to a single ticker or given company-specific rules; does not introduce Evidence Stance or B2. Re-runs the same 24 core reports (not a mixed v1/v2 result set); regenerates a unified human-review CSV; returns to `WAITING_FOR_HUMAN_REVIEW`. v2 failing the gate -> `BLOCKED_PHASE1_SEMANTIC_QUALITY`; no automatic v3.

## Stage E — Live Shadow Integration

Allowed: structured-output live orchestration wiring, run-local semantic session lifecycle, optional shadow sidecar artifacts, a feature/config mode, related tests/docs. Forbidden: TradingAgents Agent prompts, Alpha Mapper logic, Structure Extractor logic, Graph/Activation/Exposure/Conflict algorithms, canonical prompt injection, Evidence Stance, B2.

`COMQUTOR_STRUCTURED_ADAPTER_MODE` in `{legacy, shadow, primary}`, defaulting to `shadow` once wired. `shadow`: Legacy remains production authority; new Adapter runs in parallel, writes `structured_agent_outputs_shadow.json`, `structured_adapter_shadow_validation.json`, `structured_adapter_shadow_comparison.json`; downstream consumes only Legacy output; no existing production artifact changes until `PRODUCTION_CUTOVER`.

## Stage F — Four canary runs

4 Agent families, historical fixture or controlled research input, no extra market-data access, <=4 new logical calls, semantic runtime artifacts persisted, Exact Replay supported, production result still from Legacy. Verifies: Shadow never changes the production response; Shadow failure never affects the run; sidecars complete; no duplicate calls; 100% provenance; Provider-zero Exact Replay; latency/token/cost recorded; historical outputs unchanged. 4/4 pass -> auto-advance to `PRODUCTION_CUTOVER`.

## Stage G — Production Cutover

Requires ALL: Quality Gate passed; 24-slot human review passed; Canary 4/4 passed; Exact Replay passed for every accepted output; zero production-invariant change; zero critical safety error; zero new test regression.

`COMQUTOR_STRUCTURED_ADAPTER_MODE` default -> `primary`. Fail-soft: any Provider timeout/error or validation rejection falls back to the Legacy Adapter with an explicit, never-silent recorded fallback reason; the run never crashes. Persisted per run: selected authority, Prompt version/hash, provider/model, validation outcome, fallback status/reason, semantic calls/manifest. Legacy Adapter remains available for immediate config-only rollback.

## Exact Replay (primary-mode runs)

Reuses the existing ADR-007/Phase 0.6C contract unmodified: no Provider re-call, no re-interpretation of the Agent report, no re-generated Claim; only deterministic downstream stages (Graph/Activation/Exposure/Conflict) re-run; source semantic artifacts byte-identical; Provider/TradingAgents/market-data/DB calls=0. Runs that used Legacy fallback record that decision explicitly and are never presented as pure-LLM Exact Replay. Phase 0.6C fail-closed rules are never relaxed.

## Integrity

Never modified: Development Plan canonical source, ADR-001 through ADR-009 historical content, `outputs/runs/`, `outputs/replays/`, TradingAgents, Alpha Mapper semantic logic, Structure Extractor semantic logic, Graph/Activation/Exposure/Conflict algorithms, canonical prompt injection. Never: commit, push, reset, restore, clean, stash. Every state transition persists a worktree snapshot, protected-file hashes, cumulative Provider call/attempt counts, output artifact manifest, current gate, and next action.

## Final Gate

`PASS` requires: Provider connectivity confirmed working; all 24 core slots really evaluated; human review complete; Quality Gate passed; Live Shadow complete; 4/4 canaries passed; new Adapter is production authority; Legacy rollback available; Exact Replay passed; Mapper/Extractor/Graph business logic unchanged; historical artifacts unchanged; zero new test regressions; zero out-of-scope Provider/network/Redis/DB calls; no commit/push.

Final statuses on `PASS`: `PHASE_1_MASTER=PASS`, `SEMANTIC_QUALITY=VALIDATED`, `HUMAN_REVIEW=COMPLETE`, `PRODUCTION_AUTHORITY=STRUCTURED_OUTPUT_ADAPTER_LLM_PRIMARY`, `LEGACY_ROLLBACK=AVAILABLE`.

`BLOCKED` only for: unfixable Provider/network environment; waiting for human review; v2 still failing the semantic Quality Gate; external credential/system-permission problem.

`FAIL` for: exceeded call budget; accepted invalid provenance; production/history mutation; mixed Prompt versions; auto-generated human labels; new test regression; premature cutover before every gate passes.

Phase 2 is never started automatically by this contract.
