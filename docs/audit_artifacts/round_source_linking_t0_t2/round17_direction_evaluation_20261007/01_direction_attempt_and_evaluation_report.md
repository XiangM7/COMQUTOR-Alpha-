# Round 17 — real direction judgments (attempt) and the evaluation they were meant to feed (2026-10-07)

Scope executed: the direction (`evidence_stance_classifier`) run authorized for at most 17 requests, then every zero-call step that does not depend on its results. **No classification request, content re-verification, search, data fetch, research agent or Fresh Run; no commit/push/Demo; no change to verification standards, thresholds, taxonomy or review policy; no full regression.** T1 / John acceptance is **not** claimed.

## 1. What happened to the direction run

| | |
|---|---|
| Frozen plan | 162 (claim, Alpha) pairs = the saved manifest, in order; 17 batches (16 × 10 + 2); cap 17; model `deepseek-v4-flash`; retries 0 at both levels; the existing 45 s Week2 timeout; production prompt `evidence_stance.llm_classifier.v3`; allowlist `[evidence_stance_classifier]`; audit on; stance concurrency 4. Plan hash `81513d4b…`. |
| Pre-send checks (zero calls, all passed) | pairs equal the manifest and the production request builder; claim text / evidence / target Alpha equal the original structured records and the **real classification ledger**; 0 reusable pairs; cap = batches = manifest budget; audit mounted on the real client; classification task refused by the guard (0 sent); an HTTP 500 produced exactly **one** request (zero retries are real); request shape captured on the wire (`preflight_result.json`). |
| Request configuration actually used | **explicitly sent:** `model`, `stream=false`, one user message (production prompt + batch items, 13,598 chars for batch 0); **client side:** 45.0 s read timeout, 0 client and 0 application retries (verified in the audited headers). **Not sent, so provider defaults apply:** `max_tokens`, `temperature`, `top_p`, `thinking`, `reasoning_effort`, `response_format`, `stop`. No 8192 value, no max-tokens override (the launcher unsets those variables and the entry point refuses them). |
| Executed | batch 0 alone, as the protocol check. **It timed out at 45.017 s: request audited, no response** (`WEEK2_LLM_TIMEOUT`, 0 retries). Nothing else was scheduled. |
| Requests / usage | **1 of 17** counted (sent, no response, Provider-side outcome unknown). No tokens reported. 16 batches never scheduled. |
| Saved | `outputs/runs/direction-20261007T065826Z-d311b8e2/` (checkpoint, audit, semantic ledger, results-when-stopped) and `direction_execution_report_direction-20261007T065826Z-d311b8e2.json`. **No derived evaluation run was created** (a stopped run creates none). The 10 pairs of batch 0 hold the production deterministic fallback with reason `timeout` — not a neutral, not a direction. |
| Why I stopped instead of continuing | A first batch with no protocol-valid response is not a basis for spending the other 16 requests on the same configuration, and you ruled out re-parameterised retries. I read "verify the first batch, then continue" as this gate and recorded it in the frozen plan. |

**The 45 s timeout is a known property of this task, not new.** The stance task has no timeout of its own: it inherits the shared Week2 timeout. In the project's own earlier runs, 10-item stance batches mostly timed out whenever the timeout was 40–45 s (e.g. 36 of 37 calls in `6cd2566d…`, 35 of 37 in `a8d47429…`, 28 of 34 in `0a44ec41…`; latencies pile up exactly at 40.0 s) and `v0_1_3_provider_final_orphan_reliability_audit.md` records the failures as timeout-dominant (a stance-only timeout increase was left "DESIGN_NOT_READY"). Runs where they mostly succeeded had median latencies of 200–400 s and successes up to 657 s (`421bca7a…` NVDA, `d5b60b8a…` AMD). So a real direction result needs an explicit timeout choice from you; I did not guess one.

## 2. The direction task would not have changed this evaluation (code + data)

