/**
 * TypeScript types for the COMQUTOR Alpha API, derived directly from
 * reading the actual route/response-builder source (not from a design
 * doc):
 *
 *  - comqutor_alpha/api/routes_research.py (build_research_response,
 *    _public_run_record_fields, get_research_run_history,
 *    the POST /api/research route + enqueue_research_request/
 *    prepare_research_submission's response shapes)
 *  - comqutor_alpha/api/routes_system.py (health_response, readiness_response)
 *  - comqutor_alpha/api/agent_output_reader.py (get_agent_outputs_response,
 *    PUBLIC_STRUCTURED_OUTPUT_FIELDS)
 *  - comqutor_alpha/graph_engine/{graph_builder,activation_scorer,pipeline}.py
 *    (the persisted structure_graph.json shape: nodes/edges/activation/
 *    dominant_alphas)
 *  - comqutor_alpha/storage/db/week4_persistence.py + conflict_detector.py
 *    (the persisted alpha_conflicts shape: conflicts/main_conflict/
 *    arbitration)
 *
 * Fields whose presence/shape is not guaranteed purely by TypeScript (i.e.
 * anything that crossed an HTTP boundary) are validated at runtime by
 * api/adapters.ts before this frontend ever trusts them -- these types
 * describe the *validated* shape adapters produce, not raw fetch() output.
 */

export const RESEARCH_RUN_STATUSES = [
  "queued",
  "running",
  "completed",
  "partial",
  "failed",
] as const;
export type ResearchRunStatus = (typeof RESEARCH_RUN_STATUSES)[number];

export const REAL_MODE_ANALYSTS = ["market", "sentiment", "news", "fundamentals"] as const;
export type RealModeAnalyst = (typeof REAL_MODE_ANALYSTS)[number];

/** A safe error/status envelope shared by most endpoints: run_id/ticker may
 * be null, status is always the literal "failed" (every backend error
 * response builder -- _error_response/_graph_error_response/
 * _conflicts_error_response/etc. -- sets exactly this), error_code/message
 * describe the failure. Kept as a literal (not a wide `string`) so
 * `status === "ok"` discriminated-union narrowing against the matching
 * success response type actually works. */
export interface SafeErrorEnvelope {
  run_id: string | null;
  ticker: string | null;
  status: "failed";
  error_code?: string | null;
  message?: string | null;
}

// ---------------------------------------------------------------------------
// POST /api/research
// ---------------------------------------------------------------------------

/** Client-controlled request fields only -- exactly the ResearchRequest
 * Pydantic model's field set in routes_research.py. Never provider/model/
 * config/API key/allow_real_tradingagents_run/offline_raw_agent_outputs. */
export interface ResearchSubmissionRequest {
  ticker: string;
  analysis_date?: string;
  selected_analysts?: string[];
  force_refresh?: boolean;
  run_id?: string;
}

export type CacheDisposition =
  | "created"
  | "force_refreshed"
  | "reused_in_flight"
  | "reused_completed";

/** The union of every shape POST /api/research can return, whether HTTP 200,
 * 202, 4xx, or 5xx -- see _research_submission_http_status /
 * enqueue_research_request / prepare_research_submission /
 * _build_terminal_reuse_response in the backend. */
export interface ResearchSubmissionResult {
  run_id: string | null;
  ticker: string | null;
  /** Backend's own top-level "status" field: for a fresh/queued submission
   * this mirrors run_status ("queued"/"running"); for a reused_completed
   * response this is the canonical research status ("completed"/"partial"/
   * "failed"); for any error this is "failed". */
  status: string;
  run_status?: string | null;
  stage?: string | null;
  cache_disposition?: CacheDisposition | null;
  error_code?: string | null;
  message?: string | null;
  /** Only present on a reused_completed (HTTP 200) response -- the full
   * canonical research response, folded in alongside run_status/
   * cache_disposition. Re-uses CanonicalResearchResponse's fields. */
  artifacts?: CanonicalResearchResponse["artifacts"];
  agent_output_count?: number;
  structured_output_count?: number;
  structure_graph_status?: "ready" | "not_ready";
  dominant_alphas?: DominantAlpha[];
  main_conflict?: AlphaConflict | null;
  conflict_status?: "ready" | "not_ready";
  summary?: string | null;
}

// ---------------------------------------------------------------------------
// GET /api/research/{run_id}/status and GET /api/research (history)
// ---------------------------------------------------------------------------

export type EtaStatus = "estimating" | "available" | "complete" | "unavailable";

