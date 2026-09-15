# Gold v0.2 — Final Acceptance Table

**Step 4: first actual comparison of FROZEN GOLD v0.2 + FROZEN EVIDENCE TRIGGER MATRIX against actual persisted fresh-run system outputs.** No Gold rule, no evidence trigger value, was changed to produce this result. No discovered failure was fixed.

## John — Gold v0.2 Acceptance

**Formal Gold / Blocking**

- NVDA: **PASS**
- QQQ: **FAIL** (QQQ-A001-RATE-CUT-CYCLE — conditional-force violation)
- SNDK: **PASS**

**Release: FAIL**

**Silver / Non-Blocking**

- MSFT: **FAIL** (MSFT-A102-DIRECT-INFERENCE-TRIGGER — true miss; does not block release)
- TSM: **PASS**
- AMD: **PASS**

Gold contract: **FROZEN** — integrity verified
Evidence trigger matrix: **FROZEN** — integrity verified
Fresh runs: **6/6**
Alpha Memory: **SHADOW ONLY**
Activation modulation: **OFF**
Production semantics changed: **NO**

---

## Release Decision

**Formal Gold**

| Ticker | Status |
|---|---|
| NVDA | PASS |
| QQQ | FAIL |
| SNDK | PASS |

**Release Blocking Status: FAIL**

Reason: `QQQ-A001-RATE-CUT-CYCLE` is a blocking rule and resolved to FAIL (conditional-force violation — see Section below). A second blocking rule, `QQQ-A003-LIQUIDITY-EXPANSION`, is an unresolved blocking REVIEW, which would independently have produced `REVIEW_REQUIRED` had the FAIL not already been present.

**Silver Diagnostic**

| Ticker | Status |
|---|---|
| MSFT | FAIL |
| TSM | PASS |
| AMD | PASS |

**Silver affects release: NO**

---

## Method

Direction strictly followed: **FROZEN GOLD RULE + FROZEN EVIDENCE TRIGGER + ACTUAL SYSTEM RESPONSE → PASS / FAIL / NOT_TRIGGERED / REVIEW.**

- Gold v0.2 rule wording, rule types, acceptable Alpha mappings, allowed conflict families, blocking fields, and the frozen Step-3 evidence trigger PRESENT/ABSENT/UNCERTAIN states were treated as immutable inputs and were not reinterpreted.
- Actual system outputs were read for the first time in this task, exclusively from the six ledger-selected runs' own canonical persisted artifacts: `run_audit.json` (`activation_summary.per_alpha`), `conflicts.json` (`main_conflict`), `alpha_activations.json`, `structure_graph.json`.
- No pipeline rerun, no Provider call, no TradingAgents call, no fresh ticker run.
- Gold v0.2 is **not** an `expected_alphas == detected_alphas` model; acceptance is rule-based per Section 21/22 of the task — no exact-set match or `dominant_alphas - fixed_expected_alphas` metric was recreated.

### Detection Authority

- **Path**: `comqutor_alpha/regression/regression_report_v3.py::_DETECTED_LEVELS`, reading `run_audit.json → activation_summary.per_alpha[alpha_id]["level"]`. Canonical level vocabulary is defined and enforced upstream in `comqutor_alpha/graph_engine/alpha_level_classifier.py`. This is exactly the source the frozen Gold contract's own `detected_level_authority` field cites — reused unmodified, not redefined here.
- **Rule**: an Alpha is **DETECTED** iff `level ∈ {active, dominant, regime_level}`. `candidate` is never detected. For forbidden-dominant/negative-control checks, **DOMINANT** means `level ∈ {dominant, regime_level}`.
- **Note on a display-layer wrinkle investigated and resolved**: `structure_graph.json` additionally carries a presentation-only `activation_level` field (`alpha_display_normalizer.py`), which can read `capped_active` for an Alpha whose `qualified_level` is `active` but was capped down from a higher `target_level` (e.g. NVDA A101: `qualified_level=active`, `is_blocked=true`, `blocked_from=[dominant]`, `activation_level=capped_active`). This is a display/presentation concept only — `alpha_level_classifier.py`'s own documentation states the four canonical levels remain exactly `candidate/active/dominant/regime_level`, and `capped_active` is "never a fifth Activation level." The actual detection-authority field used here (`run_audit.json`'s `level`) reads plain `active` for NVDA A101, which **is** detected. No new threshold was invented; the existing, cited production authority was applied literally, and the wrinkle is documented rather than silently resolved.

---

## Main Table

