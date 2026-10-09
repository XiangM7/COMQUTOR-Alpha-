# v0.2 Final Performance Log

All values verified against source artifacts this task (`outputs/runs/{run_id}/llm_semantic_manifest.json` and `llm_semantic_calls.jsonl`), not reused blindly from a prior day's report.

## Latest NVDA Fresh (`ded99ecd-a186-4a90-859e-0f1a0efa43db`)

| Metric | Value |
|---|---:|
| Wall-clock | 1923s (32m03s) |
| Upstream calls | 12 TradingAgents agents |
| Semantic Provider calls | 819 |
| — Alpha classification | 754 |
| — Evidence stance | 34 |
| — Structure extractor | 3 |
| — Structured adapter | 10 |
| Retries | 18 |
| Timeouts | 0 |
| Token usage | `NOT_AVAILABLE` — field present, every value null |
| Measured cost | `NOT_AVAILABLE` |
| Estimated cost | Not made — no reliable token basis |

## Latest QQQ Fresh (`0d890564-2479-4361-94e8-25c48af3b9a8`)

| Metric | Value |
|---|---:|
| Wall-clock | 1721s (28m41s) |
| Upstream calls | 12 TradingAgents agents |
| Semantic Provider calls | 812 |
| — Alpha classification | 747 |
| — Evidence stance | 23 |
| — Structure extractor | 8 |
| — Structured adapter | 10 |
| Retries | 24 |
| Timeouts | 0 |
| Token usage | `NOT_AVAILABLE` |
| Measured cost | `NOT_AVAILABLE` |
| Estimated cost | Not made |

**No inference was made that QQQ's ~10.5% shorter wall-clock time implies any proportional reduction in API cost** — cost remains `NOT_AVAILABLE` for both, independently, since no reliable token data exists for either.

## Final Alpha Validation Provider Accounting (Day 4I, for reference — a different Provider path)

150 Provider calls, 150 successful, 0 retries, 0 timeouts — Anthropic-backed `ONE_SHOT_INDEPENDENT_FINAL_VALIDATION`, kept separate from the DeepSeek-backed Fresh E2E runs above. See `v0_2_candidate3_final_validation_result.json`.
