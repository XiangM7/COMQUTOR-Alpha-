# Structure Integrity Repair Sprint — Report

Branch: `comqutor-structure-layer` (HEAD unchanged at `139a83cc66f988ee1f770ba92cb58dccc39c321f`, no commits made)
Source run: `e434f80b-e4d0-4b09-9471-d84532659de5` (NVDA, analysis_date 2026-07-30)
Provider calls made during this sprint (implementation + acceptance): **0**

This sprint fixes the three concrete production defects the prior NVDA
Structure Correctness Forensic Audit identified, without touching
TradingAgents, the canonical vocabulary, the Activation formula/weights, the
Conflict registry, or Entity Alpha Exposure.

## Executive Verdict

| Track | Verdict |
|---|---|
| 1. Structure-to-Activation Lineage | **PASS** |
| 2. Evidence Fact Integrity | **PARTIAL** |
| 3. Numeric Semantic Sanity | **PASS** |

## 0. Pre-implementation audit (as required, section 2)

```
git branch --show-current  -> comqutor-structure-layer
git rev-parse HEAD          -> 139a83cc66f988ee1f770ba92cb58dccc39c321f (unchanged)
git status --short           -> only pre-existing Task-A-sprint files (M/A) plus this sprint's new files
git diff --check             -> clean (exit 0)
```

Confirmed real insertion points before writing any code:

- **Lineage**: `structure_extractor._canonical_relation_record` (synthetic
  `relation_id` was being used as the edge's only `claim_id`) →
  `canonical_relation_block.validate_canonical_relations` (produces
  `evidence_quote`, no lineage) → `graph_builder._committed_alpha_ids_for_claim`
  (looks up `claim_index` built from `alpha_matches.json`, keyed by real
  claim_id — a `canrel_*` id can never be a key in that index) →
  `graph_builder` edge merge (unions `claim_ids`, computes `alpha_ids`) →
  `activation_scorer_v2._local_structure_component` (intersects edge
  `claim_ids` against the alpha's own qualifying claim ids).
- **Evidence integrity**: `activation_scorer_v2._group_evidence` /
  `_semantic_group_key` (exact-normalized-text + `duplicate_group_id` only)
  vs. `evidence_integrity.py`'s `_group_candidates` (union-find:
  `duplicate_group_id` → relation-triple → factor/event signature →
  conservative Jaccard near-match) — two independent grouping
  implementations, never reconciled.
- **Numeric semantics**: `reported_price_extractor.py`'s
  `_DISQUALIFYING_TERMS` list (eps/revenue/market cap/price target/%) never
  included moving-average/technical-indicator vocabulary, so `check_reported_prices`
  in `data_sanity/checker.py` range-checked a 200-day SMA value as if it were
  an observed market price.

## 1. Track 1 — Structure-to-Activation Lineage Repair

### What changed

- `canonical_relation_block.py`: new `resolve_relation_source_claims()`.
  Deterministically matches each accepted canonical relation's
  `evidence_quote` against the real, quality-gate-eligible structured claims
  from the *same* `source_agent_output_id` (never cross-agent/run/ticker),
  in priority order: exact text → whitespace-normalized exact →
  containment (quote-in-claim, then claim-in-quote). Ties broken by
  shortest containing claim, then `claim_index`, then `claim_id` — a total
  order, so "ambiguous" is reserved for genuine containment-tier ties at
  equal length (proven reachable in `test_ambiguous_equally_strong_candidates_are_flagged_not_guessed`).
  Produces `source_claim_ids` / `lineage_status` (`resolved` /
  `unresolved` / `ambiguous` / `not_applicable`) / `lineage_method` /
  `lineage_reasons` per relation. Never fabricates a claim_id.
- `structured_output_adapter.py`: lineage resolution now runs *after* a raw
  agent output's real structured claims are built (`eligible_records`),
  matching against that real pool — not at validation time, when only the
  raw text existed.
- `structure_extractor.py`: `_canonical_relation_record`/`_edge()`/`_make_node()`
  gained additive `source_claim_ids` / `relation_id` / `lineage_*` fields,
  separate from the legacy `claim_id`/`source_record_id` (which still holds
  the `relation_id` for audit/display — never silently repurposed).
- `graph_builder.py`: merged edges/nodes now carry additive
  `source_claim_ids`, `relation_ids`, `lineage_statuses`,
  `lineage_rejection_reasons`, and a new `alpha_link_reason_codes` field
  (`LINEAGE_UNRESOLVED` / `LINEAGE_AMBIGUOUS` / `NO_COMMITTED_ALPHA_MATCH`).
  Alpha-id attachment (for both nodes and edges) now walks
  `source_claim_ids` instead of `claim_ids` — identical for
  deterministic/LLM edges (where the two were always equal), corrected for
  canonical-relation edges. A raw edge/node that never sets
  `source_claim_ids` at all (legacy/synthetic input) falls back to the
  existing `claim_ids`/`source_records` field — verified via
  `test_legacy_edge_without_source_claim_ids_field_still_works`.
- `activation_scorer_v2.py`: `_local_structure_component` now intersects an
  edge's real `source_claim_ids` (not `claim_ids`) against the alpha's own
  qualifying claim ids, and additionally reports `incident_graph_edge_count`
  / `qualifying_local_edge_count` / `nonqualifying_local_edge_count` /
  `local_edge_exclusion_reasons` — "how many edges touch this alpha" and
  "how many the frozen formula actually counted" are two honest, separate
  numbers.

### Deliberate scope simplification

Section 9's full exclusion-reason taxonomy (`RELATION_NOT_QUALIFYING` vs
`ASSERTION_NOT_QUALIFYING` as separate codes) is collapsed into one combined
code, `RELATION_OR_ASSERTION_NOT_QUALIFYING`, for edges where
`alpha_id in edge.alpha_ids` but the specific qualifying-claim intersection
still fails — disambiguating the two would require re-deriving Activation's
own per-claim relation/assertion qualification a second time at the graph
layer. `LINEAGE_UNRESOLVED` / `LINEAGE_AMBIGUOUS` / `NO_COMMITTED_ALPHA_MATCH`
(the cases that actually explain the diagnosed bug) are fully, separately
reported.

