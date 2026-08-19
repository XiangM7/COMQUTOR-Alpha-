# Neutral / Unclassified Findings Audit — MSFT, run `07ddc074-9ab2-4b16-8957-acbf94012144`

QA Closure v0.1.2, Item 5. Audit / diagnostics only — no B1–B5 semantics changed, no findings force-classified, no count artificially reduced.

## Audit population

| Field | Value |
|---|---|
| run_id | `07ddc074-9ab2-4b16-8957-acbf94012144` |
| ticker | MSFT |
| source artifact | `outputs/runs/07ddc074-.../unclassified_findings.json` (`unclassified_findings.v1`) |
| John's earlier observed count | ≈699 |
| **Audited count (exact)** | **699** — an exact match, not an approximation |
| audited_count == source artifact total_count | **True** |

This is the same MSFT run already used as this session's QA Item 1 regression fixture — a real, previously-completed, zero-Provider offline run, not fabricated for this audit.

## Evidence 1 — Overall audit summary

```text
Neutral / Unclassified Audit — MSFT (07ddc074-9ab2-4b16-8957-acbf94012144)

Audited findings: 699

By agent (top 5 of 12):
1. fundamental_agent          — 140  (20.0%)
2. bear_researcher            —  93  (13.3%)
3. market_agent               —  91  (13.0%)
4. sentiment_agent            —  67  ( 9.6%)
5. news_agent                 —  65  ( 9.3%)
   ... 7 more agents, 12 total, sum = 699 (100%)

By reason (primary, mutually exclusive — sums to 699):
1. no_alpha_match              — 675  (96.6%)
2. no_ticker_specific_evidence —  20  ( 2.9%)
3. generic_background          —   3  ( 0.4%)
4. duplicate_supporting_text   —   1  ( 0.1%)
5. low_confidence              —   0  ( 0.0%, never populated — no formally defined threshold exists)
Unresolved (anomalous stance): 0
```

## By agent (full)

| Agent | Count | % of total |
|---|---:|---:|
| fundamental_agent | 140 | 20.03 |
| bear_researcher | 93 | 13.30 |
| market_agent | 91 | 13.02 |
| sentiment_agent | 67 | 9.59 |
| news_agent | 65 | 9.30 |
| neutral_risk_analyst | 54 | 7.73 |
| aggressive_risk_analyst | 52 | 7.44 |
| bull_researcher | 52 | 7.44 |
| conservative_risk_analyst | 51 | 7.30 |
| portfolio_manager | 15 | 2.15 |
| research_manager | 13 | 1.86 |
| trader | 6 | 0.86 |

Sum = 699. No finding had a missing/invalid agent (`unknown_agent` bucket = 0 for this run — the check exists and is exercised by tests, just not triggered by this population).

## By reason

| Reason | finding_count (primary, mutually exclusive) | reason_occurrence_count (every applicable reason) |
|---|---:|---:|
| no_alpha_match | 675 | 675 |
| no_ticker_specific_evidence | 20 | 24 |
| generic_background | 3 | 3 |
| duplicate_supporting_text | 1 | 1 |
| low_confidence | 0 | 0 |

4 findings carry more than one applicable reason (all combining `no_ticker_specific_evidence` with a higher-priority primary reason) — `finding_count` assigns each to exactly one bucket using A3's own frozen priority order; `reason_occurrence_count` counts every applicable reason, which is why `no_ticker_specific_evidence`'s occurrence count (24) exceeds its finding count (20). Both sums reconcile exactly against the source artifact's own `reason_counts`.

**Interpretation:** `no_alpha_match` is overwhelmingly dominant (96.6%). Per the original A3 report (`a3_unclassified_findings_control_report.md`), this is a **known, expected** property of a deliberately strict Alpha Mapper (0.35 threshold), not a defect — a comparable NVDA run showed the same pattern (93% `no_alpha_match`). This audit does not treat that rate as something to "fix."

## Evidence 2 — Top repeated patterns

**Key finding: repetition is negligible.** Of 699 findings, only **6 (0.9%)** belong to any exactly-repeated pattern — the other **693 (99.1%) are fully unique text**. Only 3 distinct patterns repeat at all, each exactly twice:

| Rank | Pattern | Count | Main reason | Agents involved | Classification |
|---|---|---:|---|---|---|
| 1 | "That convergence, combined with real fundamental strength and non‑extreme forward valuation, supports a constructive but disciplined stance…" | 2 | no_alpha_match | portfolio_manager, research_manager | unclear |
| 2 | "The prediction markets show an 85% probability of no Fed rate cuts in 2026" | 2 | no_alpha_match | conservative_risk_analyst, neutral_risk_analyst | unclear |
| 3 | "They differ only on timing" | 2 | no_alpha_match | portfolio_manager, research_manager | unclear |