/** _public_run_record_fields()'s exact projection of a research_runs row,
 * plus the W7 additive progress/ETA telemetry from
 * _build_progress_and_eta_fields -- never request_fingerprint/
 * active_fingerprint/provider identity/pipeline identity/config hash/
 * offline payload content. Progress fields are null for runs predating the
 * progress table; the UI must render only what the backend reports and
 * never grow progress on its own. */
export interface ResearchRunRecord {
  run_id: string;
  ticker: string;
  analysis_date: string | null;
  selected_analysts: string[];
  status: ResearchRunStatus;
  stage: string | null;
  error_code: string | null;
  message: string;
  created_at: string | null;
  started_at: string | null;
  completed_at: string | null;
  updated_at: string | null;
  profile_id: string | null;
  profile_display_name: string | null;
  progress_percent: number | null;
  current_stage: string | null;
  completed_units: number | null;
  total_units: number | null;
  progress_message: string | null;
  elapsed_seconds: number | null;
  eta_status: EtaStatus | null;
  estimated_remaining_seconds_min: number | null;
  estimated_remaining_seconds_max: number | null;
  eta_sample_count: number | null;
}

export interface RunStatusFailure {
  run_id: string;
  status: "failed";
  error_code: string;
  message: string;
}

export type RunStatusResult = ResearchRunRecord | RunStatusFailure;

export interface RunHistoryResponse {
  status: "ok";
  items: ResearchRunRecord[];
  next_cursor: string | null;
}

export type RunHistoryResult = RunHistoryResponse | SafeErrorEnvelope;

// ---------------------------------------------------------------------------
// GET /api/research/{run_id} -- canonical research response
// (build_research_response in routes_research.py)
// ---------------------------------------------------------------------------

export interface ResearchArtifacts {
  metadata: boolean;
  raw_agent_outputs: boolean;
  structured_agent_outputs: boolean;
  final_report: boolean;
  alpha_matches: boolean;
  extracted_structures: boolean;
  structured_output_error_logs: boolean;
  week2_llm_error_logs: boolean;
  week2_pipeline_error_logs: boolean;
}

export interface DominantAlpha {
  alpha_id: string;
  alpha_name: string;
  activation_score: number;
  status: string;
  direction: string;
  evidence_summary: {
    evidence_count: number;
    distinct_supporting_agents: number;
  };
}

// ---------------------------------------------------------------------------
// Data Sanity Cross-Check v1 (comqutor_alpha/data_sanity) -- an independent
// market-data cross-validation warning, never a change to claims/Activation/
// Graph/Conflict. "not_available" is reserved for historical runs that
// predate this feature and never had a data_sanity.json written.
// ---------------------------------------------------------------------------

export const DATA_SANITY_STATUSES = [
  "ok",
  "warning",
  "critical",
  "unavailable",
  "disabled",
  "not_available",
] as const;
export type DataSanityStatus = (typeof DATA_SANITY_STATUSES)[number];

export const DATA_SANITY_SEVERITIES = ["info", "warning", "critical"] as const;
export type DataSanitySeverity = (typeof DATA_SANITY_SEVERITIES)[number];

/** Only the safe fields the backend ever forwards publicly -- never a
 * provider exception, stack trace, full market_data_snapshot, or local file
 * path. ``details`` holds only non-sensitive numbers/dates/claim_ids. */
export interface DataSanityWarning {
  code: string;
  severity: DataSanitySeverity;
  message: string;
  details: Record<string, unknown>;
}

export interface CanonicalResearchResponse {
  run_id: string;
  ticker: string | null;
  status: "completed" | "partial" | "failed";
  artifacts: ResearchArtifacts;
  agent_output_count: number;
  structured_output_count: number;
  structure_graph_status: "ready" | "not_ready";
  dominant_alphas: DominantAlpha[];
  main_conflict: AlphaConflict | null;
  conflict_status: "ready" | "not_ready";
  summary: string;
  data_sanity_status: DataSanityStatus;
  data_sanity_warning_count: number;
  data_sanity_critical_count: number;
  data_sanity_warnings: DataSanityWarning[];
}

export type CanonicalResearchResult = CanonicalResearchResponse | SafeErrorEnvelope;

// ---------------------------------------------------------------------------
// GET /api/research/{run_id}/graph
// ---------------------------------------------------------------------------

export const GRAPH_EDGE_TYPES = ["causal", "supportive", "conflicting"] as const;
export type GraphEdgeType = (typeof GRAPH_EDGE_TYPES)[number];

export const ACTIVATION_STATUSES = [
  "inactive",
  "watch",
  "active",
  "dominant",
  "regime_level",
] as const;
export type ActivationStatus = (typeof ACTIVATION_STATUSES)[number];

