# Factor Resolution Contract and Alias Impact Review Sprint

Read-only audit. No production file was modified. `FACTOR_ALIASES` was never edited on
disk; all "before/after" comparisons in Part 3 were produced by monkeypatching the
dict in a running Python process and restoring it in a `finally` block before the
process exited (verified by re-reading the dict afterward).

## Baseline

- Branch: `comqutor-structure-layer`
- HEAD: `2fe129705d824d46b4bcf7f0fc1eb43e27972824` (unchanged throughout; note this is a
  newer HEAD than the previous two sprints in this thread -- the user committed the
  prior sprints' worktree changes as `2fe1297 0.1.1 test` between sessions. Not an
  action taken by this Sprint.)
- Worktree: clean (`git status --short` = 0 lines) at both start and end.
- Python: 3.13.5 (`.venv`)

## 1. Factor resolution call chain (as read from real code, not memory)

```
structured claim record (claim/evidence/factors)
    |
    v
comqutor_alpha/structure_engine/structured_output_adapter.py: adapt_raw_agent_outputs()
    - deterministic_splitter path (extraction_method="deterministic_splitter"):
      verified_factors = extract_factors(evidence) = extract_known_factors_from_text(evidence)
      record["factors"] = only values whose normalize_factor_label(value) is in verified_factors,
      PLUS verified_factors itself (structured_output_adapter.py:889-895)
      -> record["factors"] is ALWAYS a subset of the 13 canonical factors for this path.
    - llm_strict_json path (extraction_method="llm_strict_json", only for agents in
      LLM_STRUCTURED_AGENTS and only when llm_gateway is not None):
      record["factors"] = raw LLM-proposed strings, bounded to 200 chars, NOT filtered
      against verified_factors (structured_output_adapter.py:765-790).
      -> record["factors"] can contain arbitrary, non-taxonomy strings on this path.
    |
    v
comqutor_alpha/structure_engine/factor_normalizer.py (shared by both consumers below)
    - FACTOR_ALIASES: dict[canonical_factor, tuple[alias, ...]], 13 canonical factors.
    - normalize_factor_label(value): normalize_text(value), then linear-scan every
      (factor, alias) pair for an exact normalized-string match; on no match, returns
      a title-cased rendering of the input instead of "Unknown" (factor_normalizer.py:152-165).
    - extract_known_factors_from_text(text): for each canonical factor, term_in_text()
      (word/phrase-boundary regex) against every one of its aliases; OR-matched, no
      polarity/direction awareness at all (factor_normalizer.py:168-177).
    - factor_mention_span(factor, text): searches (factor_name, *its_aliases) for the
      earliest boundary-matched span; used to order left/right mentions for edge
      direction (factor_normalizer.py:196-207).
    |
    +--> comqutor_alpha/structure_engine/structure_extractor.py
    |      _extract_factors(record): normalize_factor_label() on record["factors"]
    |      values (kept unless literally "Unknown"), UNION extract_known_factors_from_text()
    |      on the record's claim+evidence text (structure_extractor.py:104-119).
    |      NOTE: no FACTOR_ALPHA_WEIGHTS-style taxonomy filter here -- any non-empty,
    |      non-"Unknown" title-cased fallback value becomes a real graph node via
    |      _make_node() (structure_extractor.py:154-170), and can become a genuine
    |      relation endpoint in _extract_edges() if factor_mention_span() finds it in
    |      the claim text (structure_extractor.py:254-268), because factor_mention_span
    |      always includes the factor's own literal name as a search alias even when
    |      FACTOR_ALIASES has no entry for it.
    |
    +--> comqutor_alpha/structure_engine/alpha_mapper.py
           _record_factors(record): same normalize_factor_label()+extract_known_factors_from_text()
           union as above, BUT then filtered to `if factor in FACTOR_ALPHA_WEIGHTS`
           (alpha_mapper.py:129-143) -- unknown/fallback factors are silently dropped
           here and can NEVER reach factor_score, candidate eligibility, or
           matched_alpha. This is an asymmetry vs. the Extractor: the Mapper is safe
           against the Unknown fallback; the Extractor is not.
           factor_score(record, alpha) = max(FACTOR_ALPHA_WEIGHTS[factor][alpha.alpha_id]
           for factor in _record_factors(record) if present) else 0.0 (alpha_mapper.py:146-155).
           factor_score feeds into the final candidate score at weight 0.30
           (score = 0.50*keyword + 0.30*factor + 0.08*direction + 0.12*semantic,
           alpha_mapper.py:231-236) and into `eligible` for non-AI alphas
           (`eligible = bool(matched_keywords) or factor > 0`, alpha_mapper.py:222).
           For A101/A102/A103, eligibility is instead fully controlled by the
           independent `evaluate_ai_alpha_gates()` hard gate (ai_alpha_discriminator.py,
           imported at alpha_mapper.py:11-15) -- factor_score still contributes to the
           numeric `score` for these three, but never to admission.
    |
    v
comqutor_alpha/graph_engine/graph_builder.py: build_structure_graph()
    - Consumes only extracted_structures.json (nodes/edges) and alpha_matches.json
      (matches) -- never re-reads raw claim text or calls factor_normalizer directly.
    - node["alpha_ids"] = union of matched_alpha over exactly this node's own
      claim_ids, restricted to claim_info["match_status"] == "matched"
      (_committed_alpha_ids_for_claim, graph_builder.py:68-72, applied per-node at
      graph_builder.py:284-296). This is a claim-realized association, not a static
      factor->alpha taxonomy table lookup -- FACTOR_ALPHA_WEIGHTS is never read here.
    |
    v
comqutor_alpha/graph_engine/activation_scorer.py / activation_scorer_v2.py
comqutor_alpha/conflict_engine/conflict_detector.py
    - grep confirms NEITHER imports factor_normalizer.py, structure_extractor.py, nor
      alpha_mapper.py. Both consume only the already-serialized structure_graph.json /
      alpha_matches.json fields (matched_alpha, ai_alpha_matches, direction, relation,
      node/edge dicts). A FACTOR_ALIASES change can therefore only reach Activation or
      Conflict indirectly, through a changed matched_alpha / factor_score / graph node,
      never through a direct re-derivation from raw text.
```

