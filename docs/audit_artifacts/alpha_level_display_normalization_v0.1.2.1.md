# Alpha-Level Display Normalization — v0.1.2.1 (Step 7)

**Presentation/audit normalization only.** B4 (`alpha_level_classifier`) remains the sole activation authority — activation scores, thresholds (50/70/86), evidence requirements, cap logic, B1, B2, and Step-6 evidence qualification are all unchanged.

Branch `comqutor-structure-layer`, HEAD `9f228723fad5406c72e62beca67ec70ea0fdb004` (unchanged — no commit, no push). Zero Provider calls, zero TradingAgents calls.

## Key discovery: most of this already exists

Before writing any code, an inventory pass found that `comqutor_alpha/graph_engine/alpha_level_classifier.py` **already is** the centralized B4 display authority John is asking for, built and wired into `graph_engine/pipeline.py` by an earlier task (`B4_ACTIVATION_LEVEL_ALIGNMENT`):

- Four canonical levels (`candidate`/`active`/`dominant`/`regime_level`), plus a presentation-only `activation_level` field that adds `capped_active` — exactly John's vocabulary, minus `candidate_active`.
- `is_blocked` / `blocked_from` / `blocked_reason_codes` / `diagnostic_reason_codes` — already an orthogonal gating dimension, separate from the four levels, exactly the shape this task's section 7 asks for.
- A canonical 4-value `blocked_reason_codes` mapping table, already preserving raw diagnostic codes.
- **`candidate_active` was already investigated and explicitly rejected** by that same prior task — pinned permanently by `tests/test_b4_activation_level_alignment.py::test_i_candidate_shows_plain_candidate_no_authoritative_candidate_active_definition` and documented in `frontend/src/api/types.ts`'s `ACTIVATION_DISPLAY_LEVELS` comment.

Given this, Step 7's job was: (1) confirm and re-verify this precedent rather than silently overriding it, (2) build one thin, additive normalization wrapper that maps the existing authoritative fields onto John's exact requested output-field names without duplicating or re-deriving any of the underlying logic, and (3) produce the real six-ticker audit + artifacts this task requires. No B4 code was modified.

## candidate_active: `CANDIDATE_ACTIVE_REQUIRES_PRODUCT_DEFINITION`

Re-confirmed by grep across `comqutor_alpha/`, `frontend/src`, `tests/`, `docs/`: no authoritative definition for a state distinct from plain `"candidate"` exists anywhere. Per this task's own explicit instruction not to fake a definition, `display_level` for a candidate-level Alpha stays exactly `"candidate"` — never `"candidate_active"`. This status is reported, not invented.

## capped_active and blocked: reused exactly, no new code

- **`capped_active`**: `display_level == "capped_active"` iff `qualified_level == "active"` AND `is_blocked` AND `"dominant" in blocked_from` (`alpha_level_classifier._activation_level_for`, pre-existing, unmodified). A genuinely dominant/regime_level Alpha is never downgraded to `capped_active`, even if itself blocked down from a still-higher target.
- **`blocked`**: already orthogonal — `blocked` (bool) + `blocked_reason_codes` (canonical 4-value: `NO_LOCAL_STRUCTURE_SUPPORT`, `INSUFFICIENT_EVIDENCE`, `LOW_ENTITY_EXPOSURE`, `NO_TICKER_SPECIFIC_EVIDENCE`) + `cap_reason_codes` (raw, uncanonicalized) exposed alongside `display_level`, never replacing it. An Alpha can show `display_level=capped_active, blocked=true, blocked_reason_codes=[...]` simultaneously, exactly as this task's preferred shape describes.

## New centralized wrapper

`comqutor_alpha/graph_engine/alpha_display_normalizer.py` — `normalize_alpha_display_state(entry)` / `normalize_alpha_display_states(entries)`. Input: one already-classified Activation v2 entry (post `classify_and_rebuild_collections`). Output: `alpha_id`, `activation_score` (unchanged passthrough), `authoritative_level`, `display_level`, `blocked`, `blocked_reason_codes`, `cap_reason_codes`, `display_explanation` (deterministic, reason-code-driven, never new product copy), `ambiguous`, `normalization_contract_version`. Never recomputes activation, never touches evidence/claims — confirmed by a dedicated test asserting the function's only parameter is the entry itself. Fails conservatively to `UNKNOWN_DISPLAY_STATE` on any missing/malformed authoritative field, never guessing a high level.

## Precedence

`regime_level > dominant > capped_active > active > candidate` — confirmed against the actual B4 model: this ordering is already implicit in `classify_alpha_level`'s own Case A→D arbitration (Case D/regime checked first, then C/dominant, then A/B/candidate-active), never reimplemented or reordered by the new wrapper, which only reads the already-arbitrated result.

## Truth Table (see JSON `truth_table` for full detail)

