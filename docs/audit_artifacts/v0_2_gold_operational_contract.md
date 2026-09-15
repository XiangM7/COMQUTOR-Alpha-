# Gold Labels v0.2

Gold v0.2 is **EVIDENCE-CONDITIONAL**. It does **not** require a fixed Alpha output independent of evidence — every rule pairs a concept with an evidence condition and a rule type governing how strictly that condition binds.

## Formal Gold / Blocking

| Ticker | Thesis |
|---|---|
| **NVDA** | AI leader growth-vs-valuation conflict |
| **QQQ** | Macro / liquidity / valuation / narrative ETF case |
| **SNDK** | Semiconductor/storage cycle and anti-over-AI false-positive control |

**Formal Gold alone controls blocking QA.**

## Silver Diagnostic / Non-Blocking

| Ticker | Thesis |
|---|---|
| **MSFT** | Enterprise AI / inference / capex burden |
| **TSM** | Semiconductor foundry / AI infrastructure transmission |
| **AMD** | AI semiconductor competitor / valuation conflict |

**Silver Diagnostic is diagnostic only and cannot block release.**

## v0.2 Acceptance Semantics

- **`must_detect_if_evidence_present`** — if the defining evidence condition is present, the system must detect an acceptable Alpha/structure at an official detected level; if absent, not triggered.
- **`should_detect_if_supported`** — if meaningful evidence supports the concept, the system should surface it; dominance is not required unless specified.
- **`conditional_only`** — valid only when its evidence condition is present; never forced otherwise.
- **`do_not_force`** — ticker identity, historical exposure, or stereotype alone can never satisfy a rule; current evidence is always required.
- **`allowed_main_conflicts`** — one or more existing canonical conflict structures may satisfy a thesis when both sides are currently supported; no conflict is forced when one side lacks sufficient evidence.
- **`forbidden_dominant_without_strong_evidence`** — if a specified Alpha reaches dominant/regime_level status, there must be strong current evidence supporting it.
