# Phase 1 §5.1 v4.2: Why Candidate Binding Was Removed

Concise design-history record, so a future developer never reintroduces
`candidate_id`-based Evidence location without first re-reading this.

## 1. v4 required global exact Evidence provenance

v4's `EvidenceQuoteResolver` (`structured_output_shadow_v4.py`) located every
Provider-proposed `supporting_quotes` entry by exact, character-for-character
search over the complete source report. A quote with zero exact occurrences
was rejected. A quote with exactly one exact occurrence was accepted. A quote
with more than one exact occurrence (`AMBIGUOUS_MULTIPLE_MATCH`) was
rejected unless an *optional*, Provider-referenced candidate hint span
happened to disambiguate it -- never a default first-match.

## 2. Duplicate-exact-quote ambiguity motivated v4.1

The real, real-Provider v4 Live-Shadow Canary (4 NVDA reports) accepted 3/4
slots cleanly. The 4th (`technical`, `market_agent`/`market_report`) was
rejected: the model's quoted closing price appeared twice in the same report
(once in a snapshot table, once in a summary table further down), and no
disambiguating candidate hint was referenced, so the resolver correctly,
safely rejected it. This was correct fail-closed behavior, not a defect --
but it meant zero claims were admitted for that report.

## 3. v4.1 introduced Provider candidate_id binding

The product owner's response was `structured_adapter.claim_extraction_shadow.v4.1`
(`structured_output_shadow_v4_1.py`): each `supporting_evidence` item could
carry an explicit `candidate_id`, mandatory whenever a quote had more than
one global exact match, cross-validated against a caller-owned candidate
manifest (`build_candidate_manifest_v4_1`). Offline tests passed cleanly.

## 4. The real final v4.1 Re-Canary showed 58 globally unique, valid Evidence quotes were falsely rejected

The pre-registered, real, 4-slot final v4.1 Re-Canary
(`outputs/canaries/phase1-v4-1-final-recanary-20260810T230224Z/`) failed
0/4. A full, read-only, Provider-zero root-cause diagnosis
(`docs/audit_artifacts/phase1_master/phase1_v4_1_location_root_cause.md`)
of all 99 real, persisted Evidence items found: **58 of 61 rejections
(95%) were quotes with exactly one global exact match** -- already
unambiguous, already copied correctly -- that failed *only* because the
model additionally supplied an optional `candidate_id` whose registered
span did not happen to contain that already-unique quote. Source and
resolver text were byte-identical in all 4 slots (confirmed by SHA256);
zero fabricated quotes; zero canonical-relations contamination; zero
truncation; zero candidate-window overlap.

## 5. Only 3/99 were genuine duplicates

The narrow problem v4.1 was built to solve -- a quote genuinely occurring
more than once in the source -- occurred exactly 3 times across all 99
Evidence items examined (2 in `fundamental`, 1 in `technical`, the latter
almost certainly the same repeated-closing-price case from item 2 above).
In all 3, the model supplied no `candidate_id` at all, and the resolver
correctly, safely rejected them exactly as designed.

## 6. Product owner rejected Provider-controlled internal addressing

Given (4) and (5), the product owner's final decision: the Provider must
never be responsible for identifying WHERE its Evidence is located inside
COMQUTOR's internal representation -- not a `candidate_id`, not an offset,
not a segment number. The Provider's job is WHAT the claim and Evidence
are; COMQUTOR's own deterministic code is the sole authority for WHERE.

## 7. v4.2 removes active candidate binding

`structured_adapter.claim_extraction_shadow.v4.2`
(`structured_output_shadow_prompt_v4_2.py`,
`structured_output_shadow_v4_2.py`) removes every candidate/segment/offset
concept from the active runtime: no `candidate_hints` in the wire request,
no `candidate_id`/`candidate_ids` field anywhere in the wire response
schema (a claim or abstention carrying one is rejected as an unapproved
field, the same as any other unrecognized field), no candidate manifest,
no `build_candidate_segments` call anywhere in the active v4.2 path. The
following v4.1 candidate-only failure modes are consequently unreachable
in v4.2 because the concepts they depend on do not exist in this module:
`CANDIDATE_LOCAL_NO_EXACT_MATCH`, `CANDIDATE_ID_UNKNOWN`,
`CANDIDATE_SOURCE_IDENTITY_MISMATCH`, `AMBIGUOUS_CANDIDATE_REQUIRED`.
Semantic extraction rules (what counts as a faithful claim, evidence
completeness, uncertainty/attribution preservation, Markdown exactness)
are otherwise unchanged from v4 -- the prompt text is a small, anchored,
verifiable delta from v4's frozen text (four edits, each checked to occur
exactly once), not a rewrite.

## 8. v4.2 uses deterministic global exact search

`resolve_supporting_quote_v4_2(*, report, quote)` -- no candidate/segment
parameter of any kind. Exact character-for-character search only; never
fuzzy, normalized, embedding-based, Levenshtein-repaired, or LLM-repaired.

## 9. Duplicate exact matches use earliest occurrence as canonical provenance

Zero matches: reject (`NO_EXACT_MATCH`). One match: accept
(`UNIQUE_EXACT_MATCH`). More than one match: accept the occurrence with
the smallest start offset (`DUPLICATE_ACCEPTED_EARLIEST_OCCURRENCE`),
recording the full match count, every offset, the selected index, and
`selection_policy="FIRST_EXACT_OCCURRENCE"`. This is a deterministic
PROVENANCE choice only -- never a claim about which occurrence the model
"intended," and it never drives any semantic field (direction, factor,
entities, claim text).

## 10. Semantic support remains independent from provenance existence

Exact-match provenance still proves only that the quoted text exists
verbatim in the correct, hashed source report -- never that it actually
supports the claim, and never that the claim's stated certainty/attribution
level is accurate. `EXACT_MATCH == CLAIM_PROVEN` is not, and must never
become, production logic. That judgment remains reserved for human/AI
semantic review, exactly as under v4 and v4.1.

## Measured outcome (real data, not a synthetic benchmark)

Re-running the new v4.2 resolver against the actual 99 real, persisted
Evidence quotes and real source texts from the failed v4.1 Re-Canary
(`scripts/replay_v4_2_against_real_v4_1_evidence.py`, zero Provider calls):
**99/99 now resolve** -- 38 that already worked, the 58 falsely-rejected
unique quotes (now correctly accepted since candidate_id is no longer
consulted), and the 3 genuine duplicates (now accepted via earliest
occurrence). Full result:
`docs/audit_artifacts/phase1_master/phase1_v4_2_real_evidence_replay.json`.

## What remains unchanged

`QUALITY_GATE=PASS_V4` (semantic baseline; not reopened by this repair).
`PRODUCTION_AUTHORITY=LEGACY_ADAPTER` (unchanged by this task). Historical
v4, v4.1, the failed Live-Shadow Canary, and the failed final v4.1
Re-Canary are all preserved, unmodified, exactly as they completed. This
document, the root-cause diagnosis, and the real-evidence replay together
are the permanent record of why candidate binding was tried and then
removed -- so it is never silently reintroduced.
