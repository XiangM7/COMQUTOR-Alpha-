# Entity Alpha Exposure Shadow Productization Report

Date: 2026-07-31  
Default production mode: `shadow`  
Seed approval status: `draft`  
Overall verdict: **PASS — enforced mode is ready but disabled**

## Verdict

| Area | Verdict | Evidence |
|---|---|---|
| Seed Import | PASS | All three supplied files imported byte-for-byte; manifest hashes validate; SNDK extension is present. |
| Exposure Calculation | PASS | The existing `exposure_engine.py` remains the only formula implementation; current evidence uses canonical unique Evidence Fact groups and agent confidence deduplicates by agent. |
| Shadow Pipeline Integration | PASS | Live and replay pipelines calculate Exposure after Activation inputs exist; score, level, dominant membership, and Conflict remain unchanged in shadow. |
| DB / Artifact / API | PASS | Migration `0006`, repository upsert/read APIs, run artifact, artifact manifest, run audit, Research response, and optional endpoint are implemented. |
| Frontend Transparency | PASS | AlphaCard shows components, seed version/status, mode, draft/shadow/not-applied labels, would-block flags, and missing-seed fallback. |
| Enforced Mode Readiness | READY_BUT_DISABLED | Synthetic approved fixtures validate qualification ceilings; the bundled draft manifest always downgrades enforced requests to shadow. |

## Pre-change audit

- Initial branch: `comqutor-structure-layer`.
- Initial audited HEAD: `139a83cc66f988ee1f770ba92cb58dccc39c321f`.
- The branch advanced externally during the sprint to `359fad4a0a3d668f8c3062b8ed8b014ebcd9066b`; this sprint did not commit, reset, clean, or push.
- The existing formula core was `calculate_exposure` and `compute_entity_alpha_exposures` in `comqutor_alpha/exposure_engine.py`.
- The existing formula was already exactly `0.50 × historical_mapping + 0.30 × current_evidence + 0.20 × agent_confidence`; it was preserved.
- Canonical Evidence Fact eligibility/grouping was already centralized in `select_supporting_alpha_claims` and `group_evidence_candidates`.
- The insertion point is `score_and_assemble_structure_graph`, immediately after Activation v2 has computed canonical evidence groups and before graph/artifact/DB persistence and Conflict.
- The repository uses SQLAlchemy Core and explicit idempotent migrations, so a new table and migration were required.

## Exact input import

| File | Repository destination | SHA256 |
|---|---|---|
| `entity_alpha_exposure_seed_v0.1.yaml` | `comqutor_alpha/config/entity_alpha_exposure_seed_v0.1.yaml` | `97cd4510f3cc3d54965d351880346cb46c032eabd84a52e9651d1ba0029e513f` |
| `entity_alpha_exposure_seed_review_v0.1.csv` | `docs/entity_alpha_exposure_seed_review_v0.1.csv` | `7df401f99911ac46d173b068ef4bfda47d082c165f71e896461499f44b63afc3` |
| `entity_alpha_exposure_methodology_v0.1.md` | `docs/entity_alpha_exposure_methodology_v0.1.md` | `d951082f6d57cec906424787668636b4e19b0465be5207283e8fdb2ee775b189` |

The generated manifest is `comqutor_alpha/config/entity_alpha_exposure_seed_manifest_v0.1.yaml`, with `approval_status: draft`, `approved_by: null`, and `enforcement_allowed: false`. No seed value was modified. The loader returns immutable-like mapping proxies, validates every hash/value/Alpha ID, and keeps missing entries as `None`.

Coverage is ten formal tickers (`NVDA`, `AMD`, `MSFT`, `GOOGL`, `AMZN`, `AVGO`, `TSM`, `SMCI`, `QQQ`, `SPY`) plus extension ticker `SNDK`.

## Runtime calculation

The implementation uses the same canonical groups already built for Activation v2; it does not regroup raw claims.

- `current_evidence = min(ticker_specific_unique_fact_count / 4, 1) × mean(ticker-specific representative match_score)`.
- No ticker-specific fact produces deterministic `current_evidence = 0.0`.
- Each unique fact has one deterministic match-score representative.
- Each agent contributes at most once to `agent_confidence`: its maximum legal confidence across unique-fact representatives.
- No legal distinct agent produces deterministic `agent_confidence = 0.0`.
- Missing seed produces `historical_mapping = null`, `final_exposure = null`, `exposure_status = missing_seed`, and `SEED_ENTRY_MISSING`; it is never coerced to zero.
- Strong-evidence override is observational only; `qualification_effect_applied` remains false in shadow.

## Mode and qualification safety

- `COMQUTOR_ENTITY_EXPOSURE_MODE=off|shadow|enforced`; default is `shadow`.
- `COMQUTOR_ALLOW_DRAFT_EXPOSURE_ENFORCEMENT=false` by default and cannot override the signed manifest gates.
- An enforced request requires both `approval_status: approved` and `enforcement_allowed: true`.
- The bundled draft seed downgrades enforced requests to shadow and records `SEED_NOT_APPROVED` and `ENFORCEMENT_NOT_ALLOWED`.
- Enforced mode never changes numeric `activation_score`; it only caps final status at `active` below 0.30 or `dominant` below 0.60.
- Exposure is not added to the Conflict formula. Conflict receives the final qualified Activation status only when a signed manifest enables enforced mode.

