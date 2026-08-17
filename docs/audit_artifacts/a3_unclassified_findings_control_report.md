# A3 Unclassified Findings Control — Final Report

**Task:** `A3_UNCLASSIFIED_FINDINGS_CONTROL`
**Branch:** `comqutor-structure-layer`
**HEAD:** `b5837e80a4550fc35165d0013a8ef0f27ccb4c8f` (unchanged throughout — no commit, no push)
**Commit:** none. **Push:** none. **Provider calls:** 0.

## Status

**A3 IMPLEMENTATION COMPLETE.**
**A3 FORMAL PRODUCT OWNER ACCEPTANCE PENDING** — every technical/functional completion criterion in task section 23 is met (see checklist at the end of this report); no human product-owner sign-off has occurred in this session.

No `UNCLASSIFIED_REASON_VOCABULARY_DECISION_REQUIRED` condition arose: every genuinely unclassified finding in the real saved run resolved to one of John's 5 canonical reasons (`unresolved_reason_count = 0`).

## 1. What this is

A presentation/audit control layer over already-computed upstream authorities. A3 never re-judges Alpha mapping (§5.2), never re-classifies Evidence Stance (B1), never re-groups Evidence Facts (Activation v2), never recomputes Activation/Conflict (B2–B4), never calls an LLM or Provider. It only:

1. Identity-joins `alpha_matches.json` ↔ `structured_agent_outputs.json` ↔ `evidence_facts.json` by `claim_id`.
2. Assigns each finding zero or more of John's 5 canonical reasons, purely from already-computed signals.
3. Computes one deterministic primary `reason` (frozen priority order) and a full `reason_codes` list.
4. Computes a deterministic Top-20 display order.
5. Persists an additive `unclassified_findings.json` artifact, wires it into the existing manifest/run_audit/download infrastructure, and drives a rebuilt frontend panel from it.

## 2. Files changed

**New:**
- `comqutor_alpha/api/unclassified_findings.py` — the single A3 module (reason evaluation, Top-20 ordering, artifact builder).
- `tests/test_a3_unclassified_findings_control.py` — 58 dedicated tests, sections A–G.

**Modified (all additive):**
- `comqutor_alpha/api/artifact_export.py` — registers `unclassified_findings.json` in `PRODUCT_EXTENSION_ARTIFACT_FILENAMES`; calls the new builder inside `finalize_completed_run_artifacts`, gated on `alpha_matches_payload is not None` (same precedent as `evidence_stance_audit.json`), reusing the `evidence_facts` export already computed in the same pass (never a second Evidence Fact Index read/build).
- `comqutor_alpha/api/routes_research.py` — `build_run_audit_payload` gains an additive `unclassified_findings` block (status/total_count/display_count/display_limit/reason_counts/unresolved_reason_count); `build_research_response` gains 5 additive top-level fields (`unclassified_findings_top20`, `_total_count`, `_reason_counts`, `_status`, `_download_available`).
- `comqutor_alpha/storage/file_store.py` — one line: `"unclassified_findings.json"` added to `ALLOWED_ARTIFACT_FILENAMES` (same pattern every prior Sprint/Track has used for its own new artifact).
- `frontend/src/api/types.ts` — new `UnclassifiedFinding` interface, `UNCLASSIFIED_FINDING_REASONS` const, 5 additive optional fields on `CanonicalResearchResponse`.
- `frontend/src/api/adapters.ts` — new `adaptUnclassifiedFinding`, wired into `adaptCanonicalResearchResponse` (explicit field-by-field extraction, not a narrow reconstruction that silently drops fields — see §7).
- `frontend/src/pages/ResearchRunPage.tsx` — removed the old `isDirectionalFinding`/`NeutralFindingsPanel` (direction-based, wrong data source); added `UnclassifiedFindingsPanel` + `UnclassifiedFindingCard`, driven entirely by the backend's A3 fields.
- `frontend/src/pages/ResearchRunPage.test.tsx` — updated the 4 tests whose assertions depended on the old panel; removed 1 test whose entire premise (client-side expand-to-reveal over structured claims) no longer applies; added 6 new tests for the rebuilt panel.
- `frontend/src/styles.css` — additive CSS for the new panel/card classes only.

**Not touched:** any B1–B5 computation module, the Alpha Mapper, `evidence_stance.py`, `activation_scorer_v2.py`'s scoring logic (only its existing `_is_ticker_specific` helper is imported), `conflict_detector.py`, `conflict_admissibility.py`, the taxonomy, A2's `REQUIRED_ARTIFACT_FILENAMES` tuple.

