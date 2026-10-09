/**
 * T1 closure -- the claim-level evidence trace (GET /api/research/{run_id}/evidence-trace).
 *
 * For one claim: the saved source material it rests on and where in it, how that material was verified, which Alpha
 * the claim was matched to, what its stance/relation is and who decided it, and what it contributed to the
 * official score -- as four SEPARATE statuses. Every field is copied explicitly (an adapter that silently drops a
 * field means the UI never shows it, however the type reads); unknown extra fields are ignored, required ones are
 * checked.
 */

import type { SafeErrorEnvelope } from "./types";

export type TraceAdaptResult<T> = { ok: true; value: T } | { ok: false; reason: string };

function isRecord(value: unknown): value is Record<string, unknown> {
  return typeof value === "object" && value !== null && !Array.isArray(value);
}
const str = (value: unknown): string | null => (typeof value === "string" ? value : null);
const num = (value: unknown): number | null => (typeof value === "number" && Number.isFinite(value) ? value : null);
const bool = (value: unknown): boolean => value === true;
const strList = (value: unknown): string[] =>
  Array.isArray(value) ? value.filter((item): item is string => typeof item === "string") : [];
const rec = (value: unknown): Record<string, unknown> => (isRecord(value) ? value : {});
const list = (value: unknown): unknown[] => (Array.isArray(value) ? value : []);

export interface TraceStatus {
  status_code: string;
  label: string;
  reason: string;
}

export interface TraceTimeBasis {
  basis: string;
  value: string | null;
  note: string | null;
}

export interface TraceMaterialCell {
  period: string | null;
  value: number;
  used: boolean;
  token: string | null;
}

export interface TraceMaterialRow {
  label: string;
  kind: string;
  unit: string | null;
  cells: TraceMaterialCell[];
}

export interface TraceDerivedInputs {
  /** SAVED: the complete input window was saved with the run; NOT_SAVED: only method/version/window parameters survive. */
  status: string;
  method: string | null;
  version: string | null;
  row_count: number | null;
  first_date: string | null;
  last_date: string | null;
  series_hash_ok: boolean | null;
  registry_pointer_matches: boolean | null;
  recomputation_status: string | null;
  recomputation_indicators_checked: number | null;
  recomputation_mismatched: string[];
  note: string | null;
}

export interface TraceSource {
  source_id: string;
  role: string;
  resolved: boolean;
  source_type: string | null;
  title: string | null;
  name: string | null;
  provider: string | null;
  instrument: string | null;
  url: string | null;
  observation_date: string | null;
  published_at: string | null;
  retrieved_at: string | null;
  unit: string | null;
  fragment_id: string | null;
  content_hash: string | null;
  time_basis: TraceTimeBasis | null;
  excerpt_text: string | null;
  excerpt_length: number | null;
  excerpt_truncated: boolean;
  has_saved_content: boolean;
  material_rows: TraceMaterialRow[];
  derived_inputs: TraceDerivedInputs | null;
}

export interface TraceContentSupport {
  status: string | null;
  method: string | null;
  task_version: string | null;
  support_basis: string | null;
  core_proposition: string | null;
  used_source_id: string | null;
  used_location: string | null;
  supporting_quote_or_data: string | null;
  rationale: string | null;
  unsupported_remainder: string | null;
  unsupported_materiality: string | null;
  fallback_reason: string | null;
}

export interface TraceSourceSupport extends TraceStatus {
  /** Set (RUN_PREDATES_SOURCE_LINKING) when the run's records carry no source-link fields at all. */
  reason_code: string | null;
  link_status: string | null;
  link_method: string | null;
  content_support: TraceContentSupport;
  eligible: boolean;
  eligibility_reason_code: string | null;
  eligibility_time_basis: TraceTimeBasis | null;
}

export interface TraceAlphaMatch extends TraceStatus {
  match_status: string | null;
  matched_alpha: string | null;
  llm_selected_alpha_id: string | null;
  alpha_match_method: string | null;
  mapper_override: string | null;
}

export interface TraceStance extends TraceStatus {
  evidence_stance: string | null;
  method: string | null;
  relation: string | null;
  assertion_status: string | null;
  relation_basis: string | null;
  target_alpha_id: string | null;
}

export interface TraceFactGroup {
  id: string | null;
  member_claim_ids: string[];
  supporting_agents: string[];
  source_role: string | null;
  qualification_reason: string | null;
}

export interface TraceAlphaResult {
  score: number | null;
  level: string | null;
  claims_in_pool: number | null;
  independent_facts: number | null;
  distinct_agents: number | null;
  distinct_sources: number | null;
}

