# COMQUTOR Alpha data contracts

The canonical contracts are Pydantic v2 models in
`comqutor_alpha/structure_engine/structure_schema.py` and
`comqutor_alpha/alpha_library/alpha_schema.py`. All models reject unknown
fields and validate on assignment.

## Boundary flow

```text
RawAnalystReportBundle
  -> ClaimBatch (0..N Claim or typed AdapterFailure)
  -> AlphaMatch + StructureNode/StructureEdge
  -> ActivationBreakdown + ConflictResult
  -> ResearchResult
```

### Raw reports

A bundle accounts for exactly Market, Sentiment, News, and Fundamentals. An
agent may be explicitly missing; it may not silently disappear. Every report
has an immutable run UUID, ticker, analysis date, timezone-aware capture time,
and exact upstream source field.

### Claims and failures

A report may yield zero or many Claims. Claims require non-empty claim and
evidence text, bounded confidence, explicit direction/source enums, source
references, and extraction method. Adapter failures are separate typed
objects; the system never fabricates an `unknown` Claim to hide a failure.

### Taxonomy and matches

`alpha_taxonomy_v1.yaml` is the source of truth. Startup validation requires
exactly the MVP-10 IDs, the six mandatory conflict pairs, legal weights,
non-empty signals and keywords, valid targets, and the Development Plan's
mandatory structural relations. Conflict lookup is bidirectional even when a
pair is declared redundantly in YAML.

The current taxonomy is explicitly `pending_product_review`: identifiers,
names, layers and required relations come from the Development Plan; numeric
seed values not present in the three supplied documents were recovered from
the user's earlier committed taxonomy (`9b2b8a5`) and are not represented as
newly product-approved data.

Each AlphaMatch contains claim/evidence provenance, method, and component
scores. Abstention is represented by absence of a Match, never by forcing an
irrelevant Claim to an Alpha.

### Graph contracts

Nodes and edges require claim and evidence provenance. Edges reject invalid
weights, empty provenance, dangling endpoints at graph-build time, and
self-loops by default. The three allowed extracted edge types are `causal`,
`supportive`, and `conflicting`.

### Deterministic scores

Every activation component stores raw value, weight, and contribution. The
final score must equal the contributions. Conflict results store both sides'
evidence and must satisfy:

```text
score = minimum_activation * contradiction_weight * evidence_strength
```

### Research result

Results carry `complete`, `degraded`, or `failed` status. A complete result
cannot contain hidden errors/degradation reasons. Every dominant Alpha and
conflict contract requires evidence references. Upstream trading decisions
are not part of ResearchResult.

## Versioning and JSON

UUIDs, dates, datetimes and enums serialize through Pydantic JSON mode. Contract
tests require model → JSON → model equivalence. Additive or breaking contract
changes require a schema-version update and migration/compatibility notes.
