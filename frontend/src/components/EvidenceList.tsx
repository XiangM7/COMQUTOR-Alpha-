export interface EvidenceItem {
  claimId: string;
  agent?: string;
  side?: string;
  matchScore?: number;
  evidence?: string;
}

interface EvidenceListProps {
  title: string;
  items: EvidenceItem[];
}

/** Renders only backend-provided public fields (claim_id/agent/side/match
 * score/evidence text) -- never a raw agent output, chain-of-thought,
 * prompt, or local path. */
export function EvidenceList({ title, items }: EvidenceListProps) {
  if (items.length === 0) {
    return (
      <section className="evidence-list">
        <h4>{title}</h4>
        <p className="evidence-list-empty">No evidence references available.</p>
      </section>
    );
  }
  return (
    <section className="evidence-list">
      <h4>{title}</h4>
      <ul>
        {items.map((item, index) => (
          <li key={`${item.claimId}-${index}`} className="evidence-list-item">
            <span className="evidence-claim-id">{item.claimId}</span>
            {item.side ? <span className="evidence-side">{item.side}</span> : null}
            {item.agent ? <span className="evidence-agent">{item.agent}</span> : null}
            {item.matchScore != null ? (
              <span className="evidence-score">match {item.matchScore.toFixed(2)}</span>
            ) : null}
            {item.evidence ? <p className="evidence-text">{item.evidence}</p> : null}
          </li>
        ))}
      </ul>
    </section>
  );
}
