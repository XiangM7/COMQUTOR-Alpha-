import { useEffect, useMemo, useState } from "react";
import { Link, useNavigate, useParams } from "react-router-dom";
import { describeApiError, describeApiErrorCode } from "../api/errors";
import type { ResearchRunRecord } from "../api/types";
import { EmptyState } from "../components/EmptyState";
import { ErrorPanel } from "../components/ErrorPanel";
import { LoadingPanel } from "../components/LoadingPanel";
import { useResearchSubmission } from "../hooks/useResearchSubmission";
import { useRunPolling } from "../hooks/useRunPolling";

/** The frozen stage vocabulary in execution order (analyst stages are
 * filtered to the run's actual selection). Labels are text -- stage state
 * is additionally marked with a symbol and words, never color alone. */
const ANALYST_STAGE_BY_KEY: Record<string, { stage: string; label: string }> = {
  market: { stage: "market_analysis", label: "Market analysis" },
  sentiment: { stage: "sentiment_analysis", label: "Sentiment analysis" },
  news: { stage: "news_analysis", label: "News analysis" },
  fundamentals: { stage: "fundamentals_analysis", label: "Fundamentals analysis" },
};

const PRE_ANALYST_STAGES: ReadonlyArray<{ stage: string; label: string }> = [
  { stage: "queued", label: "Queued" },
  { stage: "initializing", label: "Initializing" },
];

const POST_ANALYST_STAGES: ReadonlyArray<{ stage: string; label: string }> = [
  { stage: "research_debate", label: "Research debate" },
  { stage: "trading_plan", label: "Trading plan" },
  { stage: "risk_review", label: "Risk review" },
  { stage: "raw_outputs_saved", label: "Saving agent outputs" },
  { stage: "structured_claims", label: "Structured claims" },
  { stage: "alpha_mapping", label: "Alpha mapping" },
  { stage: "structure_graph", label: "Structure graph" },
  { stage: "activation_scoring", label: "Activation scoring" },
  { stage: "conflict_analysis", label: "Conflict analysis" },
  { stage: "result_persistence", label: "Persisting results" },
  { stage: "result_assembly", label: "Assembling results" },
];

const ANALYST_ORDER = ["market", "sentiment", "news", "fundamentals"] as const;

function buildStagePlan(selectedAnalysts: string[]): Array<{ stage: string; label: string }> {
  const selected = new Set(selectedAnalysts);
  const analystStages = ANALYST_ORDER.filter((key) => selected.has(key)).flatMap((key) => {
    const entry = ANALYST_STAGE_BY_KEY[key];
    return entry ? [entry] : [];
  });
  return [...PRE_ANALYST_STAGES, ...analystStages, ...POST_ANALYST_STAGES];
}

function formatElapsed(totalSeconds: number): string {
  const minutes = Math.floor(totalSeconds / 60);
  const seconds = totalSeconds % 60;
  if (minutes >= 60) {
    const hours = Math.floor(minutes / 60);
    return `${hours}h ${minutes % 60}m ${seconds}s`;
  }
  return `${minutes}m ${seconds}s`;
}

function formatEtaRange(minSeconds: number, maxSeconds: number): string {
  const minMinutes = Math.ceil(minSeconds / 60);
  const maxMinutes = Math.ceil(maxSeconds / 60);
  if (maxMinutes <= 1) return "Estimated remaining time: less than a minute";
  if (minMinutes >= maxMinutes) {
    return `Estimated remaining time: approximately ${maxMinutes} minutes`;
  }
  return `Estimated remaining time: approximately ${minMinutes}–${maxMinutes} minutes`;
}

function EtaLine({ record }: { record: ResearchRunRecord }) {
  if (record.eta_status === "available") {
    const min = record.estimated_remaining_seconds_min;
    const max = record.estimated_remaining_seconds_max;
    if (min !== null && max !== null) {
      return <p className="processing-eta">{formatEtaRange(min, max)}</p>;
    }
  }
  if (record.eta_status === "estimating" || record.eta_status === null) {
    return <p className="processing-eta">Estimating completion time…</p>;
  }
  return null;
}

