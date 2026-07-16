import type { ResearchRunStatus } from "../api/types";

interface RunStatusBannerProps {
  status: ResearchRunStatus | string;
  stage?: string | null;
  errorCode?: string | null;
  message?: string | null;
}

const STATUS_LABELS: Record<string, string> = {
  queued: "Queued",
  running: "Running",
  completed: "Completed",
  partial: "Partially completed",
  failed: "Failed",
};

/** Status is always communicated with text (never color alone) -- see the
 * `status-badge` text label plus the `data-status` attribute used purely for
 * styling. */
export function RunStatusBanner({ status, stage, errorCode, message }: RunStatusBannerProps) {
  const label = STATUS_LABELS[status] ?? status;
  return (
    <div className="run-status-banner" data-status={status} role="status" aria-live="polite">
      <span className={`status-badge status-badge-${status}`}>{label}</span>
      {stage ? <span className="run-status-stage">Stage: {stage}</span> : null}
      {status === "failed" && (errorCode || message) ? (
        <div className="run-status-error">
          {errorCode ? <span className="run-status-error-code">{errorCode}</span> : null}
          {message ? <span className="run-status-error-message">{message}</span> : null}
        </div>
      ) : null}
    </div>
  );
}
