# Current vs Target Semantic Architecture

## Status

- Current diagram: `CURRENT_IMPLEMENTATION`
- Target diagram: `APPROVED_PROJECT_DECISION`, not yet implemented
- Production behavior changed by this document: No

## CURRENT

```mermaid
flowchart TD
    P1[(Live market/news providers)] --> TA[TradingAgents L1 data collection\nand L2 agent analysis]
    CPI[CURRENT active runtime\ncanonical prompt injection] -. modifies 12 effective prompts .-> TA
    TA -->|native LLM Provider calls| LLM1[(TradingAgents LLM Provider)]
    TA --> RAW[(Persisted raw_agent_outputs.json\nprose + optional canonical blocks)]
    RAW --> SEG[Deterministic claim segmentation\nCURRENT production authority]
    SEG -. optional; default off .-> W2[(Week2 LLM Provider\nclaim enrichment)]
    W2 --> V1[Deterministic schema/provenance\nand byte-identity validation]
    SEG --> V1
    V1 --> CLAIMS[(structured_agent_outputs.json)]
    CLAIMS --> T1[Deterministic Alpha Tier 1\neligibility/scoring]
    T1 -. optional select/defer; default off .-> W2A[(Week2 LLM Provider\nAlpha classifier)]
    T1 --> AF[Deterministic Tier 3 fallback]
    W2A --> AM[(alpha_matches.json)]
    AF --> AM
    CLAIMS --> RULE[Rule relation extraction\nCURRENT fallback/source]
    CLAIMS -. optional; default off .-> W2R[(Week2 LLM Provider\nrelation extraction)]
    RAW --> CB[Canonical-block parse\nCURRENT third source]
    RULE --> MERGE[Deterministic relation validation\nnormalization + merge]
    W2R --> MERGE
    CB --> MERGE
    MERGE --> REL[(extracted_structures.json)]
    AM --> CORE[Deterministic authorities:\nGraph admission → Activation → Exposure → Conflict]
    REL --> CORE
    CORE --> OUT[(Persisted run artifacts + API/UI)]
    RAW --> REPLAY[CURRENT replay:\nraw rebuild + llm_gateway=None]
    REPLAY --> RPOUT[(Replay artifacts\nProvider=0; DB writes=0)]

    ES[Evidence Stance\ndeterministic SHADOW_ONLY] -. diagnostic only .-> AM
```

Current boundary notes:

- Solid Provider edges are possible only during live execution. Week2 Provider edges are optional and gated by `COMQUTOR_WEEK2_LLM_ENABLED`, which defaults off.
- `comqutor_alpha/llm/canonical_prompt_injection.py` adds no call but actively changes TradingAgents prompt/output behavior.
- Graph admission, Activation, Exposure calculation, Conflict, identity, and serialization remain deterministic authorities.
- Current replay is Provider-zero but is only `RAW_REBUILD_DIAGNOSTIC`-like for LLM-influenced semantic decisions.

## TARGET

```mermaid
flowchart TD
    P1[(Live market/news providers)] --> TA[TradingAgents as-is:\nL1 collection + L2 analysis]
    TA -->|native live LLM Provider calls| LLM1[(TradingAgents LLM Provider)]
    TA --> CAP[Passive final_state/raw-output capture]
    CAP --> RAW[(Persisted immutable raw outputs)]
    RAW --> ADAPTER[COMQUTOR Structured Adapter\nprimary semantic proposer]
    ADAPTER -->|shadow/evaluated live calls only| LLM2[(COMQUTOR LLM Provider)]
    ADAPTER --> VAL1[Deterministic authority:\nschema + provenance + identity + source spans]
    VAL1 --> SCLAIMS[(Persisted validated claims\n+ prompt/schema/model/fallback metadata)]
    SCLAIMS --> MAP[Hybrid Alpha Mapper:\nTier 1 eligibility → Tier 2 select/defer → Tier 3 fallback]
    MAP --> VAL2[Deterministic candidate/taxonomy validator]
    VAL2 --> SAlpha[(Persisted validated Alpha decisions)]
    SCLAIMS --> EXTRACT[COMQUTOR Structure Extractor\nprimary relation semantic proposer]
    EXTRACT --> VAL3[Deterministic vocabulary/provenance/lineage validator]
    RULE[Rule extraction\nexplicit fallback/shadow] -.-> VAL3
    VAL3 --> SREL[(Persisted validated relation decisions)]
    SAlpha --> CORE[Deterministic authorities:\nGraph admission → Activation → Exposure → Conflict]
    SREL --> CORE
    CORE --> OUT[(Persisted deterministic artifacts + API/UI)]
    SCLAIMS --> EXACT[EXACT_SEMANTIC_REPLAY\nNOT YET IMPLEMENTED]
    SAlpha --> EXACT
    SREL --> EXACT
    RAW --> DIAG[RAW_REBUILD_DIAGNOSTIC\nexplicit named parser]
    EXACT --> RCORE[Deterministic recomputation\nProvider=0; DB writes=0]
    DIAG --> RCORE
    RCORE --> RPOUT[(Mode-labelled replay artifacts)]

    ES[Evidence Stance + ticker specificity\nAddendum A; NOT APPROVED] -. no production path .-> SCLAIMS
```

Target boundary notes:

- Canonical prompt injection is absent from target semantic authority, but its actual runtime disablement is deferred to a measured Phase 4 migration.
- Every LLM result is a proposal until deterministic validation accepts it.
- Rule semantics remain explicit fallback/shadow paths rather than silently co-equal primary authority.
- Validated semantic decisions and execution metadata are persisted before exact replay becomes available.
- `EXACT_SEMANTIC_REPLAY`, explicit `RAW_REBUILD_DIAGNOSTIC`, semantic-call persistence, and the Addendum A path are not yet implemented.
