import type {
  AlphaActivation,
  AlphaEvidenceDetail,
  EntityExposure,
  EntityExposureLifecycleStatus,
  LocalStructureSupportComponent,
} from "../api/types";

// John's B3 gated seed lifecycle (task B3_ENTITY_EXPOSURE_GATED_STATES):
// the frontend never recomputes or infers this status -- it only ever
// labels whatever effective_status the backend already resolved (or, for
// a historical payload predating that field, the legacy off/shadow/
// enforced `mode`). Never re-derive from thresholds/qualification fields.
const LIFECYCLE_STATUS_LABELS: Record<EntityExposureLifecycleStatus, string> = {
  draft_shadow: "Draft shadow",
  approved_gating: "Approved gating",
  disabled: "Disabled",
};

const LIFECYCLE_STATUS_DESCRIPTIONS: Record<EntityExposureLifecycleStatus, string> = {
  draft_shadow: "Displayed only — not applied to Activation",
  approved_gating: "Participates in qualification",
  disabled: "Seed not participating",
};

const LEGACY_MODE_TO_STATUS: Record<string, EntityExposureLifecycleStatus> = {
  off: "disabled",
  shadow: "draft_shadow",
  enforced: "approved_gating",
};

function resolveLifecycleStatus(exposure: EntityExposure): EntityExposureLifecycleStatus | null {
  if (exposure.effective_status) {
    return exposure.effective_status;
  }
  // Historical payload predating effective_status -- fall back to the
  // legacy mode field rather than crash or show nothing.
  return LEGACY_MODE_TO_STATUS[exposure.mode] ?? null;
}

const LEVEL_ICONS: Record<string, string> = {
  inactive: "○", // hollow circle
  watch: "◐", // half circle
  candidate: "◌", // dotted circle
  active: "●", // filled circle
  dominant: "★", // star
  regime_level: "✲", // asterisk-like
};

// John's four canonical, product-facing blocked reasons (task
// B4_ACTIVATION_LEVEL_ALIGNMENT section 9) -- the frontend never invents
// friendly text for anything outside this fixed set; an unrecognized code
// (should never happen, since the backend only ever emits these four in
// blocked_reason_codes) falls back to the raw code itself rather than
// hiding it.
const BLOCKED_REASON_LABELS: Record<string, string> = {
  NO_LOCAL_STRUCTURE_SUPPORT: "No supporting Structure Graph edges",
  INSUFFICIENT_EVIDENCE: "Insufficient independent evidence",
  LOW_ENTITY_EXPOSURE: "Entity Exposure below required threshold",
  NO_TICKER_SPECIFIC_EVIDENCE: "No ticker-specific evidence",
};

const ACTIVATION_V2_VERSION_PREFIX = "activation.v2.";

interface AlphaCardProps {
  alphaId: string;
  alphaName: string;
  activationScore: number;
  status: string;
  direction?: string | null;
  evidenceCount?: number | null;
  distinctSupportingAgents?: number | null;
  /** Labels of admitted conflicts involving this alpha, e.g. "A101 vs A304".
   * An empty array means "no conflicts for this run" (rendered as "None");
   * undefined/null means the caller had no conflict data at all. */
  relatedConflicts?: string[] | null;
  evidenceDetail?: AlphaEvidenceDetail[] | null;
  /** Full scored activation entry when available: carries the Activation
   * v2 transparency fields (formula version, uncapped score, caps, regime
   * gate). A v1-legacy entry (no v2 formula_version) is labeled
   * "Activation v1 (legacy)" -- never presented as v2. */
  activation?: AlphaActivation | null;
  isDominant?: boolean;
}

/** Alpha activation summary card. Status is conveyed with text + an icon +
 * a distinct CSS class (never color alone). Any field the backend did not
 * provide renders as "Not available" -- never fabricated. */
