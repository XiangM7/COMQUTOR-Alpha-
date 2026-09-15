# Atomic Edge φ Identity — Field Ablation Audit

Read-only. **No implementation changed. Provider calls: 0. TradingAgents calls: 0.**

## Overlap by model

| Model | Fields | NVDA Jaccard | MSFT Jaccard |
|---|---|---|---|
| A | ticker+alpha+source+type+target (full) | 0.105 (2/19) | 0.0 (0/13, degenerate*) |
| B | ticker+alpha+source+target | 0.25 (4/16) | 0.0 (0/12, degenerate*) |
| C | ticker+source+type+target | 0.263 (5/19) | 0.125 (2/16) |
| D | ticker+source+target | 0.4 (6/15) | 0.214 (3/14) |

*MSFT run_a (`07ddc074`) has only 1 edge with any `alpha_ids` at all — an independent data-quality observation, not introduced by this analysis; it makes A/B degenerate for that pair while C/D remain fully informative.

## Recovery

- **Removing alpha_id** (A→C): NVDA +3 (2→5), MSFT +2 (0→2)
- **Removing edge_type** (A→B): NVDA +2 (2→4), MSFT +0 (degenerate)

**Removing alpha_id recovers more matches than removing edge_type** — alpha-attribution instability is at least as large a fragmentation source as edge_type disagreement.

## Collision findings — dropping alpha_id

**Within a single run**, the same `(source, target)` pair is already, intentionally, linked to more than one Alpha simultaneously (e.g. NVDA `ai_capex→gpu_demand` → `{A101, A103}` in one run alone; MSFT run_b has 4 such cases). This is existing, deliberate multi-relevance design, not noise — dropping `alpha_id` would silently merge "this edge as A101's evidence" with "this edge as A103's evidence." **Classified CASE_2 (genuinely distinct)**.

**Cross-run**, of 7 shared-edge alpha comparisons: 5 are SUBSET relationships (one run simply found fewer/no alpha links — plausible attribution variance), 1 is a clean match, and **1 is fully DISJOINT** (NVDA `ai_infrastructure→nvda_revenue_growth`: A101 vs A103) — reported raw, unresolved, per instruction not to guess.

## Collision findings — dropping edge_type

Of 9 cross-run shared-pair comparisons: 4 exact matches, 4 (all NVDA) show overlapping/adjacent variance plausibly explained by extraction wording (causal/supportive intermixing), and **1 is flagged as potentially genuine** — MSFT `ai_capex→msft_revenue_growth`: `causal` vs `conflicting`. These are not adjacent readings of the same idea; one says X drives Y, the other says X works against Y. Reported as-is, not resolved by intuition.

## Does alpha_id belong in durable identity?

**Yes.** The within-run multi-alpha evidence shows real, intentional distinctions already exist in production data. Cross-run instability (mostly SUBSET, one DISJOINT case) is real but should be *tracked as its own signal*, not fixed by deleting the field.

## Does edge_type belong in durable identity?

**Yes**, for the same reason — the one causal-vs-conflicting case is different in *kind*, not degree, from the mostly-benign causal/supportive variance. A mixed, uncertain population must not be resolved by dropping the field wholesale; if desired later, a Product-approved, explicit (non-fuzzy) equivalence table for specific tolerated pairs is the right lever, not blanket removal.

## Recommended exact model: **EDGE_ID_A_ALPHA_AND_TYPE**

The full field set — `ticker + alpha_id + source + edge_type + target + identity_version + taxonomy_version + taxonomy_sha256`, hashed exactly as Step 1's existing `_stable_digest` already does, applied **per edge** instead of per whole-set. Models B/C/D buy higher overlap only by discarding fields whose collision analysis shows real, non-noise semantic content. The task's own instruction — don't optimize for overlap alone — is decisive: Model A's lower match count is the honest, conservative reflection of real extraction variance, not a defect.

This is a minimal, additive refinement of Step 1 — same field composition, finer granularity only.

## Recommended hierarchy

- **Level 1 (atomic, durable)**: Model A per edge.
- **Level 2 (aggregate only)**: Step 1's current whole-alpha edge set, unchanged, demoted to a coarse display/audit grouping — never the primary matching signal.
- **Motif level**: **Deferred**, reaffirming Step 1.5 — no new evidence here changes that.

## Development Plan alignment

The Plan's own worked example (`φ-001 = AI demand → GPU shortage → NVDA benefits`) is already thesis-specific by construction (its terminal step is a directional, Alpha-relevant conclusion) — consistent with keeping Alpha association *in* structure identity, not treating it as a removable per-run tag.

## Product decisions required

Formal adoption of the recommended model; whether alpha-attribution and edge_type instability should become explicitly tracked data-quality signals; whether a Product-approved edge_type equivalence table should ever exist; domain review of the two flagged raw cases (the DISJOINT alpha case and the causal-vs-conflicting edge_type case) as possible independent Alpha Mapper/extraction quality questions, separate from Alpha Memory itself; all prior open items from Step 1 and Step 1.5 remain open.

## Files inspected

`structure_graph.json` for all four real runs; `comqutor_alpha/memory/phi_identity.py` (read-only); `alpha_memory_phi_stability_audit.json` (prior step, read-only).

**Provider calls: 0. TradingAgents calls: 0.**
