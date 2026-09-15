# Regression Label Authority Audit — v0.1.2.1

Read-only audit. No production code, Alpha Mapper, B1/B2/B4, conflict taxonomy, or regression label file was modified. No rerun, no Provider call, no commit, no push. Branch `comqutor-structure-layer`, HEAD `9f228723fad5406c72e62beca67ec70ea0fdb004`.

## Why this audit exists

Regression repair must not tune production behavior against labels whose authority is provisional, superseded, or not tied to a frozen test case. Before any repair work touches Alpha Mapper, B2, or the conflict taxonomy, we need to know which of the currently-referenced "expected Alpha" and "expected main conflict" values actually carry enough authority to serve as exact gold — and which are historical AI predictions, drafting artifacts, or already-rejected pairs that a repair task could otherwise silently "fix toward" by mistake.

## Expected Main Conflict Authority

| Ticker | Expected Conflict | Source | Authority | Frozen Reference? | Canonical Today? | Exact Gold? |
|---|---|---|---|---|---|---|
| NVDA | A101__A304 | Development Plan §12 ("Bull A101 vs Bear A304"), Week 4 Gate | DOCUMENTED_EXPECTATION | No | Yes | **No** |
| NVDA | A301__A304 | J2 v0.2 `conditional_conflicts`; actually observed on the one bound reference run (`e3eb3909-...`) | PROVISIONAL_AI_PREDICTED | Yes (one run only) | Yes | **No** |
| QQQ | A001__A501 | Development Plan §12 ("Bull A001 vs Bear A501"), Week 4 Gate | DOCUMENTED_EXPECTATION | No — `run_bound_expectations: null` | Yes | **No** |
| MSFT | A102__A304 | Development Plan §12 only; v0.1 `allowed_main_conflicts` | **REJECTED_OR_SUPERSEDED** (PD-017) | No | **No** (`A102.conflict_alphas == []`) | **No** |
| SNDK | A201__A304 | J2 v0.1 `allowed_main_conflicts` | **REJECTED_OR_SUPERSEDED** (structural, no dedicated PD) | No | **No** (`A201.conflict_alphas == []`) | **No** |
| SNDK | A301__A304 | J2 v0.2 `conditional_conflicts` | PROVISIONAL_AI_PREDICTED | No | Yes | **No** |
| TSM | A201__A304 | J2 v0.1 `allowed_main_conflicts` | **REJECTED_OR_SUPERSEDED** (structural, no dedicated PD) | No | **No** | **No** |
| TSM | A301__A304 | J2 v0.2 `conditional_conflicts` | PROVISIONAL_AI_PREDICTED | No | Yes | **No** |
| AMD | A201__A304 | J2 v0.1 `allowed_main_conflicts` | **REJECTED_OR_SUPERSEDED** (structural, no dedicated PD) | No | **No** | **No** |
| AMD | A101__A304 | J2 v0.2 `conditional_conflicts` | PROVISIONAL_AI_PREDICTED | No | Yes | **No** |
| AMD | A301__A304 | J2 v0.2 `allowed_conflicts` (weakest category) | PROVISIONAL_AI_PREDICTED | No | Yes | **No** |

**Zero of the eleven currently-referenced expected-main-conflict values qualify as exact regression gold today.** Two (NVDA A101__A304, QQQ A001__A501) trace to the real Development Plan and are canonical, but carry no approval signature and no frozen reference run. Four are formally or structurally rejected. The rest are unapproved, provisional, run-unbound predictions.

## Expected Alpha Authority

