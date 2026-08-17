# LLM Semantic Call Contract v1

Status: `APPROVED_PROJECT_DECISION` for an offline foundation; `NOT_INTEGRATED`; `NO_PRODUCTION_AUTHORITY`.

Schema identifiers:

- semantic call: `comqutor.semantic_call.v1`
- validated cache entry: `comqutor.llm_cache_entry.v1`
- cache-key material: `comqutor.llm_cache_key.v1`
- manifest: `comqutor.semantic_manifest.v1`

This contract defines the future persistence boundary for COMQUTOR semantic LLM calls. Phase 0.6A supplies only offline primitives. No current pipeline imports this package and no current semantic authority changes.

## Canonical JSON and hashing

Canonical JSON is UTF-8 JSON with object keys sorted, no insignificant whitespace, Unicode emitted directly, and no platform newline added. Its accepted domain is objects with string keys, arrays, strings, booleans, integers, finite floating-point values, and null. It rejects tuples, sets, bytes, non-string keys, cycles, custom objects, `NaN`, and positive or negative infinity. It never uses `repr`, pickle, custom encoders, time, randomness, or environment values.

Hashes are lowercase hexadecimal SHA-256:

- `sha256_bytes`: SHA-256 of the supplied bytes.
- `sha256_text`: SHA-256 of the UTF-8 encoding of the exact text.
- `sha256_canonical_json`: SHA-256 of canonical JSON bytes.

Object key order does not affect canonical bytes; array order and string case do. JSON numbers preserve the Python serializer's explicit representation: integer `1` serializes as `1`, while finite float `1.0` serializes as `1.0`, so their hashes differ. No cross-language producer may claim compatibility without matching these bytes exactly.

## SemanticCallRecord v1

Every JSONL line contains exactly these fields:

| Field | Type | Rule |
|---|---|---|
| `schema_version` | string | Exactly `comqutor.semantic_call.v1`. |
| `call_id` | non-empty string | Supplied by caller; unique within an artifact. V1 does not require a globally deterministic hash. |
| `run_id` | non-empty string | Must match recorder and manifest run identity. |
| `call_sequence` | non-negative integer | Strictly increases for each run. |
| `task` | enum | `structured_adapter`, `alpha_classifier`, or `structure_extractor`. |
| `execution_mode` | enum | `live`, `shadow`, `replay_fixture`, or `test`. |
| `prompt_version` | non-empty string | Version identifier of the prompt contract. |
| `prompt_sha256` | SHA-256 | Hash of the exact prompt text or prompt bytes as declared by its producer. |
| `input_schema_version` | non-empty string | Version of `input_payload`. |
| `output_schema_version` | non-empty string | Version of `validated_output`. |
| `provider` | non-empty string | Provider identity; metadata only. |
| `model` | non-empty string | Model identity; metadata only. |
| `taxonomy_version` | string or null | Required when a task's meaning depends on a taxonomy. |
| `input_payload` | object | Secret-free semantic request payload. |
| `input_sha256` | SHA-256 | Hash of canonical `input_payload`. |
| `raw_output_text` | string or null | Exact Provider response text when one exists. Never cache eligible. |
| `raw_output_sha256` | SHA-256 or null | Hash of exact UTF-8 raw output; null iff raw output is null. |
| `validated_output` | canonical JSON value or null | Accepted structured semantic result or an explicit fallback result. |
| `validated_output_sha256` | SHA-256 or null | Canonical JSON hash; null iff validated output is null. |
| `started_at`, `completed_at` | ISO-8601 strings | Timezone-aware; completion cannot precede start. |
| `latency_ms` | non-negative number | Observed elapsed time. |
| `token_usage` | object | Exact keys `input_tokens`, `output_tokens`, `total_tokens`; each null or non-negative integer. When all exist, total equals input plus output. |
| `cache` | object | Exact keys `cache_key` and `hit`; key matches `comqutor:llm:v1:<sha256>`. |
| `retry_count` | non-negative integer | Number of retries performed. |
| `validation_status` | enum | `accepted`, `rejected`, or `not_run`. |
| `provider_status` | enum | `success`, `timeout`, `provider_error`, `budget_exhausted`, or `not_called`. |
| `fallback_used` | boolean | Whether a saved result was produced by fallback. |
| `fallback_reason` | string or null | Required only when fallback is used. |
| `error_code` | string or null | Stable uppercase reason code; required for timeout, Provider error, or exhausted budget. |
| `error_message` | string or null | Diagnostic text after redaction. |

Unknown or missing fields fail v1 validation. Validation returns a `ValidationResult` with one or more stable reason codes; it never returns an unexplained boolean.

## Cross-field invariants

