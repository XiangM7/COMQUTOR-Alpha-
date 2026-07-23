# Week 2 Adversarial Engineering Audit — COMQUTOR Alpha

Repo: `/Users/xiangmao/COMQUTOR-Alpha-`, branch `comqutor-structure-layer`, HEAD `64e657958aa1db32528d55e8b9c5520b387f86fc` (clean).
Scope: `structured_output_adapter.py`, `claim_semantics.py`, `factor_normalizer.py`, `alpha_mapper.py`, `structure_extractor.py`, `structure_schema.py`, `week2_llm.py`.

---

## 1. Doc contract claims (docs/week2_completion_report.md)

| # | Claim | doc:line |
|---|---|---|
| C1 | "长 Markdown 可拆为多个 claim；标题、表格、代码块和 disclaimer 被过滤" (long markdown splits into multiple claims; headings/tables/code fences/disclaimers filtered) | docs/week2_completion_report.md:14 |
| C2 | "初始 match threshold 与 Development Plan 对齐为 `0.35`" | docs/week2_completion_report.md:21 |
| C3 | "deterministic logic 决定 admissibility. LLM 只能在最多三个 admissible candidates 中 select 或 defer，不能创建 Alpha、恢复非法候选或改写 deterministic no-match" | docs/week2_completion_report.md:24 |
| C4 | "vague coexistence 不生成 causal edge；`no evidence that ... drives ...` 不生成 asserted edge" | docs/week2_completion_report.md:32 |
| C5 | "同一 raw output 内不同 claim 的相同关系不会因共享 raw ID 被去重" | docs/week2_completion_report.md:33 |
| C6 | "Clean 20-case gate：20/20，100%" | docs/week2_completion_report.md:69 |
| C7 | "NVDA 当前：strict 23/30，allowed 29/30" | docs/week2_completion_report.md:72 |
| C8 | "NVDA 结果是 robustness diagnostic，不是市场预测准确率，也未用于修改人工标签、降低 gate 或添加 case-specific branch" | docs/week2_completion_report.md:74 |
| C9 | "deterministic NLP 对复杂嵌套语义仍有覆盖边界" (risk, explicitly disclosed) | docs/week2_completion_report.md:87 |

---

## 2. Actual code behavior per question (file:line, with real invocations)

### Q1 — Claim splitting

`extract_claim_segments` (comqutor_alpha/structure_engine/structured_output_adapter.py:247-328) is a two-pass splitter: paragraph/line-level pass (headings, tables, bullets, code fences, disclaimer *lines*) → sentence-level regex `re.split(r"(?<=[.!?。！？])\s+", cleaned_block)` (line 303).

Confirmed real defects by direct invocation:

**(a) Disclaimer filter is line-level, not sentence-level — legitimate claims sharing a paragraph with boilerplate are silently deleted, not just the boilerplate.**
```python
extract_claim_segments("AI training demand is accelerating. GPU demand is rising as cloud "
                        "providers expand capacity. This is not investment advice.")
# => []   (ALL THREE sentences dropped, including two real claims)
```
vs. the same content with the disclaimer on its own paragraph (blank line before it):
```python
# => [{'claim': 'AI training demand is accelerating.', ...},
#     {'claim': 'GPU demand is rising as cloud providers expand capacity.', ...}]
```
Root cause: structured_output_adapter.py:287-289 checks `any(marker in line.lower() ...)` per raw markdown line *before* sentence splitting, and `continue`s the whole line (`flush_paragraph()` without keeping it) when a marker is anywhere on that line. The only existing test (`test_long_markdown_report_splits_into_traceable_claims`, tests/test_structured_output_adapter.py:244-271) always puts the disclaimer on its own isolated paragraph (line 255) — the "boilerplate glued onto the end of a real paragraph" placement (very plausible from LLM-generated markdown reports) is never exercised. **TEST GAP.**

**(b) Naive abbreviation-blind sentence splitter fragments claims.**
```python
extract_claim_segments("The U.S. Fed is expected to cut rates in Q4. Revenue grew 20.5% y/y, "
                        "beating estimates. Mr. Huang said demand remains robust vs. last year.")
# => ['Fed is expected to cut rates in Q4.',
#     'Revenue grew 20.5% y/y, beating estimates.',
#     'Huang said demand remains robust vs.']
```
"Mr. Huang said demand remains robust vs. last year." is fragmented into "Huang said demand remains robust vs." (truncated mid-comparison, losing "last year") because the regex at structured_output_adapter.py:303 splits on any `.` before whitespace, with no abbreviation list (Mr., vs., U.S., Inc., Corp., e.g., i.e., etc.). "Mr." and the trailing "last year." fragments are silently dropped by the `MIN_CLAIM_CHARS`/4-word filter (`_is_meaningful_claim`, line 237-244), so the surviving "claim" record is an incomplete, semantically truncated sentence with no signal that truncation occurred.

