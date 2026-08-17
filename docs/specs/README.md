# COMQUTOR Specification Sources

## Canonical Development Plan

`COMQUTOR_Alpha_Development_Plan_v1.0.docx` is the canonical repository copy of **COMQUTOR Alpha Development Plan v1.0**. Phase 0.5 copied it byte-for-byte from the product-provided local source; it was not converted, edited, unpacked/repacked, or regenerated.

The authoritative identity is the SHA-256 recorded in `development_plan_v1.0_manifest.json`. Future tasks must verify that hash before citing the document as `SOURCE_FROZEN`.

The v1.0 file is immutable:

- Never silently replace or edit it.
- Add a new version as a separately named file with its own manifest record.
- Preserve old versions for provenance and reconciliation.
- Treat `development_plan_v1.0_reference_index.md` as a navigation aid, never as a substitute for the DOCX.

## Source Classification and Precedence

Every requirement, ADR, audit conclusion, test, and future task must use one of these labels:

| Label | Meaning |
| --- | --- |
| `SOURCE_FROZEN` | Explicitly stated in the canonical Development Plan v1.0. |
| `JOHN_LATER_REQUIREMENT` | Product requirement introduced or changed by John after v1.0. |
| `APPROVED_PROJECT_DECISION` | Approved architecture decision where v1.0 is incomplete or permits alternatives. |
| `CURRENT_IMPLEMENTATION` | What the present code actually does; this is evidence, not specification authority. |
| `PROPOSED_EXTENSION` | Unapproved design, field, algorithm, or product extension. |
| `UNKNOWN` | Evidence is insufficient for a supported conclusion. |
| `BLOCKED_BY_PRODUCT_OWNER` | Product-owner input is required to proceed. |

The Development Plan remains the frozen baseline. A later requirement or approved ADR must retain its own provenance and does not retroactively become v1.0 text. An ADR may resolve a gap or select among choices left open by v1.0; it must not silently override an explicit frozen requirement. A genuine change to v1.0 requires a separately versioned plan or approved addendum, with the conflict and supersession stated explicitly.

`CURRENT_IMPLEMENTATION` never proves `SOURCE_FROZEN`. `PROPOSED_EXTENSION` has no production authority until explicitly approved.
