const LEVEL_ICONS: Record<string, string> = {
  inactive: "○", // hollow circle
  watch: "◐", // half circle
  active: "●", // filled circle
  dominant: "★", // star
  regime_level: "✲", // asterisk-like
};

interface AlphaCardProps {
  alphaId: string;
  alphaName: string;
  activationScore: number;
  status: string;
  direction?: string | null;
  evidenceCount?: number | null;
  distinctSupportingAgents?: number | null;
  conflictCount?: number | null;
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
  conflictCount,
  isDominant,
}: AlphaCardProps) {
  const icon = LEVEL_ICONS[status] ?? "•";
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
        <div className="alpha-card-row">
          <dt>Activation score</dt>
          <dd>{activationScore.toFixed(1)}</dd>
        </div>
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
          <dd>{conflictCount != null ? conflictCount : "Not available"}</dd>
        </div>
      </dl>
    </article>
  );
}
