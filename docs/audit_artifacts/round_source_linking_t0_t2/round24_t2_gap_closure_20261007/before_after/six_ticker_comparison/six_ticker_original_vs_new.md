# Round 23 verdict vs Round 24 verdict, ticker by ticker

| Ticker | Run | Original | New | Why the status moved (or did not) |
|---|---|---|---|---|
| NVDA | ded99ecd | needs_review | **needs_review** | left the verdict: should_detect_if_supported A101__A304; should_detect_if_supported A301__A304 ;  entered the verdict: conditional_only NVDA-GROWTH-VS-VALUATION-CONFLICT (not_evaluable); must_detect_if_evidence_present NVDA-A101-AI-GROWTH (not_evaluable); must_detect_if_evidence_present NVDA-A304-VALUATION-RISK (not_evaluable) ;  unchanged: undeclared_admitted_conflict A304__A601 |
| QQQ | 0d890564 | needs_review | **needs_review** | left the verdict: should_detect_if_supported A001__A501 ;  unchanged: undeclared_admitted_conflict A501__A601 |
| SNDK | e8e0f398 | needs_review | **pass** | left the verdict: should_detect_if_supported A301__A304 |
| MSFT | 64568bfb | needs_review | **needs_review** | entered the verdict: must_detect_if_evidence_present MSFT-A102-DIRECT-INFERENCE-TRIGGER (not_evaluable) ;  unchanged: undeclared_admitted_conflict A304__A601 |
| TSM | fc09821e | needs_review | **needs_review** | unchanged: undeclared_admitted_conflict A304__A601 |
| AMD | d5b60b8a | needs_review | **needs_review** | entered the verdict: conditional_only AMD-AI-GROWTH-VS-VALUATION (not_evaluable) ;  unchanged: undeclared_admitted_conflict A304__A601 |

## NVDA — run `ded99ecd-a186-4a90-859e-0f1a0efa43db`

**Gold contract rules executed for this ticker**

| Rule | Blocking | Evidence trigger (source / bound run → this run) | Alpha facts: identified / level (score) | Requirement met | Result | Blocks release | Reason |
|---|---|---|---|---|---|---|---|
| NVDA-A101-AI-GROWTH | yes | NOT_EVALUABLE — —; 57d7b4c4 → ded99ecd | A101: IDENTIFIED (21 claims) / candidate (48.5501) | False | not_evaluable | no | RUN_NOT_BOUND_TO_FROZEN_TRIGGER_MATRIX |
| NVDA-A304-VALUATION-RISK | yes | NOT_EVALUABLE — —; 57d7b4c4 → ded99ecd | A304: IDENTIFIED (76 claims) / dominant (71.7302) | True | not_evaluable | no | RUN_NOT_BOUND_TO_FROZEN_TRIGGER_MATRIX |
| NVDA-GROWTH-VS-VALUATION-CONFLICT | yes | NOT_EVALUABLE — —; 57d7b4c4 → ded99ecd | A101: IDENTIFIED (21 claims) / candidate (48.5501); A301: IDENTIFIED (52 claims) / dominant (74.214); A304: IDENTIFIED (76 claims) / dominant (71.7302) | — | not_evaluable | no | RUN_NOT_BOUND_TO_FROZEN_TRIGGER_MATRIX |

Contract rules of this ticker NOT executed by the entry: NVDA-A301-FUNDAMENTAL-GROWTH, NVDA-SUPPORTING-STRUCTURES.  Release: **unresolved** (blocks_release=False; blocking unresolved: ['NVDA-A101-AI-GROWTH', 'NVDA-A304-VALUATION-RISK', 'NVDA-GROWTH-VS-VALUATION-CONFLICT']).

**Conflicts: what the run did, and what B2 said about each declared pair**

Admitted: A304__A601; main: A304__A601; admitted but declared nowhere (review): A304__A601.

| Pair | Declared as | Arbitration record | Outcome / B2 status | B2 or detector reasons | Supports bull/bear | Scores bull/bear |
|---|---|---|---|---|---|---|
| A101__A304 | conditional_only | b2_rejected | suppressed / candidate | ['BULL_SCORE_BELOW_THRESHOLD'] | [4, 17] | [48.5501, 71.7302] |
| A301__A304 | conditional_only | b2_rejected | suppressed / candidate | ['NO_BULL_TICKER_SPECIFIC_SUPPORT'] | [14, 17] | [74.214, 71.7302] |

**Diagnostic findings (engine-defined; decide nothing):** A101__A304 → needs_review (B2: BULL_SCORE_BELOW_THRESHOLD); A301__A304 → needs_review (B2: NO_BULL_TICKER_SPECIFIC_SUPPORT)

