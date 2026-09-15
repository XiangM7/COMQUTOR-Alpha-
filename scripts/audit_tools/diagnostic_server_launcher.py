"""Diagnostic-only launcher for the TradingAgents 903-second timeout
root-cause task (docs/audit_artifacts/v0_2_tradingagents_timeout_root_cause.json).

Configures INFO-level logging for the new observability-only diagnostic
loggers (comqutor_alpha.runners.tradingagents_runner,
comqutor_alpha.runners.diagnostics) before starting the normal comqutor-api
server via comqutor_alpha.api.server.main(). No production code is changed
by this script -- it only sets a log level so the diagnostic log lines
already added to those two modules become visible on stdout for this one
diagnostic run.
"""

import logging

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(levelname)s %(name)s: %(message)s",
)
logging.getLogger("comqutor_alpha.runners.tradingagents_runner").setLevel(logging.INFO)
logging.getLogger("comqutor_alpha.runners.diagnostics").setLevel(logging.INFO)

from comqutor_alpha.api.server import main  # noqa: E402

if __name__ == "__main__":
    main()
