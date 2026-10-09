# v0.2 Validation Freeze Plan — Day 1 (PLAN ONLY, NOT EXECUTED)

This document defines what will be frozen before the next validation round. Nothing in this plan has been executed. No run was triggered, no rule was changed, no Provider or TradingAgents call was made to produce it.

## 0. Acceptance Authority (Resolved)

John being unavailable, his latest written v0.2 baseline is now frozen as the highest acceptance authority: `docs/audit_artifacts/v0_2_john_frozen_gold_baseline.yaml` (`authority: JOHN_WRITTEN_V0_2_BASELINE`, `status: FROZEN_FOR_DAY2_IMPLEMENTATION_AND_VALIDATION`). This is not an invented rule change — every value in that file is copied verbatim from John's written instructions. The question "which of v0.1 / v0.2 / a new baseline is authoritative?" (previously open in this plan and in `v0_2_john_rule_baseline_diff.md`) is resolved: **the new frozen baseline file is authoritative for acceptance scope; the existing v0.1/v0.2 repo label files remain implementation sources only**, to be brought into alignment with it over time (tracked as `IMPLEMENTATION_ALIGNMENT_REQUIRED`, not modified in this Day 1 task).

## 1. Validation Type Vocabulary (Section 11)

Every future validation task must declare exactly one of these three types — they are never interchangeable and none of them is "fresh" by default:

| Type | Meaning | Recomputes model/research? | Recomputes code path? |
|---|---|---|---|
| **OLD_RESULT_REEVALUATED_UNDER_NEW_RULES** | An already-computed run's existing output is re-scored/re-adjudicated under a different rule set (e.g., John's restored baseline). No model or research recomputation. | No | No — only the rule/label layer changes |
| **FROZEN_INPUT_RECOMPUTED_WITH_NEW_CODE** | Existing frozen input/evidence is reprocessed through changed code (e.g., Architecture Replay after an Alpha Mapper fix). | No | Yes |
| **FRESH_RUN** | New upstream data is retrieved and the full research flow (TradingAgents + Provider) runs again. | Yes | Yes (implicitly) |

## 2. Formal Case Freeze Requirements (Section 12)

Before any scoring for the next validation round:

- Formal evaluation inputs (the specific run artifacts to be scored) are frozen and enumerated by ID before scoring begins — no run is selected after seeing its own result.
- Evidence cutoff (the point up to which agent-report evidence is considered current) is frozen and stated explicitly per ticker.
- Gold rule version used for scoring is frozen and stated explicitly — the authoritative source is now `docs/audit_artifacts/v0_2_john_frozen_gold_baseline.yaml` (see Section 0); the repo's v0.1/v0.2 label YAMLs remain implementation sources only, until brought into alignment.
- Trigger conditions (whether the evidence condition a conditional/should-detect rule depends on was actually met) are independently adjudicated by a human/John review step — the system's own detection output alone is never sufficient to establish that the evidence condition was met.
- Disputed trigger conditions (any case where the automatic detection and the independent adjudication disagree) are listed separately for review, never silently resolved in either direction.
- Existing outputs (all run artifacts and prior submission documents) are preserved and never overwritten by a future validation round — a new round produces new, separately-named artifacts.

## 3. Per-Ticker Freeze Definition

For each ticker, the next validation round must fix all of the following before scoring:

