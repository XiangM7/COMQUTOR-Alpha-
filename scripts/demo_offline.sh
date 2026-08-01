#!/usr/bin/env bash
# Offline demo entry point (MVP Audit, Evaluation, Golden Fixtures, and
# Delivery Readiness Sprint, Track D).
#
# This is a thin, clearly-named wrapper around the existing, already
# fully-functional `scripts/run_w5_demo.sh` -- reused rather than
# duplicated (that script already: seeds approved deterministic offline
# fixtures, starts the API with COMQUTOR_REAL_TRADINGAGENTS_ENABLED=false
# and COMQUTOR_WEEK2_LLM_ENABLED=false, waits for /health + /ready, starts
# the Vite frontend, waits for it to serve /research, and prints the
# reachable URLs). Zero Provider calls throughout.
#
# See docs/demo_runbook.md for what to expect once this is running.

set -euo pipefail
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
exec "$SCRIPT_DIR/run_w5_demo.sh" "$@"
