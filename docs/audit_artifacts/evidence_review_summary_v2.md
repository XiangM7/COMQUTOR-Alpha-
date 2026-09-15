# Evidence Review Summary v2

Independent audit / documentation only. **Provider calls: 0. TradingAgents calls: 0. No ticker run. No production code changed.**

## Formal Metrics

| Metric | Result | Threshold | Status |
|---|---:|---:|---|
| Alpha Match Accuracy | 166 / 200 = 83.00% | >=80% | PASS |
| Polarity Accuracy | 52 / 61 = 85.25% | >=80% | PASS |
| Critical Support/Opposition Reversal | 0 | 0 | PASS |

These are the same numbers already in this file's `acceptance_results`/`formal_metrics` (John-approved 2026-09-01T01:02:54+00:00) -- **unchanged**. Everything below independently reproduces them, row by row, directly from the frozen source CSVs.

## Evaluation Population

- Total reviewed sentences: **200**
- Alpha-match eligible: **200** (every reviewed sentence is alpha-match eligible)
- Alpha-match correct: **166**
- Alpha-match incorrect: **34**
- Polarity eligible: **61**
- Polarity correct: **52**
- Polarity incorrect: **9**
- Critical reversals (eligible): **0**
- Ambiguous/excluded: **1** (holdout5-005)
- Human review status / approval authority: Blind Holdout #5, independent model reviewer (session-isolated from production inference -- not a human reviewer; see `review_source_note` in this file's history), frozen before any system output existed. Approved by John, 2026-09-01T01:02:54+00:00.

### Why the polarity denominator (61) is smaller than the Alpha denominator (200)

All 200 sentences are scored for Alpha-match. Only sentences the reviewer judged `human_material_alpha_fit=true` (i.e. the sentence actually asserts a mechanism-relevant claim, not just a NONE/background remark) are eligible for polarity scoring at all -- that yields **62** material-fit rows. Of those 62, exactly one (`holdout5-005`) carries a formal adjudication outcome of `BOTH_REASONABLE_AMBIGUOUS` (a genuine, reasonable-on-both-sides directional disagreement between the reviewer and the system on a negatively-phrased sentence -- see the Excluded/Ambiguous section below) and is excluded from polarity/reversal acceptance scoring under a general eligibility rule, leaving **61** eligible rows. Every non-material-fit row (138 of them) and the one excluded row (`holdout5-005`) still appear in the full row table below with `Polarity eligible: No` / `NOT_ELIGIBLE`, never silently dropped.

---

## Full Sentence-Level Review (all 200 rows)

### Review Row holdout5-001

- Ticker: AMD
- Run ID: `66794ad5-b3a9-4fcc-aa5f-7a6d7957b7c1`
- Source / agent role: aggressive_risk_analyst
- Evidence ID / claim ID: `66794ad5-b3a9-4fcc-aa5f-7a6d7957b7c1:aggressive_risk_analyst:risk_debate_state.aggressive_history:claim:37`
- Original sentence:
  > These analysts are seeing something in the forward order book, in the hyperscaler spending commitments, and in AMD's competitive positioning that justifies dramatically higher price targets.

- Expected Alpha: A103
- System-mapped Alpha: A101
- Alpha Match: **FAIL**

- Expected polarity: supports_alpha
- System polarity: supports_alpha
- Polarity eligible: Yes
- Polarity Match: **PASS**
- Critical support/opposition reversal: No

- Human review judgment: DIRECTIONALLY_CLEAR (no formal adjudication record; frozen blind label stands as ground truth)
- Review note / rationale: Hyperscaler spending commitments and forward order book directly reference AI infrastructure buildout demand supporting AMD.
- Source authority: `docs/audit_artifacts/item2_blind_holdout5_{frozen.csv,review_frozen.csv,comparison.csv}`

---

### Review Row holdout5-002

- Ticker: AMD
- Run ID: `66794ad5-b3a9-4fcc-aa5f-7a6d7957b7c1`
- Source / agent role: bear_researcher
- Evidence ID / claim ID: `66794ad5-b3a9-4fcc-aa5f-7a6d7957b7c1:bear_researcher:investment_debate_state.bear_history:claim:10`
- Original sentence:
  > Think about what happened this week.

- Expected Alpha: NONE
- System-mapped Alpha: NONE
- Alpha Match: **PASS**

- Expected polarity: NOT_ELIGIBLE
- System polarity: NOT_ELIGIBLE
- Polarity eligible: No
- Polarity Match: **NOT_ELIGIBLE**
- Critical support/opposition reversal: No

- Human review judgment: NOT_MATERIAL_ALPHA_FIT
- Review note / rationale: Purely transitional phrase; no economic mechanism or substantive content present.
- Source authority: `docs/audit_artifacts/item2_blind_holdout5_{frozen.csv,review_frozen.csv,comparison.csv}`

---

### Review Row holdout5-003

- Ticker: AMD
- Run ID: `66794ad5-b3a9-4fcc-aa5f-7a6d7957b7c1`
- Source / agent role: bear_researcher
- Evidence ID / claim ID: `66794ad5-b3a9-4fcc-aa5f-7a6d7957b7c1:bear_researcher:investment_debate_state.bear_history:claim:53`
- Original sentence:
  > AMD's entire bull case rests on continued hyperscaler AI infrastructure spending.

- Expected Alpha: A103
- System-mapped Alpha: A101
- Alpha Match: **FAIL**

- Expected polarity: supports_alpha
- System polarity: mentions_alpha
- Polarity eligible: Yes
- Polarity Match: **FAIL**
- Critical support/opposition reversal: No

- Human review judgment: DIRECTIONALLY_CLEAR (no formal adjudication record; frozen blind label stands as ground truth)
- Review note / rationale: Explicitly states AMD bull case depends on continued hyperscaler AI infrastructure spending, directly naming the A103 mechanism.
- Source authority: `docs/audit_artifacts/item2_blind_holdout5_{frozen.csv,review_frozen.csv,comparison.csv}`

---

### Review Row holdout5-004

- Ticker: AMD
- Run ID: `66794ad5-b3a9-4fcc-aa5f-7a6d7957b7c1`
- Source / agent role: conservative_risk_analyst
- Evidence ID / claim ID: `66794ad5-b3a9-4fcc-aa5f-7a6d7957b7c1:conservative_risk_analyst:risk_debate_state.conservative_history:claim:34`
- Original sentence:
  > One inventory write-down like the one that caused AMD's Q2 2025 gross margins to crater to 39.8 percent and operating income to turn negative would not just miss the quarter.

- Expected Alpha: A304
- System-mapped Alpha: A201
- Alpha Match: **FAIL**

- Expected polarity: supports_alpha
- System polarity: supports_alpha
- Polarity eligible: Yes
- Polarity Match: **PASS**
- Critical support/opposition reversal: No

- Human review judgment: DIRECTIONALLY_CLEAR (no formal adjudication record; frozen blind label stands as ground truth)
- Review note / rationale: Inventory write-down causing margin collapse and negative operating income signals downside risk to fundamentals, supporting multiple compression thesis.
- Source authority: `docs/audit_artifacts/item2_blind_holdout5_{frozen.csv,review_frozen.csv,comparison.csv}`

---

### Review Row holdout5-005

- Ticker: AMD
- Run ID: `66794ad5-b3a9-4fcc-aa5f-7a6d7957b7c1`
- Source / agent role: conservative_risk_analyst
- Evidence ID / claim ID: `66794ad5-b3a9-4fcc-aa5f-7a6d7957b7c1:conservative_risk_analyst:risk_debate_state.conservative_history:claim:56`
- Original sentence:
  > This is not independent fundamental research arriving at $1,250 through bottom-up earnings modeling.

- Expected Alpha: A601
- System-mapped Alpha: NONE
- Alpha Match: **FAIL**

- Expected polarity: supports_alpha
- System polarity: opposes_alpha
- Polarity eligible: No
- Polarity Match: **NOT_ELIGIBLE**
- Critical support/opposition reversal: Yes

- Human review judgment: AMBIGUOUS (formally adjudicated: BOTH_REASONABLE_AMBIGUOUS)
- Review note / rationale: Implies price targets are narrative/sentiment-driven rather than fundamental, directly invoking reflexive attention-flow mechanism of A601.
- Source authority: `docs/audit_artifacts/item2_blind_holdout5_{frozen.csv,review_frozen.csv,comparison.csv}`

---

### Review Row holdout5-006

- Ticker: AMD
- Run ID: `66794ad5-b3a9-4fcc-aa5f-7a6d7957b7c1`
- Source / agent role: market_agent
- Evidence ID / claim ID: `66794ad5-b3a9-4fcc-aa5f-7a6d7957b7c1:market_agent:market_report:claim:3`
- Original sentence:
  > The stock has experienced significant volatility over the past 12 weeks:

- Expected Alpha: NONE
- System-mapped Alpha: NONE
- Alpha Match: **PASS**

- Expected polarity: NOT_ELIGIBLE
- System polarity: NOT_ELIGIBLE
- Polarity eligible: No
- Polarity Match: **NOT_ELIGIBLE**
- Critical support/opposition reversal: No

- Human review judgment: NOT_MATERIAL_ALPHA_FIT
- Review note / rationale: Generic statement about stock volatility; no canonical Alpha mechanism materially present.
- Source authority: `docs/audit_artifacts/item2_blind_holdout5_{frozen.csv,review_frozen.csv,comparison.csv}`

---

### Review Row holdout5-007

- Ticker: AMD
- Run ID: `66794ad5-b3a9-4fcc-aa5f-7a6d7957b7c1`
- Source / agent role: neutral_risk_analyst
- Evidence ID / claim ID: `66794ad5-b3a9-4fcc-aa5f-7a6d7957b7c1:neutral_risk_analyst:risk_debate_state.neutral_history:claim:2`
- Original sentence:
  > To the aggressive analyst first.

- Expected Alpha: NONE
- System-mapped Alpha: NONE
- Alpha Match: **PASS**

- Expected polarity: NOT_ELIGIBLE
- System polarity: NOT_ELIGIBLE
- Polarity eligible: No
- Polarity Match: **NOT_ELIGIBLE**
- Critical support/opposition reversal: No

- Human review judgment: NOT_MATERIAL_ALPHA_FIT
- Review note / rationale: Transitional introductory phrase only; no substantive economic mechanism expressed.
- Source authority: `docs/audit_artifacts/item2_blind_holdout5_{frozen.csv,review_frozen.csv,comparison.csv}`

---

### Review Row holdout5-008

- Ticker: AMD
- Run ID: `66794ad5-b3a9-4fcc-aa5f-7a6d7957b7c1`
- Source / agent role: news_agent
- Evidence ID / claim ID: `66794ad5-b3a9-4fcc-aa5f-7a6d7957b7c1:news_agent:news_report:claim:3`
- Original sentence:
  > Baird doubled its price target on AMD to $1,250

- Expected Alpha: NONE
- System-mapped Alpha: A101
- Alpha Match: **FAIL**

- Expected polarity: NOT_ELIGIBLE
- System polarity: NOT_ELIGIBLE
- Polarity eligible: No
- Polarity Match: **NOT_ELIGIBLE**
- Critical support/opposition reversal: No

- Human review judgment: NOT_MATERIAL_ALPHA_FIT
- Review note / rationale: Analyst price target action alone; no causal economic mechanism stated, only a target number.
- Source authority: `docs/audit_artifacts/item2_blind_holdout5_{frozen.csv,review_frozen.csv,comparison.csv}`

---

### Review Row holdout5-009

- Ticker: AMD
- Run ID: `66794ad5-b3a9-4fcc-aa5f-7a6d7957b7c1`
- Source / agent role: portfolio_manager
- Evidence ID / claim ID: `66794ad5-b3a9-4fcc-aa5f-7a6d7957b7c1:portfolio_manager:final_trade_decision:claim:4`
- Original sentence:
  > Time horizon is 6–12 months.

- Expected Alpha: NONE
- System-mapped Alpha: NONE
- Alpha Match: **PASS**

- Expected polarity: NOT_ELIGIBLE
- System polarity: NOT_ELIGIBLE
- Polarity eligible: No
- Polarity Match: **NOT_ELIGIBLE**
- Critical support/opposition reversal: No

- Human review judgment: NOT_MATERIAL_ALPHA_FIT
- Review note / rationale: Time horizon disclosure only; no Alpha mechanism present.
- Source authority: `docs/audit_artifacts/item2_blind_holdout5_{frozen.csv,review_frozen.csv,comparison.csv}`

---

### Review Row holdout5-010

- Ticker: AMD
- Run ID: `66794ad5-b3a9-4fcc-aa5f-7a6d7957b7c1`
- Source / agent role: portfolio_manager
- Evidence ID / claim ID: `66794ad5-b3a9-4fcc-aa5f-7a6d7957b7c1:portfolio_manager:final_trade_decision:claim:45`
- Original sentence:
  > Downgrade to Underweight/Sell if gross margins revert toward 40% territory or confirmed hyperscaler capex reduction (not moderation) affects AMD's order book.

- Expected Alpha: A103
- System-mapped Alpha: A103
- Alpha Match: **PASS**

- Expected polarity: mentions_alpha
- System polarity: mentions_alpha
- Polarity eligible: Yes
- Polarity Match: **PASS**
- Critical support/opposition reversal: No

- Human review judgment: DIRECTIONALLY_CLEAR (no formal adjudication record; frozen blind label stands as ground truth)
- Review note / rationale: Downgrade triggers reference hyperscaler capex reduction affecting order book, discussing AI infrastructure mechanism without clear directional stance.
- Source authority: `docs/audit_artifacts/item2_blind_holdout5_{frozen.csv,review_frozen.csv,comparison.csv}`

---

### Review Row holdout5-011

- Ticker: AMD
- Run ID: `66794ad5-b3a9-4fcc-aa5f-7a6d7957b7c1`
- Source / agent role: research_manager
- Evidence ID / claim ID: `66794ad5-b3a9-4fcc-aa5f-7a6d7957b7c1:research_manager:investment_plan:claim:15`
- Original sentence:
  > And the 200-day SMA mean-reversion argument ignores that lagging indicators tell you where the stock was, not where a fundamentally re-rated business should be.

- Expected Alpha: NONE
- System-mapped Alpha: NONE
- Alpha Match: **PASS**

- Expected polarity: NOT_ELIGIBLE
- System polarity: NOT_ELIGIBLE
- Polarity eligible: No
- Polarity Match: **NOT_ELIGIBLE**
- Critical support/opposition reversal: No

- Human review judgment: NOT_MATERIAL_ALPHA_FIT
- Review note / rationale: Argues against 200-day SMA mean-reversion; technical indicator critique only, no canonical Alpha mechanism.
- Source authority: `docs/audit_artifacts/item2_blind_holdout5_{frozen.csv,review_frozen.csv,comparison.csv}`

---

### Review Row holdout5-012

- Ticker: AMD
- Run ID: `66794ad5-b3a9-4fcc-aa5f-7a6d7957b7c1`
- Source / agent role: sentiment_agent
- Evidence ID / claim ID: `66794ad5-b3a9-4fcc-aa5f-7a6d7957b7c1:sentiment_agent:sentiment_report:claim:27`
- Original sentence:
  > Bearish/cautionary unlabeled highlights (high-signal despite no tag):

- Expected Alpha: NONE
- System-mapped Alpha: NONE
- Alpha Match: **PASS**

- Expected polarity: NOT_ELIGIBLE
- System polarity: NOT_ELIGIBLE
- Polarity eligible: No
- Polarity Match: **NOT_ELIGIBLE**
- Critical support/opposition reversal: No

- Human review judgment: NOT_MATERIAL_ALPHA_FIT
- Review note / rationale: Section header with no substantive content; no canonical Alpha mechanism present.
- Source authority: `docs/audit_artifacts/item2_blind_holdout5_{frozen.csv,review_frozen.csv,comparison.csv}`

---

### Review Row holdout5-013

- Ticker: AMD
- Run ID: `b71765a0-1c9f-435a-a5f7-4ce0ea8d28a6`
- Source / agent role: bear_researcher
- Evidence ID / claim ID: `b71765a0-1c9f-435a-a5f7-4ce0ea8d28a6:bear_researcher:investment_debate_state.bear_history:claim:40`
- Original sentence:
  > The bull calls this "a feature." I call it a warning sign that AMD's premium is based on hope, not proven market share.

- Expected Alpha: A304
- System-mapped Alpha: A304
- Alpha Match: **PASS**

- Expected polarity: supports_alpha
- System polarity: supports_alpha
- Polarity eligible: Yes
- Polarity Match: **PASS**
- Critical support/opposition reversal: No

- Human review judgment: DIRECTIONALLY_CLEAR (no formal adjudication record; frozen blind label stands as ground truth)
- Review note / rationale: AMD premium based on hope not proven share; valuation risk without fundamental justification supports multiple compression thesis.
- Source authority: `docs/audit_artifacts/item2_blind_holdout5_{frozen.csv,review_frozen.csv,comparison.csv}`

---

### Review Row holdout5-014

- Ticker: AMD
- Run ID: `b71765a0-1c9f-435a-a5f7-4ce0ea8d28a6`
- Source / agent role: bear_researcher
- Evidence ID / claim ID: `b71765a0-1c9f-435a-a5f7-4ce0ea8d28a6:bear_researcher:investment_debate_state.bear_history:claim:67`
- Original sentence:
  > The bull says "buy the correction." I say: with this volatility, you're not buying a correction, you're buying a lottery ticket.

- Expected Alpha: NONE
- System-mapped Alpha: NONE
- Alpha Match: **PASS**

- Expected polarity: NOT_ELIGIBLE
- System polarity: NOT_ELIGIBLE
- Polarity eligible: No
- Polarity Match: **NOT_ELIGIBLE**
- Critical support/opposition reversal: No

- Human review judgment: NOT_MATERIAL_ALPHA_FIT
- Review note / rationale: Generic bearish sentiment about volatility and risk; no specific canonical Alpha mechanism expressed.
- Source authority: `docs/audit_artifacts/item2_blind_holdout5_{frozen.csv,review_frozen.csv,comparison.csv}`

---

### Review Row holdout5-015

- Ticker: AMD
- Run ID: `b71765a0-1c9f-435a-a5f7-4ce0ea8d28a6`
- Source / agent role: bear_researcher
- Evidence ID / claim ID: `b71765a0-1c9f-435a-a5f7-4ce0ea8d28a6:bear_researcher:investment_debate_state.bear_history:claim:85`
- Original sentence:
  > The margin for error is razor-thin.

- Expected Alpha: NONE
- System-mapped Alpha: NONE
- Alpha Match: **PASS**

- Expected polarity: NOT_ELIGIBLE
- System polarity: NOT_ELIGIBLE
- Polarity eligible: No
- Polarity Match: **NOT_ELIGIBLE**
- Critical support/opposition reversal: No

- Human review judgment: NOT_MATERIAL_ALPHA_FIT
- Review note / rationale: Generic cautionary statement with no causal or economic mechanism; too vague for any Alpha.
- Source authority: `docs/audit_artifacts/item2_blind_holdout5_{frozen.csv,review_frozen.csv,comparison.csv}`

---

### Review Row holdout5-016

- Ticker: AMD
- Run ID: `b71765a0-1c9f-435a-a5f7-4ce0ea8d28a6`
- Source / agent role: bull_researcher
- Evidence ID / claim ID: `b71765a0-1c9f-435a-a5f7-4ce0ea8d28a6:bull_researcher:investment_debate_state.bull_history:claim:103`
- Original sentence:
  > Microsoft Announcement: Baird's 155% upside target hinges on a "surprise Microsoft announcement" — a potential game-changer.

- Expected Alpha: A301
- System-mapped Alpha: A601
- Alpha Match: **FAIL**

- Expected polarity: supports_alpha
- System polarity: mentions_alpha
- Polarity eligible: Yes
- Polarity Match: **FAIL**
- Critical support/opposition reversal: No

- Human review judgment: DIRECTIONALLY_CLEAR (no formal adjudication record; frozen blind label stands as ground truth)
- Review note / rationale: Baird upside target hinges on potential Microsoft partnership announcement as a demand/revenue catalyst for AMD.
- Source authority: `docs/audit_artifacts/item2_blind_holdout5_{frozen.csv,review_frozen.csv,comparison.csv}`

---

### Review Row holdout5-017

- Ticker: AMD
- Run ID: `b71765a0-1c9f-435a-a5f7-4ce0ea8d28a6`
- Source / agent role: bull_researcher
- Evidence ID / claim ID: `b71765a0-1c9f-435a-a5f7-4ce0ea8d28a6:bull_researcher:investment_debate_state.bull_history:claim:41`
- Original sentence:
  > The market is paying a premium for growth, but it's a growth-adjusted fair value.

- Expected Alpha: A304
- System-mapped Alpha: NONE
- Alpha Match: **FAIL**

- Expected polarity: mentions_alpha
- System polarity: opposes_alpha
- Polarity eligible: Yes
- Polarity Match: **FAIL**
- Critical support/opposition reversal: No

- Human review judgment: DIRECTIONALLY_CLEAR (no formal adjudication record; frozen blind label stands as ground truth)
- Review note / rationale: Market paying growth premium but framed as fair value; discusses valuation without clear supportive or opposing stance.
- Source authority: `docs/audit_artifacts/item2_blind_holdout5_{frozen.csv,review_frozen.csv,comparison.csv}`

---

### Review Row holdout5-018

- Ticker: AMD
- Run ID: `b71765a0-1c9f-435a-a5f7-4ce0ea8d28a6`
- Source / agent role: conservative_risk_analyst
- Evidence ID / claim ID: `b71765a0-1c9f-435a-a5f7-4ce0ea8d28a6:conservative_risk_analyst:risk_debate_state.conservative_history:claim:9`
- Original sentence:
  > The RSI at 47.00 is below the 50 midline, which is not a sign of strength; it is a sign of a market that is struggling to find buyers.

- Expected Alpha: NONE
- System-mapped Alpha: NONE
- Alpha Match: **PASS**

- Expected polarity: NOT_ELIGIBLE
- System polarity: NOT_ELIGIBLE
- Polarity eligible: No
- Polarity Match: **NOT_ELIGIBLE**
- Critical support/opposition reversal: No

- Human review judgment: NOT_MATERIAL_ALPHA_FIT
- Review note / rationale: RSI reading below 50 midline; technical indicator only, no canonical Alpha mechanism present.
- Source authority: `docs/audit_artifacts/item2_blind_holdout5_{frozen.csv,review_frozen.csv,comparison.csv}`

---

### Review Row holdout5-019

- Ticker: AMD
- Run ID: `b71765a0-1c9f-435a-a5f7-4ce0ea8d28a6`
- Source / agent role: fundamental_agent
- Evidence ID / claim ID: `b71765a0-1c9f-435a-a5f7-4ce0ea8d28a6:fundamental_agent:fundamentals_report:claim:104`
- Original sentence:
  > Category: Profitability; Metric: EPS (TTM); Value: $3.01; Assessment: Doubled YoY

- Expected Alpha: A301
- System-mapped Alpha: A301
- Alpha Match: **PASS**

- Expected polarity: supports_alpha
- System polarity: supports_alpha
- Polarity eligible: Yes
- Polarity Match: **PASS**
- Critical support/opposition reversal: No

- Human review judgment: DIRECTIONALLY_CLEAR (no formal adjudication record; frozen blind label stands as ground truth)
- Review note / rationale: EPS doubled year-over-year signals strong profitability growth, supporting revenue expansion and earnings revision thesis.
- Source authority: `docs/audit_artifacts/item2_blind_holdout5_{frozen.csv,review_frozen.csv,comparison.csv}`

---

### Review Row holdout5-020

- Ticker: AMD
- Run ID: `b71765a0-1c9f-435a-a5f7-4ce0ea8d28a6`
- Source / agent role: market_agent
- Evidence ID / claim ID: `b71765a0-1c9f-435a-a5f7-4ce0ea8d28a6:market_agent:market_report:claim:3`
- Original sentence:
  > Bollinger: Middle $515.67, Upper $584.41, Lower $446.93

- Expected Alpha: NONE
- System-mapped Alpha: NONE
- Alpha Match: **PASS**

- Expected polarity: NOT_ELIGIBLE
- System polarity: NOT_ELIGIBLE
- Polarity eligible: No
- Polarity Match: **NOT_ELIGIBLE**
- Critical support/opposition reversal: No

- Human review judgment: NOT_MATERIAL_ALPHA_FIT
- Review note / rationale: Bollinger Band price levels only; pure technical indicator data with no canonical Alpha mechanism.
- Source authority: `docs/audit_artifacts/item2_blind_holdout5_{frozen.csv,review_frozen.csv,comparison.csv}`

---

### Review Row holdout5-021

- Ticker: AMD
- Run ID: `b71765a0-1c9f-435a-a5f7-4ce0ea8d28a6`
- Source / agent role: market_agent
- Evidence ID / claim ID: `b71765a0-1c9f-435a-a5f7-4ce0ea8d28a6:market_agent:market_report:claim:58`
- Original sentence:
  > MACD is deeply negative, though the histogram is decelerating.

- Expected Alpha: NONE
- System-mapped Alpha: NONE
- Alpha Match: **PASS**

- Expected polarity: NOT_ELIGIBLE
- System polarity: NOT_ELIGIBLE
- Polarity eligible: No
- Polarity Match: **NOT_ELIGIBLE**
- Critical support/opposition reversal: No

- Human review judgment: NOT_MATERIAL_ALPHA_FIT
- Review note / rationale: Pure technical indicator reading; no canonical Alpha mechanism present
- Source authority: `docs/audit_artifacts/item2_blind_holdout5_{frozen.csv,review_frozen.csv,comparison.csv}`

---

### Review Row holdout5-022

- Ticker: AMD
- Run ID: `b71765a0-1c9f-435a-a5f7-4ce0ea8d28a6`
- Source / agent role: neutral_risk_analyst
- Evidence ID / claim ID: `b71765a0-1c9f-435a-a5f7-4ce0ea8d28a6:neutral_risk_analyst:risk_debate_state.neutral_history:claim:41`
- Original sentence:
  > That catalyst is the earnings event on August 4.

- Expected Alpha: NONE
- System-mapped Alpha: NONE
- Alpha Match: **PASS**

- Expected polarity: NOT_ELIGIBLE
- System polarity: NOT_ELIGIBLE
- Polarity eligible: No
- Polarity Match: **NOT_ELIGIBLE**
- Critical support/opposition reversal: No

- Human review judgment: NOT_MATERIAL_ALPHA_FIT
- Review note / rationale: Generic event calendar reference; no causal Alpha mechanism expressed
- Source authority: `docs/audit_artifacts/item2_blind_holdout5_{frozen.csv,review_frozen.csv,comparison.csv}`

---

### Review Row holdout5-023

- Ticker: AMD
- Run ID: `b71765a0-1c9f-435a-a5f7-4ce0ea8d28a6`
- Source / agent role: portfolio_manager
- Evidence ID / claim ID: `b71765a0-1c9f-435a-a5f7-4ce0ea8d28a6:portfolio_manager:final_trade_decision:claim:13`
- Original sentence:
  > The prudent action is to hold the existing position, respect the binary nature of the event, and build exposure only at a level that offers a genuine margin of safety post-earnings.

- Expected Alpha: NONE
- System-mapped Alpha: NONE
- Alpha Match: **PASS**

- Expected polarity: NOT_ELIGIBLE
- System polarity: NOT_ELIGIBLE
- Polarity eligible: No
- Polarity Match: **NOT_ELIGIBLE**
- Critical support/opposition reversal: No

- Human review judgment: NOT_MATERIAL_ALPHA_FIT
- Review note / rationale: Portfolio risk management advice around binary event; no canonical Alpha mechanism
- Source authority: `docs/audit_artifacts/item2_blind_holdout5_{frozen.csv,review_frozen.csv,comparison.csv}`

---

### Review Row holdout5-024

- Ticker: AMD
- Run ID: `b71765a0-1c9f-435a-a5f7-4ce0ea8d28a6`
- Source / agent role: research_manager
- Evidence ID / claim ID: `b71765a0-1c9f-435a-a5f7-4ce0ea8d28a6:research_manager:investment_plan:claim:53`
- Original sentence:
  > This aligns with the critical support level identified in the debate.

- Expected Alpha: NONE
- System-mapped Alpha: NONE
- Alpha Match: **PASS**

- Expected polarity: NOT_ELIGIBLE
- System polarity: NOT_ELIGIBLE
- Polarity eligible: No
- Polarity Match: **NOT_ELIGIBLE**
- Critical support/opposition reversal: No

- Human review judgment: NOT_MATERIAL_ALPHA_FIT
- Review note / rationale: Technical support level reference only; no canonical Alpha mechanism present
- Source authority: `docs/audit_artifacts/item2_blind_holdout5_{frozen.csv,review_frozen.csv,comparison.csv}`

