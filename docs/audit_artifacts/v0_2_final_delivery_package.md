# v0.2 Final Delivery Package

**Authority:** `docs/audit_artifacts/v0_2_john_frozen_gold_baseline.yaml` (`JOHN_WRITTEN_V0_2_BASELINE`). This package is an index / concise synthesis over preserved evidence — it does not rewrite, recompute, or supersede any underlying audit artifact. Every factual claim below cites the exact artifact path that supports it. Full detail in `v0_2_final_delivery_package.json`.

---

## 1. Frozen Rules + Change Record

**Tiers** — Formal Gold: NVDA, QQQ, SNDK. Silver Diagnostic (non-blocking): MSFT, TSM, AMD.

**Frozen allowed-main-conflict baseline** (16 pairs, unchanged, `v0_2_john_frozen_gold_baseline.yaml`):

| Ticker | Allowed pairs |
|---|---|
| NVDA | A101__A304, A301__A304 |
| QQQ | A001__A501, A003__A501, A304__A601 |
| SNDK | A201__A304, A301__A304 |
| MSFT | A102__A304, A101__A304, A301__A304 |
| TSM | A201__A304, A301__A304, A101__A304 |
| AMD | A101__A304, A201__A304, A301__A304 |

**Interpretation, unchanged:** allowed means permitted when evidence supports it, never mandatory; absence of a listed conflict is never automatically a failure; there is no universal fixed number of Alphas or conflicts; conditional rules remain conditional (informational miss, not failure); `forbidden_dominant_without_strong_evidence` and `do_not_force` remain enforced. **NVDA's fresh A304__A601 finding is NOT added to this baseline** — it is recorded as `REVIEW_REQUIRED` evidence in Section 2.

