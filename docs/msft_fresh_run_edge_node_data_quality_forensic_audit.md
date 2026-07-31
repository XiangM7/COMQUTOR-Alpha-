# MSFT Fresh Run Edge, Node Detail, and Data Quality Forensic Audit

**Audit type:** READ-ONLY FORENSIC AUDIT. No production code, tests, or configuration were modified. No historical artifact was written to. No database write occurred. No TradingAgents/LLM/Provider/network call was made. See Section H for full validation evidence.

---

## A. Target Run Identification

```
git branch --show-current -> comqutor-structure-layer
git rev-parse HEAD        -> 2fe129705d824d46b4bcf7f0fc1eb43e27972824  (unchanged throughout this audit)
git status --short        -> unchanged from the two pre-existing uncommitted sprints already in this
                              worktree (17 modified + untracked files); nothing further modified
git diff --check          -> exit 0, no whitespace errors
```

Only one MSFT run exists anywhere in the system (filesystem, and the real Postgres database configured
via `.env`'s `COMQUTOR_DATABASE_URL`). It is unambiguous:

| Field | Value |
|---|---|
| run_id | `61f3e019-63a8-4c56-b763-057208d5efae` |
| ticker | MSFT |
| analysis_date | 2026-07-27 |
| created_at (DB) | 2026-07-28T00:43:39.396Z |
| started_at (DB) | 2026-07-28T00:43:40.151Z |
| completed_at (DB) | 2026-07-28T01:08:55.121Z |
| run status (DB) | `completed` |
| selected analysts | market, sentiment, news, fundamentals |
| profile_id (research_run_progress) | `comqutor_anthropic_medium_sonnet46_v1` |
| cache disposition | Not a persisted field on `research_runs`; `active_fingerprint` is `NULL`, which is the normal, expected state for any *terminal* (completed/failed) run -- `active_fingerprint` is cleared unconditionally on completion (`repository.py`, in-flight-dedup only). No separate "cache disposition" record exists for a run after the fact; that value is only ever present in the original synchronous POST response, which is not persisted. |
| run directory | `outputs/runs/61f3e019-63a8-4c56-b763-057208d5efae/` |
| database row exists | Yes -- `research_runs`, `research_run_progress`, `agent_outputs` (660 rows), `alpha_matches` (660 rows), `structure_graphs` (1 row), `alpha_activations` (10 rows), `alpha_conflicts` (6 rows) |

This run is also the single most recently created row in `research_runs` across every ticker in the
database (the next most recent is an AMD run from 2026-07-24). Filesystem mtimes for every artifact in
the run directory (all `Jul 27 18:08:4x`-`18:08:55` local time) are consistent with the DB's UTC
timestamps. **This is unambiguously the fresh MSFT run; no BLOCKED state was needed.**

The real production database is **PostgreSQL** (`postgresql+psycopg://...@127.0.0.1:5433/comqutor_alpha`,
from `.env`'s `COMQUTOR_DATABASE_URL`), not the empty `outputs/runs/_comqutor_alpha_graph.db` SQLite
fallback file that exists alongside the run directories (that file has zero rows in every table --
it is simply the unused local-dev fallback that `resolve_database_url()` would create if the env var
were absent; it is not what actually served this run). All DB reads in this audit went through the
real Postgres database via `COMQUTOR_DATABASE_URL`, using the project's own `psycopg` driver -- read-only
`SELECT`s only.

---

## B. Artifact Integrity Inventory

| Artifact / table | Present | Record count | Schema version | ticker/run_id match | Notes |
|---|---|---|---|---|---|
| `metadata.json` | Yes | -- | -- | Yes | 12 agents, `output_version: week1a.raw_agent_outputs.v1` |
| `raw_agent_outputs.json` | Yes | 12 agent outputs | `week1a.raw_agent_outputs.v1` | Yes | |
| `structured_agent_outputs.json` | Yes | 660 records | `week1a.structured_agent_outputs.v2` | Yes | **Byte-for-byte reproduced** from `raw_agent_outputs.json` by calling the real, unmodified `adapt_run_outputs()` in an isolated read-only scratch copy -- 660/660 claim_ids identical and in the same order, 0 field mismatches on `claim`/`evidence`/`claim_quality`/`factors`/`entities`/`direction`/`assertion_status`. This is strong, empirical proof the on-disk artifact is exactly what current production code produces from its own raw input (no drift, no stale/hand-edited artifact). |
| `alpha_matches.json` | Yes | 660 matches | `week2.alpha_matches.v2` | Yes | `mapper_version: week2.alpha_mapper.v2`, `minimum_match_score: 0.35` |
| `extracted_structures.json` | Yes | 6 nodes, **0 edges** | `week2.extracted_structures.v2` | Yes | `metadata.deterministic_edge_count: 0`, `metadata.llm_edge_count: 0`, `metadata.llm_enabled: false` |
| `structure_graph.json` | Yes | 6 nodes, **0 edges** | `week3.structure_graph.v2` | Yes | `graph_builder_version: week3.graph_builder.v1`, `activation_scorer_version: week3.activation_scorer.v1` |
| `run_audit.json` | Yes | -- | `structure_correctness.run_audit.v1` | Yes | `graph_edge_count: 0`, `rejected_edge_count: 0`; also carries the Track B `alpha_evidence_integrity` sidecar (schema `week_regime_evidence_integrity.v1`) from a prior sprint |
| `research_response.json` | **Not present** | -- | -- | -- | Confirmed by source inspection this is expected, not a defect: `get_research_response()`/`research_response.json` (`routes_research.py:1153-1154`) is dead code -- the live `GET /api/research/{run_id}` route (`routes_research.py:1809-1811`) calls `get_research_run()` -> `build_research_response()` directly, never the file-backed `get_research_response()`. Nothing in the codebase ever *writes* `research_response.json` either (grep confirms only these two read-only references exist). It is a vestigial allowed-filename entry in `file_store.py`'s whitelist, not an artifact this run's pipeline was ever supposed to produce. |
| `data_sanity.json` | Yes | -- | `comqutor.data_sanity.v1` | Yes | `status: critical` (see Section E) |
| `market_data_snapshot.json` | Yes | 274 rows | `comqutor.market_data_snapshot.v1` | Yes | query window `2025-06-22` .. `2026-07-28` (exclusive) |
| `week3_pipeline_status.json` | Yes | -- | -- | Yes (run_id only; no ticker field by design) | `outcome`/`stage` bookkeeping only |
| DB `research_runs` | Yes | 1 row | -- | Yes | `status: completed` |
| DB `agent_outputs` | Yes | 660 rows | -- | Yes | matches `structured_agent_outputs.json` record count exactly |
| DB `alpha_matches` | Yes | 660 rows | -- | Yes | matches `alpha_matches.json` record count exactly |
| DB `structure_graphs` | Yes | 1 row | `week3.structure_graph.v2` | Yes | `graph_json.edges: []` -- confirmed **0 edges in the database itself**, not merely in the file |
| DB `alpha_activations` | Yes | 10 rows | -- | Yes | one row per MVP alpha; scores match `structure_graph.json`'s v2 activation block exactly |
| DB `alpha_conflicts` | Yes | 6 rows | -- | Yes | |
| DB `research_run_progress` | Yes | 1 row | -- | Yes | `progress_percent: 100`, `current_stage: completed` |

**Cross-consistency:** every artifact and every DB row carries the identical `run_id`/`ticker` pair with
no mismatch. No stale/wrong-run artifact contamination was found anywhere in the stack.

---

## C. Edge Pipeline Forensics

### Method

A dedicated, fully read-only replay script imported the **real, unmodified** production functions
(`structured_output_adapter.adapt_run_outputs`, `structure_extractor._extract_factors`/`_extract_edges`,
`relation_grammar.extract_relation_candidates`/`match_conflicting`, `claim_quality.is_claim_eligible`,
`factor_normalizer.extract_known_factors_from_text`) against an isolated scratch copy of
`metadata.json` + `raw_agent_outputs.json` (never the real run directory). No regex or grammar was
reimplemented for judgment purposes -- only the outer Markdown block/sentence-splitting *mechanics*
(paragraph/heading/bullet/table detection) were duplicated, purely to enumerate the full candidate
sentence superset that the adapter's own audit counters do not expose (see C2); every actual
*classification* decision (`classify_filtered_claim`, `_is_meaningful_claim`, `classify_claim_quality`,
`extract_relation_candidates`, `match_conflicting`, `is_claim_eligible`) still calls the real function.

### C1/C3/C4 -- Definitive result: zero relation candidates were ever generated, anywhere, for any claim

Running the real `_extract_factors()` + `extract_relation_candidates()` + `match_conflicting()` +
`_extract_edges()` against **every one of the 660 real structured claims** in this run:

| Metric | Count (of 660) |
|---|---|
| Claims with 2+ resolved canonical factors (the only structural precondition for a candidate edge) | **2** |
| Claims with a relation-grammar pattern (causal/supportive verb, conditional/prefix-cause marker, contrast word) present, but fewer than 2 resolved factors | 194 |
| Claims with neither 2+ factors nor any pattern hit at all | 445 |
| Claims where `extract_relation_candidates()` returned >= 1 candidate | **0** |
| Claims where `match_conflicting()` returned >= 1 pair | **0** |
| Claims where `_extract_edges()` produced >= 1 final edge | **0** |

This is a byte-for-byte, claim-by-claim explanation of `extracted_structures.json`'s own
`deterministic_edge_count: 0` / `rejected_edge_count: 0` -- **nothing was ever proposed, so nothing was
ever rejected either.** This is not "everything got filtered downstream"; it is "the raw commentary never
put two canonical factors in one sentence with a verb connecting them, except for two near-misses that
the grammar correctly, deliberately declined."

The full per-claim detail (`resolved_factors`, `pattern_hits`, `ambiguous_factors`,
`relation_candidates`, `conflicting_pairs`, `final_edges`, quality class, and text) for all 660 claims is
in `docs/msft_relation_claim_audit.csv`.

**The two 2-factor claims, in full:**

| claim_id (suffix) | agent | factors | claim text | why no candidate |
|---|---|---|---|---|
| `sentiment_report:claim:14` | sentiment_agent | AI Infrastructure, Inference Demand | "Positive ecosystem signal: IBM joined MSFT, Nvidia, and Palantir in the Open Secure AI Alliance, reinforcing MSFT's central role in enterprise AI infrastructure." | **AMBIGUOUS_OVERLAPPING_FACTOR_ENDPOINT.** Both "factors" are triggered by the *same* physical phrase, "enterprise AI infrastructure" -- "AI Infrastructure" via its own alias, "Inference Demand" via its alias `"enterprise ai"` -- and the two mention spans overlap (share the token "AI"). `relation_grammar._ambiguous_factors()` correctly refuses to pick either as a clean endpoint rather than risk fabricating a link between what is really one single concept, not two. This is the grammar's ambiguity guard working exactly as designed, not a bug. |
| `investment_debate_state.bull_history:claim:34` | bull_researcher | AI Infrastructure, Inference Demand | "That's not reckless spending — that's the largest enterprise AI infrastructure buildout in corporate history, funded by a company with only $8.2 billion in net debt." | Same alias-overlap pattern ("enterprise AI infrastructure buildout") -- same correct abstention. No relation verb pattern is even present in this sentence either. |

Neither near-miss would have produced an edge even absent the ambiguity guard: neither contains a
recognized relation-grammar verb phrase connecting the two mentions in the same clause.

### Root cause: `NO_RELATION_STATEMENT` / `VALID_ABSTENTION` for essentially all 660 claims

Manually reviewing the 194 pattern-hit-but-single-factor claims (full list in the CSV) shows two
dominant, non-overlapping explanations, neither of which is a Structure Extractor, Factor Resolution, or
Relation Grammar defect:

1. **Technical/price-action language entirely outside the 13-factor canonical taxonomy** (54 of 194):
   moving averages, MACD, RSI, Bollinger Bands, ATR, support/resistance levels -- e.g. *"The 50 SMA is
   declining, confirming sustained medium-term selling pressure."* `FACTOR_ALIASES` (frozen, not modified
   in this audit) deliberately does not model technical indicators as factors at all; this is a scope
   boundary of the taxonomy, not a resolution gap.
2. **Rhetorical/debate framing with a contrast word but no second factor** (129 of 194): bull/bear
   "but"/"however" language contrasting *tone*, not two distinct canonical factors -- e.g. *"However, the
   histogram peaked at +3.46 on July 20 and has been declining since..."*

The remaining 11 non-technical, single-factor, pattern-hit claims were reviewed individually (see CSV);
none contains a second concept that both (a) genuinely names a distinct real-world factor and (b) is
missing only because of narrow alias-string coverage in a way that would plausibly have produced a
*different* graph if fixed. One narrow, explicitly-noted observation: `"no Fed cuts"` (plural) does not
match the `"fed cut"` (singular) alias due to the word-boundary regex requiring an exact token match --
a real but inconsequential gap, since the surrounding sentence ("...is a genuine multiple compression
headwind") has no relation-grammar verb pattern connecting the two concepts anyway, so fixing the alias
would not have produced an edge here. `FACTOR_ALIASES` was **not modified** (explicitly frozen).

**C4 root-cause categorization (per the required taxonomy):** closest to **(6) HONEST_ZERO_EDGE_RUN** --
every claim with any relation-like signal was correctly, defensibly non-productive (the 2 real
co-occurrences were correctly abstained on genuine ambiguity; the 194 single-factor pattern hits are
either out-of-taxonomy technical language or rhetorical framing) -- **with one important, independently
significant caveat found in C2 below that must not be suppressed.**

### C2 -- Independent defect found: a silent, unaudited 64-claim segmentation cap

While building the raw-sentence inventory, an unrelated but genuine defect was discovered and fully
characterized: `structured_output_adapter.py`'s `MAX_CLAIMS_PER_RAW_OUTPUT = 64` constant causes
`extract_claim_segments_with_audit()` to **return early**, mid-report, once 64 valid segments have been
collected for a single raw agent output -- silently discarding every remaining paragraph/bullet in that
report, with **zero visibility in any audit counter** (`run_audit.json`'s `raw_agent_output_count`,
`raw_claim_count`, `boilerplate_removed_count`, etc. are all computed *after* this cap has already
applied, so they cannot see what was cut).

For this run, **7 of the 12 raw agent outputs hit this cap exactly**:

| Agent | Would-be valid segments (uncapped) | Kept (capped at 64) | Truncated (never processed) | Truncated with a relation-grammar pattern hit | Truncated with 2+ factors |
|---|---:|---:|---:|---:|---:|
| market_agent | 84 | 64 | 20 | 6 | 0 |
| sentiment_agent | 72 | 64 | 8 | 3 | 0 |
| bull_researcher | 381 | 64 | 317 (83%) | 68 | 2 |
| bear_researcher | 445 | 64 | 381 (86%) | 86 | 1 |
| aggressive_risk_analyst | 265 | 64 | 201 (76%) | 52 | 0 |
| conservative_risk_analyst | 250 | 64 | 186 (74%) | 50 | 0 |
| neutral_risk_analyst | 248 | 64 | 184 (74%) | 59 | 0 |
| **Total** | | | **1,297** | **324** | **3** |

This was verified rigorously, not asserted: the first 64 "would-be-kept" sentences produced by an
independent re-derivation of the block/sentence-splitting mechanics match the real, capped
`extract_claim_segments_with_audit()` output **exactly**, in order, for all 7 agents -- proving the
uncapped superset generator is a faithful, order-correct reproduction and the only difference is the
missing cap, not a bug in the audit's own tooling.

**Critically, this defect did NOT change this run's 0-edge outcome.** All 3 truncated 2-factor sentences
were checked individually: all 3 are the same "enterprise AI [infrastructure/demand]" alias-overlap
pattern already found in the retained 660 (Section C1) -- correctly non-productive regardless. This is
reported as an honest, independently significant finding (undiscovered, unaudited, real data loss of up
to 86% of a single analyst's commentary) rather than being suppressed because it happens not to be *this
run's* proximate cause. It is entered into Defects Found below with its own severity, independent of the
edge-count question.

**True raw sentence count for this run** (previously invisible number, now established): the pipeline's
own `raw_agent_output_count: 12` / `raw_claim_count: 660` in `run_audit.json` significantly undercounts
the true size of the input. The true count of sentence-level candidates across all 12 reports is
**2,122**, of which 667 were ever evaluated as valid segments (660 after the 7-claim
quality-gate rejection), 15 were classified boilerplate/disclaimer, 113 were silently dropped as too
short/non-meaningful (uncounted by any metadata field either), and **1,297 were never evaluated at all**
because of the cap.

### C2 (continued) -- Claim Quality gate: verified NOT a source of relation-claim loss

The 7 claims rejected by `classify_claim_quality()` as `NON_SUBSTANTIVE` (6 `BARE_HEADING_OR_LABEL` + 1
`BOILERPLATE_META_COMMENTARY`, exactly matching `run_audit.json`'s `quality_reason_counts`) were
individually re-verified: all 7 resolve **zero** canonical factors. None is a lost relation claim. Example:
*"The Bollinger Band setup is telling:"* (bare heading, 0 factors), *"Now let me challenge the aggressive
analyst on the macro argument, because your interest rate framing is too cute."* (meta-commentary, 0
factors). Deduplication removed 0 claims for this run (`duplicate_removed_count: 0`), so there is no
dedup-related loss either.

**Summary funnel:**

| Stage | Count |
|---|---:|
| Raw candidate sentences (true total, uncapped) | 2,122 |
| Silently dropped as too short/non-meaningful (uncounted anywhere) | 113 |
| Dropped by boilerplate/disclaimer/transition classifier (uncapped total) | 45 |
| **Lost to the undiscovered 64-claim segmentation cap** | **1,297** |
| Segments actually evaluated (kept + filtered) | 682 |
| Kept as valid segments | 667 |
| Rejected as `NON_SUBSTANTIVE` by the claim quality gate | 7 |
| **Final valid structured claims** | **660** |
| Claims with 2+ resolved factors | 2 (both correctly abstained) |
| **Final graph edges** | **0** |

### C5 -- API / DB / artifact / frontend layer consistency

The live route function `get_persisted_structure_graph()` (`routes_research.py:1193`) was called
in-process, exactly as the real FastAPI route does, against the real Postgres database
(`COMQUTOR_DATABASE_URL` from `.env`), with no server restart and no new research run:

| Layer | Node count | Edge count |
|---|---:|---:|
| `extracted_structures.json` (file) | 6 | 0 |
| `structure_graph.json` (file) | 6 | 0 |
| DB `structure_graphs.graph_json` | 6 | 0 |
| **Live API response** (`get_persisted_structure_graph()`, real DB) | **6** | **0** |
| Frontend adapter (`adapters.ts`) | Accepts any array (including empty) for `edges`; no special-casing that would reject or hide a valid, empty edge list. `!Array.isArray(payload.nodes) || !Array.isArray(payload.edges)` is the only structural gate, and both are present here. | -- |

**The zero-edge count is fully consistent top to bottom, at every single layer.** There is no
API-projection bug and no frontend-rendering bug: the graph genuinely has 0 edges at the source
(`extracted_structures.json`), and every downstream layer faithfully reports that same 0. The Graph API
route's activation block (`graph.activation`, which the frontend reads) was also confirmed to already be
keyed to the correct **primary/v2** activation formula (`activation.v2.evidence_local_structure.v1`,
matching `structure_graph.json`'s own `primary_activation_version`) -- not the older, separately-retained
`activation_versions.v1` MVP formula, so there is no stale-formula-version bug in what the frontend
displays either.

---

## D. Node Detail Forensics

**Exact rendering code path:** `frontend/src/pages/StructureGraphPage.tsx`

```tsx
// line 134-136
const selectedNode = selectableNodes.find((node) => node.id === selectedNodeId) ?? null;
const selectedNodeActivation = selectedNode
  ? graph.activation.alphas.find((alpha) => selectedNode.alpha_ids.includes(alpha.alpha_id))
  : null;

// line 196-216
{selectedNode ? (
  selectedNodeActivation ? (
    <AlphaCard ... />
  ) : (
    <EmptyState
      title={selectedNode.label}
      description="This factor node is not mapped to a scored Alpha."   // line 214
    />
  )
) : ( ... )}
```

The fallback fires whenever `selectedNode.alpha_ids` is empty (or contains only ids absent from
`graph.activation.alphas`, which cannot happen here since all 10 MVP alphas are always present).

**Per-node ground truth**, read directly from the live API response (real DB, same call as Section C5):

| node_id | label | alpha_ids | Underlying claim-level alpha_matches status | claim_ids | evidence | agents |
|---|---|---|---|---|---|---|
| ai_capex | AI CapEx | **[]** | All 3 underlying claims: `match_status: "no_match"`. Best candidate for each is **A301 (Revenue Expansion), score 0.305** -- just below the Mapper's `minimum_match_score: 0.35` admission threshold (a genuine near-miss, not a bug: `reason: "high-scoring candidates were rejected as mention-only or outside taxonomy"`). | 3 | 3 evidence strings present | aggressive_risk_analyst, sentiment_agent |
| ai_infrastructure | AI Infrastructure | **["A103"]** | Genuinely `matched` | 4 | 4 present | conservative_risk_analyst, news_agent, sentiment_agent |
| inference_demand | Inference Demand | **[]** | `no_match` for its claims (same AI-alpha-gate rejection pattern) | 4 | 4 present | news_agent, sentiment_agent |
| msft_revenue_growth | MSFT Revenue Growth | **["A301"]** | Genuinely `matched` | 13 | 13 present | 9 distinct agents |
| recession_risk | Recession Risk | **["A501"]** | Genuinely `matched` | 1 | 1 present | news_agent |
| valuation_risk | Valuation Risk | **["A304"]** | Genuinely `matched` | 3 | 3 present | research_manager, neutral_risk_analyst, portfolio_manager |

**Direct answers to the required questions:**

1. **Does the artifact/API already contain claim/evidence/agent provenance?** Yes, for every node,
   including the two with an empty `alpha_ids` -- `claim_ids`, `evidence` (full text), `agents`, and
   `source_agent_output_ids` are all already present in the live API response today. This required no new
   query; it was read directly off the existing `get_persisted_structure_graph()` response.
2. **Does the frontend ignore these fields for the fallback case?** Yes. `StructureGraphPage.tsx`'s
   `EmptyState` branch (line 211-215) passes only `title` and one static `description` string -- it never
   reads `selectedNode.claim_ids`, `.evidence`, `.agents`, or `.source_agent_output_ids`, all of which are
   sitting on the same `selectedNode` object one line above.
3. **Is "ai_capex" genuinely un-mapped, or does alpha_matches contain a relevant mapping that the node
   just isn't carrying?** **Genuinely un-mapped by the Mapper's own admission rule**, verified directly
   against `alpha_matches.json`: every one of its 3 claims has `"matched_alpha": null` and
   `"match_status": "no_match"`. The node's empty `alpha_ids` is **not a plumbing bug** -- it is a
   correct, faithful reflection of `alpha_matches.json`. (This was checked rigorously rather than assumed:
   an initial read of a per-candidate `"eligible": true` sub-field on A301 looked like a possible
   plumbing gap, but the claim's own top-level `"eligible_candidates": []` and `"match_status": "no_match"`
   confirm the 0.305 score genuinely fell short of the 0.35 admission bar -- the per-candidate `eligible`
   flag is a narrower, lower-level diagnostic, not the admission decision.) By contrast, the other 4 nodes'
   `alpha_ids` are populated correctly and match genuinely `matched` claims one for one -- the node-level
   alpha attribution plumbing (`graph_builder.py`'s `_committed_alpha_ids_for_claim`) is working correctly
   across the board.
4. **Is "not mapped to a scored Alpha" a data fact or an oversimplified UI fallback?** **Both, and the
   distinction matters.** The *absence of a committed alpha* is a true data fact for `ai_capex` and
   `inference_demand`. But the *message itself* is an oversimplified fallback in a separate, real sense:
   it discards rich, already-available provenance (3 evidence quotes, 2 contributing agents, a
   near-miss score of 0.305 against a 0.35 bar) that a user would find far more informative than a single
   flat sentence, and that data is not even a projection change away -- it is already sitting in the
   response object the component already has in hand.
5. **Does the UI wrongly treat Factor -> Alpha as a required one-to-one relationship?** **Yes, by
   construction.** `selectedNode.alpha_ids` is explicitly typed and populated as a list (a factor can
   legitimately support multiple alphas), but `selectedNodeActivation` is computed with `.find()`, which
   returns at most one match and stops at the first. No node in this run currently has 2+ committed
   `alpha_ids` so this limitation is not visibly triggered today, but it is a real, confirmed constraint
   of the current rendering code, not a hypothetical: a future factor mapped to two admitted alphas would
   silently show only whichever one happens to appear first in `graph.activation.alphas`'s array order,
   with the second alpha's contribution invisible in the Node Detail panel entirely.

**Minimal follow-up scope (not performed in this audit; UI was not modified):**

- **Achievable with existing fields alone (frontend-only change):** render `selectedNode.claim_ids.length`,
  `.evidence`, `.agents` in the `EmptyState` fallback; change `.find()` to `.filter()` (or render a list)
  so a multi-alpha node shows every committed alpha, not just the first.
- **Needs an additive API field:** the near-miss score (0.305) and its gap to the 0.35 threshold are not
  currently exposed anywhere on the graph node shape -- `alpha_matches.json` has them per-claim, but
  nothing joins/surfaces a node-level "closest candidate" summary today.
- **Needs backend provenance aggregation:** a node-level "top candidate across all its claims" rollup
  (distinct from the per-claim detail) would require a small new aggregation step; nothing today computes
  this at the node granularity.

---

## E. Data Quality Forensics

### E1. Dividend information

All 4 dividend events shown in Data Quality are cross-verified directly against
`market_data_snapshot.json`'s raw yfinance rows (not merely against `data_sanity.json`'s own claim):

| Date | Amount | Present in raw snapshot row | Distinct corporate action | Within analysis window `[2025-06-22, 2026-07-28)` | Used for price adjustment | Severity | Verdict |
|---|---:|---|---|---|---|---|---|
| 2025-08-21 | $0.83 | Yes, exact match | Yes (only occurrence of this date) | Yes | Yes -- `adjusted_close` differs from `close` on this row via the standard ex-dividend adjustment | info | **VALID_INFORMATIONAL_EVENT** |
| 2025-11-20 | $0.91 | Yes, exact match | Yes | Yes | Yes | info | **VALID_INFORMATIONAL_EVENT** |
| 2026-02-19 | $0.91 | Yes, exact match | Yes | Yes | Yes | info | **VALID_INFORMATIONAL_EVENT** |
| 2026-05-21 | $0.91 | Yes, exact match | Yes | Yes | Yes | info | **VALID_INFORMATIONAL_EVENT** |

No duplicate dates exist anywhere in the 274-row snapshot (`Counter` check on every `date` field, 0
duplicates). The 4 dates are ~91 calendar days apart each, consistent with a genuine quarterly dividend
cadence, not a repeated/duplicated single event. `check_corporate_actions()`
(`comqutor_alpha/data_sanity/checker.py:262-321`) hard-codes `SEVERITY_INFO` for every dividend/split/
capital-gain event unconditionally -- there is no code path by which a dividend could ever be emitted as
`warning`/`critical`, so `severity: info` is correct by construction, not a coincidence of this run's data.

**Why does the frontend show these in a pink/warning-colored area despite `severity: "info"`?** This
audit inspected `ResearchRunPage.tsx`'s and `adapters.ts`'s Data Quality rendering and confirmed the
component groups Data Sanity warnings by section/count rather than rendering severity-specific,
per-item color coding purely from the `severity` field alone in every location; a full byte-for-byte
trace of the exact CSS class/branch responsible for the visual color was not completed as part of this
audit's core scope (UI styling was explicitly out of scope for a read-only backend-focused forensic pass,
and no UI code was to be modified regardless). **This is flagged as an open, UI-presentation-only question
worth a follow-up (see Defects Found) -- it is independent of the data itself, which is correct.**

### E2/E3. `$430.85` and `$13.73`

**Both amounts are confirmed to be technical/statistical price-derived indicator values, not stock
prices of any kind (not EPS, not dividend, not price target, not historical/closing/intraday price).**

#### `$430.85`

| Field | Value |
|---|---|
| claim_id | `61f3e019-...:market_agent:market_report:claim:42` |
| agent | market_agent |
| source_section | `"Bollinger Bands (Middle: $387.26 \| Upper: $405.10 \| Lower: $369.42)"` |
| Full structured claim/evidence | *"The Upper Band has been declining from $430.85 on July 1 to $405.10 now, while price has been rising — this convergence is reducing the resistance gap and building tension."* |
| reported_date | 2026-07-01 (`date_resolution: analysis_year_inferred` -- the sentence says only "July 1", correctly resolved against `analysis_date=2026-07-27`'s own year since that candidate date does not fall after the analysis date) |
| price_semantics | `generic` (matched by the extractor's bare `"$X on <date>"` pattern -- no verb like "closed at"/"traded at" is present) |
| external_reference | 408.2714858... (= real 2026-07-01 session `high` of 388.83 × the range-high tolerance factor 1.05 -- verified exactly against `market_data_snapshot.json`'s real OHLC row for that date) |
| relative_difference_percent | 5.5303% |
| severity | warning |
| **Semantic type** | **OTHER_MONETARY_AMOUNT** (a Bollinger Band Upper technical-indicator reading, not a stock price) |
| **Root cause** | **NON_PRICE_MONETARY_FALSE_POSITIVE** |

#### `$13.73`

| Field | Value |
|---|---|
| claim_id | `61f3e019-...:market_agent:market_report:claim:46` |
| agent | market_agent |
| source_section | `"ATR: $12.13"` |
| Full structured claim/evidence | *"It has been declining from a peak of $13.73 on June 29 but remains sticky at $12 range."* |
| reported_date | 2026-06-29 (`analysis_year_inferred`, same logic as above) |
| price_semantics | `generic` |
| external_reference | 341.9049942... (= real 2026-06-29 session `low` of 359.90 × the range-low tolerance factor 0.95 -- verified exactly) |
| relative_difference_percent | 95.9843% |
| severity | critical |
| **Semantic type** | **OTHER_MONETARY_AMOUNT** (an ATR -- Average True Range -- volatility-indicator reading; the claim's own trailing clause, "remains sticky at $12 range," is itself an explicit paraphrase of the section header "ATR: $12.13") |
| **Root cause** | **NON_PRICE_MONETARY_FALSE_POSITIVE** |

**Both dates/OHLC-range comparisons/arithmetic were independently re-derived and are exactly correct.**
The defect is not `DATE_ALIGNMENT_ERROR`, not `REFERENCE_SELECTION_ERROR`, and not `OHLC_RANGE_ERROR` --
every one of those mechanical steps is verified right. The defect is purely semantic: the extractor pulled
a real, correctly-dated dollar figure out of the sentence, but that figure describes a *technical
indicator level*, not a traded price of the stock.

**Root-cause code path** (`comqutor_alpha/data_sanity/reported_price_extractor.py`):

```python
# lines 32-39
_DISQUALIFYING_TERMS = ("eps", "earnings per share", "revenue", "market cap", "price target", "%")

# lines 82-84 -- the pattern that actually matched both claims
_BARE_PRICE_DATE_PATTERN = re.compile(
    rf"(?i)\$\s?(\d{{1,6}}(?:\.\d{{1,4}})?)\s+on\s+({_DATE_ALT})\b"
)
# -> price_semantics = PRICE_SEMANTICS_GENERIC (line 161)
```

`_DISQUALIFYING_TERMS` does not include any technical/statistical-indicator vocabulary ("Bollinger",
"Band", "ATR", "SMA", "EMA", "MACD", "RSI", "moving average"). **Confirmed: the extractor effectively does
"extract every bare `$number on <date>`, default-treat it as a stock price mention" whenever none of a
narrow 6-term disqualifier list is present in the same sentence** -- exactly the anti-pattern the audit
brief asked to check for, with the exact function (`extract_reported_prices` /
`_match_price_date`/`_BARE_PRICE_DATE_PATTERN`) and file/line evidence above.

**This is not an isolated pair of unlucky sentences.** Running the real extractor against all 660
structured claims produced **exactly 4** reported-price extractions total for this run:

| claim | price_semantics | Genuine stock price? | Triggered a warning? |
|---|---|---|---|
| claim:1, *"Microsoft closed at $389.10 on July 27, 2026..."* | `close` (explicit verb "closed at") | **Yes -- genuine** | No (matches real close exactly) |
| claim:7, *"The 50-day SMA is at $399.22... ($409 on July 2...)"* | `generic` | **No -- 50-day SMA**, same underlying defect | No (a short moving average happens to track close enough to real price that it stayed inside the ±5%/95% tolerance band this time) |
| claim:42 ($430.85, Bollinger Upper) | `generic` | No | **Yes, warning** |
| claim:46 ($13.73, ATR) | `generic` | No | **Yes, critical** |

**3 of this run's 4 total "reported price" extractions (75%) are technical-indicator false positives; only
1 is a genuine stock-price mention.** Two of the three happened to be far enough from the real trading
range to surface as warnings; the third (the SMA) did not, purely because a moving average's value is
naturally close to price by construction -- meaning the underlying misclassification is systemic across
this report's technical-analysis section, and this run's specific 2 visible warnings almost certainly
understate the true scope of the false-positive rate for reports with heavier technical-indicator content.

### E4. Data Quality / Graph independence

Confirmed by source inspection, not merely by architecture description: every function in
`comqutor_alpha/data_sanity/checker.py` (`check_market_availability`, `check_ohlcv_integrity`,
`check_corporate_actions`, `check_extreme_returns`, `check_reported_prices`, `run_checks`) is a pure
function over plain `rows`/`reported_prices`/`analysis_date` arguments, returning only
`{status, warnings, checks, summary}`. None of these functions imports or calls into `claim_quality`,
`structure_extractor`, `graph_builder`, `activation_scorer`, or any persistence/status-transition code.

The call site (`routes_research.py:1098`) confirms this architecturally *and* the real run confirms it
empirically:

```python
run_data_sanity_stage(run_id, output_root)   # return value discarded; no `if` gates on it
_run_week3_graph_pipeline(...)               # runs unconditionally next
```

**This run's own database row is the empirical proof:** `data_sanity_status: "critical"` (1 critical +
1 warning) coexists with `research_runs.status: "completed"` in the same real database row for the same
run. A "critical" Data Sanity outcome plainly did not, and architecturally cannot, block claim
eligibility, factor resolution, edge admission, Activation scoring, or the run reaching `completed`
status. Data Quality is a genuinely independent, additive sidecar.

---

## F. Output Files

- `docs/msft_fresh_run_edge_node_data_quality_forensic_audit.md` (this file)
- `docs/msft_relation_claim_audit.csv` (660 rows -- full per-claim C1/C3/C4 detail)
- `docs/msft_data_quality_issue_provenance.csv` (6 rows -- the 4 dividend events + the 2 price-anomaly
  warnings, full provenance)

No target run directory file was written to. No production artifact was modified.

---

## G. Final Structured Summary

```
Audit:
MSFT Fresh Run Edge, Node Detail, and Data Quality Forensic Audit

Status:
PASS_WITH_DEFECTS_FOUND

Target Run:
- run_id: 61f3e019-63a8-4c56-b763-057208d5efae
- ticker: MSFT
- analysis_date: 2026-07-27
- created_at: 2026-07-28T00:43:39.396Z (DB) / metadata.json created_at 2026-07-28T01:08:42Z
- fresh run evidence: sole MSFT row in research_runs; most recent row of any ticker; filesystem
  mtimes consistent with DB timestamps; unambiguous, no candidate ambiguity
- selected analysts: market, sentiment, news, fundamentals

Executive Verdict:
- Why edge count is zero: Across all 660 real structured claims, only 2 ever resolve 2+ canonical
  factors in the same sentence, and both are a single physical concept ("enterprise AI infrastructure")
  double-counted by overlapping alias vocabulary between "AI Infrastructure" and "Inference Demand" --
  correctly refused by the grammar's own ambiguity guard. No other claim ever had the structural
  precondition (2+ resolved factors) for a relation candidate at all.
- Edge root-cause category: HONEST_ZERO_EDGE_RUN (all legitimate relation-adjacent sentences correctly
  abstained), with an independently significant, separately-tracked defect (segmentation truncation,
  see below) that did not change this run's outcome but must not be suppressed.
- Is zero-edge result honest: Yes, verified claim-by-claim, not merely inferred from summary counters.
- Is Relation Grammar defective: No. It correctly declined the two genuine 2-factor co-occurrences on a
  real, defensible ambiguity signal.
- Is Factor Resolution defective: No systemic defect. One narrow, inconsequential alias-plurality gap
  ("Fed cuts" vs. "fed cut") was found and documented but would not have produced a different edge count
  even if fixed (no connecting relation-grammar verb pattern was present in that sentence regardless).
- Is Graph admission defective: No. 0 candidates were ever generated, so 0 were ever admitted or
  rejected (rejected_edge_count: 0 is accurate, not "everything was filtered").
- Is API/frontend inconsistent: No. Node/edge counts are identical across
  extracted_structures.json / structure_graph.json / the database row / the live in-process API call.
  The frontend's own graph adapter accepts the (valid, empty) edges array without incident.

Edge Pipeline:
- Raw relation-like sentences: 2,122 true candidate sentences across all 12 raw agent outputs
  (uncapped); of these, 324 truncated-away sentences and 194 retained sentences carry a
  relation-grammar pattern hit but fewer than 2 resolved factors.
- Structured relation claims (2+ resolved factors, the structural precondition for a candidate): 2 of
  660 retained claims; 3 of the 1,297 segmentation-cap-truncated sentences.
- Quality-filtered valid relations: 0 (both retained 2-factor claims correctly abstained via the
  ambiguity guard; none of the 3 truncated 2-factor sentences would have produced an edge either).
- Candidate edges: 0
- Admitted edges: 0
- Rejected edges: 0
- Rejection reasons: N/A -- nothing was ever proposed to reject.

Most Important Relation Claims:
- claim_id: ...sentiment_report:claim:14 / agent: sentiment_agent / text: "Positive ecosystem signal:
  IBM joined MSFT, Nvidia, and Palantir in the Open Secure AI Alliance, reinforcing MSFT's central role
  in enterprise AI infrastructure." / quality: analytical / factors: [AI Infrastructure, Inference
  Demand] / grammar result: pattern hit present (FORWARD_TRANSITIVE_SUPPORTIVE) / candidate result: 0
  (ambiguous overlapping factor endpoint) / final result: no edge.
- claim_id: ...investment_debate_state.bull_history:claim:34 / agent: bull_researcher / text: "That's
  not reckless spending — that's the largest enterprise AI infrastructure buildout in corporate
  history, funded by a company with only $8.2 billion in net debt." / quality: analytical / factors:
  [AI Infrastructure, Inference Demand] / grammar result: no pattern hit / candidate result: 0
  (ambiguous overlapping factor endpoint) / final result: no edge.
- Full 660-claim detail in docs/msft_relation_claim_audit.csv.

Node Detail:
- Exact rendering code path: frontend/src/pages/StructureGraphPage.tsx:135-136 (selectedNodeActivation
  computation) and :211-215 (EmptyState fallback with the fixed description string), gated on
  selectedNode.alpha_ids.
- Why fallback message appears: selectedNode.alpha_ids is empty for "AI CapEx" and "Inference Demand"
  specifically -- confirmed correct against alpha_matches.json (all underlying claims are
  match_status="no_match"; AI CapEx's best candidate, A301, scores 0.305 against a 0.35 admission
  threshold -- a genuine near-miss, not a bug). "AI Infrastructure"/"MSFT Revenue Growth"/"Recession
  Risk"/"Valuation Risk" correctly show A103/A301/A501/A304 respectively and would not hit this fallback.
- Provenance already available: Yes -- claim_ids, full evidence text, and agent names are already
  present on every node in the live API response today, including the two with empty alpha_ids.
- Frontend omission: Yes -- the EmptyState branch renders only a title and one static sentence; it
  never reads the claim_ids/evidence/agents fields already sitting on the same selectedNode object.
- API data gap: None for the provenance question. One real gap: no node-level "closest candidate score
  and threshold gap" field exists anywhere in the API today (this data lives per-claim in
  alpha_matches.json only).
- Product-design verdict: The "no alpha" fact is true for these 2 nodes; the message's flatness is an
  oversimplified fallback that discards data the component already has. Separately, selectedNodeActivation
  is computed with .find() (first match only) against a list-typed alpha_ids field, so the UI cannot
  currently render more than one Alpha per node even though the data model explicitly supports it -- not
  triggered visibly in this run (no node here has 2+ alpha_ids) but a confirmed source-level limitation.

Data Quality:
- Dividend verdict: All 4 (2025-08-21 $0.83, 2025-11-20 $0.91, 2026-02-19 $0.91, 2026-05-21 $0.91) are
  VALID_INFORMATIONAL_EVENT -- confirmed against market_data_snapshot.json's raw rows, all distinct
  dates, all within the analysis window, severity=info by construction (check_corporate_actions has no
  code path to emit a dividend as warning/critical).
- Dividend duplication: None found (0 duplicate dates in 274 snapshot rows).
- Dividend UI presentation verdict: Data itself and severity assignment are both correct; whether/why
  the frontend visually places an info-severity event in a warning-colored region was not fully traced
  to an exact CSS/branch line within this audit's scope and is flagged as an open follow-up question,
  not a confirmed defect.
- $430.85 semantic type: OTHER_MONETARY_AMOUNT (Bollinger Band Upper technical-indicator reading for
  2026-07-01, confirmed via the claim's own source_section header "Bollinger Bands (...Upper:
  $405.10...)").
- $430.85 root cause: NON_PRICE_MONETARY_FALSE_POSITIVE.
- $13.73 semantic type: OTHER_MONETARY_AMOUNT (ATR / Average True Range technical-indicator reading for
  2026-06-29, confirmed via source_section "ATR: $12.13" and the claim's own "$12 range" cross-reference).
- $13.73 root cause: NON_PRICE_MONETARY_FALSE_POSITIVE.
- Price extraction algorithm verdict: Confirmed -- reported_price_extractor.py's
  _BARE_PRICE_DATE_PATTERN extracts any bare "$X on <date>" phrase and treats it as a stock-price mention
  unless one of 6 narrow disqualifying terms (eps/earnings per share/revenue/market cap/price
  target/%) appears in the same sentence; none of those terms covers technical/statistical
  price-derived indicators (Bollinger/SMA/EMA/ATR/MACD/RSI). 3 of this run's 4 total reported-price
  extractions are such false positives; only 1 is a genuine stock price.
- Severity verdict: Both severity assignments (warning for 5.53%, critical for 95.98%) are computed
  correctly per the documented thresholds (5%/50%) given the (mistaken) external_reference comparison;
  the severity logic itself is not the defect.
- Provenance completeness: Complete for every item audited -- claim_id, agent, source_section, full
  claim text, external_reference, and date_resolution were all available and cross-verified for every
  dividend and every price-anomaly warning.

Layer Consistency:
- Artifact counts: 6 nodes / 0 edges (extracted_structures.json and structure_graph.json agree)
- DB counts: 6 nodes / 0 edges (structure_graphs.graph_json)
- API counts: 6 nodes / 0 edges (live in-process call to get_persisted_structure_graph() against the
  real Postgres database)
- Frontend-adapted counts: accepts 6 nodes / 0 edges without incident (edges is a valid, non-null empty
  array; the adapter's only structural gate is Array.isArray on both nodes and edges)

Defects Found:
1. severity: HIGH (real, unaudited data loss; separate from the edge-count question)
   root cause: MAX_CLAIMS_PER_RAW_OUTPUT = 64 hard cap in extract_claim_segments_with_audit() silently
   truncates a raw agent output mid-report once 64 valid segments accumulate, with zero visibility in
   any run_audit.json counter.
   file/function/line: comqutor_alpha/structure_engine/structured_output_adapter.py,
   extract_claim_segments_with_audit(), the `if len(segments) >= MAX_CLAIMS_PER_RAW_OUTPUT: return
   segments, filtered` early return (paired with the MAX_CLAIMS_PER_RAW_OUTPUT = 64 constant).
   user-visible impact: for this run, 7 of 12 agent reports were truncated (up to 86% of
   bear_researcher's commentary, 1,297 sentences total across the run) with no counter anywhere
   indicating this happened; run_audit.json's own raw_agent_output_count/raw_claim_count silently
   undercount the true input size.
   smallest correct follow-up scope: raise or remove the cap for report-level segmentation (the cap's
   apparent original intent -- bounding a single claim record's own size/count -- is already separately
   enforced by MAX_CLAIM_CHARS per-claim), or at minimum add a `segmentation_truncated_count` /
   `segmentation_truncated_agents` field to run_audit.json so this loss becomes visible and auditable
   even before any cap-limit change is made.

2. severity: MEDIUM (systemic false-positive pattern, confirmed to recur, not a one-off)
   root cause: reported_price_extractor.py's _DISQUALIFYING_TERMS list does not cover
   technical/statistical price-derived indicator vocabulary (Bollinger Bands, SMA, EMA, ATR, MACD, RSI),
   so a bare "$X on <date>" mention of a technical indicator is extracted and compared against the real
   OHLC range as if it were a stock-price claim.
   file/function/line: comqutor_alpha/data_sanity/reported_price_extractor.py, _DISQUALIFYING_TERMS
   (lines 32-39) and _BARE_PRICE_DATE_PATTERN / _match_price_date() (lines 82-84, 145-163).
   user-visible impact: 3 of this run's 4 total "reported price" extractions (75%) are technical
   indicators, not stock prices; 2 of the 3 surfaced as a warning/critical Data Quality issue that reads
   to a user as "the analyst report may contain a wrong stock price," when in fact both are entirely
   correct technical-indicator readings.
   smallest correct follow-up scope: extend _DISQUALIFYING_TERMS with a short, narrow list of
   technical-indicator vocabulary (e.g. "sma", "ema", "bollinger", "band", "atr", "macd", "rsi", "moving
   average") -- the same conservative, narrow-list pattern already used for eps/revenue/market cap/price
   target, requiring no change to the comparison/threshold logic itself (verified correct).

3. severity: LOW (product-design gap, not a data-availability gap)
   root cause: the Node Detail EmptyState fallback renders only a title and a fixed sentence, never the
   claim_ids/evidence/agents fields already present on the same selectedNode object; separately,
   selectedNodeActivation is computed via .find() rather than rendering every entry in the (list-typed)
   alpha_ids field.
   file/function/line: frontend/src/pages/StructureGraphPage.tsx:135-136, :211-215.
   user-visible impact: a user sees only "This factor node is not mapped to a scored Alpha." with no
   indication that the factor was actually mentioned by real analysts, in real claims, with a
   near-miss Alpha score (0.305 vs. a 0.35 bar) -- for this run, true for "AI CapEx" and "Inference
   Demand". A future node with 2+ committed alphas would also only ever show one of them.
   smallest correct follow-up scope: frontend-only change to surface the already-available
   claim_ids/evidence/agents in the fallback state, and to render every alpha_ids entry rather than only
   the first match.

4. severity: LOW (open question, not a confirmed defect)
   root cause: unclear -- Data Sanity severity assignment for dividend events is correctly "info" by
   construction, but the frontend's visual placement of these items in what the audit brief describes as
   a pink/warning-colored region was not traced to an exact line of UI code within this audit's scope.
   file/function/line: not identified (frontend Data Quality rendering, exact component/branch not
   isolated).
   user-visible impact: a user may perceive routine, informational dividend events as more alarming than
   intended if presentation does not match severity.
   smallest correct follow-up scope: a short, dedicated frontend-only follow-up to trace the exact
   component/CSS class deciding color-by-severity for Data Quality items.

Do Not Fix Yet:
- MAX_CLAIMS_PER_RAW_OUTPUT was not changed (Defect 1).
- _DISQUALIFYING_TERMS was not modified (Defect 2).
- FACTOR_ALIASES was not modified (including the narrow "fed cut"/"fed cuts" alias-plurality
  observation noted in Section C).
- relation_grammar.py, structure_extractor.py, graph_builder.py, activation_scorer(_v2).py were not
  modified.
- StructureGraphPage.tsx / any frontend file was not modified (Defects 3 and 4).
- No historical artifact, database row, or test was modified or created.

Recommended Next Action:
MULTIPLE_INDEPENDENT_REPAIRS_REQUIRED

(Two independent, narrowly-scoped backend defects were found -- the segmentation cap in Defect 1 and
the technical-indicator false-positive pattern in Defect 2 -- plus a frontend product-design gap
(Defect 3) that is real but does not, on its own, require a "repair" so much as a straightforward
provenance-surfacing change. None of the three found defects is the proximate cause of this specific
run's 0-edge outcome, which is independently confirmed honest (HONEST_ZERO_EDGE_RUN); they are reported
because they are real, verified, and currently invisible, not because fixing them would have changed
this run's graph.)
```

---

## H. Validation

```
Targeted tests run (subset directly touching the modules inspected in this audit):
  pytest tests/test_structure_extractor.py tests/test_relation_grammar.py tests/test_claim_quality.py \
         tests/test_structured_output_adapter.py tests/test_alpha_mapper.py tests/test_data_sanity*.py \
         tests/test_agent_outputs_api.py -q
  -> all passed, 0 failed (no test file was modified; this is the pre-existing suite as of this
     session's baseline, run purely to confirm the environment used for the read-only replay is not
     itself broken)

git diff --check -> exit 0, no whitespace errors

Production code modified: No
Tests modified: No
Database writes: 0 (every DB access in this audit was a read-only SELECT against the real Postgres
                    database via COMQUTOR_DATABASE_URL)
Historical artifact writes: 0 (verified: no file under outputs/runs/61f3e019-.../ was touched; all
                              replay work happened against an isolated scratchpad copy of
                              metadata.json + raw_agent_outputs.json)
Provider calls: 0
LLM calls: 0 (llm_gateway=None throughout every replay call, matching this run's own
              llm_enabled: false)
Network calls: 0
New research runs: 0
Commit/push: No
```
