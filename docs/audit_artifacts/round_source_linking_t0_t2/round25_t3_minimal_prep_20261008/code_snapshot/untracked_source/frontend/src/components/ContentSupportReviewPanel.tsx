import { useId, useState } from "react";
import { Link } from "react-router-dom";
import {
  getContentSupportReviews,
  getReevaluationExecutions,
  submitContentSupportReview,
} from "../api/client";
import { ApiError, describeApiError } from "../api/errors";
import type {
  ContentSupportReviewRecord,
  ContentSupportReviewVerdict,
  ReevaluationExecutionEntry,
} from "../api/types";

/**
 * Minimal viable human content-support review entrypoint (T1 verified-
 * support eligibility gate, 2026-09-28). Deliberately small: view the
 * claim's own linked source fragment (rendered by the caller, right above
 * this panel), choose a relation, enter a reviewer/rationale, save, and
 * trigger re-evaluation -- nothing else. This is NOT a standalone review
 * management system: there is no queue, no bulk actions, no separate
 * route. History is shown read-only (past reviews for this claim, past
 * re-evaluation executions for this run) so the reviewer can see prior
 * decisions without needing them repeated here.
 *
 * No authentication exists anywhere in this app (see OperatorPage's own
 * note) -- `reviewer` is always a manually-typed free-text label, never an
 * authenticated identity. This is stated in the UI itself, not implied.
 *
 * History protection: submitting a review never mutates this run's own
 * already-persisted data -- the server appends an independent review
 * record and creates a brand-new execution_id. A save failure is shown as
 * a failure (never silently treated as success), and the previous
 * saved/error state is preserved across a re-render so a reload never
 * loses what was already confirmed saved.
 */

const VERDICT_OPTIONS: ReadonlyArray<{ value: ContentSupportReviewVerdict; label: string }> = [
  { value: "SUPPORTS", label: "Supports this claim" },
  { value: "OPPOSES", label: "Opposes this claim" },
  { value: "BACKGROUND", label: "Background only" },
  { value: "CITATION_ONLY", label: "Citation only" },
  { value: "CONDITIONAL", label: "Conditional support" },
  { value: "NOT_APPLICABLE", label: "Not applicable" },
];

function formatTimestamp(value: string): string {
  const parsed = new Date(value);
  return Number.isNaN(parsed.getTime()) ? value : parsed.toLocaleString();
}

function ReviewHistoryList({ reviews }: { reviews: ContentSupportReviewRecord[] }) {
  if (reviews.length === 0) {
    return <p className="content-support-review-empty">No review submitted yet for this claim.</p>;
  }
  return (
    <ul className="content-support-review-history">
      {reviews.map((review, index) => (
        <li key={review.review_id ?? index} className="content-support-review-history-item">
          <span className="content-support-review-history-status">{review.status}</span>
          {" by "}
          <span className="content-support-review-history-reviewer">{review.reviewer}</span>
          {" · "}
          <span className="content-support-review-history-time">{formatTimestamp(review.reviewed_at)}</span>
          <p className="content-support-review-history-rationale">{review.rationale}</p>
        </li>
      ))}
    </ul>
  );
}

function ExecutionHistoryList({ runId, executions }: { runId: string; executions: ReevaluationExecutionEntry[] }) {
  if (executions.length === 0) {
    return null;
  }
  return (
    <div className="content-support-review-executions">
      <p className="content-support-review-executions-label">Past re-evaluations of run {runId}:</p>
      <ul>
        {executions.map((execution) => (
          <li key={execution.execution_id}>
            <Link to={`/runs/${encodeURIComponent(execution.execution_id)}/research`}>
              {formatTimestamp(execution.triggered_at)} ({execution.review_log_entry_count} review
              {execution.review_log_entry_count === 1 ? "" : "s"} applied)
            </Link>
          </li>
        ))}
      </ul>
    </div>
  );
}

