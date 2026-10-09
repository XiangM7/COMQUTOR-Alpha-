# Round 16 — real AMD Alpha-classification recovery (2026-10-06 / 10-07 UTC)

Scope executed: the frozen Round-15 plan, authorized for at most 973 actual `alpha_classifier` requests. **Not** run: direction tasks, content re-verification, search, data fetch, research agents, Fresh Run. No full regression, no commit/push, no Demo, no change to verification standards, scoring thresholds or taxonomy. T1 / John acceptance is **not** claimed.

Execution id **`recovery-20261007T053635Z-26d6cd1a`**, based on `c904d4cc-dc09-495c-aec5-b056979948e1`, saved in `outputs/runs/recovery-20261007T053635Z-26d6cd1a/` and in the isolated `comqutor_alpha_test` database (`research_runs`: `completed`, `execution_mode=recovery`; 975 `agent_outputs` rows).

## 1. Recovery of the 973 claims

| | |
|---|---|
| Provider requests actually sent | **955** (cap 973; failed and sent both count). Every request was `alpha_classifier`; nothing else reached the wire. |
| Responses saved | 954, all HTTP 200, all valid classifications (stage-A gate passed on the first 4; 41 batches; stop reason: none) |
| Not sent | 18 claims were served by the run-local exact response cache from an identical-input claim's real answer (ledger `provider_status=not_called`, each with its `source_call_id`). That is why 955, not 973, requests were needed. |
| Failure | **1**: `news_agent:news_report:claim:105` — request audited, **no response within 45 s** (`WEEK2_LLM_TIMEOUT`, 45,011 ms). Counted against the cap, **not resent**, saved as `llm_unavailable / provider_timeout`. Whether the Provider processed or billed it is unknown from local state. |
| Usage | prompt 1,884,981 tokens (1,236,608 cache-hit / 648,373 cache-miss), completion 545,572, total **2,430,553**. Wall clock ≈ 21 min (05:36:39 → 05:57:22 UTC). Success latency p50 2.15 s, p95 12.6 s, max 41.8 s. |
| Configuration actually in force | model `deepseek-v4-flash`; client and application retries 0; timeout 45 s exported explicitly and verified on every audited request; concurrency 4; audit on; no max-tokens/base-URL override; task allowlist `[alpha_classifier]`. |
| Resume / cap accounting | single process, no resume was needed; 18 requests of allowance went unused. |

## 2. Complete 975-claim classification

| Result | Claims |
|---|---|
| Valid Alpha selection | **162** (A304 51 · A301 43 · A201 20 · A601 16 · A501 14 · A101 9 · A103 5 · A001 4) |
| Valid NONE (a completed classification) | **812** (810 recovered + the 2 original valid NONEs, reused verbatim) |
| Failed / unknown | **1** (the timed-out claim above; kept as a failure, never turned into NONE) |

**Is classification complete? No — 974 of 975.** The API says so: "1 of 975 claims have no usable classification result … the absence of a dominant Alpha structure or admitted conflict cannot yet be read as 'none exists'." No retry was made, as frozen.

How each claim was obtained (`recovery_lineage.json`): 2 original valid result · 954 own request · 18 identical-input cache · 1 failed attempt.

## 3. The 19 analytical SUPPORTS claims (frozen order; A = the 4-claim parallel-config gate)

All 19 were failures in the original run (`provider_error`); all 19 now have a valid result from their **own** request — 4 matches, 15 valid NONE, 0 failures.

