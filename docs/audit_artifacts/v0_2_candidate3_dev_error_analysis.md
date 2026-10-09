# v0.2 Candidate 3 — Baseline Development Error Analysis

**36 of 100** baseline development samples were incorrect. Every one is analyzed below into generalized (non-sample-specific) categories.

## Category Counts

| Category | Count |
|---|---:|
| bare_keyword_overmatch | 14 |
| A304_valuation_boundary | 8 |
| A201_cycle_pricing_confusion | 7 |
| A301_boundary | 7 |
| generic_ai_mention | 7 |
| numeric_metric_overmatch | 6 |
| forced_alpha_instead_of_none | 6 |
| negation_invalidation_as_positive | 6 |
| technical_indicators_to_a601 | 3 |
| multi_signal_handling | 2 |
| a101_a102_a103_boundary_confusion | 2 |
| a304_boundary_undertrigger | 1 |

The single largest pattern (**bare_keyword_overmatch**, 14 occurrences) and the two largest per-Alpha boundaries (**A304_valuation_boundary**, 8; **A201_cycle_pricing_confusion**, 7) together account for most of the error mass, and all three are addressed by the same underlying principle: the classifier was accepting industry/ticker context, uncharacterized data listings, and generic risk-factor mentions as if they were the Alpha's own stated mechanism.

## Per-Sample Analysis

### gold-dev-003 (nh-dev-003, AMD)

- **Gold:** A301 — **System:** A304
- **Claim/Evidence:** I'm looking at a stock that's 40% above its 200-day SMA, with record revenue, record margins, record cash flow, and a forward P/E of 30x on a PEG of 1.03.
- **Categories:** A304_valuation_boundary, numeric_metric_overmatch, multi_signal_handling
- **Root cause:** PEG 1.03 is a REASONABLE/cheap valuation ratio, not a rich one; the classifier keyed on the bare presence of a P/E figure among several signals (revenue/margins/cashflow/PE/PEG) rather than recognizing the figure's own directionality argues against valuation risk.
- **Proposed general remediation principle:** A304 requires the Evidence to state that the valuation is rich/high AND creates downside risk -- a low/reasonable PEG or multiple is not itself risk evidence.

### gold-dev-005 (nh-dev-005, MU)

- **Gold:** NONE — **System:** A201
- **Claim/Evidence:** Operating margin reached 80.4% in Q3 FY2026, among the highest ever recorded for a hardware semiconductor company.
- **Categories:** A201_cycle_pricing_confusion, bare_keyword_overmatch
- **Root cause:** The Evidence names 'semiconductor company' and a margin figure; the classifier used the industry-context keyword rather than requiring an actual cycle-level signal (inventory, ASP, orders, capex recovery).
- **Proposed general remediation principle:** A201 requires the Evidence itself to state an industry cycle signal, never mere sector/industry membership.

### gold-dev-007 (nh-dev-007, TSM)

- **Gold:** A301 — **System:** A201
- **Claim/Evidence:** Apple's foldable iPhone: Morgan Stanley sees $14 billion in December-quarter revenue contribution.
- **Categories:** A201_cycle_pricing_confusion, A301_boundary
- **Root cause:** A revenue-contribution estimate for TSM was misrouted to A201 purely via ticker/industry association with 'semiconductor cycle', though no cycle signal (inventory/ASP/orders) is present.
- **Proposed general remediation principle:** Ticker/industry context alone must never satisfy A201's own mechanism requirement.

### gold-dev-011 (nh-dev-011, TSM)

- **Gold:** NONE — **System:** A201
- **Claim/Evidence:** The engineering and financial costs of switching foundries are prohibitive.
- **Categories:** A201_cycle_pricing_confusion, bare_keyword_overmatch, forced_alpha_instead_of_none
- **Root cause:** 'Foundry' keyword triggered A201 despite the claim being about competitive switching-cost economics, not a cycle signal.
- **Proposed general remediation principle:** A201 requires inventory/ASP/orders/capex-recovery language, not a bare foundry/semiconductor keyword.

### gold-dev-012 (nh-dev-012, NVDA)

- **Gold:** NONE — **System:** A301
- **Claim/Evidence:** The prediction markets show only a 20% probability of Data Center revenue exceeding $90B and just 6% above $95B.
- **Categories:** negation_invalidation_as_positive, A301_boundary
- **Root cause:** A LOW stated probability of reaching a revenue threshold (skepticism) was read as an affirmative revenue-demand signal.
- **Proposed general remediation principle:** A skepticism/low-probability statement about reaching a threshold must not be scored as an affirmative demand signal.