- `accepted` requires a non-null validated output and matching hash.
- `rejected` and `not_run` cannot carry a validated output.
- `success + accepted` requires validated output.
- A Provider failure can be `accepted` only when an explicit fallback was used.
- `timeout`, `provider_error`, and `budget_exhausted` require an error code.
- A successful Provider call cannot carry error fields.
- `not_called` cannot carry raw Provider text or token usage.
- A cache hit is exactly `not_called + accepted`, uses no retry and no fallback, and still revalidates the stored output hash.
- `fallback_used=true` requires a non-empty reason; `false` requires a null reason.
- Input, raw output, and validated output hashes are recomputed during validation.
- Across a record set, `call_id` is unique and sequence is strictly monotonic per run.

Confidence values, if a versioned task output schema later defines them, must be validated by that output schema and cannot be negative. V1 does not invent a shared confidence field.

## Redaction and forbidden content

Semantic records and cache entries must not contain API keys, authorization headers, passwords, access/refresh tokens, secrets, private keys, or complete local home paths. Credential-like assignments, bearer values, common secret token forms, and `/Users/<name>/...`, `/home/<name>/...`, or Windows user paths must be redacted before validation. The helper replaces sensitive material with explicit redaction markers. Validation fails closed when sensitive field names or unredacted values remain.

Error codes contain only uppercase letters, digits, and underscore and therefore cannot be used as raw error-message storage. Raw Provider errors and unvalidated raw text are never cacheable.

## Cache key and cache eligibility

The key is `comqutor:llm:v1:<sha256>`, where SHA-256 covers canonical JSON containing the key-contract version, semantic-call schema version, task, prompt version/hash, Provider, model, input/output schema versions, input hash, and taxonomy version. Raw prompt and raw input are never exposed in the key. `run_id` is deliberately excluded so an otherwise identical, fully versioned request can hit across runs.

Only a validated record with `provider_status=success`, `validation_status=accepted`, no fallback, no prior cache hit, and non-null validated output may create `comqutor.llm_cache_entry.v1`. Rejected output, Provider error, fallback output, cache-hit output, raw text, and raw Provider errors cannot be inserted. `source_run_id` may be stored as provenance but never contributes to the key.

`RedisLLMResponseCache` accepts an injected Redis-like client and never constructs one. Import and construction perform no I/O. Entries are canonical JSON, optionally written with a positive TTL. Reads revalidate schema, lookup key, and output hash. Malformed, non-UTF-8, wrong-key, or hash-mismatched content raises an explicit `CacheCorruptionError`; v1 does not silently convert corruption into an ordinary miss or delete it. `NullLLMResponseCache` always misses and all mutations are no-ops.

## Persistence and manifest

`llm_semantic_calls.jsonl` is append-only UTF-8 JSONL with one canonical `SemanticCallRecord` per newline-terminated line. A recorder validates before writing, enforces run/mode identity, unique call IDs, and monotonic caller-provided sequence values. One recorder instance serializes threads with a lock. V1 does not coordinate multiple processes; callers must not share one JSONL file across processes. A partial final line, empty middle line, invalid UTF-8/JSON, invalid record, or skipped sequence invariant fails closed. Destructors are not part of durability; callers explicitly close the recorder. Optional `fsync` is available.

`llm_semantic_manifest.json` is derived from the calls file and written with a temporary file in the same directory followed by atomic replacement. It contains the calls-file hash, record/task/status/fallback/cache/Provider counts, sorted prompt/model sets, completion timestamps, and derived replay readiness. `provider_call_count` counts `success`, `timeout`, and `provider_error`; `budget_exhausted` and `not_called` are zero-call states. No minimum real-run call count is imposed by this artifact contract.

`exact_replay_ready` is never caller-set. In v1 it is true only when the manifest is complete and finalized and every saved call is accepted with a present, hash-valid structured output. `complete=false` always implies `exact_replay_ready=false`.

The Phase 0.6A implementation refuses writes below repository `outputs/runs` and `outputs/replays`; tests and verification use temporary directories only. It performs no network, Provider, Redis construction, database, or production-pipeline operation.

## Corruption, versioning, and compatibility

Readers fail closed on unknown schema versions, unknown fields, missing fields, invalid enum combinations, malformed JSON/JSONL, duplicate identity, non-monotonic order, and all hash/count mismatches. Stable reason codes are part of the diagnostic contract; prose messages are not.

Schema identifiers are immutable. A breaking field, meaning, canonicalization, or invariant change requires a new schema/key version and an explicit migration or reader. V1 readers do not guess, coerce, or reinterpret future versions. Older artifacts remain readable only by an implementation that explicitly supports their exact version. There is no implicit backward-compatibility transform in Phase 0.6A.

Future Exact Semantic Replay consumes accepted saved results only after calls and manifest verify. The replay contract is specified separately; Phase 0.6A does not integrate or implement replay.

## Non-goals

This contract does not define Claim Schema, Alpha classification correctness, Structure Edge correctness, Evidence Stance, or ticker specificity. It does not change Activation or Conflict behavior. It does not validate semantic quality, supply John's 20 labels, or replace Development Plan §5.1, §5.2, or §5.3 acceptance work. It does not change current prompts, taxonomies, retry/timeout defaults, Provider budgets, live/replay execution, or any production authority.