Headings/tables/code fences are correctly filtered (verified with a constructed markdown doc containing a table, heading, and fenced block — none leaked into segments).

### Q2 — direction / assertion_status / semantic_polarity consistency

Deterministic path is internally consistent: `infer_direction` (structured_output_adapter.py:356-378) itself calls `analyze_claim_semantics` and explicitly maps `risk_relief→positive`, `invalidation→negative`, `negated/mixed→neutral`. Verified:
```python
adapt_raw_agent_outputs({...}, ...)  # "There is no evidence that AI demand is increasing..."
# direction=neutral, assertion_status=negated, semantic_polarity=mention  -- consistent
```

**LLM path is NOT reconciled against the deterministic semantics of the same text — confirmed contradiction.** `_validated_llm_segments` (structured_output_adapter.py:502-568) only bounds-checks the LLM-proposed `direction` field against `VALID_DIRECTIONS` (lines 542-545); it never cross-checks it against `analyze_claim_semantics`. In `adapt_raw_agent_outputs` (line 674), `direction` is taken as `segment.get("direction") or infer_direction(claim)` — for the LLM path `segment["direction"]` is always present, so `infer_direction` is *never called* and the LLM's raw opinion wins, while `assertion_status`/`semantic_polarity` are *always* freshly recomputed from the actual claim+evidence text (line 646, 688-689) regardless of what the LLM said. Reproduced live with a mocked `Week2LLMGateway`:
```
raw_text = "There is no evidence that AI demand is increasing for NVIDIA GPUs."
LLM proposes direction="positive" for this claim (via mocked gateway) →
  direction: positive
  assertion_status: negated
  semantic_polarity: mention
  extraction_method: llm_strict_json
```
This is a genuinely self-contradictory persisted record (`direction=positive` next to `assertion_status=negated`). Blast radius is partially contained downstream: `alpha_mapper.direction_score` (alpha_mapper.py:154-171) recomputes `alpha_relation` fresh from claim text and short-circuits to `0.0` when `relation == "mention"` (line 163-164) *before* consulting the stored `direction` field, so alpha matching itself is not fooled. But the persisted `structured_agent_outputs.json` artifact carries the contradiction, and any other consumer (dashboards, Week 3 structure graph, human QA) that reads `direction` without recomputing semantics would be misled. No test in tests/test_week2_llm.py or tests/test_structured_output_adapter.py checks LLM-direction vs. semantics consistency. **Confirmed defect + test gap.**

### Q3 — Deterministic admissibility gate independence from the LLM

`map_claim_to_alpha` (alpha_mapper.py:393-501) computes `eligible_candidates` (line 412-414, requires `eligible=True` AND `score >= min_score`) and the deterministic `status`/`matched_alpha` (lines 419-452) *before* `_apply_optional_classifier` is ever called (line 493). `_apply_optional_classifier` (alpha_mapper.py:256-390):
- refuses to run at all if `result["match_status"] == "no_match"` (line 269-271) — **cannot override deterministic no-match**, confirmed live (see Q4).
- builds `allowed_ids` strictly from `result["eligible_candidates"][:3]` (lines 279-301) — the LLM literally never sees any alpha_id outside the deterministic admissible set.
- `validate_response` (line 313-323) raises `ValueError` for any `selected_alpha_id not in allowed_ids`, which propagates up through `Week2LLMGateway.invoke_json`'s exception handling (week2_llm.py:186-193) as `WEEK2_LLM_VALIDATION_FAILED`, retried, then returns `None` → `_apply_optional_classifier` falls back to the original deterministic result (alpha_mapper.py:330-332).
- The LLM **can** upgrade a deterministic `ambiguous` verdict to `matched` (this is not gated by the `no_match` check) — this is the intended purpose of the classifier per the doc wording ("不能...改写 deterministic no-match", which does not claim ambiguous is protected), confirmed by `test_optional_classifier_can_choose_only_from_deterministic_candidates`.

Order of operations matches the doc claim: deterministic candidate generation → deterministic admissibility/status → optional LLM select/defer restricted to the deterministic candidate set. **VERIFIED.**

### Q4 — Can the LLM resurrect an out-of-taxonomy or non-admissible Alpha ID?

Two live monkeypatch attempts against `map_claim_to_alpha` with a fake `llm_gateway`:
1. LLM tries to select `"A999"` (not in taxonomy at all) → `validate_response` raises `ValueError("classifier response violates the candidate contract")` → gateway retries exhausted → `result["classifier"] = {"status": "fallback"}`, final `match_status` stays the deterministic `"ambiguous"`, `matched_alpha=None`.
2. LLM tries to select `"A501"` — a **real, valid taxonomy alpha**, just not one of this claim's two deterministic eligible candidates (`A101`, `A304`) — same rejection path, same result.

**Confirmed: the LLM cannot create, resurrect, or substitute any alpha ID outside the deterministic admissible set, even a legitimate taxonomy ID.** Matches `tests/test_week2_semantics.py::test_optional_classifier_illegal_alpha_falls_back_without_leaking_response` and `tests/test_week2_llm.py::test_mapper_invalid_llm_candidate_falls_back_without_response_leak`, both of which use the same production entrypoint.