export interface TraceScoring extends TraceStatus {
  in_official_pool: boolean;
  alpha_id: string | null;
  weight_contribution: number | null;
  match_score_lexical: number | null;
  not_scored_code: string | null;
  fact_group: TraceFactGroup | null;
  alpha_result: TraceAlphaResult | null;
}

export interface TraceDataPoint {
  source_id: string;
  label: string;
  period: string | null;
  value: number;
  unit: string | null;
  token: string;
  role: string;
}

export interface TraceDerivedCalculation {
  calc_id: string;
  metric: string;
  formula: string;
  inputs: TraceDataPoint[];
  computed: number;
  stated: number;
  stated_token: string;
  unit: string;
  comparison: string | null;
  status: string;
  scope_note: string;
}

export interface TraceDependency {
  contract: string | null;
  same_evidence_fact_members: string[];
  depends_on: string | null;
  depended_by: string[];
  shares_inputs_with: string[];
  note: string | null;
}

export interface TraceAgentWording {
  self_labeled_verified: boolean;
  matched_terms: string[];
  note: string | null;
}

export interface TraceClaim {
  text: string;
  evidence_text: string | null;
  agent: string;
  claim_quality: string | null;
  section: string | null;
  claim_index: number | null;
  char_offset: number | null;
  paragraph: string | null;
  agent_wording: TraceAgentWording;
}

/** One saved placement of a claim in a conflict of the run -- read from the run's own conflicts.json, never re-evaluated. */
export interface TraceConflictAdoptionEntry {
  conflict_id: string;
  side: string;
  target_alpha_id: string | null;
  counter_target_alpha_id: string | null;
  is_representative: boolean;
  conflict_status: string | null;
  conflict_level: string | null;
  conflict_score: number | null;
  is_main_conflict: boolean;
}

export interface TraceConflictAdoption {
  entries: TraceConflictAdoptionEntry[];
  note: string | null;
}

export interface TraceRunBasis {
  /** False when the run was saved before source linking existed (its records carry no source-link fields). */
  link_fields_saved: boolean;
  note: string | null;
}

export interface EvidenceTraceItem {
  claim_id: string;
  claim: TraceClaim;
  sources: TraceSource[];
  source_support: TraceSourceSupport;
  alpha_match: TraceAlphaMatch;
  stance: TraceStance;
  scoring: TraceScoring;
  data_points: TraceDataPoint[];
  derived_calculations: TraceDerivedCalculation[];
  unreproduced_percent_tokens: string[];
  numbers_not_found_in_saved_data: string[];
  calculation_note: string | null;
  dependency: TraceDependency;
  conflict_adoption: TraceConflictAdoption;
  run_basis: TraceRunBasis;
  note: string | null;
}

export interface KeyConclusionRow {
  claim_id: string;
  text: string;
  agent: string;
  section: string | null;
  claim_index: number | null;
  claim_quality: string | null;
  agent_wording: TraceAgentWording;
  source_support: TraceStatus;
  alpha_match: TraceStatus & { matched_alpha: string | null };
  stance: TraceStatus & { evidence_stance: string | null; method: string | null; relation: string | null };
  scoring: TraceStatus & { alpha_id: string | null; weight_contribution: number | null; not_scored_code: string | null };
}

export interface KeyConclusionGroup {
  group: string;
  rows: KeyConclusionRow[];
}

export interface KeyConclusionsView {
  rule: string;
  claim_count: number;
  agent_wording_verified_count: number;
  status_counts: Record<string, Record<string, number>>;
  groups: KeyConclusionGroup[];
}

export interface EvidenceTraceItemResponse {
  run_id: string;
  ticker: string | null;
  status: "ok";
  item: EvidenceTraceItem;
}

export interface KeyConclusionsResponse {
  run_id: string;
  ticker: string | null;
  status: "ok";
  key_conclusions: KeyConclusionsView;
}

export type EvidenceTraceItemResult = EvidenceTraceItemResponse | SafeErrorEnvelope;
export type KeyConclusionsResult = KeyConclusionsResponse | SafeErrorEnvelope;

function adaptStatus(raw: unknown): TraceStatus | null {
  const r = rec(raw);
  const status_code = str(r.status_code);
  const label = str(r.label);
  const reason = str(r.reason);
  return status_code && label && reason !== null ? { status_code, label, reason } : null;
}

function adaptTimeBasis(raw: unknown): TraceTimeBasis | null {
  const r = rec(raw);
  const basis = str(r.basis);
  return basis ? { basis, value: str(r.value), note: str(r.note) } : null;
}

