import { useRef, useState } from "react";
import { useNavigate } from "react-router-dom";
import { describeApiErrorCode } from "../api/errors";
import { ResearchForm } from "../components/ResearchForm";
import { ErrorPanel } from "../components/ErrorPanel";
import { RecentRunsMenu } from "../components/RecentRunsMenu";
import { useReadiness } from "../hooks/useReadiness";
import { useResearchSubmission } from "../hooks/useResearchSubmission";
import { canAnimate } from "../utils/motion";
import { captureStartGeometry, setRunHandoff } from "../utils/transitionHandoff";

// Live-research readiness guard (operational safety fix): a safe,
// user-facing reason the Start research button is disabled. Never an env
// var value -- these mirror the backend's own safe reason labels exactly
// (server_execution.build_live_semantic_readiness).
const LIVE_SEMANTIC_NOT_READY_MESSAGE =
  "Live semantic pipeline not ready. Real TradingAgents is enabled, but the Week2 semantic classifier or its Provider is not ready. Live research was not started.";

/** How long the hero fades out before the Processing page takes over -- at
 * least this long after the click, however fast the server answers, so the
 * fade is never cut short. */
const LEAVE_MS = 320;

/** One worked example of the evidence chain, shown at the bottom of the
 * page. Illustrative only -- it is not the result of any run. */
const TRACE_NODES = [
  {
    kind: "Claim, from the News analyst",
    text: "Cloud providers are expanding spending on AI data centers.",
    note: "Ticker-specific, supporting",
  },
  {
    kind: "Evidence fact",
    text: "3 near-duplicate claims, counted once.",
    note: "Market, News, Fundamentals",
  },
  {
    kind: "Alpha",
    text: "AI Infrastructure",
    note: "Active",
    active: true,
  },
  {
    kind: "Conflict",
    text: "AI Infrastructure against Multiple Compression",
    note: "Admitted, both sides have qualifying evidence",
    emphasis: true,
  },
] as const;

function EvidenceTrace() {
  return (
    <section className="trace-section" aria-labelledby="trace-title">
      <div className="trace-heading">
        <h2 id="trace-title">How one conclusion is traced.</h2>
        <p>
          Agent statements are grouped into evidence before they count, so repeating one fact never
          inflates the signal. Illustrative example, not a run result.
        </p>
      </div>
      <div className="trace-chain">
        {TRACE_NODES.map((node, index) => (
          <div className="trace-step" key={node.kind}>
            {index > 0 ? (
              <div
                className="trace-link"
                aria-hidden="true"
                style={{ animationDelay: `${(index * 0.45).toFixed(2)}s` }}
              />
            ) : null}
            <article
              className={`trace-node${"emphasis" in node ? " trace-node-emphasis" : ""}`}
              style={{ animationDelay: `${(0.15 + index * 0.45).toFixed(2)}s` }}
            >
              <span className="trace-node-kind">{node.kind}</span>
              <p className="trace-node-text">{node.text}</p>
              <span className={`trace-node-note${"active" in node ? " trace-node-note-active" : ""}`}>
                {"active" in node ? <span className="status-dot status-dot-active" aria-hidden="true" /> : null}
                {node.note}
              </span>
            </article>
          </div>
        ))}
      </div>
    </section>
  );
}

export function ResearchPage() {
  const navigate = useNavigate();
  const { isSubmitting, errorMessage, submit } = useResearchSubmission();
  const [submissionError, setSubmissionError] = useState<string | null>(null);
  // From the click until the page is left (or the start fails): the hero
  // fades out and the form shows "Starting…", even in the instant between
  // the server answering and the navigation.
  const [isLeaving, setIsLeaving] = useState(false);
  const leavingRef = useRef(false);
  const { readiness, errorMessage: readinessErrorMessage } = useReadiness();
  // Live-research readiness guard (operational safety fix): never let the
  // user submit a live run doomed to record zero Alpha activation because
  // Week2's semantic pipeline isn't ready. `readiness === null` (still
  // loading) does NOT disable the button -- only a confirmed "not_ready"
  // does, so the form stays usable while the readiness check is in flight
  // or for an offline-only server where this guard never applies.
  const formDisabledReason =
    readiness?.live_semantic_pipeline === "not_ready" ? LIVE_SEMANTIC_NOT_READY_MESSAGE : null;

  function stopLeaving() {
    leavingRef.current = false;
    setIsLeaving(false);
  }

  async function handleSubmit(request: Parameters<typeof submit>[0]) {
    if (leavingRef.current) return;
    leavingRef.current = true;
    setIsLeaving(true);
    setSubmissionError(null);
    const clickedAt = Date.now();
    const outcome = await submit(request);
    if (!outcome) {
      stopLeaving();
      return;
    }

    const { result } = outcome;
    if (result.status === "failed" && result.error_code) {
      setSubmissionError(
        describeApiErrorCode(result.error_code, result.message ?? undefined)
      );
      stopLeaving();
      return;
    }
    if (result.run_id) {
      // HTTP 200 completed reuse: the canonical result already exists, so
      // go straight to it. Anything queued/running (HTTP 202, including an
      // in-flight reuse) goes to the Processing page, which polls real
      // progress and forwards to the results when the run finishes.
      const target =
        result.cache_disposition === "reused_completed" ? "research" : "processing";
      if (target === "processing") {
        // Let the fade finish, then hand the Processing page where the
        // ticker and the button are right now so it can animate from them.
        const animated = canAnimate();
        if (animated) {
          await new Promise((resolve) => setTimeout(resolve, Math.max(0, LEAVE_MS - (Date.now() - clickedAt))));
        }
        setRunHandoff({
          runId: result.run_id,
          ticker: request.ticker,
          analysisDate: request.analysis_date ?? null,
          selectedAnalysts: request.selected_analysts ?? [],
          geometry: animated ? captureStartGeometry() : null,
          createdAt: Date.now(),
        });
      }
      navigate(`/runs/${encodeURIComponent(result.run_id)}/${target}`, {
        state: result.cache_disposition ? { cacheDisposition: result.cache_disposition } : undefined,
      });
      return;
    }
    stopLeaving();
  }

  return (
    <div className={isLeaving ? "research-page research-page-leaving" : "research-page"}>
      {/* Not a labelled region: a name containing "ticker" would also match
          getByLabel("Ticker") and make the input ambiguous. */}
      <section className="research-hero">
        <h1>Research a ticker.</h1>
        <p className="research-hero-subtitle">
          Every conclusion arrives with the claims and evidence behind it.
        </p>
        <ResearchForm
          isSubmitting={isSubmitting || isLeaving}
          onSubmit={handleSubmit}
          disabledReason={formDisabledReason}
          leadingAction={<RecentRunsMenu locked={isSubmitting || isLeaving} />}
        />
        {readinessErrorMessage ? (
          <p className="research-hero-notice" role="alert">
            {readinessErrorMessage}
          </p>
        ) : null}
        {errorMessage ? <ErrorPanel message={errorMessage} /> : null}
        {submissionError ? <ErrorPanel message={submissionError} /> : null}
      </section>

      <EvidenceTrace />
    </div>
  );
}
