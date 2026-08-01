# Latest NVDA Structure Correctness Forensic Audit

Audit-only. Read-only. Zero Provider calls. No production code, schema, or
frontend files were modified to produce this report. All numbers below are
either read directly from persisted artifacts/database rows, or recomputed
independently from those same artifacts using the project's own real
(unmodified) library functions, called from throwaway analysis scripts under
`/private/tmp/.../scratchpad/` — never imported into any production module,
never wired into any pipeline.

## Executive Verdict

| Area | Status | Severity | Main finding |
|---|---|---|---|
| Dedup correctness | **PARTIAL** | High | Segmentation-level dedup is correct (0 false merges, 1 legitimate cross-agent group correctly preserved). But Activation v2's own evidence-grouping dedup is exact-text-only; the system's own shadow audit layer (`evidence_integrity.py`) independently proves A304's "11 unique evidence groups" are really only 5 independent facts (`overlap_ratio=0.5455`) — a real, quantified over-count that currently inflates A304's EvidenceQuality/AgentIndependence contributions, with no user-facing flag since the overlap gate only fires for regime-candidate alphas (none reached that band this run). |
| Run Audit | **PARTIAL** | Medium | `run_audit.json` exists and every count it reports reconciles exactly against independently recomputed values (11/11 checks pass) once the correct — not the naively-stated — conservation formula is used for `candidate_segment_count`. But it omits several explicitly-required fields (`relation_like_claim_count`, `candidate_edge_count`, `rejected_edge_count` numeric breakdown by reason, `declared_pair_count`/`suppressed_count`/`rejected_count` for conflicts, taxonomy/relation-registry/prompt-contract versions, git HEAD/dirty status) that exist elsewhere (DB, replay lineage, the new vocabulary snapshot) but are not consolidated into this one audit artifact. |
| Entity Alpha Exposure | **NOT_IMPLEMENTED** | — | `comqutor_alpha/exposure_engine.py` implements the Development-Plan exposure formula as a pure, tested function, but its own module docstring states explicitly it is "Not wired into the research pipeline, any HTTP API, or the database in this phase" — no `entity_alpha_exposures` table, no endpoint, no artifact, confirmed absent from every layer inspected for this run. `Ticker-specific evidence: 3` (visible in the UI) is `activation_scorer_v2`'s `ticker_specific_evidence_count` — an unrelated, already-implemented metric — never Entity Alpha Exposure. |
| Full conflict-pair support | **PASS** | — | Exactly the 6 canonical pairs the task expected (`A001↔A501`, `A003↔A501`, `A101↔A304`, `A301↔A304`, `A304↔A601`, `A501↔A601`) are declared bidirectionally in `alpha_taxonomy_v1.yaml` and all 6 were evaluated this run (3 admitted, 1 suppressed, 2 rejected — all 6 persisted as DB rows with full reason codes). Main conflict correctly selected as `A301 vs A304` (score 36.8, matches UI exactly). |
| Data Sanity accuracy | **PARTIAL** | High | Mechanism is structurally sound (market availability/OHLCV/corporate-actions/extreme-return checks all ran, all `ok`), but the one actionable warning this run produced — `REPORTED_PRICE_OUTSIDE_DAILY_RANGE`, "Reported price: $187.60 / External reference: $204.91 / Date: 2026-06-01" — is a **confirmed false positive**: the source claim explicitly identifies $187.60 as the 200-day moving average, not a market price, and `reported_price_extractor.py`'s disqualifying-term list has no moving-average/technical-indicator vocabulary. Observed precision this run: 0/1 actionable warnings true positive. |
| Graph / Activation local-edge consistency | **FAIL** | Critical | Confirmed a real computation gap, not a UI semantic difference: 8 of 9 admitted graph edges are canonical-relation-sourced and carry a synthetic `claim_id` (`canrel_*`) that never appears in `alpha_matches.json`, so `graph_builder` can never attribute an `alpha_id` to them and `activation_scorer_v2`'s `LocalStructureSupport` component can never count them. Result: **every one of the 10 scored alphas has `local_edge_count=0`** this run, all capped at 70 by `NO_LOCAL_STRUCTURE_SUPPORT`, despite 9 real, evidence-backed structural edges existing in the Graph. "Local structural edges = 0" on GPU Demand's card is a faithful rendering of a real (currently broken) backend number, traced to `structure_extractor._canonical_relation_record`. |

