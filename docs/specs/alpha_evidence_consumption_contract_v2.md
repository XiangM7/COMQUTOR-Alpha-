# Alpha evidence consumption contract v2 (`alpha_evidence_consumption.v2`)

**Source classification** (see `README.md` in this folder): `PROPOSED_EXTENSION`. It has **no production authority** until explicitly approved; the project owner's limited approval below covers implementation and isolated verification only. It is neither `SOURCE_FROZEN`, nor a `JOHN_LATER_REQUIREMENT`, nor an `APPROVED_PROJECT_DECISION` for production use.

**Status.** Implementation contract for an **opt-in** per-run mode, written in round 36 (2026-10-10/11). The product rules it carries were approved by the project owner **for this round's v2 implementation and isolated verification only** (decisions A1, A2, A5, A7, A8, A10, A11, A12 of the 2026-10-10 decision table). This is **not** John's sign-off and **does not switch any production default**: a run whose `metadata.json` does not name the contract behaves, byte for byte, as before. The product-decision register (`product_decisions_and_unknowns.md`, PD-006 and PD-007 are still `NOT_APPROVED` there) and the semantic authority matrix are **not** edited by this document; updating them is for the owner and John.

**2026-10-13 additions.** The owner's instruction to fix the consumption defects John named in T3 (cases 005, 006, 019, 027R, 028, 037, 038, 040) added §4b–§4d and the explanation fields listed in §8. They apply only under this contract (a legacy run is unchanged byte for byte), change no formula, weight or threshold, and are **not** John's sign-off. The choices they make that need the owner's or John's decision are listed in `docs/audit_artifacts/round_source_linking_t0_t2/round36_t1_migration_20261010/t3_named_defects_20261013/00_本轮说明.md`.

## 1. Purpose

Source support, company attribution, Alpha relevance strength and stance used to be consumed by different entry points with different rules. This contract lets every entry read **one** decision per (claim, matched Alpha) pair, computed in **one** place (`comqutor_alpha/graph_engine/evidence_consumption.py`, with the name rule in `company_attribution.py`), recorded next to the raw baseline it was derived from.

It is **additive**: it never rewrites the model's Alpha selection, the model's stance, the text rule's relation / assertion / polarity, or the lexical score. Removing the blocks restores the original payload.

## 2. Switch, application point, rollback

| | |
|---|---|
| Switch | run `metadata.json` key `alpha_evidence_consumption` = `"alpha_evidence_consumption.v2"`. Absent (or `null`) = legacy. |
| Application point | `routes_research._run_week3_graph_pipeline` (the single function behind a new run, a content-support re-evaluation and a derived execution), **before** scoring and **before** any in-memory annotation. |
| Recompute | every pass recomputes the blocks from the **current** records, source registry and semantic ledger and replaces any earlier block (idempotent; a re-evaluation can never reuse a stale block). |
| Persistence | blocks live inside `alpha_matches.json` → `matches[].candidate_scores[<matched alpha>].consumption`, and therefore in the existing `alpha_matches.candidate_scores` JSON column (JSONB on PostgreSQL). No schema migration. A run-level summary is stored in `structure_graph.json` → `evidence_consumption`. Payload marker: `evidence_consumption_contract`. |
| Rollback | remove the metadata key and run the Week 3 pass again: the blocks and the marker are stripped and the original `alpha_matches.json` bytes are restored. |
| Not authorisation | the switch is a **consumption** switch. It performs no model, search or fetch call and is not an authorisation for one. |
| Operator entry | `scripts/consumption_contract.py` recomputes a **saved** run's inputs as a derived execution under an explicitly chosen contract (`derive --contract v2\|legacy`, no default) and rolls it back (`rollback`); see §4a. It is a recomputation of saved inputs, never a Fresh Run. |

## 3. The block (one per committed match; an attribution-only block on unmatched records)