---

### Review Row holdout5-025

- Ticker: AMD
- Run ID: `b71765a0-1c9f-435a-a5f7-4ce0ea8d28a6`
- Source / agent role: research_manager
- Evidence ID / claim ID: `b71765a0-1c9f-435a-a5f7-4ce0ea8d28a6:research_manager:investment_plan:claim:59`
- Original sentence:
  > 10-Year Treasury Yield: A sustained move higher would increase pressure on the stock's multiple.

- Expected Alpha: A304
- System-mapped Alpha: A304
- Alpha Match: **PASS**

- Expected polarity: supports_alpha
- System polarity: supports_alpha
- Polarity eligible: Yes
- Polarity Match: **PASS**
- Critical support/opposition reversal: No

- Human review judgment: DIRECTIONALLY_CLEAR (no formal adjudication record; frozen blind label stands as ground truth)
- Review note / rationale: Rising 10-year yield increasing pressure on stock multiple directly expresses multiple compression thesis
- Source authority: `docs/audit_artifacts/item2_blind_holdout5_{frozen.csv,review_frozen.csv,comparison.csv}`

---

### Review Row holdout5-026

- Ticker: GOOGL
- Run ID: `299bb6af-5217-422e-bd47-1b3b07c57192`
- Source / agent role: aggressive_risk_analyst
- Evidence ID / claim ID: `299bb6af-5217-422e-bd47-1b3b07c57192:aggressive_risk_analyst:risk_debate_state.aggressive_history:claim:13`
- Original sentence:
  > The sentiment data confirms the pivot: the dominant theme across news, StockTwits, and Reddit is that "AI capex is paying off," and Amazon's earnings "confirmed" it.

- Expected Alpha: A601
- System-mapped Alpha: A601
- Alpha Match: **PASS**

- Expected polarity: supports_alpha
- System polarity: supports_alpha
- Polarity eligible: Yes
- Polarity Match: **PASS**
- Critical support/opposition reversal: No

- Human review judgment: DIRECTIONALLY_CLEAR (no formal adjudication record; frozen blind label stands as ground truth)
- Review note / rationale: Dominant theme spreading across media and social platforms driving narrative shift; attention-flows mechanism present
- Source authority: `docs/audit_artifacts/item2_blind_holdout5_{frozen.csv,review_frozen.csv,comparison.csv}`

---

### Review Row holdout5-027

- Ticker: GOOGL
- Run ID: `299bb6af-5217-422e-bd47-1b3b07c57192`
- Source / agent role: aggressive_risk_analyst
- Evidence ID / claim ID: `299bb6af-5217-422e-bd47-1b3b07c57192:aggressive_risk_analyst:risk_debate_state.aggressive_history:claim:2`
- Original sentence:
  > Let me be direct with my colleagues on the other side of this table, because I think the conservative and neutral perspectives are dangerously anchored to a rearview mirror while the road ahead is wide open.

- Expected Alpha: NONE
- System-mapped Alpha: NONE
- Alpha Match: **PASS**

- Expected polarity: NOT_ELIGIBLE
- System polarity: NOT_ELIGIBLE
- Polarity eligible: No
- Polarity Match: **NOT_ELIGIBLE**
- Critical support/opposition reversal: No

- Human review judgment: NOT_MATERIAL_ALPHA_FIT
- Review note / rationale: Generic rhetorical framing of debate positions; no canonical Alpha mechanism expressed
- Source authority: `docs/audit_artifacts/item2_blind_holdout5_{frozen.csv,review_frozen.csv,comparison.csv}`

---

### Review Row holdout5-028

- Ticker: GOOGL
- Run ID: `299bb6af-5217-422e-bd47-1b3b07c57192`
- Source / agent role: bear_researcher
- Evidence ID / claim ID: `299bb6af-5217-422e-bd47-1b3b07c57192:bear_researcher:investment_debate_state.bear_history:claim:68`
- Original sentence:
  > The Narrative Is Not Shifting — It's Fracturing: The sentiment report shows a 7.2/10 bullish score, but that's driven by retail exuberance on StockTwits (9 bullish vs 2 bearish labeled posts).

- Expected Alpha: A601
- System-mapped Alpha: A601
- Alpha Match: **PASS**

- Expected polarity: mentions_alpha
- System polarity: mentions_alpha
- Polarity eligible: Yes
- Polarity Match: **PASS**
- Critical support/opposition reversal: No

- Human review judgment: DIRECTIONALLY_CLEAR (no formal adjudication record; frozen blind label stands as ground truth)
- Review note / rationale: Discusses retail-driven sentiment score and narrative fracturing; attention-flows mechanism present but contested
- Source authority: `docs/audit_artifacts/item2_blind_holdout5_{frozen.csv,review_frozen.csv,comparison.csv}`

---

### Review Row holdout5-029

- Ticker: GOOGL
- Run ID: `299bb6af-5217-422e-bd47-1b3b07c57192`
- Source / agent role: bull_researcher
- Evidence ID / claim ID: `299bb6af-5217-422e-bd47-1b3b07c57192:bull_researcher:investment_debate_state.bull_history:claim:74`
- Original sentence:
  > The Narrative Is Shifting: The sentiment data is clear: the "capex punishment" narrative is fading.

- Expected Alpha: A601
- System-mapped Alpha: A601
- Alpha Match: **PASS**

- Expected polarity: supports_alpha
- System polarity: supports_alpha
- Polarity eligible: Yes
- Polarity Match: **PASS**
- Critical support/opposition reversal: No

- Human review judgment: DIRECTIONALLY_CLEAR (no formal adjudication record; frozen blind label stands as ground truth)
- Review note / rationale: Narrative pivot from capex punishment to capex payoff directly expresses attention-driven narrative momentum mechanism
- Source authority: `docs/audit_artifacts/item2_blind_holdout5_{frozen.csv,review_frozen.csv,comparison.csv}`

---

### Review Row holdout5-030

- Ticker: GOOGL
- Run ID: `299bb6af-5217-422e-bd47-1b3b07c57192`
- Source / agent role: bull_researcher
- Evidence ID / claim ID: `299bb6af-5217-422e-bd47-1b3b07c57192:bull_researcher:investment_debate_state.bull_history:claim:86`
- Original sentence:
  > Gemini Pro Release: 91% probability of a major model release by August 31.

- Expected Alpha: A101
- System-mapped Alpha: A101
- Alpha Match: **PASS**

- Expected polarity: supports_alpha
- System polarity: supports_alpha
- Polarity eligible: Yes
- Polarity Match: **PASS**
- Critical support/opposition reversal: No

- Human review judgment: DIRECTIONALLY_CLEAR (no formal adjudication record; frozen blind label stands as ground truth)
- Review note / rationale: Major AI model release probability supports AI expansion and adoption demand thesis
- Source authority: `docs/audit_artifacts/item2_blind_holdout5_{frozen.csv,review_frozen.csv,comparison.csv}`

---

### Review Row holdout5-031

- Ticker: GOOGL
- Run ID: `299bb6af-5217-422e-bd47-1b3b07c57192`
- Source / agent role: bull_researcher
- Evidence ID / claim ID: `299bb6af-5217-422e-bd47-1b3b07c57192:bull_researcher:investment_debate_state.bull_history:claim:99`
- Original sentence:
  > The bear case rests on three pillars: a single quarter of negative FCF, a narrow AI benchmark race, and a forward P/E that is actually reasonable when adjusted for growth.

- Expected Alpha: A304
- System-mapped Alpha: A304
- Alpha Match: **PASS**

- Expected polarity: opposes_alpha
- System polarity: opposes_alpha
- Polarity eligible: Yes
- Polarity Match: **PASS**
- Critical support/opposition reversal: No

- Human review judgment: DIRECTIONALLY_CLEAR (no formal adjudication record; frozen blind label stands as ground truth)
- Review note / rationale: Forward P/E described as reasonable adjusted for growth, undermining multiple compression thesis
- Source authority: `docs/audit_artifacts/item2_blind_holdout5_{frozen.csv,review_frozen.csv,comparison.csv}`

---

### Review Row holdout5-032

- Ticker: GOOGL
- Run ID: `299bb6af-5217-422e-bd47-1b3b07c57192`
- Source / agent role: conservative_risk_analyst
- Evidence ID / claim ID: `299bb6af-5217-422e-bd47-1b3b07c57192:conservative_risk_analyst:risk_debate_state.conservative_history:claim:49`
- Original sentence:
  > On the "standing still is being short" argument: This is the most reckless statement in the aggressive case.

- Expected Alpha: NONE
- System-mapped Alpha: NONE
- Alpha Match: **PASS**

- Expected polarity: NOT_ELIGIBLE
- System polarity: NOT_ELIGIBLE
- Polarity eligible: No
- Polarity Match: **NOT_ELIGIBLE**
- Critical support/opposition reversal: No

- Human review judgment: NOT_MATERIAL_ALPHA_FIT
- Review note / rationale: Rhetorical critique of investment argument; no canonical Alpha mechanism materially present
- Source authority: `docs/audit_artifacts/item2_blind_holdout5_{frozen.csv,review_frozen.csv,comparison.csv}`

---

### Review Row holdout5-033

- Ticker: GOOGL
- Run ID: `299bb6af-5217-422e-bd47-1b3b07c57192`
- Source / agent role: conservative_risk_analyst
- Evidence ID / claim ID: `299bb6af-5217-422e-bd47-1b3b07c57192:conservative_risk_analyst:risk_debate_state.conservative_history:claim:7`
- Original sentence:
  > The claim that "CapEx is causing that revenue growth" is an assertion, not a proven fact.

- Expected Alpha: NONE
- System-mapped Alpha: A601
- Alpha Match: **FAIL**

- Expected polarity: NOT_ELIGIBLE
- System polarity: NOT_ELIGIBLE
- Polarity eligible: No
- Polarity Match: **NOT_ELIGIBLE**
- Critical support/opposition reversal: No

- Human review judgment: NOT_MATERIAL_ALPHA_FIT
- Review note / rationale: Epistemological critique of capex-revenue causation claim; no canonical Alpha mechanism expressed
- Source authority: `docs/audit_artifacts/item2_blind_holdout5_{frozen.csv,review_frozen.csv,comparison.csv}`

---

### Review Row holdout5-034

- Ticker: GOOGL
- Run ID: `299bb6af-5217-422e-bd47-1b3b07c57192`
- Source / agent role: conservative_risk_analyst
- Evidence ID / claim ID: `299bb6af-5217-422e-bd47-1b3b07c57192:conservative_risk_analyst:risk_debate_state.conservative_history:claim:8`
- Original sentence:
  > The data shows revenue growth of 24% YoY, but it also shows normalized earnings flat at $32B for three consecutive quarters.

- Expected Alpha: A301
- System-mapped Alpha: A301
- Alpha Match: **PASS**

- Expected polarity: mentions_alpha
- System polarity: mentions_alpha
- Polarity eligible: Yes
- Polarity Match: **PASS**
- Critical support/opposition reversal: No

- Human review judgment: DIRECTIONALLY_CLEAR (no formal adjudication record; frozen blind label stands as ground truth)
- Review note / rationale: Revenue growth strong at 24% YoY but normalized earnings flat; mixed signal on revenue expansion thesis
- Source authority: `docs/audit_artifacts/item2_blind_holdout5_{frozen.csv,review_frozen.csv,comparison.csv}`

---

### Review Row holdout5-035

- Ticker: GOOGL
- Run ID: `299bb6af-5217-422e-bd47-1b3b07c57192`
- Source / agent role: fundamental_agent
- Evidence ID / claim ID: `299bb6af-5217-422e-bd47-1b3b07c57192:fundamental_agent:fundamentals_report:claim:32`
- Original sentence:
  > The normalized income for Q2 2026 was $32.23 billion, which is more representative of underlying operating performance.

- Expected Alpha: NONE
- System-mapped Alpha: A301
- Alpha Match: **FAIL**

- Expected polarity: NOT_ELIGIBLE
- System polarity: NOT_ELIGIBLE
- Polarity eligible: No
- Polarity Match: **NOT_ELIGIBLE**
- Critical support/opposition reversal: No

- Human review judgment: NOT_MATERIAL_ALPHA_FIT
- Review note / rationale: Accounting normalization note; no causal Alpha mechanism materially expressed
- Source authority: `docs/audit_artifacts/item2_blind_holdout5_{frozen.csv,review_frozen.csv,comparison.csv}`

---

### Review Row holdout5-036

- Ticker: GOOGL
- Run ID: `299bb6af-5217-422e-bd47-1b3b07c57192`
- Source / agent role: fundamental_agent
- Evidence ID / claim ID: `299bb6af-5217-422e-bd47-1b3b07c57192:fundamental_agent:fundamentals_report:claim:51`
- Original sentence:
  > Growth trajectory: Revenue grew from $282.8B (FY2022) to $402.8B (FY2025), a CAGR of approximately 12.5%.

- Expected Alpha: A301
- System-mapped Alpha: A301
- Alpha Match: **PASS**

- Expected polarity: supports_alpha
- System polarity: supports_alpha
- Polarity eligible: Yes
- Polarity Match: **PASS**
- Critical support/opposition reversal: No

- Human review judgment: DIRECTIONALLY_CLEAR (no formal adjudication record; frozen blind label stands as ground truth)
- Review note / rationale: Multi-year revenue CAGR of 12.5% materially supports revenue expansion thesis
- Source authority: `docs/audit_artifacts/item2_blind_holdout5_{frozen.csv,review_frozen.csv,comparison.csv}`

---

### Review Row holdout5-037

- Ticker: GOOGL
- Run ID: `299bb6af-5217-422e-bd47-1b3b07c57192`
- Source / agent role: fundamental_agent
- Evidence ID / claim ID: `299bb6af-5217-422e-bd47-1b3b07c57192:fundamental_agent:fundamentals_report:claim:63`
- Original sentence:
  > The debt-to-equity ratio of 18.9 (as reported) reflects the recent debt issuance, though this remains manageable given the company's cash flows.

- Expected Alpha: NONE
- System-mapped Alpha: NONE
- Alpha Match: **PASS**

- Expected polarity: NOT_ELIGIBLE
- System polarity: NOT_ELIGIBLE
- Polarity eligible: No
- Polarity Match: **NOT_ELIGIBLE**
- Critical support/opposition reversal: No

- Human review judgment: NOT_MATERIAL_ALPHA_FIT
- Review note / rationale: Balance sheet leverage comment; no canonical Alpha mechanism materially present
- Source authority: `docs/audit_artifacts/item2_blind_holdout5_{frozen.csv,review_frozen.csv,comparison.csv}`

---

### Review Row holdout5-038

- Ticker: GOOGL
- Run ID: `299bb6af-5217-422e-bd47-1b3b07c57192`
- Source / agent role: neutral_risk_analyst
- Evidence ID / claim ID: `299bb6af-5217-422e-bd47-1b3b07c57192:neutral_risk_analyst:risk_debate_state.neutral_history:claim:17`
- Original sentence:
  > The ATR of 12.11 signals elevated volatility.

- Expected Alpha: NONE
- System-mapped Alpha: NONE
- Alpha Match: **PASS**

- Expected polarity: NOT_ELIGIBLE
- System polarity: NOT_ELIGIBLE
- Polarity eligible: No
- Polarity Match: **NOT_ELIGIBLE**
- Critical support/opposition reversal: No

- Human review judgment: NOT_MATERIAL_ALPHA_FIT
- Review note / rationale: ATR volatility metric only; no canonical Alpha causal mechanism expressed
- Source authority: `docs/audit_artifacts/item2_blind_holdout5_{frozen.csv,review_frozen.csv,comparison.csv}`

---

### Review Row holdout5-039

- Ticker: GOOGL
- Run ID: `299bb6af-5217-422e-bd47-1b3b07c57192`
- Source / agent role: neutral_risk_analyst
- Evidence ID / claim ID: `299bb6af-5217-422e-bd47-1b3b07c57192:neutral_risk_analyst:risk_debate_state.neutral_history:claim:65`
- Original sentence:
  > The downside is protected by a fortress balance sheet—$242B in cash, a current ratio of 2.72, and a 200-day SMA that has held as support.

- Expected Alpha: NONE
- System-mapped Alpha: NONE
- Alpha Match: **PASS**

- Expected polarity: NOT_ELIGIBLE
- System polarity: NOT_ELIGIBLE
- Polarity eligible: No
- Polarity Match: **NOT_ELIGIBLE**
- Critical support/opposition reversal: No

- Human review judgment: NOT_MATERIAL_ALPHA_FIT
- Review note / rationale: Balance sheet strength and 200-day SMA support; technical and liquidity background only, no Alpha mechanism
- Source authority: `docs/audit_artifacts/item2_blind_holdout5_{frozen.csv,review_frozen.csv,comparison.csv}`

---

### Review Row holdout5-040

- Ticker: GOOGL
- Run ID: `fadaa93c-8cd5-40df-a1bb-53ac4ccd1fb3`
- Source / agent role: aggressive_risk_analyst
- Evidence ID / claim ID: `fadaa93c-8cd5-40df-a1bb-53ac4ccd1fb3:aggressive_risk_analyst:risk_debate_state.aggressive_history:claim:50`
- Original sentence:
  > When retail is clinging to a stale Berkshire headline and the measured investor community has nothing to say, that is a sign of distribution, not accumulation.

- Expected Alpha: A601
- System-mapped Alpha: A601
- Alpha Match: **PASS**

- Expected polarity: mentions_alpha
- System polarity: opposes_alpha
- Polarity eligible: Yes
- Polarity Match: **FAIL**
- Critical support/opposition reversal: No

- Human review judgment: DIRECTIONALLY_CLEAR (no formal adjudication record; frozen blind label stands as ground truth)
- Review note / rationale: Retail clinging to stale narrative, institutional silence signals distribution; narrative/attention flow mechanism present but direction ambiguous
- Source authority: `docs/audit_artifacts/item2_blind_holdout5_{frozen.csv,review_frozen.csv,comparison.csv}`

---

### Review Row holdout5-041

- Ticker: GOOGL
- Run ID: `fadaa93c-8cd5-40df-a1bb-53ac4ccd1fb3`
- Source / agent role: bear_researcher
- Evidence ID / claim ID: `fadaa93c-8cd5-40df-a1bb-53ac4ccd1fb3:bear_researcher:investment_debate_state.bear_history:claim:54`
- Original sentence:
  > So even the world's best investor is currently underwater on this position.

- Expected Alpha: NONE
- System-mapped Alpha: NONE
- Alpha Match: **PASS**

- Expected polarity: NOT_ELIGIBLE
- System polarity: NOT_ELIGIBLE
- Polarity eligible: No
- Polarity Match: **NOT_ELIGIBLE**
- Critical support/opposition reversal: No

- Human review judgment: NOT_MATERIAL_ALPHA_FIT
- Review note / rationale: Generic anecdote about investor being underwater; no canonical Alpha mechanism present.
- Source authority: `docs/audit_artifacts/item2_blind_holdout5_{frozen.csv,review_frozen.csv,comparison.csv}`

---

### Review Row holdout5-042

- Ticker: GOOGL
- Run ID: `fadaa93c-8cd5-40df-a1bb-53ac4ccd1fb3`
- Source / agent role: bull_researcher
- Evidence ID / claim ID: `fadaa93c-8cd5-40df-a1bb-53ac4ccd1fb3:bull_researcher:investment_debate_state.bull_history:claim:49`
- Original sentence:
  > The negative FCF is entirely due to the deliberate, strategic decision to invest $44.92 billion in CapEx during the quarter.

- Expected Alpha: A103
- System-mapped Alpha: A103
- Alpha Match: **PASS**

- Expected polarity: supports_alpha
- System polarity: supports_alpha
- Polarity eligible: Yes
- Polarity Match: **PASS**
- Critical support/opposition reversal: No

- Human review judgment: DIRECTIONALLY_CLEAR (no formal adjudication record; frozen blind label stands as ground truth)
- Review note / rationale: Massive $44.92B quarterly CapEx explicitly framed as strategic AI infrastructure investment.
- Source authority: `docs/audit_artifacts/item2_blind_holdout5_{frozen.csv,review_frozen.csv,comparison.csv}`

---

### Review Row holdout5-043

- Ticker: GOOGL
- Run ID: `fadaa93c-8cd5-40df-a1bb-53ac4ccd1fb3`
- Source / agent role: bull_researcher
- Evidence ID / claim ID: `fadaa93c-8cd5-40df-a1bb-53ac4ccd1fb3:bull_researcher:investment_debate_state.bull_history:claim:5`
- Original sentence:
  > The bear is looking at the rearview mirror while Alphabet is flooring the accelerator into the AI future.

- Expected Alpha: NONE
- System-mapped Alpha: A601
- Alpha Match: **FAIL**

- Expected polarity: NOT_ELIGIBLE
- System polarity: NOT_ELIGIBLE
- Polarity eligible: No
- Polarity Match: **NOT_ELIGIBLE**
- Critical support/opposition reversal: No

- Human review judgment: NOT_MATERIAL_ALPHA_FIT
- Review note / rationale: Generic bullish rhetoric about AI future; no specific causal mechanism materially expressed.
- Source authority: `docs/audit_artifacts/item2_blind_holdout5_{frozen.csv,review_frozen.csv,comparison.csv}`

---

### Review Row holdout5-044

- Ticker: GOOGL
- Run ID: `fadaa93c-8cd5-40df-a1bb-53ac4ccd1fb3`
- Source / agent role: fundamental_agent
- Evidence ID / claim ID: `fadaa93c-8cd5-40df-a1bb-53ac4ccd1fb3:fundamental_agent:fundamentals_report:claim:104`
- Original sentence:
  > Valuation Risk: At $4.22T market cap with forward P/E of 23.4x, the market is pricing in continued high growth.

- Expected Alpha: A304
- System-mapped Alpha: A304
- Alpha Match: **PASS**

- Expected polarity: supports_alpha
- System polarity: supports_alpha
- Polarity eligible: Yes
- Polarity Match: **PASS**
- Critical support/opposition reversal: No

- Human review judgment: DIRECTIONALLY_CLEAR (no formal adjudication record; frozen blind label stands as ground truth)
- Review note / rationale: Explicitly cites $4.22T market cap and 23.4x forward P/E as valuation risk with high-growth expectations baked in.
- Source authority: `docs/audit_artifacts/item2_blind_holdout5_{frozen.csv,review_frozen.csv,comparison.csv}`

---

### Review Row holdout5-045

- Ticker: GOOGL
- Run ID: `fadaa93c-8cd5-40df-a1bb-53ac4ccd1fb3`
- Source / agent role: market_agent
- Evidence ID / claim ID: `fadaa93c-8cd5-40df-a1bb-53ac4ccd1fb3:market_agent:market_report:claim:44`
- Original sentence:
  > This indicates that the momentum recovery from the July crash has stalled, and downside momentum is reasserting.

- Expected Alpha: NONE
- System-mapped Alpha: NONE
- Alpha Match: **PASS**

- Expected polarity: NOT_ELIGIBLE
- System polarity: NOT_ELIGIBLE
- Polarity eligible: No
- Polarity Match: **NOT_ELIGIBLE**
- Critical support/opposition reversal: No

- Human review judgment: NOT_MATERIAL_ALPHA_FIT
- Review note / rationale: Pure technical momentum signal only; no canonical Alpha causal mechanism present.
- Source authority: `docs/audit_artifacts/item2_blind_holdout5_{frozen.csv,review_frozen.csv,comparison.csv}`

---

### Review Row holdout5-046

- Ticker: GOOGL
- Run ID: `fadaa93c-8cd5-40df-a1bb-53ac4ccd1fb3`
- Source / agent role: market_agent
- Evidence ID / claim ID: `fadaa93c-8cd5-40df-a1bb-53ac4ccd1fb3:market_agent:market_report:claim:69`
- Original sentence:
  > The VWMA (volume-weighted moving average) is at $353.39, which is above the current price ($345.33).

- Expected Alpha: NONE
- System-mapped Alpha: NONE
- Alpha Match: **PASS**

- Expected polarity: NOT_ELIGIBLE
- System polarity: NOT_ELIGIBLE
- Polarity eligible: No
- Polarity Match: **NOT_ELIGIBLE**
- Critical support/opposition reversal: No

- Human review judgment: NOT_MATERIAL_ALPHA_FIT
- Review note / rationale: VWMA vs price comparison is pure technical indicator; no canonical Alpha mechanism.
- Source authority: `docs/audit_artifacts/item2_blind_holdout5_{frozen.csv,review_frozen.csv,comparison.csv}`

---

### Review Row holdout5-047

- Ticker: GOOGL
- Run ID: `fadaa93c-8cd5-40df-a1bb-53ac4ccd1fb3`
- Source / agent role: neutral_risk_analyst
- Evidence ID / claim ID: `fadaa93c-8cd5-40df-a1bb-53ac4ccd1fb3:neutral_risk_analyst:risk_debate_state.neutral_history:claim:24`
- Original sentence:
  > CapEx of $44.92B in a single quarter is now outpacing operating cash flow of $39.07B.

- Expected Alpha: A103
- System-mapped Alpha: A103
- Alpha Match: **PASS**

- Expected polarity: mentions_alpha
- System polarity: mentions_alpha
- Polarity eligible: Yes
- Polarity Match: **PASS**
- Critical support/opposition reversal: No

- Human review judgment: DIRECTIONALLY_CLEAR (no formal adjudication record; frozen blind label stands as ground truth)
- Review note / rationale: CapEx outpacing operating cash flow flags AI infrastructure spending scale; no clear net directional stance.
- Source authority: `docs/audit_artifacts/item2_blind_holdout5_{frozen.csv,review_frozen.csv,comparison.csv}`

---

### Review Row holdout5-048

- Ticker: GOOGL
- Run ID: `fadaa93c-8cd5-40df-a1bb-53ac4ccd1fb3`
- Source / agent role: research_manager
- Evidence ID / claim ID: `fadaa93c-8cd5-40df-a1bb-53ac4ccd1fb3:research_manager:investment_plan:claim:6`
- Original sentence:
  > The bull frames the negative free cash flow (FCF) as a deliberate, strategic investment in AI infrastructure, a necessary cost for future dominance.

- Expected Alpha: A103
- System-mapped Alpha: A103
- Alpha Match: **PASS**

- Expected polarity: supports_alpha
- System polarity: supports_alpha
- Polarity eligible: Yes
- Polarity Match: **PASS**
- Critical support/opposition reversal: No

- Human review judgment: DIRECTIONALLY_CLEAR (no formal adjudication record; frozen blind label stands as ground truth)
- Review note / rationale: Negative FCF explicitly reframed as deliberate strategic AI infrastructure investment for future dominance.
- Source authority: `docs/audit_artifacts/item2_blind_holdout5_{frozen.csv,review_frozen.csv,comparison.csv}`

---

### Review Row holdout5-049

- Ticker: GOOGL
- Run ID: `fadaa93c-8cd5-40df-a1bb-53ac4ccd1fb3`
- Source / agent role: research_manager
- Evidence ID / claim ID: `fadaa93c-8cd5-40df-a1bb-53ac4ccd1fb3:research_manager:investment_plan:claim:8`
- Original sentence:
  > The Bear's Core Argument: The bear case is built on a forensic analysis of earnings quality, financial trajectory, and technical signals.

- Expected Alpha: NONE
- System-mapped Alpha: NONE
- Alpha Match: **PASS**

- Expected polarity: NOT_ELIGIBLE
- System polarity: NOT_ELIGIBLE
- Polarity eligible: No
- Polarity Match: **NOT_ELIGIBLE**
- Critical support/opposition reversal: No

- Human review judgment: NOT_MATERIAL_ALPHA_FIT
- Review note / rationale: Meta-description of a bear case structure; no specific Alpha mechanism materially expressed.
- Source authority: `docs/audit_artifacts/item2_blind_holdout5_{frozen.csv,review_frozen.csv,comparison.csv}`

---

### Review Row holdout5-050

- Ticker: GOOGL
- Run ID: `fadaa93c-8cd5-40df-a1bb-53ac4ccd1fb3`
- Source / agent role: sentiment_agent
- Evidence ID / claim ID: `fadaa93c-8cd5-40df-a1bb-53ac4ccd1fb3:sentiment_agent:sentiment_report:claim:16`
- Original sentence:
  > Scam/negative noise: A crypto trader reportedly lost $550,000 to a Google ad phishing scam — minor reputational noise, not material.

- Expected Alpha: NONE
- System-mapped Alpha: NONE
- Alpha Match: **PASS**

- Expected polarity: NOT_ELIGIBLE
- System polarity: NOT_ELIGIBLE
- Polarity eligible: No
- Polarity Match: **NOT_ELIGIBLE**
- Critical support/opposition reversal: No

