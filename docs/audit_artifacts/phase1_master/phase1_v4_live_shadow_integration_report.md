# Phase 1 v4 Live Shadow Integration Report

Status: `LIVE_SHADOW_INTEGRATION=PASS`

Production authority remains `LEGACY_ADAPTER`. The v4 candidate is opt-in only (`COMQUTOR_STRUCTURED_ADAPTER_MODE=shadow`); its accepted records, validation results, and Legacy comparison are persisted as three separate sidecars and never enter Mapper, Extractor, Graph, Activation, or Conflict.

## Integration boundary

The hook is in `comqutor_alpha.api.routes_research._run_week1_week2_artifact_pipeline`, immediately after the Legacy Adapter has successfully written `structured_agent_outputs.json` and before authoritative persistence and downstream processing. The hook calls the additive `structured_output_live_shadow` orchestrator. No TradingAgents code or prompt was modified.

The run mode is resolved once. The later Product Owner instruction in this task says default behavior must be Legacy-only, which conflicts with the older pre-registered Stage E text saying Shadow should become the default once wired. The later explicit decision takes precedence, so the actual default is `legacy` (`SHADOW_DEFAULT=OFF`). A premature `primary` request safely resolves to Legacy with `STRUCTURED_ADAPTER_PRIMARY_NOT_AUTHORIZED`.

When explicitly enabled, Shadow uses the existing v4 provider/parser/validator seam. Its semantic recorder and manifest use the existing runtime format in a separate run-local `structured_adapter_shadow_runtime/` directory, preventing call-sequence collision with canonical Week2 semantic artifacts. No Provider was called during this task.

## Isolation and replay evidence

The integration test uses the frozen NVDA TradingAgents fixture at `outputs/runs/0e044e37-862c-43be-871c-31012cd660e7/raw_agent_outputs.json`, covering fundamental, news, sentiment, and technical/market reports. The external Provider is replaced by a deterministic local executor while the real v4 parser, exact EvidenceQuoteResolver, schema validation, production pipeline, and sidecar persistence remain active.

All eight required cases pass: disabled, accepted, malformed JSON, unresolved Evidence, timeout, identity mismatch, Provider-zero exact replay, and authoritative downstream isolation. Legacy-only and Legacy+Shadow canonical content is equivalent across the API response, Structured Claims, Alpha Mapper, Structure Extractor, Graph, Activation, and Conflict. Independent-run wall-clock timestamp fields are excluded from that canonical equivalence comparison. Shadow claim IDs appear in none of those authoritative downstream artifacts.

Exact replay reloads the captured raw report, Legacy output, Shadow output, validation, and comparison sidecars; it revalidates accepted bundles and reproduces Shadow records and comparison results, including source and artifact hash bindings. It makes zero Provider calls and does not reinterpret or regenerate Claims.

## Verification

- `tests/structured_output_shadow`: 397 passed.
- `tests/llm_runtime tests/replay`: 123 passed.
- Shared live/API guarded regression: 66 passed, one pre-existing Starlette deprecation warning.
- Phase 1 Master verifier: 22/22 passed.
- Ruff: passed.
- `git diff --check`: passed.

One attempted all-in-one pytest collection hit the repository's existing global `conftest` module-name collision between `tests/replay` and `tests/structured_output_shadow`; no assertion ran or failed in that attempt. Running the repository's canonical suites as separate pytest processes produced the 586 non-overlapping passing tests above.

## Outcome

`READY_FOR_LIVE_SHADOW_CANARY=YES`, but the canary was not run. Production cutover was not run. No §5.2 work was started. External Provider calls: 0. Subagents: 0.
