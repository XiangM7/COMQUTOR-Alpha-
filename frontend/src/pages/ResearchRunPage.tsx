import { Link, useLocation, useParams } from "react-router-dom";
import { RunNavigation } from "../components/RunNavigation";
import { RunStatusBanner } from "../components/RunStatusBanner";
import { ErrorPanel } from "../components/ErrorPanel";
import { LoadingPanel } from "../components/LoadingPanel";
import { EmptyState } from "../components/EmptyState";
import { useRunPolling } from "../hooks/useRunPolling";
import { useResearchRun } from "../hooks/useResearchRun";
import { describeApiError } from "../api/errors";

function shortenRunId(runId: string): string {
  return runId.length > 12 ? `${runId.slice(0, 8)}…${runId.slice(-4)}` : runId;
}

function isTerminalStatus(status: string | undefined): boolean {
  return status === "completed" || status === "partial" || status === "failed";
}

export function ResearchRunPage() {
  const { runId } = useParams<{ runId: string }>();
  const location = useLocation();
  const cacheDisposition =
    location.state && typeof location.state === "object" && "cacheDisposition" in location.state
      ? String((location.state as { cacheDisposition?: string }).cacheDisposition ?? "")
      : null;

  const { status: pollStatus, error: pollError, refresh } = useRunPolling(runId);
  const currentStatus = pollStatus && "status" in pollStatus ? pollStatus.status : undefined;
  const terminal = isTerminalStatus(currentStatus);
  // A failed run never has a canonical result/agent-outputs worth fetching
  // -- only completed/partial do.
  const shouldLoadResult = terminal && currentStatus !== "failed";
  const { research, agentOutputs, isLoading: isLoadingResult, error: resultError } = useResearchRun(
    shouldLoadResult ? runId ?? null : null
  );

  if (!runId) {
    return <EmptyState title="Missing run_id" description="No research run was specified." />;
  }

  return (
    <div className="research-run-page">
      <RunNavigation runId={runId} />

      <section className="panel run-header-panel">
        <div className="run-header-row">
          <div>
            <h1>{("ticker" in (pollStatus ?? {}) && (pollStatus as { ticker?: string }).ticker) || "Research run"}</h1>
            <p className="run-id-display">
              Run ID: <code>{shortenRunId(runId)}</code>
            </p>
          </div>
          <button type="button" className="button button-secondary" onClick={refresh}>
            Refresh
          </button>
        </div>
        <dl className="run-header-meta">
          {"analysis_date" in (pollStatus ?? {}) ? (
            <div>
              <dt>Analysis date</dt>
              <dd>{(pollStatus as { analysis_date?: string | null }).analysis_date ?? "Not available"}</dd>
            </div>
          ) : null}
          {cacheDisposition ? (
            <div>
              <dt>Cache disposition</dt>
              <dd>{cacheDisposition}</dd>
            </div>
          ) : null}
        </dl>
        {pollStatus ? (
          <RunStatusBanner
            status={currentStatus ?? "queued"}
            stage={"stage" in pollStatus ? pollStatus.stage : null}
            errorCode={"error_code" in pollStatus ? pollStatus.error_code : null}
            message={"message" in pollStatus ? pollStatus.message : null}
          />
        ) : (
          <LoadingPanel label="Loading run status…" />
        )}
        {pollError ? (
          <ErrorPanel
            title="Connection issue"
            message={describeApiError(pollError)}
            onRetry={refresh}
          />
        ) : null}
      </section>

      {currentStatus === "failed" ? (
        <section className="panel run-failed-panel">
          <h2>This research run failed</h2>
          <p>See the error details above.</p>
          <Link to="/research" className="button button-primary">
            Back to Research
          </Link>
        </section>
      ) : null}

      {!terminal ? (
        <section className="panel">
          <LoadingPanel label={`Research run is ${currentStatus ?? "in progress"}. This page updates automatically.`} />
        </section>
      ) : null}

      {shouldLoadResult ? (
        <>
          {isLoadingResult ? <LoadingPanel label="Loading research results…" /> : null}
          {resultError ? <ErrorPanel message={describeApiError(resultError)} /> : null}
          {research && "summary" in research ? (
            <section className="panel research-summary-panel">
              <h2>Research summary</h2>
              <p>{research.summary}</p>
            </section>
          ) : null}

          <section className="panel analyst-outputs-panel">
            <h2>Analyst findings</h2>
            {agentOutputs && "structured_agent_outputs" in agentOutputs ? (
              agentOutputs.structured_agent_outputs.length > 0 ? (
                <ul className="analyst-output-list">
                  {agentOutputs.structured_agent_outputs.map((record) => (
                    <li key={record.claim_id} className="analyst-output-card">
                      <header>
                        <span className="analyst-output-agent">{record.agent}</span>
                        <span className={`analyst-output-direction analyst-output-direction-${record.direction}`}>
                          {record.direction}
                        </span>
                      </header>
                      <p className="analyst-output-claim">{record.claim}</p>
                      <p className="analyst-output-evidence">{record.evidence}</p>
                      <p className="analyst-output-meta">
                        Confidence {(record.confidence * 100).toFixed(0)}% · <code>{record.claim_id}</code>
                      </p>
                    </li>
                  ))}
                </ul>
              ) : (
                <EmptyState title="No structured analyst outputs yet" />
              )
            ) : null}
          </section>
        </>
      ) : null}

      <section className="panel comqutor-explainer-panel">
        <h2>Why this is not a typical AI stock summary</h2>
        <p>
          Instead of producing one free-text opinion, COMQUTOR converts agent evidence into
          structured claims, maps them onto a fixed Alpha taxonomy, assembles an Alpha structure
          graph, scores activation for every Alpha, detects structural conflicts, and keeps every
          claim traceable to its source evidence. It does not predict outcomes, guarantee profit,
          or eliminate investment risk.
        </p>
      </section>
    </div>
  );
}
