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

/** One entry of dominant_alphas/active_alphas/regime_level_alphas/
 * candidate_alphas/blocked_alphas -- see
 * alpha_level_classifier._alpha_summary. All five collections share this
 * exact shape (the backend builds every one from the same summary
 * function); the B4 fields below are optional only because a historical
 * payload predating task B4_ACTIVATION_LEVEL_ALIGNMENT never carried them,
 * never because a current backend response omits them selectively. */
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
  /** What the score alone (preferring uncapped_score) would reach, ignoring
   * every qualification gate. Absent on a historical (pre-B4) payload --
   * the UI must then fall back to `status`/`level`, never guess. */
  target_level?: CanonicalAlphaLevel;
  /** The actual final level after every qualification gate -- identical to
   * `status` on a B4-classified entry. Absent on a historical payload. */
  qualified_level?: CanonicalAlphaLevel;
  /** True exactly when qualified_level < target_level. Never re-derive this
   * by comparing the two levels yourself -- read it directly. */
  is_blocked?: boolean;
  /** Which level(s) were reached by score but denied by qualification, in
   * fixed order (dominant, then regime_level). Empty when not blocked. */
  blocked_from?: CanonicalAlphaLevel[];
  /** Canonical, deduped, natural-language-free reasons (task section 9) --
   * scoped to exactly the level(s) in blocked_from. Empty when not
   * blocked. */
  blocked_reason_codes?: CanonicalBlockedReason[];
  /** QA Closure v0.1.2 Item 4: the single display-facing level (see
   * ActivationDisplayLevel). Absent on a historical payload predating
   * this task -- the UI must then fall back to `status`/`qualified_level`. */
  activation_level?: ActivationDisplayLevel;
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

/** Aggregate numeric-semantics transparency (Evidence Integrity Completion
 * Sprint, Track C) -- how many reported-price candidates were technical
 * indicators/other non-market-price roles and therefore never eligible for
 * a daily-range warning. Never per-candidate detail. Null when the
 * reported-price check did not run for this run. */
export interface DataSanityNumericSemantics {
  evaluated_count: number;
  daily_range_eligible_count: number;
  skipped_by_role_count: number;
  semantic_role_counts: Record<string, number>;
}

// Sprint 3 (Unclassified Findings Control), Track A3. John's 5 canonical
// reasons -- the only values `reason`/`reason_codes` ever carry, plus the
// honest escape hatch for a finding no canonical reason resolves.
export const UNCLASSIFIED_FINDING_REASONS = [
  "no_alpha_match",
  "low_confidence",
  "generic_background",
  "duplicate_supporting_text",
  "no_ticker_specific_evidence",
] as const;
export type UnclassifiedFindingReason = (typeof UNCLASSIFIED_FINDING_REASONS)[number];
export const UNCLASSIFIED_FINDING_REASON_UNRESOLVED = "UNCLASSIFIED_REASON_UNRESOLVED";

/** One claim retained for audit that did not enter the normal classified/
 * research finding display path (comqutor_alpha/api/unclassified_findings.py).
 * Never re-judges Alpha mapping, Evidence Stance, or Evidence Fact grouping --
 * every field here is read straight off alpha_matches.json/
 * structured_agent_outputs.json/evidence_facts.json. */
