interface ErrorPanelProps {
  title?: string;
  message: string;
  onRetry?: () => void;
  retryLabel?: string;
}

/** Safe, user-facing error display -- never renders a raw error object, a
 * traceback, or a JSON dump. `message` must already be reviewed, safe copy
 * (see api/errors.ts's describeApiError). */
export function ErrorPanel({ title = "Something went wrong", message, onRetry, retryLabel = "Retry" }: ErrorPanelProps) {
  return (
    <div className="panel error-panel" role="alert">
      <p className="error-panel-title">{title}</p>
      <p className="error-panel-message">{message}</p>
      {onRetry ? (
        <button type="button" className="button button-secondary" onClick={onRetry}>
          {retryLabel}
        </button>
      ) : null}
    </div>
  );
}
