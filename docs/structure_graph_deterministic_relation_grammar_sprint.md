# Structure Graph Deterministic Relation Grammar Sprint

## A. Baseline

- Branch: `comqutor-structure-layer`
- HEAD: `2fe129705d824d46b4bcf7f0fc1eb43e27972824` (unchanged throughout; no commit made)
- Worktree at start: clean except one untracked file from the immediately preceding
  (unrelated) Factor Resolution Contract and Alias Impact Review Sprint
  (`docs/factor_resolution_contract_and_alias_impact_review.md`), which this Sprint
  did not touch.
- Python: 3.13.5 (`.venv`)
- Baseline targeted tests (`tests/test_structure_extractor.py tests/test_graph_builder.py`):
  48 passed.
- Baseline full offline suite (`python -m pytest -m "not integration" -q`): 2005 passed,
  1 skipped, 47 deselected, 0 failed.
- Baseline Ruff (`structure_extractor.py`, `factor_normalizer.py`, `claim_semantics.py`,
  `graph_builder.py`): 1 pre-existing, unrelated `I001` (import order) in
  `structure_extractor.py`, present before this Sprint touched anything.
- `tradingagents/`: 0 uncommitted modifications (clean).

## B. Existing relation logic found (read before writing any code)

Read in full: `comqutor_alpha/structure_engine/structure_extractor.py`,
`comqutor_alpha/structure_engine/factor_normalizer.py`,
`comqutor_alpha/structure_engine/claim_semantics.py`,
`comqutor_alpha/graph_engine/graph_builder.py`, `tests/test_structure_extractor.py`,
`tests/test_graph_builder.py`.

Pre-Sprint relation extraction lived entirely in `structure_extractor.py`:
`ACTIVE_CAUSAL_PATTERN`, `ACTIVE_SUPPORT_PATTERN`, `PASSIVE_RELATION_PATTERN`,
`CONFLICT_WORDS`, `CAUSAL_RANK`, and `_extract_edges()`. Endpoint resolution was an
**unbounded all-pairs scan**: for every pair of factor mentions in the whole
(punctuation-fully-stripped) evidence text, it searched the entire bridge substring
between them for a relation verb, regardless of how many clause boundaries or other
factor mentions the bridge crossed. This is the specific bug this Sprint's "Factor
endpoint 配对" (nearest-clause-neighbor) requirement targets: see Section D and the
real SNDK finding in Section F, where this exact all-pairs behavior produced a
technically-plausible-looking but linguistically wrong edge
(`AI Infrastructure -> Datacenter CapEx` instead of the grammatically correct
`AI Infrastructure -> Semiconductor Cycle`) on a real production claim.

`graph_builder.py` was read in full and found to need **no change**: its
self-loop/dangling-reference/invalid-type/invalid-weight rejection and
claim-scoped `alpha_ids` attachment are independent of how edges are produced
upstream, and every new edge this Sprint's Extractor produces already conforms to
the existing `_edge()` schema untouched.

## C. Files changed

- `comqutor_alpha/structure_engine/relation_grammar.py` (**new**) -- pure-function
  relation grammar: `CAUSAL_RANK`/`GROWTH_FACTORS`/`RISK_FACTORS` (moved here
  unchanged), `plausible_causal_direction()` (moved, one narrow addition -- see
  Section D), the 8 rule families, `RelationCandidate`, `extract_relation_candidates()`,
  `match_conflicting()`, and the assertion-status/confidence/reason helpers (moved,
  logic unchanged). Justification for a new file rather than extending
  `structure_extractor.py` in place: the brief itself only permits this when "pattern
  definitions 过于复杂" -- 8 priority-ordered rule families, clause segmentation,
  clause-local nearest-neighbor endpoint resolution, and same-span overlapping-alias
  detection is exactly that threshold, and the brief explicitly names this file as the
  allowed location.
