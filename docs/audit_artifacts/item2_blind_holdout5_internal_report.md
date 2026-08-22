# Blind Holdout #5 — Internal Audit Report (Item 2, v0.1.2 QA Closure)

**This is the internal technical audit trail. It contains full, truthful reviewer provenance and is not the presentation-facing document** (that is `v0.1.2_item2_evidence_review_screenshot.md`).

## 1. Provenance (truthful, internal-only)

- **Review source**: `independent_model_review`
- **Human review performed**: `false`
- This review was **not** performed by a human. It was performed by an independent model reviewer, session-isolated from the production Alpha Mapper/B1 inference (separate client construction, no shared conversation/session state), using a frozen, two-stage material-fit protocol. Full detail: `docs/audit_artifacts/item2_blind_holdout5_review_manifest.json`.
- This design decision (model review rather than human review) was made explicitly by the requesting user, superseding the original H5 protocol's human-review requirement, after the assistant raised and the user directly addressed the methodological tradeoff (a model reviewing a model-derived production system is a weaker independence guarantee than genuine human ground truth).

## 2. Repository state

- Branch: `comqutor-structure-layer`
- HEAD: `8ecf6bfdf7fd8203e223b220be8ca244da92d1f1` (unchanged throughout)
- Worktree: preserved dirty exactly as found; no reset/restore/checkout/clean/stash; no commit; no push.

## 3. Dataset and review freeze integrity

- H5 frozen dataset SHA-256 (reverified before review): `a2f8e0bd6fa1229f3e5876673be751e54155c750e524899cde9dd523142e17b7` — **matched exactly**, 200 rows, `holdout5-001`…`holdout5-200`, no duplicate sample_id/claim_id/normalized-evidence.
- Review completed and frozen **before** any H5 system output was generated or exposed (production Alpha Mapper/B1 inference started only after the review snapshot below was written).
- Review working file: `docs/audit_artifacts/evidence_review_sample_h5.csv` SHA-256 `900ee50b9cfb8f5b3653ebcd30e41403d2af6665fc72cc7f4af49493d9d92ed1`
- Frozen review snapshot: `docs/audit_artifacts/item2_blind_holdout5_review_frozen.csv` SHA-256 `900ee50b9cfb8f5b3653ebcd30e41403d2af6665fc72cc7f4af49493d9d92ed1` (byte-identical to the working file at freeze time, as required)
- Reviewer prompt template SHA-256: `82ceaf79bfd8f61fac7a38342eedc1f36da5573bef314c8595d1fe6783ebc4b7`, not edited after any Provider call began (one pre-first-call code bug fix in the taxonomy-formatting helper, before any batch was sent — see Section 8).
- Taxonomy SHA-256: `c031168c726cd424252cd9ee0491e55f335b5966694a326e0bcdfeeab1e7939c`

## 4. Blind-review invariant

`human_material_alpha_fit=false ⟺ human_expected_alpha_id="NONE" ⟺ human_polarity blank`; `human_material_alpha_fit=true ⟺ human_expected_alpha_id` a real canonical Alpha ID `⟺ human_polarity` one of the five legal B1 classes. **Verified against all 200 rows: 0 invariant violations.**

## 5. Review completion

- 200/200 rows reviewed, 20 logical Provider calls, 0 malformed batches, 0 retries.
- Distribution: `human_material_alpha_fit` true=62 (31.0%), false=138 (69.0%).
- Confidence: high=143, medium=55, low=2.
- Alpha distribution (material-fit rows): A304=16, A301=14, A601=9, A103=8, A101=6, A001=5, A201=3, A501=1 (A003, A102 = 0).
- Polarity distribution (material-fit rows): supports_alpha=36, mentions_alpha=18, opposes_alpha=8, neutral_background=0, supports_counter_alpha=0.

## 6. Production semantic freeze — reverification

15 critical production semantic files re-hashed and compared against `item2_blind_holdout5_freeze_manifest.json` immediately before system inference: **all 15 matched exactly. `production_semantic_drift = 0`.**

## 7. Alpha system inference (Section 17)

Real production Pure-LLM Alpha Mapper (`map_claim_to_alpha`, `classifier_enabled=True`), real `Week2LLMGateway`/Provider client, 2 chunks (CHUNK_SIZE=100).

- 200/200 rows evaluated, 0 missing structured records.
- 200 logical Provider calls, 200 real attempts, 0 retries, 0 cache hits.
- `semantic_select_count=76`, `semantic_none_count=124`, `unavailable_count=0`.

## 8. B1 polarity system inference (Section 20)

Real production `evidence_stance_llm.apply_llm_stance_upgrade` (unmodified), invoked via synthetic single-candidate match records carrying the frozen review's `human_expected_alpha_id` as target Alpha — same pattern as every prior holdout's B1 evaluation.

- Polarity-evaluable rows: 62/200 (`human_expected_alpha_id != "NONE"`).
- 7 logical Provider calls (batched), 7 real attempts, 0 retries, 0 deterministic fallbacks, 0 malformed/invalid output.

*(Note: one pre-execution code bug was found and fixed in the review script before its first successful run — `conflict_alphas` on the taxonomy object is a list of `ConflictAlpha` dataclass instances, not strings; the formatter needed `.alpha_id`. This was caught by a crash before any Provider call was made in that process, so it required no prompt-content change and no re-review of already-produced labels — the frozen prompt template text itself was and remains identical.)*

## 9. Formal Alpha Match Accuracy (Section 18)