function StageChecklist({ record }: { record: ResearchRunRecord }) {
  const plan = useMemo(() => buildStagePlan(record.selected_analysts), [record.selected_analysts]);
  const currentIndex = plan.findIndex((entry) => entry.stage === record.current_stage);
  const completedUnits = Math.max(0, Math.floor(record.completed_units ?? 0));
  const completedPlanCount = Math.min(plan.length, PRE_ANALYST_STAGES.length + completedUnits);

  let inferredFailureIndex = -1;
  if (record.status === "failed") {
    if (currentIndex >= 0) {
      inferredFailureIndex = currentIndex;
    } else if (record.started_at === null) {
      inferredFailureIndex = 0;
    } else if (completedUnits === 0 && (record.progress_percent ?? 0) < 10) {
      inferredFailureIndex = 1;
    } else {
      inferredFailureIndex = Math.min(completedPlanCount, plan.length - 1);
    }
  }

  return (
    <ol className="processing-stage-list" aria-label="Research stages">
      {plan.map((entry, index) => {
        let state: "done" | "current" | "failed" | "pending" = "pending";
        if (record.status === "completed") {
          state = "done";
        } else if (record.status === "partial") {
          state = index < completedPlanCount ? "done" : "pending";
        } else if (record.status === "failed") {
          state =
            index < inferredFailureIndex
              ? "done"
              : index === inferredFailureIndex
                ? "failed"
                : "pending";
        } else if (currentIndex >= 0) {
          state = index < currentIndex ? "done" : index === currentIndex ? "current" : "pending";
        } else if (record.completed_units !== null) {
          state =
            index < completedPlanCount
              ? "done"
              : index === completedPlanCount
                ? "current"
                : "pending";
        }
        const marker = state === "done" ? "✓" : state === "current" || state === "failed" ? "●" : "○";
        const stateLabel =
          state === "done"
            ? "completed"
            : state === "current"
              ? "in progress"
              : state === "failed"
                ? "failed"
                : "pending";
        return (
          <li key={entry.stage} className={`processing-stage processing-stage-${state}`}>
            <span aria-hidden="true" className="processing-stage-marker">
              {marker}
            </span>
            <span className="processing-stage-label">{entry.label}</span>
            <span className="processing-stage-state">{stateLabel}</span>
          </li>
        );
      })}
    </ol>
  );
}

/**
 * Live progress view for one research run. Everything shown here comes
 * straight from the status endpoint's persisted telemetry -- the page never
 * grows the percentage on its own (no timers incrementing progress), and a
 * transient polling error never marks the run failed. Refreshing the page
 * restores the same run purely from the run_id in the URL.
 */
