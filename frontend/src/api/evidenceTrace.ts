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

/**
 * alpha_evidence_consumption.v2 -- how the evidence contract treated ONE claim: the model's stance toward the matched Alpha, whether
 * that stance keeps the claim out of the Alpha's positive pool, whether the target company's NAME is present in the claim text
 * (never "the claim is about the company"), and which weight the scorers consumed (today always the rule-based lexical score,
 * labelled as such). `null` on the item = the run never declared the contract (legacy behaviour, nothing here is shown).
 */
export interface TraceConsumptionStance {
  /** MODEL_JUDGED (a valid model result confirmed by the run's own validated ledger) or UNJUDGED (no exclusion follows from it). */
  state: string;
  label: string | null;
  method: string | null;
  version: string | null;
  counter_alpha_id: string | null;
  /** MISSING / TIMEOUT / PARSE_FAILED / FALLBACK / UNVERIFIED -- only for UNJUDGED. */
  unjudged_category: string | null;
  unjudged_reason: string | null;
  ledger: string | null;
  explanation: string | null;
}

export interface TraceConsumptionAdmission {
  admitted: boolean;
  /** STANCE_MODEL_NOT_SUPPORTING when the claim is kept out of this Alpha's positive pool. */
  reason_code: string | null;
  label: string | null;
  policy: string | null;
  explanation: string | null;
}

export interface TraceConsumptionAttribution {
  category: string | null;
  /** "The target's name is present in the claim text" -- NOT "the claim is about the target". */
  ticker_specific: boolean;
  subject_determined: boolean;
  limits: string[];
  other_issuers_named: string[];
  basis: { kind: string; term: string }[];
  policy: string | null;
  explanation: string | null;
}

export interface TraceConsumptionRelevance {
  state: string | null;
  model_level: string | null;
  model_weight: number | null;
  lexical_baseline: number | null;
  effective_weight: number | null;
  /** LEXICAL_RULE_FALLBACK: the rule-based score is consumed unchanged; it is not a model strength. */
  weight_authority: string | null;
  policy: string | null;
  note: string | null;
}

export interface TraceConsumptionTextRule {
  relation: string | null;
  assertion_status: string | null;
  semantic_polarity: string | null;
}

/** alpha_statement_scope (2026-10-13; v2): whether the text rule's whole-claim negation negates THIS Alpha's statement. */
export interface TraceConsumptionStatementScope {
  applies: boolean;
  governing_negation: boolean;
  changed: boolean;
  removed: { basis: string; text: string }[];
  /** v2: the contrast / other-clause parts the rule did NOT remove because the pair has no anchor (a ledger-corroborated model
   * judgment that the claim supports this Alpha) -- without it the words cannot tell which side carries the Alpha's statement. */
  not_applied: { basis: string; text: string }[];
  /** v2: what anchored the contrast / other-clause removals ("MODEL_JUDGED_SUPPORTS_ALPHA"), null when nothing did. */
  anchor: string | null;
  remaining_negators: string[];
  /** The text-rule fields the positive gates and the weights read (the stored ones are unchanged). */
  effective: TraceConsumptionTextRule | null;
  policy: string | null;
  explanation: string | null;
}

export interface TraceConsumptionBinding {
  input_sha256: string | null;
  source_state_sha256: string | null;
  ledger_integrity: string | null;
  ledger_sha256: string | null;
  /** WHOSE model ledger corroborated the stance (a derived execution binds the ledger of the saved run it recomputes). */
  ledger_owner_run_id: string | null;
  /** OWN_RUN or SOURCE_RUN_DECLARED. */
  ledger_binding: string | null;
}

export interface TraceStanceLedgerRef {
  available: boolean;
  integrity: string | null;
  sha256: string | null;
  owner_run_id: string | null;
  binding: string | null;
}

/** Which run executed the evaluation and on what basis -- executing run, saved source run and ledger owner kept apart. */
export interface TraceExecutionBasis {
  execution_run_id: string | null;
  execution_type: string | null;
  based_on_run_id: string | null;
  root_research_run_id: string | null;
  /** True for a derived execution: a recomputation of saved inputs, never a Fresh Run. */
  recomputation_of_saved_inputs: boolean;
  label: string | null;
  stance_ledger: TraceStanceLedgerRef | null;
}

