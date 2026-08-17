/**
 * Runtime validation for every JSON payload this frontend receives from the
 * COMQUTOR API. Nothing crossing the HTTP boundary is trusted via `as
 * SomeType` -- every shape is checked structurally here first. A payload
 * that does not match is rejected (the caller sees ApiError.invalidResponse())
 * rather than silently rendered with missing/undefined fields.
 *
 * These adapters are deliberately lenient about *unknown extra fields* (the
 * backend is free to add additive fields later) and strict about *required*
 * fields' presence and primitive type.
 */

import type {
  AgentOutputsResponse,
  AlphaConflict,
  AlphaEvidenceDetail,
  AlphaInvalidationCondition,
  AlphaInvalidationEntry,
  ConflictAdmissibility,
  ConflictAuditSide,
  ConflictCandidateEvaluation,
  ConflictEvidenceFactGroup,
  ConflictEvidenceItem,
  ConflictEvidenceUI,
  ConflictEvidenceUIItem,
  ConflictMissingEvidenceItem,
  ConflictQualificationGapItem,
  ConflictSideStructure,
  ConflictsResponse,
  DataSanitySeverity,
  DataSanityStatus,
  DataSanityWarning,
  DominantAlpha,
  EntityAlphaExposureRecord,
  EntityExposure,
  GraphActivation,
  AlphaActivation,
  HealthResponse,
  CanonicalResearchResponse,
  ReadinessResponse,
  ReplayAllResult,
  ReplayAllRunResult,
  ResearchArtifacts,
  ResearchRunRecord,
  ResearchSubmissionResult,
  RunHistoryResponse,
  RunStatusResult,
  StructureGraphEdge,
  StructureGraphNode,
  StructureGraphResponse,
  StructuredAgentOutputRecord,
  UnclassifiedFinding,
  UnclassifiedFindingReason,
} from "./types";
import {
  DATA_SANITY_SEVERITIES,
  DATA_SANITY_STATUSES,
  UNCLASSIFIED_FINDING_REASONS,
  UNCLASSIFIED_FINDING_REASON_UNRESOLVED,
} from "./types";

export type AdaptResult<T> = { ok: true; value: T } | { ok: false; reason: string };

function ok<T>(value: T): AdaptResult<T> {
  return { ok: true, value };
}

function fail<T>(reason: string): AdaptResult<T> {
  return { ok: false, reason };
}

function isRecord(value: unknown): value is Record<string, unknown> {
  return typeof value === "object" && value !== null && !Array.isArray(value);
}

function isString(value: unknown): value is string {
  return typeof value === "string";
}

function isNumber(value: unknown): value is number {
  return typeof value === "number" && Number.isFinite(value);
}

function isStringArray(value: unknown): value is string[] {
  return Array.isArray(value) && value.every((item) => typeof item === "string");
}

function isNumberArray(value: unknown): value is number[] {
  return Array.isArray(value) && value.every((item) => typeof item === "number");
}

function isBoolean(value: unknown): value is boolean {
  return typeof value === "boolean";
}

function optionalString(value: unknown): string | undefined {
  return isString(value) ? value : undefined;
}

function nullableString(value: unknown): string | null {
  return isString(value) ? value : null;
}

function nullableNumber(value: unknown): number | null {
  return isNumber(value) ? value : null;
}

const ETA_STATUSES = ["estimating", "available", "complete", "unavailable"] as const;

function nullableEtaStatus(value: unknown): (typeof ETA_STATUSES)[number] | null {
  return typeof value === "string" && (ETA_STATUSES as readonly string[]).includes(value)
    ? (value as (typeof ETA_STATUSES)[number])
    : null;
}

/** Every "safe error envelope" response the backend can return (status,
 * error_code, message; run_id/ticker nullable) -- used as a fallback when a
 * success-shape adapter rejects a payload. */
export function looksLikeErrorEnvelope(payload: unknown): payload is {
  run_id: string | null;
  ticker: string | null;
  status: string;
  error_code?: string | null;
  message?: string | null;
} {
  if (!isRecord(payload)) return false;
  return isString(payload.status);
}

// ---------------------------------------------------------------------------
// POST /api/research
// ---------------------------------------------------------------------------

export function adaptResearchSubmissionResult(payload: unknown): AdaptResult<ResearchSubmissionResult> {
  if (!isRecord(payload)) return fail("response is not an object");
  if (!isString(payload.status)) return fail("missing status");

  const result: ResearchSubmissionResult = {
    run_id: nullableString(payload.run_id),
    ticker: nullableString(payload.ticker),
    status: payload.status,
  };
  if (isString(payload.run_status)) result.run_status = payload.run_status;
  if (isString(payload.stage) || payload.stage === null) result.stage = payload.stage as string | null;
  if (isString(payload.cache_disposition)) {
    result.cache_disposition = payload.cache_disposition as ResearchSubmissionResult["cache_disposition"];
  }
  if (isString(payload.error_code)) result.error_code = payload.error_code;
  if (isString(payload.message)) result.message = payload.message;
  if (isRecord(payload.artifacts)) {
    const artifacts = adaptArtifacts(payload.artifacts);
    if (artifacts.ok) result.artifacts = artifacts.value;
  }
  if (isNumber(payload.agent_output_count)) result.agent_output_count = payload.agent_output_count;
  if (isNumber(payload.structured_output_count)) {
    result.structured_output_count = payload.structured_output_count;
  }
  if (payload.structure_graph_status === "ready" || payload.structure_graph_status === "not_ready") {
    result.structure_graph_status = payload.structure_graph_status;
  }
  if (Array.isArray(payload.dominant_alphas)) {
    const dominant = payload.dominant_alphas
      .map(adaptDominantAlpha)
      .filter((item): item is AdaptResult<DominantAlpha> & { ok: true } => item.ok)
      .map((item) => item.value);
    result.dominant_alphas = dominant;
  }
  if (payload.main_conflict === null) {
    result.main_conflict = null;
  } else if (isRecord(payload.main_conflict)) {
    const conflict = adaptAlphaConflict(payload.main_conflict);
    if (conflict.ok) result.main_conflict = conflict.value;
  }
  if (payload.conflict_status === "ready" || payload.conflict_status === "not_ready") {
    result.conflict_status = payload.conflict_status;
  }
  if (isString(payload.summary)) result.summary = payload.summary;

  return ok(result);
}

// ---------------------------------------------------------------------------
// Run status / history
// ---------------------------------------------------------------------------

export function adaptRunStatusResult(payload: unknown): AdaptResult<RunStatusResult> {
  if (!isRecord(payload)) return fail("response is not an object");
  if (!isString(payload.status)) return fail("missing status");

  // A failed lifecycle record is still a full run record and carries the
  // ticker/date/analysts needed for a legitimate retry. Only a failed shape
  // without those record fields is an endpoint error envelope.
  if (isString(payload.run_id) && isString(payload.ticker) && isStringArray(payload.selected_analysts)) {
    return adaptResearchRunRecord(payload);
  }

  if (payload.status === "failed" && isString(payload.error_code)) {
    return ok({
      run_id: nullableString(payload.run_id) ?? "",
      status: "failed",
      error_code: payload.error_code,
      message: isString(payload.message) ? payload.message : "",
    });
  }

  return adaptResearchRunRecord(payload);
}

