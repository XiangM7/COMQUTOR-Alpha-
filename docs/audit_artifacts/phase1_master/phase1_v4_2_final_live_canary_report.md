# Phase 1 v4.2 Final Live Canary Report

## Outcome

`FINAL_V4_2_CANARY=PASS`. All four pre-registered slots (fundamental, news,
sentiment, technical — the same NVDA source reports used by the original v4
Canary and the failed v4.1 Re-Canary) passed on exactly one real Provider
attempt each, zero retries, zero subagents. Candidate binding was never
active, never requested, and never exercised.

## Slot results

| Slot | Family | Transport | Claims | Evidence | Unique | Duplicate (earliest-occurrence) | Zero-match | Exact provenance | Identity | Legacy isolation | Exact replay | Slot status |
|---:|---|---|---:|---:|---:|---:|---:|---|---|---|---|---|
| 1 | fundamental | SUCCESS | 32 | 37 | 37 | 0 | 0 | PASS | PASS | PASS | PASS | **PASS** |
| 2 | news | SUCCESS | 24 | 25 | 25 | 0 | 0 | PASS | PASS | PASS | PASS | **PASS** |
| 3 | sentiment | SUCCESS | 34 | 35 | 35 | 0 | 0 | PASS | PASS | PASS | PASS | **PASS** |
| 4 | technical | SUCCESS | 28 | 34 | 33 | 1 | 0 | PASS | PASS | PASS | PASS | **PASS** |
| **Total** | | | **118** | **131** | **130** | **1** | **0** | | | | | **4/4** |

The `technical` slot — the exact family whose duplicate quote originally
motivated v4.1 — produced one duplicate exact-match Evidence quote in this
real run and admitted it via `DUPLICATE_ACCEPTED_EARLIEST_OCCURRENCE`,
correctly and cleanly, with zero candidate involvement of any kind.

## Candidate binding

`candidate_binding_active=false` for every slot. No response from the
Provider in any of the four calls contained a `candidate_id`/`candidate_ids`
field or any other unapproved wire field (`candidate_fields_seen_in_any_response=false`
across all four). The v4.2 wire schema does not offer this field, and the
Provider was never asked for one.

## Safety and isolation

- `ambiguous_or_unresolved_evidence_admitted = 0`
- `identity_failure_admitted = 0`
- `authoritative_artifacts_equal = true` (Legacy-only run vs. Shadow-enabled
  run produced byte-identical `structured_agent_outputs.json`,
  `alpha_matches.json`, `extracted_structures.json`, `structure_graph.json`,
  `alpha_activations.json`, `conflicts.json`)
- `api_response_equal = true` (the research API response was unaffected by
  Shadow running in parallel)
- `shadow_output_reached_authoritative_downstream = false` (Shadow claim IDs
  never appear anywhere in the authoritative downstream artifacts)
- Exact Replay: `PASS`, 4/4 accepted reports reproduced, 0 Provider calls
- Semantic manifest verification: `valid=true`
- Source artifact (`outputs/runs/0e044e37-.../raw_agent_outputs.json`)
  unchanged before/after (hash-verified)

## Budget

`LOGICAL_CALLS=4/4`, `REAL_PROVIDER_ATTEMPTS=4/4`, `RETRIES=0`,
`SUBAGENTS=0`, `POST_CANARY_PROVIDER_CALLS=0`. Cumulative Phase 1
accounting after this run: 103 logical calls (at the raised cap, exactly),
110 Provider attempts (within the unchanged 130 cap).

## Production cutover — BLOCKED, not by this Canary

`FINAL_V4_2_CANARY=PASS` unconditionally authorizes cutover per this task's
own rule. However, executing it exposed a real, concrete implementation
gap, not a Canary defect:

**`MODE_PRIMARY` has no execution behavior anywhere in the codebase.**
`resolve_structured_adapter_mode()` in `structured_output_live_shadow.py`
is the *only* place `MODE_PRIMARY` is referenced besides its own enum
definition — and that one reference immediately degrades any `"primary"`
request to `effective_mode=MODE_LEGACY, shadow_enabled=False` with reason
code `STRUCTURED_ADAPTER_PRIMARY_NOT_AUTHORIZED`. No code anywhere in
`routes_research.py` or `structured_output_live_shadow.py` branches on
`effective_mode == "primary"` to make the Shadow-validated bundle become
the actual authoritative `structured_agent_outputs.json` (or otherwise
change what downstream Mapper/Extractor/Graph/Activation/Conflict/API
consume). Removing the degrade block alone would not activate anything —
without it, an unrecognized `"primary"` string would simply fall through
to the function's `STRUCTURED_ADAPTER_MODE_INVALID` catch-all, which is
worse, not better.

In short: only Stage E's parallel, non-authoritative Shadow-sidecar path
was ever built. Stage G's real primary-mode routing — the actual mechanism
"cutover" would flip — does not exist yet. This is new engineering (fail-
soft routing, a decision about what happens on a live Shadow failure at
request time, and real testing of that new path), not a configuration
change, and was not built or tested as part of this task's authorized
scope (which was the Canary itself, zero further Provider calls, and using
only the *existing* mechanism). Building and shipping it under real-money
time pressure, in the same pass as four just-completed live calls, with no
independent testing of the new path, is not something this task should do
unilaterally.

## Result

- `PRODUCTION_AUTHORITY = LEGACY_ADAPTER` (unchanged — cannot be
  meaningfully changed until primary-mode routing exists)
- `PRODUCTION_CUTOVER = BLOCKED_MECHANISM_NOT_IMPLEMENTED`
- `SECTION_5_1 = CANARY_PASSED_CUTOVER_MECHANISM_MISSING` (not `DONE`: this
  task's own completion rule requires `PRODUCTION_CUTOVER = COMPLETE`,
  which did not happen)

The deterministic v4.2 repair itself is now validated at every layer this
project has available: 99/99 real historical Evidence items replay clean
offline, and 4/4 real live Provider calls pass clean end-to-end with zero
candidate involvement. What remains is a distinct, separately-scoped
engineering task: implement real primary-mode routing (with fail-soft
fallback to Legacy on any Shadow failure, exactly as ADR-010/Stage G
already specify), then re-validate that specific mechanism -- deliberately
left for a dedicated task rather than rushed here.
