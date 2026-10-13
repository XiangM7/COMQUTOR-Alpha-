import { useEffect, useState } from "react";
import { getKeyConclusions } from "../api/client";
import { ApiError, describeApiError } from "../api/errors";
import type { KeyConclusionRow, KeyConclusionsView } from "../api/evidenceTrace";
import { EvidenceTraceDetail } from "./EvidenceTraceDetail";
import "./evidenceTrace.css";

/**
 * T1 closure -- verification status of the report's important summary and final investment conclusion.
 *
 * Lists the claims written by the final-decision agents (portfolio manager, the research manager's verdict, the
 * trader) with FOUR separate statuses per claim -- source support, Alpha match, stance, official scoring -- and the
 * reason for each. "Not linked", "partly supported", "verification not completed (technical)" and "relation not
 * established" are different states with different reasons, never one blended flag; and the Agent writing
 * "verified" in its own text is shown as the Agent's wording beside the system's own result, never in place of it.
 * Ordinary commentary needs no source link and is not verified here; this panel does not trigger any verification.
 */

function StatusCell({ code, reason, label }: { code: string; reason: string; label: string }) {
  return (
    <td className={`key-conclusion-status key-conclusion-status-${code.toLowerCase().replace(/_/g, "-")}`} title={reason}>
      <span className="evidence-trace-chip">{code}</span>
      <span className="key-conclusion-status-label">{label}</span>
    </td>
  );
}

function ConclusionRow({ runId, row }: { runId: string; row: KeyConclusionRow }) {
  const [open, setOpen] = useState(false);
  return (
    <>
      <tr className="key-conclusion-row">
        <td className="key-conclusion-text">
          {row.agent_wording.self_labeled_verified ? (
            <span className="evidence-trace-chip evidence-trace-chip-warning" title={row.agent_wording.note ?? undefined}>
              Agent wrote “verified”
            </span>
          ) : null}{" "}
          {row.text}
          <div>
            <button
              type="button"
              className="button button-secondary evidence-basis-button"
              aria-expanded={open}
              onClick={() => setOpen((value) => !value)}
            >
              {open ? "Hide detail" : "Why these statuses?"}
            </button>
          </div>
        </td>
        <StatusCell {...{ code: row.source_support.status_code, reason: row.source_support.reason, label: row.source_support.label }} />
        <StatusCell {...{ code: row.alpha_match.status_code, reason: row.alpha_match.reason, label: row.alpha_match.label }} />
        <StatusCell {...{ code: row.stance.status_code, reason: row.stance.reason, label: row.stance.label }} />
        <StatusCell {...{ code: row.scoring.status_code, reason: row.scoring.reason, label: row.scoring.label }} />
      </tr>
      {open ? (
        <tr className="key-conclusion-detail-row">
          <td colSpan={5}>
            <EvidenceTraceDetail runId={runId} claimId={row.claim_id} />
          </td>
        </tr>
      ) : null}
    </>
  );
}

export function KeyConclusionsPanel({ runId }: { runId: string | undefined }) {
  const [view, setView] = useState<KeyConclusionsView | null>(null);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    if (!runId) return undefined;
    const controller = new AbortController();
    setView(null);
    setError(null);
    getKeyConclusions(runId, { signal: controller.signal })
      .then((result) => {
        if ("key_conclusions" in result) setView(result.key_conclusions);
        else setError(result.error_code ?? "Key-conclusion statuses are not available for this run.");
      })
      .catch((cause: unknown) => {
        if (cause instanceof ApiError && cause.isAborted) return;
        setError(cause instanceof ApiError ? describeApiError(cause) : "Key-conclusion statuses could not be loaded.");
      });
    return () => controller.abort();
  }, [runId]);

  if (!runId) return null;
  return (
    <section className="panel key-conclusions-panel" aria-label="Key conclusions verification status">
      <h2>Key conclusions — verification status</h2>
      <p className="evidence-source-disclosure">
        The final decision, the research manager&apos;s verdict and the trader&apos;s action, claim by claim. Each claim
        has four separate checks: <strong>source support</strong> (does saved source material back it),{" "}
        <strong>Alpha match</strong> (which Alpha the classifier matched), <strong>stance</strong> (its relation to
        that Alpha and who decided it) and <strong>official scoring</strong> (what it contributed to the score).
        Passing one check says nothing about the others. Ordinary commentary needs no source link.
      </p>
      {error ? <p className="evidence-trace-error" role="alert">{error}</p> : null}
      {!view && !error ? <p className="evidence-trace-loading">Loading key-conclusion statuses…</p> : null}
      {view ? (
        <>
          {view.execution_basis ? (
            <p
              className={view.execution_basis.recomputation_of_saved_inputs ? "evidence-trace-execution-basis-label" : "evidence-trace-note"}
              data-testid="key-conclusions-execution-basis"
            >
              {view.execution_basis.label ?? "The execution basis was not recorded."}
              {view.execution_basis.based_on_run_id ? (
                <>
                  {" "}
                  Saved run: <code>{view.execution_basis.based_on_run_id}</code>.
                </>
              ) : null}
            </p>
          ) : null}
          <p className="key-conclusions-summary">
            {view.claim_count} claims ·{" "}
            {Object.entries(view.status_counts.source_support ?? {})
              .map(([code, count]) => `${count} ${code.replace(/_/g, " ").toLowerCase()}`)
              .join(" · ")}
            {view.agent_wording_verified_count > 0
              ? ` · ${view.agent_wording_verified_count} contain the Agent's own word “verified” (not a system verification)`
              : ""}
          </p>
          {view.groups.length === 0 ? <p>No final-decision claims were found in this run.</p> : null}
          {view.groups.map((group) => (
            <details key={group.group} className="key-conclusions-group">
              <summary>
                {group.group} ({group.rows.length})
              </summary>
              <table className="key-conclusions-table">
                <thead>
                  <tr>
                    <th scope="col">Statement</th>
                    <th scope="col">Source support</th>
                    <th scope="col">Alpha match</th>
                    <th scope="col">Stance</th>
                    <th scope="col">Official scoring</th>
                  </tr>
                </thead>
                <tbody>
                  {group.rows.map((row) => (
                    <ConclusionRow key={row.claim_id} runId={runId} row={row} />
                  ))}
                </tbody>
              </table>
            </details>
          ))}
        </>
      ) : null}
    </section>
  );
}
