# v0.1.3 TSM Semantic Recorder + Run-to-Run Variance Audit

Offline / read-only audit. **Provider calls: 0. TradingAgents calls: 0. Ticker runs executed: 0.** HEAD unchanged (`9f228723fad5406c72e62beca67ec70ea0fdb004`). No commit. No push. No code changed. No test changed. Gold and Gold Validity untouched. Old TSM authoritative run/ledger untouched. New TSM run not promoted.

## Executive Summary

```
Semantic recorder failure events (new TSM run)   247
Canonical semantic losses caused by those events 0   (architecturally proven impossible)
Recorder role classification                     B. AUDIT_TRACE_ONLY

TSM Gold hit rate -- old run                      5/6 = 83.33%
TSM Gold hit rate -- new run                      4/6 = 66.67%
Gold-set Jaccard (old vs new)                     0.5
Alpha-level flips                                 3  (A103 HIT->MISS, A201 HIT->MISS, A301 MISS->HIT)

A103 regression root cause     V1 RESEARCH_CONTENT_VARIANCE (raw topic density 54->30 mentions)
A201 regression root cause     V7 STRUCTURE_EXTRACTION_VARIANCE (0 edges vs 2, despite improved evidence)

Single-run TSM reproducibility LOW
Promotion decision             DO_NOT_PROMOTE
Recommended next step          NEXT_E -- design a multi-run reproducibility metric

Code changes: 0   Test changes: 0   Provider calls: 0   Ticker runs: 0
Gold v1 / Gold Validity SHA-256: unchanged
```

## John — TSM Reproducibility Audit

```
Metric                     Old TSM (dfc7ceb3)      New TSM (0aeea938)
Gold Detected               A101,A103,A201,          A101,A301,A304,
                             A304,A601                A601
Gold Hit Rate                5/6 = 83.33%             4/6 = 66.67%
A103                         active / 68.5499 HIT     candidate / 25.76 MISS
A201                         active / 64.5041 HIT     candidate / 44.44 MISS
A301                         candidate / 44.77 MISS   dominant / 75.96 HIT
Recorder failures            0 (not measured)         247 (AUDIT_TRACE_ONLY)
Canonical semantic loss      0                        0
Gold-set Jaccard                        0.5
Alpha-level flip count                    3
Single-run reproducibility               LOW
Promotion decision                DO_NOT_PROMOTE
```

## 1-2. Scope and Safety Confirmation

Offline replay only, reading already-persisted artifacts from both TSM runs (`dfc7ceb3-3584-4514-bd84-6c371aab3e95` and `0aeea938-97a8-49c8-97e1-409f6dadad30`) plus direct source inspection of the semantic recorder/session/task-caller code. No Provider call, no TradingAgents call, no ticker run, no code or test modification, no commit, no push occurred in this task.

## 3. Semantic Recorder Architecture Trace

`comqutor_alpha/llm_runtime/recorder.py`'s `SemanticCallRecorder.append()` is an append-only, integrity-checked JSONL writer for `llm_semantic_calls.jsonl`, raising `RecorderIntegrityError` for closed/mismatched/duplicate/non-monotonic/corrupted conditions. Its sole caller, `SemanticRuntimeSession.finalize_call()` (`llm_runtime/session.py:380-470`), wraps the append in a try/except: on any exception it calls `self._mark_degraded("SEMANTIC_RECORDER_APPEND_FAILED", exc, incomplete=True)` and returns `False` — **the exception never propagates to the caller.**

That caller, `Week2LLMGateway.finalize_semantic_invocation()` (`structure_engine/week2_llm.py:1090-1176`), is itself wrapped in a second blanket try/except and returns `None`. Its docstring states explicitly: "Persist/cache **after** the task-specific caller accepts or rejects" — proving this call is a post-hoc audit step, not part of the semantic decision.

Grepping every call site of `finalize_semantic_invocation()` confirms the identical pattern in all three semantic-critical task callers:

- `alpha_mapper.py:451-462` and `:585-589` — `response = invocation.validated_output` is already fixed; the finalize call's return value is discarded.
- `structure_extractor.py:434-441` — `return invocation.validated_output` immediately follows a discarded finalize call.
- `evidence_stance_llm.py:328-334` — `returned_items = invocation.validated_output or []` follows a discarded finalize call.