### gold-dev-014 (nh-dev-014, GOOGL)

- **Gold:** NONE — **System:** A304
- **Claim/Evidence:** Negative: The quality of reported earnings is heavily distorted by non-operating investment gains.
- **Categories:** forced_alpha_instead_of_none, A304_valuation_boundary
- **Root cause:** An earnings-quality/accounting-distortion complaint was misread as a valuation-risk claim.
- **Proposed general remediation principle:** A304 requires a stated rich-valuation-creates-downside conclusion, not any generic negative financial-quality complaint.

### gold-dev-015 (nh-dev-015, MSFT)

- **Gold:** NONE — **System:** A101
- **Claim/Evidence:** The single most important growth driver for MSFT is its deeply integrated AI strategy.
- **Categories:** generic_ai_mention
- **Root cause:** A generic 'AI strategy is the growth driver' statement, with no accelerator/inference/infrastructure specifics, triggered A101.
- **Proposed general remediation principle:** A101/A102/A103 each require a concrete, present-tense compute-demand or buildout signal, not a bare AI-strategy/theme mention.

### gold-dev-016 (nh-dev-016, AMD)

- **Gold:** NONE — **System:** A101
- **Claim/Evidence:** Competition: NVIDIA dominates the AI accelerator market with a strong ecosystem moat (CUDA).
- **Categories:** generic_ai_mention, bare_keyword_overmatch
- **Root cause:** A competitor's (NVIDIA's) AI-accelerator market dominance, cited as a competitive risk to AMD, was misread as AMD's own AI demand signal.
- **Proposed general remediation principle:** Same as above; competitive-position statements about a different company's product are not the subject company's own demand signal.

### gold-dev-018 (nh-dev-018, NVDA)

- **Gold:** NONE — **System:** A201
- **Claim/Evidence:** @BashNew (Bearish): Frames competitor MU's +20% move as a negative relative read on NVDA ("wasn't $MU up like 20% today?").
- **Categories:** A201_cycle_pricing_confusion, bare_keyword_overmatch, forced_alpha_instead_of_none
- **Root cause:** A competitor's one-day stock move used as a bearish relative read triggered A201 via ticker/semiconductor association.
- **Proposed general remediation principle:** Same A201 mechanism-sufficiency gap as gold-dev-005/007/011.

### gold-dev-020 (nh-dev-020, NVDA)

- **Gold:** NONE — **System:** A601
- **Claim/Evidence:** The seven-day losing streak, the broken momentum indicators (RSI at 48.75, bearish MACD crossover), and the stock trading below its 10-day EMA all suggest that the market is already discounting a less-than-perfect outcome.
- **Categories:** technical_indicators_to_a601
- **Root cause:** RSI/MACD/EMA technical signals were read as narrative-momentum evidence.
- **Proposed general remediation principle:** Price-technical indicators alone are never sufficient for A601; A601 requires investor-attention/narrative evidence.

### gold-dev-021 (nh-dev-021, GOOGL)

- **Gold:** NONE — **System:** A304
- **Claim/Evidence:** The Bottom Line: The valuation is not "priced for perfection." It is priced for a company that is executing flawlessly on a massive opportunity.
- **Categories:** negation_invalidation_as_positive, A304_valuation_boundary
- **Root cause:** A rebuttal of a 'priced for perfection' framing was misread as itself asserting rich-valuation risk.
- **Proposed general remediation principle:** A304 requires an affirmative rich-valuation-creates-downside assertion, never a rebuttal of that framing.

### gold-dev-022 (nh-dev-022, MSFT)

- **Gold:** NONE — **System:** A301
- **Claim/Evidence:** Fundamental: Evidence that the capex cycle is translating into FCF growth.
- **Categories:** bare_keyword_overmatch, A301_boundary
- **Root cause:** A capex-to-FCF-growth efficiency claim triggered A301 via the word 'growth', with no demand/guidance-revision signal present.
- **Proposed general remediation principle:** A301 requires an affirmative growth/demand/guidance signal, not any sentence containing the word 'growth'.

### gold-dev-023 (nh-dev-023, TSM)

- **Gold:** NONE — **System:** A101
- **Claim/Evidence:** We are waiting for the perfect entry to deploy capital into the most important company in the AI supply chain.
- **Categories:** generic_ai_mention
- **Root cause:** A generic 'most important company in the AI supply chain' thematic statement triggered A101 with no concrete demand mechanism.
- **Proposed general remediation principle:** Same as gold-dev-015/016.

