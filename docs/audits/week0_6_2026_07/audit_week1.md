# Week 1 Adversarial Audit — TradingAgents final_state -> 12 agent-output artifacts -> file storage -> research API entrypoint -> Alpha taxonomy

Repo: `/Users/xiangmao/COMQUTOR-Alpha-`, branch `comqutor-structure-layer`, HEAD `64e657958aa1db32528d55e8b9c5520b387f86fc`, worktree clean throughout (read-only analysis; mutations performed only in `/tmp` via monkeypatch/temp copies, no tracked file touched).

---

## 1. Doc contract claims (with doc:line)

| Claim | Source |
|---|---|
| `POST /api/alpha-library` returns 10 alphas driven by local taxonomy file | `docs/week1_gate_completion.md:5-14` |
| `POST /api/research` supports offline raw outputs for local validation; real path is guarded | `docs/week1_gate_completion.md:16-24` |
| agent_outputs saved as file-backed rows (`outputs/runs/{run_id}/raw_agent_outputs.json`) | `docs/week1_gate_completion.md:26-35` |
| raw output single-record cap is 50000 chars, `truncated` flag set explicitly when exceeded | `docs/week1a_gate_completion.md:41` |
| `final_report.md` is opt-in, **default not written** | `docs/week1a_gate_completion.md:42` |
| Storage centralized in `file_store.py`, JSON artifacts use atomic write, `run_id`/filename path-validated | `docs/week1a_gate_completion.md:43-45` |
| metadata only stores provider/model allowlist; never API key/secret/token/password/backend_url/full config | `docs/week1a_gate_completion.md:46` |
| `POST /api/research` response never exposes raw output, local paths, or config | `docs/week1a_gate_completion.md:47` |
| Field mapping table: 12 agents, each with a `primary_path`, 2 with `fallback_paths` (research_manager, portfolio_manager) | `docs/week1a_hook_points.md:17-30` |
| "If primary and fallback both exist, writer uses primary as raw_output, fallback recorded only in source_candidates" | `docs/week1a_hook_points.md:32` |
| Week 1J acceptance: running the documented fake-`final_state` command must produce `raw_agent_outputs.json`, `metadata.json`, **and `final_report.md`** | `docs/week1j_acceptance_checklist.md:29-43` |
| Tests never call paid API; real TradingAgents run requires explicit `allow_real_tradingagents_run=True` + server config; `.env` never modified | `docs/week1a_gate_completion.md:92-98` |

---

## 2. Actual code behavior per question (file:line evidence)

**Q1 — final_state → 12 categories mapping.**
`comqutor_alpha/adapters/tradingagents_output_writer.py:36-101` defines `AGENT_OUTPUT_FIELDS`, a static tuple of 12 `AgentOutputField` entries, each with a `primary_path` and (for `research_manager`, `portfolio_manager` only) one `fallback_paths` entry. `_select_source` (`:180-186`) walks `(primary_path, *fallback_paths)` and returns the first non-empty value; if **none** of the candidate paths resolve to a non-empty value, `_select_source` returns `(None, None)`. `_extract_agent_outputs` (`:222-249`) then does `if source_path is None: continue` — **the agent record is silently omitted from `raw_agent_outputs.json`**. `metadata["agents"]` (`:315`) is built only from whatever records survived, so it silently shrinks. The only failure signal is `warnings = [] if agent_outputs else ["NO_AGENT_OUTPUTS_EXTRACTED"]` (`:302`) — this fires **only when all 12 are missing**, never for partial loss (e.g. 4/12 missing). No field is backed by heuristic/guess logic; all extraction is exact structural path lookup, no keyword search or inference.

**Q2 — Truncation.**
`MAX_RAW_OUTPUT_CHARS = 50000` (`:22`); `_truncate_raw_output` (`:140-147`) does a hard `raw_output[:keep_chars]` character slice — no word/sentence-boundary awareness. Proven empirically (see §5) that this cuts mid-word/mid-sentence. `truncated`, `content_length`, `original_content_length` are recorded per-record (`:203`, `:215-217`) so downstream (Week 2, out of scope) can in principle detect truncation, but the text itself is already broken at an arbitrary character offset by the time it reaches them.

