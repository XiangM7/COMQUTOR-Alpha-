# B1 LLM Evidence Stance Upgrade — Implementation and Validation Report

Status: **Implementation complete, offline-tested, and validated against the
existing 50-row sample with exactly 5 real Provider attempts (0 retries,
sequential).** HEAD unchanged at `b5837e80a4550fc35165d0013a8ef0f27ccb4c8f`
throughout. No commit, no push.

## A. Exact previous B1 live call path

`alpha_mapper.map_claim_to_alpha()` → `_attach_evidence_stance(candidates,
stance_record, taxonomy)` → `evidence_stance.classify_evidence_stance(...)`
(`evidence_stance.deterministic.v1`), called once per (claim, candidate
Alpha) pair, purely deterministic (regex/relation/quality-class rules), zero
Provider calls ever, unconditionally for every candidate in `stance_scope`.

## B. Exact new B1 live call path

Unchanged entry point (`map_claim_to_alpha`/`_attach_evidence_stance`) still
runs first and unconditionally — it is the only thing that ever computes a
candidate's *starting* stance. `alpha_mapper.build_alpha_matches_payload()`
now additionally calls, once per run, after all claims are mapped:

```
build_alpha_matches_payload
  -> map_structured_records(...)          # unchanged: deterministic stance
                                           #  on every stance_scope candidate
  -> evidence_stance_llm.apply_llm_stance_upgrade(matches, taxonomy,
                                                   llm_gateway=llm_gateway)
       -> build_stance_request_items      # retained scope only (<=3/claim)
       -> chunk_items(size=10)
       -> per batch: llm_gateway.invoke_json_with_trace(
              "evidence_stance_classifier", {"items": [...]}, validate_batch_shape)
          -> per item: identity/vocabulary/counter-Alpha legality check
          -> accepted  -> overwrite candidate's stance fields, stance_method="llm"
          -> rejected  -> leave the already-correct deterministic value,
                          stance_method="deterministic_fallback"
```

