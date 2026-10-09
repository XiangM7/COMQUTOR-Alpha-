# Round 18 — evidence-eligibility breakpoints and an independent recompute (2026-10-07)

Scope: the three located breakpoints, then a recompute of the saved AMD results through the production chain. **Zero Provider / search / data-fetch calls** (a trap on every model and network path recorded 0 attempts during the recompute), no Fresh Run, no direction request, no classification retry, no new research report, no commit/push/Demo, no change to content-verification standards, scoring thresholds, taxonomy or reference labels. T1 / John acceptance is **not** claimed.

New execution **`requal-20261007T174744Z-664040d6`** (`completed`, mode `requalification`) — direct parent `recovery-20261007T053635Z-26d6cd1a`, original research run `c904d4cc-dc09-495c-aec5-b056979948e1`. Alpha classification and the saved content verification are reused verbatim; the only artifact that differs is a **copy** of `source_registry.json`.

## 1. What the time rule has to prove — and what the code actually checked

* **John's wording as recorded in this project:** 09-30 "披露日期缺失时标注时间资格未知，不进入正式已验证支持；不能因此把整个入口排除出任务范围"; 10-04 "保留已知的披露/可用时间及其依据 … 不把报告期末、抓取时间冒充披露时间 … Provider没给披露时间，就保持未知"; 10-05 "当前实时快照的抓取时间可以证明该快照在抓取时可用，但不能冒充历史财报披露时间，也不能证明某个历史日期当时已经知道该数值". The purpose is **look-ahead safety**; the disclosure date was the proxy the gate used, and "known disclosure / **available** time and its basis" is what John asks to keep.
* **Actual trigger of `DISCLOSURE_TIME_UNKNOWN`:** `compute_verified_support_eligibility` refused any bound source with an empty `published_at`. The three yfinance statement snapshots (`src_582ac24b…` income statement, `src_d889dd1e…` balance sheet, `src_40456677…` cash flow) have `published_at = None` **by design** (`y_finance.py`: the provider exposes only each column's period end; "never self-completed"). They carry `observation_date = 2026-06-30` (period end), a `data_snapshot` with the saved periods, `provider = yfinance`, and `retrieved_at = 2026-10-06T17:39:31Z`.
* **What `retrieved_at` is (checked, not assumed):** it is the writer's own clock at output-save time (`retrieved_at = created_at`), taken **after** the agent graph finished — one value for all 35 sources, an **upper bound** on each capture moment, not the per-tool-call time. It equals the run's evidence cutoff (`resolve_evidence_cutoff_at`, basis `MAX_SOURCE_FETCHED_AT`, same calendar day as the analysis date). Independent corroboration from the original records (`time_evidence` in the lineage): the TradingAgents call log covers `17:36:14 → 17:39:31Z`; the fundamentals snapshot's exact capture time `17:37:04.79Z` sits 8 ms before the LLM call that consumed it; each statement's fragment marker is present in the saved fundamentals report; each snapshot's stored hash equals `sha256(excerpt)`.
* **Fix (minimal, versioned):** a separate `availability` record (`source_availability.v1`, basis `REGISTRY_WRITE_TIME_UPPER_BOUND`) on undated **live financial data snapshots only**. The gate **re-validates it from the source's own fields and never trusts a stored flag**: live-captured financial snapshot (provider + data snapshot), `sha256(excerpt) == content_hash`, `available_by` equals the source's own `retrieved_at`, and `available_by ≤ evidence_cutoff_at` (the cutoff comes from the original analysis date and the run's saved fetch moments — never from today). `published_at` stays `None`; the period end is never used. Generation path: the registry writer now stamps this record on new runs. Consumption path: eligibility accepts it as the second time basis. For this run it was added **only to a copy** of the registry by a transform that proves nothing else changed.
* **Refused (tests, §7):** obtained after the cutoff (a later retrieval for an earlier analysis date → `AVAILABILITY_NOT_BEFORE_EVIDENCE_CUTOFF`); a period end earlier than the cutoff is irrelevant; capture time missing/unparseable; forged flag; `available_by` not the source's own `retrieved_at`; unknown version/basis; broken hash; non-financial or snapshot-less sources; dated sources and news are untouched.
* **Honest limits:** the exact per-call capture time of a statement is not recorded (upper bound only), so in a same-day live run `available_by` equals the cutoff by construction. The check is non-vacuous because of the refusal cases above — a registry replayed or reused for an earlier analysis date is refused. Recording a per-source capture time at fetch is the natural follow-up (not done). Macro/FRED sources lacking a disclosure date are **not** covered and stay unverified.

## 2. The "content-hash mismatch" was a binding defect, not a content change

The A304 claim (`portfolio_manager:final_trade_decision:claim:10`) cites two sources by marker (`linked_source_ids = [src_7e133fa7… fundamentals snapshot, src_582ac24b… income statement]`). The verifier chose `used_source_id = src_582ac24b…` and the review binds exactly that: `review.linked_source_id = src_582ac24b…`, `review.content_hash = 086818df…`. The consumer compared that hash with the record's **primary** link `src_7e133fa7…` (`73dc193a…`) and reported `CONTENT_VERSION_CHANGED_SINCE_REVIEW`.

* **Content did not change:** `086818df…` is the stored hash of `src_582ac24b…` in **both** runs; every source's stored hash equals `sha256(excerpt)`; the original and recovery registries are identical; the algorithm is plain sha256 of the stripped excerpt text — it contains no run id or metadata, so a derived identity cannot affect it (`source_hash_facts.json`).
* **Only 1 of 975 claims** has a review bound to a non-primary source; it is this one.
* **Fix:** resolve the review's own bound source (it must be one of the claim's linked sources, else `REVIEW_SOURCE_NOT_LINKED_TO_CLAIM`) and compare the hash with **that** source. Reviews without their own source id and all single-source claims resolve exactly as before; no hash is searched for across sources and no stored hash was edited. Genuinely changed content is still refused (test).
* **Limitation kept visible:** the old review binds only the source the verifier used; the other cited source (`src_7e133fa7…`) has no hash bound to it, so a change there would not be detected by this review. Binding every cited source is a generation-side change needing a new review schema — not done.
* The two defects were **stacked**: binding fix alone moves the claim to `DISCLOSURE_TIME_UNKNOWN`; the availability record then makes it eligible.

## 3. `UNSUPPORTED_RELATION` is not a mapping/consumption defect, and stays open

* **Rejecting function:** `conflict_detector._gather_qualifying_evidence` (relation ∉ `QUALIFYING_RELATIONS`); the activation scorer gives `mention` weight 0.0. **Field:** `alpha_matches…candidate_scores[A304].relation = "mention"`.
* **Producer: code** — `claim_semantics.alpha_relation`, called by `alpha_mapper` when it builds the candidate: it returns `mention` when `semantic_polarity == "mention"` or the assertion is negated. For this claim the text rules set `negated = True`, `semantic_polarity = mention` (reproduced in `a304_blockers`). It is **not** a model output and **not** a failure fallback: the classification itself succeeded (`llm_selected`, the model chose A304).
* **A second, independent exclusion** (found by the counterfactual): setting only the relation to `activation` leaves A304 with 0 evidence, because the activation scorer weights `assertion_status = negated` at 0.0; the claim's deterministic match score for A304 is also 0.0 (`a304_relation_counterfactual_not_applied.json`, computed with the production scorer on a copy, **not applied**).
* **Meaning:** the claim says the last four quarters do not support the forward EPS of $15.72 — a rebuttal of the bulls' PEG defense, which bears on valuation compression (A304) — but a lexical rule cannot tell that from a negation of A304's own thesis. The source supports the claim (axis 1, verified); whether the claim supports or opposes A304 (axis 2) needs a semantic judgment that does not exist here. I did not use keywords or my own reading as a substitute.
* **Needed:** a model judgment of this claim's relation to A304 (support / oppose / background) **and** a decision on whether a model judgment should replace the text rule for the evidence relation of model-selected matches — a design change for John / you, not a minimal fix.

## 4. The 24 time-qualification claims, one by one

(23 reported `DISCLOSURE_TIME_UNKNOWN` + the A304 claim, originally `CONTENT_VERSION_CHANGED_SINCE_REVIEW`.) **All 24 become eligible.** Only 3 reach an official pool; the other 21 are model-NONE (14), matched but `context_only` (A301 ×4, A201 ×2), or excluded by relation (A304 ×1) — see the last column. Eligible claims in the whole run: 40 → **64** (= all 64 SUPPORTS).

| # | Claim (suffix) | Used source (period) | Review | Before | Binding fix only | After | Alpha classification | Quality | Official pool after | If not: first blocker |
|---|---|---|---|---|---|---|---|---|---|---|
| 1 | `fundamental_agent:fund:claim:28` | income statement Total Revenue | LLM SUPPORTS | DISCLOSURE_TIME_UNKNOWN | DISCLOSURE_TIME_UNKNOWN | **ELIGIBLE** | model NONE | context_only | — | model NONE |
| 2 | `fundamental_agent:fund:claim:31` | income statement Total Revenue | LLM SUPPORTS | DISCLOSURE_TIME_UNKNOWN | DISCLOSURE_TIME_UNKNOWN | **ELIGIBLE** | → A301 | analytical | YES | — |
| 3 | `fundamental_agent:fund:claim:33` | income statement Total Revenue | LLM SUPPORTS | DISCLOSURE_TIME_UNKNOWN | DISCLOSURE_TIME_UNKNOWN | **ELIGIBLE** | → A301 | analytical | YES | — |
| 4 | `fundamental_agent:fund:claim:36` | income statement Total Revenue | LLM SUPPORTS | DISCLOSURE_TIME_UNKNOWN | DISCLOSURE_TIME_UNKNOWN | **ELIGIBLE** | → A301 | analytical | YES | — |
| 5 | `fundamental_agent:fund:claim:38` | income statement Total Revenue | LLM SUPPORTS | DISCLOSURE_TIME_UNKNOWN | DISCLOSURE_TIME_UNKNOWN | **ELIGIBLE** | → A201 | context_only | no | evidence qualification: NON_ANALYTICAL_QUALITY |
| 6 | `fundamental_agent:fund:claim:42` | income statement Total Revenue | LLM SUPPORTS | DISCLOSURE_TIME_UNKNOWN | DISCLOSURE_TIME_UNKNOWN | **ELIGIBLE** | model NONE | context_only | — | model NONE |
| 7 | `fundamental_agent:fund:claim:59` | balance sheet Total Assets | LLM SUPPORTS | DISCLOSURE_TIME_UNKNOWN | DISCLOSURE_TIME_UNKNOWN | **ELIGIBLE** | model NONE | analytical | — | model NONE |
| 8 | `fundamental_agent:fund:claim:65` | balance sheet Total Assets | auto-fact SUPPORTS | DISCLOSURE_TIME_UNKNOWN | DISCLOSURE_TIME_UNKNOWN | **ELIGIBLE** | model NONE | context_only | — | model NONE |
| 9 | `fundamental_agent:fund:claim:81` | cash flow Free Cash Flow | LLM SUPPORTS | DISCLOSURE_TIME_UNKNOWN | DISCLOSURE_TIME_UNKNOWN | **ELIGIBLE** | model NONE | analytical | — | model NONE |
| 10 | `fundamental_agent:fund:claim:88` | cash flow Free Cash Flow | LLM SUPPORTS | DISCLOSURE_TIME_UNKNOWN | DISCLOSURE_TIME_UNKNOWN | **ELIGIBLE** | model NONE | analytical | — | model NONE |
| 11 | `fundamental_agent:fund:claim:121` | income statement Total Revenue | LLM SUPPORTS | DISCLOSURE_TIME_UNKNOWN | DISCLOSURE_TIME_UNKNOWN | **ELIGIBLE** | model NONE | context_only | — | model NONE |
| 12 | `fundamental_agent:fund:claim:122` | income statement Total Revenue | LLM SUPPORTS | DISCLOSURE_TIME_UNKNOWN | DISCLOSURE_TIME_UNKNOWN | **ELIGIBLE** | → A301 | context_only | no | evidence qualification: NON_ANALYTICAL_QUALITY |
| 13 | `fundamental_agent:fund:claim:126` | balance sheet Total Assets | LLM SUPPORTS | DISCLOSURE_TIME_UNKNOWN | DISCLOSURE_TIME_UNKNOWN | **ELIGIBLE** | model NONE | context_only | — | model NONE |
| 14 | `fundamental_agent:fund:claim:129` | balance sheet Total Assets | LLM SUPPORTS | DISCLOSURE_TIME_UNKNOWN | DISCLOSURE_TIME_UNKNOWN | **ELIGIBLE** | → A201 | context_only | no | evidence qualification: NON_ANALYTICAL_QUALITY |
| 15 | `fundamental_agent:fund:claim:130` | cash flow Free Cash Flow | LLM SUPPORTS | DISCLOSURE_TIME_UNKNOWN | DISCLOSURE_TIME_UNKNOWN | **ELIGIBLE** | model NONE | context_only | — | model NONE |
| 16 | `bull_researcher:bull:claim:21` | income statement Total Revenue | LLM SUPPORTS | DISCLOSURE_TIME_UNKNOWN | DISCLOSURE_TIME_UNKNOWN | **ELIGIBLE** | → A301 | context_only | no | evidence qualification: NON_ANALYTICAL_QUALITY |
| 17 | `bull_researcher:bull:claim:23` | income statement Total Revenue | LLM SUPPORTS | DISCLOSURE_TIME_UNKNOWN | DISCLOSURE_TIME_UNKNOWN | **ELIGIBLE** | model NONE | context_only | — | model NONE |
| 18 | `bull_researcher:bull:claim:24` | income statement Total Revenue | LLM SUPPORTS | DISCLOSURE_TIME_UNKNOWN | DISCLOSURE_TIME_UNKNOWN | **ELIGIBLE** | model NONE | context_only | — | model NONE |
| 19 | `bull_researcher:bull:claim:34` | balance sheet Total Assets | LLM SUPPORTS | DISCLOSURE_TIME_UNKNOWN | DISCLOSURE_TIME_UNKNOWN | **ELIGIBLE** | model NONE | context_only | — | model NONE |
| 20 | `bull_researcher:bull:claim:35` | balance sheet Total Assets | auto-fact SUPPORTS | DISCLOSURE_TIME_UNKNOWN | DISCLOSURE_TIME_UNKNOWN | **ELIGIBLE** | model NONE | context_only | — | model NONE |
| 21 | `bear_researcher:bear:claim:16` | income statement Total Revenue | LLM SUPPORTS | DISCLOSURE_TIME_UNKNOWN | DISCLOSURE_TIME_UNKNOWN | **ELIGIBLE** | model NONE | context_only | — | model NONE |
| 22 | `aggressive_risk_analyst:aggr:claim:10` | income statement Total Revenue | LLM SUPPORTS | DISCLOSURE_TIME_UNKNOWN | DISCLOSURE_TIME_UNKNOWN | **ELIGIBLE** | → A301 | context_only | no | evidence qualification: NON_ANALYTICAL_QUALITY |
| 23 | `aggressive_risk_analyst:aggr:claim:12` | income statement Total Revenue | LLM SUPPORTS | DISCLOSURE_TIME_UNKNOWN | DISCLOSURE_TIME_UNKNOWN | **ELIGIBLE** | → A301 | context_only | no | evidence qualification: NON_ANALYTICAL_QUALITY |
| 24 | `portfolio_manager:PM:claim:10` | income statement Total Revenue | LLM SUPPORTS | CONTENT_VERSION_CHANGED_SINCE_REVIEW | DISCLOSURE_TIME_UNKNOWN | **ELIGIBLE** | → A304 | analytical | no | evidence qualification: UNSUPPORTED_RELATION |

## 5. Result of the independent recompute (official view)

| Alpha | Official evidence claims | Unique facts | Agents | Direction | Score | Level | Exposure (final) | Why it stays below `active` (score 50) |
|---|---|---|---|---|---|---|---|---|
| A001 | 0 → **0** | 0 → 0 | 0 → 0 | unknown → unknown | 0.0 → **0.00** | candidate → candidate | no seed | no official evidence (see funnel) |
| A003 | 0 → **0** | 0 → 0 | 0 → 0 | unknown → unknown | 0.0 → **0.00** | candidate → candidate | no seed | no official evidence (see funnel) |
| A101 | 0 → **0** | 0 → 0 | 0 → 0 | unknown → unknown | 0.0 → **0.00** | candidate → candidate | 0.4 | no official evidence (see funnel) |
| A102 | 0 → **0** | 0 → 0 | 0 → 0 | unknown → unknown | 0.0 → **0.00** | candidate → candidate | 0.275 | no official evidence (see funnel) |
| A103 | 0 → **0** | 0 → 0 | 0 → 0 | unknown → unknown | 0.0 → **0.00** | candidate → candidate | 0.325 | no official evidence (see funnel) |
| A201 | 0 → **0** | 0 → 0 | 0 → 0 | unknown → unknown | 0.0 → **0.00** | candidate → candidate | 0.425 | no official evidence (see funnel) |
| A301 | 0 → **3** | 0 → 3 | 0 → 1 | unknown → positive | 0.0 → **21.31** | candidate → candidate | 0.5 | 21.31 < 50: evidence quality 1.64/35, agent independence 4.67/20 (1 of 3 agents), local structure 0/20, ticker-specific 0/10 (recency 10/10, direction 5/5) |
| A304 | 0 → **0** | 0 → 0 | 0 → 0 | unknown → unknown | 0.0 → **0.00** | candidate → candidate | 0.375 | no official evidence (see funnel) |
| A501 | 0 → **0** | 0 → 0 | 0 → 0 | unknown → unknown | 0.0 → **0.00** | candidate → candidate | no seed | no official evidence (see funnel) |
| A601 | 0 → **0** | 0 → 0 | 0 → 0 | unknown → unknown | 0.0 → **0.00** | candidate → candidate | 0.375 | no official evidence (see funnel) |

* **A301** is the only Alpha that gains official evidence: **3 claims, 3 unique facts** (each its own fact group; no merge with another claim, none cross-agent), **1 agent** (`fundamental_agent`), direction positive, score **21.3056**, level **candidate**, exposure 0.35 → 0.5. The raw (unverified) view still shows A301 with 23 claims / 10 facts / score 44.9; the other 20 raw-pool claims lack a source link (15), a usable review method (4) or SUPPORTS status (1).
* **Actual contribution (production scorer, leave-one-out, reproduces the pipeline score exactly: 21.3056):** claim 31 contributes **6.6389** (removing it drops 21.3056 to 14.6667: the whole evidence-quality and direction terms); claims 33 and 36 contribute **0.0** at the margin — all three have the qualifying `activation` relation, but the activation formula weights evidence by the mapper's deterministic match score, which is 0.1873 for claim 31 and 0.0 for 33 and 36. They count as facts and as the agent's support, not as weight.
* **Why not `active`:** the first unmet condition is the score itself — 21.31 against `ACTIVE_THRESHOLD = 50.0`; the components above show where the points are missing (one agent of three, no ticker-specific evidence, no local structure support, near-zero evidence quality). No threshold was touched.
* **Conflicts** — 8 declared pairs, **0 admitted, 0 candidates**; the first blocker is unchanged: A304 still has no official evidence, so its direction is `unknown` and roles are unresolved. A301 vs A304 now has a positive side (21.31) but not a resolvable opponent. Stance-dependent admissibility is still never reached (direction judgments, which were not obtained, would not change this):

| Pair | Before | After | Official direction A / B (after) | Official score A / B (after) | Stance-dependent admissibility reached |
|---|---|---|---|---|---|
| A001 vs A501 | DIRECTION_ROLE_UNRESOLVED | DIRECTION_ROLE_UNRESOLVED | unknown / unknown | 0.0 / 0.0 | no |
| A003 vs A501 | MISSING_LEFT_EVIDENCE, DIRECTION_ROLE_UNRESOLVED | MISSING_LEFT_EVIDENCE, DIRECTION_ROLE_UNRESOLVED | unknown / unknown | 0.0 / 0.0 | no |
| A101 vs A304 | DIRECTION_ROLE_UNRESOLVED | DIRECTION_ROLE_UNRESOLVED | unknown / unknown | 0.0 / 0.0 | no |
| A102 vs A304 | MISSING_LEFT_EVIDENCE, DIRECTION_ROLE_UNRESOLVED | MISSING_LEFT_EVIDENCE, DIRECTION_ROLE_UNRESOLVED | unknown / unknown | 0.0 / 0.0 | no |
| A201 vs A304 | DIRECTION_ROLE_UNRESOLVED | DIRECTION_ROLE_UNRESOLVED | unknown / unknown | 0.0 / 0.0 | no |
| A301 vs A304 | DIRECTION_ROLE_UNRESOLVED | DIRECTION_ROLE_UNRESOLVED | positive / unknown | 21.3056 / 0.0 | no |
| A304 vs A601 | DIRECTION_ROLE_UNRESOLVED | DIRECTION_ROLE_UNRESOLVED | unknown / unknown | 0.0 / 0.0 | no |
| A501 vs A601 | DIRECTION_ROLE_UNRESOLVED | DIRECTION_ROLE_UNRESOLVED | unknown / unknown | 0.0 / 0.0 | no |

## 6. Classification — the correct four-way split (never "812 model NONE")

975 claims = **748 model NONE** (incl. the 2 original) + **64 model selections overridden to `no_match` by mapper gates** (all A001: 51 positive-requirement gate, 13 invalidation) + **162 final matches** + **1 timed out** (`news_agent:news_report:claim:105`, unresolved, not retried). Direction: **not obtained** — the stance in `alpha_matches` is the production deterministic classifier, not a model result; the run's lineage records this beside the program-level `completed`.

## 7. Tests (synthetic / separate from the real AMD results)

* `tests/test_evidence_requalification.py` — **18 passed**: live snapshot before the cutoff eligible with `published_at` still `None`; after the cutoff; period end earlier than the cutoff; missing/unparseable time; forged flag, decoupled `available_by`, unknown basis, broken hash; only live financial snapshots annotated; deterministic and clock-free; same content bound to the used source accepted; real content change refused; review naming an uncited source refused; no hash-shopping; the stacked-defect pattern; the registry **writer**; a qualifying relation consumed and `mention` excluded; one marked reproduction on the saved real claim.
* Affected suites (verified gate, T1 chains, content-support, automated verification, T2 qualified-evidence scenarios, source provenance, writers, API/Export, recovery / direction / completion, importer and leak guards): **398 passed + 55 passed**, 3 Postgres source-field tests **passed** against the isolated database (they skip without the URL). No full regression (as instructed). Logs and diffs: `test_logs/`, `diffs/`.

## 8. API / Export / service

* Through the real API routes (current code, real isolated database, `verify_requalification.py` → `api_requalification_verification.json`, **17/17**): response `completed` with the new lineage block (parent + original + the requalification summary); History lists all three runs; graph score 21.3056 and exposure 0.5 equal the artifacts; conflicts route equals the artifact; classification incompleteness still disclosed; the Export ZIP (17 members, 881,025 bytes) is **byte-identical** to the files; its registry carries the availability record on exactly the 3 snapshots and the **original run's registry does not**; `published_at` unchanged; `alpha_matches` equals the parent's apart from `run_id`.
* **The always-on service predates this round's code** (started 00:00 today). It reads the run, graph, exposures and artifacts correctly, but shows no lineage block, answers 400 for the two new artifact names, and its read-time verified-support diagnostic still reports 6 of the 500 API-visible claims as `DISCLOSURE_TIME_UNKNOWN` where the stored result says `ELIGIBLE` (`live_service_requalification_verification.json`). I did **not** restart it unasked (last time a stop followed by a refused relaunch left it down). To load the new code, from the repo root with no active runs: stop the service, then `bash docs/audit_artifacts/round_source_linking_t0_t2/round11_amd_fresh_run_20261006/run_amd_fresh_run_isolated_db.sh > docs/audit_artifacts/round_source_linking_t0_t2/round18_evidence_requalification_20261007/server_stdout_round18.log 2>&1 &`. No browser click-through was done.

## 9. Hash proofs

Original run (29 files) and recovery run (29 files): byte-identical to their pre-recompute snapshots (`*_run_hashes_before_requalification.json`); `alpha_matches.json` `cf13bca6…`, `structured_agent_outputs.json` `dbec9de6…`, `source_registry.json` `3c98de5a…` unchanged. Protected set (AMD 34-item list, historical request/response run, earlier rounds): **72 of 72 identical** (`final_protected_files_diff.json`). The registry in the new run is a copy; the original registry was never opened for writing.

## 10. What is still missing — and what it needs

1. **A model judgment** of the A304 claim's relation to A304 (and, more broadly, whether model-selected matches should take their evidence relation from a model instead of the text rule). Not supplied.
2. **Direction judgments** for the 162 pairs — not obtained (45 s timeout, Round 17); they would not change this run's scores or Conflicts.
3. **Source links**: 714 claims have none (not judged wrong wholesale); 15 of A301's 23 raw-pool claims are among them. External material would be needed to link them.
4. **Per-source capture time** at fetch, and binding **every** cited source's hash in a review — generation-side improvements; not done.
5. No active Alpha or Conflict is not a T1 failure by itself; what this round shows is that a verified, time-qualified financial claim now travels from source to official pool to API and Export with its basis recorded — and where the rest stops.
6. The original AMD 34-item list is still judged only from its own frozen materials; this run's sources were not used to backfill it.

## 11. Files

`run_requalification.py`, `analyze_requalification.py`, `verify_requalification.py`, `requalification_dry_run_output.log`, `requalification_execute_output.log`, `requalification_execution_report_*.json`, `before_eligibility_all_975_claims.json`, `source_hash_facts.json`, `a304_relation_counterfactual_not_applied.json`, `*_run_hashes_before_requalification.json`, `api_requalification_verification.json`, `live_service_requalification_verification.json`, `final_protected_files_diff.json`, `pre_change_snapshot/`, `diffs/`, `test_logs/`. In the run: `requalification_lineage.json`, `evidence_eligibility_requalification.json` (per-claim JSON for all 24, per-Alpha before/after, conflicts, leave-one-out, time evidence). Code: `comqutor_alpha/source_provenance.py` (availability + binding), `adapters/tradingagents_output_writer.py` (stamps the record), `classification_recovery.py` (verified artifact transform + new execution type), additive allowlist / manifest / API-lineage entries; tests `tests/test_evidence_requalification.py`.