function adaptWording(raw: unknown): TraceAgentWording {
  const r = rec(raw);
  return { self_labeled_verified: bool(r.self_labeled_verified), matched_terms: strList(r.matched_terms), note: str(r.note) };
}

function adaptDataPoint(raw: unknown): TraceDataPoint | null {
  const r = rec(raw);
  const source_id = str(r.source_id);
  const label = str(r.label);
  const value = num(r.value);
  if (!source_id || !label || value === null) return null;
  return { source_id, label, period: str(r.period), value, unit: str(r.unit), token: str(r.token) ?? "", role: str(r.role) ?? "stated" };
}

function adaptSource(raw: unknown): TraceSource | null {
  const r = rec(raw);
  const source_id = str(r.source_id);
  if (!source_id) return null;
  const excerpt = rec(r.excerpt);
  const rows: TraceMaterialRow[] = [];
  for (const rowRaw of list(r.material_rows)) {
    const row = rec(rowRaw);
    const label = str(row.label);
    if (!label) continue;
    const cells: TraceMaterialCell[] = [];
    for (const cellRaw of list(row.cells)) {
      const cell = rec(cellRaw);
      const value = num(cell.value);
      if (value === null) continue;
      cells.push({ period: str(cell.period), value, used: bool(cell.used), token: str(cell.token) });
    }
    rows.push({ label, kind: str(row.kind) ?? "", unit: str(row.unit), cells });
  }
  return {
    source_id,
    role: str(r.role) ?? "cited",
    resolved: r.resolved !== false,
    source_type: str(r.source_type),
    title: str(r.title),
    name: str(r.name),
    provider: str(r.provider),
    instrument: str(r.instrument),
    url: str(r.url),
    observation_date: str(r.observation_date),
    published_at: str(r.published_at),
    retrieved_at: str(r.retrieved_at),
    unit: str(r.unit),
    fragment_id: str(r.fragment_id),
    content_hash: str(r.content_hash),
    time_basis: adaptTimeBasis(r.time_basis),
    excerpt_text: str(excerpt.text),
    excerpt_length: num(excerpt.length),
    excerpt_truncated: bool(excerpt.truncated),
    has_saved_content: bool(r.has_saved_content),
    material_rows: rows,
    derived_inputs: adaptDerivedInputs(r.derived_inputs),
  };
}

function adaptDerivedInputs(raw: unknown): TraceDerivedInputs | null {
  if (!isRecord(raw)) return null;
  const status = str(raw.status);
  if (!status) return null;
  const recomputation = rec(raw.recomputation);
  const params = rec(raw.window_parameters);
  return {
    status,
    method: str(raw.method),
    version: str(raw.version),
    row_count: num(raw.row_count) ?? num(params.row_count),
    first_date: str(raw.first_date) ?? str(params.window_start),
    last_date: str(raw.last_date) ?? str(params.window_end),
    series_hash_ok: typeof raw.series_hash_ok === "boolean" ? raw.series_hash_ok : null,
    registry_pointer_matches: typeof raw.registry_pointer_matches === "boolean" ? raw.registry_pointer_matches : null,
    recomputation_status: str(recomputation.status),
    recomputation_indicators_checked: num(recomputation.indicators_checked),
    recomputation_mismatched: strList(recomputation.mismatched),
    note: str(raw.note),
  };
}

function adaptConflictAdoption(raw: unknown): TraceConflictAdoption {
  const r = rec(raw);
  const entries: TraceConflictAdoptionEntry[] = [];
  for (const entryRaw of list(r.entries)) {
    const e = rec(entryRaw);
    const conflict_id = str(e.conflict_id);
    const side = str(e.side);
    if (!conflict_id || !side) continue;
    entries.push({
      conflict_id,
      side,
      target_alpha_id: str(e.target_alpha_id),
      counter_target_alpha_id: str(e.counter_target_alpha_id),
      is_representative: bool(e.is_representative),
      conflict_status: str(e.conflict_status),
      conflict_level: str(e.conflict_level),
      conflict_score: num(e.conflict_score),
      is_main_conflict: bool(e.is_main_conflict),
    });
  }
  return { entries, note: str(r.note) };
}

function adaptCalculation(raw: unknown): TraceDerivedCalculation | null {
  const r = rec(raw);
  const calc_id = str(r.calc_id);
  const computed = num(r.computed);
  const stated = num(r.stated);
  if (!calc_id || computed === null || stated === null) return null;
  const inputs: TraceDataPoint[] = [];
  for (const inputRaw of list(r.inputs)) {
    const point = adaptDataPoint(inputRaw);
    if (point) inputs.push(point);
  }
  return {
    calc_id,
    metric: str(r.metric) ?? "",
    formula: str(r.formula) ?? "",
    inputs,
    computed,
    stated,
    stated_token: str(r.stated_token) ?? "",
    unit: str(r.unit) ?? "",
    comparison: str(r.comparison),
    status: str(r.status) ?? "REPRODUCED",
    scope_note: str(r.scope_note) ?? "",
  };
}

