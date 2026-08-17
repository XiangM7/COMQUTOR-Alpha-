# Sprint 2 — Alpha-Relative Evidence Stance Classification and Human Evidence Review Dataset

**Tracks:** B1 (Evidence Polarity/Stance Classifier), J3 (50-Evidence human review export)
**Branch:** `comqutor-structure-layer` · **HEAD (unchanged throughout):** `b5837e80a4550fc35165d0013a8ef0f27ccb4c8f`
**Classifier version:** `evidence_stance.deterministic.v1` · **Sampling version:** `evidence_review_sample.v1`

---

## 1. Why `direction` is not Evidence Stance

`direction` (positive/negative/neutral) is stamped once per claim by the
structured-output adapter and is a property of the **sentence's own
language alone** — it carries no notion of *which* Alpha the claim is
being evaluated against. The same positive-direction claim can be
supporting evidence for one Alpha and directly opposing evidence for
another (e.g. "AI demand accelerated" is positive-direction and supports
A101, but the same positive-direction fact is exactly what makes a
Valuation-Risk thesis (A304) *worse*, not better). A single claim-level
field cannot encode two different verdicts for two different target
Alphas at once.

## 2. Why `semantic_polarity` is not Evidence Stance

`claim_semantics.analyze_claim_semantics(text)` computes
`semantic_polarity` (activation / invalidation / risk_relief / mention /
mixed / unknown) from the claim's text **alone** — the function signature
takes no `alpha_id` parameter at all. It cannot distinguish "this
invalidates the Alpha I'm asking about" from "this invalidates some other,
unrelated Alpha," because it was never given a target Alpha to be
relative to in the first place.

## 3. Why Evidence Stance must be bound to (claim, target_alpha_id)

Both of the above are **claim-global**. The one existing field that *is*
Alpha-relative — `claim_semantics.alpha_relation(text, alpha_id)` — comes
closest, but its five-value vocabulary
(`activation`/`invalidation`/`risk_relief`/`conditional`/`mixed`/`mention`)
exists to feed the Alpha Mapper's admission/scoring formula, and its
patterns are calibrated for scoring stability, not for recognizing plain-
English rebuttal. Empirically, before this Sprint:

```python
alpha_relation(
    "The valuation risk argument is a lazy heuristic that ignores the actual numbers.",
    "A304",
)
# -> "activation"   (WRONG: this sentence REBUTS the valuation-risk thesis)
```

This is John's own fixed test case, verified directly against the
existing, frozen `claim_semantics.py` before writing a single line of new
code (see §4 below). Because the same sentence can legitimately support
one Alpha while opposing or merely mentioning another, and because a
single claim's stance toward Alpha A must be able to differ from its
stance toward Alpha B (Track B1 case 10/11 in the spec, both verified —
see §13), Evidence Stance is *only* meaningful as a function of
`(claim_id, target_alpha_id)`. Every result returned by
`classify_evidence_stance()` carries `target_alpha_id` explicitly, and
`counter_alpha_id` when the stance is `supports_counter_alpha`.

## 4. Classifier precedence

`comqutor_alpha/structure_engine/evidence_stance.py`,
`classify_evidence_stance(*, record, target_alpha_id, candidate, taxonomy)`,
evaluated in this exact order:

1. **Validity** — no `target_alpha_id` → `NO_TARGET_ALPHA`; unknown Alpha
   → `UNKNOWN_ALPHA` (`requires_manual_review=True`).
2. **Non-substantive hard reject** — `claim_quality == non_substantive` →
   `neutral_background`/`NON_SUBSTANTIVE` (no carve-out; matches spec
   literally).
