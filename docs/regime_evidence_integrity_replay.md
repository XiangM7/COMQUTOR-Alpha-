# Regime Evidence Integrity Replay

Product Findings Closure and Regime Evidence Integrity Sprint, Track B.

Read-only replay of AMD, MU, NVDA, SNDK. Structured records / alpha_matches /
extracted_structures / structure_graph are recomputed in-memory from an
isolated scratchpad copy of each run's `raw_agent_outputs.json` (never the
real `outputs/runs/<run_id>/` directory); the Evidence Integrity Shadow
Layer is then layered on top of the resulting Activation v2 output. No
Provider/LLM/network call anywhere (`llm_gateway=None` throughout). No
writes to any historical artifact -- verified both by construction (this
module performs no I/O) and by an explicit before/after byte-equality
assertion on every alpha's `activation_score`/`status` for all 4 tickers
(see `regime_evidence_replay.py`, asserted, not merely claimed).

Run IDs: AMD `66794ad5-b3a9-4fcc-aa5f-7a6d7957b7c1`, MU
`0ba23540-0623-4d05-a670-098fbbfec1d1`, NVDA `4ca7dafa-6ac1-4d94-add0-f6f93b1af150`,
SNDK `8d21c047-fc0a-4d94-957d-3787f353a544`.

## Headline finding: no alpha reaches regime_level in any of the 4 runs

Across all 4 tickers and all 30 (alpha, ticker) combinations with at least
one raw evidence claim, the highest production status reached is `active`
(SNDK's A304, score 63.07) -- no alpha reaches `dominant` (>70) or
`regime_level` (>85) in any replayed run. Every alpha therefore resolves to
`regime_evidence_integrity_status = NOT_REGIME_CANDIDATE`, and
`shadow_regime_eligible = null` for all of them (per the shadow verdict's
first, cheapest check: shadow analysis is only meaningful once production
itself already believes an alpha is regime-level).

This is an honest, unforced result of real (if evidentially thin) TradingAgents
debate transcripts, not a defect in this Sprint's code -- `dominant`/
`regime_level` are meant to be rare, high-conviction states, and most of
these alphas are additionally held down by Activation v2's own (frozen,
untouched) `NO_LOCAL_STRUCTURE_SUPPORT` cap (70.0 ceiling) whenever
`local_edge_count == 0`, which is the case for every alpha except SNDK's
A103. Because no alpha is a regime candidate, this replay cannot exercise
the `CONSISTENT`/`OVERLAP_RISK`/`UNVERIFIED_EXPOSURE` branches on real data
-- those are covered instead by dedicated synthetic unit tests in
`tests/test_evidence_integrity.py` (which inject a `status="regime_level"`
production result and, separately, a non-`None` exposure value to exercise
every branch deterministically).

## Per-ticker summary

| Ticker | Graph edges | Evidence groups | Cross-alpha groups | Max production score | Max status |
|---|---|---|---|---|---|
| AMD | 0 | 20 | 1 (A301+A601) | 46.34 (A301) | watch |
| MU | 0 | 13 | 0 | 37.04 (A201) | watch |
| NVDA | 0 | 13 | 1 (A001+A601) | 36.24 (A101) | watch |
| SNDK | 2 | 16 | 0 | 63.07 (A304) | active |

## AMD

Admitted structural edges: 0.

| Alpha | Score | Status | Raw claims | Independent groups | Primary | Secondary | Distinct agents | Overlap ratio | Integrity status |
|---|---|---|---|---|---|---|---|---|---|
| A003 | 40.05 | watch | 2 | 1 | 1 | 0 | 2 | 0.50 | NOT_REGIME_CANDIDATE |
| A101 | 29.45 | inactive | 2 | 2 | 2 | 0 | 2 | 0.00 | NOT_REGIME_CANDIDATE |
| A103 | 29.97 | inactive | 2 | 2 | 2 | 0 | 2 | 0.00 | NOT_REGIME_CANDIDATE |
| A201 | 24.56 | inactive | 2 | 2 | 2 | 0 | 2 | 0.00 | NOT_REGIME_CANDIDATE |
| A301 | 46.34 | watch | 4 | 4 | 4 | 0 | 4 | 0.00 | NOT_REGIME_CANDIDATE |
| A304 | 43.10 | watch | 4 | 4 | 4 | 0 | 3 | 0.00 | NOT_REGIME_CANDIDATE |
| A501 | 0.00 | inactive | 1 | 1 | 1 | 0 | 1 | 0.00 | NOT_REGIME_CANDIDATE |
| A601 | 32.04 | watch | 5 | 5 | 4 | 1 | 3 | 0.00 | NOT_REGIME_CANDIDATE |

