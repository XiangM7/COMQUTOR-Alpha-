# v0.2 John Rule Baseline Diff — Day 1

Read-only audit. No rule, config, test, or production code was changed to produce this document. Companion machine-readable file: `v0_2_john_rule_baseline_diff.json`.

## Authority Freeze (Day 1 Closeout)

John being unavailable, his latest written v0.2 baseline (Section 2 of his own Day 1 closeout instruction) is now frozen as the highest acceptance authority, superseding inconsistent repository configuration for acceptance purposes. This is not an invented rule change — every pair below is copied verbatim from John's own written instruction. See `docs/audit_artifacts/v0_2_john_frozen_gold_baseline.yaml` for the full frozen artifact.

**This does not erase anything discovered below.** Every difference this audit found between John's baseline and the actual repo config (`j2_provisional_regression_labels_v0.1.yaml` / `_v0.2.yaml` / `v0_2_gold_operational_contract.json`) is preserved as-is. What changes is the *resolution*: the open question "is this John's intended rule?" is now answered YES for all 16 pairs (his baseline says so explicitly), so nothing below is `REQUIRES_CONFIRMATION` any longer. Each row's final status is now either:

- **RESOLVED_MATCHES_JOHN_FROZEN_BASELINE** — CURRENT_REPO_IMPLEMENTATION already agrees with JOHN_FROZEN_BASELINE; no repo change needed.
- **IMPLEMENTATION_ALIGNMENT_REQUIRED** — JOHN_FROZEN_BASELINE includes this pair/family; CURRENT_REPO_IMPLEMENTATION does not yet reflect it (missing from config, flagged non-canonical by the taxonomy, or read under a different field name/version). The product baseline controls acceptance scope; the implementation must later be brought into alignment with it. No production taxonomy or config file is modified by this Day 1 task.

## Executive Summary

1. **Which ticker rule sets match John's baseline exactly?** By pair *content* (ignoring which field/category holds it): **NVDA** matches exactly across all three sources found in the repo. **SNDK** matches exactly in the v0.1 regression-label file only (one of its two pairs carries a taxonomy caveat — see below). No ticker matches exactly once field/category naming is also required to match.
2. **Which do not?** QQQ, MSFT, TSM, AMD each have at least one John-baseline pair that is either entirely absent from every source file, present but flagged non-canonical against the Alpha taxonomy, or present only in a source the real evaluator does not read.
3. **Are missing rules actually absent from source, or merely not loaded / misrepresented?** Both, depending on the pair. Some pairs (QQQ's A003__A501/A304__A601, MSFT's A101__A304/A301__A304, TSM's A101__A304) are **genuinely absent from every rule-source file** in the repository. Others (QQQ's A001__A501, SNDK's A301__A304, TSM's A301__A304) **do exist in a real, loaded config file** but were reported as `null`/`NOT_APPLICABLE` in the prior submission artifact anyway — a misrepresentation, not a loading failure.
4. **Which prior `NOT_APPLICABLE` conclusions are unsupported under John's restored baseline?** All four (QQQ, SNDK, MSFT, TSM). Each of these tickers has at least one non-empty, genuinely loaded `allowed_main_conflicts` entry in `j2_provisional_regression_labels_v0.1.yaml` (QQQ: 1 pair; SNDK: 2 pairs; MSFT: 1 pair, non-canonical; TSM: 2 pairs). A file with a non-empty `allowed_main_conflicts` list cannot produce the evaluator's `NOT_APPLICABLE`/`None` result (see `conflict_comparison()` in `comqutor_alpha/regression/evaluator.py`) — that result only occurs when the list is empty. This means the prior submission's per-ticker `null`/`NOT_APPLICABLE` values were **not** derived from running the real evaluator against the real v0.1 config; they trace instead to `docs/audit_artifacts/v0_2_gold_operational_contract.json`, a hand-authored, code-unwired documentation file whose `allowed_main_conflicts` field happens to be empty for exactly these four tickers.
5. **Which items require John's confirmation before changing config?** None remain open. John's latest written v0.2 baseline (see Authority Freeze above) resolves which pairs are his intended rules for all six tickers. The 13 pairs previously marked `REQUIRES_CONFIRMATION` are now either `RESOLVED_MATCHES_JOHN_FROZEN_BASELINE` (3 pairs — repo already correct) or `IMPLEMENTATION_ALIGNMENT_REQUIRED` (10 pairs — repo/taxonomy still needs to catch up), plus 5 semantic-family items also carried forward as `IMPLEMENTATION_ALIGNMENT_REQUIRED`. See per-ticker tables below and `v0_2_john_frozen_gold_baseline.yaml`.