export interface TraceConsumption {
  contract: string;
  /** CURRENT / STALE / MISSING / INVALID:<reason> / NOT_APPLICABLE / UNKNOWN (the saved decision against a fresh recomputation). */
  state: string;
  verification_error: string | null;
  /** Set for a claim matched to no Alpha: only the name decision exists. */
  scope: string | null;
  alpha_id: string | null;
  policies: Record<string, string>;
  text_rule: TraceConsumptionTextRule | null;
  stance: TraceConsumptionStance | null;
  positive_admission: TraceConsumptionAdmission | null;
  attribution: TraceConsumptionAttribution | null;
  relevance: TraceConsumptionRelevance | null;
  binding: TraceConsumptionBinding | null;
  execution_basis: TraceExecutionBasis | null;
  /** Additive (2026-10-13); null on older backends. */
  statement_scope: TraceConsumptionStatementScope | null;
}

export interface TraceRelevanceAnchor {
  element_id: string;
  label: string | null;
  /** "core" (core thesis / trigger / invalidation) or "strong" (confirmation only). */
  ownership: string | null;
  occurrences: { list: string; phrase: string }[];
  /** Output v2 (prompt v2): the claim's own words the judgment quoted for this element; empty for a judgment recorded under output v1. */
  evidence_quotes: string[];
  /** Output v3: how each quoted statement is made (assertion, forecast, probability ...), aligned with evidence_quotes; empty before v3. */
  evidence_modes: string[];
}

/** Output v3: one statement the judgment reported -- recorded as the model gave it; the API never re-judges it. */
export interface TraceRelevanceStatement {
  quote: string;
  object: string | null;
  property: string | null;
  mode: string | null;
  element_id: string | null;
  hit: boolean;
  why: string | null;
}

export interface TraceRelevanceSource {
  execution_run_id: string | null;
  based_on_run_id: string | null;
  /** The run that owns the judgment and its relevance ledger. */
  owner_run_id: string | null;
  call_id: string | null;
  task: string | null;
  prompt_version: string | null;
  criterion_version: string | null;
  provider: string | null;
  model: string | null;
  execution_mode: string | null;
  ledger_integrity: string | null;
  ledger_directory: string | null;
}

/** P4 phase 1 -- the experimental relevance judgment of a claim and its MATCHED Alpha (absent for a claim matched to no Alpha). */
export interface TraceRelevanceJudgment {
  contract: string;
  alpha_id: string | null;
  /** UNJUDGED / JUDGED / UNRESOLVED / FAILED. */
  state: string;
  /** core / strong / weak / none -- set ONLY when state is JUDGED (never "none" for a missing judgment). */
  tier: string | null;
  reason: string | null;
  reason_detail: string | null;
  label: string | null;
  anchors: TraceRelevanceAnchor[];
  basis: string | null;
  unresolved_reason: string | null;
  /** Output v3: every statement the judgment reported (hit or not); empty before v3. */
  statements: TraceRelevanceStatement[];
  /** Output v3: "element_ownership_q1" (core / strong derived from the hit elements) or "model_no_hit" (weak / none); null otherwise. */
  tier_source: string | null;
  /** True when the judgment came from the simulated gateway: TEST DATA, never a model judgment. */
  test_data: boolean;
  source: TraceRelevanceSource;
  /** Always null in this phase: no weight is derived from the label. */
  model_weight: number | null;
  consumption_note: string | null;
}

const RELEVANCE_STATES = new Set(["UNJUDGED", "JUDGED", "UNRESOLVED", "FAILED"]);
const RELEVANCE_TIERS = new Set(["core", "strong", "weak", "none"]);

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
  /** null = the run never declared alpha_evidence_consumption.v2 (nothing to show). */
  consumption: TraceConsumption | null;
  /** null = the claim has no matched Alpha, or the payload predates the relevance record. */
  relevance_judgment: TraceRelevanceJudgment | null;
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
  /** Only for a run under the evidence contract or produced by the consumption recompute entry; null for every other run. */
  execution_basis: TraceExecutionBasis | null;
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

