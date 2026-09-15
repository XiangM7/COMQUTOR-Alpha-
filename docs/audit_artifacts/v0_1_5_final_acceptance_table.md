# v0.1.5 Final Acceptance Table

Read/derive/report only. **No fresh runs. No Provider calls. No production semantic changes. No Gold modification.** HEAD unchanged (`9f228723fad5406c72e62beca67ec70ea0fdb004`). No commit. No push.

## Version Scope

COMQUTOR Alpha v0.1.5 is the current Final Acceptance Cleanup package built on the existing feature and fresh-six QA baseline. Historical artifacts carrying v0.1.3 or v0.1.4 filenames are preserved as provenance and are **not** retroactively renamed. This final acceptance table itself is a v0.1.5 artifact.

## Result: `JOHN_APPROVED_GOLD_AUTHORITY_NOT_FOUND`

## John — Final Acceptance

```
Fresh six ticker:                6/6
Artifact completeness:           6/6 at 9/9
Graph edge gate:                 6/6 pass (edges observed: 7-9)

John-approved Alpha comparison:  NOT_COMPUTABLE -- no John-approved Gold exists
Main conflict match:             NOT_COMPUTABLE -- no John-approved Gold exists
Conflict mismatches:             N/A (no Gold to mismatch against)
Unexpected dominant:             3 (NVDA:A301, MSFT:A103, SNDK:A201)

Gold authority:                  NONE FOUND (closest: alpha_conflict_gold_benchmark_v1.json,
                                  self-labeled external_analyst_gold / retrospective, not John-signed)

No production semantics changed: YES
No fresh runs executed:          YES
```

## Why This Is a Hard Stop, Not a Table

This task required strict, auditable proof that Alpha-detection and Main-Conflict expectations were **actually approved by John** before any acceptance comparison could be performed. Three independent lines of evidence, cross-confirming each other, establish that no such approval currently exists in this repository:

**1. The repository's own authority-classification mechanism says so, explicitly and numerically.** `docs/audit_artifacts/regression_label_authority_audit_v0.1.2.1.json` is the actual audit trail behind `comqutor_alpha.regression.authority_contract`'s five-level authority system (`APPROVED_GOLD`, `DOCUMENTED_EXPECTATION`, `PROVISIONAL_AI_PREDICTED`, `REJECTED_OR_SUPERSEDED`, `UNKNOWN`). Its own summary reads:

```
"approved_gold_alpha_expectations": 0,
"alpha_expectation_total_count": 37,
"main_conflict_authority_breakdown": {"APPROVED_GOLD": 0, ...},
"exact_main_conflict_gold_count": 0,
"note": "0 of the 6 tickers currently has any expected main conflict
qualifying as exact regression gold. 0 Alpha expectations qualify as
exact per-run regression gold..."
```

**2. The file used as "Gold" throughout the entire prior v0.1.3 session says so about itself.** `docs/audit_artifacts/alpha_conflict_gold_benchmark_v1.json` — the source of the 61.0317% "official Alpha Hit" figure computed and reported repeatedly in this session's earlier tasks — carries `benchmark_type: "external_analyst_gold"` and `validation_mode_for_existing_runs: "RETROSPECTIVE_GOLD_VALIDATION"`, and its own `scope_statement` states verbatim: *"It is authored externally (analyst-provided expected sets)... and is NOT derived from or copied from docs/audit_artifacts/regression_label_authority_audit_v0.1.2.1.json (that file's own APPROVED_GOLD count remains zero and is untouched by this benchmark)."* This is precisely the category of "retrospective/diagnostic benchmark artifact... NOT automatically acceptance authority" this task warned against silently substituting.

**3. The one genuine John-approval request document in the repository was never signed.** `docs/audit_artifacts/john_v0.1.2.1_approval_sheet.md` contains explicit sections (A: Alpha Regression Gold, B: Main Conflict Regression Gold, E: Final Approval) each ending in unchecked boxes (`□ APPROVED`, `□ APPROVED WITH CHANGES`, `□ NEEDS REVISION`), a blank Comments field, and a blank Date field. It was never completed. Its own **proposed** Gold table also does not match `alpha_conflict_gold_benchmark_v1.json`'s numbers (e.g. its proposed TSM set is `[A103, A304]`, a 2-alpha set, versus the benchmark file's 6-alpha `[A101,A103,A201,A301,A304,A601]`) — two separate, unreconciled proposals, neither approved.

