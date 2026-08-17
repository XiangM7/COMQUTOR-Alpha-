# §5.2 Product Decision Closure and John-Gold Provenance Audit

Status: **Bounded closure + provenance audit only.** Zero Provider calls, zero
subagents, zero Mapper/taxonomy/§5.1/§5.3/Graph/Activation/Conflict/Exposure
code changes, zero benchmark execution. HEAD unchanged at
`b5837e80a4550fc35165d0013a8ef0f27ccb4c8f` throughout. The only files touched
are `docs/specs/product_decisions_and_unknowns.md` (six new PD entries
appended, PD-001–PD-010 left byte-identical) and this report + its JSON
companion.

## Required inputs re-verified

- `docs/audit_artifacts/phase1_master/section_5_2_alpha_mapper_implementation_precheck.md`
  + `.json` — read in full (prior task's own output).
- `docs/specs/COMQUTOR_Alpha_Development_Plan_v1.0.docx` SHA-256 re-verified:
  `cabf3381aaa633b7b88035ab6df2d7dac0def3d5ddd337f6384f23f4c439a8d9` — matches
  `development_plan_v1.0_manifest.json`. Unchanged.
- `docs/specs/product_decisions_and_unknowns.md` — re-read; PD-005 confirmed
  byte-identical to the prior task's citation before any edit was made.

---

## Part A — Product Decisions recorded (PD-011 through PD-016)

Recorded in `docs/specs/product_decisions_and_unknowns.md` using the
repository's existing PD-XXX mechanism and field convention (Status / Source
/ Owner / Decision / Impact / Blocking phase / Required resolution) —
**no parallel decision system was invented.** PD-001 through PD-010 were left
untouched; nothing was rewritten.

| ID | Decision | Status |
|---|---|---|
| PD-011 | Cardinality: ONE primary `matched_alpha` + up to TWO informational `secondary_alphas`, never co-authoritative | `APPROVED_PROJECT_DECISION` |
| PD-012 | Alpha score = semantic relevance only; Claim confidence must not affect it | `APPROVED_PROJECT_DECISION` |
| PD-013 | 0.35 is the uniform threshold for all 10 Alphas; A101/A102/A103 carve-out is `NOT_APPROVED` | `APPROVED_PROJECT_DECISION` |
| PD-014 | No-match Claims are retained with `matched_alpha=null`, never dropped | `APPROVED_PROJECT_DECISION` |
| PD-015 | Tier-2 LLM classifier authority graduates only after authentic benchmark + ≥80% pass | `APPROVED_PROJECT_DECISION` |
| PD-016 | IF authentic benchmark is single-label THEN metric = Top-1 exact, pass = ≥16/20; IF multi-label, new decision required | `APPROVED_PROJECT_DECISION (conditional)` |

**PD-005 itself was NOT modified, NOT closed, and NOT superseded.** It remains
`BLOCKED_BY_PRODUCT_OWNER` exactly as before. PD-015/PD-016 explicitly
cross-reference it rather than duplicating or overriding it.

### Conflict handling (§15 of the task)

No genuine prior-authoritative-decision conflicts were found. PD-011, PD-012,
PD-014, and PD-016 close items the precheck had marked `AMBIGUOUS` or
`PRODUCT_DECISION_REQUIRED` — none of these had a prior ruling to conflict
with. PD-013 does not "supersede" a prior approval of the AI-alpha carve-out,
because **no prior approval of that carve-out was ever found to exist**
(see Part C) — it closes an open gap by declining to ratify an unapproved
implementation detail, not by overriding a settled one. PD-015 is fully
consistent with (not in conflict with) the pre-existing, non-PD
`semantic_authority_matrix.csv` row already stating
`PRODUCT_VALIDATION_MISSING` for the same Tier-2 path; PD-015 formalizes that
into an actual Product Decision record.

---

## Part B — John-20 provenance audit

### B.1 Every located claim of "John approved" for the §5.2 20-claim benchmark

