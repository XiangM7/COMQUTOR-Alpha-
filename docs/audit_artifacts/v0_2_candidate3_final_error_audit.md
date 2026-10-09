# v0.2 Candidate 3 — FINAL Validation Error Audit

**26 of 150** final-independent-set samples were misclassified by the one-shot Candidate 3 evaluation. This audit is descriptive only and was NOT used to modify Candidate 3, which remains permanently closed for this validation cycle.

## Error Type Counts

| Type | Count |
|---|---:|
| NONE_false_positive | 18 |
| wrong_alpha_substitution | 4 |
| false_negative | 4 |

## Error Category Counts

| Category | Count |
|---|---:|
| valuation_boundary | 10 |
| narrative_momentum_boundary | 4 |
| ai_family_boundary | 4 |
| semiconductor_cycle_boundary | 3 |
| revenue_expansion_boundary | 2 |
| valuation_boundary_multi_signal | 1 |
| revenue_valuation_crossover | 1 |
| revenue_narrative_crossover | 1 |

**Valuation boundary (A304) remains the single largest error source (11/26, ~42% combined with its multi-signal variant)** — consistent with the same dominant pattern already observed in the Day 4G development run, confirming this is the hardest, most persistent boundary rather than an artifact of one dataset.

**Two of the four wrong-Alpha substitutions (`gold-final-059`, `gold-final-077`) are a direct, documented side effect of Candidate 3's own new 'prefer A103 over A101 when concrete capacity is named' tie-break rule** — introduced specifically to fix the reverse confusion direction (documented in Candidate 1's regression analysis and the Day 4G development error analysis), it appears to have overcorrected on these two final-set samples where Gold judged the underlying language as A101. This is reported honestly, not corrected — Candidate 3 is closed for this cycle.

**The bare-sentiment-percentage → A601 false positive pattern recurred** (`gold-final-116`, 'StockTwits ratio is 77% bullish') — the same pattern that produced the one new regression in the Day 4G development run (`gold-dev-045`), confirming this specific gap was not fully closed by Candidate 3's guardrail.

## Per-Sample Detail

### gold-final-001 (nh-final-001)

- **Gold:** NONE — **Candidate 3:** A304
- **Claim/Evidence:** Trading 71% above your long-term average is not a sign of strength for new buyers — it's a quantification of mean reversion risk.
- **Error type:** NONE_false_positive
- **Category:** valuation_boundary
- **Root cause:** A 'mean reversion risk' technical-price statement was read as valuation-multiple risk despite asserting no valuation multiple or downside conclusion.

### gold-final-008 (nh-final-008)

- **Gold:** NONE — **Candidate 3:** A304
- **Claim/Evidence:** The market isn't rewarding visibility; it's setting a trap.
- **Error type:** NONE_false_positive
- **Category:** valuation_boundary
- **Root cause:** A generic 'setting a trap' market judgment triggered A304 with no stated multiple or valuation figure at all.

### gold-final-011 (nh-final-011)

- **Gold:** NONE — **Candidate 3:** A601
- **Claim/Evidence:** The bull also ignores the Reddit silence.
- **Error type:** NONE_false_positive
- **Category:** narrative_momentum_boundary
- **Root cause:** A single-source ('the bull ignores the Reddit silence') attention remark triggered A601 without describing genuine crowd/narrative-driven flows.

### gold-final-015 (nh-final-015)

- **Gold:** NONE — **Candidate 3:** A201
- **Claim/Evidence:** But one of those three — Samsung — has been dealing with yield issues that depressed their output.
- **Error type:** NONE_false_positive
- **Category:** semiconductor_cycle_boundary
- **Root cause:** A competitor's (Samsung, not the subject ticker) yield/output issue triggered A201 via bare industry association, not an inventory/pricing/orders upturn signal for the subject company.

### gold-final-019 (nh-final-020)

