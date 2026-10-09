# Interim execution `dependency-20261007T213234Z-3be0399d` (superseded, kept, never deleted)

Created earlier in Round 21 by the same production entry and the same offline script. It was superseded by
`dependency-20261007T220450Z-33128621` because three things changed AFTER it was created, none of which changes a score:

1. the trace read-model no longer labels a source `verified_basis` when the verification technically failed (it is
   `primary_link` / `cited` then; only a verification that actually ran names the source it used);
2. `negative $134M`-style sign words are grounded to the saved negative cell, and numbers a claim states that no saved
   cell holds are listed (`numbers_not_found_in_saved_data`);
3. the exported `evidence_trace.json` gained a run-wide `calculations` summary.

A canonical comparison of the two executions (ignoring hash ids and group order) shows identical Alpha results in every
activation view (primary, v1, v2, v2_verified) and identical dominant/active/candidate/blocked sets; the dry-run
comparison before/after the sign-word change is identical too (`dependency_dry_run_result_before_sign_word_fix.json`).
The files here are the evidence of that earlier session, unchanged.
