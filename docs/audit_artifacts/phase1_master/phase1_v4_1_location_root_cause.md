# Phase 1 v4.1 Evidence-Location Root-Cause Diagnosis

Read-only, Provider-zero forensic diagnosis of why the final v4.1 Re-Canary
(`outputs/canaries/phase1-v4-1-final-recanary-20260810T230224Z/`) failed
0/4. No Provider/network calls were made, no subagents were spawned, and no
production code or state was changed while producing this report. Every
number below comes from `scripts/diagnose_phase1_v4_1_location_root_cause.py`
reading only already-persisted artifacts (full machine-readable output in
the companion `phase1_v4_1_location_root_cause.json`), cross-checked by
direct inspection of `scripts/run_phase1_v4_1_final_recanary.py` and
`comqutor_alpha/structure_engine/structured_output_shadow_v4_1.py`.

## Headline finding

**Of the 61 rejected Evidence items across all 4 slots, 58 (95%) were
already globally unique, correctly-copied quotes that failed only because
the model additionally supplied a `candidate_id` whose span did not
contain that already-unique quote.** Only 3 items (5%) were genuine
duplicate-quote cases, and the resolver handled all 3 exactly as designed
(safe rejection because no `candidate_id` was supplied to disambiguate
them). Zero items were fabricated (zero `NO_EXACT_MATCH`), zero involved a
canonical-relations block, zero involved truncation, zero involved
candidate-window overlap, and Provider/resolver operated on byte-identical
source text in all 4 slots.

## 1-2. What each slot read, and did Provider/resolver see the same text?

| Slot | `agent` | `source_field` | `raw_output` len | `truncated` | Provider src SHA256 == resolver src SHA256 == raw_output SHA256 |
|---|---|---|---:|---|---|
| fundamental | `fundamental_agent` | `fundamentals_report` | 13,887 | No | **YES** |
| news | `news_agent` | `news_report` | 8,924 | No | **YES** |
| sentiment | `sentiment_agent` | `sentiment_report` | 12,447 | No | **YES** |
| technical | `market_agent` | `market_report` | 10,134 | No | **YES** |

All four are the standard TradingAgents analyst-report fields (nothing
unusual in the field mapping). Traced in code:
`scripts/run_phase1_v4_1_final_recanary.py::_payload_from_frozen_sources`
reads `record["raw_output"]` directly from the frozen
`outputs/runs/0e044e37-.../raw_agent_outputs.json` for each pre-registered
`source_agent_output_id`, verifies it against the pre-registered
`source_report_sha256` in the execution contract, and passes that exact
string as `context.source_report` into both the Provider-request path and
the resolver path with no intermediate transformation. Each slot's own
persisted `source_report_sha256` (used to build the wire request) and its
`rejected_forensics.source_report_sha256` (recorded by
`build_rejected_forensic_record_v4_1` from what the resolver actually
searched) are both, independently, byte-identical to the SHA256 of
`raw_output` re-read fresh from the historical run file. **Provider source
and resolver source were never different strings anywhere in this run.**

## 3. Where they differed

Nowhere. Not applicable -- see above.

## 4. Did `COMQUTOR_CANONICAL_RELATIONS` create duplicate occurrences?

**No.** `comqutor_alpha/structure_engine/canonical_relation_prompt.py`
confirms the block is appended only by specific TradingAgents prompts (the
combined analyst/debate/risk response contract); it is not present at all
in these four reports. Direct search of all four `raw_output` strings for
the literal marker `COMQUTOR_CANONICAL_RELATIONS` returns **0 occurrences
in all 4 reports**. The legacy adapter's `split_human_text_and_canonical_block`
function (`canonical_relation_block.py`) is therefore a no-op on this data
and irrelevant to this failure. This hypothesis is definitively ruled out.

## 5. Did overlapping candidate windows create fake ambiguity?

**No.** For every one of the 99 Evidence items across all 4 slots, the full
`candidate_manifest` was checked for any two candidates whose `[source_start,
source_end)` windows both cover the same global exact-match offset.
**0 instances found anywhere.** This hypothesis is definitively ruled out.

## 6. Were candidate IDs actually wrong?

