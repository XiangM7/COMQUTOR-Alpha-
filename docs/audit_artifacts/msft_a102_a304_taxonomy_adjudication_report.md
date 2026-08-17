# MSFT A102__A304 Canonical Conflict Taxonomy Adjudication

**Branch:** `comqutor-structure-layer` **HEAD (before and after):** `b5837e80a4550fc35165d0013a8ef0f27ccb4c8f` (unchanged)
**Worktree:** preserved, no destructive git operations **Commit:** none **Push:** none **Subagents used:** 0

Machine-readable companion: [`msft_a102_a304_taxonomy_adjudication_report.json`](msft_a102_a304_taxonomy_adjudication_report.json).

## Decision

```
DECISION = REJECT_PAIR
```

`A102__A304` is **not** added to the canonical conflict taxonomy. This is a **user-authorized independent
LLM product adjudication** — not a human Product Owner decision, not John's personal approval, no human
review was performed. Full reasoning is recorded as **PD-017** in
[`docs/specs/product_decisions_and_unknowns.md`](../specs/product_decisions_and_unknowns.md).

## 1. Files changed

- `docs/specs/product_decisions_and_unknowns.md` — added PD-017 (new decision record; PD-001 through PD-016 untouched).
- `comqutor_alpha/config/j2_provisional_regression_labels_v0.2.yaml` — MSFT's `A102__A304` moved from `product_decision_pending` to `remove_while_undeclared`.
- `tests/test_msft_a102_a304_taxonomy_adjudication.py` — new, 16 tests.
- `tests/test_j3_semantic_benchmark_j2_v0_2.py` — one test updated (`test_c26_*`; it asserted the pre-PD-017 pending state, now asserts the post-PD-017 rejected state — not loosened, just brought current).
- This report (`.md` + `.json`).
- `outputs/regression/regression_report_v0.2.json` — regenerated (reproducible output artifact, not source data) to reflect PD-017.

**Never touched:** `comqutor_alpha/alpha_library/alpha_taxonomy_v1.yaml`, `comqutor_alpha/config/j2_provisional_regression_labels_v0.1.yaml`, `comqutor_alpha/regression/evaluation_contract.py` (needed zero code changes), B1 (`week2_llm.py`), B2 (`conflict_admissibility.py`, `conflict_detector.py`, `conflict_schema.py`), `alpha_mapper.py`, the J3 provisional benchmark, and the Development Plan `.docx` (still PD-001 `SOURCE_FROZEN`).

## 2. Authority hierarchy applied

```
1. canonical Alpha definitions
2. approved Product Decisions / ADRs
3. canonical conflict taxonomy contract
4. Development Plan
5. saved production artifacts
6. provisional J2 predictions (never define production taxonomy)
```

## 3. A102 and A304 canonical definitions

| | A102 — Inference Explosion | A304 — Multiple Compression |
|---|---|---|
| Layer | Theme | Valuation |
| Core thesis | Enterprise AI applications and AI agents increase inference compute demand | Rich valuation and high multiples create downside risk despite strong fundamentals |
| `conflict_alphas` (taxonomy) | **`[]`** | `[A101 (0.90), A301 (0.85), A601 (0.80)]` |
| `relations` | supportive → A103 (0.80), A301 (0.70) | — |

Neither canonical definition declares a tension between these two specific Alphas.

## 4. Canonical conflict taxonomy contract

`comqutor_alpha/alpha_library/alpha_loader.py`'s `MANDATORY_CONFLICT_WEIGHTS` hard-codes exactly six pairs,
enforced by `validate_taxonomy`: `A101–A304, A301–A304, A001–A501, A003–A501, A601–A304, A601–A501`. The
taxonomy's design pattern lets A304 conflict with exactly **one** representative Alpha per causal layer
that terminates a growth thesis (A101 = Theme-top, A301 = Fundamental-terminal, A601 = Sentiment
cross-cutting), deliberately omitting the supportive chain-input Alphas that feed into them — A102
(Theme), A103 (Infrastructure), A201 (Industry) all carry `conflict_alphas: []`, structurally identical to
each other.

## 5. Development Plan expectation — and its own internal contradiction

Development Plan v1.0 (`docs/specs/COMQUTOR_Alpha_Development_Plan_v1.0.docx`, PD-001 `SOURCE_FROZEN`,
SHA-256 `cabf3381…c439a8d9`, confirmed unchanged before and after this task):

- **§4** — "Conflict (all six are mandatory in MVP): A101 vs A304 · A301 vs A304 · A001 vs A501 · A003 vs
  A501 · A601 vs A304 · A601 vs A501." **A102 vs A304 is not one of the six.**
- **§12 "Golden Test Cases"** (attributed to "John supplies expectations"):

  | Ticker | Expected dominant alphas | Expected main conflict |
  |---|---|---|
  | NVDA | A101, A103, A201, A301, A304, A601 | Bull A101 vs Bear A304 |
  | QQQ | A001, A003, A304, A501, A601 | Bull A001 vs Bear A501 |
  | MSFT | A101, A102, A301, A304 | **Bull A102 vs Bear A304** |