- Human review judgment: NOT_MATERIAL_ALPHA_FIT
- Review note / rationale: Minor reputational noise explicitly flagged as non-material; no canonical Alpha mechanism.
- Source authority: `docs/audit_artifacts/item2_blind_holdout5_{frozen.csv,review_frozen.csv,comparison.csv}`

---

### Review Row holdout5-051

- Ticker: MSFT
- Run ID: `07ddc074-9ab2-4b16-8957-acbf94012144`
- Source / agent role: aggressive_risk_analyst
- Evidence ID / claim ID: `07ddc074-9ab2-4b16-8957-acbf94012144:aggressive_risk_analyst:risk_debate_state.aggressive_history:claim:24`
- Original sentence:
  > Operating cash flow is a record $182.9 billion, up 34%.

- Expected Alpha: A301
- System-mapped Alpha: A301
- Alpha Match: **PASS**

- Expected polarity: supports_alpha
- System polarity: supports_alpha
- Polarity eligible: Yes
- Polarity Match: **PASS**
- Critical support/opposition reversal: No

- Human review judgment: DIRECTIONALLY_CLEAR (no formal adjudication record; frozen blind label stands as ground truth)
- Review note / rationale: Record operating cash flow up 34% signals strong revenue/earnings expansion supporting A301 thesis.
- Source authority: `docs/audit_artifacts/item2_blind_holdout5_{frozen.csv,review_frozen.csv,comparison.csv}`

---

### Review Row holdout5-052

- Ticker: MSFT
- Run ID: `07ddc074-9ab2-4b16-8957-acbf94012144`
- Source / agent role: bear_researcher
- Evidence ID / claim ID: `07ddc074-9ab2-4b16-8957-acbf94012144:bear_researcher:investment_debate_state.bear_history:claim:46`
- Original sentence:
  > This is a misreading of the situation.

- Expected Alpha: NONE
- System-mapped Alpha: NONE
- Alpha Match: **PASS**

- Expected polarity: NOT_ELIGIBLE
- System polarity: NOT_ELIGIBLE
- Polarity eligible: No
- Polarity Match: **NOT_ELIGIBLE**
- Critical support/opposition reversal: No

- Human review judgment: NOT_MATERIAL_ALPHA_FIT
- Review note / rationale: Purely rhetorical statement with no causal or economic mechanism expressed.
- Source authority: `docs/audit_artifacts/item2_blind_holdout5_{frozen.csv,review_frozen.csv,comparison.csv}`

---

### Review Row holdout5-053

- Ticker: MSFT
- Run ID: `07ddc074-9ab2-4b16-8957-acbf94012144`
- Source / agent role: fundamental_agent
- Evidence ID / claim ID: `07ddc074-9ab2-4b16-8957-acbf94012144:fundamental_agent:fundamentals_report:claim:128`
- Original sentence:
  > Category: Growth; Metric: Net Income (FY26); Value: $133.7B; Assessment: +31.3% YoY

- Expected Alpha: A301
- System-mapped Alpha: A301
- Alpha Match: **PASS**

- Expected polarity: supports_alpha
- System polarity: supports_alpha
- Polarity eligible: Yes
- Polarity Match: **PASS**
- Critical support/opposition reversal: No

- Human review judgment: DIRECTIONALLY_CLEAR (no formal adjudication record; frozen blind label stands as ground truth)
- Review note / rationale: Net income growth of 31.3% YoY directly supports revenue/earnings expansion thesis.
- Source authority: `docs/audit_artifacts/item2_blind_holdout5_{frozen.csv,review_frozen.csv,comparison.csv}`

---

### Review Row holdout5-054

- Ticker: MSFT
- Run ID: `07ddc074-9ab2-4b16-8957-acbf94012144`
- Source / agent role: fundamental_agent
- Evidence ID / claim ID: `07ddc074-9ab2-4b16-8957-acbf94012144:fundamental_agent:fundamentals_report:claim:131`
- Original sentence:
  > Category: Profitability; Metric: ROE; Value: 34.0%; Assessment: Exceptional

- Expected Alpha: NONE
- System-mapped Alpha: NONE
- Alpha Match: **PASS**

- Expected polarity: NOT_ELIGIBLE
- System polarity: NOT_ELIGIBLE
- Polarity eligible: No
- Polarity Match: **NOT_ELIGIBLE**
- Critical support/opposition reversal: No

- Human review judgment: NOT_MATERIAL_ALPHA_FIT
- Review note / rationale: ROE metric is a profitability descriptor; no specific canonical Alpha causal mechanism expressed.
- Source authority: `docs/audit_artifacts/item2_blind_holdout5_{frozen.csv,review_frozen.csv,comparison.csv}`

---

### Review Row holdout5-055

- Ticker: MSFT
- Run ID: `07ddc074-9ab2-4b16-8957-acbf94012144`
- Source / agent role: research_manager
- Evidence ID / claim ID: `07ddc074-9ab2-4b16-8957-acbf94012144:research_manager:investment_plan:claim:5`
- Original sentence:
  > The bear also correctly flags that the forward P/E embeds a 31% EPS growth assumption, that FCF declined to $67B despite record OCF, and that the rising depreciation burden will compress the celebrated margins.

- Expected Alpha: A304
- System-mapped Alpha: A304
- Alpha Match: **PASS**

- Expected polarity: supports_alpha
- System polarity: supports_alpha
- Polarity eligible: Yes
- Polarity Match: **PASS**
- Critical support/opposition reversal: No

- Human review judgment: DIRECTIONALLY_CLEAR (no formal adjudication record; frozen blind label stands as ground truth)
- Review note / rationale: Forward P/E embedding 31% EPS growth assumption and FCF decline highlight rich valuation and multiple compression risk.
- Source authority: `docs/audit_artifacts/item2_blind_holdout5_{frozen.csv,review_frozen.csv,comparison.csv}`

---

### Review Row holdout5-056

- Ticker: MSFT
- Run ID: `0cb43bae-1a4d-4003-bb29-55d420498842`
- Source / agent role: aggressive_risk_analyst
- Evidence ID / claim ID: `0cb43bae-1a4d-4003-bb29-55d420498842:aggressive_risk_analyst:risk_debate_state.aggressive_history:claim:22`
- Original sentence:
  > The macro "headwind" is a non-factor when a company is demonstrating this level of pricing power and operational leverage.

- Expected Alpha: A501
- System-mapped Alpha: A301
- Alpha Match: **FAIL**

- Expected polarity: opposes_alpha
- System polarity: opposes_alpha
- Polarity eligible: Yes
- Polarity Match: **PASS**
- Critical support/opposition reversal: No

- Human review judgment: DIRECTIONALLY_CLEAR (no formal adjudication record; frozen blind label stands as ground truth)
- Review note / rationale: Evidence dismisses macro headwinds as irrelevant given pricing power, opposing recession-risk concern for MSFT.
- Source authority: `docs/audit_artifacts/item2_blind_holdout5_{frozen.csv,review_frozen.csv,comparison.csv}`

---

### Review Row holdout5-057

- Ticker: MSFT
- Run ID: `0cb43bae-1a4d-4003-bb29-55d420498842`
- Source / agent role: bear_researcher
- Evidence ID / claim ID: `0cb43bae-1a4d-4003-bb29-55d420498842:bear_researcher:investment_debate_state.bear_history:claim:45`
- Original sentence:
  > Amazon's Q2 beat showed its AI/chip businesses at a $25 billion run rate, and its cloud growth is "shooting to the top of the cloud wars." Google Cloud is aggressively discounting to win enterprise deals.

- Expected Alpha: A101
- System-mapped Alpha: A102
- Alpha Match: **FAIL**

- Expected polarity: supports_alpha
- System polarity: mentions_alpha
- Polarity eligible: Yes
- Polarity Match: **FAIL**
- Critical support/opposition reversal: No

- Human review judgment: DIRECTIONALLY_CLEAR (no formal adjudication record; frozen blind label stands as ground truth)
- Review note / rationale: Amazon AI/chip businesses at $25B run rate and cloud competition directly reflect AI training and adoption demand mechanism.
- Source authority: `docs/audit_artifacts/item2_blind_holdout5_{frozen.csv,review_frozen.csv,comparison.csv}`

---

### Review Row holdout5-058

- Ticker: MSFT
- Run ID: `0cb43bae-1a4d-4003-bb29-55d420498842`
- Source / agent role: bear_researcher
- Evidence ID / claim ID: `0cb43bae-1a4d-4003-bb29-55d420498842:bear_researcher:investment_debate_state.bear_history:claim:56`
- Original sentence:
  > The 50-day SMA needs to cross above the 200-day SMA for a true golden cross.

- Expected Alpha: NONE
- System-mapped Alpha: NONE
- Alpha Match: **PASS**

- Expected polarity: NOT_ELIGIBLE
- System polarity: NOT_ELIGIBLE
- Polarity eligible: No
- Polarity Match: **NOT_ELIGIBLE**
- Critical support/opposition reversal: No

- Human review judgment: NOT_MATERIAL_ALPHA_FIT
- Review note / rationale: Pure technical indicator (SMA golden cross); no canonical Alpha causal mechanism present.
- Source authority: `docs/audit_artifacts/item2_blind_holdout5_{frozen.csv,review_frozen.csv,comparison.csv}`

---

### Review Row holdout5-059

- Ticker: MSFT
- Run ID: `0cb43bae-1a4d-4003-bb29-55d420498842`
- Source / agent role: bull_researcher
- Evidence ID / claim ID: `0cb43bae-1a4d-4003-bb29-55d420498842:bull_researcher:investment_debate_state.bull_history:claim:13`
- Original sentence:
  > This is not a company growing at GDP pace.

- Expected Alpha: NONE
- System-mapped Alpha: A301
- Alpha Match: **FAIL**

- Expected polarity: NOT_ELIGIBLE
- System polarity: NOT_ELIGIBLE
- Polarity eligible: No
- Polarity Match: **NOT_ELIGIBLE**
- Critical support/opposition reversal: No

- Human review judgment: NOT_MATERIAL_ALPHA_FIT
- Review note / rationale: Generic qualitative growth assertion with no specific Alpha mechanism expressed.
- Source authority: `docs/audit_artifacts/item2_blind_holdout5_{frozen.csv,review_frozen.csv,comparison.csv}`

---

### Review Row holdout5-060

- Ticker: MSFT
- Run ID: `0cb43bae-1a4d-4003-bb29-55d420498842`
- Source / agent role: bull_researcher
- Evidence ID / claim ID: `0cb43bae-1a4d-4003-bb29-55d420498842:bull_researcher:investment_debate_state.bull_history:claim:44`
- Original sentence:
  > The company is generating more cash than ever before.

- Expected Alpha: A301
- System-mapped Alpha: A301
- Alpha Match: **PASS**

- Expected polarity: supports_alpha
- System polarity: supports_alpha
- Polarity eligible: Yes
- Polarity Match: **PASS**
- Critical support/opposition reversal: No

- Human review judgment: DIRECTIONALLY_CLEAR (no formal adjudication record; frozen blind label stands as ground truth)
- Review note / rationale: Record cash generation supports revenue/earnings expansion thesis for MSFT.
- Source authority: `docs/audit_artifacts/item2_blind_holdout5_{frozen.csv,review_frozen.csv,comparison.csv}`

---

### Review Row holdout5-061

- Ticker: MSFT
- Run ID: `0cb43bae-1a4d-4003-bb29-55d420498842`
- Source / agent role: fundamental_agent
- Evidence ID / claim ID: `0cb43bae-1a4d-4003-bb29-55d420498842:fundamental_agent:fundamentals_report:claim:88`
- Original sentence:
  > Metric: Dividend Yield; Value: 0.81%; Context: Modest income component

- Expected Alpha: NONE
- System-mapped Alpha: NONE
- Alpha Match: **PASS**

- Expected polarity: NOT_ELIGIBLE
- System polarity: NOT_ELIGIBLE
- Polarity eligible: No
- Polarity Match: **NOT_ELIGIBLE**
- Critical support/opposition reversal: No

- Human review judgment: NOT_MATERIAL_ALPHA_FIT
- Review note / rationale: Dividend yield figure only; no canonical Alpha mechanism present
- Source authority: `docs/audit_artifacts/item2_blind_holdout5_{frozen.csv,review_frozen.csv,comparison.csv}`

---

### Review Row holdout5-062

- Ticker: MSFT
- Run ID: `0cb43bae-1a4d-4003-bb29-55d420498842`
- Source / agent role: neutral_risk_analyst
- Evidence ID / claim ID: `0cb43bae-1a4d-4003-bb29-55d420498842:neutral_risk_analyst:risk_debate_state.neutral_history:claim:35`
- Original sentence:
  > It gives the position room to breathe while protecting against a genuine trend failure.

- Expected Alpha: NONE
- System-mapped Alpha: NONE
- Alpha Match: **PASS**

- Expected polarity: NOT_ELIGIBLE
- System polarity: NOT_ELIGIBLE
- Polarity eligible: No
- Polarity Match: **NOT_ELIGIBLE**
- Critical support/opposition reversal: No

- Human review judgment: NOT_MATERIAL_ALPHA_FIT
- Review note / rationale: Generic trade management language; no canonical Alpha mechanism present
- Source authority: `docs/audit_artifacts/item2_blind_holdout5_{frozen.csv,review_frozen.csv,comparison.csv}`

---

### Review Row holdout5-063

- Ticker: MSFT
- Run ID: `0cb43bae-1a4d-4003-bb29-55d420498842`
- Source / agent role: neutral_risk_analyst
- Evidence ID / claim ID: `0cb43bae-1a4d-4003-bb29-55d420498842:neutral_risk_analyst:risk_debate_state.neutral_history:claim:45`
- Original sentence:
  > The conservative analyst is right that the velocity of this move creates elevated pullback risk.

- Expected Alpha: NONE
- System-mapped Alpha: A304
- Alpha Match: **FAIL**

- Expected polarity: NOT_ELIGIBLE
- System polarity: NOT_ELIGIBLE
- Polarity eligible: No
- Polarity Match: **NOT_ELIGIBLE**
- Critical support/opposition reversal: No

- Human review judgment: NOT_MATERIAL_ALPHA_FIT
- Review note / rationale: Technical pullback risk commentary only; no canonical Alpha mechanism materially expressed
- Source authority: `docs/audit_artifacts/item2_blind_holdout5_{frozen.csv,review_frozen.csv,comparison.csv}`

---

### Review Row holdout5-064

- Ticker: MSFT
- Run ID: `0cb43bae-1a4d-4003-bb29-55d420498842`
- Source / agent role: neutral_risk_analyst
- Evidence ID / claim ID: `0cb43bae-1a4d-4003-bb29-55d420498842:neutral_risk_analyst:risk_debate_state.neutral_history:claim:66`
- Original sentence:
  > Keep the stop at $430, not $440.

- Expected Alpha: NONE
- System-mapped Alpha: NONE
- Alpha Match: **PASS**

- Expected polarity: NOT_ELIGIBLE
- System polarity: NOT_ELIGIBLE
- Polarity eligible: No
- Polarity Match: **NOT_ELIGIBLE**
- Critical support/opposition reversal: No

- Human review judgment: NOT_MATERIAL_ALPHA_FIT
- Review note / rationale: Stop-loss price level instruction only; no canonical Alpha mechanism present
- Source authority: `docs/audit_artifacts/item2_blind_holdout5_{frozen.csv,review_frozen.csv,comparison.csv}`

---

### Review Row holdout5-065

- Ticker: MSFT
- Run ID: `0cb43bae-1a4d-4003-bb29-55d420498842`
- Source / agent role: neutral_risk_analyst
- Evidence ID / claim ID: `0cb43bae-1a4d-4003-bb29-55d420498842:neutral_risk_analyst:risk_debate_state.neutral_history:claim:84`
- Original sentence:
  > Execute the accumulation plan if price gives us the opportunity.

- Expected Alpha: NONE
- System-mapped Alpha: NONE
- Alpha Match: **PASS**

- Expected polarity: NOT_ELIGIBLE
- System polarity: NOT_ELIGIBLE
- Polarity eligible: No
- Polarity Match: **NOT_ELIGIBLE**
- Critical support/opposition reversal: No

- Human review judgment: NOT_MATERIAL_ALPHA_FIT
- Review note / rationale: Generic trade execution instruction; no canonical Alpha mechanism present
- Source authority: `docs/audit_artifacts/item2_blind_holdout5_{frozen.csv,review_frozen.csv,comparison.csv}`

---

### Review Row holdout5-066

- Ticker: MSFT
- Run ID: `0cb43bae-1a4d-4003-bb29-55d420498842`
- Source / agent role: news_agent
- Evidence ID / claim ID: `0cb43bae-1a4d-4003-bb29-55d420498842:news_agent:news_report:claim:30`
- Original sentence:
  > The following is based on news and prediction market data.

- Expected Alpha: NONE
- System-mapped Alpha: NONE
- Alpha Match: **PASS**

- Expected polarity: NOT_ELIGIBLE
- System polarity: NOT_ELIGIBLE
- Polarity eligible: No
- Polarity Match: **NOT_ELIGIBLE**
- Critical support/opposition reversal: No

- Human review judgment: NOT_MATERIAL_ALPHA_FIT
- Review note / rationale: Methodological sourcing statement only; no canonical Alpha mechanism present
- Source authority: `docs/audit_artifacts/item2_blind_holdout5_{frozen.csv,review_frozen.csv,comparison.csv}`

---

### Review Row holdout5-067

- Ticker: MSFT
- Run ID: `0cb43bae-1a4d-4003-bb29-55d420498842`
- Source / agent role: research_manager
- Evidence ID / claim ID: `0cb43bae-1a4d-4003-bb29-55d420498842:research_manager:investment_plan:claim:3`
- Original sentence:
  > This debate presents a classic clash between fundamental momentum and technical/structural risk.

- Expected Alpha: NONE
- System-mapped Alpha: NONE
- Alpha Match: **PASS**

- Expected polarity: NOT_ELIGIBLE
- System polarity: NOT_ELIGIBLE
- Polarity eligible: No
- Polarity Match: **NOT_ELIGIBLE**
- Critical support/opposition reversal: No

- Human review judgment: NOT_MATERIAL_ALPHA_FIT
- Review note / rationale: Meta-framing of a debate; no specific canonical Alpha mechanism materially expressed
- Source authority: `docs/audit_artifacts/item2_blind_holdout5_{frozen.csv,review_frozen.csv,comparison.csv}`

---

### Review Row holdout5-068

- Ticker: MSFT
- Run ID: `0cb43bae-1a4d-4003-bb29-55d420498842`
- Source / agent role: research_manager
- Evidence ID / claim ID: `0cb43bae-1a4d-4003-bb29-55d420498842:research_manager:investment_plan:claim:9`
- Original sentence:
  > The bull correctly identifies that the market is currently rewarding companies that can demonstrate a return on AI investment, and Microsoft's record cloud revenue is the strongest evidence of this.

- Expected Alpha: A301
- System-mapped Alpha: A301
- Alpha Match: **PASS**

- Expected polarity: supports_alpha
- System polarity: supports_alpha
- Polarity eligible: Yes
- Polarity Match: **PASS**
- Critical support/opposition reversal: No

- Human review judgment: DIRECTIONALLY_CLEAR (no formal adjudication record; frozen blind label stands as ground truth)
- Review note / rationale: Record cloud revenue demonstrating AI investment returns supports revenue expansion thesis
- Source authority: `docs/audit_artifacts/item2_blind_holdout5_{frozen.csv,review_frozen.csv,comparison.csv}`

---

### Review Row holdout5-069

- Ticker: MSFT
- Run ID: `0cb43bae-1a4d-4003-bb29-55d420498842`
- Source / agent role: sentiment_agent
- Evidence ID / claim ID: `0cb43bae-1a4d-4003-bb29-55d420498842:sentiment_agent:sentiment_report:claim:76`
- Original sentence:
  > Signal: Retail momentum / big wins; Direction: Bullish; Source: Reddit; Supporting Evidence: $1M gain, $700K profit, $130K quick win posts

- Expected Alpha: A601
- System-mapped Alpha: A601
- Alpha Match: **PASS**

- Expected polarity: supports_alpha
- System polarity: supports_alpha
- Polarity eligible: Yes
- Polarity Match: **PASS**
- Critical support/opposition reversal: No

- Human review judgment: DIRECTIONALLY_CLEAR (no formal adjudication record; frozen blind label stands as ground truth)
- Review note / rationale: Reddit retail momentum and crowded win-posting reflect narrative/attention-driven flows mechanism
- Source authority: `docs/audit_artifacts/item2_blind_holdout5_{frozen.csv,review_frozen.csv,comparison.csv}`

---

### Review Row holdout5-070

- Ticker: MSFT
- Run ID: `61f3e019-63a8-4c56-b763-057208d5efae`
- Source / agent role: aggressive_risk_analyst
- Evidence ID / claim ID: `61f3e019-63a8-4c56-b763-057208d5efae:aggressive_risk_analyst:risk_debate_state.aggressive_history:claim:20`
- Original sentence:
  > The 92% earnings beat probability sitting on prediction markets is real.

- Expected Alpha: A301
- System-mapped Alpha: A301
- Alpha Match: **PASS**

- Expected polarity: supports_alpha
- System polarity: mentions_alpha
- Polarity eligible: Yes
- Polarity Match: **FAIL**
- Critical support/opposition reversal: No

- Human review judgment: DIRECTIONALLY_CLEAR (no formal adjudication record; frozen blind label stands as ground truth)
- Review note / rationale: 92% earnings beat probability on prediction markets supports revenue/EPS beat expectation thesis
- Source authority: `docs/audit_artifacts/item2_blind_holdout5_{frozen.csv,review_frozen.csv,comparison.csv}`

---

### Review Row holdout5-071

- Ticker: MSFT
- Run ID: `61f3e019-63a8-4c56-b763-057208d5efae`
- Source / agent role: bear_researcher
- Evidence ID / claim ID: `61f3e019-63a8-4c56-b763-057208d5efae:bear_researcher:investment_debate_state.bear_history:claim:46`
- Original sentence:
  > If you're spending $120B+ per year on infrastructure that may or may not generate commensurate returns, operating cash flow is not the right metric.

- Expected Alpha: A103
- System-mapped Alpha: A304
- Alpha Match: **FAIL**

- Expected polarity: mentions_alpha
- System polarity: mentions_alpha
- Polarity eligible: Yes
- Polarity Match: **PASS**
- Critical support/opposition reversal: No

- Human review judgment: DIRECTIONALLY_CLEAR (no formal adjudication record; frozen blind label stands as ground truth)
- Review note / rationale: Questions whether $120B+ infrastructure capex generates commensurate returns; directly discusses AI infrastructure buildout ROI without clear net stance.
- Source authority: `docs/audit_artifacts/item2_blind_holdout5_{frozen.csv,review_frozen.csv,comparison.csv}`

---

### Review Row holdout5-072

- Ticker: MSFT
- Run ID: `61f3e019-63a8-4c56-b763-057208d5efae`
- Source / agent role: conservative_risk_analyst
- Evidence ID / claim ID: `61f3e019-63a8-4c56-b763-057208d5efae:conservative_risk_analyst:risk_debate_state.conservative_history:claim:55`
- Original sentence:
  > With 85% probability of no cuts in 2026 and the dollar at a one-month high, the discount rate environment does not support multiple expansion for any growth stock, including Microsoft.

- Expected Alpha: A001
- System-mapped Alpha: A001
- Alpha Match: **PASS**

- Expected polarity: opposes_alpha
- System polarity: opposes_alpha
- Polarity eligible: Yes
- Polarity Match: **PASS**
- Critical support/opposition reversal: No

- Human review judgment: DIRECTIONALLY_CLEAR (no formal adjudication record; frozen blind label stands as ground truth)
- Review note / rationale: 85% no-cut probability and high dollar explicitly state discount rate environment does not support multiple expansion for growth stocks.
- Source authority: `docs/audit_artifacts/item2_blind_holdout5_{frozen.csv,review_frozen.csv,comparison.csv}`

---

### Review Row holdout5-073

- Ticker: MSFT
- Run ID: `61f3e019-63a8-4c56-b763-057208d5efae`
- Source / agent role: news_agent
- Evidence ID / claim ID: `61f3e019-63a8-4c56-b763-057208d5efae:news_agent:news_report:claim:57`
- Original sentence:
  > Report compiled on July 27, 2026.

- Expected Alpha: NONE
- System-mapped Alpha: NONE
- Alpha Match: **PASS**

- Expected polarity: NOT_ELIGIBLE
- System polarity: NOT_ELIGIBLE
- Polarity eligible: No
- Polarity Match: **NOT_ELIGIBLE**
- Critical support/opposition reversal: No

- Human review judgment: NOT_MATERIAL_ALPHA_FIT
- Review note / rationale: Report date only; no economic mechanism or Alpha thesis present.
- Source authority: `docs/audit_artifacts/item2_blind_holdout5_{frozen.csv,review_frozen.csv,comparison.csv}`

---

### Review Row holdout5-074

- Ticker: MSFT
- Run ID: `61f3e019-63a8-4c56-b763-057208d5efae`
- Source / agent role: portfolio_manager
- Evidence ID / claim ID: `61f3e019-63a8-4c56-b763-057208d5efae:portfolio_manager:final_trade_decision:claim:8`
- Original sentence:
  > The $50.9B deferred revenue backlog represents contracted, Microsoft-specific demand won in a competitive market — the conservative analyst's counterpoint that it is a lagging indicator is valid, but it still proves Azure is winning in a competitive environment, not merely that demand exists in aggregate.

- Expected Alpha: A301
- System-mapped Alpha: A301
- Alpha Match: **PASS**

- Expected polarity: supports_alpha
- System polarity: supports_alpha
- Polarity eligible: Yes
- Polarity Match: **PASS**
- Critical support/opposition reversal: No

- Human review judgment: DIRECTIONALLY_CLEAR (no formal adjudication record; frozen blind label stands as ground truth)
- Review note / rationale: Deferred revenue backlog evidences contracted Azure demand won competitively, supporting revenue expansion thesis.
- Source authority: `docs/audit_artifacts/item2_blind_holdout5_{frozen.csv,review_frozen.csv,comparison.csv}`

---

### Review Row holdout5-075

- Ticker: MSFT
- Run ID: `61f3e019-63a8-4c56-b763-057208d5efae`
- Source / agent role: research_manager
- Evidence ID / claim ID: `61f3e019-63a8-4c56-b763-057208d5efae:research_manager:investment_plan:claim:1`
- Original sentence:
  > Rationale: This was a high-quality, substantive debate, and both sides landed real blows.

- Expected Alpha: NONE
- System-mapped Alpha: NONE
- Alpha Match: **PASS**

- Expected polarity: NOT_ELIGIBLE
- System polarity: NOT_ELIGIBLE
- Polarity eligible: No
- Polarity Match: **NOT_ELIGIBLE**
- Critical support/opposition reversal: No

- Human review judgment: NOT_MATERIAL_ALPHA_FIT
- Review note / rationale: Meta-commentary on debate quality; no causal or economic Alpha mechanism present.
- Source authority: `docs/audit_artifacts/item2_blind_holdout5_{frozen.csv,review_frozen.csv,comparison.csv}`

---

### Review Row holdout5-076

- Ticker: MU
- Run ID: `0ba23540-0623-4d05-a670-098fbbfec1d1`
- Source / agent role: aggressive_risk_analyst
- Evidence ID / claim ID: `0ba23540-0623-4d05-a670-098fbbfec1d1:aggressive_risk_analyst:risk_debate_state.aggressive_history:claim:19`
- Original sentence:
  > I'm not going to pretend those signals don't exist.

- Expected Alpha: NONE
- System-mapped Alpha: NONE
- Alpha Match: **PASS**

- Expected polarity: NOT_ELIGIBLE
- System polarity: NOT_ELIGIBLE
- Polarity eligible: No
- Polarity Match: **NOT_ELIGIBLE**
- Critical support/opposition reversal: No

- Human review judgment: NOT_MATERIAL_ALPHA_FIT
- Review note / rationale: Vague acknowledgment of unspecified signals; no identifiable Alpha mechanism present.
- Source authority: `docs/audit_artifacts/item2_blind_holdout5_{frozen.csv,review_frozen.csv,comparison.csv}`

---

### Review Row holdout5-077

- Ticker: MU
- Run ID: `0ba23540-0623-4d05-a670-098fbbfec1d1`
- Source / agent role: aggressive_risk_analyst
- Evidence ID / claim ID: `0ba23540-0623-4d05-a670-098fbbfec1d1:aggressive_risk_analyst:risk_debate_state.aggressive_history:claim:27`
- Original sentence:
  > You do not abandon structurally sound positions because of a pullback that occurred after a 130% rally in eight weeks.