```json
"consumption": {
  "contract": "alpha_evidence_consumption.v2",
  "ticker": "NVDA", "claim_id": "…", "alpha_id": "A301",
  "policies": {"stance": "alpha_stance_policy.v1", "attribution": "company_attribution.name.v1", "relevance": "alpha_relevance_fallback.v1"},
  "binding": {"input_sha256": "…", "source_state_sha256": "…",
              "ledger": {"available": true, "integrity": "MATCHES_MANIFEST", "sha256": "…", "owner_run_id": "…", "binding": "OWN_RUN", "usable": true}},
  "text_rule": {"relation": "activation", "assertion_status": "asserted", "semantic_polarity": "activation"},
  "stance": {"state": "MODEL_JUDGED", "label": "opposes_alpha", "method": "llm", "version": "evidence_stance.llm.v1", "counter_alpha_id": null,
             "unjudged_category": null, "unjudged_reason": null, "ledger": "VERIFIED"},
  "positive_admission": {"admitted": false, "reason_code": "STANCE_MODEL_NOT_SUPPORTING", "label": "opposes_alpha", "policy": "alpha_stance_policy.v1"},
  "attribution": {"policy": "company_attribution.name.v1", "category": "NO_TARGET_NAME", "ticker_specific": false, "subject_determined": false,
                  "basis": [], "other_issuers_named": [], "limits": [], "text_sha256": "…"},
  "relevance": {"policy": "alpha_relevance_fallback.v1", "state": "UNJUDGED", "model_level": null, "model_weight": null,
                "lexical_baseline": 0.1873, "effective_weight": 0.1873, "weight_authority": "LEXICAL_RULE_FALLBACK", "note": "…"},
  "source_support": {"link_status": "VALID", "content_support_status": "SUPPORTS", "verified_eligible": true, "eligibility_reason": null}
}
```

(`source_support` is a **mirror** of the existing eligibility decision `compute_verified_support_eligibility`, kept for binding and display; the source gate itself is unchanged and still runs where it always ran.)

2026-10-13: `policies` also names `statement_scope` (`alpha_statement_scope.v2`, §4b) and `direction` (`alpha_direction_stance_policy.v1`, §4c); the block carries a `statement_scope` decision; `binding.input_sha256` also covers the pair's matched terms. A block written before these additions therefore reads as `EVIDENCE_CONSUMPTION_BINDING_STALE` and is recomputed by the next Week 3 pass.

## 4. Stance and the positive pool (R-1, `alpha_stance_policy.v1`)

* `positive_admission` is an **explicit field**. It is **not** expressed by rewriting `relation` to `mention`: that would also remove the claim from the reverse-evidence channel. (2026-10-13: DirectionConsistency now reads it in one way only, see §4c.)
* A claim is excluded from the matched Alpha's **positive pool** iff its stance is **`MODEL_JUDGED`** and the label is one of `opposes_alpha`, `neutral_background`, `mentions_alpha`, `supports_counter_alpha`. Shared reason code: `STANCE_MODEL_NOT_SUPPORTING`.
* It only **subtracts**. It never admits a claim, never makes a model "supports" bypass the source gate or the text-rule gates, and applies to **that** Alpha only (`matched_alpha`); another Alpha's pool for the same claim is unaffected.
* **`MODEL_JUDGED`** requires a valid model result bound to this claim and this Alpha, not merely `method == "llm"` plus a legal label: the candidate's provenance fields must be self-consistent (classifier version, no fallback reason, no manual-review flag, no deterministic residue, a legal counter-Alpha for `supports_counter_alpha`, all candidate copies agreeing) **and** the run's own semantic ledger (`llm_semantic_calls.jsonl`, hash-checked against `llm_semantic_manifest.json`) — or, for a derived execution, the saved source run's ledger bound by a declared hash (§4a) — must hold an accepted, validated output for the same `(claim_id, target_alpha_id)` with the same label.
* **Unjudged** (adds **no** exclusion; the other gates still apply) is disclosed by category: `MISSING`, `TIMEOUT`, `PARSE_FAILED`, `FALLBACK`, `UNVERIFIED`, each with a precise reason (e.g. `no_stance_result`, `missing_result`, `ledger_unavailable`, `pair_not_in_ledger`, `ledger_label_mismatch`). Unjudged is never reported as opposition.
* Scope boundary (A7): the same judgement function `positive_admission_exclusion(match, alpha_id)` is read by every positive-support entry (the shared selector `evidence_fact_index.select_supporting_alpha_claims`, used by Activation and the Evidence Fact Index). It is **not** applied to the conflict side's admission, to B2 admissibility, to role rules or to the reverse-evidence channel.

## 4a. Stance ledger of a derived execution (`stance_ledger_binding`)

