# v0.2 Alpha FINAL Gold — Freeze Manifest

**Status: `FINAL_GOLD_FROZEN`**

| Field | Value |
|---|---|
| Final Gold path | `docs/audit_artifacts/v0_2_alpha_final_gold_v1.json` |
| Final Gold SHA256 | `a3c402ce391cfba1bd49d3d84a352e222e2775118f24b9ebf2a003183e2392de` |
| Sample count | 150 |
| Adjudicator mode | `INDEPENDENT_EXTERNAL_LLM_ADJUDICATION` |
| System predictions seen during Gold adjudication | NO |
| Candidate 3 outputs seen during Gold adjudication | NO |
| Used for tuning | NO |

## Label Distribution

NONE=116, A301=9, A304=8, A101=6, A601=5, A201=4, A103=2, A001=0, A003=0, A102=0, A501=0 (sum=150)

## Confidence Distribution

high=120, medium=30, low=0 (sum=150)

## Full Replacement Lineage

| Stage | Value |
|---|---:|
| Original reserve pool | 50 |
| Development replacements consumed | 18 |
| Final round-1 draw consumed | 20 |
| Final round-2 draw consumed | 4 |
| Final round-3 draw consumed | 2 |
| **Total reserve consumed** | **44** |
| **Untouched reserve remaining** | **6** |
| First-pass accepted | 130 |
| Round-1 accepted | 16 |
| Round-2 accepted | 2 |
| Round-3 accepted | 2 |
| **Total accepted** | **150** |
| **Unresolved slots** | **0** |

Replacement log status: `FINAL_REPLACEMENT_CHAIN_FULLY_RESOLVED` (`docs/audit_artifacts/v0_2_alpha_final_replacement_log.json`).

## Reference Hashes

| Item | SHA256 |
|---|---|
| Original final membership manifest | `a7c84445247f0ce0fdf187e6e73d62c04eb82e64557c40a98704a49bcd4bf70c` |
| Candidate 3 classifier prompt | `d53b2d7511f4c4a8089db746d09e4c79cb38f22597dac6459920ca3deac1171d` |
| Candidate 3 batch prompt | `a03c8f673ffd387a866bc8dd585c4c96cf5464b80a50cb6e4c3fc5f894f68379` |

## Worktree at Freeze Time

- Branch: `comqutor-structure-layer`
- HEAD: `7a9aefa5c7b5c820515447c6289aeef80eac9bdc`
- Tracked-file diff: `structured_output_adapter.py` (pre-existing Day 3 fix), `week2_llm.py` (Candidate 3), `test_week2_llm_semantic_runtime_integration.py` (Candidate 3 test-compat update) — unchanged since Day 4G/4H.

Candidate 3 final evaluations: **0**. Provider final evaluations: **0**.

## Next Step

The next, separate task performs the one-shot, final independent validation: run frozen Candidate 3 against this frozen Final Gold, exactly once, via real Provider calls. This Gold file and Candidate 3 must not be modified before then.