**Conclusion: the recorder's role is B. AUDIT_TRACE_ONLY.** A `RecorderIntegrityError` is caught twice (inside `finalize_call()`, then again inside `finalize_semantic_invocation()`) before it could ever reach code that reads `invocation.validated_output` — and that value was already computed and fixed before the recorder was ever invoked. Failure to append can never cause loss of canonical semantic state (`matched_alpha`, B1 stance, structure edges).

## 4-5. Raw Events vs. Final Loss

- Recorder failure events (new run): **247**, all `SEMANTIC_RECORDER_APPEND_FAILED` / `RecorderIntegrityError`, logged via `"semantic runtime degraded (run_id=%s, reason_code=%s, exc_type=%s)"` in `/tmp/comqutor_live_start.log` (289 lines total).
- **Unique affected claims: UNKNOWN** — the log format carries no `claim_id`, task name, or per-event timestamp, so a per-component/per-claim breakdown is genuinely not reconstructable from persisted artifacts. This traceability gap is reported honestly rather than approximated.
- **Final canonical-semantic losses: 0** (architecturally proven in Section 3).
- **Final audit-trail losses: 247** (that many entries are genuinely missing from `llm_semantic_calls.jsonl`, which nonetheless grew healthily to 616 lines ending in a valid final record).
- **Recovered recorder writes: N/A** — this architecture has no "retry of the same recorder write"; each `finalize_call` is a one-shot append tied to a specific already-completed provider call, so there is no notion of a failed write being later recovered under the same identity.

## 6. SR0-SR8 Semantic Consequence Classification

All 247 events classify as **SR1 AUDIT_TRACE_LOSS_ONLY** (equivalently SR0). Zero events classify as SR2 (Alpha-mapping trace loss), SR3 (stance trace loss), SR4 (structure trace loss), SR5 (activation input loss), SR6 (conflict input loss), or SR7 (canonical state loss) — those classes would require the semantic decision to depend on a successful append, which Section 3 proves it does not.

## 7. Provider Health Diagnostic Gap

Classified **DIAGNOSTIC_GAP_AUDITABILITY**, not `DIAGNOSTIC_GAP_SEMANTIC_INTEGRITY` (no integrity risk exists) and not `DIAGNOSTIC_GAP_NONE` (247 real, currently-invisible degradation events exist). Recorder failures should **not** become Provider failure events (different failure class — local I/O/concurrency integrity, not Provider network/LLM execution) and should **not** become final-orphan sources or `benchmark_review_required` triggers. They **could** reasonably justify a separate recorder-health metric family (`recorder_append_failure_count`, `recorder_integrity_status`) alongside, not merged into, Provider Health.

## 8-9. A103 Full Trace and Variance Classification

| | Old | New |
|---|---:|---:|
| Score / Level | 68.5499 / active (HIT) | 25.7618 / candidate (MISS) |
| Unique evidence | 13 | 1 |
| Supporting agents | 3 (fundamental, news, sentiment) | 1 (news only) |
| Ticker-specific evidence | 3 | 0 |
| Local edges | 0 | 0 |
| Cap reasons | NO_LOCAL_STRUCTURE_SUPPORT | INSUFFICIENT_UNIQUE_EVIDENCE, NO_TICKER_SPECIFIC_EVIDENCE, INSUFFICIENT_AGENT_INDEPENDENCE, NO_LOCAL_STRUCTURE_SUPPORT |
| In `impacted_alpha_ids`? | No ([A301,A601]) | No ([A101]) |

Raw AI-infrastructure keyword mentions (data center/capex/infrastructure/server/cooling/networking/power demand) dropped **54 → 30** (−44%) in the underlying research corpus — but extracted qualifying facts collapsed **13 → 1** (−92%), a disproportionately larger drop than raw content alone explains.

**Primary variance class: V1 RESEARCH_CONTENT_VARIANCE.** **Secondary: V3 CLAIM_EXTRACTION_VARIANCE** (the compounding 92%-vs-44% gap is noted but not fully resolved in this task). Not Provider-caused, not recorder-caused.

## 10-11. A201 Full Trace and Variance Classification

| | Old | New |
|---|---:|---:|
| Score / Level | 64.5041 / active (HIT) | 44.4406 / candidate (MISS) |
| Unique evidence | 30 | 25 |
| Supporting agents | 3 | **5 (improved)** |
| Ticker-specific evidence | 6 | **9 (improved)** |
| Local edges | **2** | **0** |
| In `impacted_alpha_ids`? | No ([A301,A601]) | No ([A101]) |

