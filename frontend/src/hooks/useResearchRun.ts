import { useCallback, useEffect, useRef, useState } from "react";
import { getAgentOutputs, getResearchRun } from "../api/client";
import { ApiError } from "../api/errors";
import type { AgentOutputsResult, CanonicalResearchResult } from "../api/types";

export interface UseResearchRunResult {
  research: CanonicalResearchResult | null;
  agentOutputs: AgentOutputsResult | null;
  isLoading: boolean;
  error: ApiError | null;
  reload: () => void;
}

/**
 * Loads the canonical research response (GET /api/research/{run_id}) and the
 * structured, public-whitelisted agent outputs (GET
 * /api/research/{run_id}/agent-outputs) for one run_id. Both requests share
 * one AbortController per runId so navigating away (or the run_id changing)
 * cancels both in flight requests together.
 */
export function useResearchRun(runId: string | null | undefined): UseResearchRunResult {
  const [research, setResearch] = useState<CanonicalResearchResult | null>(null);
  const [agentOutputs, setAgentOutputs] = useState<AgentOutputsResult | null>(null);
  const [isLoading, setIsLoading] = useState(false);
  const [error, setError] = useState<ApiError | null>(null);
  const abortRef = useRef<AbortController | null>(null);

  const load = useCallback((currentRunId: string) => {
    abortRef.current?.abort();
    const controller = new AbortController();
    abortRef.current = controller;
    setIsLoading(true);
    setError(null);

    Promise.all([
      getResearchRun(currentRunId, { signal: controller.signal }),
      getAgentOutputs(currentRunId, { signal: controller.signal }),
    ])
      .then(([researchResult, agentOutputsResult]) => {
        if (controller.signal.aborted) return;
        setResearch(researchResult);
        setAgentOutputs(agentOutputsResult);
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
    setResearch(null);
    setAgentOutputs(null);
    setError(null);
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

  return { research, agentOutputs, isLoading, error, reload };
}