### Q5 — Threshold logic (0.35, top-3, ambiguous/no-match boundary)

`DEFAULT_MIN_MATCH_SCORE = 0.35` (alpha_mapper.py:30). Gate check is `item["score"] >= min_score` (alpha_mapper.py:413) — inclusive at the boundary. Live boundary probe using `min_score` override on a real claim scoring `0.5608`:
```
min_score=0.5607 -> matched   (below score: still admitted)
min_score=0.5608 -> matched   (score == min_score: still admitted, confirms >=)
min_score=0.5609 -> no_match  (just above score: rejected)
```
`top_candidates`/`candidate_scores` are capped at 3 / 5 respectively both in `map_claim_to_alpha` (alpha_mapper.py:482-484) and enforced again defensively in `structure_schema.AlphaMatchRecord.to_dict` (structure_schema.py:206, 223). **VERIFIED for the ≥ boundary itself.**

**Threshold-loosening mutation is barely caught by the test suite (test-effectiveness gap — see §5 mutation results).**

Note on mechanism: `min_score` is a keyword-only parameter with a compiled-in default (`min_score: float = DEFAULT_MIN_MATCH_SCORE`). Reassigning the module attribute `alpha_mapper.DEFAULT_MIN_MATCH_SCORE` after import has **no effect** on already-defined `map_claim_to_alpha` calls (Python binds default args at function-definition time into `__kwdefaults__`), verified directly. `build_alpha_matches_payload`/`save_alpha_matches` never pass `min_score` through, so the effective production threshold can only be changed by editing `map_claim_to_alpha.__kwdefaults__["min_score"]` or the source. This is a correctness non-issue for production but means naive "reassign the constant" mutation tooling would silently no-op — flagged for anyone re-running this style of audit.

### Q6 — Causal/supportive/conflicting edges for negated / conditional / no-evidence text

`_extract_edges` (structure_extractor.py:244-350) generates edges with `edge_type` based on verb pattern matched in the "bridge" text between two factor mentions, and separately computes `assertion_status` via `_assertion_status` (line 217-223), which calls `analyze_claim_semantics` on the **full** evidence text (not just the bridge) — so negation/conditionality anywhere in the sentence (e.g. "no evidence that" appearing *before* both factor mentions) is still caught even when the bridge substring itself contains no negation word. Live confirmations:
```
"There is no evidence that AI demand drives GPU demand." → edges: [] (test_no_evidence_causal_phrase_is_not_asserted, PASSED)
"AI capex does not drive GPU demand."                    → edge_type=causal, assertion_status=negated, confidence=0.35
"If AI capex rises, GPU demand could increase."           → edge_type=causal, assertion_status=conditional, confidence=0.58
"Both AI capex and GPU demand were mentioned in the same earnings call." → edges: [] (vague coexistence, no verb match)
```
Design note: negated/conditional relations are **not suppressed** — they still produce an edge with `edge_type="causal"`, just tagged `assertion_status="negated"/"conditional"` with lower confidence. This matches the doc's literal wording ("不生成 *asserted* edge", not "不生成 edge") but means any downstream consumer that filters on `edge_type` alone (ignoring `assertion_status`) would still see a "causal" edge for a claim that explicitly denies causality. This is a correct-by-design contract, not a bug, but is a sharp edge worth flagging.

**LLM structure-extractor path: assertion_status is deterministically corrected, confidence is not.** `_validated_llm_edges` (structure_extractor.py:370-443) overrides an LLM-proposed `assertion_status` when `semantics.negated`/`semantics.conditional` disagree (lines 425-428), confirmed live: a fake gateway proposing `assertion_status="asserted", confidence=0.95` for the negated claim "AI capex does not drive GPU demand." produces a **persisted edge with `assertion_status="negated"` but `confidence=0.95`** — the deterministic path's `_relation_confidence` (which forces `negated→0.35`, line 226-231) is never re-applied to the corrected assertion_status in the LLM branch. **Confirmed inconsistency (P2): a "negated" edge can carry misleadingly high confidence when it originates from the LLM path.** No test in tests/test_week2_llm.py exercises this combination (existing LLM-edge tests only use non-negated, non-conditional text).

### Q7 — Duplicate detection

