# Structured Claim Shadow — v1 Prompt Root-Cause Report

Provider calls made to produce this report: **0**. Every number below comes from
`scripts/audit_prompt_v1_root_cause.py`, which builds the exact v1 request through
real production code (`build_candidate_segments` → `build_shadow_request` →
`build_shadow_prompt_input`) for the frozen NVDA `fundamental_agent` Smoke report
(`agent_output_id=0e044e37-862c-43be-871c-31012cd660e7:fundamental_agent:fundamentals_report`,
`report_sha256=6e745b7c19...f954f1`, raw length 13,887 chars). The recomputed
`candidate_segments` are byte-identical to the ones actually persisted by the real,
already-attempted Anthropic Smoke run
(`outputs/evaluations/phase1-master-anthropic-20260807T011444Z-7ce7880c/reports/NVDA/fundamental/candidate_segments.json`),
and the recomputed total (98,633 chars) matches the earlier ad-hoc diagnostic's
observed real request (98,529 chars; the ~100-char difference is explained by a
different `run_id` string length between the two runs). This is a reproduction of
the real failed request, not a synthetic stand-in.

## Answer: where did 13,887 raw report chars become 98,633 request chars?

| # | Component | Chars | % of total |
|---|---|---:|---:|
| 1 | `candidate_segment_id` (163× repeats of the 75-char `agent_output_id`) | 22,331 | 22.64% |
| 2 | `evidence_hint` (163× — **byte-identical to `claim_hint` in 100% of segments**) | 17,993 | 18.24% |
| 3 | `claim_hint` (163× cleaned report fragments) | 17,504 | 17.75% |
| 4 | `agent_report` (the actual report — needed exactly once) | 14,160 | 14.36% |
| 5 | `source_section` (163× heading text) | 7,087 | 7.19% |
| 6 | `semantic_authority` (163× repeats of the constant `false`) | 4,238 | 4.30% |
| 7 | `candidate_index` (163× small integers, verbose key names) | 3,313 | 3.36% |
| 8 | fixed instruction (security/claim-rules/output-shape/examples, sent once) | 3,948 | 4.00% |
| 9 | `source_spans[].exact_quote` (only 21/163 segments have one) | 1,958 | 1.99% |
| 10 | array/object JSON punctuation inside `candidate_segments` | 1,468 | 1.49% |
| 11 | identity metadata (run_id/ticker/agent/hashes/prompt version, sent once) | 668 | 0.68% |
| 12 | span offsets + span-level JSON punctuation | 877 | 0.89% |
| 13 | source_metadata / candidate contract-version / source strings | 332 | 0.34% |
| 14 | factor_vocabulary (13 short strings) | 248 | 0.25% |
| 15 | other (top-level JSON punctuation, the `SHADOW_REQUEST_JSON:` label) | 42 | 0.04% |
| | **Total** | **98,633** | **100%** |

`candidate_segments` as a whole (rows 1,2,3,5,6,7,9,10,12 above) = **79,235 chars
= 80.33% of the entire request.** Everything the model actually needs to do its
job — the fixed instruction plus the report itself — is **18,108 chars, 18.36% of
the request.**

## ASSUMED_CAUSE verdict (task section 23)

The task's working hypothesis was "candidate segments re-embed the report as
duplicated text." Measured against real data:

- **ASSUMED_CAUSE_CONFIRMED** for the *headline claim* — `candidate_segments` is
  the dominant cost driver (80.33% of the request), and a large, real fraction of
  that (37,455 chars, 37.97% of the whole request) is exactly what was
  hypothesized: report-derived text (`claim_hint`/`evidence_hint`/`exact_quote`)
  sent a second time outside the single `agent_report` copy.
- **ASSUMED_CAUSE_REFINED, not simply confirmed, for the mechanism** — the single
  largest bucket is *not* text duplication at all. It is `candidate_segment_id`
  verbosity (22,331 chars, 22.64%): `_candidate_id()` in
  `structured_output_shadow.py` builds every one of the 163 IDs as
  `f"{agent_output_id}:shadow-candidate:{digest[:20]}"`, re-embedding the full
  75-character `agent_output_id` 163 times for a value the model never needs in
  that form (see responsibility matrix). Combined with `source_section` (7,087)
  and the constant `semantic_authority=false` repeated 163 times (4,238),
  **candidate_segment *metadata* (41,780 chars, 42.36%) is slightly larger than
  candidate_segment *text* (37,455 chars, 37.97%).** Both must be fixed for v2 to
  hit the size target; fixing only text duplication would leave ~42% of the
  request untouched.
- **ASSUMED_CAUSE_REJECTED for the pre-listed alternative suspects** (task
  section 4C/D/E): the fixed prompt's schema is explained exactly once as prose
  and exactly once as a JSON skeleton (no third JSON-Schema-object restatement —
  `duplicated_schema_chars = 0`, measured); `factor_vocabulary` is already the
  minimal id-only list (248 chars, 0.25%, no descriptions/aliases ever sent);
  examples are 842 chars (0.85%) — real but not material even if fully deleted.
  See `v1_duplication_map.json` findings C/D/E for the measured detail behind
  each rejection.

## The single worst individual finding

`evidence_hint` is **byte-identical to `claim_hint` in all 163/163 segments**
(`v1_request_breakdown.json.duplication.identical_claim_and_evidence_hint_segment_pct
= 100.0`). This is not approximate overlap — it is the exact same string sent
twice, for every single candidate, with zero incremental information. Root cause:
`build_candidate_segments()` in `structured_output_shadow.py` does
`evidence = str(segment.get("evidence") or claim)`, and
`extract_claim_segments_with_audit()` (the read-only, do-not-modify production
segmenter) never populates a distinct `evidence` field — so the fallback fires
for every segment, unconditionally. Removing `evidence_hint` alone recovers
17,993 chars (18.24% of the request) with **zero** semantic loss, since it never
carried information `claim_hint` didn't already carry.