- Expected Alpha: NONE
- System-mapped Alpha: NONE
- Alpha Match: **PASS**

- Expected polarity: NOT_ELIGIBLE
- System polarity: NOT_ELIGIBLE
- Polarity eligible: No
- Polarity Match: **NOT_ELIGIBLE**
- Critical support/opposition reversal: No

- Human review judgment: NOT_MATERIAL_ALPHA_FIT
- Review note / rationale: Portfolio holding advice after a rally and pullback; no canonical Alpha causal mechanism materially expressed.
- Source authority: `docs/audit_artifacts/item2_blind_holdout5_{frozen.csv,review_frozen.csv,comparison.csv}`

---

### Review Row holdout5-078

- Ticker: MU
- Run ID: `0ba23540-0623-4d05-a670-098fbbfec1d1`
- Source / agent role: aggressive_risk_analyst
- Evidence ID / claim ID: `0ba23540-0623-4d05-a670-098fbbfec1d1:aggressive_risk_analyst:risk_debate_state.aggressive_history:claim:31`
- Original sentence:
  > That stop defines your maximum loss on the initial tranche at roughly 13.6% from entry, and given the portfolio-level sizing, that caps total portfolio drawdown at 0.5 to 0.7%.

- Expected Alpha: NONE
- System-mapped Alpha: NONE
- Alpha Match: **PASS**

- Expected polarity: NOT_ELIGIBLE
- System polarity: NOT_ELIGIBLE
- Polarity eligible: No
- Polarity Match: **NOT_ELIGIBLE**
- Critical support/opposition reversal: No

- Human review judgment: NOT_MATERIAL_ALPHA_FIT
- Review note / rationale: Position sizing and stop-loss risk management detail only; no Alpha economic mechanism present.
- Source authority: `docs/audit_artifacts/item2_blind_holdout5_{frozen.csv,review_frozen.csv,comparison.csv}`

---

### Review Row holdout5-079

- Ticker: MU
- Run ID: `0ba23540-0623-4d05-a670-098fbbfec1d1`
- Source / agent role: aggressive_risk_analyst
- Evidence ID / claim ID: `0ba23540-0623-4d05-a670-098fbbfec1d1:aggressive_risk_analyst:risk_debate_state.aggressive_history:claim:55`
- Original sentence:
  > You keep citing FY2023's $5.83 billion net loss as though it refutes the forward P/E case.

- Expected Alpha: A304
- System-mapped Alpha: A304
- Alpha Match: **PASS**

- Expected polarity: mentions_alpha
- System polarity: mentions_alpha
- Polarity eligible: Yes
- Polarity Match: **PASS**
- Critical support/opposition reversal: No

- Human review judgment: DIRECTIONALLY_CLEAR (no formal adjudication record; frozen blind label stands as ground truth)
- Review note / rationale: Debate over forward P/E validity given historical losses directly discusses valuation multiple risk without clear net direction.
- Source authority: `docs/audit_artifacts/item2_blind_holdout5_{frozen.csv,review_frozen.csv,comparison.csv}`

---

### Review Row holdout5-080

- Ticker: MU
- Run ID: `0ba23540-0623-4d05-a670-098fbbfec1d1`
- Source / agent role: aggressive_risk_analyst
- Evidence ID / claim ID: `0ba23540-0623-4d05-a670-098fbbfec1d1:aggressive_risk_analyst:risk_debate_state.aggressive_history:claim:9`
- Original sentence:
  > Daryanani's warning is real, I'm not dismissing it.

- Expected Alpha: NONE
- System-mapped Alpha: NONE
- Alpha Match: **PASS**

- Expected polarity: NOT_ELIGIBLE
- System polarity: NOT_ELIGIBLE
- Polarity eligible: No
- Polarity Match: **NOT_ELIGIBLE**
- Critical support/opposition reversal: No

- Human review judgment: NOT_MATERIAL_ALPHA_FIT
- Review note / rationale: Vague acknowledgment of an unnamed analyst warning; no Alpha mechanism identifiable.
- Source authority: `docs/audit_artifacts/item2_blind_holdout5_{frozen.csv,review_frozen.csv,comparison.csv}`

---

### Review Row holdout5-081

- Ticker: MU
- Run ID: `0ba23540-0623-4d05-a670-098fbbfec1d1`
- Source / agent role: bear_researcher
- Evidence ID / claim ID: `0ba23540-0623-4d05-a670-098fbbfec1d1:bear_researcher:investment_debate_state.bear_history:claim:57`
- Original sentence:
  > In FY2022, the industry was booming and companies were expanding.

- Expected Alpha: NONE
- System-mapped Alpha: A201
- Alpha Match: **FAIL**

- Expected polarity: NOT_ELIGIBLE
- System polarity: NOT_ELIGIBLE
- Polarity eligible: No
- Polarity Match: **NOT_ELIGIBLE**
- Critical support/opposition reversal: No

- Human review judgment: NOT_MATERIAL_ALPHA_FIT
- Review note / rationale: Generic historical industry boom statement; no specific Alpha mechanism expressed
- Source authority: `docs/audit_artifacts/item2_blind_holdout5_{frozen.csv,review_frozen.csv,comparison.csv}`

---

### Review Row holdout5-082

- Ticker: MU
- Run ID: `0ba23540-0623-4d05-a670-098fbbfec1d1`
- Source / agent role: bull_researcher
- Evidence ID / claim ID: `0ba23540-0623-4d05-a670-098fbbfec1d1:bull_researcher:investment_debate_state.bull_history:claim:1`
- Original sentence:
  > Bull Analyst: # 🐂 The Bull Case for MU: Why This Pullback Is Your Generational Entry Point

- Expected Alpha: NONE
- System-mapped Alpha: NONE
- Alpha Match: **PASS**

- Expected polarity: NOT_ELIGIBLE
- System polarity: NOT_ELIGIBLE
- Polarity eligible: No
- Polarity Match: **NOT_ELIGIBLE**
- Critical support/opposition reversal: No

- Human review judgment: NOT_MATERIAL_ALPHA_FIT
- Review note / rationale: Promotional headline only; no causal or economic mechanism present
- Source authority: `docs/audit_artifacts/item2_blind_holdout5_{frozen.csv,review_frozen.csv,comparison.csv}`

---

### Review Row holdout5-083

- Ticker: MU
- Run ID: `0ba23540-0623-4d05-a670-098fbbfec1d1`
- Source / agent role: bull_researcher
- Evidence ID / claim ID: `0ba23540-0623-4d05-a670-098fbbfec1d1:bull_researcher:investment_debate_state.bull_history:claim:9`
- Original sentence:
  > In nine months, stockholders' equity nearly doubled — from $54 billion to $100 billion.

- Expected Alpha: NONE
- System-mapped Alpha: A301
- Alpha Match: **FAIL**

- Expected polarity: NOT_ELIGIBLE
- System polarity: NOT_ELIGIBLE
- Polarity eligible: No
- Polarity Match: **NOT_ELIGIBLE**
- Critical support/opposition reversal: No

- Human review judgment: NOT_MATERIAL_ALPHA_FIT
- Review note / rationale: Balance sheet metric only; no canonical Alpha mechanism materially expressed
- Source authority: `docs/audit_artifacts/item2_blind_holdout5_{frozen.csv,review_frozen.csv,comparison.csv}`

---

### Review Row holdout5-084

- Ticker: MU
- Run ID: `0ba23540-0623-4d05-a670-098fbbfec1d1`
- Source / agent role: conservative_risk_analyst
- Evidence ID / claim ID: `0ba23540-0623-4d05-a670-098fbbfec1d1:conservative_risk_analyst:risk_debate_state.conservative_history:claim:13`
- Original sentence:
  > I want to push back on that directly because the data does not fully support that separation.

- Expected Alpha: NONE
- System-mapped Alpha: NONE
- Alpha Match: **PASS**

- Expected polarity: NOT_ELIGIBLE
- System polarity: NOT_ELIGIBLE
- Polarity eligible: No
- Polarity Match: **NOT_ELIGIBLE**
- Critical support/opposition reversal: No

- Human review judgment: NOT_MATERIAL_ALPHA_FIT
- Review note / rationale: Argumentative rebuttal with no specific mechanism or context to map to any Alpha
- Source authority: `docs/audit_artifacts/item2_blind_holdout5_{frozen.csv,review_frozen.csv,comparison.csv}`

---

### Review Row holdout5-085

- Ticker: MU
- Run ID: `0ba23540-0623-4d05-a670-098fbbfec1d1`
- Source / agent role: conservative_risk_analyst
- Evidence ID / claim ID: `0ba23540-0623-4d05-a670-098fbbfec1d1:conservative_risk_analyst:risk_debate_state.conservative_history:claim:29`
- Original sentence:
  > That is a momentum trough being tested, and the test is not resolved.

- Expected Alpha: NONE
- System-mapped Alpha: NONE
- Alpha Match: **PASS**

- Expected polarity: NOT_ELIGIBLE
- System polarity: NOT_ELIGIBLE
- Polarity eligible: No
- Polarity Match: **NOT_ELIGIBLE**
- Critical support/opposition reversal: No

- Human review judgment: NOT_MATERIAL_ALPHA_FIT
- Review note / rationale: Technical momentum language only; no canonical Alpha causal mechanism present
- Source authority: `docs/audit_artifacts/item2_blind_holdout5_{frozen.csv,review_frozen.csv,comparison.csv}`

---

### Review Row holdout5-086

- Ticker: MU
- Run ID: `0ba23540-0623-4d05-a670-098fbbfec1d1`
- Source / agent role: fundamental_agent
- Evidence ID / claim ID: `0ba23540-0623-4d05-a670-098fbbfec1d1:fundamental_agent:fundamentals_report:claim:20`
- Original sentence:
  > R&D investment is scaling up significantly but remains a small fraction of revenue due to revenue outpacing investment.

- Expected Alpha: A301
- System-mapped Alpha: A201
- Alpha Match: **FAIL**

- Expected polarity: supports_alpha
- System polarity: supports_alpha
- Polarity eligible: Yes
- Polarity Match: **PASS**
- Critical support/opposition reversal: No

- Human review judgment: DIRECTIONALLY_CLEAR (no formal adjudication record; frozen blind label stands as ground truth)
- Review note / rationale: Revenue outpacing R&D investment signals strong demand-driven revenue expansion with margin leverage
- Source authority: `docs/audit_artifacts/item2_blind_holdout5_{frozen.csv,review_frozen.csv,comparison.csv}`

---

### Review Row holdout5-087

- Ticker: MU
- Run ID: `0ba23540-0623-4d05-a670-098fbbfec1d1`
- Source / agent role: fundamental_agent
- Evidence ID / claim ID: `0ba23540-0623-4d05-a670-098fbbfec1d1:fundamental_agent:fundamentals_report:claim:26`
- Original sentence:
  > The company repaid $4.75B in debt in Q3 FY2026 alone.

- Expected Alpha: NONE
- System-mapped Alpha: NONE
- Alpha Match: **PASS**

- Expected polarity: NOT_ELIGIBLE
- System polarity: NOT_ELIGIBLE
- Polarity eligible: No
- Polarity Match: **NOT_ELIGIBLE**
- Critical support/opposition reversal: No

- Human review judgment: NOT_MATERIAL_ALPHA_FIT
- Review note / rationale: Debt repayment is a balance sheet event; no canonical Alpha mechanism materially present
- Source authority: `docs/audit_artifacts/item2_blind_holdout5_{frozen.csv,review_frozen.csv,comparison.csv}`

---

### Review Row holdout5-088

- Ticker: MU
- Run ID: `0ba23540-0623-4d05-a670-098fbbfec1d1`
- Source / agent role: fundamental_agent
- Evidence ID / claim ID: `0ba23540-0623-4d05-a670-098fbbfec1d1:fundamental_agent:fundamentals_report:claim:31`
- Original sentence:
  > Inventory has remained range-bound around $8.2–$8.7B throughout recent quarters despite explosive revenue, indicating exceptional sell-through rates with no inventory build-up risk.

- Expected Alpha: A201
- System-mapped Alpha: A201
- Alpha Match: **PASS**

- Expected polarity: supports_alpha
- System polarity: supports_alpha
- Polarity eligible: Yes
- Polarity Match: **PASS**
- Critical support/opposition reversal: No

- Human review judgment: DIRECTIONALLY_CLEAR (no formal adjudication record; frozen blind label stands as ground truth)
- Review note / rationale: Stable inventory despite explosive revenue indicates healthy sell-through, supporting semiconductor cycle upturn thesis
- Source authority: `docs/audit_artifacts/item2_blind_holdout5_{frozen.csv,review_frozen.csv,comparison.csv}`

---

### Review Row holdout5-089

- Ticker: MU
- Run ID: `0ba23540-0623-4d05-a670-098fbbfec1d1`
- Source / agent role: neutral_risk_analyst
- Evidence ID / claim ID: `0ba23540-0623-4d05-a670-098fbbfec1d1:neutral_risk_analyst:risk_debate_state.neutral_history:claim:10`
- Original sentence:
  > Now, your HBM quarantine argument is where I think you're on genuinely shaky ground.

- Expected Alpha: NONE
- System-mapped Alpha: NONE
- Alpha Match: **PASS**

- Expected polarity: NOT_ELIGIBLE
- System polarity: NOT_ELIGIBLE
- Polarity eligible: No
- Polarity Match: **NOT_ELIGIBLE**
- Critical support/opposition reversal: No

- Human review judgment: NOT_MATERIAL_ALPHA_FIT
- Review note / rationale: Argumentative fragment referencing HBM quarantine with no substantive mechanism elaborated
- Source authority: `docs/audit_artifacts/item2_blind_holdout5_{frozen.csv,review_frozen.csv,comparison.csv}`

---

### Review Row holdout5-090

- Ticker: MU
- Run ID: `0ba23540-0623-4d05-a670-098fbbfec1d1`
- Source / agent role: neutral_risk_analyst
- Evidence ID / claim ID: `0ba23540-0623-4d05-a670-098fbbfec1d1:neutral_risk_analyst:risk_debate_state.neutral_history:claim:21`
- Original sentence:
  > You will have paid for confirmation in the form of a 2 to 5% higher entry price.

- Expected Alpha: NONE
- System-mapped Alpha: NONE
- Alpha Match: **PASS**

- Expected polarity: NOT_ELIGIBLE
- System polarity: NOT_ELIGIBLE
- Polarity eligible: No
- Polarity Match: **NOT_ELIGIBLE**
- Critical support/opposition reversal: No

- Human review judgment: NOT_MATERIAL_ALPHA_FIT
- Review note / rationale: Trading entry cost commentary only; no canonical Alpha mechanism present
- Source authority: `docs/audit_artifacts/item2_blind_holdout5_{frozen.csv,review_frozen.csv,comparison.csv}`

---

### Review Row holdout5-091

- Ticker: MU
- Run ID: `0ba23540-0623-4d05-a670-098fbbfec1d1`
- Source / agent role: neutral_risk_analyst
- Evidence ID / claim ID: `0ba23540-0623-4d05-a670-098fbbfec1d1:neutral_risk_analyst:risk_debate_state.neutral_history:claim:24`
- Original sentence:
  > You're trading one risk for another, and you haven't fully accounted for the cost of being wrong in both directions.

- Expected Alpha: NONE
- System-mapped Alpha: NONE
- Alpha Match: **PASS**

- Expected polarity: NOT_ELIGIBLE
- System polarity: NOT_ELIGIBLE
- Polarity eligible: No
- Polarity Match: **NOT_ELIGIBLE**
- Critical support/opposition reversal: No

- Human review judgment: NOT_MATERIAL_ALPHA_FIT
- Review note / rationale: Generic risk-management observation; no canonical Alpha mechanism present.
- Source authority: `docs/audit_artifacts/item2_blind_holdout5_{frozen.csv,review_frozen.csv,comparison.csv}`

---

### Review Row holdout5-092

- Ticker: MU
- Run ID: `0ba23540-0623-4d05-a670-098fbbfec1d1`
- Source / agent role: neutral_risk_analyst
- Evidence ID / claim ID: `0ba23540-0623-4d05-a670-098fbbfec1d1:neutral_risk_analyst:risk_debate_state.neutral_history:claim:33`
- Original sentence:
  > The solution to binary event risk is position sizing, not abstention.

- Expected Alpha: NONE
- System-mapped Alpha: NONE
- Alpha Match: **PASS**

- Expected polarity: NOT_ELIGIBLE
- System polarity: NOT_ELIGIBLE
- Polarity eligible: No
- Polarity Match: **NOT_ELIGIBLE**
- Critical support/opposition reversal: No

- Human review judgment: NOT_MATERIAL_ALPHA_FIT
- Review note / rationale: Portfolio sizing advice only; no canonical Alpha causal mechanism expressed.
- Source authority: `docs/audit_artifacts/item2_blind_holdout5_{frozen.csv,review_frozen.csv,comparison.csv}`

---

### Review Row holdout5-093

- Ticker: MU
- Run ID: `0ba23540-0623-4d05-a670-098fbbfec1d1`
- Source / agent role: neutral_risk_analyst
- Evidence ID / claim ID: `0ba23540-0623-4d05-a670-098fbbfec1d1:neutral_risk_analyst:risk_debate_state.neutral_history:claim:44`
- Original sentence:
  > You maintain the stop at $803 on a weekly close basis, which the data fully supports as the structurally appropriate risk boundary.

- Expected Alpha: NONE
- System-mapped Alpha: NONE
- Alpha Match: **PASS**

- Expected polarity: NOT_ELIGIBLE
- System polarity: NOT_ELIGIBLE
- Polarity eligible: No
- Polarity Match: **NOT_ELIGIBLE**
- Critical support/opposition reversal: No

- Human review judgment: NOT_MATERIAL_ALPHA_FIT
- Review note / rationale: Technical stop-loss level only; no canonical Alpha mechanism present.
- Source authority: `docs/audit_artifacts/item2_blind_holdout5_{frozen.csv,review_frozen.csv,comparison.csv}`

---

### Review Row holdout5-094

- Ticker: MU
- Run ID: `0ba23540-0623-4d05-a670-098fbbfec1d1`
- Source / agent role: news_agent
- Evidence ID / claim ID: `0ba23540-0623-4d05-a670-098fbbfec1d1:news_agent:news_report:claim:12`
- Original sentence:
  > This positions MU competitively in the AI memory race, where HBM chips command premium pricing and tight supply.

- Expected Alpha: A201
- System-mapped Alpha: A201
- Alpha Match: **PASS**

- Expected polarity: supports_alpha
- System polarity: supports_alpha
- Polarity eligible: Yes
- Polarity Match: **PASS**
- Critical support/opposition reversal: No

- Human review judgment: DIRECTIONALLY_CLEAR (no formal adjudication record; frozen blind label stands as ground truth)
- Review note / rationale: HBM chips at premium pricing and tight supply directly expresses semiconductor supercycle demand/pricing thesis.
- Source authority: `docs/audit_artifacts/item2_blind_holdout5_{frozen.csv,review_frozen.csv,comparison.csv}`

---

### Review Row holdout5-095

- Ticker: MU
- Run ID: `0ba23540-0623-4d05-a670-098fbbfec1d1`
- Source / agent role: news_agent
- Evidence ID / claim ID: `0ba23540-0623-4d05-a670-098fbbfec1d1:news_agent:news_report:claim:28`
- Original sentence:
  > The Korea selloff signals that institutional investors in the memory supply chain are expressing serious concern about forward demand/supply dynamics.

- Expected Alpha: A201
- System-mapped Alpha: A201
- Alpha Match: **PASS**

- Expected polarity: opposes_alpha
- System polarity: opposes_alpha
- Polarity eligible: Yes
- Polarity Match: **PASS**
- Critical support/opposition reversal: No

- Human review judgment: DIRECTIONALLY_CLEAR (no formal adjudication record; frozen blind label stands as ground truth)
- Review note / rationale: Institutional selloff citing forward demand/supply concern weakens semiconductor supercycle thesis for memory.
- Source authority: `docs/audit_artifacts/item2_blind_holdout5_{frozen.csv,review_frozen.csv,comparison.csv}`

---

### Review Row holdout5-096

- Ticker: MU
- Run ID: `0ba23540-0623-4d05-a670-098fbbfec1d1`
- Source / agent role: portfolio_manager
- Evidence ID / claim ID: `0ba23540-0623-4d05-a670-098fbbfec1d1:portfolio_manager:final_trade_decision:claim:10`
- Original sentence:
  > The technical picture counsels against maximum initial sizing, not abstention.

- Expected Alpha: NONE
- System-mapped Alpha: NONE
- Alpha Match: **PASS**

- Expected polarity: NOT_ELIGIBLE
- System polarity: NOT_ELIGIBLE
- Polarity eligible: No
- Polarity Match: **NOT_ELIGIBLE**
- Critical support/opposition reversal: No

- Human review judgment: NOT_MATERIAL_ALPHA_FIT
- Review note / rationale: Position sizing guidance based on technical picture; no canonical Alpha mechanism.
- Source authority: `docs/audit_artifacts/item2_blind_holdout5_{frozen.csv,review_frozen.csv,comparison.csv}`

---

### Review Row holdout5-097

- Ticker: MU
- Run ID: `0ba23540-0623-4d05-a670-098fbbfec1d1`
- Source / agent role: portfolio_manager
- Evidence ID / claim ID: `0ba23540-0623-4d05-a670-098fbbfec1d1:portfolio_manager:final_trade_decision:claim:2`
- Original sentence:
  > Reserve the remaining 1.5–2% of target allocation for deployment contingent on explicit post-catalyst protocols: add aggressively to 4% on MACD crossover + two consecutive closes above $976 (bull case); add a measured 1% tranche to 3.5% on confirmed $848–$865 support hold on volume (mixed case); tighten to $848 stop and reduce to 1% stub if hyperscaler guidance is uniformly disappointing (bear case).

- Expected Alpha: NONE
- System-mapped Alpha: NONE
- Alpha Match: **PASS**

- Expected polarity: NOT_ELIGIBLE
- System polarity: NOT_ELIGIBLE
- Polarity eligible: No
- Polarity Match: **NOT_ELIGIBLE**
- Critical support/opposition reversal: No

- Human review judgment: NOT_MATERIAL_ALPHA_FIT
- Review note / rationale: Technical trading protocols and MACD triggers only; no canonical Alpha causal mechanism.
- Source authority: `docs/audit_artifacts/item2_blind_holdout5_{frozen.csv,review_frozen.csv,comparison.csv}`

---

### Review Row holdout5-098

- Ticker: MU
- Run ID: `0ba23540-0623-4d05-a670-098fbbfec1d1`
- Source / agent role: sentiment_agent
- Evidence ID / claim ID: `0ba23540-0623-4d05-a670-098fbbfec1d1:sentiment_agent:sentiment_report:claim:1`
- Original sentence:
  > Overall Sentiment: Mixed (Score: 4.2/10) Confidence: Medium

- Expected Alpha: NONE
- System-mapped Alpha: NONE
- Alpha Match: **PASS**

- Expected polarity: NOT_ELIGIBLE
- System polarity: NOT_ELIGIBLE
- Polarity eligible: No
- Polarity Match: **NOT_ELIGIBLE**
- Critical support/opposition reversal: No

- Human review judgment: NOT_MATERIAL_ALPHA_FIT
- Review note / rationale: Aggregate sentiment score label only; no canonical Alpha mechanism expressed.
- Source authority: `docs/audit_artifacts/item2_blind_holdout5_{frozen.csv,review_frozen.csv,comparison.csv}`

---

### Review Row holdout5-099

- Ticker: MU
- Run ID: `0ba23540-0623-4d05-a670-098fbbfec1d1`
- Source / agent role: sentiment_agent
- Evidence ID / claim ID: `0ba23540-0623-4d05-a670-098fbbfec1d1:sentiment_agent:sentiment_report:claim:22`
- Original sentence:
  > With 30 total messages, sample size is modest but workable; the 16 unlabeled messages contain important color.

- Expected Alpha: NONE
- System-mapped Alpha: NONE
- Alpha Match: **PASS**

- Expected polarity: NOT_ELIGIBLE
- System polarity: NOT_ELIGIBLE
- Polarity eligible: No
- Polarity Match: **NOT_ELIGIBLE**
- Critical support/opposition reversal: No

- Human review judgment: NOT_MATERIAL_ALPHA_FIT
- Review note / rationale: Meta-commentary on dataset sample size; no canonical Alpha mechanism present.
- Source authority: `docs/audit_artifacts/item2_blind_holdout5_{frozen.csv,review_frozen.csv,comparison.csv}`

---

### Review Row holdout5-100

- Ticker: MU
- Run ID: `0ba23540-0623-4d05-a670-098fbbfec1d1`
- Source / agent role: sentiment_agent
- Evidence ID / claim ID: `0ba23540-0623-4d05-a670-098fbbfec1d1:sentiment_agent:sentiment_report:claim:47`
- Original sentence:
  > Retail is not capitulating, but not piling in either — this is a "wait and see" posture after a sharp drawdown.

- Expected Alpha: NONE
- System-mapped Alpha: NONE
- Alpha Match: **PASS**

- Expected polarity: NOT_ELIGIBLE
- System polarity: NOT_ELIGIBLE
- Polarity eligible: No
- Polarity Match: **NOT_ELIGIBLE**
- Critical support/opposition reversal: No

- Human review judgment: NOT_MATERIAL_ALPHA_FIT
- Review note / rationale: Retail positioning described as neutral wait-and-see; insufficient narrative/flow mechanism for A601.
- Source authority: `docs/audit_artifacts/item2_blind_holdout5_{frozen.csv,review_frozen.csv,comparison.csv}`

---

### Review Row holdout5-101

- Ticker: NVDA
- Run ID: `0e044e37-862c-43be-871c-31012cd660e7`
- Source / agent role: bear_researcher
- Evidence ID / claim ID: `0e044e37-862c-43be-871c-31012cd660e7:bear_researcher:investment_debate_state.bear_history:claim:174`
- Original sentence:
  > That's $100+ billion in incremental annual revenue on top of the $215.94 billion base.

- Expected Alpha: A301
- System-mapped Alpha: A301
- Alpha Match: **PASS**

- Expected polarity: supports_alpha
- System polarity: supports_alpha
- Polarity eligible: Yes
- Polarity Match: **PASS**
- Critical support/opposition reversal: No

- Human review judgment: DIRECTIONALLY_CLEAR (no formal adjudication record; frozen blind label stands as ground truth)
- Review note / rationale: Incremental $100B+ revenue on top of $215.94B base directly supports revenue expansion thesis.
- Source authority: `docs/audit_artifacts/item2_blind_holdout5_{frozen.csv,review_frozen.csv,comparison.csv}`

---

### Review Row holdout5-102

- Ticker: NVDA
- Run ID: `0e044e37-862c-43be-871c-31012cd660e7`
- Source / agent role: bear_researcher
- Evidence ID / claim ID: `0e044e37-862c-43be-871c-31012cd660e7:bear_researcher:investment_debate_state.bear_history:claim:263`
- Original sentence:
  > ✅ Inventory of $25.80 billion converts to revenue without write-downs

- Expected Alpha: A301
- System-mapped Alpha: A201
- Alpha Match: **FAIL**

- Expected polarity: supports_alpha
- System polarity: supports_alpha
- Polarity eligible: Yes
- Polarity Match: **PASS**
- Critical support/opposition reversal: No

- Human review judgment: DIRECTIONALLY_CLEAR (no formal adjudication record; frozen blind label stands as ground truth)
- Review note / rationale: Clean inventory conversion to revenue without write-downs supports revenue expansion and demand strength.
- Source authority: `docs/audit_artifacts/item2_blind_holdout5_{frozen.csv,review_frozen.csv,comparison.csv}`

---

### Review Row holdout5-103

- Ticker: NVDA
- Run ID: `0e044e37-862c-43be-871c-31012cd660e7`
- Source / agent role: bear_researcher
- Evidence ID / claim ID: `0e044e37-862c-43be-871c-31012cd660e7:bear_researcher:investment_debate_state.bear_history:claim:68`
- Original sentence:
  > Microsoft is reportedly developing Maia internally.

- Expected Alpha: NONE
- System-mapped Alpha: A101
- Alpha Match: **FAIL**

- Expected polarity: NOT_ELIGIBLE
- System polarity: NOT_ELIGIBLE
- Polarity eligible: No
- Polarity Match: **NOT_ELIGIBLE**
- Critical support/opposition reversal: No

- Human review judgment: NOT_MATERIAL_ALPHA_FIT
- Review note / rationale: Single mention of Microsoft Maia development; no causal mechanism expressed for any canonical Alpha.
- Source authority: `docs/audit_artifacts/item2_blind_holdout5_{frozen.csv,review_frozen.csv,comparison.csv}`