A003's two raw claims collapse into one evidence group (overlap_ratio 0.50)
-- a genuine, verified duplicate: `"Yes, the $2.566 billion in free cash
flow is exceptional."` and `"...is real."` (from the neutral and
conservative risk analysts respectively) share the same canonical factor,
assertion status, and polarity with no distinguishing figure of their own
beyond the already-shared $2.566B figure.

One cross-alpha group: `news_agent`'s *"...the definitive test of whether
Lisa Su's AI demand confidence translates into revenue beats that can
justify the elevated valuation"* and `sentiment_agent`'s *"Net news read:
Fundamentally bullish long-term thesis (AI demand, ...) but immediate price
action is under pressure..."* both carry the sole factor `AI Demand`,
`asserted`/`activation`, no distinguishing number or date -- grouped, and
attributed A301 primary (score 0.72) / A601 secondary (score 0.55), per the
match-score-then-factor-count priority order. A601's overlap_ratio stays
0.00 (5 raw claims, 5 independent groups) because this shared group is only
one of A601's five; the other four remain independent.

## MU

Admitted structural edges: 0. Zero overlap detected on any alpha (every
`independent_evidence_group_count` equals its `raw_evidence_claim_count`) --
none of MU's admitted evidence in this run happens to be a duplicate or
near-paraphrase of another piece of admitted evidence.

| Alpha | Score | Status | Raw claims | Independent groups | Overlap ratio | Integrity status |
|---|---|---|---|---|---|---|
| A001 | 19.78 | inactive | 1 | 1 | 0.00 | NOT_REGIME_CANDIDATE |
| A101 | 15.73 | inactive | 1 | 1 | 0.00 | NOT_REGIME_CANDIDATE |
| A103 | 14.91 | inactive | 1 | 1 | 0.00 | NOT_REGIME_CANDIDATE |
| A201 | 37.04 | watch | 5 | 5 | 0.00 | NOT_REGIME_CANDIDATE |
| A301 | 32.93 | watch | 3 | 3 | 0.00 | NOT_REGIME_CANDIDATE |
| A501 | 28.10 | inactive | 1 | 1 | 0.00 | NOT_REGIME_CANDIDATE |
| A601 | 18.10 | inactive | 1 | 1 | 0.00 | NOT_REGIME_CANDIDATE |

## NVDA

Admitted structural edges: 0.

| Alpha | Score | Status | Raw claims | Independent groups | Primary | Secondary | Overlap ratio | Integrity status |
|---|---|---|---|---|---|---|---|---|
| A001 | 0.00 | inactive | 2 | 2 | 1 | 1 | 0.00 | NOT_REGIME_CANDIDATE |
| A003 | 18.10 | inactive | 1 | 1 | 1 | 0 | 0.00 | NOT_REGIME_CANDIDATE |
| A101 | 36.24 | watch | 3 | 3 | 3 | 0 | 0.00 | NOT_REGIME_CANDIDATE |
| **A102** | 26.64 | inactive | 1 | 1 | 1 | 0 | 0.00 | NOT_REGIME_CANDIDATE |
| A201 | 31.31 | watch | 1 | 1 | 1 | 0 | 0.00 | NOT_REGIME_CANDIDATE |
| A301 | 28.74 | inactive | 3 | 3 | 3 | 0 | 0.00 | NOT_REGIME_CANDIDATE |
| A304 | 25.91 | inactive | 1 | 1 | 1 | 0 | 0.00 | NOT_REGIME_CANDIDATE |
| A601 | 26.20 | inactive | 2 | 2 | 2 | 0 | 0.00 | NOT_REGIME_CANDIDATE |

