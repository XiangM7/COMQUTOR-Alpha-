"""COMQUTOR Data Sanity Cross-Check v1.

An independent, deterministic sidecar stage that cross-checks a research
run's ticker/analysis_date against yfinance market data and, when available,
the run's own structured claims. It only ever produces additive warning
artifacts (``market_data_snapshot.json``, ``data_sanity.json``) -- it never
mutates agent claims, ``final_state``, Alpha Mapping, Activation scores, the
Structure Graph, or Conflict results, and a failure here never changes
Research completion status.
"""
