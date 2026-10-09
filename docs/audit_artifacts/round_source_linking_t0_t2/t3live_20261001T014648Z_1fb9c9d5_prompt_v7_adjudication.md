# alpha_classifier prompt v6 -> v7: per-sample adjudication and real-verification plan

Scope: John's real T3 Alpha-classification path only (`alpha_classifier`, the
single-claim task used by `map_claim_to_alpha`/`_classify_alpha_with_llm`
and the real `t3live_20261001T014648Z_1fb9c9d5` execution). `alpha_classifier_batch`
(a separate task/call-path, Step 5A execution-capacity repair) is explicitly
NOT touched this round.

All work in this document is offline: zero Provider calls, zero
re-prediction, zero changes to `t3_eval_records.jsonl`, the human review
form, or historical Gold. `outputs/t3_ai_review_comparisons/` and the
samples referenced below are development regression material for this
prompt edit, not a new scored execution.

## 1. Corrected adjudication of the 13 Stage-1 disagreements

Stage 1 = agreement between the real production classifier's own raw
decision (recovered from each real call record's `validated_output`,
*before* any `alpha_mapper.py` post-hoc gate ran) and ChatGPT's AI_REVIEW,
over all 40 samples (27/40 agree, 13 disagree). This is the correct
diagnostic population for prompt adjudication -- the post-gate 35-sample/
12-disagreement view folds in Step 7A/7A.2's own separate, A001-specific
behavior and must not be used to diagnose classifier *prompt* behavior.

Two corrections to the first-pass adjudication, made before finalizing
counts below:

- **Counting error**: the first pass stated "10 of 13" without a
  programmatic recount; the actual count (verified by script against the
  structured verdict list) is confirmed below.
- **Reasoning error on gold-final-077**: the first pass treated "prefer
  A103 over A101 when concrete facility words are named" as if it were an
  *exclusive* requirement (no facility words => A103 disqualified). The
  rule is a tie-breaking *preference* for when such words ARE present; it
  says nothing about what to do in their absence. gold-final-077 was
  reclassified from `MODEL_VIOLATES_FROZEN_RULE` to
  `TAXONOMY_BOUNDARY_AMBIGUOUS` on this basis.

| sample_id | model (raw) | ChatGPT | verdict | basis |
|---|---|---|---|---|
| gold-final-001 | A304 | NONE | MODEL_VIOLATES_FROZEN_RULE | Price-vs-moving-average claim; no valuation-multiple/fundamentals language. A304 requires rich valuation/multiples vs. fundamentals, not price-technical deviation. |
| gold-final-019 | A304 | NONE | MODEL_VIOLATES_FROZEN_RULE | Only rebuts the PEG argument's math; asserts no valuation conclusion. Shares surface word (PEG) without the mechanism. |
| gold-final-041 | A304 | NONE | MODEL_VIOLATES_FROZEN_RULE | Defends a question's legitimacy; never answers it. No valuation conclusion asserted. |
| gold-final-052 | A304 | NONE | MODEL_VIOLATES_FROZEN_RULE | Pure question-framing (risk-reward at current price); no conclusion given. |
| gold-final-079 | A304 | NONE | MODEL_VIOLATES_FROZEN_RULE | Explicit conditional ("could trigger"); rule requires conditional-downside framing be judged by what it asserts is true now. |
| gold-final-085 | A304 | A001 | TAXONOMY_BOUNDARY_AMBIGUOUS | Multi-mechanism claim bundling a causal driver (rate hike/no-cuts, A001) with its own stated valuation consequence (29x PE repricing, A304). No taxonomy priority rule for this case. |
| gold-final-077 | A103 | A101 | TAXONOMY_BOUNDARY_AMBIGUOUS | **Corrected.** "AI capex spending" is genuinely ambiguous between infrastructure build (A103) and accelerator/compute demand (A101) on its own words; the facility-word rule is a tie-break preference, not a requirement, so its absence does not by itself disqualify A103. |
| gold-final-127 | A103 | A501 | MODEL_VIOLATES_FROZEN_RULE | The claim's own stated main proposition (after the contrastive "but") is that recession risk is low -- direct A501 engagement. A103 is not substantively engaged at all (no infrastructure content, not even ambiguously) -- independent of the facility-word rule. |
| gold-final-144 | A103 | NONE | MODEL_VIOLATES_FROZEN_RULE | Text never mentions AI/datacenter/compute -- generic PPE/infrastructure growth. Selecting A103 risks inferring AI-relevance from the GOOGL ticker rather than judging from the evidence's own words. |
| gold-final-030 | A001 | NONE | MISSING_CONTEXT | "this repricing" has no antecedent in the extracted text; the rule requires defaulting to NONE when the evidence doesn't state the specific mechanism. |
| gold-final-048 | A301 | NONE | MODEL_VIOLATES_FROZEN_RULE | Only sets up a rebuttal ("let me challenge that with the actual trajectory") -- the trajectory/data is never given. No revenue/EPS trend asserted, only promised. |
| prod-run-014 | A003 | NONE | MODEL_VIOLATES_FROZEN_RULE | Index-inclusion-driven passive inflow is mechanical/structural, not macro liquidity improving risk appetite. Shares surface word "inflows" without the mechanism. |
| prod-run-015 | A003 | NONE | MODEL_VIOLATES_FROZEN_RULE | Same mechanism mismatch as prod-run-014 -- forced passive-fund buying is mechanical, not a liquidity/risk-appetite claim. |

