# Entity Exposure Gating Consistency — v0.1.3

Audit/documentation only. **Provider calls: 0. TradingAgents calls: 0. No ticker run. No production code changed.**

Canonical authority: `comqutor_alpha/exposure/seed_loader.py` (seed file: `comqutor_alpha/config/entity_alpha_exposure_seed_v0.1.yaml`) — field `effective_status` (declared value: `configured_status`)
Canonical status vocabulary: `draft_shadow` | `approved_gating` | `disabled`
Ticker consistency: **6/6**
Contradictory status aliases: **0**
Overall result: **PASS**

| Ticker | Run ID | Canonical Status | Artifact Status | Conflict Found | Result |
|---|---|---|---|---|---|
| NVDA | `57d7b4c4-dbb9-4134-b962-ee2a873941cc` | approved_gating | approved_gating | No | PASS |
| QQQ | `f88c8956-cb62-48aa-9951-89f8e8a95f83` | approved_gating | approved_gating | No | PASS |
| MSFT | `43472ace-454f-4c69-892c-adca91c25be7` | approved_gating | approved_gating | No | PASS |
| SNDK | `e8e0f398-7b26-4462-8135-a1410ea5b335` | approved_gating | approved_gating | No | PASS |
| TSM | `dfc7ceb3-3584-4514-bd84-6c371aab3e95` | approved_gating | approved_gating | No | PASS |
| AMD | `949f685a-3945-4fd0-b7b9-362b37c90721` | approved_gating | approved_gating | No | PASS |

("Artifact Status" = the run's own persisted `entity_alpha_exposures.json` `effective_status`, uniform across every per-Alpha record within that run. Independently cross-checked against `run_audit.json`'s `seed_status_consistency` invariant and a live, read-only `GET /api/research/{run_id}/entity-exposures` — all identical on all six.)

---

## Step 1–2: Where the status is represented, and the canonical authority

| Layer | File / field | Role |
|---|---|---|
| Canonical source | `comqutor_alpha/config/entity_alpha_exposure_seed_v0.1.yaml` + `entity_alpha_exposure_seed_manifest_v0.1.yaml`, loaded by `comqutor_alpha/exposure/seed_loader.py` | Product authority. Defines `configured_status` per ticker (default `draft_shadow`); `resolve_exposure_mode()` computes `effective_status` after the fail-closed approval-completeness check. |
| Run artifact | `outputs/runs/<run_id>/entity_alpha_exposures.json` — top-level `configured_status`/`effective_status`/`mode`, repeated per Alpha record | Frozen at the time this specific run executed. |
| run_audit | `run_audit.json` → `entity_exposure.{mode, current_seed_status, seed_approval_status, enforcement_allowed}` + the `seed_status_consistency` accounting invariant (`entity_exposure_audit.current_seed_status == _current_seed_status(ticker)`) | Cross-checks the run's frozen value against a freshly-resolved value in the same artifact. |
| API response | `GET /api/research/{run_id}/entity-exposures` → `current_seed_status` | Resolved **fresh from the live seed file on every call** (`comqutor_alpha/api/routes_research.py::_current_seed_status`) — never cached, never derived from the frozen artifact. |
| Frontend type | `frontend/src/api/types.ts` → `EntityExposureLifecycleStatus = "draft_shadow" \| "approved_gating" \| "disabled"` (canonical); `mode` and `seed_approval_status` explicitly marked `@deprecated` | Canonical vocabulary declared once, deprecated aliases kept only for backward compatibility. |
| Frontend display | `frontend/src/components/AlphaCard.tsx::resolveLifecycleStatus()` | Prefers `effective_status`; falls back to translating the legacy `mode` field only for historical payloads that predate `effective_status` entirely. |
| `regression_report_v3.json` | — | Contains **no** Entity Exposure / seed-status field at all — confirmed out of scope, no false-authority risk there. |

**The canonical field is `effective_status` (with `configured_status` as its pre-override input) — verified by reading `seed_loader.py`'s own module docstring and constants directly, not assumed from a prior closure report.**

---

## Step 4: Investigating the historical "shadow / draft" wording

Three legitimate, non-buggy explanations apply simultaneously (not mutually exclusive), plus one that is confirmed **not** present in the current final six-run set:

**A. Old/deprecated status — temporal staleness (root cause, now fixed).**
`_current_seed_status()`'s own code docstring states this verbatim: *"John observed inconsistent approved_gating/shadow/draft wording — root cause was old per-run artifacts persisted before a ticker's approval date, served verbatim forever after."* A run executed **before** a ticker's seed was approved would freeze `draft_shadow` in its own artifact forever; a screenshot of that old run and a screenshot of today's live state would legitimately differ — not a bug in either single artifact, just two different points in time. **Fixed this session**: the API now additionally exposes a freshly-resolved `current_seed_status`, kept explicitly separate from the run's own frozen `configured_status`/`effective_status`.

**B. A different subsystem's field, visually confused.**
Alpha Memory (added this session) exposes its own, unrelated field: `alpha_memory.mode = "shadow"` — describing whether the Alpha Memory feedback-loop feature is audit-only (it always is). This has **nothing to do** with Entity Exposure gating.

> **Alpha Memory mode = shadow is NOT the same field as Entity Exposure seed/gating status = approved_gating.**
> Never present a screenshot mixing the two without labeling which subsystem/field it is.

**C. Stale/legacy field naming, not a value conflict.**
`mode: "off"|"shadow"|"enforced"` and `seed_approval_status` are both explicitly `@deprecated` in `types.ts`, kept only for backward compatibility, and are **deterministically derived** from `effective_status` via `LEGACY_MODE_BY_STATUS` (`draft_shadow→shadow`, `approved_gating→enforced`, `disabled→off`) — never an independent second source of truth. A screenshot showing the old field name is showing old *naming*, not a conflicting *value*. Separately: the canonical status value itself is literally named `draft_shadow`, whose UI label is *"Draft shadow"* — a ticker that genuinely isn't yet approved is **supposed** to show the word "shadow" as part of its correct, current label. That's a real, valid state, not a bug — a third, distinct source of the word "shadow" on screen.

**D. Still genuinely contradictory in current final outputs — does NOT apply.**
Verified directly across all six FINAL_FRESH_SELECTED runs: `configured_status == effective_status == "approved_gating"` uniformly on every per-Alpha record, the deprecated `mode` field correctly maps to `"enforced"` in every case, `run_audit.json`'s `seed_status_consistency` invariant passes on all six, and a live read-only `GET` against each already-completed run returns a freshly-resolved `current_seed_status` identical to the frozen artifact value. **Zero contradictions found in the current final six-run set.**

---

## Verification method

1. Read `seed_loader.py` source directly for the canonical vocabulary — not assumed.
2. Read each run's own `entity_alpha_exposures.json` (top-level + every per-Alpha record) for all six runs.
3. Read each run's `run_audit.json` `entity_exposure` block and its `seed_status_consistency` invariant.
4. Issued a live, read-only `GET /api/research/{run_id}/entity-exposures` against all six already-completed runs (no new research triggered) and diffed against the frozen artifact.
5. Read `types.ts` / `AlphaCard.tsx` to confirm the deprecated fields are deterministically derived, never independently authoritative.
6. Grepped `regression_report_v3.json` — no exposure/seed field present there.

**Provider calls: 0. TradingAgents calls: 0. No ticker run. No production code changed.**