/** A Week 3 Structure Graph "factor" node -- see graph_builder._serialize_node. */
export interface StructureGraphNode {
  id: string;
  node_type: string;
  label: string;
  canonical_factor: string;
  original_labels: string[];
  alpha_ids: string[];
  ambiguous_alpha_ids: string[];
  score: number;
  claim_ids: string[];
  source_agent_output_ids: string[];
  agents: string[];
  evidence: string[];
}

/** See graph_builder._serialize_edge. */
export interface StructureGraphEdge {
  source: string;
  target: string;
  edge_type: GraphEdgeType;
  weight: number;
  assertion_status: string;
  alpha_ids: string[];
  claim_ids: string[];
  source_agent_output_ids: string[];
  agents: string[];
  evidence: string[];
  extraction_methods: string[];
  rule_names: string[];
}

/** Per-claim evidence provenance for one scored alpha -- additive
 * `evidence_detail` entries built by the Week 3 pipeline from the run's own
 * alpha_matches records. */
export interface AlphaEvidenceDetail {
  claim_id: string;
  claim: string;
  agent: string;
  source_agent_output_id: string;
  match_score: number;
  relation: string;
  matched_keywords: string[];
  matched_factors: string[];
  assertion_status: string;
  direction: string;
}

/** One of the 10 MVP-10 alphas' full scored result -- see
 * activation_scorer.score_alpha. */
export interface AlphaActivation {
  alpha_id: string;
  alpha_name: string;
  activation_score: number;
  status: ActivationStatus;
  direction: string;
  components: Record<string, unknown>;
  evidence_count: number;
  distinct_supporting_agents: number;
  claim_ids: string[];
  evidence: string[];
  reason_codes: string[];
  evidence_detail: AlphaEvidenceDetail[];
  /** Activation v2 additive fields. Absent (null) on v1-legacy payloads --
   * the UI must then present the alpha as "Activation v1 legacy", never
   * pretend it was scored under v2. */
  formula_version: string | null;
  uncapped_score: number | null;
  /** The minimum value among every score cap whose condition is met (the
   * "qualification ceiling"). Null when no cap applies. This is NOT the
   * same claim as "the score was reduced" -- see cap_was_binding. */
  eligible_cap: number | null;
  /** True only when eligible_cap is non-null AND uncapped_score exceeds it
   * (the cap actually reduced activation_score). The frontend must read
   * this field directly and never re-derive it from eligible_cap/
   * uncapped_score/status itself. */
  cap_was_binding: boolean | null;
  /** Reason codes for every cap whose condition is met, regardless of
   * whether it binds. */
  cap_reason_codes: string[];
  /** Reason codes for only the cap(s) whose value equals eligible_cap,
   * populated only when cap_was_binding is true; otherwise empty. */
  binding_cap_reason_codes: string[];
  unique_evidence_count: number | null;
  ticker_specific_evidence_count: number | null;
  local_edge_count: number | null;
  /** Backend's own regime-gate verdict -- the frontend must read this
   * directly (and regime_gate_failures) rather than re-deriving pass/fail
   * from activation_score/status itself. */
  regime_gate_passed: boolean | null;
  regime_gate_failures: string[];
}

export interface GraphActivation {
  formula_version: string;
  weights: Record<string, number>;
  run_timestamp: string | null;
  as_of: string | null;
  alphas: AlphaActivation[];
}

export interface StructureGraphResponse {
  run_id: string;
  ticker: string | null;
  status: "ok";
  schema_version: string;
  graph_builder_version: string;
  activation_scorer_version: string;
  nodes: StructureGraphNode[];
  edges: StructureGraphEdge[];
  graph_metrics: Record<string, unknown>;
  graph_coherence: Record<string, unknown>;
  activation: GraphActivation;
  /** Versioned activation contract: full v1/v2 payloads when the run was
   * scored under the versioned pipeline; empty for historical v1-only
   * graphs. */
  activation_versions: Partial<Record<"v1" | "v2", GraphActivation>>;
  primary_activation_version: string | null;
  dominant_alphas: DominantAlpha[];
  provenance: Record<string, unknown>;
}

export type StructureGraphResult = StructureGraphResponse | SafeErrorEnvelope;

// ---------------------------------------------------------------------------
// GET /api/research/{run_id}/conflicts
// ---------------------------------------------------------------------------

export const CONFLICT_LEVELS = ["low", "medium", "medium_high", "high"] as const;
export type ConflictLevel = (typeof CONFLICT_LEVELS)[number];

/** bull_structure/bear_structure -- see conflict_detector._structure_block. */
export interface ConflictSideStructure {
  alpha_id: string;
  alpha_name: string;
  activation_score: number;
  status: string;
  direction: string;
  claim_ids: string[];
  source_agent_output_ids: string[];
  agents: string[];
  evidence: string[];
  match_scores: number[];
}

