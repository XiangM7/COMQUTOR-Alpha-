# Alpha Memory — Step 1: Stable φ Identity + Cross-Run History Reader

SHADOW ONLY. **Provider calls: 0. TradingAgents calls: 0. No fresh ticker research. No commit, no push.**

## φ identity formula

```
phi_id = sha256(json_canonical({
  identity_version: "alpha_memory.phi.v1",
  ticker,                 # Product Decision 2: ticker-scoped
  alpha_id,
  taxonomy_version, taxonomy_sha256,   # from THIS run's own vocabulary snapshot
  chain_edges: sorted[(source, edge_type, target), ...]
}))
```

No Python `hash()`, no timestamps, no UUIDs — `hashlib.sha256` over a `sort_keys=True` JSON canonicalization. Deterministic across processes.

## Canonical chain boundary rule

For one `(ticker, alpha_id)`, the chain is the **set** of `(source, edge_type, target)` triples among that run's `structure_graph.json` edges whose existing `alpha_ids` field already includes this alpha — reused verbatim, never re-derived. **Not a single linear path**: the persisted graph doesn't disambiguate one canonical path when an alpha's edges branch or span multiple components, and picking one would require an invented tie-break rule. This is the narrowest unit the existing data actually supports.

**Known, honestly-reported limitation**: two runs whose edges represent the same causal idea but decompose differently (an extra intermediate node in one run's extraction) get different φ ids. Confirmed empirically — this session's two real NVDA runs share **zero** φ ids despite both being genuine NVDA research, because independent LLM extraction produced different literal edges. This is exact-match-only working as specified, not a bug, but it does mean real-world recurrence will often be under-recognized in this v1.

## Cross-run reader

Filesystem-based directory scan under `output_root` (no DB migration — every needed fact is already persisted). Excludes the current run, filters by ticker, recomputes φ structures fresh per candidate run (never caches/persists), and reports `prior_run_ids`/`first_seen`/`last_seen` from real `metadata.json` timestamps only — never fabricated.

## What was reused

`structure_graph.json`'s existing `edges[].alpha_ids` linkage (unchanged); each run's own `tradingagents_comqutor_vocabulary_snapshot.json` for taxonomy authority (never the live worktree taxonomy); `run_audit.json`'s existing additive-section convention; this codebase's established frozen-version-string pattern.

## Files changed

- **New**: `comqutor_alpha/memory/__init__.py`, `phi_identity.py`, `history_reader.py`
- **Modified**: `comqutor_alpha/api/routes_research.py` — new imports, new `_alpha_memory_section()` helper, one new key (`alpha_memory`) added to `build_run_audit_payload`'s existing return dict. Nothing existing removed or altered.
- **New tests**: `tests/test_alpha_memory_phi_identity.py` (12), `tests/test_alpha_memory_history_reader.py` (9)
- **Modified tests**: `tests/test_run_audit_v2.py` (+3)

**DB migration: NO.**

## Proof

- Same structure, same ticker, same alpha, two runs → **identical** φ id (test + real fixture).
- Different ticker / different alpha / changed chain / taxonomy-version mismatch → **all** produce different φ ids (unit + integration tests).
- `comqutor_alpha/memory/*` is **never imported** by `activation_scorer_v2.py`/`alpha_level_classifier.py`/`conflict_detector.py`/`conflict_admissibility.py` (AST-verified, same pattern as the existing evidence-stance architectural guard).
- `activation_summary`/`conflict_summary` values are **byte-identical** with the new `alpha_memory` section present, verified against the same fixture the pre-existing tests already assert on.
- Full B1/B2/B4/Conflict/Activation/Evidence-Stance sweep (422 tests) re-run clean; only the same 13 pre-existing, already-documented `evidence_review_v2.json` schema-stripping failures remain, unrelated and predating this step.
- `activation_modulation_applied` is a hardcoded `False` Python literal, never computed.

## Remaining Product decisions

Per-factor ticker-scoping consistency for the other 109 canonical factors; how (or whether) to address the chain-boundary/extraction-variance limitation; whether φ ids should ever be durably persisted; every lifecycle-event decision from the prior Phase 2 spec (untouched, as instructed).

## Explicitly not implemented (per instruction)

Invalidation detection/thresholds, expired/failed logic, non-execution logic, reason-code semantics, decay, reinforcement, memory weights, activation modifiers, historical gating, human-review feedback, fuzzy φ matching, cross-ticker φ merging.

**Provider calls: 0. TradingAgents calls: 0.**
