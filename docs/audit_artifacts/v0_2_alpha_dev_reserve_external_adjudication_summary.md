# v0.2 Alpha Development Reserve External Adjudication Summary

Adjudicator mode: `INDEPENDENT_EXTERNAL_LLM_ADJUDICATION`

System predictions seen: **NO**

Samples adjudicated: **15**

Accepted replacements: **12**

Flagged/excluded replacements: **3**

SHA256 (as recorded by the external adjudicator, provenance only — not re-derivable from this repository's re-serialized copy): `2b7852946d84aeae224a6418e8f6d0482ab172b3e76a1925d6176a4674d3fe69`

## Label distribution
- A301: 2
- A304: 1
- NONE: 12

## Confidence
- high: 10
- medium: 2
- low: 3

## Flags
- INSUFFICIENT_CONTEXT: 3

## Flagged sample IDs
- nh-reserve-001: INSUFFICIENT_CONTEXT — The pronoun 'It' and the specific 'indispensable' narrative being challenged are not identified in the provided text, so no canonical Alpha mechanism can be adjudicated without relying on ticker/context inference.
- nh-reserve-011: INSUFFICIENT_CONTEXT — The sentence is visibly truncated at 'hike vs.' and does not state a complete policy outcome or mechanism, so the sample cannot be adjudicated reliably.
- nh-reserve-015: INSUFFICIENT_CONTEXT — Although an EPS-estimate cut could affect valuation, the provided text is an incomplete list item ending in 'OR'; the full asserted mechanism and conclusion are missing, so the sample should be excluded rather than forced.
