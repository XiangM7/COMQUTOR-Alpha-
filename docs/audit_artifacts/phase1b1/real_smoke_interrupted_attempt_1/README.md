# Interrupted attempt (voided, not a completed Smoke run)

output_dir attempted: outputs/evaluations/phase1b1-smoke-20260806T221741Z
started_at: 2026-08-06T22:17:41Z
research_profile: comqutor_deepseek_default_v1 (deepseek / deepseek-v4-flash)

Real DEEPSEEK_API_KEY was present (sourced from .env). 3 of 4 logical calls
(fundamental, news, sentiment) each ran the Gateway's own controlled retry
policy to completion: 2 attempts x DEFAULT_TIMEOUT_SECONDS=15.0, both
attempts timed out (error_code=WEEK2_LLM_TIMEOUT) -- no response returned by
the Provider within the Gateway's own timeout. The 4th call (technical) was
mid-retry (1 of 2 attempts logged) when the orchestrating shell's own
2-minute default command timeout sent SIGTERM to the whole process tree,
killing it before the CLI's own code path could reach any terminal status
(BLOCKED/FAIL) or its own except-block staging cleanup. No final output
directory was ever created (no atomic promotion occurred) -- only an
orphaned `.{name}.staging-<uuid>` directory, which has been removed after
this evidence was copied out.

This is voided due to external tooling error (Bash default timeout shorter
than the CLI's own worst-case runtime), not a CLI-determined result, and is
not counted as the one authorized official Smoke run. It is preserved here
only as an audit record of 3 genuine real-Provider timeout attempts.

raw_output_text for all captured calls: null (never populated, consistent
with contract).
