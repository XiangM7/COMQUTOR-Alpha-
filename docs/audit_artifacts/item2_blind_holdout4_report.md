# QA Closure v0.1.2 — Item 2 Blind Holdout #4 — Formal Acceptance of Pure-LLM Alpha Mapper

**This is the FIRST formal blind acceptance test after the Pure-LLM semantic
authority migration, the select/none Alpha v3 contract, removal of
deterministic semantic fallback, and MATCHED/NONE/UNAVAILABLE production-
boundary hardening. Holdout #3 was already consumed (development
re-evaluation) and was NOT reused as H4 input.**

## 1-3. Repository state

- Branch: `comqutor-structure-layer`
- HEAD: `8ecf6bfdf7fd8203e223b220be8ca244da92d1f1` (unchanged throughout)
- Starting worktree: intentionally dirty from prior authorized tasks, preserved unchanged; no `reset`/`restore`/`checkout`/`clean`/`stash` used; no commit/push.

## 4-7. Frozen architecture identity

Verified directly from current source (not from prior reports) before any sampling — see `item2_blind_holdout4_freeze_manifest.json` for the full verification trail:
- Full canonical taxonomy (10 Alphas) shown to the Alpha LLM, unrestricted by deterministic eligibility/AI-gate/threshold.
- `alpha_classifier` prompt v3, output schema v2, input schema v2, decisions restricted to `select`/`none` only.
- No deterministic semantic fallback exists on any path (disabled/no-gateway/timeout/error/malformed/invalid-ID all resolve to `unavailable`, never a deterministic Alpha).
- `deterministic_top_alpha`/`deterministic_match_status` are diagnostics only.
- AI gate and `DEFAULT_MIN_MATCH_SCORE=0.35` cannot veto an LLM selection (confirmed by direct code read).
- B1/B2/B4 rule files (`evidence_stance.py`, `conflict_admissibility.py`, `conflict_detector.py`, `activation_scorer_v2.py`) show **zero diff** from HEAD.
- Provider/model: `anthropic` / `claude-sonnet-4-6` (`comqutor_anthropic_medium_sonnet46_v1` profile), unchanged from H3.

## 8-9. Historical exclusion inventory

| Source | Rows |
|---|---|
| old-50 development set (`docs/evidence_review_sample_records.json`) | 50 |
| Blind Holdout #1 (`item2_blind_holdout_100.csv`) | 100 |
| Blind Holdout #2 (`item2_blind_holdout_141_v2.csv`) | 141 |
| Blind Holdout #3 (`item2_blind_holdout3_frozen.csv`) | 152 — **SHA-256 verified `e6c778d3bbfb65e7bf9e6a72580d499424f1371c69f2027f477faae15ab82bc6` matches exactly before use** |

