import { useState } from "react";
import { Link, useLocation, useParams } from "react-router-dom";
import { RunNavigation } from "../components/RunNavigation";
import { RunStatusBanner } from "../components/RunStatusBanner";
import { ErrorPanel } from "../components/ErrorPanel";
import { LoadingPanel } from "../components/LoadingPanel";
import { EmptyState } from "../components/EmptyState";
import { useRunPolling } from "../hooks/useRunPolling";
import { useResearchRun } from "../hooks/useResearchRun";
import { describeApiError } from "../api/errors";
import type {
  CanonicalResearchResponse,
  DataSanityNumericSemantics,
  DataSanityWarning,
  StructuredAgentOutputRecord,
} from "../api/types";

function shortenRunId(runId: string): string {
  return runId.length > 12 ? `${runId.slice(0, 8)}…${runId.slice(-4)}` : runId;
}

function isTerminalStatus(status: string | undefined): boolean {
  return status === "completed" || status === "partial" || status === "failed";
}

// The Research page's directional panels only ever show a clear positive or
// negative call -- "unknown"/"mixed"/missing findings are still valid claims
// (kept in artifacts/API/DB unchanged) but are a presentation-layer
// distraction here. This is display-only filtering; it must never mutate the
// API response.
function isDirectionalFinding(direction: string): boolean {
  return direction === "positive" || direction === "negative";
}

// Section G1: deterministic, reproducible sort -- no importance score, no
// LLM, no new semantic dedupe. Applied independently within each direction.
function compareFindings(a: StructuredAgentOutputRecord, b: StructuredAgentOutputRecord): number {
  if (b.confidence !== a.confidence) {
    return b.confidence - a.confidence;
  }
  const aHasEvidence = Boolean(a.evidence && a.evidence.trim().length > 0);
  const bHasEvidence = Boolean(b.evidence && b.evidence.trim().length > 0);
  if (aHasEvidence !== bHasEvidence) {
    return aHasEvidence ? -1 : 1;
  }
  const aIndex = typeof a.claim_index === "number" ? a.claim_index : Number.POSITIVE_INFINITY;
  const bIndex = typeof b.claim_index === "number" ? b.claim_index : Number.POSITIVE_INFINITY;
  if (aIndex !== bIndex) {
    return aIndex - bIndex;
  }
  if (a.claim_id < b.claim_id) return -1;
  if (a.claim_id > b.claim_id) return 1;
  return 0;
}

const MAX_FINDINGS_PER_DIRECTION = 20;
const DEFAULT_FINDINGS_SHOWN = 1;

// One finding card. Direction is never repeated here -- it is already
// expressed once by the enclosing panel's own heading (Section G3).
function FindingCard({ record }: { record: StructuredAgentOutputRecord }) {
  return (
    <li className="analyst-output-card">
      <dl className="analyst-output-meta-list">
        <div className="analyst-output-meta-row">
          <dt>Agent</dt>
          <dd>{record.agent}</dd>
        </div>
      </dl>
      <p className="analyst-output-claim">{record.claim}</p>
      {record.evidence && record.evidence !== record.claim ? (
        <p className="analyst-output-evidence">{record.evidence}</p>
      ) : null}
      <p className="analyst-output-confidence">
        Confidence {(record.confidence * 100).toFixed(0)}% · <code>{record.claim_id}</code>
      </p>
    </li>
  );
}

// One direction's panel (Positive or Negative): independent sort, independent
// default/expand state, capped at MAX_FINDINGS_PER_DIRECTION regardless of
// how many eligible records exist upstream. This limit is presentation-only
// -- it never returns to the backend, and never affects the API/artifact/DB.
function DirectionalFindingsPanel({
  direction,
  title,
  emptyMessage,
  records,
}: {
  direction: "positive" | "negative";
  title: string;
  emptyMessage: string;
  records: StructuredAgentOutputRecord[];
}) {
  const [expanded, setExpanded] = useState(false);
  const directionRecords = records.filter((record) => record.direction === direction);
  const sorted = [...directionRecords].sort(compareFindings);
  const eligible = sorted.slice(0, MAX_FINDINGS_PER_DIRECTION);
  const shown = expanded ? eligible : eligible.slice(0, DEFAULT_FINDINGS_SHOWN);
  const moreCount = eligible.length - DEFAULT_FINDINGS_SHOWN;

  return (
    <section className={`panel directional-findings-panel directional-findings-panel-${direction}`}>
      <h3>{title}</h3>
      {eligible.length === 0 ? (
        <EmptyState title={emptyMessage} />
      ) : (
        <>
          <ul className="analyst-output-list">
            {shown.map((record) => (
              <FindingCard key={record.claim_id} record={record} />
            ))}
          </ul>
          {moreCount > 0 ? (
            <button
              type="button"
              className="button button-secondary directional-findings-toggle"
              onClick={() => setExpanded((value) => !value)}
            >
              {expanded ? "Less" : `More (${moreCount})`}
            </button>
          ) : null}
        </>
      )}
    </section>
  );
}

