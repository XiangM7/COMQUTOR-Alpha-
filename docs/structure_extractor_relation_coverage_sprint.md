# Structure Extractor Relation Coverage Sprint

## A. Baseline

- Branch: `comqutor-structure-layer`
- HEAD: `413c2c259064979ffc468cbad466105b5cab3eac` (unchanged throughout)
- Worktree: dirty at Sprint start, with 39 files already modified/untracked from prior,
  previously-verified sprints (Structure Correctness Sprint, AI Alpha Mapper Discrimination
  Sprint, Data Sanity, Exposure Rubric Contract, etc.). `tradingagents/` itself was clean
  (0 modified files). The pre-existing diff set was recorded before any edit in this Sprint,
  making this Sprint's own changes unambiguously distinguishable (see Section D) -- not
  `BLOCKED_DIRTY_WORKTREE`.
- Python: 3.13.5 (`.venv`, the environment the project's own test/ruff commands resolve to)
- Baseline test command (from `.github/workflows/ci.yml`): `python -m pytest -m "not integration" -q`
  - Baseline result: **2005 passed, 1 skipped, 47 deselected, 0 failed**
- Baseline Ruff (targeted, matching this Sprint's files): `ruff check comqutor_alpha/structure_engine/structure_extractor.py comqutor_alpha/structure_engine/factor_normalizer.py`
  - Result: 1 pre-existing `I001` (unsorted import block) in `structure_extractor.py`, present
    before this Sprint touched anything (inherited from the prior Structure Correctness Sprint).
    Not in CI's maintained Ruff file list either. Left untouched -- no unsolicited whole-file
    reformatting.

## B. Evidence recovered

| Field | AMD | MU |
|---|---|---|
| Complete run ID | `66794ad5-b3a9-4fcc-aa5f-7a6d7957b7c1` | `0ba23540-0623-4d05-a670-098fbbfec1d1` |
| Ticker | AMD | MU |
| Artifact path | `outputs/runs/66794ad5-b3a9-4fcc-aa5f-7a6d7957b7c1/` | `outputs/runs/0ba23540-0623-4d05-a670-098fbbfec1d1/` |
| Number of claims | 669 | 654 |
| Number of mapped claims (`matched_alpha_count`) | 23 | 32 |
| Candidate edges before fix | 0 (`deterministic_edge_count=0`, `llm_edge_count=0`) | 0 |
| Graph edges before fix | 0 | 0 |
| Persistence edges before fix | 0 (`structure_graph.json` on disk is what gets persisted; `graph_metrics.rejected_edges` is all-zero across every rejection category, proving Graph Builder never received a single candidate edge) | 0 |

Source artifact checksums (SHA-256 of `structured_agent_outputs.json`, verified unchanged before/after):
- AMD: `343edf67e6bdca97d6e765811905d79515f0adf4b77e4ea2ced24b501ce4b13b`
- MU: `c6edd8beb02eddedd9b7db27df0a83e1acc3371151600259c22f79e05ea6371f`

### Evidence table (real claims only -- nothing inferred from financial/industry common sense)

| Claim ID | Agent | Original claim (verbatim) | Explicit relation phrase | Expected source | Expected target | Expected relation type | Current extractor result | Failure reason |
|---|---|---|---|---|---|---|---|---|
| `MU:fundamental_agent:fundamentals_report:claim:14` | fundamental_agent | "Micron has undergone a historic earnings inflection, driven primarily by AI-related HBM (High Bandwidth Memory) demand, DRAM pricing recovery, and data center spending acceleration." | "driven ... by" | *(none -- see reclassification below)* | *(none)* | *(none)* | 0 edges, 2 factors detected (Datacenter CapEx, Semiconductor Cycle) | `RELATION_PHRASE_NOT_COVERED` on first inspection ("primarily" breaks `driven\s+by`); **on rigorous re-analysis this is `NOT_AN_EXTRACTOR_BUG`** -- the two detected factors are syntactic co-objects of one shared predicate whose real target ("earnings inflection") is not a taxonomy factor at all. They are not in a source→target relationship with each other; asserting one would fabricate a relation. See Section C. |
| `AMD:news_agent:news_report:claim:17` | news_agent | "Investors are increasingly scrutinizing the heavy AI infrastructure spending by hyperscalers (Microsoft, Meta, Alphabet, Amazon), questioning whether returns on investment justify the capital outlay." | none | -- | -- | -- | 0 edges, 3 factors detected (AI CapEx, Datacenter CapEx, AI Infrastructure) | `NOT_AN_EXTRACTOR_BUG` -- all 3 factors are aliases of one overlapping phrase span ("AI infrastructure spending"), not 2 distinct concepts. |
| `AMD:bear_researcher:investment_debate_state.bear_history:claim:53` | bear_researcher | "AMD's entire bull case rests on continued hyperscaler AI infrastructure spending." | none | -- | -- | -- | 0 edges, 3 overlapping factors | `NOT_AN_EXTRACTOR_BUG` -- same overlapping-alias pattern as above. |
| `AMD:trader:trader_investment_plan:claim:4` | trader | "...are legitimate enough to argue against maximum aggression ahead of earnings, but do not undermine the medium-to-long-term investment thesis anchored in 38% revenue growth, ... and a premier AI infrastructure positioning." | none (a list, "anchored in X, Y, and Z") | -- | -- | -- | 0 edges, factors AI Infrastructure + Revenue Growth | `NOT_AN_EXTRACTOR_BUG` / `CLAIM_NOT_EXPLICIT_ENOUGH` -- a list of things a thesis is anchored in, not a causal claim between the two factors. |
| `AMD:news_agent:news_report:claim:55` | news_agent | "Recession Risk Remains Low: US recession probability at just 10% means the macro backdrop remains supportive for enterprise/cloud capex" | "remains supportive for" (adjectival, not the verb forms in `ACTIVE_SUPPORT_PATTERN`) | -- | -- | -- | 0 edges, factors AI CapEx + Recession Risk | `NOT_AN_EXTRACTOR_BUG` -- even if "supportive" were added to the pattern, the existing (frozen, unmodified) `RISK_FACTORS` guard in `_extract_edges` already refuses supportive edges touching a risk factor, because the claim's real polarity is "LOW risk supports capex", not "Recession Risk supports capex". Adding the pattern would produce zero net benefit. |
| `MU:research_manager:investment_plan:claim:15` | research_manager | "Samsung yield recovery, HBM oversupply, CXMT competition, hyperscaler capex pause, and rate-driven multiple compression all need to arrive simultaneously and severely to bring forward EPS from $153.74..." | none (conjunctive list) | -- | -- | -- | 0 edges, factors AI CapEx + Valuation Risk | `NOT_AN_EXTRACTOR_BUG` -- a list of conditions that must co-occur, not one causing the other. |
| `MU:news_agent:news_report:claim:29` | news_agent | "The market is in a state of \"AI jitter\" — while AI infrastructure spending remains robust, investors are growing anxious..." | "while" | -- | -- | -- | 0 edges, 3 overlapping factors | `NOT_AN_EXTRACTOR_BUG` -- overlapping-alias pattern; "while" is a `CONFLICT_WORDS` trigger but requires one `RISK_FACTORS` + one `GROWTH_FACTORS` member, neither of which any of the 3 overlapping AI-infra aliases is. |
| `MU:bull_researcher:investment_debate_state.bull_history:claim:16` | bull_researcher | "...when was the last time a semiconductor cycle happened while hyperscalers were collectively spending hundreds of billions...building AI infrastructure that fundamentally requires high-bandwidth memory?" | "while" / "requires" | -- | -- | -- | 0 edges, factors AI Infrastructure + Semiconductor Cycle | `CLAIM_NOT_EXPLICIT_ENOUGH` -- rhetorical question, not an assertion. |
| `MU:research_manager:investment_plan:claim:36` | research_manager | "Any reiteration or increase of 2026 AI infrastructure spending is a direct HBM demand confirmation." | "is a direct ... confirmation" | AI Infrastructure | HBM demand | supportive | 0 edges, 3 overlapping factors, "HBM demand" not a taxonomy factor at all | `TARGET_SPAN_NOT_PARSED` / `TARGET_NORMALIZATION_FAILED` -- real target concept has no alias anywhere in the taxonomy. **Out of scope** (see Section D). |
| `AMD:news_agent:news_report:claim:58` | news_agent | "...whether Lisa Su's AI demand confidence translates into revenue beats that can justify the elevated valuation." | "translates into" | AI Demand | Revenue Growth | causal | 0 edges, only 1 factor detected (AI Demand) | `RELATION_PHRASE_NOT_COVERED` ("translates into" absent from `ACTIVE_CAUSAL_PATTERN`) **and** `TARGET_SPAN_NOT_PARSED` ("revenue beats" not in the `Revenue Growth` alias list). Fixing the target requires editing `factor_normalizer.py`'s shared `FACTOR_ALIASES`, which is also read by `alpha_mapper.py` -- **out of scope**, see Section D. |
| `AMD:fundamental_agent:fundamentals_report:claim:63` | fundamental_agent | "Any guidance miss could trigger significant multiple compression." | "could trigger" | (guidance miss) | Valuation Risk | causal | 0 edges, only 1 factor (Valuation Risk) | `RELATION_PHRASE_NOT_COVERED` ("trigger" absent) **and** `SOURCE_SPAN_NOT_PARSED` ("guidance miss" has no factor anywhere in the taxonomy). Out of scope. |
| `AMD:news_agent:news_report:claim:57` | news_agent | "...a \"higher-for-longer\" rate regime (85% probability of zero cuts) applies persistent multiple compression pressure." | "applies ... pressure" | (higher-for-longer rate regime) | Valuation Risk | causal | 0 edges, only 1 factor (Valuation Risk) | `RELATION_PHRASE_NOT_COVERED` **and** `SOURCE_SPAN_NOT_PARSED` -- `Rate Cut Cycle` aliases only cover the falling-rate direction, not "rates staying elevated". Out of scope. |
| `AMD:research_manager:investment_plan:claim:34` | research_manager | "...if AMD confirms demand is intact and the selloff is multiple compression rather than revenue revision, this becomes a high-conviction accumulation zone..." | "if...then" (conditional) | (demand) / (revenue revision) | Valuation Risk | causal | 0 edges, only 1 factor (Valuation Risk); conditional if-then path also requires >= 2 factors | `SOURCE_SPAN_NOT_PARSED` + `TARGET_SPAN_NOT_PARSED` -- bare "demand" and "revenue revision" have no alias coverage. Out of scope. |

No claim in either run was found with an explicit, unambiguous `source → relation → target` between **two already-resolvable taxonomy factors** that the current Extractor fails to wire up for a purely pattern-coverage reason. Every genuine relation-phrase gap found (`translates into`, `trigger`, `applies ... pressure`, adjectival `supportive`, `driven primarily by`) co-occurs with either (a) a target/source concept with no taxonomy alias at all, (b) a pre-existing, correctly-firing guard (`RISK_FACTORS` exclusion), or (c) factors that are syntactic siblings rather than a real source/target pair.

## C. Root cause (per claim)

- **Relation phrase gap, real but not exploitable in-scope**: `translates into`, `trigger`/`triggers`/`could trigger`, `applies ... pressure`, adjectival `supportive`, and the `driven <adverb> by` insertion-word case are all genuinely absent/blocked in the current `ACTIVE_CAUSAL_PATTERN` / `ACTIVE_SUPPORT_PATTERN` / `PASSIVE_RELATION_PATTERN`. An initial fix (tolerating one `-ly` adverb between a passive participle and "by") was implemented and empirically tested against the real MU claim -- see Section D for why it was reverted.
- **Source parsing gap (out of scope)**: "guidance miss", "higher-for-longer rate regime" have zero alias coverage anywhere in `factor_normalizer.py`.
- **Target parsing gap (out of scope)**: "revenue beats", "revenue revision", "HBM demand" have zero alias coverage.
- **Normalization gap (out of scope)**: `Rate Cut Cycle`'s aliases are asymmetric -- only the falling-rate direction is covered, not "rates staying elevated"/"zero cuts".
- **Non-bug / correctly-abstaining cases**: overlapping-factor-alias claims (3 aliases matching one phrase span), conjunctive condition lists, rhetorical questions, and the pre-existing `RISK_FACTORS` supportive-edge guard. All correctly produce 0 edges today and must keep doing so.

## D. Changes

**Net functional code diff introduced by this Sprint: none.**

An initial, narrowly-scoped fix was implemented and then reverted after empirical verification proved it produced no realized benefit:

- `comqutor_alpha/structure_engine/structure_extractor.py` -- `PASSIVE_RELATION_PATTERN` was temporarily widened to tolerate one `-ly` adverb between a passive participle and "by" (e.g. "driven primarily by"), motivated by `MU:fundamental_agent:fundamentals_report:claim:14`. Testing the fix directly against the real claim text showed `_extract_edges` still produces 0 edges: the claim's two known factors (Datacenter CapEx, Semiconductor Cycle) are positioned *after* "driven primarily by" as co-objects of one shared predicate (`... driven primarily by [A], [B], and [C]`), not as a source *and* target of each other -- `_extract_edges` only searches for a relation phrase in the bridge *between* two factor mentions, and both mentions here are on the same side of the predicate. Emitting an edge between the two co-objects would fabricate a source→target relation the claim never asserts, which Section 7.4 of the Sprint brief explicitly forbids ("不得根据句子顺序推断 source 和 target"). The change was reverted; `structure_extractor.py` is byte-identical to its pre-Sprint state (confirmed via re-read).
- `tests/test_structure_extractor.py` -- **5 new regression tests added**, each built from a verbatim real AMD/MU audited claim, locking in the *correct* current zero-edge behavior so a future change cannot "fix" these cases by fabricating a relation:
  - `test_driven_by_compound_object_list_does_not_fabricate_edge_between_siblings` (MU claim:14)
  - `test_overlapping_factor_aliases_for_one_phrase_do_not_self_relate` (AMD claim:17)
  - `test_conjunctive_condition_list_does_not_imply_causal_pair` (MU claim:15)
  - `test_low_risk_supportive_language_stays_blocked_by_existing_risk_factor_guard` (AMD claim:55)
  - `test_single_factor_relation_claim_cannot_produce_an_edge` (AMD claim:58)

No other file was modified by this Sprint.

## E. Tests

| Test file | Test name | Positive case | Negative control | Command | Result |
|---|---|---|---|---|---|
| `tests/test_structure_extractor.py` | `test_driven_by_compound_object_list_does_not_fabricate_edge_between_siblings` | n/a (pure negative/abstain test) | asserts `edges == []` for the real MU claim | `pytest tests/test_structure_extractor.py -q` | PASS |
| `tests/test_structure_extractor.py` | `test_overlapping_factor_aliases_for_one_phrase_do_not_self_relate` | n/a | asserts `edges == []` | same | PASS |
| `tests/test_structure_extractor.py` | `test_conjunctive_condition_list_does_not_imply_causal_pair` | n/a | asserts `edges == []` | same | PASS |
| `tests/test_structure_extractor.py` | `test_low_risk_supportive_language_stays_blocked_by_existing_risk_factor_guard` | n/a | asserts `edges == []`, documents the existing `RISK_FACTORS` guard | same | PASS |
| `tests/test_structure_extractor.py` | `test_single_factor_relation_claim_cannot_produce_an_edge` | n/a | asserts `edges == []` when only 1 of 2 needed factors resolves | same | PASS |

`tests/test_structure_extractor.py -q -m "not integration"`: **21 passed** (16 pre-existing + 5 new), including the pre-existing acceptance cases `AI Demand -> GPU Demand`, `AI CapEx -> GPU Demand`, `GPU Demand -> NVDA Revenue Growth`, and the simple conflicting/supportive edges -- all untouched and still green.

## F. Replay

Read-only, offline, in-memory replay of the saved `structured_agent_outputs.json` for both runs through `extract_structures_from_records` (no LLM, no network, no writes to `outputs/runs/`; replay output written only to an isolated scratch location with `original_run_id`, `replay_timestamp`, `baseline_commit`, `source_artifact_sha256` recorded).

| Metric | AMD Before | AMD After | MU Before | MU After |
|---|---:|---:|---:|---:|
| Claims | 669 | 669 | 654 | 654 |
| Explicit relation claims (2-factor + genuine source→target) | 0 | 0 | 0 | 0 |
| Candidate edges | 0 | 0 | 0 | 0 |
| Valid graph edges | 0 | 0 | 0 | 0 |
| Rejected edges | 0 | 0 | 0 | 0 |
| Self-loops | 0 | 0 | 0 | 0 |
| Unsupported edges | 0 | 0 | 0 | 0 |
| Evidence-backed edges | 0 | 0 | 0 | 0 |

Newly generated edges this Sprint: **none** (no code changed the extractor's behavior).

Correctly-preserved zero-edge claims: all 9 multi-factor candidate claims across both runs (see Section B evidence table), plus the 4 AMD single-factor "page sentence" claims -- every one legitimately abstains under the current, unmodified rules.

### Mapper follow-up

- `FOLLOW_UP_MAPPER_REVIEW_REQUIRED` is **not** raised by this Sprint in the Alpha-Mapper-behavior sense (nothing here concerns `matched_alpha`/`score`/`ai_alpha_matches`). What *is* flagged for a separate, future review is a **factor-taxonomy/alias coverage gap** shared between the Extractor and the Mapper (`factor_normalizer.py`'s `FACTOR_ALIASES`):
  - Claim `AMD:news_agent:news_report:claim:58`: input received by the Extractor is `claim`/`evidence` = "...Lisa Su's AI demand confidence translates into revenue beats..."; missing factor: no alias maps "revenue beats" to `Revenue Growth`. Not an Extractor bug -- `factor_normalizer.py` is a shared dependency of both `structure_extractor.py` and `alpha_mapper.py`, and editing it would change Alpha Mapper's `factor_score` (explicitly forbidden by this Sprint). Suggested next step: an audit-only review (not a fix) of `FACTOR_ALIASES` coverage gaps against a larger claim sample, scoped and staffed separately from both the Extractor and the Mapper.
  - Claim `AMD:fundamental_agent:fundamentals_report:claim:63`: missing factor for "guidance miss" (no taxonomy concept exists for negative-guidance events at all -- this is arguably a new-factor/taxonomy question, not just an alias gap).
  - Claim `AMD:news_agent:news_report:claim:57`: missing the "rates staying elevated / zero cuts" direction of `Rate Cut Cycle` (an asymmetric-taxonomy gap).
  - Claim `MU:research_manager:investment_plan:claim:36`: missing factor for "HBM demand".

## G. Scope verification

- Mapper modified: **No**
- Taxonomy modified: **No**
- Graph Builder modified: **No**
- Activation modified: **No**
- Conflict modified: **No**
- Exposure modified: **No**
- Persistence schema modified: **No**
- Frontend modified: **No**
- `tradingagents/` upstream modified: **No**

## H. Final Gate

**PASS_WITH_FOLLOW_UP_MAPPER_REVIEW**

Evidence:
1. AMD and MU original audit runs recovered and verified byte-for-byte unchanged (SHA-256 before/after identical).
2. Every candidate coverage gap was evidence-backed (traced to a specific real claim) before any pattern was considered; the one candidate fix that was implemented was proven empirically -- against the real claim text, not assumption -- to produce no valid edge, and was reverted rather than kept as dead/unjustified surface area.
3. No claim in either run had an explicit, resolvable `source → relation → target` between two already-known factors that the Extractor was incorrectly dropping. Criterion 3 of the Gate ("所有审计确认的明确 relation claim 均产生正确合法 edge") is vacuously satisfied: zero such claims exist in the audited evidence.
4. Ambiguous/non-explicit/single-factor claims correctly continue to abstain (0 edges) -- verified via 5 new regression tests built from the exact real claim text.
5. No fabricated edges, no new self-loops, no empty source/target, no edge without evidence -- nothing was added that could cause any of these.
6. Original labels/canonical labels/evidence/provenance handling in `_edge()`/`_make_node()` untouched.
7. Mapper, taxonomy, Graph Builder, Activation, Conflict, Exposure, persistence schema, frontend, and `tradingagents/` all confirmed untouched (Section G).
8. Focused tests: 21/21 passed. Full offline suite: 2010 passed, 1 skipped, 0 failed (2005 baseline + 5 new). Ruff clean on all Sprint-touched files except one pre-existing, unrelated `I001` inherited from an earlier sprint (left untouched).
9. AMD/MU replay reproducible: same source checksum, same deterministic output, 0 candidate/graph edges before and after (correctly identical, since no functional code changed).
10. This report is complete per the required template.

The `FACTOR_ALIASES` coverage gaps identified for `AMD:news_agent:news_report:claim:58/57/63` and `MU:research_manager:investment_plan:claim:36` are the reason for the `_WITH_FOLLOW_UP_MAPPER_REVIEW` qualifier rather than a plain `PASS`: they are real, evidence-backed, but require a decision that spans both the Extractor and the (explicitly off-limits) Alpha Mapper, so they are handed off rather than fixed here.