### NVDA acceptance (real run, offline replay)

| | Before | After |
|---|---|---|
| Graph edges with non-empty `alpha_ids` | 0 / 9 | **6 / 9** |
| Alphas with `local_edge_count > 0` | 0 / 10 | **3 / 10** (A101, A103, A304) |
| Canonical relations: lineage resolved | n/a (field didn't exist) | **24 / 24 accepted** (0 unresolved, 0 ambiguous) |

The 3 edges still at `alpha_ids=[]` all carry the honest reason
`NO_COMMITTED_ALPHA_MATCH` (their real source claim genuinely has no
committed Alpha match in `alpha_matches.json` — a legitimate outcome, not a
lineage failure). See `nvda_lineage_repair_before_after.csv`.

**GPU Demand's 4 incident edges**, individually:

| Edge | Source claim (agent) | Alpha linked? | Reason if not |
|---|---|---|---|
| `ai_capex -> gpu_demand` (causal) | 5 real claims (bull_researcher, fundamental_agent, news_agent, risk analysts) | **A103** | — |
| `gpu_demand -> nvda_revenue_growth` (causal) | 2 real claims (aggressive_risk_analyst, fundamental_agent) | **A101** | — |
| `semiconductor_cycle -> gpu_demand` (supportive) | 2 real claims (bull_researcher, aggressive_risk_analyst) | **A201** | — |
| `narrative_momentum -> gpu_demand` (supportive) | 1 real claim (news_agent) | none | `NO_COMMITTED_ALPHA_MATCH` (that specific claim was never committed-matched to any alpha) |

None of GPU Demand's 4 edges are forced onto A301 — A301 legitimately has
`local_edge_count = 0` on this run because none of A301's own 11 committed
claims happen to be the specific claims backing these 4 (or any of the 9)
admitted edges. This is a real, honest "0", not the prior systemic bug.

## 2. Track 2 — Evidence Fact Integrity

### What changed

- New shared module `graph_engine/evidence_fact_index.py`: extracted the
  union-find grouping algorithm (verbatim logic) and signature helpers out
  of `evidence_integrity.py`. Exactly one grouping implementation now
  exists (`group_evidence_candidates` + `relation_triple_index`).
- `evidence_integrity.py` refactored to delegate its own `_group_candidates`
  to the shared function (pure refactor — its own 35 tests pass unchanged,
  proving behavior-preservation).
- `activation_scorer_v2.py`: `_group_evidence` now builds the same
  `EvidenceFactCandidate` shape from qualifying evidence (factors, assertion
  status, semantic polarity, `duplicate_group_id`, relation triple via the
  graph's own `source_claim_ids`) and calls the shared grouper, instead of
  the old exact-normalized-text-only `_semantic_group_key`. Added a safety
  fix to the shared grouper itself: an empty factor signature and an empty
  event signature must never be treated as "matching" each other (discovered
  via a real regression in `test_activation_scorer_v2.py`'s own fixtures —
  see "Fixed during implementation" below).
- Additive output fields on every scored alpha: `raw_supporting_claim_count`,
  `unique_evidence_fact_count`, `distinct_supporting_agent_count`,
  `evidence_overlap_ratio` (`= 1 - unique/raw`, `0` when raw is `0`).
- `run_audit.json` gained an additive `evidence_fact_integrity` section
  (per-alpha raw/unique/agent/overlap, plus `high_overlap_alphas` reusing
  the existing frozen `REGIME_GATE_MIN_UNIQUE_EVIDENCE` threshold — no new
  cutoff invented).

### Fixed during implementation (real regression, real fix)

Wiring the shared grouper into Activation's own test fixtures immediately
exposed a genuine defect in the *shared* algorithm (inherited from
`evidence_integrity.py`, never previously exercised this way): two
completely unrelated claims with **no extracted factors and no event
predicate** both have an empty factor/event signature, and empty strings
trivially equal each other — the priority-3 pass was merging them as if
"same empty signature" meant "same fact." Fixed by requiring at least one
non-empty signature before that pass can fire
(`evidence_fact_index.py`, priority-3 loop). Verified via
`tests/test_structure_integrity_evidence_fact_index.py`.

### Deliberate scope decision: Conflict Detector NOT unified

Section 16/17 asks Conflict Detector to also consume the shared Evidence
Fact Index for bull/bear evidence counting. **This was not implemented.**
Conflict Detector's `_gather_qualifying_evidence` only ever computes a
`_mean_match_score` over its qualifying claims — it has never claimed a
"unique fact count," so it never exhibited the diagnosed double-truth
defect in the first place. `test_conflict_detector.py` is explicitly
spec-frozen (multiple oracle-value tests keyed to the exact current
evidence-strength averaging), and reworking its evidence input to
fact-deduplicated averages would be a substantial, higher-risk change
disproportionate to a defect that was never actually observed there. This
is why Track 2's verdict is **PARTIAL**, not PASS.

### NVDA acceptance (real run, offline replay) — A304 (the exact diagnosed case)

| | Before | After |
|---|---|---|
| Raw supporting claims | 11 | 11 (unchanged — claims are never deleted) |
| Production `unique_evidence_fact_count` | **11** (over-counted) | **5** |
| Shadow `independent_evidence_group_count` | 5 | **5** |
| Production vs. shadow consistent? | **No** (11 vs 5) | **Yes** (5 vs 5) |
| `evidence_overlap_ratio` | not reported | 0.5455 |

This is the exact double-truth the forensic audit found, now closed on the
real run — not a synthetic fixture. Full per-alpha detail in
`nvda_production_shadow_consistency.csv`: **7 of 10** alphas are fully
production/shadow-consistent (A003, A101, A102, A103, A201, A301, A304).

**3 of 10 alphas (A001, A501, A601) still show a raw-claim-count mismatch**
between production and shadow (e.g. A001: production raw=0, shadow raw=1).
This is **not** a grouping-algorithm inconsistency (both layers already use
the identical shared grouper) — it is a **pre-existing, out-of-scope**
difference in which claims each layer considers a *candidate* in the first
place: production's `_gather_qualifying_evidence` requires
`relation in {activation, conditional, mixed}` and `assertion_status !=
negated`; the shadow layer's `_build_candidates` only requires
`is_claim_eligible` + a committed match. Reconciling *eligibility* filters
was not part of this sprint's mandate (which was specifically the grouping
algorithm) and is flagged here as a legitimate follow-up rather than
silently left unmentioned.

### Activation score changes (honest net effect, as required — not forced up or down)

| Alpha | Before | After | Δ | Why |
|---|---|---|---|---|
| A101 | 59.91 (active) | 74.89 (**dominant**) | **+14.99** | Track 1: 2 new real local edges |
| A103 | 35.91 (watch) | 45.91 (watch) | +10.00 | Track 1: 1 new real local edge |
| A201 | 62.57 (active) | 61.21 (active) | −1.36 | Track 2: evidence dedup (6→5 unique facts) |
| A304 | 65.42 (active) | 55.24 (active) | **−10.18** | Track 2: evidence dedup (11→5 unique facts), partially offset by Track 1's +1 local edge |
| A001, A003, A102, A301, A501, A601 | unchanged | unchanged | 0.00 | neither fix touched their specific claims/edges |

Full detail in `nvda_activation_before_after.csv`.

## 3. Track 3 — Numeric Semantic Sanity

### What changed

- `data_sanity/schema.py`: new `SEMANTIC_ROLE_*` constants,
  `DAILY_RANGE_ELIGIBLE_SEMANTIC_ROLES` allowlist, skip-reason constants.
- `reported_price_extractor.py`: every extracted candidate now carries
  additive `semantic_role` / `semantic_role_reason` /
  `daily_range_check_eligible` / `daily_range_skip_reason`. Technical
  vocabulary (SMA/EMA/VWAP/Bollinger/ATR/RSI → `MOVING_AVERAGE`;
  support/resistance/pivot/Fibonacci/technical level/trend
  line/channel → `TECHNICAL_LEVEL`) is matched sentence-locally and marks
  the candidate ineligible for daily-range comparison — it is still
  extracted and reported (never silently dropped), preserving full
  provenance.
- `data_sanity/checker.py`: `check_reported_prices` skips the entire
  mismatch evaluation for any candidate with
  `daily_range_check_eligible is False` (defaults to eligible when the
  field is absent — old artifacts/other callers unaffected). `run_checks`
  gained additive `semantic_role_counts` / `daily_range_eligible_count` /
  `skipped_by_role_count` on the `reported_price_cross_check` check entry.
- `run_audit.json` gained an additive `numeric_semantics` section.

### NVDA acceptance (real run, offline replay)

The exact real claim: *"The 200 SMA has been rising steadily (from $187.6
on June 1 to $192.86 today)..."*

