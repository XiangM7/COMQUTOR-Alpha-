import type { AlphaConflict, ConflictEvidenceFactGroup, ConflictEvidenceItem } from "../api/types";

const LEVEL_LABELS: Record<string, string> = {
  low: "Low",
  medium: "Medium",
  medium_high: "Medium-high",
  high: "High",
};

interface ConflictCardProps {
  conflict: AlphaConflict;
  isMain?: boolean;
}

/** Evidence Integrity Completion Sprint, Track C: per-side evidence-fact
 * transparency (raw vs. independent facts vs. distinct agents vs. overlap)
 * -- absent (undefined) on a payload predating these fields, in which case
 * this row renders nothing rather than "Not available" noise. */
function ConflictSideFactStats({
  rawCount,
  uniqueCount,
  agentCount,
  overlapRatio,
}: {
  rawCount?: number;
  uniqueCount?: number;
  agentCount?: number;
  overlapRatio?: number;
}) {
  if (rawCount == null || uniqueCount == null) return null;
  return (
    <p className="conflict-side-fact-stats">
      <span>Independent evidence facts: {uniqueCount}</span>
      {agentCount != null ? (
        <>
          {" · "}
          <span>Distinct agents: {agentCount}</span>
        </>
      ) : null}
      {overlapRatio != null ? (
        <>
          {" · "}
          <span>Evidence overlap: {(overlapRatio * 100).toFixed(1)}%</span>
        </>
      ) : null}
      {" "}
      <span className="conflict-side-fact-stats-raw">(from {rawCount} raw supporting claims)</span>
    </p>
  );
}

/** Actual bull/bear evidence claims backing one side of a conflict. Only
 * ever renders backend-provided evidence text -- never a fixed template
 * standing in for evidence.
 *
 * When the backend provides ``factGroups`` (Evidence Integrity Completion
 * Sprint, Track B), renders ONE card per independent Evidence Fact (the
 * group's representative claim) with the rest of that fact's paraphrases
 * available in an expandable "merged claims" detail -- never one card per
 * raw, possibly-repeated claim. Falls back to the old one-card-per-claim
 * rendering when factGroups is unavailable (older API payload). */
function ConflictSideEvidence({
  title,
  items,
  factGroups,
}: {
  title: string;
  items: ConflictEvidenceItem[];
  factGroups?: ConflictEvidenceFactGroup[];
}) {
  if (!items || items.length === 0) {
    return <p className="conflict-side-evidence-empty">{title}: not available.</p>;
  }
  const itemsByClaimId = new Map(items.map((item) => [item.claim_id, item]));

  if (factGroups && factGroups.length > 0) {
    return (
      <div className="conflict-side-evidence">
        <p className="conflict-side-evidence-title">{title}:</p>
        <ul>
          {factGroups.map((group) => {
            const representative = itemsByClaimId.get(group.representative_claim_id);
            const otherMembers = group.member_claim_ids.filter(
              (claimId) => claimId !== group.representative_claim_id
            );
            return (
              <li key={group.evidence_fact_group_id} className="conflict-side-evidence-item">
                <p className="conflict-side-evidence-text">
                  {representative?.claim_text ?? "(evidence text not available)"}
                </p>
                <p className="conflict-side-evidence-meta">
                  <span>Agents: {group.supporting_agents.join(", ") || "unknown"}</span>
                  {representative ? (
                    <>
                      {" · "}
                      <span>Match {representative.match_score.toFixed(2)}</span>
                      {" · "}
                      <span>Relation: {representative.relation}</span>
                    </>
                  ) : null}
                </p>
                {otherMembers.length > 0 ? (
                  <details className="conflict-side-evidence-merged">
                    <summary>{otherMembers.length} merged paraphrase(s)</summary>
                    <ul>
                      {otherMembers.map((claimId) => (
                        <li key={claimId}>{itemsByClaimId.get(claimId)?.claim_text ?? claimId}</li>
                      ))}
                    </ul>
                  </details>
                ) : null}
              </li>
            );
          })}
        </ul>
      </div>
    );
  }

  return (
    <div className="conflict-side-evidence">
      <p className="conflict-side-evidence-title">{title}:</p>
      <ul>
        {items.map((item) => (
          <li key={item.claim_id} className="conflict-side-evidence-item">
            <p className="conflict-side-evidence-text">{item.claim_text}</p>
            <p className="conflict-side-evidence-meta">
              {item.agent ? <span>Agent: {item.agent}</span> : null}
              {item.agent ? " · " : null}
              <span>Match {item.match_score.toFixed(2)}</span>
              {" · "}
              <span>Relation: {item.relation}</span>
            </p>
          </li>
        ))}
      </ul>
    </div>
  );
}