## Product surfaces

- Artifact: `entity_alpha_exposures.json`, schema `entity_alpha_exposure.run.v1`.
- DB: `entity_alpha_exposures`, unique `(run_id, alpha_id)`, migration `0006_create_entity_alpha_exposures`.
- Repository: idempotent upsert, read by run, read by run plus Alpha.
- Activation persistence whitelist preserves the additive `entity_exposure` object.
- Research response adds `entity_alpha_exposures` and `entity_alpha_exposure_status`.
- Endpoint: `GET /api/research/{run_id}/entity-exposures`; historical runs return `status: unavailable` and empty records instead of 500.
- AlphaCard labels the draft seed, shadow-only behavior, and not-applied qualification status.
- Run Audit adds seed identity, coverage, per-Alpha components/flags/reasons, and explicit score/level/Conflict no-change invariants.
- Architecture replay and replay-all use the same implementation and remain offline with zero Provider calls.
- Cross-run evaluation adds optional seed coverage, final-exposure distribution, would-block counts, and missing-seed ticker count. Golden expectations accept optional per-Alpha range/maximum specifications, but no unapproved case values were added.

## Frozen/source-run shadow acceptance

All values below came from isolated replays of the latest available source runs. The tuple is `historical / current / agent / final`.

| Ticker | Alpha | Historical | Current | Agent | Final | Block dominant | Block regime |
|---|---:|---:|---:|---:|---:|---|---|
| NVDA | A101 | 0.95 | 0.166275 | 0.637500 | 0.652383 | No | No |
| NVDA | A102 | 0.75 | 0.000000 | 0.400000 | 0.455000 | No | Yes |
| MSFT | A102 | 0.90 | 0.000000 | 0.000000 | 0.450000 | No | Yes |
| SNDK | A101 | 0.35 | 0.000000 | 0.000000 | 0.175000 | Yes | Yes |
| SNDK | A102 | 0.25 | 0.000000 | 0.000000 | 0.125000 | Yes | Yes |
| SNDK | A103 | 0.45 | 0.000000 | 0.000000 | 0.225000 | Yes | Yes |
| QQQ | A001 | 0.80 | 0.237975 | 0.400000 | 0.551393 | No | Yes |
| QQQ | A304 | 0.70 | 0.543225 | 0.464286 | 0.605825 | No | No |

SNDK A102 historical mapping was loaded from the supplied file as `0.25`; it is not hardcoded.

Replay lineage:

| Ticker | Source run | Isolated replay | Records | Provider calls | Source integrity |
|---|---|---|---:|---:|---|
| NVDA | `e434f80b-e4d0-4b09-9471-d84532659de5` | `entity-exposure-shadow-nvda-v01` | 10 | 0 | PASS (11/11 files unchanged) |
| MSFT | `0cb43bae-1a4d-4003-bb29-55d420498842` | `entity-exposure-shadow-msft-v01` | 10 | 0 | PASS (11/11 files unchanged) |
| SNDK | `183b04dd-aae3-4b33-bbb0-3c9bc3bc942f` | `entity-exposure-shadow-sndk-v01` | 10 | 0 | PASS (10/10 files unchanged) |
| QQQ | `a364e0ee-3bb4-4032-88b7-5cd82e379805` | `entity-exposure-shadow-qqq-v01` | 10 | 0 | PASS (11/11 files unchanged) |

Every replay reports `scores_unchanged=true`, `levels_unchanged=true`, `conflict_outcomes_before_equal_after=true`, `qualification_effect_applied_count=0`, and database writes `0`.

## Verification

- Dedicated Exposure productization tests: 21 passed.
- Targeted backend suite: 357 passed before the final explicit Conflict no-change test was added; that test and the complete dedicated file subsequently passed.
- Full offline backend: 2452 passed, 1 skipped, 47 deselected, 69 subtests passed. The single skip is the pre-existing optional Bedrock dependency (`langchain_aws`) and is unrelated to Exposure.
- Frontend: 152 passed.
- Frontend production build: PASS.
- Ruff on every task-modified Python file: PASS.
- Exact imported-file SHA validation: PASS.
- Final `git diff --check`: PASS.

## Audit artifacts

- `docs/audit_artifacts/entity_exposure_seed_validation.json`
- `docs/audit_artifacts/entity_exposure_nvda_shadow.csv`
- `docs/audit_artifacts/entity_exposure_sndk_shadow.csv`
- `docs/audit_artifacts/entity_exposure_activation_no_change.json`
- `docs/audit_artifacts/entity_exposure_db_roundtrip.json`

## Production behavior summary

- Mode: shadow by default.
- Extra LLM/Provider calls: 0.
- `tradingagents/` modified: no.
- TradingAgents prompts modified: no.
- Activation formula/weights/bands modified: no.
- Activation results changed in shadow: no.
- Conflict formula/registry/results changed in shadow: no.
- Factor taxonomy, aliases, relation vocabulary, or Graph admission modified: no.
- DB schema modified: yes, additive migration `0006` only.
- Historical source artifacts changed: no.
- Commit/push performed: no.
