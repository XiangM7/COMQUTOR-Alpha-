import { useEffect, useLayoutEffect, useRef, useState } from "react";
import { Link, useNavigate, useParams } from "react-router-dom";
import { describeApiError, describeApiErrorCode } from "../api/errors";
import type { ResearchRunRecord } from "../api/types";
import { EmptyState } from "../components/EmptyState";
import { ErrorPanel } from "../components/ErrorPanel";
import { LoadingPanel } from "../components/LoadingPanel";
import { PipelineScene } from "../components/PipelineScene";
import { PriceHistoryCard } from "../components/PriceHistoryCard";
import { ProgressSummary } from "../components/ProgressSummary";
import { StagesPanel } from "../components/StagesPanel";
import { useElapsedSince } from "../hooks/useElapsedSince";
import { usePriceHistory } from "../hooks/usePriceHistory";
import { useResearchSubmission } from "../hooks/useResearchSubmission";
import { useRunNotification } from "../hooks/useRunNotification";
import { useRunPolling } from "../hooks/useRunPolling";
import {
  ANALYST_ORDER,
  computeStageProgress,
  describeCaption,
  describeEta,
  formatDuration,
  type StageProgressInput,
} from "../utils/processingStages";
import { formatAnalysisDate } from "../utils/runFormat";
import { peekRunHandoff, playRunEntrance, takeRunHandoff } from "../utils/transitionHandoff";
import { canAnimate } from "../utils/motion";

const FULL_ANALYST_TEAM: readonly string[] = ANALYST_ORDER;

function describeAnalysts(selected: readonly string[]): string {
  const ordered = ANALYST_ORDER.filter((key) => selected.includes(key));
  if (ordered.length === ANALYST_ORDER.length) return "all four analysts";
  if (ordered.length === 0) return "";
  const names = ordered.map((key) => key.charAt(0).toUpperCase() + key.slice(1));
  return `${names.join(", ")} ${ordered.length === 1 ? "analyst" : "analysts"}`;
}

/** Width, in percentage points, of the band that marks the stretch of the
 * bar being worked on: from the reported percentage to what it will be once
 * the current step completes. Arithmetic over reported values only -- it
 * never changes the percentage itself. */
function activeBandWidth(record: ResearchRunRecord): number {
  const percent = record.progress_percent;
  const done = record.completed_units;
  const total = record.total_units;
  if (percent === null || done === null || total === null || total <= 0) return 0;
  const next = Math.min(100, Math.round(((done + 1) / total) * 100));
  return Math.max(0, next - percent);
}

function pageTitle(ticker: string | undefined, record: ResearchRunRecord | null): string | null {
  if (!ticker) return null;
  switch (record?.status) {
    case "completed":
      return `Done · ${ticker}`;
    case "partial":
      return `Partial · ${ticker}`;
    case "failed":
      return `Failed · ${ticker}`;
    default:
      return record?.progress_percent != null ? `${record.progress_percent}% · ${ticker}` : `Researching · ${ticker}`;
  }
}

/**
 * Live progress view for one research run. Everything shown here comes
 * straight from the status endpoint's persisted telemetry -- the page never
 * grows the percentage on its own (no timers incrementing progress), and a
 * transient polling error never marks the run failed. Time-based text (the
 * estimate and the elapsed clock) counts in real time between polls and is
 * re-calibrated by every poll. Refreshing the page restores the same run
 * purely from the run_id in the URL.
 */