Old run's 2 structure edges: `ai_capex → semiconductor_cycle` (causal — "...directly benefits TSM as the world's leading advanced-node foundry") and `ai_capex → tsm_revenue_growth` (supportive — "Massive capacity expansion (Arizona $265B, Europe) secures long-term revenue runway"). The new run has **zero** incident edges for A201 despite near-identical raw topical keyword volume (40 vs 41 mentions) and *improved* evidence diversity/quality.

**Primary variance class: V7 STRUCTURE_EXTRACTION_VARIANCE** — the specific two-factor causal-link sentence pattern that produced edges in the old run's phrasing did not appear in this run's differently-worded content, despite the same underlying facts plausibly being present. **Secondary: V1 RESEARCH_CONTENT_VARIANCE.** Not Provider-caused, not recorder-caused. A distinctly different failure mode than A103 (structural, not volumetric).

## 12-13. Research Corpus and Source Overlap

Total claims: old=766 (primary 351, secondary 415); new=817 (primary 359, secondary 458) — comparable overall volume despite the topic-specific divergence above.

Cited outlets: old=9 (Barron's, CNBC, GuruFocus, IBD, Motley Fool, Reuters, StockTwits, Yahoo Finance, Zacks); new=7 (Barclays, IBD, Motley Fool, StockTwits, TheStreet, Yahoo Finance, Zacks); 5 shared. Runs were 3 calendar days apart (2026-09-06 vs 2026-09-09) — outlet rotation is expected for independent live news-driven research and was not investigated further (no web search performed, per constraint).

## 14-16. Semantic Decision Stability and A301 Control Case

The A301 positive control (already traced in the prior fresh-provider-validation task): old `fundamentals_report:claim:42` vs new `fundamentals_report:claim:29`, different claim IDs but the same economic thesis and an **identical deterministic score of 0.7596**. Old: `match_status=unavailable` (provider_timeout). New: `match_status=matched`, `matched_alpha=A301`.

Whether claim:29's own recorder append succeeded is untraceable at the per-claim level (Section 4), but this is **irrelevant**: Section 3's architectural proof means even a recorder failure on that specific call could not have altered the already-fixed, independently-confirmed `matched_alpha=A301` outcome. A103/A201 do not have an equivalent single-claim pair to trace, since their divergence is a broad volume/structure shift, not a one-to-one claim substitution.

## 17. A101/A304/A601 Stability Controls

| Alpha | Old | New | Note |
|---|---:|---:|---|
| A101 | 52.9006 | 70.0 | both HIT; new run stronger (18 unique facts) |
| A304 | 57.9945 | 75.8263 | both HIT; new run stronger (local_structure_support raw 25.0) |
| A601 | 54.1843 | 55.4809 | both HIT; narrowest margin of the three |

These three draw on broad, generically-worded market/sentiment/narrative themes present in some form in nearly all daily news flow, giving them redundant multi-agent evidence resistant to any single day's specific phrasing — unlike A103/A201, which require specific factual/structural content sensitive to which particular items surfaced that day.

## 18. Margin/Robustness Table

Diagnostic-only bins (not production thresholds): ROBUST = |score−50| ≥ 15, else MARGIN.

| Alpha | Old Score | Old Class | New Score | New Class |
|---|---:|---|---:|---|
| A101 | 52.9006 | MARGIN_HIT | 70.0 | ROBUST_HIT |
| A103 | 68.5499 | ROBUST_HIT | 25.7618 | ROBUST_MISS |
| A201 | 64.5041 | MARGIN_HIT | 44.4406 | MARGIN_MISS |
| A301 | 44.7724 | MARGIN_MISS | 75.9582 | ROBUST_HIT |
| A304 | 57.9945 | MARGIN_HIT | 75.8263 | ROBUST_HIT |
| A601 | 54.1843 | MARGIN_HIT | 55.4809 | MARGIN_HIT |

5 of 6 old-run Gold alphas were MARGIN-classified — only A103 was robust. TSM's old "hit" set was itself fragile, which helps explain why a second independent run flipped 3 of 6 outcomes.

## 19-20. Jaccard and Flip Counts

Gold-set Jaccard = |{A101,A304,A601}| / |{A101,A103,A201,A301,A304,A601}| = **0.5**. All-10-alpha detected-set Jaccard is identical (0.5), since no non-Gold alpha (A001/A003/A102/A501) changed detected status. Flip count = **3** (A103 HIT→MISS, A201 HIT→MISS, A301 MISS→HIT). Gold hit count: old 5/6=83.33%, new 4/6=66.67%.

## 21. Benchmark Representativeness

Both runs: artifact completeness 9/9, Data Sanity ok, full semantic traceability confirmed. Old run carries one real, since-explained Provider-caused miss (A301). New run carries 247 non-semantic-impacting recorder degradation events and a non-Provider-caused A103/A201 instability pattern. **Neither run is auto-preferred** for scoring higher/lower — both classify as **BENCHMARK_USABLE_WITH_REVIEW**.

## 22. Promotion Decision

**DO_NOT_PROMOTE.** Not because A301 recovered (a real positive) or because Gold score dropped (a real negative) — but because this audit found TSM's per-run Gold outcome has **low reproducibility** (Jaccard 0.5, 3/6 flips, 5/6 old-run hits themselves borderline) from only n=2 runs. Promoting either run as "the" authoritative TSM result would overstate confidence in a measurement now shown to be materially unstable. The correct action is designing a multi-run stability metric before deciding which run(s) represent TSM's Gold-evaluable state.

## 23. Multi-Run Benchmark Design Options

| Option | Summary |
|---|---|
| A. Single frozen run | Simplest, matches current methodology; proven unstable for TSM by this audit |
| B. 2-run majority | Cheap; a tie has no resolution rule |
| C. 3-run majority | Resolves ties, more robust; 3x Provider cost |
| D. Mean Alpha score across runs | More information; requires redefining the binary detected-state contract |
| E. Detection frequency per Alpha | Directly measures what this audit found missing; natural extension of the existing contract |
| F. Stability-weighted metric | Most sophisticated; highest complexity, overkill for n=2 |
| G. Separate accuracy + reproducibility metrics | Avoids conflating "is Gold correct" with "is the system stable" |

**Recommended smallest defensible approach: E + G** — report detection frequency per Alpha (e.g. "TSM A301: detected in 1/2 runs so far") alongside the existing single-run Gold Hit percentage, without committing to a majority-vote promotion rule until more runs exist. This directly answers this audit's three motivating questions without inventing an arbitrary threshold or redefining the detected-state contract. C and D are valid future steps, not immediate ones.

## 24. Gold Validity Independence

A103/A201's instability is **not** evidence that Gold's expectation of them for TSM is wrong. Gold validity remains governed exclusively by the frozen Gold Validity Audit (SHA256 unchanged). This is a system-reproducibility question, kept on a separate axis from benchmark-quality, consistent with the QQQ/SNDK audit's precedent.

## 25. Semantic Recorder Design Recommendation

**RECORDER_NEXT_B — add recorder-health diagnostics only.** `NEXT_A` (no action) undersells a real, quantifiable, currently-invisible signal. `NEXT_C`/`NEXT_D` (reliability or P0-level fixes) are not justified — Section 3 proves no integrity risk exists. The fine-grained per-claim traceability gap (Section 4) is exactly what `NEXT_B`'s proposed metrics would remedy going forward.

## 26. Next Engineering Direction

**NEXT_E — design a multi-run benchmark/reproducibility metric.** This audit's central finding is TSM's low single-run reproducibility (3/6 alpha flips across two valid runs) — a measurement-validity question more fundamental than proceeding to new extractor design (`NEXT_D`) or a third TSM replicate (`NEXT_C`, unauthorized here and better preceded by a design decision on how extra runs would be used). `NEXT_B` (recorder diagnostics, recommended above) can proceed in parallel without conflict. This choice is not based on which direction would raise Alpha Hit — neither affects the current official 61.0317% score.

## 32. Final Validation

Gold v1 SHA256 `99b1cd0247637054de360c3b5c0c00c7d8052152f3db1d29045eae1850bd8e9a` — unchanged. Gold Validity SHA256 `3643ea45168c029d7c2a2ceb6d1d61cac3d5de80770d3dccb1f57d005c0c1cdf` — unchanged. Old TSM authoritative run/ledger — unchanged. Official six-ticker Alpha Hit (61.0317%) — unchanged. P0/P1 and Provider Health implementation — untouched. Zero production files modified. Zero test files modified. Zero Provider/TradingAgents calls. Zero new ticker runs. Zero commits, pushes, or destructive git operations.

---

**Commits: 0. Pushes: 0. Destructive git operations: 0. Provider calls: 0. TradingAgents calls: 0. Ticker runs: 0.**