**Yes -- confirmed, and this is the dominant cause.** See the per-slot
breakdown below. In every `PROVIDER_WRONG_CANDIDATE_ID_FOR_UNIQUE_QUOTE`
case the quote had exactly one global exact match, the model supplied a
non-null `candidate_id` that legitimately existed in that request's
manifest (never an unknown/hallucinated ID -- `candidate_exists_in_manifest`
was `true` for all 58), but that candidate's registered `[source_start,
source_end)` span did not contain the quote's one true offset. In roughly
85% of these (49/58), **no candidate anywhere in the manifest** covered
that offset at all (`some_other_candidate_covers_unique_offset=false`); in
the remaining ~15% (9/58) a different, uninvoked candidate in the same
manifest did cover it. Neither sub-case is a resolver bug: the resolver did
exactly what v4.1 specifies (reject unless the *supplied* candidate's local
span uniquely contains the quote).

## 7. Did the original human report genuinely contain duplicate sentences?

**Yes, rarely and benignly -- 3 confirmed instances, 2 in `fundamental` and
1 in `technical`.** All 3 are ordinary report-formatting duplication (the
same figure quoted once in a snapshot table and again in a summary table
later in the same document), not any kind of data corruption. In all 3
cases the model did **not** supply a `candidate_id` (`selected_candidate_id
== null`), so v4.1's resolver correctly and safely rejected them via
`AMBIGUOUS_CANDIDATE_REQUIRED` / `SHADOW_DUPLICATE_QUOTE_CANDIDATE_REQUIRED`
-- exactly the fail-closed behavior it was designed to produce. No
fabricated, unresolved, or wrongly-admitted Evidence ever occurred.

## 8. Did 50k truncation contribute?

**No.** All four relevant `raw_agent_outputs.json` entries show
`"truncated": false` and `content_length == original_content_length`
(13,887 / 8,924 / 12,447 / 10,134 characters respectively, all far under
the 50,000-character boundary). This hypothesis is ruled out for these
four reports.

## 9-11. Why did News fail 17/17, Sentiment 24/24, and Technical only pass 4/22?

All three follow the identical pattern:

| Slot | Total Evidence items | Located OK | Genuine duplicate (correctly rejected) | Wrong/uncovering candidate_id on a unique quote |
|---|---:|---:|---:|---:|
| fundamental | 36 | 34 | 2 | 0 |
| news | 17 | 0 | 0 | **17 (100%)** |
| sentiment | 24 | 0 | 0 | **24 (100%)** |
| technical | 22 | 4 | 1 | 17 |
| **Total** | **99** | **38** | **3** | **58** |

News and Sentiment failed completely for the same single reason: every one
of their Evidence quotes was already globally unique and exactly correct,
but the model attached a `candidate_id` to essentially all of them anyway,
and that `candidate_id` almost never happened to be the (or a) candidate
whose span actually contained the quote. Technical mixes the dominant
wrong-candidate-id pattern (17 items) with the one genuine, benign
duplicate (the repeated closing-price table row) plus 4 clean unique
matches where the model either omitted `candidate_id` or happened to
supply a correct one.

## 12. What actually caused the duplicate quote that originally motivated v4.1?

The `technical` slot's genuine duplicate is:

> `| **Close** | $195.04 |`

occurring at offsets 371 and 7975 of the same `market_report` text -- once
inside a "Market Snapshot" table near the top of the report, and again
inside a "Summary Table" near the bottom of the same report. Both
occurrences are ordinary Markdown table rows in the plain human report body
(`occurrence_location_types: ["HUMAN_REPORT", "HUMAN_REPORT"]`); this is
**Type 1, a true, single-source duplicate**, not a canonical-relations
artifact, not a candidate-window artifact, and not a data-pipeline defect.

This is the same underlying, immutable `market_report` text
(`0e044e37-...:market_agent:market_report`) used in the earlier, original
v4 Live-Shadow Canary that first surfaced a Technical rejection. **Honest
caveat, as instructed:** the original v4 canary attempt did not persist its
raw rejected Provider payload (documented in
`live_shadow_canary_failure_repair.forensic_limitation` --
"Rejected raw Provider proposal was not persisted; exact claim, quote,
offsets ... are unrecoverable and were not guessed"), so the *exact* quote
text Claude proposed in that first attempt cannot be recovered or proven
identical to this one. Given it is the same source report, the same
family, and the report's `**Close**` price is the single most obvious
duplicated fact a model would naturally quote twice, this is almost
certainly the same or a closely analogous case -- but that specific
identity is not independently provable from persisted data, and this
report does not claim more certainty than the evidence supports.

## Three duplicate types, explicitly distinguished

- **Type 1 (TRUE_SOURCE_DUPLICATE):** 3/3 confirmed cases are this type --
  the same sentence/table row appears at two distinct offsets in the plain
  human report body. Real, rare (3 of 99 items), and always safely rejected.
- **Type 2 (MACHINE_REPRESENTATION_DUPLICATE, e.g. a canonical-relations
  block):** **0 occurrences.** Ruled out for all 4 slots.
- **Type 3 (CANDIDATE_OVERLAP_DUPLICATE):** **0 occurrences.** Ruled out
  for all 99 Evidence items.

These are confirmed structurally distinct in this data, and Type 1 is the
only one that ever actually occurred.

## Root cause, aggregated by slot

```
fundamental  total_failed_evidence=2
  TRUE_HUMAN_REPORT_DUPLICATE = 2

