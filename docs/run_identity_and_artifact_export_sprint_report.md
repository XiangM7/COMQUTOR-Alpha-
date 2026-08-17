# Sprint 1 -- Run Identity Integrity and Complete Artifact Export -- Report

Branch: `comqutor-structure-layer`. Starting HEAD (re-checked at sprint
start, per instruction, never assumed): `b5837e80a4550fc35165d0013a8ef0f27ccb4c8f`
("test 0.1.3" -- includes the Entity Alpha Exposure Shadow Productization
feature from the prior session, audited but not modified except where
noted below). No commit/push performed; HEAD unchanged throughout.

## Addendum: Replay Identity Correction (post-initial-delivery)

The initial delivery of this sprint fixed Architecture Replay's
`RUN_ID_MISMATCH` symptom by calling
`detect_alpha_conflicts(run_id=source_run_id, ...)`. **This was
explicitly acknowledged, on review, to be an identity bypass, not a
correct fix**: it silenced Conflict Detector's own defensive
`_embedded_identity_mismatch` guard by handing it the run_id the guard
was already satisfied by, rather than fixing the actual defect --
replay-local regenerated artifacts (`structured_agent_outputs.json`,
`alpha_matches.json`, etc.) incorrectly continued to carry the *source*
run's identity instead of the replay's own.

**The correct fix**, implemented in this addendum: a new
`_rebase_structured_payload_for_replay` helper deep-copies
`adapt_run_outputs`'s direct output and rewrites only the identity
fields (`run_id`) at the top level, in every `records[*]`, and in every
`canonical_relations[*]` -- to `resolved_replay_run_id`. Every downstream
builder (`build_alpha_matches_payload`, `build_extracted_structures_payload`,
`score_and_assemble_structure_graph`) already derives its own `run_id`
fields directly from the structured records it is given, so rebasing
once, before those builders run, makes every regenerated artifact
consistently carry the replay's own real identity -- and
`detect_alpha_conflicts(run_id=resolved_replay_run_id, ...)` (restored,
never `source_run_id`) now receives inputs whose embedded identity
genuinely matches, so `RUN_ID_MISMATCH` no longer fires because the
identity is *correct*, not because the check was routed around. A new
`build_replay_identity_consistency` validator (in
`comqutor_alpha.audit.ticker_consistency`, reusing that module rather
than duplicating logic) defensively re-confirms this contract on every
replay and fails fast -- before any file is written, `status` never
`"completed"`, `artifact_manifest.json` never created -- if it is ever
violated again. See the updated Executive Verdict below; this addendum
is why Sprint 1's overall verdict only became PASS after this
correction.

## Executive Verdict

| Track | Verdict |
| --- | --- |
| A1. Ticker Consistency Audit | **PASS** |
| A2. Complete Run Artifact Export (live runs) | **PASS** |
| A2. Replay Artifact Identity | **PASS** (corrected in this addendum -- see above; the original delivery's fix was an identity bypass, not a pass) |

**Overall Sprint 1: PASS** (all three gates pass; per the task's own
rule, overall Sprint 1 can only be PASS once Replay Artifact Identity is
PASS).

## Architecture: before / after

**Before:** `run_audit.json` had no ticker-consistency section at all.
Live-run artifacts stopped at `structure_graph.json` +
`entity_alpha_exposures.json`; Activation, Conflict, and Evidence Fact
data existed only embedded in `structure_graph.json` or the database --
never as their own standalone, downloadable files. "completed" status
depended only on Week 1-4 pipeline success, never on whether the run's
own ticker was internally consistent or its artifact set was complete.
Architecture Replay's own conflict detection was silently broken (see
below).