---

### Review Row holdout5-104

- Ticker: NVDA
- Run ID: `0e044e37-862c-43be-871c-31012cd660e7`
- Source / agent role: bull_researcher
- Evidence ID / claim ID: `0e044e37-862c-43be-871c-31012cd660e7:bull_researcher:investment_debate_state.bull_history:claim:166`
- Original sentence:
  > The inventory increase maps almost perfectly to the production ramp timeline.

- Expected Alpha: NONE
- System-mapped Alpha: A201
- Alpha Match: **FAIL**

- Expected polarity: NOT_ELIGIBLE
- System polarity: NOT_ELIGIBLE
- Polarity eligible: No
- Polarity Match: **NOT_ELIGIBLE**
- Critical support/opposition reversal: No

- Human review judgment: NOT_MATERIAL_ALPHA_FIT
- Review note / rationale: Production ramp timeline observation; no canonical Alpha mechanism materially expressed.
- Source authority: `docs/audit_artifacts/item2_blind_holdout5_{frozen.csv,review_frozen.csv,comparison.csv}`

---

### Review Row holdout5-105

- Ticker: NVDA
- Run ID: `0e044e37-862c-43be-871c-31012cd660e7`
- Source / agent role: bull_researcher
- Evidence ID / claim ID: `0e044e37-862c-43be-871c-31012cd660e7:bull_researcher:investment_debate_state.bull_history:claim:173`
- Original sentence:
  > The alarm requires evidence of demand deceleration.

- Expected Alpha: NONE
- System-mapped Alpha: NONE
- Alpha Match: **PASS**

- Expected polarity: NOT_ELIGIBLE
- System polarity: NOT_ELIGIBLE
- Polarity eligible: No
- Polarity Match: **NOT_ELIGIBLE**
- Critical support/opposition reversal: No

- Human review judgment: NOT_MATERIAL_ALPHA_FIT
- Review note / rationale: Generic conditional statement about demand deceleration; no substantive Alpha mechanism present.
- Source authority: `docs/audit_artifacts/item2_blind_holdout5_{frozen.csv,review_frozen.csv,comparison.csv}`

---

### Review Row holdout5-106

- Ticker: NVDA
- Run ID: `0e044e37-862c-43be-871c-31012cd660e7`
- Source / agent role: conservative_risk_analyst
- Evidence ID / claim ID: `0e044e37-862c-43be-871c-31012cd660e7:conservative_risk_analyst:risk_debate_state.conservative_history:claim:161`
- Original sentence:
  > Conservative Analyst: Let me be precise about where we are in this debate, because both my colleagues have made their most sophisticated arguments and I think the moment calls for an equally precise response rather than a retreat to generalities.

- Expected Alpha: NONE
- System-mapped Alpha: NONE
- Alpha Match: **PASS**

- Expected polarity: NOT_ELIGIBLE
- System polarity: NOT_ELIGIBLE
- Polarity eligible: No
- Polarity Match: **NOT_ELIGIBLE**
- Critical support/opposition reversal: No

- Human review judgment: NOT_MATERIAL_ALPHA_FIT
- Review note / rationale: Meta-commentary about analytical debate; no canonical Alpha mechanism expressed.
- Source authority: `docs/audit_artifacts/item2_blind_holdout5_{frozen.csv,review_frozen.csv,comparison.csv}`

---

### Review Row holdout5-107

- Ticker: NVDA
- Run ID: `0e044e37-862c-43be-871c-31012cd660e7`
- Source / agent role: conservative_risk_analyst
- Evidence ID / claim ID: `0e044e37-862c-43be-871c-31012cd660e7:conservative_risk_analyst:risk_debate_state.conservative_history:claim:166`
- Original sentence:
  > It is undeployed cash that has no mechanical relationship to the loss on the deployed position.

- Expected Alpha: NONE
- System-mapped Alpha: NONE
- Alpha Match: **PASS**

- Expected polarity: NOT_ELIGIBLE
- System polarity: NOT_ELIGIBLE
- Polarity eligible: No
- Polarity Match: **NOT_ELIGIBLE**
- Critical support/opposition reversal: No

- Human review judgment: NOT_MATERIAL_ALPHA_FIT
- Review note / rationale: Abstract statement about cash vs. deployed position; no canonical Alpha mechanism present.
- Source authority: `docs/audit_artifacts/item2_blind_holdout5_{frozen.csv,review_frozen.csv,comparison.csv}`

---

### Review Row holdout5-108

- Ticker: NVDA
- Run ID: `0e044e37-862c-43be-871c-31012cd660e7`
- Source / agent role: conservative_risk_analyst
- Evidence ID / claim ID: `0e044e37-862c-43be-871c-31012cd660e7:conservative_risk_analyst:risk_debate_state.conservative_history:claim:49`
- Original sentence:
  > It does not protect you from gap risk.

- Expected Alpha: NONE
- System-mapped Alpha: NONE
- Alpha Match: **PASS**

- Expected polarity: NOT_ELIGIBLE
- System polarity: NOT_ELIGIBLE
- Polarity eligible: No
- Polarity Match: **NOT_ELIGIBLE**
- Critical support/opposition reversal: No

- Human review judgment: NOT_MATERIAL_ALPHA_FIT
- Review note / rationale: Generic risk statement about gap risk; no canonical Alpha mechanism materially present.
- Source authority: `docs/audit_artifacts/item2_blind_holdout5_{frozen.csv,review_frozen.csv,comparison.csv}`

---

### Review Row holdout5-109

- Ticker: NVDA
- Run ID: `0e044e37-862c-43be-871c-31012cd660e7`
- Source / agent role: fundamental_agent
- Evidence ID / claim ID: `0e044e37-862c-43be-871c-31012cd660e7:fundamental_agent:fundamentals_report:claim:2`
- Original sentence:
  > Analysis Date: July 30, 2026 | Exchange: NASDAQ (NMS) | Sector: Technology / Semiconductors

- Expected Alpha: NONE
- System-mapped Alpha: NONE
- Alpha Match: **PASS**

- Expected polarity: NOT_ELIGIBLE
- System polarity: NOT_ELIGIBLE
- Polarity eligible: No
- Polarity Match: **NOT_ELIGIBLE**
- Critical support/opposition reversal: No

- Human review judgment: NOT_MATERIAL_ALPHA_FIT
- Review note / rationale: Pure metadata header; no economic or causal mechanism expressed.
- Source authority: `docs/audit_artifacts/item2_blind_holdout5_{frozen.csv,review_frozen.csv,comparison.csv}`

---

### Review Row holdout5-110

- Ticker: NVDA
- Run ID: `0e044e37-862c-43be-871c-31012cd660e7`
- Source / agent role: neutral_risk_analyst
- Evidence ID / claim ID: `0e044e37-862c-43be-871c-31012cd660e7:neutral_risk_analyst:risk_debate_state.neutral_history:claim:166`
- Original sentence:
  > But the question is not whether the reserve mechanically offsets the loss.

- Expected Alpha: NONE
- System-mapped Alpha: NONE
- Alpha Match: **PASS**

- Expected polarity: NOT_ELIGIBLE
- System polarity: NOT_ELIGIBLE
- Polarity eligible: No
- Polarity Match: **NOT_ELIGIBLE**
- Critical support/opposition reversal: No

- Human review judgment: NOT_MATERIAL_ALPHA_FIT
- Review note / rationale: Abstract rhetorical statement about reserves and losses; no canonical Alpha mechanism present.
- Source authority: `docs/audit_artifacts/item2_blind_holdout5_{frozen.csv,review_frozen.csv,comparison.csv}`

---

### Review Row holdout5-111

- Ticker: NVDA
- Run ID: `4ca7dafa-6ac1-4d94-add0-f6f93b1af150`
- Source / agent role: bear_researcher
- Evidence ID / claim ID: `4ca7dafa-6ac1-4d94-add0-f6f93b1af150:bear_researcher:investment_debate_state.bear_history:claim:59`
- Original sentence:
  > That's a permanently lost market.

- Expected Alpha: NONE
- System-mapped Alpha: NONE
- Alpha Match: **PASS**

- Expected polarity: NOT_ELIGIBLE
- System polarity: NOT_ELIGIBLE
- Polarity eligible: No
- Polarity Match: **NOT_ELIGIBLE**
- Critical support/opposition reversal: No

- Human review judgment: NOT_MATERIAL_ALPHA_FIT
- Review note / rationale: Bare assertion with no mechanism, context, or causal detail present.
- Source authority: `docs/audit_artifacts/item2_blind_holdout5_{frozen.csv,review_frozen.csv,comparison.csv}`

---

### Review Row holdout5-112

- Ticker: NVDA
- Run ID: `4ca7dafa-6ac1-4d94-add0-f6f93b1af150`
- Source / agent role: fundamental_agent
- Evidence ID / claim ID: `4ca7dafa-6ac1-4d94-add0-f6f93b1af150:fundamental_agent:fundamentals_report:claim:40`
- Original sentence:
  > Investing outflows surging: Q1 FY2027 saw $26.43B in investing activities, including $13.17B in business acquisitions and $26.58B in investment securities purchases — NVDA is deploying its massive cash war chest.

- Expected Alpha: NONE
- System-mapped Alpha: NONE
- Alpha Match: **PASS**

- Expected polarity: NOT_ELIGIBLE
- System polarity: NOT_ELIGIBLE
- Polarity eligible: No
- Polarity Match: **NOT_ELIGIBLE**
- Critical support/opposition reversal: No

- Human review judgment: NOT_MATERIAL_ALPHA_FIT
- Review note / rationale: Describes cash deployment into acquisitions and securities; no canonical Alpha mechanism materially expressed.
- Source authority: `docs/audit_artifacts/item2_blind_holdout5_{frozen.csv,review_frozen.csv,comparison.csv}`

---

### Review Row holdout5-113

- Ticker: NVDA
- Run ID: `4ca7dafa-6ac1-4d94-add0-f6f93b1af150`
- Source / agent role: market_agent
- Evidence ID / claim ID: `4ca7dafa-6ac1-4d94-add0-f6f93b1af150:market_agent:market_report:claim:9`
- Original sentence:
  > The 200-SMA is rising steadily (from $189.48 on June 17 to $192.21 today) and remains well below the current price, providing strong structural long-term support.

- Expected Alpha: NONE
- System-mapped Alpha: NONE
- Alpha Match: **PASS**

- Expected polarity: NOT_ELIGIBLE
- System polarity: NOT_ELIGIBLE
- Polarity eligible: No
- Polarity Match: **NOT_ELIGIBLE**
- Critical support/opposition reversal: No

- Human review judgment: NOT_MATERIAL_ALPHA_FIT
- Review note / rationale: Pure technical indicator (200-SMA support); no canonical Alpha mechanism present.
- Source authority: `docs/audit_artifacts/item2_blind_holdout5_{frozen.csv,review_frozen.csv,comparison.csv}`

---

### Review Row holdout5-114

- Ticker: NVDA
- Run ID: `4ca7dafa-6ac1-4d94-add0-f6f93b1af150`
- Source / agent role: neutral_risk_analyst
- Evidence ID / claim ID: `4ca7dafa-6ac1-4d94-add0-f6f93b1af150:neutral_risk_analyst:risk_debate_state.neutral_history:claim:32`
- Original sentence:
  > The 200-SMA support is real.

- Expected Alpha: NONE
- System-mapped Alpha: NONE
- Alpha Match: **PASS**

- Expected polarity: NOT_ELIGIBLE
- System polarity: NOT_ELIGIBLE
- Polarity eligible: No
- Polarity Match: **NOT_ELIGIBLE**
- Critical support/opposition reversal: No

- Human review judgment: NOT_MATERIAL_ALPHA_FIT
- Review note / rationale: Bare technical support reference only; no canonical Alpha mechanism present.
- Source authority: `docs/audit_artifacts/item2_blind_holdout5_{frozen.csv,review_frozen.csv,comparison.csv}`

---

### Review Row holdout5-115

- Ticker: NVDA
- Run ID: `4ca7dafa-6ac1-4d94-add0-f6f93b1af150`
- Source / agent role: neutral_risk_analyst
- Evidence ID / claim ID: `4ca7dafa-6ac1-4d94-add0-f6f93b1af150:neutral_risk_analyst:risk_debate_state.neutral_history:claim:56`
- Original sentence:
  > The stop loss that both analysts are effectively anchoring to at 192 is not a guaranteed floor.

- Expected Alpha: NONE
- System-mapped Alpha: NONE
- Alpha Match: **PASS**

- Expected polarity: NOT_ELIGIBLE
- System polarity: NOT_ELIGIBLE
- Polarity eligible: No
- Polarity Match: **NOT_ELIGIBLE**
- Critical support/opposition reversal: No

- Human review judgment: NOT_MATERIAL_ALPHA_FIT
- Review note / rationale: Commentary on stop-loss anchoring; purely technical framing, no canonical Alpha mechanism.
- Source authority: `docs/audit_artifacts/item2_blind_holdout5_{frozen.csv,review_frozen.csv,comparison.csv}`

---

### Review Row holdout5-116

- Ticker: NVDA
- Run ID: `4ca7dafa-6ac1-4d94-add0-f6f93b1af150`
- Source / agent role: news_agent
- Evidence ID / claim ID: `4ca7dafa-6ac1-4d94-add0-f6f93b1af150:news_agent:news_report:claim:34`
- Original sentence:
  > Jefferies analysts are eyeing a potential AMD-Anthropic deal.

- Expected Alpha: A101
- System-mapped Alpha: A101
- Alpha Match: **PASS**

- Expected polarity: mentions_alpha
- System polarity: mentions_alpha
- Polarity eligible: Yes
- Polarity Match: **PASS**
- Critical support/opposition reversal: No

- Human review judgment: DIRECTIONALLY_CLEAR (no formal adjudication record; frozen blind label stands as ground truth)
- Review note / rationale: AMD-Anthropic deal implies AI accelerator competition with NVDA; AI training/adoption mechanism implied but not elaborated.
- Source authority: `docs/audit_artifacts/item2_blind_holdout5_{frozen.csv,review_frozen.csv,comparison.csv}`

---

### Review Row holdout5-117

- Ticker: NVDA
- Run ID: `4ca7dafa-6ac1-4d94-add0-f6f93b1af150`
- Source / agent role: trader
- Evidence ID / claim ID: `4ca7dafa-6ac1-4d94-add0-f6f93b1af150:trader:trader_investment_plan:claim:5`
- Original sentence:
  > Position Sizing: 4–6% of a diversified equity portfolio (up to 8–10% for high-conviction growth portfolios).

- Expected Alpha: NONE
- System-mapped Alpha: NONE
- Alpha Match: **PASS**

- Expected polarity: NOT_ELIGIBLE
- System polarity: NOT_ELIGIBLE
- Polarity eligible: No
- Polarity Match: **NOT_ELIGIBLE**
- Critical support/opposition reversal: No

- Human review judgment: NOT_MATERIAL_ALPHA_FIT
- Review note / rationale: Portfolio position sizing guidance only; no canonical Alpha mechanism expressed.
- Source authority: `docs/audit_artifacts/item2_blind_holdout5_{frozen.csv,review_frozen.csv,comparison.csv}`

---

### Review Row holdout5-118

- Ticker: NVDA
- Run ID: `5ffe121a-68fd-473b-82b5-c9465332d8a2`
- Source / agent role: aggressive_risk_analyst
- Evidence ID / claim ID: `5ffe121a-68fd-473b-82b5-c9465332d8a2:aggressive_risk_analyst:risk_debate_state.aggressive_history:claim:14`
- Original sentence:
  > On the "Hawkish Macro" and Valuation Risk: The 86% probability of no rate cuts in 2026 is a headwind, but you are treating it as a death knell.

- Expected Alpha: A001
- System-mapped Alpha: A001
- Alpha Match: **PASS**

- Expected polarity: mentions_alpha
- System polarity: mentions_alpha
- Polarity eligible: Yes
- Polarity Match: **PASS**
- Critical support/opposition reversal: No

- Human review judgment: DIRECTIONALLY_CLEAR (no formal adjudication record; frozen blind label stands as ground truth)
- Review note / rationale: 86% probability of no rate cuts in 2026 explicitly framed as valuation headwind; rate cut mechanism directly discussed without clear net direction.
- Source authority: `docs/audit_artifacts/item2_blind_holdout5_{frozen.csv,review_frozen.csv,comparison.csv}`

---

### Review Row holdout5-119

- Ticker: NVDA
- Run ID: `5ffe121a-68fd-473b-82b5-c9465332d8a2`
- Source / agent role: bull_researcher
- Evidence ID / claim ID: `5ffe121a-68fd-473b-82b5-c9465332d8a2:bull_researcher:investment_debate_state.bull_history:claim:51`
- Original sentence:
  > This is a stock in an uptrend, not a stock on the verge of a breakdown.

- Expected Alpha: NONE
- System-mapped Alpha: NONE
- Alpha Match: **PASS**

- Expected polarity: NOT_ELIGIBLE
- System polarity: NOT_ELIGIBLE
- Polarity eligible: No
- Polarity Match: **NOT_ELIGIBLE**
- Critical support/opposition reversal: No

- Human review judgment: NOT_MATERIAL_ALPHA_FIT
- Review note / rationale: Generic bullish trend assertion; technical momentum only, no canonical Alpha mechanism.
- Source authority: `docs/audit_artifacts/item2_blind_holdout5_{frozen.csv,review_frozen.csv,comparison.csv}`

---

### Review Row holdout5-120

- Ticker: NVDA
- Run ID: `5ffe121a-68fd-473b-82b5-c9465332d8a2`
- Source / agent role: bull_researcher
- Evidence ID / claim ID: `5ffe121a-68fd-473b-82b5-c9465332d8a2:bull_researcher:investment_debate_state.bull_history:claim:92`
- Original sentence:
  > Metric: Forward P/E; Value: 17.57x; Bull Signal: Undervalued for 85% growth

- Expected Alpha: A304
- System-mapped Alpha: A304
- Alpha Match: **PASS**

- Expected polarity: opposes_alpha
- System polarity: opposes_alpha
- Polarity eligible: Yes
- Polarity Match: **PASS**
- Critical support/opposition reversal: No

- Human review judgment: DIRECTIONALLY_CLEAR (no formal adjudication record; frozen blind label stands as ground truth)
- Review note / rationale: 17.57x forward P/E argued as undervalued relative to 85% growth; directly rebuts multiple compression thesis.
- Source authority: `docs/audit_artifacts/item2_blind_holdout5_{frozen.csv,review_frozen.csv,comparison.csv}`

---

### Review Row holdout5-121

- Ticker: NVDA
- Run ID: `e3eb3909-3744-4a02-9b32-b225cf6ef665`
- Source / agent role: bear_researcher
- Evidence ID / claim ID: `e3eb3909-3744-4a02-9b32-b225cf6ef665:bear_researcher:investment_debate_state.bear_history:claim:107`
- Original sentence:
  > If you don't, don't chase it here.

- Expected Alpha: NONE
- System-mapped Alpha: NONE
- Alpha Match: **PASS**

- Expected polarity: NOT_ELIGIBLE
- System polarity: NOT_ELIGIBLE
- Polarity eligible: No
- Polarity Match: **NOT_ELIGIBLE**
- Critical support/opposition reversal: No

- Human review judgment: NOT_MATERIAL_ALPHA_FIT
- Review note / rationale: Generic trading advice with no canonical Alpha mechanism present
- Source authority: `docs/audit_artifacts/item2_blind_holdout5_{frozen.csv,review_frozen.csv,comparison.csv}`

---

### Review Row holdout5-122

- Ticker: NVDA
- Run ID: `e3eb3909-3744-4a02-9b32-b225cf6ef665`
- Source / agent role: market_agent
- Evidence ID / claim ID: `e3eb3909-3744-4a02-9b32-b225cf6ef665:market_agent:market_report:claim:50`
- Original sentence:
  > This ATR level implies a reasonable daily trading range of roughly ±$7.50, which traders should factor into stop-loss placement and position sizing.

- Expected Alpha: NONE
- System-mapped Alpha: NONE
- Alpha Match: **PASS**

- Expected polarity: NOT_ELIGIBLE
- System polarity: NOT_ELIGIBLE
- Polarity eligible: No
- Polarity Match: **NOT_ELIGIBLE**
- Critical support/opposition reversal: No

- Human review judgment: NOT_MATERIAL_ALPHA_FIT
- Review note / rationale: ATR-based position sizing and stop-loss; purely technical risk management, no Alpha mechanism
- Source authority: `docs/audit_artifacts/item2_blind_holdout5_{frozen.csv,review_frozen.csv,comparison.csv}`

---

### Review Row holdout5-123

- Ticker: NVDA
- Run ID: `e3eb3909-3744-4a02-9b32-b225cf6ef665`
- Source / agent role: research_manager
- Evidence ID / claim ID: `e3eb3909-3744-4a02-9b32-b225cf6ef665:research_manager:investment_plan:claim:12`
- Original sentence:
  > And the macro backdrop — no rate cuts in 2026, entrenched inflation, rising oil — is a real headwind for a 2.2 beta stock at a $5.27 trillion market cap.

- Expected Alpha: A001
- System-mapped Alpha: A001
- Alpha Match: **PASS**

- Expected polarity: opposes_alpha
- System polarity: opposes_alpha
- Polarity eligible: Yes
- Polarity Match: **PASS**
- Critical support/opposition reversal: No

- Human review judgment: DIRECTIONALLY_CLEAR (no formal adjudication record; frozen blind label stands as ground truth)
- Review note / rationale: No rate cuts, entrenched inflation directly opposes A001 rate-cut tailwind for high-beta growth stock
- Source authority: `docs/audit_artifacts/item2_blind_holdout5_{frozen.csv,review_frozen.csv,comparison.csv}`

---

### Review Row holdout5-124

- Ticker: NVDA
- Run ID: `e434f80b-e4d0-4b09-9471-d84532659de5`
- Source / agent role: conservative_risk_analyst
- Evidence ID / claim ID: `e434f80b-e4d0-4b09-9471-d84532659de5:conservative_risk_analyst:risk_debate_state.conservative_history:claim:2`
- Original sentence:
  > Let me address my colleagues directly, because the aggressive analyst's enthusiasm, while grounded in real fundamental strength, is precisely the kind of thinking that creates portfolio-destroying drawdowns.

- Expected Alpha: A304
- System-mapped Alpha: A304
- Alpha Match: **PASS**

- Expected polarity: supports_alpha
- System polarity: supports_alpha
- Polarity eligible: Yes
- Polarity Match: **PASS**
- Critical support/opposition reversal: No

- Human review judgment: DIRECTIONALLY_CLEAR (no formal adjudication record; frozen blind label stands as ground truth)
- Review note / rationale: Warns enthusiasm on strong fundamentals creates drawdown risk; supports multiple compression thesis
- Source authority: `docs/audit_artifacts/item2_blind_holdout5_{frozen.csv,review_frozen.csv,comparison.csv}`

---

### Review Row holdout5-125

- Ticker: NVDA
- Run ID: `e434f80b-e4d0-4b09-9471-d84532659de5`
- Source / agent role: portfolio_manager
- Evidence ID / claim ID: `e434f80b-e4d0-4b09-9471-d84532659de5:portfolio_manager:final_trade_decision:claim:2`
- Original sentence:
  > Start with a smaller probing tranche (25-30% of target) and add on confirmed support holds, with a technically justified stop just below the support confluence at $187.

- Expected Alpha: NONE
- System-mapped Alpha: NONE
- Alpha Match: **PASS**

- Expected polarity: NOT_ELIGIBLE
- System polarity: NOT_ELIGIBLE
- Polarity eligible: No
- Polarity Match: **NOT_ELIGIBLE**
- Critical support/opposition reversal: No

- Human review judgment: NOT_MATERIAL_ALPHA_FIT
- Review note / rationale: Technical position sizing and entry strategy; no canonical Alpha mechanism present
- Source authority: `docs/audit_artifacts/item2_blind_holdout5_{frozen.csv,review_frozen.csv,comparison.csv}`

---

### Review Row holdout5-126

- Ticker: QQQ
- Run ID: `a364e0ee-3bb4-4032-88b7-5cd82e379805`
- Source / agent role: aggressive_risk_analyst
- Evidence ID / claim ID: `a364e0ee-3bb4-4032-88b7-5cd82e379805:aggressive_risk_analyst:risk_debate_state.aggressive_history:claim:7`
- Original sentence:
  > The MACD histogram has improved from -4.98 to -2.56 in just two sessions, and the RSI has ripped from a near-oversold 32.43 to a neutral 45.12.

- Expected Alpha: NONE
- System-mapped Alpha: NONE
- Alpha Match: **PASS**

- Expected polarity: NOT_ELIGIBLE
- System polarity: NOT_ELIGIBLE
- Polarity eligible: No
- Polarity Match: **NOT_ELIGIBLE**
- Critical support/opposition reversal: No

- Human review judgment: NOT_MATERIAL_ALPHA_FIT
- Review note / rationale: MACD and RSI readings only; pure technical indicators, no canonical Alpha mechanism
- Source authority: `docs/audit_artifacts/item2_blind_holdout5_{frozen.csv,review_frozen.csv,comparison.csv}`

---

### Review Row holdout5-127

- Ticker: QQQ
- Run ID: `a364e0ee-3bb4-4032-88b7-5cd82e379805`
- Source / agent role: aggressive_risk_analyst
- Evidence ID / claim ID: `a364e0ee-3bb4-4032-88b7-5cd82e379805:aggressive_risk_analyst:risk_debate_state.aggressive_history:claim:8`
- Original sentence:
  > This is not a market in freefall; it is a market that has found its footing and is coiling for a move higher.

- Expected Alpha: NONE
- System-mapped Alpha: NONE
- Alpha Match: **PASS**

- Expected polarity: NOT_ELIGIBLE
- System polarity: NOT_ELIGIBLE
- Polarity eligible: No
- Polarity Match: **NOT_ELIGIBLE**
- Critical support/opposition reversal: No

- Human review judgment: NOT_MATERIAL_ALPHA_FIT
- Review note / rationale: Generic bullish technical language; no canonical Alpha causal mechanism present
- Source authority: `docs/audit_artifacts/item2_blind_holdout5_{frozen.csv,review_frozen.csv,comparison.csv}`

---

### Review Row holdout5-128

- Ticker: QQQ
- Run ID: `a364e0ee-3bb4-4032-88b7-5cd82e379805`
- Source / agent role: bear_researcher
- Evidence ID / claim ID: `a364e0ee-3bb4-4032-88b7-5cd82e379805:bear_researcher:investment_debate_state.bear_history:claim:32`
- Original sentence:
  > When the discount rate rises—and it is rising—the present value of those future earnings falls.

- Expected Alpha: A001
- System-mapped Alpha: A001
- Alpha Match: **PASS**

- Expected polarity: opposes_alpha
- System polarity: opposes_alpha
- Polarity eligible: Yes
- Polarity Match: **PASS**
- Critical support/opposition reversal: No

- Human review judgment: DIRECTIONALLY_CLEAR (no formal adjudication record; frozen blind label stands as ground truth)
- Review note / rationale: Rising discount rate explicitly lowers present value of future earnings; directly opposes A001 thesis
- Source authority: `docs/audit_artifacts/item2_blind_holdout5_{frozen.csv,review_frozen.csv,comparison.csv}`

---

### Review Row holdout5-129

- Ticker: QQQ
- Run ID: `a364e0ee-3bb4-4032-88b7-5cd82e379805`
- Source / agent role: bear_researcher
- Evidence ID / claim ID: `a364e0ee-3bb4-4032-88b7-5cd82e379805:bear_researcher:investment_debate_state.bear_history:claim:57`
- Original sentence:
  > This is not a tailwind; it is a two-sided coin, and you are only looking at one side.

- Expected Alpha: NONE
- System-mapped Alpha: NONE
- Alpha Match: **PASS**

- Expected polarity: NOT_ELIGIBLE
- System polarity: NOT_ELIGIBLE
- Polarity eligible: No
- Polarity Match: **NOT_ELIGIBLE**
- Critical support/opposition reversal: No

- Human review judgment: NOT_MATERIAL_ALPHA_FIT
- Review note / rationale: Vague cautionary rhetoric with no identifiable canonical Alpha mechanism expressed
- Source authority: `docs/audit_artifacts/item2_blind_holdout5_{frozen.csv,review_frozen.csv,comparison.csv}`

---

### Review Row holdout5-130

- Ticker: QQQ
- Run ID: `a364e0ee-3bb4-4032-88b7-5cd82e379805`
- Source / agent role: bear_researcher
- Evidence ID / claim ID: `a364e0ee-3bb4-4032-88b7-5cd82e379805:bear_researcher:investment_debate_state.bear_history:claim:85`
- Original sentence:
  > The 200-day SMA at $643.83 is the real floor, and we are 6.9% above it.

