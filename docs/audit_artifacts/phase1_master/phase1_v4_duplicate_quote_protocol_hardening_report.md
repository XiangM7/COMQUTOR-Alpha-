# Phase 1 §5.1 — Duplicate Quote Protocol and Rejected Forensics Hardening

Status: **PASS (offline protocol/persistence hardening only)**  
Provider calls: **0**  
Original live Shadow Canary: **FAIL, unchanged**  
Production authority: **LEGACY_ADAPTER**

## Versioning decision

Inspection established **Case B**. v4 had stable deterministic candidate IDs and offsets internally, but its Provider-visible request exposed only numeric location hints and its output shape contained `supporting_quotes` without a claim/quote-level candidate binding. Prompt v4 also stated that a candidate ID was never required. A safe duplicate-location contract therefore required a Provider-visible output change.

The frozen v4 prompt was not edited. The additive identity is:

- Parent: `structured_adapter.claim_extraction_shadow.v4`
- New protocol: `structured_adapter.claim_extraction_shadow.v4.1`
- v4.1 SHA-256: `c5ac3a9b44df24970d27ebd5670cb7f09eb934b01a0d99d7cd4ff93e5f225c6b`
- Semantic rule delta: `NONE`
- Location protocol delta: `CANDIDATE_BINDING`

The existing `candidate_segment_id` algorithm is reused. Each Provider-visible candidate is bound to the current run, ticker, agent, agent output, source-report hash, deterministic source span, and candidate-text hash. The Provider may return only the quote and at most one pre-registered candidate ID; it cannot supply offsets.

## Deterministic duplicate resolution

The resolver always finds every exact character-for-character occurrence in the full source report first. A unique global occurrence resolves directly. A duplicate resolves only when the Provider selected a known candidate and exactly one complete occurrence lies inside that candidate’s deterministic span.

Missing, unknown, wrong-identity, zero-local-match, and multiple-local-match bindings reject. There is no first/nearest match, fuzzy matching, semantic similarity, Markdown normalization, whitespace normalization, or alternative LLM fallback. Overlapping candidates remain allowed because only the explicitly selected candidate is evaluated.

All seven required synthetic cases pass offline: no candidate rejects; candidate A and B resolve their respective occurrences; unknown and wrong-source candidates reject; candidates containing both or zero occurrences reject.

## Rejected forensic persistence

Parsed-but-rejected v4.1 output is now retained as a bounded `REJECTED_CANDIDATE / NON_AUTHORITATIVE / FORENSIC_ONLY` payload. It preserves the proposed claim fields and, for each failed evidence item, the exact quote/hash, global match count and offsets, selected candidate, candidate span, candidate-local matches, resolution status/reason, and source-report hash.

Unexpected fields and optional free-form abstention notes are not retained in rejected forensics. Rejected candidates remain ineligible for cache admission and produce zero admitted claims. Existing accepted Exact Replay semantics are unchanged. The new `REJECTED_DETERMINISTIC_REPLAY` revalidates payload/request identity, candidate binding, offsets, diagnostics, and rejection reason with zero Provider calls.

## Historical and next-stage truth

The original Technical Canary response was not persisted, so it was not reconstructed or revalidated. `HISTORICAL_TECHNICAL_REVALIDATION=NOT_APPLICABLE_RESPONSE_NOT_PERSISTED` remains true.

The v4 quality baseline remains `PASS_V4`; v4.1 has not been exercised by a real Provider. Therefore `READY_FOR_RECANARY=NO`. The only permitted next stage is `V4_1_LIMITED_PROVIDER_QUALIFICATION`. Recanary, production cutover, §5.2, and all Provider calls were not run.