**Not evaluable:** conditional_only NVDA-GROWTH-VS-VALUATION-CONFLICT; must_detect_if_evidence_present NVDA-A101-AI-GROWTH; must_detect_if_evidence_present NVDA-A304-VALUATION-RISK


## QQQ — run `0d890564-2479-4361-94e8-25c48af3b9a8`

**Gold contract rules executed for this ticker**

(none: no executed contract rule belongs to this ticker)

Contract rules of this ticker NOT executed by the entry: QQQ-A001-RATE-CUT-CYCLE, QQQ-A003-LIQUIDITY-EXPANSION, QQQ-A304-VALUATION-RISK, QQQ-A501-RECESSION-RISK, QQQ-A601-NARRATIVE-MOMENTUM, QQQ-ETF-CONTEXT-CONTROL.  Release: **no_blocker_among_executed_rules** (blocks_release=False; blocking unresolved: —).

**Conflicts: what the run did, and what B2 said about each declared pair**

Admitted: A003__A501, A304__A601, A501__A601; main: A003__A501; admitted but declared nowhere (review): A501__A601.

| Pair | Declared as | Arbitration record | Outcome / B2 status | B2 or detector reasons | Supports bull/bear | Scores bull/bear |
|---|---|---|---|---|---|---|
| A001__A501 | conditional_only | b2_rejected | suppressed / candidate | ['BULL_SCORE_BELOW_THRESHOLD', 'INSUFFICIENT_BULL_SUPPORTING_EVIDENCE', 'NO_BULL_TICKER_SPECIFIC_SUPPORT'] | [1, 2] | [43.9798, 54.9367] |
| A003__A501 | allowed_main_conflicts | admitted | admitted / admitted | — | [7, 2] | [63.9159, 54.9367] |
| A304__A601 | allowed_main_conflicts | admitted | admitted / admitted | — | [13, 10] | [54.3161, 62.9705] |

**Diagnostic findings (engine-defined; decide nothing):** A001__A501 → needs_review (B2: BULL_SCORE_BELOW_THRESHOLD, INSUFFICIENT_BULL_SUPPORTING_EVIDENCE, NO_BULL_TICKER_SPECIFIC_SUPPORT)

**Not evaluable:** none


## SNDK — run `e8e0f398-7b26-4462-8135-a1410ea5b335`

**Gold contract rules executed for this ticker**

(none: no executed contract rule belongs to this ticker)

Contract rules of this ticker NOT executed by the entry: SNDK-A201-SEMICONDUCTOR-CYCLE, SNDK-ANTI-OVER-AI-CONTROL.  Release: **no_blocker_among_executed_rules** (blocks_release=False; blocking unresolved: —).

**Conflicts: what the run did, and what B2 said about each declared pair**

Admitted: none; main: —; admitted but declared nowhere (review): —.

| Pair | Declared as | Arbitration record | Outcome / B2 status | B2 or detector reasons | Supports bull/bear | Scores bull/bear |
|---|---|---|---|---|---|---|
| A201__A304 | conditional_only | no_arbitration_record | — / — | — | [None, None] | [None, None] |
| A301__A304 | conditional_only | b2_rejected | suppressed / candidate | ['BULL_SCORE_BELOW_THRESHOLD', 'NO_BULL_TICKER_SPECIFIC_SUPPORT', 'NO_BEAR_TICKER_SPECIFIC_SUPPORT'] | [3, 7] | [36.9042, 53.7399] |

**Diagnostic findings (engine-defined; decide nothing):** A301__A304 → needs_review (B2: BULL_SCORE_BELOW_THRESHOLD, NO_BULL_TICKER_SPECIFIC_SUPPORT, NO_BEAR_TICKER_SPECIFIC_SUPPORT)

**Not evaluable:** none

**PASS scope:** this PASS covers the label-based rule families and the contract rules in contract_rule_results; it says nothing about the contract rules this entry does not execute for the ticker (SNDK-A201-SEMICONDUCTOR-CYCLE, SNDK-ANTI-OVER-AI-CONTROL)


## MSFT — run `64568bfb-fe0c-453c-9872-831a8dc339a0`

**Gold contract rules executed for this ticker**

| Rule | Blocking | Evidence trigger (source / bound run → this run) | Alpha facts: identified / level (score) | Requirement met | Result | Blocks release | Reason |
|---|---|---|---|---|---|---|---|
| MSFT-A102-DIRECT-INFERENCE-TRIGGER | no | NOT_EVALUABLE — —; 43472ace → 64568bfb | A102: IDENTIFIED (6 claims) / candidate (41.9468) | False | not_evaluable | no | RUN_NOT_BOUND_TO_FROZEN_TRIGGER_MATRIX |