export interface UnclassifiedFinding {
  run_id: string;
  ticker: string;
  claim_id: string;
  claim: string | null;
  evidence: string | null;
  agent: string | null;
  /** From structured_agent_outputs.json; null when genuinely absent, never
   * a guessed 0/1. */
  confidence: number | null;
  matched_alpha: string | null;
  secondary_alphas: string[];
  direction: string | null;
  reason: UnclassifiedFindingReason | typeof UNCLASSIFIED_FINDING_REASON_UNRESOLVED;
  reason_codes: (UnclassifiedFindingReason | typeof UNCLASSIFIED_FINDING_REASON_UNRESOLVED)[];
  diagnostic_reason_codes: string[];
  ticker_specific: boolean;
  duplicate_group_id: string | null;
  evidence_fact_group_id: string | null;
  representative_claim_id: string | null;
  source_refs: string[];
  source_agent_output_id: string | null;
  claim_index: number | null;
  display_rank: number;
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
  entity_alpha_exposures?: EntityAlphaExposureRecord[];
  entity_alpha_exposure_status?: "ready" | "unavailable";
  /** Additive; absent/null on a payload predating this field or a run with
   * no reported-price check. */
  data_sanity_numeric_semantics?: DataSanityNumericSemantics | null;
  /** Sprint 3, Track A3. Absent/undefined only for a raw payload predating
   * this field; a real current backend always sends all five, with
   * unclassified_findings_status "unavailable" (never a fabricated "0
   * findings") for a historical run lacking unclassified_findings.json. */
  unclassified_findings_top20?: UnclassifiedFinding[];
  unclassified_findings_total_count?: number | null;
  unclassified_findings_reason_counts?: Record<string, number>;
  unclassified_findings_status?: "ready" | "unavailable";
  unclassified_findings_download_available?: boolean;
}

export type CanonicalResearchResult = CanonicalResearchResponse | SafeErrorEnvelope;

// ---------------------------------------------------------------------------
// GET /api/research/{run_id}/graph
// ---------------------------------------------------------------------------

export const GRAPH_EDGE_TYPES = ["causal", "supportive", "conflicting"] as const;
export type GraphEdgeType = (typeof GRAPH_EDGE_TYPES)[number];

/** "inactive"/"watch" are historical-payload-only (task
 * B4_ACTIVATION_LEVEL_ALIGNMENT, Decision 3): a B4-classified run never
 * produces either -- "candidate" is the sole new-output level below
 * "active". Kept here only so an old saved payload still narrows/renders
 * without a runtime type error. */
export const ACTIVATION_STATUSES = [
  "inactive",
  "watch",
  "candidate",
  "active",
  "dominant",
  "regime_level",
] as const;
export type ActivationStatus = (typeof ACTIVATION_STATUSES)[number];

/** The four canonical Alpha levels (task B4_ACTIVATION_LEVEL_ALIGNMENT,
 * Decision 1) -- "blocked" is never a fifth level; it is qualification
 * metadata (`is_blocked`/`blocked_from`) layered on top of one of these
 * four. Mirrors graph_engine.alpha_level_classifier.CANONICAL_LEVELS --
 * the frontend must never hardcode a fifth string here. */
export const CANONICAL_ALPHA_LEVELS = ["candidate", "active", "dominant", "regime_level"] as const;
export type CanonicalAlphaLevel = (typeof CANONICAL_ALPHA_LEVELS)[number];

/** John's four canonical, product-facing blocked reasons (task
 * B4_ACTIVATION_LEVEL_ALIGNMENT section 9) -- mirrors
 * alpha_level_classifier.CANONICAL_BLOCKED_REASONS. The backend maps every
 * underlying diagnostic code onto one of these before it ever reaches
 * `blocked_reason_codes`; the frontend must never invent a fifth or
 * re-derive one from `diagnostic_reason_codes` itself. */
export const CANONICAL_BLOCKED_REASONS = [
  "NO_LOCAL_STRUCTURE_SUPPORT",
  "INSUFFICIENT_EVIDENCE",
  "LOW_ENTITY_EXPOSURE",
  "NO_TICKER_SPECIFIC_EVIDENCE",
] as const;
export type CanonicalBlockedReason = (typeof CANONICAL_BLOCKED_REASONS)[number];

/** QA Closure v0.1.2 Item 4 (Alpha Level Display Alignment): a
 * presentation-only refinement of CanonicalAlphaLevel -- "capped_active"
 * is never a fifth qualified_level/target_level/blocked_from value (those
 * stay exactly the four CANONICAL_ALPHA_LEVELS above); it is this
 * dedicated display field's own value, read directly from the backend
 * (alpha_level_classifier.CAPPED_ACTIVE), never recomputed from score/
 * is_blocked/blocked_from in the frontend. "candidate_active" is
 * deliberately absent: no authoritative existing B4 definition for it was
 * found (task section 4.2) -- never invented here either. */