3. **Explicit opposition (topical only)** — three new, additive,
   Evidence-Stance-only pattern families (none of which touch
   `claim_semantics.py`):
   - explicit rebuttal phrases ("lazy heuristic", "ignores the actual
     numbers", "overstated", "already priced in", "no evidence that",
     "unlikely to", "fails to account for", …) → `opposes_alpha`
   - a broader risk-easing detector for risk Alphas (handles plural
     "risks are easing", which `claim_semantics.recession_risk_is_relief`
     misses because its regex requires the singular "risk ") →
     `opposes_alpha`/`RISK_RELIEF_OPPOSES_RISK_ALPHA`
   - a broader causal-weakening detector for opportunity Alphas (handles
     continuous/copula phrasing "demand is weakening", which
     `claim_semantics._INVALIDATION_PATTERN` misses because it requires
     the verb directly adjacent to the noun) → `opposes_alpha`/
     `WEAKENS_TARGET_CAUSAL_CHAIN`
   - a reporting-only construction detector ("management discussed X
     during the call") → `mentions_alpha`/`MENTION_ONLY`

   This step runs **before** the context_only downgrade specifically
   because a context-only-tagged claim can still carry a complete,
   verifiable rebuttal that the quality label must not paper over (spec
   §8.2's explicit carve-out) — verified concretely: "AI demand remains
   strong, but most of the benefit is already priced in." classifies as
   `claim_quality=context_only` under the existing (frozen)
   `classify_claim_quality`, yet must still resolve to `opposes_alpha`
   for A101, not `neutral_background`.
4. **context_only downgrade** (not already overridden above) →
   `neutral_background`/`CONTEXT_ONLY`.
5. **Existing structural relation** (reused, never re-implemented):
   `relation == "risk_relief"` (target is a risk Alpha) → `opposes_alpha`;
   `relation == "invalidation"` → `opposes_alpha`; `relation == "mention"`
   → `mentions_alpha`; `relation == "mixed"` (or claim-level
   `semantics.mixed`) → `neutral_background`/`MIXED_STANCE_UNRESOLVED`
   (low confidence, forced manual review); `relation == "conditional"` →
   `supports_alpha`/`CONDITIONAL_SUPPORT` or `opposes_alpha`/
   `CONDITIONAL_OPPOSITION` (by `semantics.negated`), medium confidence,
   forced manual review.
6. **Activation-default bucket** (`relation == "activation"`, the common
   case):
   - if the claim's own `matched_alpha` (already computed by the Alpha
     Mapper) differs from `target_alpha_id` **and** the two are a
     canonical conflict pair (reused verbatim from
     `AlphaDefinition.conflict_alphas`, checked in both declaration
     directions) → `supports_counter_alpha`, `counter_alpha_id =
     matched_alpha`;
   - if differing and **not** canonical → conservative
     `mentions_alpha`/`neutral_background` with
     `COUNTER_ALPHA_NOT_CANONICAL` + `INSUFFICIENT_ALPHA_RELATIVE_SEMANTICS`
     (never fabricated `supports_counter_alpha`);
   - otherwise: topical for the target (keyword/factor overlap reused
     from the Mapper's own `candidate["keyword_score"]`/`["factor_score"]`
     when given, else an independent local check) → `supports_alpha`;
     not topical → `neutral_background`/`GENERIC_BACKGROUND` (low
     confidence, forced manual review) — **never** defaults to
     `supports_alpha` for an off-topic claim.

Confidence bands are exactly `high`/`medium`/`low` (§9 of the spec) — no
fabricated decimal score. Every `low`-band result has
`requires_manual_review` forced `True`.

## 5. Reason codes

23 centralized constants in `evidence_stance.VALID_REASON_CODES` — every
one of the spec's required codes, no module maintains its own separate
spelling. Verified in `tests/test_evidence_stance_classifier.py::
test_reason_codes_are_from_the_centralized_vocabulary`.

## 6. Counter-Alpha source

`_canonical_conflict_partners(alpha_id, taxonomy)` reads
`AlphaDefinition.conflict_alphas` — the exact same registry
`alpha_mapper._conflict_ids()` already uses for ambiguity detection —
checked in both declaration directions (the source YAML declares some
pairs on only one side, e.g. A101→A304 and A304→A101 both present, but
not guaranteed symmetric in general). No second conflict-pair list is
maintained anywhere in this Sprint.

## 7. Mixed / conditional handling

Mixed (`assertion_status=="mixed"`, i.e. contrast + positive + negative
language, or `relation=="mixed"`) always resolves to
`neutral_background`/`MIXED_STANCE_UNRESOLVED`, confidence `low`,
`requires_manual_review=True` — never forced to `supports_alpha` for
recall. Conditional claims resolve to `supports_alpha`/`CONDITIONAL_SUPPORT`
or `opposes_alpha`/`CONDITIONAL_OPPOSITION` depending on whether the
clause is also negated, confidence `medium`, always
`requires_manual_review=True` — B2 (a future Sprint) decides Conflict
admissibility for these; this Sprint changes none.

## 8. `alpha_matches.json` schema change

- **Previous schema:** `week2.alpha_matches.v2` (`schema_version`
  unchanged).
- **New:** `schema_version` stays `week2.alpha_matches.v2` (additive
  fields never require a schema bump per this project's existing additive-
  field convention — see e.g. the AI Alpha Discrimination Sprint's
  `ai_gate_passed` field, added the same way). A new
  `evidence_stance_version` field (`evidence_stance.deterministic.v1`) is
  stamped on every candidate dict instead.
- **Compatibility:** every pre-existing field on every candidate dict
  (`alpha_id`, `score`, `keyword_score`, `factor_score`, `direction_score`,
  `semantic_score`, `relation`, `eligible`, `rejection_reason`,
  `matched_keywords`, `matched_factors`, `ai_gate_passed`) is untouched —
  verified by `tests/test_ai_alpha_mapper_discrimination.py::
  TestArtifactSchemaCompatibility::test_non_ai_candidate_score_keys_are_unchanged`
  asserting the old key set is a *subset* of the new one. Six new keys are
  additive only: `evidence_stance`, `counter_alpha_id`,
  `stance_reason_codes`, `stance_confidence_band`, `requires_manual_review`,
  `evidence_stance_version`. Five new top-level fields on the match record:
  `matched_evidence_stance`, `matched_counter_alpha_id`,
  `matched_stance_reason_codes`, `matched_stance_confidence_band`,
  `matched_stance_requires_manual_review` (all `null` when
  `match_status != "matched"`). A historical run's `alpha_matches.json`
  predating this Sprint simply lacks these keys — every consumer reads
  them with `.get(...)`, never a hard KeyError.

## 9. Evidence Fact integration

`evidence_facts.json`'s `groups[]` gained an additive `alpha_stances`
dict, keyed by `alpha_id`, each with `representative_stance`,
`member_stance_counts` (all five stance values, always present even at
0), `mixed_member_stances` (`true` whenever more than one distinct stance
appears among real, already-classified members — forces
`requires_manual_review=True` on that entry), computed by
`_alpha_stances_for_group()` in `comqutor_alpha/api/artifact_export.py`.
**Grouping itself is completely untouched**: `evidence_fact_group_id`
values, `member_claim_ids`, and `representative_claim_id` are read
verbatim from the SAME `evidence_fact_groups` list
`activation_scorer_v2.score_alpha_v2` already computed for scoring in
Sprint 1 — `extract_evidence_facts_export` never re-groups; it only reads
each member's already-classified stance (looked up by `(claim_id,
alpha_id)` from `alpha_matches.json`) and aggregates. Verified real-data:
`tests/test_evidence_stance_integration.py::test_25_evidence_fact_ids_unchanged`
(exact ID-set equality with the pre-Sprint-2 scoring output) and `test_26`/
`test_27` (aggregation correctness against real replayed data).

## 10. Why grouping/score are unchanged (proof, not assertion)

- `evidence_stance.py` is a leaf module: it imports only from
  `claim_semantics`, `claim_quality`, `factor_normalizer`, `alpha_schema`.
  It is never imported by, and never imports, `alpha_mapper`'s scoring
  functions, `activation_scorer_v2.py`, or `conflict_detector.py`.
- `tests/test_evidence_stance_integration.py::
  test_evidence_stance_never_imported_by_activation_or_conflict_modules`
  parses the AST of `activation_scorer_v2.py`, `activation_scorer.py`, and
  `conflict_detector.py` and asserts none import `evidence_stance` —
  structural proof, not a claim.
- `_attach_evidence_stance()` in `alpha_mapper.py` runs strictly *after*
  `matched_alpha`/`status`/`score`/`eligible_candidates` are already
  finalized, and only ever **adds** keys to each candidate dict — it never
  reads or writes `score`, `eligible`, `relation`, or any field that
  scoring/admission depends on (verified: classifier tests 18-20).

## 11. Activation before/after

Real replayed NVDA/QQQ/MSFT/SNDK/TSM/AMD data (see §13): every
`activation_score`/`status` value in `structure_graph.json` is produced by
the exact same, untouched `activation_scorer_v2.score_alpha_v2` call this
Sprint never modifies. For NVDA, QQQ, SNDK, and TSM specifically, the same
source runs used in Sprint 1's own replay-identity verification
(`docs/audit_artifacts/replay_identity_consistency.json`, produced *before*
any Evidence Stance code existed) were replayed again under this Sprint's
code — declared/admitted/suppressed/rejected Conflict counts are
byte-identical run-for-run (see `docs/audit_artifacts/
evidence_stance_behavior_invariants.json`), which is only possible if
Activation's own outputs (Conflict's direct input) are also unchanged.

## 12. Conflict before/after

Same evidence as §11: `docs/audit_artifacts/evidence_stance_behavior_invariants.json`
shows 4 of 6 tickers (NVDA, QQQ, SNDK, TSM) matching Sprint 1's exact
pre-Evidence-Stance baseline (same source run, same declared/admitted/
suppressed/rejected counts); MSFT and AMD show `NO_BASELINE` only because
this session accumulated newer local source runs for those two tickers
since Sprint 1's report was written, not because of any Conflict-outcome
drift — `all_conflict_outcomes_unchanged: true` for every case where a
baseline exists at all.

## 13. Six-ticker offline results

`docs/audit_artifacts/evidence_stance_case_results.csv` /
`evidence_stance_summary.json` (real Architecture Replay, zero Provider
calls):

| Ticker | claim×alpha pairs | supports | opposes | mentions | background | counter | manual review | declared/admitted/suppressed/rejected | artifact_completeness | ticker_consistency | Provider calls | source hash unchanged |
|---|---|---|---|---|---|---|---|---|---|---|---|---|
| NVDA | 3,260 | 384 | 38 | 394 | 2,427 | 17 | 1,563 | 6/3/1/2 | pass | pass | 0 | ✓ |
| QQQ  | 3,550 | 381 | 72 | 323 | 2,736 | 38 | 1,709 | 6/5/1/0 | pass | pass | 0 | ✓ |
| MSFT | 4,320 | 469 | 53 | 285 | 3,500 | 13 | 1,804 | 6/2/1/3 | pass | pass | 0 | ✓ |
| SNDK | 9,760 | 752 | 120 | 785 | 8,095 | 8 | 3,834 | 6/2/2/2 | pass | pass | 0 | ✓ |
| TSM  | 4,225 | 443 | 54 | 415 | 3,302 | 11 | 1,757 | 6/3/1/2 | pass | pass | 0 | ✓ |
| AMD  | 4,285 | 407 | 64 | 337 | 3,452 | 25 | 1,916 | 6/3/2/1 | pass | pass | 0 | ✓ |

**Totals (6/6 tickers):** 29,400 claim×alpha pairs classified · 2,836
`supports_alpha` · 401 `opposes_alpha` · 2,539 `mentions_alpha` · 23,512
`neutral_background` · 112 `supports_counter_alpha` · 12,583
manual-review-required · **0** unknown · **0** Provider/LLM/DB calls ·
**0** source artifact bytes changed (sha256 verified, see CSV).

## 14. 50-sample distribution

`docs/evidence_review_sample.csv` (verdict **PASS**, 50/50):

- **Ticker distribution:** NVDA 10, QQQ 10, MSFT 10, SNDK 6, TSM 6, AMD 8
  (every ticker within the required 6-10 range).
- **Stance distribution:** `supports_alpha` 18/18, `opposes_alpha` 10/10,
  `mentions_alpha` 8/8, `neutral_background` 8/8,
  `supports_counter_alpha` 6/6 — every requested quota exactly met from
  real, unique candidates (no fabrication, no duplication).
- **Coverage:** 43 rows used in Activation, 43 rows used in Conflict, 34
  rows `requires_manual_review`, 10 negated/rebuttal/invalidation rows, 24
  conditional/mixed rows, 7 duplicate/paraphrase fact-group-member rows,
  **1** row matching John's own A304 rebuttal reason code
  (`johns_example_included: true` in the manifest).

## 15. Quota shortfalls

None — `quota_shortfalls` is all-zero for every stance in this
environment's real 6-ticker data (`docs/evidence_review_sample_manifest.json`).
One honest limitation: `non_ticker_specific_count` is currently always 0,
because the `ticker_specific` field (as computed in
`build_evidence_stance_audit`) is derived from
`alpha_matches.json record.ticker == run ticker`, which every record
satisfies by construction under the current adapter (it stamps every
record with the run's own ticker regardless of whether the sentence is a
genuine cross-ticker/peer-comparison mention). This means "at least 5
non-ticker-specific or peer-comparison rows" (spec §21) could not be
targeted with the data available today — flagged honestly here rather
than silently ignored (§20 remaining limitations).

## 16. Manual-review proportion

12,583 / 29,400 = 42.8% of all classified claim×alpha pairs across the
six tickers are flagged `requires_manual_review` — dominated by the
"activation-default bucket, matched_alpha differs from target and not a
canonical pair" case (§4 step 6), which is the deliberately conservative
`INSUFFICIENT_ALPHA_RELATIVE_SEMANTICS` fallback rather than a fabricated
`supports_alpha`/`supports_counter_alpha`. This is a direct, intended
consequence of never guessing under real ambiguity (spec §8.6/§8.8), not
a defect.

## 17. Provider call proof

`ReplayResult.tradingagents_calls == 0`,
`ReplayResult.llm_provider_calls == 0`,
`ReplayResult.market_data_provider_calls == 0` for every one of the six
real replay runs (asserted directly in
`tests/test_evidence_stance_integration.py::
test_43_44_45_replay_uses_replay_run_id_and_zero_provider_calls` and
independently re-confirmed by the verification script behind
`docs/audit_artifacts/evidence_stance_summary.json`'s
`all_provider_calls_zero: true`). No new LLM/Provider call site was added
anywhere in this Sprint's diff (grep-verified: no new `llm_gateway`,
`invoke_json`, or provider-client import in `evidence_stance.py`,
`evidence_review_sample.py`, or `export_evidence_review_sample.py`).

## 18. Source hash proof

For every one of the six tickers, `sha256(raw_agent_outputs.json)` was
captured before and after both the replay used for
`evidence_stance_audit.json` verification and the replay used to build the
review sample — all six byte-identical
(`docs/audit_artifacts/evidence_stance_case_results.csv`'s `source_hash`
column, cross-checked directly against the live file on disk in
`tests/test_evidence_review_sample.py::
test_source_hashes_recorded_and_match_disk`).

## 19. Tests

- **Classifier** (`tests/test_evidence_stance_classifier.py`): 40 tests —
  the 12 fixed semantic acceptance cases (including John's A304 example)
  plus the 20 classifier-level items from spec §28, plus ontology/reason-
  code hygiene checks.
- **Integration** (`tests/test_evidence_stance_integration.py`): 21 tests
  — candidate-pool propagation (21-24), Evidence Fact aggregation (25-27),
  Activation/Conflict evidence-detail carry-through and
  `stance_effect_applied` (28-30), behavior invariants (31-37, including
  the AST-based "never imported by Activation/Conflict" structural proof),
  artifact/API/replay (38-45) — all against one real, fully-computed NVDA
  run plus a real Architecture Replay.
- **Review sample** (`tests/test_evidence_review_sample.py`): 16 tests —
  spec §28 items 46-60 plus a source-hash cross-check, against the real,
  full 6-ticker/50-row sample built once per test-session run.
- **Related-suite regression:** `test_ai_alpha_mapper_discrimination.py`,
  `test_artifact_export_and_api.py`, `test_replay_identity_correction.py`,
  `test_ticker_consistency_audit.py`, `test_run_audit_v2.py`,
  `test_week3_security_hardening.py` — 324 tests total, all passing
  (includes the 77 new Evidence Stance tests).
- **Full offline suite:** `pytest -q -m "not integration"` — **2594
  passed, 1 skipped** (pre-existing, unrelated: `test_bedrock_provider.py`,
  missing optional `langchain_aws` dependency), **0 failed**. (Sprint 1's
  end-of-sprint baseline was 2517 passed/1 skipped — the +77 delta is
  exactly this Sprint's three new test files.)
- **Ruff:** clean on every file this Sprint touched or added.

## 20. Remaining limitations

1. **Human semantic validation is PENDING.** This Sprint's engineering
   implementation is fully tested and offline-verified, but the
   classifier's real-world *accuracy* on John's own judgment has not yet
   been assessed — that is precisely what the 50-row CSV exists to enable,
   and it cannot be self-certified.
2. **`ticker_specific` cannot currently distinguish genuine peer-mention
   evidence** (§15) — the underlying `alpha_matches.json` field is always
   `True` today; a future Sprint would need the adapter itself to stamp a
   real per-claim ticker-specificity signal before this coverage target
   becomes achievable.
3. **`used_in_conflict` is a fact-group-membership proxy**, not a literal
   re-derivation of Conflict's internal per-claim evidence-gathering logic
   (deliberately, to avoid duplicating `conflict_detector.py`'s admissibility
   rules in a second place) — it is precise about which *fact groups*
   participated in a declared conflict pair, but does not distinguish
   admitted-vs-suppressed-vs-rejected at the individual-claim level.
4. **Non-canonical counter-Alpha claims are classified conservatively**
   (`mentions_alpha`/`neutral_background` with low confidence) rather than
   attempting any inferred relationship — correct by design (spec
   explicitly forbids inferring counter-Alpha status from direction
   alone), but means some genuinely related-but-undeclared Alpha pairs
   will always require manual review rather than an automatic verdict.

---

## 21. Verdict

| Track | Verdict |
|---|---|
| Evidence Stance Ontology | **PASS** |
| Deterministic Classifier | **PASS** |
| Alpha Matches / Artifact Integration | **PASS** |
| Behavior Preservation | **PASS** |
| 50-Evidence Review Export | **PASS** |
| Human Validation | **PENDING** |

**Overall Sprint 2 engineering implementation: PASS.** Human semantic
validation remains **PENDING** until John completes the 50-row review.

## Files

**New:**
- `comqutor_alpha/structure_engine/evidence_stance.py`
- `comqutor_alpha/evaluation/evidence_review_sample.py`
- `scripts/export_evidence_review_sample.py`
- `tests/test_evidence_stance_classifier.py`,
  `tests/test_evidence_stance_integration.py`,
  `tests/test_evidence_review_sample.py`
- `docs/evidence_review_sample.csv`,
  `docs/evidence_review_sample_manifest.json`,
  `docs/evidence_review_sample_records.json`,
  `docs/evidence_review_instructions.md`
- `docs/audit_artifacts/evidence_stance_case_results.csv`,
  `evidence_stance_summary.json`, `evidence_stance_behavior_invariants.json`,
  `evidence_review_sample_validation.json`
- `outputs/review_sample_replays/` (real replay bundles used to build the
  sample; gitignored parent pattern does not cover this new subdirectory,
  no commit made)

**Modified (additive only):**
- `comqutor_alpha/structure_engine/alpha_mapper.py` — candidate-pool
  stance attachment, top-level `matched_*` stance fields.
- `comqutor_alpha/api/artifact_export.py` — `evidence_stance_audit.json`
  builder, `evidence_facts.json`'s `alpha_stances` aggregation.
- `comqutor_alpha/api/routes_research.py` — Run Audit v2's
  `evidence_stance` section, research response's
  `evidence_stance_summary`, `GET /api/research/{run_id}/evidence-stances`.
- `comqutor_alpha/replay/pipeline.py` — passes `alpha_matches_payload`
  through to the finalizer (replay bundles now also get
  `evidence_stance_audit.json`).
- `comqutor_alpha/storage/file_store.py` —
  `evidence_stance_audit.json` added to `ALLOWED_ARTIFACT_FILENAMES`.
- `tests/test_ai_alpha_mapper_discrimination.py` — one pre-existing
  closed-key-set assertion widened to a subset check (the schema is
  legitimately, additively extended by this Sprint).

**Historical source artifacts changed:** None (`outputs/runs/` zero
diffs; every source `raw_agent_outputs.json` sha256 verified unchanged).

**Commit/push:** No.