| Row | Condition | Authoritative qualified_level | blocked | display_level |
|---|---|---|---|---|
| A | score ≥ 86, regime gate passes | regime_level | false | regime_level |
| B | 70 ≤ score < 86, no dominant cap | dominant | false | dominant |
| C | 50 ≤ score < 70, never targeted dominant | active | false | active |
| D | uncapped ≥ 70 but capped to active by an existing dominant-cap reason | active | true | **capped_active** |
| E | score < 50 | candidate | false | candidate (never "candidate_active") |
| G | zero qualifying evidence (score forced to 0) | candidate | false | candidate |
| H | score ≥ 50 with an authoritative gate blocking active itself | — | — | **not reachable** — B4's own Case A/B applies no qualification gate to candidate/active (confirmed by `test_b_candidate_and_active_never_gain_a_new_evidence_graph_or_exposure_gate`) |
| I | regime target, both regime gate fails and dominant cap reasons present | active | true, `blocked_from=[dominant, regime_level]` | capped_active, all distinct reason codes preserved |

## Six-Ticker Display Audit — 60/60

Using the real, persisted, **Step-6-qualified** `_step5a_coverage_{ticker}/alpha_matches.json` data (the same source Step 6 measured), scored via `score_alpha_activations_v2` and classified via the unmodified `classify_and_rebuild_collections`:

| Display level | Count |
|---|---|
| candidate | 40 |
| active | 20 |
| capped_active | 0 |
| dominant | 0 |
| regime_level | 0 |
| **blocked = true** | 0 |
| **ambiguous** | 0 |

**60 / 60 normalized, 0 ambiguous.** No exceptions, no fallback to `UNKNOWN_DISPLAY_STATE`.

**Scope note on the zero counts for capped_active/dominant/regime_level/blocked**: these `_step5a_coverage_*` directories (Step 6's own isolated validation output) contain only `alpha_matches.json` — no `structure_graph.json`/local-structure graph edges, no B3 Entity Exposure. `local_structure_support` (one of six weighted activation components) is therefore 0 for every alpha in this specific audit, which keeps every real score below the dominant/regime thresholds here — the same limitation Step 6's own before/after scoring scripts already had. This is an honest reflection of what this specific persisted dataset supports, not a defect in the normalizer: the 27 new deterministic tests (and the truth table above) independently prove `capped_active`, `dominant`, `regime_level`, and `blocked=true` are all produced correctly by the unmodified classifier whenever those signals are present, e.g. in a full production run with real structure-graph edges.

No canonical Alpha is misrepresented as artificially "active" — 40/60 (67%) correctly show `candidate`, reflecting genuinely weak/insufficient evidence per the already-existing B4 score bands, not cosmetically inflated.

## One legacy/inconsistent-terminology finding (documented, not touched)

`activation_scorer_v2.score_alpha_v2` writes its own raw `status` field via `activation_status_band_v2()`, using a **different** band table (`inactive`/`watch`/`active`/`dominant`/`regime_candidate` at thresholds 30/50/70/85) than `alpha_level_classifier`'s canonical bands (`candidate`/`active`/`dominant`/`regime_level` at 50/70/86). In the live pipeline this is harmless — `graph_engine/pipeline.py` immediately calls `classify_and_rebuild_collections`, which overwrites `status` with the true authoritative `qualified_level` before anything external ever reads it. It is a real trap, however, for any direct caller of `score_alpha_v2`/`score_alpha_activations_v2` that skips the classification step (this session's own earlier Step 5A/Step 6 before/after audit scripts did exactly this, which is why some of that reporting used words like "watch" that don't exist in the true B4 vocabulary). Flagged in the inventory per this task's section 3 instruction to document ambiguous/duplicated terminology honestly — **not modified**, since changing `activation_scorer_v2.py`'s own status/band logic is out of Step 7's presentation-only scope.

## Tests

27 new deterministic tests in `tests/test_alpha_display_normalization.py`, covering all 18 required cases (Cases 10–14 pin B4/B2 threshold/import invariants; Case 18 runs the real six-ticker data through the full normalize path with zero exceptions). All passing. The pre-existing `tests/test_b4_activation_level_alignment.py` (36 tests covering the underlying classifier in exhaustive detail) is unmodified and still green — reused as-is, not duplicated.

## Files

**Created:** `comqutor_alpha/graph_engine/alpha_display_normalizer.py`, `docs/audit_artifacts/alpha_level_display_normalization_v0.1.2.1.json`, this file, `tests/test_alpha_display_normalization.py`.
**Modified:** none (no existing production file needed a change — the authority already existed).
**Updated (additive):** `docs/audit_artifacts/qa_closure_index.json` (`step7_alpha_level_display_normalization` block).
**Not touched:** `alpha_level_classifier.py`, `activation_scorer_v2.py`, B1 stance module, B2/conflict_admissibility thresholds, Alpha Mapper, Alpha taxonomy, conflict ontology, regression labels, Step-6 evidence qualification, any historical Step 1–6 artifact.
**Provider calls:** 0. **TradingAgents calls:** 0. **Commit:** NO. **Push:** NO.
