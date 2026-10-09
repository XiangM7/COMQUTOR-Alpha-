# v0.2 Alpha Prompt Candidate History

Full detail in `v0_2_alpha_candidate_history.json`. No historical result rewritten.

| | Prompt Version | Holdout #4 Result | Status |
|---|---|---:|---|
| **Baseline** | v3 (`a2ca2a32...`) | 148/200 = **74.00%** (measured before any inspection) | Current production prompt |
| **Candidate 1** | v4 — `36bf5a63...` (**retired**) | 139/200 = **69.50%** | `REJECTED_NET_REGRESSION` |
| **Candidate 2** | v5 — `70303c5f...` (**retired**) | 145/200 = **72.50%** (`DEVELOPMENT_METRIC_ONLY`) | `NOT_ACCEPTED_NO_INDEPENDENT_VALIDATION` |

Candidate 1 was used in real Provider-backed runs (Fresh NVDA `421bca7a-...`, Fresh QQQ `a4dae9c5-...`, and the Holdout #4 post-remediation validation) — its version identifier (`v4`) is permanently retired per this codebase's ADR-005 anti-collision rule, never reassigned. Candidate 2 (`v5`) is likewise retired after its one authorized development pass.

## Current Production Semantic Prompt

**`PRE_REMEDIATION_BASELINE`** — verified byte-exact after surgically removing both Candidate 1 and Candidate 2 edits:

| Prompt | SHA256 |
|---|---|
| `alpha_classifier` | `a2ca2a32be2d5c22301a0905112727d2c43aece60b1d9e680c8092c3d67c25d8` |
| `alpha_classifier_batch` | `0caa5b77b77a97618e92e1b3f254edf8749bae5aa4a21a42ba5d60a539effff0` |