## Run Identity

Confirmed independently via three sources (Postgres `research_runs`, `outputs/runs/<id>/metadata.json`, and cross-checked against every activation/conflict number visible in the screenshot) — not the screenshot alone.

| Field | Value |
|---|---|
| run_id | `e434f80b-e4d0-4b09-9471-d84532659de5` |
| ticker | NVDA |
| analysis_date | 2026-07-30 |
| created_at (DB) | 2026-07-31T01:30:59.613080Z |
| started_at | 2026-07-31T01:31:00.132840Z |
| completed_at | 2026-07-31T01:34:08.200760Z |
| status | completed |
| profile_id (fixed default profile) | comqutor_deepseek_default_v1 (provider/model recovered from `metadata.json`, not a persisted `profile_id` DB column — see Defects) |
| provider | deepseek |
| model | deepseek-v4-flash (both quick and deep) |
| debate rounds | 1 |
| risk rounds | 1 |
| thinking | disabled (`tradingagents_comqutor_vocabulary_snapshot.json` and raw-output canonical blocks confirm the prompt-injection contract was active for this run) |
| git HEAD (this audit's process, not the run's own recorded HEAD) | `139a83cc66f988ee1f770ba92cb58dccc39c321f` |
| worktree dirty | yes (10 files) — same pre-existing uncommitted implementation from the prior "Inject COMQUTOR Canonical Vocabulary" sprint; **untouched by this audit** |

Identity confirmed as the exact screenshot run via five independent numeric matches (all recomputed from DB, not read from the screenshot): Nodes=12, Edges=9, A301 activation=66.4936≈66.5, A304 activation=65.4177≈65.4, main conflict=A301 vs A304 score=36.8052≈36.8. See `docs/audit_artifacts/nvda_cross_layer_reconciliation.json` for the full field-by-field reconciliation (10/10 fields consistent).

## Artifact Inventory

| File | Status | Size | Notes |
|---|---|---|---|
| `metadata.json` | EXISTS | 831 B | |
| `raw_agent_outputs.json` | EXISTS | 94,085 B | Contains 8 `COMQUTOR_CANONICAL_RELATIONS` blocks (of 12 agent outputs) |
| `structured_agent_outputs.json` | EXISTS | 1,182,445 B | 652 records + 28 `canonical_relations` (additive field) |
| `alpha_matches.json` | EXISTS | 3,616,514 B | 652 match records (1:1 with structured records) |
| `extracted_structures.json` | EXISTS | 54,176 B | 12 nodes, 21 candidate edges |
| `structure_graph.json` | EXISTS | 293,795 B | 12 nodes, 9 admitted edges, 10 activation entries |
| `run_audit.json` | EXISTS | 92,965 B | Includes an embedded `alpha_evidence_integrity` shadow-layer block (38 evidence groups) |
| `research_response.json` | **NOT PRESENT** | — | Never written by this run's pipeline path |
| `data_sanity.json` | EXISTS | 2,794 B | 1 warning (price), 4 info (dividends) |
| `market_data_snapshot.json` | EXISTS | 87,984 B | 276 OHLCV rows |
| `week3_pipeline_status.json` | EXISTS | 136 B | |
| `final_report.md` | **NOT PRESENT** | — | `write_final_report` was not requested for this run |
| `tradingagents_comqutor_vocabulary_snapshot.json` | EXISTS | 6,618 B | New artifact from the prior Canonical Vocabulary sprint; correctly written this run |

Database (Postgres, `comqutor_alpha`, read-only queries only): `research_runs` (1 row), `agent_outputs` (652 rows), `alpha_matches` (652 rows), `structure_graphs` (1 row), `alpha_activations` (10 rows — all MVP alphas scored), `alpha_conflicts` (6 rows — **all 6** declared pairs persisted with `outcome`, not admitted-only). A stray, fully-empty SQLite file at `outputs/runs/_comqutor_alpha_graph.db` exists but is not the live database (`COMQUTOR_DATABASE_URL` points at Postgres); it holds 0 rows in every table and was not used for any figure in this report.