export const ACTIVATION_DISPLAY_LEVELS = [
  "candidate",
  "active",
  "capped_active",
  "dominant",
  "regime_level",
] as const;
export type ActivationDisplayLevel = (typeof ACTIVATION_DISPLAY_LEVELS)[number];

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

/** John's B3 gated seed lifecycle (task B3_ENTITY_EXPOSURE_GATED_STATES) --
 * the product-authoritative vocabulary. `configured_status` is what the
 * seed file declares for this ticker; `effective_status` is what actually
 * applied after the fail-closed approval-completeness check and any
 * (downgrade-only) override -- always read `effective_status` to decide
 * what happened, never re-derive it from `configured_status` alone. */
export type EntityExposureLifecycleStatus = "draft_shadow" | "approved_gating" | "disabled";

export interface EntityExposure {
  historical_mapping: number | null;
  current_evidence: number;
  agent_confidence: number;
  final_exposure: number | null;
  seed_version: string;
  seed_effective_date: string;
  /** @deprecated Backward-compatible alias of configured_status (task
   * section 7/9) -- prefer configured_status/effective_status below. */
  seed_approval_status: string;
  /** @deprecated Legacy off/shadow/enforced vocabulary -- prefer
   * effective_status below. */
  mode: "off" | "shadow" | "enforced";
  exposure_status: "computed" | "missing_seed";
  would_block_dominant: boolean;
  would_block_regime_level: boolean;
  override_candidate: boolean;
  qualification_effect_applied: boolean;
  unique_evidence_fact_count: number;
  ticker_specific_fact_count: number;
  distinct_supporting_agent_count: number;
  reason_codes: string[];
  /** Absent on historical payloads predating this field -- the UI must
   * fall back gracefully (e.g. to the legacy `mode`/`seed_approval_status`
   * fields above), never crash. */
  owner?: string | null;
  approved_by?: string | null;
  approved_at?: string | null;
  configured_status?: EntityExposureLifecycleStatus | null;
  effective_status?: EntityExposureLifecycleStatus | null;
}

export interface EntityAlphaExposureRecord extends EntityExposure {
  run_id: string;
  ticker: string;
  alpha_id: string;
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
  /** Historically ambiguous name: this is the number of QUALIFYING local
   * structure edges the frozen Activation formula counted, never the raw
   * number of graph edges incident to this alpha's factors. Prefer
   * qualifying_local_edge_count/incident_graph_edge_count below when both
   * are available; kept for backward compatibility, never removed. */
  local_edge_count: number | null;
  /** Backend's own regime-gate verdict -- the frontend must read this
   * directly (and regime_gate_failures) rather than re-deriving pass/fail
   * from activation_score/status itself. */
  regime_gate_passed: boolean | null;
  regime_gate_failures: string[];
  /** Evidence Integrity Completion Sprint, Track C (additive, top-level;
   * null/absent on an API response predating this field -- the UI must
   * fall back gracefully, never crash). */
  raw_supporting_claim_count?: number | null;
  unique_evidence_fact_count?: number | null;
  distinct_supporting_agent_count?: number | null;
  evidence_overlap_ratio?: number | null;
  /** Backend's own verdict (reuses the frozen regime-gate evidence floor)
   * -- the UI must read this directly rather than picking its own
   * threshold on evidence_overlap_ratio. */
  high_overlap_warning?: boolean | null;
  /** Draft/shadow Entity Exposure sidecar; null on historical payloads. */
  entity_exposure?: EntityExposure | null;
  /** B4 Activation Level Alignment (task B4_ACTIVATION_LEVEL_ALIGNMENT) --
   * the single authoritative classification, written by
   * alpha_level_classifier.classify_and_rebuild_collections. All seven
   * fields below are absent together on a historical payload predating
   * B4; a current backend response always includes all seven. `status`
   * above is always identical to `qualified_level` once these are
   * present -- the frontend must read qualified_level/target_level/
   * is_blocked directly and must never recompute a level from
   * activation_score, and must never hardcode the 50/70/86 thresholds. */
  target_level?: CanonicalAlphaLevel;
  qualified_level?: CanonicalAlphaLevel;
  is_blocked?: boolean;
  blocked_from?: CanonicalAlphaLevel[];
  blocked_reason_codes?: CanonicalBlockedReason[];
  /** Full, unmapped diagnostic detail preserved for audit -- never shown
   * as the primary blocked reason (use blocked_reason_codes for that);
   * useful only in a collapsible/expanded detail view. */
  diagnostic_reason_codes?: string[];
  classification_version?: string;
  /** QA Closure v0.1.2 Item 4: the single display-facing level (see
   * ActivationDisplayLevel). Absent on a historical payload predating
   * this task -- the UI must then fall back to `status`/`qualified_level`. */
  activation_level?: ActivationDisplayLevel;
}