export function ProcessingPage() {
  const { runId } = useParams<{ runId: string }>();
  const navigate = useNavigate();
  const { status: pollStatus, error: pollError, receivedAt, refresh } = useRunPolling(runId);
  const {
    isSubmitting: isRetrying,
    errorMessage: retryRequestError,
    submit: retryResearch,
  } = useResearchSubmission();
  const [retryResponseError, setRetryResponseError] = useState<string | null>(null);
  // Present only when this page was opened by "Start research" just now.
  const [handoff] = useState(() => (runId ? peekRunHandoff(runId) : null));
  const tickerRef = useRef<HTMLSpanElement>(null);
  const trackRef = useRef<HTMLDivElement>(null);

  const record: ResearchRunRecord | null =
    pollStatus && "ticker" in pollStatus ? pollStatus : null;
  const statusFailure = pollStatus && !("ticker" in pollStatus) ? pollStatus : null;
  const runStatus = record?.status;
  const isActive = runStatus === "queued" || runStatus === "running";

  const ticker = record?.ticker ?? handoff?.ticker;
  const analysisDate = record ? record.analysis_date : (handoff?.analysisDate ?? null);
  const selectedAnalysts = record?.selected_analysts ?? handoff?.selectedAnalysts ?? FULL_ANALYST_TEAM;

  const sinceSeconds = useElapsedSince(receivedAt, isActive);
  const notification = useRunNotification(runId, ticker, runStatus);
  const priceHistory = usePriceHistory(ticker, analysisDate);

  const stageInput: StageProgressInput = record ?? {
    selected_analysts: [...selectedAnalysts],
    status: "queued",
    current_stage: null,
    completed_units: null,
    progress_percent: null,
    started_at: null,
  };
  const progress = computeStageProgress(stageInput);

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

  // Research -> Processing: the ticker flies into the heading and the Start
  // button turns into the progress track. Consumed once, so a refresh or a
  // back step never replays it.
  useLayoutEffect(() => {
    if (!runId) return;
    const taken = takeRunHandoff(runId);
    if (!taken?.geometry || !canAnimate()) return;
    window.scrollTo(0, 0);
    playRunEntrance(taken.geometry, { ticker: tickerRef.current, track: trackRef.current });
  }, [runId]);

  // Tab title: progress at a glance while the tab is in the background.
  const title = pageTitle(ticker, record);
  useEffect(() => {
    if (!title) return;
    const previous = document.title;
    document.title = title;
    return () => {
      document.title = previous;
    };
  }, [title]);

  if (!runId) {
    return <EmptyState title="Missing run_id" description="No research run was specified." />;
  }

  const showLayout = record !== null || handoff !== null;
  const percent = record ? (record.progress_percent ?? null) : handoff ? 0 : null;
  const eta = record
    ? describeEta(record, sinceSeconds)
    : { headline: "Estimating time…", basis: "Waiting for the first update" };
  const basis =
    record && isActive && percent === null ? "Progress reporting is not available for this run yet." : eta.basis;
  const elapsed =
    record && isActive && record.elapsed_seconds !== null
      ? formatDuration(record.elapsed_seconds + sinceSeconds)
      : null;
  const caption = describeCaption(record, progress);
  const subtitle = [
    analysisDate ? `Analysis date ${formatAnalysisDate(analysisDate)}` : "",
    describeAnalysts(selectedAnalysts),
  ]
    .filter(Boolean)
    .join(", ");
  const resultsPath = `/runs/${encodeURIComponent(runId)}/research`;

  return (
    <div className={handoff ? "processing-page processing-enter" : "processing-page"}>
      <Link to="/research" className="processing-back">
        <svg aria-hidden="true" width="7" height="12" viewBox="0 0 7 12" fill="none" stroke="currentColor" strokeWidth="1.6" strokeLinecap="round" strokeLinejoin="round">
          <path d="M5.75 1.25 1.25 6l4.5 4.75" />
        </svg>
        Research
      </Link>

      <div className="processing-title-row">
        <h1 className="processing-title">
          {ticker ? (
            <>
              <span className="visually-hidden">Analyzing </span>
              <span ref={tickerRef} className="processing-ticker">
                {ticker}
              </span>
            </>
          ) : (
            "Analyzing research run"
          )}
        </h1>
        {subtitle ? <p className="processing-subtitle rise-1">{subtitle}</p> : null}
      </div>

      {!pollStatus && !pollError && !handoff ? <LoadingPanel label="Loading run status…" /> : null}

      {statusFailure ? (
        <ErrorPanel
          title="Run status unavailable"
          message={statusFailure.message || "The run status could not be loaded."}
          onRetry={refresh}
          retryLabel="Refresh status"
        />
      ) : null}

      {pollError && !statusFailure ? (
        <ErrorPanel
          title="Connection issue"
          message={describeApiError(pollError)}
          onRetry={refresh}
          retryLabel="Refresh status"
        />
      ) : null}

      {showLayout ? (
        <div className="processing-layout">
          <div className="processing-main">
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
                <div className="processing-actions">
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
            ) : (
              <ProgressSummary
                headline={eta.headline}
                percent={percent}
                activeBandWidth={record && isActive ? activeBandWidth(record) : 0}
                basis={basis}
                elapsed={elapsed}
                trackRef={trackRef}
              >
                {runStatus === "completed" ? (
                  <div className="processing-actions">
                    <Link to={resultsPath} className="cta-link">
                      View results
                    </Link>
                  </div>
                ) : null}
                {runStatus === "partial" ? (
                  <div className="processing-partial" role="status">
                    <p>
                      This research run finished only partially -- some stages did not produce results.
                      The available results can still be reviewed.
                    </p>
                    <div className="processing-actions">
                      <Link to={resultsPath} className="cta-link">
                        Open partial results
                      </Link>
                    </div>
                  </div>
                ) : null}
              </ProgressSummary>
            )}

            <div className="rise-3">
              <PipelineScene progress={progress} caption={caption} live={isActive || record === null} />
            </div>
            {priceHistory ? (
              <div className="rise-3">
                <PriceHistoryCard history={priceHistory} />
              </div>
            ) : null}
          </div>

          <StagesPanel className="rise-3" progress={progress} notification={notification} showNotify={isActive || record === null} />
        </div>
      ) : null}
    </div>
  );
}