**Corrected counts (computed from the table above, not hardcoded)**:
`MODEL_VIOLATES_FROZEN_RULE` = 10, `TAXONOMY_BOUNDARY_AMBIGUOUS` = 2,
`MISSING_CONTEXT` = 1. Total = 13.

ChatGPT's AI_REVIEW is not treated as Gold anywhere in this adjudication --
each verdict above is grounded in the frozen `alpha_classifier` instruction
text and the Alpha taxonomy's own definitions, independently of which side
ChatGPT happened to pick.

## 2. Why no new deterministic code gate was built this round

10 of the 13 disagreements cluster into patterns (question/rebuttal-setup
treated as a conclusion; price-technical claims treated as valuation
claims; bare "AI capex" phrasing treated as sufficient for A101/A103;
mechanical passive flows treated as macro liquidity) that are properties of
the classifier's *prompt-following behavior at inference time*, not a
mechanical, deterministic code defect in `alpha_mapper.py`/
`claim_semantics.py` the way the earlier A001 negation-scope regex bug was.
`A304`/`A101`/`A103`/`A301`/`A003` have no existing post-hoc deterministic
gate analogous to A001's Step 7A/7A.2 (confirmed: `ALPHA_SPECIFIC_
INVALIDATION_PATTERNS`/`ALPHA_POSITIVE_REQUIREMENT_CLASSIFIERS` register
only `"A001"`; `ai_alpha_discriminator.py`'s A101/A102/A103 hard gates feed
only the deterministic/counterfactual scoring path, never a post-hoc
override of the LLM's own selection). Building one now, from 13 data
points concentrated on one Alpha, would lack the audit rigor that justified
the existing A001 gates (a dedicated residual audit finding 0/29 genuine
positive matches) and risks exactly the kind of narrow, under-validated
rule the task explicitly warned against. The corrective action taken this
round is therefore a **prompt-text change**, not a new code gate.

## 3. Prompt change: what, why, and the real diff

File: `comqutor_alpha/structure_engine/week2_llm.py`,
`_TASK_INSTRUCTIONS["alpha_classifier"]` and
`_TASK_RUNTIME_METADATA["alpha_classifier"]`.

- Old version: `week2.alpha_classifier.v6`.
  Raw-instruction-text sha256: `d53b2d7511f4c4a8089db746d09e4c79cb38f22597dac6459920ca3deac1171d`.
  Full `Week2LLMGateway.prompt_identity_sha256` (includes the shared
  JSON-only prefix/separator): `bb2dbdf0f3fc9a43291233494c2f355275b4fe6fddc71cd63fd1377f9ba109d9`
  -- this is the exact value recorded in `t3live_20261001T014648Z_1fb9c9d5`'s
  own `freeze_identity.json`, confirming v6 is the real historical prompt
  this adjudication is based on.
- New version: `week2.alpha_classifier.v7`.
  Full `Week2LLMGateway.prompt_identity_sha256`:
  `ac48723f15cf347590ad2cb175f76cd438dbc4181c7b781aa0cfffaafe589b95`.
- `output_schema_version` unchanged (`week2.alpha_classifier.output.v3`):
  the JSON response shape (`decision`/`selected_alpha_id`) is unchanged;
  only the reasoning instructions that produce it changed.
- `input_schema_version` unchanged (`week2.alpha_classifier.input.v2`):
  the request payload shape is unchanged.
- Full diff: `docs/audit_artifacts/round_source_linking_t0_t2/alpha_classifier_prompt_v7_diff.patch`.

Five additive clarifications, each traced to a specific verdict above:

1. **Proposition-identification step** (new, first sentence): requires
   identifying whether the Evidence states the author's own conclusion, a
   quoted/reported view, a question, an unsubstantiated rebuttal setup, or
   an unmet conditional -- before classifying at all. Targets
   gold-final-019/041/052/048.
2. **Opposition still counts as engagement**: explicit statement that
   substantively opposing an Alpha still means selecting it, not
   decision=none. Clarifies (does not change) the existing "supports or
   opposes" rule.
3. **A304 price-vs-valuation clause**: distinguishes price-vs-own-history
   (technical) claims from valuation-vs-fundamentals claims; states a
   valuation-sounding word alone (PEG/valuation/compression) is not
   sufficient. Targets gold-final-001/019/079.
4. **A101/A103 tie-break-not-requirement clause**: makes explicit that the
   existing facility-word list is a preference for when such words ARE
   present, never a requirement whose absence disqualifies A103 or
   defaults to A101. Targets gold-final-077, and corrects the exact
   reasoning error this document's own first pass made.
5. **A003 mechanical-flow clause**: distinguishes broad macro liquidity
   conditions from mechanical, index-event-driven passive/forced flows.
   Targets prod-run-014/015.

No sample_id, no real claim text from any frozen evaluation pool, and no
answer key is embedded in the prompt -- all illustrative examples are
generic/invented. The taxonomy, every quality threshold, every downstream
eligibility rule, the model, and the response contract are unchanged. No
new classification-time regex veto gate was added anywhere in this round's
work (the earlier A001 negation-scope fix was a separate, already-completed
and already-tested change to an *existing* gate, not a new one, and is
unrelated to this prompt edit).

## 4. Real-wiring verification (what was actually checked)

`tests/test_week2_llm.py::test_alpha_classifier_v7_prompt_reaches_the_real_serialized_request`
drives a call through the real `build_server_week2_llm_gateway` ->
`Week2LLMGateway.invoke_json` -> real `DeepSeekChatOpenAI` ->
`httpx.MockTransport` path (the same path used to verify the earlier
max_tokens/field-mapping fix) and asserts the real serialized outgoing
request body's prompt text contains v7's new clauses verbatim and no
longer contains v6's superseded opening sentence, with no real sample_id or
claim text leaked in. This proves **wiring**: the edited prompt reaches the
real request. It does **not** prove, and is not claimed to prove, any
change in classification accuracy -- that requires a real Provider call,
which this round does not make.

`tests/test_candidate3_alpha_classifier_guardrail.py` (existing
version-collision/guardrail-presence test file, extended this round):
confirms the v6 guardrail clauses survive verbatim into v7, the five new
v7 clauses are present in the single prompt and deliberately absent from
the untouched batch prompt, and the new `week2.alpha_classifier.v7` version
string and prompt hash do not collide with v3, v4, v5, or v6.

Targeted suites run, all passing except one already-known, pre-existing,
unrelated failure (`alpha_mapper.py`'s frozen-hash check, confirmed via
`git stash` to fail identically before this round's changes):
`tests/test_week2_llm.py` (17 passed, 1 pre-existing skip),
`tests/test_candidate3_alpha_classifier_guardrail.py` (7 passed),
`tests/test_qqq_a001_mapping_remediation.py` (62 passed),
`tests/test_t3_diagnostic_evaluation_driver.py` (44 passed),
`tests/test_t3_joint_verification_driver.py` (5 passed), plus a broader
`alpha_mapper or alpha_classifier or t3_diagnostic or t3_joint or
qqq_a001 or week2_llm` sweep (355 passed, 1 pre-existing failure, 1
pre-existing opt-in-skip).

## 5. Remaining ambiguities (not resolved this round, flagged for a product decision)

- **gold-final-085 pattern**: no taxonomy priority rule exists for a claim
  that states a causal driver (e.g. a rate move) and its own stated
  valuation consequence (a specific multiple) in the same sentence, when
  the causal Alpha (A001) and the consequence Alpha (A304) are both
  real candidates.
- **gold-final-077 pattern**: "AI capex/spending" alone, with no facility
  words and no clearer accelerator-vs-infrastructure signal, remains a
  genuine A101-vs-A103 judgment call this round's prompt edit does not
  attempt to resolve mechanically (deliberately -- see Section 2).

## 6. Limited real-verification plan and request budget (NOT executed this round)

This round makes zero Provider calls. If and when authorized separately:

1. **Wiring-only smoke** (already technically covered offline, but a real
   single live call would confirm the real Provider accepts and responds
   coherently to the longer v7 prompt): 1 real request, 1 retry max, a
   single generic development claim (not from the frozen 40-sample pool),
   to confirm the real Provider doesn't reject the longer prompt or change
   its JSON-shape compliance behavior.
2. **Targeted re-classification of the 13 disagreement samples only**
   (reusing the frozen 40-sample pool's own claim text and ticker, with the
   v7 prompt, under the SAME configuration -- provider, model, timeout --
   as the original execution): up to 13 real requests + up to 1 retry each
   (budget ceiling 26 actual requests), to see whether v7 changes the raw
   classifier decision on exactly the samples this adjudication is about.
   This does NOT re-run the full 40-sample pool and does NOT compute or
   report any new "accuracy" or "agreement rate" -- it only observes
   whether each of the 13 raw decisions changes, saved as its own
   independent execution_id, never overwriting
   `t3live_20261001T014648Z_1fb9c9d5`'s own records.
3. If (2) shows a material shift, a FULL real re-run of the 40-sample pool
   under v7 (same budget discipline as the original authorized run: real
   request/retry ceiling, independent execution_id, predict-only, human
   review and offline scoring afterward) would be the next, separately
   authorized step -- not performed or assumed here.

Total requested budget for steps 1-2 combined: **at most 27 real requests
including retries** (1 + 26), zero model/taxonomy/threshold changes, zero
prompt changes mid-run. Awaiting explicit authorization before any of this
executes.