export function adaptResearchRunRecord(payload: unknown): AdaptResult<ResearchRunRecord> {
  if (!isRecord(payload)) return fail("record is not an object");
  const { run_id, ticker, status } = payload;
  if (!isString(run_id) || !isString(ticker) || !isString(status)) {
    return fail("missing run_id/ticker/status");
  }
  return ok({
    run_id,
    ticker,
    analysis_date: nullableString(payload.analysis_date),
    selected_analysts: isStringArray(payload.selected_analysts) ? payload.selected_analysts : [],
    status: status as ResearchRunRecord["status"],
    stage: nullableString(payload.stage),
    error_code: nullableString(payload.error_code),
    message: isString(payload.message) ? payload.message : "",
    created_at: nullableString(payload.created_at),
    started_at: nullableString(payload.started_at),
    completed_at: nullableString(payload.completed_at),
    updated_at: nullableString(payload.updated_at),
    // W7 progress/ETA telemetry: strictly what the backend reports --
    // anything missing or mis-typed degrades to null, never to a guessed
    // or client-computed value.
    profile_id: nullableString(payload.profile_id),
    profile_display_name: nullableString(payload.profile_display_name),
    progress_percent: nullableNumber(payload.progress_percent),
    current_stage: nullableString(payload.current_stage),
    completed_units: nullableNumber(payload.completed_units),
    total_units: nullableNumber(payload.total_units),
    progress_message: nullableString(payload.progress_message),
    elapsed_seconds: nullableNumber(payload.elapsed_seconds),
    eta_status: nullableEtaStatus(payload.eta_status),
    estimated_remaining_seconds_min: nullableNumber(payload.estimated_remaining_seconds_min),
    estimated_remaining_seconds_max: nullableNumber(payload.estimated_remaining_seconds_max),
    eta_sample_count: nullableNumber(payload.eta_sample_count),
  });
}

export function adaptRunHistoryResponse(payload: unknown): AdaptResult<RunHistoryResponse> {
  if (!isRecord(payload)) return fail("response is not an object");
  if (payload.status !== "ok" || !Array.isArray(payload.items)) {
    return fail("missing items/status");
  }
  const items: ResearchRunRecord[] = [];
  for (const rawItem of payload.items) {
    const adapted = adaptResearchRunRecord(rawItem);
    if (!adapted.ok) return fail(`invalid history item: ${adapted.reason}`);
    items.push(adapted.value);
  }
  return ok({
    status: "ok",
    items,
    next_cursor: nullableString(payload.next_cursor),
  });
}

// ---------------------------------------------------------------------------
// Canonical research response
// ---------------------------------------------------------------------------

function adaptArtifacts(payload: unknown): AdaptResult<ResearchArtifacts> {
  if (!isRecord(payload)) return fail("artifacts is not an object");
  const keys: (keyof ResearchArtifacts)[] = [
    "metadata",
    "raw_agent_outputs",
    "structured_agent_outputs",
    "final_report",
    "alpha_matches",
    "extracted_structures",
    "structured_output_error_logs",
    "week2_llm_error_logs",
    "week2_pipeline_error_logs",
  ];
  const artifacts = {} as ResearchArtifacts;
  for (const key of keys) {
    artifacts[key] = payload[key] === true;
  }
  return ok(artifacts);
}

function adaptDominantAlpha(payload: unknown): AdaptResult<DominantAlpha> {
  if (!isRecord(payload)) return fail("dominant alpha is not an object");
  const { alpha_id, alpha_name, activation_score, status, direction } = payload;
  if (!isString(alpha_id) || !isString(alpha_name) || !isNumber(activation_score)) {
    return fail("missing dominant alpha fields");
  }
  const summary = isRecord(payload.evidence_summary) ? payload.evidence_summary : {};
  return ok({
    alpha_id,
    alpha_name,
    activation_score,
    status: isString(status) ? status : "unknown",
    direction: isString(direction) ? direction : "unknown",
    evidence_summary: {
      evidence_count: isNumber(summary.evidence_count) ? summary.evidence_count : 0,
      distinct_supporting_agents: isNumber(summary.distinct_supporting_agents)
        ? summary.distinct_supporting_agents
        : 0,
    },
  });
}

function adaptConflictSideStructure(payload: unknown): AdaptResult<ConflictSideStructure> {
  if (!isRecord(payload)) return fail("structure is not an object");
  const { alpha_id, alpha_name, activation_score, status, direction } = payload;
  if (!isString(alpha_id) || !isString(alpha_name) || !isNumber(activation_score) || !isString(status)) {
    return fail("missing structure fields");
  }
  return ok({
    alpha_id,
    alpha_name,
    activation_score,
    status,
    direction: isString(direction) ? direction : "unknown",
    claim_ids: isStringArray(payload.claim_ids) ? payload.claim_ids : [],
    source_agent_output_ids: isStringArray(payload.source_agent_output_ids)
      ? payload.source_agent_output_ids
      : [],
    agents: isStringArray(payload.agents) ? payload.agents : [],
    evidence: isStringArray(payload.evidence) ? payload.evidence : [],
    match_scores: isNumberArray(payload.match_scores) ? payload.match_scores : [],
    // Evidence Integrity Completion Sprint, Track B: was silently dropped
    // by this adapter's own narrow reconstruction (a real, pre-existing
    // bug found while wiring B5 -- ConflictSideEvidence's per-Evidence-
    // Fact rendering has never actually activated in production). Fixed
    // additively here alongside the B5 fields below.
    evidence_facts: adaptConflictEvidenceFactGroups(payload.evidence_facts),
  });
}

function adaptConflictEvidenceFactGroups(value: unknown): ConflictEvidenceFactGroup[] {
  return Array.isArray(value)
    ? value
        .filter(isRecord)
        .filter((item) => isString(item.evidence_fact_group_id) && isString(item.representative_claim_id))
        .map((item) => ({
          evidence_fact_group_id: item.evidence_fact_group_id as string,
          representative_claim_id: item.representative_claim_id as string,
          member_claim_ids: isStringArray(item.member_claim_ids) ? item.member_claim_ids : [],
          supporting_agents: isStringArray(item.supporting_agents) ? item.supporting_agents : [],
          grouping_method: isString(item.grouping_method) ? item.grouping_method : "unknown",
        }))
    : [];
}

// B5 Conflict Radar Evidence UI (task B5_CONFLICT_RADAR_EVIDENCE_UI) --
// every field below is optional at the call site (absent entirely on a
// historical payload); a present-but-malformed value is treated the same
// as absent (undefined) rather than failing the whole conflict, matching
// this file's own "lenient about additive detail, strict about required
// top-level fields" philosophy.

function adaptConflictAdmissibility(value: unknown): ConflictAdmissibility | undefined {
  if (!isRecord(value)) return undefined;
  const { admissibility_version, status, bull_score, bear_score } = value;
  if (
    !isString(admissibility_version) ||
    (status !== "admitted" && status !== "candidate") ||
    (bull_score !== null && !isNumber(bull_score)) ||
    (bear_score !== null && !isNumber(bear_score))
  ) {
    return undefined;
  }
  return {
    admissibility_version,
    status,
    reason_codes: isStringArray(value.reason_codes) ? value.reason_codes : [],
    bull_score: bull_score === null ? null : bull_score,
    bear_score: bear_score === null ? null : bear_score,
    bull_supporting_evidence_count: isNumber(value.bull_supporting_evidence_count)
      ? value.bull_supporting_evidence_count
      : 0,
    bear_supporting_evidence_count: isNumber(value.bear_supporting_evidence_count)
      ? value.bear_supporting_evidence_count
      : 0,
    bull_ticker_specific_support_count: isNumber(value.bull_ticker_specific_support_count)
      ? value.bull_ticker_specific_support_count
      : 0,
    bear_ticker_specific_support_count: isNumber(value.bear_ticker_specific_support_count)
      ? value.bear_ticker_specific_support_count
      : 0,
    bull_supporting_fact_group_ids: isStringArray(value.bull_supporting_fact_group_ids)
      ? value.bull_supporting_fact_group_ids
      : [],
    bear_supporting_fact_group_ids: isStringArray(value.bear_supporting_fact_group_ids)
      ? value.bear_supporting_fact_group_ids
      : [],
  };
}