---

## Real Rule Authorities Found (Section 3)

Three non-identical sources exist; **no single file is both (a) John's exact baseline and (b) the file the runtime evaluator actually reads**:

| Source | File | Loaded by code? | Declared status |
|---|---|---|---|
| Canonical taxonomy | `comqutor_alpha/alpha_library/alpha_taxonomy_v1.yaml` | Yes — deepest authority; defines which pairs can ever be admitted/candidate at all | Production |
| Regression label v0.1 | `comqutor_alpha/config/j2_provisional_regression_labels_v0.1.yaml` | **Yes** — `comqutor_alpha/regression/evaluator.py::conflict_comparison` reads its literal `allowed_main_conflicts` field; this is the A4 CLI's **default** label source | `evaluation_mode=shadow`, `formal_product_owner_approval=pending` — file's own header: "never John-approved, never formal gold" |
| Regression label v0.2 | `comqutor_alpha/config/j2_provisional_regression_labels_v0.2.yaml` | Yes, but only via `evaluation_contract.py::apply_v2_contract` — a **separate** pass/fail computation that never feeds `main_conflict_match`. Only loaded when `scripts/run_regression.py --labels-v2 ...` is explicitly passed; v0.1 remains the CLI default. | Same as v0.1: shadow, pending, never John-approved |
| Gold operational contract | `docs/audit_artifacts/v0_2_gold_operational_contract.json` / `.md` | **No.** Zero Python files reference this path anywhere in the repository. | Self-declares `freeze_status: FROZEN_GOLD_V0_2` (2026-09-10), `remaining_review_items: []` — but is not wired into any loader or evaluator, and (per this audit) omits 8 of John's baseline pairs across QQQ/SNDK/MSFT/TSM |