export function adaptEvidenceTraceItem(raw: unknown): TraceAdaptResult<EvidenceTraceItem> {
  const r = rec(raw);
  const claim_id = str(r.claim_id);
  if (!claim_id) return { ok: false, reason: "trace item has no claim_id" };
  const claimRaw = rec(r.claim);
  const location = rec(claimRaw.report_location);
  const text = str(claimRaw.text);
  if (text === null) return { ok: false, reason: "trace item has no claim text" };

  const support = adaptStatus(r.source_support);
  const match = adaptStatus(r.alpha_match);
  const stance = adaptStatus(r.stance);
  const scoring = adaptStatus(r.scoring);
  if (!support || !match || !stance || !scoring) return { ok: false, reason: "trace item is missing one of the four statuses" };

  const ss = rec(r.source_support);
  const link = rec(ss.link);
  const cs = rec(ss.content_support);
  const elig = rec(ss.eligibility);
  const am = rec(r.alpha_match);
  const st = rec(r.stance);
  const sc = rec(r.scoring);
  const group = sc.fact_group === undefined || sc.fact_group === null ? null : rec(sc.fact_group);
  const role = group ? rec(group.role) : {};
  const result = sc.alpha_result === undefined || sc.alpha_result === null ? null : rec(sc.alpha_result);
  const calc = rec(r.calculation);
  const dep = rec(r.dependency);

  const sources: TraceSource[] = [];
  for (const sourceRaw of list(r.sources)) {
    const source = adaptSource(sourceRaw);
    if (source) sources.push(source);
  }
  const dataPoints: TraceDataPoint[] = [];
  for (const pointRaw of list(calc.data_points)) {
    const point = adaptDataPoint(pointRaw);
    if (point) dataPoints.push(point);
  }
  const calculations: TraceDerivedCalculation[] = [];
  for (const calcRaw of list(calc.derived_calculations)) {
    const calculation = adaptCalculation(calcRaw);
    if (calculation) calculations.push(calculation);
  }

  return {
    ok: true,
    value: {
      claim_id,
      claim: {
        text,
        evidence_text: str(claimRaw.evidence_text),
        agent: str(claimRaw.agent) ?? "unknown",
        claim_quality: str(claimRaw.claim_quality),
        section: str(location.section),
        claim_index: num(location.claim_index),
        char_offset: num(location.char_offset),
        paragraph: str(location.paragraph),
        agent_wording: adaptWording(claimRaw.agent_wording),
      },
      sources,
      source_support: {
        ...support,
        reason_code: str(ss.reason_code),
        link_status: str(link.status),
        link_method: str(link.method),
        content_support: {
          status: str(cs.status),
          method: str(cs.method),
          task_version: str(cs.task_version),
          support_basis: str(cs.support_basis),
          core_proposition: str(cs.core_proposition),
          used_source_id: str(cs.used_source_id),
          used_location: str(cs.used_location),
          supporting_quote_or_data: str(cs.supporting_quote_or_data),
          rationale: str(cs.rationale),
          unsupported_remainder: str(cs.unsupported_remainder),
          unsupported_materiality: str(cs.unsupported_materiality),
          fallback_reason: str(cs.fallback_reason),
        },
        eligible: bool(elig.eligible),
        eligibility_reason_code: str(elig.reason_code),
        eligibility_time_basis: adaptTimeBasis(elig.time_basis),
      },
      alpha_match: {
        ...match,
        match_status: str(am.match_status),
        matched_alpha: str(am.matched_alpha),
        llm_selected_alpha_id: str(am.llm_selected_alpha_id),
        alpha_match_method: str(am.alpha_match_method),
        mapper_override: str(am.mapper_override),
      },
      stance: {
        ...stance,
        evidence_stance: str(st.evidence_stance),
        method: str(st.method),
        relation: str(st.relation),
        assertion_status: str(st.assertion_status),
        relation_basis: str(st.relation_basis),
        target_alpha_id: str(st.target_alpha_id),
      },
      scoring: {
        ...scoring,
        in_official_pool: bool(sc.in_official_pool),
        alpha_id: str(sc.alpha_id),
        weight_contribution: num(sc.weight_contribution),
        match_score_lexical: num(sc.match_score_lexical),
        not_scored_code: str(sc.not_scored_code),
        fact_group: group
          ? {
              id: str(group.id),
              member_claim_ids: strList(group.member_claim_ids),
              supporting_agents: strList(group.supporting_agents),
              source_role: str(role.source_role),
              qualification_reason: str(role.activation_qualification_reason),
            }
          : null,
        alpha_result: result
          ? {
              score: num(result.score),
              level: str(result.level),
              claims_in_pool: num(result.claims_in_pool),
              independent_facts: num(result.independent_facts),
              distinct_agents: num(result.distinct_agents),
              distinct_sources: num(result.distinct_sources),
            }
          : null,
      },
      data_points: dataPoints,
      derived_calculations: calculations,
      unreproduced_percent_tokens: strList(calc.unreproduced_percent_tokens),
      numbers_not_found_in_saved_data: strList(calc.numbers_not_found_in_saved_data),
      calculation_note: str(calc.scope_note),
      conflict_adoption: adaptConflictAdoption(r.conflict_adoption),
      run_basis: { link_fields_saved: rec(r.run_basis).link_fields_saved !== false, note: str(rec(r.run_basis).note) },
      dependency: {
        contract: str(dep.contract),
        same_evidence_fact_members: strList(dep.same_evidence_fact_members),
        depends_on: str(dep.depends_on),
        depended_by: strList(dep.depended_by),
        shares_inputs_with: strList(dep.shares_inputs_with),
        note: str(dep.note),
      },
      note: str(r.note),
    },
  };
}