* Stance is read in exactly one decision place: the Conflict **admissibility** gate (only `supports_alpha` counts as support for a side) plus a display filter. **Activation v2 never reads it.** (`evidence_stance_audit.json` calls itself `effect_mode: shadow` — hard-coded text.)
* In `conflict_detector`, a candidate pair with any reason code **returns before** the admissibility call (`if reason_codes: return … rejected`). All 8 declared pairs of this run return there (table in §4), so stance is never read for any of them.
* The direction result carries **no confidence**: production clears the confidence band for an LLM result and the task never asks the model for one. I would not have reported or invented one.
* So the pending 17 requests could not alter any score, activation level or Conflict outcome of the current AMD data. They matter only if the verified evidence base changes first.

## 3. Correction to my Round-16 report

I reported "812 valid NONE". The truth: **748 model NONE (incl. the 2 original) + 64 model selections that the mapper's own gates overrode to `no_match`** (all A001: 51 "positive-requirement semantic gate not satisfied", 13 "invalidation evidence contradicts the thesis"). The model made 226 selections; 162 stayed matched. The completion counter I relied on counts any `llm` result without a matched Alpha as NONE. The 19-claim table is unaffected: all 15 NONE there are genuine model NONE.

## 4. Evaluation of the recovered AMD run — PROVISIONAL (production chain already run; stance is the deterministic one)

No final evaluation run exists, so these are the artifacts of `recovery-20261007T053635Z-26d6cd1a` (classification recovered; direction not obtained). Nothing here is recomputed or tuned; the "raw" columns are the unverified diagnostic view the pipeline also stores, **not** the official result.

**Whole-run verified-evidence gate** (the production eligibility function over all 975 claims): `SOURCE_LINK_NOT_VALID` 714 · `NOT_REVIEWED` 107 · `SUPPORT_STATUS_NOT_RESOLVED` 89 · **`ELIGIBLE` 40** · `DISCLOSURE_TIME_UNKNOWN` 23 · `SOURCE_OPPOSES_CLAIM` 1 · `CONTENT_VERSION_CHANGED_SINCE_REVIEW` 1. Of the 261 source-linked claims, 64 are SUPPORTS (40 + 23 + 1), 143 PENDING_REVIEW, 49 CONDITIONAL, 4 BACKGROUND, 1 OPPOSES; methods: 152 LLM content support, 65 offline content match, 42 agent-cited unverified, 2 automated data-fact. **Of the 40 eligible claims, 39 were classified NONE by the model and the 40th (`bull_researcher…claim:12`, "Forward EPS: $15.72 vs TTM EPS of $3.92 …", matched A301) is `context_only`, so none reaches an evidence pool.**

**Per-Alpha funnel** (matched → content gate → raw pool → facts → agents → direction → score → level):

| Alpha | Matched | Raw-pool claims (quality + relation) | …they fail the content gate as | Matched claims passing the gate | Raw facts / agents | Alpha direction raw → official | Score raw → official | Exposure (final) | Official level |
|---|---|---|---|---|---|---|---|---|---|
| A001 Rate Cut Cycle | 4 | 1 | 1 no source link | 0 | 1 / 1 | positive → unknown | 35.6 → 0.0 | no seed | candidate |
| A003 Liquidity Expansion | 0 | 0 | — | 0 | 0 / 0 | unknown → unknown | 0.0 → 0.0 | no seed | candidate |
| A101 AI Expansion | 9 | 5 | 4 no source link, 1 not reviewed (method) | 0 | 2 / 2 | positive → unknown | 34.3 → 0.0 | 0.4 | candidate |
| A102 Inference Explosion | 0 | 0 | — | 0 | 0 / 0 | unknown → unknown | 0.0 → 0.0 | 0.275 | candidate |
| A103 AI Infrastructure | 5 | 1 | 1 no source link | 0 | 0 / 0 | positive → unknown | 0.0 → 0.0 | 0.325 | candidate |
| A201 Semiconductor Supercycle | 20 | 11 | 6 no source link, 5 not reviewed (method) | 0 | 4 / 3 | positive → unknown | 36.9 → 0.0 | 0.425 | candidate |
| A301 Revenue Expansion | 43 | 23 | 15 no source link, 1 status not SUPPORTS, 4 not reviewed (method), 3 disclosure time unknown | 1 | 10 / 2 | positive → unknown | 44.9 → 0.0 | 0.35 | candidate |
| A304 Multiple Compression | 51 | 25 | 19 no source link, 4 status not SUPPORTS, 2 not reviewed (method) | 0 | 7 / 3 | negative → unknown | 41.2 → 0.0 | 0.375 | candidate |
| A501 Recession Risk | 14 | 11 | 11 no source link | 0 | 6 / 1 | negative → unknown | 37.2 → 0.0 | no seed | candidate |
| A601 Narrative Momentum | 16 | 6 | 6 no source link | 0 | 3 / 1 | positive → unknown | 29.1 → 0.0 | 0.375 | candidate |