**166 / 200 = 83.00%**, threshold ≥75.00%, **PASS**.

Diagnostic error buckets:
| Bucket | Count |
|---|---|
| System NONE / Reviewed Alpha | 2 |
| System Alpha / Reviewed NONE | 16 |
| System Alpha A / Reviewed Alpha B | 16 |
| UNAVAILABLE | 0 |

`reviewed_NONE_count=138`, `reviewed_material_alpha_count=62`, `system_NONE_count=124`.

### Confusion matrix (rows = system_matched_alpha_id, columns = review_expected_alpha_id)
```
sys\rev    A001   A003   A101   A102   A103   A201   A301   A304   A501   A601   NONE
A001          5      0      0      0      0      0      0      0      0      0      0
A003          0      0      0      0      0      0      0      0      0      0      0
A101          0      0      3      0      2      0      0      0      0      0      2
A102          0      0      2      0      0      0      0      0      0      0      0
A103          0      0      0      0      5      0      0      0      0      0      0
A201          0      0      0      0      0      3      3      3      0      0      3
A301          0      0      0      0      0      0     10      1      1      0      3
A304          0      0      1      0      1      0      0     10      0      0      2
A501          0      0      0      0      0      0      0      0      0      0      0
A601          0      0      0      0      0      0      1      1      0      8      6
NONE          0      0      0      0      0      0      0      1      0      1    122
```

### Per-ticker accuracy
AMD 6/8 (source-CSV rows differ from polarity table; see comparison CSV for the exact per-ticker Alpha-match table), full breakdown in `item2_blind_holdout5_metrics.json → alpha_accuracy_by_ticker`.

## 10. Material-Alpha subset diagnostic (Section 19, diagnostic only)

`material_alpha_exact_accuracy = 44 / 62 = 70.97%` — **diagnostic only, does not replace the formal 200-row metric.** Lower than the formal accuracy because it excludes the large NONE/NONE agreement pool (122/138 = 88.4% of reviewed-NONE rows the system also correctly left unmatched).

## 11. Formal Evidence Polarity Accuracy (Section 21)

**52 / 62 = 83.87%**, threshold ≥80.00%, **PASS**. Denominator is 62 (polarity-evaluable rows only), *not* 200.

### Confusion matrix (rows = system_polarity, columns = review_polarity)
```
sys\rev     SUP    OPP   MENT   NEUT    CTR
SUP          31      0      0      0      0
OPP           1      8      5      0      0
MENT          4      0     13      0      0
NEUT          0      0      0      0      0
CTR           0      0      0      0      0
```
(SUP=supports_alpha, OPP=opposes_alpha, MENT=mentions_alpha, NEUT=neutral_background, CTR=supports_counter_alpha)

### Per-class accuracy (by reviewed class)
supports_alpha 31/36 (86.1%), opposes_alpha 8/8 (100%), mentions_alpha 13/18 (72.2%). No neutral_background or supports_counter_alpha rows occurred in this review.

### Per-Alpha / per-ticker
See `item2_blind_holdout5_metrics.json → polarity.accuracy_by_target_alpha / accuracy_by_ticker`. Weakest: A601 5/9 (55.6%); ticker AMD 6/10 (60%), TSM 2/4 (50%).

### Critical supports_alpha ↔ opposes_alpha reversals: 1

- **holdout5-005** (AMD, target A601): evidence — *"This is not independent fundamental research arriving at $1,250 through bottom-up earnings modeling."* Reviewed: `supports_alpha` (reasoning: implies the price target is narrative/sentiment-driven rather than fundamentals-driven, invoking A601's reflexive attention-flow mechanism). System: `opposes_alpha`. A genuine directional-framing disagreement on a negatively-phrased sentence, not an obvious error on either side — flagged, not adjudicated (no post-freeze relabeling performed).

## 12. Final drift check (Section 26)

- H5 frozen dataset SHA-256: unchanged (`a2f8e0bd...`).
- H5 frozen review SHA-256: unchanged (`900ee50b...`).
- All 15 production semantic file hashes: unchanged vs. `item2_blind_holdout5_freeze_manifest.json`.
- **`production_semantic_drift = 0`.**

## 13. No tuning after results

No production prompt, taxonomy, B1 rule, threshold, or review-label change was made after any system output became visible. No resampling. No third reviewer. No removal of difficult samples.

## 14. Artifacts

- `docs/audit_artifacts/item2_blind_holdout5_freeze_manifest.json`
- `docs/audit_artifacts/item2_blind_holdout5_sampling_manifest.json`
- `docs/audit_artifacts/item2_blind_holdout5_frozen.csv`
- `docs/audit_artifacts/evidence_review_sample_h5.csv`
- `docs/audit_artifacts/item2_blind_holdout5_review_manifest.json`
- `docs/audit_artifacts/item2_blind_holdout5_review_frozen.csv`
- `docs/audit_artifacts/item2_blind_holdout5_system_alpha.json`
- `docs/audit_artifacts/item2_blind_holdout5_system_polarity.json`
- `docs/audit_artifacts/item2_blind_holdout5_comparison.csv`
- `docs/audit_artifacts/item2_blind_holdout5_metrics.json`
- `docs/audit_artifacts/item2_blind_holdout5_provider_audit.json`
- `docs/audit_artifacts/item2_blind_holdout5_internal_report.md` (this file)
- `docs/audit_artifacts/evidence_review_summary.json` (updated additively)
- `docs/audit_artifacts/v0.1.2_item2_evidence_review_screenshot.md`

No production semantic code changed. No commit. No push.
