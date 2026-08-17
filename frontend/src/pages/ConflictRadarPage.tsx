import { useEffect, useState } from "react";
import { useParams } from "react-router-dom";
import { getResearchConflicts, getResearchRun } from "../api/client";
import { ApiError, describeApiError } from "../api/errors";
import type { CanonicalResearchResult, ConflictsResult } from "../api/types";
import { RunNavigation } from "../components/RunNavigation";
import { ErrorPanel } from "../components/ErrorPanel";
import { LoadingPanel } from "../components/LoadingPanel";
import { EmptyState } from "../components/EmptyState";
import { CandidateConflictCard } from "../components/CandidateConflictCard";
import { ConflictCard } from "../components/ConflictCard";
import { EvidenceList, type EvidenceItem } from "../components/EvidenceList";

function useConflictsPageData(runId: string | undefined) {
  const [conflicts, setConflicts] = useState<ConflictsResult | null>(null);
  const [research, setResearch] = useState<CanonicalResearchResult | null>(null);
  const [error, setError] = useState<ApiError | null>(null);
  const [isLoading, setIsLoading] = useState(false);
  const [reloadToken, setReloadToken] = useState(0);

  useEffect(() => {
    if (!runId) return;
    const controller = new AbortController();
    setIsLoading(true);
    setError(null);
    Promise.all([
      getResearchConflicts(runId, { signal: controller.signal }),
      getResearchRun(runId, { signal: controller.signal }),
    ])
      .then(([conflictsResult, researchResult]) => {
        if (controller.signal.aborted) return;
        setConflicts(conflictsResult);
        setResearch(researchResult);
      })
      .catch((cause: unknown) => {
        if (controller.signal.aborted) return;
        const apiError = cause instanceof ApiError ? cause : ApiError.network();
        if (!apiError.isAborted) setError(apiError);
      })
      .finally(() => {
        if (!controller.signal.aborted) setIsLoading(false);
      });
    return () => controller.abort();
  }, [runId, reloadToken]);

  return { conflicts, research, error, isLoading, reload: () => setReloadToken((token) => token + 1) };
}

function structureEvidence(
  structure: {
    claim_ids: string[];
    evidence: string[];
    match_scores: number[];
    alpha_id: string;
  },
  evidenceItems: { claim_id: string; claim_text: string; agent: string; match_score: number }[]
): EvidenceItem[] {
  // Prefer the API's per-claim bull/bear evidence (each claim carries its
  // own agent) over the structure's parallel arrays -- the structure's
  // deduplicated agents list cannot be positionally mapped onto claims.
  if (evidenceItems.length > 0) {
    return evidenceItems.map((item) => ({
      claimId: item.claim_id,
      side: structure.alpha_id,
      evidence: item.claim_text,
      matchScore: item.match_score,
      agent: item.agent || undefined,
    }));
  }
  return structure.claim_ids.map((claimId, index) => ({
    claimId,
    side: structure.alpha_id,
    evidence: structure.evidence[index],
    matchScore: structure.match_scores[index],
  }));
}

