# Nine-Artifact Bundle Completeness — Six-Ticker Regression

QA Closure v0.1.2, Item 6. Artifact completeness and provenance only — B1–B5 semantics, J2 labels, and A101 invalidation content are unchanged. `PROVIDER_CALLS = 0` throughout.

## Evidence 1 — Six-ticker artifact matrix

| Ticker | Run | Metadata | Raw | Structured | Evidence Facts | Alpha Matches | Graph | Activations | Conflicts | Audit | Status |
|---|---|:-:|:-:|:-:|:-:|:-:|:-:|:-:|:-:|:-:|---|
| NVDA | `5ffe121a…` | ✓ original | ✓ original | ✓ original | ✓ original | ✓ original | ✓ original | ✓ original | ✓ original | ✓ original | **complete_original** |
| QQQ | `a364e0ee…` | ✓ original | ✓ original | ✓ original | ✓ **reconstructed** | ✓ original | ✓ original | ✓ **reconstructed** | ✓ **reconstructed** | ✓ original | **complete_reconstructed** |
| MSFT | `07ddc074…` | ✓ original | ✓ original | ✓ original | ✓ original | ✓ original | ✓ original | ✓ original | ✓ original | ✓ original | **complete_original** |
| SNDK | `183b04dd…` | ✓ original | ✓ original | ✓ original | ✓ **reconstructed** | ✓ original | ✓ original | ✓ **reconstructed** | ✓ **reconstructed** | ✓ original | **complete_reconstructed** |
| TSM | `1a338ced…` | ✓ original | ✓ original | ✓ original | ✓ **reconstructed** | ✓ original | ✓ original | ✓ **reconstructed** | ✓ **reconstructed** | ✓ **reconstructed** | **complete_reconstructed** |
| AMD | `b71765a0…` | ✓ original | ✓ original | ✓ original | ✓ **reconstructed** | ✓ original | ✓ original | ✓ **reconstructed** | ✓ **reconstructed** | ✓ original | **complete_reconstructed** |

**All six regression tickers: 9/9 required artifacts.** 2 were already complete (NVDA, MSFT — untouched by this task). 4 needed 3–4 files each, all now safely reconstructed from that same run's own already-present, undisputed data — zero raw historical output fabricated.

## Evidence 2 — One complete original folder (NVDA)

```
$ ls outputs/runs/5ffe121a-68fd-473b-82b5-c9465332d8a2/{metadata,raw_agent_outputs,structured_agent_outputs,evidence_facts,alpha_matches,structure_graph,alpha_activations,conflicts,run_audit}.json
metadata.json                  831 B
raw_agent_outputs.json       108 KB
structured_agent_outputs.json  1.4 MB
evidence_facts.json           29 KB
alpha_matches.json             6.7 MB
structure_graph.json          369 KB
alpha_activations.json        288 KB
conflicts.json                951 KB
run_audit.json                115 KB
```
All nine present, all originally emitted by this run's own completed pipeline — never touched by Item 6.

## Evidence 3 — Reconstructed historical example (QQQ)

```text
Ticker: QQQ
Run: a364e0ee-3bb4-4032-88b7-5cd82e379805
Bundle: 9/9 (complete_reconstructed)

Original artifacts:
  metadata.json, raw_agent_outputs.json, structured_agent_outputs.json,
  alpha_matches.json, structure_graph.json, run_audit.json

Reconstructed artifacts:
  evidence_facts.json    <- extract_evidence_facts_export(structure_graph.json, alpha_matches.json)
  alpha_activations.json <- extract_alpha_activations_export(structure_graph.json)
  conflicts.json          <- detect_alpha_conflicts(structure_graph.json['activation'], alpha_matches.json['matches'])
                              -> extract_conflicts_export(...)

Provider calls: 0
```

Reconstruction method — **not** Architecture Replay's from-raw-text rebuild. All three reconstructed files are pure, deterministic functions of *this run's own already-present* `structure_graph.json` + `alpha_matches.json` (never re-derived, never re-matched), using the exact same official extraction functions (`comqutor_alpha.api.artifact_export.extract_*_export`) and the exact same B2 entry point (`detect_alpha_conflicts`) the live pipeline itself uses. Every reconstructed file's provenance is recorded in `docs/audit_artifacts/artifact_bundle_manifest.json`'s `reconstructed_artifacts` list — never silently presented as originally emitted.

