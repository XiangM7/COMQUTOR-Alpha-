"""Shared, cross-cutting audit modules (not tied to any single pipeline
stage). See ``comqutor_alpha.audit.ticker_consistency`` for the single,
shared Ticker Consistency Audit implementation -- API, Run Audit, Replay,
and the CLI all call the same function here, never a locally re-implemented
copy of the same check."""
