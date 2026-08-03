# Entity Alpha Exposure Seed Methodology v0.1

Status: **Draft for John/product-owner review**  
Effective date: **2026-07-31**

## What the seed represents

The YAML values represent **historical_mapping**, the stable prior relationship between a ticker and an Alpha Structure. They are not the final runtime exposure score.

`final_exposure = 0.50 × historical_mapping + 0.30 × current_evidence + 0.20 × agent_confidence`

`current_evidence` and `agent_confidence` must be computed per run and must not be stored as permanent seed values.

## Score meaning

| Score | Meaning |
|---:|---|
| 0.00 | Reviewed and effectively no exposure |
| 0.10 | Very weak / incidental |
| 0.25 | Weak indirect exposure |
| 0.40 | Meaningful but secondary |
| 0.55 | Moderate |
| 0.70 | Strong |
| 0.85 | Core |
| 0.95 | Defining exposure |

Missing or unreviewed values should be `null`, not `0.00`.

## Alpha definitions

- A001 Rate Cut Cycle: rate/duration and financing-cost sensitivity
- A003 Liquidity Expansion: sensitivity to market liquidity and risk appetite
- A101 AI Expansion: AI training-compute demand exposure
- A102 Inference Explosion: inference and model-serving workload exposure
- A103 AI Infrastructure: data-center, networking, power, cooling and rack buildout exposure
- A201 Semiconductor Supercycle: semiconductor inventory/order/ASP/capex-cycle exposure
- A301 Revenue Expansion: revenue acceleration → EPS revisions → repricing exposure
- A304 Multiple Compression: valuation and expectation-compression sensitivity
- A501 Recession Risk: economic and earnings-downturn sensitivity
- A601 Narrative Momentum: theme, positioning and reflexive market-narrative sensitivity

## Drafting principles

1. Company filings and official investor materials outrank LLM judgment or media narratives.
2. Direct business exposure and market sensitivity are distinct, but both can be represented where the Alpha definition requires it.
3. The first version uses 0.05 increments to avoid false precision.
4. John/product owner must approve the methodology and each ticker row before production use.
5. Initial rollout should be shadow-only. Do not alter Activation until golden-case review is complete.
6. SNDK is included as an extra regression ticker because it motivated the original AI-over-trigger concern; it is not one of the ten formal plan tickers.

## Primary materials reviewed

- NVIDIA FY2026 Form 10-K / annual report
- AMD FY2025 Form 10-K
- Microsoft FY2025 Annual Report
- Alphabet FY2025 Form 10-K and investor disclosures
- Amazon FY2025 Form 10-K and AWS official AI infrastructure materials
- Broadcom FY2025 Form 10-K and FY2025 results
- TSMC 2025 Annual Report
- Supermicro FY2025 Form 10-K and official product disclosures
- Invesco QQQ official product/holdings information
- State Street SPY official product/holdings information

## Approval checklist

- challenge any score difference greater than 0.10 versus the reviewer;
- record approval status and reviewer;
- freeze the approved file with a hash and effective date;
- re-review quarterly or after a material business-model change.

## Recommended rollout

Start in shadow mode. Once approved:

- exposure < 0.30: normally ineligible for dominant;
- exposure < 0.60: normally ineligible for regime_level;
- a strong-evidence override must require direct ticker-specific evidence, multiple independent evidence facts, multiple agents, and an admitted graph path, with a stored reason.

These gates are proposed policy, not statements from the source plan.