## 2. Current canonical factor / alias table (verbatim, `factor_normalizer.py:16-134`)

13 canonical factors: `AI Demand`, `AI CapEx`, `GPU Demand`, `Datacenter CapEx`,
`AI Infrastructure`, `Revenue Growth`, `Valuation Risk`, `Recession Risk`,
`Liquidity Expansion`, `Narrative Momentum`, `Semiconductor Cycle`, `Rate Cut Cycle`,
`Inference Demand`. Full alias lists are reproduced in Section 1's linked source and
were not re-typed from memory anywhere in this report -- every phrase quoted below was
re-read from the live file during this audit.

## 3. Claim-by-claim audit (real data from `alpha_matches.json`, unmodified)

### AMD claim:58 -- `news_agent:news_report:claim:58`
- claim/evidence (identical): "The key event to watch is AMD's upcoming earnings report, which will be the definitive test of whether Lisa Su's AI demand confidence translates into revenue beats that can justify the elevated valuation."
- Structured factors (`record.factors`): `['AI Demand']`
- Text-recognizable factors: same, `['AI Demand']` only -- "revenue beats" matches no alias.
- matched_alpha: `A301` (Revenue Expansion). factor_score: `0.45` (AI Demand -> A301 weight). A101 scored higher (0.5673, factor_score 1.0) but is `eligible=False` (AI hard gate rejected: bare "AI demand confidence" has no training/accelerator/investment anchor).
- Relation phrase: "translates into". Candidate source phrase: "Lisa Su's AI demand confidence". Candidate target phrase: "revenue beats". Unresolved side: **target**. Reason: no `Revenue Growth` alias covers "revenue beats" (closest existing aliases are "guidance raised", "beat and raise", "eps revisions" -- all different phrasing).

1. Missing expression type: **event/result** (a discrete "beat" outcome), not a continuous state.
2. Accurate existing canonical concept: partial -- `Revenue Growth` is the closest concept but currently only represents *stated/continuous* growth language, not point-in-time beat/miss events (though it already carries two similar events: "guidance raised", "beat and raise").
3. Just a missing synonym alias, or something deeper: appears to be a missing synonym for an *already-represented event category* (same family as "beat and raise"), not a wholly new concept.
4. Directional: **yes, but always positive** -- a "beat" cannot be negative by definition, so this phrase itself carries no reversal risk (unlike "guidance miss" below).
5. Needs polarity storage: no additional polarity mechanism needed *for this specific phrase*, because it is monodirectional.
6. Could match multiple factors simultaneously: no observed collision risk (verified in Part 4).
7. Needs a new factor: no -- fits inside the existing `Revenue Growth` event-alias pattern.
8. Blocked by structured-claim schema insufficiency: no.

