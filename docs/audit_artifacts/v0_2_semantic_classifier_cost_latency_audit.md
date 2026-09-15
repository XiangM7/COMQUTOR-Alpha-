# Semantic Classifier Cost / Latency Audit

**John Follow-Up Requirement B — Phase B1 (Analysis Only).** Active acceptance version: v0.2. Gold acceptance CLOSED. Product Demo Hardening CLOSED. John Requirement A (Invalidation-Condition Coverage) PASS. This phase produced **zero production semantic changes, zero Provider calls, zero fresh research runs** — measurement only, against persisted `outputs/runs/<run_id>/llm_semantic_calls.jsonl` logs and existing source code.

## Executive Summary

The task's headline historical measurements for the QQQ post-fix run (`f239a53f-...`) are **verified, not assumed**: total wall clock ≈3141s, `structured_adapter` ≈597s/19%, the combined `alpha_classifier + evidence_stance_classifier + structure_extractor` bucket ≈2325s/74%, 595 semantic-call records, and the exact task distribution (structured_adapter:8, alpha_classifier:550, evidence_stance_classifier:33, structure_extractor:4) all match direct measurement to within rounding.

The dominant cost source is **call volume in `alpha_classifier`** (550 calls, one per claim against the full 10-Alpha taxonomy in a single request — never one call per claim-Alpha pair). The dominant *latency* source is **`evidence_stance_classifier` running fully serially** (median 2671s span across the seven analyzed runs — roughly half of total semantic wall clock — at measured max-concurrency = 1, despite `alpha_classifier` already running at a proven concurrency = 4).

A real, safe, already-built cache-key design (`comqutor_alpha/llm_runtime/cache.py`) is **implemented but never wired to a real backend** — every session defaults to `NullLLMResponseCache`, explaining `cache_hit_count = 0` in all seven runs. This is the recommended, fully offline-validatable Phase B2 slice.

Deterministic Alpha-candidate pre-filtering was investigated and explicitly **not recommended** — the codebase already contains a documented "Pure-LLM Alpha semantic authority" invariant adopted specifically to avoid the QQQ-A001 class of defect.

## Pipeline Call Topology

| Task | Unit of work | Concurrency | Retry policy | Batch capability |
|---|---|---|---|---|
| `structured_adapter` | 1 agent-report batch (≤64 segments) | **None** (serial `for` loop; max observed = 1) | Shared default (1) | Yes, ≤64 segments/call |
| `alpha_classifier` | 1 claim vs. **full** 10-Alpha taxonomy | **ThreadPoolExecutor, default 4** (proven benchmark; max observed = 4) | Shared default (1) | **Deferred** — real negative test (40-item→22.9% coverage; 15-item→timeouts) |
| `evidence_stance_classifier` | Batch of ≤10 (claim, target-Alpha) items | **None** (serial `for` loop; max observed = 1) | **Boosted to 2** (evidence-driven, prior orphan-rate audit) | Yes, ≤10 items/call |
| `structure_extractor` | 1 claim | **None** (max observed = 1) | Shared default (1) | Not batched (low volume: 2-11 calls/run) |