When `llm_gateway is None` (every existing caller's default, and
Architecture Replay's own call site, which never passes one) this entire
step is a proven zero-cost no-op — `matches` is left byte-identical to what
`map_structured_records` already produced.

## C. Where the LLM call is made

Exactly one place: `evidence_stance_llm._process_batch()`, via
`llm_gateway.invoke_json_with_trace(LLM_TASK_NAME, payload,
_validate_batch_shape)` — the same `Week2LLMGateway` method
`alpha_mapper.py`'s existing Tier-2 `alpha_classifier` already uses. No new
Provider client, no new HTTP layer, no new retry loop.

## D. Existing Week2LLMGateway functionality reused

- The shared `Week2LLMGateway` class itself (retry/timeout/per-run call
  budget, `_reserve_call()` enforcement).
- `invoke_json_with_trace` (cache lookup, prompt construction, provider
  invocation, JSON strictness, error classification) — unchanged.
- `finalize_semantic_invocation` (semantic-runtime cache/replay
  bookkeeping) — called exactly as the existing 3 tasks call it.
- The fixed `_TASK_INSTRUCTIONS` / `_TASK_RUNTIME_METADATA` task-registration
  tables — the intended, existing extension point (the same one
  `alpha_classifier` itself was added through); one new entry,
  `evidence_stance_classifier`, added. No parallel prompt-management system.
- `prompt_identity_sha256` / prompt-version identity — computed
  automatically from the new instruction text via the existing mechanism.

**Nothing new was built at the Provider layer.** `NEW_PROVIDER_CLIENT_CREATED = NO`.

## E. Exact LLM input contract

Per item (task spec section 9), and *only* these fields:

```
claim_id, target_alpha_id, ticker, claim, evidence,
target_alpha_name, target_alpha_definition,
counter_alphas: [{alpha_id, name, definition}]  (only if the target Alpha has canonical conflicts),
factors  (only if already non-empty on the record; never newly extracted)
```

Explicitly and verifiably excluded (proven by
`test_request_payload_excludes_forbidden_fields`, which inspects the actual
built payload keys): the existing deterministic stance, its reason codes,
`relation`, `keyword_score`/`factor_score`/`direction_score`, activation/
conflict score, any candidate id, any source offset. `counter_alphas`
sourced exclusively from `evidence_stance.canonical_conflict_partners` — the
taxonomy's own `conflict_alphas` registry, never a second one.

## F. Exact output contract

```json
{"items": [{"claim_id": "...", "target_alpha_id": "A304", "stance": "opposes_alpha", "counter_alpha_id": null}]}
```

`stance` ∈ the unchanged five-value `VALID_EVIDENCE_STANCES`.
`counter_alpha_id` required and canonical-conflict-validated only when
`stance == "supports_counter_alpha"`; otherwise ignored/normalized to
`None` by the program (not a rejection condition — task spec section 12 vs
13 distinguishes an output-shape *preference* from a validation *rule*, and
only the latter is enforced). No confidence, score, reasoning chain, offset,
or new reason taxonomy requested or accepted.

## G. Exact deterministic validation rules (program = contract authority only)

1. **Identity**: returned `claim_id` and `target_alpha_id` must equal the
   requested pair exactly.
2. **Vocabulary**: `stance` must be exactly one of the five existing values
   (`evidence_stance.VALID_EVIDENCE_STANCES`, reused, not duplicated).
3. **Counter-Alpha legality**: `supports_counter_alpha` requires a present
   `counter_alpha_id` that is a canonical conflict partner of
   `target_alpha_id` per the taxonomy (`canonical_conflict_partners`,
   reused, not a second registry).
4. **Duplicate/missing**: each requested pair admits at most one usable
   result; a duplicate return for the same pair, or no return at all, falls
   that one pair back — never the whole batch.
5. **Extra results**: any returned item for a pair that was never requested
   is silently ignored — never admitted, never creates anything.

The validator never asks whether the stance "sounds right," "agrees with
deterministic.v1," or "is strong enough" — confirmed by direct code
inspection of `_validate_response_item` (task spec section 14) and by
`test_1_valid_llm_stance_is_authoritative_over_disagreeing_deterministic`.

## H. Exact fallback conditions

Fallback is per `(claim_id, target_alpha_id)`, never per batch, **except**
when the response isn't even parseable as `{"items": [...]}` at all — there
is no way to salvage per-item results from an unparseable shape, so that
one condition necessarily falls back every item in that batch. Reason
vocabulary (exactly 8, matching task spec section 16):
`provider_error, timeout, malformed_response, missing_result,
identity_mismatch, invalid_stance, invalid_counter_alpha, duplicate_result`.
A bug/unexpected exception anywhere in batch handling is also caught and
treated as `provider_error` for that whole batch — fail-soft, never a
crashed research run (task spec section 15).

## I. Confirmation: deterministic.v1 was not semantically rewritten

`comqutor_alpha/structure_engine/evidence_stance.py`'s `classify_evidence_stance`
function body is **byte-identical** to before this task. The only change to
that file is a single **pure rename** (`_canonical_conflict_partners` →
public `canonical_conflict_partners`, its one internal call site updated to
match) so the new module can reuse the exact same canonical-conflict lookup
instead of building a second one — zero behavioral change, confirmed by the
existing, untouched, 77+ deterministic-classifier tests
(`tests/test_evidence_stance_classifier.py`) all still passing verbatim.

## J. Batch size

`BATCH_SIZE = 10`. Enforced by `chunk_items`, proven by
`test_14_batch_size_is_capped_at_ten` (23 synthetic items → batches of
`[10, 10, 3]`) and empirically by the real 50-row run (exactly 5 batches of
10, `50 / 10 == 5` exactly matching `MAX_LOGICAL_PROVIDER_CALLS`).

## K. Offline test results (0 Provider calls)

`tests/test_evidence_stance_llm.py`: **27/27 passed**, covering every
required scenario from task spec section 20 (1–18, all present) plus the
retained-scope cardinality rule, the section-9 forbidden-field exclusion,
full-stack wiring through `build_alpha_matches_payload`, and the
audit-extraction path. Focused regression
(`test_evidence_stance_llm.py`, `test_evidence_stance_classifier.py`,
`test_evidence_stance_integration.py`, `test_alpha_mapper*.py`,
`test_ai_alpha_mapper_discrimination.py`, `test_artifact_export_and_api.py`,
`test_agent_outputs_persistence.py`, `test_week2_labeled_accuracy.py`):
**292/292 passed**. Full offline suite
(`python -m pytest -m "not integration"`): **3218 passed**, 1 pre-existing,
unrelated failure (see below), 1 skipped (missing optional dependency,
pre-existing), 47 deselected. Ruff: clean on every touched file.

**One test required an update, with documented justification**:
`tests/structured_output_shadow/test_phase1b1_boundaries.py::
test_existing_three_task_instructions_text_unchanged` asserted the shared
gateway's task registry contained *exactly* the original three tasks. Its
own module docstring states its actual purpose: proving Phase 1B.1's own
work added zero new tasks and never leaked `"structured_claim_shadow"` into
the registry. That invariant (the second assertion,
`"structured_claim_shadow" not in _TASK_INSTRUCTIONS`) is untouched and
still holds. The set-equality assertion was updated to include
`evidence_stance_classifier` — a legitimate, later, separately-authorized
addition through the exact same intended extension point every prior task
used, not a Phase 1B.1 boundary violation.

**One pre-existing, unrelated failure, confirmed to predate this task**:
`tests/structured_output_shadow/test_source_integrity.py::
test_current_semantic_components_match_approved_phase1_master_baseline`
compares 4 files' SHA-256 against a hardcoded "approved baseline." Verified
via `git show HEAD:...`: `alpha_mapper.py`'s own **committed** HEAD version
already doesn't match this test's hardcoded baseline either — a third,
different hash — proving the drift predates this task entirely (from
earlier sessions' uncommitted work on this long-running branch, unrelated
to B1). This task's edits to `alpha_mapper.py`/`week2_llm.py` shift two
already-wrong hashes to two different already-wrong hashes; they do not
introduce a new failure category. Refreshing this baseline is a separate,
deliberate maintenance action, out of this task's narrow scope, and was not
performed.

## L. Replay zero-Provider result

`comqutor_alpha/replay/pipeline.py:421` calls
`build_alpha_matches_payload(structured)` — positional only, no
`llm_gateway` keyword at all, so it receives the default `None` and the B1
LLM path never activates. Proven three ways: (1) direct inspection of that
call site (unchanged by this task); (2)
`test_18b_build_alpha_matches_payload_replay_call_shape_makes_zero_calls`,
which calls `build_alpha_matches_payload` exactly the way Replay does; (3)
the pre-existing
`test_43_44_45_replay_uses_replay_run_id_and_zero_provider_calls`
(`tests/test_evidence_stance_integration.py`) — a real Architecture Replay
of a real source run — still passes unmodified, still asserting
`llm_provider_calls == 0`. `REPLAY_PROVIDER_CALLS = 0`.

## M. 50-row Provider call count

`LOGICAL_PROVIDER_CALLS = 5`, `REAL_PROVIDER_ATTEMPTS = 5`, `RETRIES = 0`,
sequential (5 batches, no concurrency anywhere in the batch loop). The
gateway was constructed with `max_retries=0` and `max_calls=5` — a **hard,
enforced** budget (`Week2LLMGateway._reserve_call()` refuses any call past
the 5th), not merely a soft script-level check. Provider/model: `anthropic`
/ `claude-sonnet-4-6` (the repository's existing, named
`comqutor_anthropic_medium_sonnet46_v1` research profile — the same
Provider/runtime configuration production COMQUTOR semantic tasks already
use; no new credential or endpoint).

## N. 50-row stance distribution (final, after upgrade)

| Stance | Count |
|---|---|
| supports_alpha | 22 |
| opposes_alpha | 12 |
| mentions_alpha | 6 |
| neutral_background | 6 |
| supports_counter_alpha | 4 |

## O. Fallback count / reasons

`LLM_VALID_RESULT_COUNT = 20`, `DETERMINISTIC_FALLBACK_COUNT = 30`. **Every**
fallback (30/30) was `malformed_response`; all other 7 reason codes
occurred 0 times. Root cause, confirmed via
`outputs/runs/b1-llm-stance-50-validation/error_logs/week2_llm_errors.jsonl`:
all 3 failed batches recorded `WEEK2_LLM_INVALID_JSON` — the raw response
text failed strict `json.loads` before this module's own validator ever
ran. This codebase has already identified and solved exactly this failure
class once before: `structured_output_shadow_provider.py`'s
`_MarkdownFenceStrippingModel` exists specifically because "a whole-response
markdown code fence around otherwise-valid JSON" can wrap a real Anthropic
response despite an explicit "no markdown" prompt instruction — but that
fix is scoped only to the separate `structured_claim_shadow` gateway
construction path, never applied to the shared `Week2LLMGateway`/named-task
path (`alpha_classifier`/`structure_extractor`/`claim_batch_enrichment`,
and now `evidence_stance_classifier`). **This is a pre-existing gap in the
general Week2LLMGateway real-call path, not something introduced by or
specific to B1** — it would equally affect a real run of any of the other 3
named tasks. Not fixed here (would require additional real Provider calls
to verify, exceeding the authorized 5-attempt budget, and this task's own
scope explicitly excludes inventing new retry/parsing machinery) — flagged
as a concrete, evidence-backed recommendation for whichever task next needs
a real Provider run through the shared gateway.

Despite 3/5 batches failing at the JSON-parse stage, **fail-soft worked
exactly as designed**: all 30 affected rows kept their correct,
already-computed deterministic.v1 stance, correctly labeled
`stance_method=deterministic_fallback`/`fallback_reason=malformed_response`
— zero data loss, zero crash, zero incorrect stance ever written.

## P. LLM-vs-deterministic disagreement count

**12 of 20** LLM-covered rows (60%) disagree with deterministic.v1's own
value for that same claim/target pair. All 12 rows and both values are in
`docs/audit_artifacts/b1_llm_stance_50_validation.csv`. The dominant pattern
(7 of 12): deterministic.v1 said `mentions_alpha` or `neutral_background`
where the LLM found a genuine `supports_alpha`/`opposes_alpha` stance — i.e.
the LLM more often judged the Evidence to take a real position where the
deterministic pattern layer defaulted to "just mentions/background."
Without independent human labels (see Q), this is reported as an observed
disagreement pattern, not a claim that either side is "more correct."

## Q. Independent-review agreement

`REVIEW_GOLD_AVAILABLE = NO`. Re-verified directly against
`docs/evidence_review_sample_records.json` immediately before this run: all
50 records still have `review_status="pending"` and an empty
`reviewer_expected_stance`. No completed human review exists anywhere in
the accessible repository/worktree for these 50 rows. No reviewer was
invented; no second LLM was asked to grade the first. `agreement_with_existing_review`
is `"N/A"` on every CSV row.

## R. John's A304 rebuttal result

Sample row `evrs-014` — `'The "valuation risk" argument is a lazy heuristic
that ignores the actual numbers.'` vs. `A304` — was in one of the two
successful batches (batch 2, rows evrs-011..020). The **real** LLM call
returned `opposes_alpha`, was validated (identity/vocabulary both legal),
and was accepted as `stance_method=llm` (not a fallback coincidence).
Deterministic.v1 independently also produces `opposes_alpha` for this
sample — but only via a phrase-specific regex
(`\blazy heuristic\b` → `REASON_EXPLICIT_REBUTTAL_OF_TARGET_ALPHA`) written
into `evidence_stance.py` specifically for this sentence. The real LLM
result confirms the *semantic* judgment the deterministic pattern could
only special-case: **`JOHN_A304_REBUTTAL = opposes_alpha`, genuinely and
independently reproduced by a live Provider call**, not merely by routing
mechanics (which the offline test in section 21 already proved separately
with a fake gateway).

**Sanity-check items required by task spec section 27**:
- Support↔oppose reversals: 2 of the 12 disagreements are a direct
  support↔oppose flip (`evrs-013`: `mentions_alpha → opposes_alpha`;
  `evrs-039`: `supports_alpha → opposes_alpha`) — no case flips all the way
  from `supports_alpha` to `opposes_alpha` or vice versa in a single step;
  the rest move between `mentions_alpha`/`neutral_background` and a
  committed stance, or between `supports_counter_alpha` and a plain stance.
- `LLM_VALID_RESULT_COUNT = 20`; `DETERMINISTIC_FALLBACK_COUNT = 30`.
- Every fallback's reason: `malformed_response` (30/30) — see section O.
- Batches failed: 3 of 5 (batches 1, 3, 5 — rows 1–10, 21–30, 41–50).
- `INVALID_LLM_OUTPUT_ADMITTED = 0` — confirmed both structurally (no code
  path in `_process_batch` ever calls `_apply_llm_result` without a prior
  `reason is None` from `_validate_response_item`) and empirically (the CSV
  contains no row where an out-of-vocabulary stance, wrong identity, or
  illegal counter-Alpha was written as `final_stance`).
- `VALID_LLM_RESULT_OVERRIDDEN_BY_DETERMINISTIC = 0` — confirmed
  structurally: once `_validate_response_item` accepts a result,
  `_apply_llm_result` is called unconditionally; no code path anywhere
  re-consults `classify_evidence_stance` after an LLM result is accepted.

## S. Files modified / created

- `comqutor_alpha/structure_engine/evidence_stance.py` — one function made
  public (pure rename), no behavioral change.
- `comqutor_alpha/structure_engine/week2_llm.py` — one new task entry
  (`evidence_stance_classifier`) added to the existing
  `_TASK_INSTRUCTIONS`/`_TASK_RUNTIME_METADATA` tables.
- `comqutor_alpha/structure_engine/alpha_mapper.py` — `_attach_evidence_stance`
  stamps two new default fields; `build_alpha_matches_payload` calls the
  new upgrade pass additively.
- `comqutor_alpha/api/artifact_export.py` — `build_evidence_stance_audit`
  additively reports `stance_method`/`stance_fallback_reason`/
  `evidence_stance_version` per record and `llm_stance_count`/
  `deterministic_fallback_count`/`fallback_reason_counts` in its summary.
- `comqutor_alpha/api/routes_research.py` — `run_audit.json`'s
  `evidence_stance` block extended the same way.
- `tests/structured_output_shadow/test_phase1b1_boundaries.py` — one
  assertion updated with documented reasoning (section K).
- **New**: `comqutor_alpha/structure_engine/evidence_stance_llm.py`,
  `tests/test_evidence_stance_llm.py`,
  `scripts/run_b1_llm_stance_50_validation.py`,
  `docs/audit_artifacts/b1_llm_stance_50_validation.csv`,
  `docs/audit_artifacts/b1_llm_stance_50_validation_result.json`,
  this report and its JSON companion.
- Real-run artifact: `outputs/runs/b1-llm-stance-50-validation/error_logs/week2_llm_errors.jsonl`
  (3 `WEEK2_LLM_INVALID_JSON` entries, timestamped) — left in place, not
  cleaned up, as the factual record of the real run.

No change to `comqutor_alpha/alpha_library/`, `structured_output_adapter.py`,
`structure_extractor.py`, `graph_engine/`, `conflict_engine/`,
`comqutor_alpha/exposure*`, or any A3/A4/B2/B3/B4/B5 code.

## T/U. Branch / HEAD / commit / push

`HEAD = b5837e80a4550fc35165d0013a8ef0f27ccb4c8f` (unchanged before and
after this task). `BRANCH = comqutor-structure-layer`. `COMMIT = NO`.
`PUSH = NO`.