| Ticker | Tier | Frozen Trigger Summary | Actual Detected | Actual Dominant | Actual Main Conflict | Gold Rule Result | Status |
|---|---|---|---|---|---|---|---|
| NVDA | FORMAL_GOLD | A101/A301/A304 PRESENT/STRONG; A601 PRESENT/STRONG; A103 PRESENT/MODERATE; A201 UNCERTAIN; Growth-vs-Valuation PRESENT | A101, A103, A301, A304, A601 | A301 | A101__A304 (admitted) | 5/5 rules PASS | **PASS** |
| QQQ | FORMAL_GOLD | A001 ABSENT(STRONG-contrary); A003 UNCERTAIN; A304 PRESENT; A501 ABSENT(STRONG-contrary); A601 PRESENT; ETF-control A301-evidence UNCERTAIN | A001, A103, A304, A601 | (none) | A304__A601 (admitted) | 1 FAIL, 1 REVIEW, 4 PASS/NOT_TRIGGERED | **FAIL** |
| SNDK | FORMAL_GOLD | A201 PRESENT/STRONG; anti-over-AI A101/A102 sub-triggers ABSENT/MODERATE | A201, A304, A601 | A201 | none admitted | 2/2 rules PASS | **PASS** |
| MSFT | SILVER | A101 PRESENT/MODERATE; A102-direct PRESENT/STRONG; A102-indirect UNCERTAIN; capex+linkage PRESENT | A001, A101, A103, A301 | A103 | none admitted | 1 FAIL, 2 REVIEW, 1 PASS | **FAIL (non-blocking)** |
| TSM | SILVER | AI-to-Foundry transmission PRESENT/STRONG (A101/A201/A301 sub-triggers PRESENT/STRONG; A103 optional PRESENT) | A101, A103, A201, A304, A601 | (none) | A101__A304 (admitted) | 1/1 rule PASS | **PASS (non-blocking)** |
| AMD | SILVER | Growth-vs-Valuation PRESENT/STRONG | A101, A103, A301, A304, A601 | A101 | A101__A304 (admitted) | 1/1 rule PASS | **PASS (non-blocking)** |

---

## Per-Ticker Detail

### NVDA — Formal Gold (Blocking)

| Rule | Frozen Trigger | Required Behavior | Actual Behavior | Result | Blocking? | Step-5 Review? |
|---|---|---|---|---|---|---|
| NVDA-A101-AI-GROWTH | PRESENT/STRONG | must_detect | A101 detected, level=active, score=70.0 | PASS | Yes | No |
| NVDA-A301-FUNDAMENTAL-GROWTH | PRESENT/STRONG | should_detect+conditional_only | A301 detected, level=dominant, score=78.49 | PASS | Yes | No |
| NVDA-A304-VALUATION-RISK | PRESENT/STRONG | must_detect | A304 detected, level=active, score=67.637 | PASS | Yes | No |
| NVDA-GROWTH-VS-VALUATION-CONFLICT | PRESENT | conflict from allowed family {A101__A304, A301__A304} should be admitted | main_conflict=A101__A304 admitted (in allowed family) | PASS | Yes | No |
| NVDA-SUPPORTING-STRUCTURES | A103 PRESENT/MODERATE, A201 UNCERTAIN, A601 PRESENT/STRONG | should_detect_if_supported (non-mandatory) | A103 detected (active); A601 detected (active); A201 not detected (candidate, consistent with its own UNCERTAIN trigger) | PASS | No | No |

**Ticker status: PASS.** All blocking rules PASS.

### QQQ — Formal Gold (Blocking)

| Rule | Frozen Trigger | Required Behavior | Actual Behavior | Result | Blocking? | Step-5 Review? |
|---|---|---|---|---|---|---|
| QQQ-A001-RATE-CUT-CYCLE | ABSENT/STRONG (contrary evidence) | conditional_only/do_not_force → NOT_TRIGGERED expected | A001 detected, level=active, score=66.423, direction=positive | **FAIL** (conditional-force violation) | Yes | **Yes** |
| QQQ-A003-LIQUIDITY-EXPANSION | UNCERTAIN/WEAK | should_detect_if_supported; UNCERTAIN → default REVIEW | A003 not detected (candidate, score 0.0) | REVIEW | Yes | No |
| QQQ-A304-VALUATION-RISK | PRESENT/STRONG | conditional_only, should surface | A304 detected, level=active, score=69.243 | PASS | Yes | No |
| QQQ-A501-RECESSION-RISK | ABSENT/STRONG (contrary evidence) | conditional_only/do_not_force → NOT_TRIGGERED expected | A501 not detected (candidate, score 44.555) | NOT_TRIGGERED | Yes | No |
| QQQ-A601-NARRATIVE-MOMENTUM | PRESENT/STRONG | should_detect_if_supported | A601 detected, level=active, score=54.306 | PASS | Yes | No |
| QQQ-ETF-CONTEXT-CONTROL | forbidden A301; strong ETF-evidence UNCERTAIN | forbidden_dominant_without_strong_evidence (asymmetric) | A301 not dominant (candidate, score 37.775) | PASS | Yes | No |