Contract rules of this ticker NOT executed by the entry: MSFT-A101-ENTERPRISE-AI-CONDITIONAL, MSFT-A102-INDIRECT-INFERENCE-SUPPORT, MSFT-CAPEX-BURDEN-CONDITIONAL.  Release: **no_blocker_among_executed_rules** (blocks_release=False; blocking unresolved: —).

**Conflicts: what the run did, and what B2 said about each declared pair**

Admitted: A301__A304, A304__A601; main: A301__A304; admitted but declared nowhere (review): A304__A601.

| Pair | Declared as | Arbitration record | Outcome / B2 status | B2 or detector reasons | Supports bull/bear | Scores bull/bear |
|---|---|---|---|---|---|---|
| A101__A304 | allowed_main_conflicts | b2_rejected | suppressed / candidate | ['BULL_SCORE_BELOW_THRESHOLD', 'INSUFFICIENT_BULL_SUPPORTING_EVIDENCE', 'NO_BULL_TICKER_SPECIFIC_SUPPORT'] | [1, 21] | [37.0165, 71.1556] |
| A102__A304 | conditional_only | no_arbitration_record | — / — | — | [None, None] | [None, None] |
| A301__A304 | allowed_main_conflicts | admitted | admitted / admitted | — | [17, 21] | [70.0, 71.1556] |

**Diagnostic findings (engine-defined; decide nothing):** none

**Not evaluable:** must_detect_if_evidence_present MSFT-A102-DIRECT-INFERENCE-TRIGGER


## TSM — run `fc09821e-c7cf-40a7-bd76-c98172e16992`

**Gold contract rules executed for this ticker**

(none: no executed contract rule belongs to this ticker)

Contract rules of this ticker NOT executed by the entry: TSM-AI-TO-FOUNDRY-TRANSMISSION.  Release: **no_blocker_among_executed_rules** (blocks_release=False; blocking unresolved: —).

**Conflicts: what the run did, and what B2 said about each declared pair**

Admitted: A101__A304, A301__A304, A304__A601; main: A101__A304; admitted but declared nowhere (review): A304__A601.

| Pair | Declared as | Arbitration record | Outcome / B2 status | B2 or detector reasons | Supports bull/bear | Scores bull/bear |
|---|---|---|---|---|---|---|
| A101__A304 | allowed_main_conflicts | admitted | admitted / admitted | — | [20, 7] | [70.0, 64.9288] |
| A201__A304 | conditional_only | no_arbitration_record | — / — | — | [None, None] | [None, None] |
| A301__A304 | conditional_only | admitted | admitted / admitted | — | [7, 7] | [51.6447, 64.9288] |

**Diagnostic findings (engine-defined; decide nothing):** none

**Not evaluable:** none


## AMD — run `d5b60b8a-66b8-44c1-9f55-ee345e58c48d`

**Gold contract rules executed for this ticker**

| Rule | Blocking | Evidence trigger (source / bound run → this run) | Alpha facts: identified / level (score) | Requirement met | Result | Blocks release | Reason |
|---|---|---|---|---|---|---|---|
| AMD-AI-GROWTH-VS-VALUATION | no | NOT_EVALUABLE — —; 949f685a → d5b60b8a | A101: IDENTIFIED (15 claims) / active (58.5954); A201: IDENTIFIED (56 claims) / active (62.5918); A301: IDENTIFIED (40 claims) / active (65.2271); A304: IDENTIFIED (97 claims) / dominant (81.5323) | — | not_evaluable | no | RUN_NOT_BOUND_TO_FROZEN_TRIGGER_MATRIX |

Contract rules of this ticker NOT executed by the entry: —.  Release: **no_blocker_among_executed_rules** (blocks_release=False; blocking unresolved: —).

**Conflicts: what the run did, and what B2 said about each declared pair**

Admitted: A101__A304, A301__A304, A304__A601; main: A301__A304; admitted but declared nowhere (review): A304__A601.

| Pair | Declared as | Arbitration record | Outcome / B2 status | B2 or detector reasons | Supports bull/bear | Scores bull/bear |
|---|---|---|---|---|---|---|
| A101__A304 | conditional_only | admitted | admitted / admitted | — | [5, 17] | [58.5954, 81.5323] |
| A201__A304 | conditional_only | no_arbitration_record | — / — | — | [None, None] | [None, None] |
| A301__A304 | allowed_main_conflicts | admitted | admitted / admitted | — | [15, 17] | [65.2271, 81.5323] |

**Diagnostic findings (engine-defined; decide nothing):** none

**Not evaluable:** conditional_only AMD-AI-GROWTH-VS-VALUATION