- `comqutor_alpha/structure_engine/structure_extractor.py` (**modified**) -- `_extract_edges()`
  now delegates to `relation_grammar.extract_relation_candidates()` +
  `match_conflicting()` instead of containing the pattern logic itself; `_edge()`,
  `_extract_factors()`, node construction, and the LLM-edge validation path
  (`_validated_llm_edges`, `_llm_relation_is_evidence_backed`, gated by the
  still-disabled-by-default `COMQUTOR_WEEK2_LLM_ENABLED`) are otherwise untouched
  except for importing the relocated pattern names.
- `tests/test_relation_grammar.py` (**new**) -- 35 rule-level tests exercising
  `relation_grammar.py` directly.
- `tests/test_structure_extractor.py` (**modified**) -- added the 7 mandatory
  acceptance sentences, 12 negative-grammar-variant cases, 1 common-object case, and
  1 full-provenance case (21 new tests; existing 21 tests untouched).
- `docs/structure_graph_deterministic_relation_grammar_sprint.md` (this report, new).

No other file was modified. `graph_builder.py`, `alpha_mapper.py`, `factor_normalizer.py`,
`FACTOR_ALIASES`, taxonomy, Activation, Conflict Detector, Exposure, persistence schema,
frontend, and `tradingagents/` were not touched.

## D. New pattern families (priority order actually applied)

| # | Family | Direction | Example | Rule name |
|---|---|---|---|---|
| 1 | REVERSE_PASSIVE | REVERSE | "Revenue Growth is driven primarily by AI Demand." | `reverse_passive_relation` |
| 2 | FORWARD_MULTIWORD | FORWARD | "AI CapEx translates into Datacenter CapEx." | `forward_multiword_relation` |
| 3 | REVERSE_MULTIWORD | REVERSE | "Revenue Growth benefits from AI Demand." | `reverse_multiword_relation` |
| 4 | PREFIX_CAUSE | REVERSE | "Because of AI Demand, Revenue Growth is accelerating." | `prefix_cause_relation` |
| 5 | WITH_EMBEDDED_RELATION | both | "With AI Demand driving Revenue Growth..." / "..., with support from AI Demand..." | `forward_transitive_causal` / `with_support_from_relation` |
| 6 | FORWARD_TRANSITIVE | FORWARD | "AI Demand drives Revenue Growth." | `forward_transitive_causal` / `forward_transitive_supportive` |
| 7 | CONDITIONAL | FORWARD, conditional | "If AI Demand remains strong, Revenue Growth could accelerate." | `conditional_relation` |
| 8 | CONFLICTING | n/a (serialization only) | "AI Demand is strong, but rich valuation creates downside risk." | `risk_factor_conflicts_with_growth_factor` (unchanged) |

One additional cross-clause mechanism was required beyond the 8 named families:
**comma-offset participial reduced relative clauses** ("Storage demand strength,
driven by hyperscaler AI capex, is broad.") -- the no-auxiliary REVERSE_PASSIVE form
(`driven by`, no preceding "is/are/was/were") is, in real text, frequently a
parenthetical clause whose target is the *preceding* clause's own subject, not
anything in its own clause. This is architecturally the same pattern as
WITH_EMBEDDED_RELATION's "..., with support from B..." (which the brief already
requires to reach into the preceding clause) applied to REVERSE_PASSIVE's
no-auxiliary form specifically -- the full-auxiliary form ("X is driven by Y") is
deliberately excluded from this reach, since it is ordinarily a clause's own main
verb (see `tests/test_relation_grammar.py::test_full_auxiliary_passive_does_not_reach_across_a_comma_into_an_unrelated_clause`).
This was discovered as a forcing regression against a real, pre-existing test (see
Section F) and is not an invented convenience.