**Ticker status: FAIL.** `QQQ-A001-RATE-CUT-CYCLE` is a blocking rule and FAILed.

### SNDK — Formal Gold (Blocking)

| Rule | Frozen Trigger | Required Behavior | Actual Behavior | Result | Blocking? | Step-5 Review? |
|---|---|---|---|---|---|---|
| SNDK-A201-SEMICONDUCTOR-CYCLE | PRESENT/STRONG | should_detect_if_supported+conditional_only | A201 detected, level=dominant, score=84.22 | PASS | Yes | No |
| SNDK-ANTI-OVER-AI-CONTROL | forbidden A101/A102; both sub-triggers ABSENT/MODERATE | forbidden_dominant_without_strong_evidence (asymmetric) | Neither A101 (candidate, 0.0) nor A102 (candidate, 0.0) dominant | PASS | Yes | No |

**Ticker status: PASS.** Both blocking rules PASS.

### MSFT — Silver Diagnostic (Non-Blocking)

| Rule | Frozen Trigger | Required Behavior | Actual Behavior | Result | Blocking? | Step-5 Review? |
|---|---|---|---|---|---|---|
| MSFT-A101-ENTERPRISE-AI-CONDITIONAL | PRESENT/MODERATE | conditional_only, should surface | A101 detected, level=active, score=55.697 | PASS | No | No |
| MSFT-A102-DIRECT-INFERENCE-TRIGGER | PRESENT/STRONG | must_detect | A102 NOT detected (candidate, score 34.967) | **FAIL** | No | No |
| MSFT-A102-INDIRECT-INFERENCE-SUPPORT | UNCERTAIN/WEAK | should_detect (optional) | A102 not detected (candidate, score 34.967) | REVIEW | No | No |
| MSFT-CAPEX-BURDEN-CONDITIONAL | PRESENT/STRONG (capex+linkage both PRESENT) | conditional_only/do_not_force (permissive, not obligatory) | A304 not detected (candidate, score 43.364); no force occurred | REVIEW | No | **Yes** |

**Ticker status (diagnostic only): FAIL.** `blocks_release = false` for every MSFT rule (Silver tier).

### TSM — Silver Diagnostic (Non-Blocking)

| Rule | Frozen Trigger | Required Behavior | Actual Behavior | Result | Blocking? | Step-5 Review? |
|---|---|---|---|---|---|---|
| TSM-AI-TO-FOUNDRY-TRANSMISSION | PRESENT/STRONG (A101/A201/A301 sub-triggers PRESENT/STRONG; A103 optional PRESENT) | conditional_only, canonical paths A101→A201, A101→A201→A301 | A101 detected (active, 52.901); A201 detected (active, 64.504) — first hop realized; A301 not detected (candidate, 44.772, conditional/not required simultaneously); A103 detected (active, 68.55) but optional/contextual only | PASS | No | No |

**Ticker status (diagnostic only): PASS.** `blocks_release = false`.

### AMD — Silver Diagnostic (Non-Blocking)

| Rule | Frozen Trigger | Required Behavior | Actual Behavior | Result | Blocking? | Step-5 Review? |
|---|---|---|---|---|---|---|
| AMD-AI-GROWTH-VS-VALUATION | PRESENT/STRONG | conditional_only, allowed family {A101__A304, A301__A304} | A101 detected (regime_level, 90.38); A301 detected (active, 62.24); A304 detected (active, 61.28); main_conflict=A101__A304 admitted (in allowed family) | PASS | No | No |

**Ticker status (diagnostic only): PASS.** `blocks_release = false`.

---

## Formal Gold Evidence Trigger Summary (Comparison Outcome)

| Ticker | Rules | PASS | FAIL | REVIEW | NOT_TRIGGERED |
|---|---|---|---|---|---|
| NVDA | 5 | 5 | 0 | 0 | 0 |
| QQQ | 6 | 4 | 1 | 1 | 1 |
| SNDK | 2 | 2 | 0 | 0 | 0 |
| **Total** | **13** | **11** | **1** | **1** | **1** |

**Blocking FAIL count: 1** (`QQQ-A001-RATE-CUT-CYCLE`)
**Blocking REVIEW count: 1** (`QQQ-A003-LIQUIDITY-EXPANSION`)
**Release Blocking Status: FAIL**

## Silver Diagnostic Evidence Trigger Summary (Comparison Outcome)

| Ticker | Rules | PASS | FAIL | REVIEW |
|---|---|---|---|---|
| MSFT | 4 | 1 | 1 | 2 |
| TSM | 1 | 1 | 0 | 0 |
| AMD | 1 | 1 | 0 | 0 |
| **Total** | **6** | **3** | **1** | **2** |

**Silver affects release: NO** (all `blocks_release = false`).