const EVIDENCE_STANCE_VALUE_SET: ReadonlySet<string> = new Set([
  "supports_alpha",
  "opposes_alpha",
  "supports_counter_alpha",
]);

function adaptConflictEvidenceUIItems(value: unknown): ConflictEvidenceUIItem[] {
  if (!Array.isArray(value)) return [];
  const items: ConflictEvidenceUIItem[] = [];
  for (const raw of value) {
    if (!isRecord(raw)) continue;
    const {
      evidence_fact_group_id,
      representative_claim_id,
      evidence_text,
      target_alpha_id,
      evidence_stance,
      ticker_specific,
      representative_match_score,
    } = raw;
    if (
      !isString(evidence_fact_group_id) ||
      !isString(representative_claim_id) ||
      !isString(evidence_text) ||
      !isString(target_alpha_id) ||
      !isString(evidence_stance) ||
      !EVIDENCE_STANCE_VALUE_SET.has(evidence_stance) ||
      !isBoolean(ticker_specific) ||
      !isNumber(representative_match_score)
    ) {
      continue;
    }
    const item: ConflictEvidenceUIItem = {
      evidence_fact_group_id,
      representative_claim_id,
      member_claim_ids: isStringArray(raw.member_claim_ids) ? raw.member_claim_ids : [],
      evidence_text,
      agents: isStringArray(raw.agents) ? raw.agents : [],
      source_agent_output_ids: isStringArray(raw.source_agent_output_ids) ? raw.source_agent_output_ids : [],
      target_alpha_id,
      evidence_stance: evidence_stance as ConflictEvidenceUIItem["evidence_stance"],
      stance_method: isString(raw.stance_method) ? raw.stance_method : null,
      evidence_stance_version: isString(raw.evidence_stance_version) ? raw.evidence_stance_version : null,
      stance_confidence_band: isString(raw.stance_confidence_band) ? raw.stance_confidence_band : null,
      ticker_specific,
      representative_match_score,
    };
    if (isString(raw.counter_target_alpha_id)) item.counter_target_alpha_id = raw.counter_target_alpha_id;
    if (isString(raw.supports_counter_alpha_id)) item.supports_counter_alpha_id = raw.supports_counter_alpha_id;
    items.push(item);
  }
  return items;
}

const MISSING_EVIDENCE_SIDE_SET: ReadonlySet<string> = new Set(["bull", "bear"]);
const MISSING_EVIDENCE_REASON_SET: ReadonlySet<string> = new Set([
  "INSUFFICIENT_SUPPORTING_EVIDENCE",
  "NO_TICKER_SPECIFIC_SUPPORTING_EVIDENCE",
  "NO_ADMISSIBLE_SUPPORTING_POLARITY",
]);

function adaptConflictMissingEvidenceItems(value: unknown): ConflictMissingEvidenceItem[] {
  if (!Array.isArray(value)) return [];
  const items: ConflictMissingEvidenceItem[] = [];
  for (const raw of value) {
    if (!isRecord(raw)) continue;
    const { side, alpha_id, missing_reason_code, current_value, required_value, deficit } = raw;
    if (
      !isString(side) ||
      !MISSING_EVIDENCE_SIDE_SET.has(side) ||
      !isString(alpha_id) ||
      !isString(missing_reason_code) ||
      !MISSING_EVIDENCE_REASON_SET.has(missing_reason_code) ||
      !isNumber(current_value) ||
      !isNumber(required_value) ||
      !isNumber(deficit)
    ) {
      continue;
    }
    items.push({
      side: side as "bull" | "bear",
      alpha_id,
      missing_reason_code: missing_reason_code as ConflictMissingEvidenceItem["missing_reason_code"],
      current_value,
      required_value,
      deficit,
    });
  }
  return items;
}

function adaptConflictQualificationGapItems(value: unknown): ConflictQualificationGapItem[] {
  if (!Array.isArray(value)) return [];
  const items: ConflictQualificationGapItem[] = [];
  for (const raw of value) {
    if (!isRecord(raw)) continue;
    const { side, alpha_id, gap_reason_code, current_value, required_value } = raw;
    if (
      !isString(side) ||
      !MISSING_EVIDENCE_SIDE_SET.has(side) ||
      !isString(alpha_id) ||
      gap_reason_code !== "ALPHA_SCORE_BELOW_THRESHOLD" ||
      (current_value !== null && !isNumber(current_value)) ||
      !isNumber(required_value)
    ) {
      continue;
    }
    items.push({
      side: side as "bull" | "bear",
      alpha_id,
      gap_reason_code,
      current_value: current_value === null ? null : current_value,
      required_value,
    });
  }
  return items;
}

function adaptAlphaInvalidationEntry(value: unknown): AlphaInvalidationEntry | undefined {
  if (!isRecord(value)) return undefined;
  const { alpha_id, alpha_name, approval_status, source, version, conditions } = value;
  if (
    !isString(alpha_id) ||
    (alpha_name !== null && !isString(alpha_name)) ||
    (approval_status !== "approved" && approval_status !== "not_defined") ||
    (source !== null && !isString(source)) ||
    (version !== null && !isString(version)) ||
    !Array.isArray(conditions)
  ) {
    return undefined;
  }
  const adaptedConditions: AlphaInvalidationCondition[] = conditions
    .filter(isRecord)
    .filter((c) => isString(c.condition_id) && isString(c.condition_text))
    .map((c) => ({ condition_id: c.condition_id as string, condition_text: c.condition_text as string }));
  return {
    alpha_id,
    alpha_name: alpha_name === null ? null : alpha_name,
    approval_status,
    source: source === null ? null : source,
    version: version === null ? null : version,
    conditions: adaptedConditions,
  };
}

function adaptConflictEvidenceUI(value: unknown): ConflictEvidenceUI | undefined {
  if (!isRecord(value)) return undefined;
  const { schema_version, invalidation_conditions } = value;
  if (!isString(schema_version) || !isRecord(invalidation_conditions)) return undefined;
  const bullAlpha = adaptAlphaInvalidationEntry(invalidation_conditions.bull_alpha);
  const bearAlpha = adaptAlphaInvalidationEntry(invalidation_conditions.bear_alpha);
  if (!bullAlpha || !bearAlpha) return undefined;
  return {
    schema_version,
    bull_evidence: adaptConflictEvidenceUIItems(value.bull_evidence),
    bear_evidence: adaptConflictEvidenceUIItems(value.bear_evidence),
    counter_evidence: adaptConflictEvidenceUIItems(value.counter_evidence),
    missing_evidence: adaptConflictMissingEvidenceItems(value.missing_evidence),
    qualification_gaps: adaptConflictQualificationGapItems(value.qualification_gaps),
    invalidation_conditions: { bull_alpha: bullAlpha, bear_alpha: bearAlpha },
  };
}

