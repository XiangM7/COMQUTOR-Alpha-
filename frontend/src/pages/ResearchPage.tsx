import { useEffect, useState } from "react";
import { useNavigate } from "react-router-dom";
import { getReadiness, getResearchHistory } from "../api/client";
import { ApiError, describeApiError, describeApiErrorCode } from "../api/errors";
import type { ReadinessResponse, ResearchRunRecord } from "../api/types";
import { ResearchForm } from "../components/ResearchForm";
import { ErrorPanel } from "../components/ErrorPanel";
import { LoadingPanel } from "../components/LoadingPanel";
import { EmptyState } from "../components/EmptyState";
import { ReplayAllPanel } from "../components/ReplayAllPanel";
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
        {errorMessage}
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

  const pathForRun = (item: ResearchRunRecord) => {
    const destination =
      item.status === "completed" || item.status === "partial" ? "research" : "processing";
    return `/runs/${encodeURIComponent(item.run_id)}/${destination}`;
  };

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
            onClick={() => navigate(pathForRun(item))}
            onKeyDown={(event) => {
              if (event.key === "Enter" || event.key === " ") {
                event.preventDefault();
                navigate(pathForRun(item));
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
        describeApiErrorCode(result.error_code, result.message ?? undefined)
      );
      return;
    }
    if (result.run_id) {
      // HTTP 200 completed reuse: the canonical result already exists, so
      // go straight to it. Anything queued/running (HTTP 202, including an
      // in-flight reuse) goes to the Processing page, which polls real
      // progress and forwards to the results when the run finishes.
      const target =
        result.cache_disposition === "reused_completed" ? "research" : "processing";
      navigate(`/runs/${encodeURIComponent(result.run_id)}/${target}`, {
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

      <ReplayAllPanel />

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
