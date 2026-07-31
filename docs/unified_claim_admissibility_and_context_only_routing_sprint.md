# Unified Claim Admissibility and Context-Only Routing Sprint

## A. Baseline

- Branch: `comqutor-structure-layer`
- HEAD: `2fe129705d824d46b4bcf7f0fc1eb43e27972824` (unchanged throughout this Sprint)
- Worktree at start: clean except the still-uncommitted Structure Graph Deterministic Relation Grammar Sprint's own changes (`relation_grammar.py`, its `structure_extractor.py`/test edits, and its report doc) and one untracked doc from the Factor Resolution Contract Review — none of which this Sprint modified further except where explicitly noted below.
- Tests before (full offline suite, `python -m pytest -m "not integration" -q`): 2066 passed, 1 skipped, 47 deselected, 0 failed.
- Ruff before: clean on all files this Sprint went on to touch.

## B. Existing relation logic found (Phase B/C equivalent for this Sprint)

- `structured_output_adapter.classify_filtered_claim()` already filtered pure meta-commentary/transition/disclaimer *sentences* during Markdown segmentation, but only for the **deterministic splitter** path (`extract_claim_segments_with_audit`).
- `_validated_llm_segments()` (the LLM path) validated schema shape, bounds, and "evidence must appear verbatim in the raw report" -- but applied **no quality judgment at all**. An LLM-proposed claim of pure narration ("Let me synthesize everything.") would pass validation and become a real structured record.
- `direction == "unknown"` was overloaded exactly as the brief described: a placeholder-error record, a genuine fact with no stock direction, a factor-relation claim with no polarity, and process language all produced the same value, with no way to distinguish them downstream.
- No shared eligibility concept existed: Mapper's only gate was a bare `claim.lower() == "unknown"` string check; Structure Extractor, Activation, and Conflict had no claim-quality concept whatsoever.

## C. Files changed

- **`comqutor_alpha/structure_engine/claim_quality.py`** (NEW) -- the entire Claim Quality Gate: `classify_claim_quality()`, feature extraction, and the shared `is_claim_eligible()` eligibility matrix. No I/O, no DB, no Provider/LLM/network, no Mapper/Graph imports (only `claim_semantics`, `factor_normalizer`, `relation_grammar`, `structure_schema`).
- **`comqutor_alpha/structure_engine/structured_output_adapter.py`** -- unified extraction boundary: `_build_records_from_segments()` (new helper, applies `classify_claim_quality` to every segment from either path), restructured `adapt_raw_agent_outputs()` (LLM segments built and classified first; if any survive, used; if none survive but some were proposed, falls back to the deterministic splitter; if the deterministic path also yields nothing, the existing `safe_default_record` fail-soft path is used), `safe_default_record()` now stamps `claim_quality="non_substantive"`, `claim_quality_reason_codes=["PLACEHOLDER_UNKNOWN"]`, `analysis_eligible=False`. `adapt_run_outputs()` now threads a `quality_audit` accumulator through every raw output and folds 8 new counters into `metadata`.
- **`comqutor_alpha/structure_engine/alpha_mapper.py`** -- `map_structured_records()`'s bare `claim == "unknown"` check replaced with `is_claim_eligible(record, CONSUMER_MAPPING)`; `map_claim_to_alpha()`'s result additively carries `claim_quality` through to `alpha_matches.json` so downstream readers never need to recompute it from a possibly-narrower factor list.
- **`comqutor_alpha/structure_engine/structure_extractor.py`** -- `extract_structures_from_records()` now computes each record's candidate edges (unchanged logic) *before* deciding node/edge admission, then gates on `is_claim_eligible(record, CONSUMER_STRUCTURE, has_relation_candidate=bool(extracted_edges))`.
- **`comqutor_alpha/graph_engine/activation_scorer.py`** (v1) -- `_gather_alpha_evidence()` gates each candidate record on `is_claim_eligible(record, CONSUMER_ACTIVATION)` before it can become committed/ambiguous evidence.
- **`comqutor_alpha/graph_engine/activation_scorer_v2.py`** -- same gate added to `_gather_qualifying_evidence()` and `_gather_direction_evidence()`.
- **`comqutor_alpha/conflict_engine/conflict_detector.py`** + **`conflict_schema.py`** -- new `EXCLUDED_NON_ANALYTICAL_QUALITY` reason code; `_gather_qualifying_evidence()` gates each candidate on `is_claim_eligible(record, CONSUMER_CONFLICT)` alongside its pre-existing `match_status`/`matched_alpha` checks.
- **`comqutor_alpha/storage/db/repository.py`** -- `persist_agent_outputs()` (the persistence admission boundary) now filters `structured_payload["records"]` to drop any record `is_claim_eligible(record, CONSUMER_ANALYTICAL_PERSISTENCE)` rejects, *before* building/inserting DB rows. No schema/migration change: `claim_quality` is never stored as its own DB column -- the API-facing read side can recompute it losslessly from the columns already persisted (`claim`, `evidence`, `entities`, `factors`, `direction`, `assertion_status`), since `classify_claim_quality` is a pure function of exactly those fields. (See "Remaining limitations" for the one place this recompute is not yet wired in.)
- **`comqutor_alpha/api/routes_research.py`** -- `build_run_audit_payload()` reads the 8 new adapter metadata counters and folds them into `run_audit.json`, additively.
- **Tests**: `tests/test_claim_quality.py` (NEW, 56 tests), `tests/test_structured_output_adapter.py` (+10 tests), `tests/test_structure_extractor.py` (+4), `tests/test_alpha_mapper.py` (+2), `tests/test_activation_scorer_v2.py` (+2), `tests/test_conflict_detector.py` (+1), `tests/test_agent_outputs_persistence.py` (+1). `tests/test_activation_scorer.py`, `tests/test_activation_scorer_v2.py`, `tests/fixtures/week4_conflict_cases.py` also had their shared synthetic-fixture helpers updated (see Section E).

