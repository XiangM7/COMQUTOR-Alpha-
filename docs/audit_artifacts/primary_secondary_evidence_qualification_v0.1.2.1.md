# Primary vs Secondary Evidence Qualification — v0.1.2.1 (Step 6)

**Evidence qualification for activation-input eligibility only.** Does not change B1's five stance labels (or reinterpret them by role), Alpha Mapper semantic meaning, Alpha taxonomy, conflict ontology, regression labels, or any B2/B4 threshold **value** — only which evidence inputs are eligible to feed those unchanged formulas.

Branch `comqutor-structure-layer`, HEAD `9f228723fad5406c72e62beca67ec70ea0fdb004` (unchanged — no commit, no push). Zero Provider calls, zero TradingAgents calls — reads only the healthy Step 5 persisted six-ticker semantic outputs (`outputs/runs/_step5a_coverage_{nvda,qqq,msft,sndk,tsm,amd}/alpha_matches.json`).

## Design

**One centralized source-role authority**: `comqutor_alpha/graph_engine/evidence_source_role.py`. Agent → role mapping, verified against the real fresh six-ticker source data (Section 3), not assumed:

| Role | Agents |
|---|---|
| PRIMARY_RESEARCH | `fundamental_agent`, `market_agent`, `sentiment_agent`, `news_agent` |
| SECONDARY_DECISION_OR_DEBATE | `bear_researcher`, `bull_researcher`, `conservative_risk_analyst`, `neutral_risk_analyst`, `aggressive_risk_analyst`, `research_manager`, `trader`, `portfolio_manager` |
| UNKNOWN (default-deny) | any other/future agent name |

**Policy** (per Evidence Fact group, after the existing canonical grouping — `evidence_fact_index.group_evidence_candidates` — never a second grouping algorithm):

- Group contains ≥1 PRIMARY_RESEARCH member → that member is `PRIMARY_QUALIFIED` (eligible, existing rules unchanged); any SECONDARY member in the **same** group is `SECONDARY_DUPLICATE_OF_PRIMARY` (ineligible — cannot double-count a fact already carried by Primary).
- Secondary-only group: not ticker-specific (reusing the existing, unmodified `activation_scorer_v2._is_ticker_specific`) → `SECONDARY_NOT_TICKER_SPECIFIC`. Ticker-specific **and** `relation=="activation"` **and** `assertion_status=="asserted"` (the two strongest already-existing fields every consumer already uses to gate all evidence — reused, never a new keyword classifier) → `SECONDARY_QUALIFIED_CAUSAL_EVIDENCE` (eligible). Otherwise → `SECONDARY_CAUSALITY_UNPROVEN` (ineligible, conservative default).
- UNKNOWN role → always `UNKNOWN_SOURCE_ROLE` (ineligible).
- Role is **never** a score multiplier — binary eligibility + reason code only.

