# v0.2 Alpha Human Adjudication Rubric

**Purpose.** This rubric governs how an independent adjudicator (human, or a separate blinded LLM reviewer session per the fallback order in `v0_2_new_alpha_holdout_creation_plan.md`) assigns Gold Alpha labels to the 100-sample development packet (`v0_2_alpha_dev_adjudication_packet.json/.md`) and, later, to the sealed 150-sample final independent set. This document does **not** change any taxonomy definition, does **not** add any new Alpha ID, and does **not** modify the production Alpha prompt. It only defines how a human reads the existing canonical taxonomy and existing claim/evidence text and produces a label.

**No system output is ever shown to the adjudicator.** The adjudicator sees only: `sample_number`, `ticker`, `run_id` (as opaque provenance, not a hint), `claim`, `evidence`, and the full canonical Alpha taxonomy (`alpha_id`, `name_en`, `core_thesis` for every Alpha currently defined in `comqutor_alpha/alpha_library/alpha_taxonomy_v1.yaml`). The adjudicator never sees COMQUTOR's own predicted Alpha, confidence, mapper score, explanation, or any prior system decision for that sample, in this run or any historical run.

## 1. The Core Question

For each sample, answer exactly one question:

> "Does this Evidence materially, substantively engage exactly one canonical Alpha's own thesis/mechanism? If yes, which one, and how confidently? If no single canonical Alpha is materially engaged, answer NONE."

"Materially engage" means the evidence text itself — not inference, not speculation about what the company or analyst *probably* meant — states or clearly implies a fact pattern that is a direct instance of that Alpha's `core_thesis`. A topical mention of a keyword associated with an Alpha (e.g., mentioning "AI" without describing capacity, revenue, or infrastructure buildout) is not sufficient on its own — this mirrors the same "a bare figure or keyword is never sufficient by itself" principle already built into the production prompt, and adjudicators should apply it the same way: the evidence must describe the *mechanism*, not just reference a topic adjacent to it.

## 2. Sufficient Evidence Criteria