function adaptExecutionBasis(raw: unknown): TraceExecutionBasis | null {
  if (!isRecord(raw)) return null;
  const ledger = isRecord(raw.stance_ledger) ? raw.stance_ledger : null;
  return {
    execution_run_id: str(raw.execution_run_id),
    execution_type: str(raw.execution_type),
    based_on_run_id: str(raw.based_on_run_id),
    root_research_run_id: str(raw.root_research_run_id),
    recomputation_of_saved_inputs: bool(raw.recomputation_of_saved_inputs),
    label: str(raw.label),
    stance_ledger: ledger
      ? {
          available: bool(ledger.available),
          integrity: str(ledger.integrity),
          sha256: str(ledger.sha256),
          owner_run_id: str(ledger.owner_run_id),
          binding: str(ledger.binding),
        }
      : null,
  };
}

export function adaptRelevanceJudgment(raw: unknown): TraceRelevanceJudgment | null {
  if (!isRecord(raw)) return null;
  const contract = str(raw.contract);
  const state = str(raw.state);
  if (!contract || !state || !RELEVANCE_STATES.has(state)) return null;
  const tier = str(raw.tier);
  const source = rec(raw.source);
  const ledger = rec(source.ledger);
  return {
    contract,
    alpha_id: str(raw.alpha_id),
    state,
    // a tier is shown only for a JUDGED pair, and only from the closed vocabulary
    tier: state === "JUDGED" && tier !== null && RELEVANCE_TIERS.has(tier) ? tier : null,
    reason: str(raw.reason),
    reason_detail: str(raw.reason_detail),
    label: str(raw.label),
    anchors: list(raw.anchors)
      .map((anchorRaw) => {
        const anchor = rec(anchorRaw);
        const elementId = str(anchor.element_id);
        if (!elementId) return null;
        return {
          element_id: elementId,
          label: str(anchor.label),
          ownership: str(anchor.ownership),
          occurrences: list(anchor.occurrences)
            .map((occurrenceRaw) => {
              const occurrence = rec(occurrenceRaw);
              const listName = str(occurrence.list);
              const phrase = str(occurrence.phrase);
              return listName && phrase ? { list: listName, phrase } : null;
            })
            .filter((entry): entry is { list: string; phrase: string } => entry !== null),
          evidence_quotes: strList(anchor.evidence_quotes).filter((quote) => quote.trim() !== ""),
          evidence_modes: list(anchor.evidence_modes).map((mode) => str(mode) ?? ""),
        };
      })
      .filter((entry): entry is TraceRelevanceAnchor => entry !== null),
    basis: str(raw.basis),
    unresolved_reason: str(raw.unresolved_reason),
    statements: list(raw.statements)
      .map((statementRaw) => {
        const s = rec(statementRaw);
        const quote = str(s.quote);
        if (!quote) return null;
        return { quote, object: str(s.object), property: str(s.property), mode: str(s.mode), element_id: str(s.element_id), hit: bool(s.hit), why: str(s.why) };
      })
      .filter((entry): entry is TraceRelevanceStatement => entry !== null),
    tier_source: str(raw.tier_source),
    test_data: bool(raw.test_data),
    source: {
      execution_run_id: str(source.execution_run_id),
      based_on_run_id: str(source.based_on_run_id),
      owner_run_id: str(source.owner_run_id),
      call_id: str(source.call_id),
      task: str(source.task),
      prompt_version: str(source.prompt_version),
      criterion_version: str(source.criterion_version),
      provider: str(source.provider),
      model: str(source.model),
      execution_mode: str(source.execution_mode),
      ledger_integrity: str(ledger.integrity),
      ledger_directory: str(ledger.directory),
    },
    model_weight: num(raw.model_weight),
    consumption_note: str(raw.consumption_note),
  };
}