Every Alpha's official pool is empty, so every official score is 0, every direction is `unknown`, every level is `candidate`, **no Alpha is active or dominant**. **First blocker, in the order the pipeline applies it:** (1) the classifier matches a claim to an Alpha (A301 43, A304 51, A201 20 …); (2) evidence qualification keeps the committed, analytical, relation-supporting subset — the *raw pool* (A301 23, A304 25); (3) the verified-evidence gate then removes every one of them: for A301's 23 pool claims, 15 have no source link, 4 were not verified by an eligible method, 1 is not SUPPORTS, and 3 are verified SUPPORTS but `DISCLOSURE_TIME_UNKNOWN`; for the other Alphas the pool is lost almost entirely to "no source link" (`evaluation_analysis_provisional.json`, field `3_raw_qualifying_claims_by_content_eligibility`). Exposure: A001/A003/A501 have **no AMD exposure seed entry** (`missing_seed`); the other seven are computed at 0.275–0.425 with zero current qualified evidence and are all below the regime threshold.

**Candidate Conflicts** — 8 declared pairs, 0 admitted, 0 candidates, all rejected before the stance-dependent admissibility check. The official Alpha direction is `unknown` for both sides everywhere because no verified evidence exists; the raw view would resolve roles, which is exactly why the official result is different. The qualifying-claim counts below equal the raw-pool claim counts in the funnel (before the verified gate):

| Pair | Outcome | Reason codes | Qualifying claims (A / B) | Alpha direction in the official view (A / B) | Alpha direction in the raw view (A / B) | Stance-dependent admissibility reached |
|---|---|---|---|---|---|---|
| A001 vs A501 | rejected | DIRECTION_ROLE_UNRESOLVED | 1 / 11 | unknown / unknown | positive / negative | no |
| A003 vs A501 | rejected | MISSING_LEFT_EVIDENCE, DIRECTION_ROLE_UNRESOLVED | 0 / 11 | unknown / unknown | unknown / negative | no |
| A101 vs A304 | rejected | DIRECTION_ROLE_UNRESOLVED | 5 / 25 | unknown / unknown | positive / negative | no |
| A102 vs A304 | rejected | MISSING_LEFT_EVIDENCE, DIRECTION_ROLE_UNRESOLVED | 0 / 25 | unknown / unknown | unknown / negative | no |
| A201 vs A304 | rejected | DIRECTION_ROLE_UNRESOLVED | 11 / 25 | unknown / unknown | positive / negative | no |
| A301 vs A304 | rejected | DIRECTION_ROLE_UNRESOLVED | 23 / 25 | unknown / unknown | positive / negative | no |
| A304 vs A601 | rejected | DIRECTION_ROLE_UNRESOLVED | 25 / 6 | unknown / unknown | negative / positive | no |
| A501 vs A601 | rejected | DIRECTION_ROLE_UNRESOLVED | 11 / 6 | unknown / unknown | negative / positive | no |

## 5. The 19 analytical SUPPORTS claims

All 19 carry an LLM content-support **SUPPORTS** verdict on a **VALID** source link (saved from the original run — not re-verified). 12 pass the verified gate; 6 fail `DISCLOSURE_TIME_UNKNOWN`; 1 fails `CONTENT_VERSION_CHANGED_SINCE_REVIEW`. 15 are real model-NONE classifications (not a source or verification shortfall); 4 matched. For the matched four, **no real direction judgment exists**; the production deterministic stance is attached (not a model result).