// Section 19 (Product Transparency, low priority): a low-risk entry point
// onto the neutral/unclassified findings the two directional panels
// deliberately exclude -- reuses the SAME analytical claims the API already
// returns (never mixes in context-only claims, never deletes the
// positive/negative panels, never renders all hidden findings at once).
function NeutralFindingsPanel({ records }: { records: StructuredAgentOutputRecord[] }) {
  const [expanded, setExpanded] = useState(false);
  const hidden = records.filter((record) => !isDirectionalFinding(record.direction));
  if (hidden.length === 0) return null;
  const sorted = [...hidden].sort(compareFindings);
  const shown = sorted.slice(0, MAX_FINDINGS_PER_DIRECTION);
  const truncatedCount = hidden.length - shown.length;

  return (
    <details
      className="panel neutral-findings-panel"
      open={expanded}
      onToggle={(event) => setExpanded((event.target as HTMLDetailsElement).open)}
    >
      <summary>Neutral and unclassified findings ({hidden.length})</summary>
      {expanded ? (
        <>
          <ul className="analyst-output-list">
            {shown.map((record) => (
              <FindingCard key={record.claim_id} record={record} />
            ))}
          </ul>
          {truncatedCount > 0 ? (
            <p className="analyst-output-hidden-note">
              {truncatedCount} more neutral or unclassified finding(s) are not shown here.
            </p>
          ) : null}
        </>
      ) : null}
    </details>
  );
}

function detailString(details: Record<string, unknown>, key: string): string | null {
  const value = details[key];
  return typeof value === "string" ? value : null;
}

function detailNumber(details: Record<string, unknown>, key: string): number | null {
  const value = details[key];
  return typeof value === "number" ? value : null;
}

function warningDate(details: Record<string, unknown>): string | null {
  return (
    detailString(details, "date") ??
    detailString(details, "reported_date") ??
    detailString(details, "analysis_date") ??
    detailString(details, "last_available_session")
  );
}

// A single warning's own severity always drives its presentation -- an
// info-level corporate-action signal (a stock split/dividend) is never
// rendered as critical just because the overall run status is.
function DataQualityWarningItem({ warning }: { warning: DataSanityWarning }) {
  const date = warningDate(warning.details);
  const reportedPrice = detailNumber(warning.details, "reported_price");
  const externalReference = detailNumber(warning.details, "external_reference");
  const splitRatio = detailNumber(warning.details, "stock_split") ?? detailNumber(warning.details, "split_ratio");

  return (
    <li className={`data-quality-warning-item data-quality-severity-${warning.severity}`}>
      <p className="data-quality-warning-message">{warning.message}</p>
      <dl className="data-quality-warning-meta">
        <div className="data-quality-warning-meta-row">
          <dt>Code</dt>
          <dd>{warning.code}</dd>
        </div>
        <div className="data-quality-warning-meta-row">
          <dt>Severity</dt>
          <dd>{warning.severity}</dd>
        </div>
        {date ? (
          <div className="data-quality-warning-meta-row">
            <dt>Date</dt>
            <dd>{date}</dd>
          </div>
        ) : null}
        {reportedPrice !== null ? (
          <div className="data-quality-warning-meta-row">
            <dt>Reported price</dt>
            <dd>${reportedPrice.toFixed(2)}</dd>
          </div>
        ) : null}
        {externalReference !== null ? (
          <div className="data-quality-warning-meta-row">
            <dt>External reference</dt>
            <dd>${externalReference.toFixed(2)}</dd>
          </div>
        ) : null}
        {splitRatio !== null ? (
          <div className="data-quality-warning-meta-row">
            <dt>Split ratio</dt>
            <dd>{splitRatio}</dd>
          </div>
        ) : null}
      </dl>
    </li>
  );
}