### gold-dev-024 (nh-dev-024, TSM)

- **Gold:** NONE — **System:** A103
- **Claim/Evidence:** If hyperscalers pause or trim their AI CapEx, TSM's revenue growth will decelerate sharply.
- **Categories:** negation_invalidation_as_positive, generic_ai_mention
- **Root cause:** A hypothetical downside scenario ('if hyperscalers cut AI capex, revenue decelerates') was read as a positive A103 signal.
- **Proposed general remediation principle:** A hypothetical/conditional-downside scenario must be judged by what it asserts is true now, not treated as affirmative evidence.

### gold-dev-029 (nh-dev-029, MSFT)

- **Gold:** NONE — **System:** A304
- **Claim/Evidence:** The bull is using the most optimistic scenario to justify the valuation.
- **Categories:** forced_alpha_instead_of_none, A304_valuation_boundary
- **Root cause:** A criticism of an argument's methodology ('bull uses the optimistic scenario') was misread as an assertion that valuation is rich.
- **Proposed general remediation principle:** A304 requires a stated valuation-risk conclusion, not a critique of another party's reasoning.

### gold-dev-032 (nh-dev-032, MU)

- **Gold:** NONE — **System:** A201
- **Claim/Evidence:** HBM4 acceleration — Faster yield ramp positions MU ahead of competitors in the highest-margin segment of the memory market
- **Categories:** A201_cycle_pricing_confusion, bare_keyword_overmatch
- **Root cause:** Product-execution/competitive-positioning language (HBM4 yield ramp) triggered A201 without an inventory/ASP/orders signal.
- **Proposed general remediation principle:** Same A201 mechanism gap.

### gold-dev-037 (nh-dev-040, TSM)