export function ProcessingPage() {
  const { runId } = useParams<{ runId: string }>();
  const navigate = useNavigate();
  const { status: pollStatus, error: pollError, refresh } = useRunPolling(runId);
  const {
    isSubmitting: isRetrying,
    errorMessage: retryRequestError,
    submit: retryResearch,
  } = useResearchSubmission();
  const [retryResponseError, setRetryResponseError] = useState<string | null>(null);

  const record: ResearchRunRecord | null =
    pollStatus && "ticker" in pollStatus ? pollStatus : null;
  const statusFailure = pollStatus && !("ticker" in pollStatus) ? pollStatus : null;
  const runStatus = record?.status;

  async function handleRetry() {
    if (!record || isRetrying) return;
    setRetryResponseError(null);
    const request = {
      ticker: record.ticker,
      selected_analysts: record.selected_analysts,
      ...(record.analysis_date ? { analysis_date: record.analysis_date } : {}),
    };
    const outcome = await retryResearch(request);
    if (!outcome) return;
    const { result, httpStatus } = outcome;
    if (result.status === "failed") {
      setRetryResponseError(
        result.error_code
          ? describeApiErrorCode(result.error_code, result.message ?? undefined)
          : result.message || "The research request could not be submitted."
      );
      return;
    }
    if (!result.run_id) {
      setRetryResponseError("The research request did not return a run identifier.");
      return;
    }
    const destination =
      httpStatus === 200 && result.cache_disposition === "reused_completed"
        ? "research"
        : "processing";
    navigate(`/runs/${encodeURIComponent(result.run_id)}/${destination}`);
  }

  useEffect(() => {
    if (runStatus !== "completed" || !runId) return;
    const timer = setTimeout(() => {
      navigate(`/runs/${encodeURIComponent(runId)}/research`);
    }, 1200);
    return () => clearTimeout(timer);
  }, [runStatus, runId, navigate]);

  if (!runId) {
    return <EmptyState title="Missing run_id" description="No research run was specified." />;
  }

  const percent = record?.progress_percent;

  return (
    <div className="processing-page">
      <section className="panel processing-panel">
        <h1>{record?.ticker ? `Analyzing ${record.ticker}` : "Analyzing research run"}</h1>

        {record?.profile_display_name ? (
          <p className="processing-profile">Research profile: {record.profile_display_name}</p>
        ) : null}

        {!pollStatus && !pollError ? <LoadingPanel label="Loading run status…" /> : null}

        {statusFailure ? (
          <ErrorPanel
            title="Run status unavailable"
            message={statusFailure.message || "The run status could not be loaded."}
            onRetry={refresh}
            retryLabel="Refresh status"
          />
        ) : null}

        {record && (runStatus === "queued" || runStatus === "running") ? (
          <>
            <div
              className="processing-progressbar"
              role="progressbar"
              aria-valuemin={0}
              aria-valuemax={100}
              {...(percent !== null && percent !== undefined ? { "aria-valuenow": percent } : {})}
              aria-label="Research progress"
            >
              <div
                className="processing-progressbar-fill"
                style={{ width: `${percent ?? 0}%` }}
              />
            </div>
            <p className="processing-progress-summary">
              {percent !== null && percent !== undefined
                ? `${percent}% complete`
                : "Progress reporting is not available for this run yet."}
              {record.completed_units !== null && record.total_units !== null
                ? ` · ${record.completed_units} of ${record.total_units} steps`
                : ""}
            </p>
            {record.elapsed_seconds !== null ? (
              <p className="processing-elapsed">Elapsed time: {formatElapsed(record.elapsed_seconds)}</p>
            ) : null}
            <EtaLine record={record} />
            {record.progress_message ? (
              <p className="processing-current-step">Current step: {record.progress_message}</p>
            ) : null}
          </>
        ) : null}

        {record ? <StageChecklist record={record} /> : null}

        {runStatus === "completed" ? (
          <div className="processing-complete" role="status">
            <p>Research complete. Opening results…</p>
            <Link to={`/runs/${encodeURIComponent(runId)}/research`} className="button button-primary">
              Open results now
            </Link>
          </div>
        ) : null}

        {runStatus === "partial" ? (
          <div className="processing-partial" role="status">
            <p>
              This research run finished only partially -- some stages did not produce results.
              The available results can still be reviewed.
            </p>
            <Link to={`/runs/${encodeURIComponent(runId)}/research`} className="button button-primary">
              Open partial results
            </Link>
          </div>
        ) : null}

        {runStatus === "failed" && record ? (
          <div className="processing-failed">
            <ErrorPanel
              title="Research run failed"
              message={record.message || "The research run could not be completed."}
            />
            {record.error_code ? (
              <p className="processing-error-code">
                Error code: <code>{record.error_code}</code>
              </p>
            ) : null}
            <div className="processing-failed-actions">
              <button
                type="button"
                className="button button-primary"
                onClick={handleRetry}
                disabled={isRetrying}
              >
                {isRetrying ? "Retrying…" : "Retry research"}
              </button>
              <button type="button" className="button button-secondary" onClick={refresh}>
                Refresh status
              </button>
              <Link to="/research" className="button button-secondary">
                Return to Research
              </Link>
            </div>
            {retryRequestError || retryResponseError ? (
              <ErrorPanel
                title="Retry could not start"
                message={retryResponseError ?? retryRequestError ?? "The retry could not be submitted."}
              />
            ) : null}
          </div>
        ) : null}

        {pollError && !statusFailure ? (
          <ErrorPanel
            title="Connection issue"
            message={describeApiError(pollError)}
            onRetry={refresh}
            retryLabel="Refresh status"
          />
        ) : null}
      </section>
    </div>
  );
}
