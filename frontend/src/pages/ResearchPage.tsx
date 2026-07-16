import { useEffect, useState } from "react";
import { useNavigate } from "react-router-dom";
import { getReadiness, getResearchHistory } from "../api/client";
import { ApiError, describeApiError } from "../api/errors";
import type { ReadinessResponse, ResearchRunRecord } from "../api/types";
import { ResearchForm } from "../components/ResearchForm";
import { ErrorPanel } from "../components/ErrorPanel";
import { LoadingPanel } from "../components/LoadingPanel";
import { EmptyState } from "../components/EmptyState";
import { useResearchSubmission } from "../hooks/useResearchSubmission";

const REAL_EXECUTION_LABELS: Record<string, string> = {
  disabled: "Real execution disabled",
  configured: "Real execution configured",
  misconfigured: "Real execution misconfigured",
};

function ServerCapabilityBanner() {
  const [readiness, setReadiness] = useState<ReadinessResponse | null>(null);
  const [errorMessage, setErrorMessage] = useState<string | null>(null);

  useEffect(() => {
    const controller = new AbortController();
    getReadiness({ signal: controller.signal })
      .then(({ result }) => {
        if (!controller.signal.aborted) setReadiness(result);
      })
      .catch((cause: unknown) => {
        if (controller.signal.aborted) return;
        const apiError = cause instanceof ApiError ? cause : ApiError.network();
        if (!apiError.isAborted) setErrorMessage(describeApiError(apiError));
      });
    return () => controller.abort();
  }, []);

  if (errorMessage) {
    return (
      <p className="server-capability-banner server-capability-unknown">
        API readiness unknown: {errorMessage}
      </p>
    );
  }
  if (!readiness) {
    return <p className="server-capability-banner">Checking server status…</p>;
  }
  return (
    <p className={`server-capability-banner server-capability-${readiness.status}`}>
      API {readiness.status === "ready" ? "ready" : "not ready"} ·{" "}
      {REAL_EXECUTION_LABELS[readiness.real_execution] ?? readiness.real_execution}
    </p>
  );
}

function RecentRuns() {
  const navigate = useNavigate();
  const [items, setItems] = useState<ResearchRunRecord[] | null>(null);
  const [errorMessage, setErrorMessage] = useState<string | null>(null);

  useEffect(() => {
    const controller = new AbortController();
    getResearchHistory({ limit: 10 }, { signal: controller.signal })
      .then((result) => {
        if (controller.signal.aborted) return;
        if (result.status === "ok") {
          setItems(result.items);
        } else {
          setErrorMessage(result.message ?? "Recent research runs are unavailable.");
        }
      })
      .catch((cause: unknown) => {
        if (controller.signal.aborted) return;
        const apiError = cause instanceof ApiError ? cause : ApiError.network();
        if (!apiError.isAborted) setErrorMessage(describeApiError(apiError));
      });
    return () => controller.abort();
  }, []);

  if (errorMessage) {
    return <ErrorPanel message={errorMessage} />;
  }
  if (items === null) {
    return <LoadingPanel label="Loading recent research runs…" />;
  }
  if (items.length === 0) {
    return <EmptyState title="No research runs yet" description="Submit a ticker above to get started." />;
  }

  return (
    <table className="recent-runs-table">
      <caption className="visually-hidden">Recent research runs</caption>
      <thead>
        <tr>
          <th scope="col">Ticker</th>
          <th scope="col">Status</th>
          <th scope="col">Analysis date</th>
          <th scope="col">Created</th>
          <th scope="col">Analysts</th>
        </tr>
      </thead>
      <tbody>
        {items.map((item) => (
          <tr
            key={item.run_id}
            className="recent-runs-row"
            tabIndex={0}
            role="button"
            onClick={() => navigate(`/runs/${encodeURIComponent(item.run_id)}/research`)}
            onKeyDown={(event) => {
              if (event.key === "Enter" || event.key === " ") {
                event.preventDefault();
                navigate(`/runs/${encodeURIComponent(item.run_id)}/research`);
              }
            }}
          >
            <td>{item.ticker}</td>
            <td>
              <span className={`status-badge status-badge-${item.status}`}>{item.status}</span>
            </td>
            <td>{item.analysis_date ?? "Not available"}</td>
            <td>{item.created_at ?? "Not available"}</td>
            <td>{item.selected_analysts.join(", ") || "Not available"}</td>
          </tr>
        ))}
      </tbody>
    </table>
  );
}

export function ResearchPage() {
  const navigate = useNavigate();
  const { isSubmitting, errorMessage, submit } = useResearchSubmission();
  const [submissionError, setSubmissionError] = useState<string | null>(null);

  async function handleSubmit(request: Parameters<typeof submit>[0]) {
    setSubmissionError(null);
    const outcome = await submit(request);
    if (!outcome) return;

    const { result } = outcome;
    if (result.status === "failed" && result.error_code) {
      setSubmissionError(
        describeApiErrorCodeMessage(result.error_code, result.message ?? undefined)
      );
      return;
    }
    if (result.run_id) {
      navigate(`/runs/${encodeURIComponent(result.run_id)}/research`, {
        state: result.cache_disposition ? { cacheDisposition: result.cache_disposition } : undefined,
      });
    }
  }

  return (
    <div className="research-page">
      <section className="panel research-form-panel">
        <h1>Research a ticker</h1>
        <ServerCapabilityBanner />
        <ResearchForm isSubmitting={isSubmitting} onSubmit={handleSubmit} />
        {errorMessage ? <ErrorPanel message={errorMessage} /> : null}
        {submissionError ? <ErrorPanel message={submissionError} /> : null}
      </section>

      <section className="panel recent-runs-panel">
        <h2>Recent research runs</h2>
        <RecentRuns />
      </section>

      <section className="panel comqutor-explainer-panel">
        <h2>What makes COMQUTOR different</h2>
        <p>
          COMQUTOR does not just generate a stock summary. It maps agent evidence into structured
          claims, matches those claims against a fixed Alpha taxonomy, builds an Alpha structure
          graph, computes activation for every Alpha, detects structural conflicts between bullish
          and bearish Alphas, and keeps every claim traceable back to its evidence.
        </p>
      </section>
    </div>
  );
}

const ERROR_CODE_ACTIONS: Record<string, string> = {
  REAL_RUN_DISABLED: "Real TradingAgents execution is disabled on this server.",
  REAL_RUN_CONFIG_INVALID: "Real TradingAgents execution is misconfigured on this server.",
  REAL_FORCE_REFRESH_DISABLED: "Force refresh is disabled for real research runs on this server.",
  RUN_ID_CONFLICT: "That run_id already exists for a different request.",
  INVALID_FORCE_REFRESH: "force_refresh cannot be combined with an existing run_id.",
  RESEARCH_QUEUE_FULL: "The research queue is full. Try again shortly.",
  JOB_MANAGER_UNAVAILABLE: "The background research service is unavailable right now.",
  OFFLINE_DISABLED: "Offline research submissions are disabled on this server.",
  INVALID_ANALYST_SELECTION: "One or more selected analysts are not supported.",
  INTERNAL_ERROR: "The research request failed unexpectedly. Please try again.",
};

function describeApiErrorCodeMessage(errorCode: string, fallback?: string): string {
  return ERROR_CODE_ACTIONS[errorCode] ?? fallback ?? "The research request could not be submitted.";
}
