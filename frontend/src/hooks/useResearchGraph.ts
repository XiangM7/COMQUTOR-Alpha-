import { useCallback, useEffect, useRef, useState } from "react";
import { getResearchGraph } from "../api/client";
import { ApiError } from "../api/errors";
import type { StructureGraphResult } from "../api/types";

export interface UseResearchGraphResult {
  graph: StructureGraphResult | null;
  isLoading: boolean;
  error: ApiError | null;
  /** Sprint 1 (Run Identity Integrity) guard, mirrored from
   * StructureGraphPage's own useGraphAndConflicts: true when the server
   * returned data for a different run_id than the one requested. Distinct
   * from `error` -- never silently rendered. */
  runMismatch: boolean;
  reload: () => void;
}

/**
 * Loads GET /api/research/{run_id}/graph for one run_id. Used by
 * StructuralSnapshot (Product Demo Hardening Phase 2B) to show the full
 * active-Alpha list on the main Research results page, alongside the
 * separate StructureGraphPage full-detail view -- both independently fetch
 * this same endpoint on their own page mount, matching this project's
 * existing per-page-fetch convention (see useResearchRun.ts).
 */
export function useResearchGraph(runId: string | null | undefined): UseResearchGraphResult {
  const [graph, setGraph] = useState<StructureGraphResult | null>(null);
  const [isLoading, setIsLoading] = useState(false);
  const [error, setError] = useState<ApiError | null>(null);
  const [runMismatch, setRunMismatch] = useState(false);
  const abortRef = useRef<AbortController | null>(null);

  const load = useCallback((currentRunId: string) => {
    abortRef.current?.abort();
    const controller = new AbortController();
    abortRef.current = controller;
    setIsLoading(true);
    setError(null);
    setRunMismatch(false);

    getResearchGraph(currentRunId, { signal: controller.signal })
      .then((result) => {
        if (controller.signal.aborted) return;
        const resultRunId = "run_id" in result ? result.run_id : null;
        if (resultRunId && resultRunId !== currentRunId) {
          setRunMismatch(true);
          return;
        }
        setGraph(result);
      })
      .catch((cause: unknown) => {
        if (controller.signal.aborted) return;
        const apiError = cause instanceof ApiError ? cause : ApiError.network();
        if (apiError.isAborted) return;
        setError(apiError);
      })
      .finally(() => {
        if (!controller.signal.aborted) setIsLoading(false);
      });
  }, []);

  useEffect(() => {
    setGraph(null);
    setError(null);
    setRunMismatch(false);
    abortRef.current?.abort();
    if (runId) {
      load(runId);
    }
    return () => {
      abortRef.current?.abort();
    };
  }, [runId, load]);

  const reload = useCallback(() => {
    if (runId) load(runId);
  }, [runId, load]);

  return { graph, isLoading, error, runMismatch, reload };
}
