# NVDA run (034a0a60-430e-41f8-8321-03a11389707a): source coverage root causes, and why current_evidence=0

## Correction to the first joint-review package

The first package (`nvda_fresh_run_joint_review_package/`, v1) reported Activation scores of 96.69/100/84.36/etc. and described them as "raw Activation" reaching `regime_level`/`dominant`. **That was the `activation_versions.v1` score set -- the oldest, most permissive diagnostic formula (`week3.activation.mvp_v1`), not this run's actual primary/official result.** `alpha_activations.json` carries three distinct, separately-versioned score sets:

| version key | formula_version | max score this run | status band reached |
|---|---|---|---|
| `v1` | `week3.activation.mvp_v1` | 100.0 (A102, A301) | `regime_level` (6 Alphas), `dominant` (1) |
| `v2` | `activation.v2.evidence_local_structure.v1` | 66.0 (A102) | `active` (highest reached) |
| **`v2_verified`** (= `primary_activation_version`, the actual official result, `act["activation"]` at the top level) | `activation.v2.evidence_local_structure.verified_gate.v1` | **0.0 for all 10 Alphas** | `candidate` for all 10 (the lowest/initial band) |

**The official result for this run is `v2_verified`: 0.0 for every single Alpha.** Not "below the dominant threshold" -- exactly zero, for a specific, traceable reason below. The updated package (v2) reports `v2_verified` as the headline number and shows `v1`/`v2` explicitly labeled as diagnostic-only, never conflated.

## Why current_evidence=0 for every Alpha -- the real, traced chain

`comqutor_alpha/exposure_engine.py::calculate_runtime_exposure_inputs` computes `current_evidence = ticker_specific_fact_ratio * mean_match_score`, from `evidence_summary["facts"]` -- which is built from **`v2_verified`'s own qualifying-evidence pool**, not from `v1`/`v2`'s looser evidence. Tracing one concrete real claim all the way through:

```
raw claim (fundamentals_report:claim:40):
  "Verified: Total Revenue rose to $96,221,000,000 as of 2026-07-31
   (quarterly) [fragmentid: srcbce051a83ee448c8:frag:0]."
        |
        v
source link: source_link_status = VALID, linked_source_id = real
  (the embedded [fragmentid: ...] marker resolved against a real,
  registered financial-data source)
        |
        v
content support review: content_support_status = PENDING_REVIEW,
  content_support_review.method = "UNREVIEWED"
  <-- NO HUMAN HAS REVIEWED THIS CLAIM. This run is hours old; human
      review is a separate, later, manual step this system's own
      workflow has never claimed happens automatically.
        |
        v
verified-support eligibility (compute_verified_support_eligibility,
  comqutor_alpha/source_provenance.py:311): requires ALL of six
  conditions, including #2: "content_support_review whose method ==
  HUMAN_REVIEWED". Condition #2 FAILS (method is UNREVIEWED) ->
  eligible = False, regardless of the other five conditions.
        |
        v
filter_verified_qualifying_claims (verified_evidence_gate.py:177):
  this claim is NOT included in the verified-evidence pool for ANY Alpha.
        |
        v
score_alpha_activations_v2_verified: with zero verified claims admitted
  for this Alpha (or any Alpha -- the SAME human-review gate applies to
  every one of this run's 1040 claims identically), activation_score=0.0,
  status="candidate" for all 10 Alphas.
        |
        v
Entity Exposure's current_evidence (calculate_runtime_exposure_inputs):
  built from v2_verified's own (empty) qualifying-fact pool ->
  ticker_specific_fact_count=0 -> current_evidence=0.0 for every Alpha.
        |
        v
final official result: no dominant Alpha, no main conflict -- not from
  weak signal (the v1/v2 diagnostic layers found real signal), but
  because ZERO claims in this entire run have ever been through the one
  gate (human review) that verified Activation/Exposure requires.
```

**This is confirmed as the complete, sufficient explanation, not merely the most likely one**: every one of this run's 1040 claims shows `content_support_review.method == "UNREVIEWED"` (distribution: 1016 claims `content_support_status=NOT_APPLICABLE`, the other 24 -- the only ones with a real source link at all -- `content_support_status=PENDING_REVIEW`; **zero** claims anywhere show `HUMAN_REVIEWED`). Since condition #2 of `compute_verified_support_eligibility` is never satisfiable for any claim in this run, `v2_verified` is 0 for every Alpha as a direct, deterministic consequence -- independent of, and more fundamental than, the ticker-specificity question below. **This is the expected, correct, by-design state for any freshly-completed, not-yet-human-reviewed run -- not a defect, and not something lowering a threshold or re-running anything would change.**

## A second, independent, additive factor: ticker-specificity

Separately from the human-review gate above, none of this run's 24 `source_link_status=VALID` claims carry `ticker_specific=true` in their own persisted record. Traced to `comqutor_alpha/graph_engine/activation_scorer_v2.py::_is_ticker_specific`: a claim counts as ticker-specific only when the ticker symbol or a known company-name alias appears as a literal, token-boundary match **in the claim's own text** -- deliberately not satisfied by the claim's `entities` list alone, because (per that function's own docstring) "upstream extraction appends the run ticker to every claim's entities unconditionally." The real VALID-linked claims are `market_agent`/`fundamental_agent` structured-data lines (e.g. `"Verified: Total Revenue rose to $96,221,000,000 as of 2026-07-31..."`) that never spell out "NVDA"/"NVIDIA" in the claim text itself -- the ticker is implied by the report's own context, not repeated per line.

