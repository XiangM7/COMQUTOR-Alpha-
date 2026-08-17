# Phase 1 §5.1 Stage G: Primary Authority Routing — Implementation Report

## Why Stage G was required

The v4.2 Final Live Canary (4/4 PASS, real live data) proved the
extraction/provenance implementation is correct, but exposed that
`MODE_PRIMARY` had no execution behavior anywhere in the codebase:
`resolve_structured_adapter_mode()` was the only reference to it besides
its own enum entry, and it unconditionally degraded any `"primary"`
request to `legacy` with reason code
`STRUCTURED_ADAPTER_PRIMARY_NOT_AUTHORIZED`. No code anywhere made a v4.2
Shadow result actually authoritative. This report records what was built
to close that gap.

## Previous (Stage-E-only) primary behavior

```
mode == "primary"  ->  StructuredAdapterModeDecision(
    requested_mode="primary", effective_mode="legacy",
    shadow_enabled=False, reason_code="STRUCTURED_ADAPTER_PRIMARY_NOT_AUTHORIZED",
)
```

Any caller requesting `primary` silently got Legacy-only behavior, with no
Shadow attempt at all.

## Actual implemented authority flow

```
mode == "legacy"   -> Legacy authoritative. Unchanged.
mode == "shadow"   -> Legacy authoritative; v4.2 runs as the existing
                       non-authoritative sidecar. Unchanged.
mode == "primary"  -> v4.2 attempted via the SAME existing Shadow
                       execution path (run_live_shadow_sidecar,
                       unmodified). select_primary_authority() then
                       decides, from that same run's already-computed
                       per-report accepted/rejected result:
                         all reports accepted -> v4.2 authoritative
                         any report rejected/unavailable/empty ->
                           Legacy authoritative (fail-soft fallback)
```

No new Provider invocation path, no second extraction pipeline, and no
change to `StructuredOutputShadowParserV4_2`/`resolve_supporting_quote_v4_2`
or any other v4.2 semantic/provenance logic. `select_primary_authority`
(new, in `structured_output_live_shadow.py`) reads only the same sidecar
files (`structured_agent_outputs_shadow.json`,
`structured_adapter_shadow_validation.json`) `run_live_shadow_sidecar`
already wrote before Stage G existed.

## Legacy behavior (unchanged)

`structured_agent_outputs.json` is written by
`save_structured_agent_outputs` exactly as before; nothing added by this
task ever touches that write for `legacy` or `shadow` mode.

## Shadow behavior (unchanged)

`run_live_shadow_sidecar` itself is untouched. It always writes the same
three sidecars regardless of `shadow` vs. `primary` mode -- Stage G's new
logic lives entirely in the caller (`_run_week1_week2_artifact_pipeline`),
which reads the sidecar's result to decide authority; the module that
computes the Shadow attempt has no awareness of "primary" at all.

## Primary success behavior

If every report this run attempted was accepted (unanimous -- the same
all-or-nothing philosophy already used at the Evidence-quote and
bundle-admission levels, not an invented threshold), `select_primary_
authority` returns the sidecar's own `records` (already produced by the
real v4.2 parser/resolver) with three fields flipped to reflect real
authority (`shadow_only: false`, `production_authority: true`,
`selected_authority: "structured_adapter.claim_extraction_shadow.v4.2"`
-- fields the original Stage-E author already anticipated needing for
exactly this purpose). The caller overwrites `structured_agent_outputs.json`
with this payload *before* it is read back and persisted to the database,
so every existing downstream consumer (Alpha Mapper persistence, the
research API response, `run_audit.json`) receives it through the
unmodified, existing interface -- confirmed by direct inspection:
`repository.persist_agent_outputs` reads only `records`; the two
Legacy-adapter-specific diagnostic blocks it doesn't share
(`metadata`, `canonical_relations`) are read elsewhere in
`routes_research.py` only through the codebase's already-established
graceful-default convention (`.get(...)` + `isinstance` + empty fallback),
so their absence produces honest zeros/empty lists, never a crash or a
fabricated value.

## Primary fallback behavior