A repository-wide, case-insensitive search for `john`, `approv*`,
`sign-?off`, `labeled_claims`, `labeled accuracy`, `20 claims`, `20 labeled`,
`PD-005`, `owner labels`, `gold labels`, `gold set`, `benchmark` was run
across all tracked `.py/.md/.json/.csv/.yaml/.yml/.txt` files (excluding
`.venv`, `tradingagents/`, `.git`). Of the ~150 files matched, the following
are the ones that actually claim or imply `labeled_claims_v1.json` (or its
test) is the official John-approved §5.2 benchmark:

| # | File | Location | Nature of claim | Type |
|---|---|---|---|---|
| 1 | `tests/test_week2_labeled_accuracy.py` | line 1 (module docstring) | `"Standalone Formal Week 2 accuracy gate over the approved labeled set."` | code/comment (test) |
| 2 | `tests/test_week2_labeled_accuracy.py` | line 53 | function name `test_approved_labeled_claim_accuracy_is_at_least_80_percent` | code (test name) |

**That is the complete list.** No doc, ADR, PD entry, sign-off artifact, or
audit report anywhere in the repository names `labeled_claims_v1.json` (by
filename, version, or hash) as John's approved set. This includes an
extensive, independent search of every "John-" and "approv-" mention found
repo-wide (see B.4) — none of the ~150 matched files, other than the test
file itself and this session's own prior precheck report (which explicitly
flagged the same conflict, not asserted approval), makes this claim.

### B.2 Dataset inspection (`labeled_claims_v1.json`)

Read directly, not modified; parsed and re-verified programmatically (not
assumed from the filename):

| Property | Value |
|---|---|
| Exact path | `tests/golden_cases/labeled_claims_v1.json` |
| SHA-256 | `9c0561fbf9dd23cd6ed1bd2eaedb6536887b8623ffedb6a53faa4553344c2bc7` |
| Schema/version marker | none — a bare JSON array, no `schema_version` key (unlike the sibling `nvda_real_report_labeled_claims_v1.json`, which does declare `week2.robust_labeled_claims.v1`) |
| Record count | **exactly 20** — confirmed by `len(json.load(...))`, not assumed from the filename |
| Record fields | `id`, `text`, `expected_alpha`, `expected_alpha_name`, `expected_direction` — confirmed identical across all 20 records |
| Claim IDs | `lc001`–`lc020` |
| Ticker field | **absent** — no `ticker` key on any record (the test hard-codes `"ticker": "NVDA"` itself when building the record to feed the Mapper) |
| Label cardinality | **single-label** — `expected_alpha` is a bare string on every record; `isinstance(x, list)` is `False` for all 20 |
| Alpha coverage | all 10 canonical Alphas represented: A001×2, A003×2, A101×3, A102×2, A103×2, A201×2, A301×2, A304×2, A501×2, A601×1 |
| Score field | **absent** |
| Notes/rationale field | **absent** |
| Author/creator metadata | **absent** |
| Approval/sign-off metadata | **absent** |
| Ranked/Top-K expectation field | **absent** |
| Negative/"no-alpha" cases | **none** — every one of the 20 expects a positive match |
| Creation/update timestamp (deterministic, via git) | created 2026-07-09 (see B.3); never modified since |

### B.3 Git history and blame (read-only: `git log`, `git show`, `git blame` only — no mutation)

- `labeled_claims_v1.json`: introduced in exactly **one** commit,
  `7d6d5c7d58ceea58ce2b79079f368f05945f8e53` ("w2v1", 2026-07-09 11:04:26
  -0700, author `xiangmao <xmao5@student.ohlone.edu>` — the repository's sole
  committer throughout its history). `git log --follow` shows no further
  commits touch this file — it has been byte-identical since creation. The
  commit bundles it together with the first versions of `alpha_mapper.py`,
  `structure_extractor.py`, and `tests/test_alpha_mapper.py`; the commit
  message is the terse codename `"w2v1"` with no body text.