---

## Special Negative-Control Report

**QQQ A301 ETF-control**
- Actual level: `candidate` (score 37.775) — not dominant/regime_level.
- Strong ETF-level evidence sub-trigger (frozen, Step 3): `UNCERTAIN`.
- Result: **PASS** — forbidden dominance did not occur (asymmetric rule: not-dominant is always PASS regardless of evidence strength).

**SNDK A101 anti-over-AI**
- Actual level: `candidate` (score 0.0) — not dominant/regime_level.
- Strong AI evidence sub-trigger (frozen, Step 3): `ABSENT`.
- Result: **PASS**.

**SNDK A102 anti-over-AI**
- Actual level: `candidate` (score 0.0) — not dominant/regime_level.
- Strong inference evidence sub-trigger (frozen, Step 3): `ABSENT`.
- Result: **PASS**.

---

## Special Composite Report

**NVDA Growth-vs-Valuation**
- Trigger: PRESENT.
- Actual relevant Alphas: A101 active (70.0), A301 dominant (78.49), A304 active (67.637).
- Actual conflict: `A101__A304`, admitted (bull=70.0, bear=67.637) — within allowed family {A101__A304, A301__A304}.
- Result: **PASS**.

**TSM AI-to-Foundry**
- Trigger: PRESENT.
- Actual Alpha states: A101 active (52.901), A201 active (64.504), A301 candidate (44.772, conditional), A103 active (68.55, optional/contextual only).
- Actual canonical graph path: A101→A201 taxonomy edge (weight 0.75) realized at detected level for both endpoints; A103→A201 correctly not relied upon (not a canonical taxonomy edge; A103 contributes only as optional support, consistent with the frozen exclusion).
- Result: **PASS**.

**AMD Growth-vs-Valuation**
- Trigger: PRESENT.
- Actual relevant Alphas: A101 regime_level (90.38), A301 active (62.24), A304 active (61.28).
- Actual conflict: `A101__A304`, admitted (bull=90.38, bear=61.28) — within allowed family {A101__A304, A301__A304}.
- Result: **PASS**.

---

## Step-5 Review Queue

1. **QQQ-A001-RATE-CUT-CYCLE** — `CONDITIONAL_FORCE_VIOLATION`. Frozen trigger ABSENT with strong contrary evidence (93% no-cut probability persisted upstream), yet A001 actually reached `active`/positive (score 66.423). The FAIL determination itself is not deferred (unambiguous from frozen inputs + persisted output per Section 27's carve-out), but the root cause — which gate/seed/evidence path produced this detection despite absent/contrary current evidence — requires Step 5 tracing.
2. **MSFT-CAPEX-BURDEN-CONDITIONAL** — evidence condition satisfied (capex_present=PRESENT, capex_downside_linkage_present=PRESENT) but A304 not detected; the rule's do_not_force/permissive semantics do not impose an affirmative detection obligation, so REVIEW was recorded rather than PASS/FAIL. Step 5 should determine whether this pattern (legitimate linkage evidence, no detection) reflects an activation-scoring gap worth deeper adjudication.

---

## Validation

- Gold JSON SHA256 verified: `e2df7139e19ec998afc6335caf4d53528dd3f4356a46d4e9a88d9d04b520000f` ✓ matches expected.
- Gold MD SHA256 verified: `8e184d7ed41cbe253b5aa7e97e150e9c7f4dbfd6852d411e9874dbe299bf9f04` ✓ matches expected.
- Trigger JSON SHA256 verified: `3e8e7402803632198b01c2a08a98929031929cc4b909927dc7e475d37b5d22a1` ✓ matches expected.
- Trigger MD SHA256 verified: `b751faec4166e17bf70393e0ad25523dfa3d1dae66e9ed9bdfca9a1506db5bfc` ✓ matches expected.
- 19 frozen rules represented exactly once: confirmed (5 NVDA + 6 QQQ + 2 SNDK + 4 MSFT + 1 TSM + 1 AMD = 19).
- Exactly six selected runs used, all matched against the ledger.
- No trigger value changed; no Gold rule changed.
- Actual outputs read exclusively from the same six selected runs' canonical artifacts.
- Formal Gold = NVDA/QQQ/SNDK only; Silver = MSFT/TSM/AMD only; Silver does not affect release.
- No old exact-set Alpha metric substituted; no `dominant_alphas - fixed_expected_alphas` arithmetic used.
- No production files changed; no test files changed.
- Provider calls = 0. TradingAgents calls = 0. Ticker runs = 0. Commits = 0. Pushes = 0. Destructive git operations = 0.

**STEP 4 ONLY. FROZEN INPUTS COMPARED. GOLD NOT CHANGED. TRIGGER MATRIX NOT CHANGED. NO FAILURE FIXED.**
