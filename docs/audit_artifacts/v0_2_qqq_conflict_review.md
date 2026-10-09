# QQQ Conflict Evidence Review

Authority: `docs/audit_artifacts/v0_2_john_frozen_gold_baseline.yaml` — **unchanged**. Full detail in `v0_2_qqq_conflict_review.json`.

QQQ is Formal Gold. Current main conflict: **A301__A304**. Frozen allowed baseline (unchanged): `A001__A501`, `A003__A501`, `A304__A601`. A301__A304 is **not** in the baseline and is **not** added by this review.

## 1. What evidence supports A301?

11 of A301's 17 evidence-fact groups carry a `supports_alpha` stance, from 5 agents. Concrete, named, multi-constituent evidence: Apple/AAPL foldable-iPhone ASP expansion ("Direct tailwind to largest QQQ weight"), Oracle's $664B contracted backlog, Micron's record guidance, Dell/HPE double-digit moves. Several other supporting groups are vaguer debate-process assertions with no company attribution.

## 2. Is the A301 evidence genuinely QQQ/ETF-level, or primarily one company?

**Genuinely multi-constituent.** At least 6 distinct named entities appear: Apple, Skyworks, Oracle, Dell, HPE, Micron — spanning consumer hardware and enterprise/cloud infrastructure. `news_agent` explicitly frames this at the ETF level. Not a single-company concentration.

## 3. What evidence supports A304?

43 of A304's 54 evidence-fact groups carry a `supports_alpha` stance — the richest, most cross-corroborated evidence base of any Alpha in this run, from 10 distinct agents.

## 4. Why was A301__A304 selected as the main conflict?

A301 and A304 are the two most heavily evidenced, genuinely opposing alphas in this run, and A301__A304 is a canonical taxonomy conflict pair (confirmed directly from `alpha_taxonomy_v1.yaml`). The Conflict Detector's admission of this pair is a mechanically well-supported outcome of the evidence actually present — not an anomaly, a bug, or a forced result.

## 5. Is the evidence sufficient to justify a RULE_CHANGE_RECOMMENDATION?

**Yes — evidence is sufficient.** A301__A304 is a canonical pair with substantial, genuine, cross-agent, multi-constituent evidence on both sides, and is this run's actual, mechanically-justified main conflict.

**Output: `RULE_CHANGE_RECOMMENDATION`** — for later human/product-owner decision only. This does **not** retroactively count as an allowed Gold PASS, and the frozen baseline is **not** modified.

**QQQ conflict status: `REVIEW_REQUIRED`.**