37 individual Alpha expectations were found across the six tickers (v0.2's `structural_expectations.positive_alphas` / `negative_alphas` / `conditional_alphas`). None are per-run exact gold; the table below is condensed by category rather than listing all 37 rows individually (the full per-Alpha table is in the JSON artifact).

| Ticker | Alphas (positive/negative) | Source | Authority | Conditional? | Frozen Reference? | Exact Gold? |
|---|---|---|---|---|---|---|
| NVDA | A101, A103, A201, A301 / A304 | Development Plan §12 row + v0.2 structural | DOCUMENTED_EXPECTATION | No (structural, ticker-general) | No | **No** |
| NVDA | A102, A601 | v0.2 `conditional_alphas` | PROVISIONAL_AI_PREDICTED | Yes | No | **No** |
| QQQ | A001, A003 / A304, A501 | Development Plan §12 row + v0.2 structural | DOCUMENTED_EXPECTATION | No (structural) | No | **No** |
| QQQ | A101, A601 | v0.2 `conditional_alphas` | PROVISIONAL_AI_PREDICTED | Yes | No | **No** |
| MSFT | A101, A102, A301 / A304 | Development Plan §12 row + v0.2 structural | DOCUMENTED_EXPECTATION | No (structural) | No | **No** |
| MSFT | A103, A601 | v0.2 `conditional_alphas` | PROVISIONAL_AI_PREDICTED | Yes | No | **No** |
| SNDK | A201, A301 / A304 | v0.2 structural (no Development Plan row — SNDK is absent from the Plan entirely) | PROVISIONAL_AI_PREDICTED | No (structural) | No | **No** |
| SNDK | A103, A601 | v0.2 `conditional_alphas` | PROVISIONAL_AI_PREDICTED | Yes | No | **No** |
| TSM | A103, A201, A301 / A304 | v0.2 structural (Development Plan names TSM as a golden ticker but gives it no table row) | PROVISIONAL_AI_PREDICTED | No (structural) | No | **No** |
| TSM | A101, A601 | v0.2 `conditional_alphas` | PROVISIONAL_AI_PREDICTED | Yes | No | **No** |
| AMD | A101, A201, A301 / A304 | v0.2 structural (Development Plan names AMD as a golden ticker but gives it no table row) | PROVISIONAL_AI_PREDICTED | No (structural) | No | **No** |
| AMD | A102, A103, A601 | v0.2 `conditional_alphas` | PROVISIONAL_AI_PREDICTED | Yes | No | **No** |

Important: MSFT's A102 as an **Alpha** is untouched by PD-017 — PD-017 rejected only the A102__A304 **conflict pair**, not A102's standing as a structural positive Alpha for MSFT. These are separate claims; do not conflate them in repair work.

## Superseded / Invalid Expectations

- **MSFT A102__A304** — formally rejected by PD-017. `A102.conflict_alphas == []` in the live taxonomy, verified directly. Must not be used as gold, must not be silently reintroduced.
- **SNDK A201__A304**, **TSM A201__A304**, **AMD A201__A304** — not canonical (`A201.conflict_alphas == []`, verified directly), already removed to `remove_while_undeclared` in J2 v0.2 for all three tickers. No single ticker's sharing this pattern with the other two makes it canonical; each was checked independently against the same source of truth (the live taxonomy) and each fails identically. No dedicated Product Decision exists for this pair (unlike MSFT/PD-017) — its rejection rests on direct taxonomy verification plus PD-017 §6's explicit analogous reasoning, not a numbered adjudication.

## Valid Regression Gold

**None.** No Alpha expectation and no main-conflict expectation currently in the repository meets the APPROVED_GOLD bar (formally approved by John/Product Owner, approval provenance present, tied to a defined reference input where applicable, not superseded, compatible with current taxonomy). J2 v0.2's own file header says this explicitly: *"NONE of the six tickers currently has a formally John-approved, artifact-complete, version-locked reference run."*

## Pending Product Decisions

- **NVDA A101__A304 vs A301__A304**: Development Plan says A101 vs A304; the one bound reference run actually produced A301 vs A304. Needs a human Product Owner decision on which (if either) should become the frozen-case gold, or whether NVDA's "expected main conflict" should simply remain conditional/multi-valued.
- **QQQ A001__A501**: real Development Plan provenance, canonical pair, but no reference run has ever been bound to it. Needs either (a) John/Product Owner formal sign-off plus a version-locked reference run, or (b) an explicit decision to leave it conditional indefinitely.
- **SNDK / TSM / AMD's entire expected-Alpha and expected-conflict sets**: none trace to the Development Plan at all (SNDK doesn't appear in it; TSM and AMD are named but given no table row). These are 100% provisional inference from J2 v0.1/v0.2, `John entity exposure seed v0.1`, and the taxonomy alone — never reviewed by John as ticker-specific expectations. A Product Owner should confirm whether these three tickers were ever meant to have exact per-run expectations at all, or only structural/conditional ones.
- **MSFT A102__A304**: PD-017 itself flags this as reopenable "with new formal evidence (e.g. an explicit ADR, a corrected Development Plan addendum...)" — currently closed, but not by a human.

## Regression Contract Recommendation

Based on repository evidence only:

- **exact_frozen_case**: NVDA's A301__A304 observation against reference run `e3eb3909-3744-4a02-9b32-b225cf6ef665` is the only expectation in the repository that is even structurally eligible for this category (it is the one place a specific frozen run and a specific observed conflict are bound together) — but it still requires formal approval before being called gold. No other ticker has anything eligible for this category today.
- **conditional_expectation**: every pair currently in each ticker's `conditional_conflicts`/`allowed_conflicts` (NVDA A101__A304 & A301__A304; QQQ A001__A501; SNDK A301__A304; TSM A301__A304; AMD A101__A304 & A301__A304), and every Alpha in every ticker's `conditional_alphas`.
- **provisional_not_gold**: all `structural_expectations` (positive_alphas/negative_alphas) for every ticker — real product inference, not per-run exact expectations, and never approved.
- **rejected_or_superseded**: MSFT A102__A304 (PD-017); SNDK/TSM/AMD A201__A304 (direct taxonomy verification + v0.2 removal).

---

# Final Answers

## 1. Exact Main Conflict expectations found (all six tickers)

NVDA: A101__A304, A301__A304 · QQQ: A001__A501 · MSFT: A102__A304 · SNDK: A201__A304, A301__A304 · TSM: A201__A304, A301__A304 · AMD: A201__A304, A101__A304, A301__A304

## 2. Authority level and exact-gold status, each one