MSFT's row is the *only* one of the three golden rows whose stated main conflict is not one of §4's own six
mandatory pairs — and MSFT's own dominant-alpha cell already lists **A101**, so "Bull A101 vs Bear A304"
(consistent with NVDA's row and with §4) was directly available without inventing anything. A101 and A102
are adjacent, similarly-named Theme-layer IDs ("AI Expansion" / "Inference Explosion"); the far more
parsimonious reading is a drafting slip in §12, not a reasoned, ticker-specific design decision — nothing
elsewhere in the Development Plan explains *why* MSFT specifically would need a distinct conflict pair
from every other AI-exposed ticker.

## 6. Existing Product Decisions / ADRs reviewed

PD-001 through PD-016 and ADR-001 through ADR-010 were reviewed. **None addresses `A102__A304` or MSFT's
conflict-pair set.** PD-013 is the closest related item but concerns a different topic entirely — the
A101/A102/A103 Alpha *matching*-threshold carve-out in `ai_alpha_discriminator.py`, not conflict-pair
declaration.

## 7. MSFT saved-run evidence (informational, rank-5 authority)

Only one MSFT saved run has a completed offline replay: `0cb43bae-1a4d-4003-bb29-55d420498842`
(`stance_source=deterministic_baseline`, `artifact_completeness=fail` — a known-incomplete source
artifact; this is **not** current B1-LLM-authoritative end-to-end behavior).

| Alpha | Activation score | Evidence count | Ticker-specific evidence | Status |
|---|---|---|---|---|
| A102 | 0.0 | 0 | 0 | candidate (no evidence at all) |
| A304 | 39.75 | 7 | 0 | candidate |
| A301 (context) | 60.0 | 14 | 0 | active |

`admitted_conflicts=[]`; `candidate_conflicts=[A001__A501, A301__A304, A304__A601]`. A102 never appears in
any candidate-conflict pair — structurally impossible while A102's `conflict_alphas` is empty, regardless
of B2 admissibility. A single incomplete run cannot prove the pair "doesn't exist" semantically; it is
used here only as the absence of any empirical push toward approval.

## 8. Arguments considered

**For `APPROVE_PAIR`:** Development Plan §12's MSFT row explicitly states "Bull A102 vs Bear A304",
attributed to John's own supplied expectations; A102 and A304 can plausibly co-activate for MSFT
(Copilot/Azure AI narrative vs. rich multiple).

**For `REJECT_PAIR`:** A102's canonical `conflict_alphas` is empty by deliberate, consistent taxonomy
design (identical to A103/A201); A304's own `conflict_alphas` names A101/A301/A601, not A102; the
Development Plan's own §4 excludes this pair while §12 names it — an internal contradiction, and the
higher-ranked taxonomy contract (rank 3) outranks the lower-ranked, self-contradictory Development Plan
(rank 4); MSFT's tension with A304 is already transitively expressed via the existing A301↔A304 pair
(A102 supports A301 at 0.70; A301 conflicts A304 at 0.85); approving on general "AI-growth vs.
valuation-risk" logic would equally justify `A103__A304` and `A201__A304`, which the taxonomy has
consistently avoided; the only supporting evidence is MSFT-specific, not a general Alpha-to-Alpha semantic
argument; no PD/ADR supports it; the one available saved run shows zero A102 evidence.

## 9. Outcome

```
DECISION = REJECT_PAIR
```

**Confidence: high** — converging evidence from ranks 1 (Alpha definitions), 2 (no PD/ADR support), and 3
(taxonomy contract design), plus the Development Plan's own internal self-contradiction, against a single
ambiguous line as the only counter-evidence.

**Decision source:** `User-authorized independent LLM product adjudication` **Decision record:** PD-017,
`docs/specs/product_decisions_and_unknowns.md`

## 10. Taxonomy / J2 / A4 before and after

| | Before | After |
|---|---|---|
| `alpha_taxonomy_v1.yaml` | `sha256:c031168c…eab1e7939c` | **unchanged** (identical hash) |
| J2 v0.1 MSFT | `allowed_main_conflicts: [A102__A304]` | **unchanged** (frozen historical snapshot by design) |
| J2 v0.2 MSFT | `product_decision_pending: [{A102__A304, "Development Plan expectation conflicts with canonical taxonomy."}]`, `remove_while_undeclared: []` | `product_decision_pending: []`, `remove_while_undeclared: [A102__A304]` |
| A4 (`evaluation_contract.py`) | — | **no code change** — `remove_while_undeclared` pairs were already surfaced informationally regardless of ticker evaluability by the existing evaluator |
| Real MSFT shadow result | `evaluation_status=not_evaluable`, showed a pending entry regardless of evaluability | `evaluation_status=not_evaluable` (unchanged — artifact still incomplete), `product_decision_pending_results=[]`, `removed_while_undeclared_pairs=[A102__A304]` |

J2 v0.1 is intentionally left untouched — it remains a frozen historical snapshot (its own
`PREDICTED_CONFLICT_PAIR_NOT_DECLARED` note for MSFT still fires exactly as before); v0.2 is where this
adjudication's outcome is reflected, consistent with v0.1/v0.2's existing "both remain independently
loadable, v0.1 never superseded" design.

## 11. B1/B2/B3/B4/J3 invariants

Confirmed byte-identical via SHA-256: `week2_llm.py`, `alpha_mapper.py`, `conflict_schema.py`,
`conflict_admissibility.py`, `conflict_detector.py`, `alpha_taxonomy_v1.yaml`, and the J3 provisional
benchmark. The five-value stance vocabulary, B2 admissibility thresholds, ConflictScore, Exposure formula,
and the J3 50-row benchmark's 39/50 · 22/50 · 7-reversal numbers were never touched.

## 12. Source hashes before/after

| File | Before | After | Identical |
|---|---|---|---|
| `alpha_taxonomy_v1.yaml` | `c031168c…` | `c031168c…` | ✅ |
| Development Plan `.docx` | `cabf3381…` | `cabf3381…` | ✅ (still matches PD-001's own recorded hash) |
| J3 provisional benchmark | `0a021fef…` | `0a021fef…` | ✅ |
| J2 v0.1 labels | `3eec746e…` | `3eec746e…` | ✅ |
| MSFT saved run `raw_agent_outputs.json` | — | — | ✅ (replay's own before/after check) |
| J2 v0.2 labels | `6428d437…` | `9988036e…` | intentionally changed |
| PD register | `4c572503…` | `81237b9d…` | intentionally changed |

## 13. Tests

New `tests/test_msft_a102_a304_taxonomy_adjudication.py` — **16 passed**, covering: decision record
exists/readable, decision source accurate, never claims John/human approval, J2 consistent with the
decision, A4 no longer reports the old pending entry, B1/B2/B3/B4 modules byte-identical, Provider/
TradingAgents calls = 0, source run and J3 benchmark byte-identical, canonical taxonomy hash unchanged, J2
no longer treats the pair as executable, A4 never reports the missing pair as a ticker failure, the
validator still rejects `A102__A304` if resubmitted as an executable pair, A102 still has zero canonical
conflicts, and the Development Plan is preserved with a formal superseding decision.

One existing test updated (not loosened): `test_j3_semantic_benchmark_j2_v0_2.py`'s
`test_c26_msft_a102_a304_was_adjudicated_and_rejected_not_pending` previously asserted the pre-PD-017
`product_decision_pending` state; it now asserts the post-PD-017 `remove_while_undeclared` state, since
that prior state was the very thing this task formally adjudicated and changed.

Combined related-suite re-run: **293 passed** (this task's 16 + `test_j3_semantic_benchmark_j2_v0_2.py` 61
+ `test_a4_regression_runner.py` 41 + `test_j3_review_packet_export.py` 29 + `test_conflict_detector.py`
full suite). Ruff clean on all of this task's own new/modified Python files.

**Full backend regression:**

```
3562 passed, 3 failed, 47 skipped, 69 subtests passed in 736.66s
```

The 3 failures are the same pre-existing set as the prior J2-v0.2 checkpoint (3546 passed / 3 failed / 47
skipped), unrelated to this task:
`structured_output_shadow/test_source_integrity.py::test_current_semantic_components_match_approved_phase1_master_baseline`
and `test_w5_demo_seed.py::test_seed_is_complete_idempotent_and_reusable_without_provider` +
`::test_only_nvda_and_qqq_are_seeded`. The delta (3562 − 3546 = 16) is exactly this task's own 16 new
tests. **Zero new failures introduced.**

Frontend not modified this task — not rerun.

## 14. Non-goals honored

No J4 six-ticker live LLM run · no new Provider review · no new TradingAgents run · no Golden Baseline
v1.0 · no B1 prompt tuning · no deterministic heuristic expansion · no B2 threshold adjustment · no
unrelated taxonomy expansion · no other Alpha pair cleanup · no frontend redesign · no repository cleanup
· no commit · no push.

## 15. Completion declarations

```
MSFT A102__A304 TAXONOMY ADJUDICATION COMPLETE
DECISION = REJECT_PAIR
CANONICAL TAXONOMY UNCHANGED
J2 V0.2 ALIGNED
J4 NOT STARTED

USER-AUTHORIZED INDEPENDENT LLM ADJUDICATION
JOHN APPROVAL NOT CLAIMED
HUMAN REVIEW NOT PERFORMED
PROVIDER CALLS = 0
TRADINGAGENTS CALLS = 0
COMMIT = none
PUSH = none
```