| # | Stage | Claim | Text (first 90 chars) | Result | Obtained |
|---|---|---|---|---|---|
| 1 | A | `market_agent:market_report:claim:65` | Bullish scenario: Continued momentum carries price toward the Bollinger upper band at 691. | NONE (valid) | own request |
| 2 | A | `market_agent:market_report:claim:85` | Dimension: Momentum; Indicator: MACD; Value (2026-10-06): 36.93; Signal: Bullish; Interpre | NONE (valid) | own request |
| 3 | A | `fundamental_agent:fund_report:claim:10` | Beta: 2.454 (very high volatility) | NONE (valid) | own request |
| 4 | A | `fundamental_agent:fund_report:claim:31` | Revenue grew from $7,685M (Q2'25) → $9,246M → $10,270M → $10,253M → $11,536M (Q2'26). | MATCH A301 (Revenue Expansion) | own request |
| 5 | B | `fundamental_agent:fund_report:claim:33` | The Q1'26 flat-to-down print ($10,253M vs $10,270M) was a pause, but Q2'26 re-accelerated  | MATCH A301 (Revenue Expansion) | own request |
| 6 | B | `fundamental_agent:fund_report:claim:36` | Gross profit nearly doubled YoY ($6,203M vs $3,059M). | MATCH A301 (Revenue Expansion) | own request |
| 7 | B | `fundamental_agent:fund_report:claim:59` | Verified: Total Assets rose to $84,464M as of 2026-06-30, from $79,642M as of 2026-03-31 ( | NONE (valid) | own request |
| 8 | B | `fundamental_agent:fund_report:claim:81` | Verified: Free Cash Flow fell to $1,558M as of 2026-06-30, from $2,566M as of 2026-03-31 ( | NONE (valid) | own request |
| 9 | B | `fundamental_agent:fund_report:claim:88` | Operating cash flow remains robust at $2,366M, though down from $2,955M in Q1'26. | NONE (valid) | own request |
| 10 | B | `fundamental_agent:fund_report:claim:105` | Very high beta (2.454) — AMD will amplify any macro risk-off move. | NONE (valid) | own request |
| 11 | B | `fundamental_agent:fund_report:claim:117` | Category: Market; Metric: Beta; Value: 2.454; Signal: High volatility | NONE (valid) | own request |
| 12 | B | `fundamental_agent:fund_report:claim:118` | Category: Market; Metric: 52W Range; Value: $188.22 – $658.52; Signal: Tripled off low | NONE (valid) | own request |
| 13 | B | `fundamental_agent:fund_report:claim:132` | Category: Cash Flow; Metric: TTM FCF; Value: $8.841B; Signal: Strong absolute | NONE (valid) | own request |
| 14 | B | `bull_researcher:investment_debate_state.bull_history:claim:64` | But the MACD line (36.93) remains above the signal line (33.01) — the bullish crossover is | NONE (valid) | own request |
| 15 | B | `bear_researcher:investment_debate_state.bear_history:claim:13` | And it's an estimate that requires AMD to grow earnings roughly 4x from the current TTM EP | NONE (valid) | own request |
| 16 | B | `bear_researcher:investment_debate_state.bear_history:claim:17` | But the forward estimate is $15.72. | NONE (valid) | own request |
| 17 | B | `aggressive_risk:risk_debate.aggressive_history:claim:32` | Downside to the 10 EMA at 618.52 [fragmentid: src388228ad9e12e09d:frag:0] is about 5.5%. | NONE (valid) | own request |
| 18 | B | `portfolio_manager:final_trade_decision:claim:10` | His second overreach is the PEG defense — he calls 0.64 "priced for a ramp that the last f | MATCH A304 (Multiple Compression) | own request |
| 19 | B | `portfolio_manager:final_trade_decision:claim:22` | The asymmetry at $654.91 is negative, and the internal evidence confirms it. | NONE (valid) | own request |

## 4. Derived run, and how it reads

* Lineage: `based_on_run_id`, execution type `alpha_classification_recovery`, a 975-entry identity map (claim ids, agent output ids, text, evidence, sources and verification bindings preserved verbatim; only `run_id` fields rebased). The execution's own alpha-matches, graph, activations, conflicts, summary, audit, manifest and formal-acceptance artifacts were produced by the existing production pipeline with zero model calls.
* **Lineage correction (disclosure).** As first written, the lineage labelled all 973 recovered claims `recovered_real_classification`, which was false for the timed-out claim and the 18 cache-served claims. I amended `recovery_lineage.json` (first-written copy and both sha256 kept in this directory; every changed claim and its evidence recorded inside the artifact under `amendments`; manifest hashes rebuilt with the production function) and fixed the labeling in the code, with tests. Nothing else in the run changed.
* Verified through the real API routes (`verify_derived_run_via_api.py` → `api_verification_result.json`; 11/11 checks): derived response `completed` with its `lineage` block and the incomplete-classification disclosure; `/status`; History lists both runs; `/agent-outputs` equal to the original's apart from `run_id` (500 rows each); `/artifacts` complete with all 17 manifest hashes matching the files on disk; lineage download; the **Export ZIP** (17 members, 878,232 bytes) is byte-identical member by member to the files on disk, and its `alpha_matches.json` has 975 claims all under the new run id (1 not `llm`: the timed-out claim).
* The **original run still reads `incomplete`** (973 failures, no lineage block).
* **Two separate statuses.** Classification complete: **no** (1 unknown). Follow-up evaluation complete: **no** — the direction tasks have not been run. The derived run's current graph shows no dominant Alpha and 0 conflicts; that is a *provisional* state computed with the deterministic stance, and must not be read as "no signal". Some Alphas already carry scores in that provisional view; "has a score" is not "activated", and nothing was interpreted this round.

## 5. Hash proofs

* The original run directory (29 files) is byte-identical to the snapshot taken before the real recovery; `alpha_matches.json` `cf13bca6…`, `structured_agent_outputs.json` `dbec9de6…`, `source_registry.json` `3c98de5a…` unchanged.
* Protected set (original run, AMD 34-item list, historical request/response run, earlier rounds): **72 of 72 identical** (`final_protected_files_diff.json`).
* `outputs/runs/` gained exactly one entry: the derived run.

## 6. Direction tasks needed (not sent; not part of the 973)

`evidence_stance_followup_manifest.json` (in the derived run and its Export): 162 matched claims → **162 (claim, Alpha) pairs**, **0 reusable** (the original run has no LLM direction results), batches of 10 → **independent budget 17 requests** (valid only with `MAX_RETRIES=0` exported). `requires_separate_authorization: true`, `counted_against_classification_cap: false`, `sent_by_this_manifest: 0`. Formal scoring, activation and Conflict conclusions wait for those tasks and a recompute through the existing production chain. The one timed-out claim stays unclassified unless you decide otherwise; I did not retry it.

## 7. Pre-send checks and what did not go to plan

* **Postgres path (verified).** In a scratch database on the isolated test server (`comqutor_alpha_r16_precheck_test`; dropped afterwards, absence verified) the same 23 derived-run tests passed on PostgreSQL 16 with fixed-response fake HTTP — including the API reads, History and Export. I used a scratch database rather than `comqutor_alpha_test` itself so nothing marked-as-test could appear in the database the UI reads. The real test database was only read (all 7 migrations applied; 0 active runs). The production database was never connected to. Evidence: `postgres_precheck_result.json`, `postgres_precheck_pytest_output.log`.
* Inputs, 975 identities, verification bindings, frozen plan (`593271724790d08e…`) and real configuration were re-verified identical before sending (frozen config rebuilt byte-identical).
* **The always-on backend is currently DOWN and I could not restart it.** It was started before the Round-14/15 code (it still showed the original run as plain `completed`), so a refresh was needed. After confirming zero running/queued runs (twice) and recording its environment, I stopped it with `TaskStop` and tried to relaunch it with the same AMD isolated-database launcher; the permission system denied that launch (real-world-transactions) and I did not try another route. Consequently **the check that the actual service can read the derived run is NOT done**; the API verification above is the same routes in-process, read-only, against the real isolated DB and real run directory. To bring the service back, from the repo root: `bash docs/audit_artifacts/round_source_linking_t0_t2/round11_amd_fresh_run_20261006/run_amd_fresh_run_isolated_db.sh > docs/audit_artifacts/round_source_linking_t0_t2/round16_real_recovery_20261006/server_stdout_round16.log 2>&1 &` (its environment before the stop is in `backend_env_before_restart.txt`, credentials redacted). The old stdout log `server_stdout_round2.log` was not touched.
* Tests after the label fix (targeted, no full regression): 52 passed (derived run 23, staged executor 23, mid-batch crash 3, downstream zero-call 3) and 10 passed (gate/real-path), including two new tests for the labeling.
* The recovery script wrote its own execution report into the Round-15 directory (its fixed output path); a copy is here as `recovery_execution_report_recovery-20261007T053635Z-26d6cd1a.json`. The acknowledgement was exported inline for that single command and is stored nowhere.

## 8. Files (this directory)

`real_recovery_stdout.log`, `real_recovery_results.json`, `recovery_execution_report_*.json`, `recovery_progress.py`, `amend_lineage_labels.py` + `recovery_lineage_as_first_written.json`, `verify_derived_run_via_api.py` + `api_verification_result.json`, `postgres_precheck.py` (+ result/log), `original_run_hashes_before_real_recovery.json`, `final_protected_files_diff.json`, `preflight_*`, `backend_env_before_restart.txt`.