## 3. Root cause of the pre-A3 "neutral/unclassified" problem

The pre-existing `NeutralFindingsPanel` (`ResearchRunPage.tsx`) was driven by `isDirectionalFinding(direction)` — `direction === "positive" || direction === "negative"` — applied to raw `StructuredAgentOutputRecord[]` (i.e. `structured_agent_outputs.json`, the **pre**-Alpha-mapping data source). This conflated two independent concepts the task explicitly forbids conflating:

- **Claim-level `direction`** (§4.1) — an LLM-assigned tone (positive/negative/neutral/unknown) of the sentence itself, unrelated to whether the claim has a valid Alpha match.
- **"Unclassified"** (§4.3) — whether the claim entered the normal research-finding display path.

Concretely: a claim with `direction=neutral`, a real `matched_alpha`, a `supports_alpha` B1 stance, and ticker-specific text was **always** shown as "neutral and unclassified," even though it is a fully legitimate finding. Conversely, this data source has no `matched_alpha`/`evidence_stance`/duplicate-group fields at all, so **no version of John's 5 canonical reasons could ever have been computed from it** — a structural rewrite (new data source, new join) was required, not a label change.

## 4. Authoritative "unclassified" universe

Base universe: every record in `alpha_matches.json`'s `matches[]` array (1:1 with `structured_agent_outputs.json`, PD-014-compliant: no-match claims retained with `matched_alpha=null`, never dropped).

A finding is **unclassified** ⟺ at least one of John's 5 canonical reasons applies, evaluated purely from existing signals:

| Reason | Signal used | Precondition |
|---|---|---|
| `no_alpha_match` | `match.matched_alpha is None` | — |
| `generic_background` | `match.matched_evidence_stance ∈ {neutral_background, mentions_alpha}` (B1's own final stance, already promoted to the match record's top level by the Alpha Mapper) | `matched_alpha` present |
| `duplicate_supporting_text` | claim is a non-representative `member_claim_ids` entry of an `evidence_facts.json` group whose `supporting_alpha_ids` includes the claim's own `matched_alpha` | `matched_alpha` present |
| `no_ticker_specific_evidence` | `activation_scorer_v2._is_ticker_specific(match, ticker, (), {})` is `False` — the exact function and call convention B2's `conflict_admissibility.py` already uses (its own docstring: "behaviorally identical to production, not a new heuristic") | `matched_alpha` present |
| `low_confidence` | never assigned — see §5 | — |