**A fourth, independent confirmation comes from production itself**: every one of the six entries in `docs/audit_artifacts/v0_1_3_final_fresh_six_ticker_ledger.json` (the current, correctly-identified fresh-run authority) already carries `main_conflict.authority: "NOT_GOLD_EVALUABLE"` — the system's own persisted ledger agrees with this finding without any interpretation needed.

## Closest Candidate Artifacts, and Why Each Is Insufficient

| Candidate | Why Not Sufficient |
|---|---|
| `alpha_conflict_gold_benchmark_v1.json` | Self-labeled `external_analyst_gold` / `RETROSPECTIVE_GOLD_VALIDATION`; explicitly disclaims deriving from the `APPROVED_GOLD` chain. This was the file used as "Gold" all of v0.1.3 — its result is a diagnostic, not an acceptance result. |
| `john_v0.1.2.1_approval_sheet.md` | A genuine approval request, but every checkbox is blank, unsigned, undated. Its own proposed numbers also disagree with the benchmark file's numbers. |
| `john_acceptance_closure_v0.1.2.1.json` | Approves run-ID freshness/artifact-completeness consistency (John's Item 10), not Alpha/conflict Gold labels — and references a different, older six run IDs than the current v0.1.3 baseline. |
| `qa_closure_index.json` | Stale: its own `selected_runs.status` reads `NO_CURRENT_VALID_SEMANTIC_BASELINE` and does not reference the current six FINAL_FRESH_SELECTED runs at all. |
| `main_conflict_gold_adjudication_v0.1.2.1_r2.json` | A careful engineering-side proposed adjudication, explicitly performed blind to production outputs — but it is a proposal awaiting John's decision (Section B of the same blank approval sheet), not an approval itself. |
| `entity_alpha_exposure_seed_v0.1.yaml` | **Is** genuinely John-approved (2026-08-11, `status=approved_gating`, all six tickers) — but approves Entity Exposure gating specifically, not Alpha-detection or Main-Conflict expectations. |

## Fresh-Run Authority (Independent of Gold Status)

Identifying the current authoritative fresh six runs does not depend on Gold approval, and is reported in full regardless of the hard stop above.

**Source**: `docs/audit_artifacts/v0_1_3_final_fresh_six_ticker_ledger.json` — **ticker consistency: 6/6 PASS.**

| Ticker | Run ID | Status | Artifact Completeness | Graph Edges | Actual Main Conflict | Alpha Memory |
|---|---|---|---:|---:|---|---|
| NVDA | `57d7b4c4-dbb9-4134-b962-ee2a873941cc` | completed, force_refreshed | 9/9 | 9 | A101__A304 (admitted) | shadow, no modulation |
| QQQ | `f88c8956-cb62-48aa-9951-89f8e8a95f83` | completed, force_refreshed | 9/9 | 9 | A304__A601 (admitted) | shadow, no modulation |
| MSFT | `43472ace-454f-4c69-892c-adca91c25be7` | completed, force_refreshed | 9/9 | 7 | NO_ADMITTED_MAIN_CONFLICT | shadow, no modulation |
| SNDK | `e8e0f398-7b26-4462-8135-a1410ea5b335` | completed, force_refreshed | 9/9 | 7 | NO_ADMITTED_MAIN_CONFLICT | shadow, no modulation |
| TSM | `dfc7ceb3-3584-4514-bd84-6c371aab3e95` | completed, force_refreshed | 9/9 | 8 | A101__A304 (admitted) | shadow, no modulation |
| AMD | `949f685a-3945-4fd0-b7b9-362b37c90721` | completed, force_refreshed | 9/9 | 8 | A101__A304 (admitted) | shadow, no modulation |

**Detection rule used** (reused unmodified, never reinvented): `comqutor_alpha.regression.regression_report_v3._detected_alphas()` / `_DETECTED_LEVELS` — `active`/`dominant`/`regime_level` count as detected; `candidate`/`capped_active`/`blocked`/`ambiguous`/`unavailable` never do.

## Per-Ticker Table (Expected Columns Reported as Not Available)

| Ticker | Run ID | Expected Alphas | Detected Alphas | Missing Expected | Unexpected Dominant | Allowed Main Conflict(s) | Actual Main Conflict | Match |
|---|---|---|---|---|---|---|---|---|
| NVDA | `57d7b4c4-...` | N/A (no Gold) | A101, A103, A301, A304, A601 | N/A | A301 | N/A (no Gold) | A101__A304 | N/A |
| QQQ | `f88c8956-...` | N/A (no Gold) | A001, A103, A304, A601 | N/A | — | N/A (no Gold) | A304__A601 | N/A |
| MSFT | `43472ace-...` | N/A (no Gold) | A001, A101, A103, A301 | N/A | A103 | N/A (no Gold) | NO_ADMITTED_MAIN_CONFLICT | N/A |
| SNDK | `e8e0f398-...` | N/A (no Gold) | A201, A304, A601 | N/A | A201 | N/A (no Gold) | NO_ADMITTED_MAIN_CONFLICT | N/A |
| TSM | `dfc7ceb3-...` | N/A (no Gold) | A101, A103, A201, A304, A601 | N/A | — | N/A (no Gold) | A101__A304 | N/A |
| AMD | `949f685a-...` | N/A (no Gold) | A101, A103, A301, A304, A601 | N/A | — | N/A (no Gold) | A101__A304 | N/A |

`detected_alphas` and `actual_main_conflict` are read directly from each ticker's own persisted run artifacts (`run_audit.json`, `structure_graph.json`) — not copied from any diagnostic report. `unexpected_dominant` = Alphas at `level=dominant` (no comparison to an expected set was possible, so this is simply every currently-dominant Alpha, reported factually, not classified as a defect).

## Main Conflict Mismatch Adjudication

Not applicable — no `allowed_main_conflicts` exists to compare against, so no mismatch can be adjudicated. This section is intentionally empty pending a signed Gold authority.

## Alpha Memory — Shadow-Only Verification

Verified (not modified) across all six tickers via the fresh-run ledger: **`mode: shadow`, `activation_modulation_applied: false`** for every ticker — consistent with John's requirement that Alpha Memory remain shadow-only. Alpha Memory does not affect any arithmetic in this table.

## Evidence Review (QA Context Only)

Alpha Match **83%**, Polarity **85.25%**, Critical reversal **0** — included as QA context only, per task instruction. Not used to compute `expected_alphas`, `allowed_main_conflicts`, or `main_conflict_match`.

## Historical Internal Diagnostic Result (Kept Separate)

The 61.0317% Alpha Hit figure computed and reported throughout the prior v0.1.3 session remains a valid, internally-consistent measurement — but against `alpha_conflict_gold_benchmark_v1.json` (external-analyst / retrospective), not against a John-approved acceptance authority. It is labeled here **`HISTORICAL_INTERNAL_DIAGNOSTIC_RESULT`**, explicitly distinct from **`JOHN_ACCEPTANCE_GOLD_RESULT`** (which is `NOT_COMPUTABLE` in this task). These two must not be conflated going forward.

## What Happens Next (Not Performed in This Task)

The blank `john_v0.1.2.1_approval_sheet.md` is the ready-made vehicle to obtain the missing approval — it has Sections A (Alpha Gold), B (Main Conflict Gold), and E (Final Decision) already drafted and waiting for John's checkmarks, comments, and signature. Once completed (or a v0.1.5-equivalent sheet is signed), this acceptance table can be rebuilt with real `expected_alphas`, `allowed_main_conflicts`, `missing_expected`, and `main_conflict_match` values. **This task does not create, propose, or pre-fill that sheet's decisions** — doing so would be inventing Gold, which is explicitly forbidden.

---

## Final Validation

Gold authority searched and found **not established** (absence itself independently auditable via `regression_label_authority_audit_v0.1.2.1.json` and the ledger's own `NOT_GOLD_EVALUABLE` fields). No Gold-labeled file was modified. Fresh-run authority identified (6/6 ticker consistency). Zero fresh runs executed. Zero Provider calls. Zero TradingAgents calls. Zero production code changes. Zero test changes. Alpha Memory modulation unchanged (shadow, false). Historical v0.1.2.1/v0.1.3/v0.1.4 artifacts not renamed. New files use v0.1.5 naming only.

**Production files changed: 0. Test files changed: 0. Commits: 0. Pushes: 0. Destructive git operations: 0.**