**After:** A single shared `comqutor_alpha/audit/ticker_consistency.py`
module is called from Run Audit (both live and replay) with the exact
same logic. A new `comqutor_alpha/api/artifact_export.py` module
extracts (never recomputes) `evidence_facts.json`, `alpha_activations.json`,
`conflicts.json`, and `summary.json` from already-computed
Activation/Conflict/Evidence-Fact payloads, and writes a persisted
`artifact_manifest.json` with per-artifact sha256/size/schema_version and
an overall `artifact_completeness` verdict. "completed" now additionally
requires `ticker_consistency != "fail"` and `artifact_completeness !=
"fail"` (an old run without these new artifacts is never retroactively
downgraded -- only an explicit, freshly-computed failure gates it). Two
new API routes expose this: `GET /api/research/{run_id}/artifacts`
(manifest) and `GET /api/research/{run_id}/artifacts/{artifact_name}`
(raw download, path-traversal-safe). Architecture Replay bundles are now
artifact-complete too (using a replay-specific required set that
excludes `raw_agent_outputs.json`, which a replay intentionally never
copies).

## Exact files/functions modified

**New:**
- `comqutor_alpha/audit/__init__.py`, `comqutor_alpha/audit/ticker_consistency.py`
- `comqutor_alpha/api/artifact_export.py`
- `tests/test_ticker_consistency_audit.py` (20 tests)
- `tests/test_artifact_export_and_api.py` (23 tests)
- `frontend/src/pages/StructureGraphPage.test.tsx` (4 tests)
- `docs/run_identity_and_artifact_export_sprint_report.md` (this file)
- `docs/audit_artifacts/ticker_consistency_summary.json`,
  `ticker_consistency_case_results.csv`, `sndk_tsm_forensic_report.json`,
  `artifact_completeness_summary.json`, `artifact_completeness_case_results.csv`,
  `frontend_run_switch_verification.json`
- (addendum) `tests/test_replay_identity_correction.py` (22 tests)
- (addendum) `docs/audit_artifacts/replay_identity_consistency.json`,
  `replay_identity_case_results.csv`

**Modified:**
- `comqutor_alpha/api/routes_research.py`: `build_run_audit_payload` now
  loads `evidence_facts.json`/`alpha_activations.json`/`summary.json`,
  calls `resolve_expected_ticker`/`audit_ticker_consistency`, and adds
  John's required top-level fields (`evidence_fact_count`,
  `graph_nodes`, `graph_edges`, `active_alpha_count`,
  `regime_alpha_count`, `ticker_consistency`, `inconsistencies`) plus a
  `ticker_consistency_audit` detail section. `_run_identity_section` now
  stringifies `created_at`/`started_at`/`completed_at` (see bug fix
  below). `_run_week3_graph_pipeline` now calls
  `finalize_completed_run_artifacts` and
  `build_and_write_artifact_manifest`, with real (logged, not silently
  swallowed) error handling for `run_audit_write`/`artifact_finalization`
  failures. `build_research_response`'s "completed" gate reads
  `run_audit.json`/`artifact_manifest.json` and additionally requires
  neither to have explicitly failed. Two new response-builder functions
  (`get_run_artifacts_response`, `get_run_artifact_file`) and two new
  routes.
- `comqutor_alpha/graph_engine/activation_scorer_v2.py`: `score_alpha_v2`
  gains a new, purely additive `evidence_fact_groups` field on its return
  dict -- a direct serialization of the SAME `_group_evidence` grouping
  result already computed for scoring (never a second grouping pass,
  never touching any score/weight/threshold/qualification logic). Exists
  so `evidence_facts.json` can be built by extraction only.
- `comqutor_alpha/replay/pipeline.py`: (1) **corrected** (this addendum)
  -- the original fix for the real, pre-existing `RUN_ID_MISMATCH` defect
  had called `detect_alpha_conflicts(run_id=source_run_id, ...)`, an
  identity *bypass* (see Addendum above); replaced with
  `_rebase_structured_payload_for_replay` (new helper: deep-copies
  `adapt_run_outputs`'s output, rewrites only `run_id` at the top level,
  per-`records[*]`, and per-`canonical_relations[*]`) plus the restored,
  correct `detect_alpha_conflicts(run_id=resolved_replay_run_id, ...)`.
  (2) new `build_replay_identity_consistency`-backed fail-fast guard,
  checked before any file is written. (3) `lineage`'s metadata carries a
  real top-level `"ticker"` field (previously only `source_ticker`). (4)
  wired in the same artifact finalizer + manifest a live run uses, with a
  replay-specific required-artifact set. (5) `ReplayResult` gains an
  additive, optional `identity_consistency` field.