| | Before | After |
|---|---|---|
| Data Sanity warnings | 1 | **0** |
| `$187.60` classification | (none — treated as a generic market price) | `semantic_role = MOVING_AVERAGE`, `daily_range_check_eligible = False`, `skip_reason = TECHNICAL_INDICATOR` |
| `REPORTED_PRICE_OUTSIDE_DAILY_RANGE` warning | **emitted** (relative_difference 8.45%, external_reference=$204.91 = that day's real close) | **not emitted** |
| Dividend info items | 4 (info) | 4 (info) — unchanged |
| `reported_price_cross_check` | evaluated_count=3 (implicit) | evaluated_count=3, `daily_range_eligible_count=2`, `skipped_by_role_count=1`, `semantic_role_counts={"MOVING_AVERAGE": 1, "OBSERVED_MARKET_PRICE": 2}` |

Full before/after in `nvda_data_sanity_before_after.json`.

## Cross-track regression checks

- Claim Coverage: `retained_claim_count`/`analytical_claim_count` computation untouched; unaffected.
- Canonical relation blocks still parse (24 accepted / 4 rejected — unchanged rejection reasons: all 4 are `evidence_not_found`).
- Graph admission guards (self-loop/dangling/invalid-type/invalid-weight/duplicate-merge) untouched — `graph_metrics.rejected_edges` all zero, same as before.
- Activation weights/thresholds/regime-gate constants untouched (byte-identical constants, only grouping semantics of their *inputs* changed, per the sprint's own explicit permission).
- Conflict registry/pairs/admission thresholds/score formula untouched.
- Entity Alpha Exposure: still not wired (`exposure_engine.py` untouched).
- `replay`/`replay-all` Provider call count: unaffected (no LLM-gateway-call-site was touched; `adapt_run_outputs`/`build_extracted_structures_payload` were always called with `llm_gateway=None` in this replay, and the injected DeepSeek prompt-contract code from the prior sprint was not touched at all).
- Source run artifact integrity: `raw_agent_outputs.json` sha256/size/mtime verified byte-identical before and after the replay.

## Completion Matrix

| Requirement | Status |
|---|---|
| Canonical relation lineage resolution (exact/normalized/containment/ambiguous/unresolved) | Done |
| `relation_id` vs `source_claim_ids` separated | Done |
| Graph edge additive lineage fields, merge-preserving | Done |
| `LocalStructureSupport` uses real lineage, not `canrel_*` | Done |
| Systemic "all 10 alphas local_edge_count=0" bug fixed | Done (3/10 now >0 on real data) |
| Shared canonical Evidence Fact Index (single implementation) | Done |
| Production Activation wired to shared index | Done |
| Shadow layer wired to shared index (pre-existing, reconfirmed) | Done |
| Conflict Detector wired to shared index | **Not done** (scoped out, documented) |
| A304 production/shadow double-truth closed | Done (11 vs 5 → 5 vs 5) |
| Numeric `semantic_role` classification | Done |
| `$187.60` false positive resolved | Done (verified on real run) |
| Dividend/corporate-action behavior preserved | Done |
| Additive `run_audit.json` fields (all 3 tracks) | Done |
| Offline NVDA replay, 0 Provider calls, source untouched | Done |
| Full test suite green | Done (2366 passed, 0 failed, 47 skipped) |
| Ruff clean on all changed files | Done |

## Recommended next sprint

1. Reconcile production `_gather_qualifying_evidence`'s eligibility filter
   with the shadow layer's `_build_candidates` filter (the 3/10 alphas
   raw-count mismatch above) — a scoped, single-purpose follow-up.
2. Wire Conflict Detector's bull/bear evidence onto the shared Evidence
   Fact Index, with its own dedicated regression pass over
   `test_conflict_detector.py`'s frozen oracle values.
3. Disambiguate `RELATION_OR_ASSERTION_NOT_QUALIFYING` into the two
   separate codes the spec originally asked for, if per-claim
   relation/assertion visibility at the graph layer is ever needed for its
   own sake.
