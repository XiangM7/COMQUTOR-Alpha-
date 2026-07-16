import { useId, useState } from "react";
import { REAL_MODE_ANALYSTS, type ResearchSubmissionRequest } from "../api/types";

const ANALYST_LABELS: Record<(typeof REAL_MODE_ANALYSTS)[number], string> = {
  market: "Market",
  news: "News",
  fundamentals: "Fundamentals",
  sentiment: "Sentiment",
};

export interface ResearchFormValues {
  ticker: string;
  analysisDate: string;
  selectedAnalysts: string[];
  forceRefresh: boolean;
}

interface ResearchFormProps {
  isSubmitting: boolean;
  onSubmit: (request: ResearchSubmissionRequest) => void;
}

function normalizeTicker(raw: string): string {
  return raw.trim().toUpperCase();
}

/**
 * Research submission form. Client-side validation only normalizes/guides
 * input (ticker trim+uppercase, at least one analyst selected) -- it never
 * replaces server-side validation, and it never collects a provider, model,
 * config, API key, or offline payload field (those simply do not exist as
 * inputs here).
 */
export function ResearchForm({ isSubmitting, onSubmit }: ResearchFormProps) {
  const [ticker, setTicker] = useState("");
  const [analysisDate, setAnalysisDate] = useState("");
  const [selectedAnalysts, setSelectedAnalysts] = useState<string[]>([...REAL_MODE_ANALYSTS]);
  const [forceRefresh, setForceRefresh] = useState(false);
  const [validationError, setValidationError] = useState<string | null>(null);
  const tickerId = useId();
  const dateId = useId();

  function toggleAnalyst(analyst: string) {
    setSelectedAnalysts((current) =>
      current.includes(analyst) ? current.filter((item) => item !== analyst) : [...current, analyst]
    );
  }

  function handleSubmit(event: React.FormEvent<HTMLFormElement>) {
    event.preventDefault();
    if (isSubmitting) return;

    const normalizedTicker = normalizeTicker(ticker);
    if (!normalizedTicker) {
      setValidationError("Enter a ticker symbol.");
      return;
    }
    if (selectedAnalysts.length === 0) {
      setValidationError("Select at least one analyst.");
      return;
    }
    setValidationError(null);

    const request: ResearchSubmissionRequest = {
      ticker: normalizedTicker,
      selected_analysts: selectedAnalysts,
    };
    if (analysisDate.trim()) request.analysis_date = analysisDate.trim();
    if (forceRefresh) request.force_refresh = true;

    onSubmit(request);
  }

  return (
    <form className="research-form" onSubmit={handleSubmit} noValidate>
      <div className="form-field">
        <label htmlFor={tickerId}>Ticker</label>
        <input
          id={tickerId}
          name="ticker"
          type="text"
          autoComplete="off"
          spellCheck={false}
          placeholder="e.g. NVDA"
          value={ticker}
          onChange={(event) => setTicker(event.target.value)}
          disabled={isSubmitting}
        />
      </div>

      <div className="form-field">
        <label htmlFor={dateId}>Analysis date (optional)</label>
        <input
          id={dateId}
          name="analysis_date"
          type="date"
          value={analysisDate}
          onChange={(event) => setAnalysisDate(event.target.value)}
          disabled={isSubmitting}
        />
      </div>

      <fieldset className="form-field">
        <legend>Analysts</legend>
        <div className="analyst-options">
          {REAL_MODE_ANALYSTS.map((analyst) => (
            <label key={analyst} className="checkbox-option">
              <input
                type="checkbox"
                checked={selectedAnalysts.includes(analyst)}
                onChange={() => toggleAnalyst(analyst)}
                disabled={isSubmitting}
              />
              {ANALYST_LABELS[analyst]}
            </label>
          ))}
        </div>
      </fieldset>

      <details className="advanced-options">
        <summary>Advanced options</summary>
        <label className="checkbox-option">
          <input
            type="checkbox"
            checked={forceRefresh}
            onChange={(event) => setForceRefresh(event.target.checked)}
            disabled={isSubmitting}
          />
          Force refresh (bypass a completed-run cache)
        </label>
      </details>

      {validationError ? (
        <p className="form-validation-error" role="alert">
          {validationError}
        </p>
      ) : null}

      <button type="submit" className="button button-primary" disabled={isSubmitting}>
        {isSubmitting ? "Submitting…" : "Start research"}
      </button>
    </form>
  );
}