export function adaptAlphaConflict(payload: unknown): AdaptResult<AlphaConflict> {
  if (!isRecord(payload)) return fail("conflict is not an object");
  const {
    conflict_id,
    alpha_a,
    alpha_b,
    bull_alpha_id,
    bear_alpha_id,
    conflict_score,
    conflict_level,
    explanation,
  } = payload;
  if (
    !isString(conflict_id) ||
    !isString(alpha_a) ||
    !isString(alpha_b) ||
    !isString(bull_alpha_id) ||
    !isString(bear_alpha_id) ||
    !isNumber(conflict_score) ||
    !isString(conflict_level) ||
    !isString(explanation)
  ) {
    return fail("missing top-level conflict fields");
  }
  const bullStructure = adaptConflictSideStructure(payload.bull_structure);
  const bearStructure = adaptConflictSideStructure(payload.bear_structure);
  if (!bullStructure.ok || !bearStructure.ok) return fail("invalid bull/bear structure");
  const admissibility = adaptConflictAdmissibility(payload.admissibility);
  const evidenceUi = adaptConflictEvidenceUI(payload.evidence_ui);

  const components = isRecord(payload.components) ? payload.components : {};
  const numericComponent = (key: string): number => (isNumber(components[key]) ? (components[key] as number) : 0);

  const adaptEvidenceItems = (value: unknown): ConflictEvidenceItem[] =>
    Array.isArray(value)
      ? value
          .filter(isRecord)
          .filter((item) => isString(item.claim_id))
          .map((item) => ({
            claim_id: item.claim_id as string,
            claim_text: isString(item.claim_text) ? item.claim_text : "",
            agent: isString(item.agent) ? item.agent : "",
            match_score: isNumber(item.match_score) ? item.match_score : 0,
            relation: isString(item.relation) ? item.relation : "unknown",
          }))
      : [];

  return ok({
    conflict_id,
    alpha_a,
    alpha_b,
    bull_alpha_id,
    bear_alpha_id,
    bull_structure: bullStructure.value,
    bear_structure: bearStructure.value,
    bull_evidence: adaptEvidenceItems(payload.bull_evidence),
    bear_evidence: adaptEvidenceItems(payload.bear_evidence),
    components: {
      activation_a: numericComponent("activation_a"),
      activation_b: numericComponent("activation_b"),
      minimum_activation: numericComponent("minimum_activation"),
      contradiction_weight: numericComponent("contradiction_weight"),
      alpha_a_evidence_strength: numericComponent("alpha_a_evidence_strength"),
      alpha_b_evidence_strength: numericComponent("alpha_b_evidence_strength"),
      evidence_strength: numericComponent("evidence_strength"),
    },
    alpha_a_strength: isNumber(payload.alpha_a_strength) ? payload.alpha_a_strength : 0,
    alpha_b_strength: isNumber(payload.alpha_b_strength) ? payload.alpha_b_strength : 0,
    evidence_strength: isNumber(payload.evidence_strength) ? payload.evidence_strength : 0,
    conflict_score,
    conflict_level: conflict_level as AlphaConflict["conflict_level"],
    reason_codes: isStringArray(payload.reason_codes) ? payload.reason_codes : [],
    explanation,
    // Evidence Integrity Completion Sprint, Track B -- also previously
    // silently dropped by this adapter's narrow reconstruction (same real,
    // pre-existing bug as evidence_facts above); ConflictSideFactStats has
    // never actually rendered real counts in production. Fixed additively.
    ...(isNumber(payload.bull_raw_claim_count) ? { bull_raw_claim_count: payload.bull_raw_claim_count } : {}),
    ...(isNumber(payload.bull_unique_fact_count) ? { bull_unique_fact_count: payload.bull_unique_fact_count } : {}),
    ...(isNumber(payload.bull_distinct_agent_count)
      ? { bull_distinct_agent_count: payload.bull_distinct_agent_count }
      : {}),
    ...(isNumber(payload.bull_overlap_ratio) ? { bull_overlap_ratio: payload.bull_overlap_ratio } : {}),
    ...(isStringArray(payload.bull_fact_group_ids) ? { bull_fact_group_ids: payload.bull_fact_group_ids } : {}),
    ...(isNumber(payload.bear_raw_claim_count) ? { bear_raw_claim_count: payload.bear_raw_claim_count } : {}),
    ...(isNumber(payload.bear_unique_fact_count) ? { bear_unique_fact_count: payload.bear_unique_fact_count } : {}),
    ...(isNumber(payload.bear_distinct_agent_count)
      ? { bear_distinct_agent_count: payload.bear_distinct_agent_count }
      : {}),
    ...(isNumber(payload.bear_overlap_ratio) ? { bear_overlap_ratio: payload.bear_overlap_ratio } : {}),
    ...(isStringArray(payload.bear_fact_group_ids) ? { bear_fact_group_ids: payload.bear_fact_group_ids } : {}),
    ...(isStringArray(payload.shared_fact_group_ids)
      ? { shared_fact_group_ids: payload.shared_fact_group_ids }
      : {}),
    ...(isNumber(payload.shared_fact_group_count)
      ? { shared_fact_group_count: payload.shared_fact_group_count }
      : {}),
    ...(isString(payload.shared_fact_resolution) ? { shared_fact_resolution: payload.shared_fact_resolution } : {}),
    // John's B2 Conflict Evidence Admissibility gate + B5 Conflict Radar
    // Evidence UI (additive; absent entirely on a historical payload).
    ...(admissibility ? { admissibility } : {}),
    ...(evidenceUi ? { evidence_ui: evidenceUi } : {}),
  });
}

const DATA_SANITY_STATUS_SET: ReadonlySet<string> = new Set(DATA_SANITY_STATUSES);
const DATA_SANITY_SEVERITY_SET: ReadonlySet<string> = new Set(DATA_SANITY_SEVERITIES);

/** Strict, not lenient: an unrecognized severity/code type is a contract
 * mismatch (dropped), never silently coerced to a guessed default. */
function adaptDataSanityWarning(payload: unknown): AdaptResult<DataSanityWarning> {
  if (!isRecord(payload)) return fail("data sanity warning is not an object");
  const { code, severity, message, details } = payload;
  if (!isString(code) || !isString(severity) || !isString(message)) {
    return fail("data sanity warning missing code/severity/message");
  }
  if (!DATA_SANITY_SEVERITY_SET.has(severity)) {
    return fail(`unknown data sanity warning severity: ${severity}`);
  }
  if (details !== undefined && !isRecord(details)) {
    return fail("data sanity warning details must be an object");
  }
  return ok({
    code,
    severity: severity as DataSanitySeverity,
    message,
    details: isRecord(details) ? details : {},
  });
}

// Sprint 3 (Unclassified Findings Control), Track A3.
const UNCLASSIFIED_FINDING_REASON_SET = new Set<string>([
  ...UNCLASSIFIED_FINDING_REASONS,
  UNCLASSIFIED_FINDING_REASON_UNRESOLVED,
]);

function adaptUnclassifiedFindingReason(
  value: unknown
): UnclassifiedFindingReason | typeof UNCLASSIFIED_FINDING_REASON_UNRESOLVED | null {
  return isString(value) && UNCLASSIFIED_FINDING_REASON_SET.has(value)
    ? (value as UnclassifiedFindingReason | typeof UNCLASSIFIED_FINDING_REASON_UNRESOLVED)
    : null;
}