- `comqutor_alpha/audit/ticker_consistency.py`: new
  `build_replay_identity_consistency` function (reuses this module,
  never a second, locally re-implemented identity check) +
  `REASON_REPLAY_ARTIFACT_IDENTITY_MISMATCH` reason code +
  `REPLAY_IDENTITY_ARTIFACT_FILENAMES` constant.
- `tests/test_replay_identity_correction.py` (new, addendum): 22 tests.
- `comqutor_alpha/storage/file_store.py`: `ALLOWED_ARTIFACT_FILENAMES`
  gains `evidence_facts.json`, `alpha_activations.json`, `conflicts.json`,
  `summary.json`, `artifact_manifest.json`.
- `tests/test_week3_security_hardening.py`: `_seed_week1_2_artifacts`'s
  synthetic `alpha_matches.json` fixture now backfills a `ticker` field
  on every match record (matching the real, current `alpha_mapper.py`
  contract) -- one pre-existing test's fixture had omitted it, which
  correctly failed the Ticker Consistency Audit under this sprint's new,
  stricter completion gate.

## Ticker authority rule

Priority order, exactly as specified: `run_orchestrator` (not available
at the Run Audit layer today) > `run_repository` (DB `research_runs.ticker`,
when a `repository` is passed) > `metadata.json` (or, for a replay, its
own `source_ticker`-derived `ticker` field) > `raw_agent_outputs.json`.
Normalization is strip+uppercase only -- confirmed no symbol-alias
mapping exists anywhere in `ticker_consistency.py`. An empty/`"unknown"`/
`null` value is never treated as a legal ticker (`normalize_ticker_for_audit`
returns `None`, correctly distinguished from a genuinely-present,
mismatched value via `TICKER_FIELD_INVALID` vs `TICKER_FIELD_MISSING`).

## Artifact contract

John's 9 required artifacts (`metadata.json`, `raw_agent_outputs.json`,
`structured_agent_outputs.json`, `evidence_facts.json`, `alpha_matches.json`,
`structure_graph.json`, `alpha_activations.json`, `conflicts.json`,
`run_audit.json`) all now export for every new completed run, verified
end-to-end on a real offline NVDA run (`present_required_artifact_count
== 9`, `artifact_completeness == "pass"`, final `status == "completed"`).
`entity_alpha_exposures.json` (pre-existing from the prior session) and
new `summary.json`/`artifact_manifest.json` are tracked as product
extensions, not part of John's required set, per spec. `conflict_results.json`
(replay-only, pre-existing) is preserved unchanged and the manifest
explicitly records it as `compatibility_alias_of: "conflicts.json"`.
Every export is a pure extraction: `alpha_activations.json` ==
`structure_graph.json["activation"/"activation_versions"]` byte-for-byte
(test-verified); `conflicts.json`'s `conflicts`/`main_conflict`/`arbitration`
== the exact DB conflict result (test-verified); `evidence_facts.json`'s
group IDs == the exact union of every v2 alpha's own
`evidence_fact_groups` (test-verified).

## SNDK / TSM root cause

**Verdict: `FRONTEND_STALE_CACHE` (confirmed, fixed) and
`LEGITIMATE_PEER_COMPARISON` (confirmed, no fix needed).**
`ARTIFACT_TICKER_MISMATCH` and `FOREIGN_TICKER_EVIDENCE_CONTAMINATION`
are explicitly **ruled out** by direct evidence.

- Both real, on-disk SNDK source runs (`183b04dd-...`, `8d21c047-...`)
  were re-verified via a fresh Architecture Replay + the full Ticker
  Consistency Audit: zero occurrences of the string `"TSM"` in any
  artifact of either run, `ticker_consistency: pass`,
  `foreign_entity_findings` with `actual_ticker == "TSM"`: 0 for both.
