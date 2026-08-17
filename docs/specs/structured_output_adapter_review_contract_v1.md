# Structured Output Adapter Human Review Contract v1

Status: `APPROVED_PROJECT_DECISION` for a blank Phase 1A evaluation template. It is not a gold set, does not contain human labels, and creates no production authority.

## Review ownership

Automated Legacy/Shadow comparison fields are navigation signals only. A named human reviewer inspects the exact source report, spans, Legacy record, and Shadow proposal before selecting a label. No Codex/LLM output may be recorded as a human answer. Blank values mean `NOT_REVIEWED`, not acceptance.

## Dimensions and labels

| Dimension | Allowed labels |
| --- | --- |
| Claim boundary | `correct`, `over_merged`, `over_split`, `missing_claim`, `spurious_claim`, `uncertain` |
| Evidence pairing | `correct`, `partially_supported`, `wrong_evidence`, `missing_evidence`, `invented_evidence`, `uncertain` |
| Semantic fidelity | `correct`, `meaning_distorted`, `negation_error`, `modality_error`, `attribution_error`, `temporal_error`, `uncertain` |
| Entity extraction | `correct`, `partial`, `incorrect`, `not_applicable`, `uncertain` |
| Factor extraction | `correct`, `partial`, `incorrect`, `not_applicable`, `uncertain` |
| Direction | `correct`, `incorrect`, `unclear`, `not_applicable` |
| Overall disposition | `accept`, `accept_with_minor_edit`, `revise`, `reject`, `abstain` |

Severity is exactly `critical`, `major`, `minor`, or `none`. A review process must separately define adjudication and inter-reviewer disagreement before it can claim gold-set status.

## Blank CSV contract

The exact columns are:

```text
review_row_id,source_run_id,ticker,agent,agent_output_id,source_report_sha256,legacy_record_id,shadow_claim_id,review_dimension,review_label,severity,reviewer,review_timestamp,notes
```

The builder may prefill only navigation/identity columns through `shadow_claim_id`. It must leave `review_dimension`, `review_label`, `severity`, `reviewer`, `review_timestamp`, and `notes` blank. It must not infer labels from exact overlap, set deltas, or candidate lineage.

## Review procedure

1. Verify source run/Agent/report hash and inspect exact source spans.
2. Select one dimension and one allowed label; use additional rows for additional dimensions.
3. Assign severity based on downstream risk, not on whether Legacy and Shadow differ.
4. Record reviewer identity, timezone-aware review timestamp, and concise notes without credentials or hidden reasoning.
5. Send disagreements to independent adjudication. Do not overwrite an earlier review row.

Phase 1A produces the template only. Human labels created: `No`.
