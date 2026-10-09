`formal_acceptance.json` here is what the PRODUCTION writer (`comqutor_alpha/api/formal_acceptance_artifact.py`) produces, with the final rules, from the saved payloads
(`structure_graph.json`, `conflicts.json`, `alpha_matches.json`) of the final offline AMD execution `dependency-20261007T220450Z-33128621`. It was computed offline into this
directory; nothing was written into that run (its own `formal_acceptance.json`, written by the older code, is untouched). It shows the new fields on a real run's payloads:
`coverage.pass_is_vacuous`, `failure_reasons` / `review_reasons`, `effective_rules.ticker_rules`, repository-relative rule file paths.
