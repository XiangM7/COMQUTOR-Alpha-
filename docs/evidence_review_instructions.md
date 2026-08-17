# Evidence Stance Human Review — Reviewer Instructions

This document accompanies `evidence_review_sample.csv` (50 rows, stratified
across NVDA / QQQ / MSFT / SNDK / TSM / AMD). Each row is one
**(claim, target Alpha)** pair, already classified by COMQUTOR's
deterministic Evidence Stance classifier
(`comqutor_alpha/structure_engine/evidence_stance.py`,
`evidence_stance.deterministic.v1`). Your job is to independently judge
whether the machine's classification is correct — **not** to reproduce the
machine's reasoning.

## 1. The five stances

| Stance | Meaning |
|---|---|
| `supports_alpha` | The evidence directly supports the target Alpha's core thesis, trigger, or confirmation signal. |
| `opposes_alpha` | The evidence explicitly rebuts, invalidates, or relieves the target Alpha's thesis. |
| `mentions_alpha` | The evidence names the target Alpha's topic but asserts nothing that supports or opposes it (e.g. "management discussed X during the call"). |
| `neutral_background` | Generic industry/company background with no target-specific claim at all. |
| `supports_counter_alpha` | The evidence does **not** support the target Alpha, but clearly supports a *different* Alpha that is a declared conflict partner of the target (see `counter_alpha_id`). |

A single claim can have a **different** stance for each Alpha it is
evaluated against — that is expected and correct, not a bug. Columns
`target_alpha_id` and `matched_alpha_id` tell you which Alpha the row's
stance is *about* versus which Alpha the claim was actually matched to.

## 2. How to fill in the reviewer columns

Only these columns are yours to fill in — every other column is
machine-generated context, read-only:

- `reviewer_expected_stance` — one of: `supports_alpha`, `opposes_alpha`,
  `mentions_alpha`, `neutral_background`, `supports_counter_alpha`,
  `unclear`.
- `reviewer_counter_alpha_id` — only fill in if your expected stance is
  `supports_counter_alpha`; otherwise leave blank.
- `reviewer_should_be_admissible` — **not** the same question as stance.
  This asks: if a future Conflict-admissibility gate existed (not yet
  built — see limitations below), should this piece of evidence be
  allowed to count as Bull/Bear evidence for its side? One of: `yes`,
  `no`, `conditional`, `unclear`.
- `reviewer_confidence` — your own confidence in your judgment: `high`,
  `medium`, `low`.
- `reviewer_notes` — free text. Please use this whenever you disagree with
  the machine, and especially whenever the `claim`/`evidence` text is
  genuinely ambiguous.
- `review_status` — leave as `pending` until you are done with the row,
  then set to `reviewed`.

**Do not** infer your answer from `evidence_stance`,
`stance_reason_codes`, or `stance_confidence_band` — read the `claim` and
`evidence` text yourself first, form your own judgment, *then* compare.

## 3. `counter_alpha_id` filling rule

Only set `reviewer_counter_alpha_id` when you independently believe the
evidence supports a *different*, specific Alpha that legitimately
conflicts with the target Alpha (check `matched_alpha_id`/
`matched_alpha_name` for the machine's own answer, but verify it yourself
against the claim text — is the evidence really about that other Alpha's
thesis, not just superficially similar wording?).

## 4. Admissibility is not decided by this Sprint

**Important:** `reviewer_should_be_admissible` is a data-collection
question for a *future* Sprint (B2 — Conflict Evidence Admissibility). Your
answer here does **not** change how any current run scores, admits, or
suppresses a conflict. Nothing in this review process is wired back into
production scoring yet.

## 5. Mixed / conditional evidence

Some rows have `evidence_stance = neutral_background` with
`stance_reason_codes` containing `MIXED_STANCE_UNRESOLVED`, or
`evidence_stance = supports_alpha`/`opposes_alpha` with
`CONDITIONAL_SUPPORT`/`CONDITIONAL_OPPOSITION`. These are cases the
machine flagged `requires_manual_review = True` precisely because the
claim contains **both** a supporting and an opposing signal, or is
phrased as a hypothetical ("if X accelerates, Y could improve"). For these:

- If you can determine a clear dominant stance, set
  `reviewer_expected_stance` to that stance and explain your reasoning in
  `reviewer_notes`.
- If you genuinely cannot determine a dominant stance, set
  `reviewer_expected_stance` to `unclear` rather than guessing.

## 6. Reviewer must not decide by keyword alone

Do not classify a row based on the mere presence of a keyword (e.g.
"valuation risk", "recession", "priced in"). John's own fixed test case
illustrates why:

> **Claim:** "The valuation risk argument is a lazy heuristic that ignores
> the actual numbers."
> **Target Alpha:** A304 (Multiple Compression / valuation risk)
>
> The sentence *contains* the phrase "valuation risk" — but it is a
> **rebuttal** of the valuation-risk argument, not an assertion of it. The
> correct stance is `opposes_alpha`, not `supports_alpha`. Read the full
> sentence's meaning, never just scan for topic keywords.

## 7. Handling reviewer disagreement

If a second reviewer disagrees with a first reviewer's row:

1. Both reviewers' `reviewer_notes` are preserved (do not overwrite —
   coordinate a merged note, or note both readings explicitly:
   "Reviewer A: ...; Reviewer B: ...").
2. Escalate genuinely disputed rows to John for a tie-break rather than
   silently picking one reading.
3. A disagreement is not evidence of a classifier bug by itself — check
   whether the disagreement is about the *stance* (classifier's job) or
   about *admissibility* (not yet built, inherently a matter of judgment).

## 8. What this review is for

This 50-row sample is an **engineering validation checkpoint**, not a
statistically representative accuracy benchmark. It exists to surface
whether the classifier's *categories and reasoning* make sense to a human
domain expert before any future Sprint is allowed to consume
`evidence_stance` for admissibility decisions. Until John reviews these
rows, the classifier's semantic accuracy remains **PENDING** — the
engineering implementation being complete and tested is a separate,
already-verified claim (see
`docs/evidence_stance_and_review_sample_report.md`).
