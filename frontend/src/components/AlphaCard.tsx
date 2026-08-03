import type { AlphaActivation, AlphaEvidenceDetail, LocalStructureSupportComponent } from "../api/types";

const LEVEL_ICONS: Record<string, string> = {
  inactive: "○", // hollow circle
  watch: "◐", // half circle
  active: "●", // filled circle
  dominant: "★", // star
  regime_level: "✲", // asterisk-like
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
            {entityExposure.seed_approval_status === "draft" ? (
              <div className="alpha-card-row alpha-card-row-warning">
                <dt>Seed approval</dt>
                <dd>Draft seed — pending product-owner approval</dd>
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
            <div className="alpha-card-row alpha-card-row-detail">
              <dt>Seed status</dt>
              <dd>{entityExposure.seed_approval_status}</dd>
            </div>
            <div className="alpha-card-row alpha-card-row-detail">
              <dt>Exposure mode</dt>
              <dd>{entityExposure.mode}</dd>
            </div>
            {entityExposure.mode === "shadow" ? (
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