function adaptUnclassifiedFinding(payload: unknown): AdaptResult<UnclassifiedFinding> {
  if (!isRecord(payload)) return fail("finding is not an object");
  const { run_id, ticker, claim_id } = payload;
  if (!isString(run_id) || !isString(ticker) || !isString(claim_id)) {
    return fail("missing run_id/ticker/claim_id");
  }
  const reason = adaptUnclassifiedFindingReason(payload.reason);
  if (!reason) return fail("missing/unknown reason");
  if (!isNumber(payload.display_rank)) return fail("missing display_rank");
  const reasonCodes = isStringArray(payload.reason_codes)
    ? payload.reason_codes
        .map(adaptUnclassifiedFindingReason)
        .filter((code): code is NonNullable<typeof code> => code !== null)
    : [];
  return ok({
    run_id,
    ticker,
    claim_id,
    claim: nullableString(payload.claim),
    evidence: nullableString(payload.evidence),
    agent: nullableString(payload.agent),
    confidence: nullableNumber(payload.confidence),
    matched_alpha: nullableString(payload.matched_alpha),
    secondary_alphas: isStringArray(payload.secondary_alphas) ? payload.secondary_alphas : [],
    direction: nullableString(payload.direction),
    reason,
    reason_codes: reasonCodes,
    diagnostic_reason_codes: isStringArray(payload.diagnostic_reason_codes)
      ? payload.diagnostic_reason_codes
      : [],
    ticker_specific: isBoolean(payload.ticker_specific) ? payload.ticker_specific : false,
    duplicate_group_id: nullableString(payload.duplicate_group_id),
    evidence_fact_group_id: nullableString(payload.evidence_fact_group_id),
    representative_claim_id: nullableString(payload.representative_claim_id),
    source_refs: isStringArray(payload.source_refs) ? payload.source_refs : [],
    source_agent_output_id: nullableString(payload.source_agent_output_id),
    claim_index: nullableNumber(payload.claim_index),
    display_rank: payload.display_rank,
  });
}

export function adaptCanonicalResearchResponse(payload: unknown): AdaptResult<CanonicalResearchResponse> {
  if (!isRecord(payload)) return fail("response is not an object");
  const { run_id, status } = payload;
  if (!isString(run_id) || !isString(status)) return fail("missing run_id/status");
  if (status !== "completed" && status !== "partial" && status !== "failed") {
    return fail("unexpected status value");
  }
  const artifacts = adaptArtifacts(payload.artifacts);
  if (!artifacts.ok) return fail("missing/invalid artifacts");

  let mainConflict: AlphaConflict | null = null;
  if (isRecord(payload.main_conflict)) {
    const adapted = adaptAlphaConflict(payload.main_conflict);
    if (adapted.ok) mainConflict = adapted.value;
  }

  const dominantAlphas = Array.isArray(payload.dominant_alphas)
    ? payload.dominant_alphas
        .map(adaptDominantAlpha)
        .filter((item): item is AdaptResult<DominantAlpha> & { ok: true } => item.ok)
        .map((item) => item.value)
    : [];

  // Data Sanity Cross-Check v1 additive fields -- strict, not lenient: an
  // unrecognized status/severity/field type is a contract mismatch that
  // rejects the whole response, never a silently-coerced fallback.
  const dataSanityStatus = payload.data_sanity_status;
  if (!isString(dataSanityStatus) || !DATA_SANITY_STATUS_SET.has(dataSanityStatus)) {
    return fail("unknown or missing data_sanity_status value");
  }
  if (!isNumber(payload.data_sanity_warning_count) || !isNumber(payload.data_sanity_critical_count)) {
    return fail("missing data_sanity_warning_count/data_sanity_critical_count");
  }
  if (!Array.isArray(payload.data_sanity_warnings)) {
    return fail("missing data_sanity_warnings array");
  }
  const dataSanityWarnings: DataSanityWarning[] = [];
  for (const raw of payload.data_sanity_warnings) {
    const adapted = adaptDataSanityWarning(raw);
    if (!adapted.ok) return fail(`invalid data sanity warning: ${adapted.reason}`);
    dataSanityWarnings.push(adapted.value);
  }
  const entityAlphaExposures: EntityAlphaExposureRecord[] = [];
  if (Array.isArray(payload.entity_alpha_exposures)) {
    for (const raw of payload.entity_alpha_exposures) {
      const adapted = adaptEntityAlphaExposureRecord(raw);
      if (adapted.ok) entityAlphaExposures.push(adapted.value);
    }
  }

  // Sprint 3 (Unclassified Findings Control), Track A3. Absent on a raw
  // payload predating this field -- `unclassified_findings_top20` etc.
  // are left undefined below rather than defaulted to an empty/"ready"
  // shape, so a historical caller can distinguish "field never existed"
  // from "computed, genuinely zero".
  let unclassifiedFindingsTop20: UnclassifiedFinding[] | undefined;
  if (Array.isArray(payload.unclassified_findings_top20)) {
    unclassifiedFindingsTop20 = [];
    for (const raw of payload.unclassified_findings_top20) {
      const adapted = adaptUnclassifiedFinding(raw);
      if (adapted.ok) unclassifiedFindingsTop20.push(adapted.value);
    }
  }
  const unclassifiedFindingsTotalCount =
    payload.unclassified_findings_total_count === null
      ? null
      : nullableNumber(payload.unclassified_findings_total_count);
  const unclassifiedFindingsReasonCounts = isRecord(payload.unclassified_findings_reason_counts)
    ? (payload.unclassified_findings_reason_counts as Record<string, number>)
    : undefined;
  const unclassifiedFindingsStatus =
    payload.unclassified_findings_status === "ready" || payload.unclassified_findings_status === "unavailable"
      ? payload.unclassified_findings_status
      : undefined;
  const unclassifiedFindingsDownloadAvailable = isBoolean(payload.unclassified_findings_download_available)
    ? payload.unclassified_findings_download_available
    : undefined;

  return ok({
    run_id,
    ticker: nullableString(payload.ticker),
    status,
    artifacts: artifacts.value,
    agent_output_count: isNumber(payload.agent_output_count) ? payload.agent_output_count : 0,
    structured_output_count: isNumber(payload.structured_output_count)
      ? payload.structured_output_count
      : 0,
    structure_graph_status: payload.structure_graph_status === "ready" ? "ready" : "not_ready",
    dominant_alphas: dominantAlphas,
    main_conflict: mainConflict,
    conflict_status: payload.conflict_status === "ready" ? "ready" : "not_ready",
    summary: isString(payload.summary) ? payload.summary : "",
    data_sanity_status: dataSanityStatus as DataSanityStatus,
    data_sanity_warning_count: payload.data_sanity_warning_count,
    data_sanity_critical_count: payload.data_sanity_critical_count,
    data_sanity_warnings: dataSanityWarnings,
    entity_alpha_exposures: entityAlphaExposures,
    entity_alpha_exposure_status:
      payload.entity_alpha_exposure_status === "ready" ? "ready" : "unavailable",
    unclassified_findings_top20: unclassifiedFindingsTop20,
    unclassified_findings_total_count: unclassifiedFindingsTotalCount,
    unclassified_findings_reason_counts: unclassifiedFindingsReasonCounts,
    unclassified_findings_status: unclassifiedFindingsStatus,
    unclassified_findings_download_available: unclassifiedFindingsDownloadAvailable,
  });
}

// ---------------------------------------------------------------------------
// Structure graph
// ---------------------------------------------------------------------------

