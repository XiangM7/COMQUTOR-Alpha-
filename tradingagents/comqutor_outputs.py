"""Compatibility shim for the COMQUTOR Week 1A output writer."""

from comqutor_alpha.adapters.tradingagents_output_writer import (
    AGENT_OUTPUT_FIELDS,
    OUTPUT_VERSION,
    save_comqutor_run_outputs,
)

__all__ = ["AGENT_OUTPUT_FIELDS", "OUTPUT_VERSION", "save_comqutor_run_outputs"]
