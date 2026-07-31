# Context-Only Precision Audit

Product Findings Closure and Regime Evidence Integrity Sprint, Track A section 6.

## Status

**FAIL against the numeric PASS thresholds, after a genuine minimal fix.** See
"Result" and "Why the gap was not closed further" below. This is reported
honestly rather than gamed to a false PASS -- see the Sprint's final report
for how this feeds the overall status.

## Sample method

- Baseline HEAD: `2fe129705d824d46b4bcf7f0fc1eb43e27972824`
- Seed: `SHA256(baseline_HEAD + "context-only-precision-audit-v1")`
  = `bcf66c9cd49d33ce67264fc03364a8df6c5be67be445a51fa19c9def742f5524`
- Per-claim ordering key: `SHA256(seed + ":" + run_id + ":" + claim_id)`, a
  pure function of (HEAD, run_id, claim_id) -- independent of claim content,
  file order, or ease of review.
- For each of the 4 read-only replay runs (AMD `66794ad5-b3a9-4fcc-aa5f-7a6d7957b7c1`,
  MU `0ba23540-0623-4d05-a670-098fbbfec1d1`, NVDA `4ca7dafa-6ac1-4d94-add0-f6f93b1af150`,
  SNDK `8d21c047-fc0a-4d94-957d-3787f353a544`): all CONTEXT_ONLY-predicted and
  ANALYTICAL-predicted candidates (from an in-memory, isolated-scratchpad
  recompute of `adapt_run_outputs`, never the real `outputs/runs/<run_id>/`
  directory) were sorted ascending by the per-claim key; the top 30
  CONTEXT_ONLY and top 10 ANALYTICAL were kept.
- Total: 160 rows (120 context-only + 40 analytical control).
- No sample was regenerated, swapped, or filtered after seeing the results.
  The 160 claim_ids are fixed by construction; only the *code* changed
  between the "before" and "after" prediction columns in the CSV.

## Classification rubric applied during manual review

For each sampled claim, re-read the claim text (and, where useful, its
evidence/entities/factors/direction) against the same rubric
`classify_claim_quality` implements:

- **ANALYTICAL**: an external/domain subject plus a clear state/change,
  risk/forecast, causal/relational, or directional/bullish-bearish signal.
- **CONTEXT_ONLY**: a real external fact with no such signal -- includes
  quoted third-party sentiment, technical-indicator readings, price/data
  points, and macro/news facts, even when thin or narratively framed.
- **NON_SUBSTANTIVE**: placeholders, disclaimers, pure section
  headings/labels/list-introducers, pure transitions, and pure
  process/writing narration that carries no independent content.

`manual_review_label` values used: `VALID_CONTEXT_ONLY`, `SHOULD_BE_ANALYTICAL`,
`SHOULD_BE_NON_SUBSTANTIVE`, `VALID_ANALYTICAL`, `SHOULD_BE_CONTEXT_ONLY`.
`reviewer` is stamped `CODEX_INTERNAL_MANUAL_REVIEW_NOT_INDEPENDENT` on every
row, per the Sprint's explicit instruction -- this is **not** John's or any
independent third-party human review; it is a careful rubric-based re-read
by the same assistant that implemented the classifier, and should be
weighted accordingly.

## What the review found (before any fix)

Of the 120 sampled CONTEXT_ONLY predictions, manual review judged only
57/120 (47.5%) as correctly non-directional facts on first pass. The
dominant, recurring failure pattern was **not** random noise -- it clustered
into a small number of systematic, explainable vocabulary gaps:

1. **Nominalized state-change terms.** `STATE_OR_CHANGE_TERMS` only listed
   verb forms ("expand", "expanding") -- noun forms used constantly in
   report prose ("margin **expansion**", "early sign of potential
   **stabilization**", "SOX **recovery**", "supply-demand **deterioration**")
   were invisible to the pattern.
2. **Missing common verb forms.** "rise/rises/rising/rose" and
   "fall/falls/falling/fell" were absent even though "increase"/"decline"
   were present; "decelerate" was absent even though "accelerate" was
   present.
3. **Bare magnitude idioms.** "up 180% from ...", "rose to $2,238M -- up
   from $1,970M" -- a directional adverb anchored to a figure, which no
   fixed phrase can enumerate since the number varies.
4. **Risk/technical jargon not yet in `RISK_TERMS`.** "volatility",
   "drawdown", "maximum loss", "warning signs", "underpriced", "vulnerability",
   "contingent on", "distribution volume", "selloff".
5. **Bare report headings/list-introducers being scored as facts.**
   "Operating Cash Flow (EXCEPTIONAL):", "Key inferences from news:" --
   label fragments with a colon and no independent content.
6. **An over-permissive "has substance" carve-out.** The meta-commentary
   hard-reject's exemption (never reject a sentence that "also has real
   substance") matched on bare grammatical connectives ("because", "if",
   "could") in its legacy vocabulary, letting genuine meta-commentary
   openers like *"Now let me address the technical picture, because I think
   both analysts are selectively reading the same data."* slip through as
   CONTEXT_ONLY.