news         total_failed_evidence=17
  PROVIDER_WRONG_CANDIDATE_ID_FOR_UNIQUE_QUOTE = 17

sentiment    total_failed_evidence=24
  PROVIDER_WRONG_CANDIDATE_ID_FOR_UNIQUE_QUOTE = 24

technical    total_failed_evidence=18
  PROVIDER_WRONG_CANDIDATE_ID_FOR_UNIQUE_QUOTE = 17
  TRUE_HUMAN_REPORT_DUPLICATE = 1

OVERALL (99 total Evidence items across 4 slots)
  NONE_LOCATED_OK                              = 38
  PROVIDER_WRONG_CANDIDATE_ID_FOR_UNIQUE_QUOTE = 58
  TRUE_HUMAN_REPORT_DUPLICATE                  = 3
  SOURCE_MISMATCH                              = 0
  CANONICAL_BLOCK_DUPLICATION                  = 0
  CANDIDATE_WINDOW_OVERLAP                     = 0
  ZERO_GLOBAL_EXACT_MATCH                      = 0
  TRUNCATION_MISMATCH                          = 0
  SOURCE_IDENTITY_MISMATCH                     = 0
```

One systemic bug, not several unrelated problems: **58 of 61 failures (95%)
trace to one single mechanism** -- v4.1 lets the model attach an optional
`candidate_id` to any quote (not only ambiguous ones), and validates it
whenever present, even for an already-unique, already-correct quote. The
model exercises that option far more often than genuine ambiguity requires,
and its candidate choice is unreliable, converting a large number of
otherwise-perfect `UNIQUE_EXACT_MATCH` resolutions into rejections. The
narrow problem v4.1 was actually built to solve -- genuine duplicate exact
quotes -- occurred 3 times in 99 items and was handled correctly every
time.

## Special section: the Technical duplicate-quote case

- **quote:** `| **Close** | $195.04 |`
- **global_match_count:** 2
- **global_match_offsets:** `[371, 7975]`
- **occurrence_1_context** (offset 371, ±250 chars): inside the "## 1. 📌
  Market Snapshot (Source of Truth)" table (`Open`/`High`/`Low`/`Close`/`Volume`).
- **occurrence_2_context** (offset 7975, ±250 chars): inside the "## 📋
  Summary Table" (`Close`/`50 SMA`/`200 SMA`/... rows with Signal/Interpretation
  columns).
- **occurrence_1_location_type:** HUMAN_REPORT
- **occurrence_2_location_type:** HUMAN_REPORT
- **provider_source_sha256 == resolver_source_sha256:** YES
- **same_source:** YES
- **candidate_overlap_involved:** NO
- **provider_wrong_candidate_id:** N/A for this specific item -- the model
  supplied no `candidate_id` at all for this quote, so it was correctly
  rejected as `AMBIGUOUS_CANDIDATE_REQUIRED`, not as a wrong-candidate case.
- **actual_root_cause:** `TRUE_HUMAN_REPORT_DUPLICATE` -- a genuine,
  benign, single-source duplicate table row; correctly and safely rejected.

## Minimum repair implication (diagnosis only, not implemented here)

Because 95% of failures stem from optional-candidate-id validation
penalizing already-unique quotes, and 0% stem from source mismatch,
canonical-relation contamination, candidate-window overlap, truncation, or
fabricated evidence, a repair that stops validating `candidate_id` against
already-globally-unique quotes (and/or stops offering it as an option at
all except when the quote is genuinely ambiguous) would directly address
the dominant failure mode observed here. This report does not implement,
recommend adopting, or evaluate any specific repair design -- that
decision is explicitly reserved for the product owner, per this task's own
instructions.