/** One admitted conflict -- see week4_persistence._whitelist_conflict /
 * conflict_detector's conflict dict. Used both for items in `conflicts` and
 * for `main_conflict`. */
export interface AlphaConflict {
  conflict_id: string;
  alpha_a: string;
  alpha_b: string;
  bull_alpha_id: string;
  bear_alpha_id: string;
  bull_structure: ConflictSideStructure;
  bear_structure: ConflictSideStructure;
  components: {
    activation_a: number;
    activation_b: number;
    minimum_activation: number;
    contradiction_weight: number;
    alpha_a_evidence_strength: number;
    alpha_b_evidence_strength: number;
    evidence_strength: number;
  };
  alpha_a_strength: number;
  alpha_b_strength: number;
  evidence_strength: number;
  conflict_score: number;
  conflict_level: ConflictLevel;
  reason_codes: string[];
  explanation: string;
  bull_evidence: ConflictEvidenceItem[];
  bear_evidence: ConflictEvidenceItem[];
}

/** One bull/bear evidence entry for an admitted conflict -- additive fields
 * rebuilt by the conflicts API from persisted alpha_matches rows. */
export interface ConflictEvidenceItem {
  claim_id: string;
  claim_text: string;
  agent: string;
  match_score: number;
  relation: string;
}

/** One evaluated candidate pair, admitted or not -- see
 * week4_persistence._whitelist_candidate. */
export interface ConflictCandidateEvaluation {
  alpha_a: string;
  alpha_b: string;
  outcome: "admitted" | "suppressed" | "rejected";
  reason_codes: string[];
  evidence_audit: {
    alpha_a: ConflictAuditSide;
    alpha_b: ConflictAuditSide;
  };
}

export interface ConflictAuditSide {
  alpha_id: string;
  qualifying_claim_ids: string[];
  qualifying_count: number;
  excluded: Array<Record<string, unknown>>;
}

export interface ConflictsResponse {
  status: "ok";
  schema_version: string;
  formula_version: string;
  /** Which activation formula this run's conflicts were computed against
   * (v1 for historical runs, v2 for new runs); null when unavailable. */
  activation_formula_version: string | null;
  run_id: string;
  ticker: string;
  conflicts: AlphaConflict[];
  main_conflict: AlphaConflict | null;
  arbitration: {
    declared_pair_count: number;
    admitted_count: number;
    suppressed_count: number;
    rejected_count: number;
    candidate_evaluations: ConflictCandidateEvaluation[];
  };
}

export type ConflictsResult = ConflictsResponse | SafeErrorEnvelope;

// ---------------------------------------------------------------------------
// GET /api/research/{run_id}/agent-outputs
// ---------------------------------------------------------------------------

/** The public-whitelisted subset of one structured agent output record --
 * see agent_output_reader.PUBLIC_STRUCTURED_OUTPUT_FIELDS. Every field here
 * (and only these) may ever appear; raw_output/prompt/final_state/etc. are
 * dropped server-side and must never be assumed present. */
export interface StructuredAgentOutputRecord {
  claim_id: string;
  source_agent_output_id: string;
  run_id: string;
  ticker: string;
  agent: string;
  claim: string;
  evidence: string;
  entities: string[];
  factors: string[];
  direction: string;
  confidence: number;
  agent_output_id?: string;
  timestamp?: string;
  source_type?: string;
  output_type?: string;
  source_refs?: string[];
  claim_index?: number;
  source_section?: string;
  assertion_status?: string;
  semantic_polarity?: string;
  extraction_method?: string;
}

export interface AgentOutputsResponse {
  run_id: string;
  ticker: string;
  status: "ok";
  schema_version: string;
  structured_agent_outputs: StructuredAgentOutputRecord[];
  count: number;
}

export type AgentOutputsResult = AgentOutputsResponse | SafeErrorEnvelope;

// ---------------------------------------------------------------------------
// GET /health, GET /ready
// ---------------------------------------------------------------------------

export interface HealthResponse {
  status: "ok";
}

export type RealExecutionState = "disabled" | "configured" | "misconfigured";

export interface ReadinessResponse {
  status: "ready" | "not_ready";
  database: "ready" | "unavailable";
  job_manager: "ready" | "unavailable";
  real_execution: RealExecutionState;
  /** Safe misconfiguration reason label ("credential_missing" |
   * "profile_invalid") -- never a config value or env var content. Null
   * unless real_execution is misconfigured. */
  real_execution_reason?: string | null;
}
