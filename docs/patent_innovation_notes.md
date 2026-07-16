# COMQUTOR Engineering Innovation Map

This document is an engineering implementation map, not legal advice or a patent
claim-construction opinion.

| Mechanism | Implemented mechanism | Code | Tests | Product relation | Status |
| --- | --- | --- | --- | --- | --- |
| Agent-output structuralization | Raw report fields become bounded public structured records; raw text is excluded from DB/API readout | `structured_output_adapter.py`, `agent_output_reader.py` | `test_structured_output_adapter.py`, `test_agent_outputs_api.py` | Creates a stable machine-readable research boundary | MVP implemented and verified |
| Structured claims | Stable claim/source IDs preserve claim, evidence, entities, factors, direction and confidence | `structured_output_adapter.py`, DB migration 0004 | `test_agent_outputs_persistence.py` | Makes agent assertions addressable and auditable | MVP implemented and verified |
| Merge by structure | Claims map into taxonomy Alpha IDs before graph aggregation; agents are evidence sources, not votes | `alpha_mapper.py`, `graph_builder.py` | `test_alpha_mapper.py`, `test_graph_builder.py` | Consolidates repeated reasoning around economic structure | MVP implemented and verified |
| Taxonomy admissibility | Only known Alpha IDs and declared conflict pairs enter formal graph/conflict outputs | `alpha_loader.py`, `conflict_detector.py` | `test_alpha_loader.py`, `test_conflict_detector.py` | Prevents arbitrary narrative labels becoming product facts | MVP implemented and verified |
| Deterministic activation | Versioned formula computes activation from committed evidence | `activation_scorer.py`, `graph_schema.py` | `test_activation_scorer.py`, persistence tests | Produces repeatable structure ranking | MVP implemented and verified |
| Conflict arbitration | Admitted pairs receive deterministic scores, main-conflict selection and stable reason codes | `conflict_detector.py` | NVDA/QQQ conflict sanity tests | Converts opposing structures into an explainable readout | MVP implemented and verified |
| Reason codes | Adapter, persistence, lifecycle and API failures use stable public codes | API routes, repositories, lifecycle modules | security, API and failure-path tests | Supports safe operations without exposing internals | MVP implemented and verified |
| Evidence traceability | Conflict sides link through Alpha matches to exact structured claim/source IDs | mapper, graph and conflict pipeline | `test_week4_golden_closure.py` | Lets a reviewer inspect why each side exists | MVP implemented and verified |
| Stable run identity | Canonical request fingerprint, explicit run ID and terminal reuse avoid accidental duplicate work | `research_lifecycle.py`, DB repository | research run and concurrency tests | Gives each analysis a durable audit identity | MVP implemented and verified |
| Idempotency | Run, structured output, graph, activation and conflict replacement is transactional and repeatable | DB repositories | SQLite/PostgreSQL persistence tests | Makes retries operationally safe | MVP implemented and verified |
| Readout boundary | APIs whitelist structured fields and use DB-first reads with legacy artifact fallback | API routes and readers | API/security tests | Separates internal generation from customer-visible evidence | MVP implemented and verified |

Deferred: authentication, tenant ownership, public multi-instance deployment, Alpha Memory,
cross-run feedback and portfolio execution. No legal validity, exclusivity, infringement or
patent-protection claim is made here.