A derived execution (a recomputation of a saved run's inputs) does **not** copy the source run's `llm_semantic_calls.jsonl`: that file describes the source run's own model calls. Its stances can only be corroborated against the ledger of the run that produced them, through an explicit, hash-pinned declaration in the execution's `metadata.json`:

```json
"stance_ledger_binding": {"source_run_id": "<saved run id>", "calls_file_sha256": "<sha256 of that run's llm_semantic_calls.jsonl>"}
```

Resolution (`evidence_consumption.resolve_stance_ledger`), on every pass and every read:

* the run's **own** ledger, when it has one, always wins (`binding = OWN_RUN`);
* otherwise, without a declaration: no ledger (every stance `UNJUDGED: ledger_unavailable`);
* otherwise the declaration must be well-formed (else `BINDING_INVALID`), name a run in the execution's lineage — `based_on_run_id` or `root_research_run_id` (else `BINDING_NOT_IN_LINEAGE`) — whose directory is a sibling under the same output root and holds the ledger (else `BOUND_LEDGER_MISSING`), and the file's sha256 must equal the declared value (else `BINDING_SHA_MISMATCH`). Each of these makes the ledger **unusable**: nothing is excluded and the reason is shown; there is never a silent fallback;
* a usable declared ledger is used with `binding = SOURCE_RUN_DECLARED`; `binding.ledger` in every block and in the run summary records `owner_run_id` and `binding`, so the executing run, the saved source run and the ledger owner are reported separately.

The operator entry `scripts/consumption_contract.py derive` creates such an execution (`execution_type = alpha_evidence_consumption_recompute`, id `consumption-<UTC>-<hex8>`, lineage file `consumption_lineage.json`: `fresh_run: false`, zero model / search / fetch calls) and declares the binding when the source run has a ledger; `rollback` removes the contract key, reruns the Week 3 pass and writes `consumption_rollback.json` (listed in the artifact manifest, so the Export carries it). The entry accepts only an explicitly named `*_test` database and refuses the repository's `outputs/` tree.

## 4b. Negation scope (`alpha_statement_scope.v2`, 2026-10-13)

The text rule (`claim_semantics.analyze_claim_semantics`) marks a whole claim `negated` when a negator appears anywhere in it, and `alpha_relation` then reads it as a `mention`, so the selector excluded it (`RELATION_NOT_SUPPORTING` / `ASSERTION_NEGATED`) even when the negator did not negate the Alpha's statement (T3 005, 006, 027R). Per pair, `statement_scope` removes only the parts of the claim that cannot negate the Alpha's statement and re-reads the rest with the **unchanged** text rule:

| Removed part | When |
|---|---|
| a citation marker (`[fragmentid: …]`, `Source Marker: …`) | always: provenance, never statement content |
| a negated protection of a risk ("net cash does not immunize … from compression") | always, risk Alphas A304 / A501 only: the construction affirms the risk |
| the rejected alternative of a contrast ("X, not Y", "not Y but X", "It's not — it's X") | only with the **anchor** |
| a negation in another clause than the one carrying this Alpha's own matched terms (no back-reference) | only with the **anchor** |

**Anchor.** The words alone cannot tell which side of a contrast carries the Alpha's statement ("… repricing, not a growth scare" negates the recession Alpha's own statement; "… a trailing inflection, not a forward EPS of $15.72" does not negate the valuation Alpha's). A contrast or clause removal is therefore applied only when the pair's stance is `MODEL_JUDGED` with label `supports_alpha` (ledger-corroborated, §4). Without it the would-be removal is recorded under `not_applied` and the text rule's negated reading stands. The anchor only ever **withholds** a re-read; the label is never mapped to a relation or assertion (the kept text is read by the text rule, so conditional and mixed statements keep their weights), and a `supports_alpha` label without a removal pattern changes nothing. A negator that remains, or this Alpha's matched terms appearing only in the removed part (`ALPHA_TERMS_ONLY_IN_REMOVED_PART`), keeps the claim negated. `v1` (the same day, never delivered) applied the contrast and clause removals without the anchor; on a run without a ledger it read two negated statements as support (AMD news claim 18 for A501, research-manager claim 10 for A301).

The stored `text_rule` fields are never rewritten. The selector's relation and assertion gates and the Activation v2 weights read `statement_scope.effective` (`evidence_consumption.effective_text_rule`); R-1, the claim-quality gate, the source gate and every other gate still apply afterwards. The decision is recomputed and compared on every read (`EVIDENCE_CONSUMPTION_DECISION_INCONSISTENT` if it differs). Run-level summary: `structure_graph.json` → `evidence_consumption.statement_scope`.

## 4c. Direction (`alpha_direction_stance_policy.v1`, 2026-10-13)

DirectionConsistency used every committed match's text-rule relation, so a claim R-1 keeps out of the positive pool (a model-judged, ledger-corroborated opposition, background or mention) still counted as **positive** direction evidence through the old relation label (T3 037 / 038 / 040). Under the contract the direction groups read the same effective relation as the positive pool (§4b), and a positively signed claim that R-1 excludes is **not counted**. Subtract only: negative and neutral signs are unchanged, and an opposing stance is **not** turned into negative evidence (that would be a new product rule).

## 4d. Canonical relation scope in the graph (`canonical_edge_scope.v1`, 2026-10-13)

A TradingAgents canonical relation is validated on the agent's own `assertion_status`, so "A no-cut regime means discount rates stay elevated, which … compresses …" became the edge Rate Cut Cycle -causal-> Valuation Risk — a cut the statement says is not happening. Under the contract the Week 3 pass re-reads each accepted relation's own quote before building the graph and **withholds** the relation's candidate edge when the quote negates an endpoint factor ("no-cut", "no rate cuts", "will not cut": `EVIDENCE_NEGATES_SOURCE_FACTOR` / `…_TARGET_FACTOR`) or carries the text rule's conditional markers (`EVIDENCE_CONDITIONAL`; the canonical contract admits only asserted relations as edges). Subtract only: no edge is added or re-typed, a node is dropped only when every record it came from is withheld, and the saved Week 2 `extracted_structures.json` is never rewritten. Every decision is reported in `structure_graph.json` → `evidence_consumption.canonical_edge_scope` with its quote. The graph has no "negated factor" node, so withholding is the minimal change that stops the graph asserting the opposite of its evidence.

## 5. Company name (`company_attribution.name.v1`)

`ticker_specific` means exactly **"the target company's name is present in the claim text"**. It does **not** mean the claim is about the company: `subject_determined` is always `false` and a positive result carries the limit `NAME_PRESENCE_NOT_SUBJECT`. Example of the documented limitation: "nvidia-backed Firmus is set to postpone its IPO" is name-present for NVDA although its subject is another company.

Matching conditions: the ticker symbol (whole token, case-insensitive); an approved issuer name (`issuer_aliases.issuer_names_for_ticker`: "Advanced Micro Devices", "Advanced Micro Devices, Inc.", "NVIDIA", "NVIDIA Corporation"); a product alias (`Ryzen`, `Epyc`, `Instinct`) **only** with explicit, case-sensitive product context. A bare or lower-case "instinct" never counts. The run's ticker, the structured `entities` list, the search query, the source provider and a linked source's instrument are **never** evidence of attribution. `TARGET_BY_SOURCE_OBJECT` is **disabled** (decision A6): it would move independent facts 1→2 on the official A301 and needs its own decision; attribution is not fact independence.

Categories: `TARGET_NAME_SYMBOL`, `TARGET_NAME_ISSUER`, `PRODUCT_ALIAS_WITH_CONTEXT` (target name present), `OTHER_COMPANY_NAMED_ONLY`, `NO_TARGET_NAME` (not present).

Every entry that asks "is this claim ticker-specific" (Activation, the conflict side, the evidence display, unclassified findings, the stance-audit export) reads the same field through `attribution_decision_for_record`, which validates contract version, target ticker and the text binding on every read. A record without a block takes the legacy path unchanged.

## 6. Relevance (disclosure only in this version)

No relevance judgment exists in v2. The lexical score is consumed unchanged and is labelled `weight_authority = LEXICAL_RULE_FALLBACK`; `model_weight` and `model_level` are `null` (never `0`). A lexical score that is truly `0` stays `0` and is labelled. Tier definitions and numeric weights are **not approved** (A9 open) and nothing here wires them. No relevance task is registered and no extra request is made.

## 7. Binding and explicit failure

`binding.input_sha256` covers the record-level inputs the decisions were derived from (claim text, text-rule fields, lexical score, stance fields, policy versions); `binding.source_state_sha256` covers the source-support mirror; `binding.ledger` records the ledger integrity. A reader validates the block on every read:

| Situation | Result |
|---|---|
| contract value not exactly `alpha_evidence_consumption.v2` (any other string, a list, a number, `true`) | `EVIDENCE_CONSUMPTION_ILLEGAL_CONTRACT_VERSION` |
| block ticker ≠ target ticker / record ticker | `EVIDENCE_CONSUMPTION_TICKER_MISMATCH` |
| block belongs to another claim or Alpha, or a stray block sits on a re-matched record | `EVIDENCE_CONSUMPTION_PAIR_MISMATCH` |
| record inputs changed since the block was written | `EVIDENCE_CONSUMPTION_BINDING_STALE` |
| stored decision contradicts the stored inputs it implies (admission vs stance, name decision vs text) or a part has the wrong shape | `EVIDENCE_CONSUMPTION_DECISION_INCONSISTENT` |

The Week 3 pipeline logs the failure under the stage `evidence_consumption:<reason>` (`week3_pipeline_status.json`: `outcome = failed`), writes **no** `structure_graph.json` and persists nothing; it never falls back silently and then reports success. The read-only trace reports each block as `CURRENT`, `STALE` (valid, but a fresh recomputation from today's inputs differs), `MISSING` or `INVALID:<reason>`.

## 8. Entries that read the contract

Activation (through the shared selector and `_is_ticker_specific`), the conflict side's qualifying members (pass-through of the compact block; no gating change), the evidence display, unclassified findings, Evidence Trace (`consumption` view, key `STANCE_MODEL_NOT_SUPPORTING` in the not-scored reasons; `consumption.execution_basis` names the executing run, the saved run it recomputes and whose ledger corroborated the stances) and the stance-audit export (`effect_mode = positive_pool_exclusion` only for v2; the legacy export fields are unchanged). The key-conclusions view carries the same run-level `execution_basis` (with the "not a Fresh Run" label) for a run under the contract or produced by the operator entry; every other run's view is unchanged.

2026-10-13 explanation fields (contract runs only unless stated): the trace's `consumption.statement_scope` (with an explanation, the removed parts and the `not_applied` parts); the trace's `stance` block reads the same effective relation and assertion as the gates and names its `relation_basis`; the v2 / v2_verified `evidence_detail` entries record the relation and assertion the v2 scorers weighted, with the text rule's own reading beside them (`text_rule_relation`, `text_rule_assertion_status`, `reading_policy`) when the scope changed them (v1 keeps the stored fields); the stance-audit export adds `statement_scope` per matched pair. For every run, `alpha_classification_completion` reports `gate_overridden_selection_count` (a model selection the mapper's gate vetoed, by gate) instead of counting it as a valid NONE (T3 019 / 027R / 028).

## 9. Not changed

The Activation v2 and Conflict formulas, constants and thresholds; the Alpha classifier and its prompts; the stance classifier; B2 admissibility; role / source-role rules; the reverse-evidence channel; DirectionConsistency inputs other than §4c; the 0.35 minimum match score; the source verification gate. R-2 (a model "supports" overriding the text rule) is **not** implemented (A3). 2026-10-13: §4b uses a ledger-corroborated `supports_alpha` only as the anchor that lets a **contrast or clause removal** stand; it never maps the label to a relation or assertion and changes nothing without such a removal. Because it touches the area A3 deferred, it is listed for the owner's and John's decision.

## 10. Known limits

* Name presence is not subject attribution (see §5).
* A run without a stance ledger (e.g. the AMD derived execution used in the comparison) has every stance `UNJUDGED`; R-1 cannot evaluate there.
* Relevance quality, tier definitions and the PD-013 threshold scope are open decisions (see the round-36 A9 / PD-013 decision items).
* §4b covers four negation patterns. Other non-governing negations (a negation inside a relative clause, "not X, but Y" with a comma, an outcome predicate such as "failed to lift", "without a demand break", a rhetorical heading) still read as negated: the claim stays excluded (fail-safe). On a run without a ledger no contrast or clause removal can be anchored, so those negations stay as before.
* §4d withholds an edge; the graph cannot yet state "no rate cut" as a factor.

## 11. Tests

`tests/test_t1_migration_p3_consumption_contract.py` (contract and rules, synthetic), `tests/test_t1_migration_p3_pipeline_persistence.py` (production Week 3 pipeline over a copy of a saved run, trace, export, SQLite), `tests/test_t1_migration_p3_postgres_round_trip.py` (independent PostgreSQL database; skipped unless `COMQUTOR_T1_MIGRATION_TEST_DATABASE_URL` names it), `tests/test_t1_integration_consumption_recompute.py` (ledger binding, operator entry, identities, rollback and its Export), front-end `evidenceTraceConsumption.test.ts` / `EvidenceTraceConsumption.test.tsx` / `KeyConclusionsExecutionBasis.test.tsx`. 2026-10-13: `tests/test_t3_named_consumption_defects.py` (T3 cases verbatim, the anchor, the four defects end to end over a copy of the saved NVDA run, trace and stance-audit), front-end `AlphaCard.test.tsx` and `adapters.test.ts` (the text-rule reading of a re-read evidence entry).