A102 (bolded, per required check 6) is present with real, ordinary data --
one raw claim, `primary_evidence_group_count=1`, `NOT_REGIME_CANDIDATE` --
derived purely from its own existing Mapper admission, with no
A102-specific code path anywhere in `evidence_integrity.py` (verified by
`tests/test_evidence_integrity.py::test_no_ticker_or_alpha_specific_hardcoding_in_source`,
which asserts none of AMD/MU/NVDA/SNDK's own names appear in the module
source, and by inspection: the module contains no alpha_id branches at
all -- every alpha is scored through the identical code path).

One cross-alpha group: `news_agent`'s claim:4 and `sentiment_agent`'s
claim:52 -- both tagged with the sole factor for that pair, `asserted`/
`activation`, no distinguishing figure -- merge, attributing A001 (score
0.62) primary and A601 (score 0.58) secondary.

## SNDK

Admitted structural edges: 2 (`ai_infrastructure -> semiconductor_cycle`,
causal, `alpha_ids=["A103"]`; `inference_demand -> ai_capex`, causal,
negated, `alpha_ids=[]`). Zero cross-alpha groups and zero overlap detected
on any alpha in this run.

| Alpha | Score | Status | Raw claims | Independent groups | Structured-relation groups | Overlap ratio | Integrity status |
|---|---|---|---|---|---|---|---|
| A001 | 0.00 | inactive | 1 | 1 | 0 | 0.00 | NOT_REGIME_CANDIDATE |
| A101 | 20.22 | inactive | 1 | 1 | 0 | 0.00 | NOT_REGIME_CANDIDATE |
| **A103** | 42.15 | watch | 2 | 2 | 1 | 0.00 | NOT_REGIME_CANDIDATE |
| A201 | 17.54 | inactive | 3 | 3 | 0 | 0.00 | NOT_REGIME_CANDIDATE |
| A301 | 18.93 | inactive | 1 | 1 | 0 | 0.00 | NOT_REGIME_CANDIDATE |
| A304 | 63.07 | active | 7 | 7 | 0 | 0.00 | NOT_REGIME_CANDIDATE |
| A601 | 24.79 | inactive | 1 | 1 | 0 | 0.00 | NOT_REGIME_CANDIDATE |

### SNDK positive-edge verification (required check)

The claim `sentiment_agent:sentiment_report:claim:49` --
*"AI infrastructure demand driving memory -- NAND flash and storage demand
from AI data center buildout is the fundamental bull thesis, reinforced by
Zacks, Motley Fool, and StockTwits analysts alike."* -- was directly
verified in this replay:

- **Found**: yes, present as its own evidence group
  (`evidence_group_id=0d31961145d27fadefe1a0e1`).
- **Structure Graph edge preserved**: yes -- `ai_infrastructure --causal-->
  semiconductor_cycle`, `assertion_status=asserted`, still present in the
  recomputed graph, unregressed.
- **Relation signature grounded**: the evidence group's
  `relation_signature` is `ai_infrastructure>causal>semiconductor_cycle>asserted`
  -- backed by the real structure-graph edge, not merely a factor-label
  coincidence.
- **Attribution**: `supported_alpha_ids=["A103"]`,
  `primary_alpha_id="A103"`, no secondary alphas.
- **Not deleted or demoted**: the claim's own `claim_quality` resolves to
  `analytical` (a clear structural/causal relation signal, independent of
  its `direction=unknown`), so it was never at risk of the "delete because
  direction is unknown" failure mode this Sprint and the prior Unified
  Claim Admissibility Sprint both explicitly forbid.
- **Not judged "over-AI'd"**: SNDK's AI-storage thesis evidence is treated
  as one legitimate, structurally-grounded fact supporting A103 -- this
  Sprint's grouping logic does not merge it with anything else, does not
  question its relevance, and carries no SNDK-specific rule of any kind
  (verified by the same no-hardcoding test referenced above).

