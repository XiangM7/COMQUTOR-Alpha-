# COMQUTOR Alpha upstream baseline

Recorded on 2026-07-13 before COMQUTOR implementation changes.

## Repository identity

- Branch: `tested`
- Commit: `a9028b5cdc10e76f39947a9bf77c0764f6390bf4`
- Package version: `tradingagents==0.3.0`
- Remotes: private fork `origin`; TauricResearch repository `upstream`
- Tag at HEAD: none
- Worktree before implementation: clean
- `AGENTS.md`: none found in or above the repository

The local repository has no fetched `upstream/main` remote-tracking ref at the
time of capture, so the commit hash above—not a guessed upstream tag—is the
reproducibility anchor.

## Environment used for the verified baseline

- macOS arm64
- Python 3.13.5 (`.venv/bin/python`)
- Pydantic 2.13.4
- LangGraph 1.2.9
- LangChain Core 1.4.9
- pytest 9.1.1
- Ruff 0.15.21

The project CI uses Python 3.12. Python 3.13.5 is an additional local
compatibility check, not a change to the declared support policy (`>=3.10`).

## Reproduce from a clean checkout

```bash
python -m venv .venv
.venv/bin/python -m pip install -e '.[dev]'
.venv/bin/python scripts/verify_upstream_baseline.py
.venv/bin/pytest -q
.venv/bin/ruff check .
```

The offline verifier performs no provider or market-data calls and needs no
API key. It checks the source-level integration seam and a sanitized state
fixture.

## Exact pre-task results

The first `pytest -q` attempt used the unrelated global interpreter before
dependencies were installed and stopped during collection with 33 missing-
dependency errors. It is recorded as an environment preflight failure, not a
code failure and not a passing baseline.

After an isolated editable dev install:

- `.venv/bin/pytest -q`: **490 passed, 2 skipped, 69 subtests passed** in 23.26s.
- `.venv/bin/ruff check .`: **All checks passed**.
- Skip 1: optional `langchain_aws`/Bedrock dependency not installed.
- Skip 2: live DeepSeek call not run because `DEEPSEEK_API_KEY` was absent.

No real LLM-provider test is represented as passing. The baseline is the
offline repository suite plus the two explicit skips above.

## Known baseline constraints

- A real `TradingAgentsGraph.propagate()` run requires a configured LLM
  provider and live data access; it was not run for this offline baseline.
- The upstream graph writes its normal logs and trading-memory state. COMQUTOR
  will access it through an adapter and will keep that upstream decision
  comparison-only.
- Provider output remains nondeterministic; COMQUTOR deterministic stages must
  be replayable from saved reports and claims.