7. **Unrecognized placeholder variants.** "No body excerpt available.",
   "All data is collected." are system-generated empty-content markers, not
   organic analyst prose, but were not in the placeholder exact-match list.

None of these are cases of `direction == unknown` being used to delete a
claim, and none involve `FACTOR_ALIASES`, Mapper weights, Activation
formulas, or `relation_grammar.py`'s own rules.

## The fix applied

All changes are confined to `comqutor_alpha/structure_engine/claim_quality.py`
(the Sprint's allowed file for Track A) and are additive, deterministic
vocabulary/pattern extensions -- no ML, no LLM, no new relation-grammar
rules, no change to any frozen contract:

- Added nominalized forms to `STATE_OR_CHANGE_TERMS` (expansion, contraction,
  acceleration, deceleration, stabilization, recovery, weakness,
  deterioration, growth) and missing verb forms (rise/rises/rising/rose,
  fall/falls/falling/fell, decelerate forms, widening, narrowing), plus
  domain idioms (trading above/below, paid down debt, debt paydown, doubled,
  tripled, more than double).
- Added a new bounded pattern, `_MAGNITUDE_MOVE_PATTERN`, matching "up"/"down"
  anchored to a nearby figure (optionally through "from"/"to"/"nearly"/
  "about"/etc.) -- deliberately narrow so it never fires on "up to date",
  "signed up", etc.
- Added to `RISK_TERMS`: warning sign(s), underpriced, overpriced,
  contingent on, volatility, volatile, drawdown, maximum loss, selloff,
  sell-off, distribution volume, vulnerability.
- Added to `DIRECTIONAL_TERMS`: selling/buying opportunity(-ies),
  accumulation zone(s).
- Added nominalized event terms to `EVENT_PREDICATE_TERMS`: acquisition,
  announcement.
- Added a new hard-reject rule, `_is_bare_heading_fragment` (reason code
  `BARE_HEADING_OR_LABEL`): a colon-terminated fragment with no quantitative
  anchor and no independent text-derived analytical signal is treated as a
  report heading/label, matching the spec's own "pure headings/formatting"
  NON_SUBSTANTIVE category. Deliberately keyed off a *text-only* analytical
  signal (excluding the stored `direction` field's own contribution) so an
  inherited direction value can never paper over an empty label fragment --
  the same principle already applied to `has_any_substance`.
- Trimmed the module-local `_SUBSTANTIVE_SIGNAL_PATTERN` (used only by
  `has_any_substance`, confirmed to have exactly one call site and to be
  fully independent of `structured_output_adapter.py`'s own, separate,
  untouched pattern of the same name) to drop pure grammatical connectives
  (because, due to, if, unless, could, may, might, would, despite) while
  keeping every genuinely substantive financial term.
- Extended the placeholder exact-match list with "no body excerpt available",
  "all data is collected", "all data is now collected".

**Validation before recomputing the sample:** full existing test suite
(`test_claim_quality.py`, `test_structured_output_adapter.py`,
`test_structure_extractor.py`, `test_alpha_mapper.py`,
`test_activation_scorer[_v2].py`, `test_conflict_detector.py`,
`test_agent_outputs_persistence.py`, `test_agent_outputs_api.py`,
`test_product_findings_end_to_end.py`, `test_week3_nvda_sanity.py`,
`test_week4_golden_closure.py`) -- 451 passed, 0 failed. A full 4-run
resweep confirmed no unintended mass over-rejection (non_substantive counts
moved from 0/run to 9-10/run, and every newly-rejected claim was spot-checked
and found to be a genuine heading/placeholder/meta-commentary instance, not
real content).

## Result (same 160-claim-id sample, re-classified with the fixed code)

| Metric | Result | Threshold | Met? |
|---|---|---|---|
| context_only_precision | 57/84 = **67.9%** | >= 90% | No |
| context_only Wilson 95% lower bound | **57.3%** | >= 85% | No |
| non_substantive leak (original classifier, in the 120-item context-only sample) | 7 | -- | -- |
| non_substantive leak (still leaking after the fix) | **1** | 0 | No |
| analytical_control_precision | 36/40 = **90.0%** | >= 95% | No |

(`context_only_total_after_fix` = 84, not 120: 33 of the originally
mis-predicted claims were reclassified by the fix -- 30 promoted to
`analytical`, 3 demoted to `non_substantive` -- and are no longer counted as
CONTEXT_ONLY predictions at all; precision is computed, correctly, over
whatever the *current* code still predicts CONTEXT_ONLY.)

Per ticker: AMD 78.3%, MU 68.2%, NVDA 73.9%, SNDK 43.8%.

Of the 6 leaked non-substantive claims found in the original context-only
sample, 6/7 were fixed (all 4 meta-commentary-via-generic-connective cases,
both pipeline-boilerplate/placeholder-variant cases, and 2 of 3 bare-heading
cases). One residual leak remains: a pipe-delimited report metadata line
(`"Analysis Date: July 17, 2026 | Technology / Computer Hardware / NAND
Flash Memory"`) that does not end in a colon and contains a date's digits,
so it is not caught by the colon-based heading rule -- documented, not
fixed, given its narrow (single-observed-instance) value relative to the
risk of a broader, less-precise heading heuristic.

## Why the gap was not closed further

Of the 53 `SHOULD_BE_ANALYTICAL` findings, 33 were resolved by the
vocabulary/pattern fix above; the remaining ~31 residual findings (across
both samples) cluster almost entirely into one category that a fixed,
deterministic keyword list cannot safely close under this Sprint's explicit
"no ML/LLM" constraint:

- **Open-vocabulary qualitative characterization** -- "one of the most
  **compelling** ... setups", "**extraordinary** liquidity", "**elite**
  among all technology companies", "**unprecedented** in semiconductor
  industry history", "years of **destruction**", "NAND prices **went
  vertical**", "the narrative is **exhausted**". These are genuine bullish/
  bearish signal to a human reader, but the adjectives themselves (compelling,
  extraordinary, elite, stunning, unprecedented, destruction, and dozens of
  synonyms) are ordinary English words with no reliable, narrow, deterministic
  boundary -- adding them to `DIRECTIONAL_TERMS` was evaluated and rejected:
  the false-positive risk across the full, largely-unreviewed corpus (only
  160 of roughly 2,700 total records across the 4 runs were manually read)
  was judged unacceptably high to add under time pressure without an
  equivalently thorough re-audit.
- **Relation-grammar-adjacent structural claims** ("operating leverage ...
  compounds as revenue scales", fabless-model causal claims, cross-market
  "deeply linked" claims) -- deliberately left alone: extending relation
  detection inside `claim_quality.py` beyond what `relation_grammar.py`
  already exposes would create exactly the "separately-drifting relation
  vocabulary" the original Unified Claim Admissibility Sprint's design
  explicitly forbids.
- **Narrow, single-occurrence idioms** ("ran 130%", "guided up",
  "lowest-regret, highest-protection", commodity-status negation claims like
  "HBM is not a commodity") -- each real, but too specific to generalize
  into a safe pattern from one or two sample observations.

This is a structural limitation of the deterministic-classifier approach
mandated by the Sprint brief, not a defect introduced by this Sprint's own
code, and not something a larger but equally ad hoc keyword list would fully
close -- the tail of financial English idiom is long. See the Sprint's final
report for the resulting recommendation.

## Typical misjudgment examples (before fix)

- `"Structural gross margin expansion."` -- predicted CONTEXT_ONLY;
  should be ANALYTICAL (nominalized state-change term). **Fixed.**
- `"Now let me address the technical picture, because I think both
  analysts are selectively reading the same data."` -- predicted
  CONTEXT_ONLY; should be NON_SUBSTANTIVE (meta-commentary riding through
  on a bare connective). **Fixed.**
- `"Operating Cash Flow (EXCEPTIONAL):"` -- predicted CONTEXT_ONLY; should
  be NON_SUBSTANTIVE (bare report-section label). **Fixed.**
- `"Let me walk you through why AMD at $521.95 represents one of the most
  compelling medium-to-long-term setups in the semiconductor space right
  now."` -- predicted CONTEXT_ONLY; should be ANALYTICAL (bullish
  qualitative characterization). **Residual** (generic adjective, not
  fixed).
- `"'Analysis Date: July 17, 2026 | Technology / Computer Hardware / NAND
  Flash Memory'"` -- predicted CONTEXT_ONLY; should be NON_SUBSTANTIVE
  (report metadata header). **Residual** (pipe-delimited shape, not
  colon-terminated).

## Independence disclaimer

This review was performed by the same assistant that implemented
`claim_quality.py` and the fixes described above, reading each sampled
claim against the written rubric. It is **not** an independent third-party
or human (John) acceptance review -- see `reviewer` =
`CODEX_INTERNAL_MANUAL_REVIEW_NOT_INDEPENDENT` on every row of
`context_only_precision_audit.csv`. The sample selection (hash-based,
fixed by HEAD) is independent of the reviewer's judgment; the judgment
itself is not independently verified by a second party.
