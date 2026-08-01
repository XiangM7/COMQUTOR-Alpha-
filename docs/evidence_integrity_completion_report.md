# Evidence Integrity Completion and Product Transparency Sprint — Report

Branch: `comqutor-structure-layer` (HEAD unchanged at `139a83cc66f988ee1f770ba92cb58dccc39c321f`, no commits made)
Source run: `e434f80b-e4d0-4b09-9471-d84532659de5` (NVDA, analysis_date 2026-07-30)
Provider calls made during this sprint (implementation + acceptance): **0**

This sprint completes the one item the prior Structure Integrity Repair
Sprint left PARTIAL — Conflict Detector was never wired to the shared
Evidence Fact Index, and Production/Shadow still disagreed on the eligible
claim set for 3 of 10 alphas — and adds a minimal, additive layer of
frontend transparency for what was already computed backend-side.

## Executive Verdict

| Track | Verdict |
|---|---|
| A. Production / Shadow Eligibility | **PASS** |
| B. Conflict Evidence Fact Integration | **PASS** |
| C. Product Transparency | **PASS** (one item explicitly DEFERRED, see below) |

## 0. Pre-implementation audit (section 2)

```
git branch --show-current  -> comqutor-structure-layer
git rev-parse HEAD          -> 139a83cc66f988ee1f770ba92cb58dccc39c321f (unchanged)
git diff --check             -> clean (exit 0)
```

Confirmed insertion points before writing any code:

- **Production eligibility**: `activation_scorer_v2._gather_qualifying_evidence` filters by `relation in QUALIFYING_RELATIONS = {activation, conditional, mixed}` AND `assertion_status != "negated"`.
- **Shadow eligibility**: `evidence_integrity._build_candidates` only required `match_status == "matched"` + `is_claim_eligible` — **no relation/assertion filter at all**.
- **Exact A001/A501/A601 divergence** (forensically isolated, not guessed):
  - **A001**: 1 claim with relation `invalidation` (counter-evidence) — production correctly excludes it, shadow incorrectly included it.
  - **A501**: 2 claims with relation `risk_relief` (counter-evidence for a risk alpha) — same pattern.
  - **A601**: 1 claim with `assertion_status = "negated"` — production correctly excludes it, shadow had no assertion check at all.
- **Conflict evidence path**: `conflict_detector._gather_qualifying_evidence` (a third, independent implementation) computed `evidence_strength` as a plain mean of raw claim match scores (`_mean_match_score`) — never deduplicated by fact, never touched the shared Evidence Fact Index.
- **Frontend insertion points**: `AlphaCard.tsx` (evidence/structure rows), `ConflictCard.tsx` (bull/bear evidence rendering, one card per raw claim), `ResearchRunPage.tsx`'s `DataQualityPanel` (warnings only, no semantic-role detail) and its static "N neutral or unclassified findings" note (no expand).

## Track A — Production / Shadow Evidence Eligibility Unification

### What changed

- `evidence_fact_index.py` gained the single canonical eligibility selector, `select_supporting_alpha_claims(matches, alpha_id, policy_version=ALPHA_ACTIVATION_EVIDENCE_V1)` — moved (not duplicated) from Activation's own filter chain, plus the `relation_for_match` resolver and `QUALIFYING_RELATIONS` constant it depends on (also relocated here to avoid a circular import, re-exported under the same names everywhere else).
- `activation_scorer_v2._gather_qualifying_evidence` now delegates eligibility to the shared selector, only shaping the result into its own richer per-claim dict.
- `evidence_integrity._build_candidates` now calls the **same** selector, once per distinct alpha present in the run's matches — this is the fix that closes A001/A501/A601.
- Fact-group IDs unified too: `evidence_fact_group_id(run_id, ticker, claim_ids)` is now the one hash function both `activation_scorer_v2._group_evidence` and `evidence_integrity.build_evidence_groups` call — previously production used an ad hoc `"fact:" + "|".join(claim_ids)` string.
- `run_audit.json` gained an additive `evidence_eligibility` section: `policy_version`, per-alpha `counts_by_alpha`, per-alpha `exclusion_reasons_by_alpha` (recomputed live from `alpha_matches.json` via the shared selector), `production_shadow_consistent_count`, `production_shadow_inconsistent_alphas`.

