# ADR-002 — TradingAgents Boundary

- **Status:** `ACCEPTED_FOR_FUTURE_IMPLEMENTATION`
- **Current implementation:** `CURRENT_CODE_DIVERGES`
- **Runtime change:** `RUNTIME_CHANGE_DEFERRED`
- **Decision classification:** `APPROVED_PROJECT_DECISION`

## Context

Development Plan v1.0 assigns L1 Data Collection and L2 Agent Analysis to the TradingAgents fork “as-is,” places structure computing in `comqutor_alpha/`, and permits only minimal TradingAgents modifications for output-capture hooks.

Two current mechanisms must be distinguished:

| Mechanism | Classification | Current behavior |
| --- | --- | --- |
| `comqutor_alpha/adapters/tradingagents_output_writer.py` | `CURRENT_IMPLEMENTATION`; passive capture | Reads final state/raw outputs after generation and writes COMQUTOR artifacts. It does not request additional agent semantics. |
| `comqutor_alpha/llm/canonical_prompt_injection.py` | `CURRENT_IMPLEMENTATION`; active modification | Runtime-monkeypatches prompt-builder references so 12 native agents are asked to append a `COMQUTOR_CANONICAL_RELATIONS` block. |

The prompt injection adds no separate LLM call and changes no file under `tradingagents/` on disk. It nevertheless changes the effective prompts and expected outputs, so it diverges from the behavioral substance of “as-is” and “output capture hooks.”

## Decision

The target boundary is:

- TradingAgents continues to own L1 Data Collection.
- TradingAgents continues to own L2 Agent Analysis.
- Upstream/native prompt and output behavior remains as-is.
- COMQUTOR may passively capture `final_state` and raw outputs.
- COMQUTOR must not require native agents to emit a dedicated canonical-relation block.
- All COMQUTOR structure computation belongs in `comqutor_alpha/` after passive capture.
- Canonical prompt injection is not approved as future production semantic authority.

## Deferred Migration Contract

Phase 0.5 does not disable, delete, edit, or gate `comqutor_alpha/llm/canonical_prompt_injection.py` and does not change its call sites. The current divergence is recorded, not repaired.

Before a later disablement:

1. Measure how canonical-block edges affect graph nodes/edges, Activation, and Conflict on fixed source runs.
2. Establish a no-injection COMQUTOR extractor baseline.
3. Define a production feature flag outside Phase 0.5.
4. Provide a staged rollout, observable comparison, rollback trigger, and rollback procedure.
5. Preserve source-run and semantic-decision lineage across both variants.

No baseline-free removal is permitted. Actual runtime change belongs to a separately approved migration phase.

## Consequences

- Passive output capture is the only approved target integration mechanism.
- Current canonical edges remain available in current production behavior until the later migration gate is satisfied.
- The lack of an extra Provider call does not make active prompt modification a passive hook.
- This ADR does not represent the divergence as resolved.