export function AlphaCard({
  alphaId,
  alphaName,
  activationScore,
  status,
  direction,
  evidenceCount,
  distinctSupportingAgents,
  relatedConflicts,
  evidenceDetail,
  activation,
  isDominant,
}: AlphaCardProps) {
  const icon = LEVEL_ICONS[status] ?? "•";
  const supportingAgents =
    evidenceDetail && evidenceDetail.length > 0
      ? Array.from(new Set(evidenceDetail.map((item) => item.agent).filter(Boolean)))
      : [];
  const isV2 =
    activation?.formula_version != null &&
    activation.formula_version.startsWith(ACTIVATION_V2_VERSION_PREFIX);
  const formulaLabel = activation
    ? isV2
      ? "Activation v2"
      : "Activation v1 (legacy)"
    : null;
  // Evidence Integrity Completion Sprint, Track C: prefer the additive,
  // unambiguous fields when the API provided them; fall back to nothing
  // (never fabricate) on an older payload.
  const localStructure = (activation?.components?.local_structure_support ?? null) as
    | LocalStructureSupportComponent
    | null;
  const hasEvidenceFactFields =
    isV2 &&
    activation != null &&
    activation.raw_supporting_claim_count != null &&
    activation.unique_evidence_fact_count != null;
  const hasEdgeQualificationFields =
    isV2 &&
    localStructure != null &&
    localStructure.incident_graph_edge_count != null &&
    localStructure.qualifying_local_edge_count != null;
  const entityExposure = activation?.entity_exposure ?? null;
  return (
    <article className={`alpha-card alpha-card-${status}${isDominant ? " alpha-card-dominant" : ""}`} tabIndex={0}>
      <header className="alpha-card-header">
        <span className="alpha-card-icon" aria-hidden="true">
          {icon}
        </span>
        <div>
          <p className="alpha-card-id">{alphaId}</p>
          <h3 className="alpha-card-name">{alphaName}</h3>
        </div>
        {isDominant ? <span className="alpha-card-badge">Dominant</span> : null}
      </header>
      <dl className="alpha-card-body">
        {formulaLabel ? (
          <div className="alpha-card-row">
            <dt>Formula</dt>
            <dd className={isV2 ? "alpha-card-formula-v2" : "alpha-card-formula-v1-legacy"}>
              {formulaLabel}
            </dd>
          </div>
        ) : null}
        <div className="alpha-card-row">
          <dt>Activation score</dt>
          <dd>{activationScore.toFixed(1)}</dd>
        </div>
        {isV2 && activation ? (
          <>
            <div className="alpha-card-row">
              <dt>Uncapped score</dt>
              <dd>
                {activation.uncapped_score != null
                  ? activation.uncapped_score.toFixed(1)
                  : "Not available"}
              </dd>
            </div>
            <div className="alpha-card-row">
              <dt>Qualification ceiling</dt>
              <dd>
                {activation.eligible_cap != null
                  ? `${activation.eligible_cap.toFixed(0)} (${activation.cap_reason_codes.join(", ")})`
                  : "None"}
              </dd>
            </div>
            <div className="alpha-card-row">
              <dt>Score was capped</dt>
              <dd>
                {activation.cap_was_binding
                  ? `Yes — final score: ${activation.activation_score.toFixed(1)} (${activation.binding_cap_reason_codes.join(", ")})`
                  : "No"}
              </dd>
            </div>
          </>
        ) : null}
        <div className="alpha-card-row">
          <dt>Activation level</dt>
          <dd className={`activation-level-label activation-level-${status}`}>{status}</dd>
        </div>
        {/* B4 Activation Level Alignment (task B4_ACTIVATION_LEVEL_ALIGNMENT):
            qualified_level/target_level/is_blocked are read directly from the
            backend and never recomputed here -- "blocked" is qualification
            metadata layered on qualified_level, never a fifth level string. */}
        {activation && activation.qualified_level != null && activation.target_level != null ? (
          <>
            {activation.target_level !== activation.qualified_level ? (
              <div className="alpha-card-row">
                <dt>Target level</dt>
                <dd>
                  {activation.target_level} — what the evidence alone supports, before
                  qualification
                </dd>
              </div>
            ) : null}
            {activation.is_blocked ? (
              <div className="alpha-card-row alpha-card-row-warning alpha-card-row-blocked">
                <dt>Blocked</dt>
                <dd>
                  Held at {activation.qualified_level}, blocked from{" "}
                  {(activation.blocked_from ?? []).join(", ") || "a higher level"}
                  {activation.blocked_reason_codes && activation.blocked_reason_codes.length > 0 ? (
                    <>
                      {" — "}
                      {activation.blocked_reason_codes
                        .map((code) => BLOCKED_REASON_LABELS[code] ?? code)
                        .join(", ")}
                    </>
                  ) : null}
                  {activation.diagnostic_reason_codes && activation.diagnostic_reason_codes.length > 0 ? (
                    <details className="alpha-card-diagnostic-reasons">
                      <summary>Full diagnostic detail</summary>
                      <ul>
                        {activation.diagnostic_reason_codes.map((code) => (
                          <li key={code}>{code}</li>
                        ))}
                      </ul>
                    </details>
                  ) : null}
                </dd>
              </div>
            ) : null}
          </>
        ) : activation ? (
          <div className="alpha-card-row alpha-card-row-detail">
            <dt>Classification</dt>
            <dd>Legacy classification — this run predates the B4 alpha-level classifier</dd>
          </div>
        ) : null}
        <div className="alpha-card-row">
          <dt>Direction</dt>
          <dd>{direction ?? "Not available"}</dd>
        </div>
        <div className="alpha-card-row">
          <dt>Supporting evidence</dt>
          <dd>{evidenceCount != null ? evidenceCount : "Not available"}</dd>
        </div>
        <div className="alpha-card-row">
          <dt>Distinct supporting agents</dt>
          <dd>{distinctSupportingAgents != null ? distinctSupportingAgents : "Not available"}</dd>
        </div>
        {activation ? (
          <div className="alpha-card-row alpha-card-row-entity-exposure">
            <dt>Entity Exposure</dt>
            <dd>
              {entityExposure?.exposure_status === "computed" &&
              entityExposure.final_exposure != null
                ? entityExposure.final_exposure.toFixed(3)
                : "Not available"}
            </dd>
          </div>
        ) : null}
        {entityExposure ? (
          <>
            {(() => {
              const lifecycleStatus = resolveLifecycleStatus(entityExposure);
              return (
                <div className="alpha-card-row alpha-card-row-detail">
                  <dt>Seed lifecycle</dt>
                  <dd>
                    {lifecycleStatus ? LIFECYCLE_STATUS_LABELS[lifecycleStatus] : "Not available"}
                    {lifecycleStatus ? ` — ${LIFECYCLE_STATUS_DESCRIPTIONS[lifecycleStatus]}` : ""}
                  </dd>
                </div>
              );
            })()}
            {entityExposure.configured_status &&
            entityExposure.effective_status &&
            entityExposure.configured_status !== entityExposure.effective_status ? (
              <div className="alpha-card-row alpha-card-row-warning">
                <dt>Gating downgraded</dt>
                <dd>
                  Configured as {LIFECYCLE_STATUS_LABELS[entityExposure.configured_status]}, but{" "}
                  {entityExposure.reason_codes.length > 0
                    ? `fell back due to: ${entityExposure.reason_codes.join(", ")}`
                    : "fell back for this run"}
                </dd>
              </div>
            ) : null}
            {(entityExposure.owner || entityExposure.approved_by || entityExposure.approved_at) ? (
              <div className="alpha-card-row alpha-card-row-detail">
                <dt>Approved by</dt>
                <dd>
                  {entityExposure.approved_by ?? entityExposure.owner ?? "Not available"}
                  {entityExposure.approved_at ? ` (${entityExposure.approved_at})` : ""}
                </dd>
              </div>
            ) : null}
            <div className="alpha-card-row alpha-card-row-detail">
              <dt>Historical mapping</dt>
              <dd>
                {entityExposure.historical_mapping != null
                  ? entityExposure.historical_mapping.toFixed(3)
                  : "Not available"}
              </dd>
            </div>
            <div className="alpha-card-row alpha-card-row-detail">
              <dt>Current evidence</dt>
              <dd>{entityExposure.current_evidence.toFixed(3)}</dd>
            </div>
            <div className="alpha-card-row alpha-card-row-detail">
              <dt>Agent confidence</dt>
              <dd>{entityExposure.agent_confidence.toFixed(3)}</dd>
            </div>
            <div className="alpha-card-row alpha-card-row-detail">
              <dt>Seed version</dt>
              <dd>{entityExposure.seed_version}</dd>
            </div>
            {resolveLifecycleStatus(entityExposure) === "draft_shadow" ? (
              <div className="alpha-card-row alpha-card-row-warning">
                <dt>Qualification effect</dt>
                <dd>Shadow only — Not applied to Activation</dd>
              </div>
            ) : null}
            <div className="alpha-card-row alpha-card-row-detail">
              <dt>Would block dominant</dt>
              <dd>{entityExposure.would_block_dominant ? "Yes" : "No"}</dd>
            </div>
            <div className="alpha-card-row alpha-card-row-detail">
              <dt>Would block regime level</dt>
              <dd>{entityExposure.would_block_regime_level ? "Yes" : "No"}</dd>
            </div>
            {entityExposure.exposure_status === "missing_seed" ? (
              <div className="alpha-card-row alpha-card-row-warning">
                <dt>Reason</dt>
                <dd>No approved/configured seed entry</dd>
              </div>
            ) : null}
          </>
        ) : null}
        {hasEvidenceFactFields && activation ? (
          <>
            <div className="alpha-card-row alpha-card-row-detail">
              <dt>Raw supporting claims</dt>
              <dd>{activation.raw_supporting_claim_count}</dd>
            </div>
            <div className="alpha-card-row alpha-card-row-detail">
              <dt>Independent evidence facts</dt>
              <dd>{activation.unique_evidence_fact_count}</dd>
            </div>
            <div className="alpha-card-row alpha-card-row-detail">
              <dt>Evidence overlap</dt>
              <dd>
                {activation.evidence_overlap_ratio != null
                  ? `${(activation.evidence_overlap_ratio * 100).toFixed(1)}%`
                  : "Not available"}
              </dd>
            </div>
            {activation.high_overlap_warning ? (
              <div className="alpha-card-row alpha-card-row-warning">
                <dt>Evidence overlap warning</dt>
                <dd>
                  Several supporting claims appear to restate the same underlying facts.
                </dd>
              </div>
            ) : null}
          </>
        ) : null}
        <div className="alpha-card-row">
          <dt>Related conflicts</dt>
          <dd className="alpha-card-related-conflicts">
            {relatedConflicts == null
              ? "Not available"
              : relatedConflicts.length === 0
                ? "None"
                : relatedConflicts.join(", ")}
          </dd>
        </div>
        {supportingAgents.length > 0 ? (
          <div className="alpha-card-row">
            <dt>Supporting agents</dt>
            <dd>{supportingAgents.join(", ")}</dd>
          </div>
        ) : null}
        {isV2 && activation ? (
          <>
            <div className="alpha-card-row">
              <dt>Ticker-specific evidence</dt>
              <dd>
                {activation.ticker_specific_evidence_count != null
                  ? activation.ticker_specific_evidence_count
                  : "Not available"}
              </dd>
            </div>
            <div className="alpha-card-row">
              <dt>Local structural edges</dt>
              <dd>
                {activation.local_edge_count != null
                  ? activation.local_edge_count
                  : "Not available"}
              </dd>
            </div>
            {hasEdgeQualificationFields && localStructure ? (
              <>
                <div className="alpha-card-row alpha-card-row-detail">
                  <dt>Incident graph edges</dt>
                  <dd>{localStructure.incident_graph_edge_count}</dd>
                </div>
                <div className="alpha-card-row alpha-card-row-detail">
                  <dt>Qualifying activation-support edges</dt>
                  <dd>{localStructure.qualifying_local_edge_count}</dd>
                </div>
                <div className="alpha-card-row alpha-card-row-detail">
                  <dt>Excluded local edges</dt>
                  <dd>{localStructure.nonqualifying_local_edge_count ?? 0}</dd>
                </div>
                {localStructure.local_edge_exclusion_reasons &&
                localStructure.local_edge_exclusion_reasons.length > 0 ? (
                  <details className="alpha-card-exclusion-reasons">
                    <summary>Why edges did not qualify</summary>
                    <ul>
                      {localStructure.local_edge_exclusion_reasons.map((reason) => (
                        <li key={reason}>{reason}</li>
                      ))}
                    </ul>
                  </details>
                ) : null}
              </>
            ) : null}
            <div className="alpha-card-row">
              <dt>Regime qualification</dt>
              <dd className="alpha-card-regime-gate">
                {activation.regime_gate_passed === true
                  ? "Qualified"
                  : activation.regime_gate_failures.length > 0
                    ? `Not qualified (${activation.regime_gate_failures.join(", ")})`
                    : "Not in regime band"}
              </dd>
            </div>
          </>
        ) : null}
      </dl>
      {evidenceDetail && evidenceDetail.length > 0 ? (
        <details className="alpha-card-evidence">
          <summary>Evidence ({evidenceDetail.length})</summary>
          <ul className="alpha-card-evidence-list">
            {evidenceDetail.map((item) => (
              <li key={item.claim_id} className="alpha-card-evidence-item">
                <p className="alpha-card-evidence-claim">{item.claim}</p>
                <p className="alpha-card-evidence-meta">
                  <span>Agent: {item.agent || "unknown"}</span>
                  {" · "}
                  <span>Match {item.match_score.toFixed(2)}</span>
                  {" · "}
                  <span>Relation: {item.relation}</span>
                  {" · "}
                  <span>Assertion: {item.assertion_status}</span>
                </p>
                {item.matched_keywords.length > 0 ? (
                  <p className="alpha-card-evidence-keywords">
                    Matched keywords: {item.matched_keywords.join(", ")}
                  </p>
                ) : null}
                {item.matched_factors.length > 0 ? (
                  <p className="alpha-card-evidence-factors">
                    Matched factors: {item.matched_factors.join(", ")}
                  </p>
                ) : null}
                <p className="alpha-card-evidence-claim-id">
                  <code>{item.claim_id}</code>
                </p>
              </li>
            ))}
          </ul>
        </details>
      ) : null}
    </article>
  );
}