export function ContentSupportReviewPanel({ runId, claimId }: { runId: string; claimId: string }) {
  const [status, setStatus] = useState<ContentSupportReviewVerdict>("SUPPORTS");
  const [reviewer, setReviewer] = useState("");
  const [rationale, setRationale] = useState("");
  const [saving, setSaving] = useState(false);
  const [saveError, setSaveError] = useState<string | null>(null);
  const [lastSaved, setLastSaved] = useState<ContentSupportReviewRecord | null>(null);
  const [lastExecutionId, setLastExecutionId] = useState<string | null>(null);
  const [history, setHistory] = useState<ContentSupportReviewRecord[] | null>(null);
  const [executions, setExecutions] = useState<ReevaluationExecutionEntry[] | null>(null);
  const [loadingHistory, setLoadingHistory] = useState(false);
  const [expanded, setExpanded] = useState(false);
  const statusId = useId();
  const reviewerId = useId();
  const rationaleId = useId();

  async function loadHistory() {
    setLoadingHistory(true);
    try {
      const [reviewsResult, executionsResult] = await Promise.all([
        getContentSupportReviews(runId, { claimId }),
        getReevaluationExecutions(runId),
      ]);
      setHistory(reviewsResult.status === "ok" ? reviewsResult.reviews : []);
      setExecutions(executionsResult.status === "ok" ? executionsResult.executions : []);
    } catch {
      // History is a read-only convenience -- a failure to load it must
      // never block the review form itself from being usable.
      setHistory([]);
      setExecutions([]);
    } finally {
      setLoadingHistory(false);
    }
  }

  function handleToggleExpanded() {
    const next = !expanded;
    setExpanded(next);
    if (next && history === null) {
      void loadHistory();
    }
  }

  async function handleSave() {
    if (saving) return;
    if (!reviewer.trim()) {
      setSaveError("Enter your name or identifier as the reviewer.");
      return;
    }
    if (!rationale.trim()) {
      setSaveError("Enter a rationale for this review.");
      return;
    }
    setSaving(true);
    setSaveError(null);
    try {
      const result = await submitContentSupportReview(runId, claimId, {
        status,
        reviewer: reviewer.trim(),
        rationale: rationale.trim(),
      });
      if (result.status !== "ok") {
        setSaveError(result.message ?? result.error_code ?? "The review could not be saved.");
        return;
      }
      setLastSaved(result.content_support_review);
      setLastExecutionId(
        result.reevaluation && result.reevaluation.status === "ok" ? result.reevaluation.execution_id : null
      );
      setRationale("");
      // Refresh history so the just-saved review/execution is visible
      // immediately, without requiring a full page reload.
      void loadHistory();
      setExpanded(true);
    } catch (cause) {
      setSaveError(cause instanceof ApiError ? describeApiError(cause) : "The review could not be saved.");
    } finally {
      setSaving(false);
    }
  }

  return (
    <div className="content-support-review-panel">
      <button
        type="button"
        className="content-support-review-toggle"
        onClick={handleToggleExpanded}
        aria-expanded={expanded}
      >
        {expanded ? "Hide review" : "Review this claim's source"}
      </button>
      {expanded ? (
        <div className="content-support-review-body">
          <p className="content-support-review-disclaimer">
            Reviewer identity is manually entered below -- this app has no sign-in, so it is never an
            authenticated identity.
          </p>
          <div className="form-field">
            <label htmlFor={statusId}>Relation to claim</label>
            <select
              id={statusId}
              value={status}
              onChange={(event) => setStatus(event.target.value as ContentSupportReviewVerdict)}
              disabled={saving}
            >
              {VERDICT_OPTIONS.map((option) => (
                <option key={option.value} value={option.value}>
                  {option.label}
                </option>
              ))}
            </select>
          </div>
          <div className="form-field">
            <label htmlFor={reviewerId}>Reviewer</label>
            <input
              id={reviewerId}
              type="text"
              value={reviewer}
              onChange={(event) => setReviewer(event.target.value)}
              placeholder="Your name or identifier"
              disabled={saving}
            />
          </div>
          <div className="form-field">
            <label htmlFor={rationaleId}>Rationale</label>
            <textarea
              id={rationaleId}
              value={rationale}
              onChange={(event) => setRationale(event.target.value)}
              placeholder="Why does the source content support/oppose/etc. this claim?"
              rows={3}
              disabled={saving}
            />
          </div>
          {saveError ? <p className="content-support-review-error">{saveError}</p> : null}
          <button type="button" onClick={() => void handleSave()} disabled={saving}>
            {saving ? "Saving…" : "Save review"}
          </button>
          {lastSaved ? (
            <p className="content-support-review-saved">
              Saved as {lastSaved.status} by {lastSaved.reviewer}.
              {lastExecutionId ? (
                <>
                  {" "}
                  Re-evaluation ready:{" "}
                  <Link to={`/runs/${encodeURIComponent(lastExecutionId)}/research`}>view results</Link>.
                </>
              ) : (
                " Re-evaluation did not complete -- the review itself is still saved."
              )}
            </p>
          ) : null}

          <div className="content-support-review-history-section">
            <h4>Review history for this claim</h4>
            {loadingHistory ? (
              <p>Loading…</p>
            ) : (
              <>
                <ReviewHistoryList reviews={history ?? []} />
                <ExecutionHistoryList runId={runId} executions={executions ?? []} />
              </>
            )}
          </div>
        </div>
      ) : null}
    </div>
  );
}