// Evidence Integrity Completion Sprint, Track C: aggregate transparency for
// numeric candidates that were classified as a technical indicator (or
// other non-market-price role) and therefore never entered the warning list
// above -- never per-candidate detail (the backend does not persist that),
// and never itself rendered as a warning.
function DataQualityNumericSemanticsSummary({
  semantics,
}: {
  semantics: DataSanityNumericSemantics;
}) {
  if (semantics.skipped_by_role_count === 0) return null;
  const roleEntries = Object.entries(semantics.semantic_role_counts);
  return (
    <details className="data-quality-numeric-semantics">
      <summary>
        {semantics.skipped_by_role_count} numeric candidate(s) skipped as non-market-price
      </summary>
      <p className="data-quality-numeric-semantics-note">
        These figures (e.g. a moving average) are not observed market prices and are never
        compared against a day&apos;s trading range.
      </p>
      {roleEntries.length > 0 ? (
        <ul>
          {roleEntries.map(([role, count]) => (
            <li key={role}>
              Numeric role: {role} — {count}
            </li>
          ))}
        </ul>
      ) : null}
      <p className="data-quality-numeric-semantics-eligible">
        Daily-range check: eligible for {semantics.daily_range_eligible_count} of{" "}
        {semantics.evaluated_count} candidate(s); skipped for the rest (reason: technical
        indicator or unresolved numeric role).
      </p>
    </details>
  );
}

// Yahoo Finance/yfinance is one independent cross-check input, never
// treated as absolute market truth -- this panel only ever surfaces the
// backend's own status/warnings verbatim, never recomputes or upgrades
// severity, and never hides/alters Analyst findings, claims, or Activation.
function DataQualityPanel({ response }: { response: CanonicalResearchResponse }) {
  const status = response.data_sanity_status;
  const numericSemantics = response.data_sanity_numeric_semantics ?? null;

  if (status === "ok") {
    return (
      <>
        <p className="data-quality-ok-text">External market-data cross-check completed with no warnings.</p>
        {numericSemantics ? <DataQualityNumericSemanticsSummary semantics={numericSemantics} /> : null}
      </>
    );
  }
  if (status === "unavailable") {
    return <p className="data-quality-neutral-text">External market-data cross-check is unavailable for this run.</p>;
  }
  if (status === "disabled") {
    return <p className="data-quality-neutral-text">External market-data cross-check was disabled for this run.</p>;
  }
  if (status === "not_available") {
    return <p className="data-quality-neutral-text">No data-quality artifact is available for this historical run.</p>;
  }

  const panelClassName = status === "critical" ? "data-quality-body-critical" : "data-quality-body-warning";
  return (
    <div className={panelClassName}>
      <ul className="data-quality-warning-list">
        {response.data_sanity_warnings.map((warning, index) => (
          <DataQualityWarningItem key={`${warning.code}-${index}`} warning={warning} />
        ))}
      </ul>
      {numericSemantics ? <DataQualityNumericSemanticsSummary semantics={numericSemantics} /> : null}
    </div>
  );
}