Label a sample `selected` (assign a specific `alpha_id`) only when **all** of the following hold:
1. The evidence text names or clearly describes a concrete driver, event, or data point (not just a topic word).
2. That driver directly instantiates the mechanism described in one Alpha's `core_thesis` — reread the thesis text itself, not just its name, before deciding.
3. No other canonical Alpha's thesis is engaged equally well or better by the same evidence (see Section 3, neighboring-Alpha discrimination).
4. The evidence is not merely restating background/context that could apply to almost any company in the sector (e.g., "semiconductor demand is generally strong" without a specific claim tied to this company's own fundamentals, guidance, or disclosed metrics).

If any of the four fail, the correct label is `NONE`, not a best-guess selection.

## 3. Neighboring-Alpha Discrimination

Several canonical Alphas describe adjacent or sequential mechanisms (e.g., an infrastructure buildout Alpha vs. a downstream revenue-expansion Alpha vs. a valuation/multiple-compression Alpha that can be triggered by the same underlying event from the opposite direction). When evidence plausibly touches more than one Alpha:
- Identify which Alpha's thesis the evidence engages **most directly and specifically** — not which Alpha is merely topically adjacent.
- If the evidence describes a *cause* (e.g., capacity/infrastructure buildout) without describing the *effect* the adjacent Alpha requires (e.g., realized revenue growth), label the cause-side Alpha only, not both and not the effect-side Alpha.
- If the evidence genuinely, irreducibly supports two Alphas with no basis to prefer one (not merely "I'm not sure"), do not force a single answer — mark it per Section 5 (Ambiguous Cases) instead of guessing.
- Consult each candidate Alpha's registered `conflict`/`counter` relationships (present in the taxonomy YAML) as a tie-breaking aid, but the deciding factor is always the evidence text itself, never the taxonomy's relationship metadata alone.

## 4. Use of NONE

`NONE` is a first-class, correct answer — never a fallback for "I couldn't decide." Use `NONE` when:
- The evidence is generic sector/market commentary not tied to a specific mechanism.
- The evidence states an outcome (e.g., a stock price move, an analyst rating) without stating the underlying driver.
- The evidence negates or rebuts a thesis without asserting a different one in its place (a pure negation is not automatically the "opposite" Alpha — check whether the opposite Alpha's own thesis is actually asserted, not just implied by the negation).
- The evidence is too vague, incomplete, or fragmentary to support any specific mechanism claim (truncated quotes, ambiguous pronouns with no clear referent, etc.).

Do not use `NONE` merely because a sample is hard — use the `NEEDS_SECOND_OPINION` ambiguity flag (Section 5) for genuine difficulty, and reserve `NONE` for cases where the adjudicator is confident no single Alpha is materially engaged.

## 5. Ambiguous or Invalid Cases

Mark a sample's `ambiguity_flag` (rather than forcing a `NONE`/`selected` answer) when:
- **`BOTH_REASONABLE_AMBIGUOUS`** — two Alphas are each independently well-supported by the same evidence with no textual basis to prefer one.
- **`INSUFFICIENT_CONTEXT`** — the evidence is truncated, cut off mid-sentence, or depends on referents not present in the given claim/evidence pair.
- **`NOT_A_SUBSTANTIVE_CLAIM`** — the text is boilerplate, a disclaimer, a question, or otherwise not an assertion capable of engaging any Alpha thesis at all.
- **`DUPLICATE_OR_NEAR_DUPLICATE`** — the adjudicator recognizes the sample as a near-duplicate of another sample already seen in this same packet.

A sample flagged under any of these is excluded from the accepted scoring population for whichever set it belongs to and, where a replacement is needed, is drawn from the 50-item reserve set (see `v0_2_new_alpha_holdout_split.json`) using the same deterministic sampling discipline, not hand-picked.

## 6. Multi-Signal Handling

Some evidence strings contain more than one factual claim (e.g., a quarter's earnings summary covering both revenue and cost commentary). Adjudicate based on the specific `claim` field paired with that `evidence` — the claim field identifies which assertion within the evidence is under review. Do not average or combine multiple signals into one softened label; if the claim field's specific assertion doesn't materially engage an Alpha even though other parts of the evidence text might, the correct label is still governed by the claim under review, and other content in the evidence string is context only.

## 7. Exclusion Criteria (Before Labeling)

A sample should have already been filtered out upstream (per `v0_2_alpha_validation_leakage_audit.md`'s eligibility filter) if it is a placeholder, non-substantive, or under 15 characters of normalized text. If an adjudicator nonetheless encounters such a sample, mark `ambiguity_flag: NOT_A_SUBSTANTIVE_CLAIM` rather than guessing a label, and note it in `adjudication_reason` so it can be swapped from the reserve set.

## 8. Use of Source Context

`ticker` and `run_id` may be shown for provenance/traceability only. They must **never** be used as a basis for inferring the label (e.g., "this is NVDA so it's probably an AI Alpha") — the label must be justifiable from the `claim`/`evidence` text alone. An adjudicator who cannot justify a label using only the claim/evidence text should not assign that label based on ticker-driven intuition.

## 9. Explicit Prohibition — No System Output During Labeling

At no point during adjudication may the adjudicator view, query, or otherwise access:
- COMQUTOR's own `matched_alpha_id`, candidate scores, or `plausible_alphas` for the sample being labeled, from any run, past or present.
- The production Alpha prompt's own worked examples, if those examples happen to reuse a similar phrasing (adjudicators should label from the taxonomy's `core_thesis` definitions, not from the prompt's illustrative examples).
- Any COMQUTOR-generated explanation or rationale text for the sample.

This rubric exists precisely so that the resulting Gold labels are independent of the system under test. Violating this prohibition for any sample invalidates that sample's label and requires it to be redrawn from the reserve set.

## 10. Required Fields Per Adjudicated Sample

For each sample, the adjudicator records exactly:
- `expected_label`: one canonical `alpha_id`, or `NONE`.
- `confidence`: `low` / `medium` / `high`.
- `ambiguity_flag`: one of the Section 5 values, or `null` if not applicable.
- `adjudication_reason`: a short free-text justification quoting or paraphrasing the specific part of the evidence text that supports the label (required even for `NONE`, to distinguish a considered `NONE` from an unconsidered skip).

No other field may be added, and no taxonomy definition may be edited as part of this process.