- Expected Alpha: NONE
- System-mapped Alpha: NONE
- Alpha Match: **PASS**

- Expected polarity: NOT_ELIGIBLE
- System polarity: NOT_ELIGIBLE
- Polarity eligible: No
- Polarity Match: **NOT_ELIGIBLE**
- Critical support/opposition reversal: No

- Human review judgment: NOT_MATERIAL_ALPHA_FIT
- Review note / rationale: 200-day SMA support level; purely technical indicator, no canonical Alpha mechanism
- Source authority: `docs/audit_artifacts/item2_blind_holdout5_{frozen.csv,review_frozen.csv,comparison.csv}`

---

### Review Row holdout5-131

- Ticker: QQQ
- Run ID: `a364e0ee-3bb4-4032-88b7-5cd82e379805`
- Source / agent role: bull_researcher
- Evidence ID / claim ID: `a364e0ee-3bb4-4032-88b7-5cd82e379805:bull_researcher:investment_debate_state.bull_history:claim:28`
- Original sentence:
  > The prediction markets you cite (89% odds of no cuts) are backward-looking.

- Expected Alpha: A001
- System-mapped Alpha: A001
- Alpha Match: **PASS**

- Expected polarity: mentions_alpha
- System polarity: mentions_alpha
- Polarity eligible: Yes
- Polarity Match: **PASS**
- Critical support/opposition reversal: No

- Human review judgment: DIRECTIONALLY_CLEAR (no formal adjudication record; frozen blind label stands as ground truth)
- Review note / rationale: References rate cut odds (89% no cuts) but dismisses market signal as backward-looking; mentions A001 mechanism without clear stance
- Source authority: `docs/audit_artifacts/item2_blind_holdout5_{frozen.csv,review_frozen.csv,comparison.csv}`

---

### Review Row holdout5-132

- Ticker: QQQ
- Run ID: `a364e0ee-3bb4-4032-88b7-5cd82e379805`
- Source / agent role: bull_researcher
- Evidence ID / claim ID: `a364e0ee-3bb4-4032-88b7-5cd82e379805:bull_researcher:investment_debate_state.bull_history:claim:3`
- Original sentence:
  > I appreciate your thorough analysis, but I believe you are looking at the rearview mirror while the road ahead is wide open.

- Expected Alpha: NONE
- System-mapped Alpha: NONE
- Alpha Match: **PASS**

- Expected polarity: NOT_ELIGIBLE
- System polarity: NOT_ELIGIBLE
- Polarity eligible: No
- Polarity Match: **NOT_ELIGIBLE**
- Critical support/opposition reversal: No

- Human review judgment: NOT_MATERIAL_ALPHA_FIT
- Review note / rationale: Generic metaphor about forward vs backward-looking view; no canonical Alpha mechanism expressed
- Source authority: `docs/audit_artifacts/item2_blind_holdout5_{frozen.csv,review_frozen.csv,comparison.csv}`

---

### Review Row holdout5-133

- Ticker: QQQ
- Run ID: `a364e0ee-3bb4-4032-88b7-5cd82e379805`
- Source / agent role: bull_researcher
- Evidence ID / claim ID: `a364e0ee-3bb4-4032-88b7-5cd82e379805:bull_researcher:investment_debate_state.bull_history:claim:42`
- Original sentence:
  > Amazon alone is spending $220 billion in 2026.

- Expected Alpha: A103
- System-mapped Alpha: A103
- Alpha Match: **PASS**

- Expected polarity: supports_alpha
- System polarity: supports_alpha
- Polarity eligible: Yes
- Polarity Match: **PASS**
- Critical support/opposition reversal: No

- Human review judgment: DIRECTIONALLY_CLEAR (no formal adjudication record; frozen blind label stands as ground truth)
- Review note / rationale: Amazon $220B capex spend in 2026 directly supports AI infrastructure buildout demand thesis
- Source authority: `docs/audit_artifacts/item2_blind_holdout5_{frozen.csv,review_frozen.csv,comparison.csv}`

---

### Review Row holdout5-134

- Ticker: QQQ
- Run ID: `a364e0ee-3bb4-4032-88b7-5cd82e379805`
- Source / agent role: bull_researcher
- Evidence ID / claim ID: `a364e0ee-3bb4-4032-88b7-5cd82e379805:bull_researcher:investment_debate_state.bull_history:claim:64`
- Original sentence:
  > The bear case is built on short-term technical noise and a stale macro narrative.

- Expected Alpha: NONE
- System-mapped Alpha: NONE
- Alpha Match: **PASS**

- Expected polarity: NOT_ELIGIBLE
- System polarity: NOT_ELIGIBLE
- Polarity eligible: No
- Polarity Match: **NOT_ELIGIBLE**
- Critical support/opposition reversal: No

- Human review judgment: NOT_MATERIAL_ALPHA_FIT
- Review note / rationale: Generic dismissal of bear case as technical noise and stale narrative; no specific Alpha mechanism
- Source authority: `docs/audit_artifacts/item2_blind_holdout5_{frozen.csv,review_frozen.csv,comparison.csv}`

---

### Review Row holdout5-135

- Ticker: QQQ
- Run ID: `a364e0ee-3bb4-4032-88b7-5cd82e379805`
- Source / agent role: conservative_risk_analyst
- Evidence ID / claim ID: `a364e0ee-3bb4-4032-88b7-5cd82e379805:conservative_risk_analyst:risk_debate_state.conservative_history:claim:42`
- Original sentence:
  > The Verdict: A Cautious, Phased Approach is the Only Prudent Path

- Expected Alpha: NONE
- System-mapped Alpha: NONE
- Alpha Match: **PASS**

- Expected polarity: NOT_ELIGIBLE
- System polarity: NOT_ELIGIBLE
- Polarity eligible: No
- Polarity Match: **NOT_ELIGIBLE**
- Critical support/opposition reversal: No

- Human review judgment: NOT_MATERIAL_ALPHA_FIT
- Review note / rationale: Editorial verdict label only; no causal or economic mechanism expressed
- Source authority: `docs/audit_artifacts/item2_blind_holdout5_{frozen.csv,review_frozen.csv,comparison.csv}`

---

### Review Row holdout5-136

- Ticker: QQQ
- Run ID: `a364e0ee-3bb4-4032-88b7-5cd82e379805`
- Source / agent role: fundamental_agent
- Evidence ID / claim ID: `a364e0ee-3bb4-4032-88b7-5cd82e379805:fundamental_agent:fundamentals_report:claim:25`
- Original sentence:
  > The 52-week range spans from $551.68 (low) to $748.65 (high), representing a substantial 35.7% gain from the low.

- Expected Alpha: NONE
- System-mapped Alpha: NONE
- Alpha Match: **PASS**

- Expected polarity: NOT_ELIGIBLE
- System polarity: NOT_ELIGIBLE
- Polarity eligible: No
- Polarity Match: **NOT_ELIGIBLE**
- Critical support/opposition reversal: No

- Human review judgment: NOT_MATERIAL_ALPHA_FIT
- Review note / rationale: 52-week price range statistics only; technical price data, no canonical Alpha mechanism
- Source authority: `docs/audit_artifacts/item2_blind_holdout5_{frozen.csv,review_frozen.csv,comparison.csv}`

---

### Review Row holdout5-137

- Ticker: QQQ
- Run ID: `a364e0ee-3bb4-4032-88b7-5cd82e379805`
- Source / agent role: fundamental_agent
- Evidence ID / claim ID: `a364e0ee-3bb4-4032-88b7-5cd82e379805:fundamental_agent:fundamentals_report:claim:39`
- Original sentence:
  > Consumer Discretionary (e-commerce, streaming)

- Expected Alpha: NONE
- System-mapped Alpha: NONE
- Alpha Match: **PASS**

- Expected polarity: NOT_ELIGIBLE
- System polarity: NOT_ELIGIBLE
- Polarity eligible: No
- Polarity Match: **NOT_ELIGIBLE**
- Critical support/opposition reversal: No

- Human review judgment: NOT_MATERIAL_ALPHA_FIT
- Review note / rationale: Bare sector label fragment; no mechanism, thesis, or causal content present
- Source authority: `docs/audit_artifacts/item2_blind_holdout5_{frozen.csv,review_frozen.csv,comparison.csv}`

---

### Review Row holdout5-138

- Ticker: QQQ
- Run ID: `a364e0ee-3bb4-4032-88b7-5cd82e379805`
- Source / agent role: market_agent
- Evidence ID / claim ID: `a364e0ee-3bb4-4032-88b7-5cd82e379805:market_agent:market_report:claim:67`
- Original sentence:
  > These cover trend (50/200 SMA, 10 EMA), momentum (MACD, RSI), volatility (Bollinger, ATR), and volume (VWMA) — four distinct dimensions without redundancy.

- Expected Alpha: NONE
- System-mapped Alpha: NONE
- Alpha Match: **PASS**

- Expected polarity: NOT_ELIGIBLE
- System polarity: NOT_ELIGIBLE
- Polarity eligible: No
- Polarity Match: **NOT_ELIGIBLE**
- Critical support/opposition reversal: No

- Human review judgment: NOT_MATERIAL_ALPHA_FIT
- Review note / rationale: Pure technical indicator enumeration (SMA, MACD, RSI, Bollinger); no canonical Alpha mechanism
- Source authority: `docs/audit_artifacts/item2_blind_holdout5_{frozen.csv,review_frozen.csv,comparison.csv}`

---

### Review Row holdout5-139

- Ticker: QQQ
- Run ID: `a364e0ee-3bb4-4032-88b7-5cd82e379805`
- Source / agent role: market_agent
- Evidence ID / claim ID: `a364e0ee-3bb4-4032-88b7-5cd82e379805:market_agent:market_report:claim:77`
- Original sentence:
  > A break below would target the 200 SMA (643.83).

- Expected Alpha: NONE
- System-mapped Alpha: NONE
- Alpha Match: **PASS**

- Expected polarity: NOT_ELIGIBLE
- System polarity: NOT_ELIGIBLE
- Polarity eligible: No
- Polarity Match: **NOT_ELIGIBLE**
- Critical support/opposition reversal: No

- Human review judgment: NOT_MATERIAL_ALPHA_FIT
- Review note / rationale: Technical support/target level reference only; no canonical Alpha mechanism present
- Source authority: `docs/audit_artifacts/item2_blind_holdout5_{frozen.csv,review_frozen.csv,comparison.csv}`

---

### Review Row holdout5-140

- Ticker: QQQ
- Run ID: `a364e0ee-3bb4-4032-88b7-5cd82e379805`
- Source / agent role: neutral_risk_analyst
- Evidence ID / claim ID: `a364e0ee-3bb4-4032-88b7-5cd82e379805:neutral_risk_analyst:risk_debate_state.neutral_history:claim:15`
- Original sentence:
  > The Aggressive Analyst is betting on a "Monday morning deal," but that is speculation, not analysis.

- Expected Alpha: NONE
- System-mapped Alpha: NONE
- Alpha Match: **PASS**

- Expected polarity: NOT_ELIGIBLE
- System polarity: NOT_ELIGIBLE
- Polarity eligible: No
- Polarity Match: **NOT_ELIGIBLE**
- Critical support/opposition reversal: No

- Human review judgment: NOT_MATERIAL_ALPHA_FIT
- Review note / rationale: Editorial critique of speculation vs analysis; no causal economic mechanism expressed
- Source authority: `docs/audit_artifacts/item2_blind_holdout5_{frozen.csv,review_frozen.csv,comparison.csv}`

---

### Review Row holdout5-141

- Ticker: QQQ
- Run ID: `a364e0ee-3bb4-4032-88b7-5cd82e379805`
- Source / agent role: neutral_risk_analyst
- Evidence ID / claim ID: `a364e0ee-3bb4-4032-88b7-5cd82e379805:neutral_risk_analyst:risk_debate_state.neutral_history:claim:48`
- Original sentence:
  > To mitigate this, we should not deploy the full 70% until the geopolitical situation is clearer.

- Expected Alpha: NONE
- System-mapped Alpha: NONE
- Alpha Match: **PASS**

- Expected polarity: NOT_ELIGIBLE
- System polarity: NOT_ELIGIBLE
- Polarity eligible: No
- Polarity Match: **NOT_ELIGIBLE**
- Critical support/opposition reversal: No

- Human review judgment: NOT_MATERIAL_ALPHA_FIT
- Review note / rationale: Generic risk-management advice; no canonical Alpha mechanism present
- Source authority: `docs/audit_artifacts/item2_blind_holdout5_{frozen.csv,review_frozen.csv,comparison.csv}`

---

### Review Row holdout5-142

- Ticker: QQQ
- Run ID: `a364e0ee-3bb4-4032-88b7-5cd82e379805`
- Source / agent role: neutral_risk_analyst
- Evidence ID / claim ID: `a364e0ee-3bb4-4032-88b7-5cd82e379805:neutral_risk_analyst:risk_debate_state.neutral_history:claim:55`
- Original sentence:
  > The balanced path is to do both: buy, but buy smart.

- Expected Alpha: NONE
- System-mapped Alpha: NONE
- Alpha Match: **PASS**

- Expected polarity: NOT_ELIGIBLE
- System polarity: NOT_ELIGIBLE
- Polarity eligible: No
- Polarity Match: **NOT_ELIGIBLE**
- Critical support/opposition reversal: No

- Human review judgment: NOT_MATERIAL_ALPHA_FIT
- Review note / rationale: Generic investment strategy advice; no canonical Alpha mechanism present
- Source authority: `docs/audit_artifacts/item2_blind_holdout5_{frozen.csv,review_frozen.csv,comparison.csv}`

---

### Review Row holdout5-143

- Ticker: QQQ
- Run ID: `a364e0ee-3bb4-4032-88b7-5cd82e379805`
- Source / agent role: news_agent
- Evidence ID / claim ID: `a364e0ee-3bb4-4032-88b7-5cd82e379805:news_agent:news_report:claim:101`
- Original sentence:
  > Factor: Market Technicals; Signal: Mixed/Bearish; Evidence: Barrons warns rally may be selling opp; Implication for QQQ: Caution on chasing

- Expected Alpha: NONE
- System-mapped Alpha: A601
- Alpha Match: **FAIL**

- Expected polarity: NOT_ELIGIBLE
- System polarity: NOT_ELIGIBLE
- Polarity eligible: No
- Polarity Match: **NOT_ELIGIBLE**
- Critical support/opposition reversal: No

- Human review judgment: NOT_MATERIAL_ALPHA_FIT
- Review note / rationale: Technical signals and generic caution only; no canonical Alpha mechanism present
- Source authority: `docs/audit_artifacts/item2_blind_holdout5_{frozen.csv,review_frozen.csv,comparison.csv}`

---

### Review Row holdout5-144

- Ticker: QQQ
- Run ID: `a364e0ee-3bb4-4032-88b7-5cd82e379805`
- Source / agent role: news_agent
- Evidence ID / claim ID: `a364e0ee-3bb4-4032-88b7-5cd82e379805:news_agent:news_report:claim:26`
- Original sentence:
  > This is a stock-picker's market within the index, and QQQ's heavy concentration in these mega-caps means single-stock earnings moves drive index-level volatility.

- Expected Alpha: NONE
- System-mapped Alpha: NONE
- Alpha Match: **PASS**

- Expected polarity: NOT_ELIGIBLE
- System polarity: NOT_ELIGIBLE
- Polarity eligible: No
- Polarity Match: **NOT_ELIGIBLE**
- Critical support/opposition reversal: No

- Human review judgment: NOT_MATERIAL_ALPHA_FIT
- Review note / rationale: Index concentration and volatility observation; no canonical Alpha causal mechanism
- Source authority: `docs/audit_artifacts/item2_blind_holdout5_{frozen.csv,review_frozen.csv,comparison.csv}`

---

### Review Row holdout5-145

- Ticker: QQQ
- Run ID: `a364e0ee-3bb4-4032-88b7-5cd82e379805`
- Source / agent role: news_agent
- Evidence ID / claim ID: `a364e0ee-3bb4-4032-88b7-5cd82e379805:news_agent:news_report:claim:49`
- Original sentence:
  > — Yes 8% (down -19pp).

- Expected Alpha: NONE
- System-mapped Alpha: NONE
- Alpha Match: **PASS**

- Expected polarity: NOT_ELIGIBLE
- System polarity: NOT_ELIGIBLE
- Polarity eligible: No
- Polarity Match: **NOT_ELIGIBLE**
- Critical support/opposition reversal: No

- Human review judgment: NOT_MATERIAL_ALPHA_FIT
- Review note / rationale: Isolated statistic fragment with no context or Alpha mechanism
- Source authority: `docs/audit_artifacts/item2_blind_holdout5_{frozen.csv,review_frozen.csv,comparison.csv}`

---

### Review Row holdout5-146

- Ticker: QQQ
- Run ID: `a364e0ee-3bb4-4032-88b7-5cd82e379805`
- Source / agent role: news_agent
- Evidence ID / claim ID: `a364e0ee-3bb4-4032-88b7-5cd82e379805:news_agent:news_report:claim:90`
- Original sentence:
  > Net view: The AI earnings catalyst is powerful and has reignited the trade, but QQQ faces a genuine tug-of-war between AI-driven earnings momentum and a hawkish rate/yield backdrop.

- Expected Alpha: A101
- System-mapped Alpha: A304
- Alpha Match: **FAIL**

- Expected polarity: mentions_alpha
- System polarity: mentions_alpha
- Polarity eligible: Yes
- Polarity Match: **PASS**
- Critical support/opposition reversal: No

- Human review judgment: DIRECTIONALLY_CLEAR (no formal adjudication record; frozen blind label stands as ground truth)
- Review note / rationale: AI earnings catalyst explicitly cited as momentum driver but offset by hawkish rate backdrop; no clear net direction
- Source authority: `docs/audit_artifacts/item2_blind_holdout5_{frozen.csv,review_frozen.csv,comparison.csv}`

---

### Review Row holdout5-147

- Ticker: QQQ
- Run ID: `a364e0ee-3bb4-4032-88b7-5cd82e379805`
- Source / agent role: sentiment_agent
- Evidence ID / claim ID: `a364e0ee-3bb4-4032-88b7-5cd82e379805:sentiment_agent:sentiment_report:claim:22`
- Original sentence:
  > The dominant theme in the most recent messages is geopolitical risk: multiple posts reference a CBS report that the US and Israel are preparing "one of the harshest bombing campaigns to date" against Iranian energy infrastructure.

- Expected Alpha: NONE
- System-mapped Alpha: NONE
- Alpha Match: **PASS**

- Expected polarity: NOT_ELIGIBLE
- System polarity: NOT_ELIGIBLE
- Polarity eligible: No
- Polarity Match: **NOT_ELIGIBLE**
- Critical support/opposition reversal: No

- Human review judgment: NOT_MATERIAL_ALPHA_FIT
- Review note / rationale: Geopolitical risk narrative; no canonical Alpha economic mechanism present
- Source authority: `docs/audit_artifacts/item2_blind_holdout5_{frozen.csv,review_frozen.csv,comparison.csv}`

---

### Review Row holdout5-148

- Ticker: QQQ
- Run ID: `a364e0ee-3bb4-4032-88b7-5cd82e379805`
- Source / agent role: sentiment_agent
- Evidence ID / claim ID: `a364e0ee-3bb4-4032-88b7-5cd82e379805:sentiment_agent:sentiment_report:claim:53`
- Original sentence:
  > This is the clearest cross-cutting theme.

- Expected Alpha: NONE
- System-mapped Alpha: NONE
- Alpha Match: **PASS**

- Expected polarity: NOT_ELIGIBLE
- System polarity: NOT_ELIGIBLE
- Polarity eligible: No
- Polarity Match: **NOT_ELIGIBLE**
- Critical support/opposition reversal: No

- Human review judgment: NOT_MATERIAL_ALPHA_FIT
- Review note / rationale: Vague reference with no substance or Alpha mechanism
- Source authority: `docs/audit_artifacts/item2_blind_holdout5_{frozen.csv,review_frozen.csv,comparison.csv}`

---

### Review Row holdout5-149

- Ticker: QQQ
- Run ID: `a364e0ee-3bb4-4032-88b7-5cd82e379805`
- Source / agent role: sentiment_agent
- Evidence ID / claim ID: `a364e0ee-3bb4-4032-88b7-5cd82e379805:sentiment_agent:sentiment_report:claim:92`
- Original sentence:
  > The result is a Mixed read with a slight lean toward caution on the short-term technical/geopolitical front, balanced against a constructive medium-term AI-fundamental backdrop.

- Expected Alpha: NONE
- System-mapped Alpha: NONE
- Alpha Match: **PASS**

- Expected polarity: NOT_ELIGIBLE
- System polarity: NOT_ELIGIBLE
- Polarity eligible: No
- Polarity Match: **NOT_ELIGIBLE**
- Critical support/opposition reversal: No

- Human review judgment: NOT_MATERIAL_ALPHA_FIT
- Review note / rationale: Mixed summary of technicals and AI fundamentals; no single dominant Alpha mechanism materially expressed
- Source authority: `docs/audit_artifacts/item2_blind_holdout5_{frozen.csv,review_frozen.csv,comparison.csv}`

---

### Review Row holdout5-150

- Ticker: QQQ
- Run ID: `a364e0ee-3bb4-4032-88b7-5cd82e379805`
- Source / agent role: trader
- Evidence ID / claim ID: `a364e0ee-3bb4-4032-88b7-5cd82e379805:trader:trader_investment_plan:claim:3`
- Original sentence:
  > However, given the mixed technicals (price below 50-day SMA, negative MACD) and unquantified geopolitical risk, I endorse the plan's Overweight stance with gradual accumulation in tranches targeting the $680-$690 support zone rather than aggressive all-at-once buying.

- Expected Alpha: NONE
- System-mapped Alpha: NONE
- Alpha Match: **PASS**

- Expected polarity: NOT_ELIGIBLE
- System polarity: NOT_ELIGIBLE
- Polarity eligible: No
- Polarity Match: **NOT_ELIGIBLE**
- Critical support/opposition reversal: No

- Human review judgment: NOT_MATERIAL_ALPHA_FIT
- Review note / rationale: Technical indicators and support levels only; no canonical Alpha causal mechanism present
- Source authority: `docs/audit_artifacts/item2_blind_holdout5_{frozen.csv,review_frozen.csv,comparison.csv}`

---

### Review Row holdout5-151

- Ticker: SNDK
- Run ID: `183b04dd-aae3-4b33-bbb0-3c9bc3bc942f`
- Source / agent role: bear_researcher
- Evidence ID / claim ID: `183b04dd-aae3-4b33-bbb0-3c9bc3bc942f:bear_researcher:investment_debate_state.bear_history:claim:64`
- Original sentence:
  > The company wrote off $1.83 billion of illusory value from its books when pricing deteriorated.

- Expected Alpha: A304
- System-mapped Alpha: A201
- Alpha Match: **FAIL**

- Expected polarity: supports_alpha
- System polarity: supports_alpha
- Polarity eligible: Yes
- Polarity Match: **PASS**
- Critical support/opposition reversal: No

- Human review judgment: DIRECTIONALLY_CLEAR (no formal adjudication record; frozen blind label stands as ground truth)
- Review note / rationale: Massive goodwill/asset writedown due to pricing deterioration signals rich valuation and multiple compression risk materializing.
- Source authority: `docs/audit_artifacts/item2_blind_holdout5_{frozen.csv,review_frozen.csv,comparison.csv}`

---

### Review Row holdout5-152

- Ticker: SNDK
- Run ID: `183b04dd-aae3-4b33-bbb0-3c9bc3bc942f`
- Source / agent role: bull_researcher
- Evidence ID / claim ID: `183b04dd-aae3-4b33-bbb0-3c9bc3bc942f:bull_researcher:investment_debate_state.bull_history:claim:7`
- Original sentence:
  > The bear will wave their hands at the technical chart and point to a 45% drawdown from the June peak.

- Expected Alpha: NONE
- System-mapped Alpha: NONE
- Alpha Match: **PASS**

- Expected polarity: NOT_ELIGIBLE
- System polarity: NOT_ELIGIBLE
- Polarity eligible: No
- Polarity Match: **NOT_ELIGIBLE**
- Critical support/opposition reversal: No

- Human review judgment: NOT_MATERIAL_ALPHA_FIT
- Review note / rationale: Technical chart reference and drawdown only; no canonical Alpha mechanism expressed.
- Source authority: `docs/audit_artifacts/item2_blind_holdout5_{frozen.csv,review_frozen.csv,comparison.csv}`

---

### Review Row holdout5-153

- Ticker: SNDK
- Run ID: `183b04dd-aae3-4b33-bbb0-3c9bc3bc942f`
- Source / agent role: conservative_risk_analyst
- Evidence ID / claim ID: `183b04dd-aae3-4b33-bbb0-3c9bc3bc942f:conservative_risk_analyst:risk_debate_state.conservative_history:claim:52`
- Original sentence:
  > The AI supercycle is a demand argument.

- Expected Alpha: A101
- System-mapped Alpha: A101
- Alpha Match: **PASS**

- Expected polarity: mentions_alpha
- System polarity: mentions_alpha
- Polarity eligible: Yes
- Polarity Match: **PASS**
- Critical support/opposition reversal: No

- Human review judgment: DIRECTIONALLY_CLEAR (no formal adjudication record; frozen blind label stands as ground truth)
- Review note / rationale: References AI supercycle as a demand argument but no directional stance on the mechanism.
- Source authority: `docs/audit_artifacts/item2_blind_holdout5_{frozen.csv,review_frozen.csv,comparison.csv}`

---

### Review Row holdout5-154

- Ticker: SNDK
- Run ID: `183b04dd-aae3-4b33-bbb0-3c9bc3bc942f`
- Source / agent role: fundamental_agent
- Evidence ID / claim ID: `183b04dd-aae3-4b33-bbb0-3c9bc3bc942f:fundamental_agent:fundamentals_report:claim:5`
- Original sentence:
  > > ⚡ Key Insight: The forward P/E of 6x against TTM P/E of 43x signals the market anticipates enormous profit acceleration.

- Expected Alpha: A304
- System-mapped Alpha: A301
- Alpha Match: **FAIL**

- Expected polarity: mentions_alpha
- System polarity: opposes_alpha
- Polarity eligible: Yes
- Polarity Match: **FAIL**
- Critical support/opposition reversal: No

- Human review judgment: DIRECTIONALLY_CLEAR (no formal adjudication record; frozen blind label stands as ground truth)
- Review note / rationale: Forward vs TTM P/E gap directly discusses valuation compression and anticipated earnings recovery; no clear directional stance.
- Source authority: `docs/audit_artifacts/item2_blind_holdout5_{frozen.csv,review_frozen.csv,comparison.csv}`

---

### Review Row holdout5-155

- Ticker: SNDK
- Run ID: `183b04dd-aae3-4b33-bbb0-3c9bc3bc942f`
- Source / agent role: market_agent
- Evidence ID / claim ID: `183b04dd-aae3-4b33-bbb0-3c9bc3bc942f:market_agent:market_report:claim:10`
- Original sentence:
  > May superspike: Reached $1,600 by May 8, $2,107 by June 15

- Expected Alpha: NONE
- System-mapped Alpha: NONE
- Alpha Match: **PASS**

- Expected polarity: NOT_ELIGIBLE
- System polarity: NOT_ELIGIBLE
- Polarity eligible: No
- Polarity Match: **NOT_ELIGIBLE**
- Critical support/opposition reversal: No

- Human review judgment: NOT_MATERIAL_ALPHA_FIT
- Review note / rationale: Price milestones only; no canonical Alpha causal mechanism present.
- Source authority: `docs/audit_artifacts/item2_blind_holdout5_{frozen.csv,review_frozen.csv,comparison.csv}`

---

### Review Row holdout5-156

- Ticker: SNDK
- Run ID: `183b04dd-aae3-4b33-bbb0-3c9bc3bc942f`
- Source / agent role: market_agent
- Evidence ID / claim ID: `183b04dd-aae3-4b33-bbb0-3c9bc3bc942f:market_agent:market_report:claim:15`
- Original sentence:
  > July 27: Catastrophic breakdown — closed at $1,278.23, losing 20.6% from the prior session's close of $1,610.33.

- Expected Alpha: NONE
- System-mapped Alpha: NONE
- Alpha Match: **PASS**

- Expected polarity: NOT_ELIGIBLE
- System polarity: NOT_ELIGIBLE
- Polarity eligible: No
- Polarity Match: **NOT_ELIGIBLE**
- Critical support/opposition reversal: No