export function adaptEvidenceTraceItemResponse(payload: unknown): TraceAdaptResult<EvidenceTraceItemResponse> {
  const p = rec(payload);
  const run_id = str(p.run_id);
  if (!run_id) return { ok: false, reason: "missing run_id" };
  const item = adaptEvidenceTraceItem(p.item);
  if (!item.ok) return item;
  return { ok: true, value: { run_id, ticker: str(p.ticker), status: "ok", item: item.value } };
}

function adaptKeyRow(raw: unknown): KeyConclusionRow | null {
  const r = rec(raw);
  const claim_id = str(r.claim_id);
  const text = str(r.text);
  const support = adaptStatus(r.source_support);
  const match = adaptStatus(r.alpha_match);
  const stance = adaptStatus(r.stance);
  const scoring = adaptStatus(r.scoring);
  if (!claim_id || text === null || !support || !match || !stance || !scoring) return null;
  const am = rec(r.alpha_match);
  const st = rec(r.stance);
  const sc = rec(r.scoring);
  return {
    claim_id,
    text,
    agent: str(r.agent) ?? "unknown",
    section: str(r.section),
    claim_index: num(r.claim_index),
    claim_quality: str(r.claim_quality),
    agent_wording: adaptWording(r.agent_wording),
    source_support: support,
    alpha_match: { ...match, matched_alpha: str(am.matched_alpha) },
    stance: { ...stance, evidence_stance: str(st.evidence_stance), method: str(st.method), relation: str(st.relation) },
    scoring: { ...scoring, alpha_id: str(sc.alpha_id), weight_contribution: num(sc.weight_contribution), not_scored_code: str(sc.not_scored_code) },
  };
}

export function adaptKeyConclusionsResponse(payload: unknown): TraceAdaptResult<KeyConclusionsResponse> {
  const p = rec(payload);
  const run_id = str(p.run_id);
  if (!run_id) return { ok: false, reason: "missing run_id" };
  const k = rec(p.key_conclusions);
  const groups: KeyConclusionGroup[] = [];
  for (const groupRaw of list(k.groups)) {
    const g = rec(groupRaw);
    const group = str(g.group);
    if (!group) continue;
    const rows: KeyConclusionRow[] = [];
    for (const rowRaw of list(g.rows)) {
      const row = adaptKeyRow(rowRaw);
      if (row) rows.push(row);
    }
    groups.push({ group, rows });
  }
  const counts: Record<string, Record<string, number>> = {};
  for (const [dimension, codes] of Object.entries(rec(k.status_counts))) {
    counts[dimension] = {};
    for (const [code, n] of Object.entries(rec(codes))) {
      const count = num(n);
      if (count !== null) counts[dimension][code] = count;
    }
  }
  return {
    ok: true,
    value: {
      run_id,
      ticker: str(p.ticker),
      status: "ok",
      key_conclusions: {
        rule: str(k.rule) ?? "",
        claim_count: num(k.claim_count) ?? groups.reduce((total, g) => total + g.rows.length, 0),
        agent_wording_verified_count: num(k.agent_wording_verified_count) ?? 0,
        status_counts: counts,
        groups,
      },
    },
  };
}