function adaptStructureGraphNode(payload: unknown): AdaptResult<StructureGraphNode> {
  if (!isRecord(payload)) return fail("node is not an object");
  const { id, label } = payload;
  if (!isString(id) || !isString(label)) return fail("missing node id/label");
  return ok({
    id,
    node_type: isString(payload.node_type) ? payload.node_type : "factor",
    label,
    canonical_factor: isString(payload.canonical_factor) ? payload.canonical_factor : label,
    original_labels: isStringArray(payload.original_labels) ? payload.original_labels : [],
    alpha_ids: isStringArray(payload.alpha_ids) ? payload.alpha_ids : [],
    ambiguous_alpha_ids: isStringArray(payload.ambiguous_alpha_ids) ? payload.ambiguous_alpha_ids : [],
    score: isNumber(payload.score) ? payload.score : 0,
    claim_ids: isStringArray(payload.claim_ids) ? payload.claim_ids : [],
    source_agent_output_ids: isStringArray(payload.source_agent_output_ids)
      ? payload.source_agent_output_ids
      : [],
    agents: isStringArray(payload.agents) ? payload.agents : [],
    evidence: isStringArray(payload.evidence) ? payload.evidence : [],
  });
}

function adaptStructureGraphEdge(payload: unknown): AdaptResult<StructureGraphEdge> {
  if (!isRecord(payload)) return fail("edge is not an object");
  const { source, target, edge_type } = payload;
  if (!isString(source) || !isString(target) || !isString(edge_type)) {
    return fail("missing edge source/target/edge_type");
  }
  return ok({
    source,
    target,
    edge_type: edge_type as StructureGraphEdge["edge_type"],
    weight: isNumber(payload.weight) ? payload.weight : 0,
    assertion_status: isString(payload.assertion_status) ? payload.assertion_status : "unknown",
    alpha_ids: isStringArray(payload.alpha_ids) ? payload.alpha_ids : [],
    claim_ids: isStringArray(payload.claim_ids) ? payload.claim_ids : [],
    source_agent_output_ids: isStringArray(payload.source_agent_output_ids)
      ? payload.source_agent_output_ids
      : [],
    agents: isStringArray(payload.agents) ? payload.agents : [],
    evidence: isStringArray(payload.evidence) ? payload.evidence : [],
    extraction_methods: isStringArray(payload.extraction_methods) ? payload.extraction_methods : [],
    rule_names: isStringArray(payload.rule_names) ? payload.rule_names : [],
  });
}

function adaptAlphaEvidenceDetail(value: unknown): AlphaEvidenceDetail[] {
  if (!Array.isArray(value)) return [];
  return value
    .filter(isRecord)
    .filter((item) => isString(item.claim_id))
    .map((item) => ({
      claim_id: item.claim_id as string,
      claim: isString(item.claim) ? item.claim : "",
      agent: isString(item.agent) ? item.agent : "",
      source_agent_output_id: isString(item.source_agent_output_id)
        ? item.source_agent_output_id
        : "",
      match_score: isNumber(item.match_score) ? item.match_score : 0,
      relation: isString(item.relation) ? item.relation : "unknown",
      matched_keywords: isStringArray(item.matched_keywords) ? item.matched_keywords : [],
      matched_factors: isStringArray(item.matched_factors) ? item.matched_factors : [],
      assertion_status: isString(item.assertion_status) ? item.assertion_status : "unknown",
      direction: isString(item.direction) ? item.direction : "unknown",
    }));
}

function adaptEntityExposure(payload: unknown): AdaptResult<EntityExposure> {
  if (!isRecord(payload)) return fail("entity exposure is unavailable");
  const requiredNumbers = [
    payload.current_evidence,
    payload.agent_confidence,
    payload.unique_evidence_fact_count,
    payload.ticker_specific_fact_count,
    payload.distinct_supporting_agent_count,
  ];
  if (
    requiredNumbers.some((value) => !isNumber(value)) ||
    !isString(payload.seed_version) ||
    !isString(payload.seed_effective_date) ||
    !isString(payload.seed_approval_status) ||
    !isString(payload.mode) ||
    !isString(payload.exposure_status) ||
    typeof payload.would_block_dominant !== "boolean" ||
    typeof payload.would_block_regime_level !== "boolean" ||
    typeof payload.override_candidate !== "boolean" ||
    typeof payload.qualification_effect_applied !== "boolean" ||
    !isStringArray(payload.reason_codes)
  ) {
    return fail("invalid entity exposure fields");
  }
  if (
    payload.historical_mapping !== null &&
    !isNumber(payload.historical_mapping)
  ) {
    return fail("invalid historical mapping");
  }
  if (payload.final_exposure !== null && !isNumber(payload.final_exposure)) {
    return fail("invalid final exposure");
  }
  return ok({
    historical_mapping: payload.historical_mapping,
    current_evidence: payload.current_evidence as number,
    agent_confidence: payload.agent_confidence as number,
    final_exposure: payload.final_exposure,
    seed_version: payload.seed_version,
    seed_effective_date: payload.seed_effective_date,
    seed_approval_status: payload.seed_approval_status,
    mode: payload.mode as EntityExposure["mode"],
    exposure_status: payload.exposure_status as EntityExposure["exposure_status"],
    would_block_dominant: payload.would_block_dominant,
    would_block_regime_level: payload.would_block_regime_level,
    override_candidate: payload.override_candidate,
    qualification_effect_applied: payload.qualification_effect_applied,
    unique_evidence_fact_count: payload.unique_evidence_fact_count as number,
    ticker_specific_fact_count: payload.ticker_specific_fact_count as number,
    distinct_supporting_agent_count: payload.distinct_supporting_agent_count as number,
    reason_codes: payload.reason_codes,
  });
}

function adaptEntityAlphaExposureRecord(
  payload: unknown,
): AdaptResult<EntityAlphaExposureRecord> {
  if (!isRecord(payload)) return fail("entity exposure record is not an object");
  const exposure = adaptEntityExposure(payload);
  if (
    !exposure.ok ||
    !isString(payload.run_id) ||
    !isString(payload.ticker) ||
    !isString(payload.alpha_id)
  ) {
    return fail("invalid entity exposure record");
  }
  return ok({
    ...exposure.value,
    run_id: payload.run_id,
    ticker: payload.ticker,
    alpha_id: payload.alpha_id,
  });
}

function adaptAlphaActivation(payload: unknown): AdaptResult<AlphaActivation> {
  if (!isRecord(payload)) return fail("activation is not an object");
  const { alpha_id, alpha_name, activation_score, status, direction } = payload;
  if (!isString(alpha_id) || !isString(alpha_name) || !isNumber(activation_score) || !isString(status)) {
    return fail("missing alpha activation fields");
  }
  const exposure = adaptEntityExposure(payload.entity_exposure);
  return ok({
    alpha_id,
    alpha_name,
    activation_score,
    status: status as AlphaActivation["status"],
    direction: isString(direction) ? direction : "unknown",
    components: isRecord(payload.components) ? payload.components : {},
    evidence_count: isNumber(payload.evidence_count) ? payload.evidence_count : 0,
    distinct_supporting_agents: isNumber(payload.distinct_supporting_agents)
      ? payload.distinct_supporting_agents
      : 0,
    claim_ids: isStringArray(payload.claim_ids) ? payload.claim_ids : [],
    evidence: isStringArray(payload.evidence) ? payload.evidence : [],
    reason_codes: isStringArray(payload.reason_codes) ? payload.reason_codes : [],
    evidence_detail: adaptAlphaEvidenceDetail(payload.evidence_detail),
    // Activation v2 additive fields: null/empty on v1-legacy payloads.
    formula_version: nullableString(payload.formula_version),
    uncapped_score: nullableNumber(payload.uncapped_score),
    eligible_cap: nullableNumber(payload.eligible_cap),
    cap_was_binding:
      typeof payload.cap_was_binding === "boolean" ? payload.cap_was_binding : null,
    cap_reason_codes: isStringArray(payload.cap_reason_codes) ? payload.cap_reason_codes : [],
    binding_cap_reason_codes: isStringArray(payload.binding_cap_reason_codes)
      ? payload.binding_cap_reason_codes
      : [],
    unique_evidence_count: nullableNumber(payload.unique_evidence_count),
    ticker_specific_evidence_count: nullableNumber(payload.ticker_specific_evidence_count),
    local_edge_count: nullableNumber(payload.local_edge_count),
    regime_gate_passed:
      typeof payload.regime_gate_passed === "boolean" ? payload.regime_gate_passed : null,
    regime_gate_failures: isStringArray(payload.regime_gate_failures)
      ? payload.regime_gate_failures
      : [],
    entity_exposure: exposure.ok ? exposure.value : null,
  });
}

