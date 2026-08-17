"""A4 Regression Runner (task A4_REGRESSION_RUNNER + J2_PROVISIONAL_LABELS).

A repeatable, offline, auditable regression flow: saved TradingAgents
outputs -> the existing Architecture Replay offline-reprocess path
(``comqutor_alpha.replay.pipeline.run_structure_replay``) -> the current
COMQUTOR architecture -> actual Alpha/Graph/Conflict results -> compared
against J2's provisional expectations -> ``regression_report.json``.

Never re-runs TradingAgents, never calls an LLM/Provider. Never modifies
B1-B5/A3 semantics, thresholds, or taxonomy -- this package only reads
already-computed (or freshly-replayed, zero-Provider) results and reports
on them.
"""