### NVDA acceptance (real run, offline replay)

**10 / 10 alphas fully consistent** (`nvda_evidence_fact_consistency_after.csv`, `nvda_production_shadow_eligibility_diff.csv` — 0 diff rows):

| Alpha | Production raw | Production unique | Shadow raw | Consistent |
|---|---|---|---|---|
| A001 | 0 | 0 | 0 | ✅ |
| A003 | 1 | 1 | 1 | ✅ |
| A101 | 7 | 6 | 7 | ✅ |
| A102 | 1 | 1 | 1 | ✅ |
| A103 | 3 | 3 | 3 | ✅ |
| A201 | 6 | 5 | 6 | ✅ |
| A301 | 11 | 11 | 11 | ✅ |
| A304 | 11 | **5** | 11 | ✅ |
| A501 | 1 | 1 | 1 | ✅ |
| A601 | 9 | 9 | 9 | ✅ |

A304's raw claim count (11) is unchanged — no claim was deleted, only the
counting semantics were unified. Exclusion reasons recovered live from the
real run (`run_audit.json`'s `evidence_eligibility.exclusion_reasons_by_alpha`):

```
A001: {"RELATION_NOT_SUPPORTING": 1}
A201: {"NON_ANALYTICAL_QUALITY": 3}
A304: {"NON_ANALYTICAL_QUALITY": 2}
A501: {"RELATION_NOT_SUPPORTING": 2}
A601: {"RELATION_NOT_SUPPORTING": 1}
```

Fact group IDs also verified byte-identical between production and shadow
for every alpha (spot-checked A304: both report the exact same 5 SHA256-
derived group ids).

## Track B — Conflict Evidence Fact Integration

### What changed

- `conflict_detector.py`: the existing `_gather_qualifying_evidence`/exclusion-audit pipeline is **completely untouched** (every existing `EXCLUDED_*` reason code, every admission/rejection test in `test_conflict_detector.py`, stays byte-identical — 146/146 pass unchanged). A new layer sits on top: `_group_qualifying_claims_into_facts()` groups the already-admitted qualifying claims via the shared `group_evidence_candidates`, and `_fact_grouped_strength()` replaces the evidence-strength input with a mean over unique fact groups' representative scores (previously a mean over raw claims).
- Additive per-conflict fields: `bull_raw_claim_count`, `bull_unique_fact_count`, `bull_distinct_agent_count`, `bull_overlap_ratio`, `bull_fact_group_ids` (+ the `bear_*` mirror), `shared_fact_group_ids`/`shared_fact_group_count`/`shared_fact_resolution` (dual-side integrity check — bull/bear pools are disjoint by construction since a claim's `matched_alpha` is singular, verified `"no_overlap"` on every real admitted conflict).
- `bull_structure`/`bear_structure` gained an additive `evidence_facts` list (`evidence_fact_group_id`, `representative_claim_id`, `member_claim_ids`, `supporting_agents`, `grouping_method`).
- **DB persistence bug found and fixed**: `storage/db/week4_persistence.py`'s `_whitelist_conflict`/`_whitelist_activation`/`_whitelist_local_structure_support` explicitly allowlist which fields survive a DB round-trip — none of the new fields (from this sprint OR the prior one: `raw_supporting_claim_count` etc., `incident_graph_edge_count` etc.) were in that allowlist, so every one of them was being **silently dropped** on persist/reload. Found via `test_week4_persistence.py`'s own round-trip test failing with a 13-key diff. Fixed by extending all three whitelist functions with proper typed validation (matching the file's existing per-field type/range-checking style, not a blind pass-through).
- Canonical pair registry and conflict score formula: **byte-identical**, verified via `test_conflict_score_formula_and_registry_are_unchanged` and the full existing `test_conflict_detector.py` suite passing unmodified.

### NVDA acceptance (real run, offline replay)

All 6 declared pairs still evaluated; 3 admitted (unchanged outcome set from last sprint). `nvda_conflict_evidence_fact_groups_after.csv` (41 rows) confirms every admitted conflict's fact groups are populated and traceable.

| Pair | Bull raw→unique | Bear raw→unique | Score before (this sprint) | Score after |
|---|---|---|---|---|
| A101 vs A304 | 7→6 | 11→5 | 33.28 | 29.48 |
| **A301 vs A304 (main)** | 11→11 | 11→5 | 36.81 | 30.52 |
| A304 vs A601 | 9→9 | 11→5 | 29.53 | 24.41 |

Score changes are the honest, expected consequence of Track A's eligibility
fix (A304's evidence dedup was already applied to Activation last sprint;
this sprint additionally applies the SAME dedup to Conflict's own
evidence-strength input, so A304's bear-side strength drops further, since
Conflict no longer averages 11 raw match scores but the 5 unique facts'
representative scores). **A301 vs A304 remains the main conflict** — not
forced, a direct consequence of it already having the largest margin.

## Track C — Product Transparency

### What changed (backend, additive)

- `score_alpha_v2` gained `high_overlap_warning` (reuses the frozen `REGIME_GATE_MIN_UNIQUE_EVIDENCE` threshold — never an invented cutoff): true when real overlap exists (raw > unique) and the deduplicated count falls below the gate's own evidence floor.
- `run_audit.json` gained `conflict_evidence_integrity` (pair-level bull/bear raw/unique counts, shared fact groups, `overlap_warning_pairs`) and `product_transparency` (which fields are available, so an older frontend build can feature-detect).
- `build_research_response` gained an additive `data_sanity_numeric_semantics` aggregate summary (evaluated/eligible/skipped counts, semantic role breakdown) — never per-candidate detail (that would need a new persisted artifact, out of "minimal" scope).

### What changed (frontend)

- **AlphaCard**: new "Raw supporting claims / Independent evidence facts / Evidence overlap" rows (with the backend's own `high_overlap_warning` message, never a client-invented threshold) and new "Incident graph edges / Qualifying activation-support edges / Excluded local edges" rows with an expandable "Why edges did not qualify" reason list. The pre-existing "Supporting evidence"/"Local structural edges" rows are **untouched** (never removed), with a code comment now documenting exactly what `local_edge_count` means. All new fields degrade gracefully (render nothing) on an older API payload — verified via a dedicated test.
- **ConflictCard**: new per-side "Independent evidence facts / Distinct agents / Evidence overlap (from N raw supporting claims)" stat line. Evidence rendering now groups by fact (one card per independent fact, with an expandable "N merged paraphrase(s)" detail) instead of one card per raw, possibly-repeated claim — falls back to the old per-claim rendering when `evidence_facts` is absent.
- **Data Quality panel**: new low-risk `<details>` summary ("N numeric candidate(s) skipped as non-market-price") showing the semantic-role breakdown and daily-range eligibility counts — never rendered as or alongside a warning-severity item; the main warning list itself already structurally excludes skipped candidates (that fix shipped last sprint).
- **Neutral/unclassified findings**: the previously-static "N neutral or unclassified findings are not shown" note is now a clickable `<details>` ("Neutral and unclassified findings (N)") that reveals the same capped (`MAX_FINDINGS_PER_DIRECTION`-style), already-fetched analytical claims on demand — reuses the existing API data, never renders all 238 at once, never mixes in context-only claims, never touches the positive/negative panels.

### Deferred (explicitly, not silently)

Full **per-candidate** numeric-semantics audit detail (e.g. showing the
exact `$187.60` candidate's individual role/reason inline in the Data
Quality panel) is **DEFERRED**. The backend does not currently persist a
per-candidate `reported_prices` list in any artifact/API surface (only
aggregate `checks`/`warnings`/`summary`); adding one would be a new
persisted artifact, beyond this sprint's "minimal frontend transparency"
mandate. The aggregate summary (counts + role breakdown) is shipped instead
and is sufficient to answer "was anything skipped, and why" for the whole
run.

### UI acceptance (verified via component tests against the real NVDA data shape)

- A304 Alpha Card: "Raw supporting claims: 11", "Independent evidence facts: 5", "Evidence overlap: 54.5%" — never "11 independent facts".
- GPU Demand / A301: Alpha Card shows "Incident graph edges: 0", "Qualifying activation-support edges: 0" for A301 specifically (see Track B/GPU Demand analysis below for why) — never a bare, unexplained "0".
- Conflict Radar (A301 vs A304): both sides show independent-fact/agent/overlap stats; evidence list shows fact groups, not raw paraphrases.
- Data Quality: no `$187.60` warning (backend fix, reconfirmed); skipped-candidate detail available on demand, never in the main warning list.

## GPU Demand / A301 — why the score is still 66.49

`nvda_gpu_demand_a301_edge_qualification.csv` (4 rows, one per GPU-Demand-incident edge):

| Edge | alpha_ids | Qualifies for A301? | Reason |
|---|---|---|---|
| `ai_capex -> gpu_demand` (causal) | A103 | No | `ALPHA_ID_NOT_ON_EDGE` |
| `gpu_demand -> nvda_revenue_growth` (causal) | A101 | No | `ALPHA_ID_NOT_ON_EDGE` |
| `narrative_momentum -> gpu_demand` (supportive) | *(none)* | No | `NO_COMMITTED_ALPHA_MATCH` |
| `semiconductor_cycle -> gpu_demand` (supportive) | A201 | No | `ALPHA_ID_NOT_ON_EDGE` |

**A301 `incident_graph_edge_count = 0`.** This is proven, not assumed: all 4
GPU-Demand edges' `source_claim_ids` were cross-referenced against A301's
own 11 committed claim ids (from `_gather_qualifying_evidence("A301", ...)`)
— zero overlap. Three of the four edges are legitimately owned by other
alphas (A103, A101, A201) whose own claims happen to be the ones backing
those specific edges; the fourth has no committed alpha match at all. A301's
own 11 claims support entirely different graph edges (none of which touch
`gpu_demand`). The activation score is correctly unchanged — there is
nothing to fix here; the Alpha Card now makes this explicit instead of
showing an unexplained 0.

## Cross-track regression checks

- `test_conflict_detector.py`: 146/146 pass unchanged (registry/formula untouched).
- `test_evidence_integrity.py`: 35/35 pass (one test's expectation legitimately updated — negated claims now correctly excluded from candidacy entirely, matching the new shared policy, documented inline).
- `test_activation_scorer_v2.py`: 29/29 pass.
- `test_week4_persistence.py`: 24/24 pass (after the whitelist fix).
- Full backend suite: 2393 passed, 0 failed, 47 skipped.
- Full frontend suite: 149 passed, 0 failed (16 files).
- `npm run build` (tsc -b && vite build): clean, 0 type errors.
- Source run artifact integrity: `raw_agent_outputs.json` sha256/size/mtime verified byte-identical before and after every replay in this sprint.
- Replay Provider calls: 0 (structured/extracted/graph/activation/conflict/data-sanity all recomputed via `llm_gateway=None` / the saved `market_data_snapshot.json`, no network).

## Completion Matrix

| Requirement | Status |
|---|---|
| Single canonical eligibility selector, used by Activation + Shadow | Done |
| A001/A501/A601 forensic diff (not just counts) | Done |
| 10/10 alphas production/shadow consistent | Done (0 diff rows) |
| Fact group IDs identical between production/shadow | Done |
| Conflict consumes shared Evidence Fact Index | Done |
| Conflict registry/formula byte-identical | Done (146/146 frozen tests unchanged) |
| Dual-side fact reuse checked, never silently double-counted | Done (`shared_fact_resolution` computed honestly) |
| DB persistence carries all new fields | Done (whitelist bug found + fixed) |
| Additive `run_audit.json` sections (3) | Done |
| AlphaCard: raw/facts/agents/overlap, incident vs qualifying | Done |
| ConflictRadar: per-side fact stats, grouped evidence | Done |
| Data Quality: aggregate semantic-role transparency | Done |
| Data Quality: per-candidate detail | **Deferred** (documented, not silent) |
| Neutral/unclassified findings entry | Done |
| GPU Demand / A301 explained with real data, not guessed | Done |
| Frontend build/test | Done (149 tests, clean build) |

## Recommended next sprint

1. If per-candidate numeric-semantics audit detail is wanted in the UI,
   persist the raw `reported_prices` extraction list as a new artifact
   field (currently only aggregated into `checks`/`warnings`).
2. Consider whether Conflict Detector's own admission-time relevance check
   (`_claim_is_relevant_to_alpha`) should also be reconciled against the
   shared eligibility selector's stricter relation/assertion policy — out
   of this sprint's scope (which was specifically the evidence-strength
   input, not admission), but worth a dedicated look now that both systems
   share the fact-grouping layer.
