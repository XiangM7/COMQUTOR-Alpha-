# v0.2 Candidate 3 — Fresh E2E Plan (FROZEN BEFORE EXECUTION)

**Run type: `FRESH_END_TO_END_VALIDATION`.** This is operational/product validation evidence. It is explicitly **not**: old-result re-evaluation, frozen-input recomputation, development regression, Final Gold evaluation, Candidate 3 tuning, or a replacement for the frozen Alpha (124/150=82.67%) or polarity (123/141=87.23%) validation results. Written before any `POST /api/research` call is made.

| Field | Value |
|---|---|
| Branch | `comqutor-structure-layer` |
| HEAD | `7a9aefa5c7b5c820515447c6289aeef80eac9bdc` |
| Candidate 3 classifier hash | `d53b2d7511f4c4a8089db746d09e4c79cb38f22597dac6459920ca3deac1171d` (`week2.alpha_classifier.v6`) |
| Candidate 3 batch hash | `a03c8f673ffd387a866bc8dd585c4c96cf5464b80a50cb6e4c3fc5f894f68379` |
| Tickers | NVDA, QQQ |

## Current Rule Baseline

`docs/audit_artifacts/v0_2_john_frozen_gold_baseline.yaml` (unchanged). QQQ frozen main-conflict allow-list: `[A001__A501, A003__A501, A304__A601]`. `A301__A304` is not on the allow-list; `RULE_CHANGE_RECOMMENDATION` not adopted — carried, unchanged.

## Workflow

1. **Launcher:** `scripts/start_live_comqutor.sh` — the one permanent live-research launcher. Exports `COMQUTOR_REAL_TRADINGAGENTS_ENABLED=true` and `COMQUTOR_WEEK2_LLM_ENABLED=true` in-process (never persisted to `.env`), runs a same-process preflight, then starts the real production API server.
2. **Trigger:** `POST /api/research {"ticker": "<TICKER>"}` — async; returns `run_id` immediately, execution happens in the background job manager.
3. **Polling:** `GET /api/research/{run_id}/status` until a terminal status.
4. **Inspection:** `GET /api/research/{run_id}`, `/graph`, `/conflicts`, `/evidence-stances`, `/artifacts`, `/agent-outputs`, plus direct filesystem inspection of `outputs/runs/{run_id}/`.
5. **Analysis date:** server default (today's actual date) — not pinned, guaranteeing no same-fingerprint cache reuse from a prior day.
6. **Analysts:** server default (all).
7. **`force_refresh`:** not set — unnecessary since today's date already differs from every historical run.

## Provider / Model Configuration

- Research profile: `comqutor_deepseek_default_v1` (`get_active_research_profile()` default) — provider `deepseek`, model `deepseek-v4-flash`, for the TradingAgents research agents.
- The Week2LLMGateway semantic path (structured_adapter, alpha_classifier/batch, evidence_stance_classifier, structure_extractor) uses whatever the running server process resolves — historically `anthropic`/`claude-sonnet-4-6`, per the Day 4B Fresh E2E precedent. Not independently overridden here.

## Timeout / Retry Policy

Production defaults, unmodified — identical to the Day 4B Fresh E2E precedent.

## Upstream Services To Be Invoked

- Real market/news/fundamentals/sentiment data providers via TradingAgents.
- DeepSeek LLM (TradingAgents agents: market/news/fundamentals/sentiment analysts, bull/bear researchers, risk analysts, trader, portfolio manager).
- Week2LLMGateway semantic Provider calls.

## Commitments

- No tuning of Candidate 3 after results.
- No acceptance-rule changes after results.
- No output inspection or cherry-picking before this plan was frozen.

**Status: `PLAN_FROZEN_BEFORE_EXECUTION`.**