export function ResearchRunPage() {
  const { runId } = useParams<{ runId: string }>();
  const location = useLocation();
  const cacheDisposition =
    location.state && typeof location.state === "object" && "cacheDisposition" in location.state
      ? String((location.state as { cacheDisposition?: string }).cacheDisposition ?? "")
      : null;

  const { status: pollStatus, error: pollError, refresh } = useRunPolling(runId);
  const currentStatus = pollStatus && "status" in pollStatus ? pollStatus.status : undefined;
  const terminal = isTerminalStatus(currentStatus);
  // A failed run never has a canonical result/agent-outputs worth fetching
  // -- only completed/partial do.
  const shouldLoadResult = terminal && currentStatus !== "failed";
  const { research, agentOutputs, isLoading: isLoadingResult, error: resultError } = useResearchRun(
    shouldLoadResult ? runId ?? null : null
  );

  if (!runId) {
    return <EmptyState title="Missing run_id" description="No research run was specified." />;
  }

  const allRecords =
    agentOutputs && "structured_agent_outputs" in agentOutputs ? agentOutputs.structured_agent_outputs : [];

  return (
    <div className="research-run-page">
      <RunNavigation runId={runId} />

      <section className="panel run-header-panel">
        <div className="run-header-row">
          <div>
            <h1>{("ticker" in (pollStatus ?? {}) && (pollStatus as { ticker?: string }).ticker) || "Research run"}</h1>
            <p className="run-id-display">
              Run ID: <code>{shortenRunId(runId)}</code>
            </p>
          </div>
          <button type="button" className="button button-secondary" onClick={refresh}>
            Refresh
          </button>
        </div>
        <dl className="run-header-meta">
          {"analysis_date" in (pollStatus ?? {}) ? (
            <div>
              <dt>Analysis date</dt>
              <dd>{(pollStatus as { analysis_date?: string | null }).analysis_date ?? "Not available"}</dd>
            </div>
          ) : null}
          {cacheDisposition ? (
            <div>
              <dt>Cache disposition</dt>
              <dd>{cacheDisposition}</dd>
            </div>
          ) : null}
        </dl>
        {pollStatus ? (
          <RunStatusBanner
            status={currentStatus ?? "queued"}
            stage={"stage" in pollStatus ? pollStatus.stage : null}
            errorCode={"error_code" in pollStatus ? pollStatus.error_code : null}
            message={"message" in pollStatus ? pollStatus.message : null}
          />
        ) : (
          <LoadingPanel label="Loading run status…" />
        )}
        {pollError ? (
          <ErrorPanel
            title="Connection issue"
            message={describeApiError(pollError)}
            onRetry={refresh}
          />
        ) : null}
      </section>

      {currentStatus === "failed" ? (
        <section className="panel run-failed-panel">
          <h2>This research run failed</h2>
          <p>See the error details above.</p>
          <Link to="/research" className="button button-primary">
            Back to Research
          </Link>
        </section>
      ) : null}

      {!terminal ? (
        <section className="panel">
          <LoadingPanel label={`Research run is ${currentStatus ?? "in progress"}. This page updates automatically.`} />
        </section>
      ) : null}

      {shouldLoadResult ? (
        <>
          {isLoadingResult ? <LoadingPanel label="Loading research results…" /> : null}
          {resultError ? <ErrorPanel message={describeApiError(resultError)} /> : null}
          {research && "summary" in research ? (
            <section className="panel research-summary-panel">
              <h2>Research summary</h2>
              <p>{research.summary}</p>
            </section>
          ) : null}

          {research && "data_sanity_status" in research ? (
            <section className="panel data-quality-panel">
              <h2>Data Quality</h2>
              <DataQualityPanel response={research} />
            </section>
          ) : null}

          <section className="panel analyst-outputs-panel">
            <h2>Analyst findings</h2>
            {agentOutputs && "structured_agent_outputs" in agentOutputs ? (
              allRecords.length === 0 ? (
                <EmptyState title="No structured analyst outputs yet" />
              ) : (
                <>
                  <div className="directional-findings-columns">
                    <DirectionalFindingsPanel
                      direction="positive"
                      title="Positive findings"
                      emptyMessage="No eligible positive findings were identified."
                      records={allRecords}
                    />
                    <DirectionalFindingsPanel
                      direction="negative"
                      title="Negative findings"
                      emptyMessage="No eligible negative findings were identified."
                      records={allRecords}
                    />
                  </div>
                  <NeutralFindingsPanel records={allRecords} />
                </>
              )
            ) : null}
          </section>
        </>
      ) : null}

      <section className="panel comqutor-explainer-panel">
        <h2>Why this is not a typical AI stock summary</h2>
        <p>
          Instead of producing one free-text opinion, COMQUTOR converts agent evidence into
          structured claims, maps them onto a fixed Alpha taxonomy, assembles an Alpha structure
          graph, scores activation for every Alpha, detects structural conflicts, and keeps every
          claim traceable to its source evidence. It does not predict outcomes, guarantee profit,
          or eliminate investment risk.
        </p>
      </section>
    </div>
  );
}
