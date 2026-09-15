# φ Identity Stability Audit — Real Cross-Run Data

Read-only analysis. **No implementation changed. Provider calls: 0. TradingAgents calls: 0.**

## Real run pairs analyzed

- **NVDA**: `2f8ee897` vs `c9abf687` (the two runs from Step 1)
- **MSFT**: `07ddc074` vs `6cd2566d` (additional healthy pair, semantic health PASS)

## Stability by granularity (Jaccard overlap)

| Granularity | NVDA | MSFT | Verdict |
|---|---|---|---|
| **Node** | 0.846 | 0.769 | Highly stable, but no causal direction/Alpha attribution |
| **Edge (source,type,target), ticker-wide** | 0.263 | 0.125 | Moderate — genuine recurring edges exist |
| **Per-Alpha whole edge SET (Step 1's current unit)** | 0.0 (0/6 alphas) | 0.0 (0/8 alphas) | **Zero, confirmed structural** |
| **2-edge motif** | 0.0 | 0.0 | Worse than edge-level — rare even within one run |
| **3-edge motif/path** | 0.0 | 0.0 | Same |
| **Connected component** | 1/14 comparisons | 0/14 comparisons | No better than edge-level, less specific |

**0 of 14 alpha-pairs, across both ticker pairs, produced an identical whole edge set.** Step 1's zero-overlap finding is confirmed structural, not a fluke of the original two NVDA runs.

## Why the two real NVDA runs shared zero φ IDs

Three compounding causes, all confirmed with concrete examples:

1. **Edge inventory changes run to run** — different real claims get extracted each day (union of 19 edges vs. 14+10 individually for NVDA).
2. **edge_type disagreement on the same node pair** — e.g. `ai_capex→gpu_demand` classified `causal` in one run, `supportive` in the other. A real but secondary contributor (ignoring type raises NVDA overlap from 0.26 to only 0.40).
3. **Alpha-attribution instability** — the *identical* literal edge `(ai_capex, causal, gpu_demand)` was linked to `{A101, A103}` in one run but only `{A101}` in the other. This is independent of edge content changing, and it alone is enough to break a whole-set match even when the edge itself is byte-identical.

Requiring an entire per-alpha SET to match amplifies any single one of these (typically only 1–5 edges per alpha) into total non-recognition.

## Node-ID investigation

Node overlap (0.77–0.85) is 3–6× higher than typed-edge overlap and dramatically higher than per-alpha set overlap (always 0). Node identity is necessary infrastructure for edge/chain identity (edges are literally source/target node pairs) but **not sufficient by itself** — no causal direction, no Alpha attribution. The Revenue-Growth-only ticker-scoping inconsistency found in Step 0 has **no practical effect** on this audit's measurements, because Step 1 already scopes ticker as an explicit top-level hashed field, independent of node-id scoping — confirmed correct: both NVDA and MSFT graphs contain an identical, unscoped `ai_capex` node, and without Step 1's own ticker field these would incorrectly collide. Node IDs should **not** change.

## Recommendation: **E — HIERARCHICAL_PHI**

Edge-level (`ticker + alpha_id + source + edge_type + target + taxonomy_version`) as the atomic, durable matching unit; the current whole-alpha edge set retained only as a coarser aggregate/display roll-up, never as the primary match. **Motif-level is explicitly excluded from v2** — it measured *worse* than edge-level (rarer within a single run, zero cross-run overlap in every case found), so adding it would make the problem worse, not better.

This is additive to Step 1: `phi_identity.py`'s existing hashing approach applies unchanged, just per-edge instead of per-set.

## Should one Alpha produce one φ token, or many?

**Many.** Every alpha examined has 1–5 distinct linked edges, and different ones recur independently across runs. Forcing one φ per Alpha (today's design) measured 0% recognition; allowing multiple φ tokens per Alpha (one per edge) is what makes recognition possible at all. The Plan's own language is plural — "match recurring causal **chains**" — consistent with this, not contradicted by it.

## Development Plan alignment

The Plan's worked example (`φ-001 = AI demand → GPU shortage → NVDA benefits`) is itself a chain, textually favoring individual causal-chain identities over one whole-Alpha-graph identity. But exact chain-level matching, as literally described, measured **zero** cross-run stability today. The recommended edge-level unit is honestly framed as the Plan's own "chain" concept truncated to its smallest unambiguous, currently-stable fragment (a chain of length 1) — not a redefinition of the Plan's intent, an honest acknowledgment of what real extraction variance currently allows without fuzzy matching.

## Product decisions still required

Whether to formally adopt edge-level as primary (this audit recommends, doesn't implement); whether an explicit, Product-approved edge_type equivalence table should ever exist (a controlled, non-fuzzy relaxation — still a new decision); whether to keep pursuing motif-level as a future stretch goal or deprioritize it; whether alpha-attribution instability should become its own tracked/visible signal. All of Step 1's original open decisions remain open.

## Files inspected

`structure_graph.json` for all four real runs; `comqutor_alpha/memory/phi_identity.py`/`history_reader.py` (read-only, unchanged); `comqutor_alpha/regression/semantic_execution_health.py` (used read-only to pick a healthy MSFT pair).

## Artifacts created

`docs/audit_artifacts/alpha_memory_phi_stability_audit.json`, this file.

**Provider calls: 0. TradingAgents calls: 0.**