The identical method and result were verified for SNDK and AMD; TSM additionally needed `run_audit.json` (rebuilt via the existing `build_run_audit_payload`, reading the now-complete bundle fresh from disk).

### Why file-based reconstruction, not Architecture Replay

Architecture Replay rebuilds `alpha_matches.json` from raw text using the *current* Alpha Mapper — for **AMD**, this was tested and found to disagree with the already-persisted `alpha_matches.json` (replay: `admitted_conflicts=['A301__A304']`; file-based: `[]`). Using replay's output would have made the reconstructed `conflicts.json` internally inconsistent with AMD's own, already-present, undisputed `alpha_matches.json`. File-based reconstruction (this task's method) is self-consistent with each run's own already-present artifacts by construction — the correct choice per task §5 ("the goal is auditability, not rewriting history").

A second, independent discrepancy was found and is reported for completeness: **TSM's database row** (`week4_conflict_result`) shows a *stale* 3-admitted-conflict result that agrees with neither the file-based computation *nor* QA Item 1's own fresh Architecture Replay of TSM (both show 0 admitted) — the DB row was written before some later B2/B4 change in this session's history and was correctly **not** used as a reconstruction source.

### Known content limitation (disclosed, not hidden)

QQQ/SNDK/TSM/AMD's own `structure_graph.json` (an **original**, never-touched artifact) predates two later, additive pipeline features: the Evidence Fact Index embedding (Structure Integrity Repair Sprint, Track 2) and the B4 Activation Level Alignment classifier (`target_level`/`qualified_level`/`is_blocked`/`activation_level`). Consequently:
- Reconstructed `evidence_facts.json` for these 4 tickers is schema-valid but reports **0 Evidence Fact groups** — an honest, faithful extraction of what the source graph actually contains, not a fabricated emptiness. (`unique_evidence_count` on the same alphas is non-zero — the underlying evidence exists, it was simply never grouped into this newer artifact shape by the pipeline version that originally computed this graph.)
- Reconstructed `alpha_activations.json` reflects this same older per-alpha schema (no `qualified_level`/`activation_level`/etc.).

Re-computing `structure_graph.json` itself to backfill this newer data would require re-scoring — explicitly out of scope for Item 6 ("Do not alter … activation data merely to make artifact consistency pass") — and was **not** performed. This is a real, disclosed limitation of the reconstructed bundles' content richness, not of their validity, identity, or provenance.

## Evidence 4 — Remaining blockers

**None.** All six selected regression runs reached 9/9. No ticker required `blocked_missing_source_data`.

## Cross-artifact consistency

Verified for all six tickers: every artifact's `run_id`/`ticker` field (where present) matches the selected run; `conflicts.json`'s `main_conflict` (when non-null) is a member of its own `conflicts[]` admitted set; every Alpha ID referenced by `conflicts.json` exists in that same run's `structure_graph.json` alpha list. **PASS** for all six.

## Regression report impact

Re-ran the exact QA Item 1 command (`python scripts/run_regression.py --tickers NVDA QQQ MSFT SNDK TSM AMD`, `PROVIDER_CALLS=0`) before and after reconstruction:

| Ticker | artifact_completeness (before → after) | overall_status (before → after) |
|---|---|---|
| NVDA | pass → pass | warning → warning (unchanged) |
| QQQ | fail → **pass** | fail → **warning** (`ARTIFACT_NOT_AVAILABLE` gone; `MISSING_EXPECTED_ALPHAS`+`MAIN_CONFLICT_MISMATCH` remain — real, pre-existing J2 provisional-label signals, untouched) |
| MSFT | pass → pass | warning → warning (unchanged) |
| SNDK | fail → **pass** | fail → **warning** (same pattern as QQQ) |
| TSM | fail → **pass** | fail → **warning** (same pattern as QQQ) |
| AMD | fail → **pass** | fail → **warning** (same pattern as QQQ) |

No ticker became `pass` merely from this repair — every remaining `warning` reflects a genuine, unmodified J2 provisional-label comparison, exactly matching QA Item 1's existing, unchanged status-arbitration philosophy (infra/data failure → fail; provisional mismatch alone → warning). Every other detected field (`detected_positive_alphas`, `admitted_conflicts`, `candidate_conflicts`, `main_conflict`, `graph_nodes`, `graph_edges`, `evidence_fact_count`, `ticker_consistency`) is **byte-identical before and after** for all four repaired tickers — confirmed programmatically, not sampled.