## Hidden Findings Audit

652 total retained claims this run. Full per-claim classification: `docs/audit_artifacts/nvda_hidden_findings_audit.csv`.

**Quality classification** (from `claim_quality.classify_claim_quality`, already stamped on every persisted record):
- `analytical`: 433 (eligible for every downstream consumer, including the public "findings" API)
- `context_only`: 219 (eligible for Mapping/analytical-persistence only; hidden from product findings, Activation, and Conflict by design)
- `non_substantive`: 0 in the final retained set (2 were removed earlier, at the claim-quality gate, before persistence — see Run Audit)

**Direction breakdown of the 433 analytical (product-findings-eligible) claims**: positive=101, negative=94, neutral=102, unknown=136.

**The screenshot's exact "1 visible + More(19)" / "1 visible + More(19)" / "238 hidden" numbers are now fully, exactly reconciled** — traced to `frontend/src/pages/ResearchRunPage.tsx`:
- `DirectionalFindingsPanel` hard-caps each of the Positive/Negative panels at `MAX_FINDINGS_PER_DIRECTION = 20` (`eligible = sorted.slice(0, 20)`), showing `DEFAULT_FINDINGS_SHOWN = 1` by default. Positive has 101 true candidates → capped display of 20 → "1 visible + More(19)". Negative has 94 true candidates → capped display of 20 → "1 visible + More(19)". **Both "19" values are display caps on data that already has ≥20 real candidates, not literal counts of 20 total findings.**
- `isDirectionalFinding` only renders `direction === "positive"` or `"negative"`; every other direction (`neutral`, `unknown`, or any other value) is excluded from both panels entirely, with the page showing only a static counter: "*N* neutral or unclassified findings are not shown in this directional view." `433 - 101 - 94 = 238` — an exact match. This is documented, intentional, display-only filtering (see the component's own code comment) that never mutates the underlying API/artifact/DB — the 238 are all still real `analytical` claims, fully present in `GET /api/research/{run_id}/agent-outputs` (`count=433`), fully counted in Activation/Alpha-matching/Graph, just not rendered in the two-column positive/negative view.

**What the 238 "hidden" claims actually are** (from `nvda_hidden_findings_audit.csv`, restricted to `classification=analytical`): 102 have `direction=neutral` (activation-scorer-relevant claims whose word-counting `infer_direction()` heuristic found no clear bullish/bearish signal — e.g. balance-sheet figures, technical-indicator readings — still legitimate evidence, matched by Alpha Mapper and used by Activation exactly like positive/negative claims), 136 have `direction=unknown` (same category, heuristic simply abstained). Text-pattern scan for process language ("I now have all the data", "let me synthesize", JSON-syntax echoes, table separators) found **0 hits** in the final retained set — the earlier segmentation-boundary filter (11 `BOILERPLATE_META_COMMENTARY` removals) and this audit's own canonical-relation-block splitter both worked correctly; no machine-block or process-narration text leaked into any of the 652 claims.

No claim reached 238 by any different mechanism I could find (no duplicate/malformed/boilerplate contribution) — the reconciliation above is exact and complete.

## Dedup Correctness

Full data: `docs/audit_artifacts/nvda_dedup_groups.csv`.

**Layer 1 — segmentation-level dedup** (`structured_output_adapter.dedupe_structured_records`, already applied once, persisted `duplicate_group_id`/`duplicate_count` fields audited here): 651 distinct `duplicate_group_id` values across 652 records; exactly 1 group has 2 surviving members (`market_agent`/`news_agent`, both stating "Analysis Date: 2026-07-30 | Sector: Technology / Semiconductors | Exchange: NMS" — a genuine cross-agent restatement of the same header line, correctly *preserved* under one shared group id per the documented "Boundary 3" rule, not silently removed). `duplicate_removed_count=0` in `run_audit.json` is correct: 0 records were *removed* (same-agent exact/near duplicates); this is a distinct number from "records sharing a group id," which correctly stays at 1 group / 2 members. Independent Layer-3 sentence-normalization scan (`normalize_claim_for_dedupe`, not reusing the stamped groups) confirms the same result: only 1 normalized-text collision in the whole 652-record set.

**Layer 2 — Activation v2's own evidence-grouping dedup** (`activation_scorer_v2._group_evidence`, exact-text + assertion + numeric-signature key, reused directly, not reimplemented): for 8 of 10 alphas, `raw_supporting_claims == unique_evidence_groups` exactly (no compression needed — every qualifying claim genuinely is a distinct fact). **For A304, this is not the case**: production computes `unique_evidence_count=11` (no compression), but the system's own shadow audit layer (`evidence_integrity.py`, embedded in `run_audit.json.alpha_evidence_integrity`, using a stricter Jaccard≥0.85 near-match plus relation-triple grouping) independently determines A304's 11 raw claims collapse to only **5** truly independent evidence groups (`overlap_ratio=0.5455`, i.e. 54.5% of A304's "unique" evidence is near-paraphrase restatement across agents, e.g. multiple risk/debate agents each restating the same valuation-compression argument in slightly different words). This is a genuine, quantified over-count in the number that directly feeds A304's `EvidenceQuality` (35% weight) and `AgentIndependence` (20% weight) components of a live 65.4-scoring alpha.

