import type { AlphaActivation, AlphaEvidenceDetail } from "../api/types";

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