A finding with **zero** applicable reasons is fully classified and is **not** included in the artifact at all — this is what correctly excludes a direction-neutral-but-validly-matched claim (§4.1's non-goal), by construction rather than by a special-cased exemption.

`UNCLASSIFIED_REASON_UNRESOLVED` fires only when `matched_alpha` is present but its stance is neither a known "classified" value (`supports_alpha`/`opposes_alpha`/`supports_counter_alpha`) nor a known background value (`neutral_background`/`mentions_alpha`) — a genuine data anomaly. On the real saved run this fired **0** times (test B11/B12 exercise it synthetically; it is expected to be rare/zero on well-formed data).

## 5. `low_confidence` — explicitly not populated

No formally defined, actually-used threshold against `StructuredAgentOutputRecord.confidence` exists anywhere in the repository (`rg` for `low_confidence|LOW_CONFIDENCE|confidence_threshold|MIN_CONFIDENCE` across `comqutor_alpha`: zero matches). Per the task's own explicit instruction, this module does **not** invent one.

One candidate existing signal was considered and explicitly **rejected**: `candidate_scores[].stance_confidence_band` / `matched_stance_confidence_band` (`evidence_stance.py`'s `CONFIDENCE_LOW`). This is a different concept — confidence in the Evidence Stance *classification itself*, not in the claim's own factual assertion — and every branch of `evidence_stance.classify_evidence_stance` that produces `CONFIDENCE_LOW` already produces a `neutral_background`/`mentions_alpha` stance too, meaning it would never win as *primary* reason under the frozen priority order anyway (`generic_background` outranks `low_confidence`) and would only ever be redundant `reason_codes` noise. Reusing it as a claim-level "low confidence" signal would repeat exactly the kind of confidence/relevance conflation PD-012 already forbids for match scores.

**Recorded finding: `LOW_CONFIDENCE_THRESHOLD_NOT_FORMALLY_DEFINED`.** `reason_counts["low_confidence"]` is always `0`; the reason remains in the vocabulary/schema for forward compatibility, never silently removed.

## 6. Primary-reason priority (frozen, tested)

```
1. duplicate_supporting_text
2. generic_background
3. low_confidence
4. no_alpha_match
5. no_ticker_specific_evidence
```

Locked by `test_b10_priority_order_is_frozen` (a literal tuple-equality assertion against `REASON_PRIORITY`). All applicable reasons — not just the primary — are preserved in `reason_codes` (`test_b9`).

## 7. Top-20 deterministic ordering

`(ticker_specific desc, confidence present-first then desc, claim_index present-first then asc, claim_id asc)`. Missing confidence/claim_index sort **after** present values (never guessed as 0/1 — tested D6). `display_rank` is assigned once, in this order, over the **entire** unclassified universe — the artifact's `findings` list is never truncated; only the API/UI layer slices `[:20]` from the already-sorted, already-ranked list (tested E1–E3, D9/D10 for permutation/reproducibility).

## 8. Artifact / manifest / run_audit / API wiring

- `unclassified_findings.json` (schema `unclassified_findings.v1`) is written by `finalize_completed_run_artifacts`, the same finalizer that writes `evidence_facts.json`/`alpha_activations.json`/`conflicts.json`, conditionally on `alpha_matches_payload` being available.
- Registered in `PRODUCT_EXTENSION_ARTIFACT_FILENAMES` (not `REQUIRED_ARTIFACT_FILENAMES`) — A2's 9-required-artifact tuple and count are byte-identical to before (test F2). `artifact_completeness` (pass/fail) is computed only from the required set and is unaffected either way (test F3/F3b).
- Download reuses the **existing** generic `GET /api/research/{run_id}/artifacts/{artifact_name}` route unchanged — no new download route was built. That route already enforces `validate_run_id_for_path`/`validate_artifact_filename` (the same allowlist `file_store` itself owns) and cross-checks the artifact manifest; adding the one filename to the allowlist was the only change needed (test E2, E5).
- `run_audit.json` gains an additive `unclassified_findings` block whose `reason_counts` is read straight off the artifact (byte-identical, test F5) — never independently recomputed.
- The Research API polling response (`build_research_response`) gains the Top-20 slice + lightweight counts only — the complete list never rides on every poll (test E3).
- An incompatible/future `schema_version` on disk is treated identically to "artifact absent" by both `build_run_audit_payload` and `build_research_response` (test F7) — never trusted blindly.
- Unknown/extra fields written into a hand-crafted artifact never leak into `run_audit.json`'s own block (test F6).

## 9. Historical payload compatibility

A run whose `unclassified_findings.json` was never generated (predates A3, or was never reprocessed) reports `status: "unavailable"` end-to-end — `run_audit.json`'s block, the polling response's `unclassified_findings_status`, and the frontend panel all agree, and **never** report a fabricated `total_count: 0` (tests E4, F4b; frontend tests "shows the historical-unavailable message... when the backend explicitly reports unavailable" and the two rewritten direction tests, which exercise this path against real mocked historical-shaped payloads).

## 10. Frontend

`NeutralFindingsPanel` (direction-filtered, wrong data source) was replaced by `UnclassifiedFindingsPanel`, driven entirely by the backend's `unclassified_findings_*` fields. `DirectionalFindingsPanel` (Positive/Negative) is untouched.

- Friendly-text mapping matches the task's exact wording (`no_alpha_match` → "No canonical Alpha match", etc.); machine-readable `reason`/`reason_codes` stay snake_case in the adapted data.
- Default display shows the Top 20 directly (not behind an expand toggle) with "Showing X of Y" and a reason-count summary strip.
- A duplicate finding shows "Representative finding: `<id>`".
- "Download full audit (`<total>`)" links directly to the existing artifact-download route with `download="<run_id>_unclassified_findings_audit.json"`.
- Historical/unavailable runs show the honest fallback sentence, never a fake empty state.

**A known, explicitly out-of-scope gap:** a claim that is direction-neutral/unknown *and* fully classified (0 A3 reasons apply) is correctly excluded from the unclassified list, but has no dedicated display slot elsewhere on the page either (it was never shown by the Positive/Negative panels before A3, and A3 does not add a third "classified but neutral-direction" bucket — doing so would require either shipping the full unclassified-claim-id set to the client on every poll, which the task explicitly says not to do, or a new backend concept outside A3's mandate). This is a pre-existing display-organization property of the page (findings were always organized strictly by direction bucket), not a regression A3 introduces; flagged here as a follow-up, not absorbed into A3's own scope.

### The field-dropping bug class (checked, not repeated)

B5 twice found that a narrow, explicit object-reconstruction function (not a spread) silently drops any field it doesn't enumerate. `adaptCanonicalResearchResponse`/`adaptUnclassifiedFinding` were written explicitly checking for this: every new field is individually extracted and placed in the returned object literal; confirmed correct by the real end-to-end Playwright run (§12), not just unit tests with hand-built fixtures.

## 11. Real saved run verification — `e3eb3909-3744-4a02-9b32-b225cf6ef665` (NVDA)

Offline reprocess only (no TradingAgents/LLM calls). `alpha_matches.json`/`evidence_facts.json`/`structure_graph.json`/`conflicts.json`/`structured_agent_outputs.json`/`evidence_stance_audit.json` sha256 hashes were captured **before** and **after** the full A3 pipeline (`unclassified_findings.json` build + `run_audit.json` regeneration + `artifact_manifest.json` regeneration) and are **byte-identical** — B1–B5 outputs are provably untouched, not just assumed.

- **Total findings:** 863 structured claims → 863 `alpha_matches.json` records → **855 unclassified**, **8 fully classified**.
- **Reason distribution:** `no_alpha_match: 803`, `no_ticker_specific_evidence: 51`, `generic_background: 9`, `duplicate_supporting_text: 7`, `low_confidence: 0`.
- **Unresolved:** 0.
- The 803/863 (93%) `no_alpha_match` rate is real and expected — the Alpha Mapper's matching is intentionally strict, and per the task's own instruction, A3 does not (and must not) treat this as a reason to loosen the 0.35 threshold.

**Named checks (task §21):**
1. Direction-neutral-but-valid claims never wrongly unclassified — a naive first pass flagged 2 apparent violations; root-caused as **not a bug**: both claims genuinely lack ticker-specific text within their own sentence (macro/valuation commentary that never names "NVDA"), so `no_ticker_specific_evidence` correctly still applies independent of direction and stance. Re-run with the complete condition (matched + non-background stance + **ticker-specific** + non-duplicate): 1 qualifying claim, 0 violations.
2. Repeated debate/history text correctly uses the existing Evidence Fact Index groups — 7 real `duplicate_supporting_text` findings, each with a real `evidence_fact_group_id`/`representative_claim_id` from `evidence_facts.json`.
3. Unmatched, high-confidence (≥0.8), ticker-specific claims: 1 real example, correctly `no_alpha_match` (not something else).
4. Matched-but-non-ticker-specific claims: 51 real examples, all correctly carry `no_ticker_specific_evidence` in `reason_codes`.
5. `mentions_alpha`/`neutral_background` never counted as supporting: all 9 `generic_background` findings' underlying stance is `neutral_background` (none is `supports_alpha`).

`unclassified_findings.json`/regenerated `run_audit.json`/`artifact_manifest.json` are now present on disk for this run (additive; every other artifact's timestamp and hash is unchanged).

## 12. Frontend visual verification

Real backend (fresh process, port 8010, `COMQUTOR_CORS_ORIGINS` set) + real Vite dev server (port 5190) + Playwright, against the real NVDA run above. No live Provider/LLM calls (a `research_runs` DB row was seeded directly from the run's own `metadata.json` so the status-polling endpoint would serve it — see memory note on this technique).

- Heading: "Unclassified findings (855)"; count note: "Showing 20 of 855" — exact.
- Reason-count strip renders all 4 non-zero reasons with friendly labels.
- 20 cards rendered (never hundreds inline).
- "Download full audit" href resolves to the real artifact route; `download` attribute is exactly `e3eb3909-3744-4a02-9b32-b225cf6ef665_unclassified_findings_audit.json`.
- A missing/nonexistent run_id shows a clean failed/not-found panel, never a crash.
- Structure Graph and Conflict Radar pages both still render and navigate correctly.
- **Zero browser console errors.**
- BUY/SELL/HOLD/"guarantee profit" text scan: naive substring matching found apparent hits; manual context inspection showed every one is either (a) a false positive against ordinary English ("holding" a portfolio position, "threshold", "hold" as in "expectations hold"), (b) verbatim quoted analyst/social-sentiment claim text being displayed for traceability (a pre-existing, cross-panel design property — not something A3 introduces or is scoped to filter/censor), or (c) COMQUTOR's own disclaimer sentence itself ("...does not predict outcomes, **guarantee profit**, or eliminate investment risk") being caught by the crude phrase match. Zero genuine COMQUTOR-authored investment-recommendation language found.

Full-page and panel-focused screenshots were captured and reviewed; layout is clean, text wraps correctly, no overflow, no duplicate-provenance clutter beyond the intentional "Representative finding" note.

Cleanup: temporary `frontend/a3_*.mjs` scripts deleted after use; only the two dev-server processes started in this session (ports 8010/5190) were killed — the three pre-existing, longer-running processes on ports 8000/8001/5175 were left untouched (confirmed via `ps`/`lsof` before and after).

## 13. Test results

- **New dedicated suite:** `tests/test_a3_unclassified_findings_control.py` — **58/58 passed**, sections A (7), B (12), C (6), D (10), E (6), F (7 incl. two `_b` variants), G (8 incl. parametrized).
- **Full backend regression:** **3415 passed, 3 failed, 47 skipped** (3357 passed immediately before A3's own tests were added — i.e. +58 new passing tests, zero regressions). The 3 failures are pre-existing and unrelated to A3 (root-caused, see §14) — confirmed identical before and after this segment's changes.
- **Frontend:** `npm run typecheck` clean; `npx vitest run` — **170/170 passed** across 17 files (was 165/165 before this segment: −1 obsolete test removed, +6 new tests, +... net +5 in `ResearchRunPage.test.tsx`); `npm run build` clean; `npx eslint` clean on every file this segment touched.
- **Ruff:** clean on every file this segment touched (`unclassified_findings.py`, `artifact_export.py`, `routes_research.py`, `file_store.py`, the new test file), including two unrelated pre-existing import-order issues fixed as a mechanical side effect of `ruff --fix` reorganizing an already-unsorted block.

## 14. Known pre-existing failures (unrelated to A3, root-caused)

1. `tests/structured_output_shadow/test_source_integrity.py::test_current_semantic_components_match_approved_phase1_master_baseline` — a frozen SHA-256 checksum of `alpha_mapper.py`/`week2_llm.py` predates B1's own intentional Evidence Stance changes to those files; the approved baseline was never updated. A3 never touched either file.
2. `tests/test_w5_demo_seed.py::test_seed_is_complete_idempotent_and_reusable_without_provider`
3. `tests/test_w5_demo_seed.py::test_only_nvda_and_qqq_are_seeded`
   Both fail with `NVDA_MAIN_CONFLICT_NOT_ARBITRATED` — the demo/seed script's golden NVDA fixture predates B2's stricter Conflict Evidence Admissibility gate. A3 never touched the seed script, B2, or the taxonomy.

These are the same 3 failures before and after every change in this segment (verified by running the exact same 3 test IDs standalone both times).

## 15. Explicit non-goals confirmed not done

No A4 Regression Runner, no J2/J3 work, no cold-start history fix, no B1 live configuration repair, no repository cleanup or old-artifact deletion, no "John-20" gold audit, no new Alpha invalidation content, no Alpha-threshold change, no confidence/Alpha-score relationship change, no B1 50-row re-run, no new semantic classifier/dedup system/Provider client. The one independent gap noted in §10 (no dedicated display slot for classified-but-neutral-direction claims) is recorded as a follow-up only, not absorbed into this task.

## 16. Completion checklist (task §23)

| Criterion | Status |
|---|---|
| Neutral-direction vs unclassified clearly separated | ✅ §3–4 |
| B1 neutral/mention stance vs A3 unclassified clearly separated | ✅ §4 (stance drives `generic_background`; direction never drives anything) |
| Every unclassified finding has a John canonical reason | ✅ (0 unresolved on real data) |
| Primary reason unique per finding | ✅ tested B8 |
| Multi-reason provenance retained | ✅ tested B9 |
| No unapproved 6th reason invented | ✅ tested B7 |
| UI defaults to max 20 | ✅ §10, §12 |
| UI shows accurate X/Y | ✅ "Showing 20 of 855" verified live |
| Full-audit download contains everything | ✅ tested E1/E2, verified live |
| Top20 never truncates the authoritative artifact | ✅ tested D3, E1 |
| Duplicate detection reuses existing Evidence Fact/dedup | ✅ §4, tested C1–C6 |
| Ticker-specific uses the current trusted deterministic signal | ✅ §4, same function B2 uses |
| No-match claims retained | ✅ tested A5 |
| A2's required-artifacts contract intact | ✅ tested F2 |
| Historical runs fall back safely | ✅ tested E4/F4b, verified live |
| B1–B5 authoritative outputs unmodified | ✅ byte-identical sha256, §11 |
| Provider calls = 0 | ✅ |
| No new reproducible A3 regression | ✅ §13–14 |
| No overwriting of existing legitimate uncommitted work | ✅ only additive edits; git status reviewed throughout |
| No commit, no push | ✅ HEAD unchanged |
