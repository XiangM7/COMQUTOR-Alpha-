"""Week 4 deterministic Conflict Core (W4.1).

Consumes only Week 3's structured Structure Graph/activation output, Week 2's
alpha_matches records, and the frozen Alpha taxonomy -- never raw
TradingAgents text, never an LLM, never the filesystem or a database, never
the network. See ``conflict_detector.detect_alpha_conflicts`` for the public
entry point and ``docs/week4_spec_freeze_audit.md`` for the frozen spec this
module implements.
"""

from __future__ import annotations