- Human review judgment: NOT_MATERIAL_ALPHA_FIT
- Review note / rationale: Stock price drop event only; no canonical Alpha mechanism expressed.
- Source authority: `docs/audit_artifacts/item2_blind_holdout5_{frozen.csv,review_frozen.csv,comparison.csv}`

---

### Review Row holdout5-157

- Ticker: SNDK
- Run ID: `183b04dd-aae3-4b33-bbb0-3c9bc3bc942f`
- Source / agent role: market_agent
- Evidence ID / claim ID: `183b04dd-aae3-4b33-bbb0-3c9bc3bc942f:market_agent:market_report:claim:56`
- Original sentence:
  > MACD below zero and below Signal line — bearish momentum sustained

- Expected Alpha: NONE
- System-mapped Alpha: NONE
- Alpha Match: **PASS**

- Expected polarity: NOT_ELIGIBLE
- System polarity: NOT_ELIGIBLE
- Polarity eligible: No
- Polarity Match: **NOT_ELIGIBLE**
- Critical support/opposition reversal: No

- Human review judgment: NOT_MATERIAL_ALPHA_FIT
- Review note / rationale: MACD technical indicator only; no canonical Alpha causal mechanism present.
- Source authority: `docs/audit_artifacts/item2_blind_holdout5_{frozen.csv,review_frozen.csv,comparison.csv}`

---

### Review Row holdout5-158

- Ticker: SNDK
- Run ID: `183b04dd-aae3-4b33-bbb0-3c9bc3bc942f`
- Source / agent role: neutral_risk_analyst
- Evidence ID / claim ID: `183b04dd-aae3-4b33-bbb0-3c9bc3bc942f:neutral_risk_analyst:risk_debate_state.neutral_history:claim:17`
- Original sentence:
  > Part of that differential reflects the fact that SNDK had run significantly harder into the peak than MU did, and institutional rebalancing after a parabolic move often amplifies the correction on the way down regardless of relative fundamental merit.

- Expected Alpha: A304
- System-mapped Alpha: A601
- Alpha Match: **FAIL**

- Expected polarity: supports_alpha
- System polarity: supports_alpha
- Polarity eligible: Yes
- Polarity Match: **PASS**
- Critical support/opposition reversal: No

- Human review judgment: DIRECTIONALLY_CLEAR (no formal adjudication record; frozen blind label stands as ground truth)
- Review note / rationale: Institutional rebalancing after parabolic move amplifying correction points to valuation air deflating; multiple compression thesis.
- Source authority: `docs/audit_artifacts/item2_blind_holdout5_{frozen.csv,review_frozen.csv,comparison.csv}`

---

### Review Row holdout5-159

- Ticker: SNDK
- Run ID: `183b04dd-aae3-4b33-bbb0-3c9bc3bc942f`
- Source / agent role: neutral_risk_analyst
- Evidence ID / claim ID: `183b04dd-aae3-4b33-bbb0-3c9bc3bc942f:neutral_risk_analyst:risk_debate_state.neutral_history:claim:18`
- Original sentence:
  > You can't cleanly separate the signal of "institutions believe SNDK is more fundamentally exposed" from the noise of "SNDK had more air in the valuation to deflate." Both are probably true simultaneously, and conflating them leads to overstating the structural impairment thesis.

- Expected Alpha: A304
- System-mapped Alpha: A304
- Alpha Match: **PASS**

- Expected polarity: mentions_alpha
- System polarity: mentions_alpha
- Polarity eligible: Yes
- Polarity Match: **PASS**
- Critical support/opposition reversal: No

- Human review judgment: DIRECTIONALLY_CLEAR (no formal adjudication record; frozen blind label stands as ground truth)
- Review note / rationale: Explicitly discusses valuation air and multiple compression entangled with fundamental exposure; no clear net stance.
- Source authority: `docs/audit_artifacts/item2_blind_holdout5_{frozen.csv,review_frozen.csv,comparison.csv}`

---

### Review Row holdout5-160