## D. Classifier design

### Quality classes and priority-ordered rules

1. **Hard rejects (NON_SUBSTANTIVE)**, checked first, in order: placeholder/empty (`PLACEHOLDER_UNKNOWN`) &rarr; disclaimer (`DISCLAIMER_ONLY`) &rarr; meta-commentary without any independent substantive signal (`BOILERPLATE_META_COMMENTARY`) &rarr; transition without substance (`NON_ASSERTIVE_TRANSITION`).
2. **ANALYTICAL**: an external/domain subject (a domain-anchor term, a resolved factor, or a resolved entity) *and* at least one of: a state/change predicate, a risk/forecast predicate, a relation predicate (reusing `relation_grammar`'s own compiled patterns plus `CONFLICT_WORDS` -- never a second, drifting vocabulary), or an explicit directional signal. Direction is never required to be non-`"unknown"`.
3. **CONTEXT_ONLY**: an external/domain subject with no analytical signal. Deliberately *not* restricted to a fixed "event verb" list (see Section D.1 below for why).
4. **Conservative default (NON_SUBSTANTIVE)**: no external/domain subject at all.

Complexity is O(n + p): one light-normalization pass, then a fixed, small number of compiled alternation patterns each doing one `.search()`/`.finditer()` -- never a per-word or per-phrase combinatorial search.

### Shared eligibility matrix (`is_claim_eligible`)

| consumer | ANALYTICAL | CONTEXT_ONLY | NON_SUBSTANTIVE |
|---|---|---|---|
| mapping | Yes | Yes (factor/Alpha context) | No |
| structure | Yes | only if a legal relation was found for *this* claim | No |
| activation | Yes | No | No |
| conflict | Yes | No | No |
| product_findings | Yes | No (default hidden) | No |
| analytical_persistence | Yes | Yes (tagged context_only) | No |

`is_claim_eligible` prefers an already-stamped `claim_quality` field (the adapter's own classification, computed once with full context); when absent (historical records predating this Sprint), it lazily recomputes -- a pure function of the record's own already-persisted fields, so replaying an old artifact never requires writing back to it.

### D.1 Two scope decisions forced by real production data

**1. CONTEXT_ONLY is not gated by a fixed "event predicate" vocabulary.** The original design required `has_external_subject and has_event_predicate` (report/announce/launch/introduce/sign/acquire/raise-or-cut-guidance) for CONTEXT_ONLY. A full read-only sweep of all four real completed runs (AMD/MU/NVDA/SNDK's `structured_agent_outputs.json`) showed this rejected **roughly half of every run's genuinely substantive claims** as NON_SUBSTANTIVE -- bare price prints ("AMD closed at $521.95..."), technical-indicator readings (RSI/MACD/ATR/SMA/VWMA), balance-sheet figures, analyst-rating changes, deal headlines, and quoted social-sentiment text, none of which use the fixed event-verb list. Since every real claim's `entities` unconditionally includes the run's own ticker (`extract_entities()` always prepends it), `has_external_subject` is in practice always true for real data; the discriminating job falls entirely on the predicate check, and a fixed ~30-term vocabulary cannot cover the realistic breadth of factual assertions a trading-research report makes. **Fix**: CONTEXT_ONLY now only requires `has_external_subject` once ANALYTICAL and the four hard-reject checks have already been ruled out -- `has_event_predicate` is still computed and exposed in `feature_flags` for audit, it is simply no longer a required gate. Verified this does not let meta-commentary through: `has_meta_commentary`/`has_transition_language` are checked *before* this fallback and are themselves keyed off *text-only* signals (see the next paragraph), so genuine process language is still rejected regardless of `entities`.
- A related, more serious bug this surfaced and fixed: the original `has_any_substance` carve-out (which suppresses the meta-commentary/transition hard-reject when a sentence also states something real) included `has_external_subject` in its OR-list. Combined with the ticker always being present in `entities`, this silently disabled meta-commentary detection *for every real adapter call* (only the earlier, entity-free standalone tests were passing). Caught via a failing test (`test_llm_path_keeps_only_the_real_claim_when_one_of_two_is_process_language`) before it reached the replay. Fixed by rebuilding `has_any_substance` from text-only signals (`analytical_signal`, `has_event_predicate`, `has_quantitative_anchor`, `has_domain_anchor`, `has_factor`, plus the reused legacy `_SUBSTANTIVE_SIGNAL_PATTERN`) -- never `has_entity`.

**2. `is_claim_eligible`'s activation/conflict branch does not re-check the claim's own generic `direction` field.** The spec's eligibility table describes ANALYTICAL's activation/conflict row as "only if direction is positive/negative." Implemented literally (even loosened to "not unknown"), this broke two existing, must-pass, real end-to-end pipeline tests: `test_week4_golden_closure.py`'s QQQ fixture (Liquidity Expansion claims with `direction="neutral"`) and `test_week3_nvda_sanity.py`'s NVDA fixture (Datacenter CapEx / Semiconductor Cycle claims with `direction="unknown"`, e.g. "Datacenter spending is expanding..." -- a real, correctly-matched claim whose own `infer_direction()` word-count heuristic simply does not contain a listed bullish/bearish word). In both cases the claim is genuinely analytical, genuinely matched, and the Mapper's own alpha-relative `relation` field (`activation`/`conditional`/`mixed`, which both Activation formulas already score on, unchanged) correctly treats it as real supporting evidence -- a second, cruder, alpha-agnostic `direction` re-check on top of that can only ever be redundant or actively wrong. **Fix**: `is_claim_eligible` returns `True` unconditionally for every consumer when `quality == ANALYTICAL`; whether -- and how strongly -- the evidence counts toward one specific alpha remains entirely governed by the existing, frozen `relation`-based mechanism. This is documented in the function's own docstring with both pieces of forcing evidence.

## E. Test fixture updates (pre-existing files, not authored by this Sprint)

`tests/test_activation_scorer.py`'s `_match()`, `tests/test_activation_scorer_v2.py`'s `_record()`, and `tests/fixtures/week4_conflict_cases.py`'s `match_record()` are shared synthetic-fixture builders used across dozens of pre-existing formula/admissibility tests. None of them previously set a `claim_quality` field (it did not exist), and several use deliberately generic evidence text (`"evidence for {claim_id}"`) that this Sprint's classifier correctly has no way to call analytical. Each helper now defaults `claim_quality="analytical"`, `direction="positive"` (overridable per test) -- these tests exist to isolate the Activation/Conflict *formula* from claim-quality concerns, so tagging their synthetic fixtures as already-quality-gated is the correct, minimal fix rather than a workaround. One test (`test_mutation_conflict_formula_min_to_max_still_fails_existing_tests`) builds its `alpha_matches` inline rather than through a helper and was updated the same way, in place.

## F. Correctness

- All 6 required NON_SUBSTANTIVE sentences verified rejected, both standalone and with a real ticker in `entities` (the harder, real-world case).
- All 6 required "must keep" sentences verified classified exactly as specified (4 analytical, 2 context_only), both standalone and with entities.
- `AI infrastructure demand drives storage demand.` verified ANALYTICAL with `direction="unknown"` explicitly passed -- confirms ANALYTICAL never requires a resolved direction.
- `"Volume shows signs of weakness in the chart."` verified `has_event_predicate == False` -- the common analyst idiom "signs of weakness" (noun) does not get misdetected as the event-predicate verb "signs" (a contract).
- Input-order independence verified: reordering `factors`/`entities` lists produces an identical `quality_class` and `reason_codes`.
- `is_claim_eligible` verified for all 6 consumers x all 3 quality classes, including: lazy reclassification of a record with no stamped `claim_quality` (and confirmed the record itself is never mutated by that fallback); a stamped `claim_quality` is trusted verbatim even when the record's own text would independently classify differently; an unknown consumer name raises `ValueError`.

## G. Replay (read-only; isolated pre-Sprint baseline via `git show HEAD:<path>` + `importlib`, never the live worktree; recomputed from a scratchpad copy of each run's own `raw_agent_outputs.json`, never the real `outputs/runs/<run_id>/` directory)

`llm_enabled: false` confirmed for all four runs both before and after (no Provider/LLM path exercised by this replay). Mapper-level counts (`mapper_input_count`, `activation_matched_count`, `unknown_direction_records`) are byte-identical before/after for all four runs, confirming Mapper scoring is untouched; the new columns show this Sprint's actual, isolated effect.

| Ticker | Records | Analytical | Context-only | Non-substantive removed | Structure edges (before&rarr;after) | Activation v2 qualifying evidence (matched &rarr; quality-gated) | Conflict admitted |
|---|---|---|---|---|---|---|---|
| AMD  | 669 | 331 | 338 | 0 | 0&rarr;0 | 23 &rarr; 20 | 2 |
| MU   | 654 | 317 | 337 | 0 | 0&rarr;0 | 15 &rarr; 11 | 0 |
| NVDA | 678 | 328 | 350 | 0 | 0&rarr;0 | 20 &rarr; 11 | 0 |
| SNDK | 661 | 371 | 290 | 0 | 2&rarr;2 | 21 &rarr; 14 | 0 |

- **Zero non_substantive removals** across all four real runs -- expected, not a classifier weakness: the deterministic splitter's pre-existing sentence-level boundary (`classify_filtered_claim`) already strips pure meta-commentary/transition/disclaimer *before* a segment is even built, for the path all four of these real runs actually used (`llm_enabled: false`). This Sprint's NON_SUBSTANTIVE detection was independently verified against the LLM path (which has no such pre-filter) via `test_llm_path_keeps_only_the_real_claim_when_one_of_two_is_process_language` / `test_llm_all_process_language_falls_back_to_deterministic_and_recovers_real_claim`, and against real research-debate-style text pulled from these same four runs' own claims (e.g. "Let me synthesize everything.", "Let me dismantle this argument piece by piece.") during the diagnostic sweep that led to the Section D.1 fixes.
- **AMD/MU/NVDA structure edges: 0&rarr;0.** Unchanged and correctly so -- these three runs' zero-edge status predates and is independent of this Sprint (established by the prior Relation Grammar Sprint).
- **SNDK structure edges: 2&rarr;2, preserved exactly.** Confirmed by direct inspection: claim `8d21c047-fc0a-4d94-957d-3787f353a544:sentiment_agent:sentiment_report:claim:49` --
  - Text: *"AI infrastructure demand driving memory — NAND flash and storage demand from AI data center buildout is the fundamental bull thesis, reinforced by Zacks, Motley Fool, and StockTwits analysts alike."*
  - `claim_quality: analytical` (`ANALYTICAL_RELATION_SIGNAL`), `direction: unknown`.
  - Relation: `AI Infrastructure --causal--> Semiconductor Cycle` (`forward_transitive_causal`, confidence 0.84, asserted).
  - Present in `extracted_structures.json`'s edges and in the final admitted `structure_graph.json` edge (`alpha_ids: ["A103"]`) -- unchanged by this Sprint. This is the real positive-edge case the brief requires; it is not degraded by direction=unknown or by context-only routing, because it is (correctly) ANALYTICAL, and ANALYTICAL structure-eligibility never depended on direction.
- **Activation v2 qualifying-evidence count drops below the raw matched count on every run** (23&rarr;20, 15&rarr;11, 20&rarr;11, 21&rarr;14) -- this is the Sprint's intended effect, made visible: some of each run's `match_status=="matched"` claims are `context_only`-tagged factual statements (revenue prints, product announcements, analyst quotes) that the Mapper still scores (mapping stays eligible for context) but that now correctly no longer count as Activation evidence.
- No historical artifact was written to at any point: verified via `mtime` comparison of `structured_agent_outputs.json` in all four real run directories, taken immediately before and again immediately after the full replay -- byte-identical. No `error_logs/` directory appeared in any real run directory (the isolated old/new adapter recomputations' own error-log side effects were confined to the scratchpad copy).

## H. Validation

- Targeted tests (all Sprint-relevant files together): **497 passed**, 0 failed.
- Full offline suite (`python -m pytest -m "not integration" -q`): **2137 passed, 1 skipped, 47 deselected, 0 failed** (baseline before this Sprint: 2066 passed).
- Ruff: `All checks passed!` on every file this Sprint touched.
- `git diff --check`: clean.
- `tradingagents/` modified: No. Mapper weights/scoring/eligibility logic modified: No (only its outer `map_structured_records` admission filter and an additive `claim_quality` passthrough field). Activation formulas/weights/caps modified: No (only an additive evidence-gathering filter, applied before the unchanged formula runs). Conflict pair taxonomy / conflict score formula / `contradiction_weight` modified: No (only an additive per-claim exclusion reason alongside the pre-existing ones). Relation grammar rules modified: No. Frozen seed data / alpha IDs / API contract / frontend / historical artifacts: untouched. No database migration created (not needed -- see Section C). Provider calls: 0. LLM calls: 0 (the two LLM-path tests use a local fake gateway object, never a network call). Database writes: 0 (all persistence tests run against an in-memory SQLite engine created fresh per test). Historical artifact writes: 0 (verified above).

## Remaining limitations

- **`comqutor_alpha/api/agent_output_reader.py` (the public `GET /api/research/{run_id}/agent-outputs` projection) was deliberately not wired to recompute or expose `claim_quality`.** This is a security-hardened whitelist projector (explicitly labeled "W4.3 security patch" in its own docstring) outside this Sprint's named allowed-file list, and no test requires it. `is_claim_eligible`'s `product_findings` consumer branch is fully implemented and unit-tested as a pure function (default-hides context_only, always excludes non_substantive), so wiring it into this specific endpoint is a small, well-scoped, and recommended follow-up -- not started here to avoid touching a deliberately narrow security boundary without an explicit ask.
- The one deliberately-deferred, non-hypothetical CAUSAL_RANK gap from the prior Sprint (a risk factor causally pressuring a rank-1 demand factor) is unchanged and still open; out of this Sprint's scope (relation grammar rules were not touched).
- The AMD claim-alias gaps identified by the earlier Factor Resolution Contract Review remain open and unaffected by this Sprint.

## Sprint

Unified Claim Admissibility and Context-Only Routing Sprint

## Status

PASS

## Commit/push

Not performed.