/** Additive fields on components.local_structure_support (Structure
 * Integrity Repair Sprint, Track 1) -- "how many graph edges are incident
 * to this alpha" vs "how many the frozen formula counted as qualifying"
 * are two different, both-honest numbers. Optional: components is an
 * untyped Record, so callers must narrow/guard before reading these. */
export interface LocalStructureSupportComponent {
  incident_graph_edge_count?: number | null;
  qualifying_local_edge_count?: number | null;
  nonqualifying_local_edge_count?: number | null;
  local_edge_exclusion_reasons?: string[] | null;
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
  /** Keeps its exact pre-existing meaning: dominant OR regime_level (task
   * B4_ACTIVATION_LEVEL_ALIGNMENT section 12 -- an A2-frozen field name,
   * never redefined). Prefer the four split collections below for any new
   * UI that needs the five-way mutually-exclusive partition (task section
   * 11); this field remains for backward compatibility. */
  dominant_alphas: DominantAlpha[];
  /** B4 additive authoritative collections -- absent (undefined, never a
   * fabricated empty array vs. "genuinely has none") only on a historical
   * payload predating task B4_ACTIVATION_LEVEL_ALIGNMENT. A current
   * backend response always includes all four, possibly empty. */
  active_alphas?: DominantAlpha[];
  regime_level_alphas?: DominantAlpha[];
  candidate_alphas?: DominantAlpha[];
  blocked_alphas?: DominantAlpha[];
  provenance: Record<string, unknown>;
}

export type StructureGraphResult = StructureGraphResponse | SafeErrorEnvelope;

// ---------------------------------------------------------------------------
// GET /api/research/{run_id}/conflicts
// ---------------------------------------------------------------------------

export const CONFLICT_LEVELS = ["low", "medium", "medium_high", "high"] as const;
export type ConflictLevel = (typeof CONFLICT_LEVELS)[number];

// ---------------------------------------------------------------------------
// B5 Conflict Radar Evidence UI (task B5_CONFLICT_RADAR_EVIDENCE_UI) -- see
// conflict_engine.conflict_evidence_ui.build_conflict_evidence_ui. Purely a
// presentation/audit layer over B1's already-final evidence_stance and B2's
// already-computed admissibility detail: never re-derived here, never a
// second stance classifier, never a second Evidence Fact dedup pass.
// ---------------------------------------------------------------------------

export const EVIDENCE_STANCE_VALUES = [
  "supports_alpha",
  "opposes_alpha",
  "supports_counter_alpha",
] as const;
export type EvidenceStanceValue = (typeof EVIDENCE_STANCE_VALUES)[number];

export const MISSING_EVIDENCE_REASON_CODES = [
  "INSUFFICIENT_SUPPORTING_EVIDENCE",
  "NO_TICKER_SPECIFIC_SUPPORTING_EVIDENCE",
  "NO_ADMISSIBLE_SUPPORTING_POLARITY",
] as const;
export type MissingEvidenceReasonCode = (typeof MISSING_EVIDENCE_REASON_CODES)[number];