- **Gold:** NONE — **Candidate 3:** A304
- **Claim/Evidence:** The bull's PEG argument is mathematically flawed and should be dismissed outright.
- **Error type:** NONE_false_positive
- **Category:** valuation_boundary
- **Root cause:** A critique that the bull's PEG argument is 'mathematically flawed' was read as asserting rich-valuation risk, when it is a rebuttal of methodology, not a valuation conclusion.

### gold-final-030 (nh-final-033)

- **Gold:** NONE — **Candidate 3:** A304
- **Claim/Evidence:** QQQ, as the highest-duration large-cap growth vehicle in the market, is the most exposed index product to this repricing.
- **Error type:** NONE_false_positive
- **Category:** valuation_boundary
- **Root cause:** Repricing/duration-exposure language triggered A304 without a stated rich-multiple-creates-downside conclusion.

### gold-final-041 (nh-final-045)

- **Gold:** NONE — **Candidate 3:** A304
- **Claim/Evidence:** The Trefis headline asking "Has Microsoft Stock Run Ahead Of Its AI Payoff?" is not "clickbait"; it is the central question of this investment.
- **Error type:** NONE_false_positive
- **Category:** valuation_boundary
- **Root cause:** A rhetorical valuation QUESTION ('has the stock run ahead of its AI payoff?') was read as an asserted valuation-risk conclusion.

### gold-final-043 (nh-final-047)

- **Gold:** NONE — **Candidate 3:** A201
- **Claim/Evidence:** AMD's inventory has grown from $6.42B to $8.05B over the past year.
- **Error type:** NONE_false_positive
- **Category:** semiconductor_cycle_boundary
- **Root cause:** A single company's own inventory-growth figure (explicitly characterized as 'grown', satisfying the trend-exemption clause) triggered A201 even though inventory growth alone does not establish an industry cycle upturn and could reflect non-cycle causes -- a residual interaction between the trend-exemption clause and A201's narrower own-mechanism requirement.

### gold-final-048 (nh-final-055)

- **Gold:** NONE — **Candidate 3:** A304
- **Claim/Evidence:** On "Forward EPS Assumes 95% Growth Continues" The neutral analyst will argue that the forward EPS of $15.40 assumes 95% growth, which is "too aggressive." Let me challenge that assumption with the actual trajectory.
- **Error type:** NONE_false_positive
- **Category:** valuation_boundary
- **Root cause:** A debate over whether a forward-EPS growth assumption is 'too aggressive' triggered A304 without any valuation multiple or downside assertion.

### gold-final-051 (nh-final-058)

- **Gold:** NONE — **Candidate 3:** A304
- **Claim/Evidence:** Factor: Valuation; Bear View: 120x trailing P/E; Bull Counter: 30.4x forward P/E, PEG 1.03; Verdict: Fairly valued
- **Error type:** NONE_false_positive
- **Category:** valuation_boundary_multi_signal
- **Root cause:** Evidence presenting BOTH a bear's 120x trailing P/E AND an explicit final 'Verdict: Fairly valued' triggered A304 from the bear figure alone, ignoring the evidence's own concluding verdict of fair valuation.

### gold-final-052 (nh-final-059)

- **Gold:** NONE — **Candidate 3:** A304
- **Claim/Evidence:** The question is not whether TSM is a great company; it is whether the current price offers a favorable risk-reward.
- **Error type:** NONE_false_positive
- **Category:** valuation_boundary
- **Root cause:** A generic 'does the price offer favorable risk-reward' question triggered A304 with no rich-multiple/downside assertion.

### gold-final-054 (nh-final-061)

- **Gold:** NONE — **Candidate 3:** A301
- **Claim/Evidence:** But the Conservative Analyst glosses over the most important data point in the entire fundamental report: Q2 2026 free cash flow was negative at -$5.86B.
- **Error type:** NONE_false_positive
- **Category:** revenue_expansion_boundary
- **Root cause:** A negative free-cash-flow figure, raised as a criticism of what another analyst omitted, triggered A301 despite describing a negative outcome, not growth/demand.