Forward causal verbs (`FORWARD_CAUSAL_VERBS`): cause, drive, boost, fuel, raise,
increase, reduce, lower, pressure, constrain, limit, trigger, create, generate,
produce, accelerate, slow, compress, undermine, push, expand (with conjugations).
Forward supportive verbs: support, reinforce, confirm, enable, help, strengthen,
benefit (bare transitive form only -- REVERSE_MULTIWORD's higher-priority "benefits
from" claims the phrase first whenever "from" follows, so the two never collide).

### Clause segmentation and endpoint pairing

Text is lightly normalized (NFKC, lowercase, dash-to-space) **without** stripping
`, . ; : ? !`, then split into clauses on `, . ; :` and the subordinating/contrast
words `but however although while whereas yet` (never on "and"/"or", so a shared
compound predicate's co-objects stay in one clause -- required for the
common-object negative tests). For each relation-verb match, the nearest factor
mention strictly to its left and strictly to its right *within that same clause*
is resolved as source/target per the rule's direction; a missing side, or
`source == target`, aborts that candidate. A literal `?` anywhere in the claim
aborts the whole claim (no assertion_status exists for questions in the current
schema, so this is a hard abstain, not a guess).

### Same-span overlapping-alias endpoints

Every clause's factor mentions are checked for span overlap across *different*
factors before any endpoint is picked; an overlapping factor is excluded from
`nearest_left`/`nearest_right` candidacy entirely, so a relation-verb near an
overlapping span (e.g. "AI infrastructure spending drives Revenue Growth.", where
AI CapEx/Datacenter CapEx/AI Infrastructure all match the same phrase) abstains
rather than arbitrarily choosing one of the colliding factors
(`AMBIGUOUS_OVERLAPPING_FACTOR_ENDPOINT` in spirit -- verified directly in
`tests/test_relation_grammar.py::test_overlapping_alias_span_is_not_split_into_two_endpoints`
and its reverse-passive counterpart). `FACTOR_ALIASES` itself was not modified.

### CAUSAL_RANK: changed, narrowly, with forcing evidence

`plausible_causal_direction()` gained one addition: a 2-pair explicit allowlist
(`_RANK_EXCEPTION_PAIRS = {("AI Infrastructure", "Semiconductor Cycle"),
("Datacenter CapEx", "Semiconductor Cycle")}`), not a general rank-tolerance
widening. This was **not optional** -- it was forced by a real, pre-existing
(not authored by this Sprint) test in `tests/test_structure_correctness_sprint.py`
requiring `AI Infrastructure -> Semiconductor Cycle` (an infrastructure-buildout
factor, rank 2, causing derived component/memory demand, rank 1 -- a genuine
"derived demand" economic relationship) to be admitted; this Sprint's corrected
nearest-clause-neighbor endpoint resolution (replacing the old unbounded
all-pairs scan) resolves that claim's true grammatical target as
`Semiconductor Cycle`, which the un-widened rank rule rejected.

- **Positive test**: `test_causal_rank_exception_pair_admits_infrastructure_driving_semiconductor_cycle`
  and the 4 previously-failing `test_structure_correctness_sprint.py` tests (now
  passing).
- **Negative test proving the exception is narrow, not a general relaxation**:
  `test_causal_rank_exception_is_narrow_not_a_general_rank_2_to_1_pass` --
  `GPU Demand (rank 2) drives AI Demand (rank 1)` remains rejected, exactly as the
  pre-existing (untouched) `test_reversed_causal_phrasing_does_not_emit_wrong_direction_edge`
  already required.

One *additional*, non-hypothetical case was found and **deliberately not fixed**:
a risk factor (Recession Risk, rank 3) causally pressuring a rank-1 demand factor
(e.g. "AI CapEx faces pressure from Recession Risk" / "AI CapEx is exposed to
Recession Risk") is rejected by the current rank rule, and is economically
plausible. It is not added to `_RANK_EXCEPTION_PAIRS` because, unlike the pair
above, no existing or mandated test in this Sprint requires it, and a
risk-factor-as-source exception is a materially broader, less-constrained change
(RISK_FACTORS could plausibly pressure many rank-1/2 factors, not one named pair)
that deserves its own dedicated review under less time pressure rather than being
folded in here without a forcing case. `CAUSAL_RANK changed: Yes` (narrowly,
2-pair allowlist only) -- this is the honest answer; the general rank comparison
formula itself (`source_rank <= target_rank`) is byte-identical to before.

## E. Tests

### Rule-level (`tests/test_relation_grammar.py`, 35 tests)

Each of the 8 families' positive case; REVERSE_MULTIWORD vs FORWARD_MULTIWORD
direction contrast (`results from` vs `results in`); transitive vs "from"-reversed
`benefits`/`benefits from` direction contrast; active/passive synonym agreement;
conditional rule-name distinction; clause-boundary non-reach (a comma severs
pairing); 3-factor sentence non-permutation; overlapping-alias endpoint rejection
(both forward and reverse-passive); common-object false positives (bare verb and
`driven by` compound-object forms); interrogative abstention (both active and
passive phrasing); whitelisted-adverb tolerance (all 6) plus an explicit
not-a-wildcard negative (an unlisted adverb is rejected); the numeric-magnitude
guard (`increased by 20 percent`); input-order independence; both CAUSAL_RANK
tests from Section D; and the 3 new comma-offset-participial tests.

### Full-pipeline (`tests/test_structure_extractor.py`, +21 tests)

All 7 mandatory acceptance sentences verbatim from the brief, each asserting
source/target/edge_type (and `assertion_status == "conditional"` for the
if-clause case); the 12 mandatory negative variants
(discusses/includes/follows/compares/mentions/remain-list/increased-by-percent/
compared-to/correlated-with/moved-with/conjunctive-if/interrogative), each
parametrized and asserting `edges == []`; the "Higher rates pressure X and Y"
common-object case with an unresolvable subject; and a full-provenance check
(`source_record_id`, `source_agent_output_id`, `evidence`, `source_claim` all
non-empty on a new-family edge).

### Command and result

```
python -m pytest -q tests/test_relation_grammar.py tests/test_structure_extractor.py \
  tests/test_graph_builder.py tests/test_structure_correctness_sprint.py
-> 128 passed
```

All 4 pre-existing `test_structure_correctness_sprint.py` failures encountered
mid-Sprint (Section F below explains root cause and fix) are now passing, with
zero weakening of their assertions -- the fix was in the implementation
(nearest-clause-neighbor resolution + the narrow CAUSAL_RANK exception + the
comma-offset participial cross-clause reach), never in loosening a test.

## F. Replay (real data, read-only, nothing written)

Searched **all 4 completed run artifact sets** present in `outputs/runs/` (not only
AMD/MU): AMD (`66794ad5-b3a9-4fcc-aa5f-7a6d7957b7c1`, 669 claims), MU
(`0ba23540-0623-4d05-a670-098fbbfec1d1`, 654 claims), NVDA
(`4ca7dafa-6ac1-4d94-add0-f6f93b1af150`, 681 claims), SNDK
(`8d21c047-fc0a-4d94-957d-3787f353a544`, 664 claims). "Before" was produced by
loading the exact pre-Sprint `structure_extractor.py` in isolation via
`importlib` from `git show HEAD:...` (never reverting the live, patched
worktree); "after" is the current in-worktree module. Both were run purely in
memory against the real, unmodified `structured_agent_outputs.json` for each run,
then fed through the real, unmodified `graph_builder.build_structure_graph()`
together with each run's real, unmodified `alpha_matches.json` to get admitted
graph-edge counts. No `save_*`/`persist_*`/`write_*` function was called anywhere
in the replay script.

| Metric | AMD Before | AMD After | MU Before | MU After | NVDA Before | NVDA After | SNDK Before | SNDK After |
|---|---:|---:|---:|---:|---:|---:|---:|---:|
| Claims | 669 | 669 | 654 | 654 | 681 | 681 | 664 | 664 |
| Candidate edges | 0 | 0 | 0 | 0 | 0 | 0 | 4 | 2 |
| Valid graph edges | 0 | 0 | 0 | 0 | 0 | 0 | 4 | 2 |

AMD, MU, and NVDA remain correctly at 0 candidate/0 graph edges both before and
after -- confirmed by direct inspection that none of their claims contain an
explicit, clause-local, two-distinct-factor relation (consistent with the prior
Structure Extractor Relation Coverage Sprint's and Factor Resolution Contract
Review's findings for AMD/MU specifically). **This is the correct result, not a
gap**: no claim was fabricated to force a nonzero count.

### SNDK: real live positive-edge case found (no synthetic fixture needed)

SNDK is a genuine completed Research run (not a fixture) and supplies a real
positive-edge case, so `LIVE_POSITIVE_EDGE_CASE_NOT_AVAILABLE` does **not**
apply. Full before/after detail:

| Claim (source_record_id suffix) | Before | After | Verdict |
|---|---|---|---|
| `sentiment_agent:sentiment_report:claim:49` | `AI Infrastructure -> Datacenter CapEx` (asserted) | `AI Infrastructure -> Semiconductor Cycle` (asserted) | **Corrected**, not lost. Real claim: *"AI infrastructure demand driving memory — NAND flash and storage demand from AI data center buildout is the fundamental bull thesis, reinforced by Zacks, Motley Fool, and StockTwits analysts alike."* The old all-pairs bridge scan skipped past the true, nearer object of "driving" ("...memory...and storage demand...", i.e. Semiconductor Cycle) merely because that pairing was rank-rejected, then opportunistically bridged all the way to the more distant "AI data center buildout" (Datacenter CapEx) instead. The new nearest-clause-neighbor resolution finds the grammatically correct, nearer object; the Section D CAUSAL_RANK exception (forced by this exact claim, via the sanitized fixture in `test_structure_correctness_sprint.py`) admits it. **This is this Sprint's live, evidence-backed positive edge.** |
| `research_manager:investment_plan:claim:21` | `Inference Demand -> AI CapEx` (negated) | `Inference Demand -> AI CapEx` (negated) | **Preserved**, rule name only changed from the old generic `active_causal_between_factors` to the more specific `forward_multiword_relation` (this claim's relation phrase is "feeding...into"). No behavior change. |
| `news_agent:news_report:claim:46` | `AI CapEx -> Semiconductor Cycle` (conditional) **and** `Inference Demand -> Semiconductor Cycle` (conditional) | *(abstains, 0 edges)* | **Correctly closed**, not a regression. Real claim: *"AI Capex Skepticism: IBM's warning has reignited debate about enterprise AI ROI, which could reduce forward memory demand forecasts."* The colon after "AI Capex Skepticism" is a headline-style label, not this sentence's grammatical subject; "which could reduce..." is a relative clause whose true antecedent ("enterprise AI ROI", "the debate", or "IBM's warning") is genuinely ambiguous across a comma boundary. The old implementation ignored both the colon and the comma entirely (it strips all punctuation before scanning) and opportunistically bridged both unrelated left-side factors to the one right-side factor. Adding a "which"-relative-clause cross-clause mechanism was considered and rejected: it is not one of the 8 required rule families, the antecedent is not reliably resolvable, and the brief explicitly requires abstaining on ambiguous/underspecified claims rather than inventing a new rule to force a match. |

Rejected/remaining-zero-edge claims across all 4 runs were spot-checked against
the corresponding pre-existing Structure Extractor Relation Coverage Sprint and
Factor Resolution Contract Review evidence tables (AMD claim:17/55, MU
claim:14/29/36, etc.) and continue to abstain for the same, already-documented
reasons (overlapping-alias collisions, unresolved factor-alias gaps out of this
Sprint's scope, genuinely ambiguous coordinate lists) -- none of that prior
analysis is superseded by this Sprint's grammar changes.

### Mapper follow-up

No new `FOLLOW_UP_MAPPER_REVIEW_REQUIRED` case was produced by this Sprint. The
Extractor-side gaps closed here (rank-exception pair, comma-offset participial
reach, nearest-neighbor endpoint resolution) are all internal to
`structure_extractor.py`/`relation_grammar.py`; none required touching factor
resolution, the Alpha Mapper, or the taxonomy. The previously-documented
factor-alias gaps (e.g. AMD claim:58/63/57/34's unresolved "revenue beats",
"guidance miss", "higher-for-longer rate regime") remain exactly as characterized
in the Factor Resolution Contract and Alias Impact Review Sprint -- out of this
Sprint's scope, unaffected by anything changed here.

## G. Scope verification

- Alpha Mapper (`alpha_mapper.py`) modified: **No**
- AI Alpha hard gates modified: **No**
- `factor_normalizer.py` / `FACTOR_ALIASES` modified: **No**
- Activation (v1/v2) modified: **No**
- Conflict Detector modified: **No**
- Exposure modified: **No**
- Taxonomy modified: **No**
- Graph Builder (`graph_builder.py`) modified: **No** (read in full; no bug found
  that required a change)
- Persistence schema modified: **No**
- Frontend modified: **No**
- `tradingagents/` modified: **No**
- Historical run artifacts modified: **No** (SHA-256 verified byte-identical for
  AMD/MU against this session's earlier-recorded baseline; NVDA/SNDK mtimes
  confirmed unchanged from 2026-07-17, predating this session)
- Ticker-specific or run-specific exceptions added: **No**
- New canonical relation invented to force an edge: **No**

## H. Final Gate

**PASS**

1. Explicit relations produce correct-direction edges: yes -- all 7 mandatory
   acceptance sentences verified, plus a real production example (SNDK claim:49).
2. Active and passive directions correct: yes (`test_active_and_passive_synonyms_agree_on_direction`).
3. Bare `to`/`by`/`with`/`from`/`on` never alone produce an edge: yes -- every
   pattern requires a full multi-word phrase or verb, never a bare preposition;
   verified by the negative-variant parametrized tests and the numeric-magnitude
   guard.
4. Ordinary verbs (discusses/includes/follows/compares/mentions) never produce
   an edge: yes, by omission from every verb whitelist (default-deny design),
   verified directly.
5. Coordinate lists, common objects, and interrogatives abstain: yes, verified
   (including the real SNDK "which"-relative-clause case, correctly left
   unresolved rather than forced).
6. Overlapping factor spans never become two endpoints: yes, verified both
   forward and reverse-passive.
7. Provenance (claim_id, source_agent_output_id, evidence, source_claim) is
   complete on every new edge: yes, verified directly.
8. Graph Builder receives and serializes the new edges unchanged: yes -- SNDK's
   2 after-edges pass through `build_structure_graph()` unmodified and become 2
   admitted graph edges with 0 rejections.
9. All existing tests pass: yes -- 2061 passed, 1 skipped, 0 failed on the full
   offline suite (vs. 2005/1/0 baseline; +56 net new tests, minus the 4 that were
   temporarily broken mid-Sprint and are now fixed and passing).
10. No AMD/MU (or NVDA/SNDK) edges were fabricated: yes -- AMD/MU/NVDA correctly
    remain at 0/0; SNDK's edge count (4->2) *decreased*, and every remaining and
    changed edge is individually justified against the real claim text in
    Section F.
11. Mapper, aliases, Activation, Conflict not modified: confirmed, Section G.

## Validation commands and results

```
python -m pytest -q tests/test_relation_grammar.py tests/test_structure_extractor.py \
  tests/test_graph_builder.py tests/test_structure_correctness_sprint.py
-> 128 passed

python -m pytest -m "not integration" -q
-> 2061 passed, 1 skipped, 47 deselected, 0 failed

python -m ruff check comqutor_alpha/structure_engine/relation_grammar.py \
  comqutor_alpha/structure_engine/structure_extractor.py \
  tests/test_relation_grammar.py tests/test_structure_extractor.py
-> All checks passed!

git diff --check
-> clean

git status --short
->  M comqutor_alpha/structure_engine/structure_extractor.py
    M tests/test_structure_extractor.py
   ?? comqutor_alpha/structure_engine/relation_grammar.py
   ?? tests/test_relation_grammar.py
   (plus the pre-existing, untouched prior-Sprint report file)
```

Provider calls: **ZERO**. LLM calls: **ZERO**. Database writes: **ZERO**.
Historical artifact writes: **ZERO**. No commit, no push, no tag.
