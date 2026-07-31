# DeepSeek Non-Thinking Smoke Profile + Factor/Relation Endpoint Audit + Historical Rule Learning + Architecture Replay

## Status

**PARTIAL** (honest breakdown, not a blanket pass/fail):

| Component | Status |
|---|---|
| Track A -- DeepSeek smoke profile | PASS (code + tests complete; real smoke run intentionally not executed -- no `DEEPSEEK_API_KEY` configured, and the task's own gate requires explicit user confirmation of a configured key before any real call) |
| Track B -- Factor/Relation endpoint audit | PASS |
| Track C -- Historical rule learning | PASS (0 rules promoted -- audit is complete and the evidence does not clear the promotion bar; per the task's explicit instruction this is a valid PASS, not a failure) |
| Track D -- Historical architecture replay | PARTIAL (core service, CLI, lineage metadata, comparison artifacts, and hermetic tests are complete and used for real acceptance runs; the API endpoint (D7) and frontend UI (D8) were scoped out this session -- see Remaining Limitations) |

Workspace safety baseline (Section 0) was re-verified before starting: branch `comqutor-structure-layer`, HEAD `2fe129705d824d46b4bcf7f0fc1eb43e27972824` (unchanged throughout), all pre-existing uncommitted Sprint changes preserved, `git diff --check` clean at both start and end, no reset/restore/clean/checkout, no commit/push.

---

## Track A -- DeepSeek Non-Thinking Smoke Profile

**Files:** `comqutor_alpha/llm/deepseek_smoke.py` (new), `tests/test_deepseek_smoke_profile.py` (new, 21 tests). `tradingagents/` was not edited.

- **Profile ID:** `comqutor_deepseek_smoke_v1` -- a separate, frozen dataclass (`DeepSeekSmokeProfile`), entirely independent of `research_profiles.ACTIVE_PROFILE_ID` (the formal, Anthropic-only web research profile, which is untouched and still validated to `llm_provider == "anthropic"`).
- **Provider:** `deepseek`
- **Quick model / Deep model:** `deepseek-v4-flash` for both. Chosen after reading the real DeepSeek provider registry (`tradingagents/llm_clients/model_catalog.py`, `capabilities.py`, `api_key_env.py`) rather than guessing: V4 Flash is DeepSeek's cheapest current model and is explicitly documented in this codebase as supporting both thinking and non-thinking modes, so one model covers both tiers.
- **Base URL source:** provider default (`https://api.deepseek.com`, from `OPENAI_COMPATIBLE_PROVIDERS["deepseek"]`) -- the profile does not override it.
- **Debate rounds / Risk rounds:** 1 / 1.
- **Analysts:** `market`, `sentiment` (public wire name for TradingAgents' internal `social`), `news`, `fundamentals` -- the full canonical public set.
- **Temperature:** `0.0`. Verified against DeepSeek's real API docs (`api-docs.deepseek.com/api/create-chat-completion`): temperature range is 0-2, default 1, and 0 is a valid, honored value in non-thinking mode (thinking mode ignores temperature without erroring, but this profile always runs non-thinking).
- **Thinking:** disabled by default via a new field `deepseek_thinking`, overridable through `TRADINGAGENTS_DEEPSEEK_THINKING` (`enabled`/`disabled`; any other value raises `ValueError` immediately at resolve time, before any request). The real parameter contract was confirmed against DeepSeek's live docs (`api-docs.deepseek.com/guides/thinking_mode/`): `extra_body={"thinking": {"type": "enabled"|"disabled"}}`, default `"enabled"`, applies to both `deepseek-v4-flash` and `deepseek-v4-pro`.

**How the toggle actually reaches the request without editing `tradingagents/`:** `OpenAIClient.get_llm()` (`tradingagents/llm_clients/openai_client.py`) only forwards a fixed kwarg whitelist (`_PASSTHROUGH_KWARGS`), which does not include `extra_body` -- so a config value alone cannot reach the real request through the existing plumbing. Instead, `deepseek_smoke.py` defines two small subclasses of the existing `DeepSeekChatOpenAI` (`DeepSeekThinkingEnabledChatOpenAI` / `DeepSeekThinkingDisabledChatOpenAI`) that override `_get_request_payload` to inject `extra_body["thinking"]` -- the exact same extension seam `DeepSeekChatOpenAI` and `MinimaxChatOpenAI` already use for their own provider quirks, not a string-concatenation hack. `deepseek_thinking_scope(mode)` is a `try/finally`-scoped context manager that swaps only the `deepseek` entry in `OPENAI_COMPATIBLE_PROVIDERS` (a frozen `dataclass`, replaced via `dataclasses.replace`, never mutated) to the correct subclass for the duration of one smoke run, then restores the original -- verified by a test that the swap survives an exception inside the `with` block, and by a test that every other provider's registry entry is untouched during the scope.

**No silent fallback:** there is no alternate-provider code path anywhere in `run_deepseek_smoke()` -- a missing `DEEPSEEK_API_KEY` raises `DeepSeekSmokeProfileError("DEEPSEEK_API_KEY_MISSING")` before any network call; any DeepSeek request failure propagates unchanged (verified by a test that mocks the runner to raise and asserts the exception surfaces untouched, with `ANTHROPIC_API_KEY` set but never consulted).

**Debate/risk round *node invocation* (not just config), per A4:** `ConditionalLogic(max_debate_rounds=1, max_risk_discuss_rounds=1)` was driven through its real state machine in a test: the debate path visits exactly `Bull Researcher -> Bear Researcher -> Research Manager` (one full bull/bear exchange, then the manager), and the risk path visits exactly `Aggressive Analyst -> Conservative Analyst -> Neutral Analyst -> Portfolio Manager` (one full round, then the manager) -- confirming `rounds=1` means one complete round, not zero debate.

**Tests (12 required + extras, all passing):** profile loads and is distinct from the formal profile; provider is deepseek; quick/deep models valid; thinking-disabled/-enabled both reach `_get_request_payload`; debate/risk round *node counts* (not strings); four analysts map to the correct internal workflow nodes; missing key fails with a stable reason code; a mocked request failure never touches Anthropic; non-DeepSeek providers' registry entries are untouched during the scope (and the scope restores itself even on exception); env-var override and invalid-value rejection; profile serializes via `dataclasses.asdict` and reconstructs identically; status surface shows real provider/models/rounds/thinking and never leaks the API key value (checked via `repr`/`str` of the whole status dict); invalid profile fields are rejected. **21/21 passed.**

**Real smoke run:** **not executed.** `DEEPSEEK_API_KEY` is not set in this environment (`bool(os.environ.get("DEEPSEEK_API_KEY", "").strip())` => `False`), and the task's own gate requires the user to have *explicitly* confirmed a configured key before any real call -- no such confirmation appears in this conversation. Provider calls made this session: **0** (DeepSeek, Anthropic, or otherwise).

---

## Track B -- Factor Resolution / Relation Endpoint Audit

**Method:** all analysis is read-only over **architecture-replay outputs** (Track D's service), not the stale on-disk artifacts -- because the on-disk `structured_agent_outputs.json` for every historical run still reflects the *pre-coverage-fix* 64-claim truncation from an earlier Sprint in this thread. Auditing the truncated claims would have silently hidden most of the corpus. The replay was produced by directly calling the current, unmodified `relation_grammar.extract_relation_candidates`, `structure_extractor._extract_factors`, and `claim_quality.is_claim_eligible` -- never re-implemented.

**Runs analyzed (6, all historical runs found in the workspace):**

| Ticker (run) | Source run_id | Claims before -> after (full coverage) |
|---|---|---|
| MSFT | `61f3e019-...` | 660 -> 2,097 |
| SNDK (latest, 2026-07-27) | `183b04dd-...` | 632 -> 1,952 |
| SNDK (older, 2026-07-17) | `8d21c047-...` | 664 -> 2,197 |
| MU | `0ba23540-...` | 654 -> 2,072 |
| NVDA | `4ca7dafa-...` | 681 -> 2,357 |
| AMD | `66794ad5-...` | 669 -> 2,200 |

**Totals:** 12,875 full-coverage claims scanned. 3,050 (23.7%) contained language from a required relation-phrase family (causal, dependency, negative-causal, conflict/contrast, conditional).

**Endpoint resolution breakdown** (of the 3,050 relation-like claims):

- Left-only resolved: 143
- Right-only resolved: 0
- Neither resolved: 2,884 (94.5% of relation-like claims -- the claim uses relation-family language but mentions 0-1 of the 13 canonical factors; almost entirely generic market/debate commentary, not a taxonomy or grammar defect)
- Both resolved but rejected: **20**
- (Separately: 3 claims produced a real candidate edge but were excluded by the shared `claim_quality.is_claim_eligible` gate, not by `relation_grammar` -- a downstream-eligibility matter, not a relation-extraction gap.)

**Rejection-reason distribution** (of the 20 "both resolved but rejected" claims, plus the interrogative-abstain and eligibility-gate cases folded in from the full 3,050):

| Reason | Count |
|---|---|
| `NO_CANONICAL_FACTOR` (0 or 1 factor really present despite relation-like language) | 2,790 |
| `ONLY_ONE_FACTOR_RESOLVED` | 136 |
| Interrogative abstain (`?` present -- grammar deliberately abstains) | 103 |
| `OVERLAPPING_FACTOR_ALIASES` | 12 |
| Eligibility-gate exclusion (candidate found, `claim_quality` rejects) | 3 |
| `NEGATED` | 3 |
| `RELATION_RULE_GAP` | 1 |
| `CONDITIONAL_ONLY` | 1 |
| `CONFLICT_SCOPE_FAILURE` | 1 |

**Top unmapped endpoint phrases:** `docs/audits/unmapped_relation_endpoints.csv` (4,635 distinct phrases from a lightweight word-window heuristic, **not** a real parser -- see Remaining Limitations). Manual inspection of every phrase with frequency >= 2 (74 rows) found no phrase that is a coherent, recurring economic concept: the recurring text is generic debate rhetoric ("here's what the bear's...", "i want to be precise about", "does not"), not an un-aliased factor. **Zero rows were classified `ADD_ALIAS_TO_EXISTING_FACTOR`.** No new canonical factor or alias is proposed from this corpus.

**Proposed relation-rule gaps:** exactly the 2 candidates carried into Track C below (both single-occurrence, not promoted).

Full per-claim diagnostics for all 3,050 relation-like claims (agent, claim_index, relation phrase/family, left/right endpoint + canonical factor + match method, alias-overlap spans, candidate-edge result, admission result, rejection reason) are in `docs/audits/relation_endpoint_full_diagnostics.csv`.

---

## Track C -- Historical Learning and Safe Rule Promotion

**Discovery set:** SNDK (both the 2026-07-27 and 2026-07-17 runs).
**Validation set:** MSFT, MU, NVDA, AMD (4 independent historical runs).

`docs/audits/historical_missed_edge_candidates.csv` contains the 20 "both resolved but rejected" candidates, each manually labeled with an explicit `label_reason`:

- **TRUE_RELATION_MISSED: 0**
- **CORRECTLY_REJECTED: 18** -- 12 are a documented, intentional ambiguity (`relation_grammar._ambiguous_factors`'s own docstring names this exact case: "AI CapEx" / "Datacenter CapEx" / "AI Infrastructure" all matching one "ai infrastructure spending" span); the rest are interrogative/hypothetical framing, explicit negation, or debate meta-commentary with no real risk/growth conflict pairing.
- **AMBIGUOUS_REQUIRES_REVIEW: 2** -- both single-occurrence, both requiring manual linguistic confirmation before they could even become a well-formed rule proposal:
  1. A conditional structure ("Foo is a catalyst: If X, Y") where the `if` starts a *later* clause, not `clauses[0]` of the whole claim -- the existing `CONDITIONAL` rule family only anchors to the first clause.
  2. A `reduce`-family verb whose two factor mentions sit in different clauses separated by a relative-clause boundary ("X, which could reduce Y") -- same-clause endpoint search never pairs them, and this script's own endpoint identification for the row is an unverified heuristic, not a confirmed parse.

**Rules considered:** 2 (the two `AMBIGUOUS_REQUIRES_REVIEW` patterns above). **Rules promoted: 0.** **Rules rejected: 2** -- both fail the promotion threshold (>= 3 independent TRUE_RELATION_MISSED claims across >= 2 agents/runs/tickers, OR a standard-syntax pattern with 2 positive + 3 hard-negative fixtures and 0 new false positives): each has exactly 1 occurrence, 1 agent, 1 run, 1 ticker, and zero hard-negative fixtures were ever written to check them.

Per the task's explicit instruction, since no candidate reached the threshold, **no relation/factor production code was modified** and the manifest (`docs/audits/relation_rule_promotion_manifest.json`) records `"status": "NO_RULE_PROMOTED"` with full reasoning for both rejected candidates -- this is reported as a genuine, evidence-backed PASS, not a shortfall. The only production-code touches in this whole session, in `factor_normalizer.py` and `relation_grammar.py`, are two **additive version-constant strings** (`ALIAS_VERSION`, `RELATION_GRAMMAR_VERSION`) consumed by the replay service's lineage metadata -- neither changes any matching, resolution, or extraction behavior (all 2,239 backend tests continue to pass unchanged).

---

## Track D -- Historical Architecture Replay

**Files:** `comqutor_alpha/replay/pipeline.py`, `cli.py`, `__main__.py`, `__init__.py` (new); `tests/test_replay_pipeline.py` (new, 16 hermetic tests).

**Service (D1-D5, D9-D10):** `run_structure_replay(source_run_id, ...)` takes only `raw_agent_outputs.json` as canonical input (raises `ReplaySourceIncompleteError` if absent -- never silently substitutes a stale `structured_agent_outputs.json`), and re-runs the current, unmodified pipeline: `adapt_run_outputs` -> `build_alpha_matches_payload` -> `build_extracted_structures_payload` -> `build_structure_graph_stage` + `score_and_assemble_structure_graph` (activation v1+v2) -> `detect_alpha_conflicts` (called directly as a pure function -- conflicts are written to a replay-local `conflict_results.json`, never persisted via `repository.persist_week4_results`, so replay never writes to the database). Every call passes `llm_gateway=None`; nothing in the chain touches TradingAgents, an LLM provider, or a market-data provider. The source raw artifact's sha256/size/mtime are hashed before and after; any mismatch flips `status` to `"blocked"` rather than claiming success (tested). Each replay writes to a brand-new `outputs/replays/replay-<UTC-timestamp>-<uuid>/` directory (never the source run's own directory; refuses to reuse a non-empty target dir) and always uses a new `replay_run_id` distinct from the source. Lineage metadata (`metadata.json` in the replay dir) includes every field D4 requires: `run_type=architecture_replay`, `replay_run_id`, `source_run_id`, ticker/trade_date/profile/provider/models, `source_raw_sha256`, `pipeline_git_head`/`pipeline_worktree_dirty`, and per-stage versions (`claim_adapter_version`, `taxonomy_version`, `alias_version`, `relation_grammar_version`, `graph_schema_version`, `activation_version`), plus `tradingagents_calls=0`, `llm_provider_calls=0`, `market_data_provider_calls=0`, `database_writes=0`.

**CLI (D6):** `python -m comqutor_alpha.replay --source-run-id <id> [--output-root ...] [--no-persist] [--no-comparison] [--ticker ...] [--strict]`. Prints a JSON summary (claim/factor/candidate-edge/admitted-edge/activation/conflict before-after, provider call count, output path) and exits non-zero on anything but `"completed"` (or on a ticker mismatch, verification-only, never mutating the source).

**Comparison artifact (D9):** `replay_comparison.json` in every replay directory includes before/after counts for claims, factors (with `new_factors`/`removed_factors`), candidate edges, admitted edges, activation (with which alpha IDs newly became active), and the conflict count -- plus full per-edge provenance (`claim_id`, claim text, source/target factor, relation/rule_id, assertion status, admission result) for every new, removed, and unchanged edge. (One bug was caught and fixed during this session: the first admission check compared candidate-edge dicts against graph-stage edge dicts using mismatched field shapes, since `graph_builder` merges per-claim edges into per-`(source,target,edge_type)` rows with `claim_ids` lists -- fixed to check claim-ID membership against the correct merged row, verified by re-running all 6 replays and confirming the 4 new SNDK/MU edges below now correctly report `"admitted"`.)

**Acceptance runs (D12), latest SNDK + MSFT + 4 more historical runs, real replay outputs under `outputs/replays/`:**

| Run | Claims before/after | Factors before/after | Candidate edges before/after | Admitted edges before/after | Activation count | Provider calls |
|---|---|---|---|---|---|---|
| MSFT | 660 / 2,097 | 6 / 8 | 0 / 0 | 0 / 0 | 10 / 10 | 0 |
| SNDK (latest) | 632 / 1,952 | 2 / 7 | 0 / 0 | 0 / 0 | 10 / 10 | 0 |
| SNDK (older) | 664 / 2,197 | 8 / 11 | 0 / 3 | 0 / 3 | 10 / 10 | 0 |
| MU | 654 / 2,072 | 7 / 10 | 0 / 1 | 0 / 1 | 10 / 10 | 0 |
| NVDA | 681 / 2,357 | 10 / 10 | 0 / 0 | 0 / 0 | 10 / 10 | 0 |
| AMD | 669 / 2,200 | 9 / 10 | 0 / 0 | 0 / 0 | 10 / 10 | 0 |

Full detail in `docs/audits/replay_edge_comparison.csv`. Source artifact hash/size/mtime were unchanged for all 6 runs (verified in-process by every `run_structure_replay` call, and independently re-checked via `stat` after the fact). Every new edge recovered (4 total, in SNDK-older and MU) carries full provenance (claim_id, claim text, source/target factor, rule, assertion status) in `replay_comparison.json` -- these are **not** from any Track C rule change (0 rules were promoted); they exist purely because full-coverage replay processed claims that were previously silently truncated beyond the old 64-claim cap, and those claims already satisfied the *existing*, unmodified relation grammar. MSFT, SNDK (latest), NVDA, and AMD remain at 0 admitted edges even with full coverage -- reported honestly, not forced.

**Not implemented this session (D7, D8):** the `POST /api/runs/{id}/replay` API endpoint and job-queue integration, and the frontend "Reprocess with current architecture" button / comparison view. See Remaining Limitations.

---

## Validation

- Backend unit tests (new): `tests/test_deepseek_smoke_profile.py` 21/21 passed; `tests/test_replay_pipeline.py` 16/16 passed.
- Full offline suite: `pytest -q -m "not integration"` -> **2,239 passed, 1 skipped, 47 deselected, 0 failed** (up from a pre-existing 2,202-passed baseline; the +37 are this session's new tests; 0 regressions).
- `ruff check` on every file touched or added this session (`comqutor_alpha/llm/`, `comqutor_alpha/replay/`, `comqutor_alpha/structure_engine/factor_normalizer.py`, `comqutor_alpha/structure_engine/relation_grammar.py`, `tests/test_deepseek_smoke_profile.py`, `tests/test_replay_pipeline.py`): **all checks passed**. (17 pre-existing ruff findings elsewhere in the repo are baseline, untouched by this session.)
- Frontend: `npm test -- --run` -> 129/129 passed (unaffected -- no frontend files were touched this session); `npm run build` succeeded.
- `git diff --check`: clean (exit 0), both before and after this session's work.

---

## Safety

- TradingAgents modified: **No**
- Production taxonomy (`FACTOR_ALIASES`, canonical factor list) modified: **No**
- Relation grammar / production matching behavior modified: **No** (only 2 additive version-constant strings, consumed solely by replay lineage metadata)
- Historical artifacts overwritten: **0** (verified via sha256/size/mtime before-and-after inside every replay call, plus an independent `stat` check after the session)
- Database writes during audit/replay: **0** (conflict detection called as a pure function; persistence never invoked)
- Provider calls during audit/replay: **0**
- Anthropic calls: **0**
- Commit/push: **No**

---

## Remaining Limitations (real, evidenced)

1. **Track D API (D7) and frontend (D8) were not implemented this session.** The core replay service, CLI, and lineage/comparison artifacts are complete, tested, and used for real acceptance runs, but wiring a `POST /api/runs/{id}/replay` endpoint into the existing job-queue/lifecycle system and adding a frontend "Reprocess" button were judged too large an additional surface (new DB/job-queue considerations, ~14 more frontend test scenarios) to implement safely in the same session as three other full tracks without rushing it. The CLI is a complete, working substitute for programmatic/manual use in the meantime.
2. **The `unmapped_relation_endpoints.csv` endpoint-phrase extraction is a lightweight word-window heuristic, not a real parser.** It correctly demonstrates that no phrase in this corpus is a coherent, recurring un-aliased economic concept (0 `ADD_ALIAS_TO_EXISTING_FACTOR` results), but the raw phrase text itself (e.g. "here's what the bear's") is not linguistically clean and should not be read as a proposed alias string.
3. **The two `AMBIGUOUS_REQUIRES_REVIEW` candidates in Track C are single-occurrence.** They are documented as real, plausible rule-family gaps worth revisiting once more independent examples accumulate across future runs, but they were correctly not promoted -- there is currently no safe way to generalize from n=1.
4. **Track A's real DeepSeek smoke run was not executed** (no `DEEPSEEK_API_KEY` in this environment, and no explicit user confirmation of one being configured, which the task itself requires before any real call).
5. **The replay service's `pipeline_worktree_dirty` field will read `true`** for any replay run while this session's own uncommitted Sprint changes remain in the working tree (which they must, per the safety constraints) -- this is by design (D4 explicitly allows a dirty-worktree replay, but requires it be recorded so it is never mistaken for an official reproducible run).

---

## Final Terminal Summary

```
Task:
DeepSeek Smoke + Factor/Relation Audit + Historical Rule Learning

Status:

DeepSeek:
- Profile: comqutor_deepseek_smoke_v1
- Provider: deepseek
- Quick model: deepseek-v4-flash
- Deep model: deepseek-v4-flash
- Thinking: disabled (default; TRADINGAGENTS_DEEPSEEK_THINKING overrides, invalid values raise immediately)
- Debate rounds: 1 (verified via real ConditionalLogic node sequence)
- Risk rounds: 1 (verified via real ConditionalLogic node sequence)
- Analysts: market, sentiment, news, fundamentals
- Silent fallback: None (no alternate-provider code path exists; failure always propagates)
- Real provider calls: 0 (no DEEPSEEK_API_KEY configured; real smoke run not executed)

Audit:
- Runs: 6 (MSFT, SNDK x2, MU, NVDA, AMD -- full-coverage architecture replay)
- Claims: 12,875
- Relation-like claims: 3,050
- Missed true relations: 0
- Correct rejections: 18 (of 20 both-resolved-but-rejected candidates)
- Ambiguous: 2 (both single-occurrence, not promotable)
- Top endpoint gaps: none reach ADD_ALIAS_TO_EXISTING_FACTOR or PROPOSE_NEW_CANONICAL_FACTOR confidence

Rule learning:
- Candidate rules: 2
- Promoted rules: 0
- Rejected rules: 2 (below promotion threshold: each n=1, 1 agent/run/ticker, 0 hard-negative fixtures)
- New candidate edges: 4 (SNDK-older x3, MU x1 -- recovered by full coverage alone, not by any rule change)
- New admitted edges: 4
- False positives: 0
- Production taxonomy changed: No

Validation:
- Unit tests: 21/21 (DeepSeek smoke) + 16/16 (replay pipeline) passed
- Offline suite: 2,239 passed, 1 skipped, 0 failed
- Ruff: clean on all touched/added files
- Frontend tests/build: 129/129 passed; build succeeded
- git diff --check: clean

Files changed:
comqutor_alpha/llm/__init__.py, comqutor_alpha/llm/deepseek_smoke.py,
comqutor_alpha/replay/__init__.py, comqutor_alpha/replay/pipeline.py,
comqutor_alpha/replay/cli.py, comqutor_alpha/replay/__main__.py,
comqutor_alpha/structure_engine/factor_normalizer.py (+1 version constant),
comqutor_alpha/structure_engine/relation_grammar.py (+1 version constant),
.gitignore (+outputs/replays/),
tests/test_deepseek_smoke_profile.py, tests/test_replay_pipeline.py,
docs/audits/historical_missed_edge_candidates.csv,
docs/audits/unmapped_relation_endpoints.csv,
docs/audits/relation_endpoint_full_diagnostics.csv,
docs/audits/relation_rule_promotion_manifest.json,
docs/audits/replay_edge_comparison.csv,
docs/deepseek_smoke_and_factor_relation_learning_report.md

Historical artifacts changed: 0
Database writes: 0
TradingAgents changed: No
Anthropic calls: 0
Commit/push: No
```