| Expectation | Authority | Exact Gold? |
|---|---|---|
| NVDA A101__A304 | DOCUMENTED_EXPECTATION | NO |
| NVDA A301__A304 | PROVISIONAL_AI_PREDICTED | NO |
| QQQ A001__A501 | DOCUMENTED_EXPECTATION | NO |
| MSFT A102__A304 | REJECTED_OR_SUPERSEDED | NO |
| SNDK A201__A304 | REJECTED_OR_SUPERSEDED | NO |
| SNDK A301__A304 | PROVISIONAL_AI_PREDICTED | NO |
| TSM A201__A304 | REJECTED_OR_SUPERSEDED | NO |
| TSM A301__A304 | PROVISIONAL_AI_PREDICTED | NO |
| AMD A201__A304 | REJECTED_OR_SUPERSEDED | NO |
| AMD A101__A304 | PROVISIONAL_AI_PREDICTED | NO |
| AMD A301__A304 | PROVISIONAL_AI_PREDICTED | NO |

## 3. Counts

- Approved exact-gold conflicts: **0**
- Provisional conflicts: **5** (NVDA A301__A304, SNDK A301__A304, TSM A301__A304, AMD A101__A304, AMD A301__A304)
- Rejected/superseded conflicts: **4** (MSFT A102__A304, SNDK A201__A304, TSM A201__A304, AMD A201__A304)
- Documented-but-not-approved conflicts: **2** (NVDA A101__A304, QQQ A001__A501)
- Unknown/pending conflicts: **0** (every case had an identifiable source; several are pending *human* adjudication, tracked above under "Pending Product Decisions," but none is source-unknown)

## 4. Same summary for expected Alpha labels

37 Alpha expectations total. **0 approved gold. 15 DOCUMENTED_EXPECTATION** (NVDA/QQQ/MSFT structural positive+negative Alphas, tracing to real Development Plan rows). **22 PROVISIONAL_AI_PREDICTED** (all SNDK/TSM/AMD Alphas, which have zero Development Plan provenance, plus every ticker's `conditional_alphas`). **0 rejected** — no individual Alpha label (as distinct from a conflict pair) has been formally rejected by any Product Decision.

## 5. Is "main conflict match >= 4/6" methodologically valid with the CURRENT labels?

**NO.**

The persisted regression report (`outputs/regression/regression_report.json`, `label_version: "j2.provisional.v0.1"`) shows `main_conflict_match` is computed in `comqutor_alpha/regression/evaluator.py` as `main_conflict_id in allowed_main_conflicts` — a field that exists **only in v0.1's schema**, not v0.2's. v0.1 is explicitly self-declared `status: provisional_ai_predicted`, `evaluation_authority: provisional`, `formal_product_owner_approval: pending`, and its own header states it was "never John-approved, never formal gold." Concretely, v0.1's MSFT `allowed_main_conflicts` still contains `A102__A304`, which PD-017 has since formally rejected — meaning the metric, as currently wired, would still count a match against an explicitly rejected pair if one ever occurred. A pass/fail (or "N/6") threshold computed against a label set that (a) has no formal approval anywhere in the repository, (b) contains at least one already-rejected pair, and (c) has zero frozen per-run bindings for four of six tickers, cannot be read as a measure of production correctness — only as a measure of agreement with an old, unrevised, provisional guess.

## 6. Which current regression labels are safe to use for production repair?

None as exact per-run gold. The closest things to "safe to lean on" are the pieces already independently corroborated by a source outside the label files themselves:

- The **canonical conflict taxonomy** itself (`alpha_loader.py:MANDATORY_CONFLICT_WEIGHTS`, six pairs) — this is real, current, production-verified truth, not a label.
- **NVDA A101__A304** and **QQQ A001__A501** as *directional* product intent (real Development Plan text, canonical pairs) — safe to treat as informative signal for repair prioritization, not as a strict pass/fail target.
- **NVDA's single frozen reference run** (`e3eb3909-3744-4a02-9b32-b225cf6ef665`, observed A301__A304) — safe to use as a *known, real, reproducible data point* for that one run specifically, not as a ticker-wide claim.
- J2 v0.2's `remove_while_undeclared` lists (MSFT A102__A304; SNDK/TSM/AMD A201__A304) — safe to use as a **negative** constraint (these must not be treated as targets), which is the one place this repository already has clean, corroborated authority.

## 7. Which labels must NOT be used to tune production yet?

- **All of v0.1's `allowed_main_conflicts`**, because it is the metric's current live source and still contains a rejected pair (MSFT A102__A304).
- **Every `structural_expectations`/`expected_positive_alphas`/`expected_negative_alphas` entry for all six tickers** — self-declared ticker-general, not per-run, never approved.
- **Every `conditional_alphas`/`conditional_conflicts`/`allowed_conflicts` entry** — explicitly conditional by the label file's own design; using them as unconditional repair targets would contradict the schema they're defined in.
- **MSFT A102__A304** and **SNDK/TSM/AMD A201__A304** — formally/structurally rejected; repairing production to produce these would be repairing toward a superseded or non-canonical target.

Production code changed: **NO**
Regression rerun: **NO**
Provider calls: **0**
Commit: **NO**
Push: **NO**
