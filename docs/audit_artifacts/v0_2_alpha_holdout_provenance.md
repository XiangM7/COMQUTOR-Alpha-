# v0.2 Alpha Holdout Provenance Inventory

Full detail in `v0_2_alpha_holdout_provenance.json`. Chronology confirmed directly by filesystem mtime (not assumed): H1 → H2 → H3 → H3-pure-llm-dev → H4 → H5, all created 2026-08-20/21. **No holdout set exists with a later creation date than Holdout #5** — confirmed by direct inspection.

| Holdout | Samples | Era | Already Inspected? | Influenced a Code/Prompt Change? | Eligible as Final Independent? |
|---|---:|---|---|---|---|
| #1 (100) | 100 | Pre-Pure-LLM-migration (deterministic hard gate, `decision=defer`) | Yes — full "Final QA" report already published | Fully consumed as its own era's closure milestone | **No** — architecturally obsolete + fully closed |
| #2 (141) | 141 | Pre-Pure-LLM-migration | Yes — its precomputed Alpha/Polarity numbers were already read and cited in this session's own Day 4 Phase D artifact | Same as above | **No** — obsolete + already directly cited this session |
| #3 (152) | 152 | Transitional | Yes | **Yes** — its offshoot (`item2_holdout3_pure_llm_dev_comparison.csv`) directly compares pre/post the `decision=defer→select/none` migration | **No** — directly used to validate a prior migration |
| #4 (200) | 200 | Current (Pure-LLM) | Yes | **Yes** — its 52 pre-remediation errors were inspected to design Day 4B Candidate 1 (rejected) | **No** — `DEVELOPMENT_AFTER_FIRST_INSPECTION` |
| #5 (200) | 200 | Current (Pure-LLM) | Yes | **Yes** — its 43 failures drove the Day 3 fix and Candidate 1's design | **No** — `DEVELOPMENT` |

Zero sample-ID overlap confirmed pairwise across all five sets (each set's own construction excluded all prior claim_ids).

## Classification (per Section 5)

- **Holdout #5: `DEVELOPMENT`**
- **Holdout #4: `DEVELOPMENT_AFTER_FIRST_INSPECTION`**
- **Holdout #1, #2, #3: already-closed/obsolete development artifacts — not reserved candidates** (pre-date the current Pure-LLM architecture and/or were already directly inspected this session or a prior one)
- **No holdout classified `RESERVED_FINAL_INDEPENDENT_VALIDATION`**

## Conclusion

**`NO_UNTOUCHED_INDEPENDENT_ALPHA_HOLDOUT_AVAILABLE`.**

Every existing frozen Alpha holdout set has either already been inspected/cited within this engagement, directly informed a prior code or prompt change, or belongs to an architecturally superseded generation of the system. None can honestly serve as a final, untouched independent validation set for Candidate 2.
