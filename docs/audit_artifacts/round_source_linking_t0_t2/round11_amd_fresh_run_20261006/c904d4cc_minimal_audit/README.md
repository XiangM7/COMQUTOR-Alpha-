# AMD Fresh Run `c904d4cc-dc09-495c-aec5-b056979948e1` — Minimal Audit

Read-only audit. Zero new Provider/search calls. No production code, config,
threshold, taxonomy, or historical artifact was modified while building this.
This run is an **independent Fresh Run** — not a continuation of `91d7c420`,
not a re-evaluation of `1bad76a7`. Started 2026-10-06T17:39:31Z (raw capture)
/ 17:36:07Z (API accepted), completed 2026-10-06T19:26:XXZ (`status=completed`,
`structured_output_count=975`).

## Direct answers first

- **How many claims had a complete, valid verification, how many failed/never finished?**
  261 of 975 claims had a resolvable (`VALID`) source link and were eligible for
  content-support verification. Of those: **152 went through the real v2.1 LLM
  verification path** (`content_support_method=LLM_CONTENT_SUPPORT_VERIFIED`);
  65 fell back to `UNVERIFIED_OFFLINE_CONTENT_MATCH`, 42 to
  `ORIGINAL_AGENT_CITED_UNVERIFIED_SUPPORT`, 2 to the cheap deterministic
  `AUTOMATED_DATA_FACT_VERIFIED` check (no LLM needed). 714 claims never had a
  resolvable source link at all (`NOT_PROVIDED` → `content_support_status=
  NOT_APPLICABLE`) — the content-support stage itself never crashed or
  stalled this run; this is the queue it actually had to work with.

- **How many had their core judgment supported, how many only a partial fact?**
  Of the 261: **64 resolved to `SUPPORTS`**, **49 to `CONDITIONAL`** (core fact
  verified, but part of the claim's own broader assertion — materiality
  judged real, not a format technicality), 4 `BACKGROUND`, 1 `OPPOSES`, and
  143 `PENDING_REVIEW` (timeouts, truncation, or genuinely insufficient
  material — see the claim index for which).

- **How many had material gaps in the candidate set itself?** Not
  independently re-derived this round (would require re-tracing candidate
  selection per claim against the full source registry, which this round's
  time did not cover beyond the one worked example below) — flagged as a
  real remaining gap, not glossed over.

- **How many were simultaneously content-qualified, Alpha-matched, AND had a
  clear direction?** **Zero.** Not because none existed — because Alpha
  classification itself almost completely failed (see below): of the 975
  claims, only **2** ever received a real, completed Alpha-classifier
  response (both correctly returned "no canonical Alpha fits," and both
  were `claim_quality=context_only`, not even analytical claims). **113
  claims** had both a `VALID` source link and a resolved `SUPPORTS`/
  `CONDITIONAL` content-support status — genuine, real evidence — but
  **none of them ever got a real Alpha-classification attempt that
  completed.**

- **Why did these score or not score?** The 113 qualifying-evidence claims
  did not score because they never received `matched_alpha` at all — not
  because Activation or Conflict rejected them on the merits.

- **Primary reason for zero active/Conflict, and independent secondary
  reasons?**
  - **Primary (confirmed root cause, precise mechanism below)**: Alpha
    classification (`alpha_classifier`) dispatches with concurrency=4 by
    default against the SAME shared `Week2LLMGateway` instance that has
    real request/response auditing enabled. The gateway's audit mode
    enforces strictly sequential use (at most one pending attempt at a
    time) — a precondition this call site does not honor. Result: **973 of
    975** real alpha-classifier attempts failed instantly with
    `WEEK2_LLM_AUDIT_CONCURRENT_ATTEMPT`, caught by `_classify_alpha_with_
    llm`'s own blanket `except Exception: return _unavailable("provider_
    error")` (`comqutor_alpha/structure_engine/alpha_mapper.py`) — a path
    that never reaches `week2_llm.py`'s own error logger, which is exactly
    why `week2_llm_errors.jsonl` shows **zero** `alpha_classifier` entries
    despite ~973 real failures. Only 2 calls ever won the race for the
    gateway's single pending-attempt slot. This is the same defect class
    (concurrency vs. an audit-enabled gateway assuming sequential use) as
    the one already fixed for claim extraction — it was never fixed for
    this second call site.
  - **Direct, mechanical consequence chain** (each link independently
    confirmed from this run's own real, persisted artifacts, not inferred):
    `alpha_match_method=llm_unavailable` for 973/975 → `matched_alpha=null`
    for all 975 → `evidence_facts.json`: `unique_evidence_fact_count=0,
    groups=[]` (Evidence Fact grouping requires a committed Alpha match) →
    `alpha_activations.json`: every one of the 10 Alphas shows
    `activation_score=0.0`, with the real, persisted reason codes
    `cap_reason_codes=["NO_QUALIFYING_EVIDENCE"]` and
    `local_edge_exclusion_reasons=["NO_COMMITTED_ALPHA_MATCH"]` — the
    system's own diagnostic fields, not my inference → Conflict: the real
    API (`GET /api/research/.../conflicts`) shows **8 declared Alpha pairs
    were genuinely evaluated** (`admissibility` *was* actually invoked),
    all 8 rejected, every excluded claim tagged `reason_code=
    NON_COMMITTED_MATCH`.
  - **Secondary/independent causes**: none found. I specifically checked
    for an old SUPPORTS-only filter re-zeroing MODERATE/CONDITIONAL
    downstream, a human-review gate silently blocking automated results,
    and claim-quality/dedup/Exposure conditions as independent blockers —
    none of those apply here, because the pipeline never got far enough
    (no claim ever reached the point where those gates would matter) for
    98.7% of the eligible evidence. This is a single, dominant root cause,
    not several compounding ones.

## Worked examples (real, from this run's own persisted files)

**A fully-supported, orphaned claim**: `c904d4cc-...-market_agent:market_report:claim:19`
— *"200 SMA = 379.12"*. Real v2.1 verification: `SUPPORTS`, `support_basis=
DIRECT_FACT`. Real Alpha classification: `alpha_match_method=llm_unavailable`,
`fallback_reason=provider_error`, `matched_alpha=null`. This claim had
everything needed to be real, qualified evidence and never got the chance to
be scored.

**A correctly-downgraded analytical claim**: `c904d4cc-...-market_agent:market_report:claim:21`
— *"The 200 SMA has been rising steadily: from 318.29 on 2026-08-07 to 379.12
on 2026-10-06, a clear upward slope confirming a durable long-term uptrend."*
Real v2.1 verification: `supported_proposition="The 200 SMA is 379.12 on
2026-10-06"`, `unsupported_remainder="...rising steadily from 318.29...a
clear upward slope confirming a durable long-term uptrend"`, `materiality=
MATERIAL` → effective status `CONDITIONAL`. This is the v2.1 contract working
correctly: the source snapshot proves the current value, not the historical
trend the claim actually asserts. Not a bug — genuinely insufficient
candidate material for the *trend* assertion specifically (the news/market
sources captured do not include the 318.29-on-2026-08-07 data point as a
separately citable fact in this run's registry, as far as this round
checked).

## Frontend template inconsistency (real, confirmed, not from this run's data
being wrong)