Exclusion built from exact `claim_id` **and** `normalize_claim_for_dedupe`-normalized evidence text (the repository's existing canonical dedupe normalization, reused — never invented). Total exclusion set: rows from all four sources combined.

**Methodological note (material, disclosed):** Holdout #3's own build script filtered its candidate pool to rows where the *prior* system had already produced `match_status=="matched"` — i.e., it depended on historical system output. Task spec section 8 explicitly forbids this for H4 ("Sampling must NOT depend on current matched_alpha... Do not select rows based on current Alpha Mapper output"), so H4's candidate pool was built differently: directly from `structured_agent_outputs.json`, gated only by the pre-existing, purely-structural `claim_quality.is_claim_eligible(record, CONSUMER_MAPPING)` admissibility check (a property of the claim record from the B0 adapter, never of anything the Alpha Mapper computes). This is **not a precedent violation** — it is a direct, literal compliance with this task's own stricter sampling-independence requirement, made explicitly and disclosed here because it materially changes the character of the pool (much larger, much less pre-filtered toward "looks like a confident Alpha match") relative to H3.

## 9-10. Unseen source-pool size and final H4 N

- 17 real, artifact-complete research runs discovered on disk (1 additional run excluded: no structured/alpha_matches artifacts; 3 leftover error-log-only directories excluded: not real pipeline runs).
- Genuinely unseen pool after historical exclusion + self-dedup: **13,663 rows** across 8 tickers (AMD, GOOGL, MSFT, MU, NVDA, QQQ, SNDK, TSM). SNDK/TSM — reported "exhausted" under H3's own narrower, system-output-dependent pool definition — have abundant eligible evidence (1,236 and 801 rows respectively) under H4's source-only definition; this is a genuine finding, not an error.
- Pool size is far in excess of the preferred N=150-200 target — no `HOLDOUT4_INSUFFICIENT_UNSEEN_POOL` condition; no STOP triggered.
- **Final H4 N = 200** (150-200 preferred range).

## 11. Frozen CSV

- Path: `docs/audit_artifacts/item2_blind_holdout4_frozen.csv`
- SHA-256: `20100402208b97ef0b0a2cbd6010e1bd6132031283acc84fda53437df3e17639`
- Exactly 7 columns: `sample_id, run_id, ticker, claim_id, agent, claim, evidence` — no system fields, no historical labels, no candidate scores.
- Sampling: flat per-ticker uniform random draw (deterministic seed `item2_blind_holdout4_deterministic_seed`), 25 rows/ticker × 8 tickers = 200, zero shortfall on any ticker. No dependency on current/deterministic Alpha output, candidate scores, AI gate, threshold, B1 stance, or reviewer labels at any point before freeze.

## 12. Ticker / run / agent distribution (observed, not engineered)

Ticker: AMD 25, GOOGL 25, MSFT 25, MU 25, NVDA 25, QQQ 25, SNDK 25, TSM 25 (flat by design).
Agent (observed only): fundamental_agent, bull_researcher, bear_researcher, news_agent, sentiment_agent, market_agent, aggressive/neutral/conservative_risk_analyst, research_manager, portfolio_manager, all represented — full breakdown in `item2_blind_holdout4_freeze_manifest_sampling.json`.

## 13-14. Reviewer blindness and calls

Reviewer prompt/schema/batching frozen **before** any reviewer call (`item2_blind_holdout4_reviewer_freeze.json`) and never altered afterward. Reviewer saw only `sample_id/ticker/claim/evidence` + the full canonical taxonomy — never `matched_alpha`, `deterministic_top_alpha`, scores, gate/threshold results, `match_status`, B1 stance, or any prior Holdout label. Independent client/session, separate from the production inference phase.

- Reviewer Provider calls: **20 logical calls, 20 attempts, 0 retries, 0 malformed batches, 0 missing rows.**

## 15-16. System Provider calls

Real production `map_claim_to_alpha` (Pure-LLM path), chunked 2×100 from the start (no `MAX_SERVER_CALLS` cap hit).

- System Provider calls: **200 logical calls, 200 attempts, 0 retries, 0 timeouts, 0 provider errors, 0 malformed outputs, 0 invalid Alpha IDs.**

## 16-19. Cache / decision counts

- Cache hit count: **0** (no `semantic_runtime` attached in this evaluation script — every call is a genuine fresh Provider call, no v1/v2/H3-era cache reuse possible).
- System SELECT count: **78**
- System NONE count: **122**
- System UNAVAILABLE count: **0**

## 20. OFFICIAL RESULT

```
alpha_match_accuracy = 148 / 200 = 74.00%
threshold: >= 75.00%
```

## 21. Exact verdict

**ALPHA MAPPER ACCEPTANCE: FAIL** (74.00% < 75.00%, by 2 correct rows / 1.00 percentage point)

## 22-23. Per-ticker / per-Alpha / AI-family accuracy

| Ticker | Accuracy |
|---|---|
| AMD | 20/25 = 80.0% |
| GOOGL | 15/25 = 60.0% |
| MSFT | 20/25 = 80.0% |
| MU | 20/25 = 80.0% |
| NVDA | 14/25 = 56.0% |
| QQQ | 18/25 = 72.0% |
| SNDK | 21/25 = 84.0% |
| TSM | 20/25 = 80.0% |

Per reviewer-expected-Alpha accuracy (see `item2_blind_holdout4_metrics.json` for full table incl. per-agent and per-system-Alpha views): A001 2/3, A101 4/6, A102 1/2, A103 9/14, A201 6/8, A301 7/17 (41.2%), A304 19/26 (73.1%), A501 1/3, A601 3/15 (20.0%), **NONE 96/106 (90.6%)**.

## 24. AI-family accuracy

Combined (A101+A102+A103): **14/22 = 63.6%**. Individually: A101 4/6 (66.7%), A102 1/2 (50.0%), A103 9/14 (64.3%). Non-AI-family (excluding NONE): 38/72 = 52.8%. Confusion within family: A103→A101 (2). Confusion into A201/A301/A304/A601: A101→A201 (1), A102→A301 (1), A103→A304 (1), A103→A601 (1). Confusion elsewhere: A101→NONE (1), A103→NONE (1). Descriptive only — no taxonomy/prompt tuning performed.

## 25. NONE analysis

- System NONE count: **122**
- Reviewer NONE count: **106**
- NONE/NONE correct: **96**
- System Alpha / reviewer NONE (system over-committed): **10**
- System NONE / reviewer Alpha (system over-abstained): **26**
- UNAVAILABLE count: **0**

The system's NONE recall against the reviewer's own NONE judgments is strong (96/106 = 90.6%), but the system says NONE meaningfully more often than the reviewer does (122 vs 106) — 26 rows where the reviewer found a real Alpha fit but the system returned NONE. This is a genuine, descriptive semantic-behavior finding (per task spec section 21's own instruction not to treat a high NONE rate as inherently a defect) — not remediated in this task.

## 26. Full confusion matrix (rows = system, columns = reviewer)

```
sys\rev   A001  A003  A101  A102  A103  A201  A301  A304  A501  A601  NONE
A001        2     0     0     0     0     0     0     1     0     0     1
A003        0     0     0     0     0     0     0     0     0     0     0
A101        0     0     4     0     2     0     0     1     0     0     0
A102        0     0     0     1     0     0     0     0     0     0     0
A103        0     0     0     0     9     0     0     0     0     0     0
A201        0     0     1     0     0     6     1     1     0     0     0
A301        0     0     0     1     0     1     7     0     0     0     3
A304        1     0     0     0     1     0     1    19     1     0     5
A501        0     0     0     0     0     0     0     0     1     0     0
A601        0     0     0     0     1     1     1     0     0     3     1
NONE        0     0     1     0     1     0     7     4     1    12    96
```
(Diagonal sum = 148 = official numerator, verified.)

## 27-29. Pure-LLM vs deterministic counterfactual

Computed offline from the already-persisted `deterministic_top_alpha` diagnostic — **zero additional Provider calls.**

- Pure-LLM accuracy vs reviewer: **74.0%** (148/200)
- Deterministic-only counterfactual accuracy vs reviewer: **53.5%** (107/200)
- Rows where Pure-LLM differs from deterministic: 77
- **LLM corrected deterministic: 51**
- **LLM worsened deterministic: 10**
- Both wrong differently: 16
- Equivalent: 0

Pure-LLM semantic authority still substantially outperforms the deterministic-only counterfactual on this genuinely unseen, broadly-sampled set (+20.5 points), even though the formal 75% acceptance bar was not met.

## 30. Comparison with Holdout #3 (explicitly non-paired, non-causal)

| | Result |
|---|---|
| H3 original (consumed, historical) | 105/152 = 69.08% |
| H3 Pure-LLM development re-evaluation (consumed, historical) | 119/152 = 78.29% |
| **H4 (this formal blind acceptance result)** | **148/200 = 74.00%** |

H3 and H4 use entirely different, non-overlapping samples with materially different sampling methodology (see section 9 above — H3's pool was pre-filtered by prior system confidence; H4's is not, and includes two tickers H3 treated as exhausted). **No causal or paired statistical claim is made from these raw percentages.** H4 is the formal blind acceptance result; H3 remains historical development context only.

## 31-39. Compliance confirmations

31. Production code changed during H4 = **NO**
32. Alpha prompt changed = **NO**
33. Taxonomy changed = **NO**
34. Threshold changed = **NO**
35. AI gate changed = **NO**
36. B1/B2/B4 changed = **NO**
37. H3 reused as evaluation input = **NO** (verified: 0 H4 `claim_id`/normalized-evidence values intersect H3's frozen set — H3 was used exclusively as an exclusion source)
38. Reviewer rerun after results = **NO**
39. Commit/push = **NO**

Post-freeze production drift check: HEAD unchanged, all 7 critical source SHA-256s byte-identical to the pre-sampling freeze manifest, H4 frozen CSV SHA-256 unchanged, reviewer artifact intact (200/200 unique `sample_id`). Focused zero-Provider regression (Alpha authority, production-boundary hardening, Exact/Architecture Replay, `llm_runtime`, B1/B2/B4-adjacent, run_audit): **583/583 passed.** Full repository suite last run in this exact byte-identical worktree (immediately preceding task): 3714 passed / 8 pre-existing-or-structural failed (all previously documented and unrelated to Alpha semantics) / 47 skipped — not re-run here per task spec section 29's explicit allowance.

---

## FINAL VERDICT

**ALPHA MAPPER ACCEPTANCE: FAIL**

Holdout #4 is now consumed development data. No production modification was made during this evaluation. Any future remediation requires a genuinely new blind Holdout #5 for formal re-acceptance.