- Ticker: SNDK
- Run ID: `183b04dd-aae3-4b33-bbb0-3c9bc3bc942f`
- Source / agent role: sentiment_agent
- Evidence ID / claim ID: `183b04dd-aae3-4b33-bbb0-3c9bc3bc942f:sentiment_agent:sentiment_report:claim:27`
- Original sentence:
  > Unlabeled messages lean bearish in tone: Multiple unlabeled posts convey frustration ("this is bullshit man.

- Expected Alpha: NONE
- System-mapped Alpha: NONE
- Alpha Match: **PASS**

- Expected polarity: NOT_ELIGIBLE
- System polarity: NOT_ELIGIBLE
- Polarity eligible: No
- Polarity Match: **NOT_ELIGIBLE**
- Critical support/opposition reversal: No

- Human review judgment: NOT_MATERIAL_ALPHA_FIT
- Review note / rationale: Generic bearish retail sentiment only; no canonical Alpha mechanism expressed.
- Source authority: `docs/audit_artifacts/item2_blind_holdout5_{frozen.csv,review_frozen.csv,comparison.csv}`

---

### Review Row holdout5-161

- Ticker: SNDK
- Run ID: `183b04dd-aae3-4b33-bbb0-3c9bc3bc942f`
- Source / agent role: sentiment_agent
- Evidence ID / claim ID: `183b04dd-aae3-4b33-bbb0-3c9bc3bc942f:sentiment_agent:sentiment_report:claim:59`
- Original sentence:
  > This is a genuine, informed question about relative exposure and implies sophisticated bears trying to understand SNDK's specific vulnerability.

- Expected Alpha: NONE
- System-mapped Alpha: NONE
- Alpha Match: **PASS**

- Expected polarity: NOT_ELIGIBLE
- System polarity: NOT_ELIGIBLE
- Polarity eligible: No
- Polarity Match: **NOT_ELIGIBLE**
- Critical support/opposition reversal: No

- Human review judgment: NOT_MATERIAL_ALPHA_FIT
- Review note / rationale: Meta-commentary about analyst sophistication; no canonical Alpha mechanism expressed.
- Source authority: `docs/audit_artifacts/item2_blind_holdout5_{frozen.csv,review_frozen.csv,comparison.csv}`

---

### Review Row holdout5-162

- Ticker: SNDK
- Run ID: `183b04dd-aae3-4b33-bbb0-3c9bc3bc942f`
- Source / agent role: sentiment_agent
- Evidence ID / claim ID: `183b04dd-aae3-4b33-bbb0-3c9bc3bc942f:sentiment_agent:sentiment_report:claim:7`
- Original sentence:
  > Its shares jumped +466% on debut, rattling global memory peers.

- Expected Alpha: NONE
- System-mapped Alpha: A601
- Alpha Match: **FAIL**

- Expected polarity: NOT_ELIGIBLE
- System polarity: NOT_ELIGIBLE
- Polarity eligible: No
- Polarity Match: **NOT_ELIGIBLE**
- Critical support/opposition reversal: No

- Human review judgment: NOT_MATERIAL_ALPHA_FIT
- Review note / rationale: IPO price jump and peer reaction noted; no canonical Alpha causal mechanism materially present.
- Source authority: `docs/audit_artifacts/item2_blind_holdout5_{frozen.csv,review_frozen.csv,comparison.csv}`

---

### Review Row holdout5-163

- Ticker: SNDK
- Run ID: `8d21c047-fc0a-4d94-957d-3787f353a544`
- Source / agent role: aggressive_risk_analyst
- Evidence ID / claim ID: `8d21c047-fc0a-4d94-957d-3787f353a544:aggressive_risk_analyst:risk_debate_state.aggressive_history:claim:49`
- Original sentence:
  > The VWMA at $1,745 versus a close of $1,417 tells you that the average cost basis of positions established over the past 20 days is $327 per share underwater.

- Expected Alpha: NONE
- System-mapped Alpha: A601
- Alpha Match: **FAIL**

- Expected polarity: NOT_ELIGIBLE
- System polarity: NOT_ELIGIBLE
- Polarity eligible: No
- Polarity Match: **NOT_ELIGIBLE**
- Critical support/opposition reversal: No

- Human review judgment: NOT_MATERIAL_ALPHA_FIT
- Review note / rationale: Technical VWMA cost-basis analysis only; no canonical Alpha mechanism present.
- Source authority: `docs/audit_artifacts/item2_blind_holdout5_{frozen.csv,review_frozen.csv,comparison.csv}`

---

### Review Row holdout5-164

- Ticker: SNDK
- Run ID: `8d21c047-fc0a-4d94-957d-3787f353a544`
- Source / agent role: bear_researcher
- Evidence ID / claim ID: `8d21c047-fc0a-4d94-957d-3787f353a544:bear_researcher:investment_debate_state.bear_history:claim:33`
- Original sentence:
  > But here's the critical distinction the bull glosses over: AI data centers primarily drive demand for HBM and DRAM in inference engines, not NAND flash.

- Expected Alpha: A101
- System-mapped Alpha: A102
- Alpha Match: **FAIL**

- Expected polarity: opposes_alpha
- System polarity: opposes_alpha
- Polarity eligible: Yes
- Polarity Match: **PASS**
- Critical support/opposition reversal: No

- Human review judgment: DIRECTIONALLY_CLEAR (no formal adjudication record; frozen blind label stands as ground truth)
- Review note / rationale: AI datacenter demand drives HBM/DRAM not NAND; directly weakens AI expansion thesis for SNDK.
- Source authority: `docs/audit_artifacts/item2_blind_holdout5_{frozen.csv,review_frozen.csv,comparison.csv}`

---

### Review Row holdout5-165

- Ticker: SNDK
- Run ID: `8d21c047-fc0a-4d94-957d-3787f353a544`
- Source / agent role: bull_researcher
- Evidence ID / claim ID: `8d21c047-fc0a-4d94-957d-3787f353a544:bull_researcher:investment_debate_state.bull_history:claim:57`
- Original sentence:
  > The bear is right that the near-term momentum is negative and you don't want to catch a falling knife with no process.

- Expected Alpha: NONE
- System-mapped Alpha: NONE
- Alpha Match: **PASS**

- Expected polarity: NOT_ELIGIBLE
- System polarity: NOT_ELIGIBLE
- Polarity eligible: No
- Polarity Match: **NOT_ELIGIBLE**
- Critical support/opposition reversal: No

- Human review judgment: NOT_MATERIAL_ALPHA_FIT
- Review note / rationale: Generic bearish momentum commentary; no canonical Alpha causal mechanism materially expressed.
- Source authority: `docs/audit_artifacts/item2_blind_holdout5_{frozen.csv,review_frozen.csv,comparison.csv}`

---

### Review Row holdout5-166

- Ticker: SNDK
- Run ID: `8d21c047-fc0a-4d94-957d-3787f353a544`
- Source / agent role: conservative_risk_analyst
- Evidence ID / claim ID: `8d21c047-fc0a-4d94-957d-3787f353a544:conservative_risk_analyst:risk_debate_state.conservative_history:claim:52`
- Original sentence:
  > The Kioxia joint venture manufacturing concentration in Japan is described as an unpriced structural vulnerability, and I agree with that characterization.

- Expected Alpha: NONE
- System-mapped Alpha: NONE
- Alpha Match: **PASS**

- Expected polarity: NOT_ELIGIBLE
- System polarity: NOT_ELIGIBLE
- Polarity eligible: No
- Polarity Match: **NOT_ELIGIBLE**
- Critical support/opposition reversal: No

- Human review judgment: NOT_MATERIAL_ALPHA_FIT
- Review note / rationale: Geographic manufacturing concentration risk; no canonical Alpha mechanism materially present.
- Source authority: `docs/audit_artifacts/item2_blind_holdout5_{frozen.csv,review_frozen.csv,comparison.csv}`

---

### Review Row holdout5-167

- Ticker: SNDK
- Run ID: `8d21c047-fc0a-4d94-957d-3787f353a544`
- Source / agent role: fundamental_agent
- Evidence ID / claim ID: `8d21c047-fc0a-4d94-957d-3787f353a544:fundamental_agent:fundamentals_report:claim:28`
- Original sentence:
  > Key Insight: An operating margin of 70% for a computer hardware company is extraordinary and reflects the dramatic leverage in flash memory economics — when NAND prices surge, the cost structure (which largely consists of fixed manufacturing partnership costs) barely moves, while revenue can more than double.

- Expected Alpha: A301
- System-mapped Alpha: A201
- Alpha Match: **FAIL**

- Expected polarity: supports_alpha
- System polarity: supports_alpha
- Polarity eligible: Yes
- Polarity Match: **PASS**
- Critical support/opposition reversal: No

- Human review judgment: DIRECTIONALLY_CLEAR (no formal adjudication record; frozen blind label stands as ground truth)
- Review note / rationale: NAND price surge driving extraordinary margin expansion directly supports revenue/earnings expansion thesis.
- Source authority: `docs/audit_artifacts/item2_blind_holdout5_{frozen.csv,review_frozen.csv,comparison.csv}`

---

### Review Row holdout5-168

- Ticker: SNDK
- Run ID: `8d21c047-fc0a-4d94-957d-3787f353a544`
- Source / agent role: market_agent
- Evidence ID / claim ID: `8d21c047-fc0a-4d94-957d-3787f353a544:market_agent:market_report:claim:47`
- Original sentence:
  > This indicates that the volume-weighted average cost of positions over the past 20 days is $1,745, meaning a majority of recent buyers are now sitting at a loss of $327 per share (-18.7%).

- Expected Alpha: NONE
- System-mapped Alpha: NONE
- Alpha Match: **PASS**

- Expected polarity: NOT_ELIGIBLE
- System polarity: NOT_ELIGIBLE
- Polarity eligible: No
- Polarity Match: **NOT_ELIGIBLE**
- Critical support/opposition reversal: No

- Human review judgment: NOT_MATERIAL_ALPHA_FIT
- Review note / rationale: Technical VWMA underwater cost-basis analysis only; no canonical Alpha mechanism present.
- Source authority: `docs/audit_artifacts/item2_blind_holdout5_{frozen.csv,review_frozen.csv,comparison.csv}`

---

### Review Row holdout5-169

- Ticker: SNDK
- Run ID: `8d21c047-fc0a-4d94-957d-3787f353a544`
- Source / agent role: neutral_risk_analyst
- Evidence ID / claim ID: `8d21c047-fc0a-4d94-957d-3787f353a544:neutral_risk_analyst:risk_debate_state.neutral_history:claim:21`
- Original sentence:
  > You have interpreted that data in the most bearish way possible when a neutral reading of it is at least equally supportable.

- Expected Alpha: NONE
- System-mapped Alpha: NONE
- Alpha Match: **PASS**

- Expected polarity: NOT_ELIGIBLE
- System polarity: NOT_ELIGIBLE
- Polarity eligible: No
- Polarity Match: **NOT_ELIGIBLE**
- Critical support/opposition reversal: No

- Human review judgment: NOT_MATERIAL_ALPHA_FIT
- Review note / rationale: Meta-commentary on data interpretation bias; no canonical Alpha mechanism materially expressed.
- Source authority: `docs/audit_artifacts/item2_blind_holdout5_{frozen.csv,review_frozen.csv,comparison.csv}`

---

### Review Row holdout5-170

- Ticker: SNDK
- Run ID: `8d21c047-fc0a-4d94-957d-3787f353a544`
- Source / agent role: neutral_risk_analyst
- Evidence ID / claim ID: `8d21c047-fc0a-4d94-957d-3787f353a544:neutral_risk_analyst:risk_debate_state.neutral_history:claim:41`
- Original sentence:
  > Trim 20% of total position at current levels near $1,417 without waiting for the bounce, because the execution risk of waiting for a specific bounce level in a $207 ATR environment is real and the Conservative Analyst has identified it correctly.

- Expected Alpha: NONE
- System-mapped Alpha: NONE
- Alpha Match: **PASS**

- Expected polarity: NOT_ELIGIBLE
- System polarity: NOT_ELIGIBLE
- Polarity eligible: No
- Polarity Match: **NOT_ELIGIBLE**
- Critical support/opposition reversal: No

- Human review judgment: NOT_MATERIAL_ALPHA_FIT
- Review note / rationale: Position-sizing and execution risk advice; no canonical Alpha causal mechanism present.
- Source authority: `docs/audit_artifacts/item2_blind_holdout5_{frozen.csv,review_frozen.csv,comparison.csv}`

---

### Review Row holdout5-171

- Ticker: SNDK
- Run ID: `8d21c047-fc0a-4d94-957d-3787f353a544`
- Source / agent role: neutral_risk_analyst
- Evidence ID / claim ID: `8d21c047-fc0a-4d94-957d-3787f353a544:neutral_risk_analyst:risk_debate_state.neutral_history:claim:58`
- Original sentence:
  > A stock split announcement at these price levels would be a genuine near-term sentiment catalyst.

- Expected Alpha: NONE
- System-mapped Alpha: A601
- Alpha Match: **FAIL**

- Expected polarity: NOT_ELIGIBLE
- System polarity: NOT_ELIGIBLE
- Polarity eligible: No
- Polarity Match: **NOT_ELIGIBLE**
- Critical support/opposition reversal: No

- Human review judgment: NOT_MATERIAL_ALPHA_FIT
- Review note / rationale: Stock split sentiment catalyst; no canonical Alpha causal mechanism present
- Source authority: `docs/audit_artifacts/item2_blind_holdout5_{frozen.csv,review_frozen.csv,comparison.csv}`

---

### Review Row holdout5-172

- Ticker: SNDK
- Run ID: `8d21c047-fc0a-4d94-957d-3787f353a544`
- Source / agent role: neutral_risk_analyst
- Evidence ID / claim ID: `8d21c047-fc0a-4d94-957d-3787f353a544:neutral_risk_analyst:risk_debate_state.neutral_history:claim:9`
- Original sentence:
  > You wave this away by saying that in strong downtrends price rides the lower band as a continuation signal.

- Expected Alpha: NONE
- System-mapped Alpha: NONE
- Alpha Match: **PASS**

- Expected polarity: NOT_ELIGIBLE
- System polarity: NOT_ELIGIBLE
- Polarity eligible: No
- Polarity Match: **NOT_ELIGIBLE**
- Critical support/opposition reversal: No

- Human review judgment: NOT_MATERIAL_ALPHA_FIT
- Review note / rationale: Technical Bollinger Band continuation signal only; no canonical Alpha mechanism
- Source authority: `docs/audit_artifacts/item2_blind_holdout5_{frozen.csv,review_frozen.csv,comparison.csv}`

---

### Review Row holdout5-173

- Ticker: SNDK
- Run ID: `8d21c047-fc0a-4d94-957d-3787f353a544`
- Source / agent role: news_agent
- Evidence ID / claim ID: `8d21c047-fc0a-4d94-957d-3787f353a544:news_agent:news_report:claim:27`
- Original sentence:
  > Macro indicator data from FRED was unavailable this session, but prediction market signals and news context provide strong directional guidance:

- Expected Alpha: NONE
- System-mapped Alpha: NONE
- Alpha Match: **PASS**

- Expected polarity: NOT_ELIGIBLE
- System polarity: NOT_ELIGIBLE
- Polarity eligible: No
- Polarity Match: **NOT_ELIGIBLE**
- Critical support/opposition reversal: No

- Human review judgment: NOT_MATERIAL_ALPHA_FIT
- Review note / rationale: Generic statement about data unavailability and directional guidance; no specific Alpha mechanism
- Source authority: `docs/audit_artifacts/item2_blind_holdout5_{frozen.csv,review_frozen.csv,comparison.csv}`

---

### Review Row holdout5-174

- Ticker: SNDK
- Run ID: `8d21c047-fc0a-4d94-957d-3787f353a544`
- Source / agent role: portfolio_manager
- Evidence ID / claim ID: `8d21c047-fc0a-4d94-957d-3787f353a544:portfolio_manager:final_trade_decision:claim:19`
- Original sentence:
  > The Q1 FY2026 78.4% gross margin and $5.95B revenue quarter are cycle-peak outputs, not structural run-rates.

- Expected Alpha: A304
- System-mapped Alpha: A201
- Alpha Match: **FAIL**

- Expected polarity: supports_alpha
- System polarity: supports_alpha
- Polarity eligible: Yes
- Polarity Match: **PASS**
- Critical support/opposition reversal: No

- Human review judgment: DIRECTIONALLY_CLEAR (no formal adjudication record; frozen blind label stands as ground truth)
- Review note / rationale: Cycle-peak margins and revenue flagged as unsustainable, implying multiple compression risk ahead
- Source authority: `docs/audit_artifacts/item2_blind_holdout5_{frozen.csv,review_frozen.csv,comparison.csv}`

---

### Review Row holdout5-175

- Ticker: SNDK
- Run ID: `8d21c047-fc0a-4d94-957d-3787f353a544`
- Source / agent role: portfolio_manager
- Evidence ID / claim ID: `8d21c047-fc0a-4d94-957d-3787f353a544:portfolio_manager:final_trade_decision:claim:38`
- Original sentence:
  > The 200-day SMA at $782 confirms the macro structural uptrend remains intact.

- Expected Alpha: NONE
- System-mapped Alpha: NONE
- Alpha Match: **PASS**

- Expected polarity: NOT_ELIGIBLE
- System polarity: NOT_ELIGIBLE
- Polarity eligible: No
- Polarity Match: **NOT_ELIGIBLE**
- Critical support/opposition reversal: No

- Human review judgment: NOT_MATERIAL_ALPHA_FIT
- Review note / rationale: 200-day SMA technical uptrend only; no canonical Alpha causal mechanism
- Source authority: `docs/audit_artifacts/item2_blind_holdout5_{frozen.csv,review_frozen.csv,comparison.csv}`

---

### Review Row holdout5-176

- Ticker: TSM
- Run ID: `1a338ced-118e-44d2-b3f6-2444bfb9d7e6`
- Source / agent role: aggressive_risk_analyst
- Evidence ID / claim ID: `1a338ced-118e-44d2-b3f6-2444bfb9d7e6:aggressive_risk_analyst:risk_debate_state.aggressive_history:claim:48`
- Original sentence:
  > Final Verdict: The hold is a cowardly compromise.

- Expected Alpha: NONE
- System-mapped Alpha: NONE
- Alpha Match: **PASS**

- Expected polarity: NOT_ELIGIBLE
- System polarity: NOT_ELIGIBLE
- Polarity eligible: No
- Polarity Match: **NOT_ELIGIBLE**
- Critical support/opposition reversal: No

- Human review judgment: NOT_MATERIAL_ALPHA_FIT
- Review note / rationale: Editorial opinion on analyst rating; no canonical Alpha mechanism expressed
- Source authority: `docs/audit_artifacts/item2_blind_holdout5_{frozen.csv,review_frozen.csv,comparison.csv}`

---

### Review Row holdout5-177

- Ticker: TSM
- Run ID: `1a338ced-118e-44d2-b3f6-2444bfb9d7e6`
- Source / agent role: bear_researcher
- Evidence ID / claim ID: `1a338ced-118e-44d2-b3f6-2444bfb9d7e6:bear_researcher:investment_debate_state.bear_history:claim:116`
- Original sentence:
  > The Risks are Underappreciated: Apple diversification, Intel's resurgence, and China's competition are real threats.

- Expected Alpha: NONE
- System-mapped Alpha: A201
- Alpha Match: **FAIL**

- Expected polarity: NOT_ELIGIBLE
- System polarity: NOT_ELIGIBLE
- Polarity eligible: No
- Polarity Match: **NOT_ELIGIBLE**
- Critical support/opposition reversal: No

- Human review judgment: NOT_MATERIAL_ALPHA_FIT
- Review note / rationale: Generic competitive risk narrative; no specific canonical Alpha causal mechanism materially present
- Source authority: `docs/audit_artifacts/item2_blind_holdout5_{frozen.csv,review_frozen.csv,comparison.csv}`

---

### Review Row holdout5-178

- Ticker: TSM
- Run ID: `1a338ced-118e-44d2-b3f6-2444bfb9d7e6`
- Source / agent role: bull_researcher
- Evidence ID / claim ID: `1a338ced-118e-44d2-b3f6-2444bfb9d7e6:bull_researcher:investment_debate_state.bull_history:claim:108`
- Original sentence:
  > They're going to diversify."

- Expected Alpha: NONE
- System-mapped Alpha: NONE
- Alpha Match: **PASS**

- Expected polarity: NOT_ELIGIBLE
- System polarity: NOT_ELIGIBLE
- Polarity eligible: No
- Polarity Match: **NOT_ELIGIBLE**
- Critical support/opposition reversal: No

- Human review judgment: NOT_MATERIAL_ALPHA_FIT
- Review note / rationale: Vague diversification statement with no context or canonical Alpha mechanism
- Source authority: `docs/audit_artifacts/item2_blind_holdout5_{frozen.csv,review_frozen.csv,comparison.csv}`

---

### Review Row holdout5-179

- Ticker: TSM
- Run ID: `1a338ced-118e-44d2-b3f6-2444bfb9d7e6`
- Source / agent role: bull_researcher
- Evidence ID / claim ID: `1a338ced-118e-44d2-b3f6-2444bfb9d7e6:bull_researcher:investment_debate_state.bull_history:claim:69`
- Original sentence:
  > The MACD histogram is contracting, signaling the momentum is turning.

- Expected Alpha: NONE
- System-mapped Alpha: NONE
- Alpha Match: **PASS**

- Expected polarity: NOT_ELIGIBLE
- System polarity: NOT_ELIGIBLE
- Polarity eligible: No
- Polarity Match: **NOT_ELIGIBLE**
- Critical support/opposition reversal: No

- Human review judgment: NOT_MATERIAL_ALPHA_FIT
- Review note / rationale: MACD histogram contraction is technical momentum only; no canonical Alpha mechanism
- Source authority: `docs/audit_artifacts/item2_blind_holdout5_{frozen.csv,review_frozen.csv,comparison.csv}`

---

### Review Row holdout5-180

- Ticker: TSM
- Run ID: `1a338ced-118e-44d2-b3f6-2444bfb9d7e6`
- Source / agent role: bull_researcher
- Evidence ID / claim ID: `1a338ced-118e-44d2-b3f6-2444bfb9d7e6:bull_researcher:investment_debate_state.bull_history:claim:75`
- Original sentence:
  > Morgan Stanley is telling you to buy this dip.

- Expected Alpha: NONE
- System-mapped Alpha: NONE
- Alpha Match: **PASS**

- Expected polarity: NOT_ELIGIBLE
- System polarity: NOT_ELIGIBLE
- Polarity eligible: No
- Polarity Match: **NOT_ELIGIBLE**
- Critical support/opposition reversal: No

- Human review judgment: NOT_MATERIAL_ALPHA_FIT
- Review note / rationale: Analyst buy recommendation only; no canonical Alpha causal mechanism stated
- Source authority: `docs/audit_artifacts/item2_blind_holdout5_{frozen.csv,review_frozen.csv,comparison.csv}`

---

### Review Row holdout5-181

- Ticker: TSM
- Run ID: `1a338ced-118e-44d2-b3f6-2444bfb9d7e6`
- Source / agent role: bull_researcher
- Evidence ID / claim ID: `1a338ced-118e-44d2-b3f6-2444bfb9d7e6:bull_researcher:investment_debate_state.bull_history:claim:83`
- Original sentence:
  > Bull: Trailing earnings are backward-looking.

- Expected Alpha: NONE
- System-mapped Alpha: NONE
- Alpha Match: **PASS**

- Expected polarity: NOT_ELIGIBLE
- System polarity: NOT_ELIGIBLE
- Polarity eligible: No
- Polarity Match: **NOT_ELIGIBLE**
- Critical support/opposition reversal: No

- Human review judgment: NOT_MATERIAL_ALPHA_FIT
- Review note / rationale: Generic statement about valuation methodology; no canonical Alpha mechanism expressed
- Source authority: `docs/audit_artifacts/item2_blind_holdout5_{frozen.csv,review_frozen.csv,comparison.csv}`

---

### Review Row holdout5-182

- Ticker: TSM
- Run ID: `1a338ced-118e-44d2-b3f6-2444bfb9d7e6`
- Source / agent role: bull_researcher
- Evidence ID / claim ID: `1a338ced-118e-44d2-b3f6-2444bfb9d7e6:bull_researcher:investment_debate_state.bull_history:claim:95`
- Original sentence:
  > The 'falling knife' you see is actually a coiled spring.

- Expected Alpha: NONE
- System-mapped Alpha: NONE
- Alpha Match: **PASS**

- Expected polarity: NOT_ELIGIBLE
- System polarity: NOT_ELIGIBLE
- Polarity eligible: No
- Polarity Match: **NOT_ELIGIBLE**
- Critical support/opposition reversal: No

- Human review judgment: NOT_MATERIAL_ALPHA_FIT
- Review note / rationale: Generic bullish metaphor; no canonical Alpha causal mechanism present
- Source authority: `docs/audit_artifacts/item2_blind_holdout5_{frozen.csv,review_frozen.csv,comparison.csv}`

---

### Review Row holdout5-183

- Ticker: TSM
- Run ID: `1a338ced-118e-44d2-b3f6-2444bfb9d7e6`
- Source / agent role: conservative_risk_analyst
- Evidence ID / claim ID: `1a338ced-118e-44d2-b3f6-2444bfb9d7e6:conservative_risk_analyst:risk_debate_state.conservative_history:claim:19`
- Original sentence:
  > At that rate, the PEG jumps to 1.5-2.0, and the stock is no longer "cheap." We are being asked to pay a premium valuation based on peak growth rates that have no historical precedent of persistence.

- Expected Alpha: A304
- System-mapped Alpha: A304
- Alpha Match: **PASS**

- Expected polarity: supports_alpha
- System polarity: supports_alpha
- Polarity eligible: Yes
- Polarity Match: **PASS**
- Critical support/opposition reversal: No

- Human review judgment: DIRECTIONALLY_CLEAR (no formal adjudication record; frozen blind label stands as ground truth)
- Review note / rationale: PEG 1.5-2.0 signals premium valuation at peak growth; directly supports multiple compression risk thesis
- Source authority: `docs/audit_artifacts/item2_blind_holdout5_{frozen.csv,review_frozen.csv,comparison.csv}`

---

### Review Row holdout5-184

- Ticker: TSM
- Run ID: `1a338ced-118e-44d2-b3f6-2444bfb9d7e6`
- Source / agent role: conservative_risk_analyst
- Evidence ID / claim ID: `1a338ced-118e-44d2-b3f6-2444bfb9d7e6:conservative_risk_analyst:risk_debate_state.conservative_history:claim:54`
- Original sentence:
  > The Aggressive Analyst cites "retail 100% bullish on labeled messages" as a positive.

- Expected Alpha: A601
- System-mapped Alpha: A601
- Alpha Match: **PASS**

- Expected polarity: mentions_alpha
- System polarity: mentions_alpha
- Polarity eligible: Yes
- Polarity Match: **PASS**
- Critical support/opposition reversal: No

- Human review judgment: DIRECTIONALLY_CLEAR (no formal adjudication record; frozen blind label stands as ground truth)
- Review note / rationale: 100% retail bullish sentiment cited as signal; references crowded positioning and attention-driven flows mechanism
- Source authority: `docs/audit_artifacts/item2_blind_holdout5_{frozen.csv,review_frozen.csv,comparison.csv}`

---

### Review Row holdout5-185

- Ticker: TSM
- Run ID: `1a338ced-118e-44d2-b3f6-2444bfb9d7e6`
- Source / agent role: conservative_risk_analyst
- Evidence ID / claim ID: `1a338ced-118e-44d2-b3f6-2444bfb9d7e6:conservative_risk_analyst:risk_debate_state.conservative_history:claim:7`
- Original sentence:
  > The forward P/E of 18.6x is an estimate, not a fact.

- Expected Alpha: NONE
- System-mapped Alpha: A304
- Alpha Match: **FAIL**

- Expected polarity: NOT_ELIGIBLE
- System polarity: NOT_ELIGIBLE
- Polarity eligible: No
- Polarity Match: **NOT_ELIGIBLE**
- Critical support/opposition reversal: No

- Human review judgment: NOT_MATERIAL_ALPHA_FIT
- Review note / rationale: Generic observation about estimate uncertainty; no canonical Alpha mechanism materially expressed
- Source authority: `docs/audit_artifacts/item2_blind_holdout5_{frozen.csv,review_frozen.csv,comparison.csv}`

---

### Review Row holdout5-186

- Ticker: TSM
- Run ID: `1a338ced-118e-44d2-b3f6-2444bfb9d7e6`
- Source / agent role: conservative_risk_analyst
- Evidence ID / claim ID: `1a338ced-118e-44d2-b3f6-2444bfb9d7e6:conservative_risk_analyst:risk_debate_state.conservative_history:claim:74`
- Original sentence:
  > The cost of being wrong is a double-digit drawdown.

- Expected Alpha: NONE
- System-mapped Alpha: NONE
- Alpha Match: **PASS**

- Expected polarity: NOT_ELIGIBLE
- System polarity: NOT_ELIGIBLE
- Polarity eligible: No
- Polarity Match: **NOT_ELIGIBLE**
- Critical support/opposition reversal: No

- Human review judgment: NOT_MATERIAL_ALPHA_FIT
- Review note / rationale: Generic risk statement about downside; no specific canonical Alpha causal mechanism present
- Source authority: `docs/audit_artifacts/item2_blind_holdout5_{frozen.csv,review_frozen.csv,comparison.csv}`

---

### Review Row holdout5-187

- Ticker: TSM
- Run ID: `1a338ced-118e-44d2-b3f6-2444bfb9d7e6`
- Source / agent role: fundamental_agent
- Evidence ID / claim ID: `1a338ced-118e-44d2-b3f6-2444bfb9d7e6:fundamental_agent:fundamentals_report:claim:1`
- Original sentence:
  > Analysis Date: 2026-08-03 Company: Taiwan Semiconductor Manufacturing Company Limited Sector/Industry: Technology / Semiconductors Exchange: NYQ (NYSE ADR) Ticker: TSM

- Expected Alpha: NONE
- System-mapped Alpha: NONE
- Alpha Match: **PASS**

- Expected polarity: NOT_ELIGIBLE
- System polarity: NOT_ELIGIBLE
- Polarity eligible: No
- Polarity Match: **NOT_ELIGIBLE**
- Critical support/opposition reversal: No

- Human review judgment: NOT_MATERIAL_ALPHA_FIT
- Review note / rationale: Pure metadata/header; no economic or causal mechanism expressed
- Source authority: `docs/audit_artifacts/item2_blind_holdout5_{frozen.csv,review_frozen.csv,comparison.csv}`

---

### Review Row holdout5-188

- Ticker: TSM
- Run ID: `1a338ced-118e-44d2-b3f6-2444bfb9d7e6`
- Source / agent role: market_agent
- Evidence ID / claim ID: `1a338ced-118e-44d2-b3f6-2444bfb9d7e6:market_agent:market_report:claim:48`
- Original sentence:
  > The VWMA has been declining in line with the pullback, confirming that the recent selling was accompanied by meaningful volume.

- Expected Alpha: NONE
- System-mapped Alpha: NONE
- Alpha Match: **PASS**

- Expected polarity: NOT_ELIGIBLE
- System polarity: NOT_ELIGIBLE
- Polarity eligible: No
- Polarity Match: **NOT_ELIGIBLE**
- Critical support/opposition reversal: No

- Human review judgment: NOT_MATERIAL_ALPHA_FIT
- Review note / rationale: Technical VWMA indicator only; no canonical Alpha causal mechanism present
- Source authority: `docs/audit_artifacts/item2_blind_holdout5_{frozen.csv,review_frozen.csv,comparison.csv}`

---

### Review Row holdout5-189

- Ticker: TSM
- Run ID: `1a338ced-118e-44d2-b3f6-2444bfb9d7e6`
- Source / agent role: market_agent
- Evidence ID / claim ID: `1a338ced-118e-44d2-b3f6-2444bfb9d7e6:market_agent:market_report:claim:65`
- Original sentence:
  > Indicator: macd; Why Selected: Identifies momentum trend and potential bullish crossover setup

- Expected Alpha: NONE
- System-mapped Alpha: NONE
- Alpha Match: **PASS**

- Expected polarity: NOT_ELIGIBLE
- System polarity: NOT_ELIGIBLE
- Polarity eligible: No
- Polarity Match: **NOT_ELIGIBLE**
- Critical support/opposition reversal: No

- Human review judgment: NOT_MATERIAL_ALPHA_FIT
- Review note / rationale: MACD indicator selection only; technical momentum with no canonical Alpha mechanism
- Source authority: `docs/audit_artifacts/item2_blind_holdout5_{frozen.csv,review_frozen.csv,comparison.csv}`

---

### Review Row holdout5-190

- Ticker: TSM
- Run ID: `1a338ced-118e-44d2-b3f6-2444bfb9d7e6`
- Source / agent role: market_agent
- Evidence ID / claim ID: `1a338ced-118e-44d2-b3f6-2444bfb9d7e6:market_agent:market_report:claim:77`
- Original sentence:
  > Key invalidation: A decisive break below $374.67 (recent low) and especially below the 200-day SMA ($356.54) would negate the bullish thesis.

- Expected Alpha: NONE
- System-mapped Alpha: NONE
- Alpha Match: **PASS**

- Expected polarity: NOT_ELIGIBLE
- System polarity: NOT_ELIGIBLE
- Polarity eligible: No
- Polarity Match: **NOT_ELIGIBLE**
- Critical support/opposition reversal: No

- Human review judgment: NOT_MATERIAL_ALPHA_FIT
- Review note / rationale: Technical support/SMA invalidation levels only; no canonical Alpha causal mechanism expressed
- Source authority: `docs/audit_artifacts/item2_blind_holdout5_{frozen.csv,review_frozen.csv,comparison.csv}`

---

### Review Row holdout5-191

- Ticker: TSM
- Run ID: `1a338ced-118e-44d2-b3f6-2444bfb9d7e6`
- Source / agent role: neutral_risk_analyst
- Evidence ID / claim ID: `1a338ced-118e-44d2-b3f6-2444bfb9d7e6:neutral_risk_analyst:risk_debate_state.neutral_history:claim:24`
- Original sentence:
  > This is not asymmetric risk-reward; it is a coin flip.

- Expected Alpha: NONE
- System-mapped Alpha: NONE
- Alpha Match: **PASS**

- Expected polarity: NOT_ELIGIBLE
- System polarity: NOT_ELIGIBLE
- Polarity eligible: No
- Polarity Match: **NOT_ELIGIBLE**
- Critical support/opposition reversal: No

- Human review judgment: NOT_MATERIAL_ALPHA_FIT
- Review note / rationale: Generic risk-reward characterization; no canonical Alpha mechanism expressed.
- Source authority: `docs/audit_artifacts/item2_blind_holdout5_{frozen.csv,review_frozen.csv,comparison.csv}`

---

### Review Row holdout5-192

- Ticker: TSM
- Run ID: `1a338ced-118e-44d2-b3f6-2444bfb9d7e6`
- Source / agent role: neutral_risk_analyst
- Evidence ID / claim ID: `1a338ced-118e-44d2-b3f6-2444bfb9d7e6:neutral_risk_analyst:risk_debate_state.neutral_history:claim:4`
- Original sentence:
  > It is a fundamentally exceptional company caught in a genuine technical and macro crosscurrent, and the disciplined response is to respect that tension rather than pretend it doesn't exist.

- Expected Alpha: NONE
- System-mapped Alpha: NONE
- Alpha Match: **PASS**

- Expected polarity: NOT_ELIGIBLE
- System polarity: NOT_ELIGIBLE
- Polarity eligible: No
- Polarity Match: **NOT_ELIGIBLE**
- Critical support/opposition reversal: No

- Human review judgment: NOT_MATERIAL_ALPHA_FIT
- Review note / rationale: Generic tension acknowledgment; no specific causal Alpha mechanism present.
- Source authority: `docs/audit_artifacts/item2_blind_holdout5_{frozen.csv,review_frozen.csv,comparison.csv}`

---

### Review Row holdout5-193

- Ticker: TSM
- Run ID: `1a338ced-118e-44d2-b3f6-2444bfb9d7e6`
- Source / agent role: news_agent
- Evidence ID / claim ID: `1a338ced-118e-44d2-b3f6-2444bfb9d7e6:news_agent:news_report:claim:28`
- Original sentence:
  > This represents a potential long-term threat to TSM's largest customer relationship.

- Expected Alpha: NONE
- System-mapped Alpha: NONE
- Alpha Match: **PASS**

- Expected polarity: NOT_ELIGIBLE
- System polarity: NOT_ELIGIBLE
- Polarity eligible: No
- Polarity Match: **NOT_ELIGIBLE**
- Critical support/opposition reversal: No

- Human review judgment: NOT_MATERIAL_ALPHA_FIT
- Review note / rationale: Vague threat to customer relationship; no specific Alpha mechanism identifiable without context.
- Source authority: `docs/audit_artifacts/item2_blind_holdout5_{frozen.csv,review_frozen.csv,comparison.csv}`

---

### Review Row holdout5-194

- Ticker: TSM
- Run ID: `1a338ced-118e-44d2-b3f6-2444bfb9d7e6`
- Source / agent role: research_manager
- Evidence ID / claim ID: `1a338ced-118e-44d2-b3f6-2444bfb9d7e6:research_manager:investment_plan:claim:2`
- Original sentence:
  > The bull makes a very strong fundamental case.

- Expected Alpha: NONE
- System-mapped Alpha: NONE
- Alpha Match: **PASS**

- Expected polarity: NOT_ELIGIBLE
- System polarity: NOT_ELIGIBLE
- Polarity eligible: No
- Polarity Match: **NOT_ELIGIBLE**
- Critical support/opposition reversal: No

- Human review judgment: NOT_MATERIAL_ALPHA_FIT
- Review note / rationale: Generic bullish characterization; no specific causal Alpha mechanism expressed.
- Source authority: `docs/audit_artifacts/item2_blind_holdout5_{frozen.csv,review_frozen.csv,comparison.csv}`

---

### Review Row holdout5-195

- Ticker: TSM
- Run ID: `1a338ced-118e-44d2-b3f6-2444bfb9d7e6`
- Source / agent role: sentiment_agent
- Evidence ID / claim ID: `1a338ced-118e-44d2-b3f6-2444bfb9d7e6:sentiment_agent:sentiment_report:claim:13`
- Original sentence:
  > Intel-over-TSMC debate: 24/7 Wall St.

- Expected Alpha: NONE
- System-mapped Alpha: NONE
- Alpha Match: **PASS**

- Expected polarity: NOT_ELIGIBLE
- System polarity: NOT_ELIGIBLE
- Polarity eligible: No
- Polarity Match: **NOT_ELIGIBLE**
- Critical support/opposition reversal: No

- Human review judgment: NOT_MATERIAL_ALPHA_FIT
- Review note / rationale: Mere topic label; no substantive Alpha mechanism expressed.
- Source authority: `docs/audit_artifacts/item2_blind_holdout5_{frozen.csv,review_frozen.csv,comparison.csv}`

---

### Review Row holdout5-196

- Ticker: TSM
- Run ID: `1a338ced-118e-44d2-b3f6-2444bfb9d7e6`
- Source / agent role: sentiment_agent
- Evidence ID / claim ID: `1a338ced-118e-44d2-b3f6-2444bfb9d7e6:sentiment_agent:sentiment_report:claim:18`
- Original sentence:
  > AI trade caution: Bloomberg's "AI Isn't a Catch-All Trade" warns that not all AI trades are equal this earnings season — a sector-wide caution flag.

- Expected Alpha: A601
- System-mapped Alpha: A601
- Alpha Match: **PASS**

- Expected polarity: mentions_alpha
- System polarity: opposes_alpha
- Polarity eligible: Yes
- Polarity Match: **FAIL**
- Critical support/opposition reversal: No

- Human review judgment: DIRECTIONALLY_CLEAR (no formal adjudication record; frozen blind label stands as ground truth)
- Review note / rationale: Warns not all AI trades equal this season; addresses narrative/theme differentiation without clear directional stance.
- Source authority: `docs/audit_artifacts/item2_blind_holdout5_{frozen.csv,review_frozen.csv,comparison.csv}`

---

### Review Row holdout5-197

- Ticker: TSM
- Run ID: `1a338ced-118e-44d2-b3f6-2444bfb9d7e6`
- Source / agent role: sentiment_agent
- Evidence ID / claim ID: `1a338ced-118e-44d2-b3f6-2444bfb9d7e6:sentiment_agent:sentiment_report:claim:41`
- Original sentence:
  > Both sources point to the same core narrative.

- Expected Alpha: NONE
- System-mapped Alpha: NONE
- Alpha Match: **PASS**

- Expected polarity: NOT_ELIGIBLE
- System polarity: NOT_ELIGIBLE
- Polarity eligible: No
- Polarity Match: **NOT_ELIGIBLE**
- Critical support/opposition reversal: No

- Human review judgment: NOT_MATERIAL_ALPHA_FIT
- Review note / rationale: Vague reference to 'same core narrative'; no substantive Alpha mechanism expressed.
- Source authority: `docs/audit_artifacts/item2_blind_holdout5_{frozen.csv,review_frozen.csv,comparison.csv}`

---

### Review Row holdout5-198

- Ticker: TSM
- Run ID: `1a338ced-118e-44d2-b3f6-2444bfb9d7e6`
- Source / agent role: sentiment_agent
- Evidence ID / claim ID: `1a338ced-118e-44d2-b3f6-2444bfb9d7e6:sentiment_agent:sentiment_report:claim:45`
- Original sentence:
  > This mismatch suggests retail may be leaning into the AI thesis more aggressively than institutional framing, which is a mild contrarian flag — retail could be chasing while institutions hedge.

- Expected Alpha: A601
- System-mapped Alpha: A601
- Alpha Match: **PASS**

- Expected polarity: mentions_alpha
- System polarity: opposes_alpha
- Polarity eligible: Yes
- Polarity Match: **FAIL**
- Critical support/opposition reversal: No

- Human review judgment: DIRECTIONALLY_CLEAR (no formal adjudication record; frozen blind label stands as ground truth)
- Review note / rationale: Retail chasing AI thesis vs institutional hedging directly expresses narrative momentum and crowded positioning dynamic.
- Source authority: `docs/audit_artifacts/item2_blind_holdout5_{frozen.csv,review_frozen.csv,comparison.csv}`

---

### Review Row holdout5-199

- Ticker: TSM
- Run ID: `1a338ced-118e-44d2-b3f6-2444bfb9d7e6`
- Source / agent role: sentiment_agent
- Evidence ID / claim ID: `1a338ced-118e-44d2-b3f6-2444bfb9d7e6:sentiment_agent:sentiment_report:claim:55`
- Original sentence:
  > Potential return to all-time high (stock 15% below it).

- Expected Alpha: NONE
- System-mapped Alpha: NONE
- Alpha Match: **PASS**

- Expected polarity: NOT_ELIGIBLE
- System polarity: NOT_ELIGIBLE
- Polarity eligible: No
- Polarity Match: **NOT_ELIGIBLE**
- Critical support/opposition reversal: No

- Human review judgment: NOT_MATERIAL_ALPHA_FIT
- Review note / rationale: Technical price target observation only; no canonical Alpha mechanism present.
- Source authority: `docs/audit_artifacts/item2_blind_holdout5_{frozen.csv,review_frozen.csv,comparison.csv}`

---

### Review Row holdout5-200

- Ticker: TSM
- Run ID: `1a338ced-118e-44d2-b3f6-2444bfb9d7e6`
- Source / agent role: sentiment_agent
- Evidence ID / claim ID: `1a338ced-118e-44d2-b3f6-2444bfb9d7e6:sentiment_agent:sentiment_report:claim:69`
- Original sentence:
  > "Buying Intel Over TSMC Isn't as Crazy..."

- Expected Alpha: NONE
- System-mapped Alpha: NONE
- Alpha Match: **PASS**

- Expected polarity: NOT_ELIGIBLE
- System polarity: NOT_ELIGIBLE
- Polarity eligible: No
- Polarity Match: **NOT_ELIGIBLE**
- Critical support/opposition reversal: No

- Human review judgment: NOT_MATERIAL_ALPHA_FIT
- Review note / rationale: Headline fragment only; no substantive Alpha mechanism expressed.
- Source authority: `docs/audit_artifacts/item2_blind_holdout5_{frozen.csv,review_frozen.csv,comparison.csv}`

---

## Alpha Match Errors

34 rows where the system's matched Alpha did not equal the reviewer's expected Alpha:

| Review ID | Ticker | Sentence | Expected Alpha | Predicted Alpha |
|---|---|---|---|---|
| holdout5-001 | AMD | These analysts are seeing something in the forward order book, in the hyperscaler spend... | A103 | A101 |
| holdout5-003 | AMD | AMD's entire bull case rests on continued hyperscaler AI infrastructure spending. | A103 | A101 |
| holdout5-004 | AMD | One inventory write-down like the one that caused AMD's Q2 2025 gross margins to crater... | A304 | A201 |
| holdout5-005 | AMD | This is not independent fundamental research arriving at $1,250 through bottom-up earni... | A601 | NONE |
| holdout5-008 | AMD | Baird doubled its price target on AMD to $1,250 | NONE | A101 |
| holdout5-016 | AMD | Microsoft Announcement: Baird's 155% upside target hinges on a "surprise Microsoft anno... | A301 | A601 |
| holdout5-017 | AMD | The market is paying a premium for growth, but it's a growth-adjusted fair value. | A304 | NONE |
| holdout5-033 | GOOGL | The claim that "CapEx is causing that revenue growth" is an assertion, not a proven fact. | NONE | A601 |
| holdout5-035 | GOOGL | The normalized income for Q2 2026 was $32.23 billion, which is more representative of u... | NONE | A301 |
| holdout5-043 | GOOGL | The bear is looking at the rearview mirror while Alphabet is flooring the accelerator i... | NONE | A601 |
| holdout5-056 | MSFT | The macro "headwind" is a non-factor when a company is demonstrating this level of pric... | A501 | A301 |
| holdout5-057 | MSFT | Amazon's Q2 beat showed its AI/chip businesses at a $25 billion run rate, and its cloud... | A101 | A102 |
| holdout5-059 | MSFT | This is not a company growing at GDP pace. | NONE | A301 |
| holdout5-063 | MSFT | The conservative analyst is right that the velocity of this move creates elevated pullb... | NONE | A304 |
| holdout5-071 | MSFT | If you're spending $120B+ per year on infrastructure that may or may not generate comme... | A103 | A304 |
| holdout5-081 | MU | In FY2022, the industry was booming and companies were expanding. | NONE | A201 |
| holdout5-083 | MU | In nine months, stockholders' equity nearly doubled — from $54 billion to $100 billion. | NONE | A301 |
| holdout5-086 | MU | R&D investment is scaling up significantly but remains a small fraction of revenue due ... | A301 | A201 |
| holdout5-102 | NVDA | ✅ Inventory of $25.80 billion converts to revenue without write-downs | A301 | A201 |
| holdout5-103 | NVDA | Microsoft is reportedly developing Maia internally. | NONE | A101 |
| holdout5-104 | NVDA | The inventory increase maps almost perfectly to the production ramp timeline. | NONE | A201 |
| holdout5-143 | QQQ | Factor: Market Technicals; Signal: Mixed/Bearish; Evidence: Barrons warns rally may be ... | NONE | A601 |
| holdout5-146 | QQQ | Net view: The AI earnings catalyst is powerful and has reignited the trade, but QQQ fac... | A101 | A304 |
| holdout5-151 | SNDK | The company wrote off $1.83 billion of illusory value from its books when pricing deter... | A304 | A201 |
| holdout5-154 | SNDK | > ⚡ Key Insight: The forward P/E of 6x against TTM P/E of 43x signals the market antici... | A304 | A301 |
| holdout5-158 | SNDK | Part of that differential reflects the fact that SNDK had run significantly harder into... | A304 | A601 |
| holdout5-162 | SNDK | Its shares jumped +466% on debut, rattling global memory peers. | NONE | A601 |
| holdout5-163 | SNDK | The VWMA at $1,745 versus a close of $1,417 tells you that the average cost basis of po... | NONE | A601 |
| holdout5-164 | SNDK | But here's the critical distinction the bull glosses over: AI data centers primarily dr... | A101 | A102 |
| holdout5-167 | SNDK | Key Insight: An operating margin of 70% for a computer hardware company is extraordinar... | A301 | A201 |
| holdout5-171 | SNDK | A stock split announcement at these price levels would be a genuine near-term sentiment... | NONE | A601 |
| holdout5-174 | SNDK | The Q1 FY2026 78.4% gross margin and $5.95B revenue quarter are cycle-peak outputs, not... | A304 | A201 |
| holdout5-177 | TSM | The Risks are Underappreciated: Apple diversification, Intel's resurgence, and China's ... | NONE | A201 |
| holdout5-185 | TSM | The forward P/E of 18.6x is an estimate, not a fact. | NONE | A304 |

## Polarity Errors

9 polarity-eligible rows where the system's polarity did not equal the reviewer's expected polarity:

| Review ID | Ticker | Sentence | Expected Polarity | Predicted Polarity |
|---|---|---|---|---|
| holdout5-003 | AMD | AMD's entire bull case rests on continued hyperscaler AI infrastructure spending. | supports_alpha | mentions_alpha |
| holdout5-016 | AMD | Microsoft Announcement: Baird's 155% upside target hinges on a "surprise Microsoft anno... | supports_alpha | mentions_alpha |
| holdout5-017 | AMD | The market is paying a premium for growth, but it's a growth-adjusted fair value. | mentions_alpha | opposes_alpha |
| holdout5-040 | GOOGL | When retail is clinging to a stale Berkshire headline and the measured investor communi... | mentions_alpha | opposes_alpha |
| holdout5-057 | MSFT | Amazon's Q2 beat showed its AI/chip businesses at a $25 billion run rate, and its cloud... | supports_alpha | mentions_alpha |
| holdout5-070 | MSFT | The 92% earnings beat probability sitting on prediction markets is real. | supports_alpha | mentions_alpha |
| holdout5-154 | SNDK | > ⚡ Key Insight: The forward P/E of 6x against TTM P/E of 43x signals the market antici... | mentions_alpha | opposes_alpha |
| holdout5-196 | TSM | AI trade caution: Bloomberg's "AI Isn't a Catch-All Trade" warns that not all AI trades... | mentions_alpha | opposes_alpha |
| holdout5-198 | TSM | This mismatch suggests retail may be leaning into the AI thesis more aggressively than ... | mentions_alpha | opposes_alpha |

## Critical Reversals

No critical support/opposition reversals were found in the 61 polarity-eligible rows used for acceptance scoring.

One raw reversal exists in the full 62-row material-fit pool before eligibility filtering -- see `holdout5-005` in the Excluded/Ambiguous section immediately below. It is excluded from this count via a general eligibility rule, not omitted or hidden.

## Excluded / Ambiguous Rows

### holdout5-005 (AMD, target A601)

> This is not independent fundamental research arriving at $1,250 through bottom-up earnings modeling.

- Reviewer (human) polarity: `supports_alpha`
- System polarity: `opposes_alpha`
- Adjudication outcome: `BOTH_REASONABLE_AMBIGUOUS`
- Eligibility class: `AMBIGUOUS_DIRECTION` -- retained in audit data, **not** eligible for polarity acceptance scoring or the critical reversal gate
- Why excluded: A genuine directional-framing disagreement on a negatively-phrased sentence, not an obvious error on either side -- flagged, not adjudicated (no post-freeze relabeling performed). Reviewed: supports_alpha (implies the price target is narrative/sentiment-driven rather than fundamentals-driven, invoking A601's reflexive attention-flow mechanism). System: opposes_alpha.
- General rule (no ticker-specific hardcode): Eligibility is derived generically from a formal-adjudication-outcome -> eligibility-class map (`scripts/build_evidence_review_v2_directional_eligibility.py`), never from a hardcoded sample_id or ticker check. Any other row carrying the same `BOTH_REASONABLE_AMBIGUOUS` outcome would be excluded by the identical rule, on any ticker. Confirmed: no `if sample_id == 'holdout5-005'`-style special case exists anywhere in the eligibility script.
- Source authority: `docs/audit_artifacts/item2_blind_holdout5_internal_report.md (Section 11)`

## Source Traceability

- `docs/audit_artifacts/item2_blind_holdout5_frozen.csv` -- frozen sample (sample_id, run_id, ticker, claim_id, agent, sentence)
- `docs/audit_artifacts/item2_blind_holdout5_review_frozen.csv` -- frozen blind human judgments (material_alpha_fit, expected_alpha_id, polarity, review_note)
- `docs/audit_artifacts/item2_blind_holdout5_comparison.csv` -- system output + correctness flags
- `docs/audit_artifacts/item2_blind_holdout5_metrics.json` -- raw aggregate metrics and confusion matrices
- `docs/audit_artifacts/item2_blind_holdout5_internal_report.md` -- formal adjudication record and full narrative
- `scripts/build_evidence_review_v2_directional_eligibility.py` -- the general eligibility contract
- `docs/audit_artifacts/evidence_review_summary_v2.json` -- this document's machine-readable counterpart (`row_level_audit.detailed_rows`, one object per row, same field names as this table)

**Provider calls: 0. TradingAgents calls: 0. No ticker run. No production code changed.**