### gold-final-059 (nh-final-067)

- **Gold:** A101 — **Candidate 3:** A103
- **Claim/Evidence:** CoreWeave's CEO says they are "struggling to keep up with demand for Nvidia chips." Every single one of these demand signals flows through TSM's foundry and CoWoS advanced packaging.
- **Error type:** wrong_alpha_substitution
- **Category:** ai_family_boundary
- **Root cause:** Chip-demand-exceeding-supply language ('demand for Nvidia chips'), which Gold read as primarily A101 (accelerator demand), was instead routed to A103 by Candidate 3's own new 'prefer A103 when foundry/packaging capacity is named' tie-break rule -- a documented side effect of the exact guardrail added to fix the reverse confusion direction.

### gold-final-072 (nh-final-083)

- **Gold:** A304 — **Candidate 3:** NONE
- **Claim/Evidence:** Rate environment: 89% probability of no Fed cuts in 2026, with 19-year-high yields — a headwind for high-multiple growth stocks.
- **Error type:** false_negative
- **Category:** valuation_boundary
- **Root cause:** A stated link from high-for-longer yields to a 'headwind for high-multiple growth stocks' (a textbook A304 pattern) was missed, predicted NONE.

### gold-final-077 (nh-final-088)

- **Gold:** A101 — **Candidate 3:** A103
- **Claim/Evidence:** When hyperscalers get squeezed by investors to justify their AI capex spending, they do not stop spending.
- **Error type:** wrong_alpha_substitution
- **Category:** ai_family_boundary
- **Root cause:** Continued hyperscaler AI capex spending (Gold: A101, continued demand trigger) was routed to A103 by the same new foundry/capacity tie-break rule -- second instance of this side effect.

### gold-final-082 (nh-final-094)

- **Gold:** NONE — **Candidate 3:** A601
- **Claim/Evidence:** On balance, the setup favors a positive/accumulate bias into the Nvidia earnings catalyst, with the agentic AI thesis providing a potential re-rating driver.
- **Error type:** NONE_false_positive
- **Category:** narrative_momentum_boundary
- **Root cause:** A generic 'positive/accumulate bias' and 'agentic AI thesis... re-rating driver' phrase triggered A601 without describing concrete investor attention or crowd positioning.

### gold-final-099 (nh-final-115)

- **Gold:** A301 — **Candidate 3:** A304
- **Claim/Evidence:** You are applying a backward-looking multiple to a forward-looking earnings explosion.
- **Error type:** wrong_alpha_substitution
- **Category:** revenue_valuation_crossover
- **Root cause:** A statement about a 'forward-looking earnings explosion' (Gold: A301) was routed to A304 because the sentence also contains the word 'multiple', despite the sentence's own point being about growth, not valuation risk.

### gold-final-101 (nh-final-119)

- **Gold:** NONE — **Candidate 3:** A301
- **Claim/Evidence:** If Anthropic's models lead, the perceived value of OpenAI-powered Copilot and Azure AI offerings could be pressured.
- **Error type:** NONE_false_positive
- **Category:** revenue_expansion_boundary
- **Root cause:** A competitive-threat/downside statement ('perceived value... could be pressured') was misread as growth-adjacent evidence for A301.

### gold-final-102 (nh-final-120)

- **Gold:** A301 — **Candidate 3:** A601
- **Claim/Evidence:** This divergence is the central theme of the current trading environment: the market is now rewarding AI capital spending that demonstrates tangible revenue returns while punishing spending without visible payoff.
- **Error type:** wrong_alpha_substitution
- **Category:** revenue_narrative_crossover
- **Root cause:** A statement that the market 'rewards AI capital spending that demonstrates tangible revenue returns' (Gold: A301) was routed to A601, apparently keying on 'dominant theme'/'rewarding' language as narrative-flavored rather than the sentence's actual revenue-return mechanism.

### gold-final-106 (nh-final-124)