All four share `Week2LLMGateway` (`comqutor_alpha/structure_engine/week2_llm.py`), `deepseek`/`deepseek-v4-flash`, `DEFAULT_TIMEOUT_SECONDS=20.0s` (evidence-derived from this codebase's own p50/p90 benchmark).

**`alpha_classifier` fan-out (Section 9 answer, verified from persisted payloads, not assumed):** one Provider call evaluates **one claim against all 10 Alphas simultaneously** — confirmed directly: every `alpha_classifier` input_payload carries the full `alpha_taxonomy` array (10 entries) alongside one `claim`/`evidence`/`direction`/`factors`, and returns one `{decision, selected_alpha_id}`. In the QQQ post-fix run, 550 calls covered **515 unique (claim, evidence) pairs** — i.e. essentially one call per distinct claim, plus 35 exact re-classifications of already-seen content (duplicate calls, not extra Alpha-pair fan-out).

## Per-Run Call Accounting

| Run | Records | Provider calls | Cache hits | `alpha_classifier` calls | `evidence_stance` calls | Semantic span (s) |
|---|---|---|---|---|---|---|
| NVDA | 549 | 591 | 0 | 499 | 32 | 4789.9 |
| QQQ historical | 485 | 518 | 0 | 445 | 25 | 3669.7 |
| MSFT | 542 | 585 | 0 | 499 | 30 | 4956.5 |
| SNDK | 683 | 730 | 0 | 630 | 42 | 6157.9 |
| TSM | 571 | 616 | 0 | 528 | 32 | 8564.4 |
| AMD | 580 | 626 | 0 | 533 | 33 | 3442.2 |
| **QQQ post-fix** | **595** | **617** | **0** | **550** | **33** | **2937.6** |

`provider_call_count = record_count + Σretry_count` in every run (validated exactly against each run's own `llm_semantic_manifest.json`). `cache_hit_count = 0` in all seven — see Cache Analysis.

Note: the six original acceptance runs show markedly *higher* fallback counts (39-47/run, ~90s max per-call latency ceiling) than QQQ post-fix (11 fallbacks, ~7s max `alpha_classifier` latency) — direct evidence a reliability/timeout improvement was already deployed between the six-run baseline and the QQQ post-fix run, independent of this audit.

## QQQ Post-Fix Detailed Timing

| Task | n | Sum latency (s) | Mean (ms) | p50 | p90 | p95 | Max | Task span (s) | Max concurrent |
|---|---|---|---|---|---|---|---|---|---|
| structured_adapter | 8 | 595.3 | 74412 | 84193 | 90028 | 90036 | 90036 | **596.0** | 1 |
| alpha_classifier | 550 | 1105.2 | 2009 | 1778 | 3067 | 3709 | 7027 | **706.5** | **4** |
| evidence_stance_classifier | 33 | 1604.2 | 48612 | 34206 | 135053 | 135056 | 135057 | **1604.4** | 1 |
| structure_extractor | 4 | 15.6 | 3905 | 3918 | 4852 | 4852 | 4852 | **15.8** | 1 |

**Stage attribution uses `task span` (wall clock), never `sum latency`** — summing per-call latencies double-counts overlapping (concurrent) time. `596.0 + 706.5 + 1604.4 + 15.8 = 2922.7s`, matching the claimed 597+2325=2922s almost exactly. Token usage (`input_tokens`/`output_tokens`/`total_tokens`) is **`null` on every record in every run** — no dollar cost is estimated; the only available cost proxy is `provider_call_count`, plus a character-length proxy: the repeated `alpha_taxonomy` block is **87.6% of every `alpha_classifier` request's character payload** (1526 of 1743 chars), ~839,300 redundant characters resent across 550 calls this run alone.

## Duplicate Request Analysis

**Within-run exact duplicates** (via the system's own `input_sha256`), `alpha_classifier` only — zero duplicates found in any other task, any run:

| Run | Total | Unique | Duplicate extra calls | Ratio |
|---|---|---|---|---|
| NVDA | 499 | 499 | 0 | 0.0% |
| QQQ historical | 445 | 443 | 2 | 0.45% |
| MSFT | 499 | 498 | 1 | 0.20% |
| SNDK | 630 | 623 | 7 | 1.11% |
| TSM | 528 | 526 | 2 | 0.38% |
| AMD | 533 | 533 | 0 | 0.0% |
| **QQQ post-fix** | **550** | **515** | **35** | **6.36%** |

Median 0.38%; QQQ post-fix is an outlier at 6.36%.

**Cross-run exact duplicates**: measured across all 3,684 `alpha_classifier` calls in the seven runs — only **2 calls (0.05%)** share an exact `input_sha256` with another run (both between QQQ historical and QQQ post-fix). **EXACT_DUPLICATE cross-run reuse is negligible in this dataset** — daily market data differs enough day-to-day that a cross-run cache, while architecturally free once wired, shows no measured benefit here. No `SEMANTICALLY_SIMILAR` (near-duplicate/paraphrase) request was treated as cacheable.

**Cross-agent duplication** (via the pipeline's own pre-existing `duplicate_group_id`): QQQ post-fix has 826 raw structured claims collapsing to 766 distinct text groups, of which **56 groups (7.3%) span more than one agent** — e.g. an identical sentence appearing verbatim in both `market_agent`'s report and `bull_researcher`'s debate history. This grouping is currently **informational only**: every one of the 826 claims still has `analysis_eligible=True`, so no existing gate excludes a cross-agent duplicate from separate downstream processing.

## Cache Analysis

- **Cache key** (`comqutor_alpha/llm_runtime/cache.py: build_llm_cache_key`) includes: `task`, `prompt_version`, `prompt_sha256`, `provider`, `model`, `input_schema_version`, `output_schema_version`, `input_sha256`, `taxonomy_version`, `semantic_call_schema_version` — every semantic authority capable of changing the answer. `run_id` is **deliberately excluded** ("intentionally excluded from the hashed key material") — the key is cross-run-safe by construction.
- Two implementations exist: `NullLLMResponseCache` (no-op, always misses) and `RedisLLMResponseCache` (fully implemented, strict-validating, injected-client adapter).
- `SemanticRuntimeSession.__init__` defaults `self.cache = cache or NullLLMResponseCache()`. A repo-wide search found **zero** production call sites that ever construct a `RedisLLMResponseCache` or inject any real cache client.
- **Classification: `IMPLEMENTED_BUT_NOT_USED`** — not `NOT_IMPLEMENTED`, not `MISKEYED`. This is why `cache_hit_count = 0` in every one of the seven analyzed runs.

**Safe cacheability**: all four tasks are **`SAFE_EXACT_CACHE`** under the *existing, unmodified* key design — the key already covers model/prompt/schema/taxonomy identity via `input_sha256` (which itself hashes the embedded taxonomy content) plus explicit version fields, so a future prompt or taxonomy change automatically produces a cache miss, never a silent stale reuse.

## Batching Analysis

- **`alpha_classifier`: `NOT_RECOMMENDED`.** Already tested with real controlled Provider calls (documented in `week2_llm.py`): 40-item batches → 22.9% coverage; 15-item batches → repeated >60s timeouts. This is closed, evidence-backed territory, not a fresh idea to re-litigate.
- **`structured_adapter` / `evidence_stance_classifier`: already batched** (64 / 10 items respectively) — `SAFE_CANDIDATE` only in the sense that the existing batch sizes are already in safe production use; no further size increase is evaluated or recommended without a dedicated controlled experiment, given `alpha_classifier`'s cautionary precedent on the same provider/model.
- **`structure_extractor`: `NOT_RECOMMENDED`** — call volume too low (2-11/run) to matter.

## Concurrency Analysis

Directly measured (timestamp sweep-line, not inferred) max concurrent calls per task, QQQ post-fix: `structured_adapter=1`, `alpha_classifier=4`, `evidence_stance_classifier=1`, `structure_extractor=1`. `alpha_classifier`'s `4` exactly matches its configured `DEFAULT_ALPHA_CLASSIFIER_CONCURRENCY`, itself chosen from a real 1-vs-4-vs-8 benchmark already on record.

**Why summed latency exceeds stage wall clock**: `alpha_classifier`'s sum-of-latencies (1105.2s) exceeds its task span (706.5s) by ~1.56× precisely because up to 4 calls overlap in time. The other three tasks show sum ≈ span (ratio ≈1.0) because they run with **zero** concurrency — a bare serial `for` loop, confirmed directly in `structured_output_adapter.py` and `evidence_stance_llm.py` source.

**Additional concurrency opportunity: HIGH**, concentrated in `evidence_stance_classifier` (median 2671s span — roughly half of total wall clock in every run) and `structured_adapter` (median 659s span). Both are independent-batch loops with no architectural concurrency mechanism at all — the same `ThreadPoolExecutor` pattern already proven safe for `alpha_classifier` is a direct, low-risk candidate to extend to both. **This is a latency-only lever — it changes zero provider calls.** Its magnitude cannot be proven without a live timing measurement, which is why it is recommended as the *second* (not first) B2 slice.

## Retry / Timeout / Fallback Analysis

Both the per-task retry policy and the shared timeout are **already evidence-tuned**, not naive defaults: `evidence_stance_classifier`'s retry count was deliberately raised to 2 after a prior dedicated audit found it responsible for 74.4% of all historical semantic orphans with only 2.7% recovery at 1 retry; the shared 20.0s timeout was derived directly from this task's own measured p50 (~1.87s)/p90 (~3.47s). QQQ post-fix: 22 retry-generated calls (structured_adapter:7, evidence_stance:12, structure_extractor:3, alpha_classifier:0), 11 fallbacks (structured_adapter:3, evidence_stance:4, structure_extractor:4, alpha_classifier:0). No timeout-specific error code was found in this run's records to isolate timeout-only wasted latency — reported honestly as not directly measurable rather than estimated. **Verdict: reasonable, already-tuned — no change recommended.**

## Fallback Analysis

`alpha_classifier`'s fallback is **conservative**: a persistently-failing claim becomes `unavailable`/unmatched, never a substituted guess. `evidence_stance_classifier`'s fallback **does** enter production semantics by design: it reuses the deterministic.v1 stance `alpha_mapper._attach_evidence_stance` already computed unconditionally *before* the LLM stage runs — the same mechanism already underlying the frozen 85.25% Polarity benchmark, not a new risk. `structured_adapter`'s fallback produces a lower-quality but structurally valid claim record (neutral direction, evidence=claim verbatim). No expansion of fallback usage is recommended.

## Safe Pre-Filter Analysis

A **claim-level** substantiveness gate already exists and is already active: `claim_quality.is_claim_eligible`'s ANALYTICAL/CONTEXT_ONLY/NON_SUBSTANTIVE classification excludes NON_SUBSTANTIVE claims from ever reaching `alpha_classifier` — directly evidenced by only 515 of ~766-767 deduplicated eligible claims being sent to the classifier in the QQQ post-fix run.

An **Alpha-candidate-level** pre-filter (excluding "obviously impossible" Alphas per claim before the LLM call) **does not exist and should not be added**. `alpha_mapper.py` contains an explicit "Pure-LLM Alpha semantic authority" invariant: deterministic keyword/factor/AI-gate scoring is computed for every claim but is **never** used to narrow which Alphas the LLM considers, and **never** substituted as the answer on LLM failure — by deliberate design, specifically to avoid the class of false-negative risk the QQQ-A001 defect exposed. **Classification: `NOT_SAFE`.**

## Semantic-Risk Constraints

- **QQQ-A001 lesson**: no recommendation in this audit touches candidate scope, request consolidation volume, or fallback substitution for `alpha_classifier` — the two recommended slices (exact memoization, added concurrency) change neither the claims classified nor the taxonomy presented, only call deduplication and execution scheduling.
- **Evidence-stance constraint**: frozen 52/61 (85.25%), 0 critical reversals — preserved; no prompt/model/fallback-logic change proposed.
- **Alpha-match constraint**: frozen 166/200 (83.00%), 34 failures with known TAXONOMY_OVERLAP=12/A601→NONE=6/high-confidence-wrong=15 — preserved; every recommendation reduces calls or reorders execution, never the classified claim set, so it cannot mechanically hide these figures.

## Optimization Opportunity Register

| ID | Description | Priority | Semantic risk | Recommended |
|---|---|---|---|---|
| OPP-A/B | Wire real `LLMResponseCache` backend (exact memoization, cross-run-capable) | **P0** | NONE | **yes** |
| OPP-C | Cross-agent exact-duplicate claim elimination | P1 | LOW-MEDIUM | needs further scoping |
| OPP-D1 | Batch `alpha_classifier` | NOT_RECOMMENDED | HIGH (already tested, failed) | no |
| OPP-D2 | Grow `structured_adapter`/`evidence_stance` batch size | P2 | MEDIUM | no (without a dedicated experiment) |
| OPP-E1/E2 | Add concurrency to `evidence_stance_classifier` + `structured_adapter` | **P1** | LOW | **yes, second slice** |
| OPP-F | Tune retries | NOT_RECOMMENDED | — | no (already tuned) |
| OPP-G | Tune timeouts | NOT_RECOMMENDED | — | no (already tuned) |
| OPP-H | Deterministic Alpha-candidate pre-filter | NOT_RECOMMENDED | HIGH | no |
| OPP-I | Reduce repeated taxonomy injection (provider context caching) | P2 | LOW-MEDIUM (experiment-gated) | needs experiment |
| OPP-J | Reuse deterministic score as/instead of LLM answer | NOT_RECOMMENDED | HIGH | no |

## Quantified Savings Scenarios

QQQ post-fix baseline: **617 provider calls, 2937.6s semantic-stage wall clock.**

| Scenario | Provider calls after | Call reduction | Wall clock after (est.) | Latency reduction (est.) | Semantic risk |
|---|---|---|---|---|---|
| **Conservative** (cache/memoization only) | 582 | 5.7% | ~2890-2900s | ~1-2% | NONE |
| **Moderate** (+ concurrency for evidence_stance) | 582 | 5.7% | ~2000-2150s | ~27-32% | LOW |
| **Aggressive** (+ structured_adapter concurrency + speculative context-caching + a not-recommended alpha_classifier re-batching experiment) | ~500-560 (speculative) | ~10-19% (speculative) | ~1400-1700s (speculative) | ~40-52% (speculative) | MEDIUM-HIGH |

All figures beyond Conservative are **estimates requiring live validation**, not billing facts.

## Recommended Phase B2 Slice

**Wire a real, persistent `LLMResponseCache` implementation into `SemanticRuntimeSession`**, using the existing, unmodified `build_llm_cache_key`/`LLMResponseCache` protocol — replacing the default `NullLLMResponseCache`. Chosen over the higher-upside concurrency change because its correctness *and* measured benefit can be proven **entirely offline**, with zero Provider calls, by replaying the seven already-persisted runs' call logs. Zero prompt/model/schema/taxonomy change. One dependency-injection point. Trivial rollback (revert to `NullLLMResponseCache`).

## B2 Validation Plan

- **Fresh Provider run genuinely necessary: NO** for this slice — correctness and savings are provable entirely from replaying persisted logs.
- Unit tests for the chosen cache backend against the existing `LLMResponseCache` Protocol.
- Cache-key regression test: confirm `build_llm_cache_key` (unmodified) still reproduces every `cache.cache_key` value already recorded in the seven persisted runs.
- Offline replay: feed each run's `llm_semantic_calls.jsonl` through the new cache in `call_sequence` order; confirm every within-run exact duplicate is served from cache with a byte-identical `validated_output`, and no non-duplicate ever false-hits.
- Semantic-output equivalence, Alpha-detection equivalence (against `v0_2_six_run_gold_conformance_audit.json`'s own derivation), conflict equivalence, and A001-remediation preservation — all checked via the same offline replay.
- 34+9 benchmark: **N/A** for this slice (separate holdout sample, different run_ids).
- Provider-call-count comparison: fully computable offline (cache-hit count vs. original call count).
- Latency comparison: not meaningfully measurable offline for this cost-primary slice — flagged as qualitative until observed live.
- Explicit new test: a `fallback_used=True` record must never be cached/replayed as if it were a genuine success.

---

**Gold changed: no. Production semantic files changed: 0. Test files changed: 0. Ephemeral tooling created (scripts/audit_tools/, not wired to production): 2 files. Provider calls: 0. TradingAgents calls: 0. Fresh ticker runs: 0. Alpha Memory: SHADOW, activation_modulation_applied=false, untouched. Commits: 0. Pushes: 0. Destructive git operations: 0.**

**JOHN REQUIREMENT B — PHASE B1 SEMANTIC CLASSIFIER COST/LATENCY FORENSIC AUDIT — COMPLETE.**
