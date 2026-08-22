# Repository Cleanup v0.1.2

Branch `comqutor-structure-layer`. No commit, no push, at any point in either round. Note: mid-cleanup, HEAD moved from `8ecf6bfdf7fd8203e223b220be8ca244da92d1f1` to `c45424598e87a1f4187399236e62eddc6ecb1b39` ("test 0.1.6", author `xiangmao`) — an external commit made outside this conversation's tool calls, checkpointing the whole session's prior work. Not made by this cleanup; noted for transparency. Working tree was clean at that new HEAD before either round of deletions began.

---

## Round 1

Deleted:
- `main.py` (root) — raw upstream TradingAgents demo script; zero functional references anywhere (not a package entry point, not in Dockerfile/CI). One stale prose mention in `README.md:211`, corrected to remove the "You can run `main.py`" clause (minimal edit, code example below it left untouched since it's self-contained).
- `test.py` (root) — manual, ad hoc Yahoo Finance experiment script; zero references anywhere.
- 35 `__pycache__/` directories, `.pytest_cache/`, `.ruff_cache/`, 11 `.DS_Store` files — all `.gitignore`d, untracked, 100% regenerable cache/junk.

Full path lists are in `docs/audit_artifacts/repository_cleanup_v0.1.2_inventory.md`.

Pre-cleanup baseline (`.venv/bin/python3 -m pytest tests/ -q --no-header`): **8 failed, 3714 passed, 47 skipped**, 720.91s.
Post-cleanup: **7 failed, 3715 passed, 47 skipped**, 730.87s.

One pre-existing failure (`test_shadow_provider_smoke_cli.py::test_fully_authorized_run_with_fake_client_writes_complete_bundle`, which asserted no dot-prefixed leftover files existed under `outputs/evaluations/`) started passing as a side effect of deleting the `.DS_Store` files that were sitting in that directory — not an intentional fix, a byproduct of legitimate junk removal. **Zero new failures.**

---

## Round 2

Policy change (per explicit instruction): a **SOFT HISTORICAL REFERENCE** (filename mentioned in an old report, historical JSON provenance field, successor-script docstring lineage note) no longer blocks deletion. Only a **HARD DEPENDENCY** (production import, test import/invocation, CLI/CI/build invocation, dynamic load, required by current H5/v0.1.2 reproducibility) does.

### Methodology note (important correction made mid-audit)

The first reference-count pass (filename.py as a literal string) systematically **missed Python import statements**, since `from scripts.foo import x` never contains the substring `foo.py`. This was caught when `deterministic_echo_llm.py` — which looked like a zero-reference historical script — turned out to be imported by 7 current test files and `seed_w5_demo.py`. Every script was re-checked with a second, import-statement-aware pattern (`from scripts.X import`, `import scripts.X`, `scripts.X` in general) before any classification was finalized. A third pass checked for indirect/variable-mediated `subprocess.run(...)` invocations (`build_development_plan_llm_boundary_audit.py` → `audit_llm_boundary.py` was found this way). A fourth pass checked `.github/workflows/ci.yml` and Dockerfile/docker-compose for shell-level invocation.

### Audit table (63 previously-NEEDS_REVIEW scripts + 8 previously-KEEP-on-soft-reference scripts, 71 total re-examined)

`H` = hard dependency found in that column. `—` = none found. `S` = only historical/soft references exist there (does not block deletion).

| Script | Production | Tests | CLI/CI/Build | Current v0.1.2/H5 | Historical-only refs | Decision |
|---|---|---|---|---|---|---|
| audit_prompt_v1_root_cause.py | — | H (test_shadow_v2/v3_prompt_size.py import `build_v1_request`) | — | — | — | **KEEP_CURRENT** |
| audit_prompt_v2_comparison.py | — | H (same 2 tests import `build_v2_request`) | — | — | — | **KEEP_CURRENT** |
| build_phase1a_shadow_review_bundle.py | — | H (test_review_bundle_builder.py) | — | — | verify_phase1a.py (deleted) also imported it | **KEEP_CURRENT** |
| deterministic_echo_llm.py | — | H (7 test files: evidence_stance_integration, week3/4 sanity+conflict+persistence+golden_closure) | H (seed_w5_demo.py imports it) | — | — | **KEEP_CURRENT** |
| run_phase1_master.py | — | H (7+ test files incl. test_phase1_master_ledger.py, prompt_v2/v3/v4_migration, anthropic_routing, exact_replay_false_positive_recovery) | — | — | imported by 3 deleted canary scripts too | **KEEP_CURRENT** |
| run_phase1b1_provider_smoke.py | — | H (test_shadow_provider_smoke_cli.py via `importlib.import_module`) | — | — | — | **KEEP_CURRENT** |
| seed_w5_demo.py | H (imported by verify_w5_demo.py) | H (test_w5_demo_seed.py) | H (`.github/workflows/ci.yml:45`) | — | — | **KEEP_CURRENT** |
| w5_demo_fixtures.py | — | H (8 test files incl. evidence_stance_integration, evaluation_harness, agent_outputs_persistence, artifact_export_and_api, week3 sanity ×2, b3_entity_exposure, week4_golden_closure) | — | H (seed_w5_demo.py dynamic import) | — | **KEEP_CURRENT** |
| verify_w5_demo.py | — | — | H (invoked by run_w5_demo.sh and verify_clean_install.sh) | — | release_candidate_manifest.md lists it as current delivery tooling | **KEEP_CURRENT** |
| run_regression.py | — | — | — | H (explicit task instruction: current six-ticker regression tool; `outputs/regression/` 1.0G output referenced by `comqutor_alpha/regression/*`) | — | **KEEP_CURRENT** |
| smoke_structured_output.py | referenced in `llm_call_site_inventory.json`/`development_plan_llm_boundary_audit_consolidated.md` (audit inventories, not imports) | — | — | — | CHANGELOG.md documents it as a current diagnostic | **KEEP_CURRENT** |
| healthcheck.sh | — | — | — | — | active, current ops script (checks `/health`,`/ready`, run/graph/conflict APIs, frontend build); references demo_offline.sh/seed_w5_demo.py | **KEEP_CURRENT** |
| verify_clean_install.sh | — | — | — | — | invokes seed_w5_demo.py + verify_w5_demo.py directly | **KEEP_CURRENT** |
| run_w5_demo.sh | — | — | — | — | invokes seed_w5_demo.py + verify_w5_demo.py; invoked by record_w6_demo.sh | **KEEP_CURRENT** |
| demo_offline.sh | — | — | — | — | actively documented in current README_DEV.md ("Offline demo" + troubleshooting section) | **KEEP_CURRENT** |
| record_w6_demo.sh | — | — | — | — | invokes run_w5_demo.sh + w6_demo_recorder.mjs; listed as current delivery tooling in release_candidate_manifest.md | **KEEP_CURRENT** |
| w6_demo_recorder.mjs | — | — | — | — | invoked by record_w6_demo.sh; listed in release_candidate_manifest.md | **KEEP_CURRENT** |
| build_neutral_unclassified_audit.py | — | — | — | H (generates Item 5 QA evidence, part of current Item 1-6 QA structure, not superseded by anything) | usage example in neutral_unclassified_audit_msft_07ddc074.md | **KEEP_CURRENT** |
| build_item2_blind_holdout_100.py, build_item2_blind_holdout_summary.py, run_item2_blind_holdout_alpha_mapper.py, run_item2_blind_holdout_b1.py, run_item2_blind_holdout_independent_review.py (H1) | — | — | — | — | S (H2 script docstring: "Methodology mirrors...(Holdout #1)") | **DELETE_OBSOLETE** |
| build_item2_blind_holdout2.py, build_item2_blind_holdout2_summary.py, run_item2_blind_holdout2_alpha_mapper.py, run_item2_blind_holdout2_alpha_review.py, run_item2_blind_holdout2_stance_review.py, run_item2_blind_holdout2_b1.py (H2) | — | — | — | — | S (historical H2 report methodology table; JSON provenance field `existing_b1_contract_reused_from` in item2_h4_reviewer_v2_dev_freeze.json; docstring lineage notes in H4/H5 scripts) | **DELETE_OBSOLETE** |
| build_item2_blind_holdout3.py, build_item2_blind_holdout3_summary.py, run_item2_blind_holdout3_alpha_review.py, run_item2_blind_holdout3_system_alpha.py, build_item2_holdout3_pure_llm_dev_summary.py, run_item2_holdout3_pure_llm_dev_system_alpha.py (H3) | — | — | — | — | S (H4 script docstring lineage note) | **DELETE_OBSOLETE** |
| build_item2_blind_holdout4.py, build_item2_blind_holdout4_inventory.py, build_item2_blind_holdout4_summary.py, run_item2_blind_holdout4_alpha_review.py, run_item2_blind_holdout4_system_alpha.py (H4 original) | — | — | — | — | S (sibling-script docstring cross-references, JSON provenance in freeze_manifest_sampling.json) | **DELETE_OBSOLETE** |
| audit_llm_boundary.py | — | — | — | — | S (29 refs, all historical: Phase 0 boundary-audit docs/artifacts); subprocess-invoked only by build_development_plan_llm_boundary_audit.py, which is itself unreferenced anywhere | **DELETE_OBSOLETE** |
| build_development_plan_llm_boundary_audit.py | — | — | — | — | S (one-time Phase 0 audit generator; not imported/invoked by anything) | **DELETE_OBSOLETE** |
| build_item2_holdout1_root_cause_analysis.py | — | — | — | — | S (item2_holdout1_root_cause_report.md cites its internal `POLARITY_JUDGMENTS`/`ALPHA_JUDGMENTS` — provenance only) | **DELETE_OBSOLETE** |
| build_item2_mismatch_root_cause_analysis.py | — | — | — | — | S (self-referential provenance in its own generated JSON/MD) | **DELETE_OBSOLETE** |
| run_b1_llm_stance_50_validation.py | — | — | — | — | S (completed b1_llm_evidence_stance_upgrade_report; sibling-script docstring mentions) | **DELETE_OBSOLETE** |
| run_b1_llm_stance_failed30_rerun.py | — | — | — | — | S (b1_shared_json_parser_fix_report, a completed-fix record) | **DELETE_OBSOLETE** |
| run_b1_mixed_language_50_regression.py, build_b1_mixed_language_regression_artifacts.py | — | — | — | — | S (docstring cross-reference to run_b1_llm_stance_50_validation.py) | **DELETE_OBSOLETE** |
| run_evidence_review_llm_provisional.py | — | — | — | — | S (docstring mentions run_b1_llm_stance_50_validation.py's pattern) | **DELETE_OBSOLETE** |
| export_evidence_review_sample.py | — | — | — | — | 0 references of any kind beyond its own docstring | **DELETE_OBSOLETE** |
| export_j3_llm_review_packet.py | — | — | — | — | 0 references beyond its own docstring (underlying module `comqutor_alpha/evaluation/j3_review_packet_export.py` is separately live/tested and untouched) | **DELETE_OBSOLETE** |
| verify_phase0_5_spec_freeze.py, verify_phase0_6a.py, verify_phase0_6b.py, verify_phase0_6c.py | — | — | — | — | S (completed migration/spec-freeze checks; not imported/invoked by anything) | **DELETE_OBSOLETE** |
| run_phase1_v4_1_final_recanary.py, run_phase1_v4_2_final_live_canary.py, run_phase1_v4_live_shadow_canary.py, verify_phase1_v4_live_shadow_canary.py, verify_phase1_v4_live_shadow_canary_repair.py, verify_phase1_v4_duplicate_quote_hardening.py | — | — | — | — | S (one-off v4 canary/migration cluster; they import each other and `run_phase1_master.py`, but nothing outside the cluster imports any of them, and `run_phase1_master.py` itself is kept independently for its own test coverage) | **DELETE_OBSOLETE** |
| verify_phase1_master.py, verify_phase1a.py, verify_phase1b1.py | — | — | — | — | S (one-off verification runners; import currently-live modules like build_phase1a_shadow_review_bundle.py for convenience, but nothing imports these verify_* scripts themselves) | **DELETE_OBSOLETE** |
| diagnose_phase1_v4_1_location_root_cause.py, replay_v4_2_against_real_v4_1_evidence.py | — | — | — | — | S (historical phase1_master/*.md analysis docs) | **DELETE_OBSOLETE** |
| build_phase1_human_review_packet.py, build_phase1_human_review_packet_v3.py, build_phase1_human_review_packet_v4.py, build_phase1_v4_risk_based_review.py | — | — | — | — | 0 references (the real, tested "human review packet" logic lives in `comqutor_alpha/evaluation/phase1_human_review_packet.py`, a separate production module, untouched) | **DELETE_OBSOLETE** |
| build_artifact_bundle_manifest.py | — | — | — | — | 0 references beyond its own docstring (its output `artifact_bundle_manifest.json/.md`, dated 2026-08-19, stays as historical audit content) | **DELETE_OBSOLETE** |

**53 DELETE_OBSOLETE, 18 KEEP_CURRENT.** (63 original NEEDS_REVIEW scripts split 45/18; the 8 previously-Round-1-KEEP-on-soft-reference-only scripts — H1's five, H2's two B1/stance scripts, and the H1 root-cause script — all reclassify to DELETE_OBSOLETE under the corrected policy, landing in the 45+8=53 total.)

### Output directory audit (Section 14)

| Directory | Size | Referenced by current code? | Verdict |
|---|---|---|---|
| `outputs/review_sample_replays/` | 108M | Yes — `tests/test_j3_review_packet_export.py` reads it directly | KEEP (unchanged from Round 1) |
| `outputs/regression/` | 1.0G | Yes — `scripts/run_regression.py`, `comqutor_alpha/regression/*`; holds `regression_report.json` for the current six-ticker regression | KEEP |
| `outputs/replays/` | 102M | Yes — `comqutor_alpha/replay/pipeline.py` (production), documented in README_DEV.md as the harness's own replay output | KEEP |
| `outputs/canaries/` | 54M | Yes — `comqutor_alpha/llm_runtime/manifest.py`/`recorder.py` (production), `tests/llm_runtime/test_recorder.py` | KEEP |
| `outputs/evaluations/` | 42M | Yes — `comqutor_alpha/api/main.py` (production), multiple current tests write here | KEEP |
| `outputs/runs/` | 160M | Yes — the six-ticker regression + H5 source pool | KEEP |

**0 further output-directory deletion candidates found** — every large output directory besides the already-handled `review_sample_replays/` is directly read or written by current production code, not just historically generated. Reported honestly as a null result, not forced.

### Post-deletion reference validation (Section 16)

For all 53 deleted scripts: 0 production imports, 0 test imports/invocations, 0 CLI/CI/build invocations, 0 H5/current-v0.1.2 invocations remain — verified via (a) import-statement-pattern grep across `comqutor_alpha/`, `tests/`, remaining `scripts/`, `cli/`, (b) `.github/workflows/ci.yml` scan. Historical prose/provenance references (as expected and permitted) remain untouched in `docs/audit_artifacts/*.md`/`*.json` — those files still say things like "generated by scripts/build_item2_blind_holdout2.py" even though that script no longer exists in HEAD. This is intentional and matches Section 13: historical reports are not rewritten to hide retired generators.

### Tests (Round 2)

`.venv/bin/python3 -m compileall -q comqutor_alpha cli tradingagents scripts tests` → exit 0.
Direct import check of every production module + every one of the 18 kept scripts → all OK.
Full offline suite pre/post comparison recorded in the Final Response below.

### Size impact

Round 2: 53 files removed, 16,263 lines, ~704 KB of script source.
Round 1: 2 root scripts (~1.2 KB) + cache/junk (`.pytest_cache` 432K, `.ruff_cache` 112K, 35 `__pycache__` dirs, 11 `.DS_Store` files — all regenerable, not counted as "real" repository content).

---

## Retained Hard Dependencies

The 18 KEEP_CURRENT scripts above, plus everything already protected in Round 1 (current Alpha Mapper, week2_llm.py, taxonomy, evidence_stance.py/evidence_stance_llm.py, B2, B4, llm_runtime, replay, API/server, TradingAgents runner, all Structured Output Shadow v1–v4.2 files, `outputs/review_sample_replays/`, all current v0.1.2/H4-dev-review/H5 scripts, `docs/audit_artifacts/` in full).

## Historical References Left Intact

`docs/audit_artifacts/*.md` and `*.json` files continue to name scripts that no longer exist in `HEAD` (e.g. `item2_blind_holdout2_report.md` still says "Phase 2 — `build_item2_blind_holdout2.py`"; `item2_h4_reviewer_v2_dev_freeze.json` still says `existing_b1_contract_reused_from: "scripts/run_item2_blind_holdout2_stance_review.py..."`). This is intentional per the task's own policy: a historical report is allowed to say "generated by scripts/foo.py" even after `foo.py` is retired — that is accurate provenance, not a broken reference, and none of these reports were rewritten.

## Needs Review

None remaining that were deleted or force-classified. All 71 re-examined scripts resolved to either KEEP_CURRENT (hard dependency proven) or DELETE_OBSOLETE (proven no hard dependency of any kind, including a 4-pass check: filename-string, Python-import-statement, subprocess/variable-mediated, and CI/shell invocation).

## Verification

- Production imports: all current modules import cleanly (`comqutor_alpha.*`, `cli.main`, `tradingagents.*`) after both rounds.
- All 18 kept scripts import cleanly.
- `python -m compileall` across `comqutor_alpha`, `cli`, `tradingagents`, `scripts`, `tests`: 0 errors.
- Offline suite: see Final Response for the exact pre/post numbers across all three checkpoints (pre-cleanup, post-Round-1, post-Round-2).
- Provider calls: 0 throughout.
- Current QA artifact integrity (existence only, not recomputed): six-ticker regression run directories present; `evidence_review_summary.json` present with `v0.1.2_qa_summary` intact (Alpha 166/200=83.00%, Polarity 52/62=83.87%); H5 artifacts present; `item6_a2_artifact_completeness.json` present (54/54); `neutral_unclassified_audit_msft_07ddc074.json` present (699/699). Two honest gaps found (not caused by this cleanup — pre-existing absence): no file named `COMQUTOR_Alpha_v0.1.2_QA_Closure_Report.md` exists anywhere in the repository, and only 3 of a presumed 6 `v0.1.2_item*_screenshot.md` files exist (Items 2, 4, 6 — no Item 1/3/5 screenshot file was ever created under that naming convention).

## Git State

- Branch: `comqutor-structure-layer`
- HEAD: `c45424598e87a1f4187399236e62eddc6ecb1b39` (unchanged by this cleanup; moved once, externally, before Round 2 began)
- Deleted files (working tree, uncommitted): `main.py`, `test.py`, 53 scripts (listed in Final Response), 35 `__pycache__` dirs, `.pytest_cache/`, `.ruff_cache/`, 11 `.DS_Store` files
- Modified files: `README.md` (one-line stale-instruction removal)
- No commit. No push.