export function ConflictRadarPage() {
  const { runId } = useParams<{ runId: string }>();
  const { conflicts, research, error, isLoading, reload } = useConflictsPageData(runId);

  if (!runId) {
    return <EmptyState title="Missing run_id" />;
  }

  if (isLoading && !conflicts) {
    return (
      <div className="conflict-radar-page">
        <RunNavigation runId={runId} />
        <LoadingPanel label="Loading conflict analysis…" />
      </div>
    );
  }

  if (error) {
    return (
      <div className="conflict-radar-page">
        <RunNavigation runId={runId} />
        <ErrorPanel message={describeApiError(error)} onRetry={reload} />
      </div>
    );
  }

  if (!conflicts || !("conflicts" in conflicts)) {
    const errorCode = conflicts && "error_code" in conflicts ? conflicts.error_code : null;
    const runStatus = research && "status" in research ? research.status : null;
    let title = "Conflict analysis unavailable";
    let description = conflicts && "message" in conflicts ? conflicts.message ?? undefined : undefined;
    if (errorCode === "CONFLICTS_NOT_READY") {
      if (runStatus === "partial") {
        title = "This research run is only partially complete";
        description = "Conflict analysis did not run to completion for this research run.";
      } else {
        title = "Conflict analysis is not ready yet";
        description = "This research run has not produced conflict analysis yet.";
      }
    }
    return (
      <div className="conflict-radar-page">
        <RunNavigation runId={runId} />
        <EmptyState title={title} description={description} />
      </div>
    );
  }

  return (
    <div className="conflict-radar-page">
      <RunNavigation runId={runId} />

      <section className="panel main-conflict-panel">
        <h1>Conflict radar — {conflicts.ticker}</h1>
        <p className="conflict-radar-formula-note">
          Conflict formula: {conflicts.formula_version}
          {conflicts.activation_formula_version
            ? ` · Activation: ${conflicts.activation_formula_version}`
            : null}
        </p>
        {conflicts.main_conflict ? (
          <ConflictCard conflict={conflicts.main_conflict} isMain />
        ) : (
          <EmptyState
            title="No conflicts detected"
            description="No admitted structural conflict was found between Alphas for this research run. This does not mean the position carries no risk."
          />
        )}
      </section>

      {conflicts.conflicts.length > 0 ? (
        <section className="panel conflict-list-panel">
          <h2>All admitted conflicts</h2>
          <ul className="conflict-list">
            {conflicts.conflicts.map((conflict) => (
              <li key={conflict.conflict_id}>
                <ConflictCard conflict={conflict} isMain={conflict.conflict_id === conflicts.main_conflict?.conflict_id} />
              </li>
            ))}
          </ul>
        </section>
      ) : null}

      {conflicts.main_conflict ? (
        <section className="panel evidence-traceability-panel">
          <h2>Evidence traceability</h2>
          <EvidenceList
            title={`${conflicts.main_conflict.bull_structure.alpha_id} (bull side) evidence`}
            items={structureEvidence(
              conflicts.main_conflict.bull_structure,
              conflicts.main_conflict.bull_evidence
            )}
          />
          <EvidenceList
            title={`${conflicts.main_conflict.bear_structure.alpha_id} (bear side) evidence`}
            items={structureEvidence(
              conflicts.main_conflict.bear_structure,
              conflicts.main_conflict.bear_evidence
            )}
          />
        </section>
      ) : null}

      <section className="panel arbitration-summary-panel">
        <h2>Arbitration summary</h2>
        <dl className="arbitration-meta">
          <div>
            <dt>Declared pairs</dt>
            <dd>{conflicts.arbitration.declared_pair_count}</dd>
          </div>
          <div>
            <dt>Admitted</dt>
            <dd>{conflicts.arbitration.admitted_count}</dd>
          </div>
          <div>
            <dt>Suppressed</dt>
            <dd>{conflicts.arbitration.suppressed_count}</dd>
          </div>
          <div>
            <dt>Rejected</dt>
            <dd>{conflicts.arbitration.rejected_count}</dd>
          </div>
        </dl>
      </section>

      {/* Task B5_CONFLICT_RADAR_EVIDENCE_UI section 12: candidate/rejected
          pairs are never displayed as admitted conflicts, but a candidate
          conflict score -- however high -- must never be hidden entirely
          either; each shows exactly which B2 gate it failed. */}
      {conflicts.arbitration.candidate_evaluations.some((item) => item.outcome !== "admitted") ? (
        <section className="panel candidate-conflicts-panel">
          <h2>Candidate and rejected pairs</h2>
          <ul className="conflict-list">
            {conflicts.arbitration.candidate_evaluations
              .filter((item) => item.outcome !== "admitted")
              .map((item) => (
                <li key={`${item.alpha_a}__${item.alpha_b}`}>
                  <CandidateConflictCard evaluation={item} />
                </li>
              ))}
          </ul>
        </section>
      ) : null}
    </div>
  );
}