Any of: no reports attempted, any report rejected, the sidecar output file
missing/unreadable, or empty/non-substantive records -> Legacy remains
authoritative, with an explicit `fallback_reason` code
(`STRUCTURED_ADAPTER_PRIMARY_NO_REPORTS_ATTEMPTED` /
`_REPORT_REJECTED` / `_SIDECAR_UNAVAILABLE` / `_SIDECAR_OUTPUT_UNREADABLE`
/ `_EMPTY_OR_NON_SUBSTANTIVE`). A raised exception at the Shadow execution
boundary is caught by `run_live_shadow_sidecar`'s own pre-existing
per-report exception handling (unchanged) and surfaces as that report's
rejection -- Stage G added no new exception-swallowing of its own.
`select_primary_authority` itself is called **unguarded** (no try/except)
in the pipeline, so a genuine bug in the new routing code propagates
normally rather than being absorbed into "Legacy wins" (proven by
`test_9b_a_bug_in_stage_g_routing_itself_is_not_swallowed`).

## Downstream authority proof

`test_11a`/`test_11b` prove actual dataflow, not just metadata: on primary
success, `structured_agent_outputs.json`'s `records` come from the v4.2
sidecar (118 claims from the real stored Canary result in the dedicated
integration test); on primary failure, they are byte-set-identical to an
independent Legacy-only baseline run of the same input. Every run also
gets one explicit `structured_adapter_authority_routing.json` (new
allow-listed artifact) recording `requested_mode`, `effective_mode`,
`primary_attempted`, `primary_succeeded`, `authoritative_adapter`,
`fallback_used`, `fallback_reason`, `active_protocol` -- so "which adapter
is authoritative" is never left for a downstream reader to infer.

## Production mode after this task

**Deliberately still `LEGACY_ADAPTER` by default.** The mechanism is real,
tested, and correct for an *explicitly requested* `primary` mode -- but
this task did **not** flip `resolve_structured_adapter_mode`'s hard-coded
fallback (used whenever neither an explicit mode nor the
`COMQUTOR_STRUCTURED_ADAPTER_MODE` environment variable is set) from
`"legacy"` to `"primary"`. Concrete reason, verified before touching
anything: **19 existing test files call `run_research_request` with no
explicit `structured_adapter_mode`**, relying on today's default resolving
to `legacy` (`shadow_enabled=False`, zero Shadow/Provider construction).
Flipping the shared fallback would have silently given every one of those
tests `shadow_enabled=True` by default, constructing a real Provider
gateway (`_DefaultV4ShadowExecutor`) inside tests that have never made a
Provider call and are not designed to. One existing test
(`test_shadow_default_and_explicit_legacy_are_disabled`) explicitly
asserts today's default *must* stay `legacy` -- written under a prior,
explicit product decision ("Latest product decision keeps default OFF").

This is a deployment-level activation, not a code change: setting
`COMQUTOR_STRUCTURED_ADAPTER_MODE=primary` in the actual production
environment (outside this repository, which has no visibility into or
control over that deployment configuration) activates exactly the routing
this report describes, with zero further code change required. Explicit
per-request `structured_adapter_mode="primary"` already works today,
proven by real, passing, zero-Provider tests plus the real stored Canary
data.

## Zero-Provider-call accounting

`REAL_PROVIDER_CALLS = 0` for this entire task. All 23 new Stage G tests,
all 13 pre-existing Stage E tests, and the "real stored v4.2 result"
integration test use only already-persisted data (from the real, completed
Final Live Canary) or injected offline fixtures (`LocalV4_2Executor`,
mirroring the established `LocalV4Executor`/`LocalV4_1Executor` pattern)
that exercise the real `StructuredOutputShadowParserV4_2` parsing/
resolution logic without ever constructing a real Provider gateway.

## Test results

- 23/23 new (`tests/structured_output_shadow/test_stage_g_primary_authority_routing.py`)
- 13/13 existing Stage E (`test_live_shadow_integration.py`, one test
  updated to reflect Stage G superseding its own former assertions,
  documented inline)
- 77/77 other directly-affected focused tests (v4.2 provenance, v4.1
  candidate binding/forensics, v4 provider invoker, risk-based review)
- 35/35 spot-checked, unrelated tests that call the pipeline with no
  explicit mode (confirmed still fast/zero-Provider, proving the
  deliberately-unchanged default truly protects them)
- Ruff: clean on all touched files
- `git diff --check`: clean