| Field | NVDA | QQQ | SNDK | MSFT | TSM | AMD |
|---|---|---|---|---|---|---|
| A. Input snapshot / run source | `57d7b4c4-dbb9-4134-b962-ee2a873941cc` | `f239a53f-4ebe-455c-bb76-5f5485903901` (post-remediation run; historical run `f88c8956-cb62-48aa-9951-89f8e8a95f83` explicitly excluded) | `e8e0f398-7b26-4462-8135-a1410ea5b335` | `43472ace-454f-4c69-892c-adca91c25be7` | `dfc7ceb3-3584-4514-bd84-6c371aab3e95` | `949f685a-3945-4fd0-b7b9-362b37c90721` |
| B. Evidence cutoff timestamp | TBD — to be stated explicitly per run before next scoring; **NOT_VERIFIED_DAY1** | TBD; **NOT_VERIFIED_DAY1** | TBD; **NOT_VERIFIED_DAY1** | TBD; **NOT_VERIFIED_DAY1** | TBD; **NOT_VERIFIED_DAY1** | TBD; **NOT_VERIFIED_DAY1** |
| C. Gold rule version | **Resolved:** `v0_2_john_frozen_gold_baseline.yaml` (`authority: JOHN_WRITTEN_V0_2_BASELINE`) | same resolution applies to all six tickers | | | | |
| D. Code commit / HEAD to be used | Current branch `comqutor-structure-layer`, HEAD to be re-recorded at the start of that task (do not assume — inspect, per this task's own Section 0 discipline) | | | | | |
| E. Model version | Not recorded in this Day 1 audit — **NOT_VERIFIED_DAY1**; must be captured from the run's own provider/model metadata before scoring | | | | | |
| F. Prompt version | Not recorded in this Day 1 audit — **NOT_VERIFIED_DAY1**; must be captured from the run's own metadata | | | | | |
| G. Rule/config hash | To be computed (SHA256 of whichever rule file is designated authoritative under item C) at freeze time, before scoring | | | | | |
| H. Expected artifact IDs / locations | `docs/audit_artifacts/v0_2_final_acceptance_table.json` (current, superseded pending this audit), plus the run's own `structure_graph.json` / conflict result under its `output_root` | | | | | |
| I. Evidence trigger adjudication source | Independent human/John review — never the system's own detection output alone (see Section 2 above) | | | | | |
| J. Validation type | To be assigned per task from the Section 1 vocabulary above — never assumed to be FRESH_RUN by default | | | | | |

Items marked **NOT_VERIFIED_DAY1** require the next validation task to capture them from the actual run metadata; this Day 1 audit did not execute or inspect a live run to obtain them, per its read-only/no-rerun scope.

## 4. QQQ Review Placeholder (Section 13)

QQQ current main conflict: **A301__A304**.

Review questions reserved for a later, dedicated evidence audit (not answered here):

1. Does A301 evidence represent ETF/component-level revenue expansion sufficiently for the QQQ object?
2. Is A301 based only on one company's revenue evidence?
3. Does A304 have valid supporting evidence?
4. Why did the system select A301__A304 as main conflict?
5. Is rule expansion warranted?

**Status: `REVIEW_REQUIRED`.** No guesses were made against these questions in Day 1. This status is unchanged by the authority freeze in Section 0 — A301__A304 is confirmed absent from John's frozen baseline, is not being added, and QQQ's output is not being modified.

## 5. What This Plan Does Not Do

This plan does not itself select a Gold rule version, does not add or remove any conflict pair, does not mark any ticker's acceptance status, and does not trigger any run. Its only function is to define, in advance, exactly what must be pinned down before the next validation round begins — consistent with the Section 12 requirement that formal inputs, evidence cutoff, and rule version be frozen *before* scoring, not decided during or after it.

## 6. Day 1 Final Status

```
RULE_SCOPE_FROZEN = YES
ACCEPTANCE_AUTHORITY_FROZEN = YES
QQQ_CURRENT_CONFLICT = REVIEW_REQUIRED
READY_FOR_FULL_DAY2 = YES
```

Rule scope and acceptance authority are frozen via `docs/audit_artifacts/v0_2_john_frozen_gold_baseline.yaml`. Everything still open is tracked as `IMPLEMENTATION_ALIGNMENT_REQUIRED` (see `v0_2_john_rule_baseline_diff.md`/`.json`) for Day 2+ implementation work, not as an unresolved acceptance-authority question.