/** Score bar + level band -- deterministic, accessible, no polar/radar
 * chart requirement. Level is always shown as text, never color alone. */
export function ConflictCard({ conflict, isMain }: ConflictCardProps) {
  const levelLabel = LEVEL_LABELS[conflict.conflict_level] ?? conflict.conflict_level;
  const scorePercent = Math.max(0, Math.min(100, conflict.conflict_score));

  return (
    <article className={`conflict-card conflict-level-${conflict.conflict_level}${isMain ? " conflict-card-main" : ""}`}>
      <header className="conflict-card-header">
        <h3>
          {conflict.alpha_a} vs {conflict.alpha_b}
        </h3>
        {isMain ? <span className="conflict-card-badge">Main conflict</span> : null}
      </header>
      <p className="conflict-card-explanation">{conflict.explanation}</p>
      <div className="conflict-score-row">
        <span className="conflict-score-label">
          Conflict score: {conflict.conflict_score.toFixed(1)} ({levelLabel})
        </span>
        <div
          className="score-bar"
          role="img"
          aria-label={`Conflict score ${conflict.conflict_score.toFixed(1)} out of 100, level ${levelLabel}`}
        >
          <div className="score-bar-fill" style={{ width: `${scorePercent}%` }} />
        </div>
      </div>
      <div className="conflict-sides">
        <div className="conflict-side">
          <p className="conflict-side-role">Bull side</p>
          <p className="conflict-side-alpha">
            {conflict.bull_structure.alpha_id} &mdash; {conflict.bull_structure.alpha_name}
          </p>
          <p className="conflict-side-activation">
            Activation: {conflict.bull_structure.activation_score.toFixed(1)} ({conflict.bull_structure.status})
          </p>
          <ConflictSideFactStats
            rawCount={conflict.bull_raw_claim_count}
            uniqueCount={conflict.bull_unique_fact_count}
            agentCount={conflict.bull_distinct_agent_count}
            overlapRatio={conflict.bull_overlap_ratio}
          />
          <ConflictSideEvidence
            title="Bull evidence"
            items={conflict.bull_evidence}
            factGroups={conflict.bull_structure.evidence_facts}
          />
        </div>
        <div className="conflict-side">
          <p className="conflict-side-role">Bear side</p>
          <p className="conflict-side-alpha">
            {conflict.bear_structure.alpha_id} &mdash; {conflict.bear_structure.alpha_name}
          </p>
          <p className="conflict-side-activation">
            Activation: {conflict.bear_structure.activation_score.toFixed(1)} ({conflict.bear_structure.status})
          </p>
          <ConflictSideFactStats
            rawCount={conflict.bear_raw_claim_count}
            uniqueCount={conflict.bear_unique_fact_count}
            agentCount={conflict.bear_distinct_agent_count}
            overlapRatio={conflict.bear_overlap_ratio}
          />
          <ConflictSideEvidence
            title="Bear evidence"
            items={conflict.bear_evidence}
            factGroups={conflict.bear_structure.evidence_facts}
          />
        </div>
      </div>
      <div className="conflict-evidence-strength">
        <span>Evidence strength: {(conflict.evidence_strength * 100).toFixed(0)}%</span>
        <div
          className="score-bar score-bar-secondary"
          role="img"
          aria-label={`Evidence strength ${(conflict.evidence_strength * 100).toFixed(0)} percent`}
        >
          <div className="score-bar-fill" style={{ width: `${conflict.evidence_strength * 100}%` }} />
        </div>
      </div>
    </article>
  );
}
