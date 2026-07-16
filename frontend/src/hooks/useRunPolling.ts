import { useCallback, useEffect, useRef, useState } from "react";
import { getResearchRunStatus } from "../api/client";
import { ApiError } from "../api/errors";
import type { RunStatusResult } from "../api/types";

/** Backoff sequence (ms) between polls while a run is still queued/running:
 * 1s, 2s, 3s, then capped at 5s. Never faster than 1s, never unbounded. */
const POLL_BACKOFF_MS = [1000, 2000, 3000, 5000];

function nextDelay(pollCount: number): number {
  const index = Math.min(pollCount, POLL_BACKOFF_MS.length - 1);
  return POLL_BACKOFF_MS[index] ?? 5000;
}

function isTerminalStatus(status: string | undefined): boolean {
  return status === "completed" || status === "partial" || status === "failed";
}

export interface UseRunPollingResult {
  status: RunStatusResult | null;
  error: ApiError | null;
  isPolling: boolean;
  /** Manually trigger an immediate re-fetch (e.g. a user-clicked Refresh
   * button). Safe to call at any time; it cancels and reschedules the
   * normal backoff timer around this one extra fetch. */
  refresh: () => void;
}

/**
 * Polls GET /api/research/{run_id}/status with increasing backoff while the
 * run is queued/running, and stops entirely once it reaches a terminal
 * status (completed/partial/failed) or the run_id becomes null/empty.
 *
 * Exactly one polling loop exists per mounted hook instance -- changing
 * runId cancels the previous loop's in-flight request and timer before
 * starting a new one; unmounting does the same. A transient network
 * failure never flips the run to "failed" client-side: it is surfaced via
 * `error` (with the last known `status` left untouched) and retried on the
 * same backoff schedule.
 */
export function useRunPolling(runId: string | null | undefined): UseRunPollingResult {
  const [status, setStatus] = useState<RunStatusResult | null>(null);
  const [error, setError] = useState<ApiError | null>(null);
  const [isPolling, setIsPolling] = useState(false);

  const abortRef = useRef<AbortController | null>(null);
  const timerRef = useRef<ReturnType<typeof setTimeout> | null>(null);
  const pollCountRef = useRef(0);
  const mountedRef = useRef(true);

  const clearTimer = useCallback(() => {
    if (timerRef.current !== null) {
      clearTimeout(timerRef.current);
      timerRef.current = null;
    }
  }, []);

  const runFetch = useCallback(
    (currentRunId: string) => {
      abortRef.current?.abort();
      const controller = new AbortController();
      abortRef.current = controller;
      setIsPolling(true);

      getResearchRunStatus(currentRunId, { signal: controller.signal })
        .then((result) => {
          if (!mountedRef.current || controller.signal.aborted) return;
          setStatus(result);
          setError(null);
          const currentStatus = "status" in result ? result.status : undefined;
          if (!isTerminalStatus(currentStatus)) {
            const delay = nextDelay(pollCountRef.current);
            pollCountRef.current += 1;
            clearTimer();
            timerRef.current = setTimeout(() => runFetch(currentRunId), delay);
          } else {
            setIsPolling(false);
          }
        })
        .catch((cause: unknown) => {
          if (!mountedRef.current || controller.signal.aborted) return;
          const apiError = cause instanceof ApiError ? cause : ApiError.network();
          if (apiError.isAborted) return;
          setError(apiError);
          // Network hiccups keep retrying on the same backoff schedule --
          // never treated as a terminal failure of the run itself.
          const delay = nextDelay(pollCountRef.current);
          pollCountRef.current += 1;
          clearTimer();
          timerRef.current = setTimeout(() => runFetch(currentRunId), delay);
        });
    },
    [clearTimer]
  );

  useEffect(() => {
    mountedRef.current = true;
    pollCountRef.current = 0;
    setStatus(null);
    setError(null);
    setIsPolling(false);
    clearTimer();
    abortRef.current?.abort();

    if (runId) {
      runFetch(runId);
    }

    return () => {
      mountedRef.current = false;
      clearTimer();
      abortRef.current?.abort();
    };
    // eslint-disable-next-line react-hooks/exhaustive-deps -- runFetch is stable via useCallback([clearTimer])
  }, [runId]);

  const refresh = useCallback(() => {
    if (!runId) return;
    pollCountRef.current = 0;
    clearTimer();
    runFetch(runId);
  }, [runId, runFetch, clearTimer]);

  return { status, error, isPolling, refresh };
}
