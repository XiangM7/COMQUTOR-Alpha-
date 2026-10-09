# v0.2 Day 3 Review Resolution

Authority: `docs/audit_artifacts/v0_2_john_frozen_gold_baseline.yaml` — **unchanged**. Full detail in the companion `v0_2_day3_review_resolution.json`.

## MSFT-A102-DIRECT-INFERENCE-TRIGGER (Objective B)

**Reproducible: YES.** Full trace, frozen evidence → final detection:

| Stage | Finding |
|---|---|
| Frozen evidence | 3 claims explicitly name "inference demand" tied to named MSFT products — correct, no issue |
| Trigger adjudication | `trigger_state=PRESENT`, `evidence_strength=STRONG` — correct, no issue |
| **Direction inference** | **FIRST INCORRECT STAGE.** `infer_direction()` resolved `unknown` for 2 of the 4 inference-mentioning claims (a "toll booth on the highway of frontier model inference" competitive-moat metaphor and its direct rebuttal) — neither `POSITIVE_WORDS` nor `NEGATIVE_WORDS` covered this idiom |
| Claim quality gate | Correctly downstream: given `direction=unknown`, `classify_claim_quality()` correctly labeled both claims `context_only` |
| Alpha mapping | Correct: all 4 inference-mentioning claims were matched to A102 with real, nonzero scores — the Alpha Mapper is not at fault |
| Evidence-fact grouping | Downstream consequence: `context_only` claims never populate a supporting `alpha_stances` entry (by design) — the 2 affected claims never appear in any evidence-fact group at all |
| Activation / final detection | Consequence: A102's evidence base shrank to 1 group (2 of 4 matched claims), staying at `candidate` |

**Fix applied: YES.** One line, in `comqutor_alpha/structure_engine/structured_output_adapter.py`:

```python
POSITIVE_WORDS = (
    ...
    "recovering",
    "toll booth",   # + Day 3 addition
)
```

`POSITIVE_WORDS`/`NEGATIVE_WORDS` are used nowhere else in the codebase (verified by repository-wide grep) — this is an isolated, low-blast-radius lexicon feeding only the coarse `infer_direction()` fallback. "Toll booth" is a common, cross-ticker pricing-power/competitive-moat metaphor, not an MSFT-specific term. No Alpha ID added, no Gold rule touched, no evidence adjudication changed, MSFT not named anywhere in the change.

### Before / After

| | Claim 1 | Claim 2 |
|---|---|---|
| Input | "...MSFT is the toll booth on the highway of frontier model inference." | "Bull: '...toll booth...' Bear: 'Toll booths work when there's only one highway.'" |
| Pre-fix | direction=`unknown`, quality=`context_only`, stance=`neutral_background` (never counted) | same |
| Post-fix | direction=`positive`, quality=`analytical`, stance=`supports_alpha` | direction=`positive`, quality=`analytical`, stance=`supports_alpha` |

**Scope of verification:** confirmed end-to-end for direction → claim_quality → evidence_stance, using the real, unmodified production functions and the exact persisted claim text. **Not** independently confirmed: whether A102's full activation score actually crosses into `active` once these groups are folded through the complete Alpha Mapper / Evidence Fact / Activation Scorer pipeline — that requires a full Architecture Replay run, planned for Day 4, not claimed as complete today.

**Focused regression:** `pytest tests/test_structured_output_adapter.py tests/test_evidence_stance_classifier.py tests/test_week2_semantics.py tests/test_claim_quality.py tests/test_alpha_mapper.py tests/test_ai_alpha_mapper_discrimination.py -q` → **319 passed, 0 failed**. No Provider calls, no market-data retrieval, no TradingAgents research — development verification only, not formal validation, not a Fresh Run.

---

## REVIEW_REQUIRED Rows (Objective C)

### MSFT-A102-INDIRECT-INFERENCE-SUPPORT

- **Evidence condition:** generic enterprise-AI adoption *without* inference-mechanism language.
- **Evidence sufficiency:** not resolvable — every Copilot/adoption claim in this corpus already explicitly invokes "inference demand" (the sibling DIRECT rule's territory); no clean "indirect-only" pool exists to evaluate.
- **System output:** A102 = candidate (same claims as the DIRECT rule).
- **Recommendation: `REVIEW_REQUIRED`** (unchanged). Non-blocking, informational (`should_detect_if_supported`); forcing any other status would not be justified by the evidence.

### MSFT-CAPEX-BURDEN-CONDITIONAL

- **Evidence condition:** capex burden connected to a named downside-transmission channel.
- **Evidence sufficiency:** STRONG and SUFFICIENT — both sub-conditions (`capex_present`, `capex_downside_linkage_present`) confirmed PRESENT by pre-existing adjudication (`v0_2_acceptance_adjudication.json` Case C); independently reconfirmed today: A304 has 39 evidence-fact groups in this run (13 `supports_alpha`), its richest evidence base of any alpha — this is not an evidence-loss situation.
- **System output:** A304 = candidate (score 43.36), not detected.
- **Recommendation: `REVIEW_REQUIRED`** (unchanged) — matches the pre-existing Case C adjudication exactly. The shortfall traces to the activation formula's `local_structure_support` component (0.0 — no qualifying local graph edges for A304 in this run), not to missing evidence. `conditional_only` semantics mean a miss is informational, never a failure. Flagged as worth future investigation (is edge-qualification too strict for this claim network?) but not resolved today.

### QQQ-FROZEN-ALLOWED-MAIN-CONFLICTS

Current main conflict: **A301__A304** — not in John's frozen baseline (A001__A501, A003__A501, A304__A601).

| Question | Answer |
|---|---|
| A. Does A301 evidence represent ETF/component-level revenue expansion sufficiently? | **Yes, partially diluted.** 11/17 evidence groups support; several cite concrete, named, cross-company evidence (Apple ASP expansion, Oracle's $664B backlog, Micron guidance, Dell/HPE moves) explicitly framed at the ETF level. Some other supporting groups are vaguer debate-process assertions. |
| B. Is A301 based on only one constituent company's revenue? | **No.** At least 6 distinct named entities appear (Apple, Skyworks, Oracle, Dell, HPE, Micron) spanning hardware and cloud-infrastructure names. |
| C. Does A304 have valid QQQ-relevant supporting evidence? | **Yes — the strongest evidence base of any alpha in this run:** 43/54 groups support, from 10 distinct agents. |
| D. Why did the system select A301__A304 as main conflict? | It is the run's two most heavily evidenced, genuinely opposing alphas, and a canonical taxonomy pair (confirmed Day 1). A mechanically well-supported outcome, not an anomaly. |
| E. Does the evidence justify proposing expansion of QQQ's frozen conflict rule? | **Yes, an evidence-supported case exists.** Output: **`RULE_CHANGE_RECOMMENDATION`** — for later human/product-owner decision only. |

**QQQ conflict status: `REVIEW_REQUIRED`** (unchanged). **Frozen rule NOT modified**, regardless of the answer to E, per explicit instruction.
