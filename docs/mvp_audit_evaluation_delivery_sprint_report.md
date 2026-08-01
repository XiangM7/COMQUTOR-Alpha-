# MVP Audit, Evaluation, Golden Fixtures, and Delivery Readiness Sprint -- Report

Branch: `comqutor-structure-layer`. Historical HEAD at sprint start and
throughout: `139a83cc66f988ee1f770ba92cb58dccc39c321f` (never amended,
reset, or force-pushed; this sprint's changes sit as new uncommitted work
on top, per instruction -- no commit/push performed).

This is an engineering and delivery-infrastructure sprint: no investment
logic, Activation/Conflict formula, Factor taxonomy, Graph admission
guard, or `tradingagents/` file was touched. Every number quoted below was
computed from real artifacts (either this session's own tool output or
files already on disk) -- never invented.

## Executive Verdict

| Track | Verdict |
| --- | --- |
| A. Audit Consolidation (Run Audit v2) | **PASS** |
| B. Cross-run Evaluation Harness | **PASS** |
| C. Golden Case Format | **PASS** (see Golden ticker coverage below -- format PASS, *coverage* PARTIAL) |
| D. README / Deployment / Demo | **PASS** (Docker production-hardening explicitly deferred, per spec's own allowance) |
| E. License Boundary Report | **PASS** (two real copyleft findings surfaced -- see below; report itself is complete) |

## Golden ticker coverage (reported honestly, never disguised as a Harness failure)

Harness (Track B) = **PASS**. Golden ticker coverage is a *separate*,
independently-reported number:

- Candidate tickers (sprint spec section 23): NVDA, AMD, MSFT, AVGO, QQQ,
  SPY, TSM, SMCI, GOOGL, AMZN (10).
- Real bundles wrapping an actual, previously-completed research run
  (`historical_replay_case`): **NVDA, MSFT, SNDK*, AMD, GOOGL, QQQ (6
  bundles)** -- of which **5 of the 10 candidate tickers** (NVDA, AMD,
  MSFT, QQQ, GOOGL) are covered; SNDK\* is a bonus case outside the
  10-ticker candidate list (real historical data for it happened to be
  available on disk).
- Remaining candidate tickers with no bundle yet (AVGO, SPY, TSM, SMCI,
  AMZN): reported `pending_fixture` by the harness, **exit code 0**, never
  fabricated as passing and never counted as a Harness failure.
- Approval status: **0 of 11 bundles are `approved`** -- all are `draft`,
  `created_by: mvp_audit_evaluation_sprint (automated)`, `approved_by:
  null`. This sprint authored the bundles and their structural/hygiene
  expectations; it did not, and cannot, perform the domain-analyst review
  `approval_status: approved` implies. Each bundle's `case.yaml` `notes`
  field states this explicitly, and each ships an empty
  `manual_claim_labels.csv` template for that future review.

## Track A: Audit Consolidation (Run Audit v2)

### What changed

`comqutor_alpha/api/routes_research.py`: `RUN_AUDIT_SCHEMA_VERSION` bumped
`structure_correctness.run_audit.v1` -> `.v2`. Every v1 field/section is
emitted completely unchanged (verified: `test_minimal_v1_style_fixture_still_produces_a_valid_v2_payload`
in `tests/test_run_audit_v2.py` runs the *exact* pre-sprint minimal
fixture shape and asserts nothing broke). Twelve new top-level sections
added, all additive:

- `run_identity` -- run_id/ticker/analysis_date/created_at (metadata.json)
  plus started_at/completed_at/status (DB, when a `repository` is passed
  -- optional, read-only, degrades to `null` without one) plus
  `execution_mode` read *only* from an explicit `run_type` field
  (verified real on a replay run: reads `"architecture_replay"` correctly)
  -- **never guessed** from the absence of replay-lineage fields (a
  dedicated test asserts this: `test_execution_mode_is_null_when_not_recorded_never_defaulted`).
- `code_provenance` -- git HEAD/dirty-file-count at audit-generation time
  (a small `_git()` helper, same pattern as the existing
  `comqutor_alpha/replay/pipeline.py::_git`), explicitly documented as
  describing the *audit-generation* commit, not a historical run's
  original commit.
- `configuration_versions` -- 15 versioned identifiers (taxonomy,
  alias/relation registry, prompt contract, graph schema, activation/
  conflict formula versions, etc.), each preferentially read from the
  artifact that actually recorded it for *this* run (replay metadata's
  own lineage block, the vocabulary snapshot, the structured-output
  adapter's `adapter_version` field, the graph's own `schema_version`) --
  never recomputed from the current workspace's constants and passed off
  as historical fact. Where genuinely unrecorded (`claim_quality_policy_version`,
  `conflict_registry_version`, `data_sanity_schema_version`,
  `relation_registry_sha256` -- confirmed by audit that no such constant
  exists anywhere in the codebase), the value is `null` with
  `source: "not_recorded"` and `warning: "VERSION_NOT_CAPTURED_AT_RUN_TIME"`.
- `artifact_manifest` -- 11 artifact filenames, each with
  exists/size_bytes/sha256/schema_version/record_count/producer/consumers;
  a genuinely absent file reports `exists: false, status: "NOT_PRESENT"`,
  never a fabricated empty record.
- `claims` / `relations` / `graph` (pipeline accounting) +
  `accounting_invariants` -- three real conservation identities, each
  verified true *by construction* against the actual arithmetic in
  `structured_output_adapter.adapt_run_outputs` and `graph_builder.py`
  before being asserted:
  1. `candidate_segment_count == retained_claim_count + non_substantive_removed_count`
     (an earlier draft incorrectly also added boilerplate/disclaimer
     counts -- caught because the real NVDA and MSFT-replay runs both
     failed that version by exactly the boilerplate/disclaimer count;
     fixed after confirming boilerplate/disclaimer removal happens
     *before* `candidate_segment_count` is tallied, not after).
  2. `valid_claim_count == retained_claim_count - exact_duplicate_removed_count`.
  3. `claim_level_edge_candidate_count == merged_unique_edge_count + duplicate_or_rejected_collapsed_count`
     -- deliberately reports the honest *combined* duplicate-or-rejected
     term rather than asserting the false equation the sprint spec
     explicitly warns against (`candidates == admitted + rejected`),
     since graph_builder's own output cannot separate "collapsed
     duplicate" from "rejected" edges.

  All three verified `passed: true` against the real NVDA source run
  (`e434f80b-e4d0-4b09-9471-d84532659de5`) and a real MSFT architecture
  replay. A dedicated test (`test_accounting_invariant_failure_is_reported_not_hidden`)
  proves a genuinely broken fixture surfaces `FAIL`, not a silently-passing
  check.
- `graph_lineage` -- edge-level lineage completeness
  (edges_with_relation_ids/source_claim_ids/alpha_ids,
  alpha_link_reason_counts), computed directly from each edge's own
  fields (already present on every serialized edge:
  `graph_builder.py::_serialize_edge`).
- `activation_summary` -- per-alpha status/score/evidence counts,
  reusing (never recomputing) the exact same v2 alpha fields
  `evidence_eligibility` already reports -- a dedicated test
  (`test_activation_summary_reuses_v2_alpha_counts_verbatim`) asserts
  byte-identical numbers between the two sections for the same alpha.
- `conflict_summary` -- **every taxonomy-declared pair**, not only
  admitted ones (reshapes `conflict_payload["arbitration"]["candidate_evaluations"]`,
  which the frozen Conflict Detector already produces for
  suppressed/rejected pairs too) -- verified against a real NVDA
  `detect_alpha_conflicts()` call: 6 declared, 6 evaluated, 3 admitted, 1
  suppressed, 2 rejected, all correctly reshaped with per-pair outcome and
  reason codes.
- `audit_validation` -- self-check verdict (`PASS` /
  `PASS_WITH_WARNINGS` / `FAIL`) from real invariant pass/fail counts and
  real configuration-version gaps; a missing historical version alone
  never fails the whole run (`PASS_WITH_WARNINGS`), matching the sprint's
  explicit instruction.
- `numeric_semantics` (existing key) extended additively with
  `extracted_numeric_candidate_count`, `daily_range_eligible_count`,
  `daily_range_warning_count`, `corporate_action_issue_count`,
  `dividend_info_count`, `unknown_role_count`,
  `per_candidate_detail_available: false` +
  `per_candidate_detail_unavailable_reason` -- **explicitly deferred**,
  never fabricated: no artifact today persists individual reported-price
  candidates, so per-candidate detail cannot honestly be produced without
  a new persistence change (out of this sprint's scope).

`write_run_audit_artifact`/`build_run_audit_payload` gained an optional
`repository=None` parameter (read-only, best-effort, wrapped in
`contextlib.suppress`) threaded from the one production call site in
`_run_week3_graph_pipeline`.

### NVDA / MSFT acceptance (real data, not synthetic)

Ran `build_run_audit_payload` directly against:

- NVDA source run `e434f80b-e4d0-4b09-9471-d84532659de5`: all 3
  accounting invariants pass, `graph_lineage` correctly reports all-zero
  (this run's on-disk `structure_graph.json` predates the earlier
  Structure Integrity Repair sprint's lineage fix and was never
  regenerated -- **consistent** with the existing, already-shipped
  `canonical_relation_lineage`/`local_structure_support` sections
  reporting the identical all-zero for the same frozen artifact; not a
  new-code bug).
- A real MSFT Architecture Replay (`replay-20260730T185907Z-3b948d8a`,
  regenerated fresh from `raw_agent_outputs.json`): `execution_mode` read
  correctly as `"architecture_replay"`, all 3 invariants pass,
  `configuration_versions` populated from the replay's own rich lineage
  block (`taxonomy_version=alpha_taxonomy_v1`,
  `graph_schema_version=week3.structure_graph.v2`, etc.).

### Tests

14 new tests, `tests/test_run_audit_v2.py` (all 10 required test items
from the spec covered: v1 readability, v2 sections present, honest
null+warning for missing versions, deterministic artifact hashes +
explicit NOT_PRESENT, claim/edge accounting invariants correct
(including a failure-surfacing test), all conflict outcomes included,
production/shadow reuse verified byte-identical, DB round-trip via a real
in-memory SQLite `research_runs` row, and non-mutation of source
artifacts).

## Track B: Cross-run Evaluation Harness

### What was built

New package `comqutor_alpha/evaluation/` (`expectations.py`,
`golden_case.py`, `policy.py`, `runner.py`, `metrics.py`, `cross_run.py`).
Entry point: `python -m comqutor_alpha.evaluation.cross_run --manifest
evaluation/manifests/mvp_cases.yaml --output-dir <dir>`.

Deliberately reuses (never duplicates) the existing, already-tested
`comqutor_alpha.replay.pipeline.run_structure_replay` for both
`frozen_golden_case` and `historical_replay_case` execution -- 0 Provider
calls, source-artifact sha256/size/mtime integrity checked by that
function itself. `live_smoke_result` never replays anything and never
evaluates `expected.yaml` against it (enforced in code, not just
convention -- see `runner.run_case`'s explicit `case.case_type !=
"live_smoke_result"` guard, and a dedicated test).

12 expectation types implemented (`exact`, `range`, `set_equals`,
`set_contains`, `one_of`, `minimum`, `maximum`, `must_exist`,
`must_not_exist`, `path_exists`, `evidence_link_exists`,
`manual_review`) plus the two graph-specific declarative constructs
(`required_paths` BFS reachability, `zero_edges_allowed` opt-in) and a
`claims.forbidden_patterns` boilerplate-leakage check.

Thresholds live in `evaluation/policies/mvp_evaluation_policy.yaml`
(5 configurable rates/counts) -- deliberately carries **no** global
"every run needs N edges" default; that stays a per-Golden-Case
`expected.yaml` concern.

### Discovered defect (out of this sprint's scope to fix, reported here)

Running the harness against 6 real historical runs surfaced a genuine,
previously undetected defect in the **existing, already-shipped**
`comqutor_alpha/replay/pipeline.py::run_structure_replay`: it calls
`detect_alpha_conflicts(run_id=<new replay_run_id>, ...)`, but the
regenerated `structure_graph.json`'s `activation` block still carries the
*original source run's* `run_id` (inherited from
`alpha_matches_payload`/`extracted_structures_payload`, ultimately from
`adapt_run_outputs`'s own embedded `run_id`). Conflict Detector's
defensive `_embedded_identity_mismatch` check (`conflict_detector.py:634`)
therefore rejects **every** declared pair on **every** replay with reason
code `RUN_ID_MISMATCH` -- confirmed directly on the NVDA replay
(`arbitration.admitted_count: 0`, all 6 pairs `rejected` with
`['RUN_ID_MISMATCH']`), and the existing `tests/test_replay_pipeline.py`
/ `tests/test_replay_all_api.py` never assert anything about conflict
outcomes, which is why this has gone uncaught. This is a real bug in
`comqutor_alpha/replay/pipeline.py`'s **existing, pre-sprint** code, not
introduced by this sprint. Per this sprint's explicit boundary (no
Conflict/Replay logic changes), it is **not fixed here** -- flagged as a
recommended follow-up (see below). Its only effect on this sprint's own
deliverables is that the cross-run evaluation's `conflict.admitted_pair_count_total`
metric is currently always 0 for every `historical_replay_case`; this is
reported honestly in `docs/audit_artifacts/cross_run_evaluation_summary.json`,
not concealed or worked around.

### Offline acceptance run (real data)

`docs/audit_artifacts/cross_run_evaluation_summary.json` /
`cross_run_case_results.csv` / `cross_run_evaluation_report.md` (this
sprint's actual output, not illustrative):

- 11 cases declared (10 candidate tickers + 1 bonus SNDK case), **6
  completed, 5 pending_fixture, 0 blocked, 0 error**.
- **Provider calls: 0.** `source_artifacts_changed: false`.
- **0 cases with a failed required expectation** -- all 6 completed
  cases' structural/hygiene expectations (graph edge-count minimum with
  `zero_edges_allowed`, admitted-conflict bull/bear-evidence invariants,
  boilerplate-leakage forbidden patterns) pass on real data.
- Real aggregate metrics: 8,501 retained claims across the 6 runs (4,694
  analytical / 3,807 context-only), graph node counts `[7, 8, 10, 10, 12,
  13]`, graph edge counts `[0, 0, 0, 8, 9, 9]` (3 of 6 zero-edge --
  legitimate given those runs' own frozen `structure_graph.json` predates
  the lineage fix, same as the NVDA case above; not a Harness defect).
- Exit code: `0`.

### Tests

24 new tests, `tests/test_evaluation_harness.py`, covering all items from
the spec: every expectation type, `zero_edges_allowed` doesn't fail,
per-case minimum-edge *can* fail, valid/missing/invalid bundle handling,
hash-mismatch detection, `frozen_golden_case` and `historical_replay_case`
running end-to-end (0 Provider calls, via the real approved deterministic
NVDA fixture also used by the W5 demo and several existing test suites),
`pending_fixture` reported honestly (never a fabricated pass),
`live_smoke_result` never treating exact stochastic text as an oracle,
report-file generation, non-mutation of the source run, and non-zero exit
code on a failed required expectation.

## Track C: Golden Case Format

`evaluation/golden_cases/<case_id>/` bundle format implemented per spec
(`case.yaml`, `expected.yaml`, optional `manual_claim_labels.csv`) with a
fully-commented `_template/` (deliberately not runnable -- its
`case_type` is a placeholder value no code path executes). 6 real bundles
shipped (see coverage note above), each wrapping a genuine historical run
via `historical_replay_case` with conservative, honestly-scoped
structural/hygiene expectations (never a fabricated domain-correctness
oracle) and an empty `manual_claim_labels.csv` awaiting real analyst
review.

## Track D: README / Deployment / Demo

- `README_DEV.md` (new, repo root) -- architecture overview (every stage
  named with its real module path), backend/frontend/Postgres setup,
  every env var actually read by the codebase (cross-referenced against
  `.env.example` -- 12 previously-undocumented `COMQUTOR_*`/`TRADINGAGENTS_*`
  vars added there), test/lint/build commands (all verified to actually
  exist), troubleshooting, and the provider-free offline workflow.
- `docs/deployment_runbook.md` (new) -- local dev and minimal
  single-server paths using the real, already-existing Dockerfile/compose
  Postgres profile; full container-orchestration production hardening
  explicitly marked an optional follow-up (the spec's own allowed
  outcome when Docker exists but extending it to full production
  architecture would expand scope).
- `docs/demo_runbook.md` (new) -- which fixed case (NVDA + QQQ approved
  deterministic offline fixtures), how to start/verify/stop, common
  failure modes.
- `scripts/demo_offline.sh` (new) -- a thin, explicitly-documented wrapper
  around the **existing** `scripts/run_w5_demo.sh` (reused, not
  duplicated, per the spec's own instruction) -- verified end-to-end: its
  port-occupied guard correctly refused to start a second instance
  against an already-running real dev API on port 8001.
- `scripts/healthcheck.sh` (new) -- 8 checks (backend health, DB
  connectivity, fixture presence, run/graph/conflict API readability,
  frontend build presence, frontend server reachability) against a
  running instance; **verified twice**: against a deliberately-unreachable
  port (all applicable checks FAIL, exit code 1) and against the real,
  already-running dev instance on port 8001/5175 (all 8 checks PASS,
  exit code 0, using real data: run `a364e0ee-...` / QQQ).

## Track E: License Boundary Report

`docs/license_boundary_report.md` + `docs/third_party_inventory.csv` (61
rows). Every `detected_license` value was read from repo-local evidence
only -- the root `LICENSE` file (Apache-2.0, copyright-holder placeholder
never filled in), installed Python package metadata
(`importlib.metadata`, fully offline), and frontend
`node_modules/*/package.json` `"license"` fields -- **never guessed from
a package name, never looked up online**.

Two real, non-trivial findings surfaced (both explicitly flagged
`VERIFY_WITH_COUNSEL_OR_UPSTREAM`, not resolved by this report):

- **`backtrader`** (a direct runtime dependency,
  `pyproject.toml [project.dependencies]`): **GPL-3.0-or-later**.
- **`psycopg[binary]`** (a direct runtime dependency): **LGPL-3.0-only**.

`tradingagents/` boundary: root `README.md` is verbatim upstream
TauricResearch/TradingAgents content; 5 files under
`tradingagents/llm_clients/` + `tradingagents/comqutor_outputs.py` carry
local COMQUTOR/DeepSeek edits (confirmed by grep + continuous
`git log --follow` history showing no repo-split event) -- none touched
by this sprint (`git diff --stat` shows zero changes under
`tradingagents/`).

## Cross-track regression checks

- Full backend suite (`pytest -m "not integration"`): **2430 passed, 1
  skipped (langchain_aws not installed, pre-existing), 0 failed**. This
  sprint added 38 new tests total (14 in `tests/test_run_audit_v2.py` for
  Track A, 24 in `tests/test_evaluation_harness.py` for Track B/C); the
  first full-suite measurement taken this session (2406 passed) was
  already after Track A's tests landed, and the second (2430 passed)
  after Track B/C's -- the +24 delta between those two measurements
  matches Track B/C's 24 new tests exactly, with zero regressions in
  either measurement.
- No existing test was modified or deleted.
- No historical run's own artifacts (`outputs/runs/<run_id>/`) were
  written to -- every replay/evaluation writes only to a brand-new
  `outputs/replays/<id>/` or the harness's own `--output-dir`, verified
  by `run_structure_replay`'s own before/after sha256 check (never
  `"blocked"` in any run performed this sprint) and this sprint's own
  `test_audit_generation_does_not_mutate_source_artifacts` /
  `test_report_files_are_generated_and_source_artifacts_are_untouched`
  tests.
- Ruff: clean on every file touched or added this sprint.

## Completion Matrix

| Item | Status |
| --- | --- |
| Run Audit v2 (12 new sections, v1 preserved) | Done |
| Accounting invariants (3, verified on real data) | Done |
| Cross-run Evaluation Harness (offline, 0 Provider calls) | Done |
| Golden Case format + template | Done |
| Golden ticker coverage: 10/10 approved | **Not done** (0/10 approved -- draft only, honestly reported) |
| README_DEV / deployment / demo docs | Done |
| Offline demo + healthcheck scripts | Done |
| License boundary report + third-party inventory | Done |
| Per-candidate numeric-semantics detail | Explicitly deferred (documented, not silent) |
| `replay/pipeline.py` RUN_ID_MISMATCH conflict-detection bug | Discovered + reported, **not fixed** (out of scope) |

## Recommended next sprint

1. Fix `comqutor_alpha/replay/pipeline.py::run_structure_replay`'s
   `detect_alpha_conflicts(run_id=...)` call so a replay's conflict
   admission is not unconditionally rejected by `RUN_ID_MISMATCH` --
   currently every historical replay (via the CLI or this sprint's
   Evaluation Harness) reports 0 admitted conflicts regardless of the
   underlying data. Add a regression test asserting a real admitted
   conflict survives a replay.
2. Get a domain analyst to review and promote at least the 5
   candidate-ticker `historical_replay_case` bundles from `draft` to
   `reviewed`/`approved`, filling in `manual_claim_labels.csv` and
   tightening `expected.yaml` beyond structural/hygiene checks.
3. Freeze `frozen_golden_case` bundles (self-contained, not
   `historical_replay_case`) for the 5 still-`pending_fixture` tickers
   (AVGO, SPY, TSM, SMCI, AMZN).
4. Resolve the `backtrader` (GPL-3.0-or-later) and `psycopg[binary]`
   (LGPL-3.0-only) licensing questions with counsel before any
   commercial distribution decision.
5. If per-candidate numeric-semantics detail becomes a real product
   need, add persistence for individual reported-price candidates (a
   new, currently-nonexistent artifact) -- do not retrofit this Run
   Audit v2 payload to fake it from aggregate counts.