**Wired into**: `activation_scorer_v2.score_alpha_v2` (filters the groups feeding EvidenceQuality/AgentIndependence/TickerSpecificity/caps/regime-gate; raw unfiltered data stays visible in `evidence_fact_groups[*].members_source_role_detail` for audit) and `conflict_detector._evaluate_candidate` (via a new `_qualify_and_filter_evidence`, filtering the claim pool that feeds B2's `unique_fact_count`/evidence strength/admissibility before it ever reaches `evaluate_conflict_admissibility`).

## Headline Before/After Results

| Metric | Before | After | Change |
|---|---|---|---|
| Unique evidence facts feeding activation (sum, all 6 tickers × 10 alphas with any evidence) | 1145 | 623 | **−45.6%** |
| Active alphas (status ≠ inactive, sum across 6 tickers) | 46 | 38 | **−8** |
| Admitted B2 conflicts (sum across 6 tickers) | 16 | 8 | **−8** |

This is the intended effect — activation was inflated by Secondary agents restating Primary facts. Thresholds/formulas are byte-identical; only the evidence inputs changed.

## Per-Ticker Evidence-Fact Totals

| Ticker | Before | After |
|---|---|---|
| NVDA | 203 | 111 |
| QQQ | 171 | 83 |
| MSFT | 168 | 78 |
| SNDK | 178 | 104 |
| TSM | 227 | 127 |
| AMD | 198 | 120 |

(Full per-alpha detail in the JSON artifact's `before_after_evidence_fact_counts.per_ticker_per_alpha_detail`.)

## Activation Status Changes (selected)

| Ticker | Alpha | Status before | Status after | Score before | Score after |
|---|---|---|---|---|---|
| TSM | A103 | active | watch | 54.09 | 31.02 |
| TSM | A501 | active | watch | 54.42 | 31.31 |
| TSM | A601 | active | watch | 60.67 | 48.55 |
| AMD | A201 | watch | inactive | 30.64 | 29.82 |
| AMD | A003 | inactive | inactive | 18.88 | **0.00** |

AMD A003's two supporting claims were both Secondary-only and failed the causal-evidence bar — activation evidence for that alpha/ticker goes to zero. Full per-ticker/per-alpha detail (only rows where score or status changed) is in the JSON artifact.

## B2 Conflict Admissibility Impact

| Ticker | Admitted before | Admitted after | Main conflict before | Main conflict after |
|---|---|---|---|---|
| NVDA | 3 | 3 | A101\_\_A304 | A101\_\_A304 |
| QQQ | 3 | 1 | A301\_\_A304 | A304\_\_A601 |
| MSFT | 1 | **0** | A101\_\_A304 | **null** |
| SNDK | 3 | **0** | A101\_\_A304 | **null** |
| TSM | 3 | 2 | A101\_\_A304 | A101\_\_A304 |
| AMD | 3 | 2 | A101\_\_A304 | A101\_\_A304 |

**MSFT and SNDK's only/all previously-admitted conflict pairs relied on Secondary-inflated evidence** — after qualification, neither ticker has any admitted conflict (`main_conflict` becomes `null`). B2's own thresholds (score ≥ 50, ≥ 2 unique supports_alpha facts per side, ≥ 1 ticker-specific fact per side) are unchanged in value — confirmed by a pinned test.

## Duplication/Inflation Audit

13 Evidence Fact groups found across the six tickers where a Secondary agent restated a fact already carried by a Primary agent within the same canonical group (already deduped to 1 fact by the existing grouping both before and after — what changes is that the Secondary agent's identity no longer counts toward `agent_independence`/`cross_agent_confirmation`). Examples:

| Ticker | Alpha | Primary source | Secondary restatement(s) |
|---|---|---|---|
| MSFT | A301 | fundamental_agent | aggressive_risk_analyst, bear_researcher, neutral_risk_analyst, research_manager |
| TSM | A101 | news_agent, sentiment_agent | bear_researcher |
| QQQ | A103 | news_agent | aggressive_risk_analyst, bull_researcher |
| NVDA | A101 | news_agent | bull_researcher |

Full list of 13 in the JSON artifact's `duplication_inflation_audit.examples`.

## Qualification Reason Counts (aggregate, all 6 tickers)

| Reason | Count |
|---|---|
| PRIMARY_QUALIFIED | 584 |
| SECONDARY_NOT_TICKER_SPECIFIC | 504 |
| SECONDARY_QUALIFIED_CAUSAL_EVIDENCE | 65 |
| SECONDARY_CAUSALITY_UNPROVEN | 30 |
| SECONDARY_DUPLICATE_OF_PRIMARY | 21 |

65 Secondary claims did genuinely qualify as independent causal evidence — Step 6 does not delete Secondary agents' value, it only stops unqualified restatement/recommendation from inflating counts a Primary fact already covers (or that no evidence at all backs).

## Invariants Verified

- B1's five stance labels: unchanged, never reinterpreted by role.
- Alpha Mapper semantic prompt / taxonomy / conflict ontology / regression labels: unchanged.
- B2 thresholds (`ALPHA_SCORE_THRESHOLD=50.0`, `MIN_SUPPORTING_EVIDENCE_PER_SIDE=2`, `MIN_TICKER_SPECIFIC_SUPPORT_PER_SIDE=1`) and B4/Activation-v2 constants (`AGENT_COVERAGE_DENOMINATOR=3`, `CROSS_AGENT_CONFIRMATION_DENOMINATOR=2`) unchanged in value — pinned by `test_15_b2_and_b4_threshold_constants_are_unchanged_in_value`.
- Role is never a score multiplier — binary eligibility + reason code only.
- Unknown/future agents default-deny, never silently PRIMARY.
- Primary evidence remains fully auditable; every group's `members_source_role_detail` exposes every member (Primary and Secondary, eligible and ineligible) — nothing deleted.
- Evidence artifact schema stays backwards-readable: only four additive fields (`source_agent`, `source_role`, `activation_eligible`, `activation_qualification_reason`); no existing key removed or renamed.

## Tests

16 new deterministic tests in `tests/test_evidence_source_role_qualification.py` (role-authority unit tests, group-level duplicate-of-primary protection, end-to-end Activation v2 integration, end-to-end Conflict Detector/B2 integration, role-is-not-a-multiplier checks, schema-backwards-compatibility checks, threshold-value pins) — all passing.

**Full offline suite run twice** (before and after applying the fixes below): a first full run surfaced 22 failures; a clean confirmation re-run after all fixes landed **3761 passed / 6 failed / 47 skipped / 69 subtests passed in 673.67s** — the 6 remaining failures are name-for-name identical to the pre-existing/expected failures independently root-caused below (determined before this confirmation run finished). Zero failures attributable to Step 6. All fixes were either (a) updating a test's synthetic/mismatched agent-name literal to a real registered agent — the same established pattern already used for `test_activation_scorer_v2.py`/`test_conflict_admissibility.py` — or (b) one genuine, minimal correctness fix in `activation_scorer_v2.py` itself.

**One genuine pre-existing bug found and fixed**: `score_alpha_v2`'s `direction_consistency` component contribution was never gated on `has_qualifying_evidence` (only `recency` was) — latent since an empty raw evidence pool almost always implied an empty direction-evidence pool too (both drew from closely related qualifying-claim sources). Step 6 qualification can now legitimately leave `qualified_groups` empty while the separate, broader direction-evidence pool (`_gather_direction_evidence`, itself unfiltered by role) still has entries — surfacing a case where `components` no longer summed to `activation_score`. Fixed by gating `direction_consistency`'s contribution the same way `recency`'s already was. Formula/weights unchanged; this only makes the zero-evidence case correctly report zero.

**One pre-existing fixture naming inconsistency found and fixed**: `scripts/w5_demo_fixtures.py` labeled its 4th NVDA/QQQ demo claim `"technical_agent"`, which never matched `DEMO_SELECTED_ANALYSTS = ("market", "news", "fundamentals", "sentiment")` — renamed to `"market_agent"` (the analyst it was actually meant to represent).

**Test fixtures updated** (synthetic agent-name literals only, no assertion values changed): `tests/test_activation_scorer_v2.py`, `tests/test_conflict_admissibility.py`, `tests/test_conflict_evidence_fact_integration.py`, `tests/test_b2_admissibility_integration.py` — `agent_x`/`analyst_one`/`fundamentals_agent`/`second_bear_agent`/per-claim `f"agent_{claim_id}"`/etc. → real `market_agent`/`fundamental_agent`/`sentiment_agent`/`news_agent`.

**One documented, non-breaking persistence gap**: the new `evidence_qualification` diagnostic field is dropped by the Week4 DB whitelist layer (`comqutor_alpha/storage/db/week4_persistence.py` explicitly whitelists every persisted field). Not a data-loss bug — nothing currently reads this field back from the DB — but `tests/test_week4_persistence.py` (2 tests) and `tests/test_b2_admissibility_integration.py` (1 test) needed their API-vs-DB-reconstruction equality checks updated to strip this one additive field first, matching this codebase's established convention for other additive fields (e.g. `bull_evidence`/`bear_evidence`).

**Remaining failures, confirmed unrelated to Step 6** (verified by checking `raw_supporting_claim_count`/`raw_unique_evidence_fact_count` — computed by `_gather_qualifying_evidence`/`_group_evidence`, both fully unmodified by Step 6 — is independently 0 before any qualification is even applied):
- `tests/test_artifact_export_and_api.py::test_replay_conflict_does_not_get_run_id_mismatch` and `tests/test_evidence_review_sample.py::test_60_sample_includes_conflict_and_activation_evidence` — Architecture Replay of specific historical runs produces zero raw qualifying evidence for every alpha even under pre-Step-6 logic; a replay-pipeline issue (most likely from Step 5A's `week2_llm.py` task/prompt rework changing the replay-cache lookup shape), not Step 6.
- `tests/test_w5_demo_seed.py` (2 tests) — already documented as pre-existing in project memory since 2026-08-14, predating this whole session; this fixture's 4 agents are all `PRIMARY_RESEARCH` and qualify unconditionally, so Step 6 cannot be the cause.
- `tests/test_j3_semantic_benchmark_j2_v0_2.py::test_e42_head_unchanged_from_session_frozen_starting_commit` — hardcodes an old session's git HEAD; fails identically regardless of what any segment changes.

**One expected, legitimate hash-drift, not reverted**: `tests/test_msft_a102_a304_taxonomy_adjudication.py::TestSectionAAllOutcomes::test_a6_b1_b2_b3_b4_invariant_modules_are_byte_identical` pins `conflict_detector.py`'s SHA-256 to guard an unrelated, already-completed task against accidental B1-B4 changes. Step 6 legitimately, explicitly-authorizedly modified `conflict_detector.py` — this correctly trips the pinned hash. Per established project precedent, reported honestly here; the guard itself is left untouched, not reverted or silently re-pinned.

## Files

**Created:** `comqutor_alpha/graph_engine/evidence_source_role.py`, `docs/audit_artifacts/primary_secondary_evidence_qualification_v0.1.2.1.json`, this file, `tests/test_evidence_source_role_qualification.py`.
**Modified:** `comqutor_alpha/graph_engine/activation_scorer_v2.py`, `comqutor_alpha/conflict_engine/conflict_detector.py`, `scripts/w5_demo_fixtures.py`, `tests/test_activation_scorer_v2.py`, `tests/test_conflict_admissibility.py`, `tests/test_conflict_evidence_fact_integration.py`, `tests/test_b2_admissibility_integration.py`, `tests/test_week4_persistence.py`.
**Updated (additive):** `docs/audit_artifacts/qa_closure_index.json` (`step_6` block).
**Not touched:** B1 stance module, Alpha Mapper, Alpha taxonomy, conflict ontology, regression labels, B2/B4 threshold constants, any real production run artifact under `outputs/runs/` (only read).
**Provider calls:** 0. **TradingAgents calls:** 0. **Commit:** NO. **Push:** NO.