- `tests/test_week2_labeled_accuracy.py`: introduced **one week later**, in a
  **different** commit, `62747173eede5750ad84fe167810fae49744c21a` ("w6v1",
  2026-07-16 15:41:36 -0700, same sole author). `git blame` confirms line 1's
  `"Standalone Formal Week 2 accuracy gate over the approved labeled set."`
  docstring was written in this exact commit, not edited afterward. This
  single large commit also touches CI config, DB schema/repository, and
  several unrelated docs (`docs/customer_investor_deck_outline.md`,
  `docs/demo_recording_script.md`, etc.) — again a coarse, squashed commit
  with no descriptive body.
- **Full-history commit-message search**: `git log --all -i --grep="john"
  --grep="sign-off" --grep="signoff" --grep="approv"` (OR-combined) returns
  **zero commits** in the entire repository history. No commit message,
  ever, references John, an approval, or a sign-off.

**Conclusion**: the "approved" characterization was authored unilaterally by
the engineer, in the same commit that wrote the test, one week after the
underlying data existed — with no separate approval commit, no accompanying
sign-off artifact, and no later commit ever adding provenance metadata to
either file.

### B.4 Independent, pre-existing corroboration that this is NOT John's real set

This is the strongest evidence in this audit. Multiple **pre-existing**
repository documents — written independently, at different times, for
different purposes, none of them by this task or the prior precheck task —
already searched for exactly this benchmark and concluded it does not exist,
**without ever citing `labeled_claims_v1.json` as a candidate**:

- `docs/development_plan_llm_boundary_audit.md` (§1, Executive Verdict) — an
  earlier Phase 0 audit, run *before* the canonical Development Plan docx was
  even added to the repository (its own §2 states "Canonical Development
  Plan source: NOT FOUND IN REPOSITORY," predating the Phase-0.5 manifest
  dated 2026-08-05): *"§5.2 Alpha Mapper: COMPLIANT... The plan-mandated
  20-labeled-claims / ≥80%-accuracy evaluation was **not found** in this
  repository (MISSING, see compliance matrix)."*
- `docs/development_plan_llm_boundary_audit_consolidated.md` (same finding,
  consolidated pass): *"John's 20 labeled claims and the ≥80% accuracy
  evaluation were not found anywhere in this repository."*
- `docs/audit_artifacts/development_plan_compliance_matrix.csv` (row 5.2):
  *"No file matching a 20-labeled-claims accuracy evaluation of the Alpha
  Mapper was found in this repository during Phase 0... MISSING."*
- `docs/audit_artifacts/phase0_5/phase0_5_completion_report.md`: *"John's 20
  labels: `BLOCKED_BY_PRODUCT_OWNER` for Phase 2."*
- `docs/audit_artifacts/phase0_5/reconciled_compliance_matrix.csv`: *"John's
  20 labeled claims and a formal >=80% result were not found."*
- `docs/specs/future_semantic_phase_contract.md`: lists *"John's 20 labeled
  claims supplied by the product owner"* as a **prerequisite** for a future
  phase's evaluation harness — i.e. treats it as not-yet-supplied.
- `docs/adr/ADR-001-semantic-authority.md`: *"Production cutover is
  prohibited until John's named 20-label acceptance set is available and the
  frozen evaluation passes."*
- `docs/specs/llm_semantic_call_contract_v1.md`: explicitly states its own
  contract *"does not... supply John's 20 labels."*
