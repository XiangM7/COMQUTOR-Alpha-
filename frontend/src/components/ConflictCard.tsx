import type { AlphaConflict } from "../api/types";

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
        </div>
        <div className="conflict-side">
          <p className="conflict-side-role">Bear side</p>
          <p className="conflict-side-alpha">
            {conflict.bear_structure.alpha_id} &mdash; {conflict.bear_structure.alpha_name}
          </p>
          <p className="conflict-side-activation">
            Activation: {conflict.bear_structure.activation_score.toFixed(1)} ({conflict.bear_structure.status})
          </p>
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