## Second-worst finding: 142/163 candidate hints have no verified location

Only 21 of 163 candidate segments (12.9%) have a `source_spans` entry that
`_locate_exact_hint()` actually found verbatim in the raw report. The other 142
(87.1%) are *cleaned* text (`_clean_markdown_inline` strips Markdown, collapses
table rows to `"Header: value"` pairs, etc.) that no longer appears as an exact
substring of the raw report — `source_spans: []`. This is a real, measured
constraint on the compression design, not an assumption: **v2 cannot replace all
163 hints with `{start, end}` offsets**, because 142 of them have no offset to
give. `extract_claim_segments_with_audit` is a protected production file
(`structured_output_adapter.py`) that this task must not modify, so improving the
locate-hit-rate upstream is out of scope here. v2's design (below) sends offset
hints only for the 21 verified segments and relies on the model's own reading of
the one full report copy for the rest — which matches ADR-008's own framing of
candidate segments as non-authoritative hints, not a required coverage
mechanism.

## Component classification (task section 5)

| Component | Chars | % total | Classification | Why present | Remove from Provider input? | Semantic risk | Replacement mechanism |
|---|---:|---:|---|---|---|---|---|
| Fixed instruction (security/rules/shape/examples) | 3,948 | 4.00% | SEMANTICALLY_REQUIRED_BY_MODEL | Defines the task | No | High if removed | none — already minimal |
| `agent_report` | 14,160 | 14.36% | SEMANTICALLY_REQUIRED_BY_MODEL | The only source text | No | High if removed | none — sent once in v2 too |
| `claim_hint` (142 unlocated) | ~15,200 | ~15.4% | MODEL_HINT_OPTIONAL → dropped | Segmentation aid | Yes | Low (ADR-008: hints are non-authoritative; report is present) | model re-derives from `agent_report` |
| `claim_hint` (21 located) | ~2,300 | ~2.3% | MODEL_HINT_OPTIONAL, kept as offsets | Segmentation aid with verified anchor | Text form: yes | Low | send `{id,start,end}`, no text |
| `evidence_hint` (all 163) | 17,993 | 18.24% | DUPLICATED | Always equals `claim_hint` (measured 100%) | Yes, entirely | None — proven zero incremental information | delete field |
| `exact_quote` (21 located) | 1,958 | 1.99% | DETERMINISTICALLY_RECONSTRUCTABLE | Convenience copy of `report[start:end]` | Yes | None — `validate_shadow_bundle` already re-derives/enforces it independently | caller computes `report[start:end]` after the model returns offsets |
| `candidate_segment_id` (full form) | 22,331 | 22.64% | DETERMINISTICALLY_RECONSTRUCTABLE | Global lineage ID | Yes | None — model only needs a short local reference | send `candidate_index` (already present) instead; caller maps back to the full ID |
| `source_section` (142 unlocated) | ~6,175 | ~6.3% | MODEL_HINT_OPTIONAL → dropped | Heading context | Yes | Low | omitted along with its (unlocated) candidate |
| `source_section` (21 located) | ~912 | ~0.9% | MODEL_HINT_OPTIONAL, kept | Heading context, near-free at this volume | No | None | kept verbatim |
| `semantic_authority` (163× `false`) | 4,238 | 4.30% | UNNECESSARY (as a per-item field) | Restates an invariant that never varies | Yes, entirely | None — the fact is unconditional per ADR-008 | one sentence in the fixed instruction instead of 163 repetitions |
| `candidate_index` | 3,313 | 3.36% | SEMANTICALLY_REQUIRED_BY_MODEL (in v2, becomes the reference id) | Needed so the model can cite a candidate | No (repurposed, not removed) | None | reused as the v2 `id` |
| `source_report_sha256` / `prompt_sha256` / `prompt_version` (as *input* asking the model to copy them into its *output*) | ~200 | ~0.2% | VALIDATOR_ONLY / DETERMINISTICALLY_RECONSTRUCTABLE | Caller already knows these; validator enforces the real values regardless of what the model echoes | Yes, from the *response* schema (still fine to keep small in the *request* for framing) | None | caller splices identity into the canonical bundle after normalization |
| `candidate_segment_contract_version` / `candidate_segment_source` | ~150 | ~0.15% | VALIDATOR_ONLY / UNNECESSARY | Caller provenance bookkeeping; confirmed (grep) never read by the model's instructions or by `validate_shadow_bundle` from the request | Yes | None | kept only in the persisted audit artifact, not the wire payload |
| `factor_vocabulary` | 248 | 0.25% | SEMANTICALLY_REQUIRED_BY_MODEL | Closed vocabulary the model must select from | No | High if removed | none — already minimal |
| `run_id`/`ticker`/`agent`/boundary markers | ~350 | ~0.35% | SEMANTICALLY_REQUIRED_BY_MODEL | Context + prompt-injection framing (section 18) | No | Medium if removed (loses instruction/data separation) | none |
| JSON structural punctuation | 42 | 0.04% | UNNECESSARY but unavoidable | JSON syntax | N/A | None | not worth engineering around |

Full per-field detail, source functions, and file paths: `v1_prompt_source_map.json`
and `v1_duplication_map.json`.