**Q3 — Path construction consistency.**
Single source of truth: `comqutor_alpha/storage/file_store.py:74-93` (`resolve_output_root`, `run_dir_for`). Every other module (`adapters/tradingagents_output_writer.py:14-16`, `runners/tradingagents_runner.py:32,203-215,383`, `api/routes_research.py:35-42,200,326,758,835`, `api/agent_output_reader.py:31,260,373`, `storage/db/engine.py:20,64`, `conflict_engine/pipeline.py:22,47`) imports and calls these same two functions — grep confirms **no second/competing path-construction implementation exists**. No drift risk found.

**Q4 — Atomicity.**
`file_store.py:108-129` (`atomic_write_text`): writes to `path.with_name(f".{path.name}.{uuid4().hex}.tmp")`, `chmod 0o600`, then `os.replace(tmp_path, path)` (atomic rename on POSIX same-filesystem), then `chmod` again, with a `finally` cleanup of any leftover temp file. Verified empirically with a concurrent-reader harness (§5) — no partial content ever observed.

**Q5 — Path traversal.**
`validate_run_id_for_path` (`file_store.py:33-49`) rejects `..`, `/`, `\`, absolute paths, whitespace, and enforces `^[A-Za-z0-9_-]{1,80}$`. `validate_ticker` (`api/routes_research.py:73-93`) rejects control chars/whitespace, `..`, and additionally routes through TradingAgents' own `safe_ticker_component`/`normalize_symbol`/`is_yahoo_safe`. Both are called on every path into `run_dir_for`/`_create_offline_run`/`run_research_request`. Verified empirically (§5) — all traversal payloads rejected, no directory ever created outside the sandbox.

**Q6 — Secret allowlist.**
`SAFE_CONFIG_KEYS = {"llm_provider", "quick_think_llm", "deep_think_llm"}` (`:24`); `_safe_config_value` (`:171-177`) refuses to read any other key. `config` itself is never serialized wholesale anywhere in the writer. Verified empirically (§5) — a fake `ANTHROPIC_API_KEY`-shaped string placed under `api_key`, `ANTHROPIC_API_KEY`, `openai_api_key`, `backend_url`, and a nested dict never appears in `metadata.json` or `raw_agent_outputs.json`. HTTP payload (`ResearchRequest` pydantic model, `api/routes_research.py:1251-1263`) does not even expose `config` or `allow_real_tradingagents_run` as fields — confirmed by `test_api_router_loads_with_installed_pydantic` and independently by reading the model.

**Q7 — Alpha taxonomy conflict pairs (programmatically verified, not eyeballed).**
Ran a standalone script parsing the YAML (§5): exactly 10 alpha_ids, exactly 6 unordered conflict pairs, **all 6 are the mandatory pairs from `alpha_loader.py:41-48`**, all symmetric (A→B weight == B→A weight), zero extra pairs, zero duplicates, zero self-conflicts. `alpha_loader.py:116-141` (`validate_taxonomy`) additionally enforces this at every `load_alpha_taxonomy()` call (bidirectional existence + weight tolerance ±0.05 + exact MVP-10 id-set + every alpha has ≥1 keyword) — this validation is **not optional/test-only**, it runs on the production load path.

**Q8 — Real writer vs. shortcut path.**
`api/routes_research.py:666-733` (`run_research_request`) branches: injected `runner` (test seam) → `offline_raw_agent_outputs` (gated off in production by `COMQUTOR_ENV=production`, `:681-685`) → `allow_real_tradingagents_run=True` w/o `final_state` → `run_streaming_tradingagents_research` (`runners/tradingagents_runner.py:239-396`) → else → `run_original_tradingagents_research` (`runners/tradingagents_runner.py:80-145`). **Both** real-execution runners end by calling `save_comqutor_run_outputs` (`tradingagents_runner.py:94,137,384` → `tradingagents_output_writer.py:282`) — the same formal writer. The HTTP `ResearchRequest` model (`:1251-1263`) does not expose `config` or `allow_real_tradingagents_run`, so an HTTP caller can never reach the "real run" branch directly — only the server-side lifecycle/job layer (Week 5, out of scope) can set those. `tradingagents/comqutor_outputs.py` is confirmed a pure re-export shim (`AGENT_OUTPUT_FIELDS`, `OUTPUT_VERSION`, `save_comqutor_run_outputs`) with zero internal callers except `cli/main.py:1229`, which itself calls the same `save_comqutor_run_outputs`. **No bypass/dead-code path found.**

---

## 3. Doc-vs-code conflicts

| # | Doc claim | Actual code | Verdict |
|---|---|---|---|
| 1 | `docs/week1j_acceptance_checklist.md:29-43` — the documented one-liner command (no `write_final_report=True`) must produce `final_report.md`, and the acceptance criteria list "`final_report.md` 存在" as a pass condition. | `save_comqutor_run_outputs(..., write_final_report=False)` is the default (`tradingagents_output_writer.py:290`); running the doc's exact command produces **no** `final_report.md` (reproduced in §5). This is a direct consequence of the later Week 1A hardening change ("`final_report.md` 改为 opt-in，默认不写", `docs/week1a_gate_completion.md:42`) which was never back-ported into week1j's checklist. | **CONFIRMED CONFLICT.** Week 1J's own acceptance checklist would fail today if executed literally. Doc rot, not a code defect — but it means the "Week 1J passed" claim can no longer be independently reproduced from the doc as written. |
| 2 | No doc anywhere claims partial-field-loss triggers a warning or error. | Confirmed no such behavior exists (§2 Q1, §5 mutation 1). | Not a conflict — just an undocumented, silent gap (see Defects). |

Everything else checked (allowlist, atomic write, path validation, taxonomy conflict symmetry, formal-writer call chain) matches the docs' claims exactly — no other conflicts found.

---

## 4. Test effectiveness table

| Test file | Invokes production entrypoint? | What's mocked | Assertion style | Verdict |
|---|---|---|---|---|
| `tests/test_tradingagents_output_writer.py` | Yes — `save_comqutor_run_outputs` directly, no reimplementation | Nothing | Business outcome: exact `source_path` chosen, exact truncation byte counts, exact secret-exclusion, exact `agent_output_id` format, `final_report.md` existence gated on opt-in | **STRONG** (but has a coverage gap — never tests partial-missing-field, only all-missing and single-field-missing-with-fallback cases; never asserts a warning for partial loss) |
| `tests/test_file_store.py` | Yes — all `file_store` functions called directly | Nothing | Outcome: accept/reject on real payloads including traversal strings, round-trip content equality, path containment (`relative_to`) | **STRONG** for path validation; does not itself test the atomic-write-under-concurrency property (I verified that separately, see §5) — **PARTIAL** on the atomicity claim specifically |
| `tests/test_alpha_loader.py` | Yes — `load_alpha_taxonomy()`, the real production loader incl. `validate_taxonomy` | Nothing | Outcome: exact bidirectional conflict pairs, keyword index membership | **STRONG** |
| `tests/test_alpha_library_route.py` | Yes — `get_alpha_library`/`get_alpha_detail`, which call the real loader | Nothing | Outcome: exact id set, `alpha_count`, conflict serialization | **STRONG** |
| `tests/test_tradingagents_progress_runner.py` | Yes — `run_streaming_tradingagents_research`, the real streaming runner including the real writer and real `_relocate_run_outputs` | Only `graph_factory` (the paid TradingAgentsGraph/provider boundary) is faked — an explicit, appropriate seam | Outcome: exact progress-stage sequence/percentages, dedup of repeated chunks, exact file relocation, exact `run_id` rewriting across `metadata.json`/`raw_agent_outputs.json`, checkpoint enter/exit ordering | **STRONG** — one of the best-designed files in scope |
| `tests/test_week1a_gate.py` | Yes — `run_research_request`, `get_research_run`, `build_research_response`, the real API entrypoints | Nothing (offline path is a real, first-class code path, not a mock) | Outcome: full artifact set exists, cross-artifact traceability (`claim_id`/`source_agent_output_id` chains from raw → structured → alpha_matches → extracted_structures), no local paths/config/raw_output leak into the HTTP response, safe partial-failure responses on injected failures | **STRONG** |
| `tests/test_research_input_validation.py` | Yes — `validate_ticker`, `_create_offline_run`, `run_research_request` | Nothing | Outcome: SQLi-shaped ticker rejected, traversal ticker rejected, oversized ticker rejected, **and asserts `list(tmp_path.iterdir()) == []`** (no directory created) after rejection, log level/exc_info assertions | **STRONG** — genuinely adversarial, checks filesystem side effects, not just return codes |

Overall: this is an unusually strong test suite for Week 1 — nearly every test drives the real production function with the real writer/file_store, and mocking is confined to the one boundary that must be mocked (the paid LLM/graph call). The material gap is the **silent partial-extraction case**, which no test in this list (or found via `grep` across `tests/`) exercises.

---

## 5. Mutation-style verification results

All mutations run against `/tmp` copies or via monkeypatch; no tracked file modified. Scripts left in `/private/tmp/claude-501/-Users-xiangmao-COMQUTOR-Alpha-/15b53a10-aac2-49e2-ab0e-6e4580d9d8ed/scratchpad/` (`mutation1_missing_fields.py` … `mutation6_truncation_boundary.py`, `w1j_check/`).

| # | Fault injected | Expected to be caught by | Actually failed/caught? | Verdict |
|---|---|---|---|---|
| 1 | Deleted `market_report`, `sentiment_report`, `news_report`, and `investment_debate_state.bull_history` (4/12 categories, no fallback available) from a full `final_state` before `save_comqutor_run_outputs` | A warning, error, or reduced-agent-count signal | `raw_agent_outputs.json` silently wrote only 8/12 records; `metadata.json` has **no `warnings` key at all**; `agents` list just quietly has 8 entries instead of 12; write succeeds with exit code 0 | **TEST GAP.** No test exercises this; production code has no partial-loss signal. |
| 2a | Swapped `market_report` ↔ `sentiment_report` string content within `final_state` (simulating an upstream TradingAgents field-crossing bug) | Some content/label consistency check | `market_agent` record's `raw_output` is the sentiment text and vice versa; write succeeds silently, no error | **TEST GAP.** Writer trusts final_state structurally; no semantic cross-check exists or is tested. |
| 2b | Monkeypatched `AGENT_OUTPUT_FIELDS` so `research_manager.primary_path` points at `trader_investment_plan` instead of `investment_plan` (simulating a writer-side mapping regression) | Some test asserting agent↔field identity beyond the one shipped fixture | Record written successfully with `source_path="trader_investment_plan"` but `record["source_field"]` label is unchanged (`"investment_plan"`) — **label/content mismatch persisted to disk with no complaint** | **TEST GAP.** `test_extracts_expected_outputs_from_final_state` would only catch this if the mapping table itself changed in the tracked source (it does re-derive `source_path` from the live table), but nothing catches a `source_field` (label) vs actual extracted content mismatch, since `source_field` is a static string on `AgentOutputField`, decoupled from `primary_path` by construction. |
| 3 | `output_root=None` passed to `save_comqutor_run_outputs` from a `/tmp` sandbox cwd with `COMQUTOR_OUTPUT_DIR` unset | Controlled failure or a defined fallback | `resolve_output_root(None)` falls back to `Path.cwd()/outputs/runs` (`file_store.py:74-82`); write succeeds under the sandbox cwd, no crash | **PASS** (controlled, documented fallback — also independently exercised by `test_none_output_root_uses_default_root_and_relocates` in the runner test file) |
| 4 | `run_id`/`ticker` containing `../../etc/passwd`, `..`, `/etc/passwd`, `NVDA\x00`, `NVDA;rm -rf`, absolute Windows paths, and one full end-to-end `run_research_request` call with a traversal ticker and separately a traversal `run_id` | `INVALID_RUN_ID`/`INVALID_TICKER` rejection, zero filesystem side effect | Every payload rejected with `ValueError`/`INVALID_TICKER`/`INVALID_RUN_ID`; end-to-end sandbox dir listing is `[]` after rejection; `/tmp/evil_run` never created | **PASS** — thoroughly defended, matches `tests/test_file_store.py` and `tests/test_research_input_validation.py` coverage |
| 5 | Fake `ANTHROPIC_API_KEY`-shaped secret (`sk-ant-api03-…`) placed under `ANTHROPIC_API_KEY`, `api_key`, `openai_api_key`, `backend_url` (with the key embedded in a URL), and a nested dict, inside `config` passed to `save_comqutor_run_outputs` | Allowlist blocks it from `metadata.json`/`raw_agent_outputs.json` | Confirmed absent from both files; only `llm_provider`/`quick_model`/`deep_model` survive | **PASS** — matches `test_metadata_does_not_include_secret_config_values` |
| 6 (extra, Q2) | 104,000-char input built from a repeating sentence, forcing the 50,000-char cutoff to land mid-sentence | N/A (design question) | Confirmed: kept text ends `"...ustomer demand for AI accelerators. NVDA revenue guidance wa"` — cut lands mid-word (`wa` of `was`), not at a sentence boundary | **CONFIRMED BEHAVIOR** — hard char truncation, no boundary awareness; a real risk for Week 2 claim extraction (out of this audit's lane, flagged for their attention) |
| 7 (extra, Q3/atomicity) | Monkeypatched `Path.write_text` to split a write into two halves with a 300ms sleep between them, while a concurrent reader thread polled the target path every 10ms | Reader should never observe a partial/corrupt file | 5 observations, 0 partial/corrupt | **PASS** — atomic write pattern (`tmp` + `os.replace`) holds under simulated slow-write race |
| 8 (extra, doc conflict) | Ran `docs/week1j_acceptance_checklist.md`'s exact documented command verbatim | `raw_agent_outputs.json`, `metadata.json`, `final_report.md` all exist per the doc's stated acceptance criteria | `raw_agent_outputs.json`=True, `metadata.json`=True, **`final_report.md`=False** | **DOC CONFLICT CONFIRMED** (see §3) |

---

## 6. Confirmed defects

| Severity | file:function | Test that should have caught it | Actual problem | Why tests missed it | Minimal repro | Blast radius | Fix direction |
|---|---|---|---|---|---|---|---|
| **P1** | `comqutor_alpha/adapters/tradingagents_output_writer.py:_extract_agent_outputs` (`:222-249`), `save_comqutor_run_outputs` (`:302`) | `tests/test_tradingagents_output_writer.py` (has full-state and all-missing tests but nothing in between) | When 1–11 of the 12 categories fail to resolve (missing/empty source field, no fallback), the writer silently omits those records with **zero warning, zero error, zero metadata signal**. `warnings=["NO_AGENT_OUTPUTS_EXTRACTED"]` only fires at the all-12-missing extreme. A run that lost, say, all 4 analyst reports due to an upstream TradingAgents regression looks identical in `metadata.json`/HTTP response shape to a fully successful run — only `len(metadata["agents"]) < 12` betrays it, and nothing downstream checks that. | Only two fixture states are used across the suite: the fully-populated one, and (for two specific fields only) single-field-removed-with-fallback-available. No test constructs a "some categories genuinely gone, no fallback" scenario. | `mutation1_missing_fields.py` in scratchpad — delete `market_report`/`sentiment_report`/`news_report`/`investment_debate_state.bull_history` from a full `final_state`, run `save_comqutor_run_outputs`, observe 8/12 records and no `warnings` key. | Every downstream consumer (Week 2 claim extraction, Week 3 structure graph, Week 4 conflict detection, the `/api/research/{run_id}` response) treats this run as ordinary — partial data silently degrades everything built on top, with no operator-visible signal. | Add a threshold-based warning (e.g. `MISSING_AGENT_OUTPUTS` listing which of the 12 categories are absent) whenever `len(agent_outputs) < len(AGENT_OUTPUT_FIELDS)`, not only when it's zero; surface it in the API response's `warnings`/`artifacts` block. |
| **P2** | `comqutor_alpha/adapters/tradingagents_output_writer.py:_truncate_raw_output` (`:140-147`) | None in scope claims to test semantic preservation | Truncation is a hard `str[:N]` character slice with no word/sentence-boundary logic; content over 50,000 chars is cut mid-word/mid-sentence before the `[TRUNCATED...]` marker is appended. | Existing tests only assert byte-count/flag correctness (`test_oversized_raw_output_is_truncated`), never text-boundary quality — a reasonable scope boundary for this file, but the risk transfers unchanged into Week 2's claim extraction (their lane). | `mutation6_truncation_boundary.py` — cut lands as `"...for AI accelerators. NVDA revenue guidance wa"`. | Any single agent output over 50k chars (plausible for long debate histories) can have its final claim/sentence corrupted right at the truncation boundary, potentially flipping or garbling the last extracted claim for that agent. | Trim to the last sentence/paragraph boundary before the limit (or at minimum the last whitespace) before appending the truncation marker. |
| **P2 (docs)** | `docs/week1j_acceptance_checklist.md:29-43` | N/A — documentation defect | The checklist's own documented command and acceptance criteria (`final_report.md` must exist) no longer match current writer defaults (`write_final_report=False` by default since the Week 1A hardening pass). | Doc not updated when `docs/week1a_gate_completion.md:42` introduced the opt-in change. | `w1j_check/` — ran the doc's exact one-liner, `final_report.md` does not exist. | Low direct risk (doesn't affect running code), but anyone re-validating "Week 1J passed" from the doc alone will get a false failure, and the doc can no longer be trusted as a literal reproduction script. | Update the checklist's command to pass `write_final_report=True` (or drop `final_report.md` from the acceptance criteria to match the now-opt-in default). |

No P0 (traversal, secret leakage, atomicity, taxonomy-consistency, and formal-writer-call-chain integrity — the areas with the highest blast radius if broken — all held up under adversarial testing).

---

## 7. Week 1 verdict

**VERIFIED_WITH_LIMITATIONS**

Justification: The security- and integrity-critical surfaces for Week 1 — path traversal (run_id, ticker), atomic writes, the config/metadata secret allowlist, the alpha taxonomy's MVP-10 conflict-pair bidirectionality, and the "does the API actually call the formal writer" chain — all held up under direct adversarial mutation testing with concrete, reproducible evidence (§5), not just code reading. The test suite backing this slice is genuinely strong: it drives real production entrypoints (`save_comqutor_run_outputs`, `run_research_request`, `run_streaming_tradingagents_research`, `load_alpha_taxonomy`) with business-outcome assertions and appropriately narrow mocking (only the paid-provider graph call is faked).

The "limitations" are two real, confirmed gaps rather than speculative concerns: (1) partial (non-total) loss of agent-output categories is completely silent — no warning, no error, no test coverage — which is a genuine data-integrity blind spot given this is the base layer every later week's claim/structure/conflict pipeline builds on; (2) the 50,000-char truncation is a hard character cut with no semantic-boundary awareness, a latent risk for Week 2's claim extraction. A third, minor finding is that `docs/week1j_acceptance_checklist.md` is now stale against the shipped `write_final_report` default and would fail if executed literally today.

None of the three findings amount to an exploitable security hole or a broken invariant in the code that ships — they are coverage/observability gaps and one doc-drift issue, which is why the verdict is VERIFIED_WITH_LIMITATIONS rather than PARTIALLY_VERIFIED or INCORRECT.