function adaptGraphActivation(payload: unknown): AdaptResult<GraphActivation> {
  if (!isRecord(payload)) return fail("activation block is not an object");
  if (!Array.isArray(payload.alphas)) return fail("missing activation.alphas");
  const alphas: AlphaActivation[] = [];
  for (const raw of payload.alphas) {
    const adapted = adaptAlphaActivation(raw);
    if (!adapted.ok) return fail(`invalid alpha activation: ${adapted.reason}`);
    alphas.push(adapted.value);
  }
  return ok({
    formula_version: isString(payload.formula_version) ? payload.formula_version : "",
    weights: isRecord(payload.weights) ? (payload.weights as Record<string, number>) : {},
    run_timestamp: nullableString(payload.run_timestamp),
    as_of: nullableString(payload.as_of),
    alphas,
  });
}

export function adaptStructureGraphResponse(payload: unknown): AdaptResult<StructureGraphResponse> {
  if (!isRecord(payload)) return fail("response is not an object");
  const { run_id, schema_version } = payload;
  if (!isString(run_id) || !isString(schema_version)) return fail("missing run_id/schema_version");
  if (!Array.isArray(payload.nodes) || !Array.isArray(payload.edges)) {
    return fail("missing nodes/edges");
  }

  const nodes: StructureGraphNode[] = [];
  for (const raw of payload.nodes) {
    const adapted = adaptStructureGraphNode(raw);
    if (!adapted.ok) return fail(`invalid node: ${adapted.reason}`);
    nodes.push(adapted.value);
  }
  const edges: StructureGraphEdge[] = [];
  for (const raw of payload.edges) {
    const adapted = adaptStructureGraphEdge(raw);
    if (!adapted.ok) return fail(`invalid edge: ${adapted.reason}`);
    edges.push(adapted.value);
  }
  const activation = adaptGraphActivation(payload.activation);
  if (!activation.ok) return fail(`invalid activation: ${activation.reason}`);

  // Versioned activation blocks are additive: absent on historical v1-only
  // graphs. A block that fails to adapt is dropped rather than failing the
  // whole response.
  const activationVersions: Partial<Record<"v1" | "v2", GraphActivation>> = {};
  if (isRecord(payload.activation_versions)) {
    for (const key of ["v1", "v2"] as const) {
      const raw = payload.activation_versions[key];
      if (raw === undefined) continue;
      const adapted = adaptGraphActivation(raw);
      if (adapted.ok) activationVersions[key] = adapted.value;
    }
  }

  const dominantAlphas = Array.isArray(payload.dominant_alphas)
    ? payload.dominant_alphas
        .map(adaptDominantAlpha)
        .filter((item): item is AdaptResult<DominantAlpha> & { ok: true } => item.ok)
        .map((item) => item.value)
    : [];

  return ok({
    run_id,
    ticker: nullableString(payload.ticker),
    status: "ok",
    schema_version,
    graph_builder_version: optionalString(payload.graph_builder_version) ?? "",
    activation_scorer_version: optionalString(payload.activation_scorer_version) ?? "",
    nodes,
    edges,
    graph_metrics: isRecord(payload.graph_metrics) ? payload.graph_metrics : {},
    graph_coherence: isRecord(payload.graph_coherence) ? payload.graph_coherence : {},
    activation: activation.value,
    activation_versions: activationVersions,
    primary_activation_version: nullableString(payload.primary_activation_version),
    dominant_alphas: dominantAlphas,
    provenance: isRecord(payload.provenance) ? payload.provenance : {},
  });
}

// ---------------------------------------------------------------------------
// Conflicts
// ---------------------------------------------------------------------------

function adaptConflictAuditSide(payload: unknown): AdaptResult<ConflictAuditSide> {
  if (!isRecord(payload)) return fail("audit side is not an object");
  const { alpha_id } = payload;
  if (!isString(alpha_id)) return fail("missing audit alpha_id");
  return ok({
    alpha_id,
    qualifying_claim_ids: isStringArray(payload.qualifying_claim_ids) ? payload.qualifying_claim_ids : [],
    qualifying_count: isNumber(payload.qualifying_count) ? payload.qualifying_count : 0,
    excluded: Array.isArray(payload.excluded)
      ? payload.excluded.filter((item): item is Record<string, unknown> => isRecord(item))
      : [],
  });
}

function adaptConflictCandidateEvaluation(payload: unknown): AdaptResult<ConflictCandidateEvaluation> {
  if (!isRecord(payload)) return fail("candidate is not an object");
  const { alpha_a, alpha_b, outcome } = payload;
  if (
    !isString(alpha_a) ||
    !isString(alpha_b) ||
    (outcome !== "admitted" && outcome !== "suppressed" && outcome !== "rejected")
  ) {
    return fail("missing candidate fields");
  }
  const audit = isRecord(payload.evidence_audit) ? payload.evidence_audit : {};
  const auditA = adaptConflictAuditSide(audit.alpha_a);
  const auditB = adaptConflictAuditSide(audit.alpha_b);
  if (!auditA.ok || !auditB.ok) return fail("invalid evidence_audit");
  const admissibility = adaptConflictAdmissibility(payload.admissibility);
  const evidenceUi = adaptConflictEvidenceUI(payload.evidence_ui);
  return ok({
    alpha_a,
    alpha_b,
    outcome,
    reason_codes: isStringArray(payload.reason_codes) ? payload.reason_codes : [],
    evidence_audit: { alpha_a: auditA.value, alpha_b: auditB.value },
    // Only present once bull/bear roles were actually resolved for this
    // pair (task B5_CONFLICT_RADAR_EVIDENCE_UI) -- absent together with
    // admissibility/evidence_ui for a pair rejected before B2 evaluation.
    ...(isString(payload.bull_alpha_id) ? { bull_alpha_id: payload.bull_alpha_id } : {}),
    ...(isString(payload.bear_alpha_id) ? { bear_alpha_id: payload.bear_alpha_id } : {}),
    ...(admissibility ? { admissibility } : {}),
    ...(evidenceUi ? { evidence_ui: evidenceUi } : {}),
  });
}

