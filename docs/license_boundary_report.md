# License Boundary Report

**This is a factual inventory, not legal advice.** It does not conclude
that this project may be commercially distributed, that any license here
permits any particular business model, or that no legal risk exists.
**Consult qualified counsel before commercial distribution.**

See the companion machine-readable inventory:
[docs/third_party_inventory.csv](third_party_inventory.csv) (61 rows).
Every `detected_license` value in that CSV was read from repo-local
evidence only (the root `LICENSE` file, installed Python package metadata
via `importlib.metadata`, and frontend `node_modules/*/package.json`
`"license"` fields) -- nothing here was looked up online or guessed from a
package name.

## 1. Original COMQUTOR code

`comqutor_alpha/` (the entire package: API, structure engine, graph
engine, conflict engine, data sanity, evaluation harness, storage). No
license file of its own; covered by the repo-root `LICENSE` (Apache-2.0).

## 2. Modified TradingAgents upstream code

The repo root is packaged as `tradingagents` (`pyproject.toml`: `name =
"tradingagents"`), and the root `README.md` is verbatim the upstream
TauricResearch/TradingAgents README (links to
`https://github.com/TauricResearch/`, install instructions reference
`git clone https://github.com/TauricResearch/TradingAgents.git`). This is
the strongest textual evidence of upstream origin found in-repo; no
explicit "this is a fork of commit X" provenance statement exists.

Files under `tradingagents/` that carry local COMQUTOR/DeepSeek-related
edits (grep for `COMQUTOR|DeepSeek|canonical_relation` inside
`tradingagents/*.py`, cross-checked against continuous `git log --follow`
history that shows no repo-split/import event):

- `tradingagents/comqutor_outputs.py` -- explicitly states in its own
  docstring/comments that everything COMQUTOR-specific belongs in
  `comqutor_alpha/` and that `tradingagents/` "must never be edited for
  this task" (a stated project convention, evidenced in
  `comqutor_alpha/llm/deepseek_smoke.py`'s own docstring) -- i.e. this
  file's presence *inside* `tradingagents/` is itself a pre-existing,
  narrow exception to that convention, predating this sprint.
- `tradingagents/llm_clients/model_catalog.py`
- `tradingagents/llm_clients/api_key_env.py`
- `tradingagents/llm_clients/capabilities.py`
- `tradingagents/llm_clients/openai_client.py`

No LICENSE/NOTICE file exists inside `tradingagents/` separate from the
repo-root `LICENSE`; no per-file license/copyright header exists in any
sampled `tradingagents/` file.

**Not modified by this sprint or by the Structure/Evidence/Conflict
integrity sprints preceding it** -- `git diff --stat` for the current
session shows no changes under `tradingagents/`.

## 3. Unmodified third-party dependencies

See [third_party_inventory.csv](third_party_inventory.csv), rows with
`modified = No`. Notably:

- **`backtrader`** (`pyproject.toml` `[project.dependencies]`):
  **GPL-3.0-or-later**. A copyleft license. Whether depending on
  `backtrader` as an ordinary Python import obligates the rest of this
  codebase to also be GPL-licensed upon distribution is a genuinely
  disputed question under GPL's own text (Python has no
  compile-time/link-time boundary the way C does) -- **this is the single
  highest-priority item in this inventory to raise with counsel before
  any commercial distribution.**
- **`psycopg[binary]`**: **LGPL-3.0-only**. Weak copyleft -- generally
  permits use as an unmodified library dependency without extending GPL
  obligations to the whole application, but confirm this holds for the
  specific `[binary]` wheel (which bundles a compiled `libpq`) before
  distribution.
- **`tqdm`**: **MPL-2.0 AND MIT** (dual/file-level licensing per its own
  declared metadata) -- file-level weak copyleft on the MPL-2.0-covered
  files.
- Every other backend and frontend dependency inventoried is permissive
  (MIT / BSD-3-Clause / Apache-2.0 / PSF-2.0).

## 4. Generated artifacts

`outputs/runs/`, `outputs/replays/`, `outputs/evaluations/` -- runtime
data, not licensed code. Contents are derived from TradingAgents/LLM
Provider output and are subject to each Provider's own output-usage
terms (e.g. Anthropic's, DeepSeek's), which is a separate question from
any *code* license here and out of scope for this report.

## 5. Documentation

`docs/`, `README.md`, `README_DEV.md`, this file -- original COMQUTOR
content, covered by the repo-root Apache-2.0 `LICENSE`.

