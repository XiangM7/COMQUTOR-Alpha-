# v0.2 MVP Final Gap Closure -- Structured External Source Traceability

**Task:** JOHN MVP FINAL GAP CLOSURE. Full detail in `v0_2_mvp_functional_completeness_audit_final.json`; predecessors: `v0_2_mvp_functional_completeness_audit.json/.md` (read-only baseline) and `v0_2_mvp_functional_completeness_audit_postfix.json/.md` (History + Export).

**Branch:** `comqutor-structure-layer` · **HEAD:** `7a9aefa5c7b5c820515447c6289aeef80eac9bdc` (unchanged, no commit). No Alpha semantics, Candidate 3, Gold, taxonomy, or validation-outcome-driven prompt changes made.

## Acquisition Pipeline Audit (performed before any edit)

All four analyst paths (market, news, fundamentals, sentiment) have a real, discrete external-tool-call boundary (`tradingagents/dataflows/*`, real yfinance/Alpha Vantage/FRED/Polymarket/Reddit/StockTwits calls) — none is pure LLM free-text synthesis with no tool boundary. Genuine structured metadata (title/publisher/URL/date for news) exists transiently inside these functions before being flattened into text. The universal point of loss was `tradingagents_output_writer.build_raw_agent_output_record`, which only ever captured the analyst's already-synthesized final prose — the intermediate structured tool responses were wiped between analyst turns and never persisted. No existing provenance abstraction was duplicated (the word "provenance" elsewhere in this codebase always means something else — text-span verification, code/schema versioning — never external-source identity).

## Architecture Implemented

A small, additive **source registry** captured at the acquisition boundary:

- `tradingagents/dataflows/source_capture.py` — self-contained, zero dependency on `comqutor_alpha`, a context-scoped capture sink.
- `tradingagents/dataflows/yfinance_news.py` — instrumented to record each kept article's real title/publisher/link/date **alongside**, never instead of, the exact same text it already returned.
- `comqutor_alpha/runners/tradingagents_runner.py` — scopes capture around the real `graph.propagate()`/`graph.graph.stream()` calls, passes the result to the writer.
- `comqutor_alpha/adapters/tradingagents_output_writer.py` — persists `source_registry.json`, best-effort, only when something genuine was captured.
- `comqutor_alpha/source_provenance.py` — `SourceRecord` builder, `TRACEABLE`/`PARTIAL`/`UNAVAILABLE` classification (derived purely from which genuine fields exist), and a **deterministic, read-time-only** substring matcher linking claim text to a source's own title — **no LLM ever selects or invents a source_id**; a defensive `resolve_source_by_id` rejects any id not in the run's own registry.
- Claim linking happens entirely at **read time** (`agent_output_reader.py`, `routes_research.py._attach_external_sources_to_conflicts`) — `structured_output_adapter.py` (the frozen-hash-sensitive claim-persistence layer) was **never touched**.
- Frontend: a shared `ExternalSourceDisplay` component renders only genuine fields, a clickable URL only when real, and an honest "not available" state otherwise — wired into both `ResearchRunPage`'s Analyst Findings and `ConflictEvidenceSections`' evidence cards, with the pre-existing internal `source_agent_output_id` label renamed to "Internal ref:" so it can never be confused with the new external Source block.

## Two Real Bugs Found and Fixed via Live Verification

1. **Stale run_id in `source_registry.json` after relocation.** `_relocate_run_outputs` rewrote `run_id` in `metadata.json`/`raw_agent_outputs.json` but not in `source_registry.json` — caught by directly inspecting the real AMD run's persisted file. Fixed, manually corrected on disk, manifest regenerated, regression test added.
2. **A follow-up bug in the fix itself:** `load_json_record_if_exists` returns `{}` (not `None`) for a missing file; the first fix's `isinstance(dict)` check treated that as "found" and wrote a bogus registry for runs with zero captured sources. Caught immediately by a negative-case regression test written alongside the positive one — exactly the discipline this task's own Section 16 required.

## Live Fresh Research Verification (AMD)

Ticker **AMD** (a Silver-tier ticker, chosen specifically to avoid touching NVDA/QQQ/SNDK per this task's instruction), run `d5b60b8a-66b8-44c1-9f55-ee345e58c48d`, real DeepSeek profile, 2067s wall-clock.

- **46 genuine sources captured** — real publishers (GuruFocus, Reuters, Barron's, 24/7 Wall St., MT Newswires, etc.), real headlines, real Yahoo Finance/Barron's/247wallst.com URLs, real publish dates.
- **2 of 572 findings TRACEABLE**, 570 honestly **UNAVAILABLE** — an accurate reflection of how rarely the LLM's own prose literally reproduces a source's exact title, never forced or inflated.
- Verified live through the real running server: stored in Run History (genuine DB row via real `POST /api/research`), reopenable via `/status`, Evidence findings display real sources, Export ZIP contains the corrected `source_registry.json`, and **all of it survived a real server restart**.

## Updated Five-Area + Source Traceability Determination

| Area | Status |
|---|---|
| A. Research / jargon | FULLY USABLE |
| B. Evidence detail | FULLY USABLE |
| C. Alpha mapping + Structure Graph | FULLY USABLE |
| D. Conflict Radar + invalidation | FULLY USABLE |
| E. Run history + result export | FULLY USABLE |
| Source traceability | **COMPLETE** |

`SOURCE_TRACEABILITY_COMPLETE = YES` — per this task's own acceptance criterion: completeness means the product preserves and displays provenance whenever the underlying acquisition genuinely provides it, and honestly identifies when it does not. It does not, and was never required to, mean every claim carries a URL.

## Test / Build Results

- **Backend:** `test_source_provenance.py` (16 new), `test_source_capture.py` (7 new), `test_tradingagents_output_writer.py` (+5), `test_agent_outputs_api.py` (+5), `test_artifact_export_and_api.py` (+7), `test_tradingagents_progress_runner.py` (+2, including the bug-catching regression tests) — all passing. Broad regression across ~46 `routes_research`/`tradingagents_runner`-adjacent test files: **1198+ passed**, only the same single pre-existing, unrelated `test_replay_conflict_does_not_get_run_id_mismatch` failure (confirmed to fail identically in complete isolation, touching none of this task's files).
- **Frontend:** typecheck clean, `npx eslint src` shows only the same 2 pre-existing findings in untouched files, build clean, **338/338** tests passing (16 new: `ExternalSourceDisplay.test.tsx` ×9, `ResearchRunPage.test.tsx` +4, `ConflictEvidenceSections.test.tsx` +3).
- Final Gold SHA256 and Candidate 3 classifier/batch hashes confirmed unchanged. The pre-existing baseline diff (`structured_output_adapter.py`/`week2_llm.py`/its test file) remains byte-identical to Section 0's original baseline — never touched by this task or any prior task in this engagement.

## Final Determination

- `RUN_HISTORY_COMPLETE = YES`
- `RESULT_EXPORT_COMPLETE = YES`
- `SOURCE_TRACEABILITY_COMPLETE = YES`
- **`MVP_CORE_FUNCTIONS_COMPLETE = YES`** — all five John-required MVP areas are now genuinely usable, verified against real code and, for the three most recently closed gaps, against a real live server and a real Fresh Research run.
- `MVP_DEMO_CRITICAL_FLOW_COMPLETE = YES`
- **Remaining blocker: NONE**

**FINAL CONCLUSION: FUNCTIONALLY_COMPLETE**