There is **no semantic/similarity-based claim deduplication anywhere in Week 2** (`grep -rn "dedup|duplicate|similar|fuzzy|levenshtein|jaccard"` across structure_engine turns up only `structure_schema._dedupe`, which is exact-string list de-duplication for metadata fields like `matched_keywords`, and the edge de-duplication key in `extract_structures_from_records` (structure_extractor.py:493-500), which is an exact tuple key `(source, target, edge_type, source_record_id)`.

Verified the doc's specific claim (C5) live: two **distinct** claims from the same raw output producing the same (source, target, edge_type) relation are correctly **kept separately** because `source_record_id` (the per-claim ID) is part of the key:
```
2 distinct claims, same raw_id, different claim_id → 2 edges kept, not merged.
```
This matches `test_same_raw_output_keeps_edges_from_distinct_claims`. **VERIFIED, no false-positive dedup of distinct claims under the normal contract.**

Fragility (not a confirmed production bug, since claim_id is generated uniquely by the adapter): if a caller ever supplies **colliding** `claim_id` values for genuinely different claim text (nothing in `extract_structures_from_records` validates uniqueness), the edge-dedup key silently keeps only the first edge and drops the second, with no warning. Verified live. No test constructs this scenario. **TEST GAP**, low practical severity given the adapter's ID-generation contract.

### Q8 — Deterministic fallback vs. LLM path schema parity

Both paths funnel through the same shape-producing helpers: `structured_output_adapter.py`'s final `record = {...}` dict (lines 663-691) is built identically regardless of `extraction_method`; `structure_extractor.py`'s `_edge()` helper (lines 177-208) is called by both `_extract_edges` (deterministic) and `_validated_llm_edges` (LLM), producing the identical field set — the only differing field is `extraction_method` (`"deterministic_splitter"/"deterministic_rules"` vs `"llm_strict_json"`). Verified live: an LLM-sourced edge and a deterministic edge for equivalent claims have identical key sets. **VERIFIED — no shape divergence.**

### Q9 — 20-case labeled gate: generic or fixture-gamed?

`tests/test_week2_labeled_accuracy.py` and the inline duplicate `tests/test_alpha_mapper.py::test_labeled_claim_accuracy_is_at_least_80_percent` both call the real `map_claim_to_alpha` production entrypoint against `tests/golden_cases/labeled_claims_v1.json`, generically scoring `strict_correct/total >= 0.80`. **No fixture-ID-keyed branches exist in `alpha_mapper.py`, `structure_extractor.py`, or `claim_semantics.py`** (no `if case_id == "lc016"`-style code was found anywhere in the audited source).

However, a more subtle form of overfitting was found and corroborated with git history:

- `comqutor_alpha/structure_engine/factor_normalizer.py`'s `FACTOR_ALIASES` table contains phrases that are **verbatim substrings of the 20 golden test sentences**: `"priced for perfection"`, `"reserves rise"`, `"theme flows"`, `"wafer orders"`, `"asp stabilizes"`, `"token generation"`, `"copilot usage"` (factor_normalizer.py:70,85,95,104,106,123-124).
- Git history shows `tests/golden_cases/labeled_claims_v1.json` was committed **first**, at commit `7d6d5c7` (2026-07-09 11:04:26 -0700, "w2v1"). `factor_normalizer.py` — the file containing these exact-phrase aliases — did not exist until the **next** commit, `7b8d3b7` (2026-07-10 14:53:22 -0700, "w2v2"), which introduced `FACTOR_ALIASES` with these phrases already present in its first version.
- i.e., the alias list was authored strictly *after* the 20-case labeled test set existed, and several aliases are exact phrase lifts from that set's sentence text rather than independently-designed generic financial vocabulary (contrast with `comqutor_alpha/alpha_library/alpha_taxonomy_v1.yaml`, whose keyword/trigger_signal lists were committed on 2026-07-07, i.e. *before* the golden cases — the taxonomy itself does not show this ordering issue).

This is not a hard-coded per-case branch, but it functions similarly to one: the production alias table appears reverse-engineered from the fixed 20-sentence test corpus to guarantee gate passage, and its generalization to real-world text is unproven — the NVDA real-report diagnostic (a genuinely independent 30-claim set) drops to 76.7% strict / 96.7% allowed (see Q below), consistent with weaker generalization outside the tuned 20 sentences. **Flag for §6 as a confirmed overfitting risk, not a literal case-ID branch.**

Separately: `tests/test_alpha_mapper_nvda_real_report.py::test_real_nvda_labeled_claim_accuracy_diagnostic` (the only genuinely independent accuracy check) **asserts nothing by default** — the accuracy assertion only fires when `COMQUTOR_ENFORCE_REAL_NVDA_GATE=1` is set (test_alpha_mapper_nvda_real_report.py:150-155), which is **not** set in the default `pytest` run. Confirmed live: `strict_correct=23/30 (76.7%), allowed_correct=29/30 (96.7%)`, matching doc claim C7 exactly — but this test **passes unconditionally regardless of the actual numbers** in normal CI. This matches the doc's own framing (C8, "not used to lower the gate or add case-specific branches") — it is honestly disclosed as diagnostic-only, not hidden, but it means Week 2's only externally-sourced accuracy check is a **no-op by default**.

---

## 3. Doc-vs-code conflicts

| Doc claim | Code reality | Verdict |
|---|---|---|
| C1 (disclaimers filtered, markdown splits into multiple claims) | True for isolated-paragraph disclaimers; **false/misleading** when a disclaimer phrase shares a paragraph with real claims — the entire paragraph (including legitimate claims) is dropped, not filtered per-sentence. Doc does not disclose this. | **CONFLICT** |
| C2 (threshold = 0.35) | Confirmed exact value and inclusive `>=` boundary. | Consistent |
| C3 (LLM cannot create/resurrect alpha or override no-match) | Confirmed live for both out-of-taxonomy and in-taxonomy-but-non-admissible IDs, and for no-match. Doc is silent on the (intentional, tested) ambiguous→matched upgrade path, which is not a violation of C3's literal wording but is worth an explicit doc note. | Consistent |
| C4 (no evidence → no asserted edge) | Confirmed live and by test; but LLM path re-derives `assertion_status` without re-deriving `confidence`, so a "negated" edge can carry a misleadingly high (LLM-supplied) confidence — an omission from the doc's framing. | **PARTIAL CONFLICT** |
| C5 (distinct claims not deduped by shared raw ID) | Confirmed live and by test for the documented scenario (unique claim_ids). Doc doesn't mention the un-validated claim_id-collision fragility. | Consistent (as scoped) |
| C6/C7 (20/20, 23/30, 29/30) | Reproduced exactly. | Consistent |
| C8 (NVDA diagnostic not used to lower the gate / no case-specific branches) | No literal fixture-ID branches found. However, `factor_normalizer.py`'s alias table was demonstrably authored after and using exact phrases from the 20-case golden set, which the doc does not mention and which undercuts the "no fixture-specific tuning" framing even though it's not a literal branch. | **CONFLICT (nuanced)** |
| (implicit) Fields (direction/assertion_status/semantic_polarity) are trustworthy together | LLM extraction path can persist an internally contradictory record (`direction=positive`, `assertion_status=negated`). Not mentioned anywhere in the doc. | **CONFLICT** |

---

## 4. Test effectiveness table

| Test file / representative test | Entrypoint used | Mock layer | Assertion specificity | Rating | Justification |
|---|---|---|---|---|---|
| test_structured_output_adapter.py (whole file) | `adapt_raw_agent_output(s)`, `validate_structured_output`, `_validated_llm_segments` — real production functions | None for deterministic path; none needed | Concrete field values (claim_id format, traceability, confidence bounds) | **STRONG** | Real entrypoints, business-outcome assertions, not reimplemented logic. Misses the glued-disclaimer and abbreviation-fragmentation cases (see Q1). |
| test_structure_extractor.py (whole file) | `extract_structures_from_records`, `save_extracted_structures` — real production functions | None | Exact edge source/target/type/assertion_status/confidence bounds | **STRONG** | Directly tests negation, conditional, passive voice, reversed-direction rejection, vague coexistence, cross-claim non-dedup — all via real invocation with concrete constructed sentences. |
| test_structure_schema.py | Dataclass `.to_dict()` methods directly | None | Exact clamping/normalization behavior | **STRONG** | Tests the actual schema-normalization code, not a reimplementation. |
| test_alpha_mapper.py | `map_claim_to_alpha`, `keyword_score`, `factor_score`, `save_alpha_matches` | None | Concrete alpha_id/match_status assertions incl. the 20-case gate | **STRONG**, with one **PARTIAL** sub-test (`test_labeled_claim_accuracy_is_at_least_80_percent` duplicates test_week2_labeled_accuracy.py's gate inline — redundant, not tautological, but wasted surface) |
| test_alpha_mapper_nvda_real_report.py | `map_claim_to_alpha` | None | Real numeric accuracy computed and printed | **PARTIAL→VACUOUS by default**: `test_real_nvda_labeled_claim_accuracy_diagnostic` computes real strict/allowed accuracy but asserts **nothing** unless `COMQUTOR_ENFORCE_REAL_NVDA_GATE=1` is exported — in the standard `pytest` invocation this test cannot fail no matter how bad the accuracy is. `test_real_nvda_labeled_claims_schema_is_valid` (schema-only) is STRONG. |
| test_factor_normalizer.py | `normalize_factor_label`, `extract_known_factors_from_text` | None | Exact alias→canonical mapping | **STRONG** for what it tests, but does not test alias *generalization* — see §2 Q9 overfitting finding. |
| test_week2_semantics.py | `map_claim_to_alpha` with real and injected fake classifiers | Simple fake classifier callables (not the real LLM gateway) | Concrete match_status/relation/taxonomy_gap_context assertions, incl. timeout and leak-prevention | **STRONG** | Directly tests admissibility-gate boundary conditions (no_match cannot be bypassed, illegal alpha rejected, response leak prevented, real caller-side timeout measured with wall-clock). |
| test_week2_llm.py | `Week2LLMGateway.invoke_json`, `adapt_raw_agent_outputs`, `map_claim_to_alpha`, `extract_structures_from_records` with `_SequenceModel` fake models | Fake model returning canned JSON strings (no network) | Concrete extraction_method/claim/edge assertions | **STRONG** for what it covers; **TEST GAP** for (a) LLM-direction-vs-semantics consistency (Q2 defect), (b) LLM-confidence-vs-corrected-assertion_status consistency (Q6 defect), (c) `_llm_relation_is_evidence_backed` specifically (only indirectly covered via the unrelated "invented factor" rejection path). |
| test_week2_labeled_accuracy.py | `map_claim_to_alpha` | None | `case_count==20`, `accuracy>=0.80` | **STRONG** as a gate mechanism, but see §2 Q9: the *content* it gates against (factor aliases) shows signs of having been tuned to this exact fixture after the fact. |

---

## 5. Mutation results table

| # | Mutation | Method | Result | Verdict |
|---|---|---|---|---|
| 1 | `min_score` raised 0.35→0.9 | `map_claim_to_alpha.__kwdefaults__["min_score"] = 0.9` then ran test_alpha_mapper.py + test_week2_labeled_accuracy.py + test_week2_semantics.py + test_alpha_mapper_nvda_real_report.py | Many failures (≈15+ of 41 collected) | **CAUGHT** — strong signal |
| 2 | `min_score` lowered 0.35→0.05 | same mechanism | Only 1 of 39 tests failed, and only incidentally (an unrelated candidate-set-size assertion) | **BARELY CAUGHT** — test-effectiveness gap for over-permissive threshold |
| 3 | `min_score` lowered 0.35→0.20 (subtler) | same mechanism | Only the same 1 of 41 tests failed | **BARELY CAUGHT** — confirms gap is not a fluke of the 0.05 extreme |
| 4 | LLM selects out-of-taxonomy alpha (`A999`) | Fake `llm_gateway` returning `selected_alpha_id="A999"` | Rejected by `validate_response`; falls back to deterministic `ambiguous`, `matched_alpha=None` | **REJECTED — pipeline is correct** |
| 5 | LLM selects real-taxonomy alpha not in this claim's admissible set (`A501`) | Fake `llm_gateway` | Rejected identically | **REJECTED — pipeline is correct** |
| 6 | Force deterministic `ambiguous` → `matched` via classifier | Fake classifier returning `{"match_status":"matched","alpha_id":"A101"}` for an ambiguous case | Accepted — `match_status` becomes `matched`, `A101` | **ACCEPTED BY DESIGN** (ambiguous is explicitly not protected by C3's "no-match" wording; matches `test_optional_classifier_can_choose_only_from_deterministic_candidates`) |
| 7 | Swap `claim_id` and `source_agent_output_id` on a constructed record | Direct field swap, fed to `map_claim_to_alpha` and `extract_structures_from_records` | Both silently pass the swapped values through with zero validation | **NOT CAUGHT — TEST GAP** (no test constructs this; no code validates ID field shape/semantics) |
| 8 | Force-monkeypatch LLM structure-extractor to emit `assertion_status="asserted"`, `confidence=0.95` for a negated sentence ("AI capex does not drive GPU demand.") | Fake `llm_gateway` payload via real `Week2LLMGateway` | `assertion_status` is deterministically corrected to `"negated"` (structure_extractor.py:425-428) but `confidence` stays at the attacker/LLM-supplied `0.95` (not re-derived) | **PARTIALLY CAUGHT** — assertion_status is protected, confidence is not; no test covers this combination |
| 9 | Bypass evidence validation: monkeypatch `_llm_relation_is_evidence_backed` to always return `True`, feed unrelated-context text with no real causal/supportive language | Direct monkeypatch of the module function, real `Week2LLMGateway` | Before: `edges=[]` (correctly rejected). After: a fabricated `causal` edge with `confidence=0.99` and `reason="...passed deterministic evidence validation"` (false) is persisted | **NOT CAUGHT — no test targets `_llm_relation_is_evidence_backed` directly; only indirectly covered via an unrelated "invented factor" test that exercises a different check** |

---

## 6. Confirmed defects

| Sev | file:function | Test | Actual problem | Why tests missed it | Minimal repro | Blast radius | Fix direction |
|---|---|---|---|---|---|---|---|
| **P1** | structured_output_adapter.py:287-289 (`extract_claim_segments`) | none | Disclaimer-marker check operates at the raw-markdown-*line* level and drops the entire line (via `continue`, no partial retention) when any disclaimer phrase appears anywhere on it — even if real, unrelated claims share the same paragraph/line. | Existing test (`test_long_markdown_report_splits_into_traceable_claims`) only places the disclaimer on its own isolated paragraph. | `extract_claim_segments("AI training demand is accelerating. GPU demand is rising as cloud providers expand capacity. This is not investment advice.")` → `[]` (all 3 sentences lost) | High — this is the entry point for the whole Week 2 pipeline; any agent output that appends a disclaimer to the tail of its final paragraph (common in LLM-generated reports) silently loses that paragraph's claims with no warning/log entry. | Split into sentences first, then filter disclaimer sentences individually (reorder the pipeline: sentence-split before disclaimer-check, or check disclaimer per-sentence not per-line). |
| **P1** | structured_output_adapter.py:502-568 (`_validated_llm_segments`) / :674 (`adapt_raw_agent_outputs`) | none | LLM-supplied `direction` is accepted with only a `VALID_DIRECTIONS` bounds check; it is never reconciled with the independently and always-recomputed `assertion_status`/`semantic_polarity` from the same text. A negated/no-evidence claim can be persisted with `direction="positive"`. | No test in test_week2_llm.py or test_structured_output_adapter.py checks LLM-direction vs. semantics agreement. | Mocked `Week2LLMGateway` returning `direction:"positive"` for raw_text `"There is no evidence that AI demand is increasing for NVIDIA GPUs."` → persisted record has `direction=positive`, `assertion_status=negated`, `semantic_polarity=mention` simultaneously. | Moderate-High — `alpha_mapper.direction_score` recomputes relation fresh from text and is not fooled (relation=`mention`→0.0), but the persisted `structured_agent_outputs.json` artifact itself is corrupted for any other consumer (Week 3 graph, dashboards, human QA, future direction-trusting code). | After computing `semantics = analyze_claim_semantics(...)`, force `direction` to `"neutral"` (or re-derive via `infer_direction`) whenever `semantics.negated` or `semantics.mixed`, regardless of extraction_method. |
| **P2** | structure_extractor.py:370-443 (`_validated_llm_edges`) | none | `assertion_status` is deterministically corrected against `semantics.negated`/`.conditional`, but `confidence` is taken verbatim from the (LLM-supplied) payload and never re-derived to match the corrected status — unlike the deterministic path's `_relation_confidence`, which forces `negated→0.35`. | No test constructs an LLM edge where the LLM's claimed `assertion_status` disagrees with the text's actual negation/conditionality. | Fake gateway proposes `assertion_status="asserted", confidence=0.95` for "AI capex does not drive GPU demand." → persisted edge has `assertion_status="negated"` (correctly overridden) but `confidence=0.95` (not overridden). | Low-Moderate — misleading confidence on an already-correctly-labeled-negated edge; could inflate apparent signal strength downstream. | After overriding `assertion_status` in the negated/conditional branch, also clamp/recompute `confidence` via `_relation_confidence(edge_type, assertion_status)` or an equivalent cap. |
| **P2** | structure_extractor.py:353-368 (`_llm_relation_is_evidence_backed`) | none directly (only indirectly via an unrelated "invented factor" test) | The specific function that stops an LLM from hallucinating a relation between two factors that are individually mentioned but never actually related in the text has no direct unit test; a regression here (e.g., accidentally weakening the pattern check) would not be caught by the existing suite. | test_week2_llm.py's two edge tests use either a clearly evidence-backed relation or an invented factor (caught by a *different* check, `source_factor not in allowed`). | Monkeypatched `_llm_relation_is_evidence_backed = lambda *a, **k: True`; fed "Both AI demand and GPU demand were casually referenced in an unrelated footnote." through the real `Week2LLMGateway` → a fabricated causal edge (confidence 0.99) is persisted with the (now-false) reason string "passed deterministic evidence validation." | Moderate — this is the primary defense against LLM relation hallucination for well-formed (both-factors-present) inputs; it currently has zero regression coverage. | Add a unit test for `_llm_relation_is_evidence_backed` directly, and an integration test where both factors are valid/allowed but no relation language connects them. |
| **P2** | structured_output_adapter.py:303 (`extract_claim_segments`, sentence regex) | none | Sentence splitter has no abbreviation awareness (`Mr.`, `vs.`, `U.S.`, `Inc.`, etc.); real financial/analyst prose containing these produces truncated, semantically incomplete claim fragments, with the truncated remainder silently dropped by the length filter. | No fixture/test contains any common abbreviation. | `"Mr. Huang said demand remains robust vs. last year."` → surviving claim is `"Huang said demand remains robust vs."` (comparison target silently lost). | Low-Moderate — degrades claim quality/completeness for a common real-world pattern in analyst reports; no crash, no schema violation, just information loss. | Add a small abbreviation exception list to the sentence-boundary regex (e.g., negative lookbehind for common abbreviations) or use a proper sentence tokenizer. |
| **P2 / fixture-specific tuning (flagged per instructions)** | factor_normalizer.py:70,85,95,104,106,123-124 (`FACTOR_ALIASES`) | tests/golden_cases/labeled_claims_v1.json (indirectly, via test_alpha_mapper.py / test_week2_labeled_accuracy.py) | Several factor-alias phrases (`"priced for perfection"`, `"reserves rise"`, `"theme flows"`, `"wafer orders"`, `"asp stabilizes"`, `"token generation"`, `"copilot usage"`) are verbatim substrings of the fixed 20-case golden test sentences, and git history shows the alias table was authored (commit `7b8d3b7`, 2026-07-10) strictly *after* the golden-case file (commit `7d6d5c7`, 2026-07-09). This is not a literal `if fixture_id == ...` branch, but functions as reverse-engineered, test-set-specific tuning of a "generic" lookup table that the 20-case gate depends on. | The 20-case gate only checks whether `map_claim_to_alpha` reaches the right answer on those same 20 sentences — it cannot detect that the underlying alias table was shaped by those sentences. | Compare git blame of factor_normalizer.py (introduced 2026-07-10) against tests/golden_cases/labeled_claims_v1.json (introduced 2026-07-09); grep confirms exact phrase overlap. | Moderate — undercuts confidence that the "Clean 20-case gate: 20/20, 100%" number (doc C6) reflects genuine out-of-sample generalization; consistent with the real, independent NVDA fixture scoring markedly lower (76.7% strict / 96.7% allowed, doc C7, reproduced live). | Either document the alias table's provenance honestly (acceptable if the taxonomy vocabulary genuinely is this specific), or validate generalization against a held-out set whose text was never used to write `FACTOR_ALIASES`. |
| **P3 (test-effectiveness, not a code defect)** | tests/test_alpha_mapper_nvda_real_report.py:150-155 | itself | The only externally-sourced (non-tuned) accuracy check computes real strict/allowed accuracy but asserts nothing unless `COMQUTOR_ENFORCE_REAL_NVDA_GATE=1` is exported; the default `pytest` run makes this test unconditionally pass regardless of the underlying numbers. | N/A — self-referential. | `pytest tests/test_alpha_mapper_nvda_real_report.py -q` exits 0 regardless of accuracy; confirmed live accuracy is 76.7%/96.7%. | Low — honestly disclosed as diagnostic in the doc (C8), but worth flagging since it is Week 2's only check against non-tuned text and it is a no-op by default in CI. | Consider enabling the gate by default at a conservative floor (e.g. `allowed >= 0.65` as the doc's own suggested default), or clearly mark it `pytest.mark.skip`-by-default rather than silently-vacuous-by-default. |
| **P3** | alpha_mapper.py:174-501 / structure_extractor.py:121-142 (`_source_record_id`, downstream ID consumers) | none | `claim_id` and `source_agent_output_id` are trusted verbatim from the input record with zero shape/semantic validation; a caller bug that swaps them propagates silently into `alpha_matches.json`/`extracted_structures.json`. | No test constructs a field-swap scenario. | Constructed record with `claim_id`/`source_agent_output_id` values swapped → both `map_claim_to_alpha` and `extract_structures_from_records` echo the swap without complaint. | Low under the current contract (the adapter always generates well-formed IDs), but zero defense-in-depth if that contract is ever violated upstream. | Add a light sanity check (e.g., `claim_id` should end in `:claim:N`) with a warning/error path, mirroring the existing `validate_structured_output` pattern. |

---

## 7. Week 2 verdict

**VERIFIED_WITH_LIMITATIONS.**

The core architectural claims hold up under direct adversarial testing: the deterministic admissibility gate for Alpha matching is genuinely independent of the LLM and cannot be bypassed to create, resurrect, or admit an out-of-taxonomy or non-admissible alpha (Q3/Q4, confirmed with live monkeypatched malicious gateways); the 0.35 threshold is exactly what the doc claims with a correctly inclusive boundary (Q5); negated/conditional/no-evidence causal language does not produce a false *asserted* edge (Q6, matches the doc's precise wording); the deterministic-vs-LLM output contract does not diverge in shape (Q8); and claims from distinct sources sharing a raw output ID are not falsely merged (Q7). All of these were reproduced by directly invoking the real production entrypoints, not reimplemented test logic — the test suite for these paths is genuinely STRONG.

However, five concrete, reproducible problems limit full confidence: (1) the claim splitter can silently drop entire paragraphs of legitimate signal when disclaimer boilerplate shares a line with real content — a realistic, untested failure mode at the very front of the pipeline; (2) the LLM extraction path can persist internally self-contradictory records (`direction=positive` next to `assertion_status=negated`) because direction is never reconciled against independently-computed semantics; (3) the LLM structure-extraction path corrects a hallucinated `assertion_status` but not the accompanying `confidence`, so a "negated" edge can still carry high confidence; (4) the evidence-backing check that stops LLM relation hallucination (`_llm_relation_is_evidence_backed`) has no direct regression test; and (5) the factor-alias vocabulary that the flagship "20/20, 100%" gate depends on shows git-history-confirmed evidence of having been authored from the golden test sentences themselves, which is corroborated by the sharp accuracy drop (76.7% strict) on the independent, never-tuned-against NVDA real-report fixture — whose own accuracy gate is a no-op by default in CI. None of these are fabricated-metric or hard case-ID-branch violations (no literal `if fixture_id == ...` code was found), and the doc is honest about NVDA being diagnostic-only, but the 20-case "clean gate" number should not be read as evidence of strong out-of-sample generalization.