export function adaptConflictsResponse(payload: unknown): AdaptResult<ConflictsResponse> {
  if (!isRecord(payload)) return fail("response is not an object");
  const { run_id, ticker, schema_version, formula_version } = payload;
  if (!isString(run_id) || !isString(ticker) || !isString(schema_version) || !isString(formula_version)) {
    return fail("missing top-level conflicts fields");
  }
  if (!Array.isArray(payload.conflicts)) return fail("missing conflicts array");

  const conflicts: AlphaConflict[] = [];
  for (const raw of payload.conflicts) {
    const adapted = adaptAlphaConflict(raw);
    if (!adapted.ok) return fail(`invalid conflict: ${adapted.reason}`);
    conflicts.push(adapted.value);
  }

  let mainConflict: AlphaConflict | null = null;
  if (isRecord(payload.main_conflict)) {
    const adapted = adaptAlphaConflict(payload.main_conflict);
    if (!adapted.ok) return fail(`invalid main_conflict: ${adapted.reason}`);
    mainConflict = adapted.value;
  }

  const arbitrationRaw = isRecord(payload.arbitration) ? payload.arbitration : {};
  const candidateEvaluations: ConflictCandidateEvaluation[] = [];
  if (Array.isArray(arbitrationRaw.candidate_evaluations)) {
    for (const raw of arbitrationRaw.candidate_evaluations) {
      const adapted = adaptConflictCandidateEvaluation(raw);
      if (adapted.ok) candidateEvaluations.push(adapted.value);
    }
  }

  return ok({
    status: "ok",
    schema_version,
    formula_version,
    activation_formula_version: nullableString(payload.activation_formula_version),
    run_id,
    ticker,
    conflicts,
    main_conflict: mainConflict,
    arbitration: {
      declared_pair_count: isNumber(arbitrationRaw.declared_pair_count)
        ? arbitrationRaw.declared_pair_count
        : 0,
      admitted_count: isNumber(arbitrationRaw.admitted_count) ? arbitrationRaw.admitted_count : 0,
      suppressed_count: isNumber(arbitrationRaw.suppressed_count) ? arbitrationRaw.suppressed_count : 0,
      rejected_count: isNumber(arbitrationRaw.rejected_count) ? arbitrationRaw.rejected_count : 0,
      candidate_evaluations: candidateEvaluations,
    },
  });
}

// ---------------------------------------------------------------------------
// Agent outputs
// ---------------------------------------------------------------------------

function adaptStructuredAgentOutputRecord(payload: unknown): AdaptResult<StructuredAgentOutputRecord> {
  if (!isRecord(payload)) return fail("record is not an object");
  const { claim_id, source_agent_output_id, run_id, ticker, agent, claim, evidence, direction } = payload;
  if (
    !isString(claim_id) ||
    !isString(source_agent_output_id) ||
    !isString(run_id) ||
    !isString(ticker) ||
    !isString(agent) ||
    !isString(claim) ||
    !isString(evidence) ||
    !isString(direction)
  ) {
    return fail("missing required structured output fields");
  }
  const record: StructuredAgentOutputRecord = {
    claim_id,
    source_agent_output_id,
    run_id,
    ticker,
    agent,
    claim,
    evidence,
    entities: isStringArray(payload.entities) ? payload.entities : [],
    factors: isStringArray(payload.factors) ? payload.factors : [],
    direction,
    confidence: isNumber(payload.confidence) ? payload.confidence : 0,
  };
  if (isString(payload.agent_output_id)) record.agent_output_id = payload.agent_output_id;
  if (isString(payload.timestamp)) record.timestamp = payload.timestamp;
  if (isString(payload.source_type)) record.source_type = payload.source_type;
  if (isString(payload.output_type)) record.output_type = payload.output_type;
  if (isStringArray(payload.source_refs)) record.source_refs = payload.source_refs;
  if (isNumber(payload.claim_index)) record.claim_index = payload.claim_index;
  if (isString(payload.source_section)) record.source_section = payload.source_section;
  if (isString(payload.assertion_status)) record.assertion_status = payload.assertion_status;
  if (isString(payload.semantic_polarity)) record.semantic_polarity = payload.semantic_polarity;
  if (isString(payload.extraction_method)) record.extraction_method = payload.extraction_method;
  return ok(record);
}

export function adaptAgentOutputsResponse(payload: unknown): AdaptResult<AgentOutputsResponse> {
  if (!isRecord(payload)) return fail("response is not an object");
  const { run_id, ticker, schema_version } = payload;
  if (!isString(run_id) || !isString(ticker) || !isString(schema_version)) {
    return fail("missing run_id/ticker/schema_version");
  }
  if (!Array.isArray(payload.structured_agent_outputs)) return fail("missing structured_agent_outputs");

  const records: StructuredAgentOutputRecord[] = [];
  for (const raw of payload.structured_agent_outputs) {
    const adapted = adaptStructuredAgentOutputRecord(raw);
    if (!adapted.ok) return fail(`invalid structured output record: ${adapted.reason}`);
    records.push(adapted.value);
  }

  return ok({
    run_id,
    ticker,
    status: "ok",
    schema_version,
    structured_agent_outputs: records,
    count: isNumber(payload.count) ? payload.count : records.length,
  });
}

// ---------------------------------------------------------------------------
// Health / readiness
// ---------------------------------------------------------------------------

function adaptReplayAllRunResult(value: unknown): AdaptResult<ReplayAllRunResult> {
  if (!isRecord(value)) return fail("run result is not an object");
  if (!isString(value.source_run_id)) return fail("missing source_run_id");
  if (value.status !== "completed" && value.status !== "blocked" && value.status !== "failed") {
    return fail("unexpected run status");
  }
  return ok({
    source_run_id: value.source_run_id,
    ticker: nullableString(value.ticker),
    replay_run_id: nullableString(value.replay_run_id),
    status: value.status,
    output_dir: nullableString(value.output_dir),
    error_code: nullableString(value.error_code),
  });
}

export function adaptReplayAllResult(payload: unknown): AdaptResult<ReplayAllResult> {
  if (!isRecord(payload)) return fail("response is not an object");
  if (payload.status !== "completed") return fail("unexpected batch status");
  if (!isNumber(payload.total_runs_found)) return fail("missing total_runs_found");
  if (!Array.isArray(payload.results)) return fail("missing results array");

  const results: ReplayAllRunResult[] = [];
  for (const item of payload.results) {
    const adapted = adaptReplayAllRunResult(item);
    if (!adapted.ok) return fail(adapted.reason);
    results.push(adapted.value);
  }

  return ok({
    status: "completed",
    total_runs_found: payload.total_runs_found,
    completed_count: isNumber(payload.completed_count) ? payload.completed_count : 0,
    blocked_count: isNumber(payload.blocked_count) ? payload.blocked_count : 0,
    failed_count: isNumber(payload.failed_count) ? payload.failed_count : 0,
    results,
    provider_calls: isNumber(payload.provider_calls) ? payload.provider_calls : 0,
    tradingagents_calls: isNumber(payload.tradingagents_calls) ? payload.tradingagents_calls : 0,
  });
}

export function adaptHealthResponse(payload: unknown): AdaptResult<HealthResponse> {
  if (!isRecord(payload) || payload.status !== "ok") return fail("unexpected health payload");
  return ok({ status: "ok" });
}

export function adaptReadinessResponse(payload: unknown): AdaptResult<ReadinessResponse> {
  if (!isRecord(payload)) return fail("response is not an object");
  const { status, database, job_manager, real_execution } = payload;
  if (
    (status !== "ready" && status !== "not_ready") ||
    (database !== "ready" && database !== "unavailable") ||
    (job_manager !== "ready" && job_manager !== "unavailable") ||
    (real_execution !== "disabled" && real_execution !== "configured" && real_execution !== "misconfigured")
  ) {
    return fail("unexpected readiness payload shape");
  }
  return ok({
    status,
    database,
    job_manager,
    real_execution,
    real_execution_reason: nullableString(payload.real_execution_reason),
  });
}
