import { useEffect, useId, useRef, useState, type FormEvent } from "react";
import { Link } from "react-router-dom";
import { getResearchHistory } from "../api/client";
import { ApiError, describeApiError } from "../api/errors";
import type { ResearchRunRecord } from "../api/types";
import { describeRunStatus, formatAnalysisDate, formatCreatedAt, pathForRun } from "../utils/runFormat";

const RECENT_RUNS_PAGE_SIZE = 10;

function normalizeTickerFilter(raw: string): string | undefined {
  const normalized = raw.trim().toUpperCase();
  return normalized.length > 0 ? normalized : undefined;
}

/**
 * "Recent runs" disclosure for the Research page: a button that opens a
 * floating menu of earlier runs. The history is requested when the menu
 * opens (first page of 10), never while it is closed. Closes on a second
 * click of the button, Escape, a click outside, or picking a run.
 */
export function RecentRunsMenu({ locked = false }: { locked?: boolean }) {
  const [openState, setOpen] = useState(false);
  // Locked (a run is being started): closed and not openable.
  const open = openState && !locked;

  useEffect(() => {
    if (locked) setOpen(false);
  }, [locked]);
  const buttonRef = useRef<HTMLButtonElement>(null);
  const panelRef = useRef<HTMLDivElement>(null);
  const menuId = useId();

  useEffect(() => {
    if (!open) return;
    function handlePointerDown(event: PointerEvent) {
      const target = event.target as Node | null;
      if (!target) return;
      if (buttonRef.current?.contains(target) || panelRef.current?.contains(target)) return;
      setOpen(false);
    }
    function handleKeyDown(event: KeyboardEvent) {
      if (event.key !== "Escape") return;
      setOpen(false);
      buttonRef.current?.focus();
    }
    document.addEventListener("pointerdown", handlePointerDown);
    document.addEventListener("keydown", handleKeyDown);
    return () => {
      document.removeEventListener("pointerdown", handlePointerDown);
      document.removeEventListener("keydown", handleKeyDown);
    };
  }, [open]);

  return (
    <>
      <button
        ref={buttonRef}
        type="button"
        className="ghost-button"
        aria-expanded={open}
        aria-controls={menuId}
        disabled={locked}
        onClick={() => setOpen((current) => !current)}
      >
        <svg
          aria-hidden="true"
          width="16"
          height="16"
          viewBox="0 0 16 16"
          fill="none"
          stroke="currentColor"
          strokeWidth="1.5"
          strokeLinecap="round"
          strokeLinejoin="round"
        >
          <circle cx="8" cy="8" r="6.25" />
          <path d="M8 4.75V8l2.25 1.5" />
        </svg>
        <span>Recent runs</span>
        <svg
          className={open ? "chevron chevron-open" : "chevron"}
          aria-hidden="true"
          width="10"
          height="6"
          viewBox="0 0 10 6"
          fill="none"
          stroke="currentColor"
          strokeWidth="1.5"
          strokeLinecap="round"
          strokeLinejoin="round"
        >
          <path d="M1 1l4 4 4-4" />
        </svg>
      </button>
      {open ? <RecentRunsPanel id={menuId} panelRef={panelRef} onNavigate={() => setOpen(false)} /> : null}
    </>
  );
}

interface RecentRunsPanelProps {
  id: string;
  panelRef: React.RefObject<HTMLDivElement>;
  onNavigate: () => void;
}

/**
 * John MVP Gap Closure, Gap A (Run History Discovery), inside the menu:
 * first page of 10, cursor-based "Load more" so a user can reach runs
 * beyond the first 10, and a ticker filter -- both using the existing
 * getResearchHistory(limit/cursor/ticker/status) contract as-is, never a new
 * storage/query mechanism. Newly-loaded pages are appended and de-duplicated
 * by run_id so "Load more" can never produce a repeated row. A
 * load-more/filter failure renders its own honest error message without
 * discarding rows already on screen.
 */
