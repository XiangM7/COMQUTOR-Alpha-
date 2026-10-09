# The conflict-pair defect on identical inputs: Round 23 engine vs Round 24 engine

Provider calls 0; network attempts 0. Inputs are synthetic (real detector + real B2 on hand-built activation entries and claims) except case D, a labelled controlled modification.

| Case | Fixture | What the run recorded | Round 23 | Round 24 |
|---|---|---|---|---|
| control: every B2 condition met (2 ticker-specific facts per side, scores 80/80, both active) | real detector + real B2 | outcome admitted; B2 admitted [], supports [2, 2], ticker-specific [2, 2], scores [80.0, 80.0] | **pass** | **pass** (admitted) |
| A1: Alpha A never identified (no activation entry), its two supporting claims still in alpha_matches | real detector + real B2 | outcome rejected; no B2 block; detector reasons ['MISSING_LEFT_ACTIVATION']; qualifying claims in its own evidence audit {'alpha_a': 2, 'alpha_b': 2} | **not_applicable** | **not_evaluable** (not_evaluated_before_b2) |
| A2: Alpha A present but capped_active (not an official detected level) | real detector + real B2 | outcome suppressed; no B2 block; detector reasons ['BELOW_ACTIVATION_THRESHOLD']; qualifying claims in its own evidence audit {'alpha_a': 2, 'alpha_b': 2} | **not_applicable** | **not_evaluable** (not_evaluated_before_b2) |
| B: exactly ONE supporting fact per side (scores 80/80, ticker-specific) | real detector + real B2 | outcome suppressed; B2 candidate ['INSUFFICIENT_BULL_SUPPORTING_EVIDENCE', 'INSUFFICIENT_BEAR_SUPPORTING_EVIDENCE'], supports [1, 1], ticker-specific [1, 1], scores [80.0, 80.0] | **fail** | **not_applicable** (b2_rejected) |
| B': two facts per side, none of A's ticker-specific | real detector + real B2 | outcome suppressed; B2 candidate ['NO_BULL_TICKER_SPECIFIC_SUPPORT'], supports [2, 2], ticker-specific [0, 2], scores [80.0, 80.0] | **fail** | **not_applicable** (b2_rejected) |
| B'': two facts per side, Alpha A score 40 (< 50) | real detector + real B2 | outcome suppressed; B2 candidate ['BULL_SCORE_BELOW_THRESHOLD'], supports [2, 2], ticker-specific [2, 2], scores [40.0, 80.0] | **fail** | **not_applicable** (b2_rejected) |
| C: no supporting evidence at all, both Alphas active | real detector + real B2 | outcome suppressed; no B2 block; detector reasons ['MISSING_LEFT_EVIDENCE', 'MISSING_RIGHT_EVIDENCE', 'ZERO_EVIDENCE_STRENGTH']; qualifying claims in its own evidence audit {'alpha_a': 0, 'alpha_b': 0} | **not_applicable** | **not_applicable** (rejected_before_b2_no_qualifying_evidence) |
| D: the control record hand-edited to 'candidate, no reason' (B2 cannot produce it) | CONTROLLED MODIFICATION | outcome suppressed; B2 candidate [], supports [2, 2], ticker-specific [2, 2], scores [80.0, 80.0] | **fail** | **fail** (b2_not_admitted_without_reason) |

Reading: in Round 23 the FAIL fell on B2's correct rejections (B, B', B'') and the cases where the pair was never judged (A1, A2) were waved through as `not_applicable`; case D, the only record that is a real omission, got the same FAIL as the correct rejections. In Round 24 each situation has its own result.