| # | Claim | Text (first 80 chars) | Content verification (saved) | Gate verdict | Alpha classification | Where it stops |
|---|---|---|---|---|---|---|
| 1 | `market_agent:market_report:claim:65` | Bullish scenario: Continued momentum carries price toward the Bollinger upper ba | LLM_CONTENT_SUPPORT_VERIFIED SUPPORTS, source link VALID | ELIGIBLE | NONE (model) | classification: model NONE ("no canonical Alpha materially fits") |
| 2 | `market_agent:market_report:claim:85` | Dimension: Momentum; Indicator: MACD; Value (2026-10-06): 36.93; Signal: Bullish | LLM_CONTENT_SUPPORT_VERIFIED SUPPORTS, source link VALID | ELIGIBLE | NONE (model) | classification: model NONE ("no canonical Alpha materially fits") |
| 3 | `fundamental_agent:fund_report:claim:10` | Beta: 2.454 (very high volatility) | LLM_CONTENT_SUPPORT_VERIFIED SUPPORTS, source link VALID | ELIGIBLE | NONE (model) | classification: model NONE ("no canonical Alpha materially fits") |
| 4 | `fundamental_agent:fund_report:claim:31` | Revenue grew from $7,685M (Q2'25) → $9,246M → $10,270M → $10,253M → $11,536M (Q2 | LLM_CONTENT_SUPPORT_VERIFIED SUPPORTS, source link VALID | DISCLOSURE_TIME_UNKNOWN | MATCH A301 | verified-evidence gate: DISCLOSURE_TIME_UNKNOWN |
| 5 | `fundamental_agent:fund_report:claim:33` | The Q1'26 flat-to-down print ($10,253M vs $10,270M) was a pause, but Q2'26 re-ac | LLM_CONTENT_SUPPORT_VERIFIED SUPPORTS, source link VALID | DISCLOSURE_TIME_UNKNOWN | MATCH A301 | verified-evidence gate: DISCLOSURE_TIME_UNKNOWN |
| 6 | `fundamental_agent:fund_report:claim:36` | Gross profit nearly doubled YoY ($6,203M vs $3,059M). | LLM_CONTENT_SUPPORT_VERIFIED SUPPORTS, source link VALID | DISCLOSURE_TIME_UNKNOWN | MATCH A301 | verified-evidence gate: DISCLOSURE_TIME_UNKNOWN |
| 7 | `fundamental_agent:fund_report:claim:59` | Verified: Total Assets rose to $84,464M as of 2026-06-30, from $79,642M as of 20 | LLM_CONTENT_SUPPORT_VERIFIED SUPPORTS, source link VALID | DISCLOSURE_TIME_UNKNOWN | NONE (model) | classification: model NONE ("no canonical Alpha materially fits") |
| 8 | `fundamental_agent:fund_report:claim:81` | Verified: Free Cash Flow fell to $1,558M as of 2026-06-30, from $2,566M as of 20 | LLM_CONTENT_SUPPORT_VERIFIED SUPPORTS, source link VALID | DISCLOSURE_TIME_UNKNOWN | NONE (model) | classification: model NONE ("no canonical Alpha materially fits") |
| 9 | `fundamental_agent:fund_report:claim:88` | Operating cash flow remains robust at $2,366M, though down from $2,955M in Q1'26 | LLM_CONTENT_SUPPORT_VERIFIED SUPPORTS, source link VALID | DISCLOSURE_TIME_UNKNOWN | NONE (model) | classification: model NONE ("no canonical Alpha materially fits") |
| 10 | `fundamental_agent:fund_report:claim:105` | Very high beta (2.454) — AMD will amplify any macro risk-off move. | LLM_CONTENT_SUPPORT_VERIFIED SUPPORTS, source link VALID | ELIGIBLE | NONE (model) | classification: model NONE ("no canonical Alpha materially fits") |
| 11 | `fundamental_agent:fund_report:claim:117` | Category: Market; Metric: Beta; Value: 2.454; Signal: High volatility | LLM_CONTENT_SUPPORT_VERIFIED SUPPORTS, source link VALID | ELIGIBLE | NONE (model) | classification: model NONE ("no canonical Alpha materially fits") |
| 12 | `fundamental_agent:fund_report:claim:118` | Category: Market; Metric: 52W Range; Value: $188.22 – $658.52; Signal: Tripled o | LLM_CONTENT_SUPPORT_VERIFIED SUPPORTS, source link VALID | ELIGIBLE | NONE (model) | classification: model NONE ("no canonical Alpha materially fits") |
| 13 | `fundamental_agent:fund_report:claim:132` | Category: Cash Flow; Metric: TTM FCF; Value: $8.841B; Signal: Strong absolute | LLM_CONTENT_SUPPORT_VERIFIED SUPPORTS, source link VALID | ELIGIBLE | NONE (model) | classification: model NONE ("no canonical Alpha materially fits") |
| 14 | `bull_researcher:investment_debate_state.bull_history:claim:64` | But the MACD line (36.93) remains above the signal line (33.01) — the bullish cr | LLM_CONTENT_SUPPORT_VERIFIED SUPPORTS, source link VALID | ELIGIBLE | NONE (model) | classification: model NONE ("no canonical Alpha materially fits") |
| 15 | `bear_researcher:investment_debate_state.bear_history:claim:13` | And it's an estimate that requires AMD to grow earnings roughly 4x from the curr | LLM_CONTENT_SUPPORT_VERIFIED SUPPORTS, source link VALID | ELIGIBLE | NONE (model) | classification: model NONE ("no canonical Alpha materially fits") |
| 16 | `bear_researcher:investment_debate_state.bear_history:claim:17` | But the forward estimate is $15.72. | LLM_CONTENT_SUPPORT_VERIFIED SUPPORTS, source link VALID | ELIGIBLE | NONE (model) | classification: model NONE ("no canonical Alpha materially fits") |
| 17 | `aggressive_risk:risk_debate.aggressive_history:claim:32` | Downside to the 10 EMA at 618.52 [fragmentid: src388228ad9e12e09d:frag:0] is abo | LLM_CONTENT_SUPPORT_VERIFIED SUPPORTS, source link VALID | ELIGIBLE | NONE (model) | classification: model NONE ("no canonical Alpha materially fits") |
| 18 | `portfolio_manager:final_trade_decision:claim:10` | His second overreach is the PEG defense — he calls 0.64 "priced for a ramp that  | LLM_CONTENT_SUPPORT_VERIFIED SUPPORTS, source link VALID | CONTENT_VERSION_CHANGED_SINCE_REVIEW | MATCH A304 | verified-evidence gate: CONTENT_VERSION_CHANGED_SINCE_REVIEW; evidence qualification (raw view): excluded as UNSUPPORTED_RELATION |
| 19 | `portfolio_manager:final_trade_decision:claim:22` | The asymmetry at $654.91 is negative, and the internal evidence confirms it. | LLM_CONTENT_SUPPORT_VERIFIED SUPPORTS, source link VALID | ELIGIBLE | NONE (model) | classification: model NONE ("no canonical Alpha materially fits") |

* **A301 × 3 (rows 4–6, fundamentals claims 31/33/36 — Total Revenue):** in the raw (unverified) view they are activation-eligible members of three separate fact groups (agent `fundamental_agent`), part of A301's raw score of 44.9 (10 facts, 2 agents). In the official view their contribution is **0**: the linked source `src_582ac24bf4319648` ("AMD income statement Total Revenue snapshot") has `published_at = None`, so the first actual blocker is the verified gate's disclosure-time rule. Nothing else needs to be true first.
* **A304 × 1 (row 18, portfolio manager claim 10, the PEG rebuttal):** two independent blockers: the gate says `CONTENT_VERSION_CHANGED_SINCE_REVIEW` (the saved review's content hash `086818df…` differs from the registry's `73dc193a…` for `src_7e133fa786f7aaa0`; **cause not determined**, so I make no claim about which side is stale), and the raw evidence qualification already excludes it as `UNSUPPORTED_RELATION`. Contribution 0 in both views.
* Other formally adopted evidence: **none**. The official evidence pool is empty for all ten Alphas.

## 6. Service, API and Export

* **Backend restored** this round through the normal permission flow (it was permitted this time): same AMD isolated-database launcher, no active tasks (checked), new log `server_stdout_round17.log`, old logs untouched; new process, `/ready` = ready / real execution configured, and its `COMQUTOR_*` environment is **identical** to the one recorded before the Round-16 stop.
* Through the **real running service** (`verify_live_service.py` → `live_service_verification_result.json`, GET only, 16/16 checks): the recovery run reads `completed` with its lineage and the incomplete-classification disclosure; the original run still reads `incomplete` (973 failures); History lists both; `/agent-outputs` equal apart from `run_id`; artifact manifest hashes match the files; lineage download; the **Export ZIP** (17 members, 878,232 bytes) is byte-identical to the files on disk; graph / conflicts / exposures / stances routes return 200. No final evaluation run exists, so no API/Export/UI check of one was possible. **No browser click-through was done.**

## 7. Hash proofs

Original run `c904d4cc…` (29 files) and the recovery run (29 files) are byte-identical to their pre-direction snapshots (`*_run_hashes_before_direction.json`; checked by the driver and again by the live-service script); `alpha_matches.json` `cf13bca6…`, `structured_agent_outputs.json` `dbec9de6…`, `source_registry.json` `3c98de5a…` unchanged. Protected set (AMD 34-item list, historical request/response run, earlier rounds): **72 of 72 identical** (`final_protected_files_diff.json`). `outputs/runs/` gained one entry: the stopped direction execution.

## 8. T1 — conditions still not met

1. No source-adopted evidence reaches any Alpha: 0 of 10 official pools; no active/dominant Alpha, no admitted Conflict. This is a real result of the data, not a rendering gap, and I do not present it as a complete research conclusion about AMD.
2. Of 261 source-linked claims only 40 are eligible, and those are almost disjoint from the claims the classifier matched to an Alpha (1 matched, excluded as `context_only`).
3. 23 SUPPORTS claims fail `DISCLOSURE_TIME_UNKNOWN`, including the three A301 revenue line items; 1 fails a review/registry hash mismatch whose cause is open; 714 claims carry no source link (not judged wrong wholesale); 143 linked claims are still `PENDING_REVIEW`.
4. Classification is 974 of 975 (the timed-out claim `news_agent:news_report:claim:105`); direction judgments for all 162 pairs do not exist.
5. AMD has no exposure seed for A001 / A003 / A501.
6. The John evidence package (the 261 records with judgment / basis / eligibility / adoption, key summaries, Alpha key bases, both sides of actual Conflicts) was not produced here — there are no actual Conflicts — and the original AMD 34-item list remains judged only from its own frozen materials; this run's sources were not used to backfill it.

## 9. Decision for you

* Do you want the 17 direction requests run anyway? It needs an explicit timeout (history: 40–45 s mostly fails; success needed 600–700 s+). That is a changed frozen parameter, so it needs your authorization and a new plan hash. Section 2 says it would not change this run's score, activation or Conflict.
* Where would you rather spend effort: the verified-evidence side (disclosure times for fiscal line items, the hash mismatch, pending reviews) — the only place the AMD outcome can change?

## 10. Files (this directory)

`run_direction_evaluation.py`, `launch_direction_evaluation.sh`, `preflight_result.json`, `direction_execute_blocked_output.log`, `real_direction_stdout.log`, `direction_execution_report_*.json`, `build_evaluation_analysis.py` + `evaluation_analysis_provisional.json`, `verify_live_service.py` + `live_service_verification_result.json`, `server_stdout_round17.log`, `backend_env_after_restart.txt`, `*_run_hashes_before_direction.json`, `final_protected_files_diff.json`. Code: `comqutor_alpha/direction_evaluation.py` (new), `classification_recovery.py` (saver generalized with defaults preserving the recovery path), additive allowlist / manifest / API-lineage entries; tests `tests/test_direction_evaluation.py` (16) — with the 33 derived-run and gate tests: 49 passed.