/** One stance-filtered, fact-grouped Evidence item -- shared shape for
 * bull_evidence/bear_evidence (evidence_stance always "supports_alpha") and
 * counter_evidence (evidence_stance "opposes_alpha" or
 * "supports_counter_alpha", plus counter_target_alpha_id). Never a raw,
 * un-deduplicated claim -- always one entry per unique Evidence Fact group. */
export interface ConflictEvidenceUIItem {
  evidence_fact_group_id: string;
  representative_claim_id: string;
  member_claim_ids: string[];
  evidence_text: string;
  agents: string[];
  source_agent_output_ids: string[];
  target_alpha_id: string;
  evidence_stance: EvidenceStanceValue;
  /** "llm" | "deterministic_fallback" | null (LLM never attempted for this
   * claim -- a plain deterministic classification, not a lesser LLM
   * result). Always show this alongside the stance, never imply LLM
   * provenance that was never attempted. */
  stance_method: string | null;
  evidence_stance_version: string | null;
  stance_confidence_band: string | null;
  ticker_specific: boolean;
  representative_match_score: number;
  /** Counter Evidence only: which conflict side this item counters. */
  counter_target_alpha_id?: string;
  /** Counter Evidence, Case B only (supports_counter_alpha): the alpha
   * this evidence supports instead. */
  supports_counter_alpha_id?: string | null;
}

export interface ConflictMissingEvidenceItem {
  side: "bull" | "bear";
  alpha_id: string;
  missing_reason_code: MissingEvidenceReasonCode;
  current_value: number;
  required_value: number;
  deficit: number;
}

/** Deliberately separate from missing_evidence (task section 7): an
 * Activation-score shortfall is a qualification concern, never an
 * evidence-content concern -- never render this inside a "Missing
 * Evidence" section. */
export interface ConflictQualificationGapItem {
  side: "bull" | "bear";
  alpha_id: string;
  gap_reason_code: "ALPHA_SCORE_BELOW_THRESHOLD";
  current_value: number | null;
  required_value: number;
}

export interface AlphaInvalidationCondition {
  condition_id: string;
  condition_text: string;
}

/** approval_status "not_defined" means exactly that -- no Product Owner
 * has approved invalidation content for this Alpha yet. Never render a
 * fabricated condition list; show the honest "pending" state instead. */
export interface AlphaInvalidationEntry {
  alpha_id: string;
  alpha_name: string | null;
  approval_status: "approved" | "not_defined";
  source: string | null;
  version: string | null;
  conditions: AlphaInvalidationCondition[];
}

/** The full B5 block attached to one conflict/candidate evaluation.
 * Absent entirely (undefined) on a historical payload predating task
 * B5_CONFLICT_RADAR_EVIDENCE_UI -- the UI must show "Not available for
 * this historical run", never silently render empty sections that look
 * like a verified "no evidence" result. */
export interface ConflictEvidenceUI {
  schema_version: string;
  bull_evidence: ConflictEvidenceUIItem[];
  bear_evidence: ConflictEvidenceUIItem[];
  counter_evidence: ConflictEvidenceUIItem[];
  missing_evidence: ConflictMissingEvidenceItem[];
  qualification_gaps: ConflictQualificationGapItem[];
  invalidation_conditions: {
    bull_alpha: AlphaInvalidationEntry;
    bear_alpha: AlphaInvalidationEntry;
  };
}

/** John's B2 Conflict Evidence Admissibility gate detail -- see
 * conflict_admissibility.AdmissibilityResult.to_dict(). Present on every
 * fully-evaluated candidate (admitted or not); absent only when the pair
 * never reached B2 evaluation at all (e.g. missing evidence, unresolved
 * bull/bear role -- an earlier, coarser rejection). */
export interface ConflictAdmissibility {
  admissibility_version: string;
  status: "admitted" | "candidate";
  reason_codes: string[];
  bull_score: number | null;
  bear_score: number | null;
  bull_supporting_evidence_count: number;
  bear_supporting_evidence_count: number;
  bull_ticker_specific_support_count: number;
  bear_ticker_specific_support_count: number;
  bull_supporting_fact_group_ids: string[];
  bear_supporting_fact_group_ids: string[];
}

