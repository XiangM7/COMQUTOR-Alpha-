import { useState } from "react";
import { Link } from "react-router-dom";
import { replayAllSavedOutputs } from "../api/client";
import { ApiError, describeApiError } from "../api/errors";
import type { ReplayAllResult } from "../api/types";
import { ErrorPanel } from "./ErrorPanel";

/** One-click batch replay of every saved TradingAgents raw output through
 * the current COMQUTOR architecture. Synchronous request/response (no
 * polling, no job queue) -- the confirmation dialog and pending state exist
 * purely to prevent duplicate submissions and set correct expectations,
 * never to imply a background job the user could navigate away from. */
export function ReplayAllPanel() {
  const [isConfirming, setIsConfirming] = useState(false);
  const [isRunning, setIsRunning] = useState(false);
  const [errorMessage, setErrorMessage] = useState<string | null>(null);
  const [result, setResult] = useState<ReplayAllResult | null>(null);

  async function handleStart() {
    setIsConfirming(false);
    setIsRunning(true);
    setErrorMessage(null);
    setResult(null);
    try {
      const outcome = await replayAllSavedOutputs();
      setResult(outcome);
    } catch (cause) {
      const apiError = cause instanceof ApiError ? cause : ApiError.network();
      setErrorMessage(describeApiError(apiError));
    } finally {
      setIsRunning(false);
    }
  }

  return (
    <section className="panel replay-all-panel">
      <h2>Reprocess saved outputs</h2>
      <p className="replay-all-description">
        Every saved TradingAgents output can be reprocessed with the current COMQUTOR architecture
        without rerunning TradingAgents or calling an LLM provider.
      </p>
      <button
        type="button"
        className="button button-primary"
        disabled={isRunning}
        onClick={() => setIsConfirming(true)}
      >
        {isRunning ? "Reprocessing…" : "Re-run all saved outputs with current architecture"}
      </button>

      {isConfirming ? (
        <div
          className="replay-all-dialog-backdrop"
          role="presentation"
          onClick={() => setIsConfirming(false)}
        >
          <div
            className="replay-all-dialog"
            role="dialog"
            aria-modal="true"
            aria-labelledby="replay-all-dialog-title"
            onClick={(event) => event.stopPropagation()}
          >
            <h3 id="replay-all-dialog-title">Re-run all saved outputs with current architecture</h3>
            <p>
              This will reprocess every saved TradingAgents output using the current COMQUTOR
              architecture.
            </p>
            <p>It will not rerun TradingAgents or call an LLM provider. Existing source runs will not be overwritten.</p>
            <div className="replay-all-dialog-actions">
              <button type="button" className="button button-secondary" onClick={() => setIsConfirming(false)}>
                Cancel
              </button>
              <button type="button" className="button button-primary" onClick={handleStart}>
                Start replay
              </button>
            </div>
          </div>
        </div>
      ) : null}

      {errorMessage ? <ErrorPanel message={errorMessage} onRetry={() => setIsConfirming(true)} /> : null}

      {result ? <ReplayAllSummary result={result} /> : null}
    </section>
  );
}

function ReplayAllSummary({ result }: { result: ReplayAllResult }) {
  return (
    <div className="replay-all-summary" role="status">
      <p className="replay-all-summary-headline">
        {result.total_runs_found} runs processed
        <br />
        {result.completed_count} completed
        {result.blocked_count > 0 ? <> · {result.blocked_count} blocked</> : null}
        {result.failed_count > 0 ? <> · {result.failed_count} failed</> : null}
      </p>
      {result.results.length === 0 ? (
        <p>No saved TradingAgents outputs were found under outputs/runs/.</p>
      ) : (
        <table className="replay-all-results-table">
          <caption className="visually-hidden">Architecture replay results</caption>
          <thead>
            <tr>
              <th scope="col">Ticker</th>
              <th scope="col">Source run</th>
              <th scope="col">Replay run</th>
              <th scope="col">Status</th>
            </tr>
          </thead>
          <tbody>
            {result.results.map((row) => (
              <tr key={row.source_run_id}>
                <td>{row.ticker ?? "Not available"}</td>
                <td>{row.source_run_id}</td>
                <td>
                  {row.status === "completed" && row.replay_run_id ? (
                    <Link to={`/runs/${encodeURIComponent(row.replay_run_id)}/research`}>
                      {row.replay_run_id}
                    </Link>
                  ) : (
                    row.replay_run_id ?? "Not available"
                  )}
                </td>
                <td>
                  <span className={`status-badge status-badge-${row.status}`}>
                    {row.status}
                    {row.error_code ? ` (${row.error_code})` : ""}
                  </span>
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      )}
    </div>
  );
}