### AMD claim:63 -- `fundamental_agent:fundamentals_report:claim:63`
- claim/evidence: "Any guidance miss could trigger significant multiple compression."
- Structured factors: `['Valuation Risk']` (from "multiple compression").
- matched_alpha: `A304` (Multiple Compression), factor_score `1.0`.
- Relation phrase: "could trigger". Candidate source: "guidance miss". Candidate target: "multiple compression" (already resolved to Valuation Risk). Unresolved side: **source**. Reason: no factor anywhere in the taxonomy represents a negative-guidance event.

1. Missing expression type: **event** (a discrete negative corporate-guidance outcome).
2. Existing canonical concept: **none** -- there is no "negative Revenue Growth" or "Earnings Disappointment" factor in the current 13.
3. Not just a missing synonym: this is a genuinely new *semantic category* (negative guidance event), not a rewording of something already covered.
4. Directional: **yes, and negative** -- the opposite of "guidance raised" (already a `Revenue Growth` alias).
5. Needs polarity storage: yes, if ever represented -- `factor_score`'s flat weight table has zero polarity mechanism today, so aliasing this under `Revenue Growth` (a de-facto positive-only factor in current usage) would misrepresent it.
6. Could match multiple factors: not observed, but if forced under `Revenue Growth` it would create a **semantic inversion**, not a literal collision.
7. Needs a new factor: **plausibly yes** -- this is a taxonomy question, not an alias question.
8. Blocked by schema insufficiency: no -- the claim text itself is explicit; the gap is purely in taxonomy coverage.

### AMD claim:57 -- `news_agent:news_report:claim:57`
- claim/evidence: "However, the near-term technical and sentiment picture is more cautious: the stock slipped on good news, the broader tech sector faces its worst capex-driven selloff since early 2026, and a \"higher-for-longer\" rate regime (85% probability of zero cuts) applies persistent multiple compression pressure."
- Structured factors: `['Valuation Risk']`.
- matched_alpha: `A304`, factor_score `1.0`.
- Relation phrase: "applies ... pressure". Candidate source: "higher-for-longer rate regime" / "85% probability of zero cuts". Candidate target: "multiple compression" (resolved). Unresolved side: **source**. Reason: `Rate Cut Cycle`'s aliases (`rate cut`, `falling rates`, `lower rates`, `fed cut`, `easing cycle`, `discount rates fall`, `discount rates are easing`, `treasury yields fall`, `treasury yields are falling`) cover *only* the falling-rate/easing direction.

1. Missing expression type: **state** (a persistent monetary-policy stance), not a one-off event.
2. Existing canonical concept: **`Rate Cut Cycle` exists but is semantically the opposite direction** -- not an accurate concept for this claim as-is.
3. Not a missing synonym -- it is the **mirror-image direction** of an existing factor, which is a different kind of gap.
4. Directional: **yes, and it is the reverse of every existing alias in the only related factor.**
5. Needs polarity storage: yes, unavoidably, if ever represented.
6. Could match multiple factors: no literal collision (verified empirically -- see Part 4), but a *conceptual* collision with `Rate Cut Cycle` if handled carelessly.
7. Needs a new factor: **plausibly yes** (a "Restrictive Rate Regime" / inverse concept), a taxonomy decision.
8. Blocked by schema insufficiency: no.

### AMD claim:34 -- `research_manager:investment_plan:claim:34`
- claim/evidence: "Sub-$490 (only if earnings disappoint): reassess fundamentals; if AMD confirms demand is intact and the selloff is multiple compression rather than revenue revision, this becomes a high-conviction accumulation zone toward a full position."
- Structured factors: `['Valuation Risk']`.
- matched_alpha: `A304`, factor_score `1.0`.
- Relation phrase: conditional "if ... then". Candidate source phrases: "demand" (bare, not "AI demand"), "revenue revision" (bare, no up/down qualifier). Candidate target: "multiple compression" (resolved). Unresolved side: **source** (both candidate source phrases).