/** One Evidence Fact group attached to a conflict side (Evidence Integrity
 * Completion Sprint, Track B) -- see conflict_detector._structure_block. */
export interface ConflictEvidenceFactGroup {
  evidence_fact_group_id: string;
  representative_claim_id: string;
  member_claim_ids: string[];
  supporting_agents: string[];
  grouping_method: string;
}

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
  /** Additive; absent on a payload predating this field. */
  evidence_facts?: ConflictEvidenceFactGroup[];
  /** QA Closure v0.1.2 Item 4: the same display-facing level AlphaCard
   * shows for this Alpha elsewhere (see ActivationDisplayLevel). Absent
   * on a payload predating this task -- the UI must then fall back to
   * `status`. */
  activation_level?: ActivationDisplayLevel;
  /** Populated exactly when activation_level is "capped_active" -- the
   * existing B4 reason code(s) the qualification ceiling came from. */
  blocked_reason_codes?: CanonicalBlockedReason[];
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
  /** Evidence Integrity Completion Sprint, Track B (additive; absent on a
   * payload predating this field -- the UI must fall back gracefully). */
  bull_raw_claim_count?: number;
  bull_unique_fact_count?: number;
  bull_distinct_agent_count?: number;
  bull_overlap_ratio?: number;
  bull_fact_group_ids?: string[];
  bear_raw_claim_count?: number;
  bear_unique_fact_count?: number;
  bear_distinct_agent_count?: number;
  bear_overlap_ratio?: number;
  bear_fact_group_ids?: string[];
  shared_fact_group_ids?: string[];
  shared_fact_group_count?: number;
  shared_fact_resolution?: string;
  /** John's B2 Conflict Evidence Admissibility gate -- always present on a
   * conflict that reached this point (it must have passed B2 to be
   * "admitted" at all), included here for the same "why did this qualify"
   * transparency the UI already gives a candidate/suppressed pair. */
  admissibility?: ConflictAdmissibility;
  /** B5 Conflict Radar Evidence UI (additive; absent on a payload
   * predating task B5_CONFLICT_RADAR_EVIDENCE_UI). */
  evidence_ui?: ConflictEvidenceUI;
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
  /** Only present once bull/bear roles were actually resolved for this
   * pair (present together with admissibility/evidence_ui) -- read these
   * directly to label evidence sides; never guess which of alpha_a/
   * alpha_b is bull from direction or ordering. */
  bull_alpha_id?: string;
  bear_alpha_id?: string;
  /** Only present once the pair actually reached B2 evaluation -- absent
   * for a pair rejected earlier (missing evidence, unresolved bull/bear
   * role, below-activation-threshold). Read this directly to render the
   * candidate's specific B2 gate failure; never re-derive it from
   * reason_codes alone. */
  admissibility?: ConflictAdmissibility;
  /** B5 Conflict Radar Evidence UI (additive; present exactly when
   * admissibility is -- both are attached together by the same
   * conflict_detector call site). Absent on a historical payload. */
  evidence_ui?: ConflictEvidenceUI;
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

// ---------------------------------------------------------------------------
// POST /api/replay-all -- one-click batch replay of every saved
// TradingAgents raw output under outputs/runs/ through the current
// COMQUTOR architecture. Synchronous: the response already contains every
// run's final outcome, never a queued/polling shape.
// ---------------------------------------------------------------------------

export type ReplayAllRunStatus = "completed" | "blocked" | "failed";

export interface ReplayAllRunResult {
  source_run_id: string;
  ticker: string | null;
  replay_run_id: string | null;
  status: ReplayAllRunStatus;
  output_dir: string | null;
  error_code: string | null;
}

export interface ReplayAllResult {
  status: "completed";
  total_runs_found: number;
  completed_count: number;
  blocked_count: number;
  failed_count: number;
  results: ReplayAllRunResult[];
  provider_calls: number;
  tradingagents_calls: number;
}