**Change record chronology** (each stage's own artifact is authoritative; not restated here):

| Stage | Event |
|---|---|
| Day 1 | Formal rule baseline frozen |
| Day 2 | Rule→evidence→output audit (25 rows: 21 PASS/1 FAIL/3 REVIEW) |
| Day 3 | `structured_output_adapter.py` 1-line direction-inference fix |
| Day 4B | Candidate 1 designed, Provider-validated, **REJECTED_NET_REGRESSION** (69.50% vs 74.00%) |
| Day 4C–4D | Candidate 1 reverted; Candidate 2 designed, dev-tested (72.50%), **NOT_ACCEPTED**; reverted to baseline |
| Day 4E | New 300-sample blind holdout built from untouched raw evidence (100 dev / 150 sealed final / 50 reserve) |
| Day 4F | 100-sample Development Gold independently adjudicated and frozen |
| Day 4G | Candidate 3 designed and dev-tested: 64.00% → **81.00%**; frozen |
| Day 4H | 150-sample Final Independent Gold independently adjudicated and frozen |
| Day 4I | **ONE-SHOT** final Alpha validation: **124/150 = 82.67%** |
| Day 4J | Polarity provenance audit: Holdout #2 **123/141 = 87.23%** ELIGIBLE |
| Day 4K | Fresh E2E: NVDA REVIEW_REQUIRED, QQQ PASS |

*An early Day-2 acceptance snapshot (`v0_2_final_acceptance_table.md`) showed QQQ Formal Gold = FAIL — this predates the entire Candidate 1/2/3 saga and is retained only as historical chronology, never as current truth.*

---

## 2. Rule / Evidence / Final Acceptance Table

| Ticker | Tier | Evidence State | Dominant | Main Conflict | Status | Source |
|---|---|---|---|---|---|---|
| **NVDA** | Formal Gold | Rich, ticker-specific for A301 (18/3) & A304 (23/5) | A301 (+74.21), A304 (−71.73) | Admitted A304__A601, canonical but **off NVDA's own list**; A301__A304 suppressed on merits, not forced | **REVIEW_REQUIRED** | `v0_2_candidate3_fresh_e2e_nvda.json` |
| **QQQ** | Formal Gold | Genuine ETF-level (A003 fund flows) + macro (A501) | None dominant (legitimate) | Admitted A003__A501, **on QQQ's list** | **PASS** | `v0_2_candidate3_fresh_e2e_qqq.json` |
| **SNDK** | Formal Gold | Rich for A201 (42/9 agents) | A201 (+84.22) | **None admitted** — 3 rejected, 3 suppressed, legitimately insufficient | **PASS** | run `e8e0f398-...`, verified live |
| MSFT | Silver | Direction-inference miss (fixed Day 3) + one activation-formula REVIEW | not re-verified this task | not re-verified this task | UNRESOLVED_DIAGNOSTIC (non-blocking) | `v0_2_day3_review_resolution.md` |
| TSM | Silver | Per Day 2 audit | Per Day 2 audit | Per Day 2 audit | PASS (Day 2, not re-verified) | `v0_2_rule_evidence_output_audit.json` |
| AMD | Silver | Per Day 2 audit | Per Day 2 audit | Per Day 2 audit | PASS (Day 2, not re-verified) | `v0_2_rule_evidence_output_audit.json` |

**QQQ's fresh PASS does not override its separate, standing, carried Formal Gold `REVIEW_REQUIRED` from an earlier frozen-input run with a different (off-list) conflict — that record and its unadopted `RULE_CHANGE_RECOMMENDATION` remain unchanged.** **NVDA's REVIEW_REQUIRED is reported honestly, never relabeled PASS.**

---

## 3. Error Statistics + Before/After Validation

Denominators are never combined.

| Metric | Value | Artifact |
|---|---:|---|
| Development Candidate 3 (100 samples) | 81.00% (DEVELOPMENT_METRIC_ONLY) | `v0_2_candidate3_dev_result.json` |
| **Independent Final Alpha** (150 samples) | **124/150 = 82.67%** ✅ ≥80% | `v0_2_candidate3_final_validation_result.json` |
| **Independent Polarity** (141 samples) | **123/141 = 87.23%** ✅ ≥80% | `item2_blind_holdout2_summary.json` |

**Final Alpha error diagnostics (26 total, descriptive only — not new thresholds):**
- 18 false positives, 4 false negatives, 4 wrong-Alpha substitutions
- Dominant category: valuation/A304 boundary = **11/26**
- A103-over-A101 tie-break overcorrection: 2/4 wrong-Alpha substitutions
- Bare-sentiment-percentage → A601 recurrence: `gold-final-116`, matching the one Day 4G development regression

Full detail: `v0_2_candidate3_final_error_audit.json`.

---

## 4. Run Inventory + Artifacts

| Run Type | Dataset | run_id | Result | Artifacts |
|---|---|---|---|---|
| FROZEN REGRESSION | 6-ticker regression | per-ticker | 21 PASS/1 FAIL/3 REVIEW (25 rows) | `v0_2_rule_evidence_output_audit.json` |
| INDEPENDENT VALIDATION | Dev Gold (100) | N/A (Provider eval) | 81.00% dev-only | `v0_2_candidate3_dev_result.json` |
| INDEPENDENT VALIDATION | Final Gold (150) | N/A (Provider eval) | **124/150=82.67%** | `v0_2_candidate3_final_validation_result.json` |
| INDEPENDENT VALIDATION | Holdout #2 polarity (141) | N/A (frozen historical) | **123/141=87.23%** | `item2_blind_holdout2_summary.json` |
| **FRESH E2E** | NVDA | `ded99ecd-a186-4a90-859e-0f1a0efa43db` | REVIEW_REQUIRED, 1923s | `v0_2_candidate3_fresh_e2e_nvda.json` |
| **FRESH E2E** | QQQ | `0d890564-2479-4361-94e8-25c48af3b9a8` | PASS, 1721s | `v0_2_candidate3_fresh_e2e_qqq.json` |
| **PERSISTED DEMO** (never called "Fresh") | SNDK | `e8e0f398-7b26-4462-8135-a1410ea5b335` (2026-09-04) | Dominant A201, no conflict | verified live this task |

---

## 5. Demo Walkthrough + Performance Logs

See dedicated artifacts:
- `docs/audit_artifacts/v0_2_demo_walkthrough_script.md`
- `docs/audit_artifacts/v0_2_demo_walkthrough_checklist.json` / `.md`
- `docs/audit_artifacts/v0_2_final_performance_log.json` / `.md`

---

## Final Gate Snapshot

`FINAL_ALPHA_TARGET_MET = YES` (82.67%). `POLARITY_TARGET_MET = YES` (87.23%). Candidate 3 classifier `d53b2d75...`, batch `a03c8f67...`, **permanently frozen for this validation cycle**.
