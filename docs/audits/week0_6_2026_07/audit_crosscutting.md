# COMQUTOR Alpha — Cross-Cutting Audit (Redundancy + Validation Matrix)

Repo: `/Users/xiangmao/COMQUTOR-Alpha-`, branch `comqutor-structure-layer`, HEAD `64e657958aa1db32528d55e8b9c5520b387f86fc`.
Scope: `comqutor_alpha/` production tree + `tests/`. Cross-cutting concerns only — per-week correctness is covered by other agents.

---

## 1. Redundancy / Duplication / Dead-Abstraction Findings

### 1.1 `clamp_score` vs `clamp_percent` — twin clamping functions with a proven behavioral divergence (HIGH CONFIDENCE, PROVEN)

- **Copy A**: `comqutor_alpha/structure_engine/structure_schema.py:32-37` — `clamp_score(value, minimum=0.0, maximum=1.0)`.
- **Copy B**: `comqutor_alpha/graph_engine/graph_schema.py:53-70` — `clamp_percent(value, minimum=0.0, maximum=100.0)`.

Both exist to do the exact same job — "coerce an untrusted numeric score into a bounded range, never raise" — for two different score domains (0–1 confidence/match scores in Week 2 structure output vs 0–100 activation/coherence scores in Week 3 graph output). They are implemented independently, in different files, with different names.

`clamp_percent` was written with **explicit NaN/Inf handling** (`math.isnan`/`math.isinf`, documented in its docstring: *"Non-finite input is not an error here: it is deterministically clamped... so a bad upstream number can never propagate"*). `clamp_score` has **no such handling** — it only catches `TypeError`/`ValueError` from `float(value)`, which a `float('nan')` input does not raise.

Verified empirically (`.venv/bin/python`):
```
clamp_score(nan)        = nan      # NOT clamped — bug
clamp_score(inf)        = 1.0      # clamps correctly, but only by comparison-operator luck
clamp_percent(nan,0,1)  = 0.0      # correctly clamped to minimum
clamp_percent(inf,0,1)  = 1.0
```
`clamp_score(nan)` returns `nan` unchanged because Python's `min`/`max` silently fail to reorder on NaN comparisons (`max(nan, 0.0)` returns `nan`, not `0.0`) — this is the exact defect `clamp_percent`'s explicit NaN branch was written to avoid, in the other module.