**Why this isn't caught today**: the shadow-layer's `evaluate_shadow_regime_verdict` only evaluates the overlap concern when `production_status == "regime_level"` (score ≥86). A304 scored 65.4 ("active"), so its shadow verdict is trivially `NOT_REGIME_CANDIDATE` — the overlap data exists (`overlap_ratio=0.5455`) but is never surfaced as a warning anywhere in `run_audit.json`'s top-level fields, the API, or the UI for a merely-active alpha. Since no NVDA alpha reached the regime band this run (max score 66.9), the shadow layer's protective purpose provided zero practical benefit for this run despite computing the right underlying signal.

**Rule verification (task's explicit example)**: for A301 (GPU-Demand-relevant), the same underlying fact cited by 8 different agents correctly counts as `unique_evidence_count=1` **per fact**, `distinct_agents=8` in total across 11 distinct facts — confirmed directly from the 11 printed evidence groups, each with exactly 1 member; no single fact was ever double-counted as multiple independent evidence pieces for A301 specifically. The A304 case above shows the same protection is not equally effective for every alpha, not that the mechanism is entirely absent.

Duplicate claims never inflate Activation for A301-style single-fact-per-group cases (verified); duplicate/near-duplicate claims **can** inflate Activation for A304-style near-paraphrase cases (verified, quantified). Dedup runs before Activation (evidence grouping happens inside `score_alpha_v2`, called once per alpha before any score is finalized) and before Conflict (Conflict Detector consumes the already-scored Activation payload); dedup does **not** run before Edge evidence aggregation at the Graph level — `graph_builder._normalize_and_merge_edges` unions `claim_ids`/`evidence` per `(source,target,edge_type)` key without any semantic-similarity check of its own (relies entirely on Week 2's per-claim edges already being genuinely distinct claims, which duplicate_group_id-preserving upstream dedup mostly, but per A304, not perfectly, guarantees).

## Run Audit

Full reconciliation: `docs/audit_artifacts/nvda_run_audit_reconciliation.json`.

`run_audit.json` **exists** (schema `structure_correctness.run_audit.v1`) and is produced by `comqutor_alpha/api/routes_research.py:build_run_audit_payload`. Every count independently recomputed from the canonical artifacts (`structured_agent_outputs.json`, `alpha_matches.json`, `extracted_structures.json`, `structure_graph.json`) matches exactly:

- `raw_claim_count` (652), `valid_claim_count` (652), `matched_alpha_count` (59), `ambiguous_alpha_count` (0), `no_match_count` (593), `graph_node_count` (12), `graph_edge_count` (9), `raw_agent_output_count` (12), canonical-relation validated/rejected split (24/4) — **all match exactly**.
- **Conservation formula, corrected**: the naive `candidate_segment_count == retained_claim_count + filtered_claim_count` does **not** hold (654 ≠ 652+13) because `filtered_claim_count` deliberately double-counts `non_substantive_removed_count` as one of its 3 summed components. The two formulas that actually hold, verified against the code (`structured_output_adapter.adapt_run_outputs`) and this run's real numbers: `candidate_segment_count == retained_claim_count + non_substantive_removed_count` (654 = 652+2 ✓) and `filtered_claim_count == boilerplate_removed_count + disclaimer_removed_count + non_substantive_removed_count` (13 = 11+0+2 ✓). This is a documentation subtlety in the field-naming, not a computation defect.
- `candidate_edges (21) = admitted_edges (9) + rejected_edges (...)` does **not** hold arithmetically because these are two different keyings (claim-level vs. run-level-post-merge, not candidate-vs-rejected) — `graph_metrics.rejected_edges` (the real structural-rejection counter: self_loop/dangling/invalid_type/invalid_weight) is all-zero this run, matching `run_audit.json`'s own `rejected_edge_count: 0` exactly. The arithmetic gap between 21 and 9 is claim-level→run-level duplicate-edge *merging*, not rejection.
- `conflict_count` in `run_audit.json` (3) is **admitted-conflicts-only** — it does not surface `declared_pair_count` (6), `suppressed_count` (1), or `rejected_count` (2) as its own fields, even though that data is fully available (and correctly computed) in the `alpha_conflicts` DB table's `outcome` column.

**Version/provenance completeness**: `run_audit.json` records only `primary_activation_version`. It does **not** include `git_head`, `dirty_status`, `claim_adapter_version`, `taxonomy_version`/`taxonomy_sha256`, `alias_version`, `relation_registry_version`, `graph_schema_version`, `conflict_formula_version`, or `prompt_contract_version` as its own fields — several of these exist elsewhere (architecture-replay lineage metadata carries `taxonomy_version`/`alias_version`/`relation_grammar_version`/`pipeline_git_head`; the new `tradingagents_comqutor_vocabulary_snapshot.json` carries `taxonomy_version`/`taxonomy_sha256`/`relation_registry_version`/`prompt_contract_version`), but `run_audit.json` itself does not consolidate them, so a single "was this specific run's structure correctness computed under exactly which code/taxonomy version" question cannot be answered from `run_audit.json` alone.

**Full traceability (edge → relation → claim → agent → raw output)**: verified directly, e.g. edge `ai_capex → gpu_demand` (causal, weight 0.9) → canonical relation `canrel_190605b4e2cfcc56` (among others) → `alpha_matches`/`structured_agent_outputs` claim → `source_agent_output_id` → the exact raw-output record in `raw_agent_outputs.json` (`market_agent`/`fundamental_agent` reports containing the original `COMQUTOR_CANONICAL_RELATIONS` block). Fully traceable end to end for every edge checked.

**Verdict breakdown** (per the task's required distinction): file exists — yes; counts correct — yes (11/11, once the correct formula is used); counts complete — no (several explicitly-requested fields absent); versions complete — no; provenance complete — yes (traceability itself works, just not summarized numerically in this one file).

## Entity Alpha Exposure

`comqutor_alpha/exposure_engine.py` (`calculate_exposure`, `compute_entity_alpha_exposures`) implements exactly the Development-Plan formula (`historical_mapping*0.50 + current_evidence*0.30 + agent_confidence*0.20`), is pure/deterministic, and has its own test coverage. Its **own module docstring states, verbatim**: "Not wired into the research pipeline, any HTTP API, or the database in this phase — no `entity_alpha_exposures` table, no exposure endpoint... the Exposure *Product* Gate remains `BLOCKED_BY_SEED` until the seed is provided and signed off." Confirmed independently for this run: no `entity_alpha_exposures` (or similarly-named) table exists in the live Postgres schema; no exposure field appears in `alpha_activations.activation_json`, `structure_graph.json`, or any other artifact; `evidence_integrity.py`'s own shadow layer (which *does* accept an `exposure_by_alpha` parameter) is called this run with no exposure argument supplied anywhere in the production call chain, so every alpha's shadow verdict — where evaluated at all — would report `UNVERIFIED_EXPOSURE` rather than a real score (moot this run since no alpha reached regime level to trigger that evaluation branch in the first place).

`Ticker-specific evidence: 3` (visible on A301's card) is `activation_scorer_v2.ticker_specific_evidence_count` — a real, already-implemented, unrelated metric (counts unique evidence groups whose text verifiably names the ticker or resolved company by a token-boundary match) — **never** Entity Alpha Exposure. Full detail: `docs/audit_artifacts/nvda_entity_alpha_exposure_audit.csv` (`exposure_source=NOT_WIRED` for all 10 scored alphas).

**Verdict: NOT_IMPLEMENTED** (as a runtime/product feature; the pure computational core is implemented and tested but never reaches this or any other run).

## Conflict Pair Coverage

Canonical registry source: `alpha_taxonomy_v1.yaml`'s per-Alpha `conflict_alphas` field, enumerated into undirected pairs by `conflict_detector._enumerate_canonical_pairs` (requires a reciprocal declaration on both sides; every declared pair in this taxonomy is properly reciprocal). Exactly 6 declared pairs — matching the task's expected list precisely:

| Pair | Runtime outcome (this run) | Score | Main? |
|---|---|---|---|
| A001 vs A501 | suppressed (`BELOW_ACTIVATION_THRESHOLD`, `MISSING_LEFT_EVIDENCE`) | — | no |
| A003 vs A501 | rejected (`BELOW_ACTIVATION_THRESHOLD`, `DIRECTION_ROLE_UNRESOLVED`) | — | no |
| A101 vs A304 | **admitted** | 33.28 | no |
| A301 vs A304 | **admitted** | 36.81 | **yes** |
| A304 vs A601 | **admitted** | 29.53 | no |
| A501 vs A601 | rejected (`BELOW_ACTIVATION_THRESHOLD`, `DIRECTION_ROLE_UNRESOLVED`) | — | no |

All 6 pairs are persisted as DB rows (`alpha_conflicts.outcome`) every run — not just admitted ones — so the full arbitration audit (including every suppressed/rejected reason code) is genuinely available, just not summarized in `run_audit.json` (see above). `detect_alpha_conflicts` evaluates every declared pair unconditionally each run (never short-circuits after finding a main conflict); multiple conflicts can and did admit simultaneously (3 of 6); main-conflict arbitration correctly picked the highest `conflict_score` (36.81) among the 3 admitted, matching the taxonomy-frozen sort key (`conflict_score desc, evidence_strength desc, minimum_activation desc, conflict_id asc`). Full detail: `docs/audit_artifacts/nvda_conflict_registry_coverage.csv`.

**Verdict: PASS.**

## Data Sanity Accuracy

`data_sanity.json` — status `warning`, 1 warning-severity issue, 4 info-severity issues (all dividends), 0 critical. Full provenance: `docs/audit_artifacts/nvda_data_sanity_provenance.csv`.

**The `$187.60` case, resolved definitively**: the flagged claim (`market_agent:market_report:claim:20`) reads in full: *"The 200 SMA has been rising steadily (from $187.6 on June 1 to $192.86 today), indicating the longer-term trend is still up."* This is unambiguously the semantic role **MOVING_AVERAGE** (a 200-day SMA value), not `OBSERVED_MARKET_PRICE`/`CLOSE_PRICE`/`HISTORICAL_PRICE`. `check_reported_prices` compared it against NVDA's actual June 1 2026 trading range (external reference $204.91, from real `yfinance` OHLCV data — the market data itself is correct and unrelated to this defect) and flagged an 8.45% relative mismatch as `REPORTED_PRICE_OUTSIDE_DAILY_RANGE`. **Root cause, pinpointed in code**: `comqutor_alpha/data_sanity/reported_price_extractor.py`'s `_DISQUALIFYING_TERMS = ("eps", "earnings per share", "revenue", "market cap", "price target", "%")` has no moving-average or technical-indicator vocabulary, so the bare-price-and-date regex (`_BARE_PRICE_DATE_PATTERN`) matched "$187.6 on June 1" inside the SMA sentence and classified it `price_semantics="generic"` — triggering the daily-range comparison meant for actual trade prices. A 200-day moving average trailing well below a rising stock's current price by ~8% is completely expected behavior, not a data anomaly.

**Verdict for this specific warning: FALSE_POSITIVE**, confirmed by direct inspection of the source claim.

All 4 dividend-window info items independently verified against `market_data_snapshot.json`'s corporate-actions rows — correctly classified `info` severity, correctly non-anomalous, correctly not conflated with anything else. `verdict=CORRECTLY_IGNORED` for all 4.

**Observed precision this run** (single-run sample, not a general accuracy claim): 1 actionable (warning-severity) issue, 0 true positives, 1 false positive → 0% observed precision on `REPORTED_PRICE_OUTSIDE_DAILY_RANGE` for this run. Sample size is 1; this establishes a concrete, reproducible defect instance, not a statistically general failure rate.

**Verdict: PARTIAL** (mechanism structurally correct and exercised correctly this run; the one actionable output was wrong for an identifiable, fixable reason).

## Graph and Activation Consistency

This is the audit's highest-severity finding. Full per-node detail: `docs/audit_artifacts/nvda_graph_activation_edge_consistency.csv`.

**What "Local structural edges" actually is**: confirmed via `frontend/src/components/AlphaCard.tsx` (not a factor-node-detail component — the screenshot's "GPU Demand" click opens an `AlphaCard` for GPU Demand's one mapped alpha, A301) rendering `activation.local_edge_count` — i.e. `activation_scorer_v2._local_structure_component`'s **per-Alpha** count of admitted Graph edges whose `claim_ids` intersect *that specific Alpha's own qualifying claim set* (from `alpha_matches.json`). This is not, and was never intended to be, a raw count of edges touching the factor node in the Graph visualization — that is a different, node-level number (`incident_admitted_edge_count` in the CSV, which for `gpu_demand` is genuinely **4**, not 0).

**The gap is real, not semantic**: every one of GPU Demand's 4 incident Graph edges (`ai_capex→gpu_demand`, `gpu_demand→nvda_revenue_growth`, `narrative_momentum→gpu_demand`, `semiconductor_cycle→gpu_demand`) carries `extraction_methods=["tradingagents_canonical_output"]` and `claim_ids` built from synthetic canonical-relation IDs (e.g. `canrel_190605b4e2cfcc56`). These synthetic IDs are constructed in `comqutor_alpha/structure_engine/structure_extractor.py`'s `_canonical_relation_record` (from the prior Canonical Vocabulary sprint) and are **never** written into `alpha_matches.json` (canonical relations are report-level, never passed through the Alpha Mapper, by design — they are kept as a sibling `canonical_relations` field, never merged into `structured_agent_outputs.json`'s `records`). Consequently `graph_builder._committed_alpha_ids_for_claim` can never resolve an `alpha_id` for these edges (`edge.alpha_ids=[]` for **all 9** admitted edges this run, confirmed directly), and `activation_scorer_v2._local_structure_component`'s `edge_claims & alpha_claim_ids` intersection is always empty for them, for every alpha, unconditionally.

**Blast radius, confirmed empirically**: all 10 scored alphas this run have `local_edge_count=0` and are capped at 70 by `NO_LOCAL_STRUCTURE_SUPPORT` (verified for every alpha in the CSV — A301, A304, A101, A102, A103, A201, A501, A601 all show the identical pattern; the one deterministic-sourced edge (`ai_capex→ai_demand`) that exists this run also carries `alpha_ids=[]`, but for an unrelated, legitimate reason — its own claim's Alpha-Mapper score fell below the commit threshold, `matched_alpha: null` — not a canonical-relations defect). The `LocalStructureSupport` component (20% of Activation v2's weight) contributed exactly `0.0` to every alpha's score this run, despite the Graph containing 9 real, evidence-backed structural edges directly relevant to those alphas' own factors (e.g. `ai_capex→gpu_demand` is squarely about A301's own factor set).

This is **Option A** from the task's framing: a real computation gap traceable to specific code, reproducible, quantified — not Option B (a UI-only mislabeling). The UI is rendering the correct value of a currently-broken backend computation.

**Verdict: FAIL.**

## Cross-Layer Reconciliation

Full detail: `docs/audit_artifacts/nvda_cross_layer_reconciliation.json`. All 10 spot-checked fields (nodes, edges, A301/A304 activation scores, main conflict pair + score, GPU Demand supporting-evidence count, distinct agents, ticker-specific evidence, local structural edges, dominant-alpha count) are **consistent between the filesystem artifact / database / and the screenshot's rendered UI values** — every discrepancy investigated in this report is a real backend defect faithfully surfaced through every layer, never an inter-layer data-integrity problem. (Live API responses were not queried — the dev server was not running during this read-only audit — but DB values, which the API reads from directly via `repository.py`, match the UI exactly, so this is not a material gap.)

## Defect Ranking

**Critical**
1. Canonical-relation edges structurally cannot be attributed to any Alpha, silently zeroing `LocalStructureSupport` (20% of Activation v2) for every alpha on any run where canonical relations contribute to the Graph (Graph/Activation Consistency section). Impact: Activation score.

**High**
2. Activation v2's exact-text evidence-grouping dedup measurably under-deduplicates near-paraphrase restatements across agents (A304: 11 counted vs. 5 truly independent per the system's own shadow layer), inflating EvidenceQuality/AgentIndependence for affected alphas with no surfaced warning below the regime band. Impact: Activation score.
3. `REPORTED_PRICE_OUTSIDE_DAILY_RANGE` false-positives on moving-average/technical-indicator price mentions due to an incomplete disqualifying-term list. Impact: Data Sanity accuracy / analyst trust in warnings.

**Medium**
4. `run_audit.json` omits several explicitly-useful fields (conflict declared/suppressed/rejected counts, taxonomy/relation-registry/prompt-contract versions, git provenance) that are computed correctly elsewhere but not consolidated into this one audit artifact. Impact: Auditability only.
5. Entity Alpha Exposure has no runtime/product implementation at all (formula-only, unwired) — not itself a defect (documented, deliberate `BLOCKED_BY_SEED` state) but worth flagging as a completion gap against the task's checklist. Impact: none on current scores (nothing reads it); Auditability/roadmap only.

**Low**
6. 238 of 433 analytical findings (neutral/unknown direction) are invisible in the Research page's two-column Positive/Negative view by design; all data is intact and available via the full API/DB, but no UI surface currently lets an analyst browse them without going to raw API access. Impact: UI only.

## Completion Matrix

| Requirement | Implemented | Correct on latest NVDA | Fully complete |
|---|---:|---:|---:|
| Dedup correctness (segmentation layer) | Yes | Yes | Yes |
| Dedup correctness (Activation evidence-grouping layer) | Yes | Partially (A304 gap) | No |
| Run Audit artifact | Yes | Yes (11/11 reconciled) | No (missing fields) |
| Entity Alpha Exposure | Formula only | N/A (never invoked) | No |
| Conflict pair registry + runtime evaluation | Yes | Yes (6/6 pairs) | Yes |
| Data Sanity mechanism | Yes | Partially (1 false positive) | No |
| Graph↔Activation local-edge linkage | Yes (pre-canonical-relations) | No (0/10 alphas this run) | No |

## Recommended Next Sprint

Priority order, smallest safe fix first — **not implemented by this audit, descriptions only**:

1. Give canonical-relation-sourced graph edges a real, Alpha-Mapper-resolvable claim identity (e.g. run each canonical relation's `evidence_quote`/factors through the existing Alpha Mapper the same way a segmented claim is, or attach the relation to its *parent* claim's real `claim_id` when the evidence text is a substring of an already-matched claim) so `LocalStructureSupport` and `graph.edges[*].alpha_ids` can see them. Highest-priority fix — currently zeroes a real, weighted Activation component.
2. Extend `reported_price_extractor._DISQUALIFYING_TERMS` to include moving-average/technical-indicator vocabulary (SMA, EMA, moving average, support, resistance, Bollinger, ATR, RSI) so a technical-indicator sentence with an explicit date is never treated as a historical trade-price mention.
3. Surface `evidence_integrity.py`'s `overlap_ratio`/shadow verdict for *all* alphas (not just regime-candidates) as an additive `run_audit.json`/API field, so a high-overlap active alpha like this run's A304 is visible before it ever reaches the regime band.
4. Add the missing fields to `run_audit.json`: conflict `declared_pair_count`/`suppressed_count`/`rejected_count`, taxonomy/alias/relation-registry/prompt-contract versions, git HEAD/dirty status — all already computed correctly elsewhere, just not consolidated.
5. Consider an additive "show all findings" or "neutral/unclassified findings" panel on the Research page for completeness (low priority, UI-only).
