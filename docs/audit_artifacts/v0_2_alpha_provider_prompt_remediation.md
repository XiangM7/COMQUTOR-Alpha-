# v0.2 Day 4B — Alpha Provider Prompt Remediation

Scope: `DAY_4B_ALPHA_PROVIDER_PROMPT_REMEDIATION`. Full detail in `v0_2_alpha_provider_prompt_remediation.json`. Frozen Gold baseline, frozen conflict pairs, and QQQ rule scope **unchanged**.

## Provider-Facing Alpha Semantic Path (traced end-to-end)

| Stage | Location |
|---|---|
| Prompt source / instruction text | `comqutor_alpha/structure_engine/week2_llm.py::_TASK_INSTRUCTIONS['alpha_classifier']` / `['alpha_classifier_batch']` |
| Taxonomy injection (what the model sees per Alpha) | `comqutor_alpha/structure_engine/alpha_mapper.py::_alpha_taxonomy_request_block()` |
| Model/provider call site | `alpha_mapper.py::_classify_alpha_with_llm` (single) / `_classify_alpha_batch_with_llm` (batched) → `llm_gateway.invoke_json_with_trace('alpha_classifier'[_batch], ...)` |
| Response parser | inline `validate_response` closures in the same two functions — enforce exact `{decision, selected_alpha_id}` schema |
| `none` semantics | first-class, successful "no canonical Alpha materially fits" answer — never permitted merely to avoid a close call between two plausible Alphas |
| Multi/wrong-Alpha semantics | exactly one `alpha_id` per claim; must compare competing plausible Alphas directly and pick the closer mechanistic fit |
| Taxonomy content injected (before) | `alpha_id`, `alpha_name`, `definition` (one abstract sentence) only |
| Taxonomy content injected (after) | + `trigger_signals`, `confirmation_signals` — already-authored `alpha_taxonomy_v1.yaml` fields, not previously sent to the model |

## Root-Cause-to-Prompt-Deficiency Mapping

| Category | Count | Deficiency Found |
|---|---:|---|
| `SYSTEM_FALSE_NEGATIVE_LLM_NONE` | 26 | Only an abstract one-sentence thesis to match against — paraphrased/indirect/company-specific evidence plausibly reads as not "directly" engaging any Alpha, biasing toward `none`. |
| `SYSTEM_FALSE_POSITIVE_OVERMATCH` | 10 | No explicit rule against attributing a bare, standalone financial figure/ratio (no stated mechanism) to a loosely valuation-/growth-adjacent Alpha. |
| `OTHER_WRONG_ALPHA_SUBSTITUTION` | 10 | Same abstract-thesis-only deficiency, starving the existing "compare mechanisms" instruction of concrete discriminating signal. |
| `CROSS_FAMILY_GROWTH_VS_RISK_CONFUSION` | 4 | Same deficiency, applied to growth-vs-risk neighbor pairs. |
| `A101_A102_A103_BOUNDARY_CONFUSION` | 2 | Same deficiency; these 2 samples also predate commit `c454245`'s A101/A103 worked example (age is a partial, independent factor here). |

## Changes Applied

1. **`alpha_mapper.py::_alpha_taxonomy_request_block`** — added `trigger_signals`/`confirmation_signals` to each taxonomy entry (already-authored data, zero new Alpha IDs, applies automatically to the full taxonomy and to both call sites).
2. **`week2_llm.py`, both `alpha_classifier` prompts** — added two symmetric, general instruction sentences (kept identical between single/batch, preserving the existing "copied verbatim" invariant): (a) treat trigger/confirmation signals as positive evidence under paraphrase; (b) a bare standalone financial figure/ratio is never sufficient alone.
3. **Version bookkeeping** — `alpha_classifier` `v3→v4`, input schema `v2→v3`; `alpha_classifier_batch` `v1→v2`, input schema `v1→v2`; output schema unchanged (response contract didn't change) — per this codebase's own ADR-005 convention, so no pre-remediation cached result is ever silently reused as post-remediation.
4. **Two test fixtures repaired** — both hardcoded pre-remediation prompt text/version strings; updated to reference the live source constants instead of a stale duplicate. No assertion weakened.

**Forbidden items avoided:** no sample-ID examples, no holdout-specific phrasing, no ticker-specific hack, no changed expected label, no Gold rule change, no new Alpha ID, no denominator change, no deterministic fallback added to bypass the Provider.

## Prompt Hashes

| Prompt | Pre-change SHA256 | Post-change SHA256 |
|---|---|---|
| `alpha_classifier` | `a2ca2a32be2d5c22301a0905112727d2c43aece60b1d9e680c8092c3d67c25d8` | `36bf5a632dee1e3cd8f4b2ac04fa3498db63cf99275d309157365c59c5bf77e9` |
| `alpha_classifier_batch` | `0caa5b77b77a97618e92e1b3f254edf8749bae5aa4a21a42ba5d60a539effff0` | `291f69db9c495eebc75c52cbf5d9ce9f97401af3ec7a735765f01f43af6d876e` |

## Local Non-Provider Testing

`pytest tests/test_alpha_mapper.py tests/test_alpha_mapper_llm_authority.py tests/test_ai_alpha_mapper_discrimination.py tests/test_alpha_mapper_nvda_real_report.py tests/test_week2_semantics.py tests/test_evidence_stance_classifier.py tests/test_claim_quality.py tests/test_structured_output_adapter.py tests/test_week2_llm_markdown_fence_parsing.py tests/test_week2_llm.py tests/test_week2_llm_semantic_runtime_integration.py -q`

→ **384 passed, 1 skipped (Provider smoke test, correctly skipped — no credentials), 0 failed.**

Two task-attributable failures were found and fixed (both fixture staleness, not logic regressions — see JSON for detail). These tests confirm prompt construction, schema, parser compatibility, taxonomy injection, and deterministic surrounding logic only — **they do not prove semantic accuracy** and are not reported as Alpha validation.

## Improvement Claim Status

**Not claimed.** No accuracy improvement is asserted until Provider-backed validation actually runs against the same 200-sample independent holdout — see Provider Environment Check below.

## Provider Environment Check

| Variable | Status |
|---|---|
| `COMQUTOR_REAL_TRADINGAGENTS_ENABLED` | ABSENT |
| `OPENAI_API_KEY` | ABSENT |
| `ANTHROPIC_API_KEY` | ABSENT |
| `FINNHUB_API_KEY` | ABSENT |
| `GOOGLE_API_KEY` | ABSENT |
| `PROVIDER_API_KEY` | ABSENT |
| `COMQUTOR_API_KEY` | ABSENT |

**Result: `PROVIDER_VALIDATION_BLOCKED_BY_ENVIRONMENT`.** Provider-backed re-validation of the 200-sample independent holdout, and Fresh NVDA/QQQ E2E, were not executed. No result is fabricated.