Canonical taxonomy conflict pairs (from `alpha_taxonomy_v1.yaml`'s own `conflict_alphas` declarations, confirmed via the existing loader): `A001__A501`, `A003__A501`, `A101__A304`, `A301__A304`, `A304__A601`, `A501__A601`.

Note: `docs/audit_artifacts/v0_2_gold_operational_contract.json` is also the **only** place in the repository that uses John's exact six rule_type vocabulary names (`must_detect_if_evidence_present`, `should_detect_if_supported`, `conditional_only`, `do_not_force`, `allowed_main_conflicts`, `forbidden_dominant_without_strong_evidence`) — see the family-existence table below.

---

## Rule-Type Family Existence Audit (Section 2)

John's six-family vocabulary is defined only in documentation; the real, executing A4 evaluator uses a structurally similar but differently-named and differently-scoped set of mechanisms. Per the authority freeze, absence of runtime wiring under John's exact name is never reinterpreted as absence of the Gold rule — all six families are frozen as official Gold v0.2 acceptance semantics in `v0_2_john_frozen_gold_baseline.yaml`, and any family that is documentation-only or differently-named is `IMPLEMENTATION_ALIGNMENT_REQUIRED`, not rejected.

| Rule Type | Exists in source? | Source file | Loaded at runtime? | Note | Day 1 Resolution |
|---|---|---|---|---|---|
| `must_detect_if_evidence_present` | Yes | `v0_2_gold_operational_contract.json` (rule_type value) | **No** | Documentation-only; no evaluator enforces an evidence-conditional "must detect" gate under this name. | **IMPLEMENTATION_ALIGNMENT_REQUIRED** |
| `should_detect_if_supported` | Yes | `v0_2_gold_operational_contract.json` (rule_type value) | **No** | Closest real analogue: v0.1/v0.2 `conditional_alphas` (informational miss only) — different code path, different name. | **IMPLEMENTATION_ALIGNMENT_REQUIRED** |
| `conditional_only` | Yes | `v0_2_gold_operational_contract.json` (rule_type value, most rules) | **No** | Closest real analogue: v0.1 `conditional_alphas` / v0.2 `conditional_conflicts`. | **IMPLEMENTATION_ALIGNMENT_REQUIRED** |
| `do_not_force` | Yes | `v0_2_gold_operational_contract.json` line 44 | **No** | Explicitly documented as "a cross-cutting constraint... not a standalone rule_type of its own" — has no rule entries and no code enforcement anywhere (confirmed by full-repo search). | **IMPLEMENTATION_ALIGNMENT_REQUIRED** |
| `allowed_main_conflicts` | Yes | `j2_provisional_regression_labels_v0.1.yaml` (literal field) + contract JSON (NVDA/AMD only) | **Partially** — v0.1's literal field is read by `evaluator.py`; v0.2's renamed categories and the contract JSON are not | The only family with a real, executing implementation. Full per-ticker/per-pair detail below. | Mixed — see per-pair table below (6 `RESOLVED_MATCHES_JOHN_FROZEN_BASELINE`, 10 `IMPLEMENTATION_ALIGNMENT_REQUIRED`) |
| `forbidden_dominant_without_strong_evidence` | Yes | `v0_2_gold_operational_contract.json` (rule_type, QQQ/SNDK) | **Yes** | Same concept genuinely implemented under the name `should_not_be_dominant_without_strong_evidence` in both v0.1 and v0.2 label YAMLs, read by `evaluator.py` line 333. | **RESOLVED_MATCHES_JOHN_FROZEN_BASELINE** (name differs, mechanism already real and loaded) |

---

## `allowed_main_conflicts` — Per-Ticker Detail (Sections 1, 6, 7)

### NVDA (FORMAL_GOLD)

| Pair | John Baseline | Actual Config | Source File | Rule Version | Selected/Loaded | Prior Submission | Difference | Day 1 Status | Confirmation Needed |
|---|---|---|---|---|---|---|---|---|---|
| A101__A304 | ✓ | ✓ (v0.1 `allowed_main_conflicts`, v0.2 `conditional_conflicts`, contract JSON) | `j2_provisional_regression_labels_v0.1.yaml` | j2.provisional.v0.1 | PRESENT_AND_LOADED | `["A101__A304","A301__A304"]`, match=True | None | **MATCH** | No |
| A301__A304 | ✓ | ✓ (same three sources) | same | same | PRESENT_AND_LOADED | (as above) | None | **MATCH** | No |

### QQQ (FORMAL_GOLD)

| Pair | John Baseline | Actual Config | Source File | Rule Version | Selected/Loaded | Prior Submission | Difference | Day 1 Status | Confirmation Needed |
|---|---|---|---|---|---|---|---|---|---|
| A001__A501 | ✓ | ✓ (v0.1 `allowed_main_conflicts`; v0.2 `conditional_conflicts`) | `j2_provisional_regression_labels_v0.1.yaml` | j2.provisional.v0.1 | PRESENT_AND_LOADED | reported as `null`/`NOT_APPLICABLE` | Prior artifact contradicts the real, loaded, non-empty config | SUBMISSION_ARTIFACT_MISMATCH → **RESOLVED_MATCHES_JOHN_FROZEN_BASELINE** | No — repo already correct; the old submission artifact (not the repo config) was wrong |
| A003__A501 | ✓ | ✗ — absent from every source (v0.1, v0.2, contract JSON) | — | — | — | reported as `null`/`NOT_APPLICABLE` | Canonical pair, never added to any config | MISSING_IN_CURRENT_CONFIG → **IMPLEMENTATION_ALIGNMENT_REQUIRED** | No — John's baseline resolves intent; repo config still needs this pair added |
| A304__A601 | ✓ | ✗ — absent from every source | — | — | — | reported as `null`/`NOT_APPLICABLE` | Canonical pair, never added to any config | MISSING_IN_CURRENT_CONFIG → **IMPLEMENTATION_ALIGNMENT_REQUIRED** | No — John's baseline resolves intent; repo config still needs this pair added |

CURRENT_REPO_IMPLEMENTATION for QQQ ≠ JOHN_FROZEN_BASELINE (1 of 3 pairs present and loaded; 2 of 3 missing from every source). John's baseline controls acceptance scope; the two missing pairs are `IMPLEMENTATION_ALIGNMENT_REQUIRED`, not open questions.

### SNDK (FORMAL_GOLD)

| Pair | John Baseline | Actual Config | Source File | Rule Version | Selected/Loaded | Prior Submission | Difference | Day 1 Status | Confirmation Needed |
|---|---|---|---|---|---|---|---|---|---|
| A201__A304 | ✓ | ✓ v0.1 `allowed_main_conflicts` (flagged non-canonical by the loader itself); ✗ removed in v0.2 (`remove_while_undeclared`) | `j2_provisional_regression_labels_v0.1.yaml` | j2.provisional.v0.1 | PRESENT_BUT_NON_CANONICAL | reported as `null`/`NOT_APPLICABLE` | Not a canonical taxonomy pair (A201 has no declared `conflict_alphas`); v0.1 vs v0.2 disagree on whether to keep it | SOURCE_AMBIGUOUS → **IMPLEMENTATION_ALIGNMENT_REQUIRED** | No — John's baseline resolves intent; taxonomy still needs to be brought into alignment |
| A301__A304 | ✓ | ✓ (v0.1 `allowed_main_conflicts`; v0.2 `conditional_conflicts`) | `j2_provisional_regression_labels_v0.1.yaml` | j2.provisional.v0.1 | PRESENT_AND_LOADED | reported as `null`/`NOT_APPLICABLE` | Prior artifact contradicts the real, loaded, non-empty config | SUBMISSION_ARTIFACT_MISMATCH → **RESOLVED_MATCHES_JOHN_FROZEN_BASELINE** | No — repo already correct; the old submission artifact was wrong |

CURRENT_REPO_IMPLEMENTATION for SNDK matches JOHN_FROZEN_BASELINE by content in v0.1 (2/2 pairs present, one — A201__A304 — with a taxonomy caveat that is now `IMPLEMENTATION_ALIGNMENT_REQUIRED` rather than an open question). The prior submission's "ungoverned" conclusion is not supported by v0.1 and is superseded by the frozen baseline.

### MSFT (SILVER_DIAGNOSTIC)

| Pair | John Baseline | Actual Config | Source File | Rule Version | Selected/Loaded | Prior Submission | Difference | Day 1 Status | Confirmation Needed |
|---|---|---|---|---|---|---|---|---|---|
| A102__A304 | ✓ | ✓ v0.1 `allowed_main_conflicts` (flagged non-canonical); explicitly removed in v0.2 with a cited product-decision (PD-017: `REJECTED_BY_INDEPENDENT_LLM_ADJUDICATION`) | `j2_provisional_regression_labels_v0.1.yaml` / `_v0.2.yaml` | v0.1 / v0.2 | PRESENT_BUT_NON_CANONICAL | reported as `null`/`NOT_APPLICABLE` | Not a canonical taxonomy pair (A102 has no declared `conflict_alphas`); v0.2 additionally cites a prior product-decision rejecting it | SOURCE_AMBIGUOUS → **IMPLEMENTATION_ALIGNMENT_REQUIRED** | No — John's baseline controls acceptance scope over PD-017 and the taxonomy gap; alignment deferred, not silently changed |
| A101__A304 | ✓ | ✗ — absent from every source | — | — | — | reported as `null`/`NOT_APPLICABLE` | Canonical pair, never added to any MSFT config block | MISSING_IN_CURRENT_CONFIG → **IMPLEMENTATION_ALIGNMENT_REQUIRED** | No — John's baseline resolves intent; repo config still needs this pair added |
| A301__A304 | ✓ | ✗ — absent from every source | — | — | — | reported as `null`/`NOT_APPLICABLE` | Canonical pair, never added to any MSFT config block | MISSING_IN_CURRENT_CONFIG → **IMPLEMENTATION_ALIGNMENT_REQUIRED** | No — John's baseline resolves intent; repo config still needs this pair added |

MSFT's actual run detected no main conflict at all, so "no conflict admitted" may still be a valid real output — but that is a separate question from whether the *rule set* is complete, and it is not: 2 of 3 canonical baseline pairs were never encoded anywhere for MSFT, and the third (A102__A304) needs taxonomy alignment.

### TSM (SILVER_DIAGNOSTIC)

| Pair | John Baseline | Actual Config | Source File | Rule Version | Selected/Loaded | Prior Submission | Difference | Day 1 Status | Confirmation Needed |
|---|---|---|---|---|---|---|---|---|---|
| A201__A304 | ✓ | ✓ v0.1 `allowed_main_conflicts` (flagged non-canonical); removed in v0.2 | `j2_provisional_regression_labels_v0.1.yaml` | v0.1 | PRESENT_BUT_NON_CANONICAL | reported as `null`/`NOT_APPLICABLE` | Not a canonical taxonomy pair | SOURCE_AMBIGUOUS → **IMPLEMENTATION_ALIGNMENT_REQUIRED** | No — John's baseline resolves intent; taxonomy still needs to be brought into alignment |
| A301__A304 | ✓ | ✓ (v0.1 `allowed_main_conflicts`; v0.2 `conditional_conflicts`) | `j2_provisional_regression_labels_v0.1.yaml` | v0.1 | PRESENT_AND_LOADED | reported as `null`/`NOT_APPLICABLE` | Prior artifact contradicts the real, loaded, non-empty config | SUBMISSION_ARTIFACT_MISMATCH → **RESOLVED_MATCHES_JOHN_FROZEN_BASELINE** | No — repo already correct; the old submission artifact was wrong |
| A101__A304 | ✓ | ✗ — absent from every source | — | — | — | reported as `null`/`NOT_APPLICABLE`; but TSM's actual run's own detected main conflict **is** `A101__A304` | Canonical pair, matches TSM's real detected output, yet never added to any config | MISSING_IN_CURRENT_CONFIG → **IMPLEMENTATION_ALIGNMENT_REQUIRED** | No — John's baseline already confirms this pair; repo config still needs it added. Output itself is not modified. |

### AMD (SILVER_DIAGNOSTIC)

| Pair | John Baseline | Actual Config | Source File | Rule Version | Selected/Loaded | Prior Submission | Difference | Day 1 Status | Confirmation Needed |
|---|---|---|---|---|---|---|---|---|---|
| A101__A304 | ✓ | ✓ (v0.1 `allowed_main_conflicts`; v0.2 `conditional_conflicts`) | `j2_provisional_regression_labels_v0.1.yaml` | v0.1 | PRESENT_AND_LOADED | `["A101__A304","A301__A304"]`, match=True | None | **MATCH** | No |
| A201__A304 | ✓ | ✓ v0.1 `allowed_main_conflicts` (flagged non-canonical); removed in v0.2 | `j2_provisional_regression_labels_v0.1.yaml` | v0.1 | PRESENT_BUT_NON_CANONICAL | absent from prior submission's 2-pair list | Not a canonical taxonomy pair; also silently dropped from the submission's AMD list | SOURCE_AMBIGUOUS → **IMPLEMENTATION_ALIGNMENT_REQUIRED** | No — John's baseline resolves intent; taxonomy still needs to be brought into alignment |
| A301__A304 | ✓ | ✓ in v0.2 `allowed_conflicts` and contract JSON — but **absent from v0.1's `allowed_main_conflicts`**, which is the only field the real evaluator reads | contract JSON / v0.2 | undated / v0.2 | PRESENT_IN_SOURCE_BUT_NOT_IN_EVALUATOR-READ_FIELD | `["A101__A304","A301__A304"]`, match=True — pulled from the contract JSON, not from v0.1 | Prior submission's AMD list matches the unwired contract JSON, not the actually-loaded v0.1 config (which instead has A201__A304 as the second pair) | VERSION_REFERENCE_MISMATCH → **IMPLEMENTATION_ALIGNMENT_REQUIRED** | No — John's baseline confirms this pair is intended; v0.1 (the field the real evaluator reads) still needs to be reconciled to carry it |

---

## QQQ Current Output (Section 6)

- Current QQQ main conflict: **A301__A304**.
- Is it in John's frozen baseline (A001__A501, A003__A501, A304__A601)? **No.** This is confirmed final, not provisional — John's frozen written baseline (`v0_2_john_frozen_gold_baseline.yaml`) explicitly does not include A301__A304 for QQQ.
- Does a rule/config entry exist allowing A301__A304 for QQQ? A301__A304 is a canonical taxonomy pair, but it does **not** appear in QQQ's v0.1 `allowed_main_conflicts` (`["A001__A501"]` only) or in any other QQQ rule source.
- Did the prior submission incorrectly treat QQQ as ungoverned? **Yes, in part** — QQQ does have one real, loaded, non-empty `allowed_main_conflicts` entry (A001__A501, now `RESOLVED_MATCHES_JOHN_FROZEN_BASELINE`), so "ungoverned" was not accurate; but A301__A304 itself (QQQ's actual output) is not present in any source either, and — per the authority freeze — is not being added.
- Per John's explicit Day 1 closeout instruction: do NOT add A301__A304 to the baseline, do NOT modify QQQ's output, do NOT mark it PASS.

**QQQ conflict review status: `REVIEW_REQUIRED`.** (Unchanged by the authority freeze.)
Reason: John requested evidence review before any rule expansion or acceptance decision. No adjudication of evidence sufficiency was performed in this Day 1 task.

---

## No John-Approved Claims

Nothing in this document invents a rule John did not state. The 16 `allowed_main_conflicts` pairs and the six evidence-conditional semantic families are copied verbatim from John's own latest written instructions (see Authority Freeze, above, and `v0_2_john_frozen_gold_baseline.yaml`) — this is the acceptance authority now in force, per John's own engineering decision to use his latest written instruction as highest authority while he is unavailable. Every remaining gap between that baseline and the actual repository config/taxonomy is labeled `IMPLEMENTATION_ALIGNMENT_REQUIRED`, not `REQUIRES_CONFIRMATION` — there is no longer an open question about which baseline is authoritative. No rule, config, test, or production file was modified to produce this audit.