- `docs/specs/semantic_authority_matrix.csv` (row "alpha ambiguous
  classification", ADR-001-governed): cutover gate = *"John's 20 labels
  available and >=80% formal evaluation passes"*, note = `"PRODUCT_VALIDATION_MISSING"`.

None of these seven independent, earlier documents — several written for the
specific purpose of locating exactly this artifact — ever names, cites, or
references `labeled_claims_v1.json` or `test_week2_labeled_accuracy.py`. If
that file were genuinely John's approved set, it is very unlikely all seven
independent searches would have missed it while separately finding and
citing dozens of other genuine "John's X" artifacts elsewhere in the
repository (John's 9 required artifacts, John's Activation regime gate,
John's A304 rebuttal example, etc. — real, correctly-attributed examples the
same search surfaced).

### B.5 Provenance standard applied (per the task's own §8 rules)

Per the task's explicit instruction, none of the following count as proof of
approval, and none of them exist here beyond what's already listed:
a code comment saying "John approved" (not present — the actual wording is
"approved labeled set," and it is a docstring, not linked to any approval
record), a test function name (present, and explicitly disqualified as
evidence by the task), a filename, a variable name, a README assertion with
no source, a generated audit artifact repeating another unverified assertion,
git commit authorship (the sole author is the engineer, not a distinct
Product Owner identity), the fact that the test passes, or the fact that the
dataset contains 20 records.

**No acceptable evidence category from the task's §8 list is present**: no PD
record identifies this exact dataset/version (PD-005 says the opposite — the
set is missing), no sign-off artifact exists, no later requirement names this
exact file, and no other authoritative repository record establishes
approval.

### B.6 Hash/version identity

`EXACT_DATASET_VERSION_APPROVED` / `OLDER_VERSION_ONLY` /
`APPROVAL_NOT_VERSION_BOUND` all presuppose an approval event to bind a
version to. **None was found.** Classification: **`NO_APPROVAL_FOUND`**. This
is a cleaner conclusion than "an older version was approved but the file
changed" — there is no approval event anywhere in the repository's history to
even attempt to bind to a version; the file has, in any case, never been
modified since its single creating commit (B.3).

### B.7 PD-005 direct read

Current content (verified unchanged before this audit):

> **PD-005 — John's 20 Alpha Mapper Labels**
> Status: `BLOCKED_BY_PRODUCT_OWNER`. Source: Development Plan v1.0 §5.2 and
> Week 2 acceptance. Owner: John / product owner. Impact: "Formal ≥80% Alpha
> Mapper acceptance cannot be completed." Blocking phase: Phase 2 production
> cutover. Required resolution: "Supply the original 20 labeled claims,
> labels, rubric, version, and sign-off owner; do not substitute a locally
> invented set."

It names John explicitly, names exactly the four missing artifacts (claims,
labels, rubric, sign-off) plus a version identifier, and explicitly
prohibits the substitution this audit was asked to check for. **No later
authoritative Product Decision closes PD-005** — the only PD-register entries
that reference it (PD-015, PD-016, added by this task) explicitly keep it
open and cross-reference it rather than closing it. `PD_005_STATUS` remains
`BLOCKED_BY_PRODUCT_OWNER` / **OPEN**.

### B.8 Classification

Per the task's five-way taxonomy in §12, and based strictly on provenance
(not content quality — the 20 claims themselves are well-written and cover
all 10 Alphas cleanly):

**`D. SELF_DESCRIBED_AS_APPROVED_BUT_UNVERIFIED`**

The dataset does make an explicit self-description of formal approval (via
the test's docstring and function name) — that is a real, quotable fact about
the artifact, which is why this is not simply "B — engineering fixture with
no claim either way." But per the task's own rule ("If the only support is
comments/tests calling it 'approved': classification must NOT be A"), and
given the extensive, independent, pre-existing corroboration in B.4 that
affirmatively contradicts the self-description, this cannot be classified as
`A. VERIFIED_PRODUCT_OWNER_GOLD`.

---

## Part C — AI-Alpha hard gate audit (§16 of the task)

- **Code location**: `comqutor_alpha/structure_engine/ai_alpha_discriminator.py`
  (349 lines; `AI_ALPHA_IDS = frozenset({"A101", "A102", "A103"})`, line 28),
  consumed at `comqutor_alpha/structure_engine/alpha_mapper.py:517`:
  `if item.get("eligible") and (item["alpha_id"] in AI_ALPHA_IDS or item["score"] >= min_score)`
  — i.e. for exactly these three Alphas, the independent boolean hard gate
  (an anchor phrase plus a co-located change predicate) *replaces* the 0.35
  score check entirely rather than supplementing it.
- **Original introduction commit**: `2fe129705d824d46b4bcf7f0fc1eb43e27972824`
  ("0.1.1 test", 2026-07-24 17:45:30 -0700, sole author `xiangmao`) — a large
  commit that also introduces `data_sanity/`, the exposure rubric contract,
  and `activation_scorer_v2.py` together; no descriptive commit body.
- **Claimed rationale** (from the module's own docstring, `ai_alpha_discriminator.py:1-19`):
  generic taxonomy keywords ("AI", "cloud", "capex", "data center") are good
  for candidate *recall* but not specific enough for a *formal* match, and
  the factor-weight table's deliberate partial credit across A101/A102/A103
  (e.g. "AI CapEx" contributing to both A101 and A103) is appropriate for
  scoring but not for a hard admission decision — a genuine, articulate
  **engineering** rationale, addressing a real over-triggering problem.
- **Formal approval source**: **none found.** No PD entry, ADR, or spec
  document anywhere in the repository names this gate, `AI_ALPHA_IDS`, or an
  Alpha-specific threshold exception (confirmed by grepping every ADR and
  `product_decisions_and_unknowns.md` for "AI Alpha," "A101," "A102," "A103"
  — zero matches). The gate's own acceptance fixture,
  `tests/fixtures/ai_alpha_mapper_golden_v1.json`, self-describes itself as
  *"the current implementation's acceptance fixture, not a permanent frozen
  contract"* — the artifact itself disclaims being an approved, frozen rule.

**Classification: `UNAPPROVED_IMPLEMENTATION_DETAIL`** — not
`SUPERSEDED_BY_CURRENT_PRODUCT_DECISION`, because that label would imply a
real prior approval is being overridden, and none was ever found to exist.
PD-013 (Part A) now formally rules on this: the future implementation
alignment target is `ALL_10_ALPHAS_USE_0_35_MINIMUM_MATCH_THRESHOLD`. No code
was changed in this task.

---

## Part D — Cardinality audit (§17 of the task)

`SCHEMA_CHANGE_REQUIRED = NO.`

Current code already produces a shape compatible with PD-011 without any
migration:

- `matched_alpha` (singular, nullable) is already the one primary field
  written to both `alpha_matches.json` and the `alpha_matches` DB table's
  `alpha_id` column.
- `secondary_alphas` is already **structurally capped at ≤2** as a
  consequence of existing, unrelated slicing logic — not something that
  needs new capping logic: `plausible_candidates = eligible_candidates[:3]`
  (top 3 max) and `secondary_alphas` is built from `plausible_candidates[1:]`
  (dropping the primary), which can never exceed 2 items. `TOTAL_RETAINED_ALPHA_CANDIDATES
  <= 3` (1 primary + up to 2 secondary) already holds today, for every claim,
  as an emergent property of code written well before this task.
- The DB `alpha_matches` table has no *dedicated* `secondary_alphas` column,
  but its existing `candidate_scores` JSON blob column already carries the
  full candidate list (including what PD-011 calls secondary Alphas) —
  representable without a migration, only a future read-path convenience if
  ever needed. This is noted for completeness, not as a blocking gap.

## Part E — Confidence audit (§18 of the task)

`CLAIM_CONFIDENCE_ROLE = NOT_USED_FOR_ALPHA_RELEVANCE.`

Re-confirmed directly against source: `record.get("confidence")` does not
appear anywhere in `alpha_mapper.py` — not in `keyword_score`, `factor_score`,
`direction_score`, `_candidate_score`'s final blend, or the Tier-2 LLM
request payload. Under PD-012 this is now **intentional, approved behavior**,
not an unresolved omission. No code change required.

## Part F — No-match audit (§19 of the task)

`CURRENT_IMPLEMENTATION_ALIGNS = YES.`

Re-confirmed directly against source: when no candidate clears the 0.35
threshold (`top` is `None` in `map_claim_to_alpha`), the record is retained
in the `matches` list with `match_status="no_match"`, `matched_alpha=None`,
`score=0.0` — never dropped, no fabricated "NONE" Alpha, no forced low-score
admission. This already matches PD-014 exactly. No code change required.

---

## Part G — The two allowed outcomes (§20 of the task)

**`JOHN_GOLD_STATUS = UNVERIFIED_OR_MISSING`** (classification D from B.8 —
self-described as approved, but every independent, checkable source either
says nothing or affirmatively contradicts that self-description).

**`SECTION_5_2_ACCEPTANCE = BLOCKED_BY_PRODUCT_OWNER_GOLD_DATA`** (Outcome B).

No substitute labels were created. `labeled_claims_v1.json` was not used as
official acceptance data in this task. No LLM benchmark was run. The next
required external input is unchanged from PD-005: John's actual approved 20
labeled Claims, a label rubric, a version identity, and a sign-off — now with
PD-011 through PD-016 already resolving every *downstream* product-definition
question that was blocking implementation, so that once the real benchmark
arrives, evaluation can proceed immediately under an already-settled metric
(PD-016).

---

## Required report answers (§23 of the task)

1. **What Product Decisions are now closed?** PD-011 (cardinality), PD-012
   (score semantics / confidence), PD-013 (uniform 0.35 threshold; AI-alpha
   carve-out unapproved), PD-014 (no-match retention), PD-015 (Tier-2
   authority condition), PD-016 (conditional evaluation metric). PD-005 is
   **not** closed.
2. **Is primary Alpha cardinality now explicitly singular?** Yes — PD-011.
3. **Are secondary Alphas allowed, and how many?** Yes, up to two,
   non-authoritative — PD-011.
4. **Does Claim confidence affect Alpha score?** No — PD-012. Already true in code.
5. **Is 0.35 now the universal Product Owner threshold?** Yes, for all 10
   Alphas — PD-013.
6. **Status of the A101/A102/A103 special gate?** `UNAPPROVED_IMPLEMENTATION_DETAIL`
   (Part C); future alignment target is the uniform 0.35 rule.
7. **Approved no-match behavior?** Retain the Claim, `matched_alpha=null` —
   PD-014. Already true in code.
8. **Condition for Tier-2 authority graduation?** Authentic benchmark (PD-005)
   available AND the PD-016 metric reaches ≥80% — PD-015.
9. **Where is `labeled_claims_v1.json`?** `tests/golden_cases/labeled_claims_v1.json`.
10. **How many records?** Exactly 20 (verified programmatically).
11. **Single-label or multi-label?** Single-label (`expected_alpha` is always
    a bare string).
12. **What concrete evidence claims it is John-approved?** Only
    `tests/test_week2_labeled_accuracy.py`'s own module docstring and test
    function name (B.1) — nothing else in the repository.
13. **Is that evidence authoritative?** No — it fails every acceptable-evidence
    category in the task's own §8 standard (B.5).
14. **Is approval tied to the exact current file/version/hash?** N/A — no
    approval event was found to bind to any version (`NO_APPROVAL_FOUND`, B.6).
15. **What does PD-005 currently say?** `BLOCKED_BY_PRODUCT_OWNER`; the real
    20 labeled claims, labels, rubric, version, and sign-off owner are
    required and explicitly not to be substituted (B.7).
16. **Has PD-005 ever been authoritatively closed?** No.
17. **Genuine Product Owner gold or engineering fixture?**
    `SELF_DESCRIBED_AS_APPROVED_BUT_UNVERIFIED` (classification D, B.8) — closer
    in substance to an engineering fixture than to verified gold, but the
    dataset's own explicit "approved"/"Formal" self-description is a real,
    distinguishing fact that makes plain "B" imprecise.
18. **Can the ≥80% benchmark legally/semantically be run now?** No — Outcome
    B applies; running it against this dataset would not constitute the
    Development Plan's actual acceptance gate.
19. **If single-label, is the metric now Top-1 exact ≥16/20?** Yes, as a
    conditional Product Decision (PD-016) for whenever an authentic
    single-label benchmark is supplied — it does not retroactively validate
    today's unverified fixture.
20. **What exact external input is still missing?** John's real 20 labeled
    Claims + label rubric + version identity + sign-off (unchanged from
    PD-005).
21. **Next legitimate §5.2 task?** Either (a) obtain the authentic benchmark
    from the product owner and then run
    `SECTION_5_2_20_CLAIM_ACCEPTANCE_EVALUATION` under PD-011–PD-016, or (b) a
    separate, explicitly-scoped implementation task to align the A101/A102/A103
    gate to the uniform 0.35 threshold per PD-013 (does not require the
    benchmark). Neither is started here.