- The real TSM source run (`1a338ced-...`) legitimately contains a graph
  node labeled `"TSM Revenue Growth"` -- this is deterministic,
  by-design, per-ticker factor naming (`structure_extractor.py:60-61`:
  `f"{ticker.upper()} Revenue Growth"`), not a defect.
- Direct code audit of `frontend/src/pages/StructureGraphPage.tsx` found
  a real, reproducible bug: its data-fetching hook correctly used
  `AbortController` to prevent a *stale* (superseded) request from
  overwriting newer state, but never cleared `graph`/`conflicts` React
  state when the route's `runId` changed. Combined with the render guard
  `isLoading && !graph`, switching from a TSM run to a SNDK run via
  client-side navigation continued rendering the *TSM* run's full
  Structure Graph -- including `"TSM Revenue Growth"` -- for the entire
  loading window of the newly-selected SNDK run. This is sufficient on
  its own to produce exactly the reported symptom.
- Fixed with a minimal change (clear state immediately on `runId` change,
  plus a defensive `run_id`-mismatch check on the fetched payload that
  shows a "Data Integrity Warning" and refuses to render rather than
  ever mixing runs) and 4 new regression tests, all passing.

Full evidence: `docs/audit_artifacts/sndk_tsm_forensic_report.json`,
`frontend_run_switch_verification.json`.

## Per-run audit results (real data, Architecture Replay, 0 Provider calls)

See `docs/audit_artifacts/ticker_consistency_summary.json` /
`ticker_consistency_case_results.csv` (raw) for all 7 cases. Summary:

| Ticker | Source run | ticker_consistency | inconsistencies | foreign findings | artifact_completeness | provider_calls | source_hash_unchanged |
| --- | --- | --- | --- | --- | --- | --- | --- |
| NVDA | e434f80b-... | pass | 0 | 0 | pass | 0 | true |
| SNDK | 183b04dd-... | pass | 0 | 0 | pass | 0 | true |
| SNDK | 8d21c047-... | pass | 0 | 1 (warning, co-mentioned) | pass | 0 | true |
| TSM | 1a338ced-... | pass | 0 | 6 (warning, co-mentioned) | pass | 0 | true |
| MSFT | 61f3e019-... | pass | 0 | 1 (warning, co-mentioned) | pass | 0 | true |
| QQQ | a364e0ee-... | pass | 0 | 3 (warning, co-mentioned) | pass | 0 | true |
| AMD | 66794ad5-... | pass | 0 | 3 (warning, co-mentioned) | pass | 0 | true |