All 3 are cross-agent (e.g. `portfolio_manager` echoing `research_manager`'s own debate synthesis) — consistent with normal debate-stage summarization, not prompt-template boilerplate. Below the 3-occurrence threshold this audit uses for a confident `prompt_redundancy` label, so each is honestly marked **`unclear`** rather than guessed.

**Answering John's question directly: "Are many of them repeated variants of the same pattern?" → No, not for this run.** The large unclassified count is not explained by duplicated/boilerplate output; it is explained by 675 individually-distinct claims that a deliberately strict Alpha Mapper did not match to any of the 10 canonical Alphas.

## Ticker-specificity audit

| Metric | Value |
|---|---:|
| Findings with `no_ticker_specific_evidence` as primary reason | 20 (2.86%) |
| Top source agents | fundamental_agent 7, sentiment_agent 4, aggressive_risk_analyst 2, bull_researcher 2, news_agent 2, bear_researcher 1, market_agent 1, neutral_risk_analyst 1 |
| Top repeated patterns within this subset | none (all 20 are distinct text) |

A small, genuinely secondary contributor (2.9% of the total).

## Duplicate audit

| Metric | Value |
|---|---:|
| `duplicate_supporting_text` findings | 1 (0.14%) |
| Unique Evidence Fact groups involved | 1 |
| Largest duplicate cluster | 1 member (evidence_fact_group_id `34732088e916bd857e5cf524`) |
| Top duplicate-generating agent | conservative_risk_analyst (1) |

Duplication (as already defined by the existing Evidence Fact Index) is essentially a non-factor for this run.

## Possible taxonomy gaps

**None surfaced.** The only candidates this audit would flag are `no_alpha_match` patterns repeating ≥3 times — none exist in this run (the 3 repeated patterns above all cap at 2, below the threshold). This is an honest "no evidence found," not a claim that no gap could possibly exist — see Non-Goals: no new Alpha IDs were created or considered, and no record was remapped.

## Evidence 3 — Prompt recommendations (recommendation only — not implemented)

| Target agent | Observed issue | Evidence count | Suggested fix |
|---|---|---:|---|
| fundamental_agent | Repeated findings lacking ticker-specific language (`no_ticker_specific_evidence`) | 7 | Prompt the agent to name the specific ticker/company explicitly in each extracted finding rather than relying on implicit context from the surrounding report. |

Only **one** recommendation clears this audit's evidence-support bar (≥5 occurrences for one agent×problem combination). `generic_background` (3 total, spread thin) and pattern-level `prompt_redundancy` (no pattern reaches the 3-occurrence threshold) do not — this audit does not manufacture additional recommendations to pad the list.

**`Prompt changes implemented = NO`** for all of the above — every entry carries `"status": "recommendation_only"` in the JSON artifact.

## Healthy vs. potentially-avoidable split

Attempted per task §12, using only Top-N repeated-pattern membership (a deterministic, conservative lower bound — never a claimed split of the full 699):

- Healthy-uncertainty sample: 0
- Potentially-avoidable sample: 0
- **All 3 repeated patterns are `unclear`**, so neither bucket gets a confident sample from pattern data alone.

**Explicit statement (per task §12's own escape hatch): a safe, deterministic full-population healthy-vs-avoidable split could not be established for this run.** The by-reason and by-pattern breakdowns above are the complete, exact, defensible accounting; a coarser "good/bad" label would require semantic judgment this audit deliberately does not attempt.

## Evidence 4 — UI still limited to Top 20

Real browser check (Playwright) against the live running frontend + backend, real MSFT run:

```
count note: "Showing 20 of 699"
rendered finding cards: 20
PASS - exactly 20 cards rendered
PASS - total count 699 shown
```

Screenshot captured (`ResearchRunPage`, "Unclassified findings (699)" section): reason-count summary strip, 20 individual finding cards, "Download full audit (699)" link. Full audit available internally + UI stays concise — confirmed, not just asserted.

## What this audit did **not** do

- Did not lower the Alpha Mapper's 0.35 threshold, or any other B1–B4 threshold.
- Did not reinterpret any `neutral_background`/`mentions_alpha` claim as supporting evidence.
- Did not treat the 1 `duplicate_supporting_text` finding as independent evidence.
- Did not create, rename, or remap to any Alpha ID.
- Did not call an LLM/Provider to cluster or re-judge any finding (0 Provider calls, 0 TradingAgents calls — see JSON `provider_calls`/`tradingagents_calls`).
- Did not edit any TradingAgents agent prompt — every suggested fix is `status: "recommendation_only"`.
- Did not change the UI's Top-20 display behavior.

## Full machine-readable artifact

`docs/audit_artifacts/neutral_unclassified_audit_msft_07ddc074.json` (schema `neutral_unclassified_audit.v1`) — contains every field above plus the complete `unclassified_by_agent_and_reason` cross-tab, per-pattern `example_claim_ids`, and the exact `pattern_summary` counts. Regenerable via:

```bash
python scripts/build_neutral_unclassified_audit.py \
  --run-id 07ddc074-9ab2-4b16-8957-acbf94012144 \
  --output docs/audit_artifacts/neutral_unclassified_audit_msft_07ddc074.json
```

Verified deterministic: two independent runs of this exact command produce byte-identical output (excluding `generated_at`).