**Drift scenario, concretely traced**: `clamp_score` is used at `comqutor_alpha/structure_engine/structure_extractor.py:199` to set the `"confidence"` field of every extracted structure edge. If any confidence-computation path upstream ever produces `float('nan')` (division by a zero denominator, etc.), that `NaN` is written into `extracted_structures.json` as JSON `NaN` (Python's `json.dumps` emits non-standard `NaN` literals by default, which is itself a second latent interop risk). It is **not** caught at the point where it originates. It only gets caught many stages later: `comqutor_alpha/storage/db/repository.py`'s `_strict_number` (line ~111) and `_NAMED_SCORE_RANGES["confidence"] = (0.0, 1.0)` (line ~159) explicitly call `math.isfinite()` and reject the value with `GraphPersistenceError`/`AGENT_OUTPUTS_DB_WRITE_FAILED` — surfacing as an opaque DB-write failure in Week 3/4 persistence instead of at the Week 2 source of the bad value.
- **What the correct boundary looks like**: one shared `clamp(value, minimum, maximum)` in a common module (e.g. `structure_schema.py` or a new `numeric_utils.py`), with the NaN/Inf handling written once, imported by both `structure_schema.py` and `graph_schema.py` with their respective default ranges.
- **Would existing tests catch the drift?** No. `grep -rn "clamp_score\|clamp_percent" tests/*.py` returns **zero** matches — neither function is unit-tested at all, let alone with NaN/Inf inputs.
- **Impact**: correctness (a real, provable divergent-behavior bug for the `confidence` field on any current NVDA/QQQ fixture that happens to compute a non-finite score), plus maintainability (two clamps that must be kept in sync by hand).

### 1.2 Alpha conflict weights duplicated between the taxonomy YAML and a hardcoded Python validation dict (MEDIUM CONFIDENCE — guarded, but still double-maintained)

- **Copy A (data)**: `comqutor_alpha/alpha_library/alpha_taxonomy_v1.yaml` — each alpha's `conflict_alphas[].contradiction_weight`, e.g. `A101→A304: 0.90`, `A301↔A304: 0.85`, `A001↔A501: 0.85`, `A003↔A501: 0.85`, `A601↔A304: 0.80`, `A601↔A501: 0.80`.
- **Copy B (code)**: `comqutor_alpha/alpha_library/alpha_loader.py:41-48` — `MANDATORY_CONFLICT_WEIGHTS` hardcodes the identical six pairs and weights, then `validate_taxonomy()` (line 116) asserts the YAML values match Copy B within `abs(...) > 0.05` tolerance (line 133-136).

**Drift scenario**: because `validate_taxonomy` actively asserts equality (with 0.05 tolerance), a straight silent drift is *not* possible today — changing the YAML's `A101→A304` weight to, say, `0.60` without updating `MANDATORY_CONFLICT_WEIGHTS` raises `ValueError` at taxonomy load time (`load_alpha_taxonomy` calls `validate_taxonomy`), which happens on nearly every request path. So this is a self-checking duplication rather than a silent-drift one — but it means every legitimate recalibration of a conflict weight requires editing **two files in lockstep** (YAML + the Python constant), and the 0.05 tolerance band means a "legitimate" YAML change within 0.05 of the hardcoded value would pass unnoticed even though the two sources now literally disagree.
- **Correct boundary**: derive `MANDATORY_CONFLICT_WEIGHTS`' invariant ("these 6 pairs must exist in both directions") without hardcoding the weight *values* redundantly — e.g. validate presence/symmetry only, or read the expected values from the YAML itself at test time (a "the loader agrees with itself" check) rather than encoding a second copy of the numbers in production code.
- **Test coverage of drift**: `validate_taxonomy` itself is the safety net (runs on every taxonomy load), so this is functionally self-testing, unlike most other findings here.
- **Impact**: maintainability only (double edit burden), not a live correctness risk given the built-in guard.

### 1.3 Write-then-immediate-reread churn: `structured_agent_outputs.json` (PROVEN, LOW-IMPACT)

- **Write site**: `comqutor_alpha/api/routes_research.py:517` calls `save_structured_agent_outputs(run_dir, llm_gateway=llm_gateway)` and **discards its return value**.
  - `save_structured_agent_outputs` (`comqutor_alpha/structure_engine/structured_output_adapter.py:756-764`) computes `output = adapt_run_outputs(...)` in memory, then returns `save_json_record(...)`, whose own return value is `atomic_write_text(...)`'s return — a `Path`, not the payload dict (`comqutor_alpha/storage/file_store.py:132-139`).
- **Read site**: three lines later, `comqutor_alpha/api/routes_research.py:524-526` calls `load_json_record(run_id, "structured_agent_outputs.json", output_root=output_root)`, re-opening and re-`json.load`-ing the exact same file that was written in the same function, same thread, milliseconds earlier — purely to get back the dict `save_structured_agent_outputs` had already computed in memory and thrown away.
- **Trace confirms no other consumer** sits between the write (line 517) and the read (line 524) — this is pure round-trip churn, not caching/audit/recovery.
- **Correct boundary**: have `save_structured_agent_outputs` optionally return `(path, output)`, or have the caller call `adapt_run_outputs` + `save_json_record` itself instead of going through the wrapper, eliminating the disk write→read→reparse cycle.
- **Impact**: performance only (one extra disk I/O + JSON parse per run, not correctness — the file did get written correctly first), and it's minor at current scale.

### 1.4 Score-field validators duplicated between the DB write path and the API read/projection path (MEDIUM CONFIDENCE — intentionally duplicated, but ranges can still drift)

- **Copy A (write path)**: `comqutor_alpha/storage/db/repository.py:97-159` — `_required_text`, `_optional_text`, `_strict_number`, `_string_list`, and `_NAMED_SCORE_RANGES = {"confidence": (0.0, 1.0), "match_score": (0.0, 1.0), "activation_score": (0.0, 100.0), "conflict_score": (0.0, 100.0), ...}`.
- **Copy B (read/projection path)**: `comqutor_alpha/api/agent_output_reader.py:135-208` — `_validate_flat_str_list`, `_validate_bounded_nonempty_text`, `_validate_confidence` (hardcodes `0.0 <= number <= 1.0` again at line ~168), `_validate_claim_index`, `_require_nonempty_text`, `_require_valid_direction`.

Both validate essentially the same structured-agent-output record shape (claim text bounds, confidence/score ranges, string-list fields) but were written independently with different helper names and no shared range constants. The code is self-aware of this: `agent_output_reader.py`'s `_require_nonempty_text` docstring explicitly states *"this is the whitelist projection layer's own, independent type guarantee, not a substitute for (or a duplicate of) that adapter check"* — i.e. this is a deliberate defense-in-depth design (don't trust the DB write path was correct; re-validate on read), not an accident.
- **Drift scenario**: because the `confidence` range `(0.0, 1.0)` is a raw literal in *both* files (`repository.py`'s `_NAMED_SCORE_RANGES` dict and `agent_output_reader.py`'s `_validate_confidence`), a business decision to widen the range (e.g. allow `confidence` up to `1.2` for a new scoring mode) requires editing both. If only one is updated, one layer will reject data the other layer just wrote — data that was valid on write becomes `AGENT_OUTPUTS_CORRUPTED` on read, or vice versa.
- **Correct boundary**: keep the two independent validation *functions* (legitimate defense-in-depth) but pull the numeric *range constants* (`0.0–1.0`, `0.0–100.0`, `MAX_CLAIM_CHARS`) into one shared module both files import, so the bounds can never disagree even though the enforcement stays doubled.
- **Test coverage of drift**: not checked directly; no test asserts the two range tables are equal.
- **Impact**: low today (values currently agree), but a latent maintenance trap given the documented "independent by design" stance.

### 1.5 `0.35` appearing across `alpha_mapper.py` and `structure_extractor.py` — investigated, **not** real duplication

`comqutor_alpha/structure_engine/alpha_mapper.py` uses `0.35` for `DEFAULT_MIN_MATCH_SCORE`, several `GENERIC_KEYWORD_WEIGHTS` entries, and `FACTOR_ALPHA_WEIGHTS` cell values; `comqutor_alpha/structure_engine/structure_extractor.py:228` returns `0.35` as the confidence for a *negated* claim relation. These are coincidentally the same literal but govern semantically unrelated business rules (alpha-matching threshold vs. edge-confidence-for-negation) in different pipelines. Flagging this as duplication would be a false positive — noted here only because the task explicitly asked to check `0.35` and this was the closest match; no drift risk exists because there's no shared invariant between them.

### 1.6 Thin wrapper functions (minor, low-impact)

- `comqutor_alpha/api/routes_alpha_library.py:59-60` (`get_alpha_library_route`) forwards with zero added logic to `get_alpha_library()` (same file, lines 36-43); `get_alpha_detail_route` (lines 63-64) forwards to `get_alpha_detail(alpha_id)` (lines 46-50). This is the standard FastAPI "thin route handler over a testable pure function" pattern — technically a zero-value forward, but it exists for a real reason (unit-testability of `get_alpha_library`/`get_alpha_detail` without an HTTP client), so it is not flagged as a maintenance risk.
- `comqutor_alpha/alpha_library/alpha_loader.py:83-85` (`get_alpha_by_id`) forwards to `taxonomy.get(alpha_id)` but does add a real default (`taxonomy = taxonomy or load_alpha_taxonomy()`), so it is not purely thin.

### 1.7 File + DB parallel storage of the same data (structural, by design — documented, not silently divergent)

`comqutor_alpha/api/routes_research.py`'s `_run_week1_week2_artifact_pipeline` and `_run_week3_graph_pipeline` (lines 505-663) write every stage's output to **both** the filesystem (`save_json_record`) **and** Postgres/SQLite (`GraphPersistenceRepository.persist_agent_outputs`/`persist_run`/`persist_week4_results`). `build_research_response` (line 325 onward) reconciles readiness by reading **file-existence booleans** for Week 1-2 and a separate **status marker file** (`WEEK3_PIPELINE_STATUS_ARTIFACT_FILENAME`) for Week 3/4, rather than querying the DB for status — the DB is a secondary consumer path (`GET .../graph`, `GET .../agent-outputs`), not the source of readiness truth. This is explicitly documented in code comments (`routes_research.py:338-347`) as a deliberate "DB-free readiness signal" design, and the DB write for Week 3/4 is wrapped in `contextlib.suppress(Exception)` (lines 634, 647) specifically so a DB failure cannot make an already-file-persisted stage look failed. **This can drift**: if the DB write silently fails (suppressed at line 647), the file-based status marker still says `outcome: "success"` for Week 3, but `GET /agent-outputs` or `GET /graph` (DB-backed reads) can return `AGENT_OUTPUTS_UNAVAILABLE`/empty — i.e., file says ready, DB says not-ready, and nothing reconciles the two after the fact except a future successful retry overwriting the marker. No automated reconciliation/repair job was found for this state.

---

## 2. Case-Specific / Fixture-Gaming Branch Findings

**NONE FOUND.**

Checked systematically:
- `grep -rn "if ticker ==\|if run_id ==\|== \"test-\|== 'test-"` across `comqutor_alpha/**/*.py` → zero matches.
- `grep -rn "NVDA\|QQQ"` in non-test production files → exactly one hit: `comqutor_alpha/structure_engine/structured_output_adapter.py:41`, inside `ENTITY_TERMS = ("NVDA", "NVIDIA", "GPU", "AI", "datacenter", ...)`. This is a legitimate domain-vocabulary constant (the product's demo/MVP domain is an NVDA-centric AI/semiconductor thesis — consistent with the alpha taxonomy's `AI CapEx`/`GPU Demand`/`Semiconductor Cycle` factors), not a conditional branch and not gated on a specific run/test ID. It is exercised the same way for any ticker's claim text, not special-cased for NVDA specifically.
- No hardcoded alpha IDs, claim IDs, or run IDs were found gating production behavior differently for test-fixture values.

---

## 3. Validation Command Matrix

| Command | Dir | Exit code | Result | Skip reasons | Network/external provider? | Production entrypoint exercised? |
|---|---|---|---|---|---|---|
| `.venv/bin/python -m compileall comqutor_alpha` | backend | 0 | All files compiled, no syntax errors | — | No | Static analysis only |
| `git diff --check` | backend | 0 | Clean, no whitespace/conflict-marker issues flagged | — | No | Static |
| `.venv/bin/python -m pytest -q -m "not integration"` (**run 1**, from prior parallel session, read from `run1_offline.txt`) | backend | 1 | **6 failed, 1587 passed, 1 skipped, 46 deselected**, 69 subtests passed, 141.21s | `test_bedrock_provider.py`: `langchain_aws` not installed | No | Real FastAPI TestClient app + real SQLite/Postgres repository code paths |
| `.venv/bin/python -m pytest -q -m "not integration"` (**run 2**, this session) | backend | 1 | **11 failed, 1582 passed, 1 skipped, 46 deselected**, 69 subtests passed, 164.86s | same as run 1 | No | same as run 1 |
| `.venv/bin/python -m pytest -q -m integration` | backend | 0 | **44 passed, 2 skipped, 1594 deselected** | `tests/test_deepseek_reasoning.py:209`: "DEEPSEEK_API_KEY not set (or placeholder); skipping live API call"; `tests/test_week2_llm.py:313`: "set COMQUTOR_RUN_WEEK2_PROVIDER_SMOKE=1 to allow three provider calls" | Yes — real Postgres on 127.0.0.1:5433 (localhost only, no external network) | Yes — real DB round trips (schema, persistence, isolation tests) |
| `.venv/bin/ruff check .` (read-only, no `--fix`) | backend | 1 | **19 errors** (16 auto-fixable, 3 more fixable with `--unsafe-fixes`) — mostly `I001` unsorted imports across `comqutor_alpha/*` and `tests/*`, plus `UP037` (quoted type annotation) and 3× `SIM105` (`try/except/pass` in `comqutor_alpha/storage/file_store.py` lines ~114, 119, 126 — see note below) | — | No | Static analysis only |
| `npm run typecheck` | frontend | 0 | Clean (`tsc --noEmit` on both `tsconfig.app.json` and `tsconfig.node.json`) | — | No | Static |
| `npm run lint` | frontend | 1 | **3 errors, 2 warnings** — but **all 3 errors and both warnings are inside `frontend/.vite/deps/*.js`**, a Vite dependency-optimizer cache directory that is untracked (`?? frontend/.vite/` in `git status`) and not excluded by `frontend/eslint.config.ts`'s `ignores: ["dist", "coverage"]`. Zero errors/warnings were reported against actual `src/**/*.{ts,tsx}` source files. | — | No | Static — and the "failure" is a lint-config gap (missing `.vite` in `ignores`), not a source-code defect |
| `npm test -- --run` | frontend | 0 | **90 passed** across 12 test files | — | No | Real component/route rendering via vitest + testing-library |
| `npm run build` | frontend | 0 | `tsc -b && vite build` succeeded, 58 modules, `dist/` produced (224.59 kB JS, 11.68 kB CSS) | — | No | Real production build |
| `npx playwright test` | frontend | 0 | **7 passed** (26.3s), 1 worker, chromium | — | Yes — spins up real backend (port 18001) + frontend (port 15173) on localhost via `webServer: "COMQUTOR_API_PORT=18001 COMQUTOR_FRONTEND_PORT=15173 ../scripts/run_w5_demo.sh"`, no external network | **Yes, full end-to-end**: real HTTP requests against a live FastAPI backend and a live built/served frontend, covering research submission, graph/conflict pages, 202/404 handling, and responsive layout — this is the most "real" validation in the matrix |

**Ruff `SIM105` findings** (`comqutor_alpha/storage/file_store.py:114-117, 119-122, 126-129`): three `try/except (...)/pass` blocks around `os.chmod`/`os.replace`/`tmp_path.unlink()` in the atomic-write helper. These are the broad-exception-adjacent pattern the audit asked about (§1.4 of the prompt) — each swallows `AttributeError`/`NotImplementedError`/`OSError` (chmod not supported, e.g. on some filesystems) or `OSError` (best-effort temp-file cleanup) and lets the write still report success. This is intentional best-effort behavior (permissions/cleanup are not correctness-critical to the atomic write itself, which already completed via `os.replace`), not a case of a real pipeline failure being hidden — flagged here per instructions, not read-only tool `.venv/bin/ruff check .` was not modified/fixed.

---

## 4. Two-Run Offline Suite Diff — Order-Dependency / State-Pollution Finding (CONFIRMED, HIGH SEVERITY)

Run 1 (prior session) and Run 2 (this session) of `pytest -q -m "not integration"` produced **different failure sets**, not just different counts:

**Failing in both runs (6, stable)**:
- `tests/test_api_system_routes.py::test_ready_requires_database`
- `tests/test_api_system_routes.py::test_ready_missing_migrations_is_not_ready`
- `tests/test_research_profiles.py::test_http_model_and_config_fields_cannot_override_the_profile`
- `tests/test_research_profiles.py::test_post_returns_503_before_claim_when_credential_missing`
- `tests/test_w5_1b_api.py::test_real_disabled_returns_503_before_claim`
- `tests/test_w5_1b_final_patch.py::test_post_returns_503_before_claim_on_native_config_exception`

**Additional failures only in run 2 (5 new)**, all in `tests/test_w5_1b_api.py`:
- `test_post_new_offline_request_returns_202_queued` — got HTTP 500 instead of 202
- `test_post_completed_reuse_returns_200` — got HTTP 500 instead of 200
- `test_run_id_conflict_returns_409` — got HTTP 500 instead of 202 (on first POST)
- `test_invalid_force_refresh_returns_409` — got HTTP 500 instead of 202 (on first POST)
- `test_fake_real_execution_completes_with_server_side_config`

**Root cause, traced**: `test_real_disabled_returns_503_before_claim` (failing in *both* runs) asserts `history == []` after calling `build_write_repository_from_env(str(tmp_path))`, but the actual assertion failure shows **22 pre-existing rows** already in the queried table before this test's own POST even ran. Since `tmp_path` is a fresh, unique per-test directory, a genuinely isolated SQLite-per-test setup could never accumulate rows across process invocations. The mechanism: `comqutor_alpha/storage/db/engine.py:59-65` (`resolve_database_url`) reads `COMQUTOR_DATABASE_URL` from `os.environ` **before** ever consulting the `output_root`/`tmp_path` argument — `build_write_repository_from_env` (`comqutor_alpha/storage/db/repository.py:1484-1494`) is documented as reading "server environment configuration," and when that env var is present (as it is in this environment, per `.env`, for the real Postgres instance used by the integration suite), every "offline" test that calls it silently connects to and writes into the **same persistent, shared Postgres database** as the integration suite — regardless of the `tmp_path` it was given, and regardless of the `not integration` marker. Rows written by run 1's `test_w5_1b_api.py` executions persist in that real DB and are still present when run 2 starts, and vice versa; the 500s in run 2 are consistent with downstream logic (e.g. conflict/uniqueness checks in `claim_research_run`) tripping over stale/duplicate state left by run 1.
- **This is a genuine order-dependency / shared-mutable-state risk**, not flakiness from timing: the "offline" suite is not actually offline whenever `COMQUTOR_DATABASE_URL` is set in the ambient environment, and repeated invocations are not idempotent/isolated from each other.
- **Impact**: any CI setup that (a) exports `COMQUTOR_DATABASE_URL` for its integration job and (b) doesn't scope it away from the "offline" job would see this exact non-determinism — tests failing or passing depending on unrelated prior test runs against the same database, not on the code under test.

---

## 5. Worktree State

`git status --short` before and after this audit: only pre-existing untracked `frontend/.vite/` (present at session start, a Vite build-cache directory, not created or touched by this audit). `git diff --stat` is empty. No tracked file was modified. No `.env` content or credentials were included in this report.