- **Gold:** NONE — **Candidate 3:** A304
- **Claim/Evidence:** You can't simultaneously argue the multiple is dangerously rich and that the forward multiple already embeds aggressive growth expectations.
- **Error type:** NONE_false_positive
- **Category:** valuation_boundary
- **Root cause:** A logical-consistency rebuttal ('you can't argue both X and Y about the multiple') was read as an assertion of rich-valuation risk rather than a rebuttal of another party's framing -- the exact rebuttal-framing pattern the new guardrail targeted, not fully caught here.

### gold-final-116 (nh-final-134)

- **Gold:** NONE — **Candidate 3:** A601
- **Claim/Evidence:** Yes, the labeled StockTwits ratio is 77% bullish.
- **Error type:** NONE_false_positive
- **Category:** narrative_momentum_boundary
- **Root cause:** A bare sentiment-ratio figure ('StockTwits ratio is 77% bullish') triggered A601 without any described narrative/crowding mechanism -- the same bare-sentiment-percentage pattern that produced the one new regression in the Day 4G development run (gold-dev-045), confirming this specific gap was not fully closed.

### gold-final-127 (nh-final-147)

- **Gold:** A101 — **Candidate 3:** NONE
- **Claim/Evidence:** The hawkish Fed and rising yields are a real headwind, but the low recession probability supports continued AI capex.
- **Error type:** false_negative
- **Category:** ai_family_boundary
- **Root cause:** A hedged statement that low recession probability 'supports continued AI capex' (Gold: A101) was missed, predicted NONE.

### gold-final-130 (nh-final-150)

- **Gold:** A601 — **Candidate 3:** NONE
- **Claim/Evidence:** Notes $205 as a key ATM battleground (MMs buy above, sell below), and identifies $210–$220 call blocks where institutional traders are betting on recovery.
- **Error type:** false_negative
- **Category:** narrative_momentum_boundary
- **Root cause:** Dealer/options-positioning language ('ATM battleground', institutional call blocks 'betting on recovery') was judged by Gold as A601 reflexive-flow evidence but missed by the classifier, predicted NONE -- a genuinely hard boundary case since it uses options-market vocabulary rather than typical media/crowd-attention language.

### gold-final-132 (nh-reserve-020)

- **Gold:** A304 — **Candidate 3:** NONE
- **Claim/Evidence:** When rates rise, the discount rate rises, and the multiple compresses.
- **Error type:** false_negative
- **Category:** valuation_boundary
- **Root cause:** A clean, explicit causal statement ('when rates rise, the discount rate rises, and the multiple compresses') -- a textbook A304 mechanism -- was missed, predicted NONE, despite being phrased as directly as any correctly-classified A304 example elsewhere in this same run.

### gold-final-133 (nh-reserve-021)

- **Gold:** NONE — **Candidate 3:** A201
- **Claim/Evidence:** Cyclicality: The semiconductor industry is historically cyclical; inventory build ($25.8B) bears watching.
- **Error type:** NONE_false_positive
- **Category:** semiconductor_cycle_boundary
- **Root cause:** General 'historically cyclical' industry commentary plus a company inventory-build figure triggered A201 without establishing an actual cycle upturn -- the same trend-exemption/A201-narrowness interaction as gold-final-043.

### gold-final-144 (nh-reserve-036)

- **Gold:** NONE — **Candidate 3:** A103
- **Claim/Evidence:** Capital Expenditure Surge: Net PPE has grown dramatically from $184.6B (FY2024) to $338.9B (Q2 2026), underscoring the massive infrastructure buildout.
- **Error type:** NONE_false_positive
- **Category:** ai_family_boundary
- **Root cause:** A large capex/PP&E growth figure explicitly characterized as 'massive infrastructure buildout' triggered A103 even though the buildout is not tied to AI-specific datacenter/power/networking/server demand as A103's own mechanism requires -- a case where 'infrastructure buildout' language is generic capex growth, not proven AI-specific.
