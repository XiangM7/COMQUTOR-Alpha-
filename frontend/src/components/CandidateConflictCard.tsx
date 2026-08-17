import type { ConflictCandidateEvaluation } from "../api/types";
import { ConflictEvidenceSections } from "./ConflictEvidenceSections";

// Task B5_CONFLICT_RADAR_EVIDENCE_UI section 12: a candidate/rejected pair
// must never be displayed as if it were an admitted conflict, and must show
// exactly which B2 gate it failed (or, when it never reached B2 at all, say
// so honestly rather than implying a B2 verdict that never happened).

function bull(evaluation: ConflictCandidateEvaluation): string | null {
  return evaluation.bull_alpha_id ?? null;
}

function bear(evaluation: ConflictCandidateEvaluation): string | null {
  return evaluation.bear_alpha_id ?? null;
}

export function CandidateConflictCard({ evaluation }: { evaluation: ConflictCandidateEvaluation }) {
  const admissibility = evaluation.admissibility;
  const bullAlphaId = bull(evaluation);
  const bearAlphaId = bear(evaluation);
  const reachedB2 = admissibility != null;

  return (
    <article className="conflict-card candidate-conflict-card">
      <header className="conflict-card-header">
        <h3>
          {evaluation.alpha_a} vs {evaluation.alpha_b}
        </h3>
        <span className="conflict-card-badge conflict-card-badge-candidate">
          {reachedB2 ? "Candidate conflict" : "Not evaluated"}
        </span>
      </header>
      {reachedB2 ? (
        <p className="candidate-conflict-note">
          This pair was evaluated but did not clear the B2 Conflict Evidence
          Admissibility gate -- shown here for audit, never as an admitted
          conflict.
        </p>
      ) : (
        <p className="candidate-conflict-note">
          This declared pair was rejected before B2 evaluation ({evaluation.reason_codes.join(", ")}) --
          never a candidate conflict with a B2 gate result to show.
        </p>
      )}
      {admissibility ? (
        <dl className="candidate-conflict-admissibility">
          <div>
            <dt>Bull score{bullAlphaId ? ` (${bullAlphaId})` : ""}</dt>
            <dd>{admissibility.bull_score != null ? admissibility.bull_score.toFixed(1) : "unavailable"}</dd>
          </div>
          <div>
            <dt>Bear score{bearAlphaId ? ` (${bearAlphaId})` : ""}</dt>
            <dd>{admissibility.bear_score != null ? admissibility.bear_score.toFixed(1) : "unavailable"}</dd>
          </div>
          <div>
            <dt>Bull supporting evidence facts</dt>
            <dd>{admissibility.bull_supporting_evidence_count}</dd>
          </div>
          <div>
            <dt>Bear supporting evidence facts</dt>
            <dd>{admissibility.bear_supporting_evidence_count}</dd>
          </div>
          <div>
            <dt>Bull ticker-specific support</dt>
            <dd>{admissibility.bull_ticker_specific_support_count}</dd>
          </div>
          <div>
            <dt>Bear ticker-specific support</dt>
            <dd>{admissibility.bear_ticker_specific_support_count}</dd>
          </div>
          <div>
            <dt>B2 reason codes</dt>
            <dd>{admissibility.reason_codes.join(", ") || "none"}</dd>
          </div>
        </dl>
      ) : null}
      {evaluation.evidence_ui && bullAlphaId && bearAlphaId ? (
        <ConflictEvidenceSections
          evidenceUi={evaluation.evidence_ui}
          bullAlphaId={bullAlphaId}
          bearAlphaId={bearAlphaId}
        />
      ) : null}
    </article>
  );
}