- **Gold:** A103 — **System:** A101
- **Claim/Evidence:** Interpretation for TSM: Every one of these AI demand signals ultimately flows through TSM's foundry and advanced packaging (CoWoS-class) capacity.
- **Categories:** a101_a102_a103_boundary_confusion
- **Root cause:** Foundry/advanced-packaging CAPACITY language (A103's own mechanism) was misrouted to A101.
- **Proposed general remediation principle:** When the Evidence names concrete datacenter/power/networking/server/foundry capacity, A103 should be preferred over A101.

### gold-dev-042 (nh-dev-046, GOOGL)

- **Gold:** NONE — **System:** A304
- **Claim/Evidence:** The market's initial "capex punishment" was not a misreading; it was a correct assessment that Alphabet is spending billions without a proven return.
- **Categories:** forced_alpha_instead_of_none, A304_valuation_boundary
- **Root cause:** An ROI/capex-efficiency concern ('spending billions without a proven return') was misread as a valuation-multiple risk claim.
- **Proposed general remediation principle:** A304 requires a stated valuation-multiple risk, not a generic capital-efficiency/ROI concern.

### gold-dev-044 (nh-dev-050, NVDA)

- **Gold:** NONE — **System:** A101
- **Claim/Evidence:** NVIDIA isn't just a semiconductor company; it is the foundational infrastructure of the global AI economy.
- **Categories:** generic_ai_mention, bare_keyword_overmatch
- **Root cause:** Thematic rhetoric ('foundational infrastructure of the global AI economy') triggered A101 with no concrete demand specifics.
- **Proposed general remediation principle:** Same as gold-dev-015/016/023.

### gold-dev-047 (nh-dev-056, QQQ)

- **Gold:** NONE — **System:** A304
- **Claim/Evidence:** With no rate cuts on the horizon, the multiple is being supported solely by earnings growth.
- **Categories:** negation_invalidation_as_positive, A304_valuation_boundary
- **Root cause:** A statement that the multiple IS being supported by earnings growth (not compressed) was misread as A304 valuation-risk evidence.
- **Proposed general remediation principle:** A304 requires an asserted downside/compression conclusion, not a statement that support currently exists.

### gold-dev-055 (nh-dev-066, MSFT)

- **Gold:** A304 — **System:** NONE
- **Claim/Evidence:** For a stock trading at 27x trailing earnings, the discount rate matters enormously.
- **Categories:** a304_boundary_undertrigger
- **Root cause:** An implicit valuation-risk link ('27x trailing earnings, discount rate matters enormously') was NOT recognized as sufficient for A304 -- the one false negative.
- **Proposed general remediation principle:** A304's own mechanism can be stated implicitly via multiple+discount-rate-sensitivity language; this is a genuine boundary-discrimination miss in the under-trigger direction, distinct from the dominant over-trigger pattern.

### gold-dev-056 (nh-dev-067, MU)

- **Gold:** NONE — **System:** A201
- **Claim/Evidence:** That is a full cycle swing from $8.7 billion in profit to negative $5.8 billion in a single year.
- **Categories:** bare_keyword_overmatch, A201_cycle_pricing_confusion
- **Root cause:** A large profit swing loosely described as a 'cycle' triggered A201 without inventory/ASP/orders language.
- **Proposed general remediation principle:** The word 'cycle' alone, applied to company profit volatility, is not A201's own inventory/pricing/orders mechanism.

### gold-dev-057 (nh-dev-068, TSM)

- **Gold:** NONE — **System:** A301
- **Claim/Evidence:** Year: 2021; Total Revenue: 2,263,891; Gross Profit: 1,348,355; Operating Income: 1,121,227; Net Income: 992,923; Diluted EPS (NT$): 196.00
- **Categories:** numeric_metric_overmatch, forced_alpha_instead_of_none
- **Root cause:** A bare historical financial-figures table (one year, several unrelated metrics, no growth/trend narrative) triggered A301.
- **Proposed general remediation principle:** A bare listing of figures across periods/categories that the Evidence itself never characterizes as a trend is not sufficient.

### gold-dev-062 (nh-dev-073, NVDA)

- **Gold:** NONE — **System:** A301
- **Claim/Evidence:** If NVDA beats but offers conservative guidance (supply constraints, export controls): This is the most likely downside scenario.
- **Categories:** negation_invalidation_as_positive, A301_boundary
- **Root cause:** An explicit 'downside scenario' (conservative guidance due to supply constraints) triggered A301, a positive-growth thesis.
- **Proposed general remediation principle:** A stated downside scenario must never be scored as affirmative growth evidence.

### gold-dev-063 (nh-dev-074, SNDK)

- **Gold:** NONE — **System:** A601
- **Claim/Evidence:** Signal: +8% single-day rally on Sept 4; Direction: Bullish; Source: News; Supporting Evidence: Benzinga, 24/7 Wall St.
- **Categories:** bare_keyword_overmatch, technical_indicators_to_a601
- **Root cause:** A bare price-outcome (+8% rally) with a news-source citation triggered A601 without any described attention/narrative mechanism.
- **Proposed general remediation principle:** A price outcome plus a source citation is not itself narrative/attention evidence.

### gold-dev-067 (nh-dev-078, SNDK)

- **Gold:** NONE — **System:** A301
- **Claim/Evidence:** FCF Generation is Transformational: A $2,993M FCF quarter on $45M capex is a remarkable capital efficiency ratio.
- **Categories:** numeric_metric_overmatch, A301_boundary
- **Root cause:** An FCF/capex capital-efficiency ratio triggered A301 without a demand/growth assertion.
- **Proposed general remediation principle:** Capital-efficiency metrics are not themselves A301's demand/guidance mechanism.

### gold-dev-068 (nh-dev-079, GOOGL)

- **Gold:** NONE — **System:** A102
- **Claim/Evidence:** The Gemini/Zocdoc healthcare booking partnership — cutting patient wait times from 31 days to 72 hours — is a tangible example of AI converting into real-world revenue.
- **Categories:** a101_a102_a103_boundary_confusion, generic_ai_mention
- **Root cause:** An AI application's commercial outcome (healthcare booking partnership) triggered A102 without a stated inference-compute-demand mechanism.
- **Proposed general remediation principle:** A102 requires a stated inference/enterprise-compute-demand signal, not any AI-application business outcome.

### gold-dev-069 (nh-dev-081, MSFT)

- **Gold:** NONE — **System:** A103
- **Claim/Evidence:** Unprecedented CapEx Acceleration: Capital expenditures nearly doubled from $64.55B (FY25) to $115.95B (FY26) — an 79.6% increase.
- **Categories:** numeric_metric_overmatch, bare_keyword_overmatch
- **Root cause:** A bare capex-increase figure, with no explicit AI/datacenter/power/server framing in the claim text, triggered A103.
- **Proposed general remediation principle:** A bare capex number is not sufficient for A103 without a stated infrastructure-buildout characterization.

### gold-dev-070 (nh-dev-082, AMD)

- **Gold:** NONE — **System:** A103
- **Claim/Evidence:** Data center revenue trajectory: Prediction markets see 90% probability of >$6.5B Q2 data center revenue.
- **Categories:** numeric_metric_overmatch, bare_keyword_overmatch
- **Root cause:** A probabilistic forecast of a 'data center revenue' threshold triggered A103 via the keyword, not an infrastructure-buildout assertion.
- **Proposed general remediation principle:** Same as gold-dev-069; also a forecast/probability is not itself a buildout signal.

### gold-dev-077 (nh-dev-090, MU)

- **Gold:** NONE — **System:** A601
- **Claim/Evidence:** It gaps to $848 and retests the July low with momentum firmly negative, MACD crossing lower, and the institutional community reading the hyperscaler caution as validation of the Evercore thesis.
- **Categories:** technical_indicators_to_a601
- **Root cause:** Technical momentum language plus a vague, unexplained 'Evercore thesis' reference triggered A601.
- **Proposed general remediation principle:** Same technical-indicators-insufficient-for-A601 principle as gold-dev-020/063.

### gold-dev-081 (nh-dev-095, SNDK)

- **Gold:** A301 — **System:** A201
- **Claim/Evidence:** Given the revenue surge, this may be intentional demand-building, but inventory management should be watched.
- **Categories:** multi_signal_handling, A201_cycle_pricing_confusion
- **Root cause:** A secondary 'inventory management should be watched' clause was weighted over the primary 'revenue surge' clause, flipping A301 to A201.
- **Proposed general remediation principle:** When Evidence contains both a primary demand/revenue signal and a secondary cautionary clause, the primary asserted mechanism governs, not a secondary caveat keyword.

### gold-dev-085 (nh-dev-100, SNDK)

- **Gold:** NONE — **System:** A304
- **Claim/Evidence:** I say it's a sign of peak-cycle pricing.
- **Categories:** bare_keyword_overmatch, A304_valuation_boundary
- **Root cause:** The ambiguous word 'pricing' in 'peak-cycle pricing' was read as stock/valuation pricing rather than product/commodity pricing.
- **Proposed general remediation principle:** An ambiguous keyword must not be resolved toward whichever Alpha it superficially resembles without the Alpha's own mechanism being stated.

### gold-dev-086 (nh-reserve-002, NVDA)

- **Gold:** NONE — **System:** A301
- **Claim/Evidence:** Metric: Gross Profit; Q1 FY26 (Apr-2026): $61.16B; Q4 FY25 (Jan-2026): $51.09B; Q3 FY25 (Oct-2025): $41.85B; Q2 FY25 (Jul-2025): $33.85B; Q1 FY25 (Apr-2025): $26.67B
- **Categories:** numeric_metric_overmatch, A301_boundary
- **Root cause:** A multi-quarter gross-profit figure series (rising, but uncharacterized in words) triggered A301 -- the classifier computed the trend itself rather than requiring the Evidence to state it.
- **Proposed general remediation principle:** A rising number series the Evidence itself never characterizes as growth is not sufficient; the reader-computed trend does not substitute for the Evidence's own words.

### gold-dev-091 (nh-reserve-007, MSFT)

- **Gold:** NONE — **System:** A301
- **Claim/Evidence:** And the revenue is already showing up.
- **Categories:** bare_keyword_overmatch, A301_boundary
- **Root cause:** A vague 'revenue is already showing up' statement with no specifics triggered A301 from the word 'revenue' alone.
- **Proposed general remediation principle:** A vague assertion with no supporting growth/demand specifics is not sufficient for A301.

### gold-dev-096 (nh-reserve-013, TSM)

- **Gold:** NONE — **System:** A101
- **Claim/Evidence:** But the palm pilot era was characterized by massive investment in infrastructure with minimal consumer adoption.
- **Categories:** generic_ai_mention, negation_invalidation_as_positive
- **Root cause:** A historical Palm-Pilot-era analogy (infrastructure investment WITHOUT adoption -- if anything cautionary) triggered A101.
- **Proposed general remediation principle:** A historical cautionary analogy, especially one describing adoption failing to materialize, must not be scored as a current positive AI-demand signal.

### gold-dev-098 (nh-reserve-016, AMD)

- **Gold:** NONE — **System:** A304
- **Claim/Evidence:** Strategic Actions: 1) Establish or add to the AMD position in tranches rather than a single lump sum, given the genuine valuation and competitive risks.
- **Categories:** bare_keyword_overmatch, A304_valuation_boundary
- **Root cause:** The word 'valuation' in a generic position-sizing risk disclaimer ('genuine valuation and competitive risks') triggered A304 without a specific rich-multiple/downside conclusion.
- **Proposed general remediation principle:** A304 requires valuation to be the stated, specific downside conclusion, not one generic risk-factor label in a hedging recommendation.