function RecentRunsPanel({ id, panelRef, onNavigate }: RecentRunsPanelProps) {
  const filterId = useId();
  const [tickerInput, setTickerInput] = useState("");
  const [appliedTicker, setAppliedTicker] = useState<string | undefined>(undefined);
  const [items, setItems] = useState<ResearchRunRecord[] | null>(null);
  const [nextCursor, setNextCursor] = useState<string | null>(null);
  const [errorMessage, setErrorMessage] = useState<string | null>(null);
  const [isLoadingMore, setIsLoadingMore] = useState(false);
  const [loadMoreError, setLoadMoreError] = useState<string | null>(null);

  // Initial load, and reload from scratch whenever the applied ticker
  // filter changes -- a filter change is a new query, not a "load more".
  useEffect(() => {
    const controller = new AbortController();
    setItems(null);
    setErrorMessage(null);
    setNextCursor(null);
    setLoadMoreError(null);
    getResearchHistory(
      { limit: RECENT_RUNS_PAGE_SIZE, ticker: appliedTicker },
      { signal: controller.signal }
    )
      .then((result) => {
        if (controller.signal.aborted) return;
        if (result.status === "ok") {
          setItems(result.items);
          setNextCursor(result.next_cursor);
        } else {
          setErrorMessage(result.message ?? "Recent research runs are unavailable.");
        }
      })
      .catch((cause: unknown) => {
        if (controller.signal.aborted) return;
        const apiError = cause instanceof ApiError ? cause : ApiError.network();
        if (!apiError.isAborted) setErrorMessage(describeApiError(apiError));
      });
    return () => controller.abort();
  }, [appliedTicker]);

  async function handleLoadMore() {
    if (!nextCursor || isLoadingMore) return;
    setIsLoadingMore(true);
    setLoadMoreError(null);
    try {
      const result = await getResearchHistory({
        limit: RECENT_RUNS_PAGE_SIZE,
        cursor: nextCursor,
        ticker: appliedTicker,
      });
      if (result.status === "ok") {
        setItems((previous) => {
          const existingRunIds = new Set((previous ?? []).map((item) => item.run_id));
          const newItems = result.items.filter((item) => !existingRunIds.has(item.run_id));
          return [...(previous ?? []), ...newItems];
        });
        setNextCursor(result.next_cursor);
      } else {
        setLoadMoreError(result.message ?? "Could not load more research runs.");
      }
    } catch (cause) {
      const apiError = cause instanceof ApiError ? cause : ApiError.network();
      if (!apiError.isAborted) setLoadMoreError(describeApiError(apiError));
    } finally {
      setIsLoadingMore(false);
    }
  }

  function handleFilterSubmit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    setAppliedTicker(normalizeTickerFilter(tickerInput));
  }

  function handleClearFilter() {
    setTickerInput("");
    setAppliedTicker(undefined);
  }

  return (
    <div id={id} ref={panelRef} className="recent-runs-menu" role="region" aria-label="Recent runs">
      <div className="recent-runs-menu-header">
        <span className="recent-runs-menu-title">Recent runs</span>
        <form className="recent-runs-filter" onSubmit={handleFilterSubmit} role="search">
          <label htmlFor={filterId} className="visually-hidden">
            Filter by ticker
          </label>
          <input
            id={filterId}
            type="text"
            autoComplete="off"
            spellCheck={false}
            value={tickerInput}
            placeholder="Filter by ticker"
            onChange={(event) => setTickerInput(event.target.value)}
          />
          <button type="submit" className="menu-text-button">
            Filter
          </button>
          {appliedTicker ? (
            <button type="button" className="menu-text-button" onClick={handleClearFilter}>
              Clear ({appliedTicker})
            </button>
          ) : null}
        </form>
      </div>

      <div className="recent-runs-scroll">
        {errorMessage ? (
          <p className="recent-runs-state recent-runs-state-error" role="alert">
            {errorMessage}
          </p>
        ) : null}
        {!errorMessage && items === null ? (
          <p className="recent-runs-state" role="status">
            Loading recent research runs…
          </p>
        ) : null}
        {!errorMessage && items !== null && items.length === 0 ? (
          <div className="recent-runs-state">
            <p className="recent-runs-state-title">
              {appliedTicker ? `No research runs found for ${appliedTicker}` : "No research runs yet"}
            </p>
            <p>
              {appliedTicker
                ? "Try a different ticker, or clear the filter."
                : "Enter a ticker above to start your first run."}
            </p>
          </div>
        ) : null}
        {!errorMessage && items !== null && items.length > 0 ? (
          <>
            <ul className="recent-runs-list">
              {items.map((item) => {
                const status = describeRunStatus(item.status);
                return (
                  <li key={item.run_id}>
                    <Link className="recent-run-row" to={pathForRun(item)} onClick={onNavigate}>
                      <span className="recent-run-ticker">{item.ticker}</span>{" "}
                      <span className="recent-run-meta">
                        <span className={`recent-run-status recent-run-status-${status.tone}`}>
                          <span className="status-dot" aria-hidden="true" />
                          {status.label}
                        </span>{" "}
                        <span className="recent-run-date">
                          Analysis date {formatAnalysisDate(item.analysis_date)}
                        </span>
                      </span>{" "}
                      <span className="recent-run-created">{formatCreatedAt(item.created_at)}</span>
                      <svg
                        aria-hidden="true"
                        width="7"
                        height="12"
                        viewBox="0 0 7 12"
                        fill="none"
                        stroke="currentColor"
                        strokeWidth="1.5"
                        strokeLinecap="round"
                        strokeLinejoin="round"
                      >
                        <path d="M1.25 1.25 5.75 6l-4.5 4.75" />
                      </svg>
                    </Link>
                  </li>
                );
              })}
            </ul>
            {loadMoreError ? (
              <p className="recent-runs-state recent-runs-state-error" role="alert">
                {loadMoreError}{" "}
                <button type="button" className="menu-text-button" onClick={handleLoadMore}>
                  Retry
                </button>
              </p>
            ) : null}
            {nextCursor ? (
              <button
                type="button"
                className="recent-runs-load-more"
                onClick={handleLoadMore}
                disabled={isLoadingMore}
              >
                {isLoadingMore ? "Loading…" : "Load more"}
              </button>
            ) : null}
          </>
        ) : null}
      </div>
    </div>
  );
}
