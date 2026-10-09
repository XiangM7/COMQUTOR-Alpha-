import { useId, useState, type ReactNode } from "react";
import type { ResearchSubmissionRequest } from "../api/types";

/** Every run uses the full analyst team, in the frozen product order:
 * Market, Sentiment, News, Fundamentals. The public API vocabulary is exactly
 * these four names -- TradingAgents' internal "social" key never appears in
 * the UI. */
const ANALYST_TEAM: readonly string[] = ["market", "sentiment", "news", "fundamentals"];

interface ResearchFormProps {
  isSubmitting: boolean;
  onSubmit: (request: ResearchSubmissionRequest) => void;
  /** Live-research readiness guard (operational safety fix): when set, the
   * Start research button is disabled and the reason is shown beside it --
   * never let the user submit a live run that is doomed to record zero
   * Alpha activation because Week2's semantic pipeline isn't ready yet.
   * Undefined/null when there is nothing to block on (offline-only server,
   * or a fully-ready live pipeline). */
  disabledReason?: string | null;
  /** Control rendered before Start research (the Recent runs menu). It sits
   * outside the <form> element so it may contain its own form controls. */
  leadingAction?: ReactNode;
}

function normalizeTicker(raw: string): string {
  return raw.trim().toUpperCase();
}

/** Local calendar date as YYYY-MM-DD (matches the backend's date format). */
function todayIsoDate(): string {
  const now = new Date();
  const month = String(now.getMonth() + 1).padStart(2, "0");
  const day = String(now.getDate()).padStart(2, "0");
  return `${now.getFullYear()}-${month}-${day}`;
}

/**
 * Research submission form. The only user input is the ticker: the analysis
 * date is always today (sent explicitly, never left to a server default) and
 * the analyst team is always the full four -- there is no date picker, no
 * analyst selection, no advanced-options section, no force_refresh switch,
 * and no provider/model/config/API-key/offline field (the server's fixed
 * Research Profile controls all execution configuration). Client-side
 * validation only normalizes/guides input; it never replaces server-side
 * validation.
 */
export function ResearchForm({ isSubmitting, onSubmit, disabledReason, leadingAction }: ResearchFormProps) {
  const [ticker, setTicker] = useState("");
  const [validationError, setValidationError] = useState<string | null>(null);
  const tickerId = useId();
  const formId = useId();

  const hasTicker = normalizeTicker(ticker).length > 0;

  function handleSubmit(event: React.FormEvent<HTMLFormElement>) {
    event.preventDefault();
    if (isSubmitting || disabledReason) return;

    const normalizedTicker = normalizeTicker(ticker);
    if (!normalizedTicker) {
      setValidationError("Enter a ticker symbol.");
      return;
    }
    setValidationError(null);

    onSubmit({
      ticker: normalizedTicker,
      analysis_date: todayIsoDate(),
      selected_analysts: [...ANALYST_TEAM],
    });
  }

  return (
    <div className="research-form">
      <form id={formId} className="ticker-form" onSubmit={handleSubmit} noValidate>
        <label className="ticker-field" htmlFor={tickerId}>
          <span className="ticker-field-label">Ticker</span>
          {isSubmitting ? (
            // Plain text in the input's place: it is what flies into the
            // Processing heading, so it must be measurable as text.
            <span className="ticker-readout">
              <span data-transition="ticker" className="ticker-readout-text">
                {normalizeTicker(ticker)}
              </span>
            </span>
          ) : (
            <input
              id={tickerId}
              className="ticker-input"
              name="ticker"
              type="text"
              autoComplete="off"
              autoCapitalize="characters"
              spellCheck={false}
              placeholder="NVDA"
              value={ticker}
              onChange={(event) => setTicker(event.target.value)}
            />
          )}
        </label>
      </form>

      <div className="research-actions">
        {leadingAction}
        <button
          type="submit"
          form={formId}
          data-transition="cta"
          className={isSubmitting ? "cta-button cta-button-busy" : "cta-button"}
          disabled={isSubmitting || Boolean(disabledReason) || !hasTicker}
          aria-busy={isSubmitting}
        >
          {isSubmitting ? <span className="cta-spinner" aria-hidden="true" /> : null}
          <span>{isSubmitting ? "Starting…" : "Start research"}</span>
        </button>
      </div>

      {validationError ? (
        <p className="form-validation-error" role="alert">
          {validationError}
        </p>
      ) : null}
      {!isSubmitting && disabledReason ? (
        <p className="form-validation-error" role="alert">
          {disabledReason}
        </p>
      ) : null}
    </div>
  );
}