## Cross-cutting required checks

1. **SNDK's AI storage evidence retained**: confirmed above.
2. **SNDK's verified Structure Graph edge does not regress**: confirmed
   above (2 edges, both from the same isolated in-memory recompute this
   Sprint's earlier Relation Grammar Sprint work already produced;
   unaffected by this Sprint's own changes).
3. **Same AI-storage thesis, cross-agent paraphrase recognized as a shared
   evidence group**: demonstrated concretely on AMD (A301/A601, `news_agent`
   + `sentiment_agent`) and NVDA (A001/A601, `news_agent` +
   `sentiment_agent`) -- SNDK's own admitted evidence pool did not happen to
   contain a second paraphrase of the claim:49 thesis in this specific run,
   so SNDK itself shows 0.00 overlap everywhere; the cross-agent-paraphrase
   mechanism is nonetheless proven on two of the four tickers with real
   data, plus explicit unit tests
   (`test_cross_agent_paraphrase_with_shared_factor_signature_merges`,
   `test_group_can_support_multiple_alphas_with_primary_and_secondary`).
4. **Grouping never deletes A101/A103 relevance**: every admitted claim for
   A101/A103 across all 4 tickers appears in exactly one evidence group
   each (`raw_evidence_claim_count` accounted for in full by
   `independent_evidence_group_count` plus any merges) -- no claim is ever
   dropped by grouping, only re-attributed as primary or secondary.
5. **No ticker-specific exception**: verified by
   `test_no_ticker_or_alpha_specific_hardcoding_in_source` (none of
   AMD/MU/NVDA/SNDK's own literal names appear anywhere in
   `evidence_integrity.py`) and by direct code inspection -- the module
   takes `ticker` purely as a caller-supplied parameter, never branches on
   its value.
6. **A102 follows existing Mapper admission only**: confirmed above (NVDA
   table) -- ordinary data, ordinary code path, no special case.
7. **Production score/status byte-for-byte unchanged**: asserted
   programmatically for every alpha on every ticker in
   `regime_evidence_replay.py` (captures a snapshot of
   `{alpha_id: {activation_score, status}}` before calling
   `build_alpha_evidence_integrity_payload`, an identical snapshot after,
   and asserts equality) -- the replay run completed without raising,
   confirming byte-for-byte equality held for all 4 tickers.

## Exposure availability

`comqutor_alpha/exposure/rubric_contract.py` explicitly documents that its
contract "is NOT wired into the research pipeline, the API, the frontend,
Activation, or Conflict" -- confirmed by grep: no `exposure` field exists
anywhere in any of the 4 real runs' `alpha_matches.json`/
`structure_graph.json`, nor anywhere in `graph_engine`/`structure_engine`.
Every alpha's exposure is therefore genuinely unavailable in this replay --
this Sprint does not assume 0, does not assume 1, and does not fabricate a
seed. Per spec, an alpha reaching `regime_level` in production with no
exposure value available would report `UNVERIFIED_EXPOSURE`; since no alpha
in this replay reaches `regime_level` at all (see "Headline finding"
above), `NOT_REGIME_CANDIDATE` is reached first for every alpha and
`UNVERIFIED_EXPOSURE` is not exercised on real data in this replay -- it is
covered by
`tests/test_evidence_integrity.py::test_missing_exposure_yields_unverified_exposure_never_assumed_zero_or_one`.

## OVERLAP_RISK / CONSISTENT coverage

Not reachable on real data in this replay (see "Headline finding"). Both
are exercised by dedicated synthetic unit tests injecting a
`status="regime_level"` production result plus (for OVERLAP_RISK) a
below-threshold `independent_evidence_group_count` or (for CONSISTENT) a
fully-qualifying one, with a non-`None` `exposure_value`:
`test_production_regime_level_but_thin_independent_evidence_is_overlap_risk`,
`test_production_and_shadow_both_pass_is_consistent`,
`test_insufficient_primary_evidence_is_diagnostic_only_not_a_new_gate`,
`test_evidence_integrity_warning_still_fails_shadow_gate`.