function adaptConsumption(raw: unknown): TraceConsumption | null {
  if (!isRecord(raw)) return null;
  const contract = str(raw.contract);
  if (!contract) return null;
  const stance = isRecord(raw.stance) ? raw.stance : null;
  const admission = isRecord(raw.positive_admission) ? raw.positive_admission : null;
  const attribution = isRecord(raw.attribution) ? raw.attribution : null;
  const relevance = isRecord(raw.relevance) ? raw.relevance : null;
  const textRule = isRecord(raw.text_rule) ? raw.text_rule : null;
  const scope = isRecord(raw.statement_scope) ? raw.statement_scope : null;
  const scopeEffective = scope && isRecord(scope.effective) ? scope.effective : null;
  const binding = isRecord(raw.binding) ? raw.binding : null;
  const ledger = rec(binding?.ledger);
  const policies: Record<string, string> = {};
  for (const [name, version] of Object.entries(rec(raw.policies))) {
    const text = str(version);
    if (text !== null) policies[name] = text;
  }
  return {
    contract,
    state: str(raw.state) ?? "UNKNOWN",
    verification_error: str(raw.verification_error),
    scope: str(raw.scope),
    alpha_id: str(raw.alpha_id),
    policies,
    text_rule: textRule
      ? { relation: str(textRule.relation), assertion_status: str(textRule.assertion_status), semantic_polarity: str(textRule.semantic_polarity) }
      : null,
    statement_scope: scope
      ? {
          applies: scope.applies === true,
          governing_negation: scope.governing_negation === true,
          changed: scope.changed === true,
          removed: list(scope.removed).flatMap((entry) => {
            const basis = str(rec(entry).basis);
            const text = str(rec(entry).text);
            return basis && text !== null ? [{ basis, text }] : [];
          }),
          not_applied: list(scope.not_applied).flatMap((entry) => {
            const basis = str(rec(entry).basis);
            const text = str(rec(entry).text);
            return basis && text !== null ? [{ basis, text }] : [];
          }),
          anchor: str(scope.anchor),
          remaining_negators: strList(scope.remaining_negators),
          effective: scopeEffective
            ? {
                relation: str(scopeEffective.relation),
                assertion_status: str(scopeEffective.assertion_status),
                semantic_polarity: str(scopeEffective.semantic_polarity),
              }
            : null,
          policy: str(scope.policy),
          explanation: str(scope.explanation),
        }
      : null,
    stance: stance
      ? {
          state: str(stance.state) ?? "UNKNOWN",
          label: str(stance.label),
          method: str(stance.method),
          version: str(stance.version),
          counter_alpha_id: str(stance.counter_alpha_id),
          unjudged_category: str(stance.unjudged_category),
          unjudged_reason: str(stance.unjudged_reason),
          ledger: str(stance.ledger),
          explanation: str(stance.explanation),
        }
      : null,
    positive_admission: admission
      ? {
          admitted: admission.admitted !== false,
          reason_code: str(admission.reason_code),
          label: str(admission.label),
          policy: str(admission.policy),
          explanation: str(admission.explanation),
        }
      : null,
    attribution: attribution
      ? {
          category: str(attribution.category),
          ticker_specific: bool(attribution.ticker_specific),
          subject_determined: bool(attribution.subject_determined),
          limits: strList(attribution.limits),
          other_issuers_named: strList(attribution.other_issuers_named),
          basis: list(attribution.basis).flatMap((entry) => {
            const kind = str(rec(entry).kind);
            const term = str(rec(entry).term);
            return kind && term ? [{ kind, term }] : [];
          }),
          policy: str(attribution.policy),
          explanation: str(attribution.explanation),
        }
      : null,
    relevance: relevance
      ? {
          state: str(relevance.state),
          model_level: str(relevance.model_level),
          model_weight: num(relevance.model_weight),
          lexical_baseline: num(relevance.lexical_baseline),
          effective_weight: num(relevance.effective_weight),
          weight_authority: str(relevance.weight_authority),
          policy: str(relevance.policy),
          note: str(relevance.note),
        }
      : null,
    binding: binding
      ? {
          input_sha256: str(binding.input_sha256),
          source_state_sha256: str(binding.source_state_sha256),
          ledger_integrity: str(ledger.integrity),
          ledger_sha256: str(ledger.sha256),
          ledger_owner_run_id: str(ledger.owner_run_id),
          ledger_binding: str(ledger.binding),
        }
      : null,
    execution_basis: adaptExecutionBasis(raw.execution_basis),
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
      consumption: adaptConsumption(r.consumption),
      relevance_judgment: adaptRelevanceJudgment(r.relevance_judgment),
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
        execution_basis: adaptExecutionBasis(k.execution_basis),
      },
    },
  };
}
