import { useId, useState } from "react";
import type { ResearchSubmissionRequest } from "../api/types";

/** Display order is the frozen product order: Market, Sentiment, News,
 * Fundamentals. The public API vocabulary is exactly these four names --
 * TradingAgents' internal "social" key never appears in the UI. */
const ANALYST_OPTIONS: ReadonlyArray<{ value: string; label: string }> = [
  { value: "market", label: "Market" },
  { value: "sentiment", label: "Sentiment" },
  { value: "news", label: "News" },
  { value: "fundamentals", label: "Fundamentals" },
];

interface ResearchFormProps {
  isSubmitting: boolean;
  onSubmit: (request: ResearchSubmissionRequest) => void;
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
 * Research submission form. The only user inputs are ticker, analysis date,
 * and the analyst team -- there is no advanced-options section, no
 * force_refresh switch, and no provider/model/config/API-key/offline field
 * (those simply do not exist as inputs here; the server's fixed Research
 * Profile controls all execution configuration). Client-side validation
 * only normalizes/guides input; it never replaces server-side validation.
 */
export function ResearchForm({ isSubmitting, onSubmit }: ResearchFormProps) {
  const [ticker, setTicker] = useState("");
  const [analysisDate, setAnalysisDate] = useState(todayIsoDate);
  const [selectedAnalysts, setSelectedAnalysts] = useState<string[]>(
    ANALYST_OPTIONS.map((option) => option.value)
  );
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
    const trimmedDate = analysisDate.trim();
    if (trimmedDate && trimmedDate > todayIsoDate()) {
      setValidationError("Analysis date cannot be later than today.");
      return;
    }
    if (selectedAnalysts.length === 0) {
      setValidationError("Select at least one analyst.");
      return;
    }
    setValidationError(null);

    // Canonical order, deduplicated -- exactly the three user-controlled
    // fields, nothing else, ever.
    const orderedAnalysts = ANALYST_OPTIONS.map((option) => option.value).filter((value) =>
      selectedAnalysts.includes(value)
    );
    const request: ResearchSubmissionRequest = {
      ticker: normalizedTicker,
      selected_analysts: orderedAnalysts,
    };
    if (trimmedDate) request.analysis_date = trimmedDate;

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
        <label htmlFor={dateId}>Analysis date</label>
        <input
          id={dateId}
          name="analysis_date"
          type="date"
          value={analysisDate}
          max={todayIsoDate()}
          onChange={(event) => setAnalysisDate(event.target.value)}
          disabled={isSubmitting}
        />
      </div>

      <fieldset className="form-field">
        <legend>Analysts team</legend>
        <div className="analyst-options">
          {ANALYST_OPTIONS.map(({ value, label }) => (
            <label key={value} className="checkbox-option">
              <input
                type="checkbox"
                checked={selectedAnalysts.includes(value)}
                onChange={() => toggleAnalyst(value)}
                disabled={isSubmitting}
              />
              {label}
            </label>
          ))}
        </div>
      </fieldset>

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