7/7 pass on both dimensions. Every "foreign finding" is a
`co_mentioned_with_subject`/`edge_evidence_mention` **warning** (a real
peer/supply-chain mention alongside the run's own subject ticker, e.g.
TSM's report legitimately naming NVDA/AMD as foundry customers) -- never
misclassified as contamination, confirming the conservative
comparison-vs-contamination heuristic works correctly on real report
text.

## API / UI behavior

`GET /api/research/{run_id}/artifacts`: verified end-to-end via
`TestClient` against a real completed run -- returns
`artifact_completeness`, `ticker_consistency`, and the full manifest;
unknown run -> soft `RUN_NOT_FOUND` (matches this codebase's existing
read-route convention, never a 500). `GET
/api/research/{run_id}/artifacts/{artifact_name}`: verified -- correct
`application/json` content-type, path traversal attempt -> 404, unknown/
disallowed filename -> 400, an old run with no manifest -> clean 404
(never 500). Frontend: `StructureGraphPage.tsx` fix as above (Data
Quality/Audit surfacing itself was already present in run_audit.json;
no separate new panel was required by this sprint's minimal-UI-change
scope).

## Replay results (post-correction)

Verified via `tests/test_replay_identity_correction.py` (22 tests, all 24
required items) and a real, 7-case Architecture Replay run (see
`docs/audit_artifacts/replay_identity_consistency.json`/
`replay_identity_case_results.csv`): 0 `tradingagents_calls`, 0
`llm_provider_calls`, 0 `market_data_provider_calls`, 0 `database_writes`
on every replay; source `raw_agent_outputs.json` sha256/size/mtime
unchanged before/after every run; every replay bundle
`artifact_completeness: pass`; **every** replay-local artifact
(`structured_agent_outputs.json`, `alpha_matches.json` (top-level and
every record/match), `extracted_structures.json`, `structure_graph.json`,
`alpha_activations.json`, `evidence_facts.json`, `conflicts.json`,
`conflict_results.json`, `entity_alpha_exposures.json`, `summary.json`,
`run_audit.json`, `artifact_manifest.json`) carries `replay_run_id`;
`metadata.json` carries `run_id`/`replay_run_id` = `replay_run_id` AND
preserves `source_run_id` distinctly; Conflict is evaluated with its
correct, real identity -- `RUN_ID_MISMATCH_count: 0` in all 7 cases,
never because the guard was bypassed. Conflict outcomes are real,
evidence-driven, and vary per run (never forced nonzero):

| Ticker | Source run | declared | admitted | suppressed | rejected |
| --- | --- | --- | --- | --- | --- |
| NVDA | e434f80b-... | 6 | 3 | 1 | 2 |
| SNDK | 183b04dd-... | 6 | 2 | 2 | 2 |
| SNDK | 8d21c047-... | 6 | 2 | 1 | 3 |
| TSM | 1a338ced-... | 6 | 3 | 1 | 2 |
| MSFT | 61f3e019-... | 6 | 1 | 1 | 4 |
| QQQ | a364e0ee-... | 6 | 5 | 1 | 0 |
| AMD | 66794ad5-... | 6 | 2 | 0 | 4 |

The NVDA result (3/6 admitted, main conflict A301 vs A304) matches the
exact values established in the prior sprint's own manual verification,
confirming the corrected identity mechanism reproduces the same, real,
evidence-based outcome the earlier bypass happened to also produce for
that one run -- the bypass was wrong on principle (a genuine identity
defect, silently worked around) even though it did not, for NVDA
specifically, additionally corrupt the admitted-conflict count.

## Provider call proof / source artifact integrity

`provider_calls: 0` and `source_hash_unchanged: true` for all 7 real
replay cases (both the original offline acceptance and this addendum's
re-verification) -- machine-verified, not asserted. `git diff --stat`
under `outputs/runs/` shows no changes (replay never writes there).

## Tests

- 20 new: `tests/test_ticker_consistency_audit.py` (all 15 required
  ticker-audit items covered, plus normalization/resolve-priority
  extras).
- 23 new: `tests/test_artifact_export_and_api.py` (export correctness,
  manifest, atomic-write/valid-JSON, finalizer determinism, John-field
  presence/correctness, replay Provider/DB/hash/ticker/RUN_ID_MISMATCH/
  completeness, API manifest/download/traversal/404/old-run-fallback).
- 4 new: `frontend/src/pages/StructureGraphPage.test.tsx` (all 4 required
  frontend items).
- 22 new (addendum): `tests/test_replay_identity_correction.py` -- all 24
  required replay-identity items, plus a dedicated rebase-helper test
  proving the rewrite is a targeted field rewrite (only `run_id`), never
  a blanket recursive string replace, and never mutates its input.
- 1 existing test's fixture corrected (`test_week3_security_hardening.py`,
  see above) -- not a behavior change, a fixture realism fix.

## Remaining limitations

- `run_identity`'s `debate_rounds`/`risk_rounds`/`thinking_enabled`
  remain `None` (no artifact records them today -- unchanged from the
  prior sprint's own documented gap, out of this sprint's scope to add).
- Foreign-ticker scanning is bounded to a fixed watchlist of tickers with
  real runs/candidate-list membership in this repo (`DEFAULT_TICKER_WATCHLIST`)
  -- a ticker outside that list would not be scanned for (conservative by
  design, never a false-positive risk, but also not an unbounded
  detector).
- No new Data Quality UI panel was added beyond what already existed;
  the sprint's minimal-UI-change instruction and the confirmed root
  cause (a data-fetching bug, not a missing-visibility problem) did not
  call for one.