## 6. Test fixtures

`tests/fixtures/`, `scripts/w5_demo_fixtures.py`, `evaluation/golden_cases/`
-- original COMQUTOR test data (synthetic/sanitized claim text, not
distributed with the product; `distributed_with_product = No` in the
inventory).

## 7. Provider integrations

`tradingagents/llm_clients/*.py` wrap each LLM Provider's LangChain
package (`langchain-openai`, `langchain-anthropic`,
`langchain-google-genai`) -- no raw `openai`/`anthropic`/`deepseek` SDK
import exists anywhere in this repo (confirmed by grep across
`comqutor_alpha/` and `tradingagents/`); DeepSeek specifically is reached
via an OpenAI-compatible chat-completions API through a custom
`DeepSeekChatOpenAI` subclass (`comqutor_alpha/llm/deepseek_smoke.py`),
not a dedicated `deepseek` package. These wrapper files are among the
"modified TradingAgents upstream code" listed in section 2.

## Production files inside `tradingagents/`

All of `tradingagents/` is production code (imported at runtime by both
the `tradingagents` CLI entry point and `comqutor_alpha`'s research
pipeline via `comqutor_alpha/runners/tradingagents_runner.py`) -- there is
no separate "docs-only" or "example-only" subset to exclude.

## COMQUTOR files that call into TradingAgents

(grep for `tradingagents` imports across `comqutor_alpha/`):

```
comqutor_alpha/adapters/tradingagents_output_writer.py
comqutor_alpha/api/main.py
comqutor_alpha/api/routes_replay_all.py
comqutor_alpha/api/routes_research.py
comqutor_alpha/api/server.py
comqutor_alpha/llm/__init__.py
comqutor_alpha/llm/canonical_prompt_injection.py
comqutor_alpha/llm/deepseek_smoke.py
comqutor_alpha/replay/cli.py
comqutor_alpha/replay/pipeline.py
comqutor_alpha/research_lifecycle.py
comqutor_alpha/research_profiles.py
comqutor_alpha/research_progress.py
comqutor_alpha/runners/tradingagents_runner.py
comqutor_alpha/server_execution.py
comqutor_alpha/storage/file_store.py
comqutor_alpha/structure_engine/canonical_relation_block.py
comqutor_alpha/structure_engine/structure_extractor.py
comqutor_alpha/structure_engine/structured_output_adapter.py
comqutor_alpha/structure_engine/week2_llm.py
```

## Could prompt injection move to a wrapper layer instead of `tradingagents/` edits?

Partially, already: `comqutor_alpha/llm/canonical_prompt_injection.py`
already injects the COMQUTOR Structure Output Contract into existing
TradingAgents prompts from *outside* `tradingagents/` (a wrapper-layer
approach, not a `tradingagents/` file edit) -- this is the established
pattern for new prompt content going forward. The five files listed in
section 2 predate that pattern and were not revisited in this sprint
(out of scope: this sprint makes no code changes to `tradingagents/` or
its prompts).

## Licenses and attribution to confirm before commercial release

1. Fill in the LICENSE file's copyright-holder placeholder (or obtain
   counsel's guidance on whether an explicit holder name is required).
2. Resolve the `backtrader` (GPL-3.0-or-later) and `psycopg[binary]`
   (LGPL-3.0-only) questions above with counsel.
3. Confirm whether Apache-2.0's NOTICE-file provisions apply given no
   NOTICE file currently exists anywhere in this repo or in
   `tradingagents/` upstream (as vendored here).
4. Confirm the `langchain-aws` (Bedrock, optional `[bedrock]` extra)
   license -- not verifiable offline in this sprint since the extra is
   not installed in this environment.
5. Confirm attribution requirements toward TauricResearch/TradingAgents
   specifically (beyond Apache-2.0's own notice-preservation requirement)
   before any public/commercial release that highlights this repo's
   provenance.

## Unknowns

- `langchain-aws`: license UNKNOWN (extra not installed; see
  third_party_inventory.csv).
- No formal "fork point" / upstream commit reference is recorded anywhere
  in-repo for the `tradingagents/` vendoring -- provenance is inferable
  only from README content and package naming, not a stated declaration.
- The `cli/` directory's exact modification delta versus upstream was not
  audited file-by-file in this sprint (flagged `VERIFY_WITH_COUNSEL_OR_UPSTREAM`
  in the inventory, confidence `medium`).

---

**Consult qualified counsel before commercial distribution.**