`frontend/src/components/StructuralSnapshot.tsx`:
- `ActiveStructuresSection` (line 96-99) correctly computes `activeAlphas`
  from `graph.activation.alphas` and shows "No Alpha structure currently
  meets the active threshold." only when that list is genuinely empty —
  correct for this run (truly zero active alphas).
- `DominantStructureSection` (line 121-131), when `dominant_alphas.length
  === 0`, unconditionally renders "Several active forces are present, but
  none has reached dominant status." — **without checking whether any
  alpha is actually active at all.** For this run (zero active AND zero
  dominant), this text is factually wrong on its own terms. This is a real
  template defect, not a data problem: the component never receives or
  checks `activeAlphas.length` before choosing this specific string.
  **Minimal fix** (not implemented this round): gate this detail string on
  whether `graph.activation.alphas` has any active member, falling back to
  a genuinely-empty-safe message ("No active structure currently exists")
  when there are none.

## Real API / Export confirmation

- `GET /api/research/c904d4cc-.../conflicts` (real, read-only): confirms
  `admitted_count=0`, `rejected_count=8`, `declared_pair_count=8`, each
  rejected claim tagged `NON_COMMITTED_MATCH` — matches the file-based
  `conflicts.json` exactly.
- `GET /api/research/c904d4cc-.../export`: HTTP 200 (bundle generation
  succeeds for this completed run) — read-only check only, bundle was not
  further inspected byte-for-byte this round.
- `GET /api/research/c904d4cc-.../evidence-stances`: real, deterministic
  stance pairs exist (`claim_alpha_pair_count=4875`, `llm_stance_count=0` —
  this classifier runs deterministically in this deployment, not via LLM,
  so it was never affected by the alpha_classifier concurrency bug).

## What this round did NOT do (explicit remaining gaps)

1. Did not build a full claim-by-claim "was the candidate material itself
   sufficient" judgment for all 975 claims — see `claim_trace_index.json`
   for the raw, real per-claim data (content_support_llm_detail, source
   link, method); a full second-layer material-sufficiency read-through
   for every PENDING_REVIEW/CONDITIONAL claim was not completed this round.
2. Did not independently verify whether claims with `NOT_PROVIDED` source
   link status (714 of them) include any that should have found a relevant
   source via semantic (non-number-matching) discovery — this is exactly
   the Section 3/4 gap from the earlier v3 design discussion, still real
   and still open.
3. Did not byte-verify the Export ZIP's internal contents against the
   on-disk files (checked that the endpoint returns 200 only).
4. Minimal fix for the alpha_classifier concurrency defect and the frontend
   template defect are both described above but **not implemented** this
   round, per instruction.

## Files in this package

- `claim_trace_index.json` — all 975 claims, real fields only, built by
  `../build_c904d4cc_audit.py` (included alongside this directory) directly
  from this run's own persisted artifacts.
- `00_summary_counts.json` — the real counts quoted above.
- `file_manifest.json` — original vs. copied file sizes/SHA-256; copies
  confirmed byte-identical to the originals.
- `run_data_copies/` — read-only copies of this run's own real artifacts
  (request/response audit headers already redact `authorization`; spot-
  checked for the real DeepSeek API key string, not present in any copy).

Stopped here per instruction: no further paid calls, no re-scoring, no
claim that T1 or John's overall acceptance has passed or failed.
