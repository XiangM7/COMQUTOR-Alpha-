import { useEffect, useMemo } from "react";
import { Link, useNavigate, useParams } from "react-router-dom";
import { describeApiError } from "../api/errors";
import type { ResearchRunRecord } from "../api/types";
import { EmptyState } from "../components/EmptyState";
import { ErrorPanel } from "../components/ErrorPanel";
import { LoadingPanel } from "../components/LoadingPanel";
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

  return (
    <ol className="processing-stage-list" aria-label="Research stages">
      {plan.map((entry, index) => {
        const state =
          currentIndex < 0 ? "pending" : index < currentIndex ? "done" : index === currentIndex ? "current" : "pending";
        const marker = state === "done" ? "✓" : state === "current" ? "●" : "○";
        const stateLabel =
          state === "done" ? "completed" : state === "current" ? "in progress" : "pending";
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

  const record: ResearchRunRecord | null =
    pollStatus && "ticker" in pollStatus ? pollStatus : null;
  const statusFailure = pollStatus && !("ticker" in pollStatus) ? pollStatus : null;
  const runStatus = record?.status;

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
            <StageChecklist record={record} />
          </>
        ) : null}

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
              <button type="button" className="button button-secondary" onClick={refresh}>
                Retry
              </button>
              <Link to="/research" className="button button-primary">
                Return to Research
              </Link>
            </div>
          </div>
        ) : null}

        {pollError && !statusFailure ? (
          <ErrorPanel
            title="Connection issue"
            message={describeApiError(pollError)}
            onRetry={refresh}
          />
        ) : null}
      </section>
    </div>
  );
}
