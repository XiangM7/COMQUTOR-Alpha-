# H4 Reviewer-v2 Development Re-Evaluation

> **DEVELOPMENT RE-EVALUATION — NOT A NEW BLIND HOLDOUT.** Blind Holdout #4 is already consumed. Its formal verdict (148/200 = 74.00%, FAIL) is final and is **not** changed by anything in this document. This is a re-review of the same frozen H4 rows under a corrected reviewer protocol, run for development purposes only.

| Metric | Result | Threshold | Development Status |
|---|---|---|---|
| Alpha Match Accuracy (reviewer-v2) | 154/200 = **77.00%** | ≥ 75.00% | **PASS** |
| B1 Polarity Accuracy (reviewer-v2 target, N=47) | 39/47 = **82.98%** | ≥ 80.00% | **PASS** |

### Original formal results (unchanged, for reference)

| Metric | Result | Threshold | Formal Status |
|---|---|---|---|
| H4 Alpha Match (original reviewer) | 148/200 = 74.00% | ≥ 75.00% | **FAIL** |
| B1 Polarity (Blind Holdout #2) | 123/141 = 87.23% | ≥ 80.00% | **PASS** |

**Reviewer-v2 Alpha delta vs original H4: +3.00 percentage points** (74.00% → 77.00%).

---

## Reviewer-v2 Semantic Correction Summary

| Item | Original reviewer | Reviewer-v2 |
|---|---|---|
| NONE count | 106/200 (53.00%) | 153/200 (76.50%) |
| A601 (Narrative Momentum) count | 15 | 2 |
| Labels changed vs original | — | 55/200 (27.50%) |
| Labels unchanged vs original | — | 145/200 (72.50%) |
| Original Alpha → reviewer-v2 NONE | — | 48 |
| Original NONE → reviewer-v2 Alpha | — | 1 |
| Original Alpha → different reviewer-v2 Alpha | — | 6 |

Label changes by **original** confidence band: high 1/111 (0.9%), medium 37/71 (52.1%), low 17/18 (94.4%). The correction overwhelmingly hit the original reviewer's own low- and medium-confidence calls, essentially untouched its high-confidence calls (only 1 of 111) — consistent with a targeted fix of the diagnosed forced-choice bias rather than a wholesale relabeling.

---

## 1–40. Full development report

1. **Branch**: `comqutor-structure-layer`. **HEAD**: `8ecf6bfdf7fd8203e223b220be8ca244da92d1f1` — unchanged from session start through completion of this task.
2. **Worktree starting state**: dirty, as expected/documented (multiple prior authorized segments' uncommitted work). Preserved as-is; nothing reset, restored, checked out, cleaned, or stashed.
3. **H4 frozen CSV SHA-256 verification**: `docs/audit_artifacts/item2_blind_holdout4_frozen.csv` = `20100402208b97ef0b0a2cbd6010e1bd6132031283acc84fda53437df3e17639` — matches expected exactly. 200 rows, no edits.
4. **Production code changed this segment**: **NO**. Zero edits to `alpha_mapper.py`, `week2_llm.py`, `evidence_stance.py`, `evidence_stance_llm.py`, taxonomy, AI gate, thresholds, or any other production path.
5. **Reviewer-v2 exact semantic rules**: two-stage material-fit protocol. Stage 1 (existence gate) — does the Claim/Evidence materially express/support/oppose/instantiate/reason about at least one canonical Alpha's own causal/economic mechanism? Shared vocabulary, generic bullish/bearish language, a technical indicator alone, a stock-specific recommendation alone, a catalyst alone, and a price move alone are all explicitly insufficient. Core thesis has semantic priority over trigger/confirmation signals and keywords. Stage 2 (single-best, only entered if Stage 1 = true) — compare all materially-fitting Alphas and select the single best; NONE is never used merely because the choice between two-or-more valid Alphas is close.
6. **Reviewer-v2 prompt SHA-256**: `cccccc542f42bcde8f2d245344978d2d70c5c9933dc594a6f0d8f37883592751`, frozen in `item2_h4_reviewer_v2_dev_freeze.json` before any reviewer-v2 Provider call; not edited afterward.
7. **Provider / model**: Anthropic, `claude-sonnet-4-6`, temperature 0, batch size 10, all three phases.
8. **Reviewer-v2 Alpha calls**: 20 logical calls / 20 provider attempts / 0 malformed batches / 0 retries. All 200 rows reviewed, none skipped.
9. **Original reviewer Alpha distribution**: NONE 106, A304 26, A601 15, A301 17, A103 14, A201 8, A101 (part of AI family, see confusion matrix), A501 3, plus remainder. (Full distribution in `item2_h4_reviewer_v2_dev_metrics.json → reviewer_label_drift.original_reviewer_alpha_distribution`.)
10. **Reviewer-v2 Alpha distribution**: NONE 153, A304 17, A103 9, A301 7, A101 4, A201 4, A102 2, A601 2, A501 1, A001 1.
11. **Total Alpha labels changed**: 55/200 (27.50%); unchanged 145/200 (72.50%).
12. **Old Alpha → NONE**: 48. **Old NONE → Alpha**: 1. **Old Alpha → different Alpha**: 6.
13. **ORIGINAL H4 ALPHA (unchanged, historical)**: 148/200 = 74.00%, **FORMAL VERDICT: FAIL** (threshold ≥75.00%).
14. **REVIEWER-V2 DEVELOPMENT ALPHA**: 154/200 = **77.00%**, threshold ≥75.00%, **DEVELOPMENT PASS**.
15. **Delta vs original H4**: **+3.00 percentage points**.
16. **Original system-NONE / reviewer-Alpha mismatch count**: 26 (the previously-flagged "apparent over-abstention" bucket).
17. **Reviewer-v2 system-NONE / reviewer-v2-Alpha mismatch count**: **4** — an 84.6% reduction (22 of the original 26 cases). This is the direct answer to the task's Question 4: the system's apparent over-abstention was overwhelmingly a reviewer-side forced-choice-bias artifact, not a real system defect. Only 4 genuine candidate-under-triggering cases remain.
18. **Original system-Alpha / reviewer-NONE mismatch count**: 10.
19. **Reviewer-v2 system-Alpha / reviewer-v2-NONE mismatch count**: **35** — this rose substantially. Under the corrected, stricter ground truth, 35 of the system's 78 affirmative "select" decisions (44.9%) disagree with reviewer-v2's NONE call. This is the largest single error bucket in the corrected metric and is reported prominently, not minimized: it indicates the production Alpha Mapper's own tendency to over-select an Alpha is a materially larger source of Alpha-match error than under-triggering, once forced-choice bias is removed from the ground truth. (36/78 of system selections exactly match reviewer-v2; 7/78 match a *different* real Alpha; 35/78 match NONE.)
20. **Original A601 performance**: 15 rows labeled A601 by the original reviewer.
21. **Reviewer-v2 A601 performance**: 2 rows labeled A601 (13 of the original 15 moved elsewhere, predominantly to NONE). Accuracy on the 2 reviewer-v2 A601 rows vs system: 1/2 = 50%.
22. **Exact disposition of the 12 prior A601/system-NONE cases**: see dedicated section below. All 12 requested sample IDs verified present in H4 and verified to actually match the "system NONE, original reviewer A601" pattern (not blindly trusted — independently recomputed from artifacts). 11/12 flipped to NONE under reviewer-v2 (10 at high confidence, 1 at medium); 1/12 (`holdout4-094`) stayed A601 at medium confidence in both reviews.
23. **Polarity metric contract used**: reused verbatim from `scripts/run_item2_blind_holdout2_stance_review.py` (reviewer) and `scripts/run_item2_blind_holdout2_b1.py` (production system) — the same scripts behind the historical formal B1 result (123/141 = 87.23%, PASS). Five stance classes only: `supports_alpha`, `opposes_alpha`, `mentions_alpha`, `neutral_background`, `supports_counter_alpha`. No new vocabulary invented.
24. **Polarity-evaluable denominator and why**: **47**, not 200. Denominator = `count(reviewer_v2_material_fit == true)`. H2's own metric script has no NONE-target convention (`reviewed_count = len(ids)`, always the full row count, because H2 never contained a NONE-target row) — confirming there is no existing precedent to reuse for NONE-target rows, so per task spec §17's explicit fallback, the 153 reviewer-v2-NONE rows are excluded rather than assigned an invented target.
25. **B1 system Provider calls**: 5 logical calls / 5 provider attempts / 0 retries / 0 fallbacks / 0 malformed, over the 47 polarity-evaluable rows, via the real unmodified `evidence_stance_llm.apply_llm_stance_upgrade`.
26. **B1 reviewer Provider calls**: 5 logical calls / 5 provider attempts / 0 malformed, over the same 47 rows, independently and blindly (reviewer never saw system B1 output).
27. **H4 DEVELOPMENT POLARITY**: 39/47 = **82.98%**, threshold ≥80.00%, **DEVELOPMENT PASS**.
28. **Historical formal B1 (Blind Holdout #2)**: 123/141 = 87.23%, **FORMAL PASS** — unchanged, not replaced by this development result.
29. **Critical supports/opposes reversal count**: **2** (`holdout4-057`, target A001; `holdout4-196`, target A304). Both are system=`opposes_alpha` vs reviewer-v2=`supports_alpha`, on genuinely ambiguous single-sentence evidence about macro/valuation framing — see detail below. Not a large-count systemic reversal problem, but reported prominently per task instruction rather than buried.
30. **Alpha confusion matrix**: full 11×11 (10 canonical Alphas + NONE), rows = system matched Alpha, columns = reviewer-v2 expected Alpha — see table below and `item2_h4_reviewer_v2_dev_metrics.json → alpha_confusion_matrix`.
31. **Polarity confusion matrix**: full 5×5, rows = system B1 stance, columns = reviewer-v2 B1 stance — see table below.
32. **No production prompt, taxonomy, Alpha Mapper, B1 rule, B2, B4, or threshold change**: confirmed. SHA-256 of all 14 tracked critical production source files (`alpha_mapper.py`, `week2_llm.py`, taxonomy YAML, `ai_alpha_discriminator.py`, `contracts.py`, `semantic_binding.py`, `source_bundle.py`, `routes_research.py`, `manifest.py`, `pipeline.py`, `conflict_admissibility.py`, `conflict_detector.py`, `activation_scorer_v2.py`, `evidence_stance.py`) recomputed from the current working tree and diffed against the values recorded in `item2_blind_holdout4_freeze_manifest.json`: **all 14 match exactly. Zero production drift.**
33. **No H5**: confirmed, no new blind holdout sampling or acceptance test was run or implied.
34. **No commit / push**: confirmed, no git write operations performed.
35. **Focused zero-Provider regression suite**: `test_alpha_production_boundary_hardening.py`, `test_week2_semantics.py`, `test_phase1_master_exact_replay.py`, `test_phase1_master_exact_replay_false_positive_recovery.py`, `test_shadow_exact_replay.py` — **46/46 passed**, 0 failures.
36. **Session isolation**: reviewer-v2 Alpha, polarity reviewer, and polarity B1 system phases each used independent client construction; no shared conversation/session state with each other, with the original H4 reviewer, or with the original H4 system inference.
37. **Reviewer-v2 invariant integrity**: `material_fit=false ⟺ expected_alpha_id=NONE` and `material_fit=true ⟺ expected_alpha_id ∈ canonical Alpha IDs` enforced by hard validation in the reviewer script; **zero `INVARIANT_VIOLATION_*` errors** across all 200 rows.
38. **No post-freeze tuning**: confirmed. No reviewer prompt edits after reviewer-v2 outputs became visible; no polarity prompt edits after polarity outputs became visible; no manual label edits; no third reviewer; no reruns of low-confidence or mismatched rows; no taxonomy/production-prompt/threshold changes.
39. **All required new artifacts written**, none of the original formal H4 artifacts touched (`git status --porcelain` on all six original H4 formal paths shows only their original untracked state, no modification) — see artifact list below.
40. **Final verdict**: see below.

---

## Alpha diagnostics

### Confusion matrix (rows = system matched Alpha, columns = reviewer-v2 expected Alpha)

```
sys\v2     A001   A003   A101   A102   A103   A201   A301   A304   A501   A601   NONE
A001          1      0      0      0      0      0      0      1      0      0      2
A003          0      0      0      0      0      0      0      0      0      0      0
A101          0      0      2      0      2      0      0      0      0      0      3
A102          0      0      0      1      0      0      0      0      0      0      0
A103          0      0      0      0      7      0      0      0      0      0      2
A201          0      0      1      0      0      4      1      0      0      0      3
A301          0      0      0      1      0      0      5      0      0      0      6
A304          0      0      0      0      0      0      0     14      0      0     14
A501          0      0      0      0      0      0      0      0      1      0      0
A601          0      0      1      0      0      0      0      0      0      1      5
NONE          0      0      0      0      0      0      1      2      0      1    118
```

### NONE analysis

| | Count |
|---|---|
| System NONE (excl. unavailable) | 122 |
| Reviewer-v2 NONE | 153 |
| NONE/NONE agreement | 118 |
| System NONE, reviewer-v2 Alpha (under-triggering) | **4** (was 26 vs original reviewer) |
| System Alpha, reviewer-v2 NONE (over-triggering) | **35** (was 10 vs original reviewer) |

### Per-ticker Alpha accuracy

AMD 84.0%, GOOGL 60.0%, MSFT 84.0%, MU 84.0%, NVDA 60.0%, QQQ 84.0%, SNDK 88.0%, TSM 72.0% (all n=25).

### AI-family (A101/A102/A103) accuracy vs reviewer-v2

Combined 10/15 = 66.67%. By Alpha: A101 2/4 (50%), A102 1/2 (50%), A103 7/9 (77.8%).

---

## The 12 prior "system-NONE / original-reviewer-A601" cases

All 12 requested sample IDs verified present and verified to actually match the pattern (system NONE, non-unavailable; original reviewer A601).

| sample_id | ticker | original → reviewer-v2 | system | changed? |
|---|---|---|---|---|
| holdout4-008 | AMD | A601 (low) → NONE (high) | NONE | yes |
| holdout4-033 | GOOGL | A601 (low) → NONE (high) | NONE | yes |
| holdout4-036 | GOOGL | A601 (low) → NONE (high) | NONE | yes |
| holdout4-053 | MSFT | A601 (medium) → NONE (high) | NONE | yes |
| holdout4-054 | MSFT | A601 (medium) → NONE (high) | NONE | yes |
| holdout4-060 | MSFT | A601 (medium) → NONE (high) | NONE | yes |
| holdout4-094 | MU | A601 (medium) → **A601 (medium)** | NONE | **no** |
| holdout4-114 | NVDA | A601 (medium) → NONE (high) | NONE | yes |
| holdout4-119 | NVDA | A601 (medium) → NONE (high) | NONE | yes |
| holdout4-126 | QQQ | A601 (medium) → NONE (high) | NONE | yes |
| holdout4-175 | SNDK | A601 (medium) → NONE (medium) | NONE | yes |
| holdout4-199 | TSM | A601 (low) → NONE (high) | NONE | yes |

Every flip is grounded in the same diagnosed defect: rising SMA, MACD readings, "uptrend intact," "technical breakout is legitimate," raw bullish/bearish sentiment counts, and similar pure technical/meta language were previously force-mapped to A601 despite expressing no narrative/attention/crowding/reflexive-flow mechanism. The one case that stayed A601 (`holdout4-094`, MU) describes multiple outlets *debating* the stock's fair price — i.e., active narrative/attention-driven price-discovery — which is the actual A601 mechanism. This is exactly the pattern the corrected protocol was designed to produce: strict on pure technical language, but not biased toward NONE when the mechanism is genuinely present.

---

## Polarity diagnostics

### Confusion matrix (rows = system B1 stance, columns = reviewer-v2 B1 stance)

```
sys\rev     SUP    OPP   MENT   NEUT    CTR
SUP          28      0      1      0      0
OPP           2      8      0      0      1
MENT          3      0      1      0      0
NEUT          0      0      1      2      0
CTR           0      0      0      0      0
```
(SUP=supports_alpha, OPP=opposes_alpha, MENT=mentions_alpha, NEUT=neutral_background, CTR=supports_counter_alpha)

### Accuracy by stance class (reviewer-v2 label)

supports_alpha 28/33 (84.8%), opposes_alpha 8/8 (100%), mentions_alpha 1/3 (33.3%), neutral_background 2/2 (100%), supports_counter_alpha 0/1 (0%).

### Accuracy by target Alpha

A101 4/4, A102 2/2, A103 9/9, A201 4/4, A501 1/1 (all 100%); A304 14/17 (82.4%); A301 5/7 (71.4%); A001 0/1 (0%); A601 0/2 (0%).

### Accuracy by ticker

AMD 7/7, QQQ 2/2, SNDK 4/4 (100%); NVDA 8/9 (88.9%); MSFT 6/7 (85.7%); MU 6/8 (75%); GOOGL 3/5, TSM 3/5 (60% each — weakest).

### Critical supports_alpha ↔ opposes_alpha reversals (2)

- **holdout4-057** (MSFT, target A001): evidence = "89% probability of no rate cuts, surging 10-year yields, rising oil prices — hostile macro backdrop." System: `opposes_alpha`. Reviewer-v2: `supports_alpha` (high), reasoning that confirming rate cuts are *not* materializing directly supports the A001 thesis framing. This is a genuine directional-framing ambiguity (does evidence that a catalyst *isn't* happening "support" or "oppose" an Alpha named for that catalyst?) rather than an obvious error on either side; flagged for visibility, not adjudicated (no post-freeze tuning authorized).
- **holdout4-196** (TSM, target A304): evidence = "TSM near intrinsic value after 335% run, good news may be priced in." System: `opposes_alpha`. Reviewer-v2: `supports_alpha` (high), reasoning that "no longer cheap, upside priced in" supports a multiple-compression/downside thesis. Same class of directional-framing ambiguity as above.

### Other counts

supports_counter_alpha: 1. neutral_background: 2. mentions_alpha: 3.

---

## Artifacts written this segment

- `docs/audit_artifacts/item2_h4_reviewer_v2_dev_freeze.json`
- `docs/audit_artifacts/item2_h4_reviewer_v2_dev_alpha_review.json`
- `docs/audit_artifacts/item2_h4_reviewer_v2_dev_alpha_comparison.csv`
- `docs/audit_artifacts/item2_h4_reviewer_v2_dev_polarity_review.json`
- `docs/audit_artifacts/item2_h4_reviewer_v2_dev_polarity_system.json`
- `docs/audit_artifacts/item2_h4_reviewer_v2_dev_polarity_comparison.csv`
- `docs/audit_artifacts/item2_h4_reviewer_v2_dev_metrics.json`
- `docs/audit_artifacts/item2_h4_reviewer_v2_dev_provider_audit.json`
- `docs/audit_artifacts/item2_h4_reviewer_v2_dev_report.md` (this file)
- `scripts/run_item2_h4_reviewer_v2_alpha_review.py`
- `scripts/run_item2_h4_reviewer_v2_polarity_review.py`
- `scripts/run_item2_h4_reviewer_v2_polarity_system.py`
- `scripts/build_item2_h4_reviewer_v2_dev_summary.py`

None of the six original H4 formal artifacts (`item2_blind_holdout4_frozen.csv`, `_alpha_review.json`, `_system_alpha.json`, `_comparison.csv`, `_metrics.json`, `_report.md`) were modified. Original formal H4 Alpha result remains visible and unchanged: **148/200 = 74.00%, FAIL**.

---

## Final verdict

**DEVELOPMENT RE-EVALUATION: PASS**
**Alpha Match Accuracy: 77.00% >= 75%**
**B1 Polarity Accuracy: 82.98% >= 80%**

Under the corrected two-stage material-fit reviewer protocol, the frozen H4 development set meets both the Alpha Match and B1 Polarity target thresholds. The original formal H4 blind verdict remains FAIL because H4 is consumed. The corrected reviewer protocol may now be frozen prospectively for a genuinely new Blind Holdout #5.