**This is confirmed as deliberate, reasoned design, not an accidental gap** -- the function's docstring explicitly documents why a looser check (counting entity-list membership) was rejected, and "pure sector/macro statements never qualify" is stated as an intentional anti-false-positive property. **No code fix is made for this** per this round's own instruction to fix only genuine implementation defects; this is not one. It is reported here as a real, additive reason the verified-evidence pool would likely remain empty even after a hypothetical future human-review pass, unless `market_agent`/`fundamental_agent`'s claim-text format is changed (a product decision, out of scope here) to repeat the ticker/company name per claim.

## Source-coverage root-cause breakdown (1040 claims), re-run against the real, frozen linking functions

Re-ran `comqutor_alpha.source_provenance.match_evidence_to_source_candidates` and `extract_source_marker_from_text` -- the actual production linking functions, unmodified -- offline, against every claim's frozen text and this run's frozen 45-source registry (zero new Provider/network calls):

| category | count | basis |
|---|---|---|
| `source_link_status = VALID` | 24 | already-persisted, real source link |
| No plausible external source, even on re-check against the full registry (genuinely internal analysis/debate/commentary) | 1001 | re-running the real matcher found no marker and no content-overlap candidate for these claims against ANY registered source, including the 40 excerpt-less ones |
| Plausible textual reference to one of the 40 real, registered-but-content-less news sources | 15 | a loose, best-effort textual signal (publisher name / title-prefix substring match) -- **not proof of a causal link**, reported as a plausible subset, not a confirmed count |
| A real candidate the production pipeline should have found but didn't (an actual matching-logic defect) | **0** | re-running the real functions never found a candidate that the live pipeline's own NOT_PROVIDED decision disagreed with -- **no implementation defect found in the linking/matching logic itself this run** |

**A structural, separate finding**: all 40 "news"-type registered sources (100%, provider=`yfinance`, via `get_global_news_yfinance`) carry `excerpt=null`/`fragment_id=null` -- only the 5 "financial"/"market"-type sources have real excerpts. This makes `SOURCE_LINK_VALID` **structurally impossible** for any claim whose only real-world source would have been one of those 40 news items, regardless of claim wording. **Root cause of the missing excerpts is not determined this round**: `tradingagents/dataflows/yfinance_news.py::_capture_news_source` does attempt to pass `data.get("summary")`, and the code path to populate it looks correct on inspection; whether yfinance's real Search API simply never returns article body/summary text for these items (an external data-source limitation) or whether `_extract_article_data`'s extraction has a defect could not be determined from this run's own frozen artifacts -- the raw tool response itself is not persisted anywhere queryable, and determining this with certainty would require a new live tool call, which is out of scope for this offline-only round. **Marked UNKNOWN, not guessed, and not fixed.**

## Traceability table for the main Alpha candidates (raw claim -> ... -> official result)

| Alpha | v1 (diagnostic) | v2 (diagnostic) | **v2_verified (official)** | current_evidence | Why |
|---|---|---|---|---|---|
| A101 | 96.69, regime_level | 53.43, active | **0.0, candidate** | 0.0 | 0 of its 7 v1-diagnostic-evidence claims are HUMAN_REVIEWED |
| A102 | 100.0, regime_level | 66.0, active | **0.0, candidate** | 0.0 | same -- 0 verified claims |
| A103 | 84.36, dominant | 45.35, watch | **0.0, candidate** | 0.0 | same |
| A201 | 65.49, active | 18.37, inactive | **0.0, candidate** | 0.0 | same |
| A301 | 100.0, regime_level | 32.87, watch | **0.0, candidate** | 0.0 | its one VALID-linked, Alpha-matched claim (`fundamentals_report:claim:40`) is `UNREVIEWED` and not ticker-specific (see above) |
| A304 | 92.10, regime_level | 19.67, inactive | **0.0, candidate** | 0.0 | same |
| A501 | 99.09, regime_level | 51.03, active | **0.0, candidate** | 0.0 | same |
| A601 | 88.21, regime_level | 36.54, watch | **0.0, candidate** | 0.0 | same |
| A001, A003 | 0.0, inactive | 0.0, inactive | 0.0, candidate | 0.0 | no claims matched these at all, diagnostic or verified |

**This run's honest headline, stated precisely**: there is real, structured diagnostic-layer signal (the `v1`/`v2` formulas, which never required human review) pointing at several Alphas -- most strongly A101/A102/A103 (AI-expansion/inference/infrastructure theme) and, on the negative side, A304/A501 (valuation/recession risk). **None of this has been verified** -- zero claims in this run have been through human review, which the official `v2_verified` layer (and this run's own reported `dominant_alphas`/`main_conflict`) correctly and necessarily shows as empty. This is not a weak result to be explained away, and not a strong result to be inflated -- it is an unreviewed one, and the two diagnostic layers exist specifically to surface candidates for that review, never to substitute for it.