1. Missing expression type: bare "demand" is a **fragment of a state** too generic to safely resolve (could be AI Demand, GPU Demand, or something else depending on context the sentence doesn't supply); "revenue revision" is an **event with no stated direction**.
2. Existing canonical concept: `AI Demand` is a plausible but *unproven* mapping for bare "demand" here (the sentence never says "AI demand"); no concept matches undirected "revenue revision".
3. Not a simple missing-synonym case for either phrase.
4. Directional: "revenue revision" explicitly requires distinguishing **upward / downward / undirected** revision, per the Sprint brief; the source text supplies no direction at all.
5. Needs polarity storage: yes, for "revenue revision" specifically.
6. Could match multiple factors: bare "demand" is exactly the kind of overreaching generic term that risks matching multiple demand-side factors if ever aliased without qualification.
7. Needs a new factor: unclear -- more likely a claim-schema/context problem than a taxonomy gap.
8. Blocked by structured-claim schema insufficiency: **yes, partially** -- the claim's own text underspecifies both the direction of "revenue revision" and the referent of bare "demand"; no alias fix can safely resolve an ambiguity the source text itself does not resolve.

### MU claim:36 -- `research_manager:investment_plan:claim:36`
- claim/evidence: "Any reiteration or increase of 2026 AI infrastructure spending is a direct HBM demand confirmation."
- Structured factors: `['AI CapEx', 'Datacenter CapEx', 'AI Infrastructure']` -- **all three from one overlapping phrase span**, see Part 4 collision finding; this is a pre-existing collision, not something this claim introduces.
- matched_alpha: `A103` (AI Infrastructure), factor_score `1.0`.
- Relation phrase: "is a direct ... confirmation" (a supportive-type relation, not covered by `ACTIVE_SUPPORT_PATTERN`'s verb list either, but that pattern change is out of this Sprint's scope). Candidate source: "AI infrastructure spending" (resolved, 3-way). Candidate target: "HBM demand". Unresolved side: **target**. Reason: no alias anywhere covers "HBM demand".

1. Missing expression type: **factor/state** (an ongoing demand trend for a specific memory product), the same *kind* of thing the taxonomy already models (comparable to "GPU Demand").
2. Existing canonical concept: **ambiguous among three candidates** -- `Semiconductor Cycle` already has "memory demand"/"storage demand" as generic memory-cycle aliases; `GPU Demand`/`AI Demand` are also plausible since HBM ships specifically as part of AI-accelerator memory stacks. No single canonical factor is an obviously "accurate" fit without a judgment call.
3. Not simply a missing synonym -- **which existing factor family it belongs to is itself the open question.**
4. Directional: no strong polarity issue in the *phrase* itself ("HBM demand" rising/falling is expressed elsewhere via predicates, not baked into the noun phrase).
5. Needs polarity storage: no.
6. Could match multiple factors simultaneously: **yes, materially** -- see Part 3 simulation: aliasing it to `Semiconductor Cycle` flips this exact claim from `no_match` to a brand-new formal `A201` match. Aliasing it to `GPU Demand` or `AI Demand` instead would very plausibly produce a *different* formal match (those factors carry different `FACTOR_ALPHA_WEIGHTS` rows -- `GPU Demand: {A101:0.85, A301:0.75, A201:0.35}` vs `Semiconductor Cycle: {A201:1.0, A301:0.25}`).
7. Needs a new factor: not obviously -- more likely a *placement* decision among existing factors than a taxonomy gap.
8. Blocked by schema insufficiency: no.

## 4. Canonical mapping decisions

| Phrase | Candidate canonical factor | Nearby existing aliases | Semantically equivalent? | Direction consistent? | Possible mis-match | Extractor use | Mapper impact | Classification | Recommendation |
|---|---|---|---|---|---|---|---|---|---|
| revenue beats | `Revenue Growth` | "guidance raised", "beat and raise" | Close, not identical (event vs. the compound "beat and raise" event) | Yes -- monodirectional positive | Low: no observed string/semantic collision | Would let `claim:58`'s source AND target both resolve, enabling edge extraction if a recognized relation verb existed | `factor_score` for A301 rises materially (0.45->1.0 in the one audited claim); `matched_alpha` did not flip in this instance but easily could in others | `SAFE_ALIAS_EXTENSION` | `ADD_AS_ALIAS` *(lowest-risk of the eight; still requires the dedicated Implementation Sprint's regression pass, not a rubber stamp)* |
| guidance miss | none precise; closest is `Revenue Growth` (wrong direction) or `Valuation Risk` (only as a downstream trigger, not the event itself) | "guidance raised" (opposite direction) | No -- opposite polarity of the nearest existing alias | No -- inverse of "guidance raised" | High if placed under `Revenue Growth`: would silently feed positive A301 credit off negative news | Would resolve `claim:63`'s source, enabling an edge to `Valuation Risk` | Would inject wrong-direction factor credit into A301's `factor_score` for any claim mentioning it, wherever it occurs historically or in future runs | `EVENT_NOT_FACTOR` / `DIRECTIONAL_ALIAS_REQUIRES_POLARITY` | `DO_NOT_ADD` as a plain alias; `REQUIRES_TAXONOMY_DECISION` if a distinct negative-guidance concept is wanted |
| revenue revision | none precise; closest is `Revenue Growth` | "eps revisions" (itself already directionless in the table -- a pre-existing ambiguity, not created by this review) | No -- source text gives no up/down direction | Unknown -- claim never states it | Medium: inherits the same latent ambiguity "eps revisions" already has | Would resolve one candidate source in `claim:34` (still leaves bare "demand" unresolved) | Same-shape risk as "guidance miss" if it is ever a downward revision in some other claim | `AMBIGUOUS_ALIAS` | `DEFER_FOR_MORE_EVIDENCE` / `REQUIRES_TAXONOMY_DECISION` (and flag the pre-existing "eps revisions" ambiguity for a separate maintainer decision) |
| HBM demand | ambiguous among `Semiconductor Cycle`, `GPU Demand`, `AI Demand` | "memory demand"/"storage demand" (Semiconductor Cycle); none for GPU/AI Demand specifically | Partially -- HBM is a real subset of "memory demand" but is also AI-accelerator-specific | N/A (not directional) | High: three plausible homes with materially different `FACTOR_ALPHA_WEIGHTS` rows | Would resolve `claim:36`'s target, and (per the pre-existing 3-way collision already on this claim) would add a 4th simultaneous factor to an already-overlapping span | Demonstrated empirically (Part 5): aliasing to `Semiconductor Cycle` flips this exact claim from `no_match` to a new formal `A201` match | `AMBIGUOUS_ALIAS` | `REQUIRES_TAXONOMY_DECISION` (which home is correct must be decided before any alias is added; `DO_NOT_ADD` until then) |
| higher-for-longer rate regime | `Rate Cut Cycle` (only rate-related factor), but wrong direction | all 9 `Rate Cut Cycle` aliases are falling/easing-direction | No -- opposite of every existing alias in the only candidate factor | No | High if placed under `Rate Cut Cycle`: would inject a "rates are cutting" signal from a claim asserting the opposite | Would resolve `claim:57`'s source | Would inject wrong-direction credit into A001 (`{A001:1.0, A003:0.2}`) for any claim using this phrase | `DIRECTIONAL_ALIAS_REQUIRES_POLARITY` | `DO_NOT_ADD`; `REQUIRES_TAXONOMY_DECISION` for an inverse concept |
| no rate cuts | `Rate Cut Cycle` (superficially, by string containment) | "rate cut" is a literal substring | No -- explicit negation of the alias it contains | No -- this is exactly the "contains 'rate cuts' != falling rates" trap the Sprint brief warns about | **Confirmed substring overlap with the existing "rate cut" alias** (see Part 5, `COLLISION_CONFIRMED`) | Would resolve nothing new today (verified empirically: `extract_known_factors_from_text("no rate cuts")` currently returns `[]`, because `term_in_text`'s boundary regex does not tolerate the plural "cuts" against the singular alias "rate cut" -- an accidental non-match, not a designed safeguard) | If ever added naively (e.g. as "no rate cut", singular) it would collide directly with the existing positive-direction alias | `DIRECTIONAL_ALIAS_REQUIRES_POLARITY` | `DO_NOT_ADD` |
| zero cuts | `Rate Cut Cycle` (by association only) | none literal | No | No -- same negation problem as above, phrased differently | Currently resolves to `[]` (verified) | Same risk profile as "no rate cuts" if ever added | `DIRECTIONAL_ALIAS_REQUIRES_POLARITY` | `DO_NOT_ADD` |
| restrictive rate regime | `Rate Cut Cycle` (by association only) | none literal | No | No | Currently resolves to `[]` (verified) | Same risk profile | `DIRECTIONAL_ALIAS_REQUIRES_POLARITY` | `DO_NOT_ADD`; `REQUIRES_TAXONOMY_DECISION` if an inverse concept is wanted |

No canonical factor was invented for this table; every "candidate canonical factor" cell names only a factor that already exists in the live `FACTOR_ALIASES` table read in Section 2.

## 5. Shared-alias impact simulation (in-memory only, `FACTOR_ALIASES` never written)

Two representative candidates were simulated end-to-end through the real
`map_claim_to_alpha()` against the real audited claim, by temporarily appending one
alias string to one canonical factor's tuple in the running process and restoring it
immediately afterward (verified restored: `True`).

| Phrase | Proposed canonical factor | Affected claim | Extractor impact | Mapper factor_score impact | Candidate ranking impact | Formal match impact | Secondary Alpha impact | Graph node impact | Relation endpoint impact | Overall risk |
|---|---|---|---|---|---|---|---|---|---|---|
| revenue beats | Revenue Growth | AMD claim:58 | `record.factors` gains `Revenue Growth`; target span now resolvable, so the claim would have >=2 factors for the first time (source AND target both known) | A301: `0.45 -> 1.0`; A101 unaffected (still `1.0`, hard-gate-blocked either way) | A301 candidate score `0.4023 -> 0.5673` (+41%); A101 remains top-by-score but stays ineligible | `matched_alpha` unchanged (`A301` before and after) in this specific claim | `secondary_alphas` unchanged (`[]` before and after, in this claim) | Would add a new `Revenue Growth` factor node association where this claim already touches `AI Demand` | Enables a candidate source/target pair, though no covered relation verb currently connects them (see the prior Structure Extractor Relation Coverage Sprint) | `LOW_RISK_SCORE_ONLY` for this specific claim, but **`MATERIAL_MAPPER_CHANGE` in general** -- any other historical/future claim containing "revenue beats" without a stronger competing candidate could flip `matched_alpha` the way the next row demonstrates for a different phrase |
| HBM demand | Semiconductor Cycle | MU claim:36 | `record.factors` gains `Semiconductor Cycle` (4th factor on an already 3-way-overlapping span) | New: A201 factor_score `0.0 -> 1.0` | A201 candidate score `(absent) -> 0.5`, now the top eligible candidate (A103/A101 stay ineligible, hard-gate-blocked; A301 stays at 0.305, below `min_score`) | **`matched_alpha`: `None` -> `A201`** -- a claim with `match_status="no_match"` today would become a formal match | `secondary_alphas` unchanged (`[]`) | Would create/strengthen a `Semiconductor Cycle` node association for this claim, on top of the pre-existing 3-way overlap already present | No new edge (still <2 factors with a genuine source/target relationship, per the prior Extractor Sprint's finding on this exact claim) | **`MATERIAL_MAPPER_CHANGE`** -- a `no_match` claim becomes a formal `A201` match purely from the alias addition |

Confirmed for both simulations: **A101/A102/A103 hard-gate eligibility never changed** (`ai_gate_passed`/eligibility for the AI alphas was identical before and after in every candidate row) -- the hard gate from the AI Alpha Mapper Discrimination Sprint continues to be an independent admission control, unaffected by `FACTOR_ALPHA_WEIGHTS`-driven score changes. **Non-AI alphas (A301, A201, A304, A601, ...) are directly and materially affected** by any `factor_score` change, since their eligibility is `bool(matched_keywords) or factor > 0` with no independent gate -- confirming the answer to "修改 FACTOR_ALIASES 后会不会改变 Mapper 或其他历史行为": **yes, materially, for non-AI alphas, up to and including flipping `no_match` claims into formal matches**, for any historical or future run whose claims happen to contain the aliased phrase.

The remaining six phrases were not simulated end-to-end because Section 4 already classifies all of them `DO_NOT_ADD` / `REQUIRES_TAXONOMY_DECISION` -- simulating a change that should not be made would not add decision-relevant evidence, only illustrate the same already-documented risk category.

## 6. Alias collision check (Part 4 of the brief)

**`COLLISION_CONFIRMED`** -- a real, pre-existing (not proposed) three-way overlap in
the current production table: the alias `"infrastructure spending"` (`AI CapEx`) and
the alias `"ai infrastructure"` (`AI Infrastructure`) are both literal substrings of
the alias `"ai infrastructure spending"` (`Datacenter CapEx`). Affected canonical
factors: **`AI CapEx`, `AI Infrastructure`, `Datacenter CapEx`**. This is exactly the
mechanism observed live in AMD `claim:17`/`claim:53` and MU `claim:29`/`claim:36`,
where one phrase span produces 3 simultaneous factor matches. This finding pre-dates
this Sprint (it was already visible in the earlier Structure Extractor Relation
Coverage Sprint's evidence table) and is **not caused by, and not fixed by, anything
proposed here** -- flagged for completeness since Part 4 explicitly asked for it.

No other exact-normalized-text or substring collision exists elsewhere in the current
13-factor table (systematically checked: every alias's normalized text was compared
pairwise against every other alias's normalized text across different canonical
factors; the only hits were the three strings above).

Of the eight audited phrases, the only one with a **confirmed substring overlap
against an existing alias** is `no rate cuts` (contains the literal alias `"rate
cut"`). As documented in Section 4, the current regex (`term_in_text`'s
`(?<![a-z0-9])term(?![a-z0-9])` boundary check) happens not to match plural "cuts"
against the singular alias "rate cut" today, so this is not yet live in production --
but it is a documented, direction-reversed landmine for whoever implements this alias
next (a plausible near-variant like "no rate cut" would collide immediately). No
literal collision was found for the other six.

Verified specifically for the terms named in the brief: `revenue`, `demand`, and
`rate cuts` are **not themselves literal aliases anywhere** in the current table
(good -- the table already avoids bare single/generic words as full-phrase aliases).
`ai demand`, `memory demand`, `storage demand`, `revenue growth`, `guidance raised`,
`beat and raise`, `falling rates`, `lower rates` each resolve to exactly one canonical
factor with no cross-factor ambiguity.

## 7. Unknown fallback risk (Part 5 of the brief)

Verdict: **`CURRENT_FALLBACK_NOT_REACHED`** for the two audited runs specifically,
**with a documented, real (not hypothetical) latent path** for other configurations.

1. Can an unknown factor enter structured records? Only via the `llm_strict_json`
   adapter path (`structured_output_adapter.py:765-790`), which is gated by the same
   `COMQUTOR_WEEK2_LLM_ENABLED` environment flag confirmed off-by-default and
   confirmed **not set** for both AMD (`66794ad5-...`) and MU (`0ba23540-...`) --
   both runs' `extracted_structures.json.metadata.llm_enabled` is `false`. The
   `deterministic_splitter` path used by both runs structurally cannot introduce an
   unknown factor, because `structured_output_adapter.py:889-895` filters every
   proposed factor string against `verified_factors = extract_known_factors_from_text(evidence)`
   before it ever reaches `record["factors"]`.
2. Would it create a new graph node? Yes, if reached -- `structure_extractor.py`'s
   `_extract_factors()` has no `FACTOR_ALPHA_WEIGHTS`-style filter (unlike
   `alpha_mapper.py`'s `_record_factors()`, which does filter and is therefore safe
   against this specific risk). Any non-empty title-cased fallback value becomes a
   real `node_type: "factor"` node via `_make_node()`.
3. Could it become a relation endpoint? Yes, if reached -- `factor_mention_span()`
   always includes the factor's own literal name as a search term even when
   `FACTOR_ALIASES` has no entry for it, so a fallback-labeled "factor" that happens
   to co-occur with a genuine factor and a recognized relation verb in the same claim
   could produce a real edge under a fabricated pseudo-canonical label.
4. Spelling/plural/punctuation fragmentation: punctuation and case are already
   collapsed by `normalize_text()` before the fallback runs (so "Q3 revenue-miss!"
   and "q3 REVENUE MISS" would title-case identically), but **plural/singular
   variants are not normalized** ("revenue miss" vs. "revenue misses" would produce
   two distinct node ids/labels for what a human would treat as one concept) --
   confirmed by reading `normalize_text()`, not assumed.
5. Could a user mistake it for a real canonical factor? Yes -- the fallback produces
   a plausible-looking Title Case label indistinguishable in the UI from a genuine
   taxonomy factor; nothing in the node schema marks it as unrecognized.
6. Does it affect Mapper `factor_score`? **No** -- confirmed by code: `_record_factors()`
   in `alpha_mapper.py` filters to `factor in FACTOR_ALPHA_WEIGHTS`, so any fallback
   value is silently dropped before `factor_score()` ever runs.

## 8. Factor node <-> Alpha association (Part 6 of the brief)

Verified via `graph_builder.py:68-72` and `:284-296`: a node's `alpha_ids` is the
union of `matched_alpha` over exactly that node's own `claim_ids`, restricted to
`match_status == "matched"` -- it is a **per-run, per-claim realized association**,
never a lookup into the static `FACTOR_ALPHA_WEIGHTS` taxonomy table (which
`graph_builder.py` never imports or reads). "Datacenter CapEx has alpha_ids `[A103]`"
means "in this run, at least one claim feeding this node was formally matched to
A103" -- it does not mean "Datacenter CapEx is taxonomically defined as belonging to
A103 alone" (the taxonomy table in fact also credits it to A101 at weight 0.35).

| Node id | Canonical factor | Claim_ids (count) | alpha_ids | ambiguous_alpha_ids | Alias source | Misleading-display risk |
|---|---|---|---|---|---|---|
| `ai_demand` (AMD) | AI Demand | 8 | `['A301', 'A601']` | `[]` | 2 of 8 claims matched (A601 via `claim:19`, A301 via `claim:58`); 6 no_match | If displayed as "AI Demand -> A301/A601" without context, a reader could mistake this for the taxonomy's primary mapping (which is actually A101 at weight 1.0) rather than what it is: which alphas this run's admitted evidence happened to land on |
| `valuation_risk` (AMD) | Valuation Risk | 4 | `['A304']` | `[]` | all 4 claims (including `claim:63`, `claim:57`, `claim:34`) matched A304 | Low risk -- consistent with the taxonomy's sole weight entry (`Valuation Risk: {A304:1.0}`) |
| `ai_capex` / `ai_infrastructure` / `datacenter_capex` (MU) | AI CapEx / AI Infrastructure / Datacenter CapEx | 12 / 14 / 3 | `['A101','A103']` / `['A103']` / `['A103']` | `[]` / `[]` / `[]` | **From the pre-Sprint-5 `alpha_matches.json`** (see caveat below) | High -- these three nodes share `claim:36` (the 3-way overlapping-alias collision from Section 6), so any UI presenting "this factor supports these alphas" without per-claim provenance would understate how much of that support traces back to one overlapping phrase span rather than three independent pieces of evidence |

**Caveat carried over from the prior AMD Live Artifact Root-Cause Audit**: MU's
persisted `alpha_matches.json` (and therefore `structure_graph.json`, built from it)
predates the AI Alpha Mapper Discrimination Sprint's hard-gate code -- it has no
`ai_alpha_matches` field and no `ai_gate_passed` key anywhere. The MU `alpha_ids`
shown above reflect the **old, pre-hard-gate Mapper**, not current behavior. This
does not change any conclusion in this report (none of it depends on MU's exact
historical alpha_ids), but it must not be read as current-code evidence.

## 9. Recommended next step

**`SPLIT_INTO_MULTIPLE_IMPLEMENTATION_SPRINTS`**

The eight audited phrases do not share one risk profile, so one alias-implementation
Sprint covering all of them would either be too conservative (blocking the one
low-risk phrase) or too permissive (waving through five phrases this audit
specifically found unsafe as plain aliases). Concretely:

- `revenue beats` is the only phrase classified `SAFE_ALIAS_EXTENSION` /
  `ADD_AS_ALIAS`, and even it needs a dedicated Implementation Sprint with a full
  historical-run regression pass (Section 5 shows a 41% factor_score swing on one
  real claim), not a one-line diff.
- `guidance miss`, `higher-for-longer rate regime`, `no rate cuts`, `zero cuts`,
  `restrictive rate regime` are all `DIRECTIONAL_ALIAS_REQUIRES_POLARITY` /
  `EVENT_NOT_FACTOR` and should not proceed to an alias-implementation Sprint at all
  until a taxonomy owner decides whether inverse/negative-event concepts belong in
  the MVP-10 factor set -- that is a `TAXONOMY_DECISION_REQUIRED` question, not an
  Extractor/Mapper implementation question.
- `HBM demand` is `AMBIGUOUS_ALIAS` and specifically needs a placement decision among
  three real candidates before any code change, since Section 5 demonstrates the
  choice materially changes which Alpha gets credited.
- `revenue revision` is `AMBIGUOUS_ALIAS` for a different reason (missing direction
  in the source claim itself) and should be deferred pending either more evidence or
  a structured-claim-schema change to capture revision direction at extraction time.

## Scope verification

- `factor_normalizer.py` modified: **No**
- `alpha_mapper.py` modified: **No**
- `structure_extractor.py` modified: **No**
- `graph_builder.py` modified: **No**
- `activation_scorer.py` / `activation_scorer_v2.py` modified: **No**
- `conflict_detector.py` modified: **No**
- Taxonomy modified: **No**
- Frontend modified: **No**
- Historical AMD/MU artifacts modified: **No**
- New canonical factor added: **No**
- Alpha weights modified: **No**
- Hard gate modified: **No**
- Relation pattern modified: **No**
- `CAUSAL_RANK` modified: **No**
- TradingAgents rerun: **No**
- Provider/network/database calls: **Zero**
- Files actually changed by this Sprint: this document only (`docs/factor_resolution_contract_and_alias_impact_review.md`, new).

No audit script was added -- every statistic in this report was independently
reproduced via ad hoc, throwaway Python invoked directly against the real modules
(never written to the repository), and each one is small enough that a human can
re-run the exact one-liner quoted next to the finding to verify it. Per the brief's
"只有在人工检查无法可靠复现统计时才新增脚本" instruction, that threshold was not met.
